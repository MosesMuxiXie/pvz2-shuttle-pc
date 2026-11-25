# PvZ2 SHUTTLE 原生 C++ 完整复刻实施计划

> **进展（2026-11-24 21:00 实测，替代此前所有读数）**：S0–S6 完成；**数据包已对齐最新版 460.9**
> （原 460.1 → 用官方 `.rsbpatch` 两跳升级，MD5 与 manifest 逐字相同；补丁解码器 `tools/rsbpatch.py` 已复刻）。
> 当前门禁：audit **27/27**、desktop **36/36**、Python **439**，`tools/check_all.ps1` 全量（含 content）
> **EXIT=0**；产物 `build/native/Release/PvZ2SHUTTLE.exe` 1,151,488 B `3D359952…E332`、
> `build/desktop-gate/Release/PvZ2SHUTTLE.exe` 4,413,952 B `0A543A7C…BFA2`（数据 rebase 未改 C++）。
> 版本真相：游戏 **26.11.1** / 核心库 **460.11** / 数据 **460.9**（我们原来的 `main.460….obb` 其实是 460.1）。
> 逐阶段状态见下面「1.1 阶段状态」，数据 rebase 全过程见
> `2026-11-24-obb-460.10-rebase.md`，「还缺什么」见 `docs/COMPLETENESS.md` §2.28–§2.33 与 §3 缺陷表。
> **编号提醒**：本总表的 S5=美术与音频、S6=存档/经济/进度；但实际执行时另写了
> `2026-11-20-s5-elements-plantfood-fusion-boss.md`（元素/养料/融合/Boss）与
> `2026-11-21-s6-progress-worldmap-save.md`（进度/世界地图/商店）。两套编号并存，看文档时以文件名为准。
>
> **For agentic workers:** 本计划按阶段（Stage）推进。S0/S1 已细化到可勾选步骤；S2 起每个阶段在启动时补一份同目录的详细任务计划，再逐任务实现。执行用 `executing-plans`；需要并行广度工作时用 `subagent-driven-development`。步骤用 `- [ ]` 跟踪。
>
> 文中路径一律相对仓库根 `repo/pvz2-shuttle-pc/`，除非写明「工作区」（`D:\OneDrive\文档\pvz_shuttle\`）或「OBB 表目录」（工作区 `work/obb_packages/`）。

**Goal:** 用独立 C++20/SDL3 客户端完整复刻 PvZ 2 SHUTTLE v26.10.1 —— 26 世界 1809 关全部可玩、全部角色行为/元素/养料/融合/Boss/模式/元游戏/界面/音频/存档到位，最终以原生安装包替换 Python 发行入口。

**Architecture:** 三层。① `tools/contentc`（离线 Python 工具，仅构建期）把原版 OBB 属性表 + 关卡定义编译成 `native/generated/content.pack` 与覆盖报告；② `native/src/engine`（无图形依赖、固定 60Hz、种子+输入可复现）以数据驱动的行动系统 + 行为类注册表承载全部玩法；③ `native/src/view` + `native/src/ui` 用 SDL3 渲染 DragonBones 场景与屏幕栈。Python 版 `game/` 是**广度参考实现**（结构照搬、逐屏移植），OBB 属性表是**精度权威**（数值以表为准）。

**Tech Stack:** C++20 · CMake ≥3.21 · CTest · SDL3 3.2.28 · SDL3_image 3.2.4 · FreeType 2.13.3 · nlohmann/json 3.12.0 ·（新增，SHA-256 固定）SDL3_mixer 3.x（ogg/mp3/wav）· Python 3.14（仅构建期工具）· Inno Setup 6（Windows 安装包）· macOS：Xcode + `macdeployqt` 等价的 `dylibbundler`/自建脚本。

**Spec:** `docs/superpowers/specs/2026-11-10-native-client-design.md`（已批准：独立 C++ 客户端、完整后切换发行入口）。

---

## 0. 现状基线（2026-11-20 实测，非推断）

**原生端已有**（12/12 CTest 通过，`tools/build_native.ps1`）：

| 能力 | 状态 |
| --- | --- |
| 内容加载 | 26 世界 / 147 植物 / 55 僵尸 / 1809 关（1646 `obb` + 163 `obb-synth`）；严格校验 |
| 模拟 | 60Hz 固定步长、种子 RNG、事件轨迹；30/60/120Hz 状态一致 |
| 可玩范围 | **仅 `frontyard` 首关**，硬编码 4 张卡（sunflower/peashooter/wallnut/potatomine） |
| 表现 | DragonBones 5.5 骨骼/蒙皮/affine；FreeType 中文 HUD；1280×720 letterbox |
| 存档 | Python v2/v3 只读迁移（原子写、备份、不覆盖） |

**原版表实测规模**（`work/obb_packages/`，本次实测）：

| 表 | 对象数 | 去重后 |
| --- | --- | --- |
| `pkg_2074_PlantType` | 339 植物类型 | **235 个 `PlantFramework` 行为类**、329 个 `PopAnim` |
| `pkg_2073_PlantPropertySheet` | 398 条属性 | 动作类型：projectile 410 / special 200 / explode 33 / sun 16 / plantfood 6 / manual 1 |
| `pkg_2115_ZombieType` | 1127 僵尸类型 | **183 个 `ZombieClass` 行为类**、539 个 `PopAnim` |
| `pkg_2112_ZombiePropertySheet` | 932 条属性 | 按类分表（Gargantuar 53、CakeTank 38、RomanHealer 72…） |
| `pkg_2107_WorldData` | 46 世界条目 | 含 `m_worldId`/`m_resGroupID`/`m_eventList` |
| `pkg_2000..2047_LevelDefinition` | 48 份原始关卡定义 | 派生出 1809 关 |

**关键落差**：当前可玩内容 ≈ 0.2% 的关卡、≈ 1.7% 的植物行为类、≈ 0.5% 的僵尸行为类；`content/` 的 147/55 是图鉴可玩集，不是原版全类型（339/1127）。**战斗必做集合由工具从 1809 关的 spawn 引用里算出来**（S1 产出数字），原版全类型必须能被解析与承载。

**美术资源落差**：`PvZ2SHUTTLE/assets/db/` 仅 32 植物 / 16 僵尸 / 24 投射物组，而 PopAnim 需求 329/539 —— 必须从本地 OBB（2,095,579,136 B）按需全量提取，这是 S5 的前置条件，不是可选项。

---

## Global Constraints

- 运行期**不依赖** Python / Android / WSL；Python 只用于构建期工具与测试脚本。
- 确定性：固定 `1/60 s` 步长；`seed + 输入序列 + 关卡` 唯一决定状态哈希；同一输入在 30/60/120Hz 采样下终态一致。
- 数据优先级：**OBB 属性表 > 关卡定义 > Python content > 推断**。任何推断必须在覆盖报告里标 `inferred`，不得静默。
- 未识别字段一律保留在 `raw`（现有 `pierce` 0/1 或 bool、`plantfood` bool 或串、`extra.boss_zombie` 为 OBB 代号等怪点**禁止"修正"**）。
- 逻辑分辨率 1280×720，等比 letterbox；16:10 / 4K 下不裁切、中文不破行。
- 新资产必须可追溯到 OBB 内路径或 `work/refs/`；禁止占位方块进入「完成」状态。
- 每个新增功能必须有 CTest 用例；headless 模拟路径不得触碰图形设备。
- 平台：Windows 10/11 x64 必须实测；macOS 11+ Universal 2 为交付目标，**在 macOS 机器上实测通过前不得宣称可用**。
- 不删除 `content/levels_before_*` / `levels_legacy` 备份；不执行 git commit / push（除非用户明确要求）。

## Review Focus

1. **关卡引用了不存在的类型**（某关 spawn 一个没有数据/没有模型的僵尸）→ 期望：显式 fallback + 覆盖报告条目 + 可继续开局，而不是静默丢怪或崩溃。
2. **RTID 解析歧义**（同名别名跨表、循环引用、`RTID(0)`）→ 期望：解析确定、可复现、冲突写进报告。
3. **存档半写**（写档中断电/进程被杀）→ 期望：旧档完好、临时文件被清理、下次启动可用。
4. **大表冷启动**（339+1127+1809 条）→ 期望：启动到可选关 ≤ 1.5s（SSD），内存 ≤ 400MB，惰性加载不破坏确定性。
5. **非 16:9 缩放与中文排版**（21:9、4K、HUD 贴边）→ 期望：不裁切、不重叠、可点区域与视觉一致。

---

## 1. 阶段总表

| 阶段 | 主题 | 交付物 | 门禁（DoD） | 粗估 |
| --- | --- | --- | --- | --- |
| **S0** | 基线固化 | `docs/PARITY_BASELINE.md`、`tools/parity_report.py`、`docs/PARITY_MATRIX.md` | 构建+12 测试全绿快照入库；矩阵能自动算出 0% 起点 | 0.5 轮 |
| **S1** | 内容编译管线 | `tools/contentc/`、`native/generated/content.pack`、`native/src/content/` | 15 张主表全部解析；0 个未解析 RTID；覆盖报告逐类给数字；`--audit-content` 一致 | 1–2 轮 |
| **S2** | 引擎内核 v2 | `native/src/engine/*`、回放工具 | 任意关卡 headless 快进到结算；事件哈希稳定；6×10/5×9 均通过 | 2–3 轮 |
| **S3** | 战斗内容覆盖 | 行为类注册表、元素/养料/融合/Boss/模式 | PARITY_MATRIX「战斗」行 100%；每世界前 5 关录像对比通过 | 4–6 轮 |
| **S4** | 元游戏与界面 | `native/src/ui/*` 全屏幕 | 启动器→主菜单→世界地图→选卡→战斗→结算全链路可点通 | 4–5 轮 |
| **S5** | 美术与音频 | OBB 全量提取、特效、音频总线 | 无占位方块；`Play_*` 事件覆盖 ≥95%；26 世界场景齐全 | 3–4 轮 |
| **S6** | 存档/经济/进度 | 存档 v2、星章、商店、花园 | 三星/钥匙/奖励/货币闭环；迁移与断电测试通过 | 2 轮 |
| **S7** | 平台交付 | Windows 安装包+便携包、macOS .app+DMG | 干净机器安装→启动→进首关；macOS 实测 | 1–2 轮 |
| **S8** | 联网与收尾 | HTTPS 版本/公告、离线降级 | 证书校验开启；无网可玩；文档/CHANGELOG 完整 | 1 轮 |

里程碑：**M1**=S0–S2（引擎可跑任意关卡）→ **M2**=S3 前 3 批 + S4 骨架（埃及世界可玩通）→ **M3**=S3+S4 完成（26 世界全通、全 UI）→ **M4**=S5（视听完整）→ **M5**=S6–S8（可发行）。

---

### 1.1 阶段状态（2026-11-25 实测）

> 活的剩余清单在 [`docs/PROGRESS.md`](../../PROGRESS.md)：按 P0/P1/P2 分了 21 条，带量化与门禁红线。
> 本节只保留阶段级结论。当前读数：audit **27** / Python **469** / desktop **36**，静树严格模式 EXIT=0。

| 阶段 | 状态 | 已落地 | 未做 / 缺口 | 证据 |
| --- | --- | --- | --- | --- |
| **S0 基线固化** | ✅ 完成 | `docs/PARITY_BASELINE.md`、`tools/parity_report.py`、`docs/PARITY_MATRIX.md`、`tools/check_all.ps1`（树动 → exit 2、构建重试带 `-Clean`、`-UpdateLedger`、`__pycache__` 不进树指纹） | — | 门禁静树 EXIT=0：audit 27/27、Python 469、desktop 36/36，台账三项一致 |
| **S1 内容编译** | ✅ 完成 | 12 张主表 → `content.pack`（339 植物 / 1127 僵尸）、`coverage.json`、`id_mapping.csv`。**数据包已对齐最新版 460.9**（460.1→460.2→460.9 走官方 `.rsbpatch`，MD5 与 manifest 逐字相同；`tools/rsbpatch.py` + oracle `tools/emulate_rsb.py`） | 295 植物 / 1107 僵尸在客户端侧没有 id（`id_mapping.csv` 已逐条列出）；460.9 新增的 `RlConfig` / `ThymedEventSchedule` 只有数据无消费者（C57 部分） | `Catalog::rules` 优先读 pack，坏包显式抛错；§2.32–§2.33 |
| **S2 引擎内核** | ✅ 完成 | `native/src/engine/*`（world/director/registry/action_runner/projectile/replay/rewards）、32 场景冒烟 | — | `engine_smoke.json` 32 场景双跑零差异 |
| **S3 战斗覆盖** | ✅ 完成 | 11 植物族（339/339）、183 僵尸族、护甲 102（接线 91）、弹道 602（接线 593）、养料 293、融合 85、Boss 50/155 阶段、元素 `authored` 默认关；**关卡机制五类接线**（传送带 348/350、初始植物 272、初始物件 583/690、墓碑 353、保护 286） | `spawnOffset.y` 只有数据、渲染不用；rail 192 关标记齐但引擎不消费（矩阵「铁轨」wired=0） | §2.13–§2.19、§2.25、§2.30；`mechanics_test` 8 段；矩阵「关卡机制」wired=903 |
| **S4 元游戏与界面** | ✅ 闭环 | 启动器、战斗视图、`--play-script`、`--worldmap-screen`、`--shop`、`--progress`、`--menu`、`--level-select`、`--flow`（选关→战斗→结算→写档→下一关）、**拖动连续种植**（`drag_plant.*`） | 图鉴 / 花园 / 设置未做 | §2.20、§2.23、§2.24；`--flow` 两轮实测 |
| **S5 美术与音频** | ✅ 有声有音量 | OBB **1085/1087** base（ASTC 5x5/6x6 解码 10 条）、`art_index` + `--art-audit`；音频 65 sounds（65 解码 / 4487.9 s）、22/40 引擎事件接通、四屏都 `pump()`、`--volume 0..100` + `--mute-bgm/--mute-sfx` + BGM 0.75 s 交叉淡入、minimp3 | 混音器 8 voice / 最近邻 / 无独立滑杆 UI（C52）；`UI_ALWAYSLOADED` 尺寸缺声明不修 | §2.26、§2.27；真设备 `146944 mixed frames`；`peak(0)=0.000000` |
| **S6 存档/经济/进度** | ✅ 完成 | 星章 5427（`beach_23` 如实 2 星）、世界地图 26/97 门、商店 585（可买 21、种子真发放、`one_time` 生效）、`--progress` 原子写、**掉落闭环**（金币按击杀周期 / 8 条钥匙 / 36 张午餐盒 / 76 条种子包，13 张悬空表不发）、`Progress::seeds`/`purchases` | 逐关 LootConfig/PresentTable 绑定缺失（C56）；keys=1 就能开 25 个世界（C46）；花园 UI 未做 | §2.20–§2.24、§2.31；矩阵「掉落」575/575/130；C35/C46/C48/C56 |
| **S7 平台交付** | ⬜ 未开始 | 计划已成文 `2026-11-24-packaging.md`（7 件事 + 4 条门禁 + 明确不做） | CMake `install()`、版本号单一来源、资源/存档查找顺序、LICENSES、README、`tools/package.ps1`；macOS 无机器只能标「未实测」 | 目前只有 `build/*/Release/PvZ2SHUTTLE.exe` |
| **S8 联网与收尾** | ⬜ 未开始 | 离线可用（默认不发请求） | HTTPS 版本查询/公告、证书校验、无网降级测试 | 原版联网面本来就只有版本查询 |

### 1.2 下一步队列（2026-11-25 重排；细节见 `docs/PROGRESS.md` §2）

0. **460.9 收尾**（数据已对齐）：`suppressFlagZombie` 271 关已进 content + 引擎抑制旗子波（t64/t65 完成）；
   `RlConfig`（肉鸽 17 字段）与 `ThymedEventSchedule`（30 条、新增 29/30/31）只有数据，消费者 0（C57）；
   核心库 460.11 的肉鸽/老虎机/酸性/虚空龙**数据包里没有对应数据**，不做反推（C59）。
1. **玩法补齐优先**：关卡机制剩 342 关 → 砸罐子 47 → 小游戏 45（`PROGRESS.md` P0 #1–#3），这是「像不像原版」的最大缺口。
2. **S7 打包**（用户已定「打包留到最后」，但代码侧已无阻塞）：按 `2026-11-24-packaging.md` 做
   `install()` + 资源/存档查找 + `LICENSES.md` + `tools/package.ps1`；收官前要问用户三件事
   （是否带 OBB 美术、是否保留调试 CLI、版本号起点）。
2. **尚未接线的原版机制**（矩阵「关卡机制」剩 342 关）：`events` 123 关、`mutators` 21 关、
   `boardGrid` 49 关、海滩/鱼/恐龙生成器；`rail` 192 关与 `vasebreaker` 47 关玩法本身也未实现。
3. **逐关掉落绑定**（C56）：拿到「关卡→LootConfig / PresentTable」后补，否则 47 关 danger/whack 落 default、
   13 张悬空表 68 关没午餐盒。
4. **S8 联网**：版本查询 + 公告的 HTTPS 客户端与证书校验开关。
5. **可选打磨**：混音器插值与独立音量滑杆（C52）、图鉴/花园/设置三屏。

## 2. S0 基线固化（详细任务）

### Task 0.1: 构建与测试基线快照

**Files:**
- Create: `docs/PARITY_BASELINE.md`
- Modify: 无

**Interfaces:**
- Consumes: `tools/build_native.ps1`、`native/tests/*`
- Produces: 基线文档（含 commit、时间、编译器版本、测试清单、`--audit-content` 原文输出）

- [x] **Step 1: 跑无桌面的审计构建**

Run: `pwsh -File tools/build_native.ps1 -AuditOnly`
Expected: `100% tests passed, 0 tests failed out of N`

- [x] **Step 2: 跑桌面构建并记录产物哈希**

Run: `pwsh -File tools/build_native.ps1` 然后 `Get-FileHash build/native-desktop/Release/PvZ2SHUTTLE.exe -Algorithm SHA256`
Expected: 0 错误；记录 exe SHA-256 与大小

- [x] **Step 3: 抓取内容审计输出**

Run: `build/native-desktop/Release/PvZ2SHUTTLE.exe --audit-content`
Expected: 26 世界 / 147 植物 / 55 僵尸 / 1809 关（1646 obb + 163 obb-synth）

- [x] **Step 4: 写 `docs/PARITY_BASELINE.md`**

写入：日期、git `rev-parse --short HEAD`、`cmake --version`、`MSVC` 版本、测试数、以上两条输出原文、exe 哈希。

- [x] **Step 5: 复核**

Run: 重新执行 Step 1 确认可重复
Expected: 与 Step 1 相同的测试数

### Task 0.2: 覆盖矩阵生成器

**Files:**
- Create: `tools/parity_report.py`
- Create: `docs/PARITY_MATRIX.md`（生成产物，提交）
- Test: `tools/tests/test_parity_report.py`

**Interfaces:**
- Consumes: `content/*.json`、`content/levels/*.json`、`work/obb_packages/pkg_2074_PlantType.json`、`pkg_2115_ZombieType.json`、`pkg_2083_PlantFusionConfig.json`（可选缺失则标 `unknown`）
- Produces: `build_parity_matrix(obb_dir: Path, content_dir: Path) -> dict`，键为 `plants|zombies|worlds|levels|fusions|bosses|modes`，值为 `{total, data, wired, playable, calibrated}`；`render_markdown(matrix) -> str`

- [x] **Step 1: 写失败测试**

`tools/tests/test_parity_report.py`：
- `test_totals_from_obb`：对 339/1127 两个硬数字断言（从 OBB 表读，不从常量）
- `test_level_reference_closure`：断言 1809 关中出现的 plant/zombie id 集合 ⊆ 数据集合，且返回 `missing` 为空
- `test_render_has_header`：`render_markdown` 输出含 `| 类别 | 总量 | 数据 | 接线 | 可玩 | 校准 |`

- [x] **Step 2: 跑测试确认失败**

Run: `python -m pytest tools/tests/test_parity_report.py -q`
Expected: FAIL（`ModuleNotFoundError: tools.parity_report`）

- [x] **Step 3: 实现 `build_parity_matrix` 与 `render_markdown`**

「接线/可玩/校准」三项从 `native/src/engine/registry.cpp` 的注册表符号（S2 才有，缺失时按空集合处理）与 `native/tests/golden/` 存在性推导；S0 阶段两者皆空 → 全 0，这是**预期起点**，不是缺陷。

- [x] **Step 4: 跑测试确认通过**

Run: `python -m pytest tools/tests/test_parity_report.py -q`
Expected: `3 passed`

- [x] **Step 5: 生成并检视矩阵**

Run: `python tools/parity_report.py --obb work/obb_packages --content content --out docs/PARITY_MATRIX.md`
Expected: 文件生成，植物总量 339、僵尸总量 1127、关卡 1809

### Task 0.3: 工作区脚本归位

**Files:**
- Move: 工作区 `work/probe_sheets.py` → 删除（一次性探针，结论已写入本文第 0 节）
- Create: `tools/contentc/sheets.py`（S1 Task 1.1 的占位骨架，仅含 `load_sheet(path) -> dict` 与 `iter_objects(doc) -> Iterator[dict]`）

**Interfaces:**
- Produces: `load_sheet(path: Path) -> dict`、`iter_objects(doc: dict) -> Iterator[dict]`（跳过 `#comment` 键与非 dict 项）

- [x] **Step 1: 实现上述两个函数（不做别的事）**
- [x] **Step 2: 用 `pkg_2073_PlantPropertySheet.json` 手工验证**

Run: `python -c "from tools.contentc.sheets import load_sheet, iter_objects; import pathlib; d=load_sheet(pathlib.Path(r'../work/obb_packages/pkg_2073_PlantPropertySheet.json')); print(sum(1 for _ in iter_objects(d)))"`
Expected: `398`

- [x] **Step 3: 删除一次性探针**

Run: `Remove-Item ..\work\probe_sheets.py`

### Task 0.4: 回归门禁脚本

**Files:**
- Create: `tools/check_all.ps1`
- Modify: `tools/build_native.ps1`（末尾追加可选 `-WithParity` 开关，默认关）

**Interfaces:**
- Produces: `check_all.ps1 [-SkipDesktop]`，退出码 0/1，输出 `[ok]`/`[fail]` 逐项

- [x] **Step 1: 写脚本**：审计构建 → CTest → `parity_report.py` 生成对比（与提交版 diff，无变化则忽略）→ 打印摘要
- [x] **Step 2: 跑脚本**

Run: `pwsh -File tools/check_all.ps1`
Expected: 全部 `[ok]`，退出码 0

---

## 3. S1 内容编译管线（详细任务）

目标：把原版表变成**运行期只读、启动快、可校验**的单一数据源，替换现在「Python 导出的 content JSON」作为战斗数据来源。

### Task 1.1: 属性表解析与 RTID 解析器

**Files:**
- Modify: `tools/contentc/sheets.py`
- Create: `tools/contentc/rtid.py`
- Test: `tools/tests/test_rtid.py`

**Interfaces:**
- `parse_rtid(text: str) -> tuple[str, str | None]`（`"RTID(PeaDefault@ProjectileTypes)"` → `("PeaDefault", "ProjectileTypes")`；`"RTID(0)"` → `("0", None)`）
- `SheetIndex(objects: list[dict]) -> SheetIndex`，方法 `resolve(name: str, sheet: str | None) -> dict | None`、`duplicates() -> list[str]`
- `load_sheets(obb_dir: Path) -> dict[str, SheetIndex]`，键为表名（`"PlantProperties"`、`"PlantTypes"`、`"ZombieProperties"`、`"ZombieTypes"`、`"ProjectileTypes"`、`"Fusions"`…）

- [x] **Step 1: 写失败测试** — `test_parse_rtid_basic`、`test_parse_rtid_zero`、`test_resolve_cross_sheet`、`test_duplicate_alias_reported`（构造同名两对象，断言 `duplicates()` 含该名且 `resolve` 返回首个并**标记冲突**）
- [x] **Step 2: 跑测试确认失败** — `python -m pytest tools/tests/test_rtid.py -q` → FAIL
- [x] **Step 3: 实现** — 解析 + 索引；`resolve` 大小写敏感（原表大小写混用，不得归一化）
- [x] **Step 4: 跑测试确认通过** — `3 passed` 起步
- [x] **Step 5: 全表冒烟** — `python -c "...load_sheets(obb); print({k: len(v) for k,v in sheets.items()})"` 期望五张表非空且 `duplicates()` 数量记录进基线

### Task 1.2: 归一化数据模型（C++ 侧）

**Files:**
- Create: `native/src/content/model.hpp`
- Create: `native/src/content/loader.cpp`
- Create: `native/src/content/loader.hpp`
- Test: `native/tests/content_test.cpp`

**Interfaces:**
- `namespace pvz::content`
- `struct PlantAction { enum class Kind { projectile, sun, explode, special, manual }; Kind kind; std::string projectile, special, trigger; double cooldownMin=0, cooldownMax=0, initialMin=0, damage=0; Json raw; }`
- `struct PlantType { std::string typeName, framework, popAnim, homeWorld, propsRef; int cost=0; double hp=0, packetCooldown=0; std::string gridType="ground", height="normal"; std::vector<PlantAction> actions; Json raw; }`
- `struct ZombieType { std::string typeName, zombieClass, popAnim, homeWorld, propsRef; double hp=0, speed=0, speedVariance=0, eatDps=100; std::vector<ArmorLayer> armor; Json raw; }`
- `struct ContentPack { std::map<std::string, PlantType> plants; std::map<std::string, ZombieType> zombies; std::vector<FusionRecipe> fusions; Json meta; }`
- `ContentPack loadContentPack(const std::filesystem::path& packPath)` —— 严格：缺字段/悬空引用抛 `ContentError` 并带条目名

- [x] **Step 1: 写失败测试** — fixture（两个植物、一个僵尸的最小 pack）断言字段映射；再断言一个悬空 `propsRef` 触发 `ContentError` 且消息含条目名
- [x] **Step 2: 跑测试确认失败** — `ctest -R content --output-on-failure` → FAIL
- [x] **Step 3: 实现结构体与 loader** — 用 nlohmann/json 读；未知键整体塞进 `raw`
- [x] **Step 4: 跑测试确认通过**

### Task 1.3: 编译器（表 → pack + 覆盖报告）

**Files:**
- Create: `tools/contentc/build_content.py`
- Create: `tools/contentc/emit.py`
- Test: `tools/tests/test_build_content.py`

**Interfaces:**
- `build(obb_dir: Path, content_dir: Path, out_dir: Path) -> BuildReport`
- `BuildReport` 字段：`plants_total, plants_resolved, zombies_total, zombies_resolved, levels_total, level_refs, missing_refs: list[str], inferred: list[str], duplicates: dict[str, list[str]]`
- 输出：`native/generated/content.pack`（紧凑 JSON，稳定键序）、`native/generated/coverage.json`

- [x] **Step 1: 写失败测试** — 对真实 OBB 目录跑：断言 `plants_total == 339`、`zombies_total == 1127`、`missing_refs == []`；断言同一输入两次运行产物**字节相同**（确定性）
- [x] **Step 2: 跑测试确认失败**
- [x] **Step 3: 实现合并逻辑** — `PlantType + PlantProperties` 合并；`ZombieType + ZombieProperties` 合并；`Actions` 归一；`armor` 从 `ZombieStats`/护甲道具推导；关卡 spawn 引用闭合检查
- [x] **Step 4: 跑测试确认通过**
- [x] **Step 5: 产出首份覆盖数字** — 记录「1809 关实际引用的植物类型数 / 僵尸类型数」到报告，并写进 `docs/PARITY_MATRIX.md`

### Task 1.4: CMake 接线与运行期切换

**Files:**
- Modify: `native/CMakeLists.txt`（`add_custom_command` 调 `build_content.py` 生成 pack；`content.pack` 作为依赖）
- Modify: `native/src/catalog.cpp`（优先读 pack，失败回落到现有 content JSON 并打警告）
- Modify: `native/src/main.cpp`（`--audit-content` 增加 pack 覆盖摘要）
- Test: `native/tests/catalog_test.cpp`（新增「pack 优先」与「回落」两条）

- [x] **Step 1: 写失败测试** — 临时目录放一个坏 pack，断言回落且 stderr 含 `fallback`；放好 pack 断言 `plants.size()==339`
- [x] **Step 2: 跑测试确认失败**
- [x] **Step 3: 实现接线**
- [x] **Step 4: 全量构建+测试** — `pwsh -File tools/build_native.ps1 -AuditOnly` 期望全绿
- [x] **Step 5: 记录加载耗时** — `--audit-content` 打印 pack 加载 ms，写入基线

### Task 1.5: 世界与关卡数据补全

**Files:**
- Create: `tools/contentc/worlds.py`
- Test: `tools/tests/test_worlds.py`

**Interfaces:**
- `parse_world_data(obb_dir: Path) -> list[WorldRecord]`，字段 `world_id, name, res_group, event_list, level_ids, unlock_from`
- 输出并入 `content.pack` 的 `worlds` 段；与现有 `content/worlds.json` 做 diff 报告

- [x] **Step 1: 写测试** — 断言 46 条世界条目解析；断言每世界 `level_ids` 与 `content/levels/` 的交集/差集被记录
- [x] **Step 2: 确认失败 → 实现 → 确认通过**
- [x] **Step 3: 生成 diff 报告** — `native/generated/world_diff.md`，人读 5 分钟能判断「缺哪些关」

---

## 4. S2 引擎内核 v2（阶段规格）

**目标**：把 `simulation.cpp`（当前 4 张卡硬编码、仅 frontyard）替换为数据驱动内核；任何关卡都能 headless 跑完。

**新增文件结构**（每个文件单一职责，禁止回到单文件巨兽）：
- `native/src/engine/world.hpp/.cpp` — 场地（rows/cols/地形格/特殊格/场地规则钩子）
- `native/src/engine/entity.hpp` — 实体池与稳定 id（植物/僵尸/投射物/阳光/格道具/特效）
- `native/src/engine/director.cpp` — 波次、旗帜、权重抽取、`SpeedVariance`、难度缩放
- `native/src/engine/action_runner.cpp` — `PlantAction` 四种执行器（projectile/sun/explode/special）+ `special` 分发到注册表
- `native/src/engine/registry.hpp` — `PlantBehaviorRegistry` / `ZombieBehaviorRegistry`（字符串 → 函数指针），注册表同时是覆盖矩阵的数据源
- `native/src/engine/projectile.cpp`、`elements.cpp`、`plantfood.cpp`、`fusion.cpp`、`boss.cpp`
- `native/src/engine/replay.hpp/.cpp` — 输入脚本、状态哈希、`--replay`/`--record`

**关键接口**：
- `class World { void step(); bool plant(type,row,col); bool shovel(row,col); bool collect(id); Snapshot snapshot() const; std::uint64_t hash() const; }`
- `using PlantBehavior = void(*)(World&, EntityId, Tick);`  `registry.registerPlant("PlantPeashooter", &peashooterBehavior)`
- 未注册行为 → 回落到框架默认（`PlantPeashooter` 同族复用）并在 `coverage.json` 标 `unwired`

**门禁**：`--simulate --level <id> --script <file>` 对 **26 世界各 1 关**跑通并产出稳定哈希；同一脚本 3 次运行哈希一致；5×9 与 6×10 各 1 关。

---

## 5. S3 战斗内容覆盖（批次规格）

按「行为族」而非按植物逐株推进（235 框架类去重后约 60 族）：

1. **批次 A（直射族）**：Peashooter 20 变体、Gatling、Threepeater、Rotobaga…；含穿透/多行/连发参数。
2. **批次 B（抛射/投掷族）**：Cabbagepult、Kernelpult、Winter Melon、Melon-pult…
3. **批次 C（近战/范围族）**：Snapdragon、Bonk Choy、Chomper、Wasabi Whip…
4. **批次 D（生产/支援族）**：Sunflower 系、Sun Bean、Mint 系（Appeasemint 等 5 个）、Power Lily…
5. **批次 E（陷阱/召唤族）**：Potatomine、Tangle Kelp、Cactus、Squash、Toadstool…
6. **批次 F（僵尸特殊类）**：Jump/Steal/Summon/Gargantuar/Fly/车/恐龙/章鱼/魔术师/治疗 —— 183 类的非基本型。
7. **批次 G（元素）**：火/水/风/电附着、倍率、2 秒冷却、感电、扩散。
8. **批次 H（养料）**：每植物 `PlantFood*` 字段 + 60 投射物型养料。
9. **批次 I（融合）**：85 配方表驱动 + 合成表现。
10. **批次 J（Boss）**：26 个，按 `ZombieClass` 分 5 批（GeneralTreadmill/CakeTank/RomanHealer…）。
11. **批次 K（模式）**：砸罐子 45、生存无尽、小游戏（`minigames.json`）、塔 100、史诗任务 154。

每批 DoD：注册表项 + 单测（伤害/冷却/边界）+ 覆盖矩阵推进 + 至少 1 段录像对照标注。

---

## 6. S4–S8 概要

- **S4 界面**：`native/src/ui/screen.hpp`（`enter/exit/handle/update/draw`，对齐 `game/DESIGN.md`）+ `screen_stack`；屏幕：启动器、主菜单、世界地图（浮空岛轮播/详情面板/钥匙星门）、选卡、战斗 HUD、结算、图鉴（339）、商店（`StoreProductProps`+`MarketLayoutProps`）、花园、融合、设置、存档、新闻。逻辑坐标 1280×720。
- **S5 视听**：OBB 全量资源清单 → 按 `PopAnim` 提取 DragonBones 组；运行时补 mesh/事件帧；特效系统；`SDL3_mixer` 音频总线（music/sfx/ui 三组 + 音量 + 循环点）。
- **S6 存档/经济**：存档 v2（全进度维度）、原子写+备份+迁移；星章三星、钥匙、`CoreLoopRewardsSlotConfig` 奖励、商店货币、花园时钟。
- **S7 交付**：Inno Setup 安装包 + 便携 zip + 图标/版本信息/卸载；macOS Universal 2 `.app` + DMG（实测前不宣称）。
- **S8 联网**：HTTPS 版本/公告（**开启证书校验**）、离线降级与错误态。

---

## 7. 完整复刻的定义（验收口径）

同时满足以下全部，才算「完整复刻」：

1. `docs/PARITY_MATRIX.md` 全部行 `可玩=总量`；`校准` 行标注依据（表驱动=数据校准，录像=行为校准）。
2. 26 世界地图可达；1809 关逐关可开局、可结算、胜负条件正确。
3. 关卡 spawn 引用的每个植物/僵尸类型都有行为实现与可用美术（无占位）。
4. 养料、元素、融合、Boss、砸罐子、生存、小游戏、塔、史诗任务全部可玩。
5. 商店/图鉴/花园/存档/进度闭环；旧 Python 存档可迁移。
6. 中文 UI 全量；无溢出/裁切；1280×720 与 4K 实测。
7. 音频事件覆盖 ≥95%；音乐按世界切换。
8. Windows 安装包在干净机器通过；macOS 在真机通过（否则明确标注未验证）。

---

## 8. 风险与前置

| 风险 | 影响 | 处置 |
| --- | --- | --- |
| 本地 `assets/db` 只有 32/16/24 组模型 | S3 后段与 S5 无法出画面 | S5 前置做 OBB 全量清单与提取器；提取失败的类型进矩阵 `缺资源` 列 |
| 235 植物行为类 + 183 僵尸类工作量 | S3 工期最长 | 按族批量 + 注册表 + 数据驱动参数，禁止逐株写死 |
| 原版数值只能靠表 + 录像推断 | 「校准」不可达 100% | 矩阵区分「表驱动（可达成）」与「录像校准（尽力）」，不虚报 |
| macOS 无可用机器 | S7 macOS 项无法验证 | 交付脚本 + 明确标注；不写「已通过」 |
| 联网服务（账号/云存档/活动）不可复刻 | S8 部分功能 | 以本地配置模拟 + 显式「离线」状态，不伪造在线 |
| 单轮上下文有限 | 长任务漂移 | 每阶段结束写 `docs/NATIVE_PROGRESS.md` + 矩阵 + 基线，下一轮从文档恢复 |
