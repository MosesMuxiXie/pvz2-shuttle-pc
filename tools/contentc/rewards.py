"""Compile the original game's level-reward / loot economy from the OBB RTON-JSON tables.

Why this exists
---------------
The C++ engine (`native/src/**`) has no coin or key *source*: `--shop` can only be
exercised with the `--coins` cheat. The shipped OBB does carry a complete drop
economy, it just never made it into the port. This tool reads the shipped tables and
writes one deterministic table (`native/generated/rewards_from_pack.json`) that a
`World` can consume when a level ends or a zombie dies.

Sources actually used (each row in the output cites `pkg/file:path:row_id`)
-------------------------------------------------------------------------
R01 `pkg_0234_DisableSkipLevelModuleProperties.json`
      objclass `LootTable` alias `DefaultLootTable` -> `Entries[]`
      The whole in-level drop schedule: Type (SilverCoin/GoldCoin/Gem/*Key/SmallSun/
      LargeSun/LawnMower/Sprout), Min/Max (how many), Period (kills between drops),
      LevelLootKey (which `LootConfig` selects it), EnabledAfter (first level that
      enables it), World (key drops only), DisableViaLiveToggle (server kill switch).
R02 same package, objclass `LootConfig` -> `DefaultLoot` / `DangerRoomLoot` /
      `WhackLoot` / `NoLoot`. `LevelDefinition.Loot` points at one of these RTIDs, so
      the level's loot key is `LootConfig.LevelLootKey` ("default"/"danger"/"whack")
      or the level has no loot at all (`Disable: true`).
R03 `pkg_2079_PresentTable.json` -> `Entries[].{PresentType,Weight}`
      The end-of-level lunchbox. `LevelDefinition.NormalPresentTable` and
      `ShinyPresentTable` name one of these.
R04 `pkg_2080_PresentTypeCoin.json` -> `PresentTypeCoin.CoinValue`
      Coin packs the present resolves to (coinpack_small 10 / medium 100 / large 1000).
R05 `pkg_0010_CollectableType.json` -> the pickup each loot Type spawns
      (`CollectableCoinType.CoinValue` 10/100, `CollectableGemType.GemValue` 2,
      `CollectableSunType.SunValue`, `CollectableMoneyBagType.ContentsCount`,
      `CollectableType` rows whose `CollectableClass` is `CollectableWorldKey`).
R06 `pkg_2091_RiftFirstClearRewards.json` -> `DefaultLevelClearRewards` /
      `LevelClearRewards[].FirstClearRewards[]` (coins / gems / plantXP per rift level).
R07 `pkg_2097_RiftZombossRewards.json` -> `ProgressionRewards[].DifficultyList[].Rewards[]`
      (per attempt-per difficulty rift boss payout).
R08 `pkg_0004_AwardConfigPropertySheet.json` -> `GiftBoxRewards[]`
      (Award / AwardParam / AwardQuantity / Category / Probability).
R09 `pkg_2083_PlantFusionConfig.json` objclass `GamePropertySheet`
      economy constants: CoinsPerKey 1000, KeysPerCostume 10, StarsPerCostume 20,
      LawnMowerPurchasePriceInCoins 2000, SeedSlotRentalCost 2000.
R10 `pkg_2107_WorldData.json` -> `m_eventList` events of type `key_gate` (m_cost =
      keys spent) and `star_gate` (m_cost = stars spent) — the sinks that make the
      keys/stars above worth anything.
R11 `LevelDefinition.FirstRewardType/FirstRewardParam` (486 levels) and
      `ReplayRewardType/ReplayRewardParam` (67 levels) — the *categorical* first-clear
      vs repeat reward (unlock_plant / pinata / giftbox / worldtrophy / note / ...).
R12 `ZombieDeathSeedDropModuleProperties` (15 level-inline modules) — the only per-zombie
      drop in the pack: `DropChance` (0.01..1), `DropOnAllZombieTypes` and a weighted
      `SeedDropList[].{PlantType, Weight}`. This is where seed packets actually come from.

Rules the output follows
-----------------------
* Every number keeps a `source` string of the form
  `pkg_NNNN_Sheet.json:objclass=.../path[row].field` so it can be re-read by hand.
* A loot `Type` name is **not** mapped to a pickup by any shipped table: the same
  string literals (`SilverCoin`, `GoldCoin`, `Gem`, `SmallSun`, `LargeSun`) appear in
  five different fields (LootTable.Type, LootOverride.LootOverride,
  LootOverrideZombossRift.Drop, PickupCollectableTutorial.LootType,
  ZombieCarnieMonkeyProps.CoinType) with no mapping row anywhere. The pickup and its
  value are therefore reported with `mapping="inferred-name-convention"` and never
  presented as a shipped mapping.
* Sentinels are counted separately and never folded into a total:
  `2147483647`, `-1`, and `0` appear as "no value" markers in several award fields.
* A reward the pack does not contain is listed in `unknowns[]` with the files tried —
  never invented. Two discoveries drive most of those: `mint` has a *price* field
  (`StoreProductProps.PriceMints`) but no producer anywhere, and no table grants stars
  as a reward.

Usage
-----
    python tools/contentc/rewards.py              # rewrite the table + report
    python tools/contentc/rewards.py --check      # recompute, compare bytes, exit 1 on drift
    python tools/contentc/rewards.py --needle key # where does a loot type appear
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from contentc import s5scan, worlds  # noqa: E402

REPO = worlds.REPO
DEFAULT_OBB = worlds.DEFAULT_OBB
DEFAULT_OUT = REPO / "native" / "generated" / "rewards_from_pack.json"
DEFAULT_REPORT = REPO / "docs" / "reviews" / "2026-11-24-rewards.md"

FORMAT = "pvz2-shuttle/rewards@1"
GENERATED = "rewards-compile-v1"

LOOT_PKG = "pkg_0234_DisableSkipLevelModuleProperties.json"
PRESENT_PKG = "pkg_2079_PresentTable.json"
PRESENT_TYPE_PKG = "pkg_2080_PresentTypeCoin.json"
COLLECTABLE_PKG = "pkg_0010_CollectableType.json"
AWARD_PKG = "pkg_0004_AwardConfigPropertySheet.json"
RIFT_CLEAR_PKG = "pkg_2091_RiftFirstClearRewards.json"
RIFT_BOSS_PKG = "pkg_2097_RiftZombossRewards.json"
GAME_PROPS_PKG = "pkg_2083_PlantFusionConfig.json"
WORLD_DATA_PKG = "pkg_2107_WorldData.json"
PINATA_PKG = "pkg_2066_PinataType.json"

# The packages this compiler reads for values. The recursive sentinel census below is
# reported for exactly this set, so the two numbers are about the same inputs.
READ_PACKAGES = (LOOT_PKG, PRESENT_PKG, PRESENT_TYPE_PKG, COLLECTABLE_PKG, AWARD_PKG,
                 RIFT_CLEAR_PKG, RIFT_BOSS_PKG, GAME_PROPS_PKG, WORLD_DATA_PKG, PINATA_PKG)

SENTINELS = (2147483647, -1)

# What the whitelisted read path inspects. `fieldsWithHits` in the output only lists the
# labels that actually produced a hit, so the whitelist is spelled out separately —
# otherwise a field that is read and clean looks like a field that is never read.
READ_PATH_WHITELIST = (
    "LootConfig.LevelLength",
    "LootTable.Entries[].{Min,Max,Period}",
    "PresentTable.Entries[].Weight",
    "RiftFirstClearRewards + RiftZombossRewards: every Award* leaf (walk_awards)",
    "AwardConfigPropertySheet.GiftBoxRewards[].{AwardQuantity,Probability}",
    "GamePropertySheet.{CoinsPerKey,KeysPerCostume,StarsPerCostume,"
    "LawnMowerPurchasePriceInCoins,SeedSlotRentalCost}",
)

RTID_RE = re.compile(r"RTID\(\s*([^@)\s]+)\s*@([^)\s]+)\s*\)")

# Loot `Type` -> the coarse economic kind this table reports.
LOOT_KIND = {
    "SilverCoin": "coin",
    "GoldCoin": "coin",
    "Gem": "gem",
    "SmallSun": "sun",
    "LargeSun": "sun",
    "LawnMower": "mower",
    "Sprout": "sprout",
    "EgyptKey": "key",
    "PirateKey": "key",
    "CowboyKey": "key",
    "FutureKey": "key",
}

# Loot `Type` -> the pickup it must spawn. No shipped table states this; the mapping
# below is the naming convention, and every row using it says so.
#
# The third element is the value field on that pickup row, or `None` when the pickup
# carries no number (a mower and a sprout are counted, not valued). Every entry is
# checked against `pkg_0010_CollectableType.json` at compile time: the row must exist,
# and a missing row degrades the row to `mapping="unresolved"` with the reason on the
# row (`mappingNote`) rather than silently keeping a null.
LOOT_PICKUP = {
    "SilverCoin": ("coin_silver", "CollectableCoinType", "CoinValue"),
    "GoldCoin": ("coin_gold", "CollectableCoinType", "CoinValue"),
    "Gem": ("gem_diamond", "CollectableGemType", "GemValue"),
    "SmallSun": ("sun_small", "CollectableSunType", "SunValue"),
    "LargeSun": ("sun_large", "CollectableSunType", "SunValue"),
    # Audit M2 (2026-11-24): these two used to end in `mapping="none"` even though
    # `lawn_mower` (CollectableLawnMower) and `sprout` (CollectableSprout) are real
    # rows in pkg_0010. Same convention as the five above, so same treatment.
    "LawnMower": ("lawn_mower", "CollectableType", None),
    "Sprout": ("sprout", "CollectableType", None),
}

# FirstRewardType / ReplayRewardType -> coarse kind.
AWARD_KIND = {
    "unlock_plant": "plant",
    "pinata": "pinata",
    "giftbox": "giftbox",
    "worldtrophy": "trophy",
    "note": "note",
    "collectable": "collectable",
    "powerupgadget": "powerup",
    "upgrade": "upgrade",
    "unlock_costume": "cosmetic",
    "mapgadget": "gadget",
    "none": "none",
    "": "none",
}

# The six kinds the task names, kept first so `counts.byKind` reads in a stable order.
PRIMARY_KINDS = ("coin", "key", "seed", "gem", "plantfood", "mint")

SECONDARY_KINDS = ("sun", "mower", "sprout", "xp", "star", "plant", "pinata", "giftbox",
                   "trophy", "collectable", "powerup", "upgrade", "cosmetic", "note",
                   "junk", "gadget", "none", "unknown")

# Award / pick-up vocabulary -> the canonical kind above. The pack names the same thing
# three ways (`coins` in an award, `GoldCoin` in a loot table, `coin_gold` as a pickup),
# so every row is normalised to one kind and keeps its original spelling in `rewardType`.
KIND_FIX = {
    "coins": "coin",
    "gems": "gem",
    "plantXP": "xp",
    "costume": "cosmetic",
    "powerupuse": "powerup",
}

# PresentType objclass -> kind (the lunchbox resolves through this, not through a name).
PRESENT_KIND = {
    "PresentTypeCoin": "coin",
    "PresentTypePowerupUse": "powerup",
    "PresentTypeSprout": "sprout",
    "PresentTypeJunk": "junk",
}

# Fallback for presents that resolve to a plain `CollectableType` row: the shipped
# `CollectableClass` says what the pickup is, so no name matching is needed.
COLLECTABLE_CLASS_KIND = {
    "CollectableCoin": "coin",
    "CollectableGem": "gem",
    "CollectableSun": "sun",
    "CollectablePowerup": "powerup",
    "CollectableSprout": "sprout",
    "CollectableStar": "star",
    "CollectableWorldKey": "key",
    "CollectablePresent": "giftbox",
}

ECONOMY_CONSTANTS = (
    "CoinsPerKey",
    "KeysPerCostume",
    "StarsPerCostume",
    "LawnMowerPurchasePriceInCoins",
    "SeedSlotRentalCost",
)

_CACHE: dict[str, dict | None] = {}


def load_json(path: Path) -> dict | None:
    key = str(path)
    if key in _CACHE:
        return _CACHE[key]
    try:
        with path.open(encoding="utf-8-sig") as handle:
            doc = json.load(handle)
    except (OSError, json.JSONDecodeError):
        _CACHE[key] = None
        return None
    _CACHE[key] = doc if isinstance(doc, dict) else None
    return _CACHE[key]


def objects(doc: dict | None):
    for entry in (doc or {}).get("objects") or []:
        data = entry.get("objdata")
        if isinstance(data, dict):
            yield entry, data


def aliases(entry: dict) -> list[str]:
    raw = entry.get("aliases")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    single = entry.get("alias")
    return [str(single)] if single else []


def number(value) -> float | int | None:
    """Read a numeric field that may be shipped as a string ("100" / "0.3")."""

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return None
    return None


def rtid_name(value) -> str | None:
    if not isinstance(value, str):
        return None
    match = RTID_RE.search(value)
    return match.group(1) if match else None


def generated_stamp(obb: Path) -> str:
    """Content stamp of the packages we read — never the clock, never the mtime.

    C58: an mtime stamp churned the artifact whenever the same OBB was re-extracted (we do
    that on every version bump). Hashing the inputs keeps two runs byte-identical *and*
    stable across machines, while still recording exactly which revision produced it.
    """

    digest = hashlib.sha256()
    for name in (LOOT_PKG, PRESENT_PKG, PRESENT_TYPE_PKG, COLLECTABLE_PKG, AWARD_PKG,
                 RIFT_CLEAR_PKG, RIFT_BOSS_PKG, GAME_PROPS_PKG, WORLD_DATA_PKG, PINATA_PKG):
        path = obb / name
        if path.exists():
            digest.update(name.encode("utf-8"))
            digest.update(path.read_bytes())
    # An empty package set still has to produce a stable stamp: `build()` is called with a
    # temporary directory in the tests, and `counts.filesScanned == 0` already tells the
    # caller that nothing was read (that hash is simply the digest of nothing).
    return "sha256:" + digest.hexdigest()[:16]


def collectables(obb: Path) -> dict[str, dict]:
    """TypeName -> {objclass, data} for every collectable / present / pinata row."""

    rows: dict[str, dict] = {}
    for name in (COLLECTABLE_PKG, PRESENT_TYPE_PKG, PINATA_PKG):
        doc = load_json(obb / name)
        for entry, data in objects(doc):
            type_name = data.get("TypeName")
            key = str(type_name) if type_name else (aliases(entry) or [""])[0]
            if not key:
                continue
            rows.setdefault(key, {"pkg": name, "objclass": entry.get("objclass"), "data": data})
    return rows


def pickup_value(pickups: dict[str, dict], type_name: str, field: str) -> tuple[float | int | None, str]:
    row = pickups.get(type_name)
    if not row:
        return None, f"{type_name}: absent"
    value = number(row["data"].get(field))
    return value, f"{row['pkg']}:objclass={row['objclass']}/{type_name}.{field}"


def level_index(obb: Path, paths: list[Path]) -> dict[str, object]:
    """Per-level loot plumbing plus the categorical first/replay reward counters."""

    loot_by_rtid: Counter = Counter()
    present_by_name: Counter = Counter()
    shiny_by_name: Counter = Counter()
    first_counter: Counter = Counter()
    replay_counter: Counter = Counter()
    levels = 0
    first_levels = 0
    replay_levels = 0
    for path in paths:
        doc = load_json(path)
        if not doc:
            continue
        for entry, data in objects(doc):
            if (entry.get("objclass") or "") != "LevelDefinition":
                continue
            levels += 1
            loot_by_rtid[str(data.get("Loot"))] += 1
            present_by_name[str(data.get("NormalPresentTable"))] += 1
            shiny_by_name[str(data.get("ShinyPresentTable"))] += 1
            if "FirstRewardType" in data:
                first_levels += 1
                first_counter[(str(data.get("FirstRewardType")), str(data.get("FirstRewardParam")))] += 1
            if "ReplayRewardType" in data:
                replay_levels += 1
                replay_counter[(str(data.get("ReplayRewardType")), str(data.get("ReplayRewardParam")))] += 1
    return {
        "levels": levels,
        "lootByRtid": dict(loot_by_rtid),
        "presentByName": dict(present_by_name),
        "shinyByName": dict(shiny_by_name),
        "first": first_counter,
        "replay": replay_counter,
        "firstLevels": first_levels,
        "replayLevels": replay_levels,
    }


def loot_rows(obb: Path) -> tuple[list[dict], dict]:
    """R01/R02/R05: the in-level drop schedule, with the pickup each drop spawns."""

    doc = load_json(obb / LOOT_PKG)
    configs: dict[str, dict] = {}
    table = None
    table_name = ""
    for entry, data in objects(doc):
        cls = entry.get("objclass") or ""
        names = aliases(entry)
        if cls == "LootConfig":
            for name in names:
                configs[name] = data
        elif cls == "LootTable" and "DefaultLootTable" in names:
            table = data
            table_name = "DefaultLootTable"
    if table is None:
        return [], {"entries": 0, "configs": configs}

    pickups = collectables(obb)
    loot_key_to_config = {}
    for name, data in configs.items():
        key = data.get("LevelLootKey")
        if isinstance(key, str):
            loot_key_to_config[key] = name

    rows = []
    for index, entry in enumerate(table.get("Entries") or []):
        if not isinstance(entry, dict):
            continue
        loot_type = str(entry.get("Type"))
        kind = LOOT_KIND.get(loot_type, "unknown")
        loot_key = entry.get("LevelLootKey")
        scope_key = str(loot_key) if loot_key else "any"
        period = number(entry.get("Period"))
        drop_min = number(entry.get("Min"))
        drop_max = number(entry.get("Max"))

        pickup_name = None
        unit = None
        unit_source = ""
        mapping = "none"
        mapping_note = ""
        if loot_type in LOOT_PICKUP:
            pickup_name, sheet_class, field = LOOT_PICKUP[loot_type]
            row = pickups.get(pickup_name)
            if row is None:
                # Keep the convention's answer visible even when the pickup is missing,
                # so the reader sees *which* rule failed instead of a bare null.
                mapping = "unresolved"
                mapping_note = (f"name convention {loot_type} -> {pickup_name}, but "
                                f"{COLLECTABLE_PKG} has no {sheet_class} row named "
                                f"{pickup_name}")
            elif field is None:
                # Counted pickup (mower / sprout): no value field to read on the row,
                # so one drop is one item and the value stays 1.
                unit = 1
                unit_source = (f"{row['pkg']}:objclass={row['objclass']}/{pickup_name}"
                               " (no value field)")
                mapping = "inferred-name-convention"
                mapping_note = (f"name convention {loot_type} -> {pickup_name} "
                                f"({row['objclass']}); the row carries no numeric value "
                                "field, so one drop = 1 item")
            else:
                unit, unit_source = pickup_value(pickups, pickup_name, field)
                mapping = "inferred-name-convention"
                mapping_note = (f"name convention {loot_type} -> {pickup_name} "
                                f"({row['objclass']}), value read from {pickup_name}.{field}")
        elif kind == "key":
            pickup_name = f"worldkey_{str(entry.get('World') or '').lower()}"
            unit = 1
            unit_source = f"{COLLECTABLE_PKG}:objclass=CollectableType/CollectableWorldKey"
            if pickup_name in pickups:
                mapping = "inferred-name-convention"
                mapping_note = (f"name convention {loot_type} -> {pickup_name} "
                                f"(CollectableWorldKey)")
            else:
                mapping = "unresolved"
                mapping_note = (f"name convention {loot_type} -> {pickup_name}, but no "
                                f"worldkey row for world {entry.get('World')!r} exists "
                                f"(pkg_0010 ships worldkey_beach/.../worldkey_pirate, no "
                                f"worldkey_egypt)")
        else:
            unit = None
            unit_source = f"{LOOT_PKG}:objclass=LootTable/Entries[{index}].Type"
            mapping_note = f"no name convention covers loot Type {loot_type!r}"

        amount_range = None
        if unit is not None and drop_min is not None and drop_max is not None:
            amount_range = [round(unit * drop_min, 4), round(unit * drop_max, 4)]

        # A sub-second Period cannot be "kills between drops"; the two `whack` rows are
        # the whack-a-zombie minigame, where drops are on a timer.
        period_unit = "seconds" if period is not None and period < 1 else "kills"

        rows.append({
            # The same UniqueId is reused across LootConfigs (Silver1 exists for both
            # `default` and `danger`), so the loot key is part of the identity.
            "id": f"loot:{str(entry.get('UniqueId'))}:{scope_key}",
            "kind": kind,
            "lootType": loot_type,
            "pickup": pickup_name,
            "mapping": mapping,
            "mappingNote": mapping_note,
            "amount": unit,
            "amountRange": amount_range,
            "drops": [drop_min, drop_max],
            "period": period,
            "periodUnit": period_unit,
            "world": entry.get("World") or "any",
            "levelOrRange": "in-level drops",
            "lootKey": scope_key,
            "lootConfig": loot_key_to_config.get(scope_key),
            "firstOnly": False,
            "condition": entry.get("EnabledAfter") or "",
            "liveToggle": entry.get("DisableViaLiveToggle") or "",
            "unitSource": unit_source,
            "source": f"{LOOT_PKG}:objclass=LootTable/{table_name}.Entries[{index}]",
        })
    return rows, {"entries": len(table.get("Entries") or []), "configs": configs,
                  "tableName": table_name}


def present_kind(pickup: dict) -> str:
    """Kind of a lunchbox entry: objclass first, then the shipped CollectableClass."""

    cls = str(pickup.get("objclass") or "")
    if cls in PRESENT_KIND:
        return PRESENT_KIND[cls]
    collectable_class = str(pickup.get("data", {}).get("CollectableClass") or "")
    return COLLECTABLE_CLASS_KIND.get(collectable_class, "unknown")


def present_rows(obb: Path, level: dict) -> tuple[list[dict], list[dict], dict]:
    """R03/R04: the end-of-level lunchbox, and the tables levels name but the pack lacks."""

    pickups = collectables(obb)
    doc = load_json(obb / PRESENT_PKG)
    tables: dict[str, dict] = {}
    for entry, data in objects(doc):
        if (entry.get("objclass") or "") != "PresentTable":
            continue
        name = str(data.get("TypeName"))
        tables[name] = {"data": data, "pkg": PRESENT_PKG}

    rows: list[dict] = []
    for name in sorted(tables):
        data = tables[name]["data"]
        shiny = bool(data.get("Shiny"))
        entries = data.get("Entries") or []
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            weight = number(entry.get("Weight"))
            present_type = str(entry.get("PresentType"))
            present_row = pickups.get(present_type) or {}
            coin_value = number(present_row.get("data", {}).get("CoinValue"))
            kind = present_kind(present_row)
            if kind == "coin":
                value = coin_value
            elif kind == "powerup":
                value = number(present_row.get("data", {}).get("NumUses"))
            else:
                value = None
            rows.append({
                "id": f"present:{name}:{present_type}",
                "kind": kind,
                "rewardType": present_type,
                "amount": value,
                "amountRange": None,
                "weight": weight,
                "variant": "shiny" if shiny else "normal",
                "world": name.split("_")[0],
                "levelOrRange": f"levels whose {'Shiny' if shiny else 'Normal'}PresentTable = {name}",
                "levels": (level["shinyByName"] if shiny else level["presentByName"]).get(name, 0),
                # The pack never states *when* the shiny table is used; only that a
                # separate field exists. Reported as False + unknown, not guessed.
                "firstOnly": False,
                "enabled": bool(weight),
                "source": f"{PRESENT_PKG}:objclass=PresentTable/{name}.Entries[{index}]",
                "valueSource": f"{PRESENT_TYPE_PKG}:objclass=PresentTypeCoin/{present_type}.CoinValue",
            })

    dangling = []
    for name, count in sorted(level["presentByName"].items()):
        if name in ("None", "") or name in tables:
            continue
        dangling.append({
            "table": name,
            "kind": "normal",
            "levels": count,
            "source": f"{PRESENT_PKG}:objclass=PresentTable (no row named {name})",
        })
    for name, count in sorted(level["shinyByName"].items()):
        if name in ("None", "") or name in tables:
            continue
        dangling.append({
            "table": name,
            "kind": "shiny",
            "levels": count,
            "source": f"{PRESENT_PKG}:objclass=PresentTable (no row named {name})",
        })
    return rows, dangling, {"tables": len(tables)}


def rift_rows(obb: Path) -> list[dict]:
    """R06/R07: rift level-clear and rift-boss payouts (the only FirstClearRewards in the pack)."""

    rows: list[dict] = []
    doc = load_json(obb / RIFT_CLEAR_PKG)
    for entry, data in objects(doc):
        if (entry.get("objclass") or "") != "RiftFirstClearRewards":
            continue
        default = data.get("DefaultLevelClearRewards") or {}
        for index, award in enumerate(default.get("FirstClearRewards") or []):
            if not isinstance(award, dict):
                continue
            rows.append({
                "id": f"rift-clear:default:{index}:{award.get('Award')}",
                "kind": str(award.get("Award")),
                "amount": number(award.get("AwardQuantity")),
                "amountRange": None,
                "world": "rift",
                "levelOrRange": "rift levels without an explicit LevelClearRewards row",
                "firstOnly": True,
                "source": f"{RIFT_CLEAR_PKG}:objclass=RiftFirstClearRewards/DefaultLevelClearRewards.FirstClearRewards[{index}]",
            })
        for level_index_, block in enumerate(data.get("LevelClearRewards") or []):
            if not isinstance(block, dict):
                continue
            for index, award in enumerate(block.get("FirstClearRewards") or []):
                if not isinstance(award, dict):
                    continue
                rows.append({
                    "id": f"rift-clear:{level_index_ + 1}:{index}:{award.get('Award')}",
                    "kind": str(award.get("Award")),
                    "amount": number(award.get("AwardQuantity")),
                    "amountRange": None,
                    "world": "rift",
                    "levelOrRange": f"rift level {level_index_ + 1}",
                    "firstOnly": True,
                    "source": f"{RIFT_CLEAR_PKG}:objclass=RiftFirstClearRewards/LevelClearRewards[{level_index_}].FirstClearRewards[{index}]",
                })

    doc = load_json(obb / RIFT_BOSS_PKG)
    for entry, data in objects(doc):
        if (entry.get("objclass") or "") != "RiftZombossRewards":
            continue
        for attempt_index, attempt in enumerate(data.get("ProgressionRewards") or []):
            if not isinstance(attempt, dict):
                continue
            attempt_no = attempt.get("Attempt")
            for diff_index, diff in enumerate(attempt.get("DifficultyList") or []):
                if not isinstance(diff, dict):
                    continue
                for index, award in enumerate(diff.get("Rewards") or []):
                    if not isinstance(award, dict):
                        continue
                    rows.append({
                        "id": f"rift-boss:a{attempt_no}:d{diff_index}:{index}:{award.get('Award')}",
                        "kind": str(award.get("Award")),
                        "amount": number(award.get("AwardQuantity")),
                        "amountRange": None,
                        "world": "rift",
                        "levelOrRange": f"rift zomboss, attempt {attempt_no}, difficulty {diff_index}",
                        "firstOnly": False,
                        "source": f"{RIFT_BOSS_PKG}:objclass=RiftZombossRewards/ProgressionRewards[{attempt_index}].DifficultyList[{diff_index}].Rewards[{index}]",
                    })
    return rows


def giftbox_rows(obb: Path) -> list[dict]:
    """R08: the gift-box award table (probabilistic, `Probability` out of an unknown total)."""

    rows: list[dict] = []
    doc = load_json(obb / AWARD_PKG)
    for entry, data in objects(doc):
        if (entry.get("objclass") or "") != "AwardConfigPropertySheet":
            continue
        for index, award in enumerate(data.get("GiftBoxRewards") or []):
            if not isinstance(award, dict):
                continue
            rows.append({
                "id": f"giftbox:{award.get('Category')}:{index}:{award.get('Award')}",
                "kind": str(award.get("Award")),
                "amount": number(award.get("AwardQuantity")),
                "amountRange": None,
                "probability": number(award.get("Probability")),
                "category": award.get("Category"),
                "param": award.get("AwardParam"),
                "world": "any",
                "levelOrRange": "gift box opening",
                "firstOnly": False,
                "source": f"{AWARD_PKG}:objclass=AwardConfigPropertySheet/GiftBoxRewards[{index}]",
            })
    return rows


def constant_rows(obb: Path) -> list[dict]:
    """R09: the exchange rates that turn keys/stars into buys."""

    rows: list[dict] = []
    doc = load_json(obb / GAME_PROPS_PKG)
    for entry, data in objects(doc):
        if (entry.get("objclass") or "") != "GamePropertySheet":
            continue
        for name in ECONOMY_CONSTANTS:
            if name not in data:
                continue
            value = number(data.get(name))
            kind = "coin" if "Coins" in name or "Price" in name or "Cost" in name else "key"
            if name == "StarsPerCostume":
                kind = "star"
            rows.append({
                "id": f"constant:{name}",
                "kind": kind,
                "amount": value,
                "amountRange": None,
                "constant": name,
                "world": "any",
                "levelOrRange": "economy constant",
                "firstOnly": False,
                "source": f"{GAME_PROPS_PKG}:objclass=GamePropertySheet/{name}",
            })
    return rows


def gate_rows(obb: Path) -> list[dict]:
    """R10: where keys and stars are *spent* (key_gate / star_gate `m_cost`)."""

    rows: list[dict] = []
    doc = load_json(obb / WORLD_DATA_PKG)
    for entry, data in objects(doc):
        world = str(data.get("m_worldName") or "unknown")
        for index, event in enumerate(data.get("m_eventList") or []):
            if not isinstance(event, dict):
                continue
            kind = str(event.get("m_eventType"))
            if kind not in ("key_gate", "star_gate"):
                continue
            rows.append({
                "id": f"gate:{world}:{event.get('m_name') or event.get('m_eventId')}",
                "kind": "key" if kind == "key_gate" else "star",
                "amount": number(event.get("m_cost")),
                "amountRange": None,
                "gate": kind,
                "world": world,
                "name": event.get("m_name") or "",
                "levelOrRange": "world-map gate",
                "firstOnly": False,
                "source": f"{WORLD_DATA_PKG}:objclass=WorldData/{world}.m_eventList[{index}].m_cost",
            })
    return sorted(rows, key=lambda row: row["id"])


def level_reward_rows(level: dict) -> list[dict]:
    """R11: the categorical first-clear vs repeat reward attached to a level."""

    rows: list[dict] = []
    for (reward_type, param), count in sorted(level["first"].items()):
        rows.append({
            # `""` and `"none"` are both present in the data and mean different things
            # (9 unset rows vs 7 explicit `none`), so the id keeps the raw spelling.
            "id": f"first:{reward_type or '<empty>'}:{param or '<empty>'}",
            "kind": AWARD_KIND.get(reward_type, reward_type or "none"),
            "amount": None,
            "amountRange": None,
            "rewardType": reward_type,
            "param": param,
            "difficulty": "first-clear",
            "levels": count,
            "world": "any",
            "levelOrRange": "levels granting this on first clear",
            "firstOnly": True,
            "source": f"{LOOT_PKG.replace('pkg_0234_DisableSkipLevelModuleProperties', 'pkg_0234..pkg_2047_LevelDefinition')}:objclass=LevelDefinition/FirstRewardType+FirstRewardParam",
        })
    for (reward_type, param), count in sorted(level["replay"].items()):
        rows.append({
            "id": f"replay:{reward_type or '<empty>'}:{param or '<empty>'}",
            "kind": AWARD_KIND.get(reward_type, reward_type or "none"),
            "amount": None,
            "amountRange": None,
            "rewardType": reward_type,
            "param": param,
            "difficulty": "repeat-clear",
            "levels": count,
            "world": "any",
            "levelOrRange": "levels granting this on repeat clear",
            "firstOnly": False,
            "source": "pkg_0234..pkg_2047_LevelDefinition:objclass=LevelDefinition/ReplayRewardType+ReplayRewardParam",
        })
    return rows


def sentinel_report(rows: list[dict]) -> dict:
    """Count sentinel-shaped numbers without letting them into any total."""

    hits: Counter = Counter()
    for row in rows:
        for field in ("amount", "amountRange"):
            value = row.get(field)
            values = value if isinstance(value, list) else [value]
            for item in values:
                if isinstance(item, (int, float)) and item in SENTINELS:
                    hits[f"{field}={item}"] += 1
                elif isinstance(item, (int, float)) and item == 0:
                    hits[f"{field}=0"] += 1
    return dict(hits)


def normalize_kind(kind: str) -> str:
    """Fold the pack's spelling variants into the canonical kind vocabulary."""

    return KIND_FIX.get(kind, kind or "unknown")


