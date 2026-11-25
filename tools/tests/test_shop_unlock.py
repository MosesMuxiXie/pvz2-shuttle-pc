"""Tests for `tools/contentc/shop_unlock.py` and the shipped `shop_unlock.json`.

Three groups:

* `ShippedShopUnlockTests` reads `native/generated/shop_unlock.json` and asserts the
  facts the shop UI will rely on: 585 rows, the six-class projection, the per-rule
  counts, the `unknown` bucket being named (not dropped), the world binding of the
  world key, `stars` staying null, and determinism of the artifact.
* `ClassifyRuleTests` feeds hand-written shop rows to the pure functions so each
  rule and each edge case is pinned without the 250 KB artifact: rule order
  (world key before upgrade), mint pricing falling out of the three-value enum,
  duplicate ids being kept and counted, a row with no id at all, and unknown rows
  carrying a reason.
* `CompileTests` rebuilds from `content/shop.json` and checks the shipped file is
  exactly a fresh render (byte for byte), that `--check` accepts it, and that a
  stale artifact is rejected.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.contentc import shop_unlock, worlds

SHIPPED = worlds.REPO / "native/generated/shop_unlock.json"
REPORT = worlds.REPO / "docs/reviews/2026-11-21-shop-unlock.md"
SOURCE = worlds.REPO / "content/shop.json"
WORLDMAP = worlds.REPO / "content/worldmap.json"

#: the six classes the shop UI renders; `unknown` is a bucket, not a guess
CATEGORIES = ("seed", "upgrade", "world_key", "costume", "event", "unknown")

#: rows whose `item_type` has no class among the six — kept and named, never dropped
UNKNOWN_REASONS = {
    "item_type=coin": 2,
    "item_type=gem": 2,
    "item_type=mint": 4,
    "item_type=sprout": 3,
    "item_type=action": 1,
    "item_type=bundle": 1,
}


def load_shipped() -> dict:
    with SHIPPED.open(encoding="utf-8") as handle:
        return json.load(handle)


def build_from_source() -> dict:
    doc = shop_unlock.load_json(SOURCE)
    ids = shop_unlock.world_ids(WORLDMAP)
    return shop_unlock.build(doc, ids, shop_unlock.generated_stamp(SOURCE))


class ShippedShopUnlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = load_shipped()
        cls.counts = cls.table["counts"]
        cls.by_id = {row["id"]: row for row in cls.table["items"] if row["id"]}

    # -- shape -------------------------------------------------------

    def test_format_and_generator(self) -> None:
        self.assertEqual(self.table["format"], shop_unlock.FORMAT)
        self.assertEqual(self.table["generated"], shop_unlock.GENERATED)
        self.assertEqual(self.table["source"], shop_unlock.SOURCE_NAME)
        self.assertEqual(sorted(self.table),
                         ["counts", "format", "generated", "generatedAt", "items", "source"])
        self.assertRegex(self.table["generatedAt"], r"^sha256:[0-9a-f]{16}$")

    def test_585_holds(self) -> None:
        # the task's number has to come out of the file, not out of the task
        self.assertEqual(self.counts["total"], 585)
        self.assertEqual(self.counts["sourceItems"], 585)
        self.assertEqual(self.counts["metaTotal"], 585)
        self.assertEqual(sum(self.counts["categoryTabCounts"].values()), 585)
        self.assertEqual(len(self.table["items"]), 585)
        self.assertEqual(self.counts["missingIds"], 0)
        self.assertEqual(self.counts["duplicateIds"], {})

    def test_six_category_counts(self) -> None:
        self.assertEqual(sorted(self.counts["byCategory"]), sorted(CATEGORIES))
        self.assertEqual(self.counts["byCategory"],
                         {"seed": 81, "upgrade": 11, "world_key": 1,
                          "costume": 447, "event": 32, "unknown": 13})
        self.assertEqual(sum(self.counts["byCategory"].values()), self.counts["total"])
        self.assertEqual(sum(self.counts["byUnlockKind"].values()), self.counts["total"])

    def test_every_row_is_classified_and_sorted(self) -> None:
        ids = [row["id"] for row in self.table["items"]]
        self.assertEqual(ids, sorted(ids))
        for row in self.table["items"]:
            self.assertIn(row["category"], CATEGORIES, row["id"])
            self.assertIn(row["unlock"]["kind"], shop_unlock.UNLOCK_KINDS, row["id"])
            self.assertTrue(row["rawKeys"], row["id"])
            self.assertIn(row["price"]["currency"], ("coins", "gems", "none"), row["id"])
            # every row must say which rule put it where
            self.assertTrue(
                any(key.startswith(("R01:", "R02:", "R03:", "R04:", "R05:", "R06:"))
                    for key in row["rawKeys"]),
                row["id"],
            )

    # -- rules that are easy to get wrong ----------------------------

    def test_world_key_wins_over_upgrade(self) -> None:
        # the world key is itself `item_type: gameupgrade`; R01 must come first
        row = self.by_id["obb_worldkey.rainbowmarket"]
        self.assertEqual(row["category"], "world_key")
        self.assertIn("R01:payload.world_key=rainbowmarket", row["rawKeys"])
        self.assertEqual(self.counts["byCategory"]["world_key"], 1)
        self.assertEqual(self.counts["byCategory"]["upgrade"], 11)

    def test_seed_and_costume_spot_checks(self) -> None:
        seed = self.by_id["seed_iris"]
        self.assertEqual(seed["category"], "seed")
        self.assertEqual(seed["price"], {"currency": "coins", "amount": 500})
        self.assertEqual(seed["unlock"]["kind"], "coins")
        self.assertEqual(seed["unlock"]["coins"], 500)
        costume = self.by_id["obb_Tonywrite.Costume.1"]
        self.assertEqual(costume["category"], "costume")
        self.assertIsNone(costume["unlock"]["world"])

    def test_unknown_bucket_is_named_not_dropped(self) -> None:
        unknowns = [row for row in self.table["items"] if row["category"] == "unknown"]
        self.assertEqual(len(unknowns), self.counts["unknownCategory"])
        self.assertEqual(sorted(self.counts["unknownCategoryIds"]),
                         sorted(row["id"] for row in unknowns))
        self.assertEqual(self.counts["unknownCategoryReasons"], UNKNOWN_REASONS)
        self.assertEqual(sum(self.counts["unknownCategoryReasons"].values()), 13)
        for row in unknowns:
            self.assertIn(row["unlock"]["kind"], ("none", "coins"), row["id"])
            self.assertIsNotNone(row["id"])

    def test_world_binding_and_price_join(self) -> None:
        key = self.by_id["obb_worldkey.rainbowmarket"]
        # `content/worldmap.json` has no `rainbowmarket`; the alias comes from worlds.ALIASES
        self.assertEqual(key["unlock"]["world"], "lunarrainbowmarket")
        self.assertEqual(key["unlock"]["coins"], 2026)
        self.assertEqual(key["unlock"]["kind"], "mixed")
        piñata = self.by_id["obb_com.popcap.pvz2.pinata.egypt.consume.tutorial"]
        self.assertEqual(piñata["unlock"]["world"], "egypt")
        self.assertEqual(self.counts["worldBound"],
                         ["obb_com.popcap.pvz2.pinata.egypt.consume.tutorial",
                          "obb_worldkey.rainbowmarket"])
        self.assertEqual(len(self.counts["coinGated"]), 100)

    def test_stars_never_fire(self) -> None:
        # no star gate exists in the source; null is the honest answer, not a zero
        self.assertEqual(self.counts["starGated"], [])
        self.assertEqual(self.counts["byUnlockKind"]["stars"], 0)
        for row in self.table["items"]:
            self.assertIsNone(row["unlock"]["stars"], row["id"])

    def test_mint_rows_are_kept_out_of_the_three_value_enum(self) -> None:
        self.assertEqual(len(self.counts["mintPriced"]), 10)
        self.assertEqual(self.counts["priceCurrencies"], {"coins": 100, "gems": 469, "none": 16})
        for item_id in self.counts["mintPriced"]:
            row = self.by_id[item_id]
            self.assertEqual(row["price"], {"currency": "none", "amount": None}, item_id)
            self.assertIn("currency=mint", row["rawKeys"], item_id)
            self.assertTrue(any(key.startswith("price:none-for-currency=mint")
                                for key in row["rawKeys"]), item_id)

    # -- artifact hygiene --------------------------------------------

    def test_artifact_is_lf_and_byte_identical(self) -> None:
        raw = SHIPPED.read_bytes()
        self.assertTrue(raw.endswith(b"\n"))
        self.assertNotIn(b"\r\n", raw)
        self.assertEqual(
            hashlib.sha256(shop_unlock.render(load_shipped()).encode("utf-8")).hexdigest(),
            hashlib.sha256(raw).hexdigest(),
        )

    def test_report_mentions_every_class_and_unknown(self) -> None:
        text = REPORT.read_text(encoding="utf-8")
        for heading in ("## 0.", "## 1.", "## 2.", "## 3.", "## 4.", "## 5.",
                        "## 6.", "## 7.", "## 8."):
            self.assertIn(heading, text)
        for name in CATEGORIES:
            self.assertIn("`%s`" % name, text)
        for reason in UNKNOWN_REASONS:
            self.assertIn(reason, text)
        self.assertIn("obb_worldkey.rainbowmarket", text)
        self.assertIn("lunarrainbowmarket", text)
        self.assertIn("--needle", text)


class ClassifyRuleTests(unittest.TestCase):
    """Pure-function tests: no artifact, no OBB, just hand-written rows."""

    def setUp(self) -> None:
        self.ids = {"frontyard": 1, "egypt": 1, "lunarrainbowmarket": 1}

    def row(self, **kwargs) -> dict:
        base = {"id": "x", "sku": "x", "price": 100, "currency": "coin",
                "item_type": "plant", "payload": {"plant_id": "x"}, "tab": "seeds"}
        base.update(kwargs)
        return base

    def test_rule_order(self) -> None:
        world_key = self.row(item_type="gameupgrade", payload={"world_key": "rainbowmarket"})
        self.assertEqual(shop_unlock.classify_category(world_key)[0], "world_key")
        upgrade = self.row(item_type="gameupgrade", payload={"seed_slots": 1})
        self.assertEqual(shop_unlock.classify_category(upgrade)[0], "upgrade")
        costume = self.row(item_type="costume", payload={"costume_id": "c1"})
        self.assertEqual(shop_unlock.classify_category(costume)[0], "costume")
        event = self.row(item_type="eventenergy", payload={"amount": 100})
        self.assertEqual(shop_unlock.classify_category(event)[0], "event")
        by_id = self.row(id="obb_com.popcap.pvz2.3rdanniversary", item_type="pinata",
                         payload={"seed_pack": 1})
        category, evidence = shop_unlock.classify_category(by_id)
        self.assertEqual(category, "event")
        self.assertIn("R05:item_type=pinata", evidence)

    def test_unknown_category_keeps_its_reason(self) -> None:
        for item_type in ("coin", "gem", "mint", "sprout", "bundle", "action"):
            row = self.row(item_type=item_type, payload={"amount": 1})
            category, evidence = shop_unlock.classify_category(row)
            self.assertEqual(category, "unknown", item_type)
            self.assertEqual(evidence, ["R06:item_type=%s" % item_type])

    def test_mint_price_leaves_the_enum_but_keeps_the_truth(self) -> None:
        price, evidence = shop_unlock.classify_price(
            self.row(currency="mint", price=300000))
        self.assertEqual(price, {"currency": "none", "amount": None})
        self.assertTrue(evidence)
        self.assertIn("mint", evidence[0])
        free, _ = shop_unlock.classify_price(self.row(currency="free", price=0))
        self.assertEqual(free, {"currency": "none", "amount": 0})

    def test_unlock_slots_and_kind(self) -> None:
        price, _ = shop_unlock.classify_price(self.row())
        unlock, _ = shop_unlock.classify_unlock(self.row(), "seed", price, self.ids)
        self.assertEqual(unlock, {"world": None, "stars": None, "coins": 100, "kind": "coins"})
        gem_price, _ = shop_unlock.classify_price(self.row(currency="gem", price=3000))
        unlock, _ = shop_unlock.classify_unlock(self.row(currency="gem", price=3000),
                                                "seed", gem_price, self.ids)
        self.assertEqual(unlock["kind"], "none")
        self.assertIsNone(unlock["coins"])
        key = self.row(id="obb_worldkey.egypt", item_type="gameupgrade",
                       payload={"world_key": "egypt"})
        unlock, _ = shop_unlock.classify_unlock(key, "world_key", price, self.ids)
        self.assertEqual(unlock["world"], "egypt")
        self.assertEqual(unlock["kind"], "mixed")

    def test_duplicate_ids_are_kept_and_counted(self) -> None:
        doc = {"items": [self.row(id="dup"), self.row(id="dup"), self.row(id="solo")]}
        table = shop_unlock.build(doc, self.ids, "2026-01-01T00:00:00Z")
        self.assertEqual(table["counts"]["total"], 3)
        self.assertEqual(table["counts"]["duplicateIds"], {"dup": 2})
        self.assertEqual(table["counts"]["duplicateCount"], 1)
        self.assertEqual([row["id"] for row in table["items"]], ["dup", "dup", "solo"])

    def test_missing_id_is_kept_as_unknown(self) -> None:
        doc = {"items": [{"sku": "no-id", "price": 1, "currency": "gem",
                          "item_type": "costume", "payload": {}}]}
        table = shop_unlock.build(doc, self.ids, "2026-01-01T00:00:00Z")
        row = table["items"][0]
        self.assertIsNone(row["id"])
        self.assertEqual(row["category"], "unknown")
        self.assertEqual(row["unlock"]["kind"], "unknown")
        self.assertIn("R06:id-missing", row["rawKeys"])
        self.assertEqual(table["counts"]["missingIds"], 1)
        self.assertEqual(table["counts"]["unknownConditions"], 1)
        self.assertEqual(table["counts"]["unknownConditionIds"], [None])

    def test_empty_document(self) -> None:
        table = shop_unlock.build({"items": []}, self.ids, "2026-01-01T00:00:00Z")
        self.assertEqual(table["counts"]["total"], 0)
        self.assertEqual(table["items"], [])
        self.assertEqual(sum(table["counts"]["byCategory"].values()), 0)


class CompileTests(unittest.TestCase):
    def test_two_renders_are_byte_identical(self) -> None:
        first = build_from_source()
        second = build_from_source()
        self.assertEqual(hashlib.sha256(shop_unlock.render(first).encode()).hexdigest(),
                         hashlib.sha256(shop_unlock.render(second).encode()).hexdigest())

    def test_shipped_file_matches_a_fresh_build(self) -> None:
        fresh = shop_unlock.render(build_from_source()).encode("utf-8")
        self.assertEqual(
            hashlib.sha256(fresh).hexdigest(),
            hashlib.sha256(SHIPPED.read_bytes()).hexdigest(),
            "native/generated/shop_unlock.json is stale: rerun tools/contentc/shop_unlock.py",
        )

    def test_check_accepts_shipped_and_rejects_stale(self) -> None:
        table = build_from_source()
        self.assertEqual(shop_unlock.check(table, SHIPPED), 0)
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "shop_unlock.json"
            stale.write_bytes(b'{"format": 1}\n')
            self.assertEqual(shop_unlock.check(table, stale), 1)
            missing = Path(tmp) / "absent.json"
            self.assertEqual(shop_unlock.check(table, missing), 1)

    def test_needle_finds_no_gating_keys(self) -> None:
        report = shop_unlock.needle_report(SOURCE)
        self.assertEqual(report["items"], 585)
        self.assertEqual(sum(report["keys"].values()), 0,
                         "a gating key appeared in content/shop.json: read it instead of guessing")


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
