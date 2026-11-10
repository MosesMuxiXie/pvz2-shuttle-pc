# -*- coding: utf-8 -*-
"""导入 heian/fairy/memorytour 的网络美术，并补齐 mausoleum/steam/renai/memorytour 的程序化世界图与草坪。"""
import math, os, random
from PIL import Image, ImageDraw, ImageFilter

SRC = "../work/art_research"
W, H = 1280, 720
BX, BY, BW, BH = 190, 120, 900, 580
COLS, ROWS = 9, 5


def cover(im, size=(W, H)):
    im = im.convert("RGBA")
    sw, sh = im.size
    scale = max(size[0] / sw, size[1] / sh)
    nw, nh = int(sw * scale + 0.5), int(sh * scale + 0.5)
    im = im.resize((nw, nh), Image.LANCZOS)
    x = (nw - size[0]) // 2
    y = (nh - size[1]) // 2
    return im.crop((x, y, x + size[0], y + size[1])).convert("RGB")


def composite_lawn(lawn_path, crop, out_path, tint=None):
    src = Image.open(lawn_path).convert("RGB")
    bg = cover(src)
    board = src.crop(crop).resize((BW, BH), Image.LANCZOS)
    if tint:
        board = Image.blend(board, Image.new("RGB", board.size, tint), 0.12)
    bg.paste(board, (BX, BY))
    d = ImageDraw.Draw(bg, "RGBA")
    d.rectangle([BX - 6, BY - 6, BX + BW + 6, BY + BH + 6], outline=(60, 48, 30, 200), width=3)
    bg.save(out_path)
    print("lawn", out_path, "crop", crop)


def imported():
    os.makedirs("assets/world", exist_ok=True)
    os.makedirs("assets/lawn", exist_ok=True)
    for wid, mapf in (("heian", "heian/map.png"), ("fairy", "fairy/map.png"),
                      ("memorytour", "memorytour/map.png")):
        im = Image.open(os.path.join(SRC, mapf))
        cover(im).save("assets/world/%s.png" % wid)
        print("world", wid, im.size)
    composite_lawn(os.path.join(SRC, "heian/lawn.png"), (1041, 235, 2607, 915),
                   "assets/lawn/heian.png", tint=(210, 200, 190))
    composite_lawn(os.path.join(SRC, "fairy/lawn.png"), (1066, 284, 3041, 1313),
                   "assets/lawn/fairy.png", tint=(220, 235, 200))


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vgrad(size, top, bottom):
    w, h = size
    img = Image.new("RGB", size, top)
    d = ImageDraw.Draw(img)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(top, bottom, y / max(1, h - 1)))
    return img


def tiled_lawn(bg, tile, line, name, deco):
    img = bg.convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")
    cw, ch = BW // COLS, BH // ROWS
    for r in range(ROWS):
        for c in range(COLS):
            x0, y0 = BX + c * cw, BY + r * ch
            base = tile if (r + c) % 2 == 0 else lerp(tile, (0, 0, 0), 0.08)
            d.rectangle([x0, y0, x0 + cw, y0 + ch], fill=base)
            d.line([(x0, y0), (x0 + cw, y0)], fill=line, width=2)
            d.line([(x0, y0), (x0, y0 + ch)], fill=line, width=2)
    d.rectangle([BX - 8, BY - 8, BX + BW + 8, BY + BH + 8], outline=line, width=6)
    deco(d)
    img.convert("RGB").save("assets/lawn/%s.png" % name)
    print("lawn", name)


