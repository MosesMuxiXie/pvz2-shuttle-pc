# T49 音频打磨：音量、BGM 交叉淡入、mp3 缺席处置

日期：2026-11-24 · 任务：t48（T49）· 成员：sonic
上游：T38（管线与 audit）、T45（运行时接线，已交付）

本轮只动 `native/src/audio/**`、`native/tests/audio_test.cpp`、`NOTICE.md` 与本文件。
`native/src/main.cpp` 与 `native/CMakeLists.txt` 不在本轮写作用域：CLI 的三行接线与 minimp3 的
构建归属见 §7「接线插入点」。minimp3 之所以能做到零 CMake 改动，是把它当作 `pvz_audio_core`
里 `audio_decode.cpp` 的私有实现头（单 TU 实现），third_party 的 include 目录此前已经在。

---

## 1. 结论

| 项 | 结果 |
| --- | --- |
| 音量 | `--volume <0..100>`（统一 master）+ `--mute-bgm` / `--mute-sfx`（两条总线独立静音）；混音器内部另有 music/sfx 两条总线音量，输出前统一 `master × bus × voice.gain × fade`。clamp 到 [0,1]，非法值有可读错误，解析失败时不动 argv |
| 交叉淡入 | `kMusicFadeSeconds = 0.75`（48000 Hz 下 36000 帧）。旧曲在与新曲并行的独立 voice 上淡出，新曲按同一包络淡入；`mixedFrames()` 只随 `mix()` 的请求帧数增长，与音量/淡入无关 |
| 5 个 mp3 | **采纳 vendored minimp3（CC0）**。实测证伪了「用 wav 兜底且听感一致」的前提（`ui_open` 5.578 s vs 兜底 `sfx_click` 0.050 s）；`--audio-audit` 的 `decoded` 因此 60 → 65 |
| 回归 | 两张 headless 截图 6 个哈希（含 `--audio-off`、`--volume 0`、`--volume 50 --mute-bgm --mute-sfx`）与接音频前逐字节相同；真设备跑通，pump 145 次 / 146432 混合帧，设备侧峰值 `volume 100 = 0.051850` vs `volume 0 = 0.000000` |
| 接线 | `main.cpp` 已由队长授权接线（`parseAudioOptions` + `applyAudioOptions` 替换手工过滤，帮助串加三条），CLI 四个开关实测生效，非法值 `exit 1` |
| 反向探针 | 抽掉音量乘子 → `audio test failed: master volume 0 must produce silence` |

---

## 2. 音量

### 2.1 为什么是「一个 master + 两条 mute」而不是「bgm/sfx 各一个音量」

- 玩家侧真正会用的旋钮只有一个（整体音量），而「想关掉音乐」「想关掉音效」是两个二元需求：
  一个 0..100 的 master 加两个开关，比三个滑杆少两个误操作面。
- 实现上仍然是两条独立总线（`musicBus`、`sfxBus`），所以将来要拆成两个滑杆只是加参数，
  不用改混音路径：`musicBus = master × (musicMuted ? 0 : musicVolume)`、
  `sfxBus = master × (sfxMuted ? 0 : sfxVolume)`（`native/src/audio/audio_mixer.cpp`）。
- 音量在**输出前**乘、在 clamp 之前乘，因此 0 就是真静音（不是「很小」），100 与改前的输出一致
  —— 这是截图哈希没有变化的直接原因。

### 2.2 代码位置

| 位置 | 内容 |
| --- | --- |
| `native/src/audio/audio_mixer.hpp/.cpp` | `setMasterVolume / setMusicVolume / setSfxVolume / setMusicMuted / setSfxMuted`，NaN 忽略、clamp [0,1]；`lastPeak()` 记录最近一次 `mix()` 的峰值 |
| `native/src/audio/audio_backend.hpp/.cpp`、`audio_backend_null.cpp` | 接口转发到 `mixer_`；无设备时同样记录峰值（`muted`/`headless` 不建后端） |
| `native/src/audio/audio_runtime.hpp/.cpp` | `AudioRuntime::setVolume(int percent)`（clamp 0..100 → `setMasterVolume(percent/100)`）、`volume()`、`setMusicMuted/setSfxMuted`；进程级 `AudioOptions{volume, muteMusic, muteSfx, off}`、`parseAudioOptions()`、`applyAudioOptions()`、`audioOptionUsage()` |

