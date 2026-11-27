# A1 · 砸罐子玩法进引擎（T80）

日期：2026-11-26
任务：t80 — `content/levels` 里 `extra.vasebreaker = true` 的 **47 关**真正能玩：敲罐、出怪、收物、清空即胜。
数据源：`native/generated/vasebreaker.json`（186,021 B，sha256 `F4F29CBFA31B33746086C619DC2C31FD2D5CBC6DE210C3738C4D1A28A5B65FFB`）。
结构说明先行版见 `docs/reviews/2026-11-25-vasebreaker-data.md`。

## 1. 一句话结论

47 关里有 **46 关** 的罐表是完整的，照着表就能开局铺满（第 47 关 `frontyard_166` 在原版里就没有固定罐表，见 §9）。引擎侧新增 `engine::VaseTable`（只读）+ `World::breakVase()`，`battle_view` 点罐即敲，清空且场上无僵尸即 `won`。**逐罐坐标和罐内阳光数量原版没给**，这两条是按固定种子做的确定性推断，规则写在 §3、§4。

## 2. 数据长什么样（实测，不是猜）

`vasebreaker.json` 顶层：`counts / format(=1) / generated / levels(47) / sources / unknowns(7)`。`levels` 是 **dict**（键 = 关卡 id），每关：

```
blacklistedCells, byType, coloredVases{plant,zombie}, columnRange{min,max}, endless,
entryCount, excludedCells[[a,b],…], initialSun, isVasebreaker, lastStand, levelFile,
levelId, levelNameKey, levelNumber, levelPowerupSet, modules[], preset{}, seedBank[],
seedBankInfo, sourceFiles[], stageModule, tide{startingWaveLocation}, timeLimit,
unknowns[], vaseCount, vaseGridItemType, vases[]
```

`vases[]` 每条形如：

```
{col: null, collectableType, count, plantId, row: null, sunAmount: null,
 type: "zombie"|"plant"|"collectable", zombieId}
```

关键实测数字：

| 项 | 值 |
| --- | --- |
| 关卡数 | 47 |
| `counts.vaseTotal` | 1435（**= 所有 `count` 之和**，我逐关加过，一致） |
| 罐条目数 `entryTotal` | 459 |
| 条目里 **带坐标** 的 | **0 条**（`row`/`col` 全 null） |
| `byType` | zombie 788 / plant 617 / collectable 30 |
| collectable 的种类 | **只有 `plantfood`**（30 条），没有任何阳光罐 → `sunAmount` 只能 null |
| 排除格 `excludedCells` | 5 关有，写法是 `[col, row]`（见 §3） |
| `vaseGridItemType` | 3 关是 `vase_firework` |

`counts.unknowns` 里原版自己承认缺的东西：`vasePlacement 46`、`sunAmount 46`、`timeLimit 47`、`initialSun 43`、`seedBank 39`、`preset 1`、`endless 1`。这正是 §9 的清单来源。

关卡侧核对：`content/levels/*.json` 里 `extra.vasebreaker` 为真的正好 **47 关**，与表键**一一对应，无缺无多**。这些关的 `waves` 不是 0（例如 `beach_69` 有 8 波合成波），所以引擎必须**关掉波次导演**，否则 `allSpawned()` 永远不成立、清空即胜不可达（§5）。

## 3. null 坐标怎么落地（确定性规则）

数据没有逐罐坐标，只有「列带 `columnRange` + 排除格 + 每关罐数」。落地规则：

1. 取该关的棋盘行列（`board_sizes.json`：`beach` 是 **6×9**，其余多为 5×9）。
2. **band** = 列落在 `[minColumn, maxColumn]` 且**不在** `excludedCells` 里的所有格。
3. **spill** = 棋盘上其余的所有格。
4. band 与 spill 各自用 `std::mt19937`（种子 `seed ^ 0x51ed270b`）做 Fisher–Yates 洗牌。
5. 先按 band 顺序取格，取完再按 spill 顺序取格；每个 `entry` 按 `count` 重复摆罐。
6. 格不够时**不静默丢**：`vasesUnplaced()` 计数 + `vase_unplaced` 事件（47 关按现规则跑下来是 0）。

> **`excludedCells` 的元组顺序是 `[col, row]`**（原版 `{mX, mY}`）。按 `[row, col]` 读会让 `beach` 的 6 个排除格越界（beach 只有 6 行），按 `[col, row]` 读越界 0 —— 代码里存成 `(row, col)`。

**列带装不下**的 4 关：`egypt_57`（列 4..6 只有 15 格却要 30 罐）、`future_54`（35 格要 37）、`future_65`（35 要 36）、`heian_28`（35 要 37）。这 4 关靠 spill 溢出到列带外，仍在棋盘内，不特殊处理、不缩罐数。

