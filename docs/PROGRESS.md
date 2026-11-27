# 进度与剩余工作清单

> 生成时间：2026-11-25，A/B/C 补齐轮后刷新于 2026-11-27（静态快照，所有数字都能用文末命令复现）
> 口径：只写**实测**数字；推断的地方标「推断」。与 `docs/COMPLETENESS.md`（缺陷台账）配合看，
> 缺陷编号 C* 直接引用那边的行，这里不重复论证过程。

## 0. 一句话现状

**能玩、能通关、有声、有存档；数据对齐到最新 460.9；缺的是「玩法种类」和「表现层」，不是内容量。**

- 版本三元组：游戏 **26.11.1** / 数据 **460.9** / 核心库 **460.11**（`down.pvz2shuttle.cn/manifest.json`）。
  数据包已用官方 `.rsbpatch` 从 460.1 打到 460.9，两跳 MD5 与 manifest 逐字相同。
- 门禁（静树）：ctest `audit 38` / `desktop 54` 项、`Python 925`（`Ran 925 tests`，`OK`），三项 ledger 已按 2026-11-27 实测刷新；
  本轮最后一次完整跑门禁因中途改文件而 `[inconclusive]`，静树复跑见 `docs/PARITY_BASELINE.md`。
- **已进 git 并推送**（`master`，`github.com/MosesMuxiXie/pvz2-shuttle-pc`）：
  `dcf89cc` 客户端本体（3093 文件）→ `0e26524`/`3964ce1` 产物去绝对路径 →
  `e8f62cf`/`f35cef2`/`59ccee9` 干净 clone 的前置跳过 →
  `9d4d670` 确定性戳 → `460d105` content 统一 LF → `dcb4395` portable 尾段回溯。
  干净 clone 实测：不设 `PVZ2_OBB_DIR` → `Ran 630 / OK (skipped=399)`；
  设了 → `Ran 648 / OK (skipped=75)`。
- 32 场景冒烟固定基准，双跑零差异；`--flow` 已能「选关 → 战斗 → 结算 → 写档 → 下一关」闭环。

## 1. 完成度总表（按系统）

| 系统 | 完成度 | 有数据 | 已接线/可玩 | 主要缺口 |
| --- | ---: | ---: | ---: | --- |
| 数据包与内容编译 | **95%** | 2116 包 / 1809 关 / 26 世界 | 12 张主表全部编译 | 33 株 pack-only 植物、1072 僵尸在客户端侧**没有行**（只有 pack 规则）；名册已到 409（手工 147 + pack 派生 262） |
| 引擎内核 | **88%** | — | 世界/波次/弹道/护甲/机制/植物等级/铁轨/砸罐子七类 | `support` 空实现（C11）；spider 拍数与 fish 生物仍记 unknown |
| 战斗覆盖 | **78%** | 植物 339 / 僵尸 1127 / 弹道 602 / 护甲 102 | 植物 409（手工 147 + pack 262）、僵尸 **111**、弹道 593、护甲 91 | 可玩口径只有 41 植物 / 47 僵尸（deck 与波次实际引用）；僵尸侧仍有 1016 条无客户端行 |
| 关卡机制 | **86%** | 1245 关带机制 | 1157 关（传送带/初始植物/初始物件/墓碑/保护/潮汐/寒风/棋盘格/变异/初始植物同格叠加） | 剩 **293 关** unknown：spider 118（拍数无实体）、生成器 5 类 + 挑战包装 13 |
| 关卡变体玩法 | **55%** | 砸罐子 47 / 铁轨 192 / 小游戏 20 kind；`level_playability.json` 记 可玩 1340 / 仅数据 454 / 小游戏 16 / 两者 1 / 引擎可跑 1225 | 砸罐子 46/47 关可玩、铁轨 192 关（车体/碾压/掉落/车格种植）、小游戏参数 18/20 kind | 小游戏**玩法本体**只有砸罐子/铁轨/传送带/保护四种；laststand/beghouled/whack/joust 仍只有参数 |
| Boss | **90%** | 71 关 / 50 boss / 155 阶段 | 67 关能真正出场 | 4 关数据无 boss；表现层待 S8（C15） |
| 经济与掉落 | **78%** | 575 行掉落 / 585 商品 | 掉落 **315 行落地 / 123 行显式不落地**；商店 585 行分五页、**可购买 72** 且有全屏 UI（每行拒绝原因） | 123 行缺关卡坐标或客户端入口（C62/C63）；coin 30 行需显式开关 |
| 元游戏与 UI | **88%** | 世界 26 / 门 97 / 商店 585 / 图鉴 595 / 花园 65 / 成就 53 / 每日 11 | 启动器、**九项菜单**、世界地图（含角标）、选关（含徽标）、结算、拖动种植、图鉴、花园、成就、每日、设置、商店 | 无成就/每日的服务端结算（按设计）；无联网排行榜 |
| 存档 | **75%** | — | 星章/金币/种子/购买/continue 指针，原子写 | 无版本迁移（字段只增不减的兼容策略未写死）；钥匙来源只有 `egypt_3` |
| 音频 | **95%** | 65 个音源 / 4487.955 s | 全部 65 解码，BGM/SFX/音量/淡入、**16 voice + 抢占、线性插值、事件优先级、设置屏三滑杆并写档** | 无音频设备热插拔；`priority` 表是常量（事件不带权重） |
| 美术 | **85%** | 1135 个 base | 1134 提取成功；`_Common` 归并 +430,123,461 B 已进索引；fmt160 解出亮度面 | 元素反应**只有亮度没有颜色**（C61 后续）；`spawnOffset.y` 已进引擎 |
| 工具链 | **90%** | — | `check_all` 双配置 + 树指纹 + 台账重写 | 并行编辑时仍会 `[inconclusive]`（C44，机制已缓解） |
| 发布（S7） | **90%** | 20.9 MB zip + 四条冒烟 + 真实美术实拍 | 存档目录策略 | `install()`、`PVZ_ASSET_ROOT` 查找、LICENSES、README、`package.ps1` |
| 联网（S8） | **0%** | — | — | 版本查询 / 公告拉取 |

