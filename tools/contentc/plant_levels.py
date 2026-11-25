# -*- coding: utf-8 -*-
"""植物等级 / 升级数据编译器（t78 P1-12）。

结论先说清楚（本文件所有数字都来自 460.9 的 OBB，无一处估算）：
    **原版确实有「植物等级」这一套数据**，落在 `pkg_2069_PlantLevelStats.json` 的
    `PlantLevelStats`（325 行 / 323 个 TypeName）里。它不是我原先以为的「每级一套系数」，
    而是**逐级绝对值**：`FloatStats[]` 的每一条 `{Name, Values[]}` 的 `Values` 就是一串
    逐级数值（`Values[0]` = 1 级）。因此本产物直接输出绝对数值表，不编造任何倍率；
    需要倍率的一方可以自己除（本文件另外算好了 3 个派生倍率，见 R07，标明 derived）。

口径（每条都可在报告与 `--check` 里复核）：
    R01 唯一权威表是 `pkg_2069_PlantLevelStats.json`（objclass `PlantLevelStats`）；
        `pkg_2072_unknown.json` 里也有 377 行同名 objclass，但**没有 LevelCap / LevelXP /
        LevelCoins / PlantTier**，且部分数值与正表冲突 → 只作为「alternate」旁证记录，
        绝不并入主表（见 R05）。
    R02 一个 TypeName 在正表里可能出现 2 次（实测 `aloe`、`cactus`）→ 取「有值字段最多、
        层数最大、包内下标最小」的那一行，其余进 `counts.duplicateTypeNames` 计数，
        另存进该植物的 `alternateRows`（保留证据，不静默丢）。
    R03 层数 `levelCount` 的判定分两档（准入条件全是实测出来的，不是猜的）：
        a) `LevelCap > 1` → 直接用 LevelCap（35 株，例 blockoli 10 / sunflower 3）；
        b) 否则取 {最长的 Values 长度, 单调 LevelXP 长度+1, 非花费型 PlantTier 长度,
           非零 LevelCoins 长度} 的最大值，都没有则 1。
        为什么不能无条件用 max：`wallnut` 的 LevelXP 有 39 项且尾部被追加了
        1/1/1/1/2/2/2/2/3/3（阶数），纯 max 会把它算成 40 层；`potatomine` 的
        PlantTier 装的是升阶金币（1/50/200/…/55000），纯 max 会算成 20 层。
        113 株 LevelXP 非单调、86 株 PlantTier 像花费，都记进 `levelCountIgnored`
        与 `unknowns`，原样保留、不修正。
    R04 逐级数值只做「按层取数」：`stats[列名] = Values[level-1]`；`Values` 不够长就给
        `null`，并把缺的条数记进 `raggedStats`（实测 40 株 / 1719 个空位）。**绝不**
        用上一级补、也不用 0 补。
    R04b 一条 `FloatStats` 里可能出现同名条目（实测 27 株，全是 ActionDamage 系），
        它们靠 `SubType` 区分、是**两列不同数据**（`cutebubuseed` 的
        `ActionDamage/SubType=0 → [6]`、`SubType=1 → [100]`）。名字唯一时列名就是
        `Name`（296 株的键保持不变），出现同名时改成 `Name@SubType`，一列都不丢；
        重复本身进 `unknowns` 的 `duplicate-stat-names` 供复核。
    R05 若某 TypeName 只在 alternate（`pkg_2072_unknown.json`）里出现 → 进 `unknowns`，
        不建植物条目（实测 3 个：electrictea / tombtangler / vamporcini）。
    R06 `StringStats` 原样透传（多数为空 Values，不做解释）。
    R07 派生倍率只对 3 个统计项算，且只在基线非 0 时算：
        `derived.hpMul` / `derived.actionDamageMul`（相对 1 级）、`derived.costDelta`
        （相对 1 级，可负）。全部标 `derivedFromLevel: 1`，与原值分开摆放。
    R08 「升级」不是一张表：全库 objclass 命中 `PlantUpgrade*` 为 **0**。原版只有零散的
        单株升级字段（Ultomato 的 `BeamDPSUpgrade1..3`、Iceweed 的 `HitPointsUpgraded`、
        Peapod 的 `CanPlantAgainToUpgrade`、PassionFlower 的 `Level2/3SkillRate` 等），
        以及 `pkg_2070_PlantLevelupOfferProps.json` 的货币换算表。这些都进
        `upgradeHooks`（逐字段原值），并在报告里说明「通用升级系统在数据里不存在」。
    R09 固定日期 + sort_keys + LF + 逐字节 --check；产物两次生成必须完全相同。
"""

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages"))
DEFAULT_OUT = ROOT / "native" / "generated" / "plant_levels.json"

