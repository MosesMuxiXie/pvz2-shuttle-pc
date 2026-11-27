# D5 · 截图基线（`tools/snapshot_baseline.py`）

日期：2026-11-26
任务：D5 —— 把九个无头截图的字节数 / SHA-256 从评审文档里的手抄数字，变成受版本控制的产物与可重跑的门禁。

## 0. 结论

| 项 | 结果 |
| --- | --- |
| 工具 | `tools/snapshot_baseline.py`（纯标准库，`--check` / `--accept` / `--list`） |
| 基线 | `native/generated/snapshot_baseline.json`（九场景，存 sha256 / bytes / 宽高 / 命令，不存 PNG） |
| 测试 | `tools/tests/test_snapshot_baseline.py`，**40 例通过 / 1 例跳过**（跳过的是真渲染，需 `SNAPSHOT_EXE`） |
| 门禁口径 | 9 个场景全部渲染并入库；其中 **8 个参与字节门禁**，`battle-snapshot` 记为 `stable: false`（跨进程不稳定，见 §12） |
| 记录表 | `docs/PARITY_BASELINE.md` 新增「截图基线变更记录」，九条首轮全部入库 |
| 退出码 | 0 干净 / 1 有漂移或自校验失败 / 2 用法错或基线坏 |
| 与 D2 的关系 | 同一套记录表形状与幂等规则；D2 管数值矩阵（`engine_smoke.json`），D5 管像素（九张 PNG） |

## 1. 变更前的问题

截图哈希此前散落在评审文档正文里，例如：

* `docs/reviews/2026-11-26-rail-gameplay.md` §8 里手抄的 `snapshotBytes 1563602` / `hash 0xca33d5c2eaa8f788` / PNG sha256 前 16 位 `13C891B389A37399`；
* 更早的 S4/S5 报告里逐次记录过菜单与关卡列表的尺寸变化。

这带来三个具体麻烦：

1. **没人能复跑**。数字只有「当时那个人那次渲染」的语境，命令参数（`--assets`、`--frames`、`--world`）写在正文里，抄错一个参数就是另一张图。
2. **漂了看不出来**。`check_all.ps1` 的 Step `engine smoke` 只比 `engine_smoke.json` 的数值矩阵，像素完全不设防：`battle_view` 的绘制改坏了，只要 `hash` 不变就一路绿灯。
3. **该变的和不该变的分不开**。菜单从 3 项长到 8 项，`--menu` 的 rect 自然全变；没有基线，这种「预期变化」和「回归」长得一模一样。

D5 把这三件事分别变成：可执行的 `command` 字符串、`--check` 的退出码、`--accept --reason` 的显式记账。

## 2. 九个场景

每条 `command` 都能在仓库根直接粘贴执行（输出路径已在命令末尾，默认 `build/snapshots/<scene>.png`）；`--exe` 只是替换可执行文件，不动记录里的命令。

| 场景 | 命令（省略 exe 前缀） | 选它的原因 |
| --- | --- | --- |
| `menu` | `--menu content --assets ../../PvZ2SHUTTLE/assets --frames 3 --snapshot build/snapshots/menu.png` | 主菜单承载 S4 的全部入口；菜单项数量一变，整排 rect 位移 |
| `worldmap-screen` | `--worldmap-screen content --assets … --frames 3 --snapshot build/snapshots/worldmap-screen.png` | 世界地图同时画进度与星星，`--progress` 存档一变就换图 |
| `level-select` | `--level-select content --world egypt --assets … --frames 3 --snapshot build/snapshots/level-select.png` | 关卡卡片 + 徽章 + 通关标记，密度最高的列表屏 |
| `battle-snapshot` | `--battle-snapshot content ../../PvZ2SHUTTLE/assets build/snapshots/battle-snapshot.png` | 战斗首帧：棋盘、植物、僵尸、割草机、铁轨车全在同一张图里 |
| `almanac` | `--almanac content --assets … --frames 3 --snapshot build/snapshots/almanac.png` | 图鉴依赖 `plants.json` 与字体，最容易跟着数据抖动 |
| `garden` | `--garden content --assets … --frames 3 --snapshot build/snapshots/garden.png` | 花园同时受存档植物列表与 sprite 图集影响 |
| `achievements` | `--achievements content --assets … --frames 3 --snapshot build/snapshots/achievements.png` | 成就页读 `metagame.json`，缺表时走 shipped 模型，两条路径像素不同 |
| `daily` | `--daily content --assets … --frames 3 --snapshot build/snapshots/daily.png` | 每日挑战页带日期语义，用固定进度文件消除日历影响 |
| `settings` | `--settings content --assets … --frames 3 --snapshot build/snapshots/settings.png` | 音量滑块默认值来自存档，是「空存档渲染」的守门场景 |

