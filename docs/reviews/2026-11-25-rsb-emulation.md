# rsbpatch 解码器仿真取证（libczProject.so，ARM64）

日期：2026-11-25　任务：t62 / T63　状态：oracle 已命中

## 结论摘要

1. **oracle 命中**：把官方 `libczProject_official.so`（ARM64 Android ELF）里真正干活的
   VCDIFF 解码器放进 unicorn 执行，解 `460.1_460.2.rsbpatch` 的 163 B info 流，得到
   **4,767,744 B（0x48C000）** 输出，MD5 = `5f938695079f4a2812e0770ac261e066`，与补丁容器
   第 24 字节记录的「源头部 MD5」、以及 `460.2_460.9.rsbpatch` 期望的源头部 MD5 完全一致。
2. **两个坑必须先说清**：
   - Ghidra dump 里的地址是 **文件 vaddr + 0x100000**。`FUN_002c0fc8` 的真实文件偏移是
     `0x1C0FC8`，`FUN_002c011c` 是 `0x1C011C`。按 dump 地址直接调用只会跑到无关函数里。
   - 输出不是 `vector<vector<uint8_t>>`，而是单个 `vector<uint8_t>`（`{begin,end,cap}`），
     解码结果直接写在这块缓冲里。
3. **窗口语义**：info 流是 5 个窗口（不是 1 个），每窗口产 0x100000 B（最后一窗 0x8C000 B），
   消费 19/27/27/48/37 B，加 5 B 流头正好 163 B。窗口记录布局、varint 方向、首窗口逐字节
   解析见第六节——这份布局可以直接照抄进 `tools/rsbpatch.py`。
4. **opcode 表**是运行时填的（在 `.bss`，由全局构造写），采样见第七节；表 A/表 B 的地址、
   stride、非零项数量都能复现（`work/rsb_vectors/opcode_tables.json` 是全量 256 项 dump）。

## 一、输入与产物

| 用途 | 路径 | 大小 / 摘要 |
| --- | --- | --- |
| 被测库 | `work/versions/_incoming/libczProject_official.so` | 5,317,824 B，sha256 `0083D72B…0C19` |
| 补丁 1 | `work/versions/_incoming/460.1_460.2.rsbpatch` | 2,686,247 B，md5 `b0cbd2c7aa67d98bd0d34a26e7bbc87f` |
| 补丁 2 | `work/versions/_incoming/460.2_460.9.rsbpatch` | 9,767,076 B，md5 `d9154a78e5677de897939d0efa625b50` |
| 源（460.1） | `main.460.com.ea.game.pvz2_shu.obb` | 2,095,579,136 B = `0x7CE80000` |

产物（本任务写入）：

- `tools/emulate_rsb.py`：仿真器与 CLI（`container` / `info` / `windows` / `record` / `stream` / `vectors`）。
- `tools/tests/test_emulate_rsb.py`：13 个用例，含 oracle、窗口 trace、首窗布局、no-op、坏 magic、opcode 表。
- `work/rsb_vectors/`：`container.json`、`info_stream.hex`（163 B delta 原文）、
  `info_decoded_head.bin`（解码结果前 4 KiB）、`info_decoded.json`（窗口表 + MD5）、
  `opcode_tables.json`（两个表各 256 项）、`noop_stream.hex`/`.json`。

环境：Python 3.14，`unicorn 2.1.4`、`pyelftools 0.33`、`capstone 5.0.7`。

## 二、地址定基：dump 地址 = 文件偏移 + 0x100000

证据：dump 里 `"VCDiff"` 字符串的引用地址是 `0x2c1204`；在文件里搜到同一条
`add x?, x?, #0x27b` 的指令位于 `0x1c1204`（`0x2c1204 - 0x100000`）。据此四个函数：

| 角色 | Ghidra 名 | 文件偏移 |
| --- | --- | --- |
| 流驱动（多窗口） | `FUN_002c011c` | **0x1C011C** |
| 单窗口/记录解码 | `FUN_002c0fc8` | **0x1C0FC8** |
| RSB 容器解析（`1bsr`） | `FUN_002c2b40` | 0x1C2B40 |
| 顶层 apply | `FUN_002c469c` | 0x1C469C |

最初用 `.eh_frame_hdr` 的 FDE 起点猜入口（0x2c0fcc 一类）全部落在别的函数上，调用后
hook 到 `getpid`/`vsnprintf`/`fopen` 才暴露出来。

## 三、容器格式（实测）

