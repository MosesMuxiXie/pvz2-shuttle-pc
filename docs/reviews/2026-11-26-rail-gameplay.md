# A2 铁轨玩法：192 关铁轨车（载植物 / 移动 / 撞僵尸）

日期：2026-11-26
作者：patcher（team s3-parity-sprint）
任务：t81（A2 铁轨玩法）
写作用域：`native/src/engine/rail.{hpp,cpp}`、`native/src/engine/tuning.hpp`、`native/src/engine/world.{hpp,cpp}`、`native/src/engine/entity.hpp`、`native/src/battle_view.cpp`、`native/src/main.cpp`、`native/tests/rail_test.cpp`、`native/CMakeLists.txt`、本文件。

---

## 0. 结论

| 项 | 结果 |
| --- | --- |
| 有铁轨的关卡 | **192**（`content/levels/*.json` 里 `extra.rail is true`），其中**有车 190 关**、声明了 rail 但 `minecarts` 为空 2 关 |
| 车数来源 | `extra.minecarts`（**行号数组**，本任务按内容层采信）+ 可选覆盖层 `native/generated/level_mechanics.json` 的 `levels.<id>.railcarts/rail/rows` |
| 表命中 | **0 条**（`level_mechanics.json` 今天一个关卡的 rail 字段都没有）→ 运行时全部回落到 content extra，已在测试里钉死 `RailTable::shared().size() == 0` |
| `rail` 事件 | `rail_carts`（建车一次）、`rail_move`（**每进一格一次**）、`rail_hit`（每格每僵尸一次）、`rail_derailed`（每车一次） |
| CLI | rail 关的摘要多一个 `"rail": {"carts":N,"movedCols":N,"hits":N}`；非 rail 关**没有**这个键 |
| 测试 | `ctest -R "^rail$"` → **Passed 2.62 sec**（1/1），7 段断言 |
| 反向探针 | 2 条，各自打红对应断言，原文见 §9 |
| smoke | 32 个场景里**只有 `('world cowboy','cowboy_1')` 变化**（hash 与 killed），其余 31 条逐条相同 |
| 不做的部分 | decorative 6 关、unknown 6 关不出车（§10 列 id）；DangerRoom 只取 `BaseRailcartCount`，`Layouts` 不建模 |

---

## 1. 数据从哪来：为什么走 `extra` 而不是 `level_mechanics.json`

任务给了两条路：读 `native/generated/level_mechanics.json` 的 `levels.<id>`，或者自己从 `content/levels` 读 `extra`，二选一写进报告。**结果是两件事同时成立**：

1. 表侧接口已经建好，但**今天表里没有数据**。`native/generated/level_mechanics.json`（4.8 MB）里出现 `rail` 字样的 37 处全部落在 `unknowns` / `sentinels` 的说明文本里，`counts` 里没有任何 rail 项，`levels.<id>` 里也没有 `railcarts` / `rail` / `rows` 字段。所以 `RailTable::shared()` 的命中数是 0。
2. 内容侧的数据是齐的而且是**权威的**：`content/levels/*.json` 的 `extra.rail`（bool）与 `extra.minecarts`（行号列表）由 builder 从原版包派生（`tools/contentc/rails.py`、`tools/contentc/levelextra.py:596` 注释「行号数组（如 [0, 2]）」）。

因此实现采用**「表优先、extra 兜底」**：`layRailCarts()` 先问 `RailTable`，表里没有这个关卡的行就退回 `level().extra`。今天实际走的一律是兜底分支，`rail_carts` 事件的 `source` 字段会写 `content extra`（表命中时写 `level_mechanics.json`），这样几年后表补上了也不用改代码。

`LevelDefinition` 本身早就带着 `extra`：`native/src/catalog.cpp:143` 的 `if (j.contains("extra")) { object(j.at("extra"), p, "extra"); l.extra = j.at("extra"); }`。所以 `World` 读它**不需要额外 I/O**，也不碰 `native/generated/**`。

### 1.1 `RailTable` 的错误口径

`native/src/engine/rail.cpp` 的错误串统一是 `rail table: <path>: <reason>`，与 `mechanics table:` 同形：

