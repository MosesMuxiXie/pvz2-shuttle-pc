"""关卡战斗界面。

玩法由 ``game.engine.level.LevelSession`` 负责；本界面负责：
战场环境、关卡标签、加速/返回按钮、暂停遮罩、结算遮罩，以及最终把胜负
写回存档。引擎是后加的模块，导入或初始化失败时会降级成静态战场占位，
保证整套 UI 在开发早期也能完整跑通。
"""
from __future__ import annotations

import math
import random
from types import SimpleNamespace

import pygame

from ..config import (BOARD_COLS, BOARD_ROWS, BOARD_X, BOARD_Y, CELL_H,
                      CELL_W, WIN_H, WIN_W)
from . import widgets as ui
from .base import Screen

BOARD_W = BOARD_COLS * CELL_W
BOARD_H = BOARD_ROWS * CELL_H

CARD_W, CARD_H, CARD_GAP = 76, 96, 6
CARDS_X, CARDS_Y = 118, 8

WORLD_NAMES = {
    "frontyard": "前院草坪",
    "egypt": "神秘埃及",
    "pirate": "海盗港湾",
    "cowboy": "狂野西部",
    "future": "未来世界",
    "dark": "黑暗时代",
    "beach": "巨浪沙滩",
    "lostcity": "失落之城",
}

WORLD_EN = {
    "frontyard": "FRONT YARD",
    "egypt": "ANCIENT EGYPT",
    "pirate": "PIRATE SEAS",
    "cowboy": "WILD WEST",
    "future": "FAR FUTURE",
    "dark": "DARK AGES",
    "beach": "BIG WAVE BEACH",
    "lostcity": "LOST CITY",
}

# sky_top, sky_bottom, lawn_a, lawn_b, accent
WORLD_PALETTES = {
    "frontyard": ((122, 192, 238), (206, 234, 248), (124, 176, 78),
                  (106, 160, 66), (247, 201, 72)),
    "egypt": ((238, 196, 132), (252, 231, 188), (214, 187, 112),
              (198, 168, 96), (255, 226, 150)),
    "pirate": ((124, 154, 194), (226, 205, 174), (110, 162, 98),
               (93, 142, 84), (248, 214, 142)),
    "cowboy": ((232, 184, 120), (252, 224, 168), (196, 170, 104),
               (178, 152, 90), (255, 220, 140)),
    "future": ((82, 104, 152), (168, 192, 220), (94, 152, 142),
               (80, 134, 124), (150, 240, 226)),
    "dark": ((46, 38, 70), (104, 82, 120), (92, 102, 76),
             (74, 86, 62), (200, 170, 230)),
    "beach": ((118, 200, 230), (224, 244, 246), (226, 206, 150),
              (210, 190, 134), (255, 248, 214)),
    "lostcity": ((132, 168, 138), (218, 212, 162), (120, 162, 110),
                 (102, 142, 94), (240, 220, 150)),
}


# --------------------------------------------------------------------------
# 兜底数据（content/*.json 尚未生成时使用）
# --------------------------------------------------------------------------
def _fallback_plants():
    def plant(pid, name, cost, cd, hp, behavior, **kw):
        base = dict(id=pid, name_zh=name, name_en=pid, cost=cost, cooldown=cd,
                    hp=hp, family="plant", behavior=behavior, damage=0,
                    interval=1.4, projectile="pea", rows=[0], pierce=False,
                    splash=0.0, slow=0.0, sun_value=25, sun_interval=24.0,
                    delay=0.0, melee_range=1.0, art="", tags=[], extra={})
        base.update(kw)
        return SimpleNamespace(**base)

    return {
        "sunflower": plant("sunflower", "向日葵", 50, 7.5, 300, "produce",
                           sun_value=25, sun_interval=24.0),
        "peashooter": plant("peashooter", "豌豆射手", 100, 7.5, 300, "shoot",
                            damage=20, interval=1.4),
        "wallnut": plant("wallnut", "坚果墙", 50, 30.0, 4000, "wall"),
        "snowpea": plant("snowpea", "寒冰射手", 175, 7.5, 300, "shoot",
                         damage=20, interval=1.4, slow=5.0),
        "cherrybomb": plant("cherrybomb", "樱桃炸弹", 150, 50.0, 300, "instant",
                            damage=1800, delay=1.1,
                            extra={"radius": 138.0}),
        "repeater": plant("repeater", "双发射手", 200, 7.5, 300, "shoot",
                          damage=20, interval=1.4),
        "potatomine": plant("potatomine", "土豆雷", 25, 30.0, 300, "mine",
                            damage=1800),
        "threepeater": plant("threepeater", "三线射手", 325, 7.5, 300, "shoot",
                             damage=20, interval=1.4, rows=[-1, 0, 1]),
        "cabbagepult": plant("cabbagepult", "卷心菜投手", 100, 7.5, 300, "lob",
                             damage=40, interval=3.0, splash=70.0),
    }


def _fallback_zombies():
    def zombie(zid, name, hp, speed=0.185, armor=None, eat_dps=100):
        return SimpleNamespace(id=zid, name_zh=name, name_en=zid, hp=hp,
                               speed=speed, eat_dps=eat_dps,
                               armor=armor or [], behavior="walk", art="",
                               armature=None, extra={})

    return {
        "basic": zombie("basic", "普通僵尸", 190),
        "flag": zombie("flag", "旗帜僵尸", 190, 0.21),
        "conehead": zombie("conehead", "路障僵尸", 190, armor=[
            {"hp": 370, "art": "", "name": "路障"}]),
        "buckethead": zombie("buckethead", "铁桶僵尸", 190, armor=[
            {"hp": 1100, "art": "", "name": "铁桶"}]),
    }


def _pick_deck(plants):
    preferred = ["sunflower", "peashooter", "wallnut", "snowpea",
                 "cherrybomb", "repeater", "potatomine", "threepeater"]
    deck = [pid for pid in preferred if pid in plants]
    if len(deck) < 6:
        for pid in plants:
            if pid not in deck:
                deck.append(pid)
            if len(deck) >= 6:
                break
    return deck[:6]


