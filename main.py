import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.app import App


def _selftest() -> int:
    """打包版自检：构造 App，逐个进入所有界面并跑一小段战斗。"""
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) \
        else os.path.dirname(os.path.abspath(__file__))
    log_path = os.path.join(base, "selftest.log")
    lines = []
    code = 0
    app = None
    try:
        app = App(headless=True)
        lines.append("App(headless) OK")
        lines.append(f"worlds={len(app.data.worlds)} plants={len(app.data.plants)} "
                     f"zombies={len(app.data.zombies)}")
    except Exception:
        code = 1
        lines.append("App: FAIL\n" + traceback.format_exc())

    if app is not None:
        for name in ("launcher", "menu", "worldmap", "almanac", "settings",
                     "modes", "shop", "garden", "bosses", "minigames",
                     "survival", "fusion"):
            try:
                app.switch(name)
                for _ in range(3):
                    app.screen_obj.update(1.0 / 60)
                app.screen_obj.draw(app.screen)
                lines.append(f"screen {name}: OK")
            except Exception:
                code = 1
                lines.append(f"screen {name}: FAIL\n{traceback.format_exc()}")

        try:
            app.open_seed_chooser(app.data.worlds[0].id, 0, 6)
            for _ in range(3):
                app.screen_obj.update(1.0 / 60)
            app.screen_obj.draw(app.screen)
            lines.append("screen seedchooser: OK")
        except Exception:
            code = 1
            lines.append("screen seedchooser: FAIL\n" + traceback.format_exc())

        for wid in (app.data.worlds[0].id, app.data.worlds[-1].id):
            try:
                app.start_level(wid, 0)
                for _ in range(30):
                    app.screen_obj.update(1.0 / 60)
                app.screen_obj.draw(app.screen)
                lines.append(f"level {wid}: OK")
            except Exception:
                code = 1
                lines.append(f"level {wid}: FAIL\n" + traceback.format_exc())

        try:
            app.switch("minigames")
            hub = app.screen_obj
            if getattr(hub, "cards", None):
                hub._open(hub.cards[0][1])
                for _ in range(30):
                    app.screen_obj.update(1.0 / 60)
                app.screen_obj.draw(app.screen)
                lines.append("vasebreaker: OK")
            else:
                lines.append("vasebreaker: SKIP (no cards)")
        except Exception:
            code = 1
            lines.append("vasebreaker: FAIL\n" + traceback.format_exc())

        try:
            app.start_survival(app.data.worlds[0].id)
            for _ in range(30):
                app.screen_obj.update(1.0 / 60)
            app.screen_obj.draw(app.screen)
            lines.append("survival: OK")
        except Exception:
            code = 1
            lines.append("survival: FAIL\n" + traceback.format_exc())

        try:
            bosses = (app.content_json("bosses", {"bosses": []}) or {}).get("bosses") or []
            if bosses:
                app.switch("bosses")
                hub = app.screen_obj
                if getattr(hub, "cards", None):
                    hub._open(hub.cards[0][1])
                    for _ in range(30):
                        app.screen_obj.update(1.0 / 60)
                    sess = getattr(app.screen_obj, "session", None)
                    if sess is not None and getattr(sess, "boss", None) is not None:
                        sess.boss.hp = int(sess.boss_hp_max * 0.60)
                        app.screen_obj.update(1.0 / 60)
                        sess.boss.hp = int(sess.boss_hp_max * 0.25)
                        app.screen_obj.update(1.0 / 60)
                        lines.append(f"boss phase: {getattr(sess, 'phase', '?')}/3")
                        if int(getattr(sess, "phase", 0)) < 3:
                            code = 1
                            lines.append("boss phase: FAIL (expected 3)")
                    app.screen_obj.draw(app.screen)
                    lines.append("boss: OK")
                else:
                    lines.append("boss: SKIP (no cards)")
            else:
                lines.append("boss: SKIP (no data)")
        except Exception:
            code = 1
            lines.append("boss: FAIL\n" + traceback.format_exc())

    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + f"\nexit={code}\n")
    return code


def main():
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    App().run()


if __name__ == "__main__":
    main()
