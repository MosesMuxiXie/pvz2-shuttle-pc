"""冒险模式：世界轮播 + 世界详情。

复刻 PvZ2 SHUTTLE 的世界地图交互：

* 主界面是「世界轮播」：中央一张大卡，左右相邻世界各露出一半；
  支持左右方向键、滚轮、拖拽、点击两侧卡片切换。
* 点击当前卡（或「进入世界」按钮）进入「世界详情」：
  世界简介、总进度、星章汇总、5 列关卡网格。
* 点击关卡调用 ``app.open_seed_chooser(world_id, level_index, slots)``。
* 锁定的世界在详情里显示解锁条件；顺序链上第一个未解锁的世界
  可以消耗钥匙解锁（``save.spend_keys`` + ``save.unlock``）。

本模块只依赖 pygame 与项目内的 ``widgets`` / ``Screen``，不引入新依赖。
"""
from __future__ import annotations

import math

import pygame

from .base import Screen
from . import widgets as ui

# --------------------------------------------------------------------------
# 布局常量（1280×720）
# --------------------------------------------------------------------------
SCREEN_W, SCREEN_H = 1280, 720
HUD_H = 96

CARD_W, CARD_H = 430, 500
CARD_TOP = 108
COVER_H = 300
SIDE_DROP = 12
SIDE_DIM = 112

DETAIL_LEFT = pygame.Rect(40, 112, 352, 576)
DETAIL_RIGHT = pygame.Rect(408, 112, 832, 576)
GRID_X = 430
GRID_Y = 176
GRID_W = 788
GRID_H = 450
GRID_COLS = 5
GRID_ROWS = 2
GRID_GAP = 12
LEVELS_PER_PAGE = GRID_COLS * GRID_ROWS

TEXT_CREAM = (250, 244, 230)
TEXT_CREAM_SOFT = (224, 212, 190)
TEXT_DIM = (198, 186, 168)


# --------------------------------------------------------------------------
# 程序化小图标
# --------------------------------------------------------------------------
def _star_points(cx: float, cy: float, outer: float, inner: float | None = None):
    inner = outer * 0.45 if inner is None else inner
    pts = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = outer if i % 2 == 0 else inner
        pts.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
    return pts


def draw_star_icon(surf, center, radius=12, fill=ui.GOLD, edge=ui.GOLD_DARK, width=2):
    """画一枚五角星；未点亮时传浅色 fill 即可。"""
    pts = _star_points(center[0], center[1], radius)
    pygame.draw.polygon(surf, fill, pts)
    if edge is not None and width > 0:
        pygame.draw.polygon(surf, edge, pts, width)


def draw_key_icon(surf, center, size=22, color=ui.GOLD, dark=ui.GOLD_DARK):
    """画一把小钥匙（圆环 + 钥匙杆 + 齿）。"""
    cx, cy = center
    ring_r = max(2.0, size * 0.23)
    ring_x = cx - size * 0.28
    ring_y = cy - size * 0.16
    shaft_w = max(2, int(size * 0.14))
    # 描边
    pygame.draw.circle(surf, dark, (int(ring_x), int(ring_y)), int(ring_r + 2), shaft_w)
    pygame.draw.circle(surf, dark, (int(ring_x), int(ring_y)), int(ring_r), shaft_w)
    pygame.draw.line(surf, dark, (ring_x + ring_r, ring_y), (cx + size * 0.42, ring_y), shaft_w + 2)
    pygame.draw.line(surf, dark, (cx + size * 0.42, ring_y - size * 0.1),
                     (cx + size * 0.42, ring_y + size * 0.18), shaft_w + 2)
    # 金色本体
    pygame.draw.circle(surf, color, (int(ring_x), int(ring_y)), int(ring_r), max(1, shaft_w - 1))
    pygame.draw.line(surf, color, (ring_x + ring_r, ring_y), (cx + size * 0.42, ring_y), shaft_w)
    pygame.draw.line(surf, color, (cx + size * 0.42, ring_y),
                     (cx + size * 0.42, ring_y + size * 0.18), shaft_w)
    pygame.draw.line(surf, color, (cx + size * 0.42, ring_y + size * 0.18),
                     (cx + size * 0.24, ring_y + size * 0.18), shaft_w)
    pygame.draw.line(surf, color, (cx + size * 0.24, ring_y + size * 0.18),
                     (cx + size * 0.24, ring_y + size * 0.08), shaft_w)


