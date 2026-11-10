"""背景音乐 / 音效封装（无音频设备时静默降级）。

音乐素材放在 ``assets/audio/``，文件名形如 ``frontyard_intro.ogg`` +
``frontyard_loop.ogg``：先播 intro，结束后自动切到 loop 循环。
"""
from __future__ import annotations

from pathlib import Path

import pygame

AUDIO_DIR = Path(__file__).resolve().parent.parent / "assets" / "audio"

WORLD_TRACKS = {
    "frontyard": ("frontyard_intro.ogg", "frontyard_loop.ogg"),
    "egypt": ("egypt_intro.ogg", "egypt_loop.ogg"),
    "pirate": ("pirate_intro.ogg", "pirate_loop.ogg"),
    "cowboy": ("cowboy_intro.ogg", "cowboy_loop.ogg"),
    "future": ("future_intro.ogg", "future_loop.ogg"),
    "dark": ("dark_intro.ogg", "dark_loop.ogg"),
    "beach": ("beach_intro.ogg", "beach_loop.ogg"),
    "lostcity": ("lostcity_intro.ogg", "lostcity_loop.ogg"),
    "iceage": ("dark_intro.ogg", "dark_loop.ogg"),
    "kongfu": ("obb/MUSIC_KONGFU_162326684.ogg", "obb/MUSIC_KONGFU_308215554.ogg"),
    "dino": ("beach_intro.ogg", "beach_loop.ogg"),
    "eighties": ("frontyard_intro.ogg", "frontyard_loop.ogg"),
    "modern": ("frontyard_intro.ogg", "frontyard_loop.ogg"),
    "sky": ("obb/MUSIC_SKYCITY_853739919.ogg", "obb/MUSIC_SKYCITY_1011891144.ogg"),
    "chinesegarden": ("chinesegarden_intro.ogg", "chinesegarden_loop.ogg"),
    "losantosvice": ("losantosvice_intro.ogg", "losantosvice_loop.ogg"),
    "lunarrainbowmarket": ("lunarrainbowmarket_intro.ogg",
                           "lunarrainbowmarket_loop.ogg"),
    "plantagenet": ("obb/MUSIC_PLANTAGENET_100369757.ogg",
                    "obb/MUSIC_PLANTAGENET_371401189.ogg"),
    "renai": ("obb/MUSIC_RENAI_317135244.ogg", "obb/MUSIC_RENAI_515500817.ogg"),
    "steam": ("obb/MUSIC_STEAM_75905675.ogg", "obb/MUSIC_STEAM_906722450.ogg"),
    "fairy": ("obb/MUSIC_FAIRYTALEFORESTMINIGAME_86464595.ogg",
              "obb/MUSIC_FAIRYTALEFORESTMINIGAME_605847708.ogg"),
    "carnival": ("obb/MUSIC_SPECIAL_672220229.ogg", "obb/MUSIC_SPECIAL_302109709.ogg"),
    "heian": ("obb/MUSIC_SPECIAL_302109709.ogg", "obb/MUSIC_SPECIAL_672220229.ogg"),
    "mausoleum": ("dark_intro.ogg", "dark_loop.ogg"),
    "memorytour": ("frontyard_intro.ogg", "frontyard_loop.ogg"),
    "muji": ("obb/MUSIC_CHEESESTAR_420575793.ogg",
             "obb/MUSIC_CHEESESTAR_420575793.ogg"),
}

# 世界名别名（内容里可能用中文 id / 旧名）
WORLD_ALIASES = {
    "frontyard": "frontyard", "前院": "frontyard", "day": "frontyard",
    "egypt": "egypt", "埃及": "egypt",
    "pirate": "pirate", "海盗": "pirate",
    "cowboy": "cowboy", "西部": "cowboy",
    "future": "future", "未来": "future",
    "dark": "dark", "黑暗": "dark",
    "beach": "beach", "海滩": "beach",
    "lostcity": "lostcity", "失落": "lostcity",
    "chinesegarden": "chinesegarden", "中国园林": "chinesegarden",
    "losantosvice": "losantosvice", "洛城风云": "losantosvice",
    "lunarrainbowmarket": "lunarrainbowmarket", "月虹市场": "lunarrainbowmarket",
    "plantagenet": "plantagenet",
    "heian": "heian",
    "fairy": "fairy",
    "mausoleum": "mausoleum",
    "steam": "steam",
    "memorytour": "memorytour",
    "renai": "renai",
    "muji": "muji",
    "carnival": "carnival",
}