- `cannot open`
- `root is not a JSON object`
- `no levels object`（`levels` 在但没有一条 rail 行时不报错，`rows_` 保持空 —— 这是今天的正常状态）
- 别的 nlohmann 解析错误原文附带
- `generatedDir()` 解不出目录时：`rail table: the generated directory is unknown; set PVZ_GENERATED_DIR or run from the repository root`

`load()` 对 `levels.<id>` 的形状是宽松的：`rail` 是 bool（decorative 关的形态）就跳过不建行；`railcarts` / `minecarts` / `rows` / `Rows` 任一数组里，元素可以是整数，也可以是 `{"Row": n}` / `{"row": n}`；`0..7` 之外的行号直接丢弃（`World` 的 `rows_` 上限是 8）。

---

## 2. 数据事实（本任务实测，`content/levels` 1809 关）

| 事实 | 值 |
| --- | --- |
| `extra.rail is true` | **192** |
| 其中有 `minecarts` 非空 | **190** |
| 声明了 rail 但没有 `minecarts` | **2**：`cowboy_41`、`cowboy_42` |
| 单关最多几辆 | **5**（`cowboy_10` = `[0,1,2,3,4]`） |
| 行号直方图（车数按行统计） | `{0:45, 1:74, 2:132, 3:66, 4:24}` |
| 同一关重复行号 | 无 |
| `cowboy_1`（smoke 里唯一的 rail 场景） | `[2]` → 1 辆，第 2 行 |

原版有、客户端没有的量：**轨道的起始列、长度、速度、载量**。原版对象是 `work/obb_packages` 里的 `RailcartProperties`（Column/Row）与 `DangerRoomRailcartDesigner`（`BaseRailcartCount` / `Layouts`），客户端的 `content` 只派生到「哪几行有车」。这条差距是下面 4 个 fallback 常量的唯一理由，也是 §10 里「DangerRoom 的 Layouts 不建模」的口径来源。

---

## 3. 常量（全部标 fallback）

`native/src/engine/tuning.hpp` 新增 4 条，每条都带 `// fallback: tuning constant, no pack evidence`，与文件里既有的 fallback 注释同格式：

| 常量 | 值 | 用途 | 为什么是 fallback |
| --- | --- | --- | --- |
| `kRailSpeedColumnsPerSecond` | `0.5` | 车每 tick 前进 `0.5 * dt` 列 | `rails_report.json` 的 204 个关卡都有 rail 对象，但没有任何一个给「每秒几列」；0.5 列/秒 = 2 秒一格，9 列棋盘 18 秒走完 |
| `kRailCrushReachColumns` | `0.55` | 车中心到僵尸的碾压判定半径 | 原版没有给判定盒；0.55 比半格（0.5）略大，保证「看起来撞上了」就是撞上了 |
| `kRailCrushDamage` | `1000.0` | 每次碾压的伤害 | 复用割草机的「即死级」量级（`tickMowers` 用 `100000` 直接抹掉），但走 `damageZombie` 让护甲层、`zombie_died`、`killed_` 全部走既有通道 |
| `kRailCartHitPoints` | `3000.0` | 车被咬时的耐久 | 原版没有耐久字段；3000 让 derail 之后的车在被啃时能撑一会儿（`eatDps` 通常 100 量级），坏掉时发 `rail_derailed` |

任务明确要求 `kRailSpeedColumnsPerSecond = 0.5` 并标注 fallback，已照做；另外 3 个是实现「撞僵尸掉血」「到行尾停下挡僵尸」必需的伴随常量，一并按同格式标注。

---

## 4. 数据模型

### 4.1 实体（`native/src/engine/entity.hpp`）

```cpp
struct RailCartEntity {
  EntityId id = 0;
  int row = 0;
  int col = 0;            // 当前占的格（x 的整数部分，夹到 cols_-1）
  double x = 0.0;         // 列坐标，0 = 最左列左边界
  double hp = 0.0, maxHp = 0.0;
  bool alive = true;
  bool derailed = false;
  EntityId plant = 0;     // 车上那一株（0 = 空车）
  std::vector<EntityId> crushed;  // 本格已经碾过的僵尸，进新格时清空
};
struct RailCartView { EntityId id; int row, col; double x, hp, maxHp; bool derailed; EntityId plant; };
```

`Snapshot` 末尾增加 `std::vector<RailCartView> carts;`，视图层只读。

