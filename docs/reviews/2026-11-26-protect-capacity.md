# C55 — 保护目标同格叠加：11 关容量不足改成真能赢

Task: **t89 / A5** · Attempt: `83f8d08c-1058-4405-a731-9877afcc0387` · Date: 2026-11-26
Author: auditor (`agent-3`) · Repo: `D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc` (HEAD `784e7d6`, 未 commit)

## 0. 结论

T59 记录的 11 关「`placed < mustProtectCount`」现在**全部能摆满**：一格承载多株保护目标，
判活按株数、伤害从最外株开始。`--run-level` 逐关实测 `protectCapacityShortfall: false`、
`protectPlaced == protectRequired == 数据里的株数`，没有任何一关走到 clamped 分支。
反向探针两条各打红一次并已还原（§5）。

一处**必须由队长接线**的缺口：`protectClamped` 键还没出现在 `--run-level` 的输出里，
因为写它的那三行在 `native/src/main.cpp`，不在本任务的写作用域（§7.2 给出补丁）。

## 1. 改了什么

| 文件 | sha256(12) | 字节 |
|---|---|---|
| `native/src/engine/entity.hpp` | `8F66F21DC010` | 10,181 |
| `native/src/engine/world.hpp` | `30F8E0889AD0` | 39,881 |
| `native/src/engine/world.cpp` | `FD5985F23923` | 116,388 |
| `native/src/battle_view.cpp` | `3CBC7BF7E735` | 53,351 |
| `native/tests/mechanics_test.cpp` | `42B9B0812632` | 57,225 |

### 1.1 同格叠加载体

`PlantEntity` 与 `PlantView` 各加一个 `int stackDepth = 0`（0 = 格底，数字越大越外）。
一格多株不是新的容器：`plants_` 仍然是那条扁平的 `std::vector<PlantEntity>`，
同格植物的先后关系由 `stackDepth` 表达，`World::protectStackAt(row, col)`
（`world.cpp:1691-1700`）按 `stackDepth` 升序把它们取出来。

`layInitialField()`（`world.cpp:889-989`）原来用一个 `place` lambda，遇到
`plantAt() != nullptr` 就把保护目标记成 unplaced。现在：

- `stackAt(row, col)` 数该格已有几株（`world.cpp:895-901`）；
- 关卡自己的 `initialPlants` **仍然一格一株**（`!isProtected && depth > 0` 丢弃），
  所以没有任何非保护关卡的棋盘形状被这次改动改变；
- 只有保护目标可以叠到 `World::kMaxProtectStack = 8`（`world.hpp`）；
- 摆完后若 `protectRequested_ > protectedPlants_`，按行/列扫过棋盘，在**数据已经选中的格子**上
  克隆该格最深的保护目标补足（发 `protect_plant_stacked{type,row,col,depth,id}`），
  直到满足需求或每格到上限；仍不足才 `protectClamped_ = true`，发
  `protect_requirement_clamped{level,must,placed}` 与旧的 `protect_capacity_shortfall{level,placed,must}`。

`requiredProtectedPlants()` 现在是 `std::min(mechanics_->protect.requiredSurvivors(), protectedPlants_)`，
`requestedProtectedPlants()` 保留数据原值 —— 这两个数是「要求」与「能摆」的分离，
报告和测试都引用它们。

### 1.2 伤害与判活顺序

- `plantAt(row, col)` 返回同格 `stackDepth` 最大的**活**植物（`world.cpp`），即「最外株」；
- 僵尸啃食时，原来取命中范围里第一株就 `break`，现在取**命中范围里 `stackDepth` 最大者**
  （`world.cpp:612`，`if (reachable == nullptr || plant.stackDepth > reachable->stackDepth)`），
  所以外株挡住内株；
- `damagePlant()` 的判负改用 `requiredProtectedPlants()`，`aliveProtectedPlants()` 数全部活着的保护目标，
  因此「一格里死掉内株、外株还在」时存活数真的减 1；
