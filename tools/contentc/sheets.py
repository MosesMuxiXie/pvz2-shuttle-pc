"""Property-sheet access for the original OBB tables.

An OBB property sheet file is `{"version": n, "objects": [{"objclass": ..., "aliases": [...], "objdata": {...}}, ...]}`
plus free-form `#comment` keys that must be ignored rather than parsed.

Objects are addressed by *alias*; the game's own references use RTIDs of the form
`RTID(Name@Sheet)` — see `rtid.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

# Sheet suffix used in RTIDs -> file name. Only sheets we actually consume are
# listed; anything else shows up in `load_sheets(...).unmapped` so the gap stays
# visible instead of silently dropping references.
SHEET_FILES: dict[str, str] = {
    "PlantProperties": "pkg_2073_PlantPropertySheet.json",
    "PlantTypes": "pkg_2074_PlantType.json",
    "PlantAlmanac": "pkg_2067_PlantAlmanacData.json",
    "PlantLevelStats": "pkg_2069_PlantLevelStats.json",
    "ProjectileTypes": "pkg_2082_ProjectilePropertySheet.json",
    "Fusions": "pkg_2083_PlantFusionConfig.json",
    "ZombieProperties": "pkg_2112_ZombiePropertySheet.json",
    "ZombieTypes": "pkg_2115_ZombieType.json",
    "ZombieActions": "pkg_2111_ZombieWalkActionDefinition.json",
    "WorldData": "pkg_2107_WorldData.json",
    "ArmorTypes": "pkg_0002_ArmorPropertySheetUtils.json",
    "GridItemTypes": "pkg_0024_GridItemPropertySheet.json",
}

# RTIDs such as `BoostFirstStrike@PropertySheets` name a sheet that does not exist
# as its own file; the game resolves them inside the aggregate sheet. They are kept
# in a fallback index so lookups still succeed when the alias is unique.
AGGREGATE_SHEETS = {"PropertySheets"}


def normalize_sheet(sheet: str | None) -> str | None:
    """Canonical sheet key.

    The tables use three spellings for "this aggregate sheet": no suffix, `"."`,
    and a `$`-prefixed name (`$ZombieProperties`). Normalising here keeps every
    lookup path identical instead of failing on a spelling variant.
    """
    if sheet is None:
        return None
    cleaned = sheet.strip()
    while cleaned.startswith("$"):
        cleaned = cleaned[1:].strip()
    if cleaned in ("", ".", "PropertySheets"):
        return None
    return cleaned



def load_sheet(path: Path) -> dict:
    """Load one sheet file, tolerating a BOM and ignoring comment-only keys."""
    with path.open(encoding="utf-8-sig") as handle:
        doc = json.load(handle)
    if not isinstance(doc, dict):
        raise ValueError(f"{path.name}: sheet root is {type(doc).__name__}, expected object")
    return doc


def iter_objects(doc: dict) -> Iterator[dict]:
    """Yield every object that carries an objdata mapping."""
    objects = doc.get("objects")
    if not isinstance(objects, list):
        return
    for obj in objects:
        if isinstance(obj, dict) and isinstance(obj.get("objdata"), dict):
            yield obj


def aliases(obj: dict) -> list[str]:
    raw = obj.get("aliases")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [a for a in raw if isinstance(a, str)]
    return []


class SheetIndex:
    """Alias lookup for one sheet, with duplicates reported instead of hidden."""

    def __init__(self, name: str, objects: list[dict]):
        self.name = name
        self.objects = objects
        self._by_alias: dict[str, list[dict]] = {}
        for obj in objects:
            for alias in aliases(obj):
                self._by_alias.setdefault(alias, []).append(obj)

    def __len__(self) -> int:
        return len(self.objects)

    def resolve(self, name: str) -> dict | None:
        hits = self._by_alias.get(name)
        return hits[0] if hits else None

    def resolve_all(self, name: str) -> list[dict]:
        return list(self._by_alias.get(name, ()))

    def duplicates(self) -> dict[str, int]:
        return {alias: len(objs) for alias, objs in self._by_alias.items() if len(objs) > 1}

    def names(self) -> set[str]:
        return set(self._by_alias)


class Sheets:
    """Every sheet we could load, addressed by RTID sheet suffix."""

    def __init__(self, indexes: dict[str, SheetIndex], unmapped: dict[str, str]):
        self.indexes = indexes
        self.unmapped = unmapped
        self.aggregate = SheetIndex("PropertySheets", [o for i in indexes.values() for o in i.objects])

    def get(self, name: str) -> SheetIndex | None:
        return self.indexes.get(name)

    def resolve(self, name: str, sheet: str | None) -> dict | None:
        key = normalize_sheet(sheet)
        if key is None:
            return self.aggregate.resolve(name)
        index = self.indexes.get(key)
        if index is None:
            return None
        return index.resolve(name)

    def duplicates(self) -> dict[str, dict[str, int]]:
        return {name: index.duplicates() for name, index in self.indexes.items() if index.duplicates()}


def load_sheets(obb_dir: Path) -> Sheets:
    """Load every mapped sheet present in `obb_dir`; missing files are reported."""
    indexes: dict[str, SheetIndex] = {}
    unmapped: dict[str, str] = {}
    for sheet_name, file_name in SHEET_FILES.items():
        path = obb_dir / file_name
        if not path.is_file():
            unmapped[sheet_name] = f"missing file {file_name}"
            continue
        doc = load_sheet(path)
        indexes[sheet_name] = SheetIndex(sheet_name, list(iter_objects(doc)))
    return Sheets(indexes, unmapped)
