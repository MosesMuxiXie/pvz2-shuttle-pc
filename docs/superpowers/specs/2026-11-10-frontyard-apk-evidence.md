# v26.10.1 前院第 1 关静态证据

使用 Craft Anything 0.6.0 对本地 APK 执行 `android-package-show`，确认包名 `com.ea.game.pvz2_shu`、版本 `26.10.1`、versionCode `460`。用 `native-strings-find` 定位 ARM64 `libPVZ2.so` 的波次和阳光属性，再用 Ghidra 12.1.4 核对属性绑定及默认值。库的 SHA-256 为 `3529dd6cdd3a3b92187cc8584c42903106f20083a43f6d6311713f43a4cff944`。地址均为 ELF 虚拟地址。当前 Windows 主机无可用 Android 模拟器和 ADB，以下结论基于静态核对。

| 项目 | 同版证据 | C++ 关卡 |
| --- | --- | --- |
| 开局阳光 | `LevelDefinition` 构造地址 `0x1b7f644` 将偏移 `0x90` 初始化为 50，注册点 `0x1b7d230` 将同一偏移绑定为 `StartingSun`。首关无覆盖，`AddBonusStartingSun` 默认允许额外加成。 | 使用 50 基础阳光。进度加成待实现。 |
| 落阳光 | OBB 包 `pkg_0234` 的 `DefaultSunDropper` 配置首发 2 秒、基础间隔 6 秒，另有随机范围、递增与上限。 | 采用 2 秒首发。随后间隔为 min(12, 6 + 0.1 × 已完成的定时次数) + U(0,3) 秒，递增先封顶再加随机量。 |
| 波次构成 | `pkg_1996_LevelDefinition.json` 中关卡为 `YourHouse 1`、`DayStage`。`WaveCount=6`、`FlagWaveInterval=6`，Wave1–6 有定义，Wave7–10 只有悬空引用。第五波额外掉落 1 份叶绿素。 | 转录六个有效波次，显式 1–5 行换算为 0–4，未指定的行用可重放的随机数。第五波分配 1 个叶绿素携带者，击败后可拾取。按生成顺序选取满足 CanSpawnPlantFood 的僵尸，最多分配请求的数量。第五波首个路障僵尸满足该属性。 |
| 波次间隔 | `WaveManagerProperties` 构造地址 `0x10f18cc` 默认首波倒计时 12 秒。初始化点 `0x10f8134` 设置普通下一波的 25–31 秒计时、旗帜波前 45 秒计时。`0x10f64e4` 起的分支根据 70–85% 的随机波次血量阈值提前刷波，最短间隔 4 秒。旗帜波还有 5 秒警告延迟。 | 采用首波 12 秒、普通波 25–31 秒及旗帜波前 45 秒计时。当前波生命不高于随机阈值时可提前推进，最短间隔 4 秒。旗帜警告持续 5 秒。 |
| 选卡和僵尸 | `SeedBankProperties.SelectionMethod=chooser`，首关未固定卡组。`pkg_2112` 与 `pkg_2115` 可核对 `tutorial` 和 `tutorial_armor1` 的基础生命 190、移速 0.185，`pkg_0002` 中锥桶防具生命 370。 | 基于已有四张植物卡供玩家选择。映射到现有普通僵尸和路障僵尸定义，保留已知基础生命、移速与护甲值。 |

`content/native/frontyard_1.json` 是原生版独立定义。现有 `content/levels/frontyard_1.json` 保持 150 阳光和 7 波，供旧版运行及对照。布局、状态推进、动画音频和运行时波次调度仍需要同版本实机或进一步静态证据。

2026-11-11 补充核验。原生动态波次按当前波存活僵尸的本体与头盔生命合计比较，旧波僵尸不参与。Ghidra 中 `0x1dcdc9c` 遍历当前波，`0x147c3dc` 汇总并截断本体与头盔生命，`0x14746a4`、`0x1474c68`、`0x1474d6c` 可核对字段绑定。阈值在波次开始时截断为整数，比较条件为小于或等于。ELF `0x10f64f0` 的整数 CMP 与 `0x10f64f4` 的 B.GT 表明等于阈值也会推进，替代先前对伪代码的严格小于判断。阳光公式由 `SunDropperModule` 的 `0xfc5b04` 计时路径与 `0xfc4ffc` 属性绑定核对，其次数来自定时落阳光尝试，独立于植物产出和玩家拾取。当前原生场景具备可产出阳光的条件，原版在特定条件下抑制产出的分支仍需补运行样本。

叶绿素携带者选择由 ELF `0xda3d8c` 的生成循环核对。`AdditionalPlantfood` 提供预算，`ZombiePropertySheet` 的 `CanSpawnPlantFood` 字段控制资格（注册点 `0x16ba1c0`），生成后设置携带条件与效果。第五波首个 `tutorial_armor1` 的原始属性为 true。原生兼容旧数据时该属性缺省为 true，后续全量僵尸导入需保留原始显式覆盖。

ELF `0x12d57fc` 的掉落助手读取并清除携带条件，创建 `plantfood`，坐标取僵尸矩形的水平中心与四分之一高度。`0x147ba28` 广播 `ZombieDropAllLoot` 并设置一次性标记。掉落助手中的抑制条件、全局拾取物上限，以及两条路径的具体订阅关联继续留作待核验项。当前原生拾取物以草坪格为单位呈现。
