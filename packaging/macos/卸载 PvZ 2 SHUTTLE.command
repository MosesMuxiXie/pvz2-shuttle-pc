#!/bin/bash
# PvZ 2 SHUTTLE macOS 卸载脚本
set -e
for DEST in "/Applications" "$HOME/Applications"; do
  if [ -d "$DEST/PvZ2SHUTTLE.app" ]; then
    rm -rf "$DEST/PvZ2SHUTTLE.app"
    echo "已删除 $DEST/PvZ2SHUTTLE.app"
  fi
done
echo "存档保留在 ~/Library/Application Support/PvZ2SHUTTLE（如需彻底删除请手动移除该目录）。"
