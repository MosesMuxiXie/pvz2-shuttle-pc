# PvZ 2: SHUTTLE — PC 移植版（非官方粉丝复刻）

> **这不是《植物大战僵尸 2》官方产品，也不是 SHUTTLE 模组的官方 PC 版。**
> 本项目是社区爱好者以 SHUTTLE v26.11.1（数据包 460.9 / 核心库 460.11）的公开数据、素材与界面为参照
> 重写的 Windows 单机复刻版，仅用于学习、研究与个人游玩。仓库里有两条实现：
> **`native/`（C++ 原生客户端，当前主线）** 与 `game/` + `main.py`（早期的 Python + pygame 版本，保留作对照）。

## 原生客户端重建进度（开发中）

2026-11-20 原生端已推进到**数据驱动内核**（S0–S3）：内容编译器把原版属性表编成 `native/generated/content.pack`
（339 植物类型 / 1127 僵尸类型），183 个 `ZombieClass` 全部映射到行为族，26 个世界的棋盘尺寸从关卡定义解出
（beach/modern 6×9），任意关卡可用 `--run-level` 无头跑完并在同种子下复现同一状态哈希。
**尚未完成完整复刻；现有发行版入口不变。** 147 株植物的美术、26 个 Boss、元素/养料/融合/小游戏、
桌面视图迁移到新内核与 macOS 验证仍在进行，逐项状态见 [docs/PARITY_BASELINE.md](docs/PARITY_BASELINE.md) 与
[docs/PARITY_MATRIX.md](docs/PARITY_MATRIX.md)。
运行与构建见 [native/README.md](native/README.md)，验收及后续清单见 [docs/NATIVE_PROGRESS.md](docs/NATIVE_PROGRESS.md)。

## 原生客户端：构建与命令行

`native/` 是 C++20 + SDL3 的实现，数据来自 `content/`（内容编译器产物）与 `native/generated/`（派生表，
`data 460.9`）。三条命令覆盖了从构建到验收的全过程：

```powershell
# 构建（Release，桌面视图；找不到 cmake 时脚本自己去 vswhere 里找）
pwsh -File tools/build_native.ps1

# 打包：构建 -> install 到 dist/ -> 生成 LICENSES.md -> zip -> sha256 -> 解压后台冒烟
pwsh -File tools/package.ps1

# 门禁：内容编译、C++ 审计、桌面用例、Python 用例、矩阵与台账（静树下必须 EXIT=0）
pwsh -File tools/check_all.ps1
```

打出来的 `dist/PvZ2SHUTTLE-<版本>-win64.zip` 里有 `PvZ2SHUTTLE.exe`、`content/`、`generated/`、`assets/ui/`、
`PROGRESS.md`、`LICENSES.md`（约 20.8 MB）。**`assets/ui/` 只放界面小图与中文字体（26.6 MB 解压后），
是四屏无头渲染的硬需求**；4.6 GB 的提取美术（`db/ lawn/ world/ …`）不在包里：解压后用 `PVZ_ASSET_ROOT`
指向本机 `assets/`，或把 `assets/` 放在 exe 旁边（查找顺序：`PVZ_ASSET_ROOT` → exe 所在目录的 `assets/`
→ 从工作目录向上找 `native/generated`）。构建目录里的 `PVZ_ASSET_SOURCE` 是 cache 变量，素材树换位置时
要么删 `build/package` 要么显式 `-DPVZ_ASSET_SOURCE=...`（`tools/package.ps1` 每次都会显式传）。

exe 自己的参数（`--version` 会打印版本与数据版本）：

