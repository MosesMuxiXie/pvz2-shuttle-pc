# S5.11 护甲接线 — 定稿

> 开工：2026-11-20 23:5x；暂停：2026-11-21 11:31（用户要求暂停所有进程）；复验与收尾：2026-11-21 12:0x–2026-11-23
> 结论：**audit 18/18、desktop 23/23、冒烟 32 场景 0 变化、`check_all` EXIT=0**。
> 本文件区分「我跑的」和「captain 复验的」，也保留了我暂停时留下的未验证项，便于判断某条绿是哪次改动带来的。

---

## 0. 一句话结论

`native/generated/armors_from_pack.json` 的 102 条护甲记录进了内核：`ArmorTable` 解析层（新 `native/src/engine/armor.hpp/.cpp`）；`ZombieEntity.armorLayers` 按 sheet 原序建层；`damageZombie` 从「单池扣血」改成「按 flags 逐层遍历」；`battle_view` 不再按僵尸 id 猜骨骼名。所有旧基线逐字节不变（单层僵尸的哈希记录没动），**冒烟 0 变化**就是这条的机器证明。

---

## 1. 两个人的验证矩阵

| 项 | 谁跑的 | 命令 / 构建目录 | 结果 |
|---|---|---|---|
| audit 构建 + 全用例（修 id 空间前） | wirer | `pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\arm1'` | `100% tests passed, 0 failed out of 18`，第 17 项 `armor` Passed |
| audit 构建 + 全用例（修 id 空间后） | wirer | 同上 | `100% tests passed, 0 failed out of 18`，`Built and tested: C:\pvzbuild\arm1\Release\PvZ2SHUTTLE.exe`，exit 0，18.86 s |
| 冒烟（修 id 空间**前**） | wirer | `python tools/engine_smoke.py --exe 'C:\pvzbuild\arm1\Release\PvZ2SHUTTLE.exe' --out build/engine_smoke.armor.json` | 32 场景，**2 条变化**：`world cowboy 0xeb036737659cbc46→0x53781efd585e9004`、`world muji 0xb91d57f7c4ff004c→0x67c4255c4e372f9b`（tick 7200 / status playing 均未变） |
| 冒烟（修 id 空间**后**） | **captain 复验** | 同命令（修好的构建脚本） | **0 条变化**：32 场景逐条与基线一致，`world cowboy`/`world muji` 都回到基线值 → 那两条位移确实是 bug，不是新语义 |
| audit 构建 | **captain 复验** | `C:\pvzbuild\resume-audit` | `100% tests passed, 0 failed out of 18`，exit 0 |
| **desktop 构建（我从未编过）** | **captain 复验** | `C:\pvzbuild\resume-desktop` | **23/23 通过**，exit 0，293 s；`zombieArmorArmature()` 编译无错，`battle_view.cpp` 的 C4244/C4267 干净 |
| 全量门禁 | **captain 复验** | `pwsh -File tools/check_all.ps1 -NoContent -AllowMatrixChange -UpdateLedger` | **EXIT=0**，265 s；audit 18/18、desktop 23/23、Python 296、test ledger 三项一致、矩阵已刷新（护甲行接线数 **91** = 被至少一只僵尸引用的护甲数） |

我暂停时留下的未验证清单（desktop 从未成功跑过、修后冒烟 diff 未知、反向探针未跑、`check_all` 未跑、`engine_smoke.json` 未动、`PARITY_BASELINE.md` 未动）已在上面四行里全部关闭。

---

## 2. 已落盘的改动

新增两个文件，其余就地改。`native/CMakeLists.txt:69-72` 的 `pvz_progress` 链接**没动**。

| 文件 | 改动 | 锚点 |
|------|------|------|
| `native/src/engine/armor.hpp`（新） | `ArmorFlag` 位掩码（damageable / invincible / passdamage / droppable / absorboverflow / metallic / helm / body / visibleondestroy）、`armorFlagBit`/`armorFlagNames`、`ArmorSpec`、`ArmorLayer`、`ArmorLayerState`、`ContentArmorBridge`、`ArmorTable` | — |
| `native/src/engine/armor.cpp`（新） | 解析 `native/generated/armors_from_pack.json`；失败抛 `armor table: <path>: <reason>`；`shared()` 复用 `plantfood.hpp` 的 `generatedDir()`（环境变量 → 编译期默认 → 从 `current_path()` 向上找 `native/generated`）；`counts` 全部读自 sheet 的 `counts` 节点 | — |
| `native/src/engine/entity.hpp` | `#include "armor.hpp"`；`ZombieEntity` 加 `std::vector<ArmorLayerState> armorLayers`（**顺序即 sheet 顺序，永不排序**；`armorHp/armorMaxHp` 保留为「有血池层之和」，视图与 hash 继续读它们） | — |
| `native/src/engine/world.cpp` | `armorTable()` 单例 + 构造函数期加载；`spawnZombie` 按 id 空间建层；`damageZombie` 层遍历；`hash()` 追加多层记录 | `:43`、`:90`、`:818-849`、`:935-958`、`:1153-1155` |
| `native/src/battle_view.cpp` | 骨骼名走 `zombieArmorArmature()`（content armature → 桥→sheet layer 且模型里真有该骨骼 → 缺省 `Cone` 并报一次）；灰块/橙锥替身改按 `metallic` flag | `zombieArmorArmature` |
| `native/CMakeLists.txt` | `pvz_engine` 加 `src/engine/armor.cpp`；注册 `armor` 测试（`TIMEOUT 180`） | :40-53、测试块尾部 |
| `native/tests/armor_test.cpp`（新） | 6 个用例：counts / 层序与 flags / invincible 层 / content 桥 / 引擎层 / invincible 阻挡；**captain 后续补了第 7 个 `testContentZombieKeepsContentArmor`** | — |
| `native/tests/engine_test.cpp` | 新增 `testArmorLayers`：invincible 层打满伤害不死且下层不扣血；三层僵尸首层先破 | `testSnapshotContract` 之前、main 紧跟注册 |

