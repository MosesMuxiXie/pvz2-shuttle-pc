# 460.9 rebase 全链条审计（只读）

审计时间 2026-11-25 14:39–15:05（Asia/Shanghai）。只读：未改任何源码/产物，未 commit（git HEAD `24a2493`）。
所有结论下面都贴了命令与原始输出；凡拿不到证据的都记在 §9「未覆盖」。

## 0. 结论

**数据结论成立**：`work/obb_packages`（460.9）相对 `work/obb_packages_460_1`（460.1）**只差 6 个包**，
包集合（2116）不变、零增零删；`PACKAGES` 组在 subgroup 表里的位置 **684 → 687**（因为前面插进了 3 个新组）；
`EffectElementReactionGroup_1536/_768/_Common` **确为新增**，三者解码后合计 **880,640 B**。
两跳补丁的源头哈希链路我独立复算过，与 manifest 的 MD5 逐字相同（460.1/460.2/460.9 三个 OBB 现场重算）。

**但链条的可重放性有硬伤**：生产用的 patcher **不在仓库里**
（`D:\OneDrive\文档\pvz_shuttle\tools\rsbpatch.py`，809 行），仓库 `tools/` 下没有它、也没有它的测试；
`docs/COMPLETENESS.md:729` 与 `docs/PARITY_BASELINE.md:402` 却写「`tools/rsbpatch.py` … 32 例测试」。
**一次干净的 clone 无法重建 460.9**，只能手工去仓库外找脚本。

**解码器有一处会「解出垃圾但不报错」的真实缺陷**（H1）：`_copy` 在第二个及之后的窗口里做自引用拷贝时
漏加窗口基址 `out0`。我用两条合成窗口复现成功（输出长度正确、内容错位、不抛异常）。
两份官方补丁的所有流（2 条 info + 6 条报文）**都未触发**该分支（自引用调用计数 0），所以**当前数据没被它污染**；
但补丁格式一旦出现这种窗口，产物会静默错位，只有外部 `--md5` 能兜住。

verdict：**数据 pass，工具 needs_revision**（H1 潜伏缺陷 + H2 出库脚本 + M1 链条不自校验）。

## 1. 审计对象与快照

| 对象 | 位置 | 大小 | sha256/12 | mtime |
| --- | --- | --- | --- | --- |
| patcher（**不在仓库**） | `D:\OneDrive\文档\pvz_shuttle\tools\rsbpatch.py` | 30,686 B / 809 行 | `DA35FBF0FC86129F2F4B9C9948AC0E27…` | 11-24 20:44 |
| oracle | `tools/emulate_rsb.py` | 29,779 B | `98CEE0BF2CD7` | — |
| 差量工具 | `tools/contentc/rebase_diff.py` | 6,546 B / 175 行 | `6F27501D0941` | — |
| 基础包 | `work/versions/460.1.obb` | 2,095,579,136 B | md5 `be21c6f0fe29ff243aaeaad2ca551833` | — |
| 中间包 | `work/versions/460.2.obb` | 2,095,579,136 B | md5 `7a219bb7fbfd54b4176aa33e48704b48` | — |
| 目标包 | `work/versions/460.9.obb` | 2,096,463,872 B | md5 `2963d0781e4715522cb12bc2d3bb9f8e` | — |
| 补丁 1 | `work/versions/_incoming/460.1_460.2.rsbpatch` | 2,686,247 B | target 2,095,579,136 / info 163 B / count 4310 | — |
| 补丁 2 | `work/versions/_incoming/460.2_460.9.rsbpatch` | 9,767,076 B | target 2,096,463,872 / info 427,125 B / count 4313 | — |
| 数据树 A | `work/obb_packages_460_1` | 2116 包 + `_index.json` | — | — |
| 数据树 B | `work/obb_packages`（=460.9） | 2116 包 + `_index.json` | — | — |

```
460.1.obb md5=be21c6f0fe29ff243aaeaad2ca551833 bytes=2095579136 secs=40.8
460.2.obb md5=7a219bb7fbfd54b4176aa33e48704b48 bytes=2095579136 secs=52.8
460.9.obb md5=2963d0781e4715522cb12bc2d3bb9f8e bytes=2096463872 secs=51.2
```
（`Get-FileHash -Algorithm MD5`，逐字等于 `docs/COMPLETENESS.md:717/726/727` 的三个值。）

## 2. 判据 1：patcher 的三类校验是否真做

