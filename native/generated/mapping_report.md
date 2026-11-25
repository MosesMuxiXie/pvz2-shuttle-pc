# 原版 type ↔ 客户端 id 映射报告

> 由 `python tools/contentc/mapping.py` 生成，请勿手工编辑。名单一律按输入表顺序排列，
> 且不写时间戳，因此同一份数据两次生成字节一致。

## 输入

- 原版植物表 `pkg_2074_PlantType.json`：339 条 objdata
- 原版僵尸表 `pkg_2115_ZombieType.json`：1127 条 objdata
- 客户端 `content/plants.json`：147 条；`content/zombies.json`：55 条
- 客户端 `content/almanac.json`：plants 147、zombies 55（只有图鉴文案，不含原版编号）
- 人工表 `tools/contentc/manual_mapping.csv`：8 行可用

## 匹配级别

1. `exact` —— 原版 `TypeName` 与 client id 完全相同（区分大小写）。同名多行全部归属同一 client id，并记入“一对多清单”。
2. `popanim` —— `PopAnim` 去掉 `POPANIM_PLANT_` / `POPANIM_ZOMBIE_` 前缀后与 client id 相同（不区分大小写）。
   为避免把美术复用当成同一对象，还要通过“同源守卫”：命中条目唯一、未被更高层占用、client id 与原版 `TypeName` 归一化后互为子串；
   僵尸若带 `extra.source_codename` 且该 codename 在原版表中存在，则 codename 更权威，`popanim` 一律不采信。
3. `almanac` —— 原版 `IntegerID` 命中客户端 `plants.json` 的 `almanac_no`，并同样通过同源守卫。
   客户端图鉴号是本项目自有的 1..147 编号，与原版 `IntegerID` 不是同一套体系，本版数据采信 0 条。
4. `manual` —— `tools/contentc/manual_mapping.csv`（列 `side,client_id,pack_type,note`）只补自动匹配没覆盖的 client id；
   与自动匹配冲突时保留自动匹配，并在“人工表提示”里记录。文件不存在按空处理。
   本版该表 8 行，全部是 `extra.source_codename` 已指向原版真实条目、经评审确认的僵尸（`match_kind=manual` 共 8 条）。

## 逐级命中统计

| side | 原版行 | exact | popanim | almanac | manual | 未匹配 | client 行 | client 独有 |
|---|---|---|---|---|---|---|---|---|
| plant | 339 | 44 | 0 | 0 | 0 | 295 | 147 | 103 |
| zombie | 1127 | 20 | 0 | 0 | 8 | 1099 | 55 | 27 |

“原版行”是表里的 objdata 条数；“未匹配”是没有任何 client id 归属的原版行；
“client 独有”是没有原版行归属的 client id 数。四个级别之和加“未匹配”等于“原版行”。

## 结论要点

- 客户端 147 个植物：44 个有原版归属，103 个 client 独有；这些 id 在本版 `PlantTypes` 里确实不存在（子串搜索亦无命中），不是匹配规则漏掉的。
- 客户端 55 个僵尸：28 个有原版归属（其中 8 个按 `extra.source_codename` 经人工表采信），27 个 client 独有；其中 2 个的 `source_codename` 指向原版不存在的条目（代号无效，不是没有线索），其余 25 个无任何线索。
- PopAnim 同名命中 8 条（植物 7、僵尸 1），全部判为美术复用，未采信。
- almanac 编号碰撞 102 条，全部未采信；其中 6 条撞在原版占位槽 `unused_NN` 上。
- 原版重复 `TypeName` 共 2 组（`heavy_shield`×2、`kongfu_gargantuar`×2），全部保留为独立行，不合并。

## 客户端独有（植物 103）

这些 id 在本版 `pkg_2074_PlantType.json` 中确实不存在（子串搜索亦无命中），不是匹配规则漏掉的；逐条附上可用线索：

