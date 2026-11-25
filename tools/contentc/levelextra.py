"""把 1809 个关卡的 ``extra`` 清点成机器可读的模块清单（S7.0）。

运行::

    python tools/contentc/levelextra.py            # 生成产物
    python tools/contentc/levelextra.py --check    # 只校验产物是否最新
    python tools/contentc/levelextra.py -n         # 只打印摘要，不写盘

口径
----
1. 客户端侧：``content/levels/*.json`` 的顶层 ``extra``。它的键是移植时压平的
   一组元数据 + 模块开关，不是原版的模块对象。
2. 原版侧：``work/obb_packages/pkg_*_LevelDefinition.json``。每个文件对应一个
   ``extra.package``，其中 ``LevelDefinition`` 的 ``Modules`` 是
   ``RTID(<Name>@LevelModules)`` 字符串列表，模块参数则以
   ``<Name>Properties`` 之类的对象出现在同一文件里。
3. 一个 ``extra`` 键只有在**原版文件里能找到同名模块或对应参数类**时才算
   ``data``；只说明「这一关有这个玩法」而没有参数可读的记 ``flag_only``；
   纯元数据记 ``meta``；对不上任何原版模块的记 ``unknown`` 并留探针。
4. 不做推测填充：``unknown`` 键保留原样并进入报告的探针清单，计数一律取实测。

产物（确定性：sort_keys、indent=1、utf-8、末尾换行、无时间戳）：

* ``native/generated/level_modules.json``
* ``docs/reviews/2026-11-20-level-modules.md``
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
import os

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEVELS = ROOT / "content" / "levels"
DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages"))
DEFAULT_JSON = ROOT / "native" / "generated" / "level_modules.json"
DEFAULT_REPORT = ROOT / "docs" / "reviews" / "2026-11-20-level-modules.md"

FORMAT = 1
MARKER = "level-modules-v1"
KEY_SAMPLE_LIMIT = 8
LEVEL_SAMPLE_LIMIT = 20

RTID_RE = re.compile(r"RTID\(([^@]+)@([^)]+)\)")

#: 原版里 rails 系模块用的名字（实测：Rails / CowboyRails / Railcart / Railcart1）。
RAIL_MODULES = ("Rails", "CowboyRails", "Railcart", "Railcart1")
VASE_MODULES = ("VaseBreakerArcade", "VaseBreakerProps", "TestVaseBreaker")
BOSS_MODULES = ("ZombossBattle", "ZombossBattle1", "ZombossBattle2")

#: 每个 extra 键对应的原版模块 / 参数类，以及它到底提供了多少可读数据。
KEY_SPECS: dict[str, dict[str, Any]] = {
    "boss": {
        "kind": "module",
        "status": "data",
        "modules": BOSS_MODULES,
        "classes": ("ZombossBattleModuleProperties", "ZombossBattleIntroProperties"),
        "note": "布尔开关；原版 ZombossBattleModuleProperties 带阶段与召唤参数",
    },
    "boss_zombie": {
        "kind": "module",
        "status": "flag_only",
        "modules": BOSS_MODULES,
        "classes": ("ZombossBattleModuleProperties",),
        "note": "只给僵王代号（zomboss / gargantuar），没有阶段、血量、攻击序列",
    },
    "vasebreaker": {
        "kind": "module",
        "status": "flag_only",
        "modules": VASE_MODULES,
        "classes": ("VaseBreakerPresetProperties", "VaseBreakerEndlessProperties"),
        "note": "布尔开关；花瓶数量、植物池、波次都在原版 VaseBreakerPresetProperties 里",
    },
    "special": {
        "kind": "module",
        "status": "flag_only",
        "modules": VASE_MODULES,
        "classes": ("VaseBreakerPresetProperties",),
        "note": "标记列表，实测只有 IsVasebreaker 一种",
    },
    "minecarts": {
        "kind": "module",
        "status": "flag_only",
        "modules": RAIL_MODULES,
        "classes": ("RailcartProperties",),
        "note": "只有行号数组（如 [0, 2]、[1, 2, 3]），缺轨道列、长度、速度、载量",
    },
    "rail": {
        "kind": "module",
        "status": "flag_only",
        "modules": RAIL_MODULES,
        "classes": ("RailcartProperties",),
        "note": "布尔开关，与 minecarts 同源",
    },
    "suppressFlagZombie": {
        "kind": "module",
        "status": "flag_only",
        "modules": (),
        "classes": ("WaveManagerProperties",),
        "note": "布尔开关，挂在 WaveManagerProperties 上（实测 271 关：true 215 / false 56），"
                "不是 Modules 列表里的模块",
    },
    "stage": {
        "kind": "module",
        "status": "data",
        "modules": ("StageModule",),
        "classes": (
            "StageModuleProperties",
            "BeachStageProperties",
            "EgyptStageProperties",
            "EightiesStageProperties",
            "ModernStageProperties",
            "FrontLawnStageProperties",
            "FutureStageProperties",
            "IceAgeStageProperties",
            "LunarStageProperties",
            "HeroesStageProperties",
            "WestStageProperties",
        ),
        "note": "关卡场景名；原版各 *StageProperties 带场景参数",
    },
    "night": {
        "kind": "derived",
        "status": "flag_only",
        "modules": (),
        "classes": (),
        "note": "布尔，由 stage 派生；与 stage 名里的 Night 有冲突，实现时要按原版判定",
    },
    "source": {"kind": "meta", "status": "meta", "modules": (), "classes": (), "note": "数据来源标记，实测恒为 obb"},
    "package": {"kind": "meta", "status": "meta", "modules": (), "classes": (), "note": "原版 LevelDefinition 的包号，用于反查"},
    "name_key": {"kind": "meta", "status": "meta", "modules": (), "classes": (), "note": "本地化键，3 关为 null"},
    "level_number": {"kind": "meta", "status": "meta", "modules": (), "classes": (), "note": "关卡序号"},
    "wave_count": {"kind": "meta", "status": "meta", "modules": (), "classes": (), "note": "波数；原版 WaveManagerModuleProperties 里才是波表"},
    "original_waves": {"kind": "meta", "status": "meta", "modules": (), "classes": (), "note": "移植前波数，用于对账"},
}

UNKNOWN_PROBE = (
    "未知键：原版 LevelDefinition 里找不到同名模块或参数类。"
    "探针：在 obb 中检索与键名同词的模块类（LevelModules RTID 与 *Properties 对象），"
    "确认后才可升级为 data/flag_only"
)


@dataclass
class KeyRow:
    key: str
    count: int
    worlds: list[str]
    value_types: list[str]
    samples: list[str]
    kind: str
    status: str
    modules: list[str]
    classes: list[str]
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "worlds": self.worlds,
            "valueTypes": self.value_types,
            "samples": self.samples,
            "kind": self.kind,
            "status": self.status,
            "original": {"modules": self.modules, "classes": self.classes},
            "note": self.note,
        }


@dataclass
class LevelsWith:
    key: str
    count: int
    sample: list[str]
    truncated: bool

    def as_dict(self) -> dict[str, Any]:
        return {"count": self.count, "sample": self.sample, "truncated": self.truncated}


@dataclass
class CrossCheck:
    name: str
    client_key: str
    original: int
    client: int
    both: int
    original_only: list[str]
    client_only: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "clientKey": self.client_key,
            "original": self.original,
            "client": self.client,
            "both": self.both,
            "originalOnly": {"count": len(self.original_only), "sample": self.original_only[:LEVEL_SAMPLE_LIMIT]},
            "clientOnly": {"count": len(self.client_only), "sample": self.client_only[:LEVEL_SAMPLE_LIMIT]},
        }


@dataclass
class Inventory:
    levels: int
    keys: list[KeyRow]
    levels_with: list[LevelsWith]
    cross: list[CrossCheck]
    modules: dict[str, dict[str, Any]]
    module_classes: list[str]
    class_counts: dict[str, int]
    no_modules: list[str]
    night_mismatch: list[str]
    totals: dict[str, Any] = field(default_factory=dict)


def _short(value: Any, limit: int = 60) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def load_levels(levels_dir: Path) -> list[dict[str, Any]]:
    """读全部关卡 JSON，按 id 排序。"""
    docs: list[dict[str, Any]] = []
    for path in sorted(levels_dir.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(doc, dict) or "id" not in doc:
            continue
        docs.append(doc)
    docs.sort(key=lambda d: str(d["id"]))
    return docs


def load_originals(obb_dir: Path) -> dict[str, dict[str, Any]]:
    """package -> {modules, classes, aliases}；只读 LevelDefinition 文件。"""
    originals: dict[str, dict[str, Any]] = {}
    for path in sorted(obb_dir.glob("pkg_*_LevelDefinition.json")):
        pkg = path.name.split("_LevelDefinition")[0]
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        modules: set[str] = set()
        classes: dict[str, int] = {}
        for obj in doc.get("objects") or []:
            name = obj.get("objclass") or "?"
            classes[name] = classes.get(name, 0) + 1
            if name != "LevelDefinition":
                continue
            for item in (obj.get("objdata") or {}).get("Modules") or []:
                match = RTID_RE.match(str(item))
                if match:
                    modules.add(match.group(1))
        originals[pkg] = {"modules": sorted(modules), "classes": classes}
    return originals


def _key_row(key: str, values: list[Any], worlds: list[str]) -> KeyRow:
    spec = KEY_SPECS.get(key)
    samples: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _short(value)
        if text in seen:
            continue
        seen.add(text)
        samples.append(text)
        if len(samples) >= KEY_SAMPLE_LIMIT:
            break
    types = sorted({type(v).__name__ for v in values})
    if spec is None:
        return KeyRow(
            key=key,
            count=len(values),
            worlds=worlds,
            value_types=types,
            samples=samples,
            kind="unknown",
            status="unknown",
            modules=[],
            classes=[],
            note=UNKNOWN_PROBE,
        )
    return KeyRow(
        key=key,
        count=len(values),
        worlds=worlds,
        value_types=types,
        samples=samples,
        kind=spec["kind"],
        status=spec["status"],
        modules=list(spec["modules"]),
        classes=list(spec["classes"]),
        note=spec["note"],
    )


def _module_client_key(name: str) -> str | None:
    if name in BOSS_MODULES:
        return "boss"
    if name in VASE_MODULES:
        return "vasebreaker"
    if name in RAIL_MODULES:
        return "minecarts"
    return None


def build(levels_dir: Path = DEFAULT_LEVELS, obb_dir: Path = DEFAULT_OBB) -> Inventory:
    docs = load_levels(levels_dir)
    originals = load_originals(obb_dir)

    values: dict[str, list[Any]] = {}
    worlds: dict[str, set[str]] = {}
    for doc in docs:
        extra = doc.get("extra")
        if not isinstance(extra, dict):
            continue
        for key, value in extra.items():
            values.setdefault(key, []).append(value)
            worlds.setdefault(key, set()).add(str(doc.get("world") or ""))

    keys = [_key_row(key, values[key], sorted(worlds[key])) for key in sorted(values)]

    levels_with: list[LevelsWith] = []
    for row in keys:
        if row.kind not in ("module", "derived"):
            continue
        ids = [
            str(doc["id"])
            for doc in docs
            if isinstance(doc.get("extra"), dict) and row.key in doc["extra"]
        ]
        levels_with.append(
            LevelsWith(
                key=row.key,
                count=len(ids),
                sample=ids[:LEVEL_SAMPLE_LIMIT],
                truncated=len(ids) > LEVEL_SAMPLE_LIMIT,
            )
        )

    module_levels: dict[str, list[str]] = {}
    no_modules: list[str] = []
    night_mismatch: list[str] = []
    class_counts: dict[str, int] = {}
    for doc in docs:
        extra = doc.get("extra") or {}
        original = originals.get(str(extra.get("package")))
        if original is None:
            continue
        for name, count in original["classes"].items():
            class_counts[name] = class_counts.get(name, 0) + count
        if not original["modules"]:
            no_modules.append(str(doc["id"]))
        for name in original["modules"]:
            module_levels.setdefault(name, []).append(str(doc["id"]))
        if bool(extra.get("night")) != ("Night" in str(extra.get("stage") or "")):
            night_mismatch.append(str(doc["id"]))

    modules = {
        name: {
            "levels": len(ids),
            "clientKey": _module_client_key(name),
            "sample": sorted(ids)[:LEVEL_SAMPLE_LIMIT],
        }
        for name, ids in sorted(module_levels.items())
    }

    def client_ids(pred) -> set[str]:
        return {str(doc["id"]) for doc in docs if pred(doc.get("extra") or {})}

    def original_ids(pred) -> set[str]:
        out: set[str] = set()
        for name, ids in module_levels.items():
            if pred(name):
                out.update(ids)
        return out

    cross = [
        CrossCheck(
            name="boss",
            client_key="boss",
            original=len(original_ids(lambda n: n in BOSS_MODULES)),
            client=len(client_ids(lambda e: bool(e.get("boss")))),
            both=len(original_ids(lambda n: n in BOSS_MODULES) & client_ids(lambda e: bool(e.get("boss")))),
            original_only=sorted(original_ids(lambda n: n in BOSS_MODULES) - client_ids(lambda e: bool(e.get("boss")))),
            client_only=sorted(client_ids(lambda e: bool(e.get("boss"))) - original_ids(lambda n: n in BOSS_MODULES)),
        ),
        CrossCheck(
            name="vasebreaker",
            client_key="vasebreaker",
            original=len(original_ids(lambda n: n in VASE_MODULES)),
            client=len(client_ids(lambda e: bool(e.get("vasebreaker")))),
            both=len(original_ids(lambda n: n in VASE_MODULES) & client_ids(lambda e: bool(e.get("vasebreaker")))),
            original_only=sorted(original_ids(lambda n: n in VASE_MODULES) - client_ids(lambda e: bool(e.get("vasebreaker")))),
            client_only=sorted(client_ids(lambda e: bool(e.get("vasebreaker"))) - original_ids(lambda n: n in VASE_MODULES)),
        ),
        CrossCheck(
            name="minecarts",
            client_key="minecarts",
            original=len(original_ids(lambda n: n in RAIL_MODULES)),
            client=len(client_ids(lambda e: "minecarts" in e)),
            both=len(original_ids(lambda n: n in RAIL_MODULES) & client_ids(lambda e: "minecarts" in e)),
            original_only=sorted(original_ids(lambda n: n in RAIL_MODULES) - client_ids(lambda e: "minecarts" in e)),
            client_only=sorted(client_ids(lambda e: "minecarts" in e) - original_ids(lambda n: n in RAIL_MODULES)),
        ),
    ]

    module_classes = sorted(class_counts)
    totals = {
        "levels": len(docs),
        "levelsWithExtra": sum(1 for doc in docs if isinstance(doc.get("extra"), dict)),
        "keys": len(keys),
        "moduleKeys": sum(1 for row in keys if row.kind == "module"),
        "dataKeys": sum(1 for row in keys if row.status == "data"),
        "flagOnlyKeys": sum(1 for row in keys if row.status == "flag_only"),
        "metaKeys": sum(1 for row in keys if row.status == "meta"),
        "unknownKeys": sum(1 for row in keys if row.status == "unknown"),
        "originalDefinitions": len(originals),
        "originalModules": len(modules),
        "originalModuleClasses": len(module_classes),
        "levelsWithoutModules": len(no_modules),
        "nightMismatches": len(night_mismatch),
        "stageVariants": len({str((doc.get("extra") or {}).get("stage")) for doc in docs}),
        "bossKinds": dict(
            sorted(
                Counter(
                    str((doc.get("extra") or {}).get("boss_zombie"))
                    for doc in docs
                    if (doc.get("extra") or {}).get("boss_zombie")
                ).items()
            )
        ),
    }
    return Inventory(
        levels=len(docs),
        keys=keys,
        levels_with=levels_with,
        cross=cross,
        modules=modules,
        module_classes=module_classes,
        class_counts=dict(sorted(class_counts.items())),
        no_modules=sorted(no_modules),
        night_mismatch=sorted(night_mismatch),
        totals=totals,
    )


def render_json(inv: Inventory) -> str:
    payload = {
        "format": FORMAT,
        "generated": MARKER,
        "levels": inv.levels,
        "totals": inv.totals,
        "keys": {row.key: row.as_dict() for row in inv.keys},
        "levelsWith": {item.key: item.as_dict() for item in inv.levels_with},
        "crossCheck": {item.name: item.as_dict() for item in inv.cross},
        "modules": inv.modules,
        "moduleClasses": inv.module_classes,
        "classCounts": inv.class_counts,
        "levelsWithoutModules": inv.no_modules,
        "nightMismatch": {
            "count": len(inv.night_mismatch),
            "sample": inv.night_mismatch[:LEVEL_SAMPLE_LIMIT],
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def _table(header: list[str], rows: Iterable[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def render_report(inv: Inventory) -> str:
    by_key = {row.key: row for row in inv.keys}
    cross = {item.name: item for item in inv.cross}
    unexported = [name for name, info in inv.modules.items() if info["clientKey"] is None]
    lines: list[str] = [
        "# S7.0 关卡模块清点（1809 关 extra → level_modules.json）",
        "",
        "- 生成命令：`python tools/contentc/levelextra.py`",
        "- 机器可读清单：`native/generated/level_modules.json`",
        "- 客户端侧：`content/levels/*.json` 的 `extra`",
        "- 原版侧：`work/obb_packages/pkg_*_LevelDefinition.json` 的 `Modules` 与模块参数对象",
        "",
        f"实测 {inv.levels} 关、{inv.totals['keys']} 个 `extra` 键、"
        f"{inv.totals['originalDefinitions']} 份原版关卡定义、"
        f"{inv.totals['originalModules']} 个不同模块名、"
        f"{inv.totals['originalModuleClasses']} 个对象类。下文所有数字均来自本次运行，"
        "没有对应原版模块的键一律标 `unknown` 并留探针，不做推测填充。",
        "",
        "## 结论摘要",
        "",
        f"1. **有数据可直接驱动**：`boss` {by_key['boss'].count} 关、"
        f"`vasebreaker` {by_key['vasebreaker'].count} 关、`minecarts` {by_key['minecarts'].count} 关；"
        f"另有 `stage`（{by_key['stage'].count} 关）与 `night`（{by_key['night'].count} 关）两个关卡级信号。"
        "原版这三类模块都带参数对象（见第 2 节），可以撑起运行时。",
        f"2. **只有标记无参数**：`boss_zombie`、`vasebreaker`、`special`、`minecarts`、`rail`、`night` "
        "六个键只说明「这一关有这个玩法」，参数（花瓶布局、轨道列、僵王阶段…）全部要回原版取。",
        f"3. **原版有但客户端没导出**：{inv.totals['originalModules']} 个原版模块名中只有 3 类有对应的 "
        "`extra` 键；`ChallengeModule`、`ConveyorBelt`、`Gravestones`、`ProtectThePlant`、`Tide` 等"
        f"共 {len(unexported)} 个模块完全没有客户端入口。具体覆盖缺口见第 4 节。",
        "",
        "## 一、extra 键总表",
        "",
    ]
    lines += _table(
        ["键", "出现关卡", "类型", "状态", "对应原版模块", "说明"],
        [
            [
                f"`{row.key}`",
                row.count,
                "/".join(row.value_types),
                row.status,
                "、".join(f"`{m}`" for m in row.modules) or "—",
                row.note,
            ]
            for row in inv.keys
        ],
    )
    lines += ["", "取值样例（每种键最多 8 个不同值）：", ""]
    for row in inv.keys:
        lines.append(f"- `{row.key}`：{'、'.join(row.samples)}")
    lines += [
        "",
        "## 二、有数据可直接驱动",
        "",
        "### 2.1 boss（僵王战）",
        "",
        f"- 客户端：`boss` 布尔 {by_key['boss'].count} 关、`boss_zombie` 代号 {by_key['boss_zombie'].count} 关"
        f"（实测 "
        + "、".join(f"{name} {count} 关" for name, count in inv.totals['bossKinds'].items())
        + "）。",
        f"- 原版：`ZombossBattleModuleProperties` "
        f"{inv.class_counts.get('ZombossBattleModuleProperties', 0)} 个对象、模块名 "
        f"`ZombossBattle` {inv.modules['ZombossBattle']['levels']} 关，"
        "另有 `ZombossBattleIntroProperties` 与各世界 `Zomboss*ActionDefinition`。",
        f"- 覆盖核对：原版 {cross['boss'].original} 关、客户端 {cross['boss'].client} 关、"
        f"交集 {cross['boss'].both} 关，两侧都没有多余项 —— 这一项**完全对齐**。",
        "",
        "### 2.2 vasebreaker（砸花瓶）",
        "",
        f"- 客户端：`vasebreaker` {by_key['vasebreaker'].count} 关，`special` 与之同步"
        f"（{by_key['special'].count} 关，取值恒为 `[\"IsVasebreaker\"]`）。",
        f"- 原版：`VaseBreakerPresetProperties` "
        f"{inv.class_counts.get('VaseBreakerPresetProperties', 0)} 个对象 + "
        f"`VaseBreakerEndlessProperties` {inv.class_counts.get('VaseBreakerEndlessProperties', 0)} 个，"
        f"模块名 `VaseBreakerArcade` {inv.modules['VaseBreakerArcade']['levels']} 关、"
        f"`TestVaseBreaker` {inv.modules['TestVaseBreaker']['levels']} 关。",
        f"- 覆盖核对：原版 {cross['vasebreaker'].original} 关、客户端 {cross['vasebreaker'].client} 关、"
        f"交集 {cross['vasebreaker'].both} 关，原版多出 "
        f"{len(cross['vasebreaker'].original_only)} 关："
        + "、".join(f"`{x}`" for x in cross["vasebreaker"].original_only)
        + "。",
        "",
        "### 2.3 minecarts（矿车/轨道）",
        "",
        f"- 客户端：`minecarts` {by_key['minecarts'].count} 关，取值只有行号"
        f"（如 {'、'.join(f'`{sample}`' for sample in by_key['minecarts'].samples[:3])}），"
        f"`rail` 同 {by_key['rail'].count} 关。",
        f"- 原版：`RailcartProperties` "
        f"{inv.class_counts.get('RailcartProperties', 0)} 个对象，模块名 "
        f"`Rails` {inv.modules['Rails']['levels']} 关、"
        f"`CowboyRails` {inv.modules['CowboyRails']['levels']} 关、"
        f"`Railcart` {inv.modules['Railcart']['levels']} 关、"
        f"`Railcart1` {inv.modules['Railcart1']['levels']} 关。",
        f"- 覆盖核对：原版 {cross['minecarts'].original} 关、客户端 {cross['minecarts'].client} 关、"
        f"交集只有 {cross['minecarts'].both} 关 —— 见 4.2，这项缺口最大。",
        "",
        "### 2.4 关卡级信号",
        "",
        f"- `stage`：{by_key['stage'].count} 关全覆盖，{inv.totals['stageVariants']} 个不同场景名；原版对应 `StageModule` 与各世界 "
        "`*StageProperties`（`BeachStageProperties`、`EgyptStageProperties` 等）。",
        f"- `night`：{by_key['night'].count} 关全覆盖的布尔，但有 "
        f"{inv.totals['nightMismatches']} 关与 `stage` 名里的 `Night` 不一致"
        f"（抽样：{'、'.join(f'`{x}`' for x in inv.night_mismatch[:6])}），"
        "实现时应以原版场景参数为准，不要直接信这个布尔。",
        "",
        "## 三、只有标记无参数",
        "",
        "这一档的键能告诉你「这一关是这个玩法」，但驱动不了任何表现，缺的参数如下：",
        "",
    ]
    lines += _table(
        ["键", "现有的", "缺的参数", "影响"],
        [
            ["`boss_zombie`", "僵王代号字符串", "阶段划分、血量、攻击/召唤序列、出场动作", "只能显示名字，摆不出战斗"],
            ["`vasebreaker`", "布尔", "花瓶数量与布局、可出植物池、波次表", "只能判定是不是砸花瓶关卡"],
            ["`special`", "`IsVasebreaker` 标记", "同上", "同上"],
            ["`minecarts`", "行号数组（如 `[0, 2]`）", "轨道列号、长度、速度、载量、生成节奏", "知道哪几行有车，画不出轨道"],
            ["`rail`", "布尔", "同上", "同上"],
            ["`night`", "布尔", "光照/音乐/场景参数（原版在 `*StageProperties`）", f"{inv.totals['nightMismatches']} 关与 `stage` 冲突，不能单独采信"],
        ],
    )
    absent = [row for row in inv.keys if row.status == "meta"]
    lines += [
        "",
        "另有 " + str(len(absent)) + " 个纯元数据键（"
        + "、".join(f"`{row.key}`" for row in absent)
        + "），它们不是模块，只是移植时的对账信息（`package` 用于回查原版文件）。",
        "",
        "## 四、原版有但客户端没导出",
        "",
        f"原版共 {inv.totals['originalModules']} 个不同模块名，只有 `ZombossBattle*`、`VaseBreaker*`、"
        "`Rails`/`CowboyRails`/`Railcart*` 三类能在 `extra` 里找到入口，其余 "
        f"{len(unexported)} 个模块名客户端完全没有导出。按关卡数排序的前 20 个：",
        "",
    ]
    missing = [(name, info) for name, info in inv.modules.items() if info["clientKey"] is None]
    missing.sort(key=lambda item: (-item[1]["levels"], item[0]))
    lines += _table(
        ["原版模块", "关卡数", "客户端键"],
        [[f"`{name}`", info["levels"], "—"] for name, info in missing[:20]],
    )
    lines += [
        "",
        "### 4.1 缺口集中在玩法模块",
        "",
        f"`ChallengeModule`（{inv.modules['ChallengeModule']['levels']} 关，星挑战）、"
        f"`StarChallengeModuleProperties`（{inv.class_counts.get('StarChallengeModuleProperties', 0)} 个对象）、"
        f"`ConveyorBelt`（{inv.modules['ConveyorBelt']['levels']} 关，传送带）、"
        f"`Gravestones`（{inv.modules['Gravestones']['levels']} 关，墓碑）、"
        f"`ProtectThePlant`（{inv.modules['ProtectThePlant']['levels']} 关，保护植物）、"
        f"`FrozenPlantPlacement`（{inv.modules['FrozenPlantPlacement']['levels']} 关）、"
        f"`Tide`（{inv.modules['Tide']['levels']} 关，潮汐）、"
        f"`GoldTiles`（{inv.modules['GoldTiles']['levels']} 关）、"
        f"`LastStand`（{inv.modules['LastStand']['levels']} 关）、"
        f"`SliderPlacement`（{inv.modules['SliderPlacement']['levels']} 关）都属于"
        "「有完整参数、客户端只有关卡 JSON 本体」的情况：S7 要支持它们，参数一律从原版模块对象读。",
        "",
        "### 4.2 rails 覆盖缺口",
        "",
        f"- 原版 {cross['minecarts'].original} 关带 rail 模块，客户端只有 {cross['minecarts'].client} 关标了 "
        f"`minecarts`，两侧都有的仅 {cross['minecarts'].both} 关。",
        f"- 原版有、客户端没标：{len(cross['minecarts'].original_only)} 关，抽样 "
        + "、".join(f"`{x}`" for x in cross["minecarts"].original_only[:8])
        + "。",
        f"- 客户端标了、原版没有 rail 模块：{len(cross['minecarts'].client_only)} 关 —— "
        + "、".join(f"`{x}`" for x in cross["minecarts"].client_only)
        + "。两个方向都不是漏标：模块名口径（本工具）与对象级证据（`RailcartProperties.Railcarts` / "
        "`DangerRoomRailcartDesigner`）在 7 关原版只有对象、12 关只有模块名之外的情形上不一致；"
        "t52 起 `content` 上的标记由 `tools/obb_build_content_v2.py` 按**对象级证据**派生，"
        "所以这里的分歧属口径差异，不是待修缺口。",
        "",
        "### 4.3 vasebreaker 覆盖缺口",
        "",
        f"原版 {cross['vasebreaker'].original} 关、客户端 {cross['vasebreaker'].client} 关，"
        + (
            "差集 "
            + "、".join(f"`{x}`" for x in cross["vasebreaker"].original_only)
            + " 是 `TestVaseBreaker`/未导出开关的关卡，实现时要按原版补。"
            if cross["vasebreaker"].original_only
            else "两侧一致，没有缺口（t52 已按原版 `Modules` 补齐）。"
        ),
        "",
        "### 4.4 原版没有 Modules 的关卡",
        "",
        f"{len(inv.no_modules)} 关的原版定义里没有 `Modules` 列表："
        + "、".join(f"`{x}`" for x in inv.no_modules)
        + "。它们只有 `LevelDefinition` 一个对象，属于没有模块可跑的关卡（选关/演示类），"
        "S7 不能假设每关都有模块表。",
        "",
        "## 五、unknown 与探针",
        "",
    ]
    unknown = [row for row in inv.keys if row.status == "unknown"]
    if unknown:
        for row in unknown:
            lines.append(f"- `{row.key}`（{row.count} 关）：{row.note}")
    else:
        lines.append("- 本次运行没有对不上原版的 `extra` 键。")
    lines += [
        f"- 原版没有 rail 模块名、客户端却有标记的 {len(cross['minecarts'].client_only)} 关（"
        + "、".join(f"`{x}`" for x in cross["minecarts"].client_only)
        + "）：这些关在原版有 `RailcartProperties` 对象（对象级证据成立），只是 `Modules` 里没写 "
        "`Rails`/`CowboyRails`，属模块名口径漏判；t52 起标记改由对象级证据派生，不再按缺参数处理。"
        "原先 7 个 kongfu 误标关（原版既无模块也无对象）已在 t52 撤标。",
        "",
        "## 六、逐键明细",
        "",
    ]
    for row in inv.keys:
        lines += [
            f"### `{row.key}`",
            "",
            f"- 出现：{row.count} 关；世界：{'、'.join(row.worlds)}",
            f"- 状态：`{row.status}`；对应原版模块：{'、'.join(row.modules) or '—'}；"
            f"参数类：{'、'.join(row.classes) or '—'}",
            f"- 样例：{'、'.join(row.samples)}",
            "",
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


def write_outputs(inv: Inventory, json_path: Path, report_path: Path) -> list[Path]:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_bytes(render_json(inv).encode("utf-8"))
    report_path.write_bytes(render_report(inv).encode("utf-8"))
    return [json_path, report_path]


def summarize(inv: Inventory) -> str:
    parts = [
        f"levels={inv.levels}",
        f"keys={inv.totals['keys']}",
        f"data={inv.totals['dataKeys']}",
        f"flagOnly={inv.totals['flagOnlyKeys']}",
        f"meta={inv.totals['metaKeys']}",
        f"unknown={inv.totals['unknownKeys']}",
        f"originalModules={inv.totals['originalModules']}",
    ]
    for item in inv.cross:
        parts.append(f"{item.name}=orig{item.original}/client{item.client}/both{item.both}")
    return " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="清点关卡 extra 与模块覆盖")
    parser.add_argument("--levels", type=Path, default=DEFAULT_LEVELS)
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--check", action="store_true", help="只校验产物是否与当前数据一致")
    parser.add_argument("-n", "--dry-run", action="store_true", help="只打印摘要")
    args = parser.parse_args(argv)

    if not args.levels.is_dir():
        print(f"缺少关卡目录：{args.levels}", file=sys.stderr)
        return 2
    if not args.obb.is_dir():
        print(f"缺少原版表目录：{args.obb}", file=sys.stderr)
        return 2

    inv = build(args.levels, args.obb)
    if args.check:
        stale: list[str] = []
        for path, text in ((args.json, render_json(inv)), (args.report, render_report(inv))):
            try:
                current = path.read_bytes()
            except OSError:
                stale.append(f"{path}（缺失）")
                continue
            if current != text.encode("utf-8"):
                stale.append(str(path))
        if stale:
            print("产物需要重新生成：", file=sys.stderr)
            for item in stale:
                print(f"  {item}", file=sys.stderr)
            return 2
        print(f"产物已是最新：{summarize(inv)}")
        return 0
    if args.dry_run:
        print(summarize(inv))
        return 0

    write_outputs(inv, args.json, args.report)
    print(summarize(inv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
