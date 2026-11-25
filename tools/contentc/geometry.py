"""Derive the real board geometry (rows x columns) of every client world.

`content/levels/*.json` carries no board dimensions, so the C++ core currently
assumes a 5x9 lawn everywhere. The original sheets have no `rows`/`cols` field
either: `WorldData` only describes the world map, all 302 `BoardGridMapProps`
are 5x9 mould masks, and `*StageProperties` only carries decoration. The
footprint is still recoverable from level-level grid coordinates:

* A module that tiles the whole lawn states the lawn. The six-lane family does
  exactly that: `InitialGridItemPlacements` of the six-lane module covers 54
  cells over `GridX` 0..8 and `GridY` 0..5, i.e. a full 6x9 rectangle. That is
  the only place in the sheets where a rectangle bigger than the 5x9 baseline
  can be measured at all, and it is what makes the six-lane worlds six rows.
* `StageModule` groups levels into stages, which is the only reliable
  level -> world bridge (`LevelDefinition` carries no level id). The six-lane
  stages are `SixLanePoolStage` / `SixLaneFogStage` (StagePrefix `beach`) and
  `SixLaneStage` / `SixLaneHonkaiStage` (StagePrefix `modern`).
* Every other placement stays inside the cell box `GridX` 0..8 / `GridY` 0..4,
  which is why the baseline is 5 rows by 9 columns. Coordinates outside that box
  (`GridX` 9, `GridY` 5 and up, and blatant sentinels such as `GridX` 150) are
  off-board spawn/walk-off markers, not cells - they are counted per world as
  `sentinels` instead of being read as a bigger lawn.

Evidence is applied per world in a fixed order, strongest first, and every entry
records which rule fired:

1. ``full-lawn rectangle`` - an exact, fully covered rectangle measured inside
   one of the world's own levels (rows *and* columns measured);
2. ``SixLaneModule`` - levels of that world reference the six-lane module whose
   placement list tiles the 6x9 lawn;
3. ``six-lane stage`` - the world owns a ``SixLane*`` stage;
4. ``level-grid ceiling`` - the world's levels exist and stay inside the 5x9
   cell box (world-level evidence, reported with the measured ceiling);
5. ``fallback=5x9-default`` - no level or stage in the sheets at all. Counted and
   reported, never silently invented.

Usage:
    python tools/contentc/geometry.py                       # writes native/generated/board_sizes.json
    python tools/contentc/geometry.py --out build/boards.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from contentc import worlds  # noqa: E402

REPO = worlds.REPO
DEFAULT_CONTENT = worlds.DEFAULT_CONTENT
DEFAULT_OBB = worlds.DEFAULT_OBB
DEFAULT_OUT = REPO / "native" / "generated" / "board_sizes.json"

#: The baseline lawn. All 302 `BoardGridMapProps` moulds are 5 rows x 9 columns,
#: and every non-six-lane placement in the sheets stays inside this cell box.
BASELINE_ROWS = 5
BASELINE_COLS = 9
#: A full-lawn tiling smaller than a 5x9 lawn is not a board, it is a patch.
FULL_LAWN_MIN_CELLS = BASELINE_ROWS * BASELINE_COLS
#: The six-lane lawn measured in the sheets: `GridX` 0..8 by `GridY` 0..5.
SIXLANE_ROWS = 6
SIXLANE_COLS = 9

SIXLANE_MODULE = "SixLaneModule"

#: Stage name prefix -> client world id, first match wins. Order matters:
#: `SixLanePool`/`SixLaneFog` are beach stages before `SixLane` is the modern
#: family, and `PvZ2CRoof` is a front-lawn roof before `Roof` is.
STAGE_WORLDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("frontyard", ("PvZ2CRoof", "FrontLawn", "Roof", "Day", "Night", "Tutorial")),
    ("egypt", ("Egypt",)),
    ("pirate", ("Pirate",)),
    ("cowboy", ("West",)),
    ("future", ("Future",)),
    ("dark", ("Dark",)),
    ("beach", ("SixLanePool", "SixLaneFog", "Beach", "Pool", "Fog")),
    ("lostcity", ("LostCity",)),
    ("iceage", ("Iceage",)),
    ("kongfu", ("Kongfu",)),
    ("dino", ("Dino",)),
    ("eighties", ("Eighties",)),
    ("modern", ("Modern", "SixLane")),
    ("sky", ("SkyCity",)),
    ("chinesegarden", ("ChineseGarden",)),
    ("heian", ("Heian",)),
    ("fairy", ("Fairy",)),
    ("mausoleum", ("Mausoleum",)),
    ("steam", ("Steam",)),
    ("losantosvice", ("GTA",)),
    ("lunarrainbowmarket", ("MarketNights",)),
    ("renai", ("Renai",)),
    ("carnival", ("Carnival",)),
    ("plantagenet", ("Plantagenet",)),
)

RTID_RE = re.compile(r"RTID\(([^)]*)\)")


@dataclass(frozen=True)
class LevelFacts:
    """One `LevelDefinition`, plus the grid its package measures."""

    package: str
    stage: str
    sixlane: bool
    #: Highest cell coordinate seen on that level (-1 when nothing was placed).
    cell_x: int
    cell_y: int
    #: Placements outside the 5x9 cell box: spawn/walk-off markers, not cells.
    sentinels: int
    #: rows, cols, cells of a fully covered lawn rectangle, when one was found.
    rect: tuple[int, int, int] | None


@dataclass
class Notes:
    """What the run could not explain, so the report never overstates itself."""

    levels: int = 0
    unmapped: Counter = field(default_factory=Counter)


def _rtid_name(value: object) -> str | None:
    """`"RTID(EgyptStage@LevelModules)"` -> `"EgyptStage"`."""
    if not isinstance(value, str) or not value.strip():
        return None
    match = RTID_RE.search(value)
    text = match.group(1) if match else value
    name = text.split("@", 1)[0].strip()
    return name or None


def _strings(value: object, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, list):
        for item in value:
            _strings(item, out)
    elif isinstance(value, dict):
        for item in value.values():
            _strings(item, out)


def _grid_points(value: object, out: list[tuple[int, int]]) -> None:
    if isinstance(value, dict):
        if "GridX" in value and "GridY" in value:
            try:
                out.append((int(value["GridX"]), int(value["GridY"])))
            except (TypeError, ValueError):
                pass
        for item in value.values():
            _grid_points(item, out)
    elif isinstance(value, list):
        for item in value:
            _grid_points(item, out)


def _full_lawn_rect(points: list[tuple[int, int]]) -> tuple[int, int, int] | None:
    """A placement list that tiles a whole lawn states that lawn's size."""
    cells = {
        (x, y)
        for x, y in points
        if 0 <= x < BASELINE_COLS and 0 <= y < SIXLANE_ROWS
    }
    if not cells:
        return None
    cols = max(x for x, _ in cells) + 1
    rows = max(y for _, y in cells) + 1
    if cols < SIXLANE_COLS or rows * cols < FULL_LAWN_MIN_CELLS:
        return None
    if len(cells) != rows * cols:
        return None
    return rows, cols, len(cells)