两点必须写清楚，否则复跑会掉坑：

* **`--battle-snapshot` 是三个操作数**（`<content> <资源根> <输出>`），第二个是资源根不是关卡 id；写错不会报错，只会渲染出另一张图。它的输出路径**直接跟在资源根后面**，多写一个 `--snapshot` 会让它变成 6 个 argv 并报 `invalid battle preview arguments` —— 代码里 `POSITIONAL_OUT` 就是为这条差异准备的。
* **资源根在仓库外**：`../../PvZ2SHUTTLE/assets`（相对仓库根）。仓库根下没有 `assets/`，自动发现必然失败，所以每条命令都显式给 `--assets`。

## 3. 首轮真值

由 `--accept` 九条全部建档，`--check` 随后退出 0。数值见 §3.1，命令与耗时见 §3.2。

### 3.1 九条首轮哈希

| 场景 | 字节数 | sha256 | 尺寸 |
| --- | --- | --- | --- |
| `menu` | 43,630 | `8bc2a933988a9e6030a910037a4b4945db9af94941ecb374aac90b7c2a261d5a` | 1280×720 |
| `worldmap-screen` | 120,465 | `dfc07d8da44cbdea06a572eea31f9746d8f1203410530777aefcdd83160861c4` | 1280×720 |
| `level-select` | 93,815 | `4ea63fc0f3f64b786ed4423c23f81f48acb62dfb16410022b084adf13e29d4e8` | 1280×720 |
| `battle-snapshot` | 1,585,046 | `3fbf8848dadd94e9f40ef7992dd3dea9829e40020bbb33aa603795f9dfbfd4ec` | 1280×720 |
| `almanac` | 106,400 | `8dca6c55a275634fb5e978c78d52d71889745a42ec45f1b9af41ae591c16006d` | 1280×720 |
| `garden` | 112,022 | `8704170f9d1e7e424a58af1e79620e44beb0d5327b37c178348796717c00cebd` | 1280×720 |
| `achievements` | 55,564 | `93ceea1e1770b6d06952804f0617c5189196f0006d23c5fc964540fa05ffe3c6` | 1280×720 |
| `daily` | 102,449 | `a828e23ee5182ccb6a105a2ab27d21beae53b0254833a50d4b8060e66be8b2af` | 1280×720 |
| `settings` | 46,851 | `48aa351af1ab7d3305cdf4d5275f72d99c33544c8b0da4787cf5ee005ec55b37` | 1280×720 |

九条全部 1280×720 —— 这是 `battle_view`/各 view 共用的帧尺寸常量，尺寸漂移比哈希漂移更好定位，所以宽高也进了基线。

### 3.2 渲染耗时与可执行文件

| 动作 | 命令 | 结果 | 耗时 |
| --- | --- | --- | --- |
| 首轮建档（九条） | `--accept "menu,worldmap-screen,level-select,battle-snapshot,almanac,garden,achievements,daily,settings" --reason "…" --exe <snap3>` | 9 行记录，`exit 0` | 12.1 s |
| 复验 | `--check --exe <snap3>` | `9 scenes, no change`，`exit 0` | 13.4 s |
| 二次复验（出报告） | `--check --exe <snap3> --report build/snapshots.now.json` | `exit 0`，报告 3,760 B | 13.7 s |
| 单字节漂移探针 | `--check --baseline build/baseline.mutated.json --from build/snapshots.now.json` | `~ changed  menu  bytes 43630 -> 43630  sha256 9bc2a933988a9e60 -> 8bc2a933988a9e60`，`exit 1` | 0.3 s（不再渲染） |
| 稳定性普查（每场景 6 次） | 直接跑 `--battle-snapshot/--garden/--worldmap-screen/--daily/--achievements` 各 6 次取 sha256 | `garden/worldmap-screen/daily/achievements` 各 1 个哈希；**`battle-snapshot` 6 次出现 5 个不同哈希** | 约 40 s |
| 门禁复验（连续 3 次） | `--check --exe <snap3>` ×3 | 均 `9 scenes, no change`，`exit 0`（其中 1 个不稳定场景以 `= unstable` 报出、不参与判定） | 13 s / 次 |

