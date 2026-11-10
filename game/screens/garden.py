"""禅境花园 2.0：8 个花盆、四阶段生长、浇水、收获与铲除。

数据来自 ``content/garden.json``（tools/build_garden.py 生成）。每盆的
存档结构为 ``{slot, plant, stage, planted, last_water, ready, watered}``，
老存档缺少的字段由 :mod:`game.save` 自动补齐。

测试加速：设置环境变量 ``PVZ2_GARDEN_FAST=1``，生长/浇水速度 ×100。
"""
from __future__ import annotations

import json
import math
import os
import random
import time
from pathlib import Path

import pygame

from .base import Screen
from .widgets import CREAM, GOLD, GOLD_DARK, GREEN, RED, draw_coin, text

ROOT = Path(__file__).resolve().parents[2]
WIN_W, WIN_H = 1280, 720

POT_COLS, POT_ROWS = 4, 2
POT_N = 8
POT_W, POT_H = 210, 210
GAP_X, GAP_Y = 18, 16
GRID_Y = 92
GRID_X = (WIN_W - (POT_COLS * POT_W + (POT_COLS - 1) * GAP_X)) // 2

PICKER_RECT = pygame.Rect(200, 86, 880, 548)
PICKER_COLS = 8
PICKER_ROWS = 4
PICKER_PAGE = PICKER_COLS * PICKER_ROWS
PICKER_CELL_W, PICKER_CELL_H = 98, 100
PICKER_GAP = 6

DEFAULT_CONFIG = {
    "pot_count": 8,
    "grow_seconds": 18000,
    "stage_count": 4,
    "stage_names": ["幼芽", "生长", "含苞", "成熟"],
    "stage_seconds": [0, 4500, 9000, 18000],
    "plant_pool": [],
    "seed_pool": [],
    "water": {"cost_coins": 5, "reduce_seconds": 1800,
              "max_waters": 5, "bonus_per_water": 0.05},
    "harvest": {"coins": 50, "plantfood_min": 1, "plantfood_max": 3,
                "seed_chance": 0.12, "treasure_chance": 0.03,
                "treasure_coins": 500, "treasure_plantfood": 3},
    "rarities": [
        {"id": "common", "name_zh": "普通", "weight": 60,
         "coin_mult": 1.0, "plantfood": 1},
        {"id": "rare", "name_zh": "稀有", "weight": 30,
         "coin_mult": 1.5, "plantfood": 2},
        {"id": "epic", "name_zh": "史诗", "weight": 10,
         "coin_mult": 2.5, "plantfood": 3},
    ],
}

_STAGE_COLORS = [(120, 190, 100), (90, 180, 90), (230, 190, 80),
                 (255, 215, 90)]


def _int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _load_json(path: Path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _clip(font, value, max_w):
    value = str(value or "")
    if font.size(value)[0] <= max_w:
        return value
    while value and font.size(value + "…")[0] > max_w:
        value = value[:-1]
    return (value + "…") if value else "…"


def _fmt_time(seconds):
    seconds = max(0, int(math.ceil(seconds)))
    if seconds >= 3600:
        return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 60}:{seconds % 60:02d}"


