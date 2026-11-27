#!/usr/bin/env python3
"""Audited re-anchoring for `native/generated/engine_smoke.json`.

`tools/engine_smoke.py` is the regression gate for `--run-level`: the same level,
seed and script must always produce the same state hash. When the engine really
changes behaviour the baseline has to move with it, and the only honest way to do
that is to say *which* scenarios moved and *why*. This tool is that record:

  --check                 run the gate and diff it against the baseline; exit 1
                          when a scenario was added, dropped or changed
  --accept <id>[,<id>…]   re-anchor only the named scenarios, and append one row
   --reason "<why>"       per accepted scenario to docs/PARITY_BASELINE.md
  --list                  show the baseline and the current run side by side

Everything is deterministic: the baseline is written with `engine_smoke.render`,
the very dumper that produced it, so a no-op `--accept` cannot churn the file.
The change record is keyed on (scenario, new hash) — accepting the same target
twice never appends a second row.

Usage:
    python tools/smoke_rebaseline.py --check [--exe PATH]
    python tools/smoke_rebaseline.py --accept "world cowboy" --reason "rail carts"
    python tools/smoke_rebaseline.py --list
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:  # import the sibling gate, never a copy of it
    sys.path.insert(0, str(TOOLS))

import engine_smoke  # noqa: E402  (same dumper -> byte determinism)

BASELINE = REPO / "native" / "generated" / "engine_smoke.json"
RECORD_DOC = REPO / "docs" / "PARITY_BASELINE.md"
HEADING = "冒烟基线变更记录"
TABLE_HEADER = "| 时间（UTC） | 场景 | 旧 hash | 新 hash | 原因 |"
TABLE_RULE = "| --- | --- | --- | --- | --- |"

# Fields worth printing in a one-line diff; the rest are still compared.
SHOWN = ("tick", "status", "killed", "spawned", "leaked", "mowerKills")


class BaselineError(RuntimeError):
    """The baseline file is missing, unreadable or not the shape we wrote."""


@dataclass
class Diff:
    added: list[dict] = field(default_factory=list)
    missing: list[dict] = field(default_factory=list)
    changed: dict[str, dict[str, tuple[object, object]]] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not (self.added or self.missing or self.changed)

    @property
    def names(self) -> list[str]:
        return [e["name"] for e in self.added] + [e["name"] for e in self.missing] + list(self.changed)

    def __len__(self) -> int:
        return len(self.added) + len(self.missing) + len(self.changed)


# --------------------------------------------------------------------------- io


def collect(exe: Path, content: Path, pack: Path, boards: Path) -> dict:
    """Run the smoke gate. Module-level seam: tests replace it instead of a real exe."""
    return engine_smoke.build_report(exe, content, pack, boards)


def render(report: dict) -> str:
    """The one dumper. Both the gate and this tool must produce identical bytes."""
    return engine_smoke.render(report)


def read_text(path: Path) -> str:
    """Read without newline translation: a CRLF document must stay CRLF on write."""
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()
    except OSError as exc:
        raise BaselineError(f"smoke baseline: {path}: {exc.strerror or exc}") from exc


def load(path: Path) -> dict:
    text = read_text(path)
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BaselineError(f"smoke baseline: {path}: not valid JSON: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("scenarios"), list):
        raise BaselineError(f"smoke baseline: {path}: no scenarios array")
    for entry in doc["scenarios"]:
        if not isinstance(entry, dict) or "name" not in entry:
            raise BaselineError(f"smoke baseline: {path}: a scenario entry has no name")
    return doc


def write_baseline(path: Path, report: dict) -> None:
    text = render(report)
    if "\r" in text:  # the gate writes LF; a CRLF baseline would diff forever
        raise BaselineError(f"smoke baseline: {path}: refusing to write CRLF")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


# ------------------------------------------------------------------------- diff


def diff(baseline: dict, current: dict) -> Diff:
    old = {str(e["name"]): e for e in baseline["scenarios"]}
    now = {str(e["name"]): e for e in current["scenarios"]}
    out = Diff()
    for name, entry in now.items():
        if name not in old:
            out.added.append(entry)
            continue
        before = old[name]
        fields = {k: (before.get(k), entry.get(k)) for k in set(before) | set(entry)}
        fields = {k: v for k, v in fields.items() if v[0] != v[1]}
        if fields:
            out.changed[name] = fields
    out.missing = [e for name, e in old.items() if name not in now]
    return out


def describe(result: Diff) -> list[str]:
    lines: list[str] = []
    for entry in result.added:
        lines.append(f"+ added    {entry['name']:24s} hash={entry.get('hash')}")
    for entry in result.missing:
        lines.append(f"- missing  {entry['name']:24s} hash={entry.get('hash')}")
    for name, fields in result.changed.items():
        before, after = fields.get("hash", ("?", "?"))
        detail = "  ".join(
            f"{key} {fields[key][0]}->{fields[key][1]}" for key in SHOWN if key in fields
        )
        extra = len(fields) - (1 if "hash" in fields else 0) - sum(1 for k in SHOWN if k in fields)
        if extra > 0:
            detail = f"{detail}  (+{extra} more field{'s' if extra != 1 else ''})".strip()
        lines.append(f"~ changed  {name:24s} hash {before} -> {after}  {detail}".rstrip())
    return lines


# ---------------------------------------------------------------- change record


def _eol_of(text: str) -> str:
    """Keep the document's own line ending: mixed files diff badly."""
    return "\r\n" if "\r\n" in text else "\n"


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def row_for(name: str, before: object, after: object, reason: str, stamp: str) -> str:
    return (f"| {_cell(stamp)} | `{_cell(name)}` | `{_cell(before)}` | `{_cell(after)}` "
            f"| {_cell(reason)} |")


