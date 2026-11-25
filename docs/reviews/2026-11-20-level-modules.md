# S7.0 关卡模块清点（1809 关 extra → level_modules.json）

- 生成命令：`python tools/contentc/levelextra.py`
- 机器可读清单：`native/generated/level_modules.json`
- 客户端侧：`content/levels/*.json` 的 `extra`
- 原版侧：`work/obb_packages/pkg_*_LevelDefinition.json` 的 `Modules` 与模块参数对象

实测 1809 关、15 个 `extra` 键、1809 份原版关卡定义、385 个不同模块名、273 个对象类。下文所有数字均来自本次运行，没有对应原版模块的键一律标 `unknown` 并留探针，不做推测填充。

## 结论摘要

1. **有数据可直接驱动**：`boss` 71 关、`vasebreaker` 47 关、`minecarts` 190 关；另有 `stage`（1809 关）与 `night`（1809 关）两个关卡级信号。原版这三类模块都带参数对象（见第 2 节），可以撑起运行时。
2. **只有标记无参数**：`boss_zombie`、`vasebreaker`、`special`、`minecarts`、`rail`、`night` 六个键只说明「这一关有这个玩法」，参数（花瓶布局、轨道列、僵王阶段…）全部要回原版取。
3. **原版有但客户端没导出**：385 个原版模块名中只有 3 类有对应的 `extra` 键；`ChallengeModule`、`ConveyorBelt`、`Gravestones`、`ProtectThePlant`、`Tide` 等共 375 个模块完全没有客户端入口。具体覆盖缺口见第 4 节。

## 一、extra 键总表

| 键 | 出现关卡 | 类型 | 状态 | 对应原版模块 | 说明 |
|---|---|---|---|---|---|
| `boss` | 71 | bool | data | `ZombossBattle`、`ZombossBattle1`、`ZombossBattle2` | 布尔开关；原版 ZombossBattleModuleProperties 带阶段与召唤参数 |
| `boss_zombie` | 71 | str | flag_only | `ZombossBattle`、`ZombossBattle1`、`ZombossBattle2` | 只给僵王代号（zomboss / gargantuar），没有阶段、血量、攻击序列 |
| `level_number` | 1809 | int | meta | — | 关卡序号 |
| `minecarts` | 190 | list | flag_only | `Rails`、`CowboyRails`、`Railcart`、`Railcart1` | 只有行号数组（如 [0, 2]、[1, 2, 3]），缺轨道列、长度、速度、载量 |
| `name_key` | 1809 | NoneType/str | meta | — | 本地化键，3 关为 null |
| `night` | 1809 | bool | flag_only | — | 布尔，由 stage 派生；与 stage 名里的 Night 有冲突，实现时要按原版判定 |
| `original_waves` | 1809 | int | meta | — | 移植前波数，用于对账 |
| `package` | 1809 | str | meta | — | 原版 LevelDefinition 的包号，用于反查 |
| `rail` | 192 | bool | flag_only | `Rails`、`CowboyRails`、`Railcart`、`Railcart1` | 布尔开关，与 minecarts 同源 |
| `source` | 1809 | str | meta | — | 数据来源标记，实测恒为 obb |
| `special` | 45 | list | flag_only | `VaseBreakerArcade`、`VaseBreakerProps`、`TestVaseBreaker` | 标记列表，实测只有 IsVasebreaker 一种 |
| `stage` | 1809 | str | data | `StageModule` | 关卡场景名；原版各 *StageProperties 带场景参数 |
| `suppressFlagZombie` | 271 | bool | flag_only | — | 布尔开关，挂在 WaveManagerProperties 上（实测 271 关：true 215 / false 56），不是 Modules 列表里的模块 |
| `vasebreaker` | 47 | bool | flag_only | `VaseBreakerArcade`、`VaseBreakerProps`、`TestVaseBreaker` | 布尔开关；花瓶数量、植物池、波次都在原版 VaseBreakerPresetProperties 里 |
| `wave_count` | 1809 | int | meta | — | 波数；原版 WaveManagerModuleProperties 里才是波表 |

取值样例（每种键最多 8 个不同值）：

