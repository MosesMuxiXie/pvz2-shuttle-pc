# 元游戏数据编译：图鉴 / 花园 / 成就·任务（460.9）

由 `tools/contentc/metagame.py` 生成。数据源 `work/obb_packages`（2116 个 `pkg_*.json`，其中 2115 个能解出对象、1806 个识别为关卡包）；产物 `native/generated/metagame.json`，标记 `metagame-compile-v1`。本文件与 JSON 都由 `--check` 逐字节校验，两次生成字节相同。

## 一、方法与边界

1. **只读**：只解析 `work/obb_packages` 的 JSON 与 `content/plants.json`、`content/zombies.json`；不执行二进制、不联网、不改 `content/**` 与 `native/src/**`。数据源 2116 个 `pkg_*.json` 里，`pkg_0224_unknown.json` 的 `objects` 是空数组（0 条），实际参与解析 2115 个包。
2. **类名自证**：三块表的权威 objclass 是先枚举全部 2115 个可解析包的 objclass 体量后逐个确认的，不按名字猜——花园的 65 条其实是 `CollectableType`，本地没有 `Garden*` 前缀的类；成就则在本地根本没有表。
3. **三条口径**：`levels` 是关卡包文件计数（一包近似一关）；本地化键统一去掉 objdata 里的方括号；推导出来的键/世界/售价都带 `resolved`、`worldSource`、`matchKind` 标记，推断值不写成实测值。
4. **确定性**：`sort_keys` + `indent=1` + UTF-8 + LF + 末尾换行，无时间戳、无绝对路径，`--check` 两次跑必须逐字节相同（见 `tools/tests/test_metagame.py`）。

## 二、任务线索与实测条数的对账

| 任务线索 | 实测的权威表 | 条数 | 对账结论 |
|---|---|---|---|
| `Almanac*` 169 | `PlantAlmanacData`（`pkg_2067`） | 167 | 167 条图鉴条目。线索的 169 是按名字前缀 grep 出来的，多算了 `AlmanacDLHandler`、`HotUIAlmanacVerticalListProperties` 两个非条目对象 |
| `Garden*` 65 | `CollectableType`（`pkg_0010`） | 65 | 条数完全对上，但**不是 Garden 类**：这是掉落/奖励收藏物类型；Zen Garden 自己的属性表在 `pkg_2083` |
| `Quest*`/`Achievement*` 69 | `QuestMgr.Quests` 里带 `CompletionAwards` 的条目 | 69 | 完全对上：240 条 quest 里恰有 69 条带完成奖励；成就本地只有文案键、没有表 |
| `PlayerSegmentRules` 922 | `PlayerSegmentRules`（`pkg_2076`） | 922 | 与本任务三块数据无关，未纳入 |

## 三、图鉴（`almanac`）

植物 167 条 + 僵尸 428 条 = 595 条。僵尸侧从 1127 个 `ZombieType` 里筛出：699 个没有 `ZOMBIE_<TYPE>` 名字键、120 个只有 RTID 生成引用没有自己的定义（见 U1/U9）。

| 字段 | 来源 | 说明 |
|---|---|---|
| `id` | `PlantAlmanacData.aliases[0]` / `ZombieType.TypeName` | 植物是别名，僵尸是类型名 |
| `nameKey`/`descKey`/`tooltipKey` | 推导：裸大写 id + `_DESCRIPTION`/`_TOOLTIP` | 植物键实测 166/167 命中 |
| `descHeaderKey` | `ZOMBIE_<ID>_DESCRIPTION_HEADER` | 僵尸专属，图鉴卡标题行用 |
| `resolved` | 对照 `pkg_0231`（英）/`pkg_0232`（中） | name/desc/tooltip/nameZh/descZh 五个布尔 |
| `world`/`worldSource` | `PlantType.HomeWorld` / `ZombieType.HomeWorld` | 原样保留内部 token，不映射（U7） |
| `levels` | 关卡包扫描（一.3） | 正向引用计数，`PlantExcludeList` 不算出现（U5） |
| `stats` | `AlmanacDataEntries[]` | statType/statName/typeKey/valueKey/levelToUnlock/numberFormat |
| `inPlantTypes` | `PlantType` 是否有同名条目 | false 的条目没有世界与图鉴背景 |