def walk_numbers(value, path: str = ""):
    """Every int/float leaf under `value`, depth-first, with a dotted path.

    Dict keys and list indices both appear in the path so an example can be read
    back by hand (`Entries[3].Min`, `Stages[1].HitPoints`).
    """

    stack = [(value, path)]
    while stack:
        node, prefix = stack.pop()
        if isinstance(node, dict):
            for key, child in node.items():
                stack.append((child, f"{prefix}.{key}" if prefix else str(key)))
        elif isinstance(node, list):
            for index, child in enumerate(node):
                stack.append((child, f"{prefix}[{index}]"))
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            yield node, prefix


def recursive_sentinel_count(obb: Path, paths: list[Path]) -> dict:
    """Count sentinel-shaped leaves in objdata with **no field whitelist**.

    Only `-1` and `2147483647` are counted here. `0` is a legitimate value in
    hundreds of objdata fields (cooldowns, probabilities, grid coordinates), so a
    recursive `0` census could not tell "no value" from "the value is zero" — that
    is exactly why the whitelisted read path counts `0` and this scan does not.
    """

    totals: Counter = Counter()
    by_type: Counter = Counter()
    by_package: dict[str, int] = {}
    by_objclass: Counter = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for path in paths:
        if not path.exists():
            continue
        doc = load_json(path)
        if not doc:
            continue
        count = 0
        for entry, data in objects(doc):
            for value, where in walk_numbers(data):
                if value not in SENTINELS:
                    continue
                totals[str(int(value))] += 1
                # `-1.0` is as much a sentinel as `-1`, but an int-only recount would
                # report a smaller number; the split is kept so the two agree.
                by_type["float" if isinstance(value, float) else "int"] += 1
                count += 1
                by_objclass[entry.get("objclass") or "?"] += 1
                key = f"{int(value)}@{path.name}"
                if len(examples[key]) < 2:
                    names = aliases(entry)
                    label = names[0] if names else (data.get("TypeName") or "?")
                    examples[key].append(f"{entry.get('objclass')}/{label}.{where}")
        if count:
            by_package[path.name] = count
    return {
        "total": sum(totals.values()),
        "values": {value: count for value, count in sorted(totals.items())},
        "byType": dict(sorted(by_type.items())),
        "byPackage": dict(sorted(by_package.items(), key=lambda kv: (-kv[1], kv[0]))),
        "topObjclasses": dict(by_objclass.most_common(8)),
        "examples": dict(sorted(examples.items())[:8]),
    }


