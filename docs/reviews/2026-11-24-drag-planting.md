# T50 拖动连续种植（drag-to-plant）

日期：2026-11-24
任务：t49 / T50
写作用域：`native/src/battle_view.cpp`、`native/src/battle_view.hpp`（未改）、
`native/CMakeLists.txt`、`native/tests/battle_drag_test.cpp`、本文件；状态机额外抽到
`native/src/drag_plant.{hpp,cpp}`（契约允许，理由见下）。

## 1. 做了什么

玩家原来只有「点卡 → 点格」两段式。现在按住左键从种子卡拖到草坪、松手就种，拖动过程中
指针所在格有边框反馈。两段式原样保留：按下卡再抬起在卡上（没有位移）只是选中，随后的草坪
点击照旧立即种植。

新增/改动：

| 文件 | 内容 |
| --- | --- |
| `native/src/drag_plant.hpp` | `DragCell`（格子坐标）、`DragVerdict`（6 态）、`DragRules`（占用/冷却/阳光三项前置）、`DragGeometry`（草坪矩形 → 格子）、`DragState`/`DragController`（状态机） |
| `native/src/drag_plant.cpp` | 上述实现：`dragRulesFor` 现问现算、`dragVerdictOf` 的判定次序、`cellAt`/`onBoard`、`begin/moved/release/cancel` |
| `native/src/battle_view.cpp` | 接 SDL 事件（`MOUSE_MOTION` / `MOUSE_BUTTON_UP`）、按下卡时 `drag_.begin`、松手 `finishDrag`、`drawDragPreview` 画边框；Esc/右键/`reset()` 取消拖动 |
| `native/tests/battle_drag_test.cpp` | 6 段无头用例（见第 4 节） |
| `native/CMakeLists.txt` | `battle_drag_test`（audit 配置，连带编译 `src/drag_plant.cpp`）；`pvz_launcher` 源列表加 `src/drag_plant.cpp` |

`native/src/engine/**` 未改（契约只读）；`content/**`、`native/generated/**` 未改。

## 2. 为什么把状态机抽成 `drag_plant.*`

`BattleScene` 是 `battle_view.cpp` 里的匿名类，握着 `sdl::Display`、`AssetCache`、字体和
`engine::World`，没有可注入指针的入口；要测「一次拖动只种一棵」就得造窗口。所以把能判错的
部分（指针 → 格子、三项前置、拒绝语义、一次一棵）放进不含 SDL 的 `pvz::ui` 单元，用真实
`engine::World` 驱动。`battle_view` 只负责：把事件坐标交进去、拿回「该种哪张卡」、调用领域里
唯一合法的种植入口 `World::plant`。这样 `battle_drag_test` 在 audit 配置（无 SDL、无 assets）
就能跑，也是我能把断言而不是截图交出来的原因。

## 3. 语义（每条都对应代码分支）

1. **每格独立判定**：指针每动一次就按当前格现算 `dragRulesFor`（`plantAt` 占用 / `cooldown <= tick` / `sun >= cost`），从不复用按下时的结论；`release` 再用落点格重算一次。所谓「按下选一次、松手直接种」在实现里不存在。
2. **合法落点只走 `World::plant`**：`finishDrag` 拿到卡号后才调用 `world_->plant(...)`，越界/占用/阳光不足/冷却中的判定与「已种下一棵」的判定都在种之前返回 -1，因此不扣费、不发 `planted`。
3. **一次拖动只种一棵**：`release` 一旦置 `planted`，本次拖动结束；重复的 button-up（SDL 在失焦/焦点回来时会补发）拿不到第二次卡号。数据侧也确认没有「拖一片」的植物（第 5 节）。
4. **拖动中不种**：`updateDragPreview` 只写 `DragState`，不碰世界；跨过 10 格也只有松手那一刻落一棵。

判定 → 颜色 → HUD 文案：

| verdict | 预览框 | 松手后 HUD |
| --- | --- | --- |
| `legal` | 绿 `#60D070` | （种下，沿用 `World::plant` 自己的回执） |
| `occupied` | 红 `#D64E42` | 这一格已经有植物了。 |
| `cooling` | 红 `#D64E42` | 这张卡还在冷却。 |
| `noSun` | 灰 `#969696` | 阳光不够，先别种。 |
| `offBoard` | 不画 | 拖到草坪上再松手才能种。 |
| `none` | 不画 | — |

## 4. 测试（`native/tests/battle_drag_test.cpp`，audit 配置）

| 用例 | 断言要点 |
| --- | --- |
| `testLegalDragPlants` | 空闲格预判 `legal`；移动不种；松手返回卡 0；`plantAt` 有植物；阳光正好减 `cost`；`planted` 事件恰好 1 条 |
| `testOccupiedCellRefuses` | 先占格 → 预判 `occupied`；松手 -1；阳光不变；`planted` 不增；拖动结束但仍给 HUD 文案 |
| `testOffBoardRefuses` | 卡带上方的坐标 `inside()==false`、`onBoard==false`、预判 `offBoard`；松手不种不扣费 |
| `testNoSunRefuses` | 取最贵的一张（`cost > sun`）→ `affordable==false`、预判 `noSun`；松手不种不扣费 |
| `testOneDragPlantsOnePlant` | 扫过 3 格不种；第一次松手种 1 棵；同一拖动内再松手 3 次全部 -1；最终只有 1 株、只扣 1 张卡 |
| `testNoCardDragsNothing` | 未 `begin` 时移动/松手都无效、无预览；`begin(-1)` 不激活 |