class Audio:
    def __init__(self):
        self.ok = False
        self._pending_loop: Path | None = None
        self._current: str | None = None
        self._volume = 0.5
        self.music_on = True
        self.sfx_on = True
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=1024)
            self.ok = pygame.mixer.get_init() is not None
        except Exception:
            self.ok = False

    def set_flags(self, music: bool = True, sfx: bool = True):
        """音乐 / 音效总开关（设置界面实时生效）。"""
        self.music_on = bool(music)
        self.sfx_on = bool(sfx)
        if not self.music_on:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            self._pending_loop = None

    # ------------------------------------------------------------ 基础
    @staticmethod
    def path(name: str) -> Path:
        return AUDIO_DIR / name

    def play(self, sound, volume: float = 0.7):
        if not self.ok or sound is None or not self.sfx_on:
            return
        try:
            sound.set_volume(volume)
            sound.play()
        except Exception:
            pass

    def sound(self, name: str, volume: float = 0.7):
        """按文件名播放一次性音效（缺失时忽略）。"""
        if not self.ok or not self.sfx_on:
            return
        p = self.path(name)
        if not p.exists():
            return
        try:
            self.play(pygame.mixer.Sound(str(p)), volume)
        except Exception:
            pass

    def music(self, path, volume: float = 0.5, loop: bool = True):
        if not self.ok:
            return
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play(-1 if loop else 0)
            self._pending_loop = None
        except Exception:
            pass

    def stop(self):
        self._pending_loop = None
        self._current = None
        if not self.ok:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    # ------------------------------------------------------------ 世界音乐
    def play_world(self, world_id: str, volume: float = 0.5):
        if not self.music_on:
            return
        key = WORLD_ALIASES.get(str(world_id or "").strip().lower(), "frontyard")
        if key == self._current:
            return
        self._current = key
        self._volume = volume
        intro_name, loop_name = WORLD_TRACKS.get(key, WORLD_TRACKS["frontyard"])
        intro = self.path(intro_name)
        loop = self.path(loop_name)
        if not self.ok:
            return
        try:
            pygame.mixer.music.stop()
            if intro.exists():
                pygame.mixer.music.load(str(intro))
                pygame.mixer.music.set_volume(volume)
                pygame.mixer.music.play(0)
                self._pending_loop = loop if loop.exists() else None
            elif loop.exists():
                pygame.mixer.music.load(str(loop))
                pygame.mixer.music.set_volume(volume)
                pygame.mixer.music.play(-1)
                self._pending_loop = None
            else:
                self._pending_loop = None
        except Exception:
            self._pending_loop = None

    def play_menu(self, volume: float = 0.42):
        if not self.music_on:
            return
        self._current = "__menu__"
        if not self.ok:
            return
        p = self.path("obb/STARTUPMUSIC_882874277.ogg")
        if not p.exists():
            p = self.path("menu.ogg")
        self._pending_loop = None
        if not p.exists():
            return
        try:
            pygame.mixer.music.load(str(p))
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play(-1)
        except Exception:
            pass

    def play_jingle(self, name: str, volume: float = 0.6):
        """胜利 / 失败短曲；播完不自动循环。"""
        if not self.music_on:
            return
        self._current = "__jingle__"
        if not self.ok:
            return
        p = self.path(name)
        self._pending_loop = None
        if not p.exists():
            return
        try:
            pygame.mixer.music.load(str(p))
            pygame.mixer.music.set_volume(volume)
            pygame.mixer.music.play(0)
        except Exception:
            pass

    # ------------------------------------------------------------ 每帧
    def tick(self):
        """intro 播完后接上 loop。"""
        if not self.ok or self._pending_loop is None:
            return
        try:
            if not pygame.mixer.music.get_busy():
                pygame.mixer.music.load(str(self._pending_loop))
                pygame.mixer.music.set_volume(self._volume)
                pygame.mixer.music.play(-1)
                self._pending_loop = None
        except Exception:
            self._pending_loop = None
