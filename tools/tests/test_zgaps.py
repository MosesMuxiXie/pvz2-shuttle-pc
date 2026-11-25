"""僵尸行为族缺口（T41）的回归测试。

运行：
    python -m unittest tools.tests.test_zgaps -v
    python -m unittest discover -s tools/tests -p "test_*.py"
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

from tools.contentc import zgaps  # noqa: E402

OBB = Path(
    os.environ.get("PVZ2_OBB_DIR") or (REPO.parent.parent / "work" / "obb_packages")
)
CONTENT = REPO / "content" / "zombies.json"
MAPPING = REPO / "native" / "generated" / "id_mapping.csv"

# 数据事实（探针实测，2026-11-24）：
#   content/zombies.json 55 条，其中 28 条在 id_mapping.csv 有 pack 行（exact 20 + manual 8），
#   27 条没有原版条目（garden 10 / gang 5 / market 5 / royal 7）。
TOTAL = 55
WITH_EVIDENCE = 28
AUTHORED = 27
# 2026-11-24 队长批准后已写入 content 的三条补丁；剩余缺口应为 0。
APPLIED = {"football", "garden_gargantuar", "royal_chef_gargantuar"}
GAPS: set[str] = set()
PACK_PRESENT = 20
FAMILY_COUNTS = {"walk": 50, "gargantuar": 5}
CURRENT_COUNTS = {"walk": 49, "jump": 1, "gargantuar": 5}


def run_mapping(out_dir: Path) -> int:
    return zgaps.main(
        [
            "--obb",
            str(OBB),
            "--content",
            str(CONTENT),
            "--mapping",
            str(MAPPING),
            "--json",
            str(out_dir / "zombie_family_gaps.json"),
            "--report",
            str(out_dir / "zombie-gaps.md"),
        ]
    )


def quiet_run(out_dir: Path) -> int:
    with contextlib.redirect_stdout(io.StringIO()):
        return run_mapping(out_dir)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class ZgapsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name)
        code = quiet_run(cls.out)
        if code != 0:
            raise AssertionError(f"zgaps.main 返回 {code}")
        cls.json_path = cls.out / "zombie_family_gaps.json"
        cls.report_path = cls.out / "zombie-gaps.md"
        cls.payload = load(cls.json_path)
        cls.report = cls.report_path.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    # --- 结构 -------------------------------------------------------------

    def test_schema(self) -> None:
        payload = self.payload
        self.assertEqual(payload["format"], zgaps.FORMAT)
        self.assertEqual(payload["generated"], zgaps.MARKER)
        self.assertEqual(set(payload["counts"]), set(zgaps.COUNT_KEYS))
        for row in payload["rows"]:
            self.assertEqual(set(row), set(zgaps.ROW_KEYS))
        self.assertEqual([r["clientId"] for r in payload["rows"]], sorted(r["clientId"] for r in payload["rows"]))
        self.assertIn("appliedPatches", payload)
        for item in payload["appliedPatches"]:
            self.assertEqual(
                set(item),
                {"clientId", "before", "after", "currentBehavior", "currentFamily", "family", "applied", "approved", "basis"},
            )

    def test_totals(self) -> None:
        counts = self.payload["counts"]
        self.assertEqual(counts["total"], TOTAL)
        self.assertEqual(len(self.payload["rows"]), TOTAL)
        self.assertEqual(counts["withEvidence"], WITH_EVIDENCE)
        self.assertEqual(counts["authored"], AUTHORED)
        self.assertEqual(counts["stillUnknown"], 0)
        self.assertEqual(counts["gaps"], len(GAPS))
        self.assertEqual(counts["appliedPatches"], len(APPLIED))
        self.assertEqual(counts["packPresentInContentPack"], PACK_PRESENT)
        self.assertEqual(counts["withEvidence"] + counts["authored"] + counts["stillUnknown"], TOTAL)

    def test_every_row_has_evidence(self) -> None:
        for row in self.payload["rows"]:
            self.assertTrue(row["evidence"], row["clientId"])
            for item in row["evidence"]:
                self.assertIsInstance(item, str)
                self.assertTrue(item.strip(), row["clientId"])
            if row["confidence"] == "pack":
                self.assertTrue(
                    any(item.startswith("pkg_") for item in row["evidence"]),
                    f"{row['clientId']} 标了 pack 却没有 pkg_ 证据",
                )
            if row["confidence"] == "authored":
                self.assertTrue(row["note"].strip(), f"{row['clientId']} 标了 authored 却没写理由")
                self.assertIsNone(row["className"])

    def test_families_are_engine_vocabulary(self) -> None:
        allowed = set(zgaps.FAMILIES)
        for row in self.payload["rows"]:
            self.assertIn(row["family"], allowed, row["clientId"])
            if row["currentFamily"] is not None:
                self.assertIn(row["currentFamily"], allowed, row["clientId"])
        dist = self.payload["counts"]["familyDistribution"]
        self.assertEqual(sum(dist.values()), TOTAL)
        self.assertEqual({k: v for k, v in dist.items() if v}, FAMILY_COUNTS)
        current = self.payload["counts"]["currentDistribution"]
        self.assertEqual(sum(current.values()), TOTAL)
        self.assertEqual({k: v for k, v in current.items() if v}, CURRENT_COUNTS)

    # --- 缺口与已应用补丁 ---------------------------------------------------

    def test_no_gaps_remain_after_the_approved_patch(self) -> None:
        gaps = [r for r in self.payload["rows"] if r["gap"]]
        self.assertEqual({r["clientId"] for r in gaps}, GAPS)
        self.assertEqual(self.payload["gaps"], [])

    def test_applied_patches_reach_the_content_file(self) -> None:
        applied = {item["clientId"]: item for item in self.payload["appliedPatches"]}
        self.assertEqual(set(applied), APPLIED)
        rows = {row["clientId"]: row for row in self.payload["rows"]}
        for cid, item in applied.items():
            self.assertEqual(item["before"], "walk")
            self.assertEqual(item["after"], "gargantuar")
            self.assertTrue(item["applied"], cid)
            self.assertEqual(item["currentBehavior"], "gargantuar", cid)
            self.assertEqual(rows[cid]["currentBehavior"], "gargantuar", cid)
            self.assertEqual(rows[cid]["currentFamily"], "gargantuar", cid)
            self.assertEqual(rows[cid]["family"], "gargantuar", cid)
            self.assertFalse(rows[cid]["gap"], cid)
            self.assertIn("已应用补丁", rows[cid]["note"])

    def test_pole_vaulter_keeps_content_behavior(self) -> None:
        row = next(r for r in self.payload["rows"] if r["clientId"] == "pole_vaulter")
        self.assertEqual(row["currentBehavior"], "jump")
        self.assertEqual(row["currentFamily"], "jump")
        self.assertEqual(row["family"], "walk")
        self.assertFalse(row["gap"])
        self.assertIn("保留", row["note"])

    def test_gang_gargantuar_is_already_wired(self) -> None:
        row = next(r for r in self.payload["rows"] if r["clientId"] == "gang_gargantuar")
        self.assertEqual(row["family"], "gargantuar")
        self.assertEqual(row["currentFamily"], "gargantuar")
        self.assertFalse(row["gap"])

    def test_pack_rows_come_from_mapping(self) -> None:
        pack_rows = [r for r in self.payload["rows"] if r["confidence"] == "pack"]
        self.assertEqual(len(pack_rows), WITH_EVIDENCE)
        for row in pack_rows:
            self.assertTrue(row["packId"], row["clientId"])
            self.assertTrue(row["className"], row["clientId"])
            self.assertIn(row["matchKind"], {"exact", "manual"})

    # --- 产物与确定性 -------------------------------------------------------

    def test_two_runs_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            other_dir = Path(other)
            self.assertEqual(quiet_run(other_dir), 0)
            for name in ("zombie_family_gaps.json", "zombie-gaps.md"):
                self.assertEqual(
                    (self.out / name).read_bytes(),
                    (other_dir / name).read_bytes(),
                    name,
                )

    def test_committed_artifacts_are_current(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = zgaps.main(
                [
                    "--obb",
                    str(OBB),
                    "--content",
                    str(CONTENT),
                    "--mapping",
                    str(MAPPING),
                    "--check",
                ]
            )
        self.assertEqual(exit_code, 0)

    def test_check_detects_stale_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            out = Path(other)
            self.assertEqual(quiet_run(out), 0)
            target = out / "zombie_family_gaps.json"
            payload = load(target)
            payload["counts"]["total"] = 54
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                code = zgaps.main(
                    [
                        "--obb",
                        str(OBB),
                        "--content",
                        str(CONTENT),
                        "--mapping",
                        str(MAPPING),
                        "--json",
                        str(target),
                        "--report",
                        str(out / "zombie-gaps.md"),
                        "--check",
                    ]
                )
            self.assertEqual(code, 2)

    def test_missing_obb_exits_2(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            out = Path(other)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = zgaps.main(
                    [
                        "--obb",
                        str(out / "nope"),
                        "--content",
                        str(CONTENT),
                        "--mapping",
                        str(MAPPING),
                        "--json",
                        str(out / "zombie_family_gaps.json"),
                        "--report",
                        str(out / "zombie-gaps.md"),
                    ]
                )
            self.assertEqual(code, 2)

    # --- 报告 -------------------------------------------------------------

    def test_report_sections(self) -> None:
        for token in (
            "## 结论摘要",
            "## 一、",
            "## 二、",
            "## 三、",
            "## 四、",
            "## 五、",
            "## 六、",
            "source_codename",
            "content/zombies.json",
            "已应用补丁",
            "改前",
            "改后",
            "队长批准",
        ):
            self.assertIn(token, self.report, token)

    def test_report_lists_all_six_engine_families(self) -> None:
        for family in ("walk", "jump", "steal", "summon", "gargantuar", "fly"):
            self.assertIn(family, self.report, family)

    def test_report_reconciles_the_20_claim(self) -> None:
        self.assertIn("20", self.report)
        self.assertIn("id_mapping", self.report)
        for cid in sorted(APPLIED):
            self.assertIn(cid, self.report)
        self.assertIn("behavior", self.report)
        # 报告不要让下一个人以为「20 条没 behavior」。
        self.assertIn("同名命中", self.report)
        self.assertIn("COMPLETENESS", self.report)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# 干净 clone 里没有 work/obb_packages（原版表目录不进仓库）：缺目录时整套跳过，
# 而不是每个用例报 FileNotFoundError。想真跑就设 PVZ2_OBB_DIR 指到解包目录。
if not OBB.is_dir():
    import unittest as _unittest

    for _name, _obj in list(globals().items()):
        if isinstance(_obj, type) and issubclass(_obj, _unittest.TestCase):
            setattr(_obj, "__unittest_skip__", True)
            setattr(_obj, "__unittest_skip_why__", f"缺少原版表目录 {OBB}（设 PVZ2_OBB_DIR）")
