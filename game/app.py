"""App：窗口、主循环、状态机与全局服务。"""
from __future__ import annotations

import importlib
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pygame

from . import config
from .assets import Assets
from .audio import Audio
from .data import GameData
from .save import SaveData
from .update import UpdateChecker


def crash_log_path() -> Path:
    """崩溃日志位置：打包后放在 exe 同目录，源码运行时放在工程根目录。"""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else config.ROOT
    return base / "crash.log"


def log_crash(title: str, text: str) -> None:
    try:
        with open(crash_log_path(), "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] {title}\n{text}\n")
    except Exception:
        pass

SCREEN_REGISTRY = {
    "launcher": ("game.screens.launcher", "LauncherScreen"),
    "menu": ("game.screens.menu", "MenuScreen"),
    "worldmap": ("game.screens.worldmap", "WorldMapScreen"),
    "almanac": ("game.screens.almanac", "AlmanacScreen"),
    "settings": ("game.screens.settings", "SettingsScreen"),
    "level": ("game.screens.level_screen", "LevelScreen"),
    # 扩展模式
    "modes": ("game.screens.modes", "ModeHubScreen"),
    "seedchooser": ("game.screens.seedchooser", "SeedChooserScreen"),
    "minigames": ("game.screens.minigame", "VasebreakerHubScreen"),
    "minigame_level": ("game.screens.minigame", "VasebreakerScreen"),
    "survival": ("game.screens.survival", "SurvivalHubScreen"),
    "survival_level": ("game.screens.survival", "SurvivalScreen"),
    "bosses": ("game.screens.boss", "BossHubScreen"),
    "boss_level": ("game.screens.boss", "BossScreen"),
    "shop": ("game.screens.shop", "ShopScreen"),
    "garden": ("game.screens.garden", "GardenScreen"),
    "fusion": ("game.screens.fusion", "FusionScreen"),
}


