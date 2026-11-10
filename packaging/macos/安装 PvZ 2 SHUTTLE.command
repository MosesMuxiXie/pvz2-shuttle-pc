#!/bin/bash
# PvZ 2 SHUTTLE macOS 安装脚本
set -e
cd "$(dirname "$0")"
APP="PvZ2SHUTTLE.app"
if [ ! -d "$APP" ]; then
  /usr/bin/osascript -e 'display alert "PvZ 2 SHUTTLE" message "缺少 PvZ2SHUTTLE.app，请把压缩包完整解压后再运行本脚本。" as critical'
  exit 1
fi
DEST="/Applications"
if [ ! -w "$DEST" ]; then
  DEST="$HOME/Applications"
  mkdir -p "$DEST"
fi
echo "正在安装到 $DEST ..."
rm -rf "$DEST/$APP"
cp -R "$APP" "$DEST/"
xattr -dr com.apple.quarantine "$DEST/$APP" 2>/dev/null || true
chmod +x "$DEST/$APP/Contents/MacOS/PvZ2SHUTTLE"
echo ""
echo "安装完成：$DEST/$APP"
echo "首次启动若被系统拦截，请右键点击 App → 打开。"
open "$DEST/$APP"
