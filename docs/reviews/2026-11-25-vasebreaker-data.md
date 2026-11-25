# 砸罐子（VaseBreaker）内容数据 · 2026-11-25

编译产物：`native/generated/vasebreaker.json`（186,116 字节，sha256 `adf41709daa490a927dfcf6193602b2517c315ee42c22f401d656e61d5c043df`）
编译器：`tools/contentc/vasebreaker.py`　测试：`tools/tests/test_vasebreaker.py`（18 例）

数据来源全部是随包发布的 460.9 OBB 解包目录 `work/obb_packages`，**没有**任何单元格来自推测或从客户端补写。

---

## 0. 结论摘要

| 问题 | 答案 | 依据 |
| --- | --- | --- |
| 砸罐子关卡有几关 | **47 关**，覆盖 **18 个世界** | `content/levels/*.json` 的 `extra.vasebreaker == true` |
| 罐表在哪张原版表 | **`VaseBreakerPresetProperties`**（alias `VaseBreakerProps`），46 条 / 46 个包，全部内嵌在关卡包里 | `pkg_*_LevelDefinition.json` 的 objects |
| 罐子总数 | **1435 个**（僵尸罐 788 / 植物罐 617 / 收集物罐 30），共 459 条 `Vases[]` 记录 | 46 张罐表逐条求和 |
| 有没有缺关 | **1 关没有罐表**：`frontyard_166`（pkg_0302）—— 该关是**无尽模式**，用的是 `VaseBreakerEndlessProperties`（3 段配方），不是固定罐表 | 见 §5.1 |
| 原版给不给逐罐坐标 | **不给**。罐子只有「类型 + 数量」，落位靠 `MinColumnIndex..MaxColumnIndex` 减去排除格后随机决定 | 见 §2.3 |
| 有没有计时 | **没有**。47 关全无 `TimeLimit`（全库该字段只出现在 `JoustGameModuleProperties` / `StarChallengeLevelTimerProperties`） | 见 §4 |
| 能不能只靠原版表实现 | **罐内容可以**（类型+数量+列区间+排除格全覆盖）；**初始阳光只有 4 关有**；**种卡清单只有 8 关有**；**计时/逐罐坐标原版没有** | §3 / §4 |

---

## 1. 口径与两处对任务描述的订正

### 1.1 类名订正

任务描述里写的 `VaseBreakerModuleProperties` **在 2117 个包里不存在**。实际存在的是：

| objclass | alias | 记录数 | 内容 |
| --- | --- | --- | --- |
| `VaseBreakerPresetProperties` | `VaseBreakerProps` | **46** | 罐表本体（见 §2） |
| `VaseBreakerArcadeModuleProperties` | `VaseBreakerArcade` | 1 | **objdata 为空 `{}`**，只是个开关 |
| `VaseBreakerFlowModuleProperties` | `VaseBreakerFlow` | 1 | **objdata 为空 `{}`** |
| `VaseBreakerEndlessProperties` | `TestVaseBreaker` | 1 | 无尽模式 3 段配方（`Stages[]`） |

`GridItemVaseProps`（`GridItemVaseDefault` / `GridItemVaseEgg` / `GridItemVaseFirework`，各 1 条）只有 `PopAnim*` / `HitRect*`，是**美术**不是内容，未进产物。

### 1.2 `extra` 不在 `level_mechanics.json` 里

任务描述说「`native/generated/level_mechanics.json` 已有的 `extra`」。实测**不成立**：

* `level_mechanics.json` 的 `levels[*]` 只有 8 个键：`boardGrid` / `conveyor` / `events` / `initialGridItems` / `initialPlants` / `mutators` / `protectThePlant` / `source` / `spawners`，**没有任何 `extra` 键**，`extra.vasebreaker` 在该文件里 0 命中。
* `extra` 只存在于 **`content/levels/*.json`**，且只有两种用法：`extra.vasebreaker`（bool）与 `extra.package`（包名）。

因此本工具直接读 `content/levels/*.json` 判定 47 关，再用 `extra.package` 定位包，不经 `level_mechanics.json`。

### 1.3 关卡身份

* 47 关 ↔ **47 个互不重复的包**（`pkg_0290`…`pkg_1880`），每包恰好 1 个 `LevelDefinition`。
* 关卡 key 直接用客户端 id（`beach_69` 这种），与 `content/levels` 双向一一对应（测试 `test_level_ids_match_content_flag_one_to_one` 断言两侧集合相等，且每关 `package` 与 `extra.package` 相同）。