class App:
    def __init__(self, headless: bool = False):
        pygame.init()
        self.headless = headless
        flags = 0
        if not headless:
            try:
                self.screen = pygame.display.set_mode((config.WIN_W, config.WIN_H), flags)
            except Exception:
                self.screen = pygame.display.set_mode((config.WIN_W, config.WIN_H))
            pygame.display.set_caption(config.TITLE)
        else:
            # 无窗口模式仍初始化显示格式，保证 convert()/convert_alpha() 可用
            try:
                pygame.display.set_mode((config.WIN_W, config.WIN_H))
            except Exception:
                pass
            self.screen = pygame.Surface((config.WIN_W, config.WIN_H))
        self.clock = pygame.time.Clock()
        self.running = True
        self.save = SaveData.load()
        self.audio = Audio()
        try:
            settings = getattr(self.save, "settings", {}) or {}
            self.audio.set_flags(bool(settings.get("music", True)),
                                 bool(settings.get("sfx", True)))
        except Exception:
            pass
        self.assets = Assets(self)
        self.data = GameData()
        self.screen_obj = None
        self.screen_name = None
        self.pending_level = None
        self.pending_deck = None
        self.pending_mode = "adventure"
        self.ui_payload = None
        self.garden_debug_speed = 1.0
        self.dt = 0.0
        self.error_text = None
        self._content_cache = {}
        self.updates = UpdateChecker()
        self.updates.start()
        try:
            self.switch(SplashScreen(self))
        except Exception:
            traceback.print_exc()
            log_crash("startup", traceback.format_exc())
            self.switch("launcher")

    # ---------- 状态切换 ----------
    def switch(self, target):
        if isinstance(target, str):
            name = target
            entry = SCREEN_REGISTRY.get(name)
            if entry is None:
                raise KeyError(f"unknown screen {name}")
            mod_name, cls_name = entry
            try:
                mod = importlib.import_module(mod_name)
                cls = getattr(mod, cls_name)
                obj = cls(self)
            except Exception:
                err = traceback.format_exc()
                traceback.print_exc()
                self.error_text = err
                log_crash(f"{mod_name}.{cls_name}", err)
                obj = ErrorScreen(self, f"{mod_name}.{cls_name} 加载失败")
        else:
            name = getattr(target, "name", type(target).__name__)
            obj = target
        if self.screen_obj is not None:
            try:
                self.screen_obj.exit()
            except Exception:
                traceback.print_exc()
        self.screen_obj = obj
        self.screen_name = name
        try:
            obj.enter()
        except Exception:
            traceback.print_exc()

    def start_level(self, world_id: str, index: int, deck=None):
        self.pending_level = (world_id, index)
        self.pending_deck = list(deck) if deck else None
        self.pending_mode = "adventure"
        self.switch("level")

    def finish_level(self, world_id: str, index: int, won: bool,
                     stars=None, coins: int = 0):
        if won:
            self.save.complete(world_id, index)
            worlds = self.data.worlds
            for i, w in enumerate(worlds):
                if w.id == world_id and i + 1 < len(worlds):
                    self.save.unlock(worlds[i + 1].id)
            reward = int(coins) if coins else 50 + 10 * int(index)
            self.save.add_coins(reward)
            if stars is not None:
                self.save.set_stars(world_id, index, list(stars))

    # ---------- 扩展模式 ----------
    def content_json(self, name: str, default=None):
        """读取 content/<name>.json（带缓存）。"""
        if name in self._content_cache:
            return self._content_cache[name]
        import json
        from . import config
        path = config.ROOT / "content" / f"{name}.json"
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = default if default is not None else {}
        self._content_cache[name] = data
        return data

    def open_seed_chooser(self, world_id: str, index: int, slots: int = 6):
        self.ui_payload = {"world": world_id, "index": index, "slots": slots}
        self.switch("seedchooser")

    def start_survival(self, world_id: str):
        self.ui_payload = {"world": world_id}
        self.pending_mode = "survival"
        self.switch("survival_level")

    def finish_survival(self, world_id: str, score: int):
        best = int(self.save.best_survival.get(world_id, 0) or 0)
        if score > best:
            self.save.best_survival[world_id] = int(score)
            self.save.save()
        self.save.add_coins(max(10, int(score) // 20))

    def start_boss(self, world_id: str):
        bosses = self.content_json("bosses", {"bosses": []}) or {}
        entry = None
        for b in bosses.get("bosses", []) or []:
            if b.get("world") == world_id:
                entry = b
                break
        self.ui_payload = {"world": world_id, "boss": entry}
        self.pending_mode = "boss"
        self.switch("boss_level")

    def finish_boss(self, world_id: str, won: bool):
        if won:
            self.save.add_coins(300)
            self.save.unlock_plant("darkmatter_dragonfruit")

    def start_minigame(self, mg_id: str):
        games = self.content_json("minigames", {"minigames": []}) or {}
        entry = None
        for g in games.get("minigames", []) or []:
            if g.get("id") == mg_id:
                entry = g
                break
        self.ui_payload = {"minigame": entry}
        self.switch("minigame_level")

    def quit(self):
        self.running = False

    # ---------- 便捷 ----------
    def font(self, size: int, bold: bool = False):
        return self.assets.font(size, bold)

    # ---------- 主循环 ----------
    def run(self):
        while self.running:
            try:
                dt = self.clock.tick(config.FPS) / 1000.0
                self.dt = min(dt, 0.05)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                        break
                    if self.screen_obj:
                        self.screen_obj.handle(event)
                if not self.running:
                    break
                if self.screen_obj:
                    self.screen_obj.update(self.dt)
                    self.audio.tick()
                    self.screen_obj.draw(self.screen)
                if not self.headless:
                    pygame.display.flip()
            except Exception:
                err = traceback.format_exc()
                traceback.print_exc()
                self.error_text = err
                log_crash("runtime loop", err)
                self.switch(ErrorScreen(self, "运行时错误（详见 crash.log）"))
        pygame.quit()
        sys.exit(0)


class SplashScreen:
    """启动闪屏：SHUTTLE 的 launcher.png，1.6 秒后进入启动器。"""

    name = "splash"

    def __init__(self, app: App):
        self.app = app
        self.t = 0.0
        self.done = False
        self.img = None
        try:
            self.img = app.assets.image("ui/launcher.png")
        except Exception:
            self.img = None

    def enter(self):
        pass

    def exit(self):
        pass

    def handle(self, event):
        if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            self._go()

    def update(self, dt):
        self.t += dt
        if self.t >= 1.6:
            self._go()

    def _go(self):
        if not self.done:
            self.done = True
            self.app.switch("launcher")

    def draw(self, surf):
        surf.fill((0, 0, 0))
        if self.img is not None:
            w, h = self.img.get_size()
            scale = min(surf.get_width() / w, surf.get_height() / h)
            nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
            img = pygame.transform.smoothscale(self.img, (nw, nh))
            surf.blit(img, ((surf.get_width() - nw) // 2, (surf.get_height() - nh) // 2))
        else:
            f = self.app.font(40, True)
            surf.blit(f.render("PvZ 2 SHUTTLE", True, (255, 220, 120)), (440, 320))


class ErrorScreen:
    name = "error"

    def __init__(self, app: App, message: str):
        self.app = app
        self.message = message

    def enter(self):
        pass

    def exit(self):
        pass

    def handle(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.app.quit()

    def update(self, dt):
        pass

    def draw(self, surf):
        surf.fill((30, 30, 40))
        f = self.app.font(24, True)
        surf.blit(f.render(self.message, True, (255, 120, 120)), (40, 40))
        f2 = self.app.font(16)
        y = 90
        err = self.app.error_text or ""
        for line in err.splitlines()[-18:]:
            surf.blit(f2.render(line[:140], True, (220, 220, 220)), (40, y))
            y += 22
        try:
            surf.blit(f2.render(f"崩溃日志：{crash_log_path()}", True,
                               (150, 200, 255)), (40, 696))
        except Exception:
            pass
