# PvZ2 SHUTTLE 原生复刻：系统完成度与缺陷总账（数据 460.9 / 核心库 460.11）

> 只看「还剩什么、先做什么」请直接读 [docs/PROGRESS.md](PROGRESS.md)（2026-11-25 的 P0/P1/P2 清单与完成度总表）。

> 生成时间：2026-11-20 22:35（Asia/Shanghai）；22:40 按 t18 交付（养料编译）与提取进度更新数字
> 基线（2026-11-25）：数据包已对齐 460.9，S0–S6 完成，门禁 audit 27 / Python 469 / desktop 36 静树 EXIT=0；剩余工作见 docs/PROGRESS.md。
> 口径：**只写能当场复现的数字**。凡是"感觉上差不多"的判断，一律标 `推断` 并给依据。
> 复现命令见文末附录。本文所有行号对应当前工作树（未 commit）。

---

## 0. 一句话结论

**"能跑"已经做到，"像原版"还差三块硬骨头：① 关卡玩法变体（Boss/砸罐子/矿车/潮汐/传送门等原版模块）② UI 与进度体系（菜单→世界地图→选卡→图鉴/商店/花园→结算）③ 音频与表现打磨。**
数据层接近完成（339 植物 / 1127 僵尸 / 1809 关 / 85 融合全部编译），但**玩法层只实现了"通用草坪战斗"这一种**，1809 关里有 71 关 Boss、45 关砸罐子、10 关矿车、45 个小游戏目前都按普通关卡跑——能跑完，但不是原版那一关。

---

## 1. 总览（按玩家可见面加权）

| # | 系统 | 完成度 | 一句话现状 | 主要缺口 |
|---|------|--------|-----------|---------|
| 1 | 内容数据编译 | **90%** | 339/1127/1809/85/26 全部编译进 `content.pack`，重复 id 与悬空引用已钉死 | Boss 阶段表、养料表编译中；元素表原版为空（须 authored）；46 stage/368 关未映射 |
| 2 | 模拟内核 | **70%** | 60 Hz 定步、种子可溯源、32 场景双跑同哈希；啃食/子弹/推车/波次/阳光/冷却/卡组/棋盘尺寸都通 | 关卡模块全未实现（`extra` 解析为 0）、无元素/养料/融合/Boss、关卡内植物等级成长未接 |
| 3 | 行为族 | **55%** | 植物 11 族 339/339 判定、僵尸 6 族 183/183 判定，族函数全部落地 | 26 处兜底常量（无包内证据）、`support` 空实现、37 株无 Actions、刺/咬/大砸为简化模型 |
| 4 | 元素 / 养料 / 融合 / Boss | **25%** | 数据侧全部编译：融合 85 对、养料 293 行（147 时长 / 185 次数 / 6 动作）、Boss 50 个 / 155 可上场阶段；运行时仍然为零 | 元素须纯 authored；四模块运行时未写；无 UI |
| 5 | 战斗表现 | **30%** | DragonBones 5.5 运行时 + PopAnim→DragonBones 转换器；battle_view 可交互截图 | 内容植物 111/147 有旧美术、7 株走新提取、**29 株缺**；僵尸新美术 0；无粒子/阴影/死亡动画 |
| 6 | 音频 | **0%** | `assets/audio` 有 67 个音频文件 | **C++ 侧没有任何音频子系统**（无 SDL_audio/Mixer 引用） |
| 7 | UI 与流程 | **10%** | 启动图 + 战斗 HUD（中文） | 无主菜单/世界地图/选卡/图鉴/商店/花园/设置/结算/暂停菜单/关卡介绍 |
| 8 | 进度与存档 | **30%** | 只读迁移 Python 存档；`native/src/progress.{hpp,cpp}` 已进 CMake 并通过 `progress` 用例（星章表 1809 关 / 5427 目标 + 原子存档 + 不回退合并 + 非 ASCII 路径） | 未接 UI/世界地图/商店；4 类星章目标引擎无计数器；钥匙/解锁未写档 |
| 9 | 关卡变体与特殊地形 | **10%** | 1809 关都能 headless 跑完 | Boss 71 关无 Boss、砸罐子 45 关按普通关跑、矿车 10 关无矿车、45 小游戏/无尽/传送门/潮汐/氧气全无 |
| 10 | 平台与发布 | **20%** | Windows x64 可构建可跑 | 无安装程序、无便携包；macOS 未构建未验证 |
| 11 | 工具链与门禁 | **85%** | `check_all`（audit+desktop 双配置）+ 三份基线 + 32 场景冒烟 + 263 Python 例 + 13/18 C++ 例 | 无性能/内存预算门禁、无 CI、美术覆盖率未进门禁 |
| 12 | 联网与服务 | **5%** | 仅 Python 版有版本查询 | C++ 侧完全没有 |

**加权（按玩家可见面，权重见 §3.12）：约 35%。** 这不是"完成 35% 的工作量"，而是"玩家能看到的原版体验覆盖 35%"——数据与内核的地基比这个数字高。

---

## 2. 分系统详述

### 2.1 内容数据编译 — 90%

已编译并进 `native/generated/content.pack`（1.44 MB，SHA-256 `DF2EE1EF…4AFF`，两次构建字节相同）：

| 来源 | 数量 | 落点 |
|------|------|------|
| `pkg_2074_PlantType` | 339 | `plants[]`（235 个 distinct framework） |
| `pkg_2115_ZombieType` | 1127（1125 唯一 id） | `zombies[]`；重复 `heavy_shield` / `kongfu_gargantuar` 按 class 保留 |
| `pkg_2073_PlantPropertySheet` | 398 对象 / 668 条 Actions | `plants[].actions[]`（projectile 410 / special 200 / explode 33 / sun 16 / plantfood 6 / manual 1 / 无类型 2） |
| `pkg_2112_ZombiePropertySheet` | 932 对象 / 717 条 action 引用 | `zombies[].actionRefs[]` |
| `content/levels` | 1809 | 关卡 JSON（1646 原始 + 163 合成） |
| `content/fusions.json` ↔ `pkg_2083` | **85 对**（48 个配方键，两侧零差集） | `fusions_from_pack.json` |
| `content/worlds.json` ↔ `pkg_2107` | 26 ↔ 46（匹配 22） | `world_diff.md` |
| `pkg_2107` 棋盘尺寸 | 26 世界（beach/modern 6×9） | `board_sizes.json` |
| `pkg_2115` ZombieClass | 183 | `zombie_classes.json` + 族表（walk 129 / gargantuar 29 / summon 10 / fly 8 / jump 6 / steal 1） |

**缺陷**
- **C1（high）** 46 个 stage / 368 关未映射（RiftStage 37、ChildStage 30、AprilFoolsStage 28 等周年庆/裂隙/深渊）——不影响 26 世界，但"完整复刻"目标里这些关是空的。
- **C2（high）** 包内 295 株植物 / 1107 个僵尸行**没有任何客户端 id**（`vamporcini`、`bombardmint`、`seashroom`、`plantern`、`camel_*`、`*_veteran`…）。真正目标是 339/1127，客户端只有 147/55，缺口要靠"补全名册"（美术 + 定义）填。
- **C3（medium）** 客户端 103 株植物在 pack 里不存在（`twinsunflower`、`gatling`、`iris`、`snowlotus`…）：有的是换皮复用（`rosemary→spearmint`），有的确实没数据 → 需人工裁决"保留/合并/删除"。
- **C4（medium）** `content/bosses.json` 26 条 HP 是 8000→13200 等差数列、phases 三档全同，**与 pack 的 258 阶段真实 HP 无一相符**（S5 正在用 `bosses_from_pack.json` 替换）。

### 2.2 模拟内核 — 70%

已实现（`native/src/engine/`，audit 12 例 / desktop 17 例覆盖）：

- 60 Hz 定步 `World::advance(dt)`，拒绝 NaN/负/>86400；`advance(90)` 与 180×`advance(0.5)` 同 tick 同哈希。
- 波次导演 `Director`：`clock += delay` 展平、flag 波 1 s 内铺开、非 flag 0.3 s 间隔、重僵尸 +0.5 s、`stable_sort` 固定顺序。
- 刷怪 / 啃食（窗口 `[x-1.15, x+0.35]`）/ 跳跃（`tryVault` 在啃食前，落点 `centre-0.55`）/ 飞行不吃 / 召唤走 `pendingSpawns_` 队列（避免 range-for 悬垂）。
- 子弹（5.2 列/秒、命中 ±0.25、相邻行溅射 0.5、减速、穿透）、爆炸（半径/矩形触发/自毁）。
- 小推车（触发 -0.25、判负 = `x < -0.7` 且车已用）、漏怪计数 `leaked_`、推车击杀独立计数。
- 阳光（首次 4.5 s、之后 24 s、25 点、600 tick 过期）、冷却（pack `PacketCooldown`）、卡组校验（`not-in-deck`）、上限（`kMaxPlants` 等 4 项）。
- 棋盘尺寸（`board_sizes.json` 覆盖 + `extra.board_rows` 优先）、可见行/列正确落到 `snapshot()`。
- 状态哈希 FNV-1a 64，含 tick/阳光/波次/各实体字段/计时器，用于跨构建复现（默认目录 vs 隔离目录哈希一致）。

**缺陷**
- **C5（blocker，对"完整复刻"而言）** `level.extra` 被 `catalog.cpp:143-148` 解析进 `LevelDefinition::extra`，但**引擎侧无人消费**（`grep extra native/src/engine` 只命中 `kGargantuarSmashExtraSeconds` 等无关名）：
  - `extra.boss` 71 关（`boss_zombie: zomboss` 68 / `gargantuar` 3）→ **Boss 根本不出场**；
  - `extra.vasebreaker` 45 关 → 按普通关跑；
  - `extra.minecarts`/`rail` 10 关 → 无矿车；
  - `extra.night` 1809 关全有值 → 夜晚逻辑（阳光/墓碑/蘑菇）未接；
  - `extra.special` 45 关（小游戏）→ 未接。
- **C6（high）** 关卡内植物等级成长（`pkg_2069_PlantLevelStats` 325 条）未接，所有植物按 1 级数值。
- **C7（high，部分收口）** 元素运行时为零（且原版无此机制，见 §2.13）；**养料与融合引擎已落地**（§2.18，含回放 op，C41 已修），但养料无掉落货币（C42）、桌面无交互；Boss 运行时在 S5.8 进行中。
- **C8（medium）** 无"关卡开始"事件与横幅、无旗帜波提示、无"最后一波"判定文案；`flags` 只用于波次铺开节奏。
- **C9（medium）** legacy `simulation.cpp`（292 行）仍被 `--simulate` 使用，与 `engine` 数值分叉（天空阳光 8 s vs 4.5 s、推车线 -0.25 vs -0.7）—— 两套内核同时存在是技术债（M7）。
- **C10（low）** `--run-level` 无事件导出，回放脚本之外看不到 `action_unknown`/`wave_spawn_rejected` 等诊断。

### 2.3 行为族 — 55%

- 植物 11 族（`shoot/lob/produce/wall/instant/mine/chomp/fume/boomerang/support/spike`），339/339 判定，其中 26 处为 tuning 兜底常量（每处带 `// fallback: tuning constant, no pack evidence`）。
- 僵尸 6 族（`walk/jump/steal/summon/gargantuar/fly`），183/183 判定（13 条人工覆盖有书面依据）。
- 优先级：**content `behavior` > pack `ZombieClass` 表 > `walk`**；植物 **pack 槽位 > content JSON > tuning**。

**缺陷**
- **C11（high）** `support` 族空实现（34 株判定到 support，其中 10 株客户端 support 植物无任何主动行为）。
- **C12（medium）** 37 株 pack 植物 `Actions` 为空 → 只会站着（`noActions` 已在 `pack_roster_report.md` 列出）。
- **C13（medium）** `spike` 是"每次开火全额伤害"的简化；`chomp` 1.42 列、`fume` 5 列/2.425 s 等取自包内单点，未做逐株校准。
- **C14（medium）** `gargantuar` 只有"1.2 列砸一次"，无举锤动画/范围推平/半血扔小鬼。

### 2.4 元素 / 养料 / 融合 / Boss — 25%（数据侧完成，运行时为零）

| 子项 | 数据 | 运行时 | 结论 |
|------|------|--------|------|
| 元素 | **原版无表，且这不是"缺数据"而是"无此机制"**：`ElementReactionModuleProperties` 21 条记录 objdata 全为 `{}`；`pkg_2073` 零 element 字段；1809 关 `extra` 零 element 键 | 无 | 作为**本客户端自创的可选层**（`source:"authored"`、`WorldOptions::elements` 默认关），**不计入原版复刻完成度** |
| 养料 | 已编译 `plantfood_from_pack.json`（293 行）：`PlantFoodDurationSeconds` 147 株、`PlantFoodPlayCount` 185 株（可达 172 株）、`Type=="plantfood"` 仅 **6 条**（sungun / dartichoke / draftodil1 / homingthistle / magnetfruit / rheumnobile；Draftodil 缺三个冷却字段写 null 不丢行） | 无（`action_runner` 只走冷却） | 6 株可数据驱动到弹道层，其余 333 株须 authored |
| 融合 | **85 对**已编译，与 content 零差集 | 无 | 引擎侧只差 `tryMerge` |
| Boss | 已编译 `bosses_from_pack.json`（700 KB）：**50 个 boss**、75 条 battle 放置、阶段口径三种——occurrence 求和 **258** / alias 去重 227 / **可上场 155**（被放置 mech 之和，引擎取这个）；38 个 ActionDefinition（Fire 76 条）；1 条悬空 mech（`zombossmech_egypt_rift`）、24 个完整 3 阶段表但无任何关卡放置 | 无 | 数据最富，运行时为零 |

**缺陷**
- **C15（blocker）** Boss 关（71）无 Boss 出场；`content/bosses.json` 的 HP 是合成的（等差 8000→13200、phase 恒 3），与 pack 差 2–9 倍（egypt 18500 vs 8200、dark 27000 vs 9000、chinesegarden 97000 vs 11000），**不能**用于运行时；已由 `bosses_from_pack.json` 取代。
- **C16（high）** 无养料系统 → 原版最核心的"一次性爆发"玩法缺失。
- **C17（medium，且非原版项）** 无元素反应。但三份证据（`ElementReactionModuleProperties` 全表 objdata 为 `{}`、`PlantPropertySheet` 零 element 字段、1809 关 `extra` 零 element 键）表明**原版没有元素机制**；Python 基线的 `elements.py`（水/火/冰/雷/风）是自创。因此这一项**不计入原版复刻**，只作为可选的自创玩法层。
- **C18（medium）** 融合无运行时（数据 85 对已就绪，58 对的 ingredient 是 pack-only id，需先决定是否存在于 content）。

