"""僵尸博士（Boss）模式：Boss 列表 + 战斗包装。

- :class:`BossHubScreen`  读 ``content/bosses.json`` 列出 Boss、HP 与奖励。
- :class:`BossScreen`     包装 ``game.engine.modes.BossSession``，顶部 Boss 血条。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pygame

from .base import Screen
from . import widgets as ui

WIN_W, WIN_H = 1280, 720

CARD_W, CARD_H = 380, 150
GAP_X, GAP_Y = 20, 16
COLS = 3
GRID_X = (WIN_W - (COLS * CARD_W + (COLS - 1) * GAP_X)) // 2
GRID_Y = 156

WORLD_NAMES = {
    "frontyard": "前院", "egypt": "埃及", "pirate": "海盗", "cowboy": "西部",
    "future": "未来", "dark": "黑暗", "beach": "海滩", "lostcity": "失落之城",
    "chinesegarden": "中式花园", "kongfu": "功夫", "plantagenet": "金雀花",
    "losantosvice": "洛圣都", "lunarrainbowmarket": "月虹市场",
}
WORLD_PALETTES = {
    "frontyard": (116, 176, 96), "egypt": (226, 188, 104),
    "pirate": (92, 160, 178), "cowboy": (214, 158, 92),
    "future": (116, 188, 192), "dark": (138, 120, 174),
    "beach": (108, 190, 206), "lostcity": (176, 186, 108),
    "chinesegarden": (206, 124, 116), "kongfu": (220, 170, 96),
    "plantagenet": (156, 180, 126),
}
_BOSS_VARIANTS = {
    "egypt": ("僵尸博士·法老诅咒", 9000, 250),
    "pirate": ("僵尸博士·深海炮手", 8600, 250),
    "beach": ("僵尸博士·巨浪机甲", 8800, 250),
    "cowboy": ("僵尸博士·蒸汽火车", 9200, 250),
    "kongfu": ("僵尸博士·武馆宗师", 9400, 300),
    "chinesegarden": ("僵尸博士·戏曲毁灭者", 9600, 300),
    "plantagenet": ("僵尸博士·金雀花王座", 10000, 350),
}


def _font(app, size, bold=False):
    try:
        return app.font(size, bold)
    except Exception:
        try:
            return app.assets.font(size, bold)
        except Exception:
            return pygame.font.Font(None, int(size))


def _content_path(name):
    try:
        from .. import config
        return config.CONTENT_DIR / name
    except Exception:
        from pathlib import Path
        return Path(__file__).resolve().parents[2] / "content" / name


def _fallback_bosses():
    out = []
    for wid, (title, hp, reward) in _BOSS_VARIANTS.items():
        out.append({"id": f"boss_{wid}", "world": wid, "title": title,
                    "hp": hp, "minions": [], "art": "", "reward": reward})
    return out


def load_bosses(app=None):
    """读取 content/bosses.json；缺失时返回内置 Boss 列表。"""
    raw = None
    if app is not None:
        try:
            raw = app.content_json("bosses", None)
        except Exception:
            raw = None
    if raw is None:
        try:
            path = _content_path("bosses.json")
            if path.exists():
                raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            raw = None
    entries = []
    if isinstance(raw, dict):
        entries = raw.get("bosses") or raw.get("levels") or []
    elif isinstance(raw, list):
        entries = raw
    bosses = []
    for i, entry in enumerate(entries or []):
        if not isinstance(entry, dict):
            continue
        wid = str(entry.get("world") or "frontyard")
        try:
            hp = int(entry.get("hp", 9000) or 9000)
        except (TypeError, ValueError):
            hp = 9000
        try:
            reward = int(entry.get("reward", 250) or 250)
        except (TypeError, ValueError):
            reward = 250
        bosses.append({
            "id": str(entry.get("id") or f"boss_{i}"),
            "world": wid,
            "title": str(entry.get("title") or
                         f"僵尸博士·{WORLD_NAMES.get(wid, wid)}"),
            "hp": hp,
            "minions": list(entry.get("minions") or []),
            "art": str(entry.get("art") or ""),
            "reward": reward,
            "name_zh": str(entry.get("name_zh") or ""),
            "phases": list(entry.get("phases") or []),
        })
    if not bosses:
        bosses = _fallback_bosses()
    return bosses


class BossHubScreen(Screen):
    name = "bosses"

    def __init__(self, app):
        super().__init__(app)
        self._fonts = {}
        self._bg = None
        self.toast = ui.Toast(app)
        self.bosses = load_bosses(app)
        self.cards = []
        self.page = 0
        self.per_page = COLS * 3
        self._layout()
        self.btn_back = ui.Button(
            app, (24, 22, 110, 46), "返回", on_click=self._back,
            style="cream", font_size=18)
        self.btn_prev = ui.Button(
            app, (WIN_W // 2 - 190, WIN_H - 62, 96, 40), "上一页",
            on_click=lambda: self._turn_page(-1), style="cream", font_size=16)
        self.btn_next = ui.Button(
            app, (WIN_W // 2 + 94, WIN_H - 62, 96, 40), "下一页",
            on_click=lambda: self._turn_page(1), style="cream", font_size=16)

    def _page_count(self):
        return max(1, (len(self.bosses) + self.per_page - 1) // self.per_page)

    def _turn_page(self, delta):
        page = max(0, min(self._page_count() - 1, self.page + int(delta)))
        if page != self.page:
            self.page = page
            self._layout()

    def _layout(self):
        self.cards = []
        start = self.page * self.per_page
        for i, boss in enumerate(self.bosses[start:start + self.per_page]):
            row, col = divmod(i, COLS)
            rect = pygame.Rect(GRID_X + col * (CARD_W + GAP_X),
                               GRID_Y + row * (CARD_H + GAP_Y),
                               CARD_W, CARD_H)
            self.cards.append((rect, boss))

    def enter(self):
        super().enter()
        self.bosses = load_bosses(self.app)
        self._layout()
        try:
            self.app.audio.play_menu()
        except Exception:
            pass

    def exit(self):
        self._bg = None

    def _back(self):
        self.app.switch("modes")

    def _open(self, boss):
        wid = str(boss.get("world") or "egypt")
        try:
            self.app.ui_payload = {"world": wid, "boss": boss}
        except Exception:
            pass
        starter = getattr(self.app, "start_boss", None)
        if callable(starter):
            try:
                starter(wid)
                return
            except KeyError:
                self.toast.show("Boss 战斗界面尚未接入", 2.4)
                return
            except Exception:
                pass
        try:
            self.app.switch("boss_level")
        except KeyError:
            self.toast.show("Boss 战斗界面尚未接入", 2.4)
        except Exception as exc:
            self.toast.show(f"无法进入 Boss 战：{exc}", 2.4)

    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._back()
            return
        if self.btn_back.handle(event):
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            for rect, boss in self.cards:
                if rect.collidepoint(event.pos):
                    self._open(boss)
                    return

    def update(self, dt):
        super().update(dt)
        self.toast.update(dt)
        self.btn_back.update(dt)
        self.btn_prev.update(dt)
        self.btn_next.update(dt)

    def handle_event(self, event):
        if self.btn_back.handle(event):
            return True
        if self.btn_prev.handle(event):
            return True
        if self.btn_next.handle(event):
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._back()
                return True
            if event.key in (pygame.K_LEFT, pygame.K_PAGEUP):
                self._turn_page(-1)
                return True
            if event.key in (pygame.K_RIGHT, pygame.K_PAGEDOWN):
                self._turn_page(1)
                return True
        if event.type == pygame.MOUSEWHEEL:
            self._turn_page(-1 if event.y > 0 else 1)
            return True
        return super().handle_event(event)

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
            img = ui.load_cover(self.app, "lawn/egypt.png", (WIN_W, WIN_H))
        except Exception:
            img = None
        if img is not None:
            surf.blit(img, (0, 0))
        else:
            ui.draw_gradient(surf, (0, 0, WIN_W, WIN_H),
                             (96, 74, 56), (28, 24, 20))
        ui.draw_dim(surf, None, 208, (14, 12, 10))
        return surf

    def draw(self, surf):
        if self._bg is None:
            self._bg = self._build_bg()
        surf.blit(self._bg, (0, 0))

        ui.draw_gradient(surf, (0, 0, WIN_W, 96), (78, 48, 40), (50, 30, 26))
        pygame.draw.line(surf, ui.GOLD, (0, 95), (WIN_W, 95), 2)
        pygame.draw.rect(surf, (30, 20, 16), (0, 0, WIN_W, 96), 2)
        ui.text(surf, self._font_cached(30, True), "僵尸博士", (160, 22),
                ui.CREAM, shadow=(20, 12, 10))
        ui.text(surf, self._font_cached(15),
                "驾驶巨型机械的博士正在逼近，带上你最精锐的植物",
                (162, 62), (236, 206, 186))
        self.btn_back.draw(surf)

        for rect, boss in self.cards:
            self._draw_card(surf, rect, boss)

        pages = self._page_count()
        if pages > 1:
            self.btn_prev.draw(surf)
            self.btn_next.draw(surf)
            ui.text(surf, self._font_cached(15, True),
                    f"{self.page + 1} / {pages}",
                    (WIN_W // 2, WIN_H - 42), (232, 216, 190), anchor="center")
        ui.text(surf, self._font_cached(13),
                "点击 Boss 开始挑战 · 击败获得金币 · ESC 返回",
                (WIN_W - 26, 66), (214, 196, 176), anchor="topright")
        self.toast.draw(surf)
        self.draw_fade(surf)

    def _draw_card(self, surf, rect, boss):
        wid = boss["world"]
        hover = rect.collidepoint(self.mouse)
        body = rect.move(0, -3) if hover else rect
        tint = WORLD_PALETTES.get(wid, (150, 120, 100))
        ui.draw_shadow(surf, body, radius=14, alpha=90,
                       offset=(0, 6 if hover else 4))
        ui.draw_gradient(surf, body, ui.shade(tint, 0.62),
                         ui.shade(tint, 0.28), radius=14)
        pygame.draw.rect(surf, ui.GOLD if hover else ui.shade(tint, 0.45),
                         body, 3, border_radius=14)

        portrait = pygame.Rect(body.x + 10, body.y + 12, 96, body.h - 24)
        ui.alpha_rect(surf, portrait, (18, 16, 12, 150), radius=10)
        self._draw_portrait(surf, portrait, boss)

        tx = body.x + 118
        ui.text(surf, self._font_cached(20, True),
                ui.fit_text(self._font_cached(20, True), boss["title"],
                            body.w - 132),
                (tx, body.y + 16), ui.CREAM, shadow=(18, 12, 8))
        ui.draw_chip(surf, self.app, WORLD_NAMES.get(wid, wid),
                     (tx, body.y + 46), size=12, bg=(24, 20, 16),
                     fg=(232, 214, 186), pad_x=9, pad_y=3, radius=7)

        # HP 预览条
        bar = pygame.Rect(tx, body.y + 82, body.w - 140, 12)
        pygame.draw.rect(surf, (28, 22, 18), bar, border_radius=6)
        pygame.draw.rect(surf, (176, 62, 48), bar, border_radius=6)
        pygame.draw.rect(surf, (120, 44, 36), bar, 2, border_radius=6)
        ui.text(surf, self._font_cached(13), f"HP {boss['hp']}",
                (tx, body.y + 100), (238, 214, 196))
        ui.draw_coin(surf, (tx + 12, body.y + 128), r=9)
        ui.text(surf, self._font_cached(14, True), f"奖励 {boss['reward']}",
                (tx + 28, body.y + 120), ui.GOLD)
        minions = len(boss.get("minions") or [])
        if minions:
            ui.text(surf, self._font_cached(12), f"随从 {minions} 种",
                    (body.right - 14, body.y + 122), (214, 198, 176),
                    anchor="topright")

    def _draw_portrait(self, surf, rect, boss):
        art = boss.get("art") or ""
        if art and ("/" in art) and not art.lower().endswith(".png"):
            try:
                spr = self.app.assets.db_thumb(art, rect.w - 8, rect.h - 10,
                                               anim="Idle")
                if spr is not None:
                    surf.blit(spr, spr.get_rect(center=rect.center))
                    return
            except Exception:
                pass
        if art:
            try:
                spr = self.app.assets.static_sprite(art, rect.h - 10)
                if spr is not None:
                    if spr.get_width() > rect.w - 8:
                        w = rect.w - 8
                        spr = pygame.transform.smoothscale(
                            spr, (w, max(1, int(spr.get_height() * w /
                                                max(1, spr.get_width())))))
                    surf.blit(spr, spr.get_rect(center=rect.center))
                    return
            except Exception:
                pass
        # 程序化 Boss 头像：灰绿巨人 + 红眼 + 螺栓
        cx, cy = rect.center
        r = min(rect.w, rect.h) // 2 - 6
        pygame.draw.circle(surf, (86, 104, 74), (cx, cy), r)
        pygame.draw.circle(surf, (108, 128, 92), (cx, cy - 4), r - 6)
        pygame.draw.circle(surf, (36, 44, 30), (cx, cy), r, 3)
        pygame.draw.circle(surf, (196, 62, 46), (cx - r // 3, cy - r // 5),
                           max(3, r // 5))
        pygame.draw.circle(surf, (196, 62, 46), (cx + r // 3, cy - r // 5),
                           max(3, r // 5))
        pygame.draw.rect(surf, (210, 206, 190),
                         (cx - r // 2, cy + r // 3, r, max(4, r // 4)),
                         border_radius=3)
        for i in range(4):
            x = cx - r // 2 + i * r // 4
            pygame.draw.line(surf, (40, 40, 34), (x, cy + r // 3),
                             (x, cy + r // 3 + r // 4), 2)
        for sx in (-1, 1):
            pygame.draw.circle(surf, (168, 164, 150),
                               (cx + sx * (r + 2), cy - 2), max(3, r // 6))
            pygame.draw.circle(surf, (60, 58, 52),
                               (cx + sx * (r + 2), cy - 2), max(3, r // 6), 2)


class BossScreen(Screen):
    name = "boss_level"

    def __init__(self, app):
        super().__init__(app)
        self._fonts = {}
        self._bg = None
        self.toast = ui.Toast(app)
        self.boss_def = None
        self.world_id = "egypt"
        self.session = None
        self.error = ""
        self.reward_claimed = False
        self._finish_applied = False
        self.btn_pause = ui.Button(
            app, (WIN_W - 96, 20, 64, 46), "Ⅱ", on_click=self._toggle_pause,
            style="cream", font_size=20)
        self.btn_result_back = ui.Button(
            app, (360, 452, 264, 56), "返回列表", on_click=self._back,
            style="cream", font_size=20)
        self.btn_result_replay = ui.Button(
            app, (656, 452, 264, 56), "再战一次", on_click=self._replay,
            style="primary", font_size=20)
        self.btn_resume = ui.Button(
            app, (460, 318, 360, 54), "继续游戏", on_click=self._toggle_pause,
            style="green", font_size=21)
        self.btn_pause_back = ui.Button(
            app, (540, 392, 200, 48), "返回列表", on_click=self._back,
            style="cream", font_size=17)
        self.btn_retry = ui.Button(
            app, (540, 408, 200, 50), "重新加载", on_click=self._build_session,
            style="primary", font_size=18)
        self.btn_placeholder_back = ui.Button(
            app, (540, 486, 200, 48), "返回列表", on_click=self._back,
            style="cream", font_size=18)

    # ------------------------------------------------------------ 生命周期
    def enter(self):
        super().enter()
        payload = getattr(self.app, "ui_payload", None)
        boss = None
        wid = None
        if isinstance(payload, dict):
            boss = payload.get("boss")
            if not isinstance(boss, dict):
                boss = payload if "hp" in payload else None
            wid = payload.get("world")
        elif isinstance(payload, str):
            wid = payload
        if not wid:
            wid = getattr(self.app, "pending_world", None) or "egypt"
        self.world_id = str(wid)
        if not isinstance(boss, dict):
            boss = self._find_boss(self.world_id)
        self.boss_def = boss
        self._bg = None
        self._build_session()
        try:
            self.app.audio.play_world(self.world_id)
        except Exception:
            pass

    def _find_boss(self, wid):
        for entry in load_bosses(self.app):
            if str(entry.get("world")) == str(wid):
                return entry
        bosses = load_bosses(self.app)
        return bosses[0] if bosses else None

    def _world_def(self):
        world = None
        try:
            world = self.app.data.world(self.world_id)
        except Exception:
            world = None
        if world is None:
            world = SimpleNamespace(
                id=self.world_id, name_zh=WORLD_NAMES.get(self.world_id,
                                                          self.world_id),
                name_en=self.world_id, order=0, levels=[], map=None, lawn=None,
                unlock_after=None, desc_zh="", bg_tint=None, extra={})
        return world

    def exit(self):
        self.session = None

    def _build_session(self):
        self.session = None
        self.error = ""
        self.reward_claimed = False
        self._finish_applied = False
        if not isinstance(self.boss_def, dict):
            self.error = "没有选中的 Boss 关卡"
            return
        try:
            from ..engine.modes import BossSession
        except ImportError as exc:
            self.error = f"Boss 引擎尚未就绪：{exc}"
            return
        except Exception as exc:
            self.error = f"Boss 引擎加载失败：{exc}"
            return
        try:
            self.session = BossSession(
                self.app, self._world_def(), self.boss_def,
                on_finish=self._on_finish)
        except Exception as exc:
            self.session = None
            self.error = f"Boss 战初始化失败：{exc}"

    def _on_finish(self, won=False, *args, **kwargs):
        if self._finish_applied:
            return
        self._finish_applied = True
        won = bool(won)
        finisher = getattr(self.app, "finish_boss", None)
        applied = False
        if callable(finisher):
            try:
                finisher(self.world_id, won)
                applied = True
            except Exception:
                applied = False
        if won:
            self._claim_reward(already=applied)
        try:
            self.app.audio.play_jingle("victory" if won else "defeat")
        except Exception:
            pass

    def _claim_reward(self, already=False):
        if self.reward_claimed or not isinstance(self.boss_def, dict):
            return
        self.reward_claimed = True
        if already:
            self.toast.show("僵尸博士被击败，奖励已发放！", 3.0)
            return
        try:
            reward = int(self.boss_def.get("reward", 0) or 0)
        except (TypeError, ValueError):
            reward = 0
        if reward <= 0:
            return
        save = getattr(self.app, "save", None)
        if save is None:
            return
        try:
            add = getattr(save, "add_coins", None)
            if callable(add):
                add(reward)
            else:
                save.coins = int(getattr(save, "coins", 0) or 0) + reward
                save.save()
            self.toast.show(f"击败僵尸博士，获得 {reward} 金币！", 3.0)
        except Exception:
            pass

    # ------------------------------------------------------------ 动作
    def _back(self):
        self.app.switch("bosses")

    def _toggle_pause(self):
        if self.session is None or self._status() != "playing":
            return
        toggle = getattr(self.session, "toggle_pause", None)
        if callable(toggle):
            try:
                toggle()
                return
            except Exception:
                pass
        self.session.paused = not bool(getattr(self.session, "paused", False))

    def _replay(self):
        self._build_session()
        if self.session is None:
            self.toast.show(self.error or "Boss 战重新加载失败", 2.6)

    def _status(self):
        if self.session is None:
            return "none"
        return str(getattr(self.session, "status", "playing"))

    def _paused(self):
        return bool(getattr(self.session, "paused", False)) \
            if self.session is not None else False

    def _boss_hp(self):
        hp = getattr(self.session, "boss_hp", None)
        if hp is None:
            max_hp = self._raw_max_hp()
            ratio = getattr(self.session, "boss_ratio", None)
            if ratio is not None:
                try:
                    return max(0, int(round(max_hp * float(ratio))))
                except (TypeError, ValueError):
                    pass
        if hp is None and isinstance(self.boss_def, dict):
            hp = self.boss_def.get("hp", 0)
        try:
            return max(0, int(hp))
        except (TypeError, ValueError):
            return 0

    def _raw_max_hp(self):
        hp = getattr(self.session, "boss_hp_max", None)
        if not hp and isinstance(self.boss_def, dict):
            hp = self.boss_def.get("hp", 1)
        try:
            return max(1, int(hp))
        except (TypeError, ValueError):
            return 1

    def _boss_max_hp(self):
        return self._raw_max_hp()

    def _boss_phase(self):
        phase = getattr(self.session, "boss_phase", None)
        if phase:
            return phase
        frac = self._boss_hp() / float(max(1, self._raw_max_hp()))
        if frac > 0.66:
            return 1
        if frac > 0.33:
            return 2
        return 3

    # ------------------------------------------------------------ 事件
    def handle(self, event):
        super().handle(event)
        status = self._status()

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._back()
            return

        if status != "playing":
            self.btn_result_back.handle(event)
            self.btn_result_replay.handle(event)
            return

        if self.session is None:
            self.btn_retry.handle(event)
            self.btn_placeholder_back.handle(event)
            return

        if self._paused():
            self.btn_resume.handle(event)
            self.btn_pause_back.handle(event)
            return

        if self.btn_pause.handle(event):
            return
        try:
            self.session.handle_event(event)
        except Exception as exc:
            self.error = f"Boss 战运行异常：{exc}"
            self.session = None

    def update(self, dt):
        super().update(dt)
        self.toast.update(dt)
        if self.session is None or self._status() != "playing":
            return
        if self._paused():
            return
        try:
            self.session.update(dt)
        except Exception as exc:
            self.error = f"Boss 战运行异常：{exc}"
            self.session = None

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
            tint = WORLD_PALETTES.get(self.world_id, (150, 120, 100))
            ui.draw_gradient(surf, (0, 0, WIN_W, WIN_H),
                             ui.shade(tint, 0.9), ui.shade(tint, 0.35))
        return surf

    def draw(self, surf):
        if self._bg is None:
            self._bg = self._build_bg()
        surf.blit(self._bg, (0, 0))

        if self.session is not None:
            try:
                wd = getattr(self.session, "world_def", None)
                wid = getattr(wd, "id", None) or "frontyard"
                self.world_bg(surf, wid)
                self.session.draw(surf)
            except Exception as exc:
                self.error = f"Boss 战绘制异常：{exc}"
                self.session = None

        if self.session is None:
            self._draw_placeholder(surf)
        else:
            if self._status() == "playing" and not self._paused():
                self._draw_boss_bar(surf)
                self.btn_pause.draw(surf)
            if self._status() != "playing":
                self._draw_result(surf)
            elif self._paused():
                self._draw_pause(surf)

        self.toast.draw(surf)
        self.draw_fade(surf)

    def _draw_boss_bar(self, surf):
        hp = self._boss_hp()
        max_hp = self._boss_max_hp()
        frac = max(0.0, min(1.0, hp / float(max_hp)))
        # 顶部 HUD（阳光/卡牌/铲子/暂停）占 0..112，血条放在其下方、草坪上沿
        panel = pygame.Rect(196, 112, 894, 26)
        ui.draw_shadow(surf, panel, radius=10, alpha=90, offset=(0, 3))
        ui.alpha_rect(surf, panel, (28, 16, 14, 226), radius=10)
        pygame.draw.rect(surf, (176, 108, 70), panel, 2, border_radius=10)

        title = str((self.boss_def or {}).get("title", "僵尸博士"))
        ui.text(surf, self._font_cached(13, True),
                ui.fit_text(self._font_cached(13, True), title, 190),
                (panel.x + 12, panel.centery), ui.CREAM, anchor="midleft")

        bar = pygame.Rect(panel.x + 210, panel.y + 7, 470, 12)
        pygame.draw.rect(surf, (26, 18, 16), bar, border_radius=6)
        if frac > 0:
            fill = pygame.Rect(bar.x, bar.y, max(4, int(bar.w * frac)), bar.h)
            ui.draw_gradient(surf, fill, (226, 84, 62), (156, 40, 34),
                             radius=6)
        pygame.draw.rect(surf, (240, 208, 168), bar, 2, border_radius=6)
        ui.text(surf, self._font_cached(12, True), f"{hp} / {max_hp}",
                (bar.right + 10, panel.centery), (244, 218, 190),
                anchor="midleft")
        phase = self._boss_phase()
        if phase:
            ui.text(surf, self._font_cached(12, True), f"阶段 {phase}",
                    (panel.right - 12, panel.centery), ui.GOLD,
                    anchor="midright")

    def _draw_result(self, surf):
        ui.draw_dim(surf, None, 150)
        panel = pygame.Rect(320, 168, 640, 384)
        ui.draw_panel(surf, panel, fill=ui.PAPER, border=ui.BROWN,
                      radius=18, border_width=3)
        pygame.draw.rect(surf, ui.BROWN, (panel.x, panel.y, panel.w, 74),
                         border_top_left_radius=18, border_top_right_radius=18)
        won = self._status() == "won"
        title = "僵尸博士被击败！" if won else "博士逃走了"
        ui.text(surf, self._font_cached(34, True), title,
                (panel.centerx, panel.y + 37),
                ui.GOLD if won else (236, 196, 176), anchor="center",
                shadow=(30, 20, 12))
        if won:
            try:
                reward = int((self.boss_def or {}).get("reward", 0) or 0)
            except (TypeError, ValueError):
                reward = 0
            msg = f"奖励 {reward} 金币已存入钱包。" if reward else \
                "博士的机械残骸还在冒烟。"
        else:
            msg = "巨型机械太强了，调整卡组再来一次吧。"
        ui.draw_wrapped(surf, self._font_cached(18), msg,
                        pygame.Rect(panel.x + 60, panel.y + 104,
                                    panel.w - 120, 100),
                        color=ui.INK_SOFT, line_height=27, align="center")
        hp = self._boss_hp()
        max_hp = self._boss_max_hp()
        ui.text(surf, self._font_cached(14),
                f"博士剩余生命 {hp} / {max_hp}",
                (panel.centerx, panel.y + 212), ui.INK_FAINT,
                anchor="midtop")
        self.btn_result_back.draw(surf)
        self.btn_result_replay.draw(surf)

    def _draw_pause(self, surf):
        ui.draw_dim(surf, None, 140)
        panel = pygame.Rect(400, 196, 480, 300)
        ui.draw_panel(surf, panel, fill=ui.PAPER, border=ui.BROWN,
                      radius=18, border_width=3)
        pygame.draw.rect(surf, ui.BROWN, (panel.x, panel.y, panel.w, 66),
                         border_top_left_radius=18, border_top_right_radius=18)
        ui.text(surf, self._font_cached(30, True), "已暂停",
                (panel.centerx, panel.y + 33), ui.GOLD, anchor="center")
        ui.text(surf, self._font_cached(15), "ESC 返回 Boss 列表",
                (panel.centerx, 276), ui.INK_SOFT, anchor="center")
        self.btn_resume.draw(surf)
        self.btn_pause_back.draw(surf)

    def _draw_placeholder(self, surf):
        panel = pygame.Rect(260, 190, 760, 380)
        ui.draw_panel(surf, panel, fill=ui.PAPER, border=ui.BROWN,
                      radius=18, border_width=3)
        pygame.draw.rect(surf, ui.BROWN, (panel.x, panel.y, panel.w, 72),
                         border_top_left_radius=18, border_top_right_radius=18)
        ui.text(surf, self._font_cached(30, True), "僵尸博士",
                (panel.centerx, panel.y + 36), ui.GOLD, anchor="center")
        msg = self.error or "Boss 数据缺失"
        ui.draw_wrapped(surf, self._font_cached(16), msg,
                        pygame.Rect(panel.x + 60, panel.y + 100,
                                    panel.w - 120, 120),
                        color=ui.INK_SOFT, line_height=24, align="center")
        ui.text(surf, self._font_cached(14),
                "引擎接入 game/engine/modes.py 后即可开战",
                (panel.centerx, 432), ui.INK_FAINT, anchor="center")
        self.btn_retry.draw(surf)
        self.btn_placeholder_back.draw(surf)


__all__ = ["BossHubScreen", "BossScreen", "load_bosses"]