FORMAT = "pvz2-shuttle/plant-levels@1"
GENERATED = "2026-11-25"

CANONICAL_FILE = "pkg_2069_PlantLevelStats.json"
ALTERNATE_FILE = "pkg_2072_unknown.json"
LEVELUP_OFFER_FILE = "pkg_2070_PlantLevelupOfferProps.json"
PLANT_PROPS_FILE = "pkg_2073_PlantPropertySheet.json"

CANONICAL_CLASS = "PlantLevelStats"

# R07：只对这三项算派生值
DERIVED_MUL_STATS = ("Hitpoints", "ActionDamage")
DERIVED_DELTA_STATS = ("Cost",)

# R08：pkg_2073 里与「升级 / 等级」有关、但不属于通用等级表的单株字段
UPGRADE_KEY_RE = re.compile(r"upgrade", re.I)

# R10：「原版有没有升级表」这件事要可复核，所以把搜索本身做成产物的一部分。
# 每个关键词同时统计三种命中：objclass 名、alias 名、objdata 里的字段名。
SEARCH_TERMS = (
    "PlantLevel",
    "PlantUpgrade",
    "LevelUp",
    "SeedPackLevel",
    "Upgrade",
)

_CACHE = {}


def load_json(path):
    key = str(path)
    if key in _CACHE:
        return _CACHE[key]
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        doc = json.load(handle)
    _CACHE[key] = doc
    return doc


def iter_objects(doc):
    for obj in doc.get("objects") or []:
        data = obj.get("objdata")
        if isinstance(data, dict):
            yield obj, data


def obj_aliases(obj):
    names = obj.get("aliases")
    if names is None:
        names = obj.get("alias")
    if isinstance(names, str):
        return [names]
    return list(names or [])


def level_stats_rows(obb_dir, filename):
    """读一个包里的 PlantLevelStats 行，保留包名与行下标。"""
    path = Path(obb_dir) / filename
    if not path.exists():
        return []
    rows = []
    for index, (obj, data) in enumerate(iter_objects(load_json(path))):
        if (obj.get("objclass") or "") != CANONICAL_CLASS:
            continue
        rows.append({
            "package": filename,
            "index": index,
            "aliases": obj_aliases(obj),
            "data": data,
        })
    return rows


def _int_or_none(value):
    return value if isinstance(value, int) else None


def _list(value):
    return value if isinstance(value, list) else []


def stat_series(data):
    """把 `FloatStats` 读成「列名 → 逐级数组」，同名条目按 `SubType` 拆开。

    实测：一条记录里 `FloatStats` 可能有两项同名（27 株，全是 ActionDamage 系），
    它们靠 `SubType` 区分，**是两列不同的数据**而不是重复占位——
    cutebubuseed 的 `ActionDamage/SubType=0 → [6]`、`ActionDamage/SubType=1 → [100]`。
    按名字合并会丢掉其中一列，按出现顺序后写覆盖更糟（值直接变成 null），
    所以：名字唯一时列名就是 `Name`（保持 296 株的现有键不变），
    出现同名时列名改成 `Name@SubType`（无 SubType 则用出现序号），一列都不丢。
    """
    entries = []
    for item in _list(data.get("FloatStats")):
        if isinstance(item, dict) and isinstance(item.get("Name"), str):
            entries.append(item)
    seen = {}
    for item in entries:
        seen[item["Name"]] = seen.get(item["Name"], 0) + 1

    out = {}
    used = {}
    for item in entries:
        name = item["Name"]
        if seen[name] > 1:
            sub = item.get("SubType")
            suffix = str(sub) if isinstance(sub, (str, int, float)) and str(sub) != "" else ""
            if not suffix:
                used[name] = used.get(name, 0) + 1
                suffix = str(used[name] - 1)
            key = "%s@%s" % (name, suffix)
        else:
            key = name
        # 极端情况下同 key 仍会撞（两个 SubType 都缺失且序号复用），保底加后缀
        if key in out:
            index = 1
            while "%s#%d" % (key, index) in out:
                index += 1
            key = "%s#%d" % (key, index)
        out[key] = _list(item.get("Values"))
    return out


