"""元游戏数据层（图鉴 / 花园 / 成就·任务）的契约测试。

覆盖三件事：产物条数与原表一致、本地化键真能在 LawnStrings 里查到、两次生成逐字节相同。

运行::

    python -m unittest tools.tests.test_metagame -v
    python -m unittest discover -s tools/tests -p 'test_*.py'
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.contentc import metagame as mg  # noqa: E402

OBB = mg.DEFAULT_OBB
JSON_PATH = REPO / "native" / "generated" / "metagame.json"
REPORT_PATH = REPO / "docs" / "reviews" / "2026-11-25-metagame-data.md"


def setUpModule() -> None:
    """扫一遍 2116 个包要几秒，整个模块共用一份原料与一份产物。"""
    global PAYLOAD, MATERIAL, ENGLISH, CHINESE, TABLES
    if not OBB.is_dir():
        raise unittest.SkipTest(f"缺少 obb 解包目录：{OBB}")
    MATERIAL = mg.load_material(OBB)
    PAYLOAD = mg.build(OBB, material=MATERIAL)
    ENGLISH = MATERIAL["english"]
    CHINESE = MATERIAL["chinese"]
    TABLES = MATERIAL["tables"]


def run_main(argv: list[str]) -> int:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return mg.main(argv)


class TestCounts(unittest.TestCase):
    """三块条数必须等于原表条数，而不是手写的常量。"""

    def test_almanac_plants_match_source_table(self) -> None:
        self.assertEqual(len(PAYLOAD["almanac"]["plants"]), len(TABLES["PlantAlmanacData"]))
        self.assertEqual(PAYLOAD["almanac"]["plants"][0]["id"], "akee")

    def test_garden_matches_collectable_table(self) -> None:
        self.assertEqual(len(PAYLOAD["garden"]["collectables"]), len(TABLES["CollectableType"]))
        names = {row["typeName"] for row in PAYLOAD["garden"]["collectables"]}
        self.assertIn("worldkey_pirate", names)
        self.assertIn("pinata_egypt", names)

    def test_quests_match_quest_mgr_and_reward_count(self) -> None:
        quests = PAYLOAD["quests"]["quests"]
        source = sum(len(entry) for obj in TABLES["QuestMgr"] for entry in (obj.get("objdata") or {}).get("Quests") or [])
        self.assertEqual(len(quests), source)
        self.assertEqual(PAYLOAD["quests"]["counts"]["questsWithRewards"], 69)

    def test_achievements_and_tabs(self) -> None:
        achievements = PAYLOAD["achievements"]
        self.assertEqual(len(achievements["entries"]), achievements["counts"]["achievements"])
        self.assertTrue(all(row["rewards"] is None and row["serverOnly"] for row in achievements["entries"]))
        self.assertEqual(len(PAYLOAD["quests"]["tabs"]), len(TABLES["QuestTabCategoryData"]))
        self.assertEqual(PAYLOAD["quests"]["tabOrder"], ["DailyActivities", "EpicQuests"])

    def test_counts_block_agrees_with_blocks(self) -> None:
        counts = PAYLOAD["counts"]
        self.assertEqual(counts["almanacPlants"], len(PAYLOAD["almanac"]["plants"]))
        self.assertEqual(counts["almanacZombies"], len(PAYLOAD["almanac"]["zombies"]))
        self.assertEqual(counts["gardenCollectables"], len(PAYLOAD["garden"]["collectables"]))
        self.assertEqual(counts["quests"], len(PAYLOAD["quests"]["quests"]))
        self.assertEqual(counts["unknowns"], len(PAYLOAD["unknowns"]))


class TestContentCross(unittest.TestCase):
    """与客户端 content/ 的交集是实测数，不是「应该一致」。"""

    def test_plant_intersection(self) -> None:
        cross = PAYLOAD["cross"]
        plants = {row["id"] for row in PAYLOAD["almanac"]["plants"]}
        expected = plants & set(mg.content_ids(REPO / "content" / "plants.json"))
        self.assertEqual(cross["almanacPlantsInContent"], len(expected))
        self.assertGreater(cross["contentPlants"], cross["almanacPlantsInContent"])

    def test_zombie_intersection(self) -> None:
        cross = PAYLOAD["cross"]
        zombies = {row["id"] for row in PAYLOAD["almanac"]["zombies"]}
        # 只比手写行：source=="pack" 是从原版派生的镜像（tools/contentc/zombie_roster.py），
        # 拿它和图鉴交集会把「原版自己有」算成「客户端命中」。
        expected = zombies & set(
            mg.content_ids(REPO / "content" / "zombies.json", skip_pack=True)
        )
        self.assertEqual(cross["almanacZombiesInContent"], len(expected))

    def test_unmatched_content_ids_are_listed(self) -> None:
        cross = PAYLOAD["cross"]
        self.assertEqual(
            len(cross["contentPlantsNotInAlmanac"]) + cross["almanacPlantsInContent"], cross["contentPlants"]
        )


class TestLocalisation(unittest.TestCase):
    """本地化键必须能在 0231（英）/0232（中）里真查到，不能只是拼出来。"""

    def test_sampled_plant_name_keys_exist(self) -> None:
        samples = [row for row in PAYLOAD["almanac"]["plants"] if row["id"] in ("peashooter", "sunflower", "akee")]
        self.assertEqual(len(samples), 3)
        for row in samples:
            with self.subTest(plant=row["id"]):
                self.assertIn(row["nameKey"], ENGLISH)
                self.assertIn(row["nameKey"], CHINESE)
                self.assertTrue(row["resolved"]["name"])

    def test_sampled_zombie_name_keys_exist(self) -> None:
        samples = [row for row in PAYLOAD["almanac"]["zombies"] if row["id"] in ("basic", "chicken", "atlantis")]
        self.assertTrue(samples)
        for row in samples:
            with self.subTest(zombie=row["id"]):
                self.assertIn(row["nameKey"], ENGLISH)
                self.assertTrue(row["resolved"]["desc"])

    def test_missing_keys_are_flagged_not_faked(self) -> None:
        missing = [row for row in PAYLOAD["almanac"]["plants"] if not row["resolved"]["name"]]
        self.assertEqual([row["id"] for row in missing], ["minishroom"])
        self.assertNotIn(missing[0]["nameKey"], ENGLISH)

    def test_keys_have_no_brackets(self) -> None:
        for row in PAYLOAD["garden"]["collectables"]:
            key = row["rewardDialogTitleKey"]
            self.assertFalse(key.startswith("[") or key.endswith("]"), key)

    def test_zombie_sheet_almanac_coverage_is_counted(self) -> None:
        """U1 的「没有花名册」必须有量化证据：属性表总数与带 Almanac 偏移的条数都要报出来。"""
        counts = PAYLOAD["almanac"]["counts"]
        self.assertGreater(counts["zombiePropertySheets"], 0)
        self.assertLess(counts["zombieSheetsWithAlmanacOffset"], counts["zombiePropertySheets"])
        report = (REPO / mg.DEFAULT_REPORT).read_text(encoding="utf-8")
        self.assertIn(str(counts["zombieSheetsWithAlmanacOffset"]) + " 条覆盖", report)


class TestGardenAndQuests(unittest.TestCase):
    """售价与奖励只写实测到的数，匹配不到就 null。"""

    def test_prices_only_when_matched(self) -> None:
        priced = {row["typeName"]: row["soldAs"] for row in PAYLOAD["garden"]["collectables"] if row["soldAs"]}
        self.assertIn("sprout", priced)
        self.assertEqual(priced["sprout"]["matchKind"], "item")
        self.assertEqual(priced["sprout"]["priceKind"], "gems")
        # sprout 在商品表里有多档（5/10/20…），必须报出候选数，不能把某一档当成唯一售价
        self.assertGreaterEqual(priced["sprout"]["candidates"], 2)
        self.assertTrue(priced["sprout"]["priceGems"])
        generic = next(row for row in PAYLOAD["garden"]["collectables"] if row["typeName"] == "pinata")
        self.assertIsNone(generic["soldAs"])
        self.assertEqual(generic["storeCategory"], "pinata")

    def test_drop_sources_keyed_like_collectables(self) -> None:
        """奖励表的 SubType 带序号（egypt1），归一后必须能对上 `pinata_<world>`。"""
        rows = {row["typeName"]: row for row in PAYLOAD["garden"]["collectables"]}
        self.assertIn("pinata_egypt", rows)
        sources = rows["pinata_egypt"]["dropSources"]
        self.assertTrue(sources)
        self.assertEqual([item["table"] for item in sources], ["QuestRewardTablesProps"])
        self.assertTrue(sources[0]["examples"][0].startswith("difficulty="))
        self.assertRegex(sources[0]["examples"][0], r"difficulty=\d+$")
        with_source = [name for name, row in rows.items() if row["dropSources"]]
        self.assertGreaterEqual(len(with_source), 5)
        self.assertEqual(len(with_source), PAYLOAD["garden"]["counts"]["collectablesWithDropSource"])

    def test_zen_garden_numbers(self) -> None:
        props = PAYLOAD["garden"]["zenGarden"]["props"]
        self.assertEqual(props["PlantGrowDurationInSeconds"], 18000)
        self.assertEqual(props["NormalPlantCoinRewardAmount"], 50)
        self.assertEqual(len(PAYLOAD["garden"]["zenGarden"]["pots"]), 12)

    def test_quest_rewards_are_typed(self) -> None:
        kinds = set()
        for row in PAYLOAD["quests"]["quests"]:
            for award in row["rewards"] or []:
                kinds.add(award["type"])
                self.assertTrue(award["type"])
        self.assertEqual(kinds, {"coins", "gems", "pinata"})

    def test_reward_amounts_match_raw_awards(self) -> None:
        """`Amount` 在包里是 JSON 数字，必须原样落成文本，不能丢成空串。"""
        counts = PAYLOAD["quests"]["counts"]
        self.assertEqual(counts["rewardRows"], 80)
        self.assertEqual(counts["rewardRowsWithAmount"], counts["rewardRows"])

        raw: dict[str, list[str]] = {}
        for obj in TABLES["QuestMgr"]:
            for entry in (obj.get("objdata") or {}).get("Quests") or []:
                for wrapper, inner in entry.items():
                    if not isinstance(inner, dict) or "CompletionAwards" not in inner:
                        continue
                    awards = (inner.get("CompletionAwards") or {}).get("Awards") or []
                    raw.setdefault(inner.get("UniqueID"), []).extend(str(a.get("Amount")) for a in awards)
        checked = 0
        for row in PAYLOAD["quests"]["quests"]:
            if row["rewards"] is None:
                continue
            self.assertEqual([award["amount"] for award in row["rewards"]], raw[row["id"]])
            checked += 1
        self.assertEqual(checked, 69)
        epic = next(row for row in PAYLOAD["quests"]["quests"] if row["id"] == "EPICQUEST")
        self.assertEqual([award["amount"] for award in epic["rewards"]], ["1000"])

    def test_reward_table_numbers_are_filled(self) -> None:
        """奖励表的 MinAmount/MaxAmount/Weight 也是 JSON 数字。"""
        rows = [award for table in PAYLOAD["quests"]["rewardTables"] for award in table["awards"]]
        self.assertEqual(len(rows), 6)
        for award in rows:
            for field in ("minAmount", "maxAmount", "weight"):
                self.assertRegex(award[field], r"^\d+(?:\.\d+)?$")

    def test_every_unknown_has_id_topic_question(self) -> None:
        for item in PAYLOAD["unknowns"]:
            self.assertTrue(item["id"].startswith("U"))
            self.assertTrue(item["topic"])
            self.assertTrue(item["question"])


class TestDeterminismAndCheck(unittest.TestCase):
    """两次生成必须字节相同；--check 对过期产物返回 2。"""

    def test_two_builds_are_byte_identical(self) -> None:
        """同一份原料渲染两次 + 换一份新原料重建，三者必须字节相同。"""
        cached = mg.render_json(PAYLOAD)
        self.assertEqual(cached, mg.render_json(PAYLOAD))
        rebuilt = mg.render_json(mg.build(OBB))
        self.assertEqual(cached, rebuilt)
        self.assertTrue(cached.endswith("\n"))

    def test_render_is_stable_for_same_payload(self) -> None:
        self.assertEqual(mg.render_json(PAYLOAD), mg.render_json(PAYLOAD))
        self.assertEqual(mg.render_report(PAYLOAD), mg.render_report(PAYLOAD))

    def test_write_outputs_roundtrip(self) -> None:
        """写盘走 emit（mkdir parents），写出来的字节与渲染结果一致。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "deep" / "dir"
            json_path = root / "metagame.json"
            report_path = root / "report.md"
            mg.write_outputs(PAYLOAD, json_path, mg.render_report(PAYLOAD), report_path)
            self.assertEqual(json_path.read_bytes(), mg.render_json(PAYLOAD).encode("utf-8"))
            self.assertEqual(report_path.read_bytes(), mg.render_report(PAYLOAD).encode("utf-8"))

    def test_check_detects_stale_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "metagame.json"
            report_path = root / "report.md"
            json_path.write_text("{}\n", encoding="utf-8")
            report_path.write_text("stale\n", encoding="utf-8")
            self.assertEqual(
                run_main(["--json", str(json_path), "--report", str(report_path), "--check"]), 2
            )

    def test_committed_outputs_are_current(self) -> None:
        if not (JSON_PATH.is_file() and REPORT_PATH.is_file()):
            self.skipTest("产物尚未生成")
        self.assertEqual(run_main(["--check"]), 0)
        data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        self.assertEqual(data["marker"], mg.MARKER)
        self.assertEqual(data["counts"]["almanacPlants"], PAYLOAD["counts"]["almanacPlants"])

    def test_report_has_required_sections(self) -> None:
        text = mg.render_report(PAYLOAD)
        for heading in ("## 一、方法与边界", "## 三、图鉴", "## 四、花园", "## 五、成就·任务", "## 七、原版没有的部分", "## 八、未知项"):
            with self.subTest(heading=heading):
                self.assertIn(heading, text)
        self.assertIn("serverOnly", text)


if __name__ == "__main__":
    unittest.main()