def sentinel_scan(obb: Path, paths: list[Path] | None = None) -> dict:
    """Count sentinel-shaped numbers in the *source* fields we consume.

    Two numbers, two traversals — do not compare them as if they were one census:

    * `readPathTotal` walks a **fixed whitelist** of the fields the compiler
      actually reads (`LootConfig.LevelLength`, `LootTable.{Min,Max,Period}`,
      `PresentTable.Weight`, every `Award*` leaf under the two rift tables,
      `AwardConfig.{AwardQuantity,Probability}`, the `GamePropertySheet` constants).
      It counts `-1`, `2147483647` **and** `0`, because in those fields `0` really
      does mean "no value" (a rift payout of 0 coins, a present weight of 0).
    * `fullRecursive` walks **every int leaf of every objdata** in the same
      packages, plus the whole 2117-file package set, and counts only `-1` /
      `2147483647`. The gap between the two numbers is fields we never read plus
      the different `0` policy.

    A sentinel is never a reward: `LevelLength: -1`, `0` coins in a rift payout,
    `2147483647` as "no limit". They are counted here and excluded from every total.
    """

    fields: dict[str, Counter] = defaultdict(Counter)
    examples: dict[str, list[str]] = defaultdict(list)

    def note(label: str, value, where: str) -> None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return
        if value not in (0,) + SENTINELS:
            return
        fields[label][value] += 1
        if len(examples[f"{label}={value}"]) < 3:
            examples[f"{label}={value}"].append(where)

    doc = load_json(obb / LOOT_PKG)
    for entry, data in objects(doc):
        cls = entry.get("objclass") or ""
        if cls == "LootConfig":
            note("LootConfig.LevelLength", number(data.get("LevelLength")),
                 f"LootConfig/{aliases(entry)[0]}")
        elif cls == "LootTable":
            for index, row in enumerate(data.get("Entries") or []):
                if not isinstance(row, dict):
                    continue
                for key in ("Min", "Max", "Period"):
                    note(f"LootTable.{key}", number(row.get(key)),
                         f"LootTable/Entries[{index}].{key}")

    doc = load_json(obb / PRESENT_PKG)
    for entry, data in objects(doc):
        if (entry.get("objclass") or "") != "PresentTable":
            continue
        for index, row in enumerate(data.get("Entries") or []):
            if isinstance(row, dict):
                note("PresentTable.Weight", number(row.get("Weight")),
                     f"PresentTable/{data.get('TypeName')}.Entries[{index}]")

    for pkg, cls in ((RIFT_CLEAR_PKG, "RiftFirstClearRewards"), (RIFT_BOSS_PKG, "RiftZombossRewards")):
        doc = load_json(obb / pkg)
        for entry, data in objects(doc):
            if (entry.get("objclass") or "") != cls:
                continue
            for key, value in walk_awards(data):
                note(f"{cls}.{key}", number(value), f"{cls}/{aliases(entry)[0]}.{key}")

    doc = load_json(obb / AWARD_PKG)
    for entry, data in objects(doc):
        if (entry.get("objclass") or "") != "AwardConfigPropertySheet":
            continue
        for index, row in enumerate(data.get("GiftBoxRewards") or []):
            if not isinstance(row, dict):
                continue
            for key in ("AwardQuantity", "Probability"):
                note(f"AwardConfig.{key}", number(row.get(key)),
                     f"AwardConfig/GiftBoxRewards[{index}].{key}")

    doc = load_json(obb / GAME_PROPS_PKG)
    for entry, data in objects(doc):
        if (entry.get("objclass") or "") != "GamePropertySheet":
            continue
        for name in ECONOMY_CONSTANTS:
            if name in data:
                note(f"GamePropertySheet.{name}", number(data.get(name)), f"GamePropertySheet/{name}")

    totals: Counter = Counter()
    for counter in fields.values():
        for value, count in counter.items():
            totals[value] += count
    read_path_total = sum(totals.values())

    read_packages = recursive_sentinel_count(obb, [obb / name for name in READ_PACKAGES])
    whole_obb = recursive_sentinel_count(obb, list(paths) if paths is not None else [])
    return {
        # The two censuses and the exact fields behind the smaller one, so nobody has
        # to guess which number a bare "sentinels" refers to (audit L2, 2026-11-24).
        "scope": {
            "readPath": {
                "traversal": "fixed field whitelist, no recursion",
                "whitelist": list(READ_PATH_WHITELIST),
                "fieldsWithHits": sorted(fields),
                "values": ["-1", "0", "2147483647"],
                "packages": list(READ_PACKAGES),
                "whyZeroCounted": ("in these fields 0 means 'no value' (a rift payout of 0 "
                                   "coins, a present weight of 0 is switched off)"),
            },
            "fullRecursive": {
                "traversal": "every int leaf of every objdata, dicts and lists depth-first",
                "values": ["-1", "2147483647"],
                "packages": "readPackages = READ_PACKAGES; allPackages = the whole package set",
                "whyZeroExcluded": ("0 is a legitimate value in many objdata fields "
                                    "(cooldowns, probabilities, grid coordinates), so a "
                                    "recursive 0 census cannot tell 'no value' from 'zero'"),
            },
        },
        "readPathTotal": read_path_total,
        "totals": {str(value): count for value, count in sorted(totals.items())},
        "byField": {label: {str(value): count for value, count in sorted(counter.items())}
                    for label, counter in sorted(fields.items())},
        "examples": dict(sorted(examples.items())),
        "fullRecursive": {"readPackages": read_packages, "allPackages": whole_obb},
        "difference": (
            f"readPathTotal={read_path_total} counts only the whitelisted fields the "
            f"compiler reads (and counts 0); fullRecursive.readPackages.total="
            f"{read_packages['total']} and fullRecursive.allPackages.total="
            f"{whole_obb['total']} count every leaf for -1/2147483647 only. The gap is "
            "fields we never read plus the different 0 policy — neither number replaces "
            "the other. An int-only recount lands lower by the float count "
            f"(readPackages {read_packages['byType']}, allPackages {whole_obb['byType']})."
        ),
    }


