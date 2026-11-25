# 弹道数据编译报告（pkg_2082 → projectiles_from_pack.json）

由 `tools/contentc/projectiles.py` 生成；数据源 `pkg_2082_ProjectilePropertySheet.json`，产物 `native/generated/projectiles_from_pack.json`。

```
python tools/contentc/projectiles.py            # 写 json + 本报告
python tools/contentc/projectiles.py --check    # 校验落盘文件
python tools/contentc/projectiles.py --needle   # 复现「哪些字段名在表里不存在」
```

## 0. 计数

| 项 | 值 | 说明 |
|---|---:|---|
| 编译出的弹道 | 602 | 按 alias 去重后的 id 数 |
| 原表对象 | 572 | `pkg_2082_ProjectilePropertySheet.json` 里带 objdata 的对象 |
| 原表 id | 571 | 同 id 重复的对象只算一次（`ZombossMarketBullet` 有 1 份） |
| 其它包内嵌的对象 | 47 | 关卡/植物表里重复定义的 `ProjectilePropertySheet` |
| 只存在于内嵌副本的 id | 31 | 只在关卡包里定义（`FireShroom*`、`MeteorDefault`、`ZombieDirection*` …） |
| objclass 数 | 71 | 这张表不是单一类：`ProjectilePropertySheet` 只是其中一类 |
| 扫描的其它包 | 2116（失败 0） | 坏包/非 JSON 跳过并计数，不抛异常 |

弹道类型分布：`arc` 118、`drop` 59、`static` 42、`straight` 374、`unknown` 9

## 1. 任务点名的字段：哪些真的存在

`python tools/contentc/projectiles.py --needle` 在 `pkg_2082_ProjectilePropertySheet.json` 的 572 个对象上统计：

| 字段名 | 原表命中（572 对象） | 全 2117 包命中 | 本表怎么取 |
|---|---:|---:|---|
| `TypeName` | 0 | 4137 | **表中不存在 → 输出 `null`** |
| `Speed` | 0 | 1154 | **表中不存在 → 输出 `null`** |
| `ProjectileSpeed` | 0 | 0 | **表中不存在 → 输出 `null`** |
| `Motion` | 0 | 0 | **表中不存在 → 输出 `null`** |
| `Pierce` | 0 | 0 | **表中不存在 → 输出 `null`** |
| `PierceCount` | 0 | 0 | **表中不存在 → 输出 `null`** |
| `PopAnim` | 0 | 2516 | **表中不存在 → 输出 `null`** |
| `ResourceGroups` | 0 | 2087 | **表中不存在 → 输出 `null`** |
| `SpawnOffset` | 0 | 198 | **表中不存在 → 输出 `null`** |
| `InitialPositionOffset` | 6 | 6 | 见下（`{x,y}`，且 y 是字符串如 `"-60"`） |

这 9 个字段名在本表里 0 命中：`TypeName`、`Speed`、`ProjectileSpeed`、`Motion`、`Pierce`、`PierceCount`、`PopAnim`、`ResourceGroups`、`SpawnOffset`。它们统一输出 `null` —— 用 tuning 常数去填，等于把引擎目前的猜测当成原版数据，后面就没法再区分「原版值」和「我们编的值」。

### 原版的真实拼法

| 输出键 | 原版字段 | 覆盖 |
|---|---|---:|
| `acceleration` | `InitialAcceleration` | 208/602 |
| `art` | `AttachedPAM + ImpactPAM + RenderImage + ShadowImage` | 550/602 |
| `baseDamage` | `BaseDamage` | 595/602 |
| `className` | `ClassName` | 363/602 |
| `collisionFlags` | `CollisionFlags` | 596/602 |
| `collisionRect` | `CollisionRect` | 596/602 |
| `damageFlags` | `DamageFlags` | 578/602 |
| `hitRadius` | `CollisionRect (max half-extent) / 60` | 596/602 |
| `lifetime` | `Lifetime` | 55/602 |
| `pierce` | `InitialPierceChance + PierceChanceReductionPerHit + MaxTargetHits` | 41/602 |
| `speed` | `InitialVelocity[0] / 60` | 593/602 |
| `splash` | `SplashDamage + SplashRadius` | 217/602 |
| `startOffset` | `InitialPositionOffset` | 6/602 |
| `stunDuration` | `StunDuration` | 41/602 |
| `velocity` | `InitialVelocity` | 593/602 |

`id` 用 `aliases[0]`：objdata 里**没有** `TypeName`（原表 572 个对象全部没有），alias 就是类型名。`InitialPositionOffset` 那 6 条的 `y` 是字符串（`"-60"`），代码里强制转成数字，否则会被当成缺失。

## 2. 弹道判据