- `hash()` 不包含 `stackDepth`，`snapshot()` 才把它带进 `PlantView`。

### 1.3 绘制

`native/src/battle_view.cpp` 的植物循环按索引偏移：
`lift = stackDepth * 11.0f`、`sideStep = stackDepth * 7.0f`，`anchorX += sideStep`、`anchorY -= lift`。
`stackDepth == 0` 的像素坐标与改动前完全一致，所以没有叠加的关卡截图逐字节不变；
headless 渲染同样走这条路径，叠加关出图不崩（`battle_render` 桌面测试全绿，§6）。

## 2. 11 关逐关处置

数据来自 `native/generated/level_mechanics.json`（`protectThePlant.plants` 与 `initialPlants.placements`，
用 `build/t89/table.py` 直读，不经过编译器）。`clashCells` = 保护目标所在格中，
被本关 `initialPlants` 先占的格数 —— 这 6 关就是旧代码 `placed` 远小于 `must` 的全部原因。

| 关卡 | must | 株数 | 格数 | 最大同格 | clash 格 | 处置 | 实测 placed / required |
|---|---|---|---|---|---|---|---|
| carnival_23 | 6 | 6 | 3 | 4 | 0 | 数据自带叠加 | 6 / 6 |
| carnival_79 | 1 | 1 | 1 | 1 | 1 | pvine1 之上叠 1 株 | 1 / 1 |
| carnival_81 | 3 | 3 | 3 | 1 | 3 | lilypad 之上各叠 1 株 | 3 / 3 |
| chinesegarden_57 | 3 | 3 | 3 | 1 | 3 | lilypad 之上各叠 1 株 | 3 / 3 |
| egypt_74 | 4 | 5 | 3 | 3 | 0 | 数据自带叠加 | 5 / 4 |
| frontyard_51 | 6 | 6 | 5 | 2 | 0 | 数据自带叠加 | 6 / 6 |
| frontyard_53 | 2 | 2 | 2 | 1 | 2 | flowerpot 之上各叠 1 株 | 2 / 2 |
| lostcity_45 | 8 | 8 | 2 | **7** | 0 | 数据自带叠加 | 8 / 8 |
| lostcity_67 | 1 | 1 | 1 | 1 | 1 | peashooter 之上叠 1 株 | 1 / 1 |
| sky_31 | 5 | 5 | 5 | 1 | 5 | jalapeno/bombardmint 之上各叠 1 株 | 5 / 5 |
| sky_46 | 10 | 10 | 5 | 2 | 0 | 数据自带叠加 | 10 / 10 |

**两处数据更正（任务书写错了，以现表为准）**：

1. **最大同格数是 7，不是 3**。`lostcity_45` 在 (4,3) 叠了 7 株 (`must 8`，另一株在 (0,2))。
   `kMaxProtectStack = 8` 是按这个实测值留的余量，不是按 3。
2. **clash 关是 6 个，不是 5 个**：`carnival_79`、`carnival_81`、`chinesegarden_57`、
   `frontyard_53`、`lostcity_67`、`sky_31`。而且它们需要的**不是同名升级**：lilypad 上放 bloomerang、
   flowerpot 上放 melonpult、peashooter 上放保护目标 —— 类型不同，只能真叠加。

`egypt_56`（`mustProtectCount = 0` 且列了 15 株）按任务书的口径「不判负」：
`requiredSurvivors()` 返回 0，`requiredProtectedPlants()` 取 `min(0, 15) = 0`，
杀光也不进 `lost` 分支。它有 `clashCells = 0`，不在这 11 关里。

### 2.1 出厂数据上 clamped 不可达

