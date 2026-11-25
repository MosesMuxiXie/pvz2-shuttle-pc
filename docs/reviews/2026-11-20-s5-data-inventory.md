# S5.2 元素 / 养料 / Boss 数据盘点

任务：判断这三项在原版数据里**到底有什么**，从而决定 S5 里哪些可以数据驱动、哪些必须 authored。
扫描对象：`work/obb_packages` 全量 **2117** 个 JSON（2116 个 `pkg_*.json` + 提取清单 `_index.json`，清单内 `ok=2116 fail=0`，共 **121** 个 objclass）。
工具：`tools/contentc/s5scan.py`（本次新增，唯一扫描器）→ 产物 `native/generated/s5_data_gaps.json`；测试 `tools/tests/test_s5_inventory.py`（18 项）。

## 0. 结论总表

| 概念 | 结论 | 关键数字 | 能数据驱动的部分 | 必须 authored 的部分 |
|---|---|---|---|---|
| 元素 | **只能 authored** | 相关 objclass 只有 1 个，且 21 条记录**全空** | 无（0 个元素字段） | 元素类型、克制表、反应规则、每株元素的挂载 |
| 养料 | **部分可行** | 6 条 `Type=="plantfood"` action；`PlantFoodDurationSeconds` 147 株、`PlantFoodPlayCount` 185 株有值 | 动画时长/播放次数、6 株的养料弹道、开场养料数量 | 其余 333 株的养料**效果**（杀伤/控制/召唤） |
| Boss | **部分可行** | 23/26 世界有 boss 关；75 条 battle、50 个 mech、258 个阶段、43 个 Zomboss 类 | 每阶段 HP、每阶段行动轮转、刷怪/冲锋/火球参数、出场列位 | 3 个世界的 Boss 入场、26 条 Boss 的编排与文案、legacy 世界的 Boss 绑定 |

复现全部三个结论（一条命令，约 10 秒）：

```
python tools/contentc/s5scan.py --gaps          # 打印 s5_data_gaps.json 全文（verdict 在此）
python tools/contentc/s5scan.py --write-gaps    # 重新生成 native/generated/s5_data_gaps.json
```

---

## 1. 元素（Element / 火·水·风·电·毒·暗·幻）

### 1.1 找到的表

| 表 | 位置 | objclass | alias | 记录数 | 字段数 |
|---|---|---|---|---|---|
| ElementReactionModuleProperties | `pkg_0234_DisableSkipLevelModuleProperties.json` + `pkg_0398..pkg_0417_LevelDefinition.json` | `ElementReactionModuleProperties` | `ElementReactionModule` | **21** | **0** |

21 条记录分布在 21 个包里（1 个聚合包 `pkg_0234` + 20 个关卡包 `pkg_0398`…`pkg_0417`），**每一条 `objdata` 都是 `{}`**：

```
found=21  withFields=0  empty=21  objclasses={"ElementReactionModuleProperties": 21}
records: pkg_0234 alias=ElementReactionModule fields=[] empty=True
         pkg_0398 alias=ElementReactionModule fields=[] empty=True
         ...
```

即：原版只保留了一个**空壳关卡模块开关**（关卡可以用 `ElementReactionModule` 标记"本关启用元素反应"），但反应规则、元素类型、伤害加成**一条都没有**。

### 1.2 元素属性在植物表里也不存在

`pkg_2073_PlantPropertySheet.json` 里键名含 `element` 的字段：**0 个**。

```
python tools/contentc/s5scan.py --needle elements --sheet --limit 3
# files=2117 parsed=2117
# tables (5): ElementReactionModuleProperties, MagicVineProjectileProps,
#             PowerupTypeFlamethrower, ZombieCarnieMagicianDoveProps, ZombieCarnieMagicianProps
```

那 5 个"命中"的表要逐个排除，**没有一个是元素体系**：

| 表（pkg 位置） | 为什么被命中 | 是否元素 |
|---|---|---|
| `ElementReactionModuleProperties`（pkg_0234/0398-0417） | 名字里有 Element | 空壳开关，无字段 |
| `PowerupTypeFlamethrower`（`pkg_2078_PowerupTypeWizardFinger.json`） | needle `fire` 命中 Flamethrower | 否，全局技能 |
| `MagicVineProjectileProps`（`pkg_2082_ProjectilePropertySheet.json`，alias `MagicVineProjectile`/`MagicVinePlantfoodProjectile`） | needle `magic` 命中 | 否，弹道 |
| `ZombieCarnieMagicianProps` / `ZombieCarnieMagicianDoveProps`（pkg_2112） | needle `magic` 命中 Magician（魔术师僵尸） | 否，僵尸行为 |
| `ZombossFireActionDefinition`（pkg_0256 等） | needle `fire` 命中 Fire | 否，Boss 火球 |

