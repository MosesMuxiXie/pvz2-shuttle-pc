# 自查与修正记录（2026-11-20，队长）

本文件记录我在 S2 内核自查中发现、并已修正的缺陷。每条都给出：问题、证据位置（修正前）、
为什么是真问题、修法、验证方式。审计员（`docs/reviews/2026-11-20-s2-audit.md`）的独立发现
另见其报告；两份若有重叠，以代码现状为准。

## 1. 未接线族计数器按帧累加（统计口径错误）

- 位置：`native/src/engine/world.cpp` 的 `World::noteUnwiredPlant` / `noteUnwiredZombie`；
  调用点是 `tickPlants()`（每个植物每帧一次）与 `tickZombies()`（每个僵尸每帧一次）。
- 问题：`++unwiredPlants_` 无条件自增，而调用方是 **每 tick** 调用。一个没有实现的族在
  场景里存在 10 秒，就会被报成 600 个"未接线的植物"。当前所有族都已注册，所以这个 bug
  是**潜伏的**——一旦 S3 新增族之前先加了数据，报告会立即说谎。
- 修法：先 `insert()` 进名字集合，只有**首次**插入才自增，语义改为"未接线的族个数"。
- 验证：`native/tests/world_outcome_test.cpp::testUnwiredCountsFamiliesNotFrames`
  （同一族调 50 次仍为 1，第二个族变 2）。

## 2. 反序列化之外的删除也会计入击杀（`killed` 被污染）

- 位置：`World::removeZombie`（修正前无调用点，但属于公开服务，S3 的召唤/清理会用到）。
- 问题：`removeZombie` 里 `++killed_`，而 `killed_` 同时被 `damageZombie` 用来表示"击杀"。
  两个语义混在一个计数器里，清怪率会被"消失"抬高。
- 修法：新增 `removed_` 与 `removedZombies()`；`removeZombie` 记 `removed_` 并发
  `zombie_removed` 事件；`summarize()` 增加 `removed` 字段。
- 验证：`world_outcome_test.cpp::testRemovalIsNotAKill`（kill=0、removed=1、spawned=1）。

## 3. 胜利分支从来没有被跑到过

- 事实：S2 的 5 个冒烟场景**全部 `status=lost`**，`engine_test` 只断言 26 世界的状态
  落在 `{playing,won,lost}` 之内，`won` 一次也没发生。也就是说 `resolveOutcome()` 的
  胜利路径是**未验证代码**。
- 修法：新增 `native/tests/world_outcome_test.cpp::testVictoryBranch`——构造单波单僵尸关卡，
  在僵尸出场后原地引爆 1e9 伤害，等待状态收敛，断言 `status=="won"` 且 `killed==1`。
- 验证：`world_outcome` 作为第 10 个 CTest 用例通过（见下方门禁记录）。

## 4. 状态哈希漏掉了会影响后续的所有字段

- 位置：`World::hash()`。
- 问题：修正前只混入 tick/status/sun/wave、容器尺寸与实体位置血量，**漏了**：
  `cooldowns_`（玩家冷却，决定下一次能否种植）、植物各 `slot.remainingTicks`（决定下一次
  开火）、僵尸 `slowUntilTick`/`nextSpecialTick`/`target`、`nextId_`/`spawned_`/`killed_`、
  以及 `rng_` 自身状态。两份状态在这些字段上不同、行为必然分叉，哈希却相同——"确定性"
  的证据强度被高估了。
- 修法：把上述字段全部纳入 FNV-1a 输入（浮点仍按 ×1000 量化）；生成器状态直接
  `out << rng_`，因为它是"未来随机"的唯一记录。
- 影响：所有冒烟哈希变化（见下表），`native/generated/engine_smoke.json` 已重新生成。
- 验证：`engine` 用例的 `testDeterminism` 仍通过（同种子三次同哈希、分块推进等价）。

## 5. 天空阳光节拍漂移

- 位置：`World::tickSkySun`。
- 问题：触发后 `skySunTimer_ = 0`，丢掉 1/60 秒以下的余量（理论上还有更大幅度的余量）。
  每个周期少算一点，长期节拍逐周期变慢。
- 修法：`skySunTimer_ -= threshold`。
- 验证：`engine` 用例的 `testSunEconomy` 仍通过；40 秒内仍掉阳光、可收集。

## 6. 射手会朝身后已经走过的僵尸开火（语义错误）

- 位置：`World::firstZombieAhead`（`if (zombie.x + 0.5 < from) continue;`）。
- 问题：允许僵尸越过射手 0.5 格之后仍被当作"前方目标"，豌豆会反向飞出。
- 修法：新增 `tuning::kShotBehindToleranceCols = 0.15`，只容忍 0.15 格的贴身重叠，
  超过即视为已走过。
- 验证：`engine` 的 `testShotsAndEating` 通过；冒烟哈希变化。

## 死配置清理

- `tuning::kVictoryGraceSeconds = 30.0` 从未被读取（`resolveOutcome` 里写死 0.5 秒）。
  已删除并替换为带注释的 `kVictoryFlushSeconds = 0.5`——语义是"等最后一波 spawn 游标
  越过 lastTick"，不是"赢了之后再等 30 秒"。

## 门禁记录（修正后）

| 项 | 结果 |
| --- | --- |
| `tools/build_native.ps1 -AuditOnly` | **10/10** 通过（新增 `world_outcome`） |
| `python tools/engine_smoke.py` | 5 场景双跑一致，全部 `lost`（无人操作的预期结果） |
| 新增测试 | `native/tests/world_outcome_test.cpp` |

冒烟哈希（修正后，`native/generated/engine_smoke.json`）：

| 场景 | 尺寸 | tick | 哈希 |
| --- | --- | --- | --- |
| frontyard_1 | 5×9 | 8038 | `0xa76d48ab1cfd2c8f` |
| frontyard_1 | 6×10 | 9544 | `0x44045a6cef1b7a25` |
| frontyard_1 script | 5×9 | 10019 | `0x8b62bf4a1959608f` |
| frontyard_6 | 5×9 | 8029 | `0x3f6f75f8752eaab7` |
| kongfu_1 | 5×9 | 8785 | `0xacbce1a62fe4bb98` |

## 仍未修（已知，不隐瞒）

1. **真实关卡里 `won` 依然没有发生过**：33 只僵尸对 7 株豌豆，无人操作的必然结果是输。
   这不是内核错误，是缺"能玩的强度"——属于 S3.4 行为族与数值校准的范围。
2. **`rng_` 在 1809 关里从未被消费**：每关的 `spawn.row` 都写死了行号，`rows` 数组分布
   只在少数关卡出现。种子今天只作溯源，S3.1/S3.3 接上随机行选择后才真正生效。
3. **`heavy_shield` / `kongfu_gargantuar` 两个重复 TypeName** 在 pack 里保留两条、索引取
   第一条；这是原版数据的事实，未做折叠。
4. **棋盘尺寸仍全按 5×9**：`content/levels/*.json` 无尺寸字段，由 S3.1 从原版 `WorldData`
   解出后接入。
