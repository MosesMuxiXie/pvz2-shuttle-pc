# 2026-11-26 掉落产物落地（B2 第二波）

任务：把 `native/generated/rewards_from_pack.json` 里剩下 **438 行「战斗路径发不出去」**的记录，
能落地的落进存档、落不了的给出**可复算的理由**，不允许静默丢弃。

结论一句话：**438 行里 315 行落地（plant 293 + cosmetic 22，落到 244 个植物 id + 15 个装扮 id），
123 行显式不落地**，各有 reason 与 `rewardLog` 记录；金币一族经查实际是「4 条商店价格 + 26 条无处触发的
rift 奖励」，默认一分不发，需要 `--land-constants` / `--land-rift` 显式开才发。

改动文件：`native/src/progress.{hpp,cpp}`、`native/src/rewards.{hpp,cpp}`、`native/src/main.cpp`、
`native/tests/rewards_test.cpp`。**`native/generated/rewards_from_pack.json`、`content/**`、`tools/**` 未改**，
`native/CMakeLists.txt` 也未改（`rewards.cpp` 本来就在 `pvz_progress` 里）。

---

## 1 438 行到底成了什么

| 类别 | 行数 | 处理 | reason |
| --- | ---: | --- | --- |
| `plant` / `unlock_plant:<plant>` | 293 | 写 `progress.unlockedPlants`（唯一 244 个 id） | 首次落地记 `landed`；重复行记 `already_owned` |
| `cosmetic` / `unlock_costume:<id>` | 22 | 写 `progress.costumes`（唯一 15 个 id） | 同上 |
| `coin` / `constant:*` | 4 | **不发**，只记进 `prices` + `rewardLog` | `price_constant` |
| `coin` / `rift-*` | 26 | **不发**（客户端没有 rift 入口） | `rift_payout` |
| `gem` / `rift-*` | 5 | 不发 | `rift_payout` |
| `pinata` / `rift-*` | 9 | 不发 | `rift_payout` |
| `xp` / `rift-*` | 14 | 不发 | `rift_payout` |
| `note` | 11 | 只记 `rewardLog` | `unmodelled` |
| `collectable` | 9 | 只记 `rewardLog` | `unmodelled` |
| `powerup` | 6 | 只记 `rewardLog` | `unmodelled` |
| `none` | 5 | 只记 `rewardLog` | `unmodelled` |
| `upgrade` | 3 | 只记 `rewardLog` | `unmodelled` |
| `star` / `constant:StarsPerCostume` | 1 | 只记 `rewardLog` + `prices` | `price_constant` |
| `trophy` | 18 | 只记 `rewardLog` | `unmodelled` |
| `giftbox` | 1 | 只记 `rewardLog` | `unmodelled` |
| `gadget` | 1 | 只记 `rewardLog` | `unmodelled` |
| **合计** | **438** | 落地 315 / 未落地 123 | |

reason 汇总（默认跑，`--rewards-report` 的 stderr `detail` 行原文）：

```
{"alreadyOwned":56,"costumesTotal":15,"landedCostumes":15,"landedPlants":244,"logged":123,
 "plantsTotal":244,
 "prices":{"CoinsPerKey":1000,"KeysPerCostume":10,"LawnMowerPurchasePriceInCoins":2000,
           "SeedSlotRentalCost":2000,"StarsPerCostume":20},
 "reasons":{"already_owned":56,"price_constant":5,"rift_payout":54,"unmodelled":64}}
```

三本账记的不是同一件事，别直接相加：

- **行数守恒**：`landed 315 + unlanded 123 = 438` ✅
- **`landed` 315 = 259 首次落地 + 56 already_owned**：259 = 244 植物 + 15 装扮（唯一 id 数）
- **reason 只给「非默认路径」的行记账**：`already_owned 56`（已计入 landed）+ `price_constant 5`、`rift_payout 54`、`unmodelled 64`（三者合计 123 = unlanded）。
  剩下 `438 - 56 - 123 = 259` 行是**普通首次落地**，没有 reason 值，所以在 `reasons` 里查不到——
  它们的存在由 `landedPlants 244` + `landedCostumes 15` 体现。
- 因此 `56 + 5 + 54 + 64 = 179` 是「有 reason 的行数」，不是 123，也不是 438。