### 4.2 车的生命周期

1. **建车**：`World::layRailCarts()`（构造器里 `if (options_.rail) layRailCarts();`）。`extra.rail` 必须是 `true` 才置 `railDeclared_`；行号按声明序去重、过滤 `0 <= row < rows_`；每辆 `id = nextId_++`、`col = 0`、`x = 0.0`、`hp = maxHp = kRailCartHitPoints`；**非空才发** `rail_carts{level, carts, rows, source}`。
2. **移动**：`World::tickRail()`（`step()` 里 `tickMowers();` 之后）。`x += kRailSpeedColumnsPerSecond * dt`；`col = floor(x)` 夹到 `cols_-1`。
3. **进格**：`col != before` 时清 `crushed`、`++railMoved_`、发 `rail_move{cart,row,col}`、车上植物的 `col` 跟着改。**同一格只发一次**，因为只有跨格时 `col` 才变。
4. **碾压**：同一行、`|z.x - (col + 0.5)| <= kRailCrushReachColumns`、且不在 `crushed` 里的僵尸 → 记入 `crushed`、`++railHits_`、发 `rail_hit{cart,zombie,damage}`、`damageZombie(id, kRailCrushDamage, false, true)`。**每格每僵尸只碾一次**（`crushed` 在跨格时清空，所以车往前走还能再碾新出现的僵尸）。
5. **行尾**：`col >= cols_-1` → `derailCart(cart, "row-end")`：车停在最后一格、不再前进，成为障碍。
6. **挡僵尸**：derail 之后车的 `face = col + 1.0`。只有 `face-1.0 <= z.x < face` 的僵尸被夹到 `face` 并 `z.x` 不再前进（等价于被挡住），同时 `cart.hp -= z.eatDps * dt`。**只夹最近的一列**，不是整行 —— 否则车会把整行僵尸排成一条线，视觉与手感都不对。
7. **破损**：`cart.hp <= 0` → `derailCart(cart, "broken")` + `alive = false`，循环末尾 `erase` 掉。
8. **载植物**：`World::plantOnCart(type,row,col)`。车上植物被移除（`removePlant` / 被吃 / 铲掉）后，`tickRail` 会把 `cart.plant` 清 0。

### 4.3 种到车上：闸门顺序

`plantOnCart` 用与 `plant` 相同的一套错误串（`level finished` / `unknown plant: <type>` / `too many plants` / `not-in-deck` / `not on the conveyor` / `cooling down` / `not enough sun` / `cell out of bounds`），但顺序按铁路需要重排：**先定车、再定格**，于是铁路专属的两条错误排在植物与资源检查之前：

| 顺序 | 条件 | 返回 |
| --- | --- | --- |
| 1 | `finished()` | `"level finished"` |
| 2 | `inBounds(row,col)` | `"cell out of bounds"` |
| 3 | `cartAt(row,col) != nullptr` | **`"no cart"`**（铁路专属） |
| 4 | `cart->plant != 0` | **`"cart occupied"`**（铁路专属） |
| 5 | 目录里有这个植物 | `"unknown plant: <type>"` |
| 6 | `plants_.size() < kMaxPlants` | `"too many plants"` |
| 7 | conveyor 关卡：手牌里必须有这张 | `"not on the conveyor"` |
| 8 | deck 里有这张 | `"not-in-deck"` |
| 9 | `cooldown(type) <= tick_` | `"cooling down"` |
| 10 | `sun_ >= cost` | `"not enough sun"` |

一处交互边界：`plant()` 的 conveyor 分支（`conveyorLevel()` 为真时早退到 `plantFromConveyor`）在车格上不会走 `plantOnCart`。实测 `content/levels` 里 **conveyor 关卡 0 个**（`extra` 里根本没有 conveyor 键），所以今天这条路径与车格不相交；`plantOnCart` 自己带了手牌分支（`"not on the conveyor"`），有 conveyor 关卡时直接可用。
成功后 `cart->plant = plant.id`，并发一条带 `{"cart": cart->id}` 的 `planted` 事件（与地面种植的事件同名，多一个 `cart` 键区分）。普通 `World::plant` 里加了 `if (cartAt(row,col) != nullptr) return "cell occupied";`（在 gridItem 检查之后、cooldown 之前），保证「格子上有车」和「格子上有墓碑」是同一种拒绝。

