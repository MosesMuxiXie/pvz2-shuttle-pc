# 460.9 植物等级 / 升级数据判定（P1-12 / t78）

> **门禁提醒**：本文产物 `native/generated/plant_levels.json` 目前**还没挂进** `tools/check_all.ps1`；
> 已经挂进去的有 `vasebreaker.py`（≈21.9 s）、`minigames.py`（≈36.5 s）、loot binding（≈7.3 s）。
> 只要改了 `content/**`，那几个编译器的 `--check` 就会因为产物过期而变红——那不是偶发，
> 是门禁在提醒重跑。本文件的产物同样遵守「改数据 → 重跑 → `--check` 绿」的规矩。

- 任务：t78（P1-12）植物等级 / 升级数据判定。
- 产物：`tools/contentc/plant_levels.py`、`native/generated/plant_levels.json`、
  `tools/tests/test_plant_levels.py`、本文。
- 数据源：`work/obb_packages`（460.9，2116 个包 + `_index.json`）。
- 产物指纹：`821708` 字节，`sha256 ebbeb6fe45da67f66bab4f02049be299f2a8c1b0272b7ac871d1c7c164030a18`，
  无 CRLF、单 LF 结尾，两次生成逐字节相同。

## §0 结论（先回答问题）

**原版确实有「植物等级」这套数据**，而且是一张干净的逐级数值表：

| 问题 | 答案 | 证据 |
| --- | --- | --- |
| 原版有没有植物等级机制？ | **有**。325 行 / 323 个不同植物，逐级绝对值 | `pkg_2069_PlantLevelStats.json`，objclass `PlantLevelStats` |
| 是不是「每级同一套系数」？ | **不是**。每级是独立数值（`FloatStats[].Values[]`，`Values[0]` = 1 级） | 见 §2、§4 的 blockoli 逐级表 |
| 有没有通用「升级」表？ | **没有**。`PlantUpgrade*` 三类命中全 0 | §5.1 的搜索表（产物 `searches` 字段） |
| 升级以什么形式存在？ | 零散单株字段（9 个字段 / 3 株）+ 一张货币换算表 | `pkg_2073` 的 `*Upgrade*` 键、`pkg_2070_PlantLevelupOfferProps.json` |
| 覆盖多少植物？ | 323 株有等级行，其中 **133 株 `levelCount > 1`**（真的会逐级变强） | `counts.plants` / `counts.plantsWithLeveling` |
| 有没有编数值？ | **没有**。缺数据的地方是 `null` 并记进 `raggedStats`，查不到的东西进 `unknowns` | §6 |

一句话：**等级可以照表实现；「升级系统」不能照表实现，只能按单株特例 + 换算表拼。**

## §1 口径（R01–R10，逐条都能在代码与 `--check` 里对照）

- **R01 唯一权威表**：`pkg_2069_PlantLevelStats.json`（objclass `PlantLevelStats`）。
  `pkg_2072_unknown.json` 里也有 377 行同名 objclass，但**没有** `LevelCap` / `LevelXP` /
  `LevelCoins` / `PlantTier`，且个别数值与正表冲突 → 只作旁证，绝不并入（R05）。
- **R02 同名多行**：一个 `TypeName` 在正表里可能出现 2 次（实测 `aloe`、`cactus`）→
  取「有值字段最多 > 层数最大 > 包内下标最小」那行，其余进 `alternateRows`，不静默丢。
- **R03 层数判定**分两档：
  1. `LevelCap > 1` → 直接用它（35 株，例 blockoli 10 / sunflower 3）；
  2. 否则取 {最长 `Values` 长度, **单调** `LevelXP` 长度+1, **非花费型** `PlantTier` 长度,
     非零 `LevelCoins` 长度} 的最大值；都没有 → 1。
  为什么不能无条件取 max：`wallnut` 的 `LevelXP` 有 39 项且尾部追加了 `1,1,1,1,2,2,2,2,3,3`
  （那是阶数），纯 max 会算出 40 层；`potatomine` 的 `PlantTier` 装的是升阶金币
  `1/50/200/…/55000`，纯 max 会算出 20 层。两类伪信号都记进 `levelCountIgnored` 与
  `unknowns`（113 株 / 86 株），原样保留、不修正。
