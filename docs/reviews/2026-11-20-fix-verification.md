# S4.4 复审：16 条「已修」是否真的关闭（只读）

- 审核人：auditor（只读；未改源码/测试/产物，未 commit）
- 被审对象：`docs/reviews/2026-11-20-audit-fixes.md`（88 行，21:27:17 重写，8190 B）声称"已修"的 16 条
- 原始缺陷：`docs/reviews/2026-11-20-s2-audit.md`（B1 / H1–H5 / M1–M7 / L1–L6）
- 复审时间：2026-11-20 21:26–21:50

## 0. 一句话结论

**16 条"已修"里只有 8 条真的关了**（H1/H2/H3/H5/M1/L1/L4/L6），**8 条只是部分关闭**（B1/H4/M2/M4/M5/L2/L3/L5），M3/M6/M7 仍未修。更关键的是：审核期间仓库在 21:21–21:39 存在 **audit 配置不可编译** 与 **pack-only 植物不可种** 两个真实破损窗口，而台账的"验证记录（20:40）"写的是 `10/10`、`15/15`、`[ok]`——现树已恢复（11/11、16/16），但那份验证记录**不能**作为"S4 已验收"的证据。

## 1. 审核快照（本报告的判定以此为准）

审核期间源码被并行改动（队长/wirer 持续编辑），因此每条判定都绑定 hash。最终快照 2026-11-20 21:41:19：

| 文件 | SHA256 前 12 | mtime | bytes |
|---|---|---|---|
| `native/src/engine/world.cpp` | F660532F4487 | 21:39:18 | 28180 |
| `native/src/engine/registry.cpp` | 4887E7C36D6C | 20:54:42 | 24078 |
| `native/src/engine/action_runner.cpp` | FB92874BF2F1 | 20:24:43 | — |
| `native/src/engine/projectile.cpp` | 982D16DD5ADE | 20:16:48 | — |
| `native/src/engine/replay.cpp` | 9450E9C3AF19 | 20:18:33 | — |
| `native/src/engine/tuning.hpp` | 4BC48DF501E2 | 20:16:41 | — |
| `native/src/engine/zombie_family.cpp` | CFE081BC5A5C | 20:47:27 | 1125 |
| `native/src/catalog.cpp` | 3289178FF9A0 | 20:19:14 | 17140 |
| `native/src/main.cpp` | E3FDFA8590BE | 21:38:55 | 8830 |
| `native/tests/engine_test.cpp` | A7E4F2B7AA03 | 21:31:39 | 30935 |
| `tools/check_all.ps1` | 8EA33D933D33 | 21:32:10 | 6055 |
| `tools/parity_report.py` | 6BA4636F9B52 | 21:33:03 | 16213 |
| `tools/engine_smoke.py` | 69A6E0CA118F | 20:26:44 | 8021 |
| `tools/build_native.ps1` | F3C3F4B249FB | 20:18:00 | — |

## 2. 证据命令（全部实跑，未写 `build/native`）

