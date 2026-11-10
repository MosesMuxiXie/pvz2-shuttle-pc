# 素材与数据来源

本项目所有素材均可追溯到以下公开来源。仓库不包含原始 APK/OBB。

## 1. 原始游戏与模组

| 项目 | 版本 | 来源 |
| --- | --- | --- |
| PvZ 2 SHUTTLE APK | 26.10.1（`com.ea.game.pvz2_shu`，versionCode 460） | 官方发布页 `pvz2shuttle.cn` → Google Drive / MEGA / MediaFire / 百度网盘 |
| OBB 数据包 | `main.460.com.ea.game.pvz2_shu.obb`，2,095,579,136 B | 官方发布页的 “OBB Backup” 目录（Google Drive） |
| 游戏内数据 | RSB/RSG v4 + Zstandard，4310 资源组 / 25 世界包 / 2116 RTON 包 / 1809 关卡 | 由 OBB 解包得到 |

## 2. 动画与美术

| 素材 | 来源 | 生成工具 |
| --- | --- | --- |
| 植物/僵尸/投射物 DragonBones 动画与图集 | Gardendless 网页版 0.16.15（Cocos Creator 3.8.4，`play.pvzge.com`） | `tools/bake_actors.py`（CDP + 页面内渲染/序列化） |
| 世界图、草坪图、UI 图集（太阳/种子包/面板） | 同上 | `tools/bake_ui.py` |
| 中国园林 / 洛城风云 / 月虹市场 / 王朝 立绘与世界图 | 用户提供的 SHUTTLE 素材包 `Renders/` | `tools/import_renders.py`、`import_plantagenet.py`、`import_missing_worlds.py` |
| 平安 / 童话 / 记忆之旅 世界图与草坪 | 公开 SHUTTLE 素材（fankit） | `tools/import_missing_worlds.py` |
| 嘉年华 / 无印 / 地宫 / 蒸汽 / 热奈 占位美术 | 本项目程序化绘制 | `tools/gen_missing_world_art.py` |
| 图标、启动图、字体 | APK 资源 + 系统微软雅黑 | 由作者整理 |

## 3. 音频

| 素材 | 来源 | 生成工具 |
| --- | --- | --- |
| 21 首世界/启动曲（Wwise `.wem`） | OBB 内 `MUSIC_*` / `STARTUPMUSIC` 音效库 | `tools/obb/bake_audio.py`（vgmstream → WAV → OGG） |
| 19 首早期曲目（frontyard/egypt/pirate/...） | PvZ2 Fandom 维基 “Music (PvZ2)” 页面 | 浏览器 UA + Referer 下载 OGG |
| 8 个合成音效 | 本项目用 NumPy 合成 | `tools/bake_audio.py` |
| 世界地图 / 关卡内环境音 | 上述素材组合 | — |

## 4. 界面参考

| 参考 | 用途 |
| --- | --- |
| Bilibili UP「明非的小樱花」SHUTTLE 实机截图 5 张 | 商店/图鉴/世界内容面板布局 |
| YouTube `TeoGaming201` — “Underground Palace Pt.1 | New World | PvZ 2 SHUTTLE v26.4.1”（`J5VK9EJcyO4`） | 世界地图轮播、地宫世界、战斗 HUD 参考 |
| 用户提供的 16 张真实 SHUTTLE 世界地图截图 | 轮播界面重制 |

上述视频/截图仅用于界面布局比对，未直接复制其像素。

## 5. 代码与格式研究

| 项目 | 用途 |
| --- | --- |
| [nineteendo/pyvz2](https://github.com/nineteendo/pyvz2)（GPL-3.0） | 阅读 1BSR/RSG/RTON 结构后自行实现解包器（未复制源码） |
| [vgmstream](https://github.com/vgmstream/vgmstream) | Wwise WEM → WAV |
| [Gardendless](https://pvzge.com/) | Cocos 资源烘焙与动画数据 |
| Craft Anything CLI | APK 结构取证（未分发） |
