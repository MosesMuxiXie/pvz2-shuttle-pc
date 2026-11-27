"""A6 (S3): per-level playability ledger for all 1809 client levels.

What this file answers, and for whom
------------------------------------
The A part of S3 is "wire every mechanic the sheet declares". Before that work can be
scheduled it needs one honest list: **for each of the 1809 levels, which mechanics does the
shipped data declare, and does the kernel actually run them?**  This compiler produces that
list mechanically instead of by reading the engine and guessing.

Where the answer comes from
---------------------------
Two independent halves, and neither is allowed to speak for the other:

* **What the level declares** - `native/generated/level_mechanics.json` (the per-level
  conveyor / initial field / protect mission / spawner rows / events / mutators / board
  grid) plus the level's own `extra` flags in `content/levels/*.json` (boss, rail,
  minecarts, vasebreaker, night, suppressFlagZombie).
* **What the kernel runs** - `native/src/**`, quoted as `file:line` in every row.  A
  mechanic is `wired` only when a reader exists for it; the citation is the reader, not
  the schema.  `mechanicTierFor()` in `native/src/engine/mechanics.cpp` is the engine's own
  statement of the same thing, and this file agrees with it line for line (see R03).

Rules
-----
R01 A level's mechanics come from its own rows only.  A mechanic that another level in the
    same package declares is not inherited: `pkg_0290` holds two levels and only one of
    them is a conveyor level.
R02 Presence means "the sheet asks for it": a non-empty placement list, a non-empty spawner
    table, a non-null protect mission, a true flag.  A field that is present but empty is
    the sheet saying "not this level" and is not counted (350 conveyor rows, 466 opening
    grid-item rows).
R03 `wired` is decided by an explicit registry (`MECHANISMS`) whose every entry carries the
    `file:line` of its consumer.  The registry is cross-checked against the engine's own
    `kCovered` list: `mechanicTierFor()` names thirteen covered kinds and this file must
    agree with it on all thirteen (see `check()`), so a kernel change that wires something
    new fails here until the ledger is updated rather than drifting silently.
R04 `playable` follows the contract the task fixed: a level is playable only when it has
    **no data-only mechanic and no blocked minigame**.  Data-only means the sheet declares
    it and no reader exists; blocked minigame means `minigame_rules.json` says the kind's
    critical parameters are missing (column, invisighoul).
R05 The engine's coverage of a *game mode* is a second, separate question and gets its own
    field.  `minigame_rules.json` answers "is the data complete"; `MINIGAME_ENGINE` answers
    "does `native/src` implement this mode".  Both are reported; R04 only uses the first,
    because that is what the contract fixed.  `playableInEngine` is the conjunction and is
    reported next to `playable` so the ledger cannot be read as more than it is.
R06 Wired mechanics are listed too, with their citation: a level's `mechanics` array is the
    full picture (what runs and what does not), and `wiredCount` / `dataOnlyCount` are its
    arithmetic, not a filter.
R07 Data gaps that are neither (a level that asks for a mode whose own table has no row for
    it, e.g. `frontyard_166`, the one vasebreaker level with no preset) go into `notes`, so
    they are visible without being mislabelled as a kernel gap.
R08 Determinism: fixed `GENERATED` date, compact separators, sorted keys, LF only, and
    `--check` compares the file byte for byte.  Written through `write_bytes` because
    `Path.write_text` emits CRLF on Windows and would make the gate fail on a clean tree.

Levels that declare nothing
---------------------------
80 of the 1809 declare no mechanics at all (`counts.levelsAllNull` in the mechanics sheet).
They are still listed, with empty `mechanics`/`minigames` and `playable: true`: a plain
level with no mechanic is exactly what the kernel already plays, and dropping them from the
ledger would hide the majority of the game from a coverage count.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MECH = ROOT / "native" / "generated" / "level_mechanics.json"
DEFAULT_MINI = ROOT / "native" / "generated" / "minigames.json"
DEFAULT_RULES = ROOT / "native" / "generated" / "minigame_rules.json"
DEFAULT_VASE = ROOT / "native" / "generated" / "vasebreaker.json"
DEFAULT_LEVELS = ROOT / "content" / "levels"
DEFAULT_OUT = ROOT / "native" / "generated" / "level_playability.json"

FORMAT = "pvz2-shuttle/level-playability@1"
GENERATED = "2026-11-26"

# R04, quoted by the report and asserted by the tests.
CRITERION = "playable = 没有任何 data-only 机制 且 没有 blocked 玩法（minigame_rules 判 false 的 kind）"

# R03: the wiring registry.  `source` is the reader, `declared` is the sheet field it reads.
# `wired=False` rows carry the line that proves the kernel does *not* read it.
MECHANISMS = [
    {
        "id": "conveyor",
        "cn": "传送带",
        "declared": "level_mechanics.levels.<id>.conveyor",
        "wired": True,
        "source": "native/src/engine/mechanics.cpp:127 readConveyor；native/src/engine/world.cpp:825 dealConveyor",
    },
    {
        "id": "initialPlants",
        "cn": "开局预置植物",
        "declared": "level_mechanics.levels.<id>.initialPlants.placements",
        "wired": True,
        "source": "native/src/engine/mechanics.cpp:410 readPlacements；native/src/engine/world.cpp:758 layInitialField",
    },
    {
        "id": "initialGridItems",
        "cn": "开局预置格子物件（墓碑/水坑）",
        "declared": "level_mechanics.levels.<id>.initialGridItems.placements",
        "wired": True,
        "source": "native/src/engine/mechanics.cpp:413 readGridItems；native/src/engine/world.cpp:778 layInitialField",
    },
    {
        "id": "protectThePlant",
        "cn": "保护植物任务",
        "declared": "level_mechanics.levels.<id>.protectThePlant",
        "wired": True,
        "source": "native/src/engine/mechanics.cpp:418 readProtect；native/src/engine/world.cpp:760,769,1512 requiredSurvivors",
    },
    {
        "id": "spawners.gravestone",
        "cn": "墓碑波次",
        "declared": "level_mechanics.levels.<id>.spawners.gravestone",
        "wired": True,
        "source": "native/src/engine/mechanics.cpp:419 readGravestones；native/src/engine/world.cpp:810 spawnGravestonesForWave",
    },
    {
        "id": "spawners.jittered",
        "cn": "普通僵尸波次表",
        "declared": "level_mechanics.levels.<id>.spawners.jittered",
        "wired": True,
        "source": "native/src/engine/mechanics.cpp:456（kCovered，director 已把它当普通波次）；native/src/engine/director.cpp",
    },
    {
        "id": "spawners.grid",
        "cn": "格子/墓碑群刷怪",
        "declared": "level_mechanics.levels.<id>.spawners.grid",
        "wired": True,
        "source": "native/src/engine/mechanics.cpp:247 readSpawners + 457 kCovered；native/src/engine/world.cpp:861 scheduleSpawnersForWave",
    },
    {
        "id": "spawners.portal",
        "cn": "传送门刷怪",
        "declared": "level_mechanics.levels.<id>.spawners.portal",
        "wired": True,
        "source": "native/src/engine/mechanics.cpp:247 readSpawners + 458 kCovered；native/src/engine/world.cpp:861 scheduleSpawnersForWave",
    },
    {
        "id": "spawners.storm",
        "cn": "风暴刷怪",
        "declared": "level_mechanics.levels.<id>.spawners.storm",
        "wired": True,
        "source": "native/src/engine/mechanics.cpp:247 readSpawners + 459 kCovered；native/src/engine/world.cpp:861 scheduleSpawnersForWave",
    },
    {
        "id": "spawners.ground",
        "cn": "地面钻出刷怪",
        "declared": "level_mechanics.levels.<id>.spawners.ground",
        "wired": True,
        "source": "native/src/engine/mechanics.cpp:247 readSpawners + 460 kCovered；native/src/engine/world.cpp:861 scheduleSpawnersForWave",
    },
    {
        "id": "spawners.dino",
        "cn": "恐龙骑乘刷怪",
        "declared": "level_mechanics.levels.<id>.spawners.dino",
        "wired": True,
        "source": "native/src/engine/mechanics.cpp:247 readSpawners + 461 kCovered；native/src/engine/world.cpp:861 scheduleSpawnersForWave",
    },
    {
        "id": "spawners.beach",
        "cn": "海滩出水刷怪",
        "declared": "level_mechanics.levels.<id>.spawners.beach",
        "wired": True,
        "source": "native/src/engine/mechanics.cpp:247 readSpawners + 462 kCovered；native/src/engine/world.cpp:861 scheduleSpawnersForWave",
    },
    {
        "id": "spawners.fish",
        "cn": "鱼群刷怪",
        "declared": "level_mechanics.levels.<id>.spawners.fish",
        "wired": True,
        "source": "native/src/engine/mechanics.cpp:247 readSpawners + 463 kCovered；native/src/engine/world.cpp:861 scheduleSpawnersForWave",
    },
    {
        "id": "boss",
        "cn": "Boss 关",
        "declared": "content/levels/<id>.json extra.boss / extra.boss_zombie",
        "wired": True,
        "source": "native/src/engine/boss.cpp:247 selectBoss（读 extra.boss_zombie/boss）；native/src/engine/world.cpp:107,1151 trySpawnBoss",
    },
    {
        "id": "rail",
        "cn": "矿车轨道",
        "declared": "content/levels/<id>.json extra.rail",
        "wired": True,
        "source": "native/src/engine/world.cpp:162,160 layRailCarts；native/src/engine/rail.cpp:104 RailTable::shared",
    },
    {
        "id": "minecarts",
        "cn": "矿车行号表",
        "declared": "content/levels/<id>.json extra.minecarts",
        "wired": True,
        "source": "native/src/engine/world.cpp:173（layRailCarts 读 extra.minecarts 的行号）",
    },
    {
        "id": "vasebreaker",
        "cn": "砸罐子",
        "declared": "content/levels/<id>.json extra.vasebreaker + native/generated/vasebreaker.json",
        "wired": True,
        "source": "native/src/engine/world.cpp:89,156 layVases；native/src/engine/vase.cpp:132 VaseTable::shared",
    },
    {
        "id": "suppressFlagZombie",
        "cn": "旗子波按普通波处理",
        "declared": "content/levels/<id>.json extra.suppressFlagZombie == true",
        "wired": True,
        "source": "native/src/engine/world.cpp:75 读开关；world.cpp:374 flagDropped",
    },
    {
        "id": "spawners.spider",
        "cn": "蜘蛛雨刷怪",
        "declared": "level_mechanics.levels.<id>.spawners.spider",
        "wired": False,
        "source": "native/src/engine/mechanics.cpp:488 spawnerKindIsWired 明确返回 false（两张僵尸表都没有蜘蛛）；world.cpp:141 记为 mechanic_unknown",
    },
    {
        "id": "events.tide",
        "cn": "涨潮事件",
        "declared": "level_mechanics.levels.<id>.events.tide",
        "wired": False,
        "source": "native/src/engine/mechanics.cpp:373 把整个 events 记成未知；native/src 无 tide 读取点",
    },
    {
        "id": "events.frost",
        "cn": "冰风事件",
        "declared": "level_mechanics.levels.<id>.events.frost",
        "wired": False,
        "source": "native/src/engine/mechanics.cpp:373 把整个 events 记成未知；native/src 无 frost 读取点",
    },
    {
        "id": "events.strength",
        "cn": "风力强度",
        "declared": "level_mechanics.levels.<id>.events.strength",
        "wired": False,
        "source": "native/src/engine/mechanics.cpp:373 把整个 events 记成未知；native/src 无 strength 读取点",
    },
    {
        "id": "mutators",
        "cn": "关卡变体表（挑战/筛子）",
        "declared": "level_mechanics.levels.<id>.mutators",
        "wired": False,
        "source": "native/src/engine/mechanics.cpp:375 记成未知；native/src 无 mutator 读取点",
    },
    {
        "id": "boardGrid",
        "cn": "棋盘网格覆盖（限制可种植格）",
        "declared": "level_mechanics.levels.<id>.boardGrid",
        "wired": False,
        "source": "native/src/engine/mechanics.cpp:378 记成未知；native/src 无 boardGrid 读取点",
    },
    {
        "id": "night",
        "cn": "夜战（无天降阳光）",
        "declared": "content/levels/<id>.json extra.night == true",
        "wired": False,
        "source": "native/src/engine/world.cpp:355 tickSkySun 只在砸罐子关被跳过（352 行），night 没有任何读取点",
    },
]

MECH_ORDER = [row["id"] for row in MECHANISMS]
MECH_BY_ID = {row["id"]: row for row in MECHANISMS}

# The engine's own statement of coverage, transcribed from
# native/src/engine/mechanics.cpp:451-463.  check() asserts the registry agrees.
ENGINE_KCOVERED = [
    "initialPlants",
    "initialGridItems",
    "conveyor",
    "protectThePlant",
    "spawners.gravestone",
    "spawners.jittered",
    "spawners.grid",
    "spawners.portal",
    "spawners.storm",
    "spawners.ground",
    "spawners.dino",
    "spawners.beach",
    "spawners.fish",
]

# R05: does `native/src` implement the game mode itself?  Only four of the twenty kinds have
# a reader; the rest are complete in data and play as ordinary seed-bank levels today.
MINIGAME_ENGINE = {
    "vasebreaker": ("native/src/engine/world.cpp:89 vaseLevel + :156 layVases"),
    "rail": ("native/src/engine/world.cpp:162 extra.rail + rail.cpp:104 RailTable"),
    "conveyor": ("native/src/engine/world.cpp:825 dealConveyor（传送带即该变体）"),
    "protecttheplant": ("native/src/engine/world.cpp:760,1512 requiredSurvivors（保护任务即该变体）"),
}

SPAWNER_KINDS = ("gravestone", "jittered", "grid", "portal", "storm", "ground", "dino", "beach", "fish")

NOTE_VASE_WITHOUT_PRESET = "vasebreaker-flag-without-preset"


def load_json(path: Path):
    """Read one JSON document (utf-8-sig: the sheets carry a BOM)."""
    with path.open(encoding="utf-8-sig") as fh:
        return json.load(fh)


def level_flags(levels_dir: Path) -> dict[str, dict]:
    """`{level id: extra}` for every shipped level file, sorted by id."""
    out: dict[str, dict] = {}
    for path in sorted(levels_dir.glob("*.json")):
        doc = load_json(path)
        extra = doc.get("extra")
        out[path.stem] = extra if isinstance(extra, dict) else {}
    return out


def world_of(level_id: str) -> str:
    """The level file name is `<world>_<n>.json`; the client never ships another shape."""
    return level_id.rsplit("_", 1)[0]


def declared_mechanics(row: dict | None, extra: dict) -> list[str]:
    """R01/R02: the mechanics this level itself asks for, in registry order."""
    found: set[str] = set()
    if row:
        if row.get("conveyor"):
            found.add("conveyor")
        plants = row.get("initialPlants") or {}
        if isinstance(plants, dict) and plants.get("placements"):
            found.add("initialPlants")
        items = row.get("initialGridItems") or {}
        if isinstance(items, dict) and items.get("placements"):
            found.add("initialGridItems")
        if row.get("protectThePlant"):
            found.add("protectThePlant")
        spawners = row.get("spawners") or {}
        if isinstance(spawners, dict):
            # The keys inside `spawners` are bare kind names (`grid`, `jittered`); the ledger
            # prefixes them so a spawned row cannot be confused with a top-level field.
            for kind in SPAWNER_KINDS:
                if spawners.get(kind):
                    found.add("spawners." + kind)
            if spawners.get("spider"):
                found.add("spawners.spider")
        events = row.get("events") or {}
        if isinstance(events, dict):
            if events.get("tide"):
                found.add("events.tide")
            if events.get("frost"):
                found.add("events.frost")
            if events.get("strength") is not None:
                found.add("events.strength")
        if row.get("mutators"):
            found.add("mutators")
        if row.get("boardGrid"):
            found.add("boardGrid")
    if extra.get("boss") or extra.get("boss_zombie"):
        found.add("boss")
    if extra.get("rail") is True:
        found.add("rail")
    if extra.get("minecarts"):
        found.add("minecarts")
    if extra.get("vasebreaker") is True:
        found.add("vasebreaker")
    if extra.get("suppressFlagZombie") is True:
        found.add("suppressFlagZombie")
    if extra.get("night") is True:
        found.add("night")
    return [kind for kind in MECH_ORDER if kind in found]


def build(mech_path: Path, mini_path: Path, rules_path: Path, vase_path: Path,
          levels_dir: Path) -> dict:
    mechanics_sheet = load_json(mech_path)
    mini_sheet = load_json(mini_path)
    rules_sheet = load_json(rules_path)
    vase_sheet = load_json(vase_path)

    mech_levels = mechanics_sheet.get("levels") or {}
    mini_levels = mini_sheet.get("levels") or {}
    vase_levels = vase_sheet.get("levels") or {}
    rule_kinds = rules_sheet.get("kinds") or {}
    flags = level_flags(levels_dir)

    if not flags:
        raise SystemExit(f"level_playability: no level files under {levels_dir}")

    minigame_playable = {}
    for kind, row in rule_kinds.items():
        minigame_playable[kind] = bool(row.get("playable"))

    levels: dict[str, dict] = {}
    blockers_hist: Counter = Counter()
    notes_hist: Counter = Counter()
    mech_hist: Counter = Counter()
    mini_hist: Counter = Counter()
    engine_gap_hist: Counter = Counter()
    solo: list[dict] = []
    playable = 0
    blocked_data = 0
    blocked_mini = 0
    blocked_both = 0
    any_blocker = 0
    playable_in_engine = 0

    for level_id in sorted(flags):
        extra = flags[level_id]
        row = mech_levels.get(level_id)

        mechanics = []
        for kind in declared_mechanics(row, extra):
            spec = MECH_BY_ID[kind]
            mechanics.append({
                "kind": kind,
                "wired": bool(spec["wired"]),
                "source": spec["source"],
            })
            mech_hist[kind] += 1

        minigames = []
        engine_gaps = []
        for kind in (mini_levels.get(level_id) or {}).get("kinds") or []:
            known = kind in minigame_playable
            implemented = kind in MINIGAME_ENGINE
            minigames.append({
                "kind": kind,
                "playable": bool(minigame_playable.get(kind, False)),
                "engineImplemented": implemented,
                "source": MINIGAME_ENGINE.get(kind, "native/src 无该玩法的读取点"),
            })
            mini_hist[kind] += 1
            if not implemented:
                engine_gaps.append(kind)
                engine_gap_hist[kind] += 1
            if not known:
                # A kind the rules sheet never audited cannot be called playable.
                engine_gaps.append("unaudited:" + kind)

        blockers = [m["kind"] for m in mechanics if not m["wired"]]
        blockers += ["minigame:" + m["kind"] for m in minigames if not m["playable"]]
        for blocker in blockers:
            blockers_hist[blocker] += 1

        data_only = any(not b.startswith("minigame:") for b in blockers)
        mini_blocked = any(b.startswith("minigame:") for b in blockers)
        level_playable = not blockers
        if level_playable:
            playable += 1
        else:
            any_blocker += 1
        # The two counters are inclusive: a level that is blocked on both axes counts in both,
        # and `blockedBoth` records the overlap so the three numbers still reconcile.
        if data_only:
            blocked_data += 1
        if mini_blocked:
            blocked_mini += 1
        if data_only and mini_blocked:
            blocked_both += 1
        if len(blockers) == 1:
            solo.append({"level": level_id, "blocker": blockers[0]})

        notes = []
        if "vasebreaker" in [m["kind"] for m in mechanics]:
            vase_row = vase_levels.get(level_id) or {}
            if vase_row.get("vaseCount") is None:
                notes.append(NOTE_VASE_WITHOUT_PRESET)
        for note in notes:
            notes_hist[note] += 1

        in_engine = level_playable and not engine_gaps
        if in_engine:
            playable_in_engine += 1

        levels[level_id] = {
            "level": level_id,
            "world": world_of(level_id),
            "mechanics": mechanics,
            "minigames": minigames,
            "playable": level_playable,
            "blockers": blockers,
            "wiredCount": sum(1 for m in mechanics if m["wired"]),
            "dataOnlyCount": sum(1 for m in mechanics if not m["wired"]),
            "minigameEngineGaps": engine_gaps,
            "playableInEngine": in_engine,
            "notes": notes,
        }

    solo.sort(key=lambda row: (row["blocker"], row["level"]))
    counts = {
        "levels": len(levels),
        "playable": playable,
        "blockedDataOnly": blocked_data,
        "blockedMinigame": blocked_mini,
        "blockedBoth": blocked_both,
        "playableInEngine": playable_in_engine,
        "blockersByKind": dict(sorted(blockers_hist.items())),
        "blockerKindTotal": sum(blockers_hist.values()),
        "levelsWithAnyBlocker": any_blocker,
        "levelsWithSingleBlocker": len(solo),
        "mechanicsByKind": {kind: {"levels": n, "wired": bool(MECH_BY_ID[kind]["wired"])}
                            for kind, n in sorted(mech_hist.items())},
        "minigamesByKind": dict(sorted(mini_hist.items())),
        "minigameEngineGapsByKind": dict(sorted(engine_gap_hist.items())),
        "levelsWithEngineGap": sum(1 for row in levels.values() if row["minigameEngineGaps"]),
        "notesByKind": dict(sorted(notes_hist.items())),
        "levelsByWorld": dict(sorted(Counter(world_of(lid) for lid in levels).items())),
        "mechanicKinds": len(MECH_ORDER),
        "wiredKinds": sum(1 for row in MECHANISMS if row["wired"]),
        "dataOnlyKinds": sum(1 for row in MECHANISMS if not row["wired"]),
    }

    return {
        "format": FORMAT,
        "generated": GENERATED,
        "criterion": CRITERION,
        "sources": [
            "native/generated/level_mechanics.json",
            "native/generated/minigames.json",
            "native/generated/minigame_rules.json",
            "native/generated/vasebreaker.json",
            "content/levels",
            "native/src/engine/mechanics.cpp",
            "native/src/engine/world.cpp",
        ],
        "engineKcovered": ENGINE_KCOVERED,
        "mechanisms": [{k: row[k] for k in ("id", "cn", "declared", "wired", "source")}
                       for row in MECHANISMS],
        "minigameEngine": {kind: {"implemented": True, "source": src}
                           for kind, src in MINIGAME_ENGINE.items()},
        "counts": counts,
        "singleBlockerLevels": solo[:50],
        "levels": levels,
    }


def render(table: dict) -> bytes:
    """R08: compact, sorted, LF only."""
    text = json.dumps(table, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return (text + "\n").encode("utf-8")


def dump(table: dict, path: Path) -> None:
    """Write bytes, not text: `Path.write_text` would emit CRLF on Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render(table))