### 2.3 非法值（原文，`audio test` 里逐条断言）

```
--volume expects a number from 0 to 100, got an empty value
--volume expects a number from 0 to 100, got "abc"
--volume expects a number from 0 to 100, got "40x"
--volume must be between 0 and 100, got 101
--volume must be between 0 and 100, got -5
--volume expects a number from 0 to 100, got nothing
```

`std::from_chars` 严格解析，所以 `40x` 不会被当成 40。解析失败时 `args` **原样不动**，
调用方据此打印错误并 `return 1`（现有 `run()` 的 `catch (const std::exception&)` 之外，
接线点自己判断 `ok`，见 §7）。

### 2.4 音量真的乘进去了：实测

`audio test` 的输出（同一段 `sfx_shoot` 采样，48000 Hz 输出，512 帧）：

```
volume probe: peak(100)=0.249969 peak(0)=0.000000 ratio=0.000
volume probe: peak(50)=0.124985 (half of 0.249969)
```

- `--volume 0` 的峰值严格为 0，`--volume 50` 恰好是 100 的一半，说明乘子线性且真的作用在输出上。
- 这条数字由 `AudioMixer::lastPeak()` 给出，测的就是 `SDL_PutAudioStreamData` 之前的那块缓冲
  （`audio_backend.cpp` 的 `pump()` 里 `mixer_.mix()` → `SDL_PutAudioStreamData`），设备拿到的
  就是它，中间不再乘任何系数。

---

## 3. BGM 交叉淡入

- 常量：`AudioMixer::kMusicFadeSeconds = 0.75`、`kMusicFadeFrames = 36000`（48 kHz）。
  切世界/切界面都走 `playMusic()`，因此「进关卡、回菜单、换世界」共用一条淡入淡出路径。
- 算法：新曲进 slot 0，旧曲被搬到独立的 `fading_` voice，两条 voice 用同一线性包络
  （`t = (fadeElapsed_ + frame) / fadeSpan`，淡入取 `t`、淡出取 `1 - t`）逐帧渲染，
  所以两端增益在切换瞬间都是接近 0 的连续值，不存在硬切。
- 「同一首曲子重播」只更新 gain、不重启（避免关卡重开时循环卡顿）；只有真有东西要淡出时才淡入，
  首次起播立即满增益 —— 否则首帧静音会让「进入战斗立刻有 BGM」变成 0.75 s 后才响。
- `mixedFrames()` 与淡入无关：`mix()` 请求多少帧就累加多少帧（下面 `audio test` 里
  `mixed frames 36672 == requested 36672`），因此 T45 的 `pump` 帧数证据不受本条影响。

`audio test` 原文：

```
crossfade: 0.750 s (36000 frames), max sample step 0.0000070, end level 0.250000, mixed frames 36672 == requested 36672
```

- 两个常量电平 clip（0.5 与 0.25）交叉：淡出结束时输出回到 0.25，相邻样本最大步进 7e-6
  （远低于 1/32768 的 16-bit 量化步长，即听不到爆音）。

---

## 4. 五个 mp3：评估与决策

### 4.1 实测（判定依据，不是你猜的）

用 minimp3 直接解 5 个 mp3，并与事件表原本的 wav 兜底对照（`C:\pvzbuild\mp3probe\probe.exe`，
`cl /EHsc /O2 /std:c++20`）：

| 文件 | 格式 | 声道 | 采样率 | 帧数 | 时长 | 峰值 |
| --- | --- | --- | --- | --- | --- | --- |
| ui_open.mp3 | mp3 | 2 | 48000 | 267740 | 5.578 s | 0.9455 |
| ui_close.mp3 | mp3 | 2 | 48000 | 112149 | 2.336 s | 0.4804 |
| shoot_hit.mp3 | mp3 | 1 | 32000 | 47015 | 1.469 s | 0.3969 |
| coin_drop.mp3 | mp3 | 1 | 16000 | 6463 | 0.404 s | 0.1946 |
| gem_spawn.mp3 | mp3 | 1 | 24000 | 54031 | 2.251 s | 0.2615 |
| sfx_click.wav（兜底） | wav | 1 | 22050 | 1102 | 0.050 s | 0.3000 |
| sfx_shoot.wav（兜底） | wav | 1 | 22050 | 1984 | 0.090 s | 0.2500 |

