"""生存无尽：选择世界，尽可能久地守住草坪。"""
from __future__ import annotations

import pygame

from .base import Screen
from . import widgets as ui

WIN_W, WIN_H = 1280, 720
CARD_W, CARD_H = 240, 150
GAP_X, GAP_Y = 18, 18
COLS = 4
GRID_X = 100
GRID_Y = 170


def _font(app, size, bold=False):
    try:
        return app.font(size, bold)
    except Exception:
        try:
            return app.assets.font(size, bold)
        except Exception:
            return pygame.font.Font(None, int(size))


class SurvivalHubScreen(Screen):
    name = "survival"

    def __init__(self, app):
        super().__init__(app)
        self._fonts = {}
        self._bg = None
        self.toast = ui.Toast(app)
        self.worlds = []
        self.cards = []
        self.btn_back = ui.Button(app, (24, 22, 110, 46), "返回",
                                  on_click=self._back, style="cream",
                                  font_size=18)
        self._layout()

    def _layout(self):
        self.cards = []
        for i, world in enumerate(self.worlds):
            row, col = divmod(i, COLS)
            rect = pygame.Rect(GRID_X + col * (CARD_W + GAP_X),
                               GRID_Y + row * (CARD_H + GAP_Y),
                               CARD_W, CARD_H)
            self.cards.append((rect, world))

    def enter(self):
        super().enter()
        self.worlds = list(self.app.data.worlds)
        self._layout()
        try:
            self.app.audio.play_menu()
        except Exception:
            pass

    def exit(self):
        self._bg = None

    def _back(self):
        self.app.switch("modes")

    def _open(self, world):
        best = 0
        try:
            best = int(self.app.save.best_survival.get(world.id, 0) or 0)
        except Exception:
            best = 0
        self.app.ui_payload = {"world": world.id, "best": best}
        try:
            self.app.start_survival(world.id)
        except KeyError:
            self.toast.show("生存模式界面尚未接入", 2.2)
        except Exception as exc:
            self.toast.show(f"无法进入生存模式：{exc}", 2.4)

    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._back()
            return
        if self.btn_back.handle(event):
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            for rect, world in self.cards:
                if rect.collidepoint(event.pos):
                    self._open(world)
                    return

    def update(self, dt):
        super().update(dt)
        self.toast.update(dt)
        self.btn_back.update(dt)

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
            img = ui.load_cover(self.app, "lawn/frontyard.png", (WIN_W, WIN_H))
        except Exception:
            img = None
        if img is not None:
            surf.blit(img, (0, 0))
        else:
            ui.draw_gradient(surf, (0, 0, WIN_W, WIN_H),
                             (74, 96, 62), (24, 30, 22))
        ui.draw_dim(surf, None, 196, (12, 16, 12))
        return surf

    def draw(self, surf):
        if self._bg is None:
            self._bg = self._build_bg()
        surf.blit(self._bg, (0, 0))
        ui.draw_gradient(surf, (0, 0, WIN_W, 104), (58, 72, 46), (32, 42, 26))
        pygame.draw.line(surf, ui.GOLD, (0, 103), (WIN_W, 103), 2)
        ui.text(surf, self._font_cached(30, True), "生存无尽", (160, 20),
                ui.CREAM, shadow=(20, 14, 10))
        ui.text(surf, self._font_cached(15),
                "一波接一波，看你能在草坪上坚持多久",
                (162, 62), (228, 232, 200))
        self.btn_back.draw(surf)
        for rect, world in self.cards:
            self._draw_card(surf, rect, world)
        ui.text(surf, self._font_cached(14),
                "点击世界开始 · 分数 = 击杀 + 轮次奖励 · ESC 返回",
                (WIN_W // 2, WIN_H - 32), (208, 220, 190), anchor="center")
        self.toast.draw(surf)
        self.draw_fade(surf)

    def _draw_card(self, surf, rect, world):
        hover = rect.collidepoint(self.mouse)
        body = rect.move(0, -3) if hover else rect
        ui.draw_shadow(surf, body, radius=14, alpha=90,
                       offset=(0, 6 if hover else 4))
        ui.draw_gradient(surf, body, (92, 118, 70), (56, 78, 46), radius=14)
        pygame.draw.rect(surf, ui.GOLD if hover else (132, 152, 100), body, 3,
                         border_radius=14)
        best = 0
        try:
            best = int(self.app.save.best_survival.get(world.id, 0) or 0)
        except Exception:
            best = 0
        ui.text(surf, self._font_cached(22, True),
                ui.fit_text(self._font_cached(22, True), world.name_zh,
                            body.w - 24),
                (body.centerx, body.y + 24), ui.CREAM, anchor="center",
                shadow=(18, 16, 10))
        ui.text(surf, self._font_cached(13),
                ui.fit_text(self._font_cached(13), world.desc_zh or "",
                            body.w - 24),
                (body.centerx, body.y + 62), (226, 234, 206), anchor="center")
        ui.draw_chip(surf, self.app, f"最佳 {best}", (body.centerx, body.bottom - 44),
                     size=13, bg=(26, 34, 22), fg=ui.GOLD, pad_x=12, pad_y=4,
                     radius=8)


class SurvivalScreen(Screen):
    name = "survival_level"

    def __init__(self, app):
        super().__init__(app)
        self._fonts = {}
        self.toast = ui.Toast(app)
        self.world_id = "frontyard"
        self.world = None
        self.session = None
        self.error = ""
        self._finish_applied = False
        self._bg_surf = None
        self._bg_world = None
        self.btn_back = ui.Button(app, (1152, 666, 108, 38), "返回",
                                  on_click=self._back, style="cream",
                                  font_size=16)
        self.btn_result_back = ui.Button(app, (360, 452, 264, 56), "返回列表",
                                         on_click=self._back, style="cream",
                                         font_size=20)
        self.btn_replay = ui.Button(app, (656, 452, 264, 56), "再来一局",
                                    on_click=self._replay, style="primary",
                                    font_size=20)

    def enter(self):
        super().enter()
        payload = getattr(self.app, "ui_payload", None) or {}
        self.world_id = str(payload.get("world", "frontyard"))
        self._build_session()

    def exit(self):
        self.session = None

    def _build_session(self):
        self.session = None
        self.error = ""
        self._finish_applied = False
        try:
            from ..engine.modes import SurvivalSession
            self.world = self.app.data.world(self.world_id)
            self.session = SurvivalSession(
                self.app, self.world, on_finish=self._on_finish)
            try:
                self.app.audio.play_world(self.world_id)
            except Exception:
                pass
        except Exception as exc:
            self.error = f"生存模式初始化失败：{exc}"

    def _on_finish(self, won=False, *args, **kwargs):
        if self._finish_applied:
            return
        self._finish_applied = True
        score = int(getattr(self.session, "score", 0) or 0)
        try:
            self.app.finish_survival(self.world_id, score)
        except Exception:
            pass
        try:
            self.app.audio.play_jingle("victory" if won else "defeat")
        except Exception:
            pass

    def _back(self):
        self.app.switch("survival")

    def _replay(self):
        self._build_session()

    def _status(self):
        return str(getattr(self.session, "status", "none")) \
            if self.session is not None else "none"

    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._back()
            return
        if self._status() != "playing":
            self.btn_result_back.handle(event)
            self.btn_replay.handle(event)
            return
        if self.session is None:
            self.btn_back.handle(event)
            return
        self.btn_back.handle(event)
        try:
            self.session.handle_event(event)
        except Exception as exc:
            self.error = f"生存模式运行异常：{exc}"
            self.session = None

    def update(self, dt):
        super().update(dt)
        self.toast.update(dt)
        if self.session is not None and self._status() == "playing":
            try:
                self.session.update(dt)
            except Exception as exc:
                self.error = f"生存模式运行异常：{exc}"
                self.session = None

    def _font_cached(self, size, bold=False):
        key = (int(size), bool(bold))
        font = self._fonts.get(key)
        if font is None:
            font = _font(self.app, size, bold)
            self._fonts[key] = font
        return font

    def _draw_bg(self, surf):
        """草坪底图：LevelSession 只画格子，背景由本屏负责。"""
        if self._bg_surf is not None and self._bg_world == self.world_id:
            surf.blit(self._bg_surf, (0, 0))
            return
        bg = None
        try:
            img = self.app.assets.image(f"lawn/{self.world_id}.png")
            if img is not None and img.get_width() > 100:
                bg = pygame.transform.smoothscale(img, (WIN_W, WIN_H))
        except Exception:
            bg = None
        if bg is None:
            bg = pygame.Surface((WIN_W, WIN_H))
            ui.draw_gradient(bg, (0, 0, WIN_W, WIN_H), (98, 126, 78),
                             (46, 62, 40))
        self._bg_surf = bg
        self._bg_world = self.world_id
        surf.blit(bg, (0, 0))

    def draw(self, surf):
        if self.session is not None:
            self._draw_bg(surf)
            try:
                self.session.draw(surf)
            except Exception as exc:
                self.error = f"生存模式绘制失败：{exc}"
                self.session = None
        else:
            ui.draw_gradient(surf, (0, 0, WIN_W, WIN_H), (56, 66, 44),
                             (22, 26, 18))
            ui.text(surf, self._font_cached(24, True), self.error or "加载中…",
                    (WIN_W // 2, WIN_H // 2), (232, 224, 196), anchor="center")

        if self.session is not None:
            score = int(getattr(self.session, "score", 0) or 0)
            rnd = int(getattr(self.session, "round", 1) or 1)
            label = f"第 {rnd} 轮 · 分数 {score}"
            font = self._font_cached(17, True)
            chip = pygame.Rect(0, 0, font.size(label)[0] + 30, 34)
            chip.topright = (WIN_W - 20, 120)
            ui.draw_shadow(surf, chip, radius=10, alpha=80, offset=(0, 3))
            pygame.draw.rect(surf, (26, 30, 20), chip, border_radius=10)
            pygame.draw.rect(surf, (146, 124, 78), chip, 2, border_radius=10)
            ui.text(surf, font, label, chip.center, (248, 236, 200),
                    anchor="center")
        self.btn_back.draw(surf)

        if self._status() in ("won", "lost"):
            score = int(getattr(self.session, "score", 0) or 0)
            rnd = int(getattr(self.session, "round", 1) or 1)
            ui.draw_dim(surf, None, 150, (10, 12, 10))
            panel = pygame.Rect(340, 190, 600, 348)
            ui.draw_shadow(surf, panel, radius=18, alpha=120, offset=(0, 8))
            pygame.draw.rect(surf, (246, 238, 216), panel, border_radius=18)
            pygame.draw.rect(surf, ui.GOLD_DARK, panel, 3, border_radius=18)
            ui.text(surf, self._font_cached(38, True), "生存结束",
                    (panel.centerx, panel.y + 66), (150, 96, 56),
                    anchor="center")
            ui.text(surf, self._font_cached(22, True),
                    f"坚持到第 {rnd} 轮 · 得分 {score}",
                    (panel.centerx, panel.y + 128), (86, 72, 54),
                    anchor="center")
            best = 0
            try:
                best = int(self.app.save.best_survival.get(self.world_id, 0) or 0)
            except Exception:
                best = 0
            ui.text(surf, self._font_cached(16),
                    f"该世界最佳纪录：{max(best, score)}",
                    (panel.centerx, panel.y + 168), (122, 104, 78),
                    anchor="center")
            self.btn_result_back.draw(surf)
            self.btn_replay.draw(surf)
        self.toast.draw(surf)
        self.draw_fade(surf)


__all__ = ["SurvivalHubScreen", "SurvivalScreen"]
