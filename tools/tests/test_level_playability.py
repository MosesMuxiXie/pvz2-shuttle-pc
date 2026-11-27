"""Tests for tools/contentc/level_playability.py — the A6 per-level ledger.

Two groups:

* `ShippedLedgerTests` only reads `native/generated/level_playability.json` plus the three
  generated sheets it derives from, so it runs on a box with no OBB: the shipped ledger must
  be complete, self-consistent, and agree with the engine's own `kCovered` list.
* `CompileLedgerTests` rebuilds from the same inputs: the shipped bytes must equal a fresh
  render, `--check` must be idempotent, and a stale or missing file must be rejected.

Every number here was measured against the 460.9 content tree (see
docs/reviews/2026-11-26-level-playability.md). A change means the data or the口径 moved, not
just the formatting.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from contentc import level_playability  # noqa: E402

SHIPPED = level_playability.DEFAULT_OUT

# Measured on the 460.9 tree; see the review doc's §2 table.
EXPECTED_MECHANICS = {
    "boardGrid": 49,
    "boss": 71,
    "conveyor": 350,
    "events.frost": 64,
    "events.strength": 60,
    "events.tide": 60,
    "initialGridItems": 466,
    "initialPlants": 249,
    "minecarts": 190,
    "mutators": 21,
    "night": 187,
    "protectThePlant": 286,
    "rail": 192,
    "suppressFlagZombie": 215,
    "vasebreaker": 47,
}

EXPECTED_SPAWNERS = {
    "spawners.beach": 82,
    "spawners.dino": 93,
    "spawners.fish": 26,
    "spawners.gravestone": 353,
    "spawners.grid": 237,
    "spawners.ground": 100,
    "spawners.jittered": 1615,
    "spawners.portal": 130,
    "spawners.spider": 118,
    "spawners.storm": 119,
}

EXPECTED_BLOCKERS = {
    "boardGrid": 49,
    "events.frost": 64,
    "events.strength": 60,
    "events.tide": 60,
    "minigame:column": 8,
    "minigame:invisighoul": 8,
    "mutators": 21,
    "night": 187,
    "spawners.spider": 118,
}


def load() -> dict:
    with SHIPPED.open(encoding="utf-8") as handle:
        return json.load(handle)


def expected_blockers(row: dict) -> list[str]:
    out = [m["kind"] for m in row["mechanics"] if not m["wired"]]
    out += ["minigame:" + m["kind"] for m in row["minigames"] if not m["playable"]]
    return out


class ShippedLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.table = load()
        self.levels = self.table["levels"]
        self.counts = self.table["counts"]

    def test_top_level_shape(self) -> None:
        for key in ("format", "generated", "criterion", "sources", "engineKcovered",
                    "mechanisms", "minigameEngine", "counts", "singleBlockerLevels", "levels"):
            self.assertIn(key, self.table)
        self.assertEqual(self.table["format"], "pvz2-shuttle/level-playability@1")
        self.assertEqual(self.table["generated"], "2026-11-26")
        self.assertIn("data-only", self.table["criterion"])
        self.assertEqual(len(self.levels), 1809)

    def test_counts_reconcile_to_the_row_set(self) -> None:
        counts = self.counts
        self.assertEqual(counts["levels"], 1809)
        self.assertEqual(counts["playable"], 1340)
        # blockedDataOnly / blockedMinigame are inclusive; blockedBoth is their overlap.
        self.assertEqual(counts["blockedDataOnly"], 454)
        self.assertEqual(counts["blockedMinigame"], 16)
        self.assertEqual(counts["blockedBoth"], 1)
        self.assertEqual(counts["blockedDataOnly"] + counts["blockedMinigame"]
                         - counts["blockedBoth"], counts["levelsWithAnyBlocker"])
        self.assertEqual(counts["playable"] + counts["levelsWithAnyBlocker"], counts["levels"])
        playable = sum(1 for row in self.levels.values() if row["playable"])
        self.assertEqual(playable, counts["playable"])
        self.assertEqual(counts["levelsWithAnyBlocker"], 469)
        self.assertEqual(counts["blockerKindTotal"], sum(counts["blockersByKind"].values()))
        blocks = sum(len(row["blockers"]) for row in self.levels.values())
        self.assertEqual(blocks, counts["blockerKindTotal"])

    def test_every_row_follows_the_criterion(self) -> None:
        for level, row in self.levels.items():
            with self.subTest(level=level):
                self.assertEqual(row["level"], level)
                self.assertEqual(row["world"], level.rsplit("_", 1)[0])
                self.assertEqual(row["wiredCount"],
                                 sum(1 for m in row["mechanics"] if m["wired"]))
                self.assertEqual(row["dataOnlyCount"],
                                 sum(1 for m in row["mechanics"] if not m["wired"]))
                self.assertEqual(row["blockers"], expected_blockers(row))
                self.assertEqual(row["playable"], not row["blockers"])
                for mech in row["mechanics"]:
                    self.assertTrue(mech["source"], msg=f"{level}: {mech['kind']} has no citation")

    def test_mechanics_are_in_registry_order(self) -> None:
        order = level_playability.MECH_ORDER
        for level, row in self.levels.items():
            kinds = [m["kind"] for m in row["mechanics"]]
            with self.subTest(level=level):
                self.assertEqual(kinds, [k for k in order if k in set(kinds)])

    def test_mechanics_by_kind_matches_the_measured_table(self) -> None:
        measured = {kind: row["levels"] for kind, row in self.counts["mechanicsByKind"].items()}
        spawners = {kind: n for kind, n in measured.items() if kind.startswith("spawners.")}
        others = {kind: n for kind, n in measured.items() if not kind.startswith("spawners.")}
        self.assertEqual(others, EXPECTED_MECHANICS)
        self.assertEqual(spawners, EXPECTED_SPAWNERS)
        # The per-row list has to agree with the aggregate.
        actual = Counter(m["kind"] for row in self.levels.values() for m in row["mechanics"])
        self.assertEqual(dict(sorted(actual.items())),
                         {k: v["levels"] for k, v in self.counts["mechanicsByKind"].items()})

    def test_conveyor_levels_are_wired(self) -> None:
        conveyor = [row for row in self.levels.values()
                    if any(m["kind"] == "conveyor" for m in row["mechanics"])]
        self.assertEqual(len(conveyor), 350)
        for row in conveyor:
            with self.subTest(level=row["level"]):
                entry = next(m for m in row["mechanics"] if m["kind"] == "conveyor")
                self.assertTrue(entry["wired"])
                self.assertIn("world.cpp:825", entry["source"])
                self.assertNotIn("conveyor", row["blockers"])
        self.assertTrue(self.counts["mechanicsByKind"]["conveyor"]["wired"])

    def test_column_and_invisighoul_levels_are_blocked(self) -> None:
        blocked = {kind: [] for kind in ("column", "invisighoul")}
        for level, row in self.levels.items():
            for mini in row["minigames"]:
                if mini["kind"] in blocked and not mini["playable"]:
                    blocked[mini["kind"]].append(level)
        self.assertEqual(len(blocked["column"]), 8)
        self.assertEqual(len(blocked["invisighoul"]), 8)
        for kind, ids in blocked.items():
            for level in ids:
                row = self.levels[level]
                with self.subTest(level=level):
                    self.assertFalse(row["playable"])
                    self.assertIn("minigame:" + kind, row["blockers"])
        self.assertEqual(self.counts["blockersByKind"]["minigame:column"], 8)
        self.assertEqual(self.counts["blockersByKind"]["minigame:invisighoul"], 8)

    def test_one_level_is_blocked_by_both_halves(self) -> None:
        both = [row["level"] for row in self.levels.values()
                if any(not b.startswith("minigame:") for b in row["blockers"])
                and any(b.startswith("minigame:") for b in row["blockers"])]
        self.assertEqual(len(both), 1)
        self.assertEqual(self.counts["blockedBoth"], 1)

    def test_blockers_by_kind_matches_the_measured_histogram(self) -> None:
        self.assertEqual(self.counts["blockersByKind"], EXPECTED_BLOCKERS)
        recomputed = Counter(b for row in self.levels.values() for b in row["blockers"])
        self.assertEqual(dict(sorted(recomputed.items())), EXPECTED_BLOCKERS)

    def test_night_is_a_data_only_mechanic(self) -> None:
        night = [row for row in self.levels.values()
                 if any(m["kind"] == "night" for m in row["mechanics"])]
        self.assertEqual(len(night), 187)
        for row in night:
            entry = next(m for m in row["mechanics"] if m["kind"] == "night")
            self.assertFalse(entry["wired"])
            self.assertIn("world.cpp:355", entry["source"])
            self.assertIn("night", row["blockers"])

    def test_registry_agrees_with_the_engine_kcovered_list(self) -> None:
        covered = self.table["engineKcovered"]
        self.assertEqual(len(covered), 13)
        for kind in covered:
            spec = level_playability.MECH_BY_ID[kind]
            self.assertTrue(spec["wired"], msg=kind)
        spider = level_playability.MECH_BY_ID["spawners.spider"]
        self.assertFalse(spider["wired"])
        self.assertIn("mechanics.cpp:488", spider["source"])
        self.assertEqual(self.counts["wiredKinds"], 18)
        self.assertEqual(self.counts["dataOnlyKinds"], 7)
        self.assertEqual(self.counts["mechanicKinds"], 25)

    def test_boss_rail_vasebreaker_and_flag_suppression_are_wired(self) -> None:
        for kind, levels in (("boss", 71), ("rail", 192), ("vasebreaker", 47),
                             ("suppressFlagZombie", 215), ("minecarts", 190)):
            with self.subTest(kind=kind):
                rows = [row for row in self.levels.values()
                        if any(m["kind"] == kind for m in row["mechanics"])]
                self.assertEqual(len(rows), levels)
                self.assertTrue(self.counts["mechanicsByKind"][kind]["wired"])
                for row in rows:
                    self.assertNotIn(kind, row["blockers"])

    def test_vasebreaker_level_without_a_preset_is_noted(self) -> None:
        row = self.levels["frontyard_166"]
        self.assertIn("vasebreaker", [m["kind"] for m in row["mechanics"]])
        self.assertEqual(row["notes"], ["vasebreaker-flag-without-preset"])
        self.assertEqual(self.counts["notesByKind"], {"vasebreaker-flag-without-preset": 1})
        noted = [r["level"] for r in self.levels.values() if r["notes"]]
        self.assertEqual(noted, ["frontyard_166"])

    def test_minigame_rows_say_whether_the_engine_implements_the_mode(self) -> None:
        implemented = set(self.table["minigameEngine"])
        self.assertEqual(implemented, {"vasebreaker", "rail", "conveyor", "protecttheplant"})
        for level, row in self.levels.items():
            for mini in row["minigames"]:
                with self.subTest(level=level, kind=mini["kind"]):
                    self.assertEqual(mini["engineImplemented"], mini["kind"] in implemented)
                    self.assertTrue(mini["source"])
                    self.assertEqual(mini["kind"] in row["minigameEngineGaps"],
                                     not mini["engineImplemented"])
        gap_kinds = self.counts["minigameEngineGapsByKind"]
        self.assertEqual(len(gap_kinds), 16)
        self.assertEqual(gap_kinds["laststand"], 73)
        self.assertEqual(gap_kinds["tide"], 77)
        self.assertEqual(self.counts["levelsWithEngineGap"], 232)

    def test_playable_in_engine_is_stricter_than_playable(self) -> None:
        self.assertEqual(self.counts["playableInEngine"], 1225)
        for level, row in self.levels.items():
            with self.subTest(level=level):
                if row["playableInEngine"]:
                    self.assertTrue(row["playable"])
                    self.assertEqual(row["minigameEngineGaps"], [])
                self.assertEqual(row["playableInEngine"],
                                 row["playable"] and not row["minigameEngineGaps"])

    def test_single_blocker_list_is_capped_sorted_and_consistent(self) -> None:
        rows = self.table["singleBlockerLevels"]
        self.assertEqual(len(rows), 50)
        self.assertEqual(self.counts["levelsWithSingleBlocker"], 373)
        keys = [(row["blocker"], row["level"]) for row in rows]
        self.assertEqual(keys, sorted(keys))
        for row in rows:
            with self.subTest(level=row["level"]):
                self.assertEqual(self.levels[row["level"]]["blockers"], [row["blocker"]])
        singles = [r for r in self.levels.values() if len(r["blockers"]) == 1]
        self.assertEqual(len(singles), 373)

    def test_render_is_compact_sorted_and_lf_only(self) -> None:
        blob = level_playability.render(self.table)
        self.assertNotIn(b"\r\n", blob)
        self.assertTrue(blob.endswith(b"}\n"))
        self.assertFalse(blob.endswith(b"\n\n"))
        self.assertNotIn(b'", "', blob)  # compact separators, not the pretty printer
        first = json.loads(blob)
        self.assertEqual(first["counts"], self.counts)


class CompileLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.table = level_playability.build(
            level_playability.DEFAULT_MECH,
            level_playability.DEFAULT_MINI,
            level_playability.DEFAULT_RULES,
            level_playability.DEFAULT_VASE,
            level_playability.DEFAULT_LEVELS,
        )

    def test_shipped_bytes_equal_a_fresh_build(self) -> None:
        self.assertEqual(level_playability.render(self.table), SHIPPED.read_bytes())

    def test_check_is_idempotent(self) -> None:
        self.assertEqual(level_playability.check(self.table, SHIPPED), [])

    def test_two_builds_are_byte_identical(self) -> None:
        again = level_playability.build(
            level_playability.DEFAULT_MECH,
            level_playability.DEFAULT_MINI,
            level_playability.DEFAULT_RULES,
            level_playability.DEFAULT_VASE,
            level_playability.DEFAULT_LEVELS,
        )
        self.assertEqual(level_playability.render(again), level_playability.render(self.table))

    def test_stale_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "level_playability.json"
            stale.write_bytes(level_playability.render(self.table).replace(
                b'"playable":true', b'"playable":false', 1))
            problems = level_playability.check(self.table, stale)
            self.assertTrue(any("stale" in p for p in problems), msg=problems)

    def test_missing_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.json"
            problems = level_playability.check(self.table, missing)
            self.assertTrue(any("does not exist" in p for p in problems), msg=problems)

    def test_crlf_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            crlf = Path(tmp) / "level_playability.json"
            crlf.write_bytes(level_playability.render(self.table).replace(b"\n", b"\r\n"))
            problems = level_playability.check(self.table, crlf)
            self.assertTrue(any("CRLF" in p for p in problems), msg=problems)


if __name__ == "__main__":
    unittest.main()