再加检索确认（**2117 个文件中 0 命中**，检索词为 `elemental`、`elementtype`、`singlegem`、`elem`）：元素没有任何同义字段。

`pkg_2083_PlantFusionConfig.json`（217 条，`FusionPairs[SourcePlant/FusionPlant/ResultPlant/FusionOnlyHasResultPlant]`）也没有元素字段——**融合不是元素体系**。

### 1.3 结论

> **元素：只能 authored。**
> 数据驱动可行的字段：**无**。原版数据里唯一的元素痕迹是一个 21 次出现的空 `ElementReactionModule` 开关（`pkg_0234_DisableSkipLevelModuleProperties` / `pkg_0398..0417_LevelDefinition`），没有任何元素类型、克制关系、加成数值。
>
> 附带事实：客户端 `content/plants.json` 147 条里只有 **2 条**带 `element` —— `helioscabbage`(fire/lob/Lobber)、`fireflerry`(fire/shoot/Peashooter)，且都是 S2 自造，与 pack 无关。S5 若要做元素，等于从零设计一套数值，不能声称"照原版"。

取证命令：`python tools/contentc/s5scan.py --needle elements --sheet --limit 3`（上表）、`python tools/contentc/s5scan.py --gaps`（`elements.verdict == "authored"`、`elements.driven == []`）。
测试断言：`test_elements_are_authored`、`test_element_module_is_an_empty_flag`、`test_no_element_key_on_any_plant`、`test_no_element_sheet_in_the_manifest`。

---

## 2. 养料（Plant Food）

### 2.1 找到的表

| 表 | 位置 | 作用的对象 | 关键字段 | 记录 / 非空 |
|---|---|---|---|---|
| PlantPropertySheet | `pkg_2073_PlantPropertySheet.json`（398 个对象，343 个带 `Actions`） | 339 株植物 | `PlantFoodDurationSeconds`、`PlantFoodPlayCount`、`Actions[].Type=="plantfood"` | 见下 |
| PlantType | `pkg_2074_PlantType.json` | 339 株植物 | `TypeName`、`Properties`（RTID） | 339 / 339 |
| LevelMutatorStartingPlantfoodProps | `pkg_0236_LevelMutatorStartingPlantfoodProps.json` | 关卡开场 | `OverrideStartingPlantfood0..2` | 3 |
| LevelMutatorPowerupSetProps | `pkg_0236_LevelMutatorStartingPlantfoodProps.json` | 关卡 | `OverridePowerupsDisabled` | 1 |
| CollectablePlantfoodType | `pkg_0010_CollectableType.json` | 掉落物 | `CollectablePlantfoodType` | 1 |
| HotUIPowerUpButtonProperties | `pkg_0051_HotUIWidgetProperties.json`、`pkg_0141_HotUIImageProperties.json` | UI | `PowerUpButton`、`PowerUpReward` | 2 |
| PowerPropsDamageRadius / PowerupTypeWizardFinger | `pkg_2077_PowerPropsDamageRadius.json`、`pkg_2078_PowerupTypeWizardFinger.json` | 割草机/全局技能 | 伤害半径、法师手指 | — |

**没有独立的"养料属性表"**：`pkg_2073` 里键名含 `plantfood` 的列一共 133 个（含注释键），全部是**逐株的标量列**，不是一张 per-plantfood 表。

### 2.2 逐株可用的养料列（pkg_2073，带取值）

