# 逐关扩展规则表：boardGrid / mutators / night / frost / tide / strength

> 产物 `native/generated/level_extra_rules.json`（359,996 B，sha256 `7113be14…484e09`），
> 编译器 `tools/contentc/level_extra_rules.py`，测试 `tools/tests/test_level_extra_rules.py`（22 例）。
> **门禁提醒**：本表从 `work/obb_packages` 直读。换 OBB 或改 `content/levels/**` 之后要重跑
> `python tools/contentc/level_extra_rules.py`，否则 `--check` 会红。

一句话结论：六块规则里，**boardGrid 是一张 5×9 的 0/1 矩阵**（无坐标、无语义说明），
**mutators 在关卡里只挂 3 类 37 个对象**（其余 11 类只存在于定义表，没人引用），
**night 在原版里没有"天黑时间"这种参数**，真正的信号是"有没有挂 `DefaultSunDropper`"（185/187 没挂），
**frost/tide 是逐波事件**（波次写在模块别名里），**strength 是派生量、不是 OBB 字段**。

---

## 0. 摘要

| 块 | 关卡数 | 源类 | 对象/事件数 | 产物里的样子 |
|---|---|---|---|---|
| boardGrid | **49** | `BoardGridMapProps` + `MoldColonyChallengeProps` + `InitialGridItemProperties` | 50 张图 / 2250 格 | `maps[{class,alias,height,width,rows,cellCounts,cellsByCode}]` + `moldChallenge[]` + `gridItems[]` |
| mutators | **21** | `LevelMutator*`（关卡实际只用 3 类） | 37 | `[{objclass,alias,<铺平字段>}]` |
| night | **187** | 无 `NightModule`；`content extra.night` + `StageModule` + 模块表 + `SpawnGravestonesWaveActionProps` | 315 个墓碑事件（68 关） | `{flagSource,stage,stageModule,stageModuleClass,stageProps,modules,gravestones[]}` |
| frost | **64** | `FrostWindWaveActionProps` | 283 事件 | `{class,events[{wave,alias,winds[],windCount}],directions,rows,rowsRaw}` |
| tide | **60**（涨落）/ **10**（潜艇段）/ **80**（标记位） | `TidalChangeWaveActionProps` / `TideWaveWaveActionProps` / `TideProperties` | 370 / 22 / 81 | `{class,changes[],waves[],startingWaveLocation,showTideMarker,tideMarkerClass,tideWaveClass}` |
| strength | **60** | 无（派生自 tide 的 `|ChangeAmount|` 之和） | — | `{value,changeCount,derivedFrom,derivedSource}` |

产物：`levels` 1809 键，其中 **385 关**至少有一块规则；`counts` 19 项；`unknowns` 8 条；
`generated` = `sha256:ce13b954bd69d03b`（对载荷内容寻址，不含墙钟/mtime）。

---

## 1. 类名是怎么定下来的

任务里给的线索是"`BoardGrid`/`LevelGrid`"和"`NightModule` 之类"——**这两个名字在原版里都不存在**。
做法是先做关键词普查，再逐个排除。

普查口径（`work/_lx_probe1.py`）：遍历 2117 个包的 `objclass` 与 `aliases`，匹配
`grid|board|mold|night|frost|wind|tide|strength|mutator`，把命中按类计数；
第二次（`_lx_probe2.py`）对命中的类逐类统计字段覆盖并 dump 代表对象。

### 1.1 boardGrid 的真名是 `BoardGridMapProps`

| 类 | 全库对象 | 判定 |
|---|---|---|
| `BoardGridMapProps` | 302 | **是**。唯一字段 `Values`，就是 5 行 × 9 列的 0/1 矩阵 |
| `MoldColonyChallengeProps` | 99 | **不是格图**，是挑战参数：唯一字段 `Locations` = `RTID(<地图别名>@CurrentLevel)`。49 关全命中，且指回同一张图 → 产物里作为 `boardGrid.moldChallenge` 旁证 |
| `InitialGridItemProperties` | 592 | 不是格图，是**初始摆件**：唯一字段 `InitialGridItemPlacements:[{GridX:"5",GridY:"1",TypeName:"slider_down"}]`（坐标是**字符串**） |
| `DangerRoomBoardGridMap*Placer` | 5+1+1+1+1 | 危险房专用摆放器，与这 49 关无关 |