def recorded_rows(text: str) -> list[tuple[str, str]]:
    """(scenario, new hash) pairs already in the record table."""
    seen: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|") or line.lstrip().startswith("| 时间"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or set(cells[0]) <= set("- "):
            continue
        seen.append((cells[1].strip("`"), cells[3].strip("`")))
    return seen


def insert_rows(text: str, rows: list[str]) -> str:
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


def record(path: Path, entries: list[dict], stamp: str) -> list[str]:
    """Write the change rows. Returns the scenarios actually written (idempotent)."""
    text = read_text(path) if path.is_file() else "# 原生客户端基线\n"
    seen = recorded_rows(text)
    fresh: list[str] = []
    written: list[str] = []
    for entry in entries:
        key = (entry["name"], str(entry["after"]))
        if key in seen:
            continue
        fresh.append(row_for(entry["name"], entry["before"], entry["after"], entry["reason"], stamp))
        written.append(entry["name"])
    if fresh:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(insert_rows(text, fresh).encode("utf-8"))
    return written


# ------------------------------------------------------------------- commands


def _split_ids(values: list[str] | None) -> list[str]:
    names: list[str] = []
    for value in values or []:
        for part in str(value).split(","):
            name = part.strip()
            if name and name not in names:
                names.append(name)
    return names


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    return (Path(args.exe), Path(args.content), Path(args.pack), Path(args.boards))


def _current(args: argparse.Namespace) -> dict:
    """Today's numbers: either a fresh gate run, or a report another step already wrote."""
    if args.from_path:
        return load(Path(args.from_path))
    return collect(*_paths(args))


def cmd_check(args: argparse.Namespace) -> int:
    baseline = load(Path(args.baseline))
    current = _current(args)
    result = diff(baseline, current)
    for line in describe(result):
        print(line)
    if result.empty:
        print(f"smoke baseline: {len(current['scenarios'])} scenarios, no change")
        return 0
    print(f"smoke baseline: {len(result)} scenario(s) differ from {Path(args.baseline)}")
    print('re-anchor the ones you caused: --accept "<name>[,<name>]" --reason "<why>"')
    return 1


def cmd_list(args: argparse.Namespace) -> int:
    baseline = load(Path(args.baseline))
    current = _current(args)
    old = {str(e["name"]): e.get("hash") for e in baseline["scenarios"]}
    now = {str(e["name"]): e.get("hash") for e in current["scenarios"]}
    for name in sorted(set(old) | set(now)):
        left, right = old.get(name), now.get(name)
        mark = " " if left == right else "!"
        print(f"{mark} {name:24s} baseline={str(left):20s} current={str(right):20s}")
    print(f"smoke baseline: {len(old)} baseline / {len(now)} current")
    return 0