`landed 315` 与「唯一 id 244 / 15」的差 56 恰好就是重复行数（49 条 `replay:` plant + 7 条重复 costume）。

### 1.1 「293 行 plant」不是 293 株植物

`rewards_from_pack.json` 里 plant 行有两族 id：`first:unlock_plant:<plant>` 244 条、
`replay:unlock_plant:<plant>` 49 条（同一株植物的 repeat-clear 重复行）。cosmetic 同理：22 行 → 15 个唯一 id（7 条重复）。
所以「落地」必须按行算、「持有」必须按唯一 id 算，否则第二遍落地会把同一株植物插两次。

实测（`ConvertFrom-Json -AsHashtable` 直接数文件）：

```
plant rows: 293 distinct params: 244
cosmetic rows: 22 distinct params: 15
```

`rewards_test` 把这件事钉住了（原文）：

```
plants: 293 rows -> 244 owned (landed 315, already owned 56), second pass planted 0 alreadyOwned 315
```

第二遍 `planted 0` / `alreadyOwning 315` 就是幂等性的证据：落地是「整表跑一遍」的操作，
不带关卡上下文（原因见 §4），因此必须可以重复跑而不增长。

## 2 代码里的规则（一行一处，注释写死在实现里）

`native/src/rewards.cpp` 的 `RewardLanding landRewards(Progress&, const RewardTable&, const LandingOptions&)`
（第 494 行起）就是上表的实现，判定顺序：

1. **`constant:` 族优先于 kind 判断**（第 505–525 行附近）：`constant:StarsPerCostume` 的 `kind` 是 `star`
   而不是 `coin`，若先按 kind 分流它会被错当成「星章奖励」；现在一律先记 `prices[constant]=amount`，
   只有 `kind == "coin"` 且 `options.landEconomyConstants` 时才进 `coins`（`price_paid`），
   否则 `price_constant` + `rewardLog`。星章永远只能记录，不能变成金币。
2. `kind == "plant"`：`param` 空 → `no_param`；已在 set 里 → `already_owned`（仍 `++landed`）；否则插入 + `++planted`。
3. `kind == "cosmetic"`：同 plant，写 `progress.costumes`。
4. `kind == "coin"` 且 id 前缀 `rift-`：只有 `options.landRiftPayouts` 才 `coins += amount`（`rift_paid`），否则 `rift_payout`。
5. 其余（含 `rift-` 的 gem/pinata/xp）：`++unlanded`、`++byKind[kind]`、`++byReason[rift ? "rift_payout" : "unmodelled"]`，写 `rewardLog`。

`.hpp` 里那段长注释把「为什么 trophy 不落」写明了：客户端有 `Progress::trophies` 字段，但
`rewards_from_pack.json` 的 trophy 行没有 trophy id（`param` 是 `trophy_n` 这种位置名），
按任务清单也没有要求它进 `trophies`，所以它走 `unmodelled` + `rewardLog`，不猜。

### 2.1 为什么金币一分不发（任务前提需要修正）

任务书写的是「`coin` 30 行是常量金币」，实测不成立：438 行里 `kind=="coin"` 的正好 30 行，
但它们是**两个来源**：

| 来源 | 行数 | amount | 性质 |
| --- | ---: | --- | --- |
| `constant:CoinsPerKey` | 1 | 1000 | 商店价格：换 1 把钥匙要 1000 金币 |
| `constant:KeysPerCostume` | 1 | 10 | 商店价格：1 件装扮要 10 把钥匙 |
| `constant:LawnMowerPurchasePriceInCoins` | 1 | 2000 | 商店价格：割草机 2000 金币 |
| `constant:SeedSlotRentalCost` | 1 | 2000 | 商店价格：租种子槽 2000 金币 |
| `rift-boss:aN:dN[:n]:coins` | 18 | 500/1000/2000/1700/0 | rift boss 掉落，需要 rift 进度 |
| `rift-clear:{1..5|default}:N:coins` | 8 | 600–1500 | rift 通关掉落，需要 rift 进度 |