| # | 命令 | 结果 |
|---|---|---|
| E1 | `pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir build/auditor-verify`（21:26） | **FAIL** `main.cpp(60,18): error C2039: 'PlayScriptOptions': is not a member of 'pvz'`，EXIT=1 |
| E2 | 同上 `-BuildDir build/auditor-verify2`（21:38） | **FAIL**，同 C2039 |
| E3 | 同上（21:41，main.cpp 21:38:55 重写后） | `100% tests passed, 0 tests failed out of 11`，AUDIT_EXIT=0 |
| E4 | `pwsh -File tools/build_native.ps1 -BuildDir build/auditor-verify-desktop`（21:26） | **FAIL** `engine test failed: a pack-only plant must be plantable, got: unknown plant: ailmint`，`94% tests passed, 1 tests failed out of 16` |
| E5 | 同上 `-BuildDir build/auditor-verify-desktop2`（21:39，world.cpp 21:39:18 后） | `100% tests passed, 0 tests failed out of 16`，DESKTOP_EXIT=0 |
| E6 | `python tools/engine_smoke.py --exe build/auditor-verify2/Release/PvZ2SHUTTLE.exe --out build/auditor-verify/smoke-verify.json` | SMOKE_EXIT=0，32 场景双跑一致；`beach_23 win 6x9 won tick=1538 hash=0xde03536c990dee92` |
| E7 | `python -m unittest discover -s tools/tests -p 'test_*.py'` | `Ran 106 tests … OK`（台账写 50） |
| E8 | 探针 A/B（`build/audit-probe*`，合成 content）：跳跃僵尸 vs 地刺 / 行走对照 | jump `won tick=9349 killed=1 mowerKills=0`；walk `won tick=2107 killed=1 mowerKills=1` |
| E9 | 探针：`pole_vaulter` vs 可啃 `wallnut` | `won tick=4508 mowerKills=1`（啃穿过去，未跳） |
| E10 | 探针：`deck=["wallnut"]` 却种 `peashooter` | `sun:925`（只扣了 75）⇒ 被拒，H1 生效 |
| E11 | 探针：空 deck + `--pack`，种 pack-only 植物 `ailmint` | 21:36 `sun:2000`（被拒）；21:41 `sun:1650`（扣 350） |

> `tools/check_all.ps1` **未运行**：它无条件重写 `native/generated/*.json`、`docs/PARITY_MATRIX.md`、`native/generated/world_diff.md`，超出本任务允许写的范围（仅本报告）。改为静态审查并在 §6 标注该事实的后果。

## 3. 逐条判定表（19 条）

图例：**✅真的关了** / **🟡部分关闭** / **❌只在文档里关了**

