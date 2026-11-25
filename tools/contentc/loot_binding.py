"""Compile the per-level loot binding: client level -> loot key / present table.

``native/generated/rewards_from_pack.json`` (``tools/contentc/rewards.py``) counts the
shipped loot and present tables, but it only keeps *per-table* totals. Nothing in that
artifact says **which level uses which key**, so an engine reading it can only settle
every level with the ``default`` loot key. In the shipped OBB that is wrong for 47
levels: 13 danger rooms, 1 whack-a-zombie level and 26 ``NoLoot`` levels.

The binding itself is not a separate table — it is a field on each level:

* ``LevelDefinition.Loot`` is an RTID pointing at one of four level modules,
  ``DefaultLoot`` / ``DangerRoomLoot`` / ``WhackLoot`` / ``NoLoot`` (all
  ``@LevelModules``). ``tools/contentc/rewards.py`` already maps those RTIDs to the
  ``LootConfig.LevelLootKey`` vocabulary (``default`` / ``danger`` / ``whack``) and
  reads ``Disable: true`` for ``NoLoot``.
* ``LevelDefinition.NormalPresentTable`` / ``ShinyPresentTable`` name a lunchbox table
  from ``pkg_2079_PresentTable.json`` — but only 8 tables are shipped (egypt, pirate,
  cowboy, future x normal/shiny), so 12 referenced names are dangling.
* ``LootOverrideModuleProperties`` (11 levels) overrides the drop for one zombie type
  (``Overrides[].{ZombieType, LootOverride}``), and
  ``ZombieDeathSeedDropModuleProperties`` (15 levels) hooks seed drops on zombie death.
  Both are modules *inside* the level package, so they are part of the binding.

This module walks the 1809 ``content/levels/*.json`` client levels, resolves each one's
``extra.package`` against ``work/obb_packages/pkg_*_LevelDefinition.json`` and records
the loot key, the present tables, where they came from and the loot modules involved.

Output (``native/generated/loot_binding.json``)::

    {
      "format": "pvz2-shuttle/loot-binding@1",
      "generated": "loot-binding-compile-v1",
      "generatedAt": "sha256:<16 hex>",
      "sources": {...},
      "counts": {...},
      "levels": {
        "<clientLevelId>": {
          "package": "pkg_0325_LevelDefinition.json",
          "world": "beach",
          "lootKey": "default" | "danger" | "whack" | null,
          "lootRtid": "RTID(DefaultLoot@LevelModules)" | null,
          "presentTable": "egypt_normal_01" | null,
          "presentSource": "level" | "world" | "default",
          "shinyPresentTable": "...",            # only when declared
          "presentTableDangling": true,          # only when the name is not shipped
          "danger": true, "whack": true, "noLoot": true,   # only when true
          "modules": ["LootOverrideModuleProperties", ...],
          "lootOverrides": [{"zombieType": "...", "lootOverride": "LargeSun", "alias": "..."}]
        }
      },
      "unknowns": [...]
    }

``presentSource`` says where the *lunchbox table* came from:

``level``
    The level package itself declares ``NormalPresentTable``.
``world``
    The level declares none and a world-scope table supplied it. No shipped world
    document carries one (``WorldData`` has no loot/present key at all), so this is
    currently 0 levels; :func:`collect_world_present_tables` reads it if it ever exists.
``default``
    Neither — the engine falls back to its own default box.

Usage::

    python tools/contentc/loot_binding.py                 # write the JSON
    python tools/contentc/loot_binding.py --check         # recompute, fail on drift
    python tools/contentc/loot_binding.py --grep Loot     # find class / field names
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
from typing import Any

FORMAT = "pvz2-shuttle/loot-binding@1"
GENERATED = "loot-binding-compile-v1"

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEVELS = ROOT / "content" / "levels"
DEFAULT_OBB = Path(os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages"))
DEFAULT_JSON = ROOT / "native" / "generated" / "loot_binding.json"

PKG_STEM_RE = re.compile(r"^(pkg_\d+)_")
RTID_RE = re.compile(r"RTID\(\s*([^@)\s]+)\s*@([^)\s]+)\s*\)")

LEVEL_CLASS = "LevelDefinition"
PRESENT_TABLE_PKG = "pkg_2079_PresentTable.json"
LOOT_TABLE_PKG = "pkg_0234_DisableSkipLevelModuleProperties.json"

# `LevelDefinition.Loot` RTID name -> `LootConfig.LevelLootKey` vocabulary.
# `NoLoot` maps to no key at all: the level has loot disabled (LootConfig `Disable: true`).
LOOT_RTID_KEYS: dict[str, str | None] = {
    "DefaultLoot": "default",
    "DangerRoomLoot": "danger",
    "WhackLoot": "whack",
    "NoLoot": None,
}

# Modules inside a level package that change what drops. `ZombieDropZombiesOnBoard*` and
# `ZombossDrop*` are spawner actions (they place zombies, not pickups) and stay out.
LOOT_MODULE_PREFIX = "Loot"
LOOT_MODULE_MARKERS = ("Module",)
LOOT_MODULE_CLASSES = frozenset(
    {
        "LootOverrideModuleProperties",
        "LootOverrideZombossRiftModuleProps",
        "ZombieDeathSeedDropModuleProperties",
    }
)

PRESENT_SOURCES = ("level", "world", "default")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def rtid_name(value: Any) -> str | None:
    """``RTID(DefaultLoot@LevelModules)`` -> ``DefaultLoot``."""
    if not isinstance(value, str):
        return None
    match = RTID_RE.search(value)
    return match.group(1) if match else None


def rtid_domain(value: Any) -> str | None:
    """``RTID(DefaultLoot@LevelModules)`` -> ``LevelModules``."""
    if not isinstance(value, str):
        return None
    match = RTID_RE.search(value)
    return match.group(2) if match else None


def is_loot_module(objclass: str) -> bool:
    """True for a level module that carries loot/present behaviour."""
    if objclass in LOOT_MODULE_CLASSES:
        return True
    return objclass.startswith(LOOT_MODULE_PREFIX) and any(
        marker in objclass for marker in LOOT_MODULE_MARKERS
    )


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def objects_of(doc: Any) -> list[dict[str, Any]]:
    """Every real object of a package document (comment markers are dicts with no class)."""
    if not isinstance(doc, dict):
        return []
    raw = doc.get("objects")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, dict) and isinstance(entry.get("objclass"), str):
            out.append(entry)
    return out


def index_level_packages(obb_dir: Path) -> dict[str, Path]:
    """``pkg_0325`` -> path of its LevelDefinition package."""
    out: dict[str, Path] = {}
    for path in sorted(obb_dir.glob("pkg_*_LevelDefinition.json")):
        match = PKG_STEM_RE.match(path.name)
        if match:
            out.setdefault(match.group(1), path)
    return out


def load_client_levels(levels_dir: Path) -> list[dict[str, str]]:
    """Client levels in ``content/levels``: ``id`` plus the ``extra.package`` stem."""
    out: list[dict[str, str]] = []
    for path in sorted(levels_dir.glob("*.json")):
        doc = load_json(path)
        if not isinstance(doc, dict):
            continue
        level_id = doc.get("id")
        if not isinstance(level_id, str) or not level_id:
            continue
        extra = doc.get("extra")
        package = ""
        if isinstance(extra, dict):
            raw = extra.get("package")
            if isinstance(raw, str):
                package = raw.strip()
        world = doc.get("world")
        out.append(
            {
                "id": level_id,
                "package": package,
                "world": world if isinstance(world, str) else "",
            }
        )
    out.sort(key=lambda item: item["id"])
    return out


def collect_world_present_tables(obb_dir: Path) -> dict[str, str]:
    """World-scope lunchbox tables, if a world document ever declares one.

    In 460.9 nothing does: ``pkg_2107_WorldData.json`` has none of ``Loot`` /
    ``PresentTable`` / ``NormalPresentTable`` on any object (checked with ``--grep``).
    The lookup stays here so ``presentSource: "world"`` is a real branch rather than a
    comment; :func:`compile_binding` passes its result straight through.
    """
    out: dict[str, str] = {}
    for path in sorted(obb_dir.glob("pkg_*.json")):
        if "_LevelDefinition" in path.name:
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if "PresentTable" not in text:
            continue
        doc = json.loads(text)
        for obj in objects_of(doc):
            objclass = obj["objclass"]
            if not objclass.startswith("World"):
                continue
            data = obj.get("objdata")
            if not isinstance(data, dict):
                continue
            table = data.get("NormalPresentTable") or data.get("PresentTable")
            if not isinstance(table, str) or not table:
                continue
            world = data.get("WorldKey") or data.get("Name") or objclass
            if isinstance(world, str) and world:
                out.setdefault(world, table)
    return out


def present_table_names(obb_dir: Path) -> dict[str, Path]:
    """Table name -> the package that defines it (``PresentTable`` objects).

    The name is ``objdata.TypeName`` (``egypt_normal_01`` / ``egypt_shiny_01`` ...), not an
    alias — ``pkg_2079`` carries no ``aliases`` at all. ``objdata.Shiny`` marks the shiny
    variant, so both roles resolve against the same 8 names.
    """
    out: dict[str, Path] = {}
    path = obb_dir / PRESENT_TABLE_PKG
    if not path.exists():
        return out
    for obj in objects_of(load_json(path)):
        if obj["objclass"] != "PresentTable":
            continue
        data = obj.get("objdata")
        name = data.get("TypeName") if isinstance(data, dict) else None
        if not isinstance(name, str) or not name:
            aliases = obj.get("aliases")
            name = aliases[0] if isinstance(aliases, list) and aliases else None
        if isinstance(name, str) and name:
            out[name] = path
    return out


def loot_table_keys(obb_dir: Path) -> set[str]:
    """``LevelLootKey`` values the shipped ``LootTable`` / ``LootConfig`` rows carry."""
    out: set[str] = set()
    path = obb_dir / LOOT_TABLE_PKG
    if not path.exists():
        return out
    for obj in objects_of(load_json(path)):
        data = obj.get("objdata")
        if not isinstance(data, dict):
            continue
        key = data.get("LevelLootKey")
        if isinstance(key, str) and key:
            out.add(key)
        entries = data.get("Entries")
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict):
                    entry_key = entry.get("LevelLootKey")
                    if isinstance(entry_key, str) and entry_key:
                        out.add(entry_key)
    return out


# --------------------------------------------------------------------------- #
# per-level binding
# --------------------------------------------------------------------------- #


def level_record(
    level: dict[str, str],
    doc: Any,
    *,
    package_name: str,
    defined_tables: dict[str, Path],
    world_tables: dict[str, str],
) -> dict[str, Any]:
    """One ``levels`` entry: loot key, present tables, provenance and loot modules."""
    objs = objects_of(doc)
    definition = next((obj for obj in objs if obj["objclass"] == LEVEL_CLASS), None)
    data = definition.get("objdata") if definition else None
    if not isinstance(data, dict):
        data = {}

    raw_loot = data.get("Loot")
    loot_rtid = rtid_name(raw_loot)
    loot_key = LOOT_RTID_KEYS.get(loot_rtid, None) if loot_rtid else None
    no_loot = bool(loot_rtid == "NoLoot")
    danger = bool(loot_rtid == "DangerRoomLoot") or data.get("IsDangerRoom") is True
    whack = bool(loot_rtid == "WhackLoot")

    present = data.get("NormalPresentTable")
    present = present if isinstance(present, str) and present else None
    shiny = data.get("ShinyPresentTable")
    shiny = shiny if isinstance(shiny, str) and shiny else None
    world_table = world_tables.get(level["world"]) or None
    if present:
        source = "level"
    elif world_table:
        source = "world"
    else:
        source = "default"

    record: dict[str, Any] = {
        "package": package_name,
        "world": level["world"],
        "lootKey": loot_key,
        "lootRtid": raw_loot if isinstance(raw_loot, str) and raw_loot else None,
        "presentTable": present or (world_table if source == "world" else None),
        "presentSource": source,
        "modules": sorted({obj["objclass"] for obj in objs if is_loot_module(obj["objclass"])}),
    }
    if shiny:
        record["shinyPresentTable"] = shiny
    if present and present not in defined_tables:
        record["presentTableDangling"] = True
    if danger:
        record["danger"] = True
    if whack:
        record["whack"] = True
    if no_loot:
        record["noLoot"] = True

    overrides: list[dict[str, Any]] = []
    for obj in objs:
        if obj["objclass"] != "LootOverrideModuleProperties":
            continue
        payload = obj.get("objdata")
        if not isinstance(payload, dict):
            continue
        aliases = obj.get("aliases")
        alias = aliases[0] if isinstance(aliases, list) and aliases else None
        rows = payload.get("Overrides")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            entry = {
                "zombieType": rtid_name(row.get("ZombieType")) or row.get("ZombieType"),
                "lootOverride": row.get("LootOverride"),
            }
            if isinstance(alias, str) and alias:
                entry["alias"] = alias
            overrides.append(entry)
    if overrides:
        record["lootOverrides"] = overrides
    return record


# --------------------------------------------------------------------------- #
# compile
# --------------------------------------------------------------------------- #


def generated_stamp(levels: list[dict[str, str]], packages: dict[str, Path]) -> str:
    """Stable digest of the inputs, never of the clock (two runs must be byte-identical)."""
    digest = hashlib.sha256()
    for level in levels:
        path = packages.get(level["package"])
        data = path.read_bytes() if path else b""
        digest.update(level["id"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(level["package"].encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(data).digest())
    return "sha256:" + digest.hexdigest()[:16]


def compile_binding(obb_dir: Path, levels_dir: Path) -> dict[str, Any]:
    levels = load_client_levels(levels_dir)
    packages = index_level_packages(obb_dir)
    defined_tables = present_table_names(obb_dir)
    world_tables = collect_world_present_tables(obb_dir)
    known_keys = loot_table_keys(obb_dir)

    records: dict[str, Any] = {}
    by_loot_key: Counter = Counter()
    by_present_source: Counter = Counter()
    by_present_table: Counter = Counter()
    by_shiny_present_table: Counter = Counter()
    by_world: Counter = Counter()
    modules: Counter = Counter()
    dangling: Counter = Counter()
    dangling_roles: dict[str, set[str]] = defaultdict(set)
    missing_loot: list[str] = []
    unknown_loot_rtid: list[str] = []
    missing_package: list[str] = []
    used_packages: set[str] = set()

    for level in levels:
        path = packages.get(level["package"])
        if path is None:
            missing_package.append(level["id"])
            records[level["id"]] = {
                "package": None,
                "world": level["world"],
                "lootKey": None,
                "lootRtid": None,
                "presentTable": None,
                "presentSource": "default",
                "modules": [],
            }
            by_present_source["default"] += 1
            by_loot_key["none"] += 1
            continue

        record = level_record(
            level,
            load_json(path),
            package_name=path.name,
            defined_tables=defined_tables,
            world_tables=world_tables,
        )
        records[level["id"]] = record
        used_packages.add(path.name)

        key = record["lootKey"]
        if key is None:
            by_loot_key["none"] += 1
        else:
            by_loot_key[key] += 1
        if record["lootRtid"] is None:
            missing_loot.append(level["id"])
        elif key is None and not record.get("noLoot"):
            unknown_loot_rtid.append(level["id"])
        by_present_source[record["presentSource"]] += 1
        by_present_table[record["presentTable"] or "(none)"] += 1
        by_shiny_present_table[record.get("shinyPresentTable") or "(none)"] += 1
        by_world[record["world"] or "(unknown)"] += 1
        for objclass in record["modules"]:
            modules[objclass] += 1

        if record.get("presentTableDangling"):
            table = record["presentTable"]
            dangling[table] += 1
            dangling_roles[table].add("normal")
        if record.get("shinyPresentTable") and record["shinyPresentTable"] not in defined_tables:
            table = record["shinyPresentTable"]
            dangling[table] += 1
            dangling_roles[table].add("shiny")

    unknowns: list[dict[str, Any]] = []
    if missing_package:
        unknowns.append(
            {
                "kind": "level-package-missing",
                "count": len(missing_package),
                "detail": "content/levels 的 extra.package 在 OBB 里找不到对应 LevelDefinition 包",
                "samples": missing_package[:10],
                "probe": "--grep <pkg 号>；核对 work/obb_packages 里是否缺该包",
            }
        )
    if missing_loot:
        unknowns.append(
            {
                "kind": "loot-field-missing",
                "count": len(missing_loot),
                "detail": "LevelDefinition 没有 Loot 字段或为空串，lootKey 记为 null；官方引擎只在有该字段时才按 key 选表",
                "samples": missing_loot[:10],
                "probe": "--grep Loot 列这些包的全部键",
            }
        )
    if unknown_loot_rtid:
        unknowns.append(
            {
                "kind": "loot-rtid-unmapped",
                "count": len(unknown_loot_rtid),
                "detail": "Loot 指向 LOOT_RTID_KEYS 之外的模块，未猜 key",
                "samples": unknown_loot_rtid[:10],
                "probe": "--grep LevelModules 找该模块定义",
            }
        )
    if dangling:
        unknowns.append(
            {
                "kind": "present-table-dangling",
                "count": sum(dangling.values()),
                "detail": (
                    "关卡引用的 lunckbox 表不在 pkg_2079_PresentTable.json 的 8 张之内；"
                    "本表保留关卡原本声明的名字，不替引擎挑替代表"
                ),
                "tables": [
                    {
                        "name": name,
                        "roles": sorted(dangling_roles[name]),
                        "levels": count,
                    }
                    for name, count in sorted(dangling.items(), key=lambda item: (-item[1], item[0]))
                ],
                "samples": [name for name, _ in sorted(dangling.items(), key=lambda i: (-i[1], i[0]))][:5],
                "probe": "--grep PresentTable；pkg_2079 只定义 egypt/pirate/cowboy/future 各 normal+shiny",
            }
        )
    if by_present_source["world"] == 0:
        unknowns.append(
            {
                "kind": "present-source-world-unused",
                "count": 0,
                "detail": (
                    "460.9 里没有任何 world 级 lunckbox 表：pkg_2107_WorldData 的 46 个对象"
                    "没有一个带 Loot / PresentTable / NormalPresentTable 键，"
                    "非关卡级的掉落只剩 pkg_0234 的 LootTable/LootConfig（按 LevelLootKey 选行，与 world 无关）"
                ),
                "probe": "--grep PresentTable 只看非 LevelDefinition 命中",
            }
        )

    payload: dict[str, Any] = {
        "format": FORMAT,
        "generated": GENERATED,
        "generatedAt": generated_stamp(levels, packages),
        "sources": {
            "levels": {"dir": "content/levels", "files": len(levels)},
            "obb": {"dir": obb_dir.name, "levelPackages": len(packages), "usedPackages": len(used_packages)},
            "lootTables": sorted(known_keys),
            "presentTables": sorted(defined_tables),
            "levelFields": sorted(
                {
                    "Loot",
                    "NormalPresentTable",
                    "ShinyPresentTable",
                    "IsDangerRoom",
                }
            ),
            "lootModules": sorted(LOOT_MODULE_CLASSES),
        },
        "counts": {
            "levels": len(levels),
            "withLootKey": sum(
                1 for record in records.values() if record.get("lootKey") is not None
            ),
            "byLootKey": dict(sorted(by_loot_key.items())),
            "byPresentSource": {name: by_present_source[name] for name in PRESENT_SOURCES},
            "byPresentTable": dict(sorted(by_present_table.items())),
            "byShinyPresentTable": dict(sorted(by_shiny_present_table.items())),
            "byWorld": dict(sorted(by_world.items())),
            "danger": sum(1 for record in records.values() if record.get("danger")),
            "whack": sum(1 for record in records.values() if record.get("whack")),
            "noLoot": sum(1 for record in records.values() if record.get("noLoot")),
            "lootFieldMissing": len(missing_loot),
            "presentTableDangling": sum(dangling.values()),
            "presentTableDanglingNames": len(dangling),
            "withLootModules": dict(sorted(modules.items())),
            "lootOverrides": sum(len(record.get("lootOverrides") or []) for record in records.values()),
        },
        "levels": records,
        "unknowns": unknowns,
    }
    return payload


def dumps(payload: Any) -> str:
    """Stable JSON: sorted keys, one-space indent, LF, trailing newline (same as emit.py)."""
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def grep(obb_dir: Path, needle: str) -> int:
    """Find a class or field name across the packages (case-insensitive substring)."""
    lowered = needle.lower()
    hits = 0
    for path in sorted(obb_dir.glob("pkg_*.json")):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if lowered not in text.lower():
            continue
        hits += 1
        classes: Counter = Counter()
        for obj in objects_of(json.loads(text)):
            objclass = obj["objclass"]
            if lowered in objclass.lower():
                classes[objclass] += 1
                continue
            data = obj.get("objdata")
            if isinstance(data, dict) and any(lowered in str(key).lower() for key in data):
                classes[objclass] += 1
        detail = ", ".join(f"{name}x{count}" for name, count in sorted(classes.items())[:6])
        print(f"{path.name}\t{text.lower().count(lowered)}\t{detail}")
    print(f"# {hits} package(s) contain {needle!r}")
    return 0 if hits else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB, help="directory holding pkg_*.json")
    parser.add_argument("--levels", type=Path, default=DEFAULT_LEVELS, help="content/levels directory")
    parser.add_argument("--out", type=Path, default=DEFAULT_JSON, help="JSON table to write")
    parser.add_argument("--check", action="store_true", help="recompute and compare, non-zero on drift")
    parser.add_argument("--grep", metavar="NEEDLE", help="search the packages for this text and exit")
    args = parser.parse_args(argv)

    if args.grep:
        return grep(args.obb, args.grep)
    if not args.obb.is_dir():
        parser.error(f"no OBB package directory: {args.obb}")
    if not args.levels.is_dir():
        parser.error(f"no client level directory: {args.levels}")

    text = dumps(compile_binding(args.obb, args.levels))
    data = text.encode("utf-8")
    if args.check:
        if not args.out.exists():
            print(f"MISSING {args.out}", file=sys.stderr)
            return 1
        current = args.out.read_bytes()
        if current != data:
            payload = json.loads(data)
            old = json.loads(current.decode("utf-8"))
            drift = [
                key
                for key in sorted(set(payload) | set(old))
                if payload.get(key) != old.get(key)
            ]
            print(f"DRIFT {args.out}: {', '.join(drift) or 'bytes differ'}", file=sys.stderr)
            return 1
        print(f"OK {args.out} ({len(data)} B)")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(data)
    payload = json.loads(data)
    counts = payload["counts"]
    print(
        f"{args.out} ({len(data)} B) levels={counts['levels']} "
        f"keys={counts['byLootKey']} present={counts['byPresentSource']} "
        f"dangling={counts['presentTableDangling']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