格码语义：这 50 张图 **只用 0 和 1**（2250 格里 1 有 889、0 有 1361）。
全库里确实有 2 的图（`pkg_0005` 的 `MineCarts_01..29`、`Traps*`、`Floes*`，是矿车/陷阱的辅助图），
但它们不是关卡图，**不能拿来解释关卡图里 1 的含义**。原版没有任何字段说明 1 = 可种还是 = 被模菌占住，
所以产物只原样给矩阵与坐标集合，并把它写进 `unknowns: board-grid-code-semantics`。

两张反常图：`plantagenet_42` 的 `Column0_to_Column1` **全 0**（45 格全 0，有对象但一格没占）；
`lunarrainbowmarket_49` 同一个包里**有两张同名 `MoldColonies`**（都记，不去重）。

别名谱（50 张图）：`MoldColonies` 17、`moldcolony` 11、`Column0_To_Column0` 5、`MoldLocationsCustom` 2、
其余 `tony`/`fumoutou`/`nnd`/`Mold`/`BGMP`/`Molds`/`DinoEX5`/`carnival26`/`THIRDANNIVERSARY3`/`THIRDANNIVERSARY6`/
`ChineseGarden5`/`ChineseGarden11MoldColonies`/`ChineseGarden22MoldColonies`/`Column0_to_Column1` 各 1。
**别名不能当键**（重名、大小写混排），所以产物里图以 `maps` 数组给，不建成字典。

### 1.2 mutators 的真名是 `LevelMutator*`（14 类），但关卡只挂 3 类

全库 `LevelMutator*` 共 **14 类 / 194 个对象**。关卡 `LevelModules` 里真正出现的只有：

| 类 | 关卡挂载数 | 字段 |
|---|---|---|
| `LevelMutatorTableProps` | 16 | `Tables`（嵌套：`[{moduleType, modules[], …}]`）、`TypeName` |
| `LevelMutatorModuleProperties` | 13 | `MutatorTables`（RTID 列表） |
| `LevelMutatorMaxSunProps` | 8 | `MaxSunOverride`、`DifficultyProps`、`IconImage`、`IconText` |

剩下 11 类（`StartSun`/`SeedSlotCount`/`StartingPlantfood`/`MowerSpawn`/`PowerupSet`/`SunDropper`/
`ZombieCountdownFirstWaveSecs`/`ZombieLevel`/`ZombieGeneralLevel`/`GridItemLevel`/`RiftZombossPhases`）
**只存在于两个定义表包里**：`pkg_0236_LevelMutatorStartingPlantfoodProps`（12 类）与
`pkg_0237_LevelMutatorTableProps`（`LevelMutatorTableProps` 91 个）——没有任何关卡模块引用它们。
这一条进 `unknowns: mutator-sheet-classes-unused`：数据在、接线点不在，别拿定义表冒充关卡参数。

### 1.3 night 没有 `NightModule`

`content/levels/*.json` 的 `extra.night` 是 `tools/obb_build_content.py:276 is_night_level(stage, od, modules)`
算出来的布尔量，规则三条：stage 名含 night / `Name` 大写匹配 `(?:^|_)NIGHTS?(?:_|$)` / 模块别名等于
`marketnight`、`heiannight` 或以 `night` 开头。全库别名满足这条的只有 48 个对象，且**没有一个叫 `NightModule`**：
`GridItemGridRegionAreaOfEffectTrapProps` 14（`NightTransformProps`/`NightToEgyptProps` 这类换图格）、
`GridItemType` 14、`StageModuleProperties` 3，其余全是植物（`NightcapProps`/`NightshadeProps`/`PlantLevelStats` 等）。

所以 night 这块的"参数"是**三样东西拼出来的**：

