#!/usr/bin/env python3
"""pack 植物名册：把 OBB 的 339 个植物类型补成 content 形状（纯加法产物）。

运行：
    python tools/contentc/expand.py            # 写 native/generated/plants_from_pack.json + pack_roster_report.md
    python tools/contentc/expand.py --check    # 产物与当前数据不一致时退出码 1
    python tools/contentc/expand.py -n         # 只打印摘要

为什么是加法：`content/plants.json` 只有 147 条，其中 44 条能在本版 OBB 里按同名命中；
其余 103 条是客户端独有（见 native/generated/id_mapping.csv）。本工具不动
`content/plants.json`，只把 pack 里有、content 里没有的 295 株写成一份独立的
“待并入”名册，字段形状与 content 对齐，便于后续人工 review 后并入。

字段映射（逐字段来源写进每条记录的 fieldSources）：
    id            ← pack.id
    cost          ← pack.cost；缺失时用 content 里同 behavior 族的均值（costSource=family-avg）
    cooldown      ← pack.packetCooldown；缺失时同族均值，再缺则 5.0
    hp            ← pack.hitpoints
    family        ← native/generated/plant_families.json 的 family（behavior 族）；
                    该文件缺失时按 fallback 规则判族，并在报告里注明
    behavior      ← 同 family
    rows          ← gridType=water → [] 且加 tag "water"；其余 [0]
                    （pack 没有“占几格”字段，height 是美术高度，不参与 rows）
    tags          ← "plant" + 族标签 + sunProducer ? "sun" : + water
    plantfood     ← bool(plantFoodDuration > 0)
    interval      ← 第一个 projectile action 的 cooldownMin（与 content 的 interval 同义）
    projectile    ← 该 action 的 projectile.name，小写
    damage        ← null（pack 没有伤害数值，别猜）
    art           ← 按 popAnim / animRig 猜 assets/db 的 actor 键，猜不到 null
    name_en       ← framework 去掉 "Plant" 前缀；name_zh / desc_zh / almanac_no 为 null

产出：
    native/generated/plants_from_pack.json   295 条 plants + 44 条 skipped_existing
    native/generated/pack_roster_report.md   分族统计 / art 命中率 / 缺省占比 / 先补 20 条

两次运行字节一致（无时间戳、无绝对路径）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.contentc import emit  # noqa: E402

DEFAULT_PACK = ROOT / "native" / "generated" / "content.pack"
DEFAULT_CONTENT = ROOT / "content" / "plants.json"
DEFAULT_FAMILIES = ROOT / "native" / "generated" / "plant_families.json"
DEFAULT_ASSETS = ROOT.parent.parent / "PvZ2SHUTTLE" / "assets"
DEFAULT_JSON = ROOT / "native" / "generated" / "plants_from_pack.json"
DEFAULT_REPORT = ROOT / "native" / "generated" / "pack_roster_report.md"

FORMAT = 1
MARKER = "pack-roster-v1"
TOP_READY = 20

# behavior 族 → content 里用过的 tag（照 content/plants.json 的用词）
FAMILY_TAGS: dict[str, str] = {
    "shoot": "shooter",
    "lob": "lobber",
    "produce": "sun",
    "wall": "wall",
    "instant": "explosive",
    "mine": "mine",
    "chomp": "chomp",
    "fume": "fume",
    "boomerang": "boomerang",
    "support": "support",
    "spike": "spike",
}

REQUIRED_FIELDS = (
    "id",
    "name_zh",
    "name_en",
    "cost",
    "cooldown",
    "hp",
    "family",
    "art",
    "behavior",
    "damage",
    "interval",
    "projectile",
    "rows",
    "pierce",
    "tags",
    "desc_zh",
    "almanac_no",
    "plantfood",
)


@dataclass(frozen=True)
class CostStats:
    """content 里的同族均值基准（缺省值用）。"""

    cost_by_family: dict[str, float]
    cooldown_by_family: dict[str, float]
    cost_global: float
    cooldown_global: float


@dataclass(frozen=True)
class RosterRow:
    """一条 pack 植物 → content 形状的结果。"""

    entry: dict[str, object]
    art_basis: str
    has_actions: bool
    action_kinds: tuple[str, ...]


@dataclass(frozen=True)
class Roster:
    """一次构建的全部结果。"""

    rows: tuple[RosterRow, ...]
    skipped: tuple[dict[str, object], ...]
    pack_count: int
    content_count: int
    family_source: str
    family_counts: tuple[tuple[str, int], ...]
    art_hit: int
    art_hit_pack_only: int
    art_basis: tuple[tuple[str, int], ...]
    cost_default: tuple[str, ...]
    cooldown_default: tuple[str, ...]
    water: tuple[str, ...]
    no_actions: tuple[str, ...]
    family_avg_basis: tuple[tuple[str, float], ...]
    path_pack: str
    path_content: str
    path_families: str
    path_assets: str

    @property
    def emitted(self) -> tuple[dict[str, object], ...]:
        return tuple(row.entry for row in self.rows)


def _rel(path: Path) -> str:
    """报告里只出现仓库内相对路径或文件名，保证可复现。"""

    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(ROOT.parent.parent).as_posix()
        except ValueError:
            return path.name


def load_pack(path: Path) -> list[dict[str, object]]:
    """读 content.pack 的 plants 段。"""

    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: 根必须是对象")
    plants = data.get("plants")
    if not isinstance(plants, list):
        raise ValueError(f"{path.name}: 缺少 plants 数组")
    return [row for row in plants if isinstance(row, dict) and "id" in row]


def load_content(path: Path) -> dict[str, dict[str, object]]:
    """读 content/plants.json，按 id 索引。"""

    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError(f"{path.name}: 根必须是数组")
    return {str(row["id"]): row for row in data if isinstance(row, dict) and "id" in row}


def load_families(path: Path) -> dict[str, dict[str, object]]:
    """读 geometer 的 plant_families.json；不存在时返回空表（走 fallback）。"""

    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        rows = data.get("plants") or []
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    out: dict[str, dict[str, object]] = {}
    for row in rows:
        if isinstance(row, dict) and "id" in row and "family" in row:
            out[str(row["id"])] = row
    return out


def load_plant_actors(assets: Path) -> dict[str, str]:
    """assets/db 下 plants/<X>PLANT 目录 → 规范键；小写做索引。"""

    db = assets / "db"
    keys: dict[str, str] = {}
    if not db.is_dir():
        return keys
    for group in sorted(db.iterdir()):
        if not group.is_dir() or group.name != "plants":
            continue
        for actor in sorted(group.iterdir()):
            if actor.is_dir():
                keys[f"plants/{actor.name}".lower()] = f"plants/{actor.name}"
    return keys


def _camel(token: str) -> str:
    """NUKELAUNCHER / Nuke_Launcher → Nukelauncher / NukeLauncher 的驼峰候选。"""

    parts = [part for part in re.split(r"[^A-Za-z0-9]+", token) if part]
    return "".join(part[:1].upper() + part[1:].lower() for part in parts)


def guess_art(
    pop_anim: object, anim_rig: object, actors: dict[str, str]
) -> tuple[str | None, str]:
    """按 popAnim / animRig 猜 db 键。

    顺序（都要求唯一命中，绝不猜第二个）：
      1. POPANIM_PLANT_<TOKEN> → plants/<Camel(TOKEN)>PLANT
      2. PlantAnimRig_<Token>  → plants/<Camel(Token)>PLANT
      3. 归一化子串唯一命中（token 去掉非字母数字后是某个 db 键 stem 的子串）
    猜不到返回 (None, "miss")。
    """

    pop = str(pop_anim or "")
    token = pop[len("POPANIM_PLANT_") :] if pop.startswith("POPANIM_PLANT_") else pop
    rig = str(anim_rig or "")
    rig_token = rig[len("PlantAnimRig_") :] if rig.startswith("PlantAnimRig_") else ""

    for candidate, basis in (
        (_camel(token), "popanim-token"),
        (_camel(rig_token) if rig_token else "", "animrig-token"),
    ):
        if not candidate:
            continue
        key = f"plants/{candidate}PLANT".lower()
        if key in actors:
            return actors[key], basis

    norm = re.sub(r"[^a-z0-9]", "", token.lower())
    if norm:
        hits = sorted(
            actor for low, actor in actors.items() if norm in low.split("/", 1)[1].lower()
        )
        if len(hits) == 1:
            return hits[0], "substring"
    return None, "miss"


def fallback_family(row: dict[str, object]) -> str:
    """plant_families.json 缺席时的判族规则（有据可查、按顺序命中）。"""

    actions = row.get("actions") or []
    kinds = {str(a.get("kind")) for a in actions if isinstance(a, dict)}
    hp = row.get("hitpoints") or 0
    if row.get("sunProducer"):
        return "produce"
    if "explode" in kinds:
        return "instant"
    if "projectile" in kinds or "manual" in kinds:
        return "shoot"
    if not kinds and isinstance(hp, (int, float)) and hp >= 1500:
        return "wall"
    return "support"


def cost_stats(content: dict[str, dict[str, object]]) -> CostStats:
    """按 behavior 族算 content 的 cost / cooldown 均值。"""

    costs: dict[str, list[float]] = {}
    cooldowns: dict[str, list[float]] = {}
    all_costs: list[float] = []
    all_cooldowns: list[float] = []
    for row in content.values():
        family = str(row.get("behavior") or "")
        cost = row.get("cost")
        cooldown = row.get("cooldown")
        if isinstance(cost, (int, float)):
            costs.setdefault(family, []).append(float(cost))
            all_costs.append(float(cost))
        if isinstance(cooldown, (int, float)):
            cooldowns.setdefault(family, []).append(float(cooldown))
            all_cooldowns.append(float(cooldown))

    def mean(values: Iterable[float], fallback: float) -> float:
        vals = list(values)
        return sum(vals) / len(vals) if vals else fallback

    return CostStats(
        cost_by_family={k: mean(v, 0.0) for k, v in costs.items()},
        cooldown_by_family={k: mean(v, 5.0) for k, v in cooldowns.items()},
        cost_global=mean(all_costs, 100.0),
        cooldown_global=mean(all_cooldowns, 5.0),
    )


def _rows_for(grid_type: object) -> tuple[list[int], list[str]]:
    """gridType → (rows, 额外 tags)。water 为空 rows + tag；其余单行。"""

    if str(grid_type or "").lower() == "water":
        return [], ["water"]
    return [0], []


def _first_projectile(row: dict[str, object]) -> dict[str, object] | None:
    for action in row.get("actions") or []:
        if isinstance(action, dict) and action.get("kind") == "projectile":
            return action
    return None


def _name_en(framework: object) -> str | None:
    text = str(framework or "")
    if not text:
        return None
    return text[len("Plant") :] if text.startswith("Plant") else text


def build(
    pack_path: Path = DEFAULT_PACK,
    content_path: Path = DEFAULT_CONTENT,
    families_path: Path = DEFAULT_FAMILIES,
    assets: Path = DEFAULT_ASSETS,
) -> Roster:
    """把 pack 的 339 株转成 content 形状，并只输出 content 里没有的 295 株。"""

    pack = load_pack(pack_path)
    content = load_content(content_path)
    families = load_families(families_path)
    actors = load_plant_actors(assets)
    stats = cost_stats(content)

    family_source = "plant_families.json" if families else "fallback-rule"

    rows: list[RosterRow] = []
    skipped: list[dict[str, object]] = []
    cost_default: list[str] = []
    cooldown_default: list[str] = []
    water: list[str] = []
    no_actions: list[str] = []
    family_counts: Counter[str] = Counter()
    art_basis_counts: Counter[str] = Counter()
    art_hit = 0
    art_hit_pack_only = 0

    for row in pack:
        pid = str(row["id"])
        record = families.get(pid)
        if record:
            family = str(record["family"])
            family_basis = str(record.get("rule") or record.get("source") or "plant_families")
        else:
            family = fallback_family(row)
            family_basis = "fallback-rule"

        art, art_basis = guess_art(row.get("popAnim"), row.get("animRig"), actors)
        art_basis_counts[art_basis] += 1
        if art:
            art_hit += 1

        if pid in content:
            skipped.append(
                {
                    "id": pid,
                    "reason": "content/plants.json 已有同 id 条目，保持原样不合并",
                    "framework": row.get("framework"),
                    "art": art,
                }
            )
            continue

        cost = row.get("cost")
        cost_source = "pack"
        if not isinstance(cost, (int, float)):
            cost = round(stats.cost_by_family.get(family, stats.cost_global))
            cost_source = "family-avg"
            cost_default.append(pid)

        cooldown = row.get("packetCooldown")
        cooldown_source = "pack"
        if not isinstance(cooldown, (int, float)):
            cooldown = round(stats.cooldown_by_family.get(family, stats.cooldown_global), 2)
            cooldown_source = "family-avg"
            cooldown_default.append(pid)

        hp = row.get("hitpoints")
        hp_value = int(hp) if isinstance(hp, (int, float)) else None

        rows_list, extra_tags = _rows_for(row.get("gridType"))
        if extra_tags:
            water.append(pid)

        if art:
            art_hit_pack_only += 1

        action = _first_projectile(row)
        interval = None
        projectile = None
        if action:
            min_cd = action.get("cooldownMin")
            max_cd = action.get("cooldownMax")
            if isinstance(min_cd, (int, float)) and isinstance(max_cd, (int, float)):
                interval = round(float(min_cd), 2)
            elif isinstance(min_cd, (int, float)):
                interval = round(float(min_cd), 2)
            proj = action.get("projectile")
            if isinstance(proj, dict) and proj.get("name"):
                projectile = str(proj["name"]).lower()

        actions = [a for a in row.get("actions") or [] if isinstance(a, dict)]
        action_kinds = tuple(str(a.get("kind")) for a in actions)
        if not actions:
            no_actions.append(pid)
            interval = None
            projectile = None

        tags = ["plant"]
        family_tag = FAMILY_TAGS.get(family)
        if family_tag:
            tags.append(family_tag)
        if row.get("sunProducer"):
            tags.append("sun")
        tags.extend(extra_tags)
        deduped: list[str] = []
        for tag in tags:
            if tag not in deduped:
                deduped.append(tag)

        entry: dict[str, object] = {
            "id": pid,
            "source": "pack",
            "name_zh": None,
            "name_en": _name_en(row.get("framework")),
            "cost": int(cost),
            "cooldown": cooldown,
            "hp": hp_value,
            "family": family,
            "art": art,
            "behavior": family,
            "damage": None,
            "interval": interval,
            "projectile": projectile,
            "rows": rows_list,
            "pierce": False,
            "tags": deduped,
            "desc_zh": None,
            "almanac_no": None,
            "plantfood": bool((row.get("plantFoodDuration") or 0) > 0),
            "fieldSources": {
                "id": "pack",
                "name_zh": "null",
                "name_en": "derived-framework",
                "cost": cost_source,
                "cooldown": cooldown_source,
                "hp": "pack",
                "family": family_source,
                "behavior": family_source,
                "art": art_basis if art else "null",
                "damage": "null",
                "interval": "pack-action" if interval is not None else "null",
                "projectile": "pack-action" if projectile else "null",
                "rows": "pack-gridType",
                "pierce": "default",
                "tags": "derived",
                "plantfood": "pack-plantFoodDuration",
                "desc_zh": "null",
                "almanac_no": "null",
            },
            "familyBasis": family_basis,
            "packFacts": {
                "framework": row.get("framework"),
                "popAnim": row.get("popAnim"),
                "animRig": row.get("animRig"),
                "homeWorld": row.get("homeWorld"),
                "integerId": row.get("integerId"),
                "gridType": row.get("gridType"),
                "height": row.get("height"),
                "cost": row.get("cost"),
                "packetCooldown": row.get("packetCooldown"),
                "hitpoints": row.get("hitpoints"),
                "plantFoodDuration": row.get("plantFoodDuration"),
                "sunProducer": bool(row.get("sunProducer")),
                "families": row.get("families") or [],
                "actionKinds": list(action_kinds),
                "propsSource": row.get("propsSource"),
            },
        }

        for field in REQUIRED_FIELDS:
            if field not in entry:
                raise AssertionError(f"{pid}: 缺字段 {field}")

        rows.append(
            RosterRow(
                entry=entry,
                art_basis=art_basis,
                has_actions=bool(actions),
                action_kinds=action_kinds,
            )
        )
        family_counts[family] += 1

    return Roster(
        rows=tuple(rows),
        skipped=tuple(skipped),
        pack_count=len(pack),
        content_count=len(content),
        family_source=family_source,
        family_counts=tuple(sorted(family_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        art_hit=art_hit,
        art_hit_pack_only=art_hit_pack_only,
        art_basis=tuple(sorted(art_basis_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        cost_default=tuple(cost_default),
        cooldown_default=tuple(cooldown_default),
        water=tuple(water),
        no_actions=tuple(no_actions),
        family_avg_basis=tuple(
            (family, round(stats.cost_by_family.get(family, stats.cost_global), 2))
            for family in sorted(family_counts)
        ),
        path_pack=_rel(pack_path),
        path_content=_rel(content_path),
        path_families=_rel(families_path),
        path_assets=_rel(assets),
    )


def render_json(roster: Roster) -> str:
    """稳定 JSON：plants 按 pack 顺序，skipped_existing 同序。"""

    payload = {
        "format": FORMAT,
        "generated": MARKER,
        "sources": {
            "pack": roster.path_pack,
            "content": roster.path_content,
            "families": roster.path_families,
            "assets": roster.path_assets,
            "familySource": roster.family_source,
        },
        "counts": {
            "pack": roster.pack_count,
            "emitted": len(roster.rows),
            "skipped_existing": len(roster.skipped),
            "artHit": roster.art_hit,
            "artHitPackOnly": roster.art_hit_pack_only,
            "costDefault": len(roster.cost_default),
            "cooldownDefault": len(roster.cooldown_default),
            "water": len(roster.water),
            "noActions": len(roster.no_actions),
        },
        "plants": [row.entry for row in roster.rows],
        "skipped_existing": list(roster.skipped),
    }
    return emit.dumps(payload)


def _table(header: Sequence[str], rows: Iterable[Sequence[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join("---" for _ in header) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def ready_to_fill(roster: Roster) -> tuple[RosterRow, ...]:
    """最该先补的植物：art 已命中 + 有 Actions，按动作数与动作种类排序。"""

    candidates = [
        row for row in roster.rows if row.entry["art"] and row.has_actions
    ]
    return tuple(
        sorted(
            candidates,
            key=lambda row: (
                -len(row.action_kinds),
                -len(set(row.action_kinds)),
                str(row.entry["id"]),
            ),
        )[:TOP_READY]
    )


def render_report(roster: Roster) -> str:
    """人可读报告：分族、art 命中率、缺省占比、先补 20 条。"""

    emitted = len(roster.rows)
    lines: list[str] = []
    add = lines.append

    add("# pack 植物名册报告")
    add("")
    add("> 由 `python tools/contentc/expand.py` 生成，不要手改；`--check` 会在产物过期时失败。")
    add("")
    add("## 输入")
    add("")
    lines += _table(
        ("项", "路径", "数量"),
        (
            ("pack 植物", f"`{roster.path_pack}`", roster.pack_count),
            ("现有 content 植物", f"`{roster.path_content}`", roster.content_count),
            ("行为族表", f"`{roster.path_families}`", "有" if roster.family_source == "plant_families.json" else "缺失"),
            ("美术库", f"`{roster.path_assets}/db`", "plants/*"),
        ),
    )
    add("")

    add("## 摘要")
    add("")
    lines += _table(
        ("指标", "数值"),
        (
            ("pack 植物总数", roster.pack_count),
            ("本次输出（pack-only）", emitted),
            ("按同名跳过（content 已有）", len(roster.skipped)),
            ("art 命中（本次输出）", f"{roster.art_hit_pack_only} / {emitted}"),
            ("art 命中（含已存在，全 339）", f"{roster.art_hit} / {roster.pack_count}"),
            ("cost 走同族均值", len(roster.cost_default)),
            ("cooldown 走同族均值", len(roster.cooldown_default)),
            ("water 格植物", len(roster.water)),
            ("无 Actions 植物", len(roster.no_actions)),
            ("行为族来源", roster.family_source),
        ),
    )
    add("")

    add("## 分族统计（本次输出的 295 株）")
    add("")
    basis_by_family = dict(roster.family_avg_basis)
    lines += _table(
        ("behavior 族", "株数", "content 同族 cost 均值（缺省基准）"),
        ((family, count, basis_by_family.get(family, "—")) for family, count in roster.family_counts),
    )
    add("")
    add(f"合计 {sum(count for _, count in roster.family_counts)} 株；族判定来自 `{roster.family_source}`。")
    add("")

    add("## art 命中率")
    add("")
    add(
        "guess 顺序：`POPANIM_PLANT_<TOKEN>` → `plants/<Camel>PLANT`；`PlantAnimRig_<Token>` → "
        "`plants/<Camel>PLANT`；最后是归一化子串唯一命中。命中不了写 `null`，不硬凑。"
    )
    add("")
    lines += _table(("依据（按全 339 株统计）", "株数"), roster.art_basis)
    add("")
    pct = 100.0 * roster.art_hit_pack_only / (emitted or 1)
    full_pct = 100.0 * roster.art_hit / (roster.pack_count or 1)
    add(
        f"本次输出 {emitted} 株里 {roster.art_hit_pack_only} 株（{pct:.0f}%）能挂到 assets/db 的 actor；"
        f"把 44 株已存在的算上，339 株里 {roster.art_hit} 株（{full_pct:.0f}%）有现成模型。"
        "其余只能先出静态图或色块——这是美术缺口，不是字段缺失。"
    )
    add("")

    add("## cost / cooldown 缺省")
    add("")
    add(
        "pack 里 `cost` 缺失时用 content 同 behavior 族的均值（四舍五入到整数），"
        "`packetCooldown` 缺失时同族均值（保留两位）；同族没有样本时退回全局均值。"
    )
    add("")
    lines += _table(
        ("字段", "走缺省的植物"),
        (
            ("cost", "、".join(f"`{pid}`" for pid in roster.cost_default) or "（无）"),
            ("cooldown", "、".join(f"`{pid}`" for pid in roster.cooldown_default) or "（无）"),
        ),
    )
    add("")

    add(f"## 最该先补的 {TOP_READY} 条（art 已命中 + 有 Actions）")
    add("")
    add("排序：动作数降序 → 动作种类数降序 → id；这些条目既有现成骨骼，又有可接线的动作。")
    add("")
    lines += _table(
        ("#", "植物", "framework", "actions", "动作种类", "art"),
        (
            (
                index,
                f"`{row.entry['id']}`",
                row.entry["packFacts"]["framework"],
                len(row.action_kinds),
                "、".join(sorted(set(row.action_kinds))),
                f"`{row.entry['art']}`",
            )
            for index, row in enumerate(ready_to_fill(roster), start=1)
        ),
    )
    add("")

    add("## 已知简化 / 待补")
    add("")
    add(
        "- `damage` 一律 `null`：pack 的动作里没有伤害数值，只能等引擎侧按 projectile 反查，别在这里编。"
    )
    add(
        "- `rows` 一律 `[0]`（water 为 `[]`）：pack 没有“该植物占几格”的字段，`height` 是美术高度；"
        "三行覆盖类（如 threepeater）需要棋盘几何那侧的判定，本工具不猜。"
    )
    add(
        "- `name_zh` / `desc_zh` / `almanac_no` 为 `null`：pack 不带本地化文本，"
        "`name_en` 是从 framework 去掉 `Plant` 前缀得到的候选名，不是官方译名。"
    )
    add(
        "- `family` 用的是 behavior 族（shoot/lob/…），与 content 里 `family` 的美术家族名"
        "（如 `Peashooter`）不是一个概念；pack 的原始家族名保留在 `packFacts.families` 与 `framework` 里。"
    )
    add("")

    add("## 附录：按同名跳过的 44 条")
    add("")
    lines += _table(
        ("id", "framework", "原因"),
        ((f"`{row['id']}`", row.get("framework") or "（无）", row["reason"]) for row in roster.skipped),
    )
    add("")

    return "\n".join(lines)


def write_outputs(roster: Roster, json_path: Path, report_path: Path) -> tuple[bytes, bytes]:
    """写两个产物并返回写入的字节。"""

    return (
        emit.write_text(json_path, render_json(roster)),
        emit.write_text(report_path, render_report(roster)),
    )


def summarize(roster: Roster) -> str:
    return (
        f"pack={roster.pack_count} emitted={len(roster.rows)} skipped={len(roster.skipped)} "
        f"art={roster.art_hit_pack_only}/{len(roster.rows)} (all {roster.art_hit}/{roster.pack_count}) "
        f"costDefault={len(roster.cost_default)} cooldownDefault={len(roster.cooldown_default)} "
        f"water={len(roster.water)} noActions={len(roster.no_actions)} family={roster.family_source}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="把 pack 的 339 株植物转成 content 形状，输出 pack-only 的 295 株与名册报告。"
    )
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK, help="native/generated/content.pack")
    parser.add_argument("--content", type=Path, default=DEFAULT_CONTENT, help="content/plants.json")
    parser.add_argument("--families", type=Path, default=DEFAULT_FAMILIES, help="native/generated/plant_families.json")
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS, help="PvZ2SHUTTLE/assets")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="输出 plants_from_pack.json")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="输出 pack_roster_report.md")
    parser.add_argument("--check", action="store_true", help="只校验产物是否最新，过期时退出码 1")
    parser.add_argument("-n", "--dry-run", action="store_true", help="只打印摘要，不写文件")
    args = parser.parse_args(argv)

    for label, path in (
        ("pack", args.pack),
        ("content", args.content),
        ("assets", args.assets),
    ):
        if not path.exists():
            print(f"缺少 {label}: {path}", file=sys.stderr)
            return 2

    roster = build(args.pack, args.content, args.families, args.assets)
    json_text = render_json(roster)
    report_text = render_report(roster)

    if args.dry_run:
        print(summarize(roster))
        print(f"json chars={len(json_text)} report chars={len(report_text)}")
        return 0

    if args.check:
        stale: list[str] = []
        for path, text in ((args.json, json_text), (args.report, report_text)):
            if not path.is_file():
                stale.append(f"缺失: {path}")
            elif path.read_text(encoding="utf-8") != text:
                stale.append(f"过期: {path}")
        if stale:
            for line in stale:
                print(line, file=sys.stderr)
            print("重跑 tools/contentc/expand.py 生成产物", file=sys.stderr)
            return 1
        print(summarize(roster))
        print("产物最新")
        return 0

    write_outputs(roster, args.json, args.report)
    print(summarize(roster))
    print(f"写出 {args.json}")
    print(f"写出 {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
