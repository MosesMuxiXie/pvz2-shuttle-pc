# pack 植物名册报告

> 由 `python tools/contentc/expand.py` 生成，不要手改；`--check` 会在产物过期时失败。

## 输入

| 项 | 路径 | 数量 |
|---|---|---|
| pack 植物 | `native/generated/content.pack` | 339 |
| 现有 content 植物 | `content/plants.json` | 147 |
| 行为族表 | `native/generated/plant_families.json` | 有 |
| 美术库 | `PvZ2SHUTTLE/assets/db` | plants/* |

## 摘要

| 指标 | 数值 |
|---|---|
| pack 植物总数 | 339 |
| 本次输出（pack-only） | 295 |
| 按同名跳过（content 已有） | 44 |
| art 命中（本次输出） | 25 / 295 |
| art 命中（含已存在，全 339） | 51 / 339 |
| cost 走同族均值 | 2 |
| cooldown 走同族均值 | 3 |
| water 格植物 | 1 |
| 无 Actions 植物 | 37 |
| 行为族来源 | plant_families.json |

## 分族统计（本次输出的 295 株）

| behavior 族 | 株数 | content 同族 cost 均值（缺省基准） |
|---|---|---|
| shoot | 113 | 203.21 |
| instant | 48 | 142.31 |
| lob | 38 | 247.32 |
| support | 31 | 168.0 |
| wall | 21 | 76.43 |
| produce | 19 | 106.88 |
| spike | 15 | 158.18 |
| boomerang | 3 | 116.67 |
| fume | 3 | 75.0 |
| chomp | 2 | 170.0 |
| mine | 2 | 125.0 |

合计 295 株；族判定来自 `plant_families.json`。

## art 命中率

guess 顺序：`POPANIM_PLANT_<TOKEN>` → `plants/<Camel>PLANT`；`PlantAnimRig_<Token>` → `plants/<Camel>PLANT`；最后是归一化子串唯一命中。命中不了写 `null`，不硬凑。

| 依据（按全 339 株统计） | 株数 |
|---|---|
| miss | 288 |
| popanim-token | 28 |
| animrig-token | 23 |

本次输出 295 株里 25 株（8%）能挂到 assets/db 的 actor；把 44 株已存在的算上，339 株里 51 株（15%）有现成模型。其余只能先出静态图或色块——这是美术缺口，不是字段缺失。

## cost / cooldown 缺省

pack 里 `cost` 缺失时用 content 同 behavior 族的均值（四舍五入到整数），`packetCooldown` 缺失时同族均值（保留两位）；同族没有样本时退回全局均值。

| 字段 | 走缺省的植物 |
|---|---|
| cost | `blastspinnercocoon`、`imitater` |
| cooldown | `blastspinnercocoon`、`imitater`、`noctarinecloud` |

## 最该先补的 20 条（art 已命中 + 有 Actions）

排序：动作数降序 → 动作种类数降序 → id；这些条目既有现成骨骼，又有可接线的动作。

| # | 植物 | framework | actions | 动作种类 | art |
|---|---|---|---|---|---|
| 1 | `citron` | PlantTorchwood | 3 | explode、special | `plants/TorchwoodPLANT` |
| 2 | `darktwinsunflower` | PlantTwinSunflower | 3 | special、sun | `plants/SunflowerPLANT` |
| 3 | `hollybarrierleaf` | PlantKernelpult | 3 | projectile、special | `plants/KernelPultPLANT` |
| 4 | `kernelpult1` | PlantKernelpult | 3 | projectile、special | `plants/KernelPultPLANT` |
| 5 | `lemonaider` | PlantKernelpult | 3 | projectile、special | `plants/KernelPultPLANT` |
| 6 | `reinforcemint` | PlantSunflower | 3 | special、sun | `plants/SunflowerPLANT` |
| 7 | `unused_45` | PlantKernelpult | 3 | projectile、special | `plants/KernelPultPLANT` |
| 8 | `repeater1` | PlantRepeater | 3 | projectile | `plants/RepeaterPLANT` |
| 9 | `birthsunflower` | PlantBirthSunflower | 2 | special、sun | `plants/SunflowerPLANT` |
| 10 | `gloomvine` | PlantFumeshroom | 2 | projectile、special | `plants/FumeShroomPLANT` |
| 11 | `magnetfruit` | PlantMagnetFruit | 2 | plantfood、projectile | `plants/HomingThistlePLANT` |
| 12 | `marigold` | PlantMarigold | 2 | special、sun | `plants/SunflowerPLANT` |
| 13 | `minigame_music` | PlantMagnifyingGrass | 2 | manual、unknown | `plants/MagnifyingGrassPLANT` |
| 14 | `oxygenalgae` | PlantOxygenAlgae | 2 | special、sun | `plants/SunflowerPLANT` |
| 15 | `primalsunflower` | PlantSunflower | 2 | special、sun | `plants/SunflowerPLANT` |
| 16 | `sungun` | PlantHomingThistle | 2 | plantfood、projectile | `plants/HomingThistlePLANT` |
| 17 | `ambershroom` | PlantBonkchoy | 2 | special | `plants/BonkChoyPLANT` |
| 18 | `headbutter` | PlantBonkchoy | 2 | special | `plants/BonkChoyPLANT` |
| 19 | `hollyknight` | PlantGatlingPea | 2 | projectile | `plants/GatlingPeaPLANT` |
| 20 | `starfruit_barrage` | PlantStarFruit | 2 | projectile | `plants/StarFruitPLANT` |

## 已知简化 / 待补

- `damage` 一律 `null`：pack 的动作里没有伤害数值，只能等引擎侧按 projectile 反查，别在这里编。
- `rows` 一律 `[0]`（water 为 `[]`）：pack 没有“该植物占几格”的字段，`height` 是美术高度；三行覆盖类（如 threepeater）需要棋盘几何那侧的判定，本工具不猜。
- `name_zh` / `desc_zh` / `almanac_no` 为 `null`：pack 不带本地化文本，`name_en` 是从 framework 去掉 `Plant` 前缀得到的候选名，不是官方译名。
- `family` 用的是 behavior 族（shoot/lob/…），与 content 里 `family` 的美术家族名（如 `Peashooter`）不是一个概念；pack 的原始家族名保留在 `packFacts.families` 与 `framework` 里。

## 附录：按同名跳过的 44 条

| id | framework | 原因 |
|---|---|---|
| `begonia` | PlantBegonia | content/plants.json 已有同 id 条目，保持原样不合并 |
| `birdofparadise` | PlantParadise | content/plants.json 已有同 id 条目，保持原样不合并 |
| `bloomerang` | PlantMagicShroom | content/plants.json 已有同 id 条目，保持原样不合并 |
| `bonkchoy` | PlantBonkchoy | content/plants.json 已有同 id 条目，保持原样不合并 |
| `cabbagepult` | PlantCabbagepult | content/plants.json 已有同 id 条目，保持原样不合并 |
| `cherry_bomb` | PlantCherryBomb | content/plants.json 已有同 id 条目，保持原样不合并 |
| `chomper` | PlantChomper | content/plants.json 已有同 id 条目，保持原样不合并 |
| `elderbarrier` | PlantElderbarrier | content/plants.json 已有同 id 条目，保持原样不合并 |
| `frozenpear` | PlantPeanut | content/plants.json 已有同 id 条目，保持原样不合并 |
| `fumeshroom` | PlantFumeshroom | content/plants.json 已有同 id 条目，保持原样不合并 |
| `gardenia` | PlantSeaFlora | content/plants.json 已有同 id 条目，保持原样不合并 |
| `homingthistle` | PlantHomingThistle | content/plants.json 已有同 id 条目，保持原样不合并 |
| `iceburg` | PlantIceburg | content/plants.json 已有同 id 条目，保持原样不合并 |
| `jalapeno` | PlantJalapeno | content/plants.json 已有同 id 条目，保持原样不合并 |
| `jasmine` | PlantAppeasemint | content/plants.json 已有同 id 条目，保持原样不合并 |
| `kernelpult` | PlantKernelpult | content/plants.json 已有同 id 条目，保持原样不合并 |
| `magnifyinggrass` | PlantMagnifyingGrass | content/plants.json 已有同 id 条目，保持原样不合并 |
| `melonpult` | PlantMelonpult | content/plants.json 已有同 id 条目，保持原样不合并 |
| `missiletoast` | PlantMissileToast | content/plants.json 已有同 id 条目，保持原样不合并 |
| `paradoxpult` | PlantParadoxPult | content/plants.json 已有同 id 条目，保持原样不合并 |
| `peashooter` | PlantPeashooter | content/plants.json 已有同 id 条目，保持原样不合并 |
| `poppinpoppies` | PlantPoppinPoppies | content/plants.json 已有同 id 条目，保持原样不合并 |
| `potatochip` | PlantPotatomine | content/plants.json 已有同 id 条目，保持原样不合并 |
| `potatomine` | PlantPotatomine | content/plants.json 已有同 id 条目，保持原样不合并 |
| `repeater` | PlantPeashooter | content/plants.json 已有同 id 条目，保持原样不合并 |
| `seapotatomine` | PlantPotatomine | content/plants.json 已有同 id 条目，保持原样不合并 |
| `snowpea` | PlantSnowPea | content/plants.json 已有同 id 条目，保持原样不合并 |
| `solarflare` | PlantSunGun | content/plants.json 已有同 id 条目，保持原样不合并 |
| `spikeweed` | PlantSpikeweed | content/plants.json 已有同 id 条目，保持原样不合并 |
| `splitpea` | PlantSplitpea | content/plants.json 已有同 id 条目，保持原样不合并 |
| `squash` | PlantSquash | content/plants.json 已有同 id 条目，保持原样不合并 |
| `starfruit` | PlantStarFruit | content/plants.json 已有同 id 条目，保持原样不合并 |
| `sunflower` | PlantLittleSunflower | content/plants.json 已有同 id 条目，保持原样不合并 |
| `sunshroom` | PlantSunshroom | content/plants.json 已有同 id 条目，保持原样不合并 |
| `tallnut` | PlantTallnut | content/plants.json 已有同 id 条目，保持原样不合并 |
| `taraxacum` | PlantPeashooter | content/plants.json 已有同 id 条目，保持原样不合并 |
| `threepeater` | PlantThreepeater | content/plants.json 已有同 id 条目，保持原样不合并 |
| `torchwood` | PlantTorchwood | content/plants.json 已有同 id 条目，保持原样不合并 |
| `torpedofruit` | PlantPrimalPeashooterCanSink | content/plants.json 已有同 id 条目，保持原样不合并 |
| `tubiflora` | PlantPeashooter | content/plants.json 已有同 id 条目，保持原样不合并 |
| `voiddragon` | PlantVoidDragon | content/plants.json 已有同 id 条目，保持原样不合并 |
| `wallnut` | PlantWallnut | content/plants.json 已有同 id 条目，保持原样不合并 |
| `wintermelon` | PlantWinterMelon | content/plants.json 已有同 id 条目，保持原样不合并 |
| `yuccaguardian` | PlantYuccaGuardian | content/plants.json 已有同 id 条目，保持原样不合并 |
