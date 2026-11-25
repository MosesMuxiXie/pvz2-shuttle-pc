"""把 1809 关的**关卡机制**从原版 ``LevelDefinition`` 包编译成客户端可读的一份数据（T51）。

运行::

    python tools/contentc/mechanics.py            # 生成产物
    python tools/contentc/mechanics.py --check    # 只校验产物是否最新（逐字节）
    python tools/contentc/mechanics.py -n         # 只打印摘要，不写盘

口径
----
1. **身份锚点**：客户端 ``content/levels/*.json`` 的 ``extra.package``，值形如
   ``"pkg_0264"``（已带 ``pkg_`` 前缀的完整 stem）。它对应
   ``work/obb_packages/pkg_0264_LevelDefinition.json``。实测 1809 个值两两不同、
   0 个缺文件，是双射。**不用** ``StageModule`` + ``LevelNumber``：那对键在
   1809 关里只有 1385 个不同值，不唯一（t37 已确认的坑）。
2. **机制来源**：同一个包文件里 objclass 匹配的对象的 ``objdata``。``aliases``
   是该对象的 RTID 短名，也是 ``WaveManagerProperties.Waves`` 里引用的键，
   因此波次归属 = alias -> 波号（1 基）。
3. **不推测填充**：拿不到就是 ``null``；拿不准的进 ``unknowns[]``（带探针建议）。
   哨兵值（``-1`` / ``2147483647``）**原样保留**并单独计数，不替换成"缺失"。
4. **数值字符串**：原版里不少浮点/整数以字符串给出（如
   ``TimeBetweenGroups: "1.5"``），编译时 coerce 成数字并计数，报告里给出
   出现次数最多的字段。

产物（确定性：sort_keys、indent=1、utf-8、末尾换行、固定 generated 日期）：

* ``native/generated/level_mechanics.json``
* ``docs/reviews/2026-11-24-level-mechanics.md``
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator
import os

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEVELS = ROOT / "content" / "levels"
DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages"))
DEFAULT_JSON = ROOT / "native" / "generated" / "level_mechanics.json"
DEFAULT_REPORT = ROOT / "docs" / "reviews" / "2026-11-24-level-mechanics.md"

FORMAT = 1
#: 固定日期，不取运行时时钟 —— 否则 ``--check`` 永远失败。
GENERATED = "2026-11-24"

RTID_RE = re.compile(r"RTID\(\s*([^@)\s]+)\s*@([^)\s]+)\s*\)")
#: alias 兜底：``Wave7StormEvent0`` / ``Wave11`` / ``w2dinos0_2`` 都取第一个数字。
WAVE_FALLBACK_RE = re.compile(r"[Ww]ave\s*(\d+)")
PKG_STEM_RE = re.compile(r"^(pkg_\d+)_")

#: 哨兵值：原版用它们表示"无/无穷"。
SENTINELS = (-1, 2147483647)

#: 顶层机制键（顺序即报告顺序）。值为 ``None`` 表示本关没有该机制。
MECHANICS = (
    "conveyor",
    "initialPlants",
    "initialGridItems",
    "protectThePlant",
    "spawners",
    "events",
    "mutators",
    "boardGrid",
)

CONVEYOR_CLS = "ConveyorSeedBankProperties"
CONVEYOR_MOD_CLS = "ModifyConveyorWaveActionProps"
INITIAL_PLANT_CLS = "InitialPlantProperties"
GRID_ITEM_CLS = "InitialGridItemProperties"
GRAVESTONE_CLS = "GravestoneProperties"
PROTECT_CLS = "ProtectThePlantChallengeProperties"
TIDE_CLS = "TidalChangeWaveActionProps"
FROST_CLS = "FrostWindWaveActionProps"
BOARD_CLS = "BoardGridMapProps"
WAVE_MANAGER_CLS = "WaveManagerProperties"

#: 八类生成器（任务要求）+ 实测另有两类必须一起带走：
#: ``gravestone``（353 关的墓石生成）与 ``jittered``（普通波次的主力，
#: 371 关的僵尸全部由它产生）。它们放在 ``spawners`` 子键里，不额外占顶层键。
SPAWNER_CLASSES: dict[str, str] = {
    "grid": "SpawnZombiesFromGridItemSpawnerProps",
    "ground": "SpawnZombiesFromGroundSpawnerProps",
    "spider": "SpiderRainZombieSpawnerProps",
    "storm": "StormZombieSpawnerProps",
    "fish": "SpawnZombiesFishWaveActionProps",
    "portal": "SpawnModernPortalsWaveActionProps",
    "dino": "DinoWaveActionProps",
    "beach": "BeachStageEventZombieSpawnerProps",
    "gravestone": "SpawnGravestonesWaveActionProps",
    "jittered": "SpawnZombiesJitteredWaveActionProps",
}


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #


def rtid_name(value: Any) -> str | None:
    """``RTID(Wave1@CurrentLevel)`` -> ``"Wave1"``；不是 RTID 返回 ``None``。"""
    if not isinstance(value, str):
        return None
    match = RTID_RE.search(value)
    return match.group(1) if match else None


def as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None
    return None


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
    return None


def dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def pick_str(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return None


@dataclass
class Stats:
    """编译过程中收集的异常计数（进 counts / unknowns，不进 levels）。"""

    sentinels: Counter = field(default_factory=Counter)  # (cls, key, value)
    coerced: Counter = field(default_factory=Counter)  # (cls, key, "numstr"|"boolint")
    wave_hit: Counter = field(default_factory=Counter)  # cls
    wave_miss: Counter = field(default_factory=Counter)  # cls
    wave_miss_samples: dict[str, list[str]] = field(default_factory=dict)
    empty_objdata: Counter = field(default_factory=Counter)  # cls
    dirty_keys: Counter = field(default_factory=Counter)  # (cls, key)

    def num(self, cls: str, key: str, value: Any) -> float | int | None:
        """取数字；记录"本来是字符串"的强制转换与哨兵。"""
        if isinstance(value, str) and value.strip():
            parsed = as_float(value)
            if parsed is not None:
                self.coerced[(cls, key, "numstr")] += 1
                self.check_sentinel(cls, key, parsed)
                if float(parsed).is_integer():
                    return int(parsed)
                return parsed
            return None
        if isinstance(value, bool):
            self.coerced[(cls, key, "boolint")] += 1
            return int(value)
        if isinstance(value, (int, float)):
            self.check_sentinel(cls, key, value)
            return value
        return None

    def check_sentinel(self, cls: str, key: str, value: Any) -> None:
        try:
            if value in SENTINELS:
                self.sentinels[(cls, key, int(value))] += 1
        except TypeError:  # pragma: no cover - 不可哈希的怪值
            return

    def hit_wave(self, cls: str) -> None:
        self.wave_hit[cls] += 1

    def miss_wave(self, cls: str, alias: str | None) -> None:
        self.wave_miss[cls] += 1
        bucket = self.wave_miss_samples.setdefault(cls, [])
        if alias and alias not in bucket and len(bucket) < 3:
            bucket.append(alias)


# --------------------------------------------------------------------------- #
# 加载
# --------------------------------------------------------------------------- #


@dataclass
class ClientLevel:
    level_id: str
    package: str | None
    path: Path


def load_client_levels(levels_dir: Path) -> list[ClientLevel]:
    out: list[ClientLevel] = []
    for path in sorted(levels_dir.glob("*.json")):
        try:
            with path.open(encoding="utf-8-sig") as handle:
                doc = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(doc, dict):
            continue
        level_id = doc.get("id")
        if not isinstance(level_id, str) or not level_id:
            continue
        extra = doc.get("extra")
        package = None
        if isinstance(extra, dict):
            raw = extra.get("package")
            if isinstance(raw, str) and raw.strip():
                package = raw.strip()
        out.append(ClientLevel(level_id=level_id, package=package, path=path))
    out.sort(key=lambda item: item.level_id)
    return out


def index_packages(obb_dir: Path) -> dict[str, list[Path]]:
    """``pkg_0264`` -> [path, ...]；列表长度 >1 说明包名撞车（实测 0 例）。"""
    index: dict[str, list[Path]] = {}
    for path in sorted(obb_dir.glob("pkg_*_LevelDefinition.json")):
        match = PKG_STEM_RE.match(path.name)
        if match:
            index.setdefault(match.group(1), []).append(path)
    return index


def load_package(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8-sig") as handle:
            doc = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


class Package:
    """一个 LevelDefinition 包的只读视图。"""

    __slots__ = ("path", "doc", "objects")

    def __init__(self, path: Path, doc: dict[str, Any]) -> None:
        self.path = path
        self.doc = doc
        raw = doc.get("objects")
        self.objects: list[dict[str, Any]] = dicts(raw)

    def all_of(self, objclass: str) -> list[tuple[int, dict[str, Any]]]:
        return [
            (index, obj)
            for index, obj in enumerate(self.objects)
            if obj.get("objclass") == objclass
        ]

    def one(self, objclass: str) -> tuple[int, dict[str, Any]] | None:
        found = self.all_of(objclass)
        return found[0] if found else None

    def alias(self, index: int) -> str | None:
        aliases = self.objects[index].get("aliases")
        if isinstance(aliases, list) and aliases:
            first = aliases[0]
            if isinstance(first, str) and first:
                return first
        return None

    def objdata(self, index: int) -> dict[str, Any]:
        data = self.objects[index].get("objdata")
        return data if isinstance(data, dict) else {}

    def ref(self, index: int) -> str:
        return f"objects[{index}]"

    def wave_map(self) -> dict[str, int]:
        """alias -> 波号（1 基）；``Waves`` 缺失时返回空表。"""
        mapping: dict[str, int] = {}
        for index, _obj in self.all_of(WAVE_MANAGER_CLS):
            waves = self.objdata(index).get("Waves")
            if not isinstance(waves, list):
                continue
            for wave_no, entry in enumerate(waves, 1):
                if not isinstance(entry, list):
                    continue
                for item in entry:
                    name = rtid_name(item)
                    if name and name not in mapping:
                        mapping[name] = wave_no
        return mapping

    def declared_modules(self) -> set[str]:
        for index, _obj in enumerate(self.objects):
            if self.objects[index].get("objclass") != "LevelDefinition":
                continue
            modules = self.objdata(index).get("Modules")
            if isinstance(modules, list):
                names = {rtid_name(item) for item in modules}
                return {name for name in names if name}
        return set()


def wave_number(
    alias: str | None, waves: dict[str, int], objclass: str, stats: Stats
) -> int | None:
    if alias is not None and alias in waves:
        stats.hit_wave(objclass)
        return waves[alias]
    if alias:
        match = WAVE_FALLBACK_RE.search(alias)
        if match:
            stats.hit_wave(objclass)
            return int(match.group(1))
    stats.miss_wave(objclass, alias)
    return None


# --------------------------------------------------------------------------- #
# 各机制
# --------------------------------------------------------------------------- #


def conveyor_slot(cls: str, raw: dict[str, Any], stats: Stats) -> dict[str, Any]:
    """``ConveyorSeedBankProperties.InitialPlantList[]`` 的一条。

    注意 ``Add`` 用 ``Type``、``Remove`` 用 ``Type``/``PlantType``，两种键都认；
    另有小写 ``level`` 脏键（实测 1 例），一并读但记进 dirty_keys。
    """

    plant = pick_str(raw.get("PlantType")) or pick_str(raw.get("Type"))
    if raw.get("level") is not None and raw.get("Level") is None:
        stats.dirty_keys[(cls, "level")] += 1
    level = raw.get("Level")
    if level is None and raw.get("level") is not None:
        level = raw.get("level")
    return {
        "plant": plant,
        "weight": stats.num(cls, "Weight", raw.get("Weight")),
        "minCount": stats.num(cls, "MinCount", raw.get("MinCount")),
        "maxCount": stats.num(cls, "MaxCount", raw.get("MaxCount")),
        "minWeightFactor": stats.num(cls, "MinWeightFactor", raw.get("MinWeightFactor")),
        "maxWeightFactor": stats.num(cls, "MaxWeightFactor", raw.get("MaxWeightFactor")),
        "level": stats.num(cls, "Level", level),
        "minCountCooldownSeconds": stats.num(
            cls, "MinCountCooldownSeconds", raw.get("MinCountCooldownSeconds")
        ),
        "maxCountCooldownSeconds": stats.num(
            cls, "MaxCountCooldownSeconds", raw.get("MaxCountCooldownSeconds")
        ),
        "mixCountCooldownSeconds": stats.num(
            cls, "MixCountCooldownSeconds", raw.get("MixCountCooldownSeconds")
        ),
        "maxDelivered": stats.num(cls, "MaxDelivered", raw.get("MaxDelivered")),
        "forceBoosted": as_bool(raw.get("ForceBoosted")),
        "toolType": pick_str(raw.get("ToolType")),
    }


def extract_conveyor(
    package: Package, waves: dict[str, int], stats: Stats, sources: dict[str, list[str]]
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    body = package.one(CONVEYOR_CLS)
    if body is not None:
        index, _obj = body
        data = package.objdata(index)
        sources.setdefault("conveyor", []).append(package.ref(index))
        payload["alias"] = package.alias(index)
        payload["slots"] = [
            conveyor_slot(CONVEYOR_CLS, raw, stats)
            for raw in dicts(data.get("InitialPlantList"))
        ]
        payload["speedConditions"] = [
            {
                "maxPackets": stats.num(CONVEYOR_CLS, "SpeedConditions.MaxPackets", raw.get("MaxPackets")),
                "speed": stats.num(CONVEYOR_CLS, "SpeedConditions.Speed", raw.get("Speed")),
            }
            for raw in dicts(data.get("SpeedConditions"))
        ]
        payload["dropDelayConditions"] = [
            {
                "delay": stats.num(CONVEYOR_CLS, "DropDelayConditions.Delay", raw.get("Delay")),
                "maxPackets": stats.num(
                    CONVEYOR_CLS, "DropDelayConditions.MaxPackets", raw.get("MaxPackets")
                ),
            }
            for raw in dicts(data.get("DropDelayConditions"))
        ]
        payload["manualPacketSpawning"] = as_bool(data.get("ManualPacketSpawning"))
        names = data.get("ResourceGroupNames")
        payload["resourceGroupNames"] = list(names) if isinstance(names, list) else []

    changes: list[dict[str, Any]] = []
    for index, _obj in package.all_of(CONVEYOR_MOD_CLS):
        data = package.objdata(index)
        alias = package.alias(index)
        sources.setdefault("conveyor", []).append(package.ref(index))
        changes.append(
            {
                "wave": wave_number(alias, waves, CONVEYOR_MOD_CLS, stats),
                "alias": alias,
                "add": [
                    conveyor_slot(CONVEYOR_MOD_CLS, raw, stats)
                    for raw in dicts(data.get("Add"))
                ],
                "remove": [
                    conveyor_slot(CONVEYOR_MOD_CLS, raw, stats)
                    for raw in dicts(data.get("Remove"))
                ],
                "speedConditions": [
                    {
                        "maxPackets": stats.num(
                            CONVEYOR_MOD_CLS, "SpeedConditions.MaxPackets", raw.get("MaxPackets")
                        ),
                        "speed": stats.num(
                            CONVEYOR_MOD_CLS, "SpeedConditions.Speed", raw.get("Speed")
                        ),
                    }
                    for raw in dicts(data.get("SpeedConditions"))
                ],
                "dropDelayConditions": [
                    {
                        "delay": stats.num(
                            CONVEYOR_MOD_CLS, "DropDelayConditions.Delay", raw.get("Delay")
                        ),
                        "maxPackets": stats.num(
                            CONVEYOR_MOD_CLS,
                            "DropDelayConditions.MaxPackets",
                            raw.get("MaxPackets"),
                        ),
                    }
                    for raw in dicts(data.get("DropDelayConditions"))
                ],
            }
        )

    if not payload and not changes:
        return None
    if changes:
        payload["changes"] = changes
    payload.setdefault("slots", [])
    return payload


def extract_initial_plants(
    package: Package, stats: Stats, sources: dict[str, list[str]]
) -> dict[str, Any] | None:
    placements: list[dict[str, Any]] = []
    flags: dict[str, Any] = {}
    seen = False
    for index, _obj in package.all_of(INITIAL_PLANT_CLS):
        data = package.objdata(index)
        seen = True
        sources.setdefault("initialPlants", []).append(package.ref(index))
        for raw in dicts(data.get("InitialPlantPlacements")):
            placements.append(
                {
                    "gridX": stats.num(INITIAL_PLANT_CLS, "GridX", raw.get("GridX")),
                    "gridY": stats.num(INITIAL_PLANT_CLS, "GridY", raw.get("GridY")),
                    "plant": pick_str(raw.get("TypeName")),
                    "level": stats.num(INITIAL_PLANT_CLS, "Level", raw.get("Level")),
                    "condition": pick_str(raw.get("Condition")),
                }
            )
        for key in ("IsInitialIntensiveCarrotPlacements", "IsInitialimpatiensshooterPlacements"):
            if key in data:
                flags[key] = as_bool(data.get(key))
    if not seen:
        return None
    payload: dict[str, Any] = {"placements": placements}
    payload.update(flags)
    return payload


def extract_initial_grid_items(
    package: Package, stats: Stats, sources: dict[str, list[str]]
) -> dict[str, Any] | None:
    placements: list[dict[str, Any]] = []
    aliases: list[str] = []
    seen = False
    for index, _obj in package.all_of(GRID_ITEM_CLS):
        data = package.objdata(index)
        seen = True
        alias = package.alias(index)
        if alias:
            aliases.append(alias)
        sources.setdefault("initialGridItems", []).append(package.ref(index))
        for raw in dicts(data.get("InitialGridItemPlacements")):
            placements.append(
                {
                    "gridX": stats.num(GRID_ITEM_CLS, "GridX", raw.get("GridX")),
                    "gridY": stats.num(GRID_ITEM_CLS, "GridY", raw.get("GridY")),
                    "item": pick_str(raw.get("TypeName")),
                }
            )

    gravestones: dict[str, Any] | None = None
    grave_objects: list[dict[str, Any]] = []
    for index, _obj in package.all_of(GRAVESTONE_CLS):
        data = package.objdata(index)
        sources.setdefault("initialGridItems", []).append(package.ref(index))
        if not data:
            stats.empty_objdata[GRAVESTONE_CLS] += 1
            grave_objects.append({"alias": package.alias(index), "empty": True})
            continue
        grave_objects.append(
            {
                "alias": package.alias(index),
                "forceSpawn": [
                    {
                        "gridX": stats.num(GRAVESTONE_CLS, "GridX", raw.get("GridX")),
                        "gridY": stats.num(GRAVESTONE_CLS, "GridY", raw.get("GridY")),
                        "type": pick_str(raw.get("TypeName")),
                    }
                    for raw in dicts(data.get("ForceSpawnData"))
                ],
                "gravestoneCount": stats.num(
                    GRAVESTONE_CLS, "GravestoneCount", data.get("GravestoneCount")
                ),
                "spawnColumnStart": stats.num(
                    GRAVESTONE_CLS, "SpawnColumnStart", data.get("SpawnColumnStart")
                ),
                "spawnColumnEnd": stats.num(
                    GRAVESTONE_CLS, "SpawnColumnEnd", data.get("SpawnColumnEnd")
                ),
            }
        )
    if grave_objects:
        gravestones = {"objects": grave_objects}

    if not seen and gravestones is None:
        return None
    payload: dict[str, Any] = {"placements": placements, "aliases": aliases}
    if gravestones is not None:
        payload["gravestones"] = gravestones
    return payload


def extract_protect(
    package: Package, stats: Stats, sources: dict[str, list[str]]
) -> dict[str, Any] | None:
    """抽出保护目标，**合并同包的所有 protect 模块**。

    一个 package 可以带多个 ``ProtectThePlantChallengeProperties``：
    ``pkg_0965``（= ``lostcity_46``）就同时挂了 ``ProtectThePlant1``（2 株）与
    ``ProtectThePlant``（7 株），两个别名都在同一个 ``LevelDefinition.Modules`` 里
    —— 也就是说它们是**并发**的，不是备选。旧实现用 ``package.one()`` 只取第一个，
    结果是这一关只剩 2 株目标、丢掉 7 株（t56 查实）。

    合并规则（都写在下面的字段上）：
    - ``plants``：按对象顺序拼接，每条带 ``module``（来源模块别名），逐条可追；
    - ``mustProtectCount``：**各模块之和**。原版是「每个模块各自要求 N 株存活」，
      并发模块的要求自然相加（此包 2 + 2 = 4）；有任何模块缺这个字段时整关记 ``null``，
      不用 0 兜底（0 会被引擎读成「不要求」，是危险默认值）；
    - ``aliases`` / ``modules``：合并前的模块清单，保留别名与 ``objects[i]`` 出处。
    """
    modules = package.all_of(PROTECT_CLS)
    if not modules:
        return None
    plants: list[dict[str, Any]] = []
    module_rows: list[dict[str, Any]] = []
    aliases: list[str] = []
    must_values: list[Any] = []
    for index, _obj in modules:
        data = package.objdata(index)
        alias = package.alias(index)
        aliases.append(alias)
        sources.setdefault("protectThePlant", []).append(package.ref(index))
        must = stats.num(PROTECT_CLS, "MustProtectCount", data.get("MustProtectCount"))
        must_values.append(must)
        module_plants = [
            {
                "gridX": stats.num(PROTECT_CLS, "GridX", raw.get("GridX")),
                "gridY": stats.num(PROTECT_CLS, "GridY", raw.get("GridY")),
                "plant": pick_str(raw.get("PlantType")),
                # `Level` 不是坐标，是层号（地面层/植物层这类分层），详见报告第七节。
                "level": stats.num(PROTECT_CLS, "Level", raw.get("Level")),
                "condition": pick_str(raw.get("Condition")),
                "module": alias,
            }
            for raw in dicts(data.get("Plants"))
        ]
        plants.extend(module_plants)
        module_rows.append(
            {
                "alias": alias,
                "object": package.ref(index),
                "mustProtectCount": must,
                "plants": len(module_plants),
            }
        )
    numeric = [value for value in must_values if isinstance(value, (int, float))]
    must_total: Any = int(sum(numeric)) if len(numeric) == len(must_values) else None
    return {
        "alias": aliases[0],
        "aliases": aliases,
        "mustProtectCount": must_total,
        "plants": plants,
        "modules": module_rows,
        # 失败条件：原表**没有**这个开关，它是我们的语义约定（受保护植物死亡即判负）。
        # 显式标注来源，免得以后核对字段级差距时被当成原版字段（t56 第 2.3 节）。
        "failWhenProtectedPlantDies": True,
        "failWhenProtectedPlantDiesSource": "client-default",
    }


SPAWNER_FIELDS: dict[str, tuple[str, ...]] = {
    "grid": ("GridTypes", "ZombieSpawnWaitTime", "SuppressActionIfNoGridItemsFound"),
    "ground": ("ColumnStart", "ColumnEnd"),
    "spider": ("ColumnStart", "ColumnEnd", "GroupSize", "SpiderCount", "TimeBetweenGroups"),
    "storm": ("ColumnStart", "ColumnEnd", "GroupSize", "TimeBetweenGroups", "Type"),
    "fish": ("Tiles",),
    "portal": ("PortalColumn", "PortalRow", "PortalType"),
    "dino": ("DinoType", "DinoRow", "DinoWaveDuration"),
    "beach": ("ColumnStart", "ColumnEnd", "GroupSize", "ZombieCount", "WaveLocation"),
    "gravestone": ("RandomPlacement", "ShakeScreen", "SpawnEffectAnimID", "SpawnSoundID"),
    "jittered": ("Row", "WaveStartMessage", "AdditionalPlantfood"),
}


def extract_spawners(
    package: Package, waves: dict[str, int], stats: Stats, sources: dict[str, list[str]]
) -> dict[str, Any] | None:
    buckets: dict[str, Any] = {}
    for kind, cls in SPAWNER_CLASSES.items():
        records: list[dict[str, Any]] = []
        for index, _obj in package.all_of(cls):
            data = package.objdata(index)
            alias = package.alias(index)
            sources.setdefault("spawners", []).append(package.ref(index))
            record: dict[str, Any] = {
                "wave": wave_number(alias, waves, cls, stats),
                "alias": alias,
            }
            for field_name in SPAWNER_FIELDS[kind]:
                if field_name not in data:
                    continue
                record[field_name[0].lower() + field_name[1:]] = stats.num(
                    cls, field_name, data.get(field_name)
                )
            for key in ("Zombies", "Fishes", "GravestonePool", "SpawnPositionsPool"):
                if key in data:
                    record[key[0].lower() + key[1:]] = _spawn_entries(cls, key, data.get(key), stats)
            for key in ("AdditionalPlantfood", "DynamicPlantfood", "WaveStartMessage"):
                if key in data:
                    raw = data.get(key)
                    record[key[0].lower() + key[1:]] = (
                        pick_str(raw) if isinstance(raw, str) else stats.num(cls, key, raw)
                    )
            records.append(record)
        if not records:
            continue
        if kind == "jittered":
            # 唯一被压成摘要的一类：见 _aggregate_jittered 的说明。
            buckets[kind] = _aggregate_jittered(records)
        else:
            buckets[kind] = records
    return buckets or None


def _sort_key(value: Any) -> tuple[int, Any]:
    """混合类型（int / 数字字符串 / 其它）的稳定排序键。"""
    return (0, value) if isinstance(value, (int, float)) and not isinstance(value, bool) else (1, str(value))


def _aggregate_jittered(records: list[dict[str, Any]]) -> dict[str, Any]:
    """把 ``jittered`` 池从逐条条目压成「按僵尸 id 聚合」的摘要。

    原版 ``SpawnZombiesJitteredWaveActionProps`` 在 1615 关里共 121018 条僵尸条目，
    逐条落盘会把产物顶到 17 MB。这个池不是权重表 —— 同一个 id 出现 N 次就是 N 只，
    所以 ``pool[zombieId].count`` 与逐条列表**信息等价**，引擎按 count 抽即可。
    其余机制（conveyor / initialPlants / initialGridItems / protect / events /
    mutators / boardGrid，以及 spawners 的另外九类）保持逐条，不裁。

    保留下来的字段：
    - ``objects`` / ``total``：源对象数与僵尸条目总数；
    - ``waves`` ``{波号: 对象数}`` 与 ``waveUnresolved``：波次归属（含无法解析的）；
    - ``pool`` ``{zombieId: {count, rows, levels}}``：``rows`` 是该 id 出现过的行号
      （原版多数条目不带行号，所以缺行号时该键不存在）；
    - ``additionalPlantfood`` / ``dynamicPlantfood``：非零时给总和。
    """
    pool: dict[str, dict[str, Any]] = {}
    waves: dict[str, int] = {}
    unresolved = 0
    total = 0
    plantfood = {"additionalPlantfood": 0, "dynamicPlantfood": 0}
    for record in records:
        wave = record.get("wave")
        if wave is None:
            unresolved += 1
        else:
            waves[str(wave)] = waves.get(str(wave), 0) + 1
        for key in plantfood:
            value = record.get(key)
            if isinstance(value, (int, float)):
                plantfood[key] += int(value)
        for entry in record.get("zombies") or []:
            zombie = entry.get("type")
            if not isinstance(zombie, str):
                continue
            total += 1
            slot = pool.setdefault(zombie, {"count": 0, "rows": set(), "levels": set()})
            slot["count"] += 1
            row = entry.get("row")
            if row is not None:
                slot["rows"].add(row)
            level = entry.get("level")
            if level is not None:
                slot["levels"].add(level)
    summary: dict[str, Any] = {
        "objects": len(records),
        "total": total,
        "waves": {key: waves[key] for key in sorted(waves, key=int)},
        "waveUnresolved": unresolved,
        "pool": {},
    }
    for zombie in sorted(pool):
        slot = pool[zombie]
        item: dict[str, Any] = {"count": slot["count"]}
        if slot["rows"]:
            # 原版行号既有整数也有数字字符串（还有极少数非数字），统一按「数字优先」排，
            # 值本身保持原样（不做类型改写），否则排序会在 str/int 之间炸。
            item["rows"] = sorted(slot["rows"], key=_sort_key)
        if slot["levels"]:
            item["levels"] = sorted(slot["levels"], key=_sort_key)
        summary["pool"][zombie] = item
    for key, value in plantfood.items():
        if value:
            summary[key] = value
    return summary


SPAWN_POOL_KEYS: dict[str, tuple[str, ...]] = {
    "Zombies": ("Type", "Row", "Level", "Direction"),
    "Fishes": ("Type", "Position", "Count"),
    "GravestonePool": ("Type", "Count", "Weight"),
    "SpawnPositionsPool": ("mX", "mY"),
}


def _spawn_entries(
    cls: str, key: str, value: Any, stats: Stats
) -> list[dict[str, Any]]:
    fields = SPAWN_POOL_KEYS[key]
    out: list[dict[str, Any]] = []
    for raw in dicts(value):
        entry: dict[str, Any] = {}
        for field_name in fields:
            if field_name not in raw:
                continue
            raw_value = raw.get(field_name)
            entry[field_name[0].lower() + field_name[1:]] = (
                pick_str(raw_value)
                if isinstance(raw_value, str) and not _looks_numeric(raw_value)
                else stats.num(cls, f"{key}.{field_name}", raw_value)
            )
        out.append(entry)
    return out


def _looks_numeric(text: str) -> bool:
    try:
        float(text.strip())
    except ValueError:
        return False
    return True


def extract_events(
    package: Package, waves: dict[str, int], stats: Stats, sources: dict[str, list[str]]
) -> dict[str, Any] | None:
    tide: list[dict[str, Any]] = []
    for index, _obj in package.all_of(TIDE_CLS):
        data = package.objdata(index)
        alias = package.alias(index)
        sources.setdefault("events", []).append(package.ref(index))
        change = data.get("TidalChange") if isinstance(data.get("TidalChange"), dict) else {}
        tide.append(
            {
                "wave": wave_number(alias, waves, TIDE_CLS, stats),
                "alias": alias,
                "changeAmount": stats.num(TIDE_CLS, "ChangeAmount", change.get("ChangeAmount")),
                "changeType": pick_str(change.get("ChangeType")),
            }
        )

    frost: list[dict[str, Any]] = []
    for index, _obj in package.all_of(FROST_CLS):
        data = package.objdata(index)
        alias = package.alias(index)
        sources.setdefault("events", []).append(package.ref(index))
        frost.append(
            {
                "wave": wave_number(alias, waves, FROST_CLS, stats),
                "alias": alias,
                "winds": [
                    {
                        "direction": pick_str(raw.get("Direction")),
                        "row": stats.num(FROST_CLS, "Winds.Row", raw.get("Row")),
                    }
                    for raw in dicts(data.get("Winds"))
                ],
            }
        )

    if not tide and not frost:
        return None
    return {"tide": tide, "frost": frost, "strength": _event_strength(tide)}


def _event_strength(tide: list[dict[str, Any]]) -> float | None:
    """潮汐强度 = 所有 ``changeAmount`` 的绝对值之和（无潮汐则 ``None``）。"""
    total = 0.0
    seen = False
    for item in tide:
        amount = item.get("changeAmount")
        if isinstance(amount, (int, float)):
            total += abs(float(amount))
            seen = True
    return round(total, 4) if seen else None


def extract_mutators(
    package: Package, stats: Stats, sources: dict[str, list[str]]
) -> list[dict[str, Any]] | None:
    out: list[dict[str, Any]] = []
    for index, obj in enumerate(package.objects):
        objclass = obj.get("objclass")
        if not isinstance(objclass, str) or not objclass.startswith("LevelMutator"):
            continue
        data = package.objdata(index)
        sources.setdefault("mutators", []).append(package.ref(index))
        record: dict[str, Any] = {"objclass": objclass, "alias": package.alias(index)}
        for key, value in sorted(data.items()):
            if isinstance(value, str):
                name = rtid_name(value)
                if key == "MutatorTables":
                    record["mutatorTables"] = (value if isinstance(value, list) else [value])
                    continue
                record[key[0].lower() + key[1:]] = name or value
                continue
            if isinstance(value, list):
                entries: list[Any] = []
                for item in value:
                    if isinstance(item, dict):
                        entries.append({k: _mutator_scalar(v) for k, v in sorted(item.items())})
                    else:
                        entries.append(_mutator_scalar(item))
                record[key[0].lower() + key[1:]] = entries
                continue
            record[key[0].lower() + key[1:]] = stats.num(objclass, key, value)
        out.append(record)
    return out or None


def _mutator_scalar(value: Any) -> Any:
    if isinstance(value, str):
        return rtid_name(value) or value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, list):
        return [_mutator_scalar(item) for item in value]
    return value


def extract_board_grid(
    package: Package, sources: dict[str, list[str]]
) -> dict[str, Any] | None:
    body = package.one(BOARD_CLS)
    if body is None:
        return None
    index, _obj = body
    data = package.objdata(index)
    sources.setdefault("boardGrid", []).append(package.ref(index))
    values = data.get("Values")
    rows: list[list[int]] = []
    if isinstance(values, list):
        for row in values:
            if isinstance(row, list):
                rows.append([int(cell) for cell in row if isinstance(cell, (int, float))])
            elif isinstance(row, (int, float)):
                rows.append([int(row)])
    return {
        "alias": package.alias(index),
        "rows": rows,
        "height": len(rows),
        "width": max((len(row) for row in rows), default=0),
    }


# --------------------------------------------------------------------------- #
# 组装
# --------------------------------------------------------------------------- #


@dataclass
class Inventory:
    levels: int
    records: dict[str, dict[str, Any]]
    counts: dict[str, Any]
    unknowns: list[dict[str, Any]]
    sentinels: list[dict[str, Any]]
    coerced: list[dict[str, Any]]


def build(
    levels_dir: Path,
    obb_dir: Path,
    *,
    package_index: dict[str, list[Path]] | None = None,
) -> Inventory:
    client = load_client_levels(levels_dir)
    index = package_index if package_index is not None else index_packages(obb_dir)
    stats = Stats()

    records: dict[str, dict[str, Any]] = {}
    counters: Counter = Counter()
    shared_packages: dict[str, list[str]] = {}
    missing_packages: list[str] = []
    ambiguous_packages: dict[str, list[str]] = {}
    unparsable: list[str] = []
    no_package: list[str] = []
    declared_but_empty: Counter = Counter()

    for item in client:
        record: dict[str, Any] = {name: None for name in MECHANICS}
        record["source"] = {"package": None, "objects": {}}
        if not item.package:
            no_package.append(item.level_id)
            records[item.level_id] = record
            continue
        paths = index.get(item.package, [])
        if not paths:
            missing_packages.append(item.level_id)
            records[item.level_id] = record
            continue
        if len(paths) > 1:
            ambiguous_packages[item.package] = [str(p) for p in paths]
        shared_packages.setdefault(item.package, []).append(item.level_id)
        path = paths[0]
        doc = load_package(path)
        if doc is None:
            unparsable.append(item.level_id)
            records[item.level_id] = record
            continue
        package = Package(path, doc)
        waves = package.wave_map()
        sources: dict[str, list[str]] = {}
        record["source"] = {"package": path.name, "objects": sources}

        record["conveyor"] = extract_conveyor(package, waves, stats, sources)
        if package.one(CONVEYOR_CLS) is not None:
            counters["conveyorSeedBank"] += 1
        record["initialPlants"] = extract_initial_plants(package, stats, sources)
        record["initialGridItems"] = extract_initial_grid_items(package, stats, sources)
        record["protectThePlant"] = extract_protect(package, stats, sources)
        record["spawners"] = extract_spawners(package, waves, stats, sources)
        record["events"] = extract_events(package, waves, stats, sources)
        record["mutators"] = extract_mutators(package, stats, sources)
        record["boardGrid"] = extract_board_grid(package, sources)

        declared = package.declared_modules()
        for name in MECHANICS:
            if record[name] is not None:
                counters[name] += 1
            elif name in _MODULE_NAMES:
                if any(module in declared for module in _MODULE_NAMES[name]):
                    counters[f"{name}DeclaredOnly"] += 1
                    declared_but_empty[name] += 1
        if record["conveyor"] is not None and record["conveyor"].get("changes"):
            counters["conveyorChanges"] += 1
        if record["initialGridItems"] is not None and record["initialGridItems"].get("placements"):
            counters["gridItemPlacements"] += 1
        if record["initialGridItems"] is not None and record["initialGridItems"].get("gravestones"):
            counters["gravestones"] += 1
        if record["spawners"] is not None:
            for kind, items in record["spawners"].items():
                if items:
                    counters[f"spawner_{kind}"] += 1
        records[item.level_id] = record

    # ---- counts ----
    all_null = [
        level_id
        for level_id, record in records.items()
        if all(record[name] is None for name in MECHANICS)
    ]
    # ---- protect 审计（报告第七节「保护目标的三个口径」）----
    protect_modules = 0
    module_equal = 0
    module_fewer = 0
    must_gt_distinct: list[dict[str, Any]] = []
    multi_module: list[dict[str, Any]] = []
    level_values: dict[str, int] = {}
    for level_id, record in records.items():
        payload = record.get("protectThePlant")
        if not payload:
            continue
        modules = payload.get("modules") or []
        protect_modules += len(modules)
        plants = payload.get("plants") or []
        must = payload.get("mustProtectCount")
        cells = {(plant.get("gridX"), plant.get("gridY")) for plant in plants}
        if len(modules) > 1:
            multi_module.append(
                {
                    "level": level_id,
                    "modules": [module.get("alias") for module in modules],
                    "plantCounts": [module.get("plants") for module in modules],
                    "plants": len(plants),
                    "mustProtectCount": must,
                    "cells": len(cells),
                }
            )
        for module in modules:
            module_must = module.get("mustProtectCount")
            if not isinstance(module_must, (int, float)):
                continue
            if module_must == module.get("plants"):
                module_equal += 1
            elif module_must < module.get("plants"):
                module_fewer += 1
        if isinstance(must, (int, float)) and must > len(cells):
            must_gt_distinct.append(
                {
                    "level": level_id,
                    "mustProtectCount": int(must),
                    "plants": len(plants),
                    "cells": len(cells),
                }
            )
        for plant in plants:
            level_value = plant.get("level")
            if level_value is None:
                continue
            level_values[str(level_value)] = level_values.get(str(level_value), 0) + 1

    counts: dict[str, Any] = {
        "levels": len(records),
        "clientLevels": len(client),
        "withConveyor": counters["conveyor"],
        "withConveyorSeedBank": counters["conveyorSeedBank"],
        "withConveyorChanges": counters["conveyorChanges"],
        "withInitials": counters["initialPlants"],
        "withInitialGridItems": counters["initialGridItems"],
        "withGridItemPlacements": counters["gridItemPlacements"],
        "withGravestones": counters["gravestones"],
        "withProtect": counters["protectThePlant"],
        "protect": {
            "modules": protect_modules,
            "moduleEqualPlants": module_equal,
            "moduleFewerPlants": module_fewer,
            "multiModuleLevels": multi_module,
            "mustGtDistinct": must_gt_distinct,
            "levelValues": dict(sorted(level_values.items(), key=lambda kv: (-kv[1], kv[0]))),
        },
        "withSpawners": counters["spawners"],
        "spawnerByKind": {
            kind: counters[f"spawner_{kind}"]
            for kind in sorted(SPAWNER_CLASSES)
            if counters[f"spawner_{kind}"]
        },
        "withEvents": counters["events"],
        "withMutators": counters["mutators"],
        "withBoardGrid": counters["boardGrid"],
        "levelsAllNull": len(all_null),
        "levelsAllNullSamples": sorted(all_null)[:12],
        "declaredOnly": {name: count for name, count in sorted(declared_but_empty.items())},
        "packagesResolved": sum(1 for item in client if item.package and item.package in index),
        "packagesMissing": len(missing_packages),
        "packagesShared": sum(
            1 for levels in shared_packages.values() if len(levels) > 1
        ),
        "packagesAmbiguous": len(ambiguous_packages),
        "levelsWithoutPackage": len(no_package),
        "levelsUnparsable": len(unparsable),
        "unknownMechanics": 0,
        "sentinels": sum(stats.sentinels.values()),
        "coercedHits": sum(stats.coerced.values()),
        "waveResolved": sum(stats.wave_hit.values()),
        "waveUnresolved": sum(stats.wave_miss.values()),
        "emptyObjdata": sum(stats.empty_objdata.values()),
    }

    unknowns: list[dict[str, Any]] = []
    if missing_packages:
        unknowns.append(
            {
                "kind": "package-missing",
                "detail": f"{len(missing_packages)} 关的 extra.package 在 work/obb_packages 找不到对应文件",
                "levels": missing_packages[:20],
                "count": len(missing_packages),
                "probe": "确认 OBB 是否完整解包；缺包的关卡所有机制为 null",
            }
        )
    if shared_packages and counts["packagesShared"]:
        shared = {k: v for k, v in shared_packages.items() if len(v) > 1}
        unknowns.append(
            {
                "kind": "package-shared",
                "detail": (
                    f"{len(shared)} 个包被多关共用：身份锚点是包名而非关卡号，"
                    "共用包的多关会得到完全相同的机制数据"
                ),
                "levels": sorted({lid for ids in shared.values() for lid in ids})[:20],
                "count": len(shared),
                "probe": "检查这些关卡是否本来就是同一份定义（复刻/教学关），或 extra.package 写错",
            }
        )
    if ambiguous_packages:
        unknowns.append(
            {
                "kind": "package-ambiguous",
                "detail": f"{len(ambiguous_packages)} 个包名匹配到多个文件，取字典序第一个",
                "levels": sorted(ambiguous_packages)[:10],
                "count": len(ambiguous_packages),
                "probe": "按 objclass 是否含 LevelDefinition 逐个核对，必要时改成显式白名单",
            }
        )
    if no_package:
        unknowns.append(
            {
                "kind": "no-package",
                "detail": f"{len(no_package)} 关的 extra 里没有 package 字段",
                "levels": sorted(no_package)[:20],
                "count": len(no_package),
                "probe": "确认这些关卡是否来自别的数据源（测试关/占位关）",
            }
        )
    if unparsable:
        unknowns.append(
            {
                "kind": "package-unparsable",
                "detail": f"{len(unparsable)} 关的包文件不是合法 JSON",
                "levels": sorted(unparsable)[:20],
                "count": len(unparsable),
                "probe": "重跑解包；若文件只有 #comment，说明是空壳包",
            }
        )
    for cls, misses in sorted(stats.wave_miss.items()):
        if not misses:
            continue
        unknowns.append(
            {
                "kind": "wave-unresolved",
                "detail": (
                    f"{cls} 有 {misses} 个对象的 alias 既不在 WaveManagerProperties.Waves 里、"
                    f"也不符合 Wave<N> 形态，wave 记为 null"
                ),
                "samples": stats.wave_miss_samples.get(cls, []),
                "count": misses,
                "probe": "打印该包 Waves 的完整 alias 列表，确认是否走 -1/隐藏波次",
            }
        )
    if stats.empty_objdata:
        unknowns.append(
            {
                "kind": "empty-objdata",
                "detail": "以下类的对象 objdata 为空对象，只能记录存在性",
                "counts": {cls: count for cls, count in sorted(stats.empty_objdata.items())},
                "count": sum(stats.empty_objdata.values()),
                "probe": "对照同关其它对象确认是「清空」还是解包丢失",
            }
        )
    mutator_classes = sorted(
        {
            record["objclass"]
            for payload in records.values()
            for record in (payload.get("mutators") or [])
        }
    )
    if len(mutator_classes) < 3:
        unknowns.append(
            {
                "kind": "mutator-coverage",
                "detail": f"level 文件里只出现 {len(mutator_classes)} 类 LevelMutator*",
                "count": len(mutator_classes),
                "probe": "其余 LevelMutator* 类可能在 non-level 包里，需要扩包扫描",
            }
        )
    unknowns.append(
        {
            "kind": "protect-failure-rule",
            "detail": (
                "ProtectThePlantChallengeProperties 没有显式失败动作，"
                "原版由引擎在受保护植物消失时判负；本表只导出 mustProtectCount 与 plants，"
                "并在 payload 里用 failWhenProtectedPlantDiesSource=\"client-default\" "
                "标明 failWhenProtectedPlantDies 是编译端约定而不是原表字段"
            ),
            "count": counts["withProtect"],
            "probe": "在引擎侧实现「受保护植物死亡即判负」，不要等数据里的失败字段",
        }
    )
    counts["unknownMechanics"] = len(unknowns)

    sentinels = [
        {
            "objclass": cls,
            "key": key,
            "value": value,
            "count": count,
        }
        for (cls, key, value), count in sorted(stats.sentinels.items())
    ]
    coerced = [
        {"objclass": cls, "key": key, "kind": kind, "count": count}
        for (cls, key, kind), count in sorted(stats.coerced.items(), key=lambda kv: (-kv[1], kv[0]))
    ]

    return Inventory(
        levels=len(records),
        records=records,
        counts=counts,
        unknowns=unknowns,
        sentinels=sentinels,
        coerced=coerced,
    )


#: 机制名 -> 原版模块名（用于"声明了但没参数"的统计）。
_MODULE_NAMES: dict[str, tuple[str, ...]] = {
    "conveyor": ("ConveyorBelt",),
    "initialPlants": ("InitialPlant",),
    "initialGridItems": ("Gravestones", "GridItems"),
    "protectThePlant": ("ProtectThePlant",),
    "events": ("Tide", "FrostWind"),
    "mutators": ("LevelMutator",),
    "boardGrid": ("BoardGridMap",),
}


def field_default() -> Counter:  # pragma: no cover - 兼容旧签名
    return Counter()


# --------------------------------------------------------------------------- #
# 渲染
# --------------------------------------------------------------------------- #


def render_json(inv: Inventory) -> str:
    doc = {
        "format": FORMAT,
        "generated": GENERATED,
        "counts": inv.counts,
        "levels": inv.records,
        "sentinels": inv.sentinels,
        "coerced": inv.coerced,
        "unknowns": inv.unknowns,
    }
    # 紧凑 JSON：不缩进、不留空格。18709 个记录里 12 万条 spawner 池条目，缩进会多占三成；
    # `--check` 用的是同一个 dumper，所以字节确定性契约不变。
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _table(header: list[str], rows: Iterable[Iterable[Any]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def _sentinel_split(rows: Iterable[dict[str, Any]]) -> str:
    """把哨兵按值拆开，避免读者以为 `2147483647` 也在表里。"""
    totals: dict[int, int] = {}
    for row in rows:
        totals[row["value"]] = totals.get(row["value"], 0) + row["count"]
    return "、".join(f"`{value}` {totals.get(value, 0)} 处" for value in SENTINELS)


def render_report(inv: Inventory) -> str:
    counts = inv.counts
    lines: list[str] = [
        "# 关卡机制编译（T51）",
        "",
        "把 1809 关的关卡机制从原版 `LevelDefinition` 包编译成一份客户端可读的表。"
        "生成的 `native/generated/level_mechanics.json` 是**数据**，不含任何逻辑；"
        "引擎侧按 `levels[levelId][mechanic]` 取用，`null` 表示这一关没有该机制。",
        "",
        "## 一、身份映射（先看这节）",
        "",
        "客户端 `content/levels/*.json` 的 `extra.package` 形如 `\"pkg_0264\"`，"
        "直接对应 `work/obb_packages/pkg_0264_LevelDefinition.json`。",
        "",
        "实测：",
        "",
        f"- 客户端关卡 {counts['clientLevels']} 个，`extra.package` 命中包文件 "
        f"{counts['packagesResolved']} 个；缺文件 {counts['packagesMissing']} 个、"
        f"无 package 字段 {counts['levelsWithoutPackage']} 个、解析失败 {counts['levelsUnparsable']} 个。",
        f"- 同一个包被多关共用：{counts['packagesShared']} 例（见 `unknowns` 里的 `package-shared`）。"
        "共用包的多关拿到的是同一份机制数据 —— 这是锚点选择的直接后果，不是缺失。",
        f"- 包名撞车（一个 stem 匹配多个文件）：{counts['packagesAmbiguous']} 例。",
        "",
        "**不要用 `StageModule` + `LevelNumber` 当锚点**：那对键在 1809 关里只有 1385 个"
        "不同值，1809 -> 1385 不唯一（t37 已确认），用它会把不同关卡的机制搅在一起。",
        "",
        "## 二、覆盖（实测计数）",
        "",
    ]
    lines += _table(
        ["机制", "关数", "原版对象", "备注"],
        [
            ["`conveyor`", counts["withConveyor"], "`ConveyorSeedBankProperties`", f"其中 {counts['withConveyorSeedBank']} 关有卡槽表、{counts['withConveyorChanges']} 关有 `ModifyConveyorWaveActionProps` 改动波"],
            ["`initialPlants`", counts["withInitials"], "`InitialPlantProperties`", "含 `InitialPlantPlacements`"],
            ["`initialGridItems`", counts["withInitialGridItems"], "`InitialGridItemProperties` + `GravestoneProperties`", f"其中 {counts['withGridItemPlacements']} 关有格位摆放、{counts['withGravestones']} 关有墓碑对象"],
            [
            "`protectThePlant`",
            counts["withProtect"],
            "`ProtectThePlantChallengeProperties`",
            f"同包多模块已合并（{counts['protect']['modules']} 个模块）；失败判定在引擎侧，见第七节",
        ],
            ["`spawners`", counts["withSpawners"], "8 类生成器 + `gravestone` + `jittered`", "`spawners.<kind>[]` 逐条，`jittered` 是聚合摘要（见下）"],
            ["`events`", counts["withEvents"], "`TidalChangeWaveActionProps` / `FrostWindWaveActionProps`", "潮汐取 `changeAmount` 绝对值之和当强度"],
            ["`mutators`", counts["withMutators"], "`LevelMutator*`", "level 文件里只出现 3 类"],
            ["`boardGrid`", counts["withBoardGrid"], "`BoardGridMapProps`", "`Values` 是 0/1 矩阵，用于非标准行数"],
        ],
    )
    by_kind = counts.get("spawnerByKind") or {}
    lines += [
        "",
        "生成器按类的关卡数（一个关卡可以有多类）：",
        "",
    ]
    lines += _table(
        ["`spawners.<kind>`", "关数", "原版类"],
        [[f"`{kind}`", count, f"`{SPAWNER_CLASSES[kind]}`"] for kind, count in by_kind.items()],
    )
    lines += [
        "",
        "> 任务列了八类生成器。实测必须多带两类，否则数据会看起来「缺一大块」：",
        "> `gravestone`（墓石生成）与 `jittered`（普通波次的主力 —— 不加它，"
        f"{counts['levelsAllNull']} 个关卡的僵尸就凭空消失）。两类都放在 `spawners` 子键里，"
        "不额外占顶层机制键。",
        "",
        "**`spawners.jittered` 是聚合摘要，其余九类是逐条列表。** "
        "`jittered` 在 1615 关里共 12 万条僵尸条目，逐条落盘会让产物到 17 MB；"
        "而这个池不是权重表 —— 同一个 id 出现 N 次就是 N 只，所以压成 "
        "`{objects, total, waves{波号: 对象数}, waveUnresolved, pool{zombieId: {count, rows}}}` "
        "与原表信息等价，引擎按 `count` 抽即可（`rows` 是该 id 出现过的行号，原版多数条目不带行号，"
        "所以缺行号时没有这个键）。其余机制（conveyor / initialPlants / initialGridItems / "
        "protect / events / mutators / boardGrid 与剩下九类生成器）**一个字都没裁**。",
        "",
        f"**八机制全为 null 的关卡：{counts['levelsAllNull']} / {counts['levels']}**"
        f"（样例：{'、'.join('`' + x + '`' for x in counts['levelsAllNullSamples'])}）。",
        "这些关卡的玩法不在本节导出的 8 类里（选关/演示/纯 seed-bank 关），"
        "不是映射失败 —— 它们的包文件确实只有 `LevelDefinition` + `SeedBankProperties` + "
        "`WaveManagerModuleProperties`。",
        "",
        f"合计 `unknownMechanics` = {counts['unknownMechanics']} 条（见第六节）。",
        "",
        "## 三、波次归属",
        "",
        "`WaveManagerProperties.Waves` 是 `list[list[RTID(alias@CurrentLevel)]]`，"
        "`Waves[i]` 就是第 `i+1` 波的 action 列表，所以 alias -> 波号是直接映射。"
        "alias 不符合 `Wave<N>` 形态再退回正则取第一个数字。",
        "",
        f"- 解析成功 {counts['waveResolved']} 个对象，失败 {counts['waveUnresolved']} 个（`wave: null`，进 `unknowns`）。",
        "- 失败集中在 `DinoWaveActionProps`（alias 如 `sweep1`）与 `SpawnGravestonesWaveActionProps`"
        "（alias 如 `GraveSpawnEventX`）：这些 action 由模块自己的脚本触发，不在 `Waves` 里。",
        "",
        "## 四、哨兵值与数值字符串",
        "",
        f"哨兵命中 **{counts['sentinels']}** 处（{_sentinel_split(inv.sentinels)}），"
        "原样保留，未替换成缺失。按对象类与字段排序前 15：",
        "",
    ]
    lines += _table(
        ["对象类", "字段", "值", "次数"],
        [
            [f"`{row['objclass']}`", f"`{row['key']}`", row["value"], row["count"]]
            for row in inv.sentinels[:15]
        ],
    )
    lines += [
        "",
        f"数值被写成字符串的字段 **{counts['coercedHits']}** 处，编译时 coerce 成数字。前 15：",
        "",
    ]
    lines += _table(
        ["对象类", "字段", "类型", "次数"],
        [
            [f"`{row['objclass']}`", f"`{row['key']}`", row["kind"], row["count"]]
            for row in inv.coerced[:15]
        ],
    )
    lines += [
        "",
        "**哨兵是 coerce 之后再判的**：原版把 `-1` 有时写成整数、有时写成字符串 `\"-1\"`"
        "（如 `InitialPlantProperties.InitialPlantPlacements[].Level`），"
        "两者都会计入上表同一个 `value: -1`。表里的数一律原样保留，没有替换成 `null`。",
        "",
        "**引用值原样保留为 RTID 字符串**（如 `\"RTID(atlantis@ZombieTypes)\"`）：编译时不剥表名，"
        "避免丢信息；需要短名时用仓库现有的 `tools/contentc/rtid.py`。植物类字段（`plant`）"
        "在原版里本来就是裸名字，所以两种形态会同时出现 —— 这是源数据的形状，不是编译错误。",
        "",
        "## 五、引擎接线最小闭环（先做哪三个）",
        "",
        "按「改一行数据就能让这一关看起来像原版」排序，成本从低到高：",
        "",
        f"1. **`initialGridItems`（{counts['withInitialGridItems']} 关）** —— 只有坐标 + 物件名，"
        "引擎只要有「在 (x,y) 放一个 grid item」就够。墓碑（`gravestones[].forceSpawn[]`）同构，"
        f"一次接线同时解锁 {counts['withGravestones']} 关的墓碑布局。**投入最小、覆盖面最大。**",
        f"2. **`conveyor`（{counts['withConveyor']} 关）** —— 槽位是 `{{plant, weight, min/maxCount, 冷却}}` 的"
        "加权随机表，引擎侧只需要一个「按权重抽卡、按冷却补充」的循环；"
        f"改动波（{counts['withConveyorChanges']} 关）在同一结构里按 `wave` 套用，不用另写。",
        f"3. **`protectThePlant`（{counts['withProtect']} 关）** —— 数据侧只有「保护哪几株、共 N 株」，"
        "失败判定由引擎在受保护植物消失时触发，**不需要新渲染路径**，是纯规则接线。",
        "",
        "`spawners` 数值最全但成本最高（8 类 + 池结构，每类都要在波次调度里落位），"
        "建议放到第三批；`boardGrid` 只有 "
        f"{counts['withBoardGrid']} 关，最后做。",
        "",
        "## 六、unknowns 与探针",
        "",
    ]
    for row in inv.unknowns:
        levels = row.get("levels") or row.get("samples") or []
        sample = "、".join(f"`{x}`" for x in levels[:6])
        lines.append(
            f"- **`{row['kind']}`**（{row['count']}）：{row['detail']}"
            + (f"；样例 {sample}。" if sample else "。")
            + f" 探针：{row['probe']}"
        )
    audit = counts["protect"]
    level_text = (
        "、".join(f"`{value}`×{count}" for value, count in audit["levelValues"].items()) or "（无）"
    )
    gt_rows = audit["mustGtDistinct"]
    gt_text = "、".join(
        f"`{row['level']}`（must {row['mustProtectCount']} / {row['plants']} 株 / {row['cells']} 格）"
        for row in gt_rows
    ) or "（无）"
    merge_rows = audit["multiModuleLevels"]
    merge_text = "；".join(
        "`" + row["level"] + "`："
        + " + ".join("`" + str(alias) + "`" for alias in row["modules"])
        + "（" + " + ".join(str(n) for n in row["plantCounts"]) + " 株）"
        + f" → 合并 {row['plants']} 株 / {row['cells']} 个不同格 / must {row['mustProtectCount']}"
        for row in merge_rows
    ) or "（全库没有多模块关卡）"
    lines += [
        "",
        "## 七、保护目标的三个口径",
        "",
        "`protectThePlant` 里有三个容易混的数字：原表 `mustProtectCount`（阈值）、`Plants` 的**条目数**、"
        "以及按坐标去重后的**格子数**。引擎判定用第一个；用后两个推都会偏。",
        "",
        f"1. **`mustProtectCount` vs 条目数**：{audit['modules']} 个 protect 模块里，「`must` 等于条目数」"
        f"{audit['moduleEqualPlants']} 个、「`must` 小于条目数」{audit['moduleFewerPlants']} 个、"
        "「`must` 大于条目数」**0 个**。"
        "所以 `must` 是阈值而不是总数：小的那 "
        f"{audit['moduleFewerPlants']} 个模块是「列了 N 格候选、只需守住其中 M 格」。",
        f"2. **`must` vs 不同格子数**：`must` 严格大于去重格子数的关卡 {len(gt_rows)} 个 —— {gt_text}。"
        "这 5 关里同一格出现多条记录，是因为原表用 `Level` 区分**同一格的层**"
        "（地面层/植物层），一格里能站着多株受保护植物；不是重复行，也不是脏数据。",
        f"3. **`Level` 是层号（推断）**：取值分布 {level_text}。"
        "证据是它只出现在 124/963 条记录上、且与坐标正交（`lostcity_67` 就是 protect "
        "`Level=-1` 与 initialPlant `Level=1` 落在同格）；把它当坐标会算出重复格子。"
        "注意编译期已把数字字符串 coerce 成数字，所以原表的 `'1'` 与 `1` 在这里并成一档。",
        "",
        f"**多保护模块的合并**（{len(merge_rows)} 个关卡）：{merge_text}。"
        "原版一个 package 可以挂多个 `ProtectThePlantChallengeProperties`，且它们的别名同时出现在"
        "同一个 `LevelDefinition.Modules` 里 —— 是**并发**要求，不是备选。旧实现 `package.one()` 只取"
        "第一个，`lostcity_46` 因此只剩 2 株；现在按对象顺序拼接 `plants`（每条带 `module` 标明来源）、"
        "`mustProtectCount` 各模块相加，并在 `modules` 里留下每个模块的 `objects[i]` 出处。",
        "",
        "**`failWhenProtectedPlantDies` 是客户端约定**：原表没有这个开关（t56 已核对字段级差距），"
        "是我们「受保护植物死亡即判负」的语义选择。它必须留着，所以 payload 里额外带 "
        "`\"failWhenProtectedPlantDiesSource\": \"client-default\"` —— 以后做字段级对照时，"
        "别把这个键当成原版字段捡回去。",
        "",
        "## 八、复现",
        "",
        "```",
        "python tools/contentc/mechanics.py            # 生成 json + 本报告",
        "python tools/contentc/mechanics.py --check    # 逐字节校验产物是否最新",
        "python tools/contentc/mechanics.py -n         # 只打印摘要",
        "python -m unittest discover -s tools/tests -p 'test_*.py'",
        "```",
        "",
        "`generated` 字段是固定常量而不是运行时时钟，否则 `--check` 永远失败。",
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
    counts = inv.counts
    parts = [f"levels={counts['levels']}"]
    for key in (
        "withConveyor",
        "withInitials",
        "withInitialGridItems",
        "withGravestones",
        "withProtect",
        "withSpawners",
        "withEvents",
        "withMutators",
        "withBoardGrid",
    ):
        parts.append(f"{key}={counts[key]}")
    parts.append(f"unknowns={counts['unknownMechanics']}")
    parts.append(f"sentinels={counts['sentinels']}")
    parts.append(f"waveUnresolved={counts['waveUnresolved']}")
    return " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="编译关卡机制表")
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
