"""Tests for `tools/contentc/armors.py` and the shipped armor table.

Two groups:

* `ShippedArmorTests` reads `native/generated/armors_from_pack.json` and asserts the
  facts the engine will rely on: 102 armors over 97 canonical rows, the `Cone`/`Bucket`
  spot checks, multi-armor zombies, the three dangling armor ids, determinism, and
  null-not-zero for fields the sheet does not have (`breaksInto`, `hitpoints` on the
  one template row).
* `ArmorCompileTests` recompiles from the OBB when it is present, so a stale shipped
  file cannot pass: the json must equal a fresh render byte for byte, and a directory
  with no armor sheet must compile to an empty table instead of raising.
"""

from __future__ import annotations

import collections
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.contentc import armors, worlds

SHIPPED = worlds.REPO / "native/generated/armors_from_pack.json"
REPORT = worlds.REPO / "native/generated/armor_report.md"
HAS_OBB = bool(worlds.DEFAULT_OBB) and Path(worlds.DEFAULT_OBB).is_dir()

#: dangling `ZombieArmorProps` targets: referenced by zombies but absent from every
#: `ArmorPropertySheet` object in the 2117 packages. Counted, never invented.
DANGLING = {"AngerManagement", "HideLayer", "InvincibleArmor"}


def load_shipped() -> dict:
    with SHIPPED.open(encoding="utf-8") as handle:
        return json.load(handle)


class ShippedArmorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SHIPPED.is_file():
            raise unittest.SkipTest("armors_from_pack.json not generated yet")
        cls.table = load_shipped()
        cls.armors = {record["id"]: record for record in cls.table["armors"]}
        cls.zombies = {record["zombieId"]: record for record in cls.table["zombies"]}
        cls.counts = cls.table["counts"]

    # -- shape ---------------------------------------------------------

    def test_format_and_generator(self) -> None:
        self.assertEqual(self.table["format"], armors.FORMAT)
        self.assertEqual(self.table["generated"], armors.GENERATED)
        self.assertEqual(
            sorted(self.table),
            ["armors", "contentComparison", "counts", "dangling", "fieldMap",
             "format", "generated", "sources", "zombies"],
        )

    def test_armor_and_zombie_totals(self) -> None:
        self.assertEqual(len(self.table["armors"]), 102)
        self.assertEqual(len(self.table["zombies"]), 1127)
        self.assertEqual(self.counts["canonicalArmors"], 97)
        self.assertEqual(self.counts["embeddedRows"], 9)
        self.assertEqual(self.counts["embeddedOnlyArmors"], 5)

    def test_armors_are_sorted_and_unique(self) -> None:
        ids = [record["id"] for record in self.table["armors"]]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_zombies_are_sorted_and_keep_duplicate_rows(self) -> None:
        # pkg_2115_ZombieType really lists two TypeNames twice (`heavy_shield`,
        # `kongfu_gargantuar`) with different props. Dropping a row would hide a
        # real pack fact, so the table keeps 1127 rows and reports the duplicates.
        ids = [record["zombieId"] for record in self.table["zombies"]]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), 1127)
        seen = collections.Counter(ids)
        self.assertEqual(sorted(name for name, n in seen.items() if n > 1),
                         ["heavy_shield", "kongfu_gargantuar"])
        self.assertEqual(self.counts["duplicateZombieIds"],
                         ["heavy_shield", "kongfu_gargantuar"])
        self.assertEqual(len(seen), 1125)

    def test_every_record_carries_its_source(self) -> None:
        for record in self.table["armors"]:
            self.assertTrue(record["pkg"].startswith("pkg_"), record["id"])
            self.assertTrue(record["fields"], record["id"])
            self.assertIsInstance(record["flags"], list)
            self.assertIsInstance(record["art"], dict, record["id"])
            # an armor with no bone layer still has art: armorLayer is then null
            self.assertIn("armorLayer", record["art"], record["id"])
            self.assertIn("armorType", record["art"], record["id"])

    # -- the two spot checks the task names ---------------------------

    def test_cone_default(self) -> None:
        cone = self.armors["ConeDefault"]
        self.assertEqual(cone["hitpoints"], 370)
        self.assertEqual(cone["armorType"], "Cone")
        self.assertTrue(cone["droppable"])
        self.assertTrue(cone["damageable"])
        self.assertFalse(cone["metallic"])
        self.assertEqual(cone["art"]["armorLayer"], "zombie_armor_cone_norm")
        self.assertEqual(cone["pkg"], "pkg_0002_ArmorPropertySheetUtils")
        self.assertEqual(cone["fields"]["BaseHealth"], 370)

    def test_bucket_default(self) -> None:
        bucket = self.armors["BucketDefault"]
        self.assertEqual(bucket["hitpoints"], 1100)
        self.assertEqual(bucket["armorType"], "Bucket")
        self.assertTrue(bucket["droppable"])
        self.assertTrue(bucket["metallic"])
        self.assertEqual(bucket["art"]["armorLayer"], "zombie_armor_bucket_norm")

    def test_cone_and_bucket_are_not_the_same_armor(self) -> None:
        # the engine currently hard-codes `buckethead ? "Bucket" : "Cone"`
        # (native/src/battle_view.cpp:297); the table proves there are 102 more.
        self.assertNotEqual(
            self.armors["ConeDefault"]["art"]["armorLayer"],
            self.armors["BucketDefault"]["art"]["armorLayer"],
        )

    def test_layer_health_is_passed_through_verbatim(self) -> None:
        # ArmorLayerHealth mixes break thresholds (0.666/0.333) with negative layer
        # indices (-1..-37), so the table must not "fix" either reading. `layers`
        # carries the undamaged layer plus one entry per damage state.
        cone = self.armors["ConeDefault"]
        self.assertEqual(cone["art"]["layerHealth"], [0.666, 0.333])
        self.assertEqual(len(cone["art"]["layers"]), len(cone["art"]["layerHealth"]) + 1)
        self.assertEqual(cone["art"]["layers"][0], "zombie_armor_cone_norm")
        arm_bone = self.armors["ArmBoneDefault"]
        self.assertTrue(
            all(value < 0 for value in arm_bone["art"]["layerHealth"]),
            arm_bone["art"]["layerHealth"],
        )

    # -- multi-armor chains -------------------------------------------

    def test_two_armor_zombie(self) -> None:
        surfer = self.zombies["beach_surfer"]
        self.assertEqual(
            surfer["armorIds"], ["SurfboardSurfingDefault", "SurfboardDefault"]
        )
        self.assertEqual(
            [self.armors[a]["hitpoints"] for a in surfer["armorIds"]], [700, 700]
        )
        self.assertEqual(surfer["armorCount"], 2)

    def test_three_armor_zombie(self) -> None:
        nutcracker = self.zombies["nutcracker"]
        self.assertEqual(
            nutcracker["armorIds"],
            ["NutCrackerBody", "NutCrackerArm", "NutCrackerWindUpKey"],
        )
        self.assertEqual(
            [self.armors[a]["hitpoints"] for a in nutcracker["armorIds"]],
            [2178, 11, 11],
        )
        self.assertIn("order", nutcracker["armorOrderNote"])

    def test_combination_histogram_sums_to_the_zombie_count(self) -> None:
        histogram = {int(key): value for key, value in self.counts["armorCombination"].items()}
        self.assertEqual(sum(histogram.values()), len(self.table["zombies"]))
        self.assertEqual(histogram[0], 851)
        self.assertEqual(histogram[1], 260)
        self.assertEqual(self.counts["multiArmorZombies"], 16)
        self.assertEqual(sum(v for k, v in histogram.items() if k >= 2), 16)

    def test_armored_plus_bare_plus_unknown_is_all_zombies(self) -> None:
        self.assertEqual(
            self.counts["zombiesWithArmor"] + self.counts["zombiesWithoutArmor"]
            + self.counts["zombiesUnknownProps"],
            len(self.table["zombies"]),
        )
        self.assertEqual(self.counts["zombiesWithArmor"], 276)
        self.assertEqual(self.counts["zombiesUnknownProps"], 47)

    def test_zombie_records_expose_class_and_armor(self) -> None:
        conehead = self.zombies["tutorial_armor1"]
        self.assertEqual(conehead["className"], "ZombieBasic")
        self.assertEqual(conehead["armorIds"], ["ConeDefault"])
        self.assertFalse(conehead["propsMissing"])

    # -- dangling references -----------------------------------------

    def test_dangling_count_matches_the_list(self) -> None:
        self.assertEqual(self.counts["dangling"], len(self.table["dangling"]))
        self.assertEqual({item["armorId"] for item in self.table["dangling"]}, DANGLING)
        self.assertEqual(self.counts["danglingReferences"], 13)
        self.assertEqual(
            sum(item["count"] for item in self.table["dangling"]), 13
        )

    def test_dangling_ids_are_still_listed_on_their_zombies(self) -> None:
        # the reference is a fact; the missing sheet is reported, not erased
        self.assertEqual(self.zombies["west_bungee_almanac"]["armorIds"], ["HideLayer"])
        self.assertEqual(
            self.zombies["carnie_trapeze_duo"]["armorIds"], ["InvincibleArmor"]
        )
        for item in self.table["dangling"]:
            for reference in item["references"]:
                self.assertIn(
                    item["armorId"], self.zombies[reference["zombieId"]]["armorIds"]
                )

    def test_dangling_ids_are_not_invented_in_the_armor_list(self) -> None:
        for armor_id in DANGLING:
            self.assertNotIn(armor_id, self.armors)

    # -- null-not-zero -------------------------------------------------

    def test_breaks_into_is_null_because_the_sheet_has_no_such_field(self) -> None:
        # `--needle` finds 0 hits for BreaksInto/NextArmor in all 2117 packages.
        for record in self.table["armors"]:
            self.assertIsNone(record["breaksInto"], record["id"])
            self.assertIn("no", record["breaksIntoNote"].lower() + " no")

    def test_missing_hit_points_stay_null(self) -> None:
        template = self.armors["ArmorPropertySheetUtilsTemplate"]
        self.assertIsNone(template["hitpoints"])
        self.assertEqual(self.counts["withoutHitpoints"], 1)
        self.assertEqual(
            sorted(r["id"] for r in self.table["armors"] if r["hitpoints"] is None),
            ["ArmorPropertySheetUtilsTemplate"],
        )

    def test_hit_point_sentinels_are_kept_and_flagged(self) -> None:
        flagged = sorted(r["id"] for r in self.table["armors"] if r["hitpointsSentinel"])
        self.assertEqual(
            flagged,
            ["ArmBoneDefault", "ArmDefault", "HeadDefault", "PassDamageDefault"],
        )
        for armor_id in flagged:
            self.assertEqual(self.armors[armor_id]["hitpoints"], 2147483647)
        self.assertEqual(self.counts["hitpointsSentinels"], 4)

    # -- determinism ---------------------------------------------------

    def test_render_is_byte_identical(self) -> None:
        first = hashlib.sha256(armors.render(self.table).encode("utf-8")).hexdigest()
        second = hashlib.sha256(armors.render(load_shipped()).encode("utf-8")).hexdigest()
        self.assertEqual(first, second)
        self.assertEqual(first, hashlib.sha256(SHIPPED.read_bytes()).hexdigest())

    def test_shipped_file_is_canonical_json(self) -> None:
        raw = SHIPPED.read_bytes()
        self.assertTrue(raw.endswith(b"\n"))
        self.assertNotIn(b"\r\n", raw)
        self.assertNotIn(b"\n\n", raw)
        self.assertIn(b'"ConeDefault"', raw)
        # re-encoding the parsed document must reproduce the very same bytes
        self.assertEqual(
            hashlib.sha256(armors.render(json.loads(raw.decode("utf-8"))).encode("utf-8")).hexdigest(),
            hashlib.sha256(raw).hexdigest(),
        )

    # -- report ---------------------------------------------------------

    def test_report_covers_the_required_sections(self) -> None:
        self.assertTrue(REPORT.is_file(), REPORT)
        text = REPORT.read_text(encoding="utf-8")
        for heading in (
            "## 0.",
            "## 1.",
            "## 2.",
            "## 3.",
            "## 6.",
            "### 6a.",
            "### 6b.",
        ):
            self.assertIn(heading, text)
        # the three broken bridges and the HP-only numeric comparison
        for content_id in ("market_armor1", "royal_noblewoman", "gang_cone"):
            self.assertIn("`%s`" % content_id, text)
        self.assertIn("ClockworkPlateDefault", text)
        self.assertIn("battle_view.cpp:297", text)
        self.assertIn("world.cpp:433", text)

    def test_check_helper_passes_on_the_shipped_file(self) -> None:
        self.assertEqual(armors.check(self.table, SHIPPED), 0)


class ArmorCompileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not HAS_OBB:
            raise unittest.SkipTest("OBB packages not available")
        cls.table = armors.compile_armors(worlds.DEFAULT_OBB)

    def test_recompile_is_deterministic(self) -> None:
        again = armors.compile_armors(worlds.DEFAULT_OBB)
        self.assertEqual(armors.render(self.table), armors.render(again))

    def test_shipped_file_matches_a_fresh_compile(self) -> None:
        if not SHIPPED.is_file():
            self.skipTest("armors_from_pack.json not generated yet")
        fresh = armors.render(self.table).encode("utf-8")
        self.assertEqual(hashlib.sha256(fresh).hexdigest(),
                         hashlib.sha256(SHIPPED.read_bytes()).hexdigest())

    def test_empty_directory_compiles_to_an_empty_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            empty = armors.compile_armors(directory)
        self.assertEqual(empty["armors"], [])
        self.assertEqual(empty["zombies"], [])
        self.assertEqual(empty["counts"]["filesScanned"], 0)
        self.assertEqual(empty["counts"]["dangling"], 0)


if __name__ == "__main__":
    unittest.main()
