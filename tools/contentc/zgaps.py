"""僵尸行为族缺口（T41，S3 战斗口径）：证据优先，不臆造。

口径与结论（2026-11-24 实测）
----------------------------
`content/zombies.json` 是 55 条的 list，**每一条都写了 `behavior`**（walk 53、gargantuar 1、
jump 1），所以计划书里的「20 个没有可用行为族」在本版数据上不能按字面复现。可复现的 20 是
另一个口径：`native/src/content/loader.cpp` 的 `findZombie` 按 id 精确查 `content.pack`
索引，而 content.pack 的 1127 条僵尸里恰好有 **20 个** content id 同名命中（也就是
`id_mapping.csv` 的 `exact 20`）——它决定「引擎能不能拿到原版 ZombieClass」，不是「有没有
behavior 字段」。

因此本工具把三件事分开记：

1. **判族（family）**：有原版条目的按 `ZombieClass` → `zombie_classes.json` 的类族判定；
   没有原版条目的标 `confidence="authored"`，族取 content 自述并写理由（`extra.art_gargantuar`
   这类客户端自带信号可以作为 authored 依据，但不能冒充原版证据）。
2. **引擎当前实际族（currentFamily）**：复刻 `native/src/engine/world.cpp:794-803` 的规则 ——
   先 `content.pack` 精确命中就用类族，否则用 `content.behavior`（缺省 walk）。
3. **缺口（gap）**：`currentFamily == "walk"` 且 `family != "walk"`。这才是「引擎只会走通用
   walk」的真缺口；反方向（content 自述比原版更激进，如 `pole_vaulter`）不算缺口，保留现状。

`content/**` 只在获批后动，且只动被点名的那几条：2026-11-24 队长批准把 `football`、
`garden_gargantuar`、`royal_chef_gargantuar` 的 `behavior` 从 `walk` 改成 `gargantuar`，
`pole_vaulter` 明确保留 `jump`。本工具本身仍然只读 content，改过的行记在 `APPLIED_PATCHES`，
报告第五节按「已应用补丁」逐条列改前/改后；`gap` 因此从 3 条降到 0 条。
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.contentc import emit  # noqa: E402
import os

DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages"))
DEFAULT_CONTENT = ROOT / "content"
DEFAULT_ZOMBIES = DEFAULT_CONTENT / "zombies.json"
DEFAULT_MAPPING = ROOT / "native" / "generated" / "id_mapping.csv"
DEFAULT_PACK = ROOT / "native" / "generated" / "content.pack"
DEFAULT_CLASSES = ROOT / "native" / "generated" / "zombie_classes.json"
DEFAULT_JSON = ROOT / "native" / "generated" / "zombie_family_gaps.json"
DEFAULT_REPORT = ROOT / "docs" / "reviews" / "2026-11-24-zombie-gaps.md"

FORMAT = 1
MARKER = "zombie-family-gaps-v1"

TYPE_SHEET = "pkg_2115_ZombieType.json"
PROP_SHEET = "pkg_2112_ZombiePropertySheet.json"

# 与 native/src/engine/registry.cpp 的 zombieFamilies() 完全一致，顺序也一致。
FAMILIES = ("walk", "jump", "steal", "summon", "gargantuar", "fly")
FAMILY_MEANING = {
    "walk": "普通行进/啃食",
    "jump": "跳跃/翻越（Jump/Vault 动作）",
    "steal": "偷取（BUNGEE 动画或 steal 动作）",
    "summon": "召唤（Spawn/Summon 动作）",
    "gargantuar": "巨人砸击（PopAnim/类名含 GARGANTUAR/ZOMBOSS/MECH）",
    "fly": "飞行/气球（IsSpawnedFlying）",
}

ROW_KEYS = (
    "clientId",
    "packId",
    "className",
    "matchKind",
    "family",
    "confidence",
    "currentBehavior",
    "currentFamily",
    "gap",
    "evidence",
    "note",
)
COUNT_KEYS = (
    "total",
    "withEvidence",
    "authored",
    "stillUnknown",
    "gaps",
    "appliedPatches",
    "packPresentInContentPack",
    "familyDistribution",
    "currentDistribution",
)

# 已获批并写入 content/zombies.json 的 behavior 修改（改前 → 改后）。
# 这是决策记录，不是推导结果：build() 会逐条回查当前 content 值是否已经等于 after。
APPLIED_PATCHES = (
    {
        "clientId": "football",
        "before": "walk",
        "after": "gargantuar",
        "basis": "pack TypeName football_mech → ZombieMechFootball，PopAnim 含 MECH → gargantuar",
        "approved": "2026-11-24 队长批准",
    },
    {
        "clientId": "garden_gargantuar",
        "before": "walk",
        "after": "gargantuar",
        "basis": "无原版条目；content 自带 extra.art_gargantuar=true（authored）",
        "approved": "2026-11-24 队长批准",
    },
    {
        "clientId": "royal_chef_gargantuar",
        "before": "walk",
        "after": "gargantuar",
        "basis": "无原版条目；content 自带 extra.art_gargantuar=true（authored）",
        "approved": "2026-11-24 队长批准",
    },
)

APPLIED_BY_ID = {item["clientId"]: item for item in APPLIED_PATCHES}


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8-sig"))


# --- 输入 -----------------------------------------------------------------


def load_zombies(path: Path) -> list[dict]:
    doc = _read_json(path)
    if not isinstance(doc, list):
        raise ValueError(f"{path} 期望 list，实际 {type(doc).__name__}")
    rows = []
    for entry in doc:
        if not isinstance(entry, dict) or "id" not in entry:
            continue
        # Pack rows (tools/contentc/zombie_roster.py) are derived from the OBB; this
        # report is about the hand-written roster, so they are not client evidence.
        if entry.get("source") == "pack":
            continue
        rows.append(entry)
    return rows


def load_mapping(path: Path) -> dict[str, dict]:
    """client_id → {pack_type, pack_class, match_kind}；只收有 pack 行的僵尸。"""
    mapping: dict[str, dict] = {}
    with io.open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("side") != "zombie":
                continue
            client_id = (row.get("client_id") or "").strip()
            pack_type = (row.get("pack_type") or "").strip()
            if not client_id or not pack_type:
                continue
            mapping[client_id] = {
                "pack_type": pack_type,
                "pack_class": (row.get("pack_class") or "").strip() or None,
                "match_kind": (row.get("match_kind") or "").strip() or "none",
            }
    return mapping


def load_types(obb_dir: Path) -> dict[str, dict]:
    """TypeName → ZombieType 的 objdata（pkg_2115）。"""
    doc = _read_json(obb_dir / TYPE_SHEET)
    types: dict[str, dict] = {}
    for entry in doc.get("objects", []):
        data = entry.get("objdata")
        if not isinstance(data, dict):
            continue
        name = data.get("TypeName")
        if isinstance(name, str) and name:
            types[name] = data
    return types


def load_props(obb_dir: Path) -> dict[str, dict]:
    """ZombieProperties alias → objdata（pkg_2112）。"""
    doc = _read_json(obb_dir / PROP_SHEET)
    props: dict[str, dict] = {}
    for entry in doc.get("objects", []):
        data = entry.get("objdata")
        if not isinstance(data, dict):
            continue
        for alias in entry.get("aliases") or []:
            if isinstance(alias, str) and alias:
                props[alias] = data
    return props


def load_classes(path: Path) -> dict[str, dict]:
    doc = _read_json(path)
    return {row["className"]: row for row in doc.get("classes", []) if row.get("className")}


def load_pack_ids(path: Path) -> set[str]:
    doc = _read_json(path)
    ids = set()
    for row in doc.get("zombies", []):
        if isinstance(row, dict):
            value = row.get("id")
            if isinstance(value, str) and value:
                ids.add(value)
    return ids


# --- 判族 -----------------------------------------------------------------


def _props_alias(value: object) -> str | None:
    """RTID(Foo@ZombieProperties) → Foo。"""
    text = _text(value)
    if text.startswith("RTID(") and text.endswith(")"):
        inner = text[5:-1]
        return inner.split("@", 1)[0] or None
    return None


def classify(
    client: dict,
    mapped: dict | None,
    types: dict[str, dict],
    props: dict[str, dict],
    classes: dict[str, dict],
    pack_ids: set[str],
) -> dict:
    """返回一行 ROW_KEYS 的内容。"""
    client_id = client["id"]
    behavior = _text(client.get("behavior")).strip() or "walk"
    extra = client.get("extra") or {}
    evidence: list[str] = []
    notes: list[str] = []

    pack_id = mapped["pack_type"] if mapped else None
    class_name = mapped["pack_class"] if mapped else None
    match_kind = mapped["match_kind"] if mapped else None

    if not class_name and pack_id:
        # id_mapping 偶尔只给 pack_type（例如 pack-only 行），回表补类名。
        data = types.get(pack_id) or {}
        value = data.get("ZombieClass")
        if isinstance(value, str) and value:
            class_name = value

    family: str
    confidence: str
    if class_name and class_name in classes:
        record = classes[class_name]
        family = record["family"]
        confidence = "pack"
        data = types.get(pack_id or "", {})
        if data:
            evidence.append(f"{TYPE_SHEET}: TypeName={pack_id} → ZombieClass={class_name}")
            pop = _text(data.get("PopAnim"))
            if pop:
                evidence.append(f"{TYPE_SHEET}: PopAnim={pop}")
            if "IsBasicZombie" in data:
                evidence.append(f"{TYPE_SHEET}: IsBasicZombie={_text(data['IsBasicZombie'])}")
            alias = _props_alias(data.get("Properties"))
            if alias:
                evidence.append(f"{TYPE_SHEET}: Properties=RTID({alias}@ZombieProperties)")
                prop = props.get(alias) or {}
                if "IsSpawnedFlying" in prop:
                    evidence.append(f"{PROP_SHEET}: {alias}.IsSpawnedFlying={_text(prop['IsSpawnedFlying'])}")
        evidence.append(
            "native/generated/zombie_classes.json: "
            f"ZombieClass={class_name} → family={family}（依据 {record['evidence'][0] if record['evidence'] else '—'}）"
        )
        evidence.append(
            f"native/generated/id_mapping.csv: client={client_id} pack={pack_id} match_kind={_text(match_kind) or 'none'}"
        )
    elif class_name:
        # 有映射但族表没有该类（正常不会发生，留出可审计的降级）。
        family = "walk"
        confidence = "authored"
        evidence.append(
            f"native/generated/id_mapping.csv: client={client_id} pack={pack_id} class={class_name}，"
            "但 zombie_classes.json 没有该类的族记录"
        )
        notes.append("类族不可用，按 walk 兜底并标 authored")
    else:
        family = "walk"
        confidence = "authored"
        evidence.append(
            f"native/generated/id_mapping.csv: client={client_id} 无 pack 行（match_kind=none）"
        )
        if isinstance(extra.get("source_codename"), str):
            evidence.append(
                f"content/zombies.json: extra.source_codename={extra['source_codename']}（原版表中不存在该 TypeName）"
            )

    if extra.get("art_gargantuar") is True:
        if family != "gargantuar":
            family = "gargantuar"
            confidence = "authored" if confidence == "authored" else confidence
        evidence.append("content/zombies.json: extra.art_gargantuar=true（客户端自带的美术族标记）")
    if isinstance(extra.get("art_variants"), dict) and extra["art_variants"]:
        keys = ",".join(sorted(extra["art_variants"]))
        evidence.append(f"content/zombies.json: extra.art_variants 键={keys}")
    for key in ("summon_count", "jump_distance", "is_flag", "push_damage", "newspaper_hp"):
        if key in extra:
            evidence.append(f"content/zombies.json: extra.{key}={_text(extra[key])}")

    evidence.append(f"content/zombies.json: behavior={behavior}")

    # 引擎当前族：content.pack 精确命中 → 类族；否则 content.behavior（缺省 walk）。
    if class_name and class_name in classes and client_id in pack_ids:
        current_family = classes[class_name]["family"]
        current_source = f"content.pack 精确命中 {class_name}"
    else:
        current_family = behavior if behavior in FAMILIES else "walk"
        current_source = f"content.behavior={behavior}"
        if current_family != behavior:
            notes.append(f"behavior={behavior!r} 不在 6 族词表，引擎退化为 walk")

    gap = current_family == "walk" and family != "walk"

    if gap:
        basis = (
            f"原版类族证据（{class_name}）"
            if confidence == "pack"
            else "客户端自带标记（extra.art_gargantuar）"
        )
        notes.append(
            f"{basis}判为 {family}，engine 当前落在 walk（{current_source}）→ "
            f"建议把 content/zombies.json 的 behavior 改成 {family}"
        )
    elif current_family != family:
        notes.append(
            f"{current_source} 给 {current_family}，原版类族给 {family}；"
            "客户端自述优先，保留现状，不算缺口"
        )
    elif confidence == "authored":
        notes.append("无原版条目，族来自 content 自述（authored），engine 行为与之一致")

    applied = APPLIED_BY_ID.get(client_id)
    if applied is not None:
        if behavior == applied["after"]:
            notes.append(
                f"2026-11-24 已应用补丁（队长批准）：behavior {applied['before']} → {applied['after']}，"
                "缺口已闭合"
            )
        else:
            notes.append(
                f"APPLIED_PATCHES 记的是 {applied['before']} → {applied['after']}，"
                f"但当前 content 里是 {behavior}，与记录不符"
            )

    if client_id == "kongfu":
        notes.append("extra.summon_count=3 是召唤表现，原版类 ZombieBasic 判 walk；不改族，summon 只作表现")
    if client_id == "pole_vaulter":
        notes.append("原版把 dodo 判 walk，content 主动写 jump（jump_distance），保留 content 值")

    return {
        "clientId": client_id,
        "packId": pack_id,
        "className": class_name,
        "matchKind": match_kind,
        "family": family,
        "confidence": confidence if class_name in classes or confidence == "authored" else "authored",
        "currentBehavior": behavior,
        "currentFamily": current_family,
        "gap": gap,
        "evidence": evidence,
        "note": "；".join(notes),
    }


def build(
    obb_dir: Path,
    zombies_path: Path,
    mapping_path: Path,
    pack_path: Path,
    classes_path: Path,
) -> dict:
    clients = load_zombies(zombies_path)
    mapping = load_mapping(mapping_path)
    types = load_types(obb_dir)
    props = load_props(obb_dir)
    classes = load_classes(classes_path)
    pack_ids = load_pack_ids(pack_path)

    rows = [classify(entry, mapping.get(entry["id"]), types, props, classes, pack_ids) for entry in clients]
    rows.sort(key=lambda row: row["clientId"])

    family_dist = {name: 0 for name in FAMILIES}
    current_dist = {name: 0 for name in FAMILIES}
    for row in rows:
        family_dist[row["family"]] = family_dist.get(row["family"], 0) + 1
        current_dist[row["currentFamily"]] = current_dist.get(row["currentFamily"], 0) + 1

    by_id = {row["clientId"]: row for row in rows}
    applied = []
    for item in APPLIED_PATCHES:
        row = by_id.get(item["clientId"])
        current = row["currentBehavior"] if row is not None else None
        applied.append(
            {
                "clientId": item["clientId"],
                "before": item["before"],
                "after": item["after"],
                "currentBehavior": current,
                "currentFamily": row["currentFamily"] if row is not None else None,
                "family": row["family"] if row is not None else None,
                "applied": current == item["after"],
                "approved": item["approved"],
                "basis": item["basis"],
            }
        )

    counts = {
        "total": len(rows),
        "withEvidence": sum(1 for row in rows if row["confidence"] == "pack"),
        "authored": sum(1 for row in rows if row["confidence"] == "authored"),
        "stillUnknown": sum(1 for row in rows if not row["family"]),
        "gaps": sum(1 for row in rows if row["gap"]),
        "appliedPatches": sum(1 for item in applied if item["applied"]),
        "packPresentInContentPack": sum(1 for row in rows if row["clientId"] in pack_ids),
        "familyDistribution": family_dist,
        "currentDistribution": current_dist,
    }

    payload = {
        "format": FORMAT,
        "generated": MARKER,
        "sources": {
            "zombies": "content/zombies.json",
            "mapping": "native/generated/id_mapping.csv",
            "pack": "native/generated/content.pack",
            "classes": "native/generated/zombie_classes.json",
            "typeSheet": TYPE_SHEET,
            "propertySheet": PROP_SHEET,
        },
        "counts": counts,
        "rows": rows,
        "gaps": [row["clientId"] for row in rows if row["gap"]],
        "appliedPatches": applied,
    }
    return payload


# --- 渲染 -----------------------------------------------------------------


def render_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        cells = [str(cell).replace("|", "\\|") for cell in row]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def _short(text: str, limit: int = 88) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def render_report(payload: dict) -> str:
    counts = payload["counts"]
    rows = payload["rows"]
    gaps = [row for row in rows if row["gap"]]
    authored = [row for row in rows if row["confidence"] == "authored"]

    lines: list[str] = []
    lines.append("# 僵尸行为族缺口（T41 / S3 战斗口径）")
    lines.append("")
    lines.append(f"生成：`tools/contentc/zgaps.py`（`{MARKER}`），三份输入只读；"
                 f"`content/zombies.json` 只在获批后改过 {len(APPLIED_PATCHES)} 行（见第五节）。")
    lines.append("")
    lines.append("## 结论摘要")
    lines.append("")
    lines.append(
        f"- `content/zombies.json` 共 **{counts['total']}** 条僵尸；"
        f"其中有原版 `ZombieClass` 证据的 **{counts['withEvidence']}** 条"
        f"（`id_mapping.csv` 的 exact 20 + manual 8），无原版条目、只能标 authored 的 **{counts['authored']}** 条"
        f"（garden 10 / gang 5 / market 5 / royal 7）。"
    )
    if gaps:
        lines.append(
            f"- 真正「engine 只会走通用 walk」的缺口是 **{counts['gaps']}** 条："
            + "、".join(f"`{row['clientId']}`" for row in gaps)
            + "。"
        )
    else:
        applied_ids = "、".join(f"`{item['clientId']}`" for item in payload["appliedPatches"])
        lines.append(
            f"- 真正「engine 只会走通用 walk」的缺口是 **0** 条：原先的 {counts['appliedPatches']} 条"
            f"（{applied_ids}）已在 2026-11-24 按第五节补丁写进 `content/zombies.json`，"
            f"`behavior` 从 `walk` 改为 `gargantuar`，引擎改走巨人族。"
        )
    lines.append(
        f"- 判定族与引擎当前族的差只剩**反向差异 "
        f"{sum(1 for row in rows if row['currentFamily'] != row['family'])} 条**："
        "`pole_vaulter`（原版 `ZombieIceAgeDodo` 判 walk，content 主动写 jump + `extra.jump_distance`，保留）；"
        f"其余 {sum(1 for row in rows if row['currentFamily'] == row['family'])} 条两侧一致。"
    )
    lines.append(
        f"- 6 族词表与 `native/src/engine/registry.cpp` 的 `zombieFamilies()` 一致；"
        f"本版数据只用到 walk（{counts['familyDistribution']['walk']}）与 "
        f"gargantuar（{counts['familyDistribution']['gargantuar']}），"
        "jump / steal / summon / fly 在这 55 条里没有可采信证据 —— 不臆造。"
    )
    lines.append("")
    lines.append("## 一、「20 个缺族僵尸」的核实")
    lines.append("")
    lines.append(
        "先把口径摆明：`content/zombies.json` 的 55 条**每一条都写了 `behavior`**（改补丁前 walk 53、"
        "gargantuar 1、jump 1），能复现的「20」是 `content.pack` 里与 content id **同名命中**的 20 条"
        f"（本次实测 **{counts['packPresentInContentPack']}** 条 = `id_mapping.csv` 的 `exact 20`），"
        "它决定「引擎能不能读到原版 `ZombieClass`」，与「有没有 behavior」无关；"
        "`docs/COMPLETENESS.md` §2.16 的那个 20（护甲桥）是同一批 id 的第三种用途。"
        "这个口径差异比「20 条没 behavior」有用，下一个人不该再按后者理解。"
    )
    lines.append("")
    lines.append("计划书 T41 写「55 个僵尸里有 20 个没有可用行为族」。实测该表述**不能按字面复现**：")
    lines.append("")
    lines.append(f"1. `content/zombies.json` 是 {len(rows)} 条的 list，**每一条都写了 `behavior`**，没有空值。")
    lines.append(
        f"2. 能复现的 20 是另一个量：`content.pack` 的 1127 条僵尸里，恰好有 "
        f"**{counts['packPresentInContentPack']} 个** content id 同名命中（等于 `id_mapping.csv` 的 `exact 20`）。"
        "它决定「引擎能不能读到原版 `ZombieClass`」，不是「有没有 behavior」。"
    )
    lines.append(
        "3. `docs/COMPLETENESS.md` 里出现的 20 还有一处是护甲桥口径"
        "（20 个 content 僵尸在 sheet `zombies[]` 里也有同名行）。三个 20 是同一批 id、三种用途，"
        "彼此都不等于「20 个缺族」。"
    )
    lines.append("")
    lines.append("因此本工具按「有证据就判族、无证据就标 authored」逐条处理全部 55 条，并把"
                 "「引擎当前实际族」单独列出，用 `gap = 当前是 walk 且判族不是 walk` 定义缺口。")
    lines.append("")
    lines.append("## 二、判族规则")
    lines.append("")
    lines.append("1. **pack 证据**（`confidence=pack`）：`pkg_2115_ZombieType.json` 的 `TypeName → ZombieClass`，"
                 "类族取 `native/generated/zombie_classes.json`（同一张表生成 `zombie_family_table.inc`）。"
                 "判族阈值与依据沿用该表：`IsBasicZombie` → walk、PopAnim/类名含 `GARGANTUAR/ZOMBOSS/MECH` → gargantuar、"
                 "Jump/Vault 动作 → jump、`_BUNGEE` 动画 → steal、Spawn/Summon 或 Chicken/Weasel/Statue → summon、"
                 "`IsSpawnedFlying` → fly，其余 walk。")
    lines.append("2. **authored**（`confidence=authored`）：`id_mapping.csv` 里没有该 client 的 pack 行，"
                 "族取 `content/zombies.json` 自述；`extra.art_gargantuar=true` 这类客户端自带标记可以作为 authored 依据，"
                 "但**不冒充原版证据**（报告里逐条写明）。")
    lines.append("3. **引擎当前实际族**复刻 `native/src/engine/world.cpp:794-803`："
                 "`content.pack` 精确命中就用类族，否则用 `content.behavior`（缺省 walk）；"
                 "`ContentPack::findZombie` 见 `native/src/content/loader.cpp:397-403`。")
    lines.append("4. 判族结果与引擎当前族不一致时，本工具本身**不改 content**：先在第五节出 patch 建议；"
                 "获批后改的那几条记进 `APPLIED_PATCHES`，第五节按「已应用」列改前/改后。")
    lines.append("")
    lines.append("## 三、逐条表（55 条）")
    lines.append("")
    table_rows = []
    for row in rows:
        table_rows.append(
            [
                f"`{row['clientId']}`",
                row["packId"] or "—",
                row["className"] or "—",
                row["currentBehavior"],
                row["currentFamily"],
                row["family"],
                row["confidence"],
                "**缺口**" if row["gap"] else "",
                _short(row["evidence"][0] if row["evidence"] else "—"),
            ]
        )
    lines.extend(
        _table(
            ["client id", "pack TypeName", "ZombieClass", "behavior", "当前族", "判定族", "置信", "缺口", "首条证据"],
            table_rows,
        )
    )
    lines.append("")
    lines.append("## 四、族分布与 engine 6 族对照")
    lines.append("")
    dist_rows = []
    for name in FAMILIES:
        judged = payload["counts"]["familyDistribution"].get(name, 0)
        current = payload["counts"]["currentDistribution"].get(name, 0)
        dist_rows.append([f"`{name}`", FAMILY_MEANING[name], str(current), str(judged)])
    lines.extend(_table(["族", "含义（engine）", "当前实际（55）", "判定（55）"], dist_rows))
    lines.append("")
    lines.append(
        "两侧合计都是 55。差异可以逐项对上：第五节那 3 条补丁把 `football`、`garden_gargantuar`、"
        "`royal_chef_gargantuar` 的 behavior 从 walk 改成 gargantuar，所以当前侧 walk "
        f"{counts['currentDistribution']['walk']}、gargantuar {counts['currentDistribution']['gargantuar']}；"
        f"剩下的唯一差异是 `pole_vaulter`（当前 jump {counts['currentDistribution']['jump']}、判定 walk）——"
        "原版 `ZombieIceAgeDodo` 判 walk，content 主动写 jump，按队长裁决保留 content 值。"
        "补丁前的当前侧是 walk 52 / jump 1 / gargantuar 2，判定侧一直是 walk "
        f"{counts['familyDistribution']['walk']} / gargantuar {counts['familyDistribution']['gargantuar']}。"
    )
    lines.append("")
    lines.append("## 五、已应用补丁（2026-11-24 队长批准，已写入 content）")
    lines.append("")
    applied = payload["appliedPatches"]
    applied_rows = []
    for item in applied:
        applied_rows.append(
            [
                f"`{item['clientId']}`",
                item["before"],
                item["after"],
                item["currentBehavior"] or "—",
                item["family"] or "—",
                "已生效" if item["applied"] else "**未生效**",
                _short(item["basis"], 96),
            ]
        )
    lines.extend(
        _table(
            ["client id", "改前 behavior", "改后 behavior", "当前 content 值", "判定族", "状态", "依据"],
            applied_rows,
        )
    )
    lines.append("")
    lines.append(
        "改前（当前实际族）：walk 52 / jump 1 / gargantuar 2；改后（本次实测）：walk "
        f"{counts['currentDistribution']['walk']} / jump {counts['currentDistribution']['jump']} / "
        f"gargantuar {counts['currentDistribution']['gargantuar']}。判定族不受补丁影响，仍是 walk "
        f"{counts['familyDistribution']['walk']} / gargantuar {counts['familyDistribution']['gargantuar']}。"
        f"缺口随之从 {counts['gaps'] + counts['appliedPatches']} 条降到 **{counts['gaps']}** 条。"
    )
    lines.append("")
    lines.append("补丁的实际改法（已写入 `content/zombies.json`，只动这三行的 `behavior` 值）：")
    lines.append("")
    lines.append("```json")
    lines.append(
        json.dumps(
            {item["clientId"]: {"behavior": item["after"]} for item in applied},
            ensure_ascii=False,
            indent=1,
            sort_keys=True,
        )
    )
    lines.append("```")
    lines.append("")
    lines.append("`pole_vaulter` **不在补丁里**：原版判 walk，content 主动写 jump 是有意行为，保留。")
    if gaps:
        lines.append("")
        lines.append("仍有未闭合缺口（`gap=true` 且未列入已应用补丁）：")
        lines.append("")
        for row in gaps:
            lines.append(f"- `{row['clientId']}`：{_short(row['note'], 140)}")
    lines.append("")
    lines.append("## 六、边界、未改动说明与探针")
    lines.append("")
    lines.append(
        f"- **`content/**` 的改动范围**：只改过第五节那 {len(APPLIED_PATCHES)} 行的 `behavior` 值"
        "（`walk` → `gargantuar`），其余字节未动，`pole_vaulter` 未动；本工具本身对 content 仍是只读，"
        "改的是人按批准执行的补丁，不在这里偷偷改数据。"
    )

    lines.append(
        f"- **authored {counts['authored']} 条**没有原版条目，族只能来自 content 自述；"
        "报告第三节把它们与 pack 证据行分开标注，避免被当成原版事实引用。"
    )
    lines.append(
        "- `pole_vaulter` 是**反向差异**：原版 `ZombieIceAgeDodo` 判 walk，content 主动写 `jump`"
        "（`extra.jump_distance`），引擎会按 content 走 jump —— 保留 content 值，不列入缺口。"
    )
    lines.append(
        "- `kongfu` 带 `extra.summon_count=3`，但原版 `ZombieBasic` 判 walk；按「召唤是表现、不是族」处理，"
        "不改族，只在此记录。"
    )
    coded = [row["clientId"] for row in authored if "extra.source_codename" in " ".join(row["evidence"])]
    if coded:
        lines.append(
            f"- `extra.source_codename` 在 {len(coded)} 条 authored 僵尸上出现（"
            + "、".join(f"`{cid}`" for cid in sorted(coded))
            + "）；其中代号指向的原版 TypeName 已确认不存在（`royal_zombie`→`royal`、`royal_flag`→`royal_flag`），"
            "因此只能作为「客户端自称」记录，不能据此判族。"
        )
    lines.append("- 复现：`python tools/contentc/zgaps.py`（加 `--check` 只校验不改盘）；"
                 "回归：`python -m unittest tools.tests.test_zgaps -v`。")
    lines.append("")
    return "\n".join(lines)


def write_outputs(payload: dict, json_path: Path, report_path: Path) -> tuple[Path, Path]:
    emit.write_text(json_path, render_json(payload))
    emit.write_text(report_path, render_report(payload))
    return json_path, report_path


def summarize(payload: dict) -> str:
    counts = payload["counts"]
    dist = ",".join(f"{k}={v}" for k, v in counts["familyDistribution"].items() if v)
    return (
        f"rows={counts['total']} pack={counts['withEvidence']} authored={counts['authored']} "
        f"unknown={counts['stillUnknown']} gaps={counts['gaps']} "
        f"applied={counts['appliedPatches']} families={dist}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="僵尸行为族缺口（证据优先）")
    parser.add_argument("--obb", default=str(DEFAULT_OBB), help="obb_packages 目录")
    parser.add_argument("--content", default=str(DEFAULT_ZOMBIES), help="content/zombies.json")
    parser.add_argument("--mapping", default=str(DEFAULT_MAPPING), help="id_mapping.csv")
    parser.add_argument("--pack", default=str(DEFAULT_PACK), help="content.pack")
    parser.add_argument("--classes", default=str(DEFAULT_CLASSES), help="zombie_classes.json")
    parser.add_argument("--json", default=str(DEFAULT_JSON), help="输出 JSON")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="输出报告")
    parser.add_argument("--check", action="store_true", help="只校验已提交产物是否最新")
    parser.add_argument("-n", "--dry-run", action="store_true", help="只打印摘要，不写盘")
    args = parser.parse_args(argv)

    obb_dir = Path(args.obb)
    if not obb_dir.is_dir():
        print(f"obb_packages 目录不存在：{obb_dir}", file=sys.stderr)
        return 2
    for path in (args.content, args.mapping, args.pack, args.classes):
        if not Path(path).is_file():
            print(f"输入缺失：{path}", file=sys.stderr)
            return 2
    for name in (TYPE_SHEET, PROP_SHEET):
        if not (obb_dir / name).is_file():
            print(f"输入缺失：{obb_dir / name}", file=sys.stderr)
            return 2

    payload = build(
        obb_dir,
        Path(args.content),
        Path(args.mapping),
        Path(args.pack),
        Path(args.classes),
    )

    if args.check:
        json_text = render_json(payload)
        report_text = render_report(payload)
        problems = []
        for path, text in ((Path(args.json), json_text), (Path(args.report), report_text)):
            if not path.is_file():
                problems.append(f"缺失：{path}")
            elif path.read_text(encoding="utf-8") != text:
                problems.append(f"过期：{path}")
        if problems:
            for item in problems:
                print(item, file=sys.stderr)
            return 2
        print(f"产物已是最新：{summarize(payload)}")
        return 0

    if args.dry_run:
        print(f"[dry-run] {summarize(payload)}")
        return 0

    json_path, report_path = write_outputs(payload, Path(args.json), Path(args.report))
    print(f"{json_path} · {report_path}")
    print(summarize(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
