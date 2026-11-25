# T54 只读审计：关卡机制与奖励数据（level_mechanics / rewards_from_pack）口径可信度

- 审计人：auditor（只读）
- 审计时间：2026-11-24 11:47–12:10
- 任务：t53（attempt `bb8471e3-94c2-4e95-94b7-b9c2819b949a`）
- 纪律：未改源码、未改 content、未改生成物，未 commit（HEAD `24a2493`）。所有重算用自写脚本直读 1809 关 + 1809 包，**不 import 被审编译器**，不调用其函数做二次统计。
- 结论：**两个编译器的主要口径可复现、可采信**；发现 3 条 medium（文档/映射/死数据）与 4 条 low（注释、措辞、测试绊线、容器归属）。没有 blocker/high。

## 0. 审计对象快照

| 文件 | 字节 | mtime | sha256/12 |
|---|---|---|---|
| `tools/contentc/mechanics.py` | 60073 | 11-24 11:40:18 | `4018D1895570` |
| `native/generated/level_mechanics.json` | 4750400 | 11-24 11:40:45 | `2B30D88DDF23` |
| `docs/reviews/2026-11-24-level-mechanics.md` | 11864 | 11-24 11:40:45 | `AF6E0AB32313` |
| `tools/tests/test_mechanics.py` | 25445 | 11-24 11:41:30 | `4095E207A633` |
| `tools/contentc/rewards.py` | 52946 | 11-24 11:32:08 | `935ACBF5CAA2` |
| `native/generated/rewards_from_pack.json` | 305478 | 11-24 11:36:07 | `304B26F79F7B` |
| `docs/reviews/2026-11-24-rewards.md` | 21454 | 11-24 11:35:47 | `89B000C7A795` |
| `tools/tests/test_rewards.py` | 14359 | 11-24 11:32:53 | `6E5F4215A3D0` |

数据源：`D:\OneDrive\文档\pvz_shuttle\work\obb_packages`（`mechanics.py:44` 的 `DEFAULT_OBB`，实测存在）——**1809 个 `pkg_*_LevelDefinition.json`，包目录共 2117 个文件**。`C:\work\obb_packages` 不存在（t13/t20 时代的老路径）。

## 1. 结论摘要

| # | 问题 | 判定 | 关键数字 |
|---|---|---|---|
| Q1 | 12 个计数独立重算 | **11 项逐字复现**，1 项口径不同（`sentinels`） | 350/349/132/272/690/466/241/286/1645/123/21/49/80/10 全等；`sentinels` 264（读路径）vs 1970（全量递归） |
| Q2 | jittered 聚合是否丢信息 | identity 成立；**波次归属丢失** | 50 关抽样 `sum(waves)+waveUnresolved==objects` 违例 0；46/50 关同 id 逐波数量不同 ⇒ 每波每行不可重建（M1） |
| Q3 | conveyor 350 vs 349 | **未发现缺陷** | 多出的 1 关 = `lostcity_67`（仅 `ModifyConveyorWaveActionProps`）；引擎从 `changes[].add[]` 补槽，不会误判 |
| Q4 | protect 语义 | 数据自洽，**引擎侧 count 是死数据** | 286 关；`mustProtectCount` 分布含 `0:1`；无 `>len(plants)`；18 关 `count != len(plants)`（M2） |
| Q5 | 拾取物推断标注 | 5 字面量全部真实；**5 行可映射却标 none** | `mapping` 18 inferred / 2 unresolved / 5 none（M3） |
| Q6 | 经济口径 | **与数据一致** | Silver p2 / Gold p40·p60 / key p30 + `World` + `EnabledAfter=egypt3`；`CoinsPerKey=1000` |

## 2. 证据方法

自写脚本在 `build/audit53/`（只读直读，不 import `mechanics.py` / `rewards.py`）：

| 脚本 | 作用 |
|---|---|
| `recount.py` | 12 项计数独立重算 + 哨兵全量递归 + wave 解析 |
| `probe2.py` | MOD-only 关、protect 分布、jittered 抽样 |
| `probe3.py` | jittered 对象字段 / Waves 结构 / `lostcity_67` 记录 |
| `probe4.py` | 50 关 identity 与「每波每行」可重建性 |
| `probe5.py`、`probe6.py` | `CollectableType`/`TypeName`、悬空 `PresentTable` 重算、`LootTable` 全表、常量 |