---

## 5. 事件表

| 事件 | 何时 | 字段 |
| --- | --- | --- |
| `rail_carts` | 建车后一次（有车才发） | `level`, `carts`, `rows`（数组）, `source`（`level_mechanics.json` / `content extra`） |
| `rail_move` | 每跨一格一次 | `cart`, `row`, `col` |
| `rail_hit` | 每格每僵尸一次 | `cart`, `zombie`, `damage` |
| `rail_derailed` | 每车一次（幂等） | `cart`, `row`, `col`, `reason`（`row-end` / `broken`） |

`rail_move` 按格发、不按 tick 发，是任务点名的要求，也是探针 A 专门去破坏的性质。

---

## 6. 视图与 CLI

- `native/src/battle_view.cpp`：新增
  ```cpp
  std::string plantCard(engine::World& world, const std::string& type, int row, int col) {
      if (world.cartAt(row, col) != nullptr) return world.plantOnCart(type, row, col);
      return world.plant(type, row, col);
  }
  ```
  两处种卡路径（拖拽释放 `planted` 卡、点选 `selected_` 卡）都改走它 —— 于是「拖到车上」与「点车」都能种上去，而地面上仍是原来的 `world.plant`。`localized()` 补了 `"cart occupied"` →「这辆车上已经有一株植物了。」与 `"no cart"` →「这里没有铁轨车。」。绘制在 mowers 循环之后：钢灰箱体 + 四轮，位置 `boardX + cart.x * cellW`、`boardY + (row + 0.74) * cellH`。
- `native/src/main.cpp`：`--run-level` 的摘要里，`world.railLevel()` 为真才加
  ```cpp
  summary["rail"] = {{"carts", world.railCarts().size()}, {"movedCols", world.railMovedColumns()}, {"hits", world.railHits()}};
  ```
  非 rail 关**没有**这个键（本轮手工验证：`frontyard_1` 的摘要里查不到 `rail`）。

---

## 7. 测试（`native/tests/rail_test.cpp`，7 段）

| 用例 | 断言要点 |
| --- | --- |
| `testRailTable` | `RailTable::shared().size() == 0`（今天的表没有 rail 行）；`find("cowboy_1") == nullptr`；`RailTable::load(<不存在的文件>)` 抛且 `what()` 以 `rail table:` 开头 |
| `testCartCounts` | `cowboy_1` → 1 辆、`row 2`、`col 0`；`cowboy_10` → 5 辆且顺序等于 `extra.minecarts`；`cowboy_41/42` → `railLevel()` 真但 0 辆；`frontyard_1` → 无车 |
| `testPlantOnCart` | 合成关（`sun = 5000`、`deck = {"peashooter"}`）：`plantOnCart` 成功 → `plant()` 同格返回 `"cell occupied"` → 再 `plantOnCart` 返回 `"cart occupied"` → 别的行 `"no cart"`；`advance(3.0)` 之后植物 `col` 跟着车变、`row` 不变 |
| `testRailMoveEventsOncePerColumn` | 16 × 0.25 s 推进：`rail_move` 条数 == `movedCols`，列序 `1,2,3,…` 无重复 |
| `testCartCrushesZombie` | 第 2 行 3.0 列放一只 basic 僵尸，0.5 s 步进至多 12 s：`rail_hit` 恰 1 条、`damage == kRailCrushDamage`、`railHits() >= 1`、僵尸掉血或已死 |
| `testRailOffSwitch` | `WorldOptions.rail = false` → `railLevel()` 假、无车、无 `rail_move`、无 `rail_carts` |
| `testEveryRailLevelInitializes` | rail 关恰 **192** 个；§10 的 12 个 id 都不在里面；逐关构造 + `advance(5.0)` 不抛；有车的恰 **190** 关 |

CMake 注册（`native/CMakeLists.txt`，mechanics 测试块之后）：

```cmake
add_executable(rail_test tests/rail_test.cpp)
target_link_libraries(rail_test PRIVATE pvz_engine)
pvz_warnings(rail_test)
add_test(NAME rail COMMAND rail_test "${PVZ_TEST_CONTENT}" "${PVZ_CONTENT_PACK}" "${PVZ_TEST_TEMP}")
set_tests_properties(rail PROPERTIES TIMEOUT 180)
```

