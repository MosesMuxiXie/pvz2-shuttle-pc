# -*- coding: utf-8 -*-
"""可玩植物子集评估（`tools/contentc/plant_playable.py`）的回归测试。

这些用例钉的是**实测数字**：原版 `PlantType` 名册 339 条（295 条 pack 行 + 44 条同名
skipped_existing），按「成本 > 0 / 有族 / 有美术」三条判据逐条判，293 条可玩
（42 条已在手工名册 + 251 条新增候选），46 条被阻断（缺成本 23、缺美术 26、两者都缺 3）。
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.contentc import plant_playable as pp  # noqa: E402

TOTAL = 339
PLAYABLE = 293
PLAYABLE_NEW = 251
PLAYABLE_AUTHORED = 42
BLOCKED = 46
MISSING_COST = 23
MISSING_COST_NULL = 2
MISSING_COST_ZERO = 21
MISSING_FAMILY = 0
MISSING_ART = 26
BOTH = 3
SAME_AS_AUTHORED = 44
AUTHORED_BLOCKED = 2


def built() -> dict:
    return pp.build()


class PayloadShapeTest(unittest.TestCase):
    def test_top_level_keys(self):
        payload = built()
        self.assertEqual(
            sorted(payload),
            ["blockers", "counts", "format", "marker", "playable", "playableNew", "rows", "sources"],
        )
        self.assertEqual(payload["marker"], "plant-playable-v1")
        self.assertEqual(payload["format"], 1)

    def test_every_row_carries_the_full_verdict(self):
        payload = built()
        self.assertEqual(len(payload["rows"]), TOTAL)
        for row in payload["rows"]:
            self.assertEqual(set(row), set(pp.ROW_KEYS))
            self.assertTrue(set(row["blockers"]) <= set(pp.BLOCKERS))
            self.assertEqual(row["playable"], not row["blockers"])

    def test_ids_are_unique_and_sorted(self):
        rows = built()["rows"]
        ids = [row["id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, sorted(ids))


class CountsTest(unittest.TestCase):
    def test_counts_are_the_measured_numbers(self):
        counts = built()["counts"]
        self.assertEqual(counts["total"], TOTAL)
        self.assertEqual(counts["playable"], PLAYABLE)
        self.assertEqual(counts["playableNew"], PLAYABLE_NEW)
        self.assertEqual(counts["playableAuthored"], PLAYABLE_AUTHORED)
        self.assertEqual(counts["blocked"], BLOCKED)
        self.assertEqual(counts["missingCost"], MISSING_COST)
        self.assertEqual(counts["missingCostNull"], MISSING_COST_NULL)
        self.assertEqual(counts["missingCostZero"], MISSING_COST_ZERO)
        self.assertEqual(counts["missingFamily"], MISSING_FAMILY)
        self.assertEqual(counts["missingArt"], MISSING_ART)
        self.assertEqual(counts["blockedBoth"], BOTH)
        self.assertEqual(counts["sameAsAuthored"], SAME_AS_AUTHORED)
        self.assertEqual(counts["blockedAuthored"], AUTHORED_BLOCKED)
        self.assertEqual(counts["hasPackRow"], TOTAL)

    def test_counts_close(self):
        counts = built()["counts"]
        self.assertEqual(counts["playable"] + counts["blocked"], counts["total"])
        self.assertEqual(
            counts["blocked"],
            counts["missingCost"] + counts["missingArt"] - counts["blockedBoth"],
        )
        self.assertEqual(
            counts["playable"],
            counts["playableAuthored"] + counts["playableNew"],
        )
        self.assertEqual(
            counts["playableNew"],
            counts["total"] - counts["sameAsAuthored"] - (counts["blocked"] - counts["blockedAuthored"]),
        )


class BlockerTest(unittest.TestCase):
    def test_cost_blockers_are_twenty_three(self):
        payload = built()
        ids = payload["blockers"]["no-cost"]
        self.assertEqual(len(ids), MISSING_COST)
        rows = {row["id"]: row for row in payload["rows"]}
        self.assertIsNone(rows["blastspinnercocoon"]["cost"])
        self.assertIsNone(rows["imitater"]["cost"])
        self.assertEqual(rows["potatochip"]["cost"], 0)
        self.assertEqual(rows["marigold"]["cost"], 0)
        for rid in ids:
            self.assertFalse(rows[rid]["hasCost"])
            self.assertIn("no-cost", rows[rid]["blockers"])

    def test_art_blockers_are_twenty_six(self):
        payload = built()
        ids = payload["blockers"]["no-art"]
        self.assertEqual(len(ids), MISSING_ART)
        self.assertIn("apsarlotus", ids)
        self.assertIn("cornucopia", ids)
        self.assertIn("bubblecoral", ids)
        rows = {row["id"]: row for row in payload["rows"]}
        for rid in ids:
            self.assertFalse(rows[rid]["hasArt"])
            self.assertIsNone(rows[rid]["artName"])

    def test_both_blockers_overlap_is_three(self):
        payload = built()
        both = [row["id"] for row in payload["rows"] if len(row["blockers"]) > 1]
        self.assertEqual(sorted(both), ["blastspinnercocoon", "imppear_teto", "littleguy"])

    def test_family_coverage_is_complete(self):
        payload = built()
        self.assertEqual(payload["blockers"]["no-family"], [])
        families = {row["family"] for row in payload["rows"]}
        self.assertEqual(
            families,
            {
                "boomerang",
                "chomp",
                "fume",
                "instant",
                "lob",
                "mine",
                "produce",
                "shoot",
                "spike",
                "support",
                "wall",
            },
        )


class AuthoredOverlapTest(unittest.TestCase):
    def test_same_as_authored_is_the_roster_skip_list(self):
        payload = built()
        roster = json.loads(pp.DEFAULT_ROSTER.read_text(encoding="utf-8"))
        skipped = sorted(row["id"] for row in roster["skipped_existing"])
        same = sorted(row["id"] for row in payload["rows"] if row["sameAsAuthored"])
        self.assertEqual(len(skipped), SAME_AS_AUTHORED)
        self.assertEqual(same, skipped)

    def test_new_playable_never_repeats_an_authored_id(self):
        payload = built()
        content = json.loads(pp.DEFAULT_CONTENT.read_text(encoding="utf-8"))
        authored = {row["id"] for row in content}
        new = set(payload["playableNew"])
        self.assertEqual(len(new), PLAYABLE_NEW)
        self.assertEqual(new & authored, set())
        rows = {row["id"]: row for row in payload["rows"]}
        for rid in new:
            self.assertTrue(rows[rid]["playable"])
            self.assertFalse(rows[rid]["sameAsAuthored"])

    def test_blocked_authored_rows_are_the_zero_cost_pair(self):
        payload = built()
        blocked = sorted(row["id"] for row in payload["rows"] if row["sameAsAuthored"] and not row["playable"])
        self.assertEqual(blocked, ["iceburg", "potatochip"])


class EvidenceTest(unittest.TestCase):
    def test_rows_explain_themselves(self):
        payload = built()
        for row in payload["rows"]:
            self.assertGreaterEqual(len(row["evidence"]), 3, row["id"])
            if "no-cost" in row["blockers"]:
                self.assertTrue(any("cost" in line for line in row["evidence"]), row["id"])
            if "no-art" in row["blockers"]:
                self.assertTrue(any("art" in line for line in row["evidence"]), row["id"])
            if row["playable"]:
                self.assertTrue(any("family=" in line for line in row["evidence"]), row["id"])

    def test_art_normalisation_collapses_punctuation_and_case(self):
        self.assertEqual(pp._norm("PlantBanana"), "PLANTBANANA")
        self.assertEqual(pp._norm("plant-banana"), "PLANTBANANA")
        self.assertEqual(pp._norm(None), "")
        bases = pp.load_art_bases(pp.DEFAULT_ART_INDEX)
        self.assertGreaterEqual(len(bases), 1000)
        self.assertIn("PLANTBANANA", bases)


class RenderTest(unittest.TestCase):
    def test_two_renders_are_byte_identical(self):
        first = pp.render_json(built())
        second = pp.render_json(built())
        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        self.assertNotIn("\r", first)
        self.assertNotIn("\n\n", first)

    def test_committed_artifacts_are_current(self):
        payload = built()
        self.assertEqual(
            pp.DEFAULT_JSON.read_text(encoding="utf-8"), pp.render_json(payload)
        )
        self.assertEqual(
            pp.DEFAULT_REPORT.read_text(encoding="utf-8"), pp.render_report(payload)
        )

    def test_report_states_why_not_339(self):
        report = pp.render_report(built())
        for token in (
            "## 一、判据与数据源",
            "## 二、结果分布",
            "## 三、按 blocker 分组清单",
            "## 四、为什么不是 339",
            "## 五、若要把新增候选并进",
            "## 六、C57 收尾",
            "## 七、147 与 339 的包含关系",
            "## 八、复现",
            "## 九、边界",
            "44 条同名",
            "缺美术",
            "251 条判据全过",
        ):
            self.assertIn(token, report)
        self.assertNotIn("（无）\n\n（无）", report)


class C57SectionTest(unittest.TestCase):
    """C57 收尾：三块数据的消费者判定必须与实测一致。"""

    def setUp(self):
        self.facts = pp.load_patch_facts()

    def test_patch_460_9_is_present_and_counted(self):
        self.assertTrue(self.facts, "patch_460_9.json 缺失")
        self.assertEqual(self.facts["flags"], 271)
        self.assertEqual(self.facts["flagsTrue"], 215)
        self.assertEqual(self.facts["flagsFalse"], 56)
        self.assertEqual(len(self.facts["rlFields"]), 17)
        self.assertEqual(self.facts["rlLevelCount"], 12)
        self.assertEqual(self.facts["events"], 30)
        self.assertEqual(self.facts["eventRefs"], 445)
        self.assertEqual(self.facts["eventRefsUnique"], 373)
        self.assertEqual(self.facts["eventNew"], [29, 30, 31])

    def test_event_level_pool_is_absent_from_content(self):
        self.assertEqual(len(self.facts["rlTemplates"]), 18)
        self.assertEqual(self.facts["eventRefsPresent"], [])
        self.assertEqual(self.facts["rlTemplatesPresent"], [])

    def test_report_names_the_consumer_and_the_missing_layers(self):
        report = pp.render_report(built())
        self.assertIn("world.cpp:69-77", report)
        self.assertIn("world.cpp:167-180", report)
        self.assertIn("world.hpp:182-184", report)
        self.assertIn("main.cpp:288-290", report)
        self.assertIn("**无消费者**：缺 Roguelike 层", report)
        self.assertIn("**无消费者**：缺日历层 + 活动关卡池", report)
        self.assertIn("flow.cpp:10", report)
        self.assertIn("worldmap.cpp:232", report)


class RosterInclusionTest(unittest.TestCase):
    """147 条手工名册与 339 条 pack 名册的包含关系。"""

    def setUp(self):
        self.inc = pp.roster_inclusion()

    def test_manual_roster_splits_into_five_buckets(self):
        self.assertEqual(self.inc["manual"], 147)
        self.assertEqual(self.inc["pack"], 339)
        self.assertEqual(len(self.inc["inside"]), 44)
        self.assertEqual(len(self.inc["equivalent"]), 1)
        self.assertEqual(len(self.inc["fused"]), 85)
        self.assertEqual(len(self.inc["plantagenet"]), 14)
        self.assertEqual(len(self.inc["authored"]), 3)
        self.assertEqual(self.inc["authored"], ["gatling", "twinsunflower", "umbrellaleaf"])
        self.assertEqual(self.inc["equivalent"], [("fireflerry", "firefly")])
        self.assertEqual(
            len(self.inc["inside"])
            + len(self.inc["equivalent"])
            + len(self.inc["fused"])
            + len(self.inc["plantagenet"])
            + len(self.inc["authored"]),
            147,
        )

    def test_fireflerry_is_the_same_plant_as_pack_firefly(self):
        manual = {row["id"]: row for row in pp._read_json(pp.DEFAULT_CONTENT)}
        pack = {row["id"]: row for row in pp._read_json(pp.DEFAULT_PACK)["plants"]}
        mine, twin = manual["fireflerry"], pack["firefly"]
        self.assertEqual((mine["cost"], mine["hp"]), (twin["cost"], twin["hitpoints"]))
        self.assertEqual(twin["framework"], "PlantFirefly")
        # 反例：名字也近似，但成本/血量不同，不是同一植物
        other = pack["chrysantheautumn"]
        self.assertNotEqual(
            (manual["chrysanthea"]["cost"], manual["chrysanthea"]["hp"]),
            (other["cost"], other["hitpoints"]),
        )
        self.assertNotIn(("chrysanthea", "chrysantheautumn"), self.inc["equivalent"])

    def test_no_normalised_equality_and_two_near_names(self):
        self.assertEqual(self.inc["normalised"], [])
        self.assertEqual(
            self.inc["near"],
            [("chrysanthea", "chrysantheautumn"), ("fireflerry", "firefly")],
        )

    def test_report_states_the_subset_claim_is_false(self):
        report = pp.render_report(built())
        self.assertIn("「147 是 339 的子集」不成立", report)
        self.assertIn("只有 45/147", report)
        self.assertIn("改名证据", report)
        self.assertIn("不是**同一植物", report)


class CliTest(unittest.TestCase):
    def test_check_passes_on_committed_artifacts(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = pp.main(["--check"])
        self.assertEqual(code, 0, buffer.getvalue())
        self.assertIn("产物已是最新", buffer.getvalue())

    def test_check_detects_a_tampered_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "plant_playable.json"
            report_path = Path(tmp) / "report.md"
            json_path.write_text(pp.render_json(built()), encoding="utf-8")
            report_path.write_text(pp.render_report(built()) + "\n篡改", encoding="utf-8")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = pp.main(["--check", "--json", str(json_path), "--report", str(report_path)])
            self.assertEqual(code, 1, buffer.getvalue())
            self.assertIn("不是最新", buffer.getvalue())

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            json_path = Path(tmp) / "out.json"
            report_path = Path(tmp) / "out.md"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = pp.main(["-n", "--json", str(json_path), "--report", str(report_path)])
            self.assertEqual(code, 0)
            self.assertFalse(json_path.exists())
            self.assertFalse(report_path.exists())
            self.assertIn("playable=293", buffer.getvalue())

    def test_missing_input_exits_two(self):
        buffer = io.StringIO()
        with contextlib.redirect_stderr(buffer), contextlib.redirect_stdout(io.StringIO()):
            code = pp.main(["--roster", str(Path(tempfile.gettempdir()) / "nope.json"), "-n"])
        self.assertEqual(code, 2)
        self.assertIn("缺少输入", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

# 这个模块要靠解出来的美术索引（4.6 GB，不进仓库）：缺了就整类跳过。
import unittest as _unittest
from pathlib import Path as _Path

_assets = _Path(__file__).resolve().parents[2].parent.parent / "PvZ2SHUTTLE" / "assets"
if not _assets.is_dir():
    for _name, _obj in list(globals().items()):
        if isinstance(_obj, type) and issubclass(_obj, _unittest.TestCase):
            setattr(_obj, "__unittest_skip__", True)
            setattr(_obj, "__unittest_skip_why__", f"缺少美术索引 {_assets}")
