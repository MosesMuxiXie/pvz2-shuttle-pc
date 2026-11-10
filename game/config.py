"""全局常量与路径。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content"
ASSETS_DIR = ROOT / "assets"


def _save_path() -> Path:
    """存档位置：macOS 放应用支持目录，其它平台随游戏目录（便携）。"""
    override = os.environ.get("PVZ2_SAVE_DIR")
    if override:
        return Path(override) / "save.json"
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "PvZ2SHUTTLE"
        base.mkdir(parents=True, exist_ok=True)
        return base / "save.json"
    return ROOT / "save.json"


SAVE_PATH = _save_path()

WIN_W, WIN_H = 1280, 720
FPS = 60
TITLE = "PvZ 2 SHUTTLE"

# 草坪几何（战斗画面 1280x720）
BOARD_ROWS = 5
BOARD_COLS = 9
CELL_W = 100
CELL_H = 116
BOARD_X = 190
BOARD_Y = 120

# 版本信息（复刻 SHUTTLE 启动器展示）
VERSION = "26.10.1"
BUILD_URL = "CustomBuild"
SITE = "pvz2shuttle.cn"

WHITE = (255, 255, 255)
BLACK = (20, 20, 20)
