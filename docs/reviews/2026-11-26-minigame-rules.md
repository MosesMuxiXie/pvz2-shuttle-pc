# 小游戏开局参数表（minigame_rules.json）— 20 种玩法逐 kind 实测与可玩判定

日期：2026-11-26 · 数据源：460.9 OBB（`work/obb_packages`，2117 包）· 产物：
`native/generated/minigame_rules.json`（41,496 B / sha256 `80420f0639289ee058c00c9c67957fe47573bf7daa61ab624d7c5b38b5a183ca`）

> 门禁提醒：本表由 `tools/contentc/minigame_rules.py` 编译，依赖 `native/generated/minigames.json`
> 与 `native/generated/level_mechanics.json`。这两份产物一变，本表就过期（`--check` 会报）；
> 已在 `tools/check_all.ps1` 的 `Step 'minigames'` 之后加了 `Step 'minigame rules'`。

---

## §0 结论

| 问题 | 答案 | 证据 |
| --- | --- | --- |
| 20 种玩法的开局参数能抽到几种？ | **18 / 20 判可玩**，2 种判不可玩（`column`、`invisighoul`） | `counts.playable=18`、`blockedKinds` |
| 不可玩的原因是什么？ | 不是缺模块，而是**模块挂了、参数对象是空 `{}`**：`ColumnMinigameProperties` 8 个对象、`InvisighoulMinigameProperties` 8 个对象，`objdata` 全是 `{}` → `levelsWithNonEmptyAnchor = 0` | `kinds.column.levelsWithAnchor=8` / `levelsWithNonEmptyAnchor=0` |
| 抽到的参数有多少是「每关都写」的？ | 34/36 个 critical 参数至少一关有值；空的两条正是上面两个 kind 的 `gamemodeParams` | `counts.criticalParamsCovered=34 / 36` |
| 哪些参数原版**根本没有**？ | whack 的刷新间隔、joust 的双方阵容、cowboy 的玩法规则（只有教程文案）、vasebreaker 的逐罐坐标 | 见 §6，逐条写进 `missingOptional[].reason` |
| 有没有整种玩法在数据里找不到模块？ | 只有 `chicken`（ZombieChicken）：2116 包内 Modules 别名含 Chicken 的 **0** 个 | `absentKinds[0]`，转引自 `minigames.json#unknowns` |

产物自检：`python tools/contentc/minigame_rules.py --check` 打印

```
minigame_rules kinds=20 playable=18 blocked=2 params=34/36 absent=1 sentinels=2
```

exit 0；两次生成逐字节相同（41,496 B，sha256 同上，CRLF 0）；单次重算/build **2.1 s**、`--check` **2.2 s**（PowerShell
`Measure-Command` 实测，本机 460.9 dump 已在页缓存）。测试 `tools/tests/test_minigame_rules.py` **23 例**。

---

## §1 口径（R01–R09）

- **R01** 参数只从原版对象取：`minigames.json` 的 `params`（关卡包内嵌 objdata）、关卡包本身
  （`SeedBankProperties` 这类不属于任何 kind 的模块对象）、`level_mechanics.json`（只做交叉引用）、
  `content/levels/*.json` 的 `extra`（波次计数）。**没有一处凭经验补值**。
- **R02** `coverage` = 该 kind 的关卡里**真能取到该字段**的关数，分母是 `levels`。9/73 就写 9/73。
- **R03** `playable = 锚点类存在 且 锚点至少一关非空 且 每个 critical 参数 coverage>0`。
- **R04** `missing` 只装 critical 且 coverage==0；`missingOptional` 装非 critical 的缺口，
  含「原版没有这个字段」，理由逐条写明。
- **R05** `levelsIncomplete` 是逐关缺口清单（关 id + 缺哪个 critical 参数）。
- **R06** `conveyor` / `protecttheplant` / `tide` **不重复抽取**：只放交叉引用路径与覆盖率，
  值留在 `level_mechanics.json` / `minigames.json`（所以这三者 `params[x]` 里没有 `agg`）。
