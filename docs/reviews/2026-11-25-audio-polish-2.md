# 2026-11-25 音频打磨 2：线性插值、16 voice 抢占、独立音乐/音效音量（P2-15 / T70）

承 T49（`docs/reviews/2026-11-24-audio-polish.md`）：那一轮把音频推到「能出声、能控音量」，
这一轮补三处采样质量与混音策略上的欠账——**最近邻重采样**、**8 voice 上限**、**只有一条 master**。
catalog、解码器、事件表、BGM 选择规则一律未改，所以 `--audio-audit` 的读数必须与本轮之前逐字相同，
这一点在 §5.1 用实际输出核对。

## 1. 结论

| 项 | 改前 | 改后 | 证据 |
| --- | --- | --- | --- |
| 重采样 | 最近邻（`static_cast<size_t>(position)` 取整） | 相位 + 线性插值（`a + (b-a)*frac`） | §2、`interpolation:` 行 |
| 44.1k → 48k | 每 147 个样本重复/丢一个，弦乐有金属边 | 首帧相位 0.91875 精确取样 | §2.2 |
| sfx voice 上限 | 8 | 16 | `voices: kMaxVoices=16` |
| 满了怎么淘汰 | `gain` 最小的（哪个音最轻就砍哪个） | `(priority, 起始序)`：先砍优先级最低，同优先级砍最早开始的 | §3 |
| 音量总线 | master 一条 | master × (music / sfx 两条 trim)，缺省 trim = 100 继承 master | §4 |
| CLI | `--volume`、`--mute-bgm`、`--mute-sfx` | 追加 `--music-volume`、`--sfx-volume` | §4.2 |

设计上的取舍只有一句要说清：**music 在 slot 0，永不参与抢占**。BGM 被一个 400 发的弹幕挤掉
比丢一个音效难听得太多，而且音乐是唯一会被交叉淡入管理的声部（§5.4 的 0.75 s 淡入淡出在 T49 已就位），
让它参与淘汰会让淡出状态和抢占状态互相打架。

## 2. 线性插值

### 2.1 实现

`native/src/audio/audio_mixer.cpp` 的 `AudioMixer::sampleAt`：

```cpp
const std::size_t next = index + 1 < total ? index + 1 : (wrap ? 0 : index);
const float a = clip.samples[index * stride + lane];
const float b = clip.samples[next * stride + lane];
return a + (b - a) * frac;
```

三点约定：

- **循环轨道**的最后一帧邻居是第 0 帧（`wrap=true`），这是 loop 无缝所必需的；
- **一次性音效**（`wrap=false`）最后一帧之后保持自身（`next = index`），否则尾音会混进起音变成 click；
- 位置换算仍是 `ratio = clip.sampleRate / 48000`，混音输出固定 48 kHz 立体声，所以 44.1k、48k、
  16k、22.05k、24k、32k 全部走同一支路径——`--audio-audit` 里 65 个文件的采样率覆盖面就是它的输入面。

### 2.2 正确性（手算期望值，±1e-6）

`native/tests/audio_test.cpp::testInterpolation`，期望值写在测试里而不是从实现里抄：

| 输入 | 频点 | 期望 | 说明 |
| --- | --- | --- | --- |
| 24 kHz `{0, 1}` | 相位 0.5 | `0.500000` | 直接调 `sampleAt` |
| 24 kHz 作 music 播 5 帧 | 0…2 相位 | `{0, 0.5, 1, 0.5, 0}` | 第 4 帧 `position 2.0 → fmod → 0`，测到 loop 回绕 |
| 44.1 kHz `{0, 1}` | 相位 0.91875 | `0.918750` | 最近邻会给 `0.0`，这是最刺眼的一档 |
| 48 kHz `{0.25, -0.5}` | 直通 | `0.25`, `-0.5` | ratio 1 不许引入插值误差 |

实际输出：

```
interpolation: 24k -> {0, 0.5, 1, 0.5, 0}, 44.1k phase 0.91875 -> 0.918750, 48k passthrough exact
```

## 3. 16 voice 与抢占规则

规则写在 `native/src/audio/audio_mixer.cpp:69-79` 的注释里，实现是同一段线性扫描：

