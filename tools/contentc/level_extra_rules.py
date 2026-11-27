"""逐关扩展规则表编译器：把我方引擎尚未接线的七类关卡机制参数抽成一张可接线的表。

输出 ``native/generated/level_extra_rules.json``，供引擎接线时只读表、不再回头翻 OBB。

口径（R01..R09）
---------------
R01 **来源**：只读 460.9 的 ``work/obb_packages``（``LevelDefinition`` 所在包）+ ``content/levels``
    的 ``extra``。仓库里其它 generated 产物一律不读 —— 本表是独立事实，不复述别人算过的数。
R02 **boardGrid 的真实类名是 ``BoardGridMapProps``**，唯一字段 ``Values`` 是 5 行 × 9 列的格码矩阵。
    该关的 ``MoldColonyChallengeProps.Locations`` 会以 ``RTID(<alias>@CurrentLevel)`` 指回同一张图；
    两者都写进产物，坐标语义原样保留（0/1 的含义原版没有字段说明，产物不翻译）。
R03 **mutators 就是全部 ``LevelMutator*`` 对象**（14 个类）。只铺平**标量**：字符串经 ``RTID`` 归一成
    别名，列表里的对象逐项铺平，键名首字母小写（与 ``components/level_mechanics`` 的写法一致）。
    嵌套字典原样递归铺平；不做任何「这个倍率乘什么」的解释。
R04 **night 没有 ``NightModule`` 这类模块**。原版的夜战信号有三处：``content`` 的 ``extra.night``
    （由关卡名/模块名推导）、关卡 ``StageModule`` 指向的 stage 属性对象、以及**有没有挂
    ``DefaultSunDropper``**（没挂＝天上不掉阳光，这是原版表达「夜战不送阳光」的方式）。
    墓碑节奏来自 ``SpawnGravestonesWaveActionProps``，从别名 ``Wave<N>GravestoneEvent`` 取波次。
    「天黑时间点」原版没有字段，产物不造。
R05 **frost** = ``FrostWindWaveActionProps``：``Winds[]`` 每项只有 ``Direction`` 与 ``Row``
    （``Row`` 允许 -1＝整行，RTON 里既有整数也有字符串，统一转数值并记 ``rowsRaw`` 原样）。
R06 **tide** = ``TidalChangeWaveActionProps``（``TidalChange.{ChangeAmount,ChangeType}``）+
    ``TideProperties.{StartingWaveLocation,ShowTideMarker}`` + ``TideWaveWaveActionProps``（潜艇/加速）。
    ``tide`` 块的**判定门槛是有 TidalChange 事件**（与 ``level_playability`` 的 ``events.tide``
    60 关逐关对齐）；只有 ``TideProperties`` 而没有涨落事件的 20 关记进 ``unknowns``，不硬塞进 tide。
R07 **strength 不是原版字段**：它是 ``TidalChange.ChangeAmount`` 取绝对值求和（``round(x,4)``，
    与 ``tools/contentc/mechanics.py:851 _event_strength`` 同一口径）的**派生量**，产物里带
    ``derivedFrom`` 写明。
R08 **``generated`` 是内容寻址戳** ``sha256:<16>``：对「除 generated 之外的整份载荷」的规范
    紧凑 JSON 取 sha256 前 16 位。禁墙钟、禁 mtime —— 任何机器上重建都得到同一串，``--check``
    才能逐字节比较。写法参照 ``tools/contentc/shop_unlock.py`` 的 ``generated_stamp``。
R09 **不编数值**：解析不出的东西进 ``unknowns``（每条形如 ``{kind, detail, probe}``），
    该关该块直接缺省；缺省不等于 0，也不补默认值。``sources`` 只写相对路径，不泄露本机路径。

用法::

    python tools/contentc/level_extra_rules.py            # 重新生成
    python tools/contentc/level_extra_rules.py --check    # 逐字节校验（过期 exit 1）
    python tools/contentc/level_extra_rules.py -n Winds   # 全库键名/类名检索
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from contentc import s5scan  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEVELS = ROOT / "content" / "levels"
DEFAULT_OBB = Path(
    os.environ.get("PVZ2_OBB_DIR")
    or (ROOT.parent.parent / "work" / "obb_packages")
)
DEFAULT_OUT = ROOT / "native" / "generated" / "level_extra_rules.json"

FORMAT = "pvz2-shuttle/level-extra-rules@1"
GENERATOR = "level_extra_rules"

#: 参与本表的类（R02..R07）。
BOARD_CLS = "BoardGridMapProps"
MOLD_CLS = "MoldColonyChallengeProps"
GRIDITEM_CLS = "InitialGridItemProperties"
GRAVE_CLS = "SpawnGravestonesWaveActionProps"
FROST_CLS = "FrostWindWaveActionProps"
TIDE_CHANGE_CLS = "TidalChangeWaveActionProps"
TIDE_PROPS_CLS = "TideProperties"
TIDE_WAVE_CLS = "TideWaveWaveActionProps"
STAGE_PROPS_SUFFIX = "StageProperties"

#: 夜战用到的模块名（R04）：有没有这些模块是数据事实。
SKY_SUN_MODULE = "DefaultSunDropper"
NIGHT_MODULES = ("MarketNight", "HeianNight", "NightStageMusic")

WAVE_RE = re.compile(r"Wave(\d+)")
RTID_RE = re.compile(r"^RTID\((?P<inner>.+)\)$")

_CACHE: dict[str, object] = {}


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #


def load_json(path: Path) -> object:
    key = str(path)
    if key not in _CACHE:
        _CACHE[key] = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return _CACHE[key]


def rtid_name(value: object) -> str | None:
    """'RTID(wave_egyptnight@GridItemTypes)' -> 'wave_egyptnight'；非 RTID 原样返回。"""
    if not isinstance(value, str):
        return None
    match = RTID_RE.match(value.strip())
    if not match:
        return value
    return match.group("inner").split("@", 1)[0]


def package_stem(name: object) -> str:
    """'pkg_0290' 与 'pkg_0290_LevelDefinition.json' 都归一到 'pkg_0290'。"""
    return str(name or "").split(".")[0].split("_LevelDefinition")[0]


def num(value: object) -> float | int | None:
    """RTON 里既有数字也有数字字符串（'4'、'0.5'）；统一成数值，转不出就 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return None
    return None


