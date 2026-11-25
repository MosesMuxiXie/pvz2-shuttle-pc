# S2 审计缺陷修复台账（2026-11-20）

来源：`docs/reviews/2026-11-20-s2-audit.md`（auditor，19 条：1 blocker / 5 high / 7 medium / 6 low）。
本文件逐条记录处置：修了什么、怎么验、还没修的为什么没修。台账先于修复完成写好，状态随验证更新。

## Blocker

| 编号 | 问题 | 处置 | 状态 |
| --- | --- | --- | --- |
| B1 | `zombieJump` 把僵尸落到植物右侧（`x = centre + 1.05`），而推进向左，形成无限起跳；`tickZombies` 又排除 `jump` 的啃食 → 139 张含 `pole_vaulter` 的关卡结构上不可胜 | 落地改为 `centre - (kEatStartCols + 0.1)`（植物左侧），加 2 秒冷却；`tickZombies` 只排除 `fly`，跳跃后正常啃食 | 已修，待 `engine` 用例覆盖 |

## High

| 编号 | 问题 | 处置 | 状态 |
| --- | --- | --- | --- |
| H1 | `World::plant` 不校验 `level.deck`，脚本/界面能种任何植物 | 加 `not-in-deck`（`level_.deck` 非空时校验），保留 `too many plants` 上限 | 已修，待用例 |
| H2 | 判负挂在 `mower.state == 2`，推车行驶中越线不判负；`kMowerTriggerX` 无人使用 | 触发用 `kMowerTriggerX`，判负改为「越过 `kLoseX` 且推车已非 ready」，并计 `leaked_` | 已修，待用例 |
| H3 | `zombieSummon` 在 `tickZombies` 的 range-for 中 `push_back` → 迭代器失效 | 改成 `pendingSpawns_` 队列 + 循环结束后 flush；`inZombieLoop_` 期间 `spawnZombie` 只入队 | 已修 |
| H4 | `tools/check_all.ps1` 在生成器跑完之后才读基线，门禁自愈（hash 全变仍报 IDENTICAL） | 三个基线（冒烟、矩阵、世界差异）一律在生成器**之前**读取，比较结果单独存变量再覆盖 | 已修 |
| H5 | `shot.slow` 是秒却当 tick 加，3 秒减速实际 50 ms | 改为 `tick + slow / kStepSeconds` | 已修 |

## Medium

| 编号 | 问题 | 处置 | 状态 |
| --- | --- | --- | --- |
| M1 | `advance()` 无 NaN/Inf 校验（永久冻结）；guard 满时静默丢时间 | 非有限或越界即抛 `invalid_argument`；guard 满发 `time_budget_exceeded` 并清累加器 | 已修 |
| M2 | `kVictoryFlushSeconds` 恒不成立（死代码）；`kZombieDeathFadeSeconds` 无使用者 | 删掉前者并在注释里说明为何不需要；后者真正用于 `reap`（尸体保留 0.3s 供动画） | 已修 |
| M3 | 有空间槽位的植物整段跳过族行为，而矩阵只看族名 → 「147/147 已接线」虚高 | 矩阵口径改写：注明槽位执行器与族函数两条路径，`wired` 只表示族有实现 | 部分修（语义澄清，未改分派） |
| M4 | hash 漏 `plant.actionTimer`、`skySunTimer_`、`firstSkySunSpawned_`、`sun.expires`、`shot.pierce/splash/slow/owner`、`zombie.speed/family/deathTick` | 全部并入 FNV 输入 | 已修 |
| M5 | 冒烟只 3 关 3 世界、5 场景全 lost、`won` 在 CLI 层零覆盖 | 扩到 32 场景（26 世界 + 5 定点 + 1 胜利）；`beach_23` 脚本局实测 `won`，无 `won` 即失败 | 已修 |
| M6 | `testTwentySixWorlds` 恒真、`testShotsAndEating` 不测啃食、`argv[3]` 未用 | 收紧断言 | **未修**，归 S3 测试收紧（`engine_test.cpp` 属 wirer 写作用域，本轮只加了 `testPackActions`） |
| M7 | legacy `Battle`（`battle_view.cpp` 唯一消费者）与 engine 数值分叉（天空阳光 8s vs 4.5s+24s、推车 -0.25 vs -0.7） | 在 `NATIVE_PROGRESS.md` 与本节登记分叉点；桌面视图迁移到 engine 属 S4 | **未修（已登记）** |

## Low

