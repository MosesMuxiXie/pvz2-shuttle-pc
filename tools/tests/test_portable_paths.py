"""生成产物必须是可移植的：不得写入本机绝对路径。

第一版 ``vasebreaker.json`` / ``minigames.json`` / ``armors_from_pack.json`` /
``bosses_from_pack.json`` / ``projectiles_from_pack.json`` / ``s5_data_gaps.json``
把 ``str(obb_dir)`` 原样写进 ``sources``，于是产物里嵌了
``D:\\OneDrive\\文档\\pvz_shuttle\\work\\obb_packages``。后果有两个：

* 换 clone 目录重跑 ``--check``，同一份数据算出的字节不同 —— 干净 clone
  永远报「产物过期」，这条链就不可重放了；
* 把本机目录结构带进了发行物。

修法是把这些字段过一遍 ``portable()``（写 ``work/obb_packages`` 这类工作区相对串）。
这个测试是守卫：任何人再往产物里塞绝对路径，这里就红。
"""

from __future__ import annotations

import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
GENERATED = REPO / "native" / "generated"

# 盘符绝对路径（C:\... 或 C:/...）与已知的本机目录名。
DRIVE = re.compile(r"\b[A-Za-z]:[\\/]")
HOST_MARKERS = ("pvz_shuttle", "OneDrive", "\\Users\\", "/Users/")


class GeneratedArtifactsArePortableTests(unittest.TestCase):
    def test_no_absolute_path_in_generated_json(self):
        offenders: list[str] = []
        for path in sorted(GENERATED.glob("*.json")):
            text = path.read_text(encoding="utf-8")
            if DRIVE.search(text):
                offenders.append(f"{path.name}: drive-letter path")
            for marker in HOST_MARKERS:
                if marker in text:
                    offenders.append(f"{path.name}: {marker}")
        self.assertEqual([], offenders, "generated json must stay portable")

    def test_no_absolute_path_in_generated_reports(self):
        offenders: list[str] = []
        for path in sorted(GENERATED.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            if DRIVE.search(text):
                offenders.append(f"{path.name}: drive-letter path")
            for marker in HOST_MARKERS:
                if marker in text:
                    offenders.append(f"{path.name}: {marker}")
        self.assertEqual([], offenders, "generated reports must stay portable")

    def test_portable_prefers_workspace_relative_paths(self):
        import sys

        sys.path.insert(0, str(REPO / "tools" / "contentc"))
        from portable import portable, WORKSPACE  # noqa: E402

        inside = REPO / "native" / "generated"
        expected = inside.resolve().relative_to(WORKSPACE).as_posix()
        self.assertEqual(expected, portable(inside))
        self.assertNotIn(":", portable(inside))
        outside = pathlib.Path.home() / "somewhere" / "obb_packages"
        self.assertEqual("somewhere/obb_packages", portable(outside))


if __name__ == "__main__":
    unittest.main()
