# 339 个 pack 植物的行为族判定表（S4.3）

日期：2026-11-20　作者：geometer　任务：t10

引擎承认的行为族只有 `native/src/engine/registry.cpp` 的 `plantFamilies()` 那 11 个：
`shoot` / `lob` / `produce` / `wall` / `instant` / `mine` / `chomp` / `fume` / `boomerang` / `support` / `spike`。
`content/plants.json` 只覆盖 147 株植物、其中仅 44 株能与 pack 同名命中，剩下 295 株 pack-only 植物在客户端没有 `behavior` 字段。
本表把这 339 株（`native/generated/content.pack` 的 `plants`）全部判到这 11 个族上，判定规则写死在
`tools/contentc/pfamilies.py`（模块 docstring 里是同一条规则表），每株的判定依据以 `evidence` 字符串随表落盘，
产物为 `native/generated/plant_families.json`。

## 结论

| 指标 | 值 |
|---|---|
| pack 植物总数 | 339 |
| 判到合法族 | 339（无遗漏、无重复，按 id 排序） |
| 与 `content/plants.json` 可对照（labeled） | 44 |
| 一致数 | 42 |
| 一致率 | **0.9545**（阈值 0.90） |
| 不一致 | 2（`begonia`、`frozenpear`，逐条解释见下） |
| 只有 pack 证据（unlabeled） | 295 |
| 判不出（无任何维度证据） | 0；**证据最弱**的 25 株列在「仍判不出的株」一节 |
| 两次生成 | 字节一致，`sha256=5D58040ED2C2F480C6ECE508956A5784EA0E453F4881119BAEA4D236B7C962ED` |

生成/校验：

```
python tools/contentc/pfamilies.py          # 写 native/generated/plant_families.json
python tools/contentc/pfamilies.py --check   # 只校验，退出码 0
python -m unittest tools.tests.test_pfamilies -v
```

## 数据来源与用到的字段

| 来源 | 用途 |
|---|---|
| `native/generated/content.pack` → `plants[]` | 主表：`id` / `framework` / `animRig` / `properties.name` / `hitpoints` / `cost` / `sunProducer` / `height` / `actions[]`（`kind`、`projectile.name`、`damage`、`trigger`、`needEating`） |
| `work/obb_packages/pkg_2073_PlantPropertySheet.json` | 按 `properties.name` 索引（如 `PotatomineDefault`），339 株全部命中、缺失 0：`IsInstant`、`IsConsumable`、`ProjectileLobHeight`、`CanLiveOnWaves`、`NeedNumOfEatingToUse` |
| `work/obb_packages/pkg_2082_ProjectilePropertySheet.json` | 按 `projectile.name` 索引，642 条：`InitialVelocity`、`InitialAcceleration`、`BaseDamage`、`SplashDamage`、`ClassName` |

`actions[].kind` 经实测只有 7 类：`projectile` / `sun` / `explode` / `special` / `plantfood` / `manual` / `unknown`；
`content.pack` 的 `counts.plantActions` 共 668 条。

### 弹道是判 lob / shoot 的硬证据

`InitialVelocity` 的分布是清晰的三簇，据此把弹丸分成三类（`classify_trajectory()`）：

| 类别 | 判据 | 例子 |
|---|---|---|
| `straight`（平射） | `|vx|>1`、`|vz|<=1`，典型 `[333,0,0]` / `[555,0,0]` | `PeaDefault`、`SnowPea*`、`HomingThistle`、`MagicCard`、`Gardenia` |
| `arc`（抛射） | `|vx|>1` 且 `|vz|>1`，典型 `[290..310, ±10, 500..700]`，且 `InitialAcceleration=[0,0,-10]` | `CabbageDefault`、`KernelDefault`、`MelonDefault`、`WinterMelonDefault`、`ParadoxButterDefault`、`MissileToastNormalDefault`、`YuccaGuardianNormalAttackDefault` |
| `drop`（落地种子雨） | `|vz|>1` 且 `|vx|<=1`，典型 `[0,0,-500]` | `Taraxacum`、`FrozenPear`、`Jasmine` |

`ProjectileLobHeight` 只有 `kernelpult` 一株有值（350），所以它只能当**加分项**、不能当 lob 判据——
`Cabbagepult`/`Melonpult`/`WinterMelon` 身上都是空的，`arc` 弹道才是能推广的信号。

