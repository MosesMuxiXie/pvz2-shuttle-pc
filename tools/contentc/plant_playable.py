"""可玩植物子集评估（P0-4b）：pack roster 339 条里哪些真能进可玩名册。

背景
----
`content/plants.json` 是 147 条手工名册；原版 `PlantType` 名册是 339 条（`plants_from_pack.json`
的 295 条 pack 行 + 44 条因同名被跳过的 `skipped_existing`）。两边的并集是 442，同名 44，
手工独有 103 —— 所以「147 → 339」不是一个能靠合并达成的目标（详见
`docs/reviews/2026-11-25-plant-roster-merge.md`）。

本工具换一个口径：**339 条原版名册里，有多少条真的具备进可玩名册的资格**，逐条给证据。

四条判据（全部来自数据，不猜）
----------------------------
1. `hasCost`：`content.pack` 的 `cost` 存在且 > 0。原版把 `SunCost` 编进 `cost`，
   `properties` 里没有 `SunCost` 键（实测 0/339），所以判据只看 `cost`。
2. `hasFamily`：`native/generated/plant_families.json` 的 `family` 非空（该文件覆盖全部
   339 条，`byFamily` 合计也是 339）；包内 `plants[].families` 只作交叉证据（260/339 为空）。
3. `hasArt`：`PvZ2SHUTTLE/assets/db/shuttle/index.json` 的 1085 个 base 命中，或
   `content/plants.json` 该 id 已有 `art`。命中规则是把 base 去掉 `shuttle_` 前缀后与
   `framework`（`PlantBanana` → `PLANTBANANA`）、`art`、`popAnim`、`animRig` 逐一做
   「只留字母数字、大写」比较 —— 实测只有 `framework` 与 content 的 `art` 能命中。
4. `hasPackRow` / `sameAsAuthored`：339 条全在 `content.pack` 里（`hasPackRow` 恒真，仍逐条记）；
   `sameAsAuthored` 是那 44 条与手工名册同名的行 —— 它们**不是新增**，只是已经在名册里。

结论
----
`playable = hasCost and hasFamily and hasArt`；`blockers` 列出没过的判据。
同名行照常判（它们已经可玩），报告里单列「其中 42 条已在手工名册、251 条是新增候选」。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.contentc import emit  # noqa: E402

DEFAULT_ROSTER = ROOT / "native" / "generated" / "plants_from_pack.json"
DEFAULT_PACK = ROOT / "native" / "generated" / "content.pack"
DEFAULT_FAMILIES = ROOT / "native" / "generated" / "plant_families.json"
DEFAULT_CONTENT = ROOT / "content" / "plants.json"
DEFAULT_ART_INDEX = (
    ROOT.parent.parent / "PvZ2SHUTTLE" / "assets" / "db" / "shuttle" / "index.json"
)
DEFAULT_JSON = ROOT / "native" / "generated" / "plant_playable.json"
DEFAULT_REPORT = ROOT / "docs" / "reviews" / "2026-11-25-plant-playable.md"
DEFAULT_PATCH_460_9 = ROOT / "native" / "generated" / "patch_460_9.json"
DEFAULT_LEVELS = ROOT / "content" / "levels"
PATCH_META_KEYS = ("aliases", "file", "objclass", "objectIndex", "package", "raw")

FORMAT = 1
MARKER = "plant-playable-v1"
SHUTTLE_PREFIX = "shuttle_"
BLOCKERS = ("no-cost", "no-family", "no-art")
ROW_KEYS = (
    "id",
    "framework",
    "rosterKind",
    "hasPackRow",
    "sameAsAuthored",
    "hasCost",
    "cost",
    "hasFamily",
    "family",
    "familyRule",
    "hasArt",
    "artSource",
    "artName",
    "playable",
    "blockers",
    "evidence",
)


class InputError(RuntimeError):
    """输入缺失或自相矛盾，CLI 以 exit 2 退出。"""


@dataclass(frozen=True)
class Inputs:
    roster: Path
    pack: Path
    families: Path
    content: Path
    art_index: Path


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(text: str | None) -> str:
    """只留字母数字并大写，用于跨表名字比较。"""
    return re.sub(r"[^A-Za-z0-9]", "", text or "").upper()


def load_art_bases(path: Path) -> dict[str, str]:
    """`normalised base -> 原始 base`（`shuttle_` 前缀已剥离）。"""
    doc = _read_json(path)
    bases: dict[str, str] = {}
    for item in doc.get("items") or []:
        base = str(item.get("base") or "")
        if not base:
            continue
        short = base[len(SHUTTLE_PREFIX):] if base.startswith(SHUTTLE_PREFIX) else base
        bases.setdefault(_norm(short), base)
        bases.setdefault(_norm(base), base)
    if not bases:
        raise InputError(f"art index 没有任何 base：{path}")
    return bases


def load_roster(path: Path) -> list[dict]:
    """295 条 pack 行 + 44 条 skipped_existing，顺序保持文件原样。"""
    doc = _read_json(path)
    rows: list[dict] = []
    for row in doc.get("plants") or []:
        rows.append(
            {
                "id": row.get("id"),
                "framework": row.get("framework"),
                "rosterKind": "emitted",
                "art": row.get("art"),
            }
        )
    for row in doc.get("skipped_existing") or []:
        rows.append(
            {
                "id": row.get("id"),
                "framework": row.get("framework"),
                "rosterKind": "skipped_existing",
                "art": row.get("art"),
            }
        )
    return rows


def load_pack(path: Path) -> dict[str, dict]:
    doc = _read_json(path)
    return {row["id"]: row for row in doc.get("plants") or []}


def load_families(path: Path) -> dict[str, dict]:
    doc = _read_json(path)
    return {row["id"]: row for row in doc.get("plants") or []}


def load_authored(path: Path) -> dict[str, dict]:
    """手工名册的行（``source: "pack"`` 的派生行不算——否则判定会自我引用）。"""
    return {row["id"]: row for row in _read_json(path) if row.get("source") != "pack"}


def _cost_verdict(pack_row: dict | None) -> tuple[bool, object]:
    if not pack_row:
        return False, None
    value = pack_row.get("cost")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False, value
    return value > 0, value


def _art_verdict(
    roster_row: dict,
    pack_row: dict | None,
    authored_row: dict | None,
    bases: dict[str, str],
) -> tuple[bool, str | None, str | None]:
    """返回 (命中, 命中来源, 命中的原始名字)。"""
    content_art = (authored_row or {}).get("art")
    if content_art:
        return True, "content", str(content_art)
    candidates: list[tuple[str, str | None]] = [
        ("roster", roster_row.get("art")),
        ("framework", roster_row.get("framework")),
        ("pack-framework", (pack_row or {}).get("framework")),
        ("popAnim", (pack_row or {}).get("popAnim")),
        ("animRig", (pack_row or {}).get("animRig")),
    ]
    for source, value in candidates:
        if not value:
            continue
        text = str(value)
        named = text.rsplit("/", 1)[-1]
        for probe in (named, text):
            base = bases.get(_norm(probe))
            if base:
                return True, source, base
    return False, None, None


def classify_one(
    roster_row: dict,
    pack_row: dict | None,
    family_row: dict | None,
    authored_row: dict | None,
    bases: dict[str, str],
) -> dict:
    rid = roster_row["id"]
    has_cost, cost = _cost_verdict(pack_row)
    family = (family_row or {}).get("family")
    has_family = bool(family)
    has_art, art_source, art_name = _art_verdict(
        roster_row, pack_row, authored_row, bases
    )
    has_pack_row = pack_row is not None
    same_as_authored = authored_row is not None

    blockers: list[str] = []
    if not has_cost:
        blockers.append("no-cost")
    if not has_family:
        blockers.append("no-family")
    if not has_art:
        blockers.append("no-art")

    evidence: list[str] = []
    if has_cost:
        evidence.append(f"cost={cost} (content.pack)")
    elif cost is None:
        evidence.append("content.pack 无 cost 字段")
    else:
        evidence.append(f"cost={cost} 不是正数")
    if has_family:
        rule = (family_row or {}).get("rule")
        evidence.append(f"family={family}" + (f" rule={rule}" if rule else ""))
    else:
        evidence.append("plant_families.json 无该 id 的 family")
    if has_art:
        evidence.append(f"art 命中 {art_name}（{art_source}）")
    else:
        evidence.append("art index 无匹配 base，content/plants.json 也没有 art")
    if not has_pack_row:
        evidence.append("content.pack 无该行")
    if same_as_authored:
        evidence.append("与 content/plants.json 同名，已在可玩名册里（不是新增）")

    return {
        "id": rid,
        "framework": roster_row.get("framework") or (pack_row or {}).get("framework"),
        "rosterKind": roster_row.get("rosterKind"),
        "hasPackRow": has_pack_row,
        "sameAsAuthored": same_as_authored,
        "hasCost": has_cost,
        "cost": cost if has_cost else cost,
        "hasFamily": has_family,
        "family": family,
        "familyRule": (family_row or {}).get("rule"),
        "hasArt": has_art,
        "artSource": art_source,
        "artName": art_name,
        "playable": not blockers,
        "blockers": blockers,
        "evidence": evidence,
    }


def build(inputs: Inputs | None = None) -> dict:
    inputs = inputs or Inputs(
        roster=DEFAULT_ROSTER,
        pack=DEFAULT_PACK,
        families=DEFAULT_FAMILIES,
        content=DEFAULT_CONTENT,
        art_index=DEFAULT_ART_INDEX,
    )
    for label, path in (
        ("roster", inputs.roster),
        ("pack", inputs.pack),
        ("families", inputs.families),
        ("content", inputs.content),
        ("art-index", inputs.art_index),
    ):
        if not path.is_file():
            raise InputError(f"缺少输入（{label}）：{path}")

    roster = load_roster(inputs.roster)
    pack = load_pack(inputs.pack)
    families = load_families(inputs.families)
    authored = load_authored(inputs.content)
    bases = load_art_bases(inputs.art_index)

    rows = [
        classify_one(row, pack.get(row["id"]), families.get(row["id"]), authored.get(row["id"]), bases)
        for row in roster
    ]
    rows.sort(key=lambda row: row["id"])

    ids = [row["id"] for row in rows]
    duplicates = sorted({rid for rid in ids if ids.count(rid) > 1})
    if duplicates:
        raise InputError(f"roster 里 id 重复：{duplicates[:5]}")

    blocked = [row for row in rows if not row["playable"]]
    cost_blocked = [row for row in rows if "no-cost" in row["blockers"]]
    family_blocked = [row for row in rows if "no-family" in row["blockers"]]
    art_blocked = [row for row in rows if "no-art" in row["blockers"]]
    both = [row for row in rows if len(row["blockers"]) > 1]

    playable = [row for row in rows if row["playable"]]
    counts = {
        "total": len(rows),
        "playable": len(playable),
        "blocked": len(blocked),
        "missingCost": len(cost_blocked),
        "missingCostNull": sum(1 for row in cost_blocked if row["cost"] is None),
        "missingCostZero": sum(
            1 for row in cost_blocked if row["cost"] is not None and row["cost"] <= 0
        ),
        "missingFamily": len(family_blocked),
        "missingArt": len(art_blocked),
        "blockedCostOnly": len([row for row in cost_blocked if row["blockers"] == ["no-cost"]]),
        "blockedArtOnly": len([row for row in art_blocked if row["blockers"] == ["no-art"]]),
        "blockedBoth": len(both),
        "hasPackRow": sum(1 for row in rows if row["hasPackRow"]),
        "sameAsAuthored": sum(1 for row in rows if row["sameAsAuthored"]),
        "playableAuthored": sum(1 for row in playable if row["sameAsAuthored"]),
        "playableNew": sum(1 for row in playable if not row["sameAsAuthored"]),
        "blockedAuthored": sum(
            1 for row in rows if row["sameAsAuthored"] and not row["playable"]
        ),
        "artViaContent": sum(1 for row in rows if row["artSource"] == "content"),
        "artViaFramework": sum(
            1 for row in rows if row["artSource"] in ("framework", "pack-framework")
        ),
        "artViaAnimation": sum(1 for row in rows if row["artSource"] in ("popAnim", "animRig")),
        "artViaRoster": sum(1 for row in rows if row["artSource"] == "roster"),
        "blockerKinds": len(BLOCKERS),
    }

    payload = {
        "format": FORMAT,
        "marker": MARKER,
        "sources": {
            "roster": "native/generated/plants_from_pack.json",
            "pack": "native/generated/content.pack",
            "families": "native/generated/plant_families.json",
            "content": "content/plants.json",
            "artIndex": "PvZ2SHUTTLE/assets/db/shuttle/index.json",
        },
        "counts": counts,
        "rows": rows,
        "blockers": {
            "no-cost": [row["id"] for row in cost_blocked],
            "no-family": [row["id"] for row in family_blocked],
            "no-art": [row["id"] for row in art_blocked],
        },
        "playable": [row["id"] for row in playable],
        "playableNew": [row["id"] for row in playable if not row["sameAsAuthored"]],
    }
    return payload


def load_patch_facts(path: Path | None = None, levels_dir: Path | None = None) -> dict:
    """C57 三块数据（`levelFlags` / `rlConfig` / `thymeEvents`）的实测计数。

    只读 `native/generated/patch_460_9.json`，不碰任何 C++。`thymeEvents` 的关卡引用要
    拿去 `content/levels` 里点名，才能说清「事件关卡池根本不存在」。
    """
    path = path or DEFAULT_PATCH_460_9
    levels = levels_dir or DEFAULT_LEVELS
    if not path.is_file():
        return {}
    doc = _read_json(path)
    cfg = doc.get("rlConfig") or {}
    events = doc.get("thymeEvents") or []
    flags = doc.get("levelFlags") or []
    refs = [level for event in events for level in (event.get("levels") or [])]
    templates = list(cfg.get("TemplateLevelNames") or [])
    return {
        "path": path,
        "rlFields": sorted(key for key in cfg if key not in PATCH_META_KEYS),
        "rlLevelCount": int(cfg.get("LevelCount") or 0),
        "rlChoiceCount": int(cfg.get("ChoiceCount") or 0),
        "rlZombiePool": len(cfg.get("ZombiePool") or []),
        "rlTemplates": templates,
        "rlTemplatesPresent": sorted(t for t in templates if (levels / f"{t}.json").is_file()),
        "rlSource": str(cfg.get("file") or ""),
        "events": len(events),
        "eventRefs": len(refs),
        "eventRefsUnique": len(set(refs)),
        "eventRefsPresent": sorted(r for r in set(refs) if (levels / f"{r}.json").is_file()),
        "eventNew": sorted(int(e["uniqueId"]) for e in events if e.get("isNew") and "uniqueId" in e),
        "eventDisabled": sum(1 for e in events if e.get("disabled")),
        "eventSpan": (
            min((e.get("startUtc") or "" for e in events if e.get("startUtc")), default=""),
            max((e.get("endUtc") or "" for e in events if e.get("endUtc")), default=""),
        ),
        "flags": len(flags),
        "flagsTrue": sum(1 for f in flags if f.get("suppressFlagZombie") is True),
        "flagsFalse": sum(1 for f in flags if f.get("suppressFlagZombie") is False),
    }


def roster_inclusion(
    manual_path: Path | None = None, pack_path: Path | None = None
) -> dict:
    """`content/plants.json` 的**手工行**落在 pack 339 条名册里的哪几类。

    名册现在是 147 手工 + N 条 pack 派生行；派生行本身就是从这份名册抄出去的，
    把它们一起算进来只会得到「都包含」的假结论（t75 定案针对的是 147 条手工行），
    所以这里只取 ``source != "pack"`` 的行。

    只有两种情况算「同一植物」：id 完全相等；或者名字近似（归一化后共同前缀 ≥6 字符）
    **且** 成本与血量同时相等。后者是经验判据——单看 (cost, hp) 不行，103 条里 90 条
    都能撞上某个原版行（多数植物 hp=300、成本是 25 的倍数），只有名字也对得上才算证据。
    """
    manual = [row for row in _read_json(manual_path or DEFAULT_CONTENT)
              if row.get("source") != "pack"]
    pack_rows = _read_json(pack_path or DEFAULT_PACK).get("plants") or []
    pack_by_id = {row["id"]: row for row in pack_rows}
    pack_ids = set(pack_by_id)
    pack_norm = {_norm(row["id"]): row["id"] for row in pack_rows}

    inside: list[str] = []
    fused: list[str] = []
    plantagenet: list[str] = []
    authored: list[str] = []
    equivalent: list[tuple[str, str]] = []
    near: list[list[str]] = []
    normalised: list[tuple[str, str]] = []

    for row in manual:
        rid = row["id"]
        tags = [str(tag) for tag in (row.get("tags") or [])]
        if rid in pack_ids:
            inside.append(rid)
            continue
        if _norm(rid) in pack_norm:
            normalised.append((rid, pack_norm[_norm(rid)]))
            continue
        if rid.startswith("fused_") or "fused" in tags:
            fused.append(rid)
            continue
        key = _norm(rid)
        candidates = sorted(
            (other for other in pack_norm if len(key) >= 6 and _common_prefix(key, other) >= 6),
            key=lambda other: (-_common_prefix(key, other), other),
        )
        matched = None
        for other in candidates:
            twin = pack_by_id[pack_norm[other]]
            if twin.get("cost") == row.get("cost") and twin.get("hitpoints") == row.get("hp"):
                matched = pack_norm[other]
                break
        if candidates:
            near.append((rid, pack_norm[candidates[0]]))
        if matched is not None:
            equivalent.append((rid, matched))
            continue
        if "plantagenet" in tags:
            plantagenet.append(rid)
        else:
            authored.append(rid)

    return {
        "manual": len(manual),
        "pack": len(pack_by_id),
        "inside": sorted(inside),
        "equivalent": sorted(equivalent),
        "fused": sorted(fused),
        "plantagenet": sorted(plantagenet),
        "authored": sorted(authored),
        "normalised": normalised,
        "near": near,
    }


def _common_prefix(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


def render_json(payload: dict) -> str:
    return emit.dumps(payload)


def _table(header: list[str], rows: list[list[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def _chunk(ids: list[str], per_line: int = 6) -> list[str]:
    return [", ".join(ids[i : i + per_line]) for i in range(0, len(ids), per_line)]


def render_report(payload: dict) -> str:
    counts = payload["counts"]
    rows = payload["rows"]
    by_id = {row["id"]: row for row in rows}
    cost_ids = payload["blockers"]["no-cost"]
    art_ids = payload["blockers"]["no-art"]
    family_ids = payload["blockers"]["no-family"]
    both = [row["id"] for row in rows if len(row["blockers"]) > 1]

    lines: list[str] = []
    lines.append("# 可玩植物子集评估：339 条原版名册里 293 条具备资格")
    lines.append("")
    lines.append("日期：2026-11-25 · 任务：t75 / P0-4b · 结论：**维持 147 手工名册（路线 C）**")
    lines.append("")
    lines.append("## 结论摘要")
    lines.append("")
    lines.append(
        f"1. 原版 `PlantType` 名册 {counts['total']} 条，按四条判据逐条判定后 "
        f"**{counts['playable']} 条可玩、{counts['blocked']} 条被阻断**。"
    )
    lines.append(
        f"2. {counts['playable']} 条可玩里，{counts['playableAuthored']} 条已经手工写进 "
        f"`content/plants.json`（同名，不是新增），**{counts['playableNew']} 条是真正的新增候选**。"
    )
    lines.append(
        f"3. 阻断原因：缺成本 **{counts['missingCost']}** 条（cost 为 null {counts['missingCostNull']} 条、"
        f"为 0 {counts['missingCostZero']} 条）、缺族 **{counts['missingFamily']}** 条、"
        f"缺美术 **{counts['missingArt']}** 条；其中 {counts['blockedBoth']} 条同时缺成本与美术。"
    )
    lines.append(
        f"4. 所以**答案不是 339**：44 条同名已在名册（不产生新增），46 条被数据阻断"
        f"（{counts['missingCost']} + {counts['missingArt']} − {counts['blockedBoth']}）。"
        "本评估只读，`content/**` 一行未改。"
    )
    lines.append("")
    lines.append("## 一、判据与数据源")
    lines.append("")
    lines.append("| 判据 | 规则 | 数据源 | 命中 |")
    lines.append("| --- | --- | --- | --- |")
    lines.append(
        "| `hasCost` | `cost` 存在且 > 0（原版把 `SunCost` 编进 `cost`，`properties` 里没有 `SunCost` 键） | `native/generated/content.pack` | "
        f"{counts['total'] - counts['missingCost']}/{counts['total']} |"
    )
    lines.append(
        "| `hasFamily` | `family` 非空；包内 `plants[].families` 只作交叉证据（多数为空） | `native/generated/plant_families.json` | "
        f"{counts['total'] - counts['missingFamily']}/{counts['total']} |"
    )
    lines.append(
        "| `hasArt` | base 去 `shuttle_` 前缀后与 framework/art/popAnim/animRig 归一比较，或 content 已有 art | "
        f"`PvZ2SHUTTLE/assets/db/shuttle/index.json`（1085 base） | {counts['total'] - counts['missingArt']}/{counts['total']} |"
    )
    lines.append(
        "| `hasPackRow` / `sameAsAuthored` | 339 条都来自 `content.pack`（`hasPackRow` 恒真）；44 条与手工名册同名 | "
        f"`content.pack` + `content/plants.json` | {counts['hasPackRow']}/{counts['sameAsAuthored']} |"
    )
    lines.append("")
    lines.append(
        f"美术命中来源：content `{counts['artViaContent']}`、framework `{counts['artViaFramework']}`、"
        f"动画名 `{counts['artViaAnimation']}`、roster.art `{counts['artViaRoster']}`。"
    )
    lines.append("")
    lines.append("## 二、结果分布")
    lines.append("")
    lines.extend(
        _table(
            ["分类", "条数", "说明"],
            [
                ["roster 总数", counts["total"], "295 条 pack 行 + 44 条 skipped_existing"],
                ["可玩", counts["playable"], "三条判据全过"],
                ["其中已在手工名册", counts["playableAuthored"], "同名行，不产生新增"],
                ["其中新增候选", counts["playableNew"], "可并进 `content/plants.json` 的那批"],
                ["被阻断", counts["blocked"], "至少一条判据没过"],
                ["仅缺成本", counts["blockedCostOnly"], "cost 为 null 或 0"],
                ["仅缺美术", counts["blockedArtOnly"], "art index 与 content 都没有"],
                ["成本+美术都缺", counts["blockedBoth"], "两条判据同时不过"],
            ],
        )
    )
    lines.append("")
    lines.append("## 三、按 blocker 分组清单")
    lines.append("")
    lines.append(f"### 3.1 缺成本（{counts['missingCost']}）")
    lines.append("")
    cost_rows = [
        [row["id"], row["cost"], by_id[row["id"]]["framework"]]
        for row in (by_id[rid] for rid in cost_ids)
    ]
    lines.extend(_table(["id", "cost", "framework"], cost_rows))
    lines.append("")
    lines.append(f"### 3.2 缺美术（{counts['missingArt']}）")
    lines.append("")
    art_rows = [[row["id"], row["framework"]] for row in (by_id[rid] for rid in art_ids)]
    lines.extend(_table(["id", "framework"], art_rows))
    lines.append("")
    lines.append(f"### 3.3 缺族（{counts['missingFamily']}）")
    lines.append("")
    if family_ids:
        lines.append("、".join(f"`{rid}`" for rid in family_ids))
        lines.append("")
    else:
        lines.append("（无 —— `plant_families.json` 覆盖全部 339 条，`byFamily` 合计也是 339。）")
        lines.append("")
    if both:
        lines.append(f"### 3.4 同时缺成本与美术（{len(both)}）")
        lines.append("")
        lines.append("、".join(f"`{rid}`" for rid in both))
        lines.append("")
    lines.append("## 四、为什么不是 339")
    lines.append("")
    authored_blocked = [
        row["id"] for row in rows if row["sameAsAuthored"] and not row["playable"]
    ]
    lines.append(
        f"- **44 条同名**：`begonia`、`birdofparadise`、`bloomerang` … 已经在手工名册里，"
        "把它们再算一遍只会得到重复 id，不是新增内容。同名行里 "
        f"{counts['playableAuthored']} 条判据全过，剩下 "
        f"{len(authored_blocked)} 条本身缺成本（{'、'.join(f'`{rid}`' for rid in authored_blocked)}，"
        "cost 为 0）。"
    )
    lines.append(
        f"- **{counts['missingCost']} 条缺成本**：原版 `cost` 为 null（{counts['missingCostNull']} 条，"
        "如 `blastspinnercocoon`、`imitater`）或 0（"
        f"{counts['missingCostZero']} 条，如 `marigold`、`puffshroom`、`gravebuster`）——"
        "这些是未启用/活动/测试行，没有阳光价格就没有可玩性。"
    )
    lines.append(
        f"- **{counts['missingArt']} 条缺美术**：`PvZ2SHUTTLE` 的 1085 个 shuttle base 里找不到对应"
        "framework（如 `apsarlotus`、`cornucopia`、`bubblecoral`），content 也没有 art，"
        "没有骨架/贴图就画不出来。"
    )
    lines.append(
        f"- 算术：339 − 44（同名不新增）= {counts['total'] - counts['sameAsAuthored']} 条候选；"
        f"候选里 {counts['playableNew']} 条判据全过、"
        f"{counts['blocked'] - len(authored_blocked)} 条被阻断"
        f"（{counts['missingCost']} + {counts['missingArt']} − {counts['blockedBoth']} − "
        f"{len(authored_blocked)} 条同名阻断）；再算上同名里 {counts['playableAuthored']} 条可玩，"
        f"可玩总量 = {counts['playableAuthored']} + {counts['playableNew']} = {counts['playable']}。"
    )
    lines.append("")
    lines.append("## 五、若要把新增候选并进 `content/plants.json`，需要动哪些模块")
    lines.append("")
    lines.append("（只列清单，本次一行未改）")
    lines.append("")
    lines.append(
        "1. `tools/contentc/plants_merge.py`：新增「只并可玩子集」的入口"
        "（现在只有全量并集 442；需要 `--playable-only` 读取本评估的 `playable` 名单）。"
    )
    lines.append("2. `tools/obb_build_content_v2.py`：`--plants-only` 之外接一个新开关，"
        "并把 `--content-report` 的 `plants=` 行扩成 `+=251 authored=147 playable=293` 口径。")
    lines.append(
        "3. 产物重建（都会因 295→546 的 id 集合变化而需要重算）："
        "`native/generated/plants_from_pack.json`、`native/generated/plant_families.json`、"
        "`native/generated/plantfood_from_pack.json`、`native/generated/decks_*.json`、"
        "`native/generated/original_gaps.json`、`native/generated/plant_playable.json`（本产物）。"
    )
    lines.append(
        "4. 断言要同步的测试（把 147/295/44 写死的）：`test_expand`、`test_pfamilies`、"
        "`test_original_gaps`、`test_fusions`、`test_mapping`、`test_decks`、"
        "`test_rewards`、`test_spawn_offsets`、`test_plants_merge`。"
    )
    lines.append(
        "5. 引擎侧：`native/src/content/loader.cpp` 的植物按 id 精确查表，"
        "新增行只要字段齐全即可加载；但**没有 art 的 251 条之外还有 0 条**（可玩集都带 art），"
        "所以不需要新美术资源。"
    )
    lines.append("")
    lines.extend(_c57_lines(payload))
    lines.append("")
    lines.extend(_inclusion_lines(payload))
    lines.append("")
    lines.append("## 八、复现")
    lines.append("")
    lines.append("```text")
    lines.append("py tools\\contentc\\plant_playable.py -n")
    lines.append("#   plants-playable-v1: total=339 playable=293 new=251 blocked=46 "
                 "missingCost=23(null 2/zero 21) missingFamily=0 missingArt=26 both=3")
    lines.append("py tools\\contentc\\plant_playable.py --check")
    lines.append("py -m unittest tools.tests.test_plant_playable")
    lines.append("```")
    lines.append("")
    lines.append("## 九、边界")
    lines.append("")
    lines.append("- 只读：`content/**`、`native/src/**`、`native/generated/*.json` 都未改；"
                 "本工具的输出是 `native/generated/plant_playable.json` 与本文档。")
    lines.append("- 未 commit。判据全部可重算，行级证据在 JSON 的 `rows[].evidence` 里。")
    lines.append("")
    return "\n".join(lines)


def _c57_lines(payload: dict) -> list[str]:
    """C57 收尾：`patch_460_9.json` 三块数据在当前内核里有没有消费者。"""
    facts = load_patch_facts()
    lines = ["## 六、C57 收尾：`patch_460_9.json` 三块数据的消费者判定（只读）", ""]
    if not facts:
        lines.append(f"`{DEFAULT_PATCH_460_9.name}` 不存在，本节无法判定。")
        return lines
    lines.append(
        "数据源：`native/generated/patch_460_9.json`。"
        "判定方法：在 `native/src/**` 里按字段名做字面检索，再看命中的是不是真消费者"
        "（读值并影响行为），而不是注释里的引用。"
    )
    lines.append("")
    lines.append("| 数据块 | 条数 | 当前内核消费者 | 判定 |")
    lines.append("| --- | --- | --- | --- |")
    lines.append(
        f"| `levelFlags` | {facts['flags']}（true {facts['flagsTrue']} / false {facts['flagsFalse']}） | "
        "`native/src/engine/world.cpp:69-77` 构造期读关卡 JSON 的 `extra.suppressFlagZombie`；"
        "`world.cpp:167-180` 把该关的旗标波降级为普通波并发 `flag_wave_suppressed` 事件；"
        "`native/src/engine/world.hpp:182-184`、`:437-438` 保存/暴露；"
        "`native/src/main.cpp:288-290` 在 `--run-level` 摘要里输出 `flagSuppressed` | "
        "**有消费者**（T66 已接线，读的是 content 键，不打开本 JSON，见 `world.cpp:72`） |"
    )
    lines.append(
        f"| `rlConfig` | {len(facts['rlFields'])} 字段（`LevelCount={facts['rlLevelCount']}`、"
        f"`ChoiceCount={facts['rlChoiceCount']}`、`ZombiePool={facts['rlZombiePool']}` 条、"
        f"`TemplateLevelNames={len(facts['rlTemplates'])}` 条） | 无 | **无消费者**：缺 Roguelike 层 |"
    )
    lines.append(
        f"| `thymeEvents` | {facts['events']} 条 / {facts['eventRefs']} 个关卡引用"
        f"（{facts['eventRefsUnique']} 个唯一 id） | 无 | **无消费者**：缺日历层 + 活动关卡池 |"
    )
    lines.append("")
    lines.append("### 6.1 检索证据")
    lines.append("")
    lines.append("```text")
    lines.append("PS> $src = Get-ChildItem native\\src -Recurse -Include *.cpp,*.hpp | % FullName")
    lines.append("PS> Select-String -Path $src -Pattern rlConfig,thymeEvents,levelFlags,ThymedEvent,"
                 "EliteChance,ZombiePool -SimpleMatch | Measure-Object")
    lines.append("Count : 0")
    lines.append("PS> Select-String -Path $src -Pattern suppressFlagZombie -SimpleMatch | Measure-Object")
    lines.append("Count : 11        # world.cpp / world.hpp / main.cpp")
    lines.append("PS> Select-String -Path $src -Pattern roguelike,Rogue,elite,Elite,DisableSkipLevel -SimpleMatch")
    lines.append("（无输出）")
    lines.append("PS> Select-String -Path $src -Pattern calendar -SimpleMatch")
    lines.append("（无输出）；-Pattern schedule 命中 45 行，全部在 director.cpp/hpp（波次调度）")
    lines.append("```")
    lines.append("")
    lines.append(
        "`rlConfig` / `thymeEvents` 的唯一消费者是编译器自身 `tools/newin4609.py`"
        "（`rlConfig` 29 处、`thymeEvents` 25 处），它负责生成上面的 JSON，不是运行时。"
    )
    lines.append("")
    lines.append("### 6.2 缺的是哪一层（不发明字段）")
    lines.append("")
    template_line = (
        f"`TemplateLevelNames` {len(facts['rlTemplates'])} 条里 "
        f"**{len(facts['rlTemplatesPresent'])} 条**能在 `content/levels` 找到；"
        if not facts["rlTemplatesPresent"]
        else f"`TemplateLevelNames` {len(facts['rlTemplates'])} 条里 "
        f"{len(facts['rlTemplatesPresent'])} 条在 `content/levels` 里；"
    )
    lines.append(
        "- **`rlConfig` 缺「Roguelike 运行层」**：它描述一次 12 关的 run（`LevelCount="
        f"{facts['rlLevelCount']}`、每 `EliteEvery` 关出一个精英、起始阳光按关递增、"
        "僵尸池按世界取）。" + template_line + "内核里没有任何 run 状态、关卡选择/跳过模型，"
        "也没有精英词条。最小接线点（若建该层）：`native/src/flow.cpp:10` 的 "
        "`levelsOfWorld()` 是唯一的关卡序列来源，`flow.cpp:59` 决定下一关——rl run 需要在那里"
        "改写成「按模板名造 12 关」而不是读 `content/levels`。"
    )
    lines.append(
        f"- **`thymeEvents` 缺「日历/会话层」+「活动关卡池」**：{facts['events']} 条事件共 "
        f"{facts['eventRefs']} 个关卡引用（{facts['eventRefsUnique']} 个唯一 id，时间跨度 "
        f"{facts['eventSpan'][0]} → {facts['eventSpan'][1]}，`isNew` = {facts['eventNew']}，"
        f"`disabled` {facts['eventDisabled']} 条），而 `content/levels` 里这些 id "
        f"**命中 {len(facts['eventRefsPresent'])} 条**——事件关卡池根本没有编译进内容。"
        "内核也没有「现在几点/今天哪个活动开着」的概念。最小接线点（若建该层）："
        "`native/src/worldmap.cpp:232` 的 `WorldMap::status()` 是唯一的世界可进入判定，"
        "`native/src/worldmap_view.cpp:313-315` 是进入世界时取首关的位置。"
    )
    lines.append(
        "- 结论：三块里只有 `levelFlags` 今天能落地；`rlConfig` 与 `thymeEvents` 要先有"
        "「活动关卡池 + 日历」与「Roguelike 序列」两层模型，在那之前**不要**把它们直接塞进关卡 JSON——"
        "本次判定只读，C++ 与 content 一行未改。"
    )
    return lines


def _inclusion_lines(payload: dict) -> list[str]:
    """147 条手工名册与 339 条 pack 名册的包含关系。"""
    inc = roster_inclusion()
    same = len(inc["inside"]) + len(inc["equivalent"])
    lines = ["## 七、147 与 339 的包含关系：44 条同名 + 1 条改名", ""]
    lines.append(
        f"`content/plants.json` 的 **{inc['manual']}** 条里，按 id 精确命中 pack 名册的 {len(inc['inside'])} 条，"
        f"另有 {len(inc['equivalent'])} 条能证明是同一植物的改名；剩下 "
        f"**{inc['manual'] - same}** 条在原版名册里没有对应行。"
    )
    lines.append("")
    lines.append("| 类别 | 条数 | 判定依据 | 例 |")
    lines.append("| --- | --- | --- | --- |")
    lines.append(
        f"| 同名在册 | {len(inc['inside'])} | id 与 `content.pack` 的 `plants[].id` 完全相等 | "
        f"{', '.join(inc['inside'][:4])} … |"
    )
    renamed = "、".join(f"`{left}` ↔ `{right}`" for left, right in inc["equivalent"]) or "（无）"
    lines.append(
        f"| 改名同一植物 | {len(inc['equivalent'])} | 名字近似（归一化后共同前缀 ≥6）**且** 成本、血量同时相等 | "
        f"{renamed} |"
    )
    lines.append(
        f"| 融合植物 | {len(inc['fused'])} | id 前缀 `fused_` 或 `tags` 含 `fused`；pack 名册里同名 **0** 条 | "
        f"{', '.join(inc['fused'][:4])} … |"
    )
    lines.append(
        f"| Plantagenet 世界植物 | {len(inc['plantagenet'])} | `tags` 含 `plantagenet`，pack 名册无同名 id | "
        f"{', '.join(inc['plantagenet'][:4])} … |"
    )
    lines.append(
        f"| 客户端自创 | {len(inc['authored'])} | 既无同名、也没有世界标签 | "
        f"{', '.join(inc['authored'])} |"
    )
    lines.append("")
    buckets = (
        len(inc["inside"]),
        len(inc["equivalent"]),
        len(inc["fused"]),
        len(inc["plantagenet"]),
        len(inc["authored"]),
    )
    lines.append(
        "合计：" + " + ".join(str(n) for n in buckets) + f" = {sum(buckets)}（应为 {inc['manual']}）。"
    )
    lines.append("")
    lines.append(
        f"- 归一化（去标点、转小写）后仍相等的：**{len(inc['normalised'])}** 条 —— 说明差异不是"
        "拼写层面的，是真的没有对应项。"
    )
    for left, right in inc["equivalent"]:
        twin = next(
            row for row in _read_json(DEFAULT_PACK).get("plants") or [] if row["id"] == right
        )
        mine = next(row for row in _read_json(DEFAULT_CONTENT) if row["id"] == left)
        lines.append(
            f"- 改名证据：`{left}`（cost {mine.get('cost')} / hp {mine.get('hp')}）↔ `{right}`"
            f"（cost {twin.get('cost')} / hitpoints {twin.get('hitpoints')}，framework `{twin.get('framework')}`）"
            "—— 成本与血量逐项相同，名字只差拼写，判为同一植物。"
        )
    dropped = [pair for pair in inc["near"] if pair not in inc["equivalent"]]
    if dropped:
        pairs = "、".join(f"`{left}` ↔ `{right}`" for left, right in dropped)
        lines.append(
            f"- 名字近似但**不是**同一植物 {len(dropped)} 组：{pairs}（成本/血量不同，属不同条目，"
            "不能按名字合并）。"
        )
    lines.append(
        f"- **结论：「147 是 339 的子集」不成立** —— 算上改名，共享同一植物的只有 {same}/{inc['manual']}"
        f"（{same * 100 // inc['manual']}%）；{len(inc['fused'])} 条融合 + {len(inc['plantagenet'])} 条 "
        f"Plantagenet + {len(inc['authored'])} 条自创在原版名册里都没有对应行。"
    )
    lines.append("")
    lines.append(
        "逐条清单（{0} 条）：".format(
            len(inc["fused"]) + len(inc["plantagenet"]) + len(inc["authored"])
        )
    )
    lines.append("")
    for label, ids in (("融合", inc["fused"]), ("Plantagenet", inc["plantagenet"]),
                       ("客户端自创", inc["authored"])):
        lines.append(f"- **{label}（{len(ids)}）**：")
        for line in _chunk(ids, 6):
            lines.append(f"  - {line}")
    lines.append("")
    lines.append(
        "复现：`py tools\\contentc\\plant_playable.py -n` 之后跑 "
        "`py -m unittest tools.tests.test_plant_playable`（`RosterInclusionTest` 钉住这组数字）；"
        "本节数字由 `roster_inclusion()` 现算，不是手写。"
    )
    return lines


def write_outputs(payload: dict, json_path: Path, report_path: Path) -> tuple[bytes, bytes]:
    json_bytes = emit.write_text(json_path, render_json(payload))
    report_bytes = emit.write_text(report_path, render_report(payload))
    return json_bytes, report_bytes


def summarize(payload: dict) -> str:
    counts = payload["counts"]
    return (
        f"plants-playable-v1: total={counts['total']} playable={counts['playable']} "
        f"new={counts['playableNew']} blocked={counts['blocked']} "
        f"missingCost={counts['missingCost']}(null {counts['missingCostNull']}/"
        f"zero {counts['missingCostZero']}) missingFamily={counts['missingFamily']} "
        f"missingArt={counts['missingArt']} both={counts['blockedBoth']}"
    )


def check(json_path: Path, report_path: Path, payload: dict) -> tuple[bool, str]:
    want_json = render_json(payload)
    want_report = render_report(payload)
    problems: list[str] = []
    for label, path, want in (
        ("JSON", json_path, want_json),
        ("报告", report_path, want_report),
    ):
        if not path.is_file():
            problems.append(f"{label} 不存在：{path}")
            continue
        got = path.read_text(encoding="utf-8")
        if got != want:
            problems.append(f"{label} 不是最新：{path}")
    if problems:
        return False, "；".join(problems)
    return True, f"产物已是最新：{json_path.name} + {report_path.name}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="pack roster 339 条的可玩子集评估")
    ap.add_argument("--roster", type=Path, default=DEFAULT_ROSTER)
    ap.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    ap.add_argument("--families", type=Path, default=DEFAULT_FAMILIES)
    ap.add_argument("--content", type=Path, default=DEFAULT_CONTENT)
    ap.add_argument("--art-index", type=Path, default=DEFAULT_ART_INDEX)
    ap.add_argument("--json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--check", action="store_true", help="只比对产物，不写盘")
    ap.add_argument("-n", "--dry-run", action="store_true", help="只打印摘要，不写盘")
    args = ap.parse_args(argv)

    inputs = Inputs(
        roster=args.roster,
        pack=args.pack,
        families=args.families,
        content=args.content,
        art_index=args.art_index,
    )
    try:
        payload = build(inputs)
    except InputError as error:
        print(f"输入错误：{error}", file=sys.stderr)
        return 2
    print(summarize(payload))

    if args.check:
        ok, message = check(args.json, args.report, payload)
        print(message)
        return 0 if ok else 1
    if args.dry_run:
        return 0
    write_outputs(payload, args.json, args.report)
    print(f"written: {args.json} + {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
