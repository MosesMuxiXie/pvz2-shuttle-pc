# v26.10.1 前院第 1 关静态证据

使用 Craft Anything 0.6.0 对本地 APK 执行 `android-package-show`，确认包名 `com.ea.game.pvz2_shu`、版本 `26.10.1`、versionCode `460`。用 `native-strings-find` 定位 ARM64 `libPVZ2.so` 的波次和阳光属性，再用 Ghidra 12.1.4 核对属性绑定及默认值。库的 SHA-256 为 `3529dd6cdd3a3b92187cc8584c42903106f20083a43f6d6311713f43a4cff944`。地址均为 ELF 虚拟地址。当前 Windows 主机无可用 Android 模拟器和 ADB，以下结论基于静态核对。

| 项目 | 同版证据 | C++ 关卡 |
| --- | --- | --- |
| 开局阳光 | `LevelDefinition` 构造地址 `0x1b7f644` 将偏移 `0x90` 初始化为 50，注册点 `0x1b7d230` 将同一偏移绑定为 `StartingSun`。首关无覆盖，`AddBonusStartingSun` 默认允许额外加成。 | 使用 50 基础阳光。进度加成待实现。 |
| 落阳光 | OBB 包 `pkg_0234` 的 `DefaultSunDropper` 配置首发 2 秒、基础间隔 6 秒，另有随机范围、递增与上限。 | 采用 2 秒首发与 6 秒固定基础间隔。随机时序和增长待对照。 |
| 波次构成 | `pkg_1996_LevelDefinition.json` 中关卡为 `YourHouse 1`、`DayStage`。`WaveCount=6`、`FlagWaveInterval=6`，Wave1–6 有定义，Wave7–10 只有悬空引用。第五波额外掉落 1 份叶绿素。 | 转录六个有效波次，显式 1–5 行换算为 0–4，未指定的行用可重放的随机数。额外叶绿素当前只保留为数据。 |
| 波次间隔 | `WaveManagerProperties` 构造地址 `0x10f18cc` 默认首波倒计时 12 秒。初始化点 `0x10f8134` 设置普通下一波的 25–31 秒计时、旗帜波前 45 秒计时。`0x10f64e4` 起的分支根据 70–85% 的随机波次血量阈值提前刷波，最短间隔 4 秒。旗帜波还有 5 秒警告延迟。 | 首波 12 秒，后续暂以 25/45 秒基础值排程。随机波次计时、提前刷波及旗帜提示待复现。 |
| 选卡和僵尸 | `SeedBankProperties.SelectionMethod=chooser`，首关未固定卡组。`pkg_2112` 与 `pkg_2115` 可核对 `tutorial` 和 `tutorial_armor1` 的基础生命 190、移速 0.185，`pkg_0002` 中锥桶防具生命 370。 | 基于已有四张植物卡供玩家选择。映射到现有普通僵尸和路障僵尸定义，保留已知基础生命、移速与护甲值。 |

`content/native/frontyard_1.json` 是原生版独立定义。现有 `content/levels/frontyard_1.json` 保持 150 阳光和 7 波，供旧版运行及对照。布局、状态推进、动画音频和运行时波次调度仍需要同版本实机或进一步静态证据。