```
0x00  4B   "PBSR"
0x04  u32  1
0x08  u32  2
0x0C  u64  源文件长度             patch1 = 0x7CE80000（= 盘上 OBB 字节数，逐字节相等）
0x14  u32  info 流长度            patch1 = 163        patch2 = 427125
0x18  16B  源头部 MD5             patch1 = 37ac0818…  patch2 = 5f938695…（即 oracle）
0x28  u32  build                  0x10D6 / 0x10D9
0x2C  u32  1
0x30  …    VCDIFF 流（patch1 内第二个流在 0x1978B）
```

`python tools/emulate_rsb.py container --patch …/460.1_460.2.rsbpatch`：

```
magic=PBSR source_size=0x7ce80000 info_length=163 build=0x10d6 source_md5=37ac0818b9aba97146cff6b156f6ec8e
streams at ['0x30', '0x1978b']
```

## 四、仿真器怎么搭的

- **ELF 加载**：按 `PT_LOAD` 逐段 `mem_map` + `mem_write`；处理 `R_AARCH64_RELATIVE`(1027)、
  `GLOB_DAT`(1025)、`JUMP_SLOT`(1026)、`ABS64`(1024)、`ABS32`(1029)，跳过 TLS 重定位(1030/1031)。
- **导入符号 → 蹦床**：`TRAMP_BASE=0x20000000`、`TRAMP_SIZE=0x20000`、stride 0x10，每条写
  `ret`（`0xD65F03C0`）；`UC_HOOK_CODE` 命中即按 x0..x7 派发到 Python 实现，再把返回值写回 x0、
  跳到 `RETURN_SENTINEL=0x1FFFF000` 结束本次调用。
- **内存布局**：堆 `0x30000000`（1 GiB 预留，bump）、栈 `0x70000000`（2 MiB）、
  scratch `0x80000000`（每次 `map_bytes` 单调分配新区，避免同一地址重复 map 触发 `UC_ERR_MAP`）、
  TLS 取堆最后一页，`tpidr_el0+0x28` 写 8 个 `0x5a` 当 canary（库开局 `mrs x25, tpidr_el0` 会读它）。
- **实现了的 libc/libc++ 符号**：`memcpy/memmove/bcopy/memset/memcmp/strlen`、
  `_Znwm/_Znam`（16 对齐 bump）、`_ZdlPv/_ZdaPv/free`（no-op）、`calloc/malloc/realloc`、
  `__stack_chk_fail/abort/__cxa_pure_virtual`（抛异常）、`__cxa_guard_acquire→1`、
  `__cxa_guard_release→0`、`__cxa_atexit/__cxa_finalize→0`，以及 `_ZNSt6__ndk1…`
  字符串成员（成功路径不赋值，直接返回 x0 即可跑通）。

## 五、oracle 结果（原始输出）

```
python tools/emulate_rsb.py info --patch …/460.1_460.2.rsbpatch --windows
  #0 start=   5 consumed=  19 produced=1048576 md5=d39f19b47658f16aaaaffc2c7a2331cc
  #1 start=  24 consumed=  27 produced=1048576 md5=935a20f37c9dfbd2d7892863bfe14e16
  #2 start=  51 consumed=  27 produced=1048576 md5=cf32dfefad4ad87b2cf62d5f72e2a7e8
  #3 start=  78 consumed=  48 produced=1048576 md5=8d2aa81d88d0b3b1ceedd5ac9a8028fe
  #4 start= 126 consumed=  37 produced= 573440 md5=730a9c0488566e0c40be730a8ef763e2
status=1 bytes=4767744 md5=5f938695079f4a2812e0770ac261e066
source_head_md5=37ac0818b9aba97146cff6b156f6ec8e container_md5=37ac0818b9aba97146cff6b156f6ec8e
```

解码结果前 32 字节：`31 62 73 72 04 00 00 00 …` → `"1bsr"` + 版本 4，即 460.2 的 RSB 头部容器。

调用约定（实测，不是猜的）：`STREAM_ENTRY(src, srcLen, delta, deltaLen, &outVec, writer=0, &err)`；
`outVec` 是 `std::vector<uint8_t>`，`[begin,end)` 就是输出。窗口级调用点参数为
`x0=src, x1=srcLen, x2=packages, x3=writer, x4=&cursor, x5=end, x6=&outVector, x7=&errString`
（**x4** 才是游标地址；x5 是 delta 末尾指针）。

## 六、窗口级语义

五个窗口的记录起点与消费长度如上；`consumed` 之和 158 + 流头 5 = 163，`produced` 之和
4×0x100000 + 0x8C000 = 0x48C000，与输出长度互证。

