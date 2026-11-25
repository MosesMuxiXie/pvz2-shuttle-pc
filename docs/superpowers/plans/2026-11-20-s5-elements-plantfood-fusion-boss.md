# S5 阶段计划：元素反应 / 养料 / 融合 / Boss

> 上游：`2026-11-20-full-native-replica.md`、`s2-engine-kernel.md`、`s3-behaviour-families.md`、`s4-desktop-bridge.md`
> 状态：S0–S3 完成并验证；S4 进行中（桌面接内核、美术可行性、卡组报告）。本阶段补四种"内核有位置、数据没落地"的玩法。

## Goal

让引擎支持四件事，并且每件事都能说清"数值从哪来"：
1. **元素反应**：火/冰/风/毒/电 的附着、倍率、冷却、扩散（原版有，数据表里**没有**一张 Element 表）。
2. **养料（plant food）**：每株一个技能，持续时间内改变行为（pack 只有 `PlantFoodDurationSeconds`/`PlantFoodPlayCount` 与 `Actions.Type=plantfood` 的 6 条，**没有**技能效果数据）。
3. **融合**：源植物 + 融合植物 → 结果植物。**按正后的数：`pkg_2083` 是 217 objects / 199 带 objdata / 1 张 PlantFusionConfig / `FusionPairs` 85 条**（早前把 199 个带 objdata 的 object 当成"对数"，已由 t15 证伪）。content 的 85 条与 pack 的 85 条**完全一一对应**（48 个配方键，两侧零差集）。
4. **Boss**：26 个 Boss 的多阶段行为与召唤。

## Architecture

```
engine/world.cpp
  ├─ tickPlants → action_runner (pack 槽位) / registry 族
  ├─ projectile   → 命中后 elements::apply(...)        ← 新增
  ├─ plantfood    → plantfood::run(world, plant)       ← 新增
  └─ boss         → boss::step(world, zombie)          ← 新增
engine/elements.{hpp,cpp}   plantfood.{hpp,cpp}   fusion.{hpp,cpp}   boss.{hpp,cpp}
tools/contentc/{elements,plantfood,fusion_obb,bosses}.py → native/generated/*.json（带 source 标记）
```

## Tech Stack

不变：C++20 / CMake / SDL3 / nlohmann-json；Python 3.14 stdlib 生成器；证据分级沿用 S3 的 `source` 字段。

## Spec

- **元素**：`Element{fire,ice,wind,poison,electric}`；附着有层数与持续时间；反应表（火→冰=融化×2、冰→火=熄灭、风→火=扩散、电→水=导电）作为**作者数据**落 `native/generated/elements.json`，每条带 `"source": "authored"` 与 `"rationale"`，禁止伪装成 OBB 证据。
- **养料**：`plantfood.json` 每株一条 `{id, skill, durationSeconds, effect:{kind,...}}`；`skill` 缺省 `"none"`，引擎遇到 `none` 只播 1.5 秒增益光环（不改变行为），并计入 `unimplementedPlantfood` 计数。
- **融合**：`native/generated/fusions_from_pack.json`（已由 t15 产出，85 条，`sourceKind` 标 client/pack）；引擎只实现"棋盘上两株相邻 → 触发融合 → 替换为结果植物"，不实现融合专属美术。58 条配对的 ingredient 是 pack-only id，进玩法前要先决定这些植物是否存在于 content。
- **Boss**：`bosses.json` 每 Boss `{id, phases:[{hpFraction, summon:[...], attack:{kind,...}, durationSeconds}]}`；引擎按血量分数切阶段，召唤走 `pendingSpawns_` 队列（复用 S2 修复）。

## Global Constraints

1. 60 Hz 唯一推进；元素/养料/Boss 都不得自己推进时间。
2. 每条新数值必须带 `source` ∈ {pack, content, authored}；`authored` 必须在报告里列出并解释依据（社区资料/客户端行为），不得写成"原版数据"。
3. 融合与 Boss 的**触发**可以是数据驱动，**表现**（专属动画/特效）不在本阶段。
4. 引擎改动必须有确定性测试（同种子同哈希）与"关掉特性也能跑"的开关（`WorldOptions{elements, plantfood, fusion, boss}`）。
5. 不 commit/push；不写 `content/**` 之外的用户文件；`assets/**` 不动（美术归 S4/S7）。

