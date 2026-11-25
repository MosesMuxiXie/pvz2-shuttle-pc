"""Pins the derived plant behaviour families to the shipped pack and to the labels.

The families come from `native/generated/content.pack` (actions, HP, cost,
framework) plus the two original sheets `pkg_2073_PlantPropertySheet`
(`IsInstant`, `IsConsumable`, `ProjectileLobHeight`) and
`pkg_2082_ProjectilePropertySheet` (launch vector, base damage) - see
`tools/contentc/pfamilies.py` for the rule table.

Two kinds of check live here:

* coverage - all 339 pack plants get exactly one of the eleven engine families;
* supervision - the 44 plants that also exist in `content/plants.json` carry a
  hand-written `behavior`, and the derived family must agree with at least 90%
  of them. The two known disagreements are asserted by name so that a rule
  change cannot silently swap one explanation for another.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import contentc.pfamilies as pfamilies  # noqa: E402
import contentc.worlds as worlds  # noqa: E402

PACK = pfamilies.DEFAULT_PACK
CONTENT = worlds.DEFAULT_CONTENT
OBB = worlds.DEFAULT_OBB
GENERATED = pfamilies.DEFAULT_OUT

HAS_PACK = PACK.is_file()
HAS_SHEETS = OBB.is_dir()

# Plants whose actions carry no `kind` at all in the pack. They are classified
# from their known actions and listed in the table + report on purpose instead
# of being dropped.
UNKNOWN_KIND_PLANTS = {"magnifyinggrass", "minigame_music"}

# The two plants where the pack and the content table disagree, with the reason
# spelled out in docs/reviews/2026-11-20-plant-families.md.
KNOWN_DISAGREEMENTS = {"begonia", "frozenpear"}


def build_table() -> dict:
    return pfamilies.generate(PACK, OBB, CONTENT)


@unittest.skipUnless(HAS_PACK, f"{PACK} is missing; run the pack builder first")
@unittest.skipUnless(HAS_SHEETS, f"{OBB} is missing; the trajectory rules need it")
class PlantFamiliesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = build_table()
        cls.entries = {entry["id"]: entry for entry in cls.table["plants"]}

    # -- coverage ---------------------------------------------------------

    def test_every_pack_plant_gets_one_family(self):
        pack = json.loads(PACK.read_text(encoding="utf-8"))
        pack_ids = {plant["id"] for plant in pack["plants"]}

        self.assertEqual(len(self.table["plants"]), 339)
        self.assertEqual(len(pack_ids), 339)
        self.assertEqual(set(self.entries), pack_ids)

    def test_entries_are_sorted_unique_and_typed(self):
        ids = [entry["id"] for entry in self.table["plants"]]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(set(ids)), len(ids))
        for entry in self.table["plants"]:
            self.assertIn(entry["family"], pfamilies.FAMILIES)
            self.assertIn(entry["source"], {"pack", "content"})
            self.assertTrue(entry["evidence"].startswith("rule=R"), entry["evidence"])
            self.assertTrue(entry["framework"], entry["id"])

    def test_every_family_is_used(self):
        counts = self.table["counts"]["byFamily"]
        self.assertEqual(set(counts), set(pfamilies.FAMILIES))
        empty = [family for family, count in counts.items() if count == 0]
        self.assertEqual(empty, [], f"families with no plant at all: {empty}")
        self.assertEqual(sum(counts.values()), 339)

    def test_sources_split_between_pack_and_content(self):
        counts = self.table["counts"]
        self.assertEqual(counts["labelled"], 44)
        self.assertEqual(counts["unlabelled"], 295)
        self.assertEqual(counts["labelled"] + counts["unlabelled"], counts["plants"])

    # -- supervision: the 44 labelled plants ------------------------------

    def test_labelled_agreement_meets_the_bar(self):
        labels = self.table["labels"]
        self.assertEqual(labels["compared"], 44)
        self.assertGreaterEqual(
            labels["agreement"],
            pfamilies.MIN_LABEL_AGREEMENT,
            "derived families drifted away from content/plants.json: "
            + json.dumps(labels["disagreements"], ensure_ascii=False),
        )

    def test_disagreements_are_the_two_documented_ones(self):
        found = {item["id"] for item in self.table["labels"]["disagreements"]}
        self.assertEqual(
            found,
            KNOWN_DISAGREEMENTS,
            "unexpected label disagreement; update the rule table and the review, "
            "do not just widen the accepted set",
        )
        by_id = {item["id"]: item for item in self.table["labels"]["disagreements"]}
        self.assertEqual(by_id["begonia"]["family"], "shoot")
        self.assertEqual(by_id["begonia"]["label"], "lob")
        self.assertEqual(by_id["frozenpear"]["family"], "support")
        self.assertEqual(by_id["frozenpear"]["label"], "instant")

    def test_labelled_plants_match_the_content_behaviour_field(self):
        content = json.loads((CONTENT / "plants.json").read_text(encoding="utf-8"))
        labels = {plant["id"]: plant["behavior"] for plant in content if plant.get("behavior")}
        compared = 0
        for plant_id, behaviour in labels.items():
            entry = self.entries.get(plant_id)
            if entry is None:
                continue
            compared += 1
            self.assertEqual(entry["source"], "content", plant_id)
            self.assertIn(f"label={behaviour}", entry["evidence"], plant_id)
        self.assertEqual(compared, 44)

    # -- the plants the pack cannot describe ------------------------------

    def test_unknown_kind_plants_are_listed_and_handled(self):
        listed = self.table["unknownKinds"]
        self.assertEqual({item["id"] for item in listed}, UNKNOWN_KIND_PLANTS)
        for item in listed:
            self.assertIn(item["family"], pfamilies.FAMILIES)
            self.assertTrue(item["handling"])
            self.assertIn("unknown", self.entries[item["id"]]["evidence"])

    def test_unknown_kinds_match_the_pack(self):
        pack = json.loads(PACK.read_text(encoding="utf-8"))
        expected = {
            plant["id"]
            for plant in pack["plants"]
            if any(action.get("kind") in (None, "unknown") for action in plant["actions"])
        }
        self.assertEqual(expected, UNKNOWN_KIND_PLANTS)

    def test_catch_all_rule_stays_marginal(self):
        catch_all = [
            entry["id"] for entry in self.table["plants"] if entry["rule"] == "R21-support/catch-all"
        ]
        self.assertLessEqual(
            len(catch_all), 5, f"the catch-all rule is eating the table: {catch_all}"
        )

    # -- the generated file ------------------------------------------------

    def test_generation_is_deterministic(self):
        self.assertEqual(pfamilies.render(build_table()), pfamilies.render(self.table))

    @unittest.skipUnless(GENERATED.is_file(), f"{GENERATED} is missing; run the tool")
    def test_generated_file_is_current(self):
        self.assertEqual(GENERATED.read_text(encoding="utf-8"), pfamilies.render(self.table))

    @unittest.skipUnless(GENERATED.is_file(), f"{GENERATED} is missing; run the tool")
    def test_check_passes_on_the_shipped_file(self):
        self.assertEqual(pfamilies.check(self.table, GENERATED), 0)


class DecideTests(unittest.TestCase):
    """Single-plant checks for the rules that carry the most weight."""

    @staticmethod
    def plant(**kwargs) -> pfamilies.Plant:
        payload = {
            "id": "specimen",
            "framework": "PlantPeashooter",
            "prop_name": "SpecimenDefault",
            "anim_rig": "",
            "pop_anim": "",
            "hitpoints": 300,
            "cost": 100,
            "sun_producer": False,
            "height": "normal",
            "grid": "normal",
            "kinds": ("projectile",),
            "projectiles": (),
            "explode_actions": (),
            "special_damage": 0.0,
            "sun_action": False,
            "manual_action": False,
            "unknown_action": False,
            "needs_eating": False,
            "has_projectile_action": True,
            "projectile_action_damage": 0.0,
            "props": {},
        }
        payload.update(kwargs)
        return pfamilies.Plant(**payload)

    def test_trajectory_classification(self):
        self.assertEqual(pfamilies.classify_trajectory({"InitialVelocity": [333, 0, 0]}), "straight")
        self.assertEqual(pfamilies.classify_trajectory({"InitialVelocity": [0, 0, -500]}), "drop")
        self.assertEqual(
            pfamilies.classify_trajectory(
                {"InitialVelocity": [300, 10, 600], "InitialAcceleration": [0, 0, -10]}
            ),
            "arc",
        )
        self.assertEqual(pfamilies.classify_trajectory({}), "unknown")

    def test_sun_producer_without_an_attack_is_produce(self):
        plant = self.plant(sun_producer=True, kinds=(), has_projectile_action=False)
        family, rule, _ = pfamilies.decide(plant, {})
        self.assertEqual((family, rule), ("produce", "R02-produce/sun-producer"))

    def test_mine_needs_its_own_name_not_the_shared_rig(self):
        action = {"kind": "explode", "trigger": "rect", "damage": None}
        mine = self.plant(
            id="potatomine",
            framework="PlantPotatomine",
            kinds=("explode",),
            explode_actions=(action,),
            has_projectile_action=False,
        )
        chip = self.plant(
            id="potatochip",
            prop_name="PotatochipDefault",
            framework="PlantPotatomine",
            anim_rig="PlantAnimRig_PotatoMine",
            kinds=("explode",),
            explode_actions=(action,),
            has_projectile_action=False,
        )
        self.assertEqual(pfamilies.decide(mine, {})[0], "mine")
        self.assertEqual(pfamilies.decide(chip, {})[0], "instant")

    def test_impact_explosion_does_not_make_a_shooter_instant(self):
        plant = self.plant(
            id="gardenia",
            kinds=("projectile", "explode"),
            explode_actions=({"kind": "explode", "trigger": "rect_grid", "damage": 600},),
        )
        self.assertEqual(pfamilies.decide(plant, {})[0], "shoot")

    def test_plant_food_explosion_does_not_make_a_shooter_instant(self):
        plant = self.plant(
            id="torchwood",
            kinds=("special", "explode"),
            explode_actions=({"kind": "explode", "trigger": "manual", "damage": 900},),
            has_projectile_action=False,
        )
        self.assertEqual(pfamilies.decide(plant, {})[0], "support")

    def test_big_manual_detonation_is_an_instant(self):
        plant = self.plant(
            id="hotdate",
            framework="PlantHotDate",
            kinds=("explode",),
            explode_actions=({"kind": "explode", "trigger": "manual", "damage": 1200},),
            has_projectile_action=False,
        )
        family, rule, _ = pfamilies.decide(plant, {})
        self.assertEqual((family, rule), ("instant", "R09b-instant/manual-detonation"))

    def test_melee_special_without_a_projectile_is_spike(self):
        plant = self.plant(
            id="bonkchoy", kinds=("special",), special_damage=60.0, has_projectile_action=False
        )
        self.assertEqual(pfamilies.decide(plant, {})[0], "spike")

    def test_arc_projectile_is_lob(self):
        projectiles = {
            "Arc": pfamilies.Projectile(
                name="Arc", traj="arc", damage=40.0, splash=0.0, klass=""
            )
        }
        plant = self.plant(id="cabbagepult", projectiles=("Arc",))
        self.assertEqual(pfamilies.decide(plant, projectiles)[0], "lob")

    def test_flat_projectile_is_shoot(self):
        projectiles = {
            "Pea": pfamilies.Projectile(
                name="Pea", traj="straight", damage=20.0, splash=0.0, klass=""
            )
        }
        plant = self.plant(id="peashooter", projectiles=("Pea",))
        self.assertEqual(pfamilies.decide(plant, projectiles)[0], "shoot")


if __name__ == "__main__":
    unittest.main()
