"""Build the zombie roster from what the mechanics actually reference.

`content/zombies.json` is the client roster: 55 hand-written rows. The OBB has
1424 ZombieType objects and 16 CreatureType objects, but only a small set is
actually reachable through a level rule:

* ``spawners.spider``  -- ``SpiderRainZombieSpawnerProps.SpiderZombieName``
* ``spawners.fish``    -- ``Zombies[].Type`` (atlantis family) and
                          ``Fishes[].Type`` (``@CreatureTypes``)
* ``minigames.json``   -- ``SpawnWhackAZombiesProps[].Zombies[].Type``

This tool collects exactly those ids, resolves each one in
``pkg_2115_ZombieType.json`` / ``pkg_0013_CreatureType.json`` (HP through the
``Properties`` RTID into ``pkg_2112_ZombiePropertySheet.json``), writes the
evidence to ``native/generated/zombie_roster.json`` and appends the new rows to
``content/zombies.json`` with ``"source": "pack"``.

Rules
-----
* The 55 authored rows are copied verbatim; the merge is idempotent and
  ``--check`` compares both files byte for byte.
* An id that already exists in the authored roster is a *conflict*: the
  authored row wins and nothing is appended.
* An id that cannot be resolved is *unresolved* and never invented.
* No wall clock: the stamp is ``null`` and the input digests are content
  addressed.
* The artifact keeps ``hp: null`` when the sheet has no Hitpoints; the row
  written into ``content/zombies.json`` omits the key instead, because
  ``catalog.cpp`` fails on an explicit null (``number(j, "hp", ...)``).

Usage
-----
    python tools/contentc/zombie_roster.py            # write both artifacts
    python tools/contentc/zombie_roster.py --check    # verify, exit 1 on drift
    python tools/contentc/zombie_roster.py --dry-run  # report only
    python tools/contentc/zombie_roster.py -n         # summary only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # allow `python tools/contentc/zombie_roster.py`
    sys.path.insert(0, str(ROOT))

from tools.contentc import emit  # noqa: E402

# A clone supplies the pack tree through PVZ2_OBB_DIR, like every other compiler.
DEFAULT_OBB = Path(
    os.environ.get("PVZ2_OBB_DIR") or (ROOT.parent.parent / "work" / "obb_packages")
)
DEFAULT_MECHANICS = ROOT / "native" / "generated" / "level_mechanics.json"
DEFAULT_MINIGAMES = ROOT / "native" / "generated" / "minigames.json"
DEFAULT_CLASSES = ROOT / "native" / "generated" / "zombie_classes.json"
DEFAULT_ZOMBIES = ROOT / "content" / "zombies.json"
DEFAULT_JSON = ROOT / "native" / "generated" / "zombie_roster.json"

ZOMBIE_TYPE_SHEET = "pkg_2115_ZombieType.json"
CREATURE_TYPE_SHEET = "pkg_0013_CreatureType.json"
ZOMBIE_PROP_SHEET = "pkg_2112_ZombiePropertySheet.json"

FORMAT = 1
MARKER = "zombie-roster-v1"
PACK_SOURCE = "pack"
KINDS = ("spider", "fish", "fish_creature", "minigame")
FAMILIES = ("walk", "jump", "steal", "summon", "gargantuar", "fly")
ROW_KEYS = (
    "id",
    "source",
    "objclass",
    "typeName",
    "zombieClass",
    "family",
    "hp",
    "hpSource",
    "popAnim",
    "creatureClass",
    "homeWorld",
    "isBasicZombie",
    "referencedBy",
    "referencedCounts",
)


class InputError(RuntimeError):
    """A required input is missing or malformed."""


@dataclass
class Roster:
    rows: list[dict]
    authored: list[str]
    authored_rows: list[dict]
    conflicts: list[dict]
    unresolved: list[dict]
    counts: dict
    references: dict
    sources: dict
    digests: dict = field(default_factory=dict)

    @property
    def added(self) -> list[dict]:
        return self.rows


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise InputError(f"missing input: {path}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid JSON in {path}: {exc}") from exc


def rtid_name(value) -> str | None:
    """``RTID(name@Sheet)`` -> ``name``; anything else passes through."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.startswith("RTID(") and text.endswith(")"):
        return text[5:-1].split("@")[0]
    return text or None


def index_aliases(objects) -> dict:
    index = {}
    for obj in objects:
        for alias in obj.get("aliases") or []:
            index.setdefault(alias, obj)
    return index