## Review Focus

1. 关掉四个开关时，1809 关的冒烟哈希必须与 S4 结束时**完全一致**（证明特性是加法）。
2. 元素反应的倍率与冷却是否只在一处实现（`elements.cpp`），projectile/melee/splash 三条命中路径是否都调用它。
3. 养料持续时间是否用 tick 而非秒；是否在植物被铲除/吃掉时清理状态。
4. 融合是否会消耗错植物、是否在两人同时融合时重复消耗。
5. Boss 阶段切换是否会在同 tick 内反复触发（要有一次性标志与测试）。

## 任务

### S5.1 元素反应（wirer）
- `native/src/engine/elements.hpp/.cpp`：`Element`、`Attachment{element, stacks, expiresTick}`、`applyDamage(World&, ZombieEntity&, double amount, Element)`、`react(World&, ZombieEntity&, Element incoming)`。
- 接入点：`projectile.cpp` 命中、`registry.cpp` 近战/范围、`world.cpp` 爆炸。
- 生成器 `tools/contentc/elements.py` → `native/generated/elements.json`（作者数据 + 反应矩阵 + 冷却）。
- 测试 `native/tests/elements_test.cpp`：附着累积、反应倍率、冷却、减速与冻结不叠加。

### S5.2 养料（wirer）
- `native/src/engine/plantfood.{hpp,cpp}`：`bool feed(World&, EntityId)`（每株每关一次或按 pack 次数）、`tickPlantfood(World&)`。
- 技能先做 6 个通用族：`burst`（范围伤害）、`barrage`（连射）、`shield`（回血）、`freeze`（全场减速）、`sun`（掉阳光）、`none`。
- 生成器 `tools/contentc/plantfood.py` → `native/generated/plantfood.json`（147 条，`source: authored|pack`）。
- 测试：feed 后 1 tick 内生效、持续 N tick 后复原、被铲除时清理。

### S5.3 融合（geometer）
- 已由 t15 交付：`tools/contentc/fusions.py` → `native/generated/fusions_from_pack.json`（85 条）+ `fusion_report.md`。
- 差异表已并入 `fusion_report.md`：配方键两侧各 48、交集 48、差集 0 —— **不存在"content 自创配方"**。
- 引擎 `fusion.{hpp,cpp}`：`tryMerge(World&, row, colA, colB)`；测试相邻/不相邻、重复触发、结果植物不存在时拒绝并记事件。

### S5.4 Boss（wirer）
- `native/src/engine/boss.{hpp,cpp}`；`content/bosses.json` 26 条按阶段读入；阶段切换一次性标志；召唤走 pending 队列。
- 测试：`bosses_test.cpp` 用 1 个 Boss 跑满 3 阶段，断言阶段切换次数恰为 2、召唤数 > 0、同 tick 不重复触发。

### S5.5 门禁与文档（队长）
- `tools/check_all.ps1` 增 `elements/plantfood/fusion/boss` 四项产物检查；矩阵新增四行（按 `source` 分列 pack/content/authored）。
- `docs/PARITY_BASELINE.md`、`docs/NATIVE_PROGRESS.md`、本计划勾选、CHANGELOG。

## 门禁（阶段完成判据）

- [ ] 1. 四个开关全关时，32 场景冒烟哈希与 S4 结束一致（逐条对比，写入报告）。
- [ ] 2. 元素反应有 ≥6 条测试（附着、倍率、冷却、扩散、免疫、清理）。
- [ ] 3. 养料可对 147 株全部调用，`none` 技能有明确计数；每关使用次数受 pack 限制。
- [ ] 4. 融合 85 对全部可从数据加载；`fusion_report.md` 证明与 content 零差集。
- [ ] 5. Boss 至少 1 个完整三阶段 headless 跑通并稳定哈希。
- [ ] 6. 四项数值全部带 `source`，`authored` 清单在报告中逐条列出。

## 与后续阶段的接口

