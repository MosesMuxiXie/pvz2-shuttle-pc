"""植物融合 + Boss 多阶段 headless 测试（无 pytest，直接运行）。

运行：
    $env:SDL_VIDEODRIVER="dummy"; $env:SDL_AUDIODRIVER="dummy"
    python tests/test_fusion_boss.py

覆盖：
* fusions.json 85 条配方、85 株融合植物与图鉴数据完整；
* FusionLab 扣金币/养料、解锁写存档、重复合成拦截；
* FusionScreen 构造、绘制、翻页、选择与点击“合成”；
* BossSession 66%/33% 阶段切换（提速、召唤、提示、阶段号格式）；
* BossScreen 构造与绘制（含阶段显示）；
* 玩法中心第 7 张“植物融合”卡与 4+3 布局不重叠。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PVZ2_SAVE_DIR", tempfile.mkdtemp(prefix="pvz2_fusion_boss_"))

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


def _key(key):
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="",
                              scancode=0)


def _click(screen, pos):
    for event in (_motion(pos), _down(pos), _up(pos)):
        screen.handle(event)


def _read_json(name):
    path = ROOT / "content" / f"{name}.json"
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


# --------------------------------------------------------------------- 数据
def test_fusion_data(app):
    from game.engine.fusion import load_recipes

    payload = _read_json("fusions")
    recipes = load_recipes()
    assert len(recipes) == 85, f"配方数 {len(recipes)} != 85"
    assert len(payload["recipes"]) == 85
    ids = [r.id for r in recipes]
    assert len(set(ids)) == 85, "配方 id 重复"

    results = [r.result_id for r in recipes]
    assert len(set(results)) == 85, f"融合产物应各占一株，实际 {len(set(results))}"

    plants = _read_json("plants")
    assert isinstance(plants, list)
    assert len(plants) >= 147, f"plants.json 只有 {len(plants)} 条"
    fused_ids = [p["id"] for p in plants if str(p.get("id", "")).startswith("fused_")]
    assert len(fused_ids) == 85, f"fused_* 植物 {len(fused_ids)} != 85"

    by_id = {p["id"]: p for p in plants}
    for recipe in recipes:
        assert recipe.ingredients, f"{recipe.id} 没有材料"
        assert 1 <= len(recipe.ingredients) <= 2
        assert recipe.result_id in by_id, f"{recipe.id} 产物 {recipe.result_id} 未写入 plants.json"
        assert recipe.name_zh and recipe.name_en
        result = by_id[recipe.result_id]
        assert result["name_zh"] == recipe.name_zh
        assert float(result.get("hp", 0)) > 0
        assert str(result.get("behavior") or "") in {
            "shoot", "lob", "boomerang", "produce", "wall", "instant",
            "mine", "fume", "chomp", "support", "spike"}

    almanac = _read_json("almanac")
    assert isinstance(almanac.get("plants"), dict)
    for recipe in recipes:
        entry = almanac["plants"].get(recipe.result_id)
        assert isinstance(entry, dict), f"图鉴缺少 {recipe.result_id}"
        assert entry.get("desc"), f"图鉴 {recipe.result_id} 缺少 desc"

    assert len(app.data.plants) >= 147
    for recipe in recipes:
        assert recipe.result_id in app.data.plants


# ------------------------------------------------------------------ 合成逻辑
def test_fusion_lab(app):
    from game.engine.fusion import FusionLab, load_recipes

    recipes = load_recipes()
    lab = FusionLab(app=app, recipes=recipes, save=app.save, data=app.data)
    assert len(lab) == 85

    app.save.coins = 99999
    app.save.plantfood = 9
    app.save.unlocked_plants = []

    target = recipes[13]
    before_coins = app.save.coins
    ok, message = lab.craft(target)
    assert ok, message
    assert app.save.coins == before_coins - target.unlock_cost
    assert target.result_id in app.save.unlocked_plants
    assert lab.is_unlocked(target)
    assert not lab.can_craft(target)[0], "已解锁配方不应再次合成"

    # 养料消耗
    recipe_food = next(
        r for r in recipes
        if r.plantfood_cost > 0 and r.result_id not in app.save.unlocked_plants)
    before_food = app.save.plantfood
    before_coins = app.save.coins
    ok, message = lab.craft(recipe_food)
    assert ok, message
    assert app.save.plantfood == before_food - recipe_food.plantfood_cost
    assert app.save.coins == before_coins - recipe_food.unlock_cost

    # 金币不足
    cheap = next(
        r for r in recipes if r.result_id not in app.save.unlocked_plants)
    app.save.coins = 0
    ok, reason = lab.can_craft(cheap)
    assert not ok and "金币不足" in reason, reason
    ok, message = lab.craft(cheap)
    assert not ok and "金币不足" in message

    # 查询接口
    assert lab.recipes_for(cheap.ingredients[0])
    assert lab.unlocked_count() >= 2
    assert lab.get(cheap.id) is cheap

    app.save.coins = 99999
    app.save.plantfood = 9


# ------------------------------------------------------------------ 融合界面
def test_fusion_screen(app):
    from game.screens.fusion import FusionScreen

    switched = []
    app.switch = switched.append
    app.save.coins = 99999
    app.save.plantfood = 9

    screen = FusionScreen(app)
    assert screen.name == "fusion"
    assert len(screen.lab) == 85
    screen.enter()
    assert screen._page_count_now() == 11

    screen.update(1.0 / 60.0)
    screen.draw(app.screen)

    # 点击列表第 2 行 -> 选中索引随页变化
    _click(screen, (80, 168 + 60 + 20))
    assert screen.selected == 1, screen.selected

    # 翻页按钮
    _click(screen, (334, 658))
    assert screen.page == 1, screen.page
    screen.draw(app.screen)
    _click(screen, (86, 658))
    assert screen.page == 0

    # 选一个未解锁且买得起的配方，点击“合成”
    lab = screen.lab
    index = next(i for i, r in enumerate(lab.recipes) if lab.can_craft(r)[0])
    screen._select(index)
    screen.update(1.0 / 60.0)
    assert screen.btn_craft.enabled, screen.btn_craft.label
    target_id = lab.recipes[index].result_id
    before_coins = app.save.coins
    _click(screen, (1000, 582))
    assert target_id in app.save.unlocked_plants
    assert app.save.coins == before_coins - lab.recipes[index].unlock_cost
    assert not screen.btn_craft.enabled  # 已解锁
    screen.update(1.0 / 60.0)
    screen.draw(app.screen)

    # 键盘翻页与返回
    screen.handle(_key(pygame.K_RIGHT))
    assert screen.page >= 0
    screen.handle(_key(pygame.K_ESCAPE))
    assert switched and switched[-1] == "modes", switched


# ------------------------------------------------------------------ Boss 阶段
def _boss_entry(world="egypt"):
    payload = _read_json("bosses")
    entries = payload["bosses"] if isinstance(payload, dict) else payload
    for entry in entries:
        if str(entry.get("world")) == world:
            return entry
    return entries[0]


def test_boss_phases(app):
    from game.engine.modes import BossSession, BossPhase

    entry = _boss_entry("egypt")
    assert isinstance(entry.get("phases"), list) and len(entry["phases"]) == 3
    for index, phase in enumerate(entry["phases"]):
        assert "hp_ratio" in phase and "speed_mult" in phase
        assert "eat_mult" in phase and "message" in phase
        if index:
            assert 0.0 < float(phase["hp_ratio"]) < 1.0

    world = app.data.world("egypt")
    session = BossSession(app, world, entry)
    assert session.boss is not None, "Boss 未生成"
    assert session.boss_hp_max > 0
    assert session.boss_phase_total == 3
    assert isinstance(session.boss_phase, BossPhase)
    assert str(session.boss_phase) == "1/3"
    assert f"阶段 {session.boss_phase}" == "阶段 1/3"
    assert session.boss.speed > 0
    base_zombies = len(session.zombies)

    # 60% 血量 -> 阶段 2
    session.boss.hp = int(session.boss_hp_max * 0.60)
    session.update(1.0 / 60.0)
    assert session.phase == 2, session.phase
    assert str(session.boss_phase) == "2/3"
    assert session.boss_ratio <= 0.66
    assert len(session.zombies) > base_zombies, "阶段 2 应召唤小僵尸"
    speed_2 = session.boss.speed
    assert speed_2 > 0

    # 20% 血量 -> 阶段 3
    session.boss.hp = int(session.boss_hp_max * 0.20)
    session.update(1.0 / 60.0)
    assert session.phase == 3, session.phase
    assert str(session.boss_phase) == "3/3"
    assert session.boss.speed > speed_2, "阶段 3 应再次提速"
    assert len(session.zombies) > base_zombies

    # Boss 死亡 + 小僵尸清空 -> 胜利
    session.boss.alive = False
    session.boss.state = "die"
    for zombie in session.zombies:
        zombie.alive = False
        zombie.state = "die"
    session._check_win()
    assert session.status == "won", session.status


def test_boss_screen(app):
    from game.screens.boss import BossScreen

    entry = _boss_entry("egypt")
    app.ui_payload = {"world": "egypt", "boss": entry}
    screen = BossScreen(app)
    screen.enter()
    assert screen.session is not None, screen.error
    session = screen.session
    assert session.boss_phase_total == 3
    assert str(screen._boss_phase()) == "1/3"
    screen.update(1.0 / 60.0)
    screen.draw(app.screen)

    session.boss.hp = int(session.boss_hp_max * 0.50)
    screen.update(1.0 / 60.0)
    assert session.phase >= 2
    assert "/" in str(screen._boss_phase())
    screen.draw(app.screen)

    session.boss.hp = int(session.boss_hp_max * 0.10)
    screen.update(1.0 / 60.0)
    assert session.phase == 3
    screen.draw(app.screen)


# ------------------------------------------------------------------ 玩法中心
def test_mode_hub(app):
    from game.screens.modes import ModeHubScreen

    switched = []
    app.switch = switched.append
    screen = ModeHubScreen(app)
    screen.enter()
    assert len(screen.cards) == 7, len(screen.cards)
    targets = [mode[0] for _rect, mode in screen.cards]
    assert "fusion" in targets
    assert targets.count("fusion") == 1

    rects = [rect for rect, _mode in screen.cards]
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not rects[i].colliderect(rects[j]), \
                f"卡片重叠：{rects[i]} / {rects[j]}"
    for rect in rects:
        assert rect.right <= 1280 and rect.bottom <= 720, rect

    fusion_card = next(rect for rect, mode in screen.cards
                       if mode[0] == "fusion")
    _click(screen, fusion_card.center)
    assert switched and switched[-1] == "fusion", switched
    screen.update(1.0 / 60.0)
    screen.draw(app.screen)


def main():
    import game.app as app_module

    app_module.UpdateChecker = _DummyUpdateChecker
    pygame.init()
    app = app_module.App(headless=True)
    try:
        test_fusion_data(app)
        test_fusion_lab(app)
        test_fusion_screen(app)
        test_boss_phases(app)
        test_boss_screen(app)
        test_mode_hub(app)
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        try:
            pygame.display.quit()
        except Exception:
            pass
        try:
            pygame.quit()
        except Exception:
            pass
    print("PASS: 融合 85 配方 / 85 株，Boss 3 阶段切换与界面绘制正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