def wave_of(alias: object) -> int | None:
    match = WAVE_RE.search(str(alias or ""))
    return int(match.group(1)) if match else None


def camel(key: str) -> str:
    return key[0].lower() + key[1:] if key[:1].isupper() else key


def flatten(value: object, key: str) -> object:
    """按 R03 铺平：标量原样、RTID 归一、列表逐项、字典递归、键名小写长头。"""
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        name = rtid_name(value)
        return name if name is not None else value
    if isinstance(value, list):
        return [flatten(item, key) for item in value]
    if isinstance(value, dict):
        return {camel(k): flatten(v, k) for k, v in sorted(value.items())}
    return None


def flatten_objdata(data: dict) -> dict:
    out: dict[str, object] = {}
    for key, value in sorted(data.items()):
        if key.startswith("#"):  # 原版注释键不是数据
            continue
        out[camel(key)] = flatten(value, key)
    return out


# --------------------------------------------------------------------------- #
# package index
# --------------------------------------------------------------------------- #


def package_paths(obb: Path) -> list[Path]:
    return s5scan.package_paths(obb)


def index_packages(paths: list[Path]) -> dict[str, dict[str, list[dict]]]:
    """pkg stem -> {objclass -> [{alias, data}]}，只收本表关心的类。"""
    wanted = {
        BOARD_CLS,
        MOLD_CLS,
        GRIDITEM_CLS,
        GRAVE_CLS,
        FROST_CLS,
        TIDE_CHANGE_CLS,
        TIDE_PROPS_CLS,
        TIDE_WAVE_CLS,
        "LevelDefinition",
    }
    index: dict[str, dict[str, list[dict]]] = {}
    for path in paths:
        try:
            doc = s5scan.load_package(path)
        except Exception:  # noqa: BLE001 - 坏包跳过但记进 unknowns（见 build）
            continue
        stem = package_stem(path.name)
        bucket: dict[str, list[dict]] = defaultdict(list)
        for obj in doc.get("objects") or []:
            cls = obj.get("objclass") or ""
            aliases = [a for a in (obj.get("aliases") or []) if isinstance(a, str)]
            alias = aliases[0] if aliases else ""
            if cls in wanted or cls.startswith("LevelMutator") or cls.endswith(STAGE_PROPS_SUFFIX):
                bucket[cls].append({"alias": alias, "data": obj.get("objdata") or {}})
        index[stem] = bucket
    return index