同一关同一 `seed` → 同样的罐位、同样的 `hash()`；换 `seed` → 罐位变（`vase_test` 的 `testVaseLayoutFollowsTheSeed` 钉住这一点）。这样回放/冒烟才有可比性。

## 4. 罐子里的四类内容怎么处理

`World::breakVase(row, col)` 返回 `VaseBreak{ok, kind, value, sun}`：

| kind | 行为 | 事件 |
| --- | --- | --- |
| `zombie` | `spawnZombieAt(payload, 罐所在行, centerOf(col))`；类型名来自表（`tutorial`/`pirate_gargantuar`/`dark`…） | `vase_spawn_zombie{zombie,row}`（失败另发 `vase_zombie_rejected`） |
| `plant` | 变成一张**可拾取卡** `VaseCard{plant,row,col}`，手牌里带着它 | `vase_pickup{kind:"plant",value}` |
| `collectible` | `plantfood` 只记账（**不折算阳光**，原版没给数值） | `vase_pickup{kind:"collectible",sun:0}` |
| `sun` | `sun_ += amount`（`kVaseSunValue = 25`，调参常量，**不是**表数据） | `vase_pickup{kind:"sun",sun}` |
| 任何成功 | 罐置 `alive=false`，`vaseTally().broke++` | `vase_broken{row,col,kind,value}` |

拿到的植物卡用 `plantVaseCard(index, row, col)` 种下：只能种在**罐所在格或相邻空格**（曼哈顿距离 ≤ 1，否则 `"too far from its vase"`），格被占则 `"cell occupied"`，种下**不扣阳光**（`sunSpent` 不变，有测试）。

`breakVase` 对已经敲开的格子返回 `ok=false` 并且**不再发任何事件**（幂等，测试钉住）。

## 5. 砸罐子关的引擎形态

`WorldOptions::vasebreaker`（缺省开）。关卡 `extra.vasebreaker` 为真且表里有该关时：

* **不铺草坪、不跑波次导演、不天降阳光**：`step()` 里 `tickWaves/tickSpawners/tickSkySun` 整段跳过 —— 原因见 §2（否则永远赢不了）。
* `plant()` 直接返回 `"no seed bank"`（没有种子库，也没有阳光消耗）。
* **不叠初始植物/网格物件**：`layInitialField()` 跳过（罐子关的场地只有罐）。
* 胜利：`resolveOutcome()` 里 dedicated 分支 —— `vases_` 空 且 `pendingSpawns_` 空 且 `zombies_` 空 → `won` + `level_won`。被吃穿仍走既有 `lost` 路径。
* 表里没有该关（`frontyard_166`）：**降到普通关**，并发 `vase_unavailable{level,reason:"no vase preset",table}` —— 不静默变成空棋盘。
* `vasebreaker=false`（测试用）→ 完全回到普通关：种子库可用、无罐、无 `vase_field_laid` 事件。

`hash()` 只在砸罐子模式下追加 `V<id,row,col,content,payload,amount>; K<plant,row,col>; Q<vaseRng>`，普通关的哈希序列**逐字节不变** —— 这也是冒烟只有 1 条差异的前提。

## 6. CLI 证据（`--run-level` 原文片段）

只有开局真有罐的关才带 `vasebreaker` 键（其他关键集逐字不变）：

```
beach_69  → "rows":6,"status":"playing","sun":550,"tick":1800,...,"vasebreaker":{"broke":0,"collectibles":0,"plants":0,"sun":0,"total":30,"zombies":0},"waves":0
egypt_57  → "rail":{"carts":4,...},"vasebreaker":{...,"total":30,...},"waves":0
kongfu_83 → "mechanicUnknown":[{"count":1,"kind":"spawners.grid.unscheduled",...}],"vasebreaker":{...,"total":5,...}
frontyard_1 → 无 "vasebreaker" 键（键集不变），"spawned":2,"waves":1,"sun":150
```

## 7. 测试：`native/tests/vase_test.cpp`（11 段，全绿）

1. `testTableShape` — 47 关 / 总罐 1435 / `beach_69` 30 罐 12 条 / 列带 2..8 / 5 个排除格 / `frontyard_166` 空 / `frontyard_1` 不在表里。
2. `testVasesCoverTheBoard` — 4 关：摆满 `total`、不越界、不叠格、不占排除格、`vasesUnplaced()==0`。
3. `testVaseLayoutFollowsTheSeed` — 同种子同布局同 hash，异种子不同。
4. `testBreakVaseIsIdempotent` — 首敲 ok，二次 `ok=false`，`broke==1`，`vase_broken` 只 1 次，step 后罐消失。
5. `testZombieVaseSpawnsInItsRow` — 僵尸落在**罐所在行**，事件 1 次，tally 对。
6. `testPlantVaseCardPlantsNextToItsVase` — 远处报 `too far from its vase`；原地种下不花阳光。
7. `testSunVasePaysSun` — 用临时表注入 2 个阳光罐（真表里没有阳光罐），验证入账与事件。
8. `testVaseLevelHasNoSeedBank` — `plant()` 返回 `"no seed bank"`；900 步内没有天降阳光。
9. `testClearingEveryVaseWins` — `egypt_57` 敲光 30 罐后仍 `playing`（还没结算），跑满 tick → `won` + `level_won`。
10. `testOrdinaryLevelIsUntouched` — `frontyard_1` 无罐、`snapshot.vases` 空、照常种花。
11. `testSwitchingTheModeOffKeepsTheSeedBank` — `vasebreaker=false` 回到普通关。

