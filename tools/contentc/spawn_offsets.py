"""Spawn offsets: pack `Actions[].SpawnOffset{x,y}` (px) -> cell units, plus the y axis.

Why this exists
---------------
`native/src/engine/action_runner.cpp` and `registry.cpp` read only `SpawnOffset.x`
and divide it by `kPixelsPerColumn = 60.0`; `SpawnOffset.y` is dropped entirely
(see the comment at `action_runner.cpp:85-87`).  Every shot and every sun therefore
leaves from the cell's centre line, so lobbed weapons and sun pickups have no height
difference.  This module turns the pack's raw pixel offsets into cell units on both
axes, with a traceable source per row, so the engine can add `yCols` to a spawn
position without re-deriving the scale.

Where the scale comes from (and what the repo does *not* have)
--------------------------------------------------------------
`docs/COMPLETENESS.md` does not contain a "100x116 px per cell" statement — a grep
over every markdown file in `docs/` for `116` next to a pixel/`×` token returns
nothing (`python tools/contentc/spawn_offsets.py --grep-cell` repeats the search).
The numbers are in the data, not the docs:

* `pkg_2073_PlantPropertySheet.json` gives every plant an `ArtCenter` and 379 of the
  398 objects have it.  The pivot is overwhelmingly `(99, 115)` (164 objects), then
  `(99, 116)` (38), `(97, 119)` (25) — i.e. the centre of a **100 x 116 px** cell.
  `pxPerColumn = 100`, `pxPerRow = 116` are read off that cluster (mode + 1 for the
  0-based pixel centre), and `scale.artCenter` records the pivot it came from.
* Independently, the engine's own fallback `kShotStartOffsetCols = 0.35`
  (`native/src/engine/tuning.hpp`) is exactly `35 / 100`, which is the peashooter's
  `SpawnOffset.x = 35` px — another sign that plant-space pixels belong to a 100 px
  column, not a 60 px one.
* `native/src/engine/action_runner.cpp:14` and `registry.cpp:27` use
  `kPixelsPerColumn = 60.0`.  That disagrees with the plant art cell by 100/60 =
  1.667x.  This table keeps both numbers visible (`scale.enginePxPerColumn`) and uses
  the art cell for the conversion, because that is the space `SpawnOffset` is written
  in; the report spells out the consequence for today's engine.

Sign convention
---------------
`SpawnOffset.y` is **negative upwards**: 481 of the 488 offsets with a numeric `y`
are <= 0, the median is -32 (the peashooter), the deepest are -600/-1000 for weapons
that drop in from above the board, and the seven positive rows are small (+14..+30)
muzzle offsets on vines/`XShot`.  So `yCols = yPx / 116` is a height **above** the
cell centre when negative; on screen (y grows down) that is `-yCols`.

Rows in the artifact
--------------------
One row per `Actions[i]` that carries a `SpawnOffset` with finite pixel values:

    {"plant": "<props alias>", "actionIndex": i, "kind": "shot|sun|plantfood|special|explode|manual|unknown",
     "xPx": int|float, "yPx": int|float, "xCols": float, "yCols": float,
     "source": "pkg_2073_PlantPropertySheet.json:<alias>.Actions[i].SpawnOffset"}

`xCols`/`yCols` are rounded to 4 decimals so the file is diffable.  Rows whose pixel
values are absurd (|v| >= 2000, e.g. `FlowerPotDefault` with `x = 10000`) are not
converted silently: they are counted in `counts.skippedOffsets` with the reason.

Commands
--------
    python tools/contentc/spawn_offsets.py             # write json + report
    python tools/contentc/spawn_offsets.py --check     # artifact self-consistent? (0/1)
    python tools/contentc/spawn_offsets.py --grep-cell # re-run the "100x116" doc search

Honest boundaries
-----------------
* 116 px/row is the *art cell height* read from the `ArtCenter` cluster, not a
  constant in the repo.  If the art atlas is ever rescaled, only `scale.pxPerRow`
  changes and every `yCols` follows.
* `SpawnOffset` on `special`/`explode`/`manual` actions is a trigger rect origin, not
  a muzzle point (see `action_runner.cpp:22`); those rows are kept and labelled by
  kind so a consumer does not treat them as projectile origins.
* The engine still divides `SpawnOffset.x` by 60.  This table does **not** change
  that (out of scope: `native/src/**`); it records the 100-vs-60 disagreement so the
  fix is a one-line decision instead of a re-derivation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from contentc import worlds  # noqa: E402

REPO = worlds.REPO
DEFAULT_OBB = worlds.DEFAULT_OBB
DEFAULT_PLANT_SHEET = "pkg_2073_PlantPropertySheet.json"
DEFAULT_OUT = REPO / "native" / "generated" / "spawn_offsets.json"
DEFAULT_REPORT = REPO / "docs" / "reviews" / "2026-11-24-spawn-offsets.md"

FORMAT = 1
GENERATED = "spawn-offsets-v1"

#: fallbacks if the sheet somehow has no usable `ArtCenter` cluster
PX_PER_COLUMN = 100.0
PX_PER_ROW = 116.0

#: the constant the engine uses today (`native/src/engine/action_runner.cpp:14`,
#: `native/src/engine/registry.cpp:27`) — kept for the report, not used to convert
ENGINE_PX_PER_COLUMN = 60.0

#: `native/src/engine/tuning.hpp` — equals the peashooter's 35 px / 100 px column
ENGINE_SHOT_X_COLS = 0.35

#: |pixel| at or above this is a sentinel/garbage offset, not a spawn point
OFFSET_LIMIT = 2000.0

#: pack action `Type` -> the row's `kind`
KIND_MAP = {
    "projectile": "shot",
    "sun": "sun",
    "plantfood": "plantfood",
    "special": "special",
    "explode": "explode",
    "manual": "manual",
}
KINDS = ("shot", "sun", "plantfood", "special", "explode", "manual", "unknown")

#: the three samples the report has to prove
SAMPLES = ("PeashooterDefault", "KernelpultDefault", "SunflowerDefault")

DOC_GLOB = "docs/**/*.md"
#: what `--grep-cell` looks for: a pixel cell size in prose
CELL_PATTERN = re.compile(r"116")


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as handle:
        return json.load(handle)


def objects(doc: dict) -> list[dict]:
    out = []
    for entry in doc.get("objects") or []:
        if isinstance(entry, dict) and isinstance(entry.get("objdata"), dict):
            out.append(entry)
    return out


def aliases(entry: dict) -> list[str]:
    raw = entry.get("aliases")
    if isinstance(raw, str):
        return [raw]
    return list(raw or [])


def generated_stamp(source: Path) -> str:
    """Content stamp (C58): the sheet's bytes, not its mtime.

    The mtime changed every time we re-extracted the same OBB, which churned this artifact
    for no reason. `sha256:<16 hex>` is stable across machines and still identifies the input.
    """

    return "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# scale survey
# --------------------------------------------------------------------------- #
def survey_art_center(rows: list[dict]) -> dict:
    """Read the cell size off the `ArtCenter` cluster (pivot = cell centre)."""
    points: list[tuple[float, float]] = []
    for entry in rows:
        center = entry["objdata"].get("ArtCenter")
        if not isinstance(center, dict):
            continue
        x, y = center.get("x"), center.get("y")
        if not all(isinstance(value, (int, float)) and 0 <= value <= 400 for value in (x, y)):
            continue  # the same 9-digit sentinels the offsets have
        points.append((float(x), float(y)))
    if not points:
        return {
            "samples": 0,
            "pivot": None,
            "pxPerColumn": PX_PER_COLUMN,
            "pxPerRow": PX_PER_ROW,
            "source": "fallback constants (no usable ArtCenter in the sheet)",
        }
    pivot_x = Counter(point[0] for point in points).most_common(1)[0][0]
    pivot_y = Counter(point[1] for point in points).most_common(1)[0][0]
    # a 0-based pixel centre at 99/115 implies a 100x116 cell
    width = pivot_x + 1.0
    height = pivot_y + 1.0
    modes = Counter(points).most_common(3)
    return {
        "samples": len(points),
        "pivot": {"x": pivot_x, "y": pivot_y},
        "pxPerColumn": width,
        "pxPerRow": height,
        "modes": [{"x": x, "y": y, "count": count} for (x, y), count in modes],
        "source": "%s:ArtCenter (mode of x and y, +1 for the 0-based pixel centre)"
                  % DEFAULT_PLANT_SHEET,
    }


# --------------------------------------------------------------------------- #
# rows
# --------------------------------------------------------------------------- #
def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def classify_kind(action: dict) -> str:
    return KIND_MAP.get(str(action.get("Type") or ""), "unknown")


def collect(obb_dir: Path) -> tuple[list[dict], dict]:
    """Return (rows, meta) from the plant sheet."""
    sheet = Path(obb_dir) / DEFAULT_PLANT_SHEET
    doc = load_json(sheet)
    entries = objects(doc)

    scale = survey_art_center(entries)
    px_per_column = float(scale["pxPerColumn"])
    px_per_row = float(scale["pxPerRow"])

    rows: list[dict] = []
    skipped: list[dict] = []
    kind_counter: Counter = Counter()
    actions_total = 0
    with_offset = 0
    for entry in entries:
        acts = entry["objdata"].get("Actions")
        if not isinstance(acts, list):
            continue
        plant = (aliases(entry) or ["<no-alias>"])[0]
        for index, action in enumerate(acts):
            if not isinstance(action, dict):
                continue
            actions_total += 1
            offset = action.get("SpawnOffset")
            if not isinstance(offset, dict):
                continue
            with_offset += 1
            x_px = _number(offset.get("x"))
            y_px = _number(offset.get("y"))
            kind = classify_kind(action)
            kind_counter[kind] += 1
            if x_px is None or y_px is None or abs(x_px) >= OFFSET_LIMIT or abs(y_px) >= OFFSET_LIMIT:
                skipped.append({
                    "plant": plant,
                    "actionIndex": index,
                    "kind": kind,
                    "xPx": x_px,
                    "yPx": y_px,
                    "reason": "offset-sentinel" if (x_px is not None and y_px is not None)
                              else "offset-not-numeric",
                })
                continue
            rows.append({
                "plant": plant,
                "actionIndex": index,
                "kind": kind,
                "xPx": round(x_px, 6),
                "yPx": round(y_px, 6),
                "xCols": round(x_px / px_per_column, 4),
                "yCols": round(y_px / px_per_row, 4),
                "source": "%s:%s.Actions[%d].SpawnOffset" % (DEFAULT_PLANT_SHEET, plant, index),
            })

    rows.sort(key=lambda row: (row["plant"], row["actionIndex"]))
    negative = [row["yPx"] for row in rows if row["yPx"] <= 0]
    positive = [row for row in rows if row["yPx"] > 0]
    ys = sorted(row["yPx"] for row in rows)
    meta = {
        "scale": scale,
        "actionsTotal": actions_total,
        "actionsWithSpawnOffset": with_offset,
        "skipped": skipped,
        "byKind": {kind: kind_counter.get(kind, 0) for kind in KINDS},
        "yNegativeRows": len(negative),
        "yPositiveRows": [{"plant": row["plant"], "actionIndex": row["actionIndex"],
                           "kind": row["kind"], "yPx": row["yPx"]} for row in positive],
        "yMedianPx": ys[len(ys) // 2] if ys else None,
        "yMinPx": ys[0] if ys else None,
        "yMaxPx": ys[-1] if ys else None,
        "plants": len({row["plant"] for row in rows}),
    }
    return rows, meta


def samples_from(rows: list[dict]) -> dict:
    out = {}
    for name in SAMPLES:
        picked = [row for row in rows if row["plant"] == name]
        if picked:
            out[name] = picked
    return out


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def build(obb_dir: Path) -> dict:
    rows, meta = collect(obb_dir)
    scale = meta["scale"]
    table = {
        "format": FORMAT,
        "generated": GENERATED,
        "generatedAt": generated_stamp(Path(obb_dir) / DEFAULT_PLANT_SHEET),
        "scale": {
            "pxPerColumn": scale["pxPerColumn"],
            "pxPerRow": scale["pxPerRow"],
            # rows expressed in the same unit as columns: 116 px = 1.16 columns
            "pxPerRowCols": scale["pxPerRow"],
            "enginePxPerColumn": ENGINE_PX_PER_COLUMN,
            "pxPerColumnRatioToEngine": round(scale["pxPerColumn"] / ENGINE_PX_PER_COLUMN, 6),
            "artCenter": {
                "samples": scale["samples"],
                "pivot": scale["pivot"],
                "modes": scale.get("modes", []),
            },
            "source": scale["source"],
            "engineSource": "native/src/engine/action_runner.cpp:14, native/src/engine/registry.cpp:27",
        },
        "defaults": {
            # what the engine does today: `SpawnOffset.y` is never applied
            "shotYCols": 0.0,
            "sunYCols": 0.0,
            "shotXCols": ENGINE_SHOT_X_COLS,
            "source": "native/src/engine/action_runner.cpp:85-90 (y dropped), "
                      "native/src/engine/tuning.hpp kShotStartOffsetCols / kShotHitRadius",
        },
        "samples": samples_from(rows),
        "rows": rows,
        "skipped": meta["skipped"],
        "counts": {
            "rows": len(rows),
            "plants": meta["plants"],
            "actionsTotal": meta["actionsTotal"],
            "actionsWithSpawnOffset": meta["actionsWithSpawnOffset"],
            "skippedOffsets": len(meta["skipped"]),
            "byKind": meta["byKind"],
            "yNegativeRows": meta["yNegativeRows"],
            "yPositiveRows": len(meta["yPositiveRows"]),
            "yMedianPx": meta["yMedianPx"],
            "yMinPx": meta["yMinPx"],
            "yMaxPx": meta["yMaxPx"],
        },
        "ySign": {
            "convention": "negative-is-up",
            "evidence": "%d of %d offsets are <= 0, median %s px, seven positive rows top out at +30 px"
                        % (meta["yNegativeRows"], len(rows), meta["yMedianPx"]),
            "screenRule": "y grows down on screen, so a negative yPx raises the spawn point",
        },
        "positiveY": meta["yPositiveRows"],
    }
    return table


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def render(table: dict) -> str:
    return json.dumps(table, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def dump(table: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render(table).encode("utf-8"))


def _num(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def grep_cell(repo: Path, exclude: Path | None = None) -> dict:
    """Search every markdown file for a `100x116`-style cell statement.

    `exclude` skips this task's own report — otherwise the search finds its own
    conclusion and the "docs never state the cell size" claim becomes unfalsifiable.
    """
    hits = []
    skip = exclude.resolve() if exclude is not None else None
    files = [path for path in sorted(repo.glob(DOC_GLOB))
             if skip is None or path.resolve() != skip]
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if CELL_PATTERN.search(line) and re.search(r"(px|像素|×|x\s*\d)", line):
                hits.append({"file": str(path.relative_to(repo)).replace("\\", "/"),
                             "line": number, "text": line.strip()[:160]})
    return {"files": len(files), "hits": hits}


# --------------------------------------------------------------------------- #
# check
# --------------------------------------------------------------------------- #
def check(table: dict, path: Path) -> int:
    problems: list[str] = []
    counts = table.get("counts") or {}
    scale = table.get("scale") or {}
    rows = table.get("rows") or []
    if table.get("format") != FORMAT:
        problems.append("format %r != %r" % (table.get("format"), FORMAT))
    if table.get("generated") != GENERATED:
        problems.append("generated %r != %r" % (table.get("generated"), GENERATED))
    if counts.get("rows") != len(rows):
        problems.append("counts.rows %r != len(rows) %d" % (counts.get("rows"), len(rows)))
    if counts.get("actionsWithSpawnOffset") != len(rows) + counts.get("skippedOffsets", 0):
        problems.append("withSpawnOffset != rows + skippedOffsets")
    if sum((counts.get("byKind") or {}).values()) != counts.get("actionsWithSpawnOffset"):
        problems.append("byKind 求和 != actionsWithSpawnOffset")
    px_col = scale.get("pxPerColumn")
    px_row = scale.get("pxPerRow")
    if not isinstance(px_col, (int, float)) or not isinstance(px_row, (int, float)):
        problems.append("scale.pxPerColumn / pxPerRow 缺失")
    else:
        bad = [row["plant"] for row in rows
               if abs(row["xCols"] - round(row["xPx"] / px_col, 4)) > 1e-9
               or abs(row["yCols"] - round(row["yPx"] / px_row, 4)) > 1e-9]
        if bad:
            problems.append("xCols/yCols 与像素不符：%s" % bad[:5])
        if scale.get("pxPerRowCols") != px_row:
            problems.append("scale.pxPerRowCols 与 pxPerRow 不一致")
    if [row["plant"] for row in rows] != sorted(row["plant"] for row in rows):
        problems.append("rows 未按 plant 排序")
    bad_kind = [row["plant"] for row in rows if row["kind"] not in KINDS]
    if bad_kind:
        problems.append("非法 kind：%s" % bad_kind[:5])
    if not path.is_file():
        problems.append("%s 不存在，先运行 python tools/contentc/spawn_offsets.py" % path)
    else:
        disk = path.read_bytes()
        fresh = render(table).encode("utf-8")
        if disk != fresh:
            problems.append("%s 与重算结果不一致（产物过期）" % path)
        if b"\r\n" in disk:
            problems.append("产物含 CRLF")
    if problems:
        for problem in problems:
            print("FAIL: %s" % problem)
        return 1
    print("rows=%d plants=%d pxPerColumn=%s pxPerRow=%s yMedian=%s skipped=%d"
          % (len(rows), counts.get("plants"), _num(px_col), _num(px_row),
             _num(counts.get("yMedianPx")), counts.get("skippedOffsets", 0)))
    print("OK")
    return 0


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def render_report(table: dict, cell_search: dict | None = None) -> str:
    counts = table["counts"]
    scale = table["scale"]
    lines: list[str] = []
    add = lines.append

    add("# SpawnOffset.y 语义：像素 → 格子换算（T42）")
    add("")
    add("由 `tools/contentc/spawn_offsets.py` 从 `work/obb_packages/pkg_2073_PlantPropertySheet.json` 生成。")
    add("产物：`native/generated/spawn_offsets.json`（`generatedAt` = 源表内容的 sha256 短戳 `%s`，"
        "因此两次生成逐字节相同）。" % table["generatedAt"])
    add("")
    add("## 0. 三个可验证样例")
    add("")
    add("| 道具 | 动作 | kind | `SpawnOffset.x` | `SpawnOffset.y` | xCols | yCols | 来源字段 |")
    add("|---|---|---:|---:|---:|---:|---:|---|")
    for label, name in (("豌豆", "PeashooterDefault"), ("玉米", "KernelpultDefault"),
                        ("阳光", "SunflowerDefault")):
        for row in table["samples"].get(name, []):
            add("| %s（`%s`） | `Actions[%d]` | `%s` | %s | %s | %s | %s | `%s` |"
                % (label, name, row["actionIndex"], row["kind"], _num(row["xPx"]),
                   _num(row["yPx"]), _num(row["xCols"]), _num(row["yCols"]),
                   row["source"].split(":", 1)[1]))
    add("")
    add("读法：`PeashooterDefault` 的豌豆从格子中心右 0.35 格、上 0.276 格射出；"
        "`KernelpultDefault` 的玉米从右 0.15 格、上 0.819 格抛出（所以它能越过前排植物）；"
        "`SunflowerDefault` 的阳光直接在植物中心上方 0.448 格生成（x 偏移 0）。")
    add("")

    add("## 1. 换算依据")
    add("")
    add("### 1a. 一格是多少像素")
    add("")
    add("**任务里提到的「`docs/COMPLETENESS.md` 有 100×116 像素/格」在当前树里不存在。**")
    if cell_search is not None:
        add("对 `docs/` 下全部 %d 个 markdown 文件做 `116` + 像素/乘号 检索，"
            "命中 **%d** 处（`python tools/contentc/spawn_offsets.py --grep-cell` 可复现）。"
            % (cell_search["files"], len(cell_search["hits"])))
        for hit in cell_search["hits"][:5]:
            add("- `%s:%d` — %s" % (hit["file"], hit["line"], hit["text"]))
        add("")
    add("真正的依据在数据里：")
    add("")
    add("| 证据 | 值 | 命令 / 位置 |")
    add("|---|---|---|")
    add("| `ArtCenter` 众数（%d 个可用样本；379 个对象有该字段，9 位哨兵已过滤） | "
        "枢轴 `(%s, %s)`、次众数 `(99, 116)` | "
        "`pkg_2073_PlantPropertySheet.json` 的 `ArtCenter` |"
        % (scale["artCenter"]["samples"],
           _num((scale["artCenter"]["pivot"] or {}).get("x")),
           _num((scale["artCenter"]["pivot"] or {}).get("y"))))
    add("| 由此得到的格尺寸 | **%s × %s px** | `ArtCenter` = 格子中心，故 +1 补 0 基像素中心 |"
        % (_num(scale["pxPerColumn"]), _num(scale["pxPerRow"])))
    add("| 引擎当前用的列宽 | **%s px** | `native/src/engine/action_runner.cpp:14`、"
        "`registry.cpp:27` 的 `kPixelsPerColumn` |" % _num(scale["enginePxPerColumn"]))
    add("| 交叉验证 | `kShotStartOffsetCols = 0.35` = 豌豆 `35 / 100` | "
        "`native/src/engine/tuning.hpp` |")
    add("")
    add("两者差 `%s` 倍：植物美术空间是 100 px/列，而引擎按 60 px/列换算 `SpawnOffset.x`。"
        "本表按**美术空间**换算（`SpawnOffset` 就写在这个空间里），并把 60 原样记在 "
        "`scale.enginePxPerColumn`，把差值记在 `scale.pxPerColumnRatioToEngine`。"
        % _num(scale["pxPerColumnRatioToEngine"]))
    add("")
    add("### 1b. y 的换算")
    add("")
    add("```")
    add("xCols = xPx / %s     # 100 px / 列" % _num(scale["pxPerColumn"]))
    add("yCols = yPx / %s     # 116 px / 行" % _num(scale["pxPerRow"]))
    add("```")
    add("")
    add("`yCols` 与 `xCols` 同单位（格子），所以引擎把两者加到 `(col, row)` 的浮点坐标上即可；"
        "`scale.pxPerRowCols` 就是 116，含义是「1 行 = 116 px = 1.16 个列宽」。")
    add("")

    add("## 2. y 的符号约定")
    add("")
    add("**负值向上。**")
    add("")
    add("| 事实 | 值 |")
    add("|---|---:|")
    add("| `y <= 0` 的行 | %d / %d |" % (counts["yNegativeRows"], counts["rows"]))
    add("| `y > 0` 的行 | %d（见下） |" % counts["yPositiveRows"])
    add("| 中位数 | %s px |" % _num(counts["yMedianPx"]))
    add("| 区间 | %s … %s px |" % (_num(counts["yMinPx"]), _num(counts["yMaxPx"])))
    add("")
    if table["positiveY"]:
        add("仅有的正值行（都是小幅枪口偏移，不是「向下发射」）：")
        add("")
        add("| 植物 | 动作 | kind | yPx |")
        add("|---|---:|---|---:|")
        for row in table["positiveY"]:
            add("| `%s` | %d | `%s` | %s |"
                % (row["plant"], row["actionIndex"], row["kind"], _num(row["yPx"])))
        add("")
    add("屏幕上 y 向下增长，所以负的 `yPx` 表示**抬高**；引擎若要屏幕坐标，取 `-yCols`。"
        "深度为 `-600`/`-1000` 的行（`BananaDefault`、`CobCannonDefault`、`NukeLauncherDefault`、"
        "`DandelionDefault` 等）不是格内偏移，而是「从画面上方落下来」的投放点，"
        "换算后是 -5.2 / -8.6 行，超出棋盘高度——这是它们的设计意图，不是坏数据。")
    add("")

    add("## 3. 不确定项（必须读）")
    add("")
    add("1. **116 px/行是从 `ArtCenter` 众数读出来的，不是代码常量**：仓库里没有任何"
        "「行高」常量（`native/src` 中 `kPixelsPerRow`/`kCellHeight` 均 0 命中），"
        "`battle_view.cpp:19` 的 `cellW = cellH = 100` 是**屏幕像素**，不是美术空间，"
        "不能拿来换算 `SpawnOffset`。若日后确认美术格不是 116 高，只改 `scale.pxPerRow`。")
    add("2. **100 vs 60 的口径冲突未在本任务解决**：本表按 100 输出 `xCols`，"
        "而引擎现在按 60 换算，同一条 `SpawnOffset.x = 35` 会得到 0.35（本表）与 0.583（引擎）。"
        "修 `native/src/**` 不在本任务写作用域内。")
    add("3. **`special`/`explode`/`manual` 的 `SpawnOffset` 不是发射点**：`action_runner.cpp:22` "
        "的注释已说明它是触发矩形原点，本表按 `kind` 标注，消费方不应把它当弹道起点。")
    add("4. **哨兵值**：`|像素| >= %s` 的偏移被跳过并计入 `counts.skippedOffsets`"
        "（当前 %d 条：%s）。" % (_num(OFFSET_LIMIT), counts["skippedOffsets"],
                                  "、".join("`%s` Actions[%d]" % (item["plant"], item["actionIndex"])
                                           for item in table["skipped"]) or "无"))
    add("5. **`ArtCenter` 自身有哨兵**：少数对象是 9 位数（如 `979999999`），"
        "统计时按 `0..400` 过滤，过滤前的样本数不参与众数。")
    add("")

    add("## 4. 统计")
    add("")
    add("| 项 | 值 |")
    add("|---|---:|")
    add("| 植物 props 对象里的 action 总数 | %d |" % counts["actionsTotal"])
    add("| 带 `SpawnOffset` 的 action | %d |" % counts["actionsWithSpawnOffset"])
    add("| 换算成 row 的行数 | %d |" % counts["rows"])
    add("| 涉及植物 | %d |" % counts["plants"])
    add("| 跳过（哨兵/非数值） | %d |" % counts["skippedOffsets"])
    add("")
    add("按 kind：%s。" % "、".join("`%s` %d" % (kind, count)
                                  for kind, count in counts["byKind"].items() if count))
    add("")

    add("## 5. 复现")
    add("")
    add("```")
    add("python tools/contentc/spawn_offsets.py             # 重写 json + 本报告")
    add("python tools/contentc/spawn_offsets.py --check     # 自洽 + 逐字节比对")
    add("python tools/contentc/spawn_offsets.py --grep-cell # 复现「docs 里没有 100×116」")
    add("python -m unittest tools.tests.test_spawn_offsets -v")
    add("```")
    add("")
    add("表格里的每个数都能用第三条命令重算；逐行来源在 json 的 `rows[].source`。")
    add("")

    add("## 6. 引擎接入建议（不在本任务实现）")
    add("")
    add("1. `World::spawnShot` / `spawnSun` 增加一个 `yCols` 参数（向上为正），"
        "内部按 `y` 屏幕坐标减去它；`0.0` 即今天的行为，所以加参数不会改变既有 32 个冒烟场景。")
    add("2. 换算用本表的 100 px/列 与 116 px/行——**同时**把 `kPixelsPerColumn` 从 60 改到 100，"
        "否则 x 与 y 会来自两套不同的像素空间，抛物线会歪。")
    add("3. `special`/`explode`/`manual` 行不要接进发射点，它们只决定触发矩形。")
    add("")
    return "\n".join(lines) + "\n"


def write_report(table: dict, path: Path, cell_search: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(render_report(table, cell_search).encode("utf-8"))


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert pack SpawnOffset pixels to cell units")
    parser.add_argument("--obb", type=Path, default=Path(DEFAULT_OBB) if DEFAULT_OBB else None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--check", action="store_true", help="verify the artifact is self-consistent")
    parser.add_argument("--grep-cell", action="store_true",
                        help="search docs/ for a 100x116 px-per-cell statement")
    parser.add_argument("--no-report", action="store_true", help="only write the json")
    args = parser.parse_args(argv)

    if args.grep_cell:
        found = grep_cell(args.repo, exclude=args.report)
        print("files=%d hits=%d" % (found["files"], len(found["hits"])))
        for hit in found["hits"]:
            print("  %s:%d %s" % (hit["file"], hit["line"], hit["text"]))
        return 0

    if args.obb is None:
        print("no OBB directory; pass --obb", file=sys.stderr)
        return 2

    table = build(args.obb)
    if args.check:
        return check(table, args.out)

    dump(table, args.out)
    print("wrote %s (rows=%d plants=%d)" % (args.out, table["counts"]["rows"],
                                            table["counts"]["plants"]))
    if not args.no_report:
        write_report(table, args.report, grep_cell(args.repo, exclude=args.report))
        print("wrote %s" % args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
