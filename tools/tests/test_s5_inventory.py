"""Pins the S5 element / plant-food / boss data inventory to the original packs.

The inventory answers one question per concept: can S5 implement it from the
original tables, or must it be authored? The evidence is produced by
`tools/contentc/s5scan.py` and written to `native/generated/s5_data_gaps.json`;
this module keeps three promises about it:

* coverage - the scan walks all 2117 files under `work/obb_packages`
  (2116 `pkg_*.json` plus `_index.json`), not a filtered subset;
* shape - every concept carries a verdict plus its driven/authored split, and
  the shipped JSON re-renders byte for byte (no timestamps, sorted keys);
* the substantive findings - elements have no data at all (the single
  `ElementReactionModuleProperties` object is an empty flag), plant food is
  data-driven for exactly six plants, and the boss tables do carry per-phase
  health and attack rotations.

The heavy probes (a full concept scan, the boss tables) run once per class in
`setUpClass`, because a single pass parses 45 MB of JSON.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import contentc.s5scan as s5scan  # noqa: E402

OBB = s5scan.DEFAULT_OBB
GAPS = s5scan.DEFAULT_GAPS

HAS_OBB = OBB.is_dir()
HAS_GAPS = GAPS.is_file()

# `_index.json` is the extraction manifest; the packages themselves are pkg_*.
EXPECTED_FILES = 2117
EXPECTED_PACKAGES = 2116

# The six plants that own a `Type == "plantfood"` action in pkg_2073, resolved
# through pkg_2074 `Properties = RTID(<props>@PlantProperties)`.
PLANTFOOD_PLANTS = {
    "dartichoke",
    "draftodil1",
    "homingthistle",
    "magnetfruit",
    "rheumnobile",
    "sungun",
}


def load_gaps() -> dict:
    return json.loads(GAPS.read_text(encoding="utf-8"))


@unittest.skipUnless(HAS_OBB and HAS_GAPS, "original packs or generated gaps file missing")
class S5InventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gaps = load_gaps()
        cls.manifest = s5scan.index_manifest(OBB)
        cls.elements = s5scan.element_modules(OBB)
        cls.plant_elements = s5scan.plant_elements(OBB)
        cls.plantfood = s5scan.plantfood_actions(OBB)
        cls.boss_battles = s5scan.boss_battles(OBB)
        cls.boss_phases = s5scan.boss_phases(OBB)

    # ---- coverage ---------------------------------------------------------

    def test_scan_covers_all_2117_files(self) -> None:
        result = s5scan.scan(OBB, "elements", limit=0)
        self.assertEqual(result["files"]["matched"], EXPECTED_FILES)
        self.assertEqual(result["files"]["parsed"], EXPECTED_FILES)
        self.assertEqual(result["files"]["failed"], 0)

    def test_manifest_lists_every_package(self) -> None:
        self.assertEqual(self.manifest["files"], EXPECTED_FILES)
        self.assertEqual(self.manifest["packages"], EXPECTED_PACKAGES)
        self.assertEqual(self.manifest["fail"], 0)
        self.assertGreater(self.manifest["distinctObjclasses"], 100)

    def test_no_element_sheet_in_the_manifest(self) -> None:
        # The manifest is the authoritative list of every objclass in the packs.
        classes = self.manifest["classes"]
        self.assertFalse([name for name in classes if "element" in name.lower()])

    # ---- file shape -------------------------------------------------------

    def test_gaps_file_parses_and_has_three_sections(self) -> None:
        self.assertEqual(self.gaps["format"], s5scan.FORMAT)
        for concept in ("elements", "plantfood", "boss"):
            with self.subTest(concept=concept):
                section = self.gaps[concept]
                self.assertIn("verdict", section)
                self.assertIsInstance(section["driven"], list)
                self.assertIsInstance(section["authored"], list)
                self.assertTrue(section["authored"], "every concept must name what is authored")

    def test_gaps_sources_record_the_scan_scope(self) -> None:
        sources = self.gaps["sources"]
        self.assertEqual(sources["files"], EXPECTED_FILES)
        self.assertEqual(sources["packages"], EXPECTED_PACKAGES)

    def test_gaps_renders_byte_identically(self) -> None:
        shipped = GAPS.read_bytes()
        rendered = s5scan.render_report(self.gaps).encode("utf-8")
        self.assertEqual(shipped, rendered, "the shipped file is not what the generator emits")
        self.assertEqual(rendered, s5scan.render_report(self.gaps).encode("utf-8"))

    # ---- elements ---------------------------------------------------------

    def test_elements_are_authored(self) -> None:
        self.assertEqual(self.gaps["elements"]["verdict"], "authored")
        self.assertEqual(self.gaps["elements"]["driven"], [])

    def test_element_module_is_an_empty_flag(self) -> None:
        self.assertGreater(self.elements["found"], 0)
        self.assertEqual(self.elements["withFields"], 0)
        self.assertEqual(self.elements["empty"], self.elements["found"])
        self.assertEqual(list(self.elements["objclasses"]), ["ElementReactionModuleProperties"])

    def test_no_element_key_on_any_plant(self) -> None:
        self.assertEqual(self.plant_elements["found"], 0)
        self.assertEqual(self.gaps["elements"]["plantElementKeys"], 0)

    # ---- plant food -------------------------------------------------------

    def test_plantfood_has_exactly_six_actions(self) -> None:
        self.assertEqual(self.plantfood["found"], 6)
        self.assertEqual(self.gaps["plantfood"]["actionCount"], 6)

    def test_plantfood_actions_resolve_to_six_plants(self) -> None:
        owners = {plant for row in self.plantfood["rows"] for plant in row["plants"]}
        self.assertEqual(owners, PLANTFOOD_PLANTS)
        for row in self.plantfood["rows"]:
            self.assertEqual(len(row["plants"]), 1, f"{row['alias']} must resolve to one plant")
            self.assertIn("Projectile", row["fields"], f"{row['alias']} must name a projectile")

    def test_plantfood_duration_and_playcount_columns_exist(self) -> None:
        fields = self.gaps["plantfood"]["fields"]
        for name in ("PlantFoodDurationSeconds", "PlantFoodPlayCount"):
            with self.subTest(field=name):
                self.assertIn(name, fields)
                self.assertGreater(fields[name]["records"], 100)

    def test_plantfood_verdict_is_partial(self) -> None:
        self.assertEqual(self.gaps["plantfood"]["verdict"], "partial")

    # ---- boss -------------------------------------------------------------

    def test_boss_battles_are_data(self) -> None:
        self.assertEqual(self.boss_battles["found"], 75)
        self.assertEqual(self.boss_battles["distinctMech"], 50)
        for row in self.boss_battles["rows"]:
            with self.subTest(package=row["package"]):
                self.assertTrue(row["mech"])
                self.assertTrue(row["stage"])

    def test_boss_phases_carry_hitpoints(self) -> None:
        self.assertGreater(self.boss_phases["found"], 100)
        self.assertGreaterEqual(self.boss_phases["withStages"], 80)
        self.assertGreater(self.boss_phases["totalStages"], 200)
        with_stages = [row for row in self.boss_phases["rows"] if row["stages"]]
        for row in with_stages:
            with self.subTest(alias=row["alias"]):
                self.assertEqual(len(row["hitPoints"]), row["stages"])
                self.assertTrue(all(isinstance(hp, int) and hp > 0 for hp in row["hitPoints"]))

    def test_boss_events_in_worlddata_stay_four(self) -> None:
        # Only four level events are named *boss*; the rest of the boss wiring
        # lives in ZombossBattleModuleProperties, which is why the client's 26
        # bosses cannot be attributed from WorldData alone.
        events = s5scan.boss_events(OBB)
        self.assertEqual(events["found"], 4)
        self.assertEqual(set(events["byWorld"]), {"dark", "egypt", "kongfu", "skycity"})
        self.assertEqual(self.gaps["boss"]["bossEvents"], 4)

    def test_boss_covers_most_client_worlds_but_not_all(self) -> None:
        by_world = self.boss_battles["byWorld"]
        self.assertEqual(len(by_world), 28)  # 23 client worlds + rift + roof + 3 unmatched stages
        for world in ("frontyard", "memorytour", "muji"):
            self.assertNotIn(world, by_world, f"{world} has no boss battle in the packs")

    def test_boss_action_classes_are_listed(self) -> None:
        classes = self.gaps["boss"]["actionClasses"]
        self.assertGreaterEqual(len(classes), 40)
        self.assertIn("ZombossFireActionDefinition", classes)
        self.assertIn("ZombossSpawnActionDefinition", classes)


if __name__ == "__main__":
    unittest.main()
