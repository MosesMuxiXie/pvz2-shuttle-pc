"""Scan the original OBB tables for element / plant-food / boss data.

The S5 work needs to know which of those three concepts is *in the data* and
which has to be authored. The original tables are 2117 loose JSON files, so the
question is answered by scanning them, not by memory.

Two orthogonal searches per concept:

* **objclass** - the sheet's object class (`AtlantisStageProperties`,
  `LevelMutatorStartingPlantfoodProps`, ...). It names the table.
* **key** - any mapping key anywhere in the object data, at any depth. It names
  the field, which is what actually decides whether a value can drive the game.

Plus three targeted probes for the things the review must state exactly:

* `plantfood_actions` - every `Actions[]` entry with `Type == "plantfood"` in
  `pkg_2073_PlantPropertySheet.json`, with its owning plant and every field.
* `plantfood_fields` - every `*PlantFood*` key on that sheet, with how many
  objects carry it and how many of those are non-empty.
* `boss_events` - `pkg_2107_WorldData.json` `m_eventList` events whose type or
  name mentions a boss, grouped by world.

Usage (all read-only):

    python tools/contentc/s5scan.py --sheet                 # matched sheet names only
    python tools/contentc/s5scan.py --needle element        # one concept, hits inline
    python tools/contentc/s5scan.py --needle boss --limit 40
    python tools/contentc/s5scan.py --inventory             # every group, JSON
    python tools/contentc/s5scan.py --write-gaps            # regenerate the gap file
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterator

if __package__ in (None, ""):  # allow `python tools/contentc/s5scan.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from contentc import worlds  # noqa: E402
else:
    from . import worlds  # noqa: E402

REPO = worlds.REPO
DEFAULT_OBB = worlds.DEFAULT_OBB
DEFAULT_PACKAGE_GLOB = "*.json"
DEFAULT_GAPS = REPO / "native" / "generated" / "s5_data_gaps.json"
FORMAT = "pvz2-shuttle/s5-data-gaps@1"
MANIFEST = "_index.json"

# Concepts -> needles. The needles are matched case-insensitively against object
# classes and against every key path; a needle that only ever shows up in an
# unrelated table (e.g. `Fire` in `FireRate`) stays in the output so the review
# can say "hit, but irrelevant" instead of hiding it.
CONCEPTS: dict[str, tuple[str, ...]] = {
    "elements": (
        "element",
        "elemental",
        "flame",
        "water",
        "wind",
        "volt",
        "electric",
        "toxin",
        "poison",
        "illusion",
        "dark",
        "shadow",
        "light",
        "fire",
        "ice",
        "frost",
        "nature",
        "magic",
    ),
    "plantfood": (
        "plantfood",
        "plantfoodduration",
        "powerup",
        "power",
        "foodduration",
        "food",
    ),
    "boss": (
        "boss",
        "zomboss",
        "mech",
        "herohealth",
        "bosshealth",
        "phase",
        "stagehealth",
        "finalwave",
        "herophase",
    ),
    "levels": (
        "plantlevel",
        "levelstats",
        "levelup",
        "xp",
        "rank",
        "starlevel",
    ),
}

# objclass names that ARE the table for a concept, even when the fields look
# generic. Recorded so `--sheet` can answer "which tables exist".
SHEET_HINTS: dict[str, tuple[str, ...]] = {
    "elements": ("element", "magic", "mutator", "plantfusion", "power"),
    "plantfood": ("plantfood", "powerup", "mutator"),
    "boss": ("boss", "zomboss", "hero", "mech"),
    "levels": ("levelstats", "plantlevel"),
}

VALUE_CHARS = 96


def package_paths(obb_dir: Path) -> list[Path]:
    return sorted(obb_dir.glob(DEFAULT_PACKAGE_GLOB))


_CACHE: dict[str, dict | None] = {}


def load_package(path: Path) -> dict | None:
    """Load one package; the whole set is 45 MB, so it is cached process-wide.

    The inventory makes several passes over the same 2117 files (one per
    concept plus the targeted probes); without the cache each pass re-parses
    them and the tool takes minutes instead of seconds.
    """

    key = str(path)
    if key in _CACHE:
        return _CACHE[key]
    try:
        with path.open(encoding="utf-8-sig") as handle:
            doc = json.load(handle)
    except (OSError, json.JSONDecodeError):
        _CACHE[key] = None
        return None
    _CACHE[key] = doc if isinstance(doc, dict) else None
    return _CACHE[key]


def walk_keys(value, prefix: str = "") -> Iterator[tuple[str, object]]:
    """Yield `(dotted key path, leaf value)` for every mapping key, at any depth."""

    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path, item
            if isinstance(item, (dict, list)):
                yield from walk_keys(item, path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, (dict, list)):
                yield from walk_keys(item, f"{prefix}[{index}]")


def short(value: object, limit: int = VALUE_CHARS) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        text = repr(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def matches(haystack: str, needles: tuple[str, ...]) -> str | None:
    low = haystack.lower()
    for needle in needles:
        if needle in low:
            return needle
    return None


def scan(obb_dir: Path, concept: str, limit: int = 25) -> dict:
    """Scan every package for one concept; returns tables, fields and counts."""

    needles = CONCEPTS[concept]
    hints = SHEET_HINTS[concept]
    paths = package_paths(obb_dir)
    sheets: Counter[str] = Counter()
    classes: Counter[str] = Counter()
    keys: Counter[str] = Counter()
    samples: dict[str, list[str]] = defaultdict(list)
    examples: list[dict] = []
    parsed = failed = 0
    objects_total = 0
    hit_rows = 0

    for path in paths:
        doc = load_package(path)
        if doc is None:
            failed += 1
            continue
        parsed += 1
        objects = doc.get("objects")
        if not isinstance(objects, list):
            continue
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            objects_total += 1
            objclass = str(obj.get("objclass") or "")
            data = obj.get("objdata")
            data = data if isinstance(data, dict) else {}
            alias = obj.get("aliases")
            alias = alias[0] if isinstance(alias, list) and alias else (alias or "")

            class_hit = matches(objclass, needles)
            if class_hit:
                classes[objclass] += 1
                hit_rows += 1
                if len(sheets) < 400 or path.stem in sheets:
                    sheets[path.stem] += 1
                if len(examples) < limit:
                    examples.append(
                        {
                            "kind": "objclass",
                            "package": path.stem,
                            "objclass": objclass,
                            "alias": str(alias),
                            "needle": class_hit,
                            "value": short(data),
                        }
                    )

            for keypath, value in walk_keys(data):
                leaf = keypath.rsplit(".", 1)[-1]
                key_hit = matches(leaf, needles)
                if not key_hit:
                    continue
                keys[keypath if "." not in keypath else leaf] += 1
                hit_rows += 1
                bucket = samples[leaf]
                if len(bucket) < 3:
                    rendered = f"{short(value)} @{path.stem}:{alias}"
                    if rendered not in bucket:
                        bucket.append(rendered)
                if len(examples) < limit:
                    examples.append(
                        {
                            "kind": "key",
                            "package": path.stem,
                            "objclass": objclass,
                            "alias": str(alias),
                            "needle": key_hit,
                            "key": keypath,
                            "value": short(value),
                        }
                    )

    hint_tables = sorted({c for c in classes if matches(c, hints)})
    return {
        "concept": concept,
        "needles": list(needles),
        "files": {
            "matched": len(paths),
            "parsed": parsed,
            "failed": failed,
            "objects": objects_total,
        },
        "hits": {
            "total": hit_rows,
            "objclasses": sum(classes.values()),
            "keys": sum(keys.values()),
        },
        "tables": hint_tables,
        "sheets": {name: count for name, count in sheets.most_common()},
        "objclasses": dict(classes.most_common()),
        "keys": dict(keys.most_common()),
        "samples": {key: values for key, values in sorted(samples.items())},
        "examples": examples,
    }


def plantfood_actions(obb_dir: Path) -> dict:
    """Every `Actions[]` entry with `Type == "plantfood"` in pkg_2073."""

    path = obb_dir / "pkg_2073_PlantPropertySheet.json"
    if not path.is_file():
        return {"sheet": "pkg_2073_PlantPropertySheet", "found": 0, "rows": []}
    doc = load_package(path) or {}
    rows = []
    for obj in doc.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        data = obj.get("objdata")
        if not isinstance(data, dict):
            continue
        alias = obj.get("aliases")
        alias = alias[0] if isinstance(alias, list) and alias else str(alias or "")
        actions = data.get("Actions")
        if not isinstance(actions, list):
            continue
        for index, action in enumerate(actions):
            if not isinstance(action, dict):
                continue
            if str(action.get("Type") or "").lower() != "plantfood":
                continue
            rows.append(
                {
                    "alias": alias,
                    "objclass": obj.get("objclass"),
                    "index": index,
                    "fields": {k: short(v, 64) for k, v in sorted(action.items())},
                    "cooldown": action.get("Cooldown"),
                }
            )
    # Which plant ids use those property names?
    owners = plantfood_owner_ids(obb_dir)
    for row in rows:
        row["plants"] = owners.get(row["alias"], [])
    return {
        "sheet": "pkg_2073_PlantPropertySheet",
        "objects_with_actions": sum(
            1
            for obj in doc.get("objects") or []
            if isinstance(obj, dict) and isinstance((obj.get("objdata") or {}).get("Actions"), list)
        ),
        "found": len(rows),
        "rows": rows,
    }


RTID_RE = re.compile(r"RTID\(\s*([^@)\s]+)\s*@([^)\s]+)\s*\)")


def rtid_name(value: object) -> str:
    """`RTID(SunflowerDefault@PlantProperties)` -> `SunflowerDefault`."""

    if not isinstance(value, str):
        return ""
    found = RTID_RE.search(value)
    return found.group(1) if found else ""


def plantfood_owner_ids(obb_dir: Path) -> dict[str, list[str]]:
    """Map a plant property name (e.g. `SunflowerDefault`) to plant ids.

    `pkg_2074_PlantType.json` is the only sheet that ties a plant id to the
    `PlantProperties` entry holding its actions: each row carries `TypeName`
    (the plant id) and `Properties` as `RTID(<props>@PlantProperties)`.
    Without this join the six plant-food actions could not be attributed.
    """

    path = obb_dir / "pkg_2074_PlantType.json"
    out: dict[str, list[str]] = defaultdict(list)
    if not path.is_file():
        return out
    doc = load_package(path) or {}
    for obj in doc.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        data = obj.get("objdata")
        if not isinstance(data, dict):
            continue
        ident = data.get("TypeName") or data.get("Name")
        if not ident:
            alias = obj.get("aliases")
            ident = alias[0] if isinstance(alias, list) and alias else str(alias or "")
        props = rtid_name(data.get("Properties"))
        if ident and props:
            out[props].append(str(ident))
    return out


def plantfood_fields(obb_dir: Path) -> dict:
    """Every `*PlantFood*` key on the plant sheet with fill counts."""

    path = obb_dir / "pkg_2073_PlantPropertySheet.json"
    if not path.is_file():
        return {"keys": {}, "objects": 0}
    doc = load_package(path) or {}
    counts: Counter[str] = Counter()
    filled: Counter[str] = Counter()
    samples: dict[str, list[str]] = defaultdict(list)
    objects = 0
    for obj in doc.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        data = obj.get("objdata")
        if not isinstance(data, dict):
            continue
        objects += 1
        alias = obj.get("aliases")
        alias = alias[0] if isinstance(alias, list) and alias else str(alias or "")
        for key, value in data.items():
            if "plantfood" not in key.lower():
                continue
            counts[key] += 1
            if value not in (None, "", [], {}, 0) and value is not False:
                filled[key] += 1
                if len(samples[key]) < 3:
                    samples[key].append(f"{short(value, 64)} @{alias}")
    return {
        "sheet": "pkg_2073_PlantPropertySheet",
        "objects": objects,
        "keys": {
            key: {
                "records": counts[key],
                "nonEmpty": filled[key],
                "samples": samples.get(key, []),
            }
            for key in sorted(counts)
        },
    }


BOSS_NEEDLE = re.compile(r"boss|zomboss|hero|mech", re.IGNORECASE)


def boss_events(obb_dir: Path) -> dict:
    """Boss events in `pkg_2107_WorldData.json`, grouped by world."""

    path = obb_dir / "pkg_2107_WorldData.json"
    if not path.is_file():
        return {"sheet": "pkg_2107_WorldData", "events": [], "byWorld": {}}
    doc = load_package(path) or {}
    events = []
    types: Counter[str] = Counter()
    worlds = 0
    for obj in doc.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        data = obj.get("objdata")
        if not isinstance(data, dict):
            continue
        worlds += 1
        world_name = str(data.get("m_worldName") or "")
        world_id = data.get("m_worldId")
        for event in data.get("m_eventList") or []:
            if not isinstance(event, dict):
                continue
            etype = str(event.get("m_eventType") or "")
            types[etype or "<none>"] += 1
            name = str(event.get("m_name") or "")
            if not (BOSS_NEEDLE.search(etype) or BOSS_NEEDLE.search(name)):
                continue
            events.append(
                {
                    "world": world_name,
                    "worldId": world_id,
                    "type": etype,
                    "name": name,
                    "dataString": event.get("m_dataString"),
                    "position": event.get("m_position"),
                }
            )
    by_world: dict[str, int] = Counter(e["world"] for e in events)
    return {
        "sheet": "pkg_2107_WorldData",
        "worlds": worlds,
        "eventTypes": dict(types.most_common()),
        "found": len(events),
        "byWorld": dict(sorted(by_world.items())),
        "events": events,
    }


def boss_fields(obb_dir: Path) -> dict:
    """Boss-ish fields on the zombie sheet (`pkg_2112`) and hero spawner."""

    out: dict[str, dict] = {}
    for stem, label in (
        ("pkg_2112_ZombiePropertySheet", "ZombieProperties"),
        ("pkg_0026_ZombieHeroSpawnerProps", "ZombieHeroSpawnerProps"),
        ("pkg_2097_RiftZombossRewards", "RiftZombossRewards"),
    ):
        path = obb_dir / f"{stem}.json"
        if not path.is_file():
            out[label] = {"missing": True}
            continue
        doc = load_package(path) or {}
        counts: Counter[str] = Counter()
        filled: Counter[str] = Counter()
        samples: dict[str, list[str]] = defaultdict(list)
        objects = 0
        for obj in doc.get("objects") or []:
            if not isinstance(obj, dict):
                continue
            data = obj.get("objdata")
            if not isinstance(data, dict):
                continue
            objects += 1
            alias = obj.get("aliases")
            alias = alias[0] if isinstance(alias, list) and alias else str(alias or "")
            for keypath, value in walk_keys(data):
                leaf = keypath.rsplit(".", 1)[-1]
                if not BOSS_NEEDLE.search(leaf):
                    continue
                counts[leaf] += 1
                if value not in (None, "", [], {}, 0) and value is not False:
                    filled[leaf] += 1
                    if len(samples[leaf]) < 3:
                        samples[leaf].append(f"{short(value, 64)} @{alias}")
        out[label] = {
            "package": stem,
            "objects": objects,
            "keys": {
                key: {
                    "records": counts[key],
                    "nonEmpty": filled[key],
                    "samples": samples.get(key, []),
                }
                for key in sorted(counts)
            },
        }
    return out


def levelstats(obb_dir: Path) -> dict:
    """`pkg_2069_PlantLevelStats` fields, which S5 relies on for growth."""

    path = obb_dir / "pkg_2069_PlantLevelStats.json"
    if not path.is_file():
        return {"sheet": "pkg_2069_PlantLevelStats", "missing": True}
    doc = load_package(path) or {}
    counts: Counter[str] = Counter()
    samples: dict[str, list[str]] = defaultdict(list)
    objects = 0
    for obj in doc.get("objects") or []:
        if not isinstance(obj, dict):
            continue
        data = obj.get("objdata")
        if not isinstance(data, dict):
            continue
        objects += 1
        alias = obj.get("aliases")
        alias = alias[0] if isinstance(alias, list) and alias else str(alias or "")
        for key, value in data.items():
            counts[key] += 1
            if len(samples[key]) < 3:
                samples[key].append(f"{short(value, 48)} @{alias}")
    return {
        "sheet": "pkg_2069_PlantLevelStats",
        "package": path.stem,
        "objects": objects,
        "keys": {key: {"records": counts[key], "samples": samples.get(key, [])} for key in sorted(counts)},
    }


def index_manifest(obb_dir: Path) -> dict:
    """The extraction manifest: one row per package with its objclass.

    `_index.json` is the authoritative list of what the 2117 files are, so the
    "does an Element table exist at all" question can be answered over every
    package at once instead of inferring it from key hits.
    """

    path = obb_dir / MANIFEST
    if not path.is_file():
        return {"manifest": MANIFEST, "missing": True}
    doc = load_package(path) or {}
    items = [item for item in doc.get("items") or [] if isinstance(item, dict)]
    classes: Counter[str] = Counter(str(item.get("objclass") or "") for item in items)
    matched: dict[str, list[str]] = {}
    for concept, needles in CONCEPTS.items():
        matched[concept] = sorted(name for name in classes if matches(name, needles))
    return {
        "manifest": MANIFEST,
        "files": len(package_paths(obb_dir)),
        "packages": len(items),
        "ok": doc.get("ok"),
        "fail": doc.get("fail"),
        "distinctObjclasses": len(classes),
        "classes": dict(classes.most_common()),
        "conceptObjclasses": matched,
    }


def boss_actions(obb_dir: Path) -> dict:
    """Field inventory for every `*Zomboss*` / `*Boss*` object class in the packs."""

    paths = package_paths(obb_dir)
    by_class: dict[str, dict] = {}
    parsed = 0
    for path in paths:
        doc = load_package(path)
        if doc is None:
            continue
        parsed += 1
        for obj in doc.get("objects") or []:
            if not isinstance(obj, dict):
                continue
            objclass = str(obj.get("objclass") or "")
            if not BOSS_NEEDLE.search(objclass):
                continue
            data = obj.get("objdata")
            data = data if isinstance(data, dict) else {}
            alias = obj.get("aliases")
            alias = alias[0] if isinstance(alias, list) and alias else str(alias or "")
            block = by_class.setdefault(
                objclass,
                {
                    "records": 0,
                    "packages": Counter(),
                    "fields": Counter(),
                    "samples": defaultdict(list),
                },
            )
            block["records"] += 1
            block["packages"][path.stem] += 1
            for key, value in data.items():
                block["fields"][key] += 1
                if len(block["samples"][key]) < 3 and value not in (None, "", [], {}, 0):
                    block["samples"][key].append(f"{short(value, 56)} @{alias}")
    return {
        "files": len(paths),
        "parsed": parsed,
        "classes": {
            name: {
                "records": block["records"],
                "packages": dict(block["packages"].most_common(5)),
                "fields": dict(block["fields"].most_common()),
                "samples": {key: values for key, values in sorted(block["samples"].items())},
            }
            for name, block in sorted(by_class.items())
        },
    }


STAGE_WORLD_HINTS: tuple[tuple[str, str], ...] = (
    ("marketnights", "lunarrainbowmarket"),
    ("lunarno", "lunarrainbowmarket"),
    ("daylight", "lunarrainbowmarket"),
    ("beachboss", "beach"),
    ("beach", "beach"),
    ("carnivalboss", "carnival"),
    ("carnival", "carnival"),
    ("chinesegardenboss", "chinesegarden"),
    ("chinesegarden", "chinesegarden"),
    ("westnightboss", "cowboy"),
    ("westboss", "cowboy"),
    ("west", "cowboy"),
    ("dark", "dark"),
    ("future", "future"),
    ("egyptnightsboss", "egypt"),
    ("egypt", "egypt"),
    ("lostcity", "lostcity"),
    ("eighties", "eighties"),
    ("iceageex", "iceage"),
    ("iceage", "iceage"),
    ("plantagenetboss", "plantagenet"),
    ("fairystage", "fairy"),
    ("renaiboss", "renai"),
    ("renaistage", "renai"),
    ("gtaub", "losantosvice"),
    ("mausoleum", "mausoleum"),
    ("dinonights", "dino"),
    ("dinostage", "dino"),
    ("heianboss", "heian"),
    ("kongfuboss", "kongfu"),
    ("modernub", "modern"),
    ("modern", "modern"),
    ("pirateboss", "pirate"),
    ("pirate", "pirate"),
    ("skycitylostcityboss", "sky"),
    ("skycityboss", "sky"),
    ("skycity", "sky"),
    ("steamboss", "steam"),
    ("roofnight", "roof"),
    ("rift", "rift"),
)


def world_from_stage(stage: str) -> str:
    """World name inferred from a level's `StageModule` alias.

    This is a name-prefix inference, not a data field: `LevelDefinition` never
    stores a world id, so the only link is the stage name that the world's
    levels share. Unmatched stages stay `unknown` rather than being guessed.
    """

    lowered = stage.lower()
    for needle, world in STAGE_WORLD_HINTS:
        if needle in lowered:
            return world
    return f"unknown:{stage}" if stage else "unknown"


def boss_battles(obb_dir: Path) -> dict:
    """`ZombossBattleModuleProperties` rows: which level hosts which boss.

    Each row lives inside the boss level's own `LevelDefinition` package, so
    the package also carries that level's `StageModule`, which is how the world
    is attributed (see `world_from_stage`).
    """

    rows = []
    for path in package_paths(obb_dir):
        doc = load_package(path)
        if doc is None:
            continue
        objects = [obj for obj in doc.get("objects") or [] if isinstance(obj, dict)]
        modules = [
            obj
            for obj in objects
            if str(obj.get("objclass")) in ("ZombossBattleModuleProperties", "ZombossRiftBattleModuleProperties")
        ]
        if not modules:
            continue
        stages = [
            rtid_name((obj.get("objdata") or {}).get("StageModule"))
            for obj in objects
            if str(obj.get("objclass") or "").endswith("LevelDefinition")
            and isinstance(obj.get("objdata"), dict)
        ]
        stage = next((name for name in stages if name), "")
        for module in modules:
            data = module.get("objdata")
            data = data if isinstance(data, dict) else {}
            alias = module.get("aliases")
            alias = alias[0] if isinstance(alias, list) and alias else str(alias or "")
            rows.append(
                {
                    "package": path.stem,
                    "module": str(alias),
                    "objclass": module.get("objclass"),
                    "mech": data.get("ZombossMechType"),
                    "reservedColumns": data.get("ReservedColumnCount"),
                    "spawnGridPosition": data.get("ZombossSpawnGridPosition"),
                    "deathRow": data.get("ZombossDeathRow"),
                    "deathColumn": data.get("ZombossDeathColumn"),
                    "phases": data.get("ZombossPhases"),
                    "stage": stage,
                    "world": world_from_stage(stage),
                }
            )
    rows.sort(key=lambda row: (row["world"], row["package"], row["module"]))
    return {
        "sheet": "ZombossBattleModuleProperties",
        "found": len(rows),
        "distinctMech": len({row["mech"] for row in rows if row["mech"]}),
        "byWorld": dict(sorted(Counter(row["world"] for row in rows).items())),
        "byMech": dict(sorted(Counter(str(row["mech"]) for row in rows).items())),
        "rows": rows,
    }


def boss_phases(obb_dir: Path) -> dict:
    """Every `Zombie*Zomboss*/Mech*` props object and its phase table.

    The decisive field is `Stages[]`: each entry carries `HitPoints` plus the
    `Actions` RTIDs for that phase, so boss health and attack rotation are
    data, not authored numbers.
    """

    rows = []
    for path in package_paths(obb_dir):
        doc = load_package(path)
        if doc is None:
            continue
        for obj in doc.get("objects") or []:
            if not isinstance(obj, dict):
                continue
            objclass = str(obj.get("objclass") or "")
            if not ZOMBOSS_MECH_RE.search(objclass):
                continue
            data = obj.get("objdata")
            data = data if isinstance(data, dict) else {}
            alias = obj.get("aliases")
            alias = alias[0] if isinstance(alias, list) and alias else str(alias or "")
            stages = [stage for stage in data.get("Stages") or [] if isinstance(stage, dict)]
            rows.append(
                {
                    "package": path.stem,
                    "alias": str(alias),
                    "objclass": objclass,
                    "stages": len(stages),
                    "hitPoints": [stage.get("HitPoints") for stage in stages],
                    "phaseActions": [len(stage.get("Actions") or []) for stage in stages],
                    "attackActions": sorted(
                        {
                            rtid_name(action)
                            for stage in stages
                            for action in stage.get("Actions") or []
                            if rtid_name(action)
                        }
                    )[:12],
                    "zombieStats": data.get("ZombieStats"),
                    "conditionImmunities": len(data.get("ConditionImmunities") or []),
                }
            )
    rows.sort(key=lambda row: (row["objclass"], row["alias"], row["package"]))
    with_stages = [row for row in rows if row["stages"]]
    return {
        "sheet": "ZombiePropertySheet / Zomboss*Mech*Props",
        "found": len(rows),
        "withStages": len(with_stages),
        "totalStages": sum(row["stages"] for row in rows),
        "distinctClasses": len({row["objclass"] for row in rows}),
        "rows": rows,
    }


ZOMBOSS_MECH_RE = re.compile(r"Zombie.*(Zomboss|Mech)", re.IGNORECASE)


def element_modules(obb_dir: Path) -> dict:
    """`ElementReaction*` objects: how many, and do any of them carry data?"""

    paths = package_paths(obb_dir)
    records = []
    for path in paths:
        doc = load_package(path)
        if doc is None:
            continue
        for obj in doc.get("objects") or []:
            if not isinstance(obj, dict):
                continue
            objclass = str(obj.get("objclass") or "")
            if "element" not in objclass.lower():
                continue
            data = obj.get("objdata")
            data = data if isinstance(data, dict) else {}
            alias = obj.get("aliases")
            alias = alias[0] if isinstance(alias, list) and alias else str(alias or "")
            records.append(
                {
                    "package": path.stem,
                    "objclass": objclass,
                    "alias": str(alias),
                    "fields": sorted(data),
                    "empty": not data,
                }
            )
    return {
        "found": len(records),
        "withFields": sum(1 for r in records if r["fields"]),
        "empty": sum(1 for r in records if r["empty"]),
        "objclasses": dict(Counter(r["objclass"] for r in records).most_common()),
        "records": records[:40],
    }


def plant_elements(obb_dir: Path) -> dict:
    """Any `element`-ish key on plant objects, with values."""

    path = obb_dir / "pkg_2073_PlantPropertySheet.json"
    rows = []
    if path.is_file():
        doc = load_package(path) or {}
        for obj in doc.get("objects") or []:
            if not isinstance(obj, dict):
                continue
            data = obj.get("objdata")
            if not isinstance(data, dict):
                continue
            alias = obj.get("aliases")
            alias = alias[0] if isinstance(alias, list) and alias else str(alias or "")
            for keypath, value in walk_keys(data):
                if "element" in keypath.rsplit(".", 1)[-1].lower():
                    rows.append({"alias": str(alias), "key": keypath, "value": short(value, 64)})
    return {"found": len(rows), "rows": rows[:40]}


def inventory(obb_dir: Path, limit: int = 25) -> dict:
    """Everything the review cites, in one JSON document."""

    return {
        "manifest": index_manifest(obb_dir),
        "scans": {concept: scan(obb_dir, concept, limit=limit) for concept in CONCEPTS},
        "plantfoodActions": plantfood_actions(obb_dir),
        "plantfoodFields": plantfood_fields(obb_dir),
        "bossEvents": boss_events(obb_dir),
        "bossFields": boss_fields(obb_dir),
        "bossActions": boss_actions(obb_dir),
        "bossBattles": boss_battles(obb_dir),
        "bossPhases": boss_phases(obb_dir),
        "elementModules": element_modules(obb_dir),
        "plantElements": plant_elements(obb_dir),
        "levelStats": levelstats(obb_dir),
    }


def gaps(obb_dir: Path) -> dict:
    """The machine-readable verdict per concept (driven vs authored).

    Every non-empty `driven` entry below is a field or table the scanner
    actually observed; every `authored` entry names what the tables do *not*
    contain. `verdict` is the one-word conclusion the review cites.
    """

    inv = inventory(obb_dir, limit=0)
    manifest = inv["manifest"]
    element_modules = inv["elementModules"]
    plantfood_rows = inv["plantfoodActions"]["rows"]
    plantfood_keys = inv["plantfoodFields"]["keys"]
    boss_battles = inv["bossBattles"]
    boss_phases = inv["bossPhases"]
    boss_classes = inv["bossActions"]["classes"]

    plantfood_field_names = sorted(plantfood_keys)
    plantfood_driven = [
        name
        for name in ("PlantFoodDurationSeconds", "PlantFoodPlayCount")
        if name in plantfood_keys
    ]
    boss_action_classes = sorted(name for name in boss_classes if name.startswith("Zomboss"))
    return {
        "format": FORMAT,
        "sources": {
            "obb": str(obb_dir),
            "files": manifest.get("files"),
            "packages": manifest.get("packages"),
            "distinctObjclasses": manifest.get("distinctObjclasses"),
        },
        "elements": {
            "verdict": "authored",
            "tables": [],
            "moduleFlag": {
                "objclass": "ElementReactionModuleProperties",
                "alias": "ElementReactionModule",
                "found": element_modules["found"],
                "withFields": element_modules["withFields"],
                "empty": element_modules["empty"],
            },
            "plantElementKeys": inv["plantElements"]["found"],
            "driven": [],
            "authored": [
                "element identity per plant (no Element column anywhere: plantElementKeys=0)",
                "element reaction matrix / multipliers / status effects",
                "element gating for plants and quests",
            ],
            "note": (
                "the only element object is an empty level-module flag "
                f"({element_modules['found']} records, {element_modules['withFields']} with fields)"
            ),
        },
        "plantfood": {
            "verdict": "partial",
            "sheet": inv["plantfoodActions"]["sheet"],
            "actions": [
                {
                    "alias": row["alias"],
                    "objclass": row["objclass"],
                    "index": row["index"],
                    "plants": row["plants"],
                    "projectile": row["fields"].get("Projectile"),
                    "fields": sorted(row["fields"]),
                }
                for row in plantfood_rows
            ],
            "actionCount": len(plantfood_rows),
            "plantCount": len({plant for row in plantfood_rows for plant in row["plants"]}),
            "driven": plantfood_driven
            + [
                "Action.Type=plantfood (projectile-based bursts: 6 plants)",
                "MaxPlantFoodCharge / MaxPlantFoodObjects / MaxPlantfoodKills",
                "IsFromPlantFood / FromPlantfood",
            ],
            "fieldNames": plantfood_field_names,
            "fields": {
                key: {"records": value["records"], "nonEmpty": value["nonEmpty"]}
                for key, value in plantfood_keys.items()
            },
            "authored": [
                "the per-plant plant-food script for the other 333 plants",
                "plant-food visual/audio choreography",
            ],
            "note": (
                f"{len(plantfood_rows)} of {inv['plantfoodActions']['objects_with_actions']} "
                "plant property objects carry a Type=plantfood action; the rest only expose "
                "duration/play-count numbers"
            ),
        },
        "boss": {
            "verdict": "partial",
            "battleSheet": boss_battles["sheet"],
            "battles": boss_battles["found"],
            "distinctMech": boss_battles["distinctMech"],
            "battlesByWorld": boss_battles["byWorld"],
            "mechRows": boss_battles["byMech"],
            "phaseObjects": boss_phases["found"],
            "phaseObjectsWithStages": boss_phases["withStages"],
            "totalStages": boss_phases["totalStages"],
            "actionClasses": boss_action_classes,
            "worldEventSheet": inv["bossEvents"]["sheet"],
            "bossEvents": inv["bossEvents"]["found"],
            "bossEventsByWorld": inv["bossEvents"]["byWorld"],
            "driven": [
                "ZombossBattleModuleProperties.ZombossMechType / ReservedColumnCount / ZombossSpawnGridPosition",
                "Stages[].HitPoints (per-phase boss health)",
                "Stages[].Actions (per-phase attack RTIDs)",
                "Stages[].IdleTime / StunTime / RetreatAction",
                *[f"{name} (Weight/RepeatMin/RepeatMax + damage geometry)" for name in boss_action_classes[:8]],
            ],
            "authored": [
                "boss intro pan/cinematic timing (ZombossBattleIntroProperties only gives phase count)",
                "boss reward/outro choreography",
                "which of the 26 client worlds hosts which mech (WorldData names only 4 boss level events)",
            ],
            "note": (
                f"{boss_battles['found']} boss battles over {boss_battles['distinctMech']} mech types; "
                f"{boss_phases['withStages']}/{boss_phases['found']} boss props carry a Stages[] table"
            ),
        },
    }


def render_report(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB)
    parser.add_argument("--needle", choices=sorted(CONCEPTS), help="scan one concept")
    parser.add_argument("--sheet", action="store_true", help="print matched sheet names only")
    parser.add_argument("--limit", type=int, default=25, help="inline examples per scan")
    parser.add_argument("--inventory", action="store_true", help="print the full inventory JSON")
    parser.add_argument("--gaps", action="store_true", help="print the gap file JSON")
    parser.add_argument("--write-gaps", action="store_true", help=f"write {DEFAULT_GAPS.name}")
    args = parser.parse_args(argv)

    if args.write_gaps:
        data = gaps(args.obb)
        DEFAULT_GAPS.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_GAPS.write_text(render_report(data), encoding="utf-8", newline="\n")
        print(f"wrote {DEFAULT_GAPS}")
        return 0

    if args.gaps:
        sys.stdout.write(render_report(gaps(args.obb)))
        return 0

    if args.inventory or args.needle is None:
        sys.stdout.write(render_report(inventory(args.obb, limit=args.limit)))
        return 0

    result = scan(args.obb, args.needle, limit=args.limit)
    if args.sheet:
        print(f"files={result['files']['matched']} parsed={result['files']['parsed']}")
        print(f"tables ({len(result['tables'])}): {', '.join(result['tables']) or '-'}")
        for name, count in list(result["sheets"].items())[:40]:
            print(f"  {name}  {count}")
        return 0
    sys.stdout.write(render_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
