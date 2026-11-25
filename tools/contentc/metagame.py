"""把 460.9 的三块元游戏数据（图鉴 / 花园 / 成就·任务）编成一张可消费的表。

数据源是 ``work/obb_packages`` 里 RTON 解包后的 JSON（一个 ``pkg_*.json`` 一个包），
只读解析、不执行二进制、不联网。三块表的权威 objclass 都是先枚举全部包的 objclass 体量
再逐个确认的：图鉴是 ``PlantAlmanacData`` + ``ZombieType``，花园是 ``CollectableType``
（本地没有 ``Garden*`` 前缀的类），成就·任务是 ``QuestMgr.Quests`` + ``QuestTabCategoryData``
（成就本身在本地只有 ``ACHIEVE_*`` 文案键，没有表）。

产物：

- ``native/generated/metagame.json``（``marker = metagame-compile-v1``）
- ``docs/reviews/2026-11-25-metagame-data.md``

用法::

    python tools/contentc/metagame.py            # 生成两个产物
    python tools/contentc/metagame.py --check    # 逐字节校验是否最新（过期返回 2）
    python tools/contentc/metagame.py -n         # 只算不写，打印摘要

推断值一律带标记：本地化键是推导规律给的（``resolved`` 说明是否真查到）、
世界是内部 token（``worldSource``）、售价只在商品表里对得上时才给（``matchKind``）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages"))
DEFAULT_JSON = ROOT / "native" / "generated" / "metagame.json"
DEFAULT_REPORT = ROOT / "docs" / "reviews" / "2026-11-25-metagame-data.md"
DEFAULT_PLANTS = ROOT / "content" / "plants.json"
DEFAULT_ZOMBIES = ROOT / "content" / "zombies.json"

FORMAT = 1
MARKER = "metagame-compile-v1"

RTID_RE = re.compile(r"RTID\((?P<name>[^@)]+)@[^)]+\)")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


# ---------------------------------------------------------------- generic io


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _objects(path: Path) -> list[dict]:
    payload = _load(path)
    objects = payload.get("objects")
    return [obj for obj in objects if isinstance(obj, dict)] if isinstance(objects, list) else []


def iter_packages(obb: Path):
    """按文件名顺序遍历包（顺序固定，保证产物可复现）。"""
    for path in sorted(obb.glob("pkg_*.json")):
        try:
            objects = _objects(path)
        except (OSError, ValueError):
            continue
        if objects:
            yield path, objects


def _strip_brackets(key) -> str:
    if not isinstance(key, str):
        return ""
    text = key.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return text


def _rtid_name(value) -> str:
    if not isinstance(value, str):
        return ""
    match = RTID_RE.search(value.strip())
    return match.group("name") if match else value.strip()


def _str(value) -> str:
    return value if isinstance(value, str) else ""


def _num(value) -> str:
    """数值字段：JSON 数字原样转文本（``1000`` -> ``"1000"``），字符串原样保留。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return value if isinstance(value, str) else ""


# ---------------------------------------------------------------- localization


def load_string_pairs(path: Path) -> dict[str, str]:
    """``LocStringValues`` 是扁平 ``[k, v, k, v, ...]``。"""
    for obj in _objects(path):
        values = (obj.get("objdata") or {}).get("LocStringValues")
        if isinstance(values, list):
            return {values[i]: values[i + 1] for i in range(0, len(values) - 1, 2)}
    return {}


def _is_chinese(pairs: dict[str, str]) -> bool:
    values = list(pairs.values())
    if not values:
        return False
    hits = sum(1 for value in values if isinstance(value, str) and CJK_RE.search(value))
    return hits * 2 > len(values)


def load_strings(obb: Path):
    """返回 ``(英文表, 中文表, 统计)``；语种按「值里有没有 CJK」判定，不靠文件名顺序。"""
    english: dict[str, str] = {}
    chinese: dict[str, str] = {}
    files = []
    for path in sorted(obb.glob("pkg_*LawnStringsData.json")):
        pairs = load_string_pairs(path)
        if not pairs:
            continue
        hits = sum(1 for value in pairs.values() if isinstance(value, str) and CJK_RE.search(value))
        files.append({"file": path.name, "pairs": len(pairs), "cjk": hits})
        if _is_chinese(pairs):
            chinese.update(pairs)
        else:
            english.update(pairs)
    return english, chinese, {"files": files}


# ---------------------------------------------------------------- table index

TABLE_CLASSES = (
    "PlantType",
    "PlantAlmanacData",
    "ZombieType",
    "ZombiePropertySheet",
    "CollectableType",
    "StoreProductProps",
    "QuestMgr",
    "QuestTabCategoryData",
    "QuestTabCategories",
    "QuestRewardTablesProps",
    "QuestThemeProps",
    "ZenGardenPropertySheet",
    "ZenGardenPlantSlotProps",
    "ZenGardenFloatingTextProps",
    "ZenGardenBeePropertySheet",
    "ZenGardenPlantRewardsPropertySheet",
    "AwardConfigPropertySheet",
    "PlayerSegmentRules",
)


def load_tables(obb: Path) -> dict[str, list[dict]]:
    tables, _daily, _scan = load_everything(obb)
    return tables


def load_daily_quest_defs(obb: Path) -> list[tuple[str, dict]]:
    _tables, daily, _scan = load_everything(obb)
    return daily


def scan_levels(obb: Path) -> tuple:
    _tables, _daily, scan = load_everything(obb)
    return scan


def load_everything(obb: Path) -> tuple[dict[str, list[dict]], list[tuple[str, dict]], tuple]:
    """单趟扫完 2116 个包：表索引 + 每日任务定义 + 关卡反向引用。"""
    tables: dict[str, list[dict]] = {name: [] for name in TABLE_CLASSES}
    daily: list[tuple[str, dict]] = []
    plant_levels: dict[str, int] = {}
    zombie_levels: dict[str, int] = {}
    zombie_home: dict[str, str] = {}
    zombie_class: dict[str, str] = {}
    zombie_defined: set[str] = set()
    zombie_spawn: set[str] = set()
    level_files = 0
    packages_seen = 0

    for _path, objects in iter_packages(obb):
        packages_seen += 1
        plants_here: set[str] = set()
        zombies_here: set[str] = set()
        has_level = False

        for obj in objects:
            cls = _str(obj.get("objclass"))
            data = obj.get("objdata")
            if not isinstance(data, dict):
                continue
            if cls in tables:
                tables[cls].append(obj)

            if cls == "LevelDefinition" and data.get("StageModule"):
                has_level = True

            if cls == "ZombieType" and data.get("TypeName"):
                name = _str(data.get("TypeName"))
                zombie_defined.add(name)
                # 同一 id 在多个包里可能有不同 HomeWorld（见 U10），文件序首个定义胜出
                if data.get("HomeWorld"):
                    zombie_home.setdefault(name, _str(data.get("HomeWorld")))
                if data.get("ZombieClass"):
                    zombie_class.setdefault(name, _str(data.get("ZombieClass")))

            if cls == "InitialPlantProperties":
                for placement in data.get("InitialPlantPlacements") or []:
                    if isinstance(placement, dict):
                        name = _str(placement.get("TypeName"))
                        if name:
                            plants_here.add(name)

            if cls.endswith("SeedBankProperties"):
                for key in ("PresetPlantList", "PlantPriorList"):
                    for entry in data.get(key) or []:
                        if isinstance(entry, dict):
                            name = _str(entry.get("PlantType"))
                            if name:
                                plants_here.add(name)

            if cls.startswith("SpawnZombies"):
                for entry in data.get("Zombies") or []:
                    if isinstance(entry, dict):
                        name = _rtid_name(entry.get("Type"))
                        if name:
                            zombies_here.add(name)
                            zombie_spawn.add(name)

            if cls.endswith("QuestData") and data.get("UniqueID"):
                daily.append((cls, obj))

        if has_level:
            level_files += 1
            for name in plants_here:
                plant_levels[name] = plant_levels.get(name, 0) + 1
            for name in zombies_here:
                zombie_levels[name] = zombie_levels.get(name, 0) + 1

    scan = (
        level_files,
        plant_levels,
        zombie_levels,
        zombie_home,
        zombie_class,
        zombie_defined,
        zombie_spawn,
        packages_seen,
    )
    return tables, daily, scan


