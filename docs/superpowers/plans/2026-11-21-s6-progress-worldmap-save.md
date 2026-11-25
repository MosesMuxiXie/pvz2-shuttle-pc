# S6 — 进度 / 世界地图 / 商店解锁（原生实现）

- **Status:** planned 2026-11-21（S5 运行时正在收尾：t25 Boss → t26 弹道 → t29 护甲 → t30 跳跃）
- **Goal:** 让"打完一关会怎样"在原生客户端里成立：星章按真实战斗结算并落盘、世界地图按星门/钥匙显示可玩关、商店物品按进度解锁。这是把 1809 关从"能跑"变成"能玩下去"的那一层。
- **Architecture:** 纯数据层（`native/src/progress.*` 已有）＋ 一个只读的 `worldmap` 模型 ＋ 一个把 `engine::World` 结果翻译成 `LevelRecord` 的适配器；渲染仍在 `battle_view` 之外的独立 screen，先做快照可验证的静态界面，不做动画。
- **Tech Stack:** C++20 / CMake / CTest / nlohmann-json / SDL3（仅 screen 层）；Python 侧只做数据校验工具，不参与运行期。
- **Spec:** `docs/COMPLETENESS.md` §3「S5–S9 路线」；`docs/superpowers/plans/2026-11-20-full-native-replica.md` 的 S6 条目；Python 基线 `game/screens/worldmap.py`、`game/engine/level.py`（行为参考，不作数据源）。

## Global Constraints

1. 运行期不得依赖 Python / Android；所有表在编译或启动时读 `native/generated/*.json` 与 `content/*.json`。
2. 数值与判定优先级：原版 OBB 表 > `content/` > 常量；常量必须在注释里写 `// fallback: …`，并在报告里登记。
3. 存档写入必须原子（临时文件 + rename），**只增不减**：星章、已通关、最佳 tick 不许因一次失败回退；损坏存档必须报错，不许静默重建覆盖。
4. UI 文本用中文，走 `text.cpp` 的 FreeType 路径；1280×720 letterbox，非 16:9 不得裁切。
5. 未知字段/未知星章类型保留并计数，不许丢行、不许猜语义。
6. 每个新增行为都要有 CTest；CLI 层必须有可复现证据（`--run-level` / `--worldmap` 的 JSON 输出）。
7. 不 commit / 不 push（房规）。
8. 源路径含中文：构建目录必须 ASCII（`C:\pvzbuild\…`），`-D` 传中文路径会被 cl.exe 按 ANSI 读坏（S5.7 已踩）。

## Review Focus

1. **星章可达性**：`content/stars.json` 已知 67 条 kill 目标超过该关僵尸总数（C35）。结算器不得把它们判成"永久 3 星不可达"，也不得偷偷放宽——必须走"可达性判定 + 明确报告"两条路都留证据。
2. **写档时点**：只在关卡终局（won/lost）写一次，不许每 tick 写；重开不得丢已得星章。
3. **世界门的语义**：`star_gate` / `key_gate` / `worldgate` 三种门在原版数据里是不同事件（53 / 27 / 17 条），解锁判定的边界必须逐类写清，不许合并成一个"需要 N 星"。
4. **商店不越权**：`content/shop.json` 585 件里有大量装扮/活动物品，S6 只做"可解锁性分类"，不实现购买流程（S8）。
5. **界面证据**：世界地图必须能出 PNG 快照并在测试里比对尺寸/关键像素，不能只凭"我看到了"。

## 任务

### T32 进度适配器：World → LevelRecord
- **Files:** `native/src/progress.hpp/.cpp`（扩展）、`native/src/main.cpp`、`native/tests/progress_test.cpp`。
- **Interfaces:**
  - `struct BattleOutcome { bool won; std::uint64_t tick; int sun; int sunSpent; int mowersLeft; int zombiesKilled; int plantsLost; };`
  - `BattleOutcome outcomeOf(const engine::World&);`（从 `World` 的公开 getter 取，禁止读私有字段）
  - `void recordBattle(Progress&, const std::string& levelId, const BattleOutcome&, const StarTable&);`
  - `Json progressReport(const Progress&, const StarTable&);`（每关 `stars/cleared/bestTick/goals[]` + 全局 `totalStars`）
- **Steps:**
  - [x] 在 `World` 侧补齐 `sunSpent()` / `mowersLeft()` / `plantsLost()`（若缺，加到 `world.hpp` 的只读 getter，实现放 `world.cpp`）。
  - [x] `outcomeOf` 映射字段；`--run-level` 增 `--progress <file>`，终局写一次并打印 `progressReport` 单行 JSON。
  - [x] 测试：`beach_23` 脚本胜利 → `cleared=true`、`stars==2`（C35 的 kill 10 不可达）；再跑一次失败局 → 星章不减、`attempts` 递增、`bestTick` 取更小值。
  - [x] 测试：存档在非 ASCII 路径下可写可读；损坏 JSON → 抛错且原文件不变。

