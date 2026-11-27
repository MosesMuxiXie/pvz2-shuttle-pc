#!/usr/bin/env python3
"""D5: keep the headless screenshot hashes under version control instead of prose.

The nine `--*-screen` / `--battle-snapshot` commands each render one frame and can write a PNG.
Their byte counts and SHA-256 used to live in review documents, so every real change had to be
copy-pasted by hand and nobody could tell "this frame was supposed to change" from "this frame
regressed". This tool turns them into one recorded artifact:

    python tools/snapshot_baseline.py --check            # exit 1 when a frame moved
    python tools/snapshot_baseline.py --list             # what is recorded, and the command
    python tools/snapshot_baseline.py --accept menu --reason "menu grew from 3 to 8 items"

`--check` runs every scene into a temporary directory and compares bytes + sha256 + size against
`native/generated/snapshot_baseline.json`. The PNG itself is never stored (nine frames are ~4 MB);
only the hash, the byte count and the pixel size are kept, which is enough to prove "same frame".

`--accept` re-anchors only the scenes you name, and appends one row per accepted scene to the
"截图基线变更记录" table in `docs/PARITY_BASELINE.md` — the same contract `smoke_rebaseline.py`
uses for the smoke matrix, including its idempotence rule: the same (scene, new sha256) pair is
never recorded twice.

Each recorded `command` is a full argv line that works when run from the repository root, so a
human can paste it and get the same PNG. `--exe` swaps the executable at run time (a teammate may
be holding the default binary broken), and `--from` reuses a report another step already wrote so
a gate does not render nine frames twice.

Exit codes: 0 clean, 1 drift (or self-check failure), 2 usage or a broken baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "native" / "generated" / "snapshot_baseline.json"
RECORD_DOC = REPO / "docs" / "PARITY_BASELINE.md"

FORMAT = "pvz2-shuttle/snapshot-baseline@1"
REPORT_FORMAT = "pvz2-shuttle/snapshot-report@1"
GENERATED = "snapshot-baseline@1"
HEADING = "截图基线变更记录"
TABLE_HEADER = "| 时间（UTC） | 场景 | 旧 sha256 | 新 sha256 | 原因 |"
TABLE_RULE = "| --- | --- | --- | --- | --- |"

#: The canonical binary. Deliberately the gate build the report names, not a private tree; a
#: broken default is handled with `--exe`, never by editing the stored commands.
DEFAULT_EXE = "build/desktop-gate/Release/PvZ2SHUTTLE.exe"
#: Relative to the repository root, so the stored commands run verbatim from there.
ASSETS = "../../PvZ2SHUTTLE/assets"

#: scene -> (argv after the executable, note). The snapshot path is appended by `argv_with_out`,
#: never baked in here: eight scenes take it as the value of `--snapshot`, while `--battle-snapshot`
#: takes it as a plain third operand (its middle argument is the asset root, and it rejects a sixth
#: token with `invalid battle preview arguments`).
SCENES: "dict[str, tuple[list[str], str]]" = {
    "menu": (
        ["--menu", "content", "--assets", ASSETS, "--frames", "3"],
        "S4 主菜单一帧；菜单项从 3 项增到 8 项后 rect 位置整体变化",
    ),
    "worldmap-screen": (
        ["--worldmap-screen", "content", "--assets", ASSETS, "--frames", "3"],
        "世界地图：选中世界与星数来自存档，默认空存档",
    ),
    "level-select": (
        ["--level-select", "content", "--world", "egypt", "--assets", ASSETS, "--frames", "3"],
        "埃及关卡列表；关卡徽章与已通关标记影响像素",
    ),
    "battle-snapshot": (
        ["--battle-snapshot", "content", ASSETS],
        "战斗首帧（--battle-snapshot 的第三参数是资源根，不是关卡 id）",
    ),
    "almanac": (
        ["--almanac", "content", "--assets", ASSETS, "--frames", "3"],
        "图鉴植物页首屏",
    ),
    "garden": (
        ["--garden", "content", "--assets", ASSETS, "--frames", "3"],
        "花园场景；植物列表来自存档",
    ),
    "achievements": (
        ["--achievements", "content", "--assets", ASSETS, "--frames", "3"],
        "成就页第 0 页；metagame.json 缺失时用 shipped 模型",
    ),
    "daily": (
        ["--daily", "content", "--assets", ASSETS, "--frames", "3"],
        "每日挑战页第 0 页",
    ),
    "settings": (
        ["--settings", "content", "--assets", ASSETS, "--frames", "3"],
        "设置页；音量滑块的默认值来自存档，空存档走默认",
    ),
}

#: Scenes whose output path is a positional operand instead of the value of `--snapshot`.
POSITIONAL_OUT = frozenset({"battle-snapshot"})

#: Scenes that render differently from run to run, so a byte-exact gate would fail on every run.
#:
#: `--battle-snapshot` runs `runBattlePreview()`, which plants a fixed field, steps the world 1800
#: fixed ticks (`runDemo`), then advances **once by real elapsed time**:
#: `battle_view.cpp:252 advanceFrame()` → `world_->advance(std::min(SDL_GetTicksNS() - previousNs_, 0.25))`.
#: Asset loading and process start-up land in that delta, so the recorded frame is a few ticks ahead
#: or behind. Measured on 2026-11-26 (six runs of `--battle-snapshot`, snap3 build): 5 distinct
#: sha256 among six renders. Eight scenes were byte-identical across the same six runs.
#:
#: They are still rendered and recorded — the hash documents what the last run produced — but
#: `--check` reports them as unstable instead of failing on them. Making this gateable needs a
#: fixed-step smoke advance in `battle_view.cpp`, which is outside this tool's write scope.
UNSTABLE = frozenset({"battle-snapshot"})


class BaselineError(RuntimeError):
    """Anything that makes the numbers unusable; always exit code 2."""


# ------------------------------------------------------------------ measurement


def png_size(path: Path) -> "tuple[int, int]":
    """(width, height) from the IHDR chunk; fails loudly on a truncated or non-PNG file."""
    with path.open("rb") as handle:
        head = handle.read(33)
    if len(head) < 33 or head[:8] != b"\x89PNG\r\n\x1a\n":
        raise BaselineError(f"snapshot: {path}: not a PNG")
    if head[12:16] != b"IHDR":
        raise BaselineError(f"snapshot: {path}: first chunk is not IHDR")
    width, height = struct.unpack(">II", head[16:24])
    if width == 0 or height == 0:
        raise BaselineError(f"snapshot: {path}: zero-sized image")
    return width, height


def measure(path: Path) -> dict:
    data = path.read_bytes()
    width, height = png_size(path)
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "width": width,
        "height": height,
    }


# ------------------------------------------------------------------- the scenes


def argv_with_out(scene: str, exe: str, out: str) -> "list[str]":
    """The full argv for one scene, with `out` placed the way that scene's CLI expects it."""
    flag = [] if scene in POSITIONAL_OUT else ["--snapshot"]
    return [exe, *SCENES[scene][0], *flag, out]