def load_material(obb: Path) -> dict:
    """一次扫盘得到的全部原料，``build`` 可复用（测试里只扫一次）。"""
    tables, daily, scan = load_everything(obb)
    english, chinese, loc = load_strings(obb)
    return {
        "tables": tables,
        "daily": daily,
        "scan": scan,
        "english": english,
        "chinese": chinese,
        "loc": loc,
    }


# ---------------------------------------------------------------- blocks


def _plant_stats(data) -> list[dict]:
    rows = []
    for entry in data.get("AlmanacDataEntries") or []:
        if not isinstance(entry, dict):
            continue
        rows.append(
            {
                "statName": _str(entry.get("StatName")),
                "statNameAlias": _str(entry.get("StatNameAlias")),
                "statType": _str(entry.get("StatType")),
                "typeKey": _strip_brackets(entry.get("TypeStringID")),
                "valueKey": _strip_brackets(entry.get("ValueStringID")),
                "levelToUnlock": _num(entry.get("LevelToUnlock")),
                "numberFormat": _str(entry.get("NumberFormat")),
            }
        )
    return rows


def build_almanac(tables, english, chinese, plant_levels, zombie_levels, zombie_home, zombie_class, zombie_defined, zombie_spawn):
    plant_types: dict[str, dict] = {}
    for obj in tables["PlantType"]:
        data = obj.get("objdata") or {}
        for name in (_str(data.get("TypeName")), *[a for a in obj.get("aliases") or [] if isinstance(a, str)]):
            if name:
                plant_types.setdefault(name, data)

    plants = []
    for obj in tables["PlantAlmanacData"]:
        aliases = [a for a in obj.get("aliases") or [] if isinstance(a, str)]
        if not aliases:
            continue
        identifier = aliases[0]
        name_key = identifier.upper()
        desc_key = name_key + "_DESCRIPTION"
        tooltip_key = name_key + "_TOOLTIP"
        plant_type = plant_types.get(identifier) or {}
        world = _str(plant_type.get("HomeWorld"))
        plants.append(
            {
                "id": identifier,
                "nameKey": name_key,
                "descKey": desc_key,
                "tooltipKey": tooltip_key,
                "resolved": {
                    "name": name_key in english,
                    "nameZh": name_key in chinese,
                    "desc": desc_key in english,
                    "descZh": desc_key in chinese,
                    "tooltip": tooltip_key in english,
                },
                "world": world,
                "worldSource": "PlantType.HomeWorld" if world else "unknown",
                "almanacBackdrop": _str(plant_type.get("AlmanacBackdropName")),
                "inPlantTypes": bool(plant_type),
                "levels": plant_levels.get(identifier, 0),
                "stats": _plant_stats(obj.get("objdata") or {}),
            }
        )
    plants.sort(key=lambda row: row["id"])

    zombies_by_id: dict[str, dict] = {}
    for obj in tables["ZombieType"]:
        data = obj.get("objdata") or {}
        identifier = _str(data.get("TypeName"))
        if not identifier or identifier in zombies_by_id:
            continue
        name_key = "ZOMBIE_" + identifier.upper()
        if name_key not in english:
            continue
        desc_key = name_key + "_DESCRIPTION"
        header_key = name_key + "_DESCRIPTION_HEADER"
        world = zombie_home.get(identifier, "")
        zombies_by_id[identifier] = {
            "id": identifier,
            "nameKey": name_key,
            "descKey": desc_key,
            "descHeaderKey": header_key,
            "resolved": {
                "name": True,
                "nameZh": name_key in chinese,
                "desc": desc_key in english,
                "descHeader": header_key in english,
            },
            "world": world,
            "worldSource": "ZombieType.HomeWorld" if world else "unknown",
            "zombieClass": zombie_class.get(identifier, ""),
            "levels": zombie_levels.get(identifier, 0),
            "rosterSource": "derived:name-key",
        }
    zombies = sorted(zombies_by_id.values(), key=lambda row: row["id"])

    all_zombie_names = {
        _str((obj.get("objdata") or {}).get("TypeName")) for obj in tables["ZombieType"] if obj.get("objdata")
    }
    all_zombie_names.discard("")
    without_name_key = sorted(
        name for name in all_zombie_names if "ZOMBIE_" + name.upper() not in english
    )
    sheets = [obj for obj in tables["ZombiePropertySheet"] if isinstance(obj.get("objdata"), dict)]
    sheets_with_almanac = [
        obj
        for obj in sheets
        if "AlmanacOffset" in obj["objdata"] or "AlmanacScale" in obj["objdata"]
    ]
    counts = {
        "plants": len(plants),
        "plantsWithNameKey": sum(1 for row in plants if row["resolved"]["name"]),
        "plantsWithoutNameKey": sorted(row["id"] for row in plants if not row["resolved"]["name"]),
        "plantsWithWorld": sum(1 for row in plants if row["world"]),
        "plantsNotInPlantTypes": sorted(row["id"] for row in plants if not row["inPlantTypes"]),
        "zombies": len(zombies),
        "zombieTypesDefined": len(all_zombie_names),
        "zombiesWithoutNameKey": len(without_name_key),
        "zombiesSpawnOnly": len(sorted(name for name in zombie_spawn if name not in all_zombie_names)),
        "zombiesWithWorld": sum(1 for row in zombies if row["world"]),
        "zombiePropertySheets": len(sheets),
        "zombieSheetsWithAlmanacOffset": len(sheets_with_almanac),
    }
    return {"plants": plants, "zombies": zombies, "counts": counts}


