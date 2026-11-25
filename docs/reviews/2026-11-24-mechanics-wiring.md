# S5.13 关卡机制接线：传送带 / 初始场地 / 墓碑 / 保护植物

日期：2026-11-24 · 任务：t51 · 作者：wirer

这一轮把 `native/generated/level_mechanics.json`（1809 关，4.75 MB）里**能真正跑起来**的四类机制
接进内核，其余机制一律记成「未接线」并计数 —— 不实现也不装作不存在。

## 1. 改了什么

| 文件 | 改动 |
| --- | --- |
| `native/src/engine/mechanics.hpp`（新） | `LevelMechanics{initialPlants, initialGridItems, gravestones, conveyor, protect, unknownMechanics}`、`ProtectSpec{..., requiredSurvivors()}`、`MechanicTier{covered, unknown}`、`LevelMechanicsTable{load/shared/find/withConveyor/.../withUnknown}` |
| `native/src/engine/mechanics.cpp`（新） | 解析 sheet；`shared()` 复用 `plantfood.hpp` 的 `generatedDir()`；失败一律 `mechanics table: <path>: <reason>` |
| `native/src/engine/entity.hpp` | `PlantEntity::protectedPlant`；新增 `GridItemEntity{id,type,row,col,hp,maxHp,alive}` |
| `native/src/engine/world.hpp/.cpp` | `WorldOptions::mechanics`、开局铺场 `layInitialField()`、传送带 `refillConveyor()`/`plantFromConveyor()`、墓碑 `spawnGravestonesForWave()`、保护判定、`gridItemAt()`/`shovel()`/`explode()` 打网格物件、`hash()` 混入网格物件与手牌 |
| `native/src/engine/tuning.hpp` | `kGridItemHitPoints = 300`、`kConveyorHandSize = 6`（都是 `fallback: tuning constant, no pack evidence`） |
| `native/src/main.cpp` | `--run-level` 的 summary 增加 `conveyor`、`conveyorCards`、`initialPlants`、`gridItems`、`protectedPlants`、`protectFailures`、`mechanicUnknown[{kind,count,tier}]`、`mechanicUnknownKinds`、`mechanicUnknownInstances` |
| `native/CMakeLists.txt` | `pvz_engine` 加 `src/engine/mechanics.cpp`；注册 `mechanics` 测试（TIMEOUT 180） |
| `native/tests/mechanics_test.cpp`（新） | 8 段：表口径、传送带、初始植物、网格物件、保护任务、保护阈值、未知计数、`mechanics=false` 对照 |

## 2. 语义（每条都能在代码里指到行）

- **初始植物**：`constructPlant(..., chargeSun=false)` 建出来，**不扣阳光、不进 `sunSpent`、不发 `planted`**，
  发 `initial_plant`；保护目标是同一套铺法加 `protectedPlant`，发 `protect_plant_placed`。
- **传送带**：有 conveyor 的关卡，`plant()` 走 `plantFromConveyor()`：不看卡组、不看阳光、不看冷却，
  只认手牌；种下后 `refillConveyor()` 补到 6 张（按 `weight` 做整数轮盘，`conveyorRng_` 独立于战斗 RNG）。
  卡组被 `conveyor.slots`（或 `changes[].add[]`）盖掉，`extra.seed_bank` 不再参与。
- **两者并存**：先铺初始植物，再发手牌 —— `beach_12`（6 株 lilypad + 5 张卡）是这条的实测样本。
- **墓碑**：`spawners.gravestone[]` 按 wave 落石，`gravestonesServedWave_` 记已发到的最高波，重放同一 tick 不会重发。
  墓碑是 `GridItemEntity`：占格（`plant()` 返回 `cell occupied`）、可被铲（`shovel()` 返回 true 并发
  `grid_item_removed`）、可被炸/被啃（`damageGridItem`）。
- **保护任务**（M1）：**存活数 < `mustProtectCount` 才判负**。`mustProtectCount` 缺失（`-1`）时，
  若 `failWhenProtectedPlantDies=true` 取保护株数兜底；`=0` 且 `fail=false` → 不因保护植物判负。
  失败发 `protect_failed{level,required,alive,...}` + `level_lost{reason:"protected_plant_died"}`，`protectFailures_` 计 1。
- **未接线机制**：`mechanic_unknown{level,mechanic,count,tier}` 在开机时一次性发出，按 kind 聚合，
  CLI 直接可见。

