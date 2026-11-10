"""集成自检：启动器 → 菜单 → 世界地图 → 图鉴 → 设置 → 关卡 60 秒模拟。

用法：SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy <python> tests/test_integration.py
退出码 0=PASS，1=FAIL。
"""
from __future__ import annotations

import os
import sys
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

failures: list[str] = []


def step(name, fn):
    try:
        fn()
        print(f"  OK   {name}")
    except Exception:
        failures.append(name)
        print(f"  FAIL {name}")
        traceback.print_exc()


def main():
    from game.app import App

    app = App(headless=True)
    print("== 界面切换 ==")
    for name in ("launcher", "menu", "worldmap", "almanac", "settings"):
        def _go(n=name):
            app.switch(n)
            for _ in range(5):
                app.screen_obj.update(1 / 60)
                app.screen_obj.draw(app.screen)
            assert app.screen_name == n, f"实际 {app.screen_name}"
            assert type(app.screen_obj).__name__ != "ErrorScreen", f"{n} 加载失败"
        step(f"switch {name}", _go)

    print("== 关卡模拟 ==")
    worlds = [w.id for w in app.data.worlds] or ["frontyard"]
    world = worlds[0]

    def _level():
        app.start_level(world, 0)
        scr = app.screen_obj
        assert type(scr).__name__ != "ErrorScreen", "关卡界面加载失败"
        for _ in range(60 * 60):  # 60 秒
            scr.update(1 / 60)
            scr.draw(app.screen)
        print("     level status:", getattr(getattr(scr, "session", scr), "status", "?"))
    step(f"level {world}_0 60s", _level)

    def _plant_and_play():
        app.start_level(world, 0)
        scr = app.screen_obj
        sess = getattr(scr, "session", scr)
        # 尝试种植：选卡 + 点击格子
        for row in range(5):
            for col in range(2):
                try:
                    if hasattr(sess, "cards") and sess.cards:
                        sess.selected_card = 0
                    sess.handle_mouse_down((190 + col * 100 + 50, 120 + row * 116 + 58))
                except Exception:
                    pass
            for _ in range(20):
                sess.update(1 / 60)
        for _ in range(60 * 90):
            sess.update(1 / 60)
        print("     plants:", len(getattr(sess, "plants", [])), "zombies:", len(getattr(sess, "zombies", [])),
              "sun:", getattr(sess, "sun", "?"), "status:", getattr(sess, "status", "?"))
        assert len(getattr(sess, "plants", [])) > 0, "没有成功种植任何植物"
    step("plant and simulate 90s", _plant_and_play)

    print()
    if failures:
        print("FAIL:", ", ".join(failures))
        return 1
    print("PASS: 集成自检通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