---

## 2. 原版表结构

### 2.1 关卡对象 `LevelDefinition`（47 关的字段覆盖）

| 字段 | 出现关数 | 说明 |
| --- | --- | --- |
| `Modules` | 47 | 模块引用列表，见 §2.4 |
| `Name` | 47 | 本地化键（如 `[VASEBREAKER_BEACH_LEVEL_NAME_1]`），**不是**关卡 id |
| `StageModule` | 47 | 场景模块引用（`RTID(BeachStage@LevelModules)` → `BeachStage`） |
| `Loot` | 47 | 掉落表引用 |
| `Description` | 46 | |
| `IsVasebreaker` | **45** | 真布尔；`pirate_41` / `plantagenet_18` 上没有这个键 |
| `LevelNumber` | 42 | 世界内序号，与客户端 id 的数字**不等价** |
| `LevelPowerupSet` | 37 | 多为 `LevelPowerupsVasebreaker` |
| `FirstRewardParam` | 24 | |
| `StartingSun` | **4** | 见 §3 的 `initialSun` |
| 其它 | 1–11 | `MusicType` / `ZombieLevel` / `SuppressPlantfoodPurchase` / `VictoryModule` 等 |

### 2.2 罐表 `VaseBreakerPresetProperties`

46 条记录，字段覆盖：

| 字段 | 覆盖 | 语义 |
| --- | --- | --- |
| `Vases` | 46 | 罐内容列表，见 §2.3 |
| `MinColumnIndex` / `MaxColumnIndex` | 46 | 允许落位的列区间（0 基） |
| `NumColoredPlantVases` / `NumColoredZombieVases` | 46 | **彩色罐**（内容更好的罐）数量，是额外标记，不是罐子总数 |
| `GridSquareExcludelist` | **5** | 禁止放罐的格子 `{mX,mY}` |
| `GridSquareBlacklist` | **5** | 另一套禁止格；`egypt_57` 是空数组 |
| `VaseGridItemType` | **3** | 值为 `vase_firework`，烟花罐外观 |

### 2.3 `Vases[]` 条目形状

每条只有「判别键 + `Count`」，**没有 row/col、没有阳光数量**：

```json
{"Count": 4, "ZombieTypeName": "beach"}          // 僵尸罐
{"Count": 2, "PlantTypeName": "wallnut"}         // 植物罐
{"Count": 0, "CollectableTypeName": "plantfood"} // 收集物罐
```

* 收集物罐在 47 关里出现的类型**只有 `plantfood`**（29 条记录），没有阳光罐 —— 因此 `sunAmount` 只能留 `null`。
* 全部 459 条记录里，除 `Count` + 三个判别键外**没有任何额外键**（探针逐条检查过，"unusual preset entries" 为空）。
* 僵尸/植物 id 全部能在原版表里解析：僵尸 id 命中 `pkg_2115_ZombieType.json`（1125 个 distinct `TypeName`），植物 id 命中 `content.pack`（339 株），**悬空 0 条**。

产物里每条罐子保留 `row` / `col` / `sunAmount` 三个槽位并一律 `null`，同时在关卡 `unknowns` 里写明「原版没有该字段」，不做 0 填充。

### 2.4 47 关用到的模块（`Modules` 频次，按关卡内 `Modules` 引用计数）

`DefaultZombieWinCondition` 47、`VaseBreakerArcade` 46、`VaseBreakerProps` 46、`ZombiesDeadWinCon` 43、`CowboyRails` 7、`SeedBank` 6、`ChallengeModule` 5、`Gravestones` 5、`NewWaves` 4、`PiratePlanks` 4、`Tide` 3、`CarnivalDynamicBackground` 3、`StandardIntro` 3、`LevelEscalationModule` 2、`ConveyorBelt` 1、`TestVaseBreaker`（无尽）1、`LilypadPlacement` 1、`LastStand` 1、`ProtectThePlant` 1、`BeatTheLevel` 1、`DefaultSunDropper` 1、`ZombossBattle` 1、`ZombossIntro` 1、`FutureRails` 1、`FutureLinkedTileGroups` 1、`FutureNightBackground` 1、`GTAMowers` 1、`EgyptNightBackgroundEffects` 1、`PlantagenetDaylightBackground` 1、`LightModule` 1、`LightModule2` 1、`PenaconyAnim` 1、`LevelOfTheDayModule` 1、`PerkActivator` 1、`LevelDifficultyScaling` 1、`StarChallengeModule` 5。

