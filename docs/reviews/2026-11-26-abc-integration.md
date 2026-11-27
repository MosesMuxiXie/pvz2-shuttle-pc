# A/B/C 补齐轮接线台账（2026-11-26）

用户诉求（m09906）：把上一轮列出的 **A 玩法本体 / B 经济与元游戏 / C 表现层** 未完成项做掉，然后同步到 GitHub。
这份文档是**接线台账**：谁交了什么、接在哪、当前卡在哪。数字的权威来源仍是各产物与 `--check` 输出，这里只记「接线事实」。

## 1. 引擎与数据（按任务）

| 任务 | 交付 | 接线点 / 可数证据 |
| --- | --- | --- |
| A1 砸罐子（wirer） | `engine/vase.{hpp,cpp}`、`vase_test` 11 段 | `WorldOptions::vasebreaker` 缺省开；47 关里 46 关有罐表（`frontyard_166` 无 preset → 降级普通关并发 `vase_unavailable`）；`--run-level` 输出 `vasebreaker:{total,broke,plants,zombies,collectibles,sun}`；audit 36/36（`#30 vase Passed 2.29s`） |
| A2 铁轨（patcher） | `engine/rail.{hpp,cpp}`、`rail_test` 7 段 | `WorldOptions::rail` 缺省开；`cowboy_1 --seconds 20` → `{"carts":1,"hits":0,"movedCols":8}`；非铁路关无 `rail` 键；`level_mechanics.json` 里 0 行 rail，故走 content `extra.rail`（192 关，190 关有车） |
| A3 小游戏参数（geometer） | `minigame_rules.json` 41,496 B、23 例 | 20 种玩法 18 可玩 / 2 阻断（`column`、`invisighoul` objdata 全 `{}`） |
| A4a 逐关规则（geometer） | `level_extra_rules.json` 359,996 B、22 例 | 385 关带规则：boardGrid 49 / mutators 21 / night 187 / frost 64 / tide 60 / strength 60 |
| A6 可玩性底账（geometer） | `level_playability.json` 1,394,571 B、23 例 | `playable=1340 dataOnly=454 minigame=16 inEngine=1225`；工单排序 night 187 → spider 118 → … |
| A7 关卡徽标（analyst） | `level_badges.{hpp,cpp}` | `levelSelectJson` 增 `badges`（21 条 rank、846/1809 关有徽标）；`worldMapScreenJson` 增 `almanac/garden/clearedWorlds` |
| A9 机制取证（artifex） | `mechanic_entity_resolution.json` 20,343 B、17 例 | spider 23 个 `SpiderZombieName` 全命中 `pkg_2115`；fish 7 个生物全命中 `pkg_0013`；unscheduled 125 条是 orphan |
| B3 图鉴 / 花园（analyst） | `almanac_view.{hpp,cpp}`、`garden_view.{hpp,cpp}` | `renderAlmanacHeadless` / `renderGardenHeadless`；`--almanac`/`--garden`；截图 `docs/media/s6-*.png` |
| B4 成就 / 每日（auditor） | `achievements_view.{hpp,cpp}`、`daily_view.{hpp,cpp}` | 模型在 **`namespace pvz::meta`**；53 条成就全 serverOnly、daily 11 条 `open` 只认 `Disabled` |
| B5 商店屏（auditor） | `shop_layout.{hpp,cpp}`、`shop_view.{hpp,cpp}`、`shop_ui_test` 8 段 | `renderShopHeadless` / `runShop`；五页是划分不是过滤（72+100+469+10+6 = 585）；拒绝句 585/585 用真实 `purchase()` 对账 |
| B5 名册（mapper） | `content/plants.json` 409 行、`plant_blocked.json` 35 条 | `--content-report`：`plants=409 authored=147 pack=262 playable=304 blocked=35 conflicts=44` |
| B6 本地化（artifex） | `lawn_strings.json` 2,877,130 B、`loc.{hpp,cpp}` | 19,055 键；`ACHIEVE_ALL_IN_JEST_TITLE` → 向我开炮 |
| C1 美术归并（artifex） | `obb_art.py` 的 `Subgroup.base()` | `bases_total` 1087 → 1135、磁盘 +430,123,461 B、`--art-audit` 0 mismatch |
| C2 fmt160（artifex） | `_ptx_decode_fmt160()` | 两个 base 出 `texture_alpha.png`；**只有亮度没有颜色**（七种解释已排除） |
| C3 音频优先级 + 设置屏（sonic） | `kEventPriorities` 16 条、`settings_view.{hpp,cpp}` | `renderSettingsHeadless`；`Progress::audio`；探针 `shovelled 3→0` 打红 |