用的可执行文件：`C:\pvzbuild\snap3\Release\PvZ2SHUTTLE.exe`（5,143,552 B，mtime `2026-11-26T14:06:30Z`，isolated tree `snap3`，configure 于 `14:02Z`）。

**为什么不是 `build/desktop-gate/Release/PvZ2SHUTTLE.exe`**：那个件是 `2026-11-25 19:09:58`（4,829,184 B），**没有**五个 meta 屏参数：

```
$ build/desktop-gate/Release/PvZ2SHUTTLE.exe --almanac content --assets ../../PvZ2SHUTTLE/assets --frames 3 --snapshot probe.png
error: expected a command and a directory; use --help
exit=1
```

它只有 `--menu/--worldmap-screen/--level-select/--battle-snapshot` 四条老命令，所以 `--accept` 用了 `--exe` 覆盖。基线里的 `command` 仍然写仓库相对的 `build/desktop-gate/Release/PvZ2SHUTTLE.exe`（`--list` 里可以直接看到），等 `tools/build_native.ps1 -BuildDir build/desktop-gate` 在下一次桌面门禁里重建后，那九行命令逐字可跑——本轮已用 `snap3` 的件把八条命令逐字重放过两条（`menu` 43,630 B、`battle-snapshot` 1,585,046 B，与基线逐字节一致）。

`snap3` 这棵树配了 `-DCMAKE_CXX_FLAGS=/DPVZ_ENABLE_DESKTOP=1`：当时 `native/CMakeLists.txt` 只给 `PvZ2SHUTTLE` 目标加 `PVZ_ENABLE_DESKTOP=1`，`pvz_launcher` 没有，于是 `renderAchievementsHeadless`/`renderDailyHeadless`（`achievements_view.cpp:257`、`daily_view.cpp:225`，都被 `#ifdef PVZ_ENABLE_DESKTOP` 包着）在 launcher 库里被编掉，链接报 `LNK2019 … LNK1120: 2 unresolved externals`。现在树里第 442 行已有 `target_compile_definitions(pvz_launcher PUBLIC PVZ_ENABLE_DESKTOP=1)`，正常 `tools/build_native.ps1` 的桌面件与此等价。

基线**不记录**实际用的 exe（见 §4 第四条）：换台机器重编一次就变的值不该进基线。

## 4. 基线文件形状

`native/generated/snapshot_baseline.json`：

```json
{
 "format": "pvz2-shuttle/snapshot-baseline@1",
 "generated": "snapshot-baseline@1",
 "exe": "build/desktop-gate/Release/PvZ2SHUTTLE.exe",
 "scenes": {
  "almanac": {
   "bytes": 000000,
   "command": "build/desktop-gate/Release/PvZ2SHUTTLE.exe --almanac content --assets ../../PvZ2SHUTTLE/assets --frames 3 --snapshot build/snapshots/almanac.png",
   "height": 720,
   "note": "图鉴植物页首屏",
   "sha256": "…",
   "width": 1280
  }
 }
}
```

三个刻意的选择：