def load_levels(obb_dir: Path) -> list[LevelFacts]:
    """Every `LevelDefinition` in the sheets, with the grid of its package.

    A level package embeds the module objects it references, so the placements
    found next to a level belong to that level.
    """
    facts: list[LevelFacts] = []
    for path in sorted(obb_dir.glob("pkg_*_LevelDefinition.json")):
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        objects = [obj for obj in doc.get("objects") or [] if isinstance(obj, dict)]

        package_points: list[tuple[int, int]] = []
        rect: tuple[int, int, int] | None = None
        for obj in objects:
            data = obj.get("objdata")
            if not isinstance(data, dict):
                continue
            points: list[tuple[int, int]] = []
            _grid_points(data, points)
            if not points:
                continue
            package_points.extend(points)
            candidate = _full_lawn_rect(points)
            if candidate is not None and (rect is None or candidate[2] > rect[2]):
                rect = candidate

        cells = [
            (x, y)
            for x, y in package_points
            if 0 <= x < BASELINE_COLS and 0 <= y < BASELINE_ROWS
        ]
        cell_x = max((x for x, _ in cells), default=-1)
        cell_y = max((y for _, y in cells), default=-1)
        sentinels = len(package_points) - len(cells)

        for obj in objects:
            data = obj.get("objdata") or {}
            stage = _rtid_name(data.get("StageModule"))
            if not stage:
                continue
            modules: list[str] = []
            _strings(data.get("Modules"), modules)
            facts.append(
                LevelFacts(
                    package=path.stem,
                    stage=stage,
                    sixlane=any(SIXLANE_MODULE in item for item in modules),
                    cell_x=cell_x,
                    cell_y=cell_y,
                    sentinels=sentinels,
                    rect=rect,
                )
            )
    return facts


