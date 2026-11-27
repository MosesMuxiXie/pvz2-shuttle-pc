# A4：未接线机制第二波（tide / frost / boardGrid / maxSun）

- 任务：t88（A4），attempt `deadcefa-d5ff-4c79-8915-71086eca4809`
- 数据源：`native/generated/level_mechanics.json`（只读，未改）
- 写作用域：`native/src/engine/{world.cpp,world.hpp,mechanics.cpp,mechanics.hpp}`、`native/src/main.cpp`（仅 summarize）、`native/tests/mechanics_test.cpp`、`native/CMakeLists.txt`、本文档
- 越界申报：`native/src/engine/tuning.hpp`（新增一个常量，见 §8）

## 1. 一句话结论

`events`（tide / frost）、`boardGrid`、`mutators.maxSun` 三类已真正接进内核并用数据驱动；`LevelMechanicsTable::withUnknown()` **446 → 293**；剩下仍计 unknown 的只有两件：`spawners.spider`（没有 spider 实体）与 13 关挑战包装 `mutators`（表里没有乘子）。0/1 的 boardGrid 矩阵按「数据」接线，**没有**被当成玩法规则。

## 2. 三个数必须分清

| 数 | 是什么 | 谁算的 |
| --- | --- | --- |
| **446 → 293** | `LevelMechanicsTable::withUnknown()`：有至少一条 unknown 行的关卡数（含 spawner 行级 unknown，如 `spawners.grid.unscheduled`） | 表 API，测试里断言 |
| **123 / 49 / 8** | `withEvents()` / `withBoardGrid()` / `withSunCap()`：真的带这三种机制的关卡数 | 表 API，测试里断言 |
| **118 / 13** | 接线后仍计 unknown 的**关卡数**，按 kind 去重：`spawners.spider` 118 关、`mutators` 13 关（挑战包装） | python 镜像统计 |

「284 关 → 131 关」是我按 kind 去重后的口径（284 = 接线前有 unknown 的关卡数）；它与 `withUnknown()` 不是同一个定义，两个数都写在这里，避免以后对不上账。

## 3. 三类机制在数据里长什么样

### 3.1 events：tide 与 frost

- 123 关的 `events` 键集恒为 `{frost, strength, tide}`；`strength` 是**派生量**（`tools/contentc/level_extra_rules.py` R07：Σ|ChangeAmount|），不是原版字段。
- `tide`（60 关）：`{alias, wave, changeAmount, changeType: "absolute"}`。`beach_2` wave1→列 6、wave2→列 3；`beach_10` wave 2..9 且列 = 波号。
- `frost`（64 关，1 关与 tide 同时有）：`{alias, wave, winds:[{direction:"left"|"right", row}]}`。原版是 `FrostWindWaveActionProps`，`Row = -1` 表示整行；`iceage_25` wave1 推行 {0,2,3,4}，全程 10 波。
- **`memorytour_1` 是混合样本**：5 条 frost 行里 2 条有 wave（3、5），10 条 tide 行里 6 条有 wave、**4 条 wave 为 null** —— null 的行没有「什么时候发生」的依据，计 `events.tide.unscheduled`，不猜。

### 3.2 boardGrid

- 49 关，**全部 width 9 / height 5，只有一张 `rows[5][9]` 的 0/1 矩阵，没有多阵型**（`beach_94` alias `MoldColonies`，非 0 单元 24 个）。
- alias 家族：`MoldColonies` 16、`moldcolony` 11、`MoldLocationsCustom` 2、`Column0_To_Column0` 5 等；**mold 家族多数是传送带关**（49 关里 42 关不是传送带关，但 mold 那批里相当一部分是）。
- **0/1 的语义原版没有字段说明**（`level_extra_rules.py` R02 原文：「0/1 的含义原版没有字段说明，产物不翻译」）。所以这里只做两件事：把矩阵搬进 `World`（可查、可数、进事件流）、拒绝不存在的层号。**没有**据此禁止种植——那会是一条数据里没有的规则。

