"""Which original level mechanics does the client actually represent?

Read-only. For every mechanic objclass we count:
  * objects        - how many objects of that class exist
  * levelFiles     - how many level packages (pkg_*_LevelDefinition.json) carry it
  * clientField    - what the client level JSON has for it today (or "")

The client level JSON is a simplified shape (id/world/index/title/sun/deck/waves/
flags/seed_bank/extra), so anything whose clientField is empty is a mechanic the
engine cannot see at all.

Usage: python work/probe_level_mechanics.py [--json out.json]
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from contentc import s5scan  # noqa: E402

OBB = s5scan.DEFAULT_OBB

# (mechanic id, objclass substring, what the client has today)
MECHANICS = [
    ("conveyor", "ConveyorSeedBankProperties", "extra.seed_bank 只是一个 int，没有传送带卡槽"),
    ("seedbank", "SeedBankProperties", "seed_bank(int) + deck[]"),
    ("gravestone", "GravestoneProperties", ""),
    ("initial_plant", "InitialPlantProperties", ""),
    ("initial_griditem", "InitialGridItemProperties", ""),
    ("protect_plant", "ProtectThePlantChallengeProperties", ""),
    ("tide", "TidalChangeWaveActionProps", ""),
    ("frost", "FrostWindWaveActionProps", ""),
    ("dino", "DinoWaveActionProps", ""),
    ("portal", "SpawnModernPortalsWaveActionProps", ""),
    ("spider_rain", "SpiderRainZombieSpawnerProps", ""),
    ("fish", "SpawnZombiesFishWaveActionProps", ""),
    ("storm", "StormZombieSpawnerProps", ""),
    ("beach_event", "BeachStageEventZombieSpawnerProps", ""),
    ("gravestone_wave", "SpawnGravestonesWaveActionProps", ""),
    ("grid_spawner", "SpawnZombiesFromGridItemSpawnerProps", ""),
    ("ground_spawner", "SpawnZombiesFromGroundSpawnerProps", ""),
    ("conveyor_wave", "ModifyConveyorWaveActionProps", ""),
    ("board_gridmap", "BoardGridMapProps", ""),
    ("star_challenge", "StarChallengeModuleProperties", "stars.json 只有星章目标"),
    ("mutator", "LevelMutator", ""),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    files = s5scan.package_paths(OBB)
    level_files = {p.name for p in files if p.name.endswith("_LevelDefinition.json")}
    counts = Counter()
    in_levels = defaultdict(set)

    for path in files:
        pkg = s5scan.load_package(path)
        if not pkg:
            continue
        objs = pkg.get("objects") or []
        if isinstance(objs, dict):
            objs = list(objs.values())
        is_level = path.name in level_files
        for obj in objs:
            cls = obj.get("objclass") or ""
            if not cls:
                continue
            counts[cls] += 1
            if is_level:
                in_levels[cls].add(path.name)

    rows = []
    for mid, needle, client in MECHANICS:
        hits = {c: n for c, n in counts.items() if needle.lower() in c.lower()}
        objects = sum(hits.values())
        levels = set()
        for c in hits:
            levels |= in_levels.get(c, set())
        rows.append({
            "mechanic": mid,
            "needle": needle,
            "classes": sorted(hits),
            "objects": objects,
            "levelFiles": len(levels),
            "clientField": client,
            "sampleLevels": sorted(l.replace("pkg_", "").replace("_LevelDefinition.json", "") for l in list(levels)[:5]),
        })

    print("level packages:", len(level_files))
    print("%-16s %-8s %-8s %s" % ("mechanic", "objects", "levels", "client today"))
    for r in sorted(rows, key=lambda r: -r["levelFiles"]):
        print("%-16s %-8d %-8d %s" % (r["mechanic"], r["objects"], r["levelFiles"], r["clientField"] or "(nothing)"))

    if args.json:
        io.open(args.json, "w", encoding="utf-8", newline="\n").write(
            json.dumps({"levelPackages": len(level_files), "mechanics": rows}, ensure_ascii=False, indent=1))
        print("wrote", args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