一处**对象存在但未被 `Modules` 引用**的情况：`muji_24`（pkg_1810）包内有 `SeedBankProperties`，但其 `Modules` 列表只有 `ZombiesDeadWinCon / VaseBreakerArcade / VaseBreakerProps / DefaultZombieWinCondition`，**没有** `SeedBank`。产物以「包内对象」为准收录了它的种卡（1 株 `iceburg`），并在本节标注这层差异 —— 引擎若按 `Modules` 挂载会看不到它。

---

## 3. 逐关计数

列含义：`vaseCount` = 该关罐子总数（46 张罐表求和 = 1435）；`entries` = `Vases[]` 记录条数；`cols` = `Min..MaxColumnIndex`；`z/p/c` = 僵尸 / 植物 / 收集物罐数量。

| 关卡 | 世界 | 包 | StageModule | vaseCount | entries | cols | z | p | c |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| beach_69 | beach | pkg_0290 | BeachStage | 30 | 12 | 2..8 | 21 | 9 | 0 |
| beach_70 | beach | pkg_0291 | BeachStage | 30 | 11 | 2..8 | 18 | 10 | 2 |
| beach_71 | beach | pkg_0292 | BeachStage | 30 | 13 | 3..8 | 18 | 11 | 1 |
| carnival_66 | carnival | pkg_0372 | CarnivalStage | 40 | 8 | 1..8 | 40 | 0 | 0 |
| carnival_91 | carnival | pkg_0364 | CarnivalStage | 45 | 18 | 0..8 | 18 | 26 | 1 |
| cowboy_33 | cowboy | pkg_0293 | WestStage | 30 | 9 | 2..8 | 19 | 10 | 1 |
| cowboy_36 | cowboy | pkg_0294 | WestStage | 30 | 11 | 3..8 | 14 | 15 | 1 |
| cowboy_37 | cowboy | pkg_0295 | WestStage | 35 | 11 | 1..7 | 18 | 16 | 1 |
| dark_67 | dark | pkg_0296 | DarkStage | 30 | 8 | 2..8 | 19 | 11 | 0 |
| dark_68 | dark | pkg_0297 | DarkStage | 25 | 7 | 4..8 | 14 | 11 | 0 |
| dark_72 | dark | pkg_0298 | DarkStage | 25 | 7 | 4..8 | 14 | 11 | 0 |
| egypt_54 | egypt | pkg_0299 | EgyptStage | 30 | 7 | 3..8 | 18 | 11 | 1 |
| egypt_57 | egypt | pkg_0895 | EgyptNightsStage | 30 | 19 | 4..6 | 0 | 30 | 0 |
| egypt_59 | egypt | pkg_0300 | EgyptStage | 30 | 9 | 3..8 | 14 | 15 | 1 |
| egypt_61 | egypt | pkg_0301 | EgyptStage | 30 | 9 | 3..8 | 15 | 14 | 1 |
| frontyard_166 | frontyard | pkg_0302 | FrontLawnStage | — | 0 | — | 0 | 0 | 0 |
| frontyard_167 | frontyard | pkg_0309 | FrontLawnStage | 20 | 6 | 4..7 | 8 | 12 | 0 |
| frontyard_168 | frontyard | pkg_0310 | FrontLawnStage | 20 | 6 | 5..8 | 8 | 12 | 0 |
| frontyard_169 | frontyard | pkg_0311 | FrontLawnStage | 25 | 8 | 1..5 | 11 | 13 | 1 |
| frontyard_170 | frontyard | pkg_0312 | FrontLawnStage | 30 | 9 | 3..8 | 16 | 13 | 1 |
| future_37 | future | pkg_0303 | FutureStage | 30 | 8 | 3..8 | 13 | 14 | 3 |
| future_40 | future | pkg_0304 | FutureStage | 25 | 9 | 4..8 | 12 | 11 | 2 |
| future_44 | future | pkg_0305 | FutureStage | 30 | 8 | 2..7 | 11 | 16 | 3 |
| future_46 | future | pkg_1641 | FutureOriDMGStage | 35 | 14 | 2..8 | 21 | 14 | 0 |
| future_54 | future | pkg_1643 | FutureOriDMGStage | 37 | 13 | 2..8 | 20 | 16 | 1 |
| future_65 | future | pkg_0741 | FutureOriFunTimeStage | 36 | 12 | 2..8 | 20 | 15 | 1 |
| future_68 | future | pkg_0752 | FutureOriFunTimeStage | 35 | 17 | 1..7 | 17 | 17 | 1 |
| heian_2 | heian | pkg_1322 | HeianDMGStage | 30 | 9 | 3..8 | 16 | 13 | 1 |
| heian_9 | heian | pkg_1334 | HeianDMGStage | 30 | 9 | 3..8 | 16 | 13 | 1 |
| heian_28 | heian | pkg_0966 | HeianStage | 37 | 14 | 2..8 | 20 | 16 | 1 |
| kongfu_35 | kongfu | pkg_1396 | KongfuDMGStage | 30 | 13 | 2..7 | 16 | 14 | 0 |
| kongfu_76 | kongfu | pkg_1065 | JTTWStage | 35 | 15 | 2..8 | 21 | 13 | 1 |
| kongfu_83 | kongfu | pkg_0756 | KongfuFunTimeStage | 5 | 1 | 4..4 | 5 | 0 | 0 |
| losantosvice_21 | losantosvice | pkg_1097 | GTADMGStage | 35 | 13 | 2..8 | 21 | 14 | 0 |
| lunarrainbowmarket_50 | lunarrainbowmarket | pkg_0886 | LunarStage | 35 | 11 | 2..8 | 24 | 11 | 0 |
| lunarrainbowmarket_64 | lunarrainbowmarket | pkg_0837 | LunarDMGStage | 40 | 14 | 1..8 | 24 | 16 | 0 |
| lunarrainbowmarket_74 | lunarrainbowmarket | pkg_0841 | LunarStage | 35 | 13 | 2..8 | 17 | 18 | 0 |
| mausoleum_2 | mausoleum | pkg_0549 | RiftStage | 30 | 7 | 2..8 | 13 | 17 | 0 |
| modern_51 | modern | pkg_0878 | ChildStage | 35 | 10 | 2..8 | 23 | 12 | 0 |
| muji_24 | muji | pkg_1810 | RiftStage | 35 | 11 | 2..8 | 21 | 14 | 0 |
| pirate_41 | pirate | pkg_1557 | PirateBossStage | 35 | 1 | 2..8 | 35 | 0 | 0 |
| pirate_53 | pirate | pkg_0306 | PirateStage | 30 | 7 | 3..8 | 18 | 11 | 1 |
| pirate_54 | pirate | pkg_0307 | PirateStage | 30 | 9 | 3..8 | 15 | 14 | 1 |
| pirate_57 | pirate | pkg_0308 | PirateStage | 30 | 9 | 2..7 | 15 | 14 | 1 |
| plantagenet_18 | plantagenet | pkg_1576 | PlantagenetDaylightDMGStage | 35 | 10 | 2..8 | 21 | 14 | 0 |
| sky_52 | sky | pkg_0721 | PenaconyStage | 40 | 11 | 1..8 | 24 | 16 | 0 |
| steam_32 | steam | pkg_1880 | SteamUBStage | 30 | 3 | 3..8 | 6 | 24 | 0 |