把 `InitialVelocity` 的三轴 `{Min,Max}` 折成中点，`|v| <= 1.0` px/s 视为零（与 `pfamilies.classify_trajectory` 同一阈值，两张表不会对「是不是抛射」打架）：

| kind | 条件 | 条数 |
|---|---|---:|
| `straight` | `|vx| > 1` 且 `|vz| <= 1` | 374 |
| `arc` | `|vx| > 1` 且 `|vz| > 1` | 118 |
| `drop` | `|vx| <= 1` 且 `|vz| > 1` | 59 |
| `static` | `|vx| <= 1` 且 `|vz| <= 1` | 42 |
| `unknown` | 没有 `InitialVelocity` | 9 |

`arc` 行同时带 `InitialAcceleration[2] = -10`（重力），但加速度只做透传，不参与判定：它是抛射的结果，不是原因。

## 3. 覆盖与缺失

| 输出字段 | present | null |
|---|---:|---:|
| `acceleration` | 208 | 394 |
| `art` | 550 | 52 |
| `baseDamage` | 595 | 7 |
| `className` | 363 | 239 |
| `collisionFlags` | 596 | 6 |
| `collisionRect` | 596 | 6 |
| `damageFlags` | 578 | 24 |
| `hitRadius` | 596 | 6 |
| `lifetime` | 55 | 547 |
| `pierce` | 41 | 561 |
| `speed` | 593 | 9 |
| `splash` | 217 | 385 |
| `startOffset` | 6 | 596 |
| `stunDuration` | 41 | 561 |
| `velocity` | 593 | 9 |

哨兵值：`SplashRadius` 有 6 条、`BaseDamage` 有 7 条是 `2147483647`（「无限/秒杀」），都保留原值并分别标 `splash.unbounded` / `baseDamageSentinel`，统计时排除。

内嵌副本差异：`variants` 逐条列出同一 id 的所有副本，`same=false` 的带 `differingKeys`。本表以 `pkg_2082` 的副本为准（没有时才用内嵌副本）。

## 4. 抽样 20 条（每种弹道各取一条 + 伤害最高的非哨兵行 + 三株基准植物）

| id | trajectory | v(px/s) | cols/s | BaseDamage | Splash(dmg/radius) | hitRadius(cols) | 来源 pkg |
|---|---|---:|---:|---:|---|---:|---|
| `PeaDefault` | straight | 333 | 5.55 | 20 | — | 0.25 | `pkg_2082_ProjectilePropertySheet` |
| `CabbageDefault` | arc | 300 | 5 | 40 | — | 0.25 | `pkg_2082_ProjectilePropertySheet` |
| `TaraxacumDefault` | drop | 0 | 0 | 0 | 60/2.0736 | 0.25 | `pkg_2082_ProjectilePropertySheet` |
| `AcidLemonPFProjectile` | static | 0 | 0 | 0 | 200/0.75 | 0.25 | `pkg_2082_ProjectilePropertySheet` |
| `HeianSushiDefault` | unknown | null | null | 99999 | — | 0.1667 | `pkg_2082_ProjectilePropertySheet` |
| `BoulderFallingForward` | drop | 0 | 0 | 99999 | — | 1 | `pkg_2082_ProjectilePropertySheet` |
| `BoulderOne` | drop | 0 | 0 | 99999 | — | 0.25 | `pkg_2082_ProjectilePropertySheet` |
| `BoulderTwo` | arc | -100 | -1.6667 | 99999 | — | 0.25 | `pkg_2082_ProjectilePropertySheet` |
| `TornadoDefault` | straight | -333 | -5.55 | 99999 | — | 0.3333 | `pkg_2082_ProjectilePropertySheet` |
| `RenaiStageTransform` | straight | 250 | 4.1667 | 21300 | — | 0.1667 | `pkg_2082_ProjectilePropertySheet` |
| `RoseStormProjectile` | straight | 210 | 3.5 | 15000 | — | 0.25 | `pkg_2082_ProjectilePropertySheet` |
| `SandbagDefault` | straight | -200 | -3.3333 | 10000 | — | 0.25 | `pkg_1003_LevelDefinition` |
| `MolotovDefault` | straight | 333 | 5.55 | 9999 | 50/0 | 0.25 | `pkg_2082_ProjectilePropertySheet` |
| `VanillaPlantfood` | straight | 210 | 3.5 | 5000 | — | 0.5625 | `pkg_2082_ProjectilePropertySheet` |
| `AirMissileDefault` | straight | -333 | -5.55 | 4000 | — | 0.25 | `pkg_2082_ProjectilePropertySheet` |
| `BladeHitDefault` | static | 0 | 0 | 3000 | — | 0.05 | `pkg_2082_ProjectilePropertySheet` |
| `JackfruitDefaultProjectile` | straight | 180 | 3 | 3000 | — | 0.1833 | `pkg_2082_ProjectilePropertySheet` |
| `ZombossSkyCityStormDefault` | straight | -100 | -1.6667 | 3000 | — | 0.25 | `pkg_2082_ProjectilePropertySheet` |
| `GiantPlasmaBall` | straight | 210 | 3.5 | 2500 | — | 0.5625 | `pkg_2082_ProjectilePropertySheet` |
| `BeanChemistPlantfoodProjectile` | arc | 300 | 5 | 2400 | — | 0.25 | `pkg_2082_ProjectilePropertySheet` |