# --------------------------------------------------------------------------
# 世界地图
# --------------------------------------------------------------------------
class WorldMapScreen(Screen):
    name = "worldmap"

    def __init__(self, app):
        super().__init__(app)
        self.W, self.H = SCREEN_W, SCREEN_H
        self.worlds: list[dict] = []
        self.world_meta: dict = {}
        self.index = 0
        self.view = "carousel"          # carousel | detail
        self.detail_index: int | None = None
        self.level_cells: list[dict] = []
        self.level_page = 0
        self.page_count = 1
        self.per_page = LEVELS_PER_PAGE
        self.hover_level = -1
        self.dragging = False
        self._drag_start_x = 0
        self._drag_off = 0

        self._fonts: dict = {}
        self._card_cache: dict = {}
        self._bg_cache: dict = {}
        self._cursor_shape = None
        self.toast = ui.Toast(app)

        self.btn_back = None
        self.btn_enter = None
        self.btn_unlock = None
        self.arrow_left = pygame.Rect(54, 330, 56, 56)
        self.arrow_right = pygame.Rect(SCREEN_W - 110, 330, 56, 56)
        self.page_prev_rect = pygame.Rect(GRID_X, 634, 30, 30)
        self.page_next_rect = pygame.Rect(GRID_X + 132, 634, 30, 30)
        self._make_buttons()

    # ------------------------------------------------------------ 生命周期
    def enter(self):
        super().enter()
        try:
            self.W, self.H = self.app.screen.get_size()
        except Exception:
            self.W, self.H = SCREEN_W, SCREEN_H
        self._fonts = {}
        self._card_cache = {}
        self._bg_cache = {}
        self._cursor_shape = None
        self.world_meta = self._load_meta()
        self.worlds = self._build_worlds()
        self.index = self._initial_index()
        self.view = "carousel"
        self.detail_index = None
        self.level_cells = []
        self.level_page = 0
        self.page_count = 1
        self.per_page = LEVELS_PER_PAGE
        self.hover_level = -1
        self.dragging = False
        self._drag_off = 0
        self.toast = ui.Toast(self.app)
        self._make_buttons()
        # 旧存档可能只有星章、没有钥匙字段：进入地图时补发一次
        try:
            self.app.save.sync_keys_from_stars()
        except Exception:
            pass
        self._refresh()

    def exit(self):
        self._card_cache.clear()
        self._bg_cache.clear()
        self.dragging = False

    def update(self, dt):
        super().update(dt)
        self.toast.update(dt)

    # ------------------------------------------------------------ 数据
    def _load_meta(self) -> dict:
        try:
            raw = self.app.content_json("worldmap", default={}) or {}
        except Exception:
            raw = {}
        worlds = raw.get("worlds", {}) if isinstance(raw, dict) else {}
        if not isinstance(worlds, dict):
            return {}
        return {str(k): v for k, v in worlds.items() if isinstance(v, dict)}

    def _build_worlds(self) -> list[dict]:
        items: list[dict] = []
        try:
            defs = list(self.app.data.worlds)
        except Exception:
            defs = []

        if not defs:
            # 数据文件异常时，至少用 worldmap.json 里配置的世界兜底
            for wid, md in sorted(self.world_meta.items(),
                                  key=lambda kv: int(kv[1].get("order", 999))):
                items.append(self._make_world(wid, wid, "", 10, [], md, len(items)))
            return items

        for i, wdef in enumerate(defs):
            wid = str(getattr(wdef, "id", "") or f"world{i}")
            meta = self.world_meta.get(wid, {}) or {}
            try:
                levels = list(self.app.data.levels(wid))
            except Exception:
                levels = []
            raw_levels = getattr(wdef, "levels", 10)
            if isinstance(raw_levels, (list, tuple)):
                attr_total = len(raw_levels)
            else:
                try:
                    attr_total = int(raw_levels or 10)
                except Exception:
                    attr_total = 10
            total = len(levels) or max(0, attr_total) or 10
            zh = str(getattr(wdef, "name_zh", "") or wid)
            en = str(getattr(wdef, "name_en", "") or wid.replace("_", " ").title())
            items.append(self._make_world(wid, zh, en, total, levels, meta, i))
        return items

    def _make_world(self, wid, zh, en, total, levels, meta, pos) -> dict:
        total = max(0, int(total))
        difficulty = int(meta.get("difficulty", min(5, 1 + pos // 4)) or 1)
        difficulty = int(ui.clamp(difficulty, 1, 5))
        try:
            cost = int(meta.get("unlock_cost", 1))
        except Exception:
            cost = 1
        key_required = bool(meta.get("key_required", pos > 0))
        try:
            meta_order = int(meta.get("order", pos + 1))
        except Exception:
            meta_order = pos + 1
        # 轮播与解锁顺序都跟随 app.data.worlds 的实际顺序，
        # worldmap.json 的 order 仅作为元数据保留（避免两套顺序打架）。
        order = pos + 1
        desc = str(meta.get("desc") or "")
        name_key = str(meta.get("name_key") or f"world.{wid}.name")
        stars = self._stars_in_world(wid)
        done = self._completed_in_world(wid, total)
        tint = self._world_tint(wid)
        return {
            "id": wid,
            "zh": zh or wid,
            "en": en,
            "order": order,
            "meta_order": meta_order,
            "difficulty": difficulty,
            "unlock_cost": max(0, cost),
            "key_required": key_required,
            "name_key": name_key,
            "desc": desc,
            "total": total,
            "levels": levels,
            "done": done,
            "stars": stars,
            "cover": f"world/{wid}.png",
            "tint": tint,
        }

    def _world_tint(self, wid) -> tuple:
        try:
            for w in self.app.data.worlds:
                if str(getattr(w, "id", "")) == wid:
                    tint = getattr(w, "bg_tint", None)
                    if isinstance(tint, (list, tuple)) and len(tint) >= 3:
                        return tuple(int(ui.clamp(int(c), 0, 255)) for c in tint[:3])
        except Exception:
            pass
        return (206, 224, 180)

    def _stars_in_world(self, wid) -> int:
        prefix = f"{wid}:"
        try:
            return sum(sum(int(x) for x in val)
                       for key, val in self.app.save.stars.items()
                       if str(key).startswith(prefix))
        except Exception:
            return 0

    def _completed_in_world(self, wid, total) -> int:
        try:
            return sum(1 for i in range(total) if self.app.save.is_completed(wid, i))
        except Exception:
            return 0

    def _recount_world(self, world: dict):
        wid = world.get("id")
        total = int(world.get("total", 0) or 0)
        world["done"] = self._completed_in_world(wid, total)
        world["stars"] = self._stars_in_world(wid)

    def _initial_index(self) -> int:
        last = 0
        for i in range(len(self.worlds)):
            if self.world_unlocked(i):
                last = i
        return last

    # ------------------------------------------------------------ 解锁
    def world_unlocked(self, index: int) -> bool:
        if not self.worlds:
            return False
        index %= len(self.worlds)
        if index == 0:
            return True
        wid = self.worlds[index]["id"]
        save = self.app.save
        try:
            if save.unlocked(wid):
                return True
        except Exception:
            pass
        try:
            return wid in list(getattr(save, "unlocked_worlds", []) or [])
        except Exception:
            return False

    def first_locked_index(self) -> int | None:
        for i in range(len(self.worlds)):
            if not self.world_unlocked(i):
                return i
        return None

    def unlock_cost(self, index: int) -> int:
        if not self.worlds:
            return 0
        world = self.worlds[index % len(self.worlds)]
        if not world.get("key_required", True):
            return 0
        try:
            return max(0, int(world.get("unlock_cost", 1)))
        except Exception:
            return 1

    def unlock_world(self, index: int) -> bool:
        if not self.worlds:
            return False
        index %= len(self.worlds)
        world = self.worlds[index]
        if self.world_unlocked(index):
            self.toast.show("这个世界已经解锁了")
            return False
        first = self.first_locked_index()
        if first is None or index != first:
            self.toast.show("请先解锁顺序链上更靠前的世界")
            self._refresh()
            return False
        cost = self.unlock_cost(index)
        save = self.app.save
        keys = int(getattr(save, "keys", 0) or 0)
        if keys < cost:
            self.toast.show(f"钥匙不足：需要 {cost} 把，当前 {keys} 把")
            self._refresh()
            return False
        try:
            paid = save.spend_keys(cost)
        except Exception:
            paid = False
        if not paid:
            self.toast.show("解锁失败，请稍后再试")
            self._refresh()
            return False
        try:
            save.unlock(world["id"])
        except Exception:
            pass
        self.toast.show(f"已用 {cost} 把钥匙解锁「{world['zh']}」")
        self._card_cache.clear()
        self._layout_levels()
        self._refresh()
        return True

    def unlock_current(self) -> bool:
        index = self.detail_index if self.view == "detail" else self.index
        if index is None:
            return False
        return self.unlock_world(index)

    # ------------------------------------------------------------ 轮播
    def card_rect(self) -> pygame.Rect:
        return pygame.Rect(self.W // 2 - CARD_W // 2, CARD_TOP, CARD_W, CARD_H)

    def side_rect(self, direction: int) -> pygame.Rect:
        center = self.card_rect()
        rect = center.copy()
        if direction < 0:
            rect.x = center.x - CARD_W // 2
        else:
            rect.x = center.right - CARD_W // 2
        rect.y += SIDE_DROP
        return rect

    def _card_hover(self):
        if not self.worlds or self.dragging:
            return None
        center = self.card_rect()
        if center.collidepoint(self.mouse):
            return 0
        if len(self.worlds) > 1:
            left = self.side_rect(-1)
            right = self.side_rect(1)
            if left.collidepoint(self.mouse) and self.mouse[0] < center.left:
                return -1
            if right.collidepoint(self.mouse) and self.mouse[0] > center.right:
                return 1
        return None

    def next_world(self):
        if len(self.worlds) <= 1:
            return
        self.index = (self.index + 1) % len(self.worlds)
        self.hover_level = -1
        self._refresh()

    def prev_world(self):
        if len(self.worlds) <= 1:
            return
        self.index = (self.index - 1) % len(self.worlds)
        self.hover_level = -1
        self._refresh()

    def open_detail(self, index: int | None = None):
        if not self.worlds:
            return
        if index is None:
            index = self.index
        try:
            index = int(index)
        except Exception:
            return
        self.detail_index = index % len(self.worlds)
        self.view = "detail"
        self.level_page = 0
        self.hover_level = -1
        self._recount_world(self.worlds[self.detail_index])
        self._layout_levels()
        self._refresh()

    def open_current_detail(self):
        self.open_detail(self.index)

    def close_detail(self):
        if self.detail_index is not None:
            self.index = self.detail_index
        self.view = "carousel"
        self.detail_index = None
        self.level_cells = []
        self.hover_level = -1
        self._refresh()

    def go_back(self):
        if self.view == "detail":
            self.close_detail()
        else:
            self.app.switch("menu")

    # ------------------------------------------------------------ 详情 / 关卡
    def _layout_levels(self):
        self.level_cells = []
        self.page_count = 1
        if self.detail_index is None or not self.worlds:
            return
        world = self.worlds[self.detail_index]
        wid = world["id"]
        total = int(world.get("total", 0))
        if total <= 0:
            self.level_page = 0
            return
        per_page = LEVELS_PER_PAGE if total <= LEVELS_PER_PAGE else 15
        rows = 2 if per_page == LEVELS_PER_PAGE else 3
        self.per_page = per_page
        self.page_count = max(1, math.ceil(total / per_page))
        self.level_page = int(ui.clamp(self.level_page, 0, self.page_count - 1))
        start = self.level_page * per_page
        end = min(total, start + per_page)
        col_gap = GRID_GAP
        cell_w = (GRID_W - col_gap * (GRID_COLS - 1)) // GRID_COLS
        cell_h = (GRID_H - GRID_GAP * (rows - 1)) // rows
        world_open = self.world_unlocked(self.detail_index)
        save = self.app.save
        next_found = False
        for pos, i in enumerate(range(start, end)):
            row, col = divmod(pos, GRID_COLS)
            rect = pygame.Rect(GRID_X + col * (cell_w + col_gap),
                               GRID_Y + row * (cell_h + GRID_GAP),
                               cell_w, cell_h)
            level = world["levels"][i] if i < len(world["levels"]) else None
            title = str(getattr(level, "title", "") or f"第 {i + 1} 关")
            try:
                completed = save.is_completed(wid, i)
            except Exception:
                completed = False
            try:
                stars = save.stars_for(wid, i)
            except Exception:
                stars = [0, 0, 0]
            if i == 0:
                prev_done = True
            else:
                try:
                    prev_done = save.is_completed(wid, i - 1)
                except Exception:
                    prev_done = False
            unlocked = bool(world_open and prev_done)
            is_next = bool(unlocked and not completed and not next_found)
            if is_next:
                next_found = True
            self.level_cells.append({
                "rect": rect,
                "index": i,
                "no": i + 1,
                "title": title,
                "level": level,
                "unlocked": unlocked,
                "locked": not unlocked,
                "completed": completed,
                "stars": list(stars),
                "next": is_next,
                "world": wid,
                "page": self.level_page,
            })

    def _change_page(self, delta: int) -> bool:
        if self.page_count <= 1:
            return False
        new_page = int(ui.clamp(self.level_page + delta, 0, self.page_count - 1))
        if new_page == self.level_page:
            return False
        self.level_page = new_page
        self.hover_level = -1
        self._layout_levels()
        return True

    def _slots_for(self, cell) -> int:
        level = cell.get("level")
        try:
            bank = getattr(level, "seed_bank", None)
            count = len(bank) if isinstance(bank, (list, tuple)) else int(bank or 0)
        except Exception:
            count = 0
        if count <= 0:
            count = 6
        return max(2, min(9, int(count)))

    def enter_level(self, position: int) -> bool:
        if self.view != "detail" or self.detail_index is None:
            return False
        if position < 0 or position >= len(self.level_cells):
            return False
        world = self.worlds[self.detail_index]
        cell = self.level_cells[position]
        if not self.world_unlocked(self.detail_index):
            self.toast.show("这个世界还没有解锁")
            return False
        if cell.get("locked"):
            self.toast.show("请先通过上一关")
            return False
        self.app.open_seed_chooser(world["id"], cell["index"], self._slots_for(cell))
        return True

    def _click_level(self, pos) -> bool:
        for i, cell in enumerate(self.level_cells):
            if cell["rect"].collidepoint(pos):
                return self.enter_level(i)
        return False

    def _step_detail(self, delta: int):
        if self.detail_index is None or not self.worlds:
            return
        self.detail_index = (self.detail_index + delta) % len(self.worlds)
        self.level_page = 0
        self.hover_level = -1
        self._recount_world(self.worlds[self.detail_index])
        self._layout_levels()
        self._refresh()

    # ------------------------------------------------------------ 按钮 / 刷新
    def _make_buttons(self):
        w = self.W
        self.btn_back = ui.Button(
            self.app, (24, 26, 104, 42), "返回", on_click=self.go_back,
            style="cream", font_size=18)
        self.btn_enter = ui.Button(
            self.app, (w // 2 - 150, self.H - 126, 300, 58), "查看",
            on_click=self.open_current_detail, style="gold", font_size=22)
        self.btn_unlock = ui.Button(
            self.app, (62, 620, 308, 46), "解锁世界", on_click=self.unlock_current,
            style="primary", font_size=18, subtext="")
        self.btn_unlock.visible = False
        self.arrow_left = pygame.Rect(54, CARD_TOP + CARD_H // 2 - 28, 56, 56)
        self.arrow_right = pygame.Rect(self.W - 110,
                                       CARD_TOP + CARD_H // 2 - 28, 56, 56)

    def _refresh(self):
        self.btn_back.visible = True
        self.btn_enter.visible = self.view == "carousel"
        in_detail = self.view == "detail" and self.detail_index is not None
        locked = bool(in_detail and not self.world_unlocked(self.detail_index))
        self.btn_unlock.visible = locked
        if not locked:
            return
        index = self.detail_index
        cost = self.unlock_cost(index)
        keys = int(getattr(self.app.save, "keys", 0) or 0)
        first = self.first_locked_index()
        can_unlock = first is not None and index == first
        self.btn_unlock.set_enabled(bool(can_unlock and keys >= cost))
        if not can_unlock:
            self.btn_unlock.set_text("尚未解锁")
            self.btn_unlock.subtext = "请先解锁前面的世界"
        elif keys >= cost:
            self.btn_unlock.set_text("解锁世界")
            self.btn_unlock.subtext = f"消耗 {cost} 把钥匙 · 当前 {keys}"
        else:
            self.btn_unlock.set_text("钥匙不足")
            self.btn_unlock.subtext = f"需要 {cost} 把 · 当前 {keys}"

    def _set_cursor(self, hand: bool):
        if pygame.display.get_surface() is None:
            return
        shape = pygame.SYSTEM_CURSOR_HAND if hand else pygame.SYSTEM_CURSOR_ARROW
        if shape == self._cursor_shape:
            return
        try:
            pygame.mouse.set_cursor(shape)
            self._cursor_shape = shape
        except Exception:
            self._cursor_shape = None

    # ------------------------------------------------------------ 事件
    def handle(self, event):
        super().handle(event)
        self._refresh()
        if event.type == pygame.KEYDOWN and self._handle_key(event):
            return
        if self.btn_back is not None and self.btn_back.handle(event):
            return
        if self.view == "detail":
            self._handle_detail(event)
        else:
            self._handle_carousel(event)
        if event.type == pygame.MOUSEMOTION:
            self._update_cursor()

    def _handle_key(self, event) -> bool:
        if event.key == pygame.K_ESCAPE:
            self.go_back()
            return True
        if self.view == "carousel":
            if event.key in (pygame.K_LEFT, pygame.K_a):
                self.prev_world()
                return True
            if event.key in (pygame.K_RIGHT, pygame.K_d):
                self.next_world()
                return True
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.open_current_detail()
                return True
            return False
        # 详情
        if event.key in (pygame.K_LEFT, pygame.K_a):
            self._step_detail(-1)
            return True
        if event.key in (pygame.K_RIGHT, pygame.K_d):
            self._step_detail(1)
            return True
        if event.key == pygame.K_PAGEUP:
            self._change_page(-1)
            return True
        if event.key == pygame.K_PAGEDOWN:
            self._change_page(1)
            return True
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            for i, cell in enumerate(self.level_cells):
                if not cell["locked"] and not cell["completed"]:
                    return self.enter_level(i)
            for i, cell in enumerate(self.level_cells):
                if not cell["locked"]:
                    return self.enter_level(i)
            return True
        return False

    def _handle_carousel(self, event):
        if self.btn_enter is not None and self.btn_enter.handle(event):
            return
        if event.type == pygame.MOUSEWHEEL:
            horizontal = getattr(event, "x", 0) or 0
            vertical = getattr(event, "y", 0) or 0
            if abs(horizontal) > abs(vertical):
                if horizontal < 0:
                    self.next_world()
                elif horizontal > 0:
                    self.prev_world()
            elif vertical < 0:
                self.next_world()
            elif vertical > 0:
                self.prev_world()
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if event.pos[1] >= HUD_H:
                self.dragging = True
                self._drag_start_x = event.pos[0]
                self._drag_off = 0
            return
        if event.type == pygame.MOUSEMOTION and self.dragging:
            self._drag_off = int(ui.clamp(event.pos[0] - self._drag_start_x,
                                          -CARD_W * 0.55, CARD_W * 0.55))
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if not self.dragging:
                return
            dx = self._drag_off
            self.dragging = False
            self._drag_off = 0
            if abs(dx) >= 70:
                if dx < 0:
                    self.next_world()
                else:
                    self.prev_world()
                return
            if abs(dx) < 8:
                self._handle_click(event.pos)

    def _handle_click(self, pos):
        if self.arrow_left.collidepoint(pos):
            self.prev_world()
            return
        if self.arrow_right.collidepoint(pos):
            self.next_world()
            return
        center = self.card_rect()
        if center.collidepoint(pos):
            self.open_current_detail()
            return
        if len(self.worlds) <= 1:
            return
        left = self.side_rect(-1)
        right = self.side_rect(1)
        if left.collidepoint(pos) and pos[0] < center.left:
            self.prev_world()
        elif right.collidepoint(pos) and pos[0] > center.right:
            self.next_world()

    def _handle_detail(self, event):
        if self.btn_unlock is not None and self.btn_unlock.handle(event):
            return
        if event.type == pygame.MOUSEMOTION:
            self.hover_level = -1
            for i, cell in enumerate(self.level_cells):
                if cell["rect"].collidepoint(event.pos):
                    self.hover_level = i
                    break
            return
        if event.type == pygame.MOUSEWHEEL:
            if self.page_count > 1:
                if getattr(event, "y", 0) < 0 or getattr(event, "x", 0) < 0:
                    self._change_page(1)
                elif getattr(event, "y", 0) > 0 or getattr(event, "x", 0) > 0:
                    self._change_page(-1)
                return
            if getattr(event, "y", 0) < 0 or getattr(event, "x", 0) < 0:
                self._step_detail(1)
            elif getattr(event, "y", 0) > 0 or getattr(event, "x", 0) > 0:
                self._step_detail(-1)
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.page_count > 1:
                if self.page_prev_rect.collidepoint(event.pos):
                    self._change_page(-1)
                    return
                if self.page_next_rect.collidepoint(event.pos):
                    self._change_page(1)
                    return
            self._click_level(event.pos)

    def _update_cursor(self):
        hand = False
        if self.view == "carousel":
            hand = self._card_hover() is not None
            if self.btn_enter is not None and self.btn_enter.visible:
                hand = hand or self.btn_enter.rect.collidepoint(self.mouse)
            hand = hand or self.arrow_left.collidepoint(self.mouse) \
                or self.arrow_right.collidepoint(self.mouse)
        else:
            hand = self.hover_level >= 0
            if self.page_count > 1:
                hand = hand or self.page_prev_rect.collidepoint(self.mouse) \
                    or self.page_next_rect.collidepoint(self.mouse)
            if self.btn_unlock is not None and self.btn_unlock.visible \
                    and self.btn_unlock.enabled:
                hand = hand or self.btn_unlock.rect.collidepoint(self.mouse)
        if self.btn_back is not None and self.btn_back.rect.collidepoint(self.mouse):
            hand = True
        self._set_cursor(hand)

    # ------------------------------------------------------------ 绘制
    def draw(self, surf):
        self._refresh()
        if self.view == "detail" and self.detail_index is not None:
            self._draw_background(surf)
            self._draw_detail(surf)
            self._draw_hud(surf)
        else:
            self._draw_cinematic(surf)
        self.toast.draw(surf, (self.W // 2, self.H - 22))
        self.draw_fade(surf)

    def _font(self, size, bold=False):
        key = (int(size), bool(bold))
        font = self._fonts.get(key)
        if font is None:
            font = self.app.font(int(size), bool(bold))
            self._fonts[key] = font
        return font

    # ------------------------------------------------------------ 背景
    def _background(self, wid, tint):
        cached = self._bg_cache.get(wid)
        if cached is not None:
            return cached
        img = ui.get_image(self.app, f"world/{wid}.png")
        if img is None:
            img = ui.get_image(self.app, "ui/bg_home.jpg")
        bg = None
        if img is not None:
            try:
                small = pygame.transform.smoothscale(
                    img, (max(1, self.W // 12), max(1, self.H // 12)))
                bg = pygame.transform.smoothscale(small, (self.W, self.H))
                dark = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
                dark.fill((6, 9, 14, 146))
                bg.blit(dark, (0, 0))
                ui.draw_scrim(bg, (0, 0, self.W, 150), 110, 0, (4, 6, 10))
                ui.draw_scrim(bg, (0, self.H - 250, self.W, 250), 0, 155, (4, 6, 10))
            except Exception:
                bg = None
        self._bg_cache[wid] = bg
        return bg

    def _draw_background(self, surf):
        if self.view == "detail" and self.detail_index is not None:
            world = self.worlds[self.detail_index]
        else:
            world = self.worlds[self.index] if self.worlds else None
        bg = self._background(world["id"], world["tint"]) if world else None
        if bg is not None:
            surf.blit(bg, (0, 0))
        else:
            ui.draw_gradient(surf, (0, 0, self.W, self.H),
                             (38, 48, 56), (12, 16, 20))
            ui.draw_dim(surf, alpha=70)

    # ------------------------------------------------------------ HUD
    def _draw_hud(self, surf):
        ui.draw_gradient(surf, (0, 0, self.W, HUD_H),
                         (28, 32, 40, 240), (15, 18, 24, 240))
        pygame.draw.line(surf, ui.GOLD_DARK, (0, HUD_H - 2),
                         (self.W, HUD_H - 2), 2)
        if self.btn_back is not None:
            self.btn_back.draw(surf)

        ui.text(surf, self._font(30, True), "冒险模式", (150, 28),
                TEXT_CREAM, shadow=(10, 8, 6))
        if self.view == "detail" and self.detail_index is not None:
            world = self.worlds[self.detail_index]
            subtitle = f"{world['zh']} · 世界详情"
        else:
            subtitle = "选择世界，继续冒险"
        ui.text(surf, self._font(14, False), subtitle, (152, 66),
                TEXT_DIM, shadow=(8, 6, 4))
        self._draw_world_dots(surf)
        self._draw_counters(surf)

    def _draw_world_dots(self, surf):
        n = len(self.worlds)
        if n <= 1:
            return
        current = self.detail_index if self.view == "detail" else self.index
        spacing = 16
        total_w = (n - 1) * spacing
        start = self.W // 2 - total_w // 2
        y = HUD_H - 12
        for i in range(n):
            x = start + i * spacing
            if i == current:
                pygame.draw.circle(surf, ui.GOLD, (x, y), 5)
                pygame.draw.circle(surf, (104, 74, 34), (x, y), 5, 1)
            elif self.world_unlocked(i):
                pygame.draw.circle(surf, (198, 186, 162), (x, y), 3)
            else:
                pygame.draw.circle(surf, (96, 92, 84), (x, y), 3)

    def _draw_counters(self, surf):
        save = self.app.save
        try:
            stars = save.total_stars()
        except Exception:
            stars = 0
        keys = int(getattr(save, "keys", 0) or 0)
        coins = int(getattr(save, "coins", 0) or 0)
        x = self.W - 24
        x = self._draw_counter(surf, x, "star", stars).x - 10
        x = self._draw_counter(surf, x, "key", keys).x - 10
        self._draw_counter(surf, x, "coin", coins)

    def _draw_counter(self, surf, right_x, kind, value) -> pygame.Rect:
        font = self._font(18, True)
        text = str(int(value))
        tw = font.size(text)[0]
        w = max(76, tw + 64)
        rect = pygame.Rect(int(right_x - w), 26, int(w), 40)
        ui.draw_shadow(surf, rect, radius=20, alpha=48, offset=(0, 3), spread=3)
        ui.draw_gradient(surf, rect, (250, 244, 230), (229, 216, 194), radius=20)
        pygame.draw.rect(surf, ui.BORDER, rect, 1, border_radius=20)
        cy = rect.centery
        if kind == "star":
            draw_star_icon(surf, (rect.x + 23, cy), 11)
        elif kind == "key":
            draw_key_icon(surf, (rect.x + 24, cy), 22)
        else:
            ui.draw_coin(surf, (rect.x + 23, cy), 11)
        ui.text(surf, font, text, (rect.right - 14, cy), ui.INK, anchor="midright")
        return rect

    # ------------------------------------------------------------ 轮播绘制
    def _draw_carousel(self, surf):
        if not self.worlds:
            ui.text(surf, self._font(22, True), "还没有可用的世界数据",
                    (self.W // 2, self.H // 2), TEXT_CREAM, anchor="center")
            return
        n = len(self.worlds)
        offset = self._drag_off if self.dragging else 0
        center = self.card_rect().move(offset, 0)
        hover = self._card_hover()

        if n > 1:
            for direction in (-1, 1):
                idx = (self.index + direction) % n
                rect = self.side_rect(direction).move(offset, 0)
                self._draw_card(surf, idx, rect, side=direction,
                                hover=(hover == direction))
        self._draw_card(surf, self.index, center, side=0,
                        hover=(hover == 0))

        if n > 1:
            self._draw_arrow(surf, self.arrow_left, "left",
                             hover=self.arrow_left.collidepoint(self.mouse))
            self._draw_arrow(surf, self.arrow_right, "right",
                             hover=self.arrow_right.collidepoint(self.mouse))
        if self.btn_enter is not None:
            self.btn_enter.draw(surf)
        if not self.toast.active:
            ui.text(surf, self._font(12, False),
                    "← → / 滚轮切换世界 · 拖动或点击两侧卡片 · 点击当前卡进入世界",
                    (self.W // 2, 670), TEXT_DIM, anchor="midtop",
                    shadow=(6, 5, 4))


    # ==================================================== 电影感世界轮播（对齐原版）
    def _draw_cinematic(self, surf):
        # 深蓝夜空渐变背景
        for i in range(6):
            t = i / 5.0
            col = (int(10 + 10 * t), int(24 + 14 * t), int(44 + 18 * t))
            pygame.draw.rect(surf, col, (0, i * self.H // 6, self.W, self.H // 6 + 2))
        glow = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        for r, a in ((520, 26), (400, 20), (290, 16)):
            pygame.draw.circle(glow, (54, 132, 168, a), (self.W // 2, self.H // 2 + 30), r)
        surf.blit(glow, (0, 0))
        # 星点
        for i in range(70):
            x = (i * 197 + 53) % self.W
            y = (i * 89 + 37) % (self.H - 120) + 20
            a = 90 + (i * 13) % 110
            pygame.draw.circle(surf, (210, 226, 240, a), (x, y), 1)

        n = len(self.worlds)
        if n == 0:
            ui.text(surf, self._font(24, True), "暂无世界数据",
                    (self.W // 2, self.H // 2), TEXT_CREAM, anchor="center")
            return
        offset = self._drag_off if self.dragging else 0
        center = self.card_rect().move(offset, 0)
        hover = self._card_hover()
        for direction in (-1, 1):
            idx = (self.index + direction) % n
            rect = self.side_rect(direction).move(offset, 0)
            self._draw_island(surf, idx, rect, side=direction, hover=(hover == direction))
        self._draw_island(surf, self.index, center, side=0, hover=(hover == 0))

        if n > 1:
            self._draw_arrow(surf, self.arrow_left, "left",
                             hover=self.arrow_left.collidepoint(self.mouse))
            self._draw_arrow(surf, self.arrow_right, "right",
                             hover=self.arrow_right.collidepoint(self.mouse))
        self._draw_cinematic_button(surf)
        self._draw_topbar(surf)
        self._draw_side_letters(surf)
        self._draw_bottom_dots(surf)

    def _island_surface(self, index, size, side):
        key = (index, size, side)
        cache = getattr(self, "_island_cache", None)
        if cache is None:
            cache = self._island_cache = {}
        got = cache.get(key)
        if got is not None:
            return got
        w, h = size
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, w, h), border_radius=30)
        cover = ui.load_cover(self.app, self.worlds[index]["cover"], (w, h))
        if cover is not None:
            surf.blit(cover, (0, 0))
        else:
            ui.draw_gradient(surf, (0, 0, w, h), self.worlds[index]["tint"], (18, 26, 40), radius=30)
        # 底部压暗，便于放文字
        scrim = pygame.Surface((w, h), pygame.SRCALPHA)
        ui.draw_scrim(scrim, (0, int(h * 0.42), w, int(h * 0.58)), 0, 190, (6, 12, 20))
        surf.blit(scrim, (0, 0))
        surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        pygame.draw.rect(surf, (222, 196, 140, 220), (0, 0, w, h), 3, border_radius=30)
        cache[key] = surf
        return surf

    def _draw_island(self, surf, index, rect, side=0, hover=False):
        world = self.worlds[index]
        locked = not self.world_unlocked(index)
        size = rect.size
        img = self._island_surface(index, size, side)
        draw = img
        if side:
            draw = img.copy()
            draw.set_alpha(215 if hover else 190)
        ui.draw_shadow(surf, rect, radius=30, alpha=90 if side == 0 else 60,
                       offset=(0, 8), spread=10)
        surf.blit(draw, rect.topleft)
        if side != 0:
            return
        # 世界名
        name = world["zh"]
        font = self._font(46, True)
        ui.text(surf, font, name, (rect.centerx, rect.centery + 104), TEXT_CREAM,
                anchor="center", shadow=(10, 14, 24))
        # 难度辣椒
        self._draw_chili_row(surf, world, (rect.centerx, rect.centery + 138))
        # 关卡气泡（左下，独立于辣椒行）
        total = int(world.get("total") or 0)
        done = int(world.get("done") or 0)
        bx, by = rect.left + 52, rect.bottom - 58
        pygame.draw.circle(surf, (16, 48, 62), (bx, by), 36)
        pygame.draw.circle(surf, (70, 170, 190), (bx, by), 36, 3)
        pygame.draw.circle(surf, (24, 82, 104), (bx - 6, by), 28)
        pygame.draw.circle(surf, (150, 224, 236), (bx - 12, by - 10), 6)
        ui.text(surf, self._font(22, True), f"{done}/{total}", (bx + 48, by),
                TEXT_CREAM, anchor="midleft", shadow=(6, 8, 14))
        # 锁定
        if locked:
            ui.draw_lock(surf, (rect.centerx, rect.centery - 8), 64)
            ui.text(surf, self._font(18, True), self._lock_condition(index),
                    (rect.centerx, rect.centery + 52), TEXT_CREAM,
                    anchor="center", shadow=(8, 10, 18))

    def _draw_chili_row(self, surf, world, pos):
        diff = int(world.get("difficulty") or 4)
        diff = max(1, min(8, diff))
        total = 8
        cw = 26
        x0 = pos[0] - (total * cw) // 2 + cw // 2
        font = self._font(16, True)
        ui.text(surf, font, "难度", (x0 - 36, pos[1]), TEXT_CREAM, anchor="midright",
                shadow=(6, 8, 12))
        for i in range(total):
            filled = i < diff
            cx = x0 + i * cw
            self._draw_chili(surf, (cx, pos[1]), filled)

    def _draw_chili(self, surf, center, filled):
        cx, cy = center
        body = (206, 48, 40) if filled else (86, 92, 100)
        dark = (140, 22, 20) if filled else (58, 64, 72)
        pygame.draw.ellipse(surf, body, (cx - 8, cy - 11, 15, 22))
        pygame.draw.ellipse(surf, dark, (cx - 8, cy - 11, 15, 22), 1)
        pygame.draw.polygon(surf, dark, [(cx - 2, cy - 12), (cx + 6, cy - 18), (cx + 2, cy - 8)])
        pygame.draw.circle(surf, (240, 238, 230) if filled else (120, 126, 134),
                           (cx - 3, cy + 2), 2)

    def _draw_cinematic_button(self, surf):
        r = self.btn_enter.rect
        ui.draw_shadow(surf, r, radius=16, alpha=80, offset=(0, 5), spread=4)
        top = (150, 104, 232) if r.collidepoint(self.mouse) else (128, 84, 214)
        bottom = (100, 62, 178) if r.collidepoint(self.mouse) else (88, 54, 158)
        ui.draw_gradient(surf, r, top, bottom, radius=16)
        pygame.draw.rect(surf, (206, 186, 255), r, 2, border_radius=16)
        ui.text(surf, self._font(26, True), "查看", r.center, TEXT_CREAM, anchor="center",
                shadow=(40, 20, 70))

    def _draw_topbar(self, surf):
        # 返回
        back = pygame.Rect(20, 18, 48, 48)
        ui.alpha_rect(surf, back, (12, 22, 34, 200), radius=12)
        pygame.draw.rect(surf, (210, 198, 172), back, 2, border_radius=12)
        ui.draw_arrow(surf, back.center, "left", size=14, color=TEXT_CREAM, width=5)
        self._draw_icon_tile(surf, pygame.Rect(80, 18, 48, 48), "notebook")
        self._draw_icon_tile(surf, pygame.Rect(138, 18, 48, 48), "lock")
        self._draw_icon_tile(surf, pygame.Rect(196, 18, 48, 48), "clock", badge=True)
        self._draw_icon_tile(surf, pygame.Rect(254, 18, 48, 48), "speaker")
        # 右上角资源
        save = self.app.save
        try:
            stars = save.total_stars()
        except Exception:
            stars = 0
        keys = int(getattr(save, "keys", 0) or 0)
        coins = int(getattr(save, "coins", 0) or 0)
        x = self.W - 18
        x = self._draw_dark_counter(surf, x, "key", keys) - 8
        x = self._draw_dark_counter(surf, x, "coin", coins) - 8
        self._draw_dark_counter(surf, x, "star", stars)

    def _draw_icon_tile(self, surf, rect, kind, badge=False):
        ui.alpha_rect(surf, rect, (14, 24, 36, 210), radius=13)
        pygame.draw.rect(surf, (198, 178, 142), rect, 2, border_radius=13)
        c = (rect.centerx, rect.centery)
        if kind == "notebook":
            pygame.draw.rect(surf, (86, 140, 210), (c[0] - 11, c[1] - 14, 22, 28), border_radius=3)
            pygame.draw.rect(surf, (46, 86, 150), (c[0] - 11, c[1] - 14, 6, 28), border_radius=2)
            for i in range(4):
                pygame.draw.line(surf, (222, 234, 248), (c[0] - 3, c[1] - 8 + i * 6),
                                 (c[0] + 8, c[1] - 8 + i * 6), 1)
        elif kind == "lock":
            pygame.draw.rect(surf, (120, 126, 136), (c[0] - 13, c[1] - 12, 26, 24), border_radius=4)
            pygame.draw.arc(surf, (170, 176, 186), (c[0] - 9, c[1] - 22, 18, 20), 0, 3.14, 3)
            pygame.draw.circle(surf, (44, 48, 54), c, 3)
        elif kind == "clock":
            pygame.draw.circle(surf, (226, 178, 66), (c[0] - 4, c[1] - 4), 11)
            for i in range(8):
                a = i * 3.14159 / 4
                pygame.draw.line(surf, (236, 196, 90),
                                 (c[0] - 4 + math.cos(a) * 11, c[1] - 4 + math.sin(a) * 11),
                                 (c[0] - 4 + math.cos(a) * 15, c[1] - 4 + math.sin(a) * 15), 2)
            pygame.draw.circle(surf, (246, 244, 236), (c[0] + 8, c[1] + 8), 9)
            pygame.draw.circle(surf, (70, 70, 70), (c[0] + 8, c[1] + 8), 9, 1)
            pygame.draw.line(surf, (60, 60, 60), (c[0] + 8, c[1] + 8), (c[0] + 8, c[1] + 3), 2)
            pygame.draw.line(surf, (60, 60, 60), (c[0] + 8, c[1] + 8), (c[0] + 12, c[1] + 9), 2)
        elif kind == "speaker":
            pygame.draw.rect(surf, (150, 150, 156), (c[0] - 14, c[1] - 8, 8, 16), border_radius=2)
            pygame.draw.polygon(surf, (170, 170, 176),
                                [(c[0] - 6, c[1] - 9), (c[0] + 6, c[1] - 16),
                                 (c[0] + 6, c[1] + 16), (c[0] - 6, c[1] + 9)])
            for r in (6, 11):
                pygame.draw.arc(surf, (196, 196, 202),
                                (c[0] + 4, c[1] - r, r * 2, r * 2), -0.9, 0.9, 2)
        if badge:
            pygame.draw.circle(surf, (214, 52, 44), (rect.right - 6, rect.top + 6), 9)
            pygame.draw.circle(surf, (250, 240, 230), (rect.right - 6, rect.top + 6), 9, 1)
            ui.text(surf, self._font(11, True), "!", (rect.right - 6, rect.top + 6),
                    (255, 250, 240), anchor="center")

    def _draw_dark_counter(self, surf, right_x, kind, value):
        font = self._font(20, True)
        text = str(int(value))
        tw = font.size(text)[0]
        w = max(84, tw + 62)
        rect = pygame.Rect(int(right_x - w), 18, int(w), 44)
        ui.alpha_rect(surf, rect, (10, 20, 32, 210), radius=22)
        pygame.draw.rect(surf, (150, 134, 104), rect, 2, border_radius=22)
        cy = rect.centery
        if kind == "star":
            draw_star_icon(surf, (rect.x + 22, cy), 11)
        elif kind == "key":
            draw_key_icon(surf, (rect.x + 22, cy), 22)
        else:
            ui.draw_coin(surf, (rect.x + 22, cy), 12)
        ui.text(surf, font, text, (rect.right - 14, cy), TEXT_CREAM, anchor="midright")
        return rect.x

    def _draw_side_letters(self, surf):
        labels = ["1", "2", "3", "4", "Q", "W", "E", "R", "S", "D", "F"]
        y0 = 150
        step = (self.H - 300) / (len(labels) - 1)
        for i, lab in enumerate(labels):
            ui.text(surf, self._font(12, False), lab, (22, y0 + i * step),
                    (170, 168, 160))

    def _draw_bottom_dots(self, surf):
        n = len(self.worlds)
        if n <= 1:
            return
        spacing = 26 if n <= 30 else 18
        total_w = (n - 1) * spacing
        start = self.W // 2 - total_w // 2
        y = self.H - 22
        for i in range(n):
            x = start + i * spacing
            if i == self.index:
                pygame.draw.circle(surf, (60, 50, 26), (x, y), 8)
                pygame.draw.circle(surf, (246, 200, 72), (x, y), 7)
                pygame.draw.circle(surf, (140, 104, 40), (x, y), 8, 1)
            elif self.world_unlocked(i):
                pygame.draw.circle(surf, (222, 214, 196), (x, y), 5)
            else:
                pygame.draw.circle(surf, (96, 102, 108), (x, y), 5)

    def _lock_condition_short(self, index):
        try:
            return f"需要 {self.unlock_cost(index)} 把钥匙"
        except Exception:
            return "未解锁"

    def _draw_arrow(self, surf, rect, direction, hover=False):
        ui.draw_shadow(surf, rect, radius=28, alpha=70, offset=(0, 4), spread=5)
        bg = (52, 46, 34, 225) if hover else (24, 28, 34, 190)
        ui.alpha_rect(surf, rect, bg, radius=28)
        border = ui.GOLD if hover else (116, 102, 82)
        pygame.draw.rect(surf, border, rect, 2, border_radius=28)
        ui.draw_arrow(surf, rect.center, direction, size=15,
                      color=ui.GOLD if hover else TEXT_CREAM, width=4)

    def _card_key(self, index):
        world = self.worlds[index]
        return (world["id"], world["done"], world["stars"], world["total"],
                self.world_unlocked(index), world["order"])

    def _card_surface(self, index):
        key = self._card_key(index)
        cached = self._card_cache.get(key)
        if cached is not None:
            return cached
        world = self.worlds[index]
        surf = pygame.Surface((CARD_W, CARD_H), pygame.SRCALPHA)
        pygame.draw.rect(surf, ui.CREAM, surf.get_rect(), border_radius=24)

        cover = ui.load_cover(self.app, world["cover"], (CARD_W, COVER_H))
        layer = pygame.Surface((CARD_W, COVER_H), pygame.SRCALPHA)
        if cover is not None:
            layer.blit(cover, (0, 0))
        else:
            top = world["tint"]
            bottom = ui.shade(top, 0.55)
            ui.draw_gradient(layer, (0, 0, CARD_W, COVER_H), top, bottom)
        mask = pygame.Surface((CARD_W, COVER_H), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(),
                         border_top_left_radius=24, border_top_right_radius=24)
        layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(layer, (0, 0))
        ui.draw_scrim(surf, (0, COVER_H - 150, CARD_W, 150), 0, 200,
                      (8, 8, 10))

        # 顶部世界序号
        ui.draw_chip(surf, self.app, f"第 {world['order']} 世界", (20, 18),
                     size=12, bg=(42, 32, 22, 195), fg=TEXT_CREAM,
                     pad_x=10, pad_y=5, radius=10, border=(112, 88, 54, 180))
        # 封面上的世界名
        ui.text(surf, self._font(33, True), world["zh"], (24, COVER_H - 96),
                TEXT_CREAM, shadow=(16, 12, 8))
        ui.text(surf, self._font(14, False), world["en"].upper(), (26, COVER_H - 54),
                (232, 216, 184), shadow=(12, 9, 6))

        fy = COVER_H
        pygame.draw.line(surf, ui.BORDER, (24, fy), (CARD_W - 24, fy), 1)
        ui.text(surf, self._font(13, False), "世界进度", (24, fy + 14), ui.INK_SOFT)
        ui.text(surf, self._font(15, True),
                f"已完成 {world['done']} / {world['total']}",
                (CARD_W - 24, fy + 12), ui.INK, anchor="topright")

        bar = pygame.Rect(24, fy + 40, CARD_W - 48, 10)
        pygame.draw.rect(surf, ui.CREAM_DARK, bar, border_radius=5)
        if world["total"] > 0 and world["done"] > 0:
            fill_w = max(10, int(bar.w * min(1.0, world["done"] / world["total"])))
            color = ui.GREEN_DARK if world["done"] >= world["total"] else ui.GOLD_DARK
            pygame.draw.rect(surf, color, (bar.x, bar.y, fill_w, bar.h),
                             border_radius=5)
        pygame.draw.rect(surf, ui.BORDER, bar, 1, border_radius=5)

        star_y = fy + 76
        draw_star_icon(surf, (34, star_y), 12)
        ui.text(surf, self._font(17, True),
                f"{world['stars']} / {world['total'] * 3}",
                (54, star_y), ui.INK, anchor="midleft")
        ui.text(surf, self._font(12, False), "难度", (CARD_W - 100, star_y),
                ui.INK_SOFT, anchor="midright")
        self._draw_difficulty(surf, (CARD_W - 24, star_y), world["difficulty"])

        if world["done"] >= world["total"] > 0:
            status, status_color = "已全部完成", ui.GREEN_DARK
        elif world["done"] > 0:
            status, status_color = f"继续冒险 · 还差 {world['total'] - world['done']} 关", ui.BROWN
        else:
            status, status_color = "全新世界，等待探索", ui.BROWN
        ui.text(surf, self._font(15, True), status, (24, fy + 108),
                status_color)
        ui.text(surf, self._font(12, False), "点击卡片查看世界详情",
                (24, fy + 136), ui.INK_FAINT)
        ui.text(surf, self._font(38, True), f"{world['order']:02d}",
                (CARD_W - 22, CARD_H - 16), (226, 214, 194),
                anchor="bottomright")
        self._card_cache[key] = surf
        return surf

    def _draw_card(self, surf, index, rect, side=0, hover=False):
        world = self.worlds[index]
        base = self._card_surface(index)
        locked = not self.world_unlocked(index)
        ui.draw_shadow(surf, rect, radius=26, alpha=105 if side == 0 else 70,
                       offset=(0, 12), spread=12)
        surf.blit(base, rect.topleft)

        if locked:
            alpha = 150 if side == 0 else 190
            ui.alpha_rect(surf, rect, (14, 12, 10, alpha), radius=24)
            if side == 0:
                cx = rect.centerx
                cy = rect.y + 158
                ui.draw_lock(surf, (cx, cy), size=64)
                ui.text(surf, self._font(26, True), "未解锁", (cx, cy + 52),
                        TEXT_CREAM, anchor="center")
                ui.text(surf, self._font(14, False), self._lock_condition(index),
                        (cx, cy + 86), (232, 216, 186), anchor="center")
        elif side != 0:
            ui.alpha_rect(surf, rect, (8, 10, 12, SIDE_DIM), radius=24)

        # 右侧邻卡露出的右半边看不到卡片内左侧的标题，补一个右对齐标题
        if side > 0:
            ui.text(surf, self._font(25, True), world["zh"],
                    (rect.right - 22, rect.y + COVER_H - 94), TEXT_CREAM,
                    anchor="topright", shadow=(12, 9, 6), alpha=235)
            if world["en"]:
                ui.text(surf, self._font(12, False), world["en"].upper(),
                        (rect.right - 22, rect.y + COVER_H - 58),
                        (232, 216, 184), anchor="topright", shadow=(10, 8, 5))
            if locked:
                ui.draw_lock(surf, (rect.right - 36, rect.y + 132), size=26)

        if side == 0:
            border = (255, 226, 140) if hover else ui.GOLD
            width = 4
        else:
            border = ui.GOLD if hover else ui.BROWN_LIGHT
            width = 2
        pygame.draw.rect(surf, border, rect, width, border_radius=24)
        if side != 0 and hover:
            ui.alpha_rect(surf, rect, (255, 236, 190, 30), radius=24)

    def _draw_difficulty(self, surf, right_center, level):
        """在 right_center 右侧对齐画 5 颗难度点。"""
        level = int(ui.clamp(int(level), 0, 5))
        gap = 11
        width = 5 * gap
        x0 = right_center[0] - width + gap // 2
        for i in range(5):
            cx = int(x0 + i * gap)
            cy = int(right_center[1])
            if i < level:
                pygame.draw.circle(surf, ui.GOLD, (cx, cy), 4)
                pygame.draw.circle(surf, ui.GOLD_DARK, (cx, cy), 4, 1)
            else:
                pygame.draw.circle(surf, ui.CREAM_DARK, (cx, cy), 4)
                pygame.draw.circle(surf, ui.BORDER, (cx, cy), 4, 1)

    def _lock_condition(self, index) -> str:
        world = self.worlds[index]
        cost = self.unlock_cost(index)
        first = self.first_locked_index()
        if first is not None and index != first:
            prev = self.worlds[index - 1]["zh"] if index > 0 else "前一个世界"
            return f"请先解锁「{prev}」"
        if cost <= 0:
            return "可直接解锁"
        keys = int(getattr(self.app.save, "keys", 0) or 0)
        if keys < cost:
            return f"需要 {cost} 把钥匙（当前 {keys}）"
        return f"需要 {cost} 把钥匙"

    # ------------------------------------------------------------ 详情绘制
    def _draw_detail(self, surf):
        if not self.worlds or self.detail_index is None:
            return
        world = self.worlds[self.detail_index]
        locked = not self.world_unlocked(self.detail_index)
        save = self.app.save
        keys = int(getattr(save, "keys", 0) or 0)
        total = int(world.get("total", 0))
        done = int(world.get("done", 0))
        stars = int(world.get("stars", 0))

        # ---- 左：世界信息 ----
        ui.draw_panel(surf, DETAIL_LEFT, fill=ui.PAPER, radius=20, shadow_alpha=95)
        cover_rect = pygame.Rect(62, 134, 308, 170)
        ui.draw_shadow(surf, cover_rect, radius=14, alpha=55, offset=(0, 4), spread=4)
        cover = ui.load_cover(self.app, world["cover"], cover_rect.size)
        if cover is not None:
            layer = pygame.Surface(cover_rect.size, pygame.SRCALPHA)
            layer.blit(cover, (0, 0))
            mask = pygame.Surface(cover_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(),
                             border_radius=14)
            layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surf.blit(layer, cover_rect.topleft)
        else:
            ui.draw_gradient(surf, cover_rect, world["tint"],
                             ui.shade(world["tint"], 0.55), radius=14)
        pygame.draw.rect(surf, ui.GOLD_DARK, cover_rect, 2, border_radius=14)

        ui.text(surf, self._font(28, True), world["zh"], (62, 312), ui.INK)
        if world["en"]:
            ui.text(surf, self._font(13, False), world["en"].upper(), (63, 350),
                    ui.INK_SOFT)
        ui.text(surf, self._font(12, False), "难度", (296, 351), ui.INK_SOFT,
                anchor="topright")
        self._draw_difficulty(surf, (370, 359), world["difficulty"])

        desc = world.get("desc") or "这个世界的资料还在整理中。"
        ui.draw_wrapped(surf, self._font(13, False), desc,
                        pygame.Rect(62, 380, 308, 90), color=ui.INK_SOFT,
                        line_height=19, max_lines=4)

        ui.text(surf, self._font(13, False), "世界进度", (62, 484), ui.INK_SOFT)
        ui.text(surf, self._font(16, True), f"{done} / {total}", (370, 482),
                ui.INK, anchor="topright")
        bar = pygame.Rect(62, 510, 308, 12)
        pygame.draw.rect(surf, ui.CREAM_DARK, bar, border_radius=6)
        if total > 0 and done > 0:
            fill_w = max(12, int(bar.w * min(1.0, done / total)))
            color = ui.GREEN_DARK if done >= total else ui.GOLD_DARK
            pygame.draw.rect(surf, color, (bar.x, bar.y, fill_w, bar.h),
                             border_radius=6)
        pygame.draw.rect(surf, ui.BORDER, bar, 1, border_radius=6)

        draw_star_icon(surf, (74, 548), 13)
        ui.text(surf, self._font(18, True), f"{stars} / {total * 3}", (94, 548),
                ui.INK, anchor="midleft")
        ui.text(surf, self._font(12, False), "星章", (370, 548), ui.INK_SOFT,
                anchor="midright")

        pygame.draw.line(surf, ui.BORDER, (62, 572), (370, 572), 1)
        if locked:
            first = self.first_locked_index()
            can_unlock = first is not None and self.detail_index == first
            color = (150, 70, 48) if can_unlock else ui.INK_SOFT
            cond = "解锁条件：" + self._lock_condition(self.detail_index)
            ui.draw_wrapped(surf, self._font(13, False), cond,
                            pygame.Rect(62, 578, 308, 40), color=color,
                            line_height=18, max_lines=2)
            if self.btn_unlock is not None:
                self.btn_unlock.draw(surf)
        else:
            ui.draw_chip(surf, self.app, "已解锁", (62, 580), size=13,
                         bg=(224, 238, 210), fg=ui.GREEN_DARK,
                         border=(158, 186, 132), pad_x=10, pad_y=4)
            ui.text(surf, self._font(13, False), "点击右侧关卡开始冒险",
                    (62, 618), ui.INK_FAINT)

        # ---- 右：关卡网格 ----
        ui.draw_panel(surf, DETAIL_RIGHT, fill=ui.PAPER, radius=20, shadow_alpha=95)
        ui.text(surf, self._font(22, True), "关卡", (430, 128), ui.INK)
        ui.text(surf, self._font(13, False), f"共 {total} 关 · 已完成 {done}",
                (430, 158), ui.INK_SOFT)
        ui.text(surf, self._font(16, True), f"{done} / {total}", (1218, 132),
                ui.BROWN, anchor="topright")
        pygame.draw.line(surf, ui.BORDER, (430, 168), (1218, 168), 1)

        for cell in self.level_cells:
            self._draw_level_cell(surf, cell, locked)

        if self.page_count > 1:
            for rect, direction, enabled in (
                    (self.page_prev_rect, "left", self.level_page > 0),
                    (self.page_next_rect, "right",
                     self.level_page < self.page_count - 1)):
                hover = bool(rect.collidepoint(self.mouse)) and enabled
                fill = (255, 247, 218) if hover else (240, 233, 218)
                if not enabled:
                    fill = (232, 226, 214)
                pygame.draw.rect(surf, fill, rect, border_radius=9)
                pygame.draw.rect(surf, ui.GOLD_DARK if hover else ui.BORDER,
                                 rect, 1, border_radius=9)
                ui.draw_arrow(surf, rect.center, direction, size=8,
                              color=ui.BROWN_DEEP if enabled else ui.INK_FAINT,
                              width=3)
            page_center = ((self.page_prev_rect.right + self.page_next_rect.left)
                           // 2, self.page_prev_rect.centery)
            ui.text(surf, self._font(12, True),
                    f"第 {self.level_page + 1} / {self.page_count} 页",
                    page_center, ui.INK_SOFT, anchor="center")
            if not self.toast.active:
                ui.text(surf, self._font(12, False),
                        "滚轮翻页 · ← / → 切换世界 · ESC 返回",
                        (1218, 672), ui.INK_FAINT, anchor="topright")
        elif not self.toast.active:
            ui.text(surf, self._font(12, False),
                    "点击关卡进入选卡 · ← / → 切换世界 · ESC 返回",
                    (430, 644), ui.INK_FAINT)
        ui.text(surf, self._font(12, False), f"钥匙 {keys}", (370, 668),
                ui.INK_SOFT, anchor="topright")

    def _draw_level_cell(self, surf, cell, world_locked):
        rect = cell["rect"]
        stars = cell["stars"]
        filled = sum(1 for s in stars if s)
        locked = bool(cell["locked"])
        completed = bool(cell["completed"])
        hover = bool(rect.collidepoint(self.mouse) and not locked)
        small = rect.h < 120

        fill = ui.CREAM
        if completed:
            fill = (240, 247, 233)
        if hover:
            fill = (255, 251, 238)
        if locked:
            fill = (236, 231, 220)
        ui.draw_shadow(surf, rect, radius=14, alpha=38, offset=(0, 3), spread=3)
        pygame.draw.rect(surf, fill, rect, border_radius=14)
        border = ui.BORDER
        width = 1
        if hover:
            border, width = ui.GOLD, 3
        elif completed:
            border = (150, 186, 126)
            width = 2
        elif cell.get("next"):
            border, width = ui.GOLD_DARK, 3
        pygame.draw.rect(surf, border, rect, width, border_radius=14)

        badge_r = 13 if small else 16
        bx = rect.x + 14 + badge_r
        by = rect.y + 12 + badge_r
        badge_color = (150, 142, 128) if locked else ui.BROWN_DEEP
        pygame.draw.circle(surf, badge_color, (bx, by), badge_r)
        pygame.draw.circle(surf, (44, 32, 20), (bx, by), badge_r, 1)
        ui.text(surf, self._font(13 if small else 15, True), str(cell["no"]),
                (bx, by), TEXT_CREAM, anchor="center")

        title_x = bx + badge_r + 7
        reserve = 58 if cell.get("next") else 8
        title_w = max(20, rect.right - title_x - reserve)
        title_font = self._font(12 if small else 14, True)
        ui.draw_wrapped(surf, title_font, cell["title"],
                        pygame.Rect(title_x, rect.y + 10, title_w,
                                    30 if small else 46),
                        color=ui.INK_FAINT if locked else ui.INK,
                        line_height=16 if small else 18, max_lines=2)

        level = cell.get("level")
        info = ""
        if locked:
            info = "未解锁"
        elif completed:
            info = "已通关"
        elif level is not None:
            try:
                sun = int(getattr(level, "sun", 0) or 0)
            except Exception:
                sun = 0
            waves = getattr(level, "waves", None) or []
            try:
                n_waves = len(waves) if isinstance(waves, (list, tuple)) else int(waves)
            except Exception:
                n_waves = 0
            parts = []
            if sun > 0:
                parts.append(f"阳光 {sun}")
            if n_waves > 0:
                parts.append(f"{n_waves} 波")
            info = " · ".join(parts)
        if info:
            info_color = (150, 136, 118) if locked else ui.INK_FAINT
            ui.text(surf, self._font(10, False), info,
                    (title_x, rect.y + (54 if small else 68)),
                    info_color, shadow=None)

        star_y = rect.bottom - (16 if small else 22)
        star_r = 6 if small else 8
        for k in range(3):
            on = k < filled
            draw_star_icon(surf, (rect.x + 16 + k * (star_r * 2 + 3), star_y),
                           star_r,
                           fill=ui.GOLD if on else (222, 214, 198),
                           edge=ui.GOLD_DARK if on else ui.BORDER,
                           width=1)
        ui.text(surf, self._font(11, True), f"{filled}/3",
                (rect.right - 10, star_y), ui.INK_FAINT, anchor="midright")

        if cell.get("next"):
            ui.draw_chip(surf, self.app, "继续", (rect.right - 8, rect.y + 8),
                         size=10, bg=ui.GOLD, fg=(96, 58, 26),
                         border=ui.GOLD_DARK, anchor="topright",
                         pad_x=6, pad_y=3)
        if hover:
            ui.draw_chip(surf, self.app, "进入", (rect.right - 8, rect.bottom - 8),
                         size=10, bg=(255, 238, 188), fg=ui.BROWN,
                         border=ui.GOLD_DARK, anchor="bottomright",
                         pad_x=6, pad_y=3)
