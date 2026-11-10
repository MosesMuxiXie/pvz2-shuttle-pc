"""玩法中心：砸罐子 / 生存无尽 / 僵尸博士 / 商店 / 禅境花园 的入口。

菜单里点「更多玩法」进入本界面；每个入口通过 ``app.switch(name)`` 跳转。
目标界面尚未在 ``app.SCREEN_REGISTRY`` 注册时只提示，不崩溃。
"""
from __future__ import annotations

import math

import pygame

from .base import Screen
from . import widgets as ui

WIN_W, WIN_H = 1280, 720

CARD_W, CARD_H = 286, 172
GAP_X, GAP_Y = 20, 22
COLS = 4
GRID_X = (WIN_W - (COLS * CARD_W + (COLS - 1) * GAP_X)) // 2
GRID_Y = 168


def _font(app, size, bold=False):
    try:
        return app.font(size, bold)
    except Exception:
        try:
            return app.assets.font(size, bold)
        except Exception:
            return pygame.font.Font(None, int(size))


class ModeHubScreen(Screen):
    name = "modes"

    #: (目标界面, 标题, 副标题, 主色, 深色, 图标类型)
    MODES = [
        ("minigames", "砸罐子", "敲开罐子，用阳光种下植物，清光所有僵尸", 
         (172, 126, 74), (96, 66, 38), "vase"),
        ("survival", "生存无尽", "一波接一波，看你能在草坪上坚持多久",
         (86, 148, 112), (40, 84, 62), "endless"),
        ("bosses", "僵尸博士", "驾驶巨型机械的博士，需要整支植物军队",
         (158, 78, 66), (86, 38, 34), "boss"),
        ("shop", "商店", "用金币兑换植物养料、种子包与开场支援",
         (190, 148, 62), (110, 82, 30), "shop"),
        ("fusion", "植物融合", "两株植物合成一株更强的融合植物，解锁新图鉴",
         (126, 104, 176), (62, 50, 96), "fusion"),
        ("garden", "禅境花园", "种下植物，等待成长，收获金币",
         (104, 156, 92), (52, 96, 52), "garden"),
        ("menu", "返回主菜单", "回到冒险地图与图鉴",
         (98, 106, 120), (48, 54, 66), "back"),
    ]

    def __init__(self, app):
        super().__init__(app)
        self._fonts = {}
        self._bg = None
        self.toast = ui.Toast(app)
        self.cards = []
        self._layout()
        self.btn_back = ui.Button(
            app, (24, 22, 110, 46), "返回", on_click=self._back,
            style="cream", font_size=18)

    def _layout(self):
        self.cards = []
        total = len(self.MODES)
        for i, mode in enumerate(self.MODES):
            row, col = divmod(i, COLS)
            count = min(COLS, total - row * COLS)
            offset = (COLS - count) * (CARD_W + GAP_X) // 2
            rect = pygame.Rect(
                GRID_X + offset + col * (CARD_W + GAP_X),
                GRID_Y + row * (CARD_H + GAP_Y),
                CARD_W, CARD_H)
            self.cards.append((rect, mode))

    # ------------------------------------------------------------ 生命周期
    def enter(self):
        super().enter()
        try:
            self.app.audio.play_menu()
        except Exception:
            pass

    def exit(self):
        self._bg = None

    def _back(self):
        self._go("menu")

    def _go(self, target):
        try:
            self.app.switch(target)
        except KeyError:
            self.toast.show(f"「{target}」界面尚未接入，请联系开发组", 2.4)
        except Exception as exc:
            self.toast.show(f"无法打开界面：{exc}", 2.4)

    # ------------------------------------------------------------ 事件
    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._back()
            return
        if self.btn_back.handle(event):
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            for rect, mode in self.cards:
                if rect.collidepoint(event.pos):
                    self._go(mode[0])
                    return

    def update(self, dt):
        super().update(dt)
        self.toast.update(dt)
        self.btn_back.update(dt)

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
            img = ui.load_cover(self.app, "ui/bg_home.jpg", (WIN_W, WIN_H))
        except Exception:
            img = None
        if img is not None:
            surf.blit(img, (0, 0))
        else:
            ui.draw_gradient(surf, (0, 0, WIN_W, WIN_H),
                             (74, 84, 62), (24, 30, 24))
        ui.draw_dim(surf, None, 202, (12, 16, 14))
        return surf

    def draw(self, surf):
        if self._bg is None:
            self._bg = self._build_bg()
        surf.blit(self._bg, (0, 0))

        ui.draw_gradient(surf, (0, 0, WIN_W, 96), (74, 56, 38), (50, 38, 26))
        pygame.draw.line(surf, ui.GOLD, (0, 95), (WIN_W, 95), 2)
        pygame.draw.rect(surf, (30, 24, 18), (0, 0, WIN_W, 96), 2)
        ui.text(surf, self._font_cached(30, True), "更多玩法", (160, 22),
                ui.CREAM, shadow=(20, 14, 10))
        ui.text(surf, self._font_cached(15), "小游戏 · 生存 · Boss · 商店 · 花园 · 融合",
                (162, 62), (226, 210, 178))
        self.btn_back.draw(surf)
        self._draw_coins(surf, (WIN_W - 40, 48))

        for rect, mode in self.cards:
            self._draw_card(surf, rect, mode)

        ui.text(surf, self._font_cached(14),
                "点击卡片进入 · ESC 返回主菜单", (WIN_W // 2, WIN_H - 38),
                (198, 186, 162), anchor="center")
        self.toast.draw(surf)
        self.draw_fade(surf)

    def _draw_coins(self, surf, right_center):
        coins = int(getattr(self.app.save, "coins", 0) or 0)
        font = self._font_cached(20, True)
        label = font.render(f"{coins}", True, ui.CREAM)
        chip = pygame.Rect(0, 0, label.get_width() + 64, 42)
        chip.topright = right_center
        ui.draw_shadow(surf, chip, radius=12, alpha=70, offset=(0, 3))
        pygame.draw.rect(surf, (32, 26, 20), chip, border_radius=12)
        pygame.draw.rect(surf, ui.GOLD_DARK, chip, 2, border_radius=12)
        ui.draw_coin(surf, (chip.x + 24, chip.centery), r=12)
        ui.text(surf, font, str(coins), (chip.x + 44, chip.centery),
                ui.CREAM, anchor="midleft")

    def _draw_card(self, surf, rect, mode):
        target, title, sub, color, dark, icon = mode
        hover = rect.collidepoint(self.mouse)
        body = rect.move(0, -3) if hover else rect
        ui.draw_shadow(surf, body, radius=16, alpha=90,
                       offset=(0, 6 if hover else 4))
        ui.draw_gradient(surf, body, ui.mix(color, (255, 255, 255), 0.10),
                         dark, radius=16)
        border = ui.GOLD if hover else (ui.shade(color, 0.55))
        pygame.draw.rect(surf, border, body, 3, border_radius=16)
        # 顶部高光
        ui.alpha_rect(surf, pygame.Rect(body.x + 3, body.y + 3,
                                       body.w - 6, body.h // 2),
                      (255, 255, 255, 18), radius=14)

        icon_center = (body.x + 54, body.y + 58)
        pygame.draw.circle(surf, (20, 18, 14), icon_center, 38)
        pygame.draw.circle(surf, ui.mix(color, (255, 255, 255), 0.12),
                           icon_center, 35)
        pygame.draw.circle(surf, ui.shade(color, 0.5), icon_center, 35, 3)
        self._draw_icon(surf, icon, icon_center, 23)

        tx = body.x + 100
        ui.text(surf, self._font_cached(21, True),
                ui.fit_text(self._font_cached(21, True), title, body.w - 114),
                (tx, body.y + 28), ui.CREAM, shadow=(30, 20, 14))
        ui.draw_wrapped(surf, self._font_cached(12), sub,
                        pygame.Rect(body.x + 16, body.y + 88, body.w - 32, 46),
                        color=(238, 230, 208), line_height=17, max_lines=2)
        ui.draw_chip(surf, self.app, "进入" if target != "menu" else "回主菜单",
                     (body.right - 14, body.bottom - 14), size=12,
                     bg=(28, 24, 18), fg=ui.GOLD,
                     pad_x=11, pad_y=4, radius=8, anchor="bottomright",
                     border=(247, 201, 72, 120))

    # ------------------------------------------------------------ 图标
    def _draw_icon(self, surf, kind, center, r):
        cx, cy = center
        if kind == "vase":
            body = [(cx - r * 0.72, cy - r * 0.55), (cx + r * 0.72, cy - r * 0.55),
                    (cx + r * 0.5, cy + r * 0.72), (cx - r * 0.5, cy + r * 0.72)]
            pygame.draw.polygon(surf, (226, 202, 162), body)
            pygame.draw.polygon(surf, (150, 108, 66), body, 3)
            pygame.draw.rect(surf, (196, 152, 96),
                             (cx - r * 0.82, cy - r * 0.72, r * 1.64, r * 0.26),
                             border_radius=4)
            pygame.draw.line(surf, (120, 84, 48), (cx - 6, cy - 10),
                             (cx + 4, cy + 4), 3)
            pygame.draw.line(surf, (120, 84, 48), (cx + 4, cy + 4),
                             (cx - 3, cy + 16), 3)
            pygame.draw.circle(surf, (247, 201, 72), (cx, cy + 8), 5)
        elif kind == "endless":
            pygame.draw.circle(surf, (236, 244, 230), (cx - r * 0.42, cy),
                               int(r * 0.48), 5)
            pygame.draw.circle(surf, (236, 244, 230), (cx + r * 0.42, cy),
                               int(r * 0.48), 5)
            pygame.draw.line(surf, (236, 244, 230), (cx - 4, cy - r * 0.4),
                             (cx + 4, cy + r * 0.4), 4)
            pygame.draw.polygon(surf, (247, 201, 72), [
                (cx + r * 0.86, cy), (cx + r * 0.5, cy - 9),
                (cx + r * 0.5, cy + 9)])
        elif kind == "boss":
            pygame.draw.circle(surf, (238, 228, 208), (cx, cy - 4), r)
            pygame.draw.circle(surf, (60, 48, 38), (cx, cy - 4), r, 3)
            pygame.draw.circle(surf, (60, 48, 38), (cx - r * 0.38, cy - 8),
                               max(4, int(r * 0.2)))
            pygame.draw.circle(surf, (60, 48, 38), (cx + r * 0.38, cy - 8),
                               max(4, int(r * 0.2)))
            pygame.draw.polygon(surf, (60, 48, 38), [
                (cx, cy + 2), (cx - 6, cy + 10), (cx + 6, cy + 10)])
            for i in range(4):
                x = cx - r * 0.45 + i * r * 0.3
                pygame.draw.line(surf, (60, 48, 38), (x, cy + r * 0.55),
                                 (x, cy + r * 0.92), 4)
            pygame.draw.line(surf, (60, 48, 38), (cx - r * 0.45, cy + r * 0.62),
                             (cx + r * 0.45, cy + r * 0.62), 3)
        elif kind == "shop":
            bag = pygame.Rect(cx - r * 0.75, cy - r * 0.28, r * 1.5, r * 1.15)
            pygame.draw.rect(surf, (250, 236, 206), bag, border_radius=6)
            pygame.draw.rect(surf, (120, 82, 34), bag, 3, border_radius=6)
            pygame.draw.arc(surf, (120, 82, 34),
                            (cx - r * 0.45, cy - r * 0.82, r * 0.9, r * 0.9),
                            0.15, math.pi - 0.15, 4)
            ui.draw_coin(surf, (cx, cy + r * 0.28), r=int(r * 0.38))
        elif kind == "garden":
            pot = [(cx - r * 0.7, cy + r * 0.18), (cx + r * 0.7, cy + r * 0.18),
                   (cx + r * 0.5, cy + r * 0.9), (cx - r * 0.5, cy + r * 0.9)]
            pygame.draw.polygon(surf, (196, 116, 70), pot)
            pygame.draw.polygon(surf, (122, 70, 40), pot, 3)
            pygame.draw.line(surf, (86, 148, 66), (cx, cy + r * 0.2),
                             (cx, cy - r * 0.35), 4)
            for i in range(6):
                ang = i * math.tau / 6
                px = cx + math.cos(ang) * r * 0.34
                py = cy - r * 0.32 + math.sin(ang) * r * 0.34
                pygame.draw.circle(surf, (250, 208, 96), (int(px), int(py)), 8)
            pygame.draw.circle(surf, (150, 96, 44), (cx, cy - r * 0.32), 7)
        elif kind == "fusion":
            # 两株植物融合为一：两个交叠的光球 + 加号
            left = (int(cx - r * 0.34), int(cy + r * 0.16))
            right = (int(cx + r * 0.34), int(cy + r * 0.16))
            pygame.draw.circle(surf, (156, 206, 140), left, int(r * 0.52))
            pygame.draw.circle(surf, (238, 202, 108), right, int(r * 0.52))
            pygame.draw.circle(surf, (120, 170, 110), left, int(r * 0.52), 2)
            pygame.draw.circle(surf, (190, 148, 62), right, int(r * 0.52), 2)
            pygame.draw.circle(surf, (186, 160, 224), (cx, cy - r * 0.34),
                               int(r * 0.30))
            pygame.draw.circle(surf, (110, 88, 150), (cx, cy - r * 0.34),
                               int(r * 0.30), 2)
            pygame.draw.line(surf, (250, 244, 226), (cx - 7, cy - r * 0.34),
                             (cx + 7, cy - r * 0.34), 3)
            pygame.draw.line(surf, (250, 244, 226), (cx, cy - r * 0.34 - 7),
                             (cx, cy - r * 0.34 + 7), 3)
            for ang, rad in ((-0.9, 0.78), (-0.2, 0.9), (2.5, 0.8)):
                px = cx + math.cos(ang) * r * rad
                py = cy - r * 0.1 + math.sin(ang) * r * rad * 0.6
                pygame.draw.circle(surf, (250, 240, 180), (int(px), int(py)), 3)
        else:  # back
            pygame.draw.polygon(surf, (238, 232, 216), [
                (cx - r * 0.55, cy), (cx + r * 0.15, cy - r * 0.62),
                (cx + r * 0.15, cy - r * 0.2), (cx + r * 0.8, cy - r * 0.2),
                (cx + r * 0.8, cy + r * 0.2), (cx + r * 0.15, cy + r * 0.2),
                (cx + r * 0.15, cy + r * 0.62)])
            pygame.draw.polygon(surf, (60, 64, 72), [
                (cx - r * 0.55, cy), (cx + r * 0.15, cy - r * 0.62),
                (cx + r * 0.15, cy - r * 0.2), (cx + r * 0.8, cy - r * 0.2),
                (cx + r * 0.8, cy + r * 0.2), (cx + r * 0.15, cy + r * 0.2),
                (cx + r * 0.15, cy + r * 0.62)], 2)


__all__ = ["ModeHubScreen"]
