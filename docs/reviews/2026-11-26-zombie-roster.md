# A9b · 僵尸/生物名册：按机制实际引用补进 `content/zombies.json`

**结论**：机制里被真正点名的 **57** 个僵尸/生物 id 全部解析成功，名册从 **55** 条扩到 **111** 条（新增 56，冲突 1，unresolved 0）。新增行一律 `source: "pack"`，手工 55 行逐字未动。引擎 `--audit-content content` 读出 `zombies=111` 并 exit 0，`zombie_roster.py --check` 幂等。

顺带查清了两件原任务点名要回答的事：**为什么 unresolved 是 0**（§五：57 个 RTID 在原表里全部命中），以及**引擎侧还缺什么**（§六：spider 行缺名字字段、鱼是 CreatureType 而内核没有 creature 实体）。

## 一、引用从哪来

只收「机制真的会生成」的 id，不把原版 1128 个 ZombieType 全塞进名册。

| 来源 | 具体字段 | 关数 | 不同 id | 说明 |
| --- | --- | ---: | ---: | --- |
| `spider` | `pkg_*_LevelDefinition.json` 的 `SpiderRainZombieSpawnerProps.SpiderZombieName` | 115 | 23 | `level_mechanics.json` 的 spider 行只投影 `spiderCount`，**不带名字**，必须回原表读 |
| `fish` 僵尸 | `levels[*].spawners.fish[*].zombies[].type` | 26 | 18 | `RTID(<name>@ZombieTypes)` |
| `fish` 生物 | `levels[*].spawners.fish[*].fishes[].type` | 21 | 7 | `RTID(<name>@CreatureTypes)`，是生物不是僵尸 |
| `minigame` | `minigames.json` 的 `params.whackazombie.SpawnWhackAZombiesProps[].Zombies[].Type` | 1 | 10 | 打僵尸小游戏点名的 10 个 |

合计 **57** 个不同 id：`spider 23 + fish 18 + fish_creature 7 + minigame 10`，其中 `beach_imp` 同时出现在 spider 与 minigame。

`level_mechanics.json` 有 spider 条目的关其实是 118 关，少掉的 3 关是 `SpiderCount: 0` 的「眼睛预警」行，本来就没有 `SpiderZombieName`：

| 关 | 包 |
| --- | --- |
| `egypt_25` | `pkg_0415` |
| `frontyard_162` | `pkg_1150` |
| `lostcity_65` | `pkg_0687` |

因此 `zombie_roster.json` 的 `references.spider` 记的是 **`ids 23 / levels 115`**，这是实测口径，不是笔误。

## 二、解析链（每一环都实测过）

```
RTID(name@ZombieTypes)   → pkg_2115_ZombieType.json   (1128 objects / 1214 aliases)
RTID(name@CreatureTypes) → pkg_0013_CreatureType.json (15 objects / 16 aliases)
objdata.Properties → RTID(x@ZombieProperties) → pkg_2112_ZombiePropertySheet.json (932 objects, 833 带 Hitpoints)
objdata.ZombieClass → zombie_classes.json → family（walk / gargantuar / jump / steal / summon / fly）
```

| 结果 | 数量 |
| --- | ---: |
| `objclass: ZombieType` | 49 |
| `objclass: CreatureType` | 7 |
| 解析到 `hp` | 49 |
| 没有 `hp`（生物行，键直接省略） | 7 |
| `family: walk` / `gargantuar` / `summon` | 41 / 7 / 1 |

族只出现三种，因为被点名的僵尸本来就是 imp 群、boss 级大块头（gargantuar）和一只能召唤的 poseidon：这跟 `zombie_classes.json` 的 6 族表不冲突，其余三族（jump/steal/fly）在这次的 57 个 id 里确实没有。

## 三、写进名册的行长什么样

`content/zombies.json` 的 56 条新增行统一是「拿到什么写什么」，**没拿到的键不写空串、更不写 null**：