def _tokens(text: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", text.lower()) if part}


def _find_product(collectable: str, products: list[dict]):
    """按「记号集合」在商品表里找同一个东西，返回 ``(商品, 匹配方式, 同形候选数)``。

    同一掉落物可能对应多档货（如 ``sprout`` 有 5/10/20 … 多档宝石价）；本层按
    商品表顺序取第一条，并把候选数报出来，避免把「某一档的价」当成唯一售价。
    """
    wanted = _tokens(collectable)
    matches = [p for p in products if _str(p.get("ObjectItem")) == collectable]
    if matches:
        return matches[0], "item", len(matches)
    if len(wanted) < 2:
        return None, "", 0
    matches = [p for p in products if wanted <= _tokens(_str(p.get("Sku")))]
    if matches:
        return matches[0], "sku", len(matches)
    return None, "", 0


def _award_key(award_type: str, subtype: str = "") -> str:
    """``pinata`` + ``egypt1`` -> ``pinata_egypt``，与 ``CollectableType.TypeName`` 同形。

    奖励表里的 SubType 是关卡/世界别名，常带序号（``egypt1``/``pirate2``），
    而掉落物名不带；去掉尾部数字才能与 ``pinata_<world>`` 对上。
    """
    subtype = re.sub(r"\d+$", "", subtype.strip().lower())
    return f"{award_type}_{subtype}" if subtype else award_type


def _drop_refs(tables) -> dict[str, list[dict]]:
    """「谁发这个东西」：只用本地真有表的行列，表里没写到的来源不补。"""
    refs: dict[str, dict[str, list[str]]] = {}

    def add(key: str, table: str, example: str) -> None:
        if not key:
            return
        bucket = refs.setdefault(key, {})
        items = bucket.setdefault(table, [])
        if example and example not in items and len(items) < 3:
            items.append(example)

    for obj in tables["QuestMgr"]:
        for entry in (obj.get("objdata") or {}).get("Quests") or []:
            if not isinstance(entry, dict):
                continue
            for inner in entry.values():
                if not isinstance(inner, dict) or not isinstance(inner.get("CompletionAwards"), dict):
                    continue
                for award in inner["CompletionAwards"].get("Awards") or []:
                    if isinstance(award, dict):
                        add(
                            _award_key(_str(award.get("Type")), _str(award.get("SubType"))),
                            "QuestMgr.CompletionAwards",
                            "",
                        )
    for obj in tables["QuestRewardTablesProps"]:
        for table in (obj.get("objdata") or {}).get("TablesConfig") or []:
            if not isinstance(table, dict):
                continue
            difficulty = _num(table.get("Difficulty"))
            for award in table.get("Awards") or []:
                if isinstance(award, dict):
                    add(
                        _award_key(_str(award.get("Type")), _str(award.get("SubType"))),
                        "QuestRewardTablesProps",
                        f"difficulty={difficulty}",
                    )
    for obj in tables["ZenGardenPlantRewardsPropertySheet"]:
        alias = (obj.get("aliases") or [""])[0]
        data = obj.get("objdata") or {}
        for key in ("LootCategories", "CoinRewards"):
            for reward in data.get(key) or []:
                if isinstance(reward, dict):
                    add(_str(reward.get("Award")), "ZenGardenPlantRewards", alias)
    for obj in tables["AwardConfigPropertySheet"]:
        for reward in (obj.get("objdata") or {}).get("GiftBoxRewards") or []:
            if isinstance(reward, dict):
                add(_str(reward.get("Award")), "AwardConfig.GiftBoxRewards", _str(reward.get("Category")))
    for obj in tables["StoreProductProps"]:
        data = obj.get("objdata") or {}
        add(_str(data.get("ObjectItem")), "StoreProductProps", _str(data.get("Sku")))

    return {
        key: [{"table": table, "examples": examples} for table, examples in sorted(bucket.items())]
        for key, bucket in refs.items()
    }


def build_garden(tables, english):
    products = [obj.get("objdata") or {} for obj in tables["StoreProductProps"]]
    category_names = {_str(product.get("ObjectType")) for product in products if product.get("ObjectType")}
    drop_refs = _drop_refs(tables)

    collectables = []
    for obj in tables["CollectableType"]:
        data = obj.get("objdata") or {}
        name = _str(data.get("TypeName"))
        if not name:
            continue
        title_key = _strip_brackets(data.get("RewardDialogTitle"))
        product, match_kind, candidates = _find_product(name, products)
        sold_as = None
        price_kind = ""
        if product is not None:
            prices = {
                "coins": _str(product.get("PriceCoins")),
                "gems": _str(product.get("PriceGems")),
                "mints": _str(product.get("PriceMints")),
                "usd": _str(product.get("Price")),
            }
            for kind, value in prices.items():
                if value and value not in ("0", "0.0"):
                    price_kind = kind
                    break
            sold_as = {
                "sku": _str(product.get("Sku")),
                "objectType": _str(product.get("ObjectType")),
                "objectItem": _str(product.get("ObjectItem")),
                "matchKind": match_kind,
                "candidates": candidates,
                **{f"price{kind.title()}": value for kind, value in prices.items()},
                "priceKind": price_kind,
            }
        collectables.append(
            {
                "typeName": name,
                "collectableClass": _str(data.get("CollectableClass")),
                "rewardDialogTitleKey": title_key,
                "rewardDialogTitleResolved": bool(title_key) and title_key in english,
                "image": _str(data.get("StandaloneImage")),
                "popAnim": _str(data.get("PopAnim")),
                "soldAs": sold_as,
                "storeCategory": name if name in category_names else "",
                "dropSources": drop_refs.get(name, []),
            }
        )
    collectables.sort(key=lambda row: row["typeName"])

    zen = {"props": None, "pots": [], "bee": None, "slotProps": None, "floatingText": None, "plantRewards": []}
    for obj in tables["ZenGardenPropertySheet"]:
        data = obj.get("objdata") or {}
        zen["props"] = {
            key: data.get(key)
            for key in (
                "BackgroundImageID",
                "PlantGrowDurationInSeconds",
                "NormalPlantCoinRewardAmount",
                "TreasurePlantSpawnRate",
                "GrowingSpeedupCalcMultiplyFactor",
                "GrowingSpeedupCalcAddFactor",
                "GrowingSpeedupCalcMaxTimeSeconds",
                "PotCosts",
            )
            if key in data
        }
        zen["pots"] = data.get("Pots") or []
    for obj in tables["ZenGardenPlantSlotProps"]:
        zen["slotProps"] = obj.get("objdata")
    for obj in tables["ZenGardenFloatingTextProps"]:
        zen["floatingText"] = obj.get("objdata")
    for obj in tables["ZenGardenBeePropertySheet"]:
        zen["bee"] = obj.get("objdata")
    for obj in tables["ZenGardenPlantRewardsPropertySheet"]:
        zen["plantRewards"].append({"id": (obj.get("aliases") or [""])[0], "data": obj.get("objdata")})
    zen["plantRewards"].sort(key=lambda row: row["id"])

    counts = {
        "collectables": len(collectables),
        "collectablesWithPrice": sum(1 for row in collectables if row["soldAs"]),
        "collectablesWithoutPrice": sorted(row["typeName"] for row in collectables if not row["soldAs"]),
        "collectablesWithDropSource": sum(1 for row in collectables if row["dropSources"]),
        "dropSourceTables": sorted({ref["table"] for row in collectables for ref in row["dropSources"]}),
        "collectableClasses": sorted({row["collectableClass"] for row in collectables if row["collectableClass"]}),
        "zenGardenPots": len(zen["pots"]),
        "zenGardenPlantRewards": len(zen["plantRewards"]),
        "zenGardenTables": sum(1 for key in ("props", "bee", "slotProps", "floatingText") if zen[key]),
    }
    return {"collectables": collectables, "zenGarden": zen, "counts": counts}


QUEST_PARAM_KEYS = (
    "LevelName",
    "Slot",
    "QuestCategory",
    "OverrideQuestTheme",
    "Priority",
    "ActionsToPerform",
    "CountRemainingLabel",
    "Repeatable",
    "Disabled",
)


def _rewards(awards):
    if not isinstance(awards, list):
        return None
    return [
        {
            "type": _str(award.get("Type")),
            "subtype": _str(award.get("SubType")),
            "amount": _num(award.get("Amount")),
        }
        for award in awards
        if isinstance(award, dict)
    ]


def build_quests(tables, daily_defs):
    quests = []
    for obj in tables["QuestMgr"]:
        for entry in (obj.get("objdata") or {}).get("Quests") or []:
            if not isinstance(entry, dict):
                continue
            for wrapper, inner in entry.items():
                if not isinstance(inner, dict):
                    continue
                awards = inner.get("CompletionAwards")
                rewards = _rewards(awards.get("Awards") if isinstance(awards, dict) else None)
                params = {key: inner[key] for key in QUEST_PARAM_KEYS if key in inner}
                if isinstance(inner.get("UniqueIDList"), list):
                    params["uniqueIdCount"] = len(inner["UniqueIDList"])
                if isinstance(inner.get("Prerequisites"), dict):
                    params["prerequisites"] = inner["Prerequisites"]
                quests.append(
                    {
                        "id": _str(inner.get("UniqueID")),
                        "targetType": wrapper,
                        "slot": _str(inner.get("Slot")),
                        "category": _str(inner.get("QuestCategory")),
                        "theme": _str(inner.get("OverrideQuestTheme")),
                        "nameKey": _strip_brackets(inner.get("QuestName")),
                        "descKey": _strip_brackets(inner.get("Description")),
                        "params": params,
                        "rewards": rewards,
                        "rewardSource": "QuestMgr.CompletionAwards" if rewards is not None else "unknown",
                    }
                )
    quests.sort(key=lambda row: (row["id"], row["targetType"]))

    daily = []
    for cls, obj in daily_defs:
        data = obj.get("objdata") or {}
        awards = data.get("CompletionAwards")
        rewards = _rewards(awards.get("Awards") if isinstance(awards, dict) else None)
        daily.append(
            {
                "id": _str(data.get("UniqueID")),
                "targetType": cls,
                "category": _str(data.get("QuestCategory")),
                "slot": _str(data.get("Slot")),
                "nameKey": _strip_brackets(data.get("QuestName")),
                "descKey": _strip_brackets(data.get("Description")),
                "params": {key: data[key] for key in QUEST_PARAM_KEYS if key in data},
                "rewards": rewards,
                "rewardSource": "QuestData.CompletionAwards" if rewards is not None else "unknown",
            }
        )
    daily.sort(key=lambda row: (row["id"], row["targetType"]))

    by_category: dict[str, int] = {}
    by_target: dict[str, int] = {}
    for row in quests:
        category = row["category"] or "(none)"
        by_category[category] = by_category.get(category, 0) + 1
        by_target[row["targetType"]] = by_target.get(row["targetType"], 0) + 1

    reward_tables = []
    for obj in tables["QuestRewardTablesProps"]:
        for table in (obj.get("objdata") or {}).get("TablesConfig") or []:
            if not isinstance(table, dict):
                continue
            reward_tables.append(
                {
                    "difficulty": _str(table.get("Difficulty")),
                    "awards": [
                        {
                            "type": _str(award.get("Type")),
                            "subtype": _str(award.get("SubType")),
                            "minAmount": _num(award.get("MinAmount")),
                            "maxAmount": _num(award.get("MaxAmount")),
                            "weight": _num(award.get("Weight")),
                        }
                        for award in (table.get("Awards") or [])
                        if isinstance(award, dict)
                    ],
                }
            )
    reward_tables.sort(key=lambda row: row["difficulty"])

    tabs = []
    for obj in tables["QuestTabCategoryData"]:
        data = obj.get("objdata") or {}
        tabs.append(
            {
                "id": _str(data.get("Name")) or _str(data.get("QuestTabCategory")),
                "tabLabelKey": _strip_brackets(data.get("TabLabel")),
                "questCategories": [str(item) for item in (data.get("QuestCategories") or [])],
                "selectedImage": _str(data.get("TabSelectedImage")),
                "unselectedImage": _str(data.get("TabUnselectedImage")),
                "showTimer": bool(data.get("ShowTimer")),
            }
        )
    tabs.sort(key=lambda row: row["id"])

    tab_order: list[str] = []
    for obj in tables["QuestTabCategories"]:
        tab_order = [str(item) for item in ((obj.get("objdata") or {}).get("TabCategories") or [])]

    reward_rows = [award for row in quests + daily for award in (row["rewards"] or [])]
    counts = {
        "quests": len(quests),
        "questsWithRewards": sum(1 for row in quests if row["rewards"] is not None),
        "questsByCategory": dict(sorted(by_category.items())),
        "questsByTargetType": dict(sorted(by_target.items())),
        "dailyQuestDefs": len(daily),
        "dailyWithRewards": sum(1 for row in daily if row["rewards"] is not None),
        "rewardTables": len(reward_tables),
        "questTabs": len(tabs),
        "rewardRows": len(reward_rows),
        "rewardRowsWithAmount": sum(1 for award in reward_rows if award["amount"]),
    }
    return {
        "quests": quests,
        "daily": daily,
        "rewardTables": reward_tables,
        "tabs": tabs,
        "tabOrder": tab_order,
        "counts": counts,
    }


def build_achievements(english, chinese):
    entries = []
    achieve_keys = 0
    for key in sorted(english):
        if not key.startswith("ACHIEVE_"):
            continue
        achieve_keys += 1
        if not key.endswith("_TITLE"):
            continue
        identifier = key[len("ACHIEVE_") : -len("_TITLE")]
        desc_key = "ACHIEVE_" + identifier + "_DESC"
        name_key = "ACHIEVE_" + identifier + "_NAME"
        entries.append(
            {
                "id": identifier,
                "titleKey": key,
                "descKey": desc_key if desc_key in english else "",
                "extraNameKey": name_key if name_key in english else "",
                "resolved": {
                    "title": True,
                    "titleZh": key in chinese,
                    "desc": desc_key in english,
                    "descZh": desc_key in chinese,
                },
                "rewards": None,
                "rewardSource": "serverOnly",
                "serverOnly": True,
            }
        )
    entries.sort(key=lambda row: row["id"])
    counts = {
        "achievements": len(entries),
        "achieveKeys": achieve_keys,
        "withDescKey": sum(1 for row in entries if row["descKey"]),
        "withExtraNameKey": sum(1 for row in entries if row["extraNameKey"]),
    }
    return {"entries": entries, "counts": counts, "serverOnly": True}


def content_ids(path: Path) -> list[str]:
    """``content/*.json`` 里每条记录的 ``id``（客户端自建名册）。"""
    if not path.is_file():
        return []
    payload = _load(path)
    rows = payload if isinstance(payload, list) else payload.get("items") or []
    return [row["id"] for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)]