## 5. 与 `native/src/engine/tuning.hpp` 的对照

两个常数是引擎当前硬编码值，**没有**用作任何字段的填充来源，只用来做校准对照。

### `kShotSpeedColsPerSec = 5.2`

5.2 cols/s = 312 px/s。

| 统计量 | 值 |
|---|---:|
| 直线弹（`trajectory=straight`）样本 | 374 |
| 中位数 | 333 px/s |
| 众数 | 333 px/s（5.550 cols/s） |
| 区间 | -2500 – 10000 px/s |

最常见速度：`333` px/s × 142、`650` px/s × 30、`300` px/s × 13、`450` px/s × 11、`-333` px/s × 9、`400` px/s × 8

读法：原版直线弹的主峰是 333 px/s（5.550 cols/s），5.2 cols/s 对应 312 px/s —— 312 不在任何主峰上（最近的两个峰是 333 与 300），所以 5.2 是个折中值，不是任何一株植物的原值。要么按植物逐个取 `speed.colsPerSec`，要么把常数对齐到主峰 333 px/s（5.550 cols/s）。

### `kShotHitRadius = 0.25`

| 统计量 | 值 |
|---|---:|
| 有 `CollisionRect` 的弹道 | 596 |
| 中位数 | 0.25 cols |
| 众数 | 0.25 cols |

命中半径取 `max(mWidth, mHeight) / 2 / 60`；分布：`0.25` × 358、`0.167` × 44、`0.333` × 39、`0.212` × 17、`0.5` × 16、`0.183` × 16

读法：主峰 0.25 cols 与 `kShotHitRadius = 0.25` **完全吻合**（`CollisionRect` 30×30 → 半宽 15 px → 15/60 = 0.25）。换句话说 0.25 这个常数其实就是豌豆盒子的半宽，对小弹成立；`mWidth=40` 的大弹应是 0.333，偏胖的爆炸型（0.5）也各按自己的盒子走。

### 未纳入 tuning 的两项

- `kShotStartOffsetCols = 0.35`：本表几乎没有生成点偏移（`InitialPositionOffset` 只有 6/602 条），真正的每株生成偏移在 `content.pack` 的 `Actions[].spawnOffset` 里，按 `spawnOffset.x / 60` 换算 —— 与本表的 `startOffset` 不是同一个概念。
- `kSplashNeighbourFactor = 0.5`：`SplashDamage` 有 217 条，但「邻居衰减」这个机制在 pkg_2082 里没有对应字段，只能继续 authored。

## 6. unknown（诚实边界）

1. `SplashRadius` 的**单位**：本表按格（cells）解读，证据是中位数 2.035、众数 2.0736，且哨兵值是 `2147483647`；但原版没有一处显式写单位，若要绝对确认需要用原版录像反推一次半径。
2. 内嵌副本与 `pkg_2082` 不一致时（`variants` 里 `same=false`），哪一个才是运行时生效的那份，本表没有判断依据：以 canonical 为准，差异保留在 `variants`。
3. `PrimalPeashooterProjectileProps` 等 70 个 objclass 与 `ProjectilePropertySheet` 的语义差别（是否继承、是否有额外原版行为）只看数据无法确定；本表按「同一套字段」处理。
4. `InitialPierceChance = 155`（`HysilensProjectileDefault` 等）看着像百分比而非概率，原值保留，未做归一化。

## 7. 本报告每个数字怎么复现

```
# §0/§2/§3 的计数与分布：编译时打印一行，或从产物 count/trajectoryCounts/coverage 段读
python tools/contentc/projectiles.py --check

# §1 的「原表命中」列（在 pkg_2082 上统计）
python tools/contentc/projectiles.py --needle

# §1 的「全 2117 包命中」列
python tools/contentc/projectiles.py --needle --all-packages

# §3/§5 的统计量：产物 json 的 coverage / tuning 段
python -c "import json;d=json.load(open('native/generated/projectiles_from_pack.json',encoding='utf-8'));print(d['tuning']);print(d['coverage'])

# §4 的抽样行与 §0 的 id 计数：直接读 projectiles[]
```

`projectiles_from_pack.json` 的 `counts.objclassCounts` 保存了 71 个 objclass 的逐条计数，报告里没有逐个列出，避免 71 行表格盖住结论。

