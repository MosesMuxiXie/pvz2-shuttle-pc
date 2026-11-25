#!/usr/bin/env python3
"""Run the headless engine on fixed scenarios and record the outcome.

This is the regression gate for `--run-level`: the same level, seed and script
must always produce the same state hash, and a scenario that used to finish in
one state must not silently change state between builds. Everything is read
from the CLI, so the gate also proves the CLI itself still works.

Scenarios come in three groups:
  * board       one representative level per shipped world (26 runs) — proves every
                world opens with the geometry `board_sizes.json` claims
  * probe       targeted cases: an explicit 6x10 override, a scripted game, a late
                level with two flags
  * victory     a level the engine must actually finish in `won`, so the win branch
                is covered through the CLI and not only from a unit test

Usage:
    python tools/engine_smoke.py [--exe PATH] [--content DIR] [--pack FILE]
                                 [--boards FILE] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

PROBES: list[dict[str, object]] = [
    {"name": "frontyard_1 5x9", "level": "frontyard_1", "seconds": 240},
    {"name": "frontyard_1 6x10", "level": "frontyard_1", "seconds": 240, "rows": 6, "cols": 10},
    # `killed` used to include lawn-mower kills, so this probe used to report 30.
    # Mower kills have their own counter now and the scripted deck really only
    # shoots down about 15 of the 33 zombies; the rest reach the lane mowers.
    {"name": "frontyard_1 script", "level": "frontyard_1", "seconds": 300,
     "script": "native/tests/scripts/frontyard_1_basic.json", "minKilled": 10},
    {"name": "frontyard_6 5x9", "level": "frontyard_6", "seconds": 300},
    {"name": "kongfu_1 5x9", "level": "kongfu_1", "seconds": 240},
    # The scripted game above never wins; this one must, so `won` is a gate value.
    {"name": "beach_23 win", "level": "beach_23", "seconds": 400,
     "script": "native/tests/scripts/beach_23_win.json", "expectStatus": "won"},
]


def world_levels(content: Path) -> dict[str, str]:
    """Lowest-index level per world, taken from the shipped level files."""
    chosen: dict[str, tuple[int, str]] = {}
    for path in sorted((content / "levels").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        world = str(doc.get("world") or "")
        index = int(doc.get("index") or 0)
        if not world or index <= 0:
            continue
        if world not in chosen or index < chosen[world][0]:
            chosen[world] = (index, str(doc.get("id")))
    return {world: level_id for world, (_, level_id) in chosen.items()}


def scenarios(content: Path) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for world, level_id in sorted(world_levels(content).items()):
        found.append({"name": f"world {world}", "level": level_id, "seconds": 120, "world": world})
    return found + PROBES


def run_once(exe: Path, content: Path, pack: Path, boards: Path, scenario: dict[str, object]) -> dict:
    command = [str(exe), "--run-level", str(content), str(scenario["level"])]
    if pack.is_file():
        command += ["--pack", str(pack)]
    if boards.is_file():
        command += ["--boards", str(boards)]
    command += ["--seconds", str(scenario["seconds"])]
    if "script" in scenario:
        command += ["--script", str(REPO / str(scenario["script"]))]
    if "rows" in scenario:
        command += ["--rows", str(scenario["rows"])]
    if "cols" in scenario:
        command += ["--cols", str(scenario["cols"])]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if completed.returncode != 0:
        raise SystemExit(
            f"engine smoke: {scenario['name']} exited {completed.returncode}\n"
            f"  command: {' '.join(command)}\n  stderr: {completed.stderr.strip()}"
        )
    line = completed.stdout.strip().splitlines()
    if len(line) != 1:
        raise SystemExit(f"engine smoke: {scenario['name']} printed {len(line)} lines, want 1")
    return json.loads(line[0])


def check(scenario: dict[str, object], result: dict, expected_board: dict[str, dict]) -> None:
    minimum = scenario.get("minKilled")
    if minimum is not None and result.get("killed", 0) < int(minimum):
        raise SystemExit(f"engine smoke: {scenario['name']} killed {result.get('killed')} zombies, "
                         f"want at least {minimum}")
    status = scenario.get("expectStatus")
    if status is not None and result.get("status") != status:
        raise SystemExit(f"engine smoke: {scenario['name']} ended '{result.get('status')}', want '{status}'")
    # Every spawn must end up in exactly one bucket: shot down, mowed, or leaked.
    # A win leaves nothing alive, so the identity has to be tight there; elsewhere
    # it bounds the counters from above (survivors are still walking).
    spawned = int(result.get("spawned") or 0)
    accounted = (int(result.get("killed") or 0) + int(result.get("mowerKills") or 0)
                 + int(result.get("leaked") or 0))
    if accounted > spawned:
        raise SystemExit(f"engine smoke: {scenario['name']} accounted for {accounted} zombies "
                         f"but only spawned {spawned}")
    if result.get("status") == "won" and accounted != spawned:
        raise SystemExit(f"engine smoke: {scenario['name']} won with {spawned} spawned but "
                         f"{accounted} resolved (killed+mowerKills+leaked)")
    world = scenario.get("world")
    if isinstance(world, str) and "rows" not in scenario and "cols" not in scenario:
        board = expected_board.get(world)
        if board is None:
            raise SystemExit(f"engine smoke: no board geometry for world '{world}'")
        if (result.get("rows"), result.get("cols")) != (board["rows"], board["cols"]):
            raise SystemExit(
                f"engine smoke: {scenario['name']} opened {result.get('rows')}x{result.get('cols')}, "
                f"board_sizes.json says {board['rows']}x{board['cols']}"
            )


def build_report(exe: Path, content: Path, pack: Path, boards: Path) -> dict:
    expected_board = json.loads(boards.read_text(encoding="utf-8")) if boards.is_file() else {}
    entries = []
    for scenario in scenarios(content):
        first = run_once(exe, content, pack, boards, scenario)
        second = run_once(exe, content, pack, boards, scenario)
        if first != second:
            raise SystemExit(f"engine smoke: {scenario['name']} is not deterministic\n"
                             f"  first:  {json.dumps(first, sort_keys=True)}\n"
                             f"  second: {json.dumps(second, sort_keys=True)}")
        check(scenario, first, expected_board)
        entries.append({"name": scenario["name"], "level": scenario["level"],
                        "seconds": scenario["seconds"],
                        "rows": first.get("rows"), "cols": first.get("cols"),
                        "status": first.get("status"), "tick": first.get("tick"),
                        "hash": first.get("hash"), "spawned": first.get("spawned"),
                        "killed": first.get("killed"), "removed": first.get("removed"),
                        "mowerKills": first.get("mowerKills"), "leaked": first.get("leaked"),
                        "rejectedSpawns": first.get("rejectedSpawns"),
                        "unwiredPlants": first.get("unwiredPlants"),
                        "unwiredZombies": first.get("unwiredZombies")})
    won = sum(1 for entry in entries if entry["status"] == "won")
    if won == 0:
        raise SystemExit("engine smoke: no scenario reached 'won'; the victory branch is unproven")
    return {"scenarios": entries}


def render(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=REPO / "build" / "native" / "Release" / "PvZ2SHUTTLE.exe")
    parser.add_argument("--content", type=Path, default=REPO / "content")
    parser.add_argument("--pack", type=Path, default=REPO / "native" / "generated" / "content.pack")
    parser.add_argument("--boards", type=Path, default=REPO / "native" / "generated" / "board_sizes.json")
    parser.add_argument("--out", type=Path, default=REPO / "native" / "generated" / "engine_smoke.json")
    args = parser.parse_args()

    report = build_report(args.exe, args.content, args.pack, args.boards)
    text = render(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(text.encode("utf-8"))
    print(f"wrote {args.out}")
    for entry in report["scenarios"]:
        print(f"{entry['name']:22s} {entry['rows']}x{entry['cols']} {entry['status']:8s} "
              f"tick={entry['tick']:5d} hash={entry['hash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
