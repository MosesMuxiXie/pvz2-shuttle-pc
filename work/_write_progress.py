# -*- coding: utf-8 -*-
"""Write docs/PROGRESS.md (2026-11-25 fresh remaining-work + progress list)."""
import io
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "PROGRESS.md"

TEXT = """# 进度与剩余工作清单

> 生成时间：2026-11-25（静态快照，所有数字都能用文末命令复现）
> 口径：只写**实测**数字；推断的地方标「推断」。与 `docs/COMPLETENESS.md`（缺陷台账）配合看，
> 缺陷编号 C* 直接引用那边的行，这里不重复论证过程。

## 0. 一句话现状

**能玩、能通关、有声、有存档；数据对齐到最新 460.9；缺的是「玩法种类」和「表现层」，不是内容量。**

- 版本三元组：游戏 **26.11.1** / 数据 **460.9** / 核心库 **460.11**（`down.pvz2shuttle.cn/manifest.json`）。
  数据包已用官方 `.rsbpatch` 从 460.1 打到 460.9，两跳 MD5 与 manifest 逐字相同。
- 门禁（静树、严格模式）：`audit 27/27`、`Python 469`、`desktop 36/36`，三项 ledger 一致，
  `[ok] content, build, tests and parity are consistent`，**EXIT=0**。
- 32 场景冒烟固定基准，双跑零差异；`--flow` 已能「选关 → 战斗 → 结算 → 写档 → 下一关」闭环。

## 1. 完成度总表（按系统）

| 系统 | 完成度 | 有数据 | 已接线/可玩 | 主要缺口 |
| --- | ---: | ---: | ---: | --- |
| 数据包与内容编译 | **95%** | 2116 包 / 1809 关 / 26 世界 | 12 张主表全部编译 | 192 植物、1072 僵尸在客户端侧**没有行**（只有 pack 规则） |
| 引擎内核 | **80%** | — | 世界/波次/弹道/护甲/机制五类 | 植物等级成长（C6）、`support` 空实现（C11） |
| 战斗覆盖 | **70%** | 植物 339 / 僵尸 1127 / 弹道 602 / 护甲 102 | 植物 147、僵尸 55、弹道 593、护甲 91 | 可玩口径只有 41 植物 / 47 僵尸（deck 与波次实际引用） |
| 关卡机制 | **72%** | 1245 关带机制 | 903 关（传送带/初始植物/初始物件/墓碑/保护） | 剩 **342 关**：events 123、mutators 21、boardGrid 49 + 各种生成器 |
| 关卡变体玩法 | **0%** | 砸罐子 47 / 铁轨 192 / 小游戏 45 | — | 玩法本体全无（C27）：潮汐 60、传送门 130、风暴 119、蜘蛛雨 118、恐龙 93、鱼 26 |
| Boss | **90%** | 71 关 / 50 boss / 155 阶段 | 67 关能真正出场 | 4 关数据无 boss；表现层待 S8（C15） |
| 经济与掉落 | **60%** | 575 行掉落 / 585 商品 | 130 行掉落 + 21 件可购买 | 逐关绑定缺失（C56）、445 行 `reward_unmodelled`、商品产物只支持 `plant_id` |
| 元游戏与 UI | **65%** | 世界 26 / 门 97 / 商店 585 | 启动器、菜单、世界地图、选关、结算、拖动种植 | 图鉴、花园、设置、成就（数据 169/65/69 条）、商店 UI |
| 存档 | **75%** | — | 星章/金币/种子/购买/continue 指针，原子写 | 无版本迁移（字段只增不减的兼容策略未写死）；钥匙来源只有 `egypt_3` |
| 音频 | **85%** | 65 个音源 / 4487.955 s | 全部 65 解码，BGM/SFX/音量/淡入 | 8 voice、最近邻重采样、无独立音量滑杆 UI（C52） |
| 美术 | **70%** | 1087 个 base | 1085 提取成功 | 460.9 新增 3 组元素反应美术未提取（880,640 B）；`spawnOffset.y` 只有数据 |
| 工具链 | **90%** | — | `check_all` 双配置 + 树指纹 + 台账重写 | 并行编辑时仍会 `[inconclusive]`（C44，机制已缓解） |
| 发布（S7） | **0%** | — | — | `install()`、资源/存档查找、LICENSES、README、`package.ps1` |
| 联网（S8） | **0%** | — | — | 版本查询 / 公告拉取 |

按行加权（不含 S7/S8）约 **72%**；含发布与联网约 **64%**。

## 2. 剩余工作（按优先级）

### P0 — 影响「像不像原版」的核心缺口

| # | 事项 | 量化 | 现状证据 | 工作量 |
| --- | --- | --- | --- | --- |
| 1 | **关卡机制剩余 342 关** | events 123 / mutators 21 / boardGrid 49 / 生成器（grid 237、portal 130、storm 119、spider 118、ground 100、dino 93、beach 82、fish 26） | 矩阵「关卡机制」wired=903，`level_mechanics.json` 有全部字段；未命中发 `mechanic_unknown{kind,count}` | 大（分 2–3 轮） |
| 2 | **砸罐子 47 关玩法** | 47 关标记齐全 | 矩阵「砸罐子」wired=0 | 中 |
| 3 | **小游戏 45 关 + 关卡变体** | 45 special；潮汐/传送门/风暴等见 #1 | C27 | 大 |
| 4 | **植物/僵尸内容行只有 147/55** | 总量 339/1127 | 矩阵「植物」「僵尸」数据列；`id_mapping.csv` 已列 295/1107 无客户端 id | 大（要先做映射策略） |
| 5 | **`support` 族空实现** | 34 株 support | `native/src/engine/registry.cpp:347-349` 只有 `own()` | 中（C11） |

### P1 — 玩法与经济的完整度

| # | 事项 | 量化 | 现状证据 | 工作量 |
| --- | --- | --- | --- | --- |
| 6 | **铁轨/矿车玩法** | 192 关标记（minecarts 190） | 矩阵「铁轨」wired=0，`native/src` 零引用 `rail` | 中 |
| 7 | **逐关掉落绑定（C56）** | 47 关 danger/whack 落 default；13 张悬空表 / 68 关无午餐盒 | `rewards_from_pack.json` 只有 per-key 计数 | 小（数据）；中（补表） |
| 8 | **445 行掉落 `reward_unmodelled`** | 植物 293 / 强化 3 / pinata 18… | 引擎只发事件不发放 | 中 |
| 9 | **商品产物只有 `plant_id` 能落地** | 585 件里可买 21 件 | `shop.cpp` 的 payload 白名单 | 中（costume 447 / event 32 需要外观与事件系统） |
| 10 | **`RlConfig` / `ThymedEventSchedule` 无消费者** | 17 字段 / 3 组事件（445 关卡引用） | C57；`patch_460_9.json` 已建好 | 小–中 |
| 11 | **图鉴 / 花园 / 设置 / 成就** | Almanac 169 / Garden 65 / Quest 69 / PlayerSegmentRules 922 | 全无 UI 与模型 | 大 |
| 12 | **植物等级成长（C6）** | — | 全库零命中 | 中 |

### P2 — 表现、数据卫生、发布

| # | 事项 | 量化 | 现状证据 | 工作量 |
| --- | --- | --- | --- | --- |
| 13 | **460.9 新增 3 组元素反应美术** | `EffectElementReactionGroup_1536/_768/_Common` = 880,640 B | 美术索引仍是 1075→1085/1087 的 460.1 口径 | 小（重跑 `obb_art.py`） |
| 14 | **`spawnOffset.y` 只有数据** | 487 行、224 植物 | 渲染层未用 | 小 |
| 15 | **混音器打磨（C52）** | 8 voice / 最近邻 | `--volume` 与淡入已有 | 小 |
| 16 | **保护目标容量不足（C55）** | 11 关 `placed < must`，6 关 `placed==0` | 已有 `protect_capacity_shortfall` 事件，数据未修 | 小（改数据）/ 中（同格多株） |
| 17 | **旧 `simulation.cpp` 拒绝 rail/vase 等（C54）** | 1 处调用方 | `simulation.cpp:22-24` | 小 |
| 18 | **确定性戳（C58）** | 2 张表 `generatedAt` + 1 张 `generated` | 每次重生成 churn | 小 |
| 19 | **S7 打包** | 7 件事 + 4 条门禁 | `docs/superpowers/plans/2026-11-24-packaging.md` 未开工 | 中 |
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
| 美术提取 | `python tools/obb_art.py --reindex`（读 `PvZ2SHUTTLE/assets/db/shuttle/index.json` 的 `counts`） |
| 音频 | `build/native/Release/PvZ2SHUTTLE.exe --audio-audit ..\\..\\PvZ2SHUTTLE\\assets` |
| 缺陷台账 | `docs/COMPLETENESS.md` 第 3 节 C1–C59 |
"""

OUT.write_text(TEXT, encoding="utf-8")
print("wrote", OUT, OUT.stat().st_size)