### 2.1 `@24` 源 info-section MD5 —— 真做，且方向正确

- 代码：`read_rsb_header`（`rsbpatch.py:411-422`）先校验源文件 magic `1bsr` + version 4，返回
  `hdr[H_HEADER_SIZE]` 作为 info-section 字节数；`apply_patch` 在 `:561-566` 用它
  `_md5_file_range(sf, 0, info_size)` 与补丁头 `@24` 比对，**不匹配直接抛**
  `info-section 哈希不匹配：源 …，补丁要求 …`。
- 关键点：**用的是源 OBB 自己头里的 info 长度**，不是补丁的 `@20`（info 流长度）——我实测两者相差三个数量级
  （4,767,744 vs 163），用错就会永远失败。
- 独立复算：

```
md5(460.2.obb[:4,767,744]) = 5f938695079f4a2812e0770ac261e066
patch2 @24                 = 5f938695079f4a2812e0770ac261e066   ← 相等
460.1.obb @12 info_size = 4,767,744 (0x48C000)   460.9.obb @12 = 4,771,840 (0x48D000)
```
- 逐报文 `beforeHash` 也真做（`:624-630`），新建 subgroup 要求 `EMPTY_MD5`（`:618-621`）。
  我把补丁 2 的 4313 条报文全部过了一遍：`type=0`（无 payload）的记录逐条比对
  `md5(源 subgroup) == beforeHash`，**anomalies: none**。

### 2.2 `@12` 目标长度 —— 真做，而且是三层

1. 窗口级：`_decode_window` 收尾 `if len(out) - out0 != tgt_len: raise`（`:355-356`），越界/欠量都抛；
2. 装配级：每条报文 `if total != new_rec["offset"]: raise`（`:655-658`），注释明说「不重算 offset，解码错了必须报错」；
3. 全量级：`:661-664` `total != hdr["target_size"]` 抛。

我的独立复算解释了「为什么总量差一个 info 长度」：subgroup 累加 2,090,811,392（补丁1）/
2,091,692,032（补丁2），与 target 的差额分别 **恰为 4,767,744 / 4,771,840**（= info-section 长度），
而 `apply_patch:603-604` 先把 `new_info` 写进产物再累加，所以它的 `total` 与 target 相等。**不是缺陷。**

### 2.3 失败是否删 `.part` —— 真做；但 chain 会留 2 GB 中间产物

- `_temp_product`（`:534-547`）任何异常都 `os.unlink(path)`；`_replace_with_retry`（`:521-531`）在 40×0.5 s
  退让后仍失败才抛，抛前也 unlink（`:665-670`）。
- **H/M 级问题**：`_cmd_chain`（`:705-721`）每一跳写 `.rsbchain-<n>.obb`，**只在成功后** `os.unlink(cur)`；
  中途任一跳失败（或进程被杀），上一跳那份 ~2 GB 中间产物会留在产物目录里，且没有任何日志提示它的存在。

### 2.4 「解出垃圾但不报错」的路径 —— **存在（H1）**

`_copy`（`:365-382`）：

```python
373:    if addr >= base and addr + size <= len(out):
374:        s = addr - base
375:        out += out[s:s + size]          # 纯自引用且已物化 -> 切片即可
...
381:            out.append(out[p - base])
```

`addr` 是**本窗口**虚拟地址（`base = src_seg_len`），而 `out` 是**整条流累计**的缓冲；切片起点少了窗口基址 `out0`。
第一个窗口 `out0 == 0` 时正确，**第二个及之后的窗口一旦 COPY 自己刚产出的区段（`addr >= base`），就会从整份
输出开头取字节** —— 长度仍然对得上，`:355-356` 与 `:649-652` 都不会报错。

合成复现（`build/t74probe/vcd.py`，直接调 `vcdiff_decode`）：

```
stream = hdr(d6c3c4 00 00) + win1(ADD "AAAA", tgt 4) + win2(ADD "ABCD", COPY mode0 size4 addr0, tgt 8)
two-window decode -> AAAAABCDAAAA len 12 | 期望 AAAA + ABCDABCD
VERDICT: BUG reproduced (garbage accepted)
control (out0==0) -> b'ABCDABCD'      ← 只把第一个窗口改成空窗口，同样的第二窗口就正确
```

**可达性（重要）**：我给 `_copy` 装了探针，把两份补丁的全部流都解了一遍：

