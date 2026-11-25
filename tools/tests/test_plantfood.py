"""养料数据编译测试。

运行：
    python -m unittest tools.tests.test_plantfood -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.contentc import plantfood  # noqa: E402

OBB = REPO.parent.parent / "work" / "obb_packages"
PLANTS = OBB / "pkg_2074_PlantType.json"
PROPS = OBB / "pkg_2073_PlantPropertySheet.json"
MAPPING = REPO / "native" / "generated" / "id_mapping.csv"
FAMILIES = REPO / "native" / "generated" / "plant_families.json"

ROW_KEYS = {
    "id",
    "idKind",
    "packType",
    "framework",
    "durationSeconds",
    "playCount",
    "effects",
    "source",
    "gaps",
}
EFFECT_KEYS = {
    "kind",
    "projectile",
    "spawnOffset",
    "cooldownMin",
    "cooldownMax",
    "initialMin",
    "launchSound",
    "source",
}
ACTION_IDS = {
    "sungun",
    "homingthistle",
    "dartichoke",
    "draftodil1",
    "magnetfruit",
    "rheumnobile",
}
EXPECTED_COUNTS = {
    "withDuration": 147,
    "withPlayCount": 185,
    "withAction": 6,
    "animated": 147,
    "plants": 293,
    "plantsWithDuration": 147,
    "plantsWithPlayCount": 172,
    "propSheetObjects": 398,
    "missingEffectPlants": 333,
    "clientIds": 39,
    "playCountReachable": 170,
    "playCountUnreachable": 19,
    "playCountShared": 2,
    "durationRecords": 155,
    "playCountRecords": 189,
    "referencedProps": 335,
    "unreferencedProps": 63,
}


def run(tmp: Path, *, check: bool = False) -> tuple[int, Path, Path]:
    out_json = tmp / "plantfood_from_pack.json"
    out_md = tmp / "plantfood_report.md"
    argv = [
        "--obb",
        str(OBB),
        "--plants",
        str(PLANTS),
        "--props",
        str(PROPS),
        "--mapping",
        str(MAPPING),
        "--families",
        str(FAMILIES),
        "--json",
        str(out_json),
        "--report",
        str(out_md),
    ]
    if check:
        argv.append("--check")
    return plantfood.main(argv), out_json, out_md


class PlantfoodCompileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        code, cls.json_path, cls.md_path = run(cls.tmp)
        assert code == 0, code
        cls.payload = json.loads(cls.json_path.read_text(encoding="utf-8"))
        cls.report = cls.md_path.read_text(encoding="utf-8")
        cls.rows = cls.payload["plants"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_top_level_schema(self) -> None:
        self.assertEqual(self.payload["format"], 1)
        self.assertEqual(self.payload["generated"], "plantfood-compile-v1")
        self.assertIsInstance(self.payload["counts"], dict)
        self.assertIsInstance(self.rows, list)
        self.assertTrue(self.rows)

    def test_counts_match_measured_values(self) -> None:
        for key, want in EXPECTED_COUNTS.items():
            self.assertEqual(self.payload["counts"].get(key), want, key)

    def test_rows_are_sorted_and_well_formed(self) -> None:
        ids = [(r["id"], r["packType"]) for r in self.rows]
        self.assertEqual(ids, sorted(ids))
        for row in self.rows:
            self.assertEqual(set(row), ROW_KEYS, row["id"])
            self.assertEqual(row["source"], "pack")
            self.assertIn(row["idKind"], {"client", "pack"})
            for effect in row["effects"]:
                self.assertEqual(set(effect), EFFECT_KEYS)
                self.assertEqual(effect["source"], "pack")

    def test_six_plants_carry_pack_effects(self) -> None:
        tagged = {r["id"] for r in self.rows if r["effects"]}
        self.assertEqual(tagged, ACTION_IDS)
        for row in self.rows:
            if row["id"] not in ACTION_IDS:
                continue
            self.assertEqual(len(row["effects"]), 1, row["id"])
            effect = row["effects"][0]
            self.assertEqual(effect["kind"], "projectile")
            self.assertTrue(effect["projectile"])
            self.assertEqual(effect["source"], "pack")

    def test_draftodil_keeps_row_with_missing_cooldowns(self) -> None:
        row = next(r for r in self.rows if r["id"] == "draftodil1")
        self.assertEqual(row["packType"], "draftodil1")
        self.assertEqual(row["durationSeconds"], None)
        self.assertEqual(row["playCount"], 1)
        effect = row["effects"][0]
        self.assertEqual(effect["projectile"], "DraftodilPlantfoodDefault")
        self.assertIsNone(effect["cooldownMin"])
        self.assertIsNone(effect["cooldownMax"])
        self.assertIsNone(effect["initialMin"])
        self.assertEqual(effect["spawnOffset"], {"x": 10, "y": -25})

    def test_normalized_ids_use_client_vocabulary(self) -> None:
        for row in self.rows:
            if row["idKind"] == "client":
                self.assertEqual(row["id"], row["packType"])
            else:
                self.assertNotEqual(row["id"], "")
                self.assertEqual(row["id"], row["packType"])
        # 44 条精确命中里只有 39 株在本表有养料数据
        self.assertEqual(sum(1 for r in self.rows if r["idKind"] == "client"), 39)
        self.assertEqual(self.payload["counts"]["clientIds"], 39)
        # 6 株带动作的植物：只有 homingthistle 在客户端词汇表里
        action_rows = {r["packType"]: r["idKind"] for r in self.rows if r["effects"]}
        self.assertEqual(set(action_rows), ACTION_IDS)
        self.assertEqual(action_rows["homingthistle"], "client")
        self.assertEqual(
            {k for k, v in action_rows.items() if v == "pack"},
            ACTION_IDS - {"homingthistle"},
        )

    def test_gaps_track_missing_effects_only(self) -> None:
        with_effect = sum(1 for r in self.rows if r["effects"])
        gap_rows = sum(1 for r in self.rows if r["gaps"])
        self.assertEqual(gap_rows, len(self.rows) - with_effect)
        self.assertEqual(gap_rows, 287)
        for row in self.rows:
            self.assertEqual(row["gaps"], [] if row["effects"] else ["effect"], row["id"])

    def test_dump_is_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            other_path = Path(other)
            code, json2, md2 = run(other_path)
            self.assertEqual(code, 0)
            self.assertEqual(
                self.json_path.read_bytes(),
                json2.read_bytes(),
                "两次生成的 JSON 字节应完全一致",
            )
            self.assertEqual(
                self.md_path.read_bytes(),
                md2.read_bytes(),
                "两次生成的报告字节应完全一致",
            )

    def test_report_sections_and_headline(self) -> None:
        for needle in (
            "## 一句话结论",
            "## 计数",
            "## 6 株逐字段表",
            "## 覆盖率",
            "## 必须 authored 的部分",
            "## 口径与来源",
            "DraftodilDefault",
            "147",
            "185",
            "339",
            "直射",
            "抛射",
            "墙",
            "生产",
            "瞬时",
            "其他",
        ):
            self.assertIn(needle, self.report)
        head = "\n".join(self.report.splitlines()[:3])
        self.assertIn("弹道层", head)
        self.assertIn("authored", head)

    def test_check_accepts_fresh_output_and_rejects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            fresh = Path(other)
            self.assertEqual(run(fresh)[0], 0)
            self.assertEqual(run(fresh, check=True)[0], 0)
            (fresh / "plantfood_from_pack.json").write_text("{}\n", encoding="utf-8")
            self.assertEqual(run(fresh, check=True)[0], 2)

    def test_missing_inputs_return_two(self) -> None:
        out = self.tmp / "x.json"
        code = plantfood.main(
            [
                "--obb",
                str(self.tmp / "no-such-obb"),
                "--json",
                str(out),
                "--report",
                str(self.tmp / "x.md"),
            ]
        )
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