1. **`extra.night` 布尔量**（哪 187 关算夜关，产物写 `flagSource` 指回该文件）；
2. **模块表**：夜关里 `DefaultSunDropper` 只有 **2/187**（`frontyard_46`、`lostcity_46`，已回到 pkg_2003/pkg_0965
   直接核对 `LevelDefinition.Modules`）→「夜里不落阳光」在原版里就是**不挂这个模块**，不是某个 `disableSkySun: true`；
   另有 `MarketNight` 36、`HeianNight` 2、`NightStageMusic` 1；
3. **`SpawnGravestonesWaveActionProps`**（全库 1221 个）：68/187 夜关有，产物按 `Wave<N>GravestoneEvent`
   别名解出波次，逐条给 `pool[{type,count}]`（如 `[{type:"gravestone_dark",count:5}]`）、
   `positions[{x,y}]`、`randomPlacement`、`displacePlants`、`waveStartMessage` 等。

stage 侧：`StageModule` 别名在夜关里能解析到 **7 个 `*StageProperties` 类**——
`EgyptStageProperties` 90 关、`WestStageProperties` 13、`DarkStageProperties` 10、`LostCityStageProperties` 9、
`ChineseGardenStageProperties` 6、`RoofStageProperties` 1、`EightiesStageProperties` 1（全库另有 14 个
`*StageProperties` 类共 221 个对象，但夜关用不到）。
这些类里有 `BackgroundImagePrefix`、`BackgroundResourceGroup`、`MusicSuffix`、`GravestoneDefaultTypeName`、
`DisabledStreetCells`（chinesegarden 51 格）、`IsNightStage`（只在 `ChineseGardenStageProperties`，7 个里 6 个 true），
**但没有"天黑时间点"、没有"光照强度"、没有"禁天降阳光"开关**。→ `unknowns: night-no-dusk-time`。

另有 **57 关**的 `stageModule` 别名在 2117 个包里查不到对象（`FairyNightsStage` 12、`FairyNightsDMGStage` 8、
`FairyNightsUBStage` 7、`FairyStage` 9、`FairyTale*` 等）→ `unknowns: night-stage-module-unresolved`，
产物保留了别名原文，没有编造类名。

### 1.4 frost 是 `FrostWindWaveActionProps`

283 个事件 / 64 关，唯一字段 `Winds`。每条 wind 只有 `{Direction, Row}` 两个字段（right 1049 / left 58），
`Row` 有整数 0..5 与 **-1（表示整行）**，也有 RTON 里写成字符串 `'0'..'4'` 的 → 产物统一转数值，
同时把原始写法留在 `rowsRaw` 里（不丢证据）。每事件的 wind 数 1..29，波次从别名 `Wave<N>FrostWindEvent<N>` 解出，
**10 个事件（共 283 个）的别名里解析不出波次** → 该事件 `wave: null`。

同族但**不是 frost** 的是 `HeianWindModuleProperties`（1 个，别名 `HeianWindModule`，字段 `WaveWindInfos`：
`{WaveNumber, WindDelay, StartDelay, WindInfos[{Row, AffectZombies, Distance, MoveTime}]}`）——
它是和风世界的横向吹怪，有 `AffectZombies` 和 `Distance`，frost 没有。**未并入 frost**，此条进 unknowns 的说明里，
等 wirer 决定要不要单开一块。

### 1.5 tide 是三个类、互不重叠

| 类 | 对象 | 关卡 | 字段 | 语义 |
|---|---|---|---|---|
| `TidalChangeWaveActionProps` | 370 | **60** | `TidalChange:{ChangeAmount, ChangeType:"absolute"}` | 逐波涨落量（**涨落事件**，counts 的 `tide` 只数这个） |
| `TideWaveWaveActionProps` | 22 | **10** | `Type`/`Duration`/`SubmarineMovingDistance`/`SpeedUpDuration`/`SpeedUpIncreased`/`SubmarineMovingTime`/`ZombieMovingSpeed`/`BackAfterTide` | 潜艇段（僵尸随潮推进的那一段） |
| `TideProperties` | 81 | **80** | `StartingWaveLocation`（81）、`ShowTideMarker`（4，全是 `false`：`beach_15`/`beach_21`/`beach_35`/`pirate_10`） | 起始潮位 / 潮汐记号 |

