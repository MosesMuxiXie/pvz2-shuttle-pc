# -*- coding: utf-8 -*-
"""植物名册合并（`tools/contentc/plants_merge.py`）的回归测试。

这些用例钉的是**实测数字**，不是任务书里的目标数字：本版 OBB 的 PlantType 有
339 条，手工名册 147 条里只有 44 条与它同名，另外 103 条（融合植物、中式花园、
活动植物）在原版里没有对应项。所以「手工行一条都不删」的前提下，合并结果必然
是 147 + 295 = 442，`339` 只能靠删掉 103 条手工行才凑得出。测试把这条算术写死，
免得以后有人照着「339」去改数据。
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.contentc import plants_merge as pm  # noqa: E402
from tools import obb_build_content_v2 as builder  # noqa: E402

PLANTS = REPO / "content" / "plants.json"
PACK_JSON = REPO / "native" / "generated" / "plants_from_pack.json"


def _rows() -> list[dict]:
    return json.loads(PLANTS.read_text(encoding="utf-8"))


class CountsTest(unittest.TestCase):
    """147 手工 + 295 pack-only = 442；冲突 44 来自 skipped_existing。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = pm.build()

    def test_measured_counts(self) -> None:
        c = self.result.counts
        self.assertEqual(c["total"], 442)
        self.assertEqual(c["authored"], 147)
        self.assertEqual(c["pack"], 295)
        self.assertEqual(c["conflicts"], 44)
        self.assertEqual(c["packRoster"], 339)
        self.assertEqual(c["skippedExisting"], 44)
        self.assertEqual(self.result.total, 442)

    def test_three_hundred_thirty_nine_is_not_reachable_without_deleting(self) -> None:
        """把「339 = 147 + 192」这条算术钉死成反例。"""
        c = self.result.counts
        self.assertNotEqual(c["total"], 339)
        self.assertEqual(c["authored"] + c["pack"], 442)
        self.assertEqual(c["packRoster"] - c["conflicts"], c["pack"])

    def test_conflicts_are_the_skipped_existing_ids(self) -> None:
        _pack, skipped = pm.load_pack()
        self.assertEqual(sorted(skipped), sorted(self.result.conflicts))

    def test_merged_ids_are_unique_and_pack_rows_sorted(self) -> None:
        ids = [row["id"] for row in self.result.rows]
        self.assertEqual(len(ids), len(set(ids)))
        added = [row["id"] for row in self.result.rows[147:]]
        self.assertEqual(added, sorted(added))
        self.assertEqual(added, self.result.pack_only)


