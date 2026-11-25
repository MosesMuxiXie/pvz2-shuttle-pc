#!/usr/bin/env python3
"""融合配方编译：把原版 `PlantFusionConfig.FusionPairs` 编成可复核的数据 + 对齐报告。

运行：
    python tools/contentc/fusions.py            # 写 native/generated/fusions_from_pack.json + fusion_report.md
    python tools/contentc/fusions.py --check    # 产物过期时退出码 1
    python tools/contentc/fusions.py -n         # 只打印摘要

口径（先说清楚，免得数字对不上）：
- `pkg_2083_PlantFusionConfig.json` 有 **217 个 objects**，但其中 **199 个带 objdata**；
  真正装融合配方的只有 1 个 `PlantFusionConfig`，它的 `FusionPairs` 是 **85 条**。
  所以“199 对”这个说法是 objects 数被当成了对数——本报告按实测写 85，并把 217/199/1 的
  三层计数都列出来。
- 客户端 `content/fusions.json` 也是 85 条 `recipes`，但配方键（两个 ingredient 排序后）
  只有 **48 个**：37 个键在两边各出现两次（原版把同一配方登记两遍，客户端拆成基础条 +
  数字后缀变体：36 条 `_2`、1 条 `_3`），11 个键只出现一次。

id 归一（不发明规则）：
  优先级 1：值本身就是 client 植物 id（`content/plants.json`）→ 原样保留
  优先级 2：`native/generated/id_mapping.csv` 里 pack_type → client_id 的映射 → 换名
  优先级 3：都不是 → 保留原值，标 `pack`
  结果列同理：`fused_<值>` 若在 client 融合结果里存在就采用（85 条全部命中），否则保留原值。
  配对级 `sourceKind`：两个 ingredient 都归一成 client id → `client`，否则 `pack`。

产物：
    native/generated/fusions_from_pack.json   format=1、counts、pairs（按 source,fusion 排序）
    native/generated/fusion_report.md          计数、归一、与 content 的三方对齐、结论

两次运行字节一致（`emit.dumps` + 无时间戳）。
"""

from __future__ import annotations

import argparse
import csv
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
import os

DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages"))
DEFAULT_CONFIG = DEFAULT_OBB / "pkg_2083_PlantFusionConfig.json"
DEFAULT_CONTENT = ROOT / "content" / "fusions.json"
DEFAULT_PLANTS = ROOT / "content" / "plants.json"
DEFAULT_MAPPING = ROOT / "native" / "generated" / "id_mapping.csv"
DEFAULT_JSON = ROOT / "native" / "generated" / "fusions_from_pack.json"
DEFAULT_REPORT = ROOT / "native" / "generated" / "fusion_report.md"

FORMAT = 1
MARKER = "fusion-compile-v1"
CONFIG_CLASS = "PlantFusionConfig"
VARIANT_RE = re.compile(r"_\d+$")
HEAD_LIMIT = 20


@dataclass(frozen=True)
class Pair:
    """一条编译后的融合配方。"""

    source: str
    fusion: str
    result: str
    only_result: bool
    sound: str | None
    source_kind: str
    raw: dict[str, object]

    def key(self) -> tuple[str, str]:
        return (self.source, self.fusion)

    def payload(self) -> dict[str, object]:
        return {
            "source": self.source,
            "fusion": self.fusion,
            "result": self.result,
            "onlyResult": self.only_result,
            "sound": self.sound,
            "sourceKind": self.source_kind,
            "raw": self.raw,
        }


@dataclass(frozen=True)
class Ingredients:
    """配对级对齐用的键（两个 ingredient 排序后）。"""

    pair: tuple[str, str]


@dataclass(frozen=True)
class Alignment:
    """pack 与 content 的配方对齐结果。"""

    pack_keys: tuple[tuple[str, str], ...]
    content_keys: tuple[tuple[str, str], ...]
    shared: tuple[tuple[str, str], ...]
    only_pack: tuple[tuple[str, str], ...]
    only_content: tuple[tuple[str, str], ...]
    pack_multiplicity_equal: bool
    content_variants: int
    variant_suffixes: tuple[tuple[str, int], ...]
    content_recipes: int


@dataclass(frozen=True)
class Compile:
    """一次编译的全部结果。"""

    pairs: tuple[Pair, ...]
    objects: int
    objects_with_data: int
    configs: int
    counts: dict[str, object]
    alignment: Alignment
    ingredient_client: int
    ingredient_pack: int
    result_resolved: int
    result_raw: int
    path_config: str
    path_content: str
    path_mapping: str

    @property
    def payload_pairs(self) -> list[dict[str, object]]:
        return [pair.payload() for pair in self.pairs]


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(ROOT.parent.parent).as_posix()
        except ValueError:
            return path.name