| 编号 | 问题 | 处置 | 状态 |
| --- | --- | --- | --- |
| L1 | `kMaxPlants` 无使用者 | `plant()` 用它上限 | 已修 |
| L2 | `removed` 恒 0、推车击杀混入 `killed`、无漏怪计数 | 新增 `mowerKills()/leakedZombies()/rejectedSpawns()`，`removeZombie` 只计 `removed_` | 已修 |
| L3 | 回放输入允许迟到、`collect id=0` 与真 id 冲突、tick 未校验 | `parseScript` 拒绝回退 tick、`plant` 缺 type、`collect` 负 id；迟到输入写 `input_late` 事件（不丢点击） | 已修 |
| L4 | `--rows` 缩小时 `tickWaves` 静默丢僵尸 | 记 `rejectedSpawns_` + `wave_spawn_rejected` 事件 | 已修 |
| L5 | `parity_report.playable` 是字面量 0；`engine_families` fail-open | `playable` 改为「被关卡引用且族有实现」的推导值；族表解析为空即抛错 | 已修 |
| L6 | `build_native.ps1` 固定 `build/native`，并发构建撞 `.tlog` 锁 | 新增 `-BuildDir` 参数（绝对或仓库相对），默认路径不变 | 已修 |

## 验证记录

2026-11-20 20:40（修复轮收尾）：

- `pwsh -File tools/build_native.ps1 -AuditOnly` → **10/10 Passed**（`engine`、`world_outcome` 在内），隔离构建目录 `build/captain-audit` 亦 10/10。
  （历史值。第二轮修复加入 `testVaultSkipsPlantAndMowerIsNotAPlantKill` 后为 **11/11**；本节的 10/10 与 15/15 已不可在现树复现，保留原文以示改动轨迹。）
- `pwsh -File tools/build_native.ps1`（desktop）→ **15/15 Passed**；desktop exe 3,630,592 字节 SHA-256 `5630D60B…FDA79`。（现树为 16/16，见下节。）
- `python -m unittest discover -s tools/tests -p 'test_*.py'` → **Ran 50 tests, OK**。（现树为 **Ran 106 tests**：本行是 20:40 的计数，之后又并入 `decks`/`expand`/`pfamilies` 等用例。）
- `python tools/engine_smoke.py` → 32 场景全部双跑一致；26 世界棋盘与 `board_sizes.json` 一致；`beach_23` `won`。
- `pwsh -File tools/check_all.ps1` → `[ok] content, build, tests and parity are consistent`，EXIT=0。
- 修复后 hash 全部变化（内核语义变了，属预期）：`frontyard_1` 5×9 `0x810daeae75e6004a`、6×10 `0xa7eecce8cd9df22d`、脚本局 `0x54d0952e5f1df175`、`frontyard_6` `0x6c36c1eb2fe8c506`、`kongfu_1` `0x072c993b96804fdf`、`beach_23` 胜利局 `0xde03536c990dee92`。
- 未修项：M6（测试收紧）、M7（legacy 分叉）、M3（语义澄清而非改分派），另加 wirer 登记的两条（`SpawnOffset.y`、unknown 计数 API）。

## 队长追加（2026-11-20 21:30）：M6 收紧 + pack 僵尸兜底

### M6 收紧（`native/tests/engine_test.cpp`）

- `testTwentySixWorlds`：原来只跑 120 s 断言 status 合法，恒定可过。现在每世界追加四条断言 ——
  ① `snapshot().rows/cols` 与 `world.rows()/cols()` 一致；② `waves() > 0` 的世界必须真的 `spawnedZombies() > 0`；
  ③ 同种子同关卡两次构造再跑同一步数，`hash` 必须相等（原先只在 `testDeterminism` 里测一关）；
  ④ 有棋盘表的世界，引擎尺寸必须等于 `catalog.boards[world]`（防 geometry 与 engine 分叉）。
  另加全局断言「至少 20 个世界要排上僵尸」，防止只跑空关卡也全绿。
- `testShotsAndEating`：原来只测"僵尸血量降了"。现在拆成三段 —— ① 豌豆命中；② **真啃食**：
  墙坚果 (3,5) + basic，逐 tick 推进，必须观察到 `ZombieState::eating` 且坚果 hp 严格下降；
  ③ **fly 族不啃食**：从 pack 里挑第一个 `zombieFamilyFor(className)=="fly"` 的类型（当前是 `bighead_balloon`），
  种墙坚果后跑 20 s，断言坚果仍在且 hp 未变。

