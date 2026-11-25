"""Compare the shipped world definitions with the worlds the client knows.

The original WorldData sheet describes 46 worlds: the campaign worlds a player
walks through, plus event-only entries (anniversaries, collabs, timed events,
`yourhousex`, a duplicated `kungfu`). The client's `content/worlds.json` has 26.
This module reads both, matches what can be matched, and writes a diff that names
every remaining gap instead of hiding it.

Usage:
    python tools/contentc/worlds.py                     # writes native/generated/world_diff.md
                                                        #   + native/generated/world_gates.json
    python tools/contentc/worlds.py --out build/w.md
    python tools/contentc/worlds.py --emit-json build/g.json
"""

from __future__ import annotations

import argparse
import html
import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONTENT = REPO / "content"
DEFAULT_OUT = REPO / "native" / "generated" / "world_diff.md"
DEFAULT_GATES = REPO / "native" / "generated" / "world_gates.json"
DEFAULT_GATES_REPORT = REPO / "docs" / "reviews" / "2026-11-21-world-gates.md"
GATES_FORMAT = 1
GATE_KINDS = ("star_gate", "key_gate", "worldgate")

#: Event types that are definitely not gates (map levels, plant pins, cosmetics).
#: Anything outside this set and outside `GATE_KINDS` is kept in the export as an
#: unknown gate kind instead of being dropped.
NON_GATE_KINDS = frozenset({"level", "plant", "giftbox", "costume", "doodad", "upgrade"})


def _default_obb() -> Path:
    """The sheets live next to the repository checkout, one or more levels up.

    ``PVZ2_OBB_DIR`` wins over the search: the 460.9 rebase keeps the old 460.1
    sheets in place and points every compiler at a second extraction directory.
    """
    env = os.environ.get("PVZ2_OBB_DIR")
    if env:
        return Path(env)
    for base in REPO.parents:
        candidate = base / "work" / "obb_packages"
        if candidate.is_dir():
            return candidate
    return REPO.parent / "work" / "obb_packages"


DEFAULT_OBB = _default_obb()

#: OBB world names whose client id is not the same word. Everything else is an
#: exact name match; a fuzzy matcher here would hide real gaps.
ALIASES = {
    "skycity": "sky",
    "gta": "losantosvice",
    "rainbowmarket": "lunarrainbowmarket",
    # WorldData spells the kung-fu world kungfu; the client uses kongfu everywhere
    # (worlds.json, worldmap.json and all 83 level files). t37 measured 9 gates on this
    # fork, not 24: 8 already say kongfu, 1 says kungfu.
    "kungfu": "kongfu",
}

#: Worlds the client ships that this build of the game has no WorldData for.
#: They stay because their levels exist in `content/levels` (synthesized).
KNOWN_SYNTHETIC = {
    "future": "未来世界：本版 WorldData 无对应条目，关卡为合成",
    "iceage": "冰河世界：本版 WorldData 无对应条目，关卡为合成",
    "renai": "恋爱剧场：本版 WorldData 无对应条目，关卡为合成",
    "frontyard": "前院：由 tutorial + yourhouse 合并而来",
}


@dataclass
class ObWorld:
    serial: int
    world_id: int
    name: str
    res_group: int
    events: Counter = field(default_factory=Counter)
    pieces: int = 0
    gates: list[tuple[str, str]] = field(default_factory=list)

    @property
    def levels(self) -> int:
        return self.events["level"]


@dataclass
class ContentWorld:
    id: str
    name: str
    levels: int
    unlock_after: str | None


def load_obb_worlds(obb_dir: Path) -> list[ObWorld]:
    path = obb_dir / "pkg_2107_WorldData.json"
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    worlds: list[ObWorld] = []
    for serial, entry in enumerate(doc.get("objects") or []):
        data = entry.get("objdata") if isinstance(entry, dict) else None
        if not isinstance(data, dict):
            continue
        world = ObWorld(
            serial=serial,
            world_id=int(data.get("m_worldId") or 0),
            name=str(data.get("m_worldName") or ""),
            res_group=int(data.get("m_resGroupID") or 0),
            pieces=len(data.get("m_mapPieces") or []),
        )
        for event in data.get("m_eventList") or []:
            if not isinstance(event, dict):
                continue
            kind = str(event.get("m_eventType") or "")
            world.events[kind] += 1
            if kind in {"star_gate", "key_gate", "worldgate"}:
                world.gates.append((kind, str(event.get("m_unlockedFrom") or "")))
        worlds.append(world)
    return worlds


