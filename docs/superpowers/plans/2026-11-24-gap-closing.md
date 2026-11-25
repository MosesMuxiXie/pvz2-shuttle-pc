# 本轮计划：对照原版补差距（2026-11-24）

用户决定：**打包留到最后**，先把「照原版还缺什么」查清并补上，同时把之前提到的问题收口。

## 目标

1. **对照原版**：不靠印象，用 objclass 普查 + 关卡机制覆盖两张表，量化「原版有、我们没有」的部分。
2. **补差距**：优先补「补了立刻可感知」的关卡机制，其次非战斗系统。
3. **收口旧问题**：拖动种植、经济闭环、音频（音量 / 交叉淡入 / 5 个 mp3）、铁轨与砸罐子标记。

## 已查明的差距（实测，见 `docs/reviews/2026-11-24-original-vs-client.md`）

- 原版 1110 个 objclass / 54,583 对象；我们只覆盖其中「内容 + 战斗内核」那一簇。
- **关卡机制**是主空白：传送带 349 关、墓碑波 353 关、初始场地物件 475 关、初始植物 272 关、
  保护植物 286 关、传送门 130 关、风暴 119 关、蜘蛛雨 118 关、恐龙 93 关、寒风 64 关、
  潮汐 60 关、鱼 26 关、变异 21 关、棋盘格 49 关、星章挑战 948 关（只有目标文本）。
- **非战斗系统**整块空白：竞技场/锦标赛 551 条奖励定义、玩家分段 922、图鉴 169、任务 69、
  花园 65、彩罐 41、道具 29、教程 21、强化 14、每日 2。

## 任务

| 任务 | 谁 | 依赖 | 交付 |
| --- | --- | --- | --- |
| T47 原版↔客户端字段级差距盘点（只读） | mapper | — | `native/generated/original_gaps.json` + 报告 |
| T48 关卡奖励与掉落数据编译 | geometer | — | `native/generated/rewards_from_pack.json`（经济闭环的数据基础） |
| T49 音频打磨：音量 / 交叉淡入 / mp3 | sonic | — | `--volume`、BGM 交叉淡入、mp3 决策 |
| T50 拖动连续种植 | wirer | — | `battle_view` 拖动状态机 + 测试 |
| T51 关卡机制数据编译 | artifex | — | `native/generated/level_mechanics.json`（1809 关） |
| T52 引擎接线：传送带 / 初始植物 / 墓碑 / 保护植物 | wirer | T51 | `engine/mechanics.*` + `mechanics_test` |
| T53 铁轨/砸罐子标记可复现化 | mapper | T47 | builder 派生 + content 修正（现在重跑构建会**静默丢掉**这些标记） |


## 进展（2026-11-24 14:20，本轮收尾）

| 项 | 状态 | 证据 / 数字 |
| --- | --- | --- |
| T47 字段级差距盘点 | ✅ | `original_gaps.json` 37,659 B；扫 2116 张表 mapped 13,075 / packOnly 793 / clientOnly 12,210；36 组「原版有值客户端无字段」、7 个整块子系统零覆盖；报告 `docs/reviews/2026-11-24-original-gaps.md` |
| T48 奖励与掉落编译 | ✅ | `rewards_from_pack.json` **336,895 B**（t56 更正后）/ sha256 `7F83E66B…8E8C` / **575 行**（coin 46、key 8、seed 76、plant 293…）；13 张悬空表 |
| T49 音频打磨 | ✅ | `--volume`/`--mute-bgm`/`--mute-sfx` + BGM 0.75 s 交叉淡入 + minimp3（`--audio-audit` 60→65 decoded）；探针 `master volume 0 must produce silence` |
| T50 拖动连续种植 | ✅ | `drag_plant.{hpp,cpp}`；扫 3 格不种、松手种 1 株、再松手 3 次全 -1；desktop 已含 `battle_drag` |
| T51 关卡机制编译 | ✅ | `level_mechanics.json` **4,827,318 B** / sha256 `9F33A09E…0887`（t57 后）；1809 关、1245 关带机制、`--check` 已进 `check_all` |
| T52 引擎接线（机制） | ✅ | `engine/mechanics.*` + `WorldOptions::mechanics`；传送带 348/350、初始植物 272、初始物件 583/690、保护 286、墓碑 353；`mechanics_test` 8 段；矩阵「关卡机制」wired **903** |
| T53 铁轨/砸罐子可复现化 | ✅ | builder 派生后 vasebreaker **47**、minecarts **190**、rail **192**；`catalog_test` 改 47/44；矩阵新增「铁轨」行 |
| T54 数据只读审计 | ✅（结案） | 12 项计数 11 项逐字复现；M1（保护判负）→ T52 修、M2（拾取物映射）→ T56 修、M3（jittered 聚合表述）→ 报告与文档改写；无 blocker/high |
| T55 经济闭环 | ✅ | `rewards.{hpp,cpp}`：金币/钥匙/种子进 `Progress`，其余 `reward_unmodelled`；矩阵新增「掉落」行 **575 / 575 / 130**；不带 `--progress` 输出与 T52 二进制逐字节相同 |
| T56 rewards 审计更正 | ✅ | 5 行拾取物补 `lawn_mower`/`sprout`；哨兵拆三口径（readPath 38 / readPackages 604 / allPackages 5327） |
| T57 egypt_74 取证 | ✅ | 报告 `docs/reviews/2026-11-24-egypt74-protect.md`；结论：**零容错而非必输**；5 关 `must > 去重格`、11 关 `placed < must`、6 关空转 |
| T58 protect 多模块合并 | ✅ | `lostcity_46` 2 株→**9 株 / must 4**；`failWhenProtectedPlantDies` 标 `client-default`；`counts.protect` 审计块（287 模块） |
| T59 保护容量不足可见 | ✅ | 11 关开局发 `protect_capacity_shortfall`；`--run-level` 只对保护关出 `protectPlaced`/`protectCapacityShortfall`；探针 `an exact fit is not a shortfall` |

**收尾读数**：audit **27/27**、python **426**、desktop **36/36**、冒烟 32 场景按新基线 0 差异；
严格 `check_all -NoContent` **EXIT=0**（静树，pycache 已从树指纹里滤掉）。

## 门禁（本轮结束必须满足）

1. `pwsh -File tools/check_all.ps1 -NoContent` → **EXIT=0**（静树）。
2. audit / desktop / Python 三个数字与 `docs/PARITY_BASELINE.md` 台账一致（自动核对）。
3. 每个新数据文件都有 `--check` 与测试；`check_all` 里挂上对应 step。
4. 32 场景冒烟：变化逐条列出并解释，不许「刷基线了事」。
5. headless 截图（`--battle-snapshot`、`--menu --frames 2`）哈希不变，除非有明确理由。
6. 文档：`docs/COMPLETENESS.md`、`docs/PARITY_BASELINE.md`、本文件都要写实测数字。

## 顺序

1. 数据编译（T47 / T48 / T51）与独立工程（T49 / T50）并行。
2. T51 落地后 → T52 引擎接线。
3. T47 落地后 → T53 内容可复现化。
4. 全部完成后跑门禁、刷台账、汇总。

## 不在本轮

- 打包（用户明确留到最后）。
- 竞技场 / 任务 / 每日 / 花园等联网或大 UI 系统 → 属于 S9，先在差距文档里登记。