### pack 僵尸兜底（`native/src/engine/world.cpp` `World::spawnZombie`）

- 原来只认 `catalog_.zombies`（content JSON 的 55 条），pack 里另外 1072 个类型完全无法上场 —— 这条**不计入**
  原审计 19 条，是本轮补发现的缺口。
- 现在：content 缺失但 pack 有该 id 时，`className`/family 取 class 表，`hp/speed/eatDps` 取 pack 字段
  （缺省 190/0.185/100，且 ≤0 时回落），`armor` 仍只认 content（pack 的 `ZombieArmorProps` 尚未建模）。
- **顺序保持不变**：`ZombieClass` 表 > content `behavior` > `walk`，因此 55 条已有僵尸的行为语义与哈希不受影响。
- 验证：`C:\pvzbuild\m6\Release\engine_test.exe content native\generated\content.pack %TEMP%\pvzengine` →
  `engine tests passed`，EXIT=0（构建目录必须在 ASCII 盘，见下条）。

### 构建目录约束（新发现，写入基线）

仓库位于中文路径 `D:\OneDrive\文档\...`。**全新** build 目录首次 configure 时，MSBuild 的自定义步骤会把
命令行按 ANSI 传下去，导致 `json-src/CMakeLists.txt:155 (CONFIGURE_FILE): No such file or directory`
（路径显示成 `D:/OneDrive/鏂囨。/...`）与 `MSB8066`。规避：`tools/build_native.ps1 -BuildDir 'C:\pvzbuild\<name>'`
（脚本支持绝对路径）。已验证 `C:\pvzbuild\m6` 下 audit 目标可正常配置与构建。



## 第二轮修复（2026-11-20 21:55，响应 auditor t11 的 needs_revision）

auditor 的复审结论（`docs/reviews/2026-11-20-fix-verification.md`）判 16 条里只有 8 条真关，
并点出 5 条必须先修。逐条处理如下。

### 1. B1（blocker）：跳跃仍在原地反复起跳 —— 已真关

- 根因有两层：① 落点 `centre - (kEatStartCols + 0.1)` 仍在起跳窗口 `[centre-1.4, centre+0.5]` 内；
  ② 更关键的是**跳的逻辑挂在族钩子上，而 `tickZombies` 先解算啃食**——僵尸一到窗口就被判为啃食、
  速度归零，永远走不到起跳条件，所以"对可啃的墙坚果根本不跳"。
- 修法：把跳跃搬进 `World::tryVault`（`native/src/engine/world.cpp`），在 `tickZombies` 的**啃食扫描之前**调用；
  落点改为植物左边缘外 `centre - 0.55`（植物占位 `[centre-0.5, centre+0.5]`），并且只对
  "正在走进的那一株"（`zombie.x - centre ∈ [-0.05, kEatRangeCols+0.05]`）生效——落点在 `-0.55` 之后
  不再满足触发条件，**结构上**不可能对同一株重复起跳；2 s 冷却只作第二道保险。
  `registry.cpp` 的 `zombieJump` 保留为空实现并注明原因（族表仍引用它）。
- 回归测试：`native/tests/engine_test.cpp` 的 `testVaultSkipsPlantAndMowerIsNotAPlantKill` —— 空地关 +
  墙坚果 (2,4) + pack 里第一个 jump 族僵尸，断言：植物存活且 hp 不减、`zombie_hop` 事件恰好 1 次、
  关卡能结算、`mowerKills()==1` 且 `killedZombies()==0`。

### 2. H4（high）：门禁仍会覆盖基线 —— 已真关

- `tools/check_all.ps1` 新增 `Sync-Baseline`：内容未变则不动；基线缺失才 seed；内容变了**只有**
  显式 `-AllowMatrixChange` 才写盘，否则保留旧基线、把 fresh 留在 `build/` 并在摘要里打 `[keep]`。
- 因此"一次失败就把证据换成新基线"的路径被删掉，三个报告（smoke / 矩阵 / world_diff）都走同一函数。

### 3. 双静默降级（新发现）—— 已关

- `native/src/catalog.cpp`：显式给出的 `--pack` / `--boards` 读不出来时**抛错**
  （`rules pack: ...` / `board sizes: ...`），不再 exit 0 退回常量与 5×9。