### 3.3 mutators

- 21 关只有两种形状：
  - `LevelMutatorMaxSunProps.maxSunOverride` —— **8 关**：carnival_51 275、carnival_82 200、chinesegarden_38 800、dino_38/40/41 500、lunarrainbowmarket_3 200、lunarrainbowmarket_62 50。
  - `LevelMutatorModuleProperties` —— 13 关，`tables[]` 里 `ModuleType` 只有 `bonuschallenge`(33) / `mainchallenge`(15)，Modules 是 `LevelTimer`、`BeatTheLevel`、`PlantsLost1..3`、`KillZombies1..3`、`SunProduced`、`ReachTheScore`、`ProtectThePlant` 这类**挑战目标**。
- 数据里**根本没有**速度/血量/伤害/阳光产出乘子，所以只接 `maxSun`；13 关挑战包装继续计 unknown `mutators`（`mutators.maxSun` 已标 covered）。

## 4. 引擎形态

- `native/src/engine/mechanics.{hpp,cpp}`：`TideChange`、`FrostWind`、`BoardGridSpec{cells, marked()}`、`EventsSpec`、`MutatorSpec`；`LevelMechanics` 增 `events / boardGrid / mutators`；表增 `withEvents() / withBoardGrid() / withSunCap()`。解析在 `readEvents` / `readBoardGrid` / `readMutators`，`kCovered` 追加 `events.tide`、`events.frost`、`boardGrid`、`mutators.maxSun`。
- `native/src/engine/world.{hpp,cpp}`：
  - 构造：`sun_cap_active{level,cap}`，开局 `sun_` 高于上限时 clamp 并发 `sun_capped{level,from,to}`（8 关里 7 关开局就超上限）；`applyBoardGrid(0)`。
  - 波次：`tickWaves()` 在 `scheduleSpawnersForWave(...)` 之后调 `applyWaveEvents(spawnedWaves())`；函数开头 `if (wave <= eventsServedWave_) return;` —— **这条守卫是必需的**：没有它 `tickWaves` 每 tick 都问一次，60 s 的 run 里 tide 动了 1285 次、frost 推了 2503 次（已实测）。
  - tide：`tideColumn_` 更新 + `tide_changed{level,wave,column,type}`。
  - frost：按 `winds` 的行过滤（`-1` = 整行），把该行僵尸的 `x` 推 `±0.5` 列（不小于 0），发 `frost_wind{level,wave,rows,direction,pushed}`。
  - 阳光：`addSunToBank(int)` 收敛上限；`collect()` 与砸罐子取阳光都走它。
  - `hash()` **没有**因本轮改动换口径：新状态是「关卡数据 + 已到波次」的纯函数，事件流已可观测；这样避免重钉 s5_boss 的 hash pin。

## 5. CLI 原文（`--run-level ... --seconds 60 --audio-off`）

| 关卡 | 改前（T80 二进制） | 改后 |
| --- | --- | --- |
| `beach_10` | `mechanicUnknown=[{events,1}]` | `[]`，`tideColumn=2`、`tideChanges=3` |
| `beach_2` | `[{events,1}]` | `[]`，`tideColumn=3`、`tideChanges=3` |
| `iceage_25` | `[{events,1}]` | `[]`，`frostWinds=3` |
| `beach_94` | `[{boardGrid,1}]` | `[]`，`boardGridMarked=24` |
| `carnival_51` | `[{mutators,1}]` | `[]`，`sunCap=275`、`sun=275` |
| `carnival_82` | — | `[]`，`sunCap=200`、`sun=200` |
| `beach_21` | `[{events,1},{mutators,2}]` | `[{mutators,2}]`，`tideColumn=3`、`tideChanges=5` |
| `carnival_1` | `[{spawners.spider,2}]` | `[{spawners.spider,2}]`（按设计仍是 unknown） |
| `memorytour_1` | `lost@7000`，`[{events,1}]` | `playing@7200`，`[{events.tide.unscheduled,4}]`，`frostWinds=2` |

