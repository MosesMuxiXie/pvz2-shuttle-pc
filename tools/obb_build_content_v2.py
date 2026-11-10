# -*- coding: utf-8 -*-
"""Rebuild ALL PvZ2 SHUTTLE levels / worlds from the OBB (1809 levels, 26 worlds).

This is the v2 content builder.  It deliberately imports the proven conversion
helpers from tools/obb_build_content.py (``convert_level`` / ``synth_level`` /
``_renumber_and_dedupe`` / string tables) instead of re-implementing them, and
only extends the world tables and the stage -> world routing.

Usage:
    python tools/obb_build_content_v2.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import obb_build_content as base  # noqa: E402

_BASE_LEVEL_TITLE = base._level_title

CONTENT = ROOT / "content"
LEVELS = CONTENT / "levels"
PKG_DIR = base.PKG_DIR
CJK = None

# ---------------------------------------------------------------------------
# World list (final order).  Existing 18 worlds keep their content/name/desc;
# 8 new worlds are interleaved by difficulty/theme.  The last world stays
# Plantagenet (endgame).
# ---------------------------------------------------------------------------
WORLDS = [
    # id, zh, en, map source world name in pkg_2108, tint, desc
    ("frontyard", "前院", "Front Yard", "yourhouse", [214, 226, 190],
     "阳光充足的前院草坪，一切冒险从这里开始。"),
    ("egypt", "神秘埃及", "Ancient Egypt", "egypt", [226, 202, 150],
     "黄沙与金字塔之下，木乃伊正从沉睡的陵墓中苏醒。"),
    ("pirate", "海盗港湾", "Pirate Seas", "pirate", [150, 195, 210],
     "海盗僵尸乘船登陆，甲板与浪花之间危机四伏。"),
    ("cowboy", "狂野西部", "Wild West", "cowboy", [222, 190, 150],
     "尘土飞扬的西部小镇，矿车沿着铁轨横冲直撞。"),
    ("future", "未来世界", "Far Future", "future", [160, 210, 225],
     "霓虹闪烁的未来都市，机械僵尸列队推进。"),
    ("dark", "黑暗时代", "Dark Ages", "dark", [150, 140, 175],
     "月光下的古堡，骑士与法师在迷雾中出没。"),
    ("beach", "神秘海滩", "Big Wave Beach", "beach", [170, 215, 215],
     "潮水涨落的海滩，冲浪僵尸踏浪而来。"),
    ("lostcity", "失落之城", "Lost City", "lostcity", [190, 205, 155],
     "藤蔓覆盖的失落遗迹，探险家僵尸在断壁间游荡。"),
    ("iceage", "冰河世界", "Frostbite Caves", "iceage", [185, 215, 235],
     "寒风呼啸的冰原，冰砖与雪橇僵尸从裂隙中涌出。"),
    ("kongfu", "功夫世界", "Kongfu World", "kongfu", [220, 190, 150],
     "竹林与古刹之间，功夫僵尸摆开阵势。"),
    ("dino", "恐龙危机", "Jurassic Marsh", "dino", [175, 205, 150],
     "史前沼泽深处，恐龙与原始僵尸一同袭来。"),
    ("eighties", "摇滚年代", "Neon Mixtape Tour", "eighties", [205, 160, 220],
     "霓虹舞台与磁带机，摇滚僵尸踩着节拍推进。"),
    ("modern", "摩登世界", "Modern Day", "modern", [195, 205, 210],
     "小镇的街道与屋顶，现代僵尸发起最后的总攻。"),
    ("sky", "天空之城", "Sky City", "skycity", [175, 200, 230],
     "云海之上的浮空城，雷霆与飞艇环绕。"),
    ("chinesegarden", "中国园林", "Chinese Garden", "chinesegarden", [225, 180, 170],
     "灯笼高挂的园林，纸伞与诗人在月色下穿行。"),
    ("heian", "平安时代", "Heian Age", "heian", [225, 180, 160],
     "神社、樱花与灯笼之间，武士僵尸踏着鼓声而来。"),
    ("fairy", "童话森林", "Fairytale Forest", "fairy", [175, 205, 165],
     "蘑菇与藤蔓缠绕的童话林地，骑士僵尸护送着童话队伍。"),
    ("mausoleum", "地宫遗迹", "Mausoleum", "mausoleum", [150, 145, 165],
     "幽深的地宫甬道，石棺与暗影中的守卫一同苏醒。"),
    ("steam", "蒸汽时代", "Steam Ages", "steam", [200, 180, 150],
     "齿轮与蒸汽弥漫的工坊，机械僵尸沿着铜管推进。"),
    ("memorytour", "回忆之旅", "Memory Lane", "memorytour", [210, 200, 170],
     "泛黄的记忆胶片中，熟悉的老朋友再次并肩。"),
    ("losantosvice", "洛城风云", "Los Santos Vice", "gta", [200, 170, 185],
     "夕阳下的街区车库，帮派僵尸沿着柏油路压过来。"),
    ("lunarrainbowmarket", "月虹市场", "Lunar Rainbow Market", "rainbowmarket", [198, 186, 232],
     "月虹之下的夜市石阶，发条与杂技僵尸从摊位之间涌出。"),
    ("renai", "恋爱剧场", "Renai Theatre", "renai", [220, 170, 185],
     "聚光灯下的恋爱剧场，演员僵尸轮番上演悲喜剧。"),
    ("muji", "罗马帝国", "Roman Empire", "muji", [205, 185, 150],
     "罗马柱与竞技场之间，军团僵尸列队推进。"),
    ("carnival", "后院马戏团", "Backyard Big Top", "carnival", [205, 165, 215],
     "灯火通明的马戏团，空中飞人与发条小丑轮番登场。"),
    ("plantagenet", "王朝", "Plantagenet", "plantagenet", [200, 180, 150],
     "石堡深处的王朝庭院，红毯与烛台之间，皇家僵尸正踏着鼓点列队而来。"),
]
WORLD_IDS = [w[0] for w in WORLDS]
WORLD_ZH = {w[0]: w[1] for w in WORLDS}
NEEDS_ART = {"carnival", "muji", "mausoleum", "steam", "renai", "memorytour"}
ART_SOURCES = {
    "heian": "work/art_research/heian/map.png + lawn.png (real art, board warped to the 9x5 grid)",
    "fairy": "work/art_research/fairy/map.png + lawn.png (real art, perspective quad to the 9x5 grid)",
    "memorytour": "menu screenshot card + sepia-tinted modern lawn (partial; no clean board art)",
    "mausoleum": "gradient card + purple-tinted dark lawn (placeholder)",
    "steam": "gradient card + warm-tinted future lawn (placeholder)",
    "renai": "gradient card + rose-tinted plantagenet lawn (placeholder)",
    "carnival": "vector placeholder card/lawn supplied by the art agent (NEEDS_ART)",
    "muji": "vector placeholder card/lawn supplied by the art agent (NEEDS_ART)",
}

# ---------------------------------------------------------------------------
# StageModule -> world.  Every StageModule in the OBB is routed; special
# per-level overrides are applied in ``world_of`` below.
# ---------------------------------------------------------------------------
STAGE_MAP_LISTS = {
    "frontyard": [
        "DayStage", "NightStage", "FrontLawnStage", "FrontLawnUnsoddedStage", "TutorialStage",
        "RoofStage", "RoofUBStage", "RoofNightStage", "PvZ2CRoofStage", "PvZ2CRoofNightStage",
        "DayLBStage", "NightLBStage", "DayUBStage", "NightUBStage", "PoolStage", "PoolLBStage",
        "PoolUBStage", "FogStage", "FogLBStage", "SixLaneFogStage", "SixLanePoolStage",
        "SixLaneStage", "SixLaneHonkaiStage", "Stage", "",
    ],
    "egypt": [
        "EgyptStage", "EgyptUBStage", "EgyptDMGStage", "EgyptNightsStage", "EgyptNightsUBStage",
        "EgyptNightsDMGStage", "EgyptFunTimeStage", "EgyptNightsFunTimeStage",
        "EgyptNightsBossStage", "EgyptStageUnlimitedPowerups", "EgyptExodusStage",
    ],
    "pirate": ["PirateStage", "PirateUBStage", "PirateDMGStage", "PirateFunTimeStage",
               "PirateBossStage"],
    "cowboy": ["WestStage", "WestUBStage", "WestDMGStage", "WestNightStage", "WestNightUBStage",
               "WestNightDMGStage", "WestNightBossStage", "WestBossStage"],
    "future": ["FutureStage", "FutureOriStage", "FutureOriUBStage", "FutureOriDMGStage",
               "FutureOriFunTimeStage"],
    "dark": ["DarkStage", "DarkUBStage", "DarkDMGStage"],
    "beach": ["BeachStage", "BeachUBStage", "BeachDMGStage", "BeachMiniGameStage",
              "BeachTeaserStage", "BeachBossStage", "DeepseaStage", "DeepseaLandStage"],
    "lostcity": ["LostCityStage", "LostCityUBStage", "LostCityDMGStage", "LostCityNightsStage",
                 "LostCityNightsUBStage", "LostCityNightsDMGStage", "LostCityTeaserStage",
                 "LostCityUnsoddedStage", "LostCityUnsoddedDMGStage", "VolcanoStage",
                 "VolcanoDMGStage", "VolcanoUBStage"],
    "iceage": ["IceageStage", "IceageEXStage", "IceageExpandStage", "IceageTeaserStage",
               "IceageVeteranStage", "FeastivusStage", "FeastivusNightsStage",
               "FeastivusSoccerStage", "FeastivusBeachStage"],
    "kongfu": ["KongfuStage", "KongfuUBStage", "KongfuDMGStage", "KongfuFunTimeStage",
               "KongfuBossStage", "JTTWStage", "JourneyToTheWestStage"],
    "dino": ["DinoStage", "DinoUBStage", "DinoDMGStage", "DinoNightsStage", "DinoNightsUBStage",
             "DinoNightsDMGStage", "DinoTeaserStage", "TheStage"],
    "eighties": ["EightiesStage", "EightiesTeaserStage", "UnchartedNeedforspeedStage"],
    "modern": ["ModernStage", "ModernUBStage", "ModernDMGStage", "ModernOriStage",
               "ModernOriUBStage", "ModernNightsDMGStage", "ModernNightsUBStage", "ZCorpStage",
               "ChildStage", "ChildUBStage", "ChildDMGStage"],
    "sky": ["SkyCityStage", "SkyCityUBStage", "SkyCityDMGStage", "SkyCityBossStage",
            "SkyCityLostCityStage", "SkyCityLostCityBossStage", "PenaconyStage"],
    "chinesegarden": ["ChineseGardenStage", "ChineseGardenUBStage", "ChineseGardenDMGStage",
                      "ChineseGardenNightsStage", "ChineseGardenNightsUBStage",
                      "ChineseGardenNightsDMGStage", "ChineseGardenBossStage"],
    "heian": ["HeianStage", "HeianUBStage", "HeianDMGStage", "HeianBossStage"],
    "fairy": ["FairyStage", "FairyUBStage", "FairyDMGStage", "FairyNightsStage",
              "FairyNightsUBStage", "FairyNightsDMGStage", "FairyTaleNightsStage",
              "FairyTaleUBStage"],
    "mausoleum": ["MausoleumStage", "MausoleumPalaceStage", "RiftStageLawnOfDoom"],
    "steam": ["SteamStage", "SteamUBStage", "SteamDMGStage", "SteamBossStage"],
    "memorytour": ["HeroesStage"],
    "losantosvice": ["GTAStage", "GTAUBStage", "GTADMGStage"],
    "lunarrainbowmarket": ["MarketNightsStage", "MarketNightsUBStage", "MarketNightsDMGStage",
                           "LunarStage", "LunarUBStage", "LunarDMGStage", "LunarDaylightStage",
                           "LunarDaylightUBStage", "LunarDaylightDMGStage",
                           "LunarDaylightNoMusicSuffixStage", "LunarNoMusicSuffixStage",
                           "LunarNightAndQinMusicStage"],
    "renai": ["RenaiStage", "RenaiUBStage", "RenaiDMGStage", "RenaiNightsStage",
              "RenaiNightsUBStage", "RenaiNightsDMGStage", "RenaiBossStage", "TheatreStage",
              "ValentinesStage"],
    "muji": ["RiftStage"],
    "carnival": ["CarnivalStage", "CarnivalBossStage", "AprilFoolsStage", "PlantWarsStage",
                 "BigBrainzStage", "BirthdayStage", "SpringStage", "HarvestStage", "PaddysStage",
                 "PaddysUBStage", "No42UniverseStage", "PinoconyStage", "PennyPurstStage"],
    "plantagenet": ["PlantagenetStage", "PlantagenetUBStage", "PlantagenetDMGStage",
                    "PlantagenetDaylightStage", "PlantagenetDaylightUBStage",
                    "PlantagenetDaylightDMGStage", "PlantagenetDaylightFunTimeStage",
                    "PlantagenetFunTimeStage", "PlantagenetNoMusicStage",
                    "PlantagenetBossStage", "JoustStage"],
}
STAGE_WORLD = {s: w for w, stages in STAGE_MAP_LISTS.items() for s in stages}

# ---------------------------------------------------------------------------
# Zombie mapping for the 8 new worlds (all output ids come from the 55
# zombies that already exist in content/zombies.json).
# ---------------------------------------------------------------------------
NEW_WORLD_ZOMBIES = {
    "heian": ("basic", "conehead", "buckethead"),
    "fairy": ("basic", "conehead", "buckethead"),
    "carnival": ("eighties", "eighties", "buckethead"),
    "mausoleum": ("dark", "dark_armor1", "buckethead"),
    "steam": ("future", "future_armor1", "buckethead"),
    "renai": ("royal_zombie", "royal_noblewoman", "royal_winetasting"),
    "memorytour": ("basic", "conehead", "buckethead"),
    "muji": ("royal_zombie", "royal_noblewoman", "royal_winetasting"),
}
DEFAULT_DECK = ["sunflower", "peashooter", "wallnut", "bloomerang"]

# OBB WorldMap difficulties (pkg_2108), keyed by WorldMap MapName.
OBB_DIFFICULTY = {
    "yourhouse": 5, "egypt": 1, "pirate": 8, "cowboy": 3, "future": 3, "dark": 4,
    "beach": 4, "lostcity": 2, "iceage": 3, "kongfu": 7, "dino": 5, "eighties": 5,
    "modern": 6, "skycity": 5, "chinesegarden": 5, "heian": 5, "fairy": 5,
    "mausoleum": 6, "steam": 6, "memorytour": 3, "gta": 6, "rainbowmarket": 9,
    "renai": 7, "muji": 6, "carnival": 10, "plantagenet": 8,
}

SPECIAL_FLAGS = ("IsVasebreaker", "IsBeghouled", "IsBowling")


def setup_tables():
    """Extend the imported converter tables for the 8 new worlds."""
    for world, (z0, z1, z2) in NEW_WORLD_ZOMBIES.items():
        base.WORLD_BASE[world] = z0
        base.WORLD_ARMOR1[world] = z1
        base.WORLD_ARMOR2[world] = z2
        base.DEFAULT_DECKS.setdefault(world, DEFAULT_DECK[:])
        base.WORLD_ZH[world] = WORLD_ZH[world]
    base.NEW_WORLDS.update(NEW_WORLD_ZOMBIES)
    base.WORLD_ZH.update(WORLD_ZH)
    base._level_title = localize_title


def world_of(stage: str, name_key) -> str | None:
    """Route one LevelDefinition to a world, with per-level exceptions."""
    u = str(name_key or "").upper()
    if "MEMORYTOUR_LEVEL_NAME" in u:
        return "memorytour"
    if stage == "RiftStage":
        return "muji" if ("ROME" in u or "ROMAN" in u) else "mausoleum"
    if stage == "RomanFloodedStage":
        return "muji"  # rift-flooded Roman expansion level
    return STAGE_WORLD.get(stage)


def load_map_difficulties() -> dict:
    """Read the OBB WorldMapList difficulty values."""
    out = {}
    try:
        raw = json.loads((PKG_DIR / "pkg_2108_WorldMapList.json").read_text(encoding="utf-8"))
        for obj in raw.get("objects", []):
            for entry in (obj.get("objdata") or {}).get("MapList") or []:
                out[str(entry.get("MapName"))] = int(entry.get("Difficulty") or 1)
    except Exception:
        pass
    return out


def difficulty(raw: int) -> int:
    """Fold the OBB 1..10 difficulty onto the game's 1..5 star scale."""
    return max(1, min(5, int(round(raw / 2.0))))


