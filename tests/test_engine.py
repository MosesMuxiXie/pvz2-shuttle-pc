"""引擎核心自检：无窗口模拟完整一局（种植→僵尸→豌豆→死亡→波次→胜负）。

运行：
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy <python> tests/test_engine.py
退出码 0=PASS，1=FAIL。

不读取 content/ 与 assets/db：全部用内存里的示例 PlantDef/ZombieDef/LevelDef，
因此美术与关卡数据未就绪时也能验证引擎逻辑。
"""
from __future__ import annotations

import os
import sys
import traceback
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from game.assets import Assets  # noqa: E402
from game.data import (LevelDef, PlantDef, Wave, WorldDef, ZombieDef,  # noqa: E402
                       ZombieSpawn)
from game.engine import Board, LevelSession, WaveDirector  # noqa: E402
from game.engine import combat  # noqa: E402
from game.engine.board import BOARD_X, BOARD_Y, cell_center  # noqa: E402
from game.engine.entities import Plant, Projectile, Sun, Zombie  # noqa: E402

FAILS: list[str] = []
FRAME = 1.0 / 60.0


# ---------------------------------------------------------------- 测试脚手架
class DummyApp:
    """只提供引擎需要的服务：assets / data / font。"""

    def __init__(self):
        self.assets = Assets(self)
        self.data = SimpleNamespace(plants={}, zombies={})

    def font(self, size, bold=False):
        return self.assets.font(size, bold)


def make_world():
    return WorldDef(id="test_world", name_zh="测试世界", levels=3)


def make_defs():
    plants = {
        "sunflower": PlantDef(id="sunflower", name_zh="向日葵", cost=50,
                              cooldown=1.0, hp=300, behavior="produce",
                              sun_value=25, sun_interval=6.0, art="sunflower"),
        "peashooter": PlantDef(id="peashooter", name_zh="豌豆射手", cost=100,
                               cooldown=1.2, hp=300, behavior="shoot",
                               damage=20, interval=1.2, rows=[0], art="peashooter"),
        "wallnut": PlantDef(id="wallnut", name_zh="坚果墙", cost=50,
                            cooldown=1.0, hp=1200, behavior="wall", art="wallnut"),
    }
    zombies = {
        "basic": ZombieDef(id="basic", name_zh="普通僵尸", hp=190,
                           speed=0.185, eat_dps=100, art="basic"),
        "cone": ZombieDef(id="cone", name_zh="路障僵尸", hp=190,
                          speed=0.185, eat_dps=100, art="cone",
                          armor=[{"hp":180, "name": "路障", "art": ""}]),
        "runner": ZombieDef(id="runner", name_zh="快跑僵尸", hp=190,
                            speed=0.25, eat_dps=100, art="runner"),
    }
    return plants, zombies


def build_app():
    app = DummyApp()
    plants, zombies = make_defs()
    app.data.plants.update(plants)
    app.data.zombies.update(zombies)
    return app


def win_level():
    waves = [
        Wave(delay=2.0, zombies=[ZombieSpawn("basic", rows=[0, 1, 2])]),
        Wave(delay=12.0, zombies=[ZombieSpawn("basic", rows=[2, 3, 4])]),
        Wave(delay=15.0, flag=True, zombies=[
            ZombieSpawn("basic", rows=[0, 1, 2, 3, 4]),
            ZombieSpawn("cone", rows=[1, 3]),
        ]),
    ]
    return LevelDef(id="win_test", world="test_world", index=1,
                    title="胜利测试", sun=500,
                    deck=["sunflower", "peashooter", "wallnut"], waves=waves)


def lose_level():
    waves = [
        Wave(delay=1.0, zombies=[ZombieSpawn("runner", row=0),
                                 ZombieSpawn("runner", row=0)]),
        Wave(delay=55.0, zombies=[ZombieSpawn("runner", row=0)]),
    ]
    return LevelDef(id="lose_test", world="test_world", index=2,
                    title="失败测试", sun=100, deck=["peashooter"], waves=waves)


