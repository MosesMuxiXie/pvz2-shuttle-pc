# T85 — 音频优先级分级、设置屏与存档持久化

日期：2026-11-26
任务：t85（C3 音频优先级接线 + 设置屏）
改动范围：`native/src/audio/**`、`native/src/settings_view.{hpp,cpp}`、`native/src/progress.{hpp,cpp}`（只加 `audio` 段）、`native/tests/settings_test.cpp`、`native/tests/settings_render_test.cpp`、`native/tests/audio_test.cpp`（只加优先级用例）、`native/CMakeLists.txt`（只加两个测试目标）。

`native/src/main.cpp` 与 `native/src/menu_view.cpp` **一行未改**：设置屏的菜单入口与 `--settings` 分发由队长统一接线（写窗冲突，见 §6）。

## 1. 结论

| 交付项 | 状态 | 证据 |
| --- | --- | --- |
| 事件优先级分级（4 级，16 个引擎事件） | 完成 | §2 的表；`audio_test` 打印 `priority: 16 rows, 16 graded, …` |
| 级别真正到达混音器（不是只存在于表里） | 完成 | `AudioRuntime::lastSfxPriority()` + `testPriority` 的两条端到端断言 |
| 分级在满载时保住玩家声音 | 完成 | 池子塞满 16 发子弹声后 UI 声仍然在，music 不被抢 |
| 设置屏（主/音乐/音效 + 静音，←→ ±5、↑↓ 换行、M、Esc） | 完成（无菜单入口） | §4；`settings_test` 8 组 + `settings_render` 3 张 1280×720 图 |
| 存档 `audio` 段（缺段=缺省、旧档可读） | 完成 | §5；`settings_test` 的 `persistence` / `old saves` 两行 |
| 回归：截图不变、引擎哈希不变 | 完成 | §7；两张基线哈希逐字节相同 |
| 反向探针：把 `shovelled` 从 3 降到 0 | 完成，已还原 | §8 原文 |

## 2. 优先级分级表

表在 `native/src/audio/event_map.cpp`，声明在 `event_map.hpp`：

```cpp
struct SfxPriority { std::string_view event; int priority; };
extern const std::array<SfxPriority, 16> kEventPriorities;
```

| 级别 | 含义 | 事件 |
| --- | --- | --- |
| 3 | 玩家刚做了什么：答案不能被吞 | `shovelled`、`input_rejected`、`time_budget_exceeded`、`action_unknown` |
| 2 | 每波一次 / 每关一次：必须活过弹幕风暴 | `wave_spawn`、`level_won`、`level_lost`、`mower_triggered`、`boss_spawn`、`boss_died` |
| 1 | 命中与弹道：混音的主体，池满时先削它们 | `shot_fired`、`shot_hit`、`armor_absorbed`、`armor_blocked`、`armor_broken`、`boss_fire` |
| 0 | 未列出的引擎事件（`planted`、`zombie_died`、`sun_collected` 等） | 缺省级别，不写进表 |

16 条全部非零（3 级 4 条、2 级 6 条、1 级 6 条），远超「至少 12 个」，`audio_test` 断言 `graded >= 12` 并打印实际值。

`planted` 特意**不**入表：它是最频繁的事件之一，如果给它 1 级，弹幕风暴里它就会跟子弹声抢同一档，反而挤掉真正的命中反馈。缺省 0 意味着「谁都可以先被抢」，这正是种植音该有的地位。

## 3. 级别如何到达混音器（不是只写在表里）

三段贯通，缺一段就会「表里有级别、混音器看不见」：

1. `EventMap::priorityForEngineEvent(name)`（`event_map.cpp`）线性查表，未命中返回 0。
2. `AudioRuntime::consume()` 里 `start(sound, 1.0F, events_.priorityForEngineEvent(name))`；`start()` 把级别记进 `lastSfxPriority_` 再 `backend_->playSfx(sound, gain, priority)`；`playClick()` 固定 `3`（光标声是玩家直接要的，满载也不能吞）。
3. `AudioBackend::playSfx(sound, gain, priority)` 转发 `AudioMixer::playSfx(clip, gain, priority)`；抢占规则仍是 T70 定的「最小 priority → 同 priority 最早 started」，music 在 slot 0 永不被抢。

`lastSfxPriority()` 是专为这条链路加的观察口——否则测试只能证明「表里有 3」，证明不了「3 到了混音器」。

`audio_test` 的实测输出：

```
priority: 16 rows, 16 graded, shovelled=3 shot_hit=1 wave_spawn=2 planted=0, ui survives a full pool
```