| # | 声称 | 判定 | 依据（文件:行号） | 复现/输出（≤3 行） |
|---|---|---|---|---|
| B1 | 跳跃僵尸落地改到植物左侧 | 🟡 | `registry.cpp:387` 窗口 `x > centre+0.5 || x < centre-1.4`；`:391` 落点 `centre-(kEatStartCols+0.1)`=centre−0.45；`:394` 冷却 2 s | E8：jump 死在地刺前 `tick=9349 mowerKills=0`；同 hp/speed 的 walk 对照 `tick=2107`。落点仍在窗口内，2 s 只走 0.6 列 ⇒ **原地反复起跳** |
| H1 | deck 校验 + 植物上限 | ✅ | `world.cpp:271-273` `find(deck)==end → "not-in-deck"`；`:267` `plants_.size() >= kMaxPlants` | E10：`sun:925`（wallnut 75 已扣，peashooter 未扣） |
| H2 | 触发线/判负线分离 + leaked | ✅ | `world.cpp:180-188` `x < kLoseX` 且 `mower.state != 0` → `++leaked_; lost`；`:190-192` `x < kMowerTriggerX` → 推车 | `grep kMowerTriggerX` 三处命中：`tuning.hpp:35` 定义、`world.cpp:178` 注释、`world.cpp:190` 使用 ⇒ 常量不再是死的 |
| H3 | 迭代中 spawn 改为延迟队列 | ✅ | `world.cpp:139` `inZombieLoop_=true`；`:345-350` 入 `pendingSpawns_`；`:194-201` 循环后 flush | `grep pendingSpawns_` ⇒ 队列 + flush 各一处，`tickZombies` 不再 push_back |
| H4 | 基线在生成器之前读取 | 🟡 | `check_all.ps1:94` 读基线 → `:95-97` 生成 → `:99` 比较 → **`:100` 仍无条件 `Copy-Item -Force`** → `:101-104` 记失败 | 顺序已修；但失败时基线已被覆盖，下一次比较对的是新基线（门禁一次性）。且 `git ls-files native/generated` = **0** ⇒ 覆盖即永久丢失，无 .rej/备份 |
| H5 | 减速单位换成 tick | ✅ | `projectile.cpp:35` `slowUntilTick = tick() + shot.slow / tuning::kStepSeconds` | 读码即可定性；E6 的 32 场景 hash 与 21:44 前基线一致说明未回归 |
| M1 | `advance` 拒绝非法 dt + 预算事件 | ✅ | `world.cpp:63-65` `throw "World::advance needs a finite dt in [0, 86400]"`；`:76-79` `event("time_budget_exceeded")` + `accumulator_=0` | `grep -n "time_budget_exceeded"` 命中 world.cpp + replay/summarize 路径 |
| M2 | 删死常量；fade 生效 | 🟡 | `tuning.hpp` 已无 `kVictoryFlushSeconds`；`world.cpp:235-240` 按 `kZombieDeathFadeSeconds` 保留尸体 | 但 `entity.hpp:105-111` `ZombieView` 只有 `bool eating`，**没有 alive/dying**，`world.cpp:599-636` 又照发尸体 ⇒ 消费者无法区分"存活"与"正在淡出"，fade 实际不可观测 |
| M3 | 槽位分派语义 | 🟡（自认未改） | `world.cpp:124-126` `if (!slots.empty()) { runActionSlots(...); continue; }` | 有槽位就永不跑 family；而 `parity_report` 的 `wired` 仍按 family 字符串统计 ⇒ 147/147 虚高不变 |
| M4 | hash 补全 | 🟡 | `world.cpp:553-597` 已加 `actionTimer / skySunTimer_ / firstSkySunSpawned_ / cooldowns_ / speed / family / deathTick / shot.slow|pierce|splash / sun.expires` | 仍缺 `accumulator_`、`leaked_ / mowerKills_ / rejectedSpawns_`、`zombie.eatDps/type`、`slot.cooldownTicks/initialTicks` ⇒ hash 相等**不**代表统计口径一致（E8 两种局面 hash 不同仅因位置/时间不同） |
| M5 | 冒烟扩到 32 场景 + won | 🟡 | `engine_smoke.py` 26 world + 5 probe + `beach_23 win`；`check()` 仅校验 `minKilled/expectStatus/board` | E6 确认 32 场景、6 个 hash 与台账逐字一致；但 26 条世界场景**不断言状态**（baseline 里 memorytour 是 `lost` 也照样通过），且工具 `:153-154` 无条件覆盖自己的基线 |
| M6 | 测试收紧 | ❌ | `engine_test.cpp:554-564` 只读 `argv[1]/argv[2]`，`:559` usage 仍要 `<temp>`；`:115` 仍是 `status ∈ {playing,won,lost}` 恒真 | 新增的 4 条断言（`:123/:131/:136/:143-144`）确实有效，但 M6 点名的"未使用参数 + 恒真断言"两处都还在 |
| M7 | 双内核收敛 | 🟡 | `battle_view.hpp:9,30` 已用 `engine::World`/`world_->snapshot()`（`battle_view.cpp:221`） | 但 `CMakeLists.txt:35,58` 仍编 `pvz_simulation` 并链进主程序，`main.cpp:130` `--simulate` 仍驱动旧 `Battle` ⇒ 双内核仍在产物里 |
| L1 | `kMaxPlants` 生效 | ✅ | `world.cpp:267` | 与 H1 同点 |
| L2 | 区分 mowerKills/leaked/rejected | 🟡 | `world.cpp:219` `++mowerKills_`、`:182` `++leaked_`、`:100` `++rejectedSpawns_` | **但 `damageZombie` `:444` 照样 `++killed_`** ⇒ 推车碾死的仍计入 `killed`；E6 的 26 个无防守世界全部 `killed == mowerKills` 即证 |
| L3 | replay 输入校验 | 🟡 | `replay.cpp:42-53` 拒空 op/缺 type/负 collect id/回退 tick；`:72-74` 迟到写 `input_late` | `:32` `static_cast<uint64_t>(number(entry,"tick",0))` **负数 tick 静默回绕成 1.8e19** 且永不生效（无校验）；迟到输入仍被执行，只留事件 |
| L4 | 越界 spawn 可见 | ✅ | `world.cpp:100` 失败 → `++rejectedSpawns_` + `wave_spawn_rejected` | `grep wave_spawn_rejected` 命中；`summarize` 已输出 `rejectedSpawns` |
| L5 | playable 改推导、族表 fail-closed | 🟡 | `parity_report.py:236-241` `playable = level 引用 ∩ family 已实现`；`:92-105` 族表解析为空即 `raise` | 但 `:264-268 / :276-280 / :288-291 / :295-299 / :303-307` 五行的 `wired=0/playable=0` 仍是字面常量，而 docstring `:3-5` 仍写 "never from constants" |
| L6 | 构建目录可指定 | ✅ | `build_native.ps1:6-8` 加 `-BuildDir`，`:32-36` 解析（绝对或相对仓库） | E1/E3 用它成功隔离到 `build/auditor-verify*`；默认仍是共享 `build\native`（并发仍会撞 `CL.read.1.tlog`），台账已记录 CJK 路径 configure 失败需 `-BuildDir 'C:\pvzbuild\...'` |

