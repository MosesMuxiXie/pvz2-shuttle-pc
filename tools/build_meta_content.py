# -*- coding: utf-8 -*-
"""生成元内容数据文件（stars / minigames / bosses / shop）。

数据来源：work/obb_packages/*.json（RTON 导出的 OBB 包）与 work/expansion_scan.json。
输出：content/stars.json、content/minigames.json、content/bosses.json、content/shop.json。
运行后自动做一次结构/引用自检，结果写入 work/meta_content_report.txt。

用法：
    python tools/build_meta_content.py
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # PvZ2SHUTTLE/
WORK = ROOT.parent / "work"                            # 工作区 work/
CONTENT = ROOT / "content"
OBB = WORK / "obb_packages"

PENDING_WORLDS = {"kongfu", "plantagenet"}

ALLOWED_STAR_TYPES = {
    "beat", "mowers", "kill", "plants_lost", "plants_max",
    "sun_max", "sun_produced", "time", "score",
}

# 新植物（由 Content 代理并行加入 plants.json）
NEW_PLANTS = [
    ("iris", "鸢尾"),
    ("rosemary", "迷迭香"),
    ("snowlotus", "雪莲"),
    ("wildflower", "野花"),
    ("olivewood", "橄榄木"),
    ("astrofruit", "星果"),
    ("chrysanthea", "金菊"),
    ("doominator", "毁灭者"),
    ("helioscabbage", "太阳卷心菜"),
    ("paradoxpult", "悖论投手"),
    ("tubiflora", "管花"),
    ("vortexmelon", "漩涡西瓜"),
    ("cheesestrawberry", "芝士草莓"),
    ("oolongpeach", "乌龙桃"),
    ("succulentgrape", "多肉葡萄"),
    ("doublepassion", "双生百香果"),
    ("fireflerry", "火焰莓"),
    ("frozenpear", "冰冻梨"),
    ("solarflare", "太阳耀斑"),
    ("taraxacum", "蒲公英"),
]

# 砸罐子：OBB stage -> 我们世界
VASE_WORLD_RULES = [
    ("frontlawn", "frontyard"), ("carnival", "frontyard"), ("child", "frontyard"),
    ("egyptnights", "egypt"), ("egypt", "egypt"),
    ("pirate", "pirate"),
    ("west", "cowboy"),
    ("beach", "beach"),
    ("future", "future"),
    ("dark", "dark"), ("steamub", "dark"),
    ("kongfu", "chinesegarden"),
    ("heian", "chinesegarden"), ("jttw", "chinesegarden"),
    ("gta", "losantosvice"),
    ("lunar", "lunarrainbowmarket"), ("rift", "lunarrainbowmarket"),
    ("penacony", "lunarrainbowmarket"),
]

# 植物关键词补充映射（OBB 名 -> 我们植物 id）
PLANT_EXTRA = {
    "puffshroom": "sunshroom", "magnetshroom": "fumeshroom",
    "hypnoshroom": "sunshroom", "evilshroom": "sunshroom",
    "holonut": "wallnut", "primalwallnut": "wallnut", "gumnut": "wallnut",
    "phatbeet": "wallnut", "endurian": "wallnut", "rheumnobile": "tallnut",
    "pvine": "umbrellaleaf", "powervine": "umbrellaleaf",
    "citron": "cabbagepult", "bowlingbulb": "starfruit",
    "banana": "cherry_bomb", "lavaguava": "jalapeno",
    "tanglekelp": "squash", "chilibean": "jalapeno",
    "spikerock": "spikeweed", "springbean": "snowpea",
    "celerystalker": "bonkchoy", "wasabiwhip": "bonkchoy",
    "snowdrop": "snowpea", "sunbean": "sunflower",
    "futurebubuseed": "sunflower", "cutebubuseed": "sunflower",
    "enlightenmint": "sunflower", "enforcemint": "sunflower",
    "containmint": "sunflower", "peppermint": "sunflower",
    "bombardmint": "sunflower", "powerlily": "sunflower",
    "teleportatomine": "potatomine", "primalpotatomine": "potatomine",
    "explodeonut": "cherry_bomb", "tombtangler": "chomper",
    "kiwibeast": "chomper", "imppear": "squash", "inferno": "jalapeno",
    "aloe": "sunflower", "xshot": "repeater", "laser_bean": "peashooter",
    "slingpea": "cabbagepult", "blover": "bloomerang",
    "stickybombrice": "cherry_bomb", "waterrabbit": "snowpea",
    "akee": "peashooter", "dartichoke": "peashooter",
    "heathseeker": "peashooter", "poisonpeashooter": "peashooter",
    "magnifyinggrass": "magnifyinggrass",
}


# ---------------------------------------------------------------- 基础工具
def load_json(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def pkg_path(name: str) -> Path:
    """'pkg_0415' / 'pkg_0415_LevelDefinition.json' -> 完整路径。"""
    name = str(name or "")
    if not name:
        return OBB / "_missing_"
    if name.endswith(".json"):
        return OBB / name
    return OBB / f"{name}_LevelDefinition.json"


def safe_int(value, default=0) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return default


def norm(name: str) -> str:
    """OBB 类型名归一：小写、去 _ori 后缀、去 unused 尾部编号。"""
    n = str(name or "").strip().lower()
    n = re.sub(r"_ori$", "", n)
    if n.startswith("unused"):
        n = re.sub(r"\d+$", "", n).rstrip("_")
    return n


# ---------------------------------------------------------------- 内容读取
def read_content():
    worlds = load_json(CONTENT / "worlds.json")
    plants = load_json(CONTENT / "plants.json")
    zombies = load_json(CONTENT / "zombies.json")
    levels = [load_json(p) for p in sorted((CONTENT / "levels").glob("*.json"))]
    return worlds, plants, zombies, levels


def world_meta(worlds):
    meta = {}
    for w in worlds:
        meta[w["id"]] = {
            "name_zh": w.get("name_zh", w["id"]),
            "order": safe_int(w.get("order"), 99),
        }
    if "plantagenet" not in meta:
        meta["plantagenet"] = {"name_zh": "王朝", "order": 12}
    return meta


def zombie_index(zombies):
    by_id = {z["id"]: z for z in zombies}
    by_world = {}
    for z in zombies:
        for tag in z.get("tags") or []:
            if tag in ("global",):
                continue
            by_world.setdefault(tag, []).append(z["id"])
    return by_id, by_world


def plant_index(plants):
    return {p["id"]: p for p in plants}


# ---------------------------------------------------------------- 星章
RTID_RE = re.compile(r"RTID\(([^@)]+)@")


def challenge_objects(doc):
    """返回 (challenges 二维列表, alias -> objdata, alias -> objclass)。"""
    challenges = None
    props = {}
    classes = {}
    for obj in doc.get("objects") or []:
        cls = str(obj.get("objclass") or "")
        data = obj.get("objdata") or {}
        for alias in obj.get("aliases") or []:
            props[str(alias)] = data
            classes[str(alias)] = cls
        if "StarChallengeModuleProperties" in cls and "Challenges" in data:
            challenges = data["Challenges"]
    return challenges, props, classes


def star_condition_from(rtids, props, classes):
    """从一组 RTID 中挑一个可表达的星章条件（按优先级）。"""
    found = {}
    for rtid in rtids:
        m = RTID_RE.search(str(rtid))
        if not m:
            continue
        alias = m.group(1)
        data = props.get(alias) or {}
        cls = classes.get(alias) or ""
        if cls == "StarChallengeKillZombiesInTimeProps" and data.get("ZombiesToKill"):
            found.setdefault("kill", (safe_int(data.get("ZombiesToKill")),
                                      safe_int(data.get("Time"))))
        elif cls == "StarChallengeSunUsedProps" and data.get("MaximumSun"):
            found.setdefault("sun_max", (safe_int(data.get("MaximumSun")), 0))
        elif cls == "StarChallengeSimultaneousPlantsProps" and data.get("MaximumPlants"):
            found.setdefault("plants_max", (safe_int(data.get("MaximumPlants")), 0))
        elif cls == "StarChallengePlantsLostProps" and data.get("MaximumPlantsLost"):
            found.setdefault("plants_lost", (safe_int(data.get("MaximumPlantsLost")), 0))
        elif cls == "StarChallengeTargetScoreProps" and data.get("TargetScore"):
            found.setdefault("score", (safe_int(data.get("TargetScore")), 0))
        elif cls == "StarChallengeLevelTimerProperties" and data.get("TimeLimit"):
            found.setdefault("time", (safe_int(data.get("TimeLimit")), 0))
        elif cls == "StarChallengeSunProducedProps" and data.get("TargetSun"):
            found.setdefault("sun_produced", (safe_int(data.get("TargetSun")), 0))
    for kind, payload in priority_conditions(found):
        return kind, payload
    return None


def priority_conditions(found):
    order = ["kill", "sun_max", "plants_max", "plants_lost", "score", "time",
             "sun_produced"]
    out = []
    for key in order:
        if key in found:
            out.append((key, found[key]))
    return out


def star_text(kind, value, extra):
    if kind == "beat":
        return "通关"
    if kind == "mowers":
        return "不损失小推车"
    if kind == "kill":
        return f"{extra} 秒内消灭 {value} 只僵尸" if extra else f"消灭 {value} 只僵尸"
    if kind == "sun_max":
        return f"阳光消耗不超过 {value}"
    if kind == "plants_max":
        return f"同时存活植物不超过 {value} 株"
    if kind == "plants_lost":
        return f"损失植物不超过 {value} 株"
    if kind == "score":
        return f"得分达到 {value}"
    if kind == "time":
        return f"{value} 秒内通关"
    if kind == "sun_produced":
        return f"累计生产 {value} 阳光"
    return "完成挑战"


def star_cond(kind, value, extra=0):
    """生成星章条件，同时写入运行时 _evaluate_stars 读取的别名字段。"""
    cond = {"type": kind, "value": int(value),
            "text_zh": star_text(kind, value, extra)}
    if kind == "mowers":
        cond["max"] = 0
    elif kind == "kill":
        cond["count"] = int(value)
        if extra:
            cond["seconds"] = int(extra)
    elif kind == "sun_max":
        cond["max"] = int(value)
    elif kind == "plants_lost":
        cond["max"] = int(value)
    elif kind == "plants_max":
        # 语义为“同时存活不超过 N 株”，运行时若按 count 判断会反向，故只写 value
        pass
    elif kind == "score":
        cond["target"] = int(value)
    elif kind == "sun_produced":
        cond["target"] = int(value)
    elif kind == "time":
        cond["seconds"] = int(value)
    return cond


def build_stars(levels, worlds):

    wmeta = world_meta(worlds)
    result = {}
    for lv in levels:
        lid = lv["id"]
        world = lv.get("world", "frontyard")
        index = safe_int(lv.get("index"), 1)
        total_z = 0
        for wave in lv.get("waves") or []:
            total_z += len(wave.get("zombies") or [])
        generic_kill = max(8, min(60, safe_int(total_z * 0.6)))

        third = None
        pkg = (lv.get("extra") or {}).get("package")
        path = pkg_path(pkg)
        if path.exists():
            try:
                doc = load_json(path)
                challenges, props, classes = challenge_objects(doc)
                if challenges:
                    groups = [g for g in challenges if isinstance(g, list)]
                    merged = []
                    for g in groups[1:] if len(groups) >= 3 else groups:
                        merged.extend(g)
                    if merged:
                        third = star_condition_from(merged, props, classes)
            except Exception:
                third = None

        if third is None:
            kind, value, extra = "kill", generic_kill, 0
        else:
            kind, (value, extra) = third
            if kind == "sun_max":
                value = max(300, min(4000, value))
            elif kind == "plants_max":
                value = max(5, min(40, value))
            elif kind == "plants_lost":
                value = max(1, min(10, value))
            elif kind == "score":
                # OBB 的 TargetScore 是原版计分尺度，按本项目击杀/波次计分重标定
                waves = len(lv.get("waves") or [])
                value = max(3000, min(20000, int(total_z * 40 + waves * 200)))
            elif kind == "time":
                value = max(30, min(300, value))
            elif kind == "sun_produced":
                value = max(300, min(10000, value))
            elif kind == "kill":
                value = max(8, min(int(value), max(1, int(total_z * 0.8))))
                extra = int(extra)
                if extra < 15 or extra > 600:
                    extra = 0

        result[lid] = [
            star_cond("beat", 0),
            star_cond("mowers", 5),
            star_cond(kind, value, extra),
        ]

    # 未来世界（关卡文件可能尚未生成）
    have = set(result)
    for i in range(1, 11):
        lid = f"plantagenet_{i}"
        if lid in have:
            continue
        kill = min(40, 12 + 3 * (i - 1))
        result[lid] = [
            star_cond("beat", 0),
            star_cond("mowers", 5),
            star_cond("kill", kill),
        ]

    def sort_key(lid):
        world = lid.rsplit("_", 1)[0]
        try:
            index = int(lid.rsplit("_", 1)[1])
        except Exception:
            index = 0
        return (wmeta.get(world, {}).get("order", 99), world, index)

    return {lid: result[lid] for lid in sorted(result, key=sort_key)}


# ---------------------------------------------------------------- 砸罐子
def map_world_by_stage(stage: str) -> str:
    s = str(stage or "").lower()
    for key, world in VASE_WORLD_RULES:
        if key in s:
            return world
    return "frontyard"


def zombie_role_ids(world: str, by_world, by_id):
    ids = [z for z in by_world.get(world, []) if z in by_id]
    if not ids:
        ids = ["basic"]
    base = next((z for z in ids if not any(
        k in z for k in ("garg", "armor", "imp", "flag", "cone", "bucket"))), ids[0])
    armored1 = next((z for z in ids if "armor1" in z or "cone" in z), base)
    armored2 = next((z for z in ids if "armor2" in z or "bucket" in z), armored1)
    garg = next((z for z in ids if "garg" in z), "gargantuar")
    imp = next((z for z in ids if "imp" in z), base)
    flag = next((z for z in ids if "flag" in z), base)
    return {"base": base, "armored1": armored1, "armored2": armored2,
            "garg": garg, "imp": imp, "flag": flag}


def map_zombie(name: str, world: str, roles) -> str:
    n = norm(name)
    if "gargantuar" in n or "garg" in n:
        return roles["garg"]
    if "imp" in n or "superfan" in n:
        return roles["imp"]
    if "flag" in n:
        return roles["flag"]
    if any(k in n for k in ("armor4", "armor3", "armor2", "bucket", "plate",
                            "shield", "helmet", "hammer", "spear", "trident",
                            "cannon", "barrel", "rocket", "knight")):
        return roles["armored2"]
    if "armor1" in n or "cone" in n:
        return roles["armored1"]
    if "football" in n or "disco" in n:
        return "football" if world == "future" else roles["armored2"]
    if "newspaper" in n and world == "frontyard":
        return "newspaper"
    return roles["base"]


def default_plant(world: str, plants_by_id) -> str:
    table = {
        "frontyard": "peashooter", "egypt": "bloomerang", "pirate": "threepeater",
        "cowboy": "splitpea", "future": "peashooter", "dark": "sunshroom",
        "beach": "peashooter", "lostcity": "peashooter",
        "chinesegarden": "bonkchoy", "losantosvice": "peashooter",
        "lunarrainbowmarket": "peashooter", "kongfu": "bonkchoy",
        "plantagenet": "peashooter",
    }
    zid = table.get(world, "peashooter")
    return zid if zid in plants_by_id else "peashooter"


def map_plant(name: str, world: str, plants_by_id, plant_ids_sorted) -> str:
    n = norm(name)
    if n in plants_by_id:
        return n
    if n in PLANT_EXTRA and PLANT_EXTRA[n] in plants_by_id:
        return PLANT_EXTRA[n]
    for key, pid in PLANT_EXTRA.items():
        if key in n and pid in plants_by_id:
            return pid
    best = None
    for pid in plant_ids_sorted:
        if pid in n or n in pid:
            if best is None or len(pid) > len(best):
                best = pid
    if best:
        return best
    return default_plant(world, plants_by_id)


def vase_props(doc):
    for obj in doc.get("objects") or []:
        cls = str(obj.get("objclass") or "")
        data = obj.get("objdata") or {}
        if "VaseBreakerPresetProperties" in cls or "Vases" in data:
            return data
    return None


def build_minigames(zombies, plants):
    scan = load_json(WORK / "expansion_scan.json")
    entries = list(scan.get("vase") or [])
    by_id, by_world = zombie_index(zombies)
    plants_by_id = plant_index(plants)
    plant_ids_sorted = sorted(plants_by_id, key=len, reverse=True)
    worlds = load_json(CONTENT / "worlds.json")
    wmeta = world_meta(worlds)

    per_world_count = {}
    rows = []
    for entry in sorted(entries, key=lambda e: str(e.get("pkg"))):
        world = map_world_by_stage(entry.get("stage"))
        roles = zombie_role_ids(world, by_world, by_id)
        pkg_file = pkg_path(entry.get("pkg"))
        doc = load_json(pkg_file) if pkg_file.exists() else {"objects": []}
        props = vase_props(doc) or {}

        # 格子范围
        lo = safe_int(props.get("MinColumnIndex"), 2)
        hi = safe_int(props.get("MaxColumnIndex"), 7)
        lo = max(2, min(7, lo))
        hi = max(2, min(7, hi))
        if hi < lo:
            lo, hi = hi, lo
        if hi - lo < 2:
            lo, hi = 2, 7

        blocked = set()
        for key in ("GridSquareExcludelist", "GridSquareBlacklist"):
            for cell in props.get(key) or []:
                if isinstance(cell, dict) and "mX" in cell and "mY" in cell:
                    blocked.add((safe_int(cell.get("mY")), safe_int(cell.get("mX"))))

        # 罐子池
        zombies_pool = []
        plants_pool = []
        sun_count = 0
        food_count = 0
        for item in props.get("Vases") or []:
            count = max(0, safe_int(item.get("Count"), 0))
            if not count:
                continue
            if item.get("ZombieTypeName"):
                zombies_pool.append((map_zombie(item["ZombieTypeName"], world, roles), count))
            elif item.get("PlantTypeName"):
                plants_pool.append((map_plant(item["PlantTypeName"], world,
                                              plants_by_id, plant_ids_sorted), count))
            elif str(item.get("CollectableTypeName") or "").lower() == "plantfood":
                food_count += count
            elif str(item.get("CollectableTypeName") or "").lower() in ("sun", "coins"):
                sun_count += count

        if not zombies_pool and not plants_pool:
            zombies_pool = [(roles["base"], 5), (roles["armored1"], 3),
                            (roles["armored2"], 1)]
            plants_pool = [(default_plant(world, plants_by_id), 5),
                           ("sunflower" if "sunflower" in plants_by_id
                            else default_plant(world, plants_by_id), 3),
                           ("wallnut" if "wallnut" in plants_by_id
                            else default_plant(world, plants_by_id), 2)]

        pkg_tag = re.search(r"pkg_(\d+)", str(entry.get("pkg") or "pkg_0"))
        pkg_no = int(pkg_tag.group(1)) if pkg_tag else 0
        total_vases = 14 + (pkg_no * 7 + 3) % 11          # 14..24

        plantfood_n = 1 if (food_count > 0 or total_vases >= 22) else 0
        plantfood_n = min(2, plantfood_n)
        sun_n = 2 if total_vases < 20 else 3
        rest = max(6, total_vases - sun_n - plantfood_n)

        weighted = [("zombie", pid, cnt) for pid, cnt in zombies_pool] + \
                   [("plant", pid, cnt) for pid, cnt in plants_pool]
        if not zombies_pool:
            weighted += [("zombie", roles["base"], 5),
                         ("zombie", roles["armored1"], 2)]
        if not plants_pool:
            weighted += [("plant", default_plant(world, plants_by_id), 4),
                         ("plant", "wallnut" if "wallnut" in plants_by_id
                          else default_plant(world, plants_by_id), 2)]
        agg = {}
        for kind, pid, cnt in weighted:
            agg[(kind, pid)] = agg.get((kind, pid), 0) + max(0, cnt)
        items_list = list(agg.items())
        total_w = sum(c for _k, c in items_list) or 1
        if len(items_list) >= rest:
            chosen = sorted(items_list, key=lambda kv: (-kv[1], kv[0][1]))[:rest]
            alloc = [[k[0], k[1], 1] for k, _c in chosen]
        else:
            base = {k: 1 for k, _c in items_list}
            remaining = rest - len(items_list)
            quotas = []
            for k, c in items_list:
                exact = c / total_w * remaining
                quotas.append([k, exact, int(exact)])
            used = sum(q[2] for q in quotas)
            left = remaining - used
            quotas.sort(key=lambda q: -(q[1] - q[2]))
            for i in range(left):
                quotas[i % len(quotas)][2] += 1
            alloc = [[k[0], k[1], base[k] + q] for k, _exact, q in quotas]
        # 保证僵尸/植物都有足够数量（部分 OBB 预设几乎只有单类）
        want = max(3, rest // 4)

        def _kind_total(kind):
            return sum(row[2] for row in alloc if row[0] == kind)

        def _grow(kind):
            for row in alloc:
                if row[0] == kind:
                    row[2] += 1
                    return True
            return False

        def _shrink(kind):
            cands = [row for row in alloc if row[0] == kind and row[2] > 1]
            if not cands:
                return False
            cands.sort(key=lambda row: -row[2])
            cands[0][2] -= 1
            return True

        guard = 0
        while _kind_total("zombie") < want and guard < 50:
            guard += 1
            if not _shrink("plant") or not _grow("zombie"):
                break
        guard = 0
        while _kind_total("plant") < want and guard < 50:
            guard += 1
            if not _shrink("zombie") or not _grow("plant"):
                break

        vases = []
        for kind, pid, n in alloc:
            vases.extend([[kind, pid]] * n)
        vases.extend([["sun", 25]] * sun_n)
        vases.extend([["plantfood", 1]] * plantfood_n)
        vases = vases[:total_vases]

        cells = [(r, c) for r in range(5) for c in range(lo, hi + 1)
                 if (r, c) not in blocked]
        if len(cells) < len(vases):
            cells = [(r, c) for r in range(5) for c in range(2, 8)
                     if (r, c) not in blocked]
        if len(cells) < len(vases):
            cells = [(r, c) for r in range(5) for c in range(2, 8)]
        if len(cells) < len(vases):
            vases = vases[:len(cells)]

        rng = random.Random(pkg_no * 7919 + 13)
        rng.shuffle(cells)
        cells = cells[:len(vases)]
        rng.shuffle(vases)
        layout = sorted(([r, c, kind, payload] for (r, c), (kind, payload)
                         in zip(cells, vases)), key=lambda v: (v[0], v[1]))

        per_world_count[world] = per_world_count.get(world, 0) + 1
        idx = per_world_count[world]
        wname = wmeta.get(world, {}).get("name_zh", world)
        rows.append({
            "id": f"vase_{world}_{idx}",
            "world": world,
            "title": f"{wname}·砸罐子 {idx}",
            "title_zh": f"{wname}·砸罐子 {idx}",
            "desc_zh": f"砸开罐子，清光所有僵尸。场上共 {len(layout)} 个罐子。",
            "sun": 0,
            "vases": layout,
        })

    # 按世界顺序排序
    rows.sort(key=lambda r: (wmeta.get(r["world"], {}).get("order", 99), r["world"], r["id"]))
    return {"vasebreaker": rows, "minigames": rows}


# ---------------------------------------------------------------- 僵尸博士
BOSS_PLAN = [
    ("egypt", "僵尸博士·沙漠暴君", 8000, 180,
     ["mummy", "mummy_armor1", "mummy_armor2"]),
    ("pirate", "僵尸博士·海上霸主", 8500, 200,
     ["pirate", "pirate_armor1", "gargantuar"]),
    ("beach", "僵尸博士·深海巨兽", 9000, 220,
     ["beach", "gargantuar"]),
    ("cowboy", "僵尸博士·西部枪王", 9500, 240,
     ["cowboy", "cowboy_armor1", "gargantuar"]),
    ("kongfu", "僵尸博士·武学宗师", 10000, 260,
     ["kongfu", "gargantuar"]),
    ("chinesegarden", "僵尸博士·戏曲毁灭者", 11000, 280,
     ["garden_zombie", "garden_cone", "garden_gargantuar"]),
    ("plantagenet", "僵尸博士·王朝霸主", 12000, 300,
     ["royal_zombie", "royal_noblewoman", "royal_chef_gargantuar"]),
]

BOSS_SOURCES = {
    "egypt": "pkg_0613", "pirate": "pkg_1557", "beach": "pkg_0331",
    "cowboy": "pkg_1173", "kongfu": "pkg_1412", "chinesegarden": "pkg_0390",
    "plantagenet": "pkg_1017",
}


def build_bosses():
    rows = []
    for world, title, hp, reward, minions in BOSS_PLAN:
        art = ("art/chinesegarden/zombot.png" if world == "chinesegarden"
               else "zombies/GargantuarZOMBIE")
        rows.append({
            "id": f"boss_{world}",
            "world": world,
            "title": title,
            "hp": hp,
            "minions": list(minions),
            "art": art,
            "reward": reward,
        })
    return {"bosses": rows}


# ---------------------------------------------------------------- 商店
def build_shop(plants):
    plant_names = {p["id"]: p.get("name_zh") or p["id"] for p in plants}
    items = [
        {"id": "pf_pack", "name_zh": "植物养料 ×3",
         "desc_zh": "立即获得 3 份植物养料，可在关卡中强化植物。",
         "price": 150, "kind": "plantfood", "value": 3},
        {"id": "sun_start", "name_zh": "开局阳光 +150",
         "desc_zh": "之后每关开局额外获得 150 阳光，永久生效。",
         "price": 400, "kind": "sun_start", "value": 150},
        {"id": "mower_repair", "name_zh": "补充小推车",
         "desc_zh": "关卡开始时补满小推车，避免一次失误直接失败。",
         "price": 250, "kind": "mower", "value": 1},
    ]
    for i, (pid, fallback_zh) in enumerate(NEW_PLANTS):
        zh = plant_names.get(pid) or fallback_zh
        price = 500 + i * 20
        items.append({
            "id": f"seed_{pid}",
            "name_zh": f"种子包·{zh}",
            "desc_zh": f"解锁新植物「{zh}」，可在选卡界面使用。",
            "price": price,
            "kind": "plant",
            "value": pid,
        })
    return {"items": items}


# ---------------------------------------------------------------- 自检
def check(zombies, plants, worlds):
    report = []
    problems = []
    pending = []

    json_files = {
        "stars": CONTENT / "stars.json",
        "minigames": CONTENT / "minigames.json",
        "bosses": CONTENT / "bosses.json",
        "shop": CONTENT / "shop.json",
    }
    loaded = {}
    for name, path in json_files.items():
        try:
            loaded[name] = load_json(path)
            report.append(f"[OK] parse {path.name}: {path.stat().st_size} bytes")
        except Exception as exc:  # pragma: no cover
            problems.append(f"parse {path.name}: {exc}")
            loaded[name] = None

    plant_ids = {p["id"] for p in plants}
    zombie_ids = {z["id"] for z in zombies}
    world_ids = {w["id"] for w in worlds}

    # JSON 文件格式（UTF-8 无 BOM、indent=1、非 ASCII 原样、末尾换行）
    for name in ("stars", "minigames", "bosses", "shop"):
        raw = (CONTENT / f"{name}.json").read_bytes()
        if raw[:3] == b"\xef\xbb\xbf":
            problems.append(f"{name}.json has UTF-8 BOM")
        if b"\\u" in raw:
            problems.append(f"{name}.json contains \\u escapes")
        if not raw.endswith(b"\n"):
            problems.append(f"{name}.json missing trailing newline")
        if b'\n "' not in raw:
            problems.append(f"{name}.json not indent=1")
    report.append("[CHECK] JSON 格式：UTF-8 无 BOM / indent=1 / 中文原样 / 末尾换行")

    # stars 键顺序：按 worlds.order + 关卡序号
    stars_doc = loaded.get("stars")
    if isinstance(stars_doc, dict):
        expected = []
        for w in sorted(worlds, key=lambda x: safe_int(x.get("order"), 0)):
            for i in range(1, 11):
                lid = f"{w.get('id')}_{i}"
                if lid in stars_doc:
                    expected.append(lid)
        if list(stars_doc) != expected:
            problems.append("stars key order does not follow worlds order/index")

    # stars
    stars = loaded.get("stars") or {}
    report.append(f"[COUNT] stars: {len(stars)} levels")
    bad_star = 0
    for lid, conditions in stars.items():
        if len(conditions) != 3:
            problems.append(f"stars[{lid}] has {len(conditions)} conditions")
            bad_star += 1
            continue
        for cond in conditions:
            if cond.get("type") not in ALLOWED_STAR_TYPES:
                problems.append(f"stars[{lid}] bad type {cond.get('type')}")
                bad_star += 1
            if not isinstance(cond.get("value"), int):
                problems.append(f"stars[{lid}] non-int value {cond.get('value')!r}")
                bad_star += 1
            if not str(cond.get("text_zh") or "").strip():
                problems.append(f"stars[{lid}] empty text_zh")
                bad_star += 1
        if lid not in (".",):
            world = lid.rsplit("_", 1)[0]
            if world not in world_ids and world not in PENDING_WORLDS:
                problems.append(f"stars[{lid}] unknown world {world}")
    report.append(f"[CHECK] stars bad: {bad_star}")
    try:
        level_ids = {json.loads(p.read_text(encoding="utf-8"))["id"]
                     for p in (CONTENT / "levels").glob("*.json")}
    except Exception:
        level_ids = set()
    missing_star = sorted(level_ids - set(stars))
    if missing_star:
        problems.append(f"stars missing levels: {missing_star}")

    # minigames
    mg = loaded.get("minigames") or {}
    vb = mg.get("vasebreaker") or []
    report.append(f"[COUNT] minigames.vasebreaker: {len(vb)}")
    if mg.get("minigames") != vb:
        problems.append("minigames key differs from vasebreaker")
    if len(vb) != 45:
        problems.append(f"minigames expected 45, got {len(vb)}")
    mg_ids = [e.get("id") for e in vb]
    if len(set(mg_ids)) != len(mg_ids):
        problems.append("minigames duplicate ids")
    mg_no = 0
    mg_pending_z = set()
    mg_pending_p = set()
    for entry in vb:
        eid = entry.get("id")
        if not str(entry.get("title") or "").strip():
            problems.append(f"{eid}: empty title")
        if entry.get("world") not in world_ids and entry.get("world") not in PENDING_WORLDS:
            problems.append(f"{eid}: unknown world {entry.get('world')}")
        vases = entry.get("vases") or []
        if not (14 <= len(vases) <= 24):
            problems.append(f"{eid}: {len(vases)} vases (need 14-24)")
        cells = set()
        for v in vases:
            if not isinstance(v, list) or len(v) != 4:
                problems.append(f"{eid}: bad vase {v}")
                continue
            r, c, kind, payload = v
            if not (0 <= r <= 4 and 2 <= c <= 7):
                problems.append(f"{eid}: cell out of range {r},{c}")
            if (r, c) in cells:
                problems.append(f"{eid}: duplicate cell {r},{c}")
            cells.add((r, c))
            if kind == "zombie" and payload not in zombie_ids:
                mg_pending_z.add(payload)
            elif kind == "plant" and payload not in plant_ids:
                mg_pending_p.add(payload)
            elif kind not in ("zombie", "plant", "sun", "plantfood"):
                problems.append(f"{eid}: bad kind {kind}")
        mg_no += 1
    report.append(f"[CHECK] minigames entries: {mg_no}; pending zombies={sorted(mg_pending_z)};"
                  f" pending plants={sorted(mg_pending_p)}")
    pending.extend(f"minigame zombie not in content: {z}" for z in sorted(mg_pending_z))
    pending.extend(f"minigame plant not in content: {p}" for p in sorted(mg_pending_p))

    # bosses
    bosses = (loaded.get("bosses") or {}).get("bosses") or []
    report.append(f"[COUNT] bosses: {len(bosses)}")
    if len(bosses) != 7:
        problems.append(f"bosses expected 7, got {len(bosses)}")
    for boss in bosses:
        if (boss.get("world") not in world_ids
                and boss.get("world") not in PENDING_WORLDS):
            problems.append(f"{boss.get('id')}: unknown world {boss.get('world')}")
        if not (6000 <= safe_int(boss.get("hp")) <= 12000):
            problems.append(f"{boss.get('id')}: hp {boss.get('hp')} out of 6000-12000")
        if not (150 <= safe_int(boss.get("reward")) <= 300):
            problems.append(f"{boss.get('id')}: reward {boss.get('reward')} out of 150-300")
        if boss.get("world") in PENDING_WORLDS - world_ids:
            pending.append(f"boss world not in content yet: {boss.get('world')}")
        if not (2 <= len(boss.get("minions") or []) <= 3):
            problems.append(f"{boss.get('id')}: minions count {len(boss.get('minions') or [])}")
        for mid in boss.get("minions") or []:
            if mid not in zombie_ids:
                pending.append(f"{boss.get('id')} minion not in content: {mid}")

    # shop
    shop = (loaded.get("shop") or {}).get("items") or []
    report.append(f"[COUNT] shop: {len(shop)}")
    if len(shop) != 23:
        problems.append(f"shop expected 23, got {len(shop)}")
    shop_ids = [i.get("id") for i in shop]
    if len(set(shop_ids)) != len(shop_ids):
        problems.append("shop duplicate ids")
    kinds = {"plant": 0, "plantfood": 0, "sun_start": 0, "mower": 0}
    for item in shop:
        kind = item.get("kind")
        if kind not in kinds:
            problems.append(f"{item.get('id')}: bad kind {kind}")
            continue
        kinds[kind] += 1
        if kind == "plant":
            if item.get("value") not in plant_ids:
                pending.append(f"shop plant not in content: {item.get('value')}")
            if not (500 <= safe_int(item.get("price")) <= 900):
                problems.append(f"{item.get('id')}: price {item.get('price')} out of 500-900")
    report.append(f"[CHECK] shop kinds: {kinds}")
    if kinds["plant"] != 20:
        problems.append(f"shop plant items expected 20, got {kinds['plant']}")

    report.append("")
    if pending:
        report.append("[PENDING] references awaiting parallel content additions:")
        report.extend(f"  - {p}" for p in pending)
    report.append("")
    if problems:
        report.append(f"RESULT: FAIL ({len(problems)} problems)")
        report.extend(f"  ! {p}" for p in problems)
    else:
        report.append("RESULT: PASS (all structure and reference checks passed)")
    return report, problems


# ---------------------------------------------------------------- 主流程
def main():
    worlds, plants, zombies, levels = read_content()

    stars = build_stars(levels, worlds)
    dump_json(CONTENT / "stars.json", stars)
    minigames = build_minigames(zombies, plants)
    dump_json(CONTENT / "minigames.json", minigames)
    bosses = build_bosses()
    dump_json(CONTENT / "bosses.json", bosses)
    shop = build_shop(plants)
    dump_json(CONTENT / "shop.json", shop)

    vb_rows = minigames.get("vasebreaker") or []
    world_counts = {}
    for row in vb_rows:
        world_counts[row["world"]] = world_counts.get(row["world"], 0) + 1
    third = [cond[2] for cond in stars.values()]
    type_counts = {}
    for cond in third:
        type_counts[cond["type"]] = type_counts.get(cond["type"], 0) + 1
    obb_stars = sum(1 for c in third if c["type"] != "kill" or "seconds" in c)
    n_vases = [len(row["vases"]) for row in vb_rows]
    vase_kinds = {"zombie": 0, "plant": 0, "sun": 0, "plantfood": 0}
    for row in vb_rows:
        for v in row["vases"]:
            vase_kinds[v[2]] = vase_kinds.get(v[2], 0) + 1
    min_z = min(sum(1 for v in r["vases"] if v[2] == "zombie") for r in vb_rows)
    min_p = min(sum(1 for v in r["vases"] if v[2] == "plant") for r in vb_rows)
    min_s = min(sum(1 for v in r["vases"] if v[2] == "sun") for r in vb_rows)
    lines = [
        "PvZ2 SHUTTLE 元内容生成报告（元内容子代理）",
        "=" * 46,
        "数据源：work/obb_packages（RTON 导出）+ work/expansion_scan.json + content",
        "生成器：tools/build_meta_content.py（可重复运行；只读 content，不修改 plants/zombies/worlds/levels）",
        "",
        f"levels scanned: {len(levels)}（110 个 OBB 关卡 + plantagenet_1..10）",
        f"stars.json: {len(stars)} 个关卡，每关 3 条（{len(stars) * 3} 条）",
        f"  第 3 星类型分布: {type_counts}",
        f"  第 3 星来自 OBB StarChallenge: {obb_stars}；通用击杀兜底: {len(stars) - obb_stars}",
        f"minigames.json: {len(vb_rows)} 关砸罐子；每关罐子 {min(n_vases)}-{max(n_vases)} 个",
        f"  罐子类型合计: {vase_kinds}",
        f"  每关最低配额: 僵尸 {min_z} / 植物 {min_p} / 阳光 {min_s}",
        f"  按世界: {world_counts}",
        f"bosses.json: {len(bosses['bosses'])} 条",
    ]
    for b in bosses["bosses"]:
        lines.append(f"  - {b['id']:<20} world={b['world']:<15} hp={b['hp']:<6} reward={b['reward']:<4} "
                     f"minions={','.join(b['minions'])}")
    lines += [
        f"shop.json: {len(shop['items'])} 条；价格 {min(i['price'] for i in shop['items'])}-"
        f"{max(i['price'] for i in shop['items'])} 金币",
        f"  种类: plantfood=1, sun_start=1, mower=1, seed_plant=20",
        "",
    ]
    report, problems = check(zombies, plants, worlds)
    lines.extend(report)
    out = WORK / "meta_content_report.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
