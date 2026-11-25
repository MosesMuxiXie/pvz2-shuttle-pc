# S3–S5 收口计划：战斗口径 / 元游戏界面 / 美术与音频

> 用户 m05312：「可以并继续，完成 S3-S5」。
> 阶段编号按 `2026-11-20-full-native-replica.md` 的总表：S3 = 战斗内容覆盖，S4 = 元游戏与界面，
> S5 = 美术与音频。（注意另有一套 s5-elements / s6-progress 的子文档编号，见总表头部的提醒。）


## 进展（2026-11-24 10:50，实测读数）

| 项目 | 状态 | 证据 |
| --- | --- | --- |
| S3 僵尸族缺口 | ✅ 交付 | 真实缺口 3 条（`football` / `garden_gargantuar` / `royal_chef_gargantuar`），已改 `gargantuar`；分布 walk 49 / jump 1 / gargantuar 5，`zgaps.py --check` exit 0 |
| S3 SpawnOffset.y | ✅ 数据 + 🟡 渲染未用 | `native/generated/spawn_offsets.json` 487 行 / 224 株 / `pxPerColumn 100` / `pxPerRow 116`；引擎是 2D 行列模型，纵向只影响美术 |
| S3 像素空间 | ✅ 修正 | `kPixelsPerColumn` 60 → **100**（`ArtCenter` 374 样本众数 + `kShotStartOffsetCols=0.35 = 35/100` 反证）；32 场景只 2 条变化 |
| S3 元素 | ⏸ 裁决不属原版 | 见 COMPLETENESS §2.13：21 条空 objdata、`pkg_2073` 零 element、1809 关零 element 键；作为 authored 可选层、默认关 |
| S4 主菜单 + 关卡列表 | ✅ 交付（t41/T39） | `--menu` → `{"choice":"worldmap"}`；`--level-select --world frontyard` → 175 关；desktop `menu_render`/`level_select` 各 ~2 s |
| S4 闭环 | ✅ 交付（t45/T46） | `--flow` 连跑两轮：`beach_23 won tick 1597 stars 2` → `beach_24 lost tick 8038`，`lastLevel` 推进；探针「首个未通关→第一关」能被 `flow_test` 红出 |
| S4 拖动种植 | ⬜ 未做 | 现在点击种植是「先选卡再点格」，没有按住拖动连续种植 |
| S5 ASTC 美术 | ✅ 交付（t42） | `index.json` ok 1075 → **1085**；12 条失败里只有 10 条是 ASTC（`CREDITS` 是 JSON、`UI_ALWAYSLOADED` 声明 4096² 而流只有 2048²，都不修） |
| S5 多页/mip | ✅ 检测 + 决策不实现 | 11 个 base / 281 个 part；`PLANTMANGOSTEEN` 是唯一真多页（52/97），验收样本 |
| S5 音频管线 | ✅ 交付（t38） | 65 sounds（26 bgm + 18 sfx + 21 obb）、60/65 解码、4475.916 s；事件 22 通 / 18 null；`--audio-audit` 一行 JSON |
| S5 音频运行时 | 🟡 进行中（t44） | 管线已能出声，但战斗/菜单尚未 `pump()` + `playSfx`，桌面版仍静音 |

### 本轮我（队长）自己改的

- `native/src/engine/world.cpp` / `projectile.cpp`：三个「只为表现层」的事件 `shot_fired` /
  `shot_hit` / `sun_spawned`（不进 hash），加 `World::emitEffect`。
- `native/src/engine/action_runner.cpp` / `registry.cpp`：`kPixelsPerColumn` 100；
  `engine_test.cpp` 三条期望跟改。
- `native/src/progress.{hpp,cpp}`：`Progress::lastLevel`（continue 指针），`foldAttempt` 里
  「赢输都记」；**首版把它写进 `seeds` 分支内**，被 wirer 在 `--flow` 联调时抓到
  （无 `seeds` 键的存档会静默丢 lastLevel），已移出并加「旧存档无 seeds」用例 + 反向探针。
- `native/tests/progress_test.cpp`：lastLevel 往返 + 旧存档读盘两条断言。
- `native/tests/audio_test.cpp`：`fopen(utf8)` → `std::ofstream(fs::path)`，否则门禁在中文父目录下
  根本跑不了这个用例（`cannot write the ghost manifest: …文档…`）。
- `tools/build_native.ps1`：新增 `-Clean`（`--clean-first`）；`tools/check_all.ps1` 的构建重试
  现在对 `test failed:` 也生效并带 `-Clean` —— 修「陈旧 .obj 让旧代码决定门禁」这类假红/假绿。