def stat_lengths(data):
    """每个统计列的逐级数组长度（列名规则见 stat_series）。"""
    return {key: len(values) for key, values in stat_series(data).items()}


def duplicate_stat_names(data):
    """同一条记录里 `FloatStats` 出现同名条目的次数（实测 27 株，全是 ActionDamage 系）。"""
    seen = {}
    for item in _list(data.get("FloatStats")):
        if isinstance(item, dict) and isinstance(item.get("Name"), str):
            seen[item["Name"]] = seen.get(item["Name"], 0) + 1
    return {name: count for name, count in seen.items() if count > 1}


def scan_terms(obb_dir, terms=SEARCH_TERMS):
    """R10：全库统计每个关键词在 objclass / alias / 字段名 上的命中数。

    这是「原版是否存在通用升级表」这一**否定结论**的证据：`PlantUpgrade` 三类全 0，
    而 `PlantLevel` 命中正表本身。搜索是字面子串匹配（大小写不敏感），
    不涉及语义判断，所以任何人都能按同一口径复现。
    """
    files = sorted(Path(obb_dir).glob("pkg_*.json"))
    rows = {term: {"term": term, "classes": 0, "aliases": 0, "keys": 0,
                   "examples": []} for term in terms}
    lowered = {term: term.lower() for term in terms}
    for path in files:
        try:
            doc = load_json(path)
        except (ValueError, OSError):
            continue
        for obj, data in iter_objects(doc):
            cls = obj.get("objclass") or ""
            names = list(obj_aliases(obj)) + [data.get("TypeName") or ""]
            keys = list(data)
            for term, needle in lowered.items():
                row = rows[term]
                if needle in str(cls).lower():
                    row["classes"] += 1
                    if len(row["examples"]) < 5:
                        row["examples"].append({"objclass": cls, "package": path.name})
                if any(needle in str(name).lower() for name in names if name):
                    row["aliases"] += 1
                hits = [key for key in keys if needle in str(key).lower()]
                if hits:
                    row["keys"] += len(hits)
                    if len(row["examples"]) < 5:
                        row["examples"].append({"keys": sorted(hits)[:4],
                                                "objclass": cls, "package": path.name})
    return [rows[term] for term in terms]


def level_count(data):
    """R03：层数 = LevelCap（若 >1）；否则取「互相一致的逐级数组长度」的最大值。

    三个来源的准入条件都是实测出来的，不是猜的：
      * LevelCap > 1 时它就是明确的等级上限（blockoli 10 / sunflower 3）；
      * LevelXP 只有在单调不减时才算层数——wallnut / aloe 这类行的 LevelXP 尾部被
        追加了一段 1/1/2/2/3/3（阶数），长度 39/19 明显不是层数；
      * PlantTier 只有在「不像花费」时才算层数——potatomine 的 PlantTier 是
        1/50/200/.../55000 的升阶金币，长度 20 但那是价格表。
    返回 (count, sources, parts, ignored)。
    """
    cap = _int_or_none(data.get("LevelCap")) or 0
    xp = _list(data.get("LevelXP"))
    tier = _list(data.get("PlantTier"))
    coins = _list(data.get("LevelCoins"))
    lengths = stat_lengths(data)
    max_values = max(lengths.values()) if lengths else 0
    xp_monotonic = is_monotonic(xp)
    tier_numeric = [v for v in tier if isinstance(v, (int, float))]
    tier_looks_like_coins = any(v >= 1000 for v in tier_numeric)
    parts = {
        "levelCap": cap,
        "levelXP": len(xp),
        "plantTier": len(tier),
        "levelCoins": len(coins),
        "floatStats": max_values,
    }
    if cap > 1:
        return cap, ["levelCap"], parts, []
    candidates = {}
    if max_values:
        candidates["floatStats"] = max_values
    if xp and xp_monotonic:
        candidates["levelXP"] = len(xp) + 1
    elif xp:
        pass
    if tier and not tier_looks_like_coins:
        candidates["plantTier"] = len(tier)
    if coins and any(v not in (None, 0) for v in coins):
        candidates["levelCoins"] = len(coins)
    ignored = []
    if xp and xp_monotonic is False:
        ignored.append("levelXP:non-monotonic")
    if tier and tier_looks_like_coins:
        ignored.append("plantTier:looks-like-coins")
    if not candidates:
        return 1, ["default-1"], parts, ignored
    count = max(candidates.values())
    sources = [name for name, value in candidates.items() if value == count]
    return count, sorted(sources), parts, ignored


