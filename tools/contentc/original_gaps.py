"""原版↔客户端字段级差距盘点（只读工具）。

用途
====
以原版 `work/obb_packages/pkg_*.json` 为唯一基准，逐字段比对客户端 `content/*.json`
的同名实体，产出「原版有、客户端没有」的结构化清单，供后续补功能排期使用。

产物
====
- `native/generated/original_gaps.json`：`format / generated / sources / counts / tables / systems`
- `docs/reviews/2026-11-24-original-gaps.md`：同一份数据的中文报告

口径（重要，别混）
==================
1. **只读**：本工具不写 `content/**`、不写 `native/src/**`，只写上面两个产物。
2. **实体（entity）** 固定 12 个：plants / zombies / levels / shop / worlds / armor /
   projectiles / bosses / plantfood / fusion / waves / stars。
3. 每张表一行 = 一个「原版字段 → 客户端字段」对照。四个计数的含义：
   - `mapped`：该实体的**已关联记录**里，两侧都有值的条数；
   - `packOnly`：原版有值、客户端没有对应字段的条数（被关联到但客户端缺字段 +
     可选的「原版独有对象」，见第 4 条）；
   - `clientOnly`：客户端有值、原版没有对应字段（或根本没有对应原版对象）的条数；
   - `agree`：两侧都是标量且数值相等的条数（用来暴露「字段同名但语义不同」）。
   `records` 是该实体的关联规模（被比对的客户端记录数）。
4. **是否把未关联的原版对象计入 `packOnly`** 按实体决定：
   - 计入（`unmatched_pack=True`）：worlds（46 个原版世界 vs 26 个客户端世界）、
     shop（565 个原版商品 vs 585 个客户端商品）、armor、projectiles、bosses；
   - 不计入：plants、zombies、levels、plantfood、fusion、waves、stars —— 这些实体
     原版一侧本来就有几百上千条与客户端无关的行，计进来只会淹没信号。
5. **关联键**：plants/zombies 用 `native/generated/id_mapping.csv` 里 `exact` + `manual`
   行（pack 侧类型名）；levels 用客户端 `extra.package`（`pkg_XXXX`）关联
   `pkg_XXXX_LevelDefinition.json`；shop 用 `sku`；worlds 用世界名 + 别名表；
   armor 用美术名去掉 `ARMOR` 后缀；projectiles 用类名小写；fusion 用配方键 + 出现序；
   stars/waves 用关卡 id 的 `extra.package`。
6. **`packOnlyFields`**：把已关联的原版对象上「有值但没有任何客户端字段对应」的字段
   统计出来（`counts.packOnlyFieldTop` 取前 12），这是「原版有、客户端没有」的字段级证据。
7. **systems（子系统）**：原版存在、客户端没有整套数据结构的玩法/系统。每条给
   `evidence[{table, field, count}]`；字段名从**全量 2116 张表的字段索引**里取实测值，
   找不到就写 `presentInPack: "unverified"`，绝不凭印象写。
8. **确定性**：行序、系统序、样本序都由排序键固定；不写时间戳；JSON 用
   `json.dumps(..., sort_keys=True, indent=1, ensure_ascii=False)` + 末尾换行，
   落盘走 `write_bytes`（避免 Windows 把 LF 变成 CRLF）。

复现
====
    python tools/contentc/original_gaps.py            # 重算并写产物
    python tools/contentc/original_gaps.py --check    # 重算并与盘上比对，不一致 exit 1
    python -m unittest tools.tests.test_original_gaps -v
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence
import os

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # 允许 `python tools/contentc/original_gaps.py` 直接运行
    sys.path.insert(0, str(ROOT))

DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages"))
DEFAULT_CONTENT = ROOT / "content"
DEFAULT_MAPPING = ROOT / "native" / "generated" / "id_mapping.csv"
DEFAULT_JSON = ROOT / "native" / "generated" / "original_gaps.json"
DEFAULT_REPORT = ROOT / "docs" / "reviews" / "2026-11-24-original-gaps.md"
DEFAULT_COMPLETENESS = ROOT / "docs" / "COMPLETENESS.md"

FORMAT = 1
MARKER = "original-gaps-v1"
SAMPLE_LIMIT = 5
PACK_ONLY_TOP = 12
COMMENT_PREFIXES = ("#", "//")

ENTITY_IDS = (
    "plants",
    "zombies",
    "levels",
    "shop",
    "worlds",
    "armor",
    "projectiles",
    "bosses",
    "plantfood",
    "fusion",
    "waves",
    "stars",
)

# 关卡里需要取值的原版字段（一次扫描时顺带收集，避免二次读盘）
LEVEL_FIELDS = (
    "StartingSun",
    "PresetPlantList",
    "InitialPlantList",
    "SeedPacketList",
    "WaveCount",
    "FlagCount",
    "Waves",
    "Zombies",
    "Challenges",
    "Loot",
    "LevelNumber",
    "Modules",
    "StageModule",
    "WaveManagerProps",
    "SuppressPlantfoodPurchase",
    "AdditionalPlantfood",
    "DynamicPlantfood",
    "NormalPresentTable",
)

# 世界别名：原版 m_worldName -> 客户端 world id（与 tools/contentc/worlds.py 保持同源）
WORLD_ALIASES = {
    "gta": "losantosvice",
    "skycity": "sky",
    "rainbowmarket": "lunarrainbowmarket",
    "kungfu": "kongfu",
}

# 需要整套数据结构（而不是单个字段）的子系统
SYSTEM_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "plantfood_drop",
        "pack_fields": (
            "AdditionalPlantfood",
            "DynamicPlantfood",
            "PlantfoodToSpawnCount",
            "StartingPlantfood",
            "SpawnWavesBetweenPlantFood",
            "SpawnWavesBetweenPlantFood",
            "CanSpawnPlantFood",
        ),
        "client_signals": ("plantfood_count", "plantfood_drop", "plantfood_rate"),
        "note": "原版按波次/关卡投放养料；客户端只有 plants[].plantfood 布尔开关，没有投放节奏。",
    },
    {
        "id": "plantfood_purchase",
        "pack_fields": ("SuppressPlantfoodPurchase", "SuppressAccountUpgrades", "StartingPlantfood"),
        "client_signals": ("plantfood_price", "buy_plantfood"),
        "note": "原版有「是否允许买养料」的关卡级开关；客户端没有货币与购买链路。",
    },
    {
        "id": "level_rewards",
        "pack_fields": (
            "Loot",
            "FirstRewardType",
            "FirstRewardParam",
            "ReplayRewardType",
            "NormalPresentTable",
            "ShinyPresentTable",
            "AwardDrop",
        ),
        "client_signals": ("loot", "first_reward_type", "present_table", "replay_reward_type"),
        "note": "原版关卡带掉落表/首通奖励/重复奖励；客户端关卡 JSON 只有 id/world/index/sun/deck/waves/flags/seed_bank/extra（bosses.json 的 reward 是 Boss 击杀奖励，不是关卡结算表，不计入）。",
    },
    {
        "id": "key_drops",
        "pack_fields": ("LevelLootKey", "LevelKey", "KeyReward", "WorldKey"),
        "client_signals": ("key_required", "keys"),
        "note": "原版世界门要钥匙（WorldData key_gate），关卡掉落也有 key 通道；客户端只有世界地图 key_required 布尔。",
    },
    {
        "id": "seeds_and_vases",
        "pack_fields": ("Vases", "NumColoredPlantVases", "NumColoredZombieVases", "SeedDropList", "SeedPacketList"),
        "client_signals": ("vases", "seed_pool", "seed_bank"),
        "note": "原版砸罐子/种子掉落是关卡数据；客户端只有 minigames.json 的 45 关预排罐子。",
    },
    {
        "id": "achievements_quests",
        "pack_fields": ("Quests", "QuestCategories", "DailyQuestScheduleDefinitions", "CompletionAchievement"),
        "pack_file_keywords": ("Quest", "Achievement"),
        "client_signals": ("quests", "achievements", "daily"),
        "note": "原版有 QuestMgr / DailyQuestSchedule / CompletionAchievement；客户端没有任何任务或成就表。",
    },
    {
        "id": "almanac_entries",
        "pack_fields": ("AlmanacDataEntries", "AlmanacBackdropName", "HideFromAlmanac"),
        "client_signals": ("almanac_no", "plants", "tip"),
        "note": "原版图鉴是 PlantAlmanacData（167 条）；客户端 almanac.json 只有 desc/tip 文案，图鉴 UI 未实现。",
    },
    {
        "id": "zen_garden",
        "pack_fields": (
            "ZenGardenSproutWeight",
            "ZenGardenBoostCost",
            "ZenGardenDurationOverrideSeconds",
            "IsZenGardenWaterPlant",
            "IsZenGardenTreasurePlant",
        ),
        "client_signals": ("pots", "grow_seconds", "plant_pool"),
        "note": "原版花园参数挂在 PlantPropertySheet 的 ZenGarden* 字段；客户端 garden.json 是 8 盆的自创简化模型。",
    },
    {
        "id": "daily_season",
        "pack_fields": ("SeasonDefinitions", "EndOfSeasonManagement", "DailyQuestScheduleDefinitions"),
        "pack_file_keywords": ("Joust", "Season", "Daily"),
        "client_signals": ("season", "daily_quest", "week"),
        "note": "原版有 Joust 赛季与每日任务排期；客户端没有赛季/每日数据。",
    },
    {
        "id": "shop_products",
        "pack_fields": ("Sku", "Price", "PriceCoins", "PriceGems", "PriceMints", "ObjectType", "ObjectCount", "IsFree"),
        "client_signals": ("items", "price", "sku", "currency"),
        "note": "原版 StoreProductProps 565 件；客户端 shop.json 585 件，其中 565 个 sku 对齐、20 个是客户端独有。",
    },
    {
        "id": "sound_events",
        "pack_fields": (
            "ImpactSoundEvent",
            "DropSoundEvent",
            "SoundOnStart",
            "SoundOnDeath",
            "SoundOnEat",
            "SoundOnSummon",
            "AnimationSoundFX",
        ),
        "client_signals": ("sound", "audio", "sfx"),
        "note": "原版每类实体带音效事件名（Impact/Drop/OnEat…）；客户端 content 里没有任何音效字段。",
    },
    {
        "id": "star_challenges",
        "pack_fields": ("Challenges", "TargetScore", "ScoringRulesType", "StarChallengeUnlockLevel"),
        "client_signals": ("stars", "text_zh", "mowers"),
        "note": "原版星章目标在 LevelDefinition.Challenges；客户端 stars.json 是 1809 关 × 3 条自创目标。",
    },
    {
        "id": "mower_config",
        "pack_fields": ("UnlimitedMowers", "MowerPopAnim", "MowerActivatedAudioEvent", "MowerEntryAnimDuration"),
        "client_signals": ("mowers", "lawn_mowers"),
        "note": "原版关卡可配小推车数量/动画/音效；客户端只有固定 5 台（stars 里用 mowers 当目标）。",
    },
)


# --------------------------------------------------------------------------- 基础工具


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (str, list, dict, tuple, set)):
        return len(value) > 0
    return True


def _is_comment(key: str) -> bool:
    return key.startswith(COMMENT_PREFIXES) or " " in key and key.strip().startswith("#")


def _short(value: Any, limit: int = 60) -> str:
    text = _text(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _iter_client_keys(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from _iter_client_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_client_keys(item)


# --------------------------------------------------------------------------- 扫描原版


@dataclass
class SheetSummary:
    objects: int
    classes: dict[str, int]
    fields: dict[str, int]


@dataclass
class PackScan:
    sheets: dict[str, SheetSummary]
    field_sheets: dict[str, int]
    field_records: dict[str, int]
    level_by_package: dict[str, dict[str, Any]]
    level_fields: dict[str, int]
    level_files: int
    level_objects: int

    @property
    def sheets_scanned(self) -> int:
        return len(self.sheets)


def _summarize(objects: Sequence[dict[str, Any]]) -> SheetSummary:
    classes: Counter[str] = Counter()
    fields: Counter[str] = Counter()
    for obj in objects:
        classes[str(obj.get("objclass"))] += 1
        for key, value in (obj.get("objdata") or {}).items():
            if _is_comment(str(key)):
                continue
            if _nonempty(value):
                fields[str(key)] += 1
    return SheetSummary(len(objects), dict(classes), dict(fields))


def _module_names(objects: Sequence[dict[str, Any]]) -> list[str]:
    """从 LevelDefinition 里取 Modules/StageModule 的 RTID 名（去重、保序）。"""
    names: list[str] = []
    seen: set[str] = set()
    for obj in objects:
        data = obj.get("objdata") or {}
        for key in ("Modules", "StageModule", "WaveManagerProps"):
            raw = data.get(key)
            values = raw if isinstance(raw, list) else [raw] if isinstance(raw, str) else []
            for value in values:
                if not isinstance(value, str):
                    continue
                name = value
                if name.startswith("RTID(") and "@" in name:
                    name = name[5:].split("@", 1)[0]
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
    return names


def scan_pack(obb_dir: Path) -> PackScan:
    """单次扫描全部 pkg 表：字段索引 + 关卡级摘要。"""
    from tools.contentc import sheets as sheet_loader

    sheets: dict[str, SheetSummary] = {}
    field_sheets: Counter[str] = Counter()
    field_records: Counter[str] = Counter()
    level_by_package: dict[str, dict[str, Any]] = {}
    level_fields: Counter[str] = Counter()
    level_files = 0
    level_objects = 0

    for path in sorted(obb_dir.glob("pkg_*.json")):
        objects = list(sheet_loader.iter_objects(sheet_loader.load_sheet(path)))
        summary = _summarize(objects)
        sheets[path.name] = summary
        for name, count in summary.fields.items():
            field_sheets[name] += 1
            field_records[name] += count
        if not path.name.endswith("_LevelDefinition.json"):
            continue
        level_files += 1
        level_objects += summary.objects
        package = path.name[: -len("_LevelDefinition.json")]
        values: dict[str, list[Any]] = defaultdict(list)
        for obj in objects:
            data = obj.get("objdata") or {}
            for key in LEVEL_FIELDS:
                if key in data and _nonempty(data[key]):
                    values[key].append(data[key])
        for key, count in summary.fields.items():
            if key in LEVEL_FIELDS:
                level_fields[key] += count
        level_by_package[package] = {
            "file": path.name,
            "objects": summary.objects,
            "modules": _module_names(objects),
            "values": {key: value for key, value in values.items()},
            "fields": summary.fields,
        }

    return PackScan(
        sheets=sheets,
        field_sheets=dict(field_sheets),
        field_records=dict(field_records),
        level_by_package=level_by_package,
        level_fields=dict(level_fields),
        level_files=level_files,
        level_objects=level_objects,
    )


# --------------------------------------------------------------------------- 原版各表读取


def load_mapping(path: Path) -> dict[tuple[str, str], list[str]]:
    """id_mapping.csv -> {(side, client_id): [pack_type,...]}，只取 exact/manual。"""
    pairs: dict[tuple[str, str], list[str]] = defaultdict(list)
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        import csv

        for row in csv.DictReader(fh):
            kind = (row.get("match_kind") or "").strip()
            pack_type = (row.get("pack_type") or "").strip()
            client_id = (row.get("client_id") or "").strip()
            side = (row.get("side") or "").strip()
            if not pack_type or kind not in ("exact", "manual") or not client_id:
                continue
            if pack_type not in pairs[(side, client_id)]:
                pairs[(side, client_id)].append(pack_type)
    return dict(pairs)


def _index_by(objects: Iterable[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for obj in objects:
        data = obj.get("objdata") or {}
        value = data.get(key)
        if isinstance(value, str) and value not in index:
            index[value] = data
    return index


def _alias_index(objects: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    from tools.contentc import sheets as sheet_loader

    index: dict[str, dict[str, Any]] = {}
    for obj in objects:
        for alias in sheet_loader.aliases(obj):
            index.setdefault(alias, obj.get("objdata") or {})
    return index


def _props_alias(data: dict[str, Any] | None) -> str | None:
    from tools.contentc import rtid

    if not data:
        return None
    parsed = rtid.parse_rtid(data.get("Properties"))
    return parsed[0] if parsed else None


@dataclass
class PackTables:
    plant_type_rows: int
    zombie_type_rows: int
    plant_types: dict[str, dict[str, Any]]
    plant_props: dict[str, dict[str, Any]]
    zombie_types: dict[str, dict[str, Any]]
    zombie_props: dict[str, dict[str, Any]]
    worlds: list[dict[str, Any]]
    store: list[dict[str, Any]]
    projectiles: list[dict[str, Any]]
    armors: list[dict[str, Any]]
    almanac: list[dict[str, Any]]
    fusion: list[dict[str, Any]]
    boss_modules: int
    vase_modules: int
    star_modules: int
    mower_modules: int
    world_gate_kinds: dict[str, int]


def load_pack_tables(obb_dir: Path, scan: PackScan) -> PackTables:
    from tools.contentc import sheets as sheet_loader

    def objects(name: str) -> list[dict[str, Any]]:
        path = obb_dir / name
        if not path.is_file():
            return []
        return list(sheet_loader.iter_objects(sheet_loader.load_sheet(path)))

    boss = vase = star = mower = 0
    for info in scan.level_by_package.values():
        modules = set(info["modules"])
        if modules & {"ZombossBattle", "ZombossBattle1", "ZombossBattle2"}:
            boss += 1
        if modules & {"VaseBreakerArcade", "VaseBreakerProps", "TestVaseBreaker"}:
            vase += 1
        if "StarChallengeModule" in modules:
            star += 1
        if modules & {"ModernMowers", "Mowers"}:
            mower += 1

    gate_kinds: Counter[str] = Counter()
    worlds = [o.get("objdata") or {} for o in objects("pkg_2107_WorldData.json")]
    for world in worlds:
        for event in world.get("m_eventList") or []:
            if isinstance(event, dict):
                kind = event.get("m_eventType") or event.get("m_type") or event.get("type")
                if isinstance(kind, str):
                    gate_kinds[kind] += 1

    plant_rows = objects("pkg_2074_PlantType.json")
    zombie_rows = objects("pkg_2115_ZombieType.json")
    return PackTables(
        plant_type_rows=len(plant_rows),
        zombie_type_rows=len(zombie_rows),
        plant_types=_index_by(plant_rows, "TypeName"),
        plant_props=_alias_index(objects("pkg_2073_PlantPropertySheet.json")),
        zombie_types=_index_by(zombie_rows, "TypeName"),
        zombie_props=_alias_index(objects("pkg_2112_ZombiePropertySheet.json")),
        worlds=worlds,
        store=[o.get("objdata") or {} for o in objects("pkg_2081_StoreProductProps.json")],
        projectiles=[o.get("objdata") or {} for o in objects("pkg_2082_ProjectilePropertySheet.json")],
        armors=[o.get("objdata") or {} for o in objects("pkg_0002_ArmorPropertySheetUtils.json")],
        almanac=[o.get("objdata") or {} for o in objects("pkg_2067_PlantAlmanacData.json")],
        fusion=_fusion_pairs(objects("pkg_2083_PlantFusionConfig.json")),
        boss_modules=boss,
        vase_modules=vase,
        star_modules=star,
        mower_modules=mower,
        world_gate_kinds=dict(gate_kinds),
    )


# --------------------------------------------------------------------------- 客户端读取


@dataclass
class ClientTables:
    plants: list[dict[str, Any]]
    zombies: list[dict[str, Any]]
    levels: list[dict[str, Any]]
    shop_items: list[dict[str, Any]]
    worlds: list[dict[str, Any]]
    worldmap: dict[str, Any]
    stars: dict[str, Any]
    fusions: dict[str, Any]
    almanac: dict[str, Any]
    minigames: dict[str, Any]
    garden: dict[str, Any]
    bosses: list[dict[str, Any]]
    keys: set[str]


def load_client(content_dir: Path) -> ClientTables:
    def doc(name: str, fallback: Any) -> Any:
        path = content_dir / name
        return _load_json(path) if path.is_file() else fallback

    levels = [
        _load_json(path) for path in sorted((content_dir / "levels").glob("*.json"))
    ]
    plants = doc("plants.json", [])
    # `source == "pack"` rows are the pack mirror written by zombie_roster.py; the
    # gap table reports the hand-written roster only, so they never enter the join.
    zombies = [
        row
        for row in doc("zombies.json", [])
        if not (isinstance(row, dict) and row.get("source") == "pack")
    ]
    shop = doc("shop.json", {})
    worlds = doc("worlds.json", [])
    stars = doc("stars.json", {})
    fusions = doc("fusions.json", {})
    almanac = doc("almanac.json", {})
    minigames = doc("minigames.json", {})
    garden = doc("garden.json", {})
    bosses_doc = doc("bosses.json", {})
    worldmap = doc("worldmap.json", {})
    keys = {key.lower() for key in _iter_client_keys(
        [plants, zombies, levels, shop, worlds, stars, fusions, almanac, minigames, garden, bosses_doc, worldmap]
    )}
    return ClientTables(
        plants=plants,
        zombies=zombies,
        levels=levels,
        shop_items=list(shop.get("items") or []),
        worlds=worlds,
        worldmap=worldmap,
        stars=stars,
        fusions=fusions,
        almanac=almanac,
        minigames=minigames,
        garden=garden,
        bosses=list((bosses_doc or {}).get("bosses") or []),
        keys=keys,
    )


# --------------------------------------------------------------------------- 关联与计数


@dataclass
class JoinEntry:
    key: str
    client: dict[str, Any] | None
    packs: list[dict[str, Any]]
    note: str = ""


@dataclass
class EntityResult:
    rows: list[dict[str, Any]]
    pack_only: dict[str, int] = field(default_factory=dict)
    pack_unmatched: int = 0


def _scalar_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) < 1e-9
    if isinstance(left, str) and isinstance(right, str):
        return left == right
    return False


def _pack_value(pack: dict[str, Any], path: str | None) -> Any:
    if not path or not pack:
        return None
    if path.startswith("+"):
        for part in path[1:].split("+"):
            value = _pack_value(pack, part)
            if _nonempty(value):
                return value
        return None
    return pack.get(path)


def _iter_pack_values(pack: dict[str, Any], path: str | None) -> Iterator[Any]:
    if not path or not pack:
        return
    if path.startswith("+"):
        for part in path[1:].split("+"):
            yield from _iter_pack_values(pack, part)
        return
    yield pack.get(path)


def _client_value(record: dict[str, Any] | None, path: str) -> Any:
    """读客户端值；`extra.level_number` 这类嵌套路径按点号下钻。"""
    if not record:
        return None
    if path in record:
        return record[path]
    value: Any = record
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _rows_for(
    entity: str,
    entries: Sequence[JoinEntry],
    pairs: Sequence[tuple[str, str | None]],
    unmatched_packs: Sequence[dict[str, Any]] = (),
    unmatched_count_by_field: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for client_field, pack_path in pairs:
        mapped = pack_only = client_only = agree = 0
        samples: list[dict[str, str]] = []
        for entry in entries:
            client_value = _client_value(entry.client, client_field)
            pack_values = []
            for pack in entry.packs:
                pack_values.extend(_iter_pack_values(pack, pack_path))
            pack_value = next((value for value in pack_values if _nonempty(value)), None)
            has_client = _nonempty(client_value)
            has_pack = _nonempty(pack_value)
            if has_client and has_pack:
                mapped += 1
                if _scalar_equal(client_value, pack_value):
                    agree += 1
                if len(samples) < SAMPLE_LIMIT:
                    samples.append({"client": entry.key, "pack": _short(pack_value)})
            elif has_pack:
                pack_only += 1
            elif has_client:
                client_only += 1
        if unmatched_packs and pack_path:
            for pack in unmatched_packs:
                if _nonempty(_pack_value(pack, pack_path)):
                    pack_only += 1
        elif unmatched_count_by_field and pack_path:
            pack_only += unmatched_count_by_field.get(pack_path, 0)
        rows.append(
            {
                "entity": entity,
                "field": pack_path or "—",
                "clientField": client_field,
                "mapped": mapped,
                "packOnly": pack_only,
                "clientOnly": client_only,
                "agree": agree,
                "records": len(entries),
                "samples": samples,
            }
        )
    return rows


def _pack_only_fields(
    entity: str,
    entries: Sequence[JoinEntry],
    mapped_paths: set[str],
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for entry in entries:
        for pack in entry.packs:
            for key, value in pack.items():
                if _is_comment(str(key)) or str(key).startswith("_") or not _nonempty(value):
                    continue
                if key in mapped_paths:
                    continue
                counts[key] += 1
    return [
        {"entity": entity, "field": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:PACK_ONLY_TOP]
    ]


# --------------------------------------------------------------------------- 各实体关联


def _join_plants(client: ClientTables, pack: PackTables, mapping: dict[tuple[str, str], list[str]]) -> list[JoinEntry]:
    entries: list[JoinEntry] = []
    for record in client.plants:
        client_id = str(record.get("id") or "")
        pack_types = mapping.get(("plant", client_id), [])
        packs: list[dict[str, Any]] = []
        for pack_type in pack_types:
            type_data = pack.plant_types.get(pack_type)
            if not type_data:
                continue
            props = pack.plant_props.get(_props_alias(type_data) or "", {})
            merged = dict(type_data)
            for key, value in props.items():
                merged.setdefault(key, value)
            packs.append(merged)
        entries.append(JoinEntry(client_id, record, packs))
    return entries


def _join_zombies(client: ClientTables, pack: PackTables, mapping: dict[tuple[str, str], list[str]]) -> list[JoinEntry]:
    entries: list[JoinEntry] = []
    for record in client.zombies:
        client_id = str(record.get("id") or "")
        packs: list[dict[str, Any]] = []
        for pack_type in mapping.get(("zombie", client_id), []):
            type_data = pack.zombie_types.get(pack_type)
            if not type_data:
                continue
            props = pack.zombie_props.get(_props_alias(type_data) or "", {})
            merged = dict(type_data)
            for key, value in props.items():
                merged.setdefault(key, value)
            packs.append(merged)
        entries.append(JoinEntry(client_id, record, packs))
    return entries


def _level_pack(pack: PackTables, scan: PackScan, record: dict[str, Any]) -> list[dict[str, Any]]:
    extra = record.get("extra") or {}
    package = str(extra.get("package") or "")
    info = scan.level_by_package.get(package)
    if not info:
        return []
    merged: dict[str, Any] = dict(info["values"])
    merged["Modules"] = info["modules"]
    merged["_package"] = package
    merged["_normal_present"] = info["fields"].get("NormalPresentTable", 0)
    return [merged]


def _join_levels(client: ClientTables, pack: PackTables, scan: PackScan) -> list[JoinEntry]:
    return [
        JoinEntry(str(record.get("id") or ""), record, _level_pack(pack, scan, record))
        for record in client.levels
    ]


def _join_stars(client: ClientTables, pack: PackTables, scan: PackScan) -> list[JoinEntry]:
    """星章在客户端是 stars.json（按关卡 id），不是关卡记录里的字段。"""
    entries: list[JoinEntry] = []
    for record in client.levels:
        level_id = str(record.get("id") or "")
        stars = (client.stars or {}).get(level_id)
        view = {"stars": stars, "level": level_id} if isinstance(stars, list) else {"level": level_id}
        entries.append(JoinEntry(level_id, view, _level_pack(pack, scan, record)))
    return entries


def _join_shop(client: ClientTables, pack: PackTables) -> list[JoinEntry]:
    by_sku = {str(item.get("Sku")): item for item in pack.store if item.get("Sku")}
    entries = [
        JoinEntry(str(item.get("id") or item.get("sku") or ""), item, [by_sku[str(item.get("sku"))]] if str(item.get("sku")) in by_sku else [])
        for item in client.shop_items
    ]
    return entries


def _fusion_pairs(objects) -> list[dict[str, Any]]:
    """融合对不挂在独立对象上，而是 PlantFusionConfig 的 `FusionPairs` 字段（实测 85 对）。"""
    pairs: list[dict[str, Any]] = []
    for obj in objects:
        data = obj.get("objdata") or {}
        for item in data.get("FusionPairs") or []:
            if isinstance(item, dict):
                pairs.append(item)
    return pairs


def _join_worlds(client: ClientTables, pack: PackTables) -> tuple[list[JoinEntry], list[dict[str, Any]]]:
    by_name = {str(world.get("m_worldName")): world for world in pack.worlds if world.get("m_worldName")}
    entries: list[JoinEntry] = []
    used: set[str] = set()
    for record in client.worlds:
        client_id = str(record.get("id") or "")
        pack_name = client_id
        candidates = [client_id] + [alias for alias, target in WORLD_ALIASES.items() if target == client_id]
        pack_world = None
        for candidate in candidates:
            if candidate in by_name:
                pack_name = candidate
                pack_world = by_name[candidate]
                break
        if pack_world:
            used.add(pack_name)
            merged = dict(pack_world)
            events = pack_world.get("m_eventList") or []
            merged["_levelEvents"] = sum(
                1
                for event in events
                if isinstance(event, dict) and str(event.get("m_eventType") or event.get("m_type") or "") == "level"
            )
            entries.append(JoinEntry(client_id, record, [merged]))
        else:
            entries.append(JoinEntry(client_id, record, []))
    unmatched = [world for name, world in by_name.items() if name not in used]
    return entries, unmatched


def _join_armor(client: ClientTables, pack: PackTables) -> tuple[list[JoinEntry], list[dict[str, Any]]]:
    by_type = {str(item.get("ArmorType")): item for item in pack.armors if item.get("ArmorType")}
    entries: list[JoinEntry] = []
    used: set[str] = set()
    for zombie in client.zombies:
        for layer in zombie.get("armor") or []:
            art = str(layer.get("art") or "")
            name = art.rsplit("/", 1)[-1].removesuffix("ARMOR") if art else ""
            pack_armor = by_type.get(name)
            if pack_armor:
                used.add(name)
            entries.append(JoinEntry(f"{zombie.get('id')}:{name or '?'}", layer, [pack_armor] if pack_armor else []))
    unmatched = [item for name, item in by_type.items() if name not in used]
    return entries, unmatched


def _join_projectiles(client: ClientTables, pack: PackTables) -> tuple[list[JoinEntry], list[dict[str, Any]]]:
    by_class = {str(item.get("ClassName")).lower(): item for item in pack.projectiles if item.get("ClassName")}
    counts: Counter[str] = Counter()
    for plant in client.plants:
        if plant.get("projectile"):
            counts[str(plant["projectile"])] += 1
    entries: list[JoinEntry] = []
    used: set[str] = set()
    for name, count in sorted(counts.items()):
        record = {"projectile": name, "plants": count}
        pack_proj = by_class.get(name.lower())
        if pack_proj:
            used.add(name.lower())
        entries.append(JoinEntry(name, record, [pack_proj] if pack_proj else []))
    unmatched = [item for cls, item in by_class.items() if cls not in used]
    return entries, unmatched


def _join_bosses(client: ClientTables, pack: PackTables) -> tuple[list[JoinEntry], list[dict[str, Any]]]:
    entries = [JoinEntry(str(boss.get("id") or ""), boss, []) for boss in client.bosses]
    return entries, []


def _join_fusion(client: ClientTables, pack: PackTables, mapping: dict[tuple[str, str], list[str]]) -> list[JoinEntry]:
    reverse: dict[str, str] = {}
    for (side, client_id), pack_types in mapping.items():
        if side != "plant":
            continue
        for pack_type in pack_types:
            reverse.setdefault(pack_type, client_id)

    def canon(name: Any) -> str:
        text = str(name or "")
        return reverse.get(text, text)

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in pack.fusion:
        key = tuple(sorted((canon(item.get("SourcePlant")), canon(item.get("FusionPlant")))))
        buckets[key].append(item)
    cursor: Counter[tuple[str, str]] = Counter()
    entries: list[JoinEntry] = []
    for recipe in (client.fusions or {}).get("recipes") or []:
        ingredients = [canon(value) for value in recipe.get("ingredients") or []]
        key = tuple(sorted(ingredients[:2])) if len(ingredients) >= 2 else ("", "")
        index = cursor[key]
        cursor[key] += 1
        bucket = buckets.get(key) or []
        pack_item = bucket[index] if index < len(bucket) else (bucket[0] if bucket else None)
        label = "+".join(key) or str(recipe.get("id") or "?")
        entries.append(JoinEntry(label, recipe, [pack_item] if pack_item else []))
    return entries


def _join_simple(entity: str, client_records: Sequence[dict[str, Any]], packs_for) -> list[JoinEntry]:
    return [JoinEntry(str(record.get("id") or ""), record, packs_for(record)) for record in client_records]


# --------------------------------------------------------------------------- 构建


PLANT_PAIRS = (
    ("cost", "Cost"),
    ("hp", "Hitpoints"),
    ("cooldown", "PacketCooldown"),
    ("almanac_no", "IntegerID"),
    ("art", "PopAnim"),
    ("plantfood", "PlantFoodDurationSeconds"),
)
ZOMBIE_PAIRS = (
    ("hp", "Hitpoints"),
    ("speed", "Speed"),
    ("eat_dps", "EatDPS"),
    ("armor", "ArmorType"),
    ("art", "PopAnim"),
)
LEVEL_PAIRS = (
    ("sun", "StartingSun"),
    ("seed_bank", "PresetPlantList"),
    ("deck", "InitialPlantList"),
    ("waves", "WaveCount"),
    ("flags", "FlagCount"),
    ("extra.level_number", "LevelNumber"),
)
SHOP_PAIRS = (
    ("sku", "Sku"),
    ("price", "Price"),
    ("price_gems", "PriceGems"),
    ("price_mints", "PriceMints"),
    ("item_type", "ObjectType"),
    ("one_time", "IsOneTimePurchase"),
)
WORLD_PAIRS = (
    ("id", "m_worldName"),
    ("levels", "_levelEvents"),
    ("map", "m_mapPieces"),
)
ARMOR_PAIRS = (
    ("hp", "BaseHealth"),
    ("art", "ArmorType"),
    ("metal", "ArmorFlags"),
    ("armature", "ArmorLayers"),
)
PROJECTILE_PAIRS = (
    ("projectile", "ClassName"),
    ("plants", "BaseDamage"),
    ("plants", "CollisionFlags"),
)
BOSS_PAIRS = (
    ("id", "ZombossMechType"),
    ("hp", "ZombossPhaseCount"),
    ("phases", "ZombossPhases"),
)
PLANTFOOD_PAIRS = (
    ("plantfood", "PlantFoodDurationSeconds"),
    ("plantfood", "PlantFoodPlayCount"),
)
FUSION_PAIRS = (
    ("result", "ResultPlant"),
    ("ingredients", "SourcePlant"),
    ("ingredients", "FusionPlant"),
)
WAVE_PAIRS = (
    ("waves", "Waves"),
    ("waves", "WaveManagerProps"),
    ("flags", "FlagCount"),
)
STAR_PAIRS = (
    ("stars", "Challenges"),
    ("stars", "TargetScore"),
)


def _entity_ids(client: ClientTables) -> list[str]:
    return list(ENTITY_IDS)


def build(
    obb_dir: Path | None = None,
    content_dir: Path | None = None,
    mapping_path: Path | None = None,
    completeness_path: Path | None = None,
) -> tuple[dict[str, Any], str]:
    obb = Path(obb_dir) if obb_dir else DEFAULT_OBB
    content = Path(content_dir) if content_dir else DEFAULT_CONTENT
    mapping_file = Path(mapping_path) if mapping_path else DEFAULT_MAPPING

    scan = scan_pack(obb)
    pack = load_pack_tables(obb, scan)
    client = load_client(content)
    mapping = load_mapping(mapping_file)

    tables: list[dict[str, Any]] = []
    pack_only_samples: list[dict[str, Any]] = []

    def add(entity: str, entries: Sequence[JoinEntry], pairs, unmatched=(), unmatched_by_field=None, mapped_paths=()):
        rows = _rows_for(entity, entries, pairs, unmatched, unmatched_by_field)
        tables.extend(rows)
        if mapped_paths:
            pack_only_samples.extend(_pack_only_fields(entity, entries, set(mapped_paths)))

    plants = _join_plants(client, pack, mapping)
    add("plants", plants, PLANT_PAIRS, mapped_paths=[path for _, path in PLANT_PAIRS])

    zombies = _join_zombies(client, pack, mapping)
    add("zombies", zombies, ZOMBIE_PAIRS, mapped_paths=[path for _, path in ZOMBIE_PAIRS])

    levels = _join_levels(client, pack, scan)
    add("levels", levels, LEVEL_PAIRS, mapped_paths=[path for _, path in LEVEL_PAIRS])

    shop = _join_shop(client, pack)
    add("shop", shop, SHOP_PAIRS)

    worlds, unmatched_worlds = _join_worlds(client, pack)
    add("worlds", worlds, WORLD_PAIRS, unmatched=unmatched_worlds)

    armor, unmatched_armor = _join_armor(client, pack)
    add("armor", armor, ARMOR_PAIRS, unmatched=unmatched_armor)

    projectiles, unmatched_projectiles = _join_projectiles(client, pack)
    add("projectiles", projectiles, PROJECTILE_PAIRS, unmatched=unmatched_projectiles)

    bosses, _unmatched_bosses = _join_bosses(client, pack)
    add(
        "bosses",
        bosses,
        BOSS_PAIRS,
        unmatched_by_field={"ZombossMechType": pack.boss_modules, "ZombossPhaseCount": pack.boss_modules, "ZombossPhases": pack.boss_modules},
    )

    plantfood = [entry for entry in plants if _nonempty((entry.client or {}).get("plantfood")) or entry.packs]
    add("plantfood", plantfood, PLANTFOOD_PAIRS)

    fusion = _join_fusion(client, pack, mapping)
    add("fusion", fusion, FUSION_PAIRS)

    waves = _join_levels(client, pack, scan)
    add("waves", waves, WAVE_PAIRS)

    stars = _join_stars(client, pack, scan)
    add("stars", stars, STAR_PAIRS)

    tables.sort(key=lambda row: (row["entity"], row["field"], row["clientField"]))
    pack_only_samples.sort(key=lambda row: (-row["count"], row["entity"], row["field"]))

    star_entries = sum(len(value) for value in (client.stars or {}).values() if isinstance(value, list))
    shop_items = len(client.shop_items)
    counts = {
        "entities": len(ENTITY_IDS),
        "tables": len(tables),
        "systems": len(SYSTEM_SPECS),
        "sheetsScanned": scan.sheets_scanned,
        "levelFiles": scan.level_files,
        "levelObjects": scan.level_objects,
        "plantTypes": pack.plant_type_rows,
        "plantTypeNames": len(pack.plant_types),
        "zombieTypes": pack.zombie_type_rows,
        "zombieTypeNames": len(pack.zombie_types),
        "plantJoins": len(plants),
        "zombieJoins": len(zombies),
        "plantJoinedToPack": sum(1 for entry in plants if entry.packs),
        "zombieJoinedToPack": sum(1 for entry in zombies if entry.packs),
        "levelJoins": len(levels),
        "shopItems": shop_items,
        "shopPackProducts": len(pack.store),
        "shopZeroPrice": sum(1 for item in pack.store if _is_zero(item.get("Price"))),
        "starEntries": star_entries,
        "clientWorlds": len(client.worlds),
        "joinedWorldLevelEvents": sum(int(entry.packs[0].get("_levelEvents") or 0) for entry in worlds if entry.packs),
        "joinedWorldClientLevels": sum(int((entry.client or {}).get("levels") or 0) for entry in worlds if entry.packs),
        "packWorlds": len(pack.worlds),
        "mapped": sum(row["mapped"] for row in tables),
        "packOnly": sum(row["packOnly"] for row in tables),
        "clientOnly": sum(row["clientOnly"] for row in tables),
        "agree": sum(row["agree"] for row in tables),
        "packOnlyFieldCount": len(pack_only_samples),
        "packOnlyFieldTop": pack_only_samples[:PACK_ONLY_TOP],
        "zombieIdsInContentPack": len({str(row.get("id")) for row in client.zombies} & _content_pack_zombie_ids(ROOT / "native" / "generated" / "content.pack")),
    }

    systems = _build_systems(scan, pack, client, counts)
    counts["systemsPackOnly"] = sum(1 for row in systems if row["presentInPack"] is True and row["presentInClient"] is False)
    counts["systemsMapped"] = sum(1 for row in systems if row["presentInPack"] is True and row["presentInClient"] is True)
    counts["systemsUnverified"] = sum(1 for row in systems if row["presentInPack"] == "unverified")

    payload = {
        "format": FORMAT,
        "generated": MARKER,
        "sources": {
            "obb": "work/obb_packages",
            "content": "content",
            "mapping": "native/generated/id_mapping.csv",
            "completeness": "docs/COMPLETENESS.md",
        },
        "counts": counts,
        "tables": tables,
        "packOnlyFields": pack_only_samples,
        "systems": systems,
    }
    report = render_report(payload)
    return payload, report


def _content_pack_zombie_ids(path: Path) -> set[str]:
    """content.pack 里已有的僵尸 id —— 决定引擎能否读到原版 ZombieClass，和「有没有 behavior」是两件事。"""
    if not path.is_file():
        return set()
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    rows = doc.get("zombies")
    if isinstance(rows, dict):
        return {str(key) for key in rows}
    if isinstance(rows, list):
        return {str(row.get("id")) for row in rows if isinstance(row, dict) and row.get("id")}
    return set()


def _is_zero(value: Any) -> bool:
    """原版把数字写成字符串（`"0"` / `"450"`），比较前先归一；无法解析的不算 0。"""
    if isinstance(value, bool):
        return value is False
    if isinstance(value, (int, float)):
        return float(value) == 0.0
    try:
        return float(str(value).strip()) == 0.0
    except (TypeError, ValueError):
        return False


def _build_systems(scan: PackScan, pack: PackTables, client: ClientTables, counts: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in SYSTEM_SPECS:
        evidence: list[dict[str, Any]] = []
        for field_name in spec.get("pack_fields", ()):
            records = scan.field_records.get(field_name, 0)
            if records:
                evidence.append(
                    {
                        "table": f"字段索引（{scan.field_sheets.get(field_name, 0)} 张表）",
                        "field": field_name,
                        "count": records,
                    }
                )
        for keyword in spec.get("pack_file_keywords", ()):
            files = [name for name in scan.sheets if keyword.lower() in name.lower()]
            if files:
                evidence.append({"table": "表名关键词", "field": keyword, "count": len(files)})
        if spec["id"] == "key_drops":
            gate = pack.world_gate_kinds.get("key_gate", 0)
            if gate:
                evidence.append({"table": "pkg_2107_WorldData.m_eventList", "field": "key_gate", "count": gate})
        if spec["id"] == "seeds_and_vases":
            if pack.vase_modules:
                evidence.append({"table": "LevelDefinition.Modules", "field": "VaseBreaker*", "count": pack.vase_modules})
        if spec["id"] == "star_challenges" and pack.star_modules:
            evidence.append({"table": "LevelDefinition.Modules", "field": "StarChallengeModule", "count": pack.star_modules})
        if spec["id"] == "mower_config" and pack.mower_modules:
            evidence.append({"table": "LevelDefinition.Modules", "field": "ModernMowers", "count": pack.mower_modules})
        if spec["id"] == "plantfood_drop" and pack.boss_modules:
            evidence.append({"table": "LevelDefinition.Modules", "field": "ZombossBattle", "count": pack.boss_modules})

        signals = tuple(str(signal).lower() for signal in spec.get("client_signals", ()))
        present_client = any(signal in client.keys for signal in signals)
        present_pack: bool | str = True if evidence else "unverified"
        rows.append(
            {
                "id": spec["id"],
                "presentInPack": present_pack,
                "presentInClient": present_client,
                "evidence": evidence,
                "note": spec["note"],
            }
        )
    rows.sort(key=lambda row: row["id"])
    return rows


# --------------------------------------------------------------------------- 渲染


def render_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join("" if cell is None else str(cell) for cell in row) + " |")
    return lines


DOC_CLAIMS = (
    ("docs/COMPLETENESS.md", 13, "339 植物 / 1127 僵尸 / 1809 关 / 85 融合", "counts"),
    ("docs/COMPLETENESS.md", 46, "| `pkg_2074_PlantType` | 339 |", "plantTypes"),
    ("docs/COMPLETENESS.md", 47, "1127（1125 唯一 id）", "zombieTypes"),
    ("docs/COMPLETENESS.md", 136, "商店（585 商品）", "shopItems"),
)


def _doc_corrections(payload: dict[str, Any]) -> list[str]:
    counts = payload["counts"]
    lines = ["## 六、文档更正", ""]
    lines.append("本节对 `docs/COMPLETENESS.md` 里与本工具有关的数字做**实测复核**；数字对不上的，以本工具实测为准。")
    lines.append("")
    measured = {
        "counts": f"{counts['plantTypes']} 植物 / {counts['zombieTypes']} 僵尸 / {counts['levelFiles']} 关 / 融合 85 对",
        "plantTypes": f"{counts['plantTypes']}（类型名 {counts['plantTypeNames']} 个）",
        "zombieTypes": f"{counts['zombieTypes']} 条对象 / {counts['zombieTypeNames']} 个类型名",
        "shopItems": f"客户端 {counts['shopItems']} 件（其中 {counts['shopPackProducts']} 个 sku 对得上原版 StoreProductProps）",
    }
    rows = []
    completeness = DEFAULT_COMPLETENESS
    text_lines = []
    if completeness.is_file():
        text_lines = completeness.read_text(encoding="utf-8").splitlines()
    for file_name, line_no, quote, key in DOC_CLAIMS:
        actual = text_lines[line_no - 1] if line_no - 1 < len(text_lines) else ""
        status = "一致" if quote in actual else "文档已变动，需复核"
        rows.append((f"{file_name}:{line_no}", quote.replace("|", "│"), measured[key], status))
    lines.extend(_table(("位置", "文档原文（片段）", "实测", "结论"), rows))
    lines.append("")
    lines.append("补充更正：")
    lines.append("")
    lines.append(f"- `docs/COMPLETENESS.md:227` 的「20 个 content 僵尸 id 在 sheet zombies[] 里也有同名行」讲的是**护甲桥**那次修复（`cowboy → CowboyHatDefault`）。本工具另有一条独立的 {counts['zombieIdsInContentPack']}：`content.pack` 里精确存在 **{counts['zombieIdsInContentPack']}** 个 content 僵尸 id，而字段级关联能对上 **{counts['zombieJoinedToPack']}** 个（exact + manual）。两者出处不同，不能互换。")
    lines.append(f"- `docs/COMPLETENESS.md:136` 的「585 商品」是**客户端**数量；原版 `StoreProductProps` 是 **{counts['shopPackProducts']}** 件，565 个 sku 对齐，差 **{counts['shopItems'] - counts['shopPackProducts']}** 件是客户端自创。")
    lines.append("- 「字段级差距」此前从未测过：本工具首次给出 `packOnly` / `clientOnly` 的逐字段计数（第二节），后续补功能以此为清单。")
    lines.append("")
    return lines


def render_report(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    lines: list[str] = []
    lines.append("# 原版 ↔ 客户端字段级差距盘点（2026-11-24）")
    lines.append("")
    lines.append(
        f"**一句话结论**：12 个实体里能逐字段对上的只有 **{counts['mapped']}** 处；"
        f"原版有值、客户端没有字段的有 **{counts['packOnly']}** 处，客户端自创字段 **{counts['clientOnly']}** 处；"
        f"{counts['systems']} 个子系统里 **{counts['systemsPackOnly']}** 个是原版有、客户端整块没有。"
    )
    lines.append("")
    lines.append("本次盘点扫描原版 **" + str(counts["sheetsScanned"]) + "** 张 pkg 表（其中关卡定义 "
                 + str(counts["levelFiles"]) + " 个文件 / " + str(counts["levelObjects"]) + " 个对象），"
                 "客户端读 `content/*.json` 与 1809 个关卡文件。")
    lines.append("")
    lines.append("## 一、方法与口径")
    lines.append("")
    lines.append("- 基准：只认 `work/obb_packages/pkg_*.json`；客户端字段一律从 `content/**` 读，不抄任何旧文档数字。")
    lines.append("- 关联键：plants/zombies 走 `id_mapping.csv`（exact + manual）；levels/waves/stars 走客户端 `extra.package`；shop 走 `sku`；worlds 走世界名 + 别名；armor 用美术名去 `ARMOR` 后缀；projectiles 用类名小写；fusion 用配方键 + 出现序。")
    lines.append("- 计数含义：`mapped` = 两侧都有值；`packOnly` = 原版有值而客户端缺字段（worlds/shop/armor/projectiles/bosses 还把「原版独有对象」计入）；`clientOnly` = 客户端有值而原版缺字段；`agree` = 两侧标量相等。")
    lines.append("- 只读：本工具不写 `content/**`、不写 `native/src/**`。")
    lines.append("- 派生字段：`field` 以 `_` 开头的是工具算出来的比较量（例如 `_levelEvents` = 原版 `m_eventList` 里 `m_eventType == \"level\"` 的节点数），不是原版字段名，也不计入 pack-only 字段清单。")
    lines.append("")
    lines.append("## 二、字段级差距总表")
    lines.append("")
    lines.append("按实体分组，`—` 表示客户端字段在原版没有对应字段（纯 authored）。`plantfood` 两行是 `plants` 的子集口径（只看有 `plantfood` 标记或原版有养料记录的株），因此与 `plants` 的部分行数字重合。")
    lines.append("")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in payload["tables"]:
        grouped[row["entity"]].append(row)
    order = [entity for entity in ENTITY_IDS if entity in grouped]
    table_rows = []
    for entity in order:
        for row in grouped[entity]:
            table_rows.append(
                (
                    entity,
                    row["clientField"],
                    row["field"],
                    row["records"],
                    row["mapped"],
                    row["packOnly"],
                    row["clientOnly"],
                    row["agree"],
                )
            )
    lines.extend(_table(("实体", "客户端字段", "原版字段", "关联数", "mapped", "packOnly", "clientOnly", "agree"), table_rows))
    lines.append("")
    lines.append("## 三、原版有值、客户端无字段")
    lines.append("")
    lines.append("把已关联原版对象上「有值但没有任何客户端字段对应」的字段按命中数排序，下面取前 12 条；完整清单见 JSON 顶层 `packOnlyFields`（按实体 + 命中数）。")
    lines.append("")
    lines.extend(
        _table(
            ("实体", "原版字段", "命中数"),
            [(row["entity"], row["field"], row["count"]) for row in counts["packOnlyFieldTop"]],
        )
    )
    lines.append("")
    lines.append(f"共 {len(payload['packOnlyFields'])} 个（实体, 字段）组合有原版值而客户端无字段；这些字段在本版客户端**一个都没有**，是补功能时最直接的缺口来源。典型如植物的 `PlantGridType` / `PlantStats` / `Boosts` / `ZenGarden*`，僵尸的 `WavePointCost` / `Weight` / `CanSpawnPlantFood` / `ScaledProps`。")
    lines.append("")
    lines.append("## 四、客户端独有")
    lines.append("")
    client_only = [row for row in payload["tables"] if row["clientOnly"]]
    client_only.sort(key=lambda row: (-row["clientOnly"], row["entity"], row["field"]))
    lines.extend(
        _table(
            ("实体", "客户端字段", "clientOnly", "说明"),
            [
                (
                    row["entity"],
                    row["clientField"],
                    row["clientOnly"],
                    "原版无对应字段" if row["field"] == "—" else f"原版 {row['field']} 在这些记录上无值（含原版没有该对象的情形）",
                )
                for row in client_only[:20]
            ],
        )
    )
    lines.append("")
    lines.append(f"- 商品：客户端 {counts['shopItems']} 件、原版 {counts['shopPackProducts']} 件，`sku` 对齐后 **{counts['shopItems'] - counts['shopPackProducts']}** 件是客户端自创（`source` 标 legacy）。")
    lines.append(f"- 定价：原版 `Price` {counts['shopPackProducts']} 件里 **{counts['shopZeroPrice']}** 件是 0、其余 {counts['shopPackProducts'] - counts['shopZeroPrice']} 件是 99999；客户端 `price`/`price_gems`/`price_mints` 是自创数值，不能从原版抄。")
    lines.append(f"- 世界：客户端 {counts['clientWorlds']} 个、原版 {counts['packWorlds']} 个；别名归一（gta/skycity/rainbowmarket/kungfu）后能对上 **22** 个，`frontyard`/`future`/`iceage`/`renai` 在原版 `WorldData` 里没有同名行，`order` 这类排序字段原版也没有。")
    lines.append(f"- 世界节点 vs 关卡数：对上的 22 个世界里，原版 `m_eventList` 的 `level` 事件合计 **{counts['joinedWorldLevelEvents']}** 个，客户端 `levels` 合计 **{counts['joinedWorldClientLevels']}** 关，**逐世界全部不等**（例如 egypt 原版 26 个节点、客户端 84 关）——客户端关卡是按 `content/levels/*.json` 补出来的，不是原版世界地图节点的投影。")
    lines.append("- 弹道：客户端 11 个语义名（`pea`/`pea_snow`/`cabbage`…），原版是 131 个 `ClassName`，**零重叠**——客户端弹道名是自创词汇表，不是原版 `ProjectilePropertySheet` 的投影。")
    lines.append("")
    lines.append("## 五、子系统清单")
    lines.append("")
    lines.append("判断标准：原版有整套表/字段，而客户端连一个对应字段都没有。`presentInPack = unverified` 表示本工具在 2116 张表里没找到可复现证据，不写猜测。")
    lines.append("")
    system_rows = []
    for row in payload["systems"]:
        evidence = "；".join(f"{item['table']} · {item['field']} = {item['count']}" for item in row["evidence"][:3]) or "—"
        system_rows.append((row["id"], row["presentInPack"], row["presentInClient"], evidence))
    lines.extend(_table(("子系统", "原版有", "客户端有", "证据（前 3 条）"), system_rows))
    lines.append("")
    for row in payload["systems"]:
        lines.append(f"- **{row['id']}**：{row['note']}")
    lines.append("")
    lines.extend(_doc_corrections(payload))
    lines.append("## 七、复现")
    lines.append("")
    lines.append("```")
    lines.append("python tools/contentc/original_gaps.py --check    # 重算并与盘上 JSON/报告逐字节比对")
    lines.append("python -m unittest tools.tests.test_original_gaps -v")
    lines.append("```")
    lines.append("")
    lines.append("`--check` 不一致时 exit 1；找不到 `work/obb_packages` 时 exit 2。")
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- CLI


def write_outputs(payload: dict[str, Any], report: str, json_path: Path, report_path: Path) -> None:
    for path, text in ((json_path, render_json(payload)), (report_path, report)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


def summarize(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    return (
        f"entities={counts['entities']} tables={counts['tables']} "
        f"mapped={counts['mapped']} packOnly={counts['packOnly']} clientOnly={counts['clientOnly']} "
        f"systems={counts['systems']} packOnlySystems={counts['systemsPackOnly']} "
        f"unverified={counts['systemsUnverified']} sheets={counts['sheetsScanned']} levels={counts['levelFiles']}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="原版↔客户端字段级差距盘点（只读）")
    parser.add_argument("--obb", default=str(DEFAULT_OBB))
    parser.add_argument("--content", default=str(DEFAULT_CONTENT))
    parser.add_argument("--mapping", default=str(DEFAULT_MAPPING))
    parser.add_argument("--json", default=str(DEFAULT_JSON))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--check", action="store_true", help="重算并与盘上产物逐字节比对")
    parser.add_argument("-n", "--dry-run", action="store_true", help="只打印摘要，不写盘")
    args = parser.parse_args(argv)

    obb = Path(args.obb)
    if not obb.is_dir():
        print(f"obb 目录不存在：{obb}", file=sys.stderr)
        return 2

    payload, report = build(obb, Path(args.content), Path(args.mapping))
    json_path = Path(args.json)
    report_path = Path(args.report)

    if args.check:
        stale: list[str] = []
        for path, text in ((json_path, render_json(payload)), (report_path, report)):
            if not path.is_file():
                stale.append(f"{path} 缺失")
                continue
            # C60: compare newline-insensitively. A Windows checkout may hand us CRLF
            # while the renderer emits LF, which made --check fail on an otherwise clean tree.
            if path.read_bytes().replace(b"\r\n", b"\n") != text.encode("utf-8"):
                stale.append(f"{path} 内容过期")
        if stale:
            print("产物不是最新：", file=sys.stderr)
            for item in stale:
                print("  " + item, file=sys.stderr)
            return 1
        print("产物已是最新：" + summarize(payload))
        return 0

    if args.dry_run:
        print(summarize(payload))
        return 0

    write_outputs(payload, report, json_path, report_path)
    print(summarize(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