### 2.1 每个 flag 落到哪个分支

`damageZombie` 现在遍历 `armorLayers`（`world.cpp:935-958`），分支顺序即语义：

| flag | 落点 | 行为 |
|------|------|------|
| `invincible` 且**无** `passdamage` | `:935-940` | 发 `armor_blocked` 后**直接 return**：本体不掉血，层也不掉（纯阻挡，如 `kongfu_qigong_wave` 的 `NunchakuDefault`、`lostcity_excavator` 的 `ShovelDefault`） |
| `invincible` + `passdamage` | `continue` | 层不吸收，伤害交给后面的层/本体（如 `mausoleum_drunk` 的五口坛子、`fairy_gargantuar`） |
| 有血池（`maxHp > 0`） | `:941-955` | `absorbed = min(layer.hp, rest)`；层没破就 return；破了发 `armor_broken`，`droppable` 再发 `armor_dropped` |
| `absorboverflow` | `:957-958` | 层破后**吞掉剩余伤害**并发 `armor_absorbed`，不传给本体（全表只 1 条） |
| 无 `passdamage` 的破层 | `break` | 溢出直达本体 hp —— 与 S5.11 之前的单池行为一致（这是旧基线不变的原因） |
| 悬空 id（`AngerManagement` / `HideLayer` / `InvincibleArmor`） | 建层时 | 保留成「无 flags、无血池」的层：层数诚实，但不参与吸收 |

### 2.2 哈希策略

`hash()` 在每条 `Z…` 记录后，**仅当 `armorLayers.size() > 1`** 追加 `A<hp0>,<hp1>,…;`（`world.cpp:1153-1155`）。
理由：单层僵尸的护甲完全由已有的 `armorHp` 描述，加记录只会让 S5.11 之前的所有基线无谓位移；多层僵尸才需要区分「哪一层还剩多少」。冒烟 0 变化验证了这个判断。

### 2.3 id 空间（本任务最贵的坑）

- sheet 的 `zombies[].zombieId` 是 **pack id**（`af_bald`、`lostcity_excavator`…），content 的 55 个僵尸 id 里只有少数与之同名。
- 实测：**20 个 content 僵尸 id 同时在 sheet 里有 `zombies[]` 行**（`mummy`、`mummy_armor1/2`、`pirate`、`pirate_armor1`、`cowboy`、`cowboy_armor1`、`future`、`future_armor1`、`dark`、`dark_armor1`、`beach`、`iceage`、`lostcity`、`kongfu`、`eighties`、`gang_flag`、`gang_molotov`、`gang_gargantuar`、`gang_imp`），其中 6 行 armorIds 非空，而 **content 侧根本没给这些僵尸挂甲**（`cowboy` → sheet 给 `['CowboyHatDefault']`）。
- 所以 `spawnZombie` 必须**按 id 空间分流**（`world.cpp:825-827`）：content 僵尸只走 content 定义 + 桥；只有 pack-only 僵尸才按 sheet 的 zombie id 查行。
- 我第一版写成「先查桥，空了再按 id 查 sheet 行」，于是 `world cowboy`、`world muji` 两关冒烟位移；修成分流后 0 diff。
- 回归用例：`armor_test.cpp::testContentZombieKeepsContentArmor`（captain 补）—— `cowboy` 生成后 `armorLayers` 必须为空、`armorHp == 0`；反方向 `conehead` 必须保留 1 层 `ConeDefault`、`armorMaxHp == 370`。

---

## 3. 数据事实（`native/generated/armors_from_pack.json`，python 实测）