覆盖率：

| 指标 | 值 |
|---|---|
| 植物名字键可解析 | 166/167（99.4%） |
| 植物有世界 | 116/167（69.5%） |
| 僵尸名字键可解析 | 428/428（100.0%） |
| 僵尸有世界 | 428/428（100.0%） |
| 植物有出场关卡 | 149/167（89.2%） |
| 僵尸有出场关卡 | 383/428（89.5%） |

僵尸世界分布（`ZombieType.HomeWorld`，原样 token）：

| 世界 token | 僵尸数 |
|---|---|
| beach | 35 |
| modern | 35 |
| egypt | 31 |
| rift1a | 30 |
| dark | 28 |
| rift2 | 23 |
| eighties | 22 |
| cowboy | 18 |
| lostcity | 18 |
| pirate | 17 |
| future | 17 |
| mausoleum | 16 |
| atlantis | 15 |
| tutorial | 14 |
| chinesegarden | 13 |
| dino | 13 |
| skycity | 12 |
| kongfu | 12 |
| rift1b | 12 |
| fairy | 11 |
| plantagenet | 11 |
| heian | 10 |
| gta | 8 |
| iceage | 4 |
| steam | 3 |

植物世界分布（`PlantType.HomeWorld`，前 12）：

| 世界 token | 植物数 |
|---|---|
| tower | 24 |
| epicquest | 12 |
| chinesegarden | 8 |
| tutorial | 7 |
| skycity | 6 |
| thirdanniversary | 6 |
| modern | 6 |
| lostcity | 5 |
| atlantis | 4 |
| kongfu | 4 |
| beach | 4 |
| steam | 4 |

图鉴统计行（`AlmanacDataEntries.statType`）分布（前 12）：

| statType | 出现次数 |
|---|---|
| recharge | 168 |
| suncost | 160 |
| armor | 142 |
| damage | 138 |
| special | 107 |
| MISSING INFO | 100 |
| range | 75 |
| family | 63 |
| special2 | 47 |
| special1 | 32 |
| plantfoodpower | 30 |
| area | 24 |

- 不在 `PlantType` 的图鉴条目 17 条：`aquavine`、`beansprout`、`blazeleaf`、`cornfetti`、`electricpeel`、`flattenedshroom`、`frostbonnet`、`guardshroom`、`hammeruit`、`haystack`、`kelpguard`、`minishroom`、`seashroom`、`sweetheartsnare`、`tileturnip`、`ultomato1`、`znakelily`。
- 无名字键的植物：`minishroom`（U3）。
- 与客户端内容交集：`content/plants.json` 409 条命中 147 条，`content/zombies.json` 55 条命中 19 条。交集小是原版事实：content 侧是客户端自建名册（含 `fused_*` 融合体），未命中的 id 全列在 JSON 的 `cross` 段，本层不替它们编图鉴。

## 四、花园（`garden`）

掉落物 65 条、掉落类族 8 个、Zen Garden 属性表 4/4 张、花盆 12 个、植物奖励表 3 张、其中有定价的掉落物 2 条。

| 字段 | 来源 | 说明 |
|---|---|---|
| `typeName` | `CollectableType.TypeName` | 如 `worldkey_pirate`/`pinata_egypt`/`sprout` |
| `collectableClass` | `CollectableType.CollectableClass` | 决定掉落表现 |
| `rewardDialogTitleKey` | `RewardDialogTitle` 去方括号 | 原版有缺键，解析不到的标 `rewardDialogTitleResolved=false` |
| `image`/`popAnim` | `StandaloneImage`/`PopAnim` | 美术资源名 |
| `soldAs` | `StoreProductProps` 记号匹配 | `{sku, objectType, objectItem, matchKind, candidates, priceCoins/Gems/Mints/Usd, priceKind}`；无匹配为 `null` |
| `storeCategory` | 掉落物名恰好是某个 `ObjectType` 品类名 | 只记品类，不给价（如 `pinata`） |
| `dropSources` | `QuestMgr.CompletionAwards`/`QuestRewardTablesProps`/`ZenGardenPlantRewards`/`AwardConfig.GiftBoxRewards`/`StoreProductProps` | 「谁发这个东西」的表名与样例；表里没写到的来源不补 |
| `zenGarden.*` | `pkg_2083` + `pkg_0004` | 生长时长、花盆成本、蜜蜂参数、植物奖励 |

