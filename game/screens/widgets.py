"""通用 UI 控件与绘制工具。

风格：暖色 PvZ2 调色板、圆角面板、柔和阴影、中文文本。
所有控件都接受 ``app``，通过 ``app.font(size, bold)`` 渲染中文。

控件接口统一为::

    widget.handle(event) -> bool   # 返回 True 表示事件已被消费
    widget.draw(surf)
    widget.update(dt)              # 可选
"""
from __future__ import annotations

import math
import re

import pygame

# --------------------------------------------------------------------------
# 调色板
# --------------------------------------------------------------------------
BROWN = (122, 74, 42)
BROWN_DARK = (88, 52, 28)
BROWN_DEEP = (64, 38, 22)
BROWN_LIGHT = (162, 112, 70)
CREAM = (246, 240, 226)
PAPER = (249, 246, 241)
CREAM_DARK = (232, 222, 204)
BORDER = (206, 190, 168)
GOLD = (247, 201, 72)
GOLD_DARK = (202, 150, 44)
GREEN = (106, 168, 79)
GREEN_DARK = (74, 124, 54)
GREEN_LIGHT = (146, 198, 112)
INK = (62, 46, 32)
INK_SOFT = (112, 94, 76)
INK_FAINT = (152, 134, 116)
WHITE = (255, 255, 255)
RED = (192, 74, 58)
RED_DARK = (142, 48, 38)
BLUE = (84, 132, 176)
SHADOW = (32, 24, 16)
HEADER_BLUE = (69, 76, 92)

_GRAD_CACHE: dict = {}
_SHADOW_CACHE: dict = {}
_IMAGE_CACHE: dict = {}
_SCALE_CACHE: dict = {}
_COVER_CACHE: dict = {}
_FADE_SURFS: dict = {}


# --------------------------------------------------------------------------
# 基础数学 / 颜色
# --------------------------------------------------------------------------
def clamp(value, low, high):
    return low if value < low else high if value > high else value


def mix(c1, c2, t):
    """在两个颜色之间插值（支持 RGB / RGBA）。"""
    t = clamp(t, 0.0, 1.0)
    n = min(len(c1), len(c2))
    return tuple(int(round(c1[i] + (c2[i] - c1[i]) * t)) for i in range(n))


def shade(color, factor: float):
    """factor < 1 变暗，> 1 变亮。"""
    if factor <= 1.0:
        return tuple(int(clamp(c * factor, 0, 255)) for c in color[:3])
    return mix(color, (255, 255, 255), min(1.0, factor - 1.0))


def anchor_rect(size, pos, anchor="topleft"):
    r = pygame.Rect(0, 0, int(size[0]), int(size[1]))
    try:
        setattr(r, anchor, (int(pos[0]), int(pos[1])))
    except Exception:
        r.topleft = (int(pos[0]), int(pos[1]))
    return r


# --------------------------------------------------------------------------
# 绘制工具
# --------------------------------------------------------------------------
def draw_gradient(surf, rect, top_color, bottom_color, radius: int = 0):
    """竖向渐变（带缓存）。颜色可为 RGB 或 RGBA。"""
    rect = pygame.Rect(rect)
    if rect.w <= 0 or rect.h <= 0:
        return
    key = (rect.w, rect.h, tuple(top_color), tuple(bottom_color), int(radius))
    layer = _GRAD_CACHE.get(key)
    if layer is None:
        layer = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        for y in range(rect.h):
            t = y / max(1, rect.h - 1)
            pygame.draw.line(layer, mix(top_color, bottom_color, t), (0, y), (rect.w, y))
        if radius > 0:
            mask = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(),
                             border_radius=radius)
            layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        if len(_GRAD_CACHE) > 360:
            _GRAD_CACHE.clear()
        _GRAD_CACHE[key] = layer
    surf.blit(layer, rect.topleft)