## 规则表

判定是**有序**的：从上往下第一条命中即为结果。规则编号同时写进每株的 `rule` 与 `evidence` 字段，所以表可以按规则回溯。

| 规则 | 命中数 | 判据 | 为什么这么判 |
|---|---|---|---|
| R01 `produce/sun-action` | 15 | `actions` 里有 `kind=sun` | 有产阳光动作就是产阳植物，与 `sunProducer` 标记无关 |
| R02 `produce/sun-producer` | 7 | `sunProducer=true` 且无任何攻击动作 | R01 之后仍剩下的产阳植物（无 `sun` 动作但有标记） |
| R03 `chomp/named` | 3 | 名字含 `chomp`，或 `needEating=true` | 咀嚼族在 pack 里是「吃掉目标再冷却」，`needEating` 是它的专属字段（`chomper` 的 action 甚至是 `projectile`、伤害 0） |
| R04 `fume/named` | 4 | 名字含 `fume` | 喷雾族的动作形状与平射一致，只能靠名字（`fumeshroom`/`gloomvine`/`perfumeshroom`/`ultimatefumeshroom`） |
| R05 `boomerang/named` | 4 | 名字含 `bloomerang`/`boomerang`，或弹丸 `ClassName` 命中 | `bloomerang` 的 id 里没有 `boomerang` 子串（`bloomerang`），正则必须写全 |
| R06 `mine/named` | 4 | 有攻击性爆炸（`trigger != manual`）**且**自身名字含 `potatomine`/`teleportatomine` | 名字只取 `id` + `properties.name`：`potatochip` 的 framework 也是 `PlantPotatomine`、art rig 是 `PlantAnimRig_PotatoMine`，但它不是地雷 |
| R07 `instant/flagged` | 38 | `IsInstant=true`（且不是产阳植物） | 原版自己的标记：`cherry_bomb`/`jalapeno`/`iceburg`/`squash` 都在其中 |
| R08 `instant/consumable` | 14 | `IsConsumable=true` | 覆盖漏标 `IsInstant` 的一次性植物（`potatochip`、`solarflare`） |
| R09 `instant/explosion` | 1 | 剩余的攻击性爆炸，且**没有任何 projectile 动作** | 射手弹丸落点也会生成 explode（`gardenia` 的 600 溅射），那不代表它是一次性植物 |
| R09b `instant/manual-detonation` | 1 | 植物食品爆炸（`trigger=manual`）伤害 ≥ 1000，且无 projectile 动作 | `hotdate` 的 1200 就是它的全部输出，落地即炸；`torchwood` 的 900 是增益爆炸，留在 support |
| R10 `wall/no-actions-high-hp` | 15 | 完全没有 `actions` 且 `hitpoints >= 1000` | `wallnut` 4000 / `tallnut` 8000 / `elderbarrier` 3000 / `pumpkin` 4000 / `primalwallnut` 4000 |
| R11 `wall/defensive-name` | 8 | 名字像防御件（`wallnut`/`tallnut`/`pumpkin`/`endurian`/`blockoli`/`hollybarrier`/`*guard*`） | 这些还带着攻击或光环动作（`yuccaguardian` 会抛 50 伤害的弹），但引擎里仍是墙 |
| R12 `wall/no-attack-high-hp` | 2 | `hitpoints >= 1000` 且伤害为 0 且无 projectile 动作 | `citron`（特殊动作伤害缺失）、`kiwibeast`（吸收/反击型），见「弱证据」 |
| R13 `spike/named` | 8 | 名字含 `spike`/`bonk`/`wasabi`/`celery` | `spikeweed`/`spikerock`/`bonkchoy`/`wasabiwhip`/`celerystalker`/`ambershroom`/`headbutter`/`unused_43` |
| R14 `spike/melee-special` | 9 | 无 projectile 动作、`special` 伤害 > 0、HP < 1000 | pack 把近战写成 rect `special`（`bonkchoy` 15/60、`spikeweed` 10） |
| R15 `support/seed-rain` | 8 | 主弹丸是 `drop` 且基础伤害 0 | `Taraxacum`（0 基础 + 60 溅射）是真辅助；`frozenpear` 的同一形状见「不一致」 |
| R16 `lob/arc` | 44 | 主弹丸 `arc`，或 `ProjectileLobHeight` 有值 | 抛射族硬证据；`begonia`/`missiletoast`/`wintermelon` 的 framework 里没有 PULT 字样，只有弹道能判 |
| R17 `shoot/projectile` | 128 | 还剩 projectile 动作（有/无弹丸引用都算） | `poppinpoppies`、`birdofparadise` 的 action 只写 `kind=projectile` 不带引用名，仍属平射 |
| R18 `instant/frail-oneshot` | 0 | HP ≤ 100 且有 special/explode 伤害 | 兜底守卫规则，本版数据里更早的规则已经全覆盖，故为 0 |
| R19 `support/no-attack` | 24 | 无 projectile 动作、无攻击爆炸、`special` 伤害 0 | 纯功能件（`lilypad`、`imitater`、`garlic`、`magnetshroom1`…），见「弱证据」 |
| R20 `support/buff-explosion` | 1 | 只有 `trigger=manual` 的爆炸 | `torchwood`（900 伤害的增益爆炸） |
| R21 `support/catch-all` | 1 | 以上都不命中的显式兜底 | 只剩 `beansprout`；兜底命中数被测试卡在 ≤5，规则退化会当场失败 |