```json
{
 "id": "atlantis",
 "behavior": "walk",
 "family": "walk",
 "hp": 190,
 "tags": ["zombie", "pack", "atlantis"],
 "source": "pack",
 "objclass": "ZombieType",
 "popAnim": "POPANIM_ZOMBIE_ZOMBIE_ATLANTIS_BASIC",
 "referencedBy": [{"kind": "fish", "level": "beach_23"}, "…共 15 条，全量不抽样"],
 "extra": {"packTypeName": "atlantis", "zombieClass": "ZombieAtlantisBasic",
           "popAnim": "POPANIM_ZOMBIE_ZOMBIE_ATLANTIS_BASIC", "homeWorld": "atlantis"}
}
```

生物行（7 条）没有 `family` / `hp` / `behavior`，改带 `creatureClass`：

```json
{"id": "hermitcrab", "tags": ["creature", "pack", "atlantis"], "source": "pack",
 "objclass": "CreatureType", "creatureClass": "FishHermitCrab",
 "popAnim": "POPANIM_PLANT_FISHS_FISH_HERMITCRAB", "referencedBy": […], "extra": {…}}
```

两条硬约束来自引擎读取（`native/src/catalog.cpp:236-260`）：

* `hp` 走 `number(j,"hp",p,190,true)`，**显式 null 会 fail**，所以生物行是「省略键」而不是 `"hp": null`；
* `optionalFields()`（`catalog.cpp:102-111`）只校验 `name_zh/name_en/art/behavior/desc_zh/tags/extra`，未知顶层键不报错 —— `source/objclass/family/popAnim/creatureClass/referencedBy` 因此可以安全落盘。

新增行**没有** `name_zh` / `name_en` / `art`：原表只给 `PopAnim`，中文名与美术键不在这一层，写空串会污染内容，所以一个都不写（后果见 §六）。

## 四、56 条新增清单

| id | objclass | family | hp | 引用关数 | kind |
| --- | --- | --- | ---: | ---: | --- |
| atlantis | ZombieType | walk | 190 | 15 | fish |
| atlantis_armor1 | ZombieType | walk | 190 | 17 | fish |
| atlantis_armor2 | ZombieType | walk | 190 | 16 | fish |
| atlantis_basic | ZombieType | walk | 190 | 2 | fish |
| atlantis_diver | ZombieType | walk | 320 | 16 | fish |
| atlantis_gargantuar | ZombieType | gargantuar | 2700 | 6 | fish |
| atlantis_land_armor1 | ZombieType | walk | 190 | 9 | fish |
| atlantis_land_armor2 | ZombieType | walk | 190 | 9 | fish |
| atlantis_land_basic | ZombieType | walk | 190 | 9 | fish |
| atlantis_land_gargantuar | ZombieType | gargantuar | 2700 | 6 | fish |
| atlantis_rider | ZombieType | walk | 190 | 12 | fish |
| beach_armor1 | ZombieType | walk | 190 | 1 | minigame |
| beach_armor2 | ZombieType | walk | 190 | 1 | minigame |
| beach_fem | ZombieType | walk | 190 | 1 | minigame |
| beach_fem_armor1 | ZombieType | walk | 190 | 1 | minigame |
| beach_fem_armor2 | ZombieType | walk | 190 | 1 | minigame |
| beach_imp | ZombieType | walk | 190 | 3 | minigame + spider |
| beach_octopus | ZombieType | walk | 910 | 1 | minigame |
| beach_snorkel | ZombieType | walk | 350 | 1 | minigame |
| beach_surfer | ZombieType | walk | 350 | 1 | minigame |
| bighead_imp | ZombieType | walk | 190 | 1 | spider |
| carnie_imp | ZombieType | walk | 190 | 1 | spider |
| chinesegarden_imp | ZombieType | walk | 190 | 42 | spider |
| cthulhu_jelly_fish | ZombieType | gargantuar | 2700 | 5 | fish |
| dark_imp_dragon | ZombieType | walk | 190 | 1 | spider |
| disco_mech | ZombieType | gargantuar | 2000 | 1 | spider |
| fairy_imp_normal | ZombieType | walk | 190 | 2 | spider |
| fat_dive | ZombieType | walk | 320 | 4 | fish |
| feastivus_imp | ZombieType | walk | 190 | 2 | spider |
| future_imp | ZombieType | walk | 270 | 39 | spider |
| future_imp_ori | ZombieType | walk | 270 | 3 | spider |
| giant_hermit_crab | ZombieType | gargantuar | 2700 | 6 | fish |
| heian_ninja | ZombieType | walk | 190 | 8 | spider |
| hermitcrab | CreatureType | — | — | 15 | fish_creature |
| hero_impfinity | ZombieType | walk | 190 | 2 | spider |
| iceage_imp | ZombieType | walk | 190 | 2 | spider |
| inkfish | CreatureType | — | — | 1 | fish_creature |
| jellyfish | CreatureType | — | — | 8 | fish_creature |
| kongfu_imp | ZombieType | walk | 190 | 1 | spider |
| kongfu_selfexplode | ZombieType | walk | 340 | 1 | spider |
| krill | CreatureType | — | — | 7 | fish_creature |
| lanternfish_rider | ZombieType | walk | 190 | 3 | fish |
| lostcity_relichunter_veteran | ZombieType | gargantuar | 10 | 3 | spider |
| lunar_superfanimp | ZombieType | walk | 270 | 1 | spider |
| modern_superfanimp | ZombieType | walk | 270 | 3 | spider |
| poseidon_assistant | ZombieType | summon | 550 | 8 | fish |
| priest | ZombieType | walk | 400 | 6 | fish |
| pufferfish | CreatureType | — | — | 4 | fish_creature |
| roman_imp | ZombieType | walk | 270 | 5 | spider |
| seaurchinpitcher | ZombieType | walk | 500 | 6 | fish |
| skycity_twinsplane | ZombieType | gargantuar | 1200 | 1 | spider |
| starfish | CreatureType | — | — | 4 | fish_creature |
| swordfish | CreatureType | — | — | 6 | fish_creature |
| tutorial_imp | ZombieType | walk | 190 | 2 | spider |
| west_bullrider | ZombieType | walk | 190 | 1 | spider |
| zcorp_imp | ZombieType | walk | 1100 | 1 | spider |