* **不存图**。九张 PNG 合计约 4 MB，进仓库只为了让 `git diff` 变慢；sha256 + 字节数 + 宽高足够证明「还是那一帧」，需要看的时候 `--check` 会把图留在 `--out` 目录（默认 `build/snapshots/`）。
* **存 `command`**。哈希脱离命令就是孤证。命令进基线之后，报告里不必再抄参数，`--list` 直接打印。
* **宽高一起存**。只比 sha256 时，分辨率或 DPI 缩放的变化会以「整张图都不一样」的形式出现，看不出是尺寸问题；`width 1280->1024` 一眼定位。
* **不存「实际用的 exe」**。`--check --exe <别的件>` 是常态（跑历史件、跑隔离树），把那个路径写进基线会让文件每次换机器都变；`exe_used` 只出现在 `--report` 的临时报告里，provenance 记在报告 §3.2 与记录行 `--reason` 中。

`load()` 会逐个场景校验 `command / bytes / sha256 / width / height` 的存在与非空，缺一项就是退出码 2，而不是拿半份基线去比。

## 5. 为什么会漂 —— 已知的四个来源

| 来源 | 表现 | 处置口径 |
| --- | --- | --- |
| 铁轨（A2/t81） | `battle-snapshot` 首帧出现钢灰色铁轨车；`cowboy_1` 这类 rail 关的渲染结果与无轨时不同 | 属预期：`--accept battle-snapshot --reason "rail carts drawn from the level's minecarts rows"` |
| 菜单项 3 → 8 | `menu` 的按钮列与 `--menu` 的 rect 整体位移 | 属预期：一次 `--accept menu`，原因写菜单扩容 |
| 存档内容 | `worldmap-screen`（星数）、`level-select`（徽章）、`garden`（已种植物）、`settings`（音量） | 渲染时传固定 `--progress`（或在空存档下跑）；存档一变就重新 `--accept` 并在原因里写存档来源 |
| 字体 / 图集 | 全场景的文本像素 | 这才是真回归：字体文件或 sprite 变了要停下查，不应直接 `--accept` |

上面第一、二条是这次改动的实际原因，也是 D5 存在的意义：它们此前只以「报告里数字变了」的形式存在，没有任何门禁。第二条还有现成的对拍证据——用 `2026-11-25` 的老件与 `snap3` 的新件各跑一次 `--menu`：

```
老件：31,949 B  sha256 37f75744cc8472660b34998718f4339bea9d38f7fdb39870635b13e3087ab7b1   （3 项菜单）
新件：43,630 B  sha256 8bc2a933988a9e6030a910037a4b4945db9af94941ecb374aac90b7c2a261d5a   （8 项菜单）
```

同一台机器、同一份 `content`、同一条命令，只换了二进制：+11,681 B 全是新增的菜单项与它们挪动后的 rect。差别这么大的两帧，此前没有任何地方留下记录。

## 6. 与 D2（`smoke_rebaseline.py`）的分工

| | D2 冒烟基线 | D5 截图基线 |
| --- | --- | --- |
| 覆盖 | 32 个场景的数值矩阵（tick / hash / spawned / killed / leaked / mowerKills） | 9 张 PNG 的字节数与 sha256 |
| 触发方式 | `engine_smoke.py` 跑引擎，无 SDL | 需要 **desktop 构建**（audit 构建没有 SDL，出不了 PNG） |
| 能抓到 | 引擎行为漂移（刷怪、伤害、结算） | 渲染漂移（布局、字体、图集、颜色） |
| 抓不到 | 像素级回归 | 逻辑回归 |
| 产物 | `native/generated/engine_smoke.json` | `native/generated/snapshot_baseline.json` |
| 记录表 | `docs/PARITY_BASELINE.md` 的「冒烟基线变更记录」 | 同文档的「截图基线变更记录」 |

两者**互补，不能互相替代**：`battle-snapshot` 的 sha256 变了而 smoke 的 `hash` 没变，说明只是画法变了；两者同时变，说明行为变了。

## 7. 建议的 check_all 接线

`tools/check_all.ps1` 由队长维护，本任务不改它。建议新增一步，与 D2 的做法对齐（一次渲染、两次比对）：

```powershell
# Step 'snapshot baseline'（建议：紧跟 engine smoke 之后，desktop 构建可用时）
$snapFresh = Join-Path $buildDir 'snapshot_report.json'
python tools/snapshot_baseline.py --report $snapFresh --out (Join-Path $buildDir 'snapshots')
python tools/snapshot_baseline.py --check --from $snapFresh
```