- `native/CMakeLists.txt`：`audio_device` TIMEOUT 300 → **600**（解码整库要 ~144 s，120 s 是继承
  来的默认值，会把「慢」判成「挂」）。
- `tools/tests/test_spawn_offsets.py`：把「文档永不出现 100×116」改成「文档与表一致」——
  旧断言是诚实的，但它断言的是「事实还没写下来」，现在写下来了，断言就该跟着变。
- `docs/COMPLETENESS.md`：新增 §2.25（像素空间 + SpawnOffset.y）与 §2.26（音频管线），
  缺陷 C49（像素空间，已修）/ C50（5 个 mp3 无解码器）/ C51（音频未接界面）。

## Goal

把三件事从「有数据 / 有模型 / 有一块视图」推进到「玩家能连续玩、能听见、能看见」：

1. **S3 战斗口径补齐**：内容侧 55 个僵尸里仍有 20 个没有行为族（只能通用 walk），
   弹道/阳光的 `SpawnOffset.y` 从未被使用（所有投射物与阳光都从格子中心水平飞出），
   元素运行时是可选项但没有任何数据驱动的反应表被消费。
2. **S4 元游戏链路**：现在只有启动器、战斗视图、世界地图三块，缺「主菜单 → 世界地图 → 关卡列表 →
   选卡 → 战斗 → 结算 → 回地图」的闭环；战斗里也只能点卡再点格子，没有拖动种植。
3. **S5 美术与音频**：美术已有 1075/1087 base（12 个 ASTC 未解，C40），但**音频是 0%**：
   `native/src` 内没有任何 `SDL_OpenAudio`/`SDL_AudioStream` 调用，67 个音频文件（26 首世界 BGM +
   18 个 sfx + `obb/` 22 首 OBB 还原曲）从未被播放过。

## Architecture

- 音频拆两层：`native/src/audio/` 里放**与 SDL 无关**的 `AudioCatalog`（把 `assets/audio/audio_report.json`
  与 `obb/durations.json` 读成 `Sound{name,file,format,seconds,bytes}`）与 `AudioEventMap`
  （事件名 → 音效名），桌面侧的 `audio_backend.cpp` 才碰 SDL3 设备；这样 audit 构建也能测解析与映射。
- 界面按「一屏一个 `run*Screen()`」的既有形状扩展：`runMainMenu()`、`runLevelSelect()`，
  与 `runWorldMapScreen()`、`runBattlePreview()` 并列，CLI 各有一条 `--menu` / `--level-select`。
- 战斗交互补拖动：`battle_view` 的输入层增加 drag 状态机（按下在卡上 → 移动 → 抬在格子上），
  与既有点击种植共存；不改 `engine::World` 的输入语义。

## Tech Stack

C++20 / CMake / CTest / SDL3 3.2.x（音频用 `SDL_AudioStream` + 内置 WAV 解码；OGG 用 vendored
`stb_vorbis`，许可证已随项目 NOTICE 记录）、nlohmann/json、FreeType、Python 3（数据侧）、PowerShell 门禁。

## Global Constraints

- 60Hz 唯一推进；音频不得影响 `engine::World` 的事件哈希（声音是表现层，不进 hash）。
- 任何新资产或新数值必须可追溯：要么来自 pack 表（写来源），要么标 `authored` 并在文档里说明。
- 不 commit / 不 push；所有新文件写在仓库内，构建目录一律 ASCII 路径（`C:\pvzbuild\...`）。
- 门禁只认干净构建：`-BuildDir` 每次用新目录，改完源文件不许复用旧 build 目录下结论。
- 中文路径必须能用：新代码的字符串一律不假设 ANSI（`/utf-8` + `std::filesystem::path`）。
- 音频在无声卡/无设备的环境必须能降级（`--audio-audit` 只解码不设备），不能因缺设备崩。

## Review Focus

1. **音频是否真的发声**：不能只报「加载成功」。要求 `--audio-audit` 给出每个文件的解码后帧数与时长，
   且桌面构建里有一条「播放 200ms 后 `SDL_GetAudioStreamQueued` 归零」的实测（或在 CI 无设备时明确标 skip）。
2. **事件映射是否有遗漏**：pack 里 `ProjectileLaunchSound`/`AudioGroups` 的音效名要与 `audio_report.json`
   交叉，命中率写数字；未命中的事件要列名单，不许静默丢弃。