- **R04 按层取数**：`stats[列名] = Values[level-1]`；`Values` 不够长就给 `null`，
  缺失条数记进 `raggedStats`（实测 40 株 / 1719 个空位）。**不补上一级、不补 0。**
- **R04b 同名条目靠 `SubType` 分列**：27 株的 `FloatStats` 里出现同名条目，它们是
  **两列不同数据**（`cutebubuseed` 的 `ActionDamage/SubType=0 → [6]`、`SubType=1 → [100]`）。
  名字唯一时列名就是 `Name`（296 株的键保持不变），出现同名时改成 `Name@SubType`，
  一列都不丢；重复本身进 `unknowns.duplicate-stat-names`。
- **R05 只出现在旁证表的植物**：`electrictea` / `tombtangler` / `vamporcini` → 进 `unknowns`，
  不建植物条目（不拿缺 `LevelCap` 的表硬凑等级）。
- **R06 `StringStats` 原样透传**（多为空 `Values`，不解释其语义）。
- **R07 派生值只算 3 项**且只在基线非 0 时算：`derived.hpMul` / `derived.actionDamageMul`
  （相对 1 级）、`derived.costDelta`（相对 1 级，可负），全部标 `derivedFromLevel: 1`，
  与原值分开放。
- **R08 升级侧不合并**：`pkg_2073` 里键名含 `upgrade` 的字段逐条原样进 `upgradeHooks`。
- **R09 产物确定性**：固定 `generated` 日期、`sort_keys`、LF、逐字节 `--check`。
- **R10 否定结论要带证据**：`searches` 字段给出 5 个关键词在 objclass / alias / 字段名
  上的命中数，让「没有通用升级表」这件事本身可复核（§5.1）。

## §2 原表字段覆盖（`pkg_2069_PlantLevelStats.json`，325 行）

| 字段 | 行数 | 含义 / 用法 |
| --- | --- | --- |
| `FloatStats` | 320 | 逐级数值列 `[{Name, SubType?, Values[]}]`，`Values[i]` = 第 i+1 级 |
| `LevelCap` | 323 | 等级上限；仅 >1 时作为层数依据（R03-a） |
| `PlantTier` | 324 | 阶数；86 株里装的是升阶金币 → 转进 `upgradeCoins` |
| `LevelXP` | 312 | 升级经验；113 株非单调（尾部混入阶数）→ 不采信 |
| `UsesLeveling` | 248 | 是否参与等级系统（原样保留，不参与层数判定） |
| `StringStats` | 149 | 字符串型统计，原样透传 |
| `LevelCoins` | 112 | 逐级金币；非零长度可作层数候选 |
| `SeedPacketCost` | 97 | 种子包价格（原样保留） |
| `AlmanacStatEntries` | 2 | 图鉴统计条（原样保留） |

- 统计名共 **451** 个（`counts.statNames`，按原始 `Name` 去重；27 株因同名被拆成
  `Name@SubType` 列）。按「多少株带这一列」排序，前几名是
  `Cost` 250、`PacketCooldown` 250、`Hitpoints` 233、`PlantTier` 200、
  `ActionDamage` 132、`StartingCooldown` 111。
  复现：`python -c "import json,collections;t=json.load(open('native/generated/plant_levels.json',encoding='utf-8'));c=collections.Counter(n.split('@')[0] for p in t['plants'].values() for n in p['statNames']);print(c.most_common(6))"`
- 复现原表行数：`python -c "import json,pathlib;d=json.loads(pathlib.Path(r'work/obb_packages/pkg_2069_PlantLevelStats.json').read_text(encoding='utf-8-sig'));print(len(d['objects']))"`
  （在 workspace 根执行；下同）。

## §3 覆盖率与计数

