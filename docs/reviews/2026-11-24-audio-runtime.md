# 2026-11-24 音频运行时接线（T45）

T38 交付的是「能装载、能解码、能审计」的管线，屏幕上一声不响。这一轮把管线接到运行时：战斗按世界播 BGM，
`engine::World::events()` 里映射过的事件送 `playSfx`，菜单类界面播 `menu` / `sfx_click`，每个视图每帧 `pump()`。
截图路径（`--battle-snapshot` / `--menu --frames`）自动走 headless 静音，**接音频前后 PNG 逐字节相同**。

## 1. 接线点
| 文件 | 函数 | 做了什么 |
| --- | --- | --- |
| `native/src/audio/audio_runtime.hpp/.cpp` | `AudioRuntime`、`attachAudio` / `pumpAudio` / `consumeAudioEvents` 等进程级自由函数 | 把「catalog + 事件表 + 后端」包成一个对象；`live` / `muted` / `headless` 三种模式；counter 记账 |
| `native/src/battle_view.cpp` | `BattleScene` 构造、`reset()`、`advanceFrame()` | 构造时 `attachAudio(assetRoot, headless)` + `playAudioMusicForWorld(level_.world)`；`reset()` 清游标；`advanceFrame()` 每帧 `consumeAudioEvents(world_->events(), audioCursor_)` 再 `pumpAudio()` |
| `native/src/menu_view.cpp` | `runMainMenu` | 循环前 `attachAudio` + `playAudioMenuMusic()`；每帧 `pumpAudio()`；选中项变化或鼠标点击 → `playAudioClick()` |
| `native/src/worldmap_view.cpp` | `runWorldMapScreen` | 同上（选中变化 / 点击） |
| `native/src/level_select_view.cpp` | `runLevelSelect` | 同上（选中变化 / 点击） |
| `native/src/launcher.cpp` | `runLauncher` | `attachAudio(assetRoot, smokeTest)` + `playAudioMenuMusic()`；循环内 `pumpAudio()` |
| `native/src/main.cpp` | `main` / `wmain` | 命令行过滤 `--audio-off`（任何命令都接受），转成 `setAudioOff(true)` |

`AudioRuntime` 的三个模式：

* `live`：建后端（桌面构建是 SDL3，audit 构建是 no-op 桩）。有设备才真正发声。
* `muted`：`--audio-off`。**不建后端**，请求照样记账，`playSfx` 一次都不转发。
* `headless`：`--battle-snapshot`、`--menu --frames`、`--launcher-smoke` 这类不出窗口/不出声的路径。**不建后端**，
  与 `muted` 的唯一区别是语义（谁要求的静音）而不是行为。

`enabled() == (mode == live && backend != nullptr && backend->available())`：没有设备时 `live` 也是静默的，只是在
`status()` / `note()` 里说清原因，不假装播过。

## 2. 事件 → 音效

`EventMap::gameEvents()` 列出 `engine::World::events()` 的全部 40 个名字，22 个有线、18 个显式 null。
运行时用 `EventMap::soundForEngineEvent(name)` 查（T38 的 `soundFor` 只查 21 条抽象事件，不查这张表——这是本轮
补的方法）；查不到或表里是 null，一律计入 `eventsUnmapped` 并且**记进 `silentEvents()`**，不借用别的采样顶替。

本轮接的 11 类（任务要求）与引擎事件对应关系：

| 引擎事件 | 音效 |
| --- | --- |
| `planted` | `plant` |
| `shovelled` | `sfx_shovel` |
| `sun_collected` | `sun_collect` |
| `shot_fired` | `sfx_shoot` |
| `shot_hit` | `shoot_hit`（mp3，缺解码器时 fallback `sfx_shoot`） |
| `wave_spawn` | `sfx_wave` |
| `zombie_died` / `level_lost` | `sfx_die` |
| `level_won` | `victory` |
| `mower_triggered` | `sfx_wave` |
| `input_rejected` | `sfx_error` |

另接 `plant_fed`→`plant_sprout`、`sun_spawned`→`sfx_sun`、`boss_spawn`/`zombie_summon`→`zombie_groan`、
`armor_absorbed/blocked/broken`→`shoot_hit`、`boss_fire`→`sfx_shoot`、`boss_died`→`sfx_die`、
`time_budget_exceeded`/`action_unknown`→`sfx_error`。