def walk_awards(data, prefix=""):
    """Yield every (path, value) inside the nested award structures."""

    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, (dict, list)):
                yield from walk_awards(value, path)
            else:
                yield path, value
    elif isinstance(data, list):
        for index, value in enumerate(data):
            path = f"{prefix}[{index}]"
            if isinstance(value, (dict, list)):
                yield from walk_awards(value, path)
            else:
                yield path, value


def seed_drop_rows(obb: Path, paths: list[Path]) -> tuple[list[dict], dict]:
    """A zombie dropping a seed packet on death: `ZombieDeathSeedDropModuleProperties`.

    This is the one *per-zombie* drop the pack carries — a per-level module with an
    explicit `DropChance`, `DropOnAllZombieTypes` and a weighted `SeedDropList`.
    """

    rows: list[dict] = []
    modules = 0
    for path in paths:
        doc = load_json(path)
        if not doc:
            continue
        level_name = ""
        modules_here = []
        for entry, data in objects(doc):
            cls = entry.get("objclass") or ""
            if cls == "LevelDefinition":
                level_name = str(data.get("Name") or "")
            elif cls == "ZombieDeathSeedDropModuleProperties":
                modules_here.append((entry, data))
        for entry, data in modules_here:
            modules += 1
            chance = number(data.get("DropChance"))
            all_types = data.get("DropOnAllZombieTypes")
            for index, item in enumerate(data.get("SeedDropList") or []):
                if not isinstance(item, dict):
                    continue
                plant = str(item.get("PlantType"))
                rows.append({
                    "id": f"seeddrop:{path.stem}:{index}:{plant}",
                    "kind": "seed",
                    "amount": 1,
                    "amountRange": None,
                    "rewardType": plant,
                    "weight": number(item.get("Weight")),
                    "dropChance": chance,
                    "dropOnAllZombieTypes": all_types,
                    "pkg": path.name,
                    "levelName": level_name,
                    "world": "any",
                    "levelOrRange": f"zombie death drop in {path.stem}",
                    "firstOnly": False,
                    "source": f"{path.name}:objclass=ZombieDeathSeedDropModuleProperties/SeedDropList[{index}]",
                })
    rows.sort(key=lambda row: row["id"])
    return rows, {
        "modules": modules,
        "entries": len(rows),
        "chances": sorted({row["dropChance"] for row in rows if row["dropChance"] is not None}),
    }


