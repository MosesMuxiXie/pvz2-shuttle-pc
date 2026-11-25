"""t56 / T57 的唯一探针：egypt_74 保护目标重复坐标取证（只读，不写任何产物）。

运行::

    python work/t56_probe_protect.py

它做四件事，输出即报告 `docs/reviews/2026-11-24-egypt74-protect.md` 里所有数字的来源：

1. 打印 `egypt_74`（`pkg_1051`）的 `ProtectThePlantChallengeProperties` 原文与 Modules 引用；
2. 扫全部 2116 张原版表，统计 protect 模块的字段形态（模块级 / 每个 plant 级）；
3. 逐包算 `plants / distinct / must`，列出 `distinct < must` 与「按引擎放置顺序模拟后 placed < must」的关卡；
4. 把原版表与 `native/generated/level_mechanics.json` 逐条对照，报出编译侧的差异
   （多模块只取第一个、字符串坐标被强转等）。

只读：不写 content/、不写 native/、不写 docs/。
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBB = ROOT.parent.parent / "work" / "obb_packages"
MECHANICS = ROOT / "native" / "generated" / "level_mechanics.json"
CONTENT_LEVELS = ROOT / "content" / "levels"
PROTECT_CLS = "ProtectThePlantChallengeProperties"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def level_ids_by_package() -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for path in sorted(CONTENT_LEVELS.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        out[doc["extra"]["package"]].append(doc["id"])
    return out


def section_egypt74() -> None:
    print("== 1. egypt_74 原版原文 ==")
    doc = load(OBB / "pkg_1051_LevelDefinition.json")
    for index, obj in enumerate(doc["objects"]):
        cls = obj.get("objclass")
        if cls == PROTECT_CLS:
            print(f"objects[{index}] aliases={obj.get('aliases')} objclass={cls}")
            print(json.dumps(obj["objdata"], ensure_ascii=False, indent=1))
        elif cls == "LevelDefinition":
            data = obj.get("objdata") or {}
            names = [n for n in data.get("Modules") or [] if "Protect" in str(n)]
            print(f"LevelDefinition StageModule={data.get('StageModule')} LevelNumber={data.get('LevelNumber')}")
            print("Modules 里的 protect 引用:", names)


def scan_modules() -> list[dict]:
    ids = level_ids_by_package()
    rows: list[dict] = []
    module_keys: Counter = Counter()
    plant_keys: Counter = Counter()
    for path in sorted(OBB.glob("pkg_*_LevelDefinition.json")):
        package = path.name.split("_LevelDefinition")[0]
        doc = load(path)
        for index, obj in enumerate(doc.get("objects") or []):
            if not isinstance(obj, dict) or obj.get("objclass") != PROTECT_CLS:
                continue
            data = obj.get("objdata") or {}
            module_keys[tuple(sorted(data))] += 1
            plants = [p for p in data.get("Plants") or [] if isinstance(p, dict)]
            cells = []
            for plant in plants:
                plant_keys[tuple(sorted(plant))] += 1
                cells.append((int(str(plant.get("GridX"))), int(str(plant.get("GridY")))))
            alias = obj.get("aliases") or obj.get("alias")
            rows.append(
                {
                    "package": package,
                    "index": index,
                    "alias": alias[0] if isinstance(alias, list) and alias else alias,
                    "plants": len(plants),
                    "distinct": len(set(cells)),
                    "must": data.get("MustProtectCount"),
                    "cells": cells,
                    "types": [p.get("PlantType") for p in plants],
                    "levelIds": ids.get(package) or [],
                }
            )
    print("\n== 2. protect 模块的字段形态 ==")
    print("模块数:", len(rows), "| 覆盖包数:", len({r["package"] for r in rows}))
    print("模块级字段组合:", {",".join(k): v for k, v in module_keys.items()})
    print("plant 级字段组合:", {",".join(k): v for k, v in plant_keys.items()})
    print("must > plants（原版自相矛盾）:", sum(1 for r in rows if isinstance(r["must"], int) and r["must"] > r["plants"]))
    print("must == plants:", sum(1 for r in rows if r["must"] == r["plants"]))
    print("must < plants:", sum(1 for r in rows if isinstance(r["must"], int) and r["must"] < r["plants"]))
    print("must > distinct（去重后不够）:", sum(1 for r in rows if isinstance(r["must"], int) and r["must"] > r["distinct"]))
    multi = Counter(r["package"] for r in rows)
    print("一包多模块:", {k: v for k, v in multi.items() if v > 1})
    return rows


def section_duplicates(rows: list[dict]) -> None:
    print("\n== 3a. 坐标重复的模块（plants != distinct）==")
    dup = sorted((r for r in rows if r["plants"] != r["distinct"]), key=lambda r: r["package"])
    print("数量:", len(dup))
    for r in dup:
        level = ",".join(r["levelIds"]) or "?"
        print(f"  {level:<24}{r['package']:<10}plants={r['plants']:<3}distinct={r['distinct']:<3}must={r['must']}")

    print("\n== 3b. distinct < must 的关卡（去重格子数不足）==")
    bad = [r for r in rows if isinstance(r["must"], int) and r["distinct"] < r["must"]]
    print("数量:", len(bad))
    for r in sorted(bad, key=lambda r: (r["levelIds"] or ["?"])[0]):
        level = ",".join(r["levelIds"]) or "?"
        print(f"  {level:<18}{r['package']:<10}plants={r['plants']:<3}distinct={r['distinct']:<3}must={r['must']:<3}"
              f"clamp后={min(r['must'], r['distinct'])}")


def section_placement(rows: list[dict]) -> None:
    print("\n== 3c. 按引擎放置顺序模拟（initialPlants 先占格，再放 protect）==")
    levels = json.loads(MECHANICS.read_text(encoding="utf-8"))["levels"]
    inert = []
    tight = []
    for level_id, entry in sorted(levels.items()):
        prot = entry.get("protectThePlant")
        if not prot:
            continue
        must = prot.get("mustProtectCount")
        occupied: dict[tuple, str] = {}
        for placement in (entry.get("initialPlants") or {}).get("placements") or []:
            cell = (placement.get("gridY"), placement.get("gridX"))
            occupied.setdefault(cell, f"{placement.get('plant')}(L{placement.get('level')})")
        placed = 0
        blocked: list[tuple[str, str]] = []
        for plant in prot.get("plants") or []:
            cell = (plant.get("gridY"), plant.get("gridX"))
            if cell in occupied:
                blocked.append((str(plant.get("plant")), occupied[cell]))
                continue
            placed += 1
            occupied[cell] = f"{plant.get('plant')}(protect)"
        if isinstance(must, int) and placed < must:
            row = (level_id, len(prot.get("plants") or []), placed, must, blocked)
            (inert if placed == 0 else tight).append(row)
    print("placed == 0（保护机制静默失效）:", len(inert))
    for level_id, total, placed, must, blocked in inert:
        print(f"  {level_id:<20}plants={total:<3}placed=0 must={must}")
        for target, occupant in blocked:
            print(f"      目标 {target:<18} 被先占格者 {occupant} 挡住")
    print("0 < placed < must（阈值零容错）:", len(tight))
    for level_id, total, placed, must, blocked in tight:
        print(f"  {level_id:<20}plants={total:<3}placed={placed:<3}must={must}")
        for target, occupant in blocked:
            print(f"      目标 {target:<18} 被先占格者 {occupant} 挡住")


def section_compiled(rows: list[dict]) -> None:
    print("\n== 4. 原版 vs level_mechanics.json ==")
    levels = json.loads(MECHANICS.read_text(encoding="utf-8"))["levels"]
    with_protect = {lid for lid, entry in levels.items() if entry.get("protectThePlant")}
    print("编译产物里有 protectThePlant 的关卡:", len(with_protect), "| 原版模块数:", len(rows))
    by_pkg: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_pkg[row["package"]].append(row)
    diffs = []
    for package, entries in sorted(by_pkg.items()):
        ids = entries[0]["levelIds"]
        for level_id in ids:
            prot = (levels.get(level_id) or {}).get("protectThePlant")
            if not prot:
                diffs.append((level_id, package, "编译缺少该模块"))
                continue
            chosen = [e for e in entries if e["alias"] == prot.get("alias")]
            if not chosen:
                diffs.append((level_id, package, f"别名不符 compiled={prot.get('alias')}"))
                continue
            entry = chosen[0]
            compiled_cells = [(p.get("gridX"), p.get("gridY")) for p in prot.get("plants") or []]
            if len(compiled_cells) != entry["plants"]:
                diffs.append((level_id, package, f"条目数 {entry['plants']} -> {len(compiled_cells)}"))
            if entry["must"] != prot.get("mustProtectCount"):
                diffs.append((level_id, package, f"must {entry['must']} -> {prot.get('mustProtectCount')}"))
    print("差异条数:", len(diffs))
    for row in diffs:
        print("  ", row)
    dropped = [
        (entry["package"], entry["alias"], entry["plants"], entry["levelIds"])
        for entry in rows
        if len(by_pkg[entry["package"]]) > 1
        and any(
            (levels.get(lid) or {}).get("protectThePlant", {}) is None
            or (levels.get(lid) or {}).get("protectThePlant", {}).get("alias") != entry["alias"]
            for lid in entry["levelIds"]
        )
    ]
    print("被丢弃的多模块:", dropped)


def section_declared() -> None:
    print("\n== 5. Modules 点名 ProtectThePlant、包里却没有任何 protect 对象 ==")
    ids = level_ids_by_package()
    rows = []
    for path in sorted(OBB.glob("pkg_*_LevelDefinition.json")):
        package = path.name.split("_LevelDefinition")[0]
        doc = load(path)
        objects = [obj for obj in doc.get("objects") or [] if isinstance(obj, dict)]
        names = []
        for obj in objects:
            if obj.get("objclass") == "LevelDefinition":
                names.extend(str(n) for n in (obj.get("objdata") or {}).get("Modules") or [])
        declared = sorted({n for n in names if "ProtectThePlant" in n})
        if not declared:
            continue
        has_object = any(obj.get("objclass") == PROTECT_CLS for obj in objects)
        if not has_object:
            rows.append((package, ",".join(ids.get(package) or ["?"]), declared))
    print("数量:", len(rows))
    for package, level, declared in rows:
        print(f"  {level:<20}{package:<10}{declared}")


def main() -> int:
    section_egypt74()
    rows = scan_modules()
    section_duplicates(rows)
    section_placement(rows)
    section_compiled(rows)
    section_declared()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