### 2.5 战斗表现 — 30%

- `dragonbones.cpp`（21.7 KB）：5.5 骨架平移/旋转/缩放、缓动、蒙皮、affine 贴图、动画通道叠加（不是替换）。
- `tools/obb_art.py`：PopAnim（magic `0xBAF01954` v6）→ DragonBones 转换，单 base 可复现（四文件 sha 稳定）；4×4 子块颜色精度（alpha 精确）。
- `--art-audit`（t14）：content 147 株 → **111 旧美术 / 7 新提取 / 29 缺**；pack 339 株 → 106 新提取 / 233 缺；僵尸 0（提取未到 ZOMBIE 批）。

**缺陷**
- **C19（high）** 29 株内容植物无任何美术（含 deck 引用 top3：`potatochip` 117 次、`begonia` 114 次、`missiletoast` 110 次）。
- **C20（high）** 147 株里只有 31 套独立模型（80 株换皮，`GatlingPeaPLANT` 被 11 株共用）→ 独立形象覆盖 31/147≈21%。
- **C21（medium）** 提取到 218/1087 base（`pending 867`，仍在 PLANT 批），2 个 base 因 **ASTC 块压缩（fmt 161/162，约 95 个子组）** 失败——要补需另写 ASTC 解码器。
- **C22（medium）** 无死亡淡出以外的表现：无粒子、无阴影（`ShadowOffset` 未用）、无受击闪白、无种植/铲除动画、无旗帜波特效。

### 2.6 音频 — 0%

- `PvZ2SHUTTLE/assets/audio` 有 67 个文件（Python 版在用）。
- **C23（blocker）** `native/src` 里没有任何 `SDL_OpenAudio` / `SDL_AudioStream` / Mixer 引用 → 原生版**完全无声**。这是玩家第一秒就能察觉的缺口。

### 2.7 UI 与流程 — 10%

现有：`launcher.cpp`（启动图 letterbox）+ `battle_view.cpp`（战斗 HUD：阳光/波次/状态/时间/tick、卡槽高亮与冷却、缺美术计数）。

**C24（blocker）** 缺整套流程界面：主菜单、世界地图（浮空岛 carousel + "这个世界包含"面板）、选卡（seedchooser）、关卡介绍、暂停/结算、图鉴（almanac）、商店（585 商品）、花园、设置、模式选择（生存/小游戏/砸罐子）。
Python 版对应 17 个 screen 文件（`worldmap.py` 67 KB、`shop.py` 36 KB、`level_screen.py` 50 KB…），是现成的功能基线，但**不能直接移植**（PyGame 绘制与 C++ 即时模式渲染不同）。

### 2.8 进度与存档 — 30%（模型层已编译验证，未接 UI）

- `save.hpp` 只有：`migratePythonSave`（只读）、`readNativeSave`、`importPythonSave`（原子写、原件与备份都不覆盖）。
- **C25（high）** 无原生进度模型：星章/钥匙/世界解锁/关卡三星/奖励领取/商店持有/花园植物 全都没有落盘，也没有对应的运行时状态。
- **C26（medium）** 无存档版本迁移策略（原生 v1 之后怎么升）。

### 2.9 关卡变体与特殊地形 — 10%

| 变体 | 原版规模 | C++ 现状 |
|------|---------|---------|
| Boss 关 | 71 关（68 zomboss） | 无 Boss 出场 |
| 砸罐子 | 原版 47 / 客户端 45（缺 `pirate_41`、`plantagenet_18`） | 按普通关跑 |
| 小游戏 | 45 个 | 全无 |
| 矿车 / 铁轨 | 原版 rail 模块 185 条（功能/装饰未分辨），客户端标记仅 10 关、交集 3 | 无矿车（t28 判别中） |
| 生存/无尽 | content 有模式数据 | 无 |
| 传送门 / 潮汐 / 氧气 / 洋流 / 恐龙 / 屏风 / 瓷砖 | 分布在 beach/sky/dino/mausoleum 等 | 全无 |
| 夜晚草坪 | 1809 关都有 `extra.night` | 无墓碑/夜间阳光逻辑 |

**C27（blocker）** 上述模块是"原版那一关"的核心差异，缺了它们，1809 关只剩"换皮的同一种战斗"。

### 2.10 平台与发布 — 20%

- Windows x64：`build
ative-desktop\Release\PvZ2SHUTTLE.exe` 可跑（desktop 17/17）。
- **C28（high）** 无安装程序、无便携包；依赖 DLL 靠 CMake 运行时目录，未做发布打包脚本。
- **C29（high）** macOS 11+ Universal 2 未构建、未验证（设计文档要求）。
- **C30（medium）** 字体只加载 `ui/font_zh.ttc`，无非中文回退与 DPI 缩放策略（非 16:9 letterbox 已做）。

### 2.11 工具链与门禁 — 85%

- `tools/check_all.ps1`：content 编译检查 → 构建+CTest → Python 单测 → 矩阵 → 世界差异 → 引擎冒烟（32 场景），失败即 `[fail]` + 退出码 1；基线比较改成"先比后写"（`Sync-Baseline`），不再自愈。
- `tools/parity_report.py`：矩阵 12 行（含新增「僵尸 class 族 183/183」「植物行为族 339/339」「融合 85/85」）。
- `tools/engine_smoke.py`：26 世界各取最低关 + 5 定点 + `beach_23` 胜利局 = 32 场景，双跑同哈希；记账恒等式 `spawned == killed+mowerKills+leaked`。
- 测试：C++ audit 12 例 / desktop 17 例、Python **172 例**、`content_test` 断言 pack 数字。

**缺陷**
- **C31（medium）** 无性能门禁（冷启动 ≤1.5 s 是人工量的，未进门禁）与内存预算门禁。
- **C32（medium）** 无 CI（本地 Windows-only，macOS 完全没跑过）。
- **C33（low）** 美术覆盖率（`--art-audit`）尚未进门禁，缺美术只能人肉看报告。

### 2.12 联网与服务 — 5%

- C++ 侧零联网；Python 版只有版本查询（`cz/czok.json`）且证书校验关闭。
- **C34（low）** 原版的公告/活动/云存档/内购在原版是服务端驱动；本项目定位是单机复刻，建议明确"不实现联网"并写进 README（当前含糊）。

---

### 2.14 弹道表（2026-11-20 编译，2026-11-21 11:12 接线完成 = t26）

`native/generated/projectiles_from_pack.json`（860 KB）：602 条 = 571 canonical + 31 仅存在于关卡包内嵌副本；71 个 objclass；`variants` 记录 9 条同 id 差异副本。弹道判定 straight 374 / arc 118 / drop 59 / static 42 / unknown 9。

两条对"像不像"直接相关的事实：
- `tuning::kShotHitRadius = 0.25` **不是拍出来的**，恰好等于 CollisionRect 主峰（30×30 → 15 px → 15/60），358/596 条正好 0.25。
- `tuning::kShotSpeedColsPerSec = 5.2`（312 px/s）**不在任何主峰上**；直线弹主峰 333 px/s（5.55 cols/s，142 条）。引擎当前所有子弹都偏慢约 6.7%。

引擎侧（`native/src/engine/projectile_table.*` + `spawnShot`/`stepShots`）：按 `Action.projectile` 的 RTID 名查表，命中盒/溅射/弹道类型/速度全取表值，未命中保留 5.2/0.25 并记 `projectile_unknown`（按 id 去重）。接线后 32 场景冒烟只有 2 条变：`frontyard_1 script` `0xac1156c1ef5ccf69 → 0x6286cea661ecbfee`、`beach_23 win` `0xde03536c990dee92 → 0x2f8ac180ac294f8c`（1538 → 1534 tick）。**593/602 接线**，9 条 `trajectory=unknown` 仍走直线缺省。

四个如实记录的边界（`docs/reviews/2026-11-20-projectile-wiring.md` §6）：`variants[]` 只有 `differingKeys` 无数值；`pierce` 41 条里只有 2 条给 `maxTargetHits`，其余只有概率衰减 → 不臆造上限；`CabbageDefault` 的 140 s 飞时不成立（C45）；离群命中盒 `RenaiTileLeft/Right`(166.7)、`ZomboniProjectile`(16.7) 无任何 action 引用，原样保留。
## 2.13 口径裁决：元素系统不属原版

三份独立证据：`ElementReactionModuleProperties` 全表 21 条记录 `objdata` 均为 `{}`（零字段）；`PlantPropertySheet` 398 个对象里键名含 `element` 的字段 0 个；1809 个关卡 JSON 的 `extra` 里 element 相关键 0 个。结论：**原版没有元素机制**，Python 版本的水/火/冰/雷/风 + 反应表是自创。

处理：作为 `authored` 可选层（`native/generated/elements.json` + `source:"authored"` + 默认关闭的 `WorldOptions::elements`），**不计入"原版复刻"完成度**，只在文档里标为"本客户端独有玩法"。

- **C35（high，内容数据缺陷，2026-11-20 新发现）** `content/stars.json` 里 **67 条 `kill` 星章要求的击杀数超过该关波次总僵尸数**（1702 条 kill 目标中 1635 可达、67 不可达）。典型：`beach_23` 只生成 1 只僵尸却要求"击杀 10 只"，因此该关最高只能 2 星；`beach` 世界独占 28 条，`frontyard` 12 条。已在 `native/tests/progress_test.cpp::testStarGoalsReachable` 用断言钉住（67 / 首个 `beach_2`），改内容时必须同步改测试。

- **C36（high，已按对象级证据定量）** 铁轨（**2026-11-24 已闭合**：客户端现标 rail **192 关**、minecarts **190 关**，与原版 functional 192 对齐）：原版 **204 关**带 rail 数据，其中 **functional 192**（`RailcartProperties.Railcarts` 有 Column/Row，或 `DangerRoomRailcartDesigner` 有 `BaseRailcartCount`/`Layouts`）、decorative 6（只有 `Rails` 路径点、全文无 `*Cart*`：`egypt_46`/`frontyard_143`/`frontyard_98`/`lunarrainbowmarket_93`/`muji_27`/`pirate_67`）、unknown 6。客户端只标 **10 关**：**7 关误标**（`kongfu_5/10/15/20/25/30/40`，原版既无 rail 模块也无 rail 对象，证据在 `content_fix_candidates.json.minecarts_remove_evidence`，逐关带 pkg 文件 + stage + LevelNumber）、**3 关正确**（`cowboy_6`/`cowboy_12`/`kongfu_35`）、**189 关真矿车漏标**。
- **C37（medium，口径已复核修正）** 砸罐子（**2026-11-24 已闭合**：客户端现 47 关）：原版 `VaseBreaker` 模块 **47 关**，此前客户端 45 关，缺的两关是 `pirate_41`（= 原版 `PirateBossStage` #26，同时带 `ZombossBattle` + `VaseBreakerArcade`，是** Boss/砸罐子混合关**）与 `plantagenet_18`（= 原版 `PlantagenetDaylightDMGStage` #19，纯砸罐子关）。注意 t28 报告里"pirate_41 玩法标签整体错位"的说法**不成立**：该关 `boss:true` 是对的，缺的只是 `vasebreaker` 标记；`plantagenet_18` 也没有 boss 标记。
- **C40（low）** 10 个 SHUTTLE 美术 base 因 ASTC（fmt161 5x5 / fmt162 6x6）未解出，已记入 `index.json.failures[]`。
- **C39（low）** `content/zombies.json` 16 条带甲僵尸里 6 条与 pack 护甲表桥不上（HP 无误，命名/语义不可溯源）。
- **C38（low）** 4 关原版无 Modules（`egypt_50`、`frontyard_86/87/88`）；13 关 `night` 标记与 stage 名冲突（`carnival_30`、`dark_52..57` 等）——实现夜间逻辑时应以原版场景参数为准。


### 2.15 进度与星章（2026-11-20 22:50 更新）

`native/src/progress.hpp` + `progress.cpp` 已落地并进 CMake（`pvz_progress`，链 `pvz_catalog`/`pvz_engine`），`native/tests/progress_test.cpp` 在 audit 配置下 **13/13 全绿**。

能做的：星章表解析（1809 关 / 5427 条目标，7 类 `beat/mowers/kill/sun_used/sun_produced/plants_lost/time`，unknown 0）、对局结束后判定、存档原子写（临时文件 + rename）、星章只增不减、`bestTick` 取最快、损坏存档报错不覆盖、非 ASCII 路径可用。

还没做（属 S6）：把 `recordAttempt` 接到 CLI/桌面胜利回调、世界地图/钥匙/商店货币的读写、版本迁移策略。元素层 `native/generated/elements.json`（5 元素 / 10 反应，`source:"authored"`）已由 mapper 编译完成，运行时仍未接（t23 只做数据）。
### 2.16 护甲（2026-11-20 23:00 数据层；2026-11-23 08:10 接线完成 = t29）

`tools/contentc/armors.py` → `native/generated/armors_from_pack.json`（102 条护甲 = `pkg_0002` 原表 97 + 关卡内嵌 9 行/5 个 id 只在内嵌副本存在；能定 HP 101，1 条无 `BaseHealth`；`2147483647` 哨兵 4 条保留并标记）。字段映射与任务书猜的完全不同：`hitpoints←BaseHealth`、`droppable←ArmorFlags` 含 `droppable`、`art←ArmorLayers` 骨骼层名，`breaksInto` 原版无字段（`null`，链顺序由 `zombies[].armorIds` 表达）。

