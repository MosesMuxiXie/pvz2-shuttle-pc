"""Serialise the content pack deterministically."""

from __future__ import annotations

import json
from pathlib import Path


def dumps(payload) -> str:
    """Stable JSON: sorted keys, one-space indent, LF, trailing newline."""
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def write_text(path: Path, text: str) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.encode("utf-8")
    path.write_bytes(data)
    return data


def write_pack(path: Path, pack: dict) -> bytes:
    return write_text(path, dumps(pack))


def coverage_of(pack: dict) -> dict:
    """Everything about the pack except the records themselves."""
    return {key: value for key, value in pack.items() if key not in ("plants", "zombies")}


def write_coverage(path: Path, pack: dict) -> bytes:
    return write_text(path, dumps(coverage_of(pack)))
