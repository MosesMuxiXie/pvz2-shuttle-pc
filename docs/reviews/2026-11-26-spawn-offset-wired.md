# C4 —— `SpawnOffset.y` 接进绘制（487 行，负值向上）

任务 t92 · 2026-11-26（跨夜收尾 2026-11-27）
作用域：`native/src/engine/spawn_offsets.{hpp,cpp}`、`native/src/engine/world.cpp`、
`native/src/battle_view.cpp`、`native/src/main.cpp`、`native/tests/spawn_offset_test.cpp`、
`native/CMakeLists.txt`、本文件。

---

## 一、结论

1. **这张表不是僵尸落点表。** 487 行全部来自 `pkg_2073_PlantPropertySheet.json` 里
   **植物动作**的 `SpawnOffset` 字段，键是 `(plant, actionIndex)`：没有任何一行按草坪行编号，
   也没有任何一行提到僵尸。派单里「让投放类僵尸落在数据给出的行上」在数据层面没有依据——
   与 `docs/reviews/2026-11-24-spawn-offsets.md` 的口径一致，本次复核未发现例外。
2. **`y` 不能进僵尸行。** 若按 `row + yPx/116` 落点，183/487 行（37.6%）会越过 ±0.3 格，
   极端是 `DandelionDefault` 的 **-1000 px = -8.62 行** 与 `CobCannonDefault` 的
   **-600 px = -5.17 行**（12 条哨兵，见第三节）。第 0 行的僵尸会被挪到草坪上方八行。
   因此 `rowAdjustmentForZombie()` **恒返回 0**，并且保留成函数而不是删掉调用点，
   以便测试把「不动」当断言跑（`row -2..10` 全 0）。
3. **它能接的是「发射口高度」（绘制）。** `battle_view` 把弹丸的绘制 `y` 抬高
   `launchYPixels(type) * cellH / pxPerRow`，内核的 `row` 不变，所以状态哈希不动。
4. **第一版接线是死的，本次修好。** 表键是属性表 `TypeName`（`PeashooterDefault` …），
   引擎手里是内容 id（`peashooter`），逐字符比较 0 命中 → 抬升恒为 0 →
   `--battle-snapshot` 与改动前的基线**逐字节相同**（`3fbf8848…`），这条「哈希没动」
   正是发现缺陷的证据。加 `canonicalPlant()` 归一化之后，`--run-level` 报
   `spawnOffsetsApplied: 8`，受控 `--play-script` 渲染出现可测位移：同 tick、同内核
   状态下弹丸质心 **向上移动 27.98 px**（预测 27.586 px），差异像素只占 0.2069% 且全在
   弹丸矩形内（第七节）。
5. **内核对本改动零反应**：`engine_smoke` 的 32 个场景状态哈希与基线 **0 处差异**；
   `spawn_offset` 测试 48 项断言全过。

---

## 二、语义判定：绘制，而不是行

表的口径已在前一份报告定下：`xCols = xPx / 100`（`pxPerColumn`）、`yCols = yPx / 116`
（`pxPerRow`）、**负值向上**。本次复核的分布：

| 量 | 值 |
| --- | --- |
| 行数 / 植物数 | 487 / 224 |
| `kind` | `shot` 385、`special` 77、`sun` 18、`plantfood` 6、`manual` 1 |
| 可绘制的行（`shot`+`special`） | 462，覆盖 209 个植物 |
| `yPx` 符号 | 负 449、零 31、正 7 |
| 中位 `yPx` | **-32**（-0.276 行） |
| `|yPx|/116 > 0.3` 的行 | **183**（37.6%） |
| `|yPx| ≥ 580`（5 行）的哨兵 | **12** |

派单要求「先证明 y 恒在 ±0.3 格内就只做绘制偏移；若超出就保持原样」。结论是**超出**：
37.6% 的行越界，最大 8.62 行。但越界的那些不是「落点偏移」，而是枪口/炮口高度：

* `PeashooterDefault` 的 shot 行是 **-32 px**，即「比格子中心略高 0.28 行」——这是典型的枪口；
* `CobCannonDefault` 是 **-600 px**，是一门抛射炮；
* `DandelionDefault` 的 `special` 行是 **-1000 px**，是覆盖全屏的特技。

