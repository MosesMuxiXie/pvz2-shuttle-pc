# PvZ 2 SHUTTLE 原生客户端基础

需要支持 C++20 的编译器及 CMake 3.24 或更新版本。首次配置从上游获取固定版本并校验 SHA-256。关卡审计可独立构建，不依赖 SDL 或游戏素材。

```sh
cmake -S native -B build/native -DPVZ_ENABLE_DESKTOP=OFF
cmake --build build/native --config Release
ctest --test-dir build/native -C Release --output-on-failure
```

在 Windows Visual Studio 生成器下，从仓库根目录审计现有内容。

```powershell
./build/native/Release/PvZ2SHUTTLE.exe --audit-content ./content
```

需要启动窗口时，使用 `-DPVZ_ENABLE_DESKTOP=ON` 配置独立构建目录。运行 `PvZ2SHUTTLE --launcher <本地素材目录>` 打开可缩放窗口，`--launcher-smoke` 解码、渲染一帧后退出。素材目录须含 `ui/launcher.png`。从旧版准备素材的方法见[构建与素材生成](../docs/BUILD.md)。

### 游玩前院第 1 关

```powershell
cmake -S native -B build/desktop -DPVZ_ENABLE_DESKTOP=ON
cmake --build build/desktop --config Release
./build/desktop/Release/PvZ2SHUTTLE.exe --play-first ./content
```

点击卡片选种子，按 Enter 开战。战斗中点击卡片或按 1–4 选卡，再点击草坪种植。点击阳光收集，X 选铲子，空格暂停。结算后按 R 重开。画面使用程序绘制的图形，无需额外素材。

导入 Python 存档后，通关写入独立的原生档位。默认目录由 SDL 选取，导入和游玩也可分别传入相同的目标文件路径。导入会保留原文件和其他进度字段，目标已经存在时会报错。

```powershell
./build/desktop/Release/PvZ2SHUTTLE.exe --import-save 'D:/path/to/Python/save.json'
```

### macOS 开发 DMG

GitHub Actions 的 **Build macOS development DMG** 作业构建 `arm64` 和 `x86_64` 通用 `.app`，包内含仓库的 `content/` 和 `/Applications` 拖放入口。作业挂载并验证 DMG，检查两种架构及包内资源，然后上传 DMG 和 SHA-256。包为开发构建，未做 Developer ID 签名或公证。

前院静态比对见 [APK 与 OBB 证据](../docs/superpowers/specs/2026-11-10-frontyard-apk-evidence.md)。完整的玩法、联网和发行验收见[原生重建设计](../docs/superpowers/specs/2026-11-10-native-client-design.md)。
