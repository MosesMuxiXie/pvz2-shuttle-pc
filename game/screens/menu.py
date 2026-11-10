"""主菜单：SHUTTLE 主视觉 + 冒险模式 / 图鉴 / 设置 / 退出。"""
from __future__ import annotations

import math
import random

import pygame

from ..config import VERSION
from .base import Screen
from . import widgets as ui

_HGRAD_CACHE: dict = {}


def _hgrad(surf, rect, left_color, right_color):
    """横向渐变（RGBA）。"""
    rect = pygame.Rect(rect)
    key = (rect.w, rect.h, tuple(left_color), tuple(right_color))
    layer = _HGRAD_CACHE.get(key)
    if layer is None:
        layer = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        for x in range(rect.w):
            t = x / max(1, rect.w - 1)
            pygame.draw.line(layer, ui.mix(left_color, right_color, t),
                             (x, 0), (x, rect.h))
        if len(_HGRAD_CACHE) > 40:
            _HGRAD_CACHE.clear()
        _HGRAD_CACHE[key] = layer
    surf.blit(layer, rect.topleft)


def _logo(app, text, size, fill, outline, outline_w=4, shadow=True):
    """预渲染描边标题字，返回 Surface。"""
    font = app.font(size, True)
    tw, th = font.size(text)
    pad = outline_w + 8
    w, h = tw + pad * 2, th + pad * 2
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    fill_img = font.render(text, True, fill)
    outline_img = font.render(text, True, outline)
    shadow_img = font.render(text, True, (26, 20, 12))
    if shadow:
        shadow_img.set_alpha(150)
        for oy in (5, 7):
            surf.blit(shadow_img, (pad, pad + oy))
    for dx in range(-outline_w, outline_w + 1):
        for dy in range(-outline_w, outline_w + 1):
            if dx * dx + dy * dy > (outline_w + 1) ** 2:
                continue
            surf.blit(outline_img, (pad + dx, pad + dy))
    surf.blit(fill_img, (pad, pad))
    return surf


def _glass(surf, rect, fill=(18, 20, 16, 168), border=(247, 201, 72, 90), radius=14):
    rect = pygame.Rect(rect)
    layer = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(layer, fill, layer.get_rect(), border_radius=radius)
    pygame.draw.rect(layer, border, layer.get_rect(), 1, border_radius=radius)
    surf.blit(layer, rect.topleft)


