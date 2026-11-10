"""PvZ2 同人重制版游戏引擎（无 UI 依赖，可 headless 跑）。

对外入口::

    from game.engine import LevelSession, Board

    session = LevelSession(app, world_def, level_def, on_finish=cb)
    session.handle_event(event)
    session.update(dt)
    session.draw(surface)

实体类、波次导演与战斗规则分别在 entities / waves / combat 中，
UI 层只依赖本包导出的符号。
"""
from .board import Board
from .combat import (apply_slow, damage_plant, damage_zombie,
                     find_eat_target, has_zombie_in_row, kill_zombie,
                     nearest_zombie_in_row, splash_damage, zombie_eat,
                     zombies_in_row)
from .entities import (FloatingText, LawnMower, Particle, Plant, Projectile,
                       Sun, Zombie)
from .level import LOSE_X, LevelSession
from .waves import SpawnEvent, WaveDirector

__all__ = [
    "Board",
    "LevelSession",
    "LOSE_X",
    "Plant", "Zombie", "Projectile", "Sun", "LawnMower",
    "FloatingText", "Particle",
    "WaveDirector", "SpawnEvent",
    "apply_slow", "damage_plant", "damage_zombie", "find_eat_target",
    "has_zombie_in_row", "kill_zombie", "nearest_zombie_in_row",
    "splash_damage", "zombie_eat", "zombies_in_row",
]