- `twinsunflower`（almanac_no 24） —— 客户端独有：原版表无此 id
- `gatling`（almanac_no 25） —— 客户端独有：原版表无此 id
- `umbrellaleaf`（almanac_no 30） —— 客户端独有：原版表无此 id
- `iris`（almanac_no 43） —— 客户端独有：原版表无此 id；almanac_no 43 撞上原版占位槽 `unused_43`（非同一植物）
- `rosemary`（almanac_no 44） —— 客户端独有：原版表无此 id；PopAnim 与 `spearmint` 相同，判为美术复用（非同一植物）
- `snowlotus`（almanac_no 45） —— 客户端独有：原版表无此 id；PopAnim 与 `enforcemint` 相同，判为美术复用（非同一植物）；almanac_no 45 撞上原版占位槽 `unused_45`（非同一植物）
- `wildflower`（almanac_no 46） —— 客户端独有：原版表无此 id；PopAnim 与 `evilshroom_toughness` 相同，判为美术复用（非同一植物）；almanac_no 46 撞上原版占位槽 `unused_46`（非同一植物）
- `olivewood`（almanac_no 47） —— 客户端独有：原版表无此 id；PopAnim 与 `olivepit` 相同，判为美术复用（非同一植物）；almanac_no 47 撞上原版占位槽 `unused_47`（非同一植物）
- `astrofruit`（almanac_no 48） —— 客户端独有：原版表无此 id；almanac_no 48 撞上原版占位槽 `unused_48`（非同一植物）
- `chrysanthea`（almanac_no 49） —— 客户端独有：原版表无此 id；almanac_no 49 撞上原版占位槽 `unused_49`（非同一植物）
- `doominator`（almanac_no 50） —— 客户端独有：原版表无此 id
- `helioscabbage`（almanac_no 51） —— 客户端独有：原版表无此 id
- `vortexmelon`（almanac_no 54） —— 客户端独有：原版表无此 id
- `cheesestrawberry`（almanac_no 55） —— 客户端独有：原版表无此 id；PopAnim 与 `explodeonut` 相同，判为美术复用（非同一植物）
- `oolongpeach`（almanac_no 56） —— 客户端独有：原版表无此 id；PopAnim 与 `tombtangler` 相同，判为美术复用（非同一植物）
- `succulentgrape`（almanac_no 57） —— 客户端独有：原版表无此 id；PopAnim 与 `teleportatomine` 相同，判为美术复用（非同一植物）
- `doublepassion`（almanac_no 58） —— 客户端独有：原版表无此 id
- `fireflerry`（almanac_no 59） —— 客户端独有：原版表无此 id
- `fused_wintergeddon`（almanac_no 63） —— 客户端独有：原版表无此 id
- `fused_paradoxpult`（almanac_no 64） —— 客户端独有：原版表无此 id
- `fused_repeater1`（almanac_no 65） —— 客户端独有：原版表无此 id
- `fused_primalsunflower`（almanac_no 66） —— 客户端独有：原版表无此 id
- `fused_snowpea`（almanac_no 67） —— 客户端独有：原版表无此 id
- `fused_snowpea_2`（almanac_no 68） —— 客户端独有：原版表无此 id
- `fused_wintermelon`（almanac_no 69） —— 客户端独有：原版表无此 id
- `fused_wintermelon_2`（almanac_no 70） —— 客户端独有：原版表无此 id
- `fused_punkshocker`（almanac_no 71） —— 客户端独有：原版表无此 id
- `fused_headbutterlettuce`（almanac_no 72） —— 客户端独有：原版表无此 id
- `fused_headbutterlettuce_2`（almanac_no 73） —— 客户端独有：原版表无此 id
- `fused_birthsunflower`（almanac_no 74） —— 客户端独有：原版表无此 id
- `fused_suntower`（almanac_no 75） —— 客户端独有：原版表无此 id
- `fused_sweetpotato1`（almanac_no 76） —— 客户端独有：原版表无此 id
- `fused_sweetpotato1_2`（almanac_no 77） —— 客户端独有：原版表无此 id
- `fused_spikerock`（almanac_no 78） —— 客户端独有：原版表无此 id
- `fused_iceweed`（almanac_no 79） —— 客户端独有：原版表无此 id
- `fused_iceweed_2`（almanac_no 80） —— 客户端独有：原版表无此 id
- `fused_rabbagepult`（almanac_no 81） —— 客户端独有：原版表无此 id
- `fused_rabbagepult_2`（almanac_no 82） —— 客户端独有：原版表无此 id
- `fused_primalpeashooter`（almanac_no 83） —— 客户端独有：原版表无此 id
- `fused_primalpeashooter_2`（almanac_no 84） —— 客户端独有：原版表无此 id
- `fused_magnetfruit`（almanac_no 85） —— 客户端独有：原版表无此 id
- `fused_magnetfruit_2`（almanac_no 86） —— 客户端独有：原版表无此 id
- `fused_olivepit`（almanac_no 87） —— 客户端独有：原版表无此 id
- `fused_olivepit_2`（almanac_no 88） —— 客户端独有：原版表无此 id
- `fused_magnetshroom`（almanac_no 89） —— 客户端独有：原版表无此 id
- `fused_magnetshroom_2`（almanac_no 90） —— 客户端独有：原版表无此 id
- `fused_explodeonut1`（almanac_no 91） —— 客户端独有：原版表无此 id
- `fused_explodeonut1_2`（almanac_no 92） —— 客户端独有：原版表无此 id
- `fused_reinforcemint`（almanac_no 93） —— 客户端独有：原版表无此 id
- `fused_reinforcemint_2`（almanac_no 94） —— 客户端独有：原版表无此 id
- `fused_stickybombrice`（almanac_no 95） —— 客户端独有：原版表无此 id
- `fused_stickybombrice_2`（almanac_no 96） —— 客户端独有：原版表无此 id
- `fused_chardguard`（almanac_no 97） —— 客户端独有：原版表无此 id
- `fused_chardguard_2`（almanac_no 98） —— 客户端独有：原版表无此 id
- `fused_puffball`（almanac_no 99） —— 客户端独有：原版表无此 id
- `fused_darktwinsunflower`（almanac_no 100） —— 客户端独有：原版表无此 id
- `fused_darktwinsunflower_2`（almanac_no 101） —— 客户端独有：原版表无此 id
- `fused_cactus1`（almanac_no 102） —— 客户端独有：原版表无此 id
- `fused_cactus1_2`（almanac_no 103） —— 客户端独有：原版表无此 id
- `fused_frozenpear`（almanac_no 104） —— 客户端独有：原版表无此 id
- `fused_frozenpear_2`（almanac_no 105） —— 客户端独有：原版表无此 id
- `fused_lemonaider`（almanac_no 106） —— 客户端独有：原版表无此 id
- `fused_lemonaider_2`（almanac_no 107） —— 客户端独有：原版表无此 id
- `fused_poisonpeashooter`（almanac_no 108） —— 客户端独有：原版表无此 id
- `fused_poisonpeashooter_2`（almanac_no 109） —— 客户端独有：原版表无此 id
- `fused_peppermint`（almanac_no 110） —— 客户端独有：原版表无此 id
- `fused_peppermint_2`（almanac_no 111） —— 客户端独有：原版表无此 id
- `fused_shadowpeashooter`（almanac_no 112） —— 客户端独有：原版表无此 id
- `fused_shadowpeashooter_2`（almanac_no 113） —— 客户端独有：原版表无此 id
- `fused_endurian`（almanac_no 114） —— 客户端独有：原版表无此 id
- `fused_endurian_2`（almanac_no 115） —— 客户端独有：原版表无此 id
- `fused_strawburst`（almanac_no 116） —— 客户端独有：原版表无此 id
- `fused_strawburst_2`（almanac_no 117） —— 客户端独有：原版表无此 id
- `fused_coldsnapdragon`（almanac_no 118） —— 客户端独有：原版表无此 id
- `fused_coldsnapdragon_2`（almanac_no 119） —— 客户端独有：原版表无此 id
- `fused_snappea1`（almanac_no 120） —— 客户端独有：原版表无此 id
- `fused_snappea1_2`（almanac_no 121） —— 客户端独有：原版表无此 id
- `fused_hollyknight`（almanac_no 122） —— 客户端独有：原版表无此 id
- `fused_hollyknight_2`（almanac_no 123） —— 客户端独有：原版表无此 id
- `fused_megagatling`（almanac_no 124） —— 客户端独有：原版表无此 id
- `fused_megagatling_2`（almanac_no 125） —— 客户端独有：原版表无此 id
- `fused_fusiongatling`（almanac_no 126） —— 客户端独有：原版表无此 id
- `fused_fusiongatling_2`（almanac_no 127） —— 客户端独有：原版表无此 id
- `fused_hollybarrierleaf`（almanac_no 128） —— 客户端独有：原版表无此 id
- `fused_hollybarrierleaf_2`（almanac_no 129） —— 客户端独有：原版表无此 id
- `fused_turkeypult`（almanac_no 130） —— 客户端独有：原版表无此 id
- `fused_turkeypult_2`（almanac_no 131） —— 客户端独有：原版表无此 id
- `fused_slingpea`（almanac_no 132） —— 客户端独有：原版表无此 id
- `fused_slingpea_2`（almanac_no 133） —— 客户端独有：原版表无此 id
- `fused_jasmine`（almanac_no 134） —— 客户端独有：原版表无此 id
- `fused_jasmine_2`（almanac_no 135） —— 客户端独有：原版表无此 id
- `fused_pokra1`（almanac_no 136） —— 客户端独有：原版表无此 id
- `fused_pokra1_2`（almanac_no 137） —— 客户端独有：原版表无此 id
- `fused_draftodil1`（almanac_no 138） —— 客户端独有：原版表无此 id
- `fused_draftodil1_2`（almanac_no 139） —— 客户端独有：原版表无此 id
- `fused_gumnut`（almanac_no 140） —— 客户端独有：原版表无此 id
- `fused_tumbleweed`（almanac_no 141） —— 客户端独有：原版表无此 id
- `fused_tumbleweed_2`（almanac_no 142） —— 客户端独有：原版表无此 id
- `fused_powervine`（almanac_no 143） —— 客户端独有：原版表无此 id
- `fused_powervine_2`（almanac_no 144） —— 客户端独有：原版表无此 id
- `fused_fusiongatling_3`（almanac_no 145） —— 客户端独有：原版表无此 id
- `fused_fusiongatling_4`（almanac_no 146） —— 客户端独有：原版表无此 id
- `fused_fusiongatling_5`（almanac_no 147） —— 客户端独有：原版表无此 id

## 客户端独有（僵尸 27）

这些 id 在本版 `pkg_2115_ZombieType.json` 中确实不存在（子串搜索亦无命中），不是匹配规则漏掉的；逐条附上可用线索：

- `garden_zombie` —— 客户端独有：原版表无此 id
- `garden_cone` —— 客户端独有：原版表无此 id
- `garden_bucket` —— 客户端独有：原版表无此 id
- `garden_flag` —— 客户端独有：原版表无此 id
- `garden_poet` —— 客户端独有：原版表无此 id
- `garden_umbrella` —— 客户端独有：原版表无此 id
- `garden_imp` —— 客户端独有：原版表无此 id
- `garden_gargantuar` —— 客户端独有：原版表无此 id
- `garden_cuju` —— 客户端独有：原版表无此 id
- `garden_drummer` —— 客户端独有：原版表无此 id
- `gang_zombie` —— 客户端独有：原版表无此 id
- `gang_cone` —— 客户端独有：原版表无此 id
- `gang_bucket` —— 客户端独有：原版表无此 id
- `gang_ozloc` —— 客户端独有：原版表无此 id
- `gang_carl` —— 客户端独有：原版表无此 id
- `market_clockwork` —— 客户端独有：原版表无此 id
- `market_armor1` —— 客户端独有：原版表无此 id
- `market_armor2` —— 客户端独有：原版表无此 id
- `market_mechanic` —— 客户端独有：原版表无此 id
- `market_trapeze` —— 客户端独有：原版表无此 id
- `royal_zombie` —— 客户端独有：原版表无此 id；extra.source_codename=royal 指向的原版条目不存在（代号无效，不是没有线索）
- `royal_flag` —— 客户端独有：原版表无此 id；extra.source_codename=royal_flag 指向的原版条目不存在（代号无效，不是没有线索）
- `royal_noblewoman` —— 客户端独有：原版表无此 id
- `royal_winetasting` —— 客户端独有：原版表无此 id
- `royal_chef_gargantuar` —— 客户端独有：原版表无此 id
- `imp_maid` —— 客户端独有：原版表无此 id
- `royal_princess` —— 客户端独有：原版表无此 id

