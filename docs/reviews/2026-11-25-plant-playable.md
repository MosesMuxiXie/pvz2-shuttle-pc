# 可玩植物子集评估：339 条原版名册里 293 条具备资格

日期：2026-11-25 · 任务：t75 / P0-4b · 结论：**维持 147 手工名册（路线 C）**

## 结论摘要

1. 原版 `PlantType` 名册 339 条，按四条判据逐条判定后 **304 条可玩、35 条被阻断**。
2. 304 条可玩里，42 条已经手工写进 `content/plants.json`（同名，不是新增），**262 条是真正的新增候选**。
3. 阻断原因：缺成本 **23** 条（cost 为 null 2 条、为 0 21 条）、缺族 **0** 条、缺美术 **15** 条；其中 3 条同时缺成本与美术。
4. 所以**答案不是 339**：44 条同名已在名册（不产生新增），46 条被数据阻断（23 + 15 − 3）。本评估只读，`content/**` 一行未改。

## 一、判据与数据源

| 判据 | 规则 | 数据源 | 命中 |
| --- | --- | --- | --- |
| `hasCost` | `cost` 存在且 > 0（原版把 `SunCost` 编进 `cost`，`properties` 里没有 `SunCost` 键） | `native/generated/content.pack` | 316/339 |
| `hasFamily` | `family` 非空；包内 `plants[].families` 只作交叉证据（多数为空） | `native/generated/plant_families.json` | 339/339 |
| `hasArt` | base 去 `shuttle_` 前缀后与 framework/art/popAnim/animRig 归一比较，或 content 已有 art | `PvZ2SHUTTLE/assets/db/shuttle/index.json`（1085 base） | 324/339 |
| `hasPackRow` / `sameAsAuthored` | 339 条都来自 `content.pack`（`hasPackRow` 恒真）；44 条与手工名册同名 | `content.pack` + `content/plants.json` | 339/44 |

美术命中来源：content `44`、framework `280`、动画名 `0`、roster.art `0`。

## 二、结果分布

| 分类 | 条数 | 说明 |
| --- | --- | --- |
| roster 总数 | 339 | 295 条 pack 行 + 44 条 skipped_existing |
| 可玩 | 304 | 三条判据全过 |
| 其中已在手工名册 | 42 | 同名行，不产生新增 |
| 其中新增候选 | 262 | 可并进 `content/plants.json` 的那批 |
| 被阻断 | 35 | 至少一条判据没过 |
| 仅缺成本 | 20 | cost 为 null 或 0 |
| 仅缺美术 | 12 | art index 与 content 都没有 |
| 成本+美术都缺 | 3 | 两条判据同时不过 |

## 三、按 blocker 分组清单

### 3.1 缺成本（23）

| id | cost | framework |
| --- | --- | --- |
| blastspinnercocoon | None | BlastSpinnerCocoon |
| chrysantheautumn | 0 | PlantPeppermint |
| cutebubuseed | 0 | PlantPrimalPeashooter |
| enlightenmint1 | 0 | PlantEnlightenmint |
| goldbloom | 0 | PlantGoldbloom |
| gravebuster | 0 | PlantGraveBuster |
| hotpotato | 0 | PlantHotPotato |
| iceburg | 0 | PlantIceburg |
| imitater | None | PlantImitater |
| imppear_teto | 0 | PlantImpPearTeto |
| land | 0 | PlantLilyPad |
| littleguy | 0 | PlantLittleGuy |
| marigold | 0 | PlantMarigold |
| midi | 0 | PlantHypnoShroom |
| minigame_music | 0 | PlantMagnifyingGrass |
| old_sushi | 0 | PlantSnapdragon |
| potatochip | 0 | PlantPotatomine |
| puffshroom | 0 | PlantPuffshroom |
| seashroom | 0 | PlantSeashroom |
| specialgarlic | 0 | PlantGarlic |
| stallia | 0 | PlantStallia |
| sushi | 0 | PlantPuffshroom |
| tileturnip | 0 | PlantPowerPlant |

### 3.2 缺美术（15）