- 僵尸侧：1127 类型里挂甲 **276**、无甲 804、`props` 缺失 47（标 unknown，不算无甲）；一僵尸多甲 16（0:851 / 1:260 / 2:9 / 3:5 / 5:2）。
- 悬空护甲 3 个 id / 13 处引用（`InvincibleArmor` 11、`HideLayer` 1、`AngerManagement` 1）；未被任何僵尸引用 14。
- 与 `content/zombies.json`：16 条带甲僵尸里 **精确命中 8**、世界+甲型推断 2（`garden_cone→chinesegarden_armor1`、`garden_bucket→chinesegarden_armor2`）、**桥不上 6**（其中 3 条在 pack 有 HP、3 条没有）；**HP 差 0 条** → 客户端数值本来就对，缺的是 flags 与链顺序。
- 引擎替换点（**2026-11-23 已接**）：`native/src/engine/armor.{hpp,cpp}` 成为权威表 —— 层顺序按 `zombies[].armorIds`、`invincible` 层不进血池（命中走 `armor_blocked` 事件并保住本体）、`passdamage` 穿透、`droppable` 掉落、`absorboverflow` 吞溢出；`native/src/engine/world.cpp` 的 `armorHp` 改由该表建池；`native/src/battle_view.cpp:297` 原来的 `buckethead ? "Bucket" : "Cone"` 改为按 `armors[].art.armorLayer` 取骨骼名。
- **接线时踩到并修掉的真 bug（重要）**：20 个 content 僵尸 id 在 sheet `zombies[]` 里也有同名行，其中 6 行带甲（`cowboy → CowboyHatDefault`）。第一版实现"先查桥、空了再按 id 查 sheet 行"，导致 content 僵尸读到 pack 行，冒烟出现 `world cowboy` / `world muji` 两条哈希变化。修法是**按 id 空间分流**：content 僵尸只走 content + 桥，pack-only 才查 sheet 行（`native/src/engine/world.cpp:825-827`）。修后冒烟 **0/32 变化**，并加回归用例 `native/tests/armor_test.cpp::testContentZombieKeepsContentArmor`（`cowboy` 必须无甲且 `armorHp == 0`、`conehead` 必须保留 `ConeDefault` 370）。
- 缺陷：**C39（low）** `content/zombies.json` 有 6 条护甲与 pack 桥不上（数值正确但语义/命名不可溯源）；`pkg_0002` 有 3 条悬空 + 14 条未引用属原表自身状态，按原样保留。13 条无 `ArmorLayers` 的护甲拿不到骨骼名，视图侧走缺省并计数（不臆造层名）。

**关卡身份键（复核 t22/t28 时踩到的坑，2026-11-20 23:10 再次更正）**：`work/obb_packages/pkg_*_LevelDefinition.json` 里每个文件通常只有 **1 个 `LevelDefinition` 对象且没有 alias**，所以不能用 `alias` 或 `"pirate_41"` 字面量去原表搜索（会 0 命中，从而误判"原版没有这关"）。但**`StageModule + LevelNumber` 也不唯一**：1809 个原版文件只有 **1385 个不同组合**，**246 个组合重复、多出 424 个文件**（`(DarkStage,1)` 有 20 个 package、(DinoStage,1) 14 个、(BeachStage,1) 12 个）；客户端自己就有反例：`kongfu_30` = `pkg_1415 / KongfuStage / LevelNumber 5`，与 `kongfu_5` = `pkg_1390 / KongfuStage / 5` 同 stage 同号却是两关。**正确口径：以客户端 `extra.package`（如 `pkg_1415`）为主键关联原表，`stage + LevelNumber` 只用于交叉核对。**

**Boss 关口径复核（2026-11-20 23:05）**：原版 1809 关里有 `ZombossBattle` 模块的恰 **71 关**，与客户端 `extra.boss` 的 71 关**数量一致**；但用 `*BossStage` 命名只覆盖 **18 关**——即大多数 Boss 战嵌在普通 stage 里（如 `PirateBossStage` 只 1 关，`EgyptNightsBossStage` 2 关）。所以统计 Boss 关必须按 `ZombossBattle` 模块，不能按 stage 名。
### 2.17 OBB 美术提取进度（2026-11-20 23:05 快照）

`tools/obb_art.py` 全量批在跑（1087 个可提取 base）：**ok=543 / failed=10 / pending=534**，PLANT 374 个已全部跑完、ZOMBIE 已落盘 179。产物 `PvZ2SHUTTLE/assets/db/shuttle/<base>/`（skeleton/atlas/texture/meta 四件套）+ 实时索引 `index.json`（每 base 原子重写：`items/counts/failures/progress`）。

- **popAnim 连接率已修**：pack 的命名是「类前缀 + 类型名」，僵尸会出现**重复前缀**（`ZOMBIEAFBALDGROUP → POPANIM_ZOMBIE_ZOMBIE_AF_BALD`）；原先只在"未带前缀"时补前缀，导致僵尸全为 null。加"已带前缀则再叠一层"候选并 `--reindex`（只重算 index，不重解包）后：**ZOMBIE 179 项中 115 连上、PLANT 364 项中 277 连上**；余下的是 pack 内确实没有同名非生物资源（tile/mower/effect/场景），按设计留 `popAnim: null`。
- **缺陷 C40（low）**：10 个 base 因 PTX 用 ASTC 块压缩（fmt 162 = ASTC 6x6、fmt 161 = ASTC 5x5）未能解出：`PLANTELECTRICPEEL`、`PLANTFIRESHROOM`、`PLANTICESHROOM`、`PLANTIMPATIENSSHOOTER`、`PLANTLEMON`、`PLANTMANGOSTEEN`、`PLANTNARCISSUSSHOOTER`、`PLANTPINKSTARFRUIT`、`PLANTPRIMALPEASHOOTER`、`PLANTSTALLIADAHLIA`。它们全部落在 `index.json` 的 `failures[]` 带原因串，不静默丢；补法是要么写 ASTC 解码器，要么接受这 10 株走缺省美术。
- 性能：PTX 解码 numpy 化 + atlas 矩形匹配去掉每图重建积分图后，单 base 7.0 s → 4.05 s，2048²/88 图的大件 50.75 s → 13.55 s（输出 sha256 与旧实现全等）。

### 2.18 养料 + 融合运行时（2026-11-21 10:20，S5.7 = t24 + 队长补线）

**数据**（都已在 `native/generated/`）：`plantfood_from_pack.json` 293 行（`withDuration` 147、`withPlayCount` 185、`withAction` 恰 6 株：sungun / dartichoke / draftodil1 / homingthistle / magnetfruit / rheumnobile，`missingEffect` 333）；`fusions_from_pack.json` 85 对（配方键 48 与 `content/fusions.json` 完全一致，其余 37 对至少一侧是 pack-only id）。

**引擎**：`native/src/engine/plantfood.{hpp,cpp}`、`fusion.{hpp,cpp}`，`WorldOptions{plantfood=true, fusion=true, elements=false}`。有 `plantfood` action 槽的 6 株走 `action_runner`（唯一发射路径，SpawnOffset/弹道/冷却都不复制），其余按 `durationSeconds` 开窗口（peashooter 2 s = 120 tick，窗口内伤害 ×2、攻速 ×2）。融合按 Chebyshev 距离 1（含斜邻）匹配配方，消耗两株、结果落在第一株格子。`hash()` 只在**真正生效**时追加 `f<ticks,armed>` 与 `G<fusions>`，所以默认开启不会让既有 29 个冒烟场景漂移（`beach_23` 仍 `0xde03536c990dee92`）。

**本节的缺陷与更正**：

- **C41（high，已修，验证待 t25 收尾）** 养料与融合在引擎里存在，但**没有任何玩家可达路径**：`replay.cpp` 的 op 只有 `plant/shovel/collect/spawn`，桌面视图没有喂料/融合交互，CLI 也没有参数。也就是说 `s5_runtime_test` 能过、游戏里摸不到——这正是"单测直调掩盖不可达"的典型。队长已补 `{"op":"feed","id":N}` 与 `{"op":"fuse","id":N,"id2":M}`（缺 id 在 parse 期报错，拒绝发 `input_rejected`，`summarize` 增加 `"fusions"`），新增 `native/tests/replay_s5_test.cpp`（5 段，含 `peashooter + iceburg → fused_snowpea` 与同脚本同哈希）。**桌面交互仍缺**，归 S6 的界面任务。
- **C42（medium，开放）** 养料没有货币/掉落：`feed` 可无限调用，原版里养料是掉落资源。属 S7/S8。
- **C43（low，报告更正）** t24 报告里"融合扣阳光并允许负余额"的表述与现树不符：`tryFuse` 不扣费，配方表也没有 cost 字段（`cost` 只写进 `fusion` 事件供显示）。以现树为准。

### 2.19 Boss 运行时（2026-11-21 10:56，S5.8 = t25）

原版数据 → 引擎 → CLI 三层都通了，这是"S5 里最不像 demo 的一块"。

**数据**：`native/generated/bosses_from_pack.json`（700,001 B）—— 50 个 boss、75 条 battle 放置、
**可上场 155 个阶段**（另两种口径 occurrence 258 / alias 去重 227 只写在报告里，引擎不用）。
`zombossmech_egypt_rift` 是 pack 悬空引用（`stages` 为空），`BossDefinition::usable()` 直接过滤。

**引擎**（`native/src/engine/boss.{hpp,cpp}` + `World`）：
- `WorldOptions::boss` 默认开；构造期解析表，解析不到且关卡带标记 → `++bossUnavailable_` + `boss_unavailable` 事件。
- 最后一波交给 spawner 后 `trySpawnBoss()`，按 `spawn.gridX/gridY` 进场；`tickBoss` 先吃 stun 再吃 idle，
  idle 归零按该阶 `FireMinColumn`/`FireMaxColumn`/`FireRowRange` 烧植物（`kBossFireDamage = 1800`，
  带 `// fallback: tuning constant, no pack evidence` —— 表里只有列窗口与火箭速度，没有伤害数字）。
- `damageBoss` 一次只升一阶，末阶发 `boss_died`；`hash()` 只对 boss 追加 `B<…>`，**无 boss 的世界哈希逐字节不变**
  —— 这也是 smoke 32 场景 `diffs 0` 的原因。
- 105 个 fire 类动作里只有 **58 条**带列窗口，其余（`ZombossDarkFireBreath`、`DarkLobFireballs`、
  `EightiesFireSpeakerRay`…）只计数 `boss_action_unwired`，不抛异常。`modern_93` 的 `unwired=3` 就是该阶 3 个非 Fire 动作。

**CLI 证据**（`--run-level` 追加 `boss / bossStages / bossSpawned / bossActionUnwired / bossUnavailable`）：

```
modern_93    => boss=zombossmech_modern1 stages=3 spawned=True unwired=3 tick=12000 status=playing hash=0x52d17c0a3eb87a42
modern_93 --boss off => boss= spawned=False hash=0xd4740a5cc280143a
beach_19     => boss=zombossmech_beach  stages=3 spawned=False tick=9220 status=lost
frontyard_67 => boss= unavailable=1
```

71 个带 `extra.boss_zombie` 标记的关卡里，`spawned + unavailable == 71` 且 `spawned >= 60`；
4 关（`frontyard_67/74/165`、`muji_16`）的 world 在数据里根本没有 boss，如实计入 `bossUnavailable` 而不是编一个。

**顺带修掉的真 bug**：割草机的 `damageZombie(id, 100000)` 会被路由进 `damageBoss`，一次只掉一阶，
于是割草机滚过几 tick 就把三阶全打完 —— `modern_93` 曾在 tick 4363 判 `won` 且 `mowerKills=13`（含 boss）。
现在 `tickMowers` 里 `if (zombie.isBoss) continue;`。

**仍未做**：boss 阶段动画/演出（只有数值与列燃烧）、`ReservedColumnCount` 只记录未用于禁止种植、
`deathRow/deathColumn` 未用于死亡演出。这些属 S8 表现层。
---

### 2.20 进度与星章落盘（2026-11-21 10:57，S6.0 = t33）

`--run-level … --progress <file>` 在终局写一次存档（won / lost 都记 attempt），随后打印
`progressReport` 单行 JSON；**不传该参数时输出与改动前逐字节相同**（smoke 32 场景 sha 前后都是 `95B0156A1850`）。

beach_23 脚本胜的实测输出：

```
{"cleared":1,"levels":{"beach_23":{"attempts":1,"bestTick":1597,"cleared":true,
 "goals":[true,true,false],"stars":2,"target":3}},"totalStars":2}
```

2 星而非 3 星是**数据问题不是实现问题**：`beat` 与 `mowers`（5 车全在）过，第三颗要求 `kill count=10`，
而该关只生成 1 只僵尸 —— 即 C35 那 67 条不可达星章之一。这里如实给 2 星，没有为了让三星好看去改判据。

新增三个只读 getter（已落地，**未进 hash**）：`sunSpent()`（种植+融合累计扣费）、`mowersLeft()`（`state==0` 的车数）、
`plantsLost()`（被啃死/被砸死，不含玩家铲掉）。星章只增不减、`bestTick` 取最快、损坏存档报错且原文件字节不变、
非 ASCII 路径可读写。

**仍缺**（S6 后续）：世界钥匙、金币、商店购买、奖励结算都还没有存储位；`Progress` 现在只有
`version/updated/keys/coins/levels`，`keys` 与 `coins` 是占位字段，没写入路径。`content/stars.json` 的
`sun_used`/`sun_produced`/`plants_lost`/`time` 四类目标显式判 fail 并可用 `starKindIsMeasured()` 查。

### 2.21 跳跃证据闭合（2026-11-23 08:35，S5.12 = t30）

`tryVault` 的触发窗口从 `kEatRangeCols + 0.05`（1.20 列）收到 `kEatStartCols + 0.05`（0.40 列），落点
`kEatStartCols + 0.05 = 0.55` 列；`zombie_hop` 事件带 `from/to/distance/jump`，测试断言
`distance > 0`、`to == from - distance`、`from <= centre + 0.40 + 0.01`、`jump == 1` 且被跳植物 hp 不变。
反向探针（窗口改回 1.20）原文：`a hop must only start at contact: from 5.698667 is outside the
0.400000-column window around 4.500000`。

**顺带发现并修掉的真 bug**：`tickZombies` 的啃食扫描用 `kEatRangeCols`（1.15 列）且排在 `tryVault` 之后。
旧窗口 1.20 只比它宽 0.05，起跳才总能抢先；窗口收窄后僵尸在 1.15 列先被判 eating，永远走不到接触距离。
处置：**只对 `family == "jump"`** 把啃食 reach 收到 `kEatStartCols`（贴脸才咬），其它族一字未动。
这条不是为了让测试变绿而改，反过来是测试暴露了"两套 reach 互相掩盖"的结构问题。

世界地图见 §2.22；矩阵「世界门」行现在 97/97/97（接线 = `worldmap.cpp` + `--worldmap`）。