结论：**「用 wav 兜底且听感一致」不成立**。`ui_open` 比 `sfx_click` 长 111 倍（5.578 s vs 0.050 s），
`shoot_hit` 比 `sfx_shoot` 长 16 倍且峰值高 59%：这不是同一类声音，换成 wav 等于把「开面板的
整段界面音」压成一个点击声。因此采纳 minimp3。

### 4.2 采纳方式

- `native/third_party/minimp3.h`、`minimp3_ex.h`（上游 master，2026-11-24 取回，文件顶部加了
  来源与 SHA-256 注释）、`minimp3.LICENSE`（CC0 1.0 全文）。
- 只有一个 TU 定义实现：`audio_decode.cpp` 里
  `#pragma warning(push, 0)` + `#define MINIMP3_IMPLEMENTATION` + `#define MINIMP3_FLOAT_OUTPUT`
  + `#include "minimp3_ex.h"`。**不需要新 CMake 目标**，也不需要写 `.c` 文件。
- 上游要求浮点输出时必须在包含实现前定义 `MINIMP3_FLOAT_OUTPUT`；这里就是这么写的，
  因此解码结果直接是 `float`，与 stb_vorbis 的输出同类型，共用下游的重采样/混音路径。
- `NOTICE.md` 已登记：`| minimp3（MP3 解码器…） | master（2026-11-24 取回） | CC0 1.0 Universal / Public Domain，见同目录 minimp3.LICENSE |`，
  并把「stb_vorbis.c 是唯一随仓库分发的第三方源码」一句改成同时点名 stb_vorbis 与 minimp3。

### 4.3 影响面（必须知道的两处数字变化）

- `--audio-audit` 的 `decoded`：**60 → 65**（65 个文件全部可解码），`seconds`：4475.916 → 4487.955。
  即 `{"bgm":26,"decoded":65,"deviceAvailable":…,"missing":[],"seconds":4487.955,"sfx":18,"sounds":65}`。
- T38 的报告 `docs/reviews/2026-11-24-audio.md` 里写的 `decoded 60/65`、「5 个 mp3 无解码器」
  已被本轮取代；那份报告是 T38 当时的真实状态，未回改（历史记录），以本文件为准。
- `audio_test` 里原有的两条断言按新行为更新（这不是「只加用例」，特此说明）：
  `probeAudioFile(mp3)` 不再报 `no vendored mp3 decoder`，改为 `testMp3()` 真解码；
  `audit.decoded == 60` 改为 `== 65`。

`audio test` 原文（mp3 段）：

```
mp3: ui_open      5.578 s,  267740 frames, 2 ch @48000 Hz
mp3: ui_close     2.336 s,  112149 frames, 2 ch @48000 Hz
mp3: shoot_hit    1.469 s,   47015 frames, 1 ch @32000 Hz
mp3: coin_drop    0.404 s,    6463 frames, 1 ch @16000 Hz
mp3: gem_spawn    2.251 s,   54031 frames, 1 ch @24000 Hz
mp3: fallbacks sfx_click 0.050 s, sfx_shoot 0.090 s -- not interchangeable with the mp3s above
```

---

## 5. 回归

### 5.1 headless 截图逐字节不变

四条命令（`C:\pvzbuild\pol-desk6\Release\PvZ2SHUTTLE.exe`）与 SHA-256，另加两条接音频前的基线图：

| 产物 | SHA-256 |
| --- | --- |
| `battle_final.bmp`（`--battle-snapshot`，pol-desk6） | `D56A3D6AA176CA8F55B7A8F3589272249028C7D101AFA03C1BBEC38123479A90` |
| `battle_final_off.bmp`（同上 + `--audio-off`） | `D56A3D6AA176CA8F55B7A8F3589272249028C7D101AFA03C1BBEC38123479A90` |
| `battle_before.bmp`（接音频前基线） | `D56A3D6AA176CA8F55B7A8F3589272249028C7D101AFA03C1BBEC38123479A90` |
| `menu_final.png`（`--menu … --frames 2`，pol-desk6） | `37F75744CC8472660B34998718F4339BEA9D38F7FDB39870635B13E3087AB7B1` |
| `menu_final_off.png`（同上 + `--audio-off`） | `37F75744CC8472660B34998718F4339BEA9D38F7FDB39870635B13E3087AB7B1` |
| `menu_before.png`（接音频前基线） | `37F75744CC8472660B34998718F4339BEA9D38F7FDB39870635B13E3087AB7B1` |