`pvz_engine` 的源清单加了 `src/engine/rail.cpp`。测试的 `WORKING_DIRECTORY` 沿用既有的 `${CMAKE_CURRENT_SOURCE_DIR}/..`（仓库根）—— `RailTable::shared()` 依赖 `generatedDir()` 从 cwd 上溯找 `native/generated`，cwd 不对会直接抛 §1.1 最后那条。

---

## 8. 验收证据（实测原文）

**测试**

```
ctest --test-dir C:\pvzbuild\rail1 -C Release -R "^rail$" --output-on-failure
1/1 Test #28: rail .............................   Passed    2.62 sec
```

直接跑 exe（cwd = 仓库根）：

```
C:\pvzbuild\rail1\Release\rail_test.exe <repo>\content <repo>\native\generated\content.pack C:\pvzbuild\rail1\Testing\fixtures
rail tests passed
```

**CLI**

```
PvZ2SHUTTLE.exe --run-level content cowboy_1 --pack native\generated\content.pack --seconds 20
"rail":{"carts":1,"hits":0,"movedCols":8}   status=playing tick=1200 hash=0x5e9228ecb72ad403
```

`frontyard_1 --seconds 5` 的摘要里没有 `rail` 键。

**smoke（32 场景逐条 diff）**

```
python tools\engine_smoke.py --exe C:\pvzbuild\rail1\Release\PvZ2SHUTTLE.exe --out C:\pvzbuild\rail1\smoke_generated.json
world cowboy : ('hash', '0xeb036737659cbc46', '0xcb83dd8dcba537f5')
world cowboy : ('killed', 0, 2)
其余 31 条：无差异
```

**桌面树（`C:\pvzbuild\rail1-desk`，`PVZ_ENABLE_DESKTOP=ON`）**

```
PvZ2SHUTTLE.vcxproj -> C:\pvzbuild\rail1-desk\Release\PvZ2SHUTTLE.exe      # battle_view 的改动在这里编译
battle_view_test.vcxproj -> ...\battle_view_test.exe                        # battle_render 用的就是这个

ctest -R "^battle_render$|^worldmap_render$|^menu_render$|^level_select_render$|^settings_render$|^garden_render$|^almanac_render$|^text_render$|^rail$"
1/8 rail ................. Passed  8.05 sec
2/8 text_render .......... Passed  1.58 sec
3/8 battle_render ........ Passed 15.21 sec     <- 无 rail 关的像素断言全部不变
4/8 worldmap_render ...... Passed  6.43 sec
5/8 menu_render .......... Passed 12.99 sec
6/8 almanac_render ....... Passed 11.07 sec
7/8 garden_render ........ Passed  4.75 sec
8/8 settings_render ...... Passed  6.31 sec
100% tests passed, 0 tests failed out of 8
```

**headless 截图（`--play-script … --snapshot`）**

```
PvZ2SHUTTLE.exe --play-script content cowboy_1 --pack native\generated\content.pack --seconds 12 --snapshot shot_cowboy_1.png
{"level":"cowboy_1","tick":720,"status":"playing","snapshotBytes":1563602,"hash":"0xca33d5c2eaa8f788"}
PvZ2SHUTTLE.exe --play-script content frontyard_1 … --snapshot shot_frontyard_1.png
{"level":"frontyard_1","tick":720,"snapshotBytes":1558495,"hash":"0x55286be793dc95cf"}
```

PNG 的 sha256 前 16 位：`cowboy_1` = `13C891B389A37399`，`frontyard_1` = `DECEB03A22F78049`。像素级核对（PIL 读 PNG，找车体钢灰 `#68707C` ±6）：

| 图 | 区域 | 钢灰像素数 |
| --- | --- | --- |
| `cowboy_1` | 车 12 秒后的位置（第 2 行、`x = 6.0` → 764..817 × 378..403） | **1040**（该框共 1325 px） |
| `cowboy_1` | 车起点（`x = 0` → 164..217 × 378..403） | **0**（车已经开走） |
| `frontyard_1` | 同一位置 | **0**（这个关卡没有车） |