```
460.1->460.2 info stream: decoded 4,767,744 B md5 5f938695…  windows=4   selfref-after-win0=0
460.2->460.9 info stream: decoded 4,771,840 B md5 1f0dff08…  windows=48  selfref-after-win0=0
带 payload 的报文：补丁1 = 1 条（#684 PACKAGES，8 窗口）；补丁2 = 5 条（#378/#379/#380、#687 PACKAGES 9 窗口、
#4168 __MANIFESTGROUP__ 7 窗口），selfref-after-win0 全为 0
```
即**两份官方补丁都不会触发该分支**，现有 460.9 数据没被它污染。但它是真实缺陷：解码器遇到这种流会静默错位，
而唯一的兜底是外部传入的 `expected_md5`（`:686-688`）——链条默认不传（见 M1）。

次要：单流模式（`data_len==0 and addr_len==0`，`:257`）在收尾时**不校验 `j == inst_at+inst_len`**
（尾部指令字节被忽略）；非单流模式有精确消费校验（`:357-361`）。这是「宽容」而非「错」，记 M4。

## 3. 判据 2：oracle 是否自我实现

- `tools/emulate_rsb.py:59-66`：`REPO = parents[1]`、`WORK = REPO.parent.parent/"work"`、
  **`DEFAULT_SOURCE = WORK/"versions"/"460.1.obb"`**、`DEFAULT_SO = WORK/"versions"/"_incoming"/"libczProject_official.so"`；
  `--source` 默认同值（`:573/583/598`）。**锚在 460.1，不是根目录的 460.9 ⇒ 不会自我实现。**
- `5f938695…` 的实测来源（我直接算，不经过 oracle）：

```
md5(460.2.obb[0:4,767,744]) = 5f938695079f4a2812e0770ac261e066
  · = 补丁 2 的 @24（源 info MD5）
  · = 补丁 1 的 info 流解码产物（4,767,744 B）  ← 两步互为见证
```
即 `docs/reviews/2026-11-25-rsb-emulation.md:9/64/102` 的三处数字**都对**，而且它同时说明
「补丁 1 的输出 = 补丁 2 声明的输入」，链条自洽。

## 4. 判据 3：`tools/contentc/rebase_diff.py` 的三项行为

| 实验 | 命令 | 结果 |
| --- | --- | --- |
| 同树对同树 | `--old A --new A`（3 个真实包的副本） | `added 0, removed 0, changed 0` ✅ |
| 自造改动 | 改第一个包的 `.#comment` | `changed 1`，路径 `.#comment: 'Allowed Universal Links' -> 'AUDITED-…'` ✅ |
| 只改 dict 键序/缩进 | 同一内容重新 `json.dumps(indent=2, sort_keys=False)` | `changed 0` ✅（`canonical()` 走 `sort_keys`+紧凑分隔符，`:35-36`） |
| 只翻转 `objects` 数组顺序 | 同内容反向排列 | `changed 1`，**41 条 path**（`.objects[0].aliases[0]` 等） |

判定：
- 键序、缩进、空白**不会**误报 ✅；列表**顺序**会报 — 这是对的：RSB 包里 `objects[]` 的下标就是
  `aliases` 的引用基准，重排是语义变更。
- **M6**：`--limit` 默认 40（`:93`），`walk_diff` 到 40 条就 `return`（`:64-65`），**报告里没有任何
  「已截断」标记**；上面那条实际 41 条差异，人只会看到 40 与 5 行样例（`:163-166`）。审计者容易误当完整。
- 次要：`--grep` 只过滤 `changed` 循环（`:111-113`），`added`/`removed` 照旧全列（口径不一致，L 级）。

## 5. 判据 4：差量结论复算

`python tools/contentc/rebase_diff.py --old work/obb_packages_460_1 --new work/obb_packages --json …`：

```
packages {'common': 2116, 'new': 2116, 'old': 2116} added 0 removed 0 changedCount 6
changed: pkg_0231_LawnStringsData.json, pkg_0232_LawnStringsData.json,
         pkg_0234_DisableSkipLevelModuleProperties.json, pkg_0415_LevelDefinition.json,
         pkg_0416_LevelDefinition.json, pkg_2101_ThymedEventSchedule.json
index: {'okOld': 2116, 'okNew': 2116, 'failOld': 0, 'failNew': 0, 'identical': False}
```

逐包差异（我自己写的独立比对，不是该工具的输出）：

