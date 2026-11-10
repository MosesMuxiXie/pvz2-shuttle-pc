"""战斗计算：伤害、护甲、碰撞、子弹命中、僵尸啃食。

本模块只做纯逻辑，不依赖 entities 的类型（鸭子类型），避免循环导入。
entities / level 调用这里的函数，保证伤害规则只有一份实现。

约定：
- 僵尸护甲列表 ``armor`` 按“外层 -> 内层”排列，伤害先扣 armor[0]。
- ``pierce_armor=True`` 时忽略护甲直接扣血（窝瓜/小推车/爆炸等）。
- 僵尸进入 ``state == "die"`` 后不再参与碰撞与受伤，只播放死亡淡出。
"""
from __future__ import annotations

import math


# ---------------------------------------------------------------- 查询
def is_zombie_targetable(z) -> bool:
    """僵尸是否可被命中（活着且不在死亡动画中）。"""
    return bool(getattr(z, "alive", False)) and getattr(z, "state", "walk") != "die"


def zombies_in_row(level, row: int, x_min: float | None = None,
                   x_max: float | None = None,
                   include_dying: bool = False) -> list:
    """取某一行满足 x 范围的僵尸（默认排除死亡动画中的）。"""
    out = []
    for z in getattr(level, "zombies", []) or []:
        if getattr(z, "row", None) != row:
            continue
        if not getattr(z, "alive", False):
            continue
        if not include_dying and getattr(z, "state", "walk") == "die":
            continue
        x = float(getattr(z, "x", 0.0))
        if x_min is not None and x < x_min:
            continue
        if x_max is not None and x > x_max:
            continue
        out.append(z)
    return out


def has_zombie_in_row(level, row: int, x_min: float | None = None,
                      x_max: float | None = None) -> bool:
    return bool(zombies_in_row(level, row, x_min, x_max))


def nearest_zombie_in_row(level, row: int, x_min: float | None = None,
                          x_max: float | None = None):
    """该行最靠近左侧（x 最小）的僵尸；没有返回 None。"""
    zs = zombies_in_row(level, row, x_min, x_max)
    return min(zs, key=lambda z: float(z.x)) if zs else None


def find_eat_target(zombie, level):
    """找僵尸嘴前的可啃食植物（同行、距离在啃食窗口内），取最右（最近）的。"""
    best = None
    zx = float(getattr(zombie, "x", 0.0))
    for p in getattr(level, "plants", []) or []:
        if not getattr(p, "alive", False):
            continue
        if getattr(p, "row", None) != getattr(zombie, "row", None):
            continue
        if not getattr(p, "eatable", True):
            continue
        # 僵尸从右侧靠近；-26 允许轻微越过后仍在啃
        dz = zx - float(getattr(p, "x", 0.0))
        if -26.0 <= dz <= 64.0:
            if best is None or float(p.x) > float(best.x):
                best = p
    return best


# ---------------------------------------------------------------- 植物
def damage_plant(plant, amount: float, level=None) -> float:
    """扣植物血量；死亡时把 alive 置 False（由 LevelSession 清理）。"""
    if not getattr(plant, "alive", False) or amount <= 0:
        return 0.0
    plant.hp = float(getattr(plant, "hp", 0.0)) - float(amount)
    if plant.hp <= 0.0:
        plant.hp = 0.0
        plant.alive = False
        if level is not None:
            _call(level, "on_plant_killed", plant)
    else:
        plant.hit_flash = max(getattr(plant, "hit_flash", 0.0), 0.12)
    return float(amount)


def zombie_eat(zombie, plant, dt: float, level=None) -> bool:
    """僵尸啃食一帧；返回植物是否还活着。"""
    damage = float(getattr(zombie, "eat_dps", 100.0)) * max(0.0, float(dt))
    damage_plant(plant, damage, level)
    return bool(getattr(plant, "alive", False))


