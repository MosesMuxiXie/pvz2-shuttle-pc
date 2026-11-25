"""Build `native/generated/content.pack` from the shipped property sheets.

Usage:
    python tools/contentc/build_content.py [-n]
    python tools/contentc/build_content.py --check

`--check` rebuilds in memory and fails when a count differs from the pinned
expectations, so a data or parser change cannot silently shrink coverage.
`-n/--dry-run` prints the summary without writing files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.contentc import emit, model  # noqa: E402
import os

DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages"))
DEFAULT_OUT = ROOT / "native" / "generated" / "content.pack"
DEFAULT_COVERAGE = ROOT / "native" / "generated" / "coverage.json"
DEFAULT_OVERLAP = ROOT / "native" / "generated" / "id_overlap.json"
DEFAULT_CONTENT = ROOT / "content"

EXPECTED = {"plants": 339, "zombies": 1127, "plantsMissingProps": 0, "danglingRefs": 3}


def summarize(pack: dict) -> str:
    counts = pack["counts"]
    parts = [f"{key}={counts[key]}" for key in sorted(counts)]
    kinds = ",".join(f"{kind}:{count}" for kind, count in sorted(pack["actionsByKind"].items()))
    unknown = pack["unknownActionKinds"]
    lines = [
        " ".join(parts),
        f"actions({kinds})" + (f" unknown={unknown}" if unknown else ""),
        f"dangling={[(item['type'], item['ref']) for item in pack['dangling']]}",
    ]
    return "\n".join(lines)


def check(pack: dict) -> list[str]:
    counts = pack["counts"]
    problems = []
    for key, expect in EXPECTED.items():
        got = counts.get(key)
        if got != expect:
            problems.append(f"{key}: expected {expect}, got {got}")
    if pack["counts"]["zombiesMissingProps"] != len(pack["dangling"]):
        problems.append(
            "every zombie type whose properties are dangling must be reported missing: "
            f"{pack['counts']['zombiesMissingProps']} vs {len(pack['dangling'])}"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--coverage", type=Path, default=DEFAULT_COVERAGE)
    parser.add_argument("--overlap", type=Path, default=DEFAULT_OVERLAP)
    parser.add_argument("--content", type=Path, default=DEFAULT_CONTENT)
    parser.add_argument("--generated", default=None)
    parser.add_argument("--check", action="store_true", help="verify pinned counts, write nothing")
    parser.add_argument("-n", "--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.obb.is_dir():
        print(f"error: property sheets not found: {args.obb}", file=sys.stderr)
        return 2

    pack = model.build_pack(args.obb, args.generated)
    print(summarize(pack))

    overlap = model.compute_overlap(pack, args.content)
    for kind, row in overlap.items():
        print(f"ids {kind}: pack={row['pack']} content={row['content']} shared={row['shared']}")

    problems = check(pack)
    for problem in problems:
        print(f"[fail] {problem}", file=sys.stderr)
    if args.check:
        return 1 if problems else 0
    if args.dry_run:
        return 0

    emit.write_pack(args.out, pack)
    emit.write_coverage(args.coverage, pack)
    emit.write_coverage(args.overlap, overlap)
    print(f"wrote {args.out.relative_to(ROOT)}, {args.coverage.relative_to(ROOT)}, {args.overlap.relative_to(ROOT)}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