- `native/tests/catalog_test.cpp` 的旧断言（"坏 pack 回落到 JSON"）改为断言抛错，并新增坏 boards 用例。
- 这条修掉之前，冒烟里 26 条世界几何断言其实一直在看默认 5×9，等于没测。

### 4. L2（low）：推车击杀混入 `killed` —— 已关

- `World::damageZombie` 增 `bool countsAsKill = true`；`tickMowers` 传 `false` 并自行 `++mowerKills_`。
- `tools/engine_smoke.py` 增记账恒等式：`spawned == killed + mowerKills + leaked`（`won` 时严格相等）。
- 口径影响：脚本局 `killed` 由 30 降到 15（旧值含 15 个推车击杀），故 `minKilled` 由 25 改为 10，
  并在 `PROBES` 里注明原因；26 个无防守世界不再出现 `killed == mowerKills`。

### 5. 21:21–21:38 审计配置不可编译（新发现，已修）

- wirer 的 `--play-script` 把 `pvz::PlayScriptOptions`（定义在只有桌面开关才 include 的 `battle_view.hpp`）
  用在了 `#ifdef PVZ_ENABLE_DESKTOP` 之外，`-DPVZ_ENABLE_DESKTOP=OFF` 下 C2039，audit 构建直接失败。
  该窗口内 `check_all.ps1 -Desktop` 实测 exit 1，是**门禁抓到的**，不是自查发现的。
- 修法：整个 `--play-script` 分支（含参数解析）移入桌面守卫，非桌面构建统一抛
  `desktop support is disabled; rebuild with -DPVZ_ENABLE_DESKTOP=ON`（与 `--play` 一致）。
- 同窗口内 `world.cpp` 的 `sun_ -= cost` 有 `C4244`（double→int64 截断）告警，已改
  `sun_ -= static_cast<std::int64_t>(std::llround(cost))`；`--play-script` 行为经实测未变
  （同脚本同 hash `0xf64b8a62c1d16e0d`，同截图 SHA-256 `3762fabd…690a99`）。

### 第二轮验证记录（现树，2026-11-20 22:2x round-3 重测）

> 第二轮当时写的 11/11、16/16、Ran 106 是 21:38 的状态。`art_audit` 并入后实测已变，
> 下表是 round-3 在本轮修复之后重新跑出来的数（历史值保留在括号里，不删）。

- `pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\r3a'` → **12/12 Passed**（曾记 11/11；新增 `art_audit`），AUDIT_EXIT=0。
- `pwsh -File tools/build_native.ps1 -BuildDir 'C:\pvzbuild\r3d'` → **17/17 Passed**（曾记 16/16；新增 `battle_render` 后的现树），DESKTOP_EXIT=0。
- `python -m unittest discover -s tools/tests -p 'test_*.py'` → **Ran 172 tests, OK**（曾记 106，再记 136：`tools/tests` 又并入了 S4/S5 的用例）。
- `python tools/engine_smoke.py` → 32 场景双跑一致 + 记账恒等式成立；`beach_23` 仍 `won`。
- `pwsh -File tools/check_all.ps1 -Desktop -AllowMatrixChange` → `[ok]`，EXIT=0；随后**严格重跑**
  `pwsh -File tools/check_all.ps1` → `[ok]`，EXIT=0（证明新基线自洽，且门禁不再自愈）。
- 冒烟 hash 变更（因 `killed` 参与 hash，推车击杀不再计入）：`frontyard_1` 5×9 `0x5ae9046e3d2e0528`、
  6×10 `0x1937dc728a709752`、脚本局 `0xac1156c1ef5ccf69`、`frontyard_6` `0x5f60678b82f42a5c`、
  `kongfu_1` `0xa9abd80e22754f26`；`beach_23` 胜利局 **未变** `0xde03536c990dee92`（1 只僵尸、无推车参与）。
- 仍未关：M6 的部分断言（`argv[3]` 仍未用）、M7（legacy `Battle` 与内核分叉，桌面已迁到 `engine::World`，
  只剩 `--simulate` 路径）、`SpawnOffset.y`、unknown 动作计数 API。均已在计划里留了归属。

---

## 第三轮（round-3，2026-11-20 22:2x）

t13 复审给出 4 条「必须先修」＋ 2 条建议。本轮逐条处理，**引擎目录按 captain 22:24 的指示冻结（S5 在用）**，
所以自动契约里那条 vault 窗口收紧不在本轮范围内，移交 S5。

### 1. 台账数字（t13 第 5 条）