**仍为 null 的 18 个**（音库里确实没有对应样本，点名而不是静默顶替）：
`armor_dropped`、`boss_action_unwired`、`boss_stage`、`boss_unavailable`、`explosion`、`fusion`、`input_late`、
`level_start`、`mower_spent`、`plant_died`、`plant_removed`、`projectile_unknown`、`projectile_variant_fallback`、
`wave_spawn_rejected`、`zombie_hop`、`zombie_removed`、`zombie_smash`、`zombie_steal`。

### 去重规则

一个 tick 内同一事件类型最多播一次，按 tick 号开/关一个 `tickTypes_` 集合：

```cpp
if (!tickOpen_ || tick != lastTick_) { lastTick_ = tick; tickOpen_ = true; tickTypes_.clear(); }
...
if (tickTypes_.count(name) != 0) { ++counters_.eventsDeduped; continue; }
tickTypes_.insert(name);
```

理由：豌豆射手一 tick 打 8 颗，混音器一共 8 个 voice（`AudioMixer::kMaxVoices`），400 发子弹会把号角、阳光和啃咬
全部挤掉。同一 tick 的第一发代表这一类，后面的计数进 `eventsDeduped`，可从 counter 看见丢了多少。

## 3. BGM

`AudioRuntime::playMusicForWorld(world)` 走 T38 的 `selectMusic()`：`<world>_loop` → `<world>_intro` →
`obb/MUSIC_*` 兜底（`MUSIC_` 优先于 `STARTUPMUSIC_`），命中哪首写进 `musicName()`。12 个世界（frontyard、egypt、
pirate、cowboy、dark、beach、future、lostcity、chinesegarden、losantosvice、lunarrainbowmarket、menu）在本机资产上
全部命中 `<world>_loop`，没有落到 obb 兜底。菜单/世界地图/选关/启动器播 `menu`。

## 4. 无设备降级证据

audit 构建（无 SDL）里后端是 `audio_backend_null.cpp` 的桩：

```
$ C:\pvzbuild\aud1\Release\audio_runtime_test.exe <assets> content native/generated/content.pack
audio runtime tests passed
```

同一条用例在 audit 构建里断言 `playSfxCalls == 0`（没有设备）且 `deviceAvailable() == false`；在桌面构建里同一条
断言变成 `playSfxCalls == 3`（有设备）——两个分支都由 `runtime.deviceAvailable()` 决定，测试不会因为构建配置
不同而假绿。

桌面构建里设备测试是真出声的一条，没有设备时它 `return 77` 并打印原因（CTest 记 SKIP，不算通过）：

```
$ C:\pvzbuild\aud-desk\Release\audio_runtime_device_test.exe <assets> content native/generated/content.pack
phase: catalog 1285 ms
phase: audio catalog 1292 ms
phase: backend 1478 ms
phase: music 2660 ms
phase: battle 5870 ms
device: live (SDL3 push-mode device (48 kHz float stereo))
music: frontyard_loop (starts 1)
events: seen 9 mapped 4 unmapped 1 deduped 4
pump: 133 calls, 146944 mixed frames, 4 sfx calls
audio runtime device test passed
```

`146944` 帧 ÷ 48000 Hz ≈ 3.06 s，与用例里「进战斗跑 3 秒」的设计一致：混音器确实把 PCM 交给了 SDL3 的流。
`phase:` 五行是这条用例自带的阶段计时，`music` 那段就是从 `playMusicForWorld` 到解码完成的时间。

## 5. 截图路径不开设备（逐字节回归）

接音频前先存了两张基线，接完用同一命令重跑并用 SHA-256 比对：

```
$ PvZ2SHUTTLE.exe --battle-snapshot content ..\..\PvZ2SHUTTLE\assets C:\pvzbuild\after\battle_after.bmp
battle_preview=ok
$ PvZ2SHUTTLE.exe --menu content --assets ..\..\PvZ2SHUTTLE\assets --snapshot C:\pvzbuild\after\menu_after.png --frames 2
{"choice":"worldmap"}

after    battle_after.bmp D56A3D6AA176CA8F55B7A8F3589272249028C7D101AFA03C1BBEC38123479A90
baseline battle_before.bmp D56A3D6AA176CA8F55B7A8F3589272249028C7D101AFA03C1BBEC38123479A90
after    menu_after.png    37F75744CC8472660B34998718F4339BEA9D38F7FDB39870635B13E3087AB7B1
baseline menu_before.png   37F75744CC8472660B34998718F4339BEA9D38F7FDB39870635B13E3087AB7B1
```

两张图与接音频前**完全一致**，且这两条命令的 stdout/stderr 里没有任何音频设备行——`headless` 模式下
`attachAudio` 干脆不建后端，SDL 音频子系统从未初始化。

显式 `--audio-off` 也是同一张图（同一份资产、同样两帧）：

