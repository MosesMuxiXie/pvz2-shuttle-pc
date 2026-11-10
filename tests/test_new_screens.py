"""headless 冒烟测试：新玩法界面能构造、绘制与响应输入。

运行：
    $env:SDL_VIDEODRIVER="dummy"; $env:SDL_AUDIODRIVER="dummy"
    python tests/test_new_screens.py

覆盖 seedchooser / modes / minigames / minigame_level / survival /
survival_level / bosses / boss_level / shop / garden，并在植物与世界数据
全部缺失的降级场景下再跑一遍，确保界面不会崩溃。
"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PVZ2_SAVE_DIR", tempfile.mkdtemp(prefix="pvz2_test_"))

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402


class _DummyUpdateChecker:
    done = True
    result = {}
    latest_ver = None
    error = None

    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        return self

    def stop(self):
        pass


def _motion(pos):
    return pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0),
                              buttons=(0, 0, 0))


def _down(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button)


def _up(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button)


def _key(key, mod=0):
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod, unicode="",
                              scancode=0)


def _click(screen, pos):
    for event in (_motion(pos), _down(pos), _up(pos)):
        screen.handle(event)


def _frames(screen, app, count=2):
    for _ in range(count):
        screen.update(1.0 / 60.0)
        screen.draw(app.screen)
        pygame.event.pump()


def _check_contract(screen, name=None):
    assert isinstance(screen.name, str) and screen.name, "界面缺少 name"
    if name:
        assert screen.name == name, f"name {screen.name!r} != {name!r}"
    for method in ("enter", "exit", "handle", "update", "draw"):
        assert callable(getattr(screen, method, None)), \
            f"{screen.name}: 缺少 {method}()"
    assert isinstance(screen.app.screen, pygame.Surface)


def _new_screen(app, cls, payload):
    app.ui_payload = payload
    screen = cls(app)
    _check_contract(screen)
    screen.enter()
    return screen


def _load(app):
    """返回 (类, 负载) 列表；数据缺失时也返回可用负载。"""
    from game.screens.seedchooser import SeedChooserScreen
    from game.screens.modes import ModeHubScreen
    from game.screens.minigame import (VasebreakerHubScreen,
                                       VasebreakerScreen,
                                       load_minigames)
    from game.screens.survival import SurvivalHubScreen, SurvivalScreen
    from game.screens.boss import BossHubScreen, BossScreen, load_bosses
    from game.screens.shop import ShopScreen
    from game.screens.garden import GardenScreen

    worlds = []
    try:
        worlds = list(getattr(app.data, "worlds", []) or [])
    except Exception:
        worlds = []
    wid = str(getattr(worlds[0], "id", "frontyard")) if worlds else "frontyard"

    levels = []
    try:
        levels = list(app.data.levels(wid) or [])
    except Exception:
        levels = []
    slots = 6
    if levels:
        try:
            slots = int(getattr(levels[0], "seed_bank", 6) or 6)
        except (TypeError, ValueError):
            slots = 6

    minigames = []
    try:
        minigames = load_minigames(app)
    except Exception:
        minigames = []
    mg_entry = minigames[0] if minigames else None
    if isinstance(mg_entry, dict) and "minigame" in mg_entry and \
            isinstance(mg_entry["minigame"], dict):
        mg_entry = mg_entry["minigame"]
    mg_payload = {"minigame": mg_entry} if mg_entry else \
        {"minigame": {"id": "test_vase", "world": wid, "title": "测试砸罐子",
                      "sun": 150,
                      "vases": [[2, 4, "zombie", "basic"]]}}

    bosses = []
    try:
        bosses = load_bosses(app)
    except Exception:
        bosses = []
    boss_payload = {"world": wid, "boss": bosses[0] if bosses else {
        "id": "test_boss", "world": wid, "title": "测试博士", "hp": 9000,
        "reward": 250, "minions": [], "art": ""}}

    return [
        (SeedChooserScreen, {"world": wid, "index": 0, "slots": slots},
         "worldmap"),
        (ModeHubScreen, {}, "menu"),
        (VasebreakerHubScreen, {}, "modes"),
        (VasebreakerScreen, mg_payload, "minigames"),
        (SurvivalHubScreen, {}, "modes"),
        (SurvivalScreen, {"world": wid}, "survival"),
        (BossHubScreen, {}, "modes"),
        (BossScreen, boss_payload, "bosses"),
        (ShopScreen, {}, "modes"),
        (GardenScreen, {}, "modes"),
    ]


def _exercise(app, screen, target):
    """绘制两帧，做一次轻量点击，再按 ESC，确认请求返回上级。"""
    switched = []
    original_switch = app.switch

    def _recorder(target_name):
        switched.append(target_name if isinstance(target_name, str)
                        else getattr(target_name, "name", "?"))

    app.switch = _recorder
    try:
        _frames(screen, app, 2)
        # 点击屏幕中心偏下，命中各界面卡片/花盆的概率最高
        _click(screen, (640, 300))
        _click(screen, (640, 520))
        _frames(screen, app, 1)
        screen.handle(_key(pygame.K_ESCAPE))
        _frames(screen, app, 1)
        assert switched, f"{screen.name}: ESC 未请求返回上级"
        assert switched[-1] == target, \
            f"{screen.name}: 期望返回 {target!r}，实际 {switched[-1]!r}"
    finally:
        app.switch = original_switch


def _degrade(app):
    """把植物/世界/内容数据清空，模拟其他代理尚未写入 content 的情况。"""
    data = app.data
    saved = {
        "plants": getattr(data, "plants", {}),
        "worlds": getattr(data, "worlds", []),
        "world": getattr(data, "world", None),
        "levels": getattr(data, "levels", None),
        "content_json": getattr(app, "content_json", None),
        "db_thumb": getattr(app.assets, "db_thumb", None),
    }
    data.plants = {}
    data.worlds = []
    data.world = lambda wid: None
    data.levels = lambda wid: []
    app.content_json = lambda name, default=None: default
    app.assets.db_thumb = lambda *a, **k: None
    return saved


def _restore(app, saved):
    data = app.data
    data.plants = saved["plants"]
    data.worlds = saved["worlds"]
    if saved["world"] is not None:
        data.world = saved["world"]
    if saved["levels"] is not None:
        data.levels = saved["levels"]
    if saved["content_json"] is not None:
        app.content_json = saved["content_json"]
    if saved["db_thumb"] is not None:
        app.assets.db_thumb = saved["db_thumb"]


def main():
    import game.app as app_module
    app_module.UpdateChecker = _DummyUpdateChecker
    pygame.init()
    app = app_module.App(headless=True)
    app.switch = lambda target: None  # 安装前先占位，避免构造期跳转
    failures = []
    try:
        print("[1/2] 正常数据")
        # 图标走占位路径，避免在冒烟测试里加载骨骼动画
        app.assets.db_thumb = lambda *a, **k: None
        for cls, payload, target in _load(app):
            try:
                screen = _new_screen(app, cls, payload)
                _exercise(app, screen, target)
                screen.exit()
                print(f"  PASS {screen.name}")
            except Exception:
                failures.append(cls.__name__)
                print(f"  FAIL {cls.__name__}")
                traceback.print_exc()

        print("[2/2] 数据缺失（降级）")
        saved = _degrade(app)
        try:
            for cls, payload, target in _load(app):
                try:
                    screen = _new_screen(app, cls, payload)
                    _exercise(app, screen, target)
                    screen.exit()
                    print(f"  PASS {screen.name} (degraded)")
                except Exception:
                    failures.append(cls.__name__ + ":degraded")
                    print(f"  FAIL {cls.__name__} (degraded)")
                    traceback.print_exc()
        finally:
            _restore(app, saved)
    finally:
        app.running = False
        pygame.quit()

    if failures:
        print(f"FAIL: {len(failures)} 个用例失败 -> {failures}")
        return 1
    print("PASS: 10 个新界面在正常与降级数据下均可构造、绘制、响应输入")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        print("FAIL: 测试初始化异常")
        raise SystemExit(1)
