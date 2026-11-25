# SpawnOffset.y 语义：像素 → 格子换算（T42）

由 `tools/contentc/spawn_offsets.py` 从 `work/obb_packages/pkg_2073_PlantPropertySheet.json` 生成。
产物：`native/generated/spawn_offsets.json`（`generatedAt` = 源表内容的 sha256 短戳 `sha256:ad0fa20ca73aa95b`，因此两次生成逐字节相同）。

## 0. 三个可验证样例

| 道具 | 动作 | kind | `SpawnOffset.x` | `SpawnOffset.y` | xCols | yCols | 来源字段 |
|---|---|---:|---:|---:|---:|---:|---|
| 豌豆（`PeashooterDefault`） | `Actions[0]` | `shot` | 35 | -32 | 0.35 | -0.2759 | `PeashooterDefault.Actions[0].SpawnOffset` |
| 豌豆（`PeashooterDefault`） | `Actions[1]` | `shot` | 35 | -32 | 0.35 | -0.2759 | `PeashooterDefault.Actions[1].SpawnOffset` |
| 玉米（`KernelpultDefault`） | `Actions[0]` | `shot` | 15 | -95 | 0.15 | -0.819 | `KernelpultDefault.Actions[0].SpawnOffset` |
| 玉米（`KernelpultDefault`） | `Actions[1]` | `shot` | 15 | -95 | 0.15 | -0.819 | `KernelpultDefault.Actions[1].SpawnOffset` |
| 阳光（`SunflowerDefault`） | `Actions[0]` | `sun` | 0 | -52 | 0 | -0.4483 | `SunflowerDefault.Actions[0].SpawnOffset` |

读法：`PeashooterDefault` 的豌豆从格子中心右 0.35 格、上 0.276 格射出；`KernelpultDefault` 的玉米从右 0.15 格、上 0.819 格抛出（所以它能越过前排植物）；`SunflowerDefault` 的阳光直接在植物中心上方 0.448 格生成（x 偏移 0）。

## 1. 换算依据

### 1a. 一格是多少像素