| 命令 | 用途 |
| --- | --- |
| `--version` | 打印 `PvZ2SHUTTLE <版本>` 与 `data <数据版本>`，用于验收包里是不是这次构建 |
| `--menu <content> [--frames N]` | 主菜单；带 `--frames` 时无头渲染 N 帧并落 PNG |
| `--worldmap <content> [--worldmap-screen]` | 世界地图 / 世界门状态 |
| `--level-select <content> --world <id>` | 选关屏 |
| `--run-level <content> <level> --seconds N` | 无头跑一关，输出波次、击杀、掉落、机制计数与状态哈希 |
| `--flow <content> [--progress FILE] [--flow-after N]` | 自动选关闭环：打完一关结算并推进到下一关 |
| `--battle <content> <level> [--battle-snapshot PNG]` | 桌面战斗视图（可截图） |
| `--simulate <content> [level]` | 旧 `Battle` 模拟器；该关有不支持规则时按名单 exit 2 |
| `--audio-audit` / `--audio-off` / `--volume 0..100` | 音频审计（解了多少音源、多少秒）、静音、主音量 |
| `--shop <content> --buy <id> [--coins N]` | 商店购买与可买清单 |

`--run-level` 与 `--flow` 的输出是 JSON（`status` / `tick` / `hash` / `coinsGained` / `mechanicUnknown` 等），
同一个种子两次运行必须逐字节相同——这是所有玩法改动的第一条回归判据。

## 为什么是“复刻”而不是“直接移植”

原 APK **无法**原样在 PC 上运行，本仓库作者已逐项验证：

1. `classes.dex` 由 SecShell（梆梆加固）加壳，真实启动器字节码不在 DEX 中，无法静态还原；
2. 游戏内容由 SHUTTLE 服务端在线下发，APK 本体不含关卡/美术资源；
3. 原生引擎 `libPVZ2.so` 只有 arm64-v8a，依赖 Android NDK/EGL；
4. 本机固件关闭 VT-x，无法运行带硬件加速的 Android 模拟器。

因此采用“数据 + 美术 + 音频还原，引擎重写”的路线：

- **关卡/数值/文本**：从官方 OBB（`main.460.com.ea.game.pvz2_shu.obb`，1.95 GB）解包 RSB/RSG，
  RTON 解码后重建 26 个世界、1809 个关卡、147 株植物、55 种僵尸的数值与中文文本；
- **动画/美术**：从 Gardendless 网页版（Cocos Creator 3.8.4）烘焙 DragonBones 骨骼动画与图集，
  并用 SHUTTLE 素材包 `Renders/` 中的立绘、世界图与草坪图；
- **音频**：从 OBB 的 Wwise 音效库提取 `.wem`，用 vgmstream 解码为 OGG（21 首），
  另有早期从 PvZ2 Fandom 维基收集的 19 首曲目；
- **玩法/UI**：用 pygame-ce 重新实现，参考真实 SHUTTLE 截图与视频校正界面。

## 功能

- **26 个世界 / 1809 个关卡**（含普通关、夜战、Boss 关、砸罐子关）；
- **147 株植物 / 55 种僵尸 / 85 组植物融合**；
- **26 个僵尸博士 Boss**，三阶段血量阈值、提速、召唤增援；
- **养料系统**、**360+ 星章条件**、**卡组选择**；
- **砸罐子 45 关**、**生存无尽**、**商店 585 件商品**、**禅境花园 2.0**（4 阶段、浇水、收获）；
- **6×10 动态战场**、**矿车关卡**、夜晚草坪、真实 DragonBones 动画；
- **电影感世界地图轮播**（26 世界、钥匙解锁、详情分页）；
- **音频**：21 首 SHUTTLE OBB 还原曲目 + 19 首 Fandom 曲目 + 音效；
- 存档、设置（高视角/高画质/速度/音乐/音效）、Windows/macOS 打包。

## 下载

见本仓库 **Releases**：

| 文件 | 平台 | 说明 |
| --- | --- | --- |
| `PvZ2SHUTTLE-Setup-26.10.1.exe` | Windows 10/11 x64 | Inno Setup 安装程序，按用户安装 |
| `PvZ2SHUTTLE-26.10.1-Windows-portable.zip` | Windows 10/11 x64 | 免安装，解压运行 `PvZ2SHUTTLE.exe` |
| `PvZ2SHUTTLE-26.10.1-macOS-universal.zip` | macOS 11+（Intel / Apple Silicon） | 内含 `Install PvZ2SHUTTLE.command` 安装脚本，首次右键打开 |

