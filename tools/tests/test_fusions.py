#!/usr/bin/env python3
"""fusions.py（S5.1 融合配方编译）的单元测试。

运行：
    python -m unittest tools.tests.test_fusions -v
    python -m unittest discover -s tools/tests -p 'test_*.py'

覆盖契约：
(a) pack 对数 == 实测常量（85；同时锁住 217 objects / 199 带 objdata 的口径）
(b) 能归一成 client id 的配对数 == 实测常量（27 条 sourceKind=client）
(c) 同一份输入两次 dump 字节相同
(d) report 含表头与差集小节
(e) 归一失败的配对带 sourceKind="pack"，没有被丢弃
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.contentc import fusions  # noqa: E402

OBB = Path(
    os.environ.get("PVZ2_OBB_DIR") or (REPO.parent.parent / "work" / "obb_packages")
)
CONTENT = REPO / "content"

# 实测常量：改数据源时必须同步改这里，测试就是用来发现“悄悄变了”的。
PACK_PAIRS = 85
OBJECTS_TOTAL = 217
OBJECTS_WITH_DATA = 199
PAIRS_CLIENT = 27
SHARED_KEYS = 48
CONTENT_RECIPES = 85
CONTENT_VARIANTS = 39
UNIQUE_RESULTS = 46


@contextlib.contextmanager
def quiet():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        yield buf


def run_main(args: list[str]) -> int:
    with quiet():
        return fusions.main(args)


class FusionCompileTest(unittest.TestCase):
    """源表口径、归一与对齐。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = fusions.compile_fusions()

    def test_pack_pair_count_matches_measured_constant(self) -> None:
        """(a) 217 objects / 199 带 objdata / 1 个 config / 85 条 FusionPairs。"""
        self.assertEqual(self.result.objects, OBJECTS_TOTAL)
        self.assertEqual(self.result.objects_with_data, OBJECTS_WITH_DATA)
        self.assertEqual(self.result.configs, 1)
        self.assertEqual(len(self.result.pairs), PACK_PAIRS)
        self.assertEqual(self.result.counts["pairs"], PACK_PAIRS)
        self.assertEqual(self.result.counts["objectsWithData"], OBJECTS_WITH_DATA)

    def test_pairs_normalized_to_client(self) -> None:
        """(b) 27 条配对的两位 ingredient 都是 client id。"""
        self.assertEqual(self.result.counts["pairsClient"], PAIRS_CLIENT)
        client_pairs = [p for p in self.result.pairs if p.source_kind == "client"]
        self.assertEqual(len(client_pairs), PAIRS_CLIENT)
        known = {row["id"] for row in json.loads((CONTENT / "plants.json").read_text(encoding="utf-8"))}
        fused = {
            r["result"]["id"]
            for r in json.loads((CONTENT / "fusions.json").read_text(encoding="utf-8"))["recipes"]
        }
        for pair in client_pairs:
            self.assertIn(pair.source, known | fused)
            self.assertIn(pair.fusion, known | fused)

    def test_unresolved_pairs_are_kept_as_pack(self) -> None:
        """(e) 归一不了的配对保留原值并标 pack，且一条都不丢。"""
        pack_pairs = [p for p in self.result.pairs if p.source_kind == "pack"]
        self.assertEqual(len(pack_pairs), PACK_PAIRS - PAIRS_CLIENT)
        self.assertEqual(self.result.counts["pairsPack"], PACK_PAIRS - PAIRS_CLIENT)
        for pair in pack_pairs:
            self.assertTrue(pair.source and pair.fusion)
            self.assertNotEqual(pair.source, "")
            self.assertNotEqual(pair.fusion, "")
        # 每条 raw 都留了原始字段，便于回查
        for pair in self.result.pairs:
            self.assertEqual(
                set(pair.raw),
                {"SourcePlant", "FusionPlant", "ResultPlant", "FusionOnlyHasResultPlant", "FusionSoundEvent"},
            )

    def test_result_column_resolves_to_fused_ids(self) -> None:
        """结果列 85/85 都能对上 content 的 fused_* id。"""
        self.assertEqual(self.result.counts["resultsResolved"], PACK_PAIRS)
        fused = {
            r["result"]["id"]
            for r in json.loads((CONTENT / "fusions.json").read_text(encoding="utf-8"))["recipes"]
        }
        for pair in self.result.pairs:
            self.assertIn(pair.result, fused)

    def test_alignment_with_content(self) -> None:
        """配方键 48/48 相交，两侧多重集一致，基础结果数与 pack 唯一结果数相等。"""
        alignment = self.result.alignment
        self.assertEqual(len(alignment.shared), SHARED_KEYS)
        self.assertEqual(alignment.only_pack, ())
        self.assertEqual(alignment.only_content, ())
        self.assertTrue(alignment.pack_multiplicity_equal)
        self.assertEqual(self.result.counts["contentRecipes"], CONTENT_RECIPES)
        self.assertEqual(self.result.counts["contentKeys"], SHARED_KEYS)
        self.assertEqual(self.result.counts["contentVariants"], CONTENT_VARIANTS)
        self.assertEqual(self.result.counts["uniqueResult"], UNIQUE_RESULTS)
        self.assertEqual(
            self.result.counts["contentBaseResults"] + self.result.counts["contentVariants"],
            CONTENT_RECIPES,
        )
        self.assertEqual(self.result.counts["contentBaseResults"], UNIQUE_RESULTS)
        content = json.loads((CONTENT / "fusions.json").read_text(encoding="utf-8"))["recipes"]
        base = {
            r["result"]["id"]
            for r in content
            if not re.search(r"_\d+$", r["result"]["id"])
        }
        pack_results = {pair.result for pair in self.result.pairs}
        self.assertEqual(base, pack_results)
        self.assertEqual(len(pack_results), UNIQUE_RESULTS)

    def test_payload_is_sorted_and_complete(self) -> None:
        """pairs 按 (source,fusion) 有序，字段齐全。"""
        pairs = self.result.payload_pairs
        self.assertEqual(len(pairs), PACK_PAIRS)
        keys = [(p["source"], p["fusion"]) for p in pairs]
        self.assertEqual(keys, sorted(keys))
        for item in pairs:
            self.assertEqual(
                set(item),
                {"source", "fusion", "result", "onlyResult", "sound", "sourceKind", "raw"},
            )
            self.assertIn(item["sourceKind"], {"client", "pack"})
        self.assertEqual(sum(1 for p in pairs if p["onlyResult"]), 4)


