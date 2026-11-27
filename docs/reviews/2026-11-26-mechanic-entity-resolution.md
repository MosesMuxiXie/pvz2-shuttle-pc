# 机制 unknown 的实体解析（A9）

生成：`python tools/contentc/mechanic_entity_resolution.py`  产物：`native/generated/mechanic_entity_resolution.json`（sha256:3742916456198d07）

## 一、结论摘要

| 项 | 结论 | 关键数字 |
|---|---|---|
| spider（118 关） | **实体存在**，`SpiderZombieName` 直通 ZombieType alias | 322 个对象 / 119 包 / 23 个名字，未命中 0 |
| fish（26 关） | **实体存在**，`Fishes[]` 落 CreatureType 表 | 301 个对象 / 26 包 / 7 个生物，未命中 0 |
| unscheduled `grid` | 原版**没有波次字段**，全部 orphan | 21 条 / 13 关 / 17 个 alias |
| unscheduled `portal` | 原版**没有波次字段**，全部 orphan | 17 条 / 5 关 / 5 个 alias |
| unscheduled `storm` | 原版**没有波次字段**，全部 orphan | 1 条 / 1 关 / 1 个 alias |
| unscheduled `ground` | 原版**没有波次字段**，全部 orphan | 22 条 / 7 关 / 13 个 alias |
| unscheduled `dino` | 原版**没有波次字段**，全部 orphan | 64 条 / 9 关 / 44 个 alias |

一句话：**两类「没有实体」都是误判** —— OBB 里有完整的僵尸/生物定义，缺的是客户端 `content/zombies.json`（只有 55 条通用 id）。五类 unscheduled 则是真的没排波（原表里根本不存在波次字段）。

## 二、取证方法与搜索矩阵

两路并搜（objclass 名 + objdata 字段名，大小写不敏感子串），扫 `work/obb_packages` 全量 pkg：

| 组 | 搜索词 | 命中类（个数/包） | 类名样例 | 命中对象 | 字段名样例 |
|---|---|---|---|---|---|
| spider | `Spider` | 2 / 120 包 | `DangerRoomSpiderRainDesigner`, `SpiderRainZombieSpawnerProps` | 455 | `basespiderraincount`, `basespiderraincountperlevel`, `basespiderrainstartwave` |
| spider | `SpiderRain` | 2 / 120 包 | `DangerRoomSpiderRainDesigner`, `SpiderRainZombieSpawnerProps` | 14 | `basespiderraincount`, `basespiderraincountperlevel`, `basespiderrainstartwave` |
| spider | `ZombieSpider` | 0 / 0 包 | — | 0 | — |
| spider | `SpiderRainPhase` | 0 / 0 包 | — | 0 | — |
| spider | `RainZombies` | 2 / 162 包 | `ParachuteRainZombieSpawnerProps`, `SpiderRainZombieSpawnerProps` | 13 | `basespiderrainzombiescountperlevel`, `maxspiderrainzombies` |
| spider | `SpawnZombiesFromSkyAction` | 0 / 0 包 | — | 0 | — |
| fish | `Fish` | 8 / 30 包 | `FishBasePropertySheet`, `FishHermitCrabPropertySheet`, `FishHookProjectileProps` | 84 | `beach_fisherman`, `candamagezombieandfish`, `candamagezombieandfishplantfoodonly` |
| fish | `Fisherman` | 1 / 1 包 | `ZombieBeachFishermanProps` | 1 | `beach_fisherman` |
| fish | `Hermitcrab` | 1 / 1 包 | `FishHermitCrabPropertySheet` | 0 | — |
| fish | `SeaWave` | 0 / 0 包 | — | 0 | — |
| fish | `TideWave` | 1 / 10 包 | `TideWaveWaveActionProps` | 0 | — |
| fish | `ZombieFish` | 0 / 0 包 | — | 0 | — |

实体表规模（这两张表是整个结论的地基）：

- `ZombieType`：1424 个对象 / **1319 个 alias**（pkg_2115_ZombieType.json）
- `CreatureType`：15 个对象 / **15 个 TypeName**（pkg_0013_CreatureType.json）：cthulhujelly, dinoankylo, dinoptero, dinoraptor, dinostego, dinotyranno, fishraptor, hermitcrab, inkfish, jellyfish, krill, pufferfish, smalljellyfish, starfish, swordfish
- 客户端 `content/zombies.json`：**55 条**（basic/beach/buckethead/conehead/cowboy/…）