def world_of_stage(stage: str) -> str | None:
    for world_id, prefixes in STAGE_WORLDS:
        for prefix in prefixes:
            if stage.startswith(prefix):
                return world_id
    return None


def _stage_names(levels: list[LevelFacts]) -> str:
    names = sorted({level.stage for level in levels})
    head = ",".join(names[:4])
    if len(names) > 4:
        head += ",+%d" % (len(names) - 4)
    return head


def decide(levels: list[LevelFacts]) -> tuple[int, int, str]:
    """Rows, columns and the evidence string for one world."""
    if not levels:
        return (
            BASELINE_ROWS,
            BASELINE_COLS,
            "fallback=5x9-default (no level or stage in the sheets)",
        )

    rectangles = sorted(
        (level for level in levels if level.rect is not None),
        key=lambda level: (-level.rect[2], level.package),  # type: ignore[index]
    )
    if rectangles:
        best = rectangles[0]
        rows, cols, cells = best.rect  # type: ignore[misc]
        return (
            rows,
            cols,
            "level=%s stage=%s tiles the whole lawn: %d cells = %dx%d"
            % (best.package, best.stage, cells, rows, cols),
        )

    sixlane = [level for level in levels if level.sixlane]
    if sixlane:
        return (
            SIXLANE_ROWS,
            SIXLANE_COLS,
            "level=%s stage=%s: %d of %d levels place %s, whose "
            "InitialGridItemPlacements tile GridX 0..%d by GridY 0..%d = %dx%d"
            % (
                sixlane[0].package,
                sixlane[0].stage,
                len(sixlane),
                len(levels),
                SIXLANE_MODULE,
                SIXLANE_COLS - 1,
                SIXLANE_ROWS - 1,
                SIXLANE_ROWS,
                SIXLANE_COLS,
            ),
        )

    sixlane_stage = [level for level in levels if level.stage.startswith("SixLane")]
    if sixlane_stage:
        return (
            SIXLANE_ROWS,
            SIXLANE_COLS,
            "stage=%s is a six-lane stage family (%d levels) = %dx%d"
            % (sixlane_stage[0].stage, len(sixlane_stage), SIXLANE_ROWS, SIXLANE_COLS),
        )

    placed = [level for level in levels if level.cell_x >= 0]
    sentinels = sum(level.sentinels for level in levels)
    if not placed:
        return (
            BASELINE_ROWS,
            BASELINE_COLS,
            "stage=%s levels=%d: no grid placements in the sheets, "
            "5x9 baseline (BoardGridMapProps mould)"
            % (_stage_names(levels), len(levels)),
        )
    return (
        BASELINE_ROWS,
        BASELINE_COLS,
        "stage=%s levels=%d: level grid stays inside GridX 0..%d by GridY 0..%d "
        "= %dx%d (%d off-board sentinels ignored)"
        % (
            _stage_names(levels),
            len(levels),
            max(level.cell_x for level in placed),
            max(level.cell_y for level in placed),
            BASELINE_ROWS,
            BASELINE_COLS,
            sentinels,
        ),
    )


