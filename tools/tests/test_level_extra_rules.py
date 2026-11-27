"""Tests for tools/contentc/level_extra_rules.py — per-level extra rule parameters.

Two groups:

* `ShippedRulesTests` only reads `native/generated/level_extra_rules.json`, so it runs anywhere
  (a box without the OBB still proves the shipped table is complete and self-consistent).
* `CompileRulesTests` needs the OBB and recompiles: the shipped bytes must equal a fresh
  render, `--check` must be idempotent, and a stale file must be rejected.

The numbers here are the *point* of the artifact — every one was measured against the 460.9
dump (see docs/reviews/2026-11-26-level-extra-rules.md), so a change here means the data or the
口径 changed, not just the formatting.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from contentc import level_extra_rules, worlds  # noqa: E402

SHIPPED = level_extra_rules.DEFAULT_OUT
HAS_OBB = worlds.DEFAULT_OBB.is_dir()
PLAYABILITY = TOOLS.parent / "native" / "generated" / "level_playability.json"

#: 契约表头：多一个少一个都算口径变化。
COUNTS = {
    "levels": 1809,
    "boardGrid": 49,
    "mutators": 21,
    "night": 187,
    "frost": 64,
    "tide": 60,
    "strength": 60,
    "tideBlocks": 90,
    "tideWithChanges": 60,
    "tideWithWaves": 10,
    "tideWithMarker": 80,
    "mutatorObjects": 37,
    "frostEvents": 283,
    "tideChanges": 370,
    "boardGridMaps": 50,
    "boardGridEmptyMaps": 1,
    "nightWithGravestones": 68,
    "nightWithoutSkySunDropper": 185,
    "filesScanned": 2117,
}


def load_shipped() -> dict:
    return json.loads(SHIPPED.read_text(encoding="utf-8"))


class ShippedRulesTests(unittest.TestCase):
    """产物层断言：不需要 OBB。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.table = load_shipped()
        cls.levels = cls.table["levels"]

    def rows_with(self, key: str) -> dict:
        return {lid: row for lid, row in self.levels.items() if key in row}

    def test_top_level_shape(self) -> None:
        self.assertEqual(
            sorted(self.table),
            ["counts", "format", "generated", "generator", "levels", "sources", "unknowns"],
        )
        self.assertEqual(self.table["format"], "pvz2-shuttle/level-extra-rules@1")
        self.assertEqual(self.table["generator"], "level_extra_rules")
        self.assertEqual(self.table["sources"][0].split(" ")[0], "work/obb_packages")

    def test_counts_match_the_contract(self) -> None:
        for key, value in COUNTS.items():
            self.assertEqual(self.table["counts"][key], value, f"counts.{key}")

    def test_counts_are_recomputable_from_the_levels(self) -> None:
        self.assertEqual(len(self.rows_with("boardGrid")), COUNTS["boardGrid"])
        self.assertEqual(len(self.rows_with("mutators")), COUNTS["mutators"])
        self.assertEqual(len(self.rows_with("night")), COUNTS["night"])
        self.assertEqual(len(self.rows_with("frost")), COUNTS["frost"])
        self.assertEqual(len(self.rows_with("strength")), COUNTS["strength"])
        with_changes = [row for row in self.levels.values()
                        if "changes" in (row.get("tide") or {})]
        self.assertEqual(len(with_changes), COUNTS["tide"])
        with_tide = [row for row in self.levels.values() if "tide" in row]
        self.assertEqual(len(with_tide), COUNTS["tideBlocks"])

    def test_board_grid_cells_are_exact(self) -> None:
        """beach_94 的模菌图：24 个 1、21 个 0，逐格可查。"""
        block = self.levels["beach_94"]["boardGrid"]
        self.assertEqual(len(block["maps"]), 1)
        grid = block["maps"][0]
        self.assertEqual(grid["class"], "BoardGridMapProps")
        self.assertEqual(grid["alias"], "MoldColonies")
        self.assertEqual((grid["height"], grid["width"]), (5, 9))
        self.assertEqual(grid["cellCounts"], {"0": 21, "1": 24})
        rows = grid["rows"]
        self.assertEqual(rows[0], [1, 1, 1, 1, 1, 0, 0, 0, 0])
        self.assertEqual(rows[2], [1, 1, 0, 1, 1, 0, 0, 0, 0])
        self.assertEqual(grid["cellsByCode"]["1"][0], [0, 0])
        self.assertEqual(grid["cellsByCode"]["0"][0], [5, 0])
        self.assertIn([2, 2], grid["cellsByCode"]["0"])
        # MoldColonyChallengeProps 指回同一张图
        self.assertEqual(block["moldChallenge"][0]["locations"], "MoldColonies")

    def test_board_grid_edge_maps(self) -> None:
        """一张全 0 的空图、一张包里有两张图的关，都得如实记录。"""
        multi = self.levels["lunarrainbowmarket_49"]["boardGrid"]["maps"]
        self.assertEqual(len(multi), 2)
        self.assertEqual({m["alias"] for m in multi}, {"MoldColonies"})
        empty = self.levels["plantagenet_42"]["boardGrid"]["maps"][0]
        self.assertEqual(empty["cellCounts"], {"0": 45})
        self.assertEqual(empty["cellsByCode"]["1"] if "1" in empty["cellsByCode"] else [], [])
        self.assertEqual(self.table["counts"]["boardGridMultiMapLevels"],
                         ["lunarrainbowmarket_49"])

    def test_mutator_fields_are_flattened_not_interpreted(self) -> None:
        """carnival_51 只挂了一个最大阳光修改器，字段原样铺平（键名小写长头）。"""
        rows = self.levels["carnival_51"]["mutators"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["objclass"], "LevelMutatorMaxSunProps")
        self.assertEqual(row["alias"], "OverrideMaxSun275")
        self.assertEqual(row["maxSunOverride"], 275)
        self.assertEqual(row["difficultyProps"], "LevelModuleDifficultyMaxSun")  # RTID 已归一
        self.assertEqual(row["iconText"], "<500")
        self.assertFalse([k for k in row if k.startswith("#")])

    def test_mutator_tables_stay_structured(self) -> None:
        """beach_21 的 bonuschallenge 表是嵌套结构，铺平但不丢层级。"""
        rows = {row["objclass"]: row for row in self.levels["beach_21"]["mutators"]}
        module = rows["LevelMutatorModuleProperties"]
        self.assertEqual(module["alias"], "LevelMutator")
        self.assertEqual(module["mutatorTables"],
                         ["MutatorPropsRiftConveyor", "LocalChallengeMutator"])
        table_row = rows["LevelMutatorTableProps"]
        self.assertEqual(table_row["tables"][0]["moduleType"], "bonuschallenge")
        self.assertEqual(table_row["tables"][0]["modules"], ["KillZombies1"])

    def test_night_carries_stage_and_gravestone_timing(self) -> None:
        night = self.levels["dark_54"]["night"]
        self.assertEqual(night["flagSource"], "content/levels/dark_54.json extra.night")
        self.assertEqual(night["stageModule"], "DarkDMGStage")
        self.assertEqual(night["stageModuleClass"], "DarkStageProperties")
        self.assertFalse(night["modules"]["hasSkySunDropper"])
        waves = [(g["wave"], g["alias"]) for g in night["gravestones"]]
        self.assertEqual(waves, [(5, "Wave5GravestoneEvent"), (9, "Wave9GravestoneEvent")])
        first = night["gravestones"][0]
        self.assertEqual(first["pool"], [{"type": "gravestone_dark", "count": 5}])
        self.assertEqual(first["positions"][0], {"x": 5, "y": 0})
        self.assertEqual(len(first["positions"]), 5)

    def test_night_sun_dropper_module_is_the_real_night_signal(self) -> None:
        """185/187 夜关没挂 DefaultSunDropper —— 这才是原版「夜里不落阳光」的写法。"""
        night = self.rows_with("night")
        without = [lid for lid, row in night.items()
                   if row["night"]["modules"]["hasSkySunDropper"] is False]
        self.assertEqual(len(without), COUNTS["nightWithoutSkySunDropper"])
        with_sun = sorted(set(night) - set(without))
        self.assertEqual(len(with_sun), 2)
        for lid in with_sun:
            self.assertTrue(night[lid]["night"]["modules"]["hasSkySunDropper"])

    def test_frost_rows_are_numeric_and_waves_parsed(self) -> None:
        frost = self.levels["carnival_90"]["frost"]
        self.assertEqual(frost["class"], "FrostWindWaveActionProps")
        self.assertEqual([e["wave"] for e in frost["events"]], [11, 14])
        self.assertEqual(frost["directions"], {"right": 15})
        for event in frost["events"]:
            self.assertEqual(event["windCount"], len(event["winds"]))
            for wind in event["winds"]:
                self.assertIsInstance(wind["row"], int)  # RTON 里的 '1' 已转成 1
                self.assertEqual(wind["direction"], "right")

    def test_tide_changes_and_derived_strength(self) -> None:
        tide = self.levels["beach_10"]["tide"]
        self.assertEqual(tide["class"], "TidalChangeWaveActionProps")
        self.assertEqual(len(tide["changes"]), 8)
        self.assertEqual({c["type"] for c in tide["changes"]}, {"absolute"})
        self.assertEqual([c["wave"] for c in tide["changes"][:4]], [2, 3, 4, 5])
        strength = self.levels["beach_10"]["strength"]
        expected = round(sum(abs(float(c["amount"])) for c in tide["changes"]), 4)
        self.assertEqual(strength["value"], expected)
        self.assertEqual(strength["value"], 44.0)
        self.assertEqual(strength["derivedFrom"], "sum(|TidalChange.ChangeAmount|)")
        self.assertIn("mechanics.py:851", strength["derivedSource"])

    def test_strength_never_exists_without_changes(self) -> None:
        for lid, row in self.levels.items():
            if "strength" in row:
                self.assertIn("changes", row["tide"], lid)
                self.assertEqual(row["strength"]["changeCount"], len(row["tide"]["changes"]))

    def test_tide_wave_and_marker_tiers_are_separate(self) -> None:
        """10 关只有潜艇段、80 关只有标记位，都不许冒充涨落事件（R06）。"""
        waves = self.rows_with("tide")
        wave_only = [lid for lid, row in self.levels.items()
                     if "waves" in (row.get("tide") or {})
                     and "changes" not in row["tide"]]
        self.assertEqual(len(wave_only), COUNTS["tideWithWaves"])
        self.assertEqual(len(waves), COUNTS["tideBlocks"])
        block = self.levels["beach_39"]["tide"]
        self.assertEqual(block["tideWaveClass"], "TideWaveWaveActionProps")
        self.assertEqual(block["waves"][0]["type"], "right")
        self.assertEqual(block["waves"][0]["duration"], 5.0)
        self.assertNotIn("changes", block)
        marker = self.levels["beach_1"]["tide"]
        self.assertEqual(marker["startingWaveLocation"], 5)
        self.assertNotIn("changes", marker)

    def test_unknowns_list_every_unresolved_thing(self) -> None:
        kinds = {item["kind"]: item for item in self.table["unknowns"]}
        self.assertEqual(len(kinds), 8)
        for kind, item in kinds.items():
            self.assertTrue(item["detail"], kind)
            self.assertTrue(item["probe"], kind)
        self.assertEqual(len(kinds["night-stage-module-unresolved"]["levels"]), 57)
        self.assertEqual(len(kinds["tide-properties-without-tide-events"]["levels"]), 20)
        self.assertEqual(len(kinds["tide-wave-without-tide-events"]["levels"]), 10)
        self.assertEqual(kinds["board-grid-empty-map"]["levels"], ["plantagenet_42"])
        self.assertIn("night-no-dusk-time", kinds)
        self.assertIn("board-grid-code-semantics", kinds)
        self.assertIn("mutator-sheet-classes-unused", kinds)

    def test_generated_stamp_is_content_addressed(self) -> None:
        stamp = self.table["generated"]
        self.assertRegex(stamp, r"^sha256:[0-9a-f]{16}$")
        body = {k: v for k, v in self.table.items() if k != "generated"}
        self.assertEqual(stamp, level_extra_rules.digest(body))

    def test_render_is_compact_lf_and_path_free(self) -> None:
        text = level_extra_rules.render(self.table)
        self.assertTrue(text.endswith("\n"))
        self.assertFalse(text.endswith("\n\n"))
        self.assertNotIn("\r", text)
        self.assertNotIn("OneDrive", text)
        self.assertNotIn("D:\\", text)
        self.assertEqual(text.encode("utf-8"), SHIPPED.read_bytes())
        self.assertNotIn("\n  ", text)  # 紧凑：没有缩进

    def test_blocker_counts_agree_with_level_playability(self) -> None:
        """与 A6 的 blocker 计数逐项对账（同一次 dump、两套代码路径）。"""
        if not PLAYABILITY.exists():
            self.skipTest("level_playability.json 不在，跳过跨表对账")
        play = json.loads(PLAYABILITY.read_text(encoding="utf-8"))["levels"]

        def blocked(kind: str) -> int:
            return sum(1 for row in play.values()
                       if any(m["kind"] == kind for m in row["mechanics"]))

        self.assertEqual(self.table["counts"]["night"], blocked("night"))
        self.assertEqual(self.table["counts"]["boardGrid"], blocked("boardGrid"))
        self.assertEqual(self.table["counts"]["mutators"], blocked("mutators"))
        self.assertEqual(self.table["counts"]["frost"], blocked("events.frost"))
        self.assertEqual(self.table["counts"]["tide"], blocked("events.tide"))
        self.assertEqual(self.table["counts"]["strength"], blocked("events.strength"))