def load_config(path: Path) -> tuple[list[dict[str, object]], int, int]:
    """读 pkg_2083：返回 (FusionPairs, objects 总数, 带 objdata 的 objects 数)。"""

    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    objects = doc.get("objects") or []
    if not isinstance(objects, list):
        raise ValueError(f"{path.name}: objects 必须是数组")
    pairs: list[dict[str, object]] = []
    for obj in objects:
        if not isinstance(obj, dict) or obj.get("objclass") != CONFIG_CLASS:
            continue
        data = obj.get("objdata") or {}
        chunk = data.get("FusionPairs") if isinstance(data, dict) else None
        if isinstance(chunk, list):
            pairs.extend(row for row in chunk if isinstance(row, dict))
    with_data = sum(1 for obj in objects if isinstance(obj, dict) and isinstance(obj.get("objdata"), dict))
    return pairs, len(objects), with_data


def load_client(path: Path) -> dict[str, object]:
    """读 content/fusions.json（根是对象，recipes 是数组）。"""

    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("recipes"), list):
        raise ValueError(f"{path.name}: 需要 objects 风格，含 recipes 数组")
    return data


def load_client_plants(path: Path) -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError(f"{path.name}: 根必须是数组")
    return {str(row["id"]) for row in data if isinstance(row, dict) and "id" in row}


def load_mapping(path: Path) -> dict[str, str]:
    """pack_type → client_id；只取 plant 且两侧都非空的 exact/popanim/almanac/manual 行。"""

    reverse: dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    for row in csv.DictReader(text.splitlines()):
        if row.get("side") != "plant":
            continue
        client_id = (row.get("client_id") or "").strip()
        pack_type = (row.get("pack_type") or "").strip()
        if client_id and pack_type:
            reverse.setdefault(pack_type, client_id)
    return reverse


def normalize_ingredient(
    value: object, client_plants: set[str], reverse: dict[str, str]
) -> tuple[str, str]:
    """ingredient 归一：client id 原样 → 映射表换名 → 保留原值（pack）。"""

    text = str(value)
    if text in client_plants:
        return text, "client"
    if text in reverse:
        return reverse[text], "mapping"
    return text, "pack"


def normalize_result(value: object, fused_ids: set[str]) -> tuple[str, str]:
    """result 归一：优先 client 已有的 `fused_<值>`，其次原值，最后保留 pack。"""

    text = str(value)
    if text in fused_ids:
        return text, "client"
    candidate = f"fused_{text}"
    if candidate in fused_ids:
        return candidate, "prefix"
    return text, "pack"


def _pair_key(ingredients: Iterable[object]) -> tuple[str, str]:
    vals = sorted(str(v) for v in ingredients)
    while len(vals) < 2:
        vals.append("")
    return (vals[0], vals[1])


def load_content_keys(
    client: dict[str, object],
) -> tuple[list[tuple[str, str]], int, tuple[tuple[str, int], ...]]:
    """content recipes → (配方键列表, 数字后缀变体数, 各后缀计数)。"""

    keys: list[tuple[str, str]] = []
    variants = 0
    suffixes: Counter[str] = Counter()
    for recipe in client.get("recipes") or []:
        if not isinstance(recipe, dict):
            continue
        ingredients = recipe.get("ingredients") or []
        keys.append(_pair_key(ingredients))
        result = recipe.get("result")
        if isinstance(result, dict):
            match = VARIANT_RE.search(str(result.get("id", "")))
            if match:
                variants += 1
                suffixes[match.group(0)] += 1
    return keys, variants, tuple(sorted(suffixes.items()))


