# NOTICE — 第三方组件与权利声明

本仓库的 **源代码** 以 MIT 许可发布。以下内容不属于 MIT 许可范围。

## 1. 游戏素材与数据

| 内容 | 权利人 / 来源 | 说明 |
| --- | --- | --- |
| 《植物大战僵尸 2》全部角色、美术、音频、文本、商标 | PopCap Games / Electronic Arts | 版权归原权利人；本仓库不主张任何权利 |
| 《PvZ 2: SHUTTLE》模组内容、素材包 `Renders/`、音乐包 `Music/` | SHUTTLE 制作组（李子、华人天下游、明非的小樱花 等） | 由模组作者制作；本仓库仅在用户已获取该模组的前提下用于兼容复刻 |
| OBB 解包得到的世界/关卡/数值/文本（`content/`） | 源自上述 PvZ2 / SHUTTLE 数据 | 属于衍生数据，版权归原权利人 |
| Gardendless 网页版烘焙的 DragonBones 动画、世界图、草坪图、UI 图集 | Gardendless 项目（Gzh0821 / 南Garden） | 上游未声明开源许可；仅作为素材来源记录 |
| OBB Wwise 音轨（21 首） | PopCap / EA / SHUTTLE | 从 OBB 提取，版权归原权利人 |
| PvZ2 Fandom 维基曲目（19 首） | PopCap / EA；维基页面由社区整理 | 版权归原权利人 |

发行包（Releases 中的 exe/zip）**包含上述素材**，其再分发可能不符合 EA 的服务条款。
详见 `docs/LEGAL.md`。

## 2. 运行时与工具（未随仓库分发，仅构建/运行时依赖）

| 组件 | 许可 |
| --- | --- |
| Python 3.12 (python-build-standalone) | PSF License |
| pygame-ce 2.5.8 | LGPL-2.1（动态链接） |
| NumPy | BSD-3-Clause |
| Pillow | HPND |
| PyInstaller 6.22.3 | GPL-2.0 with bootloader exception |
| Inno Setup 6 | jrsoftware 免费许可 |
| FFmpeg（imageio-ffmpeg 内置） | LGPL/GPL（取决于构建） |
| vgmstream-cli | 见上游 vgmstream 许可 |
| pyvz2（RSB/RSG/RTON 解码参考） | GPL-3.0；**仅用于研究格式，未复制进本仓库** |
| Craft Anything CLI | 仅用于 APK 结构分析，未分发 |

本仓库的 `tools/obb/` 下脚本为作者根据公开格式资料自行实现，未包含 pyvz2 源码。