```
$ PvZ2SHUTTLE.exe --audio-off --menu content --assets ..\..\PvZ2SHUTTLE\assets --snapshot C:\pvzbuild\after\menu_off.png --frames 2
{"choice":"worldmap"}
menu_off.png 37F75744CC8472660B34998718F4339BEA9D38F7FDB39870635B13E3087AB7B1
```

`--audio-off` 走同一条静音路径（`muted`），用例单独验证：

```
$ audio_runtime_test（testAmbientSwitch）
--audio-off must forward zero clicks / --audio-off still counts the click it dropped
```

## 6. 测试

| 用例 | 断言 | 构建 |
| --- | --- | --- |
| `audio`（T38） | 65 sounds / 26 bgm / 18 sfx / 60 解码 / 事件表 22 通 18 null | audit + desktop |
| `audio_runtime`（本轮） | tick 去重计数、muted/headless 转发 0 次、真实战斗 120 tick 逐 tick 对账、进程级 attach 复用与 `--audio-off` | audit + desktop |
| `audio_device`（本轮，桌面独占） | 进战斗 3 秒后 `backend()->mixedFrames() > 0`；无设备 `return 77` 并打印原因 | desktop |

`audio_runtime` 的真实战斗用例不信任实现：它自己用 `EventMap::soundForEngineEvent` 把 `world.events()` 重算一遍
`(tick, type)` 去重后的集合，再要求 `sfxRequests` 等于这个集合的大小、`playSfxCalls` 等于（有设备时的）
`sfxRequests`、`pumpCalls` 等于帧数、游标等于事件流长度。

验收：

```
$ pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\aud1'
100% tests passed, 0 tests failed out of 24
Built and tested: C:\pvzbuild\aud1\Release\PvZ2SHUTTLE.exe

$ pwsh -File tools/build_native.ps1 -BuildDir 'C:\pvzbuild\aud-desk'
100% tests passed, 0 tests failed out of 33
Built and tested: C:\pvzbuild\aud-desk\Release\PvZ2SHUTTLE.exe
```

## 7. 设备测试暴露的 BGM 解码问题（已修）

设备测试第一次跑要 109 秒，`phase: music` 一行占掉 83 秒。根因不在 SDL，而在 T38 的 OGG 解码循环：

```cpp
result.samples.reserve(result.samples.size() + produced * outChannels);  // 每帧一次
```

`reserve` 写在逐帧循环里、每次按「当前长度 + 这一帧」精确申请，于是每个 packet 都重分配整个缓冲：
`frontyard_loop` 有约 7000 帧、15 M 个 float，累计拷贝量是 O(n^2)。改成只在容量不够时按需要量翻倍预留：

```cpp
if (result.samples.capacity() < needed)
    result.samples.reserve(std::max(needed, result.samples.capacity() * 2));
```

同一台机器同一份资产：`phase: music` 83234 ms → 2660 ms（其中约 1.2 s 是解码、其余是 SDL 重采样到 48 kHz），
整条设备测试 109 s → 6 s。`probeAudioFile` 走的是 `decodeOgg<false>`（只数帧、不存样本），所以 T38 的 `audio` 用例和 `--audio-audit` 一直没暴露这个问题——
只有真正把 BGM 播出来才会踩到。

## 8. 反向探针（去重必须真的在起作用）

把 `consume()` 里的 `tickTypes_` 去重块整段删掉、重新构建后：

```
$ audio_runtime_test <assets> content native/generated/content.pack
audio runtime test failed: three (tick, type) pairs are mapped, saw 5
```

`pelletBurst()` 里 tick 10 有 3 发 `shot_fired`，去掉去重后 3 发全播、加上 tick 10 的 `shot_hit` 与 tick 11 的
`shot_fired` 一共 5 次请求。恢复去重块后同一条用例回到 `audio runtime tests passed`。

## 9. 已知限制

* **没有 mp3 解码器**：`shoot_hit`、`ui_open`、`ui_close`、`coin_drop`、`gem_spawn` 5 个 mp3 无法解码，
  `shoot_hit` / 界面的 mp3 走 `fallbackFor()` 换到 wav（`sfx_shoot` / `sfx_click`）。这是一条显式的降级路径，
  不是静默失败——`playedLog()` 里记的是最终真正播放的名字。
* **混音器只有 8 个 voice，固定 48 kHz 立体声**，重采样是最近邻（`AudioMixer::mix`）。够用，但不做插值。
* 本文只覆盖接线与降级；资产装载/事件表的数字见 `docs/reviews/2026-11-24-audio.md`（T38）。
