# -*- coding: utf-8 -*-
"""植物名册合并（`tools/contentc/plants_merge.py`）的回归测试。

这里的数字都是**实测**，不是目标数字：

* 原版 `PlantType` 名册 339 条（`plants_from_pack.json` 的 295 emitted + 44 skipped），
  其中 304 条可玩、35 条被阻断（缺成本 23 / 缺美术 15 / 两者都缺 3）。
* 手工名册 147 条里只有 44 条与 pack 同名；262 条可玩的 pack 行被合并进来，
  所以 `content/plants.json` 从 147 条长到 **409** 条。
* 「339 = 147 + 192」这条算术在本数据上不成立（147 + 295 = 442），测试把反例钉住，
  免得以后有人照着 339 去删手工行。

阻断的 46 条不进名册，但落进 `native/generated/plant_blocked.json`，缺口可审计。
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.contentc import plants_merge as pm  # noqa: E402
from tools import obb_build_content_v2 as builder  # noqa: E402

PLANTS = REPO / "content" / "plants.json"
PACK_JSON = REPO / "native" / "generated" / "plants_from_pack.json"
BLOCKED = REPO / "native" / "generated" / "plant_blocked.json"

AUTHORED = 147
# 2026-11-26：美术索引重建（bases 1087 → 1135）后可玩 293 → 304、新增 251 → 262，
# 所以 pack 行从 251 变成 262，阻断 46 → 35。
PACK_ONLY = 262
TOTAL = 409
CONFLICTS = 44
BLOCKED_TOTAL = 35


def _rows() -> list[dict]:
    return json.loads(PLANTS.read_text(encoding="utf-8"))


class CountsTest(unittest.TestCase):
    """147 手工 + 262 可玩 pack 行 = 409；44 条同名手工行胜出。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = pm.build()

    def test_measured_counts(self) -> None:
        c = self.result.counts
        self.assertEqual(c["total"], TOTAL)
        self.assertEqual(c["authored"], AUTHORED)
        self.assertEqual(c["pack"], PACK_ONLY)
        self.assertEqual(c["packOnly"], PACK_ONLY)
        self.assertEqual(c["conflicts"], CONFLICTS)
        self.assertEqual(c["skippedExisting"], CONFLICTS)
        self.assertEqual(c["packRoster"], 339)
        self.assertEqual(c["playable"], 304)
        self.assertEqual(c["playableAuthored"], 42)
        self.assertEqual(c["blocked"], BLOCKED_TOTAL)
        self.assertEqual(c["blockedPackOnly"], 33)
        self.assertEqual(self.result.total, TOTAL)

    def test_three_hundred_thirty_nine_is_not_reachable_without_deleting(self) -> None:
        """「339 = 147 + 192」的反例：147 + 295 = 442，删 103 条手工行才凑得出 339。"""
        c = self.result.counts
        _pack, skipped, roster = pm.load_pack(allow=None)
        self.assertEqual(len(_pack) + len(skipped), roster)
        self.assertEqual(roster, 339)
        self.assertNotEqual(AUTHORED + PACK_ONLY, 339)
        self.assertEqual(c["playable"] - c["playableAuthored"], PACK_ONLY)
        self.assertEqual(c["pack"] + c["blockedPackOnly"], 295)  # emitted 295 = 可玩 262 + 阻断 33
        self.assertEqual(c["playable"], c["pack"] + c["playableAuthored"])

    def test_conflicts_are_the_skipped_existing_ids(self) -> None:
        _pack, skipped, _roster = pm.load_pack(allow=None)
        self.assertEqual(sorted(skipped), sorted(self.result.conflicts))

    def test_merged_ids_are_unique_and_pack_rows_sorted(self) -> None:
        ids = [row["id"] for row in self.result.rows]
        self.assertEqual(len(ids), len(set(ids)))
        added = [row["id"] for row in self.result.rows[AUTHORED:]]
        self.assertEqual(added, sorted(added))
        self.assertEqual(added, self.result.pack_only)


