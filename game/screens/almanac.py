"""图鉴：植物 / 僵尸卡片网格 + 右侧详情面板。"""
from __future__ import annotations

import json
import math

import pygame

from ..config import CONTENT_DIR
from .base import Screen
from . import widgets as ui

GRID_RECT = pygame.Rect(40, 168, 780, 480)
CARD_W, CARD_H = 148, 152

_DB_ASSETS = None


def bind_assets(assets):
    """让图鉴优先使用 DragonBones 模型渲染的缩略图（缺失时退回程序化绘制）。"""
    global _DB_ASSETS
    _DB_ASSETS = assets

BEHAVIOR_ZH = {
    "shoot": "远程输出", "lob": "抛射", "instant": "一次性", "produce": "生产阳光",
    "wall": "高耐久", "support": "辅助", "spike": "地刺", "mine": "地雷",
    "boomerang": "回旋", "chomp": "近战", "fume": "范围伤害", "walk": "步行",
    "gargantuar": "巨型", "jump": "跳跃",
}
BEHAVIOR_TIP = {
    "shoot": "种在后排持续输出，注意用坚果类植物挡住僵尸。",
    "lob": "可以越过障碍抛射，适合打后排或高护甲目标。",
    "instant": "一次性植物，留到僵尸密集时再使用。",
    "produce": "尽早种下，稳定产出阳光，是卡组的发动机。",
    "wall": "放在前排吸收伤害，为后排射手争取时间。",
    "support": "辅助型植物，和输出植物搭配效果更好。",
    "spike": "铺在地面持续伤害经过的僵尸，不占主要输出位。",
    "mine": "需要时间准备，适合放在僵尸必经之路上。",
    "boomerang": "攻击可以往返，适合清理成排的僵尸。",
    "chomp": "近战吞噬，能快速解决高威胁目标。",
    "fume": "范围伤害，适合应对密集的僵尸群。",
    "walk": "普通僵尸，单个并不可怕，成群时才危险。",
    "gargantuar": "巨型僵尸，生命极高，需要集中火力或使用秒杀植物。",
    "jump": "会跳过第一株植物，注意后排保护。",
}


def behavior_zh(value):
    return BEHAVIOR_ZH.get(str(value or "").strip().lower(), str(value or "未知"))
GAP_X, GAP_Y = 20, 14
COLS = 5

FALLBACK_PLANTS = [
    ("sunflower", "向日葵", "Sunflower", 50, 300, "阳光", "产阳光",
     "每 24 秒生产 25 点阳光，是草坪上最可靠的阳光来源。种得越多，阳光越充裕。"),
    ("peashooter", "豌豆射手", "Peashooter", 100, 300, "攻击", "直线攻击",
     "向本行最前方的僵尸发射豌豆，射速稳定，是新手园丁的第一道防线。"),
    ("wallnut", "坚果墙", "Wall-nut", 50, 4000, "防御", "高生命",
     "厚实的外壳可以挡住僵尸很久。把它种在射手前面，为后排争取输出时间。"),
    ("snowpea", "寒冰射手", "Snow Pea", 175, 300, "减速", "冰冻",
     "发射冰冻豌豆，命中后降低僵尸移动与啃食速度。控场能力出色。"),
    ("repeater", "双发射手", "Repeater", 200, 300, "攻击", "双发",
     "一次发射两颗豌豆，输出是豌豆射手的双倍，但需要更多阳光。"),
    ("cherrybomb", "樱桃炸弹", "Cherry Bomb", 150, 300, "爆炸", "范围伤害",
     "种下后短暂延迟并爆炸，消灭周围 3x3 范围内的僵尸。关键时刻的救场神器。"),
    ("potatomine", "土豆地雷", "Potato Mine", 25, 300, "陷阱", "延时爆炸",
     "埋入地下需要时间准备。准备完成后，任何踩上来的僵尸都会被炸飞。"),
    ("chomper", "大嘴花", "Chomper", 150, 300, "近战", "吞食",
     "一口吞掉靠近的僵尸，但咀嚼期间无法攻击。适合配合减速植物使用。"),
    ("torchwood", "火炬树桩", "Torchwood", 175, 300, "增益", "点燃豌豆",
     "穿过火炬树桩的豌豆会变成火球，伤害翻倍，并可点燃部分特殊僵尸。"),
    ("threepeater", "三线射手", "Threepeater", 325, 300, "攻击", "三行攻击",
     "同时向自己所在行及上下两行发射豌豆，适合放在草坪中央。"),
    ("cabbagepult", "卷心菜投手", "Cabbage-pult", 100, 300, "抛射", "越墙",
     "把卷心菜抛向本行最前方的僵尸，可以越过障碍物命中目标。"),
    ("iceberg", "寒冰菇", "Iceberg Lettuce", 75, 300, "控制", "冻结",
     "接触到的僵尸会被短暂冻结，为其他植物争取宝贵的输出时间。"),
    ("darkdragonfruit", "暗物质火龙果", "Dark Dragonfruit", 300, 500, "元素", "元素反应",
     "26.10.1 全新植物。以暗物质能量攻击整行僵尸，并有概率触发元素反应，造成额外效果。"),
    ("angelstarfruit", "天使星星果", "Angel Starfruit", 250, 300, "增益", "强化",
     "26.10.1 植物强化计划成员。为周围植物提供攻击增益，星光会照亮整片草坪。"),
]

