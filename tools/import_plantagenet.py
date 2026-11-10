"""Import the Plantagenet (王朝) renders into the SHUTTLE asset tree.

Sources come from ``D:\\OneDrive\\文档\\pvz_shuttle\\Renders`` (outside the game
tree).  The panorama "Plantagenet Day (With Lights).png" is a 3948x1536
orthographic lawn; a single anisotropic crop of it is scaled to the 1280x720
lawn so the 9x5 tile grid lands exactly on ``BOARD`` (190,120,900,580) that
``game/config.py`` expects.  Cropping the panorama instead of using a "cover"
background keeps the source's own perspective board from peeking out behind the
pasted one.

Usage:
    python tools/import_plantagenet.py            # write assets + manifest
    python tools/import_plantagenet.py --preview   # also write review images
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None            # renders reach ~121 MP

ROOT = Path(__file__).resolve().parent.parent
RENDERS = Path(r"D:\OneDrive\文档\pvz_shuttle\Renders")
OUT_ART = ROOT / "assets" / "art"
OUT_LAWN = ROOT / "assets" / "lawn"
OUT_WORLD = ROOT / "assets" / "world"
WORK = ROOT / "work" / "arttest"

WIN = (1280, 720)
BOARD = (190, 120, 900, 580)             # x, y, w, h of the 9x5 grid on screen
LAWN_CROP = (762, 204, 2848, 1408)       # source crop mapping the grid onto BOARD
ART_MAX = 900                            # longest sprite edge, px

DAY = "Plantagenet/Plantagenet Day (With Lights).png"
NIGHT = "Plantagenet/Plantagenet Night (With Lights).png"

# slug -> (Renders-relative source, assets-relative output)
PLANT_ART = {
    "iris": ("Plantagenet/Iris.png", "art/plantagenet/iris.png"),
    "rosemary": ("Plantagenet/Rosemary.png", "art/plantagenet/rosemary.png"),
    "snowlotus": ("Plantagenet/Snow Lotus.png", "art/plantagenet/snowlotus.png"),
    "wildflower": ("Plantagenet/Wildflower.png", "art/plantagenet/wildflower.png"),
    "olivewood": ("Plantagenet/Olive Wood.png", "art/plantagenet/olivewood.png"),
    "astrofruit": ("Collaboration/Astrofruit.png", "art/plantagenet/astrofruit.png"),
    "chrysanthea": ("Collaboration/Chrysanthe Autumn.png", "art/plantagenet/chrysanthea.png"),
    "doominator": ("Collaboration/Doominator-shroom.png", "art/plantagenet/doominator.png"),
    "helioscabbage": ("Collaboration/Helios Cabbage.png", "art/plantagenet/helioscabbage.png"),
    "paradoxpult": ("Collaboration/Paradox-pult.png", "art/plantagenet/paradoxpult.png"),
    "tubiflora": ("Collaboration/Tubiflora.png", "art/plantagenet/tubiflora.png"),
    "vortexmelon": ("Collaboration/Vortex Melon.png", "art/plantagenet/vortexmelon.png"),
    "cheesestrawberry": ("Jin Jin Tea Shop/Cheese Strawberry.png", "art/plantagenet/cheesestrawberry.png"),
    "oolongpeach": ("Jin Jin Tea Shop/Oolong Peach.png", "art/plantagenet/oolongpeach.png"),
    "succulentgrape": ("Jin Jin Tea Shop/Succulent Grape.png", "art/plantagenet/succulentgrape.png"),
    "doublepassion": ("Jin Jin Tea Shop/Double Passion.png", "art/plantagenet/doublepassion.png"),
    "fireflerry": ("Stellar Sprouts/Fireflerry.png", "art/stellar/fireflerry.png"),
    "frozenpear": ("Others/Frozen Pear.png", "art/others/frozenpear.png"),
    "solarflare": ("Others/Solar Flare.png", "art/others/solarflare.png"),
    "taraxacum": ("Others/Taraxacum.png", "art/others/taraxacum.png"),
}

ZOMBIE_ART = {
    "royal_zombie": ("Plantagenet/Royal Zombie.png", "art/plantagenet/royal_zombie.png"),
    "royal_flag": ("Plantagenet/Royal Flag Zombie.png", "art/plantagenet/royal_flag.png"),
    "royal_noblewoman": ("Plantagenet/Royal Noblewoman Zombie.png", "art/plantagenet/royal_noblewoman.png"),
    "royal_winetasting": ("Plantagenet/Royal Winetasting Zombie.png", "art/plantagenet/royal_winetasting.png"),
    "royal_chef_gargantuar": ("Plantagenet/Royal Chef Gargantuar.png", "art/plantagenet/royal_chef_gargantuar.png"),
    "imp_maid": ("Plantagenet/Imp Maid Zombie.png", "art/plantagenet/imp_maid.png"),
    "royal_princess": ("Plantagenet/Zombie Royal Princess.png", "art/plantagenet/royal_princess.png"),
}


def load_rgba(name: str) -> Image.Image:
    path = RENDERS / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return Image.open(path).convert("RGBA")


def trim(im: Image.Image) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Crop to the visible alpha bounding box; returns (image, bbox)."""
    box = im.getbbox()
    if box is None:
        raise ValueError("sprite is fully transparent")
    return im.crop(box), box