# ---------------------------------------------------------------- 僵尸
def damage_zombie(zombie, amount: float, level=None,
                  pierce_armor: bool = False) -> float:
    """对僵尸造成伤害，先扣护甲。返回本次实际扣除的总量（护甲+血量）。"""
    if not is_zombie_targetable(zombie) or amount <= 0:
        return 0.0
    vm = float(getattr(zombie, "vuln_mult", 1.0) or 1.0)
    remaining = float(amount) * max(1.0, vm)
    dealt = 0.0

    if not pierce_armor:
        armor = getattr(zombie, "armor", None) or []
        while remaining > 1e-9 and armor:
            tier = armor[0]
            tier_hp = float(tier.get("hp", 0.0))
            if tier_hp <= 1e-9:
                armor.pop(0)
                continue
            absorb = min(remaining, tier_hp)
            tier["hp"] = tier_hp - absorb
            remaining -= absorb
            dealt += absorb
            if tier["hp"] <= 1e-9:
                armor.pop(0)
                _call(level, "on_armor_broken", zombie, tier)
        if remaining <= 1e-9:
            if dealt > 0:
                zombie.hit_flash = max(getattr(zombie, "hit_flash", 0.0), 0.1)
            return dealt

    zombie.hp = float(getattr(zombie, "hp", 0.0)) - remaining
    dealt += remaining
    if zombie.hp <= 0.0:
        zombie.hp = 0.0
        kill_zombie(zombie, level)
    else:
        zombie.hit_flash = max(getattr(zombie, "hit_flash", 0.0), 0.12)
    return dealt


def kill_zombie(zombie, level=None) -> None:
    """让僵尸进入死亡动画（不直接移出列表，LevelSession 负责清理）。"""
    if not is_zombie_targetable(zombie):
        return
    zombie.hp = 0.0
    zombie.state = "die"
    zombie.death_t = 0.0
    zombie.eating = None
    setter = getattr(zombie, "set_anim", None)
    if callable(setter):
        try:
            setter("Die")
        except Exception:
            pass
    if not getattr(zombie, "_counted_dead", False):
        zombie._counted_dead = True
        _call(level, "on_zombie_killed", zombie)


def apply_slow(zombie, seconds: float) -> None:
    """减速：seconds 为持续时间（秒），期间速度减半。"""
    if seconds and seconds > 0:
        zombie.slow_timer = max(float(getattr(zombie, "slow_timer", 0.0)), float(seconds))


# ---------------------------------------------------------------- 子弹
def projectile_hits(projectile, level) -> list:
    """子弹与同行僵尸的碰撞检测（已命中的会被 hit_ids 过滤）。"""
    out = []
    hit_ids = getattr(projectile, "hit_ids", None)
    rect = projectile.rect
    for z in zombies_in_row(level, getattr(projectile, "row", -1)):
        if hit_ids is not None and id(z) in hit_ids:
            continue
        try:
            if rect.colliderect(z.rect):
                out.append(z)
        except Exception:
            continue
    return out


def splash_damage(level, x: float, y: float, radius: float, damage: float,
                  slow: float = 0.0, pierce_armor: bool = False,
                  exclude: set | None = None) -> list:
    """范围伤害（抛射落地、爆炸）。返回被命中的僵尸列表。"""
    radius = max(1.0, float(radius))
    hits = []
    for z in list(getattr(level, "zombies", []) or []):
        if not is_zombie_targetable(z):
            continue
        if exclude and id(z) in exclude:
            continue
        cx = float(getattr(z, "x", 0.0))
        cy = float(getattr(z, "ground_y", 0.0)) - 50.0
        if math.hypot(cx - x, cy - y) <= radius:
            damage_zombie(z, damage, level, pierce_armor=pierce_armor)
            if slow:
                apply_slow(z, slow)
            hits.append(z)
    return hits


# ---------------------------------------------------------------- 内部
def _call(obj, name: str, *args):
    """安全地调用 level 上的可选回调。"""
    if obj is None:
        return None
    fn = getattr(obj, name, None)
    if not callable(fn):
        return None
    try:
        return fn(*args)
    except Exception:
        return None