def mausoleum():
    img = vgrad((W, H), (26, 24, 34), (12, 12, 18))
    d = ImageDraw.Draw(img, "RGBA")
    for i in range(14):
        x = 40 + i * 88
        d.rectangle([x, 60, x + 46, 300], fill=(58, 56, 66, 160))
        d.rectangle([x + 4, 66, x + 42, 300], fill=(40, 40, 50, 120))
    for i in range(90):
        rnd = random.Random(i)
        x, y = rnd.randrange(W), rnd.randrange(H)
        d.ellipse([x, y, x + rnd.randint(2, 6), y + rnd.randint(2, 6)],
                  fill=(120, 220, 160, rnd.randrange(30, 90)))
    img.save("assets/world/mausoleum.png")

    def deco(d):
        for cx, cy in ((BX - 40, BY + 40), (BX + BW + 40, BY + BH - 60)):
            d.rectangle([cx - 18, cy - 26, cx + 18, cy + 20], fill=(74, 72, 82))
            d.arc([cx - 18, cy - 42, cx + 18, cy - 6], 180, 360, fill=(120, 118, 126), width=6)
    tiled_lawn(vgrad((W, H), (34, 32, 40), (18, 18, 24)), (78, 76, 86), (40, 40, 48), "mausoleum", deco)


def steam():
    img = vgrad((W, H), (58, 44, 30), (26, 20, 14))
    d = ImageDraw.Draw(img, "RGBA")
    for i in range(10):
        cx, cy, r = 90 + i * 130, 120 + (i % 3) * 70, 34 + (i % 4) * 12
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(120, 92, 52, 90))
        d.ellipse([cx - r // 2, cy - r // 2, cx + r // 2, cy + r // 2], fill=(60, 46, 30, 120))
        for k in range(8):
            a = k * math.pi / 4
            d.line([(cx, cy), (cx + int(r * math.cos(a)), cy + int(r * math.sin(a)))],
                   fill=(160, 128, 70, 120), width=6)
    for x in range(0, W, 64):
        d.line([(x, 640), (x, H)], fill=(74, 54, 34, 120), width=6)
    img.save("assets/world/steam.png")

    def deco(d):
        for x in (BX - 46, BX + BW + 26):
            d.rectangle([x, BY + 60, x + 22, BY + BH - 60], fill=(92, 66, 36))
            for y in range(BY + 70, BY + BH - 60, 26):
                d.ellipse([x + 4, y, x + 18, y + 14], fill=(150, 120, 60))
    tiled_lawn(vgrad((W, H), (52, 40, 28), (30, 24, 16)), (122, 92, 56), (68, 48, 28), "steam", deco)


def renai():
    img = vgrad((W, H), (255, 214, 226), (232, 168, 196))
    d = ImageDraw.Draw(img, "RGBA")
    rnd = random.Random(11)
    for _ in range(70):
        x, y = rnd.randrange(W), rnd.randrange(H)
        s = rnd.randint(6, 16)
        d.text((x, y), "♥", fill=(255, 120, 160, rnd.randrange(60, 140)))
    for x in range(0, W, 120):
        d.line([(x, 560), (x + 60, H)], fill=(190, 120, 150, 90), width=8)
    img.save("assets/world/renai.png")

    def deco(d):
        for cx, cy in ((BX - 46, BY + 30), (BX + BW + 46, BY + BH - 30)):
            d.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=(230, 110, 150, 220))
            d.ellipse([cx - 6, cy - 16, cx + 6, cy + 4], fill=(255, 240, 246))
    tiled_lawn(vgrad((W, H), (255, 238, 244), (236, 196, 214)), (248, 214, 226), (226, 170, 194), "renai", deco)


def memorytour():
    img = vgrad((W, H), (30, 34, 48), (14, 16, 26))
    d = ImageDraw.Draw(img, "RGBA")
    for y in range(0, H, 6):
        d.line([(0, y), (W, y)], fill=(40, 48, 66, 40), width=2)
    for i in range(6):
        cx, cy = 120 + i * 200, 140
        d.rectangle([cx, cy, cx + 120, cy + 90], fill=(52, 58, 76))
        d.rectangle([cx + 6, cy + 6, cx + 114, cy + 84], fill=(20, 24, 34))
    img.save("assets/world/memorytour.png")

    def deco(d):
        for x in range(BX, BX + BW, 90):
            d.line([(x, BY - 16), (x, BY)], fill=(90, 96, 120, 160), width=4)
    tiled_lawn(vgrad((W, H), (44, 48, 64), (20, 22, 32)), (66, 72, 94), (34, 38, 52), "memorytour", deco)


def main():
    imported()
    mausoleum()
    steam()
    renai()
    memorytour()


if __name__ == "__main__":
    main()
