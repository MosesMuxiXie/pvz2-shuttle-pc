"""资源加载：图片、字体、音效、DragonBones 模型（带占位回退）。"""
from __future__ import annotations

import os
from pathlib import Path

import pygame

from .config import ASSETS_DIR


_PLACEHOLDER_COLORS = [(230, 90, 90), (90, 190, 120), (90, 140, 230), (230, 190, 70),
                       (190, 90, 210), (90, 200, 210), (220, 130, 60), (150, 150, 160)]


def _color_for(key: str):
    h = 0
    for ch in key:
        h = (h * 131 + ord(ch)) & 0xFFFFFFFF
    return _PLACEHOLDER_COLORS[h % len(_PLACEHOLDER_COLORS)]


class Assets:
    def __init__(self, app):
        self.app = app
        self._images: dict = {}
        self._fonts: dict = {}
        self._db: dict = {}
        self._players: dict = {}
        self._sounds: dict = {}
        self._missing_db: set = set()
        self._music_key = None

    # ---------- 路径解析 ----------
    @staticmethod
    def resolve(key: str) -> Path:
        p = Path(key)
        if p.is_absolute():
            return p
        base = ASSETS_DIR / key
        if base.exists():
            return base
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            q = Path(str(base) + ext)
            if q.exists():
                return q
        return base

    # ---------- 图片 ----------
    def image(self, key: str, scale: float | None = None, alpha: int | None = None):
        """按资源键加载图片；缺失时返回带标签的占位块（不崩溃）。"""
        if not key:
            return self.placeholder("?")
        ck = (key, scale, alpha)
        if ck in self._images:
            return self._images[ck]
        path = self.resolve(key)
        surf = None
        try:
            if path.exists():
                surf = pygame.image.load(str(path)).convert_alpha()
        except Exception:
            surf = None
        if surf is None:
            surf = self.placeholder(Path(key).stem)
        if scale and scale != 1.0:
            w = max(1, int(surf.get_width() * scale))
            h = max(1, int(surf.get_height() * scale))
            surf = pygame.transform.smoothscale(surf, (w, h))
        if alpha is not None:
            surf = surf.copy()
            surf.set_alpha(alpha)
        self._images[ck] = surf
        return surf

    def has_image(self, key: str) -> bool:
        """资源键是否对应一个真实存在的图片文件（不是占位块）。"""
        if not key:
            return False
        try:
            return self.resolve(key).is_file()
        except Exception:
            return False

    def static_sprite(self, key: str, target_h: int) -> "pygame.Surface | None":
        """加载静态 PNG 立绘，按目标高度等比缩放；缺失返回 None。

        用于 Renders 目录导入的植物/僵尸立绘（无骨骼动画），按高度归一化后
        与 DragonBones 角色在同一战场上保持相近比例。
        """
        if not self.has_image(key):
            return None
        ck = ("static", key, target_h)
        cached = self._images.get(ck)
        if cached is not None:
            return cached
        try:
            surf = pygame.image.load(str(self.resolve(key))).convert_alpha()
        except Exception:
            return None
        w, h = surf.get_size()
        if w <= 0 or h <= 0:
            return None
        s = float(target_h) / float(h)
        if abs(s - 1.0) > 0.001:
            surf = pygame.transform.smoothscale(
                surf, (max(1, int(round(w * s))), max(1, int(round(h * s)))))
        self._images[ck] = surf
        return surf

    def placeholder(self, label: str = "?", w: int = 96, h: int = 96):
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        c = _color_for(label)
        surf.fill((*c, 210))
        pygame.draw.rect(surf, (255, 255, 255, 230), surf.get_rect(), 2)
        try:
            f = self.font(14)
            t = f.render(str(label)[:10], True, (255, 255, 255))
            surf.blit(t, (max(2, (w - t.get_width()) // 2), max(2, (h - t.get_height()) // 2)))
        except Exception:
            pass
        return surf

    # ---------- 字体 ----------
    def font(self, size: int, bold: bool = False):
        key = (size, bold)
        if key in self._fonts:
            return self._fonts[key]
        candidates = [ASSETS_DIR / "ui" / "font_zh.ttf", ASSETS_DIR / "ui" / "font_zh.ttc",
                      Path("C:/Windows/Fonts/msyh.ttc"), Path("C:/Windows/Fonts/msyhbd.ttc"),
                      Path("C:/Windows/Fonts/simhei.ttf")]
        f = None
        for p in candidates:
            if p.exists():
                try:
                    f = pygame.font.Font(str(p), size)
                    if bold:
                        try:
                            f.set_bold(True)
                        except Exception:
                            pass
                    break
                except Exception:
                    continue
        if f is None:
            f = pygame.font.Font(None, size)
        self._fonts[key] = f
        return f

    # ---------- DragonBones ----------
    def db(self, key: str, armature: str | None = None):
        """加载 DragonBones 模型；armature 用于同一骨架下的不同变体（路障/铁桶等）。

        失败返回 None（调用方画占位）。
        """
        ck = (key, armature)
        if ck in self._db:
            return self._db[ck]
        model = None
        try:
            from .dragonbones import DBModel
            d = ASSETS_DIR / "db" / key
            if d.is_dir():
                model = DBModel.load(d, armature=armature)
        except Exception as e:  # noqa: BLE001
            if ck not in self._missing_db:
                self._missing_db.add(ck)
                print(f"[assets] db load failed {key}#{armature}: {e}")
        self._db[ck] = model
        return model

    def dbplayer(self, key: str, anim: str = "Idle", loop: bool = True,
                 speed: float = 1.0, armature: str | None = None):
        model = self.db(key, armature=armature)
        if model is None:
            return None
        try:
            from .dragonbones import DBPlayer
            return DBPlayer(model, anim=anim, loop=loop, speed=speed)
        except Exception:
            return None

    def db_thumb(self, key: str, w: int = 52, h: int = 52, anim: str | None = None,
                 armature: str | None = None, frame_time: float = 0.25):
        """把 DragonBones 模型渲染成缩略图（卡片/图鉴图标）；失败返回 None。"""
        ck = ("thumb", key, w, h, anim, armature)
        if ck in self._images:
            return self._images[ck]
        model = self.db(key, armature=armature)
        if model is None:
            self._images[ck] = None
            return None
        try:
            from .dragonbones import DBPlayer
            name = anim or (model.animations[0] if model.animations else "Idle")
            player = DBPlayer(model, anim=name, loop=True)
            t = 0.0
            while t < frame_time:
                player.update(1 / 30)
                t += 1 / 30
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            size = getattr(model, "size", None) or (w, h)
            src_h = max(8.0, float(size[1]))
            scale = min(1.0, (h * 0.86) / src_h)
            player.draw(surf, w // 2, int(h * 0.92), scale=scale)
            self._images[ck] = surf
            return surf
        except Exception:
            self._images[ck] = None
            return None

    # ---------- 声音 ----------
    def sound(self, key: str):
        if key in self._sounds:
            return self._sounds[key]
        snd = None
        try:
            p = self.resolve("audio/" + key)
            if p.exists() and pygame.mixer.get_init():
                snd = pygame.mixer.Sound(str(p))
        except Exception:
            snd = None
        self._sounds[key] = snd
        return snd

    def music(self, key: str):
        if key == self._music_key:
            return
        try:
            if not pygame.mixer.get_init():
                return
            p = self.resolve("audio/" + key)
            if p.exists():
                pygame.mixer.music.load(str(p))
                pygame.mixer.music.set_volume(0.5)
                pygame.mixer.music.play(-1)
                self._music_key = key
        except Exception:
            pass