统计：✅ 8 条（H1 H2 H3 H5 M1 L1 L4 L6）；🟡 8 条（B1 H4 M2 M4 M5 L2 L3 L5）；❌ 1 条（M6）；另 M3🟡、M7🟡 属于台账自认未修，此处仅登记现状。

## 4. 新代码复审

### 4.1 `native/src/engine/zombie_family.cpp`（41 行，CFE081BC5A5C）

- `:16-18` `constexpr std::array<Row,183> kRows{{ #include "zombie_family_table.inc" }}` + `:26-36` 二分查找。**已核对生成的 `.inc` 是升序**（183 行，0 处逆序），所以当前正确。
- 但**没有任何测试断言表是有序的**：一旦生成器换排序（或有人手工改一行），二分查找会静默返回空 ⇒ family 回落到内容 `behavior`/`walk`，行为漂移却全绿。建议在 `zombie_family_test.cpp` 加一条"表严格升序 + 行数 == `zombieFamilyCount()`"的断言。
- `:39` `zombieFamilyCount()` 与 `:16` 的模板长度 183 是两份真相（一个写死在类型里，一个在 `.inc`）；`.inc` 行数变化时前者会静默不匹配（编译期长度由 array 固定 ⇒ 多行直接编译错，少行补默认值 ⇒ 静默）。

### 4.2 `native/src/engine/registry.cpp`（4887E7C36D6C，pack 取值部分）

- `:18-25` 声明"pack Actions 槽位 → 内容 JSON → 常量"的三级来源，逐条常量标注 `// fallback: tuning constant, no pack evidence`——这套约定本身是好的，`damageOf/cadenceOf/windowOf/radiusOf/spawnOffsetOf` 都遵守。
- **`:438` 破坏约定**：`zombieGargantuar` 里 `world.damagePlant(p->id, 100000)`、`:439` `ticksOf(3.0)` 全是硬编码，内容里的 `extra.smash_damage=1500`、`imp_type=basic` 仍未取值。这与台账"S4 已改为 pack 取值"的整体叙述冲突，且 100000 让"砸扁"绕过任何血量（含未来护甲/减伤），属于**绕过战斗数值的旁路**。建议：走 `damageOf()`，拿不到 pack 值时退回 content `smash_damage`，再退回常量；并把 `imp_type` 接上 `spawnZombie`。
- `:486-496` `Registry::plantFamilies()/zombieFamilies()` 是 `:449-465` 两张表的**第二份手抄副本**。`parity_report.py` 解析的是 `:449-465`，运行时用的是 `:486-496`：任何一边增删族名都会让"wired 147/147"与真实分派脱钩。建议让 `plantFamilies()` 直接由表生成（同一份 `constexpr` 数组）。

### 4.3 `native/src/engine/action_runner.cpp`（FB92874BF2F1）