def pinata_names(obb: Path) -> list[str]:
    """PinataType row names, read from their own sheet.

    They must not come from the merged pickup index: a CollectableType row with the
    same name in another package would mask the PinataType row (38 of 39 readable).
    """

    doc = load_json(obb / PINATA_PKG)
    names = set()
    for entry, data in objects(doc):
        if (entry.get("objclass") or "") != "PinataType":
            continue
        name = data.get("TypeName") or (aliases(entry) or [""])[0]
        if name:
            names.add(str(name))
    return sorted(names)


def build(obb: Path) -> dict:
    paths = s5scan.package_paths(obb)
    level = level_index(obb, paths)
    loot, loot_meta = loot_rows(obb)
    presents, dangling, present_meta = present_rows(obb, level)
    rift = rift_rows(obb)
    gifts = giftbox_rows(obb)
    seeds, seed_meta = seed_drop_rows(obb, paths)
    constants = constant_rows(obb)
    gates = gate_rows(obb)
    level_rewards = level_reward_rows(level)

    rewards = loot + presents + rift + gifts + seeds + constants + level_rewards
    for row in rewards:
        row["kind"] = normalize_kind(row["kind"])
    rewards.sort(key=lambda row: row["id"])

    ids = [row["id"] for row in rewards]
    duplicates = sorted({item for item in ids if ids.count(item) > 1})

    by_kind: Counter = Counter(row["kind"] for row in rewards)
    ordered_kinds = {}
    for kind in PRIMARY_KINDS + SECONDARY_KINDS:
        if by_kind.get(kind):
            ordered_kinds[kind] = by_kind.pop(kind)
    for kind in sorted(by_kind):
        ordered_kinds[kind] = by_kind[kind]

    pickups = collectables(obb)
    world_keys = sorted(name for name, row in pickups.items()
                        if str(row["data"].get("CollectableClass")) == "CollectableWorldKey")
    pinatas = pinata_names(obb)

    counts = {
        "rewards": len(rewards),
        "byKind": ordered_kinds,
        "lootRows": len(loot),
        "lootTableEntries": loot_meta.get("entries", 0),
        "presentRows": len(presents),
        "presentTables": present_meta.get("tables", 0),
        "riftRows": len(rift),
        "giftBoxRows": len(gifts),
        "seedDropRows": len(seeds),
        "seedDropModules": seed_meta["modules"],
        "seedDropChances": seed_meta["chances"],
        "constantRows": len(constants),
        "gateRows": len(gates),
        "levelRewardRows": len(level_rewards),
        "levels": level["levels"],
        "levelsWithFirstReward": level["firstLevels"],
        "levelsWithReplayReward": level["replayLevels"],
        "levelsByLoot": level["lootByRtid"],
        "levelsByPresentTable": level["presentByName"],
        "levelsByShinyPresentTable": level["shinyByName"],
        "danglingPresentTables": len(dangling),
        "danglingPresentRefs": sum(row["levels"] for row in dangling),
        "worldKeyCollectables": len(world_keys),
        "pinataTypes": len(pinatas),
        "keyLootWorlds": sorted({row["world"] for row in loot if row["kind"] == "key"}),
        "gatesByType": dict(Counter(row["gate"] for row in gates)),
        "duplicateIds": duplicates,
        "sentinels": sentinel_scan(obb, paths),
        "sentinelHits": sentinel_report(rewards),
        "filesScanned": len(paths),
    }

    sources = [
        {"sheet": "LootTable", "pkg": LOOT_PKG, "objclass": "LootTable",
         "rows": counts["lootTableEntries"],
         "fields": ["Type", "Min", "Max", "Period", "LevelLootKey", "EnabledAfter", "World",
                    "UniqueId", "DisableViaLiveToggle"],
         "hits": counts["lootRows"]},
        {"sheet": "LootConfig", "pkg": LOOT_PKG, "objclass": "LootConfig",
         "rows": len(loot_meta.get("configs") or {}),
         "fields": ["LevelLootKey", "LevelLength", "Disable"], "hits": counts["lootRows"]},
        {"sheet": "PresentTable", "pkg": PRESENT_PKG, "objclass": "PresentTable",
         "rows": present_meta.get("tables", 0), "fields": ["TypeName", "Shiny", "Entries"],
         "hits": counts["presentRows"]},
        {"sheet": "PresentTypeCoin", "pkg": PRESENT_TYPE_PKG, "objclass": "PresentTypeCoin",
         "rows": 3, "fields": ["TypeName", "CoinValue"], "hits": counts["presentRows"]},
        {"sheet": "CollectableType", "pkg": COLLECTABLE_PKG, "objclass": "CollectableCoinType|CollectableGemType|CollectableSunType|CollectableType",
         "rows": len(pickups), "fields": ["TypeName", "CoinValue", "GemValue", "SunValue", "ContentsCount", "CollectableClass"],
         "hits": len(LOOT_PICKUP)},
        {"sheet": "RiftFirstClearRewards", "pkg": RIFT_CLEAR_PKG, "objclass": "RiftFirstClearRewards",
         "rows": 1, "fields": ["DefaultLevelClearRewards", "LevelClearRewards"], "hits": counts["riftRows"]},
        {"sheet": "RiftZombossRewards", "pkg": RIFT_BOSS_PKG, "objclass": "RiftZombossRewards",
         "rows": 1, "fields": ["ProgressionRewards", "PinataTypeForOpeningSequence"], "hits": counts["riftRows"]},
        {"sheet": "AwardConfigPropertySheet", "pkg": AWARD_PKG, "objclass": "AwardConfigPropertySheet",
         "rows": 1, "fields": ["GiftBoxRewards"], "hits": counts["giftBoxRows"]},
        {"sheet": "GamePropertySheet", "pkg": GAME_PROPS_PKG, "objclass": "GamePropertySheet",
         "rows": 1, "fields": list(ECONOMY_CONSTANTS), "hits": counts["constantRows"]},
        {"sheet": "ZombieDeathSeedDropModuleProperties",
         "pkg": "pkg_0243|0249|0662|0664|0665|0918|0919|0921|0926|0933|0941|1114|1152|1690|1817_LevelDefinition.json",
         "objclass": "ZombieDeathSeedDropModuleProperties",
         "rows": counts["seedDropModules"],
         "fields": ["DropChance", "DropOnAllZombieTypes", "SeedDropList[].{PlantType, Weight}"],
         "hits": counts["seedDropRows"]},
        {"sheet": "WorldData", "pkg": WORLD_DATA_PKG, "objclass": "WorldData",
         "rows": 46, "fields": ["m_eventList.m_eventType", "m_eventList.m_cost"], "hits": counts["gateRows"]},
        {"sheet": "LevelDefinition", "pkg": "pkg_0234..pkg_2047_LevelDefinition.json",
         "objclass": "LevelDefinition",
         "rows": counts["levels"],
         "fields": ["Loot", "NormalPresentTable", "ShinyPresentTable", "FirstRewardType",
                    "FirstRewardParam", "ReplayRewardType", "ReplayRewardParam"],
         "hits": counts["levelsWithFirstReward"] + counts["levelsWithReplayReward"]},
    ]

    unknowns = [
        {"item": "mint 产出点", "verdict": "server-only",
         "why": "mint 只有价格没有来源：StoreProductProps.PriceMints 出现 565 行（都是价格，多为 0），"
                "任何表中都没有 mint 的奖励/掉落/兑换产出；Award 词表（costume/powerupuse/gems/plantXP/coins/pinata）"
                "与 LootTable.Type 词表（SilverCoin/GoldCoin/Gem/SmallSun/LargeSun/LawnMower/Sprout/*Key）都不含 mint。",
         "tried": [LOOT_PKG, AWARD_PKG, RIFT_CLEAR_PKG, RIFT_BOSS_PKG, "pkg_2081_StoreProductProps.json"]},
        {"item": "星章（star）作为奖励", "verdict": "server-only",
         "why": "星章只在 WorldData 的 star_gate.m_cost 里被花费（1/8/10/20 等），另有 "
                "GamePropertySheet.StarsPerCostume=20 换算；没有任何表的 Award/Type 词表把星章当奖励发放。",
         "tried": [WORLD_DATA_PKG, GAME_PROPS_PKG, AWARD_PKG, LOOT_PKG]},
        {"item": "被吃植物是否返还", "verdict": "absent",
         "why": "全库对 refund/return/reimburse 的键名检索只命中鹦鹉回船等待时间等无关字段，"
                "PlantPropertySheet 没有任何返还/退款字段；返还逻辑不在数据里。",
         "tried": ["pkg_2073_PlantPropertySheet.json", "pkg_0234_DisableSkipLevelModuleProperties.json"]},
        {"item": "首通 vs 重复通关的数值差额", "verdict": "partial",
         "why": "只有分类差异（FirstRewardType/Param 486 关 vs ReplayRewardType/Param 67 关）与开场/结尾对白的"
                "First/Replay 版本；没有「首通给 X 币、重复给 Y 币」这种数值对。重复通关的金币来源是 R03 的 present 与 R01 的掉落。",
         "tried": ["pkg_0234..pkg_2047_LevelDefinition.json", RIFT_CLEAR_PKG]},
        {"item": "shiny present 的触发时机", "verdict": "unknown",
         "why": "LevelDefinition 有独立的 NormalPresentTable / ShinyPresentTable 两列，"
                "CollectablePresentType 也有 IsShiny 标记，但没有任何字段说明何时用 shiny 列"
                "（首通？随机？）。输出里 shiny 行 firstOnly=false 并有 variant=\"shiny\"，不猜。",
         "tried": [PRESENT_PKG, PRESENT_TYPE_PKG, "pkg_0234..pkg_2047_LevelDefinition.json"]},
        {"item": "12 张缺失的 PresentTable", "verdict": "missing-from-pack",
         "why": "关卡引用了 lostcity/dark/eighties/beach/heian/kongfu 六世界的 normal+shiny 共 12 个表名"
                "（68 个关卡引用），全库 2117 个包里没有任何 PresentTable 行定义它们；"
                "这 68 关的通关 present 只能回退到别的世界的表或服务端下发。",
         "tried": [PRESENT_PKG, "全部 2117 个 pkg_*.json"]},
        {"item": "loot Type → 拾取物的映射表", "verdict": "inferred",
         "why": "SilverCoin/GoldCoin/Gem/SmallSun/LargeSun 这五个字面量同时出现在 LootTable.Type、"
                "LootOverrideModuleProperties.Overrides[].LootOverride、LootOverrideZombossRiftModuleProps.Entries[].Drop、"
                "PickupCollectableTutorialProperties.LootType、ZombieCarnieMonkeyProps.CoinType 五个字段里，"
                "但没有一张表把 Type 映射到 CollectableType；本表按命名约定映射并逐行标 mapping。",
         "tried": [LOOT_PKG, COLLECTABLE_PKG, "pkg_2112_ZombiePropertySheet.json"]},
        {"item": "EgyptKey 对应的拾取物", "verdict": "unresolved",
         "why": "LootTable 有 4 条 key 掉落（EgyptKey/PirateKey/CowboyKey/FutureKey，各带 World 字段），"
                "CollectableType 里有 10 个 worldkey_*（beach/cowboy/dark/dino/eighties/future/iceage/lostcity/modern/pirate），"
                "没有 worldkey_egypt，也没有任何 worldkey_* 带值字段；EgyptKey 对应哪一列无法从数据判定。",
         "tried": [LOOT_PKG, COLLECTABLE_PKG]},
        {"item": "pinata 内容物", "verdict": "absent",
         "why": "PinataType（pkg_2066，39 行）只有美术字段（PinataPopAnim/PinataResGroup/Thumbnail/QuestIcon/PinataOffsets），"
                "没有任何种子或权重；FirstRewardType=pinata 只给出 pinata 名字，内容由服务端/商店结算。",
         "tried": [PINATA_PKG, "pkg_2081_StoreProductProps.json"]},
        {"item": "每日/成就类货币产出", "verdict": "partial",
         "why": "LevelOfTheDayRewards.Rewards 只发 plantXP（Award=plantXP，AwardQuantity=1，Probability=100），"
                "QuestRewardTablesProps 只发 pinata；两处都不发 coin/gem/mint，所以日常任务的货币产出属于服务端。",
         "tried": ["pkg_2053_LevelOfTheDayRewards.json", "pkg_2086_QuestRewardTablesProps.json"]},
    ]

    return {
        "format": FORMAT,
        "generated": GENERATED,
        "generatedAt": generated_stamp(obb),
        "counts": counts,
        "rewards": rewards,
        "gates": gates,
        "danglingPresentTables": dangling,
        "worldKeys": world_keys,
        "pinataTypes": pinatas,
        "sources": sources,
        "unknowns": unknowns,
    }