## 5. 「拖一片」不支持（数据结论）

`content/plants.json` 147 株逐键扫描：键集是 `id/name_zh/name_en/cost/cooldown/hp/family/art/
behavior/damage/interval/projectile/rows/pierce/tags/desc_zh/almanac_no/plantfood/sun_value/
sun_interval/splash/delay/slow/extra/melee_range/element/fused`，**没有任何 drag/multi/batch/
brush/rowPlanting 类字段**；`rows` 是攻击行跨度（5 株多行，如 threepeater `[-1,0,1]`），不是
种植粒度。所以坚持「一次拖动一棵」，不臆造批量种植。

## 6. 无头未变（证据）

`--battle-snapshot` 与 `--menu --frames 2` 走的是同一棵代码树，所以我做了「改动前 exe vs
改动后 exe、同一组输入、逐字节比较」：

| 场景 | 旧 exe（`C:\pvzbuild\flow-desk`，改动前） | 新 exe（`C:\pvzbuild\drag-desk`） |
| --- | --- | --- |
| `--battle-snapshot content <assets> battle.bmp --audio-off` | 3686538 B `D56A3D6AA176CA8F55B7A8F3589272249028C7D101AFA03C1BBEC38123479A90` | 3686538 B **同哈希** |
| `--menu content --progress <p> --assets <assets> --snapshot menu.png --frames 2 --audio-off` | 35611 B `40E842F3C743DA4C5284C1281BE85C8121CA05AE3FB5582A53A73627F0409F0B` | 35611 B **同哈希** |

`--battle-snapshot` 的哈希还等于 T50 开工前记下的基线 `D56A3D6A…9A90`。菜单截图里有一行
`存档：<progress 路径>`，所以整文件哈希依赖 `--progress` 的路径字符串——同一路径下新旧 exe
逐字节相同，这一点已经用它证过（早先我用另一个路径渲染得到的 `2392AC94…` 就是那行字不同，
不是画面变了）。

没有拖动时 `drawDragPreview()` 直接返回，`message_` 默认文案未改，所以无头路径像素不变；
`--frames` 下没有鼠标事件时也不会崩（本次两次快照都是 headless 跑通的）。

## 7. 门禁

| 门禁 | 结果 |
| --- | --- |
| `pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\drag1'` | 25 项，`battle_drag` 绿；见下方「外部红」 |
| `pwsh -File tools/build_native.ps1 -BuildDir 'C:\pvzbuild\drag-desk'` | `100% tests passed, 0 tests failed out of 34`，`DESKTOP_EXIT=0`（含 `battle_render` / `menu_render` / `level_select`） |

外部红（不是本任务改动）：audit 配置的 `audio` 用例在 11:19 与 11:47 两次跑分别报
`audio test failed: --mute-sfx must silence the effect voices` 和
`audio test failed: master volume 0 must produce silence` —— 两次之间 `native/src/audio/audio_mixer.cpp`
在 11:43:31 被改过（sonic 的 T38 在飞），同一份源码在 11:39 的 desktop 构建里 34/34 全绿。
`solutions` 不在我的写作用域，我没有动它。

## 8. 过程中踩到的真坑（写进注释了）

**`class` vs `struct` 前向声明的符号不同**：`drag_plant.hpp` 里我写 `class Catalog;`，而
`catalog.hpp` 是 `struct Catalog`。MSVC 按前向声明的种类修饰符号，于是 `dragRulesFor` 在
`drag_plant.cpp`（先看到 `class`）里修饰成 `…AEBVCatalog…`，在 `battle_view.cpp`（先看到
`struct`）里要的是 `…AEBUCatalog…` —— 桌面链接直接
`error LNK2019: unresolved external symbol "struct pvz::ui::DragRules __cdecl pvz::ui::dragRulesFor(...)"`，
而 audit 的 `battle_drag_test` 因为两个 TU 都先看到 `class` 反而链接通过。改成 `struct Catalog;`
后一次通过。教训：给已有类型写前向声明，tag 必须照抄定义处。

## 9. 反向探针

把 `DragController::release` 改成「松手后仍保持 armed，且去掉 planted 短路」（即连续种植）：

```
battle drag test failed: the release must end the drag
```

`96% tests passed, 1 tests failed out of 25`，失败项 `battle_drag`。探针还原后
`native/src/drag_plant.cpp` sha256 `322E16D39E5213C19D51F0FD6C77C207204280EE84268AA6773FC7EFB9546716`，
`PROBE_` 残留 0，audit 复跑 `battle_drag` 绿、`--battle-snapshot` 哈希仍是 `D56A3D6A…9A90`。

## 10. 还没做

- 触屏/多点：只处理鼠标左键，`SDL_EVENT_FINGER_*` 未接。
- 拖动中预览的是格子边框，不是植物半透明贴图（原版是后者）。
- 从草坪上把已有植物拖到别格（移动/交换）、拖动时自动滚动列表（本作草坪一屏到底，无需滚动）。
- 拖动时暂停/继续的交互未特殊处理（暂停中按下卡不激活拖动，与点击一致）。