class AuthoredRowsTest(unittest.TestCase):
    """手工 147 行必须原样出现，且不带来源标记。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = pm.build()
        cls.disk = _rows()
        cls.manual = pm.load_manual()

    def test_disk_holds_the_merged_roster(self) -> None:
        self.assertEqual(len(self.disk), TOTAL)

    def test_authored_rows_are_emitted_verbatim_in_order(self) -> None:
        self.assertEqual([row["id"] for row in self.manual],
                         [row["id"] for row in self.result.rows[:AUTHORED]])
        self.assertEqual(self.manual, self.result.rows[:AUTHORED])

    def test_no_authored_row_carries_a_source_marker(self) -> None:
        for row in self.manual:
            self.assertNotIn("source", row, row["id"])

    def test_every_added_row_is_tagged_pack(self) -> None:
        for row in self.result.rows[AUTHORED:]:
            self.assertEqual(row.get("source"), "pack", row["id"])

    def test_loading_the_shipped_file_still_yields_the_authored_rows(self) -> None:
        self.assertEqual(len(self.manual), AUTHORED)
        self.assertTrue(all("source" not in row for row in self.manual))

    def test_shipped_file_matches_the_merge_byte_for_byte(self) -> None:
        self.assertEqual(pm.render(self.result.rows), PLANTS.read_bytes())


class BlockedTest(unittest.TestCase):
    """46 条阻断不写进名册，但必须留在 `plant_blocked.json` 里可查。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(BLOCKED.read_text(encoding="utf-8"))
        cls.rows = {row["id"]: row for row in cls.payload["rows"]}
        cls.roster = {row["id"] for row in _rows()}

    def test_counts_are_measured(self) -> None:
        c = self.payload["counts"]
        self.assertEqual(self.payload["marker"], "plant-blocked-v1")
        self.assertEqual(c["total"], BLOCKED_TOTAL)
        self.assertEqual(c["missingCost"], 23)
        self.assertEqual(c["missingArt"], 15)
        self.assertEqual(c["missingFamily"], 0)
        self.assertEqual(c["both"], 3)
        self.assertEqual(c["packOnly"], 33)
        self.assertEqual(c["authored"], 2)

    def test_blocked_ids_are_not_in_the_roster(self) -> None:
        self.assertEqual(sorted(self.rows), sorted(set(self.rows)))
        # 唯二例外是手工名册里本来就有的 iceburg / potatochip：它们缺成本，
        # 但手工行不许删，所以「在名册里」与「被阻断」同时成立。
        authored_blockers = {rid for rid, row in self.rows.items() if row["inRoster"]}
        self.assertEqual(self.roster & set(self.rows), authored_blockers)
        self.assertEqual(sorted(authored_blockers), ["iceburg", "potatochip"])

    def test_authored_blockers_are_the_two_zero_cost_rows(self) -> None:
        authored = sorted(rid for rid, row in self.rows.items() if row["inRoster"])
        self.assertEqual(authored, ["iceburg", "potatochip"])
        for rid in authored:
            self.assertIn("no-cost", self.rows[rid]["blockers"])

    def test_every_row_carries_a_reason(self) -> None:
        for rid, row in self.rows.items():
            self.assertTrue(row["reason"], rid)
            self.assertTrue(row["blockers"], rid)
            for blocker in row["blockers"]:
                self.assertIn(blocker, ("no-cost", "no-art", "no-family"), rid)

    def test_both_blockers_are_the_three_expected_rows(self) -> None:
        both = sorted(rid for rid, row in self.rows.items() if len(row["blockers"]) > 1)
        self.assertEqual(both, ["blastspinnercocoon", "imppear_teto", "littleguy"])


