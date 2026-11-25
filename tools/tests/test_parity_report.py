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

import os

OBB = Path(
    os.environ.get("PVZ2_OBB_DIR") or (REPO.parent.parent / "work" / "obb_packages")
)


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

# 干净 clone 里没有 work/obb_packages（原版表目录不进仓库）：缺目录时整套跳过，
# 而不是每个用例报 FileNotFoundError。想真跑就设 PVZ2_OBB_DIR 指到解包目录。
if not OBB.is_dir():
    import unittest as _unittest

    for _name, _obj in list(globals().items()):
        if isinstance(_obj, type) and issubclass(_obj, _unittest.TestCase):
            setattr(_obj, "__unittest_skip__", True)
            setattr(_obj, "__unittest_skip_why__", f"缺少原版表目录 {OBB}（设 PVZ2_OBB_DIR）")