def command_for(scene: str, exe: str = DEFAULT_EXE, out: str = "") -> str:
    """The recorded argv line, with the snapshot path filled in.

    The default output lives under `build/snapshots/`, the same directory `--out` defaults to, so a
    recorded line runs verbatim from the repo root.
    """
    return " ".join(argv_with_out(scene, exe, out or f"build/snapshots/{scene}.png"))


def collect(exe: str, out_dir: Path, runner=None, record_exe: str = "") -> dict:
    """Render every scene into `out_dir` and measure the PNGs.

    `exe` is what actually runs (an absolute path when the caller resolved one); `record_exe` is
    what goes into the stored command, so a repo-relative default stays repo-relative and every
    recorded line runs verbatim from the repository root. `runner` is the seam the tests use: it
    receives (argv, out_path) and must produce the PNG.

    The returned report also carries `exe_used`, the binary that really rendered this run. It is
    deliberately **not** stored in the baseline: that file must not churn just because someone
    rebuilt the client on another machine. Provenance belongs in the review report and in the
    `--reason` of the record row.
    """
    if not Path(exe).is_file():
        raise BaselineError(f"snapshot: executable not found: {exe}")
    recorded = record_exe or DEFAULT_EXE
    out_dir.mkdir(parents=True, exist_ok=True)
    scenes: "dict[str, dict]" = {}
    for scene in SCENES:
        png = out_dir / f"{scene}.png"
        if png.exists():
            png.unlink()
        argv = argv_with_out(scene, exe, str(png))
        if runner is None:
            _run(argv, scene)
        else:
            runner(argv, png)
        if not png.is_file():
            raise BaselineError(f"snapshot: {scene}: {exe} produced no {png.name} (exit 0)")
        entry = measure(png)
        entry["command"] = command_for(scene, exe=recorded)
        entry["note"] = SCENES[scene][1]
        if scene in UNSTABLE:
            entry["stable"] = False
            entry["note"] += "（实时推进：跨进程不稳定，不参与 --check 门禁，见 UNSTABLE）"
        scenes[scene] = entry
    return {
        "format": REPORT_FORMAT,
        "generated": GENERATED,
        "exe": recorded,
        "exe_used": str(exe),
        "scenes": scenes,
    }