单窗口记录布局（由字节反推，并已由「按此布局重新解析 5 个窗口全部自洽」验证）：

```
type/flag byte        0x01 = 从源 COPY（0x00 = 数据段，0x02 = 从 packages COPY）
srcSegLen   varint    0x48C000
srcSegPos   varint    0
deltaLen    varint    窗口内后续字节数
  targetWindowLength varint   0x100000
  deltaIndicator     byte     0
  dataLen            varint
  instLen            varint
  addrLen            varint
  data 段 / inst 段 / addr 段
```

首窗口 19 B 逐字节：`01 | 82 a3 80 00 | 00 | 0c | c0 80 00 | 00 | 00 | 05 | 00 | 73 c0 80 00 00`
= 源 COPY、srcSegLen 0x48C000、srcSegPos 0、deltaLen 12、目标窗口 0x100000、indicator 0、
data 0 B、inst 5 B、addr 0 B，指令段就是 `73 c0 80 00 00`（一个 COPY 指令 + 长度/参数）。

varint：MSB-first，最高位=1 表示继续（`v = (v << 7) | (b & 0x7f)`），与 VCDIFF 标准一致。

## 七、opcode 表（运行时填的，`.bss`）

| 表 | 地址 | stride | 256 项中非零 | 不同行 |
| --- | --- | --- | --- | --- |
| A（Ghidra `DAT_006143e8`） | `0x5143E8` | 6 B | 93 | 38 |
| B（Ghidra `DAT_006143f4`） | `0x5143F4` | 3 B | 62 | 20 |

抽样（左列 opcode）：表 A `0x00→02 00 00 00 00 00`、`0x04→01 00 00 00 00 00`、
`0x08→01 00 00 00 01 00`、`0x0c→01 00 00 00 02 00`；表 B `0x04→01 00 00`、
`0x0d→00 01 00`、`0x15→00 02 00`、`0x1d→00 03 00`。两张表每 4 个 opcode 出现一次递增，
形状与「COPY 长度分级 × 地址模式」一致；全量 256 项见 `work/rsb_vectors/opcode_tables.json`。
表在 `.bss` 里，**必须**先跑一次解码触发全局构造，再读才是满的。

## 八、no-op 与错误路径

```
python tools/emulate_rsb.py stream --delta-hex "d6c3c45300"
status=1 bytes=0 md5=d41d8cd98f00b204e9800998ecf8427e
```

只有 5 B 流头、没有窗口的 delta 是合法的空补丁（status=1、输出 0 B）。把 magic 改成
`d6 c3 c5 53 00` 则 status 的最低位为 0（库拒绝），可用于 `tools/rsbpatch.py` 的负例。

## 九、未决与限制

1. **packages 流没解**：第二个流（0x1978B）需要更完整的源数据；本工具只用 460.1 的头部
   0x48C000 B（info 流也恰好只引用这段），解 packages 流会读越界，属于未验证范围。
2. **`decode_record`/`decode_windows` 直调 `WINDOW_ENTRY` 仍失败**：库在单窗口入口期望一个
   已构造的 writer 对象（`param_3`/`param_4` 语义与流驱动不同），传 0 会直接返回失败。
   正式向量一律走「流驱动 + 调用点 hook」，即 `Emulator.trace_stream()`。
3. **只验证了头部区**：oracle 的 MD5 覆盖 0x48C000 B；再往后的包体解不解得出来，本次没有证据。
4. **没有碰原件**：`.so`、两个补丁、OBB 全程只读；`work/rsb_vectors/internal` 之外不写任何二进制。

## 十、复现命令

```
py tools/emulate_rsb.py container --patch work/versions/_incoming/460.1_460.2.rsbpatch
py tools/emulate_rsb.py info --patch work/versions/_incoming/460.1_460.2.rsbpatch --windows
py tools/emulate_rsb.py info --patch work/versions/_incoming/460.1_460.2.rsbpatch --out work/rsb_vectors/info_decoded_full.bin
py tools/emulate_rsb.py stream --delta-hex "d6c3c45300"
py tools/emulate_rsb.py vectors --patch work/versions/_incoming/460.1_460.2.rsbpatch --outdir work/rsb_vectors
py -m unittest tools.tests.test_emulate_rsb -v
```

`tools/rsbpatch.py` 可以照抄的三件事：容器头字段（第三节）、窗口记录布局与 varint 方向
（第六节）、opcode 表结构与地址（第七节）；判据用第五节那条 MD5。