macOS 包为 Windows 交叉组装的通用 `.app`，**未签名、未公证**，首次运行需右键 → 打开；
或在终端执行 `xattr -dr com.apple.quarantine PvZ2SHUTTLE.app`。

## 原生客户端：从 clone 到能跑

仓库里已经带了**能直接构建运行**的东西：`native/` 源码、`content/`（1809 关数据）、
`native/generated/`（31 张编译表）、`assets/ui`（中文字体与界面图）。

```bash
cmake -S native -B build/native -G "Visual Studio 17 2022" -A x64 -DPVZ_ENABLE_DESKTOP=ON
cmake --build build/native --config Release
build/native/Release/PvZ2SHUTTLE.exe --menu content --frames 2 --snapshot menu.png
```

两个**不在仓库里**的前置（体积太大且不随代码分发，缺了不影响构建，只影响对应能力）：

| 前置 | 缺了会怎样 | 怎么补 |
| --- | --- | --- |
| `PvZ2SHUTTLE/assets`（约 4.6 GB 美术/音频） | 界面能用，战斗里没有贴图（走占位绘制） | 用 `tools/obb/` 从你自己的 OBB 解出来，设 `PVZ_ASSET_ROOT` 指过去，或放到 exe 同级 `assets/` |
| `work/obb_packages`（原版表目录，2116 个包） | 测试套件跳过 399 个用例；重新编译 `native/generated/*` 的工具跑不了 | 设 `PVZ2_OBB_DIR` 指向解包目录 |

干净 clone 的测试结论（实测）：不设 `PVZ2_OBB_DIR` → `Ran 630 / OK (skipped=399)`；
设了 → `Ran 648 / OK (skipped=75)`。全量门禁是 `pwsh -File tools/check_all.ps1`。

## 从源码运行

仓库**不包含** `assets/`（约 205 MB 的动画/立绘/音轨）以及 APK/OBB/素材原始文件，
因为这些素材的权利属于原权利人。生成方式见 [`docs/BUILD.md`](docs/BUILD.md)。

```bash
python -m pip install -r requirements.txt
python main.py
```

## 目录结构

```
game/            游戏源码（引擎、界面、数据加载、存档）
content/         26 世界 / 1809 关 / 植物 / 僵尸 / 商店 / 星章 JSON（从 OBB 转换）
tools/           内容生成、素材烘焙、校验与打包脚本
tools/obb/       OBB(1BSR/RSG) 解包、RTON 解码、音频提取流水线
tests/           引擎 / 界面 / 世界地图 / 商店花园测试
installer/       Inno Setup 安装脚本（Windows）
packaging/macos/ macOS universal .app 组装脚本
docs/            来源、构建、法律说明
```

## 测试

```bash
python tools/validate_all.py
python tests/test_engine.py
python tests/test_screens.py
python tests/test_new_screens.py
python tests/test_worldmap.py
python tests/test_shop_garden.py
python main.py --selftest
```

## 版权、来源与免责声明

- 《植物大战僵尸 2》及其全部角色、美术、音频、文本版权归 **PopCap Games / Electronic Arts** 所有；
- 《PvZ 2: SHUTTLE》模组版权归 **SHUTTLE 制作组（李子、华人天下游 等）** 所有；
- 本仓库代码以 **MIT** 许可发布（见 `LICENSE`），但 **不包含也不授权** 任何游戏素材；
- 详细来源清单见 [`docs/SOURCES.md`](docs/SOURCES.md)，第三方组件见 [`NOTICE.md`](NOTICE.md)，
  法律风险说明见 [`docs/LEGAL.md`](docs/LEGAL.md)。

**本项目与 EA、PopCap、SHUTTLE 制作组均无隶属或授权关系；请勿用于商业用途。**
如果任何权利人认为本仓库或发行包侵犯其权利，请通过 Issue 联系，我们会立即下架相关内容。
