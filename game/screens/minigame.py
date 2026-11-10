"""砸罐子（Vasebreaker）：选关列表与战斗界面。"""
from __future__ import annotations

import random

import pygame

from .base import Screen
from . import widgets as ui

WIN_W, WIN_H = 1280, 720
CARD_W, CARD_H = 360, 150
GAP_X, GAP_Y = 26, 14
GRID_X = (WIN_W - (3 * CARD_W + 2 * GAP_X)) // 2
GRID_Y = 168
COLS, ROWS = 3, 3
PER_PAGE = COLS * ROWS


def _font(app, size, bold=False):
    try:
        return app.font(size, bold)
    except Exception:
        try:
            return app.assets.font(size, bold)
        except Exception:
            return pygame.font.Font(None, int(size))


def load_minigames(app):
    raw = app.content_json("minigames", {"minigames": []}) or {}
    entries = list(raw.get("minigames") or [])
    games = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("type") or "vasebreaker")
        if kind != "vasebreaker":
            continue
        games.append({
            "id": str(entry.get("id") or f"vase_{i}"),
            "type": "vasebreaker",
            "world": str(entry.get("world") or "frontyard"),
            "title_zh": str(entry.get("title_zh") or "砸罐子"),
            "desc_zh": str(entry.get("desc_zh") or "敲碎罐子，清光所有僵尸。"),
            "sun": int(entry.get("sun", 150) or 150),
            "deck": list(entry.get("deck") or []),
            "vases": list(entry.get("vases") or []),
        })
    if not games:
        games = _fallback_games(app)
    return games


def _fallback_games(app):
    worlds = [w for w in app.data.worlds
              if w.id in ("frontyard", "egypt", "pirate", "cowboy",
                          "future", "dark", "beach", "lostcity",
                          "chinesegarden", "losantosvice", "lunarrainbowmarket")]
    games = []
    for i, world in enumerate(worlds):
        rng = random.Random(1000 + i)
        vases = []
        for row in range(5):
            for col in range(2, 8):
                if len(vases) >= 14:
                    break
                roll = rng.random()
                if roll < 0.55:
                    vases.append([row, col, "zombie", _world_zombie(app, world.id)])
                elif roll < 0.8:
                    vases.append([row, col, "sun"])
                elif roll < 0.9:
                    vases.append([row, col, "plantfood"])
        try:
            deck = list(app.data.levels(world.id)[0].deck)
        except Exception:
            deck = []
        games.append({
            "id": f"vase_{world.id}",
            "type": "vasebreaker",
            "world": world.id,
            "title_zh": f"{world.name_zh} · 砸罐子",
            "desc_zh": "敲碎罐子，用里面的阳光种植物，清光所有僵尸。",
            "sun": 150 + i * 50,
            "deck": deck,
            "vases": vases,
        })
    return games


def _world_zombie(app, world_id):
    keys = [z for z in (app.data.zombies or {})]
    for prefix in ("basic", f"{world_id}_", "garden_zombie", "gang_zombie",
                   "market_clockwork"):
        for key in keys:
            if key == prefix or key.startswith(prefix):
                return key
    return keys[0] if keys else "basic"