一处看着像 bug、其实是原表原值：`lostcity_relichunter_veteran` 的 `Properties` 指向 `ZombieLostCityRelicHunterVeteran@ZombieProperties`，而该 sheet 的 `objclass` 是 `ZombieCakeTankProps`、`Hitpoints` 就是 **10**。这是原版把「蛋糕坦克」的耐久套在 relichunter 身上，名册如实抄 10，不猜。

## 五、为什么 unresolved 是 0

57 个 RTID 全部在 `pkg_2115_ZombieType.json`（1214 个别名）或 `pkg_0013_CreatureType.json`（16 个别名）里命中，`hp` 也全部能顺着 `Properties` 在 `pkg_2112` 里查到 49 条（7 条生物本来就没有 Hitpoints）。

唯一没能新增的是 **冲突**（不是 unresolved）：`beach` 被小游戏引用，但手工名册已有同名行 `beach` —— 按「手工优先」保留手工行，冲突记进 `zombie_roster.json` 的 `conflicts`，不覆盖、不重复。

`unresolved` 这条通路不是摆设：`tools/tests/test_zombie_roster.py::test_unknown_rtid_is_reported_not_invented` 会喂一个假的 `RTID(no_such_zombie@ZombieTypes)`，断言它进 `unresolved` 而不是被编出一条空壳僵尸。

## 六、引擎侧还缺什么（点名文件:行号）

名册只是数据，引擎能不能真跑起来是另一回事。实测四条：

**1. spider 已经「有名册、没投影」。** `native/src/engine/mechanics.cpp:524-526` 与 `native/src/engine/mechanics.hpp:88-90` 的注释写的是：

> `spider` 是例外 —— 表里只有 spider 个数，而 55 条 content 僵尸和 1127 条 pack 僵尸里都没有蜘蛛，所以内核没有敌人可放。