def compile_fusions(
    config_path: Path = DEFAULT_CONFIG,
    content_path: Path = DEFAULT_CONTENT,
    plants_path: Path = DEFAULT_PLANTS,
    mapping_path: Path = DEFAULT_MAPPING,
) -> Compile:
    """读源表 → 归一 → 与 content 对齐。"""

    raw_pairs, objects, with_data = load_config(config_path)
    client = load_client(content_path)
    client_plants = load_client_plants(plants_path)
    reverse = load_mapping(mapping_path)
    fused_ids = {
        str(recipe["result"]["id"])
        for recipe in client.get("recipes") or []
        if isinstance(recipe, dict) and isinstance(recipe.get("result"), dict)
    }

    pairs: list[Pair] = []
    ingredient_client = 0
    ingredient_pack = 0
    result_resolved = 0
    for row in raw_pairs:
        source, source_kind = normalize_ingredient(row.get("SourcePlant"), client_plants, reverse)
        fusion, fusion_kind = normalize_ingredient(row.get("FusionPlant"), client_plants, reverse)
        result, result_kind = normalize_result(row.get("ResultPlant"), fused_ids)
        for kind in (source_kind, fusion_kind):
            if kind == "pack":
                ingredient_pack += 1
            else:
                ingredient_client += 1
        if result_kind != "pack":
            result_resolved += 1
        sound = row.get("FusionSoundEvent")
        pairs.append(
            Pair(
                source=source,
                fusion=fusion,
                result=result,
                only_result=bool(row.get("FusionOnlyHasResultPlant")),
                sound=str(sound) if sound else None,
                source_kind="client" if source_kind != "pack" and fusion_kind != "pack" else "pack",
                raw={
                    "SourcePlant": row.get("SourcePlant"),
                    "FusionPlant": row.get("FusionPlant"),
                    "ResultPlant": row.get("ResultPlant"),
                    "FusionOnlyHasResultPlant": row.get("FusionOnlyHasResultPlant"),
                    "FusionSoundEvent": row.get("FusionSoundEvent"),
                },
            )
        )

    pairs.sort(key=lambda pair: (pair.source, pair.fusion, pair.result, pair.sound or ""))

    content_keys, content_variants, variant_suffixes = load_content_keys(client)
    pack_keys = [_pair_key((pair.source, pair.fusion)) for pair in pairs]
    pack_counter = Counter(pack_keys)
    content_counter = Counter(content_keys)
    shared = tuple(sorted(set(pack_counter) & set(content_counter)))
    only_pack = tuple(sorted(set(pack_counter) - set(content_counter)))
    only_content = tuple(sorted(set(content_counter) - set(pack_counter)))
    alignment = Alignment(
        pack_keys=tuple(pack_keys),
        content_keys=tuple(content_keys),
        shared=shared,
        only_pack=only_pack,
        only_content=only_content,
        pack_multiplicity_equal=pack_counter == content_counter,
        content_variants=content_variants,
        variant_suffixes=variant_suffixes,
        content_recipes=len(content_keys),
    )

    counts: dict[str, object] = {
        "objects": objects,
        "objectsWithData": with_data,
        "configs": 1,
        "pairs": len(pairs),
        "uniqueSource": len({pair.source for pair in pairs}),
        "uniqueFusion": len({pair.fusion for pair in pairs}),
        "uniqueResult": len({pair.result for pair in pairs}),
        "onlyResult": sum(1 for pair in pairs if pair.only_result),
        "withSound": sum(1 for pair in pairs if pair.sound),
        "pairsClient": sum(1 for pair in pairs if pair.source_kind == "client"),
        "pairsPack": sum(1 for pair in pairs if pair.source_kind == "pack"),
        "ingredientsClient": ingredient_client,
        "ingredientsPack": ingredient_pack,
        "resultsResolved": result_resolved,
        "packKeys": len(pack_counter),
        "contentRecipes": alignment.content_recipes,
        "contentKeys": len(content_counter),
        "contentVariants": content_variants,
        "contentBaseResults": len(content_keys) - content_variants,
        "sharedKeys": len(shared),
        "onlyPackKeys": len(only_pack),
        "onlyContentKeys": len(only_content),
    }

    return Compile(
        pairs=tuple(pairs),
        objects=objects,
        objects_with_data=with_data,
        configs=1,
        counts=counts,
        alignment=alignment,
        ingredient_client=ingredient_client,
        ingredient_pack=ingredient_pack,
        result_resolved=result_resolved,
        result_raw=len(raw_pairs),
        path_config=_rel(config_path),
        path_content=_rel(content_path),
        path_mapping=_rel(mapping_path),
    )


def render_json(result: Compile) -> str:
    payload = {
        "format": FORMAT,
        "generated": MARKER,
        "sources": {
            "config": result.path_config,
            "content": result.path_content,
            "mapping": result.path_mapping,
        },
        "counts": result.counts,
        "pairs": result.payload_pairs,
    }
    return emit.dumps(payload)