- `:184` `auto& slot = plant.slots[index];` 是一个**跨越 `world.removePlant(plant.id)`（`:218`/`:226`）与 `Registry` 行为调用（`:225`）的绑定引用**。当前安全只是因为 `removePlant` 只置 `alive=false`、不碰 `slots` 向量；一旦将来 `removePlant` 改成"立即"或 reap 提前，`:244` 的 `slot.remainingTicks = …` 就是 use-after-free。建议：每轮先拷贝所需字段到局部变量，或在 `removePlant` 后 `return`。
- `:88-91` `spawnOffsetColumns` 只取 `SpawnOffset.x`，`:86-87` 明确记录 y 不收——属于有意识的取舍，不是缺陷，但应在 parity 文档里标成"已知偏差"。
- `:244` `slot.remainingTicks = (fired || idlesOnCooldown(kind)) ? max(1, slot.cooldownTicks) : 1;` —— `cooldownTicks` 可能是 0（内容缺 cooldown 时 `midpoint` 走 `value_or`），`max(1, …)` 保底正确；无除零（`:96-104` `repeatTicks` 里对 `<= 0` 有分支）。

### 4.4 `native/src/catalog.cpp` boards 部分（3289178FF9A0）

- `:321-341` 应用 `board_sizes.json`，`:338` 让 per-level `board_rows/board_cols` 优先——语义正确。
- **`:345-347` 是静默降级**：`catch (const std::exception& e) { c.boardsNote = "boards=json-default (fallback: …)" }`。`--boards` 文件损坏/路径写错时，26 个世界全部退回 5×9，进程照常 exit 0，只有一句 note 字符串。E6 的 26 条世界几何断言正是因为这条静默路径才"永远过"。建议：boards 文件存在但解析失败 ⇒ 抛；仅"未请求"才允许 JSON 默认。
- `:362-364` 同一形状：`--pack` 损坏时 `rules=json (fallback: …)`，所有 pack 取值静默退回常量。

### 4.5 `native/tests/engine_test.cpp` 新断言（A7E4F2B7AA03）

新增断言质量总体**好**：`:131` 同 seed 两个 `World` 的 hash 相等、`:136` 引擎 rows/cols 必须等于 `catalog.boards` 表、`:143-144` `ran==26 && spawnedSome>=20`、`:185/190/191` 真的断言了 `ZombieState::eating` 与植物掉血（此前是 OR 大杂烩）、`:235-246` fly 族真的存在且不吃植物。这些能失败。
问题集中在两处：
- `:115` `status ∈ {playing,won,lost}` 依旧是**任何合法状态都通过**的恒真断言（26 世界真正的回归——某关从 `playing` 变 `lost`——抓不住；baseline 里 memorytour 就是 `lost`）。
- `:194` "the plant must stay the same entity" 只比较了 hp，没有比较 `id`/实体身份，断言名与内容不符。

### 4.6 `native/tests/*.cpp` 与 `tools/tests/*.py` 有效性

- `tools/tests` 共 9 文件 / 106 个 `def test_`，E7 实跑 `Ran 106 tests … OK`；**无** `assert True` 之类空断言。
- `tools/tests/test_parity_report.py:27-40` 把 `339/1127/1809/26` 写成字面期望值——这是**契约快照**而非推导，可以接受，但它同时意味着 `build_parity_matrix` 的口径错误不会被这套测试发现（测试与实现同源）。
- `native/tests/zombie_family_test.cpp:108-109`：`std::error_code ec; fs::create_directories(scratch, ec);` —— `ec` 从不检查，且 `scratch` 之后没再用（`argv[3]` 在 `:124` 取到后就没被消费）。既死代码又静默失败（见 §5）。
- 恒真/弱断言汇总：`engine_test.cpp:115`（状态三选一）、`:194`（只比 hp 的"same entity"）、`:166` `!judged.empty()`（只证明表里有这个名字，不证明族正确）。其余 `hash != 0`（`:118`）属无害健全性检查。