class CompileRulesTests(unittest.TestCase):
    """需要 OBB：重建必须与产物逐字节相同。"""

    @classmethod
    def setUpClass(cls) -> None:
        if not HAS_OBB:
            raise unittest.SkipTest("OBB 不在本机")
        cls.table = level_extra_rules.build(worlds.DEFAULT_OBB, level_extra_rules.DEFAULT_LEVELS)

    def test_shipped_bytes_equal_a_fresh_render(self) -> None:
        self.assertEqual(level_extra_rules.render(self.table), SHIPPED.read_text(encoding="utf-8"))

    def test_check_is_idempotent(self) -> None:
        for _ in range(2):
            self.assertEqual(level_extra_rules.check(self.table, SHIPPED), [])

    def test_stale_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "level_extra_rules.json"
            stale.write_bytes(b'{"format":"stale"}\n')
            problems = level_extra_rules.check(self.table, stale)
            self.assertTrue(any("不一致" in p or "过期" in p for p in problems), problems)

    def test_missing_generated_stamp_is_rejected(self) -> None:
        broken = json.loads(json.dumps(self.table))
        broken["generated"] = "sha256:0000000000000000"
        problems = level_extra_rules.check(broken, SHIPPED)
        self.assertTrue(any("generated" in p for p in problems), problems)

    def test_tampered_strength_is_rejected(self) -> None:
        broken = json.loads(json.dumps(self.table))
        broken["levels"]["beach_10"]["strength"]["value"] = 1.0
        problems = level_extra_rules.check(broken, SHIPPED)
        self.assertTrue(any("beach_10" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
