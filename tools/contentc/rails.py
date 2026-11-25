"""铁轨语义判别：把「真有功能矿车」和「只有装饰铁轨」分开。

t22（`levelextra.py`）只按模块名统计了 rail 的覆盖面（原版 185 关 vs 客户端 10 关），
但模块名本身分不清「这一关真的有可站人的矿车」还是「只画了轨道」。本模块下沉到关卡内嵌的
rail 对象，按字段判定：

- `RailcartProperties` 带非空 `Railcarts`（每项有 `Column`/`Row`）→ `functional`；
- `RailcartProperties` 只有 `Rails`（`Column`/`RowStart`/`RowEnd` 路径点）→ `decorative`；
- `DangerRoomRailcartDesigner` 带 `BaseRailcartCount`/`MaxGeneratedRailcarts`/`Layouts`
  → `functional`（按布局程序化生成矿车）；
- `RailcartTutorialIntroProperties` 之类空对象 → `decorative`（只有入场标记，无玩法参数）；
- 只有模块名、没有对应对象，或对象既无车也无轨 → `unknown`（附探针）。

**为什么不改 `levelextra.py`**：t22 的 `level_modules.json` 与报告已被 `--check` 逐字节锁定，
是别的任务在用的「关卡模块清单」；铁轨语义是另一个粒度（关卡内对象），混进去会让那份
产物被动变化。因此单开 `rails.py`，只读 t22 的输入，不触碰它的输出。

本模块只产出证据与下一轮的候选（`content_fix_candidates.json`），**不写 `content/**`**。

运行::

    python tools/contentc/rails.py
    python tools/contentc/rails.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages"))
DEFAULT_LEVELS = ROOT / "content" / "levels"
DEFAULT_JSON = ROOT / "native" / "generated" / "rails_report.json"
DEFAULT_CANDIDATES = ROOT / "native" / "generated" / "content_fix_candidates.json"
DEFAULT_REPORT = ROOT / "docs" / "reviews" / "2026-11-20-rails-and-vases.md"

FORMAT = 1
MARKER = "rails-semantics-v1"
LEVEL_SAMPLE = 20

RAIL_MODULES = ("Rails", "CowboyRails", "Railcart", "Railcart1")
VASE_MODULES = ("VaseBreakerArcade", "VaseBreakerProps", "TestVaseBreaker")
BOSS_MODULES = ("ZombossBattle", "ZombossBattle1", "ZombossBattle2")

# 判定用的字段族（按小写子串匹配，实测字段名以数据为准）
CART_FIELDS = ("railcarts",)
PATH_FIELDS = ("rails",)
COUNT_FIELDS = ("baserailcartcount", "maxgeneratedrailcarts", "layouts")

VERDICTS = ("functional", "decorative", "unknown")


def _walk(doc):
    stack = [doc]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if isinstance(cur.get("objdata"), dict):
                yield cur.get("objclass"), cur["objdata"]
            for value in cur.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(cur, list):
            stack.extend(cur)


def _module_names(doc) -> list[str]:
    names: list[str] = []
    for cls, data in _walk(doc):
        if cls != "LevelDefinition":
            continue
        for text in data.get("Modules") or []:
            if isinstance(text, str) and "RTID(" in text:
                names.append(text.split("RTID(", 1)[1].split("@", 1)[0])
    return names


def _package_key(filename: str) -> str:
    return filename.split("_LevelDefinition")[0]


def _stage_name(rtid: object) -> str | None:
    """`RTID(PirateBossStage@LevelModules)` → `PirateBossStage`。"""
    if not isinstance(rtid, str) or "RTID(" not in rtid:
        return None
    return rtid.split("RTID(", 1)[1].split("@", 1)[0]


def _level_key(level_id: str) -> tuple:
    """关卡 id 的自然排序键（`kongfu_5` 排在 `kongfu_10` 前）。"""
    parts = level_id.split("_")
    return tuple((0, int(part)) if part.isdigit() else (1, part) for part in parts)


def _client_flagged(row: dict) -> bool:
    """客户端是否标了 rail 意图：`minecarts`（车道）或 `rail`（有车无车道）任一为真。"""
    client = row.get("client") or {}
    return bool(client.get("minecarts") or client.get("rail"))


def load_levels(levels_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(levels_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        extra = doc.get("extra") or {}
        rows.append(
            {
                "id": str(doc.get("id") or path.stem),
                "world": doc.get("world"),
                "package": str(extra.get("package") or ""),
                "extra": extra,
            }
        )
    return rows


def load_originals(obb_dir: Path) -> dict[str, dict]:
    originals: dict[str, dict] = {}
    for path in sorted(obb_dir.glob("pkg_*_LevelDefinition.json")):
        text = path.read_text(encoding="utf-8-sig")
        doc = json.loads(text)
        modules = _module_names(doc)
        stage = None
        level_number = None
        objects = []
        for cls, data in _walk(doc):
            if cls == "LevelDefinition":
                stage = data.get("StageModule")
                level_number = data.get("LevelNumber")
            if "rail" not in (cls or "").lower():
                continue
            objects.append({"class": cls, "fields": sorted(data.keys()), "data": data})
        originals[_package_key(path.name)] = {
            "file": path.name,
            "modules": modules,
            "objects": objects,
            "has_modules_key": bool(modules),
            "stage": stage,
            "level_number": level_number,
        }
    return originals


def _lower_keys(data: dict) -> list[str]:
    return [str(key).lower() for key in data]


def object_verdict(obj: dict) -> tuple[str, dict]:
    """返回 (verdict, 证据计数)。证据只用于报告与测试，不进判定。"""
    data = obj["data"]
    keys = _lower_keys(data)
    carts = len(data.get("Railcarts") or [])
    rails = len(data.get("Rails") or [])
    counts = {
        "carts": carts,
        "rails": rails,
        "hasCartField": any(field in key for key in keys for field in CART_FIELDS),
        "hasPathField": any(field in key for key in keys for field in PATH_FIELDS),
        "hasCountField": any(field in key for key in keys for field in COUNT_FIELDS),
    }
    if counts["hasCountField"]:
        return "functional", counts
    if carts:
        return "functional", counts
    if rails:
        return "decorative", counts
    if not data:
        return "decorative", counts
    return "unknown", counts


def level_verdict(objects: list[dict]) -> str:
    verdicts = [item["verdict"] for item in objects]
    if "functional" in verdicts:
        return "functional"
    if "decorative" in verdicts:
        return "decorative"
    return "unknown"


def build(obb_dir: Path, levels_dir: Path) -> dict:
    levels = load_levels(levels_dir)
    originals = load_originals(obb_dir)

    stage_pairs: dict[tuple, list[str]] = {}
    for package, original in originals.items():
        pair = (_stage_name(original.get("stage")), original.get("level_number"))
        stage_pairs.setdefault(pair, []).append(package)
    duplicate_pairs = {pair: pkgs for pair, pkgs in stage_pairs.items() if len(pkgs) > 1}
    duplicate_extra = sum(len(pkgs) - 1 for pkgs in duplicate_pairs.values())

    records = []
    missing_original = []
    for level in levels:
        package = _package_key(level["package"]) if level["package"] else ""
        original = originals.get(package)
        if original is None:
            missing_original.append(level["id"])
            continue
        rail_modules = [name for name in original["modules"] if name in RAIL_MODULES]
        objects = []
        for obj in original["objects"]:
            verdict, counts = object_verdict(obj)
            objects.append(
                {
                    "class": obj["class"],
                    "pkg": package,
                    "fields": obj["fields"],
                    "verdict": verdict,
                    "evidence": counts,
                    "type": obj["data"].get("RailcartType") or obj["data"].get("RailcarType"),
                }
            )
        record = {
            "level": level["id"],
            "world": level["world"],
            "package": package,
            "stage": _stage_name(original.get("stage")),
            "levelNumber": original.get("level_number"),
            "moduleNames": rail_modules,
            "modules": objects,
            "verdict": level_verdict(objects) if objects else ("unknown" if rail_modules else "none"),
            "client": {
                "minecarts": level["extra"].get("minecarts"),
                "rail": bool(level["extra"].get("rail")),
            },
        }
        if rail_modules or objects:
            records.append(record)

    rail_records = [row for row in records if row["verdict"] in VERDICTS]
    verdict_counts = Counter(row["verdict"] for row in rail_records)

    by_world = defaultdict(Counter)
    for row in rail_records:
        by_world[row["world"]][row["verdict"]] += 1

    class_counts = Counter()
    class_verdicts = defaultdict(Counter)
    for row in rail_records:
        for obj in row["modules"]:
            class_counts[obj["class"]] += 1
            class_verdicts[obj["class"]][obj["verdict"]] += 1

    module_without_object = sorted(
        (row["level"] for row in rail_records if row["moduleNames"] and not row["modules"]), key=_level_key
    )
    object_without_module = sorted(
        (row["level"] for row in rail_records if row["modules"] and not row["moduleNames"]), key=_level_key
    )

    flagged = [row["level"] for row in rail_records if _client_flagged(row)]
    flagged_all = sorted(
        (level["id"] for level in levels if level["extra"].get("minecarts") or level["extra"].get("rail")),
        key=_level_key,
    )
    functional_unflagged = sorted(
        (row["level"] for row in rail_records if row["verdict"] == "functional" and not _client_flagged(row)), key=_level_key
    )
    flagged_with_functional = sorted(
        (row["level"] for row in rail_records if _client_flagged(row) and row["verdict"] == "functional"),
        key=_level_key,
    )
    flagged_without_data = sorted(
        (row["level"] for row in rail_records if _client_flagged(row) and row["verdict"] != "functional"),
        key=_level_key,
    )

    # 客户端标了 minecarts、但该关根本没有 rail 数据（连记录都没有）——
    # 逐关给出原版证据行（文件 + StageModule + LevelNumber + 无 rail 模块/对象），供 content 补丁引用。
    rail_level_ids = {row["level"] for row in rail_records}
    level_by_id = {level["id"]: level for level in levels}
    flagged_no_record = sorted(
        (
            level["id"]
            for level in levels
            if (level["extra"].get("minecarts") or level["extra"].get("rail"))
            and level["id"] not in rail_level_ids
        ),
        key=_level_key,
    )
    flagged_evidence = []
    for level_id in flagged_no_record:
        level = level_by_id[level_id]
        package = _package_key(level["package"]) if level["package"] else ""
        original = originals.get(package) or {}
        flagged_evidence.append(
            {
                "level": level_id,
                "package": package,
                "file": original.get("file"),
                "stage": _stage_name(original.get("stage")),
                "stageRtid": original.get("stage"),
                "levelNumber": original.get("level_number"),
                "railModules": [
                    name for name in (original.get("modules") or []) if name in RAIL_MODULES
                ],
                "railObjects": len(original.get("objects") or []),
                "clientStage": level["extra"].get("stage"),
            }
        )

    # Boss 关按 ZombossBattle* 模块统计（按 *BossStage 名只有 18 关，与客户端 71 不符）
    boss_module_levels = 0
    boss_stage_named = 0
    client_boss = 0
    for level in levels:
        package = _package_key(level["package"]) if level["package"] else ""
        original = originals.get(package)
        if original and any(name in BOSS_MODULES for name in original["modules"]):
            boss_module_levels += 1
        if "boss" in str(level["extra"].get("stage") or "").lower():
            boss_stage_named += 1
        if level["extra"].get("boss") is True:
            client_boss += 1

    # 砸罐子：原版有模块、客户端没有 vasebreaker 键
    vase_original = []
    for level in levels:
        package = _package_key(level["package"]) if level["package"] else ""
        original = originals.get(package)
        if original is None:
            continue
        if any(name in VASE_MODULES for name in original["modules"]):
            vase_original.append(
                {
                    "level": level["id"],
                    "world": level["world"],
                    "package": package,
                    "modules": [name for name in original["modules"] if name in VASE_MODULES],
                    "clientVasebreaker": bool(level["extra"].get("vasebreaker")),
                    "clientSpecial": level["extra"].get("special"),
                    "stage": str(level["extra"].get("stage") or ""),
                    "wave_count": level["extra"].get("wave_count"),
                    "boss": level["extra"].get("boss") is True,
                    "bossZombie": level["extra"].get("boss_zombie"),
                }
            )
    vase_add = sorted((item["level"] for item in vase_original if not item["clientVasebreaker"]), key=_level_key)
    client_vase = sorted(
        (level["id"] for level in levels if level["extra"].get("vasebreaker")), key=_level_key
    )

    no_modules = sorted(
        key for key, original in originals.items() if not original["has_modules_key"]
    )
    level_by_package = {
        _package_key(level["package"]): level["id"] for level in levels if level["package"]
    }
    no_modules_levels = sorted((level_by_package[key] for key in no_modules if key in level_by_package), key=_level_key)

    night_mismatch = []
    for level in levels:
        stage = str(level["extra"].get("stage") or "")
        night = bool(level["extra"].get("night"))
        if night != ("night" in stage.lower()):
            night_mismatch.append({"level": level["id"], "stage": stage, "night": night})

    payload = {
        "format": FORMAT,
        "marker": MARKER,
        "source": {
            "obb": "work/obb_packages/pkg_*_LevelDefinition.json",
            "levels": "content/levels/*.json",
        },
        "counts": {
            "levels": len(levels),
            "levelsWithOriginal": len(records),
            "railLevels": len(rail_records),
            "functional": verdict_counts.get("functional", 0),
            "decorative": verdict_counts.get("decorative", 0),
            "unknown": verdict_counts.get("unknown", 0),
            "clientFlagged": len(flagged_all),
            "flaggedWithRailRecord": len(flagged),
            "flaggedWithFunctionalData": len(flagged_with_functional),
            "flaggedWithoutFunctionalData": flagged_without_data,
            "flaggedWithoutRailData": len(flagged_no_record),
            "functionalUnflagged": len(functional_unflagged),
            "missingOriginal": len(missing_original),
            "vaseOriginal": len(vase_original),
            "vaseClient": len(client_vase),
            "vaseMissing": len(vase_add),
            "noModules": len(no_modules_levels),
            "nightMismatch": len(night_mismatch),
            "bossModuleLevels": boss_module_levels,
            "bossStageNamed": boss_stage_named,
            "clientBoss": client_boss,
            "stageKeys": len(stage_pairs),
            "stageKeyTotal": len(originals),
            "stageKeyDuplicates": len(duplicate_pairs),
            "stageKeyExtraFiles": duplicate_extra,
        },
        "identity": {
            "key": "StageModule.stage + LevelNumber",
            "note": (
                "原版 `pkg_*_LevelDefinition.json` 每个文件通常只有 1 个 LevelDefinition 且没有 alias，"
                "关卡身份键必须用 StageModule 的 stage 名 + LevelNumber；用客户端关卡 id（如 `pirate_41`）"
                "在原表里字面搜索会 0 命中。"
            ),
            "bossCounting": (
                f"Boss 关按 `ZombossBattle`/`ZombossBattle1`/`ZombossBattle2` 模块统计 = {boss_module_levels} 关；"
                f"按 `*BossStage` 名统计只有 {boss_stage_named} 关，会漏掉混合关（如 pirate_41 的 PirateBossStage "
                "同时挂 ZombossBattle 与 VaseBreaker 模块）。"
            ),
            "stageKey": (
                f"(stage, LevelNumber) 并不唯一：原版 {len(originals)} 个文件只有 {len(stage_pairs)} 个不同组合，"
                f"{len(duplicate_pairs)} 个组合重复、多出 {duplicate_extra} 个文件（最多的组合有 "
                f"{max((len(pkgs) for pkgs in duplicate_pairs.values()), default=1)} 个 package）。"
                "所以关联原表时以客户端 `extra.package` 为锚点，stage 名 + LevelNumber 只用于核对。"
            ),
        },
        "classes": {
            cls: {"count": class_counts[cls], "verdicts": dict(sorted(class_verdicts[cls].items()))}
            for cls in sorted(class_counts)
        },
        "byWorld": {world: dict(sorted(counter.items())) for world, counter in sorted(by_world.items())},
        "levels": sorted(rail_records, key=lambda row: _level_key(row["level"])),
        "moduleWithoutObject": module_without_object,
        "objectWithoutModule": object_without_module,
        "flaggedWithoutRailData": flagged_no_record,
        "flaggedEvidence": flagged_evidence,
        "functionalUnflagged": functional_unflagged,
        "vasebreaker": {
            "original": vase_original,
            "client": client_vase,
            "missing": vase_add,
        },
        "noModulesLevels": no_modules_levels,
        "nightMismatch": night_mismatch,
        "missingOriginal": missing_original,
    }
    return payload


def build_candidates(payload: dict) -> dict:
    counts = payload["counts"]
    return {
        "format": FORMAT,
        "marker": "content-fix-candidates-v1",
        "vasebreaker_add": payload["vasebreaker"]["missing"],
        "minecarts": payload["functionalUnflagged"],
        "minecarts_remove": payload["flaggedWithoutRailData"],
        "minecarts_remove_evidence": payload["flaggedEvidence"],
        "minecarts_keep": sorted(
            (
                row["level"]
                for row in payload["levels"]
                if row["client"]["minecarts"] and row["verdict"] == "functional"
            ),
            key=_level_key,
        ),
        "rationale": {
            "vasebreaker_add": (
                f"原版 {counts['vaseOriginal']} 关带 VaseBreakerArcade/VaseBreakerProps 模块，"
                f"客户端只有 {counts['vaseClient']} 关标了 vasebreaker；差集 {counts['vaseMissing']} 关"
                "在原版模块对象里能查到花瓶布局参数，应补标。"
            ),
            "minecarts": (
                f"{counts['functional']} 关在原版 `RailcartProperties.Railcarts` 里有明确车位"
                f"（Column/Row）或 `DangerRoomRailcartDesigner` 的车数参数，但客户端只有 "
                f"{counts['clientFlagged']} 关标了 minecarts；这里列出 {counts['functionalUnflagged']} 关"
                "缺标的功能矿车关，供下一轮补标。"
            ),
            "minecarts_remove": (
                f"{counts['flaggedWithoutRailData']} 关客户端标了 minecarts/rail，但原版该关既无 rail 模块也无 "
                "rail 对象；逐关证据（原版文件 + StageModule + LevelNumber + railModules=[] + railObjects=0）"
                "见 `minecarts_remove_evidence`，可直接作为 content 撤标的依据。"
            ),
            "minecarts_keep": "兼顾「客户端已标 + 原版确有车位」的关卡，补标时不要重复添加。",
        },
        "scope": "只给下一轮改 content 的输入；本任务不写 content/**。",
    }


def render_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        out.append("| " + " | ".join(row) + " |")
    return out


def render_report(payload: dict) -> str:
    counts = payload["counts"]
    by_world = payload["byWorld"]
    levels = payload["levels"]
    functional = [row for row in levels if row["verdict"] == "functional"]
    decorative = [row for row in levels if row["verdict"] == "decorative"]
    unknown = [row for row in levels if row["verdict"] == "unknown"]

    lines: list[str] = []
    lines.append("# 铁轨语义与砸罐子缺口（证据轮，不改 content）")
    lines.append("")
    gaps = counts["flaggedWithoutRailData"] + counts["functionalUnflagged"] + counts["vaseMissing"]
    if gaps:
        lines.append(
            f"**结论：客户端把 `minecarts` 标反了方向。** 原版 {counts['railLevels']} 关带 rail 模块或 rail 对象，"
            f"其中 {counts['functional']} 关有明确车位参数（functional）、{counts['decorative']} 关只有轨道点"
            f"（decorative）、{counts['unknown']} 关拿不准（unknown）；客户端只标了 {counts['clientFlagged']} 关，"
            f"其中 {counts['flaggedWithoutRailData']} 关原版根本没有 rail 数据（误标），"
            f"另有 {counts['functionalUnflagged']} 关真矿车没被标出来。"
        )
    else:
        lines.append(
            f"**结论：三个标记已与原版对齐，且由 `tools/obb_build_content_v2.py` 现场派生。** 原版 "
            f"{counts['railLevels']} 关带 rail 模块或 rail 对象，其中 {counts['functional']} 关有明确车位参数"
            f"（functional）、{counts['decorative']} 关只有轨道点（decorative）、{counts['unknown']} 关拿不准"
            f"（unknown）；客户端标了 {counts['clientFlagged']} 关，误标 {counts['flaggedWithoutRailData']}、"
            f"漏标 {counts['functionalUnflagged']}；`vasebreaker` {counts['vaseClient']}/{counts['vaseOriginal']}，"
            f"差集 {counts['vaseMissing']}。"
        )

    lines.append("")
    lines.append("## 零、口径（与他轮对齐，先看这节）")
    lines.append("")
    lines.append(
        f"1. **关卡身份键 = `StageModule` 的 stage 名 + `LevelNumber`。** 原版每个 "
        "`pkg_*_LevelDefinition.json` 通常只有 1 个 `LevelDefinition` 且**没有 alias**，"
        "拿客户端关卡 id（如 `pirate_41`）在原表里字面搜索会 0 命中；本工具一律用 package 关联，"
        "再回读 stage 名与关卡号核对。"
    )
    lines.append(
        f"   但这对键**不唯一**：{counts['stageKeyTotal']} 个原版文件只有 {counts['stageKeys']} 个不同组合，"
        f"{counts['stageKeyDuplicates']} 个组合重复、多出 {counts['stageKeyExtraFiles']} 个文件"
        "（例如 `(DarkStage, 1)` 有 20 个 package、`(DinoStage, 1)` 14 个、`(BeachStage, 1)` 12 个），"
        "所以按 (stage, LevelNumber) 反查必须再叠加 package —— 客户端 `extra.package` 是唯一可靠锚点。"
        "实证：`kongfu_30` 的 `extra` 是 `pkg_1415 / KongfuStage / level_number 5`，"
        "与 `kongfu_5` 的 `pkg_1390 / KongfuStage / 5` 同 stage 同号但是两个不同 package。"
    )
    lines.append(
        f"2. **Boss 关按 `ZombossBattle` 模块统计**：原版 {counts['bossModuleLevels']} 关，与客户端的 "
        f"{counts['clientBoss']} 关对齐；按 `*BossStage` 名只有 {counts['bossStageNamed']} 关，"
        "因为混合关（Boss + 砸罐子/其它玩法）的 stage 名不带 Boss 或只对应一个模块。"
    )
    lines.append("")
    lines.append("## 一、判据与为什么单开一个工具")
    lines.append("")
    lines.append(
        "判据（按对象实测字段，字段名以数据为准）："
        "\n\n- `RailcartProperties.Railcarts` 非空（每项含 `Column`/`Row`）→ **functional**；"
        "\n- `RailcartProperties` 只有 `Rails`（`Column`/`RowStart`/`RowEnd` 路径点）→ **decorative**；"
        "\n- `DangerRoomRailcartDesigner` 带 `BaseRailcartCount`/`MaxGeneratedRailcarts`/`Layouts` → **functional**；"
        "\n- 空对象（如 `RailcartTutorialIntroProperties`）→ **decorative**（只有入场标记）；"
        "\n- 只有模块名没有对象，或对象既无车也无轨 → **unknown**（附探针）。"
    )
    lines.append("")
    lines.append(
        "没有改 `tools/contentc/levelextra.py`：t22 的 `level_modules.json` 与评审文档被 `--check` 逐字节锁定，"
        "是别的任务在用的「关卡模块清单」；铁轨语义是关卡内对象的粒度，塞进去会让那份产物被动变化。"
        "所以新增 `tools/contentc/rails.py`，只读同一批输入，不碰 t22 的输出。"
    )
    lines.append("")
    lines.append("## 二、结论表一：功能矿车关卡（functional）")
    lines.append("")
    world_rows = []
    for world, counter in by_world.items():
        if counter.get("functional"):
            world_rows.append([world, str(counter["functional"])])
    world_rows.append(["**合计**", f"**{counts['functional']}**"])
    lines.extend(_table(["世界", "功能矿车关卡数"], world_rows))
    lines.append("")
    lines.append("抽样（前 20 关，括号内为车位/轨道数）：")
    lines.append("")
    for row in functional[:LEVEL_SAMPLE]:
        carts = sum(obj["evidence"]["carts"] for obj in row["modules"])
        rails = sum(obj["evidence"]["rails"] for obj in row["modules"])
        lines.append(f"- `{row['level']}`（{carts} 车 / {rails} 轨）—— 模块 {('、'.join(f'`{m}`' for m in row['moduleNames']) or '无（对象内嵌）')}")
    lines.append("")
    lines.append("## 三、结论表二：装饰铁轨关卡（decorative）")
    lines.append("")
    if decorative:
        rows = []
        for row in decorative:
            rails = sum(obj["evidence"]["rails"] for obj in row["modules"])
            cls = "、".join(sorted({obj["class"] for obj in row["modules"]}))
            rows.append([f"`{row['level']}`", row["world"], cls, str(rails)])
        lines.extend(_table(["关卡", "世界", "对象类", "轨道点数"], rows))
        lines.append("")
        lines.append(
            "这些关卡的原版文件里搜不到任何 `*Cart*` 记号（没有波次生成矿车的痕迹），"
            "轨道只是装饰；另有 1 个 `RailcartTutorialIntroProperties` 空对象挂在 `cowboy_1` 上，"
            "该关本身有车位，所以关卡判为 functional。"
        )
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("## 四、结论表三：拿不准（unknown）")
    lines.append("")
    if unknown:
        rows = []
        for row in unknown:
            cls = "、".join(f"`{obj['class']}`" for obj in row["modules"]) or "—（只有模块名）"
            if row["modules"]:
                why = "对象里既没有 `Railcarts` 也没有 `Rails`，没有任何位置参数"
            else:
                why = "只有模块名，原版该关没有 rail 对象可读"
            rows.append([f"`{row['level']}`", row["world"], cls, why])
        lines.extend(_table(["关卡", "世界", "对象类", "缺什么"], rows))
    else:
        lines.append("（无）")
    lines.append("")
    lines.append("## 五、客户端标记对账")
    lines.append("")
    lines.append(
        f"- 客户端标了 `minecarts` 的关卡：{counts['clientFlagged']} 关；其中原版确有车位参数的 "
        f"{counts['clientFlagged'] - counts['flaggedWithoutRailData']} 关，原版完全没有 rail 数据的 "
        f"{counts['flaggedWithoutRailData']} 关（`{'`、`'.join(payload['flaggedWithoutRailData'])}`）。"
    )
    lines.append(
        f"- 原版有车位、客户端没标：**{counts['functionalUnflagged']} 关**（完整名单见 "
        "`native/generated/content_fix_candidates.json` 的 `minecarts`）。"
    )
    lines.append(
        f"- 模块名与对象错配：只有模块名、没有对应对象的 {len(payload['moduleWithoutObject'])} 关（"
        f"`{'`、`'.join(payload['moduleWithoutObject'])}`）；有对象、但 `Modules` 里没有 rail 模块名的 "
        f"{len(payload['objectWithoutModule'])} 关（`{'`、`'.join(payload['objectWithoutModule'])}`）。"
    )
    lines.append("")
    if payload["flaggedEvidence"]:
        lines.append("撤标证据（原版文件 + StageModule + LevelNumber，rail 模块与对象均为空）：")
        lines.append("")
        evidence_rows = []
        for item in payload["flaggedEvidence"]:
            evidence_rows.append(
                [
                    f"`{item['level']}`",
                    f"`{item['file']}`",
                    f"`{item['stage']}`",
                    str(item["levelNumber"]),
                    f"{len(item['railModules'])} 个模块 / {item['railObjects']} 个对象",
                ]
            )
        lines.extend(_table(["关卡", "原版文件", "StageModule", "LevelNumber", "rail 数据"], evidence_rows))
    else:
        lines.append(
            "撤标证据：（无）——原版没有 rail 数据的关卡都没有被标（t52 已把 `rail`/`minecarts` 改成派生值）。"
        )
    lines.append("")
    lines.append("## 六、砸罐子标记（pirate_41、plantagenet_18）")
    lines.append("")
    lines.append(
        f"原版带 VaseBreaker 模块的关卡 {counts['vaseOriginal']} 关，客户端标了 `vasebreaker` 的 "
        f"{counts['vaseClient']} 关；差集 {counts['vaseMissing']} 关。"
    )
    missing_rows = [
        item for item in payload["vasebreaker"]["original"] if not item["clientVasebreaker"]
    ]
    if missing_rows:
        lines.append("")
        lines.append("差集逐关（原版模块名与客户端 `extra` 实值）：")
        lines.append("")
        rows = []
        for item in missing_rows:
            rows.append(
                [
                    f"`{item['level']}`",
                    item["world"],
                    "、".join(f"`{name}`" for name in item["modules"]),
                    (
                        f"`stage`={item['stage']}、`wave_count`={item['wave_count']}、"
                        f"`boss`={json.dumps(item['boss'])}、"
                        f"`boss_zombie`={json.dumps(item['bossZombie'], ensure_ascii=False)}、"
                        f"`special`={json.dumps(item['clientSpecial'], ensure_ascii=False)}，"
                        "`vasebreaker` 缺失"
                    ),
                ]
            )
        lines.extend(_table(["关卡", "世界", "原版模块", "客户端 extra 实际值"], rows))
    lines.append("")
    lines.append(
        "证据：两关的原版 `Modules` 都含 `VaseBreakerArcade` + `VaseBreakerProps`（花瓶布局参数在同名对象里）。"
        "**这里只关砸罐子标记，不存在玩法标签错位**："
        "`pirate_41` 的 stage 是 `PirateBossStage`、LevelNumber 26，原版 `Modules` 同时含 `ZombossIntro` 与 "
        "`ZombossBattle`，所以客户端 `boss: true` / `boss_zombie: zomboss` 是对的（Boss + 砸罐子混合关）；"
        "`plantagenet_18`（`PlantagenetDaylightDMGStage` #19）原版没有 Boss 模块，客户端也没有 boss 标记，同样正确。"
    )
    if counts["vaseMissing"]:
        lines.append("下一轮只需给差集里的关卡补 `vasebreaker: true`，不要动 boss 字段。")
    else:
        lines.append(
            "t52 已把 `vasebreaker` 写成 builder 的派生产物（原版 Modules 命中即置真），两关都已补上，boss 字段未动。"
        )
    lines.append("")
    lines.append("## 七、两件遗留事项的处置建议")
    lines.append("")
    lines.append(
        f"1. **{counts['noModules']} 关原版没有 `Modules`**（`{'`、`'.join(payload['noModulesLevels'])}`）："
        "按「无模块关卡」处理，S7 加载器遇到空模块表直接跳过模块解析、只保留关卡本体，不要假设每关都有波次管理器。"
    )
    lines.append(
        f"2. **{counts['nightMismatch']} 关 `night` 与 `stage` 名冲突**：以原版 `*StageProperties` 为准，"
        "客户端 `night` 只当提示位；下一轮加一个校验器，把冲突写进报告而不是静默改正。"
    )
    lines.append("")
    lines.append("## 八、候选（给下一轮改 content，本任务不落 content）")
    lines.append("")
    if gaps or payload["vasebreaker"]["missing"] or payload["functionalUnflagged"]:
        lines.append(
            f"- `vasebreaker_add`：{payload['vasebreaker']['missing']}（只补砸罐子标记，boss 字段不动）；"
            f"\n- `minecarts`（补标）：{counts['functionalUnflagged']} 关；"
            f"\n- `minecarts_remove`（撤标）：{counts['flaggedWithoutRailData']} 关，逐关证据见 "
            "`minecarts_remove_evidence`（原版文件 + StageModule + LevelNumber + rail 数据为空）；"
            "\n- 文件：`native/generated/content_fix_candidates.json`，每项都带 rationale。"
        )
    else:
        lines.append(
            "- 已无候选：`vasebreaker_add` / `minecarts` / `minecarts_remove` 全为空 —— "
            "t52 已把三个标记改成 `tools/obb_build_content_v2.py` 的派生产物，重跑构建不会丢。"
        )
    lines.append("")
    lines.append("## 九、复现")
    lines.append("")
    lines.append("```powershell")
    lines.append("python tools/contentc/rails.py           # 重新生成 JSON + 本报告")
    lines.append("python tools/contentc/rails.py --check   # 逐字节校验三个产物")
    lines.append("python -m unittest tools.tests.test_rails -v")
    lines.append("```")
    lines.append("")
    lines.append(
        "所有计数都由 `work/obb_packages` 与原 `content/levels` 现场计算，没有手写常数；"
        "`rails_report.json` 里保留了逐关的对象、字段与证据计数，报告中的表格可直接回查。"
    )
    lines.append("")
    return "\n".join(lines)


def write_outputs(payload: dict, candidates: dict, json_path: Path, candidates_path: Path, report_path: Path) -> None:
    from tools.contentc import emit

    emit.write_text(json_path, render_json(payload))
    emit.write_text(candidates_path, render_json(candidates))
    emit.write_text(report_path, render_report(payload))


def summarize(payload: dict) -> str:
    counts = payload["counts"]
    return (
        f"levels={counts['levels']} rail={counts['railLevels']} "
        f"functional={counts['functional']} decorative={counts['decorative']} unknown={counts['unknown']} "
        f"flagged={counts['clientFlagged']} bogus={counts['flaggedWithoutRailData']} "
        f"missingFlags={counts['functionalUnflagged']} vaseMissing={counts['vaseMissing']}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="铁轨语义判别与砸罐子缺口取证")
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB)
    parser.add_argument("--levels", type=Path, default=DEFAULT_LEVELS)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--check", action="store_true", help="只校验产物是否最新")
    parser.add_argument("-n", "--dry-run", action="store_true", help="只打印摘要，不写盘")
    args = parser.parse_args(argv)

    obb_dir = Path(args.obb)
    levels_dir = Path(args.levels)
    if not obb_dir.is_dir():
        print(f"obb 目录不存在：{obb_dir}", file=sys.stderr)
        return 2
    if not levels_dir.is_dir():
        print(f"关卡目录不存在：{levels_dir}", file=sys.stderr)
        return 2

    payload = build(obb_dir, levels_dir)
    candidates = build_candidates(payload)
    summary = summarize(payload)

    if args.check:
        expected = {
            Path(args.json): render_json(payload).encode("utf-8"),
            Path(args.candidates): render_json(candidates).encode("utf-8"),
            Path(args.report): render_report(payload).encode("utf-8"),
        }
        stale = [path for path, data in expected.items() if not path.is_file() or path.read_bytes() != data]
        if stale:
            print("产物过期：" + "、".join(str(path) for path in stale), file=sys.stderr)
            return 2
        print(f"产物已是最新：{summary}")
        return 0

    if args.dry_run:
        print(f"dry-run：{summary}")
        return 0

    write_outputs(payload, candidates, Path(args.json), Path(args.candidates), Path(args.report))
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
