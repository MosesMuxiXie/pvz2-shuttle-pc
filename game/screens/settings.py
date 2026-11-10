"""设置界面：显示、游戏速度、音乐与音效，修改后立即保存。"""
from __future__ import annotations

import pygame

from ..config import VERSION
from .base import Screen
from . import widgets as ui

DEFAULT_SETTINGS = {
    "high_view": False,
    "high_quality": True,
    "speed": 1.0,
    "music": True,
    "sfx": True,
}


class Switch:
    """圆角开关。"""

    def __init__(self, app, pos, value=True, on_change=None, width=54, height=28):
        self.app = app
        self.rect = pygame.Rect(int(pos[0]), int(pos[1]), width, height)
        self.value = bool(value)
        self.on_change = on_change
        self.hover = False
        self.pressed = False
        self._pos = 1.0 if self.value else 0.0

    def handle(self, event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
                return True
            return False
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was = self.pressed
            self.pressed = False
            if was and self.rect.collidepoint(event.pos):
                self.toggle()
                return True
            return was
        return False

    def toggle(self):
        self.value = not self.value
        if self.on_change:
            self.on_change(self.value)

    def update(self, dt):
        target = 1.0 if self.value else 0.0
        self._pos += (target - self._pos) * min(1.0, 14.0 * dt)

    def draw(self, surf):
        track = self.rect
        if self.value:
            fill = (106, 168, 79) if not self.hover else (120, 182, 90)
        else:
            fill = (168, 160, 146) if not self.hover else (184, 176, 162)
        pygame.draw.rect(surf, fill, track, border_radius=track.h // 2)
        pygame.draw.rect(surf, ui.shade(fill, 0.82), track, 1, border_radius=track.h // 2)
        knob_r = track.h // 2 - 4
        x = track.x + knob_r + 4 + int((track.w - 2 * knob_r - 8) * self._pos)
        pygame.draw.circle(surf, (248, 244, 232), (x, track.centery), knob_r)
        pygame.draw.circle(surf, (198, 188, 170), (x, track.centery), knob_r, 1)


class SettingsScreen(Screen):
    name = "settings"

    def __init__(self, app):
        super().__init__(app)
        self.W, self.H = app.screen.get_size()
        self.panel = pygame.Rect(0, 0, 740, 528)
        self.panel.center = (self.W // 2, self.H // 2 + 6)
        self._fonts = {}
        self.bg = None
        self.toast = ui.Toast(app)
        self.settings = dict(DEFAULT_SETTINGS)
        self._build_widgets()

    def _build_widgets(self):
        app = self.app
        px, py = self.panel.x, self.panel.y
        self.btn_back = ui.Button(
            app, (self.panel.right - 154, self.panel.bottom - 70, 128, 46),
            "返回", on_click=lambda: app.switch("menu"), style="primary",
            font_size=19)
        self.btn_reset = ui.Button(
            app, (px + 34, self.panel.bottom - 66, 142, 40),
            "恢复默认", on_click=self._reset, style="ghost", font_size=16)
        self.cb_view = ui.Checkbox(
            app, (px + 52, py + 134), "高视角", False,
            on_change=lambda v: self._set("high_view", v), box=22, font_size=17)
        self.cb_quality = ui.Checkbox(
            app, (px + 394, py + 134), "高画质", True,
            on_change=lambda v: self._set("high_quality", v), box=22, font_size=17)
        self.speed_group = ui.ToggleGroup(
            app, (px + 210, py + 252, 292, 40), ("1.0x", "1.5x", "2.0x"), 0,
            on_change=self._on_speed, font_size=16, style="segmented")
        self.sw_music = Switch(
            app, (px + 290, py + 327), True,
            on_change=lambda v: self._set("music", v))
        self.sw_sfx = Switch(
            app, (px + 632, py + 327), True,
            on_change=lambda v: self._set("sfx", v))
        self.widgets = [self.btn_back, self.btn_reset, self.cb_view,
                        self.cb_quality, self.speed_group, self.sw_music, self.sw_sfx]

    # ------------------------------------------------------------------
    def enter(self):
        super().enter()
        settings = dict(DEFAULT_SETTINGS)
        try:
            settings.update(dict(getattr(self.app.save, "settings", {}) or {}))
        except Exception:
            pass
        self.settings = settings
        self.cb_view.checked = bool(settings.get("high_view", False))
        self.cb_quality.checked = bool(settings.get("high_quality", True))
        try:
            speed = float(settings.get("speed", 1.0))
        except (TypeError, ValueError):
            speed = 1.0
        speed = speed if speed in (1.0, 1.5, 2.0) else 1.0
        self.speed_group.set_selected((1.0, 1.5, 2.0).index(speed))
        self.sw_music.value = bool(settings.get("music", True))
        self.sw_music._pos = 1.0 if self.sw_music.value else 0.0
        self.sw_sfx.value = bool(settings.get("sfx", True))
        self.sw_sfx._pos = 1.0 if self.sw_sfx.value else 0.0

        bg = ui.load_cover(self.app, "ui/bg_home.jpg", (self.W, self.H))
        if bg is not None:
            try:
                small = pygame.transform.smoothscale(bg, (320, 180))
                bg = pygame.transform.smoothscale(small, (self.W, self.H))
            except Exception:
                pass
        self.bg = bg

    def exit(self):
        pass

    def _font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = self.app.font(size, bold)
        return self._fonts[key]

    # ------------------------------------------------------------------
    def _set(self, key, value):
        self.settings[key] = value
        try:
            self.app.save.settings[key] = value
            self.app.save.save()
        except Exception:
            pass
        if key in ("music", "sfx"):
            try:
                self.app.audio.set_flags(
                    bool(self.settings.get("music", True)),
                    bool(self.settings.get("sfx", True)))
            except Exception:
                pass

    def _on_speed(self, index):
        self._set("speed", (1.0, 1.5, 2.0)[index])

    def _reset(self):
        self.settings = dict(DEFAULT_SETTINGS)
        self.cb_view.checked = DEFAULT_SETTINGS["high_view"]
        self.cb_quality.checked = DEFAULT_SETTINGS["high_quality"]
        self.speed_group.set_selected(0)
        self.sw_music.value = DEFAULT_SETTINGS["music"]
        self.sw_sfx.value = DEFAULT_SETTINGS["sfx"]
        try:
            self.app.save.settings.update(DEFAULT_SETTINGS)
            self.app.save.save()
        except Exception:
            pass
        self.toast.show("已恢复默认设置")

    # ------------------------------------------------------------------
    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.switch("menu")
            return
        for w in self.widgets:
            if w.handle(event):
                return

    def update(self, dt):
        super().update(dt)
        self.toast.update(dt)
        self.sw_music.update(dt)
        self.sw_sfx.update(dt)

    # ------------------------------------------------------------------
    def draw(self, surf):
        self._draw_background(surf)
        self._draw_header(surf)
        self._draw_display_section(surf)
        self._draw_game_section(surf)
        self._draw_footer(surf)
        self.toast.draw(surf, (self.W // 2, self.panel.bottom + 46))
        self.draw_fade(surf)

    def _draw_background(self, surf):
        if self.bg is not None:
            surf.blit(self.bg, (0, 0))
        else:
            ui.draw_gradient(surf, surf.get_rect(), (70, 92, 66), (32, 44, 32))
        ui.draw_dim(surf, alpha=126, color=(10, 12, 10))

    def _draw_header(self, surf):
        panel = self.panel
        ui.draw_shadow(surf, panel, radius=16, alpha=120, offset=(0, 10), spread=12)
        pygame.draw.rect(surf, ui.PAPER, panel, border_radius=16)
        header = pygame.Rect(panel.x, panel.y, panel.w, 66)
        pygame.draw.rect(surf, ui.BROWN, header,
                         border_top_left_radius=16, border_top_right_radius=16)
        ui.draw_gradient(surf, header, (132, 92, 58), (104, 68, 42),
                         radius=16)
        mask = pygame.Surface((header.w, header.h), pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(),
                         border_top_left_radius=16, border_top_right_radius=16)
        header_layer = pygame.Surface((header.w, header.h), pygame.SRCALPHA)
        header_layer.blit(surf, (0, 0), (header.x, header.y, header.w, header.h))
        # 简单的标题栏高光
        ui.alpha_rect(surf, (header.x + 16, header.y + 1, header.w - 32, 2),
                      (255, 255, 255, 70), radius=1)
        gear = ui.get_image(self.app, "ui/ic_settings.png")
        if gear is not None:
            gear = ui.scale_image(gear, (26, 26))
            surf.blit(gear, (header.x + 28, header.centery - 13))
        ui.text(surf, self._font(24, True), "设置",
                (header.x + 66, header.centery), (255, 248, 226), anchor="midleft",
                shadow=(30, 20, 12))
        ui.text(surf, self._font(11, False), "SETTINGS",
                (header.x + 66 + self._font(24, True).size("设置")[0] + 14,
                 header.centery + 1), (226, 206, 174), anchor="midleft")
        ui.text(surf, self._font(12, False), "修改后自动保存",
                (header.right - 28, header.centery), (238, 218, 182),
                anchor="midright")
        pygame.draw.rect(surf, ui.BORDER, panel, 2, border_radius=16)

    def _section(self, surf, title, sub, y):
        ui.text(surf, self._font(14, True), title,
                (self.panel.x + 34, y), ui.BROWN, anchor="topleft")
        ui.text(surf, self._font(11, False), sub,
                (self.panel.x + 34 + self._font(14, True).size(title)[0] + 12, y + 2),
                ui.INK_FAINT, anchor="topleft")
        pygame.draw.line(surf, (226, 216, 198),
                         (self.panel.x + 34, y + 24),
                         (self.panel.right - 34, y + 24), 1)

    def _draw_display_section(self, surf):
        px, py = self.panel.x, self.panel.y
        self._section(surf, "显示", "DISPLAY", py + 88)
        # 两个选项卡片
        cards = [
            (pygame.Rect(px + 34, py + 122, 326, 82), self.cb_view,
             "扩大战场视野，显示更多行。"),
            (pygame.Rect(px + 376, py + 122, 326, 82), self.cb_quality,
             "启用更精细的粒子与阴影特效。"),
        ]
        for rect, cb, desc in cards:
            pygame.draw.rect(surf, (250, 246, 237), rect, border_radius=10)
            pygame.draw.rect(surf, (214, 202, 182), rect, 1, border_radius=10)
            ui.text(surf, self._font(11, False), desc,
                    (rect.x + 52, rect.y + 50), ui.INK_FAINT, anchor="topleft")
        self.cb_view.pos = (px + 52, py + 134)
        self.cb_quality.pos = (px + 394, py + 134)
        self.cb_view.draw(surf)
        self.cb_quality.draw(surf)

    def _draw_game_section(self, surf):
        px, py = self.panel.x, self.panel.y
        self._section(surf, "游戏", "GAMEPLAY", py + 216)
        ui.text(surf, self._font(14, False), "游戏速度",
                (px + 34, py + 258), ui.INK, anchor="midleft")
        self.speed_group.draw(surf)
        ui.text(surf, self._font(11, False), "影响战斗内的时间流速。",
                (px + 210, py + 300), ui.INK_FAINT, anchor="topleft")

        # 音乐 / 音效行
        rows = [
            (pygame.Rect(px + 34, py + 314, 326, 54), "背景音乐", "启动器与战斗音乐",
             self.sw_music),
            (pygame.Rect(px + 376, py + 314, 326, 54), "音效", "按钮、种植与战斗音效",
             self.sw_sfx),
        ]
        for rect, label, sub, switch in rows:
            pygame.draw.rect(surf, (250, 246, 237), rect, border_radius=10)
            pygame.draw.rect(surf, (214, 202, 182), rect, 1, border_radius=10)
            ui.text(surf, self._font(14, True), label,
                    (rect.x + 16, rect.y + 18), ui.BROWN, anchor="midleft")
            ui.text(surf, self._font(10, False), sub,
                    (rect.x + 16, rect.y + 37), ui.INK_FAINT, anchor="midleft")
        # 音效行在第二排
        self.sw_music.draw(surf)
        self.sw_sfx.draw(surf)

    def _draw_footer(self, surf):
        panel = self.panel
        pygame.draw.line(surf, (226, 216, 198), (panel.x + 34, panel.bottom - 88),
                         (panel.right - 34, panel.bottom - 88), 1)
        ui.text(surf, self._font(10, False),
                "所有修改会立即生效，并自动写入本地存档。",
                (panel.centerx, panel.bottom - 108), ui.INK_FAINT,
                anchor="center")
        self.btn_reset.draw(surf)
        self.btn_back.draw(surf)
        # 版本号居中放在两枚按钮之间，避免被“恢复默认”按钮压住
        ui.text(surf, self._font(9, False), f"设置 · 当前版本 {VERSION}",
                (panel.centerx, panel.bottom - 17), ui.INK_FAINT,
                anchor="center")
        ui.text(surf, self._font(10, False), "PvZ 2 SHUTTLE",
                (self.W - 24, self.H - 18), (234, 226, 208), anchor="bottomright")