分布：`vaseCount` 5×1 / 20×2 / 25×4 / 30×21 / 35×11 / 36×1 / 37×2 / 40×3 / 45×1（`frontyard_166` 无值）；世界分布 frontyard 5、future 7、egypt 4、pirate 4、beach/cowboy/dark/heian/kongfu/lunarrainbowmarket 各 3、carnival 2、losantosvice/mausoleum/modern/muji/plantagenet/sky/steam 各 1。

---

## 4. 未知与「原版没有」清单

产物里 `unknowns[]` 是全局汇总（7 类），每关的 `unknowns[]` 是同一批文本的实例。判定原则：原版没有该字段就写 `null` + 说明，**不写 0/false**。

| kind | 命中 | 性质 | 说明 |
| --- | --- | --- | --- |
| `timeLimit` | 47 | **原版没有** | 47 关全无 `TimeLimit`。全库 2117 包里该字段只出现在 `JoustGameModuleProperties`(4) 与 `StarChallengeLevelTimerProperties`(11) |
| `vasePlacement` | 46 | **原版没有** | `Vases[]` 只有类型 + `Count`；没有逐罐 row/col |
| `sunAmount` | 46 | **原版没有** | 收集物罐只给类型名（全部 `plantfood`），没有阳光数量字段 |
| `initialSun` | 43 | 数据缺失 | 只有 `frontyard_166`(0)、`muji_24`(0)、`pirate_41`(300)、`plantagenet_18`(200) 有 `LevelDefinition.StartingSun` |
| `seedBank` | 39 | 数据缺失 | 只有 8 关包内有 `SeedBankProperties` / `ConveyorSeedBankProperties`（其中 6 关 `SeedBank`、`steam_32` 用 `ConveyorBelt`、`muji_24` 有对象但 `Modules` 未引用，见 §2.4） |
| `preset` | 1 | 数据缺失 | `frontyard_166` 没有罐表（该关是无尽模式，见 §5.1） |
| `endless` | 1 | 口径说明 | 无尽配方已原样收进 `endless`，**没有**并进 `vases` |