- **R07** 哨兵值原样记录并单列（`sentinels`）。
- **R08** 找不到独立模块的玩法写 `absentKinds` 并附取证来源。
- **R09** 固定 `generated` 日期、`sort_keys`、紧凑 separators、LF、`--check` 逐字节。

---

## §2 逐 kind 表

「critical」列写的是 critical 参数的 `coverage/levels`；`inc` = `levelsIncomplete` 条数（起不来的关数）。

| kind | 关数 | 锚点类（原版） | critical 覆盖 | 可玩 | inc |
| --- | ---: | --- | --- | :---: | ---: |
| vasebreaker | 47 | `VaseBreakerPresetProperties`(+`…EndlessProperties`) | vases 46/47、minCol 46、maxCol 46 | ✅ | 1 |
| rail | 196 | `RailcartProperties` | rails 191/196、railcarts 191 | ✅ | 5 |
| laststand | 73 | `LastStandMinigameProperties` | startingSun 72/73、startingPlantfood 72、waveCount 73 | ✅ | 1 |
| beghouled | 11 | `BeghouledPresetProperties` | matchesToWin 11/11、initialPlants 10 | ✅ | 1 |
| whackazombie | 1 | `MinigameWhackAZombieModuleProperties` | hammerHitValue 1/1、hammerTapsToDecay 1、targets 1 | ✅ | 0 |
| joust | 4 | `JoustGameModuleProperties` | timeLimit 4/4 | ✅ | 0 |
| bowling | 15 | `BowlingMinigameProperties` | foulLine 14/15 | ✅ | 1 |
| column | 8 | `ColumnMinigameProperties` | gamemodeParams **0/8** | ❌ | 8 |
| cannon | 8 | `CannonMinigameProperties` | lanes 8/8、rowHasCannon 8、minScore 8、comboBrackets 8 | ✅ | 0 |
| invisighoul | 8 | `InvisighoulMinigameProperties` | gamemodeParams **0/8** | ❌ | 8 |
| cowboy | 10 | `CowboyMinigameProperties` | beginString 10/10 | ✅ | 0 |
| bigtrouble | 6 | `BigTroubleLittleZombieMinigameProperties` | zombieScale 6/6、zombieIncomingDamageScale 6 | ✅ | 0 |
| camel | 2 | `CamelMinigameProperties` | cardTypesUsed 2/2 | ✅ | 0 |
| deathexplosion | 17 | `DeathExplosionMiniGameModuleProperties` | hurtZombies/hurtPlants/hurtGridItems 各 17/17 | ✅ | 0 |
| sproutplanting | 2 | `SproutPlantingMinigameProperties` | plantWeights 2/2、startingSproutCount 2 | ✅ | 0 |
| seeingstars | 3 | `SeeingStarsModuleProperties` | targetPositions 3/3、plantTypeName 3 | ✅ | 0 |
| bonuschallenge | 2 | `BonusChallengeModuleProperties` | challenges 2/2 | ✅ | 0 |
| conveyor | 332 | `ConveyorSeedBankProperties` | mechanicsConveyor 327/332 | ✅ | 5 |
| tide | 77 | `TideProperties` | mechanicsTideEvents 59/77 | ✅ | 18 |
| protecttheplant | 197 | `ProtectThePlantChallengeProperties` | mechanicsProtect 189/197 | ✅ | 8 |

合计：kind 出现 **1019** 次（与 `minigames.json` 同口径）；`counts.levels=813`、`counts.levelsWithAnyKind=813`、
`counts.filesScanned=815`（813 关卡 + minigames.json + level_mechanics.json）。

---

## §3 六类重点参数实测

### 3.1 laststand —— 开局量齐全，槽位要读 SeedBank

