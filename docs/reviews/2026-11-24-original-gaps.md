# 原版 ↔ 客户端字段级差距盘点（2026-11-24）

**一句话结论**：12 个实体里能逐字段对上的只有 **13075** 处；原版有值、客户端没有字段的有 **793** 处，客户端自创字段 **12210** 处；13 个子系统里 **7** 个是原版有、客户端整块没有。

本次盘点扫描原版 **2116** 张 pkg 表（其中关卡定义 1809 个文件 / 41218 个对象），客户端读 `content/*.json` 与 1809 个关卡文件。

## 一、方法与口径

- 基准：只认 `work/obb_packages/pkg_*.json`；客户端字段一律从 `content/**` 读，不抄任何旧文档数字。
- 关联键：plants/zombies 走 `id_mapping.csv`（exact + manual）；levels/waves/stars 走客户端 `extra.package`；shop 走 `sku`；worlds 走世界名 + 别名；armor 用美术名去 `ARMOR` 后缀；projectiles 用类名小写；fusion 用配方键 + 出现序。
- 计数含义：`mapped` = 两侧都有值；`packOnly` = 原版有值而客户端缺字段（worlds/shop/armor/projectiles/bosses 还把「原版独有对象」计入）；`clientOnly` = 客户端有值而原版缺字段；`agree` = 两侧标量相等。
- 只读：本工具不写 `content/**`、不写 `native/src/**`。
- 派生字段：`field` 以 `_` 开头的是工具算出来的比较量（例如 `_levelEvents` = 原版 `m_eventList` 里 `m_eventType == "level"` 的节点数），不是原版字段名，也不计入 pack-only 字段清单。

## 二、字段级差距总表

按实体分组，`—` 表示客户端字段在原版没有对应字段（纯 authored）。`plantfood` 两行是 `plants` 的子集口径（只看有 `plantfood` 标记或原版有养料记录的株），因此与 `plants` 的部分行数字重合。

| 实体 | 客户端字段 | 原版字段 | 关联数 | mapped | packOnly | clientOnly | agree |
|---|---|---|---|---|---|---|---|
| plants | cost | Cost | 147 | 44 | 0 | 103 | 42 |
| plants | hp | Hitpoints | 147 | 44 | 0 | 103 | 42 |
| plants | almanac_no | IntegerID | 147 | 44 | 0 | 103 | 1 |
| plants | cooldown | PacketCooldown | 147 | 44 | 0 | 103 | 40 |
| plants | plantfood | PlantFoodDurationSeconds | 147 | 17 | 6 | 118 | 1 |
| plants | art | PopAnim | 147 | 44 | 0 | 103 | 0 |
| zombies | armor | ArmorType | 55 | 0 | 0 | 16 | 0 |
| zombies | eat_dps | EatDPS | 55 | 28 | 0 | 27 | 24 |
| zombies | hp | Hitpoints | 55 | 28 | 0 | 27 | 28 |
| zombies | art | PopAnim | 55 | 28 | 0 | 27 | 0 |
| zombies | speed | Speed | 55 | 28 | 0 | 27 | 26 |
| levels | flags | FlagCount | 1809 | 179 | 0 | 1630 | 0 |
| levels | deck | InitialPlantList | 1809 | 345 | 0 | 1464 | 0 |
| levels | extra.level_number | LevelNumber | 1809 | 1777 | 0 | 32 | 0 |
| levels | seed_bank | PresetPlantList | 1809 | 790 | 0 | 1019 | 0 |
| levels | sun | StartingSun | 1809 | 377 | 0 | 1432 | 0 |
| levels | waves | WaveCount | 1809 | 1586 | 0 | 223 | 0 |
| shop | one_time | IsOneTimePurchase | 585 | 1 | 0 | 584 | 1 |
| shop | item_type | ObjectType | 585 | 565 | 0 | 20 | 565 |
| shop | price | Price | 585 | 565 | 0 | 20 | 10 |
| shop | price_gems | PriceGems | 585 | 562 | 0 | 23 | 2 |
| shop | price_mints | PriceMints | 585 | 565 | 0 | 20 | 2 |
| shop | sku | Sku | 585 | 565 | 0 | 20 | 565 |
| worlds | levels | _levelEvents | 26 | 22 | 0 | 4 | 0 |
| worlds | map | m_mapPieces | 26 | 21 | 23 | 5 | 0 |
| worlds | id | m_worldName | 26 | 22 | 24 | 4 | 19 |
| armor | metal | ArmorFlags | 16 | 2 | 32 | 14 | 0 |
| armor | armature | ArmorLayers | 16 | 1 | 27 | 7 | 0 |
| armor | art | ArmorType | 16 | 2 | 34 | 14 | 0 |
| armor | hp | BaseHealth | 16 | 2 | 34 | 14 | 0 |
| projectiles | plants | BaseDamage | 11 | 0 | 127 | 11 | 0 |
| projectiles | projectile | ClassName | 11 | 0 | 131 | 11 | 0 |
| projectiles | plants | CollisionFlags | 11 | 0 | 130 | 11 | 0 |
| bosses | id | ZombossMechType | 26 | 0 | 71 | 26 | 0 |
| bosses | hp | ZombossPhaseCount | 26 | 0 | 71 | 26 | 0 |
| bosses | phases | ZombossPhases | 26 | 0 | 71 | 26 | 0 |
| plantfood | plantfood | PlantFoodDurationSeconds | 147 | 17 | 6 | 118 | 1 |
| plantfood | plantfood | PlantFoodPlayCount | 147 | 14 | 6 | 121 | 11 |
| fusion | ingredients | FusionPlant | 85 | 85 | 0 | 0 | 0 |
| fusion | result | ResultPlant | 85 | 85 | 0 | 0 | 0 |
| fusion | ingredients | SourcePlant | 85 | 85 | 0 | 0 | 0 |
| waves | flags | FlagCount | 1809 | 179 | 0 | 1630 | 0 |
| waves | waves | WaveManagerProps | 1809 | 1714 | 0 | 95 | 0 |
| waves | waves | Waves | 1809 | 1648 | 0 | 161 | 0 |
| stars | stars | Challenges | 1809 | 950 | 0 | 859 | 0 |
| stars | stars | TargetScore | 1809 | 0 | 0 | 1809 | 0 |