- `boss`：true
- `boss_zombie`："zomboss"、"gargantuar"
- `level_number`：1、6、7、8、9、10、11、12
- `minecarts`：[0,2]、[0,1,3]、[3]、[1,4]、[1,2]、[1,2,3]、[2]、[0]
- `name_key`："[BEACH_LEVEL_NAME]"、"[ATLANTIS_LEVEL_NAME]"、"[DINO_LEVEL_NAME]"、"[BEACH_EXPAND_LEVEL_NAME]"、"[SEASHROOM_LEVEL_NAME]"、"[ELEMENT_LEVEL_NAME]"、"[LYCY_LEVEL_NAME]"、"[MODERN_LEVEL_NAME]"
- `night`：false、true
- `original_waves`：12、16、18、15、20、14、0、8
- `package`："pkg_0325"、"pkg_0336"、"pkg_0337"、"pkg_0338"、"pkg_0339"、"pkg_0326"、"pkg_0327"、"pkg_0328"
- `rail`：true
- `source`："obb"、"obb-synth"
- `special`：["IsVasebreaker"]
- `stage`："BeachStage"、"BeachUBStage"、"BeachDMGStage"、"BeachBossStage"、"DeepseaStage"、"DeepseaLandStage"、"BeachTeaserStage"、"BeachMiniGameStage"
- `suppressFlagZombie`：false、true
- `vasebreaker`：true
- `wave_count`：12、16、18、14、20、13、15、8

## 二、有数据可直接驱动

### 2.1 boss（僵王战）

- 客户端：`boss` 布尔 71 关、`boss_zombie` 代号 71 关（实测 gargantuar 3 关、zomboss 68 关）。
- 原版：`ZombossBattleModuleProperties` 74 个对象、模块名 `ZombossBattle` 71 关，另有 `ZombossBattleIntroProperties` 与各世界 `Zomboss*ActionDefinition`。
- 覆盖核对：原版 71 关、客户端 71 关、交集 71 关，两侧都没有多余项 —— 这一项**完全对齐**。

### 2.2 vasebreaker（砸花瓶）

- 客户端：`vasebreaker` 47 关，`special` 与之同步（45 关，取值恒为 `["IsVasebreaker"]`）。
- 原版：`VaseBreakerPresetProperties` 46 个对象 + `VaseBreakerEndlessProperties` 1 个，模块名 `VaseBreakerArcade` 46 关、`TestVaseBreaker` 1 关。
- 覆盖核对：原版 47 关、客户端 47 关、交集 47 关，原版多出 0 关：。

### 2.3 minecarts（矿车/轨道）

- 客户端：`minecarts` 190 关，取值只有行号（如 `[0,2]`、`[0,1,3]`、`[3]`），`rail` 同 192 关。
- 原版：`RailcartProperties` 202 个对象，模块名 `Rails` 101 关、`CowboyRails` 78 关、`Railcart` 5 关、`Railcart1` 1 关。
- 覆盖核对：原版 185 关、客户端 190 关、交集只有 178 关 —— 见 4.2，这项缺口最大。

### 2.4 关卡级信号

- `stage`：1809 关全覆盖，198 个不同场景名；原版对应 `StageModule` 与各世界 `*StageProperties`（`BeachStageProperties`、`EgyptStageProperties` 等）。
- `night`：1809 关全覆盖的布尔，但有 13 关与 `stage` 名里的 `Night` 不一致（抽样：`carnival_30`、`dark_52`、`dark_53`、`dark_54`、`dark_56`、`dark_57`），实现时应以原版场景参数为准，不要直接信这个布尔。

## 三、只有标记无参数

这一档的键能告诉你「这一关是这个玩法」，但驱动不了任何表现，缺的参数如下：

| 键 | 现有的 | 缺的参数 | 影响 |
|---|---|---|---|
| `boss_zombie` | 僵王代号字符串 | 阶段划分、血量、攻击/召唤序列、出场动作 | 只能显示名字，摆不出战斗 |
| `vasebreaker` | 布尔 | 花瓶数量与布局、可出植物池、波次表 | 只能判定是不是砸花瓶关卡 |
| `special` | `IsVasebreaker` 标记 | 同上 | 同上 |
| `minecarts` | 行号数组（如 `[0, 2]`） | 轨道列号、长度、速度、载量、生成节奏 | 知道哪几行有车，画不出轨道 |
| `rail` | 布尔 | 同上 | 同上 |
| `night` | 布尔 | 光照/音乐/场景参数（原版在 `*StageProperties`） | 13 关与 `stage` 冲突，不能单独采信 |

