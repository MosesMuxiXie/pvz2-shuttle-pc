# S4 阶段计划：桌面视图接新内核 + 美术与卡组现实化

> 上游：`2026-11-20-full-native-replica.md`（总计划）、`s2-engine-kernel.md`、`s3-behaviour-families.md`
> 状态：S0–S3 已完成并验证；本阶段把"内核能跑"变成"人能玩"，并把美术/卡组的真实覆盖量摆到台面上。

## Goal

桌面端 `--play` 不再是写死四张卡的演示：它跑 `engine::World`，按关卡 `deck` 给卡、鼠标种植/铲除/收阳光，
渲染读 `snapshot()`；同时把 2 GB OBB 里的 DragonBones 美术能否取出、147 株卡组的实际覆盖写成可核对的产物。

## Architecture

```
content/levels/*.json ──┐
content/plants.json ────┼─→ Catalog(+content.pack, +board_sizes.json) ─→ engine::World ─→ snapshot()
native/generated/ ──────┘                                                        │
                                                                                 ▼
                                                              battle_view (SDL3) 绘制 + 输入
assets/db/<key>/  ← DragonBones（现有 70 个 actor；OBB 目标为 ANIM_* 子组）
native/generated/art_manifest.json ← 每个 id 是否已有可用模型（来源、骨架、动画名）
native/generated/deck_report.md   ← 26 世界 / 1809 关的 deck 覆盖现实
```

## Tech Stack

C++20 / CMake / SDL3 3.2.28 / SDL3_image / FreeType / nlohmann-json（版本与 SHA-256 见 `docs/PARITY_BASELINE.md`）；
Python 3.14 stdlib 工具链（`tools/contentc/`）；pyvz2 的 1BSR/RTON 解码器（`work/deps/`）用于 OBB 美术。

## Spec

- 视图只读 `engine::World`：不再 `#include "simulation.hpp"`（legacy `Battle` 仅留 `--simulate` 与 `simulation_test`）。
- 输入映射到内核 API：点卡 → 选卡；点格子 → `plant(type,row,col)`；右键/铲子 → `shovel`；点阳光 → `collect(id)`；空格暂停。
- 卡组来自关卡：`level.deck`（空则用世界默认 4 张），超过 8 张截断并记事件，绝不静默换人。
- 美术缺失不阻塞：没有 `assets/db/<key>` 的植物/僵尸退化成色块 + 名字，并在 HUD 角标计数。
- 所有新产物必须可复现：`content.pack`、`board_sizes.json`、`art_manifest.json`、`deck_report.md` 两次生成字节一致。

## Global Constraints

1. 60 Hz 唯一推进；视图不自己算战斗，只读 snapshot。
2. 任何数据缺口写进文档与产物，不造数、不静默兜底。
3. `native/src/engine/**` 的数值与族语义不在本阶段改动（除必要的新查询 API，需带测试）。
4. 不 commit / 不 push；不写 `content/**`（除非明确列为交付物）。
5. Windows 必验；macOS 仍需实机，不在本阶段声称支持。
6. 测试用 CTest + `tools/tests`（unittest），门禁统一走 `tools/check_all.ps1`。

## Review Focus

1. `--play` 是否真的能在一张真实关卡上完成"选卡→种植→收阳光→撑过一波"的完整闭环（录 hash + tick）。
2. legacy `Battle` 是否彻底退出桌面路径（`grep simulation.hpp native/src/battle_view.*` 应为空）。
3. 美术提取是否只增不改：`assets/db/` 既有目录字节不变，新目录来源可追溯（子组名 + 文件名）。
4. `deck_report.md` 的"缺美术"与"缺行为"是否与 `PARITY_MATRIX.md` 一致，冲突即失败。
5. 中文 HUD 在 720p/1080p/非 16:9 下不截断（截图留档）。

## 任务

### S4.0 桌面视图接引擎（wirer）

**Files**：`native/src/battle_view.hpp/.cpp`、`native/src/launcher.cpp`（若需入口）、`native/tests/battle_render_test.cpp`

- 用 `engine::World` 替换 `Battle`；`--battle-snapshot` 保留（截图回归），`--play` 改为真实交互。
- 卡槽从 `level().deck` 取，图标用 `ui/seedpacket.png` 切片（已有资产）；钱不足/冷却中/该格占用要拒绝并给 HUD 反馈。
- HUD：阳光、波次、剩余僵尸、卡组、暂停、胜负 —— 全部来自 `snapshot()` 字段。
- 交互冒烟：新增 `--play-script <json>`（复用 `engine/replay.hpp` 的脚本格式）跑一次固定操作序列并截图，写入 `native/generated/play_smoke.json`。