### T33 世界地图模型（只读）
- **Files:** 新增 `native/src/worldmap.hpp/.cpp`、`native/tests/worldmap_test.cpp`；数据 `content/worldmap.json` + `native/generated/level_modules.json` + `native/generated/world_diff.md`（证据）。
- **Interfaces:**
  - `struct WorldEntry { std::string id; int order; int difficulty; int unlockCost; bool keyRequired; std::string nameKey; };`
  - `struct WorldGate { std::string kind; /* star_gate|key_gate|worldgate */ std::string target; int stars; };`
  - `struct WorldMap { std::vector<WorldEntry> worlds; std::vector<WorldGate> gates; const WorldEntry* find(id); };`
  - `WorldMap loadWorldMap(const fs::path& contentRoot, const fs::path& generatedRoot);`
  - `Json unlockReport(const WorldMap&, const Progress&);`（每世界 `unlocked` / `reason` / `starsNeeded` / `starsHave`）
- **Steps:**
  - [x] 读 `content/worldmap.json` 的 `worlds`（26 条：`order/difficulty/unlock_cost/key_required`）。
  - [x] 从 `native/generated/world_diff.md` 的同源数据（`tools/contentc/worlds.py` 产物）导出 97 条门（星 53 / 钥匙 27 / 世界门 17）到 `native/generated/world_gates.json`；**不解析 markdown**，改让 `tools/contentc/worlds.py` 增 `--emit-json`。
  - [x] `--worldmap <content>` CLI：打印 `unlockReport` 单行 JSON（无 `--progress` 时按全零进度，最大只有 frontyard 可玩）。
  - [x] 测试：26 世界、97 门（53/27/17）、空进度下可玩 1 个世界、给足星章钥匙后可玩 26 个。

### T34 商店解锁分类（不实现购买）
- **Files:** 新增 `tools/contentc/shop_unlock.py`、`native/generated/shop_unlock.json`、`tools/tests/test_shop_unlock.py`；`docs/reviews/2026-11-21-shop-unlock.md`。
- **Steps:**
  - [x] 按 `content/shop.json` 的 `categories` 与 `items` 分类：`seed`（可买种子）/`upgrade`（植物升级）/`world_key`/`costume`/`event`/`unknown`，每类计数与样例 id。
  - [x] 输出每件的 `unlock` 条件字段（`world` / `stars` / `coins` / `none`），缺字段写 `null` 并计 `unknownConditions`。
  - [x] 测试：总数 585 与 `shop.json` 一致、分类无丢行、`unknown` 数量固定并在报告里点名。

### T35 桌面世界地图 screen（静态 + 快照）
- **Files:** 新增 `native/src/worldmap_view.hpp/.cpp`（desktop 块）、`native/tests/worldmap_render_test.cpp`；`main.cpp` 增 `--worldmap-snapshot <content> <out.png>`。
- **Steps:**
  - [x] 26 世界按 `order` 排成一行卡片：名字（中文）、难度、锁图标、已得/需要星章、钥匙标记；底部显示总星章与金币。
  - [x] 选中卡片显示"这个世界包含"面板：关卡数、Boss 数（来自 `level_modules.json`）、已通关数/星章。
  - [x] `battle_view` 增加返回地图入口（ESC 在终局界面回地图），不改现有战斗输入语义。
  - [x] 快照测试：1280×720 PNG、非空、尺寸一致、两次渲染字节相同；中文标题像素非空（复用 `text_test` 的字形覆盖断言）。

### T36 门禁与文档
- **Steps:**
  - [x] `tools/check_all.ps1` 增 `worldmap` 与 `shop unlock` 两步（Python `--check`）；audit/desktop 两配置分别统计新用例数。
  - [x] `docs/PARITY_BASELINE.md` 增「S6 增量」：新 CLI、新用例数、星章结算证据、世界地图快照 sha。
  - [x] `docs/NATIVE_PROGRESS.md` 增 S6 节；`docs/COMPLETENESS.md` 更新「进度与存档」「UI」两行百分比并引用实测数字。
  - [x] 计划文档勾选；`docs/reviews/2026-11-21-s6-report.md` 汇总每条门禁的真实输出。

## 门禁

进展（2026-11-23 10:48）：**7 条门禁全部通过**。相对 08:40 的读数有三处变化：
① 桌面 `worldmap_render` 已落地（§2.23），desktop 25→**26**；
② 商店从数据表变成可买模型（`--shop`/`--buy`，可买 21、`seed_iris` 实测发放，§2.24），audit 19→**20**；
③ t35/t36/t37 三轮审计收口（H1/H2 真关、N2/N3 已修、kungfu 拼写归一、cleared 口径收到
`map::clearedLevelsFor`），台账现为 **20 / 296 / 26**。

1. `pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir C:\pvzbuild\s6a` → 全绿（含新增 `worldmap`、`progress` 断言）。
   **已过**：`C:\pvzbuild\wm1` → 19/19（08:32）；后随商店模型涨到 **20/20**（`C:\pvzbuild\cl1`，10:12）。