def build_levels(data, count):
    """R04：逐级取数；不够长的地方给 None 并计数。

    列名规则见 `stat_series`：同名条目按 `SubType` 拆成多列，一列都不丢。
    """
    series = stat_series(data)
    names = list(series)

    levels = []
    ragged = {}
    for level in range(1, count + 1):
        stats = {}
        for name in names:
            values = series.get(name) or []
            if len(values) >= level:
                stats[name] = values[level - 1]
            else:
                stats[name] = None
                ragged[name] = ragged.get(name, 0) + 1
        levels.append({"level": level, "stats": stats})
    return levels, ragged


def derived_block(levels):
    """R07：只在基线存在且非 0 时算倍率/差值。"""
    if not levels:
        return {}
    base = levels[0]["stats"]
    out = {"derivedFromLevel": 1}
    for name in DERIVED_MUL_STATS:
        start = base.get(name)
        if not isinstance(start, (int, float)) or start == 0:
            continue
        series = []
        for row in levels:
            value = row["stats"].get(name)
            series.append(round(value / start, 4) if isinstance(value, (int, float)) else None)
        key = "hpMul" if name == "Hitpoints" else "actionDamageMul"
        out[key] = series
        out.setdefault("derivedFrom", {})[key] = name
    for name in DERIVED_DELTA_STATS:
        start = base.get(name)
        if not isinstance(start, (int, float)):
            continue
        series = []
        for row in levels:
            value = row["stats"].get(name)
            series.append(round(value - start, 4) if isinstance(value, (int, float)) else None)
        out["costDelta"] = series
        out.setdefault("derivedFrom", {})["costDelta"] = name
    return out


def is_monotonic(values):
    """LevelXP 本该是递增的阈值序列；不是递增说明这一行的字段错位了（实测 aloe）。"""
    nums = [v for v in values if isinstance(v, (int, float))]
    if len(nums) < 2 or len(nums) != len(values):
        return None
    return all(b >= a for a, b in zip(nums, nums[1:]))


def score_row(row):
    """R02：挑正表里同一个 TypeName 的「最好」那行：有值字段多 > 层数大 > 下标小。"""
    data = row["data"]
    filled = 0
    for key, value in data.items():
        if key.startswith("#"):
            continue
        if value not in (None, [], {}):
            filled += 1
    count, _sources, _parts, _ignored = level_count(data)
    return (-filled, -count, row["index"])


def upgrade_hooks(obb_dir):
    """R08：pkg_2073 里键名含 upgrade 的单株字段（原值，不解释）。"""
    path = Path(obb_dir) / PLANT_PROPS_FILE
    if not path.exists():
        return [], {"plants": 0, "fields": 0, "keys": []}
    rows = []
    key_counts = {}
    for obj, data in iter_objects(load_json(path)):
        names = obj_aliases(obj)
        owner = names[0] if names else None
        for key in data:
            if not isinstance(key, str) or key.startswith("#"):
                continue
            if not UPGRADE_KEY_RE.search(key):
                continue
            key_counts[key] = key_counts.get(key, 0) + 1
            rows.append({"key": key, "value": data[key], "plant": owner})
    return rows, {"fields": len(rows), "keys": sorted(key_counts)}


def levelup_offer(obb_dir):
    path = Path(obb_dir) / LEVELUP_OFFER_FILE
    if not path.exists():
        return None
    for obj, data in iter_objects(load_json(path)):
        if (obj.get("objclass") or "") == "PlantLevelupOfferProps":
            return {"package": LEVELUP_OFFER_FILE, "objclass": obj.get("objclass"),
                    "aliases": obj_aliases(obj), "data": data}
    return None


