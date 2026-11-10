"""商店 2.0：分类页签、5 列网格分页、金币钱包与购买。

数据来自 ``content/shop.json``（tools/build_shop.py 生成）；旧版
``{"items": [...]}`` 也仍然能读。Screen 接口保持 ``ShopScreen(app)``，
离开时调用 ``app.switch("modes")``。
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pygame

from .base import Screen
from .widgets import (BROWN, CREAM, GOLD, GOLD_DARK, GREEN, INK, INK_SOFT,
                      PAPER, RED, draw_coin, fit_text, text)

ROOT = Path(__file__).resolve().parents[2]
WIN_W, WIN_H = 1280, 720

COLS, ROWS = 5, 2
PAGE_SIZE = COLS * ROWS           # 10 件/页（大卡）
CARD_W, CARD_H = 214, 238
GAP_X, GAP_Y = 14, 12
GRID_X = (WIN_W - (COLS * CARD_W + (COLS - 1) * GAP_X)) // 2
GRID_Y = 132
TAB_Y, TAB_H = 80, 38

DEFAULT_TABS = [
    ("seeds", "种子包"),
    ("items", "道具"),
    ("currency", "货币"),
    ("bundles", "礼包"),
]

_FALLBACK_ITEMS = [
    {"id": "pf_pack", "name_zh": "养料包", "desc_zh": "立刻获得 3 份养料。",
     "price": 150, "kind": "plantfood", "value": 3, "tab": "items",
     "item_type": "plantfood", "payload": {"plantfood": 3}},
    {"id": "sun_start", "name_zh": "开局阳光 +150", "desc_zh": "每局开局多 150 阳光。",
     "price": 400, "kind": "sun_start", "value": 150, "tab": "items",
     "item_type": "gameupgrade", "payload": {"sun_start_bonus": 150}},
    {"id": "mower_repair", "name_zh": "割草机维修", "desc_zh": "修复一辆割草机。",
     "price": 250, "kind": "mower", "value": 1, "tab": "items",
     "item_type": "gameupgrade", "payload": {"mower_charges": 1}},
    {"id": "seed_iris", "name_zh": "种子包·鸢尾花", "desc_zh": "解锁鸢尾花。",
     "price": 600, "kind": "plant", "value": "iris", "tab": "seeds",
     "item_type": "plant", "payload": {"plant_id": "iris"}},
]


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


def load_shop_items(app=None) -> list[dict]:
    """读取并规整商品列表；兼容旧版 items/goods/list 三种格式。"""
    data = None
    if app is not None:
        try:
            data = app.content_json("shop", None)
        except Exception:
            data = None
    if data is None:
        data = _load_json(ROOT / "content" / "shop.json")
    if isinstance(data, dict):
        raw = data.get("items") or data.get("goods") or []
    elif isinstance(data, list):
        raw = data
    else:
        raw = []
    if not isinstance(raw, list):
        raw = []
    items = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or entry.get("item_type") or "item")
        tab = str(entry.get("tab") or entry.get("category") or "")
        if tab not in {t[0] for t in DEFAULT_TABS}:
            tab = {"plant": "seeds", "seed": "seeds", "plantfood": "items",
                   "sun_start": "items", "mower": "items",
                   "costume": "items", "gameupgrade": "items",
                   "coin": "currency", "gem": "currency", "mint": "currency",
                   "sprout": "currency", "eventenergy": "currency",
                   "pinata": "bundles", "bundle": "bundles",
                   "action": "bundles"}.get(kind, "items")
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            payload = {}
            if kind == "plant":
                payload = {"plant_id": entry.get("value") or entry.get("plant_id")}
            elif kind == "plantfood":
                payload = {"plantfood": _int(entry.get("value"), 1)}
            elif kind == "sun_start":
                payload = {"sun_start_bonus": _int(entry.get("value"), 1)}
            elif kind == "mower":
                payload = {"mower_charges": _int(entry.get("value"), 1)}
        item = {
            "id": str(entry.get("id") or f"item_{index}"),
            "sku": str(entry.get("sku") or ""),
            "name_zh": str(entry.get("name_zh") or entry.get("name") or "商品"),
            "desc_zh": str(entry.get("desc_zh") or entry.get("desc") or ""),
            "price": max(0, _int(entry.get("price"), 0)),
            "currency": str(entry.get("currency") or "coin"),
            "price_gems": max(0, _int(entry.get("price_gems"), 0)),
            "price_mints": max(0, _int(entry.get("price_mints"), 0)),
            "original_price": max(0, _int(entry.get("original_price"), 0)),
            "item_type": kind,
            "kind": kind,
            "payload": payload,
            "icon": str(entry.get("icon") or ""),
            "tab": tab,
            "category": str(entry.get("category") or tab),
            "rarity": str(entry.get("rarity") or "common"),
            "one_time": bool(entry.get("one_time") or False),
            "implemented": bool(entry.get("implemented", True)),
            "source": str(entry.get("source") or "content"),
        }
        items.append(item)
    return items or [dict(x) for x in _FALLBACK_ITEMS]


def _clip(font, value: str, max_w: int) -> str:
    value = str(value or "")
    if font.size(value)[0] <= max_w:
        return value
    while value and font.size(value + "…")[0] > max_w:
        value = value[:-1]
    return (value + "…") if value else "…"


def _wrap(font, value: str, max_w: int, max_lines: int = 2) -> list[str]:
    value = str(value or "").replace("\n", " ")
    lines, current = [], ""
    for char in value:
        if font.size(current + char)[0] > max_w:
            lines.append(current)
            current = char
            if len(lines) >= max_lines:
                break
        else:
            current += char
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and "".join(lines) != value.replace("\n", " "):
        while lines and font.size(lines[-1] + "…")[0] > max_w:
            lines[-1] = lines[-1][:-1]
        if lines:
            lines[-1] = (lines[-1] + "…") if lines[-1] else "…"
    return lines


def _rounded(surf, color, rect, radius=10, width=0):
    pygame.draw.rect(surf, color, rect, width, border_radius=radius)


class ShopScreen(Screen):
    name = "shop"

    def __init__(self, app):
        super().__init__(app)
        self.items = load_shop_items(app)
        self._fonts = {}
        self._bg = None
        self._icon_cache = {}
        self.tab_index = 0
        self.page = 0
        self.hover_id = None
        self.hover_item = None
        self._toast = ""
        self._toast_until = 0.0
        self._time = 0.0
        self._back_rect = pygame.Rect(22, 18, 104, 42)
        self._page_prev = pygame.Rect(1050, 654, 46, 38)
        self._page_next = pygame.Rect(1206, 654, 46, 38)
        self.tab_defs = self._read_tab_defs(app)
        self.tab_counts = {tab: 0 for tab, _ in self.tab_defs}
        for item in self.items:
            tab = item.get("tab", "items")
            if tab in self.tab_counts:
                self.tab_counts[tab] += 1
        self._seed_pool = self._read_seed_pool(app)
        self._tab_rects = self._make_tab_rects()

    # ------------------------------------------------------------ 数据
    def _read_tab_defs(self, app):
        data = None
        if app is not None:
            try:
                data = app.content_json("shop", None)
            except Exception:
                data = None
        if data is None:
            data = _load_json(ROOT / "content" / "shop.json")
        defs = []
        if isinstance(data, dict):
            for entry in data.get("categories", []) or []:
                if isinstance(entry, dict):
                    tid = str(entry.get("id") or entry.get("tab") or "")
                    label = str(entry.get("name_zh") or entry.get("label") or "")
                    if tid and label:
                        defs.append((tid, label))
        if not defs:
            present = {item.get("tab") for item in self.items}
            defs = [(tid, label) for tid, label in DEFAULT_TABS if tid in present]
        if not defs:
            defs = list(DEFAULT_TABS)
        return defs

    def _read_seed_pool(self, app):
        data = None
        if app is not None:
            try:
                data = app.content_json("shop", None)
            except Exception:
                data = None
        if data is None:
            data = _load_json(ROOT / "content" / "shop.json")
        pool = []
        if isinstance(data, dict) and isinstance(data.get("seed_pool"), list):
            pool = [str(x) for x in data.get("seed_pool") if isinstance(x, str)]
        if not pool:
            pool = [item["payload"].get("plant_id")
                    for item in self.items
                    if item.get("item_type") == "plant"
                    and item.get("payload", {}).get("plant_id")]
        return [x for x in pool if x]

    def _make_tab_rects(self):
        count = max(1, len(self.tab_defs))
        widths = []
        for tid, label in self.tab_defs:
            widths.append(max(124, 34 + len(label) * 20))
        total = sum(widths) + (count - 1) * 10
        x = (WIN_W - total) // 2
        rects = []
        for (tid, label), width in zip(self.tab_defs, widths):
            rects.append((pygame.Rect(x, TAB_Y, width, TAB_H), tid, label))
            x += width + 10
        return rects

    # ------------------------------------------------------------ 工具
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
        self._toast_until = self._time + 2.2

    def _items_for_tab(self):
        if not self.tab_defs:
            return list(self.items)
        tab = self.tab_defs[self.tab_index % len(self.tab_defs)][0]
        return [item for item in self.items if item.get("tab") == tab]

    def page_count(self):
        return max(1, math.ceil(len(self._items_for_tab()) / PAGE_SIZE))

    def _page_items(self):
        items = self._items_for_tab()
        start = self.page * PAGE_SIZE
        return items[start:start + PAGE_SIZE]

    def _card_rect(self, index):
        row, col = divmod(index, COLS)
        return pygame.Rect(GRID_X + col * (CARD_W + GAP_X),
                           GRID_Y + row * (CARD_H + GAP_Y), CARD_W, CARD_H)

    def _current_tab(self):
        if not self.tab_defs:
            return "items"
        return self.tab_defs[self.tab_index % len(self.tab_defs)][0]

    # ------------------------------------------------------------ 状态
    def _payload(self, item):
        return item.get("payload") if isinstance(item.get("payload"), dict) else {}

    def _is_owned(self, item):
        save = self._save()
        payload = self._payload(item)
        typ = item.get("item_type")
        if typ == "plant":
            pid = str(payload.get("plant_id") or "")
            return bool(save and pid and save.owns_plant(pid))
        if typ in ("costume", "gameupgrade") or item.get("one_time"):
            settings = getattr(save, "settings", {}) if save else {}
            return bool(settings.get(f"shop_owned_{item.get('id')}"))
        return False

    def _status_badge(self, item):
        if not item.get("implemented", True):
            return "未实装", RED
        if self._is_owned(item):
            return "已购", GREEN
        if item.get("price", 0) <= 0:
            return "免费", GOLD
        return "", None

    def _effect_text(self, item):
        payload = self._payload(item)
        typ = item.get("item_type")
        if typ == "plant":
            pid = str(payload.get("plant_id") or "")
            if not item.get("implemented", True):
                return "该植物尚未实装到本作"
            plant = None
            try:
                plant = self.app.data.plants.get(pid)
            except Exception:
                plant = None
            name = getattr(plant, "name_zh", pid)
            return f"解锁植物：{name}"
        if typ == "plantfood":
            return f"获得养料 ×{_int(payload.get('plantfood'), 1)}"
        if typ == "coin":
            return f"获得金币 ×{_int(payload.get('coins'), 0)}"
        if typ == "gem":
            return f"获得钻石 ×{_int(payload.get('gems'), 1)}"
        if typ == "seed_pack" or "seed_pack" in payload:
            return f"随机种子包 ×{_int(payload.get('seed_pack'), 1)}"
        if "setting" in payload:
            labels = {"mints": "金金茶券", "sprouts": "幼苗",
                      "event_energy": "活动能量"}
            name = labels.get(str(payload["setting"]), str(payload["setting"]))
            return f"获得{name} ×{_int(payload.get('amount'), 1)}"
        if "world_key" in payload:
            return "解锁一张世界地图钥匙"
        if "collectible" in payload:
            return "获得限定收藏品"
        if typ == "costume":
            return "获得限定装扮"
        numeric = [k for k, v in payload.items() if isinstance(v, (int, float))]
        if numeric:
            labels = {"sun_start_bonus": "开局阳光", "mower_charges": "割草机",
                      "plantfood_slots": "叶绿素槽", "seed_slots": "种子槽",
                      "sun_shovel": "阳光铲", "plantfood_refresh": "冷却强化"}
            return "、".join(f"{labels.get(k, k)} +{payload[k]}" for k in numeric)
        return item.get("desc_zh", "")

    def _price_text(self, item):
        if not item.get("implemented", True):
            return "未实装"
        if item.get("price", 0) <= 0:
            return "免费"
        return f"{item.get('price', 0):,} 金币"

    # ------------------------------------------------------------ 购买
    def buy(self, index):
        items = self._page_items()
        if index < 0 or index >= len(items):
            return False
        item = items[index]
        if not item.get("implemented", True):
            self._toast_show("该商品尚未实装")
            return False
        if self._is_owned(item):
            self._toast_show("已经购买过了")
            return False
        save = self._save()
        if save is None:
            self._toast_show("存档不可用")
            return False
        price = max(0, _int(item.get("price"), 0))
        if price > 0 and save.coins < price:
            self._toast_show(f"金币不足，还差 {price - save.coins:,}")
            return False
        if price > 0 and not save.spend_coins(price):
            self._toast_show("金币不足")
            return False
        self._grant(item, save)
        save.save()
        self._toast_show(f"购买成功：{item.get('name_zh', '商品')}")
        return True

    def _grant(self, item, save):
        payload = self._payload(item)
        typ = item.get("item_type")
        settings = save.settings
        if typ == "plant":
            pid = str(payload.get("plant_id") or "")
            if pid:
                save.unlock_plant(pid)
            return
        if typ == "plantfood":
            save.plantfood += max(0, _int(payload.get("plantfood"), 1))
            return
        if typ == "coin":
            save.coins += max(0, _int(payload.get("coins"), 0))
            return
        if typ == "gem":
            settings["gems"] = max(0, _int(settings.get("gems"), 0)) + max(
                0, _int(payload.get("gems"), 1))
        elif typ in ("mint", "sprout", "eventenergy") or "setting" in payload:
            key = str(payload.get("setting") or
                      {"mint": "mints", "sprout": "sprouts",
                       "eventenergy": "event_energy"}.get(typ, "items"))
            amount = max(0, _int(payload.get("amount"), 1))
            settings[key] = max(0, _int(settings.get(key), 0)) + amount
        elif "world_key" in payload:
            keys = settings.setdefault("world_keys", [])
            world = str(payload["world_key"])
            if world not in keys:
                keys.append(world)
        elif "collectible" in payload:
            coll = settings.setdefault("collectibles", [])
            value = str(payload["collectible"])
            if value not in coll:
                coll.append(value)
        elif "seed_pack" in payload:
            count = max(1, _int(payload.get("seed_pack"), 1))
            self._grant_seed_pack(save, count)
            if payload.get("coins"):
                save.coins += max(0, _int(payload.get("coins"), 0))
        elif typ == "costume":
            settings[f"shop_owned_{item.get('id')}"] = True
        elif typ == "gameupgrade":
            for key, value in payload.items():
                if isinstance(value, (int, float)):
                    settings[key] = max(0, _int(settings.get(key), 0)) + int(value)
                elif isinstance(value, str):
                    settings[key] = value
            settings[f"shop_owned_{item.get('id')}"] = True
        else:
            settings[f"shop_owned_{item.get('id')}"] = True

    def _grant_seed_pack(self, save, count):
        pool = [pid for pid in self._seed_pool if pid]
        locked = [pid for pid in pool if not save.owns_plant(pid)]
        random.shuffle(locked)
        granted = []
        for pid in locked[:count]:
            save.unlock_plant(pid)
            granted.append(pid)
        if len(granted) < count:
            # 种子池已满时，每差一个包补 500 金币。
            save.coins += 500 * (count - len(granted))

    # ------------------------------------------------------------ 交互
    def _set_tab(self, index):
        if not self.tab_defs:
            return
        index %= len(self.tab_defs)
        if index != self.tab_index:
            self.tab_index = index
            self.page = 0
            self.hover_id = None
            self.hover_item = None

    def _set_page(self, page):
        self.page = max(0, min(page, self.page_count() - 1))

    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.app.switch("modes")
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                self._set_tab(self.tab_index - 1)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self._set_tab(self.tab_index + 1)
            elif event.key == pygame.K_TAB:
                if event.mod & pygame.KMOD_SHIFT:
                    self._set_tab(self.tab_index - 1)
                else:
                    self._set_tab(self.tab_index + 1)
            elif event.key in (pygame.K_PAGEDOWN, pygame.K_RIGHTBRACKET):
                self._set_page(self.page + 1)
            elif event.key in (pygame.K_PAGEUP, pygame.K_LEFTBRACKET):
                self._set_page(self.page - 1)
            return
        if event.type == pygame.MOUSEWHEEL:
            self._set_page(self.page - (1 if event.y > 0 else -1))
            return
        if event.type == pygame.MOUSEMOTION:
            self._update_hover(event.pos)
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            pos = event.pos
            if self._back_rect.collidepoint(pos):
                self.app.switch("modes")
                return
            for rect, tid, _label in self._tab_rects:
                if rect.collidepoint(pos):
                    for index, (_tid, _label2) in enumerate(self.tab_defs):
                        if _tid == tid:
                            self._set_tab(index)
                            return
            if self._page_prev.collidepoint(pos):
                self._set_page(self.page - 1)
                return
            if self._page_next.collidepoint(pos):
                self._set_page(self.page + 1)
                return
            for index in range(len(self._page_items())):
                if self._card_rect(index).collidepoint(pos):
                    self.buy(index)
                    return

    def _update_hover(self, pos):
        self.hover_item = None
        self.hover_id = None
        for index, item in enumerate(self._page_items()):
            if self._card_rect(index).collidepoint(pos):
                self.hover_item = item
                self.hover_id = item.get("id")
                return

    def update(self, dt):
        super().update(dt)
        self._time += dt
        if self._toast_until and self._time > self._toast_until:
            self._toast = ""
            self._toast_until = 0.0

    # ------------------------------------------------------------ 绘制
    def _background(self):
        if self._bg is not None:
            return self._bg
        surf = pygame.Surface((WIN_W, WIN_H))
        top = (24, 43, 31)
        bottom = (12, 22, 17)
        for y in range(WIN_H):
            t = y / max(1, WIN_H - 1)
            color = (int(top[0] * (1 - t) + bottom[0] * t),
                     int(top[1] * (1 - t) + bottom[1] * t),
                     int(top[2] * (1 - t) + bottom[2] * t))
            pygame.draw.line(surf, color, (0, y), (WIN_W, y))
        # 装饰性光斑与叶子
        pygame.draw.circle(surf, (34, 66, 44), (150, 620), 220)
        pygame.draw.circle(surf, (30, 58, 40), (1160, 120), 180)
        for x, y, r in ((220, 160, 42), (1050, 600, 60), (980, 260, 24)):
            pygame.draw.circle(surf, (40, 78, 52), (x, y), r, 3)
        self._bg = surf
        return surf

    def _draw_icon(self, item, size, surf, pos):
        key = (item.get("icon"), size)
        icon = self._icon_cache.get(key)
        if icon is None:
            icon = self._build_icon(item, size)
            self._icon_cache[key] = icon
        if icon is not None:
            surf.blit(icon, pos)

    def _build_icon(self, item, size):
        try:
            icon_key = item.get("icon") or ""
            if icon_key.startswith("plant:"):
                pid = icon_key.split(":", 1)[1]
                plant = self.app.data.plants.get(pid)
                if plant is not None:
                    thumb = self.app.assets.db_thumb(plant.art, size, size,
                                                     anim="Idle")
                    if thumb is not None:
                        return thumb
                    sprite = self.app.assets.static_sprite(plant.art, size - 4)
                    if sprite is not None:
                        surf = pygame.Surface((size, size), pygame.SRCALPHA)
                        surf.blit(sprite, sprite.get_rect(center=(size // 2, size // 2)))
                        return surf
            elif icon_key.startswith("type:"):
                return self._type_icon(icon_key.split(":", 1)[1], size)
        except Exception:
            pass
        return self._type_icon(item.get("item_type"), size)

    def _type_icon(self, typ, size):
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        c = size // 2
        try:
            if typ in ("coin", "currency"):
                pygame.draw.circle(surface, (255, 205, 70), (c, c), c - 2)
                pygame.draw.circle(surface, (196, 130, 20), (c, c), c - 3, 2)
                pygame.draw.circle(surface, (255, 236, 150), (c - 4, c - 5), 3)
            elif typ == "gem":
                points = [(c, 2), (size - 3, c - 2), (c, size - 3), (3, c - 2)]
                pygame.draw.polygon(surface, (80, 220, 230), points)
                pygame.draw.polygon(surface, (220, 255, 255), points, 2)
            elif typ == "mint":
                pygame.draw.rect(surface, (168, 96, 208),
                                 (4, 10, size - 8, size - 20), border_radius=5)
                pygame.draw.rect(surface, (235, 205, 255),
                                 (4, 10, size - 8, size - 20), 2, border_radius=5)
            elif typ in ("sprout", "plant", "seeds"):
                pygame.draw.rect(surface, (122, 80, 40),
                                 (8, 8, size - 16, size - 16), border_radius=4)
                pygame.draw.ellipse(surface, (110, 200, 90),
                                    (c - 8, 9, 16, 10))
                pygame.draw.line(surface, (70, 150, 60), (c, 18), (c, size - 8), 2)
            elif typ == "costume":
                pygame.draw.polygon(surface, (210, 90, 120),
                                    [(8, 12), (c - 6, 6), (c, 14),
                                     (c + 6, 6), (size - 8, 12),
                                     (size - 12, size - 8), (10, size - 8)])
            elif typ in ("pinata", "bundle", "action"):
                pygame.draw.rect(surface, (210, 70, 70),
                                 (5, 12, size - 10, size - 17), border_radius=4)
                pygame.draw.rect(surface, (255, 220, 110),
                                 (c - 3, 12, 6, size - 17))
                pygame.draw.rect(surface, (255, 220, 110),
                                 (5, c, size - 10, 5))
            elif typ == "gameupgrade":
                pygame.draw.polygon(surface, (240, 200, 80),
                                    [(c, 3), (size - 5, size // 2),
                                     (c, size - 4), (5, size // 2)])
                pygame.draw.polygon(surface, (255, 245, 190),
                                    [(c, 3), (size - 5, size // 2),
                                     (c, size - 4), (5, size // 2)], 2)
            else:
                pygame.draw.circle(surface, (210, 210, 210), (c, c), c - 3)
                pygame.draw.circle(surface, (110, 110, 110), (c, c), c - 3, 2)
                pygame.draw.line(surface, (110, 110, 110),
                                 (c, 8), (c, size - 8), 2)
                pygame.draw.line(surface, (110, 110, 110),
                                 (8, c), (size - 8, c), 2)
        except Exception:
            pass
        return surface

    def draw(self, surf):
        surf.blit(self._background(), (0, 0))
        # 顶栏
        _rounded(surf, (18, 30, 23), (0, 0, WIN_W, 70), 0)
        pygame.draw.line(surf, (70, 58, 36), (0, 70), (WIN_W, 70), 2)
        _rounded(surf, (62, 48, 30), self._back_rect, 9)
        _rounded(surf, GOLD_DARK, self._back_rect, 9, 2)
        text(surf, self._font(20, True), "‹ 返回", self._back_rect.center,
             CREAM, anchor="center")
        text(surf, self._font(30, True), "商店", (146, 20), GOLD,
             shadow=(0, 0, 0))
        text(surf, self._font(14), "SHOP 2.0", (146, 50), (170, 180, 150))
        self._draw_wallet(surf)
        # 页签
        for index, (rect, tid, label) in enumerate(self._tab_rects):
            selected = index == self.tab_index
            color = (96, 72, 36) if selected else (34, 48, 37)
            _rounded(surf, color, rect, 8)
            _rounded(surf, GOLD if selected else (75, 95, 70), rect, 8, 2)
            label_text = f"{label} ({self.tab_counts.get(tid, 0)})"
            text(surf, self._font(16, selected), label_text, rect.center,
                 CREAM if selected else (175, 190, 165), anchor="center")
        # 网格
        page_items = self._page_items()
        if not page_items:
            text(surf, self._font(22, True), "这个货架暂时没有商品",
                 (WIN_W // 2, 330), (190, 200, 180), anchor="center")
        mouse = pygame.mouse.get_pos() if pygame.display.get_init() else self.mouse
        for index, item in enumerate(page_items):
            self._draw_card(surf, self._card_rect(index), item,
                            self._card_rect(index).collidepoint(mouse) or
                            item.get("id") == self.hover_id)
        # 底栏
        self._draw_footer(surf, page_items)
        # toast
        if self._toast:
            font = self._font(20, True)
            width = max(260, font.size(self._toast)[0] + 52)
            rect = pygame.Rect((WIN_W - width) // 2, 588, width, 44)
            _rounded(surf, (24, 20, 14), rect, 10)
            _rounded(surf, GOLD, rect, 10, 2)
            text(surf, font, self._toast, rect.center, CREAM, anchor="center")

    def _draw_wallet(self, surf):
        save = self._save()
        coins = getattr(save, "coins", 0) if save else 0
        plantfood = getattr(save, "plantfood", 0) if save else 0
        gems = 0
        if save:
            gems = _int(getattr(save, "settings", {}).get("gems"), 0)
        x = 880
        rect = pygame.Rect(x, 13, 176, 44)
        _rounded(surf, (18, 28, 21), rect, 9)
        _rounded(surf, (90, 74, 40), rect, 9, 2)
        draw_coin(surf, (x + 20, 35), 13)
        text(surf, self._font(20, True), f"{coins:,}", (x + 40, 35),
             GOLD, anchor="midleft")
        rect2 = pygame.Rect(x + 184, 13, 118, 44)
        _rounded(surf, (18, 28, 21), rect2, 9)
        _rounded(surf, (70, 96, 62), rect2, 9, 2)
        pygame.draw.circle(surf, (120, 190, 90), (rect2.x + 19, 35), 10)
        text(surf, self._font(18, True), f"养料 {plantfood}", (rect2.x + 36, 35),
             CREAM, anchor="midleft")
        if gems:
            text(surf, self._font(14), f"宝石 {gems}", (rect2.right, 60),
                 (150, 220, 230), anchor="topright")

    # 参考原版商店：奶白卡面 + 彩色标题条 + 大立绘 + 底部蓝色价格条。
    _TAB_COLORS = {"seeds": (106, 168, 50), "items": (138, 91, 214),
                   "currency": (63, 127, 208), "bundles": (224, 138, 42)}
    _TAB_COLORS_DARK = {"seeds": (74, 124, 34), "items": (100, 60, 168),
                        "currency": (44, 92, 160), "bundles": (176, 100, 26)}

    def _tab_color(self, tab, dark=False):
        table = self._TAB_COLORS_DARK if dark else self._TAB_COLORS
        return table.get(tab, (120, 120, 120))

    def _draw_card(self, surf, rect, item, hovered):
        owned = self._is_owned(item)
        implemented = item.get("implemented", True)
        cream = (247, 236, 198) if implemented else (206, 200, 182)
        border = (118, 80, 44)
        _rounded(surf, (54, 36, 20), rect.move(0, 4), 12)
        _rounded(surf, cream, rect, 12)
        _rounded(surf, border, rect, 12, 3)
        if hovered and not owned and implemented:
            _rounded(surf, (255, 226, 130), rect.inflate(4, 4), 14, 3)
        tab = item.get("tab") or self._current_tab()
        header = pygame.Rect(rect.x + 5, rect.y + 5, rect.w - 10, 34)
        _rounded(surf, self._tab_color(tab), header, 8)
        _rounded(surf, self._tab_color(tab, True), header, 8, 2)
        name_font = self._font(16, True)
        text(surf, name_font, _clip(name_font, item.get("name_zh"), rect.w - 24),
             (rect.centerx, header.centery), (255, 250, 236), anchor="center")
        # 促销标签
        promo = (item.get("original_price") or 0) > (item.get("price") or 0) > 0
        if promo:
            pill = pygame.Rect(rect.centerx - 34, header.bottom + 3, 68, 18)
            _rounded(surf, (252, 248, 232), pill, 6)
            _rounded(surf, (196, 58, 58), pill, 6, 1)
            text(surf, self._font(11, True), "促销", pill.center, (196, 58, 58),
                 anchor="center")
        # 立绘
        art_y = header.bottom + (74 if promo else 62)
        icon_size = 92
        icon_rect = pygame.Rect(0, 0, icon_size, icon_size)
        icon_rect.center = (rect.centerx, art_y)
        shadow = pygame.Surface((icon_size, 20), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (90, 66, 40, 70), shadow.get_rect())
        surf.blit(shadow, (icon_rect.x, icon_rect.bottom - 8))
        self._draw_icon(item, icon_size, surf, icon_rect.topleft)
        # 描述
        desc_font = self._font(11)
        lines = _wrap(desc_font, item.get("desc_zh") or self._effect_text(item),
                      rect.w - 26, 2)
        base_y = icon_rect.bottom + 10
        for i, line in enumerate(lines):
            text(surf, desc_font, line, (rect.centerx, base_y + i * 15),
                 (122, 96, 56) if implemented else (140, 134, 120), anchor="center")
        # 状态徽章
        badge, color = self._status_badge(item)
        if badge:
            bfont = self._font(11, True)
            bw = bfont.size(badge)[0] + 14
            brect = pygame.Rect(rect.centerx - bw // 2, base_y + 34, bw, 18)
            _rounded(surf, (60, 50, 34), brect, 6)
            _rounded(surf, color, brect, 6, 1)
            text(surf, bfont, badge, brect.center, color, anchor="center")
        # 价格条
        bar = pygame.Rect(rect.x + 7, rect.bottom - 42, rect.w - 14, 32)
        if implemented:
            currency = item.get("currency") or "coin"
            bar_col = (64, 116, 210)
            if currency == "gem":
                bar_col = (150, 84, 200)
            elif currency == "mint":
                bar_col = (168, 98, 190)
            _rounded(surf, bar_col, bar, 9)
            _rounded(surf, (232, 244, 255), bar, 9, 1)
            label = self._price_text(item).lstrip("¢").strip()
            if currency == "coin":
                draw_coin(surf, (bar.x + 18, bar.centery), 10)
            elif currency == "gem":
                pygame.draw.polygon(surf, (150, 240, 250),
                                    [(bar.x + 18, bar.centery - 7),
                                     (bar.x + 27, bar.centery),
                                     (bar.x + 18, bar.centery + 7),
                                     (bar.x + 9, bar.centery)])
            else:
                pygame.draw.circle(surf, (240, 210, 255), (bar.x + 18, bar.centery), 9)
            text(surf, self._font(15, True), label, (bar.centerx + 10, bar.centery),
                 (255, 255, 255), anchor="center")
        else:
            _rounded(surf, (86, 84, 78), bar, 9)
            text(surf, self._font(13, True), "未实装", bar.center,
                 (235, 228, 214), anchor="center")
        if owned:
            ob = pygame.Rect(rect.right - 64, header.bottom + 4, 54, 20)
            _rounded(surf, (72, 120, 56), ob, 7)
            text(surf, self._font(11, True), "已购", ob.center, (236, 255, 226),
                 anchor="center")

    def _draw_footer(self, surf, page_items):
        _rounded(surf, (18, 28, 21), (0, 640, WIN_W, 80), 0)
        pygame.draw.line(surf, (54, 68, 48), (0, 640), (WIN_W, 640), 2)
        item = self.hover_item
        if item is not None:
            icon = 34
            self._draw_icon(item, icon, surf, (24, 658))
            text(surf, self._font(16, True), item.get("name_zh", ""),
                 (68, 652), GOLD)
            detail = item.get("desc_zh") or self._effect_text(item)
            text(surf, self._font(12), _clip(self._font(12), detail, 640),
                 (68, 675), CREAM)
            text(surf, self._font(12), self._effect_text(item), (68, 693),
                 (158, 200, 145))
            price = self._price_text(item)
            text(surf, self._font(14, True), price,
                 (860, 681), GOLD, anchor="midright")
        else:
            text(surf, self._font(13), "←/→ 或 Tab 切换分类 · 滚轮/[ ] 翻页 · 点击商品购买",
                 (24, 672), (160, 176, 152))
        # 分页
        pages = self.page_count()
        text(surf, self._font(14), f"第 {self.page + 1} / {pages} 页",
             (1160, 648), (185, 200, 175), anchor="midright")
        for rect, label, enabled in (
                (self._page_prev, "‹", self.page > 0),
                (self._page_next, "›", self.page < pages - 1)):
            _rounded(surf, (44, 58, 43) if enabled else (28, 34, 28), rect, 8)
            _rounded(surf, GOLD_DARK if enabled else (60, 68, 58), rect, 8, 2)
            text(surf, self._font(24, True), label, rect.center,
                 CREAM if enabled else (100, 105, 95), anchor="center")
