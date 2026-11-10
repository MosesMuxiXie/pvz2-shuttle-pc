"""Build world cards and full-screen lawns for the eight new worlds.

Lawns are 1280x720 full-screen art whose 9x5 playable board maps exactly to
(190,120)-(1090,700), matching the official lawns used by the game
(``lawn_mode == "full"`` in content/worlds.json).

Sources:
  * heian / fairy  -> work/art_research/<world>/{map,lawn}.png (anisotropic
    crop of the in-game board, board mapped onto the target rectangle)
  * memorytour     -> art_research menu screenshot for the card, tinted
    modern lawn for the board (no clean in-game board art available)
  * mausoleum / steam / renai -> tinted official lawn + gradient card
    (no source art; flagged NEEDS_ART in the build report)
  * carnival / muji -> already supplied by the parallel art agent; this
    script only verifies their dimensions and leaves them untouched.

Everything is written as UTF-8-safe PNG (no metadata), 1280x720 RGB.
"""
from __future__ import annotations

import colorsys
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT.parent / "work" / "art_research"
WORLD_DIR = ROOT / "assets" / "world"
LAWN_DIR = ROOT / "assets" / "lawn"

BOARD = (190, 120, 1090, 700)  # x0, y0, x1, y1
CANVAS = (1280, 720)


