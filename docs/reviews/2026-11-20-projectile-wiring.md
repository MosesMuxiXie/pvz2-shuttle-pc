# S5.9 弹道接线：把 `projectiles_from_pack.json` 接进 `stepShots`

日期：2026-11-20（任务 t26）　执行：wirer　写作用域：`native/src/engine/**`、`native/tests/projectile_table_test.cpp`、`native/CMakeLists.txt`、本文件

## 1. 改动前的状态

`stepShots` 只看两个全局常量：`shot.x += shot.speed * dt`，命中判定 `|zombie.x - shot.x| > tuning::kShotHitRadius`，而 `World::spawnShot` 把 `shot.speed` 硬写为 `tuning::kShotSpeedColsPerSec = 5.2`（312 px/s）。表里 602 条弹道的速度、命中盒、抛物线/落点、溅射绝对伤害一个都没进引擎；`Action.projectile` 的 RTID name 只被存进 `ShotEntity.projectileType`，从未查表。

后果：所有植物（含豌豆、冰瓜、玉米、老虎凳）用同一个速度同一个命中盒；`arc` 类弹道按水平弹飞并在空中就命中；表中的溅射伤害（如寒冰西瓜的 40）不可达。

## 2. 数据：表里到底有什么

`native/generated/projectiles_from_pack.json`（`format` 由 contentc 生成，本任务不重建）：

- `projectiles` **602 条，id 全唯一**（571 canonical + 31 仅内嵌；`duplicateIds` 里只有 `ZombossMarketBullet` 一条）。
- 轨迹分布（`trajectoryCounts` 与解析一致）：straight **374**、arc **118**、drop **59**、static **42**、unknown **9**。
- 速度主峰：`straightShotSpeedsPxPerSec` 直方图 `333:142, 650:30, 300:13, 450:11, 400:8, -333:9` → 众数 **333 px/s = 5.55 cols/s**。旧的 5.2（312 px/s）**不是任何一档**，比主峰慢 6.3%（`5.2 / 5.55 = 0.937`，即主峰快 6.7%）。
- 命中盒：`hitRadius.cols` 精确值 `0.25:358, 0.1667:44, 0.3333:39, 0.2117:17, 0.5:16, …`；6 条没有 `hitRadius`。`0.25` 是 CollisionRect 的众数，所以保留为回退值。
- 溅射：217 条带 `splash` 对象，其中 **180** 条 `damage > 0`（37 条只有半径没有伤害）。
- 穿透：**41** 条带 `pierce`，但只有 2 条给了 `maxTargetHits`（`HeathSeekerDefaultProjectile` 3、`TudoDefaultProjectile` 5），其余 39 条只记概率衰减。

### 覆盖：content.pack 引用的弹道名

`content.pack` 的 plant actions 一共引用 **389 个不同的 projectile name**，其中 **383 命中表**，6 个未命中：

| 未命中 id | 说明 |
| --- | --- |
| `0` | 数据里的占位字符串，不是弹道 |
| `ElectricPeaPlantfoodSub` | 只在 plantfood 子效果里出现，表里没有 |
| `GeishaSuperDefault` | 同上 |
| `InfernoProjectileDefault` / `InfernoProjectilePlantfood` | 同上 |
| `ThrownMedusaParticle` | 同上 |

这 6 个按「未命中」路径处理：沿用旧常量 + `projectile_unknown` 事件（每关每个 id 只报一次，见 §4），不抛异常。

## 3. 引擎现在取哪些数

| 字段 | 取自表的哪一项 | 回退 |
| --- | --- | --- |
| 飞行速度 | `speed.colsPerSec`（> 0 时） | `tuning::kShotSpeedColsPerSec`（5.2） |
| 命中盒 | `hitRadius.cols`（> 0 时） | `tuning::kShotHitRadius`（0.25） |
| 轨迹 | `trajectory`：`arc`/`drop` → `lobbed`，`static` → 不推进 x | straight |
| 落点 | `landX = x + speed * tuning::kLobFlightSeconds`（仅 lobbed） | 0.75 s 飞时 |
| 溅射伤害 | `splash.damage`（> 0 时，绝对伤害，覆盖 `damage * kSplashNeighbourFactor`） | `damage * 0.5` |
| 溅射半径 | `splash.radius`（> 0 时） | `tuning::kShotSplashRadiusCols`（0.6） |
| 穿透上限 | `pierce.maxTargetHits`（> 0 且调用方没给时） | 调用方传值 |
| 直接伤害 | `baseDamage`（> 0 且调用方 `damage <= 0` 时） | 调用方传值（植物 JSON 的 30/40…） |