掉落类族分布：

| collectableClass | 条数 |
|---|---|
| Collectable | 33 |
| CollectablePinata | 13 |
| CollectableWorldKey | 10 |
| CollectablePowerup | 5 |
| CollectableJunk | 1 |
| CollectableCostumeReward | 1 |
| CollectableLawnMower | 1 |
| CollectableSprout | 1 |

有定价的掉落物（`StoreProductProps` 命中明细）：

| 掉落物 | matchKind | 同形候选 | Sku（取第一条） | ObjectItem | 计价字段 | 价格 |
|---|---|---|---|---|---|---|
| pinata_egypt | sku | 1 | com.popcap.pvz2.pinata.egypt.consume.tutorial | store_tutorial | （全空） | （商品表里价格字段全空，本地无价） |
| sprout | item | 3 | com.popcap.pvz2.sprout.5.consume | sprout | gems | 30 |

其余 63 条没有定价，原因是原版商品表本身覆盖不到：565 条 `StoreProductProps` 里 447 条是 costume、61 条 plant、23 条 pinata、12 条 gameupgrade、9 条 eventenergy、4 条 mint、3 条 sprout，其余个位数。世界奖杯/危险房/世界钥匙/升级道具这类掉落物在原版是关卡奖励而非货架货品，所以 `soldAs` 为 `null`，本层不编价格（U6）。
- 掉落来源（`dropSources`）：6/65 条在本地表里能找到发放方，涉及的表：`QuestRewardTablesProps`、`StoreProductProps`。世界奖杯/危险房这类只在关卡结算里给的东西，本地没有发放表，条目会留空（U6）。

| Zen Garden 参数 | 值 |
|---|---|
| BackgroundImageID | IMAGE_BACKGROUNDS_ZEN_GARDEN |
| PlantGrowDurationInSeconds | 18000 |
| NormalPlantCoinRewardAmount | 50 |
| TreasurePlantSpawnRate | 3 |
| GrowingSpeedupCalcMultiplyFactor | 2 |
| GrowingSpeedupCalcAddFactor | 1.7413 |
| GrowingSpeedupCalcMaxTimeSeconds | 28800 |
| PotCosts | {'#GemCostPurchased0': 20, '#GemCostPurchased1': 20, '#GemCostPurchased2': 20, '#GemCostPurchased3': 20, '#GemCostPurchased4': 20, '#GemCostPurchased5': 20, 'GemCostDefault': 20} |
| 花盆定义（`Pots`） | 12 个 |
| 蜜蜂（`BeeProps`） | AnimRigClass、BeeEffects、BeeMovingToPlantVelocity、BeeReadyTimeoutSeconds、BeeRestSpot、BeeVelocity、BeeWanderRange、NextBeeTimeMaxSeconds … |
| 植物奖励表 | `ZenGardenMarigoldFinalRewards`、`ZenGardenMarigoldPlantRewards`、`ZenGardenNormalPlantRewards` |

## 五、成就·任务（`quests` / `achievements`）

`QuestMgr` 任务 240 条（69 条带完成奖励）、每日任务定义 11 条（11 条带奖励）、奖励表 6 张、任务页签 2 个、成就 53 条。