这三行同时证明：车画出来了、车确实移动了、非 rail 关没有多出任何像素。
`killed 0 → 2` 是车把两只僵尸碾死了（默认剧本里它们走到了第 2 行）。只有 `world cowboy` 变，是因为 32 个场景里只有它是 rail 关（其余 `_1` 关都不在 192 关集合里）—— 这同时证明非 rail 关的 hash 没被 `'X'` 段影响到（`hash()` 里无车时一个字都不写）。

---

## 9. 反向探针（原文）

| 探针 | 改动 | 打红的原文 |
| --- | --- | --- |
| A | `if (col != before) {` → `if (true) {`（每 tick 都发 `rail_move`） | `rail test failed: one rail_move per column entered, got 240 for column 1` |
| B | 注释掉 `damageZombie(zombie.id, tuning::kRailCrushDamage, false, true);` | `rail test failed: the crushed zombie must lose hit points through damageZombie()` |

还原后 `rail` 重新 `Passed 2.62 sec`。**注意**：`Copy-Item` 还原会保留旧 mtime，MSBuild 会认为目标最新而不重编译，看到的是探针的失败还在。还原后必须 `(Get-Item <src>).LastWriteTime = Get-Date` 再构建。

---

## 10. 明确不做

1. **decorative 6 关不出车**：`egypt_46`、`frontyard_98`、`frontyard_143`、`lunarrainbowmarket_93`、`muji_27`、`pirate_67`。这 6 关在原版里有 rail 对象但 `carts = 0`（只有 `Rails` 路径），content 里 `extra.rail` 也不是 `true`，所以 content 驱动的表天然不出车。
2. **unknown 6 关不出车**：`fairy_31`、`future_66`、`future_69`、`future_70`、`iceage_65`、`plantagenet_47`。这 6 关既没有可解析的 rail 对象、也没有参数，`rails_report.json` 把它们标成 `unknown`。
3. **`cowboy_41` / `cowboy_42`**：`extra.rail` 是 `true` 但 `minecarts` 为空 → `railLevel()` 真、0 辆车、不发 `rail_carts`。测试与报告都按这个口径钉住。
4. **DangerRoom 的 `Layouts` 不建模**：只取 `BaseRailcartCount`（多少辆）这一层语义。`Layouts` 给的是每辆车在关卡里的具体排布形状，客户端没有对应字段，建模它需要凭空发明数据。
5. **不做轨道起始列/长度/速度**：见 §2 与 §3，这四样原版才有，客户端只有「哪几行有车」。车一律从第 0 列出发，速度用 fallback 常量。

---

## 11. 并发与踩坑

1. **`world.cpp` / `world.hpp` 同时被 A1（vasebreaker）改**：构造器末尾多出 `if (vasebreaker_) layVases();`，`step()` 里 waves/spawners/skySun 被 `if (!vasebreaker_)` 包住。一次大块 `edit` 因为锚点变了直接失败（`old_string was not found`）。教训：每步 `edit` 前先读当前行文，用短锚点。
2. **`Copy-Item` 还原不触发重编译**：见 §9 末尾。
3. **`NO_PROXY` / `no_proxy` 重复让 CL.exe 报 MSB6001**：`tools/build_native.ps1` 用 `ProcessStartInfo.EnvironmentVariables.Clear()` 重建环境绕开；直接在 pwsh 里调 cmake 会踩，所以本任务用同款去重的小脚本 `C:\pvzbuild\nbuild.ps1` 做增量构建。
4. **`generatedDir()` 依赖 cwd**：手跑 exe 必须在仓库根，否则 `rail table: the generated directory is unknown; ...`。ctest 侧已由 `WORKING_DIRECTORY` 覆盖。
5. **`level_mechanics.json` 今天没有 rail 数据**：这不是 bug，是「表还没人写」。`RailTable` 的接口与错误串已按最终形态建好，表补上后 `source` 会自动变成 `level_mechanics.json`，`testRailTable` 里那条 `size() == 0` 断言会提醒下一个人改它。
6. **队友的中间态会打红别的测试**：本轮隔离树 `C:\pvzbuild\rail1` 里 `engine` 失败 `ailmint must be pack-only, not in content JSON`、`vase` 失败 `beach_69 must carry 12 sheet rows, got 11`，`build_native.ps1` 整体还撞到 `audio_test.cpp` 缺 `Json`、`daily_test.cpp` / `achievements_test.cpp` 缺 `pathUtf8` 的编译错误 —— 都是别人正在改 content/pack/测试的未落盘状态，与 rail 无关（rail 的 7 段断言在同样的树里全绿）。本任务没有为了「全绿」去动这些文件。