另有 6 个纯元数据键（`level_number`、`name_key`、`original_waves`、`package`、`source`、`wave_count`），它们不是模块，只是移植时的对账信息（`package` 用于回查原版文件）。

## 四、原版有但客户端没导出

原版共 385 个不同模块名，只有 `ZombossBattle*`、`VaseBreaker*`、`Rails`/`CowboyRails`/`Railcart*` 三类能在 `extra` 里找到入口，其余 375 个模块名客户端完全没有导出。按关卡数排序的前 20 个：

| 原版模块 | 关卡数 | 客户端键 |
|---|---|---|
| `DefaultZombieWinCondition` | 1756 | — |
| `NewWaves` | 1722 | — |
| `ZombiesDeadWinCon` | 1698 | — |
| `StandardIntro` | 1385 | — |
| `SeedBank` | 1354 | — |
| `ChallengeModule` | 920 | — |
| `DefaultSunDropper` | 821 | — |
| `ConveyorBelt` | 332 | — |
| `Gravestones` | 274 | — |
| `ProtectThePlant` | 197 | — |
| `ModernMowers` | 169 | — |
| `FrozenPlantPlacement` | 158 | — |
| `LevelEscalationModule` | 127 | — |
| `SliderPlacement` | 89 | — |
| `IGP` | 81 | — |
| `Tide` | 77 | — |
| `JamZombiesModule` | 76 | — |
| `GoldTiles` | 75 | — |
| `LastStand` | 73 | — |
| `FrozenZombiePlacement` | 68 | — |

### 4.1 缺口集中在玩法模块

`ChallengeModule`（920 关，星挑战）、`StarChallengeModuleProperties`（952 个对象）、`ConveyorBelt`（332 关，传送带）、`Gravestones`（274 关，墓碑）、`ProtectThePlant`（197 关，保护植物）、`FrozenPlantPlacement`（158 关）、`Tide`（77 关，潮汐）、`GoldTiles`（75 关）、`LastStand`（73 关）、`SliderPlacement`（89 关）都属于「有完整参数、客户端只有关卡 JSON 本体」的情况：S7 要支持它们，参数一律从原版模块对象读。

### 4.2 rails 覆盖缺口

- 原版 185 关带 rail 模块，客户端只有 190 关标了 `minecarts`，两侧都有的仅 178 关。
- 原版有、客户端没标：7 关，抽样 `egypt_46`、`fairy_31`、`frontyard_98`、`future_66`、`future_69`、`future_70`、`plantagenet_47`。
- 客户端标了、原版没有 rail 模块：12 关 —— `beach_10`、`beach_11`、`beach_16`、`beach_8`、`beach_9`、`cowboy_20`、`egypt_19`、`future_54`、`kongfu_44`、`memorytour_4`、`plantagenet_40`、`plantagenet_45`。两个方向都不是漏标：模块名口径（本工具）与对象级证据（`RailcartProperties.Railcarts` / `DangerRoomRailcartDesigner`）在 7 关原版只有对象、12 关只有模块名之外的情形上不一致；t52 起 `content` 上的标记由 `tools/obb_build_content_v2.py` 按**对象级证据**派生，所以这里的分歧属口径差异，不是待修缺口。

### 4.3 vasebreaker 覆盖缺口

原版 47 关、客户端 47 关，两侧一致，没有缺口（t52 已按原版 `Modules` 补齐）。

### 4.4 原版没有 Modules 的关卡

4 关的原版定义里没有 `Modules` 列表：`egypt_50`、`frontyard_86`、`frontyard_87`、`frontyard_88`。它们只有 `LevelDefinition` 一个对象，属于没有模块可跑的关卡（选关/演示类），S7 不能假设每关都有模块表。

## 五、unknown 与探针

