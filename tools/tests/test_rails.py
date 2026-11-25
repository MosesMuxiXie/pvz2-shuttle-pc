"""`tools/contentc/rails.py` 的验收测试。

运行::

    python -m unittest tools.tests.test_rails -v
    python -m unittest discover -s tools/tests -p 'test_*.py'
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.contentc import rails  # noqa: E402
from tools import obb_build_content_v2 as builder  # noqa: E402

OBB = REPO.parent.parent / "work" / "obb_packages"
LEVELS = REPO / "content" / "levels"

TOTAL_LEVELS = 1809
RAIL_LEVELS = 204
FUNCTIONAL = 192
DECORATIVE = 6
UNKNOWN = 6
CLIENT_FLAGGED = 192
FLAGGED_NO_DATA = 0
FUNCTIONAL_UNFLAGGED = 0
VASE_ORIGINAL = 47
VASE_CLIENT = 47
VASE_MISSING: list[str] = []
BOSS_MODULE_LEVELS = 71
BOSS_STAGE_NAMED = 18
CLIENT_BOSS = 71
STAGE_KEYS = 1385
STAGE_KEY_DUPLICATES = 246
STAGE_KEY_EXTRA_FILES = 424
KONGFU_BOGUS = [
    "kongfu_5",
    "kongfu_10",
    "kongfu_15",
    "kongfu_20",
    "kongfu_25",
    "kongfu_30",
    "kongfu_40",
]


def run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = rails.main(argv)
    return code, out.getvalue(), err.getvalue()


def build_payload() -> dict:
    return rails.build(OBB, LEVELS)


class RailsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not OBB.is_dir() or not LEVELS.is_dir():
            raise unittest.SkipTest("缺少 obb 或关卡目录")
        cls.payload = build_payload()
        cls.candidates = rails.build_candidates(cls.payload)
        cls.by_level = {row["level"]: row for row in cls.payload["levels"]}

    # --- 计数 ---------------------------------------------------------------

    def test_counts_match_probed_numbers(self) -> None:
        counts = self.payload["counts"]
        self.assertEqual(counts["levels"], TOTAL_LEVELS)
        self.assertEqual(counts["railLevels"], RAIL_LEVELS)
        self.assertEqual(counts["functional"], FUNCTIONAL)
        self.assertEqual(counts["decorative"], DECORATIVE)
        self.assertEqual(counts["unknown"], UNKNOWN)
        self.assertEqual(counts["clientFlagged"], CLIENT_FLAGGED)
        self.assertEqual(counts["flaggedWithoutRailData"], FLAGGED_NO_DATA)
        self.assertEqual(counts["functionalUnflagged"], FUNCTIONAL_UNFLAGGED)
        self.assertEqual(
            counts["functional"] + counts["decorative"] + counts["unknown"], RAIL_LEVELS
        )

    def test_class_counts(self) -> None:
        classes = self.payload["classes"]
        self.assertEqual(classes["RailcartProperties"]["count"], 202)
        self.assertEqual(classes["RailcartProperties"]["verdicts"]["functional"], 195)
        self.assertEqual(classes["RailcartProperties"]["verdicts"]["decorative"], 6)
        self.assertEqual(classes["RailcartProperties"]["verdicts"]["unknown"], 1)
        self.assertEqual(classes["DangerRoomRailcartDesigner"]["count"], 2)
        self.assertEqual(classes["RailcartTutorialIntroProperties"]["verdicts"]["decorative"], 1)

    # --- 判定 ---------------------------------------------------------------

    def test_functional_levels_have_cart_evidence(self) -> None:
        for row in self.payload["levels"]:
            if row["verdict"] != "functional":
                continue
            evidence = [obj["evidence"] for obj in row["modules"]]
            self.assertTrue(
                any(item["carts"] > 0 or item["hasCountField"] for item in evidence),
                f"{row['level']} 判为 functional 但没有车位参数",
            )

    def test_unknown_levels_are_kept(self) -> None:
        unknown = [row for row in self.payload["levels"] if row["verdict"] == "unknown"]
        self.assertEqual(len(unknown), UNKNOWN)
        for row in unknown:
            self.assertTrue(
                row["moduleNames"] or row["modules"],
                f"{row['level']} 既没有模块也没有对象，不该出现在 rail 清单里",
            )
            if row["modules"]:
                for obj in row["modules"]:
                    self.assertEqual(obj["evidence"]["carts"], 0)
                    self.assertEqual(obj["evidence"]["rails"], 0)

    def test_decorative_levels_have_rails_only(self) -> None:
        decorative = [row for row in self.payload["levels"] if row["verdict"] == "decorative"]
        self.assertEqual(len(decorative), DECORATIVE)
        for row in decorative:
            for obj in row["modules"]:
                self.assertEqual(obj["evidence"]["carts"], 0)
                self.assertGreater(obj["evidence"]["rails"], 0)

    def test_known_levels(self) -> None:
        self.assertEqual(self.by_level["kongfu_35"]["verdict"], "functional")
        self.assertTrue(self.by_level["kongfu_35"]["client"]["minecarts"])
        self.assertEqual(self.by_level["cowboy_6"]["verdict"], "functional")
        self.assertEqual(self.by_level["iceage_65"]["verdict"], "unknown")

    # --- 砸罐子 -------------------------------------------------------------

    def test_boss_counting_uses_zomboss_module(self) -> None:
        counts = self.payload["counts"]
        self.assertEqual(counts["bossModuleLevels"], BOSS_MODULE_LEVELS)
        self.assertEqual(counts["bossStageNamed"], BOSS_STAGE_NAMED)
        self.assertEqual(counts["clientBoss"], CLIENT_BOSS)
        self.assertIn("ZombossBattle", self.payload["identity"]["bossCounting"])

    def test_stage_key_needs_package_disambiguation(self) -> None:
        counts = self.payload["counts"]
        self.assertEqual(counts["stageKeys"], STAGE_KEYS)
        self.assertEqual(counts["stageKeyDuplicates"], STAGE_KEY_DUPLICATES)
        self.assertEqual(counts["stageKeyExtraFiles"], STAGE_KEY_EXTRA_FILES)
        self.assertIn("extra.package", self.payload["identity"]["stageKey"])

    def test_no_client_level_carries_flags_without_data(self) -> None:
        # t52 之后：原版没有 rail 数据的关卡一律不带 rail/minecarts。
        self.assertEqual(self.payload["flaggedEvidence"], [])
        self.assertEqual(self.payload["flaggedWithoutRailData"], [])
        for level_id in KONGFU_BOGUS:
            doc = json.loads((LEVELS / f"{level_id}.json").read_text(encoding="utf-8"))
            self.assertNotIn("minecarts", doc["extra"], level_id)
            self.assertNotIn("rail", doc["extra"], level_id)

    def test_vasebreaker_is_complete(self) -> None:
        vase = self.payload["vasebreaker"]
        self.assertEqual(len(vase["original"]), VASE_ORIGINAL)
        self.assertEqual(len(vase["client"]), VASE_CLIENT)
        self.assertEqual(vase["missing"], VASE_MISSING)
        flagged = {item["level"] for item in vase["original"] if item["clientVasebreaker"]}
        self.assertEqual(flagged, {item["level"] for item in vase["original"]})
        for level_id in ("pirate_41", "plantagenet_18"):
            item = next(row for row in vase["original"] if row["level"] == level_id)
            self.assertTrue(item["clientVasebreaker"], level_id)
            self.assertIn("VaseBreakerArcade", item["modules"])
            self.assertIn("VaseBreakerProps", item["modules"])

    def test_candidates_payload(self) -> None:
        candidates = self.candidates
        self.assertEqual(candidates["vasebreaker_add"], [])
        self.assertEqual(candidates["minecarts"], [])
        self.assertEqual(candidates["minecarts_remove"], [])
        self.assertEqual(candidates["minecarts_remove_evidence"], [])
        keep = candidates["minecarts_keep"]
        self.assertEqual(len(keep), 190)
        for level_id in ("cowboy_6", "cowboy_12", "kongfu_35"):
            self.assertIn(level_id, keep)
        for key in ("vasebreaker_add", "minecarts", "minecarts_remove", "minecarts_keep"):
            self.assertIn(key, candidates["rationale"])

    def test_report_corrects_vasebreaker_label_claim(self) -> None:
        report = rails.render_report(self.payload)
        self.assertIn("不存在玩法标签错位", report)
        self.assertNotIn("整体错位", report)
        self.assertIn("pkg_1390", report)
        self.assertIn("PirateBossStage", report)
        self.assertIn("ZombossBattle", report)
        self.assertIn("已无候选", report)

    # --- 确定性 -------------------------------------------------------------

    def test_render_is_deterministic(self) -> None:
        again = build_payload()
        self.assertEqual(rails.render_json(self.payload), rails.render_json(again))
        self.assertEqual(rails.render_report(self.payload), rails.render_report(again))

    def test_json_is_sorted_and_newline_terminated(self) -> None:
        text = rails.render_json(self.payload)
        self.assertTrue(text.endswith("\n"))
        parsed = json.loads(text)
        self.assertEqual(parsed["marker"], "rails-semantics-v1")
        self.assertLessEqual(len(parsed["levels"]), RAIL_LEVELS)

    # --- CLI ----------------------------------------------------------------

    def test_cli_writes_and_check_accepts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            json_path = base / "rails.json"
            cand_path = base / "cand.json"
            report_path = base / "report.md"
            argv = [
                "--obb",
                str(OBB),
                "--levels",
                str(LEVELS),
                "--json",
                str(json_path),
                "--candidates",
                str(cand_path),
                "--report",
                str(report_path),
            ]
            code, out, _ = run(argv)
            self.assertEqual(code, 0, out)
            self.assertTrue(json_path.is_file() and cand_path.is_file() and report_path.is_file())

            code, out, err = run(argv + ["--check"])
            self.assertEqual(code, 0, err)
            self.assertIn("产物已是最新", out)

            # 篡改后应报过期
            json_path.write_text("{}\n", encoding="utf-8")
            code, _, err = run(argv + ["--check"])
            self.assertEqual(code, 2)
            self.assertIn("产物过期", err)

    def test_cli_check_on_committed_artifacts(self) -> None:
        code, _, err = run(["--check"])
        self.assertEqual(code, 0, err)

    def test_cli_missing_inputs_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run(["--obb", str(Path(tmp) / "nope"), "--json", str(Path(tmp) / "a.json")])
            self.assertEqual(code, 2)
            self.assertIn("obb 目录不存在", err)
            code, _, err = run(["--levels", str(Path(tmp) / "nope")])
            self.assertEqual(code, 2)
            self.assertIn("关卡目录不存在", err)

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            json_path = base / "rails.json"
            code, out, _ = run(
                ["--json", str(json_path), "--candidates", str(base / "c.json"), "--report", str(base / "r.md"), "-n"]
            )
            self.assertEqual(code, 0)
            self.assertIn("dry-run", out)
            self.assertFalse(json_path.exists())

    # --- 报告 ---------------------------------------------------------------

    def test_report_sections_and_numbers(self) -> None:
        report = rails.render_report(self.payload)
        for token in (
            "## 一、判据与为什么单开一个工具",
            "## 二、结论表一：功能矿车关卡",
            "## 三、结论表二：装饰铁轨关卡",
            "## 四、结论表三：拿不准",
            "## 五、客户端标记对账",
            "## 六、砸罐子标记",
            "## 七、两件遗留事项的处置建议",
            "pirate_41",
            "plantagenet_18",
            "VaseBreakerArcade",
            "192 关",
            "已无候选",
        ):
            self.assertIn(token, report)


class BuilderDerivationTest(unittest.TestCase):
    """`rail` / `minecarts` / `vasebreaker` 必须能从原版表重算出来。

    这里的核心是「可复现」：盘上的三个标记要与 builder 的派生结果逐关相同，
    而把派生逻辑摘掉之后同一份盘必须立刻对不上 —— 否则标记还是手写残留。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.facts = builder.load_rail_facts()
        cls.levels = {}
        for path in sorted(LEVELS.glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            cls.levels[doc["extra"]["package"]] = (doc["id"], doc["extra"])

    def test_every_original_package_has_facts(self) -> None:
        self.assertEqual(len(self.facts), TOTAL_LEVELS)
        self.assertEqual(set(self.levels), set(self.facts))

    def test_disk_flags_are_the_derived_ones(self) -> None:
        counts, mismatches = builder.content_flag_report()
        self.assertEqual(counts["levels"], TOTAL_LEVELS)
        self.assertEqual(counts["vasebreaker"], 47)
        self.assertEqual(counts["minecarts"], 190)
        self.assertEqual(counts["rail"], 192)
        self.assertEqual(counts["derivedVasebreaker"], counts["vasebreaker"])
        self.assertEqual(counts["derivedMinecarts"], counts["minecarts"])
        self.assertEqual(counts["derivedRail"], counts["rail"])
        self.assertEqual(mismatches, [], f"content/levels 与原版不一致：{mismatches[:5]}")

    def test_builder_emits_the_same_flags_it_derives(self) -> None:
        # 端到端：真的跑一遍 build_levels（内存里，不写盘），标记数必须等于盘上的派生口径。
        zh, en = builder.base.collect_strings()
        builder.setup_tables()
        grouped, _unknown, _special, _stats = builder.build_levels(zh, en, rail_table=self.facts)
        counted = {"vasebreaker": 0, "minecarts": 0, "rail": 0}
        total = 0
        for levels in grouped.values():
            for level in levels:
                total += 1
                extra = level.get("extra") or {}
                for key in counted:
                    if extra.get(key):
                        counted[key] += 1
        self.assertEqual(total, TOTAL_LEVELS)
        self.assertEqual(counted, {"vasebreaker": 47, "minecarts": 190, "rail": 192})

    def test_removing_the_derivation_makes_the_content_stale(self) -> None:
        # 这就是「删掉 builder 里的派生逻辑后重建会红」的那条断言。
        original = builder.derive_flags
        builder.derive_flags = lambda facts: {}
        try:
            counts, mismatches = builder.content_flag_report()
        finally:
            builder.derive_flags = original
        self.assertEqual(counts["derivedVasebreaker"], 0)
        self.assertEqual(counts["derivedRail"], 0)
        self.assertGreater(len(mismatches), 0)
        self.assertTrue(any("rail" in line for line in mismatches))
        self.assertTrue(any("vasebreaker" in line for line in mismatches))

    def test_bogus_kongfu_flags_are_gone(self) -> None:
        for package in ("pkg_1371", "pkg_1376", "pkg_1382", "pkg_1387", "pkg_1390", "pkg_1401", "pkg_1415"):
            _level_id, extra = self.levels[package]
            self.assertNotIn("minecarts", extra, package)
            self.assertNotIn("rail", extra, package)
            self.assertEqual(builder.derive_flags(self.facts[package]), {}, package)

    def test_decorative_and_unknown_packages_stay_unflagged(self) -> None:
        # decorative：只有 Rails 没有车；unknown：既无车也无轨。
        for package in ("pkg_0853", "pkg_1687"):
            derived = builder.derive_flags(self.facts[package])
            self.assertNotIn("rail", derived, package)
            self.assertNotIn("minecarts", derived, package)

    def test_danger_room_gets_rail_without_lanes(self) -> None:
        for package, level_id in (("pkg_0435", "cowboy_41"), ("pkg_0466", "cowboy_42")):
            derived = builder.derive_flags(self.facts[package])
            self.assertTrue(derived.get("rail"), package)
            self.assertNotIn("minecarts", derived, package)
            _id, extra = self.levels[package]
            self.assertEqual(_id, level_id)
            self.assertTrue(extra.get("rail"))
            self.assertNotIn("minecarts", extra)

    def test_vasebreaker_comes_from_the_module_list(self) -> None:
        for package, level_id in (("pkg_1557", "pirate_41"), ("pkg_1576", "plantagenet_18")):
            self.assertEqual(self.levels[package][0], level_id)
            self.assertTrue(self.levels[package][1].get("vasebreaker"), package)
            self.assertIn("vasebreaker", builder.derive_flags(self.facts[package]))

    def test_module_names_are_parsed_not_character_stripped(self) -> None:
        modules = self.facts["pkg_0435"]["modules"]
        self.assertIn("DangerRoomIntro", modules)
        self.assertIn("DefaultSunDropper", modules)
        self.assertNotIn("angerRoomIntro", modules)
        self.assertNotIn("efaultSunDropper", modules)
        self.assertIn("Rails", self.facts["pkg_1687"]["modules"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

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
