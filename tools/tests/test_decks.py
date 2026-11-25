#!/usr/bin/env python3
"""decks.py 的验收测试。

运行：
    python -m unittest tools.tests.test_decks -v
    python -m unittest discover -s tools/tests -p 'test_*.py'

断言的是“报告对现实的陈述必须自洽且可复现”：
  - 1809 关全部进统计，26 个世界一行不少；
  - deck 引用的 id 必须能在 plants.json 里找到（否则点名）；
  - 缺真模型清单唯一、排序稳定、两次生成字节一致；
  - --check 在报告过期时退出码非 0。
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.contentc import decks  # noqa: E402

LEVELS = REPO / "content" / "levels"
PLANTS = REPO / "content" / "plants.json"
ASSETS = REPO.parent.parent / "PvZ2SHUTTLE" / "assets"

EXPECTED_LEVELS = 1809
EXPECTED_WORLDS = 26
EXPECTED_SLOTS = 7194
EXPECTED_USED_PLANTS = 41


def run_main(argv: list[str]) -> tuple[int, str, str]:
    """跑一次 main，收集 stdout/stderr。"""

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = decks.main(argv)
    return code, out.getvalue(), err.getvalue()


@unittest.skipUnless(
    LEVELS.is_dir() and PLANTS.is_file() and (ASSETS / "db" / "MANIFEST.json").is_file(),
    "缺少关卡、植物注册表或美术库，跳过",
)
class DeckReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = decks.build(LEVELS, PLANTS, ASSETS)
        cls.text = decks.render_report(cls.report)

    def test_every_level_is_counted(self) -> None:
        self.assertEqual(self.report.totals.levels, EXPECTED_LEVELS)
        self.assertEqual(len(self.report.levels), EXPECTED_LEVELS)
        self.assertEqual(sum(w.levels for w in self.report.worlds), EXPECTED_LEVELS)
        self.assertEqual(self.report.totals.worlds, EXPECTED_WORLDS)
        self.assertEqual(len(self.report.worlds), EXPECTED_WORLDS)

    def test_deck_slots_and_distinct_plants(self) -> None:
        self.assertEqual(self.report.totals.slots, EXPECTED_SLOTS)
        self.assertEqual(self.report.totals.plants, EXPECTED_USED_PLANTS)
        self.assertEqual(len(self.report.used_plants), EXPECTED_USED_PLANTS)

    def test_deck_ids_all_exist_in_plants_json(self) -> None:
        self.assertEqual(self.report.unknown, ())
        known = set(self.report.used_plants)
        for row in self.report.levels:
            for pid in row.deck:
                self.assertIn(pid, known, f"{row.name} 引用了未统计的 id {pid}")

    def test_empty_deck_policy_is_documented(self) -> None:
        self.assertEqual(self.report.totals.empty_decks, 0)
        self.assertIn("空 deck", self.text)
        self.assertIn("seed_bank", self.text)
        self.assertIn("不参与", self.text)

    def test_world_table_has_one_row_per_world(self) -> None:
        section = self.text.split("## 逐世界覆盖", 1)[1].split("## ", 1)[0]
        rows = [
            line
            for line in section.splitlines()
            if line.startswith("| ") and not line.startswith("| 世界")
        ]
        # 最后一行是“**合计**”
        self.assertEqual(len(rows), EXPECTED_WORLDS + 1, f"世界表行数不对: {len(rows)}")
        self.assertTrue(rows[-1].startswith("| **合计**"), rows[-1])

    def test_missing_art_list_is_unique_and_sorted(self) -> None:
        ids = [m.id for m in self.report.missing]
        self.assertEqual(len(ids), len(set(ids)))
        uses = {m.id: m.uses for m in self.report.missing}
        self.assertEqual(ids, sorted(ids, key=lambda pid: (-uses[pid], pid)))
        for item in self.report.missing:
            self.assertNotEqual(item.tier, decks.TIER_ACTOR, f"{item.id} 有模型却进了缺模型清单")
            self.assertIn(item.tier, {decks.TIER_PNG, decks.TIER_NONE})

    def test_missing_tiers_and_totals_agree(self) -> None:
        total = self.report.totals
        self.assertEqual(total.with_actor + total.with_png + total.without_art, total.plants)
        self.assertEqual(len(self.report.missing), total.with_png + total.without_art)
        # 逐世界列的是“该世界缺模型的植物数”，同一株出现在多个世界会重复计；
        # 用关卡数据独立算一遍 (世界, 植物) 组合数，必须与表里的合计一致。
        missing_ids = {m.id for m in self.report.missing}
        pairs = {
            (row.world, pid)
            for row in self.report.levels
            for pid in row.deck
            if pid in missing_ids
        }
        self.assertEqual(
            sum(w.with_png + w.without_art for w in self.report.worlds),
            len(pairs),
        )

    def test_registry_coverage_is_reported_honestly(self) -> None:
        self.assertEqual(self.report.registry_total, 147)
        self.assertEqual(
            self.report.registry_actor + self.report.registry_png + self.report.registry_none,
            147,
        )
        self.assertLess(self.report.distinct_actors, self.report.registry_actor)
        self.assertIn("独立 actor", self.text)
        # 全部缺模型植物（不只是 deck 引用的那些）必须一条不落
        self.assertEqual(len(self.report.missing_all), 147 - self.report.registry_actor)
        self.assertEqual(
            len(self.report.missing_all),
            self.report.registry_png + self.report.registry_none,
        )
        self.assertGreater(len(self.report.missing_all), len(self.report.missing))
        self.assertTrue(all(m.uses == 0 for m in self.report.missing_all if m.id not in self.report.used_plants))
        # 复用表必须真的只列“2 株以上共用”
        for key, ids in self.report.reuse:
            self.assertGreater(len(ids), 1, key)
            self.assertLessEqual(len(ids), self.report.registry_actor)
        self.assertEqual(
            sum(len(ids) - 1 for _, ids in self.report.reuse),
            self.report.registry_actor - self.report.distinct_actors,
        )

    def test_report_has_conclusion_and_top20(self) -> None:
        self.assertIn("## 结论", self.text)
        self.assertIn("完整复刻", self.text)
        section = self.text.split(f"top {decks.TOP_MISSING}", 1)
        self.assertEqual(len(section), 2, "结论里缺少 top 20 清单")
        table = section[1]
        rows = [
            line
            for line in table.splitlines()
            if line.startswith("| ") and not line.startswith("| #")
        ]
        expected = min(decks.TOP_MISSING, len(self.report.missing_all))
        self.assertEqual(len(rows), expected, f"top 清单应有 {expected} 行，实得 {len(rows)}")

    def test_oversized_and_unknown_sections_exist(self) -> None:
        self.assertIn("## deck 超过", self.text)
        self.assertIn("## deck 引用但 plants.json 里不存在的 id", self.text)
        for row in self.report.oversized:
            self.assertGreater(len(row.deck), decks.DECK_WARN_SIZE)
        self.assertEqual(len(self.report.oversized), self.report.totals.oversized)

    def test_regeneration_is_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a.md"
            second = Path(tmp) / "b.md"
            code_a, _, _ = run_main(["--levels", str(LEVELS), "--plants", str(PLANTS), "--assets", str(ASSETS), "--report", str(first)])
            code_b, _, _ = run_main(["--levels", str(LEVELS), "--plants", str(PLANTS), "--assets", str(ASSETS), "--report", str(second)])
            self.assertEqual((code_a, code_b), (0, 0))
            digest_a = hashlib.sha256(first.read_bytes()).hexdigest()
            digest_b = hashlib.sha256(second.read_bytes()).hexdigest()
            self.assertEqual(digest_a, digest_b)
            self.assertEqual(first.read_text(encoding="utf-8"), self.text)

    def test_check_mode_accepts_fresh_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            self.assertEqual(run_main(["--levels", str(LEVELS), "--plants", str(PLANTS), "--assets", str(ASSETS), "--report", str(path)])[0], 0)
            code, _, _ = run_main(["--levels", str(LEVELS), "--plants", str(PLANTS), "--assets", str(ASSETS), "--report", str(path), "--check"])
            self.assertEqual(code, 0)

    def test_check_mode_rejects_stale_or_missing_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            code, _, err = run_main(["--levels", str(LEVELS), "--plants", str(PLANTS), "--assets", str(ASSETS), "--report", str(path), "--check"])
            self.assertEqual(code, 1)
            self.assertIn("不存在", err)

            self.assertEqual(run_main(["--levels", str(LEVELS), "--plants", str(PLANTS), "--assets", str(ASSETS), "--report", str(path)])[0], 0)
            stale = path.read_text(encoding="utf-8").replace("关卡总数", "关卡总数（过期）", 1)
            path.write_text(stale, encoding="utf-8")
            code, _, err = run_main(["--levels", str(LEVELS), "--plants", str(PLANTS), "--assets", str(ASSETS), "--report", str(path), "--check"])
            self.assertEqual(code, 1)
            self.assertIn("过期", err)

    def test_missing_inputs_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run_main(["--levels", str(Path(tmp) / "nope"), "--plants", str(PLANTS), "--assets", str(ASSETS)])
            self.assertEqual(code, 2)
            self.assertIn("缺少 levels", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