def build(obb_dir):
    canonical = level_stats_rows(obb_dir, CANONICAL_FILE)
    alternate = level_stats_rows(obb_dir, ALTERNATE_FILE)

    grouped = {}
    for row in canonical:
        name = row["data"].get("TypeName")
        if not isinstance(name, str) or not name:
            continue
        grouped.setdefault(name, []).append(row)

    alt_grouped = {}
    for row in alternate:
        name = row["data"].get("TypeName")
        if not isinstance(name, str) or not name:
            continue
        alt_grouped.setdefault(name, []).append(row)

    plants = {}
    duplicates = {}
    cap_below = 0
    leveling_plants = 0
    ragged_plants = 0
    null_pairs = 0
    by_count = {}
    stat_names = set()
    stats_below = 0
    xp_non_monotonic = []
    tier_looks_like_coins = []
    dup_stat_plants = 0
    dup_stat_counts = {}
    for name in sorted(grouped):
        rows = sorted(grouped[name], key=score_row)
        best = rows[0]
        if len(rows) > 1:
            duplicates[name] = len(rows)
        data = best["data"]
        count, sources, parts, ignored = level_count(data)
        levels, ragged = build_levels(data, count)
        if ragged:
            ragged_plants += 1
            null_pairs += sum(ragged.values())
        dup_names = duplicate_stat_names(data)
        dup_detail = None
        if dup_names:
            dup_stat_plants += 1
            columns = list(stat_series(data))
            dup_detail = {}
            for dup_name, dup_count in dup_names.items():
                dup_stat_counts[dup_name] = dup_stat_counts.get(dup_name, 0) + 1
                dup_detail[dup_name] = {
                    "entries": dup_count,
                    "keys": [key for key in columns
                             if key == dup_name or key.startswith(dup_name + "@")],
                }
        for item in _list(data.get("FloatStats")):
            if isinstance(item, dict) and isinstance(item.get("Name"), str):
                stat_names.add(item["Name"])
        by_count[str(count)] = by_count.get(str(count), 0) + 1
        if count > 1:
            leveling_plants += 1
        cap = parts.get("levelCap") or 0
        if cap < count:
            cap_below += 1
        stats_count = max(1, parts.get("floatStats") or 0)
        if stats_count < count:
            stats_below += 1
        xp = _list(data.get("LevelXP"))
        monotonic = is_monotonic(xp)
        if monotonic is False:
            xp_non_monotonic.append(name)
        tier = _list(data.get("PlantTier"))
        tier_coins = any(isinstance(v, (int, float)) and v >= 1000 for v in tier)
        if tier_coins:
            tier_looks_like_coins.append(name)
        entry = {
            "levels": levels,
            "levelCount": count,
            "statsLevelCount": stats_count,
            "levelCountSource": sources,
            "levelCountIgnored": ignored,
            "levelCountParts": parts,
            "levelCap": data.get("LevelCap"),
            "levelCapBelowLevelCount": bool(cap and cap < count),
            "usesLeveling": data.get("UsesLeveling"),
            "levelXP": xp,
            "levelXPMonotonic": monotonic,
            "levelCoins": _list(data.get("LevelCoins")) if "LevelCoins" in data else None,
            "plantTier": data.get("PlantTier"),
            "plantTierLooksLikeCoins": tier_coins,
            "upgradeCoins": tier if tier_coins else None,
            "seedPacketCost": data.get("SeedPacketCost"),
            "stringStats": _list(data.get("StringStats")),
            "statNames": sorted(stat_names_of(data)),
            "duplicateStatNames": dup_detail,
            "raggedStats": ragged,
            "derived": derived_block(levels),
            "source": "%s#%d" % (CANONICAL_FILE, best["index"]),
            "aliases": best["aliases"],
        }
        alt_rows = alt_grouped.get(name) or []
        if alt_rows:
            alt_best = sorted(alt_rows, key=score_row)[0]
            alt_count, _alt_sources, alt_parts, alt_ignored = level_count(alt_best["data"])
            entry["alternate"] = {
                "source": "%s#%d" % (ALTERNATE_FILE, alt_best["index"]),
                "rows": len(alt_rows),
                "levelCount": alt_count,
                "levelCountParts": alt_parts,
                "statNames": sorted(stat_names_of(alt_best["data"])),
            }
        if len(rows) > 1:
            entry["alternateRows"] = [
                {"source": "%s#%d" % (CANONICAL_FILE, row["index"]),
                 "levelCount": level_count(row["data"])[0]}
                for row in rows[1:]
            ]
        plants[name] = entry

    alt_only = sorted(set(alt_grouped) - set(grouped))
    alt_duplicate_names = sum(1 for v in alt_grouped.values() if len(v) > 1)
    hooks, hook_meta = upgrade_hooks(obb_dir)
    offer = levelup_offer(obb_dir)
    searches = scan_terms(obb_dir)

    unknowns = []
    if alt_only:
        unknowns.append({
            "kind": "alternate-only-plant",
            "count": len(alt_only),
            "plants": alt_only,
            "detail": "只出现在 pkg_2072_unknown.json 的 PlantLevelStats 里，"
                      "该表没有 LevelCap/LevelXP/LevelCoins/PlantTier，不足以建等级条目",
            "probe": "python tools/contentc/plant_levels.py --needle electrictea",
        })
    if duplicates:
        unknowns.append({
            "kind": "duplicate-canonical-typename",
            "count": len(duplicates),
            "plants": sorted(duplicates),
            "detail": "同一 TypeName 在正表里出现多次，已按「有值字段多 > 层数大 > 下标小」取一条，"
                      "其余存进 alternateRows",
            "probe": "python tools/contentc/plant_levels.py --needle aloe",
        })
    if ragged_plants:
        unknowns.append({
            "kind": "ragged-float-stats",
            "count": ragged_plants,
            "nullStatPairs": null_pairs,
            "detail": "FloatStats 的 Values 比层数短，缺失层给 null（不补上一级、不补 0）",
            "probe": "python tools/contentc/plant_levels.py --check",
        })
    if cap_below:
        unknowns.append({
            "kind": "level-cap-below-level-count",
            "count": cap_below,
            "detail": "LevelCap 小于逐级数组给出的层数（例 sapfling1 LevelCap=1 但有 10 层数值），"
                      "产物以逐级数组为准并保留 levelCap 原值",
            "probe": "python tools/contentc/plant_levels.py --needle sapfling1",
        })
    if stats_below:
        unknowns.append({
            "kind": "levels-without-stats",
            "count": stats_below,
            "detail": "levelCount 来自 LevelXP/PlantTier 而 FloatStats 的 Values 更短 → 这些层的 stats 全为 null",
            "probe": "python tools/contentc/plant_levels.py --needle aloe",
        })
    if xp_non_monotonic:
        unknowns.append({
            "kind": "level-xp-not-monotonic",
            "count": len(xp_non_monotonic),
            "plants": sorted(xp_non_monotonic),
            "detail": "LevelXP 应当递增，这些行不递增（实测 aloe 的 LevelXP 装的是 1/2/3 的档位、"
                      "PlantTier 装的是 1000..100000 ⇒ 字段疑似错位）。原样保留，不做修正",
            "probe": "python tools/contentc/plant_levels.py --needle aloe",
        })
    if tier_looks_like_coins:
        unknowns.append({
            "kind": "plant-tier-looks-like-coins",
            "count": len(tier_looks_like_coins),
            "plants": sorted(tier_looks_like_coins),
            "detail": "PlantTier 里出现 >=1000 的数值，语义应是升阶花费而不是阶数（已原样放进 upgradeCoins）",
            "probe": "python tools/contentc/plant_levels.py --needle potatomine",
        })
    if dup_stat_plants:
        unknowns.append({
            "kind": "duplicate-stat-names",
            "count": dup_stat_plants,
            "names": dict(sorted(dup_stat_counts.items())),
            "detail": "同一行的 FloatStats 里出现同名条目（实测 27 株，全是 ActionDamage 系），"
                      "它们靠 SubType 区分、是两列不同数据：列名改成 `Name@SubType` 后一列都不丢",
            "probe": "python tools/contentc/plant_levels.py --needle cutebubuseed",
        })
    if not hooks:
        unknowns.append({
            "kind": "no-generic-upgrade-table",
            "count": 0,
            "detail": "全库没有 PlantUpgrade* 物件；升级只以单株字段 + 货币换算表的形式存在",
            "probe": "python tools/contentc/plant_levels.py --needle upgrade",
        })

    counts = {
        "available": bool(plants),
        "plants": len(plants),
        "rowsCanonical": len(canonical),
        "rowsAlternate": len(alternate),
        "distinctCanonical": len(grouped),
        "duplicateTypeNames": duplicates,
        "alternateDuplicateNames": alt_duplicate_names,
        "alternateOnlyPlants": alt_only,
        "byLevelCount": dict(sorted(by_count.items(), key=lambda kv: int(kv[0]))),
        "plantsWithLeveling": leveling_plants,
        "levelCapBelowLevelCount": cap_below,
        "statsLevelCountBelowLevelCount": stats_below,
        "levelXPNonMonotonic": sorted(xp_non_monotonic),
        "plantTierLooksLikeCoins": sorted(tier_looks_like_coins),
        "plantsWithUpgradeCoins": len(tier_looks_like_coins),
        "raggedPlants": ragged_plants,
        "nullStatPairs": null_pairs,
        "duplicateStatNamePlants": dup_stat_plants,
        "duplicateStatNameCounts": dict(sorted(dup_stat_counts.items())),
        "statNames": len(stat_names),
        "upgradeHookFields": len(hooks),
        "upgradeHookKeys": hook_meta["keys"],
        "levelupOffer": bool(offer),
        "filesScanned": 4,
    }

    table = {
        "format": FORMAT,
        "generated": GENERATED,
        "sources": {
            "canonical": "%s (objclass %s)" % (CANONICAL_FILE, CANONICAL_CLASS),
            "alternate": "%s (缺 LevelCap/LevelXP/LevelCoins/PlantTier，只作旁证)" % ALTERNATE_FILE,
            "levelupOffer": LEVELUP_OFFER_FILE if offer else None,
            "upgradeHooks": PLANT_PROPS_FILE,
        },
        "mechanism": {
            "hasPlantLevels": True,
            "hasGenericUpgradeTable": False,
            "shape": "逐级绝对值：FloatStats[].Values 的第 i 项就是第 i+1 级",
            "levelCountRule": "LevelCap>1 用它；否则取 {floatStats 长度, 单调 LevelXP 长度+1, "
                              "非花费型 PlantTier 长度, 非零 LevelCoins 长度} 的最大值；都没有则 1",
        },
        "counts": counts,
        "searches": searches,
        "levelupOffer": offer,
        "upgradeHooks": hooks,
        "plants": plants,
        "unknowns": unknowns,
    }
    return table