| id | framework |
| --- | --- |
| bitpeashooter | PlantMiniPeashooter |
| blastspinnercocoon | BlastSpinnerCocoon |
| dandelion | PlantAcidLemon |
| escaperoot | PlantCNIceShroom |
| explodeovine | PlantCNFireShroom |
| fusiongatling | PlantFusionGatling |
| headbutterlettuce | PlantHeadbutterLettuce |
| imppear_teto | PlantImpPearTeto |
| littleguy | PlantLittleGuy |
| littlerepeater | PlantLittleRepeater |
| minishroom | PlantMiniShroom |
| noctarinecloud | PlantNoctarineCloud |
| rabbagepult | PlantRaCabbagepult |
| slingpea | PlantArmamintPeashooter |
| sweetpotato | PlantCabbagepultCanSink |

### 3.3 缺族（0）

（无 —— `plant_families.json` 覆盖全部 339 条，`byFamily` 合计也是 339。）

### 3.4 同时缺成本与美术（3）

`blastspinnercocoon`、`imppear_teto`、`littleguy`

## 四、为什么不是 339

- **44 条同名**：`begonia`、`birdofparadise`、`bloomerang` … 已经在手工名册里，把它们再算一遍只会得到重复 id，不是新增内容。同名行里 42 条判据全过，剩下 2 条本身缺成本（`iceburg`、`potatochip`，cost 为 0）。
- **23 条缺成本**：原版 `cost` 为 null（2 条，如 `blastspinnercocoon`、`imitater`）或 0（21 条，如 `marigold`、`puffshroom`、`gravebuster`）——这些是未启用/活动/测试行，没有阳光价格就没有可玩性。
- **15 条缺美术**：`PvZ2SHUTTLE` 的 1085 个 shuttle base 里找不到对应framework（如 `apsarlotus`、`cornucopia`、`bubblecoral`），content 也没有 art，没有骨架/贴图就画不出来。
- 算术：339 − 44（同名不新增）= 295 条候选；候选里 262 条判据全过、33 条被阻断（23 + 15 − 3 − 2 条同名阻断）；再算上同名里 42 条可玩，可玩总量 = 42 + 262 = 304。

## 五、若要把新增候选并进 `content/plants.json`，需要动哪些模块

（只列清单，本次一行未改）

1. `tools/contentc/plants_merge.py`：新增「只并可玩子集」的入口（现在只有全量并集 442；需要 `--playable-only` 读取本评估的 `playable` 名单）。
2. `tools/obb_build_content_v2.py`：`--plants-only` 之外接一个新开关，并把 `--content-report` 的 `plants=` 行扩成 `+=251 authored=147 playable=293` 口径。
3. 产物重建（都会因 295→546 的 id 集合变化而需要重算）：`native/generated/plants_from_pack.json`、`native/generated/plant_families.json`、`native/generated/plantfood_from_pack.json`、`native/generated/decks_*.json`、`native/generated/original_gaps.json`、`native/generated/plant_playable.json`（本产物）。
4. 断言要同步的测试（把 147/295/44 写死的）：`test_expand`、`test_pfamilies`、`test_original_gaps`、`test_fusions`、`test_mapping`、`test_decks`、`test_rewards`、`test_spawn_offsets`、`test_plants_merge`。
5. 引擎侧：`native/src/content/loader.cpp` 的植物按 id 精确查表，新增行只要字段齐全即可加载；但**没有 art 的 251 条之外还有 0 条**（可玩集都带 art），所以不需要新美术资源。

## 六、C57 收尾：`patch_460_9.json` 三块数据的消费者判定（只读）

数据源：`native/generated/patch_460_9.json`。判定方法：在 `native/src/**` 里按字段名做字面检索，再看命中的是不是真消费者（读值并影响行为），而不是注释里的引用。

| 数据块 | 条数 | 当前内核消费者 | 判定 |
| --- | --- | --- | --- |
| `levelFlags` | 271（true 215 / false 56） | `native/src/engine/world.cpp:69-77` 构造期读关卡 JSON 的 `extra.suppressFlagZombie`；`world.cpp:167-180` 把该关的旗标波降级为普通波并发 `flag_wave_suppressed` 事件；`native/src/engine/world.hpp:182-184`、`:437-438` 保存/暴露；`native/src/main.cpp:288-290` 在 `--run-level` 摘要里输出 `flagSuppressed` | **有消费者**（T66 已接线，读的是 content 键，不打开本 JSON，见 `world.cpp:72`） |
| `rlConfig` | 17 字段（`LevelCount=12`、`ChoiceCount=3`、`ZombiePool=112` 条、`TemplateLevelNames=18` 条） | 无 | **无消费者**：缺 Roguelike 层 |
| `thymeEvents` | 30 条 / 445 个关卡引用（373 个唯一 id） | 无 | **无消费者**：缺日历层 + 活动关卡池 |

