"""Compile the plant-food (power-up) data that actually exists in the original pack.

口径（重要，先读这段再读代码）
==============================

原版**没有**独立的「养料效果表」。能拿到的只有两类东西：

1. `pkg_2073_PlantPropertySheet.json` 里逐株的两个标量列
   - `PlantFoodDurationSeconds`：养料动画循环时长（秒）
   - `PlantFoodPlayCount`：养料动画播放次数
   398 个属性表对象里，`PlantFoodDurationSeconds` 记 155 条（非零 147 条），
   `PlantFoodPlayCount` 记 189 条（非零 185 条）。这两个「非空」数是**属性表口径**，
   也就是 `counts.withDuration` / `counts.withPlayCount`。

2. `Actions` 里 `Type == "plantfood"` 的动作，全表**恰好 6 条**，反查到 6 株植物：
   `sungun`(CattailDefault)、`homingthistle`(HomingThistleDefault)、`dartichoke`(DartichokeDefault)、
   `draftodil1`(DraftodilDefault)、`magnetfruit`(MagnetFruitDefault)、`rheumnobile`(TurrheumImmobileDefault)。
   字段并集 7 个：`Type/Projectile/SpawnOffset/CooldownTimeMin/CooldownTimeMax/InitialMinCooldownTime/ProjectileLaunchSound`；
   `DraftodilDefault` 缺三个冷却字段，解析必须允许缺省（缺省写 null，行不能丢）。

植物 → 属性表的桥是 `pkg_2074_PlantType.json` 的 `Properties` 字段（`RTID(<alias>@PlantPropertySheet)`）：
339 株全部能解析到属性表对象，去重后 335 个属性表被引用，另有 63 个对象没有任何植物引用。

**能反查到植物的**非空数是 `plantsWithDuration=147` / `plantsWithPlayCount=172`，
比属性表口径的 189 少 17：189 条记录里 19 条所在属性表无人引用（含 `PlantPropertySheetTemplate`），
另有 4 株植物共用同一属性表。报告里两个口径都列出来，不混用。

`id` 采用客户端词汇表：`native/generated/id_mapping.csv` 里 plant 侧 44 条 exact 命中
（`pack_type → client_id`）直接归一；本表 293 行里 39 行归一成功，其余 254 行保留 pack id
并标 `idKind="pack"`。6 株带养料动作的植物只有 `homingthistle` 落在客户端词汇表内，
另外 5 株（`sungun`/`dartichoke`/`draftodil1`/`magnetfruit`/`rheumnobile`）是 pack 独有 id。

其余 333 株的养料效果、以及全部 147+ 株的文案，pack 里没有，必须 authored。
`gaps` 只记录**效果层**缺口（`["effect"]`），因为时长/次数的缺失已经由 `durationSeconds` /
`playCount` 的 null 自明；这样 `gaps` 非空行数恰好等于缺效果的行数。

开场养料数量在 `pkg_0236_LevelMutatorStartingPlantfoodProps`（`OverrideStartingPlantfood0..2`），
属于关卡层数据，不在本表范围内。

产物
====
- `native/generated/plantfood_from_pack.json`
- `native/generated/plantfood_report.md`

用法
====
    python tools/contentc/plantfood.py
    python tools/contentc/plantfood.py --check
    python tools/contentc/plantfood.py -n
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.contentc import emit  # noqa: E402
from tools.contentc.rtid import parse_rtid  # noqa: E402
import os

DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages"))
DEFAULT_PLANTS = DEFAULT_OBB / "pkg_2074_PlantType.json"
DEFAULT_PROPS = DEFAULT_OBB / "pkg_2073_PlantPropertySheet.json"
DEFAULT_MAPPING = ROOT / "native" / "generated" / "id_mapping.csv"
DEFAULT_FAMILIES = ROOT / "native" / "generated" / "plant_families.json"
DEFAULT_JSON = ROOT / "native" / "generated" / "plantfood_from_pack.json"
DEFAULT_REPORT = ROOT / "native" / "generated" / "plantfood_report.md"

FORMAT = 1
MARKER = "plantfood-compile-v1"

DURATION_FIELD = "PlantFoodDurationSeconds"
PLAY_COUNT_FIELD = "PlantFoodPlayCount"
ACTION_FIELD = "Actions"
ACTION_TYPE = "plantfood"

# 行为族 → 报告里的中文分组（与 content/plants.json 的 11 族一致）
FAMILY_BUCKETS = {
    "shoot": "直射",
    "lob": "抛射",
    "wall": "墙",
    "produce": "生产",
    "instant": "瞬时",
}
OTHER_BUCKET = "其他"
BUCKET_ORDER = ("直射", "抛射", "墙", "生产", "瞬时", OTHER_BUCKET)


@dataclass(frozen=True)
class TypeRow:
    type_name: str
    framework: str
    props_alias: str | None


@dataclass
class Stats:
    prop_sheet_objects: int = 0
    duration_records: int = 0
    duration_non_zero: int = 0
    play_count_records: int = 0
    play_count_non_zero: int = 0
    referenced_props: int = 0
    unreferenced_props: int = 0
    play_count_unreachable: int = 0
    play_count_reachable: int = 0
    play_count_shared: int = 0
    missing_effect_by_bucket: Counter = field(default_factory=Counter)

    def as_counts(self, rows: Sequence[dict]) -> dict:
        with_duration = sum(1 for r in rows if r["durationSeconds"] is not None)
        with_play_count = sum(1 for r in rows if r["playCount"] is not None)
        with_action = sum(1 for r in rows if r["effects"])
        client_rows = sum(1 for r in rows if r["idKind"] == "client")
        return {
            "propSheetObjects": self.prop_sheet_objects,
            "durationRecords": self.duration_records,
            "durationNonZero": self.duration_non_zero,
            "playCountRecords": self.play_count_records,
            "playCountNonZero": self.play_count_non_zero,
            "withDuration": self.duration_non_zero,
            "withPlayCount": self.play_count_non_zero,
            "withAction": with_action,
            "animated": with_duration,
            "plants": len(rows),
            "plantsWithDuration": with_duration,
            "plantsWithPlayCount": with_play_count,
            "clientIds": client_rows,
            "referencedProps": self.referenced_props,
            "unreferencedProps": self.unreferenced_props,
            "playCountUnreachable": self.play_count_unreachable,
            "playCountReachable": self.play_count_reachable,
            "playCountShared": self.play_count_shared,
            "missingEffectPlants": sum(self.missing_effect_by_bucket.values()),
        }


def _load_objects(path: Path) -> list[dict]:
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    objects = doc.get("objects") or []
    return [o for o in objects if isinstance(o, dict)]


def _alias(obj: dict) -> str | None:
    aliases = obj.get("aliases") or []
    for name in aliases:
        if isinstance(name, str) and name:
            return name
    return None


def load_types(path: Path) -> list[TypeRow]:
    """读取 PlantType 表：TypeName / PlantFramework / Properties → 属性表别名。"""
    rows: list[TypeRow] = []
    for obj in _load_objects(path):
        data = obj.get("objdata") or {}
        name = data.get("TypeName")
        if not isinstance(name, str) or not name:
            continue
        ref = parse_rtid(data.get("Properties"))
        rows.append(
            TypeRow(
                type_name=name,
                framework=str(data.get("PlantFramework") or ""),
                props_alias=ref[0] if ref else None,
            )
        )
    return rows


def load_props(path: Path) -> dict[str, dict]:
    """属性表别名 → objdata。"""
    table: dict[str, dict] = {}
    for obj in _load_objects(path):
        alias = _alias(obj)
        if alias:
            table[alias] = obj.get("objdata") or {}
    return table


def load_client_ids(path: Path) -> dict[str, str]:
    """id_mapping.csv：pack TypeName → client id（只取两侧都有值的精确命中行）。"""
    mapping: dict[str, str] = {}
    if not path.is_file():
        return mapping
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("side") != "plant":
                continue
            pack_type = (row.get("pack_type") or "").strip()
            client_id = (row.get("client_id") or "").strip()
            if pack_type and client_id:
                mapping.setdefault(pack_type, client_id)
    return mapping


def load_families(path: Path) -> dict[str, str]:
    """plant_families.json：pack 植物 id → 行为族。"""
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    families: dict[str, str] = {}
    for item in doc.get("plants") or []:
        if isinstance(item, dict) and item.get("id"):
            families[str(item["id"])] = str(item.get("family") or "")
    return families


def _number(value: object) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _sound(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _effects(obj: dict) -> list[dict]:
    found: list[dict] = []
    actions = obj.get(ACTION_FIELD)
    if not isinstance(actions, list):
        return found
    for action in actions:
        if not isinstance(action, dict):
            continue
        if str(action.get("Type") or "").lower() != ACTION_TYPE:
            continue
        ref = parse_rtid(action.get("Projectile"))
        spawn = action.get("SpawnOffset")
        found.append(
            {
                "kind": "projectile" if ref else "special",
                "projectile": ref[0] if ref else None,
                "spawnOffset": dict(spawn) if isinstance(spawn, dict) else None,
                "cooldownMin": _number(action.get("CooldownTimeMin")),
                "cooldownMax": _number(action.get("CooldownTimeMax")),
                "initialMin": _number(action.get("InitialMinCooldownTime")),
                "launchSound": _sound(action.get("ProjectileLaunchSound")),
                "source": "pack",
            }
        )
    return found


def _bucket(family: str) -> str:
    return FAMILY_BUCKETS.get(family, OTHER_BUCKET)


def build(
    plants_path: Path,
    props_path: Path,
    mapping_path: Path,
    families_path: Path,
) -> tuple[dict, Stats]:
    types = load_types(plants_path)
    props = load_props(props_path)
    client_of = load_client_ids(mapping_path)
    families = load_families(families_path)

    stats = Stats(prop_sheet_objects=len(props))
    referenced: set[str] = set()
    rows: list[dict] = []

    for type_row in types:
        alias = type_row.props_alias
        obj = props.get(alias or "", {})
        if alias in props:
            referenced.add(alias)

        duration = _number(obj.get(DURATION_FIELD))
        play_count = _number(obj.get(PLAY_COUNT_FIELD))
        effects = _effects(obj)

        if duration is not None or play_count is not None or effects:
            client_id = client_of.get(type_row.type_name)
            rows.append(
                {
                    "id": client_id or type_row.type_name,
                    "idKind": "client" if client_id else "pack",
                    "packType": type_row.type_name,
                    "framework": type_row.framework,
                    "durationSeconds": duration,
                    "playCount": play_count,
                    "effects": effects,
                    "source": "pack",
                    "gaps": [] if effects else ["effect"],
                }
            )

        if not effects:
            stats.missing_effect_by_bucket[_bucket(families.get(type_row.type_name, ""))] += 1

    # 属性表口径：只统计原表里真的写了这一列的对象
    for obj in props.values():
        if DURATION_FIELD in obj:
            stats.duration_records += 1
            if _number(obj.get(DURATION_FIELD)) not in (None, 0):
                stats.duration_non_zero += 1
        if PLAY_COUNT_FIELD in obj:
            stats.play_count_records += 1
            if _number(obj.get(PLAY_COUNT_FIELD)) not in (None, 0):
                stats.play_count_non_zero += 1

    stats.referenced_props = len(referenced)
    stats.unreferenced_props = len(props) - len(referenced)
    pc_sheets = {alias for alias, obj in props.items() if PLAY_COUNT_FIELD in obj}
    stats.play_count_reachable = len(pc_sheets & referenced)
    stats.play_count_unreachable = len(pc_sheets - referenced)
    usage: Counter = Counter()
    for type_row in types:
        if type_row.props_alias in pc_sheets:
            usage[type_row.props_alias] += 1
    stats.play_count_shared = sum(1 for value in usage.values() if value > 1)

    rows.sort(key=lambda r: (r["id"], r["packType"]))
    payload = {
        "format": FORMAT,
        "generated": MARKER,
        "counts": stats.as_counts(rows),
        "plants": rows,
    }
    return payload, stats


def _fmt(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "({x}, {y})".format(x=value.get("x"), y=value.get("y"))
    return str(value)


def render_report(payload: dict, stats: Stats) -> str:
    counts = payload["counts"]
    rows = payload["plants"]
    total = 339
    pct = lambda n: "{:.1f}%".format(100.0 * n / total)  # noqa: E731
    lines: list[str] = []
    add = lines.append

    add("# 养料数据编译报告")
    add("")
    add(
        "> 一句话结论：这 6 株可以用 pack 数据驱动到弹道层；147 株有时长、185 株有次数；"
        "其余 333 株的养料效果与全部文案都只能 authored。"
    )
    add("")

    add("## 一句话结论")
    add("")
    add("1. 6 株（sungun / homingthistle / dartichoke / draftodil1 / magnetfruit / rheumnobile）"
        "在 pack 里有完整的 `Type==plantfood` 动作，`Projectile` / `SpawnOffset` / 冷却三件套可以原值驱动到弹道层；"
        "其中 draftodil1 缺三个冷却字段，只保留弹体与偏移。")
    add("2. 147 株在属性表里有非零 `PlantFoodDurationSeconds`，185 株有非零 `PlantFoodPlayCount`，"
        "这两类数字可以直接进引擎做动画时长与播放次数。")
    add("3. 其余 333 株没有任何养料动作记录，效果必须 authored；全部植物的养料文案（名称/说明）pack 里也没有。")
    add("")

    add("## 计数")
    add("")
    add("| 指标 | 值 | 口径 |")
    add("| --- | --- | --- |")
    add(f"| 输出行数 | {counts['plants']} | 只要有任一时长/次数/动作的植物 |")
    add(f"| `withDuration` | {counts['withDuration']} | 属性表非零 `PlantFoodDurationSeconds`（记录 {counts['durationRecords']} 条） |")
    add(f"| `withPlayCount` | {counts['withPlayCount']} | 属性表非零 `PlantFoodPlayCount`（记录 {counts['playCountRecords']} 条） |")
    add(f"| `withAction` | {counts['withAction']} | `Actions` 里 `Type==plantfood` 的条数 |")
    add(f"| `animated` | {counts['animated']} | 输出行里时长非空的行数 |")
    add(f"| `plantsWithDuration` | {counts['plantsWithDuration']} | 能反查到植物的非空时长 |")
    add(f"| `plantsWithPlayCount` | {counts['plantsWithPlayCount']} | 能反查到植物的非空次数 |")
    add(f"| 属性表对象 | {counts['propSheetObjects']} | `pkg_2073` 全表 |")
    add(f"| 被植物引用 | {counts['referencedProps']} | 339 株去重后 |")
    add(f"| 无人引用 | {counts['unreferencedProps']} | 含 `PlantPropertySheetTemplate` |")
    add(f"| 次数可达属性表 | {counts['playCountReachable']} | 被植物引用且写了次数 |")
    add(f"| 次数不可达属性表 | {counts['playCountUnreachable']} | 写了次数但没有植物指向 |")
    add(f"| 被多株共用的次数表 | {counts['playCountShared']} | BonkchoyDefault / CitronDefault 各 2 株 |")
    add(f"| 缺效果植物 | {counts['missingEffectPlants']} | 必须 authored 的株数 |")
    add("")
    add(
        f"`withPlayCount={counts['withPlayCount']}` 是属性表记录口径（189 条记录、"
        f"{counts['playCountUnreachable']} 条所在表无人引用、非零 185 条），"
        f"`plantsWithPlayCount={counts['plantsWithPlayCount']}` 是植物口径："
        f"可达的 {counts['playCountReachable']} 张表服务 {counts['plantsWithPlayCount']} 株，"
        f"其中 {counts['playCountShared']} 张被两株共用（BonkchoyDefault / CitronDefault）。"
        "两个数不能直接相减，差额不是缺失。"
    )
    add("")

    add("## 6 株逐字段表")
    add("")
    add("| id | packType | framework | 时长(s) | 次数 | kind | projectile | spawnOffset | cooldownMin | cooldownMax | initialMin | launchSound |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        if not row["effects"]:
            continue
        for effect in row["effects"]:
            add(
                "| `{id}` | `{pack}` | `{fw}` | {dur} | {pc} | {kind} | `{proj}` | {spawn} | {cmin} | {cmax} | {imin} | {snd} |".format(
                    id=row["id"],
                    pack=row["packType"],
                    fw=row["framework"],
                    dur=_fmt(row["durationSeconds"]),
                    pc=_fmt(row["playCount"]),
                    kind=effect["kind"],
                    proj=_fmt(effect["projectile"]),
                    spawn=_fmt(effect["spawnOffset"]),
                    cmin=_fmt(effect["cooldownMin"]),
                    cmax=_fmt(effect["cooldownMax"]),
                    imin=_fmt(effect["initialMin"]),
                    snd=_fmt(effect["launchSound"]),
                )
            )
    add("")
    add(
        "`DraftodilDefault` 只有 `Projectile` 与 `SpawnOffset`，缺 `CooldownTimeMin` / `CooldownTimeMax` / "
        "`InitialMinCooldownTime`，解析不设默认值，三个字段写 null 而非丢行；5 株的 "
        "`ProjectileLaunchSound` 在原表里是空串，归一为 null（不是缺字段）。"
    )
    add("")

    add("## 覆盖率")
    add("")
    add(f"- 时长：{counts['withDuration']} / {total} = {pct(counts['withDuration'])}")
    add(f"- 次数：{counts['withPlayCount']} / {total} = {pct(counts['withPlayCount'])}")
    add(f"- 动作：{counts['withAction']} / {total} = {pct(counts['withAction'])}")
    add(f"- 输出行：{counts['plants']} / {total} = {pct(counts['plants'])}（有时长/次数/动作之一）")
    add("")
    add(
        "剩下的部分在 pack 里就是空的：没有独立的养料效果表，`Actions` 也不是每株都有；"
        "6 条动作之外的 333 株应当读作「数据不在表里」而不是「没有养料」——"
        "它们在游戏里当然有养料效果，只是原版把效果写在代码或别的表里。"
    )
    add("")

    add("## 必须 authored 的部分")
    add("")
    add("按行为族（`plant_families.json`）分组统计缺效果的 333 株：")
    add("")
    add("| 分组 | 株数 |")
    add("| --- | --- |")
    for bucket in BUCKET_ORDER:
        value = stats.missing_effect_by_bucket.get(bucket, 0)
        add(f"| {bucket} | {value} |")
    add(f"| 合计 | {sum(stats.missing_effect_by_bucket.values())} |")
    add("")
    add(
        "除了效果，**全部**植物的养料文案（名称、说明、升级文案）都必须 authored；"
        "pack 里只有 `PlantFoodDurationSeconds` / `PlantFoodPlayCount` 两个数字列，没有任何可读文本。"
    )
    add("")

    add("## 口径与来源")
    add("")
    add("- `obb_packages/pkg_2073_PlantPropertySheet.json`：逐株属性表，398 个对象；只取 "
        "`Actions`、`PlantFoodDurationSeconds`、`PlantFoodPlayCount` 三列。")
    add("- `obb_packages/pkg_2074_PlantType.json`：339 株植物，`Properties` 给出属性表别名，339 株全部可解析。")
    add("- `native/generated/id_mapping.csv`：plant 侧 44 条 exact 命中用于把 pack TypeName 归一成 client id；"
        f"本表 {counts['plants']} 行里 {counts['clientIds']} 行归一成功，其余保留 pack id（`idKind=\"pack\"`）。"
        "6 株带动作的植物只有 `homingthistle` 落在客户端词汇表内，其余 5 株是 pack 独有 id。")
    add("- `native/generated/plant_families.json`：行为族，用于缺效果的族分组。")
    add("- 开场养料数量在 `pkg_0236_LevelMutatorStartingPlantfoodProps`（`OverrideStartingPlantfood0..2`），"
        "属于关卡层，不在本表范围。")
    add("- `gaps` 只记效果层缺口（`[\"effect\"]`）：时长/次数缺失已由字段 null 表达，"
        "所以 `gaps` 非空行数 == 缺效果行数，不会双重计数。")
    add("")
    add("产物：`native/generated/plantfood_from_pack.json`（本报告的同源数据）。")
    add("")
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text


def write_outputs(payload: dict, report: str, json_path: Path, report_path: Path) -> None:
    emit.write_text(json_path, emit.dumps(payload))
    emit.write_text(report_path, report)


def summarize(payload: dict) -> str:
    counts = payload["counts"]
    return (
        "rows={plants} withDuration={withDuration} withPlayCount={withPlayCount} "
        "withAction={withAction} animated={animated} plantsWithPlayCount={plantsWithPlayCount} "
        "missingEffect={missingEffectPlants}"
    ).format(**counts)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile plant-food data that exists in the original pack.")
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB, help="obb_packages 目录")
    parser.add_argument("--plants", type=Path, default=None, help="pkg_2074_PlantType.json")
    parser.add_argument("--props", type=Path, default=None, help="pkg_2073_PlantPropertySheet.json")
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING, help="id_mapping.csv")
    parser.add_argument("--families", type=Path, default=DEFAULT_FAMILIES, help="plant_families.json")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="输出 JSON")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="输出 Markdown 报告")
    parser.add_argument("--check", action="store_true", help="只校验已提交产物是否最新")
    parser.add_argument("-n", "--dry-run", action="store_true", help="只统计，不写文件")
    args = parser.parse_args(argv)

    if not args.obb.is_dir():
        print(f"找不到 obb 目录：{args.obb}", file=sys.stderr)
        return 2
    plants_path = args.plants or (args.obb / "pkg_2074_PlantType.json")
    props_path = args.props or (args.obb / "pkg_2073_PlantPropertySheet.json")
    for path in (plants_path, props_path):
        if not path.is_file():
            print(f"找不到输入表：{path}", file=sys.stderr)
            return 2

    payload, stats = build(plants_path, props_path, args.mapping, args.families)
    report = render_report(payload, stats)

    if args.check:
        stale: list[str] = []
        if not args.json.is_file() or args.json.read_text(encoding="utf-8") != emit.dumps(payload):
            stale.append(str(args.json))
        if not args.report.is_file() or args.report.read_text(encoding="utf-8") != report:
            stale.append(str(args.report))
        if stale:
            for path in stale:
                print(f"产物过期：{path}", file=sys.stderr)
            return 2
        print(f"产物最新：{summarize(payload)}")
        return 0

    print(summarize(payload))
    if args.dry_run:
        return 0

    write_outputs(payload, report, args.json, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