| 指标 | 值 | 说明 |
| --- | --- | --- |
| `plants` | **323** | 建条目的植物数（正表 distinct `TypeName`） |
| `rowsCanonical` | 325 | 正表行数（含 2 行重复） |
| `rowsAlternate` | 377 | `pkg_2072_unknown.json` 行数（只作旁证） |
| `plantsWithLeveling` | **133** | `levelCount > 1` 的植物数 |
| `byLevelCount` | 1:190, 2:36, 3:20, 4:5, 10:68, 15:1, 20:3 | 层数直方图（合计 323） |
| `raggedPlants` / `nullStatPairs` | 40 / 1719 | 有缺格的植物 / 缺格总数 |
| `duplicateStatNamePlants` | 27 | 同名 `FloatStats`（靠 `SubType` 分列） |
| `duplicateTypeNames` | `aloe` 2、`cactus` 2 | 同名多行，其余进 `alternateRows` |
| `levelCapBelowLevelCount` | 99 | `LevelCap` 小于逐级数组给出的层数 |
| `statsLevelCountBelowLevelCount` | 58 | `FloatStats` 比层数短 → 那些层 `stats` 全 `null` |
| `levelXPNonMonotonic` / `plantTierLooksLikeCoins` | 113 / 86 | 两处字段语义污染 |
| `upgradeHookFields` | 9 | `pkg_2073` 里键名含 upgrade 的字段数 |
| `levelupOffer` | true | 是否存在货币换算表 |
| `filesScanned` | 4 | 只读 4 个包（正表 / 旁证 / 换算表 / 植物属性表） |

- 复现：`python tools/contentc/plant_levels.py --check`
  → `plant_levels plants=323 leveling=133 byLevelCount={'1': 190, '2': 36, '3': 20, '4': 5, '10': 68, '15': 1, '20': 3} ragged=40/1719 unknowns=8`

## §4 逐株抽样核对（4 株，全部逐级列出）

### 4.1 `blockoli` —— 10 级，教科书式的逐级表

| 级 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Hitpoints | 6000 | 7000 | 8000 | 9000 | 10000 | 11000 | 12000 | 13000 | 14500 | 16000 |
| Cost | 150 | 125 | 125 | 125 | 100 | 100 | 100 | 100 | 100 | 75 |
| ActionDamage | 95 | 105 | 115 | 135 | 155 | 175 | 205 | 235 | 265 | 325 |
| PacketCooldown | 15 | 14 | 13 | 12 | 11 | 10 | 9 | 8 | 7 | 7 |

`LevelXP` = `[50,100,200,300,400,500,600,800,1000]`（9 个阈值 = 10 级），
`PlantTier` = `[1,1,2,2,2,2,3,3,3,3]`，`levelCountSource` = `["levelCap"]`。

### 4.2 `sunflower` —— 3 级，价格随级下降

`Cost` 50 → 40 → 30；`Hitpoints` 300 → 350 → 500；`PacketCooldown` 5 → 4.5 → 4.5；
`LevelXP` `[20,40]`；`LevelCoins` 为 `null`（原表没这个键）。

### 4.3 `peashooter` —— 派生值示例（原始值仍在 `levels` 里）

1 级 `ActionDamageNormal 30` / `ActionXVelocity 333` / `Cost 100` / `Hitpoints 300`；
3 级 `45 / 733 / 75 / 500`。
`derived` = `{"hpMul":[1.0,1.0,1.6667],"costDelta":[0,-25,-25],"derivedFromLevel":1,
"derivedFrom":{"hpMul":"Hitpoints","costDelta":"Cost"}}`。

### 4.4 `wallnut` / `potatomine` —— 两处「不能只看数组长度」的活证据

- `wallnut`：`LevelXP` 有 **39** 项且非单调（尾部是 1/1/2/2/3/3 的阶数），
  真实层数是 **3**（`Hitpoints 4000/4500/5000`），`levelCountSource` = `["floatStats","plantTier"]`，
  `levelCountIgnored` = `["levelXP:non-monotonic"]`。
- `potatomine`：`PlantTier` 是 20 个升阶金币（`1,50,200,…,55000`），层数是 **1**
  （`levelCountSource = ["default-1"]`，`stats` 为空对象），金币表原样放进 `upgradeCoins`。

## §5 升级侧：原版到底有什么

### 5.1 「没有通用升级表」的证据（产物 `searches` 字段，2116 个包全扫）

| 关键词 | objclass 命中 | alias 命中 | 字段名命中 |
| --- | --- | --- | --- |
| `PlantLevel` | **703** | 3 | 336 |
| `PlantUpgrade` | **0** | **0** | **0** |
| `LevelUp` | 1 | 4 | 0 |
| `SeedPackLevel` | **0** | **0** | **0** |
| `Upgrade` | 10 | 37 | 225 |