### 按族计数

| 族 | 数量 | 族 | 数量 |
|---|---|---|---|
| shoot | 128 | wall | 25 |
| lob | 44 | produce | 22 |
| support | 34 | spike | 17 |
| instant | 54 | boomerang | 4 |
| mine | 4 | chomp | 3 |
| fume | 4 | **合计** | **339** |

## 44 条 labeled 逐条对照

`content/plants.json` 的 `behavior` 是人工写的监督信号。下表是 44 条全部对照（`agree` 列即是否一致）。

| # | plant | content/plants.json | pack family | rule | agree |
|---|-------|--------------------|-------------|------|-------|
| 1 | `begonia` | lob | shoot | `R17-shoot/projectile` | **no** |
| 2 | `birdofparadise` | shoot | shoot | `R17-shoot/projectile` | yes |
| 3 | `bloomerang` | boomerang | boomerang | `R05-boomerang/named` | yes |
| 4 | `bonkchoy` | spike | spike | `R13-spike/named` | yes |
| 5 | `cabbagepult` | lob | lob | `R16-lob/arc` | yes |
| 6 | `cherry_bomb` | instant | instant | `R07-instant/flagged` | yes |
| 7 | `chomper` | chomp | chomp | `R03-chomp/named` | yes |
| 8 | `elderbarrier` | wall | wall | `R10-wall/no-actions-high-hp` | yes |
| 9 | `frozenpear` | instant | support | `R15-support/seed-rain` | **no** |
| 10 | `fumeshroom` | fume | fume | `R04-fume/named` | yes |
| 11 | `gardenia` | shoot | shoot | `R17-shoot/projectile` | yes |
| 12 | `homingthistle` | shoot | shoot | `R17-shoot/projectile` | yes |
| 13 | `iceburg` | instant | instant | `R07-instant/flagged` | yes |
| 14 | `jalapeno` | instant | instant | `R07-instant/flagged` | yes |
| 15 | `jasmine` | produce | produce | `R02-produce/sun-producer` | yes |
| 16 | `kernelpult` | lob | lob | `R16-lob/arc` | yes |
| 17 | `magnifyinggrass` | shoot | shoot | `R17-shoot/projectile` | yes |
| 18 | `melonpult` | lob | lob | `R16-lob/arc` | yes |
| 19 | `missiletoast` | lob | lob | `R16-lob/arc` | yes |
| 20 | `paradoxpult` | lob | lob | `R16-lob/arc` | yes |
| 21 | `peashooter` | shoot | shoot | `R17-shoot/projectile` | yes |
| 22 | `poppinpoppies` | shoot | shoot | `R17-shoot/projectile` | yes |
| 23 | `potatochip` | instant | instant | `R08-instant/consumable` | yes |
| 24 | `potatomine` | mine | mine | `R06-mine/named` | yes |
| 25 | `repeater` | shoot | shoot | `R17-shoot/projectile` | yes |
| 26 | `seapotatomine` | mine | mine | `R06-mine/named` | yes |
| 27 | `snowpea` | shoot | shoot | `R17-shoot/projectile` | yes |
| 28 | `solarflare` | instant | instant | `R08-instant/consumable` | yes |
| 29 | `spikeweed` | spike | spike | `R13-spike/named` | yes |
| 30 | `splitpea` | shoot | shoot | `R17-shoot/projectile` | yes |
| 31 | `squash` | instant | instant | `R07-instant/flagged` | yes |
| 32 | `starfruit` | shoot | shoot | `R17-shoot/projectile` | yes |
| 33 | `sunflower` | produce | produce | `R01-produce/sun-action` | yes |
| 34 | `sunshroom` | produce | produce | `R01-produce/sun-action` | yes |
| 35 | `tallnut` | wall | wall | `R10-wall/no-actions-high-hp` | yes |
| 36 | `taraxacum` | support | support | `R15-support/seed-rain` | yes |
| 37 | `threepeater` | shoot | shoot | `R17-shoot/projectile` | yes |
| 38 | `torchwood` | support | support | `R20-support/buff-explosion` | yes |
| 39 | `torpedofruit` | shoot | shoot | `R17-shoot/projectile` | yes |
| 40 | `tubiflora` | shoot | shoot | `R17-shoot/projectile` | yes |
| 41 | `voiddragon` | shoot | shoot | `R17-shoot/projectile` | yes |
| 42 | `wallnut` | wall | wall | `R10-wall/no-actions-high-hp` | yes |
| 43 | `wintermelon` | lob | lob | `R16-lob/arc` | yes |
| 44 | `yuccaguardian` | wall | wall | `R11-wall/defensive-name` | yes |

