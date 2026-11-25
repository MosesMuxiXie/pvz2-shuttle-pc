# 关卡机制编译（T51）

把 1809 关的关卡机制从原版 `LevelDefinition` 包编译成一份客户端可读的表。生成的 `native/generated/level_mechanics.json` 是**数据**，不含任何逻辑；引擎侧按 `levels[levelId][mechanic]` 取用，`null` 表示这一关没有该机制。

## 一、身份映射（先看这节）

客户端 `content/levels/*.json` 的 `extra.package` 形如 `"pkg_0264"`，直接对应 `work/obb_packages/pkg_0264_LevelDefinition.json`。

实测：

- 客户端关卡 1809 个，`extra.package` 命中包文件 1809 个；缺文件 0 个、无 package 字段 0 个、解析失败 0 个。
- 同一个包被多关共用：0 例（见 `unknowns` 里的 `package-shared`）。共用包的多关拿到的是同一份机制数据 —— 这是锚点选择的直接后果，不是缺失。
- 包名撞车（一个 stem 匹配多个文件）：0 例。

**不要用 `StageModule` + `LevelNumber` 当锚点**：那对键在 1809 关里只有 1385 个不同值，1809 -> 1385 不唯一（t37 已确认），用它会把不同关卡的机制搅在一起。

## 二、覆盖（实测计数）

| 机制 | 关数 | 原版对象 | 备注 |
|---|---|---|---|
| `conveyor` | 350 | `ConveyorSeedBankProperties` | 其中 349 关有卡槽表、132 关有 `ModifyConveyorWaveActionProps` 改动波 |
| `initialPlants` | 272 | `InitialPlantProperties` | 含 `InitialPlantPlacements` |
| `initialGridItems` | 690 | `InitialGridItemProperties` + `GravestoneProperties` | 其中 466 关有格位摆放、241 关有墓碑对象 |
| `protectThePlant` | 286 | `ProtectThePlantChallengeProperties` | 同包多模块已合并（287 个模块）；失败判定在引擎侧，见第七节 |
| `spawners` | 1645 | 8 类生成器 + `gravestone` + `jittered` | `spawners.<kind>[]` 逐条，`jittered` 是聚合摘要（见下） |
| `events` | 123 | `TidalChangeWaveActionProps` / `FrostWindWaveActionProps` | 潮汐取 `changeAmount` 绝对值之和当强度 |
| `mutators` | 21 | `LevelMutator*` | level 文件里只出现 3 类 |
| `boardGrid` | 49 | `BoardGridMapProps` | `Values` 是 0/1 矩阵，用于非标准行数 |

生成器按类的关卡数（一个关卡可以有多类）：

| `spawners.<kind>` | 关数 | 原版类 |
|---|---|---|
| `beach` | 82 | `BeachStageEventZombieSpawnerProps` |
| `dino` | 93 | `DinoWaveActionProps` |
| `fish` | 26 | `SpawnZombiesFishWaveActionProps` |
| `gravestone` | 353 | `SpawnGravestonesWaveActionProps` |
| `grid` | 237 | `SpawnZombiesFromGridItemSpawnerProps` |
| `ground` | 100 | `SpawnZombiesFromGroundSpawnerProps` |
| `jittered` | 1615 | `SpawnZombiesJitteredWaveActionProps` |
| `portal` | 130 | `SpawnModernPortalsWaveActionProps` |
| `spider` | 118 | `SpiderRainZombieSpawnerProps` |
| `storm` | 119 | `StormZombieSpawnerProps` |

> 任务列了八类生成器。实测必须多带两类，否则数据会看起来「缺一大块」：
> `gravestone`（墓石生成）与 `jittered`（普通波次的主力 —— 不加它，80 个关卡的僵尸就凭空消失）。两类都放在 `spawners` 子键里，不额外占顶层机制键。

**`spawners.jittered` 是聚合摘要，其余九类是逐条列表。** `jittered` 在 1615 关里共 12 万条僵尸条目，逐条落盘会让产物到 17 MB；而这个池不是权重表 —— 同一个 id 出现 N 次就是 N 只，所以压成 `{objects, total, waves{波号: 对象数}, waveUnresolved, pool{zombieId: {count, rows}}}` 与原表信息等价，引擎按 `count` 抽即可（`rows` 是该 id 出现过的行号，原版多数条目不带行号，所以缺行号时没有这个键）。其余机制（conveyor / initialPlants / initialGridItems / protect / events / mutators / boardGrid 与剩下九类生成器）**一个字都没裁**。