四处调用点全部受益，无需各自改：`action_runner.cpp` 的 projectile 与 plantfood 分支、`registry.cpp` 的 `familyShoot` / `familyLob`。后两者原本把**植物 id** 当弹道名传下去（永远查不到表），现在改为 `action->projectile->name`，只有数据里没有 action 时才退回植物 id。

`WorldOptions::projectiles`（默认 `true`）可以关掉查表，用于证明「默认开着」这件事本身有影响：关掉之后 `PeaDefault` 也回到 5.2，且不发任何 `projectile_unknown`。

## 4. 新增的诊断（不抛异常）

- `projectile_unknown {projectile,row,x}`：表里没有这个 id。
- `projectile_variant_fallback {projectile,pkg,variants}`：该 id 有 pkg 专属副本，但表只记录**哪些键不同**、不记录值（见 §6），所以用 canonical 数值并把替换说出来。

两者都按 id 去重（`World::notedProjectiles_`）：一株植物一分钟几十发，逐发上报会把真正有用的那条埋掉。

## 5. 测试断言（`native/tests/projectile_table_test.cpp`）

| 测试 | 断言 |
| --- | --- |
| `testTableLoads` | 602 条；straight 374 / arc 118 / drop 59 / static 42 / unknown 9；180 条带溅射伤害；41 条带穿透 |
| `testPeaUsesTableNumbers` | `PeaDefault` 5.55±0.01 且 **严格大于** `kShotSpeedColsPerSec`；命中盒 0.25 |
| `testHitBoxesPerProjectile` | `AcidLemonSliceProjectile` 0.3333±0.001、`AquaWeedShark` 0.5，且两者相差 > 0.1（否则这条测试什么也没证明） |
| `testVariantSelection` | `CannonballDefault` 有 2 个 variant；`hasVariantFor("pkg_0839_LevelDefinition")` 为真、`hasVariantFor("pkg_2082_ProjectilePropertySheet")` 为假、空串为假 |
| `testUnknownIdFallsBackToConstants` | 未知 id → 5.2/0.25 + `projectile_unknown`；`projectiles=false` 时 `PeaDefault` 也是 5.2 且无事件 |
| `testTableIdReachesTheShot` | 手搓 `spawnShot` 后 `ShotEntity.speed == 5.55`、`hitRadius == 0.3333`、`CabbageDefault` 的 `lobbed` 为真且 `landX > 1.0` |
| `testPeaFlightMatchesTable` | `frontyard_1` 种豌豆，取场上第一颗 `PeaDefault`，20 tick 位移 == `5.55 * 20/60`±0.02；另起一局单发 30 伤害打掉 30 |
| `testLobLandingZone` | 玉米投手弹道在 `x=1.0` 发出：路径上 `x=2.0` 的僵尸**不掉血**，落在 `landX` 的僵尸掉血 |

## 6. 已知差距（都是数据本身的边界，不是实现偷懒）

1. **variant 没有数值**。`variants[]` 每项只有 `{canonical,pkg,same,differingKeys[]}`，`differingKeys` 只列键名。所以 `CannonballDefault` 在 `pkg_0839_LevelDefinition` 下的真实速度/伤害无法重现，只能用 canonical 数值并发 `projectile_variant_fallback`。
2. **穿透上限 39/41 条为 null**。表记的是 `initialChance/chanceReductionPerHit`（概率衰减），不是命中个数；只有两条给了 `maxTargetHits`。引擎只在这两条上设 `shot.pierce`，其余保持调用方的值，不臆造上限。
3. **z 分量不能积分**。`CabbageDefault` 是 `velocity.z{500,700}` + `acceleration.z = -10`，按表算飞行时间 `700/10 = 140 s`，与 `lifetime`/实际手感都不符（单位不是 px/s² 就是被归一化过）。本实现取 `tuning::kLobFlightSeconds = 0.75 s` 作飞时，落点由**水平速度**决定，不假装能解出真实弹道。
4. **离群命中盒**。`RenaiTileLeftProjectile` / `RenaiTileRightProjectile` 的 `hitRadius.cols = 166.6667`（CollisionRect 宽度单位错），`ZomboniProjectile` 16.6667。三条都**没有被任何 plant action 引用**，所以原样保留、不裁剪——裁掉会掩盖数据问题。被引用的最大命中盒是 `FireGourdFireDefault` 2.5 / `TigerstoolProjectileDefault` 2.25，那是真正的范围弹。
5. `static` 类弹道（42 条）不在 `stepShots` 里推进 x，但它们本来多用于僵尸/关卡特效，植物侧几乎不用。

