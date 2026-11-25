# 原版 PvZ2 SHUTTLE v26.10.1 ↔ 本客户端：差距对照

日期：2026-11-24 · 口径：只写实测数字，复现命令在每节末尾 · 只读分析，未改源码

> 这份文档回答一个问题：**照原版看，我们还缺什么。**
> 结论先说：缺的不是植物/僵尸/弹道这类「内容」，而是**关卡机制**与**非战斗系统**。
> 战斗内核能打，但 1809 关里绝大多数关卡的玩法开关在客户端数据里根本不存在。

---

## 0. 方法

两把尺子，都跑在 2117 个原版包上（`work/obb_packages/pkg_*.json`）：

1. **objclass 普查**：数全库 objclass（1110 个 / 54,583 个对象），按功能关键词分桶，
   看哪些系统的表存在而我们没有对应实现。
2. **关卡机制覆盖**：1809 个 `*_LevelDefinition.json` 里，每种机制类出现在多少关，
   再对照客户端 `content/levels/*.json` 的实际字段（只有
   `id/world/index/title/sun/deck/waves/flags/seed_bank/extra`）。

```powershell
python work/probe_objclass_inventory.py --list 40
python work/probe_level_mechanics.py --json work/level_mechanics_probe.json
```

---

## 1. 关卡机制：最大的一块空白

| 机制 | 原版对象数 | 出现关卡数 | 客户端今天 |
| --- | ---: | ---: | --- |
| 传送带（`ConveyorSeedBankProperties`） | 349 | **349** | `extra.seed_bank` 只是一个 `int`，没有卡槽 |
| 墓碑波（`SpawnGravestonesWaveActionProps`） | 1221 | **353** | 无 |
| 墓碑对象（`GravestoneProperties`） | 241 | **241** | 无 |
| 初始场地物件（`InitialGridItemProperties`） | 592 | **475** | 无 |
| 初始植物（`InitialPlantProperties`） | 277 | **272** | 无 |
| 保护植物挑战（`ProtectThePlantChallengeProperties`） | 287 | **286** | 无 |
| 网格生成器（`SpawnZombiesFromGridItemSpawnerProps`） | 708 | 237 | 无 |
| 传送带改动波（`ModifyConveyorWaveActionProps`） | 381 | 132 | 无 |
| 传送门（`SpawnModernPortalsWaveActionProps`） | 684 | 130 | 无 |
| 风暴（`StormZombieSpawnerProps`） | 375 | 119 | 无 |
| 蜘蛛雨（`SpiderRainZombieSpawnerProps`） | 322 | 118 | 无 |
| 地面生成器（`SpawnZombiesFromGroundSpawnerProps`） | 325 | 100 | 无 |
| 恐龙波（`DinoWaveActionProps`） | 887 | 93 | 无 |
| 海滩事件（`BeachStageEventZombieSpawnerProps`） | 372 | 82 | 无 |
| 寒风（`FrostWindWaveActionProps`） | 283 | 64 | 无 |
| 潮汐（`TidalChangeWaveActionProps`） | 370 | 60 | 无 |
| 棋盘格映射（`BoardGridMapProps`） | 302 | 49 | 无 |
| 鱼（`SpawnZombiesFishWaveActionProps`） | 301 | 26 | 无 |
| 关卡变异（`LevelMutator*`） | 194 | 21 | 无 |
| 星章挑战模块（`StarChallengeModuleProperties`） | 952 | 948 | 只有 `stars.json` 的目标文本，没有挑战运行时 |

**这意味着什么**：`beach`、`frostbite`、`lostcity`、`dino`、`modern` 这些世界的主玩法
（潮汐、寒风、恐龙、传送门、传送带）在引擎里都没有对应实现。客户端现在能把一关的
「波次 + 卡组 + 阳光」跑完，但**跑的不是那一关**。

已完成的可玩层：波次生成、卡组与阳光、植物族与僵尸族、护甲、弹道、养料、融合、
Boss（71 关）、割草机、跳跃、星星结算（数据侧）。

---

## 2. 非战斗系统：原版有、客户端整块没有

