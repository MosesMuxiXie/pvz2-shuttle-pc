"""Tests for tools/contentc/minigames.py — 460.9 minigame / variant-play table.

Two groups:

* `ShippedMinigamesTests` only reads `native/generated/minigames.json`, so it runs anywhere
  (a CI box without the OBB still proves the shipped product is complete and consistent).
* `CompileMinigamesTests` needs the OBB and recompiles: the shipped bytes must equal a fresh
  render, `--check` must be idempotent, and a stale file must be rejected.
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

from contentc import minigames, worlds  # noqa: E402

SHIPPED = minigames.DEFAULT_OUT
LEVELS_DIR = minigames.DEFAULT_LEVELS
HAS_OBB = worlds.DEFAULT_OBB.is_dir()

EXPECTED_BY_KIND = {
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


def load_shipped() -> dict:
    with SHIPPED.open(encoding="utf-8") as handle:
        return json.load(handle)


def content_extra(flag: str) -> dict:
    """level id -> package for levels whose extra.<flag> is truthy."""
    out = {}
    for path in sorted(LEVELS_DIR.glob("*.json")):
        with path.open(encoding="utf-8-sig") as handle:
            doc = json.load(handle)
        extra = doc.get("extra") or {}
        if extra.get(flag):
            out[doc.get("id") or path.stem] = minigames.package_stem(extra.get("package"))
    return out


def levels_with_kind(table: dict, kind: str) -> list:
    return sorted(lid for lid, row in table["levels"].items() if kind in row["kinds"])


class ShippedMinigamesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.table = load_shipped()
        cls.levels = cls.table["levels"]
        cls.counts = cls.table["counts"]
        cls.cross = cls.table["crossChecks"]
        cls.unknowns = cls.table["unknowns"]

    # ---------------------------------------------------------------- shape

    def test_top_level_shape(self) -> None:
        self.assertEqual(self.table["format"], "pvz2-shuttle/minigames@1")
        self.assertEqual(self.table["generated"], "2026-11-25")
        self.assertEqual(
            sorted(self.table),
            ["counts", "crossChecks", "format", "generated", "levels", "sources", "unknowns"],
        )

    def test_every_level_row_carries_the_contract(self) -> None:
        for lid, row in self.levels.items():
            self.assertEqual(
                sorted(row),
                ["categories", "extra", "kinds", "levelFile", "modules", "package", "params", "relatedModules"],
                lid,
            )
            self.assertTrue(row["kinds"], lid)
            self.assertTrue(row["package"].startswith("pkg_"), lid)
            self.assertEqual(sorted(row["extra"]), ["minecarts", "rail", "special", "vasebreaker"], lid)

    def test_kinds_follow_the_registry_order(self) -> None:
        order = minigames.KIND_ORDER
        for lid, row in self.levels.items():
            self.assertEqual(
                sorted(row["kinds"], key=order.index), row["kinds"], lid
            )

    def test_levels_are_sorted_and_unique(self) -> None:
        self.assertEqual(list(self.levels), sorted(self.levels))
        self.assertEqual(len(self.levels), 813)
        self.assertEqual(self.counts["levelsScanned"], 1809)

    # --------------------------------------------------------------- counts

    def test_by_kind_matches_the_report_table(self) -> None:
        self.assertEqual(self.counts["byKind"], dict(sorted(EXPECTED_BY_KIND.items())))

    def test_kind_and_category_totals(self) -> None:
        self.assertEqual(self.counts["kinds"], 20)
        self.assertEqual(len(minigames.KINDS), 20)
        self.assertEqual(self.counts["minigameLevels"], 209)
        self.assertEqual(self.counts["variantLevels"], 673)
        # 一关可以同时属于两类（例如 rail + 小游戏），所以两者相加大于 levels。
        self.assertLess(self.counts["levels"], self.counts["minigameLevels"] + self.counts["variantLevels"])

    def test_by_kind_sums_to_level_kind_occurrences(self) -> None:
        total = sum(len(row["kinds"]) for row in self.levels.values())
        self.assertEqual(sum(self.counts["byKind"].values()), total)
        self.assertEqual(total, 1019)

    def test_multi_kind_levels_are_real(self) -> None:
        multi = [lid for lid, row in self.levels.items() if len(row["kinds"]) > 1]
        self.assertEqual(len(multi), 181)

    # ------------------------------------------- cross-check with content/

    def test_vasebreaker_kind_equals_content_flag(self) -> None:
        content = content_extra("vasebreaker")
        self.assertEqual(len(content), 47)
        self.assertEqual(levels_with_kind(self.table, "vasebreaker"), sorted(content))
        self.assertEqual(self.cross["vasebreaker"]["agree"], 47)
        self.assertEqual(self.cross["vasebreaker"]["packOnly"], [])
        self.assertEqual(self.cross["vasebreaker"]["contentOnly"], [])

    def test_rail_agrees_with_content_except_ten_known_levels(self) -> None:
        content = content_extra("rail")
        self.assertEqual(len(content), 192)
        pack = set(levels_with_kind(self.table, "rail"))
        self.assertEqual(pack - set(content),
                         {"egypt_46", "fairy_31", "frontyard_98", "future_66",
                          "future_69", "future_70", "plantagenet_47"})
        self.assertEqual(set(content) - pack, {"cowboy_41", "cowboy_42", "kongfu_44"})
        self.assertEqual(self.cross["rail"]["agree"], 189)
        self.assertEqual(len(pack), 196)

    def test_content_rail_only_levels_have_no_rail_module(self) -> None:
        for lid in ("cowboy_41", "cowboy_42", "kongfu_44"):
            row = self.levels.get(lid)
            if row is None:
                continue  # level with no kind at all is fine; the unknown row records it
            self.assertNotIn("rail", row["kinds"], lid)
        types = {row["type"]: row for row in self.unknowns}
        self.assertIn("content-rail-without-module", types)
        self.assertEqual(
            types["content-rail-without-module"]["levels"],
            ["cowboy_41", "cowboy_42", "kongfu_44"],
        )

    def test_special_is_vasebreaker_and_fully_covered(self) -> None:
        self.assertEqual(self.cross["special"]["values"], ["IsVasebreaker"])
        self.assertEqual(self.cross["special"]["contentLevels"], 45)
        self.assertTrue(self.cross["special"]["allCoveredByVasebreakerKind"])
        self.assertEqual(self.cross["special"]["notCovered"], [])

    # -------------------------------------------------------- spot checks

    def test_beach_69_is_a_vasebreaker_with_tide(self) -> None:
        row = self.levels["beach_69"]
        self.assertEqual(row["package"], "pkg_0290")
        self.assertEqual(row["kinds"], ["vasebreaker", "tide"])
        preset = row["params"]["vasebreaker"]["VaseBreakerPresetProperties"][0]
        self.assertEqual(preset["MinColumnIndex"], 2)
        self.assertEqual(preset["MaxColumnIndex"], 8)
        self.assertEqual(len(preset["Vases"]), 12)
        self.assertEqual(row["params"]["tide"]["TideProperties"][0]["StartingWaveLocation"], 4)

    def test_egypt_8_is_joust_with_last_stand_params(self) -> None:
        row = self.levels["egypt_8"]
        self.assertEqual(row["package"], "pkg_0507")
        self.assertIn("joust", row["kinds"])
        self.assertIn("laststand", row["kinds"])
        joust = row["params"]["joust"]["JoustGameModuleProperties"][0]
        self.assertEqual(joust["TimeLimit"], 180.0)
        self.assertEqual(joust["SuggestedLoadout"], "SunBasic")

    def test_modern_32_is_beghouled(self) -> None:
        row = self.levels["modern_32"]
        self.assertEqual(row["kinds"], ["beghouled"])
        preset = row["params"]["beghouled"]["BeghouledPresetProperties"][0]
        self.assertEqual(preset["MatchesToWin"], 1000000)
        bank = row["params"]["beghouled"]["BeghouledSeedBankProperties"][0]
        self.assertEqual(bank["SelectionMethod"], "beghouled")

    def test_joust_counts_only_anchor_levels(self) -> None:
        # plantagenet_22/23 只挂了 JoustZombieWinCondition / JoustDarkMowers，没有 JoustModule，
        # 所以它们不能算 joust —— 这正是 anchor/related 分离要防的膨胀。
        self.assertEqual(levels_with_kind(self.table, "joust"),
                         ["egypt_8", "egypt_9", "plantagenet_20", "plantagenet_21"])

    def test_whack_a_zombie_is_a_single_level(self) -> None:
        self.assertEqual(levels_with_kind(self.table, "whackazombie"), ["beach_20"])
        params = self.levels["beach_20"]["params"]["whackazombie"]
        self.assertEqual(params["MinigameWhackAZombieModuleProperties"][0]["HammerTapsToDecay"], [60, 40, 20])

    def test_star_challenge_is_excluded_not_counted_as_a_kind(self) -> None:
        self.assertNotIn("challenge", self.counts["byKind"])
        self.assertNotIn("starchallenge", self.counts["byKind"])
        self.assertEqual(self.counts["excluded"]["ChallengeModule"]["levels"], 924)
        for kind in ("PlantagenetMiniGameMusic", "RenaiMiniGameMusic", "SteamMiniGameMusic"):
            self.assertIn(kind, self.counts["excluded"])

    # ------------------------------------------------------------ unknowns

    def test_chicken_has_no_module_and_is_recorded(self) -> None:
        rows = {row["kind"]: row for row in self.unknowns if row["type"] == "kind-without-module"}
        self.assertIn("chicken", rows)
        self.assertEqual(rows["chicken"]["levels"], 0)
        self.assertIn("ZombieChickenProps", rows["chicken"]["whatItIs"])

    def test_no_keyword_module_is_silently_dropped(self) -> None:
        # 注册表 + 排除表 + 参数类之外，关键词命中的模块都要么分类、要么进 unknowns。
        registered = set(minigames.ANCHOR_TO_KIND) | set(minigames.RELATED_TO_KIND) | set(minigames.EXCLUDED_MODULES)
        seen = {name for row in self.levels.values() for name in row["modules"]}
        unregistered = {
            row["type"]: row for row in self.unknowns if row["type"] == "unregistered-module"
        }
        flagged = set()
        if "unregistered-module" in unregistered:
            flagged = {row["alias"] for row in unregistered["unregistered-module"]["modules"]}
        for name in seen:
            if minigames.KEYWORD_RE.search(name):
                self.assertTrue(
                    name in registered or name in flagged,
                    f"keyword module {name} neither classified nor recorded",
                )


class CompileMinigamesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not HAS_OBB:
            raise unittest.SkipTest(f"OBB not present: {worlds.DEFAULT_OBB}")
        cls.table = minigames.build(worlds.DEFAULT_OBB, LEVELS_DIR)

    def test_fresh_render_matches_the_shipped_bytes(self) -> None:
        fresh = minigames.render(self.table).encode("utf-8")
        self.assertEqual(fresh, SHIPPED.read_bytes())
        self.assertNotIn(b"\r\n", fresh)
        self.assertTrue(fresh.endswith(b"\n"))

    def test_check_passes_on_the_shipped_file(self) -> None:
        self.assertEqual(minigames.check(self.table, SHIPPED), 0)

    def test_check_rejects_a_stale_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "minigames.json"
            stale.write_bytes(b'{"format": 1}\n')
            self.assertEqual(minigames.check(self.table, stale), 1)

    def test_compile_is_stable_across_two_runs(self) -> None:
        again = minigames.build(worlds.DEFAULT_OBB, LEVELS_DIR)
        self.assertEqual(minigames.render(self.table), minigames.render(again))


if __name__ == "__main__":
    unittest.main()