## 三、spider：不是蜘蛛，是空投的 imp 家族

`SpiderRainZombieSpawnerProps` 在 119 个包里出现 322 次，载荷字段是 `SpiderZombieName`——它直接就是 ZombieType alias：

| SpiderZombieName | 对象数 |
|---|---|
| chinesegarden_imp | 118 |
| future_imp | 114 |
| heian_ninja | 25 |
| future_imp_ori | 7 |
| fairy_imp_normal | 6 |
| roman_imp | 5 |
| beach_imp | 4 |
| feastivus_imp | 4 |
| modern_superfanimp | 4 |
| hero_impfinity | 3 |
| iceage_imp | 3 |
| kongfu_imp | 3 |
| lostcity_relichunter_veteran | 3 |
| tutorial_imp | 3 |
| disco_mech | 2 |
| bighead_imp | 1 |
| carnie_imp | 1 |
| dark_imp_dragon | 1 |
| kongfu_selfexplode | 1 |
| lunar_superfanimp | 1 |
| skycity_twinsplane | 1 |
| west_bullrider | 1 |
| zcorp_imp | 1 |

未命中 ZombieType 表的取值：**0 个**。`SpiderCount` 为 0 的对象 11 个（只带 `WaveStartMessage`，投不出僵尸，是纯警告）。

这就是 wirer 判「数据里没有 spider 实体」的来路：全表没有名字含 `spider` 的 ZombieType（`alias containing spider` = 0），但这恰恰说明 `SpiderRain` 是**引擎的动作名**（下僵尸雨），不是生物名。

## 四、fish：两套命名空间（僵尸 + 生物）

`SpawnZombiesFishWaveActionProps` 在 26 个包里出现 301 次，同时带两张表：

- `Zombies[]`：普通僵尸（`atlantis`/`atlantis_armor1`/`atlantis_diver`/`atlantis_rider`/…），带 `Direction` 与数量；
- `Fishes[]`：`RTID(<name>@CreatureTypes)`，是**海生物**，另有纯数字项 0 个。

| CreatureType | 对象数 | CreatureClass | PopAnim | Properties |
|---|---|---|---|---|
| hermitcrab | 72 | `FishHermitCrab` | `POPANIM_PLANT_FISHS_FISH_HERMITCRAB` | `RTID(HermitCrabDefault@PropertySheets)` |
| jellyfish | 41 | `FishJellyfish` | `POPANIM_PLANT_FISHS_FISH_JELLYFISH` | `RTID(JellyfishDefault@PropertySheets)` |
| swordfish | 32 | `FishSwordfish` | `POPANIM_PLANT_FISHS_FISH_SWORDFISH` | `RTID(SwordfishDefault@PropertySheets)` |
| krill | 21 | `FishBase` | `POPANIM_PLANT_FISHS_FISH_KRILL` | `RTID(KrillDefault@PropertySheets)` |
| pufferfish | 4 | `FishBase` | `POPANIM_PLANT_FISHS_FISH_PUFFERFISH` | `RTID(PufferfishDefault@PropertySheets)` |
| starfish | 4 | `FishBase` | `POPANIM_PLANT_FISHS_FISH_STARFISH` | `RTID(StarfishDefault@PropertySheets)` |
| inkfish | 2 | `FishBase` | `POPANIM_PLANT_FISHS_FISH_INKFISH` | `RTID(InkfishDefault@PropertySheets)` |

未命中 CreatureType 表的取值：**0 个**；`Zombies[]` 侧未命中 ZombieType 的 0 个。

CreatureType 每条都自带美术与属性绑定（`AnimRigClass`/`HomeWorld`/`PopAnim`/`Properties`/`ResourceGroups`），所以引擎只要按名字查表就能生成——不需要额外资源映射。

## 五、unscheduled：原表没有波次字段，五类全是 orphan

抽取器的波次只来自两处：`WaveManagerProperties.Waves[i]` 里的 `RTID(<alias>@CurrentLevel)`，或 alias 自带 `Wave<数字>`（`tools/contentc/mechanics.py` 的 `Package.wave_map()` 与 `wave_number()`）。本表把每条 `wave: null` 记录按这两条判据重新分档：

