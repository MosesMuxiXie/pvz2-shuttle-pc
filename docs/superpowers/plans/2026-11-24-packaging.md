# 打包与发布计划（起草 2026-11-24，未开工）

用户口径：**打包留到最后**。本文件只是先把「最后那步要做什么」写清楚，避免收官时临时决定。
状态：**未开工**（等关卡机制与经济闭环接线完成后再执行）。

## 目标

一个在自己机器上双击就能跑、别人拿到 zip 也能跑的 Windows 版本，并且**不把第三方资产当成我们的**：

1. `PvZ2SHUTTLE.exe`（桌面版，含 SDL3 之外的零外部 DLL 依赖）
2. `assets/`（我们自己编译出来的 `content/` + `native/generated/` + 从 OBB 提取的美术，**不含**原始 OBB）
3. `README.md`（怎么跑、怎么换内容、已知限制）
4. `LICENSES.md` + `NOTICE`（SDL3 / stb_vorbis / freetype / nlohmann / 字体）

## 现在已知的约束

- **美术来自 OBB**：`PvZ2SHUTTLE/assets/db/shuttle/`（1085/1087 base 提取成功，12 条里 10 条 ASTC 已解）。
  发布包要不要带美术，是法律与体积的取舍，不是技术问题 —— 需要在收官时让用户拍一次。
- **字体**：`assets/ui/font_zh.ttc`（中文必须），体积 ~10 MB，属于必须带。
- **音频**：`assets/audio/` 67 个文件，其中 5 个 mp3 无解码器（走 wav 兜底）。
- **生成物入包**：`native/generated/*.json` 是运行时数据，不是构建中间物，必须随包。
- **`--progress` 存档**：默认写用户目录还是 exe 同目录，要定（建议 `%APPDATA%`）。
- 现有构建脚本 `tools/build_native.ps1` 只做编译与测试，**没有 install 规则**。

## 要做的七件事

| # | 事项 | 验证 |
| --- | --- | --- |
| 1 | CMake `install()` 规则：exe + assets + generated + 文档 | 全新目录 `cmake --install` 后能跑 |
| 2 | 版本号单一来源（`CMakeLists.txt` → `--version`） | `PvZ2SHUTTLE.exe --version` 与 CMake 一致 |
| 3 | 资源查找顺序：exe 同级 `assets/` → `PVZ_ASSET_ROOT` 环境变量 | 移动目录后仍能起 |
| 4 | 存档目录策略（`%APPDATA%\PvZ2SHUTTLE\progress.json`），带 `--progress` 覆盖 | 两个不同用户互不干扰 |
| 5 | `LICENSES.md` 从 `native/third_party/NOTICE` 与 CMake 依赖生成 | 每个第三方库都能追到版本与许可 |
| 6 | `README.md`：三张截图 + 命令表（`--menu`/`--worldmap-screen`/`--run-level`/`--flow`/`--audio-audit`） | 每条命令都实测过 |
| 7 | 打包脚本 `tools/package.ps1`：干净构建 → install → zip → 记录 sha256 | 两次打包同一份源码，exe 之外的字节一致 |

## 门禁

1. `tools/check_all.ps1` 静树 EXIT=0（收官那次的数字必须与台账一致）。
2. 解压到**没有源码树**的路径后，`--menu --frames 2`、`--worldmap-screen --frames 2`、`--run-level beach_23 --seconds 60`、`--audio-audit` 四条命令都能跑出预期输出。
3. 包里不含原始 OBB、不含 `.pdb`、不含 `build/`。
4. `docs/COMPLETENESS.md` 的完成度表与包内实际能力一致（不许把「数据已编译」写成「功能已实现」）。

## 明确不做

- 不联网、不做账号、不做云存档（S9 的活儿）。
- 不做安装器（zip 解压即用）；不签名（无证书）。
- 不内置原版 OBB 或任何 Capcom/EA 的原始资源包。

## 收官前必须问用户的三件事

1. 发布包是否带从 OBB 提取的美术（体积 vs 版权）。
2. 是否要保留调试命令行（`--run-level` 等），还是只留 GUI 入口。
3. 版本号从 `v0.x` 起还是直接标 `1.0`。
