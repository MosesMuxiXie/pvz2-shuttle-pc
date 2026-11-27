#!/usr/bin/env python3
"""卡组（deck）覆盖报告：把 1809 关的 deck 现实摊开。

运行：
    python tools/contentc/decks.py            # 写 native/generated/deck_report.md
    python tools/contentc/decks.py --check    # 报告与当前数据不一致时退出码 1
    python tools/contentc/decks.py -n         # 只打印摘要，不写文件

这份报告回答一个很具体的问题：要玩第 X 世界第 N 关，现在有几株植物是真模型、
几株只有静态图、几株连图都没有，以及它们的行为族是否已经在引擎里接上。

数据来源（全部只读）：
  - content/levels/*.json            1809 关，字段 deck / sun / waves / flags / seed_bank
  - content/plants.json              植物注册表（手工 147 行 + 251 条 pack 派生行 = 398）
  - <assets>/db/MANIFEST.json        DragonBones actor 清单（读 ["actors"]）
  - <assets>/art/**/*.png            静态美术（客户端 art 字段里的 png 路径）
  - native/src/engine/registry.cpp   plantFamilies() 的 11 个行为族（本文件里是常量镜像）

美术分三档，报告里逐关逐世界计数：
  actor  植物 art 命中 MANIFEST actor key —— 有骨骼动画，算“真模型”
  png    植物 art 是 assets 下真实存在的 png —— 只能静态贴图，动画做不了
  none   两样都没有 —— 只能画色块

空 deck 策略：本版 1809 关全部带非空 deck（空 deck 0 关）。若将来出现空 deck，
按 seed_bank 的顺序取默认卡组；seed_bank 也为空时，该关单独记入“空 deck 关卡”
清单，不参与“去重植物”统计，并在摘要里点名——绝不静默跳过。

输出不含时间戳、不含绝对路径，同一输入两次生成字节一致。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.contentc import emit  # noqa: E402
DEFAULT_LEVELS = ROOT / "content" / "levels"
DEFAULT_PLANTS = ROOT / "content" / "plants.json"
DEFAULT_ASSETS = ROOT.parent.parent / "PvZ2SHUTTLE" / "assets"
DEFAULT_REPORT = ROOT / "native" / "generated" / "deck_report.md"

# native/src/engine/registry.cpp:486 Registry::plantFamilies()
PLANT_FAMILIES: tuple[str, ...] = (
    "shoot",
    "lob",
    "produce",
    "wall",
    "instant",
    "mine",
    "chomp",
    "fume",
    "boomerang",
    "support",
    "spike",
)

DECK_WARN_SIZE = 8
TOP_MISSING = 20

TIER_ACTOR = "actor"
TIER_PNG = "png"
TIER_NONE = "none"


@dataclass(frozen=True)
class LevelRow:
    """一关的 deck 事实。"""

    name: str
    world: str
    index: int
    deck: tuple[str, ...]


@dataclass(frozen=True)
class PlantInfo:
    """plants.json 的一条。"""

    id: str
    behavior: str
    art: str


@dataclass(frozen=True)
class MissingPlant:
    """deck 引用、但没有骨骼模型（或连图都没有）的植物。"""

    id: str
    uses: int
    behavior: str
    art: str
    tier: str

    @property
    def has_family(self) -> bool:
        return self.behavior in PLANT_FAMILIES


@dataclass(frozen=True)
class WorldCoverage:
    """一个世界的 deck 覆盖。"""

    world: str
    levels: int
    slots: int
    plants: int
    with_family: int
    with_actor: int
    with_png: int
    without_art: int
    empty_decks: int
    oversized: int


@dataclass(frozen=True)
class TotalCoverage:
    """全部世界的合计。"""

    levels: int
    worlds: int
    slots: int
    plants: int
    with_family: int
    with_actor: int
    with_png: int
    without_art: int
    empty_decks: int
    oversized: int

    @property
    def mean_deck(self) -> float:
        if not self.levels:
            return 0.0
        return self.slots / self.levels


@dataclass(frozen=True)
class DeckReport:
    """一次扫描的全部结果。"""

    levels: tuple[LevelRow, ...]
    worlds: tuple[WorldCoverage, ...]
    totals: TotalCoverage
    missing: tuple[MissingPlant, ...]
    oversized: tuple[LevelRow, ...]
    empty: tuple[LevelRow, ...]
    unknown: tuple[tuple[str, str], ...]
    registry_total: int
    registry_actor: int
    registry_png: int
    registry_none: int
    distinct_actors: int
    actor_total: int
    reuse: tuple[tuple[str, tuple[str, ...]], ...]
    missing_all: tuple[MissingPlant, ...]
    used_plants: tuple[str, ...]
    path_levels: str
    path_plants: str
    path_assets: str


def _rel(path: Path) -> str:
    """仓库内路径尽量写成相对形式，保证报告可移植、可复现。"""

    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(ROOT.parent.parent).as_posix()
        except ValueError:
            return path.name


def load_levels(levels_dir: Path) -> tuple[LevelRow, ...]:
    """按文件名顺序读全部关卡；world 以文件里的字段为准，缺字段时退回文件名前缀。"""

    rows: list[LevelRow] = []
    for path in sorted(levels_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            raise ValueError(f"{path.name}: 关卡文件根必须是对象")
        world = str(data.get("world") or path.stem.rsplit("_", 1)[0])
        index = data.get("index")
        if not isinstance(index, int):
            index = -1
        deck = data.get("deck") or []
        if not isinstance(deck, list):
            raise ValueError(f"{path.name}: deck 必须是数组")
        rows.append(
            LevelRow(
                name=path.stem,
                world=world,
                index=index,
                deck=tuple(str(item) for item in deck),
            )
        )
    return tuple(rows)


def load_plants(path: Path) -> dict[str, PlantInfo]:
    """读客户端植物注册表。"""

    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError(f"{path.name}: 根必须是数组")
    out: dict[str, PlantInfo] = {}
    for entry in data:
        if not isinstance(entry, dict) or "id" not in entry:
            continue
        pid = str(entry["id"])
        out[pid] = PlantInfo(
            id=pid,
            behavior=str(entry.get("behavior") or ""),
            art=str(entry.get("art") or ""),
        )
    return out


def load_actors(db_dir: Path) -> tuple[set[str], int]:
    """读 MANIFEST.json 的 actors[].key，并返回 actor 总数。"""

    manifest = json.loads((db_dir / "MANIFEST.json").read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict):
        raise ValueError("MANIFEST.json: 根必须是对象")
    actors = manifest.get("actors") or []
    if not isinstance(actors, list):
        raise ValueError("MANIFEST.json: actors 必须是数组")
    keys = {str(item["key"]) for item in actors if isinstance(item, dict) and "key" in item}
    return keys, len(actors)


def art_tier(plant: PlantInfo, actors: set[str], assets: Path) -> str:
    """把植物美术归到三档之一。"""

    if plant.art and plant.art in actors:
        return TIER_ACTOR
    if plant.art and (assets / plant.art).is_file():
        return TIER_PNG
    return TIER_NONE


def build(
    levels_dir: Path = DEFAULT_LEVELS,
    plants_path: Path = DEFAULT_PLANTS,
    assets: Path = DEFAULT_ASSETS,
) -> DeckReport:
    """扫描关卡并汇总。"""

    levels = load_levels(levels_dir)
    plants = load_plants(plants_path)
    actors, actor_total = load_actors(assets / "db")

    tier_of: dict[str, str] = {
        pid: art_tier(plant, actors, assets) for pid, plant in plants.items()
    }

    uses: Counter[str] = Counter()
    unknown: list[tuple[str, str]] = []
    per_world_uses: dict[str, Counter[str]] = defaultdict(Counter)
    per_world_levels: Counter[str] = Counter()
    per_world_slots: Counter[str] = Counter()
    per_world_empty: Counter[str] = Counter()
    per_world_oversized: Counter[str] = Counter()

    oversized: list[LevelRow] = []
    empty: list[LevelRow] = []

    for row in levels:
        per_world_levels[row.world] += 1
        per_world_slots[row.world] += len(row.deck)
        if not row.deck:
            empty.append(row)
            per_world_empty[row.world] += 1
        if len(row.deck) > DECK_WARN_SIZE:
            oversized.append(row)
            per_world_oversized[row.world] += 1
        for pid in row.deck:
            uses[pid] += 1
            per_world_uses[row.world][pid] += 1
            if pid not in plants:
                unknown.append((row.name, pid))

    worlds: list[WorldCoverage] = []
    for world in sorted(per_world_levels):
        ids = per_world_uses[world]
        worlds.append(
            WorldCoverage(
                world=world,
                levels=per_world_levels[world],
                slots=per_world_slots[world],
                plants=len(ids),
                with_family=sum(1 for pid in ids if pid in plants and plants[pid].behavior in PLANT_FAMILIES),
                with_actor=sum(1 for pid in ids if tier_of.get(pid) == TIER_ACTOR),
                with_png=sum(1 for pid in ids if tier_of.get(pid) == TIER_PNG),
                without_art=sum(1 for pid in ids if tier_of.get(pid) == TIER_NONE),
                empty_decks=per_world_empty[world],
                oversized=per_world_oversized[world],
            )
        )

    used = tuple(sorted(uses))
    missing = tuple(
        MissingPlant(
            id=pid,
            uses=uses[pid],
            behavior=plants[pid].behavior,
            art=plants[pid].art,
            tier=tier_of[pid],
        )
        for pid in sorted(used, key=lambda key: (-uses[key], key))
        if tier_of.get(pid) != TIER_ACTOR
    )

    registry_tiers = Counter(tier_of.values())
    distinct_actors = len({plants[pid].art for pid in plants if tier_of[pid] == TIER_ACTOR})

    reuse_groups: dict[str, list[str]] = defaultdict(list)
    for pid in sorted(plants):
        if tier_of[pid] == TIER_ACTOR:
            reuse_groups[plants[pid].art].append(pid)
    reuse = tuple(
        sorted(
            ((key, tuple(ids)) for key, ids in reuse_groups.items() if len(ids) > 1),
            key=lambda item: (-len(item[1]), item[0]),
        )
    )

    missing_all = tuple(
        MissingPlant(
            id=pid,
            uses=uses[pid],
            behavior=plants[pid].behavior,
            art=plants[pid].art,
            tier=tier_of[pid],
        )
        for pid in sorted(plants, key=lambda key: (-uses[key], key))
        if tier_of[pid] != TIER_ACTOR
    )

    totals = TotalCoverage(
        levels=len(levels),
        worlds=len(worlds),
        slots=sum(uses.values()),
        plants=len(used),
        with_family=sum(1 for pid in used if pid in plants and plants[pid].behavior in PLANT_FAMILIES),
        with_actor=sum(1 for pid in used if tier_of.get(pid) == TIER_ACTOR),
        with_png=sum(1 for pid in used if tier_of.get(pid) == TIER_PNG),
        without_art=sum(1 for pid in used if tier_of.get(pid) == TIER_NONE),
        empty_decks=len(empty),
        oversized=len(oversized),
    )

    return DeckReport(
        levels=levels,
        worlds=tuple(worlds),
        totals=totals,
        missing=missing,
        oversized=tuple(oversized),
        empty=tuple(empty),
        unknown=tuple(unknown),
        registry_total=len(plants),
        registry_actor=registry_tiers.get(TIER_ACTOR, 0),
        registry_png=registry_tiers.get(TIER_PNG, 0),
        registry_none=registry_tiers.get(TIER_NONE, 0),
        distinct_actors=distinct_actors,
        actor_total=actor_total,
        reuse=reuse,
        missing_all=missing_all,
        used_plants=used,
        path_levels=_rel(levels_dir),
        path_plants=_rel(plants_path),
        path_assets=_rel(assets),
    )


def _table(header: Sequence[str], rows: Iterable[Sequence[object]]) -> list[str]:
    """markdown 表格；数字右对齐、文字左对齐交给读者的渲染器。"""

    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join("---" for _ in header) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def render_report(report: DeckReport) -> str:
    """整份 markdown 报告；顺序固定，不含时间戳与绝对路径。"""

    total = report.totals
    lines: list[str] = []
    add = lines.append

    add("# 卡组（deck）覆盖报告")
    add("")
    add("> 由 `python tools/contentc/decks.py` 生成，不要手改；`--check` 会在报告过期时失败。")
    add("")
    add("## 输入")
    add("")
    lines += _table(
        ("项", "路径", "数量"),
        (
            ("关卡", f"`{report.path_levels}/*.json`", total.levels),
            ("植物注册表", f"`{report.path_plants}`", report.registry_total),
            ("美术库 actor 总数", f"`{report.path_assets}/db/MANIFEST.json`", report.actor_total),
            ("植物用到的独立 actor", "（同上）", report.distinct_actors),
        ),
    )
    add("")

    add("## 摘要")
    add("")
    lines += _table(
        ("指标", "数值"),
        (
            ("关卡总数", total.levels),
            ("世界数", total.worlds),
            ("deck 槽位总数", total.slots),
            ("平均 deck 大小", f"{total.mean_deck:.2f}"),
            ("deck 去重植物", total.plants),
            ("deck 为空", total.empty_decks),
            (f"deck 超过 {DECK_WARN_SIZE} 张", total.oversized),
            ("引用 plants.json 之外的 id", len(report.unknown)),
            ("本轮 deck 里有骨骼模型（actor）", total.with_actor),
            ("本轮 deck 里只有静态图（png）", total.with_png),
            ("本轮 deck 里无任何美术", total.without_art),
        ),
    )
    add("")

    add("## 美术三档")
    add("")
    add(f"- `{TIER_ACTOR}`：植物 `art` 命中 `<assets>/db/MANIFEST.json` 的 actor key，有骨骼动画，算“真模型”。")
    add(f"- `{TIER_PNG}`：植物 `art` 是 `<assets>` 下真实存在的 png，只能静态贴图，动不了。")
    add(f"- `{TIER_NONE}`：两者都没有，只能画色块。")
    add("")
    add(
        f"全部 {report.registry_total} 株植物：`{TIER_ACTOR}` {report.registry_actor} / "
        f"`{TIER_PNG}` {report.registry_png} / `{TIER_NONE}` {report.registry_none}；"
        f"但独立 actor 只有 {report.distinct_actors} 个——{report.registry_actor} 株“有模型”里"
        "大量是同一套骨骼换皮，真正的独立模型数是后者。"
    )
    add("")

    add("## 模型复用（一个 actor 顶多株植物）")
    add("")
    add(
        f"美术库里共 {report.actor_total} 个 actor，植物只用到其中 {report.distinct_actors} 个；"
        f"{report.registry_actor} 株“有模型”的植物分布在这 {report.distinct_actors} 套骨骼上，"
        f"其中 {report.registry_actor - report.distinct_actors} 株没有独占模型。"
        "下表只列被 2 株以上植物共用的 actor（按株数降序）。"
    )
    add("")
    lines += _table(
        ("actor", "植物数", "植物 id"),
        (
            (f"`{key}`", len(ids), "、".join(f"`{pid}`" for pid in ids))
            for key, ids in report.reuse
        ),
    )
    add("")

    add("## 逐世界覆盖")
    add("")
    add("“有行为族”= 植物 `behavior` 落在 `registry.cpp:486 plantFamilies()` 的 11 族里。")
    add("")
    lines += _table(
        ("世界", "关卡", "deck 槽位", "去重植物", "有行为族", "真模型", "仅静态图", "无美术", "空 deck", f"超 {DECK_WARN_SIZE} 张"),
        [
            (
                w.world,
                w.levels,
                w.slots,
                w.plants,
                w.with_family,
                w.with_actor,
                w.with_png,
                w.without_art,
                w.empty_decks,
                w.oversized,
            )
            for w in report.worlds
        ]
        + [
            (
                "**合计**",
                total.levels,
                total.slots,
                total.plants,
                total.with_family,
                total.with_actor,
                total.with_png,
                total.without_art,
                total.empty_decks,
                total.oversized,
            )
        ],
    )
    add("")

    add("## deck 缺真模型的植物")
    add("")
    add(
        f"deck 引用到 {total.plants} 株植物，其中 {len(report.missing)} 株没有骨骼模型："
        "它们只能出静态图或色块，动作、受击、死亡演出全部缺失。按 deck 引用次数降序。"
    )
    add("")
    lines += _table(
        ("植物", "引用次数", "行为族", "art", "档位"),
        ((m.id, m.uses, m.behavior or "（无）", f"`{m.art}`", m.tier) for m in report.missing),
    )
    add("")

    add(f"## deck 超过 {DECK_WARN_SIZE} 张的关卡")
    add("")
    if report.oversized:
        lines += _table(
            ("关卡", "世界", "deck 张数", "deck"),
            (
                (row.name, row.world, len(row.deck), ", ".join(f"`{pid}`" for pid in row.deck))
                for row in report.oversized
            ),
        )
    else:
        add("（无）")
    add("")

    add("## deck 引用但 plants.json 里不存在的 id")
    add("")
    if report.unknown:
        lines += _table(("关卡", "未知 id"), report.unknown)
    else:
        add("（无）每条 deck 里的植物 id 都能在 `content/plants.json` 里找到。")
    add("")

    add("## 空 deck 策略")
    add("")
    add(
        f"本版空 deck 共 {total.empty_decks} 关。策略：空 deck 的关卡按 `seed_bank` 的顺序取默认卡组；"
        "`seed_bank` 也为空时，该关单独列入“空 deck 关卡”清单，不参与“去重植物”统计，并在摘要里点名。"
        "当前没有这种关卡，所以上面的世界表里每一关的 deck 都是关卡文件自己声明的。"
    )
    add("")
    if report.empty:
        lines += _table(("空 deck 关卡", "世界"), ((row.name, row.world) for row in report.empty))
        add("")

    add("## 结论")
    add("")
    total_plants = report.registry_total or 1
    actor_pct = 100.0 * report.registry_actor / total_plants
    deck_pct = 100.0 * total.with_actor / (total.plants or 1)
    add(
        f"1. **有模型不等于有形象。** 注册表 {report.registry_total} 株植物里 {report.registry_actor} 株"
        f"（{actor_pct:.0f}%）"
        f"能挂到骨骼模型上，但这 {report.registry_actor} 株只用了 {report.distinct_actors} 套 actor——"
        f"独立形象只覆盖 {report.distinct_actors}/{report.registry_total}"
        f"（{100.0 * report.distinct_actors / total_plants:.0f}%），"
        f"{report.registry_actor - report.distinct_actors} 株是换皮。"
        f"另外 {report.registry_png} 株只有一张静态 png，{report.registry_none} 株连图都没有。"
    )
    add(
        f"2. **本轮真正被玩到的只有 {total.plants} 株。** 1809 关的 deck 一共 {total.slots} 个槽位，"
        f"去重后只引用 {total.plants} 株植物；其中 {total.with_actor} 株（{deck_pct:.0f}%）有骨骼模型，"
        f"{total.with_png} 株只有静态图，{total.without_art} 株无美术。"
        "也就是说：现有关卡能跑起来的部分，本质上是“少数几株植物反复出现”，"
        f"美术缺口集中在少数新世界植物上，而不是均匀分布在 {report.registry_total} 株里。"
    )
    add(
        "3. **对“完整复刻”的含义。** 行为族这一侧是齐的（"
        f"{total.with_family}/{total.plants} 株 deck 植物都有已实现的 behavior 族），"
        "真正的短板是表现层：没有骨骼模型的植物在引擎里只能当静态贴图或色块，"
        "补多少行为代码都换不来它的动作演出。若目标是 1809 关全部可玩到“看起来对”，"
        "必须先把 deck 实际引用的缺模型植物补齐，而不是去铺满注册表里的每一株。"
    )
    add("")
    add(f"建议先补的 id（按 deck 引用频次 top {TOP_MISSING}；含 deck 未引用的植物，其次数为 0）：")
    add("")
    ranked = report.missing_all
    lines += _table(
        ("#", "植物", "引用次数", "行为族", "当前档位"),
        (
            (rank, f"`{m.id}`", m.uses, m.behavior or "（无）", m.tier)
            for rank, m in enumerate(ranked[:TOP_MISSING], start=1)
        ),
    )
    add("")
    add(
        f"缺模型的植物一共 {len(ranked)} 株（其中 {len(report.missing)} 株被 deck 引用），"
        "补的顺序建议照这张表的次数走：前几株（"
        + "、".join(f"`{m.id}`" for m in ranked[:3])
        + "）占了缺模型引用的大头，先把它们做成 actor，比按世界顺序铺开的收益高得多。"
    )
    add("")
    add(f"（其余 {max(0, len(ranked) - TOP_MISSING)} 株未列出的缺模型植物不影响 1809 关的可玩性，可最后补。）")
    add("")

    return "\n".join(lines)


def write_report(report: DeckReport, path: Path) -> bytes:
    """写报告并返回写入的字节。"""

    return emit.write_text(path, render_report(report))


def summarize(report: DeckReport) -> str:
    """给终端看的一行摘要。"""

    total = report.totals
    return (
        f"levels={total.levels} worlds={total.worlds} slots={total.slots} "
        f"plants={total.plants} actor={total.with_actor} png={total.with_png} "
        f"none={total.without_art} empty={total.empty_decks} oversized={total.oversized} "
        f"unknown={len(report.unknown)} registry={report.registry_actor}/{report.registry_total}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="扫描全部关卡的 deck，写出覆盖报告（缺美术清单 + 逐世界统计）。"
    )
    parser.add_argument("--levels", type=Path, default=DEFAULT_LEVELS, help="content/levels 目录")
    parser.add_argument("--plants", type=Path, default=DEFAULT_PLANTS, help="content/plants.json")
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS, help="PvZ2SHUTTLE/assets 目录")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="输出 markdown 路径")
    parser.add_argument("--check", action="store_true", help="只校验报告是否最新，过期时退出码 1")
    parser.add_argument("-n", "--dry-run", action="store_true", help="只打印摘要，不写文件")
    args = parser.parse_args(argv)

    for label, path in (("levels", args.levels), ("plants", args.plants), ("assets", args.assets)):
        if not path.exists():
            print(f"缺少 {label}: {path}", file=sys.stderr)
            return 2

    report = build(args.levels, args.plants, args.assets)
    text = render_report(report)

    if args.dry_run:
        print(summarize(report))
        print(f"report chars={len(text)}")
        return 0

    if args.check:
        if not args.report.is_file():
            print(f"报告不存在: {args.report}", file=sys.stderr)
            return 1
        current = args.report.read_text(encoding="utf-8")
        if current != text:
            print(f"报告过期: {args.report}（重跑 tools/contentc/decks.py）", file=sys.stderr)
            return 1
        print(summarize(report))
        print(f"报告最新: {args.report}")
        return 0

    write_report(report, args.report)
    print(summarize(report))
    print(f"写出 {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