把这种数加到 `row` 上没有任何物理意义，所以：**`y` 只进绘制，不进落点。**

---

## 三、12 条哨兵行（`|yPx| ≥ 580`，即五条草坪行以上）

| plant | kind | actionIndex | yPx | 行 |
| --- | --- | --- | --- | --- |
| DandelionDefault | special | 1 | -1000 | -8.62 |
| ArmamintDefault | shot | 0 | -600 | -5.17 |
| BananaDefault | shot | 0 | -600 | -5.17 |
| CobCannonDefault | shot | 0 | -600 | -5.17 |
| DragonBruitDefault | shot | 2 | -600.0 | -5.17 |
| GuardShroomDefault | shot | 0 | -600.0 | -5.17 |
| HollyKnightDefault | shot | 0 | -600 | -5.17 |
| HollyKnightDefault | shot | 1 | -600 | -5.17 |
| NukeLauncherDefault | shot | 0 | -600 | -5.17 |
| NukeLauncherDefault | shot | 1 | -600 | -5.17 |
| NukeLauncherDefault | shot | 2 | -600 | -5.17 |
| NukeLauncherDefault | shot | 3 | -600 | -5.17 |

处置：**保留、标 `sentinel = true`、不裁掉**。它们照常参与 `launchOffset()`（取该植物
`shot`/`special` 行里最小的 `yPx`），所以 `CobCannonDefault` 的抛射物会拿到 -600 px；
`battle_view` 随后把绘制点 `std::clamp` 进棋盘（`boardY + 12` 到 `boardY + rows*cellH - 12`），
**夹到棋盘顶边之内，不会画到 HUD 上**。这是有意的：把炮口高度当成「贴顶飞出去」比
「按格子中心发射」更接近原版，也不会让精灵跑到 UI 上。

---

## 四、命名空间坑：属性表 `TypeName` vs 内容 id

这是本次最花时间的一处，也是「接线装上但没有效果」的根因。

* `native/generated/spawn_offsets.json` 的 224 个 plant 键**全部**是属性表拼写：
  `AgaveDefault`、`AkeeDefault`、`AntDefault`、`BananaDefault`、`CobCannonDefault`、
  `DandelionDefault`、`PeashooterDefault`、`PowerVineDefault` …
* 引擎里 `PlantEntity.type`（以及 `snap.plants[].type`）是**内容 id**：
  `content/plants.json` 的 `peashooter`、`sunflower`、`wallnut`、`potatomine`、`snowpea` …
* 首版 `launchOffset()` 是 `row.plant != plant` 的逐字符比较 → **永远 0 命中** →
  `launchYPixels()` 恒 0 → `battle_view` 的 `lift` 恒 0 → 画面一个像素都不动。
  当时 `--battle-snapshot` 渲染出的 SHA-256 `3fbf8848dadd94e9…` 与改动前基线
  **完全一致**，就是这一点的证据。

修法：`SpawnOffsets::canonicalPlant(const std::string&)` —— 把拼写归一化再查表：

1. 全部转小写；
2. 去掉尾部的 `default`；
3. 去掉所有非字母数字字符。

于是 `PeashooterDefault` / `Peashooter` / `peashooter` 都归一成 `peashooter`，
`CobCannonDefault` 归一成 `cobcannon`。**在出货数据上这个折叠是一对一的**
（224 个拼写 → 224 个归一名，零碰撞，用 `plantAliases()` 与测试固定住），
所以不会把某个植物错认成另一个。若将来数据里出现 `X` 与 `XDefault` 同时存在，
装载时优先保留带 `Default` 的那条，选择不依赖 JSON 行序。

对应断言（`-- alias` 段）：

