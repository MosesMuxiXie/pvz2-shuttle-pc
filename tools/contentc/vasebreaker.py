"""Compile the original VaseBreaker (砸罐子) content into ``native/generated/vasebreaker.json``.

Read-only compiler: it reads the shipped OBB package dump (460.9) plus the client
level list, and writes one JSON table keyed by *client* level id.  Nothing is
inferred silently -- anything the original data does not carry is reported in
``unknowns`` instead of being filled with a made-up 0/false.

Data sources (all verified by probe against ``work/obb_packages``):

* ``content/levels/*.json`` -> which levels are VaseBreaker (``extra.vasebreaker``)
  and which package holds each of them (``extra.package``).  Note: this flag lives
  **only** in ``content/levels/*.json``; ``native/generated/level_mechanics.json``
  has no ``extra`` block at all.
* ``pkg_####_LevelDefinition.json`` -> the ``LevelDefinition`` object
  (``StageModule``, ``Name``, ``LevelNumber``, ``IsVasebreaker``, ``StartingSun``)
  plus whatever modules the level embeds.
* ``VaseBreakerPresetProperties`` (alias ``VaseBreakerProps``) -> the actual vase
  content: ``Vases[]`` entries discriminated by ``ZombieTypeName`` /
  ``PlantTypeName`` / ``CollectableTypeName``, each with a ``Count``; and the
  placement envelope ``MinColumnIndex`` / ``MaxColumnIndex`` /
  ``GridSquareExcludelist`` / ``GridSquareBlacklist``.

What the original data does **not** contain (stated, not guessed):

* No per-vase ``row``/``col``.  Vases only carry a type and a count; the game places
  them randomly inside ``MinColumnIndex..MaxColumnIndex`` minus the exclusion grid.
* No per-vase sun amount.  Collectable vases name a collectable type (in every one of
  the 47 levels that is ``plantfood``); the sun value lives in the collectable sheet,
  not in the vase entry.
* No ``TimeLimit`` on any VaseBreaker level (library-wide that field only exists on
  ``JoustGameModuleProperties`` / ``StarChallengeLevelTimerProperties``).
* ``StartingSun`` exists on only 4 of the 47 levels; the other 43 have no such field.

The output is deterministic: fixed ``generated`` date, sorted keys, LF newlines.
``--check`` regenerates in memory and compares byte-for-byte with the file on disk
so a stale artefact fails loudly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portable import portable  # noqa: E402
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEVELS = ROOT / "content" / "levels"
DEFAULT_OBB = Path(
    os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages")
)
DEFAULT_OUT = ROOT / "native" / "generated" / "vasebreaker.json"

FORMAT = 1
GENERATED = "2026-11-25"

LEVEL_CLS = "LevelDefinition"
PRESET_CLS = "VaseBreakerPresetProperties"
SEEDBANK_CLS = "SeedBankProperties"
CONVEYOR_CLS = "ConveyorSeedBankProperties"
ENDLESS_CLS = "VaseBreakerEndlessProperties"
LASTSTAND_CLS = "LastStandMinigameProperties"
TIDE_CLS = "TideProperties"

VASE_FLAG = "vasebreaker"
TYPE_ZOMBIE = "zombie"
TYPE_PLANT = "plant"
TYPE_COLLECTABLE = "collectable"

UNKNOWN_PLACEMENT = (
    "vasePlacement: 原版 Vases[] 只有类型与 Count，没有逐罐 row/col；"
    "落位由 MinColumnIndex..MaxColumnIndex 减去 GridSquareExcludelist/Blacklist 后随机决定"
)
UNKNOWN_SUN = (
    "sunAmount: 原版 Vases[] 的收集物罐只给类型名（本作全部是 plantfood），没有阳光数量字段"
)
UNKNOWN_TIMELIMIT = (
    "timeLimit: 原版 LevelDefinition 无 TimeLimit 字段（全库仅 JoustGameModuleProperties / "
    "StarChallengeLevelTimerProperties 带该字段），砸罐子关卡不计时"
)
UNKNOWN_INITIAL_SUN = "initialSun: 该关 LevelDefinition 没有 StartingSun 字段"
UNKNOWN_SEEDBANK = "seedBank: 该关包内没有 SeedBank / ConveyorBelt 模块"
UNKNOWN_PRESET = (
    "preset: 该关包内没有 VaseBreakerPresetProperties，藤罐内容无法从原版数据取得"
)
UNKNOWN_ENDLESS = (
    "endless: VaseBreakerEndlessProperties.Stages 是无尽模式的分阶段配方，"
    "不是本关固定罐表；已原样收录在 endless 字段，未并入 vases"
)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def iter_objects(doc: Dict[str, Any]) -> Iterable[Tuple[str, List[str], Dict[str, Any]]]:
    """Yield (objclass, aliases, objdata) for every object that carries objdata."""
    for obj in doc.get("objects") or []:
        data = obj.get("objdata")
        if not isinstance(data, dict):
            continue
        aliases = obj.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        yield obj.get("objclass") or "", [str(a) for a in aliases], data


def rtid_name(value: Any) -> Optional[str]:
    """``"RTID(BeachStage@LevelModules)"`` -> ``"BeachStage"``."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.startswith("RTID(") and text.endswith(")"):
        text = text[5:-1]
    name = text.split("@", 1)[0].strip()
    return name or None