## 三、原版有值、客户端无字段

把已关联原版对象上「有值但没有任何客户端字段对应」的字段按命中数排序，下面取前 12 条；完整清单见 JSON 顶层 `packOnlyFields`（按实体 + 命中数）。

| 实体 | 原版字段 | 命中数 |
|---|---|---|
| levels | Modules | 1806 |
| levels | StageModule | 1806 |
| levels | Loot | 1802 |
| levels | WaveManagerProps | 1714 |
| levels | Waves | 1648 |
| levels | Zombies | 1643 |
| levels | NormalPresentTable | 1635 |
| levels | AdditionalPlantfood | 1362 |
| levels | Challenges | 950 |
| levels | DynamicPlantfood | 305 |
| levels | SuppressPlantfoodPurchase | 276 |
| plants | AnimRigClass | 44 |

共 36 个（实体, 字段）组合有原版值而客户端无字段；这些字段在本版客户端**一个都没有**，是补功能时最直接的缺口来源。典型如植物的 `PlantGridType` / `PlantStats` / `Boosts` / `ZenGarden*`，僵尸的 `WavePointCost` / `Weight` / `CanSpawnPlantFood` / `ScaledProps`。

## 四、客户端独有

| 实体 | 客户端字段 | clientOnly | 说明 |
|---|---|---|---|
| stars | stars | 1809 | 原版 TargetScore 在这些记录上无值（含原版没有该对象的情形） |
| levels | flags | 1630 | 原版 FlagCount 在这些记录上无值（含原版没有该对象的情形） |
| waves | flags | 1630 | 原版 FlagCount 在这些记录上无值（含原版没有该对象的情形） |
| levels | deck | 1464 | 原版 InitialPlantList 在这些记录上无值（含原版没有该对象的情形） |
| levels | sun | 1432 | 原版 StartingSun 在这些记录上无值（含原版没有该对象的情形） |
| levels | seed_bank | 1019 | 原版 PresetPlantList 在这些记录上无值（含原版没有该对象的情形） |
| stars | stars | 859 | 原版 Challenges 在这些记录上无值（含原版没有该对象的情形） |
| shop | one_time | 584 | 原版 IsOneTimePurchase 在这些记录上无值（含原版没有该对象的情形） |
| levels | waves | 223 | 原版 WaveCount 在这些记录上无值（含原版没有该对象的情形） |
| waves | waves | 161 | 原版 Waves 在这些记录上无值（含原版没有该对象的情形） |
| plantfood | plantfood | 121 | 原版 PlantFoodPlayCount 在这些记录上无值（含原版没有该对象的情形） |
| plantfood | plantfood | 118 | 原版 PlantFoodDurationSeconds 在这些记录上无值（含原版没有该对象的情形） |
| plants | plantfood | 118 | 原版 PlantFoodDurationSeconds 在这些记录上无值（含原版没有该对象的情形） |
| plants | cost | 103 | 原版 Cost 在这些记录上无值（含原版没有该对象的情形） |
| plants | hp | 103 | 原版 Hitpoints 在这些记录上无值（含原版没有该对象的情形） |
| plants | almanac_no | 103 | 原版 IntegerID 在这些记录上无值（含原版没有该对象的情形） |
| plants | cooldown | 103 | 原版 PacketCooldown 在这些记录上无值（含原版没有该对象的情形） |
| plants | art | 103 | 原版 PopAnim 在这些记录上无值（含原版没有该对象的情形） |
| waves | waves | 95 | 原版 WaveManagerProps 在这些记录上无值（含原版没有该对象的情形） |
| levels | extra.level_number | 32 | 原版 LevelNumber 在这些记录上无值（含原版没有该对象的情形） |

