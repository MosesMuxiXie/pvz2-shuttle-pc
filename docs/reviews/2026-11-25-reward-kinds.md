# 掉落产物落地：gem / plant / mower / xp / trophy（T77 / P1-8）

结论：五类里**两类真的能发**（`gem` 8 行里的 2 行 loot 行、`mower` 4 行全发），
一类是**另一个 kind**（`plant` 是解锁不是种子包，真正落地的是 `seed` 的 76 行，之前就在发），
两类**今天没有任何一行能从一场战斗里发出来**（`xp` 14 行全是裂隙槽位、`trophy` 18 行全是不指名关卡的首通奖励）。
因此本轮做的是：把能发的接上存档与回执，把发不了的补齐**存储形状 + fold 通路**，再用
`rewardUnlanded` 把 438 行读表即丢的行**显形**，让"445 行发不出去"这件事从口头说法变成回执里可核对的分项。

五类的存档字段与回执键全部落地，`--run-level --progress` 输出形如
`"gemsGained":0,…"mowersGained":0,…"plantsGained":0,…"trophiesGained":0,…"xpGained":0`，
不带 `--progress` 时与改动前**逐字节相同**（实测 518 B 单行，见 §6）。

---

## 1. 数据面：575 行是怎么分的

`native/generated/rewards_from_pack.json` 的 `rewards[]` 共 **575** 行，`RewardTable::readTable` 按形状分三档读入：

| 读入路径 | 判定 | 行数 | 结构 |
|---|---|---|---|
| `LootRow` | 行内带 `period` | 25 | `loot:<Type>:<lootKey>`，按击杀周期掉落 |
| `SeedDropRow` | `kind == "seed"` | 76 | 每关一个种子袋（`pkg_*_LevelDefinition` 前缀） |
| `PresentRow` | `id` 以 `present:` 开头 | 36 | 关卡末午餐盒表的 `Entries[]` |
| **丢弃（本轮改为计数）** | 其余 | **438** | `first:` / `replay:` / `rift-*:` / `giftbox:` / `constant:` |

`25 + 76 + 36 + 438 = 575`，这条闭合恒等式写进了 `testUnlandedCensus`（`137 + 438 == 575`）。
改动前 `readTable` 对最后 438 行**静默 `continue`**，所以"有多少行永远发不出去"没有任何运行时痕迹；
现在它在 `RewardTable::unlanded` 里按 kind 计数，并由 `addRewardReceipt()` 写进回执的 `rewardUnlanded`。

### 1.1 五类的行数与分布

| kind | 总行数 | 可落地行 | 分布 | 落地去向 |
|---|---|---|---|---|
| `gem` | 8 | **2** | loot 2（`loot:Gem1:any` period 30、`loot:Gem2:any` period 40，amount 2、range [2,2]、pickup `gem_diamond`）＋丢弃 6（giftbox 1 + rift-clear 5） | `Progress::gems` |
| `plant` | 293 | **0** | `first:unlock_plant:<plant>` 244 + `replay:unlock_plant:<plant>` 49，`amount: null` | ✗（`plant` ≠ 种子包；见 §3.2） |
| `mower` | 4 | **4** | loot `loot:LawnMower1..4:any`，period 20/20/30/30，amount 1、range [1,1]、pickup `lawn_mower` | `Progress::mowers` |
| `xp` | 14 | **0** | `rift-boss:a<attempt>:d<diff>:2:plantXP` 9 + `rift-clear:*` 5 | ✗（无裂隙模式/无 attempt·difficulty 输入） |
| `trophy` | 18 | **0** | `first:worldtrophy\|worldkey\|dangerroom:<param>`，`amount: null`、`firstOnly: true`、`levels ∈ {1,2,4}` | ✗（行内不指名关卡） |

`mower` 的 4 行是**全发**的（`60` 击杀 → `3+3+2+2 = 10`）；`gem` 只有 2 行（`60` 击杀 → `30` 周期 2 次 + `40` 周期 1 次，每次 2 颗 = `6`）。
这两条数值被 `testGemMowerLand` 锁死。

### 1.2 之前就在发的部分（不在本任务范围，但报表要能对上）

