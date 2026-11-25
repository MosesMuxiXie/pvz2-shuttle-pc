# -*- coding: utf-8 -*-
"""Merge the authored plant rows with the pack-derived roster.

This is the machinery behind ``content/plants.json``: the file is generated from
two inputs, never edited by hand.

* ``content/plants.json`` — the **authored** rows (today 147).  They are emitted
  byte for byte: no key is renamed, reordered, dropped or defaulted.
* ``native/generated/plants_from_pack.json`` — the rows derived from the OBB's
  ``PlantTypes`` sheet (``plants`` = 295 not already in the authored file, and
  ``skipped_existing`` = 44 ids the authored file already covers).

Merge rule: authored first (their original order), then the pack-only rows sorted
by id, each tagged ``"source": "pack"``.  A row that exists in both lists is a
**conflict** and the authored row wins untouched.

A note on the numbers, because they do not match the issue that asked for this
work: the shipping pack declares 339 ``PlantType`` rows, but only 44 of the 147
authored ids are among them.  The other 103 authored rows (fusion results,
Chinese-garden plants, event plants) simply do not exist in this pack.  A merge
that keeps every authored row therefore lands on 147 + 295 = 442 rows, not 339;
reaching 339 would mean deleting 103 authored rows.  ``counts`` in the report
states this plainly instead of pretending the target was met.

Usage::

    python tools/contentc/plants_merge.py            # rewrite content/plants.json
    python tools/contentc/plants_merge.py --check    # verify it is up to date
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_MANUAL = ROOT / "content" / "plants.json"
DEFAULT_PACK = ROOT / "native" / "generated" / "plants_from_pack.json"
MARKER = "plants-merge-v1"
PACK_SOURCE = "pack"
EMPTY = (None, "")


class MergeError(Exception):
    """输入的 id 重复/缺字段——宁可停下也不写半份名册。"""


@dataclass
class MergeResult:
    rows: list[dict]
    counts: dict
    conflicts: list[str] = field(default_factory=list)
    pack_only: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.rows)


def _read_json(path: Path) -> object:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _check_unique(rows: list[dict], where: str) -> list[str]:
    seen: dict[str, int] = {}
    dupes: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise MergeError(f"{where} 第 {index} 条不是对象")
        rid = str(row.get("id") or "").strip()
        if not rid:
            raise MergeError(f"{where} 第 {index} 条缺少 id")
        row["id"] = rid
        if rid in seen:
            dupes.append(rid)
        seen[rid] = index
    if dupes:
        raise MergeError(f"{where} 里 id 重复: {', '.join(sorted(set(dupes)))}")
    return [str(row["id"]) for row in rows]


def load_manual(path: Path = DEFAULT_MANUAL) -> list[dict]:
    """读手工名册（list），跳过上一次合并写进去的 ``source == "pack"`` 行。

    `content/plants.json` 同时是输入与输出，所以「手工行」的判据是**没有**来源
    标记；否则第二次合并会把 295 条派生行当成手工行，再把它们加一遍。
    返回深拷贝，调用方可以放心改。
    """
    doc = _read_json(path)
    if not isinstance(doc, list):
        raise MergeError(f"{path} 必须是 list")
    rows: list[dict] = []
    for row in doc:
        if not isinstance(row, dict):
            raise MergeError(f"{path} 里有非对象条目")
        if row.get("source") == PACK_SOURCE:
            continue
        if "source" in row:
            raise MergeError(f"{path}: {row.get('id')} 带未知 source={row['source']!r}")
        rows.append(json.loads(json.dumps(row, ensure_ascii=False)))
    _check_unique(rows, str(path))
    return rows


def load_pack(path: Path = DEFAULT_PACK) -> tuple[list[dict], list[str]]:
    """读 pack 派生行，返回 (rows, skipped_existing_ids)。"""
    doc = _read_json(path)
    if not isinstance(doc, dict):
        raise MergeError(f"{path} 必须是对象")
    rows = [json.loads(json.dumps(row, ensure_ascii=False)) for row in doc.get("plants") or []]
    _check_unique(rows, f"{path}:plants")
    skipped = [str(row.get("id") or "") for row in doc.get("skipped_existing") or []]
    return rows, [sid for sid in skipped if sid]


def clean_pack_row(row: dict) -> dict:
    """pack 行落盘前的最小整理：删空值、把 ``id`` 提到最前、末尾打来源标记。

    只处理 pack 行；手工行一律原样输出（本函数不接触它们）。
    """
    out: dict = {"id": row["id"]}
    for key, value in row.items():
        if key in ("id", "source"):
            continue
        if value in EMPTY or value == [] or value == {}:
            continue
        out[key] = value
    out["source"] = PACK_SOURCE
    return out


def merge_rows(manual: list[dict], pack: list[dict],
               skipped_ids: list[str] | tuple[str, ...] = ()) -> MergeResult:
    """手工优先的并集：手工行按原序在前，pack-only 行按 id 排在后。

    ``plants_from_pack.json`` 已经把与手工行同 id 的 44 条挪到
    ``skipped_existing``，所以真正的「同一株两边都有」要把它算进来，否则冲突
    数会恒为 0、看起来像两份数据毫无交集。
    """
    manual_ids = _check_unique(manual, "manual")
    _check_unique(pack, "pack")
    manual_set = set(manual_ids)
    pack_ids = {str(row["id"]) for row in pack}
    conflicts = sorted(rid for rid in manual_set if rid in pack_ids or rid in set(skipped_ids))
    pack_only = sorted(rid for rid in pack_ids if rid not in manual_set)
    by_id = {str(row["id"]): row for row in pack}

    rows = [json.loads(json.dumps(row, ensure_ascii=False)) for row in manual]
    rows.extend(clean_pack_row(by_id[rid]) for rid in pack_only)

    counts = {
        "total": len(rows),
        "authored": len(manual),
        "pack": len(rows) - len(manual),
        "conflicts": len(conflicts),
        "packRoster": len(pack) + len(skipped_ids),
        "packOnly": len(pack_only),
        "skippedExisting": len(skipped_ids),
    }
    return MergeResult(rows=rows, counts=counts, conflicts=conflicts, pack_only=pack_only)


def build(manual_path: Path = DEFAULT_MANUAL, pack_path: Path = DEFAULT_PACK) -> MergeResult:
    manual = load_manual(manual_path)
    pack, skipped = load_pack(pack_path)
    return merge_rows(manual, pack, skipped)


def render(rows: list[dict]) -> bytes:
    """与 content/levels 一致的写法：ensure_ascii=False、indent=1、无末尾换行。"""
    return json.dumps(rows, ensure_ascii=False, indent=1).encode("utf-8")


def check(target: Path = DEFAULT_MANUAL, manual_path: Path = DEFAULT_MANUAL,
          pack_path: Path = DEFAULT_PACK) -> tuple[bool, str, MergeResult]:
    """盘上文件是否等于重新合并的结果（逐字节）。"""
    result = build(manual_path, pack_path)
    expected = render(result.rows)
    target = Path(target)
    if not target.is_file():
        return False, f"{target} 不存在", result
    actual = target.read_bytes()
    if actual != expected:
        return (False,
                f"{target} 与合并结果不一致（盘上 {len(actual)} B / 期望 {len(expected)} B）",
                result)
    return True, f"{target} 已是最新（{len(actual)} B）", result


def summarize(result: MergeResult) -> str:
    c = result.counts
    return (f"plants={c['total']} authored={c['authored']} pack={c['pack']} "
            f"conflicts={c['conflicts']} packRoster={c['packRoster']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="merge authored + pack-derived plant rows")
    ap.add_argument("--manual", type=Path, default=DEFAULT_MANUAL)
    ap.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    ap.add_argument("--out", type=Path, default=DEFAULT_MANUAL)
    ap.add_argument("--check", action="store_true", help="只比对，不写盘；不一致退 1")
    ap.add_argument("-n", "--dry-run", action="store_true", help="只打印计数，不写盘")
    args = ap.parse_args(argv)

    try:
        if args.check:
            ok, message, result = check(args.out, args.manual, args.pack)
            print(f"{MARKER}: {summarize(result)}")
            print(message)
            return 0 if ok else 1
        result = build(args.manual, args.pack)
    except MergeError as exc:
        print(f"{MARKER}: {exc}", file=sys.stderr)
        return 2

    print(f"{MARKER}: {summarize(result)}")
    if result.conflicts:
        print("conflicts (authored wins): " + ", ".join(result.conflicts[:12])
              + (" …" if len(result.conflicts) > 12 else ""))
    if args.dry_run:
        return 0
    args.out.write_bytes(render(result.rows))
    print(f"wrote {args.out} ({args.out.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
