"""Pins the derived board geometry to the shipped sheets and to the generated table.

The numbers come from `pkg_*_LevelDefinition.json` (level grid coordinates and
the six-lane module's full-lawn placement list); see `tools/contentc/geometry.py`
for the derivation rules. If a future extract moves them, the test fails instead
of the table silently drifting.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import contentc.geometry as geometry  # noqa: E402
import contentc.worlds as worlds  # noqa: E402

OBB = worlds.DEFAULT_OBB
CONTENT = worlds.DEFAULT_CONTENT
GENERATED = geometry.DEFAULT_OUT
CLIENT_WORLDS = [world.id for world in worlds.load_content_worlds(CONTENT)]

HAS_SHEETS = OBB.is_dir()


class DecideTests(unittest.TestCase):
    """Priority: level rectangle > six-lane module > six-lane stage > baseline."""

    @staticmethod
    def level(**kwargs) -> geometry.LevelFacts:
        payload = {
            "package": "pkg_0001_LevelDefinition",
            "stage": "EgyptStage",
            "sixlane": False,
            "cell_x": 8,
            "cell_y": 4,
            "sentinels": 0,
            "rect": None,
        }
        payload.update(kwargs)
        return geometry.LevelFacts(**payload)

    def test_no_levels_is_an_honest_fallback(self):
        rows, cols, source = geometry.decide([])
        self.assertEqual((rows, cols), (5, 9))
        self.assertIn("fallback=5x9-default", source)

    def test_baseline_is_five_by_nine(self):
        rows, cols, source = geometry.decide([self.level()])
        self.assertEqual((rows, cols), (5, 9))
        self.assertIn("GridX 0..8", source)
        self.assertIn("GridY 0..4", source)

    def test_six_lane_module_wins_over_baseline(self):
        rows, cols, source = geometry.decide(
            [self.level(), self.level(stage="SixLaneFogStage", sixlane=True)]
        )
        self.assertEqual((rows, cols), (6, 9))
        self.assertIn(geometry.SIXLANE_MODULE, source)

    def test_full_lawn_rectangle_beats_a_six_lane_module(self):
        rows, cols, source = geometry.decide(
            [
                self.level(stage="SixLaneFogStage", sixlane=True),
                self.level(package="pkg_0406_LevelDefinition", rect=(6, 9, 54)),
            ]
        )
        self.assertEqual((rows, cols), (6, 9))
        self.assertIn("tiles the whole lawn", source)
        self.assertIn("54 cells", source)

    def test_six_lane_stage_without_placements_still_means_six_rows(self):
        rows, cols, source = geometry.decide(
            [self.level(stage="SixLaneHonkaiStage", cell_x=-1, cell_y=-1)]
        )
        self.assertEqual((rows, cols), (6, 9))
        self.assertIn("six-lane stage family", source)

    def test_off_board_sentinels_do_not_enlarge_the_lawn(self):
        rows, cols, source = geometry.decide([self.level(sentinels=42)])
        self.assertEqual((rows, cols), (5, 9))
        self.assertIn("42 off-board sentinels", source)


@unittest.skipUnless(HAS_SHEETS, "original sheets are not extracted next to the repo")
class BoardSizeTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.board_sizes, cls.notes = geometry.build(OBB, CONTENT)

    def test_every_client_world_has_a_size(self):
        self.assertEqual(len(CLIENT_WORLDS), 26)
        self.assertEqual(list(self.board_sizes), CLIENT_WORLDS)
        for world_id, entry in self.board_sizes.items():
            self.assertEqual(sorted(entry), ["cols", "rows", "source"], world_id)
            self.assertIsInstance(entry["rows"], int)
            self.assertIsInstance(entry["cols"], int)
            self.assertTrue(entry["source"].strip())
            self.assertIn("obb=", entry["source"])

    def test_sizes_are_real_lawn_shapes(self):
        for world_id, entry in self.board_sizes.items():
            self.assertIn(entry["rows"], (5, 6), world_id)
            self.assertIn(entry["cols"], (9, 10), world_id)

    def test_frontyard_is_the_five_by_nine_home_lawn(self):
        frontyard = self.board_sizes["frontyard"]
        self.assertEqual((frontyard["rows"], frontyard["cols"]), (5, 9))

    def test_at_least_one_world_is_six_lanes(self):
        wide = {
            world_id: entry
            for world_id, entry in self.board_sizes.items()
            if (entry["rows"], entry["cols"]) in ((6, 10), (6, 9))
        }
        self.assertTrue(wide, "no six-lane world was derived")
        self.assertIn("beach", wide)
        self.assertIn("modern", wide)
        for world_id in ("beach", "modern"):
            self.assertEqual(wide[world_id]["rows"], 6, world_id)
            self.assertIn(geometry.SIXLANE_MODULE, wide[world_id]["source"])

    def test_evidence_is_measured_not_invented(self):
        kinds = {"tiles the whole lawn", geometry.SIXLANE_MODULE, "six-lane stage family"}
        for world_id, entry in self.board_sizes.items():
            source = entry["source"]
            if "fallback=" in source:
                # A fallback keeps the default shape and says so out loud.
                self.assertEqual((entry["rows"], entry["cols"]), (5, 9), world_id)
                continue
            self.assertTrue(
                any(kind in source for kind in kinds) or "level grid" in source,
                "%s has no measurable source: %s" % (world_id, source),
            )

    def test_fallbacks_are_reported(self):
        fallbacks = [
            world_id
            for world_id, entry in self.board_sizes.items()
            if "fallback=" in entry["source"]
        ]
        # The two worlds the sheets really do not cover are named, not hidden.
        self.assertEqual(fallbacks, ["memorytour", "muji"])
        text = geometry.report(self.board_sizes, self.notes)
        self.assertIn("fallback=%s" % ",".join(fallbacks), text)

    def test_stage_mapping_stays_inside_the_client_worlds(self):
        self.assertGreater(self.notes.levels, 1800)
        for world_id, _prefixes in geometry.STAGE_WORLDS:
            self.assertIn(world_id, CLIENT_WORLDS)

    def test_six_lane_stages_map_to_their_own_worlds(self):
        # beach stages must be resolved before the generic `SixLane` modern rule.
        self.assertEqual(geometry.world_of_stage("SixLanePoolStage"), "beach")
        self.assertEqual(geometry.world_of_stage("SixLaneFogStage"), "beach")
        self.assertEqual(geometry.world_of_stage("SixLaneStage"), "modern")
        self.assertEqual(geometry.world_of_stage("SixLaneHonkaiStage"), "modern")
        self.assertEqual(geometry.world_of_stage("EgyptStage"), "egypt")
        # Event-only stages have no client world and must not be folded in.
        self.assertIsNone(geometry.world_of_stage("RiftStage"))
        self.assertIsNone(geometry.world_of_stage("ChildStage"))


@unittest.skipUnless(HAS_SHEETS, "original sheets are not extracted next to the repo")
class GenerationTests(unittest.TestCase):
    def test_generation_is_byte_stable(self):
        first, _ = geometry.build(OBB, CONTENT)
        second, _ = geometry.build(OBB, CONTENT)
        self.assertEqual(geometry.render(first), geometry.render(second))

    def test_cli_writes_identical_files_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_a = Path(tmp) / "a.json"
            out_b = Path(tmp) / "b.json"
            for out in (out_a, out_b):
                result = subprocess.run(
                    [sys.executable, str(TOOLS / "contentc" / "geometry.py"), "--out", str(out)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(out_a.read_bytes(), out_b.read_bytes())

    def test_generated_file_matches_a_fresh_build(self):
        self.assertTrue(GENERATED.is_file(), "run: python tools/contentc/geometry.py")
        board_sizes, _ = geometry.build(OBB, CONTENT)
        self.assertEqual(GENERATED.read_text(encoding="utf-8"), geometry.render(board_sizes))
        payload = json.loads(GENERATED.read_text(encoding="utf-8"))
        self.assertEqual(sorted(payload), sorted(CLIENT_WORLDS))


if __name__ == "__main__":
    unittest.main()