按行加权（不含 S7/S8）约 **81%**；含发布（S7 90%）与联网（S8 0%）约 **80%**。

## 2. 剩余工作（按优先级）

### P0 — 影响「像不像原版」的核心缺口

| # | 事项 | 量化 | 现状证据 | 工作量 |
| --- | --- | --- | --- | --- |
| 1 | **关卡机制剩余 293 关** | events 123（tide 60 / frost 64）/ mutators 21 / boardGrid 49 已接线；剩 spider 118（拍数无实体）+ 生成器 5 类 + 挑战包装 13 | `LevelMechanicsTable::withUnknown()` **446 → 293**；实体取证见 `mechanic_entity_resolution.json` | 中（spider 需要「空投 imp」实体） |
| 2 | ~~**砸罐子 47 关玩法**~~ ✅ 已完成 2026-11-26 | `engine/vase.{hpp,cpp}`、`World::breakVase`、`vase_test` 11 段 | **46/47 关可玩**（`frontyard_166` 无 preset → 降级并发 `vase_unavailable`） | 已完成（A1） |
| 3 | **小游戏玩法本体** | 20 kind / 813 关；参数表 18/20 可玩 | 只有砸罐子/铁轨/传送带/保护四种有本体；laststand/beghouled/whack/joust 只有参数（`minigame_rules.json`） | 大（每种一个模式） |
| 4 | **植物/僵尸内容行 409/55** | 总量 339/1127 | 名册 409 = 手工 147 + pack 派生 262（`--content-report`）；`plant_blocked.json` 仍留 33 株 pack-only；僵尸侧 1107 无客户端 id | 大（僵尸侧要先做映射策略） |
| 5 | **`support` 族空实现** | 34 株 support | `native/src/engine/registry.cpp:347-349` 只有 `own()` | 中（C11） |

### P1 — 玩法与经济的完整度