三条命令的 stdout/stderr 里没有任何音频设备行（headless 不建后端）：

```
battle_preview=ok                      (exit 0)
battle_preview=ok                      (exit 0, --audio-off)
{"choice":"worldmap"}                  (exit 0)
{"choice":"worldmap"}                  (exit 0, --audio-off)
```

### 5.2 真设备

`audio_runtime_device_test.exe <assets> content native\generated\content.pack` 原文：

```
phase: catalog 351 ms
phase: audio catalog 353 ms
phase: backend 386 ms
phase: music 682 ms
phase: battle 3845 ms
device: live (SDL3 push-mode device (48 kHz float stereo))
music: frontyard_loop (starts 1)
events: seen 9 mapped 4 unmapped 1 deduped 4
pump: 147 calls, 146432 mixed frames, 4 sfx calls
audio runtime device test passed
```

146432 / 48000 = 3.05 s，与「3 秒墙钟」相符；`music` 与 `pump` 两行说明新的音量/淡入路径
在真实设备上照常推进。（同一二进制在 ctest 里也是 `audio_device ... Passed 4.78 sec`。）

**授权后补的设备侧峰值**（队长 m01400 授权改 `audio_runtime_device_test.cpp`，同一二进制
`C:\pvzbuild\pol-desk8` 全新构建后单独跑出的原文，末尾多两行）：

```
phase: catalog 1418 ms
phase: audio catalog 1428 ms
phase: backend 1533 ms
phase: music 2310 ms
phase: battle 5754 ms
device: live (SDL3 push-mode device (48 kHz float stereo))
music: frontyard_loop (starts 1)
events: seen 9 mapped 4 unmapped 1 deduped 4
pump: 145 calls, 146432 mixed frames, 4 sfx calls
peak: volume 100 = 0.051850 (11776 frames), volume 0 = 0.000000 (23040 frames)
audio runtime device test passed
exit=0
```

括号里是那个 240 ms 窗口**新混出来的帧数**，所以 `volume 0 = 0.000000` 不是「读到上一次的
峰值」：窗口真的混了 23040 帧，峰值恰好是 0。`volume 100` 那个窗口只混了 11776 帧（进窗口时
设备队列还比较满），因此峰值 0.051850 只代表 `frontyard_loop` 循环中的一小段电平，不能用它
跟 §2.4 的常量电平探针（0.249969）比较。断言是 `loud > 0`、`silentFrames > loudFrames`、
`silent == 0`。

> §2.4 的 `peak(100)=0.249969` vs `peak(0)=0.000000` 是常量电平 clip 的受控探针；
> 上面这一行是真实 BGM + 真实设备链路的同性质证据。设备侧不再乘任何系数。

---

## 6. 反向探针

把 `native/src/audio/audio_mixer.cpp` 里 `render()` 的
`const float frameGain = scale * envelope;` 改成 `const float frameGain = envelope;`
（即去掉 `master × bus × gain`），重新干净构建后：

```
14/25 Test #14: audio ............................***Failed    0.29 sec
audio test failed: master volume 0 must produce silence
96% tests passed, 1 tests failed out of 25
The following tests FAILED:
	 14 - audio (Failed)
Errors while running CTest
```

同一轮 MSVC 还报了 `warning C4189: 'scale': local variable is initialized but not referenced`
——这就是探针改动的指纹。恢复源码（`audio_mixer.cpp` SHA-256
`429880CC063467BDD2306E7E2B047BDF14BF7A1EB780ED10CC971117C558F35A`）后重跑即绿。

---

## 7. 接线（`main.cpp`，队长 m01400 授权后已接线）

`parseAudioOptions` 有两个重载：`std::vector<std::string>&`（测试用）与
`std::vector<std::filesystem::path>&`（就是本程序的 argv 形态，非 ASCII 路径不会被 ANSI 码页破坏）。
`main.cpp` 里原来的 `--audio-off` 手工过滤循环（含 `#ifdef _WIN32` 的宽字符比较分支，12 行）
整段换成了下面这段（`native/src/main.cpp:641-655`，唯一改动点之二）：