| kind | objclass | 记录数 | wave=null | 涉及关卡 | 不同 alias | 分档 |
|---|---|---|---|---|---|---|
| `grid` | `SpawnZombiesFromGridItemSpawnerProps` | 705 | **21** | 13 | 17 | in-waves 0 / digitless 0 / **orphan 21** |
| `portal` | `SpawnModernPortalsWaveActionProps` | 684 | **17** | 5 | 5 | in-waves 0 / digitless 0 / **orphan 17** |
| `storm` | `StormZombieSpawnerProps` | 375 | **1** | 1 | 1 | in-waves 0 / digitless 0 / **orphan 1** |
| `ground` | `SpawnZombiesFromGroundSpawnerProps` | 323 | **22** | 7 | 13 | in-waves 0 / digitless 0 / **orphan 22** |
| `dino` | `DinoWaveActionProps` | 887 | **64** | 9 | 44 | in-waves 0 / digitless 0 / **orphan 64** |

**全部 125 条都在 `orphan` 档**（in-waves 0、digitless 0）——即没有任何一条是「alias 在波里但抽取器没认出来」，也没有「带数字却没被正则兜住」。所以 `wave: null` 是数据事实：这些 spawner 由别的动作（`Move`/`PWTap`/`CA2`/`Fog1`… 这类命名事件）或「任意波」触发。

各 kind 的 alias 全集（最多 80 个）：

- `grid`：`CA2`, `Fog1`, `Fog2`, `Fog3`, `Lost`, `Move`, `PWWP`, `SpawnForShow_relichunter_veteran`, `WaveATool`, `WaveBTool`, `WaveHTool`, `WaveMFTool`, `WaveNTool`, `WaveTTool`, `WaveX`, `WaveXNecromancyEvent0`, `Zmech`
- `portal`：`PortalsEvent0`, `PortalsEvent1`, `PortalsEvent2`, `PortalsEvent3`, `PortalsEvent4`
- `storm`：`snowstormEvent0`
- `ground`：`Drag1`, `Drag3`, `SpawnFairy4`, `Sta1`, `Tap1`, `Tap3`, `TapFast1`, `TapFast3`, `TapTap1`, `TapTap3`, `TapTapFast1`, `TapTapFast3`, `Wave`
- `dino`：`JIA3`, `JIA5`, `JL2`, `JL4`, `StegoLane1`, `StegoLane2`, `StegoLane3`, `StegoLane4`, `StegoLane5`, `WaveADinoTimeEvent2`, `WaveTDinoTimeEvent0`, `WaveTDinoTimeEvent1`, `WaveTDinoTimeEvent2`, `WaveTDinoTimeEvent3`, `WaveTDinoTimeEvent4`, `XM1`, `XM3`, `Y-StegoLane1`, `Y-StegoLane2`, `Y-StegoLane3`, `Y-StegoLane4`, `Y-StegoLane5`, `fly1`, `fly2`, `fly3`, `fly4`, `fly5`, `kick2`, `kick3`, `kick4`, `push1`, `push2`, `push3`, `push4`, `push5`, `run1`, `run2`, `run3`, `run4`, `sweep1`, `sweep2`, `sweep3`, `sweep4`, `sweep5`

抽 3 关的原始 objdata（完整 JSON 在产物的 `unscheduled.<kind>.sampleLevels[].raw`）：

| kind | 关卡 | 包 | alias | 分档 | 该关 null 条数 |
|---|---|---|---|---|---|
| grid | kongfu_38 | `pkg_1399_LevelDefinition.json` | `WaveMFTool` | orphan | 6 |
| grid | pirate_39 | `pkg_1545_LevelDefinition.json` | `Fog1` | orphan | 3 |
| grid | fairy_46 | `pkg_1027_LevelDefinition.json` | `Move` | orphan | 2 |
| portal | beach_76 | `pkg_1666_LevelDefinition.json` | `PortalsEvent4` | orphan | 5 |
| portal | memorytour_6 | `pkg_1667_LevelDefinition.json` | `PortalsEvent4` | orphan | 5 |
| portal | modern_84 | `pkg_1665_LevelDefinition.json` | `PortalsEvent4` | orphan | 5 |
| storm | iceage_70 | `pkg_0933_LevelDefinition.json` | `snowstormEvent0` | orphan | 1 |
| ground | eighties_51 | `pkg_0867_LevelDefinition.json` | `Drag1` | orphan | 6 |
| ground | eighties_62 | `pkg_0870_LevelDefinition.json` | `Tap1` | orphan | 5 |
| ground | eighties_55 | `pkg_0868_LevelDefinition.json` | `Drag1` | orphan | 4 |
| dino | carnival_12 | `pkg_0262_LevelDefinition.json` | `sweep1` | orphan | 20 |
| dino | carnival_7 | `pkg_0259_LevelDefinition.json` | `sweep1` | orphan | 12 |
| dino | plantagenet_46 | `pkg_0696_LevelDefinition.json` | `StegoLane1` | orphan | 10 |