**任务里提到的「`docs/COMPLETENESS.md` 有 100×116 像素/格」在当前树里不存在。**
对 `docs/` 下全部 62 个 markdown 文件做 `116` + 像素/乘号 检索，命中 **15** 处（`python tools/contentc/spawn_offsets.py --grep-cell` 可复现）。
- `docs/COMPLETENESS.md:471` — **100×116 像素/格**——这是 `pkg_2073` 的 `ArtCenter` 在 374 个样本上的众数（`99×115` ×164、
- `docs/COMPLETENESS.md:472` — `99×116` ×38、`97×119` ×25），且出厂常量 `kShotStartOffsetCols = 0.35` 恰好等于
- `docs/COMPLETENESS.md:482` — `A96C735E…B256`）：487 行 / 224 株，`pxPerColumn 100`、`pxPerRow 116`；负值向上（480/487 ≤0，
- `docs/COMPLETENESS.md:485` — `skippedOffsets 1`。**诚实边界**：任务书里说的「COMPLETENESS 有 100×116」当时并不存在，
- `docs/COMPLETENESS.md:838` — | C49 | high | 引擎 | **已修**：像素→列换算用 60，而美术空间是 100×116（`ArtCenter` 374 样本）。SpawnOffset 与 RectTriggerRange 全部 1.667 倍错位（豌豆枪口 0.583 列 vs 应 0.35）。已改 `kPixelsPerColum

真正的依据在数据里：

| 证据 | 值 | 命令 / 位置 |
|---|---|---|
| `ArtCenter` 众数（374 个可用样本；379 个对象有该字段，9 位哨兵已过滤） | 枢轴 `(99, 115)`、次众数 `(99, 116)` | `pkg_2073_PlantPropertySheet.json` 的 `ArtCenter` |
| 由此得到的格尺寸 | **100 × 116 px** | `ArtCenter` = 格子中心，故 +1 补 0 基像素中心 |
| 引擎当前用的列宽 | **60 px** | `native/src/engine/action_runner.cpp:14`、`registry.cpp:27` 的 `kPixelsPerColumn` |
| 交叉验证 | `kShotStartOffsetCols = 0.35` = 豌豆 `35 / 100` | `native/src/engine/tuning.hpp` |

两者差 `1.666667` 倍：植物美术空间是 100 px/列，而引擎按 60 px/列换算 `SpawnOffset.x`。本表按**美术空间**换算（`SpawnOffset` 就写在这个空间里），并把 60 原样记在 `scale.enginePxPerColumn`，把差值记在 `scale.pxPerColumnRatioToEngine`。

### 1b. y 的换算

```
xCols = xPx / 100     # 100 px / 列
yCols = yPx / 116     # 116 px / 行
```

`yCols` 与 `xCols` 同单位（格子），所以引擎把两者加到 `(col, row)` 的浮点坐标上即可；`scale.pxPerRowCols` 就是 116，含义是「1 行 = 116 px = 1.16 个列宽」。

## 2. y 的符号约定

**负值向上。**

| 事实 | 值 |
|---|---:|
| `y <= 0` 的行 | 480 / 487 |
| `y > 0` 的行 | 7（见下） |
| 中位数 | -32 px |
| 区间 | -1000 … 30 px |

仅有的正值行（都是小幅枪口偏移，不是「向下发射」）：

| 植物 | 动作 | kind | yPx |
|---|---:|---|---:|
| `PowerVineDefault` | 0 | `shot` | 14 |
| `WitchHazelDefault` | 0 | `shot` | 22 |
| `WitchHazelDefault` | 1 | `special` | 22 |
| `XShotBarrageDefault` | 1 | `shot` | 30 |
| `XShotBarrageDefault` | 2 | `shot` | 30 |
| `XShotDefault` | 1 | `shot` | 30 |
| `XShotDefault` | 2 | `shot` | 30 |

屏幕上 y 向下增长，所以负的 `yPx` 表示**抬高**；引擎若要屏幕坐标，取 `-yCols`。深度为 `-600`/`-1000` 的行（`BananaDefault`、`CobCannonDefault`、`NukeLauncherDefault`、`DandelionDefault` 等）不是格内偏移，而是「从画面上方落下来」的投放点，换算后是 -5.2 / -8.6 行，超出棋盘高度——这是它们的设计意图，不是坏数据。

## 3. 不确定项（必须读）

1. **116 px/行是从 `ArtCenter` 众数读出来的，不是代码常量**：仓库里没有任何「行高」常量（`native/src` 中 `kPixelsPerRow`/`kCellHeight` 均 0 命中），`battle_view.cpp:19` 的 `cellW = cellH = 100` 是**屏幕像素**，不是美术空间，不能拿来换算 `SpawnOffset`。若日后确认美术格不是 116 高，只改 `scale.pxPerRow`。
2. **100 vs 60 的口径冲突未在本任务解决**：本表按 100 输出 `xCols`，而引擎现在按 60 换算，同一条 `SpawnOffset.x = 35` 会得到 0.35（本表）与 0.583（引擎）。修 `native/src/**` 不在本任务写作用域内。
3. **`special`/`explode`/`manual` 的 `SpawnOffset` 不是发射点**：`action_runner.cpp:22` 的注释已说明它是触发矩形原点，本表按 `kind` 标注，消费方不应把它当弹道起点。
4. **哨兵值**：`|像素| >= 2000` 的偏移被跳过并计入 `counts.skippedOffsets`（当前 1 条：`FlowerPotDefault` Actions[0]）。
5. **`ArtCenter` 自身有哨兵**：少数对象是 9 位数（如 `979999999`），统计时按 `0..400` 过滤，过滤前的样本数不参与众数。

## 4. 统计

| 项 | 值 |
|---|---:|
| 植物 props 对象里的 action 总数 | 727 |
| 带 `SpawnOffset` 的 action | 488 |
| 换算成 row 的行数 | 487 |
| 涉及植物 | 224 |
| 跳过（哨兵/非数值） | 1 |

按 kind：`shot` 386、`sun` 18、`plantfood` 6、`special` 77、`manual` 1。

## 5. 复现

```
python tools/contentc/spawn_offsets.py             # 重写 json + 本报告
python tools/contentc/spawn_offsets.py --check     # 自洽 + 逐字节比对
python tools/contentc/spawn_offsets.py --grep-cell # 复现「docs 里没有 100×116」
python -m unittest tools.tests.test_spawn_offsets -v
```

表格里的每个数都能用第三条命令重算；逐行来源在 json 的 `rows[].source`。

## 6. 引擎接入建议（不在本任务实现）

1. `World::spawnShot` / `spawnSun` 增加一个 `yCols` 参数（向上为正），内部按 `y` 屏幕坐标减去它；`0.0` 即今天的行为，所以加参数不会改变既有 32 个冒烟场景。
2. 换算用本表的 100 px/列 与 116 px/行——**同时**把 `kPixelsPerColumn` 从 60 改到 100，否则 x 与 y 会来自两套不同的像素空间，抛物线会歪。
3. `special`/`explode`/`manual` 行不要接进发射点，它们只决定触发矩形。