任务书说的"130 行真正发得出去（coin 46 / key 8 / seed 76）"里，`coin 46` 是
`loot` 8 + `present` 8 + **丢弃的 30 行**；`key 8` 是 loot；`seed 76` 是种子袋。
本任务之后，可落地行从 130 变成 **136**（多 `gem` 2 + `mower` 4），
读表即丢的 438 行不变、但可核对，结算期 `reward_unmodelled` 只剩真正没有字段的家族（sprout、whack sun）。

---

## 2. 字段来源

| 目标字段 | 数据来源 | 具体字段 |
|---|---|---|
| `Progress::gems` | `LootRow{kind=="gem"}` | `amount` × `drops`，`drops = killedZombies / period` |
| `Progress::mowers` | `LootRow{kind=="mower"}` | 同上（`amount` 恒 1） |
| `Progress::seeds` | `SeedDropRow` | 关卡的种子袋 `candidates[]`（概率 × 击杀） |
| `Progress::xp` | `RewardGain::xp` | 目前无数据来源（14 行 xp 全是 rift 槽位），只保证 fold/序列化 |
| `Progress::trophies` | `RewardGain::trophies` | 同上（18 行 trophy 全是首通、不指名关卡） |
| `rewardUnlanded[]` | `RewardTable::unlanded` | `readTable` 丢弃分支按 `kind` 累加 |

`LootRow::appliesTo()` 是既有语义，本轮确认没有改动：`lootKey` 为空或 `"any"` 的行**在全世界都掉**，
其余按 `LevelLootKey` 精确匹配。`gem`/`mower` 行的 `lootKey` 是 `any`，所以**没有 loot key 的 33 关也会掉**；
`coin` 行是 `default`，`key` 行走 `Egypt3` 门。这条差异被 `testUnmodelledKinds` 的"空 loot key"分支固定住
（`coins == 0 && keys == 0` 而 `gems == 6 && mowers == 10`）。

---

## 3. 语义判断（逐类）

### 3.1 `gem` → 货币计数
行内 `amount: 2`、`amountRange: [2,2]`、`pickup: gem_diamond`，是关卡内拾取物兑换的硬通货。
`Progress::gems` 早在 P1-9 之前就存在（`progress.json` 的唯一"只写非默认值"字段之一），直接累加即可，
`delta = after - before` 即真实增量。

### 3.2 `plant` → **不是**种子包（本任务最大的口径纠正）
293 行全部是 `first:unlock_plant:<plant>`（244）与 `replay:unlock_plant:<plant>`（49），`amount: null`，
语义是"首通/重玩**解锁**某植物"，不是"给你一包种子"，而且**行内无关卡 id**，无法绑定到某一场战斗。
真正的种子包是 `kind == "seed"` 的 76 条 `SeedDropRow`（本任务前就在 `Progress::seeds` 落地）。
因此本轮 `plant` **不进** `Progress::seeds`：如果硬塞，会把 293 个解锁当成 293 包种子，
存档里凭空多出 244 个植物——这是可验证的错误，不是保守。回执里 `plantsGained` 的语义因此明确写成
"种子袋新增的种子 id 数"（`delta.plants`），`unlanded.plant = 293` 单独可查。

### 3.3 `mower` → 额外割草机备件库存（不是"修复"）
4 行的 `pickup` 是 `lawn_mower`（关卡内可拾取的割草机），`amount: 1`、无 `value`/`repair` 字段，
`mapping: inferred-name-convention`。存档是 `{row, col}` 之外的全局量，无法表达"修哪一条道"，
所以 `Progress::mowers` 记的是**数量**，语义 = 备件库存（下一场开局多带几台），**不是** repair 标记。
这个判断写在 `progress.hpp` 的字段注释里，避免下一个人再猜一次。

### 3.4 `xp` → 累计值
14 行全是裂隙（`rift-boss:a<attempt>:d<diff>` 9 行、`rift-clear:*` 5 行）。内核没有裂隙模式，
也没有 attempt/difficulty 输入，所以**没有任何一行能在一场普通战斗里发出来**。
本轮只补 `Progress::xp`（累计计数）与 fold，`gemsGained` 式的回执键固定出现（值为 0），
等 rift 落地时不需要再动存档形状。

### 3.5 `trophy` → 拥有集合（排序去重）
18 行全部 `firstOnly: true`，参数是 `worldtrophy_*` / `worldkey_*` / `dangerroom_*`，
`levels ∈ {1,2,4}`，**行内没有关卡 id**（编译器聚合首通奖励时把关卡丢了）。
`Progress::trophies` 是 `std::vector<std::string>`，parse/apply 两处都 `sort + unique`，
重复拥有不算第二次 gain（`testXpAndTrophyFold` 断言第二次 `delta.trophies == 0`）。