def _run(argv: "list[str]", scene: str) -> None:
    # The client prints UTF-8 Chinese JSON; without an explicit codec a GBK console default makes
    # the reader threads die mid-capture and hides the real diagnostic.
    completed = subprocess.run(
        argv, cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600,
    )
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip().splitlines()
        detail = tail[-1] if tail else "no output"
        raise BaselineError(f"snapshot: {scene}: exit {completed.returncode}: {detail}")


# ---------------------------------------------------------------- baseline file


def read_text(path: Path) -> str:
    # newline="" keeps a CRLF document's CRLF, so editing it does not rewrite every line.
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def load(path: Path) -> dict:
    if not path.is_file():
        raise BaselineError(f"snapshot baseline: {path}: missing; run --accept <scene> first")
    try:
        doc = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise BaselineError(f"snapshot baseline: {path}: not valid JSON: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("scenes"), dict):
        raise BaselineError(f"snapshot baseline: {path}: no scenes object")
    for name, entry in doc["scenes"].items():
        if not isinstance(entry, dict):
            raise BaselineError(f"snapshot baseline: {path}: scene {name} is not an object")
        for key in ("command", "bytes", "sha256", "width", "height"):
            if key not in entry:
                raise BaselineError(f"snapshot baseline: {path}: scene {name} has no {key}")
        if not str(entry["sha256"]):
            raise BaselineError(f"snapshot baseline: {path}: scene {name} has an empty sha256")
    return doc


def render(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def write_text_lf(path: Path, text: str) -> None:
    """Write UTF-8 with LF only.

    Every file this tool touches is checked in and shared over Windows drives that happily turn
    `\\n` into `\\r\\n`; a baseline that flips line endings diffs forever across the team.
    """
    if "\r" in text:
        raise BaselineError(f"snapshot baseline: {path}: refusing to write CRLF")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def write_baseline(path: Path, report: dict) -> None:
    write_text_lf(path, render(report))


# ------------------------------------------------------------------------ diff


class Diff:
    def __init__(self) -> None:
        self.changed: "dict[str, dict[str, tuple]]" = {}
        self.missing: "list[str]" = []
        self.added: "list[str]" = []
        self.unstable: "list[str]" = []

    @property
    def names(self) -> "list[str]":
        return [*self.added, *self.changed, *self.missing]

    @property
    def empty(self) -> bool:
        return not (self.added or self.changed or self.missing)

    def __len__(self) -> int:
        return len(self.added) + len(self.changed) + len(self.missing)


def diff(baseline: dict, current: dict) -> Diff:
    old = {str(k): v for k, v in baseline["scenes"].items()}
    now = {str(k): v for k, v in current["scenes"].items()}
    out = Diff()
    for name, entry in now.items():
        if name not in old:
            out.added.append(name)
            continue
        before = old[name]
        if before.get("stable") is False:
            # Measured unstable: the frame depends on wall-clock time, so a sha256 gate would cry
            # wolf on every run. It is still rendered and recorded — see `UNSTABLE`.
            out.unstable.append(name)
            continue
        fields = {
            key: (before[key], entry[key])
            for key in ("bytes", "sha256", "width", "height")
            if before.get(key) != entry.get(key)
        }
        if fields:
            out.changed[name] = fields
    out.missing = [name for name in old if name not in now]
    return out


def describe(result: Diff, baseline: dict, current: dict) -> "list[str]":
    old = baseline["scenes"]
    now = current["scenes"]
    lines: "list[str]" = []
    for name in result.added:
        lines.append(f"+ new      {name:16s} bytes={now[name]['bytes']:>8}  sha256={now[name]['sha256'][:16]}")
    for name in result.missing:
        lines.append(f"- missing  {name:16s} bytes={old[name]['bytes']:>8}  sha256={old[name]['sha256'][:16]}")
    for name, fields in result.changed.items():
        before_bytes, after_bytes = fields.get("bytes", (old[name]["bytes"], now[name]["bytes"]))
        before_sha, after_sha = fields.get("sha256", (old[name]["sha256"], now[name]["sha256"]))
        extra = "".join(
            f"  {key} {fields[key][0]}->{fields[key][1]}"
            for key in ("width", "height")
            if key in fields
        )
        lines.append(
            f"~ changed  {name:16s} bytes {before_bytes} -> {after_bytes}  "
            f"sha256 {str(before_sha)[:16]} -> {str(after_sha)[:16]}{extra}"
        )
    for name in result.unstable:
        entry = now.get(name) or old.get(name) or {}
        lines.append(
            f"= unstable {name:16s} bytes={entry.get('bytes', 0):>8}  "
            f"sha256={str(entry.get('sha256', ''))[:16]}  (not gated: renders differ run to run)"
        )
    return lines


# ---------------------------------------------------------------- change record


def _eol_of(text: str) -> str:
    """Keep the document's own line ending: mixed files diff badly."""
    return "\r\n" if "\r\n" in text else "\n"


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def row_for(name: str, before: object, after: object, reason: str, stamp: str) -> str:
    return (
        f"| {_cell(stamp)} | `{_cell(name)}` | `{_cell(before)}` | `{_cell(after)}` "
        f"| {_cell(reason)} |"
    )


def recorded_rows(text: str) -> "list[tuple[str, str]]":
    """(scene, new sha256) pairs already in the record table."""
    seen: "list[tuple[str, str]]" = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("|") or stripped.startswith("| 时间"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or set(cells[0]) <= set("- "):
            continue
        seen.append((cells[1].strip("`"), cells[3].strip("`")))
    return seen


def insert_rows(text: str, rows: "list[str]") -> str:
    """Append rows to the record table, creating the section when it is absent."""
    eol = _eol_of(text)
    if not rows:
        return text
    heading = f"## {HEADING}"
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == heading), -1)
    if start < 0:
        block = ["", heading, "", TABLE_HEADER, TABLE_RULE, *rows]
        return text + eol + eol.join(block) + eol
    cursor = start + 1
    while cursor < len(lines) and not lines[cursor].lstrip().startswith("|"):
        cursor += 1
    if cursor >= len(lines):  # heading but no table yet
        block = ["", TABLE_HEADER, TABLE_RULE, *rows]
        lines[cursor:cursor] = block
    else:
        end = cursor + 1
        while end < len(lines) and lines[end].lstrip().startswith("|"):
            end += 1
        lines[end:end] = rows
    return eol.join(lines) + eol


def record(path: Path, entries: "list[dict]", stamp: str) -> "list[str]":
    """Write the change rows. Returns the scenes actually recorded (idempotent)."""
    text = read_text(path) if path.is_file() else "# 原生客户端基线\n"
    seen = recorded_rows(text)
    fresh: "list[str]" = []
    written: "list[str]" = []
    for entry in entries:
        if (entry["name"], str(entry["after"])) in seen:
            continue
        fresh.append(row_for(entry["name"], entry["before"], entry["after"], entry["reason"], stamp))
        written.append(entry["name"])
    if fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(insert_rows(text, fresh).encode("utf-8"))
    return written


# -------------------------------------------------------------------- commands


def _split_ids(values: "list[str] | None") -> "list[str]":
    names: "list[str]" = []
    for value in values or []:
        for part in str(value).split(","):
            name = part.strip()
            if name and name not in names:
                names.append(name)
    return names


def _current(args: argparse.Namespace) -> dict:
    """Today's numbers: rendered now, or a report another step already wrote."""
    if args.from_path:
        return load_report(Path(args.from_path))
    out = Path(args.out) if getattr(args, "out", "") else Path(tempfile.mkdtemp(prefix="snapshot-"))
    return collect(args.exe, out)


def load_report(path: Path) -> dict:
    if not path.is_file():
        raise BaselineError(f"snapshot report: {path}: missing")
    try:
        doc = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        raise BaselineError(f"snapshot report: {path}: not valid JSON: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("scenes"), dict):
        raise BaselineError(f"snapshot report: {path}: no scenes object")
    return doc


def cmd_check(args: argparse.Namespace) -> int:
    baseline = load(Path(args.baseline))
    current = _current(args)
    result = diff(baseline, current)
    for line in describe(result, baseline, current):
        print(line)
    if result.empty:
        print(f"snapshot baseline: {len(current['scenes'])} scenes, no change"
              + (f" ({len(result.unstable)} unstable, not gated: {', '.join(result.unstable)})"
                 if result.unstable else ""))
        return 0
    print(f"snapshot baseline: {len(result)} scene(s) differ from {Path(args.baseline)}")
    print('re-anchor the ones you caused: --accept "<scene>[,<scene>]" --reason "<why>"')
    return 1


def cmd_list(args: argparse.Namespace) -> int:
    baseline = load(Path(args.baseline)) if Path(args.baseline).is_file() else {"scenes": {}}
    print(f"snapshot baseline: {len(SCENES)} scenes defined, {len(baseline['scenes'])} recorded")
    print(f"  exe: {DEFAULT_EXE}   (override with --exe)")
    for scene in SCENES:
        entry = baseline["scenes"].get(scene)
        mark = " " if entry else "!"
        if scene in UNSTABLE:
            mark = "~"
        stamp = (
            f"bytes={entry['bytes']:>8}  sha256={entry['sha256'][:16]}  {entry['width']}x{entry['height']}"
            if entry
            else "not recorded"
        )
        print(f"{mark} {scene:16s} {stamp}"
              + ("  [unstable]" if scene in UNSTABLE else ""))
        print(f"    {command_for(scene)}")
    if UNSTABLE:
        print(f"  ~ = renders differ run to run, recorded but not gated: {', '.join(sorted(UNSTABLE))}")
    return 0


def cmd_accept(args: argparse.Namespace) -> int:
    names = _split_ids(args.accept)
    if not names:
        print("snapshot baseline: --accept needs at least one scene name", file=sys.stderr)
        return 2
    reason = (args.reason or "").strip()
    if not reason:
        print('snapshot baseline: --accept requires --reason "<why this frame changed>"', file=sys.stderr)
        return 2
    unknown = [name for name in names if name not in SCENES]
    if unknown:
        print(f"snapshot baseline: unknown scene(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"  known: {', '.join(SCENES)}", file=sys.stderr)
        return 2

    path = Path(args.baseline)
    baseline = load(path) if path.is_file() else {
        "format": FORMAT, "generated": GENERATED, "exe": DEFAULT_EXE, "scenes": {},
    }
    current = _current(args)
    result = diff(baseline, current)

    seen = recorded_rows(read_text(Path(args.log))) if Path(args.log).is_file() else []
    entries: "list[dict]" = []
    already: "list[str]" = []
    unchanged: "list[str]" = []
    schema: "list[str]" = []
    for name in names:
        if name in UNSTABLE:
            # An unstable frame is never "changed" — `diff()` skips it — so accepting one always
            # means "record whatever this run produced". That keeps the number in the baseline
            # fresh and leaves one row per accept in the record table.
            #
            # A baseline written before the flag existed needs the flag itself stored; that is a
            # schema repair, not a pixel change, so it rewrites the entry without a record row.
            if baseline["scenes"].get(name, {}).get("stable") is not False:
                schema.append(name)
            before = baseline["scenes"].get(name, {}).get("sha256", "(new)")
            after = current["scenes"].get(name, {}).get("sha256", "(removed)")
            if (name, after) in seen:
                already.append(name)
            else:
                entries.append({"name": name, "before": before, "after": after, "reason": reason})
        elif name in result.changed:
            fields = result.changed[name]
            # A frame that only changed size or dimensions cannot happen without a new sha256, so
            # fall back to the recorded/current pair rather than KeyError on a hand-edited JSON.
            before, after = fields.get(
                "sha256",
                (
                    baseline["scenes"][name]["sha256"],
                    current["scenes"][name]["sha256"],
                ),
            )
            entries.append({"name": name, "before": before, "after": after, "reason": reason})
        elif name in result.added or name in result.missing:
            before = baseline["scenes"].get(name, {}).get("sha256", "(new)")
            after = current["scenes"].get(name, {}).get("sha256", "(removed)")
            entries.append({"name": name, "before": before, "after": after, "reason": reason})
        else:
            # The frame already matches the baseline. Record it only if the table has never seen
            # this very pair, so re-running the same accept stays silent.
            entry = current["scenes"][name]
            if (name, entry["sha256"]) in seen:
                already.append(name)
            else:
                unchanged.append(name)
    if unchanged and not entries and not schema:
        print(f"snapshot baseline: baseline already matches; nothing to accept: {', '.join(unchanged)}",
              file=sys.stderr)
        return 2
    if not entries and not schema:
        print(f"snapshot baseline: already recorded, baseline unchanged: {', '.join(already or names)}")
        return 0
    if schema and not entries:
        write_baseline(path, _apply(baseline, current, set(schema)))
        print(f"snapshot baseline: stored the instability flag for {', '.join(schema)}"
              f" (schema repair, no frame changed)")
        return 0

    updated = _apply(baseline, current, {e["name"] for e in entries} | set(schema))
    stamp = args.timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_baseline(path, updated)
    written = record(Path(args.log), entries, stamp)

    reloaded = load(path)
    after = diff(reloaded, current)
    still = [e["name"] for e in entries if e["name"] in after.names]
    if still:
        print(f"snapshot baseline: self-check failed, still different: {', '.join(still)}",
              file=sys.stderr)
        return 1
    for line in describe(after, reloaded, current):
        print(line)
    print(f"accepted {len(entries)} scene(s) into {path}"
          f" ({len(written)} new record row{'s' if len(written) != 1 else ''} in {Path(args.log)})")
    if after.empty:
        print("self-check: baseline matches this run; --check now exits 0")
    else:
        print(f"remaining drift not accepted: {len(after)} scene(s); --check still exits 1")
    return 0


def _apply(baseline: dict, current: dict, names: "set[str]") -> dict:
    scenes = {
        name: (current["scenes"][name] if name in names else entry)
        for name, entry in baseline["scenes"].items()
        if name in current["scenes"] or name not in names
    }
    for name in names:
        if name not in baseline["scenes"] and name in current["scenes"]:
            scenes[name] = current["scenes"][name]
    doc = dict(baseline)
    doc["format"] = FORMAT
    doc["generated"] = GENERATED
    doc.setdefault("exe", current.get("exe", DEFAULT_EXE))
    doc["scenes"] = {name: scenes[name] for name in sorted(scenes)}
    return doc


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="render every scene and diff it; exit 1 on drift")
    mode.add_argument("--accept", action="append", metavar="SCENE[,SCENE...]",
                      help="re-anchor the named scenes (repeatable, comma separated)")
    mode.add_argument("--list", action="store_true", help="show the scenes, their commands and hashes")
    parser.add_argument("--reason", default="", help="why the named scenes changed; required by --accept")
    parser.add_argument("--exe", default=DEFAULT_EXE,
                        help=f"executable to render with (default {DEFAULT_EXE}, resolved from the repo root)")
    parser.add_argument("--baseline", default=str(BASELINE))
    parser.add_argument("--log", default=str(RECORD_DOC))
    parser.add_argument("--out", default=str(REPO / "build" / "snapshots"),
                        help="directory for --check's freshly rendered PNGs")
    parser.add_argument("--report", default="",
                        help="also write today's numbers as JSON (reusable with --from)")
    parser.add_argument("--timestamp", default="", help="ISO-8601 UTC stamp for the record row")
    parser.add_argument("--from", dest="from_path", default="",
                        help="compare an existing report instead of rendering the scenes again")
    args = parser.parse_args(argv)

    try:
        if args.exe and not Path(args.exe).is_absolute():
            # A repo-relative `--exe` is resolved for the process so `--check` works from any
            # working directory; the stored command always names DEFAULT_EXE, so it stays
            # runnable verbatim from the repository root.
            args.exe = str((REPO / args.exe).resolve()) if (REPO / args.exe).is_file() else args.exe
        if args.list:
            return cmd_list(args)
        if args.accept:
            return cmd_accept(args)
        if args.report and not args.from_path:
            report = collect(args.exe, Path(args.out))
            write_baseline(Path(args.report), {**report, "format": REPORT_FORMAT})
            baseline = load(Path(args.baseline)) if Path(args.baseline).is_file() else {"scenes": {}}
            result = diff(baseline, report)
            for line in describe(result, baseline, report):
                print(line)
            if result.empty:
                print(f"snapshot baseline: {len(report['scenes'])} scenes, no change")
                return 0
            print(f"snapshot baseline: {len(result)} scene(s) differ from {Path(args.baseline)}")
            return 1
        return cmd_check(args)
    except BaselineError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired as exc:
        print(f"snapshot: timed out after {exc.timeout}s: {shlex.join(exc.cmd or [])}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