**八机制全为 null 的关卡：80 / 1809**（样例：`beach_68`、`beach_69`、`beach_70`、`beach_95`、`carnival_37`、`carnival_43`、`carnival_63`、`carnival_91`、`cowboy_2`、`cowboy_32`、`cowboy_33`、`cowboy_36`）。
这些关卡的玩法不在本节导出的 8 类里（选关/演示/纯 seed-bank 关），不是映射失败 —— 它们的包文件确实只有 `LevelDefinition` + `SeedBankProperties` + `WaveManagerModuleProperties`。

合计 `unknownMechanics` = 10 条（见第六节）。

## 三、波次归属

`WaveManagerProperties.Waves` 是 `list[list[RTID(alias@CurrentLevel)]]`，`Waves[i]` 就是第 `i+1` 波的 action 列表，所以 alias -> 波号是直接映射。alias 不符合 `Wave<N>` 形态再退回正则取第一个数字。

- 解析成功 26914 个对象，失败 195 个（`wave: null`，进 `unknowns`）。
- 失败集中在 `DinoWaveActionProps`（alias 如 `sweep1`）与 `SpawnGravestonesWaveActionProps`（alias 如 `GraveSpawnEventX`）：这些 action 由模块自己的脚本触发，不在 `Waves` 里。

## 四、哨兵值与数值字符串

哨兵命中 **264** 处（`-1` 264 处、`2147483647` 0 处），原样保留，未替换成缺失。按对象类与字段排序前 15：

| 对象类 | 字段 | 值 | 次数 |
|---|---|---|---|
| `ConveyorSeedBankProperties` | `Level` | -1 | 31 |
| `FrostWindWaveActionProps` | `Winds.Row` | -1 | 15 |
| `InitialGridItemProperties` | `GridX` | -1 | 21 |
| `InitialGridItemProperties` | `GridY` | -1 | 18 |
| `InitialPlantProperties` | `GridX` | -1 | 1 |
| `InitialPlantProperties` | `GridY` | -1 | 1 |
| `InitialPlantProperties` | `Level` | -1 | 134 |
| `ProtectThePlantChallengeProperties` | `Level` | -1 | 33 |
| `SpawnGravestonesWaveActionProps` | `SpawnPositionsPool.mX` | -1 | 10 |

数值被写成字符串的字段 **56436** 处，编译时 coerce 成数字。前 15：

| 对象类 | 字段 | 类型 | 次数 |
|---|---|---|---|
| `SpawnZombiesJitteredWaveActionProps` | `Zombies.Row` | numstr | 52440 |
| `SpawnZombiesFromGroundSpawnerProps` | `Zombies.Row` | numstr | 678 |
| `SpawnZombiesFromGridItemSpawnerProps` | `ZombieSpawnWaitTime` | numstr | 518 |
| `DinoWaveActionProps` | `DinoWaveDuration` | numstr | 263 |
| `SpawnZombiesFishWaveActionProps` | `Zombies.Row` | numstr | 263 |
| `SpawnModernPortalsWaveActionProps` | `PortalRow` | numstr | 261 |
| `FrostWindWaveActionProps` | `Winds.Row` | numstr | 237 |
| `SpawnModernPortalsWaveActionProps` | `PortalColumn` | numstr | 151 |
| `InitialPlantProperties` | `Level` | numstr | 125 |
| `SpiderRainZombieSpawnerProps` | `TimeBetweenGroups` | numstr | 118 |
| `StormZombieSpawnerProps` | `TimeBetweenGroups` | numstr | 115 |
| `SpawnZombiesFromGridItemSpawnerProps` | `Zombies.Row` | numstr | 100 |
| `BeachStageEventZombieSpawnerProps` | `GroupSize` | numstr | 99 |
| `SpawnZombiesFromGridItemSpawnerProps` | `SuppressActionIfNoGridItemsFound` | boolint | 82 |
| `SpiderRainZombieSpawnerProps` | `ColumnEnd` | numstr | 81 |

