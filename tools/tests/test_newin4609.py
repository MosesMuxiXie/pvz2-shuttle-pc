"""Tests for tools/contentc/newin4609.py — 460.9 新增的三块数据（RlConfig / 关卡开关 / 主题事件）。

两组：

* `ShippedPatchTests` 只读 `native/generated/patch_460_9.json`，没有 OBB 的机器也能跑
  （保证交付物本身是完整的、自洽的）。
* `CompilePatchTests` 需要 OBB，重新编译一遍并逐字节比对，证明盘上的产物就是当前
  代码对当前包树的输出。
"""

from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from contentc import newin4609, worlds  # noqa: E402

SHIPPED = newin4609.DEFAULT_OUT
HAS_OBB = worlds.DEFAULT_OBB.is_dir()

TOP_LEVEL_KEYS = ["counts", "format", "levelFlags", "rlConfig", "source", "thymeEvents",
                  "unknowns"]

#: RlConfig 的 17 个原字段实测值（逐字段断言，改名/丢字段都会红）。
RL_SCALARS = {
    "Version": 1,
    "LevelCount": 12,
    "ChoiceCount": 3,
    "StartingSunBase": 50,
    "StartingSunPerLevel": 25,
    "StartingSunMax": 500,
    "ZombieHealthPctPerLevel": 0.18,
    "ZombieDamagePctPerLevel": 0.1,
    "ZombieSpeedPctPerLevel": 0.03,
    "EliteChance": 0.0,
    "EliteEvery": 4,
    "EliteHealthBonusPct": 0.5,
    "EliteDamageBonusPct": 0.25,
    "FinalLevelIsElite": 1,
    "DefaultOwnedFactionWeight": 2.0,
}


def load_shipped() -> dict:
    with SHIPPED.open(encoding="utf-8") as handle:
        return json.load(handle)


class ShippedPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = load_shipped()
        cls.counts = cls.table["counts"]
        cls.flags = cls.table["levelFlags"]
        cls.by_level = {row["levelId"]: row for row in cls.flags}
        cls.events = cls.table["thymeEvents"]
        cls.by_event = {row["uniqueId"]: row for row in cls.events}

    # ---------------------------------------------------------------- shape

    def test_format_source_and_top_level_keys(self) -> None:
        self.assertEqual(self.table["format"], newin4609.FORMAT)
        self.assertEqual(sorted(self.table), TOP_LEVEL_KEYS)
        source = self.table["source"]
        self.assertEqual(source["generated"], newin4609.GENERATED)
        self.assertEqual(source["flagKey"], "SuppressFlagZombie")
        # 产物里不许写绝对路径：换机器 --check 不该因为路径变红。
        for value in source.values():
            if isinstance(value, str):
                self.assertNotIn(":\\", value, "source 里出现了 Windows 绝对路径")

    def test_counts_agree_with_rows(self) -> None:
        counts = self.counts
        self.assertEqual(counts["levelFlags"], len(self.flags))
        self.assertEqual(counts["thymeEvents"], len(self.events))
        self.assertEqual(counts["unknowns"], len(self.table["unknowns"]))
        # true / false / null 三分支必须把 271 行铺满。
        self.assertEqual(
            counts["levelFlagsTrue"] + counts["levelFlagsFalse"] + counts["levelFlagsNull"],
            len(self.flags))
        self.assertEqual(counts["thymeEventLevelRefs"],
                         sum(len(row["levels"]) for row in self.events))
        self.assertEqual(counts["thymeEventsNew"],
                         sum(1 for row in self.events if row["isNew"]))
        self.assertEqual(counts["packagesScanned"], 2116)
        self.assertEqual(counts["clientLevels"], 1809)

    # ------------------------------------------------------------ rlConfig

    def test_rl_config_scalar_fields_one_by_one(self) -> None:
        rl = self.table["rlConfig"]
        self.assertIsNotNone(rl, "RlConfig 缺失：460.9 里它是 objects[495]")
        for field, expected in RL_SCALARS.items():
            with self.subTest(field=field):
                self.assertEqual(rl[field], expected)
        self.assertEqual(len(rl["TemplateLevelNames"]), 18)
        self.assertEqual(rl["TemplateLevelNames"][:4], ["Steam1", "Steam29", "Kongfu1",
                                                        "Kongfu13"])
        self.assertEqual(len(rl["ZombiePool"]), 112)
        self.assertEqual(rl["ZombiePool"][:2], ["beach", "beach_armor1"])

    def test_rl_config_keeps_raw_and_provenance(self) -> None:
        rl = self.table["rlConfig"]
        self.assertEqual(rl["package"], "pkg_0234")
        self.assertEqual(rl["file"], "pkg_0234_DisableSkipLevelModuleProperties.json")
        self.assertEqual(rl["objectIndex"], 495)
        self.assertEqual(rl["objclass"], "RlConfig")
        self.assertIn("RlConfig", rl["aliases"])
        raw = rl["raw"]
        self.assertIsInstance(raw, dict)
        # 铺平字段与 raw 必须一一对应：不许出现"抄错一个数"。
        for field in RL_SCALARS:
            with self.subTest(field=field):
                self.assertEqual(rl[field], raw[field])
        self.assertEqual(set(raw), set(RL_SCALARS) | {"TemplateLevelNames", "ZombiePool"})
        self.assertEqual(len(raw), len(newin4609.RL_FIELDS), "RlConfig 字段数变了")

    # ---------------------------------------------------------- levelFlags

    def test_level_flags_cover_271_levels(self) -> None:
        self.assertEqual(len(self.flags), 271)
        self.assertEqual(len(self.by_level), 271, "客户端 levelId 必须唯一")
        self.assertEqual(self.counts["levelFlagsTrue"], 215)
        self.assertEqual(self.counts["levelFlagsFalse"], 56)
        self.assertEqual(self.counts["levelFlagsNull"], 0)
        holders = {row["holder"] for row in self.flags}
        self.assertEqual(holders, {"WaveManagerProperties"})
        for row in self.flags:
            self.assertIsInstance(row["suppressFlagZombie"], bool)
            self.assertRegex(row["package"], r"^pkg_\d{4}$")

    def test_pkg_0416_row_is_the_flag_460_9_added(self) -> None:
        row = self.by_level.get("memorytour_2")
        self.assertIsNotNone(row, "pkg_0416 的客户端 id 没映射上")
        self.assertEqual(row["package"], "pkg_0416")
        self.assertEqual(row["objectIndex"], 8)
        self.assertEqual(row["levelNumber"], 8)
        self.assertEqual(row["stageModule"], "RTID(HeroesStage@LevelModules)")
        self.assertEqual(row["levelName"], "[ELEMENT_LEVEL_NAME]")
        self.assertIs(row["suppressFlagZombie"], True)
        # 该键不是 460.9 独有：全库 271 关都有（215 true / 56 false 已经断言过）。
        self.assertEqual(len({row["package"] for row in self.flags}), 271)

    def test_level_flags_are_sorted_by_client_id(self) -> None:
        ids = [row["levelId"] for row in self.flags]
        self.assertEqual(ids, sorted(ids))

    # --------------------------------------------------------- thymeEvents

    def test_thyme_events_are_thirty_with_three_new(self) -> None:
        self.assertEqual(len(self.events), 30)
        ids = sorted(self.by_event)
        self.assertEqual(ids, [i for i in range(1, 32) if i != 23],
                         "UniqueID 集合应为 1..31 去掉 23")
        new = sorted(row["uniqueId"] for row in self.events if row["isNew"])
        self.assertEqual(new, [29, 30, 31])
        self.assertEqual(self.counts["newThymeUniqueIds"], [29, 30, 31])
        for unique_id in (29, 30, 31):
            row = self.by_event[unique_id]
            self.assertEqual(row["name"], "[EVENT_TIMESPACEECHOES_BACK]")
            self.assertEqual(len(row["levels"]), 12)
        self.assertEqual(self.by_event[29]["levels"][0], "timespaceechoes_0003_1")
        self.assertEqual(self.by_event[30]["levels"][0], "timespaceechoes_0004_1")
        self.assertEqual(self.by_event[31]["levels"][0], "timespaceechoes_0009_1")

    def test_event_name_alone_cannot_identify_the_new_ones(self) -> None:
        """新增判定只能靠 UniqueID：同名事件在旧排期里早就有。"""
        same_name = [row for row in self.events
                     if row["name"] == "[EVENT_TIMESPACEECHOES_BACK]"]
        self.assertEqual(len(same_name), 6, "同名事件应多于新增的 3 条")
        older = sorted(row["uniqueId"] for row in same_name if not row["isNew"])
        self.assertEqual(older, [26, 27, 28])

    def test_thyme_events_carry_levels_dates_and_raw(self) -> None:
        for row in self.events:
            with self.subTest(uniqueId=row["uniqueId"]):
                self.assertEqual(row["package"], "pkg_2101")
                self.assertIsInstance(row["levels"], list)
                self.assertIsInstance(row["raw"], dict)
                self.assertEqual(row["raw"]["UniqueID"], row["uniqueId"])
                self.assertEqual(row["raw"]["EventName"], row["name"])
                self.assertIsInstance(row["startDate"], int)
                self.assertRegex(row["startUtc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
                # 原版有一条**零长排期**（UniqueID 2，起止同为 1678032000），
                # 所以这里只能断言"不晚于"，不能用严格小于。
                self.assertLessEqual(row["startDate"], row["endDate"])

    def test_zero_length_and_disabled_events_are_passed_through(self) -> None:
        """两条数据事实：UniqueID 2 是零长排期，UniqueID 1 是 Disabled。都原样透传。"""
        zero = sorted(row["uniqueId"] for row in self.events
                      if row["startDate"] == row["endDate"])
        self.assertEqual(zero, [2])
        disabled = sorted(row["uniqueId"] for row in self.events if row["disabled"] is True)
        self.assertEqual(disabled, [1])

    # --------------------------------------------------------- unknowns

    def test_unknowns_empty_and_rules_are_enforced(self) -> None:
        self.assertEqual(self.table["unknowns"], [],
                         "271 关全部映射到客户端 id，不该有未知项")
        broken = copy.deepcopy(self.table)
        broken["levelFlags"][0]["levelId"] = None
        problems = newin4609.validate(broken)
        self.assertTrue(any("unknowns" in problem for problem in problems), problems)

    def test_validate_rejects_non_boolean_flag(self) -> None:
        broken = copy.deepcopy(self.table)
        broken["levelFlags"][0]["suppressFlagZombie"] = "true"
        problems = newin4609.validate(broken)
        self.assertTrue(any("suppressFlagZombie" in problem for problem in problems),
                        problems)

    # --------------------------------------------------------- product io

    def test_render_is_deterministic_and_lf_only(self) -> None:
        first = newin4609.render(self.table)
        second = newin4609.render(load_shipped())
        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        self.assertNotIn("\r", first)
        self.assertEqual(first.count("\n"), 1, "产物应为单行紧凑 JSON + 末尾换行")
        self.assertEqual(SHIPPED.read_text(encoding="utf-8"), first,
                         "盘上产物与当前渲染不一致")

    def test_check_is_red_on_stale_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "patch.json"
            stale.write_bytes(newin4609.render(self.table).encode("utf-8"))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(newin4609.check(self.table, stale), 0)
            stale.write_bytes(newin4609.render(self.table).replace(
                '"EliteEvery":4', '"EliteEvery":5').encode("utf-8"))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(newin4609.check(self.table, stale), 1)
            missing = Path(tmp) / "nope.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(newin4609.check(self.table, missing), 1)


@unittest.skipUnless(HAS_OBB, "需要 OBB 包目录（PVZ2_OBB_DIR 或 work/obb_packages）")
class CompilePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = newin4609.compile_data()
        cls.table = load_shipped()

    def test_recompile_matches_the_shipped_bytes(self) -> None:
        self.assertEqual(newin4609.render(self.data), SHIPPED.read_text(encoding="utf-8"))

    def test_recompile_reports_the_same_counts(self) -> None:
        self.assertEqual(self.data["counts"], self.table["counts"])

    def test_missing_levels_dir_becomes_unknowns_not_guesses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = newin4609.compile_data(worlds.DEFAULT_OBB, Path(tmp))
        kinds = {row["kind"] for row in data["unknowns"]}
        self.assertIn("levels-index-empty", kinds)
        self.assertIn("level-flag-unmapped", kinds)
        self.assertTrue(all(row["levelId"] is None for row in data["levelFlags"]))
        self.assertEqual(data["counts"]["levelFlagsMapped"], 0)
        self.assertEqual(data["counts"]["levelFlags"], 271)


if __name__ == "__main__":
    unittest.main()
