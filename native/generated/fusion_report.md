# pack 融合配方报告

> 由 `python tools/contentc/fusions.py` 生成，不要手改；`--check` 会在产物过期时失败。

## 口径与结论（先看这段）

- 源表 `work/obb_packages/pkg_2083_PlantFusionConfig.json`：**217 个 objects，其中 199 个带 objdata**；真正装融合配方的只有 **1 个 `PlantFusionConfig`**，它的 `FusionPairs` 是 **85 条**。
  **“199 对”是把 199 个带 objdata 的 objects 当成了对数**——本树里 199 是 object 计数，配方对数实测 85。两个数字都在上表里可复现。
- 归一：94 / 170 个 ingredient 能落到 client 植物 id，其余 76 个保留 pack 原值；两位 ingredient 都是 client id 的配对 **27** 条，其余 **58** 条标 `sourceKind=pack`，一条都没丢。
- 结果列：85 / 85 条能对上 client 的 `fused_<原版名>`（客户端给融合产物加了 `fused_` 前缀）。
- 与 `content/fusions.json` 对齐：配方键（两个 ingredient 排序）**pack 48 个 / content 48 个，交集 48 个，只在 pack 0 个、只在 content 0 个**；每个键出现次数两边一致：是。
- 结果侧对得上：content 的 46 个“基础结果”（无数字后缀）与 pack 的 46 个唯一 ResultPlant **集合完全相同**；另外 39 条是数字后缀变体。
- 结论：**client 的 85 条融合配方（48 个配方键）在 pack 里全都有对应**，没有“content 自创、原版没有”的配方。content 多出来的条数来自数字后缀变体（`_2` 36 条、`_3` 1 条、`_4` 1 条、`_5` 1 条）：同一配方键在 pack 里登记两次，客户端把第二次拆成独立结果 id。

## 计数

| 指标 | 数值 |
|---|---|
| objects（源表） | 217 |
| objects 带 objdata | 199 |
| PlantFusionConfig 实例 | 1 |
| FusionPairs（对数） | 85 |
| 唯一 SourcePlant 归一值 | 44 |
| 唯一 FusionPlant 归一值 | 44 |
| 唯一 ResultPlant 归一值 | 46 |
| FusionOnlyHasResultPlant | 4 |
| 带 FusionSoundEvent | 46 |
| 配方键（pack） | 48 |
| recipes（content） | 85 |
| 配方键（content） | 48 |
| 数字后缀变体（content） | 39 |
| 基础结果（content，无后缀） | 46 |

## 归一

规则见 `tools/contentc/fusions.py` 顶部：client 植物 id 原样 → `id_mapping.csv` 的 pack_type→client_id → 保留原值标 `pack`；结果列优先 `fused_<值>`。

| 项 | client 侧 | pack 侧 | 合计 |
|---|---|---|---|
| ingredient | 94 | 76 | 170 |
| 配对 sourceKind | 27 | 58 | 85 |
| 结果列 | 85 | 0 | 85 |

## 与 content 对齐

pack 侧配方键 48 个，content 侧 48 个。

### 交集（48 个）

- `akee` + `sprout`
- `birthsunflower` + `birthsunflower`
- `bloomerang1` + `bloomerang1`
- `bonkchoy` + `buttercup`
- `bonkchoy` + `stallia`
- `cabbagepult` + `lavaguava`
- `cabbagepult` + `peashooter`
- `cabbagepult` + `shadowshroom`
- `cabbagepult` + `solartomato`
- `cabbagepult` + `sunflower`
- `chardguard` + `iceburg`
- `chardguard` + `springbean`
- `chilibean` + `stunion`
- `chomper` + `peashooter`
- `dandelion` + `iceburg`
- `draftodil` + `solarsage`
- `firepeashooter1` + `sunflower`
- `fusiongatling` + `peashooter`
- `garlic` + `wallnut`
- `hollyknight` + `peashooter`
- …（共 48 条，只列前 20）

### 只在 pack（0 个）

（无）

### 只在 content（0 个）

（无）

## 结论：哪些 client 融合配方在 pack 里根本没有

**没有**。client 的每个配方键都能在 `PlantFusionConfig.FusionPairs` 找到；`content/fusions.json` 不是自创配方，而是把这 85 条按“基础条 + 数字后缀变体”重新拆分，并补上了中文名、解锁价、plantfood 消耗等运营字段。

按 (配方键, 结果) 精确比对会有 39 条只在 content 侧：pack 对同一配方键重复登记（两条一模一样的 ResultPlant），且不同配方键会得出同名结果（例如 `fused_fusiongatling` 有 `_2`…`_5`），客户端用数字后缀保证结果 id 唯一。这不是缺配方，是变体命名。

## 前 20 条配对（按 source,fusion 排序）

| # | source | fusion | result | onlyResult | sound | kind |
|---|---|---|---|---|---|---|
| 1 | `akee` | `sprout` | `fused_draftodil1` |  |  | pack |
| 2 | `birthsunflower` | `birthsunflower` | `fused_suntower` |  |  | pack |
| 3 | `bloomerang1` | `bloomerang1` | `fused_gumnut` |  |  | pack |
| 4 | `bonkchoy` | `buttercup` | `fused_headbutterlettuce` |  | Play_Plant_Buttercup_Attack | pack |
| 5 | `bonkchoy` | `stallia` | `fused_pokra1` |  | Play_Plant_Stallia_Attack | pack |
| 6 | `buttercup` | `bonkchoy` | `fused_headbutterlettuce` |  | Play_Plant_Buttercup_Attack | pack |
| 7 | `cabbagepult` | `lavaguava` | `fused_hollybarrierleaf` |  | Play_Plant_LavaGuava_Attack_Pop | pack |
| 8 | `cabbagepult` | `peashooter` | `fused_slingpea` |  |  | client |
| 9 | `cabbagepult` | `shadowshroom` | `fused_peppermint` |  | Play_Plant_ShadowShroom_Attack | pack |
| 10 | `cabbagepult` | `solartomato` | `fused_rabbagepult` |  | Play_Plant_SolarTomato_attack | pack |
| 11 | `cabbagepult` | `sunflower` | `fused_turkeypult` |  |  | client |
| 12 | `chardguard` | `iceburg` | `fused_powervine` |  | Play_IcebergLettuce_Freeze | pack |
| 13 | `chardguard` | `springbean` | `fused_tumbleweed` |  | Play_SpringBean_Activate | pack |
| 14 | `chilibean` | `stunion` | `fused_jasmine` |  |  | pack |
| 15 | `chomper` | `peashooter` | `fused_snappea1` |  |  | client |
| 16 | `dandelion` | `iceburg` | `fused_lemonaider` |  | Play_IcebergLettuce_Freeze | pack |
| 17 | `draftodil` | `solarsage` | `fused_olivepit` |  |  | pack |
| 18 | `firepeashooter1` | `sunflower` | `fused_darktwinsunflower` |  |  | pack |
| 19 | `fusiongatling` | `peashooter` | `fused_fusiongatling` |  |  | pack |
| 20 | `garlic` | `wallnut` | `fused_sweetpotato1` |  |  | pack |