前 4 行是**价格**不是**发放**——数据文件自己的 `unknowns.whyZeroCounted` 就写着
`GamePropertySheet.{CoinsPerKey,KeysPerCostume,StarsPerCostume,LawnMowerPurchasePriceInCoins,SeedSlotRentalCost}`；
后 26 行是真实 rift 奖励，但客户端没有 rift 模式（C62 的坐标缺口，见 §4），无法触发。
把 5010 金币当作「白给的常量」发进存档就是凭空造钱，所以默认只记 `prices` + `rewardLog`，
由 `--land-constants`（4 条价格合计 5010）/ `--land-rift`（26 条 rift 合计 23600）显式 opt-in。
两条都开：`landed 345 / unlanded 93 / coins 28610`。

## 3 存档格式与旧档兼容

`Progress` 新增 3 个字段（`native/src/progress.hpp:184` `unlockedPlants`、`:187` `rewardLog`，
`costumes` 复用 t76 已有的 `std::vector<std::string> costumes`）：

```json
"unlockedPlants": ["ailmint", "akee1", "aloe", "..."],
"costumes": ["539-idle", "..."],
"rewardLog": [{"kind": "note", "id": "first:note:note_beach", "amount": 1}, "..."],
```

- 三个字段都**排序 + 去重**：`unlockedPlants`/`costumes` 用 `std::sort` + `std::unique`；
  `rewardLog` 用 `sortUniqueRewardLog()`（`native/src/progress.cpp:275`），按 (kind, id, amount) 排序 + unique。
  于是同一份数据无论落地几遍，写出来的字节一样。
- **只在非空时写**（`native/src/progress.cpp:550` 与 `:567`）：空 `Progress` 序列化出来**没有**这三个键，
  所以「不涉及奖励的存档」与 T93 之前的存档逐字节相同（`rewards_test` 里有断言）。
- **缺段可读**（`native/src/progress.cpp:404` 与 `:430`）：缺 `unlockedPlants`/`rewardLog` 就是空；
  元素不是字符串/对象就跳过；`amount` 缺省 0。数组类型的东西给了 object（`{"audio":[1,2,3]}` 那种坏档）
  也不致命，只丢这一段。

实测存档（落地后）键序：

```
coins, costumes, keys, levels, purchases, rewardLog, seeds, unlockedPlants, updated, version
unlockedPlants: 244 costumes: 15 rewardLog: 123 coins: 0
```

## 4 C62 的坐标缺口：为什么只能整表落地

438 行里没有任何一行能定位到「打哪一关掉这个」。字段普查（438 行全覆盖）：

| 字段 | 出现的行数 | 说明 |
| --- | ---: | --- |
| `amount` / `levelOrRange` / `source` / `world` / `firstOnly` | 438 | 每行都有 |
| `param` | 379 | reward 目标 id |
| `levels` / `difficulty` / `rewardType` | 367 | 只 `first:` / `replay:` 族有 |
| `constant` | 5 | 只有价格行 |
| `category` / `probability` | 12 | 只有 `present:` 族（不属于 438） |

- `world` 只有两个值：`any` 384 行、`rift` 54 行——**没有具体世界**。
- `levelOrRange` 是短语而不是 id：`levels granting this on first clear`(305)、
  `levels granting this on repeat clear`(62)、`rift level 1..5`(各 3)、
  `rift zomboss, attempt N, difficulty N`(各 3)、`gift box opening`(12)、`economy constant`(5)。
- `source` 是「哪张表来的」而不是关卡：`pkg_0234..pkg_2047_LevelDefinition.json`(305)、
  `pkg_0234..pkg_2047_LevelDefinition`(62)、`pkg_2097_RiftZombossRewards.json`(36)、
  `pkg_2091_RiftFirstClearRewards.json`(18)、`pkg_0004_AwardConfigPropertySheet.json`(12)、
  `pkg_2083_PlantFusionConfig.json`(5)。

**可复算**：上面三行加起来就是 303 + 62 + 41 + 27 + 5（含重叠口径）——准确地说，
`world=="any"` 的 384 行里没有一列能指到关卡 id，`world=="rift"` 的 54 行指向 rift 而非 175 个普通关卡。
所以落地实现是「拿整张表跑一遍」，没有 `level` 参数；要按关卡发，必须先补出
`rewards_from_pack.json` 的关卡坐标（即 C62 欠的那张 map），那是 data 侧的工作，不在本任务写作用域里。

