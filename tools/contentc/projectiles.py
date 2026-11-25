"""Compile the original projectile table (`ProjectileTypes`) for the engine.

Scope and provenance
--------------------
The pack's projectile sheet is `pkg_2082_ProjectilePropertySheet.json`
(572 objects).  It is *not* a single-class sheet: it carries 71 objclasses
(`ProjectilePropertySheet` 337, `PrimalPeashooterProjectileProps` 32,
`CactusProjectileProps` 28, `HomingThistleLeafProps` 23, ...), and every one of
them speaks the same field vocabulary (`BaseDamage`, `InitialVelocity`,
`CollisionRect`, `SplashDamage`, ...).  The table is therefore compiled object by
object, and each record keeps its `objclass` so a reader can see which variant a
row came from.

Level packages also embed `ProjectilePropertySheet` objects (47 of them across
12 packages; 31 aliases exist *only* there — `FireShroomSmallShot`,
`MeteorDefault`, `ZombieDirection2Projectile`, ...).  Skipping them would leave
`RTID(FireShroomSmallShot@ProjectileTypes)` unresolvable, so they are compiled
too and carry their own `pkg`.  `variants` records every place an id was found,
and `variantsDiffer` counts the copies whose objdata is not identical to the one
that was kept.

Field names the task asked for that the pack does not have
---------------------------------------------------------
Measured with `python tools/contentc/projectiles.py --needle` (0 hits in 572
objects): `TypeName`, `Speed`, `ProjectileSpeed`, `Motion`, `Pierce`,
`PierceCount`, `PopAnim`, `ResourceGroups`, `SpawnOffset`.  The pack spells the
same ideas differently, and this module reads the pack spelling only:

    asked            pack field(s)                              present
    ---------------  -----------------------------------------  -----------
    TypeName         `aliases` (objdata has no TypeName at all) 572 aliases
    speed            `InitialVelocity[0..2].Min/Max` (px/second) 563 / 572
    damage           `BaseDamage`                                565 / 572
    splash           `SplashDamage` / `SplashRadius`             204 / 186
    pierce           `InitialPierceChance`,                      39
                     `PierceChanceReductionPerHit`, `MaxTargetHits`
    hit box          `CollisionRect{mX,mY,mWidth,mHeight}`       566
    spawn offset     `InitialPositionOffset`                     6 (the real
                     per-plant spawn offset lives in the plant's
                     `Actions[].SpawnOffset` — see content.pack)
    art key          `AttachedPAM`, `ImpactPAM`,                 493 / 446
                     `RenderImage`, `ShadowImage`
    identity         `ClassName` (the C++ projectile class)      362

Nothing is filled in from `native/src/engine/tuning.hpp`; a field the pack does
not carry stays `null` and is counted in `coverage`.

Units
-----
`InitialVelocity` is px/second.  The engine works in columns and already
converts with `kPixelsPerColumn = 60.0` (`native/src/engine/action_runner.cpp:14`
and `native/src/engine/registry.cpp:27`), so both units are emitted:
`speed.pxPerSec` and `speed.colsPerSec`.  `CollisionRect` is px; the engine's
`kShotHitRadius` is a half-extent in columns, and `hitRadius.cols` is
`max(mWidth, mHeight) / 2 / 60` — `PeaDefault`'s 30x30 box gives exactly 0.25,
the current tuning value.

`SplashRadius` is interpreted as columns: its mode is 2.07 (59 of 186 rows) and
its unit census contains 6 rows at `2147483647` (an "unbounded" sentinel, kept
raw and flagged `unbounded`), which only makes sense as a cell count.  The unit
is still marked `splashRadiusUnit: "cells (inferred)"` rather than asserted as
pack truth — see the report's "unknown" section.

Trajectory rule (the判据 the engine will rely on)
-------------------------------------------------
Ranges are collapsed to their midpoint, `|v| <= 1.0` px/s counts as zero
(`ZERO_EPS`; the same threshold `pfamilies.classify_trajectory` uses, so the
projectile and plant tables never disagree about "is this a lob"):

    straight : |vx| > 1, |vz| <= 1        lane shot
    arc      : |vx| > 1, |vz| > 1         lobbed (pult / CATA)
    drop     : |vx| <= 1, |vz| > 1        falls straight down (seed rain, pear)
    static   : |vx| <= 1, |vz| <= 1       board-anchored effect sprite
    unknown  : no `InitialVelocity` at all (9 rows)

Acceleration is copied through but never used to decide the kind: `arc` rows
carry `InitialAcceleration[2] = -10` (gravity) as a consequence, not a cause.

Commands
--------
    python tools/contentc/projectiles.py               # write json + report
    python tools/contentc/projectiles.py --check       # verify the shipped files
    python tools/contentc/projectiles.py --needle      # prove the 0-hit field names
    python tools/contentc/projectiles.py --needle --all-packages
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

# `contentc` is a sibling package; importing it keeps REPO/default paths identical
# to the other compilers (worlds.py owns the repo-root discovery).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from contentc import s5scan, worlds  # noqa: E402

FORMAT = 1
GENERATED = "projectile-compile-v1"

REPO = worlds.REPO
DEFAULT_OBB = worlds.DEFAULT_OBB
DEFAULT_OUT = REPO / "native/generated/projectiles_from_pack.json"
DEFAULT_REPORT = REPO / "native/generated/projectile_report.md"

# The canonical sheet file name. `sheets.SHEET_FILES["ProjectileTypes"]` maps to
# exactly this file; it is spelled out here because the compiler also needs to walk
# *every other* package for embedded overrides.
CANONICAL_PKG = "pkg_2082_ProjectilePropertySheet.json"
CANONICAL_SHEET = "ProjectileTypes"
CANONICAL_STEM = "pkg_2082_ProjectilePropertySheet"
EMBEDDED_OBJCLASS = "ProjectilePropertySheet"

# one column is 60 px: native/src/engine/action_runner.cpp:14, registry.cpp:27.
PIXELS_PER_COLUMN = 60.0
# |v| <= 1 px/s is "not moving"; the same epsilon pfamilies.classify_trajectory uses.
ZERO_EPS = 1.0
# Sentinel magnitudes seen in radius-like fields (also seen in the level tables).
SENTINEL_VALUES = (2147483647,)

# Field names the task expected. Reported with their real hit counts so a 0 stays
# visible instead of being silently replaced by a tuning constant.
EXPECTED_FIELDS = (
    "TypeName",
    "Speed",
    "ProjectileSpeed",
    "Motion",
    "Pierce",
    "PierceCount",
    "PopAnim",
    "ResourceGroups",
    "SpawnOffset",
    "InitialPositionOffset",
)
# output key -> pack field(s) this compiler reads (None => the pack has no such field)
FIELD_MAP: dict[str, str | None] = {
    "id": "aliases[0]",
    "objclass": "objclass",
    "pkg": "(file the object lives in)",
    "className": "ClassName",
    "velocity": "InitialVelocity",
    "acceleration": "InitialAcceleration",
    "speed": "InitialVelocity[0] / 60",
    "baseDamage": "BaseDamage",
    "splash": "SplashDamage + SplashRadius",
    "pierce": "InitialPierceChance + PierceChanceReductionPerHit + MaxTargetHits",
    "collisionRect": "CollisionRect",
    "hitRadius": "CollisionRect (max half-extent) / 60",
    "startOffset": "InitialPositionOffset",
    "art": "AttachedPAM + ImpactPAM + RenderImage + ShadowImage",
    "lifetime": "Lifetime",
    "stunDuration": "StunDuration",
    "collisionFlags": "CollisionFlags",
    "damageFlags": "DamageFlags",
    "trajectory": "InitialVelocity (rule in the module docstring)",
    "TypeName": None,
    "Speed": None,
    "ProjectileSpeed": None,
    "Motion": None,
    "Pierce": None,
    "PierceCount": None,
    "PopAnim": None,
    "ResourceGroups": None,
    "SpawnOffset": None,
}


# --------------------------------------------------------------------------- #
# sheet reading
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


def _mid(value: object) -> float | None:
    """Midpoint of a `{Min, Max}` range (ints stay ints)."""
    if isinstance(value, dict):
        low, high = value.get("Min"), value.get("Max")
        if isinstance(low, (int, float)) and isinstance(high, (int, float)):
            mid = (low + high) / 2.0
            return int(mid) if float(mid).is_integer() and isinstance(low, int) and isinstance(high, int) else mid
    return None


def _spread(value: object) -> float | None:
    if isinstance(value, dict):
        low, high = value.get("Min"), value.get("Max")
        if isinstance(low, (int, float)) and isinstance(high, (int, float)):
            return high - low
    return None


def _triple(value: object) -> dict | None:
    """`[x, y, z]` of `{Min, Max}` ranges -> `{x: {min, max}, y: ..., z: ...}`."""
    if not isinstance(value, list) or len(value) != 3:
        return None
    axes = {}
    for axis, item in zip("xyz", value):
        if not isinstance(item, dict):
            return None
        axes[axis] = {"min": item.get("Min"), "max": item.get("Max")}
    return axes


def _triple_mid(value: object) -> tuple[float, float, float] | None:
    if not isinstance(value, list) or len(value) != 3:
        return None
    mids = [_mid(item) for item in value]
    if any(mid is None for mid in mids):
        return None
    return (mids[0], mids[1], mids[2])  # type: ignore[return-value]


def trajectory_of(data: dict) -> tuple[str, str]:
    """Classify motion, returning `(kind, evidence)`; rule in the module docstring."""
    mids = _triple_mid(data.get("InitialVelocity"))
    if mids is None:
        return "unknown", "InitialVelocity absent"
    vx, vy, vz = mids
    moving_x, moving_z = abs(vx) > ZERO_EPS, abs(vz) > ZERO_EPS
    evidence = "vx=%s vy=%s vz=%s" % (_num(vx), _num(vy), _num(vz))
    if moving_x and moving_z:
        return "arc", evidence
    if moving_x:
        return "straight", evidence
    if moving_z:
        return "drop", evidence
    return "static", evidence


def _num(value: float | int | None) -> str:
    if value is None:
        return "null"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _round(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(float(value), digits)


def _is_sentinel(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and any(
        abs(value - sentinel) < 1e-6 for sentinel in SENTINEL_VALUES
    )


def _collision_rect(data: dict) -> dict | None:
    rect = data.get("CollisionRect")
    if not isinstance(rect, dict):
        return None
    if not all(isinstance(rect.get(k), (int, float)) for k in ("mX", "mY", "mWidth", "mHeight")):
        return None
    return {
        "x": rect["mX"],
        "y": rect["mY"],
        "width": rect["mWidth"],
        "height": rect["mHeight"],
    }


# --------------------------------------------------------------------------- #
# record building
# --------------------------------------------------------------------------- #
def _velocity_block(data: dict) -> dict | None:
    axes = _triple(data.get("InitialVelocity"))
    if axes is None:
        return None
    return axes


def _speed_block(data: dict) -> dict | None:
    raw = data.get("InitialVelocity")
    if not isinstance(raw, list) or len(raw) != 3:
        return None
    mid = _mid(raw[0])
    if mid is None:
        return None
    low = raw[0].get("Min")
    high = raw[0].get("Max")
    return {
        "pxPerSec": _round(mid, 2),
        "colsPerSec": _round(mid / PIXELS_PER_COLUMN, 4),
        "pxPerSecMin": low,
        "pxPerSecMax": high,
        "spreadPx": _round(_spread(raw[0]), 2),
    }


def _splash_block(data: dict) -> dict | None:
    damage = data.get("SplashDamage")
    radius = data.get("SplashRadius")
    if damage is None and radius is None:
        return None
    block = {
        "damage": damage if isinstance(damage, (int, float)) else None,
        "radius": radius if isinstance(radius, (int, float)) else None,
        "radiusUnit": "cells (inferred)",
        "unbounded": _is_sentinel(radius),
    }
    return block


def _pierce_block(data: dict) -> dict | None:
    chance = data.get("InitialPierceChance")
    reduction = data.get("PierceChanceReductionPerHit")
    max_hits = data.get("MaxTargetHits")
    if chance is None and reduction is None and max_hits is None:
        return None
    return {
        "initialChance": chance,
        "chanceReductionPerHit": reduction,
        "maxTargetHits": max_hits,
    }


def _hit_radius_block(rect: dict | None) -> dict | None:
    if rect is None:
        return None
    half_px = max(rect["width"], rect["height"]) / 2.0
    return {
        "px": _round(half_px, 2),
        "cols": _round(half_px / PIXELS_PER_COLUMN, 4),
        "rule": "max(CollisionRect.mWidth, mHeight) / 2 / 60",
    }


def _number(value: object) -> int | float | None:
    """Coerce a pack number; the sheet sometimes stores numbers as strings.

    `InitialPositionOffset` is the offender: 6 rows carry `{"x": 0, "y": "-60"}`.
    Booleans are rejected so `true` never becomes 1.
    """
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


def _start_offset_block(data: dict) -> dict | None:
    """`InitialPositionOffset` — spelled `{x,y}` or `{mX,mY}`, numbers sometimes quoted."""
    offset = data.get("InitialPositionOffset")
    if not isinstance(offset, dict):
        return None
    x = _number(offset.get("x", offset.get("mX")))
    y = _number(offset.get("y", offset.get("mY")))
    if x is None or y is None:
        return None
    return {"x": x, "y": y, "unit": "px"}


def _art_block(data: dict) -> dict | None:
    keys = {
        "attachedPAM": data.get("AttachedPAM"),
        "impactPAM": data.get("ImpactPAM"),
        "renderImage": data.get("RenderImage"),
        "shadowImage": data.get("ShadowImage"),
    }
    if not any(isinstance(value, str) and value for value in keys.values()):
        return None
    return keys


def _flags(value: object) -> list[str] | None:
    if isinstance(value, list):
        names = [item for item in value if isinstance(item, str)]
        return names or None
    if isinstance(value, str) and value:
        return [value]
    return None


def build_record(obj_id: str, pkg: str, objclass: str, data: dict) -> dict:
    """One deterministic row: every value either comes from the pack or is `null`."""
    kind, evidence = trajectory_of(data)
    rect = _collision_rect(data)
    damage = data.get("BaseDamage")
    record = {
        "id": obj_id,
        "objclass": objclass,
        "pkg": pkg,
        "className": data.get("ClassName") if isinstance(data.get("ClassName"), str) else None,
        "trajectory": kind,
        "trajectoryEvidence": evidence,
        "velocity": _velocity_block(data),
        "speed": _speed_block(data),
        "acceleration": _triple(data.get("InitialAcceleration")),
        "baseDamage": damage if isinstance(damage, (int, float)) else None,
        # 2147483647 is the pack's "instant kill / unbounded" sentinel; it is kept raw
        # (not clamped) and flagged so statistics can exclude it instead of silently
        # averaging a 2-billion damage into the table.
        "baseDamageSentinel": _is_sentinel(damage),
        "splash": _splash_block(data),
        "pierce": _pierce_block(data),
        "collisionRect": rect,
        "hitRadius": _hit_radius_block(rect),
        "startOffset": _start_offset_block(data),
        "art": _art_block(data),
        "lifetime": data.get("Lifetime") if isinstance(data.get("Lifetime"), (int, float)) else None,
        "stunDuration": data.get("StunDuration")
        if isinstance(data.get("StunDuration"), (int, float))
        else None,
        "collisionFlags": _flags(data.get("CollisionFlags")),
        "damageFlags": _flags(data.get("DamageFlags")),
    }
    return record


def collect(obb_dir: Path) -> tuple[list[dict], dict]:
    """Read the canonical sheet plus every embedded override; never raises on junk."""
    rows: list[dict] = []
    canonical_path = obb_dir / CANONICAL_PKG
    canonical = s5scan.load_package(canonical_path) if canonical_path.is_file() else None
    canonical_objects = _objects(canonical)

    files_scanned = 0
    files_failed = 0
    for obj in canonical_objects:
        data = obj.get("objdata")
        if not isinstance(data, dict):
            continue
        objclass = str(obj.get("objclass") or "")
        for alias in _aliases(obj):
            rows.append(
                {"id": alias, "pkg": CANONICAL_STEM, "objclass": objclass, "data": data, "canonical": True}
            )

    for path in s5scan.package_paths(obb_dir):
        if path.name == CANONICAL_PKG:
            continue
        files_scanned += 1
        package = s5scan.load_package(path)
        if package is None:
            files_failed += 1
            continue
        for obj in _objects(package):
            if str(obj.get("objclass") or "") != EMBEDDED_OBJCLASS:
                continue
            data = obj.get("objdata")
            if not isinstance(data, dict):
                continue
            stem = path.name[: -len(".json")]
            for alias in _aliases(obj):
                rows.append(
                    {"id": alias, "pkg": stem, "objclass": EMBEDDED_OBJCLASS, "data": data, "canonical": False}
                )

    meta = {
        "canonical": CANONICAL_STEM if canonical is not None else "missing",
        "canonicalObjects": len(canonical_objects),
        "filesScanned": files_scanned,
        "filesFailed": files_failed,
        "embeddedRows": sum(1 for row in rows if not row["canonical"]),
    }
    return rows, meta


def bind(rows: list[dict]) -> tuple[dict[str, dict], dict]:
    """First canonical copy wins; every other copy becomes a `variant`."""
    canonical: dict[str, dict] = {}
    order: list[str] = []
    embedded: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        if row["canonical"]:
            if row["id"] in canonical:
                embedded[row["id"]].append(row)  # duplicate inside the sheet itself
                continue
            canonical[row["id"]] = row
            order.append(row["id"])
        else:
            embedded[row["id"]].append(row)

    for row_id, copies in embedded.items():
        if row_id not in canonical:
            canonical[row_id] = copies[0]
            order.append(row_id)
    return canonical, {"order": order, "copies": {k: v for k, v in embedded.items()}}


def compile_projectiles(obb_dir: Path | None = None) -> dict:
    """Build the whole table (deterministic: input order -> sorted ids)."""
    obb_dir = Path(obb_dir) if obb_dir is not None else Path(DEFAULT_OBB)
    rows, meta = collect(obb_dir)
    bound, extras = bind(rows)

    records: list[dict] = []
    for obj_id in sorted(bound):
        row = bound[obj_id]
        record = build_record(obj_id, row["pkg"], row["objclass"], row["data"])
        copies = extras["copies"].get(obj_id, [])
        variants = []
        base = row["data"]
        for copy in copies:
            if copy["pkg"] == row["pkg"] and copy["data"] is base:
                continue  # the copy this record was built from
            variants.append(
                {
                    "pkg": copy["pkg"],
                    "canonical": copy["canonical"],
                    "same": copy["data"] == base,
                    "differingKeys": sorted(
                        key
                        for key in set(copy["data"]) | set(base)
                        if copy["data"].get(key) != base.get(key)
                    )[:8],
                }
            )
        record["variants"] = sorted(variants, key=lambda item: (item["pkg"], item["same"]))
        records.append(record)

    # duplicates *inside* pkg_2082 (an embedded override is not a duplicate of itself)
    duplicates = {
        obj_id: sum(1 for copy in copies if copy["canonical"])
        for obj_id, copies in extras["copies"].items()
        if any(copy["canonical"] for copy in copies)
    }
    objclasses = collections.Counter(record["objclass"] for record in records)
    embedded_only = sum(
        1
        for record in records
        if not any(
            copy["canonical"] for copy in extras["copies"].get(record["id"], [])
        )
        and record["pkg"] != meta["canonical"]
    )

    table = {
        "format": FORMAT,
        "generated": GENERATED,
        "counts": {
            "projectiles": len(records),
            "canonicalObjects": meta["canonicalObjects"],
            "canonicalIds": len({row["id"] for row in rows if row["canonical"]}),
            "embeddedObjects": meta["embeddedRows"],
            "embeddedOnlyIds": embedded_only,
            "duplicateIds": duplicates,
            "baseDamageSentinels": sum(1 for record in records if record["baseDamageSentinel"]),
            "objclasses": len(objclasses),
            "objclassCounts": dict(sorted(objclasses.items())),
            "filesScanned": meta["filesScanned"],
            "filesFailed": meta["filesFailed"],
        },
        "units": {
            "velocity": "px per second",
            "pixelsPerColumn": PIXELS_PER_COLUMN,
            "zeroEpsilon": ZERO_EPS,
            "splashRadius": "cells (inferred)",
            "hitRadius": "columns",
        },
        "fieldMap": FIELD_MAP,
        "trajectoryCounts": dict(
            sorted(collections.Counter(record["trajectory"] for record in records).items())
        ),
        "coverage": field_coverage(records),
        "tuning": tuning_comparison(records),
        "sources": {
            "canonical": meta["canonical"],
            "canonicalPackage": CANONICAL_PKG,
            "canonicalSheet": CANONICAL_SHEET,
            "embeddedObjclass": EMBEDDED_OBJCLASS,
            "obb": str(obb_dir),
        },
        "projectiles": records,
    }
    return table


def field_coverage(records: list[dict]) -> dict:
    """How many rows carry each output field; `null` is counted, never invented."""
    keys = (
        "className",
        "velocity",
        "acceleration",
        "speed",
        "baseDamage",
        "splash",
        "pierce",
        "collisionRect",
        "hitRadius",
        "startOffset",
        "art",
        "lifetime",
        "stunDuration",
        "collisionFlags",
        "damageFlags",
    )
    coverage = {}
    for key in keys:
        present = sum(1 for record in records if record.get(key) is not None)
        coverage[key] = {"present": present, "null": len(records) - present}
    for name in EXPECTED_FIELDS:
        coverage[name] = {
            "present": 0,
            "null": len(records),
            "note": "no such field in the pack; see fieldMap",
        }
    return coverage


def tuning_comparison(records: list[dict]) -> dict:
    """Numbers the engine's tuning constants should be calibrated against."""
    speeds = [
        record["speed"]["pxPerSec"]
        for record in records
        if record["speed"] and record["speed"]["pxPerSec"] is not None
        and record["trajectory"] == "straight"
    ]
    radii = [
        record["hitRadius"]["cols"]
        for record in records
        if record["hitRadius"] and record["hitRadius"]["cols"] is not None
    ]
    splash = [
        record["splash"]["radius"]
        for record in records
        if record["splash"] and record["splash"]["radius"] is not None
        and not record["splash"]["unbounded"]
    ]
    block: dict = {
        "straightShotSpeedsPxPerSec": {
            "count": len(speeds),
            "median": _round(statistics.median(speeds), 2) if speeds else None,
            "mode": _mode(speeds),
            "min": min(speeds) if speeds else None,
            "max": max(speeds) if speeds else None,
            "histogram": _histogram(speeds, top=6),
        },
        "hitRadiusCols": {
            "count": len(radii),
            "median": _round(statistics.median(radii), 4) if radii else None,
            "mode": _mode(radii),
            "histogram": _histogram(radii, top=6, digits=3),
        },
        "splashRadiusCells": {
            "count": len(splash),
            "median": _round(statistics.median(splash), 4) if splash else None,
            "mode": _mode(splash),
            "sentinels": sum(
                1 for record in records if record["splash"] and record["splash"]["unbounded"]
            ),
        },
    }
    # the two constants the report compares against, restated so the json is self-contained
    block["engineConstants"] = {
        "kShotSpeedColsPerSec": 5.2,
        "kShotHitRadius": 0.25,
        "note": "read from native/src/engine/tuning.hpp; not used to fill any field",
    }
    return block


