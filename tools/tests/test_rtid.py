"""Tests for RTID parsing and sheet indexing.

    python tools/tests/test_rtid.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.contentc.rtid import format_rtid, is_nothing, parse_rtid  # noqa: E402
from tools.contentc.sheets import SheetIndex, load_sheets, normalize_sheet  # noqa: E402

OBB = REPO.parent.parent / "work" / "obb_packages"

# References the original tables make to sheets that are not part of the six data
# sheets: `CurrentLevel` holds spawn scripts the level itself installs.
KNOWN_EXTERNAL_SHEETS = {"CurrentLevel"}

# Three zombie types point at properties that were deleted from the shipped sheet.
# The game tolerates them, so the compiler must too — but they are pinned here so a
# new dangling reference cannot hide inside the known count.
KNOWN_DANGLING = {
    ("fairy_tale_cavalry_summoned", "ZombieFairyTaleCavarySummonedDefault"),
    ("renai_armor2_statue", "ZombieRenaiArmor2StatueDefault"),
    ("renai_perfumer_statue", "ZombieRenaiPerfumerStatueDefault"),
}


def obj(alias, **data):
    return {"objclass": "X", "aliases": [alias], "objdata": data}


class RtidTest(unittest.TestCase):
    def test_parse_rtid_basic(self):
        self.assertEqual(parse_rtid("RTID(PeaDefault@ProjectileTypes)"),
                         ("PeaDefault", "ProjectileTypes"))

    def test_parse_rtid_zero(self):
        name, sheet = parse_rtid("RTID(0)")
        self.assertEqual((name, sheet), ("0", None))
        self.assertTrue(is_nothing(name, sheet))

    def test_parse_rtid_rejects_non_rtid(self):
        self.assertIsNone(parse_rtid("peashooter"))
        self.assertIsNone(parse_rtid(None))
        self.assertEqual(format_rtid("A", "B"), "RTID(A@B)")

    def test_duplicate_alias_reported(self):
        index = SheetIndex("T", [obj("dup", n=1), obj("dup", n=2), obj("solo")])
        self.assertEqual(index.duplicates(), {"dup": 2})
        self.assertEqual(index.resolve("dup")["objdata"]["n"], 1)
        self.assertEqual(len(index.resolve_all("dup")), 2)


class RealSheetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sheets = load_sheets(OBB)

    def test_sheets_loaded(self):
        self.assertEqual(len(self.sheets.get("PlantTypes")), 339)
        self.assertEqual(len(self.sheets.get("ZombieTypes")), 1127)
        self.assertTrue(self.sheets.get("PlantProperties"))
        self.assertTrue(self.sheets.get("ZombieProperties"))

    def test_plant_type_resolves_to_properties(self):
        plant = self.sheets.resolve("sunflower", "PlantTypes")
        self.assertEqual(plant["objdata"]["TypeName"], "sunflower")
        props = self.sheets.resolve("PeashooterDefault", "PlantProperties")
        self.assertIn("Actions", props["objdata"])

    def test_every_plant_property_reference_resolves(self):
        unresolved = []
        for plant in self.sheets.get("PlantTypes").objects:
            ref = parse_rtid(plant["objdata"].get("Properties"))
            if ref is None or is_nothing(*ref):
                unresolved.append((plant["objdata"].get("TypeName"), "no ref"))
                continue
            if self.sheets.resolve(ref[0], ref[1]) is None:
                unresolved.append((plant["objdata"].get("TypeName"), ref))
        self.assertEqual(unresolved, [])

    def test_every_zombie_property_reference_resolves(self):
        dangling = set()
        for zombie in self.sheets.get("ZombieTypes").objects:
            type_name = zombie["objdata"].get("TypeName")
            ref = parse_rtid(zombie["objdata"].get("Properties"))
            if ref is None or is_nothing(*ref):
                continue
            if ref[1] in KNOWN_EXTERNAL_SHEETS:
                continue
            if self.sheets.resolve(ref[0], ref[1]) is None:
                dangling.add((type_name, ref[0]))
        self.assertEqual(dangling, KNOWN_DANGLING)

    def test_sheet_spelling_variants_normalize(self):
        self.assertEqual(normalize_sheet("$ZombieProperties"), "ZombieProperties")
        self.assertIsNone(normalize_sheet("."))
        self.assertIsNone(normalize_sheet("PropertySheets"))
        self.assertIsNone(normalize_sheet(""))
        self.assertEqual(normalize_sheet("PlantProperties"), "PlantProperties")


if __name__ == "__main__":
    unittest.main(verbosity=2)
