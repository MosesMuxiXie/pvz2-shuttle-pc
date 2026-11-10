# PvZ 2: SHUTTLE — PC 移植版（非官方粉丝复刻）

> **这不是《植物大战僵尸 2》官方产品，也不是 SHUTTLE 模组的官方 PC 版。**
> 本项目是社区爱好者以 SHUTTLE v26.10.1 的公开数据、素材与界面为参照，用 Python + pygame 重写的
> Windows / macOS 单机复刻版，仅用于学习、研究与个人游玩。

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