class FusionCliTest(unittest.TestCase):
    """CLI 产物：字节一致、check 模式、report 小节。"""

    def test_two_runs_are_byte_identical(self) -> None:
        """(c) 同一份输入两次 dump 字节相同。"""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            json_path = tmpdir / "fusions_from_pack.json"
            report_path = tmpdir / "fusion_report.md"
            code = run_main(["--json", str(json_path), "--report", str(report_path)])
            self.assertEqual(code, 0)
            first = (json_path.read_bytes(), report_path.read_bytes())
            code = run_main(["--json", str(json_path), "--report", str(report_path)])
            self.assertEqual(code, 0)
            second = (json_path.read_bytes(), report_path.read_bytes())
            self.assertEqual(first, second)
            self.assertGreater(len(first[0]), 1000)

    def test_report_sections(self) -> None:
        """(d) report 顶部结论、计数、对齐差集小节齐全。"""
        result = fusions.compile_fusions()
        report = fusions.render_report(result)
        for needle in (
            "## 口径与结论",
            "## 计数",
            "## 归一",
            "## 与 content 对齐",
            "### 交集",
            "### 只在 pack",
            "### 只在 content",
            "## 结论：哪些 client 融合配方在 pack 里根本没有",
            f"FusionPairs（对数） | {PACK_PAIRS}",
            f"配方键（pack） | {SHARED_KEYS}",
            "没有**",
            "_3",
        ):
            self.assertIn(needle, report)
        self.assertNotIn("只在 pack（0 个）\n\n- `", report)

    def test_check_mode_accepts_fresh_and_rejects_stale(self) -> None:
        """--check 接受刚生成的产物；改一个字节后必须失败。"""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            json_path = tmpdir / "fusions_from_pack.json"
            report_path = tmpdir / "fusion_report.md"
            self.assertEqual(run_main(["--json", str(json_path), "--report", str(report_path)]), 0)
            self.assertEqual(
                run_main(["--json", str(json_path), "--report", str(report_path), "--check"]), 0
            )
            report_path.write_text(report_path.read_text(encoding="utf-8") + "\n过期\n", encoding="utf-8")
            self.assertEqual(
                run_main(["--json", str(json_path), "--report", str(report_path), "--check"]), 1
            )

    def test_missing_inputs_exit_two(self) -> None:
        """缺输入退 2，不写半成品。"""
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            code = run_main(
                [
                    "--config",
                    str(tmpdir / "nope.json"),
                    "--json",
                    str(tmpdir / "out.json"),
                    "--report",
                    str(tmpdir / "out.md"),
                ]
            )
            self.assertEqual(code, 2)
            self.assertFalse((tmpdir / "out.json").exists())

    def test_committed_outputs_are_current(self) -> None:
        """仓库里的产物与当前代码一致（否则 --check 在 CI 里会红）。"""
        result = fusions.compile_fusions()
        self.assertEqual(fusions.DEFAULT_JSON.read_text(encoding="utf-8"), fusions.render_json(result))
        self.assertEqual(fusions.DEFAULT_REPORT.read_text(encoding="utf-8"), fusions.render_report(result))

    def test_json_schema_shape(self) -> None:
        """JSON 顶层字段与 format/generated 标记固定。"""
        payload = json.loads(fusions.render_json(fusions.compile_fusions()))
        self.assertEqual(payload["format"], 1)
        self.assertEqual(payload["generated"], fusions.MARKER)
        self.assertEqual(set(payload), {"format", "generated", "sources", "counts", "pairs"})
        self.assertTrue(all(re.match(r"^[\w./-]+$", p) for p in payload["sources"].values()))
        self.assertEqual(payload["counts"]["pairs"], len(payload["pairs"]))


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