# ---------------------------------------------------------------------------
# Real star challenges (StarChallenge* props inside the level package).
# ---------------------------------------------------------------------------
STAR_TYPE_BY_CLASS = {
    "StarChallengeBeatTheLevelProps": "beat",
    "StarChallengeSaveMowersProps": "mowers",
    "StarChallengeKillZombiesInTimeProps": "kill",
    "StarChallengePlantsLostProps": "plants_lost",
    "StarChallengeSunProducedProps": "sun_produced",
    "StarChallengeSunUsedProps": "sun_used",
    "StarChallengeLevelTimerProperties": "time",
}
FILL_STARS = ("beat", "mowers", "kill")


def _loc(key, zh, en, fallback=""):
    if not key:
        return fallback
    val = zh.get(str(key).strip("[]")) or en.get(str(key).strip("[]"))
    return val or fallback


def read_star_defs(pkg_name: str, level: dict, zh, en) -> list[dict]:
    """Return up to three real star goals from the level package, filled with
    sensible defaults so every level always has exactly three stars."""
    pkg = None
    try:
        pkg = json.loads((PKG_DIR / pkg_name).read_text(encoding="utf-8"))
    except Exception:
        pkg = None
    by_alias = {}
    objects = (pkg or {}).get("objects") or []
    for obj in objects:
        for alias in obj.get("aliases") or []:
            by_alias.setdefault(alias, obj)

    defs: list[dict] = []
    mod = by_alias.get("ChallengeModule")
    if mod:
        for group in ((mod.get("objdata") or {}).get("Challenges") or []):
            if isinstance(group, str):
                group = [group]
            for ref in group or []:
                alias = base.resolve_rtid_alias(ref)
                obj = by_alias.get(alias)
                if not obj:
                    continue
                kind = STAR_TYPE_BY_CLASS.get(obj.get("objclass") or "")
                if not kind:
                    continue
                props = obj.get("objdata") or {}
                text = _loc(props.get("Description"), zh, en, "通关")
                if kind == "beat":
                    defs.append({"type": "beat", "value": 0, "text_zh": text})
                elif kind == "mowers":
                    defs.append({"type": "mowers", "value": 5, "max": 0,
                                 "text_zh": text or "不损失小推车"})
                elif kind == "kill":
                    n = max(1, int(props.get("ZombiesToKill") or 10))
                    defs.append({"type": "kill", "value": n, "count": n, "text_zh": text})
                elif kind == "plants_lost":
                    n = max(0, int(props.get("MaximumPlantsLost") or 2))
                    defs.append({"type": "plants_lost", "value": n, "max": n, "text_zh": text})
                elif kind == "sun_produced":
                    n = max(1, int(props.get("TargetSun") or 1000))
                    defs.append({"type": "sun_produced", "value": n, "target": n,
                                 "text_zh": text})
                elif kind == "sun_used":
                    n = max(1, int(props.get("MaximumSun") or 3000))
                    defs.append({"type": "sun_used", "value": n, "max": n, "text_zh": text})
                elif kind == "time":
                    n = max(30, min(3600, int(props.get("TimeLimit") or 300)))
                    defs.append({"type": "time", "value": n, "seconds": n, "text_zh": text})

    total = sum(len(w.get("zombies") or []) for w in level.get("waves") or [])
    kill_n = max(10, int(round(total * 0.6)))
    defaults = {
        "beat": {"type": "beat", "value": 0, "text_zh": "通关本关"},
        "mowers": {"type": "mowers", "value": 5, "max": 0, "text_zh": "不损失小推车"},
        "kill": {"type": "kill", "value": kill_n, "count": kill_n,
                 "text_zh": f"击杀 {kill_n} 只僵尸"},
    }
    seen = set()
    out = []
    for d in defs + [defaults[t] for t in FILL_STARS]:
        if d["type"] in seen:
            continue
        seen.add(d["type"])
        out.append(d)
        if len(out) == 3:
            break
    # A level must always offer exactly three distinct star goals.
    for kind in ("beat", "mowers", "kill"):
        if len(out) >= 3:
            break
        if kind not in seen:
            out.append(defaults[kind])
            seen.add(kind)
    return out[:3]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