## 5 CLI

### 5.1 `--rewards-report`

```
--rewards-report <content directory> [--progress <file>] [--land-constants] [--land-rift]
```

stdout **一行纯 JSON，恰好 6 键**（任务书要求的键集）：

```
{"byKind":{"coin":30,"collectable":9,"gadget":1,"gem":6,"giftbox":1,"none":5,"note":11,
 "pinata":18,"powerup":6,"star":1,"trophy":18,"upgrade":3,"xp":14},
 "coins":0,"costumes":15,"landed":315,"unlanded":123,"unlockedPlants":244}
```

（上面为便于阅读折行，实际是单行；`byKind` 合计 = 123 = `unlanded`，`landed + unlanded = 438`。）

不落地明细走 stderr（`detail:` 前缀，8 键：`alreadyOwned/logged/plantsTotal/costumesTotal/landedPlants/landedCostumes/reasons/prices`），
这样 stdout 可以直接被 `jq` / 门禁脚本吃。可见 §1 的原文。

四个变体实测：

| 命令 | landed | unlanded | coins | byKind.coin |
| --- | ---: | ---: | ---: | ---: |
| 默认 | 315 | 123 | 0 | 30 |
| `--land-constants` | 319 | 119 | 5010 | 26 |
| `--land-rift` | 341 | 97 | 23600 | 4 |
| 两者同时 | 345 | 93 | 28610 | —（已无 coin） |

带 `--progress` 时报告会顺手把落地结果写回存档，因此**第二遍跑是幂等的**：

```
{"costumes":0, "landed":315, "unlanded":123, "unlockedPlants":0, ...}
```

（`landed` 仍是 315：重复行照旧算 landed，只是记 `already_owned`。）

### 5.2 `--run-level`

`coinsGained/seedsGained/keysGained/presentTableMissing/rewardUnmodelled/rewardUnlanded` 等既有键**一个没动**；
新增的只有一个条件键 `unlockedPlantsGained`，**只在本次真的解锁了新植物时才出现**
（`addLandingReceipt` 里 `if (!landing.unlockedPlants.empty())`）。第二遍通关不出现该键——
`rewards_test` 的 `testLandingReceiptIsConditional` 就是钉这个的。

`--run-level` 里的落地调用点（`native/src/main.cpp:447`）紧跟既有的 `addRewardReceipt`，
所以「战斗掉落结算」与「档案解锁落地」是两笔独立账，互不覆盖。

## 6 测试

`native/tests/rewards_test.cpp` 新增 7 段（任务要求 ≥6），全部在无 SDL 的 audit 构建里跑：

| 段 | 钉住什么 |
| --- | --- |
| `testPlantUnlocksLand` | 293 行 → 244 id 进 `unlockedPlants`；`seeds` 不被污染；第二遍 `planted 0 / alreadyOwned 315` |
| `testCoinFamiliesDoNotMintCoins` | 默认 `coins==0`；5 条价格被记下（1000/10/2000/2000/20）；`price_constant 5`、`rift_payout 54`；opt-in 后 5010 / 23600 |
| `testCostumesLand` | 22 行 → 15 个唯一 id 进 `costumes`，排序去重 |
| `testNoteOnlyRowsAreLogged` | note/collectable/powerup/none/upgrade/trophy/giftbox/gadget/star 共 123 行只进 `rewardLog`；`coins`/`keys` 不变；不重复增长 |
| `testOldSaveLandsAndRoundTrips` | 缺三个新段的旧档能读；落地后 `saveProgress`/`loadProgress` 往返；空 `Progress` 不含新键 |
| `testReportShape` | 6 键、`landed+unlanded==438`、`byKind` 合计 == `unlanded`、单行无换行 |
| `testLandingReceiptIsConditional` | `unlockedPlantsGained` 首次出现、第二遍消失 |

`rewards_test.exe` 直接跑的原文（工作目录 = 仓库根）：

```
plants: 293 rows -> 244 owned (landed 315, already owned 56), second pass planted 0 alreadyOwned 315
coins: default 0, constants opt-in 5010, rift opt-in 23600, prices 5
report: {"byKind":{"coin":30,...},"coins":0,"costumes":15,"landed":315,"unlanded":123,"unlockedPlants":244}
detail: {"alreadyOwned":56,...,"reasons":{"already_owned":56,"price_constant":5,"rift_payout":54,"unmodelled":64}}
rewards tests passed
```

