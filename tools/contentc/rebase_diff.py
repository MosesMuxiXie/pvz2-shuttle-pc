# -*- coding: utf-8 -*-
"""Measure the data delta between two OBB package trees (P2 of the 460.9 rebase).

Both sides are ``split_packages.py`` output directories: ``pkg_<index>_<objclass>.json``
plus ``_index.json``. The tool answers three questions and refuses to guess:

1. which packages were added / removed / changed;
2. for a changed package, which top-level paths differ (deep compare, leaf level);
3. how the objclass mix changed (so a new subsystem shows up as a block, not noise).

Comparison key: the **file name** (index + objclass). Index drift is visible on its own
because added/removed rows are reported by name and the ``_index.json`` blob map is
compared separately. Semantics of "changed" is byte-exact on canonical JSON
(``sort_keys`` + separators), so formatting differences never count.

Usage:
    python tools/contentc/rebase_diff.py --old DIR --new DIR [--json OUT] [--limit N]
                                         [--grep REGEX] [--quiet]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

MAX_PATHS_PER_PACKAGE = 40


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_packages(root: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for entry in sorted(os.listdir(root)):
        if not entry.endswith(".json") or entry == "_index.json":
            continue
        with open(root / entry, encoding="utf-8") as f:
            out[entry] = json.load(f)
    return out


def load_index(root: Path) -> Any:
    path = root / "_index.json"
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def objclass_of(name: str) -> str:
    stem = name[len("pkg_"):] if name.startswith("pkg_") else name
    _, _, rest = stem.partition("_")
    return rest[: -len(".json")] if rest.endswith(".json") else rest


def walk_diff(a: Any, b: Any, path: str, out: list[dict[str, Any]], limit: int) -> None:
    if len(out) >= limit:
        return
    if type(a) is not type(b):
        out.append({"path": path, "old": repr(a)[:120], "new": repr(b)[:120]})
        return
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a:
                out.append({"path": f"{path}.{key}", "old": "<missing>", "new": "<added>"})
            elif key not in b:
                out.append({"path": f"{path}.{key}", "old": "<removed>", "new": "<missing>"})
            else:
                walk_diff(a[key], b[key], f"{path}.{key}", out, limit)
        return
    if isinstance(a, list):
        if len(a) != len(b):
            out.append({"path": f"{path}.len", "old": len(a), "new": len(b)})
        for i in range(min(len(a), len(b))):
            walk_diff(a[i], b[i], f"{path}[{i}]", out, limit)
        return
    if a != b:
        out.append({"path": path, "old": repr(a)[:120], "new": repr(b)[:120]})


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True, type=Path)
    ap.add_argument("--new", required=True, type=Path)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--limit", type=int, default=MAX_PATHS_PER_PACKAGE)
    ap.add_argument("--grep", default=None, help="only report packages whose name matches")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    for side in (args.old, args.new):
        if not side.is_dir():
            raise SystemExit(f"not a directory: {side}")

    pattern = re.compile(args.grep) if args.grep else None
    old = load_packages(args.old)
    new = load_packages(args.new)

    only_old = sorted(set(old) - set(new))
    only_new = sorted(set(new) - set(old))
    common = sorted(set(old) & set(new))

    changed: list[dict[str, Any]] = []
    for name in common:
        if pattern and not pattern.search(name):
            continue
        if canonical(old[name]) == canonical(new[name]):
            continue
        paths: list[dict[str, Any]] = []
        walk_diff(old[name], new[name], "", paths, args.limit)
        changed.append({"package": name, "objclass": objclass_of(name), "paths": paths})

    classes_old = Counter(objclass_of(n) for n in old)
    classes_new = Counter(objclass_of(n) for n in new)
    class_delta = {
        cls: {"old": classes_old.get(cls, 0), "new": classes_new.get(cls, 0)}
        for cls in sorted(set(classes_old) | set(classes_new))
        if classes_old.get(cls, 0) != classes_new.get(cls, 0)
    }

    index_old, index_new = load_index(args.old), load_index(args.new)
    index_note = None
    if index_old is not None and index_new is not None:
        index_note = {
            "okOld": index_old.get("ok"),
            "okNew": index_new.get("ok"),
            "failOld": index_old.get("fail"),
            "failNew": index_new.get("fail"),
            "identical": canonical(index_old) == canonical(index_new),
        }

    report = {
        "old": str(args.old),
        "new": str(args.new),
        "packages": {"old": len(old), "new": len(new), "common": len(common)},
        "added": [{"package": n, "objclass": objclass_of(n)} for n in only_new],
        "removed": [{"package": n, "objclass": objclass_of(n)} for n in only_old],
        "changedCount": len(changed),
        "changed": changed,
        "objclassDelta": class_delta,
        "index": index_note,
    }

    if args.json:
        with open(args.json, "w", encoding="utf-8", newline="\n") as f:
            json.dump(report, f, ensure_ascii=False, sort_keys=True, indent=1)
            f.write("\n")

    if not args.quiet:
        print(f"packages: {len(old)} -> {len(new)} (common {len(common)})")
        print(f"added {len(only_new)}, removed {len(only_old)}, changed {len(changed)}")
        for row in only_new[:20]:
            print(f"  + {row}")
        for row in only_old[:20]:
            print(f"  - {row}")
        for row in changed[:20]:
            print(f"  ~ {row['package']} ({len(row['paths'])} path(s))")
            for p in row["paths"][:5]:
                print(f"      {p['path']}: {p['old']} -> {p['new']}")
        if class_delta:
            print("objclass delta:")
            for cls, d in list(class_delta.items())[:40]:
                print(f"  {cls}: {d['old']} -> {d['new']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