一致率 = 42 / 44 = **0.9545**。

## 不一致清单（2 条，均为口径分歧，不是判定错误）

### 1. `begonia`：pack = `shoot`，content = `lob`

- pack 证据：3 个 projectile 动作，弹丸 `BegoniaIce` / `BegoniaFire` 的 `InitialVelocity` 是 `[555,0,0]`，
  **没有竖直分量、没有重力加速度**，`classify_trajectory()` 判 `straight`，R17 判 `shoot`；
  `properties.name = BegoniaDefault` 上也没有 `ProjectileLobHeight`。
- content 证据：`behavior: "lob"`。
- 结论：两套数据对「抛」的定义不同。客户端把 `begonia` 的半球面弹幕当投掷物（视觉上是砸过去的），
  原版表里它是一枚平射弹。表里保留 `shoot`，因为本任务的判据是原版表；若要迁就客户端表现，
  应在 `content/plants.json` 侧改标，而不是在规则里为单株开洞。

### 2. `frozenpear`：pack = `support`，content = `instant`

- pack 证据：唯一的攻击动作是 projectile `FrozenPearDefault`，`InitialVelocity = [0,0,-500]`
  （`drop`，种子雨形态），`BaseDamage = 0`、`SplashDamage = 60`；R15 的判据「落地弹 + 基础伤害 0」命中，
  所以判 `support`——与 `taraxacum` 完全同形。它身上既没有 `IsInstant` 也没有 `IsConsumable`，
  所以 R07/R08 都不会命中。
- content 证据：`behavior: "instant"`。
- 结论：`frozenpear` 是「落地即冻一片」的一次性植物，`content` 的标法符合玩法；
  pack 只是把它建成了一个 0 基础伤害的落地弹丸，缺少「用过即消失」的标记。这是原版表缺字段导致的，
  不应通过给 R15 加例外来掩盖。**如果下游需要 `frozenpear` 进 `instant`，应在 pack 侧补
  `IsConsumable`（或让 `content` 侧标记优先），本表保持 pack 口径并在此登记。**

## 仍判不出的株

### 完全判不出（0 株）

339 株全部拿到了一个族，不存在「无值」条目。原因不是数据完备，而是规则表最后有 R21 显式兜底：
任何一株走到 R21 都会带着 `rule=R21-support/catch-all` 落盘，而不是留空。目前只命中 1 株（`beansprout`），
测试 `test_catch_all_rule_stays_marginal` 把上限卡在 5，兜底一旦开始吃表就会失败。

### 证据最弱（25 株）+ 存疑（2 株）