| 包 | 实测差异 |
| --- | --- |
| `pkg_0231`（英文串） | `LocStringValues.len` 38112 → 38114（+2 项 = 键 `ELEMENT_7_WAVEMASSAGE` + 值） |
| `pkg_0232`（中文串） | 38106 → 38108，值 `亡魂的怨念令你们震颤！` |
| `pkg_0234` | `objects.len` 495 → 496（新增 `RlConfig`） |
| `pkg_0415` | `objects[38].WaveStartMessage`：`亡魂的怨念令你们震颤！` → `[ELEMENT_7_WAVEMASSAGE]`（键化） |
| `pkg_0416` | `objects[8].SuppressFlagZombie`：`<missing>` → `<added>` |
| `pkg_2101` | `objects[0].Events.len` 27 → 30 |

**`PACKAGES` #684 → #687 与三条新组**（subgroup 级，不是包级）：我把两条补丁的 payload 全解了：

```
460.2->460.9 descriptors with payload: 5
  #378 EffectElementReactionGroup_1536  payload 647,192 → 647,168 B (1 窗口)
  #379 EffectElementReactionGroup_768   payload 217,112 → 217,088 B (1 窗口)
  #380 EffectElementReactionGroup_Common payload 16,408 → 16,384 B (1 窗口)
  #687 PACKAGES                         payload 1,341,981 → 2,342,912 B (9 窗口)
  #4168 __MANIFESTGROUP__               payload 6,461,634 → 6,561,792 B (7 窗口)
```
- 三条 `EffectElementReactionGroup_*` 在 460.2 里**不存在**（`old_by_name` 查不到，按空源解出）→ 确为新增；
  合计 647,168+217,088+16,384 = **880,640 B**，与 `COMPLETENESS.md:747` 一致。
- 三条插在索引 378/379/380，其后整表后移 3 位 ⇒ `PACKAGES` 由 684 变 687、记录数 4310 → 4313。
- 补丁 1 只有 1 条 payload（`#684 PACKAGES`），与「460.1→460.2 只动了 PACKAGES 组」吻合。

## 6. 判据 5：产物一致性（`native/generated/*.json`）

`counts.filesScanned` / `sources.files` 的实测值（口径 = 2116 个 `pkg_*.json` + `_index.json`）：

| 产物 | 字段 | 值 | mtime |
| --- | --- | --- | --- |
| `armors_from_pack.json` | `counts.filesScanned` | 2117 | 11-20 22:56 |
| `rewards_from_pack.json` | `counts.filesScanned` | 2117 | 11-25 14:36 |
| `projectiles_from_pack.json` | `counts.filesScanned` | **2116**（不含 `_index.json`） | 11-25 14:27 |
| `bosses_from_pack.json` | `sources.files` | 2117 | 11-25 14:27 |
| `s5_data_gaps.json` | `sources.files` / `sources.packages` | 2117 / 2116 | 11-20 22:18 |

**没有一个是「460.1 期独有」的数字**：两棵树都是 2116 包/2117 文件（零增零删），所以这些计数本来就不区分版本；
差异只在 2116 vs 2117 的**口径**（是否含 `_index.json`），且各自在自己文件里有 `sources` 说明。

正面证据：`work/versions/_delta_checks.txt`（11-24 20:51）记录了 19 个 compiler 在 460.9 树上的 `--check`：
全部 `exit 0`，末行 `not green under 460.9: none`。我现场复跑了其中三个：

```
python tools/contentc/rails.py --check      → 产物已是最新：levels=1809 rail=204 …        exit 0
python tools/contentc/armors.py --check     → armors=102 zombies=1127 … OK                exit 0
python tools/contentc/plantfood.py --check  → 产物最新：rows=293 …                        exit 0
```

**L1（providence 混淆）**：11-20/11-21 生成的产物把源写成 `…\work\obb_packages`，而这个目录在 11-24 20:50
被换成了 460.9 树。文件里没有任何版本戳，于是「这份数据是 460.1 还是 460.9 算的」今天无法从产物自身判断。
实测这些产物在 460.9 树上 `--check` 仍全绿（上面 + `_delta_checks.txt`），所以**当前没有实际陈旧**；
但下次若 6 个变化包里再动到被消费的字段，这类产物会静默过期，建议把 `obb` 版本（或 `_index.json` 的 sha）写进 `sources`。

## 7. 判据 6：文档数字抽查（§2.32 / §2.33 / PROGRESS）

