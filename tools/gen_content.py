"""生成 content/ 下的游戏数据：plants / zombies / worlds / levels / almanac。

数据来源：``work/gamedata``（从 PvZ2 Gardendless Web 版资源包离线导出的真实
PopCap 数据表，2026-11 由本项目一次性提取）。本脚本只做挑选、换算和补全，
不联网、不依赖游戏运行时。

用法::

    python tools/gen_content.py

输出：
    content/plants.json   30 种植物（真实阳光/冷却/血量/射速 + SHUTTLE 元素）
    content/zombies.json  24 种僵尸（真实血量/速度/啃食 + 护甲段）
    content/worlds.json   8 个世界的章节数据
    content/levels/<world>_<n>.json   每个世界 10 关（真实波次构成）
    content/almanac.json  图鉴描述（真实中文图鉴文案）
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT.parent / "work" / "gamedata"
OUT = ROOT / "content"


# ---------------------------------------------------------------- 数据读取
def load(name: str):
    with open(SRC / name, encoding="utf-8") as f:
        return json.load(f)


def objects(name: str) -> list[dict]:
    d = load(name)
    return d.get("objects") or []


def alias_map(name: str) -> dict[str, dict]:
    out = {}
    for o in objects(name):
        for a in o.get("aliases") or []:
            out.setdefault(str(a).lower(), o.get("objdata") or {})
    return out


def feature_list(name: str, key: str) -> list[dict]:
    d = load(name)
    return d.get(key) or []


def rtid_alias(s: str) -> str:
    m = re.search(r"RTID\(([^@]+)@", str(s or ""))
    return m.group(1).lower() if m else ""


# ---------------------------------------------------------------- 植物表
# 我们的游戏用 PvZ2 的 codename 作为 id，方便与图鉴/RTID 对齐。
# behavior: shoot/lob/boomerang/produce/wall/instant/fume/chomp/mine/support
PLANT_SPECS = [
    # codename, 中文名, behavior, projectile, rows, extra
    dict(id="peashooter", name_zh="豌豆射手", behavior="shoot", projectile="pea", dmg=20, interval=1.4),
    dict(id="sunflower", name_zh="向日葵", behavior="produce", sun_value=25, sun_interval=24.0),
    dict(id="wallnut", name_zh="坚果墙", behavior="wall", hp_mul=1.0),
    dict(id="potatomine", name_zh="土豆地雷", behavior="mine", dmg=1800, delay=0.0),
    dict(id="snowpea", name_zh="寒冰射手", behavior="shoot", projectile="snowpea", dmg=20, interval=1.4, extra={"element": "ice"}),
    dict(id="chomper", name_zh="大嘴花", behavior="chomp"),
    dict(id="repeater", name_zh="双发射手", behavior="shoot", projectile="pea", dmg=20, interval=0.7),
    dict(id="bloomerang", name_zh="回旋镖射手", behavior="boomerang", dmg=20, interval=1.4, extra={"element": "wind"}),
    dict(id="cabbagepult", name_zh="卷心菜投手", behavior="lob", projectile="lob", dmg=40, interval=2.9),
    dict(id="kernelpult", name_zh="玉米投手", behavior="lob", projectile="lob", dmg=20, interval=2.9, extra={"butter": True}),
    dict(id="melonpult", name_zh="西瓜投手", behavior="lob", projectile="lob", dmg=80, interval=2.9, splash=45),
    dict(id="wintermelon", name_zh="冰西瓜投手", behavior="lob", projectile="lob", dmg=80, interval=2.9, splash=45, slow=0.5, extra={"element": "ice"}),
    dict(id="fumeshroom", name_zh="大喷菇", behavior="fume", dmg=20, interval=1.4, melee_range=3.5),
    dict(id="sunshroom", name_zh="阳光菇", behavior="produce", sun_value=15, sun_interval=16.0, hp_mul=0.7),
    dict(id="iceshroom", name_zh="寒冰菇", behavior="instant", dmg=20, delay=0.6, extra={"radius": 520.0, "element": "ice", "freeze_all": True}),
    dict(id="threepeater", name_zh="三线射手", behavior="shoot", projectile="pea", dmg=20, interval=1.4, rows=[-1, 0, 1]),
    dict(id="torchwood", name_zh="火炬树桩", behavior="support", extra={"element": "fire", "fire_boost": 2.0}),
    dict(id="jalapeno", name_zh="火爆辣椒", behavior="instant", dmg=1800, delay=0.5, extra={"radius": 300.0, "element": "fire", "full_row": True}),
    dict(id="cherrybomb", name_zh="樱桃炸弹", behavior="instant", dmg=1800, delay=0.6, extra={"radius": 130.0, "element": "fire"}),
    dict(id="squash", name_zh="窝瓜", behavior="instant", dmg=1800, delay=1.1, extra={"radius": 100.0}),
    dict(id="spikeweed", name_zh="地刺", behavior="support", extra={"ground_damage": 20}),
    dict(id="cattail", name_zh="猫尾草", behavior="shoot", projectile="pea", dmg=20, interval=1.5, extra={"element": "water", "homing": True}),
    dict(id="magnifyinggrass", name_zh="魔术菇", behavior="shoot", projectile="pea", dmg=20, interval=1.4, extra={"element": "thunder"}),
    dict(id="bonkchoy", name_zh="菜问", behavior="fume", dmg=15, interval=0.5, melee_range=1.0),
    dict(id="tallnut", name_zh="高坚果", behavior="wall", hp_mul=2.0),
    dict(id="umbrellaLeaf", name_zh="伞叶", behavior="support", hp_mul=0.6),
    dict(id="twinsunflower", name_zh="双子向日葵", behavior="produce", sun_value=50, sun_interval=24.0),
    dict(id="gatlingpea", name_zh="机枪射手", behavior="shoot", projectile="pea", dmg=20, interval=0.35),
    dict(id="splitpea", name_zh="裂荚射手", behavior="shoot", projectile="pea", dmg=20, interval=1.4),
    dict(id="starfruit", name_zh="杨桃", behavior="lob", projectile="lob", dmg=20, interval=1.5, extra={"element": "wind"}),
]

PLANT_BEHAVIOR_ZH = {
    "shoot": "远程攻击", "lob": "抛射", "boomerang": "回旋镖", "produce": "产阳光",
    "wall": "阻挡", "instant": "爆炸", "fume": "近程穿透", "chomp": "吞噬",
    "mine": "地雷", "support": "辅助",
}

# 我们 id -> 真实数据里的查找候选（codename / RTID 别名 / 图鉴名）
PLANT_ALIASES = {
    "iceshroom": ["iceshroom", "ice_shroom", "glaciershroom", "iceburg", "iceberglettuce"],
    "cattail": ["cattail", "homingthistle"],
    "magnifyinggrass": ["magnifyinggrass", "magnifying_grass"],
    "bonskchoy": ["bonkchoy"],
    "umbrellaLeaf": ["umbrellaleaf", "umbrella_leaf"],
    "twinsunflower": ["twinsunflower", "sunflowertwin", "twinsun"],
    "gatlingpea": ["gatlingpea", "gatling_pea"],
    "splitpea": ["splitpea", "split_pea"],
    "starfruit": ["starfruit", "star_fruit"],
    "potatomine": ["potatomine", "potato_mine"],
    "snowpea": ["snowpea", "snow_pea"],
    "cabbagepult": ["cabbagepult", "cabbage_pult"],
    "kernelpult": ["kernelpult", "kernel_pult"],
    "melonpult": ["melonpult", "melon_pult"],
    "wintermelon": ["wintermelon", "winter_melon"],
    "fumeshroom": ["fumeshroom", "fume_shroom"],
    "sunshroom": ["sunshroom", "sun_shroom"],
    "threepeater": ["threepeater", "three_peater"],
    "spikeweed": ["spikeweed", "spike_weed"],
    "tallnut": ["tallnut", "tall_nut"],
    "wallnut": ["wallnut", "wall_nut"],
    "cherrybomb": ["cherrybomb", "cherry_bomb"],
    "jalapeno": ["jalapeno", "jalapeño"],
    "chomper": ["chomper"],
    "bloomerang": ["bloomerang"],
    "repeater": ["repeater"],
    "peashooter": ["peashooter"],
    "sunflower": ["sunflower"],
    "torchwood": ["torchwood"],
    "squash": ["squash"],
}

# 真实图鉴伤害覆盖（PlantAlmanac Elements 里 DAMAGE），部分植物没有，用上面的 dmg
REAL_NAME_FIX = {
    "fumeshroom": "大喷菇", "sunshroom": "阳光菇", "iceshroom": "寒冰菇",
    "cattail": "猫尾草", "magnifyinggrass": "魔术菇", "umbrellaLeaf": "伞叶",
    "bonskchoy": "菜问",
}


def build_plants():
    props = alias_map("json__Objects__PlantProps.json")
    almanac = {rtid_alias(o.get("aliases", [""])[0]) or str(o.get("aliases", [""])[0]).lower():
               (o.get("objdata") or {}) for o in objects("json__Objects__PlantAlmanac.json")}
    features = feature_list("json__Features__PlantFeatures.json", "PLANTS")
    feat_by_code = {str(f.get("CODENAME", "")).lower(): f for f in features}

    out = []
    for i, spec in enumerate(PLANT_SPECS):
        pid = spec["id"]
        cands = [c.lower() for c in PLANT_ALIASES.get(pid, [pid])]
        feat = None
        for c in cands:
            feat = feat_by_code.get(c)
            if feat:
                break
        prop = None
        for c in cands:
            prop = props.get(c)
            if prop:
                break
        alm = None
        for c in cands:
            alm = almanac.get(c)
            if alm:
                break

        name_zh = spec["name_zh"]
        name_en = (feat or {}).get("NAME", {}).get("en") or pid.replace("_", " ").title()
        cost = int((prop or {}).get("SunCost") or 100)
        cooldown = float((prop or {}).get("Cooldown") or 5.0)
        hp = float((prop or {}).get("Toughness") or 300)
        if spec.get("hp_mul"):
            hp *= float(spec["hp_mul"])
        interval = float(spec.get("interval") or (prop or {}).get("ShootInterval") or 1.4)
        damage = float(spec.get("dmg") or 20)
        # 图鉴里的 DAMAGE 更贴近实际（豌豆 20、西瓜 80 等）
        for e in (alm or {}).get("Elements") or []:
            if str(e.get("TYPE", "")).upper() == "DAMAGE" and e.get("VALUE"):
                try:
                    val = float(e["VALUE"])
                    if spec.get("behavior") in ("shoot", "lob", "boomerang", "fume"):
                        damage = val
                except (TypeError, ValueError):
                    pass
        desc = ((alm or {}).get("Introduction") or {}).get("zh") or ""
        tags = list((feat or {}).get("TAGS") or [])
        family = (prop or {}).get("Family") or PLANT_BEHAVIOR_ZH.get(spec["behavior"], "")
        entry = {
            "id": pid,
            "name_zh": name_zh,
            "name_en": name_en,
            "cost": cost,
            "cooldown": round(cooldown, 3),
            "hp": int(round(hp)),
            "family": family or "植物",
            "art": f"plants/{art_name_for(pid)}",
            "behavior": spec["behavior"],
            "damage": round(damage, 2),
            "interval": round(interval, 3),
            "projectile": spec.get("projectile", "pea"),
            "rows": list(spec.get("rows") or [0]),
            "pierce": bool(spec.get("pierce")),
            "tags": tags or [spec["behavior"]],
            "desc_zh": desc or f"{name_zh}，{PLANT_BEHAVIOR_ZH.get(spec['behavior'], '植物')}。",
            "almanac_no": i + 1,
            "sun_value": int(spec.get("sun_value") or 25),
            "sun_interval": float(spec.get("sun_interval") or 24.0),
            "splash": float(spec.get("splash") or 0.0),
            "slow": float(spec.get("slow") or 0.0),
            "melee_range": float(spec.get("melee_range") or 1.0),
            "delay": float(spec.get("delay") or 0.0),
            "plantfood": False,
        }
        entry.update(spec.get("extra") or {})
        out.append(entry)
    return out


ART_NAMES = {
    "peashooter": "PeashooterPLANT", "sunflower": "SunflowerPLANT", "wallnut": "WallnutPLANT",
    "potatomine": "PotatoMinePLANT", "snowpea": "SnowPeaPLANT", "chomper": "ChomperPLANT",
    "repeater": "RepeaterPLANT", "bloomerang": "BloomerangPLANT", "cabbagepult": "CabbagePultPLANT",
    "kernelpult": "KernelPultPLANT", "melonpult": "MelonPultPLANT", "wintermelon": "WinterMelonPLANT",
    "fumeshroom": "FumeShroomPLANT", "sunshroom": "SunShroomPLANT", "iceshroom": "GlacierShroomPLANT",
    "threepeater": "ThreePeaterPLANT", "torchwood": "TorchwoodPLANT", "jalapeno": "JalapenoPLANT",
    "cherrybomb": "CherryBombPLANT", "squash": "SquashPLANT", "spikeweed": "SpikeweedPLANT",
    "cattail": "HomingThistlePLANT", "magnifyinggrass": "MagnifyingGrassPLANT",
    "bonkchoy": "BonkChoyPLANT", "tallnut": "TallnutPLANT", "umbrellaLeaf": "UmbrellaLeafPLANT",
    "twinsunflower": "SunflowerTwinPLANT", "gatlingpea": "GatlingPeaPLANT",
    "splitpea": "SplitPeaPLANT", "starfruit": "StarFruitPLANT",
}


def art_name_for(pid: str) -> str:
    return ART_NAMES.get(pid, pid)


# ---------------------------------------------------------------- 僵尸表
ZOMBIE_SPECS = [
    # id, 中文名, art prefab, armature, 典型 hp 覆盖, 护甲段
    dict(id="basic", name_zh="普通僵尸", art="zombies/BasicZOMBIE", armature="BasicZombie", alias="tutorial"),
    dict(id="conehead", name_zh="路障僵尸", art="zombies/BasicZOMBIE", armature="Cone", alias="tutorial_armor1", armor=[{"name": "路障", "hp": 370, "art": "armors/BasicConeARMOR"}]),
    dict(id="buckethead", name_zh="铁桶僵尸", art="zombies/BasicZOMBIE", armature="Bucket", alias="tutorial_armor2", armor=[{"name": "铁桶", "hp": 1100, "art": "armors/BasicBucketARMOR"}]),
    dict(id="flag", name_zh="旗帜僵尸", art="zombies/BasicFlagZOMBIE", armature=None, alias="flag"),
    dict(id="mummy", name_zh="木乃伊僵尸", art="zombies/EgyptBasicZOMBIE", armature=None, alias="mummy"),
    dict(id="mummy_armor1", name_zh="木乃伊路障僵尸", art="zombies/EgyptBasicZOMBIE", armature="Cone", alias="mummy_armor1", armor=[{"name": "木乃伊护甲", "hp": 370, "art": "armors/EgyptConeARMOR"}]),
    dict(id="mummy_armor2", name_zh="木乃伊铁桶僵尸", art="zombies/EgyptBasicZOMBIE", armature="Bucket", alias="mummy_armor2", armor=[{"name": "木乃伊铁甲", "hp": 1100, "art": "armors/EgyptBucketARMOR"}]),
    dict(id="pirate", name_zh="海盗僵尸", art="zombies/PirateBasicZOMBIE", armature=None, alias="pirate"),
    dict(id="pirate_armor1", name_zh="海盗路障僵尸", art="zombies/PirateBasicZOMBIE", armature="Cone", alias="pirate_armor1", armor=[{"name": "海盗护甲", "hp": 370, "art": "armors/PirateConeARMOR"}]),
    dict(id="cowboy", name_zh="牛仔僵尸", art="zombies/CowboyBasicZOMBIE", armature=None, alias="cowboy"),
    dict(id="cowboy_armor1", name_zh="牛仔路障僵尸", art="zombies/CowboyBasicZOMBIE", armature="Cone", alias="cowboy_armor1", armor=[{"name": "牛仔护甲", "hp": 370, "art": "armors/CowboyConeARMOR"}]),
    dict(id="future", name_zh="未来僵尸", art="zombies/FutureBasicZOMBIE", armature=None, alias="future"),
    dict(id="future_armor1", name_zh="未来路障僵尸", art="zombies/FutureBasicZOMBIE", armature="Cone", alias="future_armor1", armor=[{"name": "未来护甲", "hp": 370, "art": "armors/FutureConeARMOR"}]),
    dict(id="dark", name_zh="黑暗僵尸", art="zombies/DarkBasicZOMBIE", armature=None, alias="dark"),
    dict(id="dark_armor1", name_zh="黑暗路障僵尸", art="zombies/DarkBasicZOMBIE", armature="Cone", alias="dark_armor1", armor=[{"name": "黑暗护甲", "hp": 370, "art": "armors/DarkConeARMOR"}]),
    dict(id="beach", name_zh="沙滩僵尸", art="zombies/BeachBasicZOMBIE", armature=None, alias="beach"),
    dict(id="iceage", name_zh="冰河僵尸", art="zombies/IceageBasicZOMBIE", armature=None, alias="iceage"),
    dict(id="lostcity", name_zh="失落僵尸", art="zombies/LostcityBasicZOMBIE", armature=None, alias="lostcity"),
    dict(id="kongfu", name_zh="功夫僵尸", art="zombies/KongfuBasicZOMBIE", armature=None, alias="kongfu"),
    dict(id="eighties", name_zh="八十年代僵尸", art="zombies/EightiesBasicZOMBIE", armature=None, alias="eighties"),
    dict(id="dino", name_zh="恐龙僵尸", art="zombies/DinoBasicZOMBIE", armature=None, alias="dino"),
    dict(id="gargantuar", name_zh="巨人僵尸", art="zombies/GargantuarZOMBIE", armature=None, alias="gargantuar", hp=3000, speed=0.09),
    dict(id="football", name_zh="橄榄球僵尸", art="zombies/AllstarZOMBIE", armature=None, alias="allstar", hp=600, speed=0.3, armor=[{"name": "橄榄球头盔", "hp": 600, "art": ""}]),
    dict(id="newspaper", name_zh="读报僵尸", art="zombies/ModernNewspaperZOMBIE", armature=None, alias="newspaper", hp=190),
]


def find_prop(props: dict, alias: str) -> dict:
    if alias in props:
        return props[alias]
    for k, v in props.items():
        if k == alias or k.startswith(alias + "_"):
            return v
    return {}


ZOMBIE_NAME_ZH_FIX = {
    "basic": "普通僵尸", "conehead": "路障僵尸", "buckethead": "铁桶僵尸", "flag": "旗帜僵尸",
    "mummy": "木乃伊僵尸", "pirate": "海盗僵尸", "cowboy": "牛仔僵尸", "future": "未来僵尸",
    "dark": "黑暗僵尸", "beach": "沙滩僵尸", "iceage": "冰河僵尸", "lostcity": "失落僵尸",
    "kongfu": "功夫僵尸", "eighties": "八十年代僵尸", "dino": "恐龙僵尸",
    "gargantuar": "巨人僵尸", "football": "橄榄球僵尸", "newspaper": "读报僵尸",
}


def build_zombies():
    props = alias_map("json__Objects__ZombieProps.json")
    feats = feature_list("json__Features__ZombieFeatures.json", "ZOMBIES")
    feat_by_code = {str(f.get("CODENAME", "")).lower(): f for f in feats}
    almanac = load("json__Features__ZombieAlmanac.json") if (SRC / "json__Features__ZombieAlmanac.json").exists() else {}
    out = []
    for spec in ZOMBIE_SPECS:
        alias = str(spec.get("alias") or spec["id"]).lower()
        prop = find_prop(props, alias)
        lookup = alias
        feat = None
        for key in (alias, spec["id"]):
            feat = feat_by_code.get(key)
            if feat:
                break
        if feat:
            name_en = (feat.get("NAME") or {}).get("en") or spec["id"].title()
            name_zh = ZOMBIE_NAME_ZH_FIX.get(spec["id"], (feat.get("NAME") or {}).get("zh") or spec["name_zh"])
        else:
            name_en = spec["id"].replace("_", " ").title()
            name_zh = spec["name_zh"]
        hp = float(spec.get("hp") or prop.get("Toughness") or 190)
        speed = float(spec.get("speed") or prop.get("WalkSPS") or 0.185)
        eat = float(prop.get("EatDPS") or 100)
        armor = [dict(a) for a in (spec.get("armor") or [])]
        # 真实的数据表里 StartingArmors 更准，能查到就覆盖
        starting = prop.get("StartingArmors") or []
        if starting and not armor:
            armors = alias_map("json__Objects__ArmorProps.json")
            for a in starting:
                ap = armors.get(str(a).lower()) or {}
                if ap:
                    armor.append({"name": str(a), "hp": float(ap.get("Toughness") or 370), "art": ""})
        desc = ""
        try:
            alm_items = almanac.get("ALMANAC") or []
            for it in alm_items if isinstance(alm_items, list) else []:
                if isinstance(it, dict) and str(it.get("ID", "")).lower() in (alias, spec["id"]):
                    desc = ((it.get("Introduction") or {}).get("zh") or "")
                    break
        except Exception:
            desc = ""
        out.append({
            "id": spec["id"],
            "name_zh": name_zh,
            "name_en": name_en,
            "hp": int(round(hp)),
            "speed": round(speed, 4),
            "eat_dps": round(eat, 1),
            "armor": armor,
            "behavior": "walk",
            "art": spec["art"],
            "armature": spec.get("armature"),
            "cost": 100,
            "desc_zh": desc or f"{name_zh}，慢吞吞地走向你的脑子。",
        })
    return out


# ---------------------------------------------------------------- 世界表
WORLDS = [
    dict(id="frontyard", name_zh="前院", name_en="Frontyard", order=1, levels=10,
         desc_zh="一切开始的地方。阳光、草坪，还有从篱笆缝里钻出来的僵尸。",
         bg_tint=[86, 156, 74], map="world/frontyard", lawn="lawn/frontyard"),
    dict(id="egypt", name_zh="神秘埃及", name_en="Ancient Egypt", order=2, levels=10,
         desc_zh="沙暴深处的金字塔。木乃伊在走廊里游荡，圣甲虫在阳光下闪光。",
         bg_tint=[201, 164, 92], map="world/egypt", lawn="lawn/egypt"),
    dict(id="pirate", name_zh="海盗港湾", name_en="Pirate Seas", order=3, levels=10,
         desc_zh="咸腥的海风与摇晃的甲板。海盗僵尸踩着木板，一步步逼近船舷。",
         bg_tint=[64, 132, 176], map="world/pirate", lawn="lawn/pirate"),
    dict(id="cowboy", name_zh="狂野西部", name_en="Wild West", order=4, levels=10,
         desc_zh="正午的尘土、铁轨和仙人掌。牛仔僵尸拔枪的姿势比走路还慢。",
         bg_tint=[176, 126, 80], map="world/cowboy", lawn="lawn/cowboy"),
    dict(id="future", name_zh="未来世界", name_en="Far Future", order=5, levels=10,
         desc_zh="霓虹与金属的草坪。全息投影下，未来僵尸正排队走进你的花园。",
         bg_tint=[92, 108, 168], map="world/future", lawn="lawn/future"),
    dict(id="dark", name_zh="黑暗时代", name_en="Dark Ages", order=6, levels=10,
         desc_zh="月光下的古堡废墟。墓穴在夜里打开，黑暗僵尸循着烛光而来。",
         bg_tint=[88, 92, 112], map="world/dark", lawn="lawn/dark"),
    dict(id="beach", name_zh="巨浪沙滩", name_en="Big Wave Beach", order=7, levels=10,
         desc_zh="潮水拍岸，遮阳伞歪斜。沙滩僵尸从浪花里冒出来，带着一身湿沙。",
         bg_tint=[96, 176, 190], map="world/beach", lawn="lawn/beach"),
    dict(id="lostcity", name_zh="失落之城", name_en="Lost City", order=8, levels=10,
         desc_zh="藤蔓覆盖的遗迹，黄金在暗处发亮。失落僵尸守护着早已被遗忘的宝藏。",
         bg_tint=[132, 168, 96], map="world/lostcity", lawn="lawn/lostcity"),
]


def build_worlds():
    return [dict(w) for w in WORLDS]


# ---------------------------------------------------------------- 关卡表
# 每个世界挑 10 关（在真实关卡里均匀取样，保证难度跨度）。
LEVEL_PLAN = {
    "frontyard": ("frontyard", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
    "egypt": ("egypt", [1, 4, 7, 10, 13, 16, 19, 22, 25, 28]),
    "pirate": ("pirate", [1, 4, 7, 10, 13, 16, 19, 22, 25, 28]),
    "cowboy": ("cowboy", [1, 4, 7, 10, 13, 16, 19, 22, 25, 28]),
    "future": ("future", [1, 4, 7, 10, 13, 16, 19, 22, 25, 28]),
    "dark": ("dark", [1, 4, 7, 10, 13, 16, 19, 22, 25, 28]),
    "beach": ("beach", [1, 4, 7, 10, 13, 16, 19, 22, 25, 28]),
    "lostcity": ("lostcity", [1, 4, 7, 10, 13, 16, 19, 22, 25, 28]),
}

ZOMBIE_RTID_MAP = {
    "tutorial": "basic", "tutorial_armor1": "conehead", "tutorial_armor2": "buckethead",
    "tutorial_armor3": "buckethead", "tutorial_armor4": "buckethead", "flag": "flag",
    "mummy": "mummy", "mummy_armor1": "mummy_armor1", "mummy_armor2": "mummy_armor2",
    "mummy_armor4": "mummy_armor2", "ra": "mummy", "explorer": "mummy",
    "pirate": "pirate", "pirate_armor1": "pirate_armor1", "pirate_armor2": "pirate_armor1",
    "cowboy": "cowboy", "cowboy_armor1": "cowboy_armor1", "cowboy_armor2": "cowboy_armor1",
    "future": "future", "future_armor1": "future_armor1", "future_armor2": "future_armor1",
    "dark": "dark", "dark_armor1": "dark_armor1", "dark_armor2": "dark_armor1",
    "beach": "beach", "beach_armor1": "beach", "iceage": "iceage", "iceage_armor1": "iceage",
    "lostcity": "lostcity", "lostcity_armor1": "lostcity",
    "kongfu": "kongfu", "kongfu_armor1": "kongfu", "eighties": "eighties", "eighties_armor1": "eighties",
    "dino": "dino", "dino_armor1": "dino",
    "gargantuar": "gargantuar", "allstar": "football", "football": "football",
    "newspaper": "newspaper", "prospector": "cowboy", "pianist": "dark",
    "jester": "dark", "wizard": "dark", "knight": "dark", "imp": "dark",
    "tombraiser": "mummy", "pharaoh": "mummy", "turban": "mummy",
    "swashbuckler": "pirate", "barrel": "pirate", "seagull": "pirate",
    "surfer": "beach", "fisherman": "beach", "snorkel": "beach", "octopus": "beach",
    "hunter": "iceage", "troglobite": "iceage", "dodo": "iceage", "weasel": "iceage",
    "bug": "lostcity", "relic": "lostcity", "excavator": "lostcity", "parasol": "lostcity",
    "gunner": "future", "jetpack": "future", "emperor": "future", "mech": "future",
}


def pick_world_levels(world: str) -> list[tuple[int, dict]]:
    files = sorted((SRC).glob(f"levels__{world}*.json"))
    by_num = {}
    for p in files:
        m = re.match(rf"levels__{world}(\d+)\.json$", p.name)
        if m:
            by_num[int(m.group(1))] = p
    return by_num


def parse_level(path: Path) -> dict | None:
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    objs = d.get("objects") or []
    deck: list[str] = []
    waves: list[dict] = []
    level_no = None
    title = ""
    wave_props = {}
    spawn_by_alias = {}
    for o in objs:
        cls = o.get("objclass")
        aliases = o.get("aliases") or []
        od = o.get("objdata") or {}
        if cls == "LevelDefinition":
            title = (od.get("Description") or "").strip("[]").replace("_", " ").title()
            try:
                level_no = int(od.get("LevelNumber"))
            except (TypeError, ValueError):
                level_no = None
        elif cls == "SeedBankProperties":
            decks = od.get("CardDecks") or {}
            rec = decks.get("Recommended") or []
            if rec:
                deck = [str(x) for x in (rec[0].get("Plants") or [])]
        elif cls == "WaveManagerProperties":
            wave_props = od
            for w in od.get("Waves") or []:
                a = rtid_alias(w)
                if a:
                    pass
        elif cls == "SpawnZombiesJitteredWaveActionProps":
            if aliases:
                spawn_by_alias[str(aliases[0])] = od
    # 波次：Waves 是 RTID 列表
    wave_refs = [rtid_alias(w) for w in (wave_props.get("Waves") or [])]
    flag_interval = int(wave_props.get("FlagWaveInterval") or 10)
    wave_count = int(wave_props.get("WaveCount") or len(wave_refs) or 10)
    for idx, ref in enumerate(wave_refs or [f"Wave{i+1}" for i in range(wave_count)]):
        od = spawn_by_alias.get(ref) or spawn_by_alias.get(f"Wave{idx+1}") or {}
        zs = []
        for z in od.get("Zombies") or []:
            alias = rtid_alias(z.get("Type") if isinstance(z, dict) else z)
            zid = ZOMBIE_RTID_MAP.get(alias)
            if zid:
                zs.append({"type": zid})
        if not zs:
            zs = [{"type": "basic"}]
        is_flag = (idx + 1) % max(1, flag_interval // max(1, wave_count // 10 or 1)) == 0 if False else False
        waves.append({"delay": 20.0 if idx == 0 else 18.0,
                      "flag": (idx + 1) in (wave_count,),
                      "zombies": zs})
    if not waves:
        return None
    return {"level_no": level_no, "title": title, "deck": deck, "waves": waves}


def dedupe_deck(deck: list[str]) -> list[str]:
    out = []
    for p in deck:
        p = str(p).strip().lower()
        if not p or p in out:
            continue
        out.append(p)
    return out


def build_levels(plants_by_id: dict[str, dict]):
    valid_plants = set(plants_by_id)
    default_deck = ["sunflower", "peashooter", "wallnut", "potatomine", "snowpea", "chomper"]
    out = []
    for world, (prefix, positions) in LEVEL_PLAN.items():
        by_num = pick_world_levels(prefix)
        if not by_num:
            continue
        nums = sorted(by_num)
        # 在真实关卡里按可用数量取样
        chosen = []
        for i in range(10):
            want = positions[i] if i < len(positions) else i + 1
            if want in by_num:
                chosen.append(want)
            else:
                # 退化为均匀取样
                idx = min(len(nums) - 1, round(i * (len(nums) - 1) / 9))
                chosen.append(nums[idx])
        for i, num in enumerate(chosen):
            parsed = parse_level(by_num[num])
            if not parsed:
                continue
            deck = [p for p in dedupe_deck(parsed["deck"]) if p in valid_plants]
            if len(deck) < 3:
                deck = [p for p in default_deck if p in valid_plants]
            out.append({
                "id": f"{world}_{i+1}",
                "world": world,
                "index": i + 1,
                "title": f"{WORLDS_BY_ID[world]['name_zh']} 第 {i+1} 关",
                "sun": 250 if i < 3 else 200 if i < 6 else 150,
                "deck": deck[:8],
                "waves": parsed["waves"],
                "flags": 1,
                "seed_bank": 6,
                "source": f"{prefix}{num}",
            })
    return out


WORLDS_BY_ID = {w["id"]: w for w in WORLDS}


# ---------------------------------------------------------------- 图鉴
def build_almanac(plants, zombies, plant_almanac_objs):
    intro = {}
    for o in plant_almanac_objs:
        a = str((o.get("aliases") or [""])[0]).lower()
        zh = ((o.get("objdata") or {}).get("Introduction") or {}).get("zh")
        if a and zh:
            intro[a] = zh
    out = {"plants": {}, "zombies": {}}
    for p in plants:
        if p.get("desc_zh"):
            out["plants"][p["id"]] = p["desc_zh"]
    zalm = {}
    try:
        d = load("json__Features__ZombieAlmanac.json") if (SRC / "json__Features__ZombieAlmanac.json").exists() else {}
        for it in d.get("ALMANAC") or []:
            if isinstance(it, dict):
                zalm[str(it.get("ID", "")).lower()] = it
    except Exception:
        pass
    for z in zombies:
        if z.get("desc_zh"):
            out["zombies"][z["id"]] = z["desc_zh"]
    return out


# ---------------------------------------------------------------- main
def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "levels").mkdir(exist_ok=True)
    for old in (OUT / "levels").glob("*.json"):
        old.unlink()

    plants = build_plants()
    zombies = build_zombies()
    worlds = build_worlds()
    pq = {p["id"]: p for p in plants}
    levels = build_levels(pq)
    almanac = build_almanac(plants, zombies, objects("json__Objects__PlantAlmanac.json"))

    json.dump(plants, open(OUT / "plants.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(zombies, open(OUT / "zombies.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(worlds, open(OUT / "worlds.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(almanac, open(OUT / "almanac.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for lv in levels:
        p = OUT / "levels" / f"{lv['id']}.json"
        json.dump(lv, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"plants {len(plants)}, zombies {len(zombies)}, worlds {len(worlds)}, levels {len(levels)}")
    # 自检
    problems = []
    for lv in levels:
        if not lv["deck"]:
            problems.append(f"{lv['id']}: empty deck")
        if not lv["waves"]:
            problems.append(f"{lv['id']}: no waves")
        for w in lv["waves"]:
            for z in w["zombies"]:
                if z["type"] not in {x['id'] for x in zombies}:
                    problems.append(f"{lv['id']}: unknown zombie {z['type']}")
    for p in plants:
        if p["id"] not in {x['id'] for x in plants}:
            problems.append(p["id"])
    print("problems:", problems[:10] or "none", "count", len(problems))


if __name__ == "__main__":
    main()
