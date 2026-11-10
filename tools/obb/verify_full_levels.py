# -*- coding: utf-8 -*-
"""Verify the 26-world / 1809-level content with the real game data loader.

Checks every level through ``game.data.GameData`` (the same loader the game
uses), cross-checks ``content/worlds.json``, ``content/stars.json``,
``content/worldmap.json`` and ``work/full_levels_v2_report.json``, and
verifies that every world card / lawn asset exists at 1280x720.

Writes work/full_levels_v2_verify.json and exits non-zero on any failure.
Run from the workspace root with the runtime python.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
PROJECT = WORKSPACE / "PvZ2SHUTTLE"
sys.path.insert(0, str(PROJECT))

from game.data import GameData  # noqa: E402

CONTENT = PROJECT / "content"
REPORT_PATH = WORKSPACE / "work" / "full_levels_v2_report.json"
OUT = WORKSPACE / "work" / "full_levels_v2_verify.json"
EXPECTED_WORLDS = 26
EXPECTED_LEVELS = 1809


def load_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def main() -> int:
    data = GameData()
    stars = load_json(CONTENT / "stars.json", {})
    worldmap = load_json(CONTENT / "worldmap.json", {}).get("worlds", {})
    report = load_json(REPORT_PATH, {})
    report_worlds = {w["id"]: w for w in report.get("world_list", [])}
    worlds = sorted(data.worlds, key=lambda w: w.order)

    failures: list[str] = []
    world_rows = []
    all_levels = []
    for world in worlds:
        levels = data.levels(world.id)
        deck_ok = waves_ok = stars_ok = True
        boss = night = tool = 0
        for lv in levels:
            all_levels.append(lv)
            if not lv.deck or any(p not in data.plants for p in lv.deck):
                deck_ok = False
                failures.append(f"{lv.id}: deck")
            if not lv.waves:
                waves_ok = False
                failures.append(f"{lv.id}: empty waves")
            for wave in lv.waves:
                if not wave.zombies:
                    waves_ok = False
                    failures.append(f"{lv.id}: empty wave")
                for z in wave.zombies:
                    if z.type not in data.zombies:
                        waves_ok = False
                        failures.append(f"{lv.id}: unknown zombie {z.type}")
            extra = lv.extra or {}
            boss += 1 if extra.get("boss") else 0
            night += 1 if extra.get("night") else 0
            tool += 1 if extra.get("special") else 0
            conds = stars.get(lv.id)
            if not isinstance(conds, list) or len(conds) != 3:
                stars_ok = False
                failures.append(f"{lv.id}: stars missing")
            else:
                seen = set()
                for cond in conds:
                    if not isinstance(cond, dict) or "value" not in cond or "type" not in cond:
                        stars_ok = False
                        failures.append(f"{lv.id}: bad star {cond}")
                        continue
                    if cond["type"] in seen:
                        stars_ok = False
                        failures.append(f"{lv.id}: duplicate star type {cond['type']}")
                    seen.add(cond["type"])
        row = {
            "id": world.id,
            "order": world.order,
            "name_zh": world.name_zh,
            "levels": len(levels),
            "boss": boss,
            "night": night,
            "tool_levels": tool,
            "deck_ok": deck_ok,
            "waves_ok": waves_ok,
            "stars_ok": stars_ok,
            "unlock_after": world.unlock_after,
            "map": world.map,
            "lawn": world.lawn,
        }
        world_rows.append(row)
        expected = report_worlds.get(world.id)
        if not expected:
            failures.append(f"{world.id}: missing from v2 report")
        elif expected["levels"] != len(levels):
            failures.append(f"{world.id}: report levels {expected['levels']} != {len(levels)}")

    # order + unlock chain
    orders = [w.order for w in worlds]
    if orders != list(range(1, EXPECTED_WORLDS + 1)):
        failures.append(f"world order not 1..{EXPECTED_WORLDS}: {orders}")
    for i, w in enumerate(worlds):
        expected_unlock = worlds[i - 1].id if i else None
        if w.unlock_after != expected_unlock:
            failures.append(f"{w.id}: unlock_after {w.unlock_after!r} != {expected_unlock!r}")

    # worldmap + assets
    asset_rows = []
    for w in worlds:
        if w.id not in worldmap:
            failures.append(f"{w.id}: missing worldmap entry")
        else:
            wm = worldmap[w.id]
            if wm.get("order") != w.order:
                failures.append(f"{w.id}: worldmap order mismatch")
            if wm.get("unlock_cost") != 1:
                failures.append(f"{w.id}: unlock_cost != 1")
            if wm.get("key_required") is not (w.id != "frontyard"):
                failures.append(f"{w.id}: key_required wrong")
        for kind, rel in (("world", w.map), ("lawn", w.lawn)):
            p = PROJECT / "assets" / rel
            if not p.exists():
                failures.append(f"{w.id}: missing {kind} asset {rel}")
                asset_rows.append({"world": w.id, "kind": kind, "path": rel, "ok": False})
                continue
            try:
                from PIL import Image
                with Image.open(p) as im:
                    size = im.size
                ok = size == (1280, 720)
            except Exception:
                size, ok = None, False
            if not ok:
                failures.append(f"{w.id}: {kind} asset size {size} != (1280, 720)")
            asset_rows.append({"world": w.id, "kind": kind, "path": rel,
                               "size": list(size) if size else None, "ok": ok})

    random.seed(20261110)
    sample = []
    for lv in random.sample(all_levels, min(20, len(all_levels))):
        sample.append({
            "id": lv.id,
            "world": lv.world,
            "index": lv.index,
            "title": lv.title,
            "deck_size": len(lv.deck),
            "waves": len(lv.waves),
            "zombies": sum(len(w.zombies) for w in lv.waves),
        })

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "content": {
            "plants": len(data.plants),
            "zombies": len(data.zombies),
            "worlds": len(worlds),
            "levels": len(all_levels),
            "stars": len(stars),
            "worldmap": len(worldmap),
        },
        "checks": {
            "worlds_26": len(worlds) == EXPECTED_WORLDS,
            "levels_1809": len(all_levels) == EXPECTED_LEVELS,
            "stars_cover_all_levels": all(lv.id in stars for lv in all_levels),
            "every_world_has_levels": all(r["levels"] > 0 for r in world_rows),
            "all_worlds_deck_ok": all(r["deck_ok"] for r in world_rows),
            "all_worlds_waves_ok": all(r["waves_ok"] for r in world_rows),
            "all_worlds_stars_ok": all(r["stars_ok"] for r in world_rows),
            "all_worlds_have_assets": all(a["ok"] for a in asset_rows),
            "order_contiguous": orders == list(range(1, EXPECTED_WORLDS + 1)),
            "unlock_chain_ok": not any("unlock_after" in f for f in failures),
            "worldmap_matches": not any("worldmap" in f for f in failures),
            "random_20_sample_ok": all(
                s["deck_size"] > 0 and s["waves"] > 0 for s in sample),
            "failures": failures[:80],
        },
        "totals": {
            "levels": len(all_levels),
            "boss_levels": sum(r["boss"] for r in world_rows),
            "night_levels": sum(r["night"] for r in world_rows),
            "tool_levels": sum(r["tool_levels"] for r in world_rows),
            "special_included": report.get("special_included", {}),
            "needs_art": report.get("NEEDS_ART", []),
        },
        "worlds": world_rows,
        "assets": asset_rows,
        "random_sample": sample,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    print(json.dumps({k: result[k] for k in ("content", "checks", "totals")},
                     ensure_ascii=False, indent=1))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
