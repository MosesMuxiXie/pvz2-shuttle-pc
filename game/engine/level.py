"""关卡会话：把植物、僵尸、阳光、波次、卡片、胜负串成完整一局。

本模块只依赖 pygame 与引擎内部模块；app 仅用于取 assets / data / font，
因此可以在无窗口（SDL_VIDEODRIVER=dummy）环境下直接构造与跑局。

UI 约定：
- 鼠标点击交给 ``handle_mouse_down(pos)``；``handle_event(event)`` 也会转发鼠标事件，
  内部对同一位置的重复点击做了 50ms 去重，两种调用方式都安全。
- 画面：``draw(surf)`` 画草坪 + 实体 + HUD；想自己画 HUD 的界面可以分别调用
  ``draw_world(surf)`` / ``draw_hud(surf)``。
"""
from __future__ import annotations

import math
import random

import pygame

from ..config import (BOARD_COLS, BOARD_ROWS, BOARD_X, BOARD_Y, CELL_H,
                      CELL_W, WIN_H, WIN_W)
from . import combat
from . import elements
from .board import (BOARD_H, BOARD_W, Board, board_height,
                    board_width, get_geometry, row_ground_y, set_geometry)
from .entities import (FloatingText, LawnMower, Particle, Plant, Projectile,
                       Sun, Zombie)
from .waves import WaveDirector

# 失败线：僵尸走到这里且该行小推车已用掉 -> 失败
LOSE_X = 120.0
CARD_W, CARD_H, CARD_GAP = 76, 96, 6
CARDS_X, CARDS_Y = 118, 8