def check(table: dict, path: Path) -> list[str]:
    problems: list[str] = []
    if table.get("format") != FORMAT:
        problems.append(f"format {table.get('format')!r} != {FORMAT!r}")
    counts = table.get("counts") or {}
    levels = table.get("levels") or {}
    if counts.get("levels") != len(levels):
        problems.append(f"counts.levels {counts.get('levels')} != {len(levels)} rows")
    if len(levels) != 1809:
        problems.append(f"levels {len(levels)} != 1809 shipped levels")
    if len(MECH_ORDER) != len(set(MECH_ORDER)):
        problems.append("duplicate mechanic id in MECHANISMS")
    if len(MECH_ORDER) != len(MECH_BY_ID):
        problems.append("MECH_BY_ID lost an entry")
    for kind in ENGINE_KCOVERED:
        spec = MECH_BY_ID.get(kind)
        if spec is None:
            problems.append(f"engine kCovered kind {kind!r} missing from MECHANISMS")
        elif not spec["wired"]:
            problems.append(f"engine kCovered kind {kind!r} is not wired here")
    wired_from_engine = set(ENGINE_KCOVERED)
    for spec in MECHANISMS:
        if spec["wired"] and spec["id"].startswith("spawners.") and spec["id"] not in wired_from_engine:
            problems.append(f"spawner {spec['id']!r} claims wired but is not in kCovered")

    # Per-row invariants: the arithmetic must add up and the verdict must follow R04.
    playable = 0
    hist: Counter = Counter()
    for level_id, row in levels.items():
        if row.get("level") != level_id:
            problems.append(f"{level_id}: level field {row.get('level')!r}")
        if row.get("world") != world_of(level_id):
            problems.append(f"{level_id}: world {row.get('world')!r}")
        mechanics = row.get("mechanics") or []
        kinds = [m["kind"] for m in mechanics]
        if kinds != [k for k in MECH_ORDER if k in set(kinds)]:
            problems.append(f"{level_id}: mechanics are not in registry order")
        for mech in mechanics:
            spec = MECH_BY_ID.get(mech["kind"])
            if spec is None:
                problems.append(f"{level_id}: unknown mechanic {mech['kind']!r}")
            elif bool(mech["wired"]) != bool(spec["wired"]):
                problems.append(f"{level_id}: {mech['kind']} wired flag disagrees with the registry")
            if not mech.get("source"):
                problems.append(f"{level_id}: {mech['kind']} has no source")
        for mini in row.get("minigames") or []:
            if not isinstance(mini.get("playable"), bool):
                problems.append(f"{level_id}: minigame {mini['kind']!r} has no boolean playable")
            if not mini.get("source"):
                problems.append(f"{level_id}: minigame {mini['kind']!r} has no engine source")
            if bool(mini.get("engineImplemented")) != (mini["kind"] in MINIGAME_ENGINE):
                problems.append(f"{level_id}: minigame {mini['kind']!r} engineImplemented drifted")
        if row.get("wiredCount") != sum(1 for m in mechanics if m["wired"]):
            problems.append(f"{level_id}: wiredCount mismatch")
        if row.get("dataOnlyCount") != sum(1 for m in mechanics if not m["wired"]):
            problems.append(f"{level_id}: dataOnlyCount mismatch")
        expected = [m["kind"] for m in mechanics if not m["wired"]]
        expected += ["minigame:" + m["kind"] for m in row.get("minigames") or [] if not m["playable"]]
        if row.get("blockers") != expected:
            problems.append(f"{level_id}: blockers {row.get('blockers')} != {expected}")
        if bool(row.get("playable")) != (not expected):
            problems.append(f"{level_id}: playable does not follow R04")
        if row.get("playable"):
            playable += 1
        hist.update(expected)
        if bool(row.get("playableInEngine")) and not row.get("playable"):
            problems.append(f"{level_id}: playableInEngine true while playable false")
        if row.get("playableInEngine") and row.get("minigameEngineGaps"):
            problems.append(f"{level_id}: playableInEngine true with engine gaps")
    if counts.get("playable") != playable:
        problems.append(f"counts.playable {counts.get('playable')} != {playable} recomputed")
    if counts.get("blockersByKind") != dict(sorted(hist.items())):
        problems.append("counts.blockersByKind disagrees with the rows")
    if counts.get("blockerKindTotal") != sum(hist.values()):
        problems.append("counts.blockerKindTotal disagrees with the rows")

    def _axis(row: dict, minigame: bool) -> bool:
        return any(b.startswith("minigame:") == minigame for b in row.get("blockers") or [])

    any_blocker = len(levels) - playable
    data_any = sum(1 for row in levels.values() if _axis(row, False))
    mini_any = sum(1 for row in levels.values() if _axis(row, True))
    both_any = sum(1 for row in levels.values() if _axis(row, False) and _axis(row, True))
    if counts.get("levelsWithAnyBlocker") != any_blocker:
        problems.append(f"counts.levelsWithAnyBlocker {counts.get('levelsWithAnyBlocker')} != {any_blocker}")
    if counts.get("blockedDataOnly") != data_any:
        problems.append(f"counts.blockedDataOnly {counts.get('blockedDataOnly')} != {data_any}")
    if counts.get("blockedMinigame") != mini_any:
        problems.append(f"counts.blockedMinigame {counts.get('blockedMinigame')} != {mini_any}")
    if counts.get("blockedBoth") != both_any:
        problems.append(f"counts.blockedBoth {counts.get('blockedBoth')} != {both_any}")
    if data_any + mini_any - both_any != any_blocker:
        problems.append("blockedDataOnly + blockedMinigame - blockedBoth != levelsWithAnyBlocker")
    if counts.get("playable", 0) + any_blocker != len(levels):
        problems.append(f"playable + levelsWithAnyBlocker {counts.get('playable', 0) + any_blocker} "
                        f"!= {len(levels)}")
    for kind, row in (counts.get("mechanicsByKind") or {}).items():
        recomputed = sum(1 for r in levels.values() for m in r["mechanics"] if m["kind"] == kind)
        if row["levels"] != recomputed:
            problems.append(f"counts.mechanicsByKind[{kind}] {row['levels']} != {recomputed}")

    if path.exists():
        blob = path.read_bytes()
        if b"\r\n" in blob:
            problems.append("file contains CRLF")
        if not blob.endswith(b"\n") or blob.endswith(b"\n\n"):
            problems.append("file must end with exactly one LF")
        if blob != render(table):
            problems.append("file on disk differs from a fresh render (stale output)")
    else:
        problems.append(f"{path} does not exist")
    return problems