def _zombie_types(zombies):
    preferred = [z for z in ("basic", "conehead", "buckethead", "flag")
                 if z in zombies]
    if preferred:
        return preferred
    ids = list(zombies)
    return ids[:3] if ids else ["basic"]


def _fallback_waves(types):
    """6 波演示波次；没有内容数据时也能打完整局。"""
    types = list(types) or ["basic"]
    tank = types[-1]
    mid = types[min(1, len(types) - 1)]

    def wave(delay, rows, ztypes, flag=False):
        zombies = [SimpleNamespace(type=t, rows=list(rows)) for t in ztypes]
        return SimpleNamespace(delay=delay, flag=flag, zombies=zombies)

    return [
        wave(8.0, [1, 2], [types[0]]),
        wave(16.0, [0, 3], [types[0]]),
        wave(18.0, [1, 2, 4], [types[0], mid]),
        wave(20.0, [0, 2, 4], [mid, types[0]]),
        wave(22.0, [1, 3], [types[0], mid, tank], flag=True),
        wave(26.0, [0, 1, 2, 3, 4], [mid, tank, types[0]], flag=True),
    ]


class _SessionHost:
    """给 LevelSession 的 app 代理：只替换 data，其余原样转发。"""

    def __init__(self, app, data):
        self._app = app
        self.data = data
        self.assets = getattr(app, "assets", None)
        self.font = getattr(app, "font", None)

    def __getattr__(self, name):
        return getattr(self._app, name)


