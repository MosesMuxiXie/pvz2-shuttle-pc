#!/usr/bin/env python3
"""Tests for tools/smoke_rebaseline.py.

The gate itself is stubbed out: `smoke_rebaseline.collect` is replaced with a fake
report, so every case here is about the *bookkeeping* — what counts as drift, what
`--accept` writes, and what it refuses to write.
"""

from __future__ import annotations

import importlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import smoke_rebaseline as R  # noqa: E402


def entry(name: str, hash_: str, **overrides) -> dict:
    base = {
        "name": name, "level": "some_level", "seconds": 120,
        "rows": 5, "cols": 9, "status": "playing", "tick": 7200, "hash": hash_,
        "spawned": 15, "killed": 0, "removed": 0, "mowerKills": 8, "leaked": 0,
        "rejectedSpawns": 0, "unwiredPlants": 0, "unwiredZombies": 0,
    }
    base.update(overrides)
    return base


class RebaselineCase(unittest.TestCase):
    """One baseline file, one record document, one stubbed gate."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.baseline = root / "engine_smoke.json"
        self.log = root / "PARITY_BASELINE.md"
        self.addCleanup(self._tmp.cleanup)
        self.cowboy = entry("world cowboy", "0xeb036737659cbc46")
        self.beach = entry("world beach", "0x4546274cc13f33a8")
        self.write_baseline([self.cowboy, self.beach])

    # -- helpers ---------------------------------------------------------
    def write_baseline(self, entries: list[dict]) -> None:
        self.baseline.write_bytes(R.render({"scenarios": entries}).encode("utf-8"))

    def use(self, entries: list[dict]) -> None:
        report = {"scenarios": entries}
        self._saved = R.collect
        R.collect = lambda *a, **k: json.loads(json.dumps(report))
        self.addCleanup(lambda: setattr(R, "collect", self._saved))

    def run_main(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = R.main([*argv, "--baseline", str(self.baseline), "--log", str(self.log),
                           "--timestamp", "2026-11-26T12:00:00Z"])
        return code, out.getvalue(), err.getvalue()

    def accept(self, *names: str, reason: str = "rail carts moved the row") -> tuple[int, str, str]:
        argv: list[str] = []
        for name in names:
            argv += ["--accept", name]
        if reason:
            argv += ["--reason", reason]
        return self.run_main(*argv)

    def md_text(self) -> str:
        return self.log.read_text(encoding="utf-8")

    # -- 1. clean run ----------------------------------------------------
    def test_check_clean_exits_zero(self) -> None:
        self.use([self.cowboy, self.beach])
        code, out, _ = self.run_main("--check")
        self.assertEqual(code, 0)
        self.assertIn("no change", out)
        self.assertIn("2 scenarios", out)

    # -- 2. one scenario drifted ----------------------------------------
    def test_check_single_change_names_it_and_exits_one(self) -> None:
        moved = entry("world cowboy", "0xcb83dd8dcba537f5", tick=7300, killed=2)
        self.use([moved, self.beach])
        code, out, _ = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("~ changed  world cowboy", out)
        self.assertIn("0xeb036737659cbc46 -> 0xcb83dd8dcba537f5", out)
        self.assertIn("tick 7200->7300", out)
        self.assertIn("killed 0->2", out)
        self.assertNotIn("world beach", out)

    def test_check_does_not_touch_baseline(self) -> None:
        before = self.baseline.read_bytes()
        self.use([entry("world cowboy", "0xcb83dd8dcba537f5"), self.beach])
        self.assertEqual(self.run_main("--check")[0], 1)
        self.assertEqual(self.baseline.read_bytes(), before)
        self.assertFalse(self.log.exists())

    # -- 3. accept one of two -------------------------------------------
    def test_accept_only_the_named_scenario(self) -> None:
        moved = entry("world cowboy", "0xcb83dd8dcba537f5", killed=2)
        reordered = entry("world beach", "0x9999999999999999")
        self.use([moved, reordered])
        code, out, _ = self.accept("world cowboy")
        self.assertEqual(code, 0, out)
        self.assertIn("remaining drift not accepted: 1", out)
        self.assertIn("world beach", out)
        # the accepted one is current, the other one is still red
        code, out, _ = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("world beach", out)
        self.assertNotIn("world cowboy", out)

    def test_accept_then_check_is_clean(self) -> None:
        self.use([entry("world cowboy", "0xcb83dd8dcba537f5"),
                  entry("world beach", "0x9999999999999999")])
        self.assertEqual(self.accept("world cowboy", "world beach")[0], 0)
        code, out, _ = self.run_main("--check")
        self.assertEqual(code, 0, out)
        self.assertIn("no change", out)

    def test_accept_comma_separated_and_repeated(self) -> None:
        self.use([entry("world cowboy", "0xcb83dd8dcba537f5"),
                  entry("world beach", "0x9999999999999999")])
        code, out, _ = self.run_main("--accept", "world cowboy,world beach",
                                     "--reason", "both moved")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.run_main("--check")[0], 0)

    # -- 4. reason is mandatory -----------------------------------------
    def test_accept_without_reason_exits_two_and_writes_nothing(self) -> None:
        before = self.baseline.read_bytes()
        self.use([entry("world cowboy", "0xcb83dd8dcba537f5"), self.beach])
        code, _, err = self.accept("world cowboy", reason="")
        self.assertEqual(code, 2)
        self.assertIn("--reason", err)
        self.assertEqual(self.baseline.read_bytes(), before)
        self.assertFalse(self.log.exists())

    def test_accept_blank_reason_exits_two(self) -> None:
        self.use([entry("world cowboy", "0xcb83dd8dcba537f5"), self.beach])
        code, _, err = self.run_main("--accept", "world cowboy", "--reason", "   ")
        self.assertEqual(code, 2)
        self.assertIn("--reason", err)

    def test_accept_unknown_name_exits_two(self) -> None:
        self.use([entry("world cowboy", "0xcb83dd8dcba537f5"), self.beach])
        code, _, err = self.accept("world beach")
        self.assertEqual(code, 2)
        self.assertIn("not changed", err)
        self.assertIn("world beach", err)

    # -- 5. baseline shape stays byte-compatible -------------------------
    def test_baseline_keeps_the_gate_shape_and_dumper(self) -> None:
        self.use([entry("world cowboy", "0xcb83dd8dcba537f5"), self.beach])
        self.assertEqual(self.accept("world cowboy")[0], 0)
        raw = self.baseline.read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertTrue(raw.endswith(b"\n"))
        doc = json.loads(raw.decode("utf-8"))
        self.assertEqual(list(doc), ["scenarios"])
        self.assertEqual([e["name"] for e in doc["scenarios"]], ["world cowboy", "world beach"])
        expected_keys = set(entry("x", "0x0"))
        self.assertEqual(set(doc["scenarios"][1]), expected_keys)
        # byte-for-byte: the gate's own dumper, not a second one
        self.assertEqual(raw.decode("utf-8"), R.render(doc))
        self.assertTrue(raw.decode("utf-8").startswith('{\n "scenarios": [\n  {\n   "cols": '))

    def test_render_is_the_gate_dumper(self) -> None:
        self.assertIs(R.engine_smoke, importlib.import_module("engine_smoke"))
        self.assertEqual(R.render({"scenarios": []}), '{\n "scenarios": []\n}\n')

    def test_write_baseline_refuses_crlf(self) -> None:
        saved = R.render
        R.render = lambda report: '{\r\n "scenarios": []\r\n}\r\n'
        self.addCleanup(lambda: setattr(R, "render", saved))
        with self.assertRaises(R.BaselineError) as caught:
            R.write_baseline(self.baseline, {"scenarios": []})
        self.assertIn("CRLF", str(caught.exception))

    # -- 6. the change record -------------------------------------------
    def test_record_row_is_appended(self) -> None:
        self.use([entry("world cowboy", "0xcb83dd8dcba537f5"), self.beach])
        self.assertEqual(self.accept("world cowboy")[0], 0)
        text = self.md_text()
        self.assertIn("## 冒烟基线变更记录", text)
        self.assertIn(R.TABLE_HEADER, text)
        self.assertIn("| 2026-11-26T12:00:00Z | `world cowboy` | `0xeb036737659cbc46` "
                      "| `0xcb83dd8dcba537f5` | rail carts moved the row |", text)

    def test_record_row_is_idempotent(self) -> None:
        self.use([entry("world cowboy", "0xcb83dd8dcba537f5"), self.beach])
        self.assertEqual(self.accept("world cowboy")[0], 0)
        first_rows = [line for line in self.md_text().splitlines() if line.startswith("| 2026")]
        baseline_bytes = self.baseline.read_bytes()
        code, out, _ = self.accept("world cowboy")
        self.assertEqual(code, 0, out)
        self.assertIn("already recorded", out)
        second_rows = [line for line in self.md_text().splitlines() if line.startswith("| 2026")]
        self.assertEqual(len(first_rows), 1)
        self.assertEqual(first_rows, second_rows)
        self.assertEqual(self.baseline.read_bytes(), baseline_bytes)

    def test_record_document_created_when_missing(self) -> None:
        self.assertFalse(self.log.exists())
        self.use([entry("world cowboy", "0xcb83dd8dcba537f5"), self.beach])
        self.assertEqual(self.accept("world cowboy")[0], 0)
        self.assertTrue(self.log.exists())
        self.assertTrue(self.md_text().lstrip().startswith("#"))
        self.assertIn("## 冒烟基线变更记录", self.md_text())

    def test_record_appended_to_existing_table(self) -> None:
        self.log.write_text(
            "# 原生客户端基线\n\n## 冒烟基线变更记录\n\n"
            f"{R.TABLE_HEADER}\n{R.TABLE_RULE}\n"
            "| 2026-11-20T00:00:00Z | `world beach` | `0x1` | `0x2` | earlier |\n\n## 下一节\n",
            encoding="utf-8",
        )
        self.use([entry("world cowboy", "0xcb83dd8dcba537f5"), self.beach])
        self.assertEqual(self.accept("world cowboy")[0], 0)
        text = self.md_text()
        rows = [line for line in text.splitlines() if line.startswith("| 2026")]
        self.assertEqual(len(rows), 2)
        self.assertIn("`world cowboy`", rows[1])
        self.assertLess(text.index("earlier"), text.index("rail carts moved the row"))
        self.assertIn("## 下一节", text)  # later sections survive the insert

    def test_record_keeps_crlf_document_crlf(self) -> None:
        self.log.write_bytes(
            ("# 基线\r\n\r\n## 冒烟基线变更记录\r\n\r\n"
             f"{R.TABLE_HEADER}\r\n{R.TABLE_RULE}\r\n").encode("utf-8")
        )
        self.use([entry("world cowboy", "0xcb83dd8dcba537f5"), self.beach])
        self.assertEqual(self.accept("world cowboy")[0], 0)
        raw = self.log.read_bytes()
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))  # no bare LF anywhere
        self.assertIn(b"`world cowboy`", raw)

    def test_record_keeps_lf_document_lf(self) -> None:
        self.log.write_bytes("# 基线\n".encode("utf-8"))
        self.use([entry("world cowboy", "0xcb83dd8dcba537f5"), self.beach])
        self.assertEqual(self.accept("world cowboy")[0], 0)
        raw = self.log.read_bytes()
        self.assertNotIn(b"\r", raw)

    # -- 7. added / missing scenarios -----------------------------------
    def test_added_and_missing_are_reported(self) -> None:
        fresh = entry("kongfu_1 5x9", "0xabcdef0123456789")
        self.use([self.cowboy, fresh])
        code, out, _ = self.run_main("--check")
        self.assertEqual(code, 1)
        self.assertIn("+ added    kongfu_1 5x9", out)
        self.assertIn("- missing  world beach", out)

    def test_accept_added_and_missing_rewrites_the_list(self) -> None:
        fresh = entry("kongfu_1 5x9", "0xabcdef0123456789")
        self.use([self.cowboy, fresh])
        self.assertEqual(self.run_main("--accept", "kongfu_1 5x9,world beach",
                                       "--reason", "probe renamed")[0], 0)
        doc = json.loads(self.baseline.read_text(encoding="utf-8"))
        self.assertEqual([e["name"] for e in doc["scenarios"]], ["world cowboy", "kongfu_1 5x9"])
        self.assertEqual(self.run_main("--check")[0], 0)
        text = self.md_text()
        self.assertIn("| `(new)` |", text)
        self.assertIn("| `(removed)` |", text)

    # -- 8. list ---------------------------------------------------------
    def test_list_shows_baseline_and_current(self) -> None:
        self.use([entry("world cowboy", "0xcb83dd8dcba537f5"), self.beach])
        code, out, _ = self.run_main("--list")
        self.assertEqual(code, 0)
        self.assertIn("! world cowboy", out)
        self.assertIn("baseline=0xeb036737659cbc46", out)
        self.assertIn("current=0xcb83dd8dcba537f5", out)
        self.assertIn(" baseline=0x4546274cc13f33a8", out)

    # -- 9. reuse a report another step wrote (--from) -------------------
    def test_from_reuses_a_report_without_running_the_gate(self) -> None:
        report = self.baseline.parent / "fresh.json"
        report.write_bytes(R.render({"scenarios": [self.cowboy, self.beach]}).encode("utf-8"))
        R.collect = lambda *a, **k: self.fail("--from must not run the gate")
        code, out, _ = self.run_main("--check", "--from", str(report))
        self.assertEqual(code, 0, out)
        self.assertIn("no change", out)

    def test_from_reports_drift_from_a_saved_report(self) -> None:
        report = self.baseline.parent / "fresh.json"
        report.write_bytes(R.render({"scenarios": [entry("world cowboy", "0xcb83dd8dcba537f5"),
                                                   self.beach]}).encode("utf-8"))
        code, out, _ = self.run_main("--check", "--from", str(report))
        self.assertEqual(code, 1)
        self.assertIn("world cowboy", out)

    def test_from_missing_file_exits_two(self) -> None:
        code, _, err = self.run_main("--check", "--from", str(self.baseline.parent / "nope.json"))
        self.assertEqual(code, 2)
        self.assertIn("smoke baseline:", err)

    # -- 10. broken baseline ---------------------------------------------
    def test_missing_baseline_exits_two(self) -> None:
        self.baseline.unlink()
        self.use([self.cowboy])
        code, _, err = self.run_main("--check")
        self.assertEqual(code, 2)
        self.assertIn("smoke baseline:", err)
        self.assertIn("engine_smoke.json", err)

    def test_malformed_baseline_exits_two(self) -> None:
        self.baseline.write_text("{\"scenarios\": 3}", encoding="utf-8")
        self.use([self.cowboy])
        code, _, err = self.run_main("--check")
        self.assertEqual(code, 2)
        self.assertIn("no scenarios array", err)

    def test_baseline_without_names_exits_two(self) -> None:
        self.baseline.write_text("{\"scenarios\": [{\"hash\": \"0x1\"}]}", encoding="utf-8")
        self.use([self.cowboy])
        code, _, err = self.run_main("--check")
        self.assertEqual(code, 2)
        self.assertIn("no name", err)


if __name__ == "__main__":
    unittest.main()