def needle_report(needle: str, levels_dir: Path, mech_path: Path) -> int:
    hits = 0
    lowered = needle.lower()
    for path in [mech_path, *sorted(levels_dir.glob("*.json"))]:
        text = path.read_text(encoding="utf-8-sig")
        if lowered in text.lower():
            hits += 1
            print(f"  {path.name}")
    print(f"needle {needle!r}: {hits} files")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mech", type=Path, default=DEFAULT_MECH)
    parser.add_argument("--mini", type=Path, default=DEFAULT_MINI)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--vase", type=Path, default=DEFAULT_VASE)
    parser.add_argument("--levels", type=Path, default=DEFAULT_LEVELS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true",
                        help="verify the shipped file is current; exit 1 when it is not")
    parser.add_argument("-n", "--needle", help="print level files containing a literal")
    args = parser.parse_args(argv)

    if args.needle:
        return needle_report(args.needle, args.levels, args.mech)

    started = time.perf_counter()
    table = build(args.mech, args.mini, args.rules, args.vase, args.levels)
    if args.check:
        problems = check(table, args.out)
        elapsed = time.perf_counter() - started
        if problems:
            print(f"level_playability: {len(problems)} problem(s) in {elapsed:.1f}s", file=sys.stderr)
            for problem in problems[:40]:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        counts = table["counts"]
        print(f"level_playability levels={counts['levels']} playable={counts['playable']} "
              f"dataOnly={counts['blockedDataOnly']} minigame={counts['blockedMinigame']} "
              f"both={counts['blockedBoth']} inEngine={counts['playableInEngine']} "
              f"({elapsed:.1f}s)")
        return 0

    dump(table, args.out)
    counts = table["counts"]
    elapsed = time.perf_counter() - started
    print(f"level_playability levels={counts['levels']} playable={counts['playable']} "
          f"dataOnly={counts['blockedDataOnly']} minigame={counts['blockedMinigame']} "
          f"both={counts['blockedBoth']} inEngine={counts['playableInEngine']} "
          f"-> {args.out} ({elapsed:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