def render(table: dict) -> str:
    return json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def dump(table: dict, path: Path) -> None:
    # Bytes, not write_text: write_text emits CRLF on Windows, which both breaks the
    # byte-for-byte --check comparison and makes diffs noisy for everyone else.
    path.write_bytes(render(table).encode("utf-8"))


def needle_report(obb: Path, needle: str) -> int:
    """Every package whose objdata mentions `needle` in a key or a string value."""

    needle_low = needle.lower()
    hits = 0
    for path in s5scan.package_paths(obb):
        doc = load_json(path)
        if not doc:
            continue
        for entry, data in objects(doc):
            for key, value in data.items():
                found_key = needle_low in key.lower()
                found_value = isinstance(value, str) and needle_low in value.lower()
                if not (found_key or found_value):
                    continue
                hits += 1
                print(f"{path.name}: objclass={entry.get('objclass')} {key} = {s5scan.short(value, 80)}")
    print(f"\n{needle}: {hits} hits across {len(s5scan.package_paths(obb))} packages")
    return 0


def check(table: dict, out_path: Path) -> int:
    problems: list[str] = []
    if table.get("format") != FORMAT:
        problems.append(f"format {table.get('format')!r} != {FORMAT!r}")
    if table.get("generated") != GENERATED:
        problems.append(f"generated {table.get('generated')!r} != {GENERATED!r}")

    rewards = table.get("rewards") or []
    counts = table.get("counts") or {}
    if counts.get("rewards") != len(rewards):
        problems.append(f"counts.rewards {counts.get('rewards')} != len(rewards) {len(rewards)}")
    by_kind = counts.get("byKind") or {}
    if sum(by_kind.values()) != len(rewards):
        problems.append(f"sum(counts.byKind) {sum(by_kind.values())} != len(rewards) {len(rewards)}")

    ids = [row.get("id") for row in rewards]
    if ids != sorted(ids):
        problems.append("rewards[] is not sorted by id")
    if len(set(ids)) != len(ids):
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        problems.append(f"duplicate reward ids: {duplicates[:5]}")

    for row in rewards:
        for field in ("kind", "world", "levelOrRange", "firstOnly", "source"):
            if field not in row:
                problems.append(f"row {row.get('id')} missing {field}")
                break
        amount = row.get("amount")
        if isinstance(amount, (int, float)) and amount in SENTINELS:
            problems.append(f"row {row.get('id')} carries a sentinel as a normal amount ({amount})")
        if "mapping" in row and "mappingNote" not in row:
            problems.append(f"row {row.get('id')} has a mapping but no mappingNote")

    sentinels = counts.get("sentinels") or {}
    read_path_total = sentinels.get("readPathTotal")
    totals_sum = sum((sentinels.get("totals") or {}).values())
    if read_path_total != totals_sum:
        problems.append(f"sentinels.readPathTotal {read_path_total} != sum(totals) {totals_sum}")
    scope = sentinels.get("scope") or {}
    if "readPath" not in scope or "fullRecursive" not in scope:
        problems.append("sentinels.scope must describe both traversals")
    full = sentinels.get("fullRecursive") or {}
    for key in ("readPackages", "allPackages"):
        if not isinstance(full.get(key), dict) or "total" not in (full.get(key) or {}):
            problems.append(f"sentinels.fullRecursive.{key} missing a total")

    if not out_path.exists():
        problems.append(f"{out_path.name} does not exist")
    else:
        raw = out_path.read_bytes()
        if b"\r\n" in raw:
            problems.append("shipped file contains CRLF")
        if raw.decode("utf-8") != render(table):
            problems.append("shipped file differs from a fresh render")

    if problems:
        for problem in problems:
            print(f"FAIL {problem}")
        return 1
    print(
        f"rewards={counts.get('rewards')} levels={counts.get('levels')} "
        f"loot={counts.get('lootRows')} presents={counts.get('presentRows')} "
        f"first={counts.get('levelsWithFirstReward')} replay={counts.get('levelsWithReplayReward')} "
        f"gates={counts.get('gateRows')} unknowns={len(table.get('unknowns') or [])}"
    )
    print("OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile level rewards / loot from the OBB tables.")
    parser.add_argument("--obb", default=str(DEFAULT_OBB), help="directory holding pkg_*.json")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="JSON table to write")
    parser.add_argument("--needle", default="", help="search the OBB for this text and exit")
    parser.add_argument("--check", action="store_true", help="recompute and compare, non-zero on drift")
    args = parser.parse_args(argv)

    obb = Path(args.obb)
    if args.needle:
        return needle_report(obb, args.needle)

    table = build(obb)
    out_path = Path(args.out)
    if args.check:
        return check(table, out_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    dump(table, out_path)
    counts = table["counts"]
    print(f"wrote {out_path.name}: rewards={counts['rewards']} byKind={counts['byKind']}")
    print(f"  loot={counts['lootRows']} presents={counts['presentRows']} "
          f"rift={counts['riftRows']} giftbox={counts['giftBoxRows']} "
          f"constants={counts['constantRows']} gates={counts['gateRows']}")
    print(f"  levels={counts['levels']} first={counts['levelsWithFirstReward']} "
          f"replay={counts['levelsWithReplayReward']} "
          f"danglingPresentTables={counts['danglingPresentTables']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
