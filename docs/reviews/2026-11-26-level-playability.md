# 逐关可玩性底账（A6）

> 生成日期：2026-11-26
> 产物：`native/generated/level_playability.json`（1,394,571 字节，sha256 `0209a7c3a8ea307e92c44b6248dbf9ea1fdd88039c8fc2321a93093f794781e7`）
> 编译器：`tools/contentc/level_playability.py`（`--check` 逐字节）
> 测试：`tools/tests/test_level_playability.py`（23 例）
> 门禁：`tools/check_all.ps1` 的 `Step 'level playability'`（在 `Step 'minigame rules'` 之后）
>
> **门禁提醒**：本表读的是四份上游产物（`level_mechanics.json`、`minigames.json`、`minigame_rules.json`、`vasebreaker.json`）加 `content/levels/*.json` 的 `extra` 开关。上游任何一份重生成，这里就会 `--check` 报过期——改 content 或改 `tools/contentc/mechanics.py` 等编译器后，必须一起重跑本编译器，否则 `check_all.ps1` 会红。

## 0. 结论摘要

| 问题 | 答案 |
| --- | --- |
| 一共多少关 | **1809**（26 个世界，`frontyard` 175 关最多的一次在 `counts.levelsByWorld`） |
| 按本项目判据「能玩」的关 | **1340**（74.1%） |
| 卡在 data-only 机制上 | **454** 关 |
| 卡在被阻断的玩法上 | **16** 关（`column` 8 + `invisighoul` 8，两者不重叠；其中 1 关 `lunarrainbowmarket_23` 同时也有 data-only 缺口） |
| 引擎**现在**真的能跑完的关 | **1225**（比 1340 少 115 关：数据齐、但玩法变体没实现，见 §5） |
| 只差一个机制就能玩的关 | **373**（占全部阻塞关的 79.5%） |
| 最贵的一条缺口 | `night`：**187 关**，改一处 `tickSkySun` 就能一次解决 |

两套口径必须分开看，否则会得出矛盾结论：

- **playable（数据口径）**：只问「这关的数据里有没被引擎读的机制吗」——`1340`。
- **playableInEngine（实现口径）**：再叠加「这关挂的玩法变体引擎实现了没有」——`1225`。

差的那 115 关不是数据缺失，而是**玩法变体只实现了 4 种**（见 §5）。

## 1. 判据（写死在脚本常量 `CRITERION` 里）

| 编号 | 规则 |
| --- | --- |
| R01 | 机制清单来自 `level_mechanics.json` 每关的 9 个字段（`boardGrid`/`conveyor`/`events`/`initialGridItems`/`initialPlants`/`mutators`/`protectThePlant`/`spawners`）+ `content/levels/*.json` 的 `extra` 开关；**只登记非空值**，空数组/空对象/`null` 不算这关有该机制。 |
| R02 | 每个机制在 `MECHANISMS` 注册表里固定 `wired` 与 `source`（`文件:行`），**不允许按关卡推断**——同一机制在任何关里都是同一个答案。 |
| R03 | `wired=true` 的判据是「引擎里有读取点，并且这个读取点真的被 `step()`/`parseLevel()` 调用」；只在注释/文档/字符串列举里出现的名字不算（`catalog.cpp:149`、`simulation.cpp:28` 就是这么被排除的）。 |
| R04 | 玩法轴单独看 `minigame_rules.json`：`playable=false` 的 kind（`column`、`invisighoul`）在关卡里出现即算 `blocked`，不管数据多完整。 |
| R05 | `playable = blockers 为空`；`blockers = data-only 机制 + blocked 玩法（前缀 `minigame:`）`，按 `MECH_ORDER` 后接玩法名的固定顺序排。 |
| R06 | `playableInEngine = playable 且 该关所有玩法 kind 都在引擎已实现的 4 种里`（`MINIGAME_ENGINE`：vasebreaker / rail / conveyor / protecttheplant）。这一列**不进** `blockers`，单独统计。 |
| R07 | 唯一的数据侧注释：`extra.vasebreaker` 为真但包内没有 `VaseBreakerPresetProperties` 的关 → `notes: ["vasebreaker-flag-without-preset"]`（全库只有 1 关，`frontyard_166`）。这是数据缺口，不是引擎缺口。 |
| R08 | 输出 `sort_keys` + 紧凑分隔符 + 纯 LF；`--check` 逐字节比磁盘，含 CRLF 检查与「counts 可复算」。 |

