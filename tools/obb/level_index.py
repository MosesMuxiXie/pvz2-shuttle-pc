"""Index archive paths, map events, and scoped references without converting levels.

The directory decoder is specific to the SHUTTLE v4 PACKAGES filename table.
JSON packages must come from split_packages.py's ascending stream-offset order.
Only Zstandard-compressed archives need the optional ``zstandard`` dependency.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib


@dataclass(frozen=True)
class Entry:
    path: str
    offset: int
    size: int
    image: bool = False


def decode_directory(table: bytes, data_size: int) -> list[Entry]:
    """Decode SHUTTLE's word trie; branch addresses are word indices.

    Bits 1..7 hold character+1. Bit 0 is the branch address's low bit;
    bits 8..31 hold its remaining bits. A branch keeps the prefix *before*
    that character, including when its target is an odd word boundary.
    """
    if len(table) % 4:
        raise ValueError("filename table is not word aligned")
    words = struct.unpack(f"<{len(table) // 4}I", table)
    branches: dict[int, str] = {}
    entries = []
    cursor = 0
    while cursor < len(words):
        branches = {target: prefix for target, prefix in branches.items() if target >= cursor}
        name = branches.pop(cursor, "")
        while True:
            if cursor >= len(words):
                raise ValueError("unterminated filename")
            word = words[cursor]
            cursor += 1
            char = ((word & 255) >> 1) - 1
            target = ((word >> 8) << 1) | (word & 1)
            if target:
                if not cursor <= target < len(words):
                    raise ValueError("filename branch outside remaining table")
                branches[target] = name
            if char == 0:
                break
            if char < 0:
                raise ValueError("invalid filename character")
            name += chr(char)
        if cursor + 3 > len(words):
            raise ValueError("truncated directory entry")
        image, offset, size = words[cursor:cursor + 3]
        cursor += 3
        if image not in (0, 1):
            raise ValueError("unknown directory entry type")
        if image:
            cursor += 5
        if cursor > len(words) or not name or (not image and offset + size > data_size):
            raise ValueError("directory entry outside decompressed stream")
        entries.append(Entry(name.replace("\\", "/"), offset, size, bool(image)))
    if len({entry.path.casefold() for entry in entries}) != len(entries):
        raise ValueError("duplicate archive path")
    return sorted(entries, key=lambda entry: entry.offset)


def alias_index(objects: list[dict]) -> dict[str, list[dict]]:
    aliases = defaultdict(list)
    for index, obj in enumerate(objects):
        for alias in obj.get("aliases", []):
            aliases[alias].append({"index": index, "class": obj.get("objclass")})
    return dict(aliases)


def walk_references(value, pointer=""):
    """Yield RTID strings with JSON Pointers, including nested and external refs."""
    if isinstance(value, dict):
        for key, child in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            yield from walk_references(child, pointer + "/" + escaped)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_references(child, pointer + "/" + str(index))
    elif isinstance(value, str) and value.startswith("RTID("):
        yield pointer, value


def resolve_reference(reference, pointer, aliases, shared_aliases):
    row = {"pointer": pointer, "reference": reference, "targets": []}
    if reference == "RTID(0)":
        return {**row, "status": "null"}
    match = re.fullmatch(r"RTID\(([^@()]*)@([^()]*)\)", reference)
    if not match:
        return {**row, "status": "malformed"}
    alias, scope = match.groups()
    row.update(alias=alias, scope=scope)
    if scope in ("CurrentLevel", "."):
        targets = aliases.get(alias, [])
    elif scope == "LevelModules":
        targets = shared_aliases.get(alias, [])
    else:
        return {**row, "status": "unindexed_scope"}
    row["targets"] = targets
    row["status"] = "resolved" if len(targets) == 1 else "ambiguous" if targets else "missing"
    return row


def level_references(objects, definition_index, shared_aliases):
    """Resolve Modules and retain every RTID, without crossing namespace scope."""
    aliases = alias_index(objects)
    refs = [resolve_reference(ref, pointer, aliases, shared_aliases)
            for pointer, ref in walk_references(objects, "/objects")]
    prefix = f"/objects/{definition_index}/objdata/Modules/"
    modules = [ref for ref in refs if ref["pointer"].startswith(prefix)]
    return modules, refs


def world_entries(docs, level_keys):
    """Join the complete relative level key; never fall back to a basename."""
    links = defaultdict(list)
    unmatched = []
    for package, path, doc in docs:
        for object_index, obj in enumerate(doc.get("objects", [])):
            if obj.get("objclass") != "WorldData":
                continue
            data = obj.get("objdata", {})
            for event_index, event in enumerate(data.get("m_eventList", [])):
                if event.get("m_eventType") != "level":
                    continue
                literal = event.get("m_dataString", "")
                key = literal.replace("\\", "/").casefold() if isinstance(literal, str) else ""
                row = {"package": package, "path": path,
                       "pointer": f"/objects/{object_index}/objdata/m_eventList/{event_index}",
                       "world": data.get("m_worldName"), "event": event.get("m_name"),
                       "level_key": literal, "event_data": event}
                target = level_keys.get(key)
                if target:
                    links[target].append(row)
                else:
                    unmatched.append(row)
    return dict(links), unmatched


MECHANICS = {"conveyor": "Conveyor", "rail": "Railcart", "tide": "Tide",
             "vase": "VaseBreaker"}


def build_index(docs, legacy_rows=()):
    """Build evidence from exact paths, retaining unreferenced local definitions."""
    shared_aliases = defaultdict(list)
    for package, path, doc in docs:
        if path.casefold() != "packages/levelmodules.rton":
            continue
        for alias, targets in alias_index(doc.get("objects", [])).items():
            shared_aliases[alias].extend({**target, "package": package, "path": path}
                                        for target in targets)
    levels = []
    for package, path, doc in docs:
        objects = doc.get("objects", [])
        for definition_index, definition in enumerate(objects):
            if definition.get("objclass") != "LevelDefinition":
                continue
            if not path.casefold().startswith("packages/levels/") or not path.casefold().endswith(".rton"):
                raise ValueError(f"LevelDefinition outside LEVELS: {path}")
            modules, refs = level_references(objects, definition_index, shared_aliases)
            data = definition.get("objdata", {})
            mechanics = {key: [] for key in MECHANICS}
            direct_indices = {target["index"] for ref in modules if ref["status"] == "resolved"
                              and ref.get("scope") in ("CurrentLevel", ".")
                              for target in ref["targets"]}
            for index, obj in enumerate(objects):
                for key, needle in MECHANICS.items():
                    if needle.casefold() in str(obj.get("objclass", "")).casefold():
                        mechanics[key].append({"index": index, "class": obj.get("objclass"),
                            "aliases": obj.get("aliases", []), "properties": obj.get("objdata", {}),
                            "evidence": "direct_module" if index in direct_indices else "local_definition"})
            levels.append({"package": package, "path": path,
                           "level_key": path[len("PACKAGES/LEVELS/"):-5].casefold(),
                           "definition_index": definition_index, "comment": doc.get("#comment"),
                           "name": data.get("Name"), "level_number": data.get("LevelNumber"),
                           "stage_reference": data.get("StageModule"),
                           "object_classes": dict(sorted(Counter(o.get("objclass", "<none>")
                                                                   for o in objects).items())),
                           "modules": modules, "references": refs, "mechanics": mechanics})
    keys = {level["level_key"]: level["package"] for level in levels}
    if len(keys) != len(levels):
        raise ValueError("duplicate level keys or multiple definitions in one package")
    links, unmatched = world_entries(docs, keys)
    by_package = {level["package"]: level for level in levels}
    for level in levels:
        level["world_events"] = links.get(level["package"], [])
    legacy = []
    for old in legacy_rows:
        extra = old.get("extra", {})
        package = extra.get("package")
        target = by_package.get(package)
        legacy.append({"file": old["file"], "id": old.get("id"), "world": old.get("world"),
                       "package": package, "source": extra.get("source"),
                       "status": "resolved_package" if target else "missing_package" if package else "no_package",
                       "path": target["path"] if target else None,
                       "world_events": target["world_events"] if target else []})
    unresolved = [{"package": level["package"], "path": level["path"], **ref}
                  for level in levels for ref in level["references"]
                  if ref["status"] not in ("resolved", "null")]
    summary = {"packages": len(docs), "levels": len(levels),
               "world_objects": sum(obj.get("objclass") == "WorldData" for _, _, doc in docs
                                    for obj in doc.get("objects", [])),
               "world_level_events_matched": sum(map(len, links.values())),
               "world_level_events_unmatched": len(unmatched), "levels_with_world_events": len(links),
               "reference_status": dict(Counter(ref["status"] for level in levels for ref in level["references"])),
               "module_status": dict(Counter(ref["status"] for level in levels for ref in level["modules"])),
               "mechanic_local_definitions": {key: sum(bool(level["mechanics"][key]) for level in levels)
                                               for key in MECHANICS},
               "legacy_links": dict(Counter(row["status"] for row in legacy)),
               "duplicate_shared_aliases": {alias: targets for alias, targets in shared_aliases.items()
                                            if len(targets) > 1}}
    return {"summary": summary, "levels": levels, "unmatched_world_events": unmatched,
            "unresolved_references": unresolved, "legacy_links": legacy}


def read_packages(obb: Path):
    """Read only the PACKAGES subgroup; validate ordinal joins against RTON starts."""
    with obb.open("rb") as stream:
        header = stream.read(112)
        if len(header) != 112 or header[:4] != b"1bsr":
            raise ValueError("expected an uncompressed 1bsr archive")
        words = struct.unpack("<28I", header)
        if words[1] != 4 or words[12] < 176:
            raise ValueError("expected RSB v4 subgroup records")
        stream.seek(words[11])
        groups = stream.read(words[10] * words[12])
        matches = []
        for index in range(words[10]):
            base = index * words[12]
            if groups[base:base + 128].rstrip(b"\0") == b"PACKAGES":
                matches.append((index, struct.unpack_from("<I", groups, base + 128)[0]))
        if len(matches) != 1:
            raise ValueError("archive must contain exactly one PACKAGES subgroup")
        subgroup_index, subgroup_offset = matches[0]
        stream.seek(subgroup_offset)
        subgroup = stream.read(92)
        if subgroup[:4] != b"pgsr":
            raise ValueError("PACKAGES is not pgsr")
        flags = struct.unpack_from("<I", subgroup, 16)[0]
        data_offset, compressed_size, data_size = struct.unpack_from("<III", subgroup, 24)
        table_size, table_offset = struct.unpack_from("<II", subgroup, 72)
        stream.seek(subgroup_offset + table_offset)
        table = stream.read(table_size)
        if len(table) != table_size:
            raise ValueError("truncated filename table")
        entries = decode_directory(table, data_size)
        stream.seek(subgroup_offset + data_offset)
        compressed = stream.read(compressed_size)
    if not flags & 2:
        raw = compressed
    elif compressed.startswith(b"\x28\xb5\x2f\xfd"):
        try:
            import zstandard
        except ImportError as exc:
            raise ValueError("Zstandard archive: run with `uv run --no-project --with zstandard python ...`") from exc
        raw = zstandard.ZstdDecompressor().decompress(compressed, max_output_size=data_size)
    else:
        raw = zlib.decompress(compressed)
    if len(raw) != data_size or any(e.image for e in entries):
        raise ValueError("PACKAGES data size mismatch or unexpected image entry")
    starts = [offset for offset in range(0, len(raw), 4096) if raw[offset:offset + 4] == b"RTON"]
    if [entry.offset for entry in entries] != starts:
        raise ValueError("directory offsets do not match split_packages.py's aligned RTON order")
    if any(not entry.path.casefold().endswith(".rton") for entry in entries):
        raise ValueError("PACKAGES contains a non-RTON entry")
    metadata = {"obb_name": obb.name, "obb_bytes": obb.stat().st_size,
                "subgroup_index": subgroup_index, "subgroup_offset": subgroup_offset,
                "directory_sha256": hashlib.sha256(table).hexdigest(),
                "decompressed_stream_sha256": hashlib.sha256(raw).hexdigest(),
                "decompressed_stream_bytes": len(raw), "aligned_rton_starts_verified": len(starts)}
    return entries, metadata


def load_documents(directory: Path, entries):
    files = {}
    for path in sorted(directory.glob("pkg_*.json")):
        match = re.fullmatch(r"(pkg_\d{4})_.+\.json", path.name)
        if not match or match[1] in files:
            raise ValueError(f"unexpected or duplicate package filename: {path.name}")
        files[match[1]] = path
    expected = {f"pkg_{index:04d}" for index in range(len(entries))}
    if set(files) != expected:
        raise ValueError(f"package ordinals do not match directory ({len(files)} JSON, {len(entries)} entries)")
    extraction = json.loads((directory / "_index.json").read_text(encoding="utf-8"))
    if extraction.get("fail") != 0 or extraction.get("blocks") != len(entries):
        raise ValueError("extraction index has failures or a different block count")
    if {row.get("k") for row in extraction.get("items", [])} != set(range(len(entries))):
        raise ValueError("extraction index ordinals are incomplete")
    docs = []
    packages = []
    digest = hashlib.sha256()
    for index, entry in enumerate(entries):
        package = f"pkg_{index:04d}"
        path = files[package]
        raw = path.read_bytes()
        doc = json.loads(raw)
        digest.update(path.name.encode("utf-8") + b"\0" + raw + b"\0")
        docs.append((package, entry.path, doc))
        packages.append({"package": package, "json_file": path.name, "json_sha256": hashlib.sha256(raw).hexdigest(),
                         **asdict(entry)})
    return docs, packages, digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--obb", required=True, type=Path)
    parser.add_argument("--packages", required=True, type=Path, help="split_packages.py's JSON directory")
    parser.add_argument("--legacy-levels", type=Path, default=Path(__file__).resolve().parents[2] / "content/levels")
    parser.add_argument("--output", type=Path, default=Path("build/obb-index"))
    args = parser.parse_args()
    try:
        entries, provenance = read_packages(args.obb)
        docs, packages, doc_hash = load_documents(args.packages, entries)
        legacy = [{**json.loads(path.read_text(encoding="utf-8")), "file": path.name}
                  for path in sorted(args.legacy_levels.glob("*.json"))]
        result = build_index(docs, legacy)
    except (ValueError, OSError, struct.error, zlib.error) as exc:
        parser.exit(1, f"level_index: {exc}\n")
    result["packages"] = packages
    result["summary"].update(schema_version=1, evidence="static_archive_and_decoded_json",
        provenance={**provenance, "decoded_json_set_sha256": doc_hash},
        limitations=["Package join relies on split_packages.py's ascending aligned RTON order; verified against archive offsets.",
                     "Comments, stage names, and numeric LevelNumber are retained but never used as level identity.",
                     "Only CurrentLevel, '.', and LevelModules namespaces are resolved; other scopes remain unindexed.",
                     "Mechanics are local class definitions, with direct module membership marked; runtime activation is unverified.",
                     "WorldData joins require the complete level key; no basename or stage inference.",
                     "Legacy links preserve existing extra.package assignments, not gameplay fidelity or campaign order."])
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in result.items():
        (args.output / (name + ".json")).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