两条反向探针（跑过、已还原）：

```
A) resolveOutcome 的 vase 分支首行插 `return; // PROBE_T80A`
   → vase test failed: clearing every vase with no zombies left must win, got: playing

B) breakVase 的 find_if 谓词去掉 `vase.alive`
   → vase test failed: a second tap on the same cell must be a no-op
```

还原后 `vase tests passed`，`native/src/engine/vase.cpp` sha256 `2F3E43ABFD1D83D333B1F5C314CA7D725D4EE147E4515B953B576EAF0ECC38EB`，源码里探针标记 0 命中（`PROBE_T80` 这个词只出现在本文档的描述里）。`native/src/engine/world.cpp` 在还原当时是 `9AE15405CD398CE653AA83885EC3F27ABC1D239966EEFACE7679451EF1292001`；之后 A2 把 `layRailCarts()` 合进同一个文件，当前值已变成 `201CFAAC269CFA5C5FE78AE5B7EAAD50FB53788652B6F5931426CA4A18AC50B1`（不是我的改动）。

## 8. 门禁

| 门 | 结果 |
| --- | --- |
| **audit 全量**（`pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir C:\pvzbuild\vase1-aud`） | **`100% tests passed, 0 tests failed out of 36`**，其中 `#30 vase ... Passed 2.29 sec`，`AUDIT_ONLY_EXIT=0` |
| `vase_test`（单跑） | `vase tests passed`，EXIT=0 |
| `mechanics_test` | `mechanics tests passed`，EXIT=0 |
| `battle_drag_test` | `battle drag tests passed`，EXIT=0 |
| desktop `PvZ2SHUTTLE`（`vase1-desk`） | 构建 EXIT=0（点罐/罐子绘制/HUD 分支编译通过） |
| 冒烟 32 场景 | **1 条差异**（见下） |

> 说明：`-AuditOnly` 之前（18:10 那一次）整树编不过，红在别处的 `achievements_test.cpp`/`daily_test.cpp`（`pathUtf8`）以及未注册的 `rail.cpp`；这两件都被它们的主人修好了，所以 19:59 这次能整棵 audit 跑完 36/36。
>
> **桌面全量**（含全部渲染测试）两次都停在**别人的在飞工作**上：第一次是 `native/src/shop_view.cpp(280) 'saveScreenSnapshot'` / `(328) 'SDLK_q_renamed_SDLK_Q'`；紧接着 `native/src/main.cpp` 被 daily 分支的作者改成调用 `pvz::DailyOptions` / `pvz::loadShipped` / `pvz::renderDailyHeadless`，而 `native/src/daily_view.hpp` 当时还没声明这三个符号（`main.cpp:926-929` 一串 C3861/C2039）。`main.cpp` 这一行不是我加的 —— 我最后一次改它是 18:00 之前，文件 mtime 20:10:53。
>
> 我的部分不受影响，有两层证据：① `battle_view.cpp` 用 `cl /c /utf-8` 单 TU 编译 EXIT=0（无告警）；② 18:55 那次 `PvZ2SHUTTLE` 目标链接 **EXIT=0**，§8 的截图就是这个二进制产出的。桌面**全量**门禁要等 daily 分支落地后由它们的作者跑通。

**冒烟唯一差异不是我的**：`world cowboy` `0xeb036737659cbc46 → 0xcb83dd8dcba537f5`（tick/status 不变）。`cowboy_1` 的 `extra` 是 `"minecarts":[2],"rail":true` —— A2 的 `layRailCarts()` 这次进了 `pvz_engine`。直接证据：用 T66 的老二进制（`C:\pvzbuild\spawn1\Release\PvZ2SHUTTLE.exe`，rail 之前）跑同一条命令，得到**基线原值** `0xeb036737659cbc46`；新二进制 `0xcb83dd8dcba537f5`。冒烟场景里没有任何砸罐子关（32 个场景全是世界首关 + 3 个固定关），所以 t80 没有改变任何既有场景。

**截图（headless）比对**，pre-t80 桌面二进制 = `spawn1-desk`（2026-11-25 18:32），post = `vase1-desk`：