## 原版独有

### 植物（295）

原版有、客户端没有对应 id 的条目，按原表顺序：

`vamporcini`、`bombardmint`、`seashroom`、`plantern`、`reinforcemint`、`magnetshroom1`、`enchantmint`、`puffball`
`doomshroom`、`flowerpot`、`iceshroom`、`sungun`、`hollyknight`、`marigold`、`lightningreed`、`peapod`
`phatbeet`、`coconutcannon`、`pokra1`、`chilibean`、`boingsetta1`、`ultomato1`、`lilypad`、`land`
`tanglekelp`、`dandelion`、`bowlingbulb`、`slingpea`、`puffshroom`、`gravebuster`、`sprout`、`aloe`
`witchhazel`、`shrinkingviolet`、`imitater`、`pumpkin`、`hurrikale`、`firepeashooter`、`primalpeashooter`、`perfumeshroom`
`primalsunflower`、`primalpotatomine`、`primalwallnut`、`chardguard`、`pokra`、`snapdragon`、`coldsnapdragon`、`explodeonut1`
`kiwibeast`、`kiwibeast_deprecated`、`celerystalker`、`sapfling`、`garlic`、`sporeshroom`、`minipeashooter`、`powerplant`
`cactus`、`missiletoe`、`electricpeashooter`、`snappea`、`thymewarp`、`electricblueberry`、`burnade`、`armamint`
`moonflower`、`nightshade`、`shadowshroom`、`grimrose`、`dusklobber`、`shadowpeashooter`、`icebloom`、`goldbloom`
`redstinger`、`grapeshot`、`electricitea`、`dartichoke`、`dazeychain`、`powerlily`、`ultomato`、`xshot`
`ghostpepper`、`jackolantern`、`sweetpotato`、`caulipower`、`applemortar`、`citron`、`groundcherry`、`toadstool`
`horsebean`、`wintermint`、`zoybeanpod`、`wasabiwhip`、`poisonpeashooter`、`bloominghearts`、`peppermint`、`birthsunflower`
`murkadamia`、`peanut`、`imppear`、`blastberry`、`evilshroom_speed`、`enlightenmint`、`unused_47`、`unused_46`
`unused_48`、`unused_49`、`unused_43`、`unused_45`、`gumnut`、`tumbleweed`、`ailmint`、`stickybombrice`
`evilshroom_toughness`、`spearmint`、`enforcemint`、`concealmint`、`containmint`、`olivepit`、`magnetshroom`、`shinevine`
`appeasemint`、`impatiensshooter`、`boomflower`、`heathseeker`、`solarsage`、`tigergrass`、`akee`、`boingsetta`
`blockoli`、`buttercup`、`powervine`、`lavaguava`、`iceweed`、`hocus`、`goldleaf`、`gloomvine`
`filamint`、`mangosteen`、`pvine`、`bramblebush`、`noctarine`、`rhubarbarian`、`draftodil`、`megagatling`
`headbutter`、`escaperoot`、`explodeovine`、`parsnip`、`strawburst`、`kernelpult1`、`springbean`、`spikerock`
`levitater`、`meteorflower`、`endurian`、`stallia`、`strawburst1`、`aloes`、`mangofier`、`turkeypult`
`holonut`、`tombtangler`、`teleportatomine`、`explodeonut`、`sunbean`、`bombegranate`、`pyrevine`、`chillypepper`
`waterrabbit`、`buzzbutton`、`boomberry`、`draftodil1`、`headbutterlettuce`、`bloomerang1`、`akee1`、`cactus1`
`pepperpult`、`intensivecarrot`、`olivepit1`、`powervine1`、`puffball1`、`pvine1`、`snappea1`、`vamporcini1`
`parsnip1`、`phatbeet1`、`teleportatomine1`、`sapfling1`、`sunbean1`、`fairymushroom`、`carrotmissile`、`snowdrop`
`nightcap`、`seaflora`、`maybee`、`lemonaider`、`cutebubuseed`、`futurebubuseed`、`hotpotato`、`firepeashooter1`
`pyrevine1`、`stunion`、`bamboospartan`、`sundewtangler`、`beansprout`、`cranjelly`、`buduhboom`、`dragonbruit`
`dragonbabybruit`、`phantasmagnolia`、`plummet`、`plantain`、`electricpeel`、`tileturnip`、`solartomato`、`bloominghearts1`
`witchhazel1`、`citron1`、`inferno`、`explodeovine1`、`electricitea1`、`guardshroom`、`minishroom`、`aquavine`
`blastspinner`、`blastspinnercocoon`、`escaperoot1`、`magnetfruit`、`ultimatefumeshroom`、`chrysantheautumn`、`rabbagepult`、`sweetpotato1`
`ambershroom`、`threepeater1`、`banana`、`bitpeashooter`、`blover`、`cabbagepultpvz`、`citron2`、`coconutcannon_barrage`
`electriccurrant`、`empea`、`enlightenmint1`、`guacodile`、`holonut1`、`hotdate`、`hypnoshroom`、`inferno2`
`laser_bean`、`midi`、`minigame_music`、`noctarinecloud`、`oakshooter_barrage`、`old_sushi`、`pyrevine2`、`specialgarlic`
`starfruit_barrage`、`sushi`、`xshot_barrage`、`rheumnobile`、`darktwinsunflower`、`littleguy`、`seashooter`、`cerydra`
`suntower`、`poisonvine`、`beanchemist`、`desireflower`、`punkshocker`、`spookysquash`、`duckpear`、`fusiongatling`
`repeater1`、`wintergeddon`、`chinesechompingcabbage`、`longmalily`、`haystack`、`magicvine`、`hollybarrierleaf`、`hollybarrierleafplantfood`
`mikuleek`、`imppear_teto`、`exorcislily`、`doombell`、`gloombara`、`hysilens`、`cornucopia`、`littlerepeater`
`apsarlotus`、`oxygenalgae`、`kelpguard`、`seaderris`、`aquaweed`、`bubblecoral`、`firefly`

### 僵尸（1099）

原版有、客户端没有对应 id 的条目，按原表顺序：