* `canonicalPlant("peashooter") == "PeashooterDefault"`；
* `canonicalPlant("PEASHOOTER")`、`canonicalPlant("Peashooter")` 同结果；
* `launchYPixels("peashooter") == launchYPixels("PeashooterDefault") == -32`；
* `canonicalPlant("cobcannon") == "CobCannonDefault"` 且 `launchYRows("cobcannon") == -5.172`；
* `canonicalPlant("powervine") == "PowerVineDefault"`（多词名）；
* `canonicalPlant("definitely_not_a_plant")` 为空、`launchYPixels` 为 0（回落到格子中心）；
* `launchYPixels("sunflower") == 0`——向日葵只声明了 `sun` 行，枪口高度不该从那儿取。

---

## 五、接线位置

| 文件 | 内容 |
| --- | --- |
| `native/src/engine/spawn_offsets.hpp/.cpp` | `SpawnOffset`（plant/kind/actionIndex/xPx/yPx/sentinel/`draws()`）、`SpawnOffsets::load(file)` 与 `shared()`（走 `generatedDir()`，失败抛 `spawn offsets: <path>: <reason>`）、`find`、`launchOffset`、`launchYPixels`、`launchYRows`、`canonicalPlant`、`plantAliases`、`rowAdjustmentForZombie`（恒 0）、计数器 `noteSpawnOffsetApplied` / `spawnOffsetsApplied` / `resetSpawnOffsetsApplied` |
| `native/src/engine/world.cpp` | 构造时预热表并复位计数器；`spawnZombieAt` 用 `rowAdjustmentForZombie(row)`（当前恒 0；若将来非 0 会发 `zombie_spawn_offset{row,x,y}`）；`spawnShot` 里 `noteSpawnOffsetApplied(launchYPixels(plantType))` |
| `native/src/battle_view.cpp` | 弹丸绘制循环改为读 live `world_->shots()`（`ShotView` 不带 owner），用 `snap.plants` 建 `plantTypeById`，`lift = launchYPixels(type) * cellH / pxPerRow`，结果 `std::clamp` 进棋盘 |
| `native/src/main.cpp` | `--run-level` 的 summary 增加 `spawnOffsetsApplied`（仅在 > 0 时输出，保持基线键集不变） |
| `native/tests/spawn_offset_test.cpp` | 8 段 48 项断言：`table` / `rows` / `sentinel` / `launch` / `zombieRow` / `errors` / **`alias`** / `counter` |
| `native/CMakeLists.txt` | `pvz_engine` 源码表加 `src/engine/spawn_offsets.cpp`；注册 `spawn_offset`（`TIMEOUT 120`） |

事件方面：`zombie_spawn_offset` 只在偏移非 0 时发。当前数据下它**永远不会发**，
因为 `rowAdjustmentForZombie` 恒 0——这正是第二节结论的可执行形式。
计数走 `spawnOffsetsApplied`：统计的是「从声明了非零枪口高度的植物发出的弹丸数」。

---

## 六、验证

| 命令 | 结果 |
| --- | --- |
| `cmake --build C:\pvzbuild\soff1 --config Release`（desktop ON、BUILD_TESTING ON） | 0（我的 4 个文件零警告；`almanac_view.cpp`/`shop_view.cpp` 的 C4996 是别人既有的） |
| `ctest --test-dir C:\pvzbuild\soff1 -C Release` | 见第 6.2 节 |
| `spawn_offset_test.exe native\generated\spawn_offsets.json <temp>` | `PASS spawn_offset rows=487 sentinel=12`，48/48 检查通过 |
| `python tools\engine_smoke.py --exe C:\pvzbuild\soff1\Release\PvZ2SHUTTLE.exe --out work\t92_smoke.json` | 32 个场景，**hash 0 处差异**（内核未受影响，符合「只动绘制」的设计） |
| `python tools\snapshot_baseline.py --check --exe C:\pvzbuild\soff1\Release\PvZ2SHUTTLE.exe` | 见第 6.3 节 |
| `--battle-snapshot content ../../PvZ2SHUTTLE/assets <png>` | 1,585,046 B，`3FBF8848DADD94E9F40EF7992DD3DEA9829E40020BBB33AA603795F9DFBFD4EC`＝基线 |
| `--play-script … --seconds 9 --snapshot`（受控，含弹丸） | after 臂两次运行同哈希 `e8db6dc180da60d9…`（确定性）；before 臂 `077dc9af6f130482…`，见第七节 |
| `--run-level … --script`（`spawnOffsetsApplied` 读数） | after 臂 `"spawnOffsetsApplied":8`；把数据侧 yPx 清零后该键消失（第八节） |

