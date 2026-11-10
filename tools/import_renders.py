"""把用户提供的 Music/ 与 Renders/ 整理成游戏可用资源。

- Renders/*.png  -> assets/art/<world>/<slug>.png（裁掉透明边，限制最大边长）
- Renders 键艺   -> assets/world/<world>.png（1280x720 世界图）
- Renders 草坪   -> assets/lawn/<world>.png（整幅 1280x720 场景，棋盘对齐 190,120,900,580）
- Music/*.flac   -> assets/audio/<slug>.ogg（由 ffmpeg 转码，见 convert_music.py）

脚本可重复执行；输出清单写到 tools/renders_manifest.json。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
RENDERS = Path(r"D:\OneDrive\文档\pvz_shuttle\Renders")
OUT_ART = ROOT / "assets" / "art"
OUT_WORLD = ROOT / "assets" / "world"
OUT_LAWN = ROOT / "assets" / "lawn"
BOARD = (190, 120, 900, 580)
WIN = (1280, 720)

# 立绘：世界 -> slug -> 相对 Renders 的路径
ART = {
    "chinesegarden": {
        "gardenia": "Chinese Garden/Part 1/Gardenia.png",
        "jasmine": "Chinese Garden/Part 1/Jasmine.png",
        "torpedofruit": "Chinese Garden/Part 1/Torpedo Fruit.png",
        "seapotatomine": "Chinese Garden/Part 1/Sea-potato Mine.png",
        "elderbarrier": "Chinese Garden/Part 2/Elderbarrier.png",
        "phantasmagnolia": "Chinese Garden/Part 2/Phantas Magnolia.png",
        "plummet1": "Chinese Garden/Part 2/Plummet (Growth Stage 1).png",
        "privacyscreen1": "Chinese Garden/Part 2/Privacy Screen (Variation 1).png",
        "zombie": "Chinese Garden/Part 1/Garden Zombie.png",
        "conehead": "Chinese Garden/Part 1/Garden Conehead Zombie.png",
        "buckethead": "Chinese Garden/Part 1/Garden Buckethead Zombie.png",
        "flag": "Chinese Garden/Part 1/Garden Flag Zombie.png",
        "poet": "Chinese Garden/Part 1/Literati Zombie.png",
        "umbrella": "Chinese Garden/Part 1/Umbrella Zombie.png",
        "imp": "Chinese Garden/Part 1/Official Imp.png",
        "gargantuar": "Chinese Garden/Part 1/Guardian Gargantuar.png",
        "cujustar": "Chinese Garden/Part 2/Cuju Star Zombie.png",
        "drummer": "Chinese Garden/Part 2/Drummer Zombie.png",
        "flutist": "Chinese Garden/Part 2/Flutist Zombie.png",
        "fengshuist": "Chinese Garden/Part 2/Fengshuist Zombie.png",
        "impkoi": "Chinese Garden/Part 2/Imp Koi Zombie.png",
        "imptaoist": "Chinese Garden/Part 2/Imp Taoist Zombie.png",
    },
    "losantosvice": {
        "birdofparadise": "Los Santos Vice/Bird of Paradise.png",
        "poppinpoppies": "Los Santos Vice/Poppin_ Poppies.png",
        "yuccaguardian": "Los Santos Vice/Yucca Guardian.png",
        "zombie": "Los Santos Vice/Families Basic Zombie.png",
        "conehead": "Los Santos Vice/Conehead Families.png",
        "buckethead": "Los Santos Vice/Buckethead Families.png",
        "ozloc": "Los Santos Vice/OZ Loc Zombie.png",
        "molotov": "Los Santos Vice/Vagos Molotov Zombie.png",
        "carljohnson": "Los Santos Vice/Carl Johnson.png",
        "gargantuar": "Los Santos Vice/Big Smogantuar.png",
        "imp": "Los Santos Vice/Cluckin_ Bell Imp.png",
    },
    "lunarrainbowmarket": {
        "begonia": "Lunar Rainbow Market/Begonia.png",
        "potatochip": "Lunar Rainbow Market/Potato Chip.png",
        "missiletoast": "Lunar Rainbow Market/Missile Toast.png.png",
        "desirecalamus": "Lunar Rainbow Market/Desire Calamus.png",
        "clockwork": "Lunar Rainbow Market/Clockwork Zombie.png",
        "mechanic": "Lunar Rainbow Market/Mechanic Zombie.png",
        "trapeze": "Lunar Rainbow Market/Trapeze Zombies.png",
    },
}

# 世界图（1280x720 cover）
WORLD_ART = {
    "chinesegarden": "Chinese Garden/Part 2/Chinese Garden Part 2.png",
    "losantosvice": "Los Santos Vice/Los Santos Vice.png",
    "lunarrainbowmarket": "Lunar Rainbow Market/Lunar Rainbow Market Map.png",
}

# 草坪：世界 -> (来源, 棋盘裁剪框) ；“full” 表示整幅合成
LAWN_ART = {
    "losantosvice": "Los Santos Vice/Los Santos Vice Lawn.png",
    "lunarrainbowmarket": "Lunar Rainbow Market/Lunar Rainbow Market Lawn.png",
}
LAWN_CROP = {
    "losantosvice": (996, 344, 2723, 1432),
    "lunarrainbowmarket": (1140, 384, 2582, 1430),
}


def load_rgba(path: Path) -> Image.Image:
    im = Image.open(path)
    if im.mode not in ("RGBA", "LA"):
        im = im.convert("RGBA")
    return im


def trim(im: Image.Image) -> Image.Image:
    bbox = im.getbbox()
    return im.crop(bbox) if bbox else im


def cover(im: Image.Image, size) -> Image.Image:
    w, h = im.size
    W, H = size
    s = max(W / w, H / h)
    im2 = im.resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS)
    x = (im2.width - W) // 2
    y = (im2.height - H) // 2
    return im2.crop((x, y, x + W, y + H))


def save_art(world: str, slug: str, rel: str) -> dict:
    src = RENDERS / rel
    if not src.exists():
        return {"slug": slug, "error": "missing", "src": rel}
    im = trim(load_rgba(src))
    max_side = 900
    if max(im.size) > max_side:
        s = max_side / max(im.size)
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    d = OUT_ART / world
    d.mkdir(parents=True, exist_ok=True)
    dst = d / f"{slug}.png"
    im.save(dst, optimize=True)
    return {"slug": slug, "src": rel, "size": im.size, "bytes": dst.stat().st_size,
            "key": f"art/{world}/{slug}.png"}


def build_world(world: str, rel: str) -> dict:
    src = RENDERS / rel
    im = load_rgba(src)
    bg = cover(im, WIN).convert("RGB")
    OUT_WORLD.mkdir(parents=True, exist_ok=True)
    dst = OUT_WORLD / f"{world}.png"
    bg.save(dst, optimize=True)
    return {"world": world, "src": rel, "bytes": dst.stat().st_size}


def build_lawn(world: str, rel: str) -> dict:
    src = RENDERS / rel
    im = load_rgba(src)
    bg = cover(im, WIN)
    x0, y0, x1, y1 = LAWN_CROP[world]
    board = im.crop((x0, y0, x1, y1)).resize((BOARD[2], BOARD[3]), Image.LANCZOS)
    bg = bg.convert("RGB")
    bg.paste(board.convert("RGB"), (BOARD[0], BOARD[1]))
    OUT_LAWN.mkdir(parents=True, exist_ok=True)
    dst = OUT_LAWN / f"{world}.png"
    bg.save(dst, optimize=True)
    return {"world": world, "src": rel, "bytes": dst.stat().st_size}


def build_cg_lawn() -> dict:
    """中国园林没有专用草坪原图：用 Part 2 键艺做夜色庭院背景 + 程序化石板。"""
    bg = cover(load_rgba(RENDERS / WORLD_ART["chinesegarden"]), WIN).convert("RGB")
    bg = ImageEnhance.Brightness(bg).enhance(0.52).filter(ImageFilter.GaussianBlur(1))
    W, H = BOARD[2], BOARD[3]
    board = Image.new("RGB", (W, H), (203, 191, 165))
    px = board.load()
    import math
    import random
    rng = random.Random(20261001)
    for y in range(H):
        for x in range(W):
            base = 199 + 10 * math.sin(x * 0.021) + 8 * math.sin(y * 0.047)
            v = int(base + rng.randint(-6, 6))
            px[x, y] = (v + 8, v + 2, max(0, v - 18))
    d = ImageDraw.Draw(board)
    for c in range(1, 9):
        d.line([(c * 100, 0), (c * 100, H)], fill=(112, 98, 80), width=3)
    for r in range(1, 5):
        d.line([(0, r * 116), (W, r * 116)], fill=(112, 98, 80), width=3)
    for _ in range(60):
        x = rng.randint(0, W - 1)
        y = rng.randint(0, H - 1)
        d.line([(x, y), (x + rng.randint(-4, 4), y + rng.randint(-3, 3))],
               fill=(88, 108, 60), width=2)
    bg.paste(board, (BOARD[0], BOARD[1]))
    dd = ImageDraw.Draw(bg)
    dd.rectangle([BOARD[0] - 22, BOARD[1] - 22, BOARD[0] + W + 22, BOARD[1] + H + 22],
                 outline=(52, 40, 30), width=12)
    dd.rectangle([BOARD[0] - 30, BOARD[1] - 30, BOARD[0] + W + 30, BOARD[1] + H + 30],
                 outline=(126, 40, 34), width=4)
    OUT_LAWN.mkdir(parents=True, exist_ok=True)
    dst = OUT_LAWN / "chinesegarden.png"
    bg.save(dst, optimize=True)
    return {"world": "chinesegarden", "bytes": dst.stat().st_size, "mode": "synthetic"}


def main():
    manifest = {"art": {}, "worlds": [], "lawns": []}
    for world, items in ART.items():
        rows = []
        for slug, rel in items.items():
            rows.append(save_art(world, slug, rel))
        manifest["art"][world] = rows
        ok = sum(1 for r in rows if "error" not in r)
        print(f"art {world}: {ok}/{len(rows)}")
    for world, rel in WORLD_ART.items():
        manifest["worlds"].append(build_world(world, rel))
        print("world", world, "ok")
    for world, rel in LAWN_ART.items():
        manifest["lawns"].append(build_lawn(world, rel))
        print("lawn", world, "ok")
    manifest["lawns"].append(build_cg_lawn())
    print("lawn chinesegarden ok")
    out = ROOT / "tools" / "renders_manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print("manifest ->", out)


if __name__ == "__main__":
    main()
