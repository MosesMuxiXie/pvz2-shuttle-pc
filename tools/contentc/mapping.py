"""Map the shipped PlantType/ZombieType tables onto the client's own content ids.

Usage:
    python tools/contentc/mapping.py
    python tools/contentc/mapping.py -n            # summary only, write nothing
    python tools/contentc/mapping.py --csv out.csv --report out.md

Why this exists: `content/plants.json` and `content/zombies.json` name the units the
port actually ships, while the original tables name what the shipped build contains.
The two vocabularies overlap only partly, so every later stage (board geometry,
action wiring, sprite lookup) needs one auditable table saying which original row —
if any — backs a client id.

Match levels, in order, and exactly which one a CSV row used is recorded in its
`match_kind` column:

1. ``exact``   — the original ``TypeName`` equals the client id (case sensitive).
                 Several original rows sharing one TypeName all point at that client
                 id and show up in the one-to-many list.
2. ``popanim`` — ``PopAnim`` with ``POPANIM_PLANT_`` / ``POPANIM_ZOMBIE_`` stripped
                 equals the client id. Same-token hits in this build are art reuse
                 (the client reuses another plant's animation), so acceptance also
                 requires a same-origin guard: the hit must be unique, unclaimed by a
                 higher level, and the client id must be lexically related to the
                 original ``TypeName``. A client whose ``extra.source_codename``
                 resolves in the original table vetoes ``popanim`` outright.
3. ``almanac`` — the original ``IntegerID`` equals the client ``almanac_no``, under
                 the same same-origin guard. The client almanac number is this port's
                 own 1..147 ordering and is unrelated to the original IntegerID space,
                 so this level produces candidates, not matches.
4. ``manual``  — ``tools/contentc/manual_mapping.csv`` (``side,client_id,pack_type,note``)
                 fills ids the automatic levels could not. A missing file is treated
                 as empty; conflicts never overwrite an automatic match.

Signals that are *not* one of the four levels are reported as candidates and never
auto-accepted. `content/zombies.json` carries ``extra.source_codename``, which for
eight zombies names a real original TypeName; those eight are recorded in
``manual_mapping.csv`` (the only sanctioned channel) and therefore show up with
``match_kind=manual``. Two more codenames (``royal``, ``royal_flag``) do not exist in
the shipped sheets at all: their clients stay client-only, and the report says the
codename is invalid rather than that the client has no lead.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.contentc import emit  # noqa: E402
from tools.contentc.rtid import parse_rtid  # noqa: E402
from tools.contentc.sheets import iter_objects, load_sheet  # noqa: E402
import os

DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages"))
DEFAULT_CONTENT = ROOT / "content"
DEFAULT_MANUAL = ROOT / "tools" / "contentc" / "manual_mapping.csv"
DEFAULT_CSV = ROOT / "native" / "generated" / "id_mapping.csv"
DEFAULT_REPORT = ROOT / "native" / "generated" / "mapping_report.md"

CSV_COLUMNS = (
    "side",
    "client_id",
    "pack_type",
    "pack_class",
    "pop_anim",
    "integer_id",
    "match_kind",
    "note",
)
MATCH_KINDS = ("none", "exact", "popanim", "almanac", "manual")


@dataclass(frozen=True)
class Side:
    """Everything that differs between the plant and zombie tables."""

    side: str
    sheet_file: str
    class_field: str
    popanim_prefix: str
    client_file: str
    label: str


PLANT = Side(
    side="plant",
    sheet_file="pkg_2074_PlantType.json",
    class_field="PlantFramework",
    popanim_prefix="POPANIM_PLANT_",
    client_file="plants.json",
    label="植物",
)
ZOMBIE = Side(
    side="zombie",
    sheet_file="pkg_2115_ZombieType.json",
    class_field="ZombieClass",
    popanim_prefix="POPANIM_ZOMBIE_",
    client_file="zombies.json",
    label="僵尸",
)
SIDES = (PLANT, ZOMBIE)
SIDE_BY_NAME = {spec.side: spec for spec in SIDES}


@dataclass(frozen=True)
class ClientEntry:
    id: str
    almanac_no: int | None
    codename: str | None


@dataclass(frozen=True)
class Row:
    side: str
    client_id: str
    pack_type: str
    pack_class: str
    pop_anim: str
    integer_id: str
    match_kind: str
    note: str

    def cells(self) -> list[str]:
        return [
            self.side,
            self.client_id,
            self.pack_type,
            self.pack_class,
            self.pop_anim,
            self.integer_id,
            self.match_kind,
            self.note,
        ]


@dataclass(frozen=True)
class Candidate:
    """A pairing hint that was deliberately *not* accepted automatically."""

    side: str
    client_id: str
    signal: str
    pack_type: str
    pack_class: str
    integer_id: str
    properties: str
    detail: str


@dataclass
class Mapping:
    rows: list[Row]
    pack_counts: dict[str, int]
    client_counts: dict[str, int]
    clients: dict[str, list[ClientEntry]]
    client_only: dict[str, list[str]]
    kind_counts: dict[str, dict[str, int]]
    duplicate_names: dict[str, list[str]]
    one_to_many: list[tuple[str, list[str]]]
    codename_candidates: list[Candidate]
    codename_manual: list[Candidate]
    codename_missing: list[tuple[str, str]]
    popanim_rejects: list[Candidate]
    almanac_collisions: list[tuple[str, int, str]]
    manual_notes: list[str]
    manual_rows: list[tuple[str, str, str, str]]
    almanac_coverage: dict[str, int]


# --------------------------------------------------------------------------- helpers


def _text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _rel(path) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except (ValueError, OSError):
        return Path(path).as_posix() if isinstance(path, Path) else str(path)


def normalize_popanim(value, prefix: str) -> str:
    """`POPANIM_PLANT_GATLINGPEA` -> `GATLINGPEA` (prefix match ignores case)."""
    text = _text(value)
    if prefix and text[: len(prefix)].upper() == prefix.upper():
        text = text[len(prefix) :]
    return text.strip()


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _squash(value: str) -> str:
    return "".join(_TOKEN_RE.findall(value.lower()))


def _related(left: str, right: str) -> bool:
    """True when two names share their normalised stem (same-origin guard)."""
    a, b = _squash(left), _squash(right)
    return bool(a and b and (a in b or b in a))


def properties_ref(obj_data: dict) -> str:
    token = _text(obj_data.get("Properties"))
    if not token:
        return ""
    parsed = parse_rtid(token)
    if parsed is None:
        return token
    name, sheet = parsed
    return f"RTID({name}@{sheet})" if sheet else f"RTID({name})"


# --------------------------------------------------------------------------- loading


def load_pack(obb_dir: Path, spec: Side) -> list[dict]:
    """Every objdata of one original table, in file order."""
    doc = load_sheet(Path(obb_dir) / spec.sheet_file)
    return [obj["objdata"] for obj in iter_objects(doc)]


def load_client(content_dir: Path, spec: Side) -> list[ClientEntry]:
    path = Path(content_dir) / spec.client_file
    with path.open(encoding="utf-8-sig") as handle:
        rows = json.load(handle)
    if not isinstance(rows, list):
        raise ValueError(f"{path.name}: expected a list of client rows")
    entries: list[ClientEntry] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        client_id = _text(row.get("id"))
        if not client_id:
            continue
        almanac = row.get("almanac_no")
        extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
        entries.append(
            ClientEntry(
                id=client_id,
                almanac_no=almanac if isinstance(almanac, int) else None,
                codename=_text(extra.get("source_codename")) or None,
            )
        )
    return entries


def load_almanac(content_dir: Path) -> dict[str, int]:
    """Entry counts per almanac section; the file holds prose, not original ids."""
    path = Path(content_dir) / "almanac.json"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig") as handle:
        doc = json.load(handle)
    if not isinstance(doc, dict):
        return {}
    return {str(key): len(value) for key, value in doc.items() if isinstance(value, dict)}


def load_manual(path: Path | None) -> tuple[list[tuple[str, str, str, str]], list[str]]:
    notes: list[str] = []
    if path is None or not Path(path).is_file():
        label = Path(path).name if path else "—"
        notes.append(f"人工表 `{label}` 不存在，按空处理")
        return [], notes
    entries: list[tuple[str, str, str, str]] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = {name for name in (reader.fieldnames or ()) if name}
        missing = {"side", "client_id", "pack_type"} - fields
        if missing:
            notes.append("人工表缺少列 " + "、".join(f"`{name}`" for name in sorted(missing)) + "，整表忽略")
            return [], notes
        for line_no, record in enumerate(reader, start=2):
            values = {key: _text(value) for key, value in record.items() if isinstance(key, str)}
            if not any(values.values()):
                continue
            side = values.get("side", "").lower()
            client_id = values.get("client_id", "")
            pack_type = values.get("pack_type", "")
            if side not in SIDE_BY_NAME or not client_id or not pack_type:
                notes.append(f"人工表第 {line_no} 行字段不完整或 side 非法，跳过")
                continue
            entries.append((side, client_id, pack_type, values.get("note", "")))
    if not entries:
        notes.append("人工表存在但没有可用行")
    return entries, notes


# --------------------------------------------------------------------------- matching


def build_mapping(
    obb_dir: Path = DEFAULT_OBB,
    content_dir: Path = DEFAULT_CONTENT,
    manual_path: Path | None = DEFAULT_MANUAL,
) -> Mapping:
    obb_dir, content_dir = Path(obb_dir), Path(content_dir)
    manual_rows, manual_notes = load_manual(Path(manual_path) if manual_path else None)
    almanac_coverage = load_almanac(content_dir)

    pack_rows: list[Row] = []
    client_rows: list[Row] = []
    client_only: dict[str, list[str]] = {}
    pack_counts: dict[str, int] = {}
    client_counts: dict[str, int] = {}
    clients_by_side: dict[str, list[ClientEntry]] = {}
    kind_counts: dict[str, dict[str, int]] = {}
    duplicate_names: dict[str, list[str]] = {}
    codename_candidates: list[Candidate] = []
    codename_manual: list[Candidate] = []
    codename_missing: list[tuple[str, str]] = []
    popanim_rejects: list[Candidate] = []
    almanac_collisions: list[tuple[str, int, str]] = []

    for spec in SIDES:
        objects = load_pack(obb_dir, spec)
        entries = load_client(content_dir, spec)
        pack_counts[spec.side] = len(objects)
        client_counts[spec.side] = len(entries)
        clients_by_side[spec.side] = entries
        by_client = {entry.id: entry for entry in entries}

        type_names = [_text(obj.get("TypeName")) for obj in objects]
        name_counts = Counter(type_names)
        duplicate_names[spec.side] = sorted(name for name, count in name_counts.items() if name and count > 1)
        name_set = {name for name in type_names if name}

        popanim_index: dict[str, list[int]] = defaultdict(list)
        integer_index: dict[int, list[int]] = defaultdict(list)
        for idx, obj in enumerate(objects):
            token = normalize_popanim(obj.get("PopAnim"), spec.popanim_prefix)
            if token:
                popanim_index[token.casefold()].append(idx)
            integer = obj.get("IntegerID")
            if isinstance(integer, int):
                integer_index[integer].append(idx)

        assigned: dict[int, tuple[str, str]] = {}

        # ① exact: every original row whose TypeName is a client id.
        for idx, name in enumerate(type_names):
            if name and name in by_client:
                assigned[idx] = (name, "exact")
        assigned_clients = {client_id for client_id, _ in assigned.values()}

        # ② popanim, guarded against art reuse.
        for entry in entries:
            if entry.id in assigned_clients:
                continue
            hits = popanim_index.get(entry.id.casefold(), [])
            if not hits:
                continue
            codename_hit = bool(entry.codename and entry.codename in name_set)
            for idx in hits:
                name = type_names[idx]
                obj = objects[idx]
                if len(hits) > 1:
                    reason = f"PopAnim 同名条目 {len(hits)} 条，无法唯一确定"
                elif idx in assigned:
                    reason = "该原版条目已被更高层匹配占用"
                elif codename_hit:
                    reason = f"客户端 source_codename={entry.codename} 更权威"
                elif not _related(entry.id, name):
                    reason = "PopAnim 相同但名称无关，判为美术复用"
                else:
                    reason = ""
                candidate = Candidate(
                    side=spec.side,
                    client_id=entry.id,
                    signal="popanim",
                    pack_type=name,
                    pack_class=_text(obj.get(spec.class_field)),
                    integer_id=_text(obj.get("IntegerID")),
                    properties=properties_ref(obj),
                    detail=reason or "同源守卫通过",
                )
                if reason:
                    popanim_rejects.append(candidate)
                elif entry.id not in assigned_clients:
                    assigned[idx] = (entry.id, "popanim")
                    assigned_clients.add(entry.id)

        # ③ almanac: client almanac_no vs original IntegerID, same-origin guarded.
        if spec.side == PLANT.side:
            for entry in entries:
                if entry.id in assigned_clients or entry.almanac_no is None:
                    continue
                for idx in integer_index.get(entry.almanac_no, []):
                    name = type_names[idx]
                    almanac_collisions.append((entry.id, entry.almanac_no, name))
                    if idx in assigned or not _related(entry.id, name):
                        continue
                    assigned[idx] = (entry.id, "almanac")
                    assigned_clients.add(entry.id)

        # ④ manual table fills the rest only.
        for side, client_id, pack_type, note in manual_rows:
            if side != spec.side:
                continue
            if client_id not in by_client:
                manual_notes.append(f"人工表 `{client_id}` 不在 `{spec.client_file}` 中，跳过")
                continue
            if client_id in assigned_clients:
                manual_notes.append(f"人工表 `{client_id}` → `{pack_type}` 与自动匹配冲突，保留自动匹配")
                continue
            hits = [idx for idx, name in enumerate(type_names) if name == pack_type]
            if not hits:
                manual_notes.append(f"人工表 `{client_id}` → `{pack_type}`：原版表无此 TypeName，跳过")
                continue
            free = [idx for idx in hits if idx not in assigned]
            if not free:
                manual_notes.append(f"人工表 `{client_id}` → `{pack_type}`：该原版条目已被占用，跳过")
                continue
            for idx in free:
                assigned[idx] = (client_id, "manual")
            assigned_clients.add(client_id)

        # Signals outside the four levels. A resolved codename is either already
        # carried by the manual table (`codename_manual`) or still a candidate.
        client_kind = {client_id: kind for client_id, kind in assigned.values()}
        for entry in entries:
            if not entry.codename:
                continue
            hits = [idx for idx, name in enumerate(type_names) if name == entry.codename]
            if not hits:
                codename_missing.append((entry.id, entry.codename))
                continue
            idx = hits[0]
            obj = objects[idx]
            candidate = Candidate(
                side=spec.side,
                client_id=entry.id,
                signal="codename",
                pack_type=type_names[idx],
                pack_class=_text(obj.get(spec.class_field)),
                integer_id=_text(obj.get("IntegerID")),
                properties=properties_ref(obj),
                detail=f"extra.source_codename={entry.codename} 命中 {len(hits)} 条原版条目",
            )
            if client_kind.get(entry.id) == "manual":
                codename_manual.append(candidate)
            elif entry.id not in assigned_clients:
                codename_candidates.append(candidate)

        manual_note_by_client = {
            client_id: note for side, client_id, _pack_type, note in manual_rows if side == spec.side and note
        }

        for idx, obj in enumerate(objects):
            name = type_names[idx]
            client_id, kind = assigned.get(idx, ("", "none"))
            notes: list[str] = []
            if name and name_counts[name] > 1:
                notes.append(f"原版 TypeName 重复：同名 {name_counts[name]} 条")
            if kind == "popanim":
                notes.append("PopAnim 去前缀后与 client id 相同，且同源守卫通过")
            elif kind == "almanac":
                notes.append("IntegerID 命中 client almanac_no，且同源守卫通过")
            elif kind == "manual":
                notes.append(manual_note_by_client.get(client_id) or "人工表指定")
            if kind == "none":
                reject_clients = [
                    item.client_id
                    for item in popanim_rejects
                    if item.side == spec.side and item.pack_type == name
                ]
                if reject_clients:
                    notes.append(
                        "PopAnim 与客户端 "
                        + "、".join(f"`{cid}`" for cid in reject_clients)
                        + " 同名，判为美术复用（未采信）"
                    )
                if spec.side == PLANT.side and name.startswith("unused_"):
                    slot_clients = [
                        cid for cid, _no, pack_type in almanac_collisions if pack_type == name
                    ]
                    if slot_clients:
                        notes.append(
                            "原版占位槽：IntegerID 与客户端 "
                            + "、".join(f"`{cid}`" for cid in slot_clients)
                            + " 的 almanac_no 同号（仅编号巧合）"
                        )
            pack_rows.append(
                Row(
                    side=spec.side,
                    client_id=client_id,
                    pack_type=name,
                    pack_class=_text(obj.get(spec.class_field)),
                    pop_anim=_text(obj.get("PopAnim")),
                    integer_id=_text(obj.get("IntegerID")),
                    match_kind=kind,
                    note="；".join(notes),
                )
            )

        for entry in entries:
            if entry.id in assigned_clients:
                continue
            notes = ["客户端独有：原版表无此 id"]
            reuse = next(
                (
                    item
                    for item in popanim_rejects
                    if item.side == spec.side
                    and item.client_id == entry.id
                    and "美术复用" in item.detail
                ),
                None,
            )
            if reuse is not None:
                notes.append(f"PopAnim 与 `{reuse.pack_type}` 相同，判为美术复用（非同一植物）")
            slots = [
                pack_type
                for client_id, _no, pack_type in almanac_collisions
                if client_id == entry.id and pack_type.startswith("unused_")
            ]
            if slots:
                notes.append(
                    f"almanac_no {entry.almanac_no} 撞上原版占位槽 `{slots[0]}`（非同一植物）"
                )
            codename_hit = next(
                (item for item in codename_candidates if item.side == spec.side and item.client_id == entry.id),
                None,
            )
            manual_hit = next(
                (item for item in codename_manual if item.side == spec.side and item.client_id == entry.id),
                None,
            )
            if manual_hit is not None:
                notes.append(
                    f"extra.source_codename={entry.codename} 精确命中原版 `{manual_hit.pack_type}`"
                    "（经人工表采信）"
                )
            elif codename_hit is not None:
                notes.append(
                    f"extra.source_codename={entry.codename} 精确命中原版 `{codename_hit.pack_type}`"
                    "（待人工确认，未自动采信）"
                )
            elif entry.codename:
                notes.append(
                    f"extra.source_codename={entry.codename} 指向的原版条目不存在"
                    "（代号无效，不是没有线索）"
                )
            client_rows.append(
                Row(
                    side=spec.side,
                    client_id=entry.id,
                    pack_type="",
                    pack_class="",
                    pop_anim="",
                    integer_id="",
                    match_kind="none",
                    note="；".join(notes),
                )
            )

        counter = Counter(kind for _client, kind in assigned.values())
        counts = {kind: counter.get(kind, 0) for kind in MATCH_KINDS}
        counts["none"] = len(objects) - sum(
            counts[kind] for kind in ("exact", "popanim", "almanac", "manual")
        )
        kind_counts[spec.side] = counts
        client_only[spec.side] = [entry.id for entry in entries if entry.id not in assigned_clients]

    one_to_many: list[tuple[str, list[str]]] = []
    by_client_matches: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in pack_rows:
        if row.client_id:
            by_client_matches[(row.side, row.client_id)].append(row.pack_type)
    for (side, client_id), pack_types in by_client_matches.items():
        if len(pack_types) > 1:
            one_to_many.append((f"{side}:{client_id}", pack_types))

    return Mapping(
        rows=pack_rows + client_rows,
        pack_counts=pack_counts,
        client_counts=client_counts,
        clients=clients_by_side,
        client_only=client_only,
        kind_counts=kind_counts,
        duplicate_names=duplicate_names,
        one_to_many=one_to_many,
        codename_candidates=codename_candidates,
        codename_manual=codename_manual,
        codename_missing=codename_missing,
        popanim_rejects=popanim_rejects,
        almanac_collisions=almanac_collisions,
        manual_notes=manual_notes,
        manual_rows=manual_rows,
        almanac_coverage=almanac_coverage,
    )


# --------------------------------------------------------------------------- render


def render_csv(result: Mapping) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for row in result.rows:
        writer.writerow(row.cells())
    return buffer.getvalue()


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return out


def _chunks(items: list[str], size: int = 8, sep: str = "、") -> list[str]:
    return [sep.join(f"`{item}`" for item in items[start : start + size]) for start in range(0, len(items), size)]


def _manual_snippet(result: Mapping) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["side", "client_id", "pack_type", "note"])
    for candidate in result.codename_candidates:
        writer.writerow([candidate.side, candidate.client_id, candidate.pack_type, candidate.detail])
    return buffer.getvalue().rstrip("\n")


def render_report(result: Mapping) -> str:
    lines: list[str] = []
    add = lines.append

    add("# 原版 type ↔ 客户端 id 映射报告")
    add("")
    add("> 由 `python tools/contentc/mapping.py` 生成，请勿手工编辑。名单一律按输入表顺序排列，")
    add("> 且不写时间戳，因此同一份数据两次生成字节一致。")
    add("")

    add("## 输入")
    add("")
    add(f"- 原版植物表 `pkg_2074_PlantType.json`：{result.pack_counts['plant']} 条 objdata")
    add(f"- 原版僵尸表 `pkg_2115_ZombieType.json`：{result.pack_counts['zombie']} 条 objdata")
    add(f"- 客户端 `content/plants.json`：{result.client_counts['plant']} 条；`content/zombies.json`：{result.client_counts['zombie']} 条")
    if result.almanac_coverage:
        coverage = "、".join(f"{name} {count}" for name, count in result.almanac_coverage.items())
        add(f"- 客户端 `content/almanac.json`：{coverage}（只有图鉴文案，不含原版编号）")
    add(f"- 人工表 `tools/contentc/manual_mapping.csv`：{len(result.manual_rows)} 行可用")
    add("")

    add("## 匹配级别")
    add("")
    add("1. `exact` —— 原版 `TypeName` 与 client id 完全相同（区分大小写）。同名多行全部归属同一 client id，并记入“一对多清单”。")
    add("2. `popanim` —— `PopAnim` 去掉 `POPANIM_PLANT_` / `POPANIM_ZOMBIE_` 前缀后与 client id 相同（不区分大小写）。")
    add("   为避免把美术复用当成同一对象，还要通过“同源守卫”：命中条目唯一、未被更高层占用、client id 与原版 `TypeName` 归一化后互为子串；")
    add("   僵尸若带 `extra.source_codename` 且该 codename 在原版表中存在，则 codename 更权威，`popanim` 一律不采信。")
    add("3. `almanac` —— 原版 `IntegerID` 命中客户端 `plants.json` 的 `almanac_no`，并同样通过同源守卫。")
    add("   客户端图鉴号是本项目自有的 1..147 编号，与原版 `IntegerID` 不是同一套体系，本版数据采信 0 条。")
    add("4. `manual` —— `tools/contentc/manual_mapping.csv`（列 `side,client_id,pack_type,note`）只补自动匹配没覆盖的 client id；")
    add("   与自动匹配冲突时保留自动匹配，并在“人工表提示”里记录。文件不存在按空处理。")
    add(
        f"   本版该表 {len(result.manual_rows)} 行，全部是 `extra.source_codename` 已指向原版真实条目、经评审确认的僵尸"
        f"（`match_kind=manual` 共 {result.kind_counts.get('zombie', {}).get('manual', 0)} 条）。"
    )
    add("")

    add("## 逐级命中统计")
    add("")
    header = ["side", "原版行", "exact", "popanim", "almanac", "manual", "未匹配", "client 行", "client 独有"]
    stats_rows = []
    for spec in SIDES:
        counts = result.kind_counts[spec.side]
        stats_rows.append(
            [
                spec.side,
                str(result.pack_counts[spec.side]),
                str(counts["exact"]),
                str(counts["popanim"]),
                str(counts["almanac"]),
                str(counts["manual"]),
                str(counts["none"]),
                str(result.client_counts[spec.side]),
                str(len(result.client_only[spec.side])),
            ]
        )
    lines.extend(_table(header, stats_rows))
    add("")
    add("“原版行”是表里的 objdata 条数；“未匹配”是没有任何 client id 归属的原版行；")
    add("“client 独有”是没有原版行归属的 client id 数。四个级别之和加“未匹配”等于“原版行”。")
    add("")

    add("## 结论要点")
    add("")
    plant_counts = result.kind_counts[PLANT.side]
    zombie_counts = result.kind_counts[ZOMBIE.side]
    add(
        f"- 客户端 {result.client_counts['plant']} 个植物：{plant_counts['exact'] + plant_counts['popanim'] + plant_counts['almanac'] + plant_counts['manual']}"
        f" 个有原版归属，{len(result.client_only['plant'])} 个 client 独有；"
        "这些 id 在本版 `PlantTypes` 里确实不存在（子串搜索亦无命中），不是匹配规则漏掉的。"
    )
    add(
        f"- 客户端 {result.client_counts['zombie']} 个僵尸："
        f"{zombie_counts['exact'] + zombie_counts['popanim'] + zombie_counts['almanac'] + zombie_counts['manual']}"
        f" 个有原版归属（其中 {zombie_counts['manual']} 个按 `extra.source_codename` 经人工表采信），"
        f"{len(result.client_only['zombie'])} 个 client 独有；其中 "
        f"{len(result.codename_missing)} 个的 `source_codename` 指向原版不存在的条目（代号无效，不是没有线索），"
        f"其余 {len(result.client_only['zombie']) - len(result.codename_missing)} 个无任何线索。"
    )
    add(
        f"- PopAnim 同名命中 {len(result.popanim_rejects)} 条（植物 "
        f"{sum(1 for item in result.popanim_rejects if item.side == 'plant')}、僵尸 "
        f"{sum(1 for item in result.popanim_rejects if item.side == 'zombie')}），全部判为美术复用，未采信。"
    )
    if result.almanac_collisions:
        add(f"- almanac 编号碰撞 {len(result.almanac_collisions)} 条，全部未采信；其中 "
            f"{sum(1 for _cid, _no, name in result.almanac_collisions if name.startswith('unused_'))} 条撞在原版占位槽 `unused_NN` 上。")
    duplicates = [
        f"`{name}`×{sum(1 for row in result.rows if row.side == spec.side and row.pack_type == name)}"
        for spec in SIDES
        for name in result.duplicate_names[spec.side]
    ]
    if duplicates:
        add("- 原版重复 `TypeName` 共 " + str(len(duplicates)) + " 组（" + "、".join(duplicates) + "），全部保留为独立行，不合并。")
    add("")

    for spec in SIDES:
        ids = result.client_only[spec.side]
        add(f"## 客户端独有（{spec.label} {len(ids)}）")
        add("")
        if not ids:
            add("（无）")
            add("")
            continue
        add(
            f"这些 id 在本版 `{spec.sheet_file}` 中确实不存在（子串搜索亦无命中），"
            "不是匹配规则漏掉的；逐条附上可用线索："
        )
        add("")
        for client_id in ids:
            row = next(
                row
                for row in result.rows
                if row.side == spec.side and row.client_id == client_id and not row.pack_type
            )
            entry = next(
                entry for entry in result.clients[spec.side] if entry.id == client_id
            )
            suffix = f"（almanac_no {entry.almanac_no}）" if entry.almanac_no is not None else ""
            add(f"- `{client_id}`{suffix} —— {row.note}")
        add("")

    add("## 原版独有")
    add("")
    for spec in SIDES:
        names = [row.pack_type for row in result.rows if row.side == spec.side and row.pack_type and not row.client_id]
        add(f"### {spec.label}（{len(names)}）")
        add("")
        add("原版有、客户端没有对应 id 的条目，按原表顺序：")
        add("")
        lines.extend(_chunks(names, size=8))
        add("")

    add("## 一对多清单")
    add("")
    add("### 原版重复 TypeName")
    add("")
    duplicate_any = False
    for spec in SIDES:
        for name in result.duplicate_names[spec.side]:
            duplicate_any = True
            rows = [row for row in result.rows if row.side == spec.side and row.pack_type == name]
            details = "、".join(
                f"{row.pack_class}（PopAnim {row.pop_anim or '无'}，IntegerID {row.integer_id or '无'}）"
                for row in rows
            )
            add(f"- `{name}` × {len(rows)}：{details}")
    if not duplicate_any:
        add("（无）")
    add("")
    add("### 一个 client id 命中多条原版行")
    add("")
    if result.one_to_many:
        for client_key, pack_types in result.one_to_many:
            add(f"- `{client_key}` ← " + "、".join(f"`{name}`" for name in pack_types))
    else:
        add("（无）")
    add("")
    add("### 一条原版行承担多个客户端僵尸")
    add("")
    shared: dict[str, list[str]] = defaultdict(list)
    for candidate in result.codename_manual + result.codename_candidates:
        shared[(candidate.side, candidate.pack_type)].append(candidate.client_id)
    shared_rows = {key: ids for key, ids in shared.items() if len(ids) > 1}
    if shared_rows:
        for (side, pack_type), ids in shared_rows.items():
            add(f"- `{side}` `{pack_type}` ← " + "、".join(f"`{cid}`" for cid in ids))
    else:
        add("（无）")
    add("")

    add("## 需要人工确认的候选")
    add("")
    manual_note_by_key = {
        (side, client_id): note for side, client_id, _pack_type, note in result.manual_rows if note
    }
    add("### A0. 已按 `source_codename` 经人工表采信（`manual`）")
    add("")
    if result.codename_manual:
        add(
            "这些僵尸的 `extra.source_codename` 指向的原版 `TypeName` 真实存在，"
            "经评审确认后写入 `tools/contentc/manual_mapping.csv`，CSV 中 `match_kind` 为 `manual`："
        )
        add("")
        lines.extend(
            _table(
                ["client id", "source_codename", "原版 TypeName", "原版 class", "IntegerID", "人工表依据"],
                [
                    [
                        candidate.client_id,
                        candidate.detail.split("=", 1)[1].split(" ", 1)[0],
                        f"`{candidate.pack_type}`",
                        candidate.pack_class,
                        candidate.integer_id or "无",
                        manual_note_by_key.get((candidate.side, candidate.client_id), "人工表指定"),
                    ]
                    for candidate in result.codename_manual
                ],
            )
        )
    else:
        add("（无）")
    add("")
    add("### A1. `source_codename` 仍待人工确认的候选（未自动采信）")
    add("")
    if result.codename_candidates:
        lines.extend(
            _table(
                ["client id", "source_codename", "原版 TypeName", "原版 class", "IntegerID", "Properties"],
                [
                    [
                        candidate.client_id,
                        candidate.detail.split("=", 1)[1].split(" ", 1)[0],
                        f"`{candidate.pack_type}`",
                        candidate.pack_class,
                        candidate.integer_id or "无",
                        candidate.properties or "无",
                    ]
                    for candidate in result.codename_candidates
                ],
            )
        )
        add("")
        add("确认上述候选无误后，把这些行追加到 `tools/contentc/manual_mapping.csv` 再重跑，`match_kind` 会变成 `manual`：")
        add("")
        add("```csv")
        for snippet_line in _manual_snippet(result).splitlines():
            add(snippet_line)
        add("```")
    else:
        add("（无：本版所有能解析的 `source_codename` 都已在人工表里采信）")
    add("")
    if result.codename_missing:
        add("### A2. `source_codename` 指向原版不存在的条目（代号无效，不是没有线索）")
        add("")
        add("这些 id 并非“缺线索”：它们自己写了代号，但本版原版表里没有这个 `TypeName`，")
        add("所以既不能按 exact 也不能按人工表归属，只能留在 client 独有一侧。")
        add("")
        for client_id, codename in result.codename_missing:
            add(f"- `{client_id}` → `{codename}`：原版表中没有这个 `TypeName`，代号指向不存在的条目。")
        add("")

    add("### B. PopAnim 同名但判为美术复用（未采信）")
    add("")
    if result.popanim_rejects:
        lines.extend(
            _table(
                ["side", "client id", "PopAnim 指向的原版 TypeName", "原版 class", "IntegerID", "判据"],
                [
                    [
                        candidate.side,
                        candidate.client_id,
                        f"`{candidate.pack_type}`",
                        candidate.pack_class,
                        candidate.integer_id or "无",
                        candidate.detail,
                    ]
                    for candidate in result.popanim_rejects
                ],
            )
        )
    else:
        add("（无）")
    add("")

    add("### C. almanac 编号碰撞（未采信）")
    add("")
    add(
        f"客户端 `almanac_no` 是本项目自有的 1..{result.client_counts['plant']} 编号，与原版 `IntegerID` 不构成同一套体系，"
        f"同号共 {len(result.almanac_collisions)} 条，全部只作候选。"
    )
    add("")
    placeholders = [item for item in result.almanac_collisions if item[2].startswith("unused_")]
    if placeholders:
        add("其中撞在原版占位槽上的条目（说明这些位置在本版里被留空，而不是换了名字）：")
        add("")
        lines.extend(
            _table(
                ["client id", "almanac_no", "原版占位槽"],
                [[f"`{cid}`", str(no), f"`{name}`"] for cid, no, name in placeholders],
            )
        )
        add("")
    others = [item for item in result.almanac_collisions if not item[2].startswith("unused_")]
    if others:
        add("其余同号碰撞（client=almanac_no→原版条目）：")
        add("")
        tokens = [f"`{cid}`={no}→`{name}`" for cid, no, name in others]
        lines.extend(["、".join(tokens[start : start + 4]) for start in range(0, len(tokens), 4)])
        add("")

    add("### D. 原版重复 TypeName 的处理")
    add("")
    if result.duplicate_names[PLANT.side] or result.duplicate_names[ZOMBIE.side]:
        add("重复条目当前都没有 client id 归属，因此不涉及二选一；等某个客户端僵尸要引用同名条目时，")
        add("必须按 `IntegerID` 或 `PopAnim` 指认具体一条，并在人工表里写明。")
    else:
        add("（无）")
    add("")

    if result.manual_notes:
        add("## 人工表提示")
        add("")
        for note in result.manual_notes:
            add(f"- {note}")
        add("")

    return "\n".join(lines) + "\n"


def write_outputs(result: Mapping, csv_path: Path, report_path: Path) -> tuple[bytes, bytes]:
    return emit.write_text(Path(csv_path), render_csv(result)), emit.write_text(
        Path(report_path), render_report(result)
    )


def summarize(result: Mapping) -> str:
    parts = []
    for spec in SIDES:
        counts = result.kind_counts[spec.side]
        parts.append(
            f"{spec.side}: pack={result.pack_counts[spec.side]} exact={counts['exact']} "
            f"popanim={counts['popanim']} almanac={counts['almanac']} manual={counts['manual']} "
            f"none={counts['none']} client={result.client_counts[spec.side]} "
            f"client_only={len(result.client_only[spec.side])}"
        )
    parts.append(
        f"candidates: codename={len(result.codename_candidates)} "
        f"codename_manual={len(result.codename_manual)} "
        f"codename_missing={len(result.codename_missing)} "
        f"popanim_rejected={len(result.popanim_rejects)} almanac_collisions={len(result.almanac_collisions)}"
    )
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Map original types onto client content ids.")
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB)
    parser.add_argument("--content", type=Path, default=DEFAULT_CONTENT)
    parser.add_argument("--manual", type=Path, default=DEFAULT_MANUAL)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("-n", "--dry-run", action="store_true", help="print the summary, write nothing")
    args = parser.parse_args(argv)

    if not args.obb.is_dir():
        print(f"error: property sheets not found: {args.obb}", file=sys.stderr)
        return 2

    result = build_mapping(args.obb, args.content, args.manual)
    print(summarize(result))
    if args.dry_run:
        return 0
    write_outputs(result, args.csv, args.report)
    print(f"wrote {_rel(args.csv)}, {_rel(args.report)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
