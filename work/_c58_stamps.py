# -*- coding: utf-8 -*-
"""C58: make artifact stamps content-addressed instead of mtime/wall-clock.

Before: `generatedAt` was the newest mtime among the source packages (rewards.py) or the
sheet mtime (spawn_offsets.py), `world_gates.generated` the WorldData mtime. Re-extracting
the same OBB -- which we just did for 460.9 -- changes every mtime, so three artifacts churn
even though their inputs are byte-identical. After: a short sha256 of the same inputs.
"""
from __future__ import annotations

import io
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def patch(rel: str, old: str, new: str) -> None:
    p = ROOT / rel
    text = io.open(p, encoding="utf-8").read()
    if new in text:
        print("skip", rel)
        return
    assert old in text, (rel, old[:60])
    io.open(p, "w", encoding="utf-8", newline="\n").write(text.replace(old, new, 1))
    print("patched", rel)


def ensure_import(rel: str) -> None:
    p = ROOT / rel
    text = io.open(p, encoding="utf-8").read()
    if "\nimport hashlib" in text:
        print("import ok", rel)
        return
    marker = "\nimport json"
    assert marker in text, rel
    io.open(p, "w", encoding="utf-8", newline="\n").write(text.replace(marker, "\nimport hashlib" + marker, 1))
    print("import added", rel)


# ---- rewards.py -------------------------------------------------------------
ensure_import("tools/contentc/rewards.py")
patch(
    "tools/contentc/rewards.py",
    '''def generated_stamp(obb: Path) -> str:
    """Newest mtime among the packages we read — not `now()`, so runs stay byte-identical."""

    stamps = []
    for name in (LOOT_PKG, PRESENT_PKG, PRESENT_TYPE_PKG, COLLECTABLE_PKG, AWARD_PKG,
                 RIFT_CLEAR_PKG, RIFT_BOSS_PKG, GAME_PROPS_PKG, WORLD_DATA_PKG, PINATA_PKG):
        path = obb / name
        if path.exists():
            stamps.append(path.stat().st_mtime)''',
    '''def generated_stamp(obb: Path) -> str:
    """Content stamp of the packages we read — never the clock, never the mtime.

    C58: an mtime stamp churned the artifact whenever the same OBB was re-extracted (we do
    that on every version bump). Hashing the inputs keeps two runs byte-identical *and*
    stable across machines, while still recording exactly which revision produced it.
    """

    digest = hashlib.sha256()
    stamps = []
    for name in (LOOT_PKG, PRESENT_PKG, PRESENT_TYPE_PKG, COLLECTABLE_PKG, AWARD_PKG,
                 RIFT_CLEAR_PKG, RIFT_BOSS_PKG, GAME_PROPS_PKG, WORLD_DATA_PKG, PINATA_PKG):
        path = obb / name
        if path.exists():
            digest.update(name.encode("utf-8"))
            digest.update(path.read_bytes())''',
)

# The old body ended by formatting `stamps`; find and replace that tail.
p = ROOT / "tools/contentc/rewards.py"
text = io.open(p, encoding="utf-8").read()
old_tail = '''        stamps.append(path.stat().st_mtime)'''
if old_tail in text:
    print("note: old append line still present, inspect manually")
io.open(p, "w", encoding="utf-8", newline="\n").write(text)

# ---- spawn_offsets.py ------------------------------------------------------
ensure_import("tools/contentc/spawn_offsets.py")
patch(
    "tools/contentc/spawn_offsets.py",
    '''def generated_stamp(source: Path) -> str:
    stamp = datetime.fromtimestamp(source.stat().st_mtime, tz=timezone.utc)
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")''',
    '''def generated_stamp(source: Path) -> str:
    """Content stamp (C58): the sheet's bytes, not its mtime.

    The mtime changed every time we re-extracted the same OBB, which churned this artifact
    for no reason. `sha256:<16 hex>` is stable across machines and still identifies the input.
    """

    return "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()[:16]''',
)
patch(
    "tools/contentc/spawn_offsets.py",
    'add("产物：`native/generated/spawn_offsets.json`（`generatedAt` = 源表 mtime 的 UTC 时间 `%s`，"',
    'add("产物：`native/generated/spawn_offsets.json`（`generatedAt` = 源表内容的 sha256 短戳 `%s`，"',
)

# ---- worlds.py -------------------------------------------------------------
ensure_import("tools/contentc/worlds.py")
patch(
    "tools/contentc/worlds.py",
    '''def gate_timestamp(obb_dir: Path) -> str:
    """UTC ISO8601 stamp derived from the sheet mtime (never the wall clock).

    A wall-clock stamp would make two runs differ; the sheet mtime only changes
    when the input changes, so the export stays byte-identical between runs while
    still recording which revision of WorldData it came from.
    """
    mtime = _world_data_path(obb_dir).stat().st_mtime
    return datetime.fromtimestamp(mtime, timezone.utc).isoformat()''',
    '''def gate_stamp(obb_dir: Path) -> str:
    """Content stamp of WorldData (C58): `sha256:<16 hex>`, never the clock or the mtime.

    An mtime stamp looked revision-accurate but changed on every re-extraction of the same
    OBB (each version bump re-extracts), so the export churned while its input was identical.
    """
    return "sha256:" + hashlib.sha256(_world_data_path(obb_dir).read_bytes()).hexdigest()[:16]''',
)
patch("tools/contentc/worlds.py", '"generated": generated or gate_timestamp(obb_dir),',
      '"generated": generated or gate_stamp(obb_dir),')

# ---- tests -----------------------------------------------------------------
patch(
    "tools/tests/test_spawn_offsets.py",
    """        # generatedAt is the sheet's mtime, so two runs cannot disagree
        self.assertRegex(self.table["generatedAt"], r"^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$")""",
    """        # C58: generatedAt is a content stamp, so re-extracting the same OBB cannot churn it
        self.assertRegex(self.table["generatedAt"], r"^sha256:[0-9a-f]{16}$")
        self.assertEqual(self.table["generatedAt"], spawn_offsets.generated_stamp(SHEET))""",
)
patch(
    "tools/tests/test_worlds.py",
    """        stamp = datetime.fromisoformat(self.payload["generated"])
        self.assertIsNotNone(stamp.tzinfo)
        self.assertEqual(stamp.utcoffset().total_seconds(), 0)
        self.assertEqual(self.payload["generated"], worlds.gate_timestamp(OBB))""",
    """        self.assertRegex(self.payload["generated"], r"^sha256:[0-9a-f]{16}$")
        self.assertEqual(self.payload["generated"], worlds.gate_stamp(OBB))""",
)
print("done")