- 本次运行没有对不上原版的 `extra` 键。
- 原版没有 rail 模块名、客户端却有标记的 12 关（`beach_10`、`beach_11`、`beach_16`、`beach_8`、`beach_9`、`cowboy_20`、`egypt_19`、`future_54`、`kongfu_44`、`memorytour_4`、`plantagenet_40`、`plantagenet_45`）：这些关在原版有 `RailcartProperties` 对象（对象级证据成立），只是 `Modules` 里没写 `Rails`/`CowboyRails`，属模块名口径漏判；t52 起标记改由对象级证据派生，不再按缺参数处理。原先 7 个 kongfu 误标关（原版既无模块也无对象）已在 t52 撤标。

## 六、逐键明细

### `boss`

- 出现：71 关；世界：beach、carnival、chinesegarden、cowboy、dark、dino、egypt、eighties、fairy、frontyard、future、heian、iceage、kongfu、losantosvice、lostcity、lunarrainbowmarket、mausoleum、modern、muji、pirate、plantagenet、renai、sky、steam
- 状态：`data`；对应原版模块：ZombossBattle、ZombossBattle1、ZombossBattle2；参数类：ZombossBattleModuleProperties、ZombossBattleIntroProperties
- 样例：true

### `boss_zombie`

- 出现：71 关；世界：beach、carnival、chinesegarden、cowboy、dark、dino、egypt、eighties、fairy、frontyard、future、heian、iceage、kongfu、losantosvice、lostcity、lunarrainbowmarket、mausoleum、modern、muji、pirate、plantagenet、renai、sky、steam
- 状态：`flag_only`；对应原版模块：ZombossBattle、ZombossBattle1、ZombossBattle2；参数类：ZombossBattleModuleProperties
- 样例："zomboss"、"gargantuar"

### `level_number`

- 出现：1809 关；世界：beach、carnival、chinesegarden、cowboy、dark、dino、egypt、eighties、fairy、frontyard、future、heian、iceage、kongfu、losantosvice、lostcity、lunarrainbowmarket、mausoleum、memorytour、modern、muji、pirate、plantagenet、renai、sky、steam
- 状态：`meta`；对应原版模块：—；参数类：—
- 样例：1、6、7、8、9、10、11、12

### `minecarts`

- 出现：190 关；世界：beach、carnival、chinesegarden、cowboy、dark、dino、egypt、eighties、fairy、frontyard、future、heian、iceage、kongfu、losantosvice、lostcity、lunarrainbowmarket、mausoleum、memorytour、modern、pirate、plantagenet、renai、sky、steam
- 状态：`flag_only`；对应原版模块：Rails、CowboyRails、Railcart、Railcart1；参数类：RailcartProperties
- 样例：[0,2]、[0,1,3]、[3]、[1,4]、[1,2]、[1,2,3]、[2]、[0]

### `name_key`

- 出现：1809 关；世界：beach、carnival、chinesegarden、cowboy、dark、dino、egypt、eighties、fairy、frontyard、future、heian、iceage、kongfu、losantosvice、lostcity、lunarrainbowmarket、mausoleum、memorytour、modern、muji、pirate、plantagenet、renai、sky、steam
- 状态：`meta`；对应原版模块：—；参数类：—
- 样例："[BEACH_LEVEL_NAME]"、"[ATLANTIS_LEVEL_NAME]"、"[DINO_LEVEL_NAME]"、"[BEACH_EXPAND_LEVEL_NAME]"、"[SEASHROOM_LEVEL_NAME]"、"[ELEMENT_LEVEL_NAME]"、"[LYCY_LEVEL_NAME]"、"[MODERN_LEVEL_NAME]"

### `night`

- 出现：1809 关；世界：beach、carnival、chinesegarden、cowboy、dark、dino、egypt、eighties、fairy、frontyard、future、heian、iceage、kongfu、losantosvice、lostcity、lunarrainbowmarket、mausoleum、memorytour、modern、muji、pirate、plantagenet、renai、sky、steam
- 状态：`flag_only`；对应原版模块：—；参数类：—
- 样例：false、true

### `original_waves`

- 出现：1809 关；世界：beach、carnival、chinesegarden、cowboy、dark、dino、egypt、eighties、fairy、frontyard、future、heian、iceage、kongfu、losantosvice、lostcity、lunarrainbowmarket、mausoleum、memorytour、modern、muji、pirate、plantagenet、renai、sky、steam
- 状态：`meta`；对应原版模块：—；参数类：—
- 样例：12、16、18、15、20、14、0、8