**哨兵是 coerce 之后再判的**：原版把 `-1` 有时写成整数、有时写成字符串 `"-1"`（如 `InitialPlantProperties.InitialPlantPlacements[].Level`），两者都会计入上表同一个 `value: -1`。表里的数一律原样保留，没有替换成 `null`。

**引用值原样保留为 RTID 字符串**（如 `"RTID(atlantis@ZombieTypes)"`）：编译时不剥表名，避免丢信息；需要短名时用仓库现有的 `tools/contentc/rtid.py`。植物类字段（`plant`）在原版里本来就是裸名字，所以两种形态会同时出现 —— 这是源数据的形状，不是编译错误。

## 五、引擎接线最小闭环（先做哪三个）

按「改一行数据就能让这一关看起来像原版」排序，成本从低到高：

1. **`initialGridItems`（690 关）** —— 只有坐标 + 物件名，引擎只要有「在 (x,y) 放一个 grid item」就够。墓碑（`gravestones[].forceSpawn[]`）同构，一次接线同时解锁 241 关的墓碑布局。**投入最小、覆盖面最大。**
2. **`conveyor`（350 关）** —— 槽位是 `{plant, weight, min/maxCount, 冷却}` 的加权随机表，引擎侧只需要一个「按权重抽卡、按冷却补充」的循环；改动波（132 关）在同一结构里按 `wave` 套用，不用另写。
3. **`protectThePlant`（286 关）** —— 数据侧只有「保护哪几株、共 N 株」，失败判定由引擎在受保护植物消失时触发，**不需要新渲染路径**，是纯规则接线。

`spawners` 数值最全但成本最高（8 类 + 池结构，每类都要在波次调度里落位），建议放到第三批；`boardGrid` 只有 49 关，最后做。

## 六、unknowns 与探针

- **`wave-unresolved`**（64）：DinoWaveActionProps 有 64 个对象的 alias 既不在 WaveManagerProperties.Waves 里、也不符合 Wave<N> 形态，wave 记为 null；样例 `sweep1`、`sweep3`、`sweep4`。 探针：打印该包 Waves 的完整 alias 列表，确认是否走 -1/隐藏波次
- **`wave-unresolved`**（42）：SpawnGravestonesWaveActionProps 有 42 个对象的 alias 既不在 WaveManagerProperties.Waves 里、也不符合 Wave<N> 形态，wave 记为 null；样例 `GraveSpawnEventX`、`DynamicGravestone`、`N1`。 探针：打印该包 Waves 的完整 alias 列表，确认是否走 -1/隐藏波次
- **`wave-unresolved`**（17）：SpawnModernPortalsWaveActionProps 有 17 个对象的 alias 既不在 WaveManagerProperties.Waves 里、也不符合 Wave<N> 形态，wave 记为 null；样例 `PortalsEvent4`、`PortalsEvent3`、`PortalsEvent0`。 探针：打印该包 Waves 的完整 alias 列表，确认是否走 -1/隐藏波次
- **`wave-unresolved`**（21）：SpawnZombiesFromGridItemSpawnerProps 有 21 个对象的 alias 既不在 WaveManagerProperties.Waves 里、也不符合 Wave<N> 形态，wave 记为 null；样例 `WaveXNecromancyEvent0`、`PWWP`、`Move`。 探针：打印该包 Waves 的完整 alias 列表，确认是否走 -1/隐藏波次
- **`wave-unresolved`**（22）：SpawnZombiesFromGroundSpawnerProps 有 22 个对象的 alias 既不在 WaveManagerProperties.Waves 里、也不符合 Wave<N> 形态，wave 记为 null；样例 `Drag1`、`TapFast1`、`TapFast3`。 探针：打印该包 Waves 的完整 alias 列表，确认是否走 -1/隐藏波次
- **`wave-unresolved`**（24）：SpawnZombiesJitteredWaveActionProps 有 24 个对象的 alias 既不在 WaveManagerProperties.Waves 里、也不符合 Wave<N> 形态，wave 记为 null；样例 `DynamicZombies`、`Break`、`Rap`。 探针：打印该包 Waves 的完整 alias 列表，确认是否走 -1/隐藏波次
- **`wave-unresolved`**（1）：StormZombieSpawnerProps 有 1 个对象的 alias 既不在 WaveManagerProperties.Waves 里、也不符合 Wave<N> 形态，wave 记为 null；样例 `snowstormEvent0`。 探针：打印该包 Waves 的完整 alias 列表，确认是否走 -1/隐藏波次
- **`wave-unresolved`**（4）：TidalChangeWaveActionProps 有 4 个对象的 alias 既不在 WaveManagerProperties.Waves 里、也不符合 Wave<N> 形态，wave 记为 null；样例 `TidalChangeEvent4`、`TidalChangeEvent5`、`TidalChangeEvent6`。 探针：打印该包 Waves 的完整 alias 列表，确认是否走 -1/隐藏波次
- **`empty-objdata`**（18）：以下类的对象 objdata 为空对象，只能记录存在性。 探针：对照同关其它对象确认是「清空」还是解包丢失
- **`protect-failure-rule`**（286）：ProtectThePlantChallengeProperties 没有显式失败动作，原版由引擎在受保护植物消失时判负；本表只导出 mustProtectCount 与 plants，并在 payload 里用 failWhenProtectedPlantDiesSource="client-default" 标明 failWhenProtectedPlantDies 是编译端约定而不是原表字段。 探针：在引擎侧实现「受保护植物死亡即判负」，不要等数据里的失败字段