class LevelSession:
    """一局游戏。

    参数
    ----
    app        宿主对象，需要 ``assets``，可选 ``data`` / ``font()``
    world_def  WorldDef（可 None）
    level_def  LevelDef
    on_finish  结束回调 ``on_finish(won: bool)``，只会被调用一次
    """

    def __init__(self, app, world_def, level_def, on_finish=None):
        self.app = app
        self.world_def = world_def
        self.level_def = level_def
        self.on_finish = on_finish
        self.assets = getattr(app, "assets", None)
        self.data = getattr(app, "data", None)
        self.rng = random.Random()
        # 每关可覆盖草坪行列数（如 6 行 x 10 列的特殊战场）
        _extra = getattr(level_def, "extra", {}) or {}
        try:
            _rows = int(_extra.get("board_rows", BOARD_ROWS) or BOARD_ROWS)
        except (TypeError, ValueError):
            _rows = BOARD_ROWS
        try:
            _cols = int(_extra.get("board_cols", BOARD_COLS) or BOARD_COLS)
        except (TypeError, ValueError):
            _cols = BOARD_COLS
        _rows = max(1, min(8, _rows))
        _cols = max(1, min(12, _cols))
        _g = get_geometry()
        set_geometry(rows=_rows, cols=_cols, x=_g["x"], y=_g["y"],
                     w=_g["w"], h=_g["h"])
        self.rows = _rows
        self.cols = _cols
        _gg = get_geometry()
        self.cell_w = _gg["cw"]
        self.cell_h = _gg["ch"]
        self.board = Board(_rows, _cols)

        # ------------------------------------------------------ 核心状态
        self.sun = int(getattr(level_def, "sun", 250) or 0)
        settings = getattr(getattr(app, "save", None), "settings", {}) or {}
        try:
            self.sun += int(settings.get("sun_start_bonus", 0) or 0)
        except Exception:
            pass
        self.status = "playing"          # playing / won / lost
        self.time = 0.0
        self.selected_card: int | None = None
        self.message = ""
        self.message_timer = 0.0
        self.banner_text = ""
        self.banner_timer = 0.0
        self.paused = False
        self.shovel_mode = False
        self.shake = 0.0
        self.mouse_pos = (0, 0)

        self.plants: list[Plant] = []
        self.zombies: list[Zombie] = []
        self.projectiles: list[Projectile] = []
        self.suns: list[Sun] = []
        self.effects: list = []          # FloatingText / Particle
        self.mowers: list[LawnMower] = [LawnMower(r) for r in range(self.rows)]

        # 矿车（可选特殊战场）：extra.minecarts 为真/列表；每辆车点击后沿行冲出
        self.minecarts: list[dict] = []
        _mc = _extra.get("minecarts")
        if _mc:
            if isinstance(_mc, (list, tuple)):
                _mc_rows = [int(r) for r in _mc]
            else:
                _mc_rows = [r for r in (0, 2, 4) if r < self.rows]
            _g0 = get_geometry()
            for _r in _mc_rows:
                if 0 <= _r < self.rows:
                    self.minecarts.append({
                        "row": _r, "x": float(_g0["x"] - 58),
                        "cooldown": 0.0, "active": True, "moving": False, "returning": False,
                    })
            if self.minecarts:
                _cart_rows = {c["row"] for c in self.minecarts}
                self.mowers = [m for m in self.mowers if getattr(m, "row", -1) not in _cart_rows]

        self.wave_index = 0
        self.director = WaveDirector(level_def, self.rng, self.rows)
        self.total_waves = self.director.total_waves

        # ------------------------------------------------------ 统计
        self.zombies_spawned = 0
        self.zombie_killed = 0
        self.plants_planted = 0
        self.shots_fired = 0
        self.sun_collected = 0
        # ------------------------------------------------------ 养料 / 星章统计
        self.plantfood = 0
        try:
            self.plantfood = min(3, int(getattr(app.save, "plantfood", 0) or 0))
        except Exception:
            self.plantfood = 0
        self.plantfood_mode = False
        self.plantfood_items: list[PlantFood] = []
        self.mowers_used = 0
        self.plants_lost = 0
        self.max_plants = 0
        self.sun_spent = 0
        self.sun_earned = 0

        # ------------------------------------------------------ 天空阳光
        extra = getattr(level_def, "extra", {}) or {}
        try:
            self.sky_sun_interval = float(extra.get("sky_sun_interval", 8.0) or 8.0)
        except (TypeError, ValueError):
            self.sky_sun_interval = 8.0
        self.sky_sun_interval = max(2.0, self.sky_sun_interval)
        try:
            self.sky_sun_timer = float(extra.get("first_sun", 4.5) or 4.5)
        except (TypeError, ValueError):
            self.sky_sun_timer = 4.5

        # ------------------------------------------------------ 卡片
        self.cards: list[dict] = []
        self._build_cards(getattr(level_def, "deck", []) or [])
        self.card_rects = [
            pygame.Rect(CARDS_X + i * (CARD_W + CARD_GAP), CARDS_Y, CARD_W, CARD_H)
            for i in range(len(self.cards))
        ]
        cards_end = CARDS_X + len(self.cards) * (CARD_W + CARD_GAP)
        self.shovel_rect = pygame.Rect(max(cards_end + 10, 1040), 22, 62, 62)
        self.pause_rect = pygame.Rect(self.shovel_rect.right + 10, 22, 62, 62)
        self.plantfood_rect = pygame.Rect(14, 78, 58, 58)

        # ------------------------------------------------------ 内部
        self._finished_called = False
        self._last_click: tuple[tuple[int, int], float] | None = None
        self._last_started_wave = 0
        self._flag_announced = 0
        self._final_announced = False
        self._fonts: dict[tuple[int, bool], pygame.font.Font] = {}
        self._grid_surf: pygame.Surface | None = None
        self._world_layer: pygame.Surface | None = None
        self._card_icon_cache: dict[str, pygame.Surface | None] = {}

        self._prepare_card_extras()
        self.show_message("点击卡片选中，再点击草坪种植；记得收集阳光！", 3.5)

    # ================================================================ 构建
    def _build_cards(self, deck):
        for pid in deck:
            pdef = None
            if self.data is not None:
                plants = getattr(self.data, "plants", {}) or {}
                pdef = plants.get(pid)
            if pdef is None:      # 数据里没有该植物 -> 跳过
                continue
            try:
                cost = int(getattr(pdef, "cost", 100) or 0)
            except (TypeError, ValueError):
                cost = 100
            try:
                cd = float(getattr(pdef, "cooldown", 5.0) or 0.0)
            except (TypeError, ValueError):
                cd = 5.0
            self.cards.append({
                "plant_id": pid,
                "pdef": pdef,
                "name": str(getattr(pdef, "name_zh", "") or pid),
                "cost": cost,
                "cd": max(0.0, cd),
                "cd_remain": 0.0,
                "affordable": cost <= self.sun,
                "locked": False,
            })

    def _prepare_card_extras(self):
        """预渲染卡片名字/价格，避免每帧 render。"""
        for card in self.cards:
            try:
                self._ensure_card_surfs(card)
            except Exception:
                card["name_surf"] = None
                card["cost_surf"] = None

    # ================================================================ 基础工具
    def _font(self, size: int, bold: bool = False):
        key = (int(size), bool(bold))
        f = self._fonts.get(key)
        if f is not None:
            return f
        f = None
        for getter in (getattr(self.app, "font", None),
                       getattr(self.assets, "font", None) if self.assets else None):
            if callable(getter):
                try:
                    f = getter(size, bold)
                    if f is not None:
                        break
                except Exception:
                    f = None
        if f is None:
            try:
                f = pygame.font.Font(None, int(size))
            except Exception:
                f = None
        self._fonts[key] = f
        return f

    def _card_icon(self, card) -> pygame.Surface | None:
        """卡片图标；优先用 DragonBones 模型渲染，缺失时退回图片/色块。"""
        pid = str(card.get("plant_id", ""))
        if pid in self._card_icon_cache:
            return self._card_icon_cache[pid]
        surf = None
        if self.assets is not None:
            pdef = card.get("pdef")
            art = str(getattr(pdef, "art", "") or "") if pdef is not None else ""
            if art:
                try:
                    surf = self.assets.db_thumb(art, 52, 58)
                except Exception:
                    surf = None
            if surf is None:
                keys = []
                if pdef is not None:
                    for k in (getattr(pdef, "art", ""), getattr(pdef, "id", "")):
                        if k:
                            keys.append(str(k))
                keys.append(pid)
                for key in keys:
                    try:
                        path = self.assets.resolve(key)
                        if not path.exists():
                            continue
                        img = self.assets.image(key)
                    except Exception:
                        img = None
                    if img is not None:
                        try:
                            surf = pygame.transform.smoothscale(img, (52, 52))
                        except Exception:
                            surf = img
                        break
        self._card_icon_cache[pid] = surf
        return surf

    def _ensure_card_surfs(self, card):
        if "name_surf" in card:
            return
        f_name = self._font(15, True)
        f_cost = self._font(17, True)
        name = str(card.get("name", ""))
        if len(name) > 5:
            name = name[:5]
        card["name_surf"] = f_name.render(name, True, (245, 245, 225)) if f_name else None
        card["cost_surf"] = f_cost.render(str(card["cost"]), True, (255, 240, 170)) if f_cost else None

    def _end(self, won: bool):
        if self.status != "playing":
            return
        self.status = "won" if won else "lost"
        self.selected_card = None
        self.shovel_mode = False
        self.banner_text = "关卡胜利！" if won else "僵尸吃掉了你的脑子！"
        self.banner_timer = 3.5
        self.show_message("", 0.0)
        if not self._finished_called:
            self._finished_called = True
            cb = self.on_finish
            if callable(cb):
                try:
                    cb(bool(won))
                except Exception:
                    pass

    # ================================================================ 消息/特效
    def _sfx(self, name: str, volume: float = 0.5):
        try:
            audio = getattr(self.app, "audio", None)
            if audio is not None:
                audio.sound(name, volume)
        except Exception:
            pass

    def show_message(self, text: str, duration: float = 1.6):
        self.message = str(text)
        self.message_timer = float(duration)

    def start_wave_banner(self, text: str | None = None, duration: float = 2.6):
        self.banner_text = str(text or f"第 {max(1, self.wave_index)} 波")
        self.banner_timer = float(duration)
        self._sfx("sfx_wave.wav", 0.28)

    def spawn_text(self, x, y, text, color=(255, 255, 255), size=18):
        self.effects.append(FloatingText(x, y, text, color=color, size=size))

    def spawn_burst(self, x, y, color=(255, 220, 120), count: int = 8, speed: float = 130.0):
        for _ in range(max(0, int(count))):
            a = self.rng.uniform(0.0, math.tau)
            v = self.rng.uniform(speed * 0.35, speed)
            self.effects.append(Particle(
                x, y, math.cos(a) * v, math.sin(a) * v,
                color=color, life=self.rng.uniform(0.25, 0.6),
                radius=self.rng.randint(2, 5)))

    def spawn_sun(self, x, y, target_y=None, value: int = 25, kind: str = "sky"):
        sun = Sun(x, y, target_y, value=value, assets=self.assets, kind=kind)
        self.suns.append(sun)
        return sun

    # ================================================================ 战斗接口（实体回调）
    def spawn_projectile(self, plant, row=None, kind: str = "pea"):
        r = plant.row if row is None else int(row)
        try:
            elem = elements.element_of_plant(getattr(plant, "pdef", None))
        except Exception:
            elem = None
        p = Projectile(kind, x=float(plant.x) + 20.0,
                       y=float(plant.ground_y) - 62.0, row=r,
                       damage=float(getattr(plant, "damage", 20.0)),
                       assets=self.assets, plant=plant,
                       pierce=bool(getattr(plant, "pierce", False)),
                       splash=float(getattr(plant, "splash", 0.0) or 0.0),
                       slow=float(getattr(plant, "slow", 0.0) or 0.0),
                       element=elem)
        self.projectiles.append(p)
        self.shots_fired += 1
        if self.shots_fired % 3 == 1:
            self._sfx("sfx_shoot.wav", 0.18)
        return p

    def area_damage(self, x: float, y: float, radius: float, damage: float,
                    slow: float = 0.0, pierce_armor: bool = False,
                    exclude: set | None = None):
        return combat.splash_damage(self, x, y, radius, damage,
                                    slow=slow, pierce_armor=pierce_armor,
                                    exclude=exclude)

    def nearest_zombie(self, row: int, x_min=None, x_max=None):
        return combat.nearest_zombie_in_row(self, int(row), x_min, x_max)

    def has_zombie_in_row(self, row: int, x_min=None, x_max=None) -> bool:
        return combat.has_zombie_in_row(self, int(row), x_min, x_max)

    def zombies_in_row(self, row: int, x_min=None, x_max=None):
        return combat.zombies_in_row(self, int(row), x_min, x_max)

    def on_zombie_killed(self, zombie):
        self.zombie_killed += 1
        self._sfx("sfx_die.wav", 0.3)
        try:
            self.spawn_burst(zombie.x, zombie.ground_y - 60,
                             (200, 200, 210), 6, 90)
        except Exception:
            pass
        # 养料掉落（最多同时在场上 2 个）
        try:
            if self.plantfood < 3 and self.rng.random() < 0.14 \
                    and len(self.plantfood_items) < 2:
                if self.plantfood + len(self.plantfood_items) < 5:
                    self.plantfood_items.append(
                        PlantFood(zombie.x, zombie.ground_y - 40))
        except Exception:
            pass

    def on_armor_broken(self, zombie, tier):
        try:
            self.spawn_text(zombie.x, zombie.ground_y - 110,
                            "护甲破碎", (220, 210, 240), 15)
            self.spawn_burst(zombie.x, zombie.ground_y - 70,
                             (190, 180, 210), 7, 110)
        except Exception:
            pass

    def on_plant_killed(self, plant):
        self.plants_lost += 1
        try:
            self.spawn_burst(plant.x, plant.ground_y - 30,
                             (110, 180, 90), 6, 80)
        except Exception:
            pass

    # ================================================================ 卡片/铲子
    def card_at(self, pos):
        for i, r in enumerate(self.card_rects):
            if r.collidepoint(pos):
                return i
        return None

    def select_card(self, i: int) -> bool:
        if self.status != "playing" or self.paused:
            return False
        if not (0 <= int(i) < len(self.cards)):
            return False
        i = int(i)
        card = self.cards[i]
        if card.get("locked"):
            self.show_message("该卡片尚未解锁")
            self._sfx("sfx_error.wav", 0.35)
            return False
        if card["cd_remain"] > 0.01:
            self.show_message("卡片冷却中…")
            self._sfx("sfx_error.wav", 0.3)
            return False
        self.shovel_mode = False
        self.selected_card = None if self.selected_card == i else i
        self._sfx("sfx_click.wav", 0.35)
        return True

    def toggle_shovel(self) -> bool:
        if self.status != "playing" or self.paused:
            return False
        self.shovel_mode = not self.shovel_mode
        self.selected_card = None
        self.show_message("铲子：点击植物铲除" if self.shovel_mode else "")
        return True

    def toggle_pause(self) -> bool:
        if self.status != "playing":
            return False
        self.paused = not self.paused
        return True

    def try_plant(self, row: int, col: int) -> bool:
        if self.status != "playing" or self.paused:
            return False
        if self.selected_card is None:
            return False
        if not self.board.in_bounds(row, col):
            return False
        i = self.selected_card
        if not (0 <= i < len(self.cards)):
            return False
        card = self.cards[i]
        if card.get("locked"):
            self.show_message("该卡片尚未解锁")
            return False
        if card["cd_remain"] > 0.01:
            self.show_message("卡片冷却中…")
            return False
        cost = int(card["cost"])
        if self.sun < cost:
            self.show_message("阳光不足！")
            self._sfx("sfx_error.wav", 0.3)
            return False
        if self.board.plant_at(row, col) is not None:
            self.show_message("这里已经有植物了")
            return False
        pdef = card.get("pdef")
        if pdef is None:
            return False
        plant = Plant(pdef, row, col, self.assets)
        self.board.set_plant(row, col, plant)
        self.plants.append(plant)
        self.plants_planted += 1
        self.sun = max(0, self.sun - cost)
        self.sun_spent += cost
        self.max_plants = max(self.max_plants, len(self.plants))
        card["cd_remain"] = card["cd"]
        card["affordable"] = self.sun >= cost
        self.selected_card = None
        self.spawn_text(plant.x, plant.ground_y - 80, f"-{cost}", (255, 235, 140), 17)
        self._sfx("sfx_plant.wav", 0.45)
        return True

    def try_shovel(self, row: int, col: int) -> bool:
        if self.status != "playing" or self.paused:
            return False
        plant = self.board.plant_at(row, col)
        if plant is None:
            self.show_message("这里没有植物")
            return False
        self.board.clear(row, col)
        try:
            plant.alive = False
            plant.hp = 0.0
        except Exception:
            pass
        if plant in self.plants:
            self.plants.remove(plant)
        self.spawn_burst(plant.x, plant.ground_y - 30, (120, 190, 100), 8, 90)
        self.spawn_text(plant.x, plant.ground_y - 70, "已铲除", (220, 240, 220), 16)
        self._sfx("sfx_shovel.wav", 0.45)
        return True

    # ================================================================ 养料
    def apply_plantfood(self, plant) -> bool:
        if self.plantfood <= 0 or plant is None or not getattr(plant, "alive", False):
            return False
        self.plantfood -= 1
        self.plantfood_mode = False
        self._sfx("sfx_sun.wav", 0.45)
        self.spawn_burst(plant.x, plant.ground_y - 44, (140, 240, 255), 14, 130)
        self.spawn_text(plant.x, plant.ground_y - 96, "养料!", (150, 240, 255), 20)
        behavior = str(getattr(plant, "behavior", "shoot") or "shoot")
        if behavior == "produce":
            for _ in range(3):
                self.spawn_sun(plant.x, plant.ground_y - 50, plant.ground_y - 16, 25, "plant")
            plant.boost_t = 8.0
        elif behavior == "wall":
            bonus = int(getattr(plant, "max_hp", 600) * 0.5)
            plant.max_hp = int(getattr(plant, "max_hp", 600)) + bonus
            plant.hp = float(plant.max_hp)
        elif behavior == "instant":
            plant.fuse_timer = 0.05
        elif behavior == "mine":
            plant.mine_armed = True
            plant.mine_timer = 99.0
        else:
            plant.boost_t = 8.0
            rows = plant._target_rows(self) or [plant.row]
            kind = str(getattr(plant, "projectile", "pea") or "pea")
            if behavior == "lob":
                kind = "lob"
            elif behavior == "boomerang":
                kind = "boomerang"
            if kind not in ("pea", "lob", "boomerang"):
                kind = "pea"
            for r in rows:
                for _ in range(5):
                    self.spawn_projectile(plant, row=r, kind=kind)
        pname = getattr(getattr(plant, "pdef", None), "name_zh", "") or "植物"
        self.show_message(f"{pname} 获得了养料！", 1.8)
        return True

    # ================================================================ 阳光收集
    def collect_suns_at(self, pos) -> int:
        total = 0
        for sun in self.suns:
            if not getattr(sun, "collectible", False):
                continue
            if sun.rect.collidepoint(pos):
                sun.collected = True
                sun.alive = False
                total += int(sun.value)
                self.sun += int(sun.value)
                self.sun_collected += int(sun.value)
                self.sun_earned += int(sun.value)
                self.spawn_text(sun.x, sun.y - 20, f"+{int(sun.value)}",
                                (255, 240, 150), 18)
                self.spawn_burst(sun.x, sun.y, (255, 230, 120), 8, 120)
        if total:
            self._sfx("sfx_sun.wav", 0.4)
            self.suns = [s for s in self.suns if getattr(s, "collectible", False)]
        return total

    # ================================================================ 鼠标/键盘
    def handle_event(self, event) -> bool:
        """处理 pygame 事件；返回是否消费。鼠标点击会转发到 handle_mouse_down。"""
        et = getattr(event, "type", None)
        if et == pygame.KEYDOWN:
            key = getattr(event, "key", None)
            if key in (pygame.K_ESCAPE,):
                self.selected_card = None
                self.shovel_mode = False
                return True
            if key in (pygame.K_p, pygame.K_SPACE):
                self.toggle_pause()
                return True
            if key == pygame.K_s:
                self.toggle_shovel()
                return True
            if key is not None and pygame.K_1 <= key <= pygame.K_9:
                self.select_card(key - pygame.K_1)
                return True
            return False
        if et == pygame.MOUSEMOTION:
            self.mouse_pos = tuple(getattr(event, "pos", (0, 0)))
            return False
        if et == pygame.MOUSEBUTTONDOWN and getattr(event, "button", 1) == 1:
            self.handle_mouse_down(tuple(getattr(event, "pos", (0, 0))))
            return True
        return False

    def handle_mouse_down(self, pos) -> bool:
        pos = (int(pos[0]), int(pos[1]))
        self.mouse_pos = pos
        # 同一帧内 handle_event 与直接调用都会进来，做 50ms 去重
        if self._last_click is not None:
            last_pos, last_t = self._last_click
            if last_pos == pos and abs(self.time - last_t) < 0.05:
                return True
        self._last_click = (pos, self.time)

        if self.status != "playing":
            return True
        if self.pause_rect.collidepoint(pos):
            self.toggle_pause()
            return True
        if self.paused:
            return True
        if self.shovel_rect.collidepoint(pos):
            self.toggle_shovel()
            return True

        if self.plantfood_rect.collidepoint(pos):
            if self.plantfood > 0:
                self.plantfood_mode = not self.plantfood_mode
                self.show_message("选择一株植物使用养料" if self.plantfood_mode
                                  else "已取消养料", 1.6)
            else:
                self.show_message("没有养料：击杀僵尸有几率掉落", 1.8)
            return True
        if self.plantfood_mode:
            cell = self.board.cell_at(pos)
            if cell is not None:
                plant = self.board.plant_at(cell[0], cell[1])
                if plant is not None:
                    self.apply_plantfood(plant)
                    return True
            self.plantfood_mode = False
            self.show_message("已取消养料", 1.2)
            return True

        if self._click_minecart(pos):
            return True

        idx = self.card_at(pos)
        if idx is not None:
            self.select_card(idx)
            return True

        if self.collect_suns_at(pos):
            return True

        cell = self.board.cell_at(pos)
        if cell is None:
            return False
        row, col = cell
        if self.shovel_mode:
            self.try_shovel(row, col)
            return True
        if self.selected_card is not None:
            self.try_plant(row, col)
            return True
        return False

    # ================================================================ 更新
    def update(self, dt: float):
        if self.paused:
            return
        dt = max(0.0, float(dt))
        self.time += dt
        if self.message_timer > 0.0:
            self.message_timer = max(0.0, self.message_timer - dt)
            if self.message_timer <= 0.0:
                self.message = ""
        if self.banner_timer > 0.0:
            self.banner_timer = max(0.0, self.banner_timer - dt)
        self.shake = max(0.0, self.shake - dt * 28.0)

        if self.status != "playing":
            # 结束后冻结沙盘，只让文字/粒子播完
            for e in list(self.effects):
                e.update(dt)
            self.effects = [e for e in self.effects if getattr(e, "alive", False)]
            return

        self._update_cards(dt)
        self._update_sky_sun(dt)
        self._update_waves(dt)

        for p in list(self.plants):
            p.update(dt, self)
        for z in list(self.zombies):
            z.update(dt, self)
        for pr in list(self.projectiles):
            pr.update(dt, self)
        for sun in list(self.suns):
            sun.update(dt)
        for m in self.mowers:
            if not m.used:
                before = getattr(m, "used", False)
            m.update(dt, self)
        self._update_minecarts(dt)
        self.mowers_used = sum(1 for m in self.mowers if getattr(m, "used", False))
        for pf in list(self.plantfood_items):
            pf.update(dt)
        self.plantfood_items = [pf for pf in self.plantfood_items
                                if getattr(pf, "alive", True)]
        for e in list(self.effects):
            e.update(dt)

        self._cleanup()
        if self.status != "playing":
            return
        self._check_lose()
        if self.status == "playing":
            self._check_win()

    def _update_cards(self, dt: float):
        for card in self.cards:
            if card["cd_remain"] > 0.0:
                card["cd_remain"] = max(0.0, card["cd_remain"] - dt)
            card["affordable"] = (self.sun >= int(card["cost"])
                                  and card["cd_remain"] <= 0.0
                                  and not card.get("locked"))

    def _update_sky_sun(self, dt: float):
        self.sky_sun_timer -= dt
        if self.sky_sun_timer > 0.0:
            return
        self.sky_sun_timer = self.sky_sun_interval * self.rng.uniform(0.85, 1.2)
        _g = get_geometry()
        x = self.rng.uniform(_g["x"] + 50, _g["x"] + _g["w"] - 50)
        y = _g["y"] - 40
        target = self.rng.uniform(_g["y"] + 110, _g["y"] + _g["h"] - 80)
        self.spawn_sun(x, y, target, 25, "sky")

    def _update_waves(self, dt: float):
        director = self.director
        prev_wave = self.wave_index
        events = director.update(dt)
        self.wave_index = max(self.wave_index, director.wave_index)

        if director.wave_index > prev_wave:
            if director.final_wave_started and not self._final_announced:
                self._final_announced = True
                self.start_wave_banner("最终波！", 3.0)
                self.shake = max(self.shake, 4.0)
            elif director.flag_waves_started > self._flag_announced:
                self._flag_announced = director.flag_waves_started
                self.start_wave_banner("一大波僵尸来袭！", 2.6)
                self.shake = max(self.shake, 3.0)
            else:
                self.show_message(f"第 {self.wave_index} / {self.total_waves} 波", 1.5)

        for ev in events:
            self._spawn_zombie(ev)

    def _spawn_zombie(self, ev):
        zdef = None
        if self.data is not None:
            zdef = (getattr(self.data, "zombies", {}) or {}).get(ev.type)
        if zdef is None:              # 数据缺失：跳过，不让整局崩
            return
        x = float(WIN_W + 40 + self.rng.uniform(0, 90))
        z = Zombie(zdef, ev.row, x, self.assets,
                   armature=getattr(zdef, "armature", None))
        self.zombies.append(z)
        self.zombies_spawned += 1

    def _cleanup(self):
        board = self.board
        for p in self.plants:
            if not getattr(p, "alive", False):
                try:
                    if board.plant_at(p.row, p.col) is p:
                        board.clear(p.row, p.col)
                except Exception:
                    pass
        self.plants = [p for p in self.plants if getattr(p, "alive", False)]
        self.zombies = [z for z in self.zombies if getattr(z, "alive", False)]
        self.projectiles = [p for p in self.projectiles if getattr(p, "alive", False)]
        self.suns = [s for s in self.suns if getattr(s, "collectible", False)]
        self.effects = [e for e in self.effects if getattr(e, "alive", False)]

    def _check_lose(self):
        for z in self.zombies:
            if not getattr(z, "alive", False) or getattr(z, "state", "") == "die":
                continue
            if float(z.x) >= LOSE_X:
                continue
            mower = self.mower_at_row(z.row)
            if mower is None or mower.used:
                self._end(False)
                return

    def _check_win(self):
        if self.total_waves <= 0:
            return
        if not self.director.finished:
            return
        for z in self.zombies:
            if getattr(z, "alive", False) and getattr(z, "state", "") != "die":
                return
        self._end(True)

    def mower_at_row(self, row: int):
        for m in self.mowers:
            if m.row == row:
                return m
        return None

    # ================================================================ 绘制
    def _grid(self) -> pygame.Surface:
        if self._grid_surf is None:
            _g = get_geometry()
            _w = int(round(_g["w"])); _h = int(round(_g["h"]))
            surf = pygame.Surface((_w, _h), pygame.SRCALPHA)
            for r in range(1, self.rows):
                y = int(round(r * _g["ch"]))
                pygame.draw.line(surf, (255, 255, 255, 26), (0, y), (_w, y))
            for c in range(1, self.cols):
                x = int(round(c * _g["cw"]))
                pygame.draw.line(surf, (255, 255, 255, 22), (x, 0), (x, _h))
            pygame.draw.rect(surf, (255, 255, 255, 40),
                             pygame.Rect(0, 0, _w, _h), 2)
            self._grid_surf = surf
        return self._grid_surf

    def draw(self, surf):
        self.draw_world(surf)
        self.draw_hud(surf)

    def draw_world(self, surf):
        """草坪 + 实体（不含 HUD）。"""
        if self.shake > 0.5:
            if self._world_layer is None:
                self._world_layer = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            layer = self._world_layer
            layer.fill((0, 0, 0, 0))
            self._draw_world_to(layer)
            dx = int(self.rng.uniform(-self.shake, self.shake))
            dy = int(self.rng.uniform(-self.shake * 0.5, self.shake * 0.5))
            surf.blit(layer, (dx, dy))
        else:
            self._draw_world_to(surf)

    def _draw_world_to(self, surf):
        _g = get_geometry()
        surf.blit(self._grid(), (_g["x"], _g["y"]))

        # 选中卡片/铲子时高亮鼠标所在格
        if self.status == "playing" and not self.paused:
            cell = self.board.cell_at(self.mouse_pos)
            if cell is not None and (self.selected_card is not None or self.shovel_mode):
                r, c = cell
                color = (255, 120, 90) if self.shovel_mode else (255, 245, 150)
                rect = self.board.cell_rect(r, c)
                pygame.draw.rect(surf, color, rect, 3, border_radius=6)

        for m in self.mowers:
            m.draw(surf)
        self._draw_minecarts(surf)
        for p in self.plants:
            p.draw(surf)
        for z in self.zombies:
            z.draw(surf)
        for pr in self.projectiles:
            pr.draw(surf)
        for sun in self.suns:
            sun.draw(surf)
        for pf in self.plantfood_items:
            pf.draw(surf)
        if self.plantfood_mode:
            cell = self.board.cell_at(self.mouse_pos)
            if cell is not None:
                r, c = cell
                rect = self.board.cell_rect(r, c)
                pygame.draw.rect(surf, (120, 230, 255), rect, 3, border_radius=6)
        for e in self.effects:
            if isinstance(e, FloatingText):
                e.draw(surf, self._font(e.size))
            else:
                try:
                    e.draw(surf)
                except Exception:
                    pass

    def _draw_plantfood_button(self, surf):
        rect = self.plantfood_rect
        fill = (58, 84, 96) if self.plantfood else (58, 62, 66)
        pygame.draw.rect(surf, fill, rect, border_radius=12)
        edge = (140, 240, 255) if self.plantfood_mode else (200, 220, 200)
        pygame.draw.rect(surf, edge, rect, 3 if self.plantfood_mode else 2, border_radius=12)
        # 绿色叶片/营养符号
        cx, cy = rect.centerx, rect.centery - 6
        pygame.draw.circle(surf, (120, 220, 120), (cx, cy), 13)
        pygame.draw.circle(surf, (200, 255, 210), (cx - 4, cy - 5), 4)
        f = self._font(15, True)
        t = f.render(f"x{self.plantfood}", True, (255, 255, 235))
        surf.blit(t, (rect.centerx - t.get_width() // 2, rect.bottom - 22))
        f2 = self._font(11)
        t2 = f2.render("养料", True, (230, 240, 230))
        surf.blit(t2, (rect.centerx - t2.get_width() // 2, rect.top + 3))

    def draw_hud(self, surf):
        """阳光、卡片、铲子/暂停按钮、波次进度、提示文字。"""
        ui = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        self._draw_top_bar(ui)
        self._draw_plantfood_button(ui)
        self._draw_wave_bar(ui)
        self._draw_banner(ui)
        if self.paused:
            ui.fill((0, 0, 0, 120))
            f = self._font(46, True)
            if f:
                t = f.render("已暂停", True, (255, 255, 255))
                ui.blit(t, t.get_rect(center=(WIN_W // 2, WIN_H // 2)))
        surf.blit(ui, (0, 0))

    def _draw_top_bar(self, surf):
        # 阳光计数
        panel = pygame.Rect(12, 10, 96, 66)
        pygame.draw.rect(surf, (32, 40, 30, 225), panel, border_radius=10)
        pygame.draw.rect(surf, (210, 200, 150, 200), panel, 2, border_radius=10)
        cx, cy = 40, 43
        pygame.draw.circle(surf, (255, 225, 80), (cx, cy), 16)
        pygame.draw.circle(surf, (255, 248, 180), (cx - 4, cy - 4), 7)
        f_sun = self._font(24, True)
        if f_sun:
            t = f_sun.render(str(int(self.sun)), True, (255, 248, 210))
            surf.blit(t, (62, 28))

        # 卡片区背景
        if self.cards:
            bg = pygame.Rect(CARDS_X - 8, 4,
                             len(self.cards) * (CARD_W + CARD_GAP) + 4, 104)
            pygame.draw.rect(surf, (28, 34, 26, 215), bg, border_radius=10)

        for i, card in enumerate(self.cards):
            rect = self.card_rects[i]
            selected = (self.selected_card == i)
            ready = card["affordable"] and card["cd_remain"] <= 0.0
            bg_color = (78, 98, 64, 235) if ready else (58, 60, 54, 225)
            pygame.draw.rect(surf, bg_color, rect, border_radius=7)
            border = (255, 226, 120) if selected else (150, 150, 120)
            pygame.draw.rect(surf, border, rect, 3 if selected else 1, border_radius=7)

            icon = self._card_icon(card)
            icon_rect = pygame.Rect(rect.x + 12, rect.y + 6, 52, 52)
            if icon is not None:
                surf.blit(icon, icon_rect)
            else:
                pygame.draw.rect(surf, (110, 150, 90), icon_rect, border_radius=5)
                f0 = self._font(13, True)
                if f0:
                    t = f0.render(str(card["name"])[:3], True, (240, 245, 230))
                    surf.blit(t, t.get_rect(center=icon_rect.center))

            try:
                self._ensure_card_surfs(card)
            except Exception:
                pass
            if card.get("name_surf") is not None:
                surf.blit(card["name_surf"],
                          card["name_surf"].get_rect(center=(rect.centerx, rect.y + 68)))
            if card.get("cost_surf") is not None:
                surf.blit(card["cost_surf"],
                          card["cost_surf"].get_rect(center=(rect.centerx, rect.y + 85)))

            if card["cd_remain"] > 0.0 and card["cd"] > 0:
                ratio = min(1.0, card["cd_remain"] / max(0.001, card["cd"]))
                h = int(CARD_H * ratio)
                cover = pygame.Surface((CARD_W, h), pygame.SRCALPHA)
                cover.fill((10, 12, 10, 165))
                surf.blit(cover, (rect.x, rect.bottom - h))
            if not ready:
                pygame.draw.rect(surf, (20, 22, 18, 90), rect, border_radius=7)

        # 铲子
        sh = self.shovel_rect
        pygame.draw.rect(surf, (120, 90, 60, 230) if not self.shovel_mode
                         else (220, 180, 90, 240), sh, border_radius=9)
        pygame.draw.rect(surf, (240, 230, 200), sh, 2, border_radius=9)
        pygame.draw.polygon(surf, (210, 210, 220), [
            (sh.x + 20, sh.bottom - 14), (sh.x + 34, sh.bottom - 34),
            (sh.x + 42, sh.bottom - 26), (sh.x + 28, sh.bottom - 8)])
        pygame.draw.line(surf, (150, 100, 60), (sh.x + 34, sh.bottom - 34),
                         (sh.x + 44, sh.bottom - 44), 5)

        # 暂停
        pr = self.pause_rect
        pygame.draw.rect(surf, (40, 50, 60, 225), pr, border_radius=9)
        pygame.draw.rect(surf, (200, 210, 220), pr, 2, border_radius=9)
        if self.paused:
            pygame.draw.polygon(surf, (240, 240, 240), [
                (pr.centerx - 8, pr.centery - 12), (pr.centerx - 8, pr.centery + 12),
                (pr.centerx + 12, pr.centery)])
        else:
            pygame.draw.rect(surf, (240, 240, 240),
                             (pr.centerx - 11, pr.centery - 12, 7, 24))
            pygame.draw.rect(surf, (240, 240, 240),
                             (pr.centerx + 4, pr.centery - 12, 7, 24))

        # 波次文字（砸罐子等无波次模式可隐藏）
        if not getattr(self, "hide_wave_text", False):
            f_wave = self._font(15, True)
            if f_wave:
                t = f_wave.render(f"波次 {self.wave_index}/{self.total_waves}",
                                  True, (235, 235, 220))
                chip = pygame.Rect(WIN_W - 268, 46, 118, 30)
                bg = pygame.Surface((chip.w, chip.h), pygame.SRCALPHA)
                pygame.draw.rect(bg, (36, 40, 34, 190), bg.get_rect(), border_radius=10)
                surf.blit(bg, chip.topleft)
                pygame.draw.rect(surf, (150, 146, 120), chip, 1, border_radius=10)
                surf.blit(t, (chip.centerx - t.get_width() // 2,
                              chip.centery - t.get_height() // 2))

    # ---------------------------------------------------------------- 矿车
    def _cart_rect(self, cart) -> pygame.Rect:
        y = int(row_ground_y(cart["row"]) - 34)
        return pygame.Rect(int(cart["x"]) - 30, y, 60, 36)

    def _click_minecart(self, pos) -> bool:
        for cart in self.minecarts:
            if not cart["active"] or cart["cooldown"] > 0.0:
                continue
            if self._cart_rect(cart).inflate(8, 8).collidepoint(pos):
                cart["cooldown"] = 9.0
                cart["moving"] = True
                cart["x"] = float(get_geometry()["x"] + 18)
                self.show_message("矿车出发！", 1.0)
                return True
        return False

    def _update_minecarts(self, dt: float):
        if not self.minecarts:
            return
        g = get_geometry()
        for cart in self.minecarts:
            if cart["moving"]:
                cart["x"] += 760.0 * dt
                for z in list(self.zombies):
                    if not getattr(z, "alive", False) or int(z.row) != cart["row"]:
                        continue
                    if abs(float(z.x) - cart["x"]) < 46:
                        combat.damage_zombie(z, 99999.0, self, pierce_armor=True)
                        self.spawn_burst(z.x, z.ground_y - 40, (240, 210, 120), 10, 150)
                if cart["x"] > g["x"] + g["w"] + 40:
                    cart["moving"] = False
                    cart["x"] = float(g["x"] + 18)
            elif cart["cooldown"] > 0.0:
                cart["cooldown"] = max(0.0, cart["cooldown"] - dt)

    def _draw_minecarts(self, surf):
        import math as _m
        for cart in self.minecarts:
            r = self._cart_rect(cart)
            ready = cart["cooldown"] <= 0.0
            # 铁轨
            gy = int(row_ground_y(cart["row"]) - 2)
            pygame.draw.line(surf, (72, 62, 54), (r.x - 26, gy), (r.x + 250, gy), 2)
            for tx in range(r.x - 20, r.x + 250, 16):
                pygame.draw.line(surf, (52, 44, 38), (tx, gy - 3), (tx + 8, gy + 3), 2)
            # 车体（梯形）+ 金色饰条
            pts = [(r.x, r.y + 8), (r.right, r.y + 8), (r.right - 6, r.bottom - 4), (r.x + 6, r.bottom - 4)]
            body = (188, 92, 58) if ready else (118, 104, 94)
            pygame.draw.polygon(surf, body, pts)
            pygame.draw.polygon(surf, (64, 40, 28), pts, 2)
            inner = pygame.Rect(r.x + 8, r.y + 12, r.w - 16, r.h - 20)
            pygame.draw.rect(surf, (54, 60, 66), inner, border_radius=3)
            pygame.draw.rect(surf, (212, 176, 92), inner, 1, border_radius=3)
            # 矿石
            for k in range(3):
                cx = inner.x + 8 + k * (inner.w - 16) // 2
                pygame.draw.circle(surf, (120, 190, 220), (cx, inner.y + 7), 3)
            # 车轮 + 辐条
            for wx in (r.x + 14, r.right - 14):
                wy = r.bottom - 2
                pygame.draw.circle(surf, (32, 32, 36), (wx, wy), 8)
                pygame.draw.circle(surf, (148, 148, 140), (wx, wy), 5)
                pygame.draw.circle(surf, (32, 32, 36), (wx, wy), 2)
            if ready:
                a = int(120 + 70 * (0.5 + 0.5 * _m.sin(self.time * 4.0 + cart["row"])))
                glow = pygame.Surface((r.w + 16, r.h + 16), pygame.SRCALPHA)
                pygame.draw.ellipse(glow, (255, 210, 120, a), glow.get_rect(), 2)
                surf.blit(glow, (r.x - 8, r.y - 8))
            else:
                f = self._font(12, True)
                if f:
                    t = f.render(f"{int(cart['cooldown'])}s", True, (255, 245, 220))
                    surf.blit(t, (r.centerx - t.get_width() // 2, r.y - 18))

    def _draw_wave_bar(self, surf):
        y = WIN_H - 18
        bg = pygame.Rect(BOARD_X, y, BOARD_W, 10)
        pygame.draw.rect(surf, (20, 24, 18, 200), bg, border_radius=5)
        prog = self.director.progress
        fill = pygame.Rect(bg.x, bg.y, int(bg.w * max(0.0, min(1.0, prog))), bg.h)
        if fill.w > 0:
            pygame.draw.rect(surf, (150, 210, 110, 230), fill, border_radius=5)
        pygame.draw.rect(surf, (230, 230, 210, 160), bg, 1, border_radius=5)

    def _draw_banner(self, surf):
        # 提示消息
        if self.message and self.message_timer > 0.0:
            f = self._font(21, True)
            if f:
                alpha = int(255 * min(1.0, self.message_timer / 0.35))
                t = f.render(self.message, True, (255, 250, 225))
                t.set_alpha(alpha)
                bg = pygame.Surface((t.get_width() + 26, t.get_height() + 12),
                                    pygame.SRCALPHA)
                bg.fill((20, 24, 18, 150))
                pos = (BOARD_X + BOARD_W // 2, BOARD_Y + 34)
                surf.blit(bg, bg.get_rect(center=pos))
                surf.blit(t, t.get_rect(center=pos))

        # 波次横幅
        if self.banner_text and self.banner_timer > 0.0:
            f = self._font(44, True)
            if f:
                alpha = int(255 * min(1.0, self.banner_timer / 0.6))
                t = f.render(self.banner_text, True, (255, 210, 120))
                shadow = f.render(self.banner_text, True, (60, 30, 10))
                t.set_alpha(alpha)
                shadow.set_alpha(alpha)
                c = (BOARD_X + BOARD_W // 2, BOARD_Y + BOARD_H // 2 - 40)
                surf.blit(shadow, shadow.get_rect(center=(c[0] + 3, c[1] + 3)))
                surf.blit(t, t.get_rect(center=c))

        # 结束提示
        if self.status != "playing":
            f = self._font(30, True)
            if f:
                t = f.render("点击返回" if self.status == "won" else "再试一次",
                             True, (240, 240, 220))
                surf.blit(t, t.get_rect(center=(BOARD_X + BOARD_W // 2,
                                                BOARD_Y + BOARD_H // 2 + 70)))

class PlantFood:
    """养料掉落物：缓慢飘落后停在原地，点击拾取。"""

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.vy = -40.0
        self.t = 0.0
        self.alive = True
        self.collectible = False
        self.rect = pygame.Rect(int(x) - 18, int(y) - 18, 36, 36)

    def update(self, dt: float):
        self.t += dt
        if self.vy < 0:
            self.vy += 180.0 * dt
        elif self.vy < 60:
            self.y += self.vy * dt
            self.vy = min(60.0, self.vy + 120.0 * dt)
        self.y += self.vy * dt * 0.35
        self.collectible = self.t > 0.5
        self.rect.topleft = (int(self.x) - 18, int(self.y) - 18)

    def draw(self, surf):
        t = self.t
        r = 16 + int(2 * __import__("math").sin(t * 5.0))
        pygame.draw.circle(surf, (60, 140, 90), (int(self.x), int(self.y)), r)
        pygame.draw.circle(surf, (150, 240, 170), (int(self.x) - 4, int(self.y) - 4), max(3, r // 3))
        pygame.draw.circle(surf, (235, 255, 240), (int(self.x), int(self.y)), r, 1)