def build_content_cross(almanac, plants_path: Path, zombies_path: Path) -> dict:
    plant_ids = content_ids(plants_path)
    zombie_ids = content_ids(zombies_path)
    almanac_plants = {row["id"] for row in almanac["plants"]}
    almanac_zombies = {row["id"] for row in almanac["zombies"]}
    return {
        "contentPlants": len(plant_ids),
        "contentZombies": len(zombie_ids),
        "almanacPlantsInContent": len(almanac_plants & set(plant_ids)),
        "almanacZombiesInContent": len(almanac_zombies & set(zombie_ids)),
        "contentPlantsNotInAlmanac": sorted(set(plant_ids) - almanac_plants),
        "contentZombiesNotInAlmanac": sorted(set(zombie_ids) - almanac_zombies),
    }


UNKNOWNS = [
    {
        "id": "U1",
        "topic": "zombie-roster",
        "question": (
            "原版没有僵尸图鉴花名册表（ZombiePropertySheet 里只有零星几条设了 AlmanacOffset/AlmanacScale，"
            "条数见 almanac.counts.zombieSheetsWithAlmanacOffset 与 zombiePropertySheets）；"
            "本层的准入判据是「有 ZombieType 定义 且 LawnStrings 有 ZOMBIE_<TYPE> 名字键」。被排除的两类分别见 "
            "counts.zombiesWithoutNameKey 与 counts.zombiesSpawnOnly。真正的图鉴花名册若在引擎代码里，本地数据看不出来。"
        ),
    },
    {
        "id": "U2",
        "topic": "almanac-plants-not-in-planttypes",
        "question": (
            "17 个图鉴植物在 PlantType 里没有同名条目（kelpguard/haystack/znakelily/…），它们的所属世界与图鉴背景无从取值，"
            "world 为空串。其中 ultomato1 看着是 ultomato 的升级变体（PlantType 里有 ultomato、没有 ultomato1），"
            "但按名字后缀去猜属于推断，本层不做合并。"
        ),
    },
    {
        "id": "U3",
        "topic": "missing-name-keys",
        "question": "minishroom 缺裸名键（其余 166 个植物都有）；缺键条目的 nameKey 照推导规律给出但 resolved.name=false。",
    },
    {
        "id": "U4",
        "topic": "achievement-rewards",
        "question": "成就本地只有 ACHIEVE_* 文案键，没有奖励表；奖励一律 serverOnly=true、rewards=null，未编造任何数值。",
    },
    {
        "id": "U5",
        "topic": "level-counting",
        "question": (
            "levels 是「关卡包文件计数」（一个 pkg_*.json 近似一关），同一关多波引用只计 1；"
            "植物只认 InitialPlantPlacements/PresetPlantList/PlantPriorList 的正向引用，PlantExcludeList 不算出现。"
        ),
    },
    {
        "id": "U6",
        "topic": "collectable-prices",
        "question": (
            "售价只在 StoreProductProps（565 条）里按「记号集合」对得上具体商品时给出（ObjectItem 全等，"
            "或掉落物记号≥2 个且是 Sku 记号子集）；品类名本身不冒充商品，匹配不到即 soldAs=null。"
            "同一掉落物可能对应多档货（如 sprout 有 5/10/20… 多档宝石价），本层取商品表顺序第一条并记 `candidates`，"
            "单条 price 不是唯一售价；原版是否存在其它售卖路径（服务器商品表）本地无法确认。"
        ),
    },
    {
        "id": "U7",
        "topic": "world-tokens",
        "question": (
            "PlantType.HomeWorld / ZombieType.HomeWorld 的取值是 tower/epicquest/modern/rift1a 这类内部 token，"
            "与 content/worlds.json 的 id（frontyard/…）不同源，本层原样保留、不做映射。"
        ),
    },
    {
        "id": "U8",
        "topic": "loc-key-convention",
        "question": (
            "植物名/描述键是按 166/167 条实测规律推导（裸大写 id + _DESCRIPTION/_TOOLTIP），僵尸键是 ZOMBIE_ + 大写 id；"
            "两者都不是 objdata 里显式写出的键，resolved 标记说明是否真查到。"
        ),
    },
    {
        "id": "U9",
        "topic": "spawn-only-zombies",
        "question": (
            "有 120 个名字只出现在 SpawnZombies* 的 RTID 生成引用里、没有自己的 ZombieType 定义（如 modern_screendoor）："
            "它们没有 HomeWorld、也不构成图鉴条目，本层不计入 almanac。"
        ),
    },
    {
        "id": "U10",
        "topic": "zombie-homeworld-conflict",
        "question": (
            "同一个 ZombieType id 在多个包里可能带不同 HomeWorld（本地有 9 个 id 如此，如 tutorial 同时出现 modern/tutorial、"
            "cowboy 同时出现 cowboy/dark/plantagenet/rift2/tutorial）；本层按文件序取首个定义，冲突值不合并、也不判定哪个才是原版口径。"
        ),
    },
]


