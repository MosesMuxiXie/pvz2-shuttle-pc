#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 OBB 的 PlantFusionConfig 生成植物融合数据。

用法::

    python tools/build_fusions.py            # 重建 content/fusions.json 并同步追加 plants/almanac
    python tools/build_fusions.py --dry-run  # 只统计，不写文件

数据来源（默认 ``<项目根>/../work/obb_packages``，可用 ``--obb`` 或
环境变量 ``PVZ2_OBB_DIR`` 覆盖）::

    pkg_2083_PlantFusionConfig.json  FusionPairs（85 条配方，唯一数据源）
    pkg_2069_PlantLevelStats.json    Cost / Hitpoints / ActionDamage / PacketCooldown 等真实数值
    pkg_2074_PlantType.json          PlantFramework / HomeWorld（用于 family、behavior 推断）
    pkg_0232_LawnStringsData.json    简体中文名、图鉴 DESCRIPTION_HEADER / TOOLTIP
    pkg_0231_LawnStringsData.json    英文名（用于 name_en 回退）

立绘选择顺序：
    1. 产物已在 plants.json 中 —— 直接复用该条目 art
    2. ``assets/art/<world>/<result>.png`` 静态立绘存在 —— 用静态立绘
    3. 按 PlantFramework 映射到 ``assets/db/plants/<Name>PLANT``
    4. 复用任一材料植物（plants.json 中）的 art
    5. 按 behavior 的默认 db 立绘
所有候选都会校验文件/目录存在，避免 ``validate_all.py`` 产生素材告警。

写入策略：
    * ``content/fusions.json`` 整体重建（本脚本独占该文件）。
    * ``content/plants.json`` / ``content/almanac.json`` **只追加**：保留所有既有条目，
      仅替换本脚本上次生成的 ``fused_*`` 条目（重复运行幂等）。
    * 读-改-写窗口尽量小，写后回读校验基础条目未被破坏；失败自动重试。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
ASSETS = ROOT / "assets"

DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR", str(ROOT.parent / "work" / "obb_packages")))
PLANTS_PATH = CONTENT / "plants.json"
ALMANAC_PATH = CONTENT / "almanac.json"
FUSIONS_PATH = CONTENT / "fusions.json"

FUSED_PREFIX = "fused_"
EXPECTED_PAIRS = 85

# 现有 plants.json 中的 family 集合，融合植物只从这些家族中选，避免出现野家族。
KNOWN_FAMILIES = {
    "Begonia", "Bird", "Chip", "Cold", "Defence", "Dragonfruit", "Explosive",
    "Fire", "Gardenia", "Jasmine", "Lobber", "Melee", "Mine", "Peashooter",
    "Poison", "Poppy", "Sharp", "Sun", "Support", "Toast", "Torpedo", "Wall",
    "Yucca",
}

# behavior → 默认 db 立绘（相对 assets/db 的植物目录名，不含 PLANT 后缀）。
BEHAVIOR_ART = {
    "shoot": "Peashooter",
    "lob": "MelonPult",
    "produce": "Sunflower",
    "wall": "Wallnut",
    "instant": "CherryBomb",
    "mine": "PotatoMine",
    "spike": "Spikeweed",
    "melee": "Chomper",
    "chomp": "Chomper",
    "fume": "FumeShroom",
    "boomerang": "Bloomerang",
    "support": "UmbrellaLeaf",
}