## 2. 机制 × 引擎消费者（25 条注册表）

`declared` 是「这关有这个机制」的判定源，`source` 是引擎里的读取/消费点（全部 grep 核实过）。

| 机制 | 中文 | 声明源 | 判定 | 引擎依据（文件:行） |
| --- | --- | --- | --- | --- |
| `conveyor` | 传送带 | `level_mechanics.levels.<id>.conveyor` | wired | `mechanics.cpp:127` readConveyor；`world.cpp:825` dealConveyor |
| `initialPlants` | 开局预置植物 | `…initialPlants.placements` | wired | `mechanics.cpp:410` readPlacements；`world.cpp:732` layInitialField |
| `initialGridItems` | 开局预置格子物件 | `…initialGridItems.placements` | wired | `mechanics.cpp:413` readGridItems；`world.cpp:778` addGridItem |
| `protectThePlant` | 保护植物任务 | `…protectThePlant` | wired | `mechanics.cpp:418` readProtect；`world.cpp:760,769,1512` requiredSurvivors |
| `spawners.gravestone` | 墓碑波次 | `…spawners.gravestone` | wired | `mechanics.cpp:419` readGravestones；`world.cpp:810` spawnGravestonesForWave |
| `spawners.jittered` | 普通僵尸波次表 | `…spawners.jittered` | wired | `mechanics.cpp:456` kCovered；`director.cpp` |
| `spawners.grid` | 格子/墓碑群刷怪 | `…spawners.grid` | wired | `mechanics.cpp:247` readSpawners + `:457`；`world.cpp:861` scheduleSpawnersForWave |
| `spawners.portal` | 传送门刷怪 | `…spawners.portal` | wired | `mechanics.cpp:247` + `:458`；`world.cpp:861` |
| `spawners.storm` | 风暴刷怪 | `…spawners.storm` | wired | `mechanics.cpp:247` + `:459`；`world.cpp:861` |
| `spawners.ground` | 地面钻出刷怪 | `…spawners.ground` | wired | `mechanics.cpp:247` + `:460`；`world.cpp:861` |
| `spawners.dino` | 恐龙骑乘刷怪 | `…spawners.dino` | wired | `mechanics.cpp:247` + `:461`；`world.cpp:861` |
| `spawners.beach` | 海滩出水刷怪 | `…spawners.beach` | wired | `mechanics.cpp:247` + `:462`；`world.cpp:861` |
| `spawners.fish` | 鱼群刷怪 | `…spawners.fish` | wired | `mechanics.cpp:247` + `:463`；`world.cpp:861` |
| `boss` | Boss 关 | `extra.boss` / `extra.boss_zombie` | wired | `boss.cpp:247` selectBoss；`world.cpp:107,1151` trySpawnBoss |
| `rail` | 矿车轨道 | `extra.rail` | wired | `world.cpp:153,160` layRailCarts（`:162` 读 `extra.rail`）；`rail.cpp:104` RailTable::shared |
| `minecarts` | 矿车行号表 | `extra.minecarts` | wired | `world.cpp:173`（layRailCarts 内读 `extra.minecarts`） |
| `vasebreaker` | 砸罐子 | `extra.vasebreaker` + `vasebreaker.json` | wired | `world.cpp:89,156` layVases；`vase.cpp:132` VaseTable::shared |
| `suppressFlagZombie` | 旗子波按普通波 | `extra.suppressFlagZombie == true` | wired | `world.cpp:75` 读开关；`world.cpp:374` flagDropped |
| `spawners.spider` | 蜘蛛雨刷怪 | `…spawners.spider` | **data-only** | `mechanics.cpp:488` spawnerKindIsWired 明确 `kind != spider`；`world.cpp:141` 记 mechanic_unknown |
| `events.tide` | 涨潮 | `…events.tide` | **data-only** | `mechanics.cpp:373` 整个 events 记未知；native/src 无 tide 读取点 |
| `events.frost` | 冰风 | `…events.frost` | **data-only** | `mechanics.cpp:373`；无 frost 读取点 |
| `events.strength` | 风力强度 | `…events.strength` | **data-only** | `mechanics.cpp:373`；无 strength 读取点 |
| `mutators` | 关卡变体表 | `…mutators` | **data-only** | `mechanics.cpp:375` 记未知；无 mutator 读取点 |
| `boardGrid` | 棋盘格覆盖 | `…boardGrid` | **data-only** | `mechanics.cpp:378` 记未知；无 boardGrid 读取点 |
| `night` | 夜战（无天降阳光） | `extra.night == true` | **data-only** | `world.cpp:355` tickSkySun 只在砸罐子关（`:352`）跳过，`night` 无读取点 |

