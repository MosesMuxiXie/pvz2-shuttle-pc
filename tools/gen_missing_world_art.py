# -*- coding: utf-8 -*-
"""为缺少美术的世界生成程序化世界图/草坪（carnival / muji）。"""
import math, random, os
from PIL import Image, ImageDraw, ImageFilter

OUT_WORLD = "assets/world"; OUT_LAWN = "assets/lawn"
BX, BY, BW, BH = 190, 120, 900, 580
COLS, ROWS = 9, 5


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vgrad(size, top, bottom):
    w, h = size
    img = Image.new("RGB", size, top)
    d = ImageDraw.Draw(img)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(top, bottom, y / max(1, h - 1)))
    return img


def carnival_world():
    w, h = 1280, 720
    img = vgrad((w, h), (24, 18, 52), (78, 32, 92)).convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")
    rnd = random.Random(7)
    for _ in range(180):
        x, y = rnd.randrange(w), rnd.randrange(int(h * 0.62))
        r = rnd.choice([1, 1, 1, 2])
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 245, 210, rnd.randrange(120, 230)))
    # 月亮
    d.ellipse([1080, 60, 1170, 150], fill=(255, 246, 214, 235))
    d.ellipse([1100, 48, 1198, 146], fill=(30, 20, 58, 255))
    # 摩天轮
    cx, cy, R = 960, 350, 190
    d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=(255, 210, 120, 235), width=4)
    d.ellipse([cx - R + 26, cy - R + 26, cx + R - 26, cy + R - 26], outline=(255, 210, 120, 120), width=2)
    for i in range(12):
        a = i * math.pi / 6
        x2, y2 = cx + R * math.cos(a), cy + R * math.sin(a)
        d.line([(cx, cy), (x2, y2)], fill=(255, 200, 110, 150), width=3)
        cab = [(255, 92, 84), (92, 200, 255), (255, 196, 66), (160, 110, 255)]
        d.ellipse([x2 - 11, y2 - 11, x2 + 11, y2 + 11], fill=cab[i % 4] + (235,))
    d.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=(60, 34, 24, 255))
    # 马戏团帐篷
    def tent(x, base_y, tw, th, c1, c2):
        top = (x, base_y - th)
        d.polygon([top, (x - tw // 2, base_y), (x + tw // 2, base_y)], fill=c1)
        for i in range(6):
            xa = x - tw // 2 + i * tw / 6
            d.polygon([top, (xa, base_y), (xa + tw / 12, base_y)], fill=c2)
        d.rectangle([x - tw // 2 - 6, base_y - 8, x + tw // 2 + 6, base_y + 8], fill=(90, 46, 40))
        d.ellipse([top[0] - 5, top[1] - 5, top[0] + 5, top[1] + 5], fill=(255, 214, 120))
        d.line([top, (top[0], top[1] - 40)], fill=(220, 200, 160), width=3)
        d.polygon([(top[0], top[1] - 40), (top[0] + 26, top[1] - 30), (top[0], top[1] - 20)], fill=(255, 230, 130))
    tent(250, 620, 300, 240, (196, 46, 62, 255), (245, 220, 190, 255))
    tent(600, 600, 210, 170, (70, 90, 190, 255), (245, 220, 190, 255))
    # 串灯
    for sx in range(0, w, 160):
        pts = [(sx + i * 20, 84 + int(26 * math.sin(i / 20 * math.pi)))
               for i in range(9)]
        d.line(pts, fill=(120, 100, 80, 220), width=2)
        for (px, py) in pts[::2]:
            d.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(255, 230, 140, 240))
    # 前景草坪带
    d.rectangle([0, 640, w, h], fill=(42, 92, 52))
    for i in range(0, w, 12):
        d.line([(i, 640), (i + 6, h)], fill=(56, 112, 62, 160), width=3)
    return img.convert("RGB")


def carnival_lawn():
    w, h = 1280, 720
    img = vgrad((w, h), (30, 26, 56), (22, 44, 38)).convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")
    rnd = random.Random(3)
    for _ in range(90):
        x, y = rnd.randrange(w), rnd.randrange(40, 300)
        d.ellipse([x, y, x + rnd.randint(3, 7), y + rnd.randint(3, 7)],
                  fill=(255, 235, 170, rnd.randrange(90, 190)))
    cw, ch = BW // COLS, BH // ROWS
    for r in range(ROWS):
        for c in range(COLS):
            x0, y0 = BX + c * cw, BY + r * ch
            base = (46, 84, 52) if (r + c) % 2 == 0 else (38, 72, 46)
            d.rectangle([x0, y0, x0 + cw, y0 + ch], fill=base)
            d.line([(x0, y0), (x0 + cw, y0)], fill=(24, 44, 30, 170), width=2)
            d.line([(x0, y0), (x0, y0 + ch)], fill=(24, 44, 30, 170), width=2)
    d.rectangle([BX - 8, BY - 8, BX + BW + 8, BY + BH + 8],
                outline=(120, 86, 52, 255), width=8)
    # 彩旗
    for i in range(0, BW, 60):
        x = BX + i
        d.polygon([(x, BY - 46), (x + 26, BY - 46), (x + 13, BY - 14)],
                  fill=[(226, 70, 70), (240, 200, 80), (80, 160, 220), (150, 90, 200)][(i // 60) % 4])
    d.line([(BX, BY - 46), (BX + BW, BY - 46)], fill=(90, 70, 50), width=3)
    return img.convert("RGB")


def muji_world():
    w, h = 1280, 720
    img = vgrad((w, h), (244, 238, 226), (214, 202, 184)).convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([0, 470, w, h], fill=(176, 156, 128))
    for x in range(0, w, 80):
        d.line([(x, 470), (x, h)], fill=(158, 138, 112, 120), width=2)
    for y in range(470, h, 42):
        d.line([(0, y), (w, y)], fill=(158, 138, 112, 90), width=2)
    # 木质隔板与绿植
    for (sx, sy, sw) in [(70, 180, 300), (420, 140, 360), (830, 200, 330)]:
        d.rectangle([sx, sy, sx + sw, sy + 16], fill=(196, 172, 138))
        d.rectangle([sx, sy + 16, sx + sw, sy + 22], fill=(168, 144, 112))
    rnd = random.Random(5)
    for i in range(9):
        px = 100 + i * 125 + rnd.randrange(-12, 12)
        py = 250 + rnd.randrange(-20, 10)
        pot = (150, 120, 96)
        d.rounded_rectangle([px - 26, py, px + 26, py + 44], radius=8, fill=pot)
        for k in range(5):
            a = -math.pi / 2 + (k - 2) * 0.35
            ex, ey = px + int(46 * math.cos(a)), py + int(56 * math.sin(a))
            d.line([(px, py), (ex, ey)], fill=(78, 120, 82), width=7)
            d.ellipse([ex - 15, ey - 15, ex + 15, ey + 15], fill=(96, 148, 96))
    d.rectangle([0, 0, w, 8], fill=(150, 130, 108))
    return img.convert("RGB")


def muji_lawn():
    w, h = 1280, 720
    img = vgrad((w, h), (246, 240, 230), (226, 216, 200)).convert("RGBA")
    d = ImageDraw.Draw(img, "RGBA")
    cw, ch = BW // COLS, BH // ROWS
    for r in range(ROWS):
        for c in range(COLS):
            x0, y0 = BX + c * cw, BY + r * ch
            base = (222, 206, 182) if (r + c) % 2 == 0 else (212, 195, 170)
            d.rectangle([x0, y0, x0 + cw, y0 + ch], fill=base)
            for k in range(3):
                yy = y0 + 8 + k * (ch // 3)
                d.line([(x0 + 6, yy), (x0 + cw - 8, yy + 2)], fill=(196, 178, 152, 100), width=1)
            d.line([(x0, y0), (x0 + cw, y0)], fill=(188, 170, 146, 120), width=2)
            d.line([(x0, y0), (x0, y0 + ch)], fill=(188, 170, 146, 120), width=2)
    d.rectangle([BX - 10, BY - 10, BX + BW + 10, BY + BH + 10],
                outline=(170, 150, 124, 255), width=6)
    return img.convert("RGB")


def main():
    os.makedirs(OUT_WORLD, exist_ok=True)
    os.makedirs(OUT_LAWN, exist_ok=True)
    carnival_world().save(os.path.join(OUT_WORLD, "carnival.png"))
    carnival_lawn().save(os.path.join(OUT_LAWN, "carnival.png"))
    muji_world().save(os.path.join(OUT_WORLD, "muji.png"))
    muji_lawn().save(os.path.join(OUT_LAWN, "muji.png"))
    print("generated carnival / muji world+lawn art")


if __name__ == "__main__":
    main()