## 3. 三个容易报错的数，说清楚

sheet 的 `counts` 块数的是「声明了模块的关」，内核数的是「能真正建起来的关」，两者不等：

| 口径 | 数 | 差在哪 |
| --- | --- | --- |
| 声明 conveyor | 350 | 含 `dark_33`、`frontyard_173`：既无 `slots` 也无 `changes` |
| 能建卡槽 | **348** | 349 = 350 − 2；`lostcity_67` 只有 `changes[].add[]`，是合法来源，已接（否则只有 345） |
| 声明 initialGridItems | 690 | `placements[]` 非空 466 关 + 只在 `gravestones.objects[].forceSpawn[]` 里点名 117 关 = **583** |
| 无名网格物件 | 629 是错口径 | 67 关 / 645 条 `forceSpawn` 的 `type` 是 null（`dark_63`、`dino_13`…），记成 `initialGridItems.unresolved` |
| 声明 gravestone | 353 | 1211 个 wave；其中 **27 个 wave 无 `spawnPositionsPool`**（18 关，13 关是全 wave 都没有）→ 记 `spawners.gravestone.unpositioned` |
| 未接线关数 | **868** | 826（tide/mutators/boardGrid/八种 spawner）+ 67 + 18 − 重叠 |

`spawners.jittered` 判为 **covered** 而不是 unknown：它的 `waves`/`objects` 就是普通波次表，波次系统本来就按
`director` 发（1615 关全部走同一条路径）。判据写在这里，不留给下一个人猜。

## 4. CLI 实测（`--run-level ... --seconds 40`）

```json
{"level":"beach_12","conveyor":true,"conveyorCards":["chomper","bowlingbulb","bowlingbulb","bowlingbulb","bowlingbulb","bowlingbulb"],"initialPlants":6,"gridItems":0,"protectedPlants":0,"protectFailures":0,"mechanicUnknown":[{"count":1,"kind":"events","tier":"unknown"},{"count":5,"kind":"spawners.beach","tier":"unknown"}],"mechanicUnknownInstances":6,"mechanicUnknownKinds":2,"status":"playing","sun":550,"tick":2400,"hash":"0x88252f665b9b7b68"}
{"level":"beach_20","conveyor":false,"initialPlants":0,"gridItems":5,"mechanicUnknown":[],"mechanicUnknownInstances":0,"status":"playing","sun":550,"tick":2400,"hash":"0x86f7d9827cabe743"}
{"level":"beach_14","conveyor":false,"initialPlants":10,"gridItems":0,"protectedPlants":5,"protectFailures":0,"mechanicUnknown":[{"count":1,"kind":"events","tier":"unknown"},{"count":8,"kind":"spawners.beach","tier":"unknown"}],"status":"playing","sun":550,"tick":2400,"hash":"0x30c4f098dea7e710"}
```

`beach_14` 的 10 株 = 5 初始植物 + 5 保护目标，全部不计阳光（`sun` 仍是开局的 550）。

## 5. 门禁

| 门 | 结果 |
| --- | --- |
| audit `C:\pvzbuild\mech1` | **25/26**，`mechanics` 绿；红的是 `catalog`（见下） |
| desktop `C:\pvzbuild\mech-desk` | **35/35 全绿**，`DESKTOP_EXIT=0` |
| `python tools/engine_smoke.py` | `SMOKE_EXIT=0`，32 场景 / **11 条哈希变化**（未写基线） |

`catalog` 的红**不是本轮的**：`C:\pvzbuild\flow1`（t45）、`C:\pvzbuild\drag1`（t49）两个旧二进制跑同一条命令
同样报 `FAIL overlapping mode counts`，说明是这之后 content/fixture 侧的改动或期望值漂移，二进制无关。
desktop 配置里同一条用例是绿的，两种配置参数不同，需要 content 侧的同学确认。

## 6. 冒烟 11 条变化的成因

`world <world>` 探针用的是每个世界 index 最小的关卡，这一轮起它们**不再空场**：

- `beach/dark/future/heian/iceage/lostcity/muji/pirate`（8 条）：开局有初始植物或网格物件，hash 变、状态仍 `playing`。
- `renai`：`renai_1` 是保护任务（5 株全保），空脚本跑 40 s 里被啃掉一株 → `protect_failed` → `lost`（tick 3364）。
  这是**新语义正确的结果**，不是回归：不种植物就该输。