FALLBACK_ZOMBIES = [
    ("basic", "普通僵尸", "Basic Zombie", 200, "慢", "普通", "没有护甲，移动缓慢。"),
    ("flag", "旗帜僵尸", "Flag Zombie", 200, "慢", "召唤", "举着旗帜，标志着一大波僵尸的到来。"),
    ("conehead", "路障僵尸", "Conehead Zombie", 560, "慢", "防御", "头戴路障，护甲值中等。"),
    ("buckethead", "铁桶僵尸", "Buckethead Zombie", 1300, "慢", "防御", "铁桶提供了极高的护甲，需要集中火力。"),
    ("polevault", "撑杆僵尸", "Pole Vaulting Zombie", 500, "快", "跳跃", "奔跑并撑杆跳过第一株植物，之后变为普通僵尸。"),
    ("screendoor", "铁门僵尸", "Screen Door Zombie", 1100, "慢", "护盾", "铁门可以挡住正面射来的豌豆，需要从侧面或后方突破。"),
    ("gargantuar", "巨人僵尸", "Gargantuar", 3000, "极慢", "重型", "挥舞电线杆，一击摧毁植物，生命值极高。"),
    ("icewatermelon", "冰西瓜投手僵尸", "Ice Watermelon Zombie", 900, "慢", "远程", "26.10.1 新僵尸。投掷冰冻西瓜，命中后减速植物。"),
    ("lightningreed", "闪电芦苇僵尸", "Lightning Reed Zombie", 700, "中", "远程", "26.10.1 新僵尸。释放连锁闪电，攻击多个目标。"),
    ("flowertuber", "气流水仙花僵尸", "Aerated Water-nymph Zombie", 650, "中", "控制", "26.10.1 新僵尸。用气流推开植物，打乱你的防线。"),
    ("lotus", "莲藕射手僵尸", "Lotus Archer Zombie", 600, "中", "水下", "26.10.1 新僵尸。从水下发射莲藕，难以被提前发现。"),
]


def _family_color(family, kind):
    if kind == "zombie":
        return (126, 138, 110), (76, 92, 72)
    return {
        "阳光": ((246, 206, 90), (196, 146, 40)),
        "攻击": ((126, 186, 92), (68, 128, 62)),
        "防御": ((196, 160, 112), (128, 92, 56)),
        "减速": ((122, 182, 210), (62, 118, 154)),
        "冰冻": ((122, 182, 210), (62, 118, 154)),
        "爆炸": ((224, 120, 90), (160, 62, 48)),
        "陷阱": ((210, 156, 84), (140, 94, 44)),
        "近战": ((172, 126, 190), (104, 66, 124)),
        "增益": ((246, 196, 92), (184, 126, 40)),
        "抛射": ((154, 186, 104), (92, 130, 62)),
        "控制": ((146, 196, 208), (76, 130, 148)),
        "元素": ((206, 112, 176), (120, 58, 108)),
    }.get(family, ((166, 190, 120), (92, 130, 74)))