def alias_table(index: dict[str, dict[str, list[dict]]]) -> dict[str, tuple[str, str]]:
    """alias -> (objclass, pkg stem)，用来解析 StageModule 指向的 stage 属性对象。"""
    table: dict[str, tuple[str, str]] = {}
    for stem, bucket in index.items():
        for cls, rows in bucket.items():
            for row in rows:
                alias = row["alias"]
                if alias and alias not in table:
                    table[alias] = (cls, stem)
    return table


def level_rows(levels_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted(Path(levels_dir).glob("*.json")):
        doc = load_json(path)
        extra = doc.get("extra") or {}
        lid = doc.get("id") or path.stem
        out[lid] = {
            "id": lid,
            "package": package_stem(extra.get("package")),
            "file": f"content/levels/{path.name}",
            "night": bool(extra.get("night")),
            "stage": extra.get("stage"),
            "name": doc.get("name"),
        }
    return out


# --------------------------------------------------------------------------- #
# per-mechanism extractors
# --------------------------------------------------------------------------- #


def cells_by_code(rows: list[list[int]]) -> dict[str, list[list[int]]]:
    """格码 -> 坐标列表（x=列，y=行），按格码升序；坐标顺序按行遍历。"""
    buckets: dict[int, list[list[int]]] = defaultdict(list)
    for y, row in enumerate(rows):
        for x, code in enumerate(row):
            buckets[int(code)].append([x, y])
    return {str(code): buckets[code] for code in sorted(buckets)}


def board_grid_block(bucket: dict[str, list[dict]]) -> dict | None:
    maps = bucket.get(BOARD_CLS) or []
    if not maps:
        return None
    blocks = []
    for row in maps:
        values = row["data"].get("Values") or []
        rows: list[list[int]] = []
        for line in values:
            if isinstance(line, list):
                rows.append([int(cell) for cell in line if isinstance(cell, (int, float))])
        hist = Counter(int(cell) for line in rows for cell in line)
        blocks.append(
            {
                "class": BOARD_CLS,
                "alias": row["alias"],
                "height": len(rows),
                "width": max((len(line) for line in rows), default=0),
                "rows": rows,
                "cellCounts": {str(k): hist[k] for k in sorted(hist)},
                "cellsByCode": cells_by_code(rows),
            }
        )
    block: dict = {"maps": blocks}
    mold = bucket.get(MOLD_CLS) or []
    if mold:
        block["moldChallenge"] = [
            {
                "class": MOLD_CLS,
                "alias": row["alias"],
                "locations": rtid_name(row["data"].get("Locations")),
            }
            for row in mold
        ]
    items = bucket.get(GRIDITEM_CLS) or []
    if items:
        placements: list[dict] = []
        for row in items:
            for entry in row["data"].get("InitialGridItemPlacements") or []:
                if not isinstance(entry, dict):
                    continue
                placements.append(
                    {
                        "type": rtid_name(entry.get("TypeName")) or entry.get("TypeName"),
                        "gridX": num(entry.get("GridX")),
                        "gridY": num(entry.get("GridY")),
                    }
                )
        block["gridItems"] = {
            "class": GRIDITEM_CLS,
            "aliases": [row["alias"] for row in items],
            "placements": placements,
        }
    return block


def mutator_block(bucket: dict[str, list[dict]]) -> list[dict] | None:
    rows: list[dict] = []
    for cls in sorted(k for k in bucket if k.startswith("LevelMutator")):
        for row in bucket[cls]:
            record = {"objclass": cls, "alias": row["alias"]}
            record.update(flatten_objdata(row["data"]))
            rows.append(record)
    return rows or None


def night_block(
    level: dict,
    bucket: dict[str, list[dict]],
    aliases: dict[str, tuple[str, str]],
    index: dict[str, dict[str, list[dict]]],
) -> dict | None:
    if not level["night"]:
        return None
    definition = (bucket.get("LevelDefinition") or [{}])[0].get("data") or {}
    stage_module = rtid_name(definition.get("StageModule")) or ""
    modules = [rtid_name(m) or "" for m in definition.get("Modules") or []]
    block: dict = {
        "flagSource": f"{level['file']} extra.night",
        "stage": level["stage"],
        "stageModule": stage_module,
    }
    resolved = aliases.get(stage_module)
    if resolved:
        block["stageModuleClass"] = resolved[0]
        block["stageModulePackage"] = resolved[1]
        target = None
        for row in index.get(resolved[1], {}).get(resolved[0], []):
            if row["alias"] == stage_module:
                target = row
                break
        if target is not None:
            data = target["data"]
            props = {
                "class": resolved[0],
                "alias": stage_module,
                "musicSuffix": data.get("MusicSuffix"),
                "backgroundImagePrefix": data.get("BackgroundImagePrefix"),
                "backgroundResourceGroup": data.get("BackgroundResourceGroup"),
                "isNightStage": data.get("IsNightStage"),
                "gravestoneDefaultType": rtid_name(data.get("GravestoneDefaultTypeName")),
            }
            cells = data.get("DisabledStreetCells")
            if isinstance(cells, list):
                props["disabledStreetCells"] = len(cells)
            block["stageProps"] = props
    else:
        block["stageModuleClass"] = None
    block["modules"] = {
        "count": len(modules),
        "hasSkySunDropper": SKY_SUN_MODULE in modules,
        "nightModules": [m for m in modules if m in NIGHT_MODULES],
    }
    graves: list[dict] = []
    for row in bucket.get(GRAVE_CLS) or []:
        data = row["data"]
        pool = []
        for entry in data.get("GravestonePool") or []:
            if isinstance(entry, dict):
                pool.append(
                    {
                        "type": rtid_name(entry.get("Type")),
                        "count": num(entry.get("Count")),
                    }
                )
        positions = []
        for entry in data.get("SpawnPositionsPool") or []:
            if isinstance(entry, dict):
                positions.append({"x": num(entry.get("mX")), "y": num(entry.get("mY"))})
        record = {
            "wave": wave_of(row["alias"]),
            "alias": row["alias"],
            "pool": pool,
            "positions": positions,
        }
        if isinstance(data.get("RandomPlacement"), bool):
            record["randomPlacement"] = data["RandomPlacement"]
        if isinstance(data.get("WaveStartMessage"), str):
            record["waveStartMessage"] = data["WaveStartMessage"]
        graves.append(record)
    if graves:
        graves.sort(key=lambda g: (g["wave"] is None, g["wave"] or 0, g["alias"]))
        block["gravestones"] = graves
    return block


def frost_block(bucket: dict[str, list[dict]]) -> dict | None:
    rows = bucket.get(FROST_CLS) or []
    if not rows:
        return None
    events: list[dict] = []
    directions: Counter[str] = Counter()
    rows_seen: Counter[str] = Counter()
    rows_raw: list[object] = []
    for row in rows:
        winds = []
        for wind in row["data"].get("Winds") or []:
            if not isinstance(wind, dict):
                continue
            direction = wind.get("Direction")
            row_value = num(wind.get("Row"))
            if isinstance(direction, str):
                directions[direction] += 1
            if row_value is not None:
                rows_seen[str(row_value)] += 1
                if str(row_value) != str(wind.get("Row")):
                    rows_raw.append(wind.get("Row"))
            winds.append({"direction": direction, "row": row_value})
        events.append(
            {
                "wave": wave_of(row["alias"]),
                "alias": row["alias"],
                "windCount": len(winds),
                "winds": winds,
            }
        )
    events.sort(key=lambda e: (e["wave"] is None, e["wave"] or 0, e["alias"]))
    block: dict = {
        "class": FROST_CLS,
        "eventCount": len(events),
        "events": events,
        "directions": {k: directions[k] for k in sorted(directions)},
        "rows": {k: rows_seen[k] for k in sorted(rows_seen, key=lambda s: float(s))},
    }
    if rows_raw:
        block["rowsRaw"] = sorted({str(v) for v in rows_raw})
    return block


def tide_block(bucket: dict[str, list[dict]]) -> dict | None:
    """R06：涨落事件（``TidalChange``）、标记位置（``TideProperties``）、潜艇段（``TideWave``）。

    三者互不同时出现：60 关有涨落事件、80 关有标记位置、10 关有潜艇段，交集为空。
    只要其中一项存在就出 tide 块；``counts.tide`` 只数**有涨落事件**的关（与
    ``level_playability`` 的 ``events.tide`` 对齐），其余两档各有独立计数。
    """
    changes: list[dict] = []
    for row in bucket.get(TIDE_CHANGE_CLS) or []:
        change = row["data"].get("TidalChange")
        change = change if isinstance(change, dict) else {}
        changes.append(
            {
                "wave": wave_of(row["alias"]),
                "alias": row["alias"],
                "amount": num(change.get("ChangeAmount")),
                "type": change.get("ChangeType"),
            }
        )
    changes.sort(key=lambda c: (c["wave"] is None, c["wave"] or 0, c["alias"]))

    waves: list[dict] = []
    for row in bucket.get(TIDE_WAVE_CLS) or []:
        record = {"wave": wave_of(row["alias"]), "alias": row["alias"]}
        record.update(flatten_objdata(row["data"]))
        waves.append(record)
    waves.sort(key=lambda w: (w["wave"] is None, w["wave"] or 0, w["alias"]))

    props = bucket.get(TIDE_PROPS_CLS) or []
    starting = num(props[0]["data"].get("StartingWaveLocation")) if props else None
    marker = props[0]["data"].get("ShowTideMarker") if props else None

    if not changes and not waves and starting is None:
        return None

    block: dict = {}
    if changes:
        block["class"] = TIDE_CHANGE_CLS
        block["changes"] = changes
    if waves:
        block["tideWaveClass"] = TIDE_WAVE_CLS
        block["waves"] = waves
    if props:
        block["tideMarkerClass"] = TIDE_PROPS_CLS
        block["startingWaveLocation"] = starting
        if isinstance(marker, bool):
            block["showTideMarker"] = marker
    return block


def strength_block(tide: dict | None) -> dict | None:
    """R07：|ChangeAmount| 求和，round 4；与 mechanics.py:851 同口径。"""
    if not tide:
        return None
    total = 0.0
    seen = 0
    for change in tide.get("changes") or []:
        amount = change["amount"]
        if isinstance(amount, (int, float)):
            total += abs(float(amount))
            seen += 1
    if not seen:
        return None
    return {
        "value": round(total, 4),
        "derivedFrom": "sum(|TidalChange.ChangeAmount|)",
        "derivedSource": "tools/contentc/mechanics.py:851 _event_strength",
        "changeCount": seen,
    }


# --------------------------------------------------------------------------- #
# build / render
# --------------------------------------------------------------------------- #


def digest(payload: object) -> str:
    """R08：对载荷的规范紧凑 JSON 取 sha256 前 16 位。"""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"


def build(obb: Path, levels_dir: Path) -> dict:
    index = index_packages(package_paths(obb))
    aliases = alias_table(index)
    levels = level_rows(levels_dir)

    out_levels: dict[str, dict] = {}
    unknowns: list[dict] = []
    tide_props_only: list[str] = []
    tide_wave_only: list[str] = []
    night_without_stage: list[str] = []
    night_without_graves: list[str] = []

    for lid in sorted(levels):
        info = levels[lid]
        bucket = index.get(info["package"]) or {}
        entry: dict = {}

        grid = board_grid_block(bucket)
        if grid:
            entry["boardGrid"] = grid
        mutators = mutator_block(bucket)
        if mutators:
            entry["mutators"] = mutators
        night = night_block(info, bucket, aliases, index)
        if night:
            entry["night"] = night
            if not night.get("stageModuleClass"):
                night_without_stage.append(lid)
            if "gravestones" not in night:
                night_without_graves.append(lid)
        frost = frost_block(bucket)
        if frost:
            entry["frost"] = frost
        tide = tide_block(bucket)
        if tide:
            entry["tide"] = tide
            strength = strength_block(tide)
            if strength:
                entry["strength"] = strength
            if not tide.get("changes"):
                if tide.get("waves"):
                    tide_wave_only.append(lid)
                else:
                    tide_props_only.append(lid)
        if entry:
            out_levels[lid] = entry

    def count_with(key: str) -> int:
        return sum(1 for row in out_levels.values() if key in row)

    empty_maps = [lid for lid, row in out_levels.items()
                  for block in (row.get("boardGrid") or {}).get("maps") or []
                  if not any(any(line) for line in block["rows"])]
    multi_maps = sorted(lid for lid, row in out_levels.items()
                        if len((row.get("boardGrid") or {}).get("maps") or []) > 1)
    counts = {
        "levels": len(levels),
        "levelsWithRules": len(out_levels),
        "boardGrid": count_with("boardGrid"),
        "mutators": count_with("mutators"),
        "night": count_with("night"),
        "frost": count_with("frost"),
        # R06：counts.tide 只数「有涨落事件」的关（= level_playability 的 events.tide 60 关），
        # 另给 tideBlocks / tideWithWaves / tideWithMarker 三个更细的口径。
        "tide": sum(1 for row in out_levels.values()
                    if "changes" in (row.get("tide") or {})),
        "strength": count_with("strength"),
        "tideBlocks": count_with("tide"),
        "tideWithChanges": sum(1 for row in out_levels.values()
                               if "changes" in (row.get("tide") or {})),
        "tideWithWaves": sum(1 for row in out_levels.values()
                             if "waves" in (row.get("tide") or {})),
        "tideWithMarker": sum(1 for row in out_levels.values()
                              if "startingWaveLocation" in (row.get("tide") or {})),
        "mutatorObjects": sum(len(row["mutators"]) for row in out_levels.values()
                              if "mutators" in row),
        "boardGridMaps": sum(len(row["boardGrid"]["maps"]) for row in out_levels.values()
                             if "boardGrid" in row),
        "boardGridEmptyMaps": len(empty_maps),
        "boardGridMultiMapLevels": multi_maps,
        "nightWithGravestones": sum(1 for row in out_levels.values()
                                    if "gravestones" in (row.get("night") or {})),
        "nightWithoutSkySunDropper": sum(1 for row in out_levels.values()
                                         if (row.get("night") or {}).get("modules", {})
                                         .get("hasSkySunDropper") is False),
        "frostEvents": sum((row.get("frost") or {}).get("eventCount", 0)
                           for row in out_levels.values()),
        "tideChanges": sum(len((row.get("tide") or {}).get("changes") or [])
                           for row in out_levels.values()),
        "filesScanned": len(index),
    }

    if night_without_stage:
        unknowns.append({
            "kind": "night-stage-module-unresolved",
            "detail": f"{len(night_without_stage)} 关的 StageModule 指向的别名在 460.9 全库没有对象",
            "levels": night_without_stage,
            "probe": "python tools/contentc/level_extra_rules.py -n FairyNightsStage",
        })
    if tide_props_only:
        unknowns.append({
            "kind": "tide-properties-without-tide-events",
            "detail": f"{len(tide_props_only)} 关只有 TideProperties.StartingWaveLocation（潮水标记位），"
                      "没有 TidalChange 涨落事件；按 R06 不出 changes，也不参与 strength",
            "levels": tide_props_only,
            "probe": "python tools/contentc/level_extra_rules.py -n StartingWaveLocation",
        })
    if tide_wave_only:
        unknowns.append({
            "kind": "tide-wave-without-tide-events",
            "detail": f"{len(tide_wave_only)} 关只有 TideWaveWaveActionProps（潜艇/僵尸加速段），"
                      "没有 TidalChange 涨落事件；wave 段参数原样进 tide.waves",
            "levels": tide_wave_only,
            "probe": "python tools/contentc/level_extra_rules.py -n TideWaveWaveActionProps",
        })
    if empty_maps:
        unknowns.append({
            "kind": "board-grid-empty-map",
            "detail": f"{len(empty_maps)} 关的格图全 0（有对象但没有禁用/替换格）",
            "levels": sorted(set(empty_maps)),
            "probe": "python tools/contentc/level_extra_rules.py -n Values",
        })
    unknowns.append({
        "kind": "board-grid-code-semantics",
        "detail": "BoardGridMapProps.Values 的 0/1 语义原版没有字段说明"
                  "（本表只给格码与坐标，不翻译成「可种/不可种」）",
        "levels": [],
        "probe": "python tools/contentc/level_extra_rules.py -n BoardGridMapProps",
    })
    unknowns.append({
        "kind": "night-no-dusk-time",
        "detail": "原版没有「天黑时间点」字段；夜战只体现为 extra.night、stage 属性资源、"
                  "以及缺 DefaultSunDropper（= 天上不掉阳光）与墓碑波次",
        "levels": [],
        "probe": "python tools/contentc/level_extra_rules.py -n IsNightStage",
    })
    if night_without_graves:
        unknowns.append({
            "kind": "night-without-gravestones",
            "detail": f"{len(night_without_graves)} 关是夜战但包里没有 SpawnGravestonesWaveActionProps"
                      "（这些关不出墓碑，属数据事实，不是缺字段）",
            "levels": [],
            "probe": "python tools/contentc/level_extra_rules.py -n GravestonePool",
        })
    unknowns.append({
        "kind": "mutator-sheet-classes-unused",
        "detail": "14 个 LevelMutator* 类里只有 3 个（TableProps/ModuleProperties/MaxSunProps）"
                  "被关卡挂载；其余 11 个只存在于 pkg_0236/pkg_0237 的定义表，关卡侧没有实例",
        "levels": [],
        "probe": "python tools/contentc/level_extra_rules.py -n LevelMutator",
    })

    body = {
        "format": FORMAT,
        "generator": GENERATOR,
        "sources": [
            "work/obb_packages (460.9) LevelDefinition 包",
            "content/levels (extra.night / extra.package)",
        ],
        "counts": counts,
        "levels": out_levels,
        "unknowns": sorted(unknowns, key=lambda u: (u["kind"], u["detail"])),
    }
    return {"generated": digest(body), **body}


def render(table: dict) -> str:
    """紧凑 JSON + LF（R08/R09）；键序固定，便于逐字节 --check。"""
    return json.dumps(table, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"


def dump(table: dict, path: Path) -> None:
    """write_bytes 而不是 write_text：Windows 上 write_text 会把 \\n 写成 CRLF。"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(render(table).encode("utf-8"))


# --------------------------------------------------------------------------- #
# check / needle
# --------------------------------------------------------------------------- #


def check(table: dict, path: Path) -> list[str]:
    problems: list[str] = []
    if table.get("format") != FORMAT:
        problems.append(f"format 不是 {FORMAT}: {table.get('format')!r}")
    if not isinstance(table.get("levels"), dict) or not table["levels"]:
        problems.append("levels 为空")
        return problems

    counts = table.get("counts") or {}
    for key in ("levels", "levelsWithRules", "boardGrid", "mutators", "night", "frost",
                "tide", "strength"):
        if not isinstance(counts.get(key), int):
            problems.append(f"counts.{key} 缺失或不是整数")

    levels = table["levels"]
    for lid, row in levels.items():
        if not lid or not isinstance(lid, str):
            problems.append(f"非法的关 id: {lid!r}")
            continue
        for key, block in row.items():
            if key not in ("boardGrid", "mutators", "night", "frost", "tide", "strength"):
                problems.append(f"{lid}: 未知块 {key}")
            if block is None:
                problems.append(f"{lid}: {key} 为 null（缺失应整块不写）")
        if "boardGrid" in row:
            for block in row["boardGrid"]["maps"]:
                if block["height"] != len(block["rows"]):
                    problems.append(f"{lid}: boardGrid height 与 rows 行数不符")
                width = block["width"]
                if any(len(line) != width for line in block["rows"]):
                    problems.append(f"{lid}: boardGrid 行宽不一致")
                cells = sum(block["cellCounts"].values())
                if cells != block["height"] * width:
                    problems.append(f"{lid}: boardGrid cellCounts 与矩阵尺寸不符")
        if "strength" in row and "tide" not in row:
            problems.append(f"{lid}: strength 必须由 tide 派生，不能单独存在")
        if "strength" in row:
            expected = round(sum(abs(float(c["amount"])) for c in row["tide"]["changes"]
                                 if isinstance(c["amount"], (int, float))), 4)
            if row["strength"]["value"] != expected:
                problems.append(f"{lid}: strength {row['strength']['value']} != {expected}")
        if "tide" in row:
            block = row["tide"]
            if not any(k in block for k in ("changes", "waves", "startingWaveLocation")):
                problems.append(f"{lid}: tide 块既无 changes / waves / startingWaveLocation")

    # counts 复算
    recomputed = {
        "levelsWithRules": len(levels),
        "boardGrid": sum(1 for r in levels.values() if "boardGrid" in r),
        "mutators": sum(1 for r in levels.values() if "mutators" in r),
        "night": sum(1 for r in levels.values() if "night" in r),
        "frost": sum(1 for r in levels.values() if "frost" in r),
        "tide": sum(1 for r in levels.values() if "changes" in (r.get("tide") or {})),
        "tideBlocks": sum(1 for r in levels.values() if "tide" in r),
        "strength": sum(1 for r in levels.values() if "strength" in r),
    }
    for key, value in recomputed.items():
        if counts.get(key) != value:
            problems.append(f"counts.{key}={counts.get(key)} 与复算 {value} 不符")

    unknowns = table.get("unknowns")
    if not isinstance(unknowns, list) or not unknowns:
        problems.append("unknowns 不得为空（R09：解析不出必须记录）")
    else:
        for item in unknowns:
            for field in ("kind", "detail", "probe"):
                if not isinstance(item.get(field), str) or not item[field]:
                    problems.append(f"unknowns 条目缺 {field}: {item}")

    body = {k: v for k, v in table.items() if k != "generated"}
    if table.get("generated") != digest(body):
        problems.append(f"generated 内容戳不符: {table.get('generated')}")

    text = render(table)
    if "\r" in text:
        problems.append("渲染结果含 CR（Windows 换行）")
    if not text.endswith("\n") or text.endswith("\n\n"):
        problems.append("渲染结果必须以单个 LF 结尾")
    if "D:\\" in text or "OneDrive" in text:
        problems.append("渲染结果泄露本机绝对路径")

    disk = Path(path)
    if not disk.exists():
        problems.append(f"产物不存在: {disk}")
    else:
        raw = disk.read_bytes()
        if b"\r" in raw:
            problems.append("磁盘产物含 CRLF")
        if raw != text.encode("utf-8"):
            problems.append(f"磁盘产物与重算不一致（过期）: {disk}")
    return problems


def needle_report(obb: Path, needle: str) -> int:
    """全库键名/类名检索：打印命中位置，用于报告里的「证有/证无」。"""
    paths = package_paths(obb)
    hits = 0
    lowered = needle.lower()
    for path in paths:
        if lowered in path.name.lower():
            print(f"{path.name}: <文件名>")
            hits += 1
        try:
            doc = s5scan.load_package(path)
        except Exception:  # noqa: BLE001
            continue
        for obj in doc.get("objects") or []:
            cls = obj.get("objclass") or ""
            aliases = [a for a in (obj.get("aliases") or []) if isinstance(a, str)]
            alias = aliases[0] if aliases else ""
            data = obj.get("objdata") or {}
            where = []
            if lowered in cls.lower():
                where.append("objclass")
            if lowered in alias.lower():
                where.append("alias")
            for key in data:
                if lowered in str(key).lower():
                    where.append(f"key:{key}")
            if where:
                hits += 1
                print(f"{path.name}: {cls}/{alias} -> {', '.join(where)}")
    print(f"needle {needle!r}: {hits} hits")
    return 0


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="compile per-level extra rules table")
    ap.add_argument("--obb", type=Path, default=DEFAULT_OBB)
    ap.add_argument("--levels", type=Path, default=DEFAULT_LEVELS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="逐字节校验产物是否最新")
    ap.add_argument("-n", "--needle", help="全库键名/类名检索")
    args = ap.parse_args(argv)

    if args.needle:
        return needle_report(args.obb, args.needle)
    if not Path(args.obb).is_dir():
        print(f"OBB 目录不存在: {args.obb}", file=sys.stderr)
        return 2
    table = build(args.obb, args.levels)
    if args.check:
        problems = check(table, args.out)
        if problems:
            print(f"{GENERATOR}: {len(problems)} 个问题", file=sys.stderr)
            for problem in problems:
                print(f"  - {problem}", file=sys.stderr)
            return 1
        counts = table["counts"]
        print(
            f"{GENERATOR} {table['generated']} "
            f"levels={counts['levelsWithRules']} "
            f"boardGrid={counts['boardGrid']} mutators={counts['mutators']} "
            f"night={counts['night']} frost={counts['frost']} "
            f"tide={counts['tide']} strength={counts['strength']} "
            f"unknowns={len(table['unknowns'])}"
        )
        print("OK")
        return 0
    dump(table, args.out)
    size = Path(args.out).stat().st_size
    counts = table["counts"]
    print(
        f"{GENERATOR} -> {args.out} ({size} bytes) {table['generated']} "
        f"boardGrid={counts['boardGrid']} mutators={counts['mutators']} "
        f"night={counts['night']} frost={counts['frost']} "
        f"tide={counts['tide']} strength={counts['strength']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