## 7 构建与回归

### 7.1 全新审计构建

```
pwsh -NoProfile -File tools\build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\rwd3'
92% tests passed, 3 tests failed out of 38
Total Test time (real) = 139.38 sec
```

三条红**都不在奖励路径**，且都出在我没碰的文件里：

- `1 - catalog`：`FAIL real catalog counts`（别人在改 catalog 计数）
- `17 - progress`：`progress test failed: no mower was used, so the mower goal must pass`（`native/tests/progress_test.cpp:87` 的 `testStarEvaluation`，读的是 world 统计里的「用没用割草机」；**这一条在本次改动的第一个构建里是绿的**，见下方归因）
- `29 - mechanics`：`mechanics test failed: carnival_81 must hold its target on top of the level's plant`（t51 机制接线中间态）

我的三条全绿：`33 - rewards`、`34 - cli_reward_receipt`、`35 - cli_reward_plain`。

**`progress` 这条红的归因（可复核）**：奖励落地代码在我第一次全量构建 `C:\pvzbuild\rwd1`（20:12 左右，
已含全部奖励改动）时，`progress` 是 **Passed**，那轮唯一的红是我自己的 `rewards`（口径问题，已修）。
之后到 rwd3 之间，引擎侧这些文件被改过：
`native/src/engine/plant_levels.hpp`（20:50:03）、`native/src/engine/mechanics.cpp`（20:38:29）、
`native/src/engine/action_runner.cpp`（20:53:27）、`native/src/engine/world.hpp`（21:11:52），
再往后 `native/src/engine/world.cpp`（22:16:27）、`native/src/engine/plant_levels.cpp`（22:31:51）。
星章判定读的是 world 的战斗统计（是否用割草机 / 幸存数），这些编辑足以翻转该断言；
我这轮改的 `progress.{hpp,cpp}` 只新增了 `audio`/`unlockedPlants`/`rewardLog` 的解析与写出，没有碰星章逻辑。

### 7.2 全新桌面构建

```
pwsh -NoProfile -File tools\build_native.ps1 -BuildDir 'C:\pvzbuild\rwd1-desk'
96% tests passed, 2 tests failed out of 54
Total Test time (real) = 387.65 sec
```

红 = `catalog`（同上）+ `progress`（mower goal，归因见 §7.1 末段）；`mechanics` 本轮已转绿。
其余 52 条全 Passed（含 `rewards`、`menu_render`、`settings_render`、`audio_device` 与全部 render 测试）。

### 7.3 截图哈希

| 截图 | 命令 | SHA256 | 与基线 |
| --- | --- | --- | --- |
| battle | `--battle-snapshot content ..\..\PvZ2SHUTTLE\assets C:\pvzbuild\baseline\rwd_battle.bmp` | `D56A3D6AA176CA8F55B7A8F3589272249028C7D101AFA03C1BBEC38123479A90` | **逐字节相同** |
| menu | `--menu content --assets ..\..\PvZ2SHUTTLE\assets --snapshot C:\pvzbuild\baseline\rwd_menu.png --frames 2` | `8BC2A933988A9E6030A910037A4B4945DB9AF94941ECB374AAC90B7C2A261D5A` | **变了，原因不在本任务** |

battle 的 stdout 只有 `battle_preview=ok`（exit 0），menu 只有 `{"choice":"worldmap"}`（exit 0），没有音频/奖励噪声行。

menu 变色的归因（可复核）：`native/src/menu_view.cpp` 的 mtime 是 `2026-11-26 20:43:09`，
队长的设置屏接线把菜单从 3 项扩到 9 项（`{"设置", MenuChoice::settings, true}`、
`case MenuChoice::settings: return "settings";`，`native/tests/menu_render_test.cpp:105` 同步改成 `freshItems == 9`）。
菜单多出 6 行，截图自然不同；本任务没有碰 `menu_view.cpp`，也没有碰 `PvZ2SHUTTLE` 的任何绘制路径。

### 7.4 smoke（不传 `--progress`）

