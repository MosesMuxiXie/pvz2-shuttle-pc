#!/usr/bin/env python3
"""Tests for tools/snapshot_baseline.py.

Run:  python tools/tests/test_snapshot_baseline.py

The screenshot baseline itself needs a desktop binary with SDL (the audit build cannot write a
PNG), which makes it a bad thing for a unit test to depend on. Every case here therefore goes
through one of two seams:

* `snapshot_baseline.collect(..., runner=...)` — the runner draws the PNG instead of spawning the
  game, so the recording, measuring and diffing paths run for real;
* `--from <report>` — the CLI reads a report the runner produced, so `--check` / `--accept` and
  their exit codes are exercised without any process at all.

The one case that does spawn the real binary (`RealRenderTests`) only runs when `SNAPSHOT_EXE`
points at a desktop build.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import snapshot_baseline as sb  # noqa: E402


# --------------------------------------------------------------------------- helpers


def png_bytes(width: int = 8, height: int = 6, salt: bytes = b"") -> bytes:
    """A structurally valid PNG. `salt` changes the bytes but not the reading of the header."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes([0]) * (width * height * 4))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"") + salt


class Fixture(unittest.TestCase):
    """Temp dir, a fake executable and a runner that writes the frames."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="snapshot-test-")
        self.root = Path(self._tmp.name)
        self.repo_exe = self.root / "FakeGame.exe"
        self.repo_exe.write_bytes(b"MZ fake")
        self.out = self.root / "frames"
        self.baseline = self.root / "snapshot_baseline.json"
        self.log = self.root / "PARITY_BASELINE.md"
        self.report = self.root / "report.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -- seams -----------------------------------------------------------------

    def runner(self, salts: "dict[str, str] | None" = None, size: "tuple[int, int]" = (8, 6)):
        """One frame per scene; `salts[scene]` changes exactly that scene's bytes."""

        def run(argv, png: Path) -> None:
            salt = (salts or {}).get(png.stem, "")
            png.write_bytes(png_bytes(size[0], size[1], salt.encode()))

        return run

    def collect(self, salts: "dict[str, str] | None" = None, size: "tuple[int, int]" = (8, 6)) -> dict:
        return sb.collect(
            str(self.repo_exe), self.out, runner=self.runner(salts, size), record_exe="build/x.exe"
        )

    def write_report(self, report: dict) -> Path:
        self.report.write_text(sb.render(report), encoding="utf-8", newline="")
        return self.report

    def cli(self, *argv: str) -> "tuple[int, str, str]":
        """Run main() and capture (exit, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = sb.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def seed_baseline(
        self, salts: "dict[str, str] | None" = None, size: "tuple[int, int]" = (8, 6)
    ) -> dict:
        report = self.collect(salts, size)
        sb.write_baseline(self.baseline, report)
        return report


# ------------------------------------------------------------------- scene catalog


class SceneCatalogTests(Fixture):
    def test_nine_scenes_are_defined(self) -> None:
        expected = {
            "menu",
            "worldmap-screen",
            "level-select",
            "battle-snapshot",
            "almanac",
            "garden",
            "achievements",
            "daily",
            "settings",
        }
        self.assertEqual(set(sb.SCENES), expected)
        for name, (argv, note) in sb.SCENES.items():
            self.assertTrue(argv, f"{name} has no argv")
            self.assertTrue(note.strip(), f"{name} has no note")
            self.assertIn("--", argv[0], f"{name} does not start with a flag")

    def test_every_command_runs_from_the_repo_root(self) -> None:
        for name in sb.SCENES:
            command = sb.command_for(name)
            self.assertTrue(command.startswith(sb.DEFAULT_EXE), command)
            self.assertIn("--assets", command if name != "battle-snapshot" else "--assets", command)
            self.assertTrue(command.endswith(f"build/snapshots/{name}.png"), command)
            # The assets root is the sibling checkout, not something inside this repo.
            self.assertIn("PvZ2SHUTTLE/assets", command)

    def test_snapshot_path_follows_the_snapshot_flag(self) -> None:
        # The CLI parses `--snapshot <path>` as a flag plus its value; a line that drops the flag
        # makes the executable read the path as an unknown option. This is the assertion that
        # would have caught exactly that (the first baseline run failed on it).
        for name in sb.SCENES:
            command = sb.command_for(name)
            if name in sb.POSITIONAL_OUT:
                continue
            self.assertIn(f" --snapshot build/snapshots/{name}.png", command)

    def test_battle_snapshot_takes_the_path_positionally(self) -> None:
        # `--battle-snapshot` wants exactly four operands after the executable; a trailing
        # `--snapshot` makes it 6 argv and the CLI answers `invalid battle preview arguments`.
        self.assertIn("battle-snapshot", sb.POSITIONAL_OUT)
        argv = sb.argv_with_out("battle-snapshot", "exe", "out.png")
        self.assertEqual(argv, ["exe", "--battle-snapshot", "content", sb.ASSETS, "out.png"])
        self.assertNotIn("--snapshot", argv)
        self.assertNotIn("--snapshot", sb.command_for("battle-snapshot"))

    def test_battle_snapshot_passes_the_asset_root(self) -> None:
        # `--battle-snapshot <content> <asset root> <out>`: the second operand must be the assets
        # directory, not a level id — a regression here silently renders the wrong thing.
        argv = sb.SCENES["battle-snapshot"][0]
        self.assertEqual(argv[0], "--battle-snapshot")
        self.assertEqual(argv[1], "content")
        self.assertIn("assets", argv[2])
        self.assertEqual(argv[-1], sb.ASSETS, "the asset root is the last declared operand")

    def test_list_prints_one_block_per_scene(self) -> None:
        code, out, err = self.cli("--list", "--baseline", str(self.baseline))
        self.assertEqual(code, 0, err)
        self.assertIn("9 scenes defined, 0 recorded", out)
        for name in sb.SCENES:
            self.assertIn(name, out)
        self.assertEqual(out.count("build/snapshots/"), 9)


# --------------------------------------------------------------------- measuring


class MeasureTests(Fixture):
    def test_png_size_reads_the_ihdr(self) -> None:
        path = self.root / "wide.png"
        path.write_bytes(png_bytes(37, 11))
        self.assertEqual(sb.png_size(path), (37, 11))

    def test_measure_matches_hashlib(self) -> None:
        path = self.root / "one.png"
        data = png_bytes(9, 4, b"tail")
        path.write_bytes(data)
        entry = sb.measure(path)
        self.assertEqual(entry["bytes"], len(data))
        self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual((entry["width"], entry["height"]), (9, 4))

    def test_non_png_is_refused(self) -> None:
        path = self.root / "not.png"
        path.write_bytes(b"GIF89a" + b"\x00" * 40)
        with self.assertRaises(sb.BaselineError) as ctx:
            sb.png_size(path)
        self.assertIn("not a PNG", str(ctx.exception))

    def test_truncated_png_is_refused(self) -> None:
        path = self.root / "short.png"
        path.write_bytes(png_bytes()[:20])
        with self.assertRaises(sb.BaselineError):
            sb.png_size(path)


# ------------------------------------------------------------------------ collect


class CollectTests(Fixture):
    def test_collect_records_nine_scenes(self) -> None:
        report = self.collect()
        self.assertEqual(report["format"], sb.REPORT_FORMAT)
        self.assertEqual(len(report["scenes"]), 9)
        for name, entry in report["scenes"].items():
            for key in ("command", "bytes", "sha256", "width", "height", "note"):
                self.assertIn(key, entry, f"{name} missing {key}")
            self.assertTrue(entry["command"].startswith("build/x.exe"), entry["command"])
            self.assertEqual(len(entry["sha256"]), 64)

    def test_collect_uses_the_runner_png(self) -> None:
        report = self.collect(size=(21, 13))
        for entry in report["scenes"].values():
            self.assertEqual((entry["width"], entry["height"]), (21, 13))

    def test_missing_exe_is_a_clear_error(self) -> None:
        # The baseline has to exist first: --check reads it before it renders anything, and an
        # unrecorded baseline is a different (also legitimate) exit-2 path.
        self.seed_baseline()
        code, _out, err = self.cli(
            "--check", "--exe", str(self.root / "nope.exe"), "--baseline", str(self.baseline)
        )
        self.assertEqual(code, 2)
        self.assertIn("executable not found", err)
        self.assertIn("nope.exe", err)

    def test_silent_exe_fails_loudly(self) -> None:
        def lazy(argv, png):
            return None  # exits 0 and writes nothing, the classic broken flag

        with self.assertRaises(sb.BaselineError) as ctx:
            sb.collect(str(self.repo_exe), self.out, runner=lazy)
        self.assertIn("produced no", str(ctx.exception))


# ------------------------------------------------------------------ check / accept


class CheckTests(Fixture):
    def test_no_drift_exits_zero(self) -> None:
        report = self.seed_baseline()
        path = self.write_report(report)
        code, out, err = self.cli("--check", "--baseline", str(self.baseline), "--from", str(path))
        self.assertEqual(code, 0, err)
        self.assertIn("9 scenes, no change", out)

    def test_one_changed_byte_is_named(self) -> None:
        before = self.seed_baseline()
        after = self.collect({"menu": "drift"})
        path = self.write_report(after)
        code, out, _err = self.cli("--check", "--baseline", str(self.baseline), "--from", str(path))
        self.assertEqual(code, 1)
        scene = "menu"
        self.assertIn("changed", out)
        self.assertIn(scene, out)
        self.assertIn(before["scenes"][scene]["sha256"][:16], out)
        self.assertIn(after["scenes"][scene]["sha256"][:16], out)
        self.assertIn("1 scene(s) differ", out)

    def test_size_change_is_reported_as_bytes_and_dimensions(self) -> None:
        self.seed_baseline(size=(8, 6))
        path = self.write_report(self.collect(size=(9, 6)))
        code, out, _err = self.cli("--check", "--baseline", str(self.baseline), "--from", str(path))
        self.assertEqual(code, 1)
        self.assertIn("width 8->9", out)

    def test_missing_and_new_scenes_are_reported(self) -> None:
        report = self.seed_baseline()
        trimmed = dict(report)
        trimmed["scenes"] = {k: v for k, v in report["scenes"].items() if k != "menu"}
        trimmed["scenes"]["extra"] = dict(report["scenes"]["garden"])
        path = self.write_report(trimmed)
        code, out, _err = self.cli("--check", "--baseline", str(self.baseline), "--from", str(path))
        self.assertEqual(code, 1)
        self.assertIn("- missing", out)
        self.assertIn("menu", out)
        self.assertIn("+ new", out)
        self.assertIn("extra", out)

    def test_broken_baseline_shape_exits_two(self) -> None:
        report = self.seed_baseline()
        doc = json.loads(self.baseline.read_text(encoding="utf-8"))
        del doc["scenes"]["menu"]["sha256"]
        self.baseline.write_text(json.dumps(doc), encoding="utf-8", newline="")
        path = self.write_report(report)
        code, _out, err = self.cli("--check", "--baseline", str(self.baseline), "--from", str(path))
        self.assertEqual(code, 2)
        self.assertIn("has no sha256", err)

    def test_missing_baseline_exits_two(self) -> None:
        path = self.write_report(self.collect())
        code, _out, err = self.cli("--check", "--baseline", str(self.baseline), "--from", str(path))
        self.assertEqual(code, 2)
        self.assertIn("missing; run --accept", err)

    def test_broken_report_exits_two(self) -> None:
        self.baseline.write_text(sb.render(self.collect()), encoding="utf-8", newline="")
        bad = self.root / "bad.json"
        bad.write_text("{not json", encoding="utf-8", newline="")
        code, _out, err = self.cli("--check", "--baseline", str(self.baseline), "--from", str(bad))
        self.assertEqual(code, 2)
        self.assertIn("not valid JSON", err)


class AcceptTests(Fixture):
    def accept(self, *names: str, reason: str = "menu grew from 3 to 8 items") -> "tuple[int, str, str]":
        argv = ["--accept", ",".join(names), "--baseline", str(self.baseline), "--log", str(self.log),
                "--from", str(self.report), "--timestamp", "2026-11-26T12:34:56Z"]
        if reason:
            argv += ["--reason", reason]
        return self.cli(*argv)

    def test_accept_reanchors_and_check_then_passes(self) -> None:
        before = self.seed_baseline()
        drifted = self.collect({"menu": "rail"})
        self.write_report(drifted)

        code, out, err = self.accept("menu")
        self.assertEqual(code, 0, err)
        self.assertIn("accepted 1 scene(s)", out)
        self.assertIn("--check now exits 0", out)

        reloaded = sb.load(self.baseline)
        self.assertEqual(reloaded["scenes"]["menu"]["sha256"], drifted["scenes"]["menu"]["sha256"])
        # Untouched scenes keep the old hash: accept is per scene, not wholesale.
        other = next(name for name in sb.SCENES if name != "menu")
        self.assertEqual(reloaded["scenes"][other]["sha256"], before["scenes"][other]["sha256"])

        code, out, _err = self.cli("--check", "--baseline", str(self.baseline), "--from", str(self.report))
        self.assertEqual(code, 0, out)

    def test_accept_writes_one_record_row_per_scene(self) -> None:
        before = self.seed_baseline()
        drifted = self.collect({"menu": "rail", "garden": "rail"})
        self.write_report(drifted)
        code, _out, err = self.accept("menu", "garden")
        self.assertEqual(code, 0, err)

        text = self.log.read_text(encoding="utf-8", newline="")
        self.assertIn("## 截图基线变更记录", text)
        self.assertIn("| 时间（UTC） | 场景 | 旧 sha256 | 新 sha256 | 原因 |", text)
        rows = sb.recorded_rows(text)
        self.assertEqual(sorted(name for name, _sha in rows), ["garden", "menu"])
        self.assertIn(("menu", drifted["scenes"]["menu"]["sha256"]), rows)
        self.assertIn(("garden", drifted["scenes"]["garden"]["sha256"]), rows)
        self.assertIn(before["scenes"]["menu"]["sha256"], text)
        self.assertIn("2026-11-26T12:34:56Z", text)
        self.assertIn("menu grew from 3 to 8 items", text)

    def test_accept_is_idempotent(self) -> None:
        self.seed_baseline()
        self.write_report(self.collect({"menu": "rail"}))
        self.assertEqual(self.accept("menu")[0], 0)
        baseline_once = self.baseline.read_bytes()
        log_once = self.log.read_bytes()

        code, out, err = self.accept("menu")
        self.assertEqual(code, 0, err)
        self.assertIn("already recorded", out)
        self.assertEqual(self.baseline.read_bytes(), baseline_once)
        self.assertEqual(self.log.read_bytes(), log_once)
        self.assertEqual(len(sb.recorded_rows(log_once.decode("utf-8"))), 1)

    def test_reason_is_required(self) -> None:
        self.seed_baseline()
        self.write_report(self.collect({"menu": "rail"}))
        code, _out, err = self.accept("menu", reason="")
        self.assertEqual(code, 2)
        self.assertIn("--reason", err)
        # A refused accept must not touch the baseline.
        self.assertEqual(len(sb.load(self.baseline)["scenes"]), 9)

    def test_unknown_scene_is_refused(self) -> None:
        self.seed_baseline()
        self.write_report(self.collect({"menu": "rail"}))
        code, _out, err = self.accept("menu", "no-such-scene")
        self.assertEqual(code, 2)
        self.assertIn("unknown scene(s): no-such-scene", err)

    def test_accepting_a_clean_baseline_says_so(self) -> None:
        report = self.seed_baseline()
        self.write_report(report)
        code, _out, err = self.accept("menu")
        self.assertEqual(code, 2)
        self.assertIn("baseline already matches", err)


# ------------------------------------------------------------ unstable scenes


class UnstableSceneTests(Fixture):
    """`battle-snapshot` advances by wall-clock time (`battle_view.cpp:252`), so it cannot be a
    byte-exact gate. It must still be rendered, recorded and visible — just not fatal."""

    def test_unstable_scene_is_flagged_in_the_record(self) -> None:
        self.assertIn("battle-snapshot", sb.UNSTABLE)
        report = self.collect()
        entry = report["scenes"]["battle-snapshot"]
        self.assertIs(entry["stable"], False)
        self.assertIn("不稳定", entry["note"])
        # A stable scene carries no flag at all, so a hand-edited baseline cannot fake it.
        self.assertNotIn("stable", report["scenes"]["menu"])

    def test_unstable_scene_is_reported_but_not_gated(self) -> None:
        self.seed_baseline()
        self.write_report(self.collect({"battle-snapshot": "drift"}))
        code, out, err = self.cli(
            "--check", "--baseline", str(self.baseline), "--from", str(self.report)
        )
        self.assertEqual(code, 0, out + err)
        self.assertIn("= unstable", out)
        self.assertIn("not gated", out)
        self.assertIn("1 unstable", out)

    def test_stable_scene_still_fails_next_to_an_unstable_one(self) -> None:
        self.seed_baseline()
        self.write_report(self.collect({"battle-snapshot": "drift", "menu": "drift"}))
        code, out, err = self.cli(
            "--check", "--baseline", str(self.baseline), "--from", str(self.report)
        )
        self.assertEqual(code, 1, out + err)
        self.assertIn("~ changed  menu", out)
        self.assertNotIn("~ changed  battle-snapshot", out)

    def test_accept_records_an_unstable_scene_and_stays_idempotent(self) -> None:
        self.seed_baseline()
        current = self.collect({"battle-snapshot": "drift"})
        self.write_report(current)
        argv = (
            "--accept", "battle-snapshot", "--reason", "measured instability",
            "--baseline", str(self.baseline), "--log", str(self.log), "--from", str(self.report),
        )
        code, out, err = self.cli(*argv)
        self.assertEqual(code, 0, out + err)
        rows = sb.recorded_rows(sb.read_text(self.log))
        self.assertEqual(
            rows, [("battle-snapshot", current["scenes"]["battle-snapshot"]["sha256"])]
        )
        # The same frame again: no new row, and the baseline does not move.
        before = self.baseline.read_bytes()
        code2, out2, _err2 = self.cli(*argv)
        self.assertEqual(code2, 0)
        self.assertIn("already recorded", out2)
        self.assertEqual(sb.recorded_rows(sb.read_text(self.log)), rows)
        self.assertEqual(self.baseline.read_bytes(), before)


# --------------------------------------------------------------- record helpers


class RecordTests(Fixture):
    def test_insert_rows_creates_the_section(self) -> None:
        text = "# 原生客户端基线\n\n正文。\n"
        out = sb.insert_rows(text, ["| a | b | c | d | e |"])
        self.assertIn("## 截图基线变更记录", out)
        self.assertIn("| --- | --- | --- | --- | --- |", out)
        self.assertTrue(out.rstrip().endswith("| a | b | c | d | e |"))

    def test_insert_rows_appends_to_an_existing_table(self) -> None:
        text = (
            "# doc\n\n## 截图基线变更记录\n\n"
            "| 时间（UTC） | 场景 | 旧 sha256 | 新 sha256 | 原因 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| old | `menu` | `a` | `b` | 首轮 |\n\n## 后一节\n"
        )
        out = sb.insert_rows(text, ["| new | `menu` | `b` | `c` | 再漂 |"])
        lines = out.splitlines()
        self.assertEqual(lines[6], "| old | `menu` | `a` | `b` | 首轮 |")
        self.assertEqual(lines[7], "| new | `menu` | `b` | `c` | 再漂 |")
        self.assertEqual(lines[8], "")
        self.assertEqual(lines[9], "## 后一节")

    def test_insert_rows_keeps_crlf_documents_crlf(self) -> None:
        text = "# doc\r\n\r\n正文。\r\n"
        out = sb.insert_rows(text, ["| a | b | c | d | e |"])
        self.assertIn("## 截图基线变更记录", out)
        # Every newline in the result still belongs to a CRLF pair.
        self.assertNotIn("\n", out.replace("\r\n", ""))
        self.assertIn("正文。", out)

    def test_recorded_rows_ignores_the_header_and_rule(self) -> None:
        text = (
            "| 时间（UTC） | 场景 | 旧 sha256 | 新 sha256 | 原因 |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| t | `menu` | `aa` | `bb` | why |\n"
        )
        self.assertEqual(sb.recorded_rows(text), [("menu", "bb")])

    def test_record_is_idempotent(self) -> None:
        entry = {"name": "menu", "before": "aa", "after": "bb", "reason": "why"}
        first = sb.record(self.log, [entry], "2026-11-26T00:00:00Z")
        self.assertEqual(first, ["menu"])
        once = self.log.read_bytes()
        second = sb.record(self.log, [entry], "2026-11-26T00:00:00Z")
        self.assertEqual(second, [])
        self.assertEqual(self.log.read_bytes(), once)

    def test_rows_escape_pipes(self) -> None:
        row = sb.row_for("menu", "a", "b", "reason | with pipe", "t")
        self.assertIn("reason \\| with pipe", row)

    def test_write_text_lf_refuses_crlf(self) -> None:
        with self.assertRaises(sb.BaselineError) as ctx:
            sb.write_text_lf(self.root / "x.md", "a\r\nb")
        self.assertIn("refusing to write CRLF", str(ctx.exception))

    def test_written_baseline_has_no_cr(self) -> None:
        sb.write_baseline(self.baseline, self.collect())
        raw = self.baseline.read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertTrue(raw.endswith(b"\n"))


# --------------------------------------------------------------- real render (opt-in)


class RealRenderTests(Fixture):
    """Only meaningful against a desktop build; `SNAPSHOT_EXE` enables it."""

    def setUp(self) -> None:
        super().setUp()
        exe = os.environ.get("SNAPSHOT_EXE", "")
        if not exe:
            self.skipTest("set SNAPSHOT_EXE to a desktop PvZ2SHUTTLE.exe to render real frames")
        self.exe = exe

    def test_all_scenes_render(self) -> None:
        report = sb.collect(self.exe, self.root / "frames", record_exe=sb.DEFAULT_EXE)
        self.assertEqual(len(report["scenes"]), 9)
        for name, entry in report["scenes"].items():
            self.assertGreater(entry["bytes"], 1000, f"{name} is suspiciously small")
            self.assertGreater(entry["width"], 100, name)
            self.assertGreater(entry["height"], 100, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
