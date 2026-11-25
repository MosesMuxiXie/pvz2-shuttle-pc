# 僵尸行为族缺口（T41 / S3 战斗口径）

生成：`tools/contentc/zgaps.py`（`zombie-family-gaps-v1`），三份输入只读；`content/zombies.json` 只在获批后改过 3 行（见第五节）。

## 结论摘要

- `content/zombies.json` 共 **55** 条僵尸；其中有原版 `ZombieClass` 证据的 **28** 条（`id_mapping.csv` 的 exact 20 + manual 8），无原版条目、只能标 authored 的 **27** 条（garden 10 / gang 5 / market 5 / royal 7）。
- 真正「engine 只会走通用 walk」的缺口是 **0** 条：原先的 3 条（`football`、`garden_gargantuar`、`royal_chef_gargantuar`）已在 2026-11-24 按第五节补丁写进 `content/zombies.json`，`behavior` 从 `walk` 改为 `gargantuar`，引擎改走巨人族。
- 判定族与引擎当前族的差只剩**反向差异 1 条**：`pole_vaulter`（原版 `ZombieIceAgeDodo` 判 walk，content 主动写 jump + `extra.jump_distance`，保留）；其余 54 条两侧一致。
- 6 族词表与 `native/src/engine/registry.cpp` 的 `zombieFamilies()` 一致；本版数据只用到 walk（50）与 gargantuar（5），jump / steal / summon / fly 在这 55 条里没有可采信证据 —— 不臆造。

## 一、「20 个缺族僵尸」的核实

先把口径摆明：`content/zombies.json` 的 55 条**每一条都写了 `behavior`**（改补丁前 walk 53、gargantuar 1、jump 1），能复现的「20」是 `content.pack` 里与 content id **同名命中**的 20 条（本次实测 **20** 条 = `id_mapping.csv` 的 `exact 20`），它决定「引擎能不能读到原版 `ZombieClass`」，与「有没有 behavior」无关；`docs/COMPLETENESS.md` §2.16 的那个 20（护甲桥）是同一批 id 的第三种用途。这个口径差异比「20 条没 behavior」有用，下一个人不该再按后者理解。

计划书 T41 写「55 个僵尸里有 20 个没有可用行为族」。实测该表述**不能按字面复现**：

1. `content/zombies.json` 是 55 条的 list，**每一条都写了 `behavior`**，没有空值。
2. 能复现的 20 是另一个量：`content.pack` 的 1127 条僵尸里，恰好有 **20 个** content id 同名命中（等于 `id_mapping.csv` 的 `exact 20`）。它决定「引擎能不能读到原版 `ZombieClass`」，不是「有没有 behavior」。
3. `docs/COMPLETENESS.md` 里出现的 20 还有一处是护甲桥口径（20 个 content 僵尸在 sheet `zombies[]` 里也有同名行）。三个 20 是同一批 id、三种用途，彼此都不等于「20 个缺族」。

因此本工具按「有证据就判族、无证据就标 authored」逐条处理全部 55 条，并把「引擎当前实际族」单独列出，用 `gap = 当前是 walk 且判族不是 walk` 定义缺口。

## 二、判族规则

1. **pack 证据**（`confidence=pack`）：`pkg_2115_ZombieType.json` 的 `TypeName → ZombieClass`，类族取 `native/generated/zombie_classes.json`（同一张表生成 `zombie_family_table.inc`）。判族阈值与依据沿用该表：`IsBasicZombie` → walk、PopAnim/类名含 `GARGANTUAR/ZOMBOSS/MECH` → gargantuar、Jump/Vault 动作 → jump、`_BUNGEE` 动画 → steal、Spawn/Summon 或 Chicken/Weasel/Statue → summon、`IsSpawnedFlying` → fly，其余 walk。
2. **authored**（`confidence=authored`）：`id_mapping.csv` 里没有该 client 的 pack 行，族取 `content/zombies.json` 自述；`extra.art_gargantuar=true` 这类客户端自带标记可以作为 authored 依据，但**不冒充原版证据**（报告里逐条写明）。
3. **引擎当前实际族**复刻 `native/src/engine/world.cpp:794-803`：`content.pack` 精确命中就用类族，否则用 `content.behavior`（缺省 walk）；`ContentPack::findZombie` 见 `native/src/content/loader.cpp:397-403`。
4. 判族结果与引擎当前族不一致时，本工具本身**不改 content**：先在第五节出 patch 建议；获批后改的那几条记进 `APPLIED_PATCHES`，第五节按「已应用」列改前/改后。

## 三、逐条表（55 条）

