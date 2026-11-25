"""Tests for tools/contentc/vasebreaker.py — the original VaseBreaker (砸罐子) content.

Two groups:

* `ShippedVasebreakerTests` only reads `native/generated/vasebreaker.json`, so it runs
  anywhere (CI without the OBB still checks the shipped product is complete).
* `CompileVasebreakerTests` needs the OBB and recompiles, proving the shipped file is the
  output of the current code (byte for byte), and that a missing package degrades into
  `unknowns` instead of being filled with a made-up zero.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from contentc import vasebreaker, worlds  # noqa: E402

SHIPPED = vasebreaker.DEFAULT_OUT
LEVELS_DIR = vasebreaker.DEFAULT_LEVELS
HAS_OBB = worlds.DEFAULT_OBB.is_dir()

REQUIRED_KEYS = ("vaseCount", "vases", "seedBank", "initialSun", "timeLimit",
                 "sourceFiles", "unknowns")


def load_shipped() -> dict:
    with SHIPPED.open(encoding="utf-8") as handle:
        return json.load(handle)


def client_vasebreaker_levels() -> dict:
    """level id -> package, straight from the client level files."""
    out = {}
    for path in sorted(LEVELS_DIR.glob("*.json")):
        with path.open(encoding="utf-8-sig") as handle:
            doc = json.load(handle)
        extra = doc.get("extra") or {}
        if extra.get("vasebreaker"):
            out[doc.get("id") or path.stem] = extra.get("package")
    return out


class ShippedVasebreakerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = load_shipped()
        cls.levels = cls.table["levels"]
        cls.counts = cls.table["counts"]
        cls.unknowns = {row["kind"]: row for row in cls.table["unknowns"]}

    # ---------------------------------------------------------------- shape

    def test_format_and_top_level_keys(self) -> None:
        self.assertEqual(self.table["format"], vasebreaker.FORMAT)
        self.assertEqual(sorted(self.table),
                         ["counts", "format", "generated", "levels", "sources", "unknowns"])
        self.assertEqual(self.table["generated"], vasebreaker.GENERATED)
        self.assertIn("extra.vasebreaker", self.table["sources"]["flag"])

    def test_all_47_levels_present_and_sorted(self) -> None:
        self.assertEqual(len(self.levels), 47)
        self.assertEqual(self.counts["levels"], 47)
        self.assertEqual(sorted(self.levels), list(self.levels))

    def test_level_ids_match_content_flag_one_to_one(self) -> None:
        """Every client level with extra.vasebreaker is shipped, and nothing else is."""
        wanted = client_vasebreaker_levels()
        self.assertEqual(len(wanted), 47)
        self.assertEqual(set(wanted), set(self.levels))
        for level_id, package in wanted.items():
            self.assertEqual(self.levels[level_id]["package"], package, level_id)

    def test_every_level_carries_the_required_schema(self) -> None:
        for level_id, row in self.levels.items():
            for key in REQUIRED_KEYS:
                self.assertIn(key, row, f"{level_id} missing {key}")
            self.assertTrue(row["unknowns"], f"{level_id} has no unknowns note")
            self.assertEqual(row["levelId"], level_id)

    def test_vase_count_and_type_totals_are_consistent(self) -> None:
        vase_total = 0
        entry_total = 0
        by_type = {"zombie": 0, "plant": 0, "collectable": 0}
        for level_id, row in self.levels.items():
            vases = row["vases"]
            total = sum(item["count"] for item in vases)
            if row["preset"]["found"]:
                self.assertEqual(row["vaseCount"], total, level_id)
            else:
                self.assertIsNone(row["vaseCount"], level_id)
                self.assertEqual(vases, [], level_id)
            self.assertEqual(row["entryCount"], len(vases), level_id)
            self.assertEqual(sum(row["byType"].values()), total, level_id)
            vase_total += total
            entry_total += row["entryCount"]
            for kind, value in row["byType"].items():
                by_type[kind] += value
        self.assertEqual(self.counts["vaseTotal"], vase_total)
        self.assertEqual(vase_total, 1435)
        self.assertEqual(self.counts["entryTotal"], entry_total)
        self.assertEqual(entry_total, 459)
        self.assertEqual(self.counts["byType"], by_type)
        self.assertEqual(by_type, {"zombie": 788, "plant": 617, "collectable": 30})

    # ------------------------------------------------------- pack spot checks

    def test_beach_69_matches_the_pack(self) -> None:
        """pkg_0290 is dumped in the probe; these are the raw values, not a re-derivation."""
        row = self.levels["beach_69"]
        self.assertEqual(row["package"], "pkg_0290")
        self.assertEqual(row["levelFile"], "pkg_0290_LevelDefinition.json")
        self.assertEqual(row["stageModule"], "BeachStage")
        self.assertEqual(row["levelNameKey"], "[VASEBREAKER_BEACH_LEVEL_NAME_1]")
        self.assertEqual(row["levelNumber"], 1)
        self.assertTrue(row["isVasebreaker"])
        self.assertEqual(row["levelPowerupSet"], "LevelPowerupsVasebreaker")
        self.assertEqual(row["vaseCount"], 30)
        self.assertEqual(row["entryCount"], 12)
        self.assertEqual(row["byType"], {"zombie": 21, "plant": 9, "collectable": 0})
        self.assertEqual(row["columnRange"], {"min": 2, "max": 8})
        self.assertEqual(row["excludedCells"],
                         [[4, 0], [5, 1], [6, 2], [5, 3], [4, 4]])
        self.assertEqual(row["coloredVases"], {"plant": 3, "zombie": 2})
        self.assertEqual(row["tide"], {"startingWaveLocation": 4})
        zombies = {item["zombieId"]: item["count"] for item in row["vases"] if item["type"] == "zombie"}
        plants = {item["plantId"]: item["count"] for item in row["vases"] if item["type"] == "plant"}
        self.assertEqual(zombies, {"beach": 4, "beach_armor1": 2, "beach_armor2": 1,
                                   "beach_fem": 4, "beach_fem_armor1": 2,
                                   "beach_fem_armor2": 1, "beach_snorkel": 3,
                                   "beach_imp": 4})
        self.assertEqual(plants, {"wallnut": 2, "bowlingbulb": 3, "homingthistle": 4})

    def test_beach_70_matches_the_pack(self) -> None:
        row = self.levels["beach_70"]
        self.assertEqual(row["package"], "pkg_0291")
        self.assertEqual(row["vaseCount"], 30)
        self.assertEqual(row["entryCount"], 11)
        self.assertEqual(row["byType"], {"zombie": 18, "plant": 10, "collectable": 2})
        self.assertEqual(row["columnRange"], {"min": 2, "max": 8})
        self.assertEqual(row["excludedCells"],
                         [[2, 0], [4, 1], [3, 2], [4, 3], [2, 4]])
        self.assertEqual(row["coloredVases"], {"plant": 1, "zombie": 3})
        self.assertEqual(row["tide"], {"startingWaveLocation": 6})
        collectables = [item for item in row["vases"] if item["type"] == "collectable"]
        self.assertEqual([(item["collectableType"], item["count"]) for item in collectables],
                         [("plantfood", 2)])

    def test_only_frontyard_166_lacks_a_preset(self) -> None:
        missing = [level_id for level_id, row in self.levels.items()
                   if not row["preset"]["found"]]
        self.assertEqual(missing, ["frontyard_166"])
        self.assertEqual(self.counts["withoutPresetIds"], ["frontyard_166"])
        self.assertEqual(self.counts["withPreset"], 46)
        row = self.levels["frontyard_166"]
        self.assertEqual(row["package"], "pkg_0302")
        self.assertIsNone(row["vaseCount"])
        self.assertEqual(row["vases"], [])
        # the endless recipe *is* present and must be kept verbatim, not folded into vases
        self.assertIsNotNone(row["endless"])
        self.assertEqual(row["endless"]["stageCount"], 3)
        self.assertEqual(row["seedBank"][0]["plantId"], "cherry_bomb")

    def test_seed_bank_and_starting_sun_sources(self) -> None:
        banked = sorted(level_id for level_id, row in self.levels.items() if row["seedBank"])
        self.assertEqual(banked, ["carnival_66", "egypt_57", "frontyard_166", "kongfu_83",
                                  "muji_24", "pirate_41", "plantagenet_18", "steam_32"])
        self.assertEqual(self.counts["withSeedBank"], 8)
        sun = {level_id: row["initialSun"] for level_id, row in self.levels.items()
               if row["initialSun"] is not None}
        self.assertEqual(sun, {"frontyard_166": 0, "muji_24": 0, "pirate_41": 300,
                               "plantagenet_18": 200})
        self.assertEqual(self.counts["withStartingSun"], 4)
        self.assertEqual(self.counts["withoutStartingSun"], 43)
        # pirate_41 pulls its sun from LevelDefinition while carrying a boss conveyor too
        pirate = self.levels["pirate_41"]
        self.assertEqual(pirate["initialSunSource"], "LevelDefinition.StartingSun")
        self.assertEqual(pirate["stageModule"], "PirateBossStage")
        self.assertEqual(pirate["seedBankInfo"]["method"], "chooser")
        self.assertEqual(pirate["seedBankInfo"]["conveyor"], True)
        self.assertEqual(len(pirate["seedBank"]), 5)
        self.assertEqual(pirate["seedBank"][0]["plantId"], "chardguard")
        self.assertEqual(pirate["seedBank"][0]["weight"], 10)

    # ------------------------------------------- absent fields stay absent

    def test_fields_the_original_lacks_are_null_not_zero(self) -> None:
        with_sun = ("frontyard_166", "muji_24", "pirate_41", "plantagenet_18")
        for level_id, row in self.levels.items():
            # no VaseBreaker level in the pack carries a timer
            self.assertIsNone(row["timeLimit"], level_id)
            if level_id not in with_sun:
                self.assertIsNone(row["initialSun"], level_id)
            for item in row["vases"]:
                self.assertIsNone(item["row"], level_id)
                self.assertIsNone(item["col"], level_id)
                self.assertIsNone(item["sunAmount"], level_id)
                self.assertIn(item["type"], ("zombie", "plant", "collectable"), level_id)
        self.assertEqual(self.counts["withTimeLimit"], 0)

    def test_unknowns_name_every_absent_field_with_counts(self) -> None:
        self.assertEqual(sorted(self.unknowns),
                         ["endless", "initialSun", "preset", "seedBank", "sunAmount",
                          "timeLimit", "vasePlacement"])
        self.assertEqual(self.unknowns["timeLimit"]["count"], 47)
        self.assertEqual(self.unknowns["preset"]["count"], 1)
        self.assertEqual(self.unknowns["initialSun"]["count"], 43)
        self.assertEqual(self.unknowns["seedBank"]["count"], 39)
        self.assertEqual(self.unknowns["vasePlacement"]["count"], 46)
        self.assertEqual(self.unknowns["sunAmount"]["count"], 46)
        for kind, row in self.unknowns.items():
            self.assertTrue(row["detail"].startswith(kind + ":"), kind)
        # the per-level notes must agree with the global tally
        kinds: dict = {}
        for row in self.levels.values():
            for text in row["unknowns"]:
                kind = text.split(":", 1)[0]
                kinds[kind] = kinds.get(kind, 0) + 1
        self.assertEqual(kinds, self.counts["unknownKinds"])

    def test_colored_vases_and_firework_vases_are_kept(self) -> None:
        firework = sorted(level_id for level_id, row in self.levels.items()
                          if row["vaseGridItemType"])
        self.assertEqual(firework, ["lunarrainbowmarket_50", "lunarrainbowmarket_74",
                                    "modern_51"])
        for level_id in firework:
            self.assertEqual(self.levels[level_id]["vaseGridItemType"], "vase_firework")
        # the pack really does carry a joke value here; keep it verbatim
        self.assertEqual(self.levels["carnival_91"]["coloredVases"]["zombie"], 114514)
        self.assertEqual(self.levels["kongfu_83"]["coloredVases"]["zombie"], 40)
        blacklisted = {level_id: row["blacklistedCells"] for level_id, row
                       in self.levels.items() if row["blacklistedCells"] is not None}
        self.assertEqual(sorted(blacklisted),
                         ["egypt_57", "losantosvice_21", "muji_24", "pirate_41",
                          "plantagenet_18"])
        self.assertEqual(blacklisted["egypt_57"], [])
        self.assertEqual(blacklisted["pirate_41"], [[1, 0], [1, 4]])

    def test_render_is_byte_stable(self) -> None:
        first = vasebreaker.render(self.table)
        second = vasebreaker.render(load_shipped())
        self.assertEqual(first, second)
        raw = SHIPPED.read_bytes()
        self.assertEqual(raw, first.encode("utf-8"))
        self.assertNotIn(b"\r\n", raw)
        self.assertTrue(raw.endswith(b"\n"))


@unittest.skipUnless(HAS_OBB, "OBB package dump not available")
class CompileVasebreakerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = vasebreaker.compile_data(LEVELS_DIR, worlds.DEFAULT_OBB)

    def test_compile_reproduces_the_shipped_file(self) -> None:
        raw = SHIPPED.read_bytes()
        self.assertEqual(raw, vasebreaker.render(self.table).encode("utf-8"))

    def test_check_passes_on_the_shipped_file(self) -> None:
        self.assertEqual(vasebreaker.check(self.table, SHIPPED), 0)

    def test_check_fails_when_the_artefact_is_stale(self) -> None:
        stale = json.loads(SHIPPED.read_text(encoding="utf-8"))
        stale["levels"]["beach_69"]["vaseCount"] = 999
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vasebreaker.json"
            vasebreaker.dump(stale, path)
            self.assertEqual(vasebreaker.check(stale, path), 1)

    def test_vase_ids_all_resolve_against_the_pack(self) -> None:
        """No dangling zombie/plant id: the rows point at real types in the shipped data."""
        zombie_sheet = worlds.DEFAULT_OBB / "pkg_2115_ZombieType.json"
        zombies = set()
        with zombie_sheet.open(encoding="utf-8-sig") as handle:
            doc = json.load(handle)
        for obj in doc.get("objects") or []:
            name = (obj.get("objdata") or {}).get("TypeName")
            if name:
                zombies.add(name)
        pack = json.loads((vasebreaker.ROOT / "native" / "generated" / "content.pack")
                          .read_text(encoding="utf-8"))
        plants = {row["id"] for row in pack["plants"]}
        unknown = set()
        for level_id, row in self.table["levels"].items():
            for item in row["vases"]:
                if item["type"] == "zombie" and item["zombieId"] not in zombies:
                    unknown.add(("zombie", item["zombieId"]))
                if item["type"] == "plant" and item["plantId"] not in plants:
                    unknown.add(("plant", item["plantId"]))
        self.assertEqual(unknown, set())

    def test_missing_package_degrades_to_unknowns_not_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            levels = Path(tmp) / "levels"
            levels.mkdir()
            (levels / "fake_1.json").write_text(json.dumps({
                "id": "fake_1",
                "extra": {"vasebreaker": True, "package": "pkg_9999"},
            }), encoding="utf-8")
            table = vasebreaker.compile_data(levels, worlds.DEFAULT_OBB)
        row = table["levels"]["fake_1"]
        self.assertIsNone(row["vaseCount"])
        self.assertEqual(row["vases"], [])
        self.assertIsNone(row["initialSun"])
        self.assertFalse(row["preset"]["found"])
        self.assertTrue(any(text.startswith("package:") for text in row["unknowns"]))
        self.assertEqual(table["counts"]["vaseTotal"], 0)


if __name__ == "__main__":
    unittest.main()
