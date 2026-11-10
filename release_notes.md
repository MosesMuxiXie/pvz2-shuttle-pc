# PvZ 2: SHUTTLE — PC 移植版 v26.10.1（完整版）

非官方粉丝复刻，**与 EA / PopCap / SHUTTLE 制作组无隶属关系**。
包含完整 26 世界 / 1809 关 / 147 植物 / 55 僵尸 / 85 融合 / 26 Boss 三阶段 / 585 商品 / 花园 2.0。

## 安装包

| 文件 | 平台 | 说明 |
| --- | --- | --- |
| `PvZ2SHUTTLE-Setup-26.10.1.exe` | Windows 10/11 x64 | Inno Setup 安装程序（按用户安装，无需管理员） |
| `PvZ2SHUTTLE-26.10.1-Windows-portable.zip` | Windows 10/11 x64 | 免安装解压运行 |
| `PvZ2SHUTTLE-26.10.1-macOS-universal.zip` | macOS 11+ Intel / Apple Silicon | 内含 `Install PvZ2SHUTTLE.command` 安装脚本；未签名，首次右键打开 |

## 本轮更新

- OBB 音频还原：21 首真实 SHUTTLE 音乐（Wwise BNK → WEM → vgmstream → OGG），接入对应世界与启动器。
- 世界地图重制：电影感轮播（夜空星点、中央岛、8 辣椒难度、关卡气泡、钥匙解锁、字母列、圆点分页）。
- 商店重绘：奶白大卡 + 彩色标题条 + 立绘 + 蓝色价格条，585 件商品 4 类分页。
- 图鉴重绘：深蓝种子包网格 + 阳光价签 + 绿色标题详情条。
- 修复打包后动态导入失败，加入 `crash.log` 与 `--selftest`。

## 校验

见 `SHA256SUMS.txt`。

## 版权

《植物大战僵尸 2》© PopCap Games / Electronic Arts；SHUTTLE 模组版权归其作者。
发行包包含原版权素材，仅限已合法拥有该模组的用户个人使用；请勿商用或公开再分发。
详见仓库 `NOTICE.md` 与 `docs/LEGAL.md`。
