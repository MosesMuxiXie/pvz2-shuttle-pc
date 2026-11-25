"""Compile the 460.9 minigame / variant-play data into one addressable table.

Sources (all read-only, `work/obb_packages` = the decoded 460.9 PACKAGES group):
  * `<pkg>_LevelDefinition.json` --每关的 `Modules[]`,是「这关挂什么玩法」的唯一真凭据。
  * content/levels/*.json     --客户端 level id 与 `extra.package` 的对应(身份来源,不提供玩法信息)。
  * 各 `*MinigameProperties` / `*ChallengeProperties` / `RailcartProperties` 等参数对象,
    它们是**关卡包内嵌**的,所以按包归属即可拿到该关的参数。

口径(R01..R09):
  R01 玩法 kind 只由 `Modules[]` 里的**模块别名**判定。参数对象存在但模块没挂(例如
      `BowlingMinigameProperties` 出现在 28 个包、`BowlingBulbMinigame` 只挂 15 关),
      不据此判 kind —— 否则会把普通关算成小游戏。
  R02 只有「锚点模块」(anchor)才创建 kind;同一玩法的辅助模块(related)只记录在
      `relatedModules`,不单独造 kind。例如 `JoustModule` 是锚点,`JoustZombieWinCondition`
      不是:有 2 关只挂了后者(plantagenet_22/23),算 joust 会把 4 关夸成 6 关。
  R03 `ChallengeModule`(星章挑战)不算小游戏,也不硬凑成 kind;它覆盖 924 关,只在
      `counts.excluded` 里登记,避免读者把「星章挑战」当玩法。
  R04 `params` 原样收录该关包里属于该 kind 的参数对象 objdata(键=objclass,值=对象列表),
      不做字段改名、不补默认值。
  R05 kind 分两类:`minigame`(自带模块、替换/改写整局规则)与 `variant`(在普通关之上
      叠一层规则)。分类写死在 KINDS 表里,不从字段猜。
  R06 客户端 level id 来自 content/levels 的 `extra.package`;映射不到 client id 的关卡包
      进 `unknowns`,不猜 id。
  R07 content 的 `extra.rail` / `extra.vasebreaker` / `extra.special` 只用于**交叉核对**,
      它们的差异写进 `crossChecks` 与 `unknowns`(content 侧与 pack 侧不一致时两边都留)。
  R08 找不到独立模块的玩法(ZombieChicken 等)写进 `unknowns` 并附「它到底是什么」,
      不用星章挑战或僵尸属性硬凑。
  R09 产物确定性:`GENERATED` 是固定日期、键全部 sort_keys、LF 换行、`--check` 逐字节比对。

Usage:
    python tools/contentc/minigames.py                 # 写 native/generated/minigames.json
    python tools/contentc/minigames.py --check         # 与磁盘逐字节比对(过期 exit 1)
    python tools/contentc/minigames.py -n chicken      # 打印命中某关键词的 objclass / 模块名
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from portable import portable  # noqa: E402
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEVELS = ROOT / "content" / "levels"
DEFAULT_OBB = Path(
    os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages")
)
DEFAULT_OUT = ROOT / "native" / "generated" / "minigames.json"

FORMAT = "pvz2-shuttle/minigames@1"
GENERATED = "2026-11-25"

RTID_RE = re.compile(r"RTID\(\s*([^@)\s]+)\s*@([^)\s]+)\s*\)")

# --- kind registry -----------------------------------------------------------
# anchor:   模块别名(任一命中即算该 kind)
# related:  只记录、不创建 kind 的同族模块
# params:   该 kind 的参数对象 objclass(原样收录)
# category: minigame | variant
KINDS = (
    {
        "id": "vasebreaker",
        "category": "minigame",
        "cn": "砸罐子",
        "anchor": ("VaseBreakerArcade", "VaseBreakerProps", "TestVaseBreaker"),
        "related": (),
        "params": ("VaseBreakerPresetProperties", "VaseBreakerEndlessProperties"),
        "evidence": "Modules 含 VaseBreakerArcade/VaseBreakerProps/TestVaseBreaker；参数为 VaseBreakerPresetProperties.Vases[]",
    },
    {
        "id": "rail",
        "category": "variant",
        "cn": "铁轨/矿车",
        "anchor": (
            "Rails", "Rail", "Railcart", "Railcart1", "MountingRails",
            "CowboyRails", "BeachRails", "EgyptRails", "FutureRails",
            "TutorialRails", "WorldcupRails",
        ),
        "related": (),
        "params": ("RailcartProperties",),
        "evidence": "Modules 含任一 *Rails/Railcart 别名；参数为 RailcartProperties.Railcarts[]/Rails[]",
    },
    {
        "id": "laststand",
        "category": "minigame",
        "cn": "Last Stand（背水一战）",
        "anchor": ("LastStand",),
        "related": ("LastStandSeedBank",),
        "params": ("LastStandMinigameProperties",),
        "evidence": "Modules 含 LastStand；参数为 LastStandMinigameProperties.StartingSun/StartingPlantfood",
    },
    {
        "id": "beghouled",
        "category": "minigame",
        "cn": "Beghouled（三消）",
        "anchor": ("BeghouledArcade", "BeghouledProps"),
        "related": ("BeghouledIntro", "BeghouledRiftIntro", "BeghouledSeedBank"),
        "params": (
            "BeghouledPresetProperties",
            "BeghouledZombieSpawnerProperties",
            "BeghouledSeedBankProperties",
        ),
        "evidence": "Modules 含 BeghouledArcade/BeghouledProps；参数为 BeghouledPresetProperties.MatchesToWin/UpgradeMap",
    },
    {
        "id": "whackazombie",
        "category": "minigame",
        "cn": "Whack-a-Zombie（打地鼠）",
        "anchor": ("WhackAZombieMinigame",),
        "related": ("WhackPuddles",),
        "params": ("MinigameWhackAZombieModuleProperties", "SpawnWhackAZombiesProps"),
        "evidence": "Modules 含 WhackAZombieMinigame；参数为 MinigameWhackAZombieModuleProperties.HammerHitValue",
    },
    {
        "id": "joust",
        "category": "minigame",
        "cn": "Joust（竞技场）",
        "anchor": ("JoustModule",),
        "related": ("JoustPointOfLoss", "JoustZombieWinCondition", "JoustDarkMowers"),
        "params": ("JoustGameModuleProperties",),
        "evidence": "Modules 含 JoustModule（锚点）；JoustPointOfLoss/WinCondition/DarkMowers 是辅助模块",
    },
    {
        "id": "bowling",
        "category": "minigame",
        "cn": "Bowling（保龄球）",
        "anchor": ("BowlingBulbMinigame",),
        "related": (),
        "params": ("BowlingMinigameProperties",),
        "evidence": "Modules 含 BowlingBulbMinigame；参数为 BowlingMinigameProperties.BowlingFoulLine",
    },
    {
        "id": "column",
        "category": "minigame",
        "cn": "Column（列攻）",
        "anchor": ("ColumnMinigame",),
        "related": ("Column",),
        "params": ("ColumnMinigameProperties",),
        "evidence": "Modules 含 ColumnMinigame；参数对象 ColumnMinigameProperties 全为空 {}",
    },
    {
        "id": "cannon",
        "category": "minigame",
        "cn": "Cannon（炮击）",
        "anchor": ("CannonMinigame",),
        "related": ("PirateCannonTutorial",),
        "params": ("CannonMinigameProperties",),
        "evidence": "Modules 含 CannonMinigame；参数为 CannonMinigameProperties.Lanes/ComboBrackets",
    },
    {
        "id": "invisighoul",
        "category": "minigame",
        "cn": "Invisighoul（隐形僵尸）",
        "anchor": ("InvisighoulMinigame",),
        "related": ("InvisibleBrainEater",),
        "params": ("InvisighoulMinigameProperties",),
        "evidence": "Modules 含 InvisighoulMinigame；参数对象 InvisighoulMinigameProperties 全为空 {}",
    },
    {
        "id": "cowboy",
        "category": "minigame",
        "cn": "Cowboy（西部小游戏）",
        "anchor": ("CowboyMinigame",),
        "related": ("CowboyConveyor",),
        "params": ("CowboyMinigameProperties",),
        "evidence": "Modules 含 CowboyMinigame；参数为 CowboyMinigameProperties.BeginString/ShowTutorial",
    },
    {
        "id": "bigtrouble",
        "category": "minigame",
        "cn": "Big Trouble Little Zombie（缩小僵尸）",
        "anchor": ("BigTroubleLittleZombieMinigameModule",),
        "related": (),
        "params": ("BigTroubleLittleZombieMinigameProperties",),
        "evidence": "Modules 含 BigTroubleLittleZombieMinigameModule；参数为 ZombieScale/ZombieIncomingDamageScale",
    },
    {
        "id": "camel",
        "category": "minigame",
        "cn": "Camel（骆驼牌）",
        "anchor": ("CamelMinigame",),
        "related": (),
        "params": ("CamelMinigameProperties",),
        "evidence": "Modules 含 CamelMinigame；参数为 CardTypesUsed/CardMatchingTime",
    },
    {
        "id": "deathexplosion",
        "category": "minigame",
        "cn": "Death Explosion（死亡爆炸）",
        "anchor": ("DeathExplosionMiniGameModule",),
        "related": (),
        "params": ("DeathExplosionMiniGameModuleProperties",),
        "evidence": "Modules 含 DeathExplosionMiniGameModule；参数为 ExplodeDamageForZombies/HurtZombies",
    },
    {
        "id": "sproutplanting",
        "category": "minigame",
        "cn": "Sprout Planting（种苗）",
        "anchor": ("SproutPlanting",),
        "related": (),
        "params": ("SproutPlantingMinigameProperties",),
        "evidence": "Modules 含 SproutPlanting；参数为 StartingSproutCount/TimeToPlantAllSprouts/PlantWeights",
    },
    {
        "id": "seeingstars",
        "category": "minigame",
        "cn": "Seeing Stars（踩星）",
        "anchor": ("SeeingStarsModule",),
        "related": (),
        "params": ("SeeingStarsModuleProperties",),
        "evidence": "Modules 含 SeeingStarsModule；参数为 TargetPositions[]/PlantTypeName",
    },
    {
        "id": "bonuschallenge",
        "category": "minigame",
        "cn": "Bonus Challenge（奖励挑战）",
        "anchor": ("BonusChallengeModule",),
        "related": (),
        "params": ("BonusChallengeModuleProperties",),
        "evidence": "Modules 含 BonusChallengeModule；参数为 Challenges[]/ChallengesAlwaysAvailable",
    },
    {
        "id": "conveyor",
        "category": "variant",
        "cn": "传送带出牌",
        "anchor": ("ConveyorBelt",),
        "related": ("Conveyor", "CowboyConveyor"),
        "params": ("ConveyorSeedBankProperties",),
        "evidence": "Modules 含 ConveyorBelt；参数为 ConveyorSeedBankProperties（加权卡池）",
    },
    {
        "id": "tide",
        "category": "variant",
        "cn": "潮汐",
        "anchor": ("Tide",),
        "related": (),
        "params": ("TideProperties",),
        "evidence": "Modules 含 Tide；参数为 TideProperties.StartingWaveLocation",
    },
    {
        "id": "protecttheplant",
        "category": "variant",
        "cn": "保护植物",
        "anchor": ("ProtectThePlant",),
        "related": ("ProtectThePlant1", "ProtectPeanutLevelBasicModule"),
        "params": ("ProtectThePlantChallengeProperties",),
        "evidence": "Modules 含 ProtectThePlant；参数为 MustProtectCount/Plants[]",
    },
)

# 已知但**不算** kind 的模块：星章挑战覆盖 924 关，是关卡目标系统而非玩法。
EXCLUDED_MODULES = {
    "ChallengeModule": "star-challenge objective layer (924 levels) — not a minigame/variant mode",
    "PlantagenetMiniGameMusic": "music-enable module only (no gameplay rule)",
    "RenaiMiniGameMusic": "music-enable module only (no gameplay rule)",
    "SteamMiniGameMusic": "music-enable module only (no gameplay rule)",
}

# 已知玩法但原版没有独立模块的，直接写在 unknowns 里（附证据）。
MISSING_KINDS = (
    {
        "kind": "chicken",
        "cn": "ZombieChicken（僵尸鸡）",
        "reason": "2116 个包里没有任何 Modules 别名含 Chicken；只有僵尸属性对象",
        "whatItIs": "ZombieChickenProps(pkg_2112 ZombiePropertySheet) + ZombieChickenFarmerProps(14 对象/8 包)",
        "levels": 0,
    },
)

PARAM_CLASSES = tuple(
    sorted({cls for kind in KINDS for cls in kind["params"]})
)
ANCHOR_TO_KIND = {}
RELATED_TO_KIND = {}
for _kind in KINDS:
    for _alias in _kind["anchor"]:
        ANCHOR_TO_KIND[_alias] = _kind["id"]
    for _alias in _kind["related"]:
        RELATED_TO_KIND[_alias] = _kind["id"]
KIND_BY_ID = {kind["id"]: kind for kind in KINDS}
KIND_ORDER = tuple(kind["id"] for kind in KINDS)

KEYWORD_RE = re.compile(
    r"minigame|joust|beghouled|whack|vase|rail|camel|cannon|column|invisig|bowling|"
    r"laststand|deathexplosion|bigtrouble|sproutplanting|seeingstars|bonuschallenge|"
    r"chicken|conveyor|tide|protect",
    re.IGNORECASE,
)


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def iter_objects(doc):
    for obj in (doc or {}).get("objects") or []:
        if isinstance(obj, dict) and isinstance(obj.get("objdata"), dict):
            yield obj


def rtid_name(text):
    if not isinstance(text, str):
        return None
    hit = RTID_RE.search(text)
    return hit.group(1) if hit else text


def package_stem(name):
    """'pkg_0290' 与 'pkg_0290_LevelDefinition.json' 都归一到 'pkg_0290'。"""
    if not name:
        return None
    return str(name).split(".")[0].split("_LevelDefinition")[0]


def level_index(levels_dir: Path):
    """client level id -> {id, package, file, extra 子集}"""
    index = {}
    for path in sorted(Path(levels_dir).glob("*.json")):
        doc = load_json(path)
        extra = doc.get("extra") or {}
        pkg = package_stem(extra.get("package"))
        if not doc.get("id") or not pkg:
            continue
        index[pkg] = {
            "id": doc.get("id"),
            "file": path.stem,
            "rail": bool(extra.get("rail")),
            "vasebreaker": bool(extra.get("vasebreaker")),
            "special": sorted(str(x) for x in (extra.get("special") or [])),
            "minecarts": len(extra.get("minecarts") or []),
        }
    return index


def scan_levels(obb_dir: Path):
    """逐关收集 Modules 与参数对象(只收 KINDS 表声明过的 objclass)。"""
    scanned = {}
    for path in sorted(Path(obb_dir).glob("pkg_*_LevelDefinition.json")):
        doc = load_json(path)
        pkg = package_stem(path.name)
        modules = []
        params = {}
        for obj in iter_objects(doc):
            cls = obj.get("objclass") or ""
            if cls == "LevelDefinition" and not modules:
                for ref in obj["objdata"].get("Modules") or []:
                    name = rtid_name(ref)
                    if name:
                        modules.append(name)
            elif cls in PARAM_CLASSES:
                params.setdefault(cls, []).append(obj["objdata"])
        scanned[pkg] = {"modules": modules, "params": params}
    return scanned


def classify(modules):
    """-> (kinds, relatedHits)  kinds 是 anchor 命中的 kind id 列表。"""
    kinds = set()
    related = set()
    for name in modules:
        kind = ANCHOR_TO_KIND.get(name)
        if kind:
            kinds.add(kind)
            continue
        kind = RELATED_TO_KIND.get(name)
        if kind:
            related.add(kind)
    return sorted(kinds, key=KIND_ORDER.index), sorted(related, key=KIND_ORDER.index)


def kind_params(kind_id, params):
    wanted = KIND_BY_ID[kind_id]["params"]
    out = {}
    for cls in wanted:
        rows = params.get(cls)
        if rows:
            out[cls] = rows
    return out


def build(obb_dir: Path, levels_dir: Path):
    index = level_index(levels_dir)
    scanned = scan_levels(obb_dir)

    levels = {}
    unmatched = []
    unregistered = Counter()
    seen_modules = Counter()

    for pkg, info in sorted(scanned.items()):
        modules = info["modules"]
        for name in modules:
            seen_modules[name] += 1
        kinds, related = classify(modules)
        # 关键词命中但没进注册表的模块：不静默丢弃
        for name in modules:
            if name in ANCHOR_TO_KIND or name in RELATED_TO_KIND or name in EXCLUDED_MODULES:
                continue
            if KEYWORD_RE.search(name):
                unregistered[name] += 1
        if not kinds:
            continue
        params = {kind_id: kind_params(kind_id, info["params"]) for kind_id in kinds}
        params = {k: v for k, v in params.items() if v}
        row = {
            "package": pkg,
            "kinds": kinds,
            "categories": sorted({KIND_BY_ID[k]["category"] for k in kinds}),
            "modules": modules,
            "relatedModules": related,
            "params": params,
        }
        level = index.get(pkg)
        if level is None:
            unmatched.append({"package": pkg, "kinds": kinds})
            continue
        row["levelFile"] = level["file"]
        row["extra"] = {
            "rail": level["rail"],
            "vasebreaker": level["vasebreaker"],
            "special": level["special"],
            "minecarts": level["minecarts"],
        }
        levels[level["id"]] = row

    # --- cross checks against content/levels -------------------------------
    content_rail = {v["id"] for v in index.values() if v["rail"]}
    content_vb = {v["id"] for v in index.values() if v["vasebreaker"]}
    content_special = {v["id"] for v in index.values() if "IsVasebreaker" in v["special"]}
    pack_rail = {lid for lid, row in levels.items() if "rail" in row["kinds"]}
    pack_vb = {lid for lid, row in levels.items() if "vasebreaker" in row["kinds"]}
    cross = {
        "rail": {
            "packLevels": len(pack_rail),
            "contentLevels": len(content_rail),
            "agree": len(pack_rail & content_rail),
            "packOnly": sorted(pack_rail - content_rail),
            "contentOnly": sorted(content_rail - pack_rail),
        },
        "vasebreaker": {
            "packLevels": len(pack_vb),
            "contentLevels": len(content_vb),
            "agree": len(pack_vb & content_vb),
            "packOnly": sorted(pack_vb - content_vb),
            "contentOnly": sorted(content_vb - pack_vb),
        },
        "special": {
            "contentLevels": len(content_special),
            "values": sorted({s for v in index.values() for s in v["special"]}),
            "allCoveredByVasebreakerKind": sorted(content_special - pack_vb) == [],
            "notCovered": sorted(content_special - pack_vb),
        },
    }

    by_kind = Counter()
    by_category = Counter()
    for row in levels.values():
        for kind_id in row["kinds"]:
            by_kind[kind_id] += 1
        for cat in row["categories"]:
            by_category[cat] += 1

    unknown_rows = []
    for entry in MISSING_KINDS:
        unknown_rows.append({**entry, "type": "kind-without-module"})
    if unregistered:
        unknown_rows.append(
            {
                "type": "unregistered-module",
                "reason": "别名命中玩法关键词但不在 KINDS 注册表里,未参与分类",
                "modules": [
                    {"alias": name, "levels": n} for name, n in sorted(unregistered.items())
                ],
            }
        )
    if unmatched:
        unknown_rows.append(
            {
                "type": "level-without-client-id",
                "reason": "关卡包挂了玩法模块,但 content/levels 里没有 extra.package 指向它",
                "packages": sorted(unmatched, key=lambda r: r["package"]),
            }
        )
    if cross["rail"]["contentOnly"]:
        unknown_rows.append(
            {
                "type": "content-rail-without-module",
                "reason": "content 标了 extra.rail=true,但包内 Modules 没有 *Rails/Railcart 别名",
                "levels": cross["rail"]["contentOnly"],
            }
        )
    if cross["rail"]["packOnly"]:
        unknown_rows.append(
            {
                "type": "rail-module-without-content-rail",
                "reason": "包内挂了铁轨模块,但 content 没标 extra.rail(通常是 Rails 但无 minecarts)",
                "levels": cross["rail"]["packOnly"],
            }
        )

    counts = {
        "levels": len(levels),
        "levelsScanned": len(scanned),
        "levelsWithAnyKind": len(levels),
        "byKind": {kind_id: by_kind.get(kind_id, 0) for kind_id in KIND_ORDER},
        "byCategory": {
            "minigame": by_category.get("minigame", 0),
            "variant": by_category.get("variant", 0),
        },
        "minigameLevels": sum(
            1 for row in levels.values() if "minigame" in row["categories"]
        ),
        "variantLevels": sum(
            1 for row in levels.values() if "variant" in row["categories"]
        ),
        "kinds": len(KINDS),
        "paramClasses": len(PARAM_CLASSES),
        "excluded": {name: {"levels": seen_modules.get(name, 0), "why": why} for name, why in EXCLUDED_MODULES.items()},
    }

    return {
        "format": FORMAT,
        "generated": GENERATED,
        "levels": {lid: levels[lid] for lid in sorted(levels)},
        "counts": counts,
        "crossChecks": cross,
        "unknowns": unknown_rows,
        "sources": {
            "obb": portable(obb_dir),
            "levels": portable(levels_dir),
            "moduleEvidence": "LevelDefinition.Modules[] (pack) — 唯一玩法凭据",
            "idEvidence": "content/levels/*.json extra.package → id",
            "paramEvidence": "关卡包内嵌的 *MinigameProperties / *ChallengeProperties / RailcartProperties",
        },
    }


def render(table):
    return json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def dump(table, path: Path):
    # 用 write_bytes 固定 LF：Windows 的 write_text 会把 \n 变成 \r\n，破坏逐字节比对。
    Path(path).write_bytes(render(table).encode("utf-8"))


def check(table, path: Path):
    problems = []
    if table.get("format") != FORMAT:
        problems.append(f"format!= {FORMAT}")
    if table.get("generated") != GENERATED:
        problems.append(f"generated!= {GENERATED}")
    counts = table.get("counts") or {}
    levels = table.get("levels") or {}
    if counts.get("levels") != len(levels):
        problems.append(f"counts.levels {counts.get('levels')} != len(levels) {len(levels)}")
    recomputed = Counter()
    for row in levels.values():
        for kind_id in row.get("kinds") or []:
            recomputed[kind_id] += 1
    for kind_id in KIND_ORDER:
        want = (counts.get("byKind") or {}).get(kind_id)
        if want != recomputed.get(kind_id, 0):
            problems.append(f"byKind[{kind_id}] {want} != {recomputed.get(kind_id, 0)}")
    if list(levels) != sorted(levels):
        problems.append("levels keys are not sorted")
    for lid, row in levels.items():
        if not row.get("package") or not row.get("kinds"):
            problems.append(f"{lid}: package/kinds missing")
        # kinds 按注册表顺序（KIND_ORDER）排列，不是字母序：校验用的是同一个不变式。
        if sorted(row.get("kinds"), key=KIND_ORDER.index) != row.get("kinds"):
            problems.append(f"{lid}: kinds not in registry order")
    target = Path(path)
    if not target.exists():
        problems.append(f"{target} missing")
    else:
        disk = target.read_bytes()
        if b"\r\n" in disk:
            problems.append("file contains CRLF")
        if not disk.endswith(b"\n"):
            problems.append("file does not end with LF")
        if disk != render(table).encode("utf-8"):
            problems.append("file is stale (bytes != fresh render)")
    if problems:
        print("minigames --check FAILED")
        for line in problems:
            print("  -", line)
        return 1
    by_kind = counts.get("byKind") or {}
    print(
        "minigames levels={} minigame={} variant={} kinds={}".format(
            counts.get("levels"),
            counts.get("minigameLevels"),
            counts.get("variantLevels"),
            counts.get("kinds"),
        )
    )
    print("           byKind: " + " ".join(f"{k}={v}" for k, v in by_kind.items() if v))
    print("OK")
    return 0


def needle_report(obb_dir: Path, needle: str):
    pattern = re.compile(re.escape(needle), re.IGNORECASE)
    hits = Counter()
    for path in sorted(Path(obb_dir).glob("pkg_*.json")):
        doc = load_json(path)
        for obj in iter_objects(doc):
            cls = obj.get("objclass") or ""
            if pattern.search(cls):
                hits[f"objclass {cls}"] += 1
        if pattern.search(path.name):
            hits[f"file {path.name}"] += 1
    print(f"needle {needle!r}: {sum(hits.values())} hits")
    for key, n in sorted(hits.items()):
        print(f"{n:5d}  {key}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB)
    parser.add_argument("--levels", type=Path, default=DEFAULT_LEVELS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="与磁盘逐字节比对")
    parser.add_argument("-n", "--needle", help="只打印命中关键词的 objclass/文件名")
    args = parser.parse_args(argv)

    if args.needle:
        return needle_report(args.obb, args.needle)

    table = build(args.obb, args.levels)
    if args.check:
        return check(table, args.out)
    dump(table, args.out)
    print(f"wrote {args.out} ({Path(args.out).stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
