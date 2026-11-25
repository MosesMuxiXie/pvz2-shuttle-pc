"""Tests for tools/contentc/loot_binding.py — the per-level loot / present-table binding.

Two groups, mirroring ``test_rewards.py``:

* ``ShippedLootBindingTests`` only reads ``native/generated/loot_binding.json`` (plus the
  sibling ``level_mechanics.json``), so it runs without the OBB and still proves the
  shipped product is complete: 1809 levels, 47 non-default loot keys, 68 dangling
  present-table references surfaced as unknowns.
* ``CompileLootBindingTests`` needs ``work/obb_packages`` and recompiles once; it proves
  the shipped file is the output of the current code, byte for byte, and checks three
  spot levels field by field against the original ``LevelDefinition`` packages.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from contentc import loot_binding as lb  # noqa: E402

SHIPPED = lb.DEFAULT_JSON
HAS_OBB = lb.DEFAULT_OBB.is_dir()
MECHANICS = lb.ROOT / "native" / "generated" / "level_mechanics.json"

REQUIRED_FIELDS = ("package", "lootKey", "lootRtid", "presentTable", "presentSource", "modules")
OPTIONAL_TRUE = ("danger", "whack", "noLoot", "presentTableDangling")


def load_shipped() -> dict:
    with SHIPPED.open(encoding="utf-8") as handle:
        return json.load(handle)


class ShippedLootBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = load_shipped()
        cls.levels: dict = cls.table["levels"]

    # -- 1 ------------------------------------------------------------------ #
    def test_header_and_constants(self) -> None:
        self.assertEqual(self.table["format"], "pvz2-shuttle/loot-binding@1")
        self.assertEqual(self.table["generated"], "loot-binding-compile-v1")
        self.assertTrue(self.table["generatedAt"].startswith("sha256:"))
        self.assertEqual(len(self.table["generatedAt"]), len("sha256:") + 16)
        self.assertEqual(self.table["sources"]["levels"]["files"], 1809)
        self.assertEqual(self.table["sources"]["obb"]["levelPackages"], 1809)

    # -- 2 ------------------------------------------------------------------ #
    def test_every_level_has_the_contract_fields(self) -> None:
        for level_id, record in self.levels.items():
            for field in REQUIRED_FIELDS:
                self.assertIn(field, record, f"{level_id} missing {field}")
            self.assertIn(
                record["presentSource"],
                lb.PRESENT_SOURCES,
                f"{level_id} has an unknown presentSource",
            )
            self.assertIsInstance(record["modules"], list)
            for flag in OPTIONAL_TRUE:
                if flag in record:
                    self.assertIs(record[flag], True, f"{level_id}.{flag} must be literal true")
            if record["lootKey"] is not None:
                self.assertIn(record["lootKey"], ("default", "danger", "whack"))

    # -- 3 ------------------------------------------------------------------ #
    def test_all_1809_client_levels_are_covered(self) -> None:
        self.assertEqual(len(self.levels), 1809)
        self.assertEqual(self.table["counts"]["levels"], 1809)
        with MECHANICS.open(encoding="utf-8") as handle:
            mechanics = json.load(handle)
        self.assertEqual(set(self.levels), set(mechanics["levels"]))
        # the same package mapping, from two independent generated artifacts
        for level_id in ("beach_1", "egypt_1", "modern_1"):
            self.assertEqual(
                self.levels[level_id]["package"],
                mechanics["levels"][level_id]["source"]["package"],
            )

    # -- 4 ------------------------------------------------------------------ #
    def test_danger_whack_and_noloot_are_distinguishable(self) -> None:
        danger = {k for k, v in self.levels.items() if v.get("danger")}
        whack = {k for k, v in self.levels.items() if v.get("whack")}
        no_loot = {k for k, v in self.levels.items() if v.get("noLoot")}
        self.assertEqual(len(danger), 13)
        self.assertEqual(len(whack), 1)
        self.assertEqual(len(no_loot), 26)
        self.assertFalse(danger & whack)
        self.assertFalse(danger & no_loot)
        self.assertFalse(whack & no_loot)
        # the three kinds are exactly the levels whose key is not `default`
        non_default = {
            k for k, v in self.levels.items() if v.get("lootKey") in ("danger", "whack")
        }
        self.assertEqual(non_default, danger | whack)
        for level_id in danger:
            self.assertEqual(self.levels[level_id]["lootKey"], "danger")
        for level_id in whack:
            self.assertEqual(self.levels[level_id]["lootKey"], "whack")
        for level_id in no_loot:
            self.assertIsNone(self.levels[level_id]["lootKey"])
        self.assertEqual(len(danger) + len(whack) + len(no_loot), 40)
        # 40 kind-flagged + 7 with no Loot field at all = the 47 non-default levels
        self.assertEqual(self.table["counts"]["lootFieldMissing"], 7)
        self.assertEqual(47, 40 + 7)

    # -- 5 ------------------------------------------------------------------ #
    def test_counts_reconcile_with_the_records(self) -> None:
        counts = self.table["counts"]
        by_key = counts["byLootKey"]
        self.assertEqual(sum(by_key.values()), 1809)
        self.assertEqual(by_key["default"], 1762)
        self.assertEqual(by_key["danger"], 13)
        self.assertEqual(by_key["whack"], 1)
        self.assertEqual(by_key["none"], 26 + 7)
        self.assertEqual(
            counts["withLootKey"],
            sum(1 for v in self.levels.values() if v["lootKey"] is not None),
        )
        self.assertEqual(counts["withLootKey"] + by_key["none"], 1809)

        by_source = counts["byPresentSource"]
        self.assertEqual(set(by_source), set(lb.PRESENT_SOURCES))
        self.assertEqual(sum(by_source.values()), 1809)
        self.assertEqual(
            by_source["level"],
            sum(1 for v in self.levels.values() if v["presentSource"] == "level"),
        )
        self.assertEqual(by_source["level"], 1635)
        self.assertEqual(by_source["default"], 174)
        self.assertEqual(
            by_source["level"] + by_source["default"] + by_source["world"], 1809
        )

        self.assertEqual(sum(counts["byPresentTable"].values()), 1809)
        self.assertEqual(sum(counts["byShinyPresentTable"].values()), 1809)
        self.assertEqual(sum(counts["byWorld"].values()), 1809)
        self.assertEqual(counts["noLoot"], 26)
        self.assertEqual(counts["danger"], 13)
        self.assertEqual(counts["whack"], 1)

    # -- 6 ------------------------------------------------------------------ #
    def test_dangling_present_tables_are_surfaced_not_silent(self) -> None:
        counts = self.table["counts"]
        self.assertEqual(counts["presentTableDangling"], 68)
        self.assertEqual(counts["presentTableDanglingNames"], 12)

        entry = next(
            item for item in self.table["unknowns"] if item["kind"] == "present-table-dangling"
        )
        self.assertEqual(entry["count"], 68)
        self.assertEqual(len(entry["tables"]), 12)
        self.assertEqual(sum(row["levels"] for row in entry["tables"]), 68)

        # every dangling reference is also flagged on the level record itself
        flagged_normal = sum(
            1 for v in self.levels.values() if v.get("presentTableDangling")
        )
        self.assertEqual(flagged_normal, 34)
        names = {row["name"] for row in entry["tables"]}
        for row in entry["tables"]:
            self.assertIn(row["roles"][0], ("normal", "shiny"))
        # a dangling name never resolves to a shipped table
        for name in names:
            self.assertNotIn(name, self.table["sources"]["presentTables"])
        # `heian_normal_01` is the one name used in both roles
        both = [row for row in entry["tables"] if len(row["roles"]) == 2]
        self.assertEqual([row["name"] for row in both], ["heian_normal_01"])

    # -- 7 ------------------------------------------------------------------ #
    def test_world_present_table_source_is_declared_unused(self) -> None:
        self.assertEqual(self.table["counts"]["byPresentSource"]["world"], 0)
        entry = next(
            item
            for item in self.table["unknowns"]
            if item["kind"] == "present-source-world-unused"
        )
        self.assertEqual(entry["count"], 0)
        self.assertIn("WorldData", entry["detail"])

    # -- 8 ------------------------------------------------------------------ #
    def test_loot_keys_come_from_the_shipped_tables(self) -> None:
        known = set(self.table["sources"]["lootTables"])
        self.assertEqual(known, {"danger", "default", "whack"})
        for level_id, record in self.levels.items():
            if record["lootKey"] is None:
                continue
            self.assertIn(record["lootKey"], known, level_id)

    # -- 9 ------------------------------------------------------------------ #
    def test_spot_check_six_shipped_records(self) -> None:
        expected = {
            "beach_1": {
                "package": "pkg_0325_LevelDefinition.json",
                "lootKey": "default",
                "lootRtid": "RTID(DefaultLoot@LevelModules)",
                "presentTable": "egypt_normal_01",
                "shinyPresentTable": "egypt_shiny_01",
                "presentSource": "level",
            },
            "beach_20": {
                "package": "pkg_0582_LevelDefinition.json",
                "lootKey": "whack",
                "lootRtid": "RTID(WhackLoot@LevelModules)",
                "presentTable": "egypt_normal_01",
                "presentSource": "level",
                "whack": True,
            },
            "beach_95": {
                "package": "pkg_0340_LevelDefinition.json",
                "lootKey": "danger",
                "lootRtid": "RTID(DangerRoomLoot@LevelModules)",
                "presentTable": "egypt_normal_01",
                "presentSource": "level",
                "danger": True,
            },
            "carnival_41": {
                "package": "pkg_0313_LevelDefinition.json",
                "lootKey": None,
                "lootRtid": "RTID(NoLoot@LevelModules)",
                "presentTable": "egypt_normal_01",
                "presentSource": "level",
                "noLoot": True,
            },
            "beach_68": {
                "package": "pkg_0550_LevelDefinition.json",
                "lootKey": "default",
                "lootRtid": "RTID(DefaultLoot@LevelModules)",
                "presentTable": None,
                "presentSource": "default",
            },
        }
        for level_id, fields in expected.items():
            record = self.levels[level_id]
            for field, value in fields.items():
                self.assertEqual(record.get(field), value, f"{level_id}.{field}")

    # -- 10 ----------------------------------------------------------------- #
    def test_comment_marker_objects_never_become_modules(self) -> None:
        for level_id, record in self.levels.items():
            for module in record["modules"]:
                self.assertTrue(module, level_id)
                self.assertTrue(
                    lb.is_loot_module(module), f"{level_id} kept non-loot module {module!r}"
                )
                self.assertNotIn("/", module)
        # the 8 comment markers (`//`, `#### ... ####`) live in these packages
        for level_id in ("chinesegarden_61", "chinesegarden_65"):
            self.assertIsInstance(self.levels[level_id]["modules"], list)


class UnitLootBindingTests(unittest.TestCase):
    """The resolution rules, without touching the OBB."""

    def _record(self, objdata: dict, objs: list[dict] | None = None, world_tables=None) -> dict:
        doc = {
            "objects": [{"objclass": "LevelDefinition", "objdata": objdata}] + (objs or [])
        }
        return lb.level_record(
            {"id": "x_1", "package": "pkg_0001", "world": "beach"},
            doc,
            package_name="pkg_0001_LevelDefinition.json",
            defined_tables={"egypt_normal_01": Path("pkg_2079_PresentTable.json")},
            world_tables=world_tables or {},
        )

    def test_world_table_branch_supplies_the_present_table(self) -> None:
        record = self._record({"Loot": "RTID(DefaultLoot@LevelModules)"}, world_tables={"beach": "world_normal_01"})
        self.assertEqual(record["presentSource"], "world")
        self.assertEqual(record["presentTable"], "world_normal_01")
        self.assertNotIn("presentTableDangling", record)

    def test_level_table_wins_over_the_world_table(self) -> None:
        record = self._record(
            {"NormalPresentTable": "egypt_normal_01"}, world_tables={"beach": "world_normal_01"}
        )
        self.assertEqual(record["presentSource"], "level")
        self.assertEqual(record["presentTable"], "egypt_normal_01")
        self.assertNotIn("presentTableDangling", record)

    def test_default_source_when_nothing_declares_a_table(self) -> None:
        record = self._record({})
        self.assertEqual(record["presentSource"], "default")
        self.assertIsNone(record["presentTable"])
        self.assertIsNone(record["lootKey"])
        self.assertIsNone(record["lootRtid"])

    def test_dangling_flag_only_for_undeclared_names(self) -> None:
        known = self._record({"NormalPresentTable": "egypt_normal_01"})
        self.assertNotIn("presentTableDangling", known)
        unknown = self._record({"NormalPresentTable": "atlantis_normal_01"})
        self.assertIs(unknown["presentTableDangling"], True)

    def test_loot_override_and_seed_drop_modules_are_records(self) -> None:
        record = self._record(
            {"Loot": "RTID(DefaultLoot@LevelModules)"},
            objs=[
                {
                    "objclass": "LootOverrideModuleProperties",
                    "aliases": ["Sun"],
                    "objdata": {
                        "Overrides": [
                            {"ZombieType": "RTID(ra@ZombieTypes)", "LootOverride": "SmallSun"}
                        ]
                    },
                },
                {"objclass": "ZombieDeathSeedDropModuleProperties", "objdata": {}},
                {"objclass": "ZombieDropZombiesOnBoardActionDefinition", "objdata": {}},
                {"//": "comment marker"},
            ],
        )
        self.assertEqual(
            record["modules"],
            ["LootOverrideModuleProperties", "ZombieDeathSeedDropModuleProperties"],
        )
        self.assertEqual(
            record["lootOverrides"],
            [{"zombieType": "ra", "lootOverride": "SmallSun", "alias": "Sun"}],
        )

    def test_rtid_helpers(self) -> None:
        self.assertEqual(lb.rtid_name("RTID(DefaultLoot@LevelModules)"), "DefaultLoot")
        self.assertEqual(lb.rtid_domain("RTID(DefaultLoot@LevelModules)"), "LevelModules")
        self.assertIsNone(lb.rtid_name(None))
        self.assertIsNone(lb.rtid_name("DefaultLoot"))


@unittest.skipUnless(HAS_OBB, f"needs the OBB package dump at {lb.DEFAULT_OBB}")
class CompileLootBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = lb.compile_binding(lb.DEFAULT_OBB, lb.DEFAULT_LEVELS)
        cls.text = lb.dumps(cls.payload)
        cls.levels = cls.payload["levels"]

    # -- 11 ----------------------------------------------------------------- #
    def test_two_runs_are_byte_identical_and_match_the_shipped_file(self) -> None:
        again = lb.compile_binding(lb.DEFAULT_OBB, lb.DEFAULT_LEVELS)
        self.assertEqual(lb.dumps(again), self.text)
        self.assertEqual(SHIPPED.read_bytes(), self.text.encode("utf-8"))

    # -- 12 ----------------------------------------------------------------- #
    def test_three_levels_match_the_original_packages(self) -> None:
        packages = lb.index_level_packages(lb.DEFAULT_OBB)
        for level_id in ("beach_1", "beach_95", "carnival_41"):
            level = next(
                item for item in lb.load_client_levels(lb.DEFAULT_LEVELS) if item["id"] == level_id
            )
            doc = lb.load_json(packages[level["package"]])
            objdata = doc["objects"][0]["objdata"]
            record = self.levels[level_id]
            self.assertEqual(record["lootRtid"], objdata.get("Loot"))
            self.assertEqual(record["presentTable"], objdata.get("NormalPresentTable"))
            self.assertEqual(
                record.get("shinyPresentTable"), objdata.get("ShinyPresentTable")
            )
            self.assertEqual(record.get("danger", False), objdata.get("IsDangerRoom") is True)
            self.assertEqual(record["package"], packages[level["package"]].name)

    # -- 13 ----------------------------------------------------------------- #
    def test_danger_flag_matches_is_danger_room_in_the_packages(self) -> None:
        packages = lb.index_level_packages(lb.DEFAULT_OBB)
        levels = lb.load_client_levels(lb.DEFAULT_LEVELS)
        danger_by_loot = {k for k, v in self.levels.items() if v.get("danger")}
        danger_by_field = set()
        for level in levels:
            doc = lb.load_json(packages[level["package"]])
            if doc["objects"][0]["objdata"].get("IsDangerRoom") is True:
                danger_by_field.add(level["id"])
        self.assertEqual(len(danger_by_field), 13)
        self.assertEqual(danger_by_field, danger_by_loot)

    # -- 14 ----------------------------------------------------------------- #
    def test_loot_overrides_and_seed_drop_modules_are_extracted(self) -> None:
        counts = self.payload["counts"]
        self.assertEqual(
            counts["withLootModules"],
            {"LootOverrideModuleProperties": 11, "ZombieDeathSeedDropModuleProperties": 15},
        )
        overrides = {k: v["lootOverrides"] for k, v in self.levels.items() if v.get("lootOverrides")}
        self.assertEqual(len(overrides), 11)
        self.assertEqual(counts["lootOverrides"], sum(len(v) for v in overrides.values()))
        self.assertEqual(
            overrides["beach_88"],
            [{"zombieType": "lunar", "lootOverride": "LargeSun", "alias": "LeprechaunCoinOverride"}],
        )
        self.assertEqual(len(overrides["egypt_23"]), 7)
        seeds = [k for k, v in self.levels.items() if "ZombieDeathSeedDropModuleProperties" in v["modules"]]
        self.assertEqual(len(seeds), 15)

    # -- 15 ----------------------------------------------------------------- #
    def test_grep_mode_finds_the_class_names(self) -> None:
        self.assertEqual(lb.main(["--grep", "LootOverrideModuleProperties"]), 0)
        self.assertEqual(lb.main(["--grep", "ZombieDeathSeedDropModuleProperties"]), 0)
        self.assertEqual(lb.main(["--grep", "no-such-class-anywhere"]), 1)

    # -- 16 ----------------------------------------------------------------- #
    def test_missing_level_package_is_recorded_not_silent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            levels_dir = Path(directory)
            (levels_dir / "ghost_1.json").write_text(
                json.dumps(
                    {"id": "ghost_1", "world": "nowhere", "extra": {"package": "pkg_9999"}}
                ),
                encoding="utf-8",
            )
            payload = lb.compile_binding(lb.DEFAULT_OBB, levels_dir)
        record = payload["levels"]["ghost_1"]
        self.assertIsNone(record["package"])
        self.assertIsNone(record["lootKey"])
        self.assertEqual(record["presentSource"], "default")
        kinds = {item["kind"]: item["count"] for item in payload["unknowns"]}
        self.assertEqual(kinds.get("level-package-missing"), 1)

    # -- 17 ----------------------------------------------------------------- #
    def test_check_mode_is_idempotent_and_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "loot_binding.json"
            out.write_bytes(self.text.encode("utf-8"))
            self.assertEqual(lb.main(["--check", "--out", str(out)]), 0)
            self.assertEqual(lb.main(["--check", "--out", str(out)]), 0)

            drifted = json.loads(self.text)
            drifted["counts"]["levels"] = 1
            out.write_text(json.dumps(drifted), encoding="utf-8")
            self.assertEqual(lb.main(["--check", "--out", str(out)]), 1)

            out.unlink()
            self.assertEqual(lb.main(["--check", "--out", str(out)]), 1)


if __name__ == "__main__":
    unittest.main()
