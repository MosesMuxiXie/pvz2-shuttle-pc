"""Tests for tools/contentc/plant_levels.py — 460.9 植物等级 / 升级数据表。

两组：

* `ShippedPlantLevelsTests` 只读 `native/generated/plant_levels.json`，不需要 OBB —— 在
  没有原版包的机器上也能证明「产物结构完整、数字自洽、没有编造数值」。
* `CompilePlantLevelsTests` 需要 OBB：重编译必须与磁盘逐字节相同、`--check` 幂等、
  陈旧产物必须被拒、空目录必须给出 `available: false` 而不是抛异常。

本任务的硬约束是「不许为填表编数值」，所以断言重点有两处：
  1) 结构不变量（层数连续、byLevelCount 求和、raggedStats 与 null 计数一致）；
  2) 抽样逐级核对（blockoli / sunflower / wallnut / potatomine），且缺数据处必须是 null。
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

from contentc import plant_levels, worlds  # noqa: E402

SHIPPED = plant_levels.DEFAULT_OUT
HAS_OBB = worlds.DEFAULT_OBB.is_dir()

EXPECTED_BY_LEVEL_COUNT = {
    "1": 190,
    "2": 36,
    "3": 20,
    "4": 5,
    "10": 68,
    "15": 1,
    "20": 3,
}

EXPECTED_UNKNOWN_KINDS = {
    "alternate-only-plant",
    "duplicate-canonical-typename",
    "duplicate-stat-names",
    "ragged-float-stats",
    "level-cap-below-level-count",
    "levels-without-stats",
    "level-xp-not-monotonic",
    "plant-tier-looks-like-coins",
}


def load(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


class ShippedPlantLevelsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = load(SHIPPED)
        cls.plants = cls.table["plants"]
        cls.counts = cls.table["counts"]

    def test_format_and_top_level_keys(self):
        self.assertEqual(self.table["format"], "pvz2-shuttle/plant-levels@1")
        self.assertEqual(self.table["generated"], "2026-11-25")
        self.assertEqual(
            sorted(self.table),
            ["counts", "format", "generated", "levelupOffer", "mechanism", "plants", "searches",
             "sources", "unknowns", "upgradeHooks"],
        )

    def test_levels_are_available_and_counted(self):
        self.assertIs(self.counts["available"], True)
        self.assertEqual(self.counts["plants"], 323)
        self.assertEqual(self.counts["rowsCanonical"], 325)
        self.assertEqual(self.counts["rowsAlternate"], 377)
        self.assertEqual(len(self.plants), 323)
        self.assertGreater(self.counts["plantsWithLeveling"], 0)

    def test_every_plant_ladder_is_contiguous_and_sourced(self):
        for name, row in self.plants.items():
            with self.subTest(plant=name):
                levels = row["levels"]
                self.assertEqual(row["levelCount"], len(levels))
                self.assertEqual([lv["level"] for lv in levels], list(range(1, len(levels) + 1)))
                self.assertTrue(row["source"].startswith(plant_levels.CANONICAL_FILE + "#"))
                for level_row in levels:
                    for stat, value in level_row["stats"].items():
                        self.assertNotIsInstance(value, (dict, list))

    def test_by_level_count_matches_plants(self):
        histogram = {}
        for row in self.plants.values():
            key = str(row["levelCount"])
            histogram[key] = histogram.get(key, 0) + 1
        self.assertEqual(histogram, EXPECTED_BY_LEVEL_COUNT)
        self.assertEqual(self.counts["byLevelCount"], EXPECTED_BY_LEVEL_COUNT)
        self.assertEqual(sum(EXPECTED_BY_LEVEL_COUNT.values()), 323)

    def test_blockoli_ladder_level_by_level(self):
        row = self.plants["blockoli"]
        self.assertEqual(row["levelCount"], 10)
        self.assertEqual(row["levelCap"], 10)
        self.assertEqual(row["levelCountSource"], ["levelCap"])
        self.assertEqual(row["levelXP"], [50, 100, 200, 300, 400, 500, 600, 800, 1000])
        self.assertEqual(row["plantTier"], [1, 1, 2, 2, 2, 2, 3, 3, 3, 3])
        stats = [lv["stats"] for lv in row["levels"]]
        self.assertEqual([s["Hitpoints"] for s in stats],
                         [6000, 7000, 8000, 9000, 10000, 11000, 12000, 13000, 14500, 16000])
        self.assertEqual([s["Cost"] for s in stats], [150, 125, 125, 125, 100, 100, 100, 100, 100, 75])
        self.assertEqual([s["ActionDamage"] for s in stats],
                         [95, 105, 115, 135, 155, 175, 205, 235, 265, 325])
        self.assertEqual(stats[0]["PacketCooldown"], 15)
        self.assertEqual(stats[-1]["PacketCooldown"], 7)
        self.assertEqual(row["raggedStats"], {})

    def test_sunflower_three_levels(self):
        row = self.plants["sunflower"]
        self.assertEqual(row["levelCount"], 3)
        self.assertEqual(row["levelXP"], [20, 40])
        self.assertIsNone(row["levelCoins"])
        stats = [lv["stats"] for lv in row["levels"]]
        self.assertEqual([s["Cost"] for s in stats], [50, 40, 30])
        self.assertEqual([s["Hitpoints"] for s in stats], [300, 350, 500])
        self.assertEqual([s["PacketCooldown"] for s in stats], [5, 4.5, 4.5])

    def test_wallnut_ladder_comes_from_stats_not_polluted_levelxp(self):
        row = self.plants["wallnut"]
        # wallnut 的 LevelXP 有 39 项且尾部是 1/1/2/2/3/3（阶数），不能当层数
        self.assertEqual(len(row["levelXP"]), 39)
        self.assertIs(row["levelXPMonotonic"], False)
        self.assertIn("levelXP:non-monotonic", row["levelCountIgnored"])
        self.assertEqual(row["levelCount"], 3)
        self.assertEqual(row["levelCountSource"], ["floatStats", "plantTier"])
        self.assertEqual([lv["stats"]["Hitpoints"] for lv in row["levels"]], [4000, 4500, 5000])

    def test_potatomine_has_upgrade_coins_but_no_stat_ladder(self):
        row = self.plants["potatomine"]
        self.assertEqual(row["levelCount"], 1)
        self.assertEqual(row["levelCountSource"], ["default-1"])
        self.assertIs(row["plantTierLooksLikeCoins"], True)
        self.assertEqual(len(row["upgradeCoins"]), 20)
        self.assertEqual(row["upgradeCoins"][0], 1)
        self.assertEqual(row["upgradeCoins"][-1], 55000)
        self.assertEqual(row["levels"][0]["stats"], {})

    def test_missing_levels_are_null_not_carried_forward(self):
        """缺数据的层必须是 null：既不能补上一级，也不能补 0。"""
        checked = 0
        for name, row in self.plants.items():
            if not row["raggedStats"]:
                continue
            checked += 1
            for stat, missing in row["raggedStats"].items():
                series = [lv["stats"].get(stat) for lv in row["levels"]]
                self.assertEqual(len(series), row["levelCount"])
                self.assertEqual(series.count(None), missing, "%s.%s" % (name, stat))
                # 缺失只发生在尾部：最后一个 null 之前必须连续有值
                first_null = len(series) - missing
                for value in series[first_null:]:
                    self.assertIsNone(value)
                if first_null:
                    self.assertIsNotNone(series[first_null - 1])
        self.assertEqual(checked, self.counts["raggedPlants"])

    def test_duplicate_stat_names_are_split_by_subtype(self):
        """同名条目靠 SubType 区分，是两列数据：要拆开，不能丢一列也不能后写覆盖。"""
        self.assertEqual(self.counts["duplicateStatNamePlants"], 27)
        self.assertEqual(self.counts["duplicateStatNameCounts"],
                         {"ActionDamage": 23, "ActionDamageNormal": 4,
                          "ActionDamagePF": 4, "ActionSplashDamage": 1})
        row = self.plants["cutebubuseed"]
        self.assertEqual(row["levelCount"], 2)
        self.assertEqual(row["statNames"], ["ActionDamage@0", "ActionDamage@1"])
        self.assertEqual(row["duplicateStatNames"],
                         {"ActionDamage": {"entries": 2,
                                           "keys": ["ActionDamage@0", "ActionDamage@1"]}})
        first = row["levels"][0]["stats"]
        self.assertEqual(first["ActionDamage@0"], 6)
        self.assertEqual(first["ActionDamage@1"], 100)
        self.assertEqual(row["levels"][1]["stats"],
                         {"ActionDamage@0": None, "ActionDamage@1": None})
        self.assertEqual(row["raggedStats"], {"ActionDamage@0": 1, "ActionDamage@1": 1})
        names = next(u for u in self.table["unknowns"] if u["kind"] == "duplicate-stat-names")
        self.assertEqual(names["count"], 27)
        self.assertEqual(names["names"]["ActionDamage"], 23)

    def test_null_stat_pairs_match_every_plant(self):
        total = 0
        for row in self.plants.values():
            for missing in row["raggedStats"].values():
                total += missing
        self.assertEqual(total, self.counts["nullStatPairs"])

    def test_derived_ratios_follow_the_real_values(self):
        row = self.plants["peashooter"]
        derived = row["derived"]
        self.assertEqual(derived["derivedFromLevel"], 1)
        self.assertEqual(derived["hpMul"][0], 1.0)
        hp = [lv["stats"]["Hitpoints"] for lv in row["levels"]]
        self.assertEqual(derived["hpMul"], [round(v / hp[0], 4) for v in hp])
        cost = [lv["stats"]["Cost"] for lv in row["levels"]]
        self.assertEqual(derived["costDelta"], [round(v - cost[0], 4) for v in cost])
        # 有相对基准才有派生值：没有 Cost 的植物不该凭空多出 costDelta
        for name, other in self.plants.items():
            if "Cost" not in other["levels"][0]["stats"]:
                with self.subTest(plant=name):
                    self.assertNotIn("costDelta", other["derived"])

    def test_alternate_only_plants_are_recorded_not_invented(self):
        for name in ("electrictea", "tombtangler", "vamporcini"):
            self.assertNotIn(name, self.plants)
        self.assertEqual(self.counts["alternateOnlyPlants"],
                         ["electrictea", "tombtangler", "vamporcini"])
        row = next(u for u in self.table["unknowns"] if u["kind"] == "alternate-only-plant")
        self.assertEqual(row["plants"], ["electrictea", "tombtangler", "vamporcini"])

    def test_duplicate_typenames_keep_the_extra_rows(self):
        self.assertEqual(self.counts["duplicateTypeNames"], {"aloe": 2, "cactus": 2})
        for name in ("aloe", "cactus"):
            row = self.plants[name]
            self.assertEqual(len(row["alternateRows"]), 1)
            self.assertTrue(row["alternateRows"][0]["source"].startswith(plant_levels.CANONICAL_FILE))

    def test_unknowns_cover_the_known_anomalies(self):
        kinds = {row["kind"] for row in self.table["unknowns"]}
        self.assertEqual(kinds, EXPECTED_UNKNOWN_KINDS)
        ragged = next(u for u in self.table["unknowns"] if u["kind"] == "ragged-float-stats")
        self.assertEqual(ragged["count"], self.counts["raggedPlants"])
        self.assertEqual(ragged["nullStatPairs"], self.counts["nullStatPairs"])
        for row in self.table["unknowns"]:
            self.assertTrue(row.get("detail"))
            self.assertTrue(row.get("probe"))

    def test_upgrade_side_is_honestly_scoped(self):
        mechanism = self.table["mechanism"]
        self.assertIs(mechanism["hasPlantLevels"], True)
        self.assertIs(mechanism["hasGenericUpgradeTable"], False)
        hooks = self.table["upgradeHooks"]
        self.assertEqual(len(hooks), self.counts["upgradeHookFields"])
        self.assertEqual(len(hooks), 9)
        plants = {row["plant"] for row in hooks}
        self.assertEqual(plants, {"IceweedDefault", "PeapodDefault", "UltomatoDefault"})
        keys = {row["key"] for row in hooks}
        self.assertIn("BeamDPSUpgrade3", keys)
        self.assertIn("CanPlantAgainToUpgrade", keys)

    def test_levelup_offer_is_the_currency_conversion_table(self):
        offer = self.table["levelupOffer"]
        self.assertEqual(offer["package"], plant_levels.LEVELUP_OFFER_FILE)
        data = offer["data"]
        self.assertEqual(data["MaxCoins"], 100000)
        self.assertEqual(data["MaxGems"], 500)
        self.assertEqual(data["MaxMints"], 500)
        self.assertEqual([row["Rarity"] for row in data["ConversionInfo"]],
                         ["common", "uncommon", "rare", "epic", "mythical", "legendary"])
        self.assertEqual(data["ConversionInfo"][0]["Coins"], 200.0)

    def test_searches_prove_the_negative_result(self):
        """「原版没有通用升级表」必须是可复核的产物，而不是一句话。"""
        rows = {row["term"]: row for row in self.table["searches"]}
        self.assertEqual(sorted(rows),
                         ["LevelUp", "PlantLevel", "PlantUpgrade", "SeedPackLevel", "Upgrade"])
        self.assertEqual(rows["PlantUpgrade"], {"term": "PlantUpgrade", "classes": 0,
                                                "aliases": 0, "keys": 0, "examples": []})
        self.assertEqual(rows["SeedPackLevel"]["classes"], 0)
        self.assertEqual(rows["SeedPackLevel"]["keys"], 0)
        self.assertGreater(rows["PlantLevel"]["classes"], 0)
        self.assertGreater(rows["Upgrade"]["keys"], 0)
        for row in rows.values():
            self.assertEqual(sorted(row),
                             ["aliases", "classes", "examples", "keys", "term"])

    def test_render_is_stable_and_matches_the_disk(self):
        first = plant_levels.render(self.table)
        second = plant_levels.render(load(SHIPPED))
        self.assertEqual(first, second)
        raw = Path(SHIPPED).read_bytes()
        self.assertEqual(raw.decode("utf-8"), first)
        self.assertNotIn("\r\n", first)
        self.assertTrue(first.endswith("\n"))
        self.assertFalse(first.endswith("\n\n"))


class CompilePlantLevelsTests(unittest.TestCase):
    @unittest.skipUnless(HAS_OBB, "OBB 不在默认位置，跳过重编译")
    def test_fresh_compile_matches_shipped_bytes(self):
        table = plant_levels.build(plant_levels.DEFAULT_OBB)
        self.assertEqual(plant_levels.render(table), Path(SHIPPED).read_text(encoding="utf-8"))

    @unittest.skipUnless(HAS_OBB, "OBB 不在默认位置，跳过重编译")
    def test_check_is_idempotent(self):
        table = plant_levels.build(plant_levels.DEFAULT_OBB)
        self.assertEqual(plant_levels.check(table, SHIPPED), 0)

    @unittest.skipUnless(HAS_OBB, "OBB 不在默认位置，跳过重编译")
    def test_check_rejects_a_stale_artifact(self):
        table = plant_levels.build(plant_levels.DEFAULT_OBB)
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "plant_levels.json"
            # 用 write_bytes：write_text 在 Windows 上会写 CRLF，会让这条测试红得没有意义
            stale.write_bytes(b'{"plants": {}}\n')
            self.assertEqual(plant_levels.check(table, stale), 1)

    def test_empty_obb_reports_not_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            table = plant_levels.build(Path(tmp))
        self.assertEqual(table["plants"], {})
        self.assertIs(table["counts"]["available"], False)
        self.assertIsNone(table["levelupOffer"])
        self.assertEqual(table["upgradeHooks"], [])


if __name__ == "__main__":
    unittest.main()