途中修掉的三个自身 bug（记录以免后人重复踩）：`PKG_STEM_RE` 要写成 `^(pkg_\d+)`（`pkg_0325` 后面没有下划线）；包索引要用 `"_".join(name.split("_")[:2])`（`rsplit("_",2)[0]` 会得到 `"pkg"`）；对象名在 `objdata.TypeName`，而 **alias 在对象级的 `objects[i]["aliases"][0]`**（`mechanics.py:300-306`），不在 `objdata` 里。

另：`Sort-Object -Unique` / `Group-Object` 在 PowerShell 里**默认大小写不敏感**，做唯一性统计必须显式 `-CaseSensitive`（这条曾让 t35 把 602 条弹道误记为 601）。

## 3. 发现

### M1（medium）jittered 聚合丢失波次归属，文档「信息等价」的措辞不成立

- 位置：`tools/contentc/mechanics.py:683-717`（`_aggregate_jittered`）、`docs/reviews/2026-11-24-level-mechanics.md:48`
- 文档原文（L48）：「压成 `{objects, total, waves{波号: 对象数}, waveUnresolved, pool{zombieId: {count, rows}}}` 与原表信息等价，引擎按 `count` 抽即可」。
- 期望：聚合后仍能回答「第 3 波第 2 行有几只 `lunar_armor2`」。
- 实际：不能。`waves[str(wave)] += 1` 是**按对象**计数（注意是该 spawner 对象，不是僵尸条目），`pool[id].rows` / `levels` 是整关集合，都不带波次。
- 复现：

```
python -c "import json,pathlib; d=json.loads(pathlib.Path('native/generated/level_mechanics.json').read_text(encoding='utf-8')); \
print(json.dumps(d['levels']['lunarrainbowmarket_52']['spawners']['jittered']['pool'], ensure_ascii=False))"
# 实际 {"lunar_armor2": {"count": 5, ...}}；原始池里它是 {3:2, 6:2, 7:1}
python build/audit53/probe4.py     # 50 关抽样：46 关存在同一 id 逐波数量不同
```

  其他例子：`dino_8` 的 `dino` = `{1:1, 2:2, 3:1, 5:3, 7:1, 8:2, 10:3}` → 聚合只剩 `{"count": 13, "rows": [2,3,4,5]}`；`sky_39`、`heian_6`、`kongfu_26` 同类。
- 影响：**当前不是玩法缺陷**（引擎完全不消费 jittered：`native/src/engine/mechanics.cpp:241` 与 `:273` 把 `jittered` 列为已知但跳过解析，全仓没有 pool 解析代码），但它是数据契约：任何后续想按波次刷僵尸的消费者（例如把 1615 关的普通波次换成逐条计划）都得回头改产物格式，而文档现在写着「等价」会误导下一位实现者。
- 修法：把 L48 改成「`count` 与逐条列表等价；`waves` 是对象数、`rows` 是整关行号集合，**不含波次归属**」；若确需波次，加 `waves{zombieId: {wave: count}}`（体积代价约 +1.2 MB，可接受）。

### M2（medium）`mustProtectCount` 在引擎侧是死数据，18 关的判负比数据语义严格

- 位置：`native/src/engine/world.cpp:1093`；数据在 `native/generated/level_mechanics.json` 的 `protect.thePlant`
- 期望：数据给了「需要保住 N 株」（`MustProtectCount`），失败条件应按 N 判。`mechanics.py:604` 把 `failWhenProtectedPlantDies` 硬编码为 `True`（原版无显式失败动作，已在 `unknowns` 的 `protect-failure-rule` 披露）。
- 实际：`world.cpp:1093` 只看布尔：`if (plant->protectedPlant && mechanics_ != nullptr && mechanics_->protect.failWhenProtectedPlantDies)` → 任何一株受保护植物死亡即判负；`mustProtectCount` 只被塞进事件 payload（`world.cpp:1086` 附近）。全库 1809 个包里 `FailWhenProtected*` / `ProtectedPlantDies` **0 命中**，所以布尔本身只能靠假设，问题不在布尔，而在**已经编出来的 count 没有下传**。
- 数据分布（自算，`build/audit53/probe2.py`）：286 关；`MustProtectCount` = {1:53, 2:62, 3:70, 4:17, 5:63, 6:9, 7:3, 8:4, 9:1, 10:3, **0:1**}；**无 `> len(plants)`**；`count != len(plants)` 共 **18 关**（`beach_88` 4/5、`carnival_90` 1/2、`chinesegarden_38` 1/2、`egypt_74` 4/5…），极端 `egypt_56` = **0** 且列了 15 株。
- 影响：这 18 关玩家「本来可以牺牲几株」，引擎里一株都不能死；`egypt_56` 更矛盾（要求保护 0 株，却一株都不能死）。属 win/lose 判定差异，不是显示问题。
- 修法：`world.cpp` 判负改成「受保护植物死亡数 > `len(plants) - mustProtectCount`」；`mustProtectCount == 0` 时视为「无保护要求」（或按原版语义跳过判负）。`mechanics.cpp` 已经把 count 解析进位（`mechanics.cpp:163` 一带），只需在判负处使用。