## 7. 门禁与证据

| 项 | 结果 |
| --- | --- |
| `pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\s5b'` | **17/17 Passed**，`Built and tested: C:\pvzbuild\s5b\Release\PvZ2SHUTTLE.exe`，exit 0 |
| `pwsh -File tools/build_native.ps1 -BuildDir 'C:\pvzbuild\s5b-desktop'` | **22/22 Passed**，exit 0 |
| `python tools/engine_smoke.py --exe C:\pvzbuild\s5b\Release\PvZ2SHUTTLE.exe --out build/engine_smoke.projectile.json` | 32 场景，结构检查全过，exit 0 |

### smoke 基线（预期变化，共 2 条）

| 场景 | 旧基線 | 新值 | 原因 |
| --- | --- | --- | --- |
| `frontyard_1 script` | `0xac1156c1ef5ccf69` | `0x6286cea661ecbfee` | 脚本里种了豌豆，弹速 5.2 → 5.55，命中时刻全部提前 |
| `beach_23 win` | `0xde03536c990dee92` | `0x2f8ac180ac294f8c` | 同一局因此提前 4 tick 结束（1538 → 1534） |

其余 30 个场景哈希不变——它们没有种植物，没有子弹。

**`native/generated/engine_smoke.json` 我没有覆盖**（不在本任务写作用域）：上表两条需要由门禁持有者用 `pwsh -File tools/check_all.ps1 -AllowMatrixChange` 刷新，否则 `check_all` 的 engine smoke 步会报这 2 条差异。

### 反向探针（各打红一次，已还原）

| 探针 | 改动 | 输出 |
| --- | --- | --- |
| A | `spawnShot` 末尾强制 `shot.speed = tuning::kShotSpeedColsPerSec`（假装表没接线） | `projectile table test failed: the shot must fly at the table's 5.55, got 5.200000` |
| B | `stepShots` 里 `if (shot.x + shot.hitRadius < shot.landX) continue;` 改成 `if (false) continue;` | `projectile table test failed: a lobbed shot must not hit a zombie it flies over, hp=960.000000` |

还原后 `world.cpp` sha256 `BB734598D3B87198335F03DF95750FF958BBF01A5F1AD48ABE8B12B04F5CDDB5`、`projectile.cpp` sha256 `992F104E51D919758E13223A8D5FB5D876501D0A7A12871A6863B22229A4BB14`，`PROBE_` 残留 0，单测复绿。

## 8. 改动文件

- 新增：`native/src/engine/projectile_table.hpp`、`native/src/engine/projectile_table.cpp`、`native/tests/projectile_table_test.cpp`
- 修改：`native/src/engine/entity.hpp`（`ShotEntity` 新增 `trajectory/hitRadius/splashRadius/splashDamage/landX/lobbed`）、`native/src/engine/tuning.hpp`（新增 `kShotSplashRadiusCols`、`kLobFlightSeconds`，并给 `kShotSpeedColsPerSec` 注明「不在任何主峰上，只作回退」）、`native/src/engine/world.hpp`（`WorldOptions::projectiles`、`projectiles_`、`notedProjectiles_`）、`native/src/engine/world.cpp`（构造期加载表 + `spawnShot` 查表）、`native/src/engine/projectile.cpp`（重写 `stepShots`）、`native/src/engine/registry.cpp`（`familyShoot`/`familyLob` 改传 action 的弹道名）、`native/CMakeLists.txt`（`projectile_table.cpp` 入库 + `projectile_table` 测试注册）