def load_content_worlds(content_dir: Path) -> list[ContentWorld]:
    doc = json.loads((content_dir / "worlds.json").read_text(encoding="utf-8"))
    rows = doc["worlds"] if isinstance(doc, dict) else doc
    return [
        ContentWorld(
            id=str(row["id"]),
            name=str(row.get("name_zh") or ""),
            levels=int(row.get("levels") or 0),
            unlock_after=row.get("unlock_after"),
        )
        for row in rows
    ]


def diff(obb_worlds: list[ObWorld], content_worlds: list[ContentWorld]) -> dict:
    by_client = {world.id: world for world in content_worlds}
    matched: dict[str, ObWorld] = {}
    unmatched: list[ObWorld] = []
    for world in obb_worlds:
        client = ALIASES.get(world.name, world.name)
        if client in by_client and client not in matched:
            matched[client] = world
        else:
            unmatched.append(world)
    missing = [world for world in content_worlds if world.id not in matched]
    event_totals: Counter = Counter()
    for world in obb_worlds:
        event_totals.update(world.events)
    return {
        "matched": matched,
        "unmatched_obb": unmatched,
        "unmatched_content": missing,
        "event_totals": event_totals,
        "obb_worlds": obb_worlds,
        "content_worlds": content_worlds,
    }


def render(result: dict, generated: str) -> str:
    matched: dict[str, ObWorld] = result["matched"]
    out: list[str] = []
    out.append("# 世界差异（OBB WorldData ↔ content/worlds.json）\n")
    if generated:
        out.append(f"generated={generated}\n")
    obb_worlds = result["obb_worlds"]
    content_worlds = result["content_worlds"]
    totals: Counter = result["event_totals"]
    out.append(
        f"- WorldData 条目：{len(obb_worlds)}；client 世界：{len(content_worlds)}；"
        f"已匹配：{len(matched)}\n"
    )
    out.append(
        "- 事件总数："
        + "，".join(f"{name}={count}" for name, count in sorted(totals.items()))
        + "\n"
    )
    gate_total = sum(len(world.gates) for world in obb_worlds)
    out.append(f"- 门（star_gate/key_gate/worldgate）：{gate_total} 条\n")

    out.append("\n## 已匹配\n\n")
    out.append("| client | OBB 名称 | 关卡事件 | 星门 | 钥匙门 | 世界门 | 地图件 |\n")
    out.append("| --- | --- | --- | --- | --- | --- | --- |\n")
    for client_id in sorted(matched):
        world = matched[client_id]
        out.append(
            f"| {client_id} | {world.name} | {world.events['level']} | "
            f"{world.events['star_gate']} | {world.events['key_gate']} | "
            f"{world.events['worldgate']} | {world.pieces} |\n"
        )

    out.append("\n## client 有、WorldData 无（依赖合成关卡）\n\n")
    if result["unmatched_content"]:
        out.append("| client | 名称 | 关卡 | 说明 |\n| --- | --- | --- | --- |\n")
        for world in result["unmatched_content"]:
            note = KNOWN_SYNTHETIC.get(world.id, "未标注")
            out.append(f"| {world.id} | {world.name} | {world.levels} | {html.escape(note)} |\n")
    else:
        out.append("（无）\n")

    out.append("\n## WorldData 有、client 未接（事件/变体世界）\n\n")
    if result["unmatched_obb"]:
        out.append("| OBB 名称 | worldId | 关卡事件 | 星门 | 钥匙门 | 世界门 | 地图件 |\n")
        out.append("| --- | --- | --- | --- | --- | --- | --- |\n")
        for world in result["unmatched_obb"]:
            out.append(
                f"| {world.name} | {world.world_id} | {world.events['level']} | "
                f"{world.events['star_gate']} | {world.events['key_gate']} | "
                f"{world.events['worldgate']} | {world.pieces} |\n"
            )
    else:
        out.append("（无）\n")

    gates = [
        (world.name, kind, source)
        for world in obb_worlds
        for kind, source in world.gates
    ]
    out.append("\n## 门与来源（前 40 条）\n\n")
    out.append("| OBB 名称 | 类型 | unlockedFrom |\n| --- | --- | --- |\n")
    for name, kind, source in gates[:40]:
        out.append(f"| {name} | {kind} | {source} |\n")
    if len(gates) > 40:
        out.append(f"\n（其余 {len(gates) - 40} 条略）\n")
    return "".join(out)