```cpp
    std::vector<fs::path> args;
    args.reserve(static_cast<std::size_t>(argc));
    for (int i = 0; i < argc; ++i) args.emplace_back(argv[i]);
    const auto audioOptions = pvz::parseAudioOptions(args);                        // ① 剥掉四个开关
    if (!audioOptions.ok) {                                                        // ② 非法值 exit 1
        std::cerr << "error: " << audioOptions.error << '\n';
        return 1;
    }
    pvz::applyAudioOptions(audioOptions.options);                                   // ③ 存进进程级设置
    return run(args);
```

帮助串（`native/src/main.cpp:53`）在 `--audio-off` 之后新增三行：

```
  --volume <0..100>  master volume (0 is silent, default 100)
  --mute-bgm    silence the music bus
  --mute-sfx    silence the effect bus
```

- `--audio-off` 是 latch（`applyAudioOptions` 里 `gOptions.off = gOptions.off || gAudioOff`），
  后面的 `--volume` 不会把它解开 —— 这是「截图永远静音」这条不变量的保险。
- 改前 `git status --porcelain native/src/main.cpp` 为 `??`（整个 `native/` 未跟踪），
  `git diff --stat` 为空，文件 mtime 12:06:49 早于本次改动 —— 没有和 wirer 的半成品块打架，
  两处都是最小上下文替换。
- 帮助文本还可直接打印 `pvz::audioOptionUsage()`（本轮沿用了 `main.cpp` 里既有的长字面量风格，
  保持一致，没有替换成函数调用）。

### 7.1 四个开关的实测（`C:\pvzbuild\pol-desk8\Release\PvZ2SHUTTLE.exe`）

```
& $exe --battle-snapshot content <assets> battle_wired.bmp        -> battle_preview=ok   exit=0
& $exe --battle-snapshot content <assets> battle_wired_v0.bmp --volume 0
                                                                  -> battle_preview=ok   exit=0
& $exe --menu content --assets <assets> --snapshot menu_wired.png --frames 2
                                                                  -> {"choice":"worldmap"} exit=0
& $exe --menu ... --snapshot menu_wired_off.png  --frames 2 --audio-off
                                                                  -> {"choice":"worldmap"} exit=0
& $exe --menu ... --snapshot menu_wired_v50.png  --frames 2 --volume 50 --mute-bgm --mute-sfx
                                                                  -> {"choice":"worldmap"} exit=0
& $exe --battle-snapshot content <assets> battle_bad.bmp --volume 300
   stderr: error: --volume must be between 0 and 100, got 300        exit=1
& $exe --volume abc
   stderr: error: --volume expects a number from 0 to 100, got "abc" exit=1
```

六个哈希（新产物对基线值）：

```
D56A3D6AA176CA8F55B7A8F3589272249028C7D101AFA03C1BBEC38123479A90  battle_wired.bmp
D56A3D6AA176CA8F55B7A8F3589272249028C7D101AFA03C1BBEC38123479A90  battle_wired_v0.bmp
37F75744CC8472660B34998718F4339BEA9D38F7FDB39870635B13E3087AB7B1  menu_wired.png
37F75744CC8472660B34998718F4339BEA9D38F7FDB39870635B13E3087AB7B1  menu_wired_off.png
37F75744CC8472660B34998718F4339BEA9D38F7FDB39870635B13E3087AB7B1  menu_wired_v50.png
```

即：`--volume 0`、`--volume 50`、两个 mute、`--audio-off` 都不改变截图 —— 音频不参与绘制，
这正是 T45 定下的「audio must not affect the hash」不变量。

### 7.3 设备用例打印峰值（授权后已加，`native/tests/audio_runtime_device_test.cpp`）