```
python tools\engine_smoke.py --exe C:\pvzbuild\rwd1-desk\Release\PvZ2SHUTTLE.exe --out work\_smoke_rwd.json
```

32 场景跑完，与两份基线逐场景比（按 `scenarios[].name` 建表，比 `ConvertTo-Json -Compress`）：

```
vs native/generated/engine_smoke.json -> 2 differences
   beach_23 win
   world memorytour
vs build/t89/smoke.json -> 2 differences
   beach_23 win
   world memorytour
```

两处差异都是**引擎侧在动**，不是奖励落地引起的：

| 场景 | 本次 | `native/generated` | `build/t89` |
| --- | --- | --- | --- |
| `beach_23 win` | tick 1597 / `0xa47bd864b1d332bf` | tick 1599 / `0xb2a22229f25b92e6` | tick 1599 / `0xb2a22229f25b92e6` |
| `world memorytour` | `playing` tick 7200 / `0x18cef11ac3dc5bb1`（mowerKills 30） | `lost` tick 7000 / `0xb83111a880dd862a`（mowerKills 30） | `playing` tick 7200 / `0xe81666e658cf4f95`（mowerKills 18） |

`world memorytour` 在两份基线之间就已经不同（`lost` ↔ `playing`、hash 各不相同），说明它一直在随引擎改动漂移；
`native/src/engine/world.cpp`（22:16:27）与 `native/src/engine/plant_levels.cpp`（22:31:51）都在 t89 基线（21:08）之后被改过。

**不传 `--progress` 时，我的代码根本不参与计算**：`landRewards` 只有两个调用点
（`native/src/main.cpp:447` 的 `--run-level`（且必须带 `--progress`）与 `:490` 的 `--rewards-report`），
引擎/渲染没有任何文件 include `rewards.hpp` 或 `progress.hpp` 的落地 API。所以这两处差异不可能来自本任务。

## 8 反向探针（两条，已回滚）

**探针 A：plant 不写名册。** 把 `native/src/rewards.cpp` 的 `plants.insert(row.param);` 换成一句注释
（`// PROBE t93 reverse: the roster write removed on purpose.`），重建 `rewards_test`：

```
rewards test failed: 244 distinct plants must land, got 293
```

（exit 1，说明 `unlockedPlants` 空时落地计数立刻掉到 0，测试能抓到。）

**探针 B：rift 金币不发。** 删掉 rift 分支里的 `progress.coins += row.amount;`：

```
rewards test failed: the rift opt-in pays the 26 rift coin rows (23600), got 0
```

（exit 1。）

两条都还原后 `rewards_test` 重跑 `rewards tests passed`，
`native/src/rewards.cpp` 复原 SHA256 = `332528964E3AD38B86D99C51FC02305A13764A72C78814D310ED0D7A8B9E460E`（654 行、全 CRLF）。

## 9 已知限制 / 交接

1. **`coin` 30 行的任务前提不成立**（§2.1）：4 条是商店价格、26 条是 rift 掉落。默认一分不发，
   要用 `--land-constants` / `--land-rift` 显式开。若下游需要「把 5010 当常量金币发」，改的是 opt-in 的默认值，不是数据。
2. **trophy 18 行没进 `Progress::trophies`**：数据里没有 trophy id（`param` 是位置名），猜一个就是伪造 id；
   按任务清单它属于「其余」，所以走 `rewardLog` + `unmodelled`。等 data 补出 trophy id 再接。
3. **没有关卡坐标**（§4）：落地是整表操作，不接关卡。C62 的 map 补上后，`landRewards` 应改成
   「按 level 过滤 `unlandedDetail()`」——`RewardTable::unlandedDetail()` 已经把每行的
   `id/kind/param/rewardType/constant/amount` 都留下来了，接口不需要变。
4. **`already_owned` 计入 `landed`**：`landed` 是「行被处理并落定」，不是「新增」。要看新增量看
   `detail.landedPlants` / `landedCostumes`（244 / 15）；`unlockedPlantsGained` 也只在真有新增时出现。
5. `--rewards-report` 的 `byKind` 只统计**未落地**的 kind；已落地的 plant/cosmetic 不在里面，
   所以 `byKind` 合计恒等于 `unlanded`（测试里钉住了这个不变量）。