| 字段 | 来源 | 说明 |
|---|---|---|
| `id` | `Quests[*].<wrapper>.UniqueID` | 如 `EPICQUEST`/`BEACH`/`DAILY_2_ADVENTURE_DQ` |
| `targetType` | 外层包装类名 | 目标类型：`ChallengeLevelQuestData`/`EpicQuestData`/`LevelQuestData`/… |
| `slot`/`category`/`theme` | `Slot`/`QuestCategory`/`OverrideQuestTheme` | 决定挂在哪个页签 |
| `params` | `LevelName`/`ActionsToPerform`/`CountRemainingLabel`/`Priority`/`Repeatable`/`Disabled`/`UniqueIDList` 长度/`Prerequisites` | 目标参数，原样保留 |
| `rewards` | `CompletionAwards.Awards[]` | `{type, subtype, amount}`；`amount` 是 `Amount` 原值；没有就是 `null` |
| `rewardSource` | 本层标注 | `QuestMgr.CompletionAwards` / `QuestData.CompletionAwards` / `unknown` |
| `achieve.*` | `ACHIEVE_*_TITLE`/`_DESC` 文案键 | 成就本地无表，按文案键枚举，奖励 serverOnly |

任务分类与包装类：

| QuestCategory | 条数 |
|---|---|
| DailyActivities | 1 |
| Epic | 67 |
| Tutorial | 2 |
| Unused | 170 |

| 包装类（目标类型） | 条数 |
|---|---|
| ChallengeLevelQuestData | 196 |
| EpicQuestData | 39 |
| LevelQuestData | 5 |

奖励类型分布（按奖项条数，含 QuestMgr 240 条与每日定义 11 条）：

| 奖项 Type | 条数 |
|---|---|
| coins | 66 |
| gems | 8 |
| pinata | 5 |
| mints | 1 |

- 奖励行 80 条，其中 80 条带数值：`amount` 取 `CompletionAwards.Awards[].Amount` 原值（JSON 数字原样转文本，不做单位换算、不补缺省）；空串表示原表没给这个字段。

任务页签（`QuestTabCategoryData`）：

| 页签 | TabLabel 键 | 覆盖的 QuestCategory | 带计时 |
|---|---|---|---|
| DailyActivities | `QUEST_TAB_LABEL_DAILY` | DailyActivities | 是 |
| EpicQuests | `QUEST_TAB_LABEL_EPIC` | Epic、Tutorial、Egypt、Pirate、Cowboy、UnlockWorld … | 否 |

- **成就是原版没有的部分**：本地只有 `ACHIEVE_*` 文案键（114 个键，其中 53 个有 `_TITLE`、53 个有 `_DESC`、0 个有 `_NAME`），没有任何成就定义表或奖励表。因此每条都是 `rewards=null` + `serverOnly=true`（U4）。
- 奖励表（`quest_rewards.TablesConfig`）6 张，按 `Difficulty` 分档，每档给 `pinata` 类型 + `SubType`（世界）+ `MinAmount`/`MaxAmount`/`Weight` 的随机奖励池。

## 六、本地化覆盖

| 文件 | 键值对 | 判定语种 | 含 CJK 的值数 |
|---|---|---|---|
| pkg_0231_LawnStringsData.json | 19055 | 英文 | 98 |
| pkg_0232_LawnStringsData.json | 19052 | 中文 | 18665 |

- 语种按「值里有没有 CJK」判定，不依赖文件名先后；缺键不报错，只在 `resolved` 里标 false。
- 键名去方括号的规则只作用于 objdata 里写成 `[KEY]` 的字段（`TypeStringID`/`ValueStringID`/`QuestName`/`Description`/`TabLabel`/`RewardDialogTitle`），LawnStrings 本身的键不带方括号。

## 七、原版没有的部分（明确缺口）

1. **僵尸图鉴花名册**：没有 roster 表，`AlmanacOffset`/`AlmanacScale` 只有零星 9 条覆盖（U1）。
2. **成就定义与奖励**：只有文案键，奖励在服务器侧（U4）。
3. **花园物件售价**：`CollectableType` 本身不带价格，绝大多数掉落物在原版就不是货架商品（U6）。
4. **植物图鉴的世界映射**：`HomeWorld` 是内部 token，与 `content/worlds.json` 的 id 不同源（U7）。
5. **僵尸图鉴的展示顺序/分组**：没有数据，`almanac.zombies` 按 id 字典序输出（U1）。