class AuthoredRowsTest(unittest.TestCase):
    """手工 147 行必须逐字段原样出现，且不带来源标记。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = pm.build()
        cls.disk = _rows()

    def test_disk_still_holds_only_the_authored_rows(self) -> None:
        """盘上还是 147 条手工行；合并结果只在小样/显式写入时出现。"""
        self.assertEqual(len(self.disk), 147)

    def test_authored_rows_are_emitted_verbatim_in_order(self) -> None:
        authored = self.disk
        self.assertEqual([row["id"] for row in authored],
                         [row["id"] for row in self.result.rows[:147]])
        self.assertEqual(authored, self.result.rows[:147])

    def test_no_authored_row_carries_a_source_marker(self) -> None:
        for row in self.disk:
            self.assertNotIn("source", row, row["id"])

    def test_every_added_row_is_tagged_pack(self) -> None:
        for row in self.result.rows[147:]:
            self.assertEqual(row.get("source"), "pack", row["id"])

    def test_previously_generated_rows_are_not_treated_as_authored(self) -> None:
        manual = pm.load_manual()
        self.assertEqual(len(manual), 147)
        self.assertTrue(all("source" not in row for row in manual))

    def test_rendering_the_merge_is_not_what_is_on_disk(self) -> None:
        """合并结果 442 条，盘上 147 条——这正是需要队长裁决的那一步。"""
        self.assertNotEqual(pm.render(self.result.rows), PLANTS.read_bytes())


class MergeRulesTest(unittest.TestCase):
    """用小样本钉合并规则本身。"""

    def test_conflict_keeps_the_authored_row(self) -> None:
        manual = [{"id": "pea", "hp": 300, "name_zh": "豌豆"}]
        pack = [{"id": "pea", "hp": 999, "name_zh": "PACK"}]
        result = pm.merge_rows(manual, pack)
        self.assertEqual(result.conflicts, ["pea"])
        self.assertEqual(result.total, 1)
        self.assertEqual(result.rows[0]["hp"], 300)
        self.assertNotIn("source", result.rows[0])

    def test_pack_row_drops_empty_fields_and_keeps_id_first(self) -> None:
        row = {"id": "x", "art": None, "desc_zh": "", "tags": [], "extra": {},
               "hp": 100, "name_zh": "某"}
        cleaned = pm.clean_pack_row(row)
        self.assertEqual(list(cleaned)[0], "id")
        self.assertEqual(cleaned["hp"], 100)
        self.assertEqual(cleaned["source"], "pack")
        for key in ("art", "desc_zh", "tags", "extra"):
            self.assertNotIn(key, cleaned)

    def test_duplicate_id_in_manual_is_an_error(self) -> None:
        with self.assertRaises(pm.MergeError):
            pm.merge_rows([{"id": "a"}, {"id": "a"}], [])

    def test_duplicate_id_in_pack_is_an_error(self) -> None:
        with self.assertRaises(pm.MergeError):
            pm.merge_rows([], [{"id": "a"}, {"id": "a"}])

    def test_missing_id_is_an_error(self) -> None:
        with self.assertRaises(pm.MergeError):
            pm.merge_rows([{"hp": 1}], [])

    def test_unknown_source_marker_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plants.json"
            path.write_text(json.dumps([{"id": "a", "source": "hand"}]), encoding="utf-8")
            with self.assertRaises(pm.MergeError):
                pm.load_manual(path)


class RenderTest(unittest.TestCase):
    """落盘格式与幂等：同一输入两次写出的字节必须一致。"""

    def test_render_is_stable(self) -> None:
        first = pm.render(pm.build().rows)
        second = pm.render(pm.build().rows)
        self.assertEqual(hashlib.sha256(first).hexdigest(),
                         hashlib.sha256(second).hexdigest())
        self.assertFalse(first.endswith(b"\n"))
        self.assertTrue(first.startswith(b"[\n {"))

    def test_check_reports_the_shipped_file_as_stale(self) -> None:
        """盘上 147 条 ≠ 合并结果 442 条，`--check` 必须如实报不一致。"""
        ok, message, _result = pm.check()
        self.assertFalse(ok)
        self.assertIn("不一致", message)


class CliTest(unittest.TestCase):
    """`--check` / `-n` / 篡改检测。"""

    def _run(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = pm.main(list(argv))
        return code, buffer.getvalue()

    def test_check_flags_the_shipped_file_as_stale(self) -> None:
        code, out = self._run("--check")
        self.assertEqual(code, 1, out)
        self.assertIn("不一致", out)
        self.assertIn("plants=442", out)

    def test_check_detects_a_tampered_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "plants.json"
            copy.write_bytes(PLANTS.read_bytes() + b" ")
            code, out = self._run("--check", "--out", str(copy))
            self.assertEqual(code, 1, out)
            self.assertIn("不一致", out)

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "plants.json"
            code, text = self._run("-n", "--out", str(out))
            self.assertEqual(code, 0, text)
            self.assertFalse(out.exists())
            self.assertIn("plants=442", text)

    def test_write_then_check_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "plants.json"
            code, _ = self._run("--out", str(out))
            self.assertEqual(code, 0)
            first = out.read_bytes()
            code, _ = self._run("--out", str(out))
            self.assertEqual(code, 0)
            self.assertEqual(first, out.read_bytes())
            code, _ = self._run("--check", "--out", str(out))
            self.assertEqual(code, 0)

    def test_second_generation_has_the_same_sha256(self) -> None:
        digests = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "plants.json"
                self._run("--out", str(out))
                digests.append(hashlib.sha256(out.read_bytes()).hexdigest())
        self.assertEqual(digests[0], digests[1])


class BuilderWiringTest(unittest.TestCase):
    """builder 侧的两个入口都走同一个合并器。"""

    def test_build_plants_roster_matches_the_module(self) -> None:
        result = builder.build_plants_roster()
        self.assertEqual(result.counts, pm.build().counts)
        self.assertEqual(result.counts["total"], 442)

    def test_content_report_line_has_the_plant_counts(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = builder.main(["--content-report"])
        text = buffer.getvalue()
        self.assertEqual(code, 0, text)
        self.assertIn("plants=147 authored=147 pack=295 conflicts=44 merged=442", text)
        self.assertIn("mismatches: none", text)


class ShapeTest(unittest.TestCase):
    """合并后的行本身要经得起引擎与工具读。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.added = pm.build().rows[147:]

    def test_no_pack_row_carries_an_empty_string(self) -> None:
        for row in self.added:
            for key, value in row.items():
                self.assertNotEqual(value, "", f"{row['id']}.{key}")

    def test_pack_rows_keep_the_fields_the_catalog_expects(self) -> None:
        rows = self.added
        self.assertEqual(len(rows), 295)
        for row in rows:
            self.assertTrue(row.get("name_zh") or row.get("name_en"), row["id"])
            self.assertIn("hp", row, row["id"])
            self.assertIn("behavior", row, row["id"])
            self.assertIsNotNone(row.get("cost"), row["id"])
        # 原版的 PlantType 表只给了英文名，中文名一个都没有：合并器不编造中文，
        # 只把 name_en 留下（引擎的 name_zh 是可缺省项）。
        self.assertEqual(sum(1 for row in rows if not row.get("name_zh")), 295)
        self.assertEqual(sum(1 for row in rows if not row.get("name_en")), 0)

    def test_rows_without_art_are_still_valid_and_counted(self) -> None:
        rows = self.added
        with_art = [row["id"] for row in rows if row.get("art")]
        without = [row["id"] for row in rows if not row.get("art")]
        self.assertEqual(len(with_art) + len(without), len(rows))
        # 295 条里只有 25 条能在原版美术库里命中，其余 270 条没有 art——
        # 这是真实缺口，报告里逐条列出，不在这里补假路径。
        self.assertEqual(len(with_art), 25)
        self.assertEqual(len(without), 270)


if __name__ == "__main__":
    unittest.main()