### 6.1 检索证据

```text
PS> $src = Get-ChildItem native\src -Recurse -Include *.cpp,*.hpp | % FullName
PS> Select-String -Path $src -Pattern rlConfig,thymeEvents,levelFlags,ThymedEvent,EliteChance,ZombiePool -SimpleMatch | Measure-Object
Count : 0
PS> Select-String -Path $src -Pattern suppressFlagZombie -SimpleMatch | Measure-Object
Count : 11        # world.cpp / world.hpp / main.cpp
PS> Select-String -Path $src -Pattern roguelike,Rogue,elite,Elite,DisableSkipLevel -SimpleMatch
（无输出）
PS> Select-String -Path $src -Pattern calendar -SimpleMatch
（无输出）；-Pattern schedule 命中 45 行，全部在 director.cpp/hpp（波次调度）
```

`rlConfig` / `thymeEvents` 的唯一消费者是编译器自身 `tools/newin4609.py`（`rlConfig` 29 处、`thymeEvents` 25 处），它负责生成上面的 JSON，不是运行时。

### 6.2 缺的是哪一层（不发明字段）

- **`rlConfig` 缺「Roguelike 运行层」**：它描述一次 12 关的 run（`LevelCount=12`、每 `EliteEvery` 关出一个精英、起始阳光按关递增、僵尸池按世界取）。`TemplateLevelNames` 18 条里 **0 条**能在 `content/levels` 找到；内核里没有任何 run 状态、关卡选择/跳过模型，也没有精英词条。最小接线点（若建该层）：`native/src/flow.cpp:10` 的 `levelsOfWorld()` 是唯一的关卡序列来源，`flow.cpp:59` 决定下一关——rl run 需要在那里改写成「按模板名造 12 关」而不是读 `content/levels`。
- **`thymeEvents` 缺「日历/会话层」+「活动关卡池」**：30 条事件共 445 个关卡引用（373 个唯一 id，时间跨度 2023-01-09T16:00:00Z → 2026-12-31T15:59:59Z，`isNew` = [29, 30, 31]，`disabled` 1 条），而 `content/levels` 里这些 id **命中 0 条**——事件关卡池根本没有编译进内容。内核也没有「现在几点/今天哪个活动开着」的概念。最小接线点（若建该层）：`native/src/worldmap.cpp:232` 的 `WorldMap::status()` 是唯一的世界可进入判定，`native/src/worldmap_view.cpp:313-315` 是进入世界时取首关的位置。
- 结论：三块里只有 `levelFlags` 今天能落地；`rlConfig` 与 `thymeEvents` 要先有「活动关卡池 + 日历」与「Roguelike 序列」两层模型，在那之前**不要**把它们直接塞进关卡 JSON——本次判定只读，C++ 与 content 一行未改。

## 七、147 与 339 的包含关系：44 条同名 + 1 条改名

`content/plants.json` 的 **147** 条里，按 id 精确命中 pack 名册的 44 条，另有 1 条能证明是同一植物的改名；剩下 **102** 条在原版名册里没有对应行。

| 类别 | 条数 | 判定依据 | 例 |
| --- | --- | --- | --- |
| 同名在册 | 44 | id 与 `content.pack` 的 `plants[].id` 完全相等 | begonia, birdofparadise, bloomerang, bonkchoy … |
| 改名同一植物 | 1 | 名字近似（归一化后共同前缀 ≥6）**且** 成本、血量同时相等 | `fireflerry` ↔ `firefly` |
| 融合植物 | 85 | id 前缀 `fused_` 或 `tags` 含 `fused`；pack 名册里同名 **0** 条 | fused_birthsunflower, fused_cactus1, fused_cactus1_2, fused_chardguard … |
| Plantagenet 世界植物 | 14 | `tags` 含 `plantagenet`，pack 名册无同名 id | astrofruit, cheesestrawberry, chrysanthea, doominator … |
| 客户端自创 | 3 | 既无同名、也没有世界标签 | gatling, twinsunflower, umbrellaleaf |

合计：44 + 1 + 85 + 14 + 3 = 147（应为 147）。