关于「初始阳光」还有一个原版里的旁证：`kongfu_83` 的 `LastStandMinigameProperties` 写着 `StartingSun 14514`、`StartingPlantfood 0` —— 这是**LastStand 模块**的数值，与 `LevelDefinition.StartingSun` 不是同一条路径，本产物把它单独收在 `lastStand` 字段，没有混进 `initialSun`。

---

## 5. 特殊关卡

### 5.1 `frontyard_166`（pkg_0302）— 唯一没有固定罐表的关

* `levelNameKey` = `[VASEBREAKER_ENDLESS_LEVEL_NAME]`，`StartingSun 0`，`AddBonusStartingSun false`，`StageModule FrontLawnStage`。
* 包内没有 `VaseBreakerPresetProperties`，取而代之的是 **`VaseBreakerEndlessProperties`（alias `TestVaseBreaker`，`TestEndlessLevel 0`，`Stages` 3 段）**：每段给 `MinColumnIndex`/`MaxColumnIndex`、`FixedZombieTypes`/`EscalatingZombieTypes`、`PlantTypes`、`CollectableTypes`（`sun` / `plantfood`）、`NumberOfColoredPlants`、`EscalationRate`、`StartingLevel`。
* 产物处理：`vaseCount: null`、`vases: []`、`unknowns` 写明缺罐表；整份 `Stages` 原文收进 `endless.stages`（`stageCount 3`），供实现无尽模式时使用，**不冒充固定罐表**。
* 该关种卡：`SeedBankProperties.PresetPlantList = [cherry_bomb]`。

### 5.2 `pirate_41`（pkg_1557）— Boss 场景 + 选择式种卡 + 传送带

* `stageModule PirateBossStage`，`initialSun 300`（来自 `LevelDefinition.StartingSun`），`IsVasebreaker` **键不存在**。
* 罐表只有 1 条记录（35 个僵尸罐，`Min 2..Max 8`）—— 罐子全部同一种僵尸。
* `SeedBankProperties.SelectionMethod = "chooser"` + 10 条 `PlantExcludeList`；同包还有 `ConveyorSeedBankProperties`（5 条加权植物，`Speed 100`，4 条 `DropDelayConditions`），但它的 `Modules` 里**只有 `SeedBank`、没有 `ConveyorBelt`** —— 与 §2.4 的 `muji_24` 同类，产物按包内对象收录（`seedBankInfo.conveyor = true`）。

### 5.3 `kongfu_83`（pkg_0756）— LastStand + ProtectThePlant

* 罐表 1 条（5 个僵尸罐，列区间 **4..4** 单列）；`LastStandMinigameProperties {StartingSun 14514, StartingPlantfood 0}`；`ProtectThePlantChallengeProperties` 保护 3 株（2 株 `magnifyinggrass` + 1 株 `iceburg`）。
* `NumColoredZombieVases 40` 而实际只有 5 个僵尸罐 —— 原版数据本身不自洽，**原样保留**。

### 5.4 `egypt_57`（pkg_0895）— 纯植物关

19 条记录全是植物罐（30 个），0 僵尸；列区间被压到 `4..6`（三列）；`GridSquareBlacklist` 是空数组；种卡 `PresetPlantList = [chrysantheautumn]`。