三者**集合互不相交**（wave-only 的关在 `pkg_0265..0271`、`0287..0289`），所以产物把三档并列写进同一个 `tide` 块，
并在 counts 里分层：`tide` = 有 `changes` 的 60 关、`tideBlocks` = 有 tide 块的 90 关、
`tideWithWaves` = 10、`tideWithMarker` = 80、`tideWithChanges` = 60。
组合分布：`changes+marker` 58、`marker` only 18、`waves` only 10、`changes+showTideMarker+marker` 2、`showTideMarker+marker` 2
（58+18+2+2 = 80 标记位；60 涨落 = 58+2；90 块 = 60+18+10+2）。

`TideEffectsProps`（1 个，20 个格子坐标）与 `DangerRoomBeachTideChanger`（2 个）不是这 60 关的参数，未收。

### 1.6 strength 是派生量，不是 OBB 字段

`tools/contentc/mechanics.py:851 _event_strength` 的口径是把该关 tide 事件的 `ChangeAmount` 取绝对值求和再 `round(…, 4)`。
产物照样给，但把来源写死：

```json
"strength": {"value": 44.0, "changeCount": 8,
             "derivedFrom": "sum(|TidalChange.ChangeAmount|)",
             "derivedSource": "tools/contentc/mechanics.py:851 _event_strength"}
```

`--check` 里有两条硬断言：strength 必须伴随 tide 的 `changes`，且 `value` 必须等于复算值。

---

## 2. 字段表

### 2.1 boardGrid（49 关）

| 产物字段 | 来源 | 说明 |
|---|---|---|
| `maps[].class` | `BoardGridMapProps` | 真类名，写死进产物 |
| `maps[].alias` | 对象别名 | 见 §1.1 别名谱；同名图不去重 |
| `maps[].height/width` | `Values` 形状 | 实测全 5×9 |
| `maps[].rows` | `Values` | 原样 2D 数组 |
| `maps[].cellCounts` | 统计 | `{"0":n,"1":m}` |
| `maps[].cellsByCode` | 统计 | `{"1":[[row,col],…],"0":[…]}`（**行列序**） |
| `moldChallenge[]` | `MoldColonyChallengeProps` | `{class,alias,locations}`，`locations` 已去 RTID 壳 |
| `gridItems[]` | `InitialGridItemProperties` | `{class,alias,placements[{x,y,type}]}`，坐标已从字符串转 int；19 关有 |

`beach_94` 逐格真值（测试断言用）：

```
rows[0] = [1,1,1,1,1,0,0,0,0]
rows[2] = [1,1,0,1,1,0,0,0,0]
cellCounts = {"0":21,"1":24}
```

### 2.2 mutators（21 关 / 37 对象）

铺平规则（R03）：`objdata` 的标量原样给，键名**小写长头**（`MaxSunOverride` → `maxSunOverride`），
`RTID(x@Y)` 归一成 `x`，`#` 开头的注释键跳过，嵌套结构保持嵌套（不拍平成 `a.b.c`）。
每行固定带 `objclass` 与 `alias`，因此"来源"就在行内。

`carnival_51`（1 个 MaxSun）：

```json
{"objclass":"LevelMutatorMaxSunProps","alias":"OverrideMaxSun275",
 "maxSunOverride":275,"difficultyProps":"LevelModuleDifficultyMaxSun",
 "iconImage":"…","iconText":"<500"}
```

`beach_21`（bonuschallenge 表）：`LevelMutatorTableProps.tables[0]` = `{moduleType:"bonuschallenge", modules:["KillZombies1"], …}`，
`LevelMutatorModuleProperties.mutatorTables` = `["MutatorPropsRiftConveyor","LocalChallengeMutator"]`。

### 2.3 night（187 关）