```cpp
        const auto peakAtVolume = [&runtime](int volume, std::size_t& mixedFrames) {
            runtime.setVolume(volume);
            const auto until = std::chrono::steady_clock::now() + std::chrono::milliseconds(240);
            float peak = 0.0F;
            while (std::chrono::steady_clock::now() < until) {
                runtime.pump();
                peak = runtime.lastPeak();
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
            mixedFrames = runtime.backend() != nullptr ? runtime.backend()->mixedFrames() : 0;
            return peak;
        };
        std::size_t loudFrames = 0;
        const float loud = peakAtVolume(100, loudFrames);
        std::size_t silentFrames = 0;
        const float silent = peakAtVolume(0, silentFrames);
        runtime.setVolume(100);
        printf("peak: volume 100 = %.6f (%zu frames), volume 0 = %.6f (%zu frames)\n", loud,
               loudFrames - mixed, silent, silentFrames - mixed);
        check(loud > 0.0F, "volume 100 must leave a non-zero peak in the device buffer");
        check(silentFrames > loudFrames, "the volume 0 window must have mixed new frames");
        check(silent == 0.0F, "volume 0 must push silence to the device");
```

比原计划的三行多了两件事，都是为了不让「假绿」通过：每 10 ms pump 一次（`pump()` 是推流式的，
只在队列低于目标水位时才混，纯连续调用可能一次都没混到新帧），以及打印每个窗口真正新混出来的
帧数（`silentFrames > loudFrames` 才说明 0 音量那个读数不是 stale 的 `lastPeak()`）。
输出见 §5.2 的 `peak:` 行。

---

## 8. 测试清单

`audio_test` 的用例顺序（`native/tests/audio_test.cpp`）：

| 用例 | 覆盖 |
| --- | --- |
| `testCatalog` | 65 / 26 bgm / 18 sfx / 21 obb、source 分类（report vs scan）、缺文件计数 |
| `testEventMap` | 11 类事件、14 条引擎事件精确音效、18 条未接线、12 个世界的 BGM |
| `testWav` | WAV 头解析（PCM16/22050/1ch）、非 RIFF 报错 |
| `testOgg` | stb_vorbis 解码 + probe 一致性 |
| `testMp3` | 5 个 mp3 的时长/声道/帧数与 probe 一致性 + 兜底对照打印 |
| `testMixer` | gain/mute/mix 产出非静音 |
| `testVolume` | clamp、peak(100)/peak(50)/peak(0)、两条 bus 独立静音 |
| `testCrossfade` | 包络线性、无爆音、淡出终点、`mixedFrames` 不受影响 |
| `testAudioOptions` | 开关剥离、6 条错误原文、path 重载保非 ASCII 路径、应用到 runtime |
| `testAudit` | 恰好 8 键、65 解码、pack 交叉统计 |
| `testErrors` | 缺 `audio_report.json` / 缺目录 / ghost 清单 → exit 1 |

### 8.1 `audio test` 原文（摘要行）

```
catalog: 26 bgm, 18 sfx, 21 obb (65 sounds; 10 report, 34 scan)
event map: 40 engine events, 22 mapped, 18 unwired: armor_dropped, boss_action_unwired, boss_stage, boss_unavailable, explosion, fusion, input_late, level_start, mower_spent, plant_died, plant_removed, projectile_unknown, projectile_variant_fallback, wave_spawn_rejected, zombie_hop, zombie_removed, zombie_smash, zombie_steal
volume probe: peak(100)=0.249969 peak(0)=0.000000 ratio=0.000
volume probe: peak(50)=0.124985 (half of 0.249969)
crossfade: 0.750 s (36000 frames), max sample step 0.0000070, end level 0.250000, mixed frames 36672 == requested 36672
options: path argv keeps 日志\assets
audio tests passed
```

### 8.2 构建/测试