---

## 4. 代码改动面

| 文件 | 改动 |
|---|---|
| `native/src/progress.hpp` | `Progress` 增 `int mowers`、`int xp`、`std::vector<std::string> trophies`（含语义注释） |
| `native/src/progress.cpp` | `parseProgress` 读三个新字段（trophies 去空串 + sort/unique）；`progressToJson` 只在非默认值时写（`mowers != 0`、`xp != 0`、`trophies` 非空），**老存档字节形状不变** |
| `native/src/rewards.hpp` | `RewardGain` 增 `gems/mowers/xp/trophies`；新增 `RewardDelta`（`coins/keys/gems/mowers/xp/plants/trophies`，全部 after−before）；`applyRewards` 改返回 `RewardDelta`；新增 `addRewardReceipt()`；`RewardTable` 增 `unlanded` 与 `unlandedRows()` |
| `native/src/rewards.cpp` | `readTable` 丢弃分支改成 `++table.unlanded[kind]`；`settleRewards` 的 loot 循环加 `landable` 判定与 gem/mower 分支；`applyRewards` 记 before/after 并返回 delta；新增 `addRewardReceipt()`（五个 `*Gained` + `rewardUnlanded`）；`RewardGain::empty()/json()` 覆盖新字段 |
| `native/src/main.cpp` | 只在 `if (progressPath)` 块内：接 `RewardDelta` 并在末尾调 `addRewardReceipt()`；块外一行未动 |
| `native/tests/rewards_test.cpp` | 改写 `testUnmodelledKinds`，新增 8 个用例（见 §7） |
| `native/CMakeLists.txt` | 注册 `cli_reward_receipt`（PASS_REGULAR_EXPRESSION 五个键）与 `cli_reward_plain`（FAIL_REGULAR_EXPRESSION `Gained`） |

`coinsGained` / `keysGained` / `seedsGained` / `presentTableMissing` / `rewardUnmodelled` 五个**旧键语义与位置未动**，
新键是**增量**（去重后真实到账），因此同一场里 `seedsGained`（掉落数）与 `plantsGained`（新增种子 id 数）
可以不同——这正是要表达的差异，不是不一致。

---

## 5. 回执形状（实测，frontyard_1 9 击杀失败局）

```
"gemsGained":0,"mowersGained":0,"plantsGained":0,"trophiesGained":0,"xpGained":0,
"rewardUnlanded":[{"count":30,"kind":"coin"},{"count":9,"kind":"collectable"},{"count":22,"kind":"cosmetic"},
  {"count":1,"kind":"gadget"},{"count":6,"kind":"gem"},{"count":1,"kind":"giftbox"},{"count":5,"kind":"none"},
  {"count":11,"kind":"note"},{"count":18,"kind":"pinata"},{"count":293,"kind":"plant"},{"count":6,"kind":"powerup"},
  {"count":1,"kind":"star"},{"count":18,"kind":"trophy"},{"count":3,"kind":"upgrade"},{"count":14,"kind":"xp"}],
"rewardUnmodelled":[{"count":1,"kind":"sprout"}]
```

`rewardUnlanded` 合计 **438**（15 个 kind，按 kind 升序），`rewardUnmodelled` 里只剩 `sprout`（本局 sprout 周期 5 触发 1 次）。
两个键分工明确：`rewardUnlanded` = **表里读进来就发不了**的行（静态、与战局无关）；
`rewardUnmodelled` = **本局掉了但没字段**的行（动态、与击杀数有关）。

## 6. 不带 `--progress` 的输出没变（实测，不是推断）

同一份 `frontyard_1` 剧本，取"改动前的 `main.cpp`"编出的 exe 与"本轮改动后"的 exe 各跑一次：

```
new  exit=0 bytes=518
build old exit=0
old  exit=0 bytes=518
IDENTICAL
restore build exit=0
```

两次 stdout **逐字节相同**（518 B，单行 nlohmann dump），因为新增语句全部在 `if (progressPath)` 内。
`cli_reward_plain` 用 `FAIL_REGULAR_EXPRESSION "Gained"` 把这条钉在 CI 里：一旦有人把回执键挪出
`--progress` 分支，这个用例立刻红。