class MergeRulesTest(unittest.TestCase):
    """用小样本钉合并规则本身。"""

    def test_conflict_keeps_the_authored_row(self) -> None:
        manual = [{"id": "pea", "hp": 300, "name_zh": "豌豆"}]
        pack = [{"id": "pea", "hp": 999, "name_zh": "PACK"}]
        result = pm.merge_rows(manual, pack)
        self.assertEqual(result.conflicts, ["pea"])
        self.assertEqual(result.total, 1)
        self.assertEqual(result.rows[0]["hp"], 300)
        self.assertNotIn("source", result.rows[0])

    def test_pack_row_drops_empty_fields_and_keeps_id_first(self) -> None:
        row = {"id": "x", "art": None, "desc_zh": "", "tags": [], "extra": {},
               "hp": 100, "name_zh": "某", "packFacts": {"cost": 100}}
        cleaned = pm.clean_pack_row(row)
        self.assertEqual(list(cleaned)[0], "id")
        self.assertEqual(cleaned["hp"], 100)
        self.assertEqual(cleaned["source"], "pack")
        for key in ("art", "desc_zh", "tags", "extra", "packFacts"):
            self.assertNotIn(key, cleaned)

    def test_duplicate_id_in_manual_is_an_error(self) -> None:
        with self.assertRaises(pm.MergeError):
            pm.merge_rows([{"id": "a"}, {"id": "a"}], [])

    def test_duplicate_id_in_pack_is_an_error(self) -> None:
        with self.assertRaises(pm.MergeError):
            pm.merge_rows([], [{"id": "a"}, {"id": "a"}])

    def test_missing_id_is_an_error(self) -> None:
        with self.assertRaises(pm.MergeError):
            pm.merge_rows([{"hp": 1}], [])

    def test_unknown_source_marker_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plants.json"
            path.write_text(json.dumps([{"id": "a", "source": "hand"}]), encoding="utf-8")
            with self.assertRaises(pm.MergeError):
                pm.load_manual(path)

    def test_playable_ids_missing_from_the_pack_are_an_error(self) -> None:
        with self.assertRaises(pm.MergeError):
            pm.load_pack(PACK_JSON, allow=["definitely-not-a-plant"])


class RenderTest(unittest.TestCase):
    """落盘格式与幂等：同一输入两次写出的字节必须一致。"""

    def test_render_is_stable(self) -> None:
        first = pm.render(pm.build().rows)
        second = pm.render(pm.build().rows)
        self.assertEqual(hashlib.sha256(first).hexdigest(),
                         hashlib.sha256(second).hexdigest())
        self.assertFalse(first.endswith(b"\n"))
        self.assertTrue(first.startswith(b"[\n {"))

    def test_blocked_render_is_stable(self) -> None:
        first = pm.render_blocked(pm.build().blocked)
        second = pm.render_blocked(pm.build().blocked)
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))

    def test_check_accepts_the_shipped_files(self) -> None:
        ok, message, _result = pm.check()
        self.assertTrue(ok, message)


