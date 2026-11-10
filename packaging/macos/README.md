# macOS 打包说明

`build_mac_app.py` 在 Windows 上交叉组装 `PvZ2SHUTTLE.app`：

- `Contents/MacOS/PvZ2SHUTTLE`：bash 启动脚本，按 `uname -m` 选择 `Resources/py-arm64/bin/python3.12`
  或 `Resources/py-x86_64/bin/python3.12`；
- `Contents/Resources/lib`：pygame-ce 2.5.8 universal2 wheel 解压内容；
- `Contents/Resources/app`：游戏源码与素材；
- `Info.plist`：bundle id `cn.pvz2shuttle.remake`，LSMinimumSystemVersion 11.0，
  LSArchitecturePriority `["arm64","x86_64"]`；
- 附带 `Install PvZ2SHUTTLE.command` / `Uninstall PvZ2SHUTTLE.command` 安装卸载脚本。

需要预先准备（脚本会在 `work/mac/` 下查找）：

- `py-arm64/python`、`py-x86_64/python`（python-build-standalone 3.12，install_only_stripped）；
- `lib/`（pygame universal2 wheel 解压）；
- `appicon.icns`。

该 .app 未签名、未公证；首次运行需右键 → 打开。