```cpp
// Pool full: evict the lowest priority, and among equal priorities the earliest start. That
// keeps a wave horn over a pellet and a fresh pellet over the one fired 3 ms earlier.
if (candidate.priority < victim.priority ||
    (candidate.priority == victim.priority && candidate.started < victim.started)) slot = i;
```

- `playSfx(clip, gain, priority = 0)` 新增 `priority` 形参；`started` 是进程内单调递增的起播序号，
  同优先级时它就是「谁更早」，不依赖浮点计时器；
- 调用方目前一律用缺省 `priority = 0`（`audio_runtime.cpp` 未传），也就是**现阶段等价于「最早开始的先被砍」**；
  预留的优先级位给后面「波次号角 > 弹幕」这类分层，报告里点名，不假装已经接上；
- `activeSfxNames()` 是给测试用的观测口（按 slot 顺序点名），生产路径不读它。

三阶段断言（`testVoiceStealing`）：

1. **15 个 priority 5 + 1 个 priority 1** 填满 16，再来一个 priority 9 → 被砍的是 priority 1，
   `activeSfx() == kMaxVoices` 不变；
2. **16 个 priority 5**（`shot0…shot15`）再来一个 → 被砍的是 `shot0`（最早），`shot15` 与新来的都在；
3. **music + 16 个 fx** 再来一个 → `musicName()` 仍是 `theme`。

```
voices: kMaxVoices=16, steal order (lowest priority, then earliest start), music never stolen
```

## 4. 三条总线

### 4.1 关系

```
out = clamp( master × bus × voice.gain × crossfade envelope )
bus = music : sfx          （各有自己的 trim 与自己的 mute）
master  = --volume        （0..100，0 就是全静音）
trim    = --music-volume / --sfx-volume （0..100，缺省 100 = 继承 master）
```

「一个 master + 两条 trim」而不是「三个平级 master」的理由：`--mute-bgm`/`--mute-sfx` 已经是布尔闸门，
再叠一个平级数字会产生「master 调 0 而 music 仍出声」这种自相矛盾的状态；trim 的语义是
**在 master 之下再压某一条**，缺省 100 时行为与 T49 完全一致（旧测试与旧截图哈希因此不受影响）。

`AudioOptions` 里两条 trim 的缺省值是 **`-1`（未给）**，`pushOptions()` 见到 `-1` 才回落到 100；
这样「没写 `--sfx-volume`」和「写了 `--sfx-volume 100`」在解析层可区分，报告与测试都能断言继承语义。

### 4.2 CLI

```
--volume <0..100>        master volume (0 is silent, default 100)
--music-volume <0..100>  trim the music bus (default: inherit the master)
--sfx-volume <0..100>    trim the effect bus (default: inherit the master)
--mute-bgm / --mute-sfx  silence one bus
```

错误串沿用 T49 的模板，只是换了旗标名，实测：

```
$ PvZ2SHUTTLE.exe --menu content --music-volume 101
error: --music-volume must be between 0 and 100, got 101          (exit 1)
```

## 5. 回归

### 5.1 `--audio-audit` 改前 / 改后

本轮不碰 catalog、解码器与事件表，所以两个读数必须一致（改前取自 T49 收尾的 pol-desk8）：

| | 读数 |
| --- | --- |
| 改前（T49） | `{"bgm":26,"decoded":65,"deviceAvailable":true,"missing":[],"seconds":4487.955,"sfx":18,"sounds":65}` |
| 改后（audit 构建，`deviceAvailable:false`） | `{"bgm":26,"decoded":65,"deviceAvailable":false,"missing":[],"seconds":4487.955,"sfx":18,"sounds":65}` exit 0 |

`seconds` 到毫秒都没动，说明混音器改造没有波及解码路径。

### 5.2 设备侧 peak（`audio_runtime_device_test`）

真设备跑（`C:\pvzbuild\pol-desk12\Release\audio_runtime_device_test.exe`）：