- `docs/reviews/2026-11-20-audit-fixes.md`（本节）与 `docs/PARITY_BASELINE.md`（161 行）改为**实测值**：
  audit **13/13**（多出 `art_audit` 与 `progress`）、desktop **18/18**（`progress` 也进桌面配置）、Python **Ran 259**。
  历史值按日期保留，不删：曾记 11/11、16/16、Ran 106；再记 136、172、203、217。
- `docs/PARITY_BASELINE.md` 末尾新增 `## 测试例数台账（机器可读）`，用 `<!-- test-counts -->` 块存三个数，
  由 `tools/check_all.ps1` 的 `== test ledger ==` 步骤在每次运行时比对。
- **为什么用块而不是散文**：一天之内这两行漂了四次（11/11→12/12、16/16→17/17、Ran 106→136→172→203→217），
  每次都是新增测试文件改了实数、文档留在旧值。散文里的数字没人会去对，可解析的块能对着跑。

### 2. 结构性 blocker：`catalog.hpp` 只前向声明 `ContentPack`

- `native/src/catalog.hpp`：删掉 `namespace content { struct ContentPack; }`，改为无条件
  `#include "content/model.hpp"`（附注释记录 2026-11-20 的两个红窗）。`content/model.hpp` 不 include
  `catalog.hpp`，确认无循环。
- **反向探针（证明门禁真能抓这类错误）**：把前向声明放回、并摘掉 `native/tests/art_audit_test.cpp` 自己的
  `#include "content/model.hpp"`，audit 构建立刻红：
  `native/src/art_index.cpp(290,35): error C2027: use of undefined type 'content::ContentPack'`、
  `(290,43): error C2039: 'findPlant': is not a member of 'std::shared_ptr<const content::ContentPack>'`，
  连带 `C3536/C2446/C3487`。还原后（hash 回 `3AC1CA00…E00A` 与 `6A82F837…E095`）同一目录 12/12 绿、EXIT=0。
  注意红点落在**库文件** `art_index.cpp` 而不是测试：前向声明会毒化每一个只 include `catalog.hpp` 的翻译单元。

### 3. 门禁覆盖：`check_all.ps1` 默认只跑 audit

- 现在是 **audit + desktop 两个配置默认都跑**；`-NoDesktop` 是显式跳过开关，跳过时打印
  `[skip] -NoDesktop: battle_view.cpp / assets.cpp were NOT compiled…`（不做静默通过）；`-Desktop` 保留为兼容用的空操作。
- 两个配置各有独立构建目录：`$auditBuild = build/native`、`$desktopBuild = build/desktop-gate`
  （共用会被 MSBuild 复用 `.tlog`/`.obj`，跑出「没编译被测文件却绿」）。失败信息里步骤名写明是哪个配置。
- 这一条正是第二个红窗活下来的原因：`battle_view.cpp` 属桌面专属翻译单元，audit 构建根本不编译它。

### 4. `PARITY_MATRIX` 的 `playable=0` 字面量（t11 L5 残留）

- `tools/parity_report.py`：`Row.playable` 改为 `int | None`（缺省 `None`，即「没有推导值」），新增
  `playable_kind`（derived / not-applicable / pending）、`playable_note`、`playable_text()`→`—`；
  `apply_not_derived(matrix)` 给八行写明理由；`caliber_notes(matrix)` 生成口径说明（表格里一段 + 逐行一条，CLI 也打印）。
- 结果：植物 41/147、僵尸 47/55 仍是推导值；`僵尸 class 族`、`植物行为族`、`Boss`、`砸罐子`、`小游戏` 标
  **not-applicable**，`世界`、`关卡`、`融合` 标 **pending**，表里显示 `—`，完成度也显示 `—` 而不是 `0.0%`。
- 口径说明原文：`口径：8 行「可跑」没有推导值，表中显示 —（不是 0）：不适用 5 行（僵尸 class 族、植物行为族、Boss、砸罐子、小游戏）；待统计 3 行（世界、关卡、融合）。`

### 5. 告警清扫（C4244 / C4267）

- `native/src/engine/world.cpp` 的 `sun_ -= cost` 在上一轮已改 `static_cast<std::int64_t>(std::llround(cost))`。
  本轮把 audit / desktop 的构建日志逐份落盘再扫（`%TEMP%\r3a-*.log`、`%TEMP%\r3d-*.log`，共 11 份），
  `warning C4244` 与 `warning C4267` **零命中**；日志里唯一的 `warning C` 是 `progress_test.cpp` 的 C4996
  （`fs::u8path` 在 C++20 弃用），那是 captain 新挂的文件、随后已修，不属本轮范围。