# Some LawnStringsData zh entries are still English placeholder strings.
# Localise the known SHUTTLE/Expand level-name families for the new worlds.
TITLE_RULES = [
    (r"^SHUTTLE - HA - Day (\d+)$", "\u5e73\u5b89\u65f6\u4ee3 - \u7b2c {n} \u5929"),
    (r"^SHUTTLE - HA - Night (\d+)$", "\u5e73\u5b89\u65f6\u4ee3 - \u591c\u665a {n}"),
    (r"^SHUTTLE - SA - Day (\d+)$", "\u84b8\u6c7d\u65f6\u4ee3 - \u7b2c {n} \u5929"),
    (r"^SHUTTLE - SA - Night (\d+)$", "\u84b8\u6c7d\u65f6\u4ee3 - \u591c\u665a {n}"),
    (r"^SHUTTLE - JM - Day (\d+)$", "\u7f57\u9a6c\u5e1d\u56fd\u00b7\u6d2a\u6c34 - \u7b2c {n} \u5929"),
    (r"^Roman Empire Expand - Day (\d+)$", "\u7f57\u9a6c\u5e1d\u56fd\u00b7\u8fdc\u5f81 - \u7b2c {n} \u5929"),
    (r"^SHUTTLE - RS - Day (\d+)$", "\u604b\u7231\u5267\u573a - \u7b2c {n} \u5929"),
    (r"^SHUTTLE - RS - Night (\d+)$", "\u604b\u7231\u5267\u573a - \u591c\u665a {n}"),
    (r"^SHUTTLE - RS - Theatre (\d+)$", "\u604b\u7231\u5267\u573a - \u5267\u573a {n}"),
    (r"^Renai Expand - Day (\d+)$", "\u604b\u7231\u5267\u573a\u00b7\u8fdc\u5f81 - \u7b2c {n} \u5929"),
    (r"^Renai Expand - Night (\d+)$", "\u604b\u7231\u5267\u573a\u00b7\u8fdc\u5f81 - \u591c\u665a {n}"),
]