**Verification**：`pwsh -File tools/build_native.ps1 -BuildDir build/s4-wirer` → desktop 全绿（含 `battle_render`）；
`grep -R "simulation.hpp" native/src/battle_view.*` 无输出；`--play-script` 在 `frontyard_1` 上至少种 3 株、收 1 次阳光、进入第 2 波。

### S4.1 OBB 美术可行性（artifex）

**Files**：`tools/obb_art.py`（新）、`native/generated/art_manifest.json`（新）、`docs/reviews/2026-11-20-obb-art.md`（新）
**只写**：以上三处 + `PvZ2SHUTTLE/assets/db/` 下**新增**目录。

- 目标：从 `main.460.com.ea.game.pvz2_shu.obb`（1BSR v4，4310 子组）里定位 `ANIM_<PLANT|ZOMBIE>_*` 子组，
  解出 DragonBones 5.5 的 `skeleton.rton(atlas)` + `ptx` 纹理，转成与 `assets/db/` 相同布局
  （`skeleton.json`/`atlas.json`/`texture.png`/`meta.json`），按现有命名（`plants/SunflowerPLANT` 等）落盘。
- 参考实现：`work/obb_unpack.py`（已知问题：v4 名字字典解析对部分子组给出乱码；未压缩标志下 `data is None`）。
  允许重写名字解析，但**必须**在报告里写清与参考实现的差异和验证方式（同一子组的文件数、CRC、可读骨架数）。
- 时间盒：先只做 1 个子组（`ANIM_SUNFLOWER*` 或 `ANIM_PEASHOOTER*`）打通链路，报告体积/耗时，再决定全量。
- **若打不通**：交付 `docs/reviews/2026-11-20-obb-art.md`，写清卡在哪一步（子组定位/名字表/压缩标志/纹理格式）、
  已试过的方法与失败原文，`art_manifest.json` 只记录"已确认不可取"的 id 与原因，不动 `assets/db/`。

**Verification**：`python tools/obb_art.py --probe` 列子组与候选文件；`--one <subgroup>` 成功产出 4 件套；
`python -m unittest tools.tests.test_obb_art -v`（若有）；产物两次运行字节一致。

### S4.2 卡组覆盖报告（mapper）

**Files**：`tools/contentc/decks.py`（新）、`tools/tests/test_decks.py`（新）、`native/generated/deck_report.md`（新）

- 统计 26 世界 1809 关的 `deck`：每关几张、引用哪些植物、其中多少有行为族、多少有美术（读 `assets/db` 与 `MANIFEST.json`）。
- 输出按世界分组：关卡数、去重植物数、缺行为数（应为 0）、缺美术数（现状预计很大）、超 8 张的关卡清单。
- 报告必须能回答："要玩第 X 世界第 N 关，现在能看到几个真模型、几个色块。"

**Verification**：`test_decks.py` 断言 1809 关全部被统计、`deck` 为空的关卡有明确默认策略、报告含 26 行世界表；
两次生成字节一致；`python tools/contentc/decks.py --check` 退出码 0。

### S4.3 门禁与文档（队长）

- `tools/check_all.ps1` 增加 `obb art manifest` 与 `deck report` 步骤；矩阵新增"卡组覆盖"一行。
- `docs/PARITY_BASELINE.md` 增 S4 增量；`docs/NATIVE_PROGRESS.md` 增 S4 段；计划勾选；CHANGELOG 记一条。

## 门禁（阶段完成判据）

- [ ] 1. `grep -R "simulation.hpp" native/src/battle_view.*` 为空，desktop 测试全绿。
- [ ] 2. `--play-script` 在 `frontyard_1` 完成"选卡→种植→收阳光→进入第 2 波"，产物写 `native/generated/play_smoke.json`。
- [ ] 3. `art_manifest.json` 与 `deck_report.md` 存在、可复现、与矩阵不矛盾。
- [ ] 4. `tools/check_all.ps1 -Desktop` 退出码 0；Python 测试与 CTest 均无回归。
- [ ] 5. 文档三处（基线/进度/计划）如实记录仍缺项：147 株美术覆盖、Boss、元素/养料/融合/小游戏。

## 与后续阶段的接口

- S5（元素/养料/融合/Boss）读 `engine/world.hpp` 的服务函数；本阶段只新增查询 API，不改族语义。
- S6（世界地图/商店/进度）读 `native/generated/deck_report.md` 与 `PARITY_MATRIX.md` 决定"哪些内容先可玩"。
- 发布（S7）以本阶段的门禁为最低线：能选卡、能赢一关、有真实美术的关卡才进发行包。