补足循环只在「`protectRequested_ > protectedPlants_`」时工作，而 11 关的需求在叠加后恰好等于株数；
每格上限 8 大于数据最深的 7，所以出厂数据上 `protectClamped_` **永远为 false**，
`protect_requirement_clamped` 事件一条也不会发。capped 分支只能靠合成夹具触发，
`mechanics_test.cpp` 的 2i 用「遍历全部 286 个保护关，断言 required ≤ placed、clamped == 0」把这一点钉住 ——
它是**回归护栏**，不是「clamped 已被验证」的证据。这一点在报告里必须说清楚，
否则下一轮有人会以为 clamped 路径被执行过。

## 3. 测试

`native/tests/mechanics_test.cpp`：原有 2e/2f 两段按新语义重写，新增 2g/2h/2i/2j 四段
（run 表里加了 4 行调用）。

| 段 | 钉住什么 | 关键断言 |
|---|---|---|
| 2e `testProtectThresholds` | `egypt_74` 四保五 | placed 5、unplaced 0、无 `protect_plant_unplaced`、`protectStackAt(2,3).size()==3`、`deepestProtectStack()==3`、required 4、requested 4、`!protectClamped()`；杀 1 株仍 playing、杀第 2 株 lost |
| 2f `testProtectCapacityShortfall` | 11 关逐关不再短缺 | 每关 `protectedPlantCount() > 0`、shortfall 0、无 `protect_capacity_shortfall` / `protect_requirement_clamped`、required ≤ placed、status playing；`carnival_79` 叠 1 株、`plantAt(0,0)->stackDepth == 1`、杀唯一目标 lost；`beach_88`/`beach_14` 仍零 shortfall |
| 2g `testProtectStackOnOneCell` | 一格多株各自独立、顺序正确 | `lostcity_45` (4,3) 七株逐 index 校验 `stackDepth == i` 且都受保护；`plantAt(4,3) == stack.back()`；杀中间一株后该格仍有 6 株活、`plantAt` 换成别人；另用 5 关做「底非 target、上为 target、depth 递增」，**格子从数据里取**（见 §3.1） |
| 2h `testProtectDeathCountsEveryPlant` | 判活按株数、不按格 | `egypt_74` 杀叠里最内株 → alive 4、playing；再杀最外株 → alive 3、lost、`protectFailures() == 1`；`lostcity_45` 需全 8，杀最外株即 lost |
| 2i `testProtectRequirementNeverExceedsTheBoard` | 全库不变量 | 遍历 286 个保护关：required ≤ placed、`requestedProtectedPlants() == protect.requiredSurvivors()`、shortfall 0；末尾 protectLevels 286 / clamped 0 / shortCount 0 |
| 2j `testProtectLevelsInitialize` | 11 关逐关读数 | must/plants/placed 精确值（见 §2 表）、`!protectClamped()`、unplaced 0 |

### 3.1 两处必须记下来的返工

1. **格子不能猜**：2g 最初把 5 个关卡的格子写死成 `(0,0)` 之类，`carnival_81` 因此红
   （它的三格其实是 `(2,4)/(0,5)/(4,5)`，`(0,0)` 什么都没有）。改成从
   `LevelMechanicsTable::shared().find(id)` 里遍历 `protect.plants`，取**第一个同时出现在
   `initialPlants` 里的格子**再断言。教训：这 11 关的坐标属于数据，不属于测试。
2. **`InitialPlant` 没进作用域**：lambda 参数写 `const InitialPlant&` 时 MSVC 报
   `C2228: left of '.gridY' must have class/struct/union`（类型找到了别的东西）。
   补 `using pvz::engine::InitialPlant;` 才编过。

### 3.2 我顺手修掉的两段非本任务断言（归 wirer 所有，已告知）

这两段属于 t88 的写窗，但当时是红句挡住整条 `mechanics_test`，所以我改了最小的一处并在文件里留了注释：

- `testSunCapStopsTheBank`（`mechanics_test.cpp:775-779`）：carnival_82 的
  `initialPlants` 已有 `(2,1) cabbagepult`，第二次种植被 `world.cpp:1217 "cell occupied"` 拒；
  改种 `(2,2)`。