### M3（medium）5 行 `mapping="none"` 的拾取物在数据里真实存在，可映射却被登记为无

- 位置：`tools/contentc/rewards.py`（命名约定映射规则）；产物 `native/generated/rewards_from_pack.json`
- 实际：25 条 loot 行里 `mapping` = 18 `inferred-name-convention`、2 `unresolved`（`EgyptKey1`/`EgyptKey2` → `worldkey_egypt`，而 10 个 `worldkey_*` 里没有 egypt）、**5 `none`**（`LawnMower1`–`LawnMower4`、`Sprout1`，`pickup: null`）。
- 期望：按同一条命名约定，`LawnMower*` 与 `Sprout*` 应当落在 `pkg_0010_CollectableType.json` 的既有行上。
- 实际数据：`lawn_mower`（`objdata.TypeName = CollectableLawnMower`）与 `sprout`（`CollectableSprout`）**都存在**。
- 复现：

```
python build/audit53/probe5.py    # 打印 CollectableType 全表 + loot 行 mapping
python -c "import json,pathlib; d=json.loads(pathlib.Path('native/generated/rewards_from_pack.json').read_text(encoding='utf-8')); \
print([r for r in d['loot'] if r['mapping']=='none'])"
```

- 影响：4 条割草机奖励与 1 条幼苗奖励在表里表现为「不知道掉什么」，下游（T55 经济闭环）会照 `null` 处理，直接少发道具。文档 L164 只解释了 `EgyptKey` 的 `unresolved`，没有解释这 5 条 `none`，读者会以为数据里真没有。
- 修法：映射规则加 `lawnmower→lawn_mower`、`sprout→sprout` 两条（或让规则在同名前缀命中 `Collectable*` 时采信），把这 5 行改成 `inferred-name-convention`；`EgyptKey` 保留 `unresolved` 并在文档里点名「10 个 worldkey 无 egypt」。

### L1（low）`withConveyor=350` 是「类存在」，引擎实际认 348 关

- 位置：`native/src/engine/mechanics.hpp:91`（`hasConveyor() { return !conveyor.slots.empty(); }`）、`docs/reviews/2026-11-24-level-mechanics.md:21`
- 数据：350 关有 `ConveyorSeedBankProperties`；其中 **345 关卡槽非空**，**3 关卡槽为空但能从 `changes[].add[]` 补出槽**（`lostcity_67`、`lunarrainbowmarket_44`、`steam_5`），**2 关两者皆无**（`dark_33`、`frontyard_173`）⇒ 引擎侧 `hasConveyor()` 为真的只有 **348** 关。
- 复现：

```
python -c "import json,pathlib; d=json.loads(pathlib.Path('native/generated/level_mechanics.json').read_text(encoding='utf-8')); \
lv=d['levels']; s=[k for k,r in lv.items() if (r.get('conveyor') or {}).get('slots')]; e=[k for k,r in lv.items() if r.get('conveyor') and not (r['conveyor'].get('slots') or [])]; print(len(s), len(e), e)"
# 345 5 ['lostcity_67','lunarrainbowmarket_44','steam_5','dark_33','frontyard_173']
```

- 影响：口径差 2 关，不影响正确性（`dark_33` / `frontyard_173` 本来就不是传送带关，`hasConveyor()` 为 false 是正确结果）。但如果有人拿 350 当「可玩传送带关数」验收，会对不上。
- 修法：文档 L21 补一句「350 为类存在数，其中 348 关在引擎侧会生成非空卡槽（差 2 关：`dark_33`、`frontyard_173`）」。

### L2（low）哨兵「264 处」是读路径统计，不是全量