def draw_entry_art(surf, rect, entry, kind, scale=1.0):
    """程序化绘制植物 / 僵尸小像。"""
    rect = pygame.Rect(rect)
    x, y, w, h = rect
    cx = x + w / 2
    c1, c2 = _family_color(entry.get("family"), kind)
    d = int(min(w, h))
    # 背景圆
    circle = pygame.Surface((d + 8, d + 8), pygame.SRCALPHA)
    pygame.draw.circle(circle, (*ui.shade(c2, 0.9), 60), (d // 2 + 4, d // 2 + 4), d // 2 + 2)
    pygame.draw.circle(circle, (*c1, 44), (d // 2 + 4, d // 2 + 4), int(d * 0.42))
    surf.blit(circle, (cx - d / 2 - 4, y + h / 2 - d / 2 - 4))

    if _DB_ASSETS is not None:
        art = str(entry.get("art") or "")
        if art:
            try:
                _arm = None if kind == "zombie" else entry.get("armature")
                img = _DB_ASSETS.db_thumb(art, d, d, armature=_arm)
            except Exception:
                img = None
            if img is not None:
                surf.blit(img, img.get_rect(center=(int(cx), int(y + h * 0.52))))
                return
        if _DB_ASSETS is not None and entry.get("art"):
            try:
                spr = _DB_ASSETS.static_sprite(str(entry.get("art") or ""),
                                               max(24, int(d * 0.62)))
                if spr is not None:
                    if spr.get_width() > w - 6:
                        nw = w - 6
                        spr = pygame.transform.smoothscale(
                            spr, (nw, max(1, int(spr.get_height() * nw / spr.get_width()))))
                    surf.blit(spr, spr.get_rect(center=(int(cx), int(y + h * 0.52))))
                    return
            except Exception:
                pass

    s = d / 100.0
    base = y + h * 0.84
    if kind == "plant":
        eid = entry.get("id", "")
        # 茎与叶
        pygame.draw.line(surf, (74, 118, 52), (cx, base), (cx, base - 38 * s), max(2, int(4 * s)))
        pygame.draw.ellipse(surf, (98, 152, 68),
                            (cx - 26 * s, base - 18 * s, 24 * s, 12 * s))
        pygame.draw.ellipse(surf, (84, 138, 60),
                            (cx + 2 * s, base - 12 * s, 24 * s, 12 * s))
        head = (cx, base - 54 * s)
        if eid in ("sunflower", "angelstarfruit", "darkdragonfruit"):
            petals = 12 if eid != "darkdragonfruit" else 8
            petal_color = {"sunflower": (250, 206, 74),
                           "angelstarfruit": (250, 226, 150),
                           "darkdragonfruit": (168, 74, 152)}[eid]
            for i in range(petals):
                ang = i * math.tau / petals
                px = head[0] + math.cos(ang) * 26 * s
                py = head[1] + math.sin(ang) * 26 * s
                pygame.draw.circle(surf, petal_color, (int(px), int(py)), int(12 * s))
            center = {"sunflower": (128, 82, 34),
                      "angelstarfruit": (238, 178, 60),
                      "darkdragonfruit": (74, 40, 66)}[eid]
            pygame.draw.circle(surf, center, (int(head[0]), int(head[1])), int(19 * s))
            if eid == "darkdragonfruit":
                pygame.draw.circle(surf, (232, 214, 250), (int(head[0]), int(head[1])),
                                   int(7 * s))
        elif eid in ("peashooter", "snowpea", "repeater", "threepeater", "cabbagepult"):
            color = (98, 168, 72) if eid not in ("snowpea",) else (122, 190, 180)
            pygame.draw.circle(surf, color, (int(head[0] - 6 * s), int(head[1])),
                               int(25 * s))
            pygame.draw.circle(surf, ui.shade(color, 0.8),
                               (int(head[0] + 18 * s), int(head[1] - 3 * s)),
                               int(10 * s))
            pygame.draw.circle(surf, (28, 42, 24), (int(head[0] + 2 * s), int(head[1] - 6 * s)),
                               max(2, int(4 * s)))
            pygame.draw.circle(surf, (255, 255, 255),
                               (int(head[0] + 3 * s), int(head[1] - 7 * s)),
                               max(1, int(1.6 * s)))
            if eid == "repeater":
                pygame.draw.circle(surf, ui.shade(color, 0.75),
                                   (int(head[0] + 30 * s), int(head[1] + 7 * s)),
                                   int(7 * s))
        elif eid == "wallnut":
            pygame.draw.ellipse(surf, (196, 154, 92),
                                (cx - 30 * s, base - 84 * s, 60 * s, 82 * s))
            pygame.draw.ellipse(surf, (168, 124, 68),
                                (cx - 30 * s, base - 84 * s, 60 * s, 82 * s), max(2, int(2 * s)))
            for ex in (-10, 10):
                pygame.draw.circle(surf, (52, 38, 24),
                                   (int(cx + ex * s), int(base - 52 * s)), max(2, int(3 * s)))
            pygame.draw.arc(surf, (72, 48, 28),
                            (cx - 12 * s, base - 44 * s, 24 * s, 14 * s), 0, math.pi,
                            max(2, int(2 * s)))
        elif eid == "chomper":
            pygame.draw.circle(surf, (118, 66, 142), (int(head[0]), int(head[1])),
                               int(28 * s))
            pygame.draw.arc(surf, (50, 24, 54),
                            (cx - 28 * s, head[1] - 10 * s, 56 * s, 40 * s),
                            math.pi, math.tau, max(2, int(4 * s)))
            for i in range(3):
                pygame.draw.line(surf, (244, 238, 220),
                                 (cx - 18 * s + i * 14 * s, head[1] + 10 * s),
                                 (cx - 16 * s + i * 14 * s, head[1] + 17 * s), 2)
            pygame.draw.circle(surf, (28, 26, 24), (int(head[0] + 12 * s), int(head[1] - 10 * s)),
                               max(2, int(4 * s)))
        elif eid == "cherrybomb":
            for dx, col in ((-14, (206, 64, 52)), (14, (178, 48, 44))):
                pygame.draw.circle(surf, col, (int(cx + dx * s), int(base - 44 * s)),
                                   int(20 * s))
            pygame.draw.line(surf, (74, 118, 52), (cx - 10 * s, base - 58 * s),
                             (cx + 8 * s, base - 72 * s), max(2, int(3 * s)))
        elif eid == "potatomine":
            pygame.draw.ellipse(surf, (172, 138, 92),
                                (cx - 26 * s, base - 34 * s, 52 * s, 30 * s))
            pygame.draw.circle(surf, (70, 52, 32), (int(cx - 8 * s), int(base - 22 * s)),
                               max(2, int(3 * s)))
            pygame.draw.circle(surf, (70, 52, 32), (int(cx + 8 * s), int(base - 22 * s)),
                               max(2, int(3 * s)))
        elif eid == "torchwood":
            pygame.draw.rect(surf, (114, 76, 42),
                             (cx - 14 * s, base - 54 * s, 28 * s, 54 * s), border_radius=6)
            flame = [(cx, base - 86 * s), (cx + 16 * s, base - 60 * s),
                     (cx + 4 * s, base - 56 * s), (cx, base - 70 * s),
                     (cx - 8 * s, base - 54 * s), (cx - 16 * s, base - 62 * s)]
            pygame.draw.polygon(surf, (242, 152, 52), flame)
            pygame.draw.polygon(surf, (250, 216, 98),
                                [(cx, base - 76 * s), (cx + 8 * s, base - 60 * s),
                                 (cx - 6 * s, base - 58 * s)])
        elif eid == "cactus":
            pygame.draw.rect(surf, (92, 158, 82),
                             (cx - 12 * s, base - 74 * s, 24 * s, 74 * s), border_radius=10)
            for i in range(4):
                yy = base - (16 + i * 14) * s
                pygame.draw.line(surf, (222, 238, 190), (cx - 12 * s, yy),
                                 (cx - 20 * s, yy - 4 * s), 2)
                pygame.draw.line(surf, (222, 238, 190), (cx + 12 * s, yy),
                                 (cx + 20 * s, yy - 4 * s), 2)
            pygame.draw.circle(surf, (32, 54, 30), (int(cx), int(base - 58 * s)),
                               max(2, int(3 * s)))
        else:
            pygame.draw.circle(surf, c1, (int(head[0]), int(head[1])), int(24 * s))
            pygame.draw.circle(surf, ui.shade(c2, 0.9),
                               (int(head[0]), int(head[1])), int(24 * s), max(2, int(2 * s)))
            pygame.draw.circle(surf, (32, 44, 28), (int(head[0] - 7 * s), int(head[1] - 4 * s)),
                               max(2, int(3 * s)))
            pygame.draw.circle(surf, (32, 44, 28), (int(head[0] + 7 * s), int(head[1] - 4 * s)),
                               max(2, int(3 * s)))
    else:
        eid = entry.get("id", "")
        giant = eid == "gargantuar"
        bw, bh = (46, 42) if giant else (34, 34)
        body_y = base - bh * s
        pygame.draw.rect(surf, (78, 88, 68),
                         (cx - bw * s / 2, body_y, bw * s, bh * s), border_radius=int(6 * s))
        pygame.draw.rect(surf, (54, 62, 48),
                         (cx - bw * s / 2, body_y, bw * s, bh * s), max(1, int(1.5 * s)),
                         border_radius=int(6 * s))
        # 手臂
        pygame.draw.line(surf, (140, 158, 118), (cx - bw * s / 2, body_y + 8 * s),
                         (cx - bw * s / 2 - 14 * s, body_y + 24 * s), max(3, int(5 * s)))
        pygame.draw.line(surf, (140, 158, 118), (cx + bw * s / 2, body_y + 8 * s),
                         (cx + bw * s / 2 + 12 * s, body_y + 20 * s), max(3, int(5 * s)))
        # 头
        hr = (19 if giant else 16) * s
        hx, hy = cx, body_y - hr * 0.6
        pygame.draw.circle(surf, (150, 168, 124), (int(hx), int(hy)), int(hr))
        pygame.draw.circle(surf, (108, 126, 88), (int(hx), int(hy)), int(hr), max(1, int(2 * s)))
        # 眼睛
        pygame.draw.circle(surf, (240, 240, 214), (int(hx - hr * 0.38), int(hy - hr * 0.15)),
                           max(2, int(4 * s)))
        pygame.draw.circle(surf, (240, 240, 214), (int(hx + hr * 0.38), int(hy - hr * 0.15)),
                           max(2, int(4 * s)))
        pygame.draw.circle(surf, (36, 30, 24), (int(hx - hr * 0.34), int(hy - hr * 0.12)),
                           max(1, int(2 * s)))
        pygame.draw.circle(surf, (36, 30, 24), (int(hx + hr * 0.42), int(hy - hr * 0.12)),
                           max(1, int(2 * s)))
        # 嘴与牙
        pygame.draw.line(surf, (60, 46, 34), (hx - hr * 0.45, hy + hr * 0.35),
                         (hx + hr * 0.45, hy + hr * 0.35), max(2, int(2.5 * s)))
        for tx in (-0.25, 0.0, 0.25):
            pygame.draw.line(surf, (238, 232, 208),
                             (hx + hr * tx, hy + hr * 0.3),
                             (hx + hr * tx, hy + hr * 0.46), max(1, int(1.5 * s)))
        # 护甲 / 道具
        if eid == "conehead":
            pygame.draw.polygon(surf, (206, 118, 44),
                                [(hx - hr * 0.9, hy - hr * 0.4), (hx, hy - hr * 2.1),
                                 (hx + hr * 0.9, hy - hr * 0.4)])
        elif eid == "buckethead":
            pygame.draw.rect(surf, (146, 150, 148),
                             (hx - hr * 0.95, hy - hr * 1.7, hr * 1.9, hr * 1.25),
                             border_radius=int(3 * s))
            pygame.draw.rect(surf, (104, 108, 106),
                             (hx - hr * 0.95, hy - hr * 1.7, hr * 1.9, hr * 1.25),
                             max(1, int(2 * s)), border_radius=int(3 * s))
        elif eid == "flag":
            pygame.draw.line(surf, (98, 74, 46), (hx + hr, hy - hr * 1.7),
                             (hx + hr, hy + hr * 0.6), max(2, int(2 * s)))
            pygame.draw.polygon(surf, (200, 66, 52),
                                [(hx + hr, hy - hr * 1.6), (hx + hr * 2.4, hy - hr * 1.2),
                                 (hx + hr, hy - hr * 0.8)])
        elif eid == "screendoor":
            pygame.draw.rect(surf, (128, 132, 128),
                             (hx + hr * 0.4, hy - hr * 1.2, hr * 1.4, hr * 2.2),
                             border_radius=int(3 * s))
        elif giant:
            pygame.draw.line(surf, (108, 82, 52), (hx + hr * 1.8, hy - hr * 3),
                             (hx + hr * 1.4, hy + hr * 2.4), max(4, int(7 * s)))
        elif eid in ("icewatermelon", "lightningreed"):
            tint = (110, 176, 210) if eid == "icewatermelon" else (228, 210, 90)
            pygame.draw.circle(surf, tint, (int(hx), int(hy)), int(hr * 1.25),
                               max(2, int(3 * s)))
            pygame.draw.circle(surf, tint, (int(hx + hr * 0.9), int(hy - hr * 0.9)),
                               max(2, int(4 * s)))
        elif eid == "flowertuber":
            pygame.draw.circle(surf, (226, 160, 190), (int(hx), int(hy)), int(hr * 1.15),
                               max(2, int(3 * s)))


class AlmanacScreen(Screen):
    name = "almanac"

    def __init__(self, app):
        super().__init__(app)
        self.W, self.H = app.screen.get_size()
        bind_assets(getattr(app, "assets", None))
        self.kind = "plant"
        self.entries = {"plant": [], "zombie": []}
        self.selected = {"plant": 0, "zombie": 0}
        self.hover = -1
        self.scroll = ui.ScrollPanel(app, GRID_RECT, step=64)
        self._fonts = {}
        self._desc = {}
        self._cards = []
        self._bg = None
        self.btn_back = ui.Button(
            app, (24, 20, 110, 44), "返回", on_click=lambda: app.switch("menu"),
            style="cream", font_size=18)
        self.tabs = ui.ToggleGroup(
            app, (40, 104, 330, 46), ("植物图鉴", "僵尸图鉴"), 0,
            on_change=self._on_tab, font_size=18, style="segmented", radius=12)

    # ------------------------------------------------------------------
    def enter(self):
        super().enter()
        self._load_desc()
        self._build_entries()
        self.kind = "plant"
        self.tabs.set_selected(0)
        self.selected = {"plant": 0, "zombie": 0}
        self.hover = -1
        self._rebuild()
        self.scroll.reset()

    def exit(self):
        pass

    def _font(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = self.app.font(size, bold)
        return self._fonts[key]

    def _load_desc(self):
        self._desc = {}
        path = CONTENT_DIR / "almanac.json"
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for key in ("plants", "zombies"):
                        block = data.get(key)
                        if isinstance(block, dict):
                            for eid, val in block.items():
                                if isinstance(val, str):
                                    self._desc[eid] = val
                                elif isinstance(val, dict):
                                    self._desc[eid] = val.get("desc_zh") or val.get("desc") or ""
                        elif isinstance(block, list):
                            for item in block:
                                if isinstance(item, dict) and item.get("id"):
                                    self._desc[item["id"]] = (
                                        item.get("desc_zh") or item.get("desc") or "")
                    for eid, val in data.items():
                        if eid in ("plants", "zombies"):
                            continue
                        if isinstance(val, str):
                            self._desc.setdefault(eid, val)
                        elif isinstance(val, dict):
                            self._desc.setdefault(
                                eid, val.get("desc_zh") or val.get("desc") or "")
        except Exception:
            self._desc = {}

    def _raw(self, kind):
        try:
            if kind == "plant":
                data = self.app.data.plants
            else:
                data = self.app.data.zombies
            if isinstance(data, dict):
                return list(data.values())
            if isinstance(data, (list, tuple)):
                return list(data)
        except Exception:
            pass
        return []

    @staticmethod
    def _get(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def _build_entries(self):
        plants = self._raw("plant")
        zombies = self._raw("zombie")
        self.entries["plant"] = []
        for i, p in enumerate(plants):
            self.entries["plant"].append({
                "id": self._get(p, "id", f"plant{i}"),
                "name_zh": self._get(p, "name_zh", "未知植物"),
                "name_en": self._get(p, "name_en", ""),
                "cost": int(self._get(p, "cost", 0) or 0),
                "hp": int(self._get(p, "hp", 0) or 0),
                "family": self._get(p, "family", "攻击") or "攻击",
                "behavior": self._get(p, "behavior", "") or "未知",
                "desc": self._desc.get(self._get(p, "id", ""), "")
                        or self._get(p, "desc_zh", "") or "暂无图鉴描述。",
                "tags": list(self._get(p, "tags", []) or []),
                "almanac_no": self._get(p, "almanac_no", i + 1),
                "art": self._get(p, "art", ""),
            })
        self.entries["zombie"] = []
        for i, z in enumerate(zombies):
            armor = list(self._get(z, "armor", []) or [])
            base_hp = int(self._get(z, "hp", 0) or 0)
            armor_hp = sum(int(a.get("hp", 0) or 0) for a in armor if isinstance(a, dict))
            armature = self._get(z, "armature", None)
            if not armature and armor and isinstance(armor[0], dict):
                armature = armor[0].get("armature")
            self.entries["zombie"].append({
                "id": self._get(z, "id", f"zombie{i}"),
                "name_zh": self._get(z, "name_zh", "未知僵尸"),
                "name_en": self._get(z, "name_en", ""),
                "cost": 0,
                "hp": base_hp + armor_hp,
                "base_hp": base_hp,
                "armor_hp": armor_hp,
                "family": "僵尸",
                "behavior": self._get(z, "behavior", "") or self._get(z, "armor", "")
                            or "普通",
                "desc": self._desc.get(self._get(z, "id", ""), "")
                        or self._get(z, "desc_zh", "") or "暂无图鉴描述。",
                "tags": list(self._get(z, "tags", []) or []),
                "almanac_no": self._get(z, "almanac_no", i + 1),
                "speed": self._get(z, "speed", ""),
                "art": self._get(z, "art", ""),
                "armature": armature,
            })
        if not self.entries["plant"]:
            for i, (eid, zh, en, cost, hp, family, behavior, desc) in enumerate(
                    FALLBACK_PLANTS):
                self.entries["plant"].append({
                    "id": eid, "name_zh": zh, "name_en": en, "cost": cost,
                    "hp": hp, "family": family, "behavior": behavior, "desc": desc,
                    "tags": [behavior], "almanac_no": i + 1,
                })
        if not self.entries["zombie"]:
            for i, (eid, zh, en, hp, speed, behavior, desc) in enumerate(
                    FALLBACK_ZOMBIES):
                self.entries["zombie"].append({
                    "id": eid, "name_zh": zh, "name_en": en, "cost": 0, "hp": hp,
                    "family": "僵尸", "behavior": behavior, "desc": desc,
                    "tags": [behavior], "almanac_no": i + 1, "speed": speed,
                })

    # ------------------------------------------------------------------
    def _on_tab(self, index):
        self.kind = "plant" if index == 0 else "zombie"
        self.hover = -1
        self._rebuild()
        self.scroll.reset()

    def _rebuild(self):
        entries = self.entries[self.kind]
        n = len(entries)
        rows = max(1, (n + COLS - 1) // COLS)
        content_h = rows * (CARD_H + GAP_Y) + 8
        self.scroll.set_content_height(content_h)
        self._cards = []
        for i in range(n):
            col, row = i % COLS, i // COLS
            x = GRID_RECT.x + col * (CARD_W + GAP_X)
            y = GRID_RECT.y + row * (CARD_H + GAP_Y)
            self._cards.append(pygame.Rect(x, y, CARD_W, CARD_H))
        sel = self.selected.get(self.kind, 0)
        if n:
            self.selected[self.kind] = ui.clamp(sel, 0, n - 1)

    def _entry_at(self, pos):
        for i, r in enumerate(self._cards):
            rr = r.move(0, -int(self.scroll.offset))
            if rr.collidepoint(pos):
                return i
        return -1

    # ------------------------------------------------------------------
    def handle(self, event):
        super().handle(event)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.app.switch("menu")
                return
            if event.key == pygame.K_TAB:
                self.tabs.set_selected(1 - self.tabs.selected, notify=True)
                return
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                self._move_selection(event.key)
                return
        if self.btn_back.handle(event):
            return
        if self.tabs.handle(event):
            if self.tabs.style == "tabs":
                pass
            return
        if event.type == pygame.MOUSEWHEEL:
            if GRID_RECT.collidepoint(self.mouse):
                self.scroll.scroll_by(-event.y * 64)
            return
        if event.type == pygame.MOUSEMOTION:
            self.hover = self._entry_at(event.pos)
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            idx = self._entry_at(event.pos)
            if idx >= 0:
                self.selected[self.kind] = idx
                return
        if self.scroll.handle(event):
            return

    def _move_selection(self, key):
        entries = self.entries[self.kind]
        if not entries:
            return
        i = self.selected[self.kind]
        if key == pygame.K_LEFT:
            i -= 1
        elif key == pygame.K_RIGHT:
            i += 1
        elif key == pygame.K_UP:
            i -= COLS
        else:
            i += COLS
        i = ui.clamp(i, 0, len(entries) - 1)
        self.selected[self.kind] = i
        # 让选中项滚入视野
        row = i // COLS
        top = row * (CARD_H + GAP_Y)
        if top < self.scroll.offset:
            self.scroll.scroll_to(top)
        elif top + CARD_H > self.scroll.offset + GRID_RECT.h:
            self.scroll.scroll_to(top + CARD_H - GRID_RECT.h)

    # ------------------------------------------------------------------
    def update(self, dt):
        super().update(dt)

    def draw(self, surf):
        self._draw_background(surf)
        self._draw_header(surf)
        self._draw_grid(surf)
        self._draw_side(surf)
        self.draw_fade(surf)

    def _draw_background(self, surf):
        ui.draw_gradient(surf, surf.get_rect(), (248, 242, 230), (224, 214, 194))
        # 淡淡的叶片纹理
        layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        for i in range(12):
            x = (i * 137 + 60) % self.W
            y = (i * 211 + 80) % self.H
            pygame.draw.ellipse(layer, (120, 150, 100, 12),
                                (x, y, 120, 54))
        surf.blit(layer, (0, 0))

    def _draw_header(self, surf):
        bar = pygame.Rect(0, 0, self.W, 88)
        ui.draw_gradient(surf, bar, (98, 70, 46), (68, 48, 32))
        pygame.draw.line(surf, (247, 201, 72), (0, 86), (self.W, 86), 2)
        self.btn_back.draw(surf)
        ui.text(surf, self._font(26, True), "植物与僵尸图鉴",
                (154, 36), (253, 246, 226), anchor="midleft", shadow=(28, 20, 12))
        ui.text(surf, self._font(11, False), "ALMANAC · 记录草坪上遇到的每一种生命",
                (156, 64), (212, 200, 176), anchor="midleft")
        ui.draw_coin(surf, (self.W - 180, 44), 10)
        ui.text(surf, self._font(15, True), str(int(getattr(self.app.save, "coins", 0))),
                (self.W - 160, 44), (250, 238, 210), anchor="midleft")

    def _draw_grid(self, surf):
        self.tabs.draw(surf)
        n_plant = len(self.entries["plant"])
        n_zombie = len(self.entries["zombie"])
        ui.text(surf, self._font(12, False), f"植物 {n_plant} 种  ·  僵尸 {n_zombie} 种",
                (self.tabs.rect.right + 16, self.tabs.rect.centery),
                ui.INK_FAINT, anchor="midleft")
        ui.text(surf, self._font(12, False), "滚轮浏览 · 点击查看详情",
                (GRID_RECT.right, self.tabs.rect.centery), ui.INK_FAINT,
                anchor="midright")

        # 网格背景底板
        board = pygame.Rect(GRID_RECT.x - 10, GRID_RECT.y - 10,
                            GRID_RECT.w + 20, GRID_RECT.h + 20)
        ui.draw_panel(surf, board, (248, 243, 233), (220, 209, 190), radius=12,
                      border_width=1, shadow=False)

        old = surf.get_clip()
        surf.set_clip(GRID_RECT)
        for i, r in enumerate(self._cards):
            rr = r.move(0, -int(self.scroll.offset))
            if rr.bottom < GRID_RECT.y - 10 or rr.top > GRID_RECT.bottom + 10:
                continue
            self._draw_card(surf, i, rr, self.entries[self.kind][i],
                            i == self.selected[self.kind], i == self.hover)
        surf.set_clip(old)
        self.scroll.draw_scrollbar(surf)

        if not self.entries[self.kind]:
            ui.text(surf, self._font(18, True), "暂无图鉴数据",
                    GRID_RECT.center, ui.INK_FAINT, anchor="center")

    def _draw_card(self, surf, i, rect, entry, selected, hover):
        # 参考原版图鉴：深蓝种子包卡面 + 金色描边 + 底部阳光价签。
        lift = -3 if hover or selected else 0
        card = rect.move(0, lift)
        ui.draw_shadow(surf, card, radius=10, alpha=44, offset=(0, 3), spread=3)
        ui.draw_gradient(surf, card, (34, 48, 78), (18, 28, 48), radius=10)
        if selected:
            pygame.draw.rect(surf, (255, 214, 110), card, 3, border_radius=10)
            pygame.draw.rect(surf, (120, 96, 52), card.inflate(-6, -6), 1,
                             border_radius=8)
        elif hover:
            pygame.draw.rect(surf, (240, 206, 120), card, 2, border_radius=10)
        else:
            pygame.draw.rect(surf, (150, 130, 82), card, 2, border_radius=10)
        # 顶部高光
        gloss = pygame.Rect(card.x + 6, card.y + 5, card.w - 12, 10)
        pygame.draw.rect(surf, (92, 112, 148), gloss, border_radius=5)
        # 编号
        ui.text(surf, self._font(10, True), f"{entry.get('almanac_no', i + 1):02d}",
                (card.x + 8, card.y + 7), (246, 232, 196), anchor="topleft")
        if self.kind == "plant" and entry.get("cost") is not None:
            price_font = self._font(10, True)
            label = str(entry.get("cost", 0))
            pw = price_font.size(label)[0] + 26
            pill = pygame.Rect(card.right - pw - 6, card.bottom - 24, pw, 18)
            pygame.draw.rect(surf, (246, 226, 150), pill, border_radius=9)
            pygame.draw.circle(surf, (244, 196, 62), (pill.x + 10, pill.centery), 6)
            pygame.draw.circle(surf, (176, 128, 34), (pill.x + 10, pill.centery), 6, 1)
            ui.text(surf, price_font, label, (pill.x + 19, pill.centery),
                    (72, 54, 24), anchor="midleft")
        art_rect = pygame.Rect(card.centerx - 33, card.y + 22, 66, 66)
        draw_entry_art(surf, art_rect, entry, self.kind, 1.0)
        name_font = self._font(14, True)
        name = ui.fit_text(name_font, entry.get("name_zh", "?"), card.w - 16)
        ui.text(surf, name_font, name, (card.centerx, card.y + 96), (255, 248, 226),
                anchor="midtop", shadow=(6, 10, 20))
        bfont = self._font(9, False)
        behavior = behavior_zh(entry.get("behavior", ""))
        ui.text(surf, bfont, ui.fit_text(bfont, behavior, max(30, card.w - 62)),
                (card.x + 8, card.bottom - 16), (196, 206, 224), anchor="midleft")

    def _draw_side(self, surf):
        panel = pygame.Rect(844, 104, 396, 548)
        ui.draw_panel(surf, panel, ui.PAPER, (198, 182, 158), radius=14,
                      border_width=2, shadow_alpha=60)
        entries = self.entries[self.kind]
        if not entries:
            ui.text(surf, self._font(16, False), "选择左侧条目查看详情",
                    panel.center, ui.INK_FAINT, anchor="center")
            return
        idx = ui.clamp(self.selected[self.kind], 0, len(entries) - 1)
        entry = entries[idx]
        c1, c2 = _family_color(entry.get("family"), self.kind)

        # 绿色标题条（参考原版图鉴）
        hdr = pygame.Rect(panel.x + 12, panel.y + 12, panel.w - 24, 56)
        ui.draw_gradient(surf, hdr, (86, 158, 52), (44, 100, 34), radius=10)
        pygame.draw.rect(surf, (30, 72, 26), hdr, 1, border_radius=10)
        name_font = self._font(24, True)
        ui.text(surf, name_font, ui.fit_text(name_font, entry.get("name_zh", "?"), hdr.w - 90),
                (hdr.centerx, hdr.centery), (255, 252, 236), anchor="center",
                shadow=(20, 44, 16))
        ui.text(surf, self._font(10, True), f"No.{entry.get('almanac_no', idx + 1):02d}",
                (hdr.right - 12, hdr.centery), (228, 244, 208), anchor="midright")
        # 顶部画框
        art_area = pygame.Rect(panel.x + 18, hdr.bottom + 10, panel.w - 36, 158)
        ui.draw_gradient(surf, art_area, ui.mix(c1, (255, 255, 255), 0.62),
                         ui.mix(c2, (255, 255, 255), 0.42), radius=10)
        pygame.draw.rect(surf, ui.mix(c2, (255, 255, 255), 0.2), art_area, 1,
                         border_radius=10)
        draw_entry_art(surf, pygame.Rect(art_area.centerx - 70, art_area.y + 6, 140, 140),
                       entry, self.kind, 1.0)
        kind_label = "植物" if self.kind == "plant" else "僵尸"
        tag = pygame.Rect(art_area.x + 10, art_area.y + 8, 52, 20)
        ui.alpha_rect(surf, tag, (40, 30, 20, 150), radius=10)
        ui.text(surf, self._font(10, True), kind_label, tag.center,
                (250, 238, 208), anchor="center")
        y = art_area.bottom + 8
        ui.text(surf, self._font(11, False), entry.get("name_en", "") or "",
                (panel.x + 27, y), ui.INK_FAINT, anchor="topleft")
        y += 24

        chips = []
        if self.kind == "plant":
            chips = [f"阳光 {entry.get('cost', 0)}", f"生命 {entry.get('hp', 0)}",
                     entry.get("family", "植物")]
        else:
            chips = [f"生命 {entry.get('hp', 0)}",
                     f"速度 {entry.get('speed', '?') or '?'}",
                     behavior_zh(entry.get("behavior", "僵尸"))]
        x = panel.x + 26
        for text in chips[:3]:
            r = ui.draw_chip(surf, self.app, text, (x, y), size=12,
                             bg=(238, 228, 208), fg=(96, 72, 48))
            x = r.right + 8
        y += 38

        pygame.draw.line(surf, (226, 216, 198), (panel.x + 26, y),
                         (panel.right - 26, y), 1)
        y += 14
        ui.text(surf, self._font(13, True), "特性",
                (panel.x + 26, y), ui.BROWN, anchor="topleft")
        y += 24
        raw_behavior = str(entry.get("behavior", "") or "")
        behavior = behavior_zh(raw_behavior)
        if entry.get("tags"):
            extra = [str(t) for t in entry["tags"][:3]
                     if str(t) and str(t).lower() != raw_behavior.lower()]
            if extra:
                behavior = behavior + " · " + " / ".join(extra)
        ui.text(surf, self._font(13, False), ui.fit_text(
            self._font(13, False), behavior, panel.w - 52),
            (panel.x + 26, y), ui.INK, anchor="topleft")
        y += 32
        ui.text(surf, self._font(13, True), "简介",
                (panel.x + 26, y), ui.BROWN, anchor="topleft")
        y += 24
        desc = entry.get("desc", "") or "暂无图鉴描述。"
        lines = ui.wrap_text(self._font(13, False), desc, panel.w - 52)
        max_lines = max(2, (panel.bottom - 126 - y) // 21)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = ui.fit_text(self._font(13, False), lines[-1] + "…",
                                    panel.w - 52)
        for line in lines:
            ui.text(surf, self._font(13, False), line, (panel.x + 26, y),
                    ui.INK_SOFT, anchor="topleft")
            y += 21

        # 战斗提示卡（填充简介下方的空白）
        tip = BEHAVIOR_TIP.get(raw_behavior.strip().lower(), "")
        if tip:
            box = pygame.Rect(panel.x + 26, panel.bottom - 108, panel.w - 52, 66)
            pygame.draw.rect(surf, (246, 240, 226), box, border_radius=9)
            pygame.draw.rect(surf, (222, 210, 188), box, 1, border_radius=9)
            pygame.draw.rect(surf, ui.GOLD, (box.x, box.y + 10, 3, box.h - 20),
                             border_radius=2)
            ui.text(surf, self._font(11, True), "战斗提示",
                    (box.x + 12, box.y + 9), ui.BROWN, anchor="topleft")
            tf = self._font(10, False)
            tlines = ui.wrap_text(tf, tip, box.w - 24)[:2]
            ty = box.y + 26
            for line in tlines:
                ui.text(surf, tf, line, (box.x + 12, ty), ui.INK_SOFT,
                        anchor="topleft")
                ty += 16
        # 底部提示
        ui.text(surf, self._font(10, False), "← → ↑ ↓ 切换条目 · TAB 切换图鉴",
                (panel.centerx, panel.bottom - 16), ui.INK_FAINT, anchor="midbottom")