class MenuScreen(Screen):
    name = "menu"

    def __init__(self, app):
        super().__init__(app)
        self.W, self.H = app.screen.get_size()
        self.bg = None
        self.logo_shuttle = None
        self.logo_pvz = None
        self.particles = []
        self._fonts = {}
        # 左侧压暗层：平台状遮到 720px，再平滑淡出，盖住背景里的SHUTTLE标志
        self._scrim = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        for x in range(self.W):
            if x < 720:
                alpha = 200
            elif x < 1120:
                alpha = int(200 * (1120 - x) / 400)
            else:
                alpha = 0
            if alpha:
                pygame.draw.line(self._scrim, (5, 8, 7, alpha),
                                 (x, 0), (x, self.H))

        self.btn_adventure = ui.Button(
            app, (168, 300, 340, 68), "冒险模式", on_click=self._adventure,
            style="green", font_size=27)
        self.btn_almanac = ui.Button(
            app, (168, 382, 340, 56), "植物与僵尸图鉴", on_click=self._almanac,
            style="primary", font_size=21)
        self.btn_modes = ui.Button(
            app, (168, 446, 340, 56), "特殊模式", on_click=self._modes,
            style="gold", font_size=21)
        self.btn_settings = ui.Button(
            app, (168, 510, 340, 52), "设置", on_click=self._settings,
            style="primary", font_size=20)
        self.btn_quit = ui.Button(
            app, (168, 568, 340, 48), "退出游戏", on_click=self._quit,
            style="ghost", font_size=18)
        self.buttons = [self.btn_adventure, self.btn_almanac, self.btn_modes,
                        self.btn_settings, self.btn_quit]

    # ------------------------------------------------------------------
    def enter(self):
        super().enter()
        try:
            self.app.audio.play_menu()
        except Exception:
            pass
        cover = ui.load_cover(self.app, "ui/launcher.png", (self.W, self.H))
        # 轻微虚化关键艺术，弱化背景自带的 SHUTTLE 标志，避免与前景标题抢视线
        try:
            small = pygame.transform.smoothscale(cover, (56, 32))
            self.bg = pygame.transform.smoothscale(small, (self.W, self.H))
        except Exception:
            self.bg = cover
        self.logo_pvz = _logo(self.app, "PvZ 2", 40, (250, 238, 206),
                              (64, 40, 22), outline_w=3)
        self.logo_shuttle = _logo(self.app, "SHUTTLE", 96, (247, 201, 72),
                                  (74, 42, 20), outline_w=5)
        rnd = random.Random(20261001)
        self.particles = []
        for _ in range(26):
            self.particles.append({
                "x": rnd.uniform(0, self.W),
                "y": rnd.uniform(0, self.H),
                "r": rnd.uniform(1.2, 3.4),
                "speed": rnd.uniform(8, 26),
                "drift": rnd.uniform(-6, 6),
                "phase": rnd.uniform(0, math.tau),
                "alpha": rnd.randint(40, 130),
            })

    def exit(self):
        pass

    def _font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = self.app.font(size, bold)
        return self._fonts[key]

    # ------------------------------------------------------------------
    def _adventure(self):
        self.app.switch("worldmap")

    def _almanac(self):
        self.app.switch("almanac")

    def _modes(self):
        self.app.switch("modes")

    def _settings(self):
        self.app.switch("settings")

    def _quit(self):
        self.app.quit()

    # ------------------------------------------------------------------
    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self._adventure()
                return
            if event.key == pygame.K_ESCAPE:
                self._quit()
                return
        for b in self.buttons:
            if b.handle(event):
                return

    def update(self, dt):
        super().update(dt)
        t = pygame.time.get_ticks() / 1000.0
        for p in self.particles:
            p["y"] -= p["speed"] * dt
            p["x"] += math.sin(t * 0.6 + p["phase"]) * p["drift"] * dt
            if p["y"] < -8:
                p["y"] = self.H + 8
            if p["x"] < -8:
                p["x"] = self.W + 8
            elif p["x"] > self.W + 8:
                p["x"] = -8

    # ------------------------------------------------------------------
    def draw(self, surf):
        self._draw_background(surf)
        self._draw_particles(surf)
        self._draw_title(surf)
        for b in self.buttons:
            b.draw(surf)
        self._draw_info(surf)
        self.draw_fade(surf)

    def _draw_background(self, surf):
        if self.bg is not None:
            surf.blit(self.bg, (0, 0))
        else:
            ui.draw_gradient(surf, surf.get_rect(), (38, 54, 44), (14, 20, 16))
        ui.draw_dim(surf, alpha=66, color=(6, 8, 8))
        # 左侧压暗，压住背景里的 SHUTTLE 标志，避免和前景标题重叠
        surf.blit(self._scrim, (0, 0))
        ui.draw_gradient(surf, (0, self.H - 210, self.W, 210),
                         (6, 8, 6, 0), (6, 8, 6, 185))
        # 左下角暖色灯光
        glow = pygame.Surface((520, 420), pygame.SRCALPHA)
        for i in range(10):
            a = int(16 - i * 1.4)
            pygame.draw.circle(glow, (247, 201, 72, max(0, a)),
                               (170, 330), 210 - i * 18)
        surf.blit(glow, (0, 0))

    def _draw_particles(self, surf):
        t = pygame.time.get_ticks() / 1000.0
        for p in self.particles:
            a = int(p["alpha"] * (0.65 + 0.35 * math.sin(t * 1.4 + p["phase"])))
            r = max(1, int(p["r"]))
            dot = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(dot, (255, 232, 150, max(0, a)),
                               (r + 1, r + 1), r)
            surf.blit(dot, (int(p["x"]), int(p["y"])))

    def _draw_title(self, surf):
        surf.blit(self.logo_pvz, (162, 74))
        surf.blit(self.logo_shuttle, (154, 112))
        ui.text(surf, self._font(19, True), "植物大战僵尸 2 · 粉丝复刻版",
                (172, 250), (244, 234, 210), shadow=(20, 14, 8))
        pygame.draw.line(surf, (247, 201, 72), (172, 284), (500, 284), 2)
        pygame.draw.circle(surf, (247, 201, 72), (508, 284), 3)
        ui.text(surf, self._font(12, False), "ADVENTURE AWAITS · 时空穿梭",
                (172, 294), (210, 200, 176))

    def _draw_info(self, surf):
        panel = pygame.Rect(self.W - 408, self.H - 218, 288, 150)
        _glass(surf, panel)
        ui.text(surf, self._font(15, True), "园丁档案",
                (panel.x + 18, panel.y + 16), ui.GOLD, anchor="topleft")
        pygame.draw.line(surf, (247, 201, 72, 90),
                         (panel.x + 18, panel.y + 42), (panel.right - 18, panel.y + 42), 1)

        coins = int(getattr(self.app.save, "coins", 0))
        ui.draw_coin(surf, (panel.x + 26, panel.y + 62), 9)
        ui.text(surf, self._font(14, False), f"金币  {coins}",
                (panel.x + 42, panel.y + 62), (240, 232, 214), anchor="midleft")

        done, total = self._completion()
        pct = 0 if total <= 0 else int(round(done * 100.0 / total))
        ui.text(surf, self._font(13, False), f"通关进度  {done} / {total}",
                (panel.right - 18, panel.y + 62), (220, 212, 194), anchor="midright")

        bar = pygame.Rect(panel.x + 18, panel.y + 86, panel.w - 36, 9)
        pygame.draw.rect(surf, (52, 48, 40), bar, border_radius=5)
        if pct > 0:
            fill = bar.copy()
            fill.w = max(6, int(bar.w * pct / 100.0))
            ui.draw_gradient(surf, fill, (247, 214, 110), (218, 162, 52), radius=5)
        ui.text(surf, self._font(11, False), f"{pct}%",
                (bar.right, bar.y - 4), (240, 222, 170), anchor="bottomright")

        ui.text(surf, self._font(11, False), f"版本 {VERSION}  ·  已解锁世界",
                (panel.x + 18, panel.bottom - 16), (172, 166, 150), anchor="midleft")
        unlocked = len(getattr(self.app.save, "unlocked_worlds", []) or [])
        ui.text(surf, self._font(11, True), str(unlocked),
                (panel.right - 18, panel.bottom - 16), (240, 222, 170),
                anchor="midright")

        ui.text(surf, self._font(11, False), "Enter 开始冒险", (168, 612),
                (212, 202, 180))

    def _completion(self):
        try:
            worlds = list(self.app.data.worlds)
        except Exception:
            worlds = []
        total = 0
        for w in worlds:
            try:
                n = len(self.app.data.levels(w.id))
            except Exception:
                n = 0
            total += n if n > 0 else int(getattr(w, "levels", 10) or 10)
        if total <= 0:
            total = 80
        done = len(getattr(self.app.save, "completed", []) or [])
        return done, total