## 5. 静默失败点清单

| 位置 | 形态 | 影响 |
|---|---|---|
| `native/src/catalog.cpp:345-347` | `catch (std::exception) → note 字符串` | `--boards` 坏 ⇒ 26 世界静默退回 5×9，exit 0 |
| `native/src/catalog.cpp:362-364` | `catch (std::exception) → "rules=json (fallback…)"` | `--pack` 坏 ⇒ 所有 pack 取值静默退回常量，exit 0 |
| `native/src/main.cpp` `CatalogOptions.boardSizes` 默认空 | 不传 `--boards` 时不报错 | `--run-level content beach_23` 静默按 5×9 跑（E6 的 `beach_23` 之所以 6×9 是因为 smoke 显式传了 `--boards`） |
| `native/src/engine/replay.cpp:32` | `static_cast<uint64_t>(负 tick)` | 静默回绕成 1.8e19，该输入永不生效，无诊断 |
| `tools/check_all.ps1:100/120/134` | `Copy-Item -Force` 在失败判定之前执行 | 基线与矩阵在失败时被覆盖；`git ls-files native/generated` = 0 ⇒ 无可回收副本 |
| `native/tests/zombie_family_test.cpp:108` | `std::error_code ec` 未检查 | 目录创建失败也继续跑，且该参数根本未被使用（M6 同类复发） |
| `native/src/battle_view.cpp:76-82` | `reportOnce()` 打印一次后继续 | 美术资源缺失降级为占位图形——**设计如此**，登记以防被当成缺陷 |

（`native/src/*.cpp` 共 9 处 `catch`：`assets.cpp:44`、`catalog.cpp:28/345/362`、`dragonbones.cpp:19`、`main.cpp:162`、`save.cpp:57/244/266`。除上表两处外，其余为"资源/存档损坏可容忍"路径，未见吞掉关键错误。）

## 6. 诚实性审查（文档数字 vs 产物）

| 文档声称 | 实际 | 判定 |
|---|---|---|
| 32 场景 = 26 世界 + 5 定点 + 1 胜利（`PARITY_BASELINE.md:169`） | E6 实跑 32 行，构成一致 | ✅ |
| 6 个 hash（`0x810d…/0xa7ee…/0x54d0…/0x6c36…/0x072c…/0xde03…`） | E6 输出**逐字相同** | ✅ |
| 僵尸 class 族 183/183（`PARITY_BASELINE.md:212`、`PARITY_MATRIX.md`） | `.inc` 183 行 + 族分布 fly 8 / gargantuar 29 / jump 6 / steal 1 / summon 10 / walk 129 = 183 | ✅ |
| 植物 41/147、僵尸 47/55（`PARITY_BASELINE.md:176`） | `PARITY_MATRIX.md` 同行给 41 / 47；`playable` 现由"关卡引用 ∩ family 已实现"推导（`parity_report.py:236-241`） | ✅（但见 §4.2：`wired` 147 含 M3 未修的虚高） |
| 验证记录 `10/10`、`15/15`、`Ran 50 tests`、`check_all [ok]`（台账 20:40 段） | 现树是 **11/11**、**16/16**、**Ran 106 tests**；`check_all` 会写产物故未复跑 | ❌ **数字已过期/不可复现**（50 vs 106 差一倍） |
| "31 套模型" | 有出处但口径不同：`docs/reviews/deck_report.md:40,132` 写"111 株有模型植物只用了 31 套 actor / 独立形象 31/147（21%）"。该数字由 `work/obb_packages` 美术库统计得出，`native/generated/*.json` 里**没有**对应产物 | 🟡 有出处、非伪造；但属于"美术覆盖面"而非"引擎可玩性"，不能与 parity 的 41/147 混用于验收表述 |
| 台账 `M5 已修` | 26 世界场景无状态断言（§3 M5） | 🟡 表述过强 |