三个补充事实：

1. 引擎自己已经有一份「已覆盖」清单 `native/src/engine/mechanics.cpp:451-463 kCovered[]`，共 13 项；本表的 `wired` 集合与它逐条对齐（脚本 `check()` 会强制这个一致性，谁改一边另一边就会红）。
2. `rail.cpp:19` 那句「the sheet has never shipped one」已经过期——t81 交付了 `rail.json`，`rail.cpp:104 RailTable::shared` 现在是真读。
3. `native/src/simulation.cpp:18-33 Battle::unsupportedRules` 拒绝 boss/vasebreaker/night/minecarts，那是旧的 `--simulate` 预览层，**不是**主引擎 `World`；主引擎这四项都已经接了。别拿它当证据说引擎没接。

## 3. 汇总计数（`counts`）

| 键 | 值 |
| --- | --- |
| `levels` | 1809 |
| `playable` | **1340** |
| `blockedDataOnly` | **454**（含 1 关同时被玩法挡） |
| `blockedMinigame` | **16**（含同一关） |
| `blockedBoth` | 1 |
| `playableInEngine` | **1225** |
| `levelsWithAnyBlocker` | 469 |
| `levelsWithSingleBlocker` | **373** |
| `levelsWithEngineGap` | 232 |
| `mechanicKinds` / `wiredKinds` / `dataOnlyKinds` | 25 / 18 / 7 |

`blockersByKind`（575 条 blocker 合计，含玩法）

| blocker | 关数 |
| --- | --- |
| `night` | 187 |
| `spawners.spider` | 118 |
| `events.frost` | 64 |
| `events.tide` | 60 |
| `events.strength` | 60 |
| `boardGrid` | 49 |
| `mutators` | 21 |
| `minigame:column` | 8 |
| `minigame:invisighoul` | 8 |

`mechanicsByKind`（25 条，wired 在前）

| 机制 | 关数 | | 机制 | 关数 |
| --- | --- | --- | --- | --- |
| `spawners.jittered` | 1615 | | `night` | 187 |
| `initialGridItems` | 466 | | `spawners.spider` | 118 |
| `spawners.gravestone` | 353 | | `events.frost` | 64 |
| `conveyor` | 350 | | `events.tide` | 60 |
| `protectThePlant` | 286 | | `events.strength` | 60 |
| `initialPlants` | 249 | | `boardGrid` | 49 |
| `spawners.grid` | 237 | | `mutators` | 21 |
| `suppressFlagZombie` | 215 | | | |
| `rail` | 192 | | | |
| `minecarts` | 190 | | | |
| `spawners.portal` | 130 | | | |
| `spawners.storm` | 119 | | | |
| `spawners.ground` | 100 | | | |
| `spawners.dino` | 93 | | | |
| `spawners.beach` | 82 | | | |
| `boss` | 71 | | | |
| `vasebreaker` | 47 | | | |
| `spawners.fish` | 26 | | | |

## 4. 一条引擎改动能一次解决多少关

这是本表最有行动价值的部分：缺口按「同一条改动」聚合，不是按关卡。

| 改动 | 一次解锁 | 具体做什么 | 关例 |
| --- | --- | --- | --- |
| 读 `extra.night` | **187 关** | `world.cpp` 的 `step()` 在 `tickSkySun` 前判 `night`（现存只有 `vasebreaker_` 一个跳过条件，在 `:352`） | `carnival_30`、`chinesegarden_24`、`chinesegarden_26` |
| 接 `spider` 刷怪 | **118 关** | `mechanics.cpp:488 spawnerKindIsWired` 去掉 `!= spider` 例外，并给蜘蛛补僵尸表项 | `carnival_1`、`carnival_11`、`carnival_46` |
| 读 `events.frost` | **64 关** | 在 `parseLevel` 里解 events、给植物挂冻结/减速状态 | `carnival_46`、`dino_10`、`dino_52` |
| 读 `events.tide` | **60 关** | 涨潮改变地面占位（海滩） | `beach_10`–`beach_15` |
| 读 `events.strength` | **60 关** | 风力影响弹道 | `beach_10`–`beach_15` |
| 读 `boardGrid` | **49 关** | 限制可种植格（`battle_view`/`grid` 层） | `beach_94`、`carnival_10`、`carnival_26` |
| 读 `mutators` | **21 关** | 关卡变体表（挑战/骰子） | `beach_21`、`carnival_51`、`dark_32` |