### 本轮验证记录

| 命令 | 结果 |
| --- | --- |
| `pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\r3a'` | 13/13 Passed（含 `progress`），EXIT=0 |
| `pwsh -File tools/build_native.ps1 -BuildDir 'C:\pvzbuild\r3d'` | 17/17 Passed，EXIT=0（`progress` 落地前）；改用门禁目录 `build/desktop-gate` 后 **18/18** |
| `python -m unittest discover -s tools/tests -p 'test_*.py'` | Ran 259 tests，OK，EXIT=0 |
| `pwsh -File tools/check_all.ps1 -AllowMatrixChange` | audit + desktop 同跑，`[ok] refreshed docs/PARITY_MATRIX.md`，EXIT=0 |
| `pwsh -File tools/check_all.ps1`（严格，双配置） | audit 13/13 + desktop 18/18（`build/desktop-gate`）+ Ran 259 + 冒烟 + 矩阵 + 世界 diff 全过，`== test ledger ==` 三项一致，`[ok]`，EXIT=0 |
| 反向探针（`catalog.hpp` 放回前向声明 + 摘测试 include） | audit 构建 `error C2027/C2039` 红，还原后绿 |
| 反向探针（台账写 `| audit | 11 |`） | `[fail] audit ran 12 tests, the ledger says 11` + EXIT=1，还原后绿 |

### 本轮撞上的外部红窗（都不是本轮改动，记下来免得下次误判）

1. **`progress_test.cpp` 编不过**（captain 22:34 挂 `pvz_progress` 时新加的文件）：`World` 拷贝构造被 delete
   引发 `error C2280`、`(void)temp` 引发 `error C2065`、`fs::u8path` 触发 C4996。于是 audit 构建红、
   `check_all` 停在 `== audit build ==`。captain 修完后 13/13 绿。
   教训：双配置门禁只能把「红窗」压到下一次跑门禁，防不住别人刚挂进来的目标编不过。
2. **`test_armors` 三项失败**（`tools/contentc` 的护甲表与生成物不一致：shipped hash 不符、`1127 != 1125`），
   使 `== tool tests ==` 红；与本轮改动无关，对方重新生成后 27 个用例全绿，`check_all` 才跑到底。

### 仍未关（有归属）

- **vault 窗口收紧 / `jump_distance` 断言**：自动契约第 3 条要求改 `native/src/engine/world.cpp`，
  但 captain 22:24 明确冻结 `native/src/engine/**`（S5 正在改），本轮**未做**，移交 S5。
  现状仍是 `ahead > tuning::kEatRangeCols + 0.05`（1.20 列）与 `jump_distance` 未被读取，t13 的 residual 依然成立。
  → **2026-11-23 由 t30（S5.12）关闭**：窗口收到 `kVaultTriggerMaxCols`（0.40 列）、事件补
  `from/to/distance/jump`、`engine_test` 断言 `distance > 0` 且 `from <= 中心 + 0.40`，反向探针原文见文末「S5.12 跳跃证据闭合」。
- Python 例数是**下界**而非精确值：`tools/tests` 由多个 agent 并行编辑，精确相等会在几分钟内变红
  （实测 136→172→203→217 只花了 40 分钟）。丢用例仍会红，新增只打 `[warn]`。

## 第三轮复审（auditor t20，2026-11-21 10:29）

报告：`docs/reviews/2026-11-20-fix-verification-round3.md`（320 行）。判定 **needs_revision**：
4 条真关、1 条未关（台账数字）。

| # | 条目 | 判定 | 证据（复审原文摘要） |
| --- | --- | --- | --- |
| 1 | B1 跳跃 | 真关 | `world.cpp:256` 落点 `centre-0.55` 在触发窗口外；副本改回 `centre+1.05` → `engine` 红出 `the vaulted plant must survive`，其余 13 例绿 |
| 2 | H4 门禁自愈 | 真关 | 副本篡改基线 → `[keep] … left untouched` + `[fail] … changed` + EXIT=1，基线 sha 不变 |
| 3 | 双静默降级 | 真关 | 坏 `--pack` / `--boards` 均 EXIT=1 且点名阶段；`catalog_test:82-97` 为抛错断言 |
| 4 | L2 击杀计数 | 真关 | 26 个无防守世界 `killed==mowerKills` 行数 26→0；脚本局 killed 30→15；`won` 局守恒 |
| 5 | 台账数字 | **未关** | 台账 13/18/259 vs 现树 15/20/263；`check_all` 的 ledger 步对干净树报 `[fail]` 并 EXIT=1 |