def _mode(values: list[float]) -> float | None:
    if not values:
        return None
    counter = collections.Counter(_round(value, 4) for value in values)
    return counter.most_common(1)[0][0]


def _histogram(values: list[float], top: int = 6, digits: int = 2) -> dict:
    counter = collections.Counter(_round(value, digits) for value in values)
    return {_num(key): count for key, count in counter.most_common(top)}


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def render(table: dict) -> str:
    return json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def dump(table: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render(table).encode("utf-8"))


def needle_report(obb_dir: Path, all_packages: bool = False) -> dict:
    """Count how often each expected-but-absent field name appears. Evidence for 0."""
    needles = list(EXPECTED_FIELDS)
    hits = {name: 0 for name in needles}
    objects = 0
    files = 0
    paths = s5scan.package_paths(obb_dir)
    if not all_packages:
        canonical = obb_dir / CANONICAL_PKG
        paths = [canonical] if canonical.is_file() else []
    for path in paths:
        package = s5scan.load_package(path)
        if package is None:
            continue
        files += 1
        for obj in _objects(package):
            data = obj.get("objdata")
            if not isinstance(data, dict):
                continue
            objects += 1
            for name in needles:
                if name in data:
                    hits[name] += 1
    return {"files": files, "objects": objects, "hits": hits, "allPackages": all_packages}