| client id | pack TypeName | ZombieClass | behavior | 当前族 | 判定族 | 置信 | 缺口 | 首条证据 |
|---|---|---|---|---|---|---|---|---|
| `basic` | tutorial | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=tutorial → ZombieClass=ZombieBasic |
| `beach` | beach | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=beach → ZombieClass=ZombieBasic |
| `buckethead` | tutorial_armor2 | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=tutorial_armor2 → ZombieClass=ZombieBasic |
| `conehead` | tutorial_armor1 | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=tutorial_armor1 → ZombieClass=ZombieBasic |
| `cowboy` | cowboy | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=cowboy → ZombieClass=ZombieBasic |
| `cowboy_armor1` | cowboy_armor1 | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=cowboy_armor1 → ZombieClass=ZombieBasic |
| `dark` | dark | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=dark → ZombieClass=ZombieBasic |
| `dark_armor1` | dark_armor1 | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=dark_armor1 → ZombieClass=ZombieBasic |
| `eighties` | eighties | ZombieEightiesBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=eighties → ZombieClass=ZombieEightiesBasic |
| `flag` | tutorial_flag | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=tutorial_flag → ZombieClass=ZombieBasic |
| `football` | football_mech | ZombieMechFootball | gargantuar | gargantuar | gargantuar | pack |  | pkg_2115_ZombieType.json: TypeName=football_mech → ZombieClass=ZombieMechFootball |
| `future` | future | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=future → ZombieClass=ZombieBasic |
| `future_armor1` | future_armor1 | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=future_armor1 → ZombieClass=ZombieBasic |
| `gang_bucket` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=gang_bucket 无 pack 行（match_kind=none） |
| `gang_carl` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=gang_carl 无 pack 行（match_kind=none） |
| `gang_cone` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=gang_cone 无 pack 行（match_kind=none） |
| `gang_flag` | gang_flag | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=gang_flag → ZombieClass=ZombieBasic |
| `gang_gargantuar` | gang_gargantuar | ZombieGangGargantuar | walk | gargantuar | gargantuar | pack |  | pkg_2115_ZombieType.json: TypeName=gang_gargantuar → ZombieClass=ZombieGangGargantuar |
| `gang_imp` | gang_imp | ZombieImp | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=gang_imp → ZombieClass=ZombieImp |
| `gang_molotov` | gang_molotov | ZombieGangMolotov | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=gang_molotov → ZombieClass=ZombieGangMolotov |
| `gang_ozloc` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=gang_ozloc 无 pack 行（match_kind=none） |
| `gang_zombie` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=gang_zombie 无 pack 行（match_kind=none） |
| `garden_bucket` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=garden_bucket 无 pack 行（match_kind=none） |
| `garden_cone` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=garden_cone 无 pack 行（match_kind=none） |
| `garden_cuju` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=garden_cuju 无 pack 行（match_kind=none） |
| `garden_drummer` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=garden_drummer 无 pack 行（match_kind=none） |
| `garden_flag` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=garden_flag 无 pack 行（match_kind=none） |
| `garden_gargantuar` | — | — | gargantuar | gargantuar | gargantuar | authored |  | native/generated/id_mapping.csv: client=garden_gargantuar 无 pack 行（match_kind=none） |
| `garden_imp` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=garden_imp 无 pack 行（match_kind=none） |
| `garden_poet` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=garden_poet 无 pack 行（match_kind=none） |
| `garden_umbrella` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=garden_umbrella 无 pack 行（match_kind=none） |
| `garden_zombie` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=garden_zombie 无 pack 行（match_kind=none） |
| `gargantuar` | tutorial_gargantuar | ZombieGargantuar | gargantuar | gargantuar | gargantuar | pack |  | pkg_2115_ZombieType.json: TypeName=tutorial_gargantuar → ZombieClass=ZombieGargantuar |
| `iceage` | iceage | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=iceage → ZombieClass=ZombieBasic |
| `imp_maid` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=imp_maid 无 pack 行（match_kind=none） |
| `kongfu` | kongfu | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=kongfu → ZombieClass=ZombieBasic |
| `lostcity` | lostcity | ZombieLostCityBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=lostcity → ZombieClass=ZombieLostCityBasic |
| `market_armor1` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=market_armor1 无 pack 行（match_kind=none） |
| `market_armor2` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=market_armor2 无 pack 行（match_kind=none） |
| `market_clockwork` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=market_clockwork 无 pack 行（match_kind=none） |
| `market_mechanic` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=market_mechanic 无 pack 行（match_kind=none） |
| `market_trapeze` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=market_trapeze 无 pack 行（match_kind=none） |
| `mummy` | mummy | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=mummy → ZombieClass=ZombieBasic |
| `mummy_armor1` | mummy_armor1 | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=mummy_armor1 → ZombieClass=ZombieBasic |
| `mummy_armor2` | mummy_armor2 | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=mummy_armor2 → ZombieClass=ZombieBasic |
| `newspaper` | modern_newspaper | ZombieModernNewspaper | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=modern_newspaper → ZombieClass=ZombieModernNewspaper |
| `pirate` | pirate | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=pirate → ZombieClass=ZombieBasic |
| `pirate_armor1` | pirate_armor1 | ZombieBasic | walk | walk | walk | pack |  | pkg_2115_ZombieType.json: TypeName=pirate_armor1 → ZombieClass=ZombieBasic |
| `pole_vaulter` | iceage_dodo | ZombieIceAgeDodo | jump | jump | walk | pack |  | pkg_2115_ZombieType.json: TypeName=iceage_dodo → ZombieClass=ZombieIceAgeDodo |
| `royal_chef_gargantuar` | — | — | gargantuar | gargantuar | gargantuar | authored |  | native/generated/id_mapping.csv: client=royal_chef_gargantuar 无 pack 行（match_kind=none） |
| `royal_flag` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=royal_flag 无 pack 行（match_kind=none） |
| `royal_noblewoman` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=royal_noblewoman 无 pack 行（match_kind=none） |
| `royal_princess` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=royal_princess 无 pack 行（match_kind=none） |
| `royal_winetasting` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=royal_winetasting 无 pack 行（match_kind=none） |
| `royal_zombie` | — | — | walk | walk | walk | authored |  | native/generated/id_mapping.csv: client=royal_zombie 无 pack 行（match_kind=none） |