| 产物字段 | 来源 |
|---|---|
| `flagSource` | `content/levels/<id>.json extra.night`（原版没有 night 类，只能以构建器判定为准） |
| `stage` / `stageModule` / `stageModuleClass` / `stageModulePackage` | `LevelDefinition.StageModule` → 别名解析到 `*StageProperties` |
| `stageProps` | 该 stage 类对象里可接线的几个键（`BackgroundImagePrefix` 等），没有时间/光照字段 |
| `modules.count` / `hasSkySunDropper` / `nightModules[]` | `LevelModules` 表（185/187 无 `DefaultSunDropper`） |
| `gravestones[]` | `SpawnGravestonesWaveActionProps`：`{wave,alias,pool,positions,randomPlacement,displacePlants,waveStartMessage,…}` |

### 2.4 frost（64 关 / 283 事件）

`events[].winds[]` 每条 `{direction, row}`（`row` 已转 int，原始写法在 `rowsRaw`），
另有汇总 `directions`（`{"right":n,"left":m}`）与 `rows`。

### 2.5 tide（60 / 10 / 80）

`changes[]` 每条 `{wave, alias, amount, type}`（`amount` 已从字符串转 float）；`waves[]` 每条给
`{wave?, alias, type, duration, submarineMovingDistance, speedUpDuration, speedUpIncreased, submarineMovingTime, zombieMovingSpeed, backAfterTide}`
（哪些字段有就写哪些）；`startingWaveLocation`、`showTideMarker`、`tideMarkerClass`、`tideWaveClass` 原样。

### 2.6 strength（60 关）

见 §1.6。

---

## 3. 与 A6 / mechanics / content 的逐项对账

同一份 460.9 dump、两套代码路径（`level_playability.py` 读 `level_mechanics.json` 派生的 blocker，
本表读 OBB 原始对象），六个数字必须相等：

| 口径 | 本表 | `level_playability.json` | `level_mechanics.json` | `content/levels` |
|---|---|---|---|---|
| boardGrid | **49** | `blockersByKind.boardGrid` 49 | `boardGrid` 非空 49 | — |
| mutators | **21** | `blockersByKind.mutators` 21 | `mutators` 非空 21 | — |
| night | **187** | `blockersByKind.night` 187 | — | `extra.night == true` 187 |
| frost | **64** | `blockersByKind["events.frost"]` 64 | `events.frost` 非空 64 | — |
| tide | **60** | `blockersByKind["events.tide"]` 60 | `events.tide` 非空 60（与本表 `changes` 的关集合逐关相同） | — |
| strength | **60** | `blockersByKind["events.strength"]` 60 | 同 tide 事件集 | — |

`tests/test_level_extra_rules.py::test_blocker_counts_agree_with_level_playability` 就是逐项跑上表（缺文件时 skip）。
tide 这一行两边口径不同但数字相同：`events.tide` 只收「有涨落事件」的关，本表的 `tide` 也按同一门槛数（60），
另有 `tideBlocks=90` 把「只有标记位」和「只有潜艇段」的关也算进来 —— 看数时别把 90 当成 60。

包加载覆盖：2117 个包**全部可加载**（`failed=0`）——否则"某类 0 命中"可能只是解包失败。

---

## 4. unknowns（8 条，只增不减）

| kind | 是什么 | 建议探针 |
|---|---|---|
| `board-grid-code-semantics` | 0/1 哪个表示禁用/替换，原版无字段说明 | 对照 `GridItemType` 里模菌的行为，或游戏内实测 |
| `board-grid-empty-map` | `plantagenet_42` 有 `BoardGridMapProps` 但 45 格全 0 | 查该关 `LevelModules` 是否真挂了格图模块 |
| `mutator-sheet-classes-unused` | 11 类 `LevelMutator*` 只在 `pkg_0236`/`pkg_0237` 定义表，无关卡引用 | 查这些表是否由服务器/活动系统在运行时下发 |
| `night-no-dusk-time` | 原版没有"天黑时间点/光照强度"字段 | 只能以「有没有 `DefaultSunDropper`」+ 背景资源判定 |
| `night-stage-module-unresolved` | 57 关的 `StageModule` 别名无对象（`FairyNightsStage` 等） | 查这些关是否被裁掉的世界（fairy 系列） |
| `night-without-gravestones` | 119 个夜关没有墓碑生成模块 | 确认这些关是否只靠"没阳光"体现夜晚 |
| `tide-properties-without-tide-events` | 20 关只有 `TideProperties` 没有涨落事件 | 查是否靠初始潮位静止表现 |
| `tide-wave-without-tide-events` | 10 关只有潜艇段没有涨落事件 | 查潜艇段的触发条件是否在 WaveAction 之外 |