| # | 事项 | 量化 | 现状证据 | 工作量 |
| --- | --- | --- | --- | --- |
| 6 | ~~**铁轨/矿车玩法**~~ ✅ 已完成 2026-11-26 | `engine/rail.{hpp,cpp}`、`RailCartEntity`、`rail_test` 7 段 | `cowboy_1` → `rail:{carts:1,movedCols:8}`；192 关按 content `extra.rail` 出车 | 已完成（A2） |
| 7 | **逐关掉落绑定（C56）** | 47 关 danger/whack 落 default；13 张悬空表 / 68 关无午餐盒 | `rewards_from_pack.json` 只有 per-key 计数 | 小（数据）；中（补表） |
| 8 | ~~**445 行掉落 `reward_unmodelled`**~~ ✅ 已完成 2026-11-26 | 438 行 → **315 落地 / 123 显式不落地** | plant 293 行 → 244 株进 `unlockedPlants`、cosmetic 22 → 15 个 | 已完成（B2）；剩 123 行见 C62/C63 |
| 9 | **商品产物只有 `plant_id` 能落地** | 585 件里可买 **72** 件（`shop-payloads.md:48`：`buyable=72 unmodelledCurrency=479`） | `shop.cpp` 的 payload 白名单 | 中（costume 447 / event 32 需要外观与事件系统） |
| 10 | **`RlConfig` / `ThymedEventSchedule` 无消费者** | 17 字段 / 3 组事件（445 关卡引用） | C57；`patch_460_9.json` 已建好 | 小–中 |
| 11 | ~~**图鉴 / 花园 / 设置 / 成就 / 每日 / 商店**~~ ✅ 已完成 2026-11-26/27 | 图鉴 167+428 / 花园 65 / 成就 53 / 每日 11 / 商店 585 | 六屏 + 六条 CLI + 九项菜单全部接线；`metagame.json`、`shop_layout/shop_view` | 已完成（B3/B4/B5/C3） |
| 12 | ~~**植物等级成长（C6）**~~ ✅ 已完成 2026-11-26 | `plant_levels.json` 323 株 / 133 有梯子 | `plantStatsOf()` 单出口 + 身份守卫；**106 生效 / 20 被拒 / 7 pack-only** | 已完成（B1） |

### P2 — 表现、数据卫生、发布

| # | 事项 | 量化 | 现状证据 | 工作量 |
| --- | --- | --- | --- | --- |
| 13 | **460.9 新增 3 组元素反应美术** | `EffectElementReactionGroup_1536/_768/_Common` = 880,640 B | ✅ 2026-11-26 已重建美术索引：**bases_total 1135 / ok 1134 / failed 0 / skipped 1**（`assets/db/shuttle/index.json`） | 已完成（C61） |
| 14 | ~~**`spawnOffset.y` 只有数据**~~ ✅ 已接线 2026-11-27 | `engine/spawn_offsets.{hpp,cpp}`、`spawn_offset_test` | `--run-level` 出 `spawnOffsetApplied` | 已完成（C4） |
| 15 | ~~**混音器打磨（C52）**~~ ✅ 已完成 2026-11-26 | 16 voice + 抢占、线性插值、事件优先级 16 条 | 设置屏三滑杆写档；探针「铲子必须 rank 3」 | 已完成（C3） |
| 16 | ~~**保护目标容量不足（C55）**~~ ✅ 已完成 2026-11-26 | `kMaxProtectStack=8`、`requiredProtectedPlants()=min(sheet,placed)` | 11 关 `protectCapacityShortfall` 全部 false（`egypt_74` 5/4 也补齐） | 已完成（A5） |
| 17 | ~~**旧 `simulation.cpp` 拒绝 rail/vase 等（C54）**~~ ✅ 已做完 2026-11-25 | 新增 `Battle::unsupportedRules()`，`--simulate <content> [level]` 改为列出不支持的规则并 exit 2（`beach_19` → `world 'beach'`/`synthesized levels`/`level rule 'boss'`） | — | 已完成 |
| 18 | ~~**确定性戳（C58）**~~ ✅ 已做完 2026-11-25 | 三处戳改成 `sha256:<16 hex>` 内容戳（rewards 10 包 / spawn_offsets 源表 / world_gates WorldData） | — | 已完成 |
| 21 | ~~**产物换行归一（C60）**~~ ✅ 已做完 2026-11-25 | 5 处 `write_text` → `write_bytes`，7 个 CRLF 产物归一为 LF，新增 `tools/tests/test_newlines.py` 三条守卫 | — | 已完成 |
| 19 | **S7 打包** | 6/7 已落地（`install()` 树含 `content/`+`generated/`+`assets/ui`、静态 CRT、版本单一来源、`PVZ_ASSET_ROOT`→exe 同级→向上搜、LICENSES 自动生成、README 命令表、`tools/package.ps1` 20.8 MB zip + 四条无源码树冒烟全绿）；剩存档目录策略（仍要 `--progress` 显式路径） | `docs/PARITY_BASELINE.md` §打包；`docs/superpowers/plans/2026-11-24-packaging.md` | 中 |
| 20 | **S8 联网** | 版本查询 + 公告 | 未开工 | 中 |