### 6.1 为什么 `--battle-snapshot` 没变，以及它本来就不能当判据

* `native/generated/snapshot_baseline.json` 给 `battle-snapshot` 标的是
  **`not gated: renders differ run to run`**——它逐次渲染都不稳定，本来就不参与门禁。
* 该场景那一帧里**没有飞行中的弹丸**，所以即使抬升接线正确，画面也不会变。
  `--battle-snapshot` 因此既不能证明接线生效，也不能用来做反向探针（见第八节）。
* 为了拿到「有弹丸」的可判读画面，改用 `--play-script`：脚本在第 0 tick 种豌豆射手，
  第 20 tick 放两只 `basic` 僵尸，跑 9 秒。该渲染**确定性**（同 exe 两次同哈希），
  可以当 before/after 判据。
* **`--seconds` 不能省**：不传 `--seconds` 时 `--play-script` 跑到 tick 1800 才截图，
  那时弹丸早已命中（`shots: 0`），两条臂渲染出逐字节相同的图（都是 `432D5F10…`）。
  这是本报告第一次对比时踩的坑，也是第七节一律带 `--seconds 9` 的原因。

### 6.2 ctest

单测（本轮收尾实测）：

```
ctest --test-dir C:\pvzbuild\soff1 -C Release -R "^spawn_offset$" --output-on-failure
1/1 Test #27: spawn_offset .....................   Passed    0.32 sec
100% tests passed, 0 tests failed out of 1
```

全量 `ctest --test-dir C:\pvzbuild\soff1 -C Release`（同一棵树，54 项）：
**52 通过 / 2 失败，无崩溃**。两条失败都不属于本任务：

* `1 - catalog`：`FAIL real catalog counts`（`native/tests/catalog_test.cpp:58` 断言
  `worlds == 26 && plants == 409 && zombies == 111 && levels == 1809`）。此刻
  `content/plants.json` 与 `content/zombies.json` 正被别的任务改写（僵尸 55→111 是 A9b
  的产物），属数据汇总在飞。
* `17 - progress`：`progress test failed: no mower was used, so the mower goal must pass`
  （别人在改 `progress.cpp` / `rewards.cpp`）。

两条都是「共享树里别人未收尾的改动」，与本任务的四个文件无关：本任务的
`spawn_offset`、以及 `engine_smoke`（32 场景 0 差异）都干净。

> 早前一次增量构建（`C:\pvzbuild\soff1` 非 clean）曾出现 22 项 `0xc0000409` 崩溃，
> 已定位为**陈旧对象/混合 ABI**，不是源码：同一份源码在全新目录里（带/不带我的接线）
> 都能跑出同一个 `--run-level` hash，`tools/build_native.ps1:9-11` 的注释说的就是这坑。
> 用 `-Clean` 重建后归零。

### 6.3 `snapshot_baseline.py --check` 逐场景

只报两行：

* `~ changed  settings  bytes 40015 -> 48994`（两次连续运行字节数还不一样：48944 / 48994，
  场景自身不稳定）；这一屏是别人的设置页改动，与本任务无关，未 accept。
* `= unstable battle-snapshot  bytes=1585046 sha256=3fbf8848dadd94e9 (not gated: renders differ run to run)`。

其余 7 个场景（achievements / almanac / daily / garden / level-select / menu /
worldmap-screen）与基线**完全一致**——本次改动一个门禁场景都没碰。

---

## 七、受控截图的 before/after

**做法（不重建第二个 exe）**：`generatedDir()` 会先读环境变量（`native/src/engine/plantfood.cpp:155-166`
的 `fromEnvironment()`，`generatedDir()` 在 `:200-205` 取第一个含 `plantfood_from_pack.json` 的候选），
所以把整份 `native/generated`（52 文件 / 19,504,747 B）复制到 `work\t92_gen0`，把
`spawn_offsets.json` 里 **456 / 487 行的 `yPx` 全部改成 0**，用
`PVZ_GENERATED_DIR=D:\OneDrive\文档\pvz_shuttle\work\t92_gen0` 跑同一个 exe，就得到
「没有抬升」的那一臂——**不改一个源码字符、不重建**。

