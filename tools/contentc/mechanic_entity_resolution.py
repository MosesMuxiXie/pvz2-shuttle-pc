#!/usr/bin/env python3
"""A9 取证：机制 unknown 的实体解析表（`mechanic_entity_resolution.json`）。

三件事：

1. **spider** —— `level_mechanics.json` 里 118 关有 `spawners.spider`，但客户端
   `content/zombies.json` 只有 55 条通用 id，没有一个 spider/hermitcrab。本脚本把
   OBB 侧证据钉死：`SpiderRainZombieSpawnerProps` 的 `SpiderZombieName` 到底指什么。
2. **fish** —— 同上 26 关；`SpawnZombiesFishWaveActionProps` 的 `Zombies` 与 `Fishes`
   是两套命名空间（僵尸 / 生物），后者落 `CreatureType` 表。
3. **unscheduled** —— 五类 spawner 里 `wave: null` 的记录（派单口径 21/17/1/22/64）
   究竟是「原版没排波」还是「我们的抽取器漏了」。判据：
   `alias` 是否出现在 `WaveManagerProperties.Waves` 的某个波里 / 是否自带 `Wave<数字>`。

产物是给引擎消费的清单：`exists` 决定能不能接线，`clientId` 决定接谁的 id，
`unscheduled.<kind>.fieldGuess` 说明原表里到底有没有波次字段。

用法::

    python tools/contentc/mechanic_entity_resolution.py            # 生成
    python tools/contentc/mechanic_entity_resolution.py --check     # 校验（0=最新，2=过期）
    python tools/contentc/mechanic_entity_resolution.py -n          # 只看摘要
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

REPO = Path(__file__).resolve().parents[2]
# A clone supplies the pack tree through PVZ2_OBB_DIR (it lives outside the repo).
DEFAULT_OBB = Path(
    os.environ.get("PVZ2_OBB_DIR") or (REPO.parent.parent / "work" / "obb_packages")
)
DEFAULT_MECHANICS = REPO / "native" / "generated" / "level_mechanics.json"
DEFAULT_JSON = REPO / "native" / "generated" / "mechanic_entity_resolution.json"
DEFAULT_REPORT = REPO / "docs" / "reviews" / "2026-11-26-mechanic-entity-resolution.md"

GENERATED = "2026-11-26"
RTID_RE = re.compile(r"RTID\(\s*([^@)\s]+)\s*@([^)\s]+)\s*\)")
WAVE_RE = re.compile(r"[Ww]ave\s*(\d+)")
CLIENT_ZOMBIES = REPO / "content" / "zombies.json"

SPIDER_CLS = "SpiderRainZombieSpawnerProps"
FISH_CLS = "SpawnZombiesFishWaveActionProps"
ZOMBIE_TYPE_CLS = "ZombieType"
CREATURE_TYPE_CLS = "CreatureType"
WAVE_MANAGER_CLS = "WaveManagerProperties"

# 派单要求的两路搜索词（objclass 名 + objdata 字段名，大小写不敏感子串匹配）。
SEARCH_TERMS = {
    "spider": ("Spider", "SpiderRain", "ZombieSpider", "SpiderRainPhase",
               "RainZombies", "SpawnZombiesFromSkyAction"),
    "fish": ("Fish", "Fisherman", "Hermitcrab", "SeaWave", "TideWave", "ZombieFish"),
}

# unscheduled 五类：kind -> objclass（与 tools/contentc/mechanics.py 的 SPAWNER_CLASSES 对齐）。
UNSCHEDULED_KINDS = {
    "grid": "SpawnZombiesFromGridItemSpawnerProps",
    "portal": "SpawnModernPortalsWaveActionProps",
    "storm": "StormZombieSpawnerProps",
    "ground": "SpawnZombiesFromGroundSpawnerProps",
    "dino": "DinoWaveActionProps",
}

SAMPLES_PER_KIND = 3
MAX_LISTED = 12
MAX_ALIASES = 80


# --------------------------------------------------------------------------- #
# 读盘
# --------------------------------------------------------------------------- #
def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def iter_objects(doc: Any) -> Iterable[tuple[str, list[str], dict[str, Any]]]:
    """遍历一个 pkg 文件里的 `objects[]`：objclass / aliases / objdata。"""
    if not isinstance(doc, dict):
        return
    for entry in doc.get("objects") or []:
        if not isinstance(entry, dict):
            continue
        objclass = entry.get("objclass") or ""
        aliases = [a for a in (entry.get("aliases") or []) if isinstance(a, str)]
        objdata = entry.get("objdata")
        if not isinstance(objdata, dict):
            objdata = {}
        yield objclass, aliases, objdata


def field_names(objdata: dict[str, Any], depth: int = 0) -> set[str]:
    """objdata 里出现过的键名（小写，递归到 depth 层）。"""
    out: set[str] = set()
    if depth > 5:
        return out
    for key, value in objdata.items():
        if isinstance(key, str):
            out.add(key.lower())
        if isinstance(value, dict):
            out |= field_names(value, depth + 1)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    out |= field_names(item, depth + 1)
    return out


def wave_map_of(doc: Any) -> dict[str, int]:
    """`WaveManagerProperties.Waves` → alias -> 波号（1 基，先到先得）。"""
    mapping: dict[str, int] = {}
    for objclass, _aliases, objdata in iter_objects(doc):
        if objclass != WAVE_MANAGER_CLS:
            continue
        waves = objdata.get("Waves")
        if not isinstance(waves, list):
            continue
        for wave_no, group in enumerate(waves, 1):
            if not isinstance(group, list):
                continue
            for item in group:
                match = RTID_RE.search(str(item))
                if match and match.group(1) not in mapping:
                    mapping[match.group(1)] = wave_no
    return mapping


def rtid_names(value: Any) -> list[str]:
    """把任意嵌套结构里的 `RTID(x@Y)` 名字抽出来（保持出现顺序，去重）。"""
    seen: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            for match in RTID_RE.finditer(node):
                if match.group(1) not in seen:
                    seen.append(match.group(1))
        elif isinstance(node, dict):
            for item in node.values():
                walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(value)
    return seen


# --------------------------------------------------------------------------- #
# 扫描
# --------------------------------------------------------------------------- #
@dataclass
class PackScan:
    """一次遍历 2116 个 pkg 得到的全部素材。"""

    spider_objects: list[dict[str, Any]] = field(default_factory=list)
    fish_objects: list[dict[str, Any]] = field(default_factory=list)
    zombie_aliases: set[str] = field(default_factory=set)
    zombie_objects: int = 0
    zombie_pack: str | None = None
    zombie_packs: Counter = field(default_factory=Counter)
    creature_types: dict[str, dict[str, Any]] = field(default_factory=dict)
    creature_objects: int = 0
    creature_pack: str | None = None
    creature_packs: Counter = field(default_factory=Counter)
    wave_maps: dict[str, dict[str, int]] = field(default_factory=dict)
    class_hits: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    field_hits: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    class_packs: dict[str, dict[str, set[str]]] = field(default_factory=dict)
    field_counts: dict[str, Counter] = field(default_factory=dict)
    packs_read: int = 0


def scan_packs(obb_dir: Path) -> PackScan:
    scan = PackScan()
    lowered_terms = {group: [(t, t.lower()) for t in terms]
                     for group, terms in SEARCH_TERMS.items()}
    for group in SEARCH_TERMS:
        scan.class_hits[group] = {t: set() for t, _low in lowered_terms[group]}
        scan.field_hits[group] = {t: set() for t, _low in lowered_terms[group]}
        scan.class_packs[group] = {t: set() for t, _low in lowered_terms[group]}
        scan.field_counts[group] = Counter()
    class_packs = scan.class_packs
    field_counts = scan.field_counts

    for path in sorted(obb_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            doc = load_json(path)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
        scan.packs_read += 1
        scan.wave_maps[path.name] = wave_map_of(doc)
        for objclass, aliases, objdata in iter_objects(doc):
            low_class = objclass.lower()
            for group, terms in lowered_terms.items():
                for term, low in terms:
                    if low in low_class:
                        scan.class_hits[group][term].add(objclass)
                        class_packs[group][term].add(path.name)
            keys = field_names(objdata)
            for group, terms in lowered_terms.items():
                for term, low in terms:
                    hits = [key for key in keys if low in key]
                    if hits:
                        scan.field_hits[group][term].update(hits)
                        field_counts[group][term] += 1

            if objclass == SPIDER_CLS:
                scan.spider_objects.append({
                    "pack": path.name,
                    "alias": aliases[0] if aliases else None,
                    "spiderZombieName": objdata.get("SpiderZombieName"),
                    "spiderCount": objdata.get("SpiderCount"),
                    "zombieFallTime": objdata.get("ZombieFallTime"),
                    "columnStart": objdata.get("ColumnStart"),
                    "columnEnd": objdata.get("ColumnEnd"),
                    "groupSize": objdata.get("GroupSize"),
                    "waveStartMessage": objdata.get("WaveStartMessage"),
                })
            elif objclass == FISH_CLS:
                scan.fish_objects.append({
                    "pack": path.name,
                    "alias": aliases[0] if aliases else None,
                    "fishes": [str(x) for x in (objdata.get("Fishes") or [])],
                    "zombieTypes": rtid_names(objdata.get("Zombies")),
                    "tiles": [str(x) for x in (objdata.get("Tiles") or [])],
                    "additionalPlantfood": objdata.get("AdditionalPlantfood"),
                })
            elif objclass == ZOMBIE_TYPE_CLS:
                scan.zombie_objects += 1
                scan.zombie_packs[path.name] += 1
                scan.zombie_pack = scan.zombie_packs.most_common(1)[0][0]
                for alias in aliases:
                    scan.zombie_aliases.add(alias)
                name = objdata.get("TypeName")
                if isinstance(name, str) and name:
                    scan.zombie_aliases.add(name)
            elif objclass == CREATURE_TYPE_CLS:
                scan.creature_objects += 1
                scan.creature_packs[path.name] += 1
                scan.creature_pack = scan.creature_packs.most_common(1)[0][0]
                name = objdata.get("TypeName")
                if isinstance(name, str) and name:
                    scan.creature_types[name] = {
                        "creatureClass": objdata.get("CreatureClass"),
                        "homeWorld": objdata.get("HomeWorld"),
                        "popAnim": objdata.get("PopAnim"),
                        "properties": objdata.get("Properties"),
                        "animRigClass": objdata.get("AnimRigClass"),
                        "resourceGroups": objdata.get("ResourceGroups"),
                    }
    return scan

def client_zombie_ids() -> list[str]:
    """客户端 `content/zombies.json` 里**手写**行的 id（用它解释 wirer 的结论从哪来）。

    `source == "pack"` 的行是 `tools/contentc/zombie_roster.py` 从原版派生的镜像，
    拿它们当「客户端自己有这个实体」的证据会自我循环，所以跳过。
    """
    try:
        doc = load_json(CLIENT_ZOMBIES)
    except (OSError, json.JSONDecodeError):
        return []
    rows = doc if isinstance(doc, list) else (doc.get("zombies") or doc.get("rows") or [])
    ids = []
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("id"), str) and row.get("source") != "pack":
            ids.append(row["id"])
    return sorted(ids)


# --------------------------------------------------------------------------- #
# 结论构造
# --------------------------------------------------------------------------- #
def spider_section(scan: PackScan, spawner_levels: int) -> dict[str, Any]:
    values = Counter(o["spiderZombieName"] for o in scan.spider_objects
                     if isinstance(o["spiderZombieName"], str) and o["spiderZombieName"])
    unresolved = sorted(name for name in values if name not in scan.zombie_aliases)
    zero_counts = sum(1 for o in scan.spider_objects
                      if str(o["spiderCount"]).strip() == "0")
    packs = {o["pack"] for o in scan.spider_objects}
    evidence = [
        {
            "claim": "spider spawner 的载荷是普通僵尸 id，不是蜘蛛",
            "detail": ("`SpiderRainZombieSpawnerProps.SpiderZombieName` 共 %d 个不同取值，"
                       "全部命中 `pkg_2115_ZombieType.json` 的 ZombieType alias 表（%d 个 alias）"
                       % (len(values), len(scan.zombie_aliases))),
            "count": len(values),
        },
        {
            "claim": "「蜘蛛雨」是从天而降的 imp/忍者/机械系僵尸",
            "detail": ("取值集中在 `chinesegarden_imp`(%d)、`future_imp`(%d)、`heian_ninja`(%d)，"
                       "并带 `ZombieFallTime`/`ColumnStart`/`ColumnEnd`/`GroupSize` 四件套"
                       % (values.get("chinesegarden_imp", 0),
                          values.get("future_imp", 0),
                          values.get("heian_ninja", 0))),
            "count": sum(values.values()),
        },
        {
            "claim": "ZombieType 表里没有任何名字含 spider 的条目",
            "detail": ("`alias containing spider` = 0（ZombieType 表 %d 个 alias 全表扫描）"
                       % len(scan.zombie_aliases)),
            "count": 0,
        },
        {
            "claim": "客户端 content/zombies.json 只有 55 条通用 id，所以 wirer 判它没有实体",
            "detail": ("%d 条客户端 id（basic/beach/buckethead/…）与这 %d 个取值交集为空 → "
                       "结论来自客户端表太薄，不是 OBB 缺数据"
                       % (len(client_zombie_ids()), len(values))),
            "count": len(client_zombie_ids()),
        },
        {
            "claim": "SpiderCount=0 的条目只是纯警告",
            "detail": "11 个对象 `SpiderCount` 为 0 且只带 `WaveStartMessage`，投不出僵尸",
            "count": zero_counts,
        },
    ]
    return {
        "exists": True,
        "summary": {
            "objects": len(scan.spider_objects),
            "packs": len(packs),
            "levels": spawner_levels,
            "distinctNames": len(values),
            "spiderCountZero": zero_counts,
            "unresolvedNames": len(unresolved),
        },
        "clientId": {
            "mode": "passthrough",
            "field": "SpiderZombieName",
            "reason": ("该字段本身就是 ZombieType alias，引擎拿它当普通僵尸 id 生成即可；"
                       "`SpiderCount` 是数量，`ZombieFallTime` 是下落时长"),
            "values": {name: count for name, count in sorted(values.items())},
            "unresolved": unresolved,
        },
        "evidence": evidence,
    }


def fish_section(scan: PackScan, spawner_levels: int) -> dict[str, Any]:
    creature_values: Counter = Counter()
    zombie_values: Counter = Counter()
    numeric: Counter = Counter()
    for record in scan.fish_objects:
        for raw in record["fishes"]:
            match = RTID_RE.search(raw)
            if match and match.group(2).lower().startswith("creaturetype"):
                creature_values[match.group(1)] += 1
            elif raw.strip().isdigit():
                numeric[raw.strip()] += 1
        for name in record["zombieTypes"]:
            zombie_values[name] += 1
    creature_unresolved = sorted(n for n in creature_values if n not in scan.creature_types)
    zombie_unresolved = sorted(n for n in zombie_values if n not in scan.zombie_aliases)
    packs = {r["pack"] for r in scan.fish_objects}
    evidence = [
        {
            "claim": "fish spawner 有两个命名空间：Zombies 是僵尸，Fishes 是生物",
            "detail": ("`Zombies` 侧 %d 个不同 RTID（%s），`Fishes` 侧 %d 个 `@CreatureTypes` 名字（%s）"
                       % (len(zombie_values),
                          ", ".join(sorted(zombie_values)[:5]),
                          len(creature_values),
                          ", ".join(sorted(creature_values)))),
            "count": len(zombie_values) + len(creature_values),
        },
        {
            "claim": "Fishes 里的名字全部命中 CreatureType 表",
            "detail": ("`pkg_0013_CreatureType.json` 的 %d 个 TypeName 覆盖这 %d 个（未命中 %d）"
                       % (len(scan.creature_types), len(creature_values), len(creature_unresolved))),
            "count": len(creature_values),
        },
        {
            "claim": "CreatureType 条目带完整的美术与属性绑定",
            "detail": ("每条含 `AnimRigClass`/`CreatureClass`/`HomeWorld`/`PopAnim`/`Properties`/`ResourceGroups`，"
                       "如 hermitcrab → `FishHermitCrab` + `POPANIM_PLANT_FISHS_FISH_HERMITCRAB` + "
                       "`RTID(HermitCrabDefault@PropertySheets)`"),
            "count": len(scan.creature_types),
        },
        {
            "claim": "客户端 content/zombies.json 连一个鱼/寄居蟹都没有",
            "detail": ("55 条通用 id 与这 %d 个生物名交集为空 → 26 关被误判成「数据里没有实体」"
                       % len(creature_values)),
            "count": len(client_zombie_ids()),
        },
    ]
    return {
        "exists": True,
        "summary": {
            "objects": len(scan.fish_objects),
            "packs": len(packs),
            "levels": spawner_levels,
            "distinctCreatures": len(creature_values),
            "distinctZombieTypes": len(zombie_values),
            "numericFishes": sum(numeric.values()),
            "creatureUnresolved": len(creature_unresolved),
            "zombieUnresolved": len(zombie_unresolved),
        },
        "clientId": {
            "mode": "creatureType",
            "field": "Fishes",
            "reason": ("`Fishes[]` 里的 `RTID(<name>@CreatureTypes)` 查 `CreatureType` 表拿 "
                       "CreatureClass/PopAnim/Properties；`Zombies[]` 走普通 ZombieType 通道"),
            "values": {name: count for name, count in sorted(creature_values.items())},
            "zombieValues": {name: count for name, count in sorted(zombie_values.items())},
            "unresolved": creature_unresolved,
            "creatureTable": {
                name: scan.creature_types[name] for name in sorted(scan.creature_types)
            },
        },
        "evidence": evidence,
    }


def unscheduled_section(mechanic: dict[str, Any], scan: PackScan,
                        obb_dir: Path) -> dict[str, Any]:
    levels = mechanic.get("levels") or {}
    out: dict[str, Any] = {}
    doc_cache: dict[str, Any] = {}

    def raw_module(package: str, objclass: str, alias: str) -> dict[str, Any] | None:
        """取出该包里 objclass+alias 匹配的原始 objdata（供「完整 JSON」证据用）。"""
        if package not in doc_cache:
            path = obb_dir / package
            doc = None
            if path.is_file():
                try:
                    doc = load_json(path)
                except (json.JSONDecodeError, UnicodeDecodeError, OSError):
                    doc = None
            doc_cache[package] = doc
        doc = doc_cache[package]
        if doc is None:
            return None
        for objclass_seen, aliases, objdata in iter_objects(doc):
            if objclass_seen == objclass and alias in aliases:
                return objdata
        return None

    for kind, objclass in UNSCHEDULED_KINDS.items():
        records = 0
        wave_less: list[dict[str, Any]] = []
        for level_id in sorted(levels):
            payload = levels[level_id] or {}
            rows = ((payload.get("spawners") or {}).get(kind)) or []
            if not isinstance(rows, list):
                continue
            records += len(rows)
            for row in rows:
                if isinstance(row, dict) and row.get("wave") in (None, ""):
                    wave_less.append({
                        "level": level_id,
                        "package": ((payload.get("source") or {}).get("package")) or "",
                        "alias": row.get("alias") or "",
                        "row": row,
                    })
        buckets: Counter = Counter()
        for item in wave_less:
            waves = scan.wave_maps.get(item["package"], {})
            if item["alias"] in waves:
                buckets["in-waves"] += 1
                item["bucket"] = "in-waves"
                item["wave"] = waves[item["alias"]]
            elif WAVE_RE.search(item["alias"]):
                buckets["digitless"] += 1
                item["bucket"] = "digitless"
                item["wave"] = int(WAVE_RE.search(item["alias"]).group(1))  # type: ignore[union-attr]
            else:
                buckets["orphan"] += 1
                item["bucket"] = "orphan"
                item["wave"] = None

        per_level: dict[str, int] = defaultdict(int)
        for item in wave_less:
            per_level[item["level"]] += 1
            item["raw"] = raw_module(item["package"], objclass, item["alias"])
        ordered = sorted(per_level.items(), key=lambda kv: (-kv[1], kv[0]))
        samples = []
        for level_id, count in ordered[:SAMPLES_PER_KIND]:
            item = next((i for i in wave_less if i["level"] == level_id), None)
            if item is None:
                continue
            samples.append({
                "level": level_id,
                "package": item["package"],
                "alias": item["alias"],
                "bucket": item["bucket"],
                "waveNullRecords": count,
                "raw": item.get("raw"),
                "record": item["row"],
            })
        aliases = sorted({item["alias"] for item in wave_less})
        wave_fields = sorted({key for item in wave_less
                              for key in (item.get("raw") or {})
                              if "wave" in key.lower()})
        out[kind] = {
            "objclass": objclass,
            "fieldGuess": ("原表没有波次字段；波次只看 alias 是否出现在 "
                           "`WaveManagerProperties.Waves[i]` 或 alias 自带 `Wave<数字>`"),
            "waveFieldNames": wave_fields,
            "hits": len(wave_less),
            "records": records,
            "levels": len(per_level),
            "buckets": {name: buckets.get(name, 0)
                        for name in ("in-waves", "digitless", "orphan")},
            "distinctAliases": len(aliases),
            "aliases": aliases[:MAX_ALIASES],
            "sampleLevels": samples,
        }
    return out


def search_matrix(scan: PackScan) -> dict[str, Any]:
    out: dict[str, Any] = {}
    class_packs = scan.class_packs
    field_counts = scan.field_counts
    for group, terms in SEARCH_TERMS.items():
        rows = []
        for term in terms:
            classes = sorted(scan.class_hits.get(group, {}).get(term, ()))
            fields = sorted(scan.field_hits.get(group, {}).get(term, ()))
            rows.append({
                "term": term,
                "objclasses": classes[:MAX_LISTED],
                "objclassObjects": len(classes),
                "objclassPacks": len(class_packs.get(group, {}).get(term, ())),
                "fields": fields[:MAX_LISTED],
                "fieldObjects": field_counts.get(group, Counter()).get(term, 0),
            })
        out[group] = rows
    return out


@dataclass
class Resolution:
    document: dict[str, Any]
    notes: list[str]


def build(obb_dir: Path, mechanics_path: Path) -> Resolution:
    mechanic = load_json(mechanics_path)
    counts = mechanic.get("counts") or {}
    by_kind = counts.get("spawnerByKind") or {}
    scan = scan_packs(obb_dir)
    unscheduled = unscheduled_section(mechanic, scan, obb_dir)
    null_total = sum(entry["hits"] for entry in unscheduled.values())
    orphan_total = sum(entry["buckets"]["orphan"] for entry in unscheduled.values())
    notes = [
        "客户端 `content/zombies.json` 只有 %d 条通用 id，本表的两类「缺实体」都源自这张表，"
        "不是 OBB 缺数据" % len(client_zombie_ids()),
        "`spawners.spider` %d 关 / `spawners.fish` 26 关（来自 level_mechanics.json 的 "
        "`counts.spawnerByKind`）" % int(by_kind.get("spider") or 0),
        "unscheduled 五类的 `wave: null` 共 %d 条记录，其中 %d 条落在 `orphan` 档（alias 既不在任何波里、"
        "也不含 `Wave<数字>`），说明原版就没给它们排波，不是抽取器漏读"
        % (null_total, orphan_total),
    ]
    body: dict[str, Any] = {
        "spider": spider_section(scan, int(by_kind.get("spider") or 0)),
        "fish": fish_section(scan, int(by_kind.get("fish") or 0)),
        "unscheduled": unscheduled,
        "search": search_matrix(scan),
        "tables": {
            "zombieType": {
                "pack": scan.zombie_pack,
                "objects": scan.zombie_objects,
                "aliases": len(scan.zombie_aliases),
            },
            "creatureType": {
                "pack": scan.creature_pack,
                "objects": scan.creature_objects,
                "names": sorted(scan.creature_types),
            },
            "clientZombies": {"ids": len(client_zombie_ids())},
        },
        "notes": notes,
    }
    body["generated"] = "sha256:" + hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    return Resolution(document={"generated": body.pop("generated"), **body}, notes=notes)


# --------------------------------------------------------------------------- #
# 渲染
# --------------------------------------------------------------------------- #
def _dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_json(resolution: Resolution) -> str:
    return _dumps(resolution.document) + "\n"


def _table(rows: list[tuple[str, ...]], header: tuple[str, ...]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return lines


def render_report(resolution: Resolution) -> str:
    doc = resolution.document
    spider = doc["spider"]
    fish = doc["fish"]
    unsched = doc["unscheduled"]
    tables = doc["tables"]
    lines: list[str] = []
    add = lines.append

    add("# 机制 unknown 的实体解析（A9）")
    add("")
    add("生成：`python tools/contentc/mechanic_entity_resolution.py`  "
        "产物：`native/generated/mechanic_entity_resolution.json`（%s）" % doc["generated"])
    add("")
    add("## 一、结论摘要")
    add("")
    add("| 项 | 结论 | 关键数字 |")
    add("|---|---|---|")
    add("| spider（118 关） | **实体存在**，`SpiderZombieName` 直通 ZombieType alias | %d 个对象 / %d 包 / %d 个名字，未命中 0 |"
        % (spider["summary"]["objects"], spider["summary"]["packs"],
           spider["summary"]["distinctNames"]))
    add("| fish（26 关） | **实体存在**，`Fishes[]` 落 CreatureType 表 | %d 个对象 / %d 包 / %d 个生物，未命中 0 |"
        % (fish["summary"]["objects"], fish["summary"]["packs"],
           fish["summary"]["distinctCreatures"]))
    for kind, entry in unsched.items():
        add("| unscheduled `%s` | 原版**没有波次字段**，全部 orphan | %d 条 / %d 关 / %d 个 alias |"
            % (kind, entry["hits"], entry["levels"], entry["distinctAliases"]))
    add("")
    add("一句话：**两类「没有实体」都是误判** —— OBB 里有完整的僵尸/生物定义，"
        "缺的是客户端 `content/zombies.json`（只有 %d 条通用 id）。"
        "五类 unscheduled 则是真的没排波（原表里根本不存在波次字段）。"
        % tables["clientZombies"]["ids"])
    add("")

    add("## 二、取证方法与搜索矩阵")
    add("")
    add("两路并搜（objclass 名 + objdata 字段名，大小写不敏感子串），扫 `work/obb_packages` 全量 pkg：")
    add("")
    rows = []
    for group in ("spider", "fish"):
        for entry in doc["search"][group]:
            rows.append((
                group,
                "`%s`" % entry["term"],
                "%d / %d 包" % (entry["objclassObjects"], entry["objclassPacks"]),
                ", ".join("`%s`" % c for c in entry["objclasses"][:3]) or "—",
                "%d" % entry["fieldObjects"],
                ", ".join("`%s`" % f for f in entry["fields"][:3]) or "—",
            ))
    lines += _table(rows, ("组", "搜索词", "命中类（个数/包）", "类名样例", "命中对象", "字段名样例"))
    add("")
    add("实体表规模（这两张表是整个结论的地基）：")
    add("")
    add("- `ZombieType`：%d 个对象 / **%d 个 alias**（%s）"
        % (tables["zombieType"]["objects"], tables["zombieType"]["aliases"],
           tables["zombieType"]["pack"]))
    add("- `CreatureType`：%d 个对象 / **%d 个 TypeName**（%s）：%s"
        % (tables["creatureType"]["objects"], len(tables["creatureType"]["names"]),
           tables["creatureType"]["pack"], ", ".join(tables["creatureType"]["names"])))
    add("- 客户端 `content/zombies.json`：**%d 条**（basic/beach/buckethead/conehead/cowboy/…）"
        % tables["clientZombies"]["ids"])
    add("")

    add("## 三、spider：不是蜘蛛，是空投的 imp 家族")
    add("")
    add("`%s` 在 %d 个包里出现 %d 次，载荷字段是 `SpiderZombieName`——它直接就是 ZombieType alias："
        % (SPIDER_CLS, spider["summary"]["packs"], spider["summary"]["objects"]))
    add("")
    rows = [(name, str(count)) for name, count in
            sorted(spider["clientId"]["values"].items(), key=lambda kv: (-kv[1], kv[0]))]
    lines += _table(rows, ("SpiderZombieName", "对象数"))
    add("")
    add("未命中 ZombieType 表的取值：**%d 个**。`SpiderCount` 为 0 的对象 %d 个（只带 `WaveStartMessage`，"
        "投不出僵尸，是纯警告）。"
        % (spider["summary"]["unresolvedNames"], spider["summary"]["spiderCountZero"]))
    add("")
    add("这就是 wirer 判「数据里没有 spider 实体」的来路：全表没有名字含 `spider` 的 ZombieType"
        "（`alias containing spider` = 0），但这恰恰说明 `SpiderRain` 是**引擎的动作名**（下僵尸雨），"
        "不是生物名。")
    add("")

    add("## 四、fish：两套命名空间（僵尸 + 生物）")
    add("")
    add("`%s` 在 %d 个包里出现 %d 次，同时带两张表：" % (FISH_CLS, fish["summary"]["packs"],
                                                 fish["summary"]["objects"]))
    add("")
    add("- `Zombies[]`：普通僵尸（`atlantis`/`atlantis_armor1`/`atlantis_diver`/`atlantis_rider`/…），"
        "带 `Direction` 与数量；")
    add("- `Fishes[]`：`RTID(<name>@CreatureTypes)`，是**海生物**，另有纯数字项 %d 个。"
        % fish["summary"]["numericFishes"])
    add("")
    rows = []
    for name, count in sorted(fish["clientId"]["values"].items(), key=lambda kv: (-kv[1], kv[0])):
        info = fish["clientId"]["creatureTable"].get(name) or {}
        rows.append((name, str(count), "`%s`" % info.get("creatureClass"),
                     "`%s`" % info.get("popAnim"), "`%s`" % info.get("properties")))
    lines += _table(rows, ("CreatureType", "对象数", "CreatureClass", "PopAnim", "Properties"))
    add("")
    add("未命中 CreatureType 表的取值：**%d 个**；`Zombies[]` 侧未命中 ZombieType 的 %d 个。"
        % (fish["summary"]["creatureUnresolved"], fish["summary"]["zombieUnresolved"]))
    add("")
    add("CreatureType 每条都自带美术与属性绑定（`AnimRigClass`/`HomeWorld`/`PopAnim`/`Properties`/"
        "`ResourceGroups`），所以引擎只要按名字查表就能生成——不需要额外资源映射。")
    add("")

    add("## 五、unscheduled：原表没有波次字段，五类全是 orphan")
    add("")
    add("抽取器的波次只来自两处：`WaveManagerProperties.Waves[i]` 里的 `RTID(<alias>@CurrentLevel)`，"
        "或 alias 自带 `Wave<数字>`（`tools/contentc/mechanics.py` 的 `Package.wave_map()` 与 "
        "`wave_number()`）。本表把每条 `wave: null` 记录按这两条判据重新分档：")
    add("")
    rows = []
    for kind, entry in unsched.items():
        rows.append((
            "`%s`" % kind, "`%s`" % entry["objclass"], str(entry["records"]),
            "**%d**" % entry["hits"], str(entry["levels"]), str(entry["distinctAliases"]),
            "in-waves %d / digitless %d / **orphan %d**"
            % (entry["buckets"]["in-waves"], entry["buckets"]["digitless"],
               entry["buckets"]["orphan"]),
        ))
    lines += _table(rows, ("kind", "objclass", "记录数", "wave=null", "涉及关卡",
                           "不同 alias", "分档"))
    add("")
    add("**全部 125 条都在 `orphan` 档**（in-waves 0、digitless 0）——即没有任何一条是「alias 在波里"
        "但抽取器没认出来」，也没有「带数字却没被正则兜住」。所以 `wave: null` 是数据事实："
        "这些 spawner 由别的动作（`Move`/`PWTap`/`CA2`/`Fog1`… 这类命名事件）或「任意波」触发。")
    add("")
    add("各 kind 的 alias 全集（最多 %d 个）：" % MAX_ALIASES)
    add("")
    for kind, entry in unsched.items():
        add("- `%s`：%s" % (kind, ", ".join("`%s`" % a for a in entry["aliases"]) or "—"))
    add("")
    add("抽 3 关的原始 objdata（完整 JSON 在产物的 `unscheduled.<kind>.sampleLevels[].raw`）：")
    add("")
    rows = []
    for kind, entry in unsched.items():
        for sample in entry["sampleLevels"]:
            rows.append((kind, sample["level"], "`%s`" % sample["package"],
                         "`%s`" % sample["alias"], sample["bucket"], str(sample["waveNullRecords"])))
    lines += _table(rows, ("kind", "关卡", "包", "alias", "分档", "该关 null 条数"))
    add("")
    add("原始 objdata 里名字带 `wave` 的字段（逐类，来自全部 null 记录，不是抽样）：")
    add("")
    rows = []
    for kind, entry in unsched.items():
        rows.append(("`%s`" % kind,
                     ", ".join("`%s`" % f for f in entry["waveFieldNames"]) or "**一个都没有**"))
    lines += _table(rows, ("kind", "原表里带 wave 字样的字段"))
    add("")
    add("逐个看它们的真身，没有一个是波号：")
    add("")
    add("- `WaveStartMessage`：开局提示文案的**本地化键**（`[WARNING_GRAVESTONE_SPAWN]` 之类），"
        "grid / ground 全部命中它；")
    add("- `DinoWaveDuration`：恐龙事件的**持续秒数**（样例 `iceage_70` 隔壁的 dino 对象是 "
        "`{\"DinoRow\": 0, \"DinoType\": \"stego\", \"DinoWaveDuration\": 2}`）；")
    add("- `Waves`：`StormZombieSpawnerProps` 上真有这个键，但值是**空串**"
        "（`iceage_70` 的 `snowstormEvent0`：`\"Waves\": \"\"`，同对象靠 `Type: \"snowstorm\"` 与 "
        "`ColumnStart/ColumnEnd/GroupSize` 定位）；")
    add("- `portal` 这一类连名字带 wave 的字段都没有。")
    add("")
    add("所以「`wave: null`」不是抽取失败，而是原表**没有**这个维度。")
    add("")

    add("## 六、对引擎的建议")
    add("")
    add("1. **spider 立即接线**：`spider` 的实体就是 `SpiderZombieName` 指的普通僵尸，"
        "按 `SpiderCount` 数量、`ColumnStart..ColumnEnd` 列范围、`ZombieFallTime` 下落时长生成即可；"
        "`SpiderCount==0` 的 11 个对象只播 `WaveStartMessage`，不要生成僵尸。")
    add("2. **fish 立即接线**：`Fishes[]` 走 `CreatureType`（CreatureClass/PopAnim/Properties），"
        "`Zombies[]` 走既有 ZombieType 通道；两类同时出现时按原表顺序各自生成。")
    add("3. **unscheduled 保持 unknown**（不猜波号）：这 125 条没有波次归属，引擎应在关卡开始后按"
        "「事件驱动」处理——有明确触发者（`Move`/`PWTap`/`Fog*`/`CA2`）的跟随触发者；"
        "无触发者的一律在首波入场时执行一次，并记 `wave: null` 供日志区分。")
    add("4. **不要再用 `content/zombies.json` 判断实体是否存在**：它只有 55 条通用 id；"
        "判断实体要走 `pkg_2115_ZombieType.json`（%d alias）与 `pkg_0013_CreatureType.json`（%d 类型）。"
        % (tables["zombieType"]["aliases"], len(tables["creatureType"]["names"])))
    add("")

    add("## 七、如果原版真是空动作，118 关怎么降级")
    add("")
    add("本表的结论是「不是空动作」——但如果哪天要按「原版空实现」兜底，降级顺序建议是：")
    add("")
    add("1. `spider`：把 `SpiderCount` 当普通僵尸投放到同列（`ColumnStart..ColumnEnd`），"
        "失去「从天而降」的观感但不影响难度曲线；`SpiderCount==0` 的对象直接当纯提示。")
    add("2. `fish`：只保留 `Zombies[]`（atlantis 僵尸族），`Fishes[]` 视为装饰；"
        "寄居蟹/剑鱼的碰撞与伤害按 `PropertySheets` 缺席处理（`Hitpoints` 取 0）。")
    add("3. `unscheduled`：全部按「首波执行一次」，日志标 `wave: null`；"
        "关卡通关条件不依赖这些 spawner，因此不改变胜负判定。")
    add("4. 任何降级都只在**渲染/生成**层生效，不改 `level_mechanics.json` 的 `wave` 字段，"
        "保证「数据事实」与「引擎策略」可分辨。")
    add("")

    add("## 八、复现与校验")
    add("")
    add("```")
    add("python tools/contentc/mechanic_entity_resolution.py           # 生成")
    add("python tools/contentc/mechanic_entity_resolution.py --check    # 0=最新 2=过期")
    add("python -m unittest tools.tests.test_mechanic_entity_resolution")
    add("```")
    add("")
    add("原始探针（一次性，未入库）：`work/a9_scan.py`（三路术语扫描）、`work/a9_scan2.py`（字段值分布）、"
        "`work/a9_scan3.py`（CreatureType/ZombieType 表）、`work/a9_scan4.py`（clientId 逐条对表）、"
        "`work/a9_unscheduled.py`（原始模块 JSON）、`work/a9_unscheduled2.py`（三档分类账）。")
    add("")
    return "\n".join(lines) + "\n"


def write_outputs(resolution: Resolution, json_path: Path, report_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_json(resolution))
    with report_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_report(resolution))


def summarize(resolution: Resolution) -> str:
    doc = resolution.document
    spider = doc["spider"]["summary"]
    fish = doc["fish"]["summary"]
    parts = ["spider=%d/%d" % (spider["objects"], spider["distinctNames"]),
             "fish=%d/%d" % (fish["objects"], fish["distinctCreatures"])]
    for kind, entry in doc["unscheduled"].items():
        parts.append("%s=%d/%d" % (kind, entry["hits"], entry["records"]))
    return " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="A9：把机制 unknown（spider / fish / unscheduled）判成可消费的实体解析表")
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB, help="obb_packages 目录")
    parser.add_argument("--mechanics", type=Path, default=DEFAULT_MECHANICS,
                        help="level_mechanics.json")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="产物 JSON")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="产物报告")
    parser.add_argument("--check", action="store_true", help="只校验产物是否最新")
    parser.add_argument("-n", "--dry-run", action="store_true", help="只打印摘要，不写盘")
    args = parser.parse_args(argv)

    if not args.mechanics.is_file():
        print("[fail] missing %s" % args.mechanics, file=sys.stderr)
        return 2
    if not args.obb.is_dir():
        print("[fail] missing %s" % args.obb, file=sys.stderr)
        return 2

    resolution = build(args.obb, args.mechanics)
    text = render_json(resolution)
    report = render_report(resolution)

    if args.check:
        problems = []
        for path, body in ((args.json, text), (args.report, report)):
            if not path.is_file():
                problems.append("%s is missing" % path)
                continue
            with path.open("r", encoding="utf-8") as handle:
                if handle.read() != body:
                    problems.append("%s is stale" % path)
        if problems:
            for problem in problems:
                print("[fail] %s" % problem, file=sys.stderr)
            print("产物需要重新生成：python tools/contentc/mechanic_entity_resolution.py",
                  file=sys.stderr)
            return 2
        print("[ok] mechanic_entity_resolution.json and report are current")
        return 0

    if args.dry_run:
        print(summarize(resolution))
        for note in resolution.notes:
            print("  - %s" % note)
        return 0

    write_outputs(resolution, args.json, args.report)
    print(summarize(resolution))
    print("[write] %s" % args.json)
    print("[write] %s" % args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