| # | 文档位置 | 声称 | 实测 | 判定 |
| --- | --- | --- | --- | --- |
| 1 | `COMPLETENESS.md:717` | 460.1 MD5 `be21c6f0…` | 重算 = `be21c6f0fe29ff243aaeaad2ca551833` | ✅ |
| 2 | `:726` / `:727` | 460.2 `7a219bb7…` / 460.9 `2963d078…` | 重算逐字相同 | ✅ |
| 3 | `:734` | 差量 6 包（两条 LawnStrings 各加 1 条 `ELEMENT_7_WAVEMASSAGE`、`RlConfig`、键化、`SuppressFlagZombie`、27→30） | 6 包；字符串是**扁平的键/值对**所以数组 +2 项；其余逐条对上 | ✅（L2 措辞） |
| 4 | `:747` | 三组元素反应美术合计 880,640 B | 647,168+217,088+16,384 = **880,640** | ✅ |
| 5 | `:750-751` | `patch_460_9.json` 154,618 B sha256 `90b4e3b2…`；`--check` → `rlConfig=1 levelFlags=271(true 215/false 56) thymeEvents=30(new 3) unknowns=0` | 154,618 B、sha256 `90b4e3b2c9fc884d7cd38c260b97e102823b1e51fc6cf61545c5a0d77cc57144`；`--check` 输出逐字相同，exit 0 | ✅ |
| 6 | `:772` | `level_modules.json` 键数 14 → 15（flagOnly 6 → 7） | 现场 `levelextra.py --check` → `keys=15 data=2 flagOnly=7` | ✅ |
| 7 | `:759-760` | 30 条，`UniqueID` 1..31 去 23；新增 29/30/31；445 个关卡引用 | Events=30、ids 缺 23、`newThymeUniqueIds [29,30,31]`、`thymeEventLevelRefs 445` | ✅ |
| 8 | `:739` | `world_gates.json`「必须重生成（新 sha256 `7d369ced…`）」 | 产物 `generated = sha256:b1f61cd5ef86dedb`；而 `sha256(pkg_2107_WorldData.json)` 前 16 位 = **b1f61cd5ef86dedb**；`pkg_2107` 不在 6 个变化包里 | ❌ **M5**：sha 未变，文档那个 `7d369ced…` 既不等于产物也不等于源 |
| 9 | `:729`、`PARITY_BASELINE.md:402` | 「`tools/rsbpatch.py`（`apply`/`chain`/`info`/`table`，**32 例测试**）」 | 仓库内**没有** `tools/rsbpatch.py`；`tools/tests/` 里也没有针对它的测试（只有 `test_emulate_rsb.py` 针对 oracle） | ❌ **H2** |
| 10 | `:803-807`（§2.33 交叉核对） | `ElementReactionModule` 在 `pkg_0234`+LevelDefinition；`GridItemIceHole`/`FireWall` 在 `pkg_0024/0025`；`RogueModule`/`SlotMachineModule`/`AciditySubsystem`/`VoidDragonNasaSubsystem`/`roguelike` 均 0 命中 | 现场全库 grep：`ElementReactionModule` 21 个包（含 `pkg_0234`、`pkg_0398/0399/0400`…）、`GridItemIceHole`/`GridItemFireWall` 各 2 个包（`pkg_0024`/`pkg_0025`）、其余 5 个名字 **0 命中** | ✅ |
| 11 | `PROGRESS.md:116` | 差量命令可复现 | 同命令跑出 `changed 6`，与文档一致 | ✅ |
| 12 | `:737` | `level_mechanics.json` 只有 `egypt_25` 的 `waveStartMessage` 变化 | 全表只有 `egypt_25` 含 `ELEMENT_7_WAVEMASSAGE` | ✅ |

## 8. 发现清单

**H1（high，潜伏，非当前数据）**：`rsbpatch.py:365-382` `_copy` 在窗口 `out0 > 0` 时用
`out[addr-base : …]` / `out[p-base]` 取字节，漏加 `out0`。合成两窗口流复现出「长度正确、内容错位、不抛异常」
（`AAAA+ABCDAAAA` vs 期望 `AAAA+ABCDABCD`）。两份官方补丁 selfref 计数 0，故 460.9 未被污染。
修法：`s = out0 + (addr - base)`、`out.append(out[out0 + p - base])`；并加一条两窗口单测（照我这个流即可）。