# PlantFramework → db 立绘目录名（不含 PLANT 后缀）。键为去掉 "Plant" 前缀的 PascalCase。
FRAMEWORK_ART = {
    "Peashooter": "Peashooter", "SnowPea": "SnowPea", "Repeater": "Repeater",
    "GatlingPea": "GatlingPea", "MegaGatling": "GatlingPea",
    "FusionGatling": "GatlingPea", "PrimalPeashooter": "Peashooter",
    "Cactus": "Spikeweed", "SnapPea": "Chomper", "HomingThistle": "HomingThistle",
    "StarFruit": "StarFruit", "Threepeater": "ThreePeater", "SplitPea": "SplitPea",
    "Bloomerang": "Bloomerang", "ArmamintPeashooter": "Peashooter",
    "ShadowPeashooter": "SplitPea", "PoisonPeashooter": "Peashooter",
    "PunkShocker": "GatlingPea", "Cabbagepult": "CabbagePult",
    "RaCabbagepult": "CabbagePult", "Kernelpult": "KernelPult",
    "Turkeypult": "KernelPult", "MelonPult": "MelonPult",
    "WinterMelon": "WinterMelon", "WinterGeddon": "WinterMelon",
    "ParadoxPult": "MelonPult", "LemonAider": "KernelPult",
    "Sunflower": "Sunflower", "TwinSunflower": "SunflowerTwin",
    "SunTower": "SunflowerTwin", "BirthSunflower": "SunflowerTwin",
    "SunShroom": "SunShroom", "Wallnut": "Wallnut", "Tallnut": "Tallnut",
    "Endurian": "Wallnut", "ChardGuard": "Wallnut", "ExplodeONut": "Wallnut",
    "Gumnut": "Wallnut", "PowerVine": "Wallnut", "Chomper": "Chomper",
    "BonkChoy": "BonkChoy", "Spikeweed": "Spikeweed", "Spikerock": "Spikeweed",
    "Iceweed": "Spikeweed", "Pokra": "Spikeweed", "StickybombRice": "CabbagePult",
    "FumeShroom": "FumeShroom", "Snapdragon": "FumeShroom",
    "Coldsnapdragon": "FumeShroom", "Torchwood": "Torchwood",
    "Jalapeno": "Jalapeno", "CherryBomb": "CherryBomb",
    "IcebergLettuce": "IcebergLettuce", "GlacierShroom": "GlacierShroom",
    "PotatoMine": "PotatoMine", "Squash": "Squash",
    "UmbrellaLeaf": "UmbrellaLeaf", "SweetPotato": "UmbrellaLeaf",
    "MagnetFruit": "MagnifyingGrass", "Magnetshroom": "MagnifyingGrass",
    "Draftodil": "CabbagePult", "Strawburst": "CabbagePult",
    "Puffball": "Peashooter", "Tumbleweed": "Bloomerang",
    "HeadbutterLettuce": "BonkChoy", "HollyBarrierLeaf": "Wallnut",
}

# 少数 OBB 里没有中文名的植物，人工补齐（sweetpotato1 缺 LawnStrings 条目）。
EXTRA_ZH = {
    "sweetpotato1": "甜薯",
    "iceweed": "冰蔓草",
}

CN_NUM = "零一二三四五六七八九十"


