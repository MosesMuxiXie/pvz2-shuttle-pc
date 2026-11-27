# -*- coding: utf-8 -*-
"""Merge the authored plant rows with the playable part of the pack-derived roster.

This is the machinery behind ``content/plants.json``: the file is generated from
three inputs, never edited by hand.

* ``content/plants.json`` — the **authored** rows.  They are emitted byte for
  byte: no key is renamed, reordered, dropped or defaulted.
* ``native/generated/plants_from_pack.json`` — the rows derived from the OBB's
  ``PlantTypes`` sheet (``plants`` = 295 not already in the authored file, and
  ``skipped_existing`` = 44 ids the authored file already covers).
* ``native/generated/plant_playable.json`` — which of those 339 pack rows are
  actually playable (t75).  293 pass the four checks; 251 of them are new, 42
  already exist in the authored file, and 46 are blocked (23 lack a cost, 26
  lack artwork, 3 lack both).

Merge rule: authored first (their original order), then the **playable** pack
rows sorted by id, each tagged ``"source": "pack"``.  A row that exists in both
lists is a **conflict** and the authored row wins untouched.  The blocked rows
are not merged; they land in ``native/generated/plant_blocked.json`` with the
reason, so the number 339 = 293 playable + 46 blocked stays auditable.

The arithmetic, because it is not the number the issue asked for: 147 authored +
251 new playable = **398 rows**, and 293 is the *playable coverage* (42 authored
rows + 251 new ones).  Reaching 339 rows in the file would mean deleting authored
rows, which this project does not do.

Usage::

    python tools/contentc/plants_merge.py            # rewrite plants.json + plant_blocked.json
    python tools/contentc/plants_merge.py --check    # verify both are up to date
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from tools.contentc import emit  # noqa: E402

DEFAULT_MANUAL = ROOT / "content" / "plants.json"
DEFAULT_PACK = ROOT / "native" / "generated" / "plants_from_pack.json"
DEFAULT_PLAYABLE = ROOT / "native" / "generated" / "plant_playable.json"
DEFAULT_BLOCKED = ROOT / "native" / "generated" / "plant_blocked.json"
MARKER = "plants-merge-v1"
BLOCKED_MARKER = "plant-blocked-v1"
PACK_SOURCE = "pack"
EMPTY = (None, "")
#: ``expand.py`` writes these two provenance blocks into every packed row.  The
#: roster keeps ``fieldSources`` (it documents where each value came from) and
#: ``familyBasis`` (which rule picked the family) but drops ``packFacts``: it is
#: the raw sheet dump and would triple the file for no reader.
DROPPED_PACK_KEYS = ("packFacts",)
#: How a blocked row is explained in the report and in ``plant_blocked.json``.
BLOCKER_REASON = {
    "no-cost": "缺成本：原版 Cost 缺失或为 0，开局无法定价",
    "no-art": "缺美术：art index 没有匹配 base，content 也没有 art",
    "no-family": "缺族：plant_families.json 与 pack Actions 都没有可用行为族",
}


class MergeError(Exception):
    """输入的 id 重复/缺字段——宁可停下也不写半份名册。"""


@dataclass
class MergeResult:
    rows: list[dict]
    counts: dict
    conflicts: list[str] = field(default_factory=list)
    pack_only: list[str] = field(default_factory=list)
    blocked: dict = field(default_factory=dict)

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
    """读手工名册，**跳过**上一次合并写进去的 ``source: "pack"`` 行。

    `content/plants.json` 既是输入也是输出：不跳过派生存，第二次合并会把
    251 条派生行当成手工行，再加一遍。
    """
    doc = _read_json(path)
    if not isinstance(doc, list):
        raise MergeError(f"{path} 必须是数组")
    rows: list[dict] = []
    for row in doc:
        if not isinstance(row, dict):
            raise MergeError(f"{path}: 名册条目必须是对象")
        if row.get("source") == PACK_SOURCE:
            continue
        if "source" in row:
            raise MergeError(f"{path}: {row.get('id')} 带未知 source={row['source']!r}")
        rows.append(json.loads(json.dumps(row, ensure_ascii=False)))
    _check_unique(rows, str(path))
    return rows


def load_playable(path: Path = DEFAULT_PLAYABLE) -> tuple[list[str], list[dict], list[str]]:
    """读可玩判定，返回 (可玩且未在名册里的 id, 被阻断的行, 可玩但已在名册的 id)。

    第三项就是原版名册里那 42 条「同名已经有了」的行——它们不产生新行，但算进
    「293 条可玩」这个口径里。
    """
    doc = _read_json(path)
    if not isinstance(doc, dict):
        raise MergeError(f"{path} 必须是对象")
    rows = doc.get("rows") or []
    playable_new: list[str] = []
    playable_authored: list[str] = []
    blocked: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            raise MergeError(f"{path}: rows 条目必须是对象")
        rid = str(row.get("id") or "").strip()
        if not rid:
            raise MergeError(f"{path}: 有行缺少 id")
        if row.get("playable") and not row.get("sameAsAuthored"):
            playable_new.append(rid)
        elif row.get("playable"):
            playable_authored.append(rid)
        else:
            blocked.append(row)
    return playable_new, blocked, playable_authored


def load_pack(path: Path = DEFAULT_PACK,
              allow: list[str] | tuple[str, ...] | None = None) -> tuple[list[dict], list[str], int]:
    """读 pack 派生行，返回 (rows, skipped_existing_ids, roster_total)。

    ``allow`` 给了就只保留这些 id（即 ``plant_playable.json`` 判为可玩的新增行）。
    ``roster_total`` 是原版名册的总条数（295 条 pack 行 + 44 条同名），不受 ``allow``
    过滤影响——报告里的 339 就是这个数。
    """
    doc = _read_json(path)
    if not isinstance(doc, dict):
        raise MergeError(f"{path} 必须是对象")
    allowed = {str(rid) for rid in allow} if allow is not None else None
    rows = [json.loads(json.dumps(row, ensure_ascii=False)) for row in doc.get("plants") or []]
    _check_unique(rows, f"{path}:plants")
    skipped = [str(row.get("id") or "") for row in doc.get("skipped_existing") or []]
    skipped = [sid for sid in skipped if sid]
    roster_total = len(rows) + len(skipped)
    if allowed is not None:
        missing = allowed - {str(row["id"]) for row in rows}
        if missing:
            raise MergeError(f"{path}: 可玩名单里有 {len(missing)} 条在 pack 行里找不到: "
                             + ", ".join(sorted(missing)[:6]))
        rows = [row for row in rows if str(row["id"]) in allowed]
    return rows, skipped, roster_total


def clean_pack_row(row: dict) -> dict:
    """pack 行落盘前的最小整理：删空值、把 ``id`` 提到最前、末尾打来源标记。

    只处理 pack 行；手工行一律原样输出（本函数不接触它们）。
    """
    out: dict = {"id": row["id"]}
    for key, value in row.items():
        if key in ("id", "source") or key in DROPPED_PACK_KEYS:
            continue
        if value in EMPTY or value == [] or value == {}:
            continue
        out[key] = value
    out["source"] = PACK_SOURCE
    return out


def blocked_payload(blocked_rows: list[dict], manual_ids: list[str] | tuple[str, ...],
                    pack_path: Path = DEFAULT_PACK, playable_path: Path = DEFAULT_PLAYABLE) -> dict:
    """46 条进不来的行，逐条带原因——名册里没有它们，但缺口要可审计。"""
    manual = set(manual_ids)
    rows: list[dict] = []
    for row in sorted(blocked_rows, key=lambda r: str(r.get("id") or "")):
        rid = str(row.get("id") or "")
        blockers = list(row.get("blockers") or [])
        reasons = [BLOCKER_REASON.get(b, b) for b in blockers]
        rows.append({
            "id": rid,
            "framework": row.get("framework"),
            "cost": row.get("cost"),
            "family": row.get("family"),
            "blockers": blockers,
            "reason": "；".join(reasons),
            "inRoster": rid in manual,
            "inPackRoster": bool(row.get("hasPackRow")),
        })
    counts = {
        "total": len(rows),
        "packOnly": sum(1 for r in rows if not r["inRoster"]),
        "authored": sum(1 for r in rows if r["inRoster"]),
        "missingCost": sum(1 for r in rows if "no-cost" in r["blockers"]),
        "missingArt": sum(1 for r in rows if "no-art" in r["blockers"]),
        "missingFamily": sum(1 for r in rows if "no-family" in r["blockers"]),
        "both": sum(1 for r in rows if len(r["blockers"]) > 1),
    }
    return {
        "format": 1,
        "marker": BLOCKED_MARKER,
        "sources": {"pack": _rel(pack_path), "playable": _rel(playable_path)},
        "counts": counts,
        "rows": rows,
    }


def _rel(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def merge_rows(manual: list[dict], pack: list[dict],
               skipped_ids: list[str] | tuple[str, ...] = (),
               blocked_rows: list[dict] | None = None,
               playable_authored: int = 0,
               pack_roster: int = 0) -> MergeResult:
    """手工优先的并集：手工行按原序在前，可玩的 pack-only 行按 id 排在后。

    ``plants_from_pack.json`` 已经把与手工行同 id 的 44 条挪到
    ``skipped_existing``，所以真正的「同一株两边都有」要把它算进来，否则冲突
    数会恒为 0、看起来像两份数据毫无交集。
    """
    manual_ids = _check_unique(manual, "manual")
    _check_unique(pack, "pack")
    manual_set = set(manual_ids)
    pack_ids = {str(row["id"]) for row in pack}
    skipped_set = set(skipped_ids)
    conflicts = sorted(rid for rid in manual_set if rid in pack_ids or rid in skipped_set)
    pack_only = sorted(rid for rid in pack_ids if rid not in manual_set)
    by_id = {str(row["id"]): row for row in pack}

    rows = [json.loads(json.dumps(row, ensure_ascii=False)) for row in manual]
    rows.extend(clean_pack_row(by_id[rid]) for rid in pack_only)

    blocked = blocked_rows or []
    counts = {
        "total": len(rows),
        "authored": len(manual),
        "pack": len(rows) - len(manual),
        "conflicts": len(conflicts),
        "packRoster": pack_roster or (len(pack) + len(skipped_ids)),
        "packOnly": len(pack_only),
        "skippedExisting": len(skipped_ids),
        "blocked": len(blocked),
        "blockedPackOnly": sum(1 for row in blocked if str(row.get("id")) not in manual_set),
        "playable": len(pack_only) + playable_authored,
        "playableAuthored": playable_authored,
    }
    return MergeResult(rows=rows, counts=counts, conflicts=conflicts, pack_only=pack_only,
                       blocked=blocked_payload(blocked, manual_ids))


def build(manual_path: Path = DEFAULT_MANUAL, pack_path: Path = DEFAULT_PACK,
          playable_path: Path = DEFAULT_PLAYABLE) -> MergeResult:
    manual = load_manual(manual_path)
    playable_new, blocked, playable_authored = load_playable(playable_path)
    pack, skipped, roster_total = load_pack(pack_path, allow=playable_new)
    return merge_rows(manual, pack, skipped, blocked,
                      playable_authored=len(playable_authored), pack_roster=roster_total)


def render(rows: list[dict]) -> bytes:
    """与 content/levels 一致的写法：ensure_ascii=False、indent=1、无末尾换行。"""
    return json.dumps(rows, ensure_ascii=False, indent=1).encode("utf-8")


def render_blocked(payload: dict) -> bytes:
    return emit.dumps(payload).encode("utf-8")


def check(target: Path = DEFAULT_MANUAL, manual_path: Path = DEFAULT_MANUAL,
          pack_path: Path = DEFAULT_PACK, playable_path: Path = DEFAULT_PLAYABLE,
          blocked_path: Path = DEFAULT_BLOCKED) -> tuple[bool, str, MergeResult]:
    """盘上两份产物是否等于重新合并的结果（逐字节）。"""
    result = build(manual_path, pack_path, playable_path)
    problems: list[str] = []
    for path, expected in ((Path(target), render(result.rows)),
                           (Path(blocked_path), render_blocked(result.blocked))):
        if not path.is_file():
            problems.append(f"{path} 不存在")
            continue
        actual = path.read_bytes()
        if actual != expected:
            problems.append(f"{path} 与合并结果不一致（盘上 {len(actual)} B / 期望 {len(expected)} B）")
    if problems:
        return False, "；".join(problems), result
    return True, f"{Path(target)} 与 {Path(blocked_path)} 已是最新", result


def summarize(result: MergeResult) -> str:
    c = result.counts
    return (f"plants={c['total']} authored={c['authored']} pack={c['pack']} "
            f"conflicts={c['conflicts']} playable={c['playable']} blocked={c['blocked']} "
            f"packRoster={c['packRoster']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="merge authored + playable pack-derived plant rows")
    ap.add_argument("--manual", type=Path, default=DEFAULT_MANUAL)
    ap.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    ap.add_argument("--playable", type=Path, default=DEFAULT_PLAYABLE)
    ap.add_argument("--out", type=Path, default=DEFAULT_MANUAL)
    ap.add_argument("--blocked", type=Path, default=DEFAULT_BLOCKED)
    ap.add_argument("--check", action="store_true", help="只比对，不写盘；不一致退 1")
    ap.add_argument("-n", "--dry-run", action="store_true", help="只打印计数，不写盘")
    args = ap.parse_args(argv)

    try:
        if args.check:
            ok, message, result = check(args.out, args.manual, args.pack, args.playable, args.blocked)
            print(f"{MARKER}: {summarize(result)}")
            print(message)
            return 0 if ok else 1
        result = build(args.manual, args.pack, args.playable)
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
    args.blocked.write_bytes(render_blocked(result.blocked))
    print(f"wrote {args.out} ({args.out.stat().st_size} B)")
    print(f"wrote {args.blocked} ({args.blocked.stat().st_size} B)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