`--report` 会把本次渲染的九条数值写成 JSON（形状与基线一致，可直接 `--from` 复用），`--check` 读它而不是再渲染一遍。失败串建议：

```
[fail] native/generated/snapshot_baseline.json changed; open the two PNGs in build/snapshots or pass -AllowSnapshotChange
```

## 8. 已知缺口与明确不做

* **必须是 desktop 构建**。audit 构建（`-AuditOnly`）没有 SDL，`--snapshot` 写不出 PNG；`--check` 会以 `executable not found` 或 `produced no …png` 明确报错，不会静默通过。
* **五个 meta 屏依赖较新的 `main.cpp`**。`--almanac/--garden/--achievements/--daily/--settings` 是在 2026-11-26 才接进 CLI 的；更老的二进制会退到 `error: expected a command and a directory; use --help`。记录里保留了当时使用的 exe 路径与时间（§3.2）。
* **不做图像 diff**。只比整帧 sha256：给出「变了/没变」，不给出「哪一块变了」。真要看差异就打开两张 PNG（`--out` 目录里留着），用眼睛或用 P4 的像素工具看，不为这一层引入 Pillow 依赖。
* **`battle-snapshot` 不进字节门禁**。它按真实时间推进，跨进程不可复现（6 次 5 个哈希）；仍渲染、仍入库，但只报 `= unstable` 不判红。原因、证据与解法见 §12；`UNSTABLE` 里只有这一条。
* **不存图、不建 LFS**。理由见 §4。
* **不做自动接受**。`--accept` 必须点名场景 + 给 `--reason`，缺一即退出码 2；这是 D2 的同一条纪律，防止「一把全接受」把真回归洗掉。
* **窗口 DPI / 分辨率**：九条命令都用默认窗口尺寸（1280×720 headless 纹理），基线里存了宽高，换机器渲染若尺寸不同会直接报 `width 1280->…`，不会被误判成内容变化。

## 9. 复现

```powershell
cd D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc

# 看有哪些场景、各自命令与已记录哈希
python tools\snapshot_baseline.py --list

# 渲染九张图并比对（有漂移 exit 1）
python tools\snapshot_baseline.py --check

# 用指定可执行文件（默认门禁二进制早于九屏 CLI 时的常规做法）
python tools\snapshot_baseline.py --check --exe C:\pvzbuild\snap3\Release\PvZ2SHUTTLE.exe

# 只重锚自己造成的漂移，并在 PARITY_BASELINE.md 记一行
python tools\snapshot_baseline.py --accept "menu,battle-snapshot" --reason "menu grew 3->8 items; rail carts drawn"

# 自测（不需要 SDL：走 runner 接缝与 --from 报告）；两种跑法都行
python -m unittest tools.tests.test_snapshot_baseline
python tools\tests\test_snapshot_baseline.py
```

## 10. 范围声明

本任务只新增/修改：`tools/snapshot_baseline.py`、`tools/tests/test_snapshot_baseline.py`、`native/generated/snapshot_baseline.json`、`docs/PARITY_BASELINE.md`（只追加一张表）、本文。

未改 `native/src/**`、`content/**`、其它 `native/generated/**` 产物、`tools/check_all.ps1`，未 `git commit`。

## 11. 附：踩坑（真机接线时才暴露的四条）

单元测试用 `runner` 接缝跑得很干净，第一次拿真二进制建档时连着踩了四个坑——都已修好并用测试钉住：

1. **命令里把 `--snapshot` 弄丢了**。`collect()` 原先用 `SCENES[scene][0][:-1]` 拼命令（当成「最后一项是占位符」），于是 `--menu content --assets … --frames 3 --snapshot` 变成 `--menu content --assets … --frames 3 <out.png>`，客户端把路径当选项读：

   ```
   snapshot: menu: exit 1: error: unknown --menu option: D:\…\build\snapshots\menu.png
   ```

   现在 `argv_with_out()` 明确把路径接在 `--snapshot` 之后，`test_snapshot_path_follows_the_snapshot_flag` 钉住。