| 参数 | 覆盖 | 实测 |
| --- | ---: | --- |
| `startingSun` | 72/73 | 36 个不同值，min 200 / max 45000 |
| `startingPlantfood` | 72/73 | ∈ {0,1,2,3,4} |
| `waveCount`（`extra.wave_count`） | 73/73 | 1…16（10 波 26 关、12 波 21 关、8 波 9 关…） |
| `seedBankSlots`（`SeedBankProperties.OverrideSeedSlotsCount`） | 9/73 | ∈ {3,4,6,7} |
| `sunFromSky`（`Modules[]` 含 `DefaultSunDropper`） | 7/73 | 其余 66 关默认不掉阳光 |
| `presetSeedList` / `selectionMethod` | 20/73 · 71/73 | `chooser`(69) / `preset`(2) |

- 唯一起不来的关：**`cowboy_31`**（整个 `LastStandMinigameProperties` 都没有）。
- `seedBankSlots`、`sunFromSky` **不算 critical**：没写就是走引擎默认槽位/默认掉阳光，不是缺数据，
  但 coverage 照实给（否则这一栏永远 73/73，等于没说）。
- 全库 `LastStand*` 类只有 `LastStandMinigameProperties` 一个（72 对象），**没有** `LastStandSeedBankProperties`。

### 3.2 bowling —— 只有 6 关真的给了子弹序列

| 参数 | 覆盖 | 实测 |
| --- | ---: | --- |
| `foulLine` | 14/15 | ∈ {1,2,3,4,8,9,99,**99999**} |
| `bulbPool`（该关 `ConveyorBelt.InitialPlantList`） | 6/15 | 3–5 个槽，共 26 个条目 |
| `bulletBudget`（`sum(MaxCount)`，派生） | 6/15 | ∈ {0,1,10,13,14} |
| `dropDelayConditions` / `speedConditions` | 6/15 | 掉包间隔 1–4 条 / 速度 1 条 |

- 15 关里只有 6 关挂 `ConveyorBelt`；子弹类型是 `tool_projectile_bowlingbulb1/2/3/_explode/_mega`，
  另有 pokra/iceburg/hurrikale/hotpotato/dazeychain 各 1。
- `lostcity_59` 没有 `BowlingFoulLine`，是 `levelsIncomplete` 里唯一的关。
- `99999`（4 关）是哨兵，已进 `sentinels`，**不**当可用参数。

### 3.3 beghouled —— 目标分有 1000000 哨兵

- `matchesToWin` 11/11：{75, 100, 125, 145, 150, 288, **1000000**}（`modern_32` 是 1000000，等于「不可能达标」）。
- `initialPlants` 10/11（`frontyard_171` 没有），`upgradeMap` 10/11，`stages` 11/11，
  `matchCountsToStageAdvance` 10/11。

### 3.4 joust —— 只有时间与难度联赛，没有「双方阵容」

- `timeLimit` 4/4：`180.0`（3 关）与 `960`（`egypt_9`），原版里 float/int 混写。
- `suggestedLoadout` 3/4：`SunBasic` / `NoSunBasic` / `NoSunMagic`。
- `leagueModifiers` 2/4：`plantagenet_20/21` 各 9 档。
- `playerLineup` / `opponentLineup`：**原版没有**（见 §6）。

### 3.5 whack —— 参数够，但没有刷新节奏

- `targets`（`SpawnWhackAZombiesProps.Zombies`）1/1，17 个对象共 **72** 条目标，单对象 1–8 条。
- `hammerHitValue` `[0.34,0.5,1,2]`、`hammerTapsToDecay` `[60,40,20]`、`groupSize` ∈ {2,3}、
  `zombieCondition` = `speedup3`、`dynamicPlantfood` 7 项。
- `spawnIntervalSeconds`：**原版没有**（见 §6）。

### 3.6 tide / conveyor / protecttheplant —— 只做交叉引用

