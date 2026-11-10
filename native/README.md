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

此阶段支持内容审计和启动图显示。完整的玩法、联网和打包验收见[原生重建设计](../docs/superpowers/specs/2026-11-10-native-client-design.md)。
