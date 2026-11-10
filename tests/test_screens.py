"""无窗口冒烟测试：依次构造并绘制所有界面。

运行:
    python tests/test_screens.py

使用 SDL dummy 驱动，不打开窗口、不访问网络、不写入存档。
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402


class _DummyUpdateChecker:
    """离线测试用：不启动网络线程。"""

    def __init__(self):
        self.done = True
        self.result = {}
        self.latest_ver = None

    def start(self):
        return self


def _motion(pos):
    return pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0),
                              buttons=(0, 0, 0))


def _down(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button)


def _up(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button)


def _key(key):
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="",
                              scancode=0)


def _click(screen, pos):
    screen.handle(_motion(pos))
    screen.handle(_down(pos))
    screen.handle(_up(pos))


def _draw(screen, app, frames=2):
    for _ in range(frames):
        screen.update(1.0 / 60.0)
        screen.draw(app.screen)
        pygame.event.pump()


def _check_contract(screen, expected_name):
    assert getattr(screen, "name", None) == expected_name, \
        f"name={getattr(screen, 'name', None)!r}, expected {expected_name!r}"
    for method in ("enter", "exit", "handle", "update", "draw"):
        assert callable(getattr(screen, method, None)), \
            f"{expected_name} missing {method}()"
    assert isinstance(app_screen(screen), pygame.Surface)


def app_screen(screen):
    return screen.app.screen


def main():
    import game.app as app_module

    # 避免测试时发起版本检查网络请求
    app_module.UpdateChecker = _DummyUpdateChecker

    app = None
    try:
        pygame.init()
        app = app_module.App(headless=True)
        assert getattr(app, "screen", None) is not None

        order = ["launcher", "menu", "worldmap", "almanac", "settings"]
        for name in order:
            app.switch(name)
            screen = app.screen_obj
            _check_contract(screen, name)
            screen.handle(_motion((640, 360)))
            if name == "worldmap":
                # 点开第一世界的关卡面板，再关闭，覆盖面板绘制路径
                _click(screen, (260, 430))
                _draw(screen, app, 1)
                screen.handle(_key(pygame.K_ESCAPE))
            elif name == "almanac":
                screen.handle(_motion((240, 320)))
                _click(screen, (140, 210))
                screen.handle(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1,
                                                flipped=False, which=0,
                                                precise_x=0.0,
                                                precise_y=0.0))
            _draw(screen, app, 2)
            print(f"  OK  {name}")

        # ---------------------------------------------------------- 关卡
        app.start_level("frontyard", 0)
        level = app.screen_obj
        _check_contract(level, "level")
        assert level.session is not None, \
            f"LevelSession 未创建: {level.error}"
        print(f"  OK  level session ({len(level.session.cards)} cards, "
              f"{level.session.total_waves} waves)")

        # 选卡 + 种到第 2 行第 2 列
        if level.session.card_rects:
            _click(level, level.session.card_rects[0].center)
        cell = (190 + 100 + 50, 120 + 116 + 58)
        _click(level, cell)
        for _ in range(6):
            level.update(0.05)
            level.draw(app.screen)

        # 暂停遮罩
        level.handle(_key(pygame.K_ESCAPE))
        assert level.session.paused
        level.draw(app.screen)
        level.handle(_key(pygame.K_ESCAPE))
        assert not level.session.paused
        level.draw(app.screen)
        print("  OK  level pause overlay")

        # 结算遮罩 + 重玩按钮
        level.session.status = "won"
        level.session.banner_text = "关卡胜利！"
        level.draw(app.screen)
        _click(level, level.btn_result_replay.rect.center)
        assert level.session is not None and level.session.status == "playing"
        level.draw(app.screen)
        print("  OK  level result overlay + replay")

        # 引擎缺失兜底界面
        level.session = None
        level.error = "headless smoke test: engine unavailable"
        level.draw(app.screen)
        print("  OK  level placeholder fallback")

        app.running = False
        print("PASS: all screens constructed and drawn without exceptions")
        return 0
    except Exception:
        print("FAIL")
        traceback.print_exc()
        return 1
    finally:
        try:
            if app is not None:
                app.running = False
        except Exception:
            pass
        try:
            pygame.quit()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