# --------------------------------------------------------------------------
# 关卡界面
# --------------------------------------------------------------------------
class LevelScreen(Screen):
    name = "level"

    def __init__(self, app):
        super().__init__(app)
        pending = getattr(app, "pending_level", None)
        if isinstance(pending, (tuple, list)) and len(pending) >= 2:
            self.world_id = str(pending[0])
            try:
                self.index = max(0, int(pending[1]))
            except (TypeError, ValueError):
                self.index = 0
        else:
            self.world_id, self.index = "frontyard", 0

        self.world_def = None
        self.level_def = None
        self.world_name = WORLD_NAMES.get(self.world_id, self.world_id)
        self.level_title = f"第 {self.index + 1} 关"
        self.session = None
        self.error = ""
        self.ff = False
        self._finish_applied = False
        self.earned_stars = None
        self.reward_coins = 0
        self.star_defs = []
        self.night = False
        self.toast = ui.Toast(app)
        self._fonts = {}
        self._bg = None
        self._build_buttons()

    # ------------------------------------------------------------ 生命周期
    def enter(self):
        super().enter()
        self._load_world()
        self._build_background()
        self._build_session()
        self._refresh_ff_button()
        try:
            self.app.audio.play_world(getattr(self.world_def, "id", self.world_id))
        except Exception:
            pass

    def exit(self):
        self.session = None

    # ------------------------------------------------------------ 数据解析
    def _load_world(self):
        world = None
        data = getattr(self.app, "data", None)
        try:
            if data is not None:
                world = data.world(self.world_id)
        except Exception:
            world = None
        if world is None:
            world = SimpleNamespace(
                id=self.world_id,
                name_zh=WORLD_NAMES.get(self.world_id, self.world_id),
                name_en=WORLD_EN.get(self.world_id, self.world_id.upper()),
                order=0, levels=10)
        self.world_def = world
        self.world_name = str(getattr(world, "name_zh", "") or
                              WORLD_NAMES.get(self.world_id, self.world_id))

    def _prepare_defs(self):
        data = getattr(self.app, "data", None)
        real_plants = dict(getattr(data, "plants", {}) or {})
        real_zombies = dict(getattr(data, "zombies", {}) or {})
        plants = real_plants or _fallback_plants()
        zombies = real_zombies or _fallback_zombies()

        real_level = None
        try:
            levels = list(data.levels(self.world_id)) if data is not None else []
        except Exception:
            levels = []
        if 0 <= self.index < len(levels):
            real_level = levels[self.index]

        deck = []
        if real_plants and real_level is not None:
            for pid in (getattr(real_level, "deck", []) or []):
                if pid in plants and pid not in deck:
                    deck.append(pid)
        if not deck:
            deck = _pick_deck(plants)

        waves = []
        if real_level is not None:
            waves = list(getattr(real_level, "waves", []) or [])
        if not waves or not real_zombies:
            waves = _fallback_waves(_zombie_types(zombies))

        try:
            sun = int(getattr(real_level, "sun", 250) or 250) \
                if real_level is not None else 250
        except (TypeError, ValueError):
            sun = 250
        title = str(getattr(real_level, "title", "") or "") \
            if real_level is not None else ""
        if not title:
            title = f"第 {self.index + 1} 关"
        self.level_title = title
        extra = getattr(real_level, "extra", {}) or {} \
            if real_level is not None else {}
        override = getattr(self.app, "pending_deck", None)
        if override:
            filtered = [pid for pid in override if pid in plants]
            if len(filtered) >= 1:
                deck = filtered
        self.night = bool((extra or {}).get("night")
                          or (getattr(self.world_def, "extra", {}) or {}).get("night"))
        self.star_defs = self._load_star_defs(
            str(getattr(real_level, "id", f"{self.world_id}_{self.index}")))
        level_def = SimpleNamespace(
            id=getattr(real_level, "id", f"{self.world_id}_{self.index}"),
            world=self.world_id,
            index=self.index,
            title=title,
            sun=sun,
            deck=deck,
            waves=waves,
            flags=getattr(real_level, "flags", 1) if real_level else 1,
            seed_bank=getattr(real_level, "seed_bank", 6) if real_level else 6,
            extra=dict(extra) if isinstance(extra, dict) else {},
        )
        host = _SessionHost(self.app, SimpleNamespace(plants=plants,
                                                     zombies=zombies))
        return host, self.world_def, level_def

    def _load_star_defs(self, level_id: str) -> list[dict]:
        data = getattr(self.app, "content_json", None)
        if data is None:
            return []
        try:
            stars = data("stars", {"levels": {}}) or {}
            entry = (stars.get("levels") or {}).get(level_id)
            if entry is None:
                entry = stars.get(level_id) or []
            return [s for s in entry if isinstance(s, dict)]
        except Exception:
            return []

    def _evaluate_stars(self, won: bool) -> list[bool]:
        session = self.session
        if session is None or not won:
            return [False] * 3
        kills = int(getattr(session, "zombie_killed", 0))
        mowers_used = int(getattr(session, "mowers_used", 0))
        seconds = float(getattr(session, "time", 0.0))
        sun_spent = int(getattr(session, "sun_spent", 0))
        sun_earned = int(getattr(session, "sun_earned", 0))
        plants_lost = int(getattr(session, "plants_lost", 0))
        max_plants = int(getattr(session, "max_plants", 0))
        defs = self.star_defs or [
            {"type": "beat"}, {"type": "mowers"}, {"type": "kill", "count": 10}]

        def _val(d, *keys, default=0):
            if "value" in d:
                try:
                    return int(d["value"])
                except Exception:
                    pass
            for k in keys:
                if k in d:
                    try:
                        return int(d[k])
                    except Exception:
                        return default
            return default

        rows = 5
        try:
            rows = int(getattr(self.session.board, "rows", 5))
        except Exception:
            pass
        out = []
        for d in defs[:3]:
            kind = str(d.get("type", "beat"))
            try:
                if kind == "beat":
                    ok = won
                elif kind == "mowers":
                    keep = _val(d, "max", default=rows)
                    # value 表示“保留的小推车数”，允许损失 rows-keep 辆
                    allowed = max(0, rows - keep) if ("value" in d) else keep
                    ok = mowers_used <= allowed
                elif kind == "kill":
                    ok = kills >= _val(d, "count", "target", default=10)
                elif kind == "time":
                    ok = seconds <= _val(d, "seconds", "value", default=300)
                elif kind == "sun_used":
                    ok = sun_spent <= _val(d, "max", default=3000)
                elif kind == "sun_produced":
                    ok = sun_earned >= _val(d, "target", default=1000)
                elif kind == "plants_lost":
                    ok = plants_lost <= _val(d, "max", default=2)
                elif kind == "plants_max":
                    ok = max_plants >= _val(d, "count", default=15)
                elif kind == "distance":
                    ok = True
                else:
                    ok = won
            except Exception:
                ok = won
            out.append(bool(ok))
        while len(out) < 3:
            out.append(bool(won))
        return out

    def _build_session(self):
        self.session = None
        self.error = ""
        try:
            from ..engine.level import LevelSession
        except Exception as exc:                    # engine not ready
            self.error = f"战斗引擎未就绪：{exc}"
            return
        try:
            host, world_def, level_def = self._prepare_defs()
            self.session = LevelSession(host, world_def, level_def,
                                        on_finish=self._on_finish)
            self.world_def = world_def
            self.level_def = level_def
            self.level_title = str(getattr(level_def, "title",
                                           self.level_title))
        except Exception as exc:                    # engine broken -> placeholder
            self.session = None
            self.error = f"战斗初始化失败：{exc}"

    # ------------------------------------------------------------ 按钮
    def _build_buttons(self):
        app = self.app
        self.btn_ff = ui.Button(
            app, (WIN_W - 96, 22, 62, 62), "1x",
            on_click=self._toggle_ff, style="cream", font_size=20)
        self.btn_back = ui.Button(
            app, (WIN_W - 104, 660, 88, 38), "地图",
            on_click=self._to_map, style="cream", font_size=15)

        self.btn_resume = ui.Button(
            app, (460, 318, 360, 54), "继续游戏",
            on_click=self._resume, style="green", font_size=21)
        self.btn_pause_map = ui.Button(
            app, (460, 392, 170, 46), "返回地图",
            on_click=self._to_map, style="cream", font_size=17)
        self.btn_pause_replay = ui.Button(
            app, (650, 392, 170, 46), "重玩",
            on_click=self._replay, style="primary", font_size=17)

        self.btn_result_map = ui.Button(
            app, (360, 452, 264, 56), "返回地图",
            on_click=self._to_map, style="cream", font_size=20)
        self.btn_result_replay = ui.Button(
            app, (656, 452, 264, 56), "重玩",
            on_click=self._replay, style="primary", font_size=20)

        self.btn_retry = ui.Button(
            app, (540, 402, 200, 50), "重新加载",
            on_click=self._retry, style="primary", font_size=18)

    def _refresh_ff_button(self):
        self.btn_ff.set_text("2x" if self.ff else "1x")
        self.btn_ff.style = "gold" if self.ff else "cream"

    # ------------------------------------------------------------ 动作
    def _toggle_ff(self):
        if not self.session or self.session.status != "playing":
            return
        self.ff = not self.ff
        self._refresh_ff_button()
        self.toast.show("已切换为 2 倍速" if self.ff else "已恢复 1 倍速", 1.5)

    def _to_map(self):
        self.app.switch("worldmap")

    def _resume(self):
        if self.session is not None and self.session.paused:
            self.session.toggle_pause()

    def _replay(self):
        self._finish_applied = False
        self.ff = False
        self._refresh_ff_button()
        self._build_session()
        if self.session is None:
            self.toast.show("重新加载失败，可返回地图", 2.4)
        else:
            self.toast.show("本关重新开始", 1.6)

    def _retry(self):
        self._build_session()
        if self.session is not None:
            self.toast.show("战斗已重新加载", 1.6)
        else:
            self.toast.show("仍无法加载战斗引擎", 2.2)

    def _on_finish(self, won):
        if self._finish_applied:
            return
        self._finish_applied = True
        stars = self._evaluate_stars(bool(won))
        self.earned_stars = stars
        self.reward_coins = (50 + 10 * self.index) if won else 0
        try:
            self.app.finish_level(self.world_id, self.index, bool(won),
                                  stars=stars, coins=self.reward_coins)
        except Exception:
            pass
        try:
            self.app.audio.play_jingle("victory" if won else "defeat")
        except Exception:
            pass
        self.toast.show("关卡胜利，进度已保存" if won
                        else "挑战失败，可以重玩本关", 3.0)

    # ------------------------------------------------------------ 事件
    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_f:
                self._toggle_ff()
                return
            if event.key == pygame.K_ESCAPE:
                if self.session is None:
                    self._to_map()
                    return
                if self.session.status != "playing":
                    self._to_map()
                    return
                self.session.toggle_pause()
                return
            if self.session is None:
                if event.key in (pygame.K_RETURN, pygame.K_r):
                    self._retry()
                return
            if self.session.status != "playing":
                if event.key in (pygame.K_RETURN, pygame.K_r):
                    self._replay()
                elif event.key in (pygame.K_m, pygame.K_ESCAPE):
                    self._to_map()
                return
            if self.session.paused:
                return
            # 1-9 选卡、P/Space 暂停、S 铲子等交给引擎
            self.session.handle_event(event)
            return

        # 结算遮罩
        if self.session is not None and self.session.status != "playing":
            for btn in (self.btn_result_map, self.btn_result_replay):
                btn.handle(event)
            return

        # 暂停遮罩
        if self.session is not None and self.session.paused:
            for btn in (self.btn_resume, self.btn_pause_map,
                        self.btn_pause_replay):
                btn.handle(event)
            return

        # 占位界面
        if self.session is None:
            self.btn_back.handle(event)
            self.btn_retry.handle(event)
            return

        # 正常战斗：浮动按钮 + 战斗内点击
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN,
                          pygame.MOUSEBUTTONUP):
            self.btn_ff.handle(event)
            self.btn_back.handle(event)
            if event.type == pygame.MOUSEBUTTONUP:
                return
        self.session.handle_event(event)

    # ------------------------------------------------------------ 更新
    def update(self, dt):
        super().update(dt)
        self.toast.update(dt)
        if self.session is None:
            return
        mult = 2.0 if self.ff else 1.0
        try:
            self.session.update(dt * mult)
        except Exception as exc:
            self.error = f"战斗运行异常：{exc}"
            self.session = None

    # ------------------------------------------------------------ 字体
    def _font(self, size, bold=False):
        key = (int(size), bool(bold))
        font = self._fonts.get(key)
        if font is None:
            try:
                font = self.app.font(size, bold)
            except Exception:
                font = pygame.font.Font(None, int(size))
            self._fonts[key] = font
        return font

    # ------------------------------------------------------------ 背景
    def _build_background(self):
        surf = pygame.Surface((WIN_W, WIN_H))
        # 整幅草坪模式（新世界用 Renders 合成的 1280×720 场景，棋盘已对齐）
        world_extra = getattr(self.world_def, "extra", None) or {}
        if isinstance(world_extra, dict) and world_extra.get("lawn_mode") == "full":
            try:
                lawn_name = f"lawn/{self.world_id}.png"
                night_flag = bool(getattr(self, "night", False))
                if not night_flag:
                    night_flag = bool((getattr(self.level_def, "extra", {}) or {})
                                      .get("night"))
                if night_flag and self.app.assets.has_image(
                        f"lawn/{self.world_id}_night.png"):
                    lawn_name = f"lawn/{self.world_id}_night.png"
                path = self.app.assets.resolve(lawn_name)
                if path.exists():
                    img = pygame.image.load(str(path)).convert()
                    if img.get_size() != (WIN_W, WIN_H):
                        img = pygame.transform.smoothscale(img, (WIN_W, WIN_H))
                    surf.blit(img, (0, 0))
                    # 顶部 HUD 底板 / 底部横条（与程序化背景保持一致）
                    ui.draw_gradient(surf, (0, 0, WIN_W, 112),
                                     (88, 68, 46), (50, 40, 29))
                    pygame.draw.line(surf, (210, 170, 96), (0, 111), (WIN_W, 111), 2)
                    pygame.draw.rect(surf, (28, 22, 16), (0, 0, WIN_W, 112), 2)
                    ui.draw_gradient(surf, (0, WIN_H - 26, WIN_W, 26),
                                     (60, 48, 34), (36, 30, 22))
                    self._bg = surf
                    return surf
            except Exception:
                pass
        pal = WORLD_PALETTES.get(self.world_id,
                                 WORLD_PALETTES["frontyard"])
        sky_top, sky_bot, lawn_a, lawn_b, accent = pal

        # 天空 + 远景（大部分会被草坪和顶栏遮住，留作边缘过渡）
        ui.draw_gradient(surf, (0, 0, WIN_W, BOARD_Y + 180),
                         sky_top, sky_bot)

        # 草坪底色
        top = BOARD_Y - 12
        pygame.draw.rect(surf, lawn_a, (0, top, WIN_W, WIN_H - top))

        # 真实草坪贴图：从 assets/lawn/<world>.png 取一格草地平铺，再压明暗条带
        grass_ok = False
        try:
            grass_path = self.app.assets.resolve(f"lawn/{self.world_id}.png")
            if grass_path.exists():
                lawn_img = pygame.image.load(str(grass_path)).convert()
                w, h = lawn_img.get_size()
                cell = lawn_img.subsurface((int(w * 0.368), int(h * 0.435),
                                            max(8, int(w * 0.039)),
                                            max(8, int(h * 0.092)))).copy()
                tile = pygame.transform.smoothscale(cell, (CELL_W, CELL_H))
                # 轻微提亮，避免与草坪底色脱节
                tile.fill((18, 24, 14), special_flags=pygame.BLEND_RGB_ADD)
                board_tex = pygame.Surface((BOARD_W, BOARD_H), pygame.SRCALPHA)
                for rr in range(BOARD_ROWS):
                    for cc in range(BOARD_COLS):
                        t = tile
                        if cc % 2:
                            t = pygame.transform.flip(t, True, False)
                        if rr % 2:
                            t = pygame.transform.flip(t, False, True)
                        board_tex.blit(t, (cc * CELL_W, rr * CELL_H))
                board_tex.set_alpha(165)
                pygame.draw.rect(surf, lawn_a,
                                 (BOARD_X, BOARD_Y, BOARD_W, BOARD_H))
                surf.blit(board_tex, (BOARD_X, BOARD_Y))
                grass_ok = True
        except Exception:
            grass_ok = False
        if not grass_ok:
            for row in range(BOARD_ROWS):
                color = lawn_a if row % 2 == 0 else lawn_b
                pygame.draw.rect(surf, color,
                                 (BOARD_X, BOARD_Y + row * CELL_H,
                                  BOARD_W, CELL_H))
        else:
            for row in range(BOARD_ROWS):
                if row % 2 == 1:
                    ui.alpha_rect(surf, (BOARD_X, BOARD_Y + row * CELL_H,
                                         BOARD_W, CELL_H), (24, 44, 16, 34))
        # 左右草带的轻微压暗
        ui.alpha_rect(surf, (0, top, BOARD_X, WIN_H - top), (30, 46, 20, 36))
        ui.alpha_rect(surf, (BOARD_X + BOARD_W, top,
                             WIN_W - BOARD_X - BOARD_W, WIN_H - top),
                      (30, 46, 20, 40))

        # 左侧小屋
        self._draw_house(surf, top)
        # 右侧灌木
        self._draw_hedge(surf)

        # 草坪上的小花，让空场不单调
        rng = random.Random(20261001 + sum(ord(c) for c in self.world_id))
        for _ in range(46):
            x = rng.randint(6, WIN_W - 8)
            if BOARD_X < x < BOARD_X + BOARD_W and rng.random() < 0.7:
                continue
            y = rng.randint(BOARD_Y + 20, WIN_H - 30)
            color = rng.choice([(255, 240, 150), (250, 220, 160),
                                (246, 246, 236)])
            pygame.draw.circle(surf, color, (x, y), rng.choice((1, 2, 2)))
            pygame.draw.line(surf, (68, 112, 52), (x, y + 2), (x, y + 5), 1)

        # 棋盘描边
        pygame.draw.rect(surf, (250, 244, 220),
                         (BOARD_X, BOARD_Y, BOARD_W, BOARD_H), 2)

        # 底部横条
        ui.draw_gradient(surf, (0, WIN_H - 26, WIN_W, 26),
                         (60, 48, 34), (36, 30, 22))

        # 顶部 HUD 底板
        ui.draw_gradient(surf, (0, 0, WIN_W, 112),
                         (88, 68, 46), (50, 40, 29))
        pygame.draw.line(surf, (210, 170, 96), (0, 111), (WIN_W, 111), 2)
        pygame.draw.rect(surf, (28, 22, 16), (0, 0, WIN_W, 112), 2)

        # 四角柔光
        ui.alpha_rect(surf, (0, 112, 12, WIN_H - 138), (0, 0, 0, 40))
        ui.alpha_rect(surf, (WIN_W - 12, 112, 12, WIN_H - 138),
                      (0, 0, 0, 46))
        self._bg = surf

    def _draw_house(self, surf, top):
        # 只露出顶栏下方的一段，作为背景层次
        pygame.draw.polygon(surf, (150, 70, 54), [
            (-50, 190), (64, 96), (188, 190)])
        pygame.draw.polygon(surf, (176, 88, 66), [
            (-50, 190), (64, 112), (188, 190)])
        pygame.draw.rect(surf, (232, 218, 190), (-50, 188, 240, 138))
        pygame.draw.rect(surf, (206, 188, 158), (-50, 188, 240, 10))
        # 窗户
        win = pygame.Rect(18, 214, 72, 58)
        pygame.draw.rect(surf, (96, 132, 150), win)
        pygame.draw.rect(surf, (248, 238, 214), win, 4)
        pygame.draw.line(surf, (248, 238, 214), (win.centerx, win.y),
                         (win.centerx, win.bottom), 3)
        pygame.draw.line(surf, (248, 238, 214), (win.x, win.centery),
                         (win.right, win.centery), 3)
        # 门
        door = pygame.Rect(126, 236, 44, 90)
        pygame.draw.rect(surf, (132, 86, 58), door, border_radius=6)
        pygame.draw.circle(surf, (240, 200, 96),
                           (door.right - 9, door.centery), 3)

    def _draw_hedge(self, surf):
        rng = random.Random(77 + sum(ord(c) for c in self.world_id))
        for i in range(9):
            x = 1112 + (i % 3) * 54 + rng.randint(-10, 10)
            y = 150 + (i // 3) * 96 + rng.randint(-10, 10)
            r = rng.randint(28, 38)
            pygame.draw.circle(surf, (74, 118, 66), (x, y), r)
            pygame.draw.circle(surf, (92, 142, 78), (x - 6, y - 8), r - 8)
        # 右侧木栅栏：细木条 + 两道横梁，避免形成一根突兀的深色立柱
        for i in range(4):
            x = 1230 + i * 12
            top = 386 + (i % 3) * 3
            pygame.draw.rect(surf, (158, 116, 76), (x, top, 8, 300),
                             border_radius=2)
            pygame.draw.polygon(surf, (182, 138, 94), [
                (x, top), (x + 4, top - 8), (x + 8, top)])
        for y in (444, 552):
            pygame.draw.rect(surf, (146, 104, 66), (1224, y, 56, 8),
                             border_radius=2)
            pygame.draw.rect(surf, (182, 138, 94), (1224, y, 56, 3),
                             border_radius=2)

    # ------------------------------------------------------------ 种子卡
    def _draw_plant_icon(self, surf, rect, card):
        """优先使用真实 DragonBones 立绘缩略图，缺失时退回程序化图标。"""
        pdef = card.get("pdef")
        art = getattr(pdef, "art", None) if pdef is not None else None
        if art:
            try:
                thumb = self.app.assets.db_thumb(art, rect.w - 2, rect.h - 2, anim="Idle")
                if thumb:
                    surf.blit(thumb, thumb.get_rect(center=rect.center))
                    return
            except Exception:
                pass
            try:
                spr = self.app.assets.static_sprite(art, rect.h - 10)
                if spr is not None:
                    if spr.get_width() > rect.w - 2:
                        spr = pygame.transform.smoothscale(
                            spr, (rect.w - 2, max(1, int(spr.get_height() * (rect.w - 2) / spr.get_width()))))
                    surf.blit(spr, spr.get_rect(center=rect.center))
                    return
            except Exception:
                pass
        pid = str(card.get("plant_id", ""))
        cx, cy = rect.center
        r = 23
        pygame.draw.circle(surf, (44, 64, 40), (cx, cy), r + 2)
        pygame.draw.circle(surf, (72, 104, 60), (cx, cy - 2), r)
        pygame.draw.circle(surf, (92, 128, 74), (cx - 5, cy - 8), r - 7)

        stem = (70, 126, 54)
        leaf = (96, 164, 66)
        if pid == "sunflower":
            for i in range(10):
                ang = i * math.tau / 10
                px = cx + int(math.cos(ang) * 14)
                py = cy - 3 + int(math.sin(ang) * 14)
                pygame.draw.circle(surf, (250, 206, 76), (px, py), 7)
                pygame.draw.circle(surf, (255, 226, 120), (px - 1, py - 2), 4)
            pygame.draw.circle(surf, (126, 82, 40), (cx, cy - 3), 10)
            pygame.draw.circle(surf, (96, 60, 30), (cx, cy - 3), 10, 2)
            pygame.draw.circle(surf, (40, 30, 18), (cx - 3, cy - 6), 1)
            pygame.draw.circle(surf, (40, 30, 18), (cx + 3, cy - 6), 1)
            pygame.draw.line(surf, stem, (cx, cy + 12), (cx, cy + 24), 3)
            pygame.draw.ellipse(surf, leaf, (cx - 15, cy + 15, 13, 7))
        elif pid in ("wallnut", "tallnut"):
            pygame.draw.ellipse(surf, (188, 124, 62), (cx - 15, cy - 19, 30, 40))
            pygame.draw.ellipse(surf, (156, 96, 46), (cx - 15, cy - 19, 30, 40), 2)
            pygame.draw.ellipse(surf, (206, 146, 82), (cx - 8, cy - 14, 9, 16))
            pygame.draw.circle(surf, (44, 30, 18), (cx - 5, cy - 2), 2)
            pygame.draw.circle(surf, (44, 30, 18), (cx + 6, cy - 2), 2)
            pygame.draw.arc(surf, (90, 54, 28), (cx - 6, cy + 4, 12, 8), 0.2, 2.9, 2)
        elif pid in ("cherrybomb", "jalapeno", "iceberg"):
            c1, c2 = ((220, 58, 46), (176, 34, 32))
            if pid == "iceberg":
                c1, c2 = ((150, 220, 236), (86, 168, 206))
            pygame.draw.circle(surf, c1, (cx - 8, cy), 11)
            pygame.draw.circle(surf, c2, (cx + 8, cy - 3), 11)
            pygame.draw.circle(surf, (255, 255, 255), (cx - 11, cy - 4), 2)
            pygame.draw.circle(surf, (255, 255, 255), (cx + 5, cy - 7), 2)
            pygame.draw.line(surf, (74, 120, 52), (cx - 6, cy - 10), (cx, cy - 20), 2)
            pygame.draw.line(surf, (74, 120, 52), (cx + 6, cy - 11), (cx, cy - 20), 2)
        elif pid in ("potatomine", "potato"):
            pygame.draw.ellipse(surf, (170, 112, 58), (cx - 15, cy - 12, 30, 26))
            pygame.draw.circle(surf, (44, 30, 18), (cx - 6, cy - 3), 2)
            pygame.draw.circle(surf, (44, 30, 18), (cx + 6, cy - 3), 2)
            pygame.draw.arc(surf, (96, 60, 28), (cx - 7, cy + 2, 14, 8), 0.2, 2.9, 2)
            pygame.draw.circle(surf, (230, 180, 100), (cx + 8, cy - 9), 3)
        else:
            # 射手 / 投手 / 蘑菇 / 通用植物
            head = (78, 160, 62)
            if pid in ("snowpea",):
                head = (122, 206, 228)
            elif pid in ("peashooter", "repeater", "threepeater", "splitpea"):
                head = (92, 176, 64)
            elif pid in ("cabbagepult", "kernelpult", "melonpult"):
                head = (156, 190, 86)
            elif pid in ("puffshroom", "sunshroom", "fumeshroom"):
                head = (196, 178, 138)
            pygame.draw.circle(surf, head, (cx - 1, cy - 4), 15)
            pygame.draw.circle(surf, tuple(min(255, c + 26) for c in head),
                               (cx - 6, cy - 10), 8)
            if pid in ("peashooter", "repeater", "threepeater", "snowpea",
                       "splitpea"):
                pygame.draw.circle(surf, head, (cx + 15, cy - 4), 7)
                pygame.draw.rect(surf, head, (cx + 10, cy - 11, 12, 14),
                                 border_radius=5)
                pygame.draw.rect(surf, (38, 48, 30), (cx + 21, cy - 8, 5, 9),
                                 border_radius=2)
            pygame.draw.circle(surf, (248, 248, 236), (cx + 2, cy - 8), 4)
            pygame.draw.circle(surf, (34, 28, 20), (cx + 3, cy - 8), 2)
            pygame.draw.line(surf, stem, (cx - 2, cy + 11), (cx - 2, cy + 25), 3)
            pygame.draw.ellipse(surf, leaf, (cx - 16, cy + 15, 13, 7))
            pygame.draw.ellipse(surf, leaf, (cx + 3, cy + 17, 13, 7))

    def _draw_seed_bank(self, surf):
        """自绘种子卡：引擎的未就绪遮罩在 SRCALPHA 层会抹掉卡片内容。"""
        session = self.session
        cards = getattr(session, "cards", None)
        rects = getattr(session, "card_rects", None)
        if not cards or not rects:
            return
        name_font = self._font(12, True)
        cost_font = self._font(13, True)
        small = self._font(9, False)
        for i, card in enumerate(cards):
            if i >= len(rects):
                break
            rect = rects[i]
            ready = bool(card.get("affordable")) and float(
                card.get("cd_remain", 0.0)) <= 0.0
            selected = getattr(session, "selected_card", None) == i
            base = (99, 129, 72) if ready else (78, 82, 68)
            if selected:
                base = (128, 156, 82) if ready else (98, 100, 80)
            ui.draw_shadow(surf, rect, radius=8, alpha=42, offset=(0, 2))
            pygame.draw.rect(surf, base, rect, border_radius=8)
            pygame.draw.rect(surf, (232, 222, 190), rect, 1, border_radius=8)
            ui.alpha_rect(surf, (rect.x + 4, rect.y + 3, rect.w - 8, 24),
                          (255, 255, 255, 26), 6)
            if selected:
                pygame.draw.rect(surf, (255, 216, 104), rect.inflate(4, 4), 3,
                                 border_radius=9)
                pygame.draw.rect(surf, (255, 246, 208), rect, 2, border_radius=8)

            icon_rect = pygame.Rect(rect.x + 15, rect.y + 5, 46, 44)
            self._draw_plant_icon(surf, icon_rect, card)
            name = ui.fit_text(name_font, str(card.get("name", "")), rect.w - 8)
            ui.text(surf, name_font, name, (rect.centerx, rect.y + 51),
                    (248, 246, 226), anchor="midtop", shadow=(24, 20, 12),
                    shadow_offset=(1, 1))
            cost = int(card.get("cost", 0) or 0)
            ui.draw_sun(surf, (rect.centerx - 16, rect.y + 76), 6, True)
            ui.text(surf, cost_font, str(cost), (rect.centerx + 4, rect.y + 75),
                    (255, 242, 176) if ready else (246, 188, 150),
                    anchor="midleft", shadow=(30, 22, 12),
                    shadow_offset=(1, 1))

            cd = float(card.get("cd_remain", 0.0) or 0.0)
            if cd > 0.05:
                ratio = max(0.0, min(1.0, cd / max(0.01, float(card.get("cd", 1.0)))))
                cover_h = int(rect.h * ratio)
                ui.alpha_rect(surf, (rect.x, rect.y, rect.w, cover_h),
                              (12, 14, 12, 150), 8)
                ui.text(surf, small, f"{cd:.1f}s",
                        (rect.centerx, rect.y + 32), (255, 255, 255),
                        anchor="center", shadow=(10, 10, 8))
            if not ready:
                ui.alpha_rect(surf, rect, (10, 12, 10, 70), 8)

    # ------------------------------------------------------------ 背景 HUD 附加
    def _draw_extras(self, surf):
        # 关卡标签（放进顶栏空白处，避免与 0 行僵尸出没区域重叠）
        chip = pygame.Rect(318, 16, 470, 26)
        ui.alpha_rect(surf, chip, (24, 20, 15, 150), 8)
        label = (self.level_title if self.world_name and self.world_name in self.level_title
                 else f"{self.world_name} · {self.level_title}")
        f = self._font(14, True)
        ui.text(surf, f, ui.fit_text(f, label, chip.w - 20),
                (chip.right - 10, chip.centery), (250, 240, 214),
                anchor="midright", alpha=235)

        # 底部操作提示
        f_small = self._font(10, False)
        ui.text(surf, f_small, "ESC 暂停 · F 加速 · 1-9 选卡",
                (10, WIN_H - 13), (226, 214, 188), anchor="midleft",
                shadow=(20, 14, 8), alpha=210)

        if self.session is not None and self.session.status == "playing":
            self.btn_ff.draw(surf)
        if self.session is not None and self.session.status == "playing":
            self.btn_back.draw(surf)

    # ------------------------------------------------------------ 遮蔽层
    def _draw_pause(self, surf):
        ui.draw_dim(surf, None, 138)
        panel = pygame.Rect(400, 196, 480, 328)
        ui.draw_panel(surf, panel, fill=ui.CREAM, border=ui.BROWN_DARK,
                      radius=20, border_width=3, shadow=True)
        pygame.draw.rect(surf, ui.BROWN_DARK,
                         (panel.x, panel.y, panel.w, 58),
                         border_top_left_radius=20,
                         border_top_right_radius=20)
        ui.text(surf, self._font(28, True), "已暂停",
                (panel.centerx, panel.y + 29), (255, 246, 214),
                anchor="center")
        ui.text(surf, self._font(14, False),
                "阳光和僵尸都停下来了，休息一下再继续。",
                (panel.centerx, panel.y + 82), ui.INK_SOFT, anchor="center")
        ui.draw_sun(surf, (panel.centerx - 150, panel.y + 112), 13, True)
        ui.text(surf, self._font(12, False),
                f"当前阳光 {int(getattr(self.session, 'sun', 0))}",
                (panel.centerx - 130, panel.y + 112), ui.INK_SOFT,
                anchor="midleft")
        self.btn_resume.draw(surf)
        self.btn_pause_map.draw(surf)
        self.btn_pause_replay.draw(surf)
        ui.text(surf, self._font(10, False), "ESC 继续 · 进度已自动保存",
                (panel.centerx, panel.bottom - 18), ui.INK_FAINT,
                anchor="center")

    def _draw_result(self, surf):
        session = self.session
        won = getattr(session, "status", "") == "won"
        ui.draw_dim(surf, None, 168)
        panel = pygame.Rect(320, 168, 640, 384)
        ui.draw_panel(surf, panel, fill=ui.CREAM, border=ui.BROWN_DARK,
                      radius=22, border_width=3, shadow=True)
        accent = ui.GREEN_DARK if won else ui.RED_DARK
        pygame.draw.rect(surf, accent,
                         (panel.x, panel.y, panel.w, 8),
                         border_top_left_radius=22,
                         border_top_right_radius=22)
        ui.text(surf, self._font(11, True),
                "VICTORY" if won else "GAME OVER",
                (panel.centerx, panel.y + 38), accent, anchor="center")
        ui.text(surf, self._font(40, True),
                "关卡胜利！" if won else "挑战失败",
                (panel.centerx, panel.y + 76),
                ui.GOLD if won else ui.RED, anchor="center",
                shadow=(60, 34, 18))
        sub = ("世界又安全了一天，继续前往下一片草坪吧。"
               if won else "僵尸吃掉了你的脑子……再试一次吧！")
        ui.text(surf, self._font(14, False), sub,
                (panel.centerx, panel.y + 120), ui.INK_SOFT,
                anchor="center")

        stats = pygame.Rect(panel.x + 40, panel.y + 148,
                            panel.w - 80, 68)
        pygame.draw.rect(surf, (238, 230, 214), stats, border_radius=12)
        pygame.draw.rect(surf, (210, 196, 172), stats, 1, border_radius=12)
        f = self._font(14, True)
        wave = int(getattr(session, "wave_index", 0))
        total = int(getattr(session, "total_waves", 0))
        killed = int(getattr(session, "zombie_killed", 0))
        sun = int(getattr(session, "sun_collected", 0))
        parts = [f"波次 {wave}/{total}", f"消灭僵尸 {killed}",
                 f"收集阳光 {sun}"]
        ui.text(surf, f, "    ·    ".join(parts),
                (stats.centerx, stats.y + 22), ui.INK, anchor="center")
        prog = wave / total if total > 0 else (1.0 if won else 0.0)
        bar = pygame.Rect(stats.x + 18, stats.bottom - 18, stats.w - 36, 8)
        pygame.draw.rect(surf, (198, 186, 164), bar, border_radius=4)
        fill = pygame.Rect(bar.x, bar.y, int(bar.w * max(0.0, min(1.0, prog))),
                           bar.h)
        pygame.draw.rect(surf, accent, fill, border_radius=4)

        # 星章与奖励
        stars = list(self.earned_stars or [False, False, False])
        for i, ok in enumerate(stars[:3]):
            cx = panel.centerx - 62 + i * 62
            cy = panel.y + 232
            color = ui.GOLD if ok else (198, 186, 166)
            ui.star(surf, (cx, cy), 13, color) if hasattr(ui, "star") else \
                pygame.draw.polygon(surf, color, [
                    (cx, cy - 13), (cx + 4, cy - 4), (cx + 13, cy - 3),
                    (cx + 6, cy + 3), (cx + 8, cy + 12), (cx, cy + 7),
                    (cx - 8, cy + 12), (cx - 6, cy + 3), (cx - 13, cy - 3),
                    (cx - 4, cy - 4)])
        if self.reward_coins:
            ui.text(surf, self._font(12, True), f"+{self.reward_coins} 金币",
                    (panel.centerx, panel.y + 258), ui.BROWN,
                    anchor="center")
        self.btn_result_map.draw(surf)
        self.btn_result_replay.draw(surf)
        ui.text(surf, self._font(10, False),
                (self.level_title if self.world_name and self.world_name in self.level_title
                 else f"{self.world_name} · {self.level_title}"),
                (panel.centerx, panel.bottom - 16), ui.INK_FAINT,
                anchor="center")

    # ------------------------------------------------------------ 占位战场
    def _draw_placeholder(self, surf):
        # 网格
        for row in range(BOARD_ROWS + 1):
            y = BOARD_Y + row * CELL_H
            pygame.draw.line(surf, (255, 255, 255), (BOARD_X, y),
                             (BOARD_X + BOARD_W, y), 1)
        for col in range(BOARD_COLS + 1):
            x = BOARD_X + col * CELL_W
            pygame.draw.line(surf, (255, 255, 255), (x, BOARD_Y),
                             (x, BOARD_Y + BOARD_H), 1)

        # 顶栏阳光
        pygame.draw.rect(surf, (32, 40, 30), (12, 10, 96, 66),
                         border_radius=10)
        pygame.draw.rect(surf, (210, 200, 150), (12, 10, 96, 66), 2,
                         border_radius=10)
        ui.draw_sun(surf, (40, 43), 16, True)
        ui.text(surf, self._font(24, True), "250", (62, 28),
                (255, 248, 210))

        # 六张占位卡
        fake = [("向日葵", 50), ("豌豆射手", 100), ("坚果墙", 50),
                ("寒冰射手", 175), ("樱桃炸弹", 150), ("双发射手", 200)]
        for i, (name, cost) in enumerate(fake):
            rect = pygame.Rect(CARDS_X + i * (CARD_W + CARD_GAP),
                               CARDS_Y, CARD_W, CARD_H)
            pygame.draw.rect(surf, (58, 60, 54), rect, border_radius=7)
            pygame.draw.rect(surf, (150, 150, 120), rect, 1, border_radius=7)
            pygame.draw.rect(surf, (110, 150, 90),
                             (rect.x + 12, rect.y + 6, 52, 52),
                             border_radius=5)
            ui.text(surf, self._font(18, True), "?",
                    (rect.centerx, rect.y + 32), (240, 245, 230),
                    anchor="center")
            f = self._font(11, True)
            ui.text(surf, f, ui.fit_text(f, name, CARD_W - 6),
                    (rect.centerx, rect.y + 68), (235, 235, 215),
                    anchor="center")
            ui.text(surf, self._font(14, True), str(cost),
                    (rect.centerx, rect.y + 85), (255, 240, 170),
                    anchor="center")

        panel = pygame.Rect(330, 236, 620, 268)
        ui.draw_panel(surf, panel, fill=ui.CREAM, border=ui.BROWN_DARK,
                      radius=18, border_width=3)
        ui.text(surf, self._font(26, True), "战斗准备中",
                (panel.centerx, panel.y + 34), ui.BROWN_DARK,
                anchor="center")
        msg = ("战斗引擎尚未就绪，这里显示静态战场。\n"
               "可以重新加载，或先返回地图查看其他界面。")
        if self.error:
            msg += "\n\n" + str(self.error)
        f = self._font(13, False)
        ui.draw_wrapped(surf, f, msg,
                        (panel.x + 28, panel.y + 70,
                         panel.w - 56, panel.h - 186),
                        ui.INK_SOFT, line_height=21, max_lines=4,
                        align="center")
        ui.text(surf, self._font(10, False),
                "提示：关卡数据来自 content/levels/，战斗逻辑来自 game/engine/",
                (panel.centerx, panel.bottom - 22), ui.INK_FAINT,
                anchor="center")

    # ------------------------------------------------------------ 绘制
    def draw(self, surf):
        if self._bg is None:
            self._build_background()
        surf.blit(self._bg, (0, 0))

        if self.session is None:
            self._draw_placeholder(surf)
        else:
            try:
                self.session.draw(surf)
                self._draw_seed_bank(surf)
            except Exception as exc:
                self.error = f"战斗绘制异常：{exc}"
                self.session = None
                self._draw_placeholder(surf)

        if self.session is not None:
            if self.night:
                veil = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
                veil.fill((18, 24, 64, 58))
                surf.blit(veil, (0, 0))
            self._draw_extras(surf)
            if self.session.paused and self.session.status == "playing":
                self._draw_pause(surf)
            elif self.session.status != "playing":
                self._draw_result(surf)
        else:
            self.btn_back.draw(surf)
            self.btn_retry.draw(surf)

        self.toast.draw(surf, pos=(WIN_W // 2, 646))
        self.draw_fade(surf)


__all__ = ["LevelScreen"]