| 字段 | records | nonEmpty | 取值样例（带植物） |
|---|---|---|---|
| `PlantFoodDurationSeconds` | 155 | **147** | `2.5 @LittleRepeaterDefault`、`2.4 @CornucopiaDefault` |
| `PlantFoodPlayCount` | 189 | **185** | `1 @ElderbarrierDefault`、`1 @ParadoxPultDefault` |
| `NetworkedPlantFoodPlayCount` | 1 | 1 | （单株网络同步用） |
| `MaxPlantFoodCharge` | 1 | 1 | `1 @MiniShroomDefault` |
| `MaxPlantFoodObjects` | 1 | 1 | `20 @MagnetShroomDefault` |
| `MaxPlantfoodKills` | 1 | 1 | `1 @GrimroseDefault` |
| `IsFromPlantFood` | 3 | 1 | `true @HollyShieldPlantfood` |
| `FromPlantfood` | 2 | 2 | `{EatDuration:0, IndifferenceDuration:1.5, LaneChangeDuration:…} @GarlicDefault`、`@SpecialGarlicDefault` |
| `PlantFoodCloudDuration` | 2 | 2 | — |
| `PlantfoodRainDuration` / `PlantfoodStallDuration` | 1 / 1 | 1 / 1 | — |

覆盖率：`PlantFoodDurationSeconds` 只覆盖 **147 / 339** 株（43%），`PlantFoodPlayCount` 覆盖 185 / 339。

### 2.3 特别核对 (a)：6 条 `Type=="plantfood"` 的 action 属于哪些植物

`pkg_2073_PlantPropertySheet.json` 里 343 个对象带 `Actions`，其中 `Type=="plantfood"` 的只有 **6 条**，索引都是 1。归属通过 `pkg_2074_PlantType.json` 的 `TypeName` + `Properties = RTID(<props>@PlantProperties)` 反查得到：

| # | Action alias | 所在 Props | 植物 id | Projectile | 其它字段 |
|---|---|---|---|---|---|
| 1 | `CattailDefault` | HomingThistleProps | **sungun** | `RTID(CattailPlantfood@ProjectileTypes)` | `CooldownTimeMax 2`、`CooldownTimeMin 1.7`、`InitialMinCooldownTime 0`、`SpawnOffset {x:35,y:-32}`、`ProjectileLaunchSound ""` |
| 2 | `DartichokeDefault` | DartichokeProps | **dartichoke** | `RTID(DartichokeLeafPerfect@ProjectileTypes)` | 同上冷却三件套 + `SpawnOffset` |
| 3 | `DraftodilDefault` | DraftodilProps | **draftodil1** | `RTID(DraftodilPlantfoodDefault@ProjectileTypes)` | 只有 `Type`/`Projectile`/`SpawnOffset {x:10,y:-25}`（无冷却） |
| 4 | `HomingThistleDefault` | HomingThistleProps | **homingthistle** | `RTID(HomingThistlePlantfood@ProjectileTypes)` | `CooldownTimeMax 2`、`CooldownTimeMin 1.7`、`InitialMinCooldownTime 0` |
| 5 | `MagnetFruitDefault` | MagnetFruitProps | **magnetfruit** | `RTID(MagnetFruitGiantShot@ProjectileTypes)` | 冷却三件套 |
| 6 | `TurrheumImmobileDefault` | DartichokeProps | **rheumnobile** | `RTID(TurrheumImmobileProjectilePlantfood@ProjectileTypes)` | 冷却三件套 |

`Actions[].Type=="plantfood"` 的**全字段集合**（6 条并集，7 个键）：
`Type`、`Projectile`、`SpawnOffset`、`CooldownTimeMin`、`CooldownTimeMax`、`InitialMinCooldownTime`、`ProjectileLaunchSound`。
（`DraftodilDefault` 只有前 3 个 → 代码必须允许冷却字段缺省。）

**含义**：只有这 6 株的养料是"发射一枚真弹道"这种可纯数据驱动的形态；其余 333 株的养料效果在原版数据里没有结构化描述，只在美术/动画里体现。

### 2.4 结论

> **养料：部分可行。**
> 数据驱动可行：
> ① 6 株（`sungun`/`dartichoke`/`draftodil1`/`homingthistle`/`magnetfruit`/`rheumnobile`）的养料 = 弹道 action，7 个字段全部可读（`pkg_2073` Actions）；
> ② 147 株的 `PlantFoodDurationSeconds`、185 株的 `PlantFoodPlayCount`（动画时序）；
> ③ 关卡开场养料数量（`pkg_0236_LevelMutatorStartingPlantfoodProps` 的 `OverrideStartingPlantfood0..2`）；
> ④ 掉落物/UI 入口（`pkg_0010_CollectablePlantfoodType`、`pkg_0051`/`pkg_0141` HotUIPowerUpButton）。
>
> 必须 authored：其余 333 株的养料**效果**（伤害、控制、召唤、变形）、333 株的时长（缺 `PlantFoodDurationSeconds`）、以及所有养料的中文文案。`content/plants.json` 目前每株只有一个 `plantfood: bool`，没有数值——S5 若要做数值化养料，只能 authored 或按族给默认值。

