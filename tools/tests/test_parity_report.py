"""Tests for the parity matrix generator.

Run either way:
    python tools/tests/test_parity_report.py
    python -m unittest discover -s tools/tests -p "test_*.py"
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.parity_report import build_parity_matrix, render_markdown  # noqa: E402

OBB = REPO.parent.parent / "work" / "obb_packages"


def matrix():
    return build_parity_matrix(OBB, REPO / "content", REPO / "native")


class ParityReportTest(unittest.TestCase):
    def test_totals_from_obb(self):
        m = matrix()
        self.assertEqual(m.rows["植物"].total, 339)
        self.assertEqual(m.rows["僵尸"].total, 1127)
        self.assertGreater(m.rows["融合"].total, 0)
        self.assertEqual(m.rows["世界"].total, m.worlds_in_content)

    def test_level_reference_closure(self):
        m = matrix()
        self.assertEqual(m.rows["关卡"].total, 1809)
        self.assertEqual(m.missing_plants, [])
        self.assertEqual(m.missing_zombies, [])
        self.assertTrue(m.level_plants)
        self.assertTrue(m.level_zombies)

    def test_render_has_header(self):
        text = render_markdown(matrix(), "test")
        self.assertIn("| 类别 | 总量 | 数据 | 接线 | 可玩 | 校准 |", text)
        self.assertIn("生成时间：test", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
