"""Tests for `tools/contentc/projectiles.py` and the shipped projectile table.

Two groups:
* `ShippedProjectileTests` reads `native/generated/projectiles_from_pack.json` and
  asserts the facts the engine will rely on (counts, PeaDefault, null-not-zero,
  sentinels, art keys, per-record evidence).
* `ProjectileCompileTests` recompiles from the OBB when it is present, so a stale
  shipped file cannot pass: the json must equal a fresh render byte for byte, and
  a directory with no `pkg_2082` must compile to an empty table instead of raising.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.contentc import projectiles, worlds

SHIPPED = worlds.REPO / "native/generated/projectiles_from_pack.json"
REPORT = worlds.REPO / "native/generated/projectile_report.md"
HAS_OBB = bool(worlds.DEFAULT_OBB) and Path(worlds.DEFAULT_OBB).is_dir()


def load_shipped() -> dict:
    with SHIPPED.open(encoding="utf-8") as handle:
        return json.load(handle)


class ShippedProjectileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SHIPPED.is_file():
            raise unittest.SkipTest("projectiles_from_pack.json not generated yet")
        cls.table = load_shipped()
        cls.records = {record["id"]: record for record in cls.table["projectiles"]}

    def test_format_and_generator(self) -> None:
        self.assertEqual(self.table["format"], projectiles.FORMAT)
        self.assertEqual(self.table["generated"], projectiles.GENERATED)
        self.assertEqual(self.table["sources"]["canonicalPackage"], projectiles.CANONICAL_PKG)

    def test_totals(self) -> None:
        counts = self.table["counts"]
        # 571 ids in pkg_2082 + 31 that only exist as overrides inside level packages.
        self.assertEqual(counts["canonicalIds"], 571)
        self.assertEqual(counts["canonicalObjects"], 572)
        self.assertEqual(counts["embeddedObjects"], 47)
        self.assertEqual(counts["embeddedOnlyIds"], 31)
        self.assertEqual(counts["projectiles"], 602)
        self.assertEqual(len(self.table["projectiles"]), 602)
        # the sheet is not single-class; 71 objclasses share the same vocabulary
        self.assertEqual(counts["objclasses"], 71)
        self.assertEqual(counts["filesFailed"], 0)

    def test_ids_sorted_unique_and_every_record_has_provenance(self) -> None:
        ids = [record["id"] for record in self.table["projectiles"]]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(set(ids)), len(ids))
        for record in self.table["projectiles"]:
            self.assertTrue(record["pkg"].startswith("pkg_"), record["id"])
            self.assertIn(record["trajectory"], {"straight", "arc", "drop", "static", "unknown"})
            self.assertTrue(record["trajectoryEvidence"], record["id"])
            self.assertIn(record["objclass"], self.table["counts"]["objclassCounts"])

    def test_pea_default_speed_and_trajectory(self) -> None:
        pea = self.records["PeaDefault"]
        self.assertEqual(pea["trajectory"], "straight")
        self.assertEqual(pea["speed"]["pxPerSec"], 333)
        self.assertEqual(pea["speed"]["colsPerSec"], 5.55)  # 333 / 60
        self.assertEqual(pea["speed"]["pxPerSecMin"], 333)
        self.assertEqual(pea["speed"]["pxPerSecMax"], 333)
        self.assertEqual(pea["baseDamage"], 20)
        # CollisionRect 30x30 -> half extent 15 px -> 15/60 = 0.25 == kShotHitRadius
        self.assertEqual(pea["hitRadius"]["cols"], 0.25)
        self.assertEqual(pea["hitRadius"]["px"], 15)
        self.assertEqual(pea["art"]["attachedPAM"], "POPANIM_EFFECTS_T_PEA_PROJECTILE")

    def test_lob_and_drop_speeds_come_from_the_pack(self) -> None:
        cabbage = self.records["CabbageDefault"]
        self.assertEqual(cabbage["trajectory"], "arc")
        self.assertEqual(cabbage["speed"]["pxPerSec"], 300)
        self.assertEqual(cabbage["velocity"]["z"], {"min": 500, "max": 700})
        self.assertEqual(cabbage["acceleration"]["z"], {"min": -10, "max": -10})
        taraxacum = self.records["TaraxacumDefault"]
        self.assertEqual(taraxacum["trajectory"], "drop")
        self.assertEqual(taraxacum["baseDamage"], 0)  # a real zero, not a missing field
        self.assertEqual(taraxacum["splash"]["damage"], 60)
        self.assertEqual(taraxacum["splash"]["radius"], 2.0736)

    def test_missing_fields_are_null_not_zero(self) -> None:
        # these rows carry no BaseDamage at all -> null (0 would mean "does no damage")
        for obj_id in ("HandEffectDefault", "ZombieBoneDefault", "TokenProjectile"):
            self.assertIsNone(self.records[obj_id]["baseDamage"], obj_id)
        # a row without InitialVelocity -> velocity/speed null and trajectory unknown
        sushi = self.records["HeianSushiDefault"]
        self.assertIsNone(sushi["velocity"])
        self.assertIsNone(sushi["speed"])
        self.assertEqual(sushi["trajectory"], "unknown")
        # asked-for fields that the pack simply does not have stay null everywhere
        for name in ("TypeName", "Speed", "ProjectileSpeed", "Motion", "Pierce", "PierceCount",
                     "PopAnim", "ResourceGroups", "SpawnOffset"):
            self.assertEqual(self.table["coverage"][name]["present"], 0, name)
            self.assertIsNone(self.table["fieldMap"][name], name)
        self.assertNotIn("Speed", self.records["PeaDefault"])

    def test_no_tuning_value_leaked_into_the_table(self) -> None:
        # every straight shot must carry its own pack speed, not the 5.2 cols/s constant
        speeds = {
            record["speed"]["colsPerSec"]
            for record in self.table["projectiles"]
            if record["trajectory"] == "straight" and record["speed"]
        }
        self.assertGreater(len(speeds), 10)
        self.assertEqual(self.table["tuning"]["engineConstants"]["kShotSpeedColsPerSec"], 5.2)
        # 5.2 would be 312 px/s, which no row reports
        self.assertNotIn(312, {
            record["speed"]["pxPerSec"] for record in self.table["projectiles"] if record["speed"]
        })

    def test_int_sentinels_are_flagged_and_kept_raw(self) -> None:
        sentinel = 2147483647
        flagged = [record for record in self.table["projectiles"] if record["baseDamageSentinel"]]
        self.assertEqual(len(flagged), self.table["counts"]["baseDamageSentinels"])
        self.assertGreaterEqual(len(flagged), 7)
        for record in flagged:
            self.assertEqual(record["baseDamage"], sentinel, record["id"])
        unbounded = [
            record for record in self.table["projectiles"] if record["splash"] and record["splash"]["unbounded"]
        ]
        self.assertEqual(len(unbounded), self.table["tuning"]["splashRadiusCells"]["sentinels"])
        self.assertEqual(len(unbounded), 6)

    def test_trajectory_counts_and_tuning_stats(self) -> None:
        traj = self.table["trajectoryCounts"]
        self.assertEqual(sum(traj.values()), self.table["counts"]["projectiles"])
        self.assertEqual(traj["straight"], 374)
        self.assertEqual(traj["arc"], 118)
        self.assertEqual(traj["drop"], 59)
        self.assertEqual(traj["static"], 42)
        self.assertEqual(traj["unknown"], 9)
        tuning = self.table["tuning"]
        self.assertEqual(tuning["straightShotSpeedsPxPerSec"]["mode"], 333.0)
        self.assertEqual(tuning["straightShotSpeedsPxPerSec"]["median"], 333.0)
        # the engine's hit radius matches the dominant CollisionRect exactly
        self.assertEqual(tuning["hitRadiusCols"]["mode"], 0.25)
        self.assertEqual(tuning["hitRadiusCols"]["median"], 0.25)
        self.assertEqual(tuning["engineConstants"]["kShotHitRadius"], 0.25)

    def test_variants_record_every_copy(self) -> None:
        variants = {record["id"]: record["variants"] for record in self.table["projectiles"] if record["variants"]}
        self.assertGreaterEqual(len(variants), 5)
        for obj_id, copies in variants.items():
            for copy in copies:
                self.assertIn("pkg", copy, obj_id)
                self.assertIsInstance(copy["same"], bool)
                self.assertIsInstance(copy["differingKeys"], list)
            # a differing copy must name at least one field
            for copy in copies:
                if not copy["same"]:
                    self.assertTrue(copy["differingKeys"], obj_id)

    def test_embedded_only_ids_are_present(self) -> None:
        for obj_id in ("MeteorDefault", "FireShroomSmallShot", "ZombieDirection2Projectile", "SandbagDefault"):
            self.assertIn(obj_id, self.records, obj_id)
            self.assertNotEqual(self.records[obj_id]["pkg"], projectiles.CANONICAL_STEM, obj_id)

    def test_report_numbers_match_the_table(self) -> None:
        if not REPORT.is_file():
            self.skipTest("report not generated")
        text = REPORT.read_text(encoding="utf-8")
        counts = self.table["counts"]
        self.assertIn("| 编译出的弹道 | %d |" % counts["projectiles"], text)
        self.assertIn("| 只存在于内嵌副本的 id | %d |" % counts["embeddedOnlyIds"], text)
        self.assertIn("| 中位数 | 0.25 cols |", text)
        self.assertIn("## 5.", text)
        self.assertIn("kShotSpeedColsPerSec", text)
        self.assertIn("kShotHitRadius", text)
        # the 0-hit field names must be stated with their counts, not silently dropped
        self.assertIn("0 命中", text)
        for name in ("TypeName", "Speed", "ProjectileSpeed", "Motion", "Pierce", "PierceCount",
                     "PopAnim", "ResourceGroups", "SpawnOffset"):
            self.assertIn("`%s`" % name, text)
        # the sample must include the three reference shots
        for obj_id in ("PeaDefault", "CabbageDefault", "TaraxacumDefault"):
            self.assertIn("`%s`" % obj_id, text)

    def test_check_passes_on_the_shipped_file(self) -> None:
        table = projectiles.compile_projectiles(Path(worlds.DEFAULT_OBB))
        self.assertEqual(projectiles.check(table, SHIPPED), 0)

    def test_shipped_json_is_sorted_with_indent_one(self) -> None:
        raw = SHIPPED.read_text(encoding="utf-8")
        self.assertTrue(raw.endswith("\n"))
        self.assertIn('\n "counts": {', raw)  # one-space indent, sorted keys
        self.assertNotIn("\t", raw)


@unittest.skipUnless(HAS_OBB, "original OBB packages not available")
class ProjectileCompileTests(unittest.TestCase):
    def test_compile_is_deterministic(self) -> None:
        first = projectiles.compile_projectiles(Path(worlds.DEFAULT_OBB))
        second = projectiles.compile_projectiles(Path(worlds.DEFAULT_OBB))
        self.assertEqual(projectiles.render(first), projectiles.render(second))

    @unittest.skipUnless(SHIPPED.is_file(), "shipped table missing")
    def test_shipped_file_matches_a_fresh_compile(self) -> None:
        table = projectiles.compile_projectiles(Path(worlds.DEFAULT_OBB))
        self.assertEqual(SHIPPED.read_text(encoding="utf-8"), projectiles.render(table))

    def test_unknown_package_directory_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            junk = Path(tmp) / "pkg_9999_Bogus.json"
            junk.write_text("{not json", encoding="utf-8")
            table = projectiles.compile_projectiles(Path(tmp))
            self.assertEqual(table["counts"]["projectiles"], 0)
            self.assertEqual(table["counts"]["canonicalIds"], 0)
            self.assertEqual(table["projectiles"], [])
            self.assertEqual(table["trajectoryCounts"], {})

    def test_report_render_is_deterministic(self) -> None:
        table = projectiles.compile_projectiles(Path(worlds.DEFAULT_OBB))
        first = projectiles.render_report(table, Path(worlds.DEFAULT_OBB))
        second = projectiles.render_report(table, Path(worlds.DEFAULT_OBB))
        self.assertEqual(first, second)
        if REPORT.is_file():
            self.assertEqual(first, REPORT.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

# 干净 clone 里没有原版表目录（`work/obb_packages` 不进仓库）：缺目录时整套跳过，
# 而不是每个用例报 FileNotFoundError。要真跑就设 PVZ2_OBB_DIR 指向解包目录。
import os as _os
import unittest as _unittest
from pathlib import Path as _Path

_obb = _Path(
    _os.environ.get("PVZ2_OBB_DIR")
    or (_Path(__file__).resolve().parents[2].parent.parent / "work" / "obb_packages")
)
if not _obb.is_dir():
    for _name, _obj in list(globals().items()):
        if isinstance(_obj, type) and issubclass(_obj, _unittest.TestCase):
            setattr(_obj, "__unittest_skip__", True)
            setattr(_obj, "__unittest_skip_why__", f"缺少原版表目录 {_obb}（设 PVZ2_OBB_DIR）")
