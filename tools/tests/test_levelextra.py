"""S7.0 关卡模块清点的回归测试。

运行::

    python -m unittest tools.tests.test_levelextra -v

计数一律取实测（1809 关、14 个 extra 键、boss 71、vasebreaker 47、minecarts 190、rail 192；
t52 起三个玩法标记由 `tools/obb_build_content_v2.py` 从原版表派生）。
若原版表或关卡数据更新导致数字变化，先跑 ``python tools/contentc/levelextra.py -n``
拿到新值，再同步这里的常量与注释。
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
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.contentc import levelextra as le  # noqa: E402

OBB = Path(
    os.environ.get("PVZ2_OBB_DIR") or (REPO.parent.parent / "work" / "obb_packages")
)
LEVELS = REPO / "content" / "levels"

#: 原版关卡定义份数 == 客户端关卡数（实测一一对应）。
TOTAL_LEVELS = 1809
#: extra 键总数：7 个模块键 + 1 个派生键（night）+ 6 个元数据键 + boss_zombie/special
#: （t64 起多了 suppressFlagZombie，挂在 WaveManagerProperties 上）。
TOTAL_KEYS = 15
#: 两侧都有的僵王战关卡数。
BOSS_LEVELS = 71
#: 原版 VaseBreaker 系 47 关；t52 起客户端也是 47 关（派生值）。
VASE_ORIGINAL = 47
VASE_CLIENT = 47
#: 原版 Rails/CowboyRails/Railcart 模块名系 185 关；客户端 `minecarts` 190 关（对象级证据派生）。
RAIL_ORIGINAL = 185
MINE_CLIENT = 190
RAIL_CLIENT = 192
#: 客户端标了 minecarts、原版 Modules 里却没有 rail 模块的关卡（对象级证据成立，属模块名口径漏判）。
RAIL_CLIENT_ONLY = [
    "beach_10",
    "beach_11",
    "beach_16",
    "beach_8",
    "beach_9",
    "cowboy_20",
    "egypt_19",
    "future_54",
    "kongfu_44",
    "memorytour_4",
    "plantagenet_40",
    "plantagenet_45",
]
#: 砸罐子两侧一致，没有原版独有的关卡（t52 已补齐 pirate_41 / plantagenet_18）。
VASE_ORIGINAL_ONLY: list[str] = []


def run_mapping(out_dir: Path, extra: list[str] | None = None) -> int:
    """跑一次 CLI；stdout 静音，只看退出码与产物。"""
    with contextlib.redirect_stdout(io.StringIO()):
        return le.main(
            [
                "--levels",
                str(LEVELS),
                "--obb",
                str(OBB),
                "--json",
                str(out_dir / "level_modules.json"),
                "--report",
                str(out_dir / "report.md"),
                *(extra or []),
            ]
        )


class InventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inv = le.build(LEVELS, OBB)
        cls.by_key = {row.key: row for row in cls.inv.keys}
        cls.cross = {item.name: item for item in cls.inv.cross}

    def test_level_and_key_counts(self) -> None:
        self.assertEqual(self.inv.levels, TOTAL_LEVELS)
        self.assertEqual(self.inv.totals["levelsWithExtra"], TOTAL_LEVELS)
        self.assertEqual(len(self.inv.keys), TOTAL_KEYS)
        # 本次运行没有对不上原版的键：unknown 必须为 0，否则报告会多出探针。
        self.assertEqual(self.inv.totals["unknownKeys"], 0)
        self.assertEqual(self.inv.totals["dataKeys"], 2)
        self.assertEqual(self.inv.totals["flagOnlyKeys"], 7)
        self.assertEqual(self.inv.totals["metaKeys"], 6)

    def test_known_key_counts(self) -> None:
        expected = {
            "boss": BOSS_LEVELS,
            "boss_zombie": BOSS_LEVELS,
            "vasebreaker": VASE_CLIENT,
            "special": 45,
            "minecarts": MINE_CLIENT,
            "rail": RAIL_CLIENT,
            "night": TOTAL_LEVELS,
            "stage": TOTAL_LEVELS,
            "source": TOTAL_LEVELS,
            "package": TOTAL_LEVELS,
            "name_key": TOTAL_LEVELS,
            "level_number": TOTAL_LEVELS,
            "wave_count": TOTAL_LEVELS,
            "original_waves": TOTAL_LEVELS,
        }
        for key, count in expected.items():
            with self.subTest(key=key):
                self.assertIn(key, self.by_key)
                self.assertEqual(self.by_key[key].count, count)

    def test_minecart_values_are_rows_only(self) -> None:
        row = self.by_key["minecarts"]
        # 取值是行号数组（如 [0,2]、[1,2,3]）：只有行号，没有列号/速度/长度。
        for sample in row.samples:
            rows = json.loads(sample)
            self.assertIsInstance(rows, list)
            self.assertTrue(all(isinstance(value, int) and 0 <= value <= 4 for value in rows), sample)
            self.assertEqual(rows, sorted(set(rows)), sample)
        self.assertIn("[0,2]", row.samples)
        self.assertNotEqual(row.samples, ["[0,2,4]"])
        self.assertEqual(row.status, "flag_only")

    def test_cross_check_matches_original(self) -> None:
        boss = self.cross["boss"]
        self.assertEqual((boss.original, boss.client, boss.both), (BOSS_LEVELS, BOSS_LEVELS, BOSS_LEVELS))
        self.assertEqual(boss.original_only, [])
        self.assertEqual(boss.client_only, [])

        vase = self.cross["vasebreaker"]
        self.assertEqual((vase.original, vase.client, vase.both), (VASE_ORIGINAL, VASE_CLIENT, VASE_CLIENT))
        self.assertEqual(vase.original_only, VASE_ORIGINAL_ONLY)
        self.assertEqual(vase.client_only, [])

        rails = self.cross["minecarts"]
        self.assertEqual(
            (rails.original, rails.client, rails.both), (RAIL_ORIGINAL, MINE_CLIENT, 178)
        )
        self.assertEqual(rails.client_only, sorted(RAIL_CLIENT_ONLY))
        self.assertEqual(len(rails.original_only), RAIL_ORIGINAL - 178)

    def test_levels_with_truncates_long_lists(self) -> None:
        levels_with = {item.key: item for item in self.inv.levels_with}
        self.assertNotIn("package", levels_with)  # 元数据键不进 levelsWith
        boss = levels_with["boss"]
        self.assertEqual(boss.count, BOSS_LEVELS)
        self.assertEqual(len(boss.sample), le.LEVEL_SAMPLE_LIMIT)
        self.assertTrue(boss.truncated)
        night = levels_with["night"]
        self.assertEqual(night.count, TOTAL_LEVELS)
        self.assertTrue(night.truncated)
        self.assertEqual(len(night.sample), le.LEVEL_SAMPLE_LIMIT)

    def test_original_modules_inventory(self) -> None:
        self.assertEqual(len(self.inv.modules), 385)
        self.assertEqual(self.inv.modules["ZombossBattle"]["levels"], BOSS_LEVELS)
        self.assertEqual(self.inv.modules["ZombossBattle"]["clientKey"], "boss")
        self.assertEqual(self.inv.modules["VaseBreakerArcade"]["clientKey"], "vasebreaker")
        self.assertEqual(self.inv.modules["Rails"]["clientKey"], "minecarts")
        self.assertIsNone(self.inv.modules["ChallengeModule"]["clientKey"])
        self.assertGreater(self.inv.modules["ChallengeModule"]["levels"], 900)
        # 原版有 4 关没有 Modules 列表，S7 不能假设每关都有模块表。
        self.assertEqual(self.inv.no_modules, ["egypt_50", "frontyard_86", "frontyard_87", "frontyard_88"])

    def test_unknown_keys_are_kept(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            levels = Path(raw) / "levels"
            levels.mkdir()
            for name, extra in (
                ("zz_1", {"boss": True, "mystery_module": [1, 2]}),
                ("zz_2", {"boss": False}),
            ):
                (levels / f"{name}.json").write_text(
                    json.dumps({"id": name, "world": "w", "extra": {"package": "pkg_0325", **extra}}),
                    encoding="utf-8",
                )
            inv = le.build(levels, OBB)
        self.assertEqual(inv.levels, 2)
        by_key = {row.key: row for row in inv.keys}
        self.assertIn("mystery_module", by_key)
        self.assertEqual(by_key["mystery_module"].status, "unknown")
        self.assertEqual(by_key["mystery_module"].kind, "unknown")
        self.assertIn("探针", by_key["mystery_module"].note)
        self.assertEqual(inv.totals["unknownKeys"], 1)
        payload = json.loads(le.render_json(inv))
        self.assertIn("mystery_module", payload["keys"])
        self.assertEqual(payload["keys"]["mystery_module"]["count"], 1)


class CliTest(unittest.TestCase):
    def test_generation_is_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            first = Path(raw) / "a"
            second = Path(raw) / "b"
            self.assertEqual(run_mapping(first), 0)
            self.assertEqual(run_mapping(second), 0)
            for name in ("level_modules.json", "report.md"):
                self.assertEqual(
                    (first / name).read_bytes(),
                    (second / name).read_bytes(),
                    f"{name} 两次生成不一致",
                )
            text = (first / "level_modules.json").read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            payload = json.loads(text)
            for key in ("format", "generated", "levels", "totals", "keys", "levelsWith", "crossCheck", "modules"):
                self.assertIn(key, payload)
            self.assertEqual(payload["format"], le.FORMAT)
            self.assertEqual(payload["generated"], le.MARKER)
            self.assertEqual(payload["levels"], TOTAL_LEVELS)
            self.assertEqual(payload["crossCheck"]["boss"]["both"], BOSS_LEVELS)

    def test_check_accepts_fresh_and_rejects_stale(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            self.assertEqual(run_mapping(out), 0)
            self.assertEqual(run_mapping(out, ["--check"]), 0)
            report = out / "report.md"
            report.write_text(report.read_text(encoding="utf-8") + "\n多余\n", encoding="utf-8")
            buffer = io.StringIO()
            with contextlib.redirect_stderr(buffer):
                self.assertEqual(run_mapping(out, ["--check"]), 2)
            self.assertIn("需要重新生成", buffer.getvalue())

    def test_check_reports_missing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            buffer = io.StringIO()
            with contextlib.redirect_stderr(buffer):
                self.assertEqual(run_mapping(Path(raw), ["--check"]), 2)
            self.assertIn("缺失", buffer.getvalue())

    def test_missing_inputs_exit_2(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            self.assertEqual(
                le.main(
                    ["--levels", str(out / "nope"), "--obb", str(OBB), "--json", str(out / "a.json"), "--report", str(out / "a.md")]
                ),
                2,
            )
            self.assertEqual(
                le.main(
                    ["--levels", str(LEVELS), "--obb", str(out / "nope"), "--json", str(out / "b.json"), "--report", str(out / "b.md")]
                ),
                2,
            )

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                self.assertEqual(le.main(["--json", str(out / "x.json"), "--report", str(out / "x.md"), "-n"]), 0)
            self.assertFalse((out / "x.json").exists())
            self.assertIn("levels=1809", buffer.getvalue())

    def test_report_has_three_sections_and_samples(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw)
            self.assertEqual(run_mapping(out), 0)
            text = (out / "report.md").read_text(encoding="utf-8")
        for heading in (
            "## 结论摘要",
            "## 一、extra 键总表",
            "## 二、有数据可直接驱动",
            "## 三、只有标记无参数",
            "## 四、原版有但客户端没导出",
            "## 五、unknown 与探针",
            "## 六、逐键明细",
        ):
            self.assertIn(heading, text)
        for token in (
            "beach_10",
            "plantagenet_45",
            "egypt_50",
            "ZombossBattleModuleProperties",
            "RailcartProperties",
            "VaseBreakerPresetProperties",
            "1809",
        ):
            self.assertIn(token, text)


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