class GardenScreen(Screen):
    name = "garden"

    def __init__(self, app):
        super().__init__(app)
        self.config = self._load_config(app)
        self._fonts = {}
        self._bg = None
        self._sprite_cache = {}
        self._time = 0.0
        self._toast = ""
        self._toast_until = 0.0
        self._refresh_timer = 0.0
        self.hover_slot = None
        self.picker_open = False
        self.picker_slot = None
        self.picker_page = 0
        self.picker_choices = []
        self._back_rect = pygame.Rect(22, 18, 104, 42)
        self._picker_close = pygame.Rect(PICKER_RECT.right - 46,
                                         PICKER_RECT.y + 8, 36, 36)
        self._picker_prev = pygame.Rect(PICKER_RECT.x + 230,
                                        PICKER_RECT.bottom - 46, 46, 34)
        self._picker_next = pygame.Rect(PICKER_RECT.right - 276,
                                        PICKER_RECT.bottom - 46, 46, 34)
        self._stage_names = self._read_stage_names()
        self._speed = self._read_speed(app)
        self._grow_seconds = max(1, int(self.config.get("grow_seconds", 18000)
                                        / self._speed))
        water = self.config.get("water") or {}
        self.water_cost = max(0, _int(water.get("cost_coins"), 5))
        self.water_reduce = max(1, int(_int(water.get("reduce_seconds"), 1800)
                                       / self._speed))
        self.water_max = max(1, _int(water.get("max_waters"), 5))
        self.water_bonus = float(water.get("bonus_per_water", 0.05) or 0.0)
        harvest = self.config.get("harvest") or {}
        self.harvest_coins = max(0, _int(harvest.get("coins"), 50))
        self.harvest_seed_chance = float(harvest.get("seed_chance", 0.12) or 0)
        self.harvest_treasure_chance = float(
            harvest.get("treasure_chance", 0.03) or 0)
        self.harvest_treasure_coins = _int(harvest.get("treasure_coins"), 500)
        self.harvest_treasure_food = _int(
            harvest.get("treasure_plantfood"), 3)
        self.rarities = [r for r in (self.config.get("rarities") or [])
                         if isinstance(r, dict)] or list(DEFAULT_CONFIG["rarities"])
        self.plant_pool = [str(x) for x in
                           (self.config.get("plant_pool") or []) if x]
        self.seed_pool = [str(x) for x in
                          (self.config.get("seed_pool") or []) if x]
        self._choice_cache = None
        self.picker_choices = self._build_choices()

    # ------------------------------------------------------------ 数据
    def _load_config(self, app):
        data = None
        if app is not None:
            try:
                data = app.content_json("garden", None)
            except Exception:
                data = None
        if data is None:
            data = _load_json(ROOT / "content" / "garden.json")
        if not isinstance(data, dict):
            data = {}
        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        for key, value in data.items():
            if key in ("water", "harvest") and isinstance(value, dict):
                merged.setdefault(key, {}).update(value)
            elif key == "rarities" and isinstance(value, list):
                merged[key] = value
            else:
                merged[key] = value
        return merged

    def _read_stage_names(self):
        names = self.config.get("stage_names") or []
        if not isinstance(names, list) or len(names) < 4:
            names = list(DEFAULT_CONFIG["stage_names"])
        return [str(x) for x in names[:4]]

    def _read_speed(self, app):
        fast = os.environ.get("PVZ2_GARDEN_FAST", "").strip().lower()
        if fast in ("1", "true", "yes", "on"):
            return 100.0
        try:
            speed = float(getattr(app, "garden_debug_speed", 1.0) or 1.0)
        except (TypeError, ValueError):
            speed = 1.0
        return max(0.05, min(5000.0, speed))

    def _font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            try:
                self._fonts[key] = self.app.font(size, bold=bold)
            except Exception:
                try:
                    self._fonts[key] = self.app.font(size, bold)
                except Exception:
                    self._fonts[key] = pygame.font.Font(None, size)
        return self._fonts[key]

    def _save(self):
        try:
            return self.app.save
        except Exception:
            return None

    def _toast_show(self, message):
        self._toast = str(message)
        self._toast_until = self._time + 2.4

    def _build_choices(self):
        save = self._save()
        owned = set(getattr(save, "unlocked_plants", []) or []) if save else set()
        choices = []
        seen = set()
        try:
            plants = self.app.data.plants
        except Exception:
            plants = {}
        for pid in self.plant_pool:
            if pid in seen or pid not in plants:
                continue
            seen.add(pid)
            choices.append(pid)
        for pid in owned:
            if pid in seen or pid not in plants:
                continue
            seen.add(pid)
            choices.append(pid)
        if not choices:
            # 数据缺失时退回配置池，至少让界面可用。
            choices = [pid for pid in self.plant_pool if pid]
        def sort_key(pid):
            plant = plants.get(pid) if plants else None
            return (getattr(plant, "almanac_no", 999), getattr(plant, "name_zh", pid))
        choices.sort(key=sort_key)
        return choices

    def refresh_choices(self):
        self._choice_cache = None
        self.picker_choices = self._build_choices()

    def _plant_name(self, pid):
        try:
            plant = self.app.data.plants.get(pid)
            if plant is not None:
                return plant.name_zh
        except Exception:
            pass
        return pid

    # ------------------------------------------------------------ 时间
    def _now(self):
        return int(time.time())

    def stage_of(self, entry, now=None):
        save = self._save()
        if save is not None:
            return save.garden_stage(entry, now)
        if not entry:
            return -1
        now = self._now() if now is None else int(now)
        planted = _int(entry.get("planted"), now)
        ready = _int(entry.get("ready"), planted)
        if now >= ready:
            return 3
        span = max(1, ready - planted)
        return max(0, min(2, int((now - planted) / span * 4)))

    def _remaining(self, entry):
        if not entry:
            return 0
        return max(0, _int(entry.get("ready"), 0) - self._now())

    def _progress(self, entry):
        if not entry:
            return 0.0
        planted = _int(entry.get("planted"), 0)
        ready = _int(entry.get("ready"), planted)
        span = max(1, ready - planted)
        return max(0.0, min(1.0, (self._now() - planted) / span))

    def _mature(self, entry):
        return bool(entry) and self._now() >= _int(entry.get("ready"), 0)

    def _pot_entry(self, slot):
        save = self._save()
        return save.garden_slot(slot) if save else None

    # ------------------------------------------------------------ 布局
    def pot_rect(self, slot):
        row, col = divmod(int(slot), POT_COLS)
        return pygame.Rect(GRID_X + col * (POT_W + GAP_X),
                           GRID_Y + row * (POT_H + GAP_Y), POT_W, POT_H)

    def _pot_rect(self, slot):
        return self.pot_rect(slot)

    def water_rect(self, slot):
        r = self.pot_rect(slot)
        return pygame.Rect(r.x + 8, r.bottom - 34, 60, 26)

    def harvest_rect(self, slot):
        r = self.pot_rect(slot)
        return pygame.Rect(r.x + 75, r.bottom - 34, 60, 26)

    def shovel_rect(self, slot):
        r = self.pot_rect(slot)
        return pygame.Rect(r.x + 142, r.bottom - 34, 60, 26)

    def picker_cell_rect(self, index):
        index = int(index)
        row, col = divmod(index, PICKER_COLS)
        total_w = PICKER_COLS * PICKER_CELL_W + (PICKER_COLS - 1) * PICKER_GAP
        x0 = PICKER_RECT.centerx - total_w // 2
        y0 = PICKER_RECT.y + 58
        return pygame.Rect(x0 + col * (PICKER_CELL_W + PICKER_GAP),
                           y0 + row * (PICKER_CELL_H + PICKER_GAP),
                           PICKER_CELL_W, PICKER_CELL_H)

    def picker_page_count(self):
        return max(1, math.ceil(len(self.picker_choices) / PICKER_PAGE))

    def _picker_items(self):
        start = self.picker_page * PICKER_PAGE
        return self.picker_choices[start:start + PICKER_PAGE]

    # ------------------------------------------------------------ 动作
    def open_picker(self, slot):
        self.refresh_choices()
        if not self.picker_choices:
            self._toast_show("还没有可种植的植物")
            return
        self.picker_open = True
        self.picker_slot = int(slot)
        self.picker_page = 0

    def close_picker(self):
        self.picker_open = False
        self.picker_slot = None

    def plant_at(self, index):
        """在当前选择器里种下第 index 株植物。"""
        items = self._picker_items()
        if index < 0 or index >= len(items):
            return False
        pid = items[index]
        save = self._save()
        if save is None:
            self._toast_show("存档不可用")
            return False
        slot = self.picker_slot
        if slot is None:
            return False
        save.garden_plant(slot, pid, self._grow_seconds)
        self._toast_show(f"种下了 {self._plant_name(pid)}")
        self.close_picker()
        return True

    def water_slot(self, slot):
        save = self._save()
        if save is None:
            return False
        result = save.garden_water(slot, cost=self.water_cost,
                                   reduce_seconds=self.water_reduce,
                                   max_waters=self.water_max)
        if not result.get("ok"):
            reason = result.get("reason")
            if reason == "coins":
                self._toast_show(f"金币不足，还差 {result.get('need', 0):,}")
            elif reason == "max":
                self._toast_show("这盆已经浇过太多次了")
            elif reason == "mature":
                self._toast_show("已经成熟，直接收获吧")
            else:
                self._toast_show(result.get("message") or "浇水失败")
            return False
        if result.get("mature"):
            self._toast_show("浇水后立刻成熟了！")
        else:
            self._toast_show(f"浇水 -{self.water_cost} 金币，成熟时间缩短")
        return True

    def _pick_rarity(self, entry, slot):
        total = sum(max(1, _int(r.get("weight"), 1)) for r in self.rarities)
        seed = _int(entry.get("planted"), 0) * 131 + int(slot) * 17 + 7
        roll = random.Random(seed).randrange(max(1, total))
        acc = 0
        for rarity in self.rarities:
            acc += max(1, _int(rarity.get("weight"), 1))
            if roll < acc:
                return rarity
        return self.rarities[-1]

    def _grant_seed(self, rng):
        save = self._save()
        if save is None:
            return None
        pool = list(self.seed_pool)
        if not pool:
            pool = [pid for pid in self.picker_choices if pid not in self.plant_pool]
        locked = [pid for pid in pool if pid and not save.owns_plant(pid)]
        if not locked:
            return None
        pid = locked[rng.randrange(len(locked))]
        save.unlock_plant(pid)
        return pid

    def harvest_slot(self, slot):
        save = self._save()
        if save is None:
            return False
        entry = save.garden_slot(slot)
        if not entry:
            self._toast_show("花盆是空的")
            return False
        if not self._mature(entry):
            self._toast_show(f"还没成熟，剩下 {_fmt_time(self._remaining(entry))}")
            return False
        rarity = self._pick_rarity(entry, slot)
        watered = max(0, _int(entry.get("watered"), 0))
        coins = int(self.harvest_coins * float(rarity.get("coin_mult", 1.0))
                    * (1.0 + watered * self.water_bonus))
        plantfood = max(1, _int(rarity.get("plantfood"), 1) + watered // 2)
        rng = random.Random(_int(entry.get("planted"), 0) * 977 + slot * 31 + 5)
        treasure = rng.random() < self.harvest_treasure_chance
        if treasure:
            coins += self.harvest_treasure_coins
            plantfood += self.harvest_treasure_food
        seed = None
        if rng.random() < self.harvest_seed_chance:
            seed = self._grant_seed(rng)
        taken = save.garden_take(slot)
        if not taken:
            return False
        save.add_coins(coins)
        save.plantfood += plantfood
        save.save()
        parts = [f"收获 {self._plant_name(taken.get('plant'))}",
                 f"+{coins} 金币", f"+{plantfood} 养料"]
        if seed:
            parts.append(f"种子包：{self._plant_name(seed)}")
        if treasure:
            parts.append("发现宝藏！")
        self._toast_show("，".join(parts))
        if seed:
            self.refresh_choices()
        return True

    def shovel_slot(self, slot):
        save = self._save()
        if save is None:
            return False
        entry = save.garden_slot(slot)
        if not entry:
            self._toast_show("花盆是空的")
            return False
        name = self._plant_name(entry.get("plant"))
        save.garden_remove(slot)
        self._toast_show(f"已铲除 {name}")
        return True

    # ------------------------------------------------------------ 交互
    def _in_picker(self, pos):
        return self.picker_open and PICKER_RECT.collidepoint(pos)

    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.picker_open:
                    self.close_picker()
                else:
                    self.app.switch("modes")
            elif self.picker_open and event.key in (pygame.K_LEFT, pygame.K_a,
                                                    pygame.K_PAGEUP):
                self.picker_page = max(0, self.picker_page - 1)
            elif self.picker_open and event.key in (pygame.K_RIGHT, pygame.K_d,
                                                    pygame.K_PAGEDOWN):
                self.picker_page = min(self.picker_page_count() - 1,
                                       self.picker_page + 1)
            return
        if event.type == pygame.MOUSEMOTION:
            self._update_hover(event.pos)
            return
        if event.type == pygame.MOUSEWHEEL and self.picker_open:
            self.picker_page = max(0, min(self.picker_page_count() - 1,
                                          self.picker_page - event.y))
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._click(event.pos)

    def _update_hover(self, pos):
        self.hover_slot = None
        if self.picker_open:
            return
        for slot in range(POT_N):
            if self.pot_rect(slot).collidepoint(pos):
                self.hover_slot = slot
                return

    def _click(self, pos):
        if self.picker_open:
            if not PICKER_RECT.collidepoint(pos):
                self.close_picker()
                return
            if self._picker_close.collidepoint(pos):
                self.close_picker()
                return
            if self._picker_prev.collidepoint(pos):
                self.picker_page = max(0, self.picker_page - 1)
                return
            if self._picker_next.collidepoint(pos):
                self.picker_page = min(self.picker_page_count() - 1,
                                       self.picker_page + 1)
                return
            for index in range(len(self._picker_items())):
                if self.picker_cell_rect(index).collidepoint(pos):
                    self.plant_at(index)
                    return
            return
        if self._back_rect.collidepoint(pos):
            self.app.switch("modes")
            return
        for slot in range(POT_N):
            if not self.pot_rect(slot).collidepoint(pos):
                continue
            entry = self._pot_entry(slot)
            if not entry:
                self.open_picker(slot)
                return
            if self.water_rect(slot).collidepoint(pos):
                self.water_slot(slot)
                return
            if self.harvest_rect(slot).collidepoint(pos):
                self.harvest_slot(slot)
                return
            if self.shovel_rect(slot).collidepoint(pos):
                self.shovel_slot(slot)
                return
            if self._mature(entry):
                self.harvest_slot(slot)
            else:
                self._toast_show(
                    f"{self._stage_names[self.stage_of(entry)]}，"
                    f"还需 {_fmt_time(self._remaining(entry))}")
            return

    def update(self, dt):
        super().update(dt)
        self._time += dt
        if self._toast_until and self._time > self._toast_until:
            self._toast = ""
            self._toast_until = 0.0
        self._refresh_timer += dt
        if self._refresh_timer >= 0.5:
            self._refresh_timer = 0.0
            save = self._save()
            if save is not None:
                try:
                    save.garden_refresh()
                except Exception:
                    pass

    # ------------------------------------------------------------ 绘制
    def _background(self):
        if self._bg is not None:
            return self._bg
        surf = pygame.Surface((WIN_W, WIN_H))
        top = (46, 74, 62)
        bottom = (24, 52, 32)
        for y in range(WIN_H):
            t = y / max(1, WIN_H - 1)
            color = (int(top[0] * (1 - t) + bottom[0] * t),
                     int(top[1] * (1 - t) + bottom[1] * t),
                     int(top[2] * (1 - t) + bottom[2] * t))
            pygame.draw.line(surf, color, (0, y), (WIN_W, y))
        pygame.draw.circle(surf, (58, 94, 70), (150, 300), 180)
        pygame.draw.circle(surf, (58, 94, 70), (1140, 420), 220)
        for x in range(0, WIN_W, 80):
            pygame.draw.line(surf, (32, 64, 42), (x, 620), (x + 40, 620), 2)
        self._bg = surf
        return surf

    def draw(self, surf):
        surf.blit(self._background(), (0, 0))
        rounded = pygame.Rect(0, 0, WIN_W, 70)
        pygame.draw.rect(surf, (18, 30, 23), rounded)
        pygame.draw.line(surf, (70, 58, 36), (0, 70), (WIN_W, 70), 2)
        pygame.draw.rect(surf, (62, 48, 30), self._back_rect, border_radius=9)
        pygame.draw.rect(surf, GOLD_DARK, self._back_rect, 2, border_radius=9)
        text(surf, self._font(20, True), "‹ 返回", self._back_rect.center,
             CREAM, anchor="center")
        text(surf, self._font(30, True), "禅境花园", (146, 18), GOLD,
             shadow=(0, 0, 0))
        text(surf, self._font(13),
             f"8 盆 · 生长 {max(1, int(self.config.get('grow_seconds', 18000)) // 60)} 分钟"
             f" · 浇水 {self.water_cost} 金币",
             (146, 50), (185, 205, 180))
        self._draw_wallet(surf)
        for slot in range(POT_N):
            self._draw_pot(surf, slot)
        self._draw_tips(surf)
        if self.picker_open:
            self._draw_picker(surf)
        if self._toast:
            font = self._font(19, True)
            width = max(300, font.size(self._toast)[0] + 52)
            rect = pygame.Rect((WIN_W - width) // 2, 636, width, 42)
            pygame.draw.rect(surf, (24, 20, 14), rect, border_radius=10)
            pygame.draw.rect(surf, GOLD, rect, 2, border_radius=10)
            text(surf, font, self._toast, rect.center, CREAM, anchor="center")

    def _draw_wallet(self, surf):
        save = self._save()
        coins = getattr(save, "coins", 0) if save else 0
        food = getattr(save, "plantfood", 0) if save else 0
        rect = pygame.Rect(880, 13, 176, 44)
        pygame.draw.rect(surf, (18, 28, 21), rect, border_radius=9)
        pygame.draw.rect(surf, (90, 74, 40), rect, 2, border_radius=9)
        draw_coin(surf, (rect.x + 20, 35), 13)
        text(surf, self._font(20, True), f"{coins:,}", (rect.x + 40, 35),
             GOLD, anchor="midleft")
        rect2 = pygame.Rect(1064, 13, 118, 44)
        pygame.draw.rect(surf, (18, 28, 21), rect2, border_radius=9)
        pygame.draw.rect(surf, (70, 96, 62), rect2, 2, border_radius=9)
        pygame.draw.circle(surf, (120, 190, 90), (rect2.x + 19, 35), 10)
        text(surf, self._font(18, True), f"养料 {food}", (rect2.x + 36, 35),
             CREAM, anchor="midleft")

    def _draw_tips(self, surf):
        rect = pygame.Rect(193, 558, 894, 58)
        pygame.draw.rect(surf, (24, 36, 27), rect, border_radius=10)
        pygame.draw.rect(surf, (68, 86, 60), rect, 1, border_radius=10)
        text(surf, self._font(14, True), "花园操作",
             (rect.x + 18, rect.y + 12), GOLD)
        text(surf, self._font(12),
             "点击空盆种下已解锁植物 · 浇水花金币缩短时间 · 成熟后收获金币/养料/种子包 · 铲除清空花盆",
             (rect.x + 18, rect.y + 32), (188, 204, 178))
        text(surf, self._font(11), "阶段会随时间自动推进",
             (rect.right - 16, rect.y + 34), (142, 176, 144),
             anchor="topright")

    def _draw_pot(self, surf, slot):
        rect = self.pot_rect(slot)
        entry = self._pot_entry(slot)
        hovered = self.hover_slot == slot
        save = self._save()
        coins = getattr(save, "coins", 0) if save else 0
        pygame.draw.rect(surf, (12, 18, 13), rect.move(0, 4), border_radius=12)
        pygame.draw.rect(surf, (52, 46, 34) if hovered else (42, 38, 30),
                         rect, border_radius=12)
        pygame.draw.rect(surf, GOLD if hovered else (92, 76, 48),
                         rect, 2, border_radius=12)
        # 花盆本体
        bowl = pygame.Rect(rect.x + 18, rect.y + 40, rect.w - 36, 104)
        pygame.draw.ellipse(surf, (126, 72, 44), bowl)
        pygame.draw.ellipse(surf, (92, 50, 32), bowl.inflate(-8, -10))
        soil = pygame.Rect(bowl.x + 8, bowl.y + 8, bowl.w - 16, 30)
        pygame.draw.ellipse(surf, (56, 38, 26), soil)
        if not entry:
            text(surf, self._font(17, True), "+ 选择植物",
                 (rect.centerx, rect.y + 168), (210, 215, 190), anchor="center")
            return
        stage = self.stage_of(entry)
        stage = max(0, min(3, stage))
        self._draw_plant(surf, entry, rect, stage)
        # 阶段与计时
        stage_color = _STAGE_COLORS[stage]
        pygame.draw.rect(surf, (24, 26, 20),
                         (rect.x + 10, rect.y + 8, 92, 24), border_radius=7)
        text(surf, self._font(13, True), self._stage_names[stage],
             (rect.x + 16, rect.y + 10), stage_color)
        watered = max(0, _int(entry.get("watered"), 0))
        text(surf, self._font(11), f"浇水 {watered}/{self.water_max}",
             (rect.right - 10, rect.y + 12), (160, 200, 160),
             anchor="topright")
        if stage < 3:
            text(surf, self._font(12),
                 f"还需 {_fmt_time(self._remaining(entry))}",
                 (rect.centerx, rect.y + 150), CREAM, anchor="center")
        else:
            text(surf, self._font(13, True), "成熟啦！",
                 (rect.centerx, rect.y + 150), GOLD, anchor="center")
        # 进度条
        bar = pygame.Rect(rect.x + 12, rect.y + 160, rect.w - 24, 6)
        pygame.draw.rect(surf, (24, 30, 22), bar, border_radius=3)
        fill = bar.copy()
        fill.w = max(0, int(bar.w * self._progress(entry)))
        pygame.draw.rect(surf, stage_color, fill, border_radius=3)
        # 按钮
        water = self.water_rect(slot)
        harvest = self.harvest_rect(slot)
        shovel = self.shovel_rect(slot)
        can_water = stage < 3 and watered < self.water_max and coins >= self.water_cost
        can_harvest = stage >= 3
        self._draw_button(surf, water, "浇水", can_water,
                          GOLD_DARK if can_water else (70, 74, 62))
        self._draw_button(surf, harvest, "收获", can_harvest,
                          (70, 120, 58) if can_harvest else (70, 74, 62))
        self._draw_button(surf, shovel, "铲除", True, (120, 66, 52))
        # 悬停提示
        if hovered:
            tip = self._effect_tip(entry, stage)
            font = self._font(12)
            tw = font.size(tip)[0] + 16
            trect = pygame.Rect(rect.centerx - tw // 2,
                                rect.bottom + 4, tw, 22)
            pygame.draw.rect(surf, (18, 24, 16), trect, border_radius=6)
            pygame.draw.rect(surf, (110, 96, 60), trect, 1, border_radius=6)
            text(surf, font, tip, trect.center, CREAM, anchor="center")

    def _effect_tip(self, entry, stage):
        if stage >= 3:
            return "点击收获金币、养料，可能掉落种子包"
        if stage == 0:
            return "幼芽期：浇水可缩短成熟时间"
        if stage == 1:
            return "生长期：继续浇水，等待含苞"
        return "含苞期：快成熟了"

    def _draw_button(self, surf, rect, label, enabled, color):
        pygame.draw.rect(surf, color, rect, border_radius=7)
        pygame.draw.rect(surf, (150, 130, 80) if enabled else (86, 88, 76),
                         rect, 1, border_radius=7)
        text(surf, self._font(13, True), label, rect.center,
             CREAM if enabled else (130, 132, 118), anchor="center")

    def _draw_plant(self, surf, entry, rect, stage):
        pid = str(entry.get("plant") or "")
        plant = None
        try:
            plant = self.app.data.plants.get(pid)
        except Exception:
            plant = None
        if plant is None:
            pygame.draw.circle(surf, (100, 170, 90), (rect.centerx, rect.y + 100), 20)
            return
        key = (pid, stage)
        sprite = self._sprite_cache.get(key)
        if sprite is None:
            target = 58 + stage * 14
            try:
                sprite = self.app.assets.db_thumb(plant.art, target, target,
                                                  anim="Idle")
            except Exception:
                sprite = None
            self._sprite_cache[key] = sprite
        if sprite is not None:
            surf.blit(sprite, (rect.centerx - sprite.get_width() // 2,
                               rect.y + 72 - sprite.get_height() // 2))
        else:
            radius = 16 + stage * 5
            pygame.draw.circle(surf, (90, 170, 80),
                               (rect.centerx, rect.y + 92), radius)
            pygame.draw.line(surf, (60, 120, 50),
                             (rect.centerx, rect.y + 92),
                             (rect.centerx, rect.y + 60), 3)

    def _draw_picker(self, surf):
        overlay = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
        overlay.fill((6, 10, 6, 180))
        surf.blit(overlay, (0, 0))
        pygame.draw.rect(surf, (36, 46, 34), PICKER_RECT, border_radius=12)
        pygame.draw.rect(surf, GOLD, PICKER_RECT, 2, border_radius=12)
        text(surf, self._font(22, True),
             f"选择植物 · 第 {self.picker_slot + 1} 号花盆",
             (PICKER_RECT.x + 18, PICKER_RECT.y + 10), GOLD)
        text(surf, self._font(12),
             "只显示已解锁与初始植物 · 点击卡片种下",
             (PICKER_RECT.x + 18, PICKER_RECT.y + 38), (170, 185, 160))
        pygame.draw.rect(surf, (90, 74, 40), self._picker_close,
                         border_radius=8)
        text(surf, self._font(22, True), "×", self._picker_close.center,
             CREAM, anchor="center")
        items = self._picker_items()
        mouse = pygame.mouse.get_pos() if pygame.display.get_init() else self.mouse
        for index, pid in enumerate(items):
            cell = self.picker_cell_rect(index)
            hovered = cell.collidepoint(mouse)
            pygame.draw.rect(surf, (48, 62, 44) if hovered else (42, 54, 40),
                             cell, border_radius=9)
            pygame.draw.rect(surf, GOLD if hovered else (78, 92, 68),
                             cell, 2, border_radius=9)
            plant = None
            try:
                plant = self.app.data.plants.get(pid)
            except Exception:
                plant = None
            sprite = None
            if plant is not None:
                try:
                    sprite = self.app.assets.db_thumb(plant.art, 52, 52, anim="Idle")
                except Exception:
                    sprite = None
            if sprite is not None:
                surf.blit(sprite, (cell.centerx - sprite.get_width() // 2,
                                   cell.y + 8))
            else:
                pygame.draw.circle(surf, (90, 170, 80),
                                   (cell.centerx, cell.y + 32), 20)
            name = self._plant_name(pid)
            text(surf, self._font(11), _clip(self._font(11), name, cell.w - 8),
                 (cell.centerx, cell.bottom - 16), CREAM, anchor="center")
        pages = self.picker_page_count()
        text(surf, self._font(13), f"{self.picker_page + 1} / {pages}",
             (PICKER_RECT.centerx, PICKER_RECT.bottom - 30),
             (200, 210, 180), anchor="center")
        for rect, label, enabled in (
                (self._picker_prev, "‹", self.picker_page > 0),
                (self._picker_next, "›", self.picker_page < pages - 1)):
            pygame.draw.rect(surf, (54, 68, 48) if enabled else (38, 44, 36),
                             rect, border_radius=7)
            pygame.draw.rect(surf, GOLD_DARK if enabled else (70, 76, 64),
                             rect, 2, border_radius=7)
            text(surf, self._font(22, True), label, rect.center,
                 CREAM if enabled else (110, 114, 100), anchor="center")