取证命令：`python tools/contentc/s5scan.py --needle plantfood --sheet --limit 3`、`python tools/contentc/s5scan.py --gaps`（`plantfood.verdict == "partial"`）。
测试断言：`test_plantfood_has_exactly_six_actions`、`test_plantfood_actions_resolve_to_six_plants`、`test_plantfood_duration_and_playcount_columns_exist`、`test_plantfood_verdict_is_partial`。

---

## 3. Boss

### 3.1 找到的表

| 表 | 位置 | 作用 | 记录数 |
|---|---|---|---|
| ZombossBattleModuleProperties | 各 Boss 关卡的 `pkg_NNNN_LevelDefinition.json`（如 `pkg_0331`、`pkg_0562`、`pkg_1219`） | 一场 Boss 战的入场配置 | 75 |
| ZombossRiftBattleModuleProperties | `pkg_0576_LevelDefinition.json` 等 Rift 关卡 | Rift 版 Boss 战 | 含在上面 75 内 |
| ZombieZombossMech*Props | `pkg_2112_ZombiePropertySheet.json` 及关卡包 | 僵尸形态：每阶段 HP + 行动轮转 | 168（82 个带 `Stages`，共 258 阶段） |
| Zomboss\*ActionDefinition（38 个类） | `pkg_2111_ZombieWalkActionDefinition.json`、`pkg_0256`/`pkg_1092`/`pkg_1212` 等 `LevelDefinition` | 具体攻击/召唤/移动动作 | 例：Fire 76、Summon 127、Spawn 119、Rush 55、DropZombie 34 |
| BossIconModuleProps / LevelMutatorRiftZombossPhasesProps / RiftZombossRewards / PennyPerkBossBusterCannonProperties | `pkg_0236`、`pkg_2097_RiftZombossRewards.json`、`pkg_2093_PennyPerkTrafficJamProperties.json` | UI/奖励/关卡修饰 | 见 gaps |

`boss` 相关 objclass 共 **70** 个（名字含 `Zomboss` 的 61 个），其中 `Zomboss*` 前缀的 **43** 个（= `gaps.boss.actionClasses`）：5 个非攻击类（`ZombossBattleIntroProperties`、`ZombossBattleModuleProperties`、`ZombossRiftBattleModuleProperties`、`ZombossRiftPointOfLossModuleProperties`、`ZombossVictoryOutroProperties`）+ 38 个 `Zomboss*ActionDefinition`。

### 3.2 可用字段与取值样例

**(a) 入场/场地位置 —— `ZombossBattleModuleProperties`**

| 包 | mech | `ReservedColumnCount` | `SpawnGridPosition` | `DeathRow/Column` | stage |
|---|---|---|---|---|---|
| `pkg_0331_LevelDefinition` | `zombossmech_beach` | 3 | {mX:6, mY:3} | 3 / 5 | BeachBossStage |
| `pkg_0562_LevelDefinition` | `zombossmech_egypt` | 2 | {mX:6, mY:3} | 3 / 5 | EgyptStage |
| `pkg_1219_LevelDefinition` | `zombossmech_skycity` | 3 | {mX:7, mY:2} | 3 / 5 | SkyCityBossStage |
| `pkg_1328_LevelDefinition` | `zombossmech_heian` | 3 | {mX:0, mY:3} | 3 / 5 | HeianBossStage |
| `pkg_1593_LevelDefinition` | `kongfu_zomboss_blade` | 2 | {mX:6, mY:3} | 3 / 5 | KongfuBossStage |
| `pkg_0576_LevelDefinition` | `zombossmech_egypt_rift` | 2 | {mX:6, mY:3} | 3 / 5 | RiftStage（`phases=3`） |

**(b) 每阶段血量 —— `ZombieZombossMech*Props.Stages[].HitPoints`**