def apply_title_rules(raw: str) -> str:
    for pattern, fmt in TITLE_RULES:
        m = re.match(pattern, raw or "")
        if m:
            return fmt.format(n=m.group(1))
    return raw


def localize_title(od: dict, zh, en) -> str:
    return apply_title_rules(_BASE_LEVEL_TITLE(od, zh, en))


def build_levels(zh, en):
    all_levels = base.load_all_levels()
    grouped = defaultdict(list)
    unknown = Counter()
    special_counts = Counter()
    for pkg_name, obj in all_levels:
        od = obj.get("objdata") or {}
        stage = base.resolve_rtid_alias(od.get("StageModule"))
        world = world_of(stage, od.get("Name"))
        if world not in WORLD_ZH:
            unknown[stage] += 1
            continue
        grouped[world].append((pkg_name, obj))
        for flag in SPECIAL_FLAGS:
            if od.get(flag):
                special_counts[flag] += 1

    levels_by_world = {}
    stage_stats = defaultdict(dict)
    for world in WORLD_IDS:
        rows = grouped.get(world, [])
        rows.sort(key=lambda t: (base._name_score(t[1].get("objdata", {}).get("Name"), world),
                                 int(t[1].get("objdata", {}).get("LevelNumber") or 9999),
                                 t[0]))
        out = []
        for i, (pkg_name, obj) in enumerate(rows, 1):
            od = obj.get("objdata") or {}
            level = base.convert_level(world, i, pkg_name, obj, zh, en)
            source = "obb"
            if level is None:
                level = base.synth_level(world, i, pkg_name, obj, zh, en)
                source = "obb-synth"
            level["extra"]["source"] = source
            stage = level["extra"].get("stage") or ""
            # Boss stages always carry the boss flag, even when the package
            # does not reference a zomboss module directly.
            if "boss" in stage.lower() and not level["extra"].get("boss"):
                level["extra"]["boss"] = True
                level["extra"]["boss_zombie"] = level["extra"].get("boss_zombie") or "zomboss"
            flags = [f for f in SPECIAL_FLAGS if od.get(f)]
            if flags:
                level["extra"]["special"] = flags
                if "IsVasebreaker" in flags:
                    level["extra"]["vasebreaker"] = True
            out.append(level)
            st = stage_stats[world].setdefault(stage, {"total": 0, "converted": 0, "synth": 0})
            st["total"] += 1
            st["converted" if source == "obb" else "synth"] += 1
        base._renumber_and_dedupe(out)
        levels_by_world[world] = out

    return levels_by_world, unknown, special_counts, stage_stats