def stat_names_of(data):
    return list(stat_series(data))


def render(table):
    return json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def dump(table, path):
    # 用 write_bytes 写 LF：Windows 的 write_text 会把 \n 变成 \r\n，--check 的逐字节比较会失效
    Path(path).write_bytes(render(table).encode("utf-8"))


def check(table, path):
    problems = []
    if table.get("format") != FORMAT:
        problems.append("format != %r" % FORMAT)
    counts = table.get("counts") or {}
    plants = table.get("plants") or {}
    if counts.get("plants") != len(plants):
        problems.append("counts.plants %r != len(plants) %d" % (counts.get("plants"), len(plants)))
    if counts.get("available") is not True:
        problems.append("counts.available 不是 true")
    if counts.get("rowsCanonical") != len(plants) + sum((counts.get("duplicateTypeNames") or {}).values()) - len(counts.get("duplicateTypeNames") or {}):
        problems.append("rowsCanonical 与 plants + 重复行不吻合")
    by_count = counts.get("byLevelCount") or {}
    if sum(by_count.values()) != len(plants):
        problems.append("byLevelCount 合计 %d != plants %d" % (sum(by_count.values()), len(plants)))
    if sum(1 for row in plants.values() if row["levelCount"] > 1) != counts.get("plantsWithLeveling"):
        problems.append("plantsWithLeveling 与逐条 levelCount 不吻合")
    null_pairs = 0
    for name, row in plants.items():
        levels = row.get("levels") or []
        if row.get("levelCount") != len(levels):
            problems.append("%s: levelCount %r != len(levels) %d" % (name, row.get("levelCount"), len(levels)))
        if [lv.get("level") for lv in levels] != list(range(1, len(levels) + 1)):
            problems.append("%s: levels 不是 1..N 连续" % name)
        if not row.get("source"):
            problems.append("%s: 缺 source" % name)
        for key, value in (row.get("raggedStats") or {}).items():
            null_pairs += value
        for level_row in levels:
            for stat, value in level_row["stats"].items():
                if value is None:
                    continue
                if isinstance(value, (dict, list)):
                    problems.append("%s: stats.%s 不是标量" % (name, stat))
    if null_pairs != counts.get("nullStatPairs"):
        problems.append("nullStatPairs %d != raggedStats 求和 %d" % (counts.get("nullStatPairs"), null_pairs))
    if (table.get("mechanism") or {}).get("hasGenericUpgradeTable"):
        problems.append("mechanism.hasGenericUpgradeTable 不应为 true（全库无 PlantUpgrade* 表）")
    searches = {row.get("term"): row for row in (table.get("searches") or [])}
    if not searches:
        problems.append("searches 为空：『没有通用升级表』的否定结论必须带可复现的命中数")
    else:
        upgrade = searches.get("PlantUpgrade") or {}
        if any(upgrade.get(key, 0) for key in ("classes", "aliases", "keys")):
            problems.append("PlantUpgrade 出现命中，与「没有通用升级表」的结论矛盾")
        if not (searches.get("PlantLevel") or {}).get("classes"):
            problems.append("PlantLevel 一类都没命中：正表定位证据缺失")
    if not table.get("unknowns"):
        problems.append("unknowns 为空：查不到的东西必须显式记录")
    text = render(table)
    if "\r\n" in text:
        problems.append("渲染结果含 CRLF")
    if not text.endswith("\n") or text.endswith("\n\n"):
        problems.append("渲染结果必须以单个 LF 结尾")
    path = Path(path)
    if not path.exists():
        problems.append("产物不存在：%s" % path)
    else:
        disk = path.read_bytes()
        if b"\r\n" in disk:
            problems.append("磁盘产物含 CRLF")
        if disk != text.encode("utf-8"):
            problems.append("%s 与重算结果不一致（产物过期），重跑 python tools/contentc/plant_levels.py" % path)
    for line in problems:
        print("FAIL:", line)
    print("plant_levels plants=%d leveling=%d byLevelCount=%s ragged=%d/%d unknowns=%d"
          % (len(plants), counts.get("plantsWithLeveling"), by_count,
             counts.get("raggedPlants"), counts.get("nullStatPairs"), len(table.get("unknowns") or [])))
    return 0 if not problems else 1