def level_ids(levels_dir: Path) -> Dict[str, str]:
    """Client level id -> package stem, for every level flagged ``extra.vasebreaker``."""
    out: Dict[str, str] = {}
    for path in sorted(levels_dir.glob("*.json")):
        doc = load_json(path)
        extra = doc.get("extra") or {}
        if not extra.get(VASE_FLAG):
            continue
        level_id = doc.get("id") or path.stem
        package = extra.get("package")
        out[str(level_id)] = str(package) if package else ""
    return out


def package_index(obb_dir: Path) -> Dict[str, Path]:
    """``pkg_0290`` -> path of ``pkg_0290_LevelDefinition.json``."""
    index: Dict[str, Path] = {}
    for path in sorted(obb_dir.glob("pkg_*.json")):
        stem = path.name.split("_", 2)
        if len(stem) < 2:
            continue
        index[f"{stem[0]}_{stem[1]}"] = path
    return index


def _ints(entries: Any) -> List[List[int]]:
    out: List[List[int]] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        out.append([entry.get("mX"), entry.get("mY")])
    return out


def _num(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def vase_entries(preset: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Counter]:
    """Normalise ``Vases[]`` into typed rows; every row keeps the schema slots."""
    rows: List[Dict[str, Any]] = []
    tally: Counter = Counter()
    for entry in preset.get("Vases") or []:
        if not isinstance(entry, dict):
            continue
        count = _num(entry.get("Count")) or 0
        row = {
            "count": count,
            "type": None,
            "zombieId": None,
            "plantId": None,
            "collectableType": None,
            # slots the client schema asks for, absent in the original data
            "row": None,
            "col": None,
            "sunAmount": None,
        }
        if entry.get("ZombieTypeName"):
            row["type"] = TYPE_ZOMBIE
            row["zombieId"] = entry["ZombieTypeName"]
        elif entry.get("PlantTypeName"):
            row["type"] = TYPE_PLANT
            row["plantId"] = entry["PlantTypeName"]
        elif entry.get("CollectableTypeName"):
            row["type"] = TYPE_COLLECTABLE
            row["collectableType"] = entry["CollectableTypeName"]
        else:
            row["type"] = "unknown"
            tally["unknown"] += count
            rows.append(row)
            continue
        tally[row["type"]] += count
        rows.append(row)
    return rows, tally


def seed_bank(objs: Dict[str, Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Flatten the seed bank modules into an array plus a provenance block."""
    rows: List[Dict[str, Any]] = []
    info: Optional[Dict[str, Any]] = None
    bank = objs.get(SEEDBANK_CLS)
    if bank:
        method = bank.get("SelectionMethod")
        info = {
            "objclass": SEEDBANK_CLS,
            "method": method,
            "excludeList": list(bank.get("PlantExcludeList") or []),
        }
        for item in bank.get("PresetPlantList") or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "plantId": item.get("PlantType"),
                    "method": method,
                    "level": item.get("Level"),
                    "weight": None,
                    "minCount": None,
                    "maxCount": None,
                }
            )
    conveyor = objs.get(CONVEYOR_CLS)
    if conveyor:
        if info is None:
            info = {"objclass": CONVEYOR_CLS, "method": "conveyor"}
        else:
            info["conveyor"] = True
        for item in conveyor.get("InitialPlantList") or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "plantId": item.get("PlantType"),
                    "method": "conveyor",
                    "level": None,
                    "weight": item.get("Weight"),
                    "minCount": item.get("MinCount"),
                    "maxCount": item.get("MaxCount"),
                }
            )
    return rows, info


def collect_level(
    level_id: str, package: str, packages: Dict[str, Path]
) -> Dict[str, Any]:
    path = packages.get(package)
    row: Dict[str, Any] = {
        "levelId": level_id,
        "package": package,
        "levelFile": path.name if path else None,
        "levelNumber": None,
        "levelNameKey": None,
        "stageModule": None,
        "isVasebreaker": None,
        "levelPowerupSet": None,
        "modules": [],
        "preset": {"found": False, "objclass": PRESET_CLS, "aliases": [], "package": None},
        "vaseCount": None,
        "entryCount": 0,
        "byType": {TYPE_ZOMBIE: 0, TYPE_PLANT: 0, TYPE_COLLECTABLE: 0},
        "vases": [],
        "columnRange": {"min": None, "max": None},
        "excludedCells": [],
        "blacklistedCells": None,
        "coloredVases": {"plant": None, "zombie": None},
        "vaseGridItemType": None,
        "seedBank": [],
        "seedBankInfo": None,
        "initialSun": None,
        "initialSunSource": None,
        "timeLimit": None,
        "tide": None,
        "lastStand": None,
        "endless": None,
        "sourceFiles": [path.name] if path else [],
        "unknowns": [],
    }
    unknowns: List[str] = row["unknowns"]
    if path is None:
        unknowns.append(f"package: OBB 里找不到 {package}（extra.package 指向的包缺失）")
        return row

    by_class: Dict[str, Dict[str, Any]] = {}
    preset = None
    level = None
    preset_aliases: List[str] = []
    for objclass, aliases, data in iter_objects(load_json(path)):
        by_class.setdefault(objclass, data)
        if objclass == LEVEL_CLS and level is None:
            level = data
        elif objclass == PRESET_CLS and preset is None:
            preset = data
            preset_aliases = aliases

    if level is not None:
        row["levelNumber"] = _num(level.get("LevelNumber"))
        row["levelNameKey"] = level.get("Name")
        row["stageModule"] = rtid_name(level.get("StageModule"))
        row["levelPowerupSet"] = level.get("LevelPowerupSet")
        flag = level.get("IsVasebreaker")
        row["isVasebreaker"] = bool(flag) if isinstance(flag, bool) else None
        row["modules"] = [rtid_name(item) for item in level.get("Modules") or [] if rtid_name(item)]
        sun = _num(level.get("StartingSun"))
        if sun is not None:
            row["initialSun"] = sun
            row["initialSunSource"] = f"{LEVEL_CLS}.StartingSun"
        else:
            unknowns.append(UNKNOWN_INITIAL_SUN)
    else:
        unknowns.append(f"level: 该包里没有 {LEVEL_CLS} 对象")

    if preset is not None:
        row["preset"] = {
            "found": True,
            "objclass": PRESET_CLS,
            "aliases": preset_aliases,
            "package": package,
        }
        rows, tally = vase_entries(preset)
        row["vases"] = rows
        row["entryCount"] = len(rows)
        row["byType"] = {
            TYPE_ZOMBIE: tally.get(TYPE_ZOMBIE, 0),
            TYPE_PLANT: tally.get(TYPE_PLANT, 0),
            TYPE_COLLECTABLE: tally.get(TYPE_COLLECTABLE, 0),
        }
        row["vaseCount"] = sum(int(item["count"]) for item in rows)
        row["columnRange"] = {
            "min": _num(preset.get("MinColumnIndex")),
            "max": _num(preset.get("MaxColumnIndex")),
        }
        row["excludedCells"] = _ints(preset.get("GridSquareExcludelist"))
        blacklist = preset.get("GridSquareBlacklist")
        row["blacklistedCells"] = _ints(blacklist) if isinstance(blacklist, list) else None
        row["coloredVases"] = {
            "plant": _num(preset.get("NumColoredPlantVases")),
            "zombie": _num(preset.get("NumColoredZombieVases")),
        }
        row["vaseGridItemType"] = preset.get("VaseGridItemType")
        unknowns.extend([UNKNOWN_PLACEMENT, UNKNOWN_SUN])
    else:
        unknowns.append(UNKNOWN_PRESET)

    bank, info = seed_bank(by_class)
    row["seedBank"] = bank
    row["seedBankInfo"] = info
    if not bank:
        unknowns.append(UNKNOWN_SEEDBANK)

    tide = by_class.get(TIDE_CLS)
    if tide:
        row["tide"] = {"startingWaveLocation": _num(tide.get("StartingWaveLocation"))}
    last_stand = by_class.get(LASTSTAND_CLS)
    if last_stand:
        row["lastStand"] = {
            "startingSun": _num(last_stand.get("StartingSun")),
            "startingPlantfood": _num(last_stand.get("StartingPlantfood")),
        }
    endless = by_class.get(ENDLESS_CLS)
    if endless:
        row["endless"] = {
            "stageCount": len(endless.get("Stages") or []),
            "testEndlessLevel": endless.get("TestEndlessLevel"),
            "stages": endless.get("Stages") or [],
        }
        unknowns.append(UNKNOWN_ENDLESS)

    unknowns.append(UNKNOWN_TIMELIMIT)
    return row


def compile_data(levels_dir: Path, obb_dir: Path) -> Dict[str, Any]:
    wanted = level_ids(levels_dir)
    packages = package_index(obb_dir)
    levels: Dict[str, Any] = {}
    for level_id in sorted(wanted):
        levels[level_id] = collect_level(level_id, wanted[level_id], packages)

    by_type = Counter()
    unknown_kinds: Counter = Counter()
    missing_preset: List[str] = []
    missing_seedbank: List[str] = []
    missing_sun: List[str] = []
    with_preset = 0
    with_bank = 0
    with_sun = 0
    with_tide = 0
    with_endless = 0
    with_laststand = 0
    vase_total = 0
    entry_total = 0
    worlds: Counter = Counter()
    for level_id, row in levels.items():
        for kind, value in (row.get("byType") or {}).items():
            by_type[kind] += value
        vase_total += row.get("vaseCount") or 0
        entry_total += row.get("entryCount") or 0
        if row["preset"]["found"]:
            with_preset += 1
        else:
            missing_preset.append(level_id)
        if row.get("seedBank"):
            with_bank += 1
        else:
            missing_seedbank.append(level_id)
        if row.get("initialSun") is None:
            missing_sun.append(level_id)
        else:
            with_sun += 1
        if row.get("tide"):
            with_tide += 1
        if row.get("endless"):
            with_endless += 1
        if row.get("lastStand"):
            with_laststand += 1
        worlds[level_id.rsplit("_", 1)[0]] += 1
        for text in row.get("unknowns") or []:
            unknown_kinds[text.split(":", 1)[0]] += 1

    unknown_rows = [
        {
            "kind": kind,
            "count": count,
            "detail": next(
                text
                for row in levels.values()
                for text in row.get("unknowns") or []
                if text.split(":", 1)[0] == kind
            ),
        }
        for kind, count in sorted(unknown_kinds.items())
    ]

    counts = {
        "levels": len(levels),
        "withPreset": with_preset,
        "withoutPreset": len(missing_preset),
        "withoutPresetIds": missing_preset,
        "withSeedBank": with_bank,
        "withoutSeedBank": len(missing_seedbank),
        "withStartingSun": with_sun,
        "withoutStartingSun": len(missing_sun),
        "withTide": with_tide,
        "withEndless": with_endless,
        "withLastStand": with_laststand,
        "vaseTotal": vase_total,
        "entryTotal": entry_total,
        "byType": {TYPE_ZOMBIE: by_type[TYPE_ZOMBIE], TYPE_PLANT: by_type[TYPE_PLANT],
                   TYPE_COLLECTABLE: by_type[TYPE_COLLECTABLE]},
        "withTimeLimit": 0,
        "worlds": dict(sorted(worlds.items())),
        "unknownKinds": {kind: count for kind, count in sorted(unknown_kinds.items())},
    }
    return {
        "format": FORMAT,
        "generated": GENERATED,
        "sources": {
            "obb": portable(obb_dir),
            "levels": portable(levels_dir),
            "flag": f"content/levels/*.json extra.{VASE_FLAG}",
            "presetClass": PRESET_CLS,
            "levelClass": LEVEL_CLS,
        },
        "counts": counts,
        "levels": levels,
        "unknowns": unknown_rows,
    }


def render(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def dump(data: Dict[str, Any], path: Path) -> None:
    # write_bytes keeps the artefact LF-only on Windows, so --check can compare raw bytes.
    path.write_bytes(render(data).encode("utf-8"))


def check(data: Dict[str, Any], path: Path) -> int:
    problems: List[str] = []
    if data.get("format") != FORMAT:
        problems.append(f"format: {data.get('format')} != {FORMAT}")
    if data.get("generated") != GENERATED:
        problems.append(f"generated: {data.get('generated')} != {GENERATED}")
    levels = data.get("levels") or {}
    counts = data.get("counts") or {}
    if counts.get("levels") != len(levels):
        problems.append(f"counts.levels: {counts.get('levels')} != {len(levels)}")
    if sorted(levels) != list(levels):
        problems.append("levels: keys are not sorted")
    required = ("vaseCount", "vases", "seedBank", "initialSun", "timeLimit",
                "sourceFiles", "unknowns")
    vase_total = 0
    for level_id, row in levels.items():
        for key in required:
            if key not in row:
                problems.append(f"{level_id}: missing key {key}")
        vases = row.get("vases") or []
        if row.get("entryCount") != len(vases):
            problems.append(f"{level_id}: entryCount != len(vases)")
        total = sum(int(item.get("count") or 0) for item in vases)
        if (row.get("preset") or {}).get("found"):
            if row.get("vaseCount") != total:
                problems.append(f"{level_id}: vaseCount {row.get('vaseCount')} != {total}")
        else:
            # no preset -> the count is unknown, not zero: it must stay null and empty.
            if row.get("vaseCount") is not None:
                problems.append(f"{level_id}: vaseCount must be null without a preset")
            if vases:
                problems.append(f"{level_id}: vases must be empty without a preset")
        type_sum = sum(int(v) for v in (row.get("byType") or {}).values())
        if type_sum != total:
            problems.append(f"{level_id}: byType sum {type_sum} != {total}")
        if not (row.get("unknowns") or []):
            problems.append(f"{level_id}: unknowns must explain absent fields")
        if row.get("timeLimit") is not None:
            problems.append(f"{level_id}: timeLimit is not present in the original data")
        vase_total += total
    if counts.get("vaseTotal") != vase_total:
        problems.append(f"counts.vaseTotal: {counts.get('vaseTotal')} != {vase_total}")
    if counts.get("withPreset") is None or counts.get("withoutPreset") is None:
        problems.append("counts: preset totals missing")
    if counts.get("withPreset", 0) + counts.get("withoutPreset", 0) != len(levels):
        problems.append("counts: withPreset + withoutPreset != levels")
    if not path.exists():
        problems.append(f"artefact missing: {path}")
    else:
        raw = path.read_bytes()
        if b"\r\n" in raw:
            problems.append("artefact contains CRLF")
        if raw != render(data).encode("utf-8"):
            problems.append("artefact on disk differs from a fresh render (stale)")

    if problems:
        print("vasebreaker check FAILED")
        for text in problems[:40]:
            print(f"  - {text}")
        if len(problems) > 40:
            print(f"  ... {len(problems) - 40} more")
        return 1
    print(
        "vasebreaker levels={} presets={} (missing {}) vases={} seedBank={} startingSun={}"
        " unknowns={}".format(
            len(levels),
            counts.get("withPreset"),
            counts.get("withoutPreset"),
            vase_total,
            counts.get("withSeedBank"),
            counts.get("withStartingSun"),
            len(data.get("unknowns") or []),
        )
    )
    print("OK")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compile VaseBreaker level content")
    parser.add_argument("--obb", default=str(DEFAULT_OBB), help="OBB package dump directory")
    parser.add_argument("--levels", default=str(DEFAULT_LEVELS), help="client level directory")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output JSON path")
    parser.add_argument("--check", action="store_true", help="verify the artefact is up to date")
    args = parser.parse_args(argv)

    data = compile_data(Path(args.levels), Path(args.obb))
    out = Path(args.out)
    if args.check:
        return check(data, out)
    out.parent.mkdir(parents=True, exist_ok=True)
    dump(data, out)
    counts = data["counts"]
    print(
        "wrote {} levels={} presets={} vases={} bytes={}".format(
            out, counts["levels"], counts["withPreset"], counts["vaseTotal"],
            out.stat().st_size,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