def plant_plan(sess):
    """自动种植策略：前两列向日葵，之后 2~4 列豌豆。"""
    plan = [
        ("sunflower", [(r, c) for c in (0, 1) for r in range(5)]),
        ("peashooter", [(r, c) for c in (2, 3, 4) for r in range(5)]),
    ]
    for pid, cells in plan:
        idx = next((i for i, c in enumerate(sess.cards)
                    if c["plant_id"] == pid), None)
        if idx is None:
            continue
        card = sess.cards[idx]
        if card["cd_remain"] > 0.0:
            continue
        for (r, c) in cells:
            if sess.board.plant_at(r, c) is not None:
                continue
            if sess.sun < card["cost"]:
                break
            if sess.selected_card != idx:
                sess.select_card(idx)
            if sess.selected_card == idx:
                sess.try_plant(r, c)
            break


def autoplay(sess, seconds, draw=False, surface=None, collect=True):
    """自动收集阳光 + 种植，跑满 seconds 或直到结束。返回逐秒阳光采样。"""
    sun_samples = []
    total_frames = int(seconds / FRAME)
    for frame in range(total_frames):
        if collect:
            for sun in list(sess.suns):
                if getattr(sun, "collectible", False):
                    sess.collect_suns_at((int(sun.x), int(sun.y)))
        plant_plan(sess)
        sess.update(FRAME)
        if draw and surface is not None and frame % 90 == 0:
            sess.draw(surface)
        if frame % 60 == 0:
            sun_samples.append(sess.sun)
        if sess.status != "playing":
            break
    return sun_samples


def step(name, fn):
    try:
        fn()
        print(f"  OK   {name}")
    except Exception:
        FAILS.append(name)
        print(f"  FAIL {name}")
        traceback.print_exc()


# ---------------------------------------------------------------- 用例
def test_board():
    b = Board()
    assert (b.rows, b.cols) == (5, 9), (b.rows, b.cols)
    assert b.in_bounds(0, 0) and b.in_bounds(4, 8)
    assert not b.in_bounds(-1, 0) and not b.in_bounds(0, 9)
    cx, cy = b.cell_center(0, 0)
    assert (cx, cy) == cell_center(0, 0)
    assert BOARD_X < cx < BOARD_X + 100 and BOARD_Y < cy < BOARD_Y + 116
    assert b.cell_at((cx, cy)) == (0, 0)
    assert b.cell_at((5, 5)) is None
    assert b.cell_at((BOARD_X + 899, BOARD_Y + 579)) == (4, 8)

    marker = object()
    assert b.plant_at(2, 3) is None
    assert b.set_plant(2, 3, marker) is None
    assert b.plant_at(2, 3) is marker
    assert not b.is_empty(2, 3)
    assert b.clear(2, 3) is marker
    assert b.plant_at(2, 3) is None


def test_waves():
    waves = [
        Wave(delay=1.0, zombies=[ZombieSpawn("basic", row=0)]),
        Wave(delay=2.0, flag=True, zombies=[ZombieSpawn("basic", rows=[0, 1])]),
        Wave(delay=2.0, zombies=[ZombieSpawn("cone", row=2)]),
    ]
    ld = LevelDef(id="w", sun=0, waves=waves)
    d = WaveDirector(ld, rows=5)
    assert d.total_waves == 3
    assert d.due_times == [1.0, 3.0, 5.0], d.due_times

    assert d.update(0.5) == []
    ev1 = d.update(0.6)
    assert len(ev1) == 1 and ev1[0].type == "basic" and ev1[0].row == 0
    assert d.current_wave == 0 and d.wave_index == 1

    ev2 = d.update(2.0)
    assert 4 <= len(ev2) <= 6, len(ev2)          # flag 波 2~3 倍
    assert all(e.flag for e in ev2)
    assert d.flag_waves_started == 1 and d.wave_index == 2

    ev3 = d.update(2.5)
    assert len(ev3) == 1 and ev3[0].is_final and ev3[0].type == "cone"
    assert d.finished and d.progress == 1.0
    assert d.update(10.0) == []