`tutorial_armor4`、`tutorial_balloon`、`tutorial_flag_veteran`、`mummy_armor4`、`mummy_flag`、`mummy_flag_veteran`、`camel_almanac`、`camel_onehump`
`camel_twohump`、`camel_manyhump`、`camel_segment`、`camel_onehump_touch`、`camel_twohump_touch`、`camel_manyhump_touch`、`camel_segment_touch`、`pharaoh`
`ra`、`tomb_raiser`、`explorer`、`explorer_veteran`、`pirate_armor2`、`pirate_armor4`、`pirate_flag`、`pirate_flag_veteran`
`barrelroller`、`cannon`、`pirate_imp`、`seagull`、`pelican`、`pirate_captain`、`pirate_captain_parrot`、`swashbuckler`
`pirate_barrel`、`cowboy_armor2`、`cowboy_armor4`、`cowboy_flag`、`cowboy_flag_veteran`、`prospector`、`west_bullrider`、`west_bull`
`west_bull_veteran`、`poncho`、`poncho_no_plate`、`poncho_plate`、`piano`、`chicken_farmer`、`chicken`、`chicken_battlez`
`cowboy_tacochamp`、`mech_cone`、`mech_cone_veteran`、`disco_mech`、`future_armor2`、`future_armor4`、`future_flag`、`future_flag_veteran`
`future_jetpack`、`future_jetpack_veteran`、`future_jetpack_disco`、`future_gargantuar`、`future_imp`、`tutorial_imp`、`egypt_gargantuar`、`egypt_imp`
`pirate_gargantuar`、`cowboy_gargantuar`、`future_protector`、`future_protector_veteran`、`zombossmech_modern1`、`zombossmech_future`、`zombossmech_future2`、`zombossmech_future_battlez`
`zombossmech_future_rift`、`zombossmech_egypt`、`zombossmech_egypt2`、`zombossmech_egypt_battlez`、`zombossmech_cowboy`、`zombossmech_cowboy2`、`zombossmech_cowboy_battlez`、`zombossmech_cowboy_rift`
`zombossmech_pirate`、`zombossmech_pirate_battlez`、`zombossmech_pirate_rift`、`zombossmech_pirate2`、`zombossmech_dark`、`zombossmech_dark2`、`zombossmech_dark_battlez`、`zombossmech_dark_rift`
`zombossmech_beach`、`zombossmech_beach2`、`zombossmech_iceage`、`zombossmech_iceage2`、`zombossmech_iceage_battlez`、`zombossmech_lostcity`、`zombossmech_lostcity2`、`zombossmech_lostcity_battlez`
`zombossmech_eighties`、`zombossmech_eighties2`、`zombossmech_dino`、`zombossmech_dino2`、`zombossmech_dino_battlez`、`zombossmech_modern_egypt`、`zombossmech_modern_pirate`、`zombossmech_modern_cowboy`
`zombossmech_modern_future`、`zombossmech_modern_dark`、`zombossmech_modern_beach`、`zombossmech_modern_iceage`、`zombossmech_modern_lostcity`、`zombossmech_modern_eighties`、`zombossmech_modern_dino`、`cleopatra`
`treasureyeti`、`joustyeti`、`holiday_gargantuar`、`holiday_imp`、`leprachaun_imp`、`spring`、`spring_armor1`、`spring_armor2`
`spring_flag`、`spring_camel_onehump`、`spring_camel_twohump`、`spring_camel_manyhump`、`spring_camel_segment`、`spring_poncho`、`spring_wizard`、`spring_gargantuar`
`spring_gargantuar_af`、`spring_imp`、`spring_imp_af`、`halloween`、`halloween_armor1`、`halloween_armor2`、`halloween_flag`、`halloween_gargantuar`
`halloween_imp`、`halloween_camel_twohump`、`foodfight`、`foodfight_armor1`、`foodfight_armor2`、`foodfight_flag`、`foodfight_chefster`、`foodfight_gobbler_king`
`foodfight_turkey`、`foodfight_turkey_battlez`、`foodfight_turkey_boss`、`feastivus`、`feastivus_armor1`、`feastivus_armor2`、`feastivus_flag`、`feastivus_gargantuar`
`feastivus_imp`、`feastivus_camel_onehump`、`feastivus_camel_twohump`、`feastivus_camel_manyhump`、`feastivus_camel_segment`、`feastivus_swashbuckler`、`feastivus_poncho`、`feastivus_piano`
`nutcracker`、`easter_troglobite`、`easter_troglobite_1block`、`easter_troglobite_2block`、`feastivus_troglobite`、`feastivus_troglobite_1block`、`feastivus_troglobite_2block`、`pet`
`beach_armor1`、`beach_armor2`、`beach_flag`、`beach_fem`、`beach_fem_armor1`、`beach_fem_armor2`、`beach_snorkel`、`beach_surfer`
`beach_fastswimmer`、`beach_imp`、`beach_gargantuar`、`beach_fisherman`、`beach_octopus`、`iceage_armor1`、`iceage_armor2`、`iceage_armor3`
`iceage_armor4`、`iceage_flag`、`iceage_imp`、`iceage_gargantuar`、`iceage_hunter`、`iceage_chief`、`iceage_chief_veteran`、`iceage_hunter_veteran`
`iceage_weaselhoarder`、`iceage_weaselhoarder_veteran`、`iceage_weasel`、`iceage_weasel_veteran`、`iceage_troglobite`、`iceage_troglobite_2block`、`iceage_troglobite_1block`、`lostcity_impporter`
`lostcity_excavator`、`lostcity_armor1`、`lostcity_armor2`、`lostcity_flag`、`lostcity_jane`、`lostcity_lostpilot`、`lostcity_bug`、`lostcity_bug_armor1`
`lostcity_bug_armor2`、`lostcity_crystalskull`、`lostcity_imp`、`lostcity_gargantuar`、`lostcity_relichunter`、`lostcity_relichunter_veteran`、`relichunter_veteran_basic`、`relichunter_veteran_tool`
`relichunter_veteran_action`、`eighties_armor1`、`eighties_armor2`、`eighties_8bit`、`eighties_8bit_armor1`、`eighties_8bit_armor2`、`eighties_flag`、`eighties_imp`
`eighties_gargantuar`、`eighties_punk`、`eighties_mc`、`eighties_breakdancer`、`eighties_glitter`、`eighties_boombox`、`eighties_arcade`、`dino`
`dino_armor1`、`dino_armor2`、`dino_armor3`、`dino_armor4`、`dino_bully`、`dino_bully_veteran`、`dino_flag`、`dino_flag_veteran`
`dino_imp`、`dino_gargantuar`、`newspaper_veteran`、`modern_balloon`、`modern_allstar`、`modern_superfanimp`、`vase_gargantuar`、`hamster_ball`
`valentines`、`valentines_armor1`、`valentines_armor2`、`valentines_flag`、`valentines_gargantuar`、`valentines_imp`、`leprachaun_dodo`、`stpatrick`
`stpatrick_armor1`、`stpatrick_armor2`、`birthday`、`birthday_flag`、`birthday_barrel`、`birthday_gargantuar`、`birthday_pharaoh`、`birthday_juggler`
`birthday_troglobite`、`birthday_troglobite_2block`、`birthday_troglobite_1block`、`birthday_jetpack`、`summer_basic`、`summer_armor1`、`summer_armor2`、`summer_flag`
`summer_bug`、`summer_bug_armor1`、`summer_bug_armor2`、`summer_gargantuar`、`summer_imp`、`beghouled`、`beghouled_armor1`、`beghouled_armor2`
`beghouled_newspaper`、`beghouled_mummy`、`beghouled_mummy_armor1`、`beghouled_mummy_armor2`、`beghouled_pirate`、`beghouled_pirate_armor1`、`beghouled_pirate_armor2`、`beghouled_cowboy`
`beghouled_cowboy_armor1`、`beghouled_cowboy_armor2`、`beghouled_future`、`beghouled_future_armor1`、`beghouled_future_armor2`、`beghouled_dark`、`beghouled_dark_armor1`、`beghouled_dark_armor2`
`beghouled_beach`、`beghouled_beach_armor1`、`beghouled_beach_armor2`、`beghouled_beach_fem`、`beghouled_beach_fem_armor1`、`beghouled_beach_fem_armor2`、`beghouled_iceage`、`beghouled_iceage_armor1`
`beghouled_iceage_armor2`、`beghouled_lostcity`、`beghouled_lostcity_armor1`、`beghouled_lostcity_armor2`、`hero_electricboogaloo`、`hero_impfinity`、`hero_rustbolt`、`hero_smash`
`hero_superbrainz`、`hero_barrelroller`、`hero_barrel`、`bighead_allstar`、`bighead_balloon`、`bighead_newspaper`、`bighead_superfan`、`bighead_flag`
`bighead`、`bighead_armor1`、`bighead_armor2`、`bighead_gargantuar`、`bighead_imp`、`bighead_barrelroller`、`bighead_barrel`、`general_treadmill_phase1`
`general_treadmill_phase2`、`general_treadmill_phase3`、`general_zmech_phase1`、`general_zmech_phase2`、`general_zmech_phase3`、`zoybeanpod_gargantuar`、`zoybeanpod_basic`、`zoybeanpod_armor1`
`zoybeanpod_armor2`、`caketank`、`caketankfeastivus`、`imppear_imp`、`roman`、`roman_armor1`、`roman_armor2`、`roman_armor3`
`roman_armor4`、`roman_flag`、`roman_healer`、`roman_shield_almanac`、`roman_shield_triad`、`roman_shield_pair`、`roman_segment`、`roman_shield_top`
`roman_gargantuar`、`roman_imp`、`roman_ballista`、`gum`、`general_caesar_phase1`、`general_caesar_phase2`、`general_caesar_phase3`、`roman_medusa`
`zombie_statue`、`zcorp_gargantuar`、`zcorp_imp`、`zcorp`、`zcorp_armor1`、`zcorp_armor2`、`zcorp_fem`、`zcorp_fem_armor1`
`zcorp_fem_armor2`、`zcorp_flag`、`turkeypult_basic`、`turkeypult_turkzilla`、`zcorp_consultant`、`zcorp_helpdesk`、`solarsage_enlightened`、`zcorp_racer_chair`
`zcorp_racer`、`tigergrass_tiger`、`carnie`、`carnie_armor1`、`carnie_armor2`、`carnie_flag`、`carnie_cannon`、`carnie_imp`
`carnie_imp_twins`、`carnie_imp_split`、`carnie_gargantuar`、`carnie_armor4`、`carnie_monkey`、`carnie_magician`、`carnie_firebreather`、`carnie_dove`
`carnie_stiltwalker`、`zombossmech_circus`、`zombossmech_circus_battlez`、`zombossmech_circus_rift`、`lunar`、`lunar_armor1`、`lunar_armor2`、`lunar_flag`
`lunar_superfanimp`、`lunar_camel_onehump`、`lunar_camel_twohump`、`lunar_camel_manyhump`、`lunar_camel_segment`、`sportzball_buckethead`、`sportzball_balloon`、`sportzball_wizard`
`sportzball_imp`、`sportzball_gargantuar`、`duckytube`、`duckytube_armor1`、`duckytube_armor2`、`dino_cheese_pusher`、`dino_cheese_barrel`、`aircraft`
`air_missile_launcher`、`barrage`、`carnie_cannon_veteran`、`carnie_dove_veteran`、`carnie_firebreather_veteran`、`carnie_flag_veteran`、`carnie_imp_veteran`、`carnie_magician_veteran`
`carnie_monkey_veteran`、`carnie_stiltwalker_veteran`、`catch`、`cavalrygun`、`digger_zombie`、`duck`、`duck_armor1`、`duck_armor2`
`duck_armor4`、`duck_flag`、`duck_flag_veteran`、`eighties_8bit_armor3`、`eighties_arcade_veteran`、`eighties_armor4`、`eighties_armor4_ballad`、`eighties_armor4_punk`
`eighties_armor4_pop`、`eighties_armor4_rap`、`eighties_armor4_metal`、`eighties_bitpeashooter`、`eighties_boombox_veteran`、`eighties_popsinger`、`eighties_breakdancer_veteran`、`eighties_flag_veteran`
`eighties_glitter_veteran`、`eighties_mc_veteran`、`eighties_punk_veteran`、`fairy`、`fairy_armor1`、`fairy_armor2`、`fairy_armor3`、`fairy_flag`
`fairy_flag_veteran`、`fairy_gargantuar`、`fairy_armed_gargantuar`、`fairy_imp`、`fairy_armed_gargantuar2`、`fairy_imp2`、`fairy_imp_b`、`fairy_imp_normal`
`fairy_knight`、`fairy_knight_rider`、`fairy_tale`、`fairy_tale_armor1`、`fairy_tale_armor2`、`fairy_tale_armor3`、`fairy_tale_flag`、`fairy_tale_flag_veteran`
`fairy_tale_gargantuar`、`fairy_tale_armed_gargantuar`、`fairy_tale_imp`、`fairy_tale_armed_gargantuar2`、`fairy_tale_imp2`、`fairy_tale_knight`、`fairy_tale_cavalry`、`fairy_cavalry`
`fairy_tale_cavalry_summoned`、`fairy_tale_cavalry_spawner`、`fairy_tale_cavalry_horse`、`fairy_tale_knight_rider`、`fairy_tale_witch`、`fairy_tale_wizard`、`fairy_witch`、`fairy_wizard`
`fireball`、`fog2`、`football_mech_ori`、`future_ori`、`future_armor1_ori`、`future_armor2_ori`、`future_armor4_ori`、`future_flag_ori`
`future_flag_veteran_ori`、`future_protector_ori`、`future_gargantuar_ori`、`future_imp_ori`、`dark_ori`、`dark_armor1_ori`、`dark_armor2_ori`、`dark_flag_ori`
`dark_flag_veteran`、`dark_armor3`、`dark_armor4`、`dark_imp_ori`、`dark_imp_dragon`、`dark_gargantuar_ori`、`dark_wizard`、`dark_wizard_veteran`
`dark_juggler`、`dark_king`、`general_ikun_phase1`、`general_zmech_phase4`、`grinderhead_veteran`、`heavy_shield`、`heavy_shield`、`cavalrygun2`
`heian`、`heian_akinndo`、`heian_armor1`、`heian_armor2`、`heian_flag`、`heian_gargantuar`、`heian_hanabi`、`heian_ninja`
`heian_onmyoji`、`heian_onmyoji_veteran`、`heian_sushi`、`heian_worker`、`iceball`、`invisible_plane`、`invisible_plane_invisible`、`invisible_plane_shoot`
`jackbox`、`kongfu_armor1`、`kongfu_armor2`、`kongfu_armor3`、`kongfu_armrack_flag`、`kongfu_basic`、`kongfu_basic_armor1`、`kongfu_basic_armor2`
`kongfu_basic_armor3`、`kongfu_drink`、`kongfu_flag`、`kongfu_gong`、`kongfu_hammer`、`kongfu_monk`、`kongfu_monk_armor1`、`kongfu_monk_armor2`
`kongfu_monk_armor3`、`kongfu_monk_armrack_flag`、`kongfu_monk_basic`、`kongfu_monk_blade`、`kongfu_monk_bucket`、`kongfu_monk_cone`、`kongfu_monk_drink`、`kongfu_monk_flag`
`kongfu_monk_helmet`、`kongfu_monk_imp`、`kongfu_monk_nunchaku`、`kongfu_monk_torch`、`kongfu_qigong`、`kongfu_rocket`、`kongfu_selfexplode`、`kongfu_strong_bronze`
`kongfu_gargantuar`、`kongfu_torch`、`kongfu_torch_b`、`kongfu_gargantuar`、`kongfu_imp`、`kongfu_zomboss_blade`、`lineshoot`、`mech_cone_ori`
`mirror_queen`、`modern_allstar_ori`、`modern_digger`、`modern_miner`、`modern_pogo`、`modern_polevaulting`、`plantagenet`、`plantagenet_armor1`
`plantagenet_armor2`、`plantagenet_flag`、`plantagenet_gargantuar`、`plantagenet_imp`、`plantagenet_noblewoman`、`plantagenet_odin`、`plantagenet_princess`、`plantagenet_winetasting`
`plantagenet_winetasting_weak`、`pollution`、`pool`、`pool_allstar`、`pool_armor1`、`pool_armor2`、`pool_armor4`、`pool_balloon`
`pool_balloon2`、`pool_digger`、`pool_digger2`、`pool_digger_zombie`、`pool_flag`、`pool_flag_veteran`、`pool_football`、`pool_gargantuar`
`pool_imp`、`pool_newspaper`、`pool_newspaper2`、`pool_newspaper3`、`pool_polevaulting`、`pool_redeyes`、`pool_screendoor`、`pool_screendoor_bucket`
`pool_superfanimp`、`pvza_barrel`、`radiated_large`、`radiated_mid`、`radiated_small`、`ra_veteran`、`renai_ballet`、`renai_balletimp`
`renai_gargantuar`、`renai_gliding`、`renai_perfumer`、`sandstorm`、`selfdestroy`、`selfdestroy_b`、`skycity`、`skycity_armor1`
`skycity_armor2`、`skycity_armor3`、`skycity_battleplane`、`skycity_battleplane_shoot`、`skycity_dropship`、`skycity_dropship1`、`skycity_dropship10`、`skycity_dropship2`
`skycity_dropship3`、`skycity_dropship4`、`skycity_dropship5`、`skycity_dropship6`、`skycity_dropship7`、`skycity_dropship8`、`skycity_dropship9`、`skycity_electric`
`skycity_electric_negative`、`skycity_electric_positive`、`skycity_electric_shoot`、`skycity_electric_shoot_negative`、`skycity_electric_shoot_positive`、`skycity_flag`、`skycity_flag_veteran`、`skycity_gargantuar`
`skycity_gargantuar_noimps`、`skycity_ggtimp`、`skycity_shoot`、`skycity_shoot_armor1`、`skycity_shoot_armor2`、`skycity_shoot_armor3`、`skycity_twinsplane`、`skycity_twinsplane_shoot`
`skycity_win`、`solarsage_bully`、`steam_armor1`、`steam_armor2`、`steam_coal_miner`、`steam_flag`、`steam_gargantuar`、`steam_gentleman`
`steam_imp`、`steam_stove`、`steam_worker`、`toycar`、`lris_bird`、`lris_bird_pf`、`chinesegarden`、`chinesegarden_armor1`
`chinesegarden_armor2`、`chinesegarden_flag`、`chinesegarden_flag_veteran`、`chinesegarden_gargantuar`、`chinesegarden_imp`、`chinesegarden_umbrella`、`chinesegarden_poet`、`chinese_poet_spawner`
`chinesegarden_cujustar`、`chinesegarden_scientist`、`chinesegarden_imp_taoist`、`chinesegarden_carpimp`、`modern_football`、`tutorial_newspaper`、`tutorial_redeyes`、`tutorial_screendoor`
`tutorial_screendoor_bucket`、`twister_armor1`、`twister_armor2`、`twister_football`、`twister_worker`、`water_imp`、`white_noise_fairy_day`、`white_noise_fairy_night`
`wolfboss`、`wolffire`、`xzj`、`zamboni`、`zombieportal_beach`、`zombieportal_circus`、`zombieportal_dark`、`zombieportal_dino`
`zombieportal_egypt`、`zombieportal_eighties`、`zombieportal_future`、`zombieportal_heian`、`zombieportal_iceage`、`zombieportal_kongfu`、`zombieportal_lostcity`、`zombieportal_modern`
`zombieportal_pirate`、`zombieportal_renai`、`zombieportal_rome`、`zombieportal_skycity`、`zombieportal_steam`、`zombieportal_west`、`zombossmech_adventure`、`zombossmech_adventure2`
`zombossmech_added_adventure`、`zombossmech_dino3`、`zombossmech_heian`、`zombossmech_skycity`、`zomboss_car`、`zomboss_fireball_missile`、`zomboss_iceball_missile`、`zomboss_spawn_1`
`zomboss_spawn_2`、`zomboss_spawn_3`、`zomboss_spawn_4`、`zomboss_spawn_5`、`zomboss_spawn2_1`、`zomboss_spawn2_2`、`zomboss_spawn2_3`、`zomboss_spawn_added_1`
`zomboss_spawn_added_2`、`zomboss_spawn_added_3`、`catapult`、`zomboni`、`zombie_bobsled_team`、`zombie_bobsled_crew`、`raincoat`、`zombossmech_fairytale`
`zombossmech_fairytale_head1`、`zombossmech_fairytale_head2`、`zombossmech_added_fairytale`、`zombossmech_added_fairytale_head1`、`zombossmech_added_fairytale_head2`、`kiwifruit_stick`、`zombossmech_steam`、`zombossmech_added_steam`
`zombieportal_train`、`steam_train`、`steam_train_explosion`、`coal_steam_zomboss_cannon_phase2`、`coal_steam_zomboss_cannon_phase3`、`coal_steam_zomboss_imp`、`coal_steam_zomboss`、`general_base_moverow`
`wealth_god`、`wealth_god_minigame`、`lunar_cannon`、`lion_dancer`、`money_tree`、`yuanbao`、`nian_beast`、`nian_beast_added`
`nian_beast_special`、`west_bungee_almanac`、`west_bungee`、`west_bungee_alt`、`west_target`、`modern_target_retreat`、`football_mech_instant`、`zombossmech_added_egypt`
`zombossmech_added_pirate`、`zombossmech_added_cowboy`、`zombossmech_added_future`、`zombossmech_added_dark`、`zombossmech_added_beach`、`zombossmech_added_iceage`、`zombossmech_added_lostcity`、`zombossmech_added_eighties`
`zombossmech_added_dino`、`zombossmech_added_circus`、`zombossmech_added_kongfu`、`zombossmech_added_skycity`、`fairy_tale_cavalry_rider`、`dark_armor2`、`dark_flag`、`dark_imp`
`dark_gargantuar`、`renai_worker`、`renai`、`renai_flag`、`renai_armor1`、`renai_armor2`、`renai_perfumer2`、`renai_ballet2`
`renai_ballet_mid`、`renai_ballet_imp`、`renai_gliding2`、`renai_glider`、`gliding_plane_2`、`renai_carver`、`renai_imp`、`renai_gargantuar2`
`renai_roller`、`renai_sherlock`、`renai_antonio`、`renai_hamlet`、`renai_romeo`、`renai_romeo_spawner`、`renai_romeo_shift`、`renai_juliet`
`renai_original_statue`、`renai_zomboss_missile`、`renai_zomboss_missilespawner`、`renai_zomboss_missilelauncher`、`gliding_plane`、`renai_stage1`、`renai_stage2`、`renai_stage3`
`renai_stage_curtain`、`renai_stage_curtain2`、`renai_stage_transform`、`renai_stage_damage1`、`renai_stage_damage2`、`renai_wallet`、`renai_statue`、`renai_armor1_statue`
`renai_armor2_statue`、`renai_perfumer_statue`、`renai_carver_statue`、`zombossmech_renai`、`zombossmech_added_renai`、`statue_original`、`statue_renai`、`statue_renai_armor1`
`statue_renai_armor2`、`statue_renai_carver`、`statue_renai_perfumer`、`renai_statue_zombie1`、`renai_statue_zombie_armor1`、`renai_statue_zombie_armor2`、`renai_statue_zombie_carver`、`renai_statue_zombie_perfumer`
`fairy_fog_head1`、`fairy_fog_head2_spawner`、`fairy_fog_head2`、`fairy_fog_head2_effect`、`fairy_fog_head2_buff`、`fairy_mirror`、`fairy_mirror_added`、`fairy_mirror_added1`
`fairy_mirror_added2`、`fairy_mirror_added3`、`fairy_mirror_added4`、`fairy_mirror_added5`、`jttw`、`jttw_armor1`、`jttw_armor2`、`jttw_flag`
`jttw_flag_veteran`、`jttw_gargantuar`、`jttw_imp`、`jttw_balloon`、`jttw_allstar`、`jttw_digger`、`jttw_miner`、`jttw_digger_zombie`
`jttw_digger_zombie_attracted`、`jttw_superfanimp`、`jttw_trident`、`jttw_poncho`、`jttw_poncho_no_plate`、`jttw_poncho_plate`、`jttw_catapult`、`jttw_yellowbrow`
`jttw_goldclock`、`general_shift`、`jttw_yellowbrow_headdrop`、`jttw_racebag`、`jttw_redboy`、`jttw_redboy_spawner`、`jttw_redboy_shift`、`jttw_redboy_fireball`
`armrack_torch_spawner`、`armrack_monk_torch_spawner`、`armrack_hammer_spawner`、`armrack_helmet_spawner`、`armrack_monk_helmet_spawner`、`armrack_nunchaku_spawner`、`armrack_blade_spawner`、`armrack_bomb_spawner`
`armrack_flag_spawner`、`armrack_monk_flag_spawner`、`armrack_torch`、`armrack_trap_torch`、`armrack_trap_monk_torch`、`armrack_hammer`、`armrack_trap_hammer`、`armrack_helmet`
`armrack_trap_helmet`、`armrack_trap_monk_helmet`、`armrack_nunchaku`、`armrack_trap_nunchaku`、`armrack_blade`、`armrack_trap_blade`、`armrack_bomb`、`armrack_trap_bomb`
`armrack_flag`、`armrack_trap_flag`、`armrack_trap_monk_flag`、`zomboss_kongfu_qigong_meditate`、`zomboss_kongfu_qigong_stun`、`zomboss_kongfu_qigong_bounce`、`zomboss_kongfu_qigong_power`、`kongfu_qigong_b`
`kongfu_qigong_wave`、`kongfu_qigong_waveboss`、`kongfu_qigong_wave_spawner`、`zombossmech_added_kongfu_qigong`、`zombossmech_kongfu_qigong`、`kongfu_zomboss_qigong`、`gang`、`gang_armor1`
`gang_armor2`、`gang_loudmouth`、`magicshroom_hat`、`magicshroom_hat_yaoguang`、`carnie_trapeze_blue`、`carnie_trapeze_red`、`carnie_trapeze_yellow`、`carnie_trapeze_duo`
`carnie_trapeze_trio`、`carnie_trapeze_quad`、`carnie_trapeze_duo_spawner`、`carnie_trapeze_trio_spawner`、`carnie_trapeze_quad_spawner`、`carnie_trapeze_spawner1_yellow`、`carnie_trapeze_spawner1_red`、`carnie_trapeze_spawner2_yellow`
`carnie_trapeze_spawner2_blue`、`carnie_trapeze_spawner3`、`lostcity_guide`、`lostcity_doctor`、`lostcity_photographer`、`camera_spawner`、`lostcity_photographer_basic`、`dark_archmage`
`zombossmech_roman`、`zombossmech_roman_cl`、`zombossmech_added_roman`、`spirit_white`、`spirit_cyan`、`spirit_green`、`spirit_red`、`steam_mechanic`
`steam_mechanic_spawner`、`steam_mechanic_zombie`、`steam_clockwork`、`steam_clockwork_blue`、`steam_clockwork_green`、`zombotany_torchwood`、`zombotany_peashooter`、`zombotany_repeater`
`zombotany_firepeashooter`、`zombotany_threepeater`、`zombotany_bloomerang`、`zombotany_wallnut`、`zombotany_tallnut`、`zombotany_primalwallnut`、`zombotany_jalapeno`、`zombotany_potatochip`
`zombotany_potatomine`、`zombotany_phatbeet`、`zombotany_kiwibeast`、`zombotany_splitpea`、`zombotany_puffshroom`、`zombotany_snowpea`、`zombotany_seapotatomine`、`zombotany_snowlotus`
`zombotany_rosemary`、`zombotany_solarsage`、`zombossmech_market`、`zombossmech_added_market`、`zomboss_marketbox_speedracermower`、`zomboss_marketbox_iceburgfrenzy`、`zomboss_marketbox_gumexplosion`、`zomboss_marketbox_yetihaunted`
`zomboss_marketbox_greedymarket`、`zomboss_marketbox_popsmart`、`zomboss_marketbox_highvoltagepoles`、`zomboss_marketbox_undeaddefense`、`zomboss_marketbox_peashootervacation`、`zomboss_marketbox_buildaline`、`modern_disco`、`modern_dancer`
`gangster_imp_greaser`、`gangster_tyre`、`general_zmech_z7`、`zombossmech_chinesegarden`、`zombossmech_added_chinesegarden`、`mausoleum`、`mausoleum_armor1`、`mausoleum_armor2`
`mausoleum_armor4`、`mausoleum_flag`、`mausoleum_flag_veteran`、`mausoleum_cavalry`、`mausoleum_archer`、`mausoleum_assassin`、`mausoleum_vendor`、`mausoleum_piggy`
`mausoleum_shield`、`mausoleum_shield_pair`、`mausoleum_shield_triad`、`mausoleum_shield_quad`、`mausoleum_shield_pentad`、`mausoleum_shield_segment`、`mausoleum_terracotta_trog`、`mausoleum_taoist`
`mausoleum_terracotta`、`mausoleum_gargantuar`、`mausoleum_imp`、`mausoleum_drunk`、`mausoleum_token`、`mausoleum_token_defend`、`mausoleum_spirit`、`mausoleum_spirit_armor1`
`mausoleum_spirit_armor2`、`mausoleum_spirit_armor4`、`mausoleum_spirit_archer`、`mausoleum_spirit_assassin`、`mausoleum_spirit_gargantuar`、`mausoleum_spirit_drunk`、`mausoleum_ghost`、`mausoleum_ghost_armor1`
`mausoleum_ghost_armor2`、`mausoleum_ghost_armor4`、`mausoleum_ghost_archer`、`mausoleum_ghost_assassin`、`mausoleum_ghost_gargantuar`、`mausoleum_ghost_drunk`、`mausoleum_fireball`、`mausoleum_iceball`
`parkour_runner`、`af_kunz`、`af_godmother`、`af_leo`、`af_bluesexy`、`af_runner`、`af_bald`、`zombossmech_mausoleum`
`zombossmech_added_mausoleum`、`modern_polevaulter`、`feastivus_polevaulter`、`modern_dolphin`、`modern_screen`、`modern_pogostick`、`imposter`、`modern_ducky`
`modern_ducky_armor1`、`modern_ducky_armor2`、`atlantis`、`atlantis_flag`、`atlantis_flag_veteran`、`atlantis_armor1`、`atlantis_armor2`、`atlantis_armor4`
`atlantis_land`、`atlantis_land_flag`、`atlantis_land_flag_veteran`、`atlantis_land_armor1`、`atlantis_land_armor2`、`atlantis_land_armor4`、`atlantis_gargantuar`、`atlantis_imp`
`atlantis_land_gargantuar`、`atlantis_land_imp`、`atlantis_diver`、`atlantis_rider`、`atlantis_poseidon`、`atlantis_pitcher`、`atlantis_priest`、`zombotany_reed`
`zombotany_wintermelon`、`zombotany_lotusshooter`、`zombotany_draftodil`