前六条加起来的并集是 **454 关** data-only 缺口的全部——也就是说 **A 部分只要动 7 处（其中 `events.*` 三项目前都用同一个 `readUnknowns` 分支，实际可合并成 1 处解析 + 3 处消费），就能把 playable 从 1340 推到 1793**（454 关里 `lunarrainbowmarket_23` 同时还被 `minigame:invisighoul` 挡着，所以实际是 1340 + 454 − 1 = 1793，剩 16 关仍卡在玩法轴）。

## 5. 玩法轴：18 可玩 / 2 阻断，但引擎只实现了 4 种

`minigame_rules.json` 判定的可玩性（数据完整度口径）与引擎实现是两件事：

- **数据可玩 18 种**：beghouled、bigtrouble、bonuschallenge、bowling、camel、cannon、conveyor、cowboy、deathexplosion、joust、laststand、protecttheplant、rail、seeingstars、sproutplanting、tide、vasebreaker、whackazombie。
- **数据阻断 2 种**：`column`（8 关）、`invisighoul`（8 关）——锚点模块 8/8 都挂上了，但参数对象 objdata 全是 `{}`，一行可用参数都没有。
- **引擎实现 4 种**：vasebreaker（`world.cpp:89,156`）、rail（`world.cpp:162` + `rail.cpp:104`）、conveyor（`world.cpp:825`）、protecttheplant（`world.cpp:760,1512`）。

于是 `minigameEngineGapsByKind`（数据齐、引擎没实现）就是剩下 16 种，涉及 **232 关**：

| kind | 关数 | | kind | 关数 |
| --- | --- | --- | --- | --- |
| `tide` | 77 | | `cannon` | 8 |
| `laststand` | 73 | | `column` | 8 |
| `deathexplosion` | 17 | | `invisighoul` | 8 |
| `bowling` | 15 | | `bigtrouble` | 6 |
| `beghouled` | 11 | | `joust` | 4 |
| `cowboy` | 10 | | `seeingstars` | 3 |
| | | | `bonuschallenge` / `camel` / `sproutplanting` | 2 / 2 / 2 |
| | | | `whackazombie` | 1 |

玩法轴与机制轴**不是同一口径**，别混：机制轴 `conveyor` 350 关（含 `ConveyorBelt` 未挂玩法模块的情况），玩法轴 `conveyor` 只有 332 关；`protectThePlant` 机制 286 关 vs 玩法 197 关；`tide` 事件 60 关 vs 玩法 77 关。三处差都来自「对象在包里但模块没挂」或「模块挂了但对象没进 mechanics」。

## 6. 只差一个机制的 373 关

按 kind 分布（`counts.levelsWithSingleBlocker = 373`，逐关明细见顶层 `singleBlockerLevels`，按 blocker kind 再按关卡名排序、最多 50 条）：

| kind | 关数 |
| --- | --- |
| `night` | 161 |
| `spawners.spider` | 97 |
| `events.frost` | 54 |
| `boardGrid` | 30 |
| `mutators` | 16 |
| `minigame:column` | 8 |
| `minigame:invisighoul` | 7 |

另有 **87 关**卡在两个 blocker、**9 关**卡在三个及以上（三个 blocker 的 8 关如 `beach_21` = `events.tide` + `events.strength` + `mutators`；唯一四个 blocker 的是 `fairy_41` = `spawners.spider` + `events.tide` + `events.strength` + `night`）。

## 7. 数据侧缺口与注意事项

1. `frontyard_166`：`extra.vasebreaker = true`，但包内只有 `VaseBreakerEndlessProperties`（无尽模式），没有 `VaseBreakerPresetProperties` → `notes: ["vasebreaker-flag-without-preset"]`。它是无尽关，不是 47 关中的一个常规罐子关。
2. `extra.night` 键在 1809 个 level 文件里**都存在**，但只有 **187** 关为 `true`；判据必须看值，不能看键是否存在（`extra.rail`/`minecarts`/`boss`/`vasebreaker`/`special`/`suppressFlagZombie` 同理）。
3. `boss` 的 71 关同时都有 `boss_zombie`，判据用 `extra.boss` 或 `extra.boss_zombie` 任一为真即可（`boss.cpp:247` 也允许只有后者）。
4. `initialPlants` 有 272 关写了字段、但只有 249 关的 `placements` 非空；`initialGridItems` 690 → 466。本表按**非空**计，空列表不算机制。
5. `suppressFlagZombie` 键出现在 271 关，其中 215 关为 `true`；56 关显式写 `false`（与默认相同，不算机制）。
6. `vasebreaker` 机制 47 关与 `vasebreaker.json` 47 关一一对应，没有孤儿。