def _world_data_path(obb_dir: Path) -> Path:
    return obb_dir / "pkg_2107_WorldData.json"


def gate_stamp(obb_dir: Path) -> str:
    """Content stamp of WorldData (C58): `sha256:<16 hex>`, never the clock or the mtime.

    An mtime stamp looked revision-accurate but changed on every re-extraction of the same
    OBB (each version bump re-extracts), so the export churned while its input was identical.
    """
    return "sha256:" + hashlib.sha256(_world_data_path(obb_dir).read_bytes()).hexdigest()[:16]


def _gate_source(obb_dir: Path) -> str:
    path = _world_data_path(obb_dir)
    if path.parent.name == "obb_packages" and path.parent.parent.name == "work":
        return f"work/obb_packages/{path.name}"
    return path.as_posix()


def _gate_target(kind: str, event: dict) -> str | None:
    """What the gate points at, or None when WorldData records no target.

    - `worldgate` carries `m_dataString = "<world>-<entry event>-<bool>"`; the first
      segment is the world it unlocks.
    - `star_gate` / `key_gate` record no destination event, only the prerequisite in
      `m_unlockedFrom` (empty on 31 of 53 star gates and on all 27 key gates). That
      prerequisite is the only target-shaped field, so it is used verbatim and the
      rest stay null instead of being guessed.
    """
    if kind == "worldgate":
        data = str(event.get("m_dataString") or "")
        head = data.split("-", 1)[0].strip()
        return head or None
    unlocked = str(event.get("m_unlockedFrom") or "").strip()
    return unlocked or None


def _gate_stars(kind: str, event: dict) -> int | None:
    """Star requirement, and only for star gates.

    `m_cost` means stars on `star_gate` (0/1/8/10/20, absent on 18) and keys on
    `key_gate` (1..5). Keys are not stars, so they stay in `raw` instead of being
    squeezed into this field.
    """
    if kind != "star_gate":
        return None
    cost = event.get("m_cost")
    if isinstance(cost, bool) or not isinstance(cost, int):
        return None
    return cost


def _client_name(name: str | None) -> str | None:
    """Map an OBB world name to the client id via `ALIASES`; unchanged otherwise."""
    if name is None:
        return None
    return ALIASES.get(name, name)


def _gate_keys(kind: str, event: dict) -> int | None:
    """Key requirement, and only for key gates.

    `m_cost` on `key_gate` counts keys (1/3/4/5). It is exported here and *not* as
    stars; `stars` stays null for key gates so the two currencies never mix.
    """
    if kind != "key_gate":
        return None
    cost = event.get("m_cost")
    if isinstance(cost, bool) or not isinstance(cost, int):
        return None
    return cost