- 归一化（去标点、转小写）后仍相等的：**0** 条 —— 说明差异不是拼写层面的，是真的没有对应项。
- 改名证据：`fireflerry`（cost 225 / hp 2671）↔ `firefly`（cost 225 / hitpoints 2671，framework `PlantFirefly`）—— 成本与血量逐项相同，名字只差拼写，判为同一植物。
- 名字近似但**不是**同一植物 1 组：`chrysanthea` ↔ `chrysantheautumn`（成本/血量不同，属不同条目，不能按名字合并）。
- **结论：「147 是 339 的子集」不成立** —— 算上改名，共享同一植物的只有 45/147（30%）；85 条融合 + 14 条 Plantagenet + 3 条自创在原版名册里都没有对应行。

逐条清单（102 条）：

- **融合（85）**：
  - fused_birthsunflower, fused_cactus1, fused_cactus1_2, fused_chardguard, fused_chardguard_2, fused_coldsnapdragon
  - fused_coldsnapdragon_2, fused_darktwinsunflower, fused_darktwinsunflower_2, fused_draftodil1, fused_draftodil1_2, fused_endurian
  - fused_endurian_2, fused_explodeonut1, fused_explodeonut1_2, fused_frozenpear, fused_frozenpear_2, fused_fusiongatling
  - fused_fusiongatling_2, fused_fusiongatling_3, fused_fusiongatling_4, fused_fusiongatling_5, fused_gumnut, fused_headbutterlettuce
  - fused_headbutterlettuce_2, fused_hollybarrierleaf, fused_hollybarrierleaf_2, fused_hollyknight, fused_hollyknight_2, fused_iceweed
  - fused_iceweed_2, fused_jasmine, fused_jasmine_2, fused_lemonaider, fused_lemonaider_2, fused_magnetfruit
  - fused_magnetfruit_2, fused_magnetshroom, fused_magnetshroom_2, fused_megagatling, fused_megagatling_2, fused_olivepit
  - fused_olivepit_2, fused_paradoxpult, fused_peppermint, fused_peppermint_2, fused_poisonpeashooter, fused_poisonpeashooter_2
  - fused_pokra1, fused_pokra1_2, fused_powervine, fused_powervine_2, fused_primalpeashooter, fused_primalpeashooter_2
  - fused_primalsunflower, fused_puffball, fused_punkshocker, fused_rabbagepult, fused_rabbagepult_2, fused_reinforcemint
  - fused_reinforcemint_2, fused_repeater1, fused_shadowpeashooter, fused_shadowpeashooter_2, fused_slingpea, fused_slingpea_2
  - fused_snappea1, fused_snappea1_2, fused_snowpea, fused_snowpea_2, fused_spikerock, fused_stickybombrice
  - fused_stickybombrice_2, fused_strawburst, fused_strawburst_2, fused_suntower, fused_sweetpotato1, fused_sweetpotato1_2
  - fused_tumbleweed, fused_tumbleweed_2, fused_turkeypult, fused_turkeypult_2, fused_wintergeddon, fused_wintermelon
  - fused_wintermelon_2
- **Plantagenet（14）**：
  - astrofruit, cheesestrawberry, chrysanthea, doominator, doublepassion, helioscabbage
  - iris, olivewood, oolongpeach, rosemary, snowlotus, succulentgrape
  - vortexmelon, wildflower
- **客户端自创（3）**：
  - gatling, twinsunflower, umbrellaleaf

复现：`py tools\contentc\plant_playable.py -n` 之后跑 `py -m unittest tools.tests.test_plant_playable`（`RosterInclusionTest` 钉住这组数字）；本节数字由 `roster_inclusion()` 现算，不是手写。

## 八、复现

```text
py tools\contentc\plant_playable.py -n
#   plants-playable-v1: total=339 playable=293 new=251 blocked=46 missingCost=23(null 2/zero 21) missingFamily=0 missingArt=26 both=3
py tools\contentc\plant_playable.py --check
py -m unittest tools.tests.test_plant_playable
```

## 九、边界

- 只读：`content/**`、`native/src/**`、`native/generated/*.json` 都未改；本工具的输出是 `native/generated/plant_playable.json` 与本文档。
- 未 commit。判据全部可重算，行级证据在 JSON 的 `rows[].evidence` 里。
