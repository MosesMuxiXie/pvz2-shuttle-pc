"""Screen 基类：统一生命周期、鼠标跟踪与淡入淡出转场。"""
from __future__ import annotations

import pygame

_FADE_SURF = None


def _fade_surface(size):
    global _FADE_SURF
    if _FADE_SURF is None or _FADE_SURF.get_size() != size:
        _FADE_SURF = pygame.Surface(size)
        _FADE_SURF.fill((0, 0, 0))
    return _FADE_SURF


class Screen:
    """所有界面的基类。

    生命周期：``__init__`` → :meth:`enter` → ``handle/update/draw`` → :meth:`exit`。
    默认提供黑场淡入（进入新界面）与淡出后转场（:meth:`transition_to`）。
    """

    name = "screen"
    fade_in_time = 0.24
    fade_out_time = 0.18

    def __init__(self, app):
        self.app = app
        self.mouse = (0, 0)
        self._fade = 1.0
        self._fading_out = False
        self._fade_target = None

    # ---------------- 生命周期 ----------------
    def enter(self):
        self._fade = 1.0
        self._fading_out = False
        self._fade_target = None

    def exit(self):
        pass

    def handle(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.mouse = event.pos
        elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self.mouse = getattr(event, "pos", self.mouse)

    def update(self, dt):
        if self._fading_out:
            self._fade = min(1.0, self._fade + dt / max(0.01, self.fade_out_time))
            if self._fade >= 1.0:
                target = self._fade_target
                self._fade_target = None
                self._fading_out = False
                if target is not None:
                    self.app.switch(target)
        elif self._fade > 0.0:
            self._fade = max(0.0, self._fade - dt / max(0.01, self.fade_in_time))

    def draw(self, surf):
        """子类实现。"""

    # ---------------- 转场 ----------------
    def world_bg(self, surf, world_id: str) -> bool:
        """给自定义战斗屏（生存/砸罐子/Boss）铺一张世界草坪背景。"""
        cache = getattr(self, "_world_bg_cache", None)
        if cache is None:
            cache = {}
            self._world_bg_cache = cache
        img = cache.get(world_id)
        if img is None:
            img = False
            try:
                raw = self.app.assets.image(f"lawn/{world_id}.png")
                if raw is not None and raw.get_width() > 200:
                    img = pygame.transform.smoothscale(
                        raw, self.app.screen.get_size())
            except Exception:
                img = False
            cache[world_id] = img
        if img:
            surf.blit(img, (0, 0))
            return True
        return False

    def transition_to(self, target):
        """淡出到目标界面（target 为界面名或 Screen 实例）。"""
        if self._fading_out or target is None:
            return
        self._fade_target = target
        self._fading_out = True

    def draw_fade(self, surf):
        if self._fade <= 0.004:
            return
        overlay = _fade_surface(surf.get_size())
        overlay.set_alpha(int(255 * min(1.0, self._fade)))
        surf.blit(overlay, (0, 0))

    # ---------------- 小工具 ----------------
    @staticmethod
    def is_key(event, key) -> bool:
        return event.type == pygame.KEYDOWN and event.key == key

    @staticmethod
    def is_click(event) -> bool:
        return event.type == pygame.MOUSEBUTTONUP and event.button == 1

    @staticmethod
    def is_press(event) -> bool:
        return event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