```
device: live (SDL3 push-mode device (48 kHz float stereo))
music: frontyard_loop (starts 1)
events: seen 9 mapped 4 unmapped 1 deduped 4
pump: 145 calls, 146432 mixed frames, 4 sfx calls
peak: volume 100 = 0.051850 (11776 frames), volume 0 = 0.000000 (23040 frames)
audio runtime device test passed
```

（同一二进制在 `C:\pvzbuild\pol-desk11` 上另跑过一次，阶段计时为
`catalog 1080 ms / audio catalog 1085 ms / backend 1204 ms / music 2062 ms / battle 5560 ms`，
peak 同样是 `0.051850 → 0.000000`，帧数 `11264 / 23040`。）

`peak:` 那行是 T49 加的测量：把同一段 BGM 在 `--volume 100` 与 `--volume 0` 下各混 240 ms，
`0.051850 → 0.000000`。两次窗口里真正新混进去的帧数分别是 11776 与 23040（都 `> 0` 才说明不是读到旧值），
所以 0 是真乘进去的 0，不是「这一轮没混东西」。

### 5.3 headless 截图逐字节

`C:\pvzbuild\pol-desk12\Release\PvZ2SHUTTLE.exe`（`pol-desk11` 的同名产物给出完全相同的两个哈希）：

| 命令 | 输出 | SHA-256 |
| --- | --- | --- |
| `--battle-snapshot content <assets> C:\pvzbuild\baseline\battle_p2.bmp` | `battle_preview=ok` | `D56A3D6AA176CA8F55B7A8F3589272249028C7D101AFA03C1BBEC38123479A90` |
| `--menu content --assets <assets> --snapshot C:\pvzbuild\baseline\menu_p2.png --frames 2` | `{"choice":"worldmap"}` | `37F75744CC8472660B34998718F4339BEA9D38F7FDB39870635B13E3087AB7B1` |
| 同上，加 `--audio-off --volume 0 --music-volume 0 --sfx-volume 0` | `battle_preview=ok` | `D56A3D6AA176CA8F55B7A8F3589272249028C7D101AFA03C1BBEC38123479A90` |

两个哈希与 T45/T49 记录的基线逐字符相同；三条命令的 stdout 里没有任何音频设备行，
说明 `--battle-snapshot` / `--frames` 的 headless 自动静音仍然生效（截图不开设备）。

### 5.4 性能：`frontyard_loop` 解码

本轮没有改解码器（`audio_decode.cpp` 的最后一次编辑在 T49 的 O(n²) 修复），`--audio-audit` 的
`seconds` 到毫秒都没变（§5.1），所以「不退化」有两层证据：

- **结构上**：插值发生在 `AudioMixer::sampleAt`，逐输出帧、在混音线程的 `pump()` 里；解码是
  `stb_vorbis_get_frame_float` 一次性展开到 `AudioClip::samples`，两条路径不同 TU、不同调用点。
- **实测**：`audio_test` 里新增一条只计时不断言的测量（`testOgg` 末尾，带 5 s 兜底断言）：

  ```
  decode: frontyard_loop 6708608 frames in 957 ms
  ```

  同一台机器上 T45 记录的是 `phase: music 2660 ms`（当时刚修完 O(n²)，`frontyard_loop` 从
  `83234 ms` 降到 `2660 ms`）；本轮 `phase: music - phase: backend` 三次独立运行为
  `858 / 798 / 471 ms`，机器负载不同，故取量级而不是绝对值：**同一数量级、没有回到 O(n²)**。

## 6. 测试与构建

三个新用例（不新建测试文件，全部加在 `native/tests/audio_test.cpp` 里，`wmain` 注册顺序
`testMixer → testInterpolation → testVoiceStealing → testBusVolumes → testVolume → …`）：

| 用例 | 断言 |
| --- | --- |
| `testInterpolation` | 24k 相位 0.5、24k 播 5 帧的三角波形、44.1k 相位 0.91875、48k 直通（全部 ±1e-6） |
| `testVoiceStealing` | 三阶段：最低优先级被砍 / 同优先级最早被砍 / music 永不被砍 |
| `testBusVolumes` | sfx 50% 减半且 music trim 不影响它；music 50% 减半且 sfx trim 不影响它 |