---
### 2.22 世界地图模型（2026-11-23 09:20，S6.1 = 队长；10:30 按 t37 收口）

`native/src/worldmap.{hpp,cpp}` 把两张表合成一个可判定对象：`native/generated/world_gates.json`
（97 条门：星门 53 / 钥匙门 27 / 世界门 17）与 `content/worldmap.json`（26 个世界的
order/difficulty/unlock_cost/key_required）。关卡数从 `content/stars.json` 的键前缀数出
（frontyard 175 / egypt 84 / beach 95 / modern 129 …）。

三条口径，都不是猜的：

1. **钥匙与星数是两套货币**。`key_gate` 的 `m_cost` 是**钥匙把数 1..5**，`star_gate` 的 `m_cost` 是星数；
   世界入口按 `key_required` 走钥匙，不再用星数开门。
2. **门的名字取 pack world id，不是 client id**。`rainbowmarket_stargate_start` 的 `worldClient` 是
   `lunarrainbowmarket`，所以匹配同时接受 `<client>_stargate_start` 与 `<world>_stargate_start`；
   三个别名（gta→losantosvice、skycity→sky、rainbowmarket→lunarrainbowmarket）在生成器里已归一。
3. **"没有门"与"门要求 0 星"是两件事**。`WorldInfo::hasEntryGate` 区分它们，
   `WorldStatus::starsSource` 取 `sheet`（原表给了数）/ `client`（回落到 unlock_cost）/ `none`（钥匙门，不谈星数）。
   实测只有 frontyard 是 `client` 回落；10 个世界根本没有 `*_stargate_start`。

CLI 证据（`--worldmap content`，26 行 state）：

```
{"clearedLevels":0,"gates":97,"keys":0,"rows":[{"gates":0,"id":"frontyard","levels":175,"order":1,
 "reason":"needs 1 stars, has 0","requiredKeys":0,"requiredStars":1,"starsSource":"client","state":"locked"},
 {"gates":0,"id":"egypt","levels":84,"order":2,"reason":"needs 1 keys, has 0","requiredKeys":1,
 "requiredStars":0,"starsSource":"none","state":"locked"}, ...],"stars":0,"worlds":26}
```

`--worldmap` 存在的理由是**避免 C41 重演**：模型若无任何真实调用方，单测绿灯只说明它能算，不说明它被用。

**新发现 C46（medium）**：`content/worldmap.json` 里 25 个世界 `key_required=true` 且 `unlock_cost=1`，
即"任何世界都只花 1 把钥匙"；而原版 `key_gate` 本身就消耗 1..5 把钥匙（分布于 27 条门）。
这更像客户端把开门价压平的简化，不是原版数值；S6.3 接入真实钥匙经济时需要重新核对，
现在不做推断性改写。

---

**t37 收口（2026-11-23 10:30）**：

1. **`kungfu` / `kongfu` 拼写**：判决统一用 `kongfu`（`content/worlds.json` 的 id、`worldmap.json` 的键、
   83 个关卡文件的 `world` 字段、8 条门世界名都是 `kongfu`；只有 1 条门写 `kungfu`）。
   `tools/contentc/worlds.py` 的 `ALIASES` 已加 `"kungfu": "kongfu"`，`native/generated/world_gates.json`
   已重生成：`worldClient`/`targetClient` 全部归一到 `kongfu`，`world`/`target` 保留原表原值（原始证据不涂改）。
   **注意**：任务书里「24 条门」无法复现——按 `world` 值或 raw 文本统计都是 9 条（`kongfu` 8 + `kungfu` 1）。
2. **62 条「悬空 world」的分类**：真别名 9（`gta` 6 / `skycity` 2 / `rainbowmarket` 1）+ 活动·赛事·节日 49 +
   测试残留 3（`tes12`/`tes13`/`element`）+ 拼写错 1（`kungfu`）。归一后真正无家可归只剩 `kungfu` **0 条**（已修）。
   附带发现：`target` 侧 38 条不是世界 id，而是 star/key 门的 `m_unlockedFrom` 关卡引用——统计悬空只能看 `world`。
3. **cleared 口径收口**：新增 `pvz::map::clearedLevelsFor(progress, worldId)`（`native/src/worldmap.cpp`），
   `--worldmap`（`main.cpp`）与 `--worldmap-screen`（`worldmap_view.cpp`）都改走它，不再各存一份前缀统计。
   `worldmap_test.cpp::testClearedLevelsAddUp` 断言「逐世界 cleared 之和 == 该存档清关总数」、
   「全清 + 99 把钥匙 → 26 个世界全 completed」、「不属于任何世界的关卡 id 不计入 frontyard」。
   **口径诚实点**：25/26 个世界是钥匙门（C46），所以「全清」不等于「全 completed」；
   `lunarrainbowmarket` 另有 10 星门槛，夹具必须给星才过。

### 2.23 桌面世界地图 screen（2026-11-23 08:55，S6.3 = 队长）

`native/src/worldmap_view.{hpp,cpp}`（挂 `pvz_launcher`，只有桌面构建编译）把 §2.22 的模型画成玩家真正
看到的选关界面：26 个世界排两列（左 13 / 右 13），选中行高亮，右栏是详情（中文名 / id / 状态 / 描述 /
门票 / 关卡数 / 世界门数 / 回车入口）。`↑↓` 选行、`←→` 翻列、鼠标点行、`Enter` 进入（填
`enteredWorld/enteredLevel` 后退出）、`Esc` 退出。

CLI：`--worldmap-screen <content> [--progress <file>] [--assets <dir>] [--snapshot <out.png>] [--frames <n>]`。
`--frames >0` 用 SDL 软件渲染跑固定帧数后返回，所以这个界面能在 CI 里测（`worldmap_render`，desktop 第 25 个用例）。

实测（空存档，`--frames 2 --snapshot worldmap.png`）：

```
{"completed":0,"entered":"","keys":0,"level":"","selected":"frontyard","stars":0,"unlocked":1,"worlds":26}
```

- 画面 1280×720，采样色数远超 300（不是空画面）；两次运行帧大小一致（界面不读时钟、不读随机）。
- 缺 `ui/font_zh.ttc` 时抛 `…/ui/font_zh.ttc: cannot open the Chinese font`，不是画一个空窗口。
- 截图三张的迭代记录：第一版详情栏文字冲出面板、底部提示被裁；第二版把提示移到面板外；第三版给门票加
  换行 —— 三处都是**看图才发现的**，不是测试报的。

**C48（medium，已按规则处理）**：`content/worldmap.json` 给最基础的世界 `frontyard` 也标了
`unlock_cost = 1`，照字面算，新存档 0 星时 26 个世界全锁 —— 玩家一步都走不了。处置：模型显式加
`WorldInfo::starter`（order 最小的世界）并让 `status()` 对它返回 `available`，详情栏写「初始世界（客户端
标价 1 颗星，不生效）」。这是**写进模型的产品规则**，不是界面里的隐藏特例；测试
`worldmap_test.cpp` 断言 starter 开放、埃及 99 星仍锁（必须用钥匙）。

---

---

### 2.24 商店模型（S6.2，2026-11-23 落地）

**数据**：`content/shop.json` 585 条（items 459 / seeds 81 / bundles 25 / currency 20；
计价 currency＝gem 469、coin 100、mint 10、free 6；`implemented` 527 true / 58 false）。
`native/generated/shop_unlock.json` 585 条（unlock.kind＝none 484、coins 99、world 1、mixed 1、stars 0）。

**三条必须记住的真相**：

1. 唯一 `unlock.kind == "world"` 的行是 `obb_com.popcap.pvz2.pinata.egypt.consume.tutorial`
   （埃及彩罐包，gem 60,000），**不是世界钥匙**。商店不铸钥匙，钥匙只来自玩法进度。
2. 6 条 `free` 行 `price=0` 且**全部 `implemented=false`` —— 出厂状态下免费商品拿不到，
   引擎因此拒绝它们（`not implemented in this client`），而不是假装发奖。
3. gem/mint 计价一律拒绝（`unmodelledCurrency` 479 条）：客户端没有宝石与薄荷货币，
   硬发等于凭空造币。

**引擎**：`native/src/shop.{hpp,cpp}`（挂 `pvz_shop`，链 `pvz_progress`）。
`Shop::load(contentDir, unlockFile)` 把两张表按 id 左连接，缺 unlock 记录记进 `missingRows`
且该行 `unlock=unknown`（fail-closed，不猜）。`purchase()` 的拒绝顺序固定：
未知商品 → 已拥有 → 未实现 → 星门不足 → 门槛未知 → 货币不支持 → 余额不足；
只有最后一步真的扣钱并写入 `Progress::purchases`。

**CLI 证据**（`build
ative\Release\PvZ2SHUTTLE.exe`，839,168 B，
sha256 `42EE9647F13B86042DF0232D3E8A3CA10AD7ECE6F757E3E2B075001FFB8CC821`）：

```
--shop content --coins 1200
{"buyable":21,"byUnlock":{"coins":99,"mixed":1,"none":484,"stars":0,"unknown":0,"world":1},
 "coins":1200,"items":585,"keys":0,"missingRows":0,"purchases":0,"seeds":0,"unmodelledCurrency":479}

--shop content --coins 1200 --buy seed_iris
{"buyable":21,...,"coins":700,"coinsSpent":500,"grantedSeed":"iris","item":"seed_iris",
 "ok":true,"purchases":1,"reason":"","seeds":1,"unmodelledCurrency":479}
