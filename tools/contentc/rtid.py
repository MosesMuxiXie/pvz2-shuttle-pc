"""RTID parsing: `RTID(Name@Sheet)` is how the original game references another table entry.

A bare `RTID(0)` means "nothing" and is common in the sheets; callers must treat it as
absent rather than as a name to look up.
"""

from __future__ import annotations

_NOTHING = {"0", ""}


def parse_rtid(text: object) -> tuple[str, str | None] | None:
    """Split an RTID into (name, sheet). Returns None when `text` is not an RTID.

    `RTID(PeaDefault@ProjectileTypes)` -> ("PeaDefault", "ProjectileTypes")
    `RTID(0)`                          -> ("0", None)
    """
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped.startswith("RTID(") or not stripped.endswith(")"):
        return None
    inner = stripped[5:-1].strip()
    if "@" in inner:
        name, _, sheet = inner.partition("@")
        return name.strip(), sheet.strip() or None
    return inner, None


def is_nothing(name: str, sheet: str | None) -> bool:
    return sheet is None and name in _NOTHING


def format_rtid(name: str, sheet: str | None) -> str:
    return f"RTID({name}@{sheet})" if sheet else f"RTID({name})"