## 8. 产物结构

顶层（实际 11 个键，`sort_keys` 序）：

```
counts            见 §3；键为 levels / playable / blockedDataOnly / blockedMinigame
                  / blockedBoth / playableInEngine / levelsWithAnyBlocker
                  / levelsWithSingleBlocker / levelsWithEngineGap / mechanicKinds
                  / wiredKinds / dataOnlyKinds / mechanicsByKind / blockersByKind
                  / blockerKindTotal / minigamesByKind / minigameEngineGapsByKind
                  / levelsByWorld / notesByKind
criterion         一句话判据原文：playable = 没有任何 data-only 机制 且 没有 blocked 玩法
engineKcovered    引擎 mechanics.cpp:451-463 的 13 项 kCovered 副本（用于交叉校验）
format            "pvz2-shuttle/level-playability@1"
generated         "2026-11-26"
levels            1809 键，每关：
                  { level, world,
                    mechanics[{kind, wired, source}],
                    minigames[{kind, playable, engineImplemented, source}],
                    minigameEngineGaps[], notes[],
                    playable, playableInEngine, blockers[],
                    wiredCount, dataOnlyCount }
mechanisms        25 条注册表副本（id / cn / declared / wired / source）
minigameEngine    引擎已实现的 4 种玩法（conveyor / protecttheplant / rail / vasebreaker）
                  及各自依据
singleBlockerLevels 只差一个机制的 50 条样例 [{blocker, level}, …]
sources           6 个输入及其 sha256（4 份上游产物 + content/levels + mechanics.cpp）
```

`blockerKindTotal` 是 `blockersByKind` 各项之和（575）；`blockedDataOnly + blockedMinigame - blockedBoth` 与「有 blocker 的关数」469 一致，`check()` 会复算这两条。

每关的 `mechanics` 顺序固定为 `mechanicOrder`，`blockers` 顺序固定为机制在前、玩法在后——所以同一关两次生成必然逐字节相同（`--check` 依赖这一点）。

## 9. 复现与耗时

```powershell
cd D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc
python tools/contentc/level_playability.py            # 生成
python tools/contentc/level_playability.py --check    # 逐字节自检（门禁用这一条）
python -m unittest tools.tests.test_level_playability -v
```

实测（Windows + OneDrive 工作区，冷跑）：

| 动作 | 脚本内计时 | 墙上时间（含解释器启动与读盘） |
| --- | --- | --- |
| 生成 | 3.9 s | 13.9 s |
| `--check` | 3.9 s | 13.8 s |

单测 `Ran 23 tests in 43.031s / OK`。

## 10. 诚实边界

1. **`wired` 是静态阅读结论**，依据是 grep 到的读取点与调用点；没有跑引擎做行为验证。若某处读取点读了但没真正生效（例如被后续逻辑覆盖），本表看不出来——那需要 `engine smoke`/`parity` 那类测试来兜。
2. `spawners.jittered` 的依据不是独立读取点，而是「普通波次表由 `director.cpp` 统一处理 + `kCovered` 里没有单列它」；它的 1615 关是所有波次关的基本盘，把它列成 wired 意味着「普通波次能打」，不是「每一关的波次数值都验过」。
3. `playableInEngine` 只判「玩法 kind 在 4 种已实现里」，按**变体类型**判，不看该变体的参数是否齐全。例如 `vasebreaker` 引擎接了，但 `frontyard_166` 是无尽关、参数缺失，仍算「引擎实现了该变体」——它靠 `notes` 单独标注。
4. `minigame_rules.json` 的 18/2 判定是数据完整度口径；若上游把 `column`/`invisighoul` 的参数补上，本表会自动从 blocked 变 playable（`--check` 会先报过期）。
5. `blockers` 只统计**机制与玩法**两类缺口。经济、奖励、图鉴、关卡解锁进度等都不在判据内——本表不回答「这关该不该解锁」。
6. 计数里的「关」是 `content/levels/*.json` 的文件数（1809），不是原版关卡表里的 `LevelNumber` 计数；两者口径不同（无尽关、重复编号关都存在）。
