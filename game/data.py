"""内容数据加载：plants / zombies / worlds / levels / almanac。

所有 Loader 必须容错：文件缺失时返回空集合，不让游戏崩溃。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import CONTENT_DIR


def _load_json(path: Path, default: Any):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


@dataclass
class PlantDef:
    id: str
    name_zh: str = ""
    name_en: str = ""
    cost: int = 100
    cooldown: float = 5.0
    hp: int = 300
    family: str = ""
    art: str = ""
    behavior: str = "shoot"
    damage: float = 20
    interval: float = 1.4
    projectile: str = "pea"
    rows: list[int] = field(default_factory=lambda: [0])
    pierce: bool = False
    tags: list[str] = field(default_factory=list)
    desc_zh: str = ""
    almanac_no: int = 0
    extra: dict = field(default_factory=dict)
    # 便捷派生字段
    sun_value: int = 25
    sun_interval: float = 24.0
    splash: float = 0.0
    slow: float = 0.0
    melee_range: float = 1.0
    delay: float = 0.0
    plantfood: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "PlantDef":
        known = {f for f in cls.__dataclass_fields__ if f != "extra"}
        kw = {k: v for k, v in d.items() if k in known}
        extra = {k: v for k, v in d.items() if k not in known}
        return cls(extra=extra, **kw)


@dataclass
class ZombieDef:
    id: str
    name_zh: str = ""
    name_en: str = ""
    hp: int = 190
    speed: float = 0.185
    eat_dps: float = 100.0
    armor: list[dict] = field(default_factory=list)
    behavior: str = "walk"
    art: str = ""
    armature: str | None = None
    cost: int = 100
    desc_zh: str = ""
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "ZombieDef":
        known = {f for f in cls.__dataclass_fields__ if f != "extra"}
        kw = {k: v for k, v in d.items() if k in known}
        extra = {k: v for k, v in d.items() if k not in known}
        return cls(extra=extra, **kw)


@dataclass
class WorldDef:
    id: str
    name_zh: str = ""
    name_en: str = ""
    order: int = 1
    levels: int = 10
    map: str = ""
    lawn: str = ""
    unlock_after: str | None = None
    desc_zh: str = ""
    bg_tint: tuple = (255, 255, 255)
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "WorldDef":
        known = {f for f in cls.__dataclass_fields__ if f != "extra"}
        kw = {k: v for k, v in d.items() if k in known}
        if isinstance(kw.get("bg_tint"), list):
            kw["bg_tint"] = tuple(kw["bg_tint"])
        extra = {k: v for k, v in d.items() if k not in known}
        nested = extra.pop("extra", None)
        if isinstance(nested, dict):
            extra = {**nested, **extra}
        return cls(extra=extra, **kw)


@dataclass
class ZombieSpawn:
    type: str
    row: int | None = None
    rows: list[int] | None = None


@dataclass
class Wave:
    delay: float = 18.0
    flag: bool = False
    zombies: list[ZombieSpawn] = field(default_factory=list)


@dataclass
class LevelDef:
    id: str
    world: str = ""
    index: int = 1
    title: str = ""
    sun: int = 250
    deck: list[str] = field(default_factory=list)
    waves: list[Wave] = field(default_factory=list)
    flags: int = 1
    seed_bank: int = 6
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "LevelDef":
        known = {f for f in cls.__dataclass_fields__ if f != "extra"}
        kw = {k: v for k, v in d.items() if k in known}
        extra = {k: v for k, v in d.items() if k not in known}
        nested = extra.pop("extra", None)
        if isinstance(nested, dict):
            extra = {**nested, **extra}
        waves = []
        for w in kw.get("waves", []) or []:
            zs = []
            for z in w.get("zombies", []) or []:
                if isinstance(z, str):
                    zs.append(ZombieSpawn(type=z))
                else:
                    zs.append(ZombieSpawn(type=z.get("type", "basic"),
                                          row=z.get("row"), rows=z.get("rows")))
            waves.append(Wave(delay=float(w.get("delay", 18.0)),
                              flag=bool(w.get("flag", False)), zombies=zs))
        kw["waves"] = waves
        return cls(extra=extra, **kw)


class GameData:
    """全部内容数据的只读访问入口。"""

    def __init__(self):
        self.plants: dict[str, PlantDef] = {}
        self.zombies: dict[str, ZombieDef] = {}
        self.worlds: list[WorldDef] = []
        self.almanac: dict = {"plants": {}, "zombies": {}}
        self._levels: dict[str, list[LevelDef]] = {}
        self.load()

    def load(self):
        self.plants = {}
        for d in _load_json(CONTENT_DIR / "plants.json", []) or []:
            try:
                p = PlantDef.from_dict(d)
                self.plants[p.id] = p
            except Exception:
                continue
        self.zombies = {}
        for d in _load_json(CONTENT_DIR / "zombies.json", []) or []:
            try:
                z = ZombieDef.from_dict(d)
                self.zombies[z.id] = z
            except Exception:
                continue
        self.worlds = []
        for d in _load_json(CONTENT_DIR / "worlds.json", []) or []:
            try:
                self.worlds.append(WorldDef.from_dict(d))
            except Exception:
                continue
        self.worlds.sort(key=lambda w: w.order)
        self.almanac = _load_json(CONTENT_DIR / "almanac.json", {"plants": {}, "zombies": {}})

    def world(self, world_id: str) -> WorldDef | None:
        for w in self.worlds:
            if w.id == world_id:
                return w
        return None

    def levels(self, world_id: str) -> list[LevelDef]:
        if world_id in self._levels:
            return self._levels[world_id]
        out: list[LevelDef] = []
        lv_dir = CONTENT_DIR / "levels"
        if lv_dir.is_dir():
            for p in sorted(lv_dir.glob(f"{world_id}_*.json")):
                d = _load_json(p, None)
                if d:
                    try:
                        out.append(LevelDef.from_dict(d))
                    except Exception:
                        continue
        out.sort(key=lambda lv: lv.index)
        self._levels[world_id] = out
        return out

    def level(self, world_id: str, index: int) -> LevelDef | None:
        for lv in self.levels(world_id):
            if lv.index == index:
                return lv
        return None