其中最后一项是分级存在的理由：先塞满 16 个 `priority=1` 的子弹声，再播一个 `priority=3` 的 UI 声，断言 UI 声出现在 `activeSfxNames()` 里、池子仍是 16 个、music 名字没变。

## 4. 设置屏

### 4.1 结构

逻辑与渲染分离，逻辑部分零 SDL（`native/src/audio/audio_settings.hpp`，header-only，不进 `.cpp` 源表）：

- `SettingsRow { master, music, sfx }`、`kSettingsRowCount = 3`、`kSettingsStepPercent = 5`
- `SettingsState { AudioSettings audio; int row; value(); setValue(); }`
- `SettingsKey { up, down, left, right, mute, back, none }`
- `applySettingsKey(state, key) -> { state, changed, moved, closed }`
- `applyAudioSettings(AudioRuntime&, audio)` / `applyAudioSettingsProcess(audio)`（走 `ambientAudio()`，没有 runtime 就跳过）
- `audioSettingsOf(runtime, muted)`（反向读）、`settingsJsonLine(audio)`

渲染部分 `native/src/settings_view.{hpp,cpp}`：

```cpp
SettingsResult runSettingsScreen(const SettingsOptions&);   // 有窗口；headless = frames > 0
nlohmann::json renderSettingsHeadless(const std::filesystem::path& assetRoot, int frames,
                                      const std::filesystem::path& snapshot,
                                      const AudioSettings& start = {});
```

`renderSettingsHeadless` 就是给队长接线用的纯入口：给资源目录、帧数、出图路径，返回要打印的 JSON。它**不写存档**——写档归调用方（已有的 `saveProgress` 路径）。

### 4.2 交互

`←/→` 当前行 ±5（clamp 到 0..100，100 再按 +5 不算“变化”，不会假装有声）、`↑/↓` 换行并环绕、`M` 切换静音（不动三个百分比）、`Esc` 关闭。每一步都是立即生效：`applySettingsKey` 返回 `changed` 时立刻 `applyAudioSettingsProcess`，不需要“确认”。

### 4.3 实测

```
settings_default: 1280x720 {"master":100,"music":100,"muted":false,"sfx":100}
settings_custom: 1280x720 {"master":55,"music":20,"muted":true,"sfx":95}
settings_one_frame: 1280x720 {"master":100,"music":100,"muted":false,"sfx":100}
settings render tests passed
```

尺寸由 `IMG_Load` 读回来断言（不是“文件非空”），三张都是 1280×720；`frames = 0` 也至少画一帧，不会产出空文件。

**哈希依赖路径**：页脚会画出图路径（`截图：<path>`），所以不同输出目录的 PNG 哈希不同。判定确定性要在同一路径上跑两次 —— 实测两次同为

```
A8761D41E1A1F8ACEB51F0D28DF463407AD0172554ACC863E86B4AA445986E1F   settings_default.png  (C:\pvzbuild\settings-shot)
```

### 4.4 菜单入口（未做，交接）

`native/src/menu_view.cpp` 里是 `std::array<Item, 3>`（继续游戏 / 世界地图 / 退出），`native/tests/menu_render_test.cpp:102` 断言 `freshResult.items == 3`；而 `menu` 截图哈希（`37F75744…`）也是本轮验收项。插第 4 项会同时打破这两条（第 4 个框与页脚文字重叠），所以菜单项与 `--settings` 分发留给队长统一接线。需要动的地方是三行：

```cpp
// 1) menu_view.cpp：菜单项加一项，choice 映射到菜单枚举
// 2) main.cpp：解析 --settings <content> 后调用
const auto line = pvz::renderSettingsHeadless(assetRoot, frames, snapshot);
std::cout << line.dump() << '\n';
// 3) 想持久化就顺手 saveProgress(progressFile, progressWithAudio, now)
```

## 5. 存档 `audio` 段

`native/src/progress.hpp`：

```cpp
struct AudioSettings { int master = 100; int music = 100; int sfx = 100; bool muted = false; };
struct Progress { … std::map<std::string, Json> settings; AudioSettings audio; … };
```

单独一个成员而不是塞进 `settings` 映射：`settings` 是商店行的自由字典，键名由内容决定；把音量放进去，改一次商店行名就会把玩家的音量丢掉。

格式（`progressToJson`）：值不是缺省时写

```json
"audio": { "master": 45, "music": 30, "sfx": 90, "muted": true }
```

三条硬规则：