- `counts`：`armors 102`、`canonicalArmors 97`、`embeddedOnlyArmors 5`、`embeddedRows 9`、`unusedArmors 14`、`dangling 3`、`danglingReferences 13`、`withArmorLayer 89`、`withoutArmorLayer 13`、`withHitpoints 101`、`withoutHitpoints 1`、`zombiesWithArmor 276`、`zombiesWithoutArmor 804`、`zombieTypes 1127`、`contentZombies 55`、`contentArmored 16`、`contentBridged 16`、`contentExact 8`、`contentHeuristicBridge 2`、`contentHpDifferences 0`、`duplicateZombieIds ["heavy_shield","kongfu_gargantuar"]`。
- `flagCounts`：`damageable 72`、`invincible 16`、`passdamage 33`、`droppable 62`、`helm 49`、`metallic 20`、`body 20`、`visibleondestroy 4`、`absorboverflow 1`、`none 1`。
- `armorCombination`：0 层 851 / 1 层 260 / 2 层 9 / 3 层 5 / 5 层 2。矩阵里的「护甲接线 91」= 被至少一只僵尸引用的护甲数。
- **`hitpoints` 101 vs 我数出的 96**：sheet 把 4 条 sentinel（`BaseHealth == INT_MAX`）计为「有血」，我按「非 sentinel 且 > 0」数得 96。最终**直接读 sheet 的 `counts`**，不自己数；`hitpointsSentinel` 仍逐条保留，`poolsHitPoints()` 用 `maxHp > 0`。
- `fieldMap`：`hitpoints←BaseHealth`、`flags←ArmorFlags`、`droppable←ArmorFlags 含 "droppable"`、`art.armorLayer←ArmorLayers[0]`、`art.layers←ArmorLayers`、`breaksInto`/`NextArmor` 原版无字段（null）。
- `zombies[].armorOrderNote` 原文：`ZombieArmorProps order is kept as stored; reading it as outermost-first is an inference from the multi-armor zombies in the report, not a pack field` → **代码里不排序**，也不假设「第 0 层是最外层」。

---

## 4. 构建期真问题（三条，都修了）

1. `armor.hpp` 里 `bridges_` 同时被声明成 map 和 vector（`error C2371: redefinition`）→ vector 改名 `bridgeRows_`。
2. `zombieRows_` 同时当计数器和 map（`error C2039`）→ 拆成 `zombieRowTotal_` + `zombieRowCounts_`。
3. `withHitpoints()` 自己数（96）与 sheet（101）不符 → 改为读 sheet `counts`（见 §3）。

另有两次是环境/操作问题，不是代码问题：
- 我以 `*>` 重定向后台跑 desktop 构建，PowerShell 把命令解析成打印帮助，`DESKTOP_EXIT=64` —— 这是我写错重定向，不是编译失败。
- 2026-11-21 11:31 之后所有构建起不来，`CMake Error: No CMAKE_CXX_COMPILER could be found`：根因是**环境里有大小写重复的代理变量**（`NO_PROXY` 与 `no_proxy` 同时存在），MSBuild 的 CL 任务把它们塞进大小写不敏感的 Hashtable → `MSB6001: Item has already been added. Key: 'NO_PROXY'`。`tools/build_native.ps1` 原来只删小写名，删不掉重复项；captain 改成先把只差大小写的名字收敛成一份、再用 `ProcessStartInfo` 以干净环境启动 cmake/msbuild/ctest。**恢复后直接用脚本，不要自己清环境变量。**

---

## 5. 顺带条款（captain 要求写进本报告）

1. **`pierce` 的 39/41 条 `maxTargetHits` 为 null 不是漏接。** sheet 只记穿透概率衰减（`initialChance`/`chanceReductionPerHit`），不记命中次数上限；`ProjectileSpec::hasPierce/pierceHits` 只在真有 `maxTargetHits` 时填（`HeathSeekerDefaultProjectile`=3、`TudoDefaultProjectile`=5），其余保持 0 = 「不限次数、只按概率衰减」，没有臆造数字。
2. **`CabbageDefault` 的 140 s 飞时不成立。** 表里 `velocity.z{500,700}` + `acceleration.z -10`，按积分得 700/10 = 140 s，与任何关卡时长对不上；实现改用水平速度 + `kLobFlightSeconds = 0.75` 推落点（`world.cpp` 的 `spawnShot`）。
3. **离群命中盒原样保留**：`RenaiTileLeft/Right` 166.67 cols、`ZomboniProjectile` 16.67 cols 照 sheet 存值，不做钳制——钳制会把「数据错」变成「数据被我改过」，失去可复查性。

---

## 6. 已知缺口

- 视图的骨骼名选择**没有目视验证**：desktop 已 23/23 通过（含 `battle_render` 冒烟画一帧），但「带甲僵尸画出来用的是哪根骨骼」没有逐僵尸截图比对。layer 名（`zombie_armor_bucket_norm`）与 content 骨骼名（`Bucket`）不是同一套，代码里靠 `Model::findArmature` 的存在性决定用谁。
- 13 条 `withoutArmorLayer` 的护甲没有骨骼名，走缺省 `Cone` 并 `reportOnce` 记录；如果以后要精确，需要人工补一张 armorId→骨骼名表。