| 画面 | pre | post | 结论 |
| --- | --- | --- | --- |
| `--menu --frames 2` | 35899 B `6B22F40F…48EDB` | 同 | 一致 |
| `--play-script frontyard_1 --seconds 1` | `43644483…20D37` | 同 | 一致 |
| `--play-script frontyard_1 --seconds 30` | `EDF5A2AB…D1F6D` | 同 | 一致 |
| `--play-script kongfu_1 --seconds 20` | `FCE15C5C…6867D` | 同 | 一致 |
| `--play-script beach_69 --seconds 1`（砸罐子） | 无（该关本来只是空草坪） | `2F51E04D…D035ED0` | 新增罐位画面 |

`--battle-snapshot` **不适合当不变性门槛**：它跑的是带 `SDL_Delay` 的 demo，同一二进制连跑 5 次会出 3 个不同哈希（老二进制 `{668B…×2, D56A…×3}`，新二进制 `{668B…×1, D56A…×3, E561…×1}`），历史基线 `D56A3D6A…` 两边都在。要钉画面请用 `--play-script ... --seconds`（确定性）。

## 9. 没做 / 做不到的（诚实边界）

* **逐罐坐标**：原版没给（459 条全 null），只能按 §3 规则推断；因此**和原版的具体摆位不会逐格一致**，只能保证同种子可复现。
* **`sunAmount`**：原版没给；`kVaseSunValue = 25` 是调参常量，真表里也没有任何阳光罐（30 条 collectable 全是 `plantfood`）。
* **`timeLimit`（47 关全部声明）**：没有接入 —— 没有「超时判负」。
* **`endless`（1 关）/ `lastStand`（1 关）/ `preset` 变体 / `tide`**：未接线。
* **彩色罐 / `vaseGridItemType = vase_firework`**：字段读了但没用起来，罐一律同色；`vase_firework` 缺网格物件实体。
* **`pirate_41`**：原版是 Boss + 传送带的砸罐子关，这里只当普通砸罐子关跑（35 罐全僵尸）。
* **美术**：罐子是棕色方块 + 瓶颈细条（没有罐子模型），植物卡也只显示在手牌计数里，`battle_view` 的 HUD 在砸罐子模式把种子库换成「砸罐子」提示行。
* **`frontyard_166`**：`withoutPresetIds` 里唯一一关，数据没有罐表 → 降级成普通关并发 `vase_unavailable`。

## 10. 这一轮踩到的外部阻塞（都已申报，不是我改坏的）

1. `native/CMakeLists.txt` 一度没注册 `src/engine/rail.cpp`，`world.obj` 未解析 `RailTable::shared/find`，连锁 20+ target 链接失败 —— A2 随后注册（现在 :86），我的 `src/engine/vase.cpp` 在 :87。
2. `achievements_test.cpp:329` / `daily_test.cpp:257` 用了未声明的 `pathUtf8` → 整棵测试树编不过，只能单 target 构建验证。
3. `content/plants.json` 被加入 `ailmint`，`engine_test` 的「pack-only」断言红 —— 用 T66 老二进制同样红，属内容改动。
4. 桌面 relink 在 19:24 之后被 `native/src/level_select_view.cpp` 引用 `pvz::loadBadges/badgesFor/badgeLine`（模块尚未落地）挡住 —— 与本书无关；先等了约 20 分钟，`badges` 落地后桌面 `PvZ2SHUTTLE` 重新构建 **EXIT=0**，上面 §8 的截图就是最终二进制跑出来的；期间另用 `cl /c /utf-8` 单独编译 `battle_view.cpp`（EXIT=0，无告警）证明我的 TU 干净。
5. `python` 读 `vasebreaker.json` 必须 `encoding='utf-8'`（默认 GBK 会 `UnicodeDecodeError`）；用 python 改 C++ 源文件时要注意 CRLF——这次一度把 `battle_view.cpp` 写成 LF，已还原成 CRLF（`git diff --numstat` 86/9 行）。

## 11. 维护提示（给下一个动这块的人）

* 罐表是**只读**的：`VaseTable::shared()` 从 `engine::generatedDir()/vasebreaker.json` 读，缺文件/形状不对会抛 `vase table: <path>: <原因>`，不要在这里加兜底默认值。
* 改摆放规则要同步改 `testVaseLayoutFollowsTheSeed`（同种子必须同 hash），否则回放与冒烟全乱。
* 新增罐内容类型时，`VaseContent` 枚举、`vaseContentName`、`breakVase` 的分支、`VaseTally` 字段、`--run-level` 的 `vasebreaker` 计数要一起改；漏一个就是静默降级。
* 砸罐子关**不要**再打开波次导演：内容里的合成波只是数据残留，不是玩法。