---

## 7. 测试与反向探针

`native/tests/rewards_test.cpp` 现在 18 个用例，本轮新增/改写 9 个：

| 用例 | 断言 |
|---|---|
| `testUnmodelledKinds`（改写） | gem/mower **不再** unmodelled；sprout 仍 unmodelled；空 loot key 只停 coin |
| `testGemMowerLand` | 60 击杀 → `gain.gems == 6`、`gain.mowers == 10`；fold 后 `progress.gems/mowers` 与 `delta` 一致；回执同值 |
| `testGemMowerDeltaIsHonest` | 存档已有 4 钻/2 割草机时，delta 仍是 6/10（不是累加值） |
| `testPlantUnlockIsNotASeedBag` | `unlanded.at("plant") == 293`；种子进存档算 1，重复不再算 |
| `testXpAndTrophyFold` | xp 累加；trophy 排序去重、重复拥有不算 gain |
| `testReceiptShape` | 只有五个 `*Gained` + `rewardUnlanded`（不抢 `coinsGained` 等旧键）、`rewardUnlanded` 按 kind 升序 |
| `testUnlandedCensus` | 438 总计 + 分项（plant 293 / cosmetic 22 / trophy 18 / xp 14 / note 11 / collectable 9 / gem 6）+ `137 + 438 == 575` |
| `testNewSaveFieldsRoundTrip` | 三字段写入/读回；**空存档不出现这三个键**；重复 trophy id 加载时折叠 |
| `testSeedBagReachesTheReceipt` | 种子袋 5 次掉落 → 存档去重 → `delta.plants == 唯一 id 数` → 回执同值 |

三条 ctest（`build\native`，Release）：

```
1/3 Test #25: rewards ............. Passed  1.81 sec
2/3 Test #26: cli_reward_receipt .. Passed  1.55 sec
3/3 Test #27: cli_reward_plain .... Passed  1.33 sec
100% tests passed, 0 tests failed out of 3
```

回归（Progress 序列化/存档/世界地图/商店/CLI 审计）：`catalog worldmap cli_audit save_import progress flow shop`
→ **7/7 passed**（10.93 s）。

### 反向探针（各删一处存档增量 → 对应测试红，原文如下）

做法：临时删掉 `applyRewards` 里那一种 kind 的写回，重建 `rewards_test`，跑 `ctest -R ^rewards$`，记录首条失败；随后还原并重建。

| 探针 | 删掉的行 | ctest 输出（原文） |
|---|---|---|
| gem | `progress.gems += gain.gems;` | `rewards test failed: the save holds the gems, got 0` |
| mower | `progress.mowers += gain.mowers;` | `rewards test failed: the save holds the mowers, got 0` |
| xp | `progress.xp += gain.xp;` | `rewards test failed: xp accumulates, got 0` |
| plant（seed 包） | `progress.seeds.insert(...gain.seeds...)` | `rewards test failed: seeds stay sorted and unique` |
| trophy | `progress.trophies.insert(...gain.trophies...)` | `rewards test failed: trophies stay sorted and unique` |

五条全红，还原后 `RESTORED exit=0`。每条失败信息都指向具体 kind，不需要看日志上下文。

---

## 8. 仍然发不出去的 438 行（清单与原因）

按 `rewardUnlanded` 实测分项（15 个 kind）：

| kind | 行数 | 为什么发不出去 |
|---|---|---|
| `plant` | 293 | `first:`/`replay:` 的 `unlock_plant`，`amount: null`、行内无关卡 id（编译器丢关卡） |
| `coin` | 30 | 同上族（`first:`/`replay:`/`rift-*`），coin 的落库通路已有，缺的是"哪一关的首通" |
| `cosmetic` | 22 | 首通外观，无存档字段（`costumes` 是另一套 id 空间，未对齐） |
| `pinata` | 18 | 首通/裂隙皮纳塔，无"下一次开箱"载体 |
| `trophy` | 18 | `firstOnly` + `levels ∈ {1,2,4}`，行内无关卡 id |
| `xp` | 14 | 全 rift 槽位（`a<attempt>`/`d<diff>`），无裂隙模式与输入 |
| `note` | 11 | 文案行，不是产物 |
| `collectable` | 9 | 裂隙收集品，无背包 |
| `gem` | 6 | giftbox 1 + rift-clear 5：有字段，缺"开箱/裂隙结算"入口 |
| `powerup` | 6 | 首通能力，无等级/解锁位 |
| `none` | 5 | 空产物（占位行） |
| `upgrade` | 3 | 升级行，无升级表落地 |
| `star` | 1 | 星星已由 `recordBattle` 走星表计算，不从这里发 |
| `giftbox` | 1 | 同上（开箱入口未接） |
| `gadget` | 1 | 小游戏道具，无存档位 |