- S6（世界地图/商店/进度）读 `elements.json`/`plantfood.json` 决定解锁顺序。
- 发布（S7）前必须回答："哪些玩法是原版数据、哪些是作者补全"——本阶段的 `source` 字段就是答案来源。

## 进展（2026-11-21 10:35）

### 数据侧：全完成

| 表 | 产物 | 数量口径 |
| --- | --- | --- |
| 融合 | `native/generated/fusions_from_pack.json` | 85 对（`FusionPairs` 条数；`pkg_2083` 的 217 objects / 199 带 objdata 不是对数） |
| 养料 | `native/generated/plantfood_from_pack.json` | 293 行：147 有 duration、185 有 playCount、6 条 `plantfood` action |
| Boss | `native/generated/bosses_from_pack.json` | 50 boss，**可上场 155 阶段**（occurrence 258 / alias 227 是另两种口径） |
| 弹道 | `native/generated/projectiles_from_pack.json` | 602 条（571 canonical + 31 关卡内嵌），71 个 objclass |
| 护甲 | `native/generated/armors_from_pack.json` | 102 条（97 + 5 条只在内嵌副本） |
| 元素 | `native/generated/s5_data_gaps.json` | **原版无元素数据**（21 条空 objdata）→ 标 `authored`，不入复刻口径 |
| 关卡模块 | `native/generated/level_modules.json` | 1809 关 14 键，boss 71 关与原版 71 对齐 |
| 铁轨 | `native/generated/rails_report.json` | 原版 204 关带 rail（functional 192），客户端 10 关 |

### 运行时侧（2026-11-21 11:20 更新）

- **t24 养料 + 融合：完成**（`plantfood.{hpp,cpp}`、`fusion.{hpp,cpp}`、`WorldOptions`、`s5_runtime`）。审计构建 14/14。
- **C41 已修**：`feed`/`tryFuse` 原先没有玩家可达路径（只有单测直调）。现在 `replay` 支持 `feed`/`fuse` 两个 op，`replay_s5` 用例从脚本驱动，并核对拒绝路径与同脚本同哈希。
- **t25 Boss 运行时：完成**（`boss.{hpp,cpp}`）。71 个 Boss 关 `spawned + unavailable == 71`；4 关（`frontyard_67/74/165`、`muji_16`）数据里没有 boss，如实计 `bossUnavailable`。修掉割草机经 `damageZombie` 路由把 Boss 秒掉的 bug（`mowerKills=13` 的那局）。
- **t26 弹道接线：完成**（`projectile_table.{hpp,cpp}`）。直线弹 5.2 → 5.55 cols/s；冒烟只有 2/32 条变化，且都在预期内。
- **t29 护甲接线：进行中**；**t30 跳跃窗口收紧：待办**（t20 的 N3：窗口上界 1.20 列 vs 接触 0.35、冷却 2 s 可连跳）。

### 门禁现状

| 门禁 | 状态 | 证据 |
| --- | --- | --- |
| 1. 四开关全关 = S4 基线 | 未验 | 基线已被 t26 刷新，需一项「全关」跑并与 S4 末期哈希逐条对比 |
| 2. 元素反应 ≥6 测试 | 未验 | 元素为 `authored`，运行时未接线（默认关） |
| 3. 养料对 147 株可调用 | 部分 | t24 提供 `canFeed`，6 株走 pack action；未对 147 株逐一断言 |
| 4. 融合 85 对可加载、零差集 | 通过 | `fusion_report.md`：85/85，配方键 48 两侧一致 |
| 5. Boss 三阶段 headless 稳定哈希 | 通过 | `modern_93` 两次运行同 hash `0x52d17c0a3eb87a42`；`--boss off` 得 `0xd4740a5cc280143a` |
| 6. 四项数值带 `source` | 部分 | 数据侧逐条带 `source:"pack"`；引擎侧 26 处兜底标 `// fallback: tuning constant, no pack evidence` |

### 已登记的缺口

- C42 养料无货币掉落（原版靠掉落植物food，现为脚本驱动）——S7。
- `SpawnOffset.y` 未应用（`spawnSun` 无高度参数）。
- 24 个 Boss mech 有完整阶段表但无任何关卡放置；`zombossmech_egypt_rift` 是 pack 悬空引用。