### 复审新发现与处置

| 编号 | 严重度 | 发现 | 处置 |
| --- | --- | --- | --- |
| N2 | medium | 门禁结论不能与并行编辑共存：同一次运行 audit 绿、desktop 红在别人半成品的 `world.hpp(107-115)` | `check_all.ps1` 新增 `Get-TreeStamp`（`native/src`、`native/tests`、`CMakeLists.txt`、`tools` 的路径+大小+mtime 摘要），运行前后不一致即 `[inconclusive]` 并 **exit 2**（既不算过也不算失败） |
| N3 | medium | `tryVault` 窗口上界 `kEatRangeCols+0.05 = 1.20` 列 vs 接触距离 `kEatStartCols = 0.35`，冷却 2 s 可连跳；无跳跃距离/时机用例 | 归 **t30**（S5.12 跳跃证据闭合），本文件不重复登记 |
| N4 | medium | `LNK1104 cannot open ...exe` 直接打断门禁（OneDrive 持有产物） | `check_all.ps1` 新增 `Step-Build`：首次失败且输出含 `LNK1104/C1041/cannot open program database` 时等 3 s 重试一次，其它错误立即失败 |
| N5 | low | `check_all.ps1:136` 有两个 0x08 控制字符（注释里） | 已改写成可读文本 |
| N6 | low | M6 残留：`engine_test` 的 `argv[3]` 未用、26 世界 status 断言恒真 | `testTwentySixWorlds(catalog, temp)` 现在把每个世界的 `world/level/几何/status/tick/spawned/hash` 写进 `<temp>/engine_worlds.txt` 并回读校验 26 行；`playing` 的世界必须 `tick==7200`，结束的世界必须 `tick<=7200` |
| — | — | 台账数字落后 | `check_all.ps1` 新增 `-UpdateLedger`（显式开关，重写 `docs/PARITY_BASELINE.md` 的 `test-counts` 块）；默认仍对干净树判红 |

### 台账为什么必须显式更新

`test-counts` 块是文档与运行之间唯一的机器可读绑定。一天内它错了两次（11/11 时实际 12/12、
16/16 时实际 17/17），根因都是"加了测试文件但没人回头改文档"。把写回做成 `-UpdateLedger`
既保留了"数字必须与运行一致"的门禁，又不给自动改写留后门——红的时候仍要人去判断该不该接受。

## 台账数字关闭（t20 第 5 条，2026-11-21 11:20）

t20 唯一未关的是"台账数字落后于现树"（文档 13/18/259 vs 当时 15/20/263）。现在它以机器可读的方式关闭：

```
$ pwsh -File tools/check_all.ps1 -NoContent -AllowMatrixChange -UpdateLedger
== audit build ==      100% tests passed, 0 tests failed out of 17
== tool tests ==       Ran 296 tests in 46.722s
== desktop build ==    100% tests passed, 0 tests failed out of 22
== test ledger ==      [ok] rewrote the test-counts block in docs/PARITY_BASELINE.md (-UpdateLedger)
                       [ok] audit ran 17 tests (ledger agrees)
                       [ok] python ran 296 tests (ledger agrees)
                       [ok] desktop ran 22 tests (ledger agrees)
EXIT=0  elapsed=332s
```

写回不是自动的：`-UpdateLedger` 是显式开关，默认只比对不写。写回后立刻做了一次不带任何放行开关的严格重跑：

```
$ pwsh -File tools/check_all.ps1 -NoContent
...全部步骤绿（17/17、22/22、296、三项 ledger 一致）
[warn] the source tree changed while the gate ran (99903D4DABC4D205 -> 38674AFEE86E8832)
[inconclusive] rerun on a quiet tree before believing any result
EXIT=2
```

**exit 2 是正确结果**：这 143 秒里 wirer 已经开始 t29（护甲接线），源码确实变了，所以这一轮不对任何单棵树作结论。
C44 从"设计意图"变成"实测行为"——此前同一情形会给出 audit 绿、desktop 红的假信号。

`#5 台账数字` 判定：已关闭（机制层面），待 t29/t30 落定后做一次静树严格跑作为最终证据。

## S5.12 跳跃证据闭合（t30，2026-11-23）

