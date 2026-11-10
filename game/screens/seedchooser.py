"""卡组选择：从可用植物里挑出本关要带的种子包。

进入方式：``app.open_seed_chooser(world_id, index, slots)``，参数放在
``app.ui_payload = {"world", "index", "slots"}``；开始游戏时把选中的植物 id
写回 ``app.pending_deck`` 并调用 ``app.start_level(world, index, deck=...)``。
"""
from __future__ import annotations

import math

import pygame

from .base import Screen
from . import widgets as ui

WIN_W, WIN_H = 1280, 720
CARD_W, CARD_H = 86, 108
GAP_X, GAP_Y = 8, 8
COLS = 11
GRID_X = 72
GRID_Y = 132
GRID_BOTTOM = WIN_H - 112


def _font(app, size, bold=False):
    try:
        return app.font(size, bold)
    except Exception:
        try:
            return app.assets.font(size, bold)
        except Exception:
            return pygame.font.Font(None, int(size))


class SeedChooserScreen(Screen):
    name = "seedchooser"

    def __init__(self, app):
        super().__init__(app)
        self._fonts = {}
        self._bg = None
        self.toast = ui.Toast(app)
        self.world_id = "frontyard"
        self.level_index = 0
        self.slots = 6
        self.level_title = ""
        self.world_name = ""
        self.selected: list[str] = []
        self.cards: list[dict] = []
        self.scroll = 0.0
        self.max_scroll = 0.0
        self.btn_clear = ui.Button(app, (WIN_W - 470, WIN_H - 86, 130, 50),
                                   "清空", on_click=self._clear, style="cream",
                                   font_size=18)
        self.btn_back = ui.Button(app, (WIN_W - 320, WIN_H - 86, 130, 50),
                                  "返回", on_click=self._back, style="cream",
                                  font_size=18)
        self.btn_start = ui.Button(app, (WIN_W - 170, WIN_H - 86, 140, 50),
                                   "开始", on_click=self._start,
                                   style="primary", font_size=19,
                                   enabled=False)

    # ------------------------------------------------------------ 生命周期
    def enter(self):
        super().enter()
        payload = getattr(self.app, "ui_payload", None)
        if not isinstance(payload, dict):
            payload = {}
        if not payload:
            # 允许直接构造后手动指定参数
            payload = {"world": getattr(self, "world_id", "frontyard"),
                       "index": getattr(self, "level_index", 0),
                       "slots": getattr(self, "slots", 6)}
        self.world_id = str(payload.get("world") or "frontyard")
        try:
            self.level_index = int(payload.get("index", 0) or 0)
        except (TypeError, ValueError):
            self.level_index = 0
        try:
            self.slots = max(1, int(payload.get("slots", 6) or 6))
        except (TypeError, ValueError):
            self.slots = 6
        self._bg = None
        self.scroll = 0.0

        try:
            world = self.app.data.world(self.world_id)
            self.world_name = str(getattr(world, "name_zh", self.world_id))
        except Exception:
            self.world_name = self.world_id

        default_deck = []
        try:
            levels = self.app.data.levels(self.world_id)
            level = levels[self.level_index]
            self.level_title = str(getattr(level, "title", "") or "")
            default_deck = list(getattr(level, "deck", []) or [])
            seed_bank = getattr(level, "seed_bank", None)
            if payload.get("slots") is None and seed_bank:
                self.slots = max(1, int(seed_bank))
        except Exception:
            if not self.level_title:
                self.level_title = f"第 {self.level_index + 1} 关"

        self._build_cards()
        available = {c["pdef"].id for c in self.cards}
        self.selected = [pid for pid in default_deck
                         if pid in available][: self.slots]
        self._sync_start_button()
        try:
            self.app.audio.play_menu()
        except Exception:
            pass

    def exit(self):
        self._bg = None

    # ------------------------------------------------------------ 数据
    def _plant_defs(self):
        try:
            plants = list(self.app.data.plants.values())
        except Exception:
            plants = []
        def _key(pdef):
            try:
                no = int(getattr(pdef, "almanac_no", 999) or 999)
            except (TypeError, ValueError):
                no = 999
            return (no, str(getattr(pdef, "id", "")))
        return sorted(plants, key=_key)

    def _build_cards(self):
        self.cards = []
        for i, pdef in enumerate(self._plant_defs()):
            row, col = divmod(i, COLS)
            rect = pygame.Rect(GRID_X + col * (CARD_W + GAP_X),
                               GRID_Y + row * (CARD_H + GAP_Y),
                               CARD_W, CARD_H)
            self.cards.append({"rect": rect, "pdef": pdef,
                               "icon": self._icon(pdef)})
        rows = max(1, int(math.ceil(len(self.cards) / float(COLS))))
        content_h = rows * CARD_H + (rows - 1) * GAP_Y
        view_h = GRID_BOTTOM - GRID_Y
        self.max_scroll = float(max(0, content_h - view_h))
        self.scroll = max(0.0, min(self.scroll, self.max_scroll))

    def _icon(self, pdef):
        art = str(getattr(pdef, "art", "") or "")
        if not art:
            return None
        try:
            img = self.app.assets.db_thumb(art, 58, 58)
            if img is not None:
                return img
        except Exception:
            pass
        try:
            return self.app.assets.static_sprite(art, 58)
        except Exception:
            return None

    def _cooldown(self, pdef):
        try:
            value = float(getattr(pdef, "cooldown", 0) or 0)
        except (TypeError, ValueError):
            return ""
        if value <= 0:
            return ""
        if value >= 10:
            return f"{value:.0f}s"
        return f"{value:.1f}s"

    def _sync_start_button(self):
        full = len(self.selected) >= self.slots
        self.btn_start.set_enabled(full)
        label = "开始" if full else f"开始 {len(self.selected)}/{self.slots}"
        try:
            self.btn_start.set_text(label)
        except Exception:
            self.btn_start.label = label

    # ------------------------------------------------------------ 动作
    def _back(self):
        self.app.switch("worldmap")

    def _clear(self):
        self.selected = []
        self._sync_start_button()

    def _toggle(self, pid):
        if pid in self.selected:
            self.selected.remove(pid)
            self._sync_start_button()
            return
        if len(self.selected) >= self.slots:
            self.toast.show(f"最多只能带 {self.slots} 张种子包", 2.0)
            return
        self.selected.append(pid)
        self._sync_start_button()

    def _start(self):
        if len(self.selected) < self.slots:
            self.toast.show(f"请选满 {self.slots} 张种子包", 2.0)
            return
        deck = list(self.selected)
        try:
            self.app.ui_result = list(deck)
        except Exception:
            pass
        try:
            self.app.pending_deck = list(deck)
        except Exception:
            pass
        try:
            self.app.start_level(self.world_id, self.level_index, deck=deck)
            return
        except TypeError:
            pass
        except Exception as exc:
            self.toast.show(f"无法开始关卡：{exc}", 2.6)
            return
        try:
            self.app.start_level(self.world_id, self.level_index)
        except Exception as exc:
            self.toast.show(f"无法开始关卡：{exc}", 2.6)

    # ------------------------------------------------------------ 事件
    def _grid_rect(self):
        return pygame.Rect(0, GRID_Y - 4, WIN_W, GRID_BOTTOM - GRID_Y + 8)

    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._back()
            return
        if self.btn_clear.handle(event) or self.btn_back.handle(event):
            return
        if self.btn_start.handle(event):
            return
        if event.type == pygame.MOUSEWHEEL:
            if self._grid_rect().collidepoint(pygame.mouse.get_pos()):
                self.scroll = max(0.0, min(self.scroll - event.y * 56,
                                           self.max_scroll))
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if not self._grid_rect().collidepoint(event.pos):
                return
            for card in self.cards:
                rect = card["rect"].move(0, -int(self.scroll))
                if rect.collidepoint(event.pos):
                    self._toggle(card["pdef"].id)
                    return

    def update(self, dt):
        super().update(dt)
        self.toast.update(dt)
        for btn in (self.btn_clear, self.btn_back, self.btn_start):
            btn.update(dt)

    # ------------------------------------------------------------ 绘制
    def _font_cached(self, size, bold=False):
        key = (int(size), bool(bold))
        font = self._fonts.get(key)
        if font is None:
            font = _font(self.app, size, bold)
            self._fonts[key] = font
        return font

    def _build_bg(self):
        surf = pygame.Surface((WIN_W, WIN_H))
        img = None
        try:
            img = ui.load_cover(self.app, f"lawn/{self.world_id}.png",
                                (WIN_W, WIN_H))
        except Exception:
            img = None
        if img is not None:
            surf.blit(img, (0, 0))
        else:
            ui.draw_gradient(surf, (0, 0, WIN_W, WIN_H),
                             (78, 96, 62), (26, 32, 22))
        ui.draw_dim(surf, None, 190, (12, 16, 12))
        return surf

    def draw(self, surf):
        if self._bg is None:
            self._bg = self._build_bg()
        surf.blit(self._bg, (0, 0))

        ui.draw_gradient(surf, (0, 0, WIN_W, 112), (62, 48, 34), (36, 28, 20))
        pygame.draw.line(surf, ui.GOLD, (0, 111), (WIN_W, 111), 2)
        ui.text(surf, self._font_cached(30, True), "选择你的种子包", (40, 18),
                ui.CREAM, shadow=(20, 14, 10))
        ui.text(surf, self._font_cached(15),
                (self.level_title if self.world_name and self.world_name in self.level_title
             else f"{self.world_name} · {self.level_title}"),
                (42, 60), (232, 214, 182))
        ui.draw_chip(surf, self.app, f"{len(self.selected)}/{self.slots}",
                     (WIN_W - 40, 34), size=17, bg=(30, 26, 18),
                     fg=(255, 232, 168), pad_x=14, pad_y=7, radius=10,
                     anchor="topright", border=(150, 126, 78))

        old_clip = surf.get_clip()
        surf.set_clip(self._grid_rect())
        for card in self.cards:
            self._draw_card(surf, card)
        surf.set_clip(old_clip)

        if self.max_scroll > 0:
            track = pygame.Rect(WIN_W - 26, GRID_Y, 8, GRID_BOTTOM - GRID_Y)
            ui.alpha_rect(surf, track, (20, 18, 14, 130), radius=4)
            view_h = GRID_BOTTOM - GRID_Y
            frac = view_h / (view_h + self.max_scroll)
            h = max(40, int(view_h * frac))
            t = self.scroll / self.max_scroll if self.max_scroll else 0.0
            thumb = pygame.Rect(track.x, track.y + int((view_h - h) * t),
                                track.w, h)
            pygame.draw.rect(surf, (198, 172, 126), thumb, border_radius=4)

        # 托盘区先用不透明底色盖住，避免下一行卡片半透明透出
        ui.draw_gradient(surf, (0, GRID_BOTTOM - 4, WIN_W,
                                WIN_H - GRID_BOTTOM + 4),
                         (34, 40, 30), (18, 22, 16))
        self._draw_tray(surf)
        self.btn_clear.draw(surf)
        self.btn_back.draw(surf)
        self.btn_start.draw(surf)
        ui.text(surf, self._font_cached(13),
                f"点击卡片加入卡组 · 最多 {self.slots} 张 · ESC 返回地图",
                (40, WIN_H - 22), (206, 196, 172))
        self.toast.draw(surf)
        self.draw_fade(surf)

    def _draw_card(self, surf, card):
        rect = card["rect"].move(0, -int(self.scroll))
        if rect.bottom < GRID_Y - 8 or rect.y > GRID_BOTTOM + 8:
            return
        pdef = card["pdef"]
        hover = rect.collidepoint(self.mouse)
        picked = pdef.id in self.selected
        body = rect.move(0, -2) if hover else rect
        if picked:
            pygame.draw.rect(surf, (84, 104, 54), body, border_radius=10)
            pygame.draw.rect(surf, ui.GOLD, body, 3, border_radius=10)
        else:
            ui.alpha_rect(surf, body, (18, 22, 16, 172), radius=10)
            pygame.draw.rect(surf, (92, 82, 64), body, 2, border_radius=10)

        icon = card["icon"]
        if icon is not None:
            ir = icon.get_rect(midtop=(body.centerx, body.y + 4))
            surf.blit(icon, ir)
        else:
            pygame.draw.circle(surf, (86, 120, 72),
                               (body.centerx, body.y + 38), 24)
            ui.text(surf, self._font_cached(16, True),
                    str(getattr(pdef, "name_zh", "?"))[:1],
                    (body.centerx, body.y + 38), ui.CREAM, anchor="center")

        ui.text(surf, self._font_cached(13, True),
                ui.fit_text(self._font_cached(13, True),
                            str(getattr(pdef, "name_zh", "?")), body.w - 4),
                (body.centerx, body.bottom - 38), ui.CREAM, anchor="center",
                shadow=(14, 12, 8))
        try:
            cost = int(getattr(pdef, "cost", 0) or 0)
        except (TypeError, ValueError):
            cost = 0
        ui.text(surf, self._font_cached(11), f"{cost} 阳光",
                (body.centerx, body.bottom - 21), (247, 214, 120),
                anchor="center")
        cd = self._cooldown(pdef)
        if cd:
            ui.text(surf, self._font_cached(10), f"CD {cd}",
                    (body.centerx, body.bottom - 7), (176, 196, 166),
                    anchor="center")
        if picked:
            idx = self.selected.index(pdef.id) + 1
            badge = pygame.Rect(0, 0, 22, 22)
            badge.topright = (body.right - 4, body.y + 4)
            pygame.draw.circle(surf, ui.GOLD, badge.center, 11)
            ui.text(surf, self._font_cached(13, True), str(idx),
                    badge.center, (48, 34, 16), anchor="center")

    def _draw_tray(self, surf):
        rect = pygame.Rect(40, WIN_H - 96, WIN_W - 540, 66)
        ui.alpha_rect(surf, rect, (14, 18, 12, 172), radius=12)
        pygame.draw.rect(surf, (108, 94, 70), rect, 2, border_radius=12)
        ui.text(surf, self._font_cached(14), "已选",
                (rect.x + 14, rect.centery), (214, 202, 176),
                anchor="midleft")
        x = rect.x + 64
        step = min(52, max(34, (rect.w - 90) // max(1, self.slots)))
        for i in range(self.slots):
            slot = pygame.Rect(x + i * step, rect.y + 13, step - 6, 40)
            if i < len(self.selected):
                pdef = self.app.data.plants.get(self.selected[i])
                pygame.draw.rect(surf, (70, 92, 52), slot, border_radius=8)
                pygame.draw.rect(surf, ui.GOLD_DARK, slot, 2, border_radius=8)
                if pdef is not None:
                    icon = None
                    try:
                        icon = self.app.assets.db_thumb(pdef.art, 30, 30)
                    except Exception:
                        icon = None
                    if icon is not None:
                        surf.blit(icon, icon.get_rect(center=slot.center))
                    else:
                        ui.text(surf, self._font_cached(12),
                                str(getattr(pdef, "name_zh", "?"))[:2],
                                slot.center, ui.CREAM, anchor="center")
                ui.text(surf, self._font_cached(11), str(i + 1),
                        (slot.x + 3, slot.y + 1), (238, 226, 196))
            else:
                pygame.draw.rect(surf, (30, 34, 26), slot, border_radius=8)
                pygame.draw.rect(surf, (70, 64, 52), slot, 1, border_radius=8)


__all__ = ["SeedChooserScreen"]