def _read_json(path: Path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def _write_json(path: Path, data, indent: int = 2, newline: str = "\n") -> None:
    """原子写入 UTF-8（无 BOM）JSON，并保持既有文件的换行风格。"""
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    if newline != "\n":
        text = text.replace("\n", newline)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
        fh.write(newline)
    os.replace(tmp, path)


def _newline_of(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return "\n"
    return "\r\n" if b"\r\n" in raw else "\n"


# ------------------------------------------------------------------ OBB 读取
def _objects(obb: Path, name: str):
    path = obb / name
    if not path.exists():
        return []
    try:
        data = _read_json(path)
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        return list(data.get("objects") or [])
    if isinstance(data, list):
        return data
    return []


def load_pairs(obb: Path):
    for obj in _objects(obb, "pkg_2083_PlantFusionConfig.json"):
        if str(obj.get("objclass", "")) != "PlantFusionConfig":
            continue
        pairs = (obj.get("objdata") or {}).get("FusionPairs")
        if pairs:
            return [p for p in pairs if isinstance(p, dict)]
    return []


def load_stats(obb: Path):
    """TypeName → {FloatStat 名称: 首个值}（同名多 SubType 时保留最大值）。"""
    out = {}
    for obj in _objects(obb, "pkg_2069_PlantLevelStats.json"):
        data = obj.get("objdata") or {}
        name = data.get("TypeName")
        if not name:
            continue
        stats = {}
        for entry in data.get("FloatStats") or []:
            key = str(entry.get("Name") or "")
            values = entry.get("Values") or []
            if not key or not values:
                continue
            try:
                value = float(values[0])
            except (TypeError, ValueError):
                continue
            stats[key] = max(value, stats.get(key, value))
        out[str(name)] = stats
    return out


def load_plant_types(obb: Path):
    out = {}
    for obj in _objects(obb, "pkg_2074_PlantType.json"):
        data = obj.get("objdata") or {}
        name = data.get("TypeName")
        if name:
            out[str(name)] = data
    return out


def load_strings(path: Path):
    for obj in _objects(path.parent, path.name):
        values = (obj.get("objdata") or {}).get("LocStringValues")
        if values:
            return dict(zip(values[0::2], values[1::2]))
    return {}


# ------------------------------------------------------------------ 数值工具
def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _int(value, default=0):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return int(default)


def _stat(stats, *names, default=None):
    for name in names:
        if name in stats:
            return stats[name]
    return default


def _title_from_id(plant_id: str) -> str:
    """把 ``fusiongatling`` / ``snow_pea`` 变成 ``Fusiongatling`` 之类的可读名。"""
    words = re.split(r"[_\W]+", str(plant_id).strip())
    out = []
    for word in words:
        if not word:
            continue
        if word.isdigit():
            out.append(word)
        elif word.isupper():
            out.append(word)
        else:
            out.append(word[:1].upper() + word[1:])
    return " ".join(out) or str(plant_id)


def _slug(plant_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(plant_id).lower()).strip("_")
    return slug or "fusion"


def _cn_index(n: int) -> str:
    if 1 <= n <= 10:
        return CN_NUM[n]
    if n < 20:
        return "十" + CN_NUM[n - 10]
    return str(n)


def _behavior_from_framework(framework: str, result_id: str) -> str:
    fw = str(framework or "")
    if fw.startswith("Plant"):
        fw = fw[5:]
    low = (fw + " " + result_id).lower()
    rules = [
        (("sunflower", "suntower", "sunshroom", "twinsun"), "produce"),
        (("cabbagepult", "kernelpult", "melonpult", "wintermelon", "wintergeddon",
          "paradoxpult", "rabbagepult", "turkeypult", "lemon", "pult"), "lob"),
        (("chomper", "snapdragon", "snappea"), "chomp"),
        (("fumeshroom", "fume", "gloom"), "fume"),
        (("wallnut", "tallnut", "endurian", "chardguard", "explodeonut", "gumnut",
          "barrier", "powervine", "hollybarrier"), "wall"),
        (("cherrybomb", "jalapeno", "iceberg", "squash", "strawburst", "puffball",
          "stickybomb", "explode"), "instant"),
        (("potatomine", "olivepit", "mine"), "mine"),
        (("spikeweed", "spikerock", "iceweed", "pokra", "bonkchoy",
          "cactus", "spike", "headbutter"), "spike"),
        (("boomerang", "tumbleweed"), "boomerang"),
        (("umbrellaleaf", "sweetpotato", "magnet", "draftodil", "magnifying",
          "torchwood"), "support"),
        (("peashooter", "snowpea", "repeater", "gatling", "starfruit", "thistle",
          "threepeater", "splitpea", "shooter", "pea", "punk"), "shoot"),
    ]
    for words, behavior in rules:
        if any(word in low for word in words):
            return behavior
    return ""


def infer_behavior(result_id, framework, materials, existing):
    if existing and existing.get("behavior"):
        return str(existing["behavior"])
    behavior = _behavior_from_framework(framework, result_id)
    if behavior:
        return behavior
    # 回退：材料里出现次数最多、且不是墙/辅助的 behavior
    counts = {}
    for mat in materials:
        b = str((mat or {}).get("behavior") or "")
        if b:
            counts[b] = counts.get(b, 0) + 1
    if counts:
        for candidate in ("shoot", "lob", "spike", "fume", "chomp", "boomerang",
                          "mine", "instant", "produce", "wall", "support"):
            if counts.get(candidate):
                return candidate
    return "shoot"


def infer_family(result_id, framework, behavior, materials, existing):
    if existing and existing.get("family") in KNOWN_FAMILIES:
        return str(existing["family"])
    hay = (str(result_id) + " " + str(framework)).lower()
    # 元素优先：冰/火/阳光是玩家最直观的家族标签
    for words, family in (
        (("winter", "ice", "snow", "cold", "frost"), "Cold"),
        (("fire", "flame", "torch", "jalapeno", "pepper", "solar"), "Fire"),
        (("sun",), "Sun"),
    ):
        if any(word in hay for word in words):
            return family
    # 其次按行为定家族，避免「甜薯」被 potato 误判成爆炸系
    by_behavior = {
        "shoot": "Peashooter", "lob": "Lobber", "produce": "Sun",
        "wall": "Defence", "support": "Support", "spike": "Sharp",
        "chomp": "Melee", "fume": "Poison", "instant": "Explosive",
        "mine": "Mine", "boomerang": "Melee",
    }
    if behavior in by_behavior:
        return by_behavior[behavior]
    for words, family in (
        (("bomb", "cherry", "explode", "potato"), "Explosive"),
        (("nut", "wall", "barrier", "guard"), "Defence"),
        (("chomp", "bite", "snap"), "Melee"),
        (("spike", "thorn", "cactus", "pokra"), "Sharp"),
        (("fume", "smoke", "poison", "gloom"), "Poison"),
        (("boom", "rang"), "Melee"),
    ):
        if any(word in hay for word in words):
            return family
    counts = {}
    for mat in materials:
        fam = (mat or {}).get("family")
        if fam in KNOWN_FAMILIES:
            counts[fam] = counts.get(fam, 0) + 1
    if counts:
        return max(counts, key=counts.get)
    return "Peashooter"


# ------------------------------------------------------------------ 立绘
def _art_exists(art: str) -> bool:
    art = str(art or "")
    if not art:
        return False
    try:
        if art.lower().endswith(".png"):
            return (ASSETS / art.replace("/", os.sep)).is_file()
        return (ASSETS / "db" / art / "skeleton.json").is_file()
    except OSError:
        return False


def _static_art_index():
    index = {}
    art_root = ASSETS / "art"
    if not art_root.is_dir():
        return index
    for world in sorted(art_root.iterdir()):
        if not world.is_dir():
            continue
        for png in sorted(world.glob("*.png")):
            index.setdefault(png.stem.lower(), f"art/{world.name}/{png.name}")
    return index


def _db_art(dir_name: str) -> str:
    key = f"plants/{dir_name}PLANT"
    return key if _art_exists(key) else ""


def pick_art(result_id, framework, behavior, materials, existing, static_index):
    if existing and _art_exists(existing.get("art")):
        return str(existing["art"])
    low = str(result_id).lower()
    for stem in (low, re.sub(r"\d+$", "", low)):
        art = static_index.get(stem)
        if art:
            return art
    # 一次性/墙体/生产类优先用行为默认立绘，比框架立绘更像产物
    if behavior in ("instant", "mine", "wall", "produce", "support"):
        art = _db_art(BEHAVIOR_ART.get(behavior, "Peashooter"))
        if art:
            return art
    fw = str(framework or "")
    if fw.startswith("Plant"):
        fw = fw[5:]
    for name, dir_name in FRAMEWORK_ART.items():
        if name.lower() == fw.lower():
            art = _db_art(dir_name)
            if art:
                return art
    # 复用材料立绘（优先静态立绘，其次 db）
    material_arts = [str(m.get("art")) for m in materials if m and m.get("art")]
    for art in material_arts:
        if art.lower().endswith(".png") and _art_exists(art):
            return art
    for art in material_arts:
        if _art_exists(art):
            return art
    art = _db_art(BEHAVIOR_ART.get(behavior, "Peashooter"))
    if art:
        return art
    return "plants/PeashooterPLANT"


# ------------------------------------------------------------------ 配方 → 植物
def _clean_desc(text):
    text = re.sub(r"\{[^}]*\}", "", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _build_plant(index, pair, occurrence, stats, plant_types, zh_strings, en_strings,
                 plant_by_id, static_index):
    result_id = str(pair.get("ResultPlant") or "").strip()
    if not result_id:
        return None, None
    sources = [str(pair.get("SourcePlant") or ""), str(pair.get("FusionPlant") or "")]
    materials = [plant_by_id.get(s) for s in sources if s]
    material_stats = [stats.get(s, {}) for s in sources]
    existing = plant_by_id.get(result_id)
    meta = plant_types.get(result_id) or {}
    framework = str(meta.get("PlantFramework") or "")

    behavior = infer_behavior(result_id, framework, materials, existing)
    family = infer_family(result_id, framework, behavior, materials, existing)
    st = stats.get(result_id, {})

    upper = result_id.upper()
    base_zh = EXTRA_ZH.get(result_id) or zh_strings.get(upper) or ""
    if not base_zh and existing:
        base_zh = str(existing.get("name_zh") or "")
    base_en = en_strings.get(upper) or ""
    if not base_en and existing:
        base_en = str(existing.get("name_en") or "")
    if not base_en:
        base_en = _title_from_id(result_id)
    base_zh = base_zh or base_en

    exists_in_base = existing is not None
    if occurrence <= 1:
        suffix_zh = "·融合" if exists_in_base else ""
        suffix_en = " (Fusion)" if exists_in_base else ""
    else:
        suffix_zh = (f"·融合{_cn_index(occurrence)}式" if exists_in_base
                     else f"·{_cn_index(occurrence)}式")
        suffix_en = f" (Fusion Mk {_roman(occurrence)})" if exists_in_base \
            else f" Mk {_roman(occurrence)}"
    name_zh = base_zh + suffix_zh
    name_en = base_en + suffix_en

    slug = _slug(result_id)
    plant_id = FUSED_PREFIX + slug + ("" if occurrence <= 1 else f"_{occurrence}")
    recipe_id = "fusion_" + slug + ("" if occurrence <= 1 else f"_{occurrence}")

    # ---- 数值：优先 OBB 真实值，其次现有条目，最后按材料加权 ----
    material_cost = [m.get("cost") for m in materials if m and m.get("cost") is not None]
    material_hp = [m.get("hp") for m in materials if m and m.get("hp") is not None]
    material_cd = [m.get("cooldown") for m in materials if m and m.get("cooldown") is not None]

    cost = _stat(st, "Cost", "SeedPacketCost", default=None)
    if cost is None:
        cost = (existing or {}).get("cost")
    if cost is None and material_cost:
        cost = sum(_num(c) for c in material_cost) * 0.8
    cost = max(0, _int(cost, 100))

    cooldown = _stat(st, "PacketCooldown", default=None)
    if cooldown is None:
        cooldown = (existing or {}).get("cooldown")
    if cooldown is None and material_cd:
        cooldown = sum(_num(c) for c in material_cd) / len(material_cd)
    cooldown = max(1.0, round(_num(cooldown, 10.0), 1))

    hp = _stat(st, "Hitpoints", default=None)
    if hp is None:
        hp = (existing or {}).get("hp")
    if hp is None and material_hp:
        hp = max(_num(h) for h in material_hp) * 1.35
    hp = max(100, _int(hp, 300))

    if behavior in ("wall", "produce", "support"):
        damage = 0
    elif behavior == "instant":
        damage = _stat(st, "ActionDamageExplosion", "ActionDamage", default=None)
        if damage is None:
            damage = 1200
    elif behavior == "mine":
        damage = _stat(st, "ActionDamage", "ActionDamageExplosion", default=None)
        if damage is None:
            damage = 1800
    else:
        damage = _stat(st, "ActionDamageNormal", "ActionDamage", default=None)
        if damage is None:
            material_damage = [m.get("damage") for m in materials
                               if m and _num(m.get("damage")) > 0]
            damage = (max(_num(d) for d in material_damage) * 1.25
                      if material_damage else 30)
    damage = max(0, _int(damage, 30))

    if behavior in ("instant", "wall", "support"):
        interval = 0.0
    elif behavior == "produce":
        interval = max(8.0, round(_num(_stat(st, "ActionCooldownMax", default=None), 22.0), 1))
    else:
        interval = _stat(st, "ActionCooldownMax", "ActionCooldown", default=None)
        if interval is None and existing:
            interval = existing.get("interval")
        if interval is None and materials:
            intervals = [m.get("interval") for m in materials
                         if m and _num(m.get("interval")) > 0]
            interval = (sum(_num(i) for i in intervals) / len(intervals)
                        if intervals else {"shoot": 1.4, "lob": 2.7, "spike": 1.2,
                                           "chomp": 1.2, "fume": 0.6,
                                           "boomerang": 1.5, "mine": 15.0}.get(behavior, 1.5))
        interval = max(0.2, round(_num(interval, 1.5), 2))

    projectile = None
    if behavior == "shoot":
        projectile = "pea_snow" if family == "Cold" else "pea"
    elif behavior == "lob":
        projectile = "winter_melon" if family == "Cold" else (
            "melon" if family == "Lobber" and "melon" in result_id.lower() else "cabbage")
    elif behavior == "boomerang":
        projectile = "boomerang"

    rows = [0]
    if existing and isinstance(existing.get("rows"), list) and existing["rows"]:
        rows = [int(v) for v in existing["rows"]]
    elif any(word in (slug + framework.lower()) for word in ("three", "triple")):
        rows = [0, 1, 2]
    elif any(word in (slug + framework.lower()) for word in ("split", "twin")):
        rows = [-1, 0]

    tags = ["plant", "fused"]
    for mat in materials:
        for tag in (mat or {}).get("tags") or []:
            tag = str(tag)
            if re.fullmatch(r"[a-z0-9_]+", tag) and tag not in tags:
                tags.append(tag)
    if family == "Cold" and "ice" not in tags:
        tags.append("ice")
    if family == "Fire" and "fire" not in tags:
        tags.append("fire")
    if behavior == "lob" and "lobber" not in tags:
        tags.append("lobber")
    if behavior == "shoot" and "shooter" not in tags:
        tags.append("shooter")

    header = _clean_desc(zh_strings.get(f"{upper}_DESCRIPTION_HEADER"))
    tip_text = _clean_desc(zh_strings.get(f"{upper}_TOOLTIP"))
    if not header:
        header = _clean_desc(zh_strings.get(f"{upper}_DESCRIPTION"))
    if not header:
        mat_names = [str((m or {}).get("name_zh") or s) for m, s in zip(materials, sources)]
        header = f"{name_zh}由{'与'.join(n for n in mat_names if n)}融合而成，拥有独特的战斗方式。"
    if len(header) > 90:
        header = header[:88].rstrip("，。；、 ") + "。"

    plantfood = bool(zh_strings.get(f"{upper}_DESCRIPTION_PLANTFOOD")
                     or zh_strings.get(f"{upper}_PLANTFOOD"))
    if f"{upper}_PLANTFOOD" not in zh_strings and f"{upper}_DESCRIPTION_PLANTFOOD" not in zh_strings:
        plantfood = behavior in ("shoot", "lob", "produce", "wall", "spike", "fume",
                                 "chomp", "boomerang", "instant", "mine")

    art = pick_art(result_id, framework, behavior, materials, existing, static_index)

    plant = {
        "id": plant_id,
        "name_zh": name_zh,
        "name_en": name_en,
        "cost": cost,
        "cooldown": cooldown,
        "hp": hp,
        "family": family,
        "art": art,
        "behavior": behavior,
        "damage": damage,
        "interval": interval,
        "projectile": projectile,
        "rows": list(rows),
        "pierce": any(bool((m or {}).get("pierce")) for m in materials),
        "tags": tags,
        "desc_zh": header,
        "almanac_no": 63 + index,
        "plantfood": bool(plantfood),
        "fused": True,
    }
    if family == "Cold":
        plant["slow"] = 0.5
    if behavior == "lob" and family == "Cold":
        plant["splash"] = 40
        plant["extra"] = {"splash_radius": 1.5}

    unlock_cost = 120 + int(round((sum(_num(c) for c in material_cost) * 0.4
                                   + cost * 0.5) / 10.0)) * 10
    unlock_cost = max(150, min(2500, unlock_cost))
    plantfood_cost = 0 if unlock_cost <= 350 else (1 if unlock_cost <= 900 else 2)

    ingredient_names = []
    for sid, mat in zip(sources, materials):
        if mat and mat.get("name_zh"):
            ingredient_names.append(str(mat["name_zh"]))
        else:
            ingredient_names.append(EXTRA_ZH.get(sid) or zh_strings.get(sid.upper())
                                    or _title_from_id(sid))

    recipe = {
        "id": recipe_id,
        "ingredients": sources,
        "ingredient_names": ingredient_names,
        "result": plant,
        "unlock_cost": unlock_cost,
        "plantfood_cost": plantfood_cost,
        "unlock_condition": "在植物融合实验室消耗金币解锁",
    }
    almanac_tip = tip_text or f"融合配方：{ingredient_names[0]} + {ingredient_names[1]}。"
    return recipe, {"desc": header, "tip": almanac_tip}


def _roman(n: int) -> str:
    table = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    out = ""
    for value, sym in table:
        while n >= value:
            out += sym
            n -= value
    return out or "I"


# ------------------------------------------------------------------ 写入
def _update_plants(fused_plants):
    for _attempt in range(3):
        try:
            data = _read_json(PLANTS_PATH)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"无法读取 {PLANTS_PATH}: {exc}")
        if not isinstance(data, list):
            raise SystemExit("content/plants.json 必须是 list")
        base = [p for p in data if isinstance(p, dict)
                and not str(p.get("id", "")).startswith(FUSED_PREFIX)]
        base_ids = [p.get("id") for p in base]
        merged = base + list(fused_plants)
        _write_json(PLANTS_PATH, merged, indent=2, newline=_newline_of(PLANTS_PATH))
        try:
            check = _read_json(PLANTS_PATH)
        except (OSError, ValueError):
            continue
        if [p.get("id") for p in check][:len(base_ids)] == base_ids \
                and len(check) == len(merged):
            return merged
    raise SystemExit("plants.json 写入校验失败（可能被其他进程同时修改），请重试")


def _update_almanac(entries):
    for _attempt in range(3):
        try:
            data = _read_json(ALMANAC_PATH)
        except FileNotFoundError:
            data = {"plants": {}, "zombies": {}}
        except ValueError as exc:
            raise SystemExit(f"无法解析 {ALMANAC_PATH}: {exc}")
        if not isinstance(data, dict):
            data = {"plants": {}, "zombies": {}}
        plants = dict(data.get("plants") or {})
        for old_id in [pid for pid in plants if str(pid).startswith(FUSED_PREFIX)]:
            plants.pop(old_id, None)
        plants.update(entries)
        data["plants"] = plants
        data.setdefault("zombies", {})
        _write_json(ALMANAC_PATH, data, indent=2, newline=_newline_of(ALMANAC_PATH))
        try:
            check = _read_json(ALMANAC_PATH)
        except (OSError, ValueError):
            continue
        if all(key in (check.get("plants") or {}) for key in entries):
            return check
    raise SystemExit("almanac.json 写入校验失败（可能被其他进程同时修改），请重试")


# ------------------------------------------------------------------ 主流程
def build(obb: Path):
    pairs = load_pairs(obb)
    if len(pairs) != EXPECTED_PAIRS:
        raise SystemExit(f"FusionPairs 数量 {len(pairs)}，期望 {EXPECTED_PAIRS}"
                         f"（检查 {obb}）")
    stats = load_stats(obb)
    plant_types = load_plant_types(obb)
    zh_strings = load_strings(obb / "pkg_0232_LawnStringsData.json")
    en_strings = load_strings(obb / "pkg_0231_LawnStringsData.json")
    static_index = _static_art_index()

    try:
        current_plants = _read_json(PLANTS_PATH)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"无法读取 {PLANTS_PATH}: {exc}")
    plant_by_id = {str(p.get("id")): p for p in current_plants
                   if isinstance(p, dict) and p.get("id")}

    recipes, fused_plants, almanac_entries = [], [], {}
    occurrences = {}
    for index, pair in enumerate(pairs):
        result_id = str(pair.get("ResultPlant") or "")
        occurrences[result_id] = occurrences.get(result_id, 0) + 1
        recipe, almanac = _build_plant(index, pair, occurrences[result_id], stats,
                                       plant_types, zh_strings, en_strings,
                                       plant_by_id, static_index)
        if recipe is None:
            continue
        recipes.append(recipe)
        fused_plants.append(recipe["result"])
        almanac_entries[recipe["result"]["id"]] = almanac

    payload = {
        "version": 1,
        "source": "obb:PlantFusionConfig.FusionPairs",
        "pairs": len(pairs),
        "unique_results": len({str(p.get("ResultPlant")) for p in pairs}),
        "recipes": recipes,
    }
    return payload, fused_plants, almanac_entries


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="生成 content/fusions.json 并追加融合植物")
    parser.add_argument("--obb", default=str(DEFAULT_OBB), help="OBB 解包目录")
    parser.add_argument("--dry-run", action="store_true", help="只打印统计，不写文件")
    args = parser.parse_args(argv)

    obb = Path(args.obb)
    if not obb.is_dir():
        raise SystemExit(f"OBB 目录不存在: {obb}")
    payload, fused_plants, almanac_entries = build(obb)

    print(f"配方: {len(payload['recipes'])} 条")
    print(f"产物: {payload['unique_results']} 种唯一植物 / 追加 {len(fused_plants)} 个 fused_* 条目")
    print(f"图鉴: {len(almanac_entries)} 条")
    arts = {}
    for plant in fused_plants:
        arts[plant["art"]] = arts.get(plant["art"], 0) + 1
    print(f"立绘: {len(arts)} 种（复用材料/框架立绘）")
    if args.dry_run:
        for plant in fused_plants[:3]:
            print("  样例:", json.dumps(plant, ensure_ascii=False)[:200])
        return 0

    _write_json(FUSIONS_PATH, payload, indent=2, newline="\n")
    merged = _update_plants(fused_plants)
    _update_almanac(almanac_entries)
    print(f"已写入 {FUSIONS_PATH.relative_to(ROOT)}")
    print(f"plants.json 现有 {len(merged)} 条（基础 {len(merged) - len(fused_plants)} + 融合 {len(fused_plants)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