def build_stars(levels_by_world, zh, en) -> dict:
    stars = {}
    for world in WORLD_IDS:
        for level in levels_by_world[world]:
            stars[level["id"]] = read_star_defs(
                level["extra"]["package"] + "_LevelDefinition.json", level, zh, en)
    return stars


def build_worlds_json(levels_by_world) -> list:
    raw_diff = load_map_difficulties()
    worlds = []
    previous = None
    for order, (wid, zh, en, map_name, tint, desc) in enumerate(WORLDS, 1):
        row = {
            "id": wid,
            "name_zh": zh,
            "name_en": en,
            "order": order,
            "levels": len(levels_by_world[wid]),
            "map": f"world/{wid}.png",
            "lawn": f"lawn/{wid}.png",
            "unlock_after": previous,
            "lawn_mode": "full",
            "desc_zh": desc,
            "bg_tint": tint,
        }
        if wid == "frontyard":
            row["difficulty"] = 1
        else:
            row["difficulty"] = difficulty(raw_diff.get(map_name, OBB_DIFFICULTY.get(map_name, 3)))
        worlds.append(row)
        previous = wid
    return worlds


def build_worldmap_json(worlds) -> dict:
    out = {}
    for w in worlds:
        out[w["id"]] = {
            "id": w["id"],
            "order": w["order"],
            "name_key": f"world.{w['id']}.name",
            "difficulty": w["difficulty"],
            "unlock_cost": 1,
            "key_required": w["id"] != "frontyard",
            "desc": w["desc_zh"],
        }
    return {"worlds": out}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stars-only", action="store_true",
                    help="only rewrite content/stars.json (levels/worlds untouched)")
    ap.add_argument("--titles-only", action="store_true",
                    help="only localise English titles in existing content/levels/*.json")
    args = ap.parse_args()

    if args.titles_only:
        changed = 0
        for path in sorted(LEVELS.glob("*.json")):
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            new = apply_title_rules(str(data.get("title") or ""))
            if new != data.get("title"):
                data["title"] = new
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=1)
                changed += 1
        print(f"titles localised: {changed}")
        return 0

    setup_tables()
    zh, en = base.collect_strings()
    levels_by_world, unknown, special_counts, stage_stats = build_levels(zh, en)

    total = sum(len(v) for v in levels_by_world.values())
    print(f"levels: {total} / worlds: {len(WORLD_IDS)}")
    for wid in WORLD_IDS:
        print(f"  {wid:20s} {len(levels_by_world[wid]):4d}")
    print("unknown stages:", dict(unknown), "special:", dict(special_counts))

    stars = build_stars(levels_by_world, zh, en)
    worlds = build_worlds_json(levels_by_world)
    worldmap = build_worldmap_json(worlds)

    night = sum(1 for lv in (x for v in levels_by_world.values() for x in v)
                if (lv.get("extra") or {}).get("night"))
    boss = sum(1 for lv in (x for v in levels_by_world.values() for x in v)
               if (lv.get("extra") or {}).get("boss"))
    synth = sum(1 for lv in (x for v in levels_by_world.values() for x in v)
                if (lv.get("extra") or {}).get("source") == "obb-synth")
    print(f"stars: {len(stars)} night: {night} boss: {boss} synth: {synth}")

    if args.dry_run:
        return 0

    # stars-only mode: rewrite just the star table (used to repair goals)
    if args.stars_only:
        with open(CONTENT / "stars.json", "w", encoding="utf-8", newline="\n") as fh:
            json.dump(stars, fh, ensure_ascii=False, indent=1)
        print("stars only written.")
        return 0

    # levels
    if LEVELS.exists():
        backup = CONTENT / "levels_before_v2"
        if backup.exists():
            shutil.rmtree(backup)
        shutil.copytree(LEVELS, backup)
        for f in LEVELS.glob("*.json"):
            f.unlink()
    else:
        LEVELS.mkdir(parents=True, exist_ok=True)
    for wid in WORLD_IDS:
        for level in levels_by_world[wid]:
            with open(LEVELS / f"{level['id']}.json", "w", encoding="utf-8", newline="\n") as fh:
                json.dump(level, fh, ensure_ascii=False, indent=1)

    # worlds
    with open(CONTENT / "worlds.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(worlds, fh, ensure_ascii=False, indent=1)

    # stars (full replacement: exactly the 1809 levels, old keys dropped)
    with open(CONTENT / "stars.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(stars, fh, ensure_ascii=False, indent=1)

    # world map
    with open(CONTENT / "worldmap.json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump(worldmap, fh, ensure_ascii=False, indent=1)

    # report
    report = {
        "generated_by": "tools/obb_build_content_v2.py",
        "worlds": len(worlds),
        "levels": total,
        "stars": len(stars),
        "night_levels": night,
        "boss_levels": boss,
        "synth_levels": synth,
        "special_included": dict(special_counts),
        "special_note": (
            "45 IsVasebreaker levels are included as ordinary playable levels "
            "to reach the required 1809 total; they carry extra.special / extra.vasebreaker."
        ),
        "world_list": [
            {"id": w["id"], "name_zh": w["name_zh"], "order": w["order"],
             "levels": w["levels"], "difficulty": w["difficulty"],
             "unlock_after": w["unlock_after"]}
            for w in worlds
        ],
        "stage_module_mapping": {wid: sorted(stages) for wid, stages in STAGE_MAP_LISTS.items()},
        "stage_stats": {w: dict(v) for w, v in stage_stats.items()},
        "unmapped_stages": dict(unknown),
        "overrides": {
            "RiftStage": "ROME/ROMAN level names -> muji, others -> mausoleum",
            "RomanFloodedStage": "-> muji",
            "MEMORYTOUR_LEVEL_NAME": "-> memorytour",
            "PennyPurstStage": "-> carnival",
            "empty StageModule": "-> frontyard",
        },
        "NEEDS_ART": sorted(NEEDS_ART),
        "art_sources": ART_SOURCES,
        "art_note": (
            "heian / fairy use work/art_research maps+lawns; memorytour uses the "
            "art_research menu map and a tinted lawn (partial); carnival / muji "
            "have vector placeholder art in assets/; mausoleum / steam / renai "
            "use tinted official lawns + flat-colour world cards.  All eight new "
            "worlds have 1280x720 cards and full-screen lawns whose 9x5 board "
            "maps to (190,120)-(1090,700)."
        ),
    }
    with open(ROOT.parent / "work" / "full_levels_v2_report.json", "w",
              encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print("written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