另：审核期间 `docs/reviews/2026-11-20-audit-fixes.md` 从 5643 B（21:24）被改写成 8190 B（21:27），追加了"21:30 队长追加"段落；台账是**可变文档**而非冻结记录，这与 H4 的"基线可被覆盖"是同一类问题——**没有任何一份验收物是不可变的**（`native/generated/*` 与 `docs/PARITY_*.md` 全部未纳入 git）。

## 7. 必须先修（blocker / high）

1. **[blocker] B1 跳跃族特征未实现且几何自锁** —— `registry.cpp:387/391/394`：落点 centre−0.45 落在起跳窗口 `[centre−1.4, centre+0.5]` 内，2 s 冷却只够走 0.6 列，净位移 0。E8 证明 jump 僵尸被地刺磨死（`mowerKills=0`）而同等 speed 的 walker 早已越过（`tick=2107`）；E9 证明对**可啃**植物它根本不跳。content 有 139 个关卡引用该僵尸。修法：落点改到 `centre - (kEatRangeCols + 0.2)`（< centre−1.35）并让冷却 ≥ 离开窗口所需时间，或直接置 `state=walking` 并跳过本次啃食判定；补一条"跳跃后 `z->x < centre` 且不再起跳"的用例。
2. **[high] 验收物没有不可变副本** —— H4 顺序已修但 `check_all.ps1:100/120/134` 仍无条件覆盖；`native/generated/*` 与 `docs/PARITY_MATRIX.md` 在 git 里是 0 个文件。任何一次 `check_all` 失败都会把"证据"换成"新基线"。修法：失败时写 `.rej`/备份并保留原文件；把三类基线纳入 git（或至少 `-AllowMatrixChange` 外禁止覆盖）。
3. **[high] boards / pack 双静默降级** —— `catalog.cpp:345-347` 与 `:362-364`：损坏的几何文件把 26 个世界悄悄退回 5×9，损坏的 pack 把全部数值悄悄退回常量，两者都 exit 0，只有一句 note 字符串。E6 的世界几何断言因此永远过。修法：显式请求的文件解析失败 ⇒ 抛；仅"未请求"才走默认。
4. **[high] `killed` 仍混算推车击杀** —— `world.cpp:444` 的 `++killed_` 对 `tickMowers` 的 `damageZombie(…,100000)`（`:218`）同样生效，`mowerKills_`（`:219`）只是重复计数。E6 的 26 个无防守世界 `killed == mowerKills` 即证据。修法：`damageZombie` 增加 `bool countsAsKill`/`KillSource` 参数，推车与 explode 走不同来源；`hash` 同时纳入三类计数器（M4 残留）。
5. **[high] audit 配置曾在 21:21–21:38 不可编译，而台账仍写 `[ok]`** —— `main.cpp:60` 的 `pvz::PlayScriptOptions play;` 落在 `#ifdef PVZ_ENABLE_DESKTOP`（`:80` 才开）之外，`-DPVZ_ENABLE_DESKTOP=OFF`（即 `-AuditOnly`）下 C2039（E1/E2）；现树已修（E3 11/11）。这说明"验证记录"是某一时刻的抽样，不是持续门禁。修法：把 `#ifdef` 上移到 `:57` 之前；并在 CI 里固定跑 audit + desktop 两套配置。

## 8. 附：本次未做/不可做

- `tools/check_all.ps1` 未执行（会重写 `native/generated/*`、`docs/PARITY_MATRIX.md`、`native/generated/world_diff.md`，超出本任务写范围）。因此台账的 `check_all [ok]` 无法在当前树上复现，只能静态审查其逻辑（§3 H4、§5）。
- `build/native` 未改；所有构建都落在 `build/auditor-verify*`，报告与探针产物均在 `build/` 下。
- 审核期间源码被并行编辑（21:27→21:41 之间 `world.cpp` 两次、`main.cpp` 两次变化），本报告的每条判定都以 §1 快照 hash 为准；若之后仍有改动，相关行号需重核。