def build(obb: Path = DEFAULT_OBB, plants_path: Path = DEFAULT_PLANTS, zombies_path: Path = DEFAULT_ZOMBIES, material: dict | None = None) -> dict:
    material = material or load_material(obb)
    tables = material["tables"]
    english = material["english"]
    chinese = material["chinese"]
    (
        level_files,
        plant_levels,
        zombie_levels,
        zombie_home,
        zombie_class,
        zombie_defined,
        zombie_spawn,
        packages,
    ) = material["scan"]

    almanac = build_almanac(
        tables,
        english,
        chinese,
        plant_levels,
        zombie_levels,
        zombie_home,
        zombie_class,
        zombie_defined,
        zombie_spawn,
    )
    garden = build_garden(tables, english)
    quests = build_quests(tables, material["daily"])
    achievements = build_achievements(english, chinese)
    cross = build_content_cross(almanac, plants_path, zombies_path)

    package_files = len(list(obb.glob("pkg_*.json")))
    payload = {
        "format": FORMAT,
        "marker": MARKER,
        "sources": {
            "obb": "work/obb_packages",
            "packageFiles": package_files,
            "packages": packages,
            "levelPackages": level_files,
            "locStrings": material["loc"],
            "content": {"plants": cross["contentPlants"], "zombies": cross["contentZombies"]},
        },
        "almanac": almanac,
        "garden": garden,
        "quests": quests,
        "achievements": achievements,
        "cross": cross,
        "counts": {
            "almanacPlants": len(almanac["plants"]),
            "almanacZombies": len(almanac["zombies"]),
            "almanacEntries": len(almanac["plants"]) + len(almanac["zombies"]),
            "gardenCollectables": len(garden["collectables"]),
            "quests": len(quests["quests"]),
            "questsWithRewards": quests["counts"]["questsWithRewards"],
            "dailyQuestDefs": len(quests["daily"]),
            "achievements": len(achievements["entries"]),
            "contentAlmanacIntersection": cross["almanacPlantsInContent"] + cross["almanacZombiesInContent"],
            "unknowns": len(UNKNOWNS),
        },
        "unknowns": UNKNOWNS,
    }
    return payload


# ---------------------------------------------------------------- render


def render_json(payload: dict) -> str:
    from tools.contentc import emit

    return emit.dumps(payload)


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return lines


def _pct(part: int, total: int) -> str:
    return f"{part}/{total}（{100.0 * part / total:.1f}%）" if total else f"{part}/0"


