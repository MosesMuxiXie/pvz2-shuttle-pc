# -*- coding: utf-8 -*-
"""Rebuild game content from the SHUTTLE OBB (18-world / full-level edition).

Reads the RTON packages extracted from the OBB (work/obb_packages) and writes
authentic levels for the 18 worlds shipped by the game, plus refreshed plant
stats and the 26.10.1 plant "Dark Matter Dragonfruit" (voiddragon).

Compared with the old 12-world / 10-level build this version:
  * maps the six extra worlds (iceage / kongfu / dino / eighties / modern / sky);
  * keeps *every* ordinary level of a world (not just the first ten);
  * excludes vasebreaker / beghouled / bowling levels but counts them;
  * preserves boss levels (``extra.boss``) and night levels (``extra.night``);
  * writes the three-star definitions for every level it produces;
  * preserves the handcrafted "plantagenet" levels (world 18).

Usage: python tools/obb_build_content.py [--dry-run]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG_DIR = ROOT.parent / "work" / "obb_packages"
CONTENT = ROOT / "content"
LEVELS = CONTENT / "levels"

# The order must match content/worlds.json.
WORLD_ORDER = [
    "frontyard", "egypt", "pirate", "cowboy", "future", "dark", "beach",
    "lostcity", "iceage", "kongfu", "dino", "eighties", "modern", "sky",
    "chinesegarden", "losantosvice", "lunarrainbowmarket", "plantagenet",
]

# Worlds generated from the OBB.  "plantagenet" is handcrafted and preserved.
STAGE_WORLDS = [
    # The old frontyard mapping used ModernStage, which now belongs to the
    # "modern" world; the house / front-lawn stages are the real frontyard.
    ("frontyard", ["DayStage", "NightStage", "FrontLawnStage"]),
    ("egypt", ["EgyptStage"]),
    ("pirate", ["PirateStage"]),
    ("cowboy", ["WestStage"]),
    ("future", ["FutureStage"]),
    ("dark", ["DarkStage"]),
    ("beach", ["BeachStage"]),
    ("lostcity", ["LostCityStage"]),
    ("iceage", ["IceageStage"]),
    ("kongfu", ["KongfuStage", "KongfuUBStage", "KongfuDMGStage"]),
    ("dino", ["DinoStage"]),
    ("eighties", ["EightiesStage"]),
    ("modern", ["ModernStage"]),
    ("sky", ["SkyCityStage", "SkyCityLostCityStage"]),
    ("chinesegarden", ["ChineseGardenStage", "ChineseGardenUBStage", "ChineseGardenDMGStage"]),
    ("losantosvice", ["GTAStage", "GTAUBStage", "GTADMGStage"]),
    ("lunarrainbowmarket", ["MarketNightsStage", "MarketNightsUBStage", "MarketNightsDMGStage"]),
]

PRESERVE_WORLDS = ["plantagenet"]

WORLD_BASE = {
    "frontyard": "basic",
    "egypt": "mummy",
    "pirate": "pirate",
    "cowboy": "cowboy",
    "future": "future",
    "dark": "dark",
    "beach": "beach",
    "lostcity": "lostcity",
    "iceage": "iceage",
    "kongfu": "kongfu",
    "dino": "basic",
    "eighties": "eighties",
    "modern": "basic",
    "sky": "beach",
    "chinesegarden": "garden_zombie",
    "losantosvice": "gang_zombie",
    "lunarrainbowmarket": "market_clockwork",
    "plantagenet": "royal_zombie",
}
WORLD_ARMOR1 = {
    "frontyard": "conehead",
    "egypt": "mummy_armor1",
    "pirate": "pirate_armor1",
    "cowboy": "cowboy_armor1",
    "future": "future_armor1",
    "dark": "dark_armor1",
    "beach": "beach",
    "lostcity": "lostcity",
    "iceage": "iceage",
    "kongfu": "kongfu",
    "dino": "conehead",
    "eighties": "eighties",
    "modern": "conehead",
    "sky": "beach",
    "chinesegarden": "garden_cone",
    "losantosvice": "gang_cone",
    "lunarrainbowmarket": "market_armor1",
    "plantagenet": "royal_noblewoman",
}
WORLD_ARMOR2 = {
    "frontyard": "buckethead",
    "egypt": "mummy_armor2",
    "pirate": "buckethead",
    "cowboy": "buckethead",
    "future": "buckethead",
    "dark": "buckethead",
    "beach": "buckethead",
    "lostcity": "buckethead",
    "iceage": "buckethead",
    "kongfu": "buckethead",
    "dino": "buckethead",
    "eighties": "buckethead",
    "modern": "buckethead",
    "sky": "buckethead",
    "chinesegarden": "garden_bucket",
    "losantosvice": "gang_bucket",
    "lunarrainbowmarket": "market_armor2",
    "plantagenet": "royal_winetasting",
}

WORLD_ZH = {
    "frontyard": "前院",
    "egypt": "神秘埃及",
    "pirate": "海盗港湾",
    "cowboy": "狂野西部",
    "future": "未来世界",
    "dark": "黑暗时代",
    "beach": "神秘海滩",
    "lostcity": "失落之城",
    "iceage": "冰河世界",
    "kongfu": "功夫世界",
    "dino": "恐龙危机",
    "eighties": "摇滚年代",
    "modern": "摩登世界",
    "sky": "天空之城",
    "chinesegarden": "中国园林",
    "losantosvice": "洛城风云",
    "lunarrainbowmarket": "月虹市场",
    "plantagenet": "王朝",
}

DEFAULT_DECKS = {
    "frontyard": ["sunflower", "peashooter", "wallnut", "potatomine"],
    "egypt": ["sunflower", "peashooter", "wallnut", "bloomerang"],
    "pirate": ["sunflower", "peashooter", "wallnut", "bloomerang"],
    "cowboy": ["sunflower", "peashooter", "wallnut", "bloomerang"],
    "future": ["sunflower", "peashooter", "wallnut", "bloomerang"],
    "dark": ["sunflower", "peashooter", "wallnut", "bloomerang"],
    "beach": ["sunflower", "peashooter", "wallnut", "bloomerang"],
    "lostcity": ["sunflower", "peashooter", "wallnut", "bloomerang"],
    "iceage": ["sunflower", "peashooter", "wallnut", "iceburg"],
    "kongfu": ["sunflower", "peashooter", "wallnut", "bonkchoy"],
    "dino": ["sunflower", "peashooter", "wallnut", "bonkchoy"],
    "eighties": ["sunflower", "peashooter", "wallnut", "bonkchoy"],
    "modern": ["sunflower", "peashooter", "wallnut", "bloomerang"],
    "sky": ["sunflower", "peashooter", "wallnut", "bloomerang"],
    "chinesegarden": ["sunflower", "gardenia", "elderbarrier", "torpedofruit"],
    "losantosvice": ["sunflower", "peashooter", "birdofparadise", "yuccaguardian"],
    "lunarrainbowmarket": ["sunflower", "begonia", "potatochip", "missiletoast"],
    "plantagenet": ["sunflower", "peashooter", "iris", "olivewood"],
}

PLANT_ALIAS = {
    "cherry_bomb": "cherry_bomb",
    "iceburg": "iceburg",
    "twinsunflower": "twinsunflower",
    "homingthistle": "homingthistle",
    "umbrellaleaf": "umbrellaleaf",
    "magnifyinggrass": "magnifyinggrass",
    "bonkchoy": "bonkchoy",
    "potatomine": "potatomine",
    "snowpea": "snowpea",
    "cabbagepult": "cabbagepult",
    "kernelpult": "kernelpult",
    "melonpult": "melonpult",
    "wintermelon": "wintermelon",
    "spikeweed": "spikeweed",
    "threepeater": "threepeater",
    "splitpea": "splitpea",
    "gatling": "gatling",
    "tallnut": "tallnut",
    "starfruit": "starfruit",
    "fumeshroom": "fumeshroom",
    "torchwood": "torchwood",
    "jalapeno": "jalapeno",
    "squash": "squash",
    "chomper": "chomper",
    "bloomerang": "bloomerang",
    "repeater": "repeater",
    "sunflower": "sunflower",
    "peashooter": "peashooter",
    "wallnut": "wallnut",
    "sunshroom": "sunshroom",
    "gardenia": "gardenia",
    "jasmine": "jasmine",
    "torpedofruit": "torpedofruit",
    "seapotatomine": "seapotatomine",
    "elderbarrier": "elderbarrier",
    "birdofparadise": "birdofparadise",
    "poppinpoppies": "poppinpoppies",
    "yuccaguardian": "yuccaguardian",
    "begonia": "begonia",
    "potatochip": "potatochip",
    "missiletoast": "missiletoast",
}

CJK = re.compile(r"[\u4e00-\u9fff]")
SPECIAL_FLAGS = ("IsVasebreaker", "IsBeghouled", "IsBowling")
BOSS_RE = re.compile(r"zomboss|bossstage|bossicon", re.I)


def load_objects(pattern: str):
    out = []
    for path in sorted(glob.glob(str(PKG_DIR / pattern))):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        for obj in data.get("objects", []):
            out.append((Path(path).name, obj))
    return out


def load_all_levels():
    """Return [(package_file_name, level_object)] for every LevelDefinition."""
    return [(name, obj) for name, obj in load_objects("*LevelDefinition.json")
            if obj.get("objclass") == "LevelDefinition"]


def collect_strings():
    """Return (zh_table, en_table) merged from all LawnStringsData packages."""
    zh: dict[str, str] = {}
    en: dict[str, str] = {}
    for name, obj in load_objects("*LawnStringsData.json"):
        values = (obj.get("objdata") or {}).get("LocStringValues") or []
        pairs = max(1, len(values) // 2)
        cjk = sum(1 for v in values if isinstance(v, str) and CJK.search(v))
        is_zh = cjk / pairs > 0.2
        target = zh if is_zh else en
        for i in range(0, len(values) - 1, 2):
            key, val = values[i], values[i + 1]
            if isinstance(key, str) and isinstance(val, str):
                target.setdefault(key, val)
    return zh, en


def localize(key: str | None, zh: dict[str, str], en: dict[str, str]) -> str:
    if not key:
        return ""
    k = str(key).strip()
    if k.startswith("["):
        k = k.strip("[]")
    for table in (zh, en):
        if k in table:
            return table[k]
    return ""


def resolve_rtid_alias(value) -> str:
    m = re.search(r"RTID\(([^@]+)@", str(value or ""))
    return m.group(1) if m else ""


def is_boss_level(modules: list[str]) -> bool:
    return any(BOSS_RE.search(resolve_rtid_alias(m) or "") for m in modules)


def is_night_level(stage: str, od: dict, modules: list[str]) -> bool:
    if "night" in stage.lower():
        return True
    key = str(od.get("Name") or "").upper()
    # TOWER_NIGHT_LEVEL_NAME is a night level; EPIC_QUEST_NIGHTCAP is a plant.
    if re.search(r"(?:^|_)NIGHTS?(?:_|$)", key):
        return True
    for m in modules:
        alias = resolve_rtid_alias(m).lower()
        if alias == "marketnight" or alias == "heiannight" or alias.startswith("night"):
            return True
    return False


SPECIAL_ZOMBIES = {
    "chinesegarden": [
        ("umbrella", "garden_umbrella"),
        ("poet", "garden_poet"),
        ("literati", "garden_poet"),
        ("cujustar", "garden_cuju"),
        ("cuju", "garden_cuju"),
        ("taoist", "garden_imp"),
        ("koi", "garden_imp"),
        ("imp", "garden_imp"),
        ("drummer", "garden_drummer"),
        ("flutist", "garden_drummer"),
        ("fengshui", "garden_drummer"),
        ("scientist", "garden_poet"),
        ("gargantuar", "garden_gargantuar"),
    ],
    "losantosvice": [
        ("molotov", "gang_molotov"),
        ("loudmouth", "gang_ozloc"),
        ("ozloc", "gang_ozloc"),
        ("carl", "gang_carl"),
        ("imp", "gang_imp"),
        ("gargantuar", "gang_gargantuar"),
    ],
    "lunarrainbowmarket": [
        ("trapeze", "market_trapeze"),
        ("clockwork", "market_clockwork"),
        ("mechanic", "market_mechanic"),
        ("cannon", "market_mechanic"),
        ("poet", "garden_poet"),
    ],
    # --- 18-world expansion (only existing zombie ids can be used) ---
    "iceage": [
        ("dodo", "pole_vaulter"),
        ("weasel", "iceage"),
        ("gargantuar", "gargantuar"),
        ("imp", "iceage"),
    ],
    "kongfu": [
        ("gargantuar", "gargantuar"),
        ("imp", "kongfu"),
        ("monk", "kongfu"),
        ("torch", "kongfu"),
        ("qigong", "kongfu"),
    ],
    "dino": [
        ("bully", "football"),
        ("gargantuar", "gargantuar"),
        ("imp", "basic"),
    ],
    "eighties": [
        ("popsinger", "eighties"),
        ("gargantuar", "gargantuar"),
        ("imp", "eighties"),
    ],
    "modern": [
        ("newspaper", "newspaper"),
        ("allstar", "football"),
        ("gargantuar", "gargantuar"),
        ("imp", "basic"),
    ],
    "sky": [
        ("plane", "beach"),
        ("gargantuar", "gargantuar"),
        ("imp", "basic"),
    ],
}

# Cross-world aliases that can be resolved to one of the 55 existing zombies.
# Longest / most specific prefixes first.
GLOBAL_PREFIX = [
    ("poncho_plate", "cowboy_armor1"),
    ("poncho", "cowboy"),
    ("prospector", "cowboy"),
    ("piano", "cowboy"),
    ("chicken_farmer", "cowboy"),
    ("west_bullrider", "cowboy"),
    ("west_bull", "cowboy"),
    ("barrelroller", "pirate"),
    ("pelican", "pirate"),
    ("seagull", "pirate"),
    ("swashbuckler", "pirate_armor1"),
    ("cannon", "pirate"),
    ("skycity", "beach"),
    ("invisible_plane", "beach"),
    ("air_missile", "beach"),
    ("iceage", "iceage"),
    ("kongfu", "kongfu"),
    ("renai", "kongfu"),
    ("eighties", "eighties"),
    ("dino", "basic"),
    ("modern", "basic"),
    ("tutorial", "basic"),
    ("tomb_raiser", "mummy"),
    ("cleopatra", "mummy_armor1"),
    ("explorer", "mummy"),
    ("pharaoh", "mummy"),
    ("mummy", "mummy"),
    ("camel", "mummy"),
    ("pirate", "pirate"),
    ("cowboy", "cowboy"),
    ("future", "future"),
    ("dark", "dark"),
    ("beach", "beach"),
    ("lostcity", "lostcity"),
    ("gang", "gang_zombie"),
    ("market", "market_clockwork"),
    ("royal", "royal_zombie"),
    ("garden", "garden_zombie"),
]
GLOBAL_EXACT = {"ra": "mummy_armor2"}
NEW_WORLDS = {"iceage", "kongfu", "dino", "eighties", "modern", "sky"}
UNMAPPED: dict[str, Counter] = {}


def map_zombie(alias: str, world: str) -> str:
    a = str(alias or "").lower()
    base = WORLD_BASE.get(world, "basic")
    for needle, zid in SPECIAL_ZOMBIES.get(world, []):
        if needle in a:
            return zid
    if "gargantuar" in a or "gargantur" in a:
        return "gargantuar"
    if "football" in a or "mech" in a or "allstar" in a:
        return "football"
    if "newspaper" in a:
        return "newspaper"
    if "flag" in a:
        return "flag"
    if "pole" in a or "vaulter" in a or "dodo" in a:
        return "pole_vaulter"
    if any(k in a for k in ("armor4", "armor3", "armor2", "bucket", "helmet2", "toughness2", "toughness3")):
        return WORLD_ARMOR2.get(world, "buckethead")
    if any(k in a for k in ("armor1", "cone", "toughness1", "helmet", "veteran")):
        return WORLD_ARMOR1.get(world, "conehead")
    if a in GLOBAL_EXACT:
        return GLOBAL_EXACT[a]
    for prefix, zid in GLOBAL_PREFIX:
        if a == prefix or a.startswith(prefix):
            return zid
    if a and world in NEW_WORLDS:
        UNMAPPED.setdefault(world, Counter())[alias] += 1
    return base


NAME_CANON = {
    "frontyard": "YOURHOUSE_CHAPTER1_LEVEL_NAME",
    "egypt": "EGYPT_LEVEL_NAME",
    "pirate": "PIRATE_LEVEL_NAME",
    "cowboy": "WEST_LEVEL_NAME",
    "future": "FUTURE_LEVEL_NAME",
    "dark": "DARKAGES_LEVEL_NAME",
    "beach": "BEACH_LEVEL_NAME",
    "lostcity": "LOSTCITY_LEVEL_NAME",
    "iceage": "ICEAGE_LEVEL_NAME",
    "kongfu": "KONGFU_LEVEL_NAME",
    "dino": "DINO_LEVEL_NAME",
    "eighties": "EIGHTIES_LEVEL_NAME",
    "modern": "MODERN_LEVEL_NAME",
    "sky": "SKYCITY_LEVEL_NAME",
    "chinesegarden": "CHINESEGARDEN_LEVEL_NAME",
    "losantosvice": "GTA_LEVEL_NAME",
    "lunarrainbowmarket": "LUNARRAINBOWMARKET_NIGHT_LEVEL_NAME",
    "plantagenet": "PLANTAGENET_LEVEL_NAME",
}


def _name_score(key: str | None, world: str) -> int:
    k = str(key or "").strip("[]").upper()
    if k == NAME_CANON.get(world):
        return 0
    if any(tag in k for tag in ("LOD_", "LTE_", "VASEBREAKER", "EPIC_QUEST", "DANGER_ROOM", "TARAXACUM", "MINIGAME")):
        return 3
    if "LEVEL_NAME" in k:
        return 1
    return 2


def pick_levels(all_levels, stages: list[str], world: str):
    """Return (selected_rows, stage_stats, special_counts) for one world."""
    picked: list[tuple] = []
    stats: dict[str, dict] = {}
    specials: dict[str, dict] = {}
    for stage in stages:
        st = {"total": 0, "normal": 0, "boss": 0, "night": 0, "special": 0,
              "vase": 0, "beghouled": 0, "bowling": 0, "selected": 0}
        rows = []
        for name, obj in all_levels:
            od = obj.get("objdata") or {}
            if resolve_rtid_alias(od.get("StageModule")) != stage:
                continue
            st["total"] += 1
            mods = [str(m) for m in (od.get("Modules") or [])]
            if is_night_level(stage, od, mods):
                st["night"] += 1
            flags = [f for f in SPECIAL_FLAGS if od.get(f)]
            if flags:
                st["special"] += 1
                for f in flags:
                    key = {"IsVasebreaker": "vase", "IsBeghouled": "beghouled",
                           "IsBowling": "bowling"}[f]
                    st[key] += 1
                specials.setdefault(stage, Counter())["+".join(flags)] += 1
                continue
            has_nw = any("NewWaves@CurrentLevel" in m for m in mods)
            has_sb = any("SeedBank@CurrentLevel" in m for m in mods)
            boss = is_boss_level(mods)
            if has_nw and has_sb:
                st["normal"] += 1
            if boss:
                st["boss"] += 1
            # Boss levels may lack NewWaves / SeedBank but are still playable
            # as ordinary levels (the engine ignores the Zomboss modules).
            if (has_nw and has_sb) or boss:
                rows.append((_name_score(od.get("Name"), world),
                             int(od.get("LevelNumber") or 9999), name, obj))
        rows.sort(key=lambda t: (t[0], t[1], t[2]))
        st["selected"] = len(rows)
        stats[stage] = st
        picked.extend(rows)
    return picked, stats, specials


def _level_title(od: dict, zh, en) -> str:
    level_number = int(od.get("LevelNumber") or 0)
    raw = localize(od.get("Name"), zh, en)
    if raw:
        raw = raw.replace("{LEVEL_NUMBER}", str(level_number))
        raw = raw.replace("{WORLD_NAME}", "")
        raw = re.sub(r"\s+", " ", raw).strip(" -_")
    return raw or (f"第 {level_number} 关" if level_number else "")


def convert_level(world: str, index: int, name: str, obj: dict, zh, en) -> dict | None:
    od = obj.get("objdata") or {}
    stage = resolve_rtid_alias(od.get("StageModule"))
    mods = [str(m) for m in (od.get("Modules") or [])]
    boss = is_boss_level(mods)
    night = is_night_level(stage, od, mods)

    pkg_file = PKG_DIR / name
    try:
        with open(pkg_file, encoding="utf-8") as fh:
            pkg = json.load(fh)
    except Exception:
        return None
    by_alias = {}
    for o in pkg.get("objects", []):
        for a in o.get("aliases") or []:
            by_alias.setdefault(a, o)

    level_number = int(od.get("LevelNumber") or index)
    title = _level_title(od, zh, en) or f"第 {level_number} 关"

    # deck
    deck = []
    seed = by_alias.get("SeedBank")
    if seed:
        for item in (seed.get("objdata") or {}).get("PresetPlantList") or []:
            pid = str(item.get("PlantType") or "").strip()
            mapped = PLANT_ALIAS.get(pid)
            if mapped:
                deck.append(mapped)
    deck = list(dict.fromkeys(deck))
    if len(deck) < 3:
        deck = DEFAULT_DECKS.get(world, ["sunflower", "peashooter", "wallnut"])[:]

    # waves
    wmp = by_alias.get("WaveManagerProps")
    waves_out = []
    flag_interval = 10
    wave_zombie_aliases: list[str] = []
    if wmp:
        wod = wmp.get("objdata") or {}
        flag_interval = max(3, int(wod.get("FlagWaveInterval") or 10))
        raw_waves = wod.get("Waves") or []
        for wi, wave_refs in enumerate(raw_waves):
            spawn = None
            for ref in wave_refs:
                cand = by_alias.get(resolve_rtid_alias(ref))
                if cand and cand.get("objclass") == "SpawnZombiesJitteredWaveActionProps":
                    spawn = cand
                    break
            entries = []
            if spawn:
                for zi, z in enumerate((spawn.get("objdata") or {}).get("Zombies") or []):
                    raw_alias = resolve_rtid_alias(z.get("Type"))
                    wave_zombie_aliases.append(raw_alias)
                    zid = map_zombie(raw_alias, world)
                    try:
                        row = int(z.get("Row"))
                    except Exception:
                        row = zi % 5
                    if not (0 <= row < 5):
                        row = zi % 5
                    entries.append({"type": zid, "row": row})
            if not entries:
                if wi == len(raw_waves) - 1:
                    entries = [{"type": WORLD_BASE[world], "row": 2}]
                else:
                    continue
            entries = entries[:14]
            flag = ((wi + 1) % flag_interval == 0) or (wi == len(raw_waves) - 1)
            delay = 18 if wi == 0 else (24 if flag else 20)
            waves_out.append({"delay": delay, "flag": flag, "zombies": entries})
    if not waves_out:
        return None

    extra = {
        "source": "obb",
        "package": name.replace("_LevelDefinition.json", ""),
        "stage": stage,
        "name_key": od.get("Name"),
        "level_number": level_number,
        "wave_count": len(waves_out),
        "original_waves": len((wmp.get("objdata") or {}).get("Waves") or []) if wmp else 0,
        "night": night,
    }
    if boss:
        extra["boss"] = True
        extra["boss_zombie"] = _boss_zombie(wave_zombie_aliases, boss=True)

    return {
        "id": f"{world}_{index}",
        "world": world,
        "index": index,
        "title": title,
        "sun": 150 + min(index - 1, 10) * 40,
        "deck": deck,
        "waves": waves_out,
        "flags": sum(1 for w in waves_out if w["flag"]),
        "seed_bank": max(6, len(deck)),
        "extra": extra,
    }


def _boss_zombie(aliases: list[str], boss: bool) -> str | None:
    if not boss:
        return None
    low = [str(a or "").lower() for a in aliases]
    if any("zomboss" in a or a == "boss" for a in low):
        return "zomboss"
    if any("gargantuar" in a for a in low):
        return "gargantuar"
    return "zomboss"


def refresh_plant_stats(plants: list[dict]) -> int:
    stats = {}
    for _, obj in load_objects("*PlantLevelStats.json"):
        if obj.get("objclass") != "PlantLevelStats":
            continue
        alias = (obj.get("aliases") or [""])[0]
        flat = {}
        for entry in (obj.get("objdata") or {}).get("FloatStats") or []:
            vals = entry.get("Values") or []
            if vals:
                flat[entry.get("Name")] = vals[0]
        stats[alias] = flat
    changed = 0
    for plant in plants:
        alias = PLANT_ALIAS.get(plant["id"], plant["id"])
        flat = stats.get(alias) if alias else None
        if not flat:
            continue
        for key, stat in (("cost", "Cost"), ("hp", "Hitpoints"), ("cooldown", "PacketCooldown")):
            val = flat.get(stat)
            if val is None:
                continue
            val = round(val) if key != "hp" else int(round(val))
            if plant.get(key) != val:
                plant[key] = val
                changed += 1
        dmg = flat.get("ActionDamageNormal")
        if dmg is not None and plant.get("damage") != int(round(dmg)):
            plant["damage"] = int(round(dmg))
            changed += 1
    return changed


VOID_DRAGON = {
    "id": "voiddragon",
    "name_zh": "暗物质火龙果",
    "name_en": "Dark Matter Dragonfruit",
    "cost": 250,
    "cooldown": 10,
    "hp": 300,
    "family": "Dragonfruit",
    "art": "plants/DarkMatterDragonfruitPLANT",
    "behavior": "shoot",
    "damage": 40,
    "interval": 1.6,
    "projectile": "pea",
    "rows": [0],
    "pierce": 0,
    "tags": ["plant", "dark", "event"],
    "desc_zh": "来自虚空的暗物质火龙果，以暗物质能量攻击整行僵尸，并有概率触发元素反应。",
    "almanac_no": 31,
    "plantfood": "",
}


def synth_level(world: str, index: int, name: str, obj: dict, zh, en) -> dict:
    """Fallback level for packages whose wave module is missing in this build."""
    od = obj.get("objdata") or {}
    stage = resolve_rtid_alias(od.get("StageModule"))
    mods = [str(m) for m in (od.get("Modules") or [])]
    boss = is_boss_level(mods)
    night = is_night_level(stage, od, mods)
    base = WORLD_BASE[world]
    arm1 = WORLD_ARMOR1[world]
    waves = []
    for wi in range(8):
        count = min(6, 1 + wi)
        zs = []
        for k in range(count):
            zid = arm1 if (wi >= 4 and k % 3 == 0) else base
            zs.append({"type": zid, "row": (wi * 2 + k) % 5})
        flag = wi == 7
        waves.append({"delay": 18 if wi == 0 else (24 if flag else 20), "flag": flag,
                      "zombies": zs})
    extra = {
        "source": "obb-synth",
        "package": name.replace("_LevelDefinition.json", ""),
        "stage": stage,
        "name_key": od.get("Name"),
        "level_number": int(od.get("LevelNumber") or index),
        "wave_count": len(waves),
        "original_waves": 0,
        "night": night,
    }
    if boss:
        extra["boss"] = True
        extra["boss_zombie"] = "zomboss"
    return {
        "id": f"{world}_{index}",
        "world": world,
        "index": index,
        "title": _level_title(od, zh, en) or f"{WORLD_ZH.get(world, '')} - 第 {index} 天",
        "sun": 150 + min(index - 1, 10) * 40,
        "deck": DEFAULT_DECKS[world][:],
        "waves": waves,
        "flags": 1,
        "seed_bank": max(6, len(DEFAULT_DECKS[world])),
        "extra": extra,
    }


def _renumber_and_dedupe(rows: list[dict]) -> None:
    """Title numbering: use the level index, then make every title unique."""
    for row in rows:
        t = row["title"]
        nums = list(re.finditer(r"\d+", t))
        if nums:
            last = nums[-1]
            row["title"] = t[:last.start()] + str(row["index"]) + t[last.end():]
    seen = set()
    for row in rows:
        t = row["title"]
        if t in seen:
            base = t
            k = 2
            while t in seen:
                t = f"{base}（{row['index']}-{k}）"
                k += 1
            row["title"] = t
        seen.add(row["title"])


def make_stars(level: dict) -> list[dict]:
    total = sum(len(w.get("zombies") or []) for w in level.get("waves") or [])
    kills = max(10, int(round(total * 0.6)))
    return [
        {"type": "beat", "value": 0, "text_zh": "通关"},
        {"type": "mowers", "value": 5, "max": 0, "text_zh": "不损失小推车"},
        {"type": "kill", "value": kills, "count": kills, "text_zh": f"击杀 {kills} 个僵尸"},
    ]


def write_stars(levels_by_world: dict[str, list[dict]]) -> tuple[int, int]:
    path = CONTENT / "stars.json"
    stars = json.load(open(path, encoding="utf-8")) if path.exists() else {}
    ordered: dict[str, list] = {}
    added = 0
    for world in WORLD_ORDER:
        for level in levels_by_world.get(world, []):
            sid = level["id"]
            if sid in stars:
                ordered[sid] = stars[sid]
            else:
                ordered[sid] = make_stars(level)
                added += 1
    for key, value in stars.items():
        if key not in ordered:
            ordered[key] = value
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(ordered, fh, ensure_ascii=False, indent=1)
    return added, len(ordered)


def update_world_level_counts(levels_by_world: dict[str, list[dict]]) -> None:
    path = CONTENT / "worlds.json"
    worlds = json.load(open(path, encoding="utf-8"))
    for world in worlds:
        world["levels"] = len(levels_by_world.get(world.get("id"), []))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(worlds, fh, ensure_ascii=False, indent=1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not PKG_DIR.exists():
        print(f"missing {PKG_DIR}")
        return 1
    zh, en = collect_strings()
    print(f"strings zh={len(zh)} en={len(en)}")

    plants_path = CONTENT / "plants.json"
    almanac_path = CONTENT / "almanac.json"
    plants = json.load(open(plants_path, encoding="utf-8"))
    voiddragon_added = not any(p.get("id") == "voiddragon" for p in plants)
    if voiddragon_added:
        plants.append(dict(VOID_DRAGON))
    changed = refresh_plant_stats(plants)
    # Any plant that exists may appear in an OBB seed bank (identity alias).
    for plant in plants:
        PLANT_ALIAS.setdefault(plant["id"], plant["id"])

    all_levels = load_all_levels()
    print(f"level definitions={len(all_levels)}")
    stage_inventory = Counter(resolve_rtid_alias(((o.get("objdata") or {}).get("StageModule")))
                              for _, o in all_levels)

    built: dict[str, list[dict]] = {}
    stage_stats: dict[str, dict] = {}
    special_counts: dict[str, dict] = {}
    for world, stages in STAGE_WORLDS:
        picked, stats, specials = pick_levels(all_levels, stages, world)
        rows: list[dict] = []
        used = set()
        for _score, _num, name, obj in picked:
            if name in used:
                continue
            used.add(name)
            idx = len(rows) + 1
            level = convert_level(world, idx, name, obj, zh, en)
            if level is None:
                level = synth_level(world, idx, name, obj, zh, en)
            if not level or not level["waves"]:
                continue
            rows.append(level)
        _renumber_and_dedupe(rows)
        built[world] = rows
        stage_stats[world] = stats
        special_counts[world] = {k: dict(v) for k, v in specials.items()}
        boss = sum(1 for r in rows if (r.get("extra") or {}).get("boss"))
        night = sum(1 for r in rows if (r.get("extra") or {}).get("night"))
        print(f"{world:18s} candidates={len(picked):3d} built={len(rows):3d} "
              f"boss={boss:2d} night={night:2d}")

    # Handcrafted worlds (plantagenet) are kept byte-for-byte.
    preserved: dict[str, list[dict]] = {}
    for world in PRESERVE_WORLDS:
        preserved[world] = []
        for path in sorted(LEVELS.glob(f"{world}_*.json")):
            try:
                preserved[world].append(json.load(open(path, encoding="utf-8")))
            except Exception:
                pass
        print(f"{world:18s} preserved={len(preserved[world]):3d}")

    levels_by_world: dict[str, list[dict]] = {}
    for world in WORLD_ORDER:
        levels_by_world[world] = built.get(world) or preserved.get(world) or []

    total = sum(len(v) for v in levels_by_world.values())
    if total < 40:
        print("too few levels built, aborting")
        return 2

    if args.dry_run:
        print(json.dumps({w: len(v) for w, v in levels_by_world.items()},
                         ensure_ascii=False))
        print(json.dumps(levels_by_world["iceage"][:1], ensure_ascii=False)[:1200])
        return 0

    # backup (first run only) + write
    before = CONTENT / "levels_before_full"
    if LEVELS.exists() and not before.exists():
        shutil.copytree(LEVELS, before)
        print(f"backup -> {before}")
    legacy = CONTENT / "levels_legacy"
    if LEVELS.exists() and not legacy.exists():
        shutil.copytree(LEVELS, legacy)

    LEVELS.mkdir(exist_ok=True)
    for old in LEVELS.glob("*.json"):
        old.unlink()
    for world in WORLD_ORDER:
        for row in levels_by_world[world]:
            with open(LEVELS / f"{row['id']}.json", "w", encoding="utf-8") as fh:
                json.dump(row, fh, ensure_ascii=False, indent=1)

    with open(plants_path, "w", encoding="utf-8") as fh:
        json.dump(plants, fh, ensure_ascii=False, indent=2)

    almanac = json.load(open(almanac_path, encoding="utf-8"))
    almanac.setdefault("plants", {})["voiddragon"] = {
        "desc": "来自虚空的暗物质火龙果，以暗物质能量攻击整行僵尸，并有概率触发元素反应。",
        "tip": "虚空不会说话，但它记得每一个被它吞下的僵尸。暗物质火龙果只是在替它记账。",
    }
    with open(almanac_path, "w", encoding="utf-8") as fh:
        json.dump(almanac, fh, ensure_ascii=False, indent=2)

    stars_added, stars_total = write_stars(levels_by_world)
    update_world_level_counts(levels_by_world)

    boss_total = sum(1 for rows in levels_by_world.values() for r in rows
                     if (r.get("extra") or {}).get("boss"))
    night_total = sum(1 for rows in levels_by_world.values() for r in rows
                      if (r.get("extra") or {}).get("night"))
    unmapped = {w: dict(c) for w, c in sorted(UNMAPPED.items()) if c}
    report = {
        "source": "main.460.com.ea.game.pvz2_shu.obb (RTON packages)",
        "generated_by": "tools/obb_build_content.py (18-world full-level build)",
        "world_order": WORLD_ORDER,
        "worlds": {w: len(levels_by_world.get(w, [])) for w in WORLD_ORDER},
        "total_levels": total,
        "plants": len(plants),
        "stat_fields_changed": changed,
        "voiddragon_added": voiddragon_added,
        "preserved_worlds": {w: len(v) for w, v in preserved.items()},
        "boss_levels": boss_total,
        "night_levels": night_total,
        "special_excluded": special_counts,
        "stage_stats": stage_stats,
        "unmapped_aliases": unmapped,
        "unmapped_alias_stats": {
            "unique": sum(len(v) for v in unmapped.values()),
            "occurrences": sum(sum(v.values()) for v in unmapped.values()),
        },
        "stars_added": stars_added,
        "stars_total": stars_total,
        "level_inventory_total": len(all_levels),
        "stage_inventory": dict(sorted(stage_inventory.items())),
    }
    with open(ROOT / "tools" / "obb_build_report.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps({k: report[k] for k in (
        "worlds", "total_levels", "plants", "stat_fields_changed", "boss_levels",
        "night_levels", "unmapped_alias_stats", "stars_added", "stars_total")},
        ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