---

## 12. 复现

```powershell
# 增量化一棵隔离树（desktop OFF 就够跑 rail 测试）
cd D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc
.\tools\build_native.ps1 -BuildDir C:\pvzbuild\rail1        # 或 -AuditOnly
& 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\ctest.exe' `
    --test-dir C:\pvzbuild\rail1 -C Release -R "^rail$" --output-on-failure

# CLI 看 rail 键
C:\pvzbuild\rail1\Release\PvZ2SHUTTLE.exe --run-level content cowboy_1 `
    --pack native\generated\content.pack --seconds 20

# smoke 逐条 diff（输出必须落到 build/work，别写 native/generated）
python tools\engine_smoke.py --exe C:\pvzbuild\rail1\Release\PvZ2SHUTTLE.exe `
    --out C:\pvzbuild\rail1\smoke_generated.json
```

## 13. 范围声明

本任务只改头部列出的 10 个代码/构建文件 + 本报告。没有改 `content/**`、`native/generated/**`、`tools/**`，没有 commit。`git status` 里 `content/levels/*.json`、`native/src/engine/vase*` 等改动是并行队友的，与本任务无关。
**两棵树的全量 ctest 与红项归属**

| 树 | 命令 | 结果 |
| --- | --- | --- |
| `C:\pvzbuild\rail1`（desktop OFF） | `ctest --test-dir C:\pvzbuild\rail1 -C Release` | 44/48 passed（121.36 s），4 红 |
| `C:\pvzbuild\rail1-desk`（desktop ON） | `ctest --test-dir C:\pvzbuild\rail1-desk -C Release` | 44/51 passed，7 红/未跑 |

rail 侧全绿：`rail Passed 2.59`（审计树）/ `Passed 5.45`（桌面树）、`battle_render Passed 8.40` / `Passed 10.43`、`rewards` / `mechanics` / `vase` / `cli_reward_*` 全 Passed。

红项逐条归属（都不是 rail，全部来自并行队友正在改的内容与桌面目标）：

| 树 | 测试 | 原文 | 归属 |
| --- | --- | --- | --- |
| 两棵 | `catalog` | `FAIL real catalog counts` | 期望 `worlds==26 && plants==409 && zombies==55 && levels==1809`；四个文件实测都是这个数，差异来自队友在改的 `content/plants.json` 过滤口径 |
| 两棵 | `engine` | `engine test failed: ailmint must be pack-only, not in content JSON` | 队友把 pack-only 条目写进了 content（`ailmint` 在 content 出现 1 处） |
| 两棵 | `art_audit` | `art audit test failed: eight content plants share the fixture's web art, got 13` | 内容/美术数据 |
| 两棵 | `s5_boss` | `s5 boss test failed: boss level pirate_41 neither spawned a boss nor reported boss_unavailable` | `pirate_41.json` 有 `extra.boss=true`，属 boss 表数据 |
| 桌面 | `level_badges` | 未跑：`level_badges_test.cpp(159,34): error C2440` 等 6 个编译错（`LevelBadges` ↔ `path` 类型不匹配） | 队友正在写的 `native/tests/level_badges_test.cpp` |
| 桌面 | `shop_render` | 未跑：`shop_view.cpp(280,36): error C3861: 'saveScreenSnapshot' identifier not found`、`SDLK_q_renamed_SDLK_Q` 未声明 | 队友正在写的 `native/src/shop_view.cpp` |
| 桌面 | `shop_ui` | `Failed 0.26 sec`（编译通过、运行时断言失败） | 队友的 shop 用例 |

所以「两棵树全量 ctest 全绿」这一条**没有达成**：rail 自身的 7 段测试 + 8 个渲染/rail 测试 + CLI + smoke + 截图全部通过，剩余 7 项红全部可归因于队友的在途改动（逐条给了文件与原文）。这是 partial，不是 rail 的回归。
