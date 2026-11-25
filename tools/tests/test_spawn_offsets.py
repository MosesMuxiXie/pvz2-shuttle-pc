"""Tests for `tools/contentc/spawn_offsets.py` and the shipped `spawn_offsets.json`.

Three groups:

* `ShippedSpawnOffsetTests` reads `native/generated/spawn_offsets.json` and pins the
  facts the engine will consume: 487 converted rows over 224 plants, the three
  samples (pea 35/-32, corn 15/-95, sun 0/-52), the derived cell scale
  (100 x 116 px against the engine's 60), the negative-is-up convention with its
  seven small positive rows, and the offset that is a sentinel rather than a point.
* `DerivationTests` re-checks every row arithmetically (`xCols == xPx / 100`,
  `yCols == yPx / 116`), so a hand-edited row cannot slip through, and pins the
  deep drop-in offsets (-600 / -1000 px) as intentional, not garbage.
* `CompileTests` rebuilds from the OBB and demands the shipped file be exactly a
  fresh render (byte for byte, LF only), that `--check` accepts it, and that a stale
  artifact is rejected.  The doc search that shows `docs/` never states "100x116"
  also lives here, because the report's honesty depends on it.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from tools.contentc import spawn_offsets, worlds

REPO = worlds.REPO
SHIPPED = REPO / "native/generated/spawn_offsets.json"
REPORT = REPO / "docs/reviews/2026-11-24-spawn-offsets.md"
PLANT_SHEET = Path(worlds.DEFAULT_OBB) / spawn_offsets.DEFAULT_PLANT_SHEET if worlds.DEFAULT_OBB else None

#: the three samples the task names, with their pack pixels and converted cells
SAMPLES = {
    "PeashooterDefault": {"kind": "shot", "xPx": 35, "yPx": -32, "xCols": 0.35, "yCols": -0.2759},
    "KernelpultDefault": {"kind": "shot", "xPx": 15, "yPx": -95, "xCols": 0.15, "yCols": -0.819},
    "SunflowerDefault": {"kind": "sun", "xPx": 0, "yPx": -52, "xCols": 0.0, "yCols": -0.4483},
}

#: every offset that is positive; all are small muzzle nudges, not downward shots
POSITIVE_Y = {
    ("PowerVineDefault", 0): 14,
    ("WitchHazelDefault", 0): 22,
    ("WitchHazelDefault", 1): 22,
    ("XShotBarrageDefault", 1): 30,
    ("XShotBarrageDefault", 2): 30,
    ("XShotDefault", 1): 30,
    ("XShotDefault", 2): 30,
}


def _load() -> dict:
    return json.loads(SHIPPED.read_text(encoding="utf-8"))


def _rows_by_plant(table: dict) -> dict:
    out: dict[str, list] = {}
    for row in table["rows"]:
        out.setdefault(row["plant"], []).append(row)
    return out


class ShippedSpawnOffsetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = _load()

    def test_format_and_generator(self) -> None:
        self.assertEqual(sorted(self.table), [
            "counts", "defaults", "format", "generated", "generatedAt",
            "positiveY", "rows", "samples", "scale", "skipped", "ySign",
        ])
        self.assertEqual(self.table["format"], 1)
        self.assertEqual(self.table["generated"], "spawn-offsets-v1")
        # C58: generatedAt is a content stamp, so re-extracting the same OBB cannot churn it
        self.assertRegex(self.table["generatedAt"], r"^sha256:[0-9a-f]{16}$")
        self.assertEqual(self.table["generatedAt"], spawn_offsets.generated_stamp(PLANT_SHEET))

    def test_counts_match_the_sheet(self) -> None:
        counts = self.table["counts"]
        self.assertEqual(len(self.table["rows"]), 487)
        self.assertEqual(counts["rows"], 487)
        self.assertEqual(counts["plants"], 224)
        self.assertEqual(counts["actionsTotal"], 727)
        self.assertEqual(counts["actionsWithSpawnOffset"], 488)
        self.assertEqual(counts["skippedOffsets"], 1)
        self.assertEqual(counts["rows"] + counts["skippedOffsets"], counts["actionsWithSpawnOffset"])
        self.assertEqual(sum(counts["byKind"].values()), counts["actionsWithSpawnOffset"])
        self.assertEqual(counts["byKind"]["shot"], 386)
        self.assertEqual(counts["byKind"]["sun"], 18)

    def test_three_samples(self) -> None:
        by_plant = _rows_by_plant(self.table)
        for name, expected in SAMPLES.items():
            with self.subTest(plant=name):
                rows = [row for row in by_plant[name] if row["kind"] == expected["kind"]]
                self.assertTrue(rows, "%s: no %s action" % (name, expected["kind"]))
                first = rows[0]
                self.assertEqual(first["xPx"], expected["xPx"])
                self.assertEqual(first["yPx"], expected["yPx"])
                self.assertAlmostEqual(first["xCols"], expected["xCols"], places=4)
                self.assertAlmostEqual(first["yCols"], expected["yCols"], places=4)
                self.assertTrue(first["source"].endswith(".SpawnOffset"))
                self.assertTrue(first["source"].startswith(spawn_offsets.DEFAULT_PLANT_SHEET))
        # the sampled block is the same data, so the report cannot drift from the rows
        for name in SAMPLES:
            self.assertIn(name, self.table["samples"])
            self.assertEqual(self.table["samples"][name], by_plant[name])

    def test_scale_is_the_art_cell_not_the_engine_constant(self) -> None:
        scale = self.table["scale"]
        self.assertEqual(scale["pxPerColumn"], 100.0)
        self.assertEqual(scale["pxPerRow"], 116.0)
        self.assertEqual(scale["pxPerRowCols"], scale["pxPerRow"])
        # the pivot the cell size was read from, and the engine constant kept aside
        self.assertEqual(scale["artCenter"]["pivot"], {"x": 99.0, "y": 115.0})
        self.assertEqual(scale["enginePxPerColumn"], 60.0)
        self.assertAlmostEqual(scale["pxPerColumnRatioToEngine"], 100.0 / 60.0, places=6)
        self.assertIn("action_runner.cpp:14", scale["engineSource"])
        self.assertGreaterEqual(scale["artCenter"]["samples"], 300)

    def test_sign_convention_is_negative_up(self) -> None:
        counts = self.table["counts"]
        self.assertEqual(self.table["ySign"]["convention"], "negative-is-up")
        self.assertEqual(counts["yNegativeRows"] + counts["yPositiveRows"], counts["rows"])
        self.assertEqual(counts["yNegativeRows"], 480)
        self.assertEqual(counts["yPositiveRows"], 7)
        self.assertEqual(counts["yMedianPx"], -32)
        self.assertEqual(counts["yMinPx"], -1000)
        self.assertEqual(counts["yMaxPx"], 30)
        positive = {(row["plant"], row["actionIndex"]): row["yPx"]
                    for row in self.table["positiveY"]}
        self.assertEqual(positive, POSITIVE_Y)

    def test_sentinel_offset_is_named_not_converted(self) -> None:
        skipped = self.table["skipped"]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["plant"], "FlowerPotDefault")
        self.assertEqual(skipped[0]["actionIndex"], 0)
        self.assertEqual(skipped[0]["xPx"], 10000)
        self.assertEqual(skipped[0]["reason"], "offset-sentinel")
        # no row may carry the sentinel; the plant's *other* action is legitimate
        self.assertLess(max(abs(row["xPx"]) for row in self.table["rows"]),
                        spawn_offsets.OFFSET_LIMIT)
        kept = [row for row in self.table["rows"] if row["plant"] == "FlowerPotDefault"]
        self.assertEqual([row["actionIndex"] for row in kept], [1])
        self.assertEqual(kept[0]["yPx"], -64)

    def test_defaults_keep_todays_engine_behaviour(self) -> None:
        defaults = self.table["defaults"]
        self.assertEqual(defaults["shotYCols"], 0.0)
        self.assertEqual(defaults["sunYCols"], 0.0)
        # 0.35 is exactly the peashooter's 35 px over a 100 px column
        self.assertEqual(defaults["shotXCols"], 0.35)
        self.assertAlmostEqual(defaults["shotXCols"],
                               SAMPLES["PeashooterDefault"]["xPx"] / self.table["scale"]["pxPerColumn"],
                               places=6)


class DerivationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = _load()

    def test_every_row_re_derives_from_its_pixels(self) -> None:
        px_col = self.table["scale"]["pxPerColumn"]
        px_row = self.table["scale"]["pxPerRow"]
        for row in self.table["rows"]:
            with self.subTest(plant=row["plant"], action=row["actionIndex"]):
                self.assertAlmostEqual(row["xCols"], round(row["xPx"] / px_col, 4), places=9)
                self.assertAlmostEqual(row["yCols"], round(row["yPx"] / px_row, 4), places=9)
                self.assertIn(row["kind"], spawn_offsets.KINDS)
                self.assertTrue(row["source"].endswith(
                    "%s.Actions[%d].SpawnOffset" % (row["plant"], row["actionIndex"])))

    def test_rows_are_sorted_by_plant_then_action(self) -> None:
        keys = [(row["plant"], row["actionIndex"]) for row in self.table["rows"]]
        self.assertEqual(keys, sorted(keys))

    def test_deep_offsets_are_kept_as_drop_in_points(self) -> None:
        by_plant = _rows_by_plant(self.table)
        for name in ("BananaDefault", "CobCannonDefault", "GuardShroomDefault"):
            with self.subTest(plant=name):
                self.assertEqual(by_plant[name][0]["yPx"], -600)
                self.assertAlmostEqual(by_plant[name][0]["yCols"], round(-600 / 116.0, 4), places=4)
        dandelion = by_plant["DandelionDefault"]
        deep = [row for row in dandelion if row["yPx"] == -1000]
        self.assertEqual(len(deep), 1)
        self.assertLess(deep[0]["yCols"], -8.0)
        # negative y means "up", so a -600 px offset is 5+ cells above the plant
        self.assertLess(by_plant["BananaDefault"][0]["yCols"], -5.0)

    def test_artifact_is_lf_only_and_has_no_blank_lines(self) -> None:
        raw = SHIPPED.read_bytes()
        self.assertNotIn(b"\r\n", raw)
        self.assertTrue(raw.endswith(b"\n"))
        text = raw.decode("utf-8")
        self.assertNotIn("\n\n", text)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         hashlib.sha256(spawn_offsets.render(self.table).encode("utf-8")).hexdigest())

    def test_report_states_the_evidence_and_the_uncertainties(self) -> None:
        text = REPORT.read_text(encoding="utf-8")
        for needle in ("PeashooterDefault", "KernelpultDefault", "SunflowerDefault",
                       "ArtCenter", "kPixelsPerColumn", "×", "负值向上",
                       "不确定项", "0.35", "116"):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)
        # the report has to say out loud that docs/ never claims the cell size
        self.assertIn("不存在", text)


class CompileTests(unittest.TestCase):
    def test_docs_and_artifact_agree_on_the_cell_size(self) -> None:
        # This test used to assert the opposite ("no doc ever states 100x116") because that claim
        # was the honest state before 2026-11-24: the number existed only in this table. The table
        # now has a written home in docs/COMPLETENESS.md §2.25, so the invariant is agreement, not
        # absence — and the grep still proves the number is not scattered around unverifiably.
        found = spawn_offsets.grep_cell(REPO, exclude=REPORT)
        self.assertGreaterEqual(found["files"], 30)
        table = _load()
        self.assertEqual(table["scale"]["pxPerColumn"], 100)
        self.assertEqual(table["scale"]["pxPerRow"], 116)
        doc = (REPO / "docs" / "COMPLETENESS.md").read_text(encoding="utf-8")
        self.assertIn("100×116", doc)
        self.assertIn("ArtCenter", doc)

    def test_check_accepts_the_shipped_artifact(self) -> None:
        table = _load()
        self.assertEqual(spawn_offsets.check(table, SHIPPED), 0)

    def test_check_rejects_a_stale_artifact(self) -> None:
        table = _load()
        table["rows"] = table["rows"][:-1]
        self.assertEqual(spawn_offsets.check(table, SHIPPED), 1)

    def test_check_rejects_a_wrong_conversion(self) -> None:
        table = _load()
        table["rows"][0] = dict(table["rows"][0], yCols=999.0)
        self.assertEqual(spawn_offsets.check(table, SHIPPED), 1)

    def test_artifact_renders_identically(self) -> None:
        table = _load()
        first = spawn_offsets.render(table)
        second = spawn_offsets.render(_load())
        self.assertEqual(first, second)
        self.assertEqual(hashlib.sha256(first.encode("utf-8")).hexdigest(),
                         hashlib.sha256(SHIPPED.read_bytes()).hexdigest())

    def test_cli_check_exits_zero(self) -> None:
        root = Path(__file__).resolve().parents[2]
        done = subprocess.run([sys.executable, str(root / "tools/contentc/spawn_offsets.py"), "--check"],
                              cwd=str(root), capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("OK", done.stdout)

    @unittest.skipUnless(PLANT_SHEET and PLANT_SHEET.is_file(), "original plant sheet not available")
    def test_shipped_file_is_exactly_a_fresh_render(self) -> None:
        table = spawn_offsets.build(Path(worlds.DEFAULT_OBB))
        fresh = spawn_offsets.render(table).encode("utf-8")
        self.assertEqual(hashlib.sha256(fresh).hexdigest(),
                         hashlib.sha256(SHIPPED.read_bytes()).hexdigest())

    @unittest.skipUnless(PLANT_SHEET and PLANT_SHEET.is_file(), "original plant sheet not available")
    def test_rebuild_matches_the_three_samples(self) -> None:
        table = spawn_offsets.build(Path(worlds.DEFAULT_OBB))
        rows = _rows_by_plant(table)
        for name, expected in SAMPLES.items():
            with self.subTest(plant=name):
                hit = [row for row in rows[name] if row["kind"] == expected["kind"]][0]
                self.assertEqual((hit["xPx"], hit["yPx"]),
                                 (expected["xPx"], expected["yPx"]))


if __name__ == "__main__":
    unittest.main()