这一句在本任务之后**过时了**：名册现在有 23 个 spider-rain 僵尸（`chinesegarden_imp`、`future_imp`、`heian_ninja`…）。缺的不是敌人在不在，而是**名字传不进投影**：`level_mechanics.json` 的 spider 行只有 `spiderCount`，所以 `native/src/engine/world.cpp:1120-1122` 的 `pool.empty()` 直接 return，计数进 `mechanicUnknown_["spawners.spider"]`。要接线，两层选一层：给 sheet 的 spider 行补 `spiderZombieName`（投影时按 kind 加白名单字段），或在引擎里读 `zombie_roster.json` 的 `referencedBy`。接线点：`mechanics.cpp:643-646` 的 `return kind != SpawnerKind::spider;`、`world.cpp:1130` 的 `storm || spider` 分支。

**2. 鱼是 `CreatureType`，内核没有 creature 实体。** `native/src/engine/mechanics.cpp:290-293` 的注释已经写明：

> `fishes[]` 是 CreatureTypes（寄居蟹），不是僵尸：内核没有 creature 实体，所以只计数，不当僵尸生成。

本任务把 7 条生物（`hermitcrab`/`jellyfish`/`krill`/`swordfish`/`starfish`/`pufferfish`/`inkfish`）按 `objclass: CreatureType` + `creatureClass` 写进名册，但**没有**把它们伪装成僵尸 —— 它们的行里连 `hp`/`behavior` 都没有，引擎即使误读也只会拿默认 `walk`/190，不会变成能咬植物的敌人。要真跑鱼群，需要一层 `CreatureEntity`（游过、可被溅射、是否受击），这是引擎的活，不在数据侧。

**3. 美术靠 `popAnim` 兜底。** 56 条新增行没有 `art`，但 49 条有 `popAnim`；`native/src/assets.hpp:27-31` 与 `native/src/assets.cpp:56-60` 的解析器本来就同时接受 `art` 键和 pack 的 `popAnim`，miss 会进 `missingArt()` 而不是崩。所以「没有 art」不等于「画不出来」，但确实需要一次实机确认哪些 popAnim 能在 shuttle 索引里落下。

**4. 名字只有 id 可显示。** `native/src/catalog.cpp:241` 的 `d.name = text(j, "name_zh", p)` 对 pack 行读出空串（本任务不发明中文名）。植物侧在 t83 加过 `name_zh → name_en → id` 的回落，僵尸侧没有等价回落；要显示得补同一处容错，或者等本地化表把这些 TypeName 接进来。

读取本身没有障碍：`--audit-content content` 读到 `zombies=111`、exit 0，说明 56 条新行在 `catalog.cpp:236-260` 的契约下是合法的。

## 七、验证与复现

```
python tools\contentc\zombie_roster.py --check
zombie-roster: authored=55 added=56 total=111 referenced=57 conflicts=1 unresolved=0 (spider=23 fish=18 fish_creature=7 minigame=9) hp 49/7 families[gargantuar=7 summon=1 walk=41]
产物已是最新
→ exit 0

python -m unittest tools.tests.test_zombie_roster
Ran 28 tests in 19.475s
OK

build\desktop-gate\Release\PvZ2SHUTTLE.exe --audit-content content
worlds=26
plants=409
zombies=111
levels=1809
original=1646
synthesized=163
unknown_source=0
vasebreaker=47
synthesized_vasebreaker=44
rules=json (no pack requested)
→ exit 0

python tools\obb_build_content_v2.py --content-report
content-report: levels=1809 vasebreaker=47 minecarts=190 rail=192 suppressFlag=271(true 215) derivedVasebreaker=47 derivedMinecarts=190 derivedRail=192 derivedSuppressFlag=271(true 215)
  plants=409 authored=147 pack=262 playable=304 blocked=35 conflicts=44 merged=409 packRoster=339
mismatches: none
→ exit 0
```

`--content-report` 里没有僵尸行是对的：那个 builder 只派生关卡与植物名册（`tools/obb_build_content_v2.py`），僵尸名册由 `zombie_roster.py` 自己守。之所以仍然跑它，是为了确认 111 条僵尸没有把关卡与植物口径带歪 —— `mismatches: none` 就是这个确认。