`memorytour_1` 的状态变化是可解释的：wave 3 / wave 5 的 frost 把对应行僵尸往回推了 0.5 列，120 s 窗口里没被打穿 → `playing` 而不是 `lost`；4 条 null-wave 的 tide 行按设计计 unknown。

## 6. 测试（`native/tests/mechanics_test.cpp`，五段，排在我自己的表断言之后）

| 用例 | 断言 |
| --- | --- |
| `testTideFollowsTheWaves` | `beach_2`：起手 `tideChanges()==0`；跑到 wave≥2 后 `columns.front()==6`、`tideColumn()==columns.back()`、事件数与波次数一致 |
| `testFrostWindPushesItsRows` | `iceage_25`：两个探针僵尸（row0 / row1），wave 1 落地那一步 row0 的 `x` 变大、row1 不变；`frostWinds()` 与 `frost_wind` 事件数相等；direction 为 right |
| `testSunCapStopsTheBank` | `carnival_82`：`sunCap()==200`、开局 `sun()==200`、`sun_capped` 恰好 1 次；种两株向日葵（中间步过 700 tick 冷却）后 6000 tick 内反复 `collect`，峰值不超过 200 且收尾正好 200 |
| `testBoardGridMaskIsCarried` | `beach_94`：`boardGridIndex()==0`、`boardGridMarkedCells()==24`（与表求和一致）、`boardGridMarked(0,0)` 一致、`applyBoardGrid(1)==false` 并发 `board_grid_rejected`；另建 `carnival_7`（同 mask、普通种子库）在标记空格种 deck 首卡**必须成功** —— 用行为证明 0/1 不是规则 |
| `testWiringLeavesOnlyTheDocumentedGaps` | `beach_2` 无 unknown；`beach_21` 仍有 `mutators`；`carnival_1` 仍有 `spawners.spider`；`beach_94` 不再有 `boardGrid` |

`testTableShape` 的计数改为：`withUnknown()==293`，并新增 `withEvents()==123`、`withBoardGrid()==49`、`withSunCap()==8`。`testUnknownMechanicsAreCounted` 的 `beach_10` 口径翻转成「unknown 为空 + `events.tide` covered + `spawners.spider` 仍是 unknown」。

## 7. 两条反向探针（原文）

**探针 A：tide 行永不生效**（`applyWaveEvents` 的 tide 循环插 `if (true) continue;`）

```
mechanics test failed: beach_2's tide must arrive with its waves
```

**探针 B：上限不收敛**（`addSunToBank` 的 clamp 前加 `false &&`）

```
mechanics test failed: the bank must never pass the cap, peaked at 400
```

两条都已还原；`Select-String PROBE_T88` 在源码与测试里 **0 命中**，`mechanics tests passed`。

## 8. 门禁