- 位置：`docs/reviews/2026-11-24-level-mechanics.md:64`（「哨兵命中 **264** 处（`-1` 264 处、`2147483647` 0 处）」）
- 实际：264 是经 `Stats.num()` 读到的命中数（`mechanics.py:187-211` 记录 `SENTINELS=(-1, 2147483647)` 命中但**原值原样返回**）。对全部 objdata 递归扫描是 **1970** 处（全为 `-1`，`2147483647` 零命中），差额最大的类：`SeedBankProperties` 1459、`WaveManagerModuleProperties` 128、`ZombieGeneralZmechProps` 48、`BeghouledSeedBankProperties` 48、`InitialGridItemProperties` 39、`ProtectThePlantChallengeProperties` 33、`ConveyorSeedBankProperties` 31。
- 影响：读起来像「全库只有 264 个哨兵」，实际是「编译器读的那些字段里有 264 个」。不影响产物正确性（未替换、原样保留是对的）。
- 修法：L64 改成「**本次读取路径**命中 264 处；全库 objdata 递归为 1970 处（全部 `-1`）」。

### L3（low）12 个头条计数只有 1 条测试绊线

- 位置：`tools/tests/test_mechanics.py:437`（`assertEqual(self.counts["withConveyorSeedBank"], 349)`）
- 实际：`withConveyor=350`、`withInitials=272`、`withInitialGridItems=690`、`withGravestones=241`、`withProtect=286`、`withSpawners=1645`、`withEvents=123`、`withMutators=21`、`withBoardGrid=49`、`unknowns=10`、`sentinels=264`、`waveUnresolved=195` 都没有断言；`--check` 的逐字节比对只在产物与 fresh render 同源时才有意义（编译器逻辑改了、产物一起重生成，`--check` 仍然是绿的）。
- 影响：编译口径回退（例如某类对象改判）不会红，只会静默改数字，正是本轮要用「独立重算」才能发现的那类腐坏。
- 修法：把上表 12 个数字写进 `test_mechanics.py` 的一组 `assertEqual`（配 `-CaseSensitive` 的唯一性口径说明）。同理 `test_rewards.py` 可加 `lootRows=25 / danglingPresentTables=13 / danglingPresentRefs=68`。

### L4（low）`mechanics.cpp:127-129` 注释把 5 关全归因于 `changes[].add[]`，实际只有 3 关

- 原文：「Five conveyor levels carry no `slots` at all and instead add packets through `changes[].add[]` (`lostcity_67`).」
- 实测：「5 关无 slots」正确；但走 `changes` 补槽的是 3 关（`lostcity_67`、`lunarrainbowmarket_44`、`steam_5`），另 2 关（`dark_33`、`frontyard_173`）既无 slots 也无 changes，`hasConveyor()` 为 false —— 这是正确结果，不是漏判。
- 修法：注释改成「Three conveyor levels carry no `slots` and add packets through `changes[].add[]` (`lostcity_67`, `lunarrainbowmarket_44`, `steam_5`); two carry neither (`dark_33`, `frontyard_173`) and are correctly treated as non-conveyor.」

## 4. 六问逐条

### Q1 计数口径——11 项逐字复现，`sentinels` 口径不同

独立重算（直读 1809 关的 `extra.package` + 1809 个包，自己判 objclass）与产物全等：

```
withConveyor 350 / withConveyorSeedBank 349 / withConveyorChanges 132
withInitials 272 / withInitialGridItems 690 / withGridItemPlacements 466 / withGravestones 241
withProtect 286 / withSpawners 1645（10 个 kind 全等：grid 237 ground 100 spider 118 storm 119 fish 26
portal 130 dino 93 beach 82 gravestone 353 jittered 1615）
withEvents 123 / withMutators 21 / withBoardGrid 49 / levelsAllNull 80 / unknownMechanics 10
waveResolved 26914 / waveUnresolved 195 / packagesResolved 1809（missing/shared/ambiguous 均 0）
```

两项需要说明（都不是缺陷）：

1. `withGridItemPlacements=466`：定义是「`InitialGridItemProperties` 存在**且** `InitialGridItemPlacements` 非空」。只判类存在会得 475，差的 9 关（`frontyard_119`、`frontyard_145`、`iceage_26`、`lostcity_11`、`lostcity_13`、`lostcity_17` 等）placements 为空 ⇒ **466 正确**。
2. `sentinels=264`：见 L2，是读路径统计，非全量。

### Q2 jittered 聚合——identity 成立，波次归属丢失

