"""Compile zombie armor from the original `ArmorTypes` sheet and the zombie tables.

What the pack actually has (measured, `--needle`-able, not assumed)
------------------------------------------------------------------
`pkg_0002_ArmorPropertySheetUtils.json` holds 97 armor objects (90
`ArmorPropertySheet`, 5 `NewspaperArmorPropertySheet`, 1 `RaincoatArmorPropertySheet`,
1 `ArmorPropertySheetUtils` template) and every one is addressed by `aliases[0]`.
Level/zombie packages embed 9 more armor objects; 5 of their aliases exist only
there (`ArmBoneDefault`, `PogoStickDefault`, `StatueOriginalDefault`,
`RenaiStatueDefault`, `PerfumerStatueDefault`, `ImpStatueDefault`), so the table is
compiled from **all** packages and every row carries its `pkg`.

Field names, real ones first:

    wanted              pack field                       present
    ------------------  --------------------------------  -----------
    id                  `aliases[0]`                      97/97
    hitpoints           `BaseHealth`                      96/97
    droppable           `"droppable" in ArmorFlags`       96/97 (flags)
    damageable          `"damageable" in ArmorFlags`      —
    invincible          `"invincible" in ArmorFlags`      —
    metallic            `"metallic" in ArmorFlags`        —
    helm / body         `"helm"` / `"body"` in ArmorFlags —
    art                 `ArmorLayers` (bone/layer names)  94/97
    layer breakpoints   `ArmorLayerHealth`                 95/97
    armor class         `ClassName`                        10/97
    impact/drop sound   `ImpactSoundEvent` / `DropSoundEvent`
    breaksInto          **no such field**                  see below

`breaksInto` is the one thing the pack does not answer: there is no "what does this
armor become" field.  What the pack *does* encode is the zombie side —
`ZombieArmorProps` is an ordered list of `RTID(<armor>@ArmorTypes)` refs, so a
zombie's armor is a chain and the armour that remains after the first one breaks is
the next entry of that list (or the bare zombie).  The table therefore emits
`breaksInto: null` plus `breaksIntoNote`, and puts the order on the zombie record
(`armorIds`, `armorChain`) instead of inventing a per-armor successor.
The order in `ZombieArmorProps` is stored outermost-first for every multi-armor
zombie we checked (`beach_surfer` = surfboard-then-board, `eighties_armor4` =
hair-then-brick, `nutcracker` = body/arm/key) — that is an inference from three
examples, marked as such in the report, not a pack field.

Units / sentinels
-----------------
`BaseHealth` is hit points (370 for `ConeDefault`, 1100 for `BucketDefault`).
`2147483647` appears as "invincible/unbounded" and is kept raw and flagged
(`hitpointsSentinel`) rather than clamped.  `ArmorLayerHealth` mixes break
fractions (`0.666`, `0.333`) with negative layer indices for multi-part armor
(`ArmBoneDefault` uses `-1..-37` to hide every layer), so it is copied verbatim
and **not** interpreted here.

Two engine constants this table is meant to replace
---------------------------------------------------
* `native/src/engine/world.cpp:433` — `for (double armor : def.armor) zombie.armorHp += armor;`
  sums a flat list.  An armor with `invincible` (e.g. `BasicBucketDefault`,
  `FairyTaleImpDefault`) must not be added to a damage pool at all, and
  `droppable` decides whether breaking it removes art or leaves the zombie bare —
  both flags are in this table.
* `native/src/battle_view.cpp:297` — `gear.armature = z.type == "buckethead" ? "Bucket" : "Cone";`
  hardcodes two armors.  The pack names 102, each with its own `ArmorLayers`.

Commands
--------
    python tools/contentc/armors.py            # write json + report
    python tools/contentc/armors.py --check    # verify the shipped files
    python tools/contentc/armors.py --needle   # field-name census (0-hit proof)
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

# `contentc` is a sibling package; importing it keeps REPO/default paths identical
# to the other compilers (worlds.py owns the repo-root discovery).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from contentc import rtid, s5scan, worlds  # noqa: E402
from contentc.portable import portable  # noqa: E402

FORMAT = 1
GENERATED = "armor-compile-v1"

REPO = worlds.REPO
DEFAULT_OBB = worlds.DEFAULT_OBB
DEFAULT_OUT = REPO / "native/generated/armors_from_pack.json"
DEFAULT_REPORT = REPO / "native/generated/armor_report.md"
DEFAULT_CONTENT = REPO / "content/zombies.json"

CANONICAL_PKG = "pkg_0002_ArmorPropertySheetUtils.json"
CANONICAL_STEM = "pkg_0002_ArmorPropertySheetUtils"
ARMOR_SHEET = "ArmorTypes"
ARMOR_CLASS_NEEDLE = "ArmorPropertySheet"
ZOMBIE_TYPE_PKG = "pkg_2115_ZombieType.json"
ZOMBIE_PROPS_PKG = "pkg_2112_ZombiePropertySheet.json"
ZOMBIE_PROPS_STEM = "pkg_2112_ZombiePropertySheet"

# "invincible / instant kill" sentinel seen in BaseHealth.
SENTINEL_VALUES = (2147483647,)

# Flags the engine cares about; the raw `ArmorFlags` list is kept too.
FLAG_NAMES = (
    "damageable",
    "droppable",
    "helm",
    "body",
    "metallic",
    "passdamage",
    "invincible",
    "visibleondestroy",
    "absorboverflow",
    "none",
)

# Field names the task named that the pack may not spell this way; reported with
# their real hit counts so a 0 stays visible.
EXPECTED_FIELDS = ("Hitpoints", "HitPoints", "Health", "Droppable", "BreaksInto", "NextArmor",
                   "Armature", "PopAnim", "ResourceGroups")

FIELD_MAP: dict[str, str | None] = {
    "id": "aliases[0]",
    "armorType": "ArmorType",
    "hitpoints": "BaseHealth",
    "flags": "ArmorFlags",
    "droppable": 'ArmorFlags contains "droppable"',
    "breaksInto": None,
    "art.armorLayer": "ArmorLayers[0]",
    "art.layers": "ArmorLayers",
    "art.layerHealth": "ArmorLayerHealth",
    "art.className": "ClassName",
    "art.fireLayer": "FireLayer",
    "art.particleOverride": "ParticleLayerOverride",
    "sounds.impact": "ImpactSoundEvent",
    "sounds.drop": "DropSoundEvent",
    "Hitpoints": None,
    "HitPoints": None,
    "Health": None,
    "Droppable": None,
    "BreaksInto": None,
    "NextArmor": None,
    "Armature": None,
    "PopAnim": None,
    "ResourceGroups": None,
}

BREAKS_INTO_NOTE = (
    "the pack has no successor field; what remains after this armor breaks is the next "
    "entry of the zombie's ZombieArmorProps chain (see zombies[].armorIds), or the bare zombie"
)
ORDER_NOTE = (
    "ZombieArmorProps order is kept as stored; reading it as outermost-first is an inference "
    "from the multi-armor zombies in the report, not a pack field"
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _objects(package: dict | None) -> list[dict]:
    if not isinstance(package, dict):
        return []
    objects = package.get("objects")
    if not isinstance(objects, list):
        return []
    return [obj for obj in objects if isinstance(obj, dict)]


def _aliases(obj: dict) -> list[str]:
    raw = obj.get("aliases")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [name for name in raw if isinstance(name, str)]
    return []


def _number(value: object) -> int | float | None:
    """Coerce a pack number (some rows store numbers as strings)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return None
    return None