def draw_shadow(surf, rect, radius: int = 14, alpha: int = 70, offset=(0, 5), spread: int = 6):
    """柔和投影（带缓存）。"""
    rect = pygame.Rect(rect)
    if rect.w <= 0 or rect.h <= 0:
        return
    key = (rect.w, rect.h, int(radius), int(alpha), int(spread))
    shadow = _SHADOW_CACHE.get(key)
    if shadow is None:
        pad = spread + 2
        shadow = pygame.Surface((rect.w + pad * 2, rect.h + pad * 2), pygame.SRCALPHA)
        for grow, a in ((spread, max(8, alpha // 3)),
                        (max(2, spread // 2), max(10, alpha // 3)),
                        (0, max(12, alpha // 2))):
            r = pygame.Rect(pad - grow, pad - grow, rect.w + grow * 2, rect.h + grow * 2)
            pygame.draw.rect(shadow, (20, 14, 8, a), r,
                             border_radius=int(radius) + grow)
        if len(_SHADOW_CACHE) > 260:
            _SHADOW_CACHE.clear()
        _SHADOW_CACHE[key] = shadow
    surf.blit(shadow, (rect.x - spread - 2, rect.y - spread - 2 + int(offset[1])))


def draw_panel(surf, rect, fill=PAPER, border=BORDER, radius: int = 16,
               border_width: int = 2, shadow: bool = True, shadow_alpha: int = 72):
    """标准面板：阴影 + 填充 + 描边。"""
    rect = pygame.Rect(rect)
    if shadow:
        draw_shadow(surf, rect, radius=radius, alpha=shadow_alpha)
    pygame.draw.rect(surf, fill, rect, border_radius=radius)
    if border is not None and border_width > 0:
        pygame.draw.rect(surf, border, rect, border_width, border_radius=radius)


def alpha_rect(surf, rect, color, radius: int = 0):
    """半透明矩形（自动使用 SRCALPHA 小表面）。"""
    rect = pygame.Rect(rect)
    if rect.w <= 0 or rect.h <= 0:
        return
    layer = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(layer, color, layer.get_rect(), border_radius=radius)
    surf.blit(layer, rect.topleft)


def draw_scrim(surf, rect, top_alpha=170, bottom_alpha=0, color=(8, 10, 8)):
    """竖向渐隐遮罩，常用于压暗背景。"""
    draw_gradient(surf, rect, (*color, top_alpha), (*color, bottom_alpha))


def text(surf, font, s, pos, color=INK, anchor="topleft", shadow=None,
         shadow_offset=(1, 2), alpha: int = 255):
    """渲染一行文本并返回其 Rect。"""
    s = str(s)
    if not s:
        return pygame.Rect(int(pos[0]), int(pos[1]), 0, 0)
    img = font.render(s, True, color)
    if alpha < 255:
        img = img.copy()
        img.set_alpha(alpha)
    rect = img.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
    if shadow is not None:
        sh = font.render(s, True, shadow)
        if alpha < 255:
            sh = sh.copy()
            sh.set_alpha(alpha)
        surf.blit(sh, rect.move(shadow_offset))
    surf.blit(img, rect)
    return rect


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-'’.,:：/!?%×+]*|\s+|.", re.S)


def wrap_text(font, s, max_width):
    """中英混排换行（中文逐字，英文尽量按词）。"""
    max_width = max(12, int(max_width))
    lines = []
    for para in str(s).split("\n"):
        if not para:
            lines.append("")
            continue
        cur = ""
        for tok in _TOKEN_RE.findall(para):
            if tok.isspace():
                if cur:
                    cur += " "
                continue
            trial = cur + tok
            if not cur or font.size(trial)[0] <= max_width:
                cur = trial
            else:
                lines.append(cur.rstrip())
                cur = tok
                while font.size(cur)[0] > max_width and len(cur) > 1:
                    cut = len(cur) - 1
                    while cut > 1 and font.size(cur[:cut])[0] > max_width:
                        cut -= 1
                    lines.append(cur[:cut])
                    cur = cur[cut:]
        lines.append(cur.rstrip())
    return lines or [""]


def draw_wrapped(surf, font, s, rect, color=INK, line_height=None, max_lines=None,
                 align="left"):
    """在矩形内绘制自动换行文本，返回实际高度。"""
    rect = pygame.Rect(rect)
    lh = int(line_height or font.get_linesize())
    lines = wrap_text(font, s, rect.w)
    if max_lines is not None:
        lines = lines[:max_lines]
    y = rect.y
    for line in lines:
        if y + lh > rect.bottom + 2:
            break
        if align == "center":
            text(surf, font, line, (rect.centerx, y), color, anchor="midtop")
        else:
            text(surf, font, line, (rect.x, y), color, anchor="topleft")
        y += lh
    return y - rect.y


def fit_text(font, s, max_width):
    """单行截断，超出部分用省略号。"""
    s = str(s)
    if font.size(s)[0] <= max_width:
        return s
    out = s
    while out and font.size(out + "…")[0] > max_width:
        out = out[:-1]
    return (out + "…") if out else "…"


def draw_chip(surf, app, label, pos, size=12, bg=(238, 226, 200), fg=INK_SOFT,
              pad_x=8, pad_y=4, radius=8, anchor="topleft", border=None,
              bold=True):
    """小标签胶囊。"""
    font = app.font(size, bold)
    tw, th = font.size(str(label))
    rect = anchor_rect((tw + pad_x * 2, th + pad_y * 2), pos, anchor)
    pygame.draw.rect(surf, bg, rect, border_radius=radius)
    if border:
        pygame.draw.rect(surf, border, rect, 1, border_radius=radius)
    text(surf, font, label, rect.center, fg, anchor="center")
    return rect


# --------------------------------------------------------------------------
# 图片加载（无显示设备时也可工作）
# --------------------------------------------------------------------------
def get_image(app, key):
    """从 assets 加载原图；缺失返回 None。结果缓存。"""
    if key in _IMAGE_CACHE:
        return _IMAGE_CACHE[key]
    img = None
    try:
        path = app.assets.resolve(key)
        if path is not None and path.exists():
            img = pygame.image.load(str(path))
            if pygame.display.get_surface() is not None:
                try:
                    img = img.convert_alpha()
                except Exception:
                    pass
    except Exception:
        img = None
    _IMAGE_CACHE[key] = img
    return img


def scale_image(img, size, smooth=True):
    """缩放图片（带缓存）。"""
    if img is None:
        return None
    size = (max(1, int(size[0])), max(1, int(size[1])))
    key = (id(img), size, bool(smooth))
    cached = _SCALE_CACHE.get(key)
    if cached is not None:
        return cached
    if smooth:
        out = pygame.transform.smoothscale(img, size)
    else:
        out = pygame.transform.scale(img, size)
    if len(_SCALE_CACHE) > 300:
        _SCALE_CACHE.clear()
    _SCALE_CACHE[key] = out
    return out


def load_cover(app, key, size):
    """加载并按 center-crop（cover）方式铺满 size；缺失返回 None。"""
    size = (int(size[0]), int(size[1]))
    ck = (key, size)
    if ck in _COVER_CACHE:
        return _COVER_CACHE[ck]
    img = get_image(app, key)
    out = None
    if img is not None:
        iw, ih = img.get_size()
        scale = max(size[0] / iw, size[1] / ih)
        sw, sh = max(1, int(math.ceil(iw * scale))), max(1, int(math.ceil(ih * scale)))
        big = pygame.transform.smoothscale(img, (sw, sh))
        out = pygame.Surface(size)
        out.blit(big, ((size[0] - sw) // 2, (size[1] - sh) // 2))
    _COVER_CACHE[ck] = out
    return out


def draw_cover(surf, img, rect):
    """把图片以 cover 方式画进 rect。"""
    if img is None:
        return
    rect = pygame.Rect(rect)
    iw, ih = img.get_size()
    if iw <= 0 or ih <= 0:
        return
    scale = max(rect.w / iw, rect.h / ih)
    sw, sh = max(1, int(math.ceil(iw * scale))), max(1, int(math.ceil(ih * scale)))
    big = pygame.transform.smoothscale(img, (sw, sh))
    surf.blit(big, (rect.x + (rect.w - sw) // 2, rect.y + (rect.h - sh) // 2))


def draw_dim(surf, rect=None, alpha=120, color=(8, 10, 12)):
    """整屏（或局部）压暗。"""
    if rect is None:
        rect = surf.get_rect()
    key = ("dim", surf.get_width(), surf.get_height(), int(alpha), tuple(color))
    layer = _FADE_SURFS.get(key)
    if layer is None:
        layer = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        layer.fill((*color, int(alpha)))
        _FADE_SURFS[key] = layer
    surf.blit(layer, rect.topleft)


# --------------------------------------------------------------------------
# 小图标（程序化绘制）
# --------------------------------------------------------------------------
def draw_sun(surf, center, r=18, rays=True):
    cx, cy = int(center[0]), int(center[1])
    if rays:
        for i in range(12):
            ang = i * math.pi / 6
            x1 = cx + math.cos(ang) * (r + 3)
            y1 = cy + math.sin(ang) * (r + 3)
            x2 = cx + math.cos(ang) * (r + 8)
            y2 = cy + math.sin(ang) * (r + 8)
            pygame.draw.line(surf, (255, 220, 110), (x1, y1), (x2, y2), 3)
    pygame.draw.circle(surf, (226, 158, 34), (cx, cy), r)
    pygame.draw.circle(surf, (250, 198, 72), (cx, cy), max(1, r - 2))
    pygame.draw.circle(surf, (255, 228, 146), (cx - max(1, r // 3), cy - max(1, r // 3)),
                       max(2, r // 3))


def draw_coin(surf, center, r=12):
    cx, cy = int(center[0]), int(center[1])
    pygame.draw.circle(surf, (176, 124, 34), (cx, cy), r)
    pygame.draw.circle(surf, (244, 194, 78), (cx, cy), max(1, r - 2))
    pygame.draw.circle(surf, (255, 226, 144), (cx, cy), max(1, r - 2), 2)
    pygame.draw.line(surf, (205, 152, 46), (cx, cy - r + 4), (cx, cy + r - 4), 2)


def draw_lock(surf, center, size=40, color=(238, 228, 208), dark=(42, 32, 24)):
    cx, cy = int(center[0]), int(center[1])
    body = pygame.Rect(0, 0, int(size * 0.70), int(size * 0.46))
    body.center = (cx, cy + int(size * 0.17))
    # 锁梁：先描深色外轮廓，再叠亮色，最后用锁体压住下缘
    r = max(4, int(size * 0.21))
    shackle_y = body.top - int(size * 0.10)
    pygame.draw.circle(surf, dark, (cx, shackle_y), r, max(3, int(size * 0.15)))
    pygame.draw.line(surf, dark, (cx - r, shackle_y),
                     (cx - r, body.top + 2), max(3, int(size * 0.15)))
    pygame.draw.line(surf, dark, (cx + r, shackle_y),
                     (cx + r, body.top + 2), max(3, int(size * 0.15)))
    pygame.draw.circle(surf, color, (cx, shackle_y), r, max(1, int(size * 0.07)))
    pygame.draw.rect(surf, dark, body.inflate(4, 4), border_radius=max(3, int(size * 0.13)))
    pygame.draw.rect(surf, color, body, border_radius=max(2, int(size * 0.11)))
    pygame.draw.rect(surf, (205, 192, 166), body, 1,
                     border_radius=max(2, int(size * 0.11)))
    # 钥匙孔：圆孔 + 向下的槽
    hole_r = max(2, int(size * 0.055))
    hole_y = body.centery - max(1, int(size * 0.04))
    pygame.draw.circle(surf, dark, (cx, hole_y), hole_r)
    pygame.draw.polygon(surf, dark, [
        (cx - hole_r + 1, hole_y + 1), (cx + hole_r - 1, hole_y + 1),
        (cx + max(1, hole_r - 2), body.bottom - max(3, int(size * 0.11))),
        (cx - max(1, hole_r - 2), body.bottom - max(3, int(size * 0.11)))])


def draw_check(surf, center, size, color=GREEN_DARK, width=3):
    cx, cy = center
    s = size
    pts = [(cx - s * 0.42, cy + s * 0.02),
           (cx - s * 0.10, cy + s * 0.34),
           (cx + s * 0.46, cy - s * 0.34)]
    pygame.draw.lines(surf, color, False, pts, width)


def draw_cross(surf, center, size, color=(90, 70, 52), width=3):
    cx, cy = center
    s = size * 0.5
    pygame.draw.line(surf, color, (cx - s, cy - s), (cx + s, cy + s), width)
    pygame.draw.line(surf, color, (cx - s, cy + s), (cx + s, cy - s), width)


def draw_arrow(surf, center, direction="right", size=14, color=CREAM, width=4):
    cx, cy = center
    s = size
    if direction == "right":
        pts = [(cx - s, cy - s), (cx + s, cy), (cx - s, cy + s)]
    elif direction == "left":
        pts = [(cx + s, cy - s), (cx - s, cy), (cx + s, cy + s)]
    elif direction == "up":
        pts = [(cx - s, cy + s), (cx, cy - s), (cx + s, cy + s)]
    else:
        pts = [(cx - s, cy - s), (cx, cy + s), (cx + s, cy - s)]
    pygame.draw.lines(surf, color, False, pts, width)


def draw_leaf(surf, center, size=10, color=GREEN_DARK):
    cx, cy = center
    pygame.draw.ellipse(surf, color, (cx - size, cy - size // 2, size * 2, size))


# --------------------------------------------------------------------------
# Label
# --------------------------------------------------------------------------
class Label:
    def __init__(self, app, label, pos, size=18, bold=False, color=INK,
                 anchor="topleft", shadow=None):
        self.app = app
        self.label = str(label)
        self.pos = pos
        self.size = size
        self.bold = bold
        self.color = color
        self.anchor = anchor
        self.shadow = shadow
        self.visible = True

    def set_text(self, label):
        self.label = str(label)

    def draw(self, surf):
        if not self.visible or not self.label:
            return
        text(surf, self.app.font(self.size, self.bold), self.label, self.pos,
             self.color, anchor=self.anchor, shadow=self.shadow)


# --------------------------------------------------------------------------
# Button
# --------------------------------------------------------------------------
BUTTON_STYLES = {
    # name: (top, bottom, border, text)
    "primary": ((255, 250, 236), (246, 233, 205), (198, 152, 72), BROWN),
    "start": ((255, 251, 239), (246, 232, 202), (196, 148, 64), BROWN),
    "green": ((128, 188, 92), (84, 142, 58), (56, 100, 40), (250, 247, 236)),
    "gold": ((252, 214, 100), (236, 176, 52), (164, 116, 32), (96, 58, 26)),
    "cream": ((251, 245, 232), (238, 228, 208), (176, 158, 130), (112, 80, 54)),
    "brown": ((142, 96, 58), (106, 66, 38), (70, 40, 20), (250, 240, 222)),
    "ghost": ((72, 84, 70), (50, 60, 50), (116, 134, 106), (236, 242, 230)),
    "danger": ((208, 100, 80), (170, 64, 50), (126, 42, 32), (255, 244, 236)),
    "blue": ((112, 158, 196), (76, 120, 160), (50, 84, 118), (250, 248, 238)),
    "paused": ((92, 70, 52), (72, 52, 38), (52, 36, 24), (250, 240, 222)),
}


class Button:
    def __init__(self, app, rect, label, on_click=None, style="primary",
                 font_size=22, bold=True, radius=None, enabled=True,
                 icon=None, subtext=None, border_width=None):
        self.app = app
        self.rect = pygame.Rect(rect)
        self.label = str(label)
        self.on_click = on_click
        self.style = style
        self.font_size = font_size
        self.bold = bold
        self.radius = radius if radius is not None else (14 if self.rect.h >= 56 else 11)
        self.enabled = enabled
        self.icon = icon
        self.subtext = subtext
        self.border_width = border_width
        self.hover = False
        self.pressed = False
        self.visible = True

    # ---------- 状态 ----------
    def set_text(self, label):
        self.label = str(label)

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        if not self.enabled:
            self.pressed = False

    def contains(self, pos):
        return self.rect.collidepoint(pos)

    def activate(self):
        if self.enabled and self.on_click is not None:
            self.on_click()

    # ---------- 事件 ----------
    def handle(self, event) -> bool:
        if not self.enabled or not self.visible:
            return False
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
                self.hover = True
                return True
            return False
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was = self.pressed
            self.pressed = False
            self.hover = self.rect.collidepoint(event.pos)
            if was and self.hover:
                self.activate()
                return True
            return was
        return False

    def update(self, dt):
        pass

    # ---------- 绘制 ----------
    def draw(self, surf):
        if not self.visible:
            return
        top, bottom, border, fg = BUTTON_STYLES.get(self.style, BUTTON_STYLES["primary"])
        border_w = self.border_width if self.border_width is not None else (
            3 if self.style in ("start", "green", "gold") else 2)
        if not self.enabled:
            top, bottom = (214, 208, 196), (198, 192, 180)
            border, fg = (170, 162, 148), (152, 144, 132)

        shift = 2 if self.pressed else 0
        rect = self.rect.move(0, shift)
        if not self.pressed:
            draw_shadow(surf, rect, radius=self.radius, alpha=64, offset=(0, 4), spread=5)
        if self.hover and self.enabled:
            top = mix(top, (255, 255, 255), 0.12)
            bottom = mix(bottom, (255, 255, 255), 0.08)
        if self.pressed:
            top, bottom = shade(top, 0.94), shade(bottom, 0.92)

        draw_gradient(surf, rect, top, bottom, radius=self.radius)
        pygame.draw.rect(surf, border, rect, border_w, border_radius=self.radius)
        # 内侧高光
        if self.rect.h >= 36 and self.enabled:
            hl = pygame.Rect(rect.x + 3, rect.y + 3, rect.w - 6, max(2, rect.h // 5))
            alpha_rect(surf, hl, (255, 255, 255, 46), radius=max(2, self.radius - 3))

        font = self.app.font(self.font_size, self.bold)
        label = self.label
        if self.subtext:
            main_font = self.app.font(self.font_size, self.bold)
            sub_font = self.app.font(max(10, self.font_size - 8), False)
            group_h = main_font.get_height() + sub_font.get_height() - 2
            y = rect.centery - group_h // 2
            text(surf, main_font, label, (rect.centerx, y), fg, anchor="midtop")
            text(surf, sub_font, self.subtext,
                 (rect.centerx, y + main_font.get_height() - 2),
                 mix(fg, (255, 255, 255), 0.25), anchor="midtop")
            return
        if self.icon is not None and not self.subtext:
            gap = 8
            tw = font.size(label)[0]
            total = self.icon.get_width() + gap + tw
            x = rect.centerx - total // 2
            surf.blit(self.icon, (x, rect.centery - self.icon.get_height() // 2))
            text(surf, font, label, (x + self.icon.get_width() + gap, rect.centery),
                 fg, anchor="midleft")
        else:
            text(surf, font, label, rect.center, fg, anchor="center")


class IconButton:
    """图标按钮（悬停时出现柔和底色）。"""

    def __init__(self, app, rect, image, on_click=None, radius=9,
                 hover_bg=(255, 255, 255, 40), padding=5, enabled=True):
        self.app = app
        self.rect = pygame.Rect(rect)
        self.image = image
        self.on_click = on_click
        self.radius = radius
        self.hover_bg = hover_bg
        self.padding = padding
        self.enabled = enabled
        self.hover = False
        self.pressed = False

    def handle(self, event) -> bool:
        if not self.enabled:
            return False
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.pressed = True
                self.hover = True
                return True
            return False
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was = self.pressed
            self.pressed = False
            inside = self.rect.collidepoint(event.pos)
            self.hover = inside
            if was and inside and self.on_click:
                self.on_click()
                return True
            return was
        return False

    def draw(self, surf):
        if self.hover:
            alpha_rect(surf, self.rect, self.hover_bg, radius=self.radius)
        if self.image is not None:
            pad = self.padding + (1 if self.pressed else 0)
            w = max(1, self.rect.w - pad * 2)
            h = max(1, self.rect.h - pad * 2)
            img = scale_image(self.image, (w, h))
            surf.blit(img, (self.rect.x + pad, self.rect.y + pad))


# --------------------------------------------------------------------------
# Checkbox
# --------------------------------------------------------------------------
class Checkbox:
    def __init__(self, app, pos, label, checked=False, on_change=None,
                 box=22, font_size=17, color=INK, gap=10):
        self.app = app
        self.pos = (int(pos[0]), int(pos[1]))
        self.label = str(label)
        self.checked = bool(checked)
        self.on_change = on_change
        self.box = box
        self.font_size = font_size
        self.color = color
        self.gap = gap
        self.hover = False
        self.pressed = False

    @property
    def rect(self):
        font = self.app.font(self.font_size, False)
        tw, th = font.size(self.label)
        h = max(self.box, th) + 6
        return pygame.Rect(self.pos[0], self.pos[1], self.box + self.gap + tw + 4, h)

    def handle(self, event) -> bool:
        r = self.rect
        if event.type == pygame.MOUSEMOTION:
            self.hover = r.collidepoint(event.pos)
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if r.collidepoint(event.pos):
                self.pressed = True
                return True
            return False
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was = self.pressed
            self.pressed = False
            inside = r.collidepoint(event.pos)
            if was and inside:
                self.toggle()
                return True
            return was
        return False

    def toggle(self):
        self.checked = not self.checked
        if self.on_change:
            self.on_change(self.checked)

    def draw(self, surf):
        font = self.app.font(self.font_size, False)
        r = self.rect
        box_rect = pygame.Rect(r.x, r.centery - self.box // 2, self.box, self.box)
        if self.checked:
            top, bottom = (255, 252, 242), (244, 235, 214)
            border = BROWN if not self.hover else GOLD_DARK
        else:
            top, bottom = (255, 253, 248), (240, 232, 216)
            border = (170, 154, 132) if not self.hover else GOLD_DARK
        if self.pressed:
            top, bottom = shade(top, 0.95), shade(bottom, 0.94)
        draw_gradient(surf, box_rect, top, bottom, radius=5)
        pygame.draw.rect(surf, border, box_rect, 2, border_radius=5)
        if self.checked:
            draw_check(surf, box_rect.center, self.box * 0.8, GREEN_DARK, 3)
        text(surf, font, self.label, (box_rect.right + self.gap, r.centery), self.color,
             anchor="midleft")


# --------------------------------------------------------------------------
# ToggleGroup（分段选择 / 标签页）
# --------------------------------------------------------------------------
class ToggleGroup:
    def __init__(self, app, rect, options, selected=0, on_change=None,
                 font_size=16, style="segmented", radius=10):
        self.app = app
        self.rect = pygame.Rect(rect)
        self.options = [str(o) for o in options]
        self.selected = int(selected)
        self.on_change = on_change
        self.font_size = font_size
        self.style = style
        self.radius = radius
        self.hover = -1
        self.pressed = -1

    def option_rect(self, index):
        n = max(1, len(self.options))
        w = self.rect.w // n
        return pygame.Rect(self.rect.x + index * w, self.rect.y,
                           w if index < n - 1 else self.rect.right - (self.rect.x + index * w),
                           self.rect.h)

    def set_selected(self, index, notify=False):
        index = clamp(int(index), 0, len(self.options) - 1)
        changed = index != self.selected
        self.selected = index
        if notify and changed and self.on_change:
            self.on_change(index)

    def handle(self, event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.hover = -1
            for i in range(len(self.options)):
                if self.option_rect(i).collidepoint(event.pos):
                    self.hover = i
                    break
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(len(self.options)):
                if self.option_rect(i).collidepoint(event.pos):
                    self.pressed = i
                    return True
            return False
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was = self.pressed
            self.pressed = -1
            for i in range(len(self.options)):
                if self.option_rect(i).collidepoint(event.pos):
                    if was == i:
                        self.set_selected(i, notify=True)
                    return True
            return was >= 0
        return False

    def draw(self, surf):
        if self.style == "tabs":
            for i, label in enumerate(self.options):
                r = self.option_rect(i)
                sel = i == self.selected
                if sel:
                    draw_gradient(surf, r, (255, 252, 244), (243, 234, 216),
                                  radius=self.radius)
                    pygame.draw.rect(surf, (188, 168, 140), r, 2, border_radius=self.radius)
                    hl = pygame.Rect(r.x + 6, r.bottom - 5, r.w - 12, 3)
                    pygame.draw.rect(surf, GOLD_DARK, hl, border_radius=2)
                elif i == self.hover:
                    alpha_rect(surf, r, (255, 255, 255, 40), radius=self.radius)
                color = BROWN if sel else INK_SOFT
                text(surf, self.app.font(self.font_size, sel), label, r.center, color,
                     anchor="center")
            return

        pygame.draw.rect(surf, (236, 226, 208), self.rect, border_radius=self.radius)
        pygame.draw.rect(surf, (192, 176, 152), self.rect, 2, border_radius=self.radius)
        for i, label in enumerate(self.options):
            r = self.option_rect(i).inflate(-6, -6)
            if i == self.selected:
                draw_gradient(surf, r, (255, 235, 168), (243, 194, 78),
                              radius=max(4, self.radius - 4))
                pygame.draw.rect(surf, (176, 128, 40), r, 1,
                                 border_radius=max(4, self.radius - 4))
                color = (82, 50, 24)
            else:
                if i == self.hover:
                    alpha_rect(surf, r, (255, 255, 255, 60), radius=max(4, self.radius - 4))
                color = INK_SOFT
            text(surf, self.app.font(self.font_size, i == self.selected), label,
                 r.center, color, anchor="center")


# --------------------------------------------------------------------------
# ScrollPanel（滚轮 / 拖动滚动条）
# --------------------------------------------------------------------------
class ScrollPanel:
    def __init__(self, app, rect, step=54):
        self.app = app
        self.rect = pygame.Rect(rect)
        self.step = step
        self.offset = 0.0
        self.content_h = 0
        self.dragging = False
        self._drag_mouse_y = 0
        self._drag_offset = 0.0

    # ---------- 数据 ----------
    def set_content_height(self, height):
        self.content_h = max(0, int(height))
        self.offset = clamp(self.offset, 0, self.max_offset())

    def max_offset(self):
        return max(0, self.content_h - self.rect.h)

    def reset(self):
        self.offset = 0.0

    def scroll_to(self, offset):
        self.offset = clamp(float(offset), 0.0, float(self.max_offset()))

    def scroll_by(self, dy):
        self.scroll_to(self.offset + dy)

    # ---------- 滚动条几何 ----------
    def _track_rect(self):
        return pygame.Rect(self.rect.right - 8, self.rect.y + 2, 6, self.rect.h - 4)

    def _thumb_rect(self):
        mo = self.max_offset()
        if mo <= 0:
            return None
        track = self._track_rect()
        ratio = self.rect.h / max(1, self.content_h)
        th = max(30, int(track.h * ratio))
        y = track.y + int((track.h - th) * (self.offset / mo))
        return pygame.Rect(track.x, y, track.w, th)

    # ---------- 事件 ----------
    def handle(self, event) -> bool:
        if event.type == pygame.MOUSEWHEEL:
            if self.rect.collidepoint(pygame.mouse.get_pos()):
                self.scroll_by(-event.y * self.step)
                return True
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            thumb = self._thumb_rect()
            if thumb is not None and thumb.collidepoint(event.pos):
                self.dragging = True
                self._drag_mouse_y = event.pos[1]
                self._drag_offset = self.offset
                return True
            if self.rect.collidepoint(event.pos):
                # 点击轨道空白：直接跳到该位置
                track = self._track_rect()
                if track.collidepoint(event.pos) and self.max_offset() > 0:
                    frac = clamp((event.pos[1] - track.y) / max(1, track.h), 0, 1)
                    self.scroll_to(frac * self.max_offset())
                    return True
            return False
        if event.type == pygame.MOUSEMOTION and self.dragging:
            thumb = self._thumb_rect()
            if thumb is None:
                return False
            track = self._track_rect()
            travel = max(1, track.h - thumb.h)
            delta = event.pos[1] - self._drag_mouse_y
            self.scroll_to(self._drag_offset + (delta / travel) * self.max_offset())
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.dragging:
            self.dragging = False
            return True
        return False

    # ---------- 绘制 ----------
    def begin_clip(self, surf):
        old = surf.get_clip()
        surf.set_clip(self.rect)
        return old

    @staticmethod
    def end_clip(surf, old):
        surf.set_clip(old)

    def draw_scrollbar(self, surf, always=False):
        mo = self.max_offset()
        if mo <= 0 and not always:
            return
        track = self._track_rect()
        alpha_rect(surf, track, (82, 64, 48, 28), radius=3)
        thumb = self._thumb_rect()
        if thumb is not None:
            color = (104, 82, 60, 150) if self.dragging else (104, 82, 60, 105)
            alpha_rect(surf, thumb, color, radius=3)


# --------------------------------------------------------------------------
# Toast
# --------------------------------------------------------------------------
class Toast:
    def __init__(self, app):
        self.app = app
        self.text = ""
        self.timer = 0.0
        self.duration = 2.2

    @property
    def active(self):
        return self.timer > 0.0

    def show(self, text, duration=2.2):
        self.text = str(text)
        self.timer = float(duration)
        self.duration = float(duration)

    def update(self, dt):
        if self.timer > 0:
            self.timer = max(0.0, self.timer - dt)

    def draw(self, surf, pos=None):
        if not self.active or not self.text:
            return
        font = self.app.font(16, True)
        tw, th = font.size(self.text)
        w, h = tw + 48, th + 22
        if pos is None:
            pos = (surf.get_width() // 2, surf.get_height() - 46)
        rect = anchor_rect((w, h), pos, "center")
        fade = min(1.0, (self.duration - self.timer) / 0.16 + 0.15, self.timer / 0.28)
        fade = clamp(fade, 0.0, 1.0)
        layer = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(layer, (30, 24, 18, 235), layer.get_rect(), border_radius=h // 2)
        pygame.draw.rect(layer, (247, 201, 72, 170), layer.get_rect(), 2,
                         border_radius=h // 2)
        img = font.render(self.text, True, (250, 244, 230))
        layer.blit(img, ((w - img.get_width()) // 2, (h - img.get_height()) // 2))
        layer.set_alpha(int(255 * fade))
        surf.blit(layer, rect.topleft)


# --------------------------------------------------------------------------
# MessagePopup（模态信息框）
# --------------------------------------------------------------------------
class MessagePopup:
    def __init__(self, app, title, message, button_text="确定", on_close=None,
                 width=440, height=232):
        self.app = app
        self.title = str(title)
        self.message = str(message)
        self.on_close = on_close
        self.visible = True
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = (app.screen.get_width() // 2, app.screen.get_height() // 2)
        btn_w, btn_h = 150, 44
        self.button = Button(
            app,
            (self.rect.centerx - btn_w // 2, self.rect.bottom - 62, btn_w, btn_h),
            button_text, style="primary", font_size=18, on_click=self.close)
        self._lines = None
        self._wrap_w = None

    def close(self):
        if not self.visible:
            return
        self.visible = False
        if self.on_close:
            self.on_close()

    def handle(self, event) -> bool:
        if not self.visible:
            return False
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.close()
            return True
        self.button.handle(event)
        return True

    def update(self, dt):
        pass

    def draw(self, surf):
        if not self.visible:
            return
        draw_dim(surf, alpha=120)
        draw_shadow(surf, self.rect, radius=16, alpha=110, offset=(0, 8), spread=8)
        pygame.draw.rect(surf, PAPER, self.rect, border_radius=16)
        header = pygame.Rect(self.rect.x, self.rect.y, self.rect.w, 48)
        pygame.draw.rect(surf, HEADER_BLUE, header,
                         border_top_left_radius=16, border_top_right_radius=16)
        text(surf, self.app.font(19, True), self.title,
             (header.x + 20, header.centery), (255, 248, 204), anchor="midleft")
        pygame.draw.rect(surf, BORDER, self.rect, 2, border_radius=16)

        font = self.app.font(15, False)
        wrap_w = self.rect.w - 56
        if self._lines is None or self._wrap_w != wrap_w:
            self._lines = wrap_text(font, self.message, wrap_w)
            self._wrap_w = wrap_w
        y = header.bottom + 24
        for line in self._lines[:4]:
            text(surf, font, line, (self.rect.centerx, y), INK_SOFT, anchor="midtop")
            y += 24
        self.button.draw(surf)