def collect_gates(obb_dir: Path) -> tuple[list[dict], dict]:
    """Walk `m_eventList` and project every gate (plus unknown gate kinds)."""
    doc = json.loads(_world_data_path(obb_dir).read_text(encoding="utf-8-sig"))
    gates: list[dict] = []
    per_kind: Counter = Counter()
    unknown: Counter = Counter()
    for entry in doc.get("objects") or []:
        data = entry.get("objdata") if isinstance(entry, dict) else None
        if not isinstance(data, dict):
            continue
        world = str(data.get("m_worldName") or "")
        for event in data.get("m_eventList") or []:
            if not isinstance(event, dict):
                continue
            kind = str(event.get("m_eventType") or "").strip()
            if not kind or kind in NON_GATE_KINDS:
                continue
            if kind not in GATE_KINDS:
                unknown[kind] += 1
            target = _gate_target(kind, event)
            gates.append(
                {
                    "world": world,
                    "worldClient": _client_name(world),
                    "kind": kind,
                    "event": str(event.get("m_name") or kind),
                    "target": target,
                    "targetClient": _client_name(target),
                    "stars": _gate_stars(kind, event),
                    "keys": _gate_keys(kind, event),
                    "raw": event,
                }
            )
            per_kind[kind] += 1
    counts = {kind: per_kind.get(kind, 0) for kind in GATE_KINDS}
    counts["total"] = len(gates)
    counts["unknownKinds"] = dict(sorted(unknown.items()))
    counts["aliasHits"] = {
        alias: sum(1 for gate in gates if gate["world"] == alias) for alias in sorted(ALIASES)
    }
    return gates, counts


def build_gates(obb_dir: Path, generated: str | None = None) -> dict:
    gates, counts = collect_gates(obb_dir)
    return {
        "format": GATES_FORMAT,
        "source": _gate_source(obb_dir),
        "generated": generated or gate_stamp(obb_dir),
        "gates": gates,
        "counts": counts,
    }


def render_gates_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def write_gates(path: Path, payload: dict) -> bytes:
    data = render_gates_json(payload).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)  # bytes, not text mode: Windows must not turn LF into CRLF
    return data


def _md_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |\n", "|" + "|".join(" --- " for _ in headers) + "|\n"]
    for row in rows:
        out.append("| " + " | ".join(row) + " |\n")
    return out