- `PlantUpgrade` 与 `SeedPackLevel` 三类全 0 → **不存在**按类组织的升级表。
- `Upgrade` 的 225 个字段名命中分散在 `pkg_2073` 的单株字段与少量模块里，不是一张表。
- 复现：`python tools/contentc/plant_levels.py --check` 会校验这两点
  （`PlantUpgrade` 必须全 0、`PlantLevel` 必须 >0），改动方向反了会直接变红。

### 5.2 实际存在的升级数据（全部原样收录，不解释）

`upgradeHooks`（9 条 / 3 株，来自 `pkg_2073_PlantPropertySheet.json`）：

| 植物 | 字段 | 值 |
| --- | --- | --- |
| `IceweedDefault` | `HitPointsUpgraded` | 900 |
| `PeapodDefault` | `CanPlantAgainToUpgrade` | true |
| `UltomatoDefault` | `CanPlantAgainToUpgrade` | true |
| `UltomatoDefault` | `ResetLaunchTimeOnUpgrade` | 0.5 |
| `UltomatoDefault` | `BeamDPSUpgrade1/2/3` | 350 / 750 / 1600 |
| `UltomatoDefault` | `HitpointsUpgrade2/3` | 400 / 500 |

### 5.3 升级的货币换算（`pkg_2070_PlantLevelupOfferProps.json`，唯一的 1 行）

`MaxCoins 100000`、`MaxGems 500`、`MaxMints 500`；`ConversionInfo` 6 档：

| Rarity | Coins | Gems |
| --- | --- | --- |
| common | 200 | 1.0 |
| uncommon | 200 | 1.3 |
| rare | 300 | 1.7 |
| epic | 400 | 2.0 |
| mythical | 500 | 2.5 |
| legendary | 600 | 3.0 |

## §6 `unknowns`（8 类，全部显式记录，带 `probe` 命令）

| kind | count | 含义 |
| --- | --- | --- |
| `alternate-only-plant` | 3 | 只在旁证表出现：`electrictea` / `tombtangler` / `vamporcini` |
| `duplicate-canonical-typename` | 2 | 正表同名多行：`aloe` / `cactus`，其余进 `alternateRows` |
| `duplicate-stat-names` | 27 | 同名 `FloatStats`（`ActionDamage` 23 / `ActionDamageNormal` 4 / `ActionDamagePF` 4 / `ActionSplashDamage` 1），已按 `SubType` 分列 |
| `ragged-float-stats` | 40 | 1719 个空位，缺失层写 `null` |
| `level-cap-below-level-count` | 99 | `LevelCap` 小于逐级数组层数（例 `sapfling1`：cap 1 但有 10 层数值） |
| `levels-without-stats` | 58 | 层数来自 `LevelXP`/`PlantTier`，`FloatStats` 更短 → 那些层 `stats` 全 `null` |
| `level-xp-not-monotonic` | 113 | `LevelXP` 非单调（尾部混入阶数） |
| `plant-tier-looks-like-coins` | 86 | `PlantTier` 里出现 ≥1000 的值（是花费不是阶数） |

## §7 若要在复刻里做「升级」，还缺什么数据

1. **每级的价格/材料**：原表只有 `LevelXP`（且 113 株被污染）与部分 `LevelCoins`；
   没有「升级要花什么」的完整字段。`pkg_2070` 只给 Rarity → 货币的换算，缺
   「哪一株属于哪个 Rarity」的映射（`content/plants.json` 也没有 rarity 字段）。
2. **升级的触发点**：`UsesLeveling` 是布尔开关，但没有「在哪个界面、什么条件」的功能数据。
3. **升级后的美术/动画**：`pkg_2073` 的升级字段是数值（`BeamDPSUpgrade1..3`），
   没有对应的 `PopAnim` / 骨骼变体映射。
4. **通用升级表不存在**（§5.1），所以要实现成「逐株特例」而不是「一套公式」。
5. **客户端侧完全为空**：`content/plants.json`（147 条）**没有任何 level / upgrade 字段**
   （键只有 `id/name_zh/name_en/cost/cooldown/hp/family/art/behavior/…`）；
   323 株里 314 株能在 pack 的植物 id 里对上，剩下 9 株是命名变体
   （`blazeleaf`/`buduhoom`/`cornfetti`/`dragonbrute`/`flattenedshroom`/`frostbonnet`/
   `hammeruit`/`sweetheartsnare`/`znakelily`）。

