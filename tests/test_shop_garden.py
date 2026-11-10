"""商店 2.0 / 禅境花园 2.0 的冒烟测试（SDL dummy，无 pytest 依赖）。

运行：
    <python> tests/test_shop_garden.py
退出码 0 表示全部通过。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["PVZ2_GARDEN_FAST"] = "1"
_TEST_SAVE_DIR = tempfile.mkdtemp(prefix="pvz2_shop_garden_")
os.environ["PVZ2_SAVE_DIR"] = _TEST_SAVE_DIR

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

import game.app as app_module  # noqa: E402
from game.save import SaveData  # noqa: E402
from game.screens.garden import GardenScreen, POT_N  # noqa: E402
from game.screens.shop import ShopScreen, load_shop_items  # noqa: E402

SAVE_PATH = Path(_TEST_SAVE_DIR) / "save.json"


class _DummyUpdateChecker:
    done = True
    result = {}

    def start(self):
        return self


def _reset_save():
    try:
        if SAVE_PATH.exists():
            SAVE_PATH.unlink()
    except OSError:
        pass


def _app():
    _reset_save()
    app_module.UpdateChecker = _DummyUpdateChecker
    pygame.init()
    app = app_module.App(headless=True)
    app.switch = lambda target: setattr(app, "_switched_to", target)
    # 测试不加载 DragonBones 缩略图，画面能画出来即可。
    app.assets.db_thumb = lambda *args, **kwargs: None
    return app


def _click(screen, pos):
    pygame.event.clear()
    screen.handle(pygame.event.Event(pygame.MOUSEMOTION, pos=pos,
                                     rel=(0, 0), buttons=(0, 0, 0)))
    screen.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=1))
    screen.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1))


def _key(screen, key, mod=0):
    pygame.event.clear()
    screen.handle(pygame.event.Event(pygame.KEYDOWN, key=key, mod=mod,
                                    unicode="", scancode=0))


def _frames(screen, app, count=2):
    for _ in range(count):
        screen.update(1 / 60)
        screen.draw(app.screen)


def test_shop_categories_and_pages():
    app = _app()
    screen = ShopScreen(app)
    screen.enter()
    assert [t[0] for t in screen.tab_defs] == [
        "seeds", "items", "currency", "bundles"], screen.tab_defs
    assert len(load_shop_items(app)) >= 500
    assert screen.page_count() >= 2
    _frames(screen, app)

    # 点击「货币」页签。
    rect = next(r for r, tid, _ in screen._tab_rects if tid == "currency")
    _click(screen, rect.center)
    assert screen.tab_index == 2
    assert screen.page == 0
    assert all(item["tab"] == "currency" for item in screen._page_items())

    # 键盘左右切换 / Tab 切换。
    _key(screen, pygame.K_RIGHT)
    assert screen.tab_index == 3
    _key(screen, pygame.K_TAB)
    assert screen.tab_index == 0
    _key(screen, pygame.K_LEFT)
    assert screen.tab_index == 3

    # 翻页按钮。
    screen.tab_index = 1
    screen.page = 0
    first_ids = [x["id"] for x in screen._page_items()]
    assert screen.page_count() > 1
    _click(screen, screen._page_next.center)
    assert screen.page == 1
    assert [x["id"] for x in screen._page_items()] != first_ids
    _click(screen, screen._page_prev.center)
    assert screen.page == 0

    # ESC 返回模式选择。
    _key(screen, pygame.K_ESCAPE)
    assert getattr(app, "_switched_to", None) == "modes"
    _frames(screen, app)


def test_shop_buy_and_insufficient_coins():
    app = _app()
    screen = ShopScreen(app)
    save = app.save
    save.coins = 100000
    plant_item = next(item for item in screen._page_items()
                      if item["item_type"] == "plant"
                      and item["implemented"])
    index = screen._page_items().index(plant_item)
    pid = plant_item["payload"]["plant_id"]
    _click(screen, screen._card_rect(index).center)
    assert save.owns_plant(pid), pid
    assert save.coins == 100000 - plant_item["price"]
    assert screen._is_owned(plant_item)
    _frames(screen, app)

    # 已购商品不能重复购买。
    coins = save.coins
    assert not screen.buy(index)
    assert save.coins == coins

    # 金币不足：选一个当前页付不起的商品。
    expensive = next((item for item in screen._page_items()
                      if item["price"] > 0 and item["implemented"]
                      and not screen._is_owned(item)), None)
    assert expensive is not None
    save.coins = 0
    save.save()
    before = list(save.unlocked_plants)
    screen.buy(screen._page_items().index(expensive))
    assert "不足" in screen._toast, screen._toast
    assert save.unlocked_plants == before

    # 货币包：金币买金币包，净变化为 0（花 3000 得 3000）。
    save.coins = 10000
    screen.tab_index = next(i for i, (tid, _) in enumerate(screen.tab_defs)
                            if tid == "currency")
    screen.page = 0
    coin_pack = next(item for item in screen._page_items()
                     if item["item_type"] == "coin")
    result = screen.buy(screen._page_items().index(coin_pack))
    assert result
    assert save.coins == 10000

    # 强化道具写入 settings。
    screen.tab_index = next(i for i, (tid, _) in enumerate(screen.tab_defs)
                            if tid == "items")
    save.coins = 100000
    upgrade = None
    upgrade_index = -1
    for page in range(screen.page_count()):
        screen.page = page
        for i, item in enumerate(screen._page_items()):
            if (item["item_type"] == "gameupgrade"
                    and "sun_start_bonus" in item["payload"]):
                upgrade = item
                upgrade_index = i
                break
        if upgrade is not None:
            break
    assert upgrade is not None
    assert screen.buy(upgrade_index)
    assert save.settings.get("sun_start_bonus") == \
        upgrade["payload"]["sun_start_bonus"]


def test_garden_plant_water_harvest_shovel():
    app = _app()
    screen = GardenScreen(app)
    save = app.save
    save.coins = 500
    save.plantfood = 0
    save.save()
    assert POT_N == 8
    assert all(screen.pot_rect(i).width == 210 for i in range(POT_N))

    # 点击空盆 → 选择器 → 点击第一株植物。
    _click(screen, screen.pot_rect(0).center)
    assert screen.picker_open and screen.picker_slot == 0
    assert len(screen.picker_choices) >= 42
    _frames(screen, app)
    _click(screen, screen.picker_cell_rect(0).center)
    assert not screen.picker_open
    entry = save.garden_slot(0)
    assert entry is not None
    assert entry["slot"] == 0 and entry["plant"]
    assert set(("stage", "planted", "last_water", "ready", "watered")) <= set(entry)
    assert entry["ready"] > entry["planted"]
    assert entry["watered"] == 0

    # 浇水：扣金币、缩短 ready、次数 +1。
    coins = save.coins
    ready = entry["ready"]
    _click(screen, screen.water_rect(0).center)
    entry = save.garden_slot(0)
    assert entry is not None
    assert entry["watered"] == 1
    assert entry["last_water"] > 0
    assert entry["ready"] < ready
    assert save.coins == coins - screen.water_cost

    # 强制成熟后收获：金币 + 养料，花盆清空。
    entry["ready"] = int(time.time()) - 1
    entry["stage"] = 3
    save.save()
    coins, food = save.coins, save.plantfood
    _click(screen, screen.harvest_rect(0).center)
    assert save.garden_slot(0) is None
    assert save.coins > coins
    assert save.plantfood > food

    # 再种一盆并铲除。
    _click(screen, screen.pot_rect(1).center)
    assert screen.picker_open
    _click(screen, screen.picker_cell_rect(1).center)
    assert save.garden_slot(1) is not None
    _click(screen, screen.shovel_rect(1).center)
    assert save.garden_slot(1) is None

    # 选择器翻页 + 绘制。
    _click(screen, screen.pot_rect(2).center)
    assert screen.picker_open
    assert screen.picker_page_count() >= 2
    _click(screen, screen._picker_next.center)
    assert screen.picker_page == 1
    _frames(screen, app)
    _key(screen, pygame.K_ESCAPE)
    assert not screen.picker_open
    _key(screen, pygame.K_ESCAPE)
    assert getattr(app, "_switched_to", None) == "modes"


def test_old_save_compat():
    _reset_save()
    now = int(time.time())
    old = {
        "version": 2,
        "coins": 321,
        "completed": ["frontyard:1"],
        "stars": {"frontyard:1": [1, 0, 0]},
        "unlocked_plants": ["iris"],
        "plantfood": 4,
        "garden": [
            {"slot": 0, "plant": "peashooter",
             "planted": now - 100, "ready": now + 100},
            {"slot": 1, "plant": "sunflower", "planted": now - 10},
            {"slot": 2, "plant": "wallnut", "planted": now - 50,
             "ready": now - 1, "stage": 3, "watered": 2},
            {"slot": 3, "plant": ""},
            "bad-entry",
        ],
    }
    SAVE_PATH.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    data = SaveData.load()
    assert data.version >= 3
    assert data.coins == 321
    assert data.completed == ["frontyard:1"]
    assert data.plantfood == 4
    assert len(data.garden) == 3
    first = data.garden_slot(0)
    assert first["stage"] in range(4)
    assert first["last_water"] == 0
    assert first["watered"] == 0
    assert data.garden_slot(1)["ready"] > data.garden_slot(1)["planted"]
    assert data.garden_slot(2)["stage"] == 3
    # 旧存档还能继续操作花园。
    data.garden_plant(4, "peashooter", 10)
    assert data.garden_slot(4)["stage"] == 0

    # 兼容 garden 为 {slot: entry} 字典的写法。
    old2 = {"version": 2,
            "garden": {"0": {"plant": "peashooter", "planted": now - 5,
                             "ready": now + 50}}}
    SAVE_PATH.write_text(json.dumps(old2), encoding="utf-8")
    data2 = SaveData.load()
    assert [g["slot"] for g in data2.garden] == [0]
    assert data2.garden_slot(0)["plant"] == "peashooter"

    # 保存后 version 3 且字段完整。
    data.save()
    raw = json.loads(SAVE_PATH.read_text(encoding="utf-8"))
    assert raw["version"] == 3
    assert set(("stage", "last_water", "watered")) <= set(raw["garden"][0])


def main():
    tests = [
        test_shop_categories_and_pages,
        test_shop_buy_and_insufficient_coins,
        test_garden_plant_water_harvest_shovel,
        test_old_save_compat,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL {test.__name__}")
            traceback.print_exc()
    if failures:
        print(f"{failures} test(s) failed")
        return 1
    print(f"all {len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