| 门 | 结果 |
| --- | --- |
| audit `pwsh -NoProfile -File tools/build_native.ps1 -AuditOnly -BuildDir C:\pvzbuild\a4-aud`（最后一次） | **37/38 通过**，唯一红 `progress`（`progress test failed: no mower was used, so the mower goal must pass`，`progress.*` 我没动过）；`mechanics` 绿 |
| desktop `pwsh -NoProfile -File tools/build_native.ps1 -Desktop -BuildDir C:\pvzbuild\a4-desk` | **52/54 通过**；当时红的 `catalog`（`FAIL real catalog counts`，T80 老二进制同样红）与 `progress`，`catalog` 随后已被其负责人修好，最后一次 audit 里只剩 `progress` |
| `python tools/contentc/mechanics.py --check` | `EXIT=0`（`levels=1809 ... withEvents=123 withMutators=21 withBoardGrid=49 unknowns=10`） |
| 冒烟 `python tools/engine_smoke.py --exe <a4-desk exe> --out work\_smoke_mech2.json` | 32 场景，`SMOKE_EXIT=0`。**相对 T80 二进制只变 1 条**：`world memorytour`（`memorytour_1`，见 §5 解释）。对照仓库基线 `native/generated/engine_smoke.json` 是 2 条，多出来的 `beach_23 win`（`0xb2a22229f25b92e6 → 0xa47bd864b1d332bf`、tick 1599→1597）**用 T80 老二进制跑同样是新值** → 基线漂移，不是我这一轮 |
| 截图确定性 | `--play-script content frontyard_1 --script native/tests/scripts/frontyard_1_basic.json --seconds 1` 与 `--play-script content kongfu_1 --seconds 20`：T80 与 T88 二进制**逐字节相同**（`AC13533F…D17EC9` / `FCE15C5C…6867D`）。菜单截图在两版之间变了（`31949B 37F75744…` → `43630B 8BC2A933…`），那是别人在这两个构建之间改的菜单/徽章代码，我的 diff 不碰 `menu_view` |

## 9. 越界申报

1. **`native/src/engine/tuning.hpp`**：新增 `inline constexpr double kFrostWindPushColumns = 0.5; // fallback: tuning constant, no pack evidence`。任务书要求「乘子的作用点写进 tuning」，但该文件不在写作用域列表里；frost 表只给方向与行、**不给距离**，所以距离只能是一个带注释的回退常数。
2. **`native/CMakeLists.txt`**：本轮开始时他人新增的 `src/engine/plant_levels.cpp` 尚未注册，`world.obj` 因此报 `PlantLevelTable::shared/find`、`clampPlantLevel`、`leveledValue`、`SpawnOffsets::*` 一批 LNK2019；我先补了这一行，后来 B1 自己也注册了，形成重复 → **已删掉我自己加的那行**，现在文件里只有 B1 的那一份。
3. `mechanics_test.cpp` 是与 auditor（t89）共享的文件：我只动了自己五段与它们的调用点，并把自己的五段排在 `testTableShape()` 之后，这样探针一红就能确认红句出自我的断言。

## 10. 没做的 / 诚实的边界

- **`spawners.spider`（118 关）仍然 unknown**：`content/zombies.json`(55) 与 `content.pack`(1127) 里都没有 spider 实体，凭空造一个通用僵尸是数据没要求的规则。
- **13 关挑战包装 `mutators` 仍然 unknown**：`LevelMutatorModuleProperties` 里只有挑战目标模块，没有乘子数值；把「bonuschallenge 的 33 行」当成倍率会是编造。
- **tide 只处理 `changeType == "absolute"`**：相对型需要知道「从哪开始」，表里没有；相对型会记 `events.tide.relative`。
- **水位不致死**：数据没有「淹到第几列开始扣血/判负」的字段，所以内核只记录水位线与事件，不发明溺水伤害。
- **frost 的推动距离是回退常数**（§9.1），表里只有方向与行。
- **boardGrid 的 0/1 语义仍未解**：内核只携带矩阵、可查可数；是否「该格有霉菌所以不能种」需要原版字段，而不是猜。

## 11. 给后续的提示

- `eventsServedWave_` 那条守卫不能删：`tickWaves()` 每 tick 都会问，删掉就会得到 1285 次 tide / 2503 次 frost。
- 别用 pwsh 的 `-replace` 写多行 C++ 探针：反引号 `` `n `` 在单引号字符串里是字面量，会把注释和代码粘成一行，接下来是 `kEatRangeCols` 之类的连锁报错。用 `edit`。
- mold 家族大量是**传送带关**：`World::plant()` 对它们返回 `"not on the conveyor"`，想在 mold 关验种植语义要用 `carnival_7` 这类同 mask 的普通关。
- OneDrive 上 `edit` 偶发 `ReplaceFileW EIO (Win32 32)`，原样重试一次就成功。