def test_combat_rules():
    zdef = ZombieDef(id="cone", hp=190, armor=[{"hp": 180, "name": "路障"}])
    z = SimpleNamespace(alive=True, state="walk", hp=190.0, hit_flash=0.0,
                        armor=[{"hp": 180.0, "max_hp": 180.0, "art": "", "name": "路障"}],
                        _counted_dead=False, x=300.0, row=0, ground_y=200.0)
    combat.damage_zombie(z, 100.0)
    assert z.armor[0]["hp"] == 80.0 and z.hp == 190.0
    combat.damage_zombie(z, 100.0)
    assert z.armor == [] and z.hp == 170.0
    combat.damage_zombie(z, 20.0, pierce_armor=True)
    assert z.hp == 150.0
    combat.damage_zombie(z, 9999.0)
    assert z.state == "die" and z.hp == 0.0 and z._counted_dead

    # 子弹命中：豌豆走到僵尸身上造成伤害
    target = SimpleNamespace(alive=True, state="walk", hp=190.0, hit_flash=0.0,
                             armor=[], _counted_dead=False, x=300.0, row=0,
                             ground_y=200.0,
                             rect=pygame.Rect(268, 80, 64, 120))

    class StubLevel:
        zombies = [target]
        plants = []

        def spawn_burst(self, *a, **k):
            pass

        def area_damage(self, *a, **k):
            pass

        def on_zombie_killed(self, z):
            pass

    lvl = StubLevel()
    pea = Projectile("pea", x=250.0, y=target.ground_y - 60, row=0, damage=20.0)
    for _ in range(20):
        pea.update(1 / 60, lvl)
        if not pea.alive:
            break
    assert target.hp < 190.0, target.hp

    # 阳光：落地后 13 秒消失
    sun = Sun(300, 260, 260, value=25)
    assert sun.collectible
    sun.update(13.5)
    assert not sun.alive


def test_card_and_shovel():
    app = build_app()
    sess = LevelSession(app, make_world(), win_level())
    surf = pygame.Surface((1280, 720))
    assert sess.status == "playing"
    assert sess.sun == 500
    assert len(sess.cards) == 3
    assert all(c["cd_remain"] == 0 for c in sess.cards)
    sess.update(FRAME)
    sess.draw(surf)

    # 鼠标选卡 + 点格子种植
    assert sess.handle_mouse_down(sess.card_rects[1].center)
    assert sess.selected_card == 1, sess.selected_card
    r, c = 3, 4
    cx, cy = sess.board.cell_center(r, c)
    assert sess.handle_mouse_down((cx, cy))
    assert sess.board.plant_at(r, c) is not None
    assert sess.selected_card is None
    assert sess.sun == 400, sess.sun
    assert sess.cards[1]["cd_remain"] > 0

    # 冷却期间不能再次选卡；强行指定也会被 try_plant 拦下
    assert not sess.select_card(1)
    sess.selected_card = 1
    assert not sess.try_plant(3, 3)
    assert sess.board.plant_at(3, 3) is None
    sess.selected_card = None

    # 铲子
    assert sess.toggle_shovel()
    assert sess.try_shovel(r, c)
    assert sess.board.plant_at(r, c) is None
    assert not sess.try_shovel(r, c)
    sess.toggle_shovel()

    # 冷却随时间恢复
    sess.update(2.0)
    assert sess.cards[1]["cd_remain"] == 0.0

    # 非法位置/未选卡
    assert not sess.try_plant(-1, 0)
    assert not sess.try_plant(0, 9)
    sess.selected_card = None
    assert not sess.try_plant(0, 0)