§「仍未关（有归属）」里那条 **vault 窗口 / `jump_distance`** 由本节关闭。改变三处（都在 t30 写作用域内）：

1. `native/src/engine/tuning.hpp` 新增两个命名常量：
   `kVaultTriggerMaxCols = kEatStartCols + 0.05`（= **0.40** 列）与 `kVaultLandingCols = 0.55`（落点距植物中心）。
   注释写明「只对贴身僵尸生效」以及为什么旧的 `kEatRangeCols + 0.05` 会让起跳提前一整列。
2. `native/src/engine/world.cpp::tryVault` 用这两个常量；`zombie_hop` 事件从 `{id,row,col,x}` 扩成
   `{id,row,col,x,from,to,distance,jump}`，其中 `jump = (from > 植物中心 && to < 植物中心) ? 1 : 0`
   ——「真越过」与「只是落地校正」分开记，旧字段 `x` 保留不动。
3. **连带修掉一个只有收窄窗口才会暴露的排序问题**：`tickZombies` 的啃食扫描用的是 `kEatRangeCols`（1.15），
   而 `tryVault` 在它之前跑。旧窗口 1.20 恰好比它宽 0.05，所以起跳总能抢在啃食判定之前；
   窗口收到 0.40 后，僵尸会在 1.15 列处先被判成 eating、停住不动，永远走不到接触距离——测试立刻红出
   `the vaulted plant must survive: a vaulter must not eat it`（wall-nut 被吃掉）。
   处置：**只有 `family == "jump"` 的僵尸**把啃食 reach 收成 `kEatStartCols`（贴脸才咬），其它族完全不变。
   这不是为了让测试变绿而放宽窗口，而是「跳跃者必须先走到植物跟前才谈得上跳过去」。

### 实测一跳（`engine_test` 的 `testVaultSkipsPlantAndMowerIsNotAPlantKill`，wall-nut 在 (2,4)，中心 4.5）

```
DBGHOP hops=1 tick=1764 from=4.89867 to=3.95 distance=0.948667 jump=1
```

`from - 4.5 = 0.39867` → 正好落在 0.40 的窗口内第一个 tick（速度 0.3 列/s，每 tick 0.005 列）；
`to = 3.95 = 4.5 - 0.55`；`distance = from - to = 0.948667 > 0`；`jump = 1`。植物 hp 全程未变，僵尸由本行割草机清掉。

### 反向探针（原文）

把 `world.cpp` 的条件改回 `ahead > tuning::kEatRangeCols + 0.05`（标 `// PROBE_T30`），重建后：

```
$ pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\t30'
100% tests passed 之前先红：
engine test failed: a hop must only start at contact: from 5.698667 is outside the 0.400000-column window around 4.500000
PROBE_EXIT=1
```

即**窗口一放宽，起跳就从 4.898667 提前到 5.698667**（正好 is 4.5+1.15+0.05-0.005），断言 ② 报红。
还原（`world.cpp` sha256 回到 `C3B3EF84CDF8ACCA64BB93A1EE6CB2C582F47F32FA090C4F97968126C23C93F9`，
`PROBE_|DBGHOP|fprintf` 残留 0）后两道门禁复绿。

### 本轮的验证记录

| 门禁 | 命令 | 结果 |
| --- | --- | --- |
| audit | `pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\t30'` | `100% tests passed, 0 tests failed out of 19`，EXIT=0 |
| desktop | `pwsh -File tools/build_native.ps1 -BuildDir 'C:\pvzbuild\t30-desktop'` | `100% tests passed, 0 tests failed out of 24`，EXIT=0 |
| 冒烟 | `python tools/engine_smoke.py --exe 'C:\pvzbuild\t30\Release\PvZ2SHUTTLE.exe' --out build/engine_smoke.t30.json` | 32 场景 **0 条哈希变化**，其它字段（tick/status/killed/mowerKills/spawned）全等 |

冒烟 0 变化的解释（不是「没测到」，是这一改动不可能触达那些场景）：
32 个场景里只有 `frontyard_6 5x9` 的关卡含 `pole_vaulter`，但该冒烟场景不种任何植物 → 没有触发目标 → 不会起跳；
其余场景的僵尸族都不是 `jump`，而两处改动分别只作用于 `family == "jump"` 的啃食 reach 与 vault 路径。
`native/generated/engine_smoke.json` 因此**没有被改写**（0 diff 即无需刷新）。