### 5.5 数值异常但属原版事实

| 关卡 | 字段 | 值 | 备注 |
| --- | --- | --- | --- |
| `carnival_91` | `NumColoredZombieVases` | **114514** | 彩蛋数字，原版写字面量；罐表实际 18 个僵尸罐 |
| `kongfu_83` | `NumColoredZombieVases` | 40 | 同上不自洽 |
| `pirate_41` | `NumColoredZombieVases` | 35 | 与僵尸罐数相同 |
| `steam_32` | `Vases[]` | 3 条（6 僵尸 / 24 植物） | 单关植物罐占比最高 |
| `muji_24` | `StageModule` `RiftStage` | — | 裂境场景上跑砸罐子 |

产物的 `coloredVases` 字段照抄这些值，测试 `test_colored_vases_and_firework_vases_are_kept` 固定住 `114514` 这个字面量，避免以后被"修"掉。

---

## 6. 产物结构

```
{
  "format": 1,
  "generated": "2026-11-25",
  "sources": {...},
  "counts": {levels, withPreset, withoutPreset, withoutPresetIds, withSeedBank,
             withStartingSun, withTide, withEndless, withLastStand, vaseTotal,
             entryTotal, byType, withTimeLimit, worlds, unknownKinds},
  "levels": {
    "<clientLevelId>": {
      levelId, package, levelFile, levelNumber, levelNameKey, stageModule,
      isVasebreaker, levelPowerupSet, modules[],
      preset {found, objclass, aliases, package},
      vaseCount, entryCount, byType {zombie, plant, collectable},
      vases[] {type, zombieId, plantId, collectableType, count, row, col, sunAmount},
      columnRange {min, max}, excludedCells[][], blacklistedCells[][]|null,
      coloredVases {plant, zombie}, vaseGridItemType,
      seedBank[] {plantId, method, level, weight, minCount, maxCount},
      seedBankInfo {objclass, method, excludeList, conveyor?} | null,
      initialSun, initialSunSource, timeLimit, tide, lastStand, endless,
      sourceFiles[], unknowns[]
    }
  },
  "unknowns": [{kind, count, detail}]
}
```

`vases[]` 里的 `row` / `col` / `sunAmount` 恒为 `null`、`timeLimit` 恒为 `null` —— 这是**如实缺省**，不是漏填。

---

## 7. 复现命令

```powershell
cd D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc

# 生成（确定性：固定 generated 日期、sort_keys、LF 换行）
python tools\contentc\vasebreaker.py

# 逐字节校验（过期即非零退出）
python tools\contentc\vasebreaker.py --check
# -> vasebreaker levels=47 presets=46 (missing 1) vases=1435 seedBank=8 startingSun=4 unknowns=7
# -> OK

# 单测（18 例）
python -m unittest tools.tests.test_vasebreaker -v
```

产物哈希：`vasebreaker.json` 186,116 字节，sha256 `adf41709daa490a927dfcf6193602b2517c315ee42c22f401d656e61d5c043df`，两次生成逐字节相同。

---

## 8. 诚实边界

1. **没有逐罐坐标**：实现放置逻辑时必须自己按 `columnRange` + `excludedCells`/`blacklistedCells` 随机落位（原版行数按 `Mechanics` 的世界棋盘，砸罐子关卡在数据里没写行数）。
2. **没有计时**：砸罐子关卡的胜负条件只有 `ZombiesDeadWinCon` / `DefaultZombieWinCondition` 两个模块，无 `TimeLimit`。
3. **初始阳光缺 43 关**：不能假设"砸罐子统一 0 阳光"，`pirate_41` 是 300、`plantagenet_18` 是 200，`frontyard_166`/`muji_24` 明确是 0。
4. **种卡缺 39 关**：多数关卡靠罐子给植物，没有 `SeedBank`；这 39 关的"可选植物"在原版数据里确实不存在。
5. **彩蛋值不修**：`NumColoredZombieVases = 114514` 这类值原样保留，只在报告里标注，不做 clamp。
6. **`IsVasebreaker` 缺 2 关**（`pirate_41` / `plantagenet_18`）：本产物以 `content/levels` 的 `extra.vasebreaker` 为准入依据（47 关），`isVasebreaker` 字段照抄原表（可能为 `null`），两者不一致处已在 §5.2 标注。
