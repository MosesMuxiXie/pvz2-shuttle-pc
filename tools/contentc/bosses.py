"""Compile the original boss tables into one engine-readable file.

What the packs actually contain (proven in `docs/reviews/2026-11-20-s5-data-inventory.md`,
section 3, and re-read here field by field):

* `ZombieType` rows (`pkg_2115_ZombieType.json`) - one row per zombie type. For a
  boss the row carries `TypeName` (e.g. `zombossmech_egypt`), `ZombieClass`,
  `Properties = RTID(<props>@ZombieProperties)`, `PopAnim`, `AnimRigClass`.
  This is the *only* link from a level's boss module to its stage table.
* `ZombossBattleModuleProperties` / `ZombossRiftBattleModuleProperties` - one row
  per boss level, living inside that level's own `LevelDefinition` package. It
  names the mech (`ZombossMechType`, which is a `ZombieType.TypeName`), the
  reserved columns, the spawn grid position and the death row/column.
* `Zombie*Zomboss*Mech*Props` objects (`pkg_2112_ZombiePropertySheet.json` or a
  level package for per-level variants) - `Stages[]`, and each stage carries
  `HitPoints`, `IdleTime`, `StunTime`, `AnimRateModifier`, `DamageIndex*`,
  `RetreatAction` and `Actions[]` (RTIDs into `@ZombieActions`).
* `*ActionDefinition` objects - the actual attack/summon payloads, e.g.
  `ZombossFireActionDefinition` with `FireMinColumn`/`FireMaxColumn`/
  `FireRowRange`/`FireRocketSpeed`/`FireRocketHitTime`.

Which values below are the pack's own and which are inferred
------------------------------------------------------------------
PACK ORIGINAL (copied verbatim, never normalised):
  `id` (the `ZombieType.TypeName` string as written), `className`
  (`ZombieClass`), `propsName` / `propsSheet` (from the `Properties` RTID),
  `popAnim`, `animRig`, `stages[].hitPoints`, `stages[].idleSeconds`
  (`IdleTime.Min`/`Max`), `stages[].stunSeconds` (`StunTime`),
  `stages[].animRate` (`AnimRateModifier`), `stages[].damageIndex`
  (`DamageIndexFull`/`DamageIndexHalf`), `stages[].retreatAction`,
  `stages[].actions[].rtid` / `.type` / `.fields` (the action object's objclass
  and its entire objdata), `spawn.reservedColumns`, `spawn.gridX`/`gridY`,
  `spawn.deathRow`/`deathColumn`, `spawn.module`, `spawn.moduleObjclass`,
  `spawn.stageModule`, `stageSelection` (`ZombossStageCount` /
  `ZombossStartStageIndex` when present).

INFERRED (spelled out so each row can be re-checked by hand):
  `world` - the packs never store a world id on a level; it is inferred from the
  level's `StageModule` alias by name prefix (`s5scan.STAGE_WORLD_HINTS`), and
  unmatched stages are kept verbatim as `unknown:<stage>` instead of dropped.
  `spawn` (the primary placement) - the same mech can be placed by several
  levels; the primary is the placement whose stage name contains `boss`, ties
  broken by package name. Every placement is still listed in `placements`, so
  nothing is hidden by this choice.
  `worlds` - the sorted set of worlds across all placements; a mech reused by
  two worlds (e.g. `zombossmech_added_beach` inside ChineseGarden) shows up there
  and is listed in the report as a cross-world reuse.
  `resolution` - `zombietype` when the mech was found in `pkg_2115_ZombieType`,
  `alias-guess` when the pack had no `ZombieType` row and the props object was
  found by guessing `Zombie`+CamelCase (`MissingMechanicCount` stays visible).

Deliberately NOT used: `content/bosses.json` (its HP is a synthetic 8000+200n
ladder and its three phases are identical in all 26 rows) and
`docs/reviews/2026-11-20-s5-data-inventory.md`'s counts are only cited, never
re-derived into numbers.

Usage:
    python tools/contentc/bosses.py                 # write json + report
    python tools/contentc/bosses.py --check         # validate the shipped file
    python tools/contentc/bosses.py --dump          # print the compiled json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from contentc import s5scan  # noqa: E402
from contentc import worlds  # noqa: E402

REPO = worlds.REPO
DEFAULT_OBB = worlds.DEFAULT_OBB
DEFAULT_OUT = REPO / "native" / "generated" / "bosses_from_pack.json"
DEFAULT_REPORT = REPO / "native" / "generated" / "boss_report.md"
DEFAULT_CLIENT = worlds.DEFAULT_CONTENT / "bosses.json"

FORMAT = 1
GENERATED = "boss-compile-v1"

# `ZombossSpawn1` -> class `ZombossSpawnActionDefinition`; the suffix is stable
# across all 38 arm classes, so one regex covers every payload.
ACTION_CLASS_RE = re.compile(r"ActionDefinition$")

# The sheets a boss module can point its `Properties` RTID at. `ZombieProperties`
# is the shared sheet (`pkg_2112_ZombiePropertySheet`); `CurrentLevel` means the
# object was inlined into the level package that references it.
SHARED_PROP_SHEET = "ZombieProperties"
SHARED_PROP_PKG = "pkg_2112_ZombiePropertySheet"

# Worlds that exist in `content/worlds.json` - used only to report which of them
# have no boss data at all.
CLIENT_WORLDS = (
    "frontyard",
    "egypt",
    "pirate",
    "cowboy",
    "future",
    "dark",
    "beach",
    "lostcity",
    "iceage",
    "kongfu",
    "dino",
    "eighties",
    "modern",
    "sky",
    "chinesegarden",
    "heian",
    "fairy",
    "mausoleum",
    "steam",
    "memorytour",
    "losantosvice",
    "lunarrainbowmarket",
    "renai",
    "muji",
    "carnival",
    "plantagenet",
)


def rtid_parts(value: object) -> tuple[str, str]:
    """Split `RTID(Name@Sheet)` into `(Name, Sheet)`; missing pieces are ""."""

    text = str(value or "")
    match = re.search(r"RTID\(\s*([^@)\s]+)\s*@\s*([^)\s]+)\s*\)", text)
    if not match:
        return ("", "")
    return (match.group(1), match.group(2))


def camelize(type_name: str) -> str:
    """`zombossmech_egypt_rift` -> `ZombieZombossMechEgyptRift` (fallback only)."""

    parts = [part for part in re.split(r"[_\s]+", type_name) if part]
    return "Zombie" + "".join(part[:1].upper() + part[1:] for part in parts)


def alias_of(obj: dict) -> str:
    alias = obj.get("aliases")
    if isinstance(alias, list):
        return str(alias[0]) if alias else ""
    return str(alias or "")


def index_packages(obb_dir: Path) -> dict:
    """Read every package once and keep only the four tables this compiler needs.

    Candidates are collected per alias instead of per name, because the same
    alias can be redefined inside a level package (`@CurrentLevel`) - the
    resolver below then prefers the sheet the RTID asked for.
    """

    modules: list[dict] = []
    props: dict[str, list[dict]] = {}
    types: dict[str, dict] = {}
    actions: dict[str, list[dict]] = {}
    files = 0
    for path in s5scan.package_paths(obb_dir):
        files += 1
        doc = s5scan.load_package(path)
        if doc is None:
            continue
        objects = [obj for obj in doc.get("objects") or [] if isinstance(obj, dict)]
        level_stages = [
            s5scan.rtid_name((obj.get("objdata") or {}).get("StageModule"))
            for obj in objects
            if str(obj.get("objclass") or "").endswith("LevelDefinition")
            and isinstance(obj.get("objdata"), dict)
        ]
        stage_module = next((name for name in level_stages if name), "")
        for obj in objects:
            objclass = str(obj.get("objclass") or "")
            data = obj.get("objdata")
            data = data if isinstance(data, dict) else {}
            alias = alias_of(obj)
            if objclass in ("ZombossBattleModuleProperties", "ZombossRiftBattleModuleProperties"):
                modules.append(
                    {
                        "package": path.stem,
                        "objclass": objclass,
                        "alias": alias,
                        "data": data,
                        "stageModule": stage_module,
                        "world": s5scan.world_from_stage(stage_module),
                    }
                )
                continue
            if s5scan.ZOMBOSS_MECH_RE.search(objclass):
                props.setdefault(alias, []).append(
                    {"package": path.stem, "objclass": objclass, "data": data}
                )
                continue
            if objclass == "ZombieType":
                type_name = str(data.get("TypeName") or alias)
                types.setdefault(
                    type_name,
                    {
                        "package": path.stem,
                        "data": data,
                        "alias": alias,
                    },
                )
                continue
            if ACTION_CLASS_RE.search(objclass):
                actions.setdefault(alias, []).append(
                    {"package": path.stem, "objclass": objclass, "data": data}
                )
    return {
        "files": files,
        "modules": modules,
        "props": props,
        "types": types,
        "actions": actions,
    }


def pick_props(
    index: dict, name: str, sheet: str, near_package: str
) -> dict | None:
    """Resolve a mech props alias to one object, honouring the RTID's sheet.

    `@ZombieProperties` must come from the shared zombie sheet; `@CurrentLevel`
    must come from the level package that referenced it. Falling back to any
    candidate keeps a mis-sheeted reference visible instead of silently empty.
    """

    candidates = index["props"].get(name) or []
    if not candidates:
        return None
    if sheet == SHARED_PROP_SHEET:
        for candidate in candidates:
            if candidate["package"] == SHARED_PROP_PKG:
                return candidate
    else:
        for candidate in candidates:
            if candidate["package"] == near_package:
                return candidate
    return candidates[0]


def compile_action(index: dict, ref: object, near_package: str) -> dict:
    """One `Actions[]` entry: pack class + pack objdata, plus its raw RTID."""

    rtid = str(ref or "")
    alias = s5scan.rtid_name(rtid)
    candidates = index["actions"].get(alias) or []
    chosen = None
    for candidate in candidates:
        if candidate["package"] == near_package:
            chosen = candidate
            break
    if chosen is None:
        for candidate in candidates:
            if candidate["package"] == "pkg_2111_ZombieWalkActionDefinition":
                chosen = candidate
                break
    if chosen is None and candidates:
        chosen = candidates[0]
    if chosen is None:
        return {"rtid": rtid, "alias": alias, "type": None, "fields": {}, "pkg": None, "missing": True}
    return {
        "rtid": rtid,
        "alias": alias,
        "type": chosen["objclass"],
        "fields": chosen["data"],
        "pkg": chosen["package"],
    }


def compile_stage(index: dict, stage: dict, position: int, near_package: str) -> dict:
    idle = stage.get("IdleTime") if isinstance(stage.get("IdleTime"), dict) else {}
    return {
        "index": position,
        "hitPoints": stage.get("HitPoints"),
        "idleSeconds": {"min": idle.get("Min"), "max": idle.get("Max")},
        "stunSeconds": stage.get("StunTime"),
        "animRate": stage.get("AnimRateModifier"),
        "damageIndex": {
            "full": stage.get("DamageIndexFull"),
            "half": stage.get("DamageIndexHalf"),
        },
        "retreatAction": s5scan.rtid_name(stage.get("RetreatAction")) or None,
        "actions": [
            compile_action(index, ref, near_package) for ref in stage.get("Actions") or []
        ],
    }


def placement_of(module: dict) -> dict:
    data = module["data"]
    spawn = data.get("ZombossSpawnGridPosition")
    spawn = spawn if isinstance(spawn, dict) else {}
    return {
        "module": module["package"],
        "moduleObjclass": module["objclass"],
        "stageModule": module["stageModule"],
        "world": module["world"],
        "reservedColumns": data.get("ReservedColumnCount"),
        "gridX": spawn.get("mX"),
        "gridY": spawn.get("mY"),
        "deathRow": data.get("ZombossDeathRow"),
        "deathColumn": data.get("ZombossDeathColumn"),
        "stageSelection": {
            "count": data.get("ZombossStageCount"),
            "startIndex": data.get("ZombossStartStageIndex"),
        },
    }


def primary_placement(placements: list[dict]) -> dict:
    """The placement an engine should default to.

    Inferred rule (documented in the report), applied in this order:
      1. drop `unknown:*` worlds when a placement with a known world exists -
         otherwise a mech reused by a `ChildStage` would look worldless even
         though its real levels are known;
      2. prefer a stage whose alias says `boss` (the dedicated boss level);
      3. otherwise the first package name in sorted order.
    All placements remain in `placements`, so this is a display choice, not a
    data reduction.
    """

    def rank(placement: dict) -> tuple[int, int, str]:
        world = str(placement.get("world") or "")
        stage = str(placement.get("stageModule") or "").lower()
        return (
            1 if world.startswith("unknown") else 0,
            0 if "boss" in stage else 1,
            placement["module"],
        )

    return sorted(placements, key=rank)[0]


def unplaced_mechs(index: dict, placed: set[str]) -> list[dict]:
    """Mech types that own a stage table but are placed by no battle module.

    These are the Battlez/Rift variants (`zombossmech_*_battlez`,
    `zombossmech_*_rift`, `zombossmech_dino2`…). They are real pack data, but
    nothing in this pack tree puts them on a lawn, so they have no spawn and are
    not part of the default compile - they are listed here so the omission is
    visible instead of silent.
    """

    reverse: dict[str, str] = {}
    for type_name, row in index["types"].items():
        props_name, _ = rtid_parts(row["data"].get("Properties"))
        if props_name:
            reverse.setdefault(props_name, type_name)
    rows = []
    for alias, candidates in sorted(index["props"].items()):
        with_stages = [candidate for candidate in candidates if candidate["data"].get("Stages")]
        if not with_stages:
            continue
        type_name = reverse.get(alias)
        if not type_name or type_name in placed:
            continue
        rows.append(
            {
                "id": type_name,
                "propsName": alias,
                "propsPkg": with_stages[0]["package"],
                "stageCount": max(len(candidate["data"]["Stages"]) for candidate in with_stages),
            }
        )
    rows.sort(key=lambda row: row["id"])
    return rows


def compile_boss(index: dict, type_name: str, mech_types: dict, placements: list[dict]) -> dict:
    row = mech_types.get(type_name)
    resolution = "zombietype"
    props_name = ""
    props_sheet = ""
    class_name = ""
    pop_anim = ""
    anim_rig = ""
    display_name = ""
    if row:
        data = row["data"]
        class_name = str(data.get("ZombieClass") or "")
        props_name, props_sheet = rtid_parts(data.get("Properties"))
        pop_anim = str(data.get("PopAnim") or "")
        anim_rig = str(data.get("AnimRigClass") or "")
        display_name = str(data.get("DisplayTypeName") or "")
    else:
        resolution = "alias-guess"
        props_name = camelize(type_name)
        props_sheet = SHARED_PROP_SHEET

    ordered = sorted(placements, key=lambda item: (item["module"], item["moduleObjclass"]))
    primary = primary_placement(ordered)
    near = primary["module"]
    props = pick_props(index, props_name, props_sheet, near)
    stages: list[dict] = []
    if props:
        raw_stages = [stage for stage in props["data"].get("Stages") or [] if isinstance(stage, dict)]
        stages = [
            compile_stage(index, stage, position, props["package"])
            for position, stage in enumerate(raw_stages)
        ]
    return {
        "id": type_name,
        "className": class_name,
        "displayTypeName": display_name,
        "propsName": props_name,
        "propsSheet": props_sheet,
        "propsPkg": props["package"] if props else None,
        "missingProps": props is None,
        "popAnim": pop_anim,
        "animRig": anim_rig,
        "world": primary["world"],
        "worlds": sorted({placement["world"] for placement in ordered}),
        "worldSource": "stage-prefix-inference",
        "resolution": resolution,
        "stageCount": len(stages),
        "stages": stages,
        "spawn": {
            key: value for key, value in primary.items() if key not in ("world",)
        },
        "placements": ordered,
        "source": "pack",
        "modulePkg": primary["module"],
    }


def compile_bosses(obb_dir: Path = DEFAULT_OBB) -> dict:
    """Build the whole table; deterministic for a given pack tree."""

    index = index_packages(obb_dir)
    by_mech: dict[str, list[dict]] = {}
    for module in index["modules"]:
        mech = str(module["data"].get("ZombossMechType") or "")
        if not mech:
            continue
        by_mech.setdefault(mech, []).append(placement_of(module))

    bosses = [
        compile_boss(index, mech, index["types"], placements)
        for mech, placements in sorted(by_mech.items())
    ]
    bosses.sort(key=lambda boss: boss["id"])

    stage_total = sum(boss["stageCount"] for boss in bosses)
    # Three different stage totals exist in this pack tree; only the first is
    # what an engine can actually reach, so all three are reported together:
    #   placed          - stages of the 50 mechs that a battle module puts on a lawn
    #   distinctProps   - stages after de-duplicating props aliases redefined in
    #                     several level packages (`@CurrentLevel` variants)
    #   occurrences     - stages summed over every object occurrence; this is the
    #                     258 quoted in docs/reviews/2026-11-20-s5-data-inventory.md
    distinct_props_total = 0
    occurrence_total = 0
    for candidates in index["props"].values():
        with_stages = [len(candidate["data"].get("Stages") or []) for candidate in candidates]
        occurrence_total += sum(with_stages)
        if with_stages:
            distinct_props_total += max(with_stages)
    action_refs = [
        action for boss in bosses for stage in boss["stages"] for action in stage["actions"]
    ]
    distinct_actions = {action["alias"] for action in action_refs}
    class_counts = Counter(
        action["type"] for action in action_refs if action.get("type")
    )
    unknown_worlds = Counter(
        boss["world"] for boss in bosses if str(boss["world"]).startswith("unknown")
    )
    world_counts = Counter(boss["world"] for boss in bosses)
    cross_world = sorted(boss["id"] for boss in bosses if len(boss["worlds"]) > 1)
    missing_actions = [action["alias"] for action in action_refs if action.get("missing")]
    placement_worlds = Counter(
        placement["world"] for boss in bosses for placement in boss["placements"]
    )
    placed = {boss["id"] for boss in bosses}
    unplaced = unplaced_mechs(index, placed)
    dangling = sorted(boss["id"] for boss in bosses if boss.get("missingProps"))

    return {
        "format": FORMAT,
        "generated": GENERATED,
        "counts": {
            "bosses": len(bosses),
            "placements": len(index["modules"]),
            "stages": stage_total,
            "stageTotals": {
                "placedMechs": stage_total,
                "distinctMechProps": distinct_props_total,
                "occurrences": occurrence_total,
            },
            "propsObjects": sum(len(value) for value in index["props"].values()),
            "propsObjectsWithStages": sum(
                1
                for candidates in index["props"].values()
                for candidate in candidates
                if candidate["data"].get("Stages")
            ),
            "zombieTypes": len(index["types"]),
            "actionRefs": len(action_refs),
            "distinctActions": len(distinct_actions),
            "actionClasses": len(class_counts),
            "missingActions": len(missing_actions),
            "bossesWithoutStages": sum(1 for boss in bosses if not boss["stages"]),
            "danglingMechs": dangling,
            "unplacedMechs": unplaced,
            "byWorld": dict(sorted(world_counts.items())),
            "unknownWorlds": dict(sorted(unknown_worlds.items())),
            "placementsByWorld": dict(sorted(placement_worlds.items())),
            "unknownPlacements": dict(
                sorted(
                    (world, count)
                    for world, count in placement_worlds.items()
                    if str(world).startswith("unknown")
                )
            ),
            "actionClassesUsed": dict(sorted(class_counts.items())),
            "crossWorldMechs": cross_world,
        },
        "sources": {
            "obb": str(obb_dir),
            "files": index["files"],
            "battleModule": "ZombossBattleModuleProperties / ZombossRiftBattleModuleProperties",
            "mechTypes": "pkg_2115_ZombieType.json",
            "mechProps": "pkg_2112_ZombiePropertySheet.json + level-local @CurrentLevel",
            "actions": "pkg_2111_ZombieWalkActionDefinition.json + level-local overrides",
        },
        "bosses": bosses,
    }


def render(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def dump(data: dict, path: Path = DEFAULT_OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render(data).encode("utf-8"))
    return path


def load_client_bosses(path: Path = DEFAULT_CLIENT) -> dict[str, dict]:
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc.get("bosses") if isinstance(doc, dict) else doc
    return {
        str(row.get("world")): row
        for row in rows or []
        if isinstance(row, dict) and row.get("world")
    }


def client_comparison(bosses: list[dict], client: dict[str, dict]) -> list[dict]:
    """Per world: pack stages vs the synthetic client row.

    A world can own several mech tables (Egypt has `zombossmech_egypt`,
    `zombossmech_egypt2`, `zombossmech_modern_egypt`), so two numbers are kept:
    the world total and one *representative* boss - the one with the most stages,
    ties broken by id - which is what a single `content/bosses.json` row roughly
    stands for. Comparing the client's single HP against the world total would
    overstate the gap, so the three worked examples use the representative.
    """

    pack: dict[str, dict] = {}
    for boss in bosses:
        values = [
            int(stage["hitPoints"])
            for stage in boss["stages"]
            if isinstance(stage["hitPoints"], (int, float))
        ]
        for world in boss["worlds"]:
            entry = pack.setdefault(
                world, {"ids": [], "stages": 0, "hpTotal": 0, "hpPerStage": [], "candidates": []}
            )
            entry["ids"].append(boss["id"])
            entry["stages"] += boss["stageCount"]
            entry["hpTotal"] += sum(values)
            entry["hpPerStage"].extend(values)
            entry["candidates"].append(
                {"id": boss["id"], "stages": boss["stageCount"], "hp": values}
            )
    rows = []
    for world in sorted(set(pack) | set(client)):
        ours = pack.get(world)
        theirs = client.get(world) or {}
        client_hp = theirs.get("hp")
        client_stages = len(theirs.get("phases") or [])
        primary = None
        if ours and ours["candidates"]:
            primary = sorted(
                ours["candidates"], key=lambda row: (-row["stages"], row["id"])
            )[0]
        primary_total = sum(primary["hp"]) if primary else None
        rows.append(
            {
                "world": world,
                "packIds": sorted(ours["ids"]) if ours else [],
                "packStages": ours["stages"] if ours else 0,
                "packHpTotal": ours["hpTotal"] if ours else 0,
                "packHpPerStage": ours["hpPerStage"] if ours else [],
                "packPrimaryId": primary["id"] if primary else None,
                "packPrimaryStages": primary["stages"] if primary else 0,
                "packPrimaryHp": primary["hp"] if primary else [],
                "packPrimaryHpTotal": primary_total,
                "clientId": theirs.get("id"),
                "clientHp": client_hp,
                "clientStages": client_stages,
                "hpDelta": (
                    (primary_total - int(client_hp))
                    if primary_total is not None and client_hp
                    else None
                ),
                "stageDelta": (
                    (primary["stages"] - client_stages)
                    if primary is not None
                    else None
                ),
            }
        )
    return rows


def render_report(data: dict, client_rows: list[dict], client_path: Path = DEFAULT_CLIENT) -> str:
    counts = data["counts"]
    bosses = data["bosses"]
    lines: list[str] = []
    add = lines.append

    add("# Boss 数据编译报告（pack → bosses_from_pack.json）")
    add("")
    add("由 `tools/contentc/bosses.py` 生成；数据源 `work/obb_packages`（%d 个文件），"
        "产物 `native/generated/bosses_from_pack.json`。" % data["sources"]["files"])
    add("")
    add("```")
    add("python tools/contentc/bosses.py            # 写 json + 本报告")
    add("python tools/contentc/bosses.py --check    # 校验已落盘文件")
    add("```")
    add("")
    add("## 0. 计数")
    add("")
    add("| 项 | 值 | 说明 |")
    add("|---|---:|---|")
    add("| 编译出的 boss（distinct mech） | %d | 每个 `ZombieType.TypeName` 一条 |" % counts["bosses"])
    add("| 战场放置（battle module 行） | %d | 同一 mech 可被多个关卡复用 |" % counts["placements"])
    add("| 阶段总数（可上场，本表采用） | %d | 50 个被 battle module 放置的 mech 之和 |" % counts["stages"])
    add("| 阶段（按 alias 去重） | %d | 同一 props 在多个关卡包里重复定义时只算一次 |"
        % counts["stageTotals"]["distinctMechProps"])
    add("| 阶段（occurrence 求和） | %d | s5 盘点报告里的 258 就是这个口径 |"
        % counts["stageTotals"]["occurrences"])
    add("| 阶段表对象 / 其中有 Stages | %d / %d | `Zombie*Zomboss*Mech*Props` |"
        % (counts["propsObjects"], counts["propsObjectsWithStages"]))
    add("| ZombieType 行 | %d | `pkg_2115_ZombieType.json` 全表 |" % counts["zombieTypes"])
    add("| 动作引用 / 去重 | %d / %d | 阶段 `Actions[]` 展开 |"
        % (counts["actionRefs"], counts["distinctActions"]))
    add("| 动作类 | %d | 每种 `*ActionDefinition` 一类 |" % counts["actionClasses"])
    add("| 未解析动作 | %d | 引用了但包内找不到对象 |" % counts["missingActions"])
    add("| 无阶段 boss | %d | 见 §4b 的悬空引用 |" % counts["bossesWithoutStages"])
    add("| 有阶段表但未被放置的 mech | %d | Battlez/Rift 变体，无 spawn，见 §4c |"
        % len(counts["unplacedMechs"]))
    add("")
    add("**三个阶段总数为什么不同**（都保留，不取整也不隐藏）：")
    add("")
    add("- `%d`（本表采用）：只有被 `ZombossBattleModuleProperties` 放进关卡的 mech 才算，"
        "引擎能真正取到的就是这一批。" % counts["stageTotals"]["placedMechs"])
    add("- `%d`（按 alias 去重）：`@CurrentLevel` 变体（如 `ZombieZombossMechAddedBeach`）"
        "会在每个引用它的关卡包里重新定义一份，去重后才是「有多少张阶段表」。"
        % counts["stageTotals"]["distinctMechProps"])
    add("- `%d`（occurrence 求和）：逐对象累加，同一张表被重复定义就重复计数 —— "
        "`docs/reviews/2026-11-20-s5-data-inventory.md` 里的 258 是这一口径，两者对得上，"
        "但 258 不等于可上场阶段数。" % counts["stageTotals"]["occurrences"])
    add("")

    add("## 1. 哪些是 pack 原值、哪些是推断")
    add("")
    add("**pack 原值（逐字段复制，未做任何归一化）**")
    add("")
    add("| 字段 | 来源 |")
    add("|---|---|")
    add("| `id` | `ZombieType.TypeName` 原字符串（如 `zombossmech_egypt`），不改写 |")
    add("| `className` / `popAnim` / `animRig` / `displayTypeName` | `ZombieClass` / `PopAnim` / `AnimRigClass` / `DisplayTypeName` |")
    add("| `propsName` / `propsSheet` / `propsPkg` | `Properties = RTID(<name>@<sheet>)` 的两段 + 对象所在包 |")
    add("| `stages[].hitPoints` / `stunSeconds` / `animRate` | `HitPoints` / `StunTime` / `AnimRateModifier` |")
    add("| `stages[].idleSeconds` | `IdleTime.Min` / `IdleTime.Max` |")
    add("| `stages[].damageIndex` | `DamageIndexFull` / `DamageIndexHalf` |")
    add("| `stages[].actions[].rtid` / `.type` / `.fields` | 阶段 `Actions[]` 的 RTID、动作对象的 objclass、动作对象**整份** objdata |")
    add("| `spawn.*` | `ReservedColumnCount` / `ZombossSpawnGridPosition.mX,mY` / `ZombossDeathRow,Column` |")
    add("| `spawn.module` / `moduleObjclass` / `stageModule` | 模块所在包、模块类名、同包 LevelDefinition 的 `StageModule` |")
    add("| `stageSelection` | `ZombossStageCount` / `ZombossStartStageIndex`（缺省为 null） |")
    add("")
    add("**推断项（每条都可人工复核）**")
    add("")
    add("| 推断 | 规则 | 复核方式 |")
    add("|---|---|---|")
    add("| `world` | 关卡 `StageModule` 别名按前缀表 `s5scan.STAGE_WORLD_HINTS` 匹配；匹配不到写 `unknown:<stage>` 并保留 | 见 §3 的 stage→world 表；下方 §4 列全部 unknown 行 |")
    add("| `spawn`（主放置） | ① 有已知世界就不选 `unknown:*` ② 优先 stage 名含 `boss` 的放置 ③ 再按包名排序 | 每条的 `placements` 都完整列出，可与 `spawn.module` 对照 |")
    add("| `worlds` | 该 mech 所有放置的世界去重排序 | 长度 >1 的 mech 列在 §2 末尾（跨世界复用） |")
    add("| `resolution` | 在 `pkg_2115_ZombieType` 找到 → `zombietype`；找不到 → `alias-guess`（用 `Zombie`+CamelCase 猜 props 名） | 全表 `resolution` 计数见下 |")
    add("")
    resolutions = Counter(boss["resolution"] for boss in bosses)
    add("`resolution` 分布：" + "、".join("`%s`=%d" % (key, value) for key, value in sorted(resolutions.items())))
    add("")
    add("**明确不采信**：`content/bosses.json` 的 HP（8000 起每条 +200 的等差，26 条 phases 完全相同）——只用于 §5 的对比，不作为任何字段来源。")
    add("")

    add("## 2. 每世界一行")
    add("")
    add("| 世界 | boss id | 阶段数 | 各阶段 HP | spawn(cols / gridX,Y) | 召唤类动作 | Fire 动作 | 来源 pkg |")
    add("|---|---|---:|---|---|---:|---:|---|")
    for boss in bosses:
        stages = boss["stages"]
        hp = " / ".join(str(stage["hitPoints"]) for stage in stages) or "—"
        spawn = boss["spawn"]
        coords = "%s / %s,%s" % (
            spawn.get("reservedColumns"),
            spawn.get("gridX"),
            spawn.get("gridY"),
        )
        summon = sum(
            1
            for stage in stages
            for action in stage["actions"]
            if action.get("type") in ("ZombossSummonActionDefinition", "ZombossSpawnActionDefinition")
        )
        fire = sum(
            1
            for stage in stages
            for action in stage["actions"]
            if action.get("type") == "ZombossFireActionDefinition"
        )
        add(
            "| %s | `%s`%s | %d | %s | %s | %d | %d | `%s` |"
            % (
                boss["world"],
                boss["id"],
                " ⚠无 props" if boss.get("missingProps") else "",
                boss["stageCount"],
                hp,
                coords,
                summon,
                fire,
                boss["modulePkg"],
            )
        )
    add("")
    if counts["crossWorldMechs"]:
        add("跨世界复用的 mech（`worlds` 长度 >1，主放置按上面的规则选）：")
        add("")
        for boss in bosses:
            if len(boss["worlds"]) > 1:
                add(
                    "- `%s`：主 `%s`，全部 %s"
                    % (boss["id"], boss["world"], "、".join(boss["worlds"]))
                )
        add("")

    add("## 3. stage → world 推断表（命中前缀即该世界）")
    add("")
    add("| stage | world |")
    add("|---|---|")
    seen_stage: dict[str, str] = {}
    for boss in bosses:
        for placement in boss["placements"]:
            seen_stage.setdefault(str(placement["stageModule"]), str(placement["world"]))
    for stage, world in sorted(seen_stage.items()):
        add("| `%s` | %s |" % (stage, world))
    add("")

    add("## 4. unknown 归属（保留，不丢）")
    add("")
    if counts["unknownWorlds"]:
        add("按 boss（distinct mech）计：`%d` 条落在 unknown 世界。按放置计：%s。"
            % (sum(counts["unknownWorlds"].values()),
               "、".join("`%s` × %d" % item for item in sorted(counts["unknownPlacements"].items()))))
        add("")
        add("| world | boss id | stage | 说明 |")
        add("|---|---|---|---|")
        for boss in bosses:
            if str(boss["world"]).startswith("unknown"):
                add(
                    "| `%s` | `%s` | `%s` | 该 stage 未命中前缀表，原样保留 |"
                    % (boss["world"], boss["id"], boss["spawn"].get("stageModule"))
                )
        add("")
        add("这些行的 `world` 字段原样保留为 `unknown:<StageModule>`，没有被归入任何客户端世界。")
    else:
        add("无（所有 stage 都命中了前缀表）。")
    add("")

    add("## 4b. 悬空引用（battle module 指向的 mech 在包里不存在）")
    add("")
    if counts["danglingMechs"]:
        add("| boss id | module pkg | 结果 |")
        add("|---|---|---|")
        for boss in bosses:
            if not boss.get("missingProps"):
                continue
            add(
                "| `%s` | `%s` | `pkg_2115_ZombieType` 无该 `TypeName` 行；按 "
                "`Zombie`+CamelCase 猜出的 props 名 `%s` 也不存在 → `stages` 为空、`missingProps=true` |"
                % (boss["id"], boss["modulePkg"], boss["propsName"])
            )
        add("")
        add("这是 pack 自身的数据缺口（Rift 关卡引用的 mech 类型没有随包发布），不是编译失败；"
            "该 boss 仍然出现在表里，只是没有阶段表，引擎需回退到 authored 数值或忽略该关卡。")
    else:
        add("无。")
    add("")

    add("## 4c. 有完整阶段表、但本包内没有任何关卡放置的 mech（%d）"
        % len(counts["unplacedMechs"]))
    add("")
    if counts["unplacedMechs"]:
        add("这些是 Battlez / Rift 变体，`Stages` 齐全但没有 `ZombossBattleModuleProperties` 把它们放上场，"
            "因此没有 `spawn`，默认不编入 `bosses`（列在这里以免看起来是被丢掉了）。")
        add("")
        add("| boss id | props | 阶段数 | 来源 pkg |")
        add("|---|---|---:|---|")
        for row in counts["unplacedMechs"]:
            add("| `%s` | `%s` | %d | `%s` |" % (row["id"], row["propsName"], row["stageCount"], row["propsPkg"]))
        add("")
    else:
        add("无。")
        add("")

    add("## 5. 零数据世界")
    add("")
    placed_worlds = {
        world for world in counts["placementsByWorld"] if world in CLIENT_WORLDS
    }
    zero = [world for world in CLIENT_WORLDS if world not in placed_worlds]
    add("按放置（%d 条 battle module）统计：26 个客户端世界里 **%d 个有 boss 关**；"
        "完全没有 boss 数据的 **%d 个**：%s。"
        % (counts["placements"], len(placed_worlds), len(zero),
           "、".join("`%s`" % world for world in zero) or "无"))
    add("")
    outside = sorted(
        world for world in counts["placementsByWorld"] if world not in CLIENT_WORLDS
    )
    if outside:
        add("另有 %d 个由 stage 名推断出来的非客户端世界（`%s`）——"
            "它们是 pack 里的屋顶/Rift/其它关卡，不属于 26 个世界，但数据保留在表里。"
            % (len(outside), "`、`".join(outside)))
        add("")
    add("这些世界在 `content/bosses.json` 里有条目（%s），"
        "但 pack 里既无 `ZombossBattleModuleProperties` 也无对应 mech —— 它们只能 authored。"
        % ("、".join("`boss_%s`" % world for world in zero) or "—"))
    add("")

    add("## 6. 与 `content/bosses.json` 的对比")
    add("")
    add("来源：`%s`（客户端合成数据）。" % client_path.as_posix())
    add("")
    add("| 世界 | 代表 pack boss | 代表 HP 序列 | 代表 HP 合计 | 该世界全部 mech / 阶段 | 客户端 id | 客户端 HP | 客户端阶段 | HP 差 | 阶段差 |")
    add("|---|---|---|---:|---|---|---:|---:|---:|---:|")
    for row in client_rows:
        hp = " / ".join(str(value) for value in row["packPrimaryHp"]) or "—"
        add(
            "| %s | %s | %s | %s | %s / %d | %s | %s | %s | %s | %s |"
            % (
                row["world"],
                ("`%s`" % row["packPrimaryId"]) if row["packPrimaryId"] else "—",
                hp,
                row["packPrimaryHpTotal"] if row["packPrimaryHpTotal"] is not None else "—",
                "、".join("`%s`" % name for name in row["packIds"]) or "—",
                row["packStages"],
                ("`%s`" % row["clientId"]) if row["clientId"] else "—",
                row["clientHp"] if row["clientHp"] is not None else "—",
                row["clientStages"] or "—",
                ("%+d" % row["hpDelta"]) if row["hpDelta"] is not None else "—",
                ("%+d" % row["stageDelta"]) if row["stageDelta"] is not None else "—",
            )
        )
    add("")
    add("「代表 boss」= 该世界里阶段数最多的 mech（并列取 id 最小），因为客户端的每行只描述一只 boss；"
        "「该世界全部 mech / 阶段」是这个世界在 pack 里的完整规模（含 Battlez/UB 等变体表）。")
    add("")

    examples = [
        row for row in client_rows if row["packPrimaryHpTotal"] and row["clientHp"] is not None
    ]
    examples.sort(key=lambda row: abs(row["hpDelta"] or 0), reverse=True)
    add("### 三个具体例子")
    add("")
    for row in examples[:3]:
        add(
            "- **%s**：pack 的 `%s` 有 %d 个阶段、HP 依次 %s（合计 %d），"
            "客户端 `%s` 只有 %d 个阶段、单一 HP %d —— HP 差 %+d，阶段差 %+d。"
            % (
                row["world"],
                row["packPrimaryId"],
                row["packPrimaryStages"],
                " / ".join(str(value) for value in row["packPrimaryHp"]),
                row["packPrimaryHpTotal"],
                row["clientId"] or "—",
                row["clientStages"],
                row["clientHp"],
                row["hpDelta"],
                row["stageDelta"],
            )
        )
    add("")
    add("结论：客户端的 HP 是「世界顺序 × 200」的等差数列（8000…13200），阶段数恒为 3，"
        "三条 `phases` 的 `speed`/`eat_mult` 也完全相同；pack 的分阶段 HP、阶段数（3 / 4 / 5 / 6）、"
        "每阶段的动作池都不同，且没有一条 world 的 HP 与客户端相同。"
        "`bosses_from_pack.json` 可以直接替换它的 `hp`/`phases` 数值来源。")
    add("")

    add("## 7. 引擎怎么用这张表")
    add("")
    add("1. 按 `world`（或 `modulePkg` 精确到关）取 boss；`unknown:*` 的行按 `spawn.stageModule` 自行决定归属。")
    add("2. 用 `stages[i].hitPoints` 作为第 i 阶段血量上限；`stages[i].actions` 是这一阶段的行动池，"
        "`type` 决定走哪个动作分支（Fire / Spawn / Summon / Rush / Walk…），`fields` 是原值参数。")
    add("3. `spawn.reservedColumns` 是本关要为 boss 预留的列数，`gridX/gridY` 是出场格；"
        "`deathRow/deathColumn` 是死亡演出定位。")
    add("4. `stageSelection` 非空时（如 SkyCity 的 `count=3/startIndex=0`），按它裁剪 `stages`。")
    add("")
    add("未做的事（诚实边界）：没有把 `Actions[]` 里的僵尸类型 RTID 展开成刷怪波次，也没有解析 "
        "`@ZombieActions` 的动作时长/前摇（这些字段在动作对象里，引擎侧按需读取即可）；"
        "`content/bosses.json` 的文案/奖励/小怪列表仍未与 pack 建立映射。")
    add("")
    return "\n".join(lines) + "\n"


def write_report(data: dict, path: Path = DEFAULT_REPORT, client_path: Path = DEFAULT_CLIENT) -> Path:
    client = load_client_bosses(client_path)
    rows = client_comparison(data["bosses"], client)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_report(data, rows, client_path).encode("utf-8"))
    return path


def check(data: dict, out_path: Path = DEFAULT_OUT) -> int:
    """Fail loudly when the shipped file drifts from what the compiler produces."""

    problems: list[str] = []
    counts = data["counts"]
    bosses = data["bosses"]
    if data.get("format") != FORMAT:
        problems.append("format is %r, expected %r" % (data.get("format"), FORMAT))
    if counts["bosses"] != len(bosses):
        problems.append("counts.bosses=%d but %d bosses" % (counts["bosses"], len(bosses)))
    ids = [boss["id"] for boss in bosses]
    if ids != sorted(ids):
        problems.append("bosses are not sorted by id")
    if len(set(ids)) != len(ids):
        problems.append("duplicate boss ids: %s" % sorted({i for i in ids if ids.count(i) > 1}))
    stage_total = sum(boss["stageCount"] for boss in bosses)
    if stage_total != counts["stages"]:
        problems.append("counts.stages=%d but stages sum to %d" % (counts["stages"], stage_total))
    for boss in bosses:
        if len(boss["stages"]) != boss["stageCount"]:
            problems.append("%s: stageCount=%d but %d stages" % (boss["id"], boss["stageCount"], len(boss["stages"])))
        for stage in boss["stages"]:
            if not isinstance(stage.get("hitPoints"), (int, float)):
                problems.append("%s stage %s has no hitPoints" % (boss["id"], stage["index"]))
        if not boss["placements"]:
            problems.append("%s has no placements" % boss["id"])
    if out_path.is_file():
        shipped = out_path.read_text(encoding="utf-8")
        if shipped != render(data):
            problems.append("shipped file differs from a fresh render")
    else:
        problems.append("missing %s" % out_path)

    print("bosses=%d placements=%d stages=%d actions=%d/%d classes=%d unknown=%d"
          % (
              counts["bosses"],
              counts["placements"],
              counts["stages"],
              counts["actionRefs"],
              counts["distinctActions"],
              counts["actionClasses"],
              sum(counts["unknownWorlds"].values()),
          ))
    for world, count in sorted(counts["byWorld"].items()):
        print("  %-22s %d" % (world, count))
    if problems:
        for problem in problems:
            print("FAIL %s" % problem)
        return 1
    print("OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile the original boss tables into one JSON.")
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB, help="original pack directory")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="compiled json path")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="markdown report path")
    parser.add_argument("--client", type=Path, default=DEFAULT_CLIENT, help="content/bosses.json for the comparison")
    parser.add_argument("--dump", action="store_true", help="print the compiled json instead of writing")
    parser.add_argument("--check", action="store_true", help="validate the shipped file and exit")
    parser.add_argument("--no-report", action="store_true", help="skip writing the markdown report")
    args = parser.parse_args(argv)

    data = compile_bosses(args.obb)
    if args.dump:
        sys.stdout.write(render(data))
        return 0
    if args.check:
        return check(data, args.out)
    out = dump(data, args.out)
    print(
        "wrote %s (bosses=%d placements=%d stages=%d)"
        % (out, data["counts"]["bosses"], data["counts"]["placements"], data["counts"]["stages"])
    )
    if not args.no_report:
        report = write_report(data, args.report, args.client)
        print("wrote %s" % report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
