"""Compile the per-kind *startup* parameters of every minigame into ``minigame_rules.json``.

``native/generated/minigames.json`` answers "which level mounts which minigame" (20 kinds,
813 of 1809 levels).  It does **not** answer "can the client actually start that minigame":
some kinds carry a full rule object (``CannonMinigameProperties`` has 11 fields), some carry
an empty ``{}`` (``ColumnMinigameProperties`` / ``InvisighoulMinigameProperties``), and some
of the parameters a real port needs simply do not exist in the shipped data at all (the
Whack-a-Zombie respawn interval, the Joust side lineups).

This compiler turns that into one table: per kind, the extracted parameters with their
**coverage** (how many of the kind's levels actually supply them), the parameters the
original data cannot supply, and a ``playable`` verdict that follows mechanically from
those two facts.

口径（R01..R09，报告 ``docs/reviews/2026-11-26-minigame-rules.md`` 逐条对应）:

  R01 参数只从**原版对象**里取：``minigames.json`` 的 ``params``（关卡包内嵌的 objdata）、
      关卡包本身（``SeedBankProperties`` 等不属于任何 kind 的模块对象）、
      ``level_mechanics.json``（只做交叉引用，不复制值）、``content/levels/*.json`` 的
      ``extra``（波次计数）。没有一处凭经验补值。
  R02 ``coverage`` = 该 kind 的关卡里**真能取到该字段**的关数，分母是 ``levels``。一个
      字段取到 9/73 就是 9/73，不写成 1。
  R03 ``playable`` 判据（机械可复核，不靠人判断）：
        playable = 锚点类存在，且锚点至少在一关里有非空 objdata，且每个 critical 参数的
                   coverage > 0。
      也就是「模块名挂着、但参数对象是空 ``{}``」一定判 false（column / invisighoul）。
  R04 ``missing`` 只装 critical 且 coverage == 0 的参数；``missingOptional`` 装非 critical
      的缺口（含「原版根本没有这个字段」，理由逐条写明）。critical 缺口必然让
      playable=false，二者由 ``check`` 交叉验证。
  R05 ``levelsIncomplete`` 给出逐关缺口：哪些关缺哪个 critical 参数。kind 判 true 而个别关
      缺字段时，这里就是「哪些关起不来」的清单。
  R06 ``conveyor`` / ``protecttheplant`` / ``tide`` 三种玩法**不重复抽取**：``params`` 里只
      放交叉引用路径（``level_mechanics.json#levels.<id>.conveyor`` 等）与覆盖率，值留在
      mechanics 产物里。
  R07 哨兵值原样记录并单独列出（bowling ``BowlingFoulLine = 99999``、beghouled
      ``MatchesToWin = 1000000``），不当成可用参数。
  R08 找不到独立模块的玩法（ZombieChicken）写进 ``absentKinds`` 并附取证来源，不用僵尸
      属性或星章挑战硬凑。
  R09 产物确定性：固定 ``generated`` 日期、``sort_keys``、紧凑 separators、LF 换行、
      ``--check`` 重新渲染后逐字节比对（过期 exit 1）。

Usage:
    python tools/contentc/minigame_rules.py                  # 写 native/generated/minigame_rules.json
    python tools/contentc/minigame_rules.py --check          # 与磁盘逐字节比对
    python tools/contentc/minigame_rules.py -n bullet        # 打印命中关键词的 kind / 参数 / 类名
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portable import portable  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MINI = ROOT / "native" / "generated" / "minigames.json"
DEFAULT_MECH = ROOT / "native" / "generated" / "level_mechanics.json"
DEFAULT_LEVELS = ROOT / "content" / "levels"
DEFAULT_OBB = Path(
    os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages")
)
DEFAULT_OUT = ROOT / "native" / "generated" / "minigame_rules.json"

FORMAT = "pvz2-shuttle/minigame-rules@1"
GENERATED = "2026-11-26"

# 原版类名（逐条由 probe 证实，见报告 §2）
CLS_LASTSTAND = "LastStandMinigameProperties"
CLS_VASE = "VaseBreakerPresetProperties"
CLS_VASE_ENDLESS = "VaseBreakerEndlessProperties"
CLS_RAIL = "RailcartProperties"
CLS_BEGH_PRESET = "BeghouledPresetProperties"
CLS_BEGH_SPAWNER = "BeghouledZombieSpawnerProperties"
CLS_BEGH_BANK = "BeghouledSeedBankProperties"
CLS_WHACK = "MinigameWhackAZombieModuleProperties"
CLS_WHACK_SPAWN = "SpawnWhackAZombiesProps"
CLS_JOUST = "JoustGameModuleProperties"
CLS_BOWLING = "BowlingMinigameProperties"
CLS_COLUMN = "ColumnMinigameProperties"
CLS_CANNON = "CannonMinigameProperties"
CLS_INVISI = "InvisighoulMinigameProperties"
CLS_COWBOY = "CowboyMinigameProperties"
CLS_BIGTROUBLE = "BigTroubleLittleZombieMinigameProperties"
CLS_CAMEL = "CamelMinigameProperties"
CLS_DEATH = "DeathExplosionMiniGameModuleProperties"
CLS_SPROUT = "SproutPlantingMinigameProperties"
CLS_STARS = "SeeingStarsModuleProperties"
CLS_BONUS = "BonusChallengeModuleProperties"
CLS_CONVEYOR_BANK = "ConveyorSeedBankProperties"
CLS_TIDE = "TideProperties"
CLS_PROTECT = "ProtectThePlantChallengeProperties"
CLS_SEEDBANK = "SeedBankProperties"

MODULE_SUN = "DefaultSunDropper"

MECH_CONVEYOR = "level_mechanics.json#levels.<id>.conveyor"
MECH_PROTECT = "level_mechanics.json#levels.<id>.protectThePlant"
MECH_TIDE = "level_mechanics.json#levels.<id>.events.tide"
MINI_TIDE = "minigames.json#levels.<id>.params.tide.TideProperties[0].StartingWaveLocation"
MINI_CONVEYOR_SLOTS = "minigames.json#levels.<id>.params.conveyor.ConveyorSeedBankProperties[0]"

SENTINEL_VALUES = {99999, 1000000, 2147483647}

# 「原版没有这个字段」的说明（报告 §6 同文）
ABSENT_WHACK_INTERVAL = (
    "spawnIntervalSeconds: 原版 Whack-a-Zombie 没有刷新间隔字段;"
    "SpawnWhackAZombiesProps 只给 Zombies/GroupSize/ZombieCondition，节奏在引擎默认值里"
)
ABSENT_JOUST_LINEUPS = (
    "{name}: 原版没有双方独立阵容字段; JoustGameModuleProperties 只有 TimeLimit / "
    "SuggestedLoadout (SunBasic|NoSunBasic|NoSunMagic) / LeagueModifiers，僵尸池见 "
    "level_mechanics.json#levels.<id>.spawners，植物侧见 SeedBankProperties.PresetPlantList"
)
ABSENT_COWBOY_GAMEPLAY = (
    "cowboy 自身模块只有教程文案 (BeginString/ShowTutorial)，玩法靠 CowboyRails（归 rail kind）"
)


def p_class(name: str, cls: str, field: str, crit: bool = False) -> Dict[str, Any]:
    """参数来自 minigames.json 的 params（关卡包内嵌对象）。field='*' 表示「任意字段」。"""
    return {"name": name, "critical": crit, "via": "class", "cls": cls, "field": field}


def p_any(name: str, cls: str, field: str, crit: bool = False) -> Dict[str, Any]:
    """参数来自**任意 kind** 的 params（典型：bowling 的子弹池挂在 conveyor 下）。"""
    return {"name": name, "critical": crit, "via": "classAny", "cls": cls, "field": field}


def p_pkg(name: str, cls: str, field: str, crit: bool = False) -> Dict[str, Any]:
    """参数来自关卡包里的任意对象（不属于任何 kind 的模块，如 SeedBankProperties）。"""
    return {"name": name, "critical": crit, "via": "pkg", "cls": cls, "field": field}


def p_module(name: str, alias: str, crit: bool = False) -> Dict[str, Any]:
    """参数由「模块是否挂在这关」直接派生（布尔）。"""
    return {"name": name, "critical": crit, "via": "module", "alias": alias}


def p_cross(name: str, path: str, crit: bool = False) -> Dict[str, Any]:
    """交叉引用：只记路径与覆盖率，值留在目标产物里（R06）。"""
    return {"name": name, "critical": crit, "via": "cross", "path": path}


def p_content(name: str, key: str, crit: bool = False) -> Dict[str, Any]:
    """参数来自 content/levels/<id>.json 的 extra（波次计数等）。"""
    return {"name": name, "critical": crit, "via": "content", "key": key}


def p_derived(name: str, rule: str, crit: bool = False) -> Dict[str, Any]:
    """由已抽到的字段算出来的派生量（rule 写在报告里，不藏逻辑）。"""
    return {"name": name, "critical": crit, "via": "derived", "rule": rule}


def p_absent(name: str, reason: str) -> Dict[str, Any]:
    """原版数据根本没有的字段：coverage 恒 0，进 missingOptional（或 critical 让 playable=false）。"""
    return {"name": name, "critical": False, "via": "absent", "reason": reason}


# kind -> 锚点类 / 参数 / 依赖（dependsOn 只做记录，不参与 playable 判定）
SPECS: Dict[str, Dict[str, Any]] = {
    "vasebreaker": {
        "anchors": [CLS_VASE, CLS_VASE_ENDLESS],
        "params": [
            p_class("vases", CLS_VASE, "Vases", crit=True),
            p_class("minColumnIndex", CLS_VASE, "MinColumnIndex", crit=True),
            p_class("maxColumnIndex", CLS_VASE, "MaxColumnIndex", crit=True),
            p_class("coloredPlantVases", CLS_VASE, "NumColoredPlantVases"),
            p_class("coloredZombieVases", CLS_VASE, "NumColoredZombieVases"),
            p_class("excludelist", CLS_VASE, "GridSquareExcludelist"),
            p_class("blacklist", CLS_VASE, "GridSquareBlacklist"),
            p_class("vaseGridItemType", CLS_VASE, "VaseGridItemType"),
            p_class("endlessStages", CLS_VASE_ENDLESS, "Stages"),
        ],
        "dependsOn": [],
        "notes": [
            "逐罐 row/col 与逐罐阳光在原版 Vases[] 里不存在（见 vasebreaker.json 的 unknowns）",
        ],
    },
    "rail": {
        "anchors": [CLS_RAIL],
        "params": [
            p_class("rails", CLS_RAIL, "Rails", crit=True),
            p_class("railcarts", CLS_RAIL, "Railcarts", crit=True),
            p_class("railcartType", CLS_RAIL, "RailcartType"),
        ],
        "dependsOn": [],
        "notes": ["1 关把 RailcartType 写成 RailcarType（原版拼写），已单独进 unknowns"],
    },
    "laststand": {
        "anchors": [CLS_LASTSTAND],
        "params": [
            p_class("startingSun", CLS_LASTSTAND, "StartingSun", crit=True),
            p_class("startingPlantfood", CLS_LASTSTAND, "StartingPlantfood", crit=True),
            p_content("waveCount", "wave_count", crit=True),
            p_pkg("seedBankSlots", CLS_SEEDBANK, "OverrideSeedSlotsCount"),
            p_module("sunFromSky", MODULE_SUN),
            p_pkg("presetSeedList", CLS_SEEDBANK, "PresetPlantList"),
            p_pkg("selectionMethod", CLS_SEEDBANK, "SelectionMethod"),
            p_class("preSeedchooserFlow", CLS_LASTSTAND, "PreSeedchooserFlow"),
            p_content("originalWaves", "original_waves"),
        ],
        "dependsOn": [],
        "notes": [
            "critical 只放「开局必须由数据给出的量」：初始阳光、初始植物food、波数；"
            "seedBankSlots(9/73) 与 sunFromSky(7/73) 是「原版没写就用引擎默认槽位 / 不许天降阳光」，"
            "所以不作 playable 门槛，但 coverage 照实给",
            "SeedBank 大小 = SeedBankProperties.OverrideSeedSlotsCount；只有 9 关显式写，其余走默认",
            "sunFromSky = Modules[] 里是否挂 DefaultSunDropper（本 kind 7/73 挂）",
        ],
    },
    "beghouled": {
        "anchors": [CLS_BEGH_PRESET],
        "params": [
            p_class("initialPlants", CLS_BEGH_PRESET, "InitialPlants", crit=True),
            p_class("matchesToWin", CLS_BEGH_PRESET, "MatchesToWin", crit=True),
            p_class("upgradeMap", CLS_BEGH_PRESET, "UpgradeMap"),
            p_class("stages", CLS_BEGH_SPAWNER, "Stages"),
            p_class("matchCountsToStageAdvance", CLS_BEGH_SPAWNER, "MatchCountsToStageAdvance"),
            p_class("presetPlantList", CLS_BEGH_BANK, "PresetPlantList"),
            p_class("upgradeList", CLS_BEGH_BANK, "BeghouledUpgradeList"),
            p_class("selectionMethod", CLS_BEGH_BANK, "SelectionMethod"),
        ],
        "dependsOn": [],
        "notes": ["MatchesToWin 有 1000000 的哨兵（1 关），游戏里等于「不可能达标」，照原样收录"],
    },
    "whackazombie": {
        "anchors": [CLS_WHACK],
        "params": [
            p_class("hammerHitValue", CLS_WHACK, "HammerHitValue", crit=True),
            p_class("hammerTapsToDecay", CLS_WHACK, "HammerTapsToDecay", crit=True),
            p_class("targets", CLS_WHACK_SPAWN, "Zombies", crit=True),
            p_class("groupSize", CLS_WHACK_SPAWN, "GroupSize"),
            p_class("zombieCondition", CLS_WHACK_SPAWN, "ZombieCondition"),
            p_class("additionalPlantfood", CLS_WHACK_SPAWN, "AdditionalPlantfood"),
            p_class("dynamicPlantfood", CLS_WHACK_SPAWN, "DynamicPlantfood"),
            p_absent("spawnIntervalSeconds", ABSENT_WHACK_INTERVAL),
        ],
        "dependsOn": [],
        "notes": ["目标数 = targets 列表长度；刷新间隔原版没有字段"],
    },
    "joust": {
        "anchors": [CLS_JOUST],
        "params": [
            p_class("timeLimit", CLS_JOUST, "TimeLimit", crit=True),
            p_class("suggestedLoadout", CLS_JOUST, "SuggestedLoadout"),
            p_class("leagueModifiers", CLS_JOUST, "LeagueModifiers"),
            p_absent("playerLineup", ABSENT_JOUST_LINEUPS.format(name="playerLineup")),
            p_absent("opponentLineup", ABSENT_JOUST_LINEUPS.format(name="opponentLineup")),
        ],
        "dependsOn": ["conveyor"],
        "notes": [
            "本 kind 只提供计分赛的时间上限与难度联赛；阵容在数据里没有『双方』概念",
        ],
    },
    "bowling": {
        "anchors": [CLS_BOWLING],
        "params": [
            p_class("foulLine", CLS_BOWLING, "BowlingFoulLine", crit=True),
            p_any("bulbPool", CLS_CONVEYOR_BANK, "InitialPlantList"),
            p_any("dropDelayConditions", CLS_CONVEYOR_BANK, "DropDelayConditions"),
            p_any("speedConditions", CLS_CONVEYOR_BANK, "SpeedConditions"),
            p_derived(
                "bulletBudget",
                "sum(MaxCount) over params.conveyor.ConveyorSeedBankProperties[0].InitialPlantList[]",
            ),
        ],
        "dependsOn": ["conveyor"],
        "notes": [
            "子弹序列 = 该关 ConveyorBelt 的 InitialPlantList（tool_projectile_bowlingbulb1/2/3"
            "/_explode/_mega）；只有挂了 ConveyorBelt 的关才有",
            "BowlingFoulLine 有 99999 哨兵（4 关），照原样收录并列入 sentinels",
        ],
    },
    "column": {
        "anchors": [CLS_COLUMN],
        "params": [
            p_class("gamemodeParams", CLS_COLUMN, "*", crit=True),
            p_any("conveyorSeedBank", CLS_CONVEYOR_BANK, "InitialPlantList"),
        ],
        "dependsOn": ["conveyor"],
        "notes": ["ColumnMinigameProperties 在 8 关里 objdata 全是 {}（空对象）"],
    },
    "cannon": {
        "anchors": [CLS_CANNON],
        "params": [
            p_class("lanes", CLS_CANNON, "Lanes", crit=True),
            p_class("rowHasCannon", CLS_CANNON, "RowHasCannon", crit=True),
            p_class("minScore", CLS_CANNON, "MinScore", crit=True),
            p_class("comboBrackets", CLS_CANNON, "ComboBrackets", crit=True),
            p_class("baseMovementRate", CLS_CANNON, "BaseMovementRate"),
            p_class("slowdownMovementRate", CLS_CANNON, "SlowdownMovementRate"),
            p_class("bufferDistance", CLS_CANNON, "BufferDistance"),
            p_class("baseZombieKillScore", CLS_CANNON, "BaseZombieKillScore"),
            p_class("minRewardGold", CLS_CANNON, "MinRewardGold"),
            p_class("maxRewardGold", CLS_CANNON, "MaxRewardGold"),
            p_class("resourceGroupNames", CLS_CANNON, "ResourceGroupNames"),
        ],
        "dependsOn": [],
        "notes": ["本 kind 参数最全（11 个字段覆盖 8/8 关）"],
    },
    "invisighoul": {
        "anchors": [CLS_INVISI],
        "params": [
            p_class("gamemodeParams", CLS_INVISI, "*", crit=True),
            p_any("conveyorSeedBank", CLS_CONVEYOR_BANK, "InitialPlantList"),
        ],
        "dependsOn": ["conveyor"],
        "notes": ["InvisighoulMinigameProperties 在 8 关里 objdata 全是 {}（空对象）"],
    },
    "cowboy": {
        "anchors": [CLS_COWBOY],
        "params": [
            p_class("beginString", CLS_COWBOY, "BeginString", crit=True),
            p_class("showTutorial", CLS_COWBOY, "ShowTutorial"),
        ],
        "dependsOn": ["rail"],
        "notes": [ABSENT_COWBOY_GAMEPLAY],
    },
    "bigtrouble": {
        "anchors": [CLS_BIGTROUBLE],
        "params": [
            p_class("zombieScale", CLS_BIGTROUBLE, "ZombieScale", crit=True),
            p_class("zombieIncomingDamageScale", CLS_BIGTROUBLE, "ZombieIncomingDamageScale", crit=True),
            p_class("zombieAddSpeedScaleMin", CLS_BIGTROUBLE, "ZombieAddSpeedScaleMin"),
            p_class("zombieAddSpeedScaleMax", CLS_BIGTROUBLE, "ZombieAddSpeedScaleMax"),
        ],
        "dependsOn": [],
        "notes": [],
    },
    "camel": {
        "anchors": [CLS_CAMEL],
        "params": [
            p_class("cardTypesUsed", CLS_CAMEL, "CardTypesUsed", crit=True),
            p_class("cardMatchingTime", CLS_CAMEL, "CardMatchingTime"),
            p_class("cardNoMatchTime", CLS_CAMEL, "CardNoMatchTime"),
            p_class("camelSegmentRiseStagger", CLS_CAMEL, "CamelSegmentRiseStagger"),
            p_class("minSpawnXStart", CLS_CAMEL, "MinSpawnXStart"),
            p_class("minSpawnXEnd", CLS_CAMEL, "MinSpawnXEnd"),
            p_class("maxSpawnX", CLS_CAMEL, "MaxSpawnX"),
            p_class("additionalXBufferBetweenChains", CLS_CAMEL, "AdditionalXBufferBetweenChains"),
            p_class("initialTutorialZombieRiseDelay", CLS_CAMEL, "InitialTutorialZombieRiseDelay"),
            p_class("showTutorial", CLS_CAMEL, "ShowTutorial"),
        ],
        "dependsOn": [],
        "notes": ["原版还有个无字段名的注释键 '# Delay time ...'（0），已随字段一起带出"],
    },
    "deathexplosion": {
        "anchors": [CLS_DEATH],
        "params": [
            p_class("hurtZombies", CLS_DEATH, "HurtZombies", crit=True),
            p_class("hurtPlants", CLS_DEATH, "HurtPlants", crit=True),
            p_class("hurtGridItems", CLS_DEATH, "HurtGridItems", crit=True),
            p_class("explodeDamageForZombies", CLS_DEATH, "ExplodeDamageForZombies"),
            p_class("explodeDamageForPlants", CLS_DEATH, "ExplodeDamageForPlants"),
            p_class("explodeDamageForGridItems", CLS_DEATH, "ExplodeDamageForGridItems"),
        ],
        "dependsOn": [],
        "notes": [],
    },
    "sproutplanting": {
        "anchors": [CLS_SPROUT],
        "params": [
            p_class("plantWeights", CLS_SPROUT, "PlantWeights", crit=True),
            p_class("startingSproutCount", CLS_SPROUT, "StartingSproutCount", crit=True),
            p_class("timeToPlantAllSprouts", CLS_SPROUT, "TimeToPlantAllSprouts"),
        ],
        "dependsOn": [],
        "notes": [],
    },
    "seeingstars": {
        "anchors": [CLS_STARS],
        "params": [
            p_class("targetPositions", CLS_STARS, "TargetPositions", crit=True),
            p_class("plantTypeName", CLS_STARS, "PlantTypeName", crit=True),
            p_class("plantAnimToPlay", CLS_STARS, "PlantAnimToPlay"),
        ],
        "dependsOn": [],
        "notes": [],
    },
    "bonuschallenge": {
        "anchors": [CLS_BONUS],
        "params": [
            p_class("challenges", CLS_BONUS, "Challenges", crit=True),
            p_class("challengesAlwaysAvailable", CLS_BONUS, "ChallengesAlwaysAvailable"),
            p_pkg("challengePropClasses", "*StarChallenge*Props", "*"),
        ],
        "dependsOn": [],
        "notes": [
            "Challenges 是 RTID 引用列表（本作 2 关都是 ZombieDistance），被引用的 props 对象"
            "在同一关卡包里，challengePropClasses 列出它们的类名（交叉引用，不复制值）",
        ],
    },
    "conveyor": {
        "anchors": [CLS_CONVEYOR_BANK],
        "params": [
            p_cross("mechanicsConveyor", MECH_CONVEYOR, crit=True),
            p_cross("slots", MINI_CONVEYOR_SLOTS),
        ],
        "dependsOn": [],
        "notes": ["按 R06 只给交叉引用路径与覆盖率，值留在 level_mechanics.json / minigames.json"],
    },
    "tide": {
        "anchors": [CLS_TIDE],
        "params": [
            p_cross("mechanicsTideEvents", MECH_TIDE, crit=True),
            p_cross("startingWaveLocation", MINI_TIDE),
        ],
        "dependsOn": [],
        "notes": [
            "level_mechanics.json 把涨潮记在 events.tide（changeAmount/changeType/wave 列表），"
            "没有独立 tide 字段；起潮波次在 minigames.json 的 TideProperties.StartingWaveLocation",
        ],
    },
    "protecttheplant": {
        "anchors": [CLS_PROTECT],
        "params": [
            p_cross("mechanicsProtect", MECH_PROTECT, crit=True),
            p_cross("mustProtectCount", MINI_PROTECT := (
                "minigames.json#levels.<id>.params.protecttheplant."
                "ProtectThePlantChallengeProperties[0].MustProtectCount"
            )),
        ],
        "dependsOn": [],
        "notes": ["按 R06 只给交叉引用路径与覆盖率，值留在 level_mechanics.json / minigames.json"],
    },
}

KIND_ORDER = tuple(SPECS)


# --------------------------------------------------------------------------- io


_CACHE: Dict[str, Any] = {}


def load_json(path: Path) -> Dict[str, Any]:
    key = str(Path(path).resolve())
    if key not in _CACHE:
        _CACHE[key] = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return _CACHE[key]


def iter_objects(doc: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for obj in (doc or {}).get("objects") or []:
        if isinstance(obj, dict) and isinstance(obj.get("objdata"), dict):
            yield obj


def package_paths(obb_dir: Path, stem: str) -> List[Path]:
    return sorted(Path(obb_dir).glob(stem + "_*.json"))


def package_classes(obb_dir: Path, stem: str) -> Dict[str, List[Dict[str, Any]]]:
    """关卡包 -> {objclass: [objdata...]}；整包只读一次（缓存）。"""
    key = "pkg:" + stem
    if key in _CACHE:
        return _CACHE[key]
    table: Dict[str, List[Dict[str, Any]]] = {}
    for path in package_paths(obb_dir, stem):
        try:
            doc = load_json(path)
        except (OSError, ValueError):
            continue
        for obj in iter_objects(doc):
            table.setdefault(obj.get("objclass") or "", []).append(obj["objdata"])
    _CACHE[key] = table
    return table


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------- value plumbing


def field_values(rows: Sequence[Dict[str, Any]], field: str) -> List[Any]:
    """从一个类在一关里的全部对象里取字段值；field='*' 表示「任意字段名列表」。"""
    out: List[Any] = []
    for row in rows:
        if field == "*":
            if row:
                out.append(sorted(row.keys()))
            continue
        if field in row:
            out.append(row[field])
    return out


def mech_lookup(mech_levels: Dict[str, Any], level_file: str, path: str) -> Tuple[bool, Optional[Path]]:
    """按交叉引用路径取值：只回答「有没有」，值留在原产物里。"""
    doc = MECH_CONVEYOR if path is None else path
    level = mech_levels.get(level_file)
    if not isinstance(level, dict):
        return False, None
    parts = doc.split("#", 1)[1].split(".")
    # levels.<id>.<a>.<b> -> 去掉 'levels' 与 '<id>' 两段
    node: Any = level
    for part in parts[2:]:
        if not isinstance(node, dict) or part not in node:
            return False, None
        node = node[part]
    if node in (None, [], {}):
        return False, None
    return True, None


def mini_lookup(entry: Dict[str, Any], path: str) -> bool:
    """minigames.json#levels.<id>.params.<kind>.<cls>[0].<Field> 形式的交叉引用。

    ``<Field>`` 可以省略（只问「这个对象在不在」），这时段落数是 3。
    """
    body = path.split("#", 1)[1]
    parts = body.split(".")
    # levels.<id>.params.<kind>.<cls>[0](.<Field...>)  -> 去掉 levels / <id> / params
    rest = parts[3:]
    if len(rest) < 2:
        return False
    kind = rest[0]
    cls = rest[1].split("[")[0]
    field = ".".join(rest[2:])
    rows = (entry.get("params") or {}).get(kind, {}).get(cls) or []
    if not rows:
        return False
    if not field:
        return True
    return any(field in row for row in rows)


def summarize(values: Sequence[Any]) -> Dict[str, Any]:
    """把一列值压成「可读的覆盖率证据」，不丢种类信息。"""
    if not values:
        return {}
    kinds = Counter(type(v).__name__ for v in values)
    out: Dict[str, Any] = {"type": sorted(kinds)[0] if len(kinds) == 1 else "mixed"}
    if len(kinds) > 1:
        out["types"] = dict(sorted(kinds.items()))

    def all_numbers() -> bool:
        return all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)

    if all_numbers():
        distinct = sorted({v for v in values})
        out["min"] = min(values)
        out["max"] = max(values)
        out["distinct"] = len(distinct)
        if len(distinct) <= 12:
            out["values"] = distinct
        return out
    if all(isinstance(v, str) for v in values):
        distinct = sorted(set(values))
        out["distinct"] = len(distinct)
        out["values"] = distinct[:12]
        return out
    if all(isinstance(v, list) for v in values):
        lengths = [len(v) for v in values]
        out["items"] = sum(lengths)
        out["minItems"] = min(lengths)
        out["maxItems"] = max(lengths)
        out["distinctLengths"] = sorted(set(lengths))
        return out
    if all(isinstance(v, dict) for v in values):
        keys: Counter = Counter()
        for v in values:
            keys.update(v.keys())
        out["objects"] = len(values)
        out["keys"] = sorted(keys)
        return out
    if all(isinstance(v, bool) for v in values):
        out["true"] = sum(1 for v in values if v)
        out["false"] = len(values) - out["true"]
        return out
    out["distinct"] = len({json.dumps(v, sort_keys=True, ensure_ascii=False) for v in values})
    return out


def level_row_values(
    param: Dict[str, Any],
    entry: Dict[str, Any],
    kind: str,
    mech_levels: Dict[str, Any],
    levels_dir: Path,
    obb_dir: Path,
) -> List[Any]:
    """某一关里该参数的全部取值（可能多对象 -> 多值）；空列表=这关没有。"""
    via = param["via"]
    if via == "class":
        rows = (entry.get("params") or {}).get(kind, {}).get(param["cls"]) or []
        return field_values(rows, param["field"])
    if via == "classAny":
        out: List[Any] = []
        for other in sorted(entry.get("params") or {}):
            rows = (entry["params"] or {}).get(other, {}).get(param["cls"]) or []
            out.extend(field_values(rows, param["field"]))
        return out
    if via == "pkg":
        table = package_classes(obb_dir, entry.get("package") or "")
        if param["cls"] == "*StarChallenge*Props":
            out: List[Any] = []
            hits = sorted(c for c in table if c.startswith("StarChallenge") and c.endswith("Props"))
            if hits:
                out.append(hits)
            return out
        rows = table.get(param["cls"]) or []
        return field_values(rows, param["field"])
    if via == "module":
        # 挂上才算「有」；没挂就是缺（否则 coverage 恒等于 levels，这一栏等于没说）
        return [True] if param["alias"] in (entry.get("modules") or []) else []
    if via == "cross":
        path = param["path"]
        if path.startswith("level_mechanics.json"):
            ok, _ = mech_lookup(mech_levels, entry.get("levelFile") or "", path)
            return [True] if ok else []
        if path.startswith("minigames.json"):
            return [True] if mini_lookup(entry, path) else []
        return []
    if via == "content":
        doc_path = Path(levels_dir) / ((entry.get("levelFile") or "") + ".json")
        if not doc_path.exists():
            return []
        extra = (load_json(doc_path).get("extra") or {})
        return [extra[param["key"]]] if param["key"] in extra else []
    if via == "derived":
        if param["rule"].startswith("sum(MaxCount)"):
            rows = (entry.get("params") or {}).get("conveyor", {}).get(CLS_CONVEYOR_BANK) or []
            if not rows:
                return []
            slots = rows[0].get("InitialPlantList") or []
            total = 0
            for slot in slots:
                if isinstance(slot, dict):
                    total += int(slot.get("MaxCount") or 0)
            return [total]
        return []
    if via == "absent":
        return []
    return []


def is_sentinel(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value in SENTINEL_VALUES


# ------------------------------------------------------------------- compilation


def collect_kind(
    kind: str,
    spec: Dict[str, Any],
    entries: List[Tuple[str, Dict[str, Any]]],
    mech_levels: Dict[str, Any],
    levels_dir: Path,
    obb_dir: Path,
) -> Dict[str, Any]:
    total = len(entries)
    params: Dict[str, Any] = {}
    evidence: List[str] = []
    levels_anchor = 0
    levels_anchor_nonempty = 0
    sentinels: List[Dict[str, Any]] = []
    per_level_missing: Dict[str, List[str]] = {}

    for level_file, entry in entries:
        has_any = False
        nonempty = False
        for cls in spec["anchors"]:
            rows = (entry.get("params") or {}).get(kind, {}).get(cls) or []
            if rows:
                has_any = True
                if any(r for r in rows):
                    nonempty = True
        levels_anchor += 1 if has_any else 0
        levels_anchor_nonempty += 1 if nonempty else 0

    for param in spec["params"]:
        values: List[Any] = []
        covered = 0
        per_param_sentinels: List[Any] = []
        for level_file, entry in entries:
            got = level_row_values(param, entry, kind, mech_levels, levels_dir, obb_dir)
            if got:
                covered += 1
                values.extend(got)
                per_param_sentinels.extend(v for v in got if is_sentinel(v))
        entry_out: Dict[str, Any] = {
            "critical": param["critical"],
            "coverage": covered,
            "levels": total,
            "via": param["via"],
        }
        if param["via"] == "class":
            entry_out["source"] = "%s.%s" % (param["cls"], param["field"])
        elif param["via"] == "classAny":
            entry_out["source"] = "any kind params: %s.%s" % (param["cls"], param["field"])
        elif param["via"] == "pkg":
            entry_out["source"] = "package objects: %s.%s" % (param["cls"], param["field"])
        elif param["via"] == "module":
            entry_out["source"] = "Modules[] contains %s" % param["alias"]
        elif param["via"] == "cross":
            entry_out["source"] = param["path"]
        elif param["via"] == "content":
            entry_out["source"] = "content/levels/<id>.json#extra.%s" % param["key"]
        elif param["via"] == "derived":
            entry_out["source"] = param["rule"]
        elif param["via"] == "absent":
            entry_out["source"] = "absent"
            entry_out["reason"] = param["reason"]
        if values and param["via"] != "cross":
            # cross 只记「有没有」，值留在原产物里（R06）；连 True 这种派生值也不写进去
            entry_out["agg"] = summarize(values)
        params[param["name"]] = entry_out
        if param["via"] != "absent":
            evidence.append(
                "%s: %d/%d %s"
                % (
                    param["name"],
                    covered,
                    total,
                    entry_out["source"],
                )
            )
        if per_param_sentinels:
            sentinels.append(
                {
                    "kind": kind,
                    "param": param["name"],
                    "source": entry_out["source"],
                    "values": sorted({v for v in per_param_sentinels}),
                    "levels": len(per_param_sentinels),
                }
            )

    critical = [p for p in spec["params"] if p["critical"]]
    missing = [p["name"] for p in critical if params[p["name"]]["coverage"] == 0]
    missing_optional = []
    for p in spec["params"]:
        if p["critical"]:
            continue
        if p["via"] == "absent":
            missing_optional.append({"name": p["name"], "reason": p["reason"]})
        elif params[p["name"]]["coverage"] == 0:
            missing_optional.append(
                {"name": p["name"], "reason": "原版该类字段在本 kind 的关卡里一次都没出现"}
            )

    for level_file, entry in entries:
        gaps = []
        for p in critical:
            got = level_row_values(p, entry, kind, mech_levels, levels_dir, obb_dir)
            if not got:
                gaps.append(p["name"])
        if gaps:
            per_level_missing[level_file] = gaps

    playable = bool(
        levels_anchor > 0
        and levels_anchor_nonempty > 0
        and not missing
        and all(params[p["name"]]["coverage"] > 0 for p in critical)
    )

    deps = []
    for dep in spec.get("dependsOn") or []:
        deps.append(dep)

    return {
        "levels": total,
        "levelsWithAnchor": levels_anchor,
        "levelsWithNonEmptyAnchor": levels_anchor_nonempty,
        "playable": playable,
        "anchorClasses": list(spec["anchors"]),
        "params": params,
        "missing": missing,
        "missingOptional": missing_optional,
        "levelsIncomplete": [
            {"level": level_file, "missing": per_level_missing[level_file]}
            for level_file in sorted(per_level_missing)
        ],
        "dependsOn": deps,
        "evidence": evidence,
        "notes": list(spec.get("notes") or []),
        "sentinels": sentinels,
    }


def absent_kinds(mini: Dict[str, Any]) -> List[Dict[str, Any]]:
    """minigames.json 已经记过「找不到独立模块」的 kind；这里转成可核对的条目。

    minigames.json 的 unknowns 用 ``type`` 区分（``kind-without-module`` 只 1 条 = chicken），
    这里只搬那一条，不把 content/模块名单对不齐的另外两类混进「证空」。
    """
    out: List[Dict[str, Any]] = []
    for unknown in mini.get("unknowns") or []:
        if str(unknown.get("type") or "") != "kind-without-module":
            continue
        kind = str(unknown.get("kind") or "")
        out.append(
            {
                "id": kind,
                "cn": str(unknown.get("cn") or ""),
                "levels": unknown.get("levels"),
                "whatItIs": str(unknown.get("whatItIs") or ""),
                "reason": str(unknown.get("reason") or ""),
                "evidence": "minigames.json#unknowns[type=kind-without-module, kind=%s]" % kind,
                "probe": "python tools/contentc/minigames.py -n chicken",
            }
        )
    return sorted(out, key=lambda row: row["id"])


def build(
    mini_path: Path = DEFAULT_MINI,
    mech_path: Path = DEFAULT_MECH,
    levels_dir: Path = DEFAULT_LEVELS,
    obb_dir: Path = DEFAULT_OBB,
) -> Dict[str, Any]:
    mini = load_json(mini_path)
    mech = load_json(mech_path)
    mech_levels = mech.get("levels") or {}
    levels = mini.get("levels") or {}

    grouped: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {kind: [] for kind in KIND_ORDER}
    for level_file in sorted(levels):
        entry = levels[level_file]
        for kind in entry.get("kinds") or []:
            if kind in grouped:
                grouped[kind].append((level_file, entry))

    kinds_out: Dict[str, Any] = {}
    for kind in KIND_ORDER:
        kinds_out[kind] = collect_kind(
            kind, SPECS[kind], grouped[kind], mech_levels, levels_dir, obb_dir
        )

    sentinels: List[Dict[str, Any]] = []
    for kind in KIND_ORDER:
        sentinels.extend(kinds_out[kind]["sentinels"])

    playable = sorted(k for k in KIND_ORDER if kinds_out[k]["playable"])
    blocked = sorted(k for k in KIND_ORDER if not kinds_out[k]["playable"])
    crit_total = sum(
        1 for k in KIND_ORDER for p in SPECS[k]["params"] if p["critical"]
    )
    crit_covered = sum(
        1
        for k in KIND_ORDER
        for name, row in kinds_out[k]["params"].items()
        if row["critical"] and row["coverage"] > 0
    )
    table: Dict[str, Any] = {
        "format": FORMAT,
        "generated": GENERATED,
        "sources": {
            "minigames": {
                "path": portable(mini_path),
                "bytes": Path(mini_path).stat().st_size,
                "sha256": sha256_of(mini_path),
            },
            "mechanics": {
                "path": portable(mech_path),
                "bytes": Path(mech_path).stat().st_size,
                "sha256": sha256_of(mech_path),
            },
            "levels": portable(levels_dir),
            "obb": portable(obb_dir),
        },
        "criteria": {
            "coverage": "coverage = 该 kind 的关卡里取到该字段的关数，分母 levels",
            "playable": (
                "playable = 锚点类存在 且 锚点至少一关非空 且 每个 critical 参数 coverage>0；"
                "参数对象是空 {} 的 kind 必然 false"
            ),
            "missing": "missing 只装 critical 且 coverage==0；critical 缺口必然让 playable=false",
            "missingOptional": "非 critical 的缺口，含原版根本没有的字段（reason 逐条写明）",
        },
        "counts": {
            "kinds": len(KIND_ORDER),
            "playable": len(playable),
            "notPlayable": len(blocked),
            "levels": len(levels),
            "levelsWithAnyKind": sum(1 for e in levels.values() if e.get("kinds")),
            "criticalParams": crit_total,
            "criticalParamsCovered": crit_covered,
            "absentKinds": len(absent_kinds(mini)),
            "sentinelRows": len(sentinels),
            "filesScanned": len(levels) + 1 + 1,
        },
        "playableKinds": playable,
        "blockedKinds": blocked,
        "kindOrder": list(KIND_ORDER),
        "absentKinds": absent_kinds(mini),
        "sentinels": sentinels,
        "kinds": kinds_out,
    }
    return table


# ----------------------------------------------------------------------- output


def render(table: Dict[str, Any]) -> str:
    return json.dumps(
        table, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) + "\n"


def dump(table: Dict[str, Any], path: Path = DEFAULT_OUT) -> None:
    # write_bytes：Windows 的 write_text 会把 \n 变成 \r\n，--check 会永远报过期。
    Path(path).write_bytes(render(table).encode("utf-8"))


def check(table: Dict[str, Any], path: Path = DEFAULT_OUT) -> int:
    problems: List[str] = []
    if table.get("format") != FORMAT:
        problems.append("format 不是 %s" % FORMAT)
    kinds = table.get("kinds") or {}
    if sorted(kinds) != sorted(KIND_ORDER):
        problems.append("kinds 与注册表不一致：%s" % sorted(set(kinds) ^ set(KIND_ORDER)))
    if table.get("kindOrder") != list(KIND_ORDER):
        problems.append("kindOrder 与注册表顺序不一致（JSON 按键排序，顺序只存在这一栏）")
    counts = table.get("counts") or {}
    if counts.get("kinds") != len(KIND_ORDER):
        problems.append("counts.kinds 与注册表不符")
    if counts.get("playable", 0) + counts.get("notPlayable", 0) != len(KIND_ORDER):
        problems.append("counts.playable + notPlayable != kinds")
    for kind, row in kinds.items():
        if not row.get("evidence"):
            problems.append("%s 没有 evidence" % kind)
        if not row.get("params"):
            problems.append("%s 没有 params" % kind)
        has_critical_gap = any(
            p["coverage"] == 0 for p in row["params"].values() if p["critical"]
        )
        if row["playable"] and has_critical_gap:
            problems.append("%s 判 playable 但有 critical 缺口" % kind)
        if not row["playable"] and not row.get("missing"):
            problems.append("%s 判不可玩却 missing 为空" % kind)
        if row["playable"] and row.get("missing"):
            problems.append("%s 判可玩却列了 missing" % kind)
        if row["levelsWithAnchor"] > row["levels"]:
            problems.append("%s 的 levelsWithAnchor 超过 levels" % kind)
        for param in row["params"].values():
            if param["coverage"] > row["levels"]:
                problems.append("%s 有参数 coverage 超过 levels" % kind)
    if not table.get("absentKinds"):
        problems.append("absentKinds 为空：证空记录必须留下")

    raw = render(table).encode("utf-8")
    if b"\r\n" in raw:
        problems.append("渲染结果含 CRLF")
    target = Path(path)
    if not target.exists():
        problems.append("%s 不存在，先运行 python tools/contentc/minigame_rules.py" % target)
    else:
        on_disk = target.read_bytes()
        if on_disk != raw:
            problems.append("%s 与重算结果不一致（产物过期）" % target)
    for problem in problems:
        print("FAIL: " + problem)
    if problems:
        return 1
    print(
        "minigame_rules kinds=%d playable=%d blocked=%d params=%d/%d absent=%d sentinels=%d"
        % (
            counts["kinds"],
            counts["playable"],
            counts["notPlayable"],
            counts["criticalParamsCovered"],
            counts["criticalParams"],
            counts["absentKinds"],
            counts["sentinelRows"],
        )
    )
    return 0


def needle_report(needle: str) -> int:
    """打印命中关键词的 kind / 参数 / 类名，方便复核某个断言。"""
    hit = 0
    low = needle.lower()
    for kind in KIND_ORDER:
        spec = SPECS[kind]
        for cls in spec["anchors"]:
            if low in cls.lower():
                print("%-16s anchor %s" % (kind, cls))
                hit += 1
        for param in spec["params"]:
            text = " ".join(
                str(param.get(key) or "") for key in ("name", "cls", "field", "alias", "path", "key")
            )
            if low in text.lower():
                print("%-16s param %-24s %s" % (kind, param["name"], param.get("via")))
                hit += 1
    print("%d hit(s) for %r" % (hit, needle))
    return 0 if hit else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mini", default=str(DEFAULT_MINI), help="minigames.json")
    parser.add_argument("--mech", default=str(DEFAULT_MECH), help="level_mechanics.json")
    parser.add_argument("--levels", default=str(DEFAULT_LEVELS), help="content/levels")
    parser.add_argument("--obb", default=str(DEFAULT_OBB), help="OBB package dump dir")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output json")
    parser.add_argument("--check", action="store_true", help="compare with the file on disk")
    parser.add_argument("-n", "--needle", default=None, help="print kinds/params matching a word")
    args = parser.parse_args(argv)

    if args.needle:
        return needle_report(args.needle)

    table = build(Path(args.mini), Path(args.mech), Path(args.levels), Path(args.obb))
    if args.check:
        return check(table, Path(args.out))
    dump(table, Path(args.out))
    counts = table["counts"]
    print(
        "wrote %s  kinds=%d playable=%d blocked=%d params=%d/%d"
        % (
            args.out,
            counts["kinds"],
            counts["playable"],
            counts["notPlayable"],
            counts["criticalParamsCovered"],
            counts["criticalParams"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