| 命令 | 结果 |
| --- | --- |
| `pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\pol4'` | `100% tests passed, 0 tests failed out of 25`（本轮音频改动齐全时的整仓绿；此后只清了 `audio_mixer.cpp` 的一条 `warning C4127`） |
| `pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\pol5'` | 全部目标编译通过；`audio` Passed 12.07 s、`audio_runtime` Passed 1.59 s、`cli_audio_audit` Passed 10.14 s；整仓 `85% tests passed, 4 tests failed out of 26` —— 红的是 `catalog` / `engine` / `s5_boss` / `mechanics`，是队友正在改的 S3 mechanics/gridItems 工作（见下） |
| `pwsh -File tools/build_native.ps1 -BuildDir 'C:\pvzbuild\pol-desk6'` | 全部目标编译通过（含 SDL3 静态库）；`audio_device` **Passed 4.78 s**；整仓 31/35，红的还是上面那四个非音频用例 |
| `pwsh -File tools/build_native.ps1 -BuildDir 'C:\pvzbuild\pol-desk'` | `100% tests passed, 0 tests failed out of 34`（本轮桌面整仓绿的那一次，此时 S3 mechanics 还没把 catalog/engine 弄红） |
| `pwsh -File tools/build_native.ps1 -AuditOnly -BuildDir 'C:\pvzbuild\pol6'` | 授权后两处改动落地后的全新审计构建：全部目标编译通过（`main.cpp` 的新接线一并编过）；`92% tests passed, 2 tests failed out of 26`，红 = `catalog` + `mechanics`（`mechanics test failed: levels with an unwired mechanic, got 868`，wirer t51 中间态）；`audio` / `audio_runtime` / `cli_audio_audit` 全 Passed |
| `pwsh -File tools/build_native.ps1 -BuildDir 'C:\pvzbuild\pol-desk8'` | 授权后两处改动的全新桌面构建（`pol-desk7` 那次撞上 wirer 保存中的 `native/src/engine/world.cpp(477)` / `world.hpp(154)` 的 `error C2065: 'unplacedProtectedPlants_': undeclared identifier`，重开目录后通过）：全部目标编译通过；`97% tests passed, 1 tests failed out of 35`，唯一红是 `catalog`；`audio` / `audio_runtime` / `audio_device` / `cli_audio_audit` 全 Passed，设备用例原文见 §5.2 |

并发红（不是音频路径引入）的原文：

```
24/26 Test #24: mechanics ........................***Failed    0.96 sec
mechanics test failed: levels that open with grid items, got 583
10/26 Test #10: engine ...........................***Failed    0.79 sec
engine test failed: the pack-only plant must be on the lawn
20/26 Test #20: s5_boss ..........................***Failed    1.30 sec
s5 boss test failed: --boss off must reproduce the pre-boss hash for beach_19, got 0xd19e8983839045d1 want 0x298107e37cabd608
```

`pol-desk3` / `pol-desk4` 期间还撞到过队友正在保存的 `native/src/engine/world.hpp`（`mechanics_`、
`gridItems_`、`conveyorCards_` 未声明，`error C2065`）与 `native/src/engine/mechanics.cpp`
（`error C2888: 'int pvz::engine::ProtectSpec::requiredSurvivors(void) const': symbol cannot be defined
within namespace 'anonymous-namespace'`）；两次都在对方保存完成后消失，与音频无关（我这一轮只改了
`native/src/audio/**`、`native/tests/audio_test.cpp`、`NOTICE.md`）。

---

## 9. 已知限制

1. ~~`main.cpp` 的三行接线未落盘~~ —— 队长 m01400 授权后已接线并实测（§7.1），四个开关
   在 `--battle-snapshot` / `--menu` 上都生效，非法值 `exit 1`。
2. ~~`audio_runtime_device_test.cpp` 没有打印设备侧峰值~~ —— 同一授权后已加（§7.3），原文在 §5.2。
3. BGM 交叉淡入只覆盖 `playMusic()` 这条路；`stopMusic()` 仍是立即停止（用于「退回主菜单后静音」）。
4. 淡入淡出是线性包络，不是等功率（-3 dB）曲线；两首曲子相位无关时听感差异可忽略，若将来出现
   「切换瞬间音量塌陷」再换成 `cos/sin` 曲线即可，只需改 `render()` 里的 envelope 一行。
5. mp3 解码走 float 输出，与 OGG 一样在混音器里做最近邻重采样；32 kHz/16 kHz 的 mp3 升到 48 kHz
   有轻微镜像（现有 WAV 兜底同样如此），未做带限插值。
6. 授权后的两处改动（`main.cpp`、`audio_runtime_device_test.cpp`）落地时整仓正在被 wirer 的 t51
   机制接线改动，`pol6`（audit）与 `pol-desk8`（desktop）都编过了全部音频目标、`audio` /
   `audio_runtime` / `audio_device` / `cli_audio_audit` 全 Passed，整仓各剩 1–2 条非音频红
   （`catalog` / `mechanics`，t51 中间态），按队长指示未为变绿改动音频代码。