## 一对多清单

### 原版重复 TypeName

- `heavy_shield` × 2：ZombieStatue（PopAnim POPANIM_EFFECTS_HEAVY_SHIELD，IntegerID 538）、ZombieRomanHealer（PopAnim POPANIM_EFFECTS_FOG，IntegerID 538）
- `kongfu_gargantuar` × 2：ZombieGargantuar（PopAnim POPANIM_ZOMBIE_ZOMBIE_KONGFU_STRONG_BRONZE，IntegerID 无）、ZombieLostCityGargantuar（PopAnim POPANIM_ZOMBIE_ZOMBIE_KONGFU_GARGANTUAR，IntegerID 187）

### 一个 client id 命中多条原版行

（无）

### 一条原版行承担多个客户端僵尸

（无）

## 需要人工确认的候选

### A0. 已按 `source_codename` 经人工表采信（`manual`）

这些僵尸的 `extra.source_codename` 指向的原版 `TypeName` 真实存在，经评审确认后写入 `tools/contentc/manual_mapping.csv`，CSV 中 `match_kind` 为 `manual`：

| client id | source_codename | 原版 TypeName | 原版 class | IntegerID | 人工表依据 |
|---|---|---|---|---|---|
| basic | tutorial | `tutorial` | ZombieBasic | 1 | extra.source_codename=tutorial 精确命中原版 TypeName，人工确认同一僵尸 |
| conehead | tutorial_armor1 | `tutorial_armor1` | ZombieBasic | 2 | extra.source_codename=tutorial_armor1 精确命中原版 TypeName，人工确认同一僵尸 |
| buckethead | tutorial_armor2 | `tutorial_armor2` | ZombieBasic | 3 | extra.source_codename=tutorial_armor2 精确命中原版 TypeName，人工确认同一僵尸 |
| flag | tutorial_flag | `tutorial_flag` | ZombieBasic | 4 | extra.source_codename=tutorial_flag 精确命中原版 TypeName，人工确认同一僵尸 |
| gargantuar | tutorial_gargantuar | `tutorial_gargantuar` | ZombieGargantuar | 80 | extra.source_codename=tutorial_gargantuar 精确命中原版 TypeName，人工确认同一僵尸 |
| football | football_mech | `football_mech` | ZombieMechFootball | 48 | extra.source_codename=football_mech 精确命中原版 TypeName，人工确认同一僵尸 |
| newspaper | modern_newspaper | `modern_newspaper` | ZombieModernNewspaper | 230 | extra.source_codename=modern_newspaper 精确命中原版 TypeName，人工确认同一僵尸 |
| pole_vaulter | iceage_dodo | `iceage_dodo` | ZombieIceAgeDodo | 146 | extra.source_codename=iceage_dodo 精确命中原版 TypeName，人工确认同一僵尸 |