def cmd_accept(args: argparse.Namespace) -> int:
    names = _split_ids(args.accept)
    if not names:
        print("smoke rebaseline: --accept needs at least one scenario name", file=sys.stderr)
        return 2
    reason = (args.reason or "").strip()
    if not reason:
        print('smoke rebaseline: --accept requires --reason "<why this changed>"', file=sys.stderr)
        return 2
    baseline = load(Path(args.baseline))
    current = _current(args)
    result = diff(baseline, current)

    seen = recorded_rows(read_text(Path(args.log))) if Path(args.log).is_file() else []
    known = set(result.names)
    entries: list[dict] = []
    unknown: list[str] = []
    already: list[str] = []
    for name in names:
        if name in result.changed:
            entries.append({"name": name, "before": result.changed[name].get("hash", ("?", "?"))[0],
                            "after": result.changed[name].get("hash", ("?", "?"))[1], "reason": reason})
        elif any(e["name"] == name for e in result.added):
            entry = next(e for e in result.added if e["name"] == name)
            entries.append({"name": name, "before": "(new)", "after": entry.get("hash"), "reason": reason})
        elif any(e["name"] == name for e in result.missing):
            entry = next(e for e in result.missing if e["name"] == name)
            entries.append({"name": name, "before": entry.get("hash"), "after": "(removed)", "reason": reason})
        elif name not in known:
            if any(key == name for key, _ in seen):
                already.append(name)
            else:
                unknown.append(name)
    if unknown:
        print(f"smoke rebaseline: not changed, nothing to accept: {', '.join(unknown)}", file=sys.stderr)
        print(f"  baseline already matches the current run for {len(names) - len(unknown)} other name(s)",
              file=sys.stderr)
        return 2
    if not entries:
        print(f"smoke rebaseline: already recorded, baseline unchanged: {', '.join(already or names)}")
        return 0

    updated = _apply(baseline, current, {e["name"] for e in entries})
    stamp = args.timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_baseline(Path(args.baseline), updated)
    written = record(Path(args.log), entries, stamp)

    reloaded = load(Path(args.baseline))
    after = diff(reloaded, current)
    accepted_still_different = [e["name"] for e in entries if e["name"] in after.names]
    if accepted_still_different:
        print(f"smoke rebaseline: self-check failed, still different: "
              f"{', '.join(accepted_still_different)}", file=sys.stderr)
        return 1
    for line in describe(after):
        print(line)
    print(f"accepted {len(entries)} scenario(s) into {Path(args.baseline)}"
          f" ({len(written)} new record row{'s' if len(written) != 1 else ''} in {Path(args.log)})")
    if after.empty:
        print("self-check: baseline matches this run; --check now exits 0")
    else:
        print(f"remaining drift not accepted: {len(after)} scenario(s); --check still exits 1")
    return 0


def _apply(baseline: dict, current: dict, names: set[str]) -> dict:
    old = {str(e["name"]): e for e in baseline["scenarios"]}
    now = {str(e["name"]): e for e in current["scenarios"]}
    out: list[dict] = []
    for entry in baseline["scenarios"]:
        name = str(entry["name"])
        if name not in names:
            out.append(entry)
        elif name in now:  # changed or re-added: take today's numbers
            out.append(now[name])
        # accepted removal: drop it
    for entry in current["scenarios"]:
        name = str(entry["name"])
        if name in names and name not in old:
            out.append(entry)
    doc = dict(baseline)
    doc["scenarios"] = out
    return doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="diff the gate against the baseline; exit 1 on drift")
    mode.add_argument("--accept", action="append", metavar="ID[,ID...]",
                      help="re-anchor the named scenarios (repeatable, comma separated)")
    mode.add_argument("--list", action="store_true", help="show baseline and current hashes side by side")
    parser.add_argument("--reason", default="", help="why the named scenarios changed; required by --accept")
    parser.add_argument("--exe", default=str(REPO / "build" / "native" / "Release" / "PvZ2SHUTTLE.exe"))
    parser.add_argument("--content", default=str(REPO / "content"))
    parser.add_argument("--pack", default=str(REPO / "native" / "generated" / "content.pack"))
    parser.add_argument("--boards", default=str(REPO / "native" / "generated" / "board_sizes.json"))
    parser.add_argument("--baseline", default=str(BASELINE))
    parser.add_argument("--log", default=str(RECORD_DOC))
    parser.add_argument("--timestamp", default="", help="ISO-8601 UTC stamp for the record row (tests pass a fixed one)")
    parser.add_argument("--from", dest="from_path", default="",
                        help="compare an existing smoke report instead of running the gate again "
                             "(lets check_all.ps1 reuse build/engine_smoke.fresh.json)")
    args = parser.parse_args(argv)

    try:
        if args.list:
            return cmd_list(args)
        if args.accept:
            return cmd_accept(args)
        return cmd_check(args)
    except BaselineError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except SystemExit as exc:  # engine_smoke raises SystemExit(str) on a broken gate
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