## 四、族分布与 engine 6 族对照

| 族 | 含义（engine） | 当前实际（55） | 判定（55） |
|---|---|---|---|
| `walk` | 普通行进/啃食 | 49 | 50 |
| `jump` | 跳跃/翻越（Jump/Vault 动作） | 1 | 0 |
| `steal` | 偷取（BUNGEE 动画或 steal 动作） | 0 | 0 |
| `summon` | 召唤（Spawn/Summon 动作） | 0 | 0 |
| `gargantuar` | 巨人砸击（PopAnim/类名含 GARGANTUAR/ZOMBOSS/MECH） | 5 | 5 |
| `fly` | 飞行/气球（IsSpawnedFlying） | 0 | 0 |

两侧合计都是 55。差异可以逐项对上：第五节那 3 条补丁把 `football`、`garden_gargantuar`、`royal_chef_gargantuar` 的 behavior 从 walk 改成 gargantuar，所以当前侧 walk 49、gargantuar 5；剩下的唯一差异是 `pole_vaulter`（当前 jump 1、判定 walk）——原版 `ZombieIceAgeDodo` 判 walk，content 主动写 jump，按队长裁决保留 content 值。补丁前的当前侧是 walk 52 / jump 1 / gargantuar 2，判定侧一直是 walk 50 / gargantuar 5。

## 五、已应用补丁（2026-11-24 队长批准，已写入 content）

| client id | 改前 behavior | 改后 behavior | 当前 content 值 | 判定族 | 状态 | 依据 |
|---|---|---|---|---|---|---|
| `football` | walk | gargantuar | gargantuar | gargantuar | 已生效 | pack TypeName football_mech → ZombieMechFootball，PopAnim 含 MECH → gargantuar |
| `garden_gargantuar` | walk | gargantuar | gargantuar | gargantuar | 已生效 | 无原版条目；content 自带 extra.art_gargantuar=true（authored） |
| `royal_chef_gargantuar` | walk | gargantuar | gargantuar | gargantuar | 已生效 | 无原版条目；content 自带 extra.art_gargantuar=true（authored） |

改前（当前实际族）：walk 52 / jump 1 / gargantuar 2；改后（本次实测）：walk 49 / jump 1 / gargantuar 5。判定族不受补丁影响，仍是 walk 50 / gargantuar 5。缺口随之从 3 条降到 **0** 条。

补丁的实际改法（已写入 `content/zombies.json`，只动这三行的 `behavior` 值）：

```json
{
 "football": {
  "behavior": "gargantuar"
 },
 "garden_gargantuar": {
  "behavior": "gargantuar"
 },
 "royal_chef_gargantuar": {
  "behavior": "gargantuar"
 }
}
```

`pole_vaulter` **不在补丁里**：原版判 walk，content 主动写 jump 是有意行为，保留。

## 六、边界、未改动说明与探针

- **`content/**` 的改动范围**：只改过第五节那 3 行的 `behavior` 值（`walk` → `gargantuar`），其余字节未动，`pole_vaulter` 未动；本工具本身对 content 仍是只读，改的是人按批准执行的补丁，不在这里偷偷改数据。
- **authored 27 条**没有原版条目，族只能来自 content 自述；报告第三节把它们与 pack 证据行分开标注，避免被当成原版事实引用。
- `pole_vaulter` 是**反向差异**：原版 `ZombieIceAgeDodo` 判 walk，content 主动写 `jump`（`extra.jump_distance`），引擎会按 content 走 jump —— 保留 content 值，不列入缺口。
- `kongfu` 带 `extra.summon_count=3`，但原版 `ZombieBasic` 判 walk；按「召唤是表现、不是族」处理，不改族，只在此记录。
- `extra.source_codename` 在 2 条 authored 僵尸上出现（`royal_flag`、`royal_zombie`）；其中代号指向的原版 TypeName 已确认不存在（`royal_zombie`→`royal`、`royal_flag`→`royal_flag`），因此只能作为「客户端自称」记录，不能据此判族。
- 复现：`python tools/contentc/zgaps.py`（加 `--check` 只校验不改盘）；回归：`python -m unittest tools.tests.test_zgaps -v`。