| 对象 | 阶段数 | HP 序列 |
|---|---|---|
| `ZombieZombossMechEgypt` | 3 | **4000 / 8000 / 6500** |
| `ZombieZombossMechSkyCity` | 3 | **10000 / 14000 / 20000** |
| `ZombieZombossMechSteam` | 3 | **13000 / 17000 / 25000** |
| `ZombieZombossMechHeian` | 3 | 7500 / 9750 / 12000 |
| `ZombieZombossMechBeach` | 3 | 10000 / 14000 / 18000 |
| `ZombieZombossMechEighties` | 5 | 2500 / 3000 / 3500 / 4000 / 5500（同名另一份 4500…7000） |
| `ZombieZombossMechRenai` | 6 | 6000 / 21300 / 8000 / 21300 / 11000 / 21300 |
| `ZombieZombossMechFairyTaleHead1` | 1 | 2147483647（无敌演出段） |

每阶段还带 `Actions`（RTID 列表）、`IdleTime`、`StunTime`、`RetreatAction`、`DamageIndex*` → **阶段机可数据驱动**。

**(c) 攻击参数 —— `ZombossFireActionDefinition`（76 条，15 个字段）**

`Weight 4`、`RepeatMin 0`、`RepeatMax 1`、`FireMinColumn 3 @ZombossChineseGardenFire2`、`FireMaxColumn 4 @ZombossMarketFire1`、`FireRowRange 3`、`FireRocketSpeed 500`、`FireRocketHitTime 0.75`、`FireRocketCount {Min:2,Max:2} @ZombossMarketFire1`、`FireRocketDropSound "Play_Zomb_Egypt_Zomboss_Attack_Projectile_Impact_Whistle"`、`FireTargetPlantWeight 1`、`FireTargetEmptyWeight 0`、`FireTargetTileWeight`(57)、`FireTargetRailsWeight`(51)、`FireTargetTilesWeight`(19)。

### 3.3 特别核对 (b)：`pkg_2107_WorldData` 里的 boss 事件

`m_eventType` 的全局分布：`level 1248`、`plant 231`、`key_gate 27`、`star_gate 53`、`worldgate 17`、`giftbox 8`、`costume 7`、`doodad 6`、`upgrade 2`。
**没有 `boss` / `zomboss` / `boss_start` 这种事件类型**——命中只来自关卡事件的 `m_name`/`m_dataString` 里带 boss 字样，一共 **4 条**，全部 `type=="level"`：

| 世界 | worldId | 事件名 | dataString | 地图坐标 |
|---|---|---|---|---|
| egypt | 2 | `egypt_level_boss` | `egypt15` | (3617, 362) |
| dark | 6 | `renai_level_boss` | `renaiboss` | (7715, 312.33) |
| skycity | 70 | `skycity_level_boss` | `skycity20` | (6116, 446) |
| kongfu | 71 | `kongfu_level_boss` | `kongfu25` | (5176, 408) |

**含义**：26 个客户端 Boss 里，只有 4 个能从世界地图直接定位到具体关卡；其余 22 个必须靠 `ZombossBattleModuleProperties`（75 条）反查"哪个关卡包内嵌了 Boss 模块"来定位。这正是 3.4 里 23/26 的来源。

### 3.4 Boss 关卡的世界分布（按 stage 名推断）

75 条 battle 按世界聚合（**推断**：`stage` → 世界用名字前缀表 `STAGE_WORLD_HINTS`，不是数据字段）：

| 世界 | Boss 关卡数 | 世界 | Boss 关卡数 | 世界 | Boss 关卡数 |
|---|---|---|---|---|---|
| lostcity | 6 | cowboy | 4 | chinesegarden | 4 |
| fairy | 6 | dark | 3 | egypt | 4 |
| lunarrainbowmarket | 5 | future | 4 | eighties | 4 |
| beach | 2 | carnival | 2 | dino | 2 |
| kongfu | 2 | mausoleum | 2 | modern | 2 |
| pirate | 2 | renai | 4 | iceage | 4 |
| heian | 1 | losantosvice | 1 | plantagenet | 1 |
| sky | 1 | steam | 1 | rift / roof | 2 / 2 |
| 未归属（ChildStage/JoustStage/Stage） | 2 / 1 / 1 | | | | |

**26 个客户端世界里 23 个有 Boss 关卡；`frontyard`、`memorytour`、`muji` 三个没有**（它们也没有任何 Zomboss 模块）。

### 3.5 客户端现状（为什么必须 authored 一部分）

`content/bosses.json`（26 条）**完全是合成数据**，与 pack 无对应关系：