## 2. 队长接线（本轮改的文件）

| 文件 | 改动 |
| --- | --- |
| `native/src/menu_view.hpp` | `MenuChoice` 加 `shop`（共 9 项） |
| `native/src/menu_view.cpp` | 加「商店」行；`menuChoiceName` 加 `shop`；行几何 `kItemH 56→48`、`kItemStep 66→58`（132 + 8×58 + 48 = 644，footer 在 648） |
| `native/src/main.cpp` | 五屏 + 商店的 `#include`；`--help` 补 `--shop-screen`/`--menu`；`--almanac/--garden/--achievements/--daily/--settings/--shop-screen` 分派；`--menu` 循环里加 shop 与 settings 两支（都在关闭后重回菜单，且都会写档） |
| `native/CMakeLists.txt` | `pvz_launcher` 源列表补 `achievements_view.cpp`、`daily_view.cpp`、`settings_view.cpp`、`shop_layout.cpp`、`shop_view.cpp` |

**踩到的两个真问题**（都已修）：
1. `pvz::AchievementsModel` / `pvz::DailyModel` 不存在 —— 它们在 `pvz::meta`，`main.cpp` 里六个限定名全部改成 `pvz::meta::*`。
2. `LNK2019` 八处未解析：B4/C3 的测试是「直接编译 .cpp」的，`achievements_view.cpp`/`daily_view.cpp`/`settings_view.cpp` **从未进过 `pvz_launcher`**，而 `main.cpp` 已经调用它们 —— 补进源列表后链接通过。
3. 小项：`level_select_view.cpp` 用 `palette.dim`，但 A7 只往 `almanac_view`/`garden_view` 的调色板加了这个色。给 `level_select_view` 的 `Palette` 补 `dim = rgb(92, 104, 110)`。

## 3. 已知未完成（A/B/C 范围内）

- **A4b 引擎接线**：`level_extra_rules.json` 的 boardGrid/mutators/night/frost/tide/strength 还没有消费方（wirer 的 t88 在做 boardGrid + mutators）。
- **A5 保护同格叠加**（t89）：`egypt_74` 那 11 关的容量不足改成「同格多株」。
- **A9b 僵尸名册**（t105）：`content/zombies.json` 仍 55 条，spider/fish 的 30 个 id 需要补进去，引擎才可能生成它们。
- **B1 植物等级**（t90）：`plant_levels.json` 里的 133 株逐级数值还没接进战斗。
- **B2 掉落第二波**（t93）：`plant 293`/`cosmetic 22`/`coin 30` 的落地。
- **C4 `SpawnOffset.y`**（t92）：487 行的 y 偏移还没进落点与绘制。

## 4. 复现命令

```powershell
# 数据侧
python tools/contentc/level_playability.py --check
python tools/contentc/level_extra_rules.py --check
python tools/contentc/minigame_rules.py --check
python tools/contentc/plant_playable.py --check
python tools/contentc/loc.py --check

# 引擎侧（桌面构建才有 --menu / --shop-screen）
build\desktop-gate\Release\PvZ2SHUTTLE.exe --menu content --frames 2
build\desktop-gate\Release\PvZ2SHUTTLE.exe --shop-screen content --frames 2
build\desktop-gate\Release\PvZ2SHUTTLE.exe --run-level content --play-script beach_69 --seconds 30
```