下游各工具的 `--check` 也逐个复跑（它们都读 `content/zombies.json`）：

```
python tools\contentc\zgaps.py --check
产物已是最新：rows=55 pack=28 authored=27 unknown=0 gaps=0 applied=3 families=walk=50,gargantuar=5
→ exit 0
python tools\contentc\metagame.py --check
产物已是最新：almanac=167p+428z garden=65 quests=240(69 rewards) daily=11 achievements=53 unknowns=10
→ exit 0
python tools\contentc\armors.py --check
armors=102 zombies=1127 armored=276 unknownProps=47 dangling=3 multi=16 | OK
→ exit 0
python tools\contentc\original_gaps.py --check
产物已是最新：entities=12 tables=46 mapped=13081 packOnly=787 clientOnly=14216 systems=13 packOnlySystems=7 unverified=0 sheets=2116 levels=1809
→ exit 0
python tools\contentc\mechanic_entity_resolution.py --check
[ok] mechanic_entity_resolution.json and report are current
→ exit 0
```

全量套件（收尾那次）：

```
python -m unittest discover -s tools/tests -p "test_*.py"
Ran 921 tests in 900.368s
FAILED (failures=2, skipped=2)
```

这 2 例**都不是本任务的产物**，是 `native/generated/snapshot_baseline.json`（D5 截图基线，另一个 agent 的产物）还没登记进 `tools/tests/test_gate_coverage.py` 的 `PRODUCTS`：

```
FAIL test_a_new_unregistered_product_is_reported
  ['brand_new_table.json', 'snapshot_baseline.json'] != ['brand_new_table.json']
FAIL test_registry_covers_every_generated_file
  ['snapshot_baseline.json'] != []
```

我自己的 `zombie_roster.json` 已经按 `no-check` + `covered_by=tools/tests/test_zombie_roster.py` 登记（`zombie_roster.py` 有 `--check`，但 `tools/check_all.ps1` 本任务不许改，没有对应 Step）。

## 八、边界

改动的路径（全部未 commit）：

| 路径 | 说明 |
| --- | --- |
| `content/zombies.json` | 55 → 111 行（26,685 → 70,468 B），手工 55 行逐字未动 |
| `native/generated/zombie_roster.json` | 新增，51,732 B，`generated: null`（禁墙钟） |
| `tools/contentc/zombie_roster.py` | 新增，编译器 + `--check` / `--dry-run` / `-n` |
| `tools/tests/test_zombie_roster.py` | 新增，28 例 |
| `docs/reviews/2026-11-26-zombie-roster.md` | 本文 |
| `tools/contentc/zgaps.py` | 只加「跳过 `source == "pack"`」过滤（`--check` 仍按 55 条口径） |
| `tools/contentc/mechanic_entity_resolution.py` | 同上 |
| `tools/contentc/metagame.py` | `content_ids(path, skip_pack=False)`，僵尸交叉用 `skip_pack=True` |
| `tools/contentc/model.py` | `ids_of(name, skip_pack=False)`，`zombies.json` 传 True |
| `tools/contentc/original_gaps.py` | 客户端僵尸只取手写行 |
| `tools/contentc/armors.py` | 内容对照只取手写行 |
| `tools/validate_all.py` | 僵尸段只校验手写行（否则 56 条 pack 行会被当成缺字段） |
| `tools/tests/test_metagame.py` | `test_zombie_intersection` 传 `skip_pack=True`（口径不变，仍比图鉴交集） |
| `tools/tests/test_gate_coverage.py` | `PRODUCTS` 登记 `zombie_roster.json`（no-check + covered_by） |

未改：`native/src/**`（§六 的引擎缺口只记录不实现）、除 `zombie_roster.json` 外的 `native/generated/**`、`tools/check_all.ps1`。原 `content/zombies.json` 备份在 `D:\Temp\User\t105_zombies_before.json`，探针脚本已删。