| kind | 交叉引用 | 覆盖 | 缺口 |
| --- | --- | ---: | --- |
| conveyor | `level_mechanics.json#levels.<id>.conveyor` | 327/332 | 5 关挂了 `ConveyorBelt` 但 mechanics 侧没有 conveyor 对象：`carnival_83`、`dino_28`、`fairy_37`、`fairy_46`、`plantagenet_43` |
| tide | `…#levels.<id>.events.tide` | 59/77 | 18 关挂 `Tide` 模块但没有任何涨潮事件（`beach_1`、`beach_16`、`beach_19`… ）；起潮波次 `StartingWaveLocation` 76/77 |
| protecttheplant | `…#levels.<id>.protectThePlant` | 189/197 | 8 关（`fairy_31`、`frontyard_80/99`、`future_70`…）有 `ProtectThePlant` 模块但 mechanics 无对象 |

这三类 `params` 里**不写 `agg`**（R06），值留在原产物；所以这里的覆盖率差异就是**引擎侧缺口**，
不是编译器丢数据。

---

## §4 playable 判定与两个 ❌

判据是机械的（R03），因此可以反推：只要 `missing` 为空且锚点非空，就判可玩。

`column` / `invisighoul` 判 ❌ 不是因为模块没挂（8/8 都挂了），而是：

```
ColumnMinigameProperties       8 对象 / objdata 全是 {}
InvisighoulMinigameProperties  8 对象 / objdata 全是 {}
```

`levelsWithAnchor = 8` 但 `levelsWithNonEmptyAnchor = 0` → `gamemodeParams` coverage 0 → 8 关全进
`levelsIncomplete`。若照抄模块名就宣布「可玩」，客户端只会拿到 8 个空对象；如实判 ❌ 才能让下游知道
这两关的规则必须另找（或按引擎默认自己定）。

---

## §5 哨兵与反常值

| kind | 参数 | 值 | 关数 | 处理 |
| --- | --- | ---: | ---: | --- |
| bowling | `BowlingFoulLine` | 99999 | 4 | 收录 + 列入 `sentinels`，不当可用参数 |
| beghouled | `MatchesToWin` | 1000000 | 1 | 同上（语义是「不可能达标」） |
| laststand | `StartingSun` | 45000 | 1 | 合法极值（大关），不拦 |
| cannon | `MinScore` | 265500 / 230000 / 188888 | 各 1 | 合法极值，不拦 |

`SENTINEL_VALUES = {99999, 1000000, 2147483647}` 只在 `sentinels` 一处判定，不影响 coverage。

另有两处「原版自己写歪」的记录（不修数据，照原样带出）：

- `cowboy.beginString` 只有 2 个不同值，其中一个是**未本地化的中文**「本关墓碑无法被完全摧毁」
  （其余关是 `[COWBOY_MINIGAME_TUTORIAL_1]` 这类 key）。
- `rail` 有 1 关把 `RailcartType` 写成 `RailcarType`（原版拼写），所以 `railcartType` coverage 是 190 而不是 191。

---

## §6 「原版没有」清单（写进 `missingOptional[].reason`）

| 期望参数 | 结论 | 依据 |
| --- | --- | --- |
| whack `spawnIntervalSeconds` | **没有** | `SpawnWhackAZombiesProps` 只有 Zombies/GroupSize/ZombieCondition/AdditionalPlantfood/DynamicPlantfood；节奏在引擎默认值里 |
| joust `playerLineup` / `opponentLineup` | **没有** | `JoustGameModuleProperties` 只有 TimeLimit / SuggestedLoadout / LeagueModifiers，数据里没有「双方」概念；僵尸池在 `level_mechanics.json#spawners`，植物侧在 `SeedBankProperties.PresetPlantList` |
| cowboy 玩法规则 | **没有** | `CowboyMinigameProperties` 只有 `BeginString` / `ShowTutorial`（教程文案），玩法靠 `CowboyRails`（归 `rail` kind） |
| vasebreaker 逐罐 `row`/`col`、逐罐阳光 | **没有** | `Vases[]` 只有 `Count` + 一个类型键，落位靠 `MinColumnIndex..MaxColumnIndex` 减排除格由游戏随机摆（详见 `vasebreaker.json` 的 unknowns） |