def build(
    obb_dir: Path = DEFAULT_OBB, content_dir: Path = DEFAULT_CONTENT
) -> tuple[dict, Notes]:
    """The board-size table ``{world: {rows, cols, source}}`` and its notes."""
    content_worlds = worlds.load_content_worlds(content_dir)
    obb_worlds = {world.name: world for world in worlds.load_obb_worlds(obb_dir)}
    reverse_aliases = {alias: name for name, alias in worlds.ALIASES.items()}

    levels = load_levels(obb_dir)
    notes = Notes(levels=len(levels))
    by_world: dict[str, list[LevelFacts]] = {}
    for level in levels:
        world_id = world_of_stage(level.stage)
        if world_id is None:
            notes.unmapped[level.stage] += 1
            continue
        by_world.setdefault(world_id, []).append(level)

    board_sizes: dict[str, dict] = {}
    for world in content_worlds:
        rows, cols, source = decide(by_world.get(world.id, []))
        obb_name = reverse_aliases.get(world.id, world.id)
        if obb_name in obb_worlds:
            presence = "obb=%s" % obb_name
        else:
            # future/iceage/renai are client-side worlds without a WorldData row;
            # their stages still exist, so stage evidence remains available.
            presence = "obb=absent"
        board_sizes[world.id] = {
            "rows": rows,
            "cols": cols,
            "source": "%s %s" % (presence, source),
        }
    return board_sizes, notes


def render(board_sizes: dict) -> str:
    return json.dumps(board_sizes, ensure_ascii=False, indent=2) + "\n"


def report(board_sizes: dict, notes: Notes) -> str:
    lines = ["board sizes derived from the original sheets", ""]
    fallbacks: list[str] = []
    kinds: Counter = Counter()
    for world_id, entry in board_sizes.items():
        lines.append(
            "  %-20s %dx%d  %s"
            % (world_id, entry["rows"], entry["cols"], entry["source"])
        )
        source = entry["source"]
        if "fallback=" in source:
            kinds["fallback"] += 1
            fallbacks.append(world_id)
        elif "tiles the whole lawn" in source:
            kinds["full-lawn rectangle (level)"] += 1
        elif SIXLANE_MODULE in source:
            kinds["SixLaneModule (level)"] += 1
        elif "six-lane stage family" in source:
            kinds["six-lane stage (world)"] += 1
        elif "no grid placements" in source:
            kinds["5x9 baseline, no placements"] += 1
        else:
            kinds["level-grid ceiling (world)"] += 1
    lines.append("")
    for kind, count in kinds.most_common():
        lines.append("  evidence %-32s %d" % (kind, count))
    lines.append("")
    lines.append(
        "  worlds=%d levels=%d fallback=%s"
        % (len(board_sizes), notes.levels, ",".join(fallbacks) or "none")
    )
    if notes.unmapped:
        lines.append(
            "  stages with no client world (%d stages, %d levels): %s"
            % (
                len(notes.unmapped),
                sum(notes.unmapped.values()),
                ", ".join("%s=%d" % item for item in notes.unmapped.most_common(6)),
            )
        )
    return "\n".join(lines) + "\n"


def write(board_sizes: dict, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(board_sizes), encoding="utf-8", newline="\n")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--obb", type=Path, default=DEFAULT_OBB, help="extracted sheet folder"
    )
    parser.add_argument(
        "--content", type=Path, default=DEFAULT_CONTENT, help="client content folder"
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output json")
    args = parser.parse_args(argv)

    board_sizes, notes = build(args.obb, args.content)
    path = write(board_sizes, args.out)
    sys.stdout.write(report(board_sizes, notes))
    sys.stdout.write("\nwrote %s\n" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