- `frontyard_6 5x9`、`beach_23 win`：网格物件/初始植物的 hash 变化，胜负不变（`beach_23` 仍 tick 1536 赢）。

基线 `native/generated/engine_smoke.json` **没有**由我覆盖 —— 它要把这 11 条一起接收，属于收口动作。

## 7. 反向探针

1. **保护阈值改成「任一株死即输」**（`if (required > 0 && alive < required)` → `if (required > 0)`）：

   `mechanics test failed: losing one of five must not lose a mission that requires four, got: lost`

2. **传送带恢复扣阳光**（`constructPlant(type, row, col, false)` → `true`）：

   `mechanics test failed: a belt card must not cost sun, sun=525`

两处还原后 `world.cpp` sha256 `30831B53FA222BA46ED69588F1D1CCA06071F8119A27DDED6908E11EA82C19A4`，
`PROBE_` 残留 0，audit 回到 25/26。

## 8. 数据自身的两个坑（都记成事件，没有悄悄放过）

- **`egypt_74`**：保护目标列了 5 条却只落在 3 个格子上（(3,2) 重复三次），`mustProtectCount=4`。
  内核只摆得下 3 株，另 2 条发 `protect_plant_unplaced` 并计数（`unplacedProtectedPlants()`）。
  这关因此在数据层面就是打不赢的 4/5；我没有把它偷偷放宽成 3/3，`mechanics_test` 就是按「一株死即 lost」断言的。
- **27 个无位置墓碑 wave**：sheet 只给了池子不给格子，原版按棋盘现算。内核无法凭空放，记
  `spawners.gravestone.unpositioned`（18 关，其中 13 关每个 wave 都这样）。

## 9. 越界改动（已申报）

- `native/tests/engine_test.cpp` 的 `testPackOnlyPlant`：它用 `beach_23` + 清空卡组测「pack-only 植物能种」，
  而 `beach_23` 现在是传送带关，`plant()` 会走手牌。给它加了 `WorldOptions options; options.mechanics = false;`
  并注释原因 —— 该用例测的是卡组之外的种植路径，与关卡机制无关。
- `native/tests/s5_boss_test.cpp` 的三个 `--boss off` 钉死哈希：`beach_19` 现在开局有 3 株初始植物，
  `egypt_14` / `mausoleum_40` 各有自己的场地机制，旧哈希（S5.8 记录）不再适用。新值
  `beach_19 0xd19e8983839045d1`、`egypt_14 0x59d4f87dd42ec2f4`、`mausoleum_40 0x483a1e822b54aa7d`，
  用例注释写明了为什么重钉。它仍保证「关掉 boss 后 boss 不再参与」。

## 10. 顺手抓到的一个 C++ 坑（`class` vs `struct` 前向声明）

t49 里我在 `drag_plant.hpp` 写了 `class Catalog;`，而真身是 `struct Catalog`（`catalog.hpp:85`）。
MSVC 按**前向声明的 tag** 修饰符号（`?dragRulesFor@ui@pvz@@YA?AU…@AEBV Catalog…` vs `AEBU Catalog…`），
于是 `pvz_launcher.lib` 里定义的是 `V` 版、desktop 的两个 TU 期待 `U` 版，链接期 `LNK2019`。
audit 那边两个 TU 都只见到 `class`，反而「恰好」链接通过 —— **编译通过、语义靠巧合**。
教训：跨 TU 的前向声明必须和定义的 tag 一字不差；`mechanics.hpp` 里因此只包含 `catalog.hpp`，不做前向声明。

## 11. 还没有的

- `events`（tide/frost/strength）、`mutators`、`boardGrid`（mold colonies 的格子规则）、
  `spawners.beach/dino/fish/grid/ground/portal/spider/storm` 八种刷怪器：全部只计数，没实现。
- 传送带的 `dropDelayConditions`（延迟与每次包裹数）没跑，现在是一张就补一张。
- 墓碑的初始 `initialGridItems.gravestones`（开局就立着的那些）与掉落石块分开处理，前者已摆、后者按 wave 落。

## 12. 保护目标容量不足（T59 补充）

`protectThePlant` 的判负只在**植物死亡路径**（`World::damagePlant`）读阈值，开局与胜利路径从不问
「这关到底摆得下几个目标」。于是有 11 关开局就欠容量，其中 6 关一个目标都摆不下：那 6 关的死亡路径
永远不会触发，保护判定等于静默空转 —— 玩家什么都不做也是过。