def render_report(payload: dict) -> str:
    almanac = payload["almanac"]
    garden = payload["garden"]
    quests = payload["quests"]
    achievements = payload["achievements"]
    cross = payload["cross"]
    src_meta = payload["sources"]
    lc = almanac["counts"]
    gc = garden["counts"]
    qc = quests["counts"]

    world_counter = Counter(row["world"] for row in almanac["zombies"] if row["world"])
    plant_world_counter = Counter(row["world"] for row in almanac["plants"] if row["world"])
    stat_counter = Counter(stat["statType"] for row in almanac["plants"] for stat in row["stats"])
    class_counter = Counter(row["collectableClass"] for row in garden["collectables"] if row["collectableClass"])
    reward_counter = Counter(
        award["type"]
        for row in quests["quests"] + quests["daily"]
        if row["rewards"]
        for award in row["rewards"]
    )
    priced = [row for row in garden["collectables"] if row["soldAs"]]

    lines: list[str] = []
    add = lines.append
    add("# 元游戏数据编译：图鉴 / 花园 / 成就·任务（460.9）")
    add("")
    add(
        f"由 `tools/contentc/metagame.py` 生成。数据源 `work/obb_packages`（{src_meta['packageFiles']} 个 `pkg_*.json`，"
        f"其中 {src_meta['packages']} 个能解出对象、{src_meta['levelPackages']} 个识别为关卡包）；产物 `native/generated/metagame.json`，"
        f"标记 `{payload['marker']}`。本文件与 JSON 都由 `--check` 逐字节校验，两次生成字节相同。"
    )
    add("")
    add("## 一、方法与边界")
    add("")
    add(
        "1. **只读**：只解析 `work/obb_packages` 的 JSON 与 `content/plants.json`、`content/zombies.json`；"
        "不执行二进制、不联网、不改 `content/**` 与 `native/src/**`。"
        f"数据源 {src_meta['packageFiles']} 个 `pkg_*.json` 里，`pkg_0224_unknown.json` 的 `objects` 是空数组（0 条），"
        f"实际参与解析 {src_meta['packages']} 个包。"
    )
    add(
        f"2. **类名自证**：三块表的权威 objclass 是先枚举全部 {src_meta['packages']} 个可解析包的 objclass 体量后逐个确认的，"
        "不按名字猜——花园的 65 条其实是 `CollectableType`，本地没有 `Garden*` 前缀的类；"
        "成就则在本地根本没有表。"
    )
    add(
        "3. **三条口径**：`levels` 是关卡包文件计数（一包近似一关）；本地化键统一去掉 objdata 里的方括号；"
        "推导出来的键/世界/售价都带 `resolved`、`worldSource`、`matchKind` 标记，推断值不写成实测值。"
    )
    add(
        "4. **确定性**：`sort_keys` + `indent=1` + UTF-8 + LF + 末尾换行，无时间戳、无绝对路径，"
        "`--check` 两次跑必须逐字节相同（见 `tools/tests/test_metagame.py`）。"
    )
    add("")
    add("## 二、任务线索与实测条数的对账")
    add("")
    lines.extend(
        _table(
            ["任务线索", "实测的权威表", "条数", "对账结论"],
            [
                [
                    "`Almanac*` 169",
                    "`PlantAlmanacData`（`pkg_2067`）",
                    str(lc["plants"]),
                    "167 条图鉴条目。线索的 169 是按名字前缀 grep 出来的，多算了 "
                    "`AlmanacDLHandler`、`HotUIAlmanacVerticalListProperties` 两个非条目对象",
                ],
                [
                    "`Garden*` 65",
                    "`CollectableType`（`pkg_0010`）",
                    str(gc["collectables"]),
                    "条数完全对上，但**不是 Garden 类**：这是掉落/奖励收藏物类型；Zen Garden 自己的属性表在 `pkg_2083`",
                ],
                [
                    "`Quest*`/`Achievement*` 69",
                    "`QuestMgr.Quests` 里带 `CompletionAwards` 的条目",
                    str(qc["questsWithRewards"]),
                    f"完全对上：{qc['quests']} 条 quest 里恰有 {qc['questsWithRewards']} 条带完成奖励；成就本地只有文案键、没有表",
                ],
                [
                    "`PlayerSegmentRules` 922",
                    "`PlayerSegmentRules`（`pkg_2076`）",
                    "922",
                    "与本任务三块数据无关，未纳入",
                ],
            ],
        )
    )
    add("")
    add("## 三、图鉴（`almanac`）")
    add("")
    add(
        f"植物 {lc['plants']} 条 + 僵尸 {lc['zombies']} 条 = {lc['plants'] + lc['zombies']} 条。"
        f"僵尸侧从 {lc['zombieTypesDefined']} 个 `ZombieType` 里筛出：{lc['zombiesWithoutNameKey']} 个没有 `ZOMBIE_<TYPE>` 名字键、"
        f"{lc['zombiesSpawnOnly']} 个只有 RTID 生成引用没有自己的定义（见 U1/U9）。"
    )
    add("")
    lines.extend(
        _table(
            ["字段", "来源", "说明"],
            [
                ["`id`", "`PlantAlmanacData.aliases[0]` / `ZombieType.TypeName`", "植物是别名，僵尸是类型名"],
                ["`nameKey`/`descKey`/`tooltipKey`", "推导：裸大写 id + `_DESCRIPTION`/`_TOOLTIP`", f"植物键实测 {lc['plantsWithNameKey']}/{lc['plants']} 命中"],
                ["`descHeaderKey`", "`ZOMBIE_<ID>_DESCRIPTION_HEADER`", "僵尸专属，图鉴卡标题行用"],
                ["`resolved`", "对照 `pkg_0231`（英）/`pkg_0232`（中）", "name/desc/tooltip/nameZh/descZh 五个布尔"],
                ["`world`/`worldSource`", "`PlantType.HomeWorld` / `ZombieType.HomeWorld`", "原样保留内部 token，不映射（U7）"],
                ["`levels`", "关卡包扫描（一.3）", "正向引用计数，`PlantExcludeList` 不算出现（U5）"],
                ["`stats`", "`AlmanacDataEntries[]`", "statType/statName/typeKey/valueKey/levelToUnlock/numberFormat"],
                ["`inPlantTypes`", "`PlantType` 是否有同名条目", "false 的条目没有世界与图鉴背景"],
            ],
        )
    )
    add("")
    add("覆盖率：")
    add("")
    lines.extend(
        _table(
            ["指标", "值"],
            [
                ["植物名字键可解析", _pct(lc["plantsWithNameKey"], lc["plants"])],
                ["植物有世界", _pct(lc["plantsWithWorld"], lc["plants"])],
                ["僵尸名字键可解析", _pct(lc["zombies"], lc["zombies"])],
                ["僵尸有世界", _pct(lc["zombiesWithWorld"], lc["zombies"])],
                ["植物有出场关卡", _pct(sum(1 for row in almanac["plants"] if row["levels"]), lc["plants"])],
                ["僵尸有出场关卡", _pct(sum(1 for row in almanac["zombies"] if row["levels"]), lc["zombies"])],
            ],
        )
    )
    add("")
    add("僵尸世界分布（`ZombieType.HomeWorld`，原样 token）：")
    add("")
    lines.extend(_table(["世界 token", "僵尸数"], [[key, str(value)] for key, value in world_counter.most_common()]))
    add("")
    add("植物世界分布（`PlantType.HomeWorld`，前 12）：")
    add("")
    lines.extend(
        _table(
            ["世界 token", "植物数"],
            [[key, str(value)] for key, value in plant_world_counter.most_common(12)],
        )
    )
    add("")
    add("图鉴统计行（`AlmanacDataEntries.statType`）分布（前 12）：")
    add("")
    lines.extend(_table(["statType", "出现次数"], [[key, str(value)] for key, value in stat_counter.most_common(12)]))
    add("")
    add(
        f"- 不在 `PlantType` 的图鉴条目 {len(lc['plantsNotInPlantTypes'])} 条："
        + "、".join(f"`{name}`" for name in lc["plantsNotInPlantTypes"])
        + "。"
    )
    add(
        "- 无名字键的植物："
        + "、".join(f"`{name}`" for name in lc["plantsWithoutNameKey"])
        + "（U3）。"
    )
    add(
        f"- 与客户端内容交集：`content/plants.json` {cross['contentPlants']} 条命中 {cross['almanacPlantsInContent']} 条，"
        f"`content/zombies.json` {cross['contentZombies']} 条命中 {cross['almanacZombiesInContent']} 条。"
        "交集小是原版事实：content 侧是客户端自建名册（含 `fused_*` 融合体），"
        "未命中的 id 全列在 JSON 的 `cross` 段，本层不替它们编图鉴。"
    )
    add("")
    add("## 四、花园（`garden`）")
    add("")
    add(
        f"掉落物 {gc['collectables']} 条、掉落类族 {len(gc['collectableClasses'])} 个、"
        f"Zen Garden 属性表 {gc['zenGardenTables']}/4 张、花盆 {gc['zenGardenPots']} 个、"
        f"植物奖励表 {gc['zenGardenPlantRewards']} 张、其中有定价的掉落物 {gc['collectablesWithPrice']} 条。"
    )
    add("")
    lines.extend(
        _table(
            ["字段", "来源", "说明"],
            [
                ["`typeName`", "`CollectableType.TypeName`", "如 `worldkey_pirate`/`pinata_egypt`/`sprout`"],
                ["`collectableClass`", "`CollectableType.CollectableClass`", "决定掉落表现"],
                ["`rewardDialogTitleKey`", "`RewardDialogTitle` 去方括号", "原版有缺键，解析不到的标 `rewardDialogTitleResolved=false`"],
                ["`image`/`popAnim`", "`StandaloneImage`/`PopAnim`", "美术资源名"],
                ["`soldAs`", "`StoreProductProps` 记号匹配", "`{sku, objectType, objectItem, matchKind, candidates, priceCoins/Gems/Mints/Usd, priceKind}`；无匹配为 `null`"],
                ["`storeCategory`", "掉落物名恰好是某个 `ObjectType` 品类名", "只记品类，不给价（如 `pinata`）"],
                ["`dropSources`", "`QuestMgr.CompletionAwards`/`QuestRewardTablesProps`/`ZenGardenPlantRewards`/`AwardConfig.GiftBoxRewards`/`StoreProductProps`", "「谁发这个东西」的表名与样例；表里没写到的来源不补"],
                ["`zenGarden.*`", "`pkg_2083` + `pkg_0004`", "生长时长、花盆成本、蜜蜂参数、植物奖励"],
            ],
        )
    )
    add("")
    add("掉落类族分布：")
    add("")
    lines.extend(_table(["collectableClass", "条数"], [[key, str(value)] for key, value in class_counter.most_common()]))
    add("")
    add("有定价的掉落物（`StoreProductProps` 命中明细）：")
    add("")
    lines.extend(
        _table(
            ["掉落物", "matchKind", "同形候选", "Sku（取第一条）", "ObjectItem", "计价字段", "价格"],
            [
                [
                    row["typeName"],
                    row["soldAs"]["matchKind"],
                    str(row["soldAs"]["candidates"]),
                    row["soldAs"]["sku"],
                    row["soldAs"]["objectItem"],
                    row["soldAs"]["priceKind"] or "（全空）",
                    row["soldAs"].get("price" + row["soldAs"]["priceKind"].title(), "")
                    or "（商品表里价格字段全空，本地无价）",
                ]
                for row in priced
            ],
        )
    )
    add("")
    add(
        f"其余 {gc['collectables'] - gc['collectablesWithPrice']} 条没有定价，原因是原版商品表本身覆盖不到："
        "565 条 `StoreProductProps` 里 447 条是 costume、61 条 plant、23 条 pinata、12 条 gameupgrade、"
        "9 条 eventenergy、4 条 mint、3 条 sprout，其余个位数。世界奖杯/危险房/世界钥匙/升级道具这类掉落物"
        "在原版是关卡奖励而非货架货品，所以 `soldAs` 为 `null`，本层不编价格（U6）。"
    )
    add(
        f"- 掉落来源（`dropSources`）：{gc['collectablesWithDropSource']}/{gc['collectables']} 条在本地表里能找到发放方，"
        f"涉及的表：{'、'.join('`' + name + '`' for name in gc['dropSourceTables']) or '（无）'}。"
        "世界奖杯/危险房这类只在关卡结算里给的东西，本地没有发放表，条目会留空（U6）。"
    )
    add("")
    lines.extend(
        _table(
            ["Zen Garden 参数", "值"],
            [[key, str(value)] for key, value in (garden["zenGarden"]["props"] or {}).items()]
            + [
                ["花盆定义（`Pots`）", f"{gc['zenGardenPots']} 个"],
                ["蜜蜂（`BeeProps`）", "、".join(sorted((garden["zenGarden"]["bee"] or {}).keys())[:8]) + " …"],
                ["植物奖励表", "、".join(f"`{row['id']}`" for row in garden["zenGarden"]["plantRewards"])],
            ],
        )
    )
    add("")
    add("## 五、成就·任务（`quests` / `achievements`）")
    add("")
    add(
        f"`QuestMgr` 任务 {qc['quests']} 条（{qc['questsWithRewards']} 条带完成奖励）、"
        f"每日任务定义 {qc['dailyQuestDefs']} 条（{qc['dailyWithRewards']} 条带奖励）、"
        f"奖励表 {qc['rewardTables']} 张、任务页签 {qc['questTabs']} 个、成就 {achievements['counts']['achievements']} 条。"
    )
    add("")
    lines.extend(
        _table(
            ["字段", "来源", "说明"],
            [
                ["`id`", "`Quests[*].<wrapper>.UniqueID`", "如 `EPICQUEST`/`BEACH`/`DAILY_2_ADVENTURE_DQ`"],
                ["`targetType`", "外层包装类名", "目标类型：`ChallengeLevelQuestData`/`EpicQuestData`/`LevelQuestData`/…"],
                ["`slot`/`category`/`theme`", "`Slot`/`QuestCategory`/`OverrideQuestTheme`", "决定挂在哪个页签"],
                ["`params`", "`LevelName`/`ActionsToPerform`/`CountRemainingLabel`/`Priority`/`Repeatable`/`Disabled`/`UniqueIDList` 长度/`Prerequisites`", "目标参数，原样保留"],
                ["`rewards`", "`CompletionAwards.Awards[]`", "`{type, subtype, amount}`；`amount` 是 `Amount` 原值；没有就是 `null`"],
                ["`rewardSource`", "本层标注", "`QuestMgr.CompletionAwards` / `QuestData.CompletionAwards` / `unknown`"],
                ["`achieve.*`", "`ACHIEVE_*_TITLE`/`_DESC` 文案键", "成就本地无表，按文案键枚举，奖励 serverOnly"],
            ],
        )
    )
    add("")
    add("任务分类与包装类：")
    add("")
    lines.extend(
        _table(["QuestCategory", "条数"], [[key, str(value)] for key, value in qc["questsByCategory"].items()])
    )
    add("")
    lines.extend(
        _table(["包装类（目标类型）", "条数"], [[key, str(value)] for key, value in qc["questsByTargetType"].items()])
    )
    add("")
    add("奖励类型分布（按奖项条数，含 QuestMgr 240 条与每日定义 11 条）：")
    add("")
    lines.extend(_table(["奖项 Type", "条数"], [[key, str(value)] for key, value in reward_counter.most_common()]))
    add("")
    add(
        f"- 奖励行 {qc['rewardRows']} 条，其中 {qc['rewardRowsWithAmount']} 条带数值："
        "`amount` 取 `CompletionAwards.Awards[].Amount` 原值（JSON 数字原样转文本，不做单位换算、不补缺省）；"
        "空串表示原表没给这个字段。"
    )
    add("")
    add("任务页签（`QuestTabCategoryData`）：")
    add("")
    lines.extend(
        _table(
            ["页签", "TabLabel 键", "覆盖的 QuestCategory", "带计时"],
            [
                [
                    row["id"],
                    "`" + row["tabLabelKey"] + "`" if row["tabLabelKey"] else "（无）",
                    "、".join(row["questCategories"][:6]) + (" …" if len(row["questCategories"]) > 6 else ""),
                    "是" if row["showTimer"] else "否",
                ]
                for row in quests["tabs"]
            ],
        )
    )
    add("")
    add(
        "- **成就是原版没有的部分**：本地只有 `ACHIEVE_*` 文案键（"
        f"{achievements['counts']['achieveKeys']} 个键，其中 {achievements['counts']['achievements']} 个有 `_TITLE`、"
        f"{achievements['counts']['withDescKey']} 个有 `_DESC`、{achievements['counts']['withExtraNameKey']} 个有 `_NAME`），"
        "没有任何成就定义表或奖励表。因此每条都是 `rewards=null` + `serverOnly=true`（U4）。"
    )
    add(
        f"- 奖励表（`quest_rewards.TablesConfig`）{qc['rewardTables']} 张，按 `Difficulty` 分档，"
        "每档给 `pinata` 类型 + `SubType`（世界）+ `MinAmount`/`MaxAmount`/`Weight` 的随机奖励池。"
    )
    add("")
    add("## 六、本地化覆盖")
    add("")
    lines.extend(
        _table(
            ["文件", "键值对", "判定语种", "含 CJK 的值数"],
            [
                [
                    row["file"],
                    str(row["pairs"]),
                    "中文" if row["cjk"] * 2 > row["pairs"] else "英文",
                    str(row["cjk"]),
                ]
                for row in src_meta["locStrings"]["files"]
            ],
        )
    )
    add("")
    add("- 语种按「值里有没有 CJK」判定，不依赖文件名先后；缺键不报错，只在 `resolved` 里标 false。")
    add(
        "- 键名去方括号的规则只作用于 objdata 里写成 `[KEY]` 的字段"
        "（`TypeStringID`/`ValueStringID`/`QuestName`/`Description`/`TabLabel`/`RewardDialogTitle`），"
        "LawnStrings 本身的键不带方括号。"
    )
    add("")
    add("## 七、原版没有的部分（明确缺口）")
    add("")
    add("1. **僵尸图鉴花名册**：没有 roster 表，`AlmanacOffset`/`AlmanacScale` 只有零星 "
        f"{lc['zombieSheetsWithAlmanacOffset']} 条覆盖（U1）。")
    add("2. **成就定义与奖励**：只有文案键，奖励在服务器侧（U4）。")
    add("3. **花园物件售价**：`CollectableType` 本身不带价格，绝大多数掉落物在原版就不是货架商品（U6）。")
    add("4. **植物图鉴的世界映射**：`HomeWorld` 是内部 token，与 `content/worlds.json` 的 id 不同源（U7）。")
    add("5. **僵尸图鉴的展示顺序/分组**：没有数据，`almanac.zombies` 按 id 字典序输出（U1）。")
    add("")
    add("## 八、未知项")
    add("")
    lines.extend(_table(["编号", "主题", "问题"], [[item["id"], item["topic"], item["question"]] for item in payload["unknowns"]]))
    add("")
    add("## 九、复现")
    add("")
    add("```")
    add("python tools/contentc/metagame.py            # 写 native/generated/metagame.json 与本报告")
    add("python tools/contentc/metagame.py --check    # 逐字节校验两个产物是否最新（过期返回 2）")
    add("python -m unittest tools.tests.test_metagame -v")
    add("```")
    add("")
    counts = payload["counts"]
    add(
        f"条数一览：almanac {counts['almanacEntries']}（植物 {counts['almanacPlants']} + 僵尸 {counts['almanacZombies']}）、"
        f"garden {counts['gardenCollectables']}、quests {counts['quests']}（带奖励 {counts['questsWithRewards']}）、"
        f"achievements {counts['achievements']}、unknowns {counts['unknowns']}。"
    )
    return "\n".join(lines) + "\n"