def _load(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def _crop_to_aspect(im: Image.Image, aspect: float) -> Image.Image:
    w, h = im.size
    if w / h > aspect:
        nw = int(round(h * aspect))
        x0 = (w - nw) // 2
        return im.crop((x0, 0, x0 + nw, h))
    nh = int(round(w / aspect))
    y0 = (h - nh) // 2
    return im.crop((0, y0, w, y0 + nh))


def world_card(src: Path, out: Path) -> None:
    im = _crop_to_aspect(_load(src), CANVAS[0] / CANVAS[1])
    im = im.resize(CANVAS, Image.LANCZOS)
    im.save(out, optimize=True)


def gradient_card(tint, out: Path, motif: str = "") -> None:
    """Simple flat-colour card used until proper key art exists."""
    w, h = CANVAS
    top = tuple(max(0, c - 70) for c in tint)
    bottom = tuple(min(255, int(c * 0.55)) for c in tint)
    im = Image.new("RGB", CANVAS)
    px = im.load()
    for y in range(h):
        t = y / (h - 1)
        row = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(w):
            px[x, y] = row
    dr = ImageDraw.Draw(im)
    # soft vignette + a few geometric silhouettes so the card reads as
    # intentional placeholder art rather than a solid colour.
    for i in range(6):
        k = i / 5
        col = tuple(int(c * (0.85 - 0.10 * k)) for c in tint)
        if motif == "columns":
            x = 210 + i * 170
            dr.rectangle((x, 250 - i * 8, x + 46, 620), fill=col)
            dr.rectangle((x - 14, 236 - i * 8, x + 60, 256 - i * 8), fill=col)
        elif motif == "gears":
            r = 60 + (i % 3) * 22
            cx, cy = 200 + i * 180, 200 + (i % 2) * 160
            dr.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=14)
            dr.ellipse((cx - r // 3, cy - r // 3, cx + r // 3, cy + r // 3), fill=col)
        elif motif == "curtains":
            x = i * 128
            dr.polygon([(x, 0), (x + 90, 0), (x + 130, 720), (x - 40, 720)], fill=col)
    dr.rectangle((0, 0, w - 1, h - 1), outline=tuple(min(255, c) for c in tint), width=3)
    im.save(out, optimize=True)


def _perspective_coeffs(dst, src):
    """Return PIL PERSPECTIVE coefficients mapping dst->src for 4 point pairs."""
    import numpy as np

    a = []
    b = []
    for (dx, dy), (sx, sy) in zip(dst, src):
        a.append([dx, dy, 1, 0, 0, 0, -sx * dx, -sx * dy])
        b.append(sx)
        a.append([0, 0, 0, dx, dy, 1, -sy * dx, -sy * dy])
        b.append(sy)
    res = np.linalg.solve(np.asarray(a, dtype=float), np.asarray(b, dtype=float))
    return tuple(res.tolist())


def board_lawn(src: Path, out: Path, board_src) -> None:
    """Crop/warp ``src`` so that ``board_src`` maps onto BOARD in a 1280x720 canvas.

    ``board_src`` is either an (x0, y0, x1, y1) rectangle or four source
    points (TL, TR, BR, BL) for a perspective quad.
    """
    im = _load(src)
    if len(board_src) == 4 and not isinstance(board_src[0], (int, float)):
        quad = board_src
        dst = [(BOARD[0], BOARD[1]), (BOARD[2], BOARD[1]),
               (BOARD[2], BOARD[3]), (BOARD[0], BOARD[3])]
        coeffs = _perspective_coeffs(dst, quad)
        im = im.transform(CANVAS, Image.PERSPECTIVE, coeffs, Image.BICUBIC)
        im.save(out, optimize=True)
        return
    x0, y0, x1, y1 = board_src
    sx = (BOARD[2] - BOARD[0]) / (x1 - x0)
    sy = (BOARD[3] - BOARD[1]) / (y1 - y0)
    crop_w = CANVAS[0] / sx
    crop_h = CANVAS[1] / sy
    left = x0 - BOARD[0] / sx
    top = y0 - BOARD[1] / sy
    box = (left, top, left + crop_w, top + crop_h)
    if box[0] < 0 or box[1] < 0 or box[2] > im.width or box[3] > im.height:
        raise ValueError(f"crop {box} outside source {im.size} for {src}")
    crop = im.resize((CANVAS[0], CANVAS[1]), Image.LANCZOS, box=box)
    crop.save(out, optimize=True)


def hsv_tint(im: Image.Image, hue_shift: float, sat_mul: float = 1.0,
             val_mul: float = 1.0, blend=None, blend_alpha: float = 0.0) -> Image.Image:
    hsv = im.convert("HSV")
    px = hsv.load()
    w, h = hsv.size
    shift = int(hue_shift * 255) % 256
    for y in range(h):
        for x in range(w):
            hh, ss, vv = px[x, y]
            hh = (hh + shift) % 256
            ss = min(255, int(ss * sat_mul))
            vv = min(255, int(vv * val_mul))
            px[x, y] = (hh, ss, vv)
    out = hsv.convert("RGB")
    if blend is not None and blend_alpha > 0:
        out = Image.blend(out, Image.new("RGB", out.size, blend), blend_alpha)
    return out


def main() -> int:
    WORLD_DIR.mkdir(parents=True, exist_ok=True)
    LAWN_DIR.mkdir(parents=True, exist_ok=True)

    # ---- heian -----------------------------------------------------------
    heian_board = (1020, 400, 2660, 1425)
    board_lawn(ART / "heian" / "lawn.png", LAWN_DIR / "heian.png", heian_board)
    world_card(ART / "heian" / "map.png", WORLD_DIR / "heian.png")
    hsv_tint(_load(LAWN_DIR / "heian.png"), 0.0, 0.75, 0.55).save(
        LAWN_DIR / "heian_night.png", optimize=True)

    # ---- fairy -----------------------------------------------------------
    # The grass board in the screenshot is a trapezoid: its right edge follows
    # the diagonal path, so a perspective quad keeps that path outside the
    # 9x5 playable area.
    fairy_board = [(990, 455), (2692, 455), (2473, 1395), (990, 1395)]
    board_lawn(ART / "fairy" / "lawn.png", LAWN_DIR / "fairy.png", fairy_board)
    world_card(ART / "fairy" / "map.png", WORLD_DIR / "fairy.png")
    hsv_tint(_load(LAWN_DIR / "fairy.png"), 0.0, 0.70, 0.55).save(
        LAWN_DIR / "fairy_night.png", optimize=True)

    # ---- memorytour ------------------------------------------------------
    world_card(ART / "memorytour" / "map.png", WORLD_DIR / "memorytour.png")
    base = _load(LAWN_DIR / "modern.png")
    hsv_tint(base, 0.0, 0.80, 0.92, blend=(236, 214, 170), blend_alpha=0.28).save(
        LAWN_DIR / "memorytour.png", optimize=True)
    hsv_tint(_load(LAWN_DIR / "memorytour.png"), 0.0, 0.7, 0.6).save(
        LAWN_DIR / "memorytour_night.png", optimize=True)

    # ---- mausoleum -------------------------------------------------------
    gradient_card((92, 78, 120), WORLD_DIR / "mausoleum.png", "columns")
    hsv_tint(_load(LAWN_DIR / "dark.png"), 0.02, 0.85, 0.80,
             blend=(70, 54, 96), blend_alpha=0.30).save(
        LAWN_DIR / "mausoleum.png", optimize=True)

    # ---- steam -----------------------------------------------------------
    gradient_card((150, 108, 74), WORLD_DIR / "steam.png", "gears")
    hsv_tint(_load(LAWN_DIR / "future.png"), 0.18, 0.80, 0.88,
             blend=(190, 140, 80), blend_alpha=0.22).save(
        LAWN_DIR / "steam.png", optimize=True)

    # ---- renai -----------------------------------------------------------
    gradient_card((190, 110, 130), WORLD_DIR / "renai.png", "curtains")
    hsv_tint(_load(LAWN_DIR / "plantagenet.png"), 0.93, 1.05, 0.95,
             blend=(232, 150, 180), blend_alpha=0.18).save(
        LAWN_DIR / "renai.png", optimize=True)

    # ---- verify the parallel-art worlds ---------------------------------
    for wid in ("carnival", "muji"):
        for folder in (WORLD_DIR, LAWN_DIR):
            p = folder / f"{wid}.png"
            if not p.exists():
                print(f"MISSING art: {p}")
            else:
                print(f"{wid:10s} {folder.name:5s} {Image.open(p).size} {p.stat().st_size}B")
    print("art written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