class VasebreakerHubScreen(Screen):
    name = "minigames"

    def __init__(self, app):
        super().__init__(app)
        self._fonts = {}
        self._bg = None
        self.toast = ui.Toast(app)
        self.games = []
        self.cards = []
        self.page = 0
        self.page_count = 1
        self.btn_back = ui.Button(app, (24, 22, 110, 46), "返回",
                                  on_click=self._back, style="cream",
                                  font_size=18)
        self.btn_prev = ui.Button(app, (WIN_W - 358, WIN_H - 62, 150, 42),
                                  "上一页", on_click=lambda: self._turn(-1),
                                  style="cream", font_size=17)
        self.btn_next = ui.Button(app, (WIN_W - 188, WIN_H - 62, 150, 42),
                                  "下一页", on_click=lambda: self._turn(1),
                                  style="cream", font_size=17)
        self._layout()

    def _layout(self):
        self.page_count = max(1, (len(self.games) + PER_PAGE - 1) // PER_PAGE)
        self.page = max(0, min(self.page, self.page_count - 1))
        self.cards = []
        start = self.page * PER_PAGE
        for i, game in enumerate(self.games[start:start + PER_PAGE]):
            row, col = divmod(i, COLS)
            rect = pygame.Rect(GRID_X + col * (CARD_W + GAP_X),
                               GRID_Y + row * (CARD_H + GAP_Y),
                               CARD_W, CARD_H)
            self.cards.append((rect, game))
        try:
            self.btn_prev.set_enabled(self.page > 0)
            self.btn_next.set_enabled(self.page < self.page_count - 1)
        except Exception:
            pass

    def _turn(self, delta):
        page = max(0, min(self.page + delta, self.page_count - 1))
        if page != self.page:
            self.page = page
            self._layout()

    def enter(self):
        super().enter()
        self.games = load_minigames(self.app)
        self.page = 0
        self._layout()
        try:
            self.app.audio.play_menu()
        except Exception:
            pass

    def exit(self):
        self._bg = None

    def _back(self):
        self.app.switch("modes")

    def _open(self, game):
        self.app.ui_payload = game
        try:
            self.app.switch("minigame_level")
        except KeyError:
            self.toast.show("砸罐子界面尚未接入", 2.2)
        except Exception as exc:
            self.toast.show(f"无法进入砸罐子：{exc}", 2.4)

    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._back()
            return
        if self.btn_back.handle(event):
            return
        if self.btn_prev.handle(event) or self.btn_next.handle(event):
            return
        if event.type == pygame.MOUSEWHEEL:
            self._turn(-1 if event.y > 0 else 1)
            return
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_LEFT, pygame.K_PAGEUP):
                self._turn(-1)
                return
            if event.key in (pygame.K_RIGHT, pygame.K_PAGEDOWN):
                self._turn(1)
                return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            for rect, game in self.cards:
                if rect.collidepoint(event.pos):
                    self._open(game)
                    return

    def update(self, dt):
        super().update(dt)
        self.toast.update(dt)
        self.btn_back.update(dt)
        self.btn_prev.update(dt)
        self.btn_next.update(dt)

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
            img = ui.load_cover(self.app, "lawn/egypt.png", (WIN_W, WIN_H))
        except Exception:
            img = None
        if img is not None:
            surf.blit(img, (0, 0))
        else:
            ui.draw_gradient(surf, (0, 0, WIN_W, WIN_H),
                             (120, 88, 58), (32, 24, 18))
        ui.draw_dim(surf, None, 202, (14, 12, 10))
        return surf

    def draw(self, surf):
        if self._bg is None:
            self._bg = self._build_bg()
        surf.blit(self._bg, (0, 0))
        ui.draw_gradient(surf, (0, 0, WIN_W, 104), (94, 64, 40), (52, 34, 22))
        pygame.draw.line(surf, ui.GOLD, (0, 103), (WIN_W, 103), 2)
        ui.text(surf, self._font_cached(30, True), "砸罐子", (160, 20),
                ui.CREAM, shadow=(20, 14, 10))
        ui.text(surf, self._font_cached(15),
                "敲开罐子，用阳光种下植物，清光所有僵尸",
                (162, 62), (236, 218, 186))
        self.btn_back.draw(surf)
        for rect, game in self.cards:
            self._draw_card(surf, rect, game)
        self.btn_prev.draw(surf)
        self.btn_next.draw(surf)
        if self.page_count > 1:
            ui.draw_chip(surf, self.app,
                         f"第 {self.page + 1} / {self.page_count} 页",
                         (GRID_X, WIN_H - 41), size=14, bg=(30, 24, 18),
                         fg=(246, 224, 170), pad_x=12, pad_y=5, radius=8,
                         border=(132, 104, 68))
        ui.text(surf, self._font_cached(14),
                "点击关卡开始 · 滚轮翻页 · ESC 返回更多玩法",
                (WIN_W // 2, WIN_H - 16), (214, 200, 176), anchor="center")
        self.toast.draw(surf)
        self.draw_fade(surf)

    def _draw_card(self, surf, rect, game):
        hover = rect.collidepoint(self.mouse)
        body = rect.move(0, -3) if hover else rect
        ui.draw_shadow(surf, body, radius=14, alpha=90,
                       offset=(0, 6 if hover else 4))
        ui.draw_gradient(surf, body, (120, 94, 62), (54, 40, 28), radius=14)
        pygame.draw.rect(surf, ui.GOLD if hover else (140, 112, 74), body, 3,
                         border_radius=14)
        # 罐子图标
        cx, cy = body.x + 74, body.centery
        pygame.draw.circle(surf, (206, 176, 128), (cx, cy + 10), 34)
        pygame.draw.polygon(surf, (226, 200, 156), [
            (cx - 26, cy - 18), (cx + 26, cy - 18), (cx + 18, cy + 22),
            (cx - 18, cy + 22)])
        pygame.draw.polygon(surf, (150, 110, 60), [
            (cx - 26, cy - 18), (cx + 26, cy - 18), (cx + 18, cy + 22),
            (cx - 18, cy + 22)], 3)
        pygame.draw.rect(surf, (196, 152, 96),
                         (cx - 30, cy - 34, 60, 14), border_radius=5)
        pygame.draw.line(surf, (120, 84, 48), (cx - 10, cy - 2),
                         (cx + 8, cy + 12), 3)
        pygame.draw.line(surf, (120, 84, 48), (cx + 8, cy + 12),
                         (cx - 2, cy + 24), 3)
        tx = body.x + 132
        ui.text(surf, self._font_cached(22, True),
                ui.fit_text(self._font_cached(22, True), game["title_zh"],
                            body.w - 152),
                (tx, body.y + 20), ui.CREAM, shadow=(18, 12, 8))
        ui.draw_wrapped(surf, self._font_cached(14), game["desc_zh"],
                        pygame.Rect(tx, body.y + 58, body.w - 154, 56),
                        color=(238, 226, 202), line_height=20, max_lines=2)
        ui.draw_chip(surf, self.app, f"罐子 {len(game['vases'])} 个",
                     (tx, body.bottom - 40), size=12, bg=(30, 24, 18),
                     fg=ui.GOLD, pad_x=10, pad_y=3, radius=7)


class VasebreakerScreen(Screen):
    name = "minigame_level"

    def __init__(self, app):
        super().__init__(app)
        self._fonts = {}
        self.toast = ui.Toast(app)
        self.game = None
        self.session = None
        self.error = ""
        self._finish_applied = False
        self.btn_back = ui.Button(app, (1152, 666, 108, 38), "返回",
                                  on_click=self._back, style="cream",
                                  font_size=16)
        self.btn_replay = ui.Button(app, (656, 452, 264, 56), "再来一次",
                                    on_click=self._replay, style="primary",
                                    font_size=20)
        self.btn_result_back = ui.Button(app, (360, 452, 264, 56), "返回列表",
                                         on_click=self._back, style="cream",
                                         font_size=20)

    def enter(self):
        super().enter()
        payload = getattr(self.app, "ui_payload", None)
        if isinstance(payload, dict) and isinstance(payload.get("minigame"), dict):
            # App.start_minigame 传 {"minigame": 关卡定义}
            payload = payload["minigame"]
        if isinstance(payload, dict) and "vases" not in payload \
                and isinstance(payload.get("level"), dict):
            payload = payload["level"]
        self.game = payload if isinstance(payload, dict) else None
        self._build_session()

    def exit(self):
        self.session = None

    def _build_session(self):
        self.session = None
        self.error = ""
        self._finish_applied = False
        if not isinstance(self.game, dict):
            self.error = "没有选中的砸罐子关卡"
            return
        try:
            from ..engine.modes import VasebreakerSession
            world = self.app.data.world(self.game.get("world", "frontyard"))
            self.session = VasebreakerSession(
                self.app, self.game, world, on_finish=self._on_finish)
            try:
                self.app.audio.play_world(world.id)
            except Exception:
                pass
        except Exception as exc:
            self.error = f"砸罐子初始化失败：{exc}"

    def _on_finish(self, won=False, *args, **kwargs):
        if self._finish_applied:
            return
        self._finish_applied = True
        try:
            self.app.audio.play_jingle("victory" if won else "defeat")
        except Exception:
            pass

    def _back(self):
        self.app.switch("minigames")

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
            self.error = f"砸罐子运行异常：{exc}"
            self.session = None

    def update(self, dt):
        super().update(dt)
        self.toast.update(dt)
        if self.session is not None and self._status() == "playing":
            try:
                self.session.update(dt)
            except Exception as exc:
                self.error = f"砸罐子运行异常：{exc}"
                self.session = None

    def _font_cached(self, size, bold=False):
        key = (int(size), bool(bold))
        font = self._fonts.get(key)
        if font is None:
            font = _font(self.app, size, bold)
            self._fonts[key] = font
        return font

    def _draw_bg(self, surf):
        if getattr(self, "_bg", None) is None:
            self._bg = None
            try:
                wd = getattr(self.session, "world_def", None)
                wid = (getattr(wd, "id", None)
                       or getattr(getattr(self.session, "level_def", None), "world", None)
                       or "frontyard")
                key = f"lawn/{wid}.png"
                img = self.app.assets.image(key)
                if img is not None and img.get_width() > 200:
                    self._bg = pygame.transform.smoothscale(img, (WIN_W, WIN_H))
            except Exception:
                self._bg = None
            if self._bg is None:
                bg = pygame.Surface((WIN_W, WIN_H))
                ui.draw_gradient(bg, (0, 0, WIN_W, WIN_H), (96, 122, 74),
                                 (52, 70, 44))
                self._bg = bg
        surf.blit(self._bg, (0, 0))

    def _draw_vases(self, surf):
        session = self.session
        for v in getattr(session, "vases", []) or []:
            if v.get("broken"):
                continue
            rect = session._vase_rect(v)
            body = pygame.Rect(rect.x + 6, rect.y + 12, rect.w - 12, rect.h - 12)
            pygame.draw.ellipse(surf, (0, 0, 0, 70), body.move(0, 6))
            pygame.draw.ellipse(surf, (176, 112, 62), body)
            pygame.draw.ellipse(surf, (128, 76, 40), body, 3)
            rim = pygame.Rect(body.x + 4, body.y - 4, body.w - 8, 14)
            pygame.draw.ellipse(surf, (196, 132, 78), rim)
            pygame.draw.ellipse(surf, (128, 76, 40), rim, 2)
            pygame.draw.arc(surf, (226, 176, 118),
                            body.inflate(-14, -18), 0.6, 2.2, 3)

    def draw(self, surf):
        if self.session is not None:
            try:
                self._draw_bg(surf)
                self.session.draw(surf)
                self._draw_vases(surf)
            except Exception as exc:
                self.error = f"砸罐子绘制失败：{exc}"
                self.session = None
        else:
            ui.draw_gradient(surf, (0, 0, WIN_W, WIN_H), (60, 50, 36),
                             (24, 20, 16))
            ui.text(surf, self._font_cached(24, True), self.error or "加载中…",
                    (WIN_W // 2, WIN_H // 2), (236, 210, 180), anchor="center")

        if self.session is not None:
            vases = getattr(self.session, "vases", [])
            left = sum(1 for v in vases if not v.get("broken"))
            ui.text(surf, self._font_cached(16, True), f"剩余罐子 {left}",
                    (WIN_W - 14, 150), (248, 226, 168), shadow=(20, 14, 10),
                    anchor="topright")
        self.btn_back.draw(surf)

        status = self._status()
        if status in ("won", "lost"):
            ui.draw_dim(surf, None, 150, (10, 12, 10))
            panel = pygame.Rect(340, 196, 600, 340)
            ui.draw_shadow(surf, panel, radius=18, alpha=120, offset=(0, 8))
            pygame.draw.rect(surf, (246, 238, 216), panel, border_radius=18)
            pygame.draw.rect(surf, ui.GOLD_DARK, panel, 3, border_radius=18)
            title = "砸罐子完成！" if status == "won" else "防线被突破"
            color = (86, 132, 62) if status == "won" else (170, 72, 56)
            ui.text(surf, self._font_cached(38, True), title,
                    (panel.centerx, panel.y + 76), color, anchor="center")
            ui.text(surf, self._font_cached(18),
                    "干得漂亮，所有僵尸都被清理干净。" if status == "won"
                    else "罐子里的僵尸冲破了防线。",
                    (panel.centerx, panel.y + 138), (96, 82, 64),
                    anchor="center")
            self.btn_result_back.draw(surf)
            self.btn_replay.draw(surf)
        self.toast.draw(surf)
        self.draw_fade(surf)


__all__ = ["VasebreakerHubScreen", "VasebreakerScreen"]