- 商品：客户端 585 件、原版 565 件，`sku` 对齐后 **20** 件是客户端自创（`source` 标 legacy）。
- 定价：原版 `Price` 565 件里 **561** 件是 0、其余 4 件是 99999；客户端 `price`/`price_gems`/`price_mints` 是自创数值，不能从原版抄。
- 世界：客户端 26 个、原版 46 个；别名归一（gta/skycity/rainbowmarket/kungfu）后能对上 **22** 个，`frontyard`/`future`/`iceage`/`renai` 在原版 `WorldData` 里没有同名行，`order` 这类排序字段原版也没有。
- 世界节点 vs 关卡数：对上的 22 个世界里，原版 `m_eventList` 的 `level` 事件合计 **555** 个，客户端 `levels` 合计 **1432** 关，**逐世界全部不等**（例如 egypt 原版 26 个节点、客户端 84 关）——客户端关卡是按 `content/levels/*.json` 补出来的，不是原版世界地图节点的投影。
- 弹道：客户端 11 个语义名（`pea`/`pea_snow`/`cabbage`…），原版是 131 个 `ClassName`，**零重叠**——客户端弹道名是自创词汇表，不是原版 `ProjectilePropertySheet` 的投影。

## 五、子系统清单

判断标准：原版有整套表/字段，而客户端连一个对应字段都没有。`presentInPack = unverified` 表示本工具在 2116 张表里没找到可复现证据，不写猜测。

| 子系统 | 原版有 | 客户端有 | 证据（前 3 条） |
|---|---|---|---|
| achievements_quests | True | False | 字段索引（1 张表） · Quests = 1；字段索引（1 张表） · QuestCategories = 2；字段索引（1 张表） · DailyQuestScheduleDefinitions = 1 |
| almanac_entries | True | True | 字段索引（2 张表） · AlmanacDataEntries = 167；字段索引（33 张表） · AlmanacBackdropName = 413；字段索引（1 张表） · HideFromAlmanac = 6 |
| daily_season | True | False | 字段索引（1 张表） · SeasonDefinitions = 1；字段索引（1 张表） · EndOfSeasonManagement = 1；字段索引（1 张表） · DailyQuestScheduleDefinitions = 1 |
| key_drops | True | True | 字段索引（1 张表） · LevelLootKey = 3；pkg_2107_WorldData.m_eventList · key_gate = 27 |
| level_rewards | True | False | 字段索引（1802 张表） · Loot = 1802；字段索引（476 张表） · FirstRewardType = 476；字段索引（458 张表） · FirstRewardParam = 458 |
| mower_config | True | False | 字段索引（4 张表） · UnlimitedMowers = 6；字段索引（6 张表） · MowerPopAnim = 46；字段索引（5 张表） · MowerActivatedAudioEvent = 34 |
| plantfood_drop | True | False | 字段索引（1363 张表） · AdditionalPlantfood = 8351；字段索引（305 张表） · DynamicPlantfood = 1163；字段索引（180 张表） · PlantfoodToSpawnCount = 180 |
| plantfood_purchase | True | False | 字段索引（276 张表） · SuppressPlantfoodPurchase = 276；字段索引（132 张表） · SuppressAccountUpgrades = 132；字段索引（86 张表） · StartingPlantfood = 90 |
| seeds_and_vases | True | True | 字段索引（46 张表） · Vases = 46；字段索引（46 张表） · NumColoredPlantVases = 46；字段索引（46 张表） · NumColoredZombieVases = 46 |
| shop_products | True | True | 字段索引（1 张表） · Sku = 565；字段索引（1 张表） · Price = 565；字段索引（1 张表） · PriceCoins = 565 |
| sound_events | True | False | 字段索引（17 张表） · ImpactSoundEvent = 478；字段索引（2 张表） · DropSoundEvent = 16；字段索引（10 张表） · SoundOnStart = 51 |
| star_challenges | True | True | 字段索引（950 张表） · Challenges = 954；字段索引（15 张表） · TargetScore = 17；字段索引（17 张表） · ScoringRulesType = 17 |
| zen_garden | True | True | 字段索引（1 张表） · ZenGardenSproutWeight = 371；字段索引（1 张表） · ZenGardenBoostCost = 371；字段索引（1 张表） · ZenGardenDurationOverrideSeconds = 359 |