### `package`

- 出现：1809 关；世界：beach、carnival、chinesegarden、cowboy、dark、dino、egypt、eighties、fairy、frontyard、future、heian、iceage、kongfu、losantosvice、lostcity、lunarrainbowmarket、mausoleum、memorytour、modern、muji、pirate、plantagenet、renai、sky、steam
- 状态：`meta`；对应原版模块：—；参数类：—
- 样例："pkg_0325"、"pkg_0336"、"pkg_0337"、"pkg_0338"、"pkg_0339"、"pkg_0326"、"pkg_0327"、"pkg_0328"

### `rail`

- 出现：192 关；世界：beach、carnival、chinesegarden、cowboy、dark、dino、egypt、eighties、fairy、frontyard、future、heian、iceage、kongfu、losantosvice、lostcity、lunarrainbowmarket、mausoleum、memorytour、modern、pirate、plantagenet、renai、sky、steam
- 状态：`flag_only`；对应原版模块：Rails、CowboyRails、Railcart、Railcart1；参数类：RailcartProperties
- 样例：true

### `source`

- 出现：1809 关；世界：beach、carnival、chinesegarden、cowboy、dark、dino、egypt、eighties、fairy、frontyard、future、heian、iceage、kongfu、losantosvice、lostcity、lunarrainbowmarket、mausoleum、memorytour、modern、muji、pirate、plantagenet、renai、sky、steam
- 状态：`meta`；对应原版模块：—；参数类：—
- 样例："obb"、"obb-synth"

### `special`

- 出现：45 关；世界：beach、carnival、cowboy、dark、egypt、frontyard、future、heian、kongfu、losantosvice、lunarrainbowmarket、mausoleum、modern、muji、pirate、sky、steam
- 状态：`flag_only`；对应原版模块：VaseBreakerArcade、VaseBreakerProps、TestVaseBreaker；参数类：VaseBreakerPresetProperties
- 样例：["IsVasebreaker"]

### `stage`

- 出现：1809 关；世界：beach、carnival、chinesegarden、cowboy、dark、dino、egypt、eighties、fairy、frontyard、future、heian、iceage、kongfu、losantosvice、lostcity、lunarrainbowmarket、mausoleum、memorytour、modern、muji、pirate、plantagenet、renai、sky、steam
- 状态：`data`；对应原版模块：StageModule；参数类：StageModuleProperties、BeachStageProperties、EgyptStageProperties、EightiesStageProperties、ModernStageProperties、FrontLawnStageProperties、FutureStageProperties、IceAgeStageProperties、LunarStageProperties、HeroesStageProperties、WestStageProperties
- 样例："BeachStage"、"BeachUBStage"、"BeachDMGStage"、"BeachBossStage"、"DeepseaStage"、"DeepseaLandStage"、"BeachTeaserStage"、"BeachMiniGameStage"

### `suppressFlagZombie`

- 出现：271 关；世界：beach、carnival、chinesegarden、cowboy、dark、dino、egypt、eighties、fairy、frontyard、future、heian、iceage、kongfu、lostcity、lunarrainbowmarket、mausoleum、memorytour、modern、muji、pirate、plantagenet、renai、sky、steam
- 状态：`flag_only`；对应原版模块：—；参数类：WaveManagerProperties
- 样例：false、true

### `vasebreaker`

- 出现：47 关；世界：beach、carnival、cowboy、dark、egypt、frontyard、future、heian、kongfu、losantosvice、lunarrainbowmarket、mausoleum、modern、muji、pirate、plantagenet、sky、steam
- 状态：`flag_only`；对应原版模块：VaseBreakerArcade、VaseBreakerProps、TestVaseBreaker；参数类：VaseBreakerPresetProperties、VaseBreakerEndlessProperties
- 样例：true

### `wave_count`

- 出现：1809 关；世界：beach、carnival、chinesegarden、cowboy、dark、dino、egypt、eighties、fairy、frontyard、future、heian、iceage、kongfu、losantosvice、lostcity、lunarrainbowmarket、mausoleum、memorytour、modern、muji、pirate、plantagenet、renai、sky、steam
- 状态：`meta`；对应原版模块：—；参数类：—
- 样例：12、16、18、14、20、13、15、8