def render_gates_markdown(payload: dict, obb_dir: Path) -> str:
    gates = payload["gates"]
    counts = payload["counts"]
    out: list[str] = []
    out.append("# 世界门数据（world_gates.json）：字段口径与分布\n")
    out.append(f"\ngenerated={payload['generated']}；source={payload['source']}\n")
    out.append(
        f"\n门总数 {counts['total']}：star_gate {counts['star_gate']}、"
        f"key_gate {counts['key_gate']}、worldgate {counts['worldgate']}。\n"
    )

    out.append("\n## 一、字段口径\n\n")
    out.append("- `stars`：只有 `star_gate` 有值，取自 `m_cost`；**`0` 表示免费**，`null` 表示原表没写。\n")
    out.append("- `keys`：只有 `key_gate` 有值，取自 `m_cost`（钥匙数 1/3/4/5）；其它 kind 一律 `null`。\n")
    out.append(
        "- 两个字段互斥：`keys` 与 `stars` 不会同时有值；缺值写 `null` 而不是 `0`，"
        "S6 判定时把 `null` 当「不设门槛」，把 `0` 当「门槛为 0」。\n"
    )
    out.append(
        "- `world` 是 WorldData 的 `m_worldName` 原值；`worldClient` 用 `ALIASES` 归一后的 client id，"
        "未收录的原样返回。`target`/`targetClient` 同理（`target` 为 `null` 时 `targetClient` 也是 `null`）。\n"
    )
    out.append("- `raw` 是 `m_eventList` 里的原始事件对象，未删字段；上面的字段都是它的投影。\n")

    out.append("\n## 二、三类门字段表\n\n")
    rows: list[list[str]] = []
    for kind in GATE_KINDS:
        subset = [gate for gate in gates if gate["kind"] == kind]
        rows.append(
            [
                f"`{kind}`",
                str(len(subset)),
                str(sum(1 for gate in subset if gate["world"] is not None)),
                str(sum(1 for gate in subset if gate["worldClient"] is not None)),
                str(sum(1 for gate in subset if gate["target"] is not None)),
                str(sum(1 for gate in subset if gate["targetClient"] is not None)),
                str(sum(1 for gate in subset if gate["stars"] is not None)),
                str(sum(1 for gate in subset if gate["stars"] is None)),
                str(sum(1 for gate in subset if gate["keys"] is not None)),
                str(sum(1 for gate in subset if gate["keys"] is None)),
            ]
        )
    out.extend(
        _md_table(
            [
                "kind",
                "条数",
                "world 有值",
                "worldClient 有值",
                "target 有值",
                "targetClient 有值",
                "stars 有值",
                "stars=null",
                "keys 有值",
                "keys=null",
            ],
            rows,
        )
    )

    out.append("\n## 三、`ALIASES` 命中（按 `world` 统计）\n\n")
    alias_rows = [
        [f"`{alias}`", f"`{ALIASES[alias]}`", str(counts["aliasHits"].get(alias, 0))]
        for alias in sorted(ALIASES)
    ]
    alias_rows.append(["（未命中别名的世界）", "—", str(counts["total"] - sum(counts["aliasHits"].values()))])
    out.extend(_md_table(["原始 world", "client id", "门数"], alias_rows))

    out.append("\n## 四、钥匙数分布（key_gate 的 `m_cost`）\n\n")
    key_values: Counter = Counter()
    for gate in gates:
        if gate["kind"] == "key_gate":
            key_values["null" if gate["keys"] is None else str(gate["keys"])] += 1
    key_rows = [[f"`{value}`", str(key_values[value])] for value in sorted(key_values)]
    out.extend(_md_table(["keys", "条数"], key_rows or [["（无）", "0"]]))

    out.append("\n## 五、零门世界\n\n")
    with_gates = {gate["world"] for gate in gates}
    all_worlds = [world.name for world in load_obb_worlds(obb_dir)]
    zero = [name for name in all_worlds if name not in with_gates]
    out.append(f"WorldData 共 {len(all_worlds)} 个世界，其中 {len(zero)} 个没有任何门事件：\n\n")
    out.append("、".join(f"`{name}`" for name in zero) + "\n")
    out.append(
        f"\n其余 {len(all_worlds) - len(zero)} 个世界有门；`egypt` 也在零门名单里——"
        "它只有 level/plant 事件，不是导出漏项。\n"
    )

    out.append("\n## 六、复现\n\n")
    out.append("```powershell\npython tools/contentc/worlds.py\n```\n")
    out.append(
        "\n所有计数现场计算；`generated` 取 `pkg_2107_WorldData.json` 的 mtime（UTC ISO8601），"
        "不用墙钟，因此两次运行字节一致。\n"
    )
    return "".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB)
    parser.add_argument("--content", type=Path, default=DEFAULT_CONTENT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--generated", default="")
    parser.add_argument(
        "--emit-json",
        type=Path,
        default=DEFAULT_GATES,
        help="world gate export (default: native/generated/world_gates.json); pass '' to skip",
    )
    parser.add_argument(
        "--emit-report",
        type=Path,
        default=DEFAULT_GATES_REPORT,
        help="gate field report (default: docs/reviews/2026-11-21-world-gates.md); pass '' to skip",
    )
    args = parser.parse_args()

    result = diff(load_obb_worlds(args.obb), load_content_worlds(args.content))
    text = render(result, args.generated)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(text.encode("utf-8"))  # bytes: Windows must not turn LF into CRLF
    matched = len(result["matched"])
    print(
        f"worlds obb={len(result['obb_worlds'])} content={len(result['content_worlds'])} "
        f"matched={matched} unmatched_obb={len(result['unmatched_obb'])} "
        f"unmatched_content={len(result['unmatched_content'])}"
    )
    print(f"wrote {args.out}")

    if args.emit_json is not None and str(args.emit_json) not in ("", "."):
        payload = build_gates(args.obb)
        write_gates(args.emit_json, payload)
        counts = payload["counts"]
        print(
            f"gates star={counts['star_gate']} key={counts['key_gate']} "
            f"world={counts['worldgate']} total={counts['total']} "
            f"unknown={len(counts['unknownKinds'])}"
        )
        print(f"wrote {args.emit_json}")
        if args.emit_report is not None and str(args.emit_report) not in ("", "."):
            report = render_gates_markdown(payload, args.obb)
            args.emit_report.parent.mkdir(parents=True, exist_ok=True)
            args.emit_report.write_bytes(report.encode("utf-8"))
            print(f"wrote {args.emit_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
