"""Pins `native/generated/bosses_from_pack.json` to the original boss tables.

The shipped file is compiled by `tools/contentc/bosses.py` from
`work/obb_packages`; this test keeps it honest on two levels:

* structural checks read the *shipped* file only, so they run everywhere:
  counts, stage tables, spawn coordinates, dangling references, unknown worlds;
* a recompile check (skipped when the pack tree is absent) asserts that the
  compiler still produces the shipped bytes, twice over.

The three different stage totals are asserted together on purpose - the report
explains them, and a future change to the props de-duplication would show up
here instead of quietly moving one number:

    155  stages of the 50 mechs a battle module actually places (what an engine
         can reach; this is the table's `counts.stages`)
    227  stages after de-duplicating props aliases redefined per level package
    258  occurrence sum, i.e. the `258` quoted by the S5 data inventory
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import contentc.bosses as bosses  # noqa: E402
import contentc.worlds as worlds  # noqa: E402

OBB = worlds.DEFAULT_OBB
GENERATED = bosses.DEFAULT_OUT
REPORT = bosses.DEFAULT_REPORT
CLIENT = bosses.DEFAULT_CLIENT

HAS_GENERATED = GENERATED.is_file()
HAS_REPORT = REPORT.is_file()
HAS_CLIENT = CLIENT.is_file()
HAS_OBB = OBB.is_dir()

# The stage total an engine can reach, the de-duplicated props total and the
# occurrence total - all three were measured, none of them is a guess.
STAGES_PLACED = 155
STAGES_DISTINCT_PROPS = 227
STAGES_OCCURRENCES = 258

# Bosses named in the task as spot checks.
RENAI_STAGES = 6
EIGHTIES_STAGES = 5
EGYPT_STAGES = 3

# (mech id, reserved columns, gridX, gridY) straight out of
# `ZombossBattleModuleProperties` in the level packages named in the comment.
SPAWN_CASES = (
    ("zombossmech_beach", 3, 6, 3),  # pkg_0331_LevelDefinition, BeachBossStage
    ("zombossmech_skycity", 3, 7, 2),  # pkg_1219_LevelDefinition, SkyCityBossStage
    ("zombossmech_heian", 3, 0, 3),  # pkg_1328_LevelDefinition, HeianBossStage
)

FIRE_FIELDS = (
    "FireMinColumn",
    "FireMaxColumn",
    "FireRowRange",
    "FireRocketSpeed",
    "FireRocketHitTime",
)


def load_shipped() -> dict:
    return json.loads(GENERATED.read_text(encoding="utf-8"))


@unittest.skipUnless(HAS_GENERATED, f"{GENERATED} is missing; run tools/contentc/bosses.py")
class ShippedBossTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = load_shipped()
        cls.counts = cls.table["counts"]
        cls.bosses = cls.table["bosses"]
        cls.by_id = {boss["id"]: boss for boss in cls.bosses}

    # ---- shape -----------------------------------------------------------

    def test_format_and_generator(self) -> None:
        self.assertEqual(self.table["format"], bosses.FORMAT)
        self.assertEqual(self.table["generated"], bosses.GENERATED)

    def test_bosses_sorted_and_unique(self) -> None:
        ids = [boss["id"] for boss in self.bosses]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(set(ids)))

    def test_counts_match_the_table(self) -> None:
        self.assertEqual(self.counts["bosses"], 50)
        self.assertEqual(self.counts["bosses"], len(self.bosses))
        self.assertEqual(self.counts["placements"], 75)
        self.assertEqual(
            self.counts["placements"],
            sum(len(boss["placements"]) for boss in self.bosses),
        )
        self.assertEqual(self.counts["zombieTypes"], 1127)
        self.assertEqual(self.counts["missingActions"], 0)

    # ---- (a) stage totals ------------------------------------------------

    def test_stage_totals(self) -> None:
        self.assertEqual(self.counts["stages"], STAGES_PLACED)
        self.assertEqual(
            sum(boss["stageCount"] for boss in self.bosses), STAGES_PLACED
        )
        totals = self.counts["stageTotals"]
        self.assertEqual(totals["placedMechs"], STAGES_PLACED)
        self.assertEqual(totals["distinctMechProps"], STAGES_DISTINCT_PROPS)
        self.assertEqual(totals["occurrences"], STAGES_OCCURRENCES)

    def test_every_stage_has_pack_health(self) -> None:
        for boss in self.bosses:
            self.assertEqual(len(boss["stages"]), boss["stageCount"], boss["id"])
            for position, stage in enumerate(boss["stages"]):
                self.assertEqual(stage["index"], position, boss["id"])
                self.assertIsInstance(stage["hitPoints"], int, boss["id"])
                self.assertGreater(stage["hitPoints"], 0, boss["id"])
                self.assertIsInstance(stage["stunSeconds"], (int, float), boss["id"])
                self.assertIsInstance(stage["idleSeconds"], dict, boss["id"])

    # ---- (b) named bosses ------------------------------------------------

    def test_renai_has_six_stages(self) -> None:
        boss = self.by_id["zombossmech_renai"]
        self.assertEqual(boss["stageCount"], RENAI_STAGES)
        self.assertEqual(
            [stage["hitPoints"] for stage in boss["stages"]],
            [6000, 21300, 8000, 21300, 11000, 21300],
        )

    def test_eighties_has_five_stages(self) -> None:
        boss = self.by_id["zombossmech_eighties"]
        self.assertEqual(boss["stageCount"], EIGHTIES_STAGES)
        for name in [key for key in self.by_id if key.startswith("zombossmech_eighties")]:
            self.assertEqual(self.by_id[name]["stageCount"], EIGHTIES_STAGES, name)

    def test_egypt_has_three_stages(self) -> None:
        boss = self.by_id["zombossmech_egypt"]
        self.assertEqual(boss["stageCount"], EGYPT_STAGES)
        self.assertEqual(
            [stage["hitPoints"] for stage in boss["stages"]], [4000, 8000, 6500]
        )

    # ---- (c) spawn coordinates -------------------------------------------

    def test_spawn_coordinates(self) -> None:
        for mech, columns, grid_x, grid_y in SPAWN_CASES:
            boss = self.by_id[mech]
            spawn = boss["spawn"]
            self.assertEqual(spawn["reservedColumns"], columns, mech)
            self.assertEqual(spawn["gridX"], grid_x, mech)
            self.assertEqual(spawn["gridY"], grid_y, mech)
            self.assertTrue(str(spawn["module"]).startswith("pkg_"), mech)
            self.assertTrue(str(spawn["stageModule"]), mech)

    def test_every_spawn_names_a_placement(self) -> None:
        for boss in self.bosses:
            modules = {placement["module"] for placement in boss["placements"]}
            self.assertIn(boss["spawn"]["module"], modules, boss["id"])
            self.assertEqual(boss["modulePkg"], boss["spawn"]["module"])
            for placement in boss["placements"]:
                self.assertIn("gridX", placement)
                self.assertIn("stageSelection", placement)

    # ---- (e) unknown worlds are kept -------------------------------------

    def test_unknown_worlds_are_preserved(self) -> None:
        unknown = [boss for boss in self.bosses if boss["world"].startswith("unknown:")]
        self.assertTrue(unknown, "no unknown world rows survived")
        # the compile counts must agree with the rows themselves
        seen: dict[str, int] = {}
        for boss in unknown:
            seen[boss["world"]] = seen.get(boss["world"], 0) + 1
        self.assertEqual(seen, dict(sorted(self.counts["unknownWorlds"].items())))
        self.assertIn("unknown:ChildStage", seen)
        # the placements that cannot be attributed keep their stage name verbatim
        for boss in unknown:
            self.assertEqual(
                boss["world"], "unknown:%s" % boss["spawn"]["stageModule"]
            )

    def test_unattributed_stage_names_are_reported(self) -> None:
        self.assertEqual(
            self.counts["unknownPlacements"],
            {"unknown:ChildStage": 2, "unknown:JoustStage": 1, "unknown:Stage": 1},
        )

    # ---- (f) fire payload ------------------------------------------------

    def test_fire_action_keeps_five_pack_fields(self) -> None:
        fire = [
            action
            for boss in self.bosses
            for stage in boss["stages"]
            for action in stage["actions"]
            if action["type"] == "ZombossFireActionDefinition"
        ]
        self.assertTrue(fire, "no ZombossFireActionDefinition survived")
        complete = [
            action
            for action in fire
            if all(field in action["fields"] for field in FIRE_FIELDS)
        ]
        self.assertTrue(complete, "no fire action carries all five fields")
        sample = complete[0]["fields"]
        self.assertEqual(sample["FireRocketSpeed"], 500)
        self.assertEqual(sample["FireRocketHitTime"], 0.75)

    def test_actions_are_pack_objects(self) -> None:
        for boss in self.bosses:
            for stage in boss["stages"]:
                for action in stage["actions"]:
                    self.assertTrue(action["rtid"].startswith("RTID("), action["rtid"])
                    self.assertTrue(action["alias"], action["rtid"])
                    if action.get("missing"):
                        continue
                    self.assertTrue(action["type"].endswith("ActionDefinition"), action["type"])
                    self.assertIsInstance(action["fields"], dict)
                    self.assertTrue(str(action["pkg"]).startswith("pkg_"), action["pkg"])

    # ---- dangling + unplaced --------------------------------------------

    def test_dangling_mech_is_flagged_not_dropped(self) -> None:
        self.assertEqual(self.counts["danglingMechs"], ["zombossmech_egypt_rift"])
        boss = self.by_id["zombossmech_egypt_rift"]
        self.assertTrue(boss["missingProps"])
        self.assertEqual(boss["stageCount"], 0)
        self.assertIsNone(boss["propsPkg"])
        self.assertEqual(self.counts["bossesWithoutStages"], 1)
        # it still keeps its placement, so the level it came from is traceable
        self.assertEqual(len(boss["placements"]), 1)
        self.assertEqual(boss["placements"][0]["module"], "pkg_0576_LevelDefinition")

    def test_unplaced_mechs_are_listed(self) -> None:
        unplaced = self.counts["unplacedMechs"]
        self.assertEqual(len(unplaced), 24)
        ids = [row["id"] for row in unplaced]
        self.assertEqual(ids, sorted(ids))
        for row in unplaced:
            self.assertGreater(row["stageCount"], 0, row["id"])
            self.assertNotIn(row["id"], self.by_id, row["id"])
            self.assertTrue(str(row["propsPkg"]).startswith("pkg_"), row["id"])

    def test_cross_world_mechs(self) -> None:
        cross = self.counts["crossWorldMechs"]
        self.assertTrue(cross)
        for mech in cross:
            self.assertGreater(len(self.by_id[mech]["worlds"]), 1, mech)

    # ---- pack original vs inference --------------------------------------

    def test_resolution_and_world_source(self) -> None:
        for boss in self.bosses:
            self.assertIn(boss["resolution"], ("zombietype", "alias-guess"))
            self.assertEqual(boss["worldSource"], "stage-prefix-inference")
            self.assertEqual(boss["source"], "pack")
            self.assertIn(boss["world"], boss["worlds"])
        self.assertEqual(
            [boss["id"] for boss in self.bosses if boss["resolution"] == "alias-guess"],
            ["zombossmech_egypt_rift"],
        )

    # ---- world coverage --------------------------------------------------

    def test_client_world_coverage(self) -> None:
        client_worlds = set(bosses.CLIENT_WORLDS)
        covered = {
            world for world in self.counts["placementsByWorld"] if world in client_worlds
        }
        self.assertEqual(len(client_worlds), 26)
        self.assertEqual(len(covered), 23)
        missing = sorted(client_worlds - covered)
        self.assertEqual(missing, ["frontyard", "memorytour", "muji"])

    @unittest.skipUnless(HAS_CLIENT, f"{CLIENT} is missing")
    def test_client_comparison_differs_from_pack(self) -> None:
        client = bosses.load_client_bosses(CLIENT)
        self.assertEqual(len(client), 26)
        rows = {row["world"]: row for row in bosses.client_comparison(self.bosses, client)}
        egypt = rows["egypt"]
        # pack: 4000 + 8000 + 6500 (+ the egypt2/modern_egypt tables); the
        # client ladder says 8200 for the whole world.
        self.assertEqual(egypt["clientHp"], 8200)
        self.assertEqual(egypt["clientStages"], 3)
        self.assertGreater(egypt["packHpTotal"], egypt["clientHp"])
        self.assertNotEqual(egypt["hpDelta"], 0)
        # every client row is the same three-phase shape, the pack never is
        for world, row in rows.items():
            if row["clientId"]:
                self.assertEqual(row["clientStages"], 3, world)

    # ---- shipped report --------------------------------------------------

    @unittest.skipUnless(HAS_REPORT, f"{REPORT} is missing")
    def test_report_has_required_sections(self) -> None:
        text = REPORT.read_text(encoding="utf-8")
        for heading in (
            "## 0. 计数",
            "## 1. 哪些是 pack 原值、哪些是推断",
            "## 2. 每世界一行",
            "## 3. stage → world 推断表",
            "## 4. unknown 归属",
            "## 4b. 悬空引用",
            "## 4c. 有完整阶段表",
            "## 5. 零数据世界",
            "## 6. 与 `content/bosses.json` 的对比",
        ):
            self.assertIn(heading, text)
        self.assertIn("### 三个具体例子", text)
        # every boss id appears in the per-world table
        for boss in self.bosses:
            self.assertIn("`%s`" % boss["id"], text)

    def test_check_passes_on_the_shipped_file(self) -> None:
        self.assertEqual(bosses.check(load_shipped(), GENERATED), 0)


@unittest.skipUnless(HAS_OBB, f"{OBB} is missing; cannot recompile")
@unittest.skipUnless(HAS_GENERATED, f"{GENERATED} is missing")
class BossRecompileTests(unittest.TestCase):
    """The compile must be reproducible byte for byte."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.first = bosses.compile_bosses(OBB)
        cls.second = bosses.compile_bosses(OBB)
        cls.shipped = GENERATED.read_text(encoding="utf-8")

    def test_dump_is_deterministic(self) -> None:
        self.assertEqual(bosses.render(self.first), bosses.render(self.second))

    def test_shipped_file_matches_a_fresh_compile(self) -> None:
        self.assertEqual(self.shipped, bosses.render(self.first))

    def test_recompiled_counts_match_the_shipped_ones(self) -> None:
        shipped = load_shipped()
        self.assertEqual(self.first["counts"], shipped["counts"])
        self.assertEqual(
            [boss["id"] for boss in self.first["bosses"]],
            [boss["id"] for boss in shipped["bosses"]],
        )


if __name__ == "__main__":
    unittest.main()