## §8 复现命令（每个数字都有出处）

```powershell
cd D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc

# 1) 全量重编译 + 逐字节自检（幂等）
python tools/contentc/plant_levels.py
python tools/contentc/plant_levels.py --check

# 2) 单测（23 例）
python -m unittest tools.tests.test_plant_levels -v

# 3) 抽一株看逐级 + 层数来源
python tools/contentc/plant_levels.py --needle blockoli
python tools/contentc/plant_levels.py --needle wallnut
python tools/contentc/plant_levels.py --needle potatomine

# 4) 关键词命中（"没有通用升级表"的复核入口；同一个表也在产物 searches 字段里）
python -c "import json;t=json.load(open('native/generated/plant_levels.json',encoding='utf-8'));[print(s['term'],s['classes'],s['aliases'],s['keys']) for s in t['searches']]"

# 5) 原表字段覆盖（§2 的表）
python -c "import json,collections,pathlib;d=json.loads(pathlib.Path('work/obb_packages/pkg_2069_PlantLevelStats.json').read_text(encoding='utf-8-sig'));c=collections.Counter(k for o in d['objects'] for k in (o.get('objdata') or {}));print(len(d['objects']));print({k:c[k] for k in ('FloatStats','LevelCap','LevelXP','PlantTier','UsesLeveling','StringStats','LevelCoins','SeedPacketCost')})"
```

（第 5 条里的相对路径按仓库根算：`work` 在仓库的上一级，实际执行时用
`pathlib.Path('../../work/obb_packages/pkg_2069_PlantLevelStats.json')` 或直接用绝对路径。）

## §9 诚实边界

1. **层数判定是启发式**：`LevelCap > 1` 时信 cap，其余靠数组长度 + 单调性 + 「像不像花费」。
   99 株 `LevelCap` 与数组层数不一致，本产物以数组为准并保留 cap 原值——这是选择，不是事实。
2. **`null` 不等于 0**：1719 个缺格都是「原表这一级没写」，不是「这一级数值为零」。
3. **`levelXP` 尾部污染无法还原**：113 株的 `LevelXP` 混了阶数，本产物原样保留、不裁剪。
4. **`PlantTier` 的双重语义未解**：86 株当金币用、其余当阶数用，没有字段能区分，
   只能按「是否出现 ≥1000」判，属推断。
5. **旁证表没有被并入**：`pkg_2072_unknown.json` 的 377 行只在 `alternate` 里做参考，
   与正表冲突的数值（如 `aquaweed` hp 500 vs 300）以正表为准。
6. **`upgradeHooks` 只有 9 个字段**：全库 `Upgrade` 字段名命中 225 次，本产物只收
   `pkg_2073`（植物属性表）里键名含 upgrade 的、且属于植物的那 9 条；其余命中分布在
   模块/道具表里，与「植物升级」无关。
7. **没有跨表验证**：`content/plants.json` 没有等级字段，所以不存在「客户端 vs 原表」的对照，
   本表只可能与 `pkg_2069` 自身对照。

## §10 产物结构

```text
{
  format: "pvz2-shuttle/plant-levels@1",
  generated: "2026-11-25",
  sources: {canonical, alternate, levelupOffer, upgradeHooks},
  mechanism: {hasPlantLevels, hasGenericUpgradeTable, shape, levelCountRule},
  counts: {...},                # §3 的全部数字
  searches: [{term, classes, aliases, keys, examples}],   # §5.1
  levelupOffer: {package, objclass, aliases, data},        # §5.3
  upgradeHooks: [{key, plant, value}],                     # §5.2
  plants: {<TypeName>: {
     levels: [{level, stats{}}], levelCount, statsLevelCount,
     levelCountSource, levelCountIgnored, levelCountParts,
     levelCap, levelCapBelowLevelCount, usesLeveling,
     levelXP, levelXPMonotonic, levelCoins,
     plantTier, plantTierLooksLikeCoins, upgradeCoins,
     seedPacketCost, stringStats, statNames, duplicateStatNames,
     raggedStats, derived, source, aliases, alternate?, alternateRows?
  }},
  unknowns: [{kind, count, detail, probe, ...}]
}
```