### A1. `source_codename` 仍待人工确认的候选（未自动采信）

（无：本版所有能解析的 `source_codename` 都已在人工表里采信）

### A2. `source_codename` 指向原版不存在的条目（代号无效，不是没有线索）

这些 id 并非“缺线索”：它们自己写了代号，但本版原版表里没有这个 `TypeName`，
所以既不能按 exact 也不能按人工表归属，只能留在 client 独有一侧。

- `royal_zombie` → `royal`：原版表中没有这个 `TypeName`，代号指向不存在的条目。
- `royal_flag` → `royal_flag`：原版表中没有这个 `TypeName`，代号指向不存在的条目。

### B. PopAnim 同名但判为美术复用（未采信）

| side | client id | PopAnim 指向的原版 TypeName | 原版 class | IntegerID | 判据 |
|---|---|---|---|---|---|
| plant | rosemary | `spearmint` | PlantAppeasemint | 141 | PopAnim 相同但名称无关，判为美术复用 |
| plant | snowlotus | `enforcemint` | PlantPeashooter | 138 | PopAnim 相同但名称无关，判为美术复用 |
| plant | wildflower | `evilshroom_toughness` | PlantPrimalPeashooter | 57 | PopAnim 相同但名称无关，判为美术复用 |
| plant | olivewood | `olivepit` | PlantPeashooter | 164 | PopAnim 相同但名称无关，判为美术复用 |
| plant | cheesestrawberry | `explodeonut` | PlantCabbagepult | 115 | PopAnim 相同但名称无关，判为美术复用 |
| plant | oolongpeach | `tombtangler` | PlantAloe | 191 | PopAnim 相同但名称无关，判为美术复用 |
| plant | succulentgrape | `teleportatomine` | PlantCabbagepult | 184 | PopAnim 相同但名称无关，判为美术复用 |
| zombie | gargantuar | `future_gargantuar_ori` | ZombieGargantuarMech | 881 | 客户端 source_codename=tutorial_gargantuar 更权威 |