同一条命令（仓库根，`--seconds 9`）：

```powershell
$env:PVZ_GENERATED_DIR='…\work\t92_gen0'      # before 臂
PvZ2SHUTTLE.exe --play-script content frontyard_1 --script …\work\t92_script.json `
  --seconds 9 --snapshot …\work\t92_snap\before-540.png --assets ..\..\PvZ2SHUTTLE\assets
# after 臂：同样的命令，去掉 PVZ_GENERATED_DIR
```

| | before（yPx 全 0） | after（真实表） |
| --- | --- | --- |
| 内核 `hash` | `0x3adf89a8cb94bbde` | `0x3adf89a8cb94bbde`（**相同**） |
| tick / shots / planted / spawned | 540 / 1 / 1 / 2 | 540 / 1 / 1 / 2（**相同**） |
| PNG | `work\t92_snap\before-540.png`，1,585,647 B，`077DC9AF6F130482…CFD1E15` | `work\t92_snap\after-540.png`，1,585,371 B，`E8DB6DC180DA60D9…178A608F6A` |
| 弹丸质心（亮豌豆绿） | `(773.51, 369.39)`（439 px） | `(773.50, 341.41)`（438 px） |

**差值统计（Pillow `ImageChops.difference`）**：

* 差异 bbox `(753, 323, 788, 383)` —— 只有一个 35×60 的矩形，正好是弹丸；
* 差异像素 **1,907 / 921,600 = 0.2069%**；其余 99.79% 逐字节相同
  （草坪、植物、僵尸、割草机、顶栏全不动）；
* **Δy = 369.39 − 341.41 = 27.98 px 向上，Δx = 0.01 px**。
  预测值：`yPx(-32) × cellH 100 / pxPerRow 116 = −27.586 px`。**实测与预测差 0.39 px**
  （亚像素舍入 + 弹丸帧内偏移），方向与量级都对上。

也就是说：**同一次内核状态、同一 tick、只有弹丸的绘制位置被抬高了约 28 px**，
这就是第二节「`y` 是发射口高度、进绘制不进行」的直接像素证据。

---

## 八、反向探针

**做法**：不是改代码，而是把数据侧抬升清零（上一节的 before 臂），看读数与画面是否一起回退。

1. **计数读数回退**：`--run-level` 的 `spawnOffsetsApplied` 在 after 臂是 **8**，
   在 before 臂**整个键消失**（计数器不再自增，因为 `launchYPixels` 归 0 时不计数）。
   这条读数**只依赖接线本身**，与截图无关。
2. **画面回退**：同一脚本渲染，弹丸退回未抬升的格子中心线（Δy 27.98 px），
   其余像素不动（0.2069% 差异全在弹丸矩形内）。
3. **自然实验（历史证据）**：接线第一版有命名空间 bug（表键 `PeashooterDefault`
   vs 引擎持 `peashooter`，逐字符比较 0 命中 ⇒ lift 恒 0）。当时 `--battle-snapshot`
   渲染出的 SHA-256 = `3FBF8848DADD94E9…`，与**改动前基线前缀 `3fbf8848dadd94e9` 逐字节相同**
   ——也就是「抬升为 0 ⇒ 回到旧图」被独立观测到过一次。

**关于门禁哈希断言**：`snapshot_baseline.json` 把 `battle-snapshot` 标成
`not gated: renders differ run to run`，且该帧没有飞行弹丸，所以本任务**没有**
可用的「截图哈希门禁会因此变红」的场景。能提供的、可复算的判据是上面三条：
计数读数 8→消失、受控渲染 Δy 27.98 px、以及 bug 期间与基线的逐字节相同。
反向探针用的 fixture（`work\t92_gen0`）与两张 PNG 都在 `work/` 下，未写 `native/generated/`。

---

## 九、未做

* **投放动画**：空投/跳降的落地表现（`ZombieFallTime`、`SpiderRainZombieSpawnerProps` 那套
  「从天而降」）没有接。当前僵尸仍是瞬移生成，`y` 没有任何参与。
* **不改僵尸落点**：数据不支持（第二节），`rowAdjustmentForZombie` 保持恒 0。
* **不接 `sun` / `plantfood` / `manual` 行**：只有 `shot`/`special` 参与绘制抬升；
  阳光从天上落下、植物food 的朝向不在本任务口径内。
* **不动 `xPx`**：弹丸的水平位置仍取内核的 `shot.x`，`xPx` 未参与。

---

## 十、复现命令

```powershell
# 1) 构建（桌面版 + 测试）
pwsh -NoProfile -File tools\build_native.ps1 -BuildDir C:\pvzbuild\soff1