另有**结算期**仍走 `reward_unmodelled` 的两类：`sprout`（5 行 loot，关卡内掉落，无字段）与
`sun`（2 行 loot，属 whack 小游戏；普通关卡里不会命中，`testUnmodelledKinds` 断言其为 0）。

要让 `plant`/`trophy` 家族真正落地，缺的不是存档字段而是**数据**：`content/levels/*.json` 的 `extra`
只有 `source/package/stage/name_key/level_number/wave_count/original_waves/night/minecarts/rail/boss/
boss_zombie/special/vasebreaker/suppressFlagZombie`，没有 FirstReward / worldtrophy / unlock_plant
（`grep worldtrophy|unlock_plant|FirstReward|first_reward` 命中 0）。也就是说 305 行 `first:` + 62 行 `replay:`
**在客户端资产里没有关卡坐标**，需要用 OBB 侧的 `LevelDefinition.objdata` 首通字段重建（另一条工作流），
不是本任务能在 `native/` 里解决的。

---

## 9. 踩坑

1. **`plant` 差点被当成种子包**：293 行里 `unlock_plant:` 的命名很像"给种子"，但 `amount` 是 `null`、
   行内无关卡 id。硬塞会让 244 个首通解锁变成 244 包种子（存档凭空膨胀），已在 §3.2 定死口径。
2. **`LootRow::appliesTo` 对空 loot key 的行为**：第一版断言写"空 loot key 停掉所有周期行"，实测
   `gems = 6`——因为 `gem`/`mower` 行的 `lootKey` 是 `any`。改成"只停 coin（`default`）与 key（Egypt3 门）"，
   并把 `any` 语义写进注释：这解释了"为什么没有 loot key 的 33 关照样掉宝石"。
3. **`seedsGained` 与 `plantsGained` 不是一个数**：前者是掉落次数（含重复候选），后者是去重后新增 id 数。
   两个都保留，报告与注释都写明，避免下一个人把它们当重复字段删掉。
4. **`rewardUnlanded` 与 `rewardUnmodelled` 容易混**：前者静态（读表即丢 438 行），后者动态（本局没字段的掉落）。
   两个键名字都保留，回执里并排出现，`testUnlandedCensus` 与 `testUnmodelledKinds` 各钉一头。
5. **Windows 共享目录写入抖动**：`edit`/`write` 偶发 `ReplaceFileW EIO (Win32 32)` 或 Python `PermissionError`，
   需重试；本次用"重试 N 次 + 每次 0.5 s"的写法完成所有文件改动与探针脚本。
6. **`native/CMakeLists.txt` 在并行队友手里被改坏过**：18:03 那次 configure 报 `Flow control statements are
   not properly nested`（`if(PVZ_ENABLE_DESKTOP)` 缺 `endif()`），我的构建因此失败两轮；等对方落盘后才通过。
   本轮在该文件里只追加了 §7 的两条 ctest，未动既有分支。

---

## 10. 复现

```powershell
$cmake = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
$ctest = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\ctest.exe"
& $cmake -S native -B build\native
& $cmake --build build\native --target rewards_test PvZ2SHUTTLE --config Release
& $ctest --test-dir build\native -C Release -R "^rewards$|^cli_reward" --output-on-failure

# 回执长什么样
build\native\Release\PvZ2SHUTTLE.exe --run-level content frontyard_1 `
  --script native\tests\scripts\frontyard_1_basic.json --progress "$env:TEMP\save.json"
```

## 11. 范围声明

只改 `native/src/rewards.{hpp,cpp}`、`native/src/progress.{hpp,cpp}`、`native/src/main.cpp`（结算输出）、
`native/tests/rewards_test.cpp`、`native/CMakeLists.txt`（新测试注册）与本报告。
未改 `content/**`、`native/generated/**`、`tools/**`，未 commit。
