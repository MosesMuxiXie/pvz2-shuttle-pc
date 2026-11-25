"""Tests for tools/contentc/rewards.py — the original data's coin/key/loot economy.

Two groups:

* `ShippedRewardTests` only reads `native/generated/rewards_from_pack.json`, so it runs
  anywhere (CI without the OBB still checks the shipped product is complete).
* `CompileRewardTests` needs the OBB and recompiles, proving the shipped file is the
  output of the current code (byte for byte).
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from contentc import rewards, worlds  # noqa: E402

SHIPPED = rewards.DEFAULT_OUT
HAS_OBB = worlds.DEFAULT_OBB.is_dir()

REQUIRED_FIELDS = ("id", "kind", "amount", "world", "levelOrRange", "firstOnly", "source")


def load_shipped() -> dict:
    with SHIPPED.open(encoding="utf-8") as handle:
        return json.load(handle)


class ShippedRewardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = load_shipped()
        cls.rows = cls.table["rewards"]
        cls.by_id = {row["id"]: row for row in cls.rows}

    def test_format_and_top_level_keys(self) -> None:
        self.assertEqual(self.table["format"], rewards.FORMAT)
        self.assertEqual(self.table["generated"], rewards.GENERATED)
        self.assertEqual(
            sorted(self.table),
            ["counts", "danglingPresentTables", "format", "gates", "generated", "generatedAt",
             "pinataTypes", "rewards", "sources", "unknowns", "worldKeys"],
        )

    def test_counts_agree_with_rows(self) -> None:
        counts = self.table["counts"]
        self.assertEqual(counts["rewards"], len(self.rows))
        self.assertEqual(sum(counts["byKind"].values()), len(self.rows))
        self.assertEqual(counts["filesScanned"], 2117)
        self.assertEqual(counts["levels"], 1809)
        # The eight sections must account for every row.
        sections = {
            "loot": counts["lootRows"],
            "present": counts["presentRows"],
            "rift-clear": 18,
            "rift-boss": 36,
            "giftbox": counts["giftBoxRows"],
            "seeddrop": counts["seedDropRows"],
            "constant": counts["constantRows"],
            "first": None,
            "replay": None,
        }
        seen = {"loot": 0, "present": 0, "rift-clear": 0, "rift-boss": 0,
                "giftbox": 0, "seeddrop": 0, "constant": 0, "first": 0, "replay": 0}
        for row in self.rows:
            seen[row["id"].split(":")[0]] += 1
        for name, expected in sections.items():
            if expected is not None:
                self.assertEqual(seen[name], expected, f"{name} rows")
        self.assertEqual(sum(seen.values()), len(self.rows))

    def test_rows_sorted_and_unique(self) -> None:
        ids = [row["id"] for row in self.rows]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(set(ids)), len(ids), "reward ids must be unique")
        self.assertEqual(self.table["counts"]["duplicateIds"], [])

    def test_every_row_carries_a_source(self) -> None:
        for row in self.rows:
            for field in REQUIRED_FIELDS:
                self.assertIn(field, row, f"{row.get('id')} misses {field}")
            self.assertTrue(row["source"].startswith("pkg_"), row["id"])
            self.assertGreater(len(row["source"]), 20, row["id"])
            self.assertIn(row["kind"], rewards.PRIMARY_KINDS + rewards.SECONDARY_KINDS, row["id"])

    def test_loot_table_is_25_rows(self) -> None:
        loot = [row for row in self.rows if row["id"].startswith("loot:")]
        self.assertEqual(len(loot), 25)
        kinds = {}
        for row in loot:
            kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
        self.assertEqual(kinds, {"coin": 8, "key": 8, "gem": 2, "sun": 2, "mower": 4, "sprout": 1})

    def test_silver_drop_values_come_from_the_collectable(self) -> None:
        row = self.by_id["loot:Silver1:default"]
        self.assertEqual(row["lootType"], "SilverCoin")
        self.assertEqual(row["amount"], 10)          # coin_silver CoinValue
        self.assertEqual(row["amountRange"], [10, 30])
        self.assertEqual(row["drops"], [1, 3])
        self.assertEqual(row["period"], 2)
        self.assertEqual(row["periodUnit"], "kills")
        self.assertEqual(row["mapping"], "inferred-name-convention")
        self.assertIn("CollectableCoinType", row["unitSource"])

    def test_gold_entries_are_100_per_drop(self) -> None:
        gold = [row for row in self.rows
                if row["id"].startswith("loot:Gold") and row["kind"] == "coin"]
        self.assertEqual(len(gold), 6)               # Gold1/3 default + Gold1/2/3/4 danger
        for row in gold:
            self.assertEqual(row["amount"], 100)     # coin_gold CoinValue

    def test_key_drops_are_per_world_and_enabled_after_egypt3(self) -> None:
        keys = [row for row in self.rows if row["kind"] == "key"]
        self.assertEqual(len(keys), 8)
        self.assertEqual(sorted({row["world"] for row in keys}),
                         ["cowboy", "egypt", "future", "pirate"])
        for row in keys:
            self.assertEqual(row["condition"], "egypt3")
            self.assertEqual(row["period"], 30)
            # Key rows carry no LevelLootKey: they are world-gated, not loot-key gated.
            self.assertEqual(row["lootKey"], "any")

    def test_whack_rows_use_seconds(self) -> None:
        sun = {row["id"]: row for row in self.rows if row["kind"] == "sun"}
        self.assertEqual(sorted(sun), ["loot:SunLarge1:whack", "loot:SunSmall1:whack"])
        self.assertEqual(sun["loot:SunSmall1:whack"]["amount"], 5)    # sun_small SunValue
        self.assertEqual(sun["loot:SunLarge1:whack"]["amount"], 75)   # sun_large SunValue
        for row in sun.values():
            self.assertEqual(row["periodUnit"], "seconds")

    def test_egypt_key_has_no_pickup(self) -> None:
        row = self.by_id["loot:EgyptKey1:any"]
        self.assertEqual(row["pickup"], "worldkey_egypt")
        self.assertEqual(row["mapping"], "unresolved")
        self.assertNotIn("worldkey_egypt", self.table["worldKeys"])
        self.assertEqual(len(self.table["worldKeys"]), 10)

    def test_present_coin_is_100_for_normal_and_shiny(self) -> None:
        presents = [row for row in self.rows if row["id"].startswith("present:")]
        self.assertEqual(len(presents), 36)
        coins = [row for row in presents if row["kind"] == "coin"]
        self.assertEqual(len(coins), 8)              # 4 worlds × (normal + shiny)
        for row in coins:
            self.assertEqual(row["amount"], 100)
            self.assertEqual(row["rewardType"], "coinpack_medium")
            self.assertTrue(row["enabled"])
            self.assertIs(row["firstOnly"], False)
        # The seven extras in every shiny table are shipped with weight 0 = disabled.
        shiny_extras = [row for row in presents if row["variant"] == "shiny" and row["kind"] != "coin"]
        self.assertEqual(len(shiny_extras), 28)
        for row in shiny_extras:
            self.assertEqual(row["weight"], 0)
            self.assertIs(row["enabled"], False)

    def test_present_powerup_kind_comes_from_collectable_class(self) -> None:
        row = self.by_id["present:egypt_shiny_01:powerupwizardfinger"]
        self.assertEqual(row["kind"], "powerup")
        self.assertEqual(row["amount"], None)        # a CollectableType row has no NumUses

    def test_thirteen_dangling_present_tables(self) -> None:
        dangling = self.table["danglingPresentTables"]
        self.assertEqual(len(dangling), 13)
        self.assertEqual(self.table["counts"]["danglingPresentRefs"], 68)
        names = {row["table"] for row in dangling}
        self.assertIn("lostcity_normal_01", names)
        self.assertIn("kongfu_shiny_01", names)
        # A level points its ShinyPresentTable at a *normal* table that is not shipped.
        shiny_heian = [row for row in dangling if row["table"] == "heian_normal_01"
                       and row["kind"] == "shiny"]
        self.assertEqual(len(shiny_heian), 1)

    def test_gates_count_matches_world_data(self) -> None:
        gates = self.table["gates"]
        self.assertEqual(len(gates), 80)
        self.assertEqual(self.table["counts"]["gatesByType"], {"key_gate": 27, "star_gate": 53})
        spent = {}
        for row in gates:
            spent[row["gate"]] = spent.get(row["gate"], 0) + 1
            self.assertEqual(row["kind"], "key" if row["gate"] == "key_gate" else "star")
        self.assertEqual(spent, {"key_gate": 27, "star_gate": 53})

    def test_rift_first_clear_rewards(self) -> None:
        default = sorted(row["amount"] for row in self.rows
                         if row["id"].startswith("rift-clear:default:"))
        self.assertEqual(default, [500, 1000, 1500])
        level1 = {row["kind"]: row["amount"] for row in self.rows
                  if row["id"].startswith("rift-clear:1:")}
        self.assertEqual(level1, {"coin": 600, "xp": 5, "gem": 4})
        for row in self.rows:
            if row["id"].startswith("rift-clear:"):
                self.assertIs(row["firstOnly"], True)

    def test_seed_drops_carry_an_explicit_chance(self) -> None:
        seeds = [row for row in self.rows if row["id"].startswith("seeddrop:")]
        self.assertEqual(len(seeds), 76)
        self.assertEqual(self.table["counts"]["seedDropModules"], 15)
        self.assertEqual(self.table["counts"]["seedDropChances"],
                         [0.01, 0.03, 0.06, 0.1, 0.15, 0.2, 0.4, 1])
        for row in seeds:
            self.assertEqual(row["kind"], "seed")
            self.assertEqual(row["amount"], 1)
            self.assertIs(row["dropOnAllZombieTypes"], True)
            self.assertGreater(row["weight"], 0)
            self.assertIn("ZombieDeathSeedDropModuleProperties", row["source"])
        # The richest module: april-fools drops one of 21 plants at 15 %.
        april = [row for row in seeds if row["pkg"] == "pkg_0243_LevelDefinition.json"]
        self.assertEqual(len(april), 21)
        self.assertEqual({row["dropChance"] for row in april}, {0.15})
        self.assertEqual({row["levelName"] for row in april}, {"[APRILFOOLS_LEVEL_NAME]"})
        self.assertIn("threepeater1", {row["rewardType"] for row in april})

    def test_giftbox_gem_award(self) -> None:
        gems = [row for row in self.rows if row["id"].startswith("giftbox:") and row["kind"] == "gem"]
        self.assertEqual(len(gems), 1)
        self.assertEqual(gems[0]["amount"], 20)
        self.assertEqual(gems[0]["probability"], 3)
        self.assertEqual(gems[0]["category"], "VasebreakerGiftBox")

    def test_economy_constants(self) -> None:
        constants = {row["constant"]: row["amount"] for row in self.rows
                     if row["id"].startswith("constant:")}
        self.assertEqual(constants["CoinsPerKey"], 1000)
        self.assertEqual(constants["KeysPerCostume"], 10)
        self.assertEqual(constants["StarsPerCostume"], 20)
        self.assertEqual(constants["LawnMowerPurchasePriceInCoins"], 2000)
        self.assertEqual(constants["SeedSlotRentalCost"], 2000)

    def test_sentinels_are_counted_not_spent(self) -> None:
        sentinels = self.table["counts"]["sentinels"]
        self.assertEqual(sentinels["totals"].get("-1"), 3)
        self.assertEqual(sentinels["totals"].get("0"), 35)
        self.assertNotIn("2147483647", sentinels["totals"])
        self.assertIn("LootConfig.LevelLength", sentinels["byField"])
        self.assertIn("PresentTable.Weight", sentinels["byField"])
        # No reward row may present a sentinel as a normal amount.
        for row in self.rows:
            self.assertNotIn(row["amount"], rewards.SENTINELS, row["id"])

    def test_mower_and_sprout_rows_map_to_real_pickups(self) -> None:
        """Audit M2: five rows used to be `mapping=none` although pkg_0010 has the rows."""

        wanted = {
            "loot:LawnMower1:any": "lawn_mower",
            "loot:LawnMower2:any": "lawn_mower",
            "loot:LawnMower3:any": "lawn_mower",
            "loot:LawnMower4:any": "lawn_mower",
            "loot:Sprout1:any": "sprout",
        }
        by_id = {row["id"]: row for row in self.rows}
        for row_id, pickup in wanted.items():
            row = by_id[row_id]
            self.assertEqual(row["pickup"], pickup, row_id)
            self.assertEqual(row["mapping"], "inferred-name-convention", row_id)
            self.assertEqual(row["amount"], 1, row_id)
            # The value source is the pickup row itself, not the loot entry.
            self.assertIn("pkg_0010", row["unitSource"], row_id)
            self.assertIn("no value field", row["unitSource"], row_id)
            self.assertIn(pickup, row["mappingNote"], row_id)
        # No loot row is left with a bare null any more.
        mappings = {}
        for row in self.rows:
            if "mapping" in row:
                mappings[row["mapping"]] = mappings.get(row["mapping"], 0) + 1
        self.assertEqual(mappings.get("none", 0), 0)
        self.assertEqual(mappings.get("inferred-name-convention"), 23)
        self.assertEqual(mappings.get("unresolved"), 2)

    def test_sentinel_scope_names_both_traversals(self) -> None:
        """Audit L2: one `sentinels` number is not a census; the scope must say which."""

        sentinels = self.table["counts"]["sentinels"]
        scope = sentinels["scope"]
        self.assertEqual(sorted(scope), ["fullRecursive", "readPath"])
        self.assertEqual(scope["readPath"]["values"], ["-1", "0", "2147483647"])
        self.assertEqual(scope["fullRecursive"]["values"], ["-1", "2147483647"])
        self.assertEqual(scope["fullRecursive"]["traversal"].count("objdata"), 1)
        self.assertEqual(len(scope["readPath"]["packages"]), 10)
        self.assertEqual(sorted(scope["readPath"]["packages"]), sorted(rewards.READ_PACKAGES))

        # The whitelisted read path: 38 = 3 x -1 + 35 x 0, and it is the invariant.
        self.assertEqual(sentinels["readPathTotal"], 38)
        self.assertEqual(sentinels["readPathTotal"], sum(sentinels["totals"].values()))

        # Full recursion: two scopes, and no `0` may enter them.
        full = sentinels["fullRecursive"]
        self.assertEqual(full["readPackages"]["total"], 604)
        self.assertEqual(full["allPackages"]["total"], 5327)
        for key in ("readPackages", "allPackages"):
            self.assertNotIn("0", full[key]["values"])
            self.assertEqual(
                sum(full[key]["byType"].values()), full[key]["total"],
                f"{key}: int/float split must add up to the total",
            )
        self.assertEqual(full["allPackages"]["byType"]["int"], 5298)
        self.assertIn("readPathTotal=38", sentinels["difference"])
        self.assertIn("5327", sentinels["difference"])

    def test_mint_and_star_have_no_producers(self) -> None:
        produced = {row["kind"] for row in self.rows}
        self.assertNotIn("mint", produced)
        star_rows = [row for row in self.rows if row["kind"] == "star"]
        self.assertEqual(len(star_rows), 1)
        self.assertEqual(star_rows[0]["constant"], "StarsPerCostume")  # a rate, not a payout
        verdicts = {row["item"]: row["verdict"] for row in self.table["unknowns"]}
        self.assertEqual(verdicts["mint 产出点"], "server-only")
        self.assertEqual(verdicts["星章（star）作为奖励"], "server-only")

    def test_unknowns_list_and_shape(self) -> None:
        unknowns = self.table["unknowns"]
        self.assertEqual(len(unknowns), 10)
        for row in unknowns:
            self.assertTrue(row["item"])
            self.assertTrue(row["verdict"])
            self.assertTrue(row["why"])
            self.assertTrue(row["tried"], row["item"])

    def test_file_bytes_are_lf_and_renders_identically(self) -> None:
        raw = SHIPPED.read_bytes()
        self.assertNotIn(b"\r\n", raw)
        self.assertTrue(raw.endswith(b"\n"))
        again = rewards.render(load_shipped()).encode("utf-8")
        self.assertEqual(hashlib.sha256(raw).hexdigest(), hashlib.sha256(again).hexdigest())


@unittest.skipUnless(HAS_OBB, f"OBB packages not present at {worlds.DEFAULT_OBB}")
class CompileRewardTests(unittest.TestCase):
    def test_recompile_matches_shipped_bytes(self) -> None:
        table = rewards.build(worlds.DEFAULT_OBB)
        self.assertEqual(rewards.render(table).encode("utf-8"), SHIPPED.read_bytes())

    def test_check_passes(self) -> None:
        table = rewards.build(worlds.DEFAULT_OBB)
        self.assertEqual(rewards.check(table, SHIPPED), 0)

    def test_check_detects_drift(self) -> None:
        table = rewards.build(worlds.DEFAULT_OBB)
        with tempfile.TemporaryDirectory() as directory:
            bogus = Path(directory) / "rewards.json"
            bogus.write_bytes(b'{"format": "wrong"}\n')
            self.assertEqual(rewards.check(table, bogus), 1)

    def test_empty_obb_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            table = rewards.build(Path(directory))
            self.assertEqual(table["rewards"], [])
            self.assertEqual(table["counts"]["levels"], 0)
            self.assertEqual(table["counts"]["filesScanned"], 0)


if __name__ == "__main__":
    unittest.main()