`testAudioOptions` 同时扩了 `--music-volume`/`--sfx-volume`：两种写法、缺省 `-1`（继承）、
非法值与缺值原文、`applyAudioOptions` 之后 `attachAudio` 的 `musicVolume() == 40` 与
`sfxVolume() == 100`（未给的继承 master）。

两套全新 `-BuildDir` 构建（都用 `tools/build_native.ps1`，未复用旧目录）：

| 配置 | 命令 | 结果 |
| --- | --- | --- |
| audit（无 SDL） | `-AuditOnly -BuildDir C:\pvzbuild\pol9` | `100% tests passed, 0 tests failed out of 29`，`Total Test time (real) = 82.12 sec`；`audio` 16.61 s、`audio_runtime` 1.33 s、`cli_audio_audit` 18.08 s |
| desktop | `-BuildDir C:\pvzbuild\pol-desk12` | `100% tests passed, 0 tests failed out of 38`，`Total Test time (real) = 50.90 sec`；`audio` 8.05 s、`audio_runtime` 0.84 s、`audio_device` 5.08 s、`cli_audio_audit` 7.09 s |

中途两次红都与音频无关，按时间顺序记录以免误读：`C:\pvzbuild\pol8`（audit）只有
`shop` 红（`shop test failed: 4 implemented coin-priced rows are refused for an undeliverable payload, got 15`）；
`C:\pvzbuild\pol-desk11`（desktop）只有 `mechanics` 红
（`mechanics test failed: carnival_86's grid row must report the kind it used`）。两者都是队友在改
关卡机制/商店时留下的中间态，下一次全新构建（pol9 / pol-desk12）即全绿。`pol-desk10` 甚至没能配置：
`native/CMakeLists.txt` 在 18:03–18:11 被改到 `CMake Error at CMakeLists.txt:423 (elseif): Flow control
statements are not properly nested`（缺一个 `endif()`），队友补齐后恢复正常——这条也说明为什么本轮所有
结论都来自最后的全新构建，而不是更早的目录。

## 7. 反向探针原文

两条探针都是先在源码里把行为改坏、全新 `-BuildDir` 构建、跑 `audio_test` 取原文，再恢复。
恢复后的 `audio_mixer.cpp` 两份探针都没有残留（`grep PROBE` 无命中）。

### 7.1 插值退回最近邻

`sampleAt` 的 `return a + (b - a) * frac;` 改成 `return a;`：

```
audio test failed: sampleAt at phase 0.5 must interpolate to 0.5, got 0.000000
audio_test exit=1
```

（构建目录 `C:\pvzbuild\probe-near`。）

### 7.2 抢占顺序反过来

淘汰条件两个比较符反向（砍最高优先级、同优先级砍最晚开始）：

```
audio test failed: the lowest-priority voice must be the one stolen when the pool is full
interpolation: 24k -> {0, 0.5, 1, 0.5, 0}, 44.1k phase 0.91875 -> 0.918750, 48k passthrough exact
audio_test exit=1
```

（构建目录 `C:\pvzbuild\probe-steal2`。插值断言先过、抢占断言后红，正好说明两条探针各自独立。）

## 8. 已知限制

1. **优先级分层还没接**：`playSfx` 有了 `priority` 形参，但 `AudioRuntime` 一律用缺省 0，
   所以运行时行为等价于「最早的先被砍」。接分层需要事件表带权重（波次号角 > 命中 > 弹幕），
   那是下一个任务的事，本轮不假装做了。
2. **插值没有做抗混叠滤波**：44.1k → 48k 是升采样，线性插值足够；真正的降采样（例如 96k 源）会需要
   低通，当前资产里没有超过 48k 的文件，所以有意不做。
3. **`--music-volume`/`--sfx-volume` 没有滑杆 UI**：任务只要求 CLI 开关，菜单里的滑杆需要
   `menu_view` 的选项结构与键盘路由（不在本轮写作用域）。
4. `audio_runtime_device_test` 在没有音频设备时会打印 `SKIP ... no audio device` 并返回 77，
   CMake 用 `SKIP_RETURN_CODE 77` 认它——这条是 T45 就有的约定，本轮未改。