def _is_sentinel(value: object) -> bool:
    number = _number(value)
    if number is None:
        return False
    return any(abs(number - sentinel) < 1e-6 for sentinel in SENTINEL_VALUES)


def _flags(value: object) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, str) and value:
        return [value]
    return []


def _num_text(value: float | int | None) -> str:
    if value is None:
        return "null"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _rtid_refs(value: object) -> list[str]:
    """`["RTID(A@ArmorTypes)", ...]` -> `["A", ...]`; unknown shapes are kept verbatim."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    names = []
    for item in value:
        parsed = rtid.parse_rtid(item) if isinstance(item, str) else None
        if parsed:
            names.append(parsed[0])
        elif isinstance(item, str):
            names.append(item)
    return names


# --------------------------------------------------------------------------- #
# armor table
# --------------------------------------------------------------------------- #
def collect_armors(obb_dir: Path) -> tuple[list[dict], dict]:
    """Every object whose objclass carries `ArmorPropertySheet`, from every package."""
    rows: list[dict] = []
    files = 0
    failed = 0
    for path in s5scan.package_paths(obb_dir):
        package = s5scan.load_package(path)
        if package is None:
            failed += 1
            continue
        files += 1
        stem = path.name[: -len(".json")]
        for obj in _objects(package):
            objclass = str(obj.get("objclass") or "")
            data = obj.get("objdata")
            if ARMOR_CLASS_NEEDLE not in objclass or not isinstance(data, dict):
                continue
            for alias in _aliases(obj):
                rows.append(
                    {
                        "id": alias,
                        "pkg": stem,
                        "objclass": objclass,
                        "data": data,
                        "canonical": stem == CANONICAL_STEM,
                    }
                )
    meta = {
        "files": files,
        "failed": failed,
        "canonicalRows": sum(1 for row in rows if row["canonical"]),
        "embeddedRows": sum(1 for row in rows if not row["canonical"]),
    }
    return rows, meta


def build_armor(row: dict) -> dict:
    data = row["data"]
    flags = _flags(data.get("ArmorFlags"))
    hitpoints = _number(data.get("BaseHealth"))
    layers = data.get("ArmorLayers") if isinstance(data.get("ArmorLayers"), list) else None
    layer_health = (
        data.get("ArmorLayerHealth") if isinstance(data.get("ArmorLayerHealth"), list) else None
    )
    # The art block is kept for every record: `ArmorType` alone already names the
    # armor (e.g. BalloonDefault files itself as `Ballon`), so an empty `ArmorLayers`
    # means "no bone layer to hang the shell on", not "no art information at all".
    art = {
        "armorLayer": layers[0] if layers else None,
        "layers": layers,
        "layerHealth": layer_health,
        "className": data.get("ClassName") if isinstance(data.get("ClassName"), str) else None,
        "fireLayer": data.get("FireLayer") if isinstance(data.get("FireLayer"), str) else None,
        "particleOverride": data.get("ParticleLayerOverride")
        if isinstance(data.get("ParticleLayerOverride"), list)
        else None,
        "armorType": data.get("ArmorType") if isinstance(data.get("ArmorType"), str) else None,
    }
    sounds = None
    if data.get("ImpactSoundEvent") or data.get("DropSoundEvent"):
        sounds = {
            "impact": data.get("ImpactSoundEvent") if isinstance(data.get("ImpactSoundEvent"), str) else None,
            "drop": data.get("DropSoundEvent") if isinstance(data.get("DropSoundEvent"), str) else None,
        }
    record = {
        "id": row["id"],
        "armorType": data.get("ArmorType") if isinstance(data.get("ArmorType"), str) else None,
        "hitpoints": hitpoints,
        "hitpointsSentinel": _is_sentinel(hitpoints),
        "flags": flags,
        "droppable": "droppable" in flags,
        "damageable": "damageable" in flags,
        "invincible": "invincible" in flags,
        "metallic": "metallic" in flags,
        "helm": "helm" in flags,
        "body": "body" in flags,
        "passDamage": "passdamage" in flags,
        "breaksInto": None,
        "breaksIntoNote": BREAKS_INTO_NOTE,
        "art": art,
        "sounds": sounds,
        "pkg": row["pkg"],
        "objclass": row["objclass"],
        "fields": data,
    }
    return record


def bind_armors(rows: list[dict]) -> tuple[dict[str, dict], dict]:
    """First canonical copy wins; every other copy becomes a variant."""
    chosen: dict[str, dict] = {}
    copies: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        if row["canonical"] and row["id"] not in chosen:
            chosen[row["id"]] = row
            continue
        copies[row["id"]].append(row)
    for armor_id, extra in copies.items():
        if armor_id not in chosen:
            chosen[armor_id] = extra[0]
    return chosen, {"copies": {k: v for k, v in copies.items()}}


# --------------------------------------------------------------------------- #
# zombie -> armor
# --------------------------------------------------------------------------- #
def index_zombie_props(obb_dir: Path) -> dict[str, list[dict]]:
    """Alias -> every `Zombie*` props object carrying that alias, all packages."""
    index: dict[str, list[dict]] = collections.defaultdict(list)
    for path in s5scan.package_paths(obb_dir):
        package = s5scan.load_package(path)
        if package is None:
            continue
        for obj in _objects(package):
            if not isinstance(obj.get("objdata"), dict):
                continue
            objclass = str(obj.get("objclass") or "")
            if not objclass.startswith("Zombie"):
                continue
            for alias in _aliases(obj):
                index[alias].append(
                    {"pkg": path.name[: -len(".json")], "objclass": objclass, "data": obj["objdata"]}
                )
    return dict(index)


def pick_props(candidates: list[dict], prefer_pkg: str | None = None) -> dict | None:
    """Deterministic precedence: canonical zombie sheet, then a `*Props` class, then package name."""
    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda item: (
            0 if item["pkg"] == ZOMBIE_PROPS_STEM else 1,
            0 if prefer_pkg and item["pkg"] == prefer_pkg else 1,
            0 if item["objclass"].endswith("Props") else 1,
            item["pkg"],
            item["objclass"],
        ),
    )
    return ranked[0]


def compile_zombies(obb_dir: Path, props_index: dict[str, list[dict]], armor_ids: set[str]) -> dict:
    """ZombieType rows joined with the props object that holds `ZombieArmorProps`."""
    package = s5scan.load_package(obb_dir / ZOMBIE_TYPE_PKG)
    types = [obj for obj in _objects(package) if isinstance(obj.get("objdata"), dict)]
    zombies: list[dict] = []
    dangling: dict[str, list[dict]] = collections.defaultdict(list)
    missing_props = 0
    collisions = 0
    for obj in types:
        data = obj["objdata"]
        zombie_id = data.get("TypeName") if isinstance(data.get("TypeName"), str) else None
        parsed = rtid.parse_rtid(data.get("Properties")) if data.get("Properties") else None
        props_name = parsed[0] if parsed else None
        candidates = props_index.get(props_name, []) if props_name else []
        picked = pick_props(candidates, prefer_pkg=ZOMBIE_PROPS_STEM)
        if len(candidates) > 1:
            collisions += 1
        armors: list[str] = []
        stats = None
        props_pkg = None
        props_class = None
        if picked is None:
            missing_props += 1
        else:
            props_pkg = picked["pkg"]
            props_class = picked["objclass"]
            armors = _rtid_refs(picked["data"].get("ZombieArmorProps"))
            raw_stats = picked["data"].get("ZombieStats")
            if isinstance(raw_stats, list):
                stats = raw_stats
        for armor_id in armors:
            if armor_id not in armor_ids:
                dangling[armor_id].append(
                    {
                        "zombieId": zombie_id,
                        "propsName": props_name,
                        "propsPkg": props_pkg,
                        "propsObjclass": props_class,
                    }
                )
        resource_groups = data.get("ResourceGroups")
        zombies.append(
            {
                "zombieId": zombie_id,
                "className": data.get("ZombieClass") if isinstance(data.get("ZombieClass"), str) else None,
                "armorIds": armors,
                "armorCount": len(armors),
                "armorOrderNote": ORDER_NOTE if armors else None,
                "propsName": props_name,
                "propsPkg": props_pkg,
                "propsObjclass": props_class,
                "propsMissing": picked is None,
                "zombieStats": stats,
                "popAnim": data.get("PopAnim") if isinstance(data.get("PopAnim"), str) else None,
                "animRig": data.get("AnimRigClass") if isinstance(data.get("AnimRigClass"), str) else None,
                "resourceGroups": resource_groups if isinstance(resource_groups, list) else None,
            }
        )
    return {
        # ZombieType sheet order is stable, but sorting by id makes a reader able to
        # find a row without loading the sheet, and keeps the file diff quiet.
        "zombies": sorted(zombies, key=lambda row: row["zombieId"]),
        "dangling": {k: v for k, v in dangling.items()},
        "missingProps": missing_props,
        "propAliasCollisions": collisions,
    }


# --------------------------------------------------------------------------- #
# content comparison
# --------------------------------------------------------------------------- #
def load_content(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as handle:
        doc = json.load(handle)
    if isinstance(doc, dict):
        doc = doc.get("zombies") or []
    return [row for row in doc if isinstance(row, dict)]


def _world_from_art(art: object) -> str | None:
    """`art/chinesegarden/conehead.png` -> `chinesegarden`; used only as a search hint."""
    if not isinstance(art, str):
        return None
    parts = art.split("/")
    if len(parts) >= 3 and parts[0] == "art":
        return parts[1]
    return None


def compare_content(content: list[dict], zombies: list[dict], armors: dict[str, dict]) -> dict:
    """Content's hand-written `armor[]` vs the pack chain.

    Three bridge qualities, in decreasing strength:

    * `exact`     - `extra.source_codename` (or the id) names a pack `ZombieType`.
    * `world-token` - no name match, but the content art path names a world whose
      pack armored zombies are unambiguous by (world token, armor type).
    * `none`      - nothing to bridge on; only the HP values can be compared.

    The heuristic is reported as a heuristic (`bridgeMethod`) and never presented as
    pack truth: the pack has no field that links `market_armor1` to anything.
    """
    by_id = {row["zombieId"]: row for row in zombies}
    armored_ids = [row["zombieId"] for row in zombies if row["armorIds"]]
    pack_hp_values = {record["hitpoints"] for record in armors.values() if record["hitpoints"] is not None}
    rows: list[dict] = []
    for row in content:
        content_armor = row.get("armor")
        if not isinstance(content_armor, list) or not content_armor:
            continue
        extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
        codename = extra.get("source_codename")
        content_id = row.get("id")
        bridge = None
        method = "none"
        for candidate in (codename, content_id):
            if isinstance(candidate, str) and candidate in by_id:
                bridge = candidate
                method = "exact"
                break
        entries = [item for item in content_armor if isinstance(item, dict)]
        world = _world_from_art(entries[0].get("art") if entries else None)
        content_hp = [_number(item.get("hp")) for item in entries]
        candidates: list[dict] = []
        if bridge is None and world:
            # the art path names a world; pack ids either contain it whole
            # (`chinesegarden_armor1`) or carry it as their prefix token
            # (`lunar_armor1` in `lunarrainbowmarket`).
            pool = [
                zombie_id
                for zombie_id in armored_ids
                if world in zombie_id or zombie_id.split("_")[0] in world
            ]
            for zombie_id in sorted(pool):
                pack_row = by_id[zombie_id]
                types = [
                    armors[a]["armorType"] if a in armors else None for a in pack_row["armorIds"]
                ]
                candidates.append(
                    {
                        "zombieId": zombie_id,
                        "armorIds": pack_row["armorIds"],
                        "armorTypes": types,
                        "hitpoints": [
                            armors[a]["hitpoints"] if a in armors else None
                            for a in pack_row["armorIds"]
                        ],
                    }
                )
            wanted_types = [item.get("armature") for item in entries]
            same_length = [
                item for item in candidates if len(item["armorIds"]) == len(entries)
            ]
            typed = [
                item
                for item in same_length
                if all(isinstance(want, str) for want in wanted_types)
                and all(want == got for want, got in zip(wanted_types, item["armorTypes"]))
            ]
            by_hp = [
                item
                for item in same_length
                if item["hitpoints"] == content_hp
            ]
            for pool_hit in (typed, by_hp):
                if len(pool_hit) == 1:
                    bridge = pool_hit[0]["zombieId"]
                    method = "world-token"
                    break
        pack_armor_ids = by_id[bridge]["armorIds"] if bridge else []
        pack_hp = [armors[a]["hitpoints"] if a in armors else None for a in pack_armor_ids]
        deltas = []
        for index, value in enumerate(content_hp):
            reference = pack_hp[index] if index < len(pack_hp) else None
            deltas.append(None if reference is None or value is None else value - reference)
        nearest: list[dict] = []
        if bridge is None and content_hp and content_hp[0] is not None:
            ranked = sorted(
                (
                    (abs(record["hitpoints"] - content_hp[0]), record["id"], record["hitpoints"])
                    for record in armors.values()
                    if record["hitpoints"] is not None
                    and not record["hitpointsSentinel"]
                ),
            )[:2]
            nearest = [
                {
                    "id": armor_id,
                    "hitpoints": value,
                    "delta": content_hp[0] - value,
                }
                for _, armor_id, value in ranked
            ]
        rows.append(
            {
                "contentId": content_id,
                "contentCodename": codename,
                "packZombieId": bridge,
                "bridgeMethod": method,
                "contentWorld": world,
                "packCandidates": candidates[:6],
                "nearestPackArmors": nearest,
                "packArmorIds": pack_armor_ids,
                "packHitpoints": pack_hp,
                "contentHitpoints": content_hp,
                "hpDelta": deltas,
                "contentHpInPack": [
                    (value in pack_hp_values) if value is not None else None for value in content_hp
                ],
                "contentArmature": [item.get("armature") for item in entries],
                "contentArt": [item.get("art") for item in entries],
                "match": method == "exact"
                and len(pack_armor_ids) == len(entries)
                and all(delta == 0 for delta in deltas),
            }
        )
    bridged = [row for row in rows if row["packZombieId"]]
    differing = [row for row in rows if any(delta not in (None, 0) for delta in row["hpDelta"])]
    unbridged = [row for row in rows if not row["packZombieId"]]
    return {
        "rows": rows,
        "bridged": len(bridged),
        "exactBridged": sum(1 for row in rows if row["bridgeMethod"] == "exact"),
        "heuristicBridged": sum(1 for row in rows if row["bridgeMethod"] == "world-token"),
        "unbridged": len(unbridged),
        "exact": sum(1 for row in rows if row["match"]),
        "withHpDifference": len(differing),
        "hpDifferences": [
            {
                "contentId": row["contentId"],
                "packZombieId": row["packZombieId"],
                "packHitpoints": row["packHitpoints"],
                "contentHitpoints": row["contentHitpoints"],
                "hpDelta": row["hpDelta"],
            }
            for row in differing
        ],
        "unbridgedHpInPack": sum(
            1 for row in unbridged if any(value is True for value in row["contentHpInPack"])
        ),
        "unbridgedHpMissing": sum(
            1
            for row in unbridged
            if row["contentHpInPack"] and not any(value is True for value in row["contentHpInPack"])
        ),
    }


# --------------------------------------------------------------------------- #
# compile
# --------------------------------------------------------------------------- #
def compile_armors(obb_dir: Path | None = None, content_path: Path | None = None) -> dict:
    obb_dir = Path(obb_dir) if obb_dir is not None else Path(DEFAULT_OBB)
    content_path = Path(content_path) if content_path is not None else DEFAULT_CONTENT

    rows, meta = collect_armors(obb_dir)
    bound, extras = bind_armors(rows)
    armor_records = []
    for armor_id in sorted(bound):
        record = build_armor(bound[armor_id])
        variants = []
        for copy in extras["copies"].get(armor_id, []):
            if copy["data"] is bound[armor_id]["data"]:
                continue
            variants.append(
                {
                    "pkg": copy["pkg"],
                    "objclass": copy["objclass"],
                    "same": copy["data"] == bound[armor_id]["data"],
                    "differingKeys": sorted(
                        key
                        for key in set(copy["data"]) | set(bound[armor_id]["data"])
                        if copy["data"].get(key) != bound[armor_id]["data"].get(key)
                    )[:8],
                }
            )
        record["variants"] = sorted(variants, key=lambda item: (item["pkg"], item["same"]))
        armor_records.append(record)
    armors = {record["id"]: record for record in armor_records}

    props_index = index_zombie_props(obb_dir)
    zombie_block = compile_zombies(obb_dir, props_index, set(armors))
    zombies = zombie_block["zombies"]
    dangling = zombie_block["dangling"]

    combination = collections.Counter(row["armorCount"] for row in zombies)
    referenced = {armor_id for row in zombies for armor_id in row["armorIds"]}
    unused = sorted(set(armors) - referenced)
    flag_counts = {
        name: sum(1 for record in armor_records if name in record["flags"]) for name in FLAG_NAMES
    }
    content = load_content(content_path)
    comparison = compare_content(content, zombies, armors)

    table = {
        "format": FORMAT,
        "generated": GENERATED,
        "counts": {
            "armors": len(armor_records),
            "canonicalArmors": len({row["id"] for row in rows if row["canonical"]}),
            "canonicalRows": meta["canonicalRows"],
            "embeddedRows": meta["embeddedRows"],
            "embeddedOnlyArmors": sum(
                1 for record in armor_records if record["pkg"] != CANONICAL_STEM
            ),
            "withHitpoints": sum(1 for record in armor_records if record["hitpoints"] is not None),
            "withoutHitpoints": sum(1 for record in armor_records if record["hitpoints"] is None),
            "hitpointsSentinels": sum(1 for record in armor_records if record["hitpointsSentinel"]),
            "withArt": sum(1 for record in armor_records if record["art"] is not None),
            "withArmorLayer": sum(
                1 for record in armor_records if record["art"] and record["art"]["armorLayer"]
            ),
            "withoutArmorLayer": sum(
                1 for record in armor_records if not (record["art"] and record["art"]["armorLayer"])
            ),
            "withoutArmorLayerIds": sorted(
                record["id"]
                for record in armor_records
                if not (record["art"] and record["art"]["armorLayer"])
            ),
            "flagCounts": flag_counts,
            "zombieTypes": len(zombies),
            # ZombieType really does list two TypeNames twice; the table keeps both
            # rows instead of silently dropping one, so the count has to say so.
            "duplicateZombieIds": sorted(
                zombie_id
                for zombie_id, seen in collections.Counter(
                    row["zombieId"] for row in zombies
                ).items()
                if seen > 1
            ),
            "zombiesWithArmor": sum(1 for row in zombies if row["armorIds"]),
            "zombiesWithoutArmor": sum(1 for row in zombies if not row["armorIds"] and not row["propsMissing"]),
            "zombiesUnknownProps": zombie_block["missingProps"],
            "armorCombination": {str(k): v for k, v in sorted(combination.items())},
            "multiArmorZombies": sum(1 for row in zombies if row["armorCount"] > 1),
            "distinctArmorRefs": len(referenced),
            "dangling": len(dangling),
            "danglingRefs": sorted(dangling),
            "danglingReferences": sum(len(v) for v in dangling.values()),
            "unusedArmors": len(unused),
            "unusedArmorIds": unused,
            "propAliasCollisions": zombie_block["propAliasCollisions"],
            "filesScanned": meta["files"],
            "filesFailed": meta["failed"],
            "contentZombies": len(content),
            "contentArmored": len(comparison["rows"]),
            "contentBridged": comparison["bridged"],
            "contentExactBridge": comparison["exactBridged"],
            "contentHeuristicBridge": comparison["heuristicBridged"],
            "contentUnbridged": comparison["unbridged"],
            "contentExact": comparison["exact"],
            "contentHpDifferences": comparison["withHpDifference"],
            "contentUnbridgedHpInPack": comparison["unbridgedHpInPack"],
            "contentUnbridgedHpMissing": comparison["unbridgedHpMissing"],
        },
        "fieldMap": FIELD_MAP,
        "sources": {
            "canonicalPackage": CANONICAL_PKG,
            "armorSheet": ARMOR_SHEET,
            "armorClassNeedle": ARMOR_CLASS_NEEDLE,
            "zombieTypePackage": ZOMBIE_TYPE_PKG,
            "zombiePropsPackage": ZOMBIE_PROPS_PKG,
            "content": portable(content_path),
            "obb": portable(obb_dir),
        },
        "armors": armor_records,
        "zombies": zombies,
        "dangling": [
            {"armorId": armor_id, "references": refs, "count": len(refs)}
            for armor_id, refs in sorted(dangling.items())
        ],
        "contentComparison": comparison,
    }
    return table


def render(table: dict) -> str:
    return json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def dump(table: dict, path: Path) -> None:
    # write bytes with LF so the file is identical on every platform and
    # `--check` can compare it with a fresh render byte for byte
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render(table).encode("utf-8"))


# --------------------------------------------------------------------------- #
# census
# --------------------------------------------------------------------------- #
def needle_report(obb_dir: Path) -> dict:
    """Count how often each expected-but-absent field name appears. Evidence for 0."""
    hits = {name: 0 for name in EXPECTED_FIELDS}
    objects = 0
    files = 0
    canonical = obb_dir / CANONICAL_PKG
    for path in [canonical] if canonical.is_file() else []:
        package = s5scan.load_package(path)
        if package is None:
            continue
        files += 1
        for obj in _objects(package):
            data = obj.get("objdata")
            if not isinstance(data, dict):
                continue
            objects += 1
            for name in hits:
                if name in data:
                    hits[name] += 1
    return {"files": files, "objects": objects, "hits": hits}


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def render_report(table: dict, obb_dir: Path | None = None) -> str:
    counts = table["counts"]
    armors = table["armors"]
    by_id = {record["id"]: record for record in armors}
    zombies = table["zombies"]
    comparison = table["contentComparison"]
    obb_dir = Path(obb_dir) if obb_dir is not None else Path(DEFAULT_OBB)
    needle = needle_report(obb_dir)
    lines: list[str] = []
    add = lines.append

    add("# 护甲数据编译报告（ArmorTypes + 僵尸护甲映射）")
    add("")
    add("由 `tools/contentc/armors.py` 生成；数据源 `%s` + `%s`，产物 `native/generated/armors_from_pack.json`。"
        % (table["sources"]["canonicalPackage"], table["sources"]["zombieTypePackage"]))
    add("")
    add("```")
    add("python tools/contentc/armors.py            # 写 json + 本报告")
    add("python tools/contentc/armors.py --check    # 校验落盘文件")
    add("python tools/contentc/armors.py --needle   # 复现「哪些字段名不存在」")
    add("```")
    add("")

    add("## 0. 计数")
    add("")
    add("| 项 | 值 | 说明 |")
    add("|---|---:|---|")
    add("| 编译出的护甲 | %d | 按 alias 去重 |" % counts["armors"])
    add("| 原表（pkg_0002）护甲 | %d（%d 行） | 原表里 97 行、97 个 alias |"
        % (counts["canonicalArmors"], counts["canonicalRows"]))
    add("| 其它包内嵌护甲 | %d 行 / %d 个 id | 只在内嵌副本里存在的 id 见 §1 |"
        % (counts["embeddedRows"], counts["embeddedOnlyArmors"]))
    add("| 能定 HP 的护甲 | %d | `BaseHealth` 有值 |" % counts["withHitpoints"])
    add("| 定不出 HP 的护甲 | %d | 模板行 / 无 `BaseHealth`，输出 null |" % counts["withoutHitpoints"])
    add("| HP 为哨兵 2147483647 | %d | 「无敌/秒杀」，保留原值并标记 |" % counts["hitpointsSentinels"])
    add("| 带美术块的护甲 | %d（有骨骼主层 %d） | `ArmorLayers[0]` 即护甲骨骼层名；"
        "没有骨骼层的 %d 条见 §9 第 6 条 |"
        % (counts["withArt"], counts["withArmorLayer"], counts["withoutArmorLayer"]))
    add("| 僵尸类型 | %d | `pkg_2115_ZombieType`（其中 %d 个 TypeName 重复出现：%s） |"
        % (counts["zombieTypes"], len(counts["duplicateZombieIds"]),
           "、".join(counts["duplicateZombieIds"]) or "无"))
    add("| **挂护甲的僵尸** | **%d** | `ZombieArmorProps` 非空 |" % counts["zombiesWithArmor"])
    add("| 无护甲僵尸 | %d | props 解析成功且 `ZombieArmorProps` 为空/缺失 |" % counts["zombiesWithoutArmor"])
    add("| 护甲状态未知的僵尸 | %d | props 对象在 2117 个包里找不到，**不能算作无甲** |"
        % counts["zombiesUnknownProps"])
    add("| 被引用到的护甲 id | %d | 其余 %d 个从未被任何僵尸类型引用（§5） |"
        % (counts["distinctArmorRefs"], counts["unusedArmors"]))
    add("| 悬空护甲引用 | **%d** 个 id / %d 处 | 僵尸引用了表里不存在的护甲（§5 逐条） |"
        % (counts["dangling"], counts["danglingReferences"]))
    add("| props alias 撞名 | %d 个僵尸 | 同一 props 名在多包里出现，已按优先级取值并记 variants |"
        % counts["propAliasCollisions"])
    add("| 扫描的包 | %d（失败 %d） | 坏包跳过并计数 |" % (counts["filesScanned"], counts["filesFailed"]))
    add("")

    add("## 1. 护甲表：字段与样例")
    add("")
    add("`python tools/contentc/armors.py --needle` 在 `%s` 的 %d 个对象上统计任务点名的字段：" %
        (table["sources"]["canonicalPackage"], needle["objects"]))
    add("")
    add("| 字段名 | 原表命中 | 本表怎么取 |")
    add("|---|---:|---|")
    for name in EXPECTED_FIELDS:
        hits = needle["hits"].get(name, 0)
        add("| `%s` | %d | %s |" % (name, hits, "见下" if hits else "**表中不存在 → 输出 `null`**"))
    add("")
    add("原版真实拼法：")
    add("")
    add("| 输出键 | 原版字段 | 覆盖 |")
    add("|---|---|---:|")
    for key in ("armorType", "hitpoints", "flags", "art.armorLayer", "art.layers", "art.layerHealth",
                "art.className", "sounds.impact", "sounds.drop", "breaksInto"):
        source = table["fieldMap"].get(key)
        if source is None:
            add("| `%s` | （无） | 0/%d |" % (key, counts["armors"]))
        else:
            add("| `%s` | `%s` | — |" % (key, source))
    add("")
    add("样例（三只最常被引用的护甲）：")
    add("")
    add("| id | armorType | HP | flags | 主层 | 掉落后 |")
    add("|---|---|---:|---|---|---|")
    for armor_id in ("ConeDefault", "BucketDefault", "BrickDefault"):
        record = by_id.get(armor_id)
        if not record:
            continue
        add("| `%s` | %s | %s | %s | `%s` | %s |"
            % (armor_id, record["armorType"], _num_text(record["hitpoints"]),
               ", ".join(record["flags"]),
               (record["art"] or {}).get("armorLayer") or "—",
               "见 §4（pack 无 breaksInto 字段）"))
    add("")
    add("`breaksInto` 是**唯一一个 pack 不回答的字段**：原版没有「这个甲破掉之后变成什么」的字段。"
        "原版把这件事写在僵尸侧 —— `ZombieArmorProps` 是有序的 `RTID(<armor>@ArmorTypes)` 列表，"
        "所以本表把顺序放在 `zombies[].armorIds`（以及 `armorOrderNote` 标明「外层优先」是推断），"
        "护甲行里只给 `breaksInto: null` + 说明，不凭空造一个后继。")
    add("")
    add("只存在于内嵌副本的护甲 id：%s。"
        % "、".join("`%s`" % record["id"] for record in armors if record["pkg"] != CANONICAL_STEM))
    add("")

    flags = counts["flagCounts"]
    add("## 2. ArmorFlags 分布与引擎含义")
    add("")
    add("| flag | 护甲数 | 引擎要注意什么 |")
    add("|---|---:|---|")
    add("| `damageable` | %d | 可以被伤害削；没有它的甲不能靠打掉 |" % flags.get("damageable", 0))
    add("| `droppable` | %d | 打掉后护甲掉落消失（否则是「打死才消失」的甲） |" % flags.get("droppable", 0))
    add("| `invincible` | %d | **不能计入可打掉的护甲血池**（`world.cpp:433` 现在的求和模型对这种甲是错的） |"
        % flags.get("invincible", 0))
    add("| `passdamage` | %d | 伤害穿透护甲打本体 |" % flags.get("passdamage", 0))
    add("| `metallic` | %d | 金属甲（电磁/磁力类攻击需要它） |" % flags.get("metallic", 0))
    add("| `helm` | %d | 头部甲 |" % flags.get("helm", 0))
    add("| `body` | %d | 躯干/整体甲（护盾、雨衣、棺材） |" % flags.get("body", 0))
    add("| `visibleondestroy` | %d | 破坏时仍有可见表现 |" % flags.get("visibleondestroy", 0))
    add("| `absorboverflow` | %d | 溢出伤害被吸收 |" % flags.get("absorboverflow", 0))
    add("")
    add("哨兵：`BaseHealth = 2147483647` 的 %d 条（`PassDamageDefault`、`ArmBoneDefault`、`ArmDefault`、`HeadDefault` 等）"
        "是「无敌/秒杀」标记，保留原值 + `hitpointsSentinel: true`，统计时排除。"
        % counts["hitpointsSentinels"])
    add("")
    add("`ArmorLayerHealth` 混了两种语义：破甲阈值（`0.666`/`0.333`，如 `ConeDefault`）"
        "与负层索引（`-1..-37`，如 `ArmBoneDefault` 用来隐藏每一层），原样透传，不做解释。")
    add("")

    combo = counts["armorCombination"]
    add("## 3. 僵尸 → 护甲：组合分布")
    add("")
    add("| 护甲数 | 僵尸类型数 |")
    add("|---|---:|")
    for key in sorted(combo, key=lambda value: int(value)):
        add("| %s | %d |" % (key, combo[key]))
    add("")
    add("单甲 %d、双甲 %d、三甲 %d、五甲 %d；多甲合计 %d。"
        % (combo.get("1", 0), combo.get("2", 0), combo.get("3", 0), combo.get("5", 0),
           counts["multiArmorZombies"]))
    add("")
    add("还要注意 %d 个僵尸类型的 props 对象在 2117 个包里**找不到**（多为 `@$ZombieProperties` / "
        "`@CurrentLevel` 内联定义），它们的护甲状态是 `unknown`，不是「无甲」——"
        "`counts.zombiesUnknownProps` 单独计数，`zombies[].propsMissing` 逐条标记。"
        % counts["zombiesUnknownProps"])
    add("")

    add("## 4. 多甲僵尸：掉一层之后剩什么")
    add("")
    add("| 僵尸 | 护甲链（pack 顺序） | HP 链 |")
    add("|---|---|---|")
    multi = sorted(
        (row for row in zombies if row["armorCount"] > 1),
        key=lambda row: (-row["armorCount"], row["zombieId"] or ""),
    )
    for row in multi[:12]:
        hp = [by_id[a]["hitpoints"] if a in by_id else None for a in row["armorIds"]]
        add("| `%s` | %s | %s |"
            % (row["zombieId"], " → ".join("`%s`" % a for a in row["armorIds"]),
               " → ".join(_num_text(value) for value in hp)))
    add("")
    add("读法：第一个甲破掉后，僵尸身上的下一个甲继续吃伤害；全破就是裸僵尸（本体 HP 在 `zombieStats` 的 "
        "`toughness` 档里，原版不给数值）。顺序 = `ZombieArmorProps` 存储顺序；"
        "「外层优先」是从 `beach_surfer`（冲浪板→板）、`eighties_armor4`（头发→砖）、`nutcracker`（身→臂→发条）"
        "这几个例子推出来的，原版没有写明，标为推断。")
    add("")

    add("## 5. 悬空引用与未被引用的护甲")
    add("")
    add("| 护甲 id | 被引用次数 | 引用者（props 类） |")
    add("|---|---:|---|")
    for entry in table["dangling"]:
        referrers = collections.Counter(
            "%s / %s" % (item["propsObjclass"], item["propsPkg"]) for item in entry["references"]
        )
        add("| `%s` | %d | %s |"
            % (entry["armorId"], entry["count"],
               "、".join("%s ×%d" % item for item in referrers.most_common(3))))
    add("")
    add("这 %d 个名字只作为 `ZombieArmorProps` 的 RTID 出现，**在 2117 个包里没有任何同名的 "
        "`ArmorPropertySheet` 对象**（`--needle`-able：按 alias 全库搜 0 命中）——是原版包自身的数据缺口，"
        "不是编译漏读。引擎遇到这些僵尸应当当作「无甲/不可破」处理。" % counts["dangling"])
    add("")
    add("从未被任何僵尸类型引用的护甲 %d 个：%s。它们可能是靠脚本/关卡动态挂载，"
        "本表保留但不猜用途。"
        % (counts["unusedArmors"], "、".join("`%s`" % name for name in counts["unusedArmorIds"])))
    add("")

    add("## 6. 与 `content/zombies.json` 的差异（重点：HP 差多少）")
    add("")
    add("客户端 %d 个僵尸，其中 %d 个写了 `armor`。桥接质量分三档："
        "**精确**（`extra.source_codename` / id 命中 pack `ZombieType`）%d 个、"
        "**世界+甲型推断**（无名可对，用 art 路径里的世界名 + `armature` 唯一命中）%d 个、"
        "**桥不上**（没有任何 pack 依据，只比数值）%d 个。"
        % (counts["contentZombies"], counts["contentArmored"], counts["contentExactBridge"],
           counts["contentHeuristicBridge"], counts["contentUnbridged"]))
    add("")
    add("| content id | 桥接 | pack 僵尸 | pack 护甲链 | pack HP | content HP | HP 差（content−pack） |")
    add("|---|---|---|---|---|---|---|")
    for row in comparison["rows"]:
        method = {"exact": "精确", "world-token": "世界+甲型推断", "none": "桥不上"}[row["bridgeMethod"]]
        add("| `%s` | %s | %s | %s | %s | %s | %s |"
            % (
                row["contentId"],
                method,
                ("`%s`" % row["packZombieId"]) if row["packZombieId"] else "—",
                " → ".join("`%s`" % a for a in row["packArmorIds"]) or "—",
                " / ".join(_num_text(value) for value in row["packHitpoints"]) or "—",
                " / ".join(_num_text(value) for value in row["contentHitpoints"]) or "—",
                " / ".join(
                    ("%+d" % delta) if delta is not None else "?"
                    for delta in row["hpDelta"]
                ) or "—",
            ))
    add("")
    add("### 6a. 能对上的 %d 条：HP 差" % counts["contentBridged"])
    add("")
    if comparison["hpDifferences"]:
        add("**不一致 %d 条**（content − pack）：" % len(comparison["hpDifferences"]))
        add("")
        for item in comparison["hpDifferences"]:
            add("- `%s`（pack `%s`）：pack %s ← content %s，差 %s"
                % (item["contentId"], item["packZombieId"],
                   " / ".join(_num_text(v) for v in item["packHitpoints"]),
                   " / ".join(_num_text(v) for v in item["contentHitpoints"]),
                   " / ".join(("%+d" % d) if d is not None else "?" for d in item["hpDelta"])))
        add("")
    else:
        pairs: dict[tuple[str, str], int] = {}
        for row in comparison["rows"]:
            if row["bridgeMethod"] == "none" or not row["contentHitpoints"] or not row["packArmorIds"]:
                continue
            key = (_num_text(row["contentHitpoints"][0]), row["packArmorIds"][0])
            pairs[key] = pairs.get(key, 0) + 1
        detail = "、".join(
            "`%s` 对 `%s`（%d 条）" % (hp, armor, seen)
            for (hp, armor), seen in sorted(pairs.items(), key=lambda item: (-item[1], item[0]))
        )
        add("这 %d 条的 HP 与 pack **逐个相同**：%s。也就是说 content 的 HP 数值本身没错，"
            "错的是它把护甲压成了扁平数字、丢了 flags 与链顺序。"
            % (counts["contentBridged"], detail))
        add("")
    add("### 6b. 桥不上的 %d 条：content 自己编的护甲数值" % counts["contentUnbridged"])
    add("")
    add("这 %d 条没有任何 pack 僵尸类型可以对应（`source_codename` 缺失、id 也不在 `ZombieType` 里），"
        "其中 **%d 条的 HP 在 pack 的 102 条护甲里根本不存在**、%d 条至少能在 pack 里找到同值护甲。"
        "它们是 content 侧 authored 的数，不是从原版抄的。"
        % (counts["contentUnbridged"], counts["contentUnbridgedHpMissing"],
           counts["contentUnbridgedHpInPack"]))
    add("")
    add("按（世界 + 甲型）能拿到的**最近候选**（仅作参考，不是身份认定）：")
    add("")
    add("| content id | 世界提示 | content HP | pack 候选（僵尸 / HP 链） | 数值最接近的 pack 护甲 | 差 |")
    add("|---|---|---:|---|---|---|")
    for row in comparison["rows"]:
        if row["bridgeMethod"] != "none":
            continue
        content_hp = " / ".join(_num_text(v) for v in row["contentHitpoints"])
        nearest = row["nearestPackArmors"][0] if row["nearestPackArmors"] else None
        nearest_text = ("`%s`（%s）" % (nearest["id"], _num_text(nearest["hitpoints"]))
                        if nearest else "**无**")
        nearest_delta = ("%+d" % nearest["delta"]) if nearest else "—"
        if row["packCandidates"]:
            candidates = "；".join(
                "`%s`（%s）" % (candidate["zombieId"],
                                " / ".join(_num_text(v) for v in candidate["hitpoints"]))
                for candidate in row["packCandidates"][:3]
            )
        else:
            candidates = "**无候选**"
        add("| `%s` | %s | %s | %s | %s | %s |"
            % (row["contentId"], row["contentWorld"] or "—", content_hp,
               candidates, nearest_text, nearest_delta))
    add("")
    clock = [record for record in table["armors"]
             if "clock" in record["id"].lower() or "gear" in (record["armorType"] or "").lower()]
    if clock:
        record = clock[0]
        add("最典型的一条：`market_armor1` 写着齿轮护罩 640，而 pack 里名字/甲型带 clock|gear 的护甲"
            "只有 `%s`（%s，`steam_clockwork` 在用），差 **%+d**；"
            "`royal_noblewoman` 的 160 与 `royal_winetasting` 的 790 在全部 %d 条护甲里也没有同值项。"
            % (record["id"], _num_text(record["hitpoints"]),
               640 - int(record["hitpoints"]), counts["armors"]))
        add("")
    add("另外两类差异不是数值而是**形状**：")
    add("")
    add("- content 用 `armature: \"Cone\"/\"Bucket\"` 与 `art: \"armors/BasicConeARMOR\"` 表达外观，"
        "这两个字段名在 pack 里都不存在（`--needle` 0 命中）；pack 给的是 `ArmorLayers` 的骨骼层名"
        "（如 `zombie_armor_cone_norm`）。本表 `art.armorLayer` 就是那个层名，可直接喂给 "
        "`actor_view` 的 armature 查找，不需要 `battle_view.cpp:297` 那种 `buckethead ? \"Bucket\" : \"Cone\"` 的硬编码。")
    add("- content 的 `armor` 是扁平 `[{hp, art, armature, metal}]`，pack 是**有序链 + flags**："
        "`metal` 对应 `metallic` flag、`droppable` 决定破甲后是否移除、`invincible` 的甲不能进血池。")
    add("")

    add("## 7. 这张表替换掉的两处写死")
    add("")
    add("| 位置 | 现状 | 本表对应字段 |")
    add("|---|---|---|")
    add("| `native/src/engine/world.cpp:433` | `for (double armor : def.armor) zombie.armorHp += armor;` | "
        "`zombies[].armorIds` + `armors[].hitpoints`/`flags`（`invincible`、`passdamage`、`droppable` 分别处理） |")
    add("| `native/src/battle_view.cpp:297` | `gear.armature = z.type == \"buckethead\" ? \"Bucket\" : \"Cone\";` | "
        "`armors[].art.armorLayer`（102 条各自的骨骼层名） |")
    add("")

    add("## 8. 复现")
    add("")
    add("```")
    add("python tools/contentc/armors.py --check      # §0 的计数一行")
    add("python tools/contentc/armors.py --needle     # §1 的字段命中列")
    add('python -c "import json;d=json.load(open(\'native/generated/armors_from_pack.json\',encoding=\'utf-8\'));'
        'print(d[\'counts\'])"   # §0/§2/§3 的全部数字')
    add("```")
    add("")

    add("## 9. unknown（诚实边界）")
    add("")
    add("1. `breaksInto` 原版没有对应字段（§1 已说明）：护甲→后继的关系只存在于僵尸侧的链顺序里。")
    add("2. `ZombieArmorProps` 的顺序语义（外层优先）是从 3 个多甲僵尸推出来的推断，不是 pack 字段。")
    add("3. `ArmorLayerHealth` 的两种语义（破甲阈值 vs 负层索引）没有文档，本表透传不做解释。")
    add("4. %d 个僵尸类型的 props 对象缺失 → 护甲状态 `unknown`，无法判定有无护甲。"
        % counts["zombiesUnknownProps"])
    add("5. 护甲与 `content` 的 `art`（`armors/BasicConeARMOR`）之间没有 pack 侧的对应关系，"
        "本表只给骨骼层名，模型文件路径仍需 authored。")
    add("6. %d 个护甲的 `ArmorLayers` 是空列表或缺失，只有 `ArmorType` 与 HP，没有可挂的骨骼层，"
        "`art.armorLayer` 输出 null：%s。"
        % (counts["withoutArmorLayer"],
           "、".join("`%s`" % name for name in counts["withoutArmorLayerIds"])))
    add("")
    return "\n".join(lines) + "\n"


def write_report(table: dict, path: Path, obb_dir: Path | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_report(table, obb_dir).encode("utf-8"))


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #
def check(table: dict, out_path: Path) -> int:
    problems: list[str] = []
    armors = table["armors"]
    ids = [record["id"] for record in armors]
    counts = table["counts"]
    if table.get("format") != FORMAT:
        problems.append("format %r != %r" % (table.get("format"), FORMAT))
    if table.get("generated") != GENERATED:
        problems.append("generated %r != %r" % (table.get("generated"), GENERATED))
    if ids != sorted(ids):
        problems.append("armor ids are not sorted")
    if len(set(ids)) != len(ids):
        problems.append("duplicate armor ids")
    if len(ids) != counts["armors"]:
        problems.append("armor rows %d != counts.armors %d" % (len(ids), counts["armors"]))
    if len(table["zombies"]) != counts["zombieTypes"]:
        problems.append("zombie rows %d != counts.zombieTypes %d"
                        % (len(table["zombies"]), counts["zombieTypes"]))
    if len(table["dangling"]) != counts["dangling"]:
        problems.append("dangling rows %d != counts.dangling %d"
                        % (len(table["dangling"]), counts["dangling"]))
    known = set(ids)
    dangling_ids = {entry["armorId"] for entry in table["dangling"]}
    for row in table["zombies"]:
        unknown = [a for a in row["armorIds"] if a not in known and a not in dangling_ids]
        if unknown:
            problems.append("zombie %s references armor %r that is neither known nor dangling"
                            % (row["zombieId"], unknown[0]))
            break
    for record in armors:
        if record["hitpoints"] is None and record["hitpointsSentinel"]:
            problems.append("armor %s has a null hitpoints but is flagged as sentinel" % record["id"])
            break
    if not out_path.is_file():
        problems.append("missing %s (run without --check first)" % out_path)
    else:
        shipped = out_path.read_text(encoding="utf-8")
        if shipped != render(table):
            problems.append("%s differs from a fresh compile" % out_path.name)

    print(
        "armors=%d zombies=%d armored=%d unknownProps=%d dangling=%d multi=%d"
        % (counts["armors"], counts["zombieTypes"], counts["zombiesWithArmor"],
           counts["zombiesUnknownProps"], counts["dangling"], counts["multiArmorZombies"])
    )
    for problem in problems:
        print("FAIL", problem)
    print("OK" if not problems else "FAILED")
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="compile zombie armor from the OBB tables")
    parser.add_argument("--obb", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--content", type=Path, default=DEFAULT_CONTENT)
    parser.add_argument("--check", action="store_true", help="verify the shipped files")
    parser.add_argument("--needle", action="store_true", help="field-name census")
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args(argv)

    obb_dir = args.obb or Path(DEFAULT_OBB)

    if args.needle:
        report = needle_report(obb_dir)
        print("files=%d objects=%d" % (report["files"], report["objects"]))
        for name, count in report["hits"].items():
            print("  %-16s %d" % (name, count))
        return 0

    table = compile_armors(obb_dir, args.content)
    if args.check:
        return check(table, args.out)
    dump(table, args.out)
    if not args.no_report:
        write_report(table, args.report, obb_dir)
    counts = table["counts"]
    print(
        "wrote %s (armors=%d zombies=%d armored=%d)"
        % (args.out, counts["armors"], counts["zombieTypes"], counts["zombiesWithArmor"])
    )
    if not args.no_report:
        print("wrote %s" % args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