def _spider_names(obb: Path, packages: set[str]) -> dict[str, set[str]]:
    """Package -> SpiderZombieName values, scanned only for the packages we need."""
    result: dict[str, set[str]] = {}
    for package in sorted(packages):
        path = obb / f"{package}_LevelDefinition.json"
        if not path.is_file():
            continue
        for obj in read_json(path).get("objects") or []:
            if obj.get("objclass") != "SpiderRainZombieSpawnerProps":
                continue
            name = (obj.get("objdata") or {}).get("SpiderZombieName")
            if isinstance(name, str) and name:
                result.setdefault(package, set()).add(name)
    return result


def _walk_strings(node, path: str = ""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _walk_strings(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk_strings(value, f"{path}[{index}]")
    elif isinstance(node, str):
        yield path, node


def collect_references(mechanics: dict, minigames: dict, obb: Path) -> dict[str, dict[str, set[str]]]:
    """id -> {kind: {level, ...}} for every id a level rule actually names."""
    refs: dict[str, dict[str, set[str]]] = {}

    def add(name, kind: str, level: str) -> None:
        if not name:
            return
        refs.setdefault(name, {}).setdefault(kind, set()).add(level)

    levels = mechanics.get("levels") or {}
    spider_levels = {lv for lv, row in levels.items() if (row.get("spawners") or {}).get("spider")}
    package_of = {
        lv: (((levels[lv].get("source") or {}).get("package") or "").replace("_LevelDefinition.json", ""))
        for lv in spider_levels
    }
    names = _spider_names(obb, {pkg for pkg in package_of.values() if pkg})
    for level in sorted(spider_levels):
        for name in names.get(package_of[level], ()):
            add(name, "spider", level)

    for level, row in levels.items():
        for spawner in (row.get("spawners") or {}).get("fish") or []:
            for zombie in spawner.get("zombies") or []:
                add(rtid_name(zombie.get("type")), "fish", level)
            for fish in spawner.get("fishes") or []:
                add(rtid_name(fish.get("type")), "fish_creature", level)

    for level, row in (minigames.get("levels") or {}).items():
        for path, text in _walk_strings((row.get("params") or {}).get("whackazombie")):
            if "@ZombieTypes)" not in text:
                continue
            add(rtid_name(text), "minigame", level)

    return refs


def _hp_of(objdata: dict, prop_index: dict) -> tuple[int | None, str | None]:
    alias = rtid_name(objdata.get("Properties"))
    if not alias:
        return None, None
    sheet = prop_index.get(alias) or {}
    hp = (sheet.get("objdata") or {}).get("Hitpoints")
    return (int(hp) if isinstance(hp, (int, float)) else None), alias


def build(obb: Path = DEFAULT_OBB, mechanics_path: Path = DEFAULT_MECHANICS,
          minigames_path: Path = DEFAULT_MINIGAMES, classes_path: Path = DEFAULT_CLASSES,
          zombies_path: Path = DEFAULT_ZOMBIES) -> Roster:
    mechanics = read_json(mechanics_path)
    minigames = read_json(minigames_path)
    classes = read_json(classes_path)
    loaded = read_json(zombies_path)
    if not isinstance(loaded, list):
        raise InputError(f"{zombies_path} must be a list of zombie rows")
    # The file is both input and output: rows we wrote earlier carry source="pack".
    authored_rows = [row for row in loaded if row.get("source") != PACK_SOURCE]

    ztypes = index_aliases(read_json(obb / ZOMBIE_TYPE_SHEET).get("objects") or [])
    ctypes = index_aliases(read_json(obb / CREATURE_TYPE_SHEET).get("objects") or [])
    props = index_aliases(read_json(obb / ZOMBIE_PROP_SHEET).get("objects") or [])
    families = {row["className"]: row["family"] for row in classes.get("classes") or []}

    refs = collect_references(mechanics, minigames, obb)
    authored_ids = [row.get("id") for row in authored_rows if row.get("id")]
    authored_set = set(authored_ids)

    rows: list[dict] = []
    conflicts: list[dict] = []
    unresolved: list[dict] = []
    for zid in sorted(refs):
        kinds = refs[zid]
        if zid in authored_set:
            conflicts.append({
                "id": zid,
                "kinds": sorted(kinds),
                "reason": "content/zombies.json 已有同 id 的手工行；保留手工行，不追加 pack 行",
            })
            continue
        creature = ctypes.get(zid)
        zombie = ztypes.get(zid)
        if creature is None and zombie is None:
            unresolved.append({
                "id": zid,
                "kinds": sorted(kinds),
                "reason": f"在 {ZOMBIE_TYPE_SHEET} 与 {CREATURE_TYPE_SHEET} 里都找不到该别名",
            })
            continue
        obj = creature if creature is not None else zombie
        objclass = "CreatureType" if creature is not None else "ZombieType"
        data = obj.get("objdata") or {}
        zombie_class = data.get("ZombieClass") if objclass == "ZombieType" else None
        family = families.get(zombie_class) if zombie_class else None
        if objclass == "ZombieType" and family is None:
            unresolved.append({
                "id": zid,
                "kinds": sorted(kinds),
                "reason": f"ZombieClass {zombie_class!r} 不在 native/generated/zombie_classes.json 的 183 类里",
            })
            continue
        hp, hp_source = _hp_of(data, props) if objclass == "ZombieType" else (None, None)
        referenced = [
            {"kind": kind, "level": level}
            for kind in KINDS
            for level in sorted(kinds.get(kind, ()))
        ]
        rows.append({
            "id": zid,
            "source": PACK_SOURCE,
            "objclass": objclass,
            "typeName": data.get("TypeName"),
            "zombieClass": zombie_class,
            "family": family,
            "hp": hp,
            "hpSource": hp_source,
            "popAnim": data.get("PopAnim"),
            "creatureClass": data.get("CreatureClass") if objclass == "CreatureType" else None,
            "homeWorld": data.get("HomeWorld"),
            "isBasicZombie": data.get("IsBasicZombie"),
            "referencedBy": referenced,
            "referencedCounts": {kind: len(kinds.get(kind, ())) for kind in KINDS},
        })

    by_kind = {kind: sum(1 for row in rows if row["referencedCounts"][kind]) for kind in KINDS}
    by_objclass: dict[str, int] = {}
    by_family: dict[str, int] = {}
    for row in rows:
        by_objclass[row["objclass"]] = by_objclass.get(row["objclass"], 0) + 1
        if row["family"]:
            by_family[row["family"]] = by_family.get(row["family"], 0) + 1

    counts = {
        "authored": len(authored_ids),
        "added": len(rows),
        "total": len(authored_ids) + len(rows),
        "referenced": len(refs),
        "conflicts": len(conflicts),
        "unresolved": len(unresolved),
        "byKind": by_kind,
        "byObjclass": dict(sorted(by_objclass.items())),
        "byFamily": dict(sorted(by_family.items())),
        "withHp": sum(1 for row in rows if row["hp"] is not None),
        "withoutHp": sum(1 for row in rows if row["hp"] is None),
    }
    references = {
        kind: {
            "ids": sum(1 for ref in refs.values() if ref.get(kind)),
            "levels": len({level for ref in refs.values() for level in ref.get(kind, ())}),
        }
        for kind in KINDS
    }

    digests = {}
    for label, path in (
        ("mechanics", mechanics_path),
        ("minigames", minigames_path),
        ("classes", classes_path),
        ("zombies", zombies_path),
        ("zombieTypes", obb / ZOMBIE_TYPE_SHEET),
        ("creatureTypes", obb / CREATURE_TYPE_SHEET),
        ("zombieProperties", obb / ZOMBIE_PROP_SHEET),
    ):
        data = path.read_bytes()
        digests[label] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    sources = {
        "obb": "work/obb_packages",
        "mechanics": "native/generated/level_mechanics.json",
        "minigames": "native/generated/minigames.json",
        "classes": "native/generated/zombie_classes.json",
        "content": "content/zombies.json",
        "zombieTypes": f"work/obb_packages/{ZOMBIE_TYPE_SHEET}",
        "creatureTypes": f"work/obb_packages/{CREATURE_TYPE_SHEET}",
        "zombieProperties": f"work/obb_packages/{ZOMBIE_PROP_SHEET}",
    }

    return Roster(
        rows=rows,
        authored=authored_ids,
        authored_rows=authored_rows,
        conflicts=conflicts,
        unresolved=unresolved,
        counts=counts,
        references=references,
        sources=sources,
        digests=digests,
    )


def content_row(row: dict) -> dict:
    """The row written into content/zombies.json (engine-safe: no explicit nulls)."""
    out: dict = {"id": row["id"]}
    if row["family"]:
        out["behavior"] = row["family"]
        out["family"] = row["family"]
    if row["hp"] is not None:
        out["hp"] = row["hp"]
    tags = ["creature", PACK_SOURCE] if row["objclass"] == "CreatureType" else ["zombie", PACK_SOURCE]
    if row["homeWorld"]:
        tags.append(row["homeWorld"])
    out["tags"] = tags
    out["source"] = PACK_SOURCE
    out["objclass"] = row["objclass"]
    if row["creatureClass"]:
        out["creatureClass"] = row["creatureClass"]
    if row["popAnim"]:
        out["popAnim"] = row["popAnim"]
    out["referencedBy"] = row["referencedBy"]
    extra = {
        "packTypeName": row["typeName"],
        "zombieClass": row["zombieClass"],
        "popAnim": row["popAnim"],
        "homeWorld": row["homeWorld"],
    }
    out["extra"] = {key: value for key, value in extra.items() if value is not None}
    return out


def merge_content(authored_rows: list[dict], roster: Roster) -> list[dict]:
    """Authored rows first (verbatim), then the pack rows sorted by id."""
    merged = list(authored_rows)
    existing = {row.get("id") for row in authored_rows}
    for row in roster.rows:
        if row["id"] in existing:
            raise InputError(f"pack row {row['id']!r} collides with an authored row")
        merged.append(content_row(row))
    return merged


def render_artifact(roster: Roster) -> str:
    payload = {
        "format": FORMAT,
        "marker": MARKER,
        "generated": None,
        "sources": roster.sources,
        "inputs": roster.digests,
        "counts": roster.counts,
        "references": roster.references,
        "authored": roster.authored,
        "added": roster.added,
        "conflicts": roster.conflicts,
        "unresolved": roster.unresolved,
    }
    return emit.dumps(payload)


def render_content(rows: list[dict]) -> str:
    """Matches the hand-maintained file: indent=1, no trailing newline."""
    return json.dumps(rows, ensure_ascii=False, indent=1)


def check(content_path: Path = DEFAULT_ZOMBIES, artifact_path: Path = DEFAULT_JSON,
          **kwargs) -> tuple[bool, str, Roster]:
    roster = build(zombies_path=content_path, **kwargs)
    expected_content = render_content(merge_content(roster.authored_rows, roster))
    expected_artifact = render_artifact(roster)
    problems = []
    if not artifact_path.is_file():
        problems.append(f"{artifact_path} 不存在")
    elif artifact_path.read_text(encoding="utf-8") != expected_artifact:
        problems.append(f"{artifact_path} 与重算结果不一致")
    if content_path.read_text(encoding="utf-8") != expected_content:
        problems.append(f"{content_path} 与重算结果不一致（authored + pack 行）")
    message = "产物已是最新" if not problems else "；".join(problems)
    return not problems, message, roster


def write_outputs(content_path: Path = DEFAULT_ZOMBIES, artifact_path: Path = DEFAULT_JSON,
                  **kwargs) -> Roster:
    roster = build(zombies_path=content_path, **kwargs)
    emit.write_text(artifact_path, render_artifact(roster))
    emit.write_text(content_path, render_content(merge_content(roster.authored_rows, roster)))
    return roster


def summarize(roster: Roster) -> str:
    counts = roster.counts
    kinds = " ".join(f"{kind}={counts['byKind'][kind]}" for kind in KINDS)
    families = " ".join(f"{name}={count}" for name, count in counts["byFamily"].items())
    return (
        f"zombie-roster: authored={counts['authored']} added={counts['added']} "
        f"total={counts['total']} referenced={counts['referenced']} "
        f"conflicts={counts['conflicts']} unresolved={counts['unresolved']} "
        f"({kinds}) hp {counts['withHp']}/{counts['withoutHp']} families[{families}]"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Zombie roster derived from mechanic references")
    parser.add_argument("--obb", type=Path, default=DEFAULT_OBB)
    parser.add_argument("--mechanics", type=Path, default=DEFAULT_MECHANICS)
    parser.add_argument("--minigames", type=Path, default=DEFAULT_MINIGAMES)
    parser.add_argument("--classes", type=Path, default=DEFAULT_CLASSES)
    parser.add_argument("--zombies", type=Path, default=DEFAULT_ZOMBIES)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--check", action="store_true", help="verify the artifacts, exit 1 on drift")
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    parser.add_argument("-n", "--summary", action="store_true", help="one-line summary only")
    args = parser.parse_args(argv)

    kwargs = {
        "obb": args.obb,
        "mechanics_path": args.mechanics,
        "minigames_path": args.minigames,
        "classes_path": args.classes,
    }
    try:
        if args.check:
            ok, message, roster = check(content_path=args.zombies, artifact_path=args.json, **kwargs)
            print(summarize(roster))
            print(message)
            return 0 if ok else 1
        if args.dry_run or args.summary:
            roster = build(zombies_path=args.zombies, **kwargs)
            print(summarize(roster))
            if args.dry_run:
                for row in roster.added[:10]:
                    print(f"  + {row['id']} {row['objclass']} family={row['family']} hp={row['hp']}")
                for row in roster.conflicts:
                    print(f"  = {row['id']} conflict ({','.join(row['kinds'])})")
                for row in roster.unresolved:
                    print(f"  ? {row['id']} unresolved: {row['reason']}")
            return 0
        roster = write_outputs(content_path=args.zombies, artifact_path=args.json, **kwargs)
        print(summarize(roster))
        print(f"wrote {args.json} and {args.zombies}")
        return 0
    except InputError as exc:
        print(f"zombie-roster: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