- `sum(waves) + waveUnresolved == objects`：50 关抽样 **0 违例**；产物内部 1809 关 **0 违例**。
- `pool[id].count` 与原始逐条总数：**全等**（jittered 对象 20898、僵尸条目 121018，与文档「1615 关、12 万条」一致）。
- 「每波每行几只」：**不可重建**，见 M1。

### Q3 conveyor 350 vs 349——未发现缺陷

- 多出的 1 关：**`lostcity_67`**（`pkg_0697`），只有 `ModifyConveyorWaveActionProps`（alias `MC1`，`{"Add":[{"MaxCount":1,"Type":"RTID(hollyknight@PlantTypes)","MaxWeightFactor":0}],"Remove":[{"Type":"RTID(repeater1@PlantTypes)"}]}`，`wave: 21`），产物里 `conveyor.slots=[]`、`changes[0]` 有内容。
- 引擎不会误判为「传送带关却没有卡槽」：`native/src/engine/mechanics.cpp:127-146` 专门把 `changes[].add[]` 转成 `ConveyorSlotRow`，`hasConveyor()` 仍以 `!slots.empty()` 为准。
- 相关口径差异（350 类存在 vs 348 有槽）记 L1；注释措辞记 L4。

### Q4 保护植物——数据自洽，`mustProtectCount` 未下传（M2）

- 286 关；分布见 M2；**无 `mustProtectCount > len(plants)`**；`= 0` 有 1 关（`egypt_56`，同时列了 15 株）。
- `failWhenProtectedPlantDies` 在数据里没有来源（全库 0 命中），编译器硬编码 true 并进 `unknowns` 披露 —— 这是**诚实**的降级。
- 真正的问题在引擎消费端，见 M2。

### Q5 拾取物推断——5 字面量成立，`none` 行漏映射（M3）

- 五个字面量在 `pkg_0010_CollectableType.json` 都有真实行：`coin_silver` CoinValue **10**、`coin_gold` **100**、`gem_diamond` GemValue **2**、`sun_small` SunValue **5**、`sun_large` **75**（另有 `coin_gold_fake` 100、`coin_treasure_chest` 10000、`sun` 50、`sun_medium` 25、`sunflower_sun65/90/115`、`moneybag` 30、`big_moneybag` 200）。
- 全库没有任何表把 `LootTable.Type` 映射到 `CollectableType`（同时出现 `SilverCoin` 与 `Collectable` 的包只有 `pkg_2112_ZombiePropertySheet.json`）⇒ 标注为「推断」是对的，文档 L164 的说明准确。
- `mapping` 计数：18 inferred / 2 unresolved / 5 none；5 条 `none` 见 M3。
- 13 张悬空 `PresentTable` / 68 关引用：独立重算与产物**逐条一致**（`beach_normal_01` 2、`dark_normal_01` 6、`eighties_normal_01` 4、`heian_normal_01` 2 + 1 shiny、`kongfu_normal_01` 1、`lostcity_normal_01` 19，7 张 shiny 各 2/6/4/1/1/1/19）；`pkg_2079` 实有 8 张表（cowboy/egypt/future/pirate × normal/shiny）⇒ 「13 张悬空」是 8 张里被引用的部分 + 名字不存在，文档 L133 的叙述与数据一致。

### Q6 经济口径——未发现缺陷

- `DefaultLootTable` 25 条：`Silver1` 1..3 **Period 2**、`EnabledAfter=tutorial4`、`DisableLootCoins`（default 与 danger 各一条）；`Gold1` 1..1 **p40**；`Gold2`(danger) 1..1 p40；`Gold3` 1..3 **p60**；`Gold4`(danger) 1..3 p60；`Gem1` p30、`Gem2` p40（这两条无 `LevelLootKey`）。
- 8 条 key（`EgyptKey1/2`、`PirateKey1/2`、`CowboyKey1/2`、`FutureKey1/2`）都是 1..1 **Period 30**、`EnabledAfter=egypt3`、**且带 `World`**（egypt/pirate/cowboy/future）⇒ 文档 L89「`World` 限定世界、`EnabledAfter` 限定进度、不属 default/danger 子集」准确，「只在埃及后启用」不等于「只在埃及掉」。
- whack 两条 `SunSmall1` p0.3、`SunLarge1` p0.5，单位按秒推断 —— 文档 L88 已明确标成推断而不是字段声明。
- 常量（`GamePropertySheet`）：`CoinsPerKey=1000`、`KeysPerCostume=10`、`StarsPerCostume=20`、`LawnMowerPurchasePriceInCoins=2000`、`SeedSlotRentalCost=2000`。
- 花币端 80 门（`world_gates.json` 同源）：27 key（4→13、3→7、5→5、1→2）、53 star（10→8、8→3、20→2、1→1、**0→21**、缺字段 18）——与文档 L185 完全一致。