## 3. 明确不做（有数据/有实现但不复刻）

- **元素反应运行时**：原版数据里没有元素字段（21 条空 objdata、`pkg_2073` 零 element、1809 关零 element 键），
  我们只保留 `authored` 可选层且默认关（§2.13）。
- **核心库 460.11 的肉鸽 / 老虎机 / 酸性 / 虚空龙（C59）**：460.9 数据包里 0 命中，属「有实现无数据」，
  不反推（`RogueModule` 155 条字符串、`SlotMachineModule`、`AciditySubsystem`、`VoidDragonNasaSubsystem`）。
- **mint / star 货币**：原版由服务器下发（§2.31），客户端只落地 coin。
- **联网对战 / 账号**：S9 范围，不在本轮。

## 4. 里程碑建议（顺序）

1. **M1 玩法补齐**：P0 #1–#3（机制 342 关 + 砸罐子 + 小游戏），做完矩阵「可玩」列才会实质上涨。
2. **M2 内容与家族**：P0 #4–#5（植物/僵尸内容行、support auras）。
3. **M3 经济收口**：P1 #6–#10（铁轨、逐关掉落、产物落地、460.9 新数据消费者）。
4. **M4 元游戏补屏**：P1 #11–#12（图鉴/花园/设置/成就、植物等级）。
5. **M5 发布**：P2 #13–#19（美术补齐 → 打包 → 门禁）。
6. **M6 联网**：P2 #20。

## 5. 门禁红线（改完必须能跑）

```powershell
# 全量（含内容重建、矩阵与台账刷新；只在静树跑）
pwsh -File tools/check_all.ps1 -AllowMatrixChange -UpdateLedger
# 严格（提交前；不接受 -Allow* 参数通过）
pwsh -File tools/check_all.ps1
# 快速（只编译 + 测试，不动内容）
pwsh -File tools/check_all.ps1 -NoContent
```

判定：`EXIT=0` 且三行 ledger 一致（`audit / python / desktop`）；
`[inconclusive]`（树中途被改）不算通过，必须静树重跑。
Python 套件里打印的 `FAIL: …` 是负向用例的期望文本，只看 `Ran N tests` 与退出码。

## 6. 数字来源（可复现）

| 数字 | 命令 |
| --- | --- |
| 门禁三项 | `pwsh -File tools/check_all.ps1`（末段 `== test ledger ==`） |
| 矩阵各行（总量/数据/接线） | `python tools/parity_report.py`，或直接读 `docs/PARITY_MATRIX.md` |
| 机制逐类关数 | `python -c "import json;d=json.load(open('native/generated/level_mechanics.json',encoding='utf-8'));print(d['counts'])"` |
| 460.9 差量 6 包 | `python tools/contentc/rebase_diff.py --old work/obb_packages_460_1 --new work/obb_packages` |
| 美术提取 | `python tools/obb_art.py --all --needle=`（脚本在工作区根 `tools/`，不在 repo 内）；数字读 `PvZ2SHUTTLE/assets/db/shuttle/index.json` 的 `counts` |
| 音频 | `build/native/Release/PvZ2SHUTTLE.exe --audio-audit ..\..\PvZ2SHUTTLE\assets` |
| 缺陷台账 | `docs/COMPLETENESS.md` 第 3 节 C1–C59 |
| 植物名册 / 可玩子集 | `python tools/obb_build_content_v2.py --content-report`（`plants=409 authored=147 pack=262 playable=304 blocked=35`）；`python tools/contentc/plant_playable.py --check` |
| 关卡可玩性 | `python -c "import json;d=json.load(open('native/generated/level_playability.json',encoding='utf-8'));print(d['counts'])"` |
| 新表尺寸 | `Get-ChildItem native/generated/*.json \| Select-Object Name,Length` |