```
hp 阶梯: 8000, 8200, 8400, ... 13200        # 每条 +200 的等差数列
phases: 26 条一模一样的 {at 1.0/0.66/0.33, speed 1.0/1.15/1.3, eat_mult 1.0/1.2/1.4}
```

对照 pack 的真实 HP（Egypt 4000/8000/6500、Sky 10000/14000/20000、Steam 13000/17000/25000、Renai 6 阶段），**没有一条对得上**，阶段数也不一致（Renai 真实 6 阶段，客户端 3 阶段）。

### 3.6 结论

> **Boss：部分可行。**
> 数据驱动可行（有表有字段有样例）：
> ① 每场 Boss 的全部阶段 HP（`ZombieZombossMech*Props.Stages[].HitPoints`，82 个对象 / 258 个阶段）；
> ② 每阶段的行动轮转与冷却（同对象 `Actions` / `IdleTime` / `StunTime` / `RetreatAction`）；
> ③ 全部攻击/召唤动作参数（38 个 `Zomboss*ActionDefinition`，如 Fire 76 条、Summon 127 条）；
> ④ 场地占位与出场格（`ZombossBattleModuleProperties.ReservedColumnCount` / `SpawnGridPosition`，75 条）。
>
> 必须 authored：
> ① `frontyard` / `memorytour` / `muji` 三个世界**没有任何** Boss 数据（`content/bosses.json` 里的 `boss_frontyard` 是纯造）；
> ② 22/26 个 Boss 的"世界地图进场点"——WorldData 只给了 4 条 `*_boss` 关卡事件，其余必须靠 stage 名推断（本报告 3.4 的归属即属推断）；
> ③ 26 条 Boss 的名字/称号/中文文案/奖励数值（pack 无本地化 key 关联到 `content/bosses.json` 的 id）；
> ④ 现客户端 HP 阶梯与阶段划分必须整体替换为 pack 值，否则与 3.5 一样是假数据。

取证命令：`python tools/contentc/s5scan.py --needle boss --sheet --limit 3`、`python tools/contentc/s5scan.py --gaps`（`boss.verdict == "partial"`、`battles 75`、`distinctMech 50`、`totalStages 258`、`bossEvents 4`）。
测试断言：`test_boss_battles_are_data`、`test_boss_phases_carry_hitpoints`、`test_boss_events_in_worlddata_stay_four`、`test_boss_covers_most_client_worlds_but_not_all`、`test_boss_action_classes_are_listed`。

---

## 4. 给 S5 的分界建议

| 项 | 数据驱动 | authored | 落地文件 |
|---|---|---|---|
| 元素 | — | 元素表（火/水/风/电/毒/暗/幻 8 系 × 克制关系）、每株元素标签、反应伤害公式 | 新建 `content/elements.json`（S5 自定） |
| 养料 | 6 株弹道型养料（7 字段）、147 株时长、185 株播放次数、开场数量 | 333 株效果数值、全部文案 | `native/generated/plant_food.json` + 手写覆盖表 |
| Boss | 阶段 HP、阶段行动、38 类动作参数、75 条场地占位 | 3 个世界的 Boss、22 条的进场点、全部文案与奖励 | `native/generated/boss_phases.json` + 手写 `content/bosses.json` 修正 |

相关既有产物（勿重复生成）：`native/generated/zombie_classes.json`（1127 僵尸）、`native/generated/plant_families.json`（339 株 11 族）、`native/generated/board_sizes.json`（26 世界棋盘）。

## 5. 0 命中记录（检索词 → 结果）

| 检索词 | 范围 | 结果 |
|---|---|---|
| `element`（键名 + objclass） | 2117 文件 | 命中 21 条，**全部为空 objdata**；作为"元素属性"的字段 0 个 |
| `element`（`pkg_2073` 内） | 1 文件 | **0 命中** |
| `elemental` / `elementtype` / `singlegem` / `elem` | 2117 文件 | **0 命中** |
| `plantfood`（作为独立 sheet 名） | 2117 文件 | **0 张**独立养料属性表（只有逐株列与 6 条 action） |
| `boss`（作为 `m_eventType` 取值） | `pkg_2107_WorldData.json` | **0 条**；boss 仅在 4 条关卡事件的 `m_name` 里出现 |
| `element`（客户端 `content/plants.json`） | 147 条 | 2 条（`helioscabbage`、`fireflerry`），S2 自造 |