## 八、未知项

| 编号 | 主题 | 问题 |
|---|---|---|
| U1 | zombie-roster | 原版没有僵尸图鉴花名册表（ZombiePropertySheet 里只有零星几条设了 AlmanacOffset/AlmanacScale，条数见 almanac.counts.zombieSheetsWithAlmanacOffset 与 zombiePropertySheets）；本层的准入判据是「有 ZombieType 定义 且 LawnStrings 有 ZOMBIE_<TYPE> 名字键」。被排除的两类分别见 counts.zombiesWithoutNameKey 与 counts.zombiesSpawnOnly。真正的图鉴花名册若在引擎代码里，本地数据看不出来。 |
| U2 | almanac-plants-not-in-planttypes | 17 个图鉴植物在 PlantType 里没有同名条目（kelpguard/haystack/znakelily/…），它们的所属世界与图鉴背景无从取值，world 为空串。其中 ultomato1 看着是 ultomato 的升级变体（PlantType 里有 ultomato、没有 ultomato1），但按名字后缀去猜属于推断，本层不做合并。 |
| U3 | missing-name-keys | minishroom 缺裸名键（其余 166 个植物都有）；缺键条目的 nameKey 照推导规律给出但 resolved.name=false。 |
| U4 | achievement-rewards | 成就本地只有 ACHIEVE_* 文案键，没有奖励表；奖励一律 serverOnly=true、rewards=null，未编造任何数值。 |
| U5 | level-counting | levels 是「关卡包文件计数」（一个 pkg_*.json 近似一关），同一关多波引用只计 1；植物只认 InitialPlantPlacements/PresetPlantList/PlantPriorList 的正向引用，PlantExcludeList 不算出现。 |
| U6 | collectable-prices | 售价只在 StoreProductProps（565 条）里按「记号集合」对得上具体商品时给出（ObjectItem 全等，或掉落物记号≥2 个且是 Sku 记号子集）；品类名本身不冒充商品，匹配不到即 soldAs=null。同一掉落物可能对应多档货（如 sprout 有 5/10/20… 多档宝石价），本层取商品表顺序第一条并记 `candidates`，单条 price 不是唯一售价；原版是否存在其它售卖路径（服务器商品表）本地无法确认。 |
| U7 | world-tokens | PlantType.HomeWorld / ZombieType.HomeWorld 的取值是 tower/epicquest/modern/rift1a 这类内部 token，与 content/worlds.json 的 id（frontyard/…）不同源，本层原样保留、不做映射。 |
| U8 | loc-key-convention | 植物名/描述键是按 166/167 条实测规律推导（裸大写 id + _DESCRIPTION/_TOOLTIP），僵尸键是 ZOMBIE_ + 大写 id；两者都不是 objdata 里显式写出的键，resolved 标记说明是否真查到。 |
| U9 | spawn-only-zombies | 有 120 个名字只出现在 SpawnZombies* 的 RTID 生成引用里、没有自己的 ZombieType 定义（如 modern_screendoor）：它们没有 HomeWorld、也不构成图鉴条目，本层不计入 almanac。 |
| U10 | zombie-homeworld-conflict | 同一个 ZombieType id 在多个包里可能带不同 HomeWorld（本地有 9 个 id 如此，如 tutorial 同时出现 modern/tutorial、cowboy 同时出现 cowboy/dark/plantagenet/rift2/tutorial）；本层按文件序取首个定义，冲突值不合并、也不判定哪个才是原版口径。 |

## 九、复现

```
python tools/contentc/metagame.py            # 写 native/generated/metagame.json 与本报告
python tools/contentc/metagame.py --check    # 逐字节校验两个产物是否最新（过期返回 2）
python -m unittest tools.tests.test_metagame -v
```

条数一览：almanac 595（植物 167 + 僵尸 428）、garden 65、quests 240（带奖励 69）、achievements 53、unknowns 10。