def save_art(src: str, out_rel: str) -> dict:
    im = load_rgba(src)
    size = im.size
    im, box = trim(im)
    trimmed = im.size
    if max(trimmed) > ART_MAX:
        scale = ART_MAX / max(trimmed)
        im = im.resize((max(1, round(trimmed[0] * scale)),
                        max(1, round(trimmed[1] * scale))), Image.LANCZOS)
    dst = ROOT / "assets" / out_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, optimize=True)
    return {"src": src, "out": out_rel, "source_size": list(size),
            "trim_box": list(box), "trimmed_size": list(trimmed),
            "saved_size": list(im.size), "bytes": dst.stat().st_size}


def build_lawn(src: str, out_rel: str, crop=LAWN_CROP) -> dict:
    im = load_rgba(src).convert("RGB")
    panel = im.crop(crop).resize(WIN, Image.LANCZOS)
    dst = ROOT / "assets" / out_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    panel.save(dst, optimize=True)
    left, top = crop[0], crop[1]
    sx = WIN[0] / (crop[2] - crop[0])
    sy = WIN[1] / (crop[3] - crop[1])
    grid = ((1072 - left) * sx, (405 - top) * sy,
            (2538 - 1072) * sx, (1375 - 405) * sy)
    return {"src": src, "out": out_rel, "crop": list(crop),
            "source_size": list(Image.open(RENDERS / src).size),
            "saved_size": list(WIN), "bytes": dst.stat().st_size,
            "grid_on_screen": [round(v, 2) for v in grid],
            "grid_target": list(BOARD)}


def build_world(src: str, out_rel: str) -> dict:
    """Cover the 1280x720 banner with the panorama (centre crop)."""
    im = load_rgba(src).convert("RGB")
    scale = max(WIN[0] / im.width, WIN[1] / im.height)
    big = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    x = (big.width - WIN[0]) // 2
    y = (big.height - WIN[1]) // 2
    panel = big.crop((x, y, x + WIN[0], y + WIN[1]))
    dst = ROOT / "assets" / out_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    panel.save(dst, optimize=True)
    return {"src": src, "out": out_rel, "source_size": list(im.size),
            "crop": [x, y, x + WIN[0], y + WIN[1]],
            "saved_size": list(WIN), "bytes": dst.stat().st_size}


# ---------------------------------------------------------------- 预览
def contact_sheet(entries, out_path: Path, cols: int = 8, cell: int = 220):
    rows = (len(entries) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), (28, 32, 40))
    draw = ImageDraw.Draw(sheet)
    for i, (label, rel) in enumerate(entries):
        img = Image.open(ROOT / "assets" / rel).convert("RGBA")
        scale = min((cell - 30) / img.width, (cell - 30) / img.height)
        img = img.resize((max(1, round(img.width * scale)),
                          max(1, round(img.height * scale))), Image.LANCZOS)
        cx = (i % cols) * cell
        cy = (i // cols) * cell
        sheet.paste(img, (cx + (cell - img.width) // 2,
                          cy + (cell - img.height) // 2), img)
        draw.text((cx + 4, cy + cell - 16), label[:26], fill=(240, 240, 240))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)


def lawn_preview(out_rel: str, preview_path: Path):
    img = Image.open(ROOT / "assets" / out_rel).convert("RGB")
    draw = ImageDraw.Draw(img)
    x, y, w, h = BOARD
    draw.rectangle((x, y, x + w, y + h), outline=(255, 60, 60), width=3)
    for c in range(1, 9):
        draw.line((x + w * c / 9, y, x + w * c / 9, y + h), fill=(255, 60, 60), width=1)
    for r in range(1, 5):
        draw.line((x, y + h * r / 5, x + w, y + h * r / 5), fill=(255, 60, 60), width=1)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(preview_path)


def main(preview: bool = False) -> dict:
    report = {"art": {}, "lawn": {}, "night_lawn": {}, "world": {}}
    for slug, (src, out) in {**PLANT_ART, **ZOMBIE_ART}.items():
        info = save_art(src, out)
        report["art"][slug] = info
        print("art  %-18s %-9s -> %-9s" % (slug, "x".join(map(str, info["trimmed_size"])),
                                           "x".join(map(str, info["saved_size"]))))
    report["lawn"] = build_lawn(DAY, "lawn/plantagenet.png")
    print("lawn day   crop=%s grid=%s" % (report["lawn"]["crop"], report["lawn"]["grid_on_screen"]))
    report["night_lawn"] = build_lawn(NIGHT, "lawn/plantagenet_night.png")
    print("lawn night crop=%s grid=%s" % (report["night_lawn"]["crop"],
                                          report["night_lawn"]["grid_on_screen"]))
    report["world"] = build_world(DAY, "world/plantagenet.png")
    print("world      %s" % (report["world"]["saved_size"],))

    if preview:
        contact_sheet([(slug, info["out"]) for slug, info in report["art"].items()],
                      WORK / "plantagenet_sheet.png")
        contact_sheet([(slug, info["out"]) for slug, info in list(report["art"].items())[:20]],
                      WORK / "plantagenet_plants.png", cols=5, cell=260)
        lawn_preview("lawn/plantagenet.png", WORK / "plantagenet_lawn_check.png")
        lawn_preview("lawn/plantagenet_night.png", WORK / "plantagenet_lawn_night_check.png")
        w = Image.open(ROOT / "assets" / "world" / "plantagenet.png")
        w.resize((640, 360), Image.LANCZOS).save(WORK / "plantagenet_world_check.png")
        print("previews -> %s" % WORK)

    manifest = ROOT / "tools" / "plantagenet_manifest.json"
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("manifest -> %s" % manifest)
    return report


if __name__ == "__main__":
    main("--preview" in sys.argv[1:])