class CliTest(unittest.TestCase):
    """`--check` / `-n` / 篡改检测 / 幂等。"""

    def _run(self, *argv: str) -> tuple[int, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            code = pm.main(list(argv))
        return code, buffer.getvalue()

    def test_check_passes_on_the_shipped_files(self) -> None:
        code, out = self._run("--check")
        self.assertEqual(code, 0, out)
        self.assertIn("plants=409", out)

    def test_check_detects_a_tampered_roster(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "plants.json"
            copy.write_bytes(PLANTS.read_bytes() + b" ")
            blocked = Path(tmp) / "plant_blocked.json"
            blocked.write_bytes(BLOCKED.read_bytes())
            code, out = self._run("--check", "--out", str(copy), "--blocked", str(blocked))
            self.assertEqual(code, 1, out)
            self.assertIn("不一致", out)

    def test_check_detects_a_tampered_blocked_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            roster = Path(tmp) / "plants.json"
            roster.write_bytes(PLANTS.read_bytes())
            blocked = Path(tmp) / "plant_blocked.json"
            blocked.write_bytes(BLOCKED.read_bytes().replace(b"plant-blocked-v1", b"plant-blocked-v2"))
            code, out = self._run("--check", "--out", str(roster), "--blocked", str(blocked))
            self.assertEqual(code, 1, out)

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "plants.json"
            blocked = Path(tmp) / "plant_blocked.json"
            code, text = self._run("-n", "--out", str(out), "--blocked", str(blocked))
            self.assertEqual(code, 0, text)
            self.assertFalse(out.exists())
            self.assertFalse(blocked.exists())
            self.assertIn("plants=409", text)

    def test_write_then_check_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "plants.json"
            blocked = Path(tmp) / "plant_blocked.json"
            code, _ = self._run("--out", str(out), "--blocked", str(blocked))
            self.assertEqual(code, 0)
            first, first_blocked = out.read_bytes(), blocked.read_bytes()
            code, _ = self._run("--out", str(out), "--blocked", str(blocked))
            self.assertEqual(code, 0)
            self.assertEqual(first, out.read_bytes())
            self.assertEqual(first_blocked, blocked.read_bytes())
            code, _ = self._run("--check", "--out", str(out), "--blocked", str(blocked))
            self.assertEqual(code, 0)

    def test_second_generation_has_the_same_sha256(self) -> None:
        digests = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "plants.json"
                blocked = Path(tmp) / "plant_blocked.json"
                self._run("--out", str(out), "--blocked", str(blocked))
                digests.append((hashlib.sha256(out.read_bytes()).hexdigest(),
                                hashlib.sha256(blocked.read_bytes()).hexdigest()))
        self.assertEqual(digests[0], digests[1])


class BuilderWiringTest(unittest.TestCase):
    """builder 侧的两个入口都走同一个合并器。"""

    def test_build_plants_roster_matches_the_module(self) -> None:
        result = builder.build_plants_roster()
        self.assertEqual(result.counts, pm.build().counts)
        self.assertEqual(result.counts["total"], TOTAL)

    def test_content_report_line_has_the_plant_counts(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = builder.main(["--content-report"])
        text = buffer.getvalue()
        self.assertEqual(code, 0, text)
        self.assertIn(
            "plants=409 authored=147 pack=262 playable=304 blocked=35 conflicts=44 "
            "merged=409 packRoster=339",
            text,
        )
        self.assertIn("mismatches: none", text)


class ShapeTest(unittest.TestCase):
    """合并后的行本身要经得起引擎与工具读。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.added = pm.build().rows[AUTHORED:]

    def test_no_pack_row_carries_an_empty_string(self) -> None:
        for row in self.added:
            for key, value in row.items():
                self.assertNotEqual(value, "", f"{row['id']}.{key}")

    def test_pack_rows_keep_the_fields_the_catalog_expects(self) -> None:
        rows = self.added
        self.assertEqual(len(rows), PACK_ONLY)
        for row in rows:
            self.assertTrue(row.get("name_zh") or row.get("name_en"), row["id"])
            self.assertIn("hp", row, row["id"])
            self.assertIn("behavior", row, row["id"])
            self.assertIsNotNone(row.get("cost"), row["id"])
        # 原版的 PlantType 表只给英文名，中文名一个都没有：合并器不编造中文，
        # 只把 name_en 留下（引擎的 name_zh 可缺省，catalog 会退回 name_en）。
        self.assertEqual(sum(1 for row in rows if not row.get("name_zh")), PACK_ONLY)
        self.assertEqual(sum(1 for row in rows if not row.get("name_en")), 0)

    def test_rows_without_art_are_still_valid_and_counted(self) -> None:
        rows = self.added
        with_art = [row["id"] for row in rows if row.get("art")]
        without = [row["id"] for row in rows if not row.get("art")]
        self.assertEqual(len(with_art) + len(without), len(rows))
        # 262 条里 23 条能在原版美术库命中，其余 239 条没有 art —— 真实缺口，
        # 引擎按 `battle_view.cpp` 的既有兜底画占位形状，不在这里补假路径。
        self.assertEqual(len(with_art), 23)
        self.assertEqual(len(without), 239)


if __name__ == "__main__":
    unittest.main()

# `--content-report` 的派生标记要读原版表目录（`work/obb_packages` 不进仓库）：
# 缺目录时整套跳过，否则 derived*=0 会让「mismatches: none」这条断言假红。
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