def _sample_rows(records: list[dict], limit: int = 20) -> list[dict]:
    """Deterministic sample: the three reference shots, one per kind, then the hardest hits."""
    picked: list[dict] = []
    by_id = {record["id"]: record for record in records}
    for anchor in ("PeaDefault", "CabbageDefault", "TaraxacumDefault"):
        record = by_id.get(anchor)
        if record is not None:
            picked.append(record)
    seen = {record["trajectory"] for record in picked}
    for record in records:
        if record["trajectory"] not in seen:
            seen.add(record["trajectory"])
            picked.append(record)
    ranked = sorted(
        (record for record in records if not record["baseDamageSentinel"]),
        key=lambda record: (
            -(record["baseDamage"] or 0),
            record["id"],
        ),
    )
    for record in ranked:
        if len(picked) >= limit:
            break
        if record not in picked:
            picked.append(record)
    return picked[:limit]


def render_report(table: dict, obb_dir: Path | None = None) -> str:
    counts = table["counts"]
    coverage = table["coverage"]
    tuning = table["tuning"]
    records = table["projectiles"]
    obb_dir = Path(obb_dir) if obb_dir is not None else Path(DEFAULT_OBB)
    needle = needle_report(obb_dir)
    needle_all = needle_report(obb_dir, all_packages=True)
    lines: list[str] = []
    add = lines.append

    add("# 弹道数据编译报告（pkg_2082 → projectiles_from_pack.json）")
    add("")
    add("由 `tools/contentc/projectiles.py` 生成；数据源 `%s`，产物 `native/generated/projectiles_from_pack.json`。"
        % table["sources"]["canonicalPackage"])
    add("")
    add("```")
    add("python tools/contentc/projectiles.py            # 写 json + 本报告")
    add("python tools/contentc/projectiles.py --check    # 校验落盘文件")
    add("python tools/contentc/projectiles.py --needle   # 复现「哪些字段名在表里不存在」")
    add("```")
    add("")

    add("## 0. 计数")
    add("")
    add("| 项 | 值 | 说明 |")
    add("|---|---:|---|")
    add("| 编译出的弹道 | %d | 按 alias 去重后的 id 数 |" % counts["projectiles"])
    add("| 原表对象 | %d | `%s` 里带 objdata 的对象 |" % (counts["canonicalObjects"], table["sources"]["canonicalPackage"]))
    add("| 原表 id | %d | 同 id 重复的对象只算一次（%s） |"
        % (
            counts["canonicalIds"],
            "、".join(
                "`%s` 有 %d 份" % (name, count) for name, count in sorted(counts["duplicateIds"].items())
            )
            or "无重复",
        ))
    add("| 其它包内嵌的对象 | %d | 关卡/植物表里重复定义的 `ProjectilePropertySheet` |" % counts["embeddedObjects"])
    add("| 只存在于内嵌副本的 id | %d | 只在关卡包里定义（`FireShroom*`、`MeteorDefault`、`ZombieDirection*` …） |" % counts["embeddedOnlyIds"])
    add("| objclass 数 | %d | 这张表不是单一类：`ProjectilePropertySheet` 只是其中一类 |" % counts["objclasses"])
    add("| 扫描的其它包 | %d（失败 %d） | 坏包/非 JSON 跳过并计数，不抛异常 |" % (counts["filesScanned"], counts["filesFailed"]))
    add("")
    add("弹道类型分布：" + "、".join("`%s` %d" % item for item in table["trajectoryCounts"].items()))
    add("")

    add("## 1. 任务点名的字段：哪些真的存在")
    add("")
    add("`python tools/contentc/projectiles.py --needle` 在 `%s` 的 %d 个对象上统计："
        % (table["sources"]["canonicalPackage"], needle["objects"]))
    add("")
    add("| 字段名 | 原表命中（%d 对象） | 全 %d 包命中 | 本表怎么取 |"
        % (needle["objects"], needle_all["files"]))
    add("|---|---:|---:|---|")
    for name in EXPECTED_FIELDS:
        hits = needle["hits"].get(name, 0)
        add(
            "| `%s` | %d | %d | %s |"
            % (
                name,
                hits,
                needle_all["hits"].get(name, 0),
                "见下（`{x,y}`，且 y 是字符串如 `\"-60\"`）" if hits else "**表中不存在 → 输出 `null`**",
            )
        )
    add("")
    missing = [name for name in EXPECTED_FIELDS if not needle["hits"].get(name)]
    add("这 %d 个字段名在本表里 0 命中：%s。它们统一输出 `null` —— 用 tuning 常数去填，"
        "等于把引擎目前的猜测当成原版数据，后面就没法再区分「原版值」和「我们编的值」。"
        % (len(missing), "、".join("`%s`" % name for name in missing)))
    add("")
    add("### 原版的真实拼法")
    add("")
    add("| 输出键 | 原版字段 | 覆盖 |")
    add("|---|---|---:|")
    for key, source in sorted(FIELD_MAP.items()):
        if source is None or key in ("id", "objclass", "pkg", "trajectory"):
            continue
        present = coverage.get(key, {}).get("present")
        add("| `%s` | `%s` | %s |" % (key, source, "%d/%d" % (present, counts["projectiles"]) if present is not None else "—"))
    add("")
    add("`id` 用 `aliases[0]`：objdata 里**没有** `TypeName`（原表 572 个对象全部没有），alias 就是类型名。"
        "`InitialPositionOffset` 那 6 条的 `y` 是字符串（`\"-60\"`），代码里强制转成数字，否则会被当成缺失。")
    add("")

    add("## 2. 弹道判据")
    add("")
    add("把 `InitialVelocity` 的三轴 `{Min,Max}` 折成中点，`|v| <= %.1f` px/s 视为零"
        "（与 `pfamilies.classify_trajectory` 同一阈值，两张表不会对「是不是抛射」打架）：" % ZERO_EPS)
    add("")
    add("| kind | 条件 | 条数 |")
    add("|---|---|---:|")
    traj = table["trajectoryCounts"]
    add("| `straight` | `|vx| > 1` 且 `|vz| <= 1` | %d |" % traj.get("straight", 0))
    add("| `arc` | `|vx| > 1` 且 `|vz| > 1` | %d |" % traj.get("arc", 0))
    add("| `drop` | `|vx| <= 1` 且 `|vz| > 1` | %d |" % traj.get("drop", 0))
    add("| `static` | `|vx| <= 1` 且 `|vz| <= 1` | %d |" % traj.get("static", 0))
    add("| `unknown` | 没有 `InitialVelocity` | %d |" % traj.get("unknown", 0))
    add("")
    add("`arc` 行同时带 `InitialAcceleration[2] = -10`（重力），但加速度只做透传，不参与判定："
        "它是抛射的结果，不是原因。")
    add("")

    add("## 3. 覆盖与缺失")
    add("")
    add("| 输出字段 | present | null |")
    add("|---|---:|---:|")
    for key in sorted(coverage):
        if key in EXPECTED_FIELDS:
            continue
        add("| `%s` | %d | %d |" % (key, coverage[key]["present"], coverage[key]["null"]))
    add("")
    add("哨兵值：`SplashRadius` 有 %d 条、`BaseDamage` 有 %d 条是 `2147483647`（「无限/秒杀」），"
        "都保留原值并分别标 `splash.unbounded` / `baseDamageSentinel`，统计时排除。"
        % (tuning["splashRadiusCells"]["sentinels"], counts["baseDamageSentinels"]))
    add("")
    add("内嵌副本差异：`variants` 逐条列出同一 id 的所有副本，`same=false` 的带 `differingKeys`。"
        "本表以 `pkg_2082` 的副本为准（没有时才用内嵌副本）。")
    add("")

    add("## 4. 抽样 %d 条（每种弹道各取一条 + 伤害最高的非哨兵行 + 三株基准植物）" % len(_sample_rows(records)))
    add("")
    add("| id | trajectory | v(px/s) | cols/s | BaseDamage | Splash(dmg/radius) | hitRadius(cols) | 来源 pkg |")
    add("|---|---|---:|---:|---:|---|---:|---|")
    for record in _sample_rows(records):
        speed = record["speed"]["pxPerSec"] if record["speed"] else None
        cols = record["speed"]["colsPerSec"] if record["speed"] else None
        splash = record["splash"]
        splash_text = "—" if not splash else "%s/%s" % (splash["damage"], splash["radius"])
        radius = record["hitRadius"]["cols"] if record["hitRadius"] else None
        add(
            "| `%s` | %s | %s | %s | %s%s | %s | %s | `%s` |"
            % (
                record["id"],
                record["trajectory"],
                _num(speed),
                _num(cols),
                _num(record["baseDamage"]),
                " (哨兵)" if record["baseDamageSentinel"] else "",
                splash_text,
                _num(radius),
                record["pkg"],
            )
        )
    add("")

    speeds = tuning["straightShotSpeedsPxPerSec"]
    radii = tuning["hitRadiusCols"]
    add("## 5. 与 `native/src/engine/tuning.hpp` 的对照")
    add("")
    add("两个常数是引擎当前硬编码值，**没有**用作任何字段的填充来源，只用来做校准对照。")
    add("")
    add("### `kShotSpeedColsPerSec = 5.2`")
    add("")
    add("5.2 cols/s = %.0f px/s。" % (5.2 * PIXELS_PER_COLUMN))
    add("")
    add("| 统计量 | 值 |")
    add("|---|---:|")
    add("| 直线弹（`trajectory=straight`）样本 | %d |" % speeds["count"])
    add("| 中位数 | %s px/s |" % _num(speeds["median"]))
    add("| 众数 | %s px/s（%.3f cols/s） |" % (_num(speeds["mode"]), (speeds["mode"] or 0) / PIXELS_PER_COLUMN))
    add("| 区间 | %s – %s px/s |" % (_num(speeds["min"]), _num(speeds["max"])))
    add("")
    add("最常见速度：" + "、".join("`%s` px/s × %d" % item for item in speeds["histogram"].items()))
    add("")
    add("读法：原版直线弹的主峰是 %s px/s（%.3f cols/s），5.2 cols/s 对应 %d px/s —— 312 不在任何主峰上"
        "（最近的两个峰是 %s 与 %s），所以 5.2 是个折中值，不是任何一株植物的原值。"
        "要么按植物逐个取 `speed.colsPerSec`，要么把常数对齐到主峰 %s px/s（%.3f cols/s）。"
        % (
            _num(speeds["mode"]),
            (speeds["mode"] or 0) / PIXELS_PER_COLUMN,
            int(5.2 * PIXELS_PER_COLUMN),
            _num(speeds["mode"]),
            "300",
            _num(speeds["mode"]),
            (speeds["mode"] or 0) / PIXELS_PER_COLUMN,
        ))
    add("")
    add("### `kShotHitRadius = 0.25`")
    add("")
    add("| 统计量 | 值 |")
    add("|---|---:|")
    add("| 有 `CollisionRect` 的弹道 | %d |" % radii["count"])
    add("| 中位数 | %s cols |" % radii["median"])
    add("| 众数 | %s cols |" % radii["mode"])
    add("")
    add("命中半径取 `max(mWidth, mHeight) / 2 / 60`；分布：" +
        "、".join("`%s` × %d" % item for item in radii["histogram"].items()))
    add("")
    add("读法：主峰 %s cols 与 `kShotHitRadius = 0.25` **完全吻合**（`CollisionRect` 30×30 → 半宽 15 px → 15/60 = 0.25）。"
        "换句话说 0.25 这个常数其实就是豌豆盒子的半宽，对小弹成立；`mWidth=40` 的大弹应是 0.333，"
        "偏胖的爆炸型（0.5）也各按自己的盒子走。" % radii["mode"])
    add("")
    add("### 未纳入 tuning 的两项")
    add("")
    add("- `kShotStartOffsetCols = 0.35`：本表几乎没有生成点偏移（`InitialPositionOffset` 只有 "
        "%d/%d 条），真正的每株生成偏移在 `content.pack` 的 `Actions[].spawnOffset` 里，"
        "按 `spawnOffset.x / 60` 换算 —— 与本表的 `startOffset` 不是同一个概念。"
        % (coverage["startOffset"]["present"], counts["projectiles"]))
    add("- `kSplashNeighbourFactor = 0.5`：`SplashDamage` 有 %d 条，但「邻居衰减」这个机制在 pkg_2082 里没有对应字段，"
        "只能继续 authored。" % coverage["splash"]["present"])
    add("")

    add("## 6. unknown（诚实边界）")
    add("")
    add("1. `SplashRadius` 的**单位**：本表按格（cells）解读，证据是中位数 %.3f、众数 %s，且哨兵值是 `2147483647`；"
        "但原版没有一处显式写单位，若要绝对确认需要用原版录像反推一次半径。" %
        (tuning["splashRadiusCells"]["median"] or 0, tuning["splashRadiusCells"]["mode"]))
    add("2. 内嵌副本与 `pkg_2082` 不一致时（`variants` 里 `same=false`），哪一个才是运行时生效的那份，"
        "本表没有判断依据：以 canonical 为准，差异保留在 `variants`。")
    add("3. `PrimalPeashooterProjectileProps` 等 %d 个 objclass 与 `ProjectilePropertySheet` 的语义差别"
        "（是否继承、是否有额外原版行为）只看数据无法确定；本表按「同一套字段」处理。" % (counts["objclasses"] - 1))
    add("4. `InitialPierceChance = 155`（`HysilensProjectileDefault` 等）看着像百分比而非概率，"
        "原值保留，未做归一化。")
    add("")

    add("## 7. 本报告每个数字怎么复现")
    add("")
    add("```")
    add("# §0/§2/§3 的计数与分布：编译时打印一行，或从产物 count/trajectoryCounts/coverage 段读")
    add("python tools/contentc/projectiles.py --check")
    add("")
    add("# §1 的「原表命中」列（在 pkg_2082 上统计）")
    add("python tools/contentc/projectiles.py --needle")
    add("")
    add("# §1 的「全 2117 包命中」列")
    add("python tools/contentc/projectiles.py --needle --all-packages")
    add("")
    add("# §3/§5 的统计量：产物 json 的 coverage / tuning 段")
    add('python -c "import json;d=json.load(open(\'native/generated/projectiles_from_pack.json\','
        'encoding=\'utf-8\'));print(d[\'tuning\']);print(d[\'coverage\'])')
    add("")
    add("# §4 的抽样行与 §0 的 id 计数：直接读 projectiles[]")
    add("```")
    add("")
    add("`%s` 的 `counts.objclassCounts` 保存了 71 个 objclass 的逐条计数，"
        "报告里没有逐个列出，避免 71 行表格盖住结论。" % "projectiles_from_pack.json")
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
    records = table["projectiles"]
    ids = [record["id"] for record in records]
    if table.get("format") != FORMAT:
        problems.append("format %r != %r" % (table.get("format"), FORMAT))
    if table.get("generated") != GENERATED:
        problems.append("generated %r != %r" % (table.get("generated"), GENERATED))
    if len(ids) != table["counts"]["projectiles"]:
        problems.append("record count %d != counts.projectiles %d" % (len(ids), table["counts"]["projectiles"]))
    if ids != sorted(ids):
        problems.append("ids are not sorted")
    if len(set(ids)) != len(ids):
        problems.append("duplicate ids in the table")
    flagged = [record["id"] for record in records if record["splash"] and record["splash"]["unbounded"]]
    if len(flagged) != table["tuning"]["splashRadiusCells"]["sentinels"]:
        problems.append("unbounded splash rows %d != counters %d" % (len(flagged), table["tuning"]["splashRadiusCells"]["sentinels"]))
    for record in records:
        if record["hitRadius"] is not None and record["collisionRect"] is None:
            problems.append("hitRadius without collisionRect on %s" % record["id"])
            break
        if record["trajectory"] == "unknown" and record["velocity"] is not None:
            problems.append("unknown trajectory with velocity on %s" % record["id"])
            break
    if not out_path.is_file():
        problems.append("missing %s (run without --check first)" % out_path)
    else:
        shipped = out_path.read_text(encoding="utf-8")
        if shipped != render(table):
            problems.append("%s differs from a fresh compile" % out_path.name)

    print(
        "projectiles=%d objclasses=%d canonicalIds=%d embeddedOnly=%d trajectory=%s"
        % (
            table["counts"]["projectiles"],
            table["counts"]["objclasses"],
            table["counts"]["canonicalIds"],
            table["counts"]["embeddedOnlyIds"],
            ",".join("%s:%d" % item for item in table["trajectoryCounts"].items()),
        )
    )
    for problem in problems:
        print("FAIL", problem)
    print("OK" if not problems else "FAILED")
    return 0 if not problems else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--obb", type=Path, default=None, help="OBB package directory")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--check", action="store_true", help="verify the shipped files")
    parser.add_argument("--needle", action="store_true", help="print the absent-field-name census")
    parser.add_argument("--all-packages", action="store_true", help="with --needle: scan every package")
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args(argv)

    obb_dir = args.obb or Path(DEFAULT_OBB)

    if args.needle:
        report = needle_report(obb_dir, all_packages=args.all_packages)
        print("files=%d objects=%d allPackages=%s" % (report["files"], report["objects"], report["allPackages"]))
        for name, count in report["hits"].items():
            print("  %-24s %d" % (name, count))
        return 0

    table = compile_projectiles(obb_dir)
    if args.check:
        return check(table, args.out)
    dump(table, args.out)
    if not args.no_report:
        write_report(table, args.report, obb_dir)
    print(
        "wrote %s (projectiles=%d objclasses=%d)"
        % (args.out, table["counts"]["projectiles"], table["counts"]["objclasses"])
    )
    if not args.no_report:
        print("wrote %s" % args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