```

**购买口径（2026-11-23 09:55 收紧，t36 复审 N2/N3 修复后）**：`buyable 21` 只数
「coin 计价 + 已实现 + 门槛已知 + **产物本客户端能真正发放**」的行；唯一能发放的产物是
`payload.plant_id`，写进 `Progress::seeds`。其余 coin 计价行（costume/setting/seed_pack/gems/
world_key/mower_charges/plantfood_*）一律拒绝，理由 `payload <kind> is not modelled yet` ——
收了币什么也不给，比不卖更糟。`unmodelledCurrency 479` 仍是 gem/mint 计价的行数。

**`one_time` 语义（N2）**：`shop.cpp` 此前解析了 `one_time` 却从不读，导致 43 行可重复购买行
第一次买完就报 `already owned`。现在只有 `one_time=true` 的行用 ownership 拦；可重复行可以再买，
`purchases` 保持集合语义（不重复记名），种子不重复入账。

**矩阵**：商店行由 `wired=0` 改为 `wired=585`（`shop.cpp` + `--shop` 是真实调用方）。

**测试**：`native/tests/shop_test.cpp` 13 段，含「coin 购买后余额 1200→700、二次购买报 already owned」、「种子落进 `Progress::seeds` 且往返存得住」、「coin 计价的 gems/setting 行报 `payload … is not modelled yet` 且不扣款」、「内联可重复行能买两次、只记一次 ownership」、
「gem 行拒绝且不扣款不记录」、「world 行拒绝且 `progress.keys` 仍为 0」、
「存档往返保留 purchases」。desktop 26 用例、audit 20 用例全绿。

### 2.25 战斗空间单位修正 + SpawnOffset.y（2026-11-24，S3 = 队长 + geometer）

**发现**：引擎把 pack 像素换算成列时用的是 `kPixelsPerColumn = 60.0`
（`native/src/engine/action_runner.cpp`、`native/src/engine/registry.cpp`），但美术空间是
**100×116 像素/格**——这是 `pkg_2073` 的 `ArtCenter` 在 374 个样本上的众数（`99×115` ×164、
`99×116` ×38、`97×119` ×25），且出厂常量 `kShotStartOffsetCols = 0.35` 恰好等于
`SpawnOffset.x = 35 / 100`。也就是说 SpawnOffset 与 RectTriggerRange 一直在 1.667 倍错的
空间里运算：豌豆枪口不是 0.35 列而是 0.583 列，土豆雷的爆炸窗口不是 ±0.65 列而是 ±1.08 列。

**处置**（本次已改，两处常量同时改）：`kPixelsPerColumn = 100.0`，并跟进三条测试期望
（`engine_test.cpp` 的 `windowEdge` 除数、土豆雷 RectTriggerRange、食人花射程）。
改后 32 场景冒烟只有 2 条变化（`frontyard_1 script`、`beach_23 win`）——没有植物的纯波次场景
不受影响，正是这条修正在「本来就不该动」的地方没动。

**SpawnOffset.y 数据**（geometer，`native/generated/spawn_offsets.json`，sha256
`A96C735E…B256`）：487 行 / 224 株，`pxPerColumn 100`、`pxPerRow 116`；负值向上（480/487 ≤0，
中位 −32 px ≈ −0.28 行），7 条正值逐条列出；`-600/-1000 px` 是「从天而降」的投放点
（−5.17/−8.62 行），保留不裁剪；`FlowerPot Actions[0].x = 10000` 是哨兵，跳过并计入
`skippedOffsets 1`。**诚实边界**：任务书里说的「COMPLETENESS 有 100×116」当时并不存在，
这份数据是本次实测建立的，不是引用。

> 仍未用上：`SpawnOffset.y` 目前只在数据侧（渲染层还没有纵向落点），引擎是 2D 行列模型，
> 纵向高度只影响美术表现。接法见 S3 队列。

### 2.26 音频管线（2026-11-24，S5 = sonic）

**状态：从 0% 变成「能解码、能映射、能出声」，但还没接进战斗与菜单的播放循环。**

- **目录**：`AudioCatalog` 三段装载 = `audio_report.json`（10 条）+ 目录扫描（34 条：26 首
  世界曲 + 8 个 wav）+ `audio/obb/`（21 条 OBB 还原曲 + `durations.json`），合计 **65 sounds =
  26 bgm + 18 sfx + 21 obb**。`audio_report.json` 只有 10 条这点必须记住：光看清单会漏掉
  26 首世界曲。
- **解码**：WAV（`SDL_LoadWAV` 同构的自研头解析）+ OGG（vendored `stb_vorbis` v1.25，NOTICE 已登记）
  共 **60/65 文件、4475.916 秒**；**5 个 mp3 没有解码器**，审计里逐条显式报错，不静默当作零。
  OBB `durations.json` 与实测吻合到毫秒（123.4→123.440、6.0→6.018、63.0→63.000）。
- **事件映射**：40 个引擎事件里 **22 个接通**，18 个因音库无对应素材显式 `null`
  （含 `level_start`/`plant_died`/`explosion`/`fusion`）。12 个世界的 `_loop` 全部命中，
  无一走 OBB 兜底。
- **pack 交叉**：`pkg_2073`+`pkg_2082` 的音效字段共 966 值（215 空），非空 751，
  **别名档命中 554/751 = 73.8%**，精确档 0/751——pack 里存的是 `Play_*` 事件名，
  不是音频文件名，所以精确匹配必然是 0（报告 §5 解释了映射规则）；44 个未命中逐条列名。
- **引擎侧为此新增三个「只为表现层」的事件**（不进 hash，audit 22/22 不变）：
  `shot_fired{id,row,x,projectile,damage}`、`shot_hit{shot,zombie,row,x,damage}`、
  `sun_spawned{id,row,x,value}`——没有它们，音频层只能靠血量差猜「刚开了一枪」。
- **CLI**：`--audio-audit <assets>` → `{"bgm":26,"decoded":60,"deviceAvailable":false,"missing":[],
  "seconds":4475.916,"sfx":18,"sounds":65}`，audit 构建 `deviceAvailable:false`、桌面构建 `true`
  （真的开到了设备）。
- **仍未做**：`battle_view`/菜单里每帧 `pump()` + 把 `World::events()` 送进 `playSfx`
  （T45 进行中）；5 个 mp3 需要再 vendored 一个解码器。

### 2.27 音频运行时接线（2026-11-24 10:50，S5 = sonic / T45）

**状态：桌面版第一次真的有声。** 管线（§2.26）接上播放循环后：

- 接线：`battle_view` 按 `level.world` 起 BGM（`frontyard_loop`），每帧 `consume(events)+pump()`，
  11 类引擎事件映射；`menu/worldmap/level_select/launcher` 播 menu 音乐 + 点击 `sfx_click`；
  `main` 只加 `--audio-off`。headless（`--frames`/`--battle-snapshot`）**不建后端**，
  SDL 音频子系统都不初始化，截图逐字节不变（`D56A3D6A…79A90` / `37F75744…AB7B1`，与接音频前相同）。
- **抓到的真 bug**：`EventMap::soundFor` 查的是 21 条抽象事件，而引擎发的是 40 条引擎事件，
  两套名字表不重合 —— 一度「有 22 条映射但一条都播不出来」。新增
  `EventMap::soundForEngineEvent()` 后 22 通 / 18 显式 null，null 全部进 `silentEvents()`。
- **抓到的性能坑（必须记住）**：T38 的 OGG 解码每帧 `reserve(精确大小)`，等于每帧重分配整条缓冲 ——
  `frontyard_loop` 解码 **83.2 s**（O(n²)）。改成「容量不够才翻倍」后 **2.66 s**，设备用例整条
  109 s → 6 s。`probeAudioFile` 走 `decodeOgg<false>` 不存样本，所以 T38 的 `audio`/`--audio-audit`
  全程没暴露它 —— **只测「能不能解码」不测「解码多快」，就会漏掉死循环级的性能退化**。
- 实测（真设备）：`device: live (SDL3 push-mode device (48 kHz float stereo))`、
  `pump: 133 calls, 146944 mixed frames, 4 sfx calls`（146944/48000 ≈ 3.06 s，与设计一致）、
  `events: seen 9 mapped 4 unmapped 1 deduped 4`。
- 反向探针：删掉 `tickTypes_` 去重 →
  `audio runtime test failed: three (tick, type) pairs are mapped, saw 5`。
**打磨（2026-11-24 12:20，T49）**：上一条「5 个 mp3 走 wav 兜底」已被实测证伪并修掉 ——
`ui_open` 真身 5.578 s（267,740 帧，peak 0.9455），兜底的 `sfx_click` 只有 0.050 s（1,102 帧），
**差 111 倍**；`shoot_hit` 1.469 s vs `sfx_shoot` 0.090 s。决策：引入 **minimp3**（CC0，单 TU，
`native/third_party/minimp3.h` + `minimp3_ex.h` + `minimp3.LICENSE`，NOTICE 已登记），零 CMake 改动。
`--audio-audit` 读数因此变成 `decoded 65 / seconds 4487.955`（原 60 / 4475.916）。

- 音量：`--volume 0..100`（一个 master，两条总线 `musicBus = master × (muted?0:vol)` 保留拆分空间）
  + `--mute-bgm` / `--mute-sfx`。实测 `peak(100)=0.249969 / peak(50)=0.124985 / peak(0)=0.000000`。
- BGM 交叉淡入 `kMusicFadeSeconds = 0.75`（36,000 帧 @48k），旧曲搬进独立 fading voice、
  共用同一线性包络；`max sample step 0.0000070`（无爆音）、`mixed frames 36672 == requested`。
  同曲重播只更新 gain，不重启。
- 反向探针：抽掉 `render()` 的音量乘子 → `audio test failed: master volume 0 must produce silence`（14/26 红）。
- 仍存限制：混音器 **8 voice**、48 kHz 立体声、**最近邻重采样**（无插值），没有 3D/衰减；
  无独立音量滑杆 UI（只有命令行）。这些已不足以影响「有声可听」，记为 C52 的剩余部分。

### 2.28 原版差距对照：我们到底还缺什么（2026-11-24）

口径：跑在 2117 个原版包上，**1110 个 objclass / 54,583 个对象**；客户端只覆盖「内容 + 战斗内核」
那一簇。完整数据见 `docs/reviews/2026-11-24-original-vs-client.md`。

**结论：缺的不是内容，是关卡机制与非战斗系统。** 1809 关里 1200+ 关有至少一种
客户端数据里不存在的机制 —— 现在能打，但打的不一定是那一关。

| 类别 | 原版规模 | 客户端 | 后果 |
| --- | --- | --- | --- |
| 传送带关 | 349（+132 关带改动波） | `extra.seed_bank` 只是一个 `int` | 349 关的卡组来源是错的 |
| 初始植物 / 初始场地物件 | 272 / 475 关 | 无 | 开局空场，原版是预设阵地 |
| 墓碑 | 241 关（+353 关墓碑波） | 无 | 挡格与出土机制不存在 |
| 保护植物挑战 | 286 关 | 无 | 失败条件不存在（现在是「割草机没了就输」） |
| 事件波（潮汐/寒风/风暴/传送门/蜘蛛雨/鱼/恐龙/海滩） | 26–130 关各一类 | 无 | 这些世界的招牌玩法缺失 |
| 星章挑战运行时 | 948 关 | 只有 `stars.json` 的目标文本 | 目标能算分，挑战本身不触发 |
| 关卡变异 / 棋盘格 | 21 / 49 关 | 无 | 少数关的规则与行数不对 |

非战斗系统（整块空白，属 S9）：

| 系统 | 原版对象数 | 说明 |
| --- | ---: | --- |
| 竞技场/锦标赛（`Joust*`） | 551 | 联网玩法，本地只能做壳 |
| 玩家分段规则 | 922 | 单文件 92 条规则 |
| 图鉴（`PlantAlmanacData`） | 167 | 植物条目文案 |
| 任务 / 每日 | 69 + 2 | |
| 花园（`ChineseGarden*`） | 65 | 42 个桥接模块 |
| 彩罐 / 道具 / 强化 / 教程 | 41 / 29 / 14 / 21 | |
| 装扮 | 566 件（`shop.json` 里已编） | 界面未做 |

已对齐的部分（不要重复做功）：植物 339 / 僵尸 1127 / 护甲 102 / 弹道 602 / 养料 293 /
融合 85 / Boss 50（71 关）/ 世界门 97 / 商店 585 / 星章 5427 条目标。

**经济闭环的数据答案**（T48，`native/generated/rewards_from_pack.json`）：
金币按**击杀周期**掉（银币每 2 杀 1–3 个、金币每 40 杀 1 个 / 每 60 杀 1–3 个，银币 10 / 金币 100），
关卡末午餐盒只 `coinpack_medium` = 100 币（normal 与 shiny 数值相同，shiny 的 7 条额外奖励
`Weight` 全 0 = 关闭）；**钥匙是真实掉落**（`EgyptKey`/`PirateKey`/`CowboyKey`/`FutureKey`，
`Period=30` 击杀、按世界限定、`EnabledAfter=egypt3`）；种子包来自 15 个关卡内嵌的
`ZombieDeathSeedDropModuleProperties`（`DropChance` 0.01–1，76 条加权）。**mint 与 star 是
server-only**（mint 只有价格、star 只有花费端）。另有 13 张 `PresentTable` 是悬空引用
（68 关引用、全库 0 定义）——这些关原版大概率不出午餐盒。

**内容管线的隐患（C53）**：`content/levels/*.json` 的 `minecarts`/`rail`/`vasebreaker` 三个键在
`tools/` 里没有生成代码，是手写残留 —— 重跑内容构建会静默丢掉。已开 T53 修。

### 2.29 字段级差距与三条口径更正（2026-11-24，T47）

`tools/contentc/original_gaps.py` 单趟扫 2116 张原版表（1809 个 `LevelDefinition`、41,218 个对象），
对 12 个实体做 46 张字段对照。总数：**mapped 13,075 / packOnly 793 / clientOnly 12,210 / agree 1,427**。

**原版有值、客户端没有字段的 36 组**（按影响排序，前三名）：

| 实体.字段 | 有值的关卡/条目 | 我们缺什么 |
| --- | ---: | --- |
| `levels.Modules` | 1806 | 模块名清单本身（我们只导了 `extra` 的 14 个键） |
| `levels.StageModule` | 1806 | 原版舞台标识，是回到原表的身份键（见 §2.22 的 package 主键） |
| `levels.Loot` | 1802 | 每关的掉落表引用 —— T48 的 `rewards_from_pack.json` 是它的投影，但没进 `content/levels` |
| `plants.PlantStats` / `PlantGridType` / `Boosts` / `ZenGarden*` | — | 数值分档、占地类型、强化、花园 |
| `zombies.WavePointCost` / `Weight` / `CanSpawnPlantFood` / `ScaledProps` | — | 波次点数预算与缩放 |

**原版整块、客户端零覆盖的子系统 7 个**：`plantfood_drop`、`plantfood_purchase`、
`level_rewards`、`achievements_quests`、`daily_season`、`mower_config`、`sound_events`
（`key_drops` 有 `worldmap.key_required` 布尔，算「部分」）。其中 `sound_events` 尤其明显：
原版 `ImpactSoundEvent` 有 **478** 条，我们的事件→音效映射是按 40 个引擎事件手写的。

> 5 个整块子系统与「补 36 个单字段」哪个先做：**子系统优先**。原因：单字段补上但消费方不存在，
> 等于把数据搬进来又不接线（C41 的老毛病）。

#### 三条口径更正（原文改成这里，旧表述一律作废）

1. **「20」有三个不同出处，不可互换**：`content.pack` 里与客户端同名的僵尸 20 个 / `id_mapping`
   的 exact 命中 20 条 / 护甲桥的 20 条 —— 数字相同、集合来源不同。§2.16 用的是第三个。
2. **商店 585 是客户端口径**：原版 `StoreProductProps` 只有 **565** 件，且 **561 件 `Price=0`**；
   客户端的 `price`/`price_gems`/`price_mints` 是自创定价（`price ← Price` 的 `agree=10` 是
   「0 撞 0」的巧合，不能当成对齐证据）。
3. **关卡不是世界地图节点投影**：原版 worldmap 只有 **555** 个 level 节点，客户端有 **1432** 个
   关卡文件（1809 关里 1809 个文件、1432 个有世界地图入口），22 个世界逐世界都不等 ——
   客户端关卡是从 `content/levels/*.json` 补出来的，不是从 worldmap 抄的。

### 2.30 关卡机制接线（2026-11-24 13:00，T51 = wirer）

**状态：五类机制真的会出现在战斗里，其余机制不再静默消失。**

数据侧（§2.21 与 T50/T51 编译产物 `level_mechanics.json`，t57 后 **4,827,318 B** /
sha256 `9F33A09E4FCD49EFAACAE8432D834EA42C47AF7B2C5FBD134316CF8437470887`）此前只有一张表，
引擎一个字都没读。T51 之后：

- 表：`native/src/engine/mechanics.{hpp,cpp}` 的 `LevelMechanicsTable` 读 1809 关，
  `WorldOptions::mechanics` 默认开，失败一律 `mechanics table: <path>: <reason>`。
- **传送带**（350 关声明 / 348 关能建卡槽 / 349 关有卡槽表，`lostcity_67` 走 `changes[].add[]`）：
  开局 6 张手牌，种一张补一张；**不扣阳光**（探针原文
  `mechanics test failed: a belt card must not cost sun, sun=525`），不进 `sunSpent`、不发 `planted`。
- **初始植物**（272 关）：开局直接铺，不扣阳光。`beach_23` 实测 `initialPlants=4 sun=550`，
  这就是它冒烟哈希变化的原因。
- **初始场地物件**（690 关声明 / 583 关可摆）：`GridItemEntity`（占格、可铲、可炸、可被啃，
  血量走 `kGridItemHitPoints = 300`，**fallback，无原表证据**），墓碑波另有一路。
- **保护植物**（286 关）：按 `mustProtectCount` 判活 —— **存活数 < 需求才判负**，
  缺失(−1)+`failWhenProtectedPlantDies` 时用株数兜底，`=0` 且不设 flag 时不判负。
  探针原文 `mechanics test failed: losing one of five must not lose a mission that requires four, got: lost`。
  `renai_1`（5 株全保）空脚本实测 `protectFailures=1 status=lost tick=3455` —— **不种植物就该输**，
  它从 `playing` 变 `lost` 是对的。
- **其余机制不静默降级**：`mechanic_unknown{kind,count,tier}` 按 kind 聚合，`--run-level`
  直接出 `mechanicUnknown[{kind,count}]`。`beach_14` → `events 1 + spawners.beach 8`、
  `beach_23` → `spawners.fish 10`。`spawners.jittered` 判 **covered**（它的 waves/objects 就是普通
  波次表，1615 关走同一条 director 路径）。

**覆盖率**：`level_mechanics.json` 里 1245 关至少带一类机制，其中 **903 关的机制全部被引擎消费**
（`tools/parity_report.py` 的「关卡机制」行 `wired=903`）；剩 342 关带 `events` / `mutators` /
`boardGrid` / 海滩·鱼·恐龙生成器之一。

**冒烟**：32 场景 **11 条变化**，全部逐条归因 —— 8 个世界 index-1 关卡开局有初始场地（只 hash 变）、
`frontyard_6` 只 hash 变、`beach_23 win` 只 hash 变（4 株初始植物）、`renai` 变 `lost`（保护任务，正确）。
基线已按这 11 条刷新。

**保护目标的真相（t56 取证，`docs/reviews/2026-11-24-egypt74-protect.md`）**：`egypt_74` 的 5 条目标只落在
**3 个格子**上（(3,2) 重复三次）、`MustProtectCount=4`，但**它不是打不赢，是零容错** ——
判负只在植物死亡路径读阈值（`world.cpp:1106-1119`），三株都不死就能通关。
数据层 `mustProtectCount > 去重格子数` 的关卡有 **5 关**（carnival_23、egypt_74、frontyard_51、
lostcity_45、sky_46），按放置顺序模拟 `placed < must` 的有 **11 关**，其中 **6 关 `placed==0`**
（carnival_79、carnival_81、chinesegarden_57、frontyard_53、lostcity_67、sky_31）——
这些关的保护判定永远不会触发，等于静默空转，需要显式事件（t58）。

原表 287 个 protect 模块里 `must ≤ len(Plants)` 全部成立，而 `must > distinct` 有 5 关，
两者同时成立只能靠「同格多株独立计数」（这是推断，未跑原版客户端验证）。我方还有两处偏差待修：
`extract_protect` 用 `package.one()` 只取第一个模块（`lostcity_46` 少 7 株，t57 在修）、
`failWhenProtectedPlantDies=true` 是编译端客户端默认值（原表无此字段，正在加标注）。

### 2.31 经济闭环：金币、钥匙、种子包真的会进存档（2026-11-24 13:40，T55 = wirer）

**状态：打完一关，钱和东西真的会变。**

数据侧 `rewards_from_pack.json`（336,895 B / sha256 `7F83E66B…8E8C`，t56 更正后的版本）此前只有表。
T54 接线后 `native/src/rewards.{hpp,cpp}`（挂 `pvz_progress`，失败抛 `rewards table: <path>: <reason>`）读
25 条击杀周期行 / 36 张 present 表 / 76 条种子行 / 13 张悬空表 / 10 个 worldKey：

- **击杀周期金币**：银币 `Period=2` → 每 2 杀 1..3 枚 ×10；金币 `Period=40` → 每 40 杀 1 枚 ×100；
  金币 `Period=60` → 每 60 杀 1..3 枚 ×100。掉落次数 = 击杀数 / period，随机走 `World::randomBelow`
  （同种子同结果，测试用同种子两跑比对）。探针（银币 period 2→3）原文
  `rewards test failed: two kills must drop 1..3 silver coins, got 0`。
- **钥匙**：8 条 key 行按 `world` + `keysUnlocked()`（= 存档里 `egypt_3` 已 cleared，读档时判定，不追溯本轮）。
  实测把存档 `keys` 设 1 后 `--worldmap` 的 available 从 1 个世界变成 **25** 个 —— 这是世界门口径（C46）的
  连带事实，不是本轮引入。
- **午餐盒**：`<world>_normal_01`；命中 `danglingPresentTables`（13 张表 / 68 关）→ **不发**且
  `presentTableMissing=true`；表名不存在 → 回落 `egypt_normal_01` 并记 `presentSource="egypt_default"`；
  只有 `won` 才发；shiny 的 7 条 `Weight` 全 0 → 不发。
- **种子包**：按 `extra.package` 匹配 15 个内嵌模块（一 pkg 一关），逐击杀先 roll `DropChance` 再按 `weight` 抽，
  `applyRewards` 排序去重。
- **只在结算时算账**：`--run-level` 的 `coinsGained/keysGained/seedsGained/presentTableMissing/rewardUnmodelled`
  五个字段**只在带 `--progress` 时出现**；不传时与 T51 二进制**逐字节相同**（frontyard_1+script、beach_12 实测）。
  `--flow` 的 JSON 带同样五字段。

**CLI 证据**：
- `--run-level content beach_23 --script native/tests/scripts/beach_23_win.json --progress` →
  `"coinsGained":0,"keysGained":0,"presentTableMissing":true,"seedsGained":0,"status":"won"`（悬空表，不发）；
- `--run-level content egypt_1 --script <3 杀脚本> --progress` → `"coinsGained":30`（银币周期）；
- 两次 `--flow --progress` → `{"coinsGained":80,"presentTableMissing":false,"rewardUnmodelled":[{"count":1,"kind":"sprout"}],"status":"lost","tick":9220}`，两跑完全一致、存档 coins 累积到 160。

**门禁**：audit **27/27**（新增 `rewards` 用例）、desktop **36/36**、smoke 与 T51 二进制 **32 场景 diff 0**。

**申报的边界（C56）**：`rewards_from_pack.json` 只有 per-key / per-table 计数，**没有「关卡→LootConfig」
与「关卡→PresentTable」的逐关绑定**（`content/levels/*.json` 无 `loot` 字段、`content.pack` 里 `PresentTable` 命中 0）。
因此 `lootKey` 一律 `default`（47 个 danger/whack/NoLoot 关会按 default 结算），present 表按世界名推导 + 上述回落。

### 2.32 数据包对齐 460.9（2026-11-24 20:50，P0/P2 完成）

**结论先说**：我们手上的 `main.460….obb` 本来就是官方 **460.1**（MD5 `be21c6f0fe29ff243aaeaad2ca551833`），
不是 460.9。最新版三元组是**游戏 26.11.1 / 核心库 460.11 / 数据 460.9**（`down.pvz2shuttle.cn/manifest.json`）。
全渠道（MediaFire `v26.11.23`、Google Drive、GitHub 备份、官方站点）**都没有完整 460.9 OBB**，官方只供 460.1 基础包 + 两枚 `.rsbpatch` 补丁，
因此升级路线是「打补丁」，且必须从原版 460.1 起打。

已实测达成（每一步都有 MD5 硬校验）：

| 步骤 | 产物 | 校验 |
| --- | --- | --- |
| 460.1 → 460.2 | `work/versions/460.2.obb` 2,095,579,136 B | md5 `7a219bb7fbfd54b4176aa33e48704b48`（manifest 同） |
| 460.2 → 460.9 | `work/versions/460.9.obb` 2,096,463,872 B | md5 `2963d0781e4715522cb12bc2d3bb9f8e`（manifest 同） |

补丁容器（`RSBPatch`）已被复刻成纯 Python：`tools/rsbpatch.py`（`apply`/`chain`/`info`/`table`，35 例测试，含两窗口自引用回归与 `chain` 跨跳互校），
另有一份独立 oracle `tools/emulate_rsb.py`（unicorn 仿真核心库）只做验收、不参与生产。
容器格式、报文骨架、VCDIFF 方言与装配算法分别记在计划文档
`docs/superpowers/plans/2026-11-24-obb-460.10-rebase.md` 的 §6.2–§6.5。

**差量只有 6 个包**（详见计划 §6.5）：两条 `LawnStringsData` 各加 1 条 `ELEMENT_7_WAVEMASSAGE`、
`DisableSkipLevelModuleProperties` 加一行 `RlConfig`（Roguelike）、一个关卡的 `WaveStartMessage` 键化、
一个关卡加 `SuppressFlagZombie`、`ThymedEventSchedule` 27→30。植物 / 僵尸 / 弹道 / 护甲 / 关卡波次**一字未变**。
于是派生表里只有 `level_mechanics.json` 有一处实质变化（`egypt_25` 的 `waveStartMessage`），
`rewards_from_pack.json`、`spawn_offsets.json` 只换了 `generatedAt` 墙钟戳，
`world_gates.json` 因 `generated` 取 WorldData 的内容戳必须重生成（现 `generated = sha256:b1f61cd5ef86dedb` = `sha256(pkg_2107_WorldData.json)` 前 16 位；文件本身 59,584 B / `sha256:b200e17f1b6fe1322ea5f5e2913440651c03d0b06a6fcdd426ee40691d0e75d2`，且该包不在 460.9 的 6 个变化包里）。

**数据树切换**：`work/obb_packages` → `obb_packages_460_1`（归档），`obb_packages_460_9` → `obb_packages`，
460.9 成为唯一真源；`PVZ2_OBB_DIR` 是切树开关（`tools/contentc/worlds.py::_default_obb` 起 12 处统一读它）。
切换后 12 个 compiler `--check` 全 exit 0，`obb_build_content_v2.py --content-report` → `mismatches: none`。

**460.9 新增但**无人建模**的东西**（已登记为缺口，不当成已复刻）：
`RlConfig`（Roguelike 配置）、`SuppressFlagZombie`（关卡开关）、`ThymedEventSchedule` 的 3 组新事件、
`EffectElementReactionGroup_1536/_768/_Common`（三组元素反应美术，合计 880,640 B 未解压进美术库）。

**460.9 新增数据的实测口径（t63 = geometer，2026-11-24 21:02）**：`tools/contentc/newin4609.py` →
`native/generated/patch_460_9.json`（154,618 B，sha256 `90b4e3b2c9fc884d7cd38c260b97e102823b1e51fc6cf61545c5a0d77cc57144`），
`--check` → `patch_460_9 rlConfig=1 levelFlags=271(true 215/false 56) thymeEvents=30(new 3) unknowns=0`。

- **`RlConfig`**：`pkg_0234` objects[495]，17 字段原样铺平（`Version 1 / LevelCount 12 / ChoiceCount 3 /
  StartingSunBase 50 / StartingSunPerLevel 25 / StartingSunMax 500 / HealthPct 0.18 / DamagePct 0.1 / SpeedPct 0.03 /
  EliteChance 0.0 / EliteEvery 4 / EliteHealthBonusPct 0.5 / EliteDamageBonusPct 0.25 / FinalLevelIsElite 1 /
  DefaultOwnedFactionWeight 2.0 / TemplateLevelNames[18] / ZombiePool[112]`）。
- **`SuppressFlagZombie`**：**271 关有该键**（true 215 / false 56），且不是 460.9 独有——460.9 只把
  `pkg_0416`（`memorytour_2`）从 null 改成 true。271 关**全部**映射到客户端 id（1809 包 ↔ 1809 关双射）。
- **`ThymedEventSchedule`**：`pkg_2101` objects[0] 共 30 条，`UniqueID` = 1..31 去掉 23；新增 **29/30/31**
  （全 `[EVENT_TIMESPACEECHOES_BACK]`，各 12 关，首关 `timespaceechoes_0003_1/_0004_1/_0009_1`），合计 445 个关卡引用。
  ★新增**不能靠 EventName 判**（同名事件在旧排期已出现 6 次），工具里写成常量 `THYME_NEW_IDS=(29,30,31)`。
- 三者**消费者 0**（`tools/**` 与 `native/src/**` 全 0 命中）→ 当时口径记「未实现」（C57）；
  其中 `SuppressFlagZombie` 已由 t64/t65 接力接进 content 与引擎（见下），`RlConfig` 与 `ThymedEventSchedule` 仍无消费者。

**消费端接线（t64 = mapper / t65 = wirer，2026-11-24 21:20）**

- **content 侧**：`content/levels/*.json` 的 `extra.suppressFlagZombie` **271 关**（true 215 / false 56），
  逐文件只多一行；`obb_build_content_v2.py --content-report` → `suppressFlag=271(true 215)` / `mismatches: none`。
  原版字段是 CamelCase `SuppressFlagZombie`、客户端键是 camelCase，工具里拆成 `SUPPRESS_FIELD`/`SUPPRESS_KEY`
  两个常量（只用一个会让 `derivedSuppressFlag=0`）。`false` 必须写出来——它与「没有这个字段」不是一回事。
  连带 `levelextra.py` 的 `KEY_SPECS` 多一条（kind=module / status=flag_only / classes=`WaveManagerProperties`），
  `level_modules.json` 的键数 14 → **15**（flagOnly 6 → 7）。
- **引擎侧**：**内核没有旗子僵尸实体**——`WaveDefinition.flag` 只有两个消费者
  （`native/src/engine/director.cpp:38` 的 `kFlagWaveSpreadSeconds = 1.0` 烘进 schedule、
  `native/src/engine/world.cpp` 的 `wave_spawn{"flag",…}`），content 里 3774 个 flag 波的僵尸类型全是普通类型。
  所以「抑制」= **丢掉波标记 + 计数**，不是造一个旗子僵尸：`flagDropped = spawn.flag && suppressFlagZombie_`，
  每波首次命中推 `suppressedFlagWaves_` 并发 `flag_wave_suppressed{wave,level}`，
  `wave_spawn.flag = spawn.flag && !flagDropped`（僵尸照常生成）。节奏窗口**没动**（1.0 s 仍烘在 schedule 里），
  真要连 spread 一起收得另开任务改 `director.cpp`。
- **CLI 证据**：`--run-level content frontyard_75` → `"flagSuppressed":1,"waves":1,"spawned":1,"status":"playing","tick":1800`；
  `beach_83`（false）与 `frontyard_1`（无键）JSON 里**没有** `flagSuppressed` 键。
- 口径提醒：`World::flagSuppressed()` 数的是「被抑制的 flag **波**」（去重），不是被抑制的 spawn 数。
- 探针：把 `flagDropped` 恒置 false → `mechanics test failed: each flag wave must be counted exactly once, got 0`。

### 2.33 核心库 460.11 清点（2026-11-24 20:55，analyst；报告 `docs/reviews/2026-11-25-core-460.11.md`）

数据是 460.9，但**最新核心库是 460.11**，两者不是同一版本。清点结论（只读比对，未执行 .so）：

- **460.11 不是 EA 官方流水线产物**：`.comment` 是 clang 17.0.2 (+pgo,+bolt,+lto) + LLD 17.0.2、`e_entry = 0`、
  出现源码路径 `D:/HookPVZ2/czProj/x64/jni/PvZ2/src/…`（451 时代是 `/opt/scm/jenkins_root/…`）→ 判定为本地重编。
- **JNI 导出面完全没变**（349 个导出符号名逐字一致），导入 +30/−7；规模 `.text +8.7%`、`.rodata +30.7%`。
- **新增 873 条字符串**，重心：**Roguelike 肉鸽系统 155**、**元素反应 60**、**7 个新植物 57**、关卡机制字段 42、设置/UI 50；
  消失 165 条。新增的 Module 类：`RogueModule`、`ElementReactionModule`、`SlotMachineModule`；
  Subsystem：`AciditySubsystem`、`VoidDragonNasaSubsystem`；GridItem：`GridItemIceHole`、`GridItemFireWall`。
- **容器与补丁格式没变**：仍是 RSBP patch v1 + RSB v4；没有新世界 id（`Poseidon`/`Atlantis` 在 451 已存在）。
- OBB 命名闸门要求 `main.<APK versionName 数字段>.com.ea.game.pvz2_shu.obb`，所以「460.11 的 APK + 460.9 的 OBB」
  会先卡在文件名（推断，报告 §9 已标明是推断）。

**对我们的口径影响（实测交叉核对，2026-11-24 20:58）**：拿 460.9 数据包搜这些新类名——

| 名字 | 460.9 数据里 |
| --- | --- |
| `ElementReactionModule` | 有（`pkg_0234` + `pkg_0398/0399` LevelDefinition） |
| `GridItemIceHole` / `GridItemFireWall` | 有（`pkg_0024`/`pkg_0025`） |
| `RogueModule` / `SlotMachineModule` | **0 命中** |
| `AciditySubsystem` / `VoidDragonNasaSubsystem` | **0 命中** |
| `roguelike`（数据文件/字段） | **0 命中** |

即：**肉鸽与老虎机只有客户端代码、没有随 460.9 下发的数据**；元素反应与两个新 GridItem 的数据在包里，
但我们既没编译也没接线（元素系统此前已裁决为「非原版机制、authored 可选层」，见 §2.13）。
结论：本轮「对齐最新版」在**数据侧**已到 460.9；**代码侧**的 460.11 新玩法（肉鸽/老虎机/酸性/虚空龙）
属于「有实现无数据」的客户端特性，复刻口径里记为未实现（C59），不做猜测性反推。

## 3. 缺陷汇总（按严重度）

| ID | 级别 | 系统 | 问题 | 归属阶段 |
|----|------|------|------|---------|
| C5 | 已修（原 blocker → 关闭） | 内核 | 记录已过期：`catalog.cpp` 早就在解析 `level.extra`，引擎现消费 boss / vasebreaker·rail·minecarts 标记 / `suppressFlagZombie` / 五类关卡机制（§2.19、§2.30、§2.32）。剩余的是「变体玩法本体」，另见 C27 | — |
| C15 | high | Boss | 71 关里 67 关已能真正出场（§2.19）；4 关数据无 boss 如实记 `bossUnavailable`；content Boss HP 仍是合成数据，引擎改读 pack 的 155 阶段 | S5 基本收口，表现层 S8 |
| C23 | blocker | 音频 | 无任何音频子系统 | S8 |
| C24 | 部分已修（原 blocker） | UI | 已有启动器、主菜单、世界地图、选关、结算、拖动连续种植；**未做**图鉴（Almanac 169）/ 花园（Garden 65）/ 设置 / 成就（Quest 69）/ 商店 UI（`--shop` 只有 CLI） | S6 余下部分 |
| C27 | blocker | 关卡变体 | 砸罐子/小游戏/矿车/潮汐/传送门全无 | S7 |
| C6 | high | 内核 | 植物等级成长未接 | S6 |
| C7/C16/C17 | high | 玩法 | 元素运行时为零；养料/融合引擎已落地（§2.18）但养料无掉落货币、桌面无交互 | S5→S6 |
| C11 | high | 行为族 | `support` 空实现 | S5 |
| C19/C20 | high | 表现 | 29 株缺美术；独立形象仅 31/147 | S4/S8 |
| C25 | 部分已修 | 存档 | `Progress` 已有星章（`stars`/`goals`）、金币、种子、购买记录、`lastLevel` continue 指针，原子写、损坏不覆盖；**未做**存档版本迁移策略；钥匙来源只有 `egypt_3` 通关一条，且世界门只花 1 把（C46） | S6 余下部分 |
| C28/C29 | high | 发布 | 无安装包；macOS 未构建 | S8 |
| C1/C2 | high | 数据 | 368 关未映射；1107 僵尸无客户端 id；24 个 Boss mech 无关卡放置 | S7/S9 |
| C3/C4/C8–C14/C18/C21/C22/C26/C30 | medium | — | 见各节 | S5–S8 |
| C41 | high | 玩法 | `World::feed`/`tryFuse` 曾无可达路径（只有单测直调）；已接 `replay` 的 `feed`/`fuse` op 并加 `replay_s5` 用例（§2.18） | 已修，待门禁复验 |
| C42 | medium | 玩法 | 养料无货币掉落（原版靠掉落植物food）；现为脚本/CLI 驱动 | S7 |
| C43 | low | 文档 | t24 报告称「融合扣阳光且允许负余额」，与现树不符（`tryFuse` 无扣费、配方表无 cost 字段） | 已更正（§2.18） |
| C44 | medium | 工具链 | 门禁结论不能与并行编辑共存：同一次运行可能 audit 绿、desktop 红在别人半成品 | 已加 `Get-TreeStamp`：树动了即 `[inconclusive]` + exit 2；11:19 严格跑实测 exit 2 |
| C45 | low | 数据/引擎 | `CabbageDefault` 按表内 `velocity.z{500,700}` + `acceleration.z -10` 积出 **140 s** 飞时，不成立；引擎改用水平速度算落点 + `kLobFlightSeconds = 0.75` |
| C46 | medium | 数据 | `content/worldmap.json` 25 个世界 `key_required=true` 且 `unlock_cost=1`（任何世界开门都只花 1 把钥匙），而原版 `key_gate` 本身消耗 1..5 把；倾向客户端把开门价压平的简化，S6.3 接钥匙经济时再核（§2.22） |
| C47 | low | 引擎/CLI | `--run-level` 不传 `--boards` 时全按 5×9 开（beach/modern 少两行）。已修为默认读 `content/../native/generated/board_sizes.json`，`--boards` 仍可覆盖；beach_23 现默认 6×9，哈希 `0x2f8ac180ac294f8c` 与冒烟基线一致 | 已替换并注明；原表数值未改（它描述的是原引擎的积分方式，不是错误） |
| C49 | high | 引擎 | **已修**：像素→列换算用 60，而美术空间是 100×116（`ArtCenter` 374 样本）。SpawnOffset 与 RectTriggerRange 全部 1.667 倍错位（豌豆枪口 0.583 列 vs 应 0.35）。已改 `kPixelsPerColumn = 100.0`，32 场景只 2 条变化。 |
| C50 | medium | 音频 | **已修**（T49）：5 个 mp3 sfx（shoot_hit/ui_open/ui_close/coin_drop/gem_spawn）用 vendored minimp3（CC0）真实解码；此前 wav 兜底不是「听感略差」而是差 111 倍时长（`ui_open` 5.578 s vs `sfx_click` 0.050 s），属实测证伪。`--audio-audit` 60→65 decoded。 |
| C51 | high | 音频 | **已修**（T45）：`battle_view`/`menu`/`worldmap`/`level_select`/`launcher` 都接了 `consume+pump`，真设备实测 133 次 pump / 146944 mixed frames；headless 不建后端，截图逐字节不变。 |
| C52 | low | 音频 | **部分已修**（T49）：已有 `--volume 0..100` 与 `--mute-bgm/--mute-sfx`、BGM 0.75 s 交叉淡入。仍缺：8 voice、最近邻重采样（无插值）、无独立音量滑杆 UI。 |
| C54 | low | 引擎 | **已修（2026-11-25）**：旧 `simulation.cpp` 的 `Battle` 保留（`engine::World` 已是主路径，但 `--simulate` 与 `simulation_test` 还用它做小规模自检），拒绝方式改成**可枚举**：新增 `Battle::unsupportedRules(level)` 返回「不支持的规则」清单（world / synthesized / 四条 extra 标记 / 棋盘尺寸），构造函数只抛出清单里的第一条。CLI `--simulate <content> [level id]` 现在支持指定关卡：干净关（`frontyard_1`）→ `{"level":"frontyard_1","simulated":true,…}` exit 0；Boss 关（`beach_19`）→ `{"level":"beach_19","simulated":false,"unsupported":["world 'beach'","synthesized levels","level rule 'boss'"]}` **exit 2**，不再抛异常、也不再可能假装跑过。`simulation_test` 新增两条断言（boss 关按规则名被拒、干净关清单为空）。 |
| C56 | high | 经济 | **已修（2026-11-25）**：`loot_binding.json` 补齐 1809 关的 `lootKey`/`presentTable`/`danger`/`noLoot`，13 张悬空表按「不发 + `presentTableMissing`」处理。原始缺口描述：掉落的**逐关绑定**缺失：`rewards_from_pack.json` 只有 per-key / per-table 计数，没有「关卡→LootConfig」「关卡→PresentTable」映射（`content/levels/*.json` 无 `loot` 字段，`content.pack` 里 `PresentTable` 命中 0）。后果：`lootKey` 一律 `default`（47 个 danger/whack/NoLoot 关按 default 结算）、present 表按世界名推导 + `egypt_normal_01` 回落、13 张悬空表 68 关拿不到午餐盒 |
| C57 | medium（已部分收口） | 数据（460.9） | **460.9 新增数据有人读、但消费者只接上一半**：`SuppressFlagZombie` 已建进 `patch_460_9.json` 与 `content/levels/*.json`（271 关）+ 引擎抑制与计数（t64/t65，CLI 有 `flagSuppressed`）；仍无消费者的是 `RlConfig`（Roguelike：ChoiceCount/EliteEvery/EliteChance/EliteDamageBonusPct…，17 字段只有数据）、`ThymedEventSchedule` 新增 3 组事件（timespaceechoes_0003/0004/0009，445 个关卡引用，只有数据）、`EffectElementReactionGroup_1536/_768/_Common` 三组美术（880,640 B 未解压进美术库）。这三样在复刻口径里应视为「未实现」而不是「已对齐」。 |
| C58 | low | 工具链确定性 | **已修（2026-11-25）**：三处戳全部改成内容寻址 —— `rewards.generated_stamp()` 现在把读到的 10 个包按「包名 + 字节」喂进 sha256，返回 `sha256:<16 hex>`；`spawn_offsets.generated_stamp(source)` 改成源表字节的 `sha256:<16 hex>`；`worlds.gate_timestamp()` 改名 `gate_stamp()`，返回 `pkg_2107_WorldData.json` 的 `sha256:<16 hex>`。此前它们分别取「包 mtime 最大值」「表 mtime」「表 mtime」，所以把同一份 OBB 重新解包（每次版本升级都会）就 churn 一遍产物。三条测试同步改断言（`^sha256:[0-9a-f]{16}$` + 与生成器函数互校），重生成后 `rewards…=sha256:30ec5ddd121d9bb8`、`spawn_offsets…=sha256:ad0fa20ca73aa95b`、`world_gates…=sha256:b1f61cd5ef86dedb`。 |
| C59 | low | 最新版对齐 | 核心库 460.11 新增的客户端玩法（`RogueModule` 肉鸽 155 条字符串、`SlotMachineModule`、`AciditySubsystem`、`VoidDragonNasaSubsystem`）在 460.9 数据包里**没有对应数据**（0 命中），属「有实现无数据」；我们的复刻只到 460.9 数据 + 460.1 行为，不反推这些玩法。元素反应与 `GridItemIceHole/FireWall` 的数据在包里但未编译未接线。 |
| C55 | medium | 内容数据 | **已取证（t56）**：`egypt_74` 5 条保护目标落在 3 个格子、`mustProtectCount=4`，但它在引擎里是**零容错而非必输**（判负只在植物死亡路径）。全库 5 关 `must > 去重格子`、11 关 `placed < must`，其中 6 关 `placed==0` 保护判定空转 → t58 加 `protect_capacity_shortfall` 事件。另：`extract_protect` 只取第一个模块（`lostcity_46` 少 7 株，t57 修）、`failWhenProtectedPlantDies=true` 是客户端默认值（加标注） |
| C53 | high | 内容管线 | **已修**（T53）：`minecarts` / `rail` / `vasebreaker` 三个标记已写进 `tools/obb_build_content_v2.py` 的派生逻辑并写回 content —— vasebreaker 45→**47**（补 `pirate_41`、`plantagenet_18`）、minecarts 10→**190**、rail 10→**192**；`--content-report` 的 `mismatches: none`，201 个关卡文件只改了 `extra` 与这三键（+1112/−257）。派生只取 functional 证据（`RailcartProperties` 有 Column/Row 或 `DangerRoomRailcartDesigner` 有 BaseRailcartCount/Layouts），7 个 kongfu 误标已撤、189 关补标。红测试 `test_removing_the_derivation_makes_the_content_stale` 证明摘掉派生后盘上立刻对不上 |
| C10/C33/C34 | low | — | 诊断/门禁/定位声明 | S8 |

---

| C60 | medium | 工具链确定性 | **已修（2026-11-25）**：根因是 `Path.write_text()` 在 Windows 把 `\n` 翻成 `\r\n`，所以 `bosses.py:546/937`、`projectiles.py:701/1000`、`engine_smoke.py:169`、`parity_report.py:776`、`worlds.py:503` 写出的产物是 CRLF，而 `--check` 逐字节比对 → 干净检出（`core.autocrlf=true`）也会闪红。五处全部改成 `write_bytes(...encode("utf-8"))`，7 个 CRLF 产物重生成或归一为 LF（`bosses_from_pack.json`、`boss_report.md`、`engine_smoke.json`、`projectiles_from_pack.json`、`projectile_report.md`、`world_diff.md`、`docs/reviews/2026-11-21-pause.md`），并新增 `tools/tests/test_newlines.py` 三条守卫（生成 JSON / 生成 MD / review MD 一律不许出现 CRLF）。修后 `--check` 全部 exit 0，引擎冒烟 32 场景与基线 **0 差异**（`engine_smoke.json` 换行变化不影响哈希）。 |
## 4. 未来计划（S5 收尾 → S9）

### S5（进行中）：元素 / 养料 / 融合 / Boss 数据 + 运行时
- 已完成：融合 85 编译、Boss/养料/元素数据盘点。
- 进行中：`bosses_from_pack.json`（258 阶段 + 50 mech 坐标）、`plantfood_from_pack.json`（147/185/6）。
- 待做：`elements.json`（authored + 反应矩阵 + rationale）、运行时 `elements/plantfood/fusion/boss` 四个模块、`WorldOptions{elements,plantfood,fusion,boss}` 开关、关掉开关时 32 场景哈希不变（证明是加法）。
- 门禁：四模块各有确定性测试；Boss 三阶段切换一次性；养料持续 N tick 后复原；融合不重复消耗。

### S6：进度体系 + 世界地图 + 选卡（玩家流程闭环）
- 原生存档 schema（星章/钥匙/三星/奖励/商店持有/花园）+ 版本迁移；Python 存档可导入。
- 世界地图（26 世界 → gate/key 97 条门）、关卡选择、选卡界面（deck 41 株 + seed bank 槽位）、结算（阳光/星章/奖励）。
- 植物等级成长接 `pkg_2069`（325 条）。
- 门禁：从启动到打赢 `beach_23` 再回地图、重启后进度不丢；三份存档格式各一次迁移测试。

### S7：关卡玩法变体与地形
- `level.extra` 全量解析：boss 71 / vasebreaker 45 / minecarts 10 / night 1809 / special 45。
- Boss 运行时接 `bosses_from_pack.json`（258 阶段、召唤、Fire 动作）。
- 砸罐子、小游戏、无尽、矿车、传送门、潮汐/氧气（beach/modern 6×9 + 水下）。
- 门禁：每类变体至少 3 关跑通并与原版录像对照；`carnival_12` 等含跳跃僵尸关卡不再结构性不可胜。

### S8：音频、表现打磨、发布
- 音频子系统（BGM 21 首 OBB 还原曲 + 音效，SVorbis/WAV 解码，混音与音量设置）。
- 表现：死亡淡出/阴影/受击闪白/种植动画、粒子（爆炸/冰冻）、PopAnim 颜色精度提升（ASTC 解码或降级策略）。
- 发布：Windows 安装程序 + 便携包；macOS Universal 2 .app + DMG；首次启动向导（导入 Python 存档）。
- 门禁：无声→有声（至少 1 首 BGM + 6 类音效）、安装包在干净机器可跑、macOS 实测。

### S9（可选）：补齐名册与联网边界
- 1107 个 pack-only 僵尸 + 295 个 pack-only 植物 的名册补全（美术 + 定义），368 关未映射 stage 的接入，README 明确"不实现联网"。

---

## 5. 附录：复现命令

```powershell
# 内容编译与一致性
python tools/contentc/build_content.py --check
python tools/contentc/plant_family_inc.py --check
python tools/contentc/mapping.py            # id_mapping.csv
python tools/contentc/fusions.py            # fusions_from_pack.json (85)
python tools/contentc/s5scan.py --gaps      # 元素/养料/Boss 盘点
python tools/parity_report.py               # PARITY_MATRIX.md

# 构建与测试（必须用 ASCII 构建目录：中文父路径下全新 configure 会失败）
pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\status-a'
pwsh -File tools/build_native.ps1 -BuildDir 'C:\pvzbuild\status-d'
python -m unittest discover -s tools/tests -p 'test_*.py'

# 单关跑通 / 美术覆盖
build
ative\Release\PvZ2SHUTTLE.exe --run-level content frontyard_1 --pack native\generated\content.pack --seconds 240
build
ative\Release\PvZ2SHUTTLE.exe --art-audit content --pack native\generated\content.pack
```

**已知的"别再犯"清单**（历史错误，均已更正并在报告留痕）：
1. 融合"199 对"是把 `pkg_2083` 里 199 个带 objdata 的 object 当成对数，真实是 **85 对**。
2. `content/bosses.json` 的 HP 是等差数列合成值，**不是**原版数据。
3. `PvZ2SHUTTLE/assets/db/` 的 70 个 actor 来自线上 Cocos 构建（Gardendless 0.16.15），**不是** SHUTTLE OBB 素材；OBB 是 PopAnim，需要转换。
4. 关卡 JSON 无棋盘尺寸字段，6×9 只能从原版 `StageModule` 推导。
5. `check_all` 曾"先覆盖基线再比较"导致门禁自愈；现改为先比后写。

---

## 2.34 P0–P2 补齐轮（2026-11-25）

`docs/PROGRESS.md` 的 21 条按 P0/P1/P2 三档推进；本轮把其中能靠**数据 + 接线**完成的全部做完，
剩下的都是「原版没数据」或「需要新运行层」的硬骨头，逐条落在这里。

### 新增数据表（六份，均已进 `check_all`）

| 产物 | 尺寸 | 内容 | 门禁步骤 |
| --- | --- | --- | --- |
| `native/generated/vasebreaker.json` | 186,116 B | 砸罐子 **47 关** / 1435 罐（僵尸 788 / 植物 617 / 收集物 30），真实类名 `VaseBreakerPresetProperties`（46 条 / 46 包）；逐罐 row/col、逐罐 sun、`timeLimit` 原版**没有** → null + `unknowns`；`frontyard_166` 是无尽 | `vasebreaker --check`（21.9 s） |
| `native/generated/minigames.json` | 1,222,781 B | **813 关**挂玩法模块、20 kind（16 minigame + 4 variant）、1019 次；vasebreaker 47 / rail 196 / laststand 73 / beghouled 11 / whack 1 / joust 4 / conveyor 332 / tide 77 / protecttheplant 197 | `minigames --check`（36.5 s） |
| `native/generated/loot_binding.json` | 537,332 B | **1809 关**逐关绑定 `lootKey`(default 1762 / danger 13 / whack 1 / null 33)、`presentTable`(level 1635 / default 174)、悬空表 12 名 13 条 68 次引用 | `loot binding --check`（7.3 s） |
| `native/generated/metagame.json` | 730,277 B | 图鉴 植物 **167** + 僵尸 **428**（= 595；旧「169」多算了 `AlmanacDLHandler`/`HotUIAlmanacVerticalListProperties`）、花园掉落 65 + Zen 4/4 表 + 盆 12、任务 240（69 带 `CompletionAwards`）+ 每日 11、成就 53（**全 serverOnly**） | `metagame --check` |
| `native/generated/plant_playable.json` | 200,236 B | pack 名册 339 判可玩性：**293 可玩**（42 同名 + 251 新增候选）、**46 阻断**（缺成本 23 = null 2 + cost 0 21；缺美术 26；两者都缺 3） | `plant playable --check` |
| `native/generated/plant_levels.json` | 821,708 B | 权威表 `pkg_2069_PlantLevelStats`（325 行 / 323 株）→ **133 株可升级**，byLevelCount {1:190,2:36,3:20,4:5,10:68,15:1,20:3}；`levelXPNonMonotonic` 113、`ragged` 40；`PlantUpgrade*` objclass 全库 0 → 无通用升级表 | `plant levels --check` |

口径要点（都踩过坑，写下来免得重犯）：

- **vasebreaker**：任务书里的 `VaseBreakerModuleProperties` 全库 0 命中，真名是 `VaseBreakerPresetProperties`；
  「45 关」是 `extra.special` 口径，按 `VaseBreakerPresetProperties` 数是 **47 关**，与 content 的 `extra.vasebreaker` 双向一一对应。
- **minigames**：kind 只认 `LevelDefinition.Modules` 的别名（按参数对象统计会把 BowlingBulb 从 15 关虚报 27 关）；
  锚点与辅助模块要分离（Joust 只 4 关）；`ZombieChicken` 原版无模块 → `unknowns`。
- **loot_binding**：460.9 **没有 world 级午餐盒表**（`presentSource=world` 分支是真代码 + 单测，`unknowns[present-source-world-unused] count=0`）；
  26 个 NoLoot 关里 19 关仍声明午餐盒表；10 个 heian 关把 `egypt_normal_01` 填在 Shiny 槽（照抄不修正）。
- **metagame**：僵尸「有出场关卡」口径从 428/428 收到 **383/428**（植物 149/167）；成就全部 serverOnly，
  所以 `metagame.json` 只声明形状与文本，不声明可获取。
- **plant_levels**：`LevelCap>1` 直接用，否则取「最长 Values / 单调 LevelXP+1 / 非花费型 PlantTier / 非零 LevelCoins」
  的最大值，都没有 → 1（纯 max 会把 wallnut 算 40 层、potatomine 算 20 层）；`pkg_2072` 同名 377 行数值冲突
  （aquaweed hp 500 vs 300）只作旁证。

### 引擎接线（本轮真接上的）

| 项 | 语义 | 证据 |
| --- | --- | --- |
| `spawners.*` 七类 | grid / portal / storm / ground / dino / beach / fish 真入场；`--run-level` 出 `mechanicWired:[{kind,spawned}]`（`carnival_86` grid=6、`mausoleum_40` dino=2+storm=6）；`spider` 与 `fish.hermits` 保持 unknown（content 与 pack 都无对应实体） | 冒烟两条 hash 变化：`kongfu_1`、`beach_23`（tick 1536→1599） |
| `suppressFlagZombie` | 内核没有旗子僵尸实体，`flag` 只是波标记 + `director.cpp:38` 的 1.0 s 铺开窗口 → 丢标记 + 计数 + 发 `flag_wave_suppressed`；CLI `frontyard_75` → `"flagSuppressed":1` | 探针 `flagDropped` 恒 false → `mechanics test failed: each flag wave must be counted exactly once, got 0` |
| 保护容量 | `placed < must` 发 `protect_capacity_shortfall`；11 关欠容量（`lostcity_45` 2/8、`sky_46` 5/10、`egypt_74` 3/4…） | 探针把 `<` 改 `<=` → `mechanics test failed: an exact fit is not a shortfall` |
| 商店产物 | 六类（coins/gems/keys/costume/plantfood/setting）接进 `Progress` 并带回执 → **buyable 21 → 72**；`unmodelledCurrency` 仍 479 | 六条反向探针全红在「存档增量」断言；`ctest -R '^shop$'` 1/1 |
| 掉落产物 | 只有 **gem**（2 行 loot）与 **mower**（4 行）真能在一场战斗里发；`plant` 293 行是 `unlock_plant` 解锁不是种子包；`xp`/`trophy` 补了存储形状但今天无来源；445 行「发不出去」变成可数 `unlanded`（`137+438==575` 有测试钉） | 逐字节 `new bytes=518 / old bytes=518 / IDENTICAL` |
| 混音器 | `sampleAt` 相位线性插值（24k 相位 0.5、44.1k 0.91875 手算期望 ±1e-6）、voice 8→**16**、抢占按 (priority, 起播序)、`--music-volume`/`--sfx-volume`（缺省 -1 = 继承 master） | 探针 `audio test failed: sampleAt at phase 0.5 must interpolate to 0.5, got 0.000000` |

### 明确不做的（附理由，不再排期）

1. **植物名册 147 → 339 不可达**：147 条里只有 44 条与原版同名（另 1 条 `fireflerry` ↔ `firefly` 是改名同一植物，
   cost 225 / hp 2671 逐项相同），85 条是融合、14 条 Plantagenet、3 条自创（gatling/twinsunflower/umbrellaleaf）；
  **「147 ⊂ 339」不成立**，共享同一植物的只有 **45/147 = 30%**。并集 442 条会让 20 个写死 147/44/295 的用例同时红，
  且 102 条手工植物在原版没有任何行可对照。结论：**维持 147**，`plants_merge.py` 留作显式工具（幂等、冲突手工胜），
  新增候选走 `plant_playable.json`（293 / 46）。
2. **`spider` / `fish.fishes[]`**：content/zombies.json 55 条与 content.pack 1127 条都没有 spider 实体
   （只有 `ZombieGeneralZmechSpiderRainPhase*Action` 这类 boss 动作名），hermitcrab 同理 → 不凭动作名造实体。
3. **`rlConfig` / `thymeEvents` 无消费者**（C57 的一半）：前者缺 Roguelike 运行层（最小接线点 `flow.cpp:10`/`flow.cpp:59`），
   后者缺日历层 + 活动关卡池（30 条 / 445 引用 / 373 唯一 id，`content/levels` 命中 0；接线点 `worldmap.cpp:232`）。
4. **元素反应三组美术解不出**：`EffectElementReactionGroup_Common` 因 `Subgroup.base()` 只剥大写后缀而自成 base（无纹理页），
   唯一纹理页是 fmt160（1 B/texel），现解码器按 RGBA8 取 `w*h*4` → 用 fmt150 路径硬解排布正确但颜色是噪点。
   用途上它挂在 20 个关卡（`ElementReactionModule@CurrentLevel`），引擎按模块名取美术故 `popAnim: null`。

### 本轮新登记的缺陷

| 编号 | 级别 | 领域 | 内容 |
| --- | --- | --- | --- |
| C61 | medium | 美术 | 小写 `_Common` base 全库 **48 个，其中 46 个带纹理页、合计 61,345,792 B，索引命中 0** —— 含整个**亚特兰蒂斯**世界（`WorldMap_Atlantis` 15.0 MB、`Environment_Atlantis`、`Submarine_Atlantis`、`TideWave_Atlantis`）与宇宙植物线（PlantCosmicMushroom/Nut/Pea/VoidDragon/DarkMatterDragonfruit/Levitater/Cornucopia）。修 `Subgroup.base()` 认 `_common` 后 `bases_total` 预期 1087 → **1133**，45 个现有解码器就能吃（fmt162×27 / fmt151×11 / fmt161×6 / fmt150×1） |
| C62 | low | 经济 | `plant` 293 + `xp` 14 + `trophy` 18 等 438 行掉落「发不出去」不是实现缺口而是**数据缺口**：`first:`/`replay:` 行在客户端资产里没有关卡坐标（`content/levels/*.json` 的 extra grep `worldtrophy|unlock_plant|FirstReward` 命中 0），要真发得重建 OBB 侧绑定（形状类似 `loot_binding`） |
| C63 | low | 商店 | `{coins}`/`{gems}` 产物行出厂全是 gem/mint 计价（先被币种拒，只有夹具能走通）；开关型 setting 出厂 0 行；gem/mint 消费侧未开放 → `unmodelledCurrency` 保持 479 |
| C64 | low | 音频 | `playSfx(priority)` 形参就位但 `AudioRuntime` 一律传缺省 0，运行时等价「最早的先被砍」；分层（波次号角 > 命中 > 弹幕）要事件表带权重 |

### 一条被提到但**未复现**的问题

t76 报告 `worldmap_test` 报 `0xC0000005`。在静树门禁构建里直接跑 `build/desktop-gate/Release/worldmap_test.exe content`
→ `worldmap tests passed`、exit 0；desktop 38/38 全绿。判定为并行改窗期间的旧构建产物，未登记为缺陷。
