# 养料数据编译报告

> 一句话结论：这 6 株可以用 pack 数据驱动到弹道层；147 株有时长、185 株有次数；其余 333 株的养料效果与全部文案都只能 authored。

## 一句话结论

1. 6 株（sungun / homingthistle / dartichoke / draftodil1 / magnetfruit / rheumnobile）在 pack 里有完整的 `Type==plantfood` 动作，`Projectile` / `SpawnOffset` / 冷却三件套可以原值驱动到弹道层；其中 draftodil1 缺三个冷却字段，只保留弹体与偏移。
2. 147 株在属性表里有非零 `PlantFoodDurationSeconds`，185 株有非零 `PlantFoodPlayCount`，这两类数字可以直接进引擎做动画时长与播放次数。
3. 其余 333 株没有任何养料动作记录，效果必须 authored；全部植物的养料文案（名称/说明）pack 里也没有。

## 计数

| 指标 | 值 | 口径 |
| --- | --- | --- |
| 输出行数 | 293 | 只要有任一时长/次数/动作的植物 |
| `withDuration` | 147 | 属性表非零 `PlantFoodDurationSeconds`（记录 155 条） |
| `withPlayCount` | 185 | 属性表非零 `PlantFoodPlayCount`（记录 189 条） |
| `withAction` | 6 | `Actions` 里 `Type==plantfood` 的条数 |
| `animated` | 147 | 输出行里时长非空的行数 |
| `plantsWithDuration` | 147 | 能反查到植物的非空时长 |
| `plantsWithPlayCount` | 172 | 能反查到植物的非空次数 |
| 属性表对象 | 398 | `pkg_2073` 全表 |
| 被植物引用 | 335 | 339 株去重后 |
| 无人引用 | 63 | 含 `PlantPropertySheetTemplate` |
| 次数可达属性表 | 170 | 被植物引用且写了次数 |
| 次数不可达属性表 | 19 | 写了次数但没有植物指向 |
| 被多株共用的次数表 | 2 | BonkchoyDefault / CitronDefault 各 2 株 |
| 缺效果植物 | 333 | 必须 authored 的株数 |

`withPlayCount=185` 是属性表记录口径（189 条记录、19 条所在表无人引用、非零 185 条），`plantsWithPlayCount=172` 是植物口径：可达的 170 张表服务 172 株，其中 2 张被两株共用（BonkchoyDefault / CitronDefault）。两个数不能直接相减，差额不是缺失。

## 6 株逐字段表

| id | packType | framework | 时长(s) | 次数 | kind | projectile | spawnOffset | cooldownMin | cooldownMax | initialMin | launchSound |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `dartichoke` | `dartichoke` | `PlantDartichoke` | 3 | — | projectile | `DartichokeLeafPerfect` | (35, -32) | 1.7 | 2 | 0 | — |
| `draftodil1` | `draftodil1` | `PlantDraftodil` | — | 1 | projectile | `DraftodilPlantfoodDefault` | (10, -25) | — | — | — | — |
| `homingthistle` | `homingthistle` | `PlantHomingThistle` | 2 | — | projectile | `HomingThistlePlantfood` | (35, -32) | 1.7 | 2 | 0 | — |
| `magnetfruit` | `magnetfruit` | `PlantMagnetFruit` | 2 | — | projectile | `MagnetFruitGiantShot` | (35, -32) | 1.7 | 2 | 0 | — |
| `rheumnobile` | `rheumnobile` | `PlantDartichoke` | 3 | — | projectile | `TurrheumImmobileProjectilePlantfood` | (0, 0) | 1.7 | 2 | 0 | — |
| `sungun` | `sungun` | `PlantHomingThistle` | 0.2 | — | projectile | `CattailPlantfood` | (35, -32) | 1.7 | 2 | 0 | — |

`DraftodilDefault` 只有 `Projectile` 与 `SpawnOffset`，缺 `CooldownTimeMin` / `CooldownTimeMax` / `InitialMinCooldownTime`，解析不设默认值，三个字段写 null 而非丢行；5 株的 `ProjectileLaunchSound` 在原表里是空串，归一为 null（不是缺字段）。

## 覆盖率

- 时长：147 / 339 = 43.4%
- 次数：185 / 339 = 54.6%
- 动作：6 / 339 = 1.8%
- 输出行：293 / 339 = 86.4%（有时长/次数/动作之一）

剩下的部分在 pack 里就是空的：没有独立的养料效果表，`Actions` 也不是每株都有；6 条动作之外的 333 株应当读作「数据不在表里」而不是「没有养料」——它们在游戏里当然有养料效果，只是原版把效果写在代码或别的表里。

## 必须 authored 的部分

按行为族（`plant_families.json`）分组统计缺效果的 333 株：

| 分组 | 株数 |
| --- | --- |
| 直射 | 122 |
| 抛射 | 44 |
| 墙 | 25 |
| 生产 | 22 |
| 瞬时 | 54 |
| 其他 | 66 |
| 合计 | 333 |

除了效果，**全部**植物的养料文案（名称、说明、升级文案）都必须 authored；pack 里只有 `PlantFoodDurationSeconds` / `PlantFoodPlayCount` 两个数字列，没有任何可读文本。

## 口径与来源

- `obb_packages/pkg_2073_PlantPropertySheet.json`：逐株属性表，398 个对象；只取 `Actions`、`PlantFoodDurationSeconds`、`PlantFoodPlayCount` 三列。
- `obb_packages/pkg_2074_PlantType.json`：339 株植物，`Properties` 给出属性表别名，339 株全部可解析。
- `native/generated/id_mapping.csv`：plant 侧 44 条 exact 命中用于把 pack TypeName 归一成 client id；本表 293 行里 39 行归一成功，其余保留 pack id（`idKind="pack"`）。6 株带动作的植物只有 `homingthistle` 落在客户端词汇表内，其余 5 株是 pack 独有 id。
- `native/generated/plant_families.json`：行为族，用于缺效果的族分组。
- 开场养料数量在 `pkg_0236_LevelMutatorStartingPlantfoodProps`（`OverrideStartingPlantfood0..2`），属于关卡层，不在本表范围。
- `gaps` 只记效果层缺口（`["effect"]`）：时长/次数缺失已由字段 null 表达，所以 `gaps` 非空行数 == 缺效果行数，不会双重计数。

产物：`native/generated/plantfood_from_pack.json`（本报告的同源数据）。