---

## §7 证空记录：ZombieChicken

`absentKinds` 只有一条：

```json
{"id": "chicken", "levels": 0,
 "whatItIs": "ZombieChickenProps(pkg_2112 ZombiePropertySheet) + ZombieChickenFarmerProps(14 对象/8 包)",
 "reason": "2116 个包里没有任何 Modules 别名含 Chicken；只有僵尸属性对象",
 "evidence": "minigames.json#unknowns[type=kind-without-module, kind=chicken]",
 "probe": "python tools/contentc/minigames.py -n chicken"}
```

即：僵尸鸡是**僵尸属性**，不是玩法模块。要用它只能自己写一套刷新规则，数据帮不上。

---

## §8 产物结构与复现

```
{format, generated, sources{minigames{path,bytes,sha256}, mechanics{…}, levels, obb},
 criteria{coverage, playable, missing, missingOptional},
 counts{kinds,playable,notPlayable,levels,levelsWithAnyKind,criticalParams,
        criticalParamsCovered,absentKinds,sentinelRows,filesScanned},
 playableKinds[], blockedKinds[], kindOrder[], absentKinds[], sentinels[],
 kinds{<kind>:{levels, levelsWithAnchor, levelsWithNonEmptyAnchor, playable,
               anchorClasses[], params{<name>:{critical,coverage,levels,via,source[,agg][,reason]}},
               missing[], missingOptional[{name,reason}],
               levelsIncomplete[{level,missing[]}], dependsOn[], evidence[], notes[], sentinels[]}}}
```

- `kindOrder` 单列一份注册表顺序：JSON 是 `sort_keys`，`kinds` 的键必然是字母序。
- 每 kind 的 `evidence` 是一行行「参数名: 覆盖/总数 来源」，便于逐条抽查。

复现：

```powershell
python tools/contentc/minigame_rules.py                     # 41,496 B / sha256 80420f06…
python tools/contentc/minigame_rules.py --check              # exit 0（2.2 s）
python tools/contentc/minigame_rules.py -n bullet            # 打印命中关键词的 kind/参数
python -m unittest tools.tests.test_minigame_rules -v        # 23 例
```

`tools/check_all.ps1` 已在 `Step 'minigames'` 之后插入：

```powershell
Step 'minigame rules' { python tools/contentc/minigame_rules.py --check }
```

---

## §9 诚实边界

1. `coverage` 是**关卡数**，不是「每个对象都有该字段」。同一关 17 个 `SpawnWhackAZombiesProps` 里
   只有 2 个有 `GroupSize`，coverage 仍算 1 关。
2. `playable` 只回答「开局参数在数据里够不够」，**不**回答「引擎已经能跑」。`protected` 的 3 类
   cross 引用覆盖率（327/59/189）就是引擎侧还没补齐的证据。
3. `column` / `invisighoul` 判 ❌ 是数据结论，不是实现结论：如果将来引擎给这两种玩法定了默认规则，
   改口径要同时改 `SPECS` 与报告，不能只把 `playable` 翻成 true。
4. 哨兵集合 `{99999,1000000,2147483647}` 是**经验集合**，只用于标注，不做数据清洗；
   若发现新的哨兵值，应加进集合并在 §5 补一行。
5. `absentKinds` 只搬 `minigames.json` 已记过的 `kind-without-module`（1 条），
   不把 `content-rail-without-module` 之类的名单对齐问题混进「玩法缺失」。
6. 本报告所有数字取自产物本身 + 探针复算；`--needle` / `-n` 只能证明「注册表里有这个词」，
   证明不了原版有对应对象——后者一律靠 `coverage` 与 `evidence` 里的类名。