## 七、保护目标的三个口径

`protectThePlant` 里有三个容易混的数字：原表 `mustProtectCount`（阈值）、`Plants` 的**条目数**、以及按坐标去重后的**格子数**。引擎判定用第一个；用后两个推都会偏。

1. **`mustProtectCount` vs 条目数**：287 个 protect 模块里，「`must` 等于条目数」268 个、「`must` 小于条目数」19 个、「`must` 大于条目数」**0 个**。所以 `must` 是阈值而不是总数：小的那 19 个模块是「列了 N 格候选、只需守住其中 M 格」。
2. **`must` vs 不同格子数**：`must` 严格大于去重格子数的关卡 5 个 —— `carnival_23`（must 6 / 6 株 / 3 格）、`egypt_74`（must 4 / 5 株 / 3 格）、`frontyard_51`（must 6 / 6 株 / 5 格）、`lostcity_45`（must 8 / 8 株 / 2 格）、`sky_46`（must 10 / 10 株 / 5 格）。这 5 关里同一格出现多条记录，是因为原表用 `Level` 区分**同一格的层**（地面层/植物层），一格里能站着多株受保护植物；不是重复行，也不是脏数据。
3. **`Level` 是层号（推断）**：取值分布 `1`×74、`-1`×33、`0`×11、`2`×6。证据是它只出现在 124/963 条记录上、且与坐标正交（`lostcity_67` 就是 protect `Level=-1` 与 initialPlant `Level=1` 落在同格）；把它当坐标会算出重复格子。注意编译期已把数字字符串 coerce 成数字，所以原表的 `'1'` 与 `1` 在这里并成一档。

**多保护模块的合并**（1 个关卡）：`lostcity_46`：`ProtectThePlant1` + `ProtectThePlant`（2 + 7 株） → 合并 9 株 / 9 个不同格 / must 4。原版一个 package 可以挂多个 `ProtectThePlantChallengeProperties`，且它们的别名同时出现在同一个 `LevelDefinition.Modules` 里 —— 是**并发**要求，不是备选。旧实现 `package.one()` 只取第一个，`lostcity_46` 因此只剩 2 株；现在按对象顺序拼接 `plants`（每条带 `module` 标明来源）、`mustProtectCount` 各模块相加，并在 `modules` 里留下每个模块的 `objects[i]` 出处。

**`failWhenProtectedPlantDies` 是客户端约定**：原表没有这个开关（t56 已核对字段级差距），是我们「受保护植物死亡即判负」的语义选择。它必须留着，所以 payload 里额外带 `"failWhenProtectedPlantDiesSource": "client-default"` —— 以后做字段级对照时，别把这个键当成原版字段捡回去。

## 八、复现

```
python tools/contentc/mechanics.py            # 生成 json + 本报告
python tools/contentc/mechanics.py --check    # 逐字节校验产物是否最新
python tools/contentc/mechanics.py -n         # 只打印摘要
python -m unittest discover -s tools/tests -p 'test_*.py'
```

`generated` 字段是固定常量而不是运行时时钟，否则 `--check` 永远失败。