- `testBoardGridMaskIsCarried`（`:799-835`）：beach_94 是**传送带关**，`World::plant()`
  在 `world.cpp:1205` 就把 deck 卡挡成 `"not on the conveyor"`；21 个 mold 家族关卡同属此类。
  改成 `world.conveyorLevel() ? world.conveyorCards().front() : deck.front()`。
  另查明：**49 个带 `boardGrid` 的关卡全部是传送带关**（直读 `level_mechanics.json`，非传送带 0 个）。

## 4. 反向探针（两条，各红一次，已还原）

探针跑在**仓库副本** `C:\pvzbuild\probe89`（robocopy 出来的 `native/`，构建目录
`C:\pvzbuild\probe89build`），不碰共享工作树 —— 当时 wirer 正在 `world.cpp` 里做他自己的
`PROBE_T88A`，两边同时改同一文件必然打架。

**A. 关掉同格叠加**（`world.cpp:919`，`(!isProtected && depth > 0)` → `depth > 0`）：

```
mechanics test failed: egypt_74 lists five targets, so five must stand, got 4
EXIT=1
```

**B. 判活只数格底**（`aliveProtectedPlants()` 加 `&& plant.stackDepth == 0`）：

```
mechanics test failed: four of five surviving still satisfies the mission, got: lost
EXIT=1
```

还原后两个标记都从工作树与副本里消失（`Select-String PROBE_A89|PROBE_B89` 零命中），
真实树从未出现这两个标记。

## 5. 门禁与回归

| 门禁 | 结果 | 归属 |
|---|---|---|
| `build_native.ps1 -AuditOnly -BuildDir C:\pvzbuild\prot1` | **36/38 通过**，`Test #29 mechanics ... Passed 1.80 sec` | 红的两个不是本任务 |
| 同上，`catalog` | Failed | 长期基线红（本任务未触碰） |
| 同上，`progress` | Failed：`no mower was used, so the mower goal must pass` | 别人的目标/割草机改动 |
| `build_native.ps1 -BuildDir C:\pvzbuild\prot1d`（桌面） | **52/54 通过** | 同样只有 catalog + progress |
| `smoke_rebaseline.py --check` | 2 个场景差异 | 两个都**不是保护关** |

smoke 的两个差异，附证据说明与本次改动无关：

```
~ changed  world memorytour   hash 0xb83111a880dd862a -> 0x18cef11ac3dc5bb1  tick 7000->7200  status lost->playing  leaked 1->0
~ changed  beach_23 win       hash 0xb2a22229f25b92e6 -> 0xa47bd864b1d332bf  tick 1599->1597
```

`build/t89/check2.py` 直读 `level_mechanics.json`：`beach_23` 与 `memorytour_1` 的
`protectThePlant` 都是空（`protect False n 0`）；32 个 smoke 场景里
`protect` 字样命中 0 个 —— 也就是说 **smoke 根本不覆盖保护关**。
保护类证据只能来自 11 关 `--run-level` 读数（§2）与 `mechanics_test`；
那两条哈希漂移来自本轮的 tide/rail/vase 改动，不是 C55。

### 5.1 11 关 CLI 读数（改后，逐关）

`PvZ2SHUTTLE.exe --run-level content <id> --pack native\generated\content.pack --seconds 1`：

| 关卡 | protectPlaced | protectRequired | protectCapacityShortfall |
|---|---|---|---|
| carnival_23 | 6 | 6 | false |
| carnival_79 | 1 | 1 | false |
| carnival_81 | 3 | 3 | false |
| chinesegarden_57 | 3 | 3 | false |
| egypt_74 | 5 | 4 | false |
| frontyard_51 | 6 | 6 | false |
| frontyard_53 | 2 | 2 | false |
| lostcity_45 | 8 | 8 | false |
| lostcity_67 | 1 | 1 | false |
| sky_31 | 5 | 5 | false |
| sky_46 | 10 | 10 | false |