**H2（high，可重放性）**：生产 patcher 出库（`D:\…\pvz_shuttle\tools\rsbpatch.py`），仓库里没有副本、
没有测试；而 `COMPLETENESS.md:729` / `PARITY_BASELINE.md:402` 指向不存在的 `tools/rsbpatch.py` 并声称 32 例测试。
修法：把 patcher 移入 `tools/`（或加一份逐字副本 + 校验和），补最少 5 条单测（窗口解码、两窗口自引用、目标长度、
before_hash、链装配闭合），文档改成真实路径。

**M1（medium，链不自校验）**：`_cmd_chain:711` 只在调用方传 `--md5` 时才比对产物 MD5；下一跳的 `@24`
本来就在补丁头里，可以自动校验「第 n 跳产物的 info-section md5 == 第 n+1 跳的 @24」，现在没做。
所以「每一步都有 MD5 硬校验」（`COMPLETENESS.md:722`）在命令行默认执行下**只是部分成立**。

**M2（medium）**：`verify_patch:504-516` 只校验头 + info MD5 + 描述符，**不校验逐报文 beforeHash**，
名字比行为强；真正严格的是 `apply_patch`。建议改名或在输出里写明覆盖范围。

**M3（medium）**：`_cmd_chain:705-721` 失败/中断时遗留 `.rsbchain-<n>.obb`（每份 ~2 GB），无日志提示。

**M4（medium/low）**：单流模式收尾不校验指令流被精确消费（`:357-361` 只在非单流分支），尾部字节被静默忽略。

**M5（medium，文档）**：`COMPLETENESS.md:739` 的「新 sha256 `7d369ced…`」与实测不符：`pkg_2107_WorldData.json`
未变，其 sha256 前 16 位就是产物里的 `b1f61cd5ef86dedb`。

**M6（medium，工具）**：`rebase_diff.py` 的 `--limit`（默认 40）截断后无任何标记；实测 41 条差异只显示 40。

**L1**：生成物 `sources.obb` 只写路径不写版本，目录被换树后无法判断数据出自哪一版（见 §6）。
**L2**：`COMPLETENESS.md:734`「各加 1 条」实为扁平键/值数组 +2 项（语义没错，字面不符）。
**L3**：`walk_diff` 用 `type(a) is not type(b)`（`:66`），`1` 与 `1.0` 会被报成 changed（对 RTON 保真比对是对的，
但报告里没说明这一敏感性）。

## 9. 未覆盖

- **没有真跑整链**（会写 2×2 GB 到 OneDrive 同步盘）。替代证据：两条 info 流 + 6 条报文流全部逐条解码，
  长度/装配偏移/总量三层闭合都在我的脚本里独立复算过（§2.2、§5）。
- **链的产物 md5 是否被 `--md5` 校验过**：`work/versions/gate_*.log` 里没有 `md5=` 行，无法证明当时传了
  `--md5`；但三个 OBB 的 md5 与 manifest/文档逐字相同（§1），端点是对的。
- §2.33 的 `.so` 级数字（349 导出、导入 +30/−7、`.text +8.7%`、873 条新字符串）未复算——那属于
  `docs/reviews/2026-11-25-core-460.11.md` 的取证范围，我只核了对我们有口径影响的名字表（§7 #10）。
- oracle（`emulate_rsb.py`）没有执行（要 unicorn 仿真 .so）；我只核了它的锚点与 `5f938695…` 的独立可复算性。

## 10. 复现命令

```powershell
# 三个 OBB 的 md5（约 40–55 s/个）
pwsh -NoProfile -File build\t74probe\md5.ps1
# 补丁头 + OBB 头对照
python build\t74probe\hdr.py ; python build\t74probe\hdr2.py
# 两条 info 流 + 6 条报文流（长度/窗口/自引用计数/装配闭合）
python build\t74probe\streams2.py
# _copy 的 out0 缺陷复现（合成两窗口）
python build\t74probe\vcd.py
# rebase_diff 三实验 + 真实差量
python build\t74probe\diffdrv.py
# 产物/文档数字
python build\t74probe\gen.py ; python build\t74probe\paths.py ; python build\t74probe\cmp.py
python tools\contentc\newin4609.py --check
python tools\contentc\levelextra.py --check
python tools\contentc\rails.py --check ; python tools\contentc\armors.py --check
python build\t74probe\names.py ; python build\t74probe\thyme.py ; python build\t74probe\wg.py
```

（探针脚本全部在 `build/t74probe/`，只读源数据，不写仓库任何文件。）