## 5. 测试与自检（实跑）

```
python -m unittest tools.tests.test_mechanics tools.tests.test_rewards
→ Ran 53 tests in 8.467s / OK / exit 0        (mechanics 27 + rewards 26)

python tools/contentc/mechanics.py --check
→ exit 0（15 s）
→ 产物已是最新：levels=1809 withConveyor=350 … sentinels=264 waveUnresolved=195

python tools/contentc/rewards.py --check
→ exit 0（10 s）
→ rewards=575 levels=1809 loot=25 presents=36 first=486 replay=67 gates=80 unknowns=10 / OK
```

两次 `--check` 前后 `level_mechanics.json` `2B30D88DDF23`、`rewards_from_pack.json` `304B26F79F7B` 未变（只读）。

两条容易被误判的观察：

- 日志里 `FAIL shipped file differs from a fresh render` 是 `tools/tests/test_rewards.py:284 test_check_detects_drift` 触发的**预期负路径**（对应 `tools/contentc/rewards.py:1136`），不是失败。
- `tools/tests/test_rewards.py:274` 有 `@unittest.skipUnless(HAS_OBB, …)`：OBB 缺失时相关用例静默少跑（本机 OBB 在，未跳过）。

## 6. 环境与未覆盖

- 环境：OBB 在 `D:\OneDrive\文档\pvz_shuttle\work\obb_packages`（1809 关卡包 + 308 其它 = 2117 文件）。`mechanics.py:44` 的默认路径正确；`C:\work\obb_packages` 不存在，旧脚本若引用该路径会假红。
- 未覆盖（本轮不判）：
  1. 引擎侧消费语义的正确性（传送带补充节奏、墓碑与原版波次的先后）——属 T51/T52 复审范围，本轮只看数据与已存在的消费代码。
  2. `unknowns` 里 `wave-unresolved` 的 195 条为何 miss（alias 不在 `WaveManagerProperties.Waves` 也不符合 `Wave<N>`）——需要逐包 dump Waves 全表，本轮只确认**计数**与产物一致。
  3. `rewards_from_pack.json` 目前无引擎消费者（全仓 grep 只在 tools 内），经济闭环（T55）落地后需重新审一遍「数据 → 行为」的接线。

## 7. 复现命令清单

```powershell
# 独立重算 12 项计数（不 import 被审代码）
python build/audit53/recount.py

# jittered：identity + 逐波可重建性（50 关抽样）
python build/audit53/probe4.py

# MOD-only 关 / protect 分布
python build/audit53/probe2.py

# conveyor 空槽分布（345 slots / 5 空槽 / 2 两者皆无）
python -c "import json,pathlib; d=json.loads(pathlib.Path('native/generated/level_mechanics.json').read_text(encoding='utf-8')); lv=d['levels']; e=[k for k,r in lv.items() if r.get('conveyor') and not (r['conveyor'].get('slots') or [])]; print(len(e), e)"

# 拾取物 / 悬空 PresentTable / LootTable 全表
python build/audit53/probe5.py

# 两个编译器的自检
python tools/contentc/mechanics.py --check
python tools/contentc/rewards.py --check

# 测试
python -m unittest tools.tests.test_mechanics tools.tests.test_rewards
```

## 8. 必须先修清单

1. **M2**（`native/src/engine/world.cpp:1093`）：判负要用 `mustProtectCount`，否则 18 关（含 `egypt_56`）的胜负条件与数据相反。
2. **M3**（`tools/contentc/rewards.py`）：`LawnMower*` / `Sprout*` 5 行映射到 `lawn_mower` / `sprout`，否则 T55 会少发 5 类奖励。
3. **M1**（`docs/reviews/2026-11-24-level-mechanics.md:48`）：把「信息等价」改成「count 等价、波次不保留」，避免下一个消费者按错假设接线。
4. **L3**：给 12 个头条数字加断言（可与其他 L 项同批）。

L1 / L2 / L4 为注释与措辞修正，可与上述同批，不阻塞。