## 6. 剩余限制

### 6.1 `protectClamped` 还没输出（需队长接线）

`--run-level` 现在只写 `protectPlaced` / `protectCapacityShortfall`（`native/src/main.cpp:334-335`），
既没有 `protectRequired` 也没有 `protectClamped`。`main.cpp` 不在本任务写作用域，补丁三行：

```cpp
out["protectPlaced"] = world.protectedPlantCount();
out["protectRequired"] = world.requiredProtectedPlants();      // 新增
out["protectCapacityShortfall"] = world.protectCapacityShortfall() > 0;
out["protectClamped"] = world.protectClamped();                // 新增
```

`World` 侧的三个访问器（`requestedProtectedPlants()` / `requiredProtectedPlants()` /
`protectClamped()`）都已就位并有测试覆盖，接线后 `--run-level` 的其它键集不变。

### 6.2 clamped 在出厂数据上是死分支

见 §2.1：11 关补足后恰好等于需求，最深的同格 7 < 上限 8。想让这条路径真的跑一次，
需要合成一个「可用格 × 8 < must」的夹具关卡；本轮没做，2i 只能证明「出厂数据永不触发」。

### 6.3 啃食目标选择的可见副作用

僵尸现在打「命中范围里最外株」，因此同一格的内株在正常情况下不会被单独啃到 ——
只有溅射/爆炸这类按 id 选目标的伤害才能打到内株（2g/2h 就是用 `damagePlant(id)` 做的）。
这是「先打最外」的直接后果，不是漏实现。

### 6.4 顺带发现（不在本任务范围）

- `native/CMakeLists.txt` 的 `pvz_engine` 源列表把 `src/engine/plant_levels.cpp` **列了两次**
  （第 92 与第 95 行），`src/engine/mechanics.cpp` 那行还缺缩进。CMake 会去重，所以只是噪声，
  但两次失败的链接（`PlantLevelTable::shared` 等未解析）正是半初始化的 build 目录 + 这个重复行一起造成的。
- `pvz_progress` 的 `progress` 测试当前红（`no mower was used, so the mower goal must pass`），
  与本任务无关，但它使「全绿门禁」这条验收在本轮不可达。

## 7. 复现

```powershell
cd D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc
# 数据表（11 关 must/株数/格数/最大同格/clash）
python build\t89\table.py

# 单目标构建 + 测试
pwsh -File build\t87\tbuild.ps1 -BuildDir C:\pvzbuild\prot1 -Target mechanics_test -Configure
C:\pvzbuild\prot1\Release\mechanics_test.exe content native\generated\content.pack $env:TEMP

# 全量门禁（审计 / 桌面）
pwsh -File tools\build_native.ps1 -AuditOnly -BuildDir C:\pvzbuild\prot1
pwsh -File tools\build_native.ps1 -BuildDir C:\pvzbuild\prot1d

# 11 关读数
C:\pvzbuild\prot1\Release\PvZ2SHUTTLE.exe --run-level content egypt_74 --pack native\generated\content.pack --seconds 1

# smoke
python tools\smoke_rebaseline.py --check --exe C:\pvzbuild\prot1\Release\PvZ2SHUTTLE.exe

# 反向探针（副本，不碰工作树）
robocopy native C:\pvzbuild\probe89\native /E
#   然后按 §4 改 C:\pvzbuild\probe89\native\src\engine\world.cpp，再：
$env:PVZ_PROBE_REPO='C:\pvzbuild\probe89'
pwsh -File build\t89\tbuild2.ps1 -BuildDir C:\pvzbuild\probe89build -Target mechanics_test -Configure
C:\pvzbuild\probe89build\Release\mechanics_test.exe content native\generated\content.pack $env:TEMP
```