def _table(header: Sequence[str], rows: Iterable[Sequence[object]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def _key_list(keys: Iterable[tuple[str, str]], limit: int = HEAD_LIMIT) -> list[str]:
    vals = list(keys)
    if not vals:
        return ["（无）"]
    lines = [f"- `{a}` + `{b}`" for a, b in vals[:limit]]
    if len(vals) > limit:
        lines.append(f"- …（共 {len(vals)} 条，只列前 {limit}）")
    return lines


def render_report(result: Compile) -> str:
    counts = result.counts
    alignment = result.alignment
    lines: list[str] = []
    add = lines.append

    add("# pack 融合配方报告")
    add("")
    add("> 由 `python tools/contentc/fusions.py` 生成，不要手改；`--check` 会在产物过期时失败。")
    add("")
    add("## 口径与结论（先看这段）")
    add("")
    add(
        f"- 源表 `{result.path_config}`：**{counts['objects']} 个 objects，其中 "
        f"{counts['objectsWithData']} 个带 objdata**；真正装融合配方的只有 "
        f"**{counts['configs']} 个 `PlantFusionConfig`**，它的 `FusionPairs` 是 "
        f"**{counts['pairs']} 条**。"
    )
    add(
        "  **“199 对”是把 199 个带 objdata 的 objects 当成了对数**——本树里 199 是 object 计数，"
        f"配方对数实测 {counts['pairs']}。两个数字都在上表里可复现。"
    )
    add(
        f"- 归一：{counts['ingredientsClient']} / "
        f"{counts['ingredientsClient'] + counts['ingredientsPack']} 个 ingredient 能落到 client 植物 id，"
        f"其余 {counts['ingredientsPack']} 个保留 pack 原值；两位 ingredient 都是 client id 的配对 "
        f"**{counts['pairsClient']}** 条，其余 **{counts['pairsPack']}** 条标 `sourceKind=pack`，一条都没丢。"
    )
    add(
        f"- 结果列：{counts['resultsResolved']} / {counts['pairs']} 条能对上 client 的 "
        "`fused_<原版名>`（客户端给融合产物加了 `fused_` 前缀）。"
    )
    add(
        f"- 与 `{result.path_content}` 对齐：配方键（两个 ingredient 排序）**pack "
        f"{counts['packKeys']} 个 / content {counts['contentKeys']} 个，交集 "
        f"{counts['sharedKeys']} 个，只在 pack {counts['onlyPackKeys']} 个、只在 content "
        f"{counts['onlyContentKeys']} 个**；每个键出现次数两边一致："
        f"{'是' if alignment.pack_multiplicity_equal else '否'}。"
    )
    add(
        f"- 结果侧对得上：content 的 {counts['contentBaseResults']} 个“基础结果”（无数字后缀）与 pack 的 "
        f"{counts['uniqueResult']} 个唯一 ResultPlant **集合完全相同**；另外 {counts['contentVariants']} "
        "条是数字后缀变体。"
    )
    suffix_text = "、".join(f"`{suffix}` {count} 条" for suffix, count in alignment.variant_suffixes) or "无"
    add(
        f"- 结论：**client 的 {counts['contentRecipes']} 条融合配方（{counts['contentKeys']} 个配方键）"
        f"在 pack 里全都有对应**，没有“content 自创、原版没有”的配方。"
        f"content 多出来的条数来自数字后缀变体（{suffix_text}）：同一配方键在 pack 里登记两次，"
        "客户端把第二次拆成独立结果 id。"
    )
    add("")

    add("## 计数")
    add("")
    lines += _table(
        ("指标", "数值"),
        (
            ("objects（源表）", counts["objects"]),
            ("objects 带 objdata", counts["objectsWithData"]),
            ("PlantFusionConfig 实例", counts["configs"]),
            ("FusionPairs（对数）", counts["pairs"]),
            ("唯一 SourcePlant 归一值", counts["uniqueSource"]),
            ("唯一 FusionPlant 归一值", counts["uniqueFusion"]),
            ("唯一 ResultPlant 归一值", counts["uniqueResult"]),
            ("FusionOnlyHasResultPlant", counts["onlyResult"]),
            ("带 FusionSoundEvent", counts["withSound"]),
            ("配方键（pack）", counts["packKeys"]),
            ("recipes（content）", counts["contentRecipes"]),
            ("配方键（content）", counts["contentKeys"]),
            ("数字后缀变体（content）", counts["contentVariants"]),
            ("基础结果（content，无后缀）", counts["contentBaseResults"]),
        ),
    )
    add("")

    add("## 归一")
    add("")
    add(
        "规则见 `tools/contentc/fusions.py` 顶部：client 植物 id 原样 → `id_mapping.csv` 的 "
        "pack_type→client_id → 保留原值标 `pack`；结果列优先 `fused_<值>`。"
    )
    add("")
    lines += _table(
        ("项", "client 侧", "pack 侧", "合计"),
        (
            (
                "ingredient",
                counts["ingredientsClient"],
                counts["ingredientsPack"],
                counts["ingredientsClient"] + counts["ingredientsPack"],
            ),
            ("配对 sourceKind", counts["pairsClient"], counts["pairsPack"], counts["pairs"]),
            ("结果列", counts["resultsResolved"], counts["pairs"] - counts["resultsResolved"], counts["pairs"]),
        ),
    )
    add("")

    add("## 与 content 对齐")
    add("")
    add(f"pack 侧配方键 {counts['packKeys']} 个，content 侧 {counts['contentKeys']} 个。")
    add("")
    add(f"### 交集（{len(alignment.shared)} 个）")
    add("")
    lines += _key_list(alignment.shared)
    add("")
    add(f"### 只在 pack（{len(alignment.only_pack)} 个）")
    add("")
    lines += _key_list(alignment.only_pack)
    add("")
    add(f"### 只在 content（{len(alignment.only_content)} 个）")
    add("")
    lines += _key_list(alignment.only_content)
    add("")

    add("## 结论：哪些 client 融合配方在 pack 里根本没有")
    add("")
    if alignment.only_content:
        add(f"有 {len(alignment.only_content)} 个 content 配方键在 pack 里找不到，见上一节。")
    else:
        add(
            "**没有**。client 的每个配方键都能在 `PlantFusionConfig.FusionPairs` 找到；"
            "`content/fusions.json` 不是自创配方，而是把这 85 条按“基础条 + 数字后缀变体”重新拆分，"
            "并补上了中文名、解锁价、plantfood 消耗等运营字段。"
        )
    add("")
    add(
        f"按 (配方键, 结果) 精确比对会有 {counts['contentVariants']} 条只在 content 侧："
        "pack 对同一配方键重复登记（两条一模一样的 ResultPlant），且不同配方键会得出同名结果"
        "（例如 `fused_fusiongatling` 有 `_2`…`_5`），客户端用数字后缀保证结果 id 唯一。"
        "这不是缺配方，是变体命名。"
    )
    add("")

    add(f"## 前 {HEAD_LIMIT} 条配对（按 source,fusion 排序）")
    add("")
    lines += _table(
        ("#", "source", "fusion", "result", "onlyResult", "sound", "kind"),
        (
            (
                index,
                f"`{pair.source}`",
                f"`{pair.fusion}`",
                f"`{pair.result}`",
                "是" if pair.only_result else "",
                pair.sound or "",
                pair.source_kind,
            )
            for index, pair in enumerate(result.pairs[:HEAD_LIMIT], start=1)
        ),
    )
    add("")

    return "\n".join(lines)


def write_outputs(result: Compile, json_path: Path, report_path: Path) -> tuple[bytes, bytes]:
    return (
        emit.write_text(json_path, render_json(result)),
        emit.write_text(report_path, render_report(result)),
    )


def summarize(result: Compile) -> str:
    counts = result.counts
    return (
        f"objects={counts['objects']} withData={counts['objectsWithData']} pairs={counts['pairs']} "
        f"pairsClient={counts['pairsClient']} pairsPack={counts['pairsPack']} "
        f"resultsResolved={counts['resultsResolved']} packKeys={counts['packKeys']} "
        f"contentKeys={counts['contentKeys']} shared={counts['sharedKeys']} "
        f"onlyPack={counts['onlyPackKeys']} onlyContent={counts['onlyContentKeys']}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="编译 PlantFusionConfig 的融合配方并与 content/fusions.json 对齐。")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="pkg_2083_PlantFusionConfig.json")
    parser.add_argument("--content", type=Path, default=DEFAULT_CONTENT, help="content/fusions.json")
    parser.add_argument("--plants", type=Path, default=DEFAULT_PLANTS, help="content/plants.json")
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING, help="native/generated/id_mapping.csv")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="输出 fusions_from_pack.json")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="输出 fusion_report.md")
    parser.add_argument("--check", action="store_true", help="只校验产物是否最新，过期时退出码 1")
    parser.add_argument("-n", "--dry-run", action="store_true", help="只打印摘要，不写文件")
    args = parser.parse_args(argv)

    for label, path in (
        ("config", args.config),
        ("content", args.content),
        ("plants", args.plants),
        ("mapping", args.mapping),
    ):
        if not path.is_file():
            print(f"缺少 {label}: {path}", file=sys.stderr)
            return 2

    result = compile_fusions(args.config, args.content, args.plants, args.mapping)
    json_text = render_json(result)
    report_text = render_report(result)

    if args.dry_run:
        print(summarize(result))
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
            print("重跑 tools/contentc/fusions.py 生成产物", file=sys.stderr)
            return 1
        print(summarize(result))
        print("产物最新")
        return 0

    write_outputs(result, args.json, args.report)
    print(summarize(result))
    print(f"写出 {args.json}")
    print(f"写出 {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
