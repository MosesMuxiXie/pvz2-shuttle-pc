"""渲染各界面截图，便于快速目检。

用法：
  <python> tools/screenshot.py                 # launcher/menu/worldmap/almanac/settings
  <python> tools/screenshot.py level frontyard 0
输出：PvZ2SHUTTLE/work_out/shot_<screen>.png
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "work_out")
os.makedirs(OUT, exist_ok=True)

import pygame  # noqa: E402

from game.app import App  # noqa: E402


def shot(app: App, name: str):
    app.screen_obj.update(0.016)
    app.screen_obj.draw(app.screen)
    path = os.path.join(OUT, f"shot_{name}.png")
    pygame.image.save(app.screen, path)
    print("saved", path)


def main():
    app = App(headless=True)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args and args[0] == "level":
        world = args[1] if len(args) > 1 else "frontyard"
        idx = int(args[2]) if len(args) > 2 else 0
        app.start_level(world, idx)
        app.screen_obj.update(0.016)
        shot(app, f"level_{world}_{idx}")
        # 快进 20 秒看战斗
        for _ in range(1200):
            app.screen_obj.update(1 / 60)
        shot(app, f"level_{world}_{idx}_20s")
        return
    for name in ("launcher", "menu", "worldmap", "almanac", "settings"):
        app.switch(name)
        shot(app, name)


if __name__ == "__main__":
    main()