原始 objdata 里名字带 `wave` 的字段（逐类，来自全部 null 记录，不是抽样）：

| kind | 原表里带 wave 字样的字段 |
|---|---|
| `grid` | `WaveStartMessage` |
| `portal` | **一个都没有** |
| `storm` | `Waves` |
| `ground` | `WaveStartMessage` |
| `dino` | `DinoWaveDuration` |

逐个看它们的真身，没有一个是波号：

- `WaveStartMessage`：开局提示文案的**本地化键**（`[WARNING_GRAVESTONE_SPAWN]` 之类），grid / ground 全部命中它；
- `DinoWaveDuration`：恐龙事件的**持续秒数**（样例 `iceage_70` 隔壁的 dino 对象是 `{"DinoRow": 0, "DinoType": "stego", "DinoWaveDuration": 2}`）；
- `Waves`：`StormZombieSpawnerProps` 上真有这个键，但值是**空串**（`iceage_70` 的 `snowstormEvent0`：`"Waves": ""`，同对象靠 `Type: "snowstorm"` 与 `ColumnStart/ColumnEnd/GroupSize` 定位）；
- `portal` 这一类连名字带 wave 的字段都没有。

所以「`wave: null`」不是抽取失败，而是原表**没有**这个维度。

## 六、对引擎的建议

1. **spider 立即接线**：`spider` 的实体就是 `SpiderZombieName` 指的普通僵尸，按 `SpiderCount` 数量、`ColumnStart..ColumnEnd` 列范围、`ZombieFallTime` 下落时长生成即可；`SpiderCount==0` 的 11 个对象只播 `WaveStartMessage`，不要生成僵尸。
2. **fish 立即接线**：`Fishes[]` 走 `CreatureType`（CreatureClass/PopAnim/Properties），`Zombies[]` 走既有 ZombieType 通道；两类同时出现时按原表顺序各自生成。
3. **unscheduled 保持 unknown**（不猜波号）：这 125 条没有波次归属，引擎应在关卡开始后按「事件驱动」处理——有明确触发者（`Move`/`PWTap`/`Fog*`/`CA2`）的跟随触发者；无触发者的一律在首波入场时执行一次，并记 `wave: null` 供日志区分。
4. **不要再用 `content/zombies.json` 判断实体是否存在**：它只有 55 条通用 id；判断实体要走 `pkg_2115_ZombieType.json`（1319 alias）与 `pkg_0013_CreatureType.json`（15 类型）。

## 七、如果原版真是空动作，118 关怎么降级

本表的结论是「不是空动作」——但如果哪天要按「原版空实现」兜底，降级顺序建议是：

1. `spider`：把 `SpiderCount` 当普通僵尸投放到同列（`ColumnStart..ColumnEnd`），失去「从天而降」的观感但不影响难度曲线；`SpiderCount==0` 的对象直接当纯提示。
2. `fish`：只保留 `Zombies[]`（atlantis 僵尸族），`Fishes[]` 视为装饰；寄居蟹/剑鱼的碰撞与伤害按 `PropertySheets` 缺席处理（`Hitpoints` 取 0）。
3. `unscheduled`：全部按「首波执行一次」，日志标 `wave: null`；关卡通关条件不依赖这些 spawner，因此不改变胜负判定。
4. 任何降级都只在**渲染/生成**层生效，不改 `level_mechanics.json` 的 `wave` 字段，保证「数据事实」与「引擎策略」可分辨。

## 八、复现与校验

```
python tools/contentc/mechanic_entity_resolution.py           # 生成
python tools/contentc/mechanic_entity_resolution.py --check    # 0=最新 2=过期
python -m unittest tools.tests.test_mechanic_entity_resolution
```

原始探针（一次性，未入库）：`work/a9_scan.py`（三路术语扫描）、`work/a9_scan2.py`（字段值分布）、`work/a9_scan3.py`（CreatureType/ZombieType 表）、`work/a9_scan4.py`（clientId 逐条对表）、`work/a9_unscheduled.py`（原始模块 JSON）、`work/a9_unscheduled2.py`（三档分类账）。