---

## 5. 给接线的人（wirer）

- **boardGrid**：只有矩阵，**没有坐标映射表**。5×9 与 `boardGrid` 的 row/col 方向要和 `board_grid` 的
  `boardGrid`（mechanics 同名字段）对齐；0/1 语义未定，接之前必须先决定"1 = 可种"还是"1 = 不可种"。
- **mutators**：21 关里 16 关是 `TableProps`/`ModuleProperties`（表名引用），真正能直接用的标量只有
  `maxSunOverride`（8 关）。其余 11 类**不要在关卡里找**，它们不在 `LevelModules` 里。
- **night**：接线的判据是 `modules.hasSkySunDropper == false`，别去找"天黑时间"；墓碑按
  `gravestones[].wave` 挂在对应波次，`positions` 是格子坐标（`x`=列、`y`=行）。
- **frost**：`row == -1` 表示整行/全屏，不是"第 -1 行"。
- **tide**：`changes[]` 是逐波涨落（`amount` 正负表示方向），`waves[]` 是潜艇段，`startingWaveLocation` 是起始潮位；
  三者可以同时存在于不同关，`--check` 会保证不混为一谈。
- **strength**：派生量，别去 OBB 找同名字段。

---

## 6. 产物结构与复现

```json
{"format":"pvz2-shuttle/level-extra-rules@1","generator":"level_extra_rules",
 "generated":"sha256:ce13b954bd69d03b","sources":["work/obb_packages …","content/levels …"],
 "counts":{…19 项…},
 "levels":{"beach_94":{"boardGrid":{…},"mutators":[…],"night":{…},"frost":{…},"tide":{…},"strength":{…}}},
 "unknowns":[…8 条…]}
```

- 紧凑 JSON（`separators=(",",":")`）+ `sort_keys=True` + 单个结尾 LF；`generated` 是对**去掉该键后的载荷**
  做规范紧凑编码再取 `sha256` 前 16 位，**不含墙钟、不含文件 mtime**。
- 复现：

```powershell
python tools/contentc/level_extra_rules.py           # 写产物
python tools/contentc/level_extra_rules.py --check   # 幂等校验（改过 OBB/content 会红）
python -m unittest tools.tests.test_level_extra_rules -v
```

- 实测耗时：`--check` 冷跑 **15.7 s**（含解释器启动与 OneDrive 读盘；build 内部计时 5.8 s）；
  测试 **22 例 / 7.9 s**。`--check` 两跑逐字节相同（sha256 `7113be14…` 不变）。

---

## 7. 诚实边界

1. **boardGrid 的 0/1 语义没解出来**，只给矩阵与坐标集合；任何"1 = 可种"的写法都是猜测。
2. **night 不是一块规则**：187 这个数字来自构建器的三元判定，不是某个原版模块；「不落阳光」是**缺模块**的副作用。
3. **strength 是派生量**（`sum(|ChangeAmount|)`），产物里显式标了 `derivedFrom`，别当原版字段用。
4. **mutators 只覆盖关卡实际挂的 3 类**；定义表里的 11 类没有接线点，写进 unknowns 而不是硬塞进产物。
5. **57 关的 stage 别名在全库无对象**（多为 fairy 系列被裁内容），产物保留别名原文，没有编类名。
6. tide 的 `tide`（60）与 `tideBlocks`（90）是两个口径，看数时别混：前者对齐 A6 的 blocker，后者是"有潮汐数据的关"。
7. 本表只读 `work/obb_packages` 与 `content/levels`；不读其它 generated 产物（跨表对账只在测试里做，且缺文件时 skip）。