这 25 株的判定**只建立在「没有任何攻击证据」之上**（无 projectile 动作、无攻击爆炸、special 伤害为 0），
即「从排除法得到 `support`」，不是正向证据：

```
aloes apsarlotus aquaweed beansprout cornucopia garlic haystack hocus horsebean
imitater intensivecarrot jackolantern levitater lilypad littleguy magnetshroom1
maybee minigame_music olivepit1 phatbeet1 pyrevine1 specialgarlic tombtangler
unused_49 waterrabbit
```

其中 24 株命中 R19、1 株（`beansprout`）命中 R21。
它们大多是功能性植物（`lilypad` 睡莲、`imitater` 模仿者、`garlic` 大蒜、`magnetshroom1` 磁力菇），
`support` 是引擎里唯一能容纳「不输出伤害」的族，因此这个归档可用；但它们的**具体能力**（给别的植物加成、
反弹、改道）在这 11 个族里本来就没有表达位，后续要接能力必须另起机制，不能指望 family 字段。

另有 2 株证据同样薄弱，落到了 `wall`：

| 株 | 判定 | 为什么弱 |
|---|---|---|
| `citron` | `R12-wall/no-attack-high-hp`（hp 4000） | 动作只有 rect `special`（伤害字段为空）与 `manual` 爆炸，pack 里没有可用的伤害数字；原版 `citron` 是发射系。framework 是 `PlantTorchwood`、properties 是 `PineappleDefault`，两者都不指向平射 |
| `kiwibeast` | `R12-wall/no-attack-high-hp`（hp 2000） | 两个 rect `special` 都不带伤害（吸收/反击型），没有可判的攻击形状 |

这两株与上面 25 株一起构成「弱证据集合」，合计 27 株；它们不影响 44 条 labeled 的一致率（都不在 labeled 里）。

## `unknown` kind 的 2 株

`content.pack` 的 `unknownActionKinds` 是 `{"<none>": 2}`：有 2 个 action 完全没有 `kind` 字段。命中的株：

| 株 | 归属 | 处理方式 |
|---|---|---|
| `magnifyinggrass` | `R17-shoot/projectile` → `shoot` | 忽略无法解释的那个 action，用它其它的已知动作（projectile `trigger=manual`）定族；与 `content` 标 `shoot` 一致 |
| `minigame_music` | `R21-support/catch-all` → `support` | 同上；它整体只有这 1 个无法解释的 action，因此落到兜底 `support`，并进入「证据最弱」清单 |

两株都写进产物的 `unknownKinds[]`（含 `family` 与 `handling` 说明），测试
`test_unknown_kind_plants_are_listed_and_handled` 与 `test_unknown_kinds_match_the_pack` 双重锁定：
一旦上游 pack 的 `kind` 缺失情况变化，测试会失败而不是让这两株悄悄换族。

## 已知的方法论局限

1. **295 株没有任何人工标签**，规则表只在 44 株上被监督过。R16/R17（弹道）与 R07/R08（原版标记）
   这两组硬证据覆盖了 38+14+44+128 = 224 株，占 66%；其余靠名字、HP、动作形状，属推断。
2. **名字规则**（R03/R04/R05/R06/R11/R13）依赖 id/properties 命名，原版命名不规范时（如 `bloomerang`
   里没有 `boomerang` 子串）会漏判，因此每条名字正则都有对应的测试或已登记的例外。
3. **framework 不能单独定族**：同一个 framework 会横跨多个族——
   `PlantPeashooter` 覆盖 20 株，其中 16 株 shoot（`peashooter`、`repeater`、`flowerpot`…）、
   3 株 support（`fairymushroom`、`puffball`、`taraxacum`）、1 株 lob（`tumbleweed`）；
   `PlantPotatomine` 覆盖 4 株，3 株 mine + 1 株 instant（`potatochip`）；
   `PlantTorchwood` 只有 2 株，却是 `torchwood`（support）+ `citron`（wall）。
   规则里 framework 只参与 `all_blob` 的名字匹配，从不作为唯一依据。
4. `disabled` 的 `R18` 目前 0 命中，保留为守卫：若未来 pack 里出现「HP ≤ 100 且有一次性别伤害」的株，
   它会先于 R19/R21 命中。
