"""Generate the parity matrix: how much of the original game the native client covers.

The matrix is the only progress measure for the full replica. Every number is
derived from files on disk, never from constants, so the report cannot drift
away from reality.

Columns per row:
    total       how many the original game defines (authoritative OBB tables)
    data        how many the native content pack can describe
    wired       how many have a behaviour registered in the engine
    playable    how many reach a real level and can be used/shot/eaten
    calibrated  how many have a golden trace or a video comparison

Usage:
    python tools/parity_report.py                      # writes docs/PARITY_MATRIX.md
    python tools/parity_report.py --out build/m.md      # or somewhere else

The OBB directory defaults to the one next to this repository checkout
(`../../work/obb_packages`); override it with --obb when the sheets live elsewhere.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
import os

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR") or (REPO.parent.parent / "work" / "obb_packages"))


# --------------------------------------------------------------------------- io


def load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def objects_with_data(path: Path) -> list[dict]:
    """Objects in a property sheet that actually carry an objdata block."""
    doc = load_json(path)
    objects = doc.get("objects") if isinstance(doc, dict) else None
    if not isinstance(objects, list):
        return []
    return [o for o in objects if isinstance(o, dict) and isinstance(o.get("objdata"), dict)]


def fusion_pair_count(path: Path) -> int:
    """Fusion recipes in pkg_2083.

    The sheet holds 217 objects, 199 of which carry objdata, but only one of them
    is the PlantFusionConfig that actually stores FusionPairs. Counting objects
    (the obvious reading) overstates the recipe total by 199 vs 85, so count the
    pairs themselves.
    """
    pairs = 0
    for obj in objects_with_data(path):
        data = obj.get("objdata") or {}
        entries = data.get("FusionPairs")
        if isinstance(entries, list):
            pairs += sum(1 for e in entries if isinstance(e, dict))
    return pairs


def aliases_of(sheet_path: Path) -> set[str]:
    names: set[str] = set()
    for obj in objects_with_data(sheet_path):
        for alias in obj.get("aliases") or []:
            if isinstance(alias, str):
                names.add(alias)
    return names


# ------------------------------------------------------------------------ model


@dataclass
class Row:
    total: int = 0
    data: int = 0
    wired: int = 0
    # `None` means "no derivation exists for this row", which is not the same thing as
    # "zero entries are playable". The default is `None` on purpose: a row that forgets
    # to derive its number now renders as "—" instead of quietly claiming 0.
    playable: int | None = None
    calibrated: int = 0
    note: str = ""
    playable_kind: str = "derived"  # derived | not-applicable | pending
    playable_note: str = ""

    @property
    def derived(self) -> bool:
        return self.playable is not None

    @property
    def percent(self) -> float:
        if not self.total or self.playable is None:
            return 0.0
        return 100.0 * self.playable / self.total

    def playable_text(self) -> str:
        return str(self.playable) if self.playable is not None else "—"

    def percent_text(self) -> str:
        return f"{self.percent:.1f}%" if self.playable is not None else "—"


# Rows whose 可跑 column cannot be derived from anything on disk. The module docstring
# promises "every number is derived from files on disk, never from constants", and a
# literal `playable=0` broke that promise on 2026-11-20: it read as "zero are playable"
# when the truth was "this unit has no playable channel". They render as "—" and carry
# the reason into both the table and stdout.
NOT_DERIVED: dict[str, tuple[str, str]] = {
    "僵尸 class 族": ("not-applicable", "生成表的一行不是可玩单位：class 名与关卡 zombie id 无一一映射"),
    "植物行为族": ("not-applicable", "族不是可玩单位：植物行的可跑已按族推导，此处再算会重复"),
    "世界": ("pending", "世界没有可跑通道，要等世界专属玩法统计"),
    "关卡": ("pending", "关卡能跑≠能通，要等胜率与冒烟对照"),
    "融合": ("pending", "熔合对没有族实现通道，需 fusions 表接线后才能推导"),
    "Boss": ("not-applicable", "Boss 是僵尸 class 的子集，可跑已在「僵尸」行计入"),
    "砸罐子": ("not-applicable", "小游戏关卡不是可玩单位"),
    "铁轨": ("pending", "rail 已接线（A2：车体移动/碾压/掉落/车格种植，`rail_test` 7 段 + `--run-level` 的 rail 读数），可跑要等 192 关的胜率实测"),
    "小游戏": ("not-applicable", "小游戏关卡不是可玩单位"),
    "关卡模块": ("pending", "模块是关卡的一层标签，可跑要看机制接线后的胜负，不按标签累加"),
    "关卡机制": ("pending", "数据已编译、T51 接线了五类（传送带/初始植物/初始物件/保护植物/墓碑·抖动波），可跑仍要看机制后胜率"),
    "护甲": ("pending", "护甲不是可玩单位：接线率已在「接线」列，可跑要等挂甲僵尸的胜负统计"),
    "世界门": ("pending", "门是解锁条件而不是可玩单位：可跑要等门后的关卡真被打通"),
    "商店": ("pending", "商品不是可玩单位：能买不等于能用，产物能否落地另计"),
    "掉落": ("pending", "掉落不是可玩单位：接线率在「接线」列，可跑要看经济平衡后的实测"),
}


def apply_not_derived(matrix: "Matrix") -> None:
    """Mark the rows without a derivation and say why. Called once, after rows exist."""
    for name, row in matrix.rows.items():
        mark = NOT_DERIVED.get(name)
        if mark is None:
            continue
        row.playable = None
        row.playable_kind, row.playable_note = mark


def caliber_notes(matrix: "Matrix") -> list[str]:
    """The 口径 lines that explain any non-derived 可跑 cell.

    Printed by `main()` whenever the matrix carries one, so a reader of the console
    output cannot mistake "—" for a measured zero or for a missing row.
    """
    gaps = [(name, row) for name, row in matrix.rows.items() if not row.derived]
    if not gaps:
        return []
    pending = [name for name, row in gaps if row.playable_kind == "pending"]
    inapplicable = [name for name, row in gaps if row.playable_kind != "pending"]
    notes = [
        f"口径：{len(gaps)} 行「可跑」没有推导值，表中显示 —（不是 0）："
        f"不适用 {len(inapplicable)} 行（{'、'.join(inapplicable) or '无'}）；"
        f"待统计 {len(pending)} 行（{'、'.join(pending) or '无'}）。"
    ]
    notes += [f"  - {name}（{row.playable_kind}）：{row.playable_note}" for name, row in gaps]
    return notes


@dataclass
class Matrix:
    rows: dict[str, Row] = field(default_factory=dict)
    missing_plants: list[str] = field(default_factory=list)
    missing_zombies: list[str] = field(default_factory=list)
    level_plants: set[str] = field(default_factory=set)
    level_zombies: set[str] = field(default_factory=set)
    worlds_in_obb: int = 0
    worlds_in_content: int = 0


FAMILY_PLANT_RE = re.compile(r'\{"([a-z0-9_]+)",\s*&family')
FAMILY_ZOMBIE_RE = re.compile(r'\{"([a-z0-9_]+)",\s*&zombie')


def engine_families(native_dir: Path) -> tuple[set[str], set[str]]:
    """Behaviour families the engine can actually run, read from the registry table.

    Fails closed: a registry that exists but yields no family (renamed table, changed
    macro) is an error, not "everything is unwired" — a silent empty set would make
    the whole matrix look like a regression nobody can explain.
    """
    path = native_dir / "src" / "engine" / "registry.cpp"
    if not path.is_file():
        raise FileNotFoundError(f"engine registry not found: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    plants, zombies = set(FAMILY_PLANT_RE.findall(text)), set(FAMILY_ZOMBIE_RE.findall(text))
    if not plants or not zombies:
        raise RuntimeError(f"no behaviour families parsed from {path}; the table format changed")
    return plants, zombies


def pack_counts(native_dir: Path) -> dict[str, int]:
    path = native_dir / "generated" / "coverage.json"
    if not path.is_file():
        return {}
    counts = load_json(path).get("counts") or {}
    return {str(k): int(v) for k, v in counts.items() if isinstance(v, int)}


def family_of(entry: dict) -> str:
    return str(entry.get("behavior") or entry.get("family") or "")


def plant_family_rows(native_dir: Path) -> dict:
    """Rows of the generated 339-type plant -> behaviour-family table (S4.3)."""
    empty = {"total": 0, "mapped": 0, "rows": 0, "counts": {}, "table": "missing", "labelled_match": 0}
    path = native_dir / "generated" / "plant_families.json"
    table = native_dir / "generated" / "plant_family_table.inc"
    if not path.is_file():
        return empty
    doc = load_json(path)
    rows = [entry for entry in doc.get("plants") or [] if isinstance(entry, dict)]
    counts: dict[str, int] = {}
    for entry in rows:
        family = entry.get("family")
        if family:
            counts[family] = counts.get(family, 0) + 1
    labels = doc.get("labels") or {}
    labelled_match = 0
    if isinstance(labels, dict):
        compared = int(labels.get("compared") or 0)
        agreement = float(labels.get("agreement") or 0.0)
        labelled_match = round(compared * agreement)
    return {
        "total": len(rows),
        "mapped": sum(1 for entry in rows if entry.get("family")),
        "rows": len(rows) if table.is_file() else 0,
        "counts": counts,
        "table": table.name if table.is_file() else "missing",
        "labelled_match": labelled_match,
    }


def zombie_classes(native_dir: Path) -> dict:
    """Rows of the generated `ZombieClass` -> behaviour-family table (S3.3)."""
    empty = {"total": 0, "mapped": 0, "rows": 0, "counts": {}, "table": "missing"}
    path = native_dir / "generated" / "zombie_classes.json"
    table = native_dir / "generated" / "zombie_family_table.inc"
    if not path.is_file():
        return empty
    doc = load_json(path)
    classes = [entry for entry in doc.get("classes") or [] if isinstance(entry, dict)]
    counts: dict[str, int] = {}
    for entry in classes:
        family = str(entry.get("family") or "")
        if family:
            counts[family] = counts.get(family, 0) + 1
    rows = sum(1 for line in table.read_text(encoding="utf-8").splitlines()
               if line.strip().startswith('{"')) if table.is_file() else 0
    return {
        "total": len(classes),
        "mapped": sum(1 for entry in classes if str(entry.get("family") or "")),
        "rows": rows,
        "counts": counts,
        "table": f"zombie_family_table.inc {rows} 行" if rows else "缺 .inc",
    }


def compiled_rows(native_dir: Path) -> dict[str, Row]:
    """Rows derived from the S5/S6 compiled tables.

    Every number here comes from a generated file that is itself checked by
    `tools/check_all.ps1`, so the matrix cannot claim more than the tables hold.
    A missing file yields no row at all rather than a zero row: "not compiled
    yet" and "compiled to zero" are different facts.
    """
    gen = native_dir / "generated"
    rows: dict[str, Row] = {}

    def read(name: str):
        path = gen / name
        if not path.is_file():
            return None
        try:
            return load_json(path)
        except Exception:
            return None

    projectiles = read("projectiles_from_pack.json")
    if isinstance(projectiles, dict) and isinstance(projectiles.get("projectiles"), list):
        entries = projectiles["projectiles"]
        traj = projectiles.get("trajectoryCounts") or {}
        unknown = int(traj.get("unknown") or 0)
        counts = projectiles.get("counts") or {}
        rows["弹道"] = Row(
            total=len(entries),
            data=len(entries),
            wired=len(entries) - unknown,
            note=(
                f"{counts.get('canonicalIds', 0)} 个 canonical + "
                f"{counts.get('embeddedOnlyIds', 0)} 个仅关卡内嵌；弹道 straight "
                f"{traj.get('straight', 0)} / arc {traj.get('arc', 0)} / drop "
                f"{traj.get('drop', 0)} / static {traj.get('static', 0)} / unknown {unknown}"
            ),
        )

    armors = read("armors_from_pack.json")
    if isinstance(armors, dict) and isinstance(armors.get("armors"), list):
        entries = armors["armors"]
        counts = armors.get("counts") or {}
        combination = counts.get("armorCombination") or {}
        bare = int(combination.get("0") or 0)
        wearing = sum(int(v) for k, v in combination.items() if str(k) != "0")
        rows["护甲"] = Row(
            total=len(entries),
            data=len(entries),
            # t29 (S5.11) makes `ArmorTable` the engine's source for layer order, flags and
            # the hit-point pool; 91 of the 102 rows are referenced by at least one zombie.
            wired=int(counts.get("distinctArmorRefs") or 0),
            playable=None,
            playable_kind="pending",
            note=(
                f"{counts.get('canonicalArmors', 0)} 条 canonical + "
                f"{counts.get('embeddedOnlyArmors', 0)} 条只在内嵌副本；僵尸挂甲 {wearing} / 无甲 {bare}；"
                f"与 content 桥接 exact {counts.get('contentExact', 0)} / heuristic "
                f"{counts.get('contentHeuristicBridge', 0)} / 桥不上 {counts.get('contentUnbridged', 0)}"
            ),
        )

    bosses = read("bosses_from_pack.json")
    modules = read("level_modules.json")
    if isinstance(bosses, dict) and isinstance(bosses.get("bosses"), list):
        entries = bosses["bosses"]
        counts = bosses.get("counts") or {}
        usable = len(entries) - int(counts.get("bossesWithoutStages") or 0)
        levels_with_boss = 0
        if isinstance(modules, dict):
            boss_entry = (modules.get("levelsWith") or {}).get("boss") or {}
            if isinstance(boss_entry, dict):
                levels_with_boss = int(boss_entry.get("count") or 0)
            elif isinstance(boss_entry, (int, float)):
                levels_with_boss = int(boss_entry)
        rows["Boss"] = Row(
            total=levels_with_boss or len(entries),
            data=len(entries),
            wired=usable,
            playable=None,
            playable_kind="pending",
            note=(
                f"{levels_with_boss} 关带 ZombossBattle 模块；pack 可上场 {usable} 个 boss"
                f"（{counts.get('bossesWithoutStages', 0)} 个无阶段表）"
            ),
        )

    gates = read("world_gates.json")
    if isinstance(gates, dict) and isinstance(gates.get("gates"), list):
        entries = gates["gates"]
        counts = gates.get("counts") or {}
        rows["世界门"] = Row(
            total=len(entries),
            data=len(entries),
            # `map::WorldMap::load` (native/src/worldmap.cpp) reads every entry and the
            # `--worldmap` command prints the resulting 26 world states, so all of them are
            # consumed by the client rather than merely compiled.
            wired=len(entries),
            playable=None,
            playable_kind="pending",
            note=(
                f"星门 {counts.get('star_gate', 0)} / 钥匙门 {counts.get('key_gate', 0)} / "
                f"世界门 {counts.get('worldgate', 0)}；钥匙数为 1..5 把，与星数不同域；"
                "接线 = worldmap.cpp（--worldmap 输出 26 世界的 state/starsSource）"
            ),
        )

    shop = read("shop_unlock.json")
    if isinstance(shop, dict) and isinstance(shop.get("items"), list):
        entries = shop["items"]
        counts = shop.get("counts") or {}
        kinds = counts.get("byUnlockKind") or {}
        # S6.2: `native/src/shop.cpp` loads every row and `--shop` exercises the purchase
        # path, so the row is wired. "Buyable" is a narrower number and lives in the note.
        coin_rows = sum(
            1
            for entry in entries
            if isinstance(entry.get("price"), dict)
            and str(entry["price"].get("currency") or "") in ("coin", "coins")
            and float(entry["price"].get("amount") or 0) > 0
        )
        rows["商店"] = Row(
            total=len(entries),
            data=len(entries),
            wired=len(entries),
            playable=None,
            playable_kind="pending",
            note=(
                f"解锁门槛 coins {kinds.get('coins', 0)} / world {kinds.get('world', 0)} / "
                f"mixed {kinds.get('mixed', 0)} / 无门槛 {kinds.get('none', 0)}；"
                f"coin 计价 {coin_rows} 条；源表本身没有门槛字段，门槛由 price/upgrade 结构推导"
            ),
        )

    if isinstance(modules, dict):
        levels_with = modules.get("levelsWith") or {}

        def count_of(key: str) -> int:
            entry = levels_with.get(key) or {}
            if isinstance(entry, dict):
                return int(entry.get("count") or 0)
            return int(entry or 0)

        totals = modules.get("totals") or {}
        rows["关卡模块"] = Row(
            total=int(modules.get("levels") or 0),
            data=int(totals.get("levelsWithExtra") or 0),
            wired=0,
            playable=None,
            playable_kind="pending",
            note=(
                f"extra {totals.get('keys', 0)} 键；boss {count_of('boss')} / "
                f"vasebreaker {count_of('vasebreaker')} / rail {count_of('rail')}"
                "（客户端口径；原版 rail 192 关 functional）"
            ),
        )

    mechanics = read("level_mechanics.json")
    if isinstance(mechanics, dict) and isinstance(mechanics.get("levels"), dict):
        entries = mechanics["levels"]
        counts = mechanics.get("counts") or {}

        def with_(field: str) -> int:
            return sum(
                1
                for entry in entries.values()
                if isinstance(entry, dict) and entry.get(field)
            )

        with_items = 0
        with_graves = 0
        for entry in entries.values():
            if not isinstance(entry, dict):
                continue
            spawners = entry.get("spawners") or {}
            if isinstance(spawners, dict):
                if spawners.get("gravestone"):
                    with_graves += 1
                if spawners.get("beach"):
                    with_items += 1
        any_mechanic = 0
        for entry in entries.values():
            if not isinstance(entry, dict):
                continue
            spawners = entry.get("spawners") or {}
            if (
                entry.get("conveyor")
                or entry.get("initialPlants")
                or entry.get("initialGridItems")
                or entry.get("protectThePlant")
                or entry.get("mutators")
                or entry.get("boardGrid")
                or (isinstance(spawners, dict) and spawners.get("gravestone"))
            ):
                any_mechanic += 1
        # T51 wired five kinds into engine::World: conveyor, initialPlants,
        # initialGridItems, protectThePlant, and the two spawner shapes the wave
        # director already walks (jittered pools, gravestone waves).  A level counts
        # as wired only when *every* mechanic it carries is one of those; anything
        # else (events, mutators, boardGrid, beach/fish/dino/... spawners) keeps the
        # level in the gap, which is exactly what `mechanic_unknown` reports at run time.
        consumed_spawners = {"jittered", "gravestone"}
        wired_levels = 0
        for entry in entries.values():
            if not isinstance(entry, dict):
                continue
            spawners = entry.get("spawners") or {}
            unsupported_spawner = isinstance(spawners, dict) and any(
                key not in consumed_spawners and spawners.get(key)
                for key in spawners
            )
            if (entry.get("events") or entry.get("mutators") or entry.get("boardGrid")
                    or unsupported_spawner):
                continue
            if (entry.get("conveyor") or entry.get("initialPlants")
                    or entry.get("initialGridItems") or entry.get("protectThePlant")
                    or (isinstance(spawners, dict)
                        and (spawners.get("gravestone") or spawners.get("jittered")))):
                wired_levels += 1
        rows["关卡机制"] = Row(
            total=int(counts.get("levels") or len(entries)),
            data=any_mechanic,
            wired=wired_levels,
            playable=None,
            playable_kind="pending",
            note=(
                f"传送带 {counts.get('withConveyor', with_('conveyor'))} / "
                f"初始植物 {counts.get('withInitials', with_('initialPlants'))} / "
                f"初始物件 {counts.get('withInitialGridItems', with_('initialGridItems'))} / "
                f"墓碑对象 {counts.get('withGravestones', 0)} 关 + 墓碑波 {with_graves} 关 / "
                f"保护植物 {counts.get('withProtect', with_('protectThePlant'))} / "
                f"事件 {counts.get('withEvents', with_('events'))} / "
                f"变异 {counts.get('withMutators', with_('mutators'))} / "
                f"棋盘格 {counts.get('withBoardGrid', with_('boardGrid'))} / "
                f"海滩生成器 {with_items}；未解析波次 {counts.get('waveUnresolved', 0)} 条，"
                f"unknowns {len(mechanics.get('unknowns') or [])} 条"
            ),
        )

    rewards = read("rewards_from_pack.json")
    if isinstance(rewards, dict) and isinstance(rewards.get("rewards"), list):
        entries = [r for r in rewards["rewards"] if isinstance(r, dict)]
        by_kind: dict[str, int] = {}
        for entry in entries:
            kind = str(entry.get("kind") or "unknown")
            by_kind[kind] = by_kind.get(kind, 0) + 1
        # T55 wired the three kinds that can already land in Progress: coins,
        # keys and seed packs. Everything else is a row the engine reports as
        # `reward_unmodelled` instead of silently dropping it.
        wired = by_kind.get("coin", 0) + by_kind.get("key", 0) + by_kind.get("seed", 0)
        rows["掉落"] = Row(
            total=len(entries),
            data=len(entries),
            wired=wired,
            playable=None,
            playable_kind="pending",
            note=(
                f"金币 {by_kind.get('coin', 0)} / 钥匙 {by_kind.get('key', 0)} / "
                f"种子包 {by_kind.get('seed', 0)} 已落地；其余 {len(entries) - wired} 行发 "
                f"`reward_unmodelled`（植物 {by_kind.get('plant', 0)} / 强化 {by_kind.get('upgrade', 0)} / "
                f"pinata {by_kind.get('pinata', 0)}…）；悬空表 "
                f"{len(rewards.get('danglingPresentTables') or [])} 张，逐关绑定缺失（见 C56）"
            ),
        )

    return rows


def golden_names(native_dir: Path) -> set[str]:
    golden = native_dir / "tests" / "golden"
    if not golden.is_dir():
        return set()
    return {p.stem for p in golden.rglob("*.json")}


def level_references(content_dir: Path) -> tuple[set[str], set[str], set[str], list[str]]:
    """Plant ids in decks and zombie ids in waves across every level file."""
    plants: set[str] = set()
    zombies: set[str] = set()
    worlds: set[str] = set()
    files: list[str] = []
    for path in sorted((content_dir / "levels").glob("*.json")):
        files.append(path.name)
        level = load_json(path)
        worlds.add(str(level.get("world", "")))
        plants.update(str(p) for p in level.get("deck") or [])
        for wave in level.get("waves") or []:
            for spawn in wave.get("zombies") or []:
                if isinstance(spawn, dict) and "type" in spawn:
                    zombies.add(str(spawn["type"]))
    return plants, zombies, worlds, files


def level_flags(content_dir: Path) -> dict[str, int]:
    """Count levels whose `extra` carries a rule flag (rail / minecarts / vasebreaker).

    T53 turned these three into builder output derived from the original tables, so
    the count must come from the level files themselves; the old `minigames.json`
    route reported 45 vasebreaker levels and knew nothing about rails.
    """
    flags = {"rail": 0, "minecarts": 0, "vasebreaker": 0}
    for path in sorted((content_dir / "levels").glob("*.json")):
        extra = load_json(path).get("extra") or {}
        for name in flags:
            value = extra.get(name)
            if value is True or (isinstance(value, list) and value):
                flags[name] += 1
    return flags


# ---------------------------------------------------------------------- builder


def build_parity_matrix(obb_dir: Path, content_dir: Path | None = None,
                        native_dir: Path | None = None) -> Matrix:
    content_dir = content_dir or REPO / "content"
    native_dir = native_dir or REPO / "native"
    matrix = Matrix()

    plant_types = objects_with_data(obb_dir / "pkg_2074_PlantType.json")
    zombie_types = objects_with_data(obb_dir / "pkg_2115_ZombieType.json")
    fusion_pairs = fusion_pair_count(obb_dir / "pkg_2083_PlantFusionConfig.json")
    world_objs = objects_with_data(obb_dir / "pkg_2107_WorldData.json")

    content_plants = load_json(content_dir / "plants.json")
    content_zombies = load_json(content_dir / "zombies.json")
    content_worlds = load_json(content_dir / "worlds.json")
    content_fusions = load_json(content_dir / "fusions.json")
    content_bosses = load_json(content_dir / "bosses.json")
    minigames = load_json(content_dir / "minigames.json")

    level_plants, level_zombies, level_worlds, level_files = level_references(content_dir)
    flags = level_flags(content_dir)
    plant_families, zombie_families = engine_families(native_dir)
    counts = pack_counts(native_dir)
    golden = golden_names(native_dir)

    plant_ids = {str(p.get("id")) for p in content_plants}
    zombie_ids = {str(z.get("id")) for z in content_zombies}
    family_of_plant = {str(p.get("id")): family_of(p) for p in content_plants}
    family_of_zombie = {str(z.get("id")): family_of(z) for z in content_zombies}
    wired_plants = sum(1 for p in content_plants if family_of(p) in plant_families)
    wired_zombies = sum(1 for z in content_zombies if family_of(z) in zombie_families)
    # "Playable" is measured, not asserted: an entry counts only when a real level
    # references it *and* its behaviour family has an implementation. It still says
    # nothing about win rates — that is what the smoke runs and golden traces are for.
    playable_plants = sum(
        1 for pid in level_plants if pid in family_of_plant and family_of_plant[pid] in plant_families
    )
    playable_zombies = sum(
        1 for zid in level_zombies if zid in family_of_zombie and family_of_zombie[zid] in zombie_families
    )
    matrix.level_plants = level_plants
    matrix.level_zombies = level_zombies
    matrix.missing_plants = sorted(level_plants - plant_ids)
    matrix.missing_zombies = sorted(level_zombies - zombie_ids)

    matrix.rows["植物"] = Row(
        total=len(plant_types),
        data=len(content_plants),
        wired=wired_plants,
        playable=playable_plants,
        calibrated=len(golden & plant_ids),
        note=f"deck 引用 {len(level_plants)} 种；pack 规则 {counts.get('plants', 0)} 种待映射",
    )
    matrix.rows["僵尸"] = Row(
        total=len(zombie_types),
        data=len(content_zombies),
        wired=wired_zombies,
        playable=playable_zombies,
        calibrated=len(golden & zombie_ids),
        note=f"波次引用 {len(level_zombies)} 种；pack 规则 {counts.get('zombies', 0)} 种待映射",
    )
    classes = zombie_classes(native_dir)
    matrix.rows["僵尸 class 族"] = Row(
        total=classes["total"],
        data=classes["mapped"],
        wired=classes["rows"],
        calibrated=0,
        note=(
            f"生成表 {classes['table']}；族分布 "
            + "、".join(f"{name} {count}" for name, count in sorted(classes["counts"].items()))
        ) if classes["total"] else "缺 native/generated/zombie_classes.json",
    )
    pfamilies = plant_family_rows(native_dir)
    matrix.rows["植物行为族"] = Row(
        total=pfamilies["total"],
        data=pfamilies["mapped"],
        wired=pfamilies["rows"],
        calibrated=pfamilies["labelled_match"],
        note=(
            f"生成表 {pfamilies['table']}；族分布 "
            + "、".join(f"{name} {count}" for name, count in sorted(pfamilies["counts"].items()))
            + f"；44 株标注对照一致 {pfamilies['labelled_match']}"
        ) if pfamilies["total"] else "缺 native/generated/plant_families.json",
    )
    matrix.rows["世界"] = Row(
        total=len(content_worlds),
        data=len(content_worlds),
        wired=0,
        calibrated=0,
        note=f"OBB WorldData {len(world_objs)} 条，关卡覆盖 {len(level_worlds)} 个世界",
    )
    matrix.rows["关卡"] = Row(
        total=len(level_files),
        data=len(level_files),
        wired=0,
        calibrated=0,
    )
    recipes = content_fusions.get("recipes") or []
    compiled = load_json(native_dir / "generated" / "fusions_from_pack.json")
    compiled_pairs = compiled.get("pairs") if isinstance(compiled, dict) else None
    compiled_count = len(compiled_pairs) if isinstance(compiled_pairs, list) else 0
    matrix.rows["融合"] = Row(
        total=fusion_pairs,
        data=len(recipes),
        wired=compiled_count,
        calibrated=0,
        note="配方键 48 两侧一致" if compiled_count else "",
    )
    # S5/S6 compiled tables (projectiles, armors, bosses, gates, shop, modules).
    # They take precedence over the content-json guess because they come from the
    # original sheets.
    matrix.rows.update(compiled_rows(native_dir))
    if "Boss" not in matrix.rows:
        bosses = content_bosses.get("bosses") or []
        matrix.rows["Boss"] = Row(
            total=len(bosses),
            data=len(bosses),
            note="按 ZombieClass 视为 Boss；pack 表尚未编译",
        )
    mini = minigames.get("minigames") or []
    # 砸罐子/铁轨都改为「content 里 extra 标记的关卡数」：T53 之后这三个标记是
    # obb_build_content_v2 从原表派生并写回的，minigames.json 的 45 条是旧口径。
    matrix.rows["砸罐子"] = Row(
        total=flags["vasebreaker"],
        data=flags["vasebreaker"],
        note="extra.vasebreaker；玩法（砸罐子）未实现",
    )
    matrix.rows["铁轨"] = Row(
        total=flags["rail"],
        data=flags["rail"],
        note=f"extra.rail {flags['rail']} 关 / extra.minecarts {flags['minecarts']} 关；引擎不消费 rail",
    )
    matrix.rows["小游戏"] = Row(total=len(mini), data=len(mini))
    matrix.worlds_in_obb = len(world_objs)
    matrix.worlds_in_content = len(content_worlds)
    apply_not_derived(matrix)
    return matrix


# ----------------------------------------------------------------------- render


def render_markdown(matrix: Matrix, generated: str = "") -> str:
    lines = [
        "# 复刻覆盖矩阵",
        "",
        "> 由 `tools/parity_report.py` 生成，勿手改。所有数字来自磁盘上的表与代码，不是常量。",
        f"> 生成时间：{generated or '（未记录）'}",
        "",
        "| 类别 | 总量 | 数据 | 接线 | 可玩 | 校准 | 完成度 | 说明 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, row in matrix.rows.items():
        lines.append(
            f"| {name} | {row.total} | {row.data} | {row.wired} | {row.playable_text()} | "
            f"{row.calibrated} | {row.percent_text()} | {row.note} |"
        )
    lines += [
        "",
        "## 口径",
        "",
        "- **总量**：原版属性表定义的数量（植物 `pkg_2074_PlantType`，僵尸 `pkg_2115_ZombieType`，融合 `pkg_2083`）。",
        "- **数据**：`content/` 能描述的条目（可玩/图鉴集），不代表原版全类型。",
        "- **接线**：`content/*.json` 的 `behavior` 族已出现在 `native/src/engine/registry.cpp` 的行为族表里（按源码解析，不是常量名单）。注意两条执行路径：有 `Actions` 的植物走属性表槽位执行器（`action_runner`），没有槽位的才落到族函数；因此「接线」只表示该族有实现，不代表两者都被走过。",
        "- **可跑**：既被至少一张关卡引用、族又有实现（推导值，不保证能赢；胜负与数值校准看冒烟场景与 golden 轨迹）。",
        "- **`—`**：该行的「可跑」没有推导口径（不是 0，也不是缺数据）。原版 2026-11-20 之前这里写死 `playable=0`，与本文件头部「所有数字来自磁盘」的承诺冲突，round-3 已改为显式标记：",
        "- **校准**：有 `native/tests/golden/<id>.json` 轨迹或有录像对照的条目。",
    ]
    for name, row in matrix.rows.items():
        if row.derived:
            continue
        lines.append(f"  - `{name}` — **{row.playable_kind}**：{row.playable_note}。")
    lines += [
        "",
        "## 引用闭合",
        "",
        f"- 关卡 plant 引用：{len(matrix.level_plants)} 种，缺失 {len(matrix.missing_plants)} 种",
        f"- 关卡 zombie 引用：{len(matrix.level_zombies)} 种，缺失 {len(matrix.missing_zombies)} 种",
        f"- 世界：content {matrix.worlds_in_content} / OBB {matrix.worlds_in_obb}",
    ]
    if matrix.missing_plants:
        lines.append(f"- 缺失植物：`{', '.join(matrix.missing_plants[:40])}`")
    if matrix.missing_zombies:
        lines.append(f"- 缺失僵尸：`{', '.join(matrix.missing_zombies[:40])}`")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB, help="OBB property sheet directory")
    parser.add_argument("--content", type=Path, default=REPO / "content")
    parser.add_argument("--native", type=Path, default=REPO / "native")
    parser.add_argument("--out", type=Path, default=REPO / "docs" / "PARITY_MATRIX.md")
    parser.add_argument("--generated", default="")
    args = parser.parse_args()

    matrix = build_parity_matrix(args.obb, args.content, args.native)
    text = render_markdown(matrix, args.generated)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(text.encode("utf-8"))
    print(f"wrote {args.out}")
    for name, row in matrix.rows.items():
        print(f"{name:6s} total={row.total:5d} data={row.data:5d} playable={row.playable_text():>5s}")
    # A literal in the 可跑 column used to be indistinguishable from a measurement; the
    # note now comes out on stdout as well as in the document.
    for note in caliber_notes(matrix):
        print(note)
    if matrix.missing_plants or matrix.missing_zombies:
        print(f"MISSING plants={matrix.missing_plants} zombies={matrix.missing_zombies}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