3. **界面链路是否闭环**：主菜单 → 世界地图 → 关卡列表 → 战斗 → 结算 → 回世界地图，每一步都要有 CLI 级证据。
4. **拖动种植不破坏既有输入**：既有的「点卡 → 点格子」必须仍可用，并有用例断言两条路径结果一致。
5. **S3 口径不臆造**：20 个僵尸的族归属要么有 pack 证据（`ZombieClass`/动画名），要么标 `authored`；
   `SpawnOffset.y` 的换算必须写清像素→格子的依据。

## 任务

### T38 音频管线（sonic）
- `native/src/audio/audio_catalog.hpp/.cpp`：`Sound{name,file,format,seconds,bytes,source}`、
  `AudioCatalog::load(assetRoot)` 读 `audio/audio_report.json` 与 `audio/obb/durations.json`；
  缺文件抛 `audio catalog: <path>: <what>`。
- `native/src/audio/event_map.hpp/.cpp`：`AudioEventMap::load(packJson?)` 建「事件 → 音效名」表，
  覆盖 plant / shoot / hit / sun / wave / die / click / error / shovel / gameover / win 至少 11 类。
- `native/src/audio/audio_backend.cpp`（仅桌面）：SDL3 音频设备 + `SDL_AudioStream`；
  BGM 循环、sfx 混音、master/sfx 音量、静音；无设备时降级为 no-op 并置 `available=false`。
- CLI `--audio-audit <assets>`：一行 JSON `{sounds,bgm,sfx,decoded,seconds,missing[],deviceAvailable}`，exit 0/1。
- 测试 `native/tests/audio_test.cpp`：解析计数、事件映射覆盖、WAV 头解析、缺文件报错。

### T39 主菜单 + 关卡列表（wirer）
- `native/src/menu_view.{hpp,cpp}`：`--menu <content> [--progress] [--snapshot] [--frames]`，
  三项「继续游戏 / 世界地图 / 退出」，显示星章与钥匙。
- `native/src/level_select_view.{hpp,cpp}`：`--level-select <content> --world <id>`，
  按 `catalog.levels` 列该世界关卡（序号、星数、是否通关），Enter 返回选中关卡 id。
- 测试 `menu_render` / `level_select_render`：1280×720 PNG、两次相同、选中项文字非空。

### T40 战斗拖动种植（wirer，依赖 T39 不改同一文件即可并行）
- `battle_view.cpp` 输入层加 drag 状态机；`--play-script` 语义不变。
- 测试：拖放与点击两条路径在同一脚本下产生相同 hash。

### T41 20 个僵尸的行为族补齐（mapper）
- 输入：`content/zombies.json` 里 `behavior` 缺失的条目 + `native/generated/id_mapping.csv`。
- 证据：pack `ZombieClass` / `PopAnim` / 动画名；无证据者标 `authored` 并写理由。
- 产物 `native/generated/zombie_family_gaps.json` + 报告 + 测试；**如需改 `content/zombies.json` 单独批准**。

### T42 SpawnOffset.y 语义（geometer）
- 从 `pkg_2073` 的 `Actions.SpawnOffset{x,y}`、`pkg_2082` 的 `AttachedPAM/ImpactPAM` 与野外高度
  （`Height`/`ArtCenter`）推导「y 像素 = 多少格」的经验换算，产物 `native/generated/spawn_offsets.json`。
- 报告里必须给三个以上可验证样例（豌豆、玉米、阳光），并说明不确定项。

### T43 美术 ASTC 12 个 base（artifex，时间盒 1 轮）
- 目标：`native/generated` 之外的 `PvZ2SHUTTLE/assets/db/shuttle/` 补齐 12 个失败 base；
  若决定不写解码器，必须给出「不做的代价」清单（哪 12 个、影响哪些植物）。

## 门禁

1. `-AuditOnly -BuildDir C:\pvzbuild\s345a` → 全绿（预计 ≥ 24 用例）。
2. `-BuildDir C:\pvzbuild\s345d` → desktop 全绿（预计 ≥ 32 用例，含音频与两屏）。
3. `python -m unittest discover -s tools/tests -p 'test_*.py'` → 全绿（现 296，预计 ≥ 310）。
4. `python tools/engine_smoke.py` → 32 场景零差异（音频与界面不得改战斗数值）。
5. `tools/check_all.ps1 -NoContent` 严格模式 → EXIT=0。
6. `--audio-audit` 给出真实解码帧数；无设备环境明确 `deviceAvailable:false` 而不是崩。
7. 文档：`docs/COMPLETENESS.md` 新增音频与界面两节、`docs/PARITY_BASELINE.md` 增本轮增量、
   总计划 1.1 表把 S3/S4/S5 的状态改到位。
