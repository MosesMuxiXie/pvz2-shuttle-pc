"""Project the shipped property sheets into the engine's content pack.

The pack is a *projection*: it carries the fields the engine consumes, resolved
through the RTID alias tables. `work/obb_packages/` stays the authoritative
source; anything the projection does not model is still readable there, so no
original value is lost or "corrected" here.

Determinism: records are sorted by id and JSON is written with sorted keys, so
two runs on the same input produce byte-identical output.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .rtid import is_nothing, parse_rtid
from .sheets import SHEET_FILES, Sheets, load_sheets, normalize_sheet

PACK_FORMAT = 1

ACTION_KINDS = {"projectile", "sun", "explode", "special", "plantfood", "manual"}

# Sheets a reference can name that are not part of the static data tables.
EXTERNAL_SHEETS = {"CurrentLevel", "ItemGroups", "EffectObjectTypes", "HeroTypes", "LevelModules"}

PLANT_PROP_KEYS = (
    "Cost",
    "BeghouledCost",
    "Hitpoints",
    "PacketCooldown",
    "StartingCooldown",
    "PlantGridType",
    "Height",
    "PlantFoodDurationSeconds",
    "PlantFoodPlayCount",
    "Actions",
)

ZOMBIE_PROP_KEYS = (
    "Hitpoints",
    "Speed",
    "SpeedVariance",
    "EatDPS",
    "Weight",
    "WavePointCost",
    "Cost",
    "HitRect",
    "AttackRect",
    "ArtCenter",
    "ShadowOffset",
    "GridExtents",
    "Actions",
    "ZombieArmorProps",
)


def _clean(value: Any, stats: Counter) -> Any:
    """Drop `#`-prefixed designer comments, recursively, and count them."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key.startswith("#"):
                stats["commentKeys"] += 1
                continue
            out[key] = _clean(item, stats)
        return out
    if isinstance(value, list):
        return [_clean(item, stats) for item in value]
    return value


