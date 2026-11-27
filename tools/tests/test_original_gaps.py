"""原版↔客户端字段级差距盘点的契约测试。

运行：
    python -m unittest tools.tests.test_original_gaps -v
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

from tools.contentc import original_gaps  # noqa: E402

OBB = REPO.parent.parent / "work" / "obb_packages"
CONTENT = REPO / "content"
GENERATED = REPO / "native" / "generated" / "original_gaps.json"
REPORT = REPO / "docs" / "reviews" / "2026-11-24-original-gaps.md"

_CACHE: dict[str, tuple[dict, str]] = {}


def _install_scan_cache() -> None:
    """整表扫描约 10 秒；同一个进程里只扫一次，CLI 用例才不会把套件拖成分钟级。"""
    original_scan = original_gaps.scan_pack
    cache: dict[Path, object] = {}

    def cached_scan(obb_dir: Path):
        key = Path(obb_dir)
        if key not in cache:
            cache[key] = original_scan(key)
        return cache[key]

    original_gaps.scan_pack = cached_scan


_install_scan_cache()


def built() -> tuple[dict, str]:
    """整表扫描约 10 秒，整个模块共用一次结果。"""
    if "value" not in _CACHE:
        _CACHE["value"] = original_gaps.build()
    return _CACHE["value"]


def payload() -> dict:
    return built()[0]


class PayloadShapeTest(unittest.TestCase):
    def test_top_level_keys(self):
        self.assertEqual(
            sorted(payload()),
            ["counts", "format", "generated", "packOnlyFields", "sources", "systems", "tables"],
        )

    def test_counts_are_measured(self):
        counts = payload()["counts"]
        self.assertEqual(counts["entities"], len(original_gaps.ENTITY_IDS))
        self.assertEqual(counts["entities"], 12)
        self.assertEqual(counts["sheetsScanned"], 2116)
        self.assertEqual(counts["levelFiles"], 1809)
        self.assertEqual(counts["levelObjects"], 41218)
        self.assertEqual(counts["tables"], len(payload()["tables"]))
        self.assertEqual(counts["systems"], len(payload()["systems"]))
        self.assertEqual(counts["plantTypes"], 339)
        self.assertEqual(counts["plantTypeNames"], 339)
        self.assertEqual(counts["zombieTypes"], 1127)
        self.assertEqual(counts["zombieTypeNames"], 1125)
        self.assertEqual(counts["zombieIdsInContentPack"], 20)
        self.assertEqual(counts["plantJoinedToPack"], 44)
        self.assertEqual(counts["zombieJoinedToPack"], 28)

    def test_every_table_row_has_required_keys(self):
        keys = {"entity", "field", "clientField", "mapped", "packOnly", "clientOnly", "agree", "records", "samples"}
        for row in payload()["tables"]:
            self.assertEqual(set(row), keys, row)
            self.assertIn(row["entity"], set(original_gaps.ENTITY_IDS))
            self.assertLessEqual(len(row["samples"]), 5)
            self.assertGreaterEqual(row["records"], 0)

    def test_every_system_row_has_required_keys(self):
        keys = {"id", "presentInPack", "presentInClient", "evidence", "note"}
        for row in payload()["systems"]:
            self.assertEqual(set(row), keys, row)
            self.assertIn(row["presentInPack"], (True, False, "unverified"))
            self.assertIn(row["presentInClient"], (True, False, "unverified"))
            self.assertIsInstance(row["evidence"], list)
            self.assertTrue(row["note"])


class MeasuredFactsTest(unittest.TestCase):
    """这些数字都是 probe 实测值，改了数据就必须同步改这里（不能改断言迁就实现）。"""

    def setUp(self):
        self.data = payload()
        self.rows = {(row["entity"], row["field"]): row for row in self.data["tables"]}

    def test_plants_cost_matches_pack_cost(self):
        """名册 409 行 = 手工 147 + 262 条 pack 派生行；只有 44 条能按 id 关联回原版。"""
        row = self.rows[("plants", "Cost")]
        self.assertEqual(row["clientField"], "cost")
        self.assertEqual(row["records"], 409)
        self.assertEqual(row["mapped"], 44)
        self.assertEqual(row["clientOnly"], 365)
        self.assertEqual(row["agree"], 42)

    def test_zombies_hitpoints_matches_pack_hitpoints(self):
        row = self.rows[("zombies", "Hitpoints")]
        self.assertEqual(row["clientField"], "hp")
        self.assertEqual(row["records"], 55)
        self.assertEqual(row["mapped"], 28)
        self.assertEqual(row["clientOnly"], 27)
        self.assertEqual(row["agree"], 28)

    def test_shop_products_are_mostly_mapped(self):
        row = self.rows[("shop", "Sku")]
        self.assertEqual(row["records"], 585)
        self.assertEqual(row["mapped"], 565)
        self.assertEqual(row["clientOnly"], 20)

    def test_shop_prices_are_authored_not_copied(self):
        """原版 Price 561/565 是 0，客户端定价是自创数值 —— 对齐数只有 10 是 0 撞 0。"""
        self.assertEqual(payload()["counts"]["shopZeroPrice"], 561)
        self.assertEqual(self.rows[("shop", "Price")]["agree"], 10)
        self.assertEqual(self.rows[("shop", "IsOneTimePurchase")]["clientOnly"], 584)

    def test_worlds_join_leaves_pack_only_worlds(self):
        row = self.rows[("worlds", "m_worldName")]
        self.assertEqual(row["records"], 26)
        self.assertEqual(row["mapped"], 22)
        self.assertEqual(row["packOnly"], 24)
        self.assertEqual(row["clientOnly"], 4)
        self.assertEqual(self.data["counts"]["packWorlds"], 46)
        self.assertEqual(self.data["counts"]["joinedWorldLevelEvents"], 555)
        self.assertEqual(self.data["counts"]["joinedWorldClientLevels"], 1432)

    def test_projectiles_have_no_name_overlap(self):
        """名册扩到 409 后多了 139 个弹道名，但真正能对上原版 ClassName 的只有 2 个。"""
        row = self.rows[("projectiles", "ClassName")]
        self.assertEqual(row["records"], 150)
        self.assertEqual(row["mapped"], 2)
        self.assertEqual(row["clientOnly"], 148)
        self.assertEqual(row["packOnly"], 129)

    def test_stars_entries_are_counted(self):
        row = self.rows[("stars", "Challenges")]
        self.assertEqual(row["records"], 1809)
        self.assertEqual(row["mapped"], 950)
        self.assertEqual(self.data["counts"]["starEntries"], 5427)
        self.assertEqual(row["clientOnly"], 1809 - row["mapped"])

    def test_levels_join_by_package(self):
        row = self.rows[("levels", "StartingSun")]
        self.assertEqual(row["records"], 1809)
        self.assertEqual(row["mapped"], 377)
        self.assertGreaterEqual(row["mapped"], 300)

    def test_levels_nested_field_is_read_through_extra(self):
        row = self.rows[("levels", "LevelNumber")]
        self.assertEqual(row["clientField"], "extra.level_number")
        self.assertEqual(row["mapped"], 1777)
        self.assertEqual(row["clientOnly"], 32)

    def test_fusion_pairs_come_from_the_config_field(self):
        for field in ("ResultPlant", "SourcePlant", "FusionPlant"):
            row = self.rows[("fusion", field)]
            self.assertEqual(row["records"], 85, field)
            self.assertEqual(row["mapped"], 85, field)
            self.assertEqual(row["packOnly"], 0, field)
            self.assertEqual(row["clientOnly"], 0, field)

    def test_counts_split_table_outcomes(self):
        counts = self.data["counts"]
        for key in ("mapped", "packOnly", "clientOnly", "agree"):
            self.assertGreater(counts[key], 0, key)
        self.assertEqual(counts["mapped"], sum(row["mapped"] for row in self.data["tables"]))
        self.assertEqual(counts["packOnly"], sum(row["packOnly"] for row in self.data["tables"]))
        self.assertEqual(counts["clientOnly"], sum(row["clientOnly"] for row in self.data["tables"]))
        self.assertEqual(counts["tables"], 46)

    def test_systems_capture_authored_only_and_pack_only(self):
        systems = {row["id"]: row for row in self.data["systems"]}
        pack_only = {
            "plantfood_drop",
            "plantfood_purchase",
            "level_rewards",
            "achievements_quests",
            "daily_season",
            "sound_events",
            "mower_config",
        }
        for system_id in pack_only:
            self.assertIs(systems[system_id]["presentInPack"], True, system_id)
            self.assertIs(systems[system_id]["presentInClient"], False, system_id)
        for system_id in ("shop_products", "almanac_entries", "zen_garden", "star_challenges", "seeds_and_vases", "key_drops"):
            self.assertIs(systems[system_id]["presentInClient"], True, system_id)
        self.assertEqual(self.data["counts"]["systemsPackOnly"], 7)
        self.assertEqual(self.data["counts"]["systemsUnverified"], 0)
        for row in self.data["systems"]:
            self.assertTrue(row["evidence"], row["id"])

    def test_pack_only_field_samples_are_sorted_by_count(self):
        fields = self.data["packOnlyFields"]
        self.assertTrue(fields)
        counts = [item["count"] for item in fields]
        self.assertEqual(counts, sorted(counts, reverse=True))
        self.assertEqual(fields[0]["field"], "Modules")
        self.assertEqual(fields[0]["count"], 1806)
        for item in fields:
            self.assertFalse(item["field"].startswith("_"), item)

    def test_pack_only_top_is_a_prefix_of_the_full_list(self):
        self.assertEqual(
            self.data["counts"]["packOnlyFieldTop"],
            self.data["packOnlyFields"][: len(self.data["counts"]["packOnlyFieldTop"])],
        )


class RenderTest(unittest.TestCase):
    def test_json_is_deterministic(self):
        first, _ = original_gaps.build()
        second, _ = original_gaps.build()
        self.assertEqual(original_gaps.render_json(first), original_gaps.render_json(second))

    def test_report_mentions_the_corrections_section(self):
        data, _ = built()
        text = original_gaps.render_report(data)
        for heading in ("## 二、字段级差距总表", "## 五、子系统清单", "## 六、文档更正", "## 七、复现"):
            self.assertIn(heading, text)
        self.assertIn("原版有值、客户端无字段", text)
        self.assertIn("packOnlyFields", text)
        self.assertIn("55", text)
        self.assertNotIn("\\\\", text)

    def test_report_numbers_follow_the_payload(self):
        data, _ = built()
        text = original_gaps.render_report(data)
        counts = data["counts"]
        self.assertIn(str(counts["mapped"]), text)
        self.assertIn(str(counts["packOnly"]), text)
        self.assertIn(str(counts["clientOnly"]), text)
        self.assertIn(str(counts["systemsPackOnly"]), text)
        self.assertIn("零重叠", text)


class CliTest(unittest.TestCase):
    def test_check_accepts_committed_artifacts(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(original_gaps.main(["--check"]), 0)

    def test_check_detects_tampering(self):
        tmp = Path(tempfile.mkdtemp(prefix="oggaps-"))
        try:
            data, _ = built()
            target = tmp / "original_gaps.json"
            target.write_bytes(original_gaps.render_json(data).encode("utf-8"))
            broken = json.loads(target.read_text(encoding="utf-8"))
            broken["counts"]["entities"] = 999
            target.write_text(json.dumps(broken, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            report_path = tmp / "report.md"
            report_path.write_bytes(original_gaps.render_report(data).encode("utf-8"))
            with contextlib.redirect_stdout(io.StringIO()):
                code = original_gaps.main(["--check", "--json", str(target), "--report", str(report_path)])
            self.assertEqual(code, 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_check_detects_stale_report(self):
        tmp = Path(tempfile.mkdtemp(prefix="oggaps-stale-"))
        try:
            data, report = built()
            target = tmp / "original_gaps.json"
            target.write_bytes(original_gaps.render_json(data).encode("utf-8"))
            report_path = tmp / "report.md"
            report_path.write_text(report + "\nstale\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                code = original_gaps.main(["--check", "--json", str(target), "--report", str(report_path)])
            self.assertEqual(code, 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_obb_exits_two(self):
        tmp = Path(tempfile.mkdtemp(prefix="oggaps-miss-"))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                code = original_gaps.main(["--obb", str(tmp / "nope"), "-n"])
            self.assertEqual(code, 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_dry_run_writes_nothing(self):
        tmp = Path(tempfile.mkdtemp(prefix="oggaps-dry-"))
        try:
            out = tmp / "x.json"
            rep = tmp / "x.md"
            with contextlib.redirect_stdout(io.StringIO()):
                code = original_gaps.main(["--json", str(out), "--report", str(rep), "-n"])
            self.assertEqual(code, 0)
            self.assertFalse(out.exists())
            self.assertFalse(rep.exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_committed_artifacts_match_rendered_bytes(self):
        data, _ = built()
        self.assertEqual(GENERATED.read_bytes(), original_gaps.render_json(data).encode("utf-8"))
        self.assertEqual(REPORT.read_bytes(), original_gaps.render_report(data).encode("utf-8"))


class MappingInputTest(unittest.TestCase):
    def test_mapping_csv_gives_exact_plants_and_zombies(self):
        pairs = original_gaps.load_mapping(REPO / "native" / "generated" / "id_mapping.csv")
        self.assertEqual(len(pairs[("plant", "peashooter")]), 1)
        self.assertEqual(pairs[("plant", "peashooter")][0], "peashooter")
        self.assertEqual(pairs[("zombie", "kongfu")][0], "kongfu")


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