| 系统 | 原版对象数 | 表 | 客户端 |
| --- | ---: | --- | --- |
| 竞技场 / 锦标赛（`Joust*`） | **551** | `JoustProgressiveRewardDefinition` 513、`JoustTournamentRewardDefinition` 27、`JoustSeasonRewards` 11 | 无 |
| 玩家分段规则 | **922** | `PlayerSegmentRules`（单文件） | 无 |
| 图鉴（`PlantAlmanacData`） | 169 | 167 条植物图鉴 | 无 |
| 任务（`Quest*`） | 69 | 19 个类 | 无 |
| 花园（`ChineseGarden*`） | 65 | 42 个桥接模块 + 7 舞台 + 3 奖励表 | 无 |
| 彩罐（`PinataType`） | 41 | 39 种 | 无 |
| 道具（`PowerupType` / `LevelPowerupSet`） | 29 | 12 个类 | 无 |
| 教程（`*Tutorial*`） | 21 | 12 个类 | 无 |
| 强化（`PlantBoostPropertySheet`） | 14 | 7 种 | 无 |
| 每日（`DailyActivitiesQuestData` / `DailyQuestSchedule`） | 2 | — | 无 |
| 装扮（`CostumePropertySheet`） | 1 | 566 件产物的字段之一 | 数据侧在 `shop.json`，界面无 |
| 商店（`StoreProductProps`） | 565 | — | **已做**：585 件、可买 21、种子真发放 |
| 存档 / 进度 | — | — | **已做**：`Progress` 原子写、星章、continue 指针 |

原版是 Unity 客户端，UI 全在 `HotUI*`（643 + 541 + 418 + 349 + 325 个对象）里描述；
我们走 SDL 自绘，屏幕数不等量对比，只比「有没有这个功能」。

---

## 3. 已对齐但仍有小口径差的地方

| 项 | 原版 | 客户端 | 缺陷号 |
| --- | --- | --- | --- |
| 铁轨关 | 204 关（functional 192 / decorative 6 / unknown 6） | 只标 10 关（7 关误标、189 关漏标） | C36 |
| 砸罐子关 | 47 关 | 45 关（缺 `pirate_41`、`plantagenet_18`） | C37 |
| Boss 关 | 71 关（按 `ZombossBattle` 模块） | 71 关对齐；4 关数据无 boss 判 `unavailable` | — |
| 世界门 | 97 条（星 53 / 钥匙 27 / 世界 17） | 97 条全接 | C46（钥匙消耗原版 1–5 把，客户端开门恒 1 把） |
| 星章 | 5427 条目标 | 全部落盘，但 **67 条 kill 目标不可达** | C35 |
| 护甲 | 102 条 | 接线 91 条引用 | — |
| 弹道 | 602 条 | 接线 593 条（9 条 unknown 走缺省） | — |
| 画廊/音效 | 65 个音源 | 60 解码、5 个 mp3 缺席 | C50 |

---

## 4. 缺口清单（按「补了立刻可感知」排序）

**P0 关卡机制**（这是「不像原版」的主因）
1. 传送带关卡 349 关：需要 `conveyor` 卡槽数据 + 引擎「卡从带上来」。
2. 初始植物 272 关 / 初始场地物件 475 关 / 墓碑 241 关：需要 `initials` 数据 + 世界初始化。
3. 保护植物 286 关：需要挑战目标类型 + 失败判定。
4. 事件波 60–130 关（潮汐 / 寒风 / 风暴 / 传送门 / 蜘蛛雨 / 鱼 / 恐龙）：需要事件调度器。

**P1 玩法模式**
5. 砸罐子 47 关、铁轨 204 关的运行时（现在只有标记位）。
6. 星章挑战运行时 948 关（现在只有目标文本）。

**P2 非战斗系统**
7. 图鉴 167 条、商店界面、装扮、彩罐、强化、道具、任务/每日。
8. 竞技场 / 锦标赛 551 条奖励定义（原版是联网玩法，本地只能做壳）。

**P3 平台**
9. 打包（用户已明确：留到最后）。

---

## 5. 结论

- **战斗内核**：能跑、能赢、能结算，数据侧（植物 339 / 僵尸 1127 / 护甲 102 / 弹道 602 /
  养料 293 / 融合 85 / Boss 50）齐。
- **关卡玩法**：几乎为零 —— 1809 关里 1200+ 关有至少一种客户端看不见的机制。
  下一步应该优先把 P0 的四类机制做进数据与引擎，而不是继续加内容。
- **非战斗系统**：整块空白，属 S9；其中竞技场依赖联网，只能做壳。