def _number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _point(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    x, y = _number(value.get("x")), _number(value.get("y"))
    if x is None and y is None:
        return None
    return {"x": x, "y": y}


def _rect(value: Any) -> dict | None:
    if not isinstance(value, dict):
        return None
    out = {
        "x": _number(value.get("mX")),
        "y": _number(value.get("mY")),
        "width": _number(value.get("mWidth")),
        "height": _number(value.get("mHeight")),
    }
    if all(item is None for item in out.values()):
        return None
    return out


def _rtid(value: Any) -> dict | None:
    ref = parse_rtid(value) if isinstance(value, str) else None
    if ref is None:
        return None
    if is_nothing(*ref):
        return {"name": ref[0], "sheet": None, "nothing": True}
    return {"name": ref[0], "sheet": normalize_sheet(ref[1])}


def _actions(raw: Any, stats: Counter) -> list[dict]:
    out: list[dict] = []
    for action in raw or []:
        if not isinstance(action, dict):
            stats["skippedActions"] += 1
            continue
        kind = str(action.get("Type") or "").lower()
        if kind not in ACTION_KINDS:
            stats["unknownActionKind:" + (kind or "<none>")] += 1
        stats["actions:" + (kind or "<none>")] += 1
        record: dict[str, Any] = {"kind": kind or "unknown"}
        if kind not in ACTION_KINDS:
            record["rawType"] = action.get("Type")
        projectile = _rtid(action.get("Projectile"))
        if projectile is not None:
            record["projectile"] = projectile
        trigger = action.get("TriggerType")
        if isinstance(trigger, str) and trigger and trigger != "none":
            record["trigger"] = trigger
        explode = action.get("ExplodeType")
        if isinstance(explode, str) and explode and explode != "none":
            record["explode"] = explode
        for key, field in (
            ("Damage", "damage"),
            ("SplashDamage", "splashDamage"),
            ("CooldownTimeMin", "cooldownMin"),
            ("CooldownTimeMax", "cooldownMax"),
            ("InitialMinCooldownTime", "initialMin"),
            ("InitialMaxCooldownTime", "initialMax"),
            ("ExplodeRadius", "explodeRadius"),
            ("ChillDuration", "chillDuration"),
            ("FreezeDuration", "freezeDuration"),
            ("StunDuration", "stunDuration"),
            ("PushbackAmount", "pushback"),
            ("NeedNumOfEatingToUse", "needEating"),
        ):
            number = _number(action.get(key))
            if number is not None:
                record[field] = number
        for key, field in (
            ("Burns", "burns"),
            ("DieAfterExplode", "dieAfterExplode"),
            ("SecondaryAction", "secondary"),
        ):
            if isinstance(action.get(key), bool):
                record[field] = action[key]
        spawn = _point(action.get("SpawnOffset"))
        if spawn is not None:
            record["spawnOffset"] = spawn
        rect = _rect(action.get("RectTriggerRange"))
        if rect is not None:
            record["triggerRect"] = rect
        sound = action.get("ProjectileLaunchSound")
        if isinstance(sound, str) and sound:
            record["launchSound"] = sound
        out.append(record)
    return out


def _props_of(
    sheets: Sheets, ref: dict | None, stats: Counter, dangling: list, who: str
) -> tuple[dict | None, str]:
    """Resolve a Properties RTID to its `objdata`, reporting where it came from.

    Returns `(props, source)` with source one of `static` (resolved in a shipped
    sheet), `external` (the level supplies it, e.g. `CurrentLevel`) or `missing`
    (the shipped data dangles; the original game tolerates it).
    """
    if ref is None or ref.get("nothing"):
        return None, "none"
    entry = sheets.resolve(ref["name"], ref["sheet"])
    if entry is not None:
        return entry.get("objdata") or {}, "static"
    sheet = ref["sheet"]
    if sheet and sheet in EXTERNAL_SHEETS:
        stats["externalRefs"] += 1
        stats["externalRefsBySheet:" + sheet] += 1
        return None, "external"
    stats["danglingRefs"] += 1
    dangling.append(
        {
            "type": who,
            "ref": f"{ref['name']}@{sheet}" if sheet else ref["name"],
            "sheet": sheet,
        }
    )
    return None, "missing"


def _ints(record: dict, source: dict, pairs: tuple[tuple[str, str], ...]) -> None:
    for key, field in pairs:
        number = _number(source.get(key))
        if number is not None:
            record[field] = number


def _strings(record: dict, source: dict, pairs: tuple[tuple[str, str], ...]) -> None:
    for key, field in pairs:
        value = source.get(key)
        if isinstance(value, str) and value:
            record[field] = value


def build_plant(entry: dict, sheets: Sheets, ctx: dict) -> dict:
    stats: Counter = ctx["stats"]
    data = entry["objdata"]
    name = data.get("TypeName") or (entry["aliases"] or [""])[0]
    ref = _rtid(data.get("Properties"))
    props, source = _props_of(sheets, ref, stats, ctx["dangling"], name)
    record: dict[str, Any] = {
        "id": name,
        "framework": data.get("PlantFramework"),
        "properties": ref,
        "propsSource": source,
        "popAnim": data.get("PopAnim"),
        "animRig": data.get("AnimRigClass"),
        "homeWorld": data.get("HomeWorld"),
        "integerId": _number(data.get("IntegerID")),
        "families": data.get("Families") or [],
        "sunProducer": bool(data.get("SunProducer")),
        "almanacBackdrop": data.get("AlmanacBackdropName"),
        "resourceGroups": data.get("shatoResourceGroups") or [],
    }
    if props is None:
        if source == "missing":
            record["propsMissing"] = True
        record["actions"] = []
        return record
    copy = {key: props[key] for key in PLANT_PROP_KEYS if key in props}
    _ints(
        record,
        copy,
        (
            ("Cost", "cost"),
            ("BeghouledCost", "beghouledCost"),
            ("Hitpoints", "hitpoints"),
            ("PacketCooldown", "packetCooldown"),
            ("StartingCooldown", "startingCooldown"),
            ("PlantFoodDurationSeconds", "plantFoodDuration"),
            ("PlantFoodPlayCount", "plantFoodPlayCount"),
        ),
    )
    _strings(record, copy, (("PlantGridType", "gridType"), ("Height", "height")))
    record["actions"] = _actions(copy.get("Actions"), stats)
    return record


def build_zombie(entry: dict, sheets: Sheets, ctx: dict) -> dict:
    stats: Counter = ctx["stats"]
    data = entry["objdata"]
    name = data.get("TypeName") or (entry["aliases"] or [""])[0]
    ref = _rtid(data.get("Properties"))
    props, source = _props_of(sheets, ref, stats, ctx["dangling"], name)
    record: dict[str, Any] = {
        "id": name,
        "class": data.get("ZombieClass"),
        "properties": ref,
        "propsSource": source,
        "popAnim": data.get("PopAnim"),
        "animRig": data.get("AnimRigClass"),
        "homeWorld": data.get("HomeWorld"),
        "integerId": _number(data.get("IntegerID")),
        "isBasic": bool(data.get("IsBasicZombie")),
        "resourceGroups": data.get("ResourceGroups") or [],
    }
    if props is None:
        if source == "missing":
            record["propsMissing"] = True
        record["actions"] = []
        return record
    copy = {key: props[key] for key in ZOMBIE_PROP_KEYS if key in props}
    _ints(
        record,
        copy,
        (
            ("Hitpoints", "hitpoints"),
            ("Speed", "speed"),
            ("SpeedVariance", "speedVariance"),
            ("EatDPS", "eatDps"),
            ("Weight", "weight"),
            ("WavePointCost", "wavePointCost"),
            ("Cost", "cost"),
        ),
    )
    for key, field in (("HitRect", "hitRect"), ("AttackRect", "attackRect")):
        rect = _rect(copy.get(key))
        if rect is not None:
            record[field] = rect
    art = {key: copy[key] for key in ("ArtCenter", "ShadowOffset", "GridExtents") if key in copy}
    art = _clean(art, stats)
    if art:
        record["art"] = art
    raw_actions = copy.get("Actions")
    if isinstance(raw_actions, list) and raw_actions and all(isinstance(item, str) for item in raw_actions):
        # Zombie "Actions" are RTID references to behaviour scripts, not inline actions.
        refs = []
        for text in raw_actions:
            ref = parse_rtid(text)
            if ref is None:
                continue
            resolved = sheets.resolve(ref[0], normalize_sheet(ref[1])) is not None
            stats["zombieActionRefs"] += 1
            if not resolved:
                stats["missingActionRefs"] += 1
            refs.append(
                {"name": ref[0], "sheet": normalize_sheet(ref[1]), "resolved": resolved}
            )
        record["actionRefs"] = refs
        record["actions"] = []
    else:
        record["actions"] = _actions(raw_actions, stats)
    return record


def compute_overlap(pack: dict, content_dir: Path) -> dict:
    """Compare the pack's ids with the ids the Python-era content files use.

    The two vocabularies are not identical: the shipped types are named after
    their art/behaviour (e.g. `kongfu_monk_bucket`), while `content/*.json` uses
    short gameplay ids (`buckethead`). This report is the mapping worklist for
    the behaviour batches, not an error list.
    """

    def ids_of(name: str) -> set[str]:
        path = content_dir / name
        if not path.is_file():
            return set()
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw = raw.get("items") or raw.get("plants") or raw.get("zombies") or []
        return {item["id"] for item in raw if isinstance(item, dict) and "id" in item}

    def report(pack_ids: set[str], content_ids: set[str]) -> dict:
        return {
            "pack": len(pack_ids),
            "content": len(content_ids),
            "shared": len(pack_ids & content_ids),
            "packOnly": len(pack_ids - content_ids),
            "contentOnly": len(content_ids - pack_ids),
            "contentOnlyIds": sorted(content_ids - pack_ids),
        }

    return {
        "plants": report({item["id"] for item in pack["plants"]}, ids_of("plants.json")),
        "zombies": report({item["id"] for item in pack["zombies"]}, ids_of("zombies.json")),
    }


def _source_hashes(obb_dir: Path) -> dict:
    out = {}
    for sheet, filename in sorted(SHEET_FILES.items()):
        path = obb_dir / filename
        if not path.is_file():
            continue
        out[sheet] = {"file": filename, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return out


def _duplicate_ids(rows: list[dict]) -> list[str]:
    """Ids that appear more than once. Kept, not collapsed: the game tells some
    of them apart by class (two `heavy_shield` entries share one IntegerID)."""
    seen: Counter = Counter(row["id"] for row in rows)
    return sorted(name for name, count in seen.items() if count > 1)


def build_pack(obb_dir: Path, generated: str | None = None) -> dict:
    sheets = load_sheets(obb_dir)
    ctx: dict = {"stats": Counter(), "dangling": []}
    stats: Counter = ctx["stats"]
    plants = [build_plant(entry, sheets, ctx) for entry in sheets.get("PlantTypes").objects]
    zombies = [build_zombie(entry, sheets, ctx) for entry in sheets.get("ZombieTypes").objects]
    plants.sort(key=lambda item: item["id"])
    zombies.sort(key=lambda item: item["id"])
    actions_by_kind = {
        key.split(":", 1)[1]: count
        for key, count in sorted(stats.items())
        if key.startswith("actions:")
    }
    unknown_kinds = {
        key.split(":", 1)[1]: count
        for key, count in sorted(stats.items())
        if key.startswith("unknownActionKind:")
    }
    return {
        "format": PACK_FORMAT,
        "generated": generated or _dt.date.today().isoformat(),
        "sources": _source_hashes(obb_dir),
        "counts": {
            "plants": len(plants),
            "zombies": len(zombies),
            "plantActions": sum(len(item["actions"]) for item in plants),
            "zombieActions": sum(len(item["actions"]) for item in zombies),
            "zombieActionRefs": stats["zombieActionRefs"],
            "missingActionRefs": stats["missingActionRefs"],
            "plantsMissingProps": sum(1 for item in plants if item.get("propsMissing")),
            "zombiesMissingProps": sum(1 for item in zombies if item.get("propsMissing")),
            "danglingRefs": stats["danglingRefs"],
            "externalRefs": stats["externalRefs"],
            "commentsStripped": stats["commentKeys"],
            "duplicatePlantIds": len(_duplicate_ids(plants)),
            "duplicateZombieIds": len(_duplicate_ids(zombies)),
        },
        "actionsByKind": actions_by_kind,
        "unknownActionKinds": unknown_kinds,
        "duplicateIds": {"plants": _duplicate_ids(plants), "zombies": _duplicate_ids(zombies)},
        "dangling": sorted(ctx["dangling"], key=lambda item: (item["type"], item["ref"])),
        "externalRefsBySheet": {
            key.split(":", 1)[1]: count
            for key, count in sorted(stats.items())
            if key.startswith("externalRefsBySheet:")
        },
        "plants": plants,
        "zombies": zombies,
    }