2. **`--battle-snapshot` 的输出是位置参数，不是 `--snapshot` 的值**。它只要 5 个 argv（`--battle-snapshot <content> <资源根> <out>`），多一个 `--snapshot` 就是 6 个：

   ```
   snapshot: battle-snapshot: exit 1: error: invalid battle preview arguments; use --help
   ```

   引入 `POSITIONAL_OUT = {"battle-snapshot"}`，`test_battle_snapshot_takes_the_path_positionally` 钉住。

3. **`subprocess.run(text=True)` 用 GBK 解 UTF-8 的 JSON**。客户端每屏都往 stdout 打一行中文 JSON，Windows 的 locale 是 GBK，于是 reader 线程抛

   ```
   UnicodeDecodeError: 'gbk' codec can't decode byte 0x80 in position 161: illegal multibyte sequence
   ```

   异常在子线程里，主流程只看到被截断的 stdout——真正的错误信息就此消失。现在 `_run()` 显式 `encoding="utf-8", errors="replace"`。

4. **基线的 `command` 一开始记了绝对路径**。用 `--exe C:\pvzbuild\snap3\...` 建档时，记录里写成了那台机器的绝对路径，换台机器一行都跑不了。现在 `command` 永远写 `build/desktop-gate/Release/PvZ2SHUTTLE.exe`（仓库相对），实际跑的件只进 `--report` 的 `exe_used`，见 §4 第四条。已按新口径重建了一次基线（旧的九行记录在 `docs/PARITY_BASELINE.md` 里被替换，不是追加：那次是我自己的错误录入，不是画面漂移）。

## 12. 附：一个不能做门禁的场景：`battle-snapshot`

第一次打通全流程时它偶发变红，查下去是真问题——**这张帧本身不可复现**。

同一台机器、同一份 `content`、同一条命令，连跑 6 次得到 5 个不同的 sha256（前 12 位）：`10C9FA2A82BF`、`1E11DEC6FB44`、`202C10666632`、`3FBF8848DADD`、`A75979B5EE37`。同一次普查里 `garden`、`worldmap-screen`、`daily`、`achievements` 各 6 次都只有 1 个哈希。

原因在 `native/src/battle_view.cpp`：

* `runBattlePreview()`（约 970 行）先 `scene.runDemo()` —— 固定 1800 次 `world_->step()`，完全是确定性的；
* 紧接着的 `advanceFrame()`（252–262 行）却用**真实时间**推进：`const auto now = SDL_GetTicksNS(); const double dt = (now - previousNs_) / 1e9;`，而 `previousNs_` 在 `BattleScene` 构造时（198 行）只取过一次；
* 于是第一次 `advance` 把**整个资源加载耗时**当成了 dt（`std::min(dt, 0.25)` 封顶）——机器忙一点就多跑几十个 tick，画面自然不同。

处置：

* 代码里 `UNSTABLE = frozenset({"battle-snapshot"})`，基线里该场景记 `"stable": false`；
* `--check` 仍会渲染它、仍会打印它当前的字节数与哈希，但以 `= unstable battle-snapshot … (not gated: renders differ run to run)` 报出，**不计入差异**、不影响退出码；
* `--accept battle-snapshot --reason …` 仍会记录「这一帧现在长什么样」（进记录表），同一哈希二次 accept 只打印 `already recorded`；
* 连续 3 次 `--check` 均 `exit 0`，另外 8 个场景照旧严格比对。

为什么不干脆删掉它：这张图仍然证明「战斗首帧能渲染、不崩、尺寸对、内容在」，而且它是唯一同时含棋盘 / 植物 / 僵尸 / 割草机 / 铁轨车的帧；它只是证明不了「逐字节没变」。删掉会丢掉覆盖面，装作能比则会每次误报。

要让它真正成为门禁，需要 `battle_view` 侧的一次改动（不在本任务写作用域）：`smokeTest` 时用固定步长（例如 `world_->advance(1.0 / 60)`）替代真实时间，或在 `runDemo()` 之后把 `previousNs_` 重置再固定步进一次。改完把该场景从 `UNSTABLE` 移除、重新 `--accept` 一次即可接入门禁。
