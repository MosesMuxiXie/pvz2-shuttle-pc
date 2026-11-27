"""Tests for tools/contentc/minigame_rules.py — per-kind startup parameters.

Two groups:

* `ShippedRulesTests` only reads `native/generated/minigame_rules.json`, so it runs anywhere
  (a box without the OBB still proves the shipped table is complete and self-consistent).
* `CompileRulesTests` needs the OBB and recompiles: the shipped bytes must equal a fresh
  render, `--check` must be idempotent, and a stale file must be rejected.

The numbers here are the *point* of the artifact — every one of them was measured against the
460.9 dump (see docs/reviews/2026-11-26-minigame-rules.md), so a change here means the data
or the口径 changed, not just the formatting.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from contentc import minigame_rules, worlds  # noqa: E402

SHIPPED = minigame_rules.DEFAULT_OUT
HAS_OBB = worlds.DEFAULT_OBB.is_dir()

EXPECTED_LEVELS = {
    "vasebreaker": 47,
    "rail": 196,
    "laststand": 73,
    "beghouled": 11,
    "whackazombie": 1,
    "joust": 4,
    "bowling": 15,
    "column": 8,
    "cannon": 8,
    "invisighoul": 8,
    "cowboy": 10,
    "bigtrouble": 6,
    "camel": 2,
    "deathexplosion": 17,
    "sproutplanting": 2,
    "seeingstars": 3,
    "bonuschallenge": 2,
    "conveyor": 332,
    "tide": 77,
    "protecttheplant": 197,
}


def load() -> dict:
    with SHIPPED.open(encoding="utf-8") as handle:
        return json.load(handle)


class ShippedRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.table = load()
        self.kinds = self.table["kinds"]

    def test_top_level_shape(self) -> None:
        for key in (
            "format",
            "generated",
            "sources",
            "criteria",
            "counts",
            "playableKinds",
            "blockedKinds",
            "absentKinds",
            "sentinels",
            "kinds",
        ):
            self.assertIn(key, self.table)
        self.assertEqual(self.table["format"], "pvz2-shuttle/minigame-rules@1")
        self.assertEqual(self.table["generated"], "2026-11-26")
        # 来源必须能复算：路径 + 字节 + sha256 都在
        for name in ("minigames", "mechanics"):
            source = self.table["sources"][name]
            self.assertTrue(source["path"].endswith(".json"))
            self.assertGreater(source["bytes"], 0)
            self.assertEqual(len(source["sha256"]), 64)

    def test_counts_are_internally_consistent(self) -> None:
        counts = self.table["counts"]
        self.assertEqual(counts["kinds"], 20)
        self.assertEqual(counts["kinds"], len(self.kinds))
        self.assertEqual(counts["playable"] + counts["notPlayable"], counts["kinds"])
        self.assertEqual(counts["playable"], len(self.table["playableKinds"]))
        self.assertEqual(counts["notPlayable"], len(self.table["blockedKinds"]))
        self.assertEqual(sum(EXPECTED_LEVELS.values()), 1019)  # kind 出现次数，与 minigames.json 同口径
        self.assertEqual(self.table["counts"]["levels"], 813)

    def test_every_kind_reports_its_level_count(self) -> None:
        for kind, expected in EXPECTED_LEVELS.items():
            with self.subTest(kind=kind):
                self.assertEqual(self.kinds[kind]["levels"], expected)

    def test_every_kind_has_the_contract_keys(self) -> None:
        for kind, row in self.kinds.items():
            with self.subTest(kind=kind):
                for key in (
                    "levels",
                    "levelsWithAnchor",
                    "levelsWithNonEmptyAnchor",
                    "playable",
                    "anchorClasses",
                    "params",
                    "missing",
                    "missingOptional",
                    "levelsIncomplete",
                    "evidence",
                    "sentinels",
                ):
                    self.assertIn(key, row)
                self.assertTrue(row["anchorClasses"], kind)
                self.assertTrue(row["evidence"], kind)
                for name, param in row["params"].items():
                    with self.subTest(kind=kind, param=name):
                        self.assertIn("critical", param)
                        self.assertIn("coverage", param)
                        self.assertIn("source", param)
                        self.assertLessEqual(param["coverage"], row["levels"])

    def test_kinds_follow_the_registry_order(self) -> None:
        # JSON 按键排序，所以 kinds 是字母序；注册表顺序单独存一份 kindOrder
        self.assertEqual(self.table["kindOrder"], list(minigame_rules.KIND_ORDER))
        self.assertEqual(sorted(self.kinds), sorted(minigame_rules.KIND_ORDER))

    def test_playable_verdict_matches_the_missing_list(self) -> None:
        for kind, row in self.kinds.items():
            with self.subTest(kind=kind):
                gaps = [
                    name
                    for name, param in row["params"].items()
                    if param["critical"] and param["coverage"] == 0
                ]
                self.assertEqual(sorted(gaps), sorted(row["missing"]))
                self.assertEqual(row["playable"], not gaps and row["levelsWithNonEmptyAnchor"] > 0)
                self.assertEqual(row["playable"], kind in self.table["playableKinds"])
                # 判不可玩必须有 missing，判可玩必须没有
                self.assertEqual(bool(row["missing"]), not row["playable"])

    def test_empty_gamemode_objects_block_column_and_invisighoul(self) -> None:
        self.assertEqual(self.table["blockedKinds"], ["column", "invisighoul"])
        for kind in ("column", "invisighoul"):
            row = self.kinds[kind]
            self.assertFalse(row["playable"])
            self.assertEqual(row["missing"], ["gamemodeParams"])
            # 模块挂满了（8/8），但 objdata 全是 {} —— levelsWithNonEmptyAnchor 才是 0
            self.assertEqual(row["levelsWithAnchor"], 8)
            self.assertEqual(row["levelsWithNonEmptyAnchor"], 0)
            self.assertEqual(len(row["levelsIncomplete"]), 8)
            reason = [p for p in row["missingOptional"] if p["name"] == "conveyorSeedBank"]
            self.assertEqual(reason, [])  # 6/8 与 2/8 有关卡有传送带，不算缺

    def test_vasebreaker_parameters(self) -> None:
        row = self.kinds["vasebreaker"]
        self.assertTrue(row["playable"])
        self.assertEqual(row["levels"], 47)
        # 47 关里只有 46 关有 VaseBreakerPresetProperties（frontyard_166 是无尽模式）
        for name in ("vases", "minColumnIndex", "maxColumnIndex", "coloredPlantVases"):
            with self.subTest(param=name):
                self.assertTrue(row["params"][name]["critical"] or name == "coloredPlantVases")
                self.assertEqual(row["params"][name]["coverage"], 46)
        # 彩色罐与排除格不是每关都写
        self.assertEqual(row["params"]["excludelist"]["coverage"], 5)
        self.assertEqual(row["params"]["endlessStages"]["coverage"], 1)
        self.assertEqual(
            row["levelsIncomplete"],
            [
                {
                    "level": "frontyard_166",
                    "missing": ["vases", "minColumnIndex", "maxColumnIndex"],
                }
            ],
        )

    def test_laststand_parameters_and_the_one_incomplete_level(self) -> None:
        row = self.kinds["laststand"]
        self.assertTrue(row["playable"])
        self.assertEqual(row["levels"], 73)
        self.assertEqual(row["params"]["startingSun"]["coverage"], 72)
        self.assertEqual(row["params"]["startingPlantfood"]["coverage"], 72)
        self.assertEqual(row["params"]["waveCount"]["coverage"], 73)
        # 这两项走引擎默认，不算 critical，但 coverage 照实给
        self.assertFalse(row["params"]["seedBankSlots"]["critical"])
        self.assertFalse(row["params"]["sunFromSky"]["critical"])
        self.assertEqual(row["params"]["seedBankSlots"]["coverage"], 9)
        self.assertEqual(row["params"]["sunFromSky"]["coverage"], 7)
        self.assertEqual(row["params"]["sunFromSky"]["agg"]["true"], 7)
        # 唯一起不来的关：cowboy_31 整个 LastStandMinigameProperties 都没有
        self.assertEqual(
            row["levelsIncomplete"],
            [{"level": "cowboy_31", "missing": ["startingSun", "startingPlantfood"]}],
        )

    def test_bowling_bullet_budget_and_the_foul_line_sentinel(self) -> None:
        row = self.kinds["bowling"]
        self.assertTrue(row["playable"])
        self.assertEqual(row["levels"], 15)
        self.assertEqual(row["params"]["foulLine"]["coverage"], 14)  # 1 关没有该字段
        self.assertEqual(row["params"]["bulbPool"]["coverage"], 6)  # 只有 6 关挂了 ConveyorBelt
        self.assertEqual(row["params"]["bulletBudget"]["coverage"], 6)
        self.assertIn("MaxCount", row["params"]["bulletBudget"]["source"])
        self.assertEqual(row["params"]["foulLine"]["agg"]["max"], 99999)
        sentinel = [
            s for s in self.table["sentinels"] if s["kind"] == "bowling" and s["param"] == "foulLine"
        ]
        self.assertEqual(len(sentinel), 1)
        self.assertEqual(sentinel[0]["values"], [99999])
        self.assertEqual(sentinel[0]["levels"], 4)
        self.assertEqual(len(row["levelsIncomplete"]), 1)

    def test_beghouled_matches_to_win_sentinel(self) -> None:
        row = self.kinds["beghouled"]
        self.assertTrue(row["playable"])
        self.assertEqual(row["params"]["matchesToWin"]["coverage"], 11)
        self.assertEqual(row["params"]["matchesToWin"]["agg"]["max"], 1000000)
        self.assertEqual(row["params"]["initialPlants"]["coverage"], 10)
        self.assertEqual(row["params"]["stages"]["coverage"], 11)
        sentinel = [s for s in self.table["sentinels"] if s["kind"] == "beghouled"]
        self.assertEqual([s["values"] for s in sentinel], [[1000000]])

    def test_joust_time_limit_and_the_absent_lineups(self) -> None:
        row = self.kinds["joust"]
        self.assertTrue(row["playable"])
        self.assertEqual(row["levels"], 4)
        self.assertEqual(row["params"]["timeLimit"]["coverage"], 4)
        self.assertEqual(row["params"]["timeLimit"]["agg"]["values"], [180.0, 960])
        self.assertEqual(row["params"]["suggestedLoadout"]["coverage"], 3)
        self.assertEqual(
            row["params"]["suggestedLoadout"]["agg"]["values"],
            ["NoSunBasic", "NoSunMagic", "SunBasic"],
        )
        absent = {p["name"]: p["reason"] for p in row["missingOptional"]}
        self.assertEqual(sorted(absent), ["opponentLineup", "playerLineup"])
        for name in ("opponentLineup", "playerLineup"):
            self.assertEqual(row["params"][name]["coverage"], 0)
            self.assertIn("没有双方独立阵容字段", absent[name])

    def test_whack_targets_and_the_absent_spawn_interval(self) -> None:
        row = self.kinds["whackazombie"]
        self.assertTrue(row["playable"])
        self.assertEqual(row["levels"], 1)
        self.assertEqual(row["params"]["targets"]["coverage"], 1)
        self.assertEqual(row["params"]["hammerHitValue"]["agg"]["items"], 4)
        self.assertEqual(row["params"]["hammerTapsToDecay"]["agg"]["items"], 3)
        absent = {p["name"]: p["reason"] for p in row["missingOptional"]}
        self.assertIn("spawnIntervalSeconds", absent)
        self.assertIn("刷新间隔", absent["spawnIntervalSeconds"])

    def test_cross_reference_kinds_do_not_copy_values(self) -> None:
        for kind, names in (
            ("conveyor", ["mechanicsConveyor", "slots"]),
            ("tide", ["mechanicsTideEvents", "startingWaveLocation"]),
            ("protecttheplant", ["mechanicsProtect", "mustProtectCount"]),
        ):
            row = self.kinds[kind]
            with self.subTest(kind=kind):
                self.assertTrue(row["playable"])
                for name in names:
                    param = row["params"][name]
                    self.assertEqual(param["via"], "cross")
                    self.assertNotIn("agg", param)  # 值留在原产物里，不复制
                    self.assertRegex(param["source"], r"^(level_mechanics|minigames)\.json#")
        # 三者的覆盖率就是 mechanics / minigames 侧的实测数
        self.assertEqual(self.kinds["conveyor"]["params"]["mechanicsConveyor"]["coverage"], 327)
        self.assertEqual(self.kinds["tide"]["params"]["mechanicsTideEvents"]["coverage"], 59)
        self.assertEqual(self.kinds["tide"]["params"]["startingWaveLocation"]["coverage"], 76)
        self.assertEqual(self.kinds["protecttheplant"]["params"]["mechanicsProtect"]["coverage"], 189)

    def test_rail_levels_without_geometry_are_listed(self) -> None:
        row = self.kinds["rail"]
        self.assertTrue(row["playable"])
        self.assertEqual(row["levels"], 196)
        self.assertEqual(row["params"]["rails"]["coverage"], 191)
        self.assertEqual(row["params"]["railcarts"]["coverage"], 191)
        self.assertEqual(row["params"]["railcartType"]["coverage"], 190)
        self.assertEqual(row["levelsWithAnchor"], 191)
        missing_levels = [e["level"] for e in row["levelsIncomplete"]]
        self.assertEqual(
            missing_levels, ["fairy_31", "future_66", "future_69", "future_70", "plantagenet_47"]
        )
        for entry in row["levelsIncomplete"]:
            self.assertEqual(entry["missing"], ["rails", "railcarts"])

    def test_cannon_parameters_are_complete(self) -> None:
        row = self.kinds["cannon"]
        self.assertTrue(row["playable"])
        self.assertEqual(row["levels"], 8)
        self.assertEqual(row["levelsIncomplete"], [])
        for name, param in row["params"].items():
            with self.subTest(param=name):
                self.assertEqual(param["coverage"], 8)
        self.assertEqual(row["params"]["lanes"]["agg"]["maxItems"], 5)

    def test_absent_kinds_record_the_missing_module(self) -> None:
        absent = self.table["absentKinds"]
        self.assertEqual([row["id"] for row in absent], ["chicken"])
        row = absent[0]
        self.assertEqual(row["levels"], 0)
        self.assertIn("ZombieChickenProps", row["whatItIs"])
        self.assertIn("minigames.py", row["probe"])
        self.assertEqual(row["evidence"], "minigames.json#unknowns[type=kind-without-module, kind=chicken]")

    def test_render_matches_disk_and_has_no_crlf(self) -> None:
        raw = SHIPPED.read_bytes()
        self.assertNotIn(b"\r\n", raw)
        self.assertTrue(raw.endswith(b"}\n"))
        self.assertEqual(raw, minigame_rules.render(self.table).encode("utf-8"))

    def test_needle_report_finds_registered_params(self) -> None:
        self.assertEqual(minigame_rules.needle_report("bullet"), 0)
        self.assertEqual(minigame_rules.needle_report("no-such-param-anywhere"), 1)


@unittest.skipUnless(HAS_OBB, "要 OBB dump 才能重编译")
class CompileRulesTests(unittest.TestCase):
    def test_shipped_equals_a_fresh_build(self) -> None:
        fresh = minigame_rules.build()
        self.assertEqual(
            minigame_rules.render(fresh).encode("utf-8"), SHIPPED.read_bytes()
        )

    def test_check_is_idempotent(self) -> None:
        self.assertEqual(minigame_rules.main(["--check"]), 0)

    def test_stale_file_is_rejected(self) -> None:
        stale = load()
        stale["counts"]["playable"] += 1  # 造一个与重算不符的产物
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "minigame_rules.json"
            path.write_bytes(minigame_rules.render(stale).encode("utf-8"))
            self.assertEqual(minigame_rules.main(["--check", "--out", str(path)]), 1)

    def test_build_is_byte_stable_across_runs(self) -> None:
        first = minigame_rules.render(minigame_rules.build())
        minigame_rules._CACHE.clear()
        second = minigame_rules.render(minigame_rules.build())
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