def summarize(payload: dict) -> str:
    counts = payload["counts"]
    quests = payload["quests"]["counts"]
    return (
        f"almanac={counts['almanacPlants']}p+{counts['almanacZombies']}z "
        f"garden={counts['gardenCollectables']} "
        f"quests={counts['quests']}({counts['questsWithRewards']} rewards) "
        f"daily={quests['dailyQuestDefs']} achievements={counts['achievements']} unknowns={counts['unknowns']}"
    )


def write_outputs(payload: dict, json_path: Path, report_text: str, report_path: Path) -> None:
    from tools.contentc import emit

    emit.write_text(json_path, render_json(payload))
    emit.write_text(report_path, report_text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="编译图鉴 / 花园 / 成就·任务三块元游戏数据")
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB, help="解包目录（默认 work/obb_packages）")
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON, help="产物 JSON 路径")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="产物报告路径")
    parser.add_argument("--plants", type=Path, default=DEFAULT_PLANTS, help="content/plants.json")
    parser.add_argument("--zombies", type=Path, default=DEFAULT_ZOMBIES, help="content/zombies.json")
    parser.add_argument("--check", action="store_true", help="逐字节校验产物是否最新")
    parser.add_argument("-n", "--dry-run", action="store_true", help="只算不写")
    args = parser.parse_args(argv)

    if not args.obb.is_dir():
        print(f"找不到 obb 解包目录：{args.obb}", file=sys.stderr)
        return 1

    payload = build(args.obb, args.plants, args.zombies)
    summary = summarize(payload)
    json_text = render_json(payload)
    report_text = render_report(payload)

    if args.check:
        stale = []
        for path, text in ((args.json, json_text), (args.report, report_text)):
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                stale.append(path)
        if stale:
            print("产物过期：" + "、".join(str(path) for path in stale))
            return 2
        print(f"产物已是最新：{summary}")
        return 0

    if args.dry_run:
        print(f"（dry-run）{summary}")
        return 0

    write_outputs(payload, args.json, report_text, args.report)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