1. **缺段 = 缺省**：`parseProgress` 里 `find("audio")` 找不到就保持默认，旧档照常读。
2. **只在非缺省时写**：默认存档里不会长出 `"audio"` 键 —— 否则既有多份「存档字节不变」的断言会被无声改写。`settings_test` 直接断言 `dump()` 里没有 `"audio"`。
3. **坏段不致命**：`audio` 是数组而不是对象、或某一项类型不对，都退回缺省，`coins` 等其余字段照常读出。为了一个偏好设置丢掉全部星星是更坏的失败。

`settings_test` 的实测：

```
persistence: 45/30/90 muted round trips through saveProgress/loadProgress
old saves: no block -> 100/100/100, partial -> 20/100/100, array -> defaults
```

## 6. 与并行任务的写窗关系

- `native/src/main.cpp`、`native/src/menu_view.cpp`：**未改**（队长 m02009 明确不许改）。
- `native/src/settings_view.cpp` 只进 `settings_render_test` 目标，不进 `PvZ2SHUTTLE` 源列表，也不进 `pvz_launcher`，所以另外四个改 `main.cpp`/`menu_view.cpp` 的任务不会与它冲突。
- `native/CMakeLists.txt` 只加了两段测试注册（`settings`、`settings_render`），未动任何现有目标。

## 7. 回归

### 7.1 截图（`C:\pvzbuild\set3-desk\Release\PvZ2SHUTTLE.exe`）

```
battle.bmp D56A3D6AA176CA8F55B7A8F3589272249028C7D101AFA03C1BBEC38123479A90
menu.png   37F75744CC8472660B34998718F4339BEA9D38F7FDB39870635B13E3087AB7B1
```

与接音频前的基线逐字节相同；stdout 仍然只有 `battle_preview=ok` 和 `{"choice":"worldmap"}`。

### 7.2 `--audio-audit` 未变

```
{"bgm":26,"decoded":65,"deviceAvailable":false,"missing":[],"seconds":4487.955,"sfx":18,"sounds":65}
```

（`audio_test` 的 audit 断言里打印；数值与 T70 交付时一致。）

### 7.3 引擎哈希：同一份代码，音频开关不改变任何东西

三个与旧基线不同的场景分别跑三次（默认 / `--audio-off --volume 0` / `--volume 0 --music-volume 0 --sfx-volume 0`），三次 JSON 逐字相同：

| 场景 | 默认 | 关音频 | 零音量 | 相同 |
| --- | --- | --- | --- | --- |
| `kongfu_1` | `0x741d5fb1a7a7408f` | `0x741d5fb1a7a7408f` | `0x741d5fb1a7a7408f` | 是 |
| `beach_23` | `0x051da1aca051d8bf` | `0x051da1aca051d8bf` | `0x051da1aca051d8bf` | 是 |
| `cowboy_1` | `0xcb83dd8dcba537f5` | `0xcb83dd8dcba537f5` | `0xcb83dd8dcba537f5` | 是 |

更强的对照：`python tools/engine_smoke.py` 分别用**桌面构建**（SDL + 真音频设备）和**审计构建**（无 SDL，后端是 stub）各跑一遍 32 个场景：

```
0 differences over 32 scenarios (desktop SDL build vs audit no-SDL build)
```

一个完全没有音频设备的二进制和一个真出声的二进制算出同一批哈希 —— 音频对引擎是纯旁路。

### 7.4 与 11-25 旧基线的 3 处差异（不是音频）

`work/_smoke_now.json`（11-25 14:30）对比本轮 `work/_smoke_settings.json`，32 个场景里 3 个不同：

| 场景 | 旧基线 | 本轮 | 归因 |
| --- | --- | --- | --- |
| `world cowboy` | `0xeb036737659cbc46` | `0xcb83dd8dcba537f5` | 本轮输出里出现 `"rail":{"carts":1,"hits":2,"movedCols":8}` —— 铁轨机制（t81） |
| `kongfu_1 5x9` | `0xa9abd80e22754f26` | `0x741d5fb1a7a7408f` | 输出里 `mechanicWired":[{"kind":"spawners.portal","spawned":1}]` —— 关卡机制接线（t51 后续） |
| `beach_23 win` | tick 1536 / `0xed25b11f14b6682e` | tick 1599 / `0xb2a22229f25b92e6` | 罐子/初始植物逻辑（t80） |

三个场景的引擎代码本轮都没被本任务碰过；§7.3 的桌面/审计双跑 0 差异说明这些变化不可能来自音频。旧基线文件保留不动（它是别人的产物），本轮的输出写到 `work/_smoke_settings.json` 与 `work/_smoke_auditbuild.json`。