def test_win_simulation():
    app = build_app()
    results = []
    sess = LevelSession(app, make_world(), win_level(), on_finish=results.append)
    surf = pygame.Surface((1280, 720))
    assert sess.total_waves == 3 and sess.wave_index == 0

    suns = autoplay(sess, 180.0, draw=True, surface=surf)
    print(f"     win sim: status={sess.status} time={sess.time:.1f}s "
          f"plants={len(sess.plants)} kills={sess.zombie_killed} "
          f"spawned={sess.zombies_spawned} shots={sess.shots_fired} "
          f"sun={sess.sun} collected={sess.sun_collected} waves={sess.wave_index}")
    assert sess.status == "won", f"未胜利：{sess.status} @ {sess.time:.1f}s"
    assert results == [True], results
    assert sess.zombie_killed > 0 and sess.shots_fired > 0
    assert sess.zombies_spawned > 0
    assert len(sess.plants) > 0
    assert sess.sun_collected > 0
    assert min(suns) != max(suns), "阳光数值从未变化"
    assert sess.wave_index == sess.total_waves
    # 结束回调只调用一次
    sess.update(1.0)
    assert results == [True], results
    # 网格一致性
    for p in sess.plants:
        assert sess.board.plant_at(p.row, p.col) is p
    sess.draw(surf)


def test_lose_simulation():
    app = build_app()
    results = []
    sess = LevelSession(app, make_world(), lose_level(), on_finish=results.append)
    assert sess.total_waves == 2
    for _ in range(int(180 / FRAME)):
        sess.update(FRAME)
        if sess.status != "playing":
            break
    print(f"     lose sim: status={sess.status} time={sess.time:.1f}s "
          f"zombies={len(sess.zombies)} mower_used={sess.mower_at_row(0).used}")
    assert sess.status == "lost", f"应该失败，实际 {sess.status} @ {sess.time:.1f}s"
    assert results == [False], results
    assert sess.plants == []
    sess.update(1.0)
    assert results == [False], results


def test_pause_and_banner():
    app = build_app()
    sess = LevelSession(app, make_world(), win_level())
    assert sess.toggle_pause()
    t0 = sess.time
    sess.update(1.0)
    assert sess.time == t0, "暂停时不应推进时间"
    assert sess.toggle_pause()
    sess.update(1.0)
    assert sess.time > t0
    sess.start_wave_banner("一大波僵尸来袭！")
    assert sess.banner_text and sess.banner_timer > 0
    surf = pygame.Surface((1280, 720))
    sess.draw(surf)
    sess.shake = 8.0
    sess.draw(surf)