def needle_report(table, needles):
    blob = render(table)
    for needle in needles:
        n = blob.count(needle)
        print("needle %-24s hits=%d" % (needle, n))
    plants = table.get("plants") or {}
    for needle in needles:
        hits = [name for name in plants if needle.lower() in name.lower()]
        if hits:
            for name in hits[:5]:
                row = plants[name]
                print("  %-28s levelCount=%d cap=%r source=%s ragged=%s"
                      % (name, row["levelCount"], row["levelCap"], row["source"], row["raggedStats"]))
    return 0


def main(argv):
    obb = DEFAULT_OBB
    out = DEFAULT_OUT
    needles = []
    do_check = False
    args = list(argv)
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--obb":
            i += 1
            obb = Path(args[i])
        elif arg == "--out":
            i += 1
            out = Path(args[i])
        elif arg == "--needle":
            i += 1
            needles.extend(args[i].split(","))
        elif arg == "--check":
            do_check = True
        else:
            print("unknown argument:", arg)
            return 2
        i += 1

    table = build(obb)
    if needles:
        return needle_report(table, needles)
    if do_check:
        return check(table, out)
    dump(table, out)
    counts = table["counts"]
    print("wrote %s plants=%d leveling=%d ragged=%d nullPairs=%d unknowns=%d"
          % (out, counts["plants"], counts["plantsWithLeveling"], counts["raggedPlants"],
             counts["nullStatPairs"], len(table["unknowns"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