2. `pwsh -File tools/build_native.ps1 -BuildDir C:\pvzbuild\s6d` → desktop 全绿（含 `worldmap_render`）。 **已过**：`C:\pvzbuild\wm-desktop` → 25/25（08:55）；后随商店模型涨到 **26/26**（`C:\pvzbuild\cl-desktop`，10:20）。
3. `python -m unittest discover -s tools/tests -p 'test_*.py'` 全绿，例数为下界口径。**已过**：Ran 296（2026-11-23 08:34）。
4. `python tools/engine_smoke.py` 零差异（S6 不许改战斗数值；仅 `--progress` 新参数不得影响既有场景）。**已过**：32 场景 0 diff（t30 收窄 vault 窗口后仍全等）。
5. `--run-level content beach_23 --script native/tests/scripts/beach_23_win.json --progress <tmp>` 第二次运行读回同值（幂等），且 `beach_23` 仍只得 2 星（C35 如实）。**已过**：goals [true,true,false] stars=2 target=3，tick 1534，6x9。
6. `--worldmap content` 空进度输出 `unlocked=1`（frontyard）、`stars=0`；喂一份 3 星存档后对应世界解锁。**已过**（口径改为 `state`）：空进度 26 世界全 locked（frontyard needs 1 stars）；喂 beach_23 胜局（2 星）后 frontyard 变 `available`、egypt 仍 locked（needs 1 keys）。
7. `tools/check_all.ps1` 退出码 0（严格模式，不 `-AllowMatrixChange`）。**已过**：08:34 严格跑 EXIT=0（19/24/296）；10:30 与 10:35 两次严格跑仍 EXIT=0，台账 **20/296/26**。

## Execution Handoff

默认按 **Subagent-driven**：T32/T33 给 wirer（引擎），T34 给 mapper（Python 数据），T35 给 wirer（desktop），T36 由队长收口。T33 的 `world_gates.json` 依赖 `tools/contentc/worlds.py --emit-json`，先做那一步再动 C++。所有任务写作用域互斥，禁 commit。

## 依赖与已知事实（别再查一遍）

- `content/worldmap.json` 结构：`{ "worlds": { id: {id, order, name_key, difficulty, unlock_cost, key_required, desc} } }`，26 条。
- `content/stars.json` 结构：`{ levelId: [ {type, value, max?, count?, text_zh} ] }`，1702 条 kill 中 67 条不可达（C35）。
- `Progress` 已实现：`loadProgress/parseProgress/saveProgress/recordAttempt/evaluateStars/progressToJson`；星章只增、`bestTick` 取快、原子写。
- `native/generated/level_modules.json` 已含每关 `boss`/`vasebreaker`/`rail`/`night` 标记（14 键）。
- 世界门数据来自 `tools/contentc/worlds.py` 解析的 `pkg_2107_WorldData.json` `m_eventList`（level 1248 / plant 231 / star_gate 53 / key_gate 27 / worldgate 17）。
- `content/shop.json` 结构：`{version, source, exchange, categories, seed_pool, items, meta}`，585 件。

## 数据侧现状（2026-11-21 10:35，已交付）

| 表 | 产物 | 实测口径 |
| --- | --- | --- |
| 世界门 | `native/generated/world_gates.json` | 97 条门：star_gate **53** / key_gate **27** / worldgate **17**；`unknownKinds` 真实数据 0 个；52,018 B，sha256 `D2DB7D6A…6AAA0` |
| 商店解锁 | `native/generated/shop_unlock.json` | 585 件：seed 81 / upgrade 11 / world_key 1 / costume 447 / event 32 / unknown 13；解锁 kind：`none` 484 / `coins` 99 / `world` 1 / `mixed` 1 / `stars` 0；251,592 B |
| 星章任务 | `content/stars.json` | 1809 关 / 5427 条目标；`beat` 1808、`mowers` 1784、`kill` 1702、`sun_used` 31、`sun_produced` 61、`plants_lost` 36、`time` 5 |

三条必须记住的口径：

1. **`key_gate` 的 `m_cost` 是钥匙数（1/3/4/5），不是星数**；`star_gate` 的 `m_cost` 才是星数（0/1/8/10/20）。
   混用就是造假。t34 正在给导出补 `keys` 字段（与 `stars` 分开，各缺各的 null）。
2. **`world` 是 WorldData 的 `m_worldName`**（`gta`/`skycity`/`rainbowmarket`），与 `content/worlds.json` 的 client id
   差三个别名（→`losantosvice`/`sky`/`lunarrainbowmarket`）。t34 在导出里并列 `worldClient`/`targetClient`，
   不在原字段上偷改。
3. **`egypt` 一个门都没有**（只有 level/plant 事件）；45 个世界有门。别把"无门"当成导出漏项。

商店侧的两个已知缺口（`docs/reviews/2026-11-21-shop-unlock.md` §6/§8）：

- 源里**没有门槛字段**（对 unlock/requires/stars/world/level 等 10 键 585 条 0 命中），所以 `stars` 恒 null、
  只有 100 条能给出 `coins` 价格；这是数据事实，不是解析漏项。
- `mint` 计价 10 条（金金茶券）在 `price.currency` 的 `coins|gems|none` 枚举里无对应值，导出为 `none` + `amount:null`，
  真相留在 `rawKeys.currency=mint`。S6 若要显示价格，得先决定 mint 怎么折算。