def test_special_plants():
    """一次性/地雷/吞噬/喷雾/抛射/回旋镖/减速/啃食 的冒烟测试。"""
    app = build_app()
    plants = app.data.plants
    plants["cherry"] = PlantDef(id="cherry", name_zh="樱桃炸弹", cost=150,
                                behavior="instant", damage=2000, delay=0.3,
                                extra={"radius": 140}, art="cherry")
    plants["mine"] = PlantDef(id="mine", name_zh="土豆雷", cost=25,
                              behavior="mine", damage=1800, art="mine")
    plants["chomper"] = PlantDef(id="chomper", name_zh="大嘴花", cost=150,
                                 behavior="chomp", art="chomper")
    plants["fumer"] = PlantDef(id="fumer", name_zh="大喷菇", cost=75,
                               behavior="fume", damage=20, interval=0.5,
                               melee_range=2.0, art="fumer")
    plants["lobber"] = PlantDef(id="lobber", name_zh="投手", cost=100,
                                behavior="lob", damage=20, interval=1.2,
                                splash=60.0, art="lobber")
    plants["boomer"] = PlantDef(id="boomer", name_zh="回旋镖", cost=100,
                                behavior="boomerang", damage=20, interval=1.2,
                                pierce=True, art="boomer")
    plants["snowpea"] = PlantDef(id="snowpea", name_zh="寒冰射手", cost=175,
                                 behavior="shoot", damage=20, interval=1.2,
                                 slow=3.0, art="snowpea")

    ld = LevelDef(id="special", world="test_world", sun=1000, deck=[], waves=[])
    sess = LevelSession(app, make_world(), ld)
    assert sess.total_waves == 0
    b = sess.board

    def add_plant(pid, row, col):
        p = Plant(app.data.plants[pid], row, col, app.assets)
        b.set_plant(row, col, p)
        sess.plants.append(p)
        return p

    def add_zombie(zid, row, x):
        z = Zombie(app.data.zombies[zid], row, x, app.assets)
        sess.zombies.append(z)
        return z

    # 樱桃：延迟爆炸清掉周围僵尸
    cherry = add_plant("cherry", 0, 4)
    z1 = add_zombie("basic", 0, cherry.x + 90)
    for _ in range(30):
        cherry.update(1 / 60, sess)
    assert not cherry.alive and z1.state == "die", (cherry.alive, z1.state)

    # 土豆雷：武装 2 秒后接触爆炸（穿透护甲）
    mine = add_plant("mine", 1, 4)
    for _ in range(130):
        mine.update(1 / 60, sess)
    assert mine.mine_armed
    z2 = add_zombie("cone", 1, mine.x + 30)
    mine.update(1 / 60, sess)
    assert not mine.alive and z2.state == "die"

    # 大嘴花：吞掉前方僵尸并进入长冷却
    chomper = add_plant("chomper", 2, 4)
    z3 = add_zombie("basic", 2, chomper.x + 40)
    chomper.update(1 / 60, sess)
    assert z3.state == "die" and chomper.chomp_timer > 0

    # 大喷菇：一次伤害范围内两只僵尸
    fumer = add_plant("fumer", 3, 4)
    za = add_zombie("basic", 3, fumer.x + 60)
    zb = add_zombie("basic", 3, fumer.x + 150)
    fumer.update(0.4, sess)
    fumer.update(1 / 60, sess)
    assert za.hp < 190 and zb.hp < 190, (za.hp, zb.hp)

    # 投手：抛射落地命中
    lobber = add_plant("lobber", 4, 4)
    zc = add_zombie("basic", 4, lobber.x + 210)
    lobber.update(0.4, sess)
    lobber.update(1 / 60, sess)
    assert sess.projectiles, "投手没有发射"
    for _ in range(240):
        for pr in list(sess.projectiles):
            pr.update(1 / 60, sess)
        sess.projectiles = [p for p in sess.projectiles if p.alive]
        if not sess.projectiles:
            break
    assert zc.hp < 190, f"抛射未命中 hp={zc.hp}"

    # 回旋镖：去程命中一次并飞回
    boomer = add_plant("boomer", 0, 3)
    zd = add_zombie("basic", 0, boomer.x + 120)
    boomer.update(0.4, sess)
    boomer.update(1 / 60, sess)
    assert sess.projectiles
    for _ in range(300):
        for pr in list(sess.projectiles):
            pr.update(1 / 60, sess)
        sess.projectiles = [p for p in sess.projectiles if p.alive]
        if not sess.projectiles:
            break
    assert zd.hp < 190, f"回旋镖未命中 hp={zd.hp}"

    # 减速：速度减半且计时衰减
    ze = add_zombie("basic", 2, 900.0)
    combat.apply_slow(ze, 3.0)
    x0 = ze.x
    ze.update(1.0, sess)
    assert abs((x0 - ze.x) - 0.185 * 100 * 0.5) < 0.1, x0 - ze.x
    assert 1.9 < ze.slow_timer < 2.1

    # 僵尸啃食植物
    wall = add_plant("wallnut", 2, 2)
    zf = add_zombie("basic", 2, wall.x + 40)
    zf.update(1.0, sess)
    assert zf.state == "eat" and wall.hp < wall.max_hp, (zf.state, wall.hp)


def main():
    pygame.init()
    print("== 引擎自检 ==")
    for name, fn in [
        ("Board 几何/占位", test_board),
        ("WaveDirector 波次", test_waves),
        ("combat 护甲/子弹/阳光", test_combat_rules),
        ("卡片/种植/铲子", test_card_and_shovel),
        ("180s 胜利模拟", test_win_simulation),
        ("180s 失败模拟", test_lose_simulation),
        ("暂停/横幅/绘制", test_pause_and_banner),
        ("特殊植物行为", test_special_plants),
    ]:
        step(name, fn)

    print()
    if FAILS:
        print(f"FAIL: {len(FAILS)} 项未通过 -> {', '.join(FAILS)}")
        return 1
    print("PASS: 引擎自检全部通过")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 1
    sys.exit(code)