### 12.1 改了什么

| 文件 | 改动 |
| --- | --- |
| `native/src/engine/world.hpp` | 新增 `int protectCapacityShortfall() const`（欠几个，0 表示不缺）与成员 `protectCapacityShortfall_` |
| `native/src/engine/world.cpp` | `layInitialField()` 摆完保护目标后比较 `requiredSurvivors()` 与实摆数；`placed < must` 时发 `protect_capacity_shortfall{level, placed, must, delta}` |
| `native/src/main.cpp` | `--run-level` 只在**该关有保护任务**时输出 `protectPlaced` 与 `protectCapacityShortfall`；其他关卡键集不变（冒烟基线与逐字节对比都靠这一点，不靠眼看） |
| `native/tests/mechanics_test.cpp` | 新增 `testProtectCapacityShortfall`：`egypt_74`（3/4、delta 1、且三株不死能赢）、`carnival_79`（0 目标、delta 等于整关要求）、`beach_88`（够用，不发）、`beach_14`（5/5 正好，实测数量相等——`<` 不许漂成 `<=`） |

这是**报告，不是改规则**：欠容量的关照样开打，`egypt_74` 三株都不死时照样赢（测试真跑 `clearedWaves`
后 `step()` 到 `won`，不是只看事件）。变的只是「欠了多少」这件事从不可见变成可数。

### 12.2 11 关清单（`placed / must / delta`）

| 关卡 | placed | must | delta |
| --- | --- | --- | --- |
| `carnival_23` | 3 | 6 | 3 |
| `carnival_79` | 0 | 1 | 1 |
| `carnival_81` | 0 | 3 | 3 |
| `chinesegarden_57` | 0 | 3 | 3 |
| `egypt_74` | 3 | 4 | 1 |
| `frontyard_51` | 5 | 6 | 1 |
| `frontyard_53` | 0 | 2 | 2 |
| `lostcity_45` | 2 | 8 | 6 |
| `lostcity_67` | 0 | 1 | 1 |
| `sky_31` | 0 | 5 | 5 |
| `sky_46` | 5 | 10 | 5 |

前 6 行里 `delta == must` 的六关（`carnival_79`、`carnival_81`、`chinesegarden_57`、`frontyard_53`、
`lostcity_67`、`sky_31`）就是「保护判定永远不触发」的那批：目标格子先被 `initialPlants` 占了，
`place()` 只发 `protect_plant_unplaced` 而不落株。数字复算方式与 `layInitialField` 一致（先铺
`initialPlants`、再铺保护目标、同格跳过），没有按 `counts` 块猜。

### 12.3 CLI 实测

```text
egypt_74   protectPlaced=3 protectCapacityShortfall=True   protectedPlants=3 protectFailures=0
carnival_79 protectPlaced=0 protectCapacityShortfall=True  protectedPlants=0 protectFailures=0
beach_88   protectPlaced=5 protectCapacityShortfall=False  protectedPlants=5 protectFailures=0
frontyard_1 <absent> <absent>                              protectedPlants=0 protectFailures=0
```

### 12.4 门禁与探针

- audit `C:\pvzbuild\cap1`：`100% tests passed, 0 tests failed out of 27`，`AUDIT_EXIT=0`。
- desktop `C:\pvzbuild\cap-desk`：`100% tests passed, 0 tests failed out of 36`，`DESKTOP_EXIT=0`。
- 冒烟：`python tools/engine_smoke.py --exe 'C:\pvzbuild\cap1\Release\PvZ2SHUTTLE.exe'` → `SMOKE_EXIT=0`，
  32 场景与 **T54 二进制**（`build/engine_smoke.rew.json`）**0 条差异**，与仓库基线
  `native/generated/engine_smoke.json` 也是 **0 条**。事件不进 `hash()`，规则也没动，所以一条都不该变 ——
  这是预期，而不是「恰好没测到」。
- 反向探针：把 `layInitialField` 的比较写成 `protectedPlants_ <= mustProtect` →
  `mechanics test failed: an exact fit is not a shortfall`，`96% tests passed, 1 tests failed out of 27`，
  失败项 `mechanics`。还原后 `native/src/engine/world.cpp` sha256
  `62B005DACC59A41066629642C5720A88E79CADF48A3D7787974419BF96DB900E`，`PROBE_` 残留 0，audit 复绿。