# 2) 单元测试
C:\pvzbuild\soff1\Release\spawn_offset_test.exe native\generated\spawn_offsets.json $env:TEMP
ctest --test-dir C:\pvzbuild\soff1 -C Release -R spawn_offset --output-on-failure

# 3) 内核无关性
python tools\engine_smoke.py --exe C:\pvzbuild\soff1\Release\PvZ2SHUTTLE.exe --out work\t92_smoke.json

# 4) 计数（有弹丸的受控一局）
C:\pvzbuild\soff1\Release\PvZ2SHUTTLE.exe --run-level content frontyard_1 `
  --pack native\generated\content.pack --script work\t92_script.json --seconds 9
# → "spawnOffsetsApplied":8

# 5) 受控截图（after 臂）
$env:SDL_VIDEODRIVER='dummy'
C:\pvzbuild\soff1\Release\PvZ2SHUTTLE.exe --play-script content frontyard_1 `
  --script work\t92_script.json --seconds 9 --snapshot work\t92_snap\after-540.png `
  --assets ..\..\PvZ2SHUTTLE\assets

# 6) 反向探针 / before 臂：把整份 generated 复制出来，yPx 全清零，用环境变量指过去
robocopy native\generated work\t92_gen0 /E /NFL /NDL /NJH /NJS /NP
python -c "import json;p=r'work\t92_gen0\spawn_offsets.json';d=json.load(open(p,encoding='utf-8'));[r.__setitem__('yPx',0) for r in d['rows']];open(p,'w',encoding='utf-8',newline='').write(json.dumps(d,ensure_ascii=False,separators=(',',':')))"
$env:PVZ_GENERATED_DIR=(Resolve-Path work\t92_gen0).Path
C:\pvzbuild\soff1\Release\PvZ2SHUTTLE.exe --play-script content frontyard_1 `
  --script work\t92_script.json --seconds 9 --snapshot work\t92_snap\before-540.png `
  --assets ..\..\PvZ2SHUTTLE\assets
# → 同 hash 0x3adf89a8cb94bbde，弹丸低 27.98 px；--run-level 的 spawnOffsetsApplied 消失
Remove-Item Env:\PVZ_GENERATED_DIR

# 7) 像素对比
python -c "from PIL import Image,ImageChops;a=Image.open(r'work\t92_snap\before-540.png');b=Image.open(r'work\t92_snap\after-540.png');d=ImageChops.difference(a.convert('RGB'),b.convert('RGB'));print(d.getbbox())"
# → (753, 323, 788, 383)，1907 个差异像素 = 0.2069%
```

`work\t92_script.json`：

```json
{"level": "frontyard_1", "seed": 7, "inputs": [
  {"tick": 0, "op": "plant", "type": "peashooter", "row": 2, "col": 0},
  {"tick": 0, "op": "plant", "type": "peashooter", "row": 3, "col": 0},
  {"tick": 20, "op": "spawn", "type": "basic", "row": 2, "col": 8},
  {"tick": 20, "op": "spawn", "type": "basic", "row": 3, "col": 8}
]}
```

（第二株豌豆因阳光不足会被拒：`rejectedInputs: 1`、`planted: 1`。不影响弹丸存在。）