### C. almanac 编号碰撞（未采信）

客户端 `almanac_no` 是本项目自有的 1..147 编号，与原版 `IntegerID` 不构成同一套体系，同号共 102 条，全部只作候选。

其中撞在原版占位槽上的条目（说明这些位置在本版里被留空，而不是换了名字）：

| client id | almanac_no | 原版占位槽 |
|---|---|---|
| `iris` | 43 | `unused_43` |
| `snowlotus` | 45 | `unused_45` |
| `wildflower` | 46 | `unused_46` |
| `olivewood` | 47 | `unused_47` |
| `astrofruit` | 48 | `unused_48` |
| `chrysanthea` | 49 | `unused_49` |

其余同号碰撞（client=almanac_no→原版条目）：

`twinsunflower`=24→`lightningreed`、`gatling`=25→`peapod`、`umbrellaleaf`=30→`blover`、`rosemary`=44→`puffshroom`
`doominator`=50→`sunbean`、`helioscabbage`=51→`magnetshroom`、`vortexmelon`=54→`peanut`、`cheesestrawberry`=55→`fumeshroom`
`oolongpeach`=56→`evilshroom_speed`、`succulentgrape`=57→`evilshroom_toughness`、`doublepassion`=58→`lilypad`、`fireflerry`=59→`bowlingbulb`
`fused_wintergeddon`=63→`chomper`、`fused_paradoxpult`=64→`guacodile`、`fused_repeater1`=65→`ghostpepper`、`fused_primalsunflower`=66→`sweetpotato`
`fused_snowpea`=67→`sapfling`、`fused_snowpea_2`=68→`hurrikale`、`fused_wintermelon`=69→`xshot`、`fused_wintermelon_2`=70→`chardguard`
`fused_punkshocker`=71→`pepperpult`、`fused_headbutterlettuce`=72→`hotpotato`、`fused_headbutterlettuce_2`=73→`kiwibeast_deprecated`、`fused_birthsunflower`=74→`stunion`
`fused_suntower`=75→`sprout`、`fused_sweetpotato1`=76→`dandelion`、`fused_spikerock`=78→`redstinger`、`fused_iceweed`=79→`goldleaf`
`fused_iceweed_2`=80→`sungun`、`fused_rabbagepult`=81→`akee`、`fused_rabbagepult_2`=82→`lavaguava`、`fused_primalpeashooter`=83→`toadstool`
`fused_primalpeashooter_2`=84→`endurian`、`fused_magnetfruit`=85→`stallia`、`fused_magnetfruit_2`=86→`strawburst`、`fused_olivepit`=87→`cactus`
`fused_olivepit_2`=88→`phatbeet`、`fused_magnetshroom`=89→`thymewarp`、`fused_magnetshroom_2`=90→`celerystalker`、`fused_explodeonut1`=91→`electricblueberry`
`fused_explodeonut1_2`=92→`sporeshroom`、`fused_reinforcemint`=93→`garlic`、`fused_reinforcemint_2`=94→`impatiensshooter`、`fused_stickybombrice`=95→`jackolantern`
`fused_stickybombrice_2`=96→`primalpeashooter`、`fused_chardguard`=97→`grapeshot`、`fused_chardguard_2`=98→`primalwallnut`、`fused_puffball`=99→`coldsnapdragon`
`fused_darktwinsunflower`=100→`perfumeshroom`、`fused_darktwinsunflower_2`=101→`primalsunflower`、`fused_cactus1`=102→`primalpotatomine`、`fused_cactus1_2`=103→`shrinkingviolet`
`fused_frozenpear`=104→`moonflower`、`fused_frozenpear_2`=105→`nightshade`、`fused_lemonaider`=106→`shadowshroom`、`fused_lemonaider_2`=107→`bloominghearts`
`fused_poisonpeashooter`=108→`explodeovine`、`fused_poisonpeashooter_2`=109→`grimrose`、`fused_peppermint`=110→`dusklobber`、`fused_peppermint_2`=111→`goldbloom`
`fused_shadowpeashooter`=112→`electriccurrant`、`fused_shadowpeashooter_2`=113→`aloe`、`fused_endurian`=114→`wasabiwhip`、`fused_endurian_2`=115→`explodeonut`
`fused_strawburst`=116→`kiwibeast`、`fused_strawburst_2`=117→`applemortar`、`fused_coldsnapdragon`=118→`bombegranate`、`fused_coldsnapdragon_2`=119→`missiletoe`
`fused_snappea1`=120→`parsnip`、`fused_snappea1_2`=121→`witchhazel`、`fused_hollyknight`=122→`hotdate`、`fused_hollyknight_2`=123→`caulipower`
`fused_megagatling`=124→`solartomato`、`fused_megagatling_2`=125→`electricpeashooter`、`fused_fusiongatling`=126→`hollyknight`、`fused_fusiongatling_2`=127→`hollybarrierleaf`
`fused_hollybarrierleaf`=128→`hollybarrierleafplantfood`、`fused_hollybarrierleaf_2`=129→`filamint`、`fused_turkeypult`=130→`peppermint`、`fused_turkeypult_2`=131→`wintermint`
`fused_slingpea`=132→`enlightenmint`、`fused_slingpea_2`=133→`reinforcemint`、`fused_jasmine`=134→`bombardmint`、`fused_jasmine_2`=135→`ailmint`
`fused_pokra1`=136→`enchantmint`、`fused_pokra1_2`=137→`containmint`、`fused_draftodil1`=138→`enforcemint`、`fused_draftodil1_2`=139→`armamint`
`fused_gumnut`=140→`concealmint`、`fused_tumbleweed`=141→`spearmint`、`fused_tumbleweed_2`=142→`shadowpeashooter`、`fused_powervine`=143→`poisonpeashooter`
`fused_powervine_2`=144→`slingpea`、`fused_fusiongatling_3`=145→`appeasemint`、`fused_fusiongatling_4`=146→`minipeashooter`、`fused_fusiongatling_5`=147→`snappea`

### D. 原版重复 TypeName 的处理

重复条目当前都没有 client id 归属，因此不涉及二选一；等某个客户端僵尸要引用同名条目时，
必须按 `IntegerID` 或 `PopAnim` 指认具体一条，并在人工表里写明。

