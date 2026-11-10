"""草坪网格：几何换算与格子占用。

坐标基准（战斗画面 1280x720）：
    行 0 在上，列 0 在左。
    格子 (row, col) 的屏幕矩形 = (BOARD_X + col*CELL_W, BOARD_Y + row*CELL_H, CELL_W, CELL_H)
    ``cell_center`` 返回格子中心，``row_ground_y`` 返回该行“脚底”y。

Board 只负责数据（占用网格），不持有实体列表；实体由 LevelSession 管理。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from ..config import (BOARD_COLS, BOARD_ROWS, BOARD_X, BOARD_Y, CELL_H, CELL_W)

if TYPE_CHECKING:  # 仅类型提示，避免循环导入
    from .entities import Plant

# 草坪整体尺寸（像素）
BOARD_W = BOARD_COLS * CELL_W
BOARD_H = BOARD_ROWS * CELL_H

# 当前会话几何（支持每关不同的行列数，如 6 行 x 10 列）
_GEOM = {
    "rows": BOARD_ROWS, "cols": BOARD_COLS,
    "x": BOARD_X, "y": BOARD_Y,
    "w": BOARD_W, "h": BOARD_H,
    "cw": CELL_W, "ch": CELL_H,
}


def set_geometry(rows=None, cols=None, x=None, y=None, w=None, h=None):
    """设置当前会话的草坪几何，返回上一份几何（供恢复）。"""
    old = dict(_GEOM)
    if rows is not None:
        _GEOM["rows"] = max(1, int(rows))
    if cols is not None:
        _GEOM["cols"] = max(1, int(cols))
    if x is not None:
        _GEOM["x"] = int(x)
    if y is not None:
        _GEOM["y"] = int(y)
    if w is not None:
        _GEOM["w"] = int(w)
    if h is not None:
        _GEOM["h"] = int(h)
    _GEOM["cw"] = _GEOM["w"] / float(_GEOM["cols"])
    _GEOM["ch"] = _GEOM["h"] / float(_GEOM["rows"])
    return old


def get_geometry():
    return dict(_GEOM)


def board_width():
    return _GEOM["w"]


def board_height():
    return _GEOM["h"]


def cell_width():
    return _GEOM["cw"]


def cell_height():
    return _GEOM["ch"]


# ---------------------------------------------------------------- 几何工具
def cell_center(row: int, col: int) -> tuple[int, int]:
    """格子中心的屏幕坐标（int）。"""
    g = _GEOM
    return (g["x"] + int(col) * g["cw"] + g["cw"] / 2,
            g["y"] + int(row) * g["ch"] + g["ch"] / 2)


def cell_topleft(row: int, col: int) -> tuple[int, int]:
    g = _GEOM
    return (g["x"] + int(col) * g["cw"], g["y"] + int(row) * g["ch"])


def cell_rect(row: int, col: int) -> pygame.Rect:
    g = _GEOM
    return pygame.Rect(int(g["x"] + int(col) * g["cw"]),
                       int(g["y"] + int(row) * g["ch"]),
                       int(g["cw"]), int(g["ch"]))


def row_ground_y(row: int) -> int:
    """某一行实体“脚底”的 y 坐标（略高于格子底边）。"""
    g = _GEOM
    return int(g["y"] + (int(row) + 1) * g["ch"] - 6)


def col_at_x(x: float) -> int:
    """屏幕 x -> 列号（可能越界，调用方自行判断）。"""
    return int((float(x) - _GEOM["x"]) // _GEOM["cw"])


def row_at_y(y: float) -> int:
    """屏幕 y -> 行号（可能越界）。"""
    return int((float(y) - _GEOM["y"]) // _GEOM["ch"])


class Board:
    """草坪网格与格子占用表。"""

    def __init__(self, rows: int = BOARD_ROWS, cols: int = BOARD_COLS):
        self.rows = int(rows)
        self.cols = int(cols)
        # _grid[row][col] = Plant | None
        self._grid: list[list["Plant | None"]] = [
            [None] * self.cols for _ in range(self.rows)
        ]

    # ------------------------------------------------------------ 基础查询
    def in_bounds(self, row: int, col: int) -> bool:
        try:
            return 0 <= int(row) < self.rows and 0 <= int(col) < self.cols
        except (TypeError, ValueError):
            return False

    def cell_center(self, row: int, col: int) -> tuple[int, int]:
        return cell_center(row, col)

    def cell_rect(self, row: int, col: int) -> pygame.Rect:
        return cell_rect(row, col)

    def cell_at(self, pos) -> tuple[int, int] | None:
        """屏幕坐标 -> (row, col)；不在草坪内返回 None。"""
        try:
            x, y = pos[0], pos[1]
        except (TypeError, IndexError):
            return None
        row = row_at_y(y)
        col = col_at_x(x)
        if self.in_bounds(row, col):
            return (row, col)
        return None

    # ------------------------------------------------------------ 占用网格
    def plant_at(self, row: int, col: int) -> "Plant | None":
        if not self.in_bounds(row, col):
            return None
        return self._grid[int(row)][int(col)]

    def is_empty(self, row: int, col: int) -> bool:
        return self.in_bounds(row, col) and self._grid[int(row)][int(col)] is None

    def set_plant(self, row: int, col: int, plant: "Plant | None") -> "Plant | None":
        """放入植物，返回该格原有植物（可能为 None）。"""
        if not self.in_bounds(row, col):
            return None
        old = self._grid[int(row)][int(col)]
        self._grid[int(row)][int(col)] = plant
        return old

    def clear(self, row: int, col: int) -> "Plant | None":
        """清空一格，返回被清掉的植物。"""
        return self.set_plant(row, col, None)

    def clear_all(self):
        for r in range(self.rows):
            for c in range(self.cols):
                self._grid[r][c] = None

    def iter_plants(self):
        """遍历网格中所有植物（按行、列顺序）。"""
        for r in range(self.rows):
            for c in range(self.cols):
                p = self._grid[r][c]
                if p is not None:
                    yield p

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<Board {self.rows}x{self.cols}>"