## 8. 反向探针

把 `native/src/audio/event_map.cpp` 的 `{"shovelled", 3}` 改成 `{"shovelled", 0}`，只重建 `audio_test`：

```
audio test failed: the shovel is a player action and must rank 3
[exit code: 1]
```

改回 `3`、`touch` 时间戳重建后：

```
errors: missing files make --audio-audit exit 1
audio tests passed
[exit code: 0]
```

还原后 `event_map.cpp` 的 SHA256：`C7A8A0B9B53190A2EC5D335A84E95C23EF54A0A791CC80622F66A01B7A5A5DCD`。

## 9. 构建与测试

### 9.1 审计构建（无 SDL）

```
pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\set3'
100% tests passed, 0 tests failed out of 34
Total Test time (real) =  61.62 sec
Built and tested: C:\pvzbuild\set3\Release\PvZ2SHUTTLE.exe
```

`settings` 在审计配置里也跑（无 SDL、无设备），说明设置模型与存档路径不依赖图形栈。

### 9.2 桌面构建

```
ctest -R '^(audio|audio_runtime|audio_device|cli_audio_audit|settings|settings_render)$'
1/6 Test  #5: cli_audio_audit ..................   Passed   17.17 sec
2/6 Test #14: audio ............................   Passed   22.09 sec
3/6 Test #15: audio_runtime ....................   Passed    5.96 sec
4/6 Test #16: settings .........................   Passed    0.61 sec
5/6 Test #34: audio_device .....................   Passed   15.58 sec
6/6 Test #49: settings_render ..................   Passed    3.50 sec
100% tests passed, 0 tests failed out of 6
```

六项全绿（含真设备用例 `audio_device`）。**整棵树的桌面构建本轮是红的**，红在别人的在写文件上：

```
native/tests/shop_ui_test.cpp(399,5): error C2653: 'sdl': is not a class or namespace name
native/src/shop_view.cpp(328,71): error C2065: 'SDLK_q_renamed_SDLK_Q': undeclared identifier
```

`shop_render_test` 因此编不过；`PvZ2SHUTTLE.exe`、`settings_render_test.exe` 与本任务相关的目标都已生成，上表的用例是在这份新构建里跑的。`SDLK_q_renamed_SDLK_Q` 这种标识符看起来是编辑器改名留下的，不在本任务作用域内。

### 9.3 逐条用例

```
settings_test:
defaults: {"master":100,"music":100,"muted":false,"sfx":100}
clamp: 900/-40/55 -> {100,0,55,muted}
keys: 100 +5 stays 100, 50 +5 = 55, rows wrap, mute keeps 70/60/50
immediate: peak 0.250000 -> 0.125000 at 50% -> 0.000000 at 0%, runtime keeps 35/40/45
mute: peak 0.25 -> 0.000000 -> 0.25, master kept at 1
persistence: 45/30/90 muted round trips through saveProgress/loadProgress
old saves: no block -> 100/100/100, partial -> 20/100/100, array -> defaults
json line: {"master":5,"music":50,"muted":true,"sfx":95}
settings tests passed
```

`audio_test` 只加了一组（`testPriority`），其余全部沿用；它的 printing 里与优先级相关的两行：

```
voices: kMaxVoices=16, steal order (lowest priority, then earliest start), music never stolen
priority: 16 rows, 16 graded, shovelled=3 shot_hit=1 wave_spawn=2 planted=0, ui survives a full pool
```

## 10. 已知限制

1. **菜单里还没有「设置」项**，`--settings` 也还没有分发（§4.4 的三行插入点）。本轮 `native/src/main.cpp`、`menu_view.cpp` 属于别人的写窗。
2. **mp3 事件仍走 wav 兜底**：`hit`/`ui_*`/`coin`/`gem` 的映射优先用 mp3，但 `sfx_shoot` / `sfx_click` 兜底是为了在解码器缺失时仍有声；本轮没改这条策略。
3. **设置屏的可访问性只到键盘**：鼠标点击行/滑块没做（菜单项接线时再补更合适）。
4. **`planted` 的 0 级是刻意的**（§2 末），如果后续觉得种植音太容易被吞，应该加的是「同优先级内更晚被抢」而不是把它提到 1 级。
5. `settings_render` 的 PNG 哈希依赖页脚里画出的输出路径（§4.3）；比对截图时要用同一路径，否则差异只是那一行字。