- **achievements_quests**：原版有 QuestMgr / DailyQuestSchedule / CompletionAchievement；客户端没有任何任务或成就表。
- **almanac_entries**：原版图鉴是 PlantAlmanacData（167 条）；客户端 almanac.json 只有 desc/tip 文案，图鉴 UI 未实现。
- **daily_season**：原版有 Joust 赛季与每日任务排期；客户端没有赛季/每日数据。
- **key_drops**：原版世界门要钥匙（WorldData key_gate），关卡掉落也有 key 通道；客户端只有世界地图 key_required 布尔。
- **level_rewards**：原版关卡带掉落表/首通奖励/重复奖励；客户端关卡 JSON 只有 id/world/index/sun/deck/waves/flags/seed_bank/extra（bosses.json 的 reward 是 Boss 击杀奖励，不是关卡结算表，不计入）。
- **mower_config**：原版关卡可配小推车数量/动画/音效；客户端只有固定 5 台（stars 里用 mowers 当目标）。
- **plantfood_drop**：原版按波次/关卡投放养料；客户端只有 plants[].plantfood 布尔开关，没有投放节奏。
- **plantfood_purchase**：原版有「是否允许买养料」的关卡级开关；客户端没有货币与购买链路。
- **seeds_and_vases**：原版砸罐子/种子掉落是关卡数据；客户端只有 minigames.json 的 45 关预排罐子。
- **shop_products**：原版 StoreProductProps 565 件；客户端 shop.json 585 件，其中 565 个 sku 对齐、20 个是客户端独有。
- **sound_events**：原版每类实体带音效事件名（Impact/Drop/OnEat…）；客户端 content 里没有任何音效字段。
- **star_challenges**：原版星章目标在 LevelDefinition.Challenges；客户端 stars.json 是 1809 关 × 3 条自创目标。
- **zen_garden**：原版花园参数挂在 PlantPropertySheet 的 ZenGarden* 字段；客户端 garden.json 是 8 盆的自创简化模型。

## 六、文档更正

本节对 `docs/COMPLETENESS.md` 里与本工具有关的数字做**实测复核**；数字对不上的，以本工具实测为准。

| 位置 | 文档原文（片段） | 实测 | 结论 |
|---|---|---|---|
| docs/COMPLETENESS.md:13 | 339 植物 / 1127 僵尸 / 1809 关 / 85 融合 | 339 植物 / 1127 僵尸 / 1809 关 / 融合 85 对 | 文档已变动，需复核 |
| docs/COMPLETENESS.md:46 | │ `pkg_2074_PlantType` │ 339 │ | 339（类型名 339 个） | 文档已变动，需复核 |
| docs/COMPLETENESS.md:47 | 1127（1125 唯一 id） | 1127 条对象 / 1125 个类型名 | 文档已变动，需复核 |
| docs/COMPLETENESS.md:136 | 商店（585 商品） | 客户端 585 件（其中 565 个 sku 对得上原版 StoreProductProps） | 文档已变动，需复核 |

补充更正：

- `docs/COMPLETENESS.md:227` 的「20 个 content 僵尸 id 在 sheet zombies[] 里也有同名行」讲的是**护甲桥**那次修复（`cowboy → CowboyHatDefault`）。本工具另有一条独立的 20：`content.pack` 里精确存在 **20** 个 content 僵尸 id，而字段级关联能对上 **28** 个（exact + manual）。两者出处不同，不能互换。
- `docs/COMPLETENESS.md:136` 的「585 商品」是**客户端**数量；原版 `StoreProductProps` 是 **565** 件，565 个 sku 对齐，差 **20** 件是客户端自创。
- 「字段级差距」此前从未测过：本工具首次给出 `packOnly` / `clientOnly` 的逐字段计数（第二节），后续补功能以此为清单。

## 七、复现

```
python tools/contentc/original_gaps.py --check    # 重算并与盘上 JSON/报告逐字节比对
python -m unittest tools.tests.test_original_gaps -v
```

`--check` 不一致时 exit 1；找不到 `work/obb_packages` 时 exit 2。
