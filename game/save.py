"""存档：世界解锁 / 关卡通过 / 星章 / 商店 / 花园 / 设置。

version 3 起，花园里的每一盆拥有完整的时间模型：
    {slot, plant, planted, ready, stage, last_water, watered}
旧存档（version 2，缺少 stage/last_water/watered）会被自动补齐。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from .config import SAVE_PATH

MAX_STARS = 3
GARDEN_DEFAULT_GROW = 18000
SAVE_VERSION = 3


def _to_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _stage_for(planted: int, ready: int, now: int) -> int:
    """按时间比例返回 0..3 阶段；只有真正成熟才是 3。"""
    if now >= ready:
        return 3
    span = max(1, int(ready) - int(planted))
    frac = max(0.0, min(0.999999, (now - int(planted)) / span))
    return max(0, min(2, int(frac * 4)))


def _normalize_garden_entry(raw: dict, index: int, now: int) -> dict | None:
    if not isinstance(raw, dict):
        return None
    plant = str(raw.get("plant", "") or "")
    if not plant:
        return None
    slot = _to_int(raw.get("slot", index), index)
    if slot < 0:
        return None
    planted = _to_int(raw.get("planted", now), now)
    ready = _to_int(raw.get("ready", 0), 0)
    if ready <= 0:
        grow = _to_int(raw.get("grow_seconds", GARDEN_DEFAULT_GROW),
                       GARDEN_DEFAULT_GROW)
        ready = planted + max(1, grow)
    if ready <= planted:
        ready = planted + 1
    last_water = _to_int(raw.get("last_water", 0), 0)
    watered = _to_int(raw.get("watered", 0), 0)
    entry = dict(raw)
    entry.update({
        "slot": slot,
        "plant": plant,
        "planted": planted,
        "ready": ready,
        "stage": _stage_for(planted, ready, now),
        "last_water": max(0, last_water),
        "watered": max(0, watered),
    })
    return entry


def _normalize_garden(raw) -> list[dict]:
    """兼容旧版 list、{"slots": [...]}、{slot: entry} 三种写法。"""
    now = int(time.time())
    entries = []
    if isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict):
        slots = raw.get("slots")
        if isinstance(slots, list):
            entries = slots
        else:
            for key, value in raw.items():
                if isinstance(value, dict):
                    item = dict(value)
                    item.setdefault("slot", _to_int(key, 0))
                    entries.append(item)
    out = []
    seen = set()
    for index, item in enumerate(entries):
        entry = _normalize_garden_entry(item, index, now)
        if entry is None:
            continue
        # 同槽位重复时保留最后一条，和旧版 garden_plant 的行为一致。
        slot = entry["slot"]
        if slot in seen:
            out = [x for x in out if x["slot"] != slot]
        seen.add(slot)
        out.append(entry)
    out.sort(key=lambda x: x["slot"])
    return out


@dataclass
class SaveData:
    completed: list[str] = field(default_factory=list)      # "world:index"
    unlocked_worlds: list[str] = field(default_factory=list)
    settings: dict = field(default_factory=lambda: {
        "high_view": False, "high_quality": True, "speed": 1.0, "music": True, "sfx": True})
    coins: int = 0
    version: int = SAVE_VERSION
    stars: dict = field(default_factory=dict)               # "world:index" -> [0/1,0/1,0/1]
    unlocked_plants: list[str] = field(default_factory=list)  # 商店购买的植物
    plantfood: int = 0
    garden: list[dict] = field(default_factory=list)        # 见模块 docstring
    best_survival: dict = field(default_factory=dict)       # world_id -> score
    keys: int = 0                                           # 冒险钥匙
    keys_earned_from_stars: int = 0                         # 已按星数发放的钥匙记账

    # 每累计这么多颗星，补发 1 把钥匙
    STARS_PER_KEY = 10

    @classmethod
    def load(cls) -> "SaveData":
        try:
            with open(SAVE_PATH, encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                return cls()
            s = cls()
            s.completed = [str(x) for x in (d.get("completed", []) or [])]
            s.unlocked_worlds = [str(x) for x in (d.get("unlocked_worlds", []) or [])]
            s.coins = max(0, _to_int(d.get("coins", 0), 0))
            raw_settings = d.get("settings", {}) or {}
            if isinstance(raw_settings, dict):
                s.settings.update(raw_settings)
            raw_stars = d.get("stars", {}) or {}
            if isinstance(raw_stars, dict):
                for key, val in raw_stars.items():
                    if isinstance(val, list):
                        s.stars[str(key)] = [1 if x else 0 for x in val[:MAX_STARS]]
            raw_plants = d.get("unlocked_plants", []) or []
            if isinstance(raw_plants, (list, tuple, set)):
                s.unlocked_plants = [str(p) for p in raw_plants]
            s.plantfood = max(0, _to_int(d.get("plantfood", 0), 0))
            s.garden = _normalize_garden(d.get("garden", []) or [])
            raw_best = d.get("best_survival", {}) or {}
            if isinstance(raw_best, dict):
                s.best_survival = {str(k): _to_int(v, 0) for k, v in raw_best.items()}
            s.keys = max(0, _to_int(d.get("keys", 0), 0))
            s.keys_earned_from_stars = max(
                0, _to_int(d.get("keys_earned_from_stars", 0), 0))
            # 读档即迁移到 version 3；真正的落盘等下一次 save。
            s.version = max(SAVE_VERSION, _to_int(d.get("version", 2), 2))
            # 旧存档没有钥匙字段：按已有星数补记账（不写盘，等下一次 save 落盘）
            s.sync_keys_from_stars(save=False)
            return s
        except Exception:
            return cls()

    def save(self):
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump({"completed": self.completed,
                           "unlocked_worlds": self.unlocked_worlds,
                           "coins": self.coins,
                           "settings": self.settings,
                           "stars": self.stars,
                           "unlocked_plants": self.unlocked_plants,
                           "plantfood": self.plantfood,
                           "garden": self.garden,
                           "best_survival": self.best_survival,
                           "keys": self.keys,
                           "keys_earned_from_stars": self.keys_earned_from_stars,
                           "version": self.version}, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    # ------------------------------------------------------------ 关卡
    def is_completed(self, world: str, index: int) -> bool:
        return f"{world}:{index}" in self.completed

    def complete(self, world: str, index: int):
        key = f"{world}:{index}"
        if key not in self.completed:
            self.completed.append(key)
            self.save()

    def unlocked(self, world: str) -> bool:
        return world in self.unlocked_worlds

    def unlock(self, world: str):
        if world not in self.unlocked_worlds:
            self.unlocked_worlds.append(world)
            self.save()

    # ------------------------------------------------------------ 星章
    def stars_for(self, world: str, index: int) -> list[int]:
        val = self.stars.get(f"{world}:{index}") or []
        return [int(x) for x in (list(val) + [0, 0, 0])[:MAX_STARS]]

    def set_stars(self, world: str, index: int, earned: list[bool]):
        key = f"{world}:{index}"
        old = self.stars_for(world, index)
        new = [max(old[i], 1 if (i < len(earned) and earned[i]) else 0)
               for i in range(MAX_STARS)]
        self.stars[key] = new
        self.sync_keys_from_stars(save=False)
        self.save()
        return new

    def total_stars(self) -> int:
        return sum(sum(v) for v in self.stars.values())

    # ------------------------------------------------------------ 钥匙
    def add_keys(self, amount: int) -> int:
        """增加钥匙，返回当前数量。"""
        amount = int(amount)
        if amount > 0:
            self.keys += amount
            self.save()
        return self.keys

    def spend_keys(self, amount: int) -> bool:
        """消耗钥匙；数量不足或为负时返回 False。"""
        amount = int(amount)
        if amount < 0 or self.keys < amount:
            return False
        self.keys -= amount
        self.save()
        return True

    def sync_keys_from_stars(self, save: bool = True) -> int:
        """按累计星数补发钥匙，返回本次补发数量。

        ``keys_earned_from_stars`` 记录“已因星数获得多少把”，
        因此重复调用、读档、重复领奖都不会重复发钥匙。
        """
        earned = max(0, self.total_stars()) // max(1, self.STARS_PER_KEY)
        due = max(0, int(earned) - int(self.keys_earned_from_stars))
        if due <= 0:
            return 0
        self.keys_earned_from_stars = int(earned)
        self.keys += due
        if save:
            self.save()
        return due

    # ------------------------------------------------------------ 金币 / 商店
    def add_coins(self, amount: int):
        self.coins = max(0, int(self.coins) + int(amount))
        self.save()

    def spend_coins(self, amount: int) -> bool:
        amount = int(amount)
        if amount < 0 or self.coins < amount:
            return False
        self.coins -= amount
        self.save()
        return True

    def owns_plant(self, plant_id: str) -> bool:
        return plant_id in self.unlocked_plants

    def unlock_plant(self, plant_id: str):
        if plant_id not in self.unlocked_plants:
            self.unlocked_plants.append(plant_id)
            self.save()

    # ------------------------------------------------------------ 花园
    def garden_slot(self, slot: int) -> dict | None:
        for g in self.garden:
            if isinstance(g, dict) and _to_int(g.get("slot", -1), -1) == int(slot):
                return g
        return None

    def garden_stage(self, entry: dict | None, now: int | None = None) -> int:
        """不写盘的阶段查询；entry 为空返回 -1。"""
        if not isinstance(entry, dict):
            return -1
        now = int(time.time()) if now is None else int(now)
        planted = _to_int(entry.get("planted", now), now)
        ready = _to_int(entry.get("ready", planted), planted)
        return _stage_for(planted, ready, now)

    def garden_refresh(self, now: int | None = None, save: bool = True) -> int:
        """推进所有花盆的 stage；返回发生变化的盆数。"""
        now = int(time.time()) if now is None else int(now)
        changed = 0
        for entry in self.garden:
            if not isinstance(entry, dict):
                continue
            stage = _stage_for(_to_int(entry.get("planted", now), now),
                               _to_int(entry.get("ready", now), now), now)
            if _to_int(entry.get("stage", -1), -1) != stage:
                entry["stage"] = stage
                changed += 1
        if changed and save:
            self.save()
        return changed

    def garden_plant(self, slot: int, plant_id: str,
                     grow_seconds: float = GARDEN_DEFAULT_GROW) -> dict:
        now = int(time.time())
        grow = max(1, _to_int(grow_seconds, GARDEN_DEFAULT_GROW))
        self.garden = [g for g in self.garden
                       if not isinstance(g, dict)
                       or _to_int(g.get("slot", -1), -1) != int(slot)]
        entry = {"slot": int(slot), "plant": str(plant_id), "planted": now,
                 "ready": now + grow, "stage": 0,
                 "last_water": 0, "watered": 0}
        self.garden.append(entry)
        self.garden.sort(key=lambda g: _to_int(g.get("slot", 0), 0))
        self.save()
        return entry

    def garden_water(self, slot: int, cost: int = 0,
                     reduce_seconds: int = 0, max_waters: int = 5,
                     now: int | None = None) -> dict:
        """给花盆浇水：扣金币、缩短成熟时间。返回结果字典。"""
        now = int(time.time()) if now is None else int(now)
        entry = self.garden_slot(slot)
        if entry is None:
            return {"ok": False, "reason": "empty", "message": "花盆是空的"}
        if now >= _to_int(entry.get("ready", 0), 0):
            return {"ok": False, "reason": "mature", "message": "已经成熟了"}
        watered = _to_int(entry.get("watered", 0), 0)
        if watered >= int(max_waters):
            return {"ok": False, "reason": "max", "message": "浇水次数已用完"}
        cost = max(0, int(cost))
        if cost > 0 and self.coins < cost:
            return {"ok": False, "reason": "coins", "message": "金币不足",
                    "need": cost - self.coins}
        reduce = max(1, _to_int(reduce_seconds, 0))
        ready = _to_int(entry.get("ready", now + reduce), now + reduce)
        self.coins = max(0, self.coins - cost)
        entry["ready"] = max(now, ready - reduce)
        entry["last_water"] = now
        entry["watered"] = watered + 1
        entry["stage"] = _stage_for(_to_int(entry.get("planted", now), now),
                                    entry["ready"], now)
        self.save()
        return {"ok": True, "cost": cost, "watered": entry["watered"],
                "ready": entry["ready"], "mature": entry["ready"] <= now}

    def garden_harvest(self, slot: int, now: int | None = None) -> str | None:
        """成熟后收获，返回植物 id；未成熟/空盆返回 None。"""
        now = int(time.time()) if now is None else int(now)
        g = self.garden_slot(slot)
        if not g or _to_int(g.get("ready", 0), 0) > now:
            return None
        plant = str(g.get("plant", ""))
        self.garden = [x for x in self.garden
                       if not isinstance(x, dict)
                       or _to_int(x.get("slot", -1), -1) != int(slot)]
        self.save()
        return plant or None

    def garden_take(self, slot: int) -> dict | None:
        """无条件取走一盆（用于收获前读取奖励属性）。"""
        g = self.garden_slot(slot)
        if g is None:
            return None
        self.garden = [x for x in self.garden
                       if not isinstance(x, dict)
                       or _to_int(x.get("slot", -1), -1) != int(slot)]
        self.save()
        return dict(g)

    def garden_remove(self, slot: int) -> dict | None:
        """铲除：无条件移除并返回原条目。"""
        return self.garden_take(slot)
