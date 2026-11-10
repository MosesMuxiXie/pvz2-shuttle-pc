"""世界地图（世界轮播 + 世界详情 + 钥匙解锁）无窗口测试。

运行方式::

    python tests/test_worldmap.py

测试使用 SDL dummy 视频/音频驱动和独立临时存档目录，不会读写真实存档。
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# 每次测试使用一个全新的存档目录；必须在 import game.app 之前设置。
_SAVE_DIR = tempfile.mkdtemp(prefix="pvz2_worldmap_test_")
os.environ["PVZ2_SAVE_DIR"] = _SAVE_DIR

import pygame  # noqa: E402

import game.app as app_module  # noqa: E402


class _DummyUpdateChecker:
    def __init__(self, *args, **kwargs):
        pass

    def start(self, *args, **kwargs):
        pass

    def check(self, *args, **kwargs):
        return None


app_module.UpdateChecker = _DummyUpdateChecker


def click(screen, pos):
    """发送完整的按下 + 抬起，模拟真实鼠标点击。"""
    pos = (int(pos[0]), int(pos[1]))
    screen.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos))
    screen.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos))


def key(screen, code):
    screen.handle(pygame.event.Event(pygame.KEYDOWN, key=code, mod=0,
                                     unicode="", scancode=0))


def draw(screen, frames=3):
    surf = pygame.Surface((1280, 720))
    for _ in range(frames):
        screen.update(0.1)
        screen.draw(surf)
    return surf


def main() -> int:
    app = app_module.App(headless=True)
    app.switch("worldmap")
    screen = app.screen_obj
    save = app.save

    # ---- 1. 构造 / 动态世界数量 / 绘制 ----
    assert screen is not None and screen.name == "worldmap"
    assert len(screen.worlds) >= 12, f"世界数量异常: {len(screen.worlds)}"
    assert len(screen.world_meta) >= 12, f"worldmap.json 条目异常: {len(screen.world_meta)}"
    assert screen.view == "carousel"
    surf = draw(screen)
    assert surf.get_size() == (1280, 720)

    # ---- 2. 左右键 / 滚轮轮播 ----
    n = len(screen.worlds)
    start = screen.index
    key(screen, pygame.K_RIGHT)
    assert screen.index == (start + 1) % n, "右键没有切到下一个世界"
    key(screen, pygame.K_LEFT)
    assert screen.index == start, "左键没有切回上一个世界"
    screen.handle(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1))
    assert screen.index == (start + 1) % n, "滚轮下滚没有切到下一个世界"
    screen.handle(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1))
    assert screen.index == start, "滚轮上滚没有切回上一个世界"
    key(screen, pygame.K_RIGHT)
    key(screen, pygame.K_LEFT)

    # ---- 3. 点击中央卡片进入世界详情 ----
    click(screen, screen.card_rect().center)
    assert screen.view == "detail", f"点击中央卡片未进入详情: {screen.view}"
    assert screen.detail_index == start
    total0 = int(screen.worlds[start]["total"])
    assert total0 > 0
    per_page = 10 if total0 <= 10 else 15
    assert screen.per_page == per_page
    assert screen.page_count == max(1, (total0 + per_page - 1) // per_page)
    assert 1 <= len(screen.level_cells) <= per_page
    assert [c["index"] for c in screen.level_cells] == list(
        range(0, min(per_page, total0)))
    draw(screen)

    # 关卡翻页
    if screen.page_count > 1:
        screen._change_page(1)
        assert screen.level_page == 1
        assert screen.level_cells[0]["index"] == per_page
        screen._change_page(-1)
        assert screen.level_page == 0

    # ESC 从详情回到轮播，而不是直接退出
    key(screen, pygame.K_ESCAPE)
    assert screen.view == "carousel", "详情内 ESC 应回到轮播"

    # ---- 4. 星章补发钥匙：20 星 -> 2 把钥匙，且不重复发 ----
    frontyard = screen.worlds[start]["id"]
    for i in range(20):
        save.set_stars(frontyard, i, [True, False, False])
    assert save.total_stars() == 20
    assert save.keys == 2, f"20 星应补发 2 把钥匙，实际 {save.keys}"
    assert save.keys_earned_from_stars == 2
    # 再设置一次星章不应重复发钥匙
    save.set_stars(frontyard, 0, [True, False, False])
    assert save.keys == 2, "重复设置星章重复补发了钥匙"
    screen.enter()  # 重新进入地图会 sync 一次，仍应幂等
    screen = app.screen_obj
    assert save.keys == 2, "进入地图时重复补发了钥匙"

    # ---- 5. 用钥匙解锁顺序链上的第一个未解锁世界 ----
    first_locked = screen.first_locked_index()
    assert first_locked == 1, f"顺序链第一个未解锁世界应为 1，实际 {first_locked}"
    assert not screen.world_unlocked(first_locked)
    locked_id = screen.worlds[first_locked]["id"]
    assert screen.unlock_cost(first_locked) == 1
    screen.open_detail(first_locked)
    assert screen.btn_unlock.visible and screen.btn_unlock.enabled
    assert screen.unlock_current() is True
    assert save.unlocked(locked_id), "解锁后 save.unlocked_worlds 未写入"
    assert save.keys == 1, f"解锁应消耗 1 把钥匙，剩余 {save.keys}"
    assert screen.world_unlocked(first_locked)
    assert screen.first_locked_index() == 2
    # 解锁后该世界第一关应可进入
    assert screen.level_cells and not screen.level_cells[0]["locked"]
    draw(screen)

    # ---- 6. 进入关卡回调 open_seed_chooser(world, index, slots) ----
    calls = []
    app.open_seed_chooser = lambda w, i, slots: calls.append((w, i, slots))
    screen.open_detail(0)
    assert screen.enter_level(0) is True
    assert len(calls) == 1
    world_arg, level_arg, slots_arg = calls[0]
    assert world_arg == frontyard
    assert level_arg == 0
    assert 2 <= slots_arg <= 9

    # ---- 7. 锁定世界不可进入 ----
    locked = screen.first_locked_index()
    assert locked is not None
    screen.open_detail(locked)
    assert not screen.world_unlocked(locked)
    assert all(cell["locked"] for cell in screen.level_cells)
    assert screen.enter_level(0) is False
    assert len(calls) == 1, "锁定世界不应触发 open_seed_chooser"
    draw(screen)

    # ---- 8. 钥匙读写接口与旧存档容错 ----
    save.add_keys(2)
    assert save.keys == 3
    assert save.spend_keys(3) is True and save.keys == 0
    assert save.spend_keys(1) is False
    save.add_keys(-5)
    assert save.keys == 0, "add_keys 不应接受负数"

    import json
    from game.save import SaveData

    save_path = Path(_SAVE_DIR) / "save.json"
    save_path.write_text(json.dumps({"coins": 7, "stars": {}}), encoding="utf-8")
    legacy = SaveData.load()
    assert legacy.keys == 0, "旧存档缺少 keys 时应默认为 0"
    stars = {f"frontyard:{i}": [1, 0, 0] for i in range(20)}
    save_path.write_text(json.dumps({"stars": stars}), encoding="utf-8")
    legacy = SaveData.load()
    assert legacy.keys == 2, "旧存档按累计星章补发钥匙失败"

    # ---- 9. 返回菜单 ----
    screen = app.screen_obj
    key(screen, pygame.K_ESCAPE)  # 详情 -> 轮播
    assert screen.view == "carousel"
    screen.go_back()
    assert app.screen_name == "menu", f"ESC 应返回 menu，实际 {app.screen_name}"

    pygame.quit()
    print("PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
