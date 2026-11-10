"""扩展玩法会话：砸罐子 / 生存无尽 / 僵尸博士。

三者都复用 LevelSession 的战斗、种植与渲染，只替换目标与刷怪逻辑。
"""
from __future__ import annotations

import copy
import random

import pygame

from ..config import BOARD_COLS, BOARD_ROWS, WIN_W
from ..data import LevelDef, Wave, ZombieSpawn
from .entities import Plant, Zombie
from .board import row_ground_y
from .level import LevelSession
from .waves import WaveDirector

VASE_COL_MIN, VASE_COL_MAX = 2, 7


class BossPhase(int):
    """Boss 阶段号；直接格式化时显示 “2/3”。"""

    def __new__(cls, value, total=3):
        obj = super().__new__(cls, int(value))
        obj.total = max(1, int(total))
        return obj

    def __format__(self, spec):
        return format(int(self), spec) if spec else f"{int(self)}/{self.total}"

    def __str__(self):
        return f"{int(self)}/{self.total}"


# ------------------------------------------------------------------ 工具
def _clone_zdef(zdef, hp=None, name=None, eat_dps=None):
    z = copy.copy(zdef)
    if hp is not None:
        z.hp = int(hp)
    if name:
        z.name_zh = name
    if eat_dps is not None:
        z.eat_dps = float(eat_dps)
    return z


def _world_deck(data, world_id, fallback=("sunflower", "peashooter", "wallnut")):
    try:
        levels = data.levels(world_id)
        if levels:
            deck = list(getattr(levels[0], "deck", []) or [])
            if deck:
                return deck
    except Exception:
        pass
    return list(fallback)


# ------------------------------------------------------------------ 砸罐子
class VasebreakerSession(LevelSession):
    """砸罐子：地图上摆满罐子，点破后可能出僵尸/阳光/养料，清场过关。"""

    def __init__(self, app, minigame, world_def, on_finish=None):
        mg = dict(minigame or {})
        self.minigame = mg
        world_id = str(mg.get("world", "frontyard"))
        deck = list(mg.get("deck") or []) or _world_deck(app.data, world_id)
        level = LevelDef(id=str(mg.get("id", "vase")), world=world_id, index=0,
                         title=str(mg.get("title_zh", "砸罐子")),
                         sun=int(mg.get("sun", 150) or 150), deck=deck[:8],
                         waves=[], flags=1, seed_bank=6,
                         extra={"sky_sun_interval": 99.0, "first_sun": 99.0})
        super().__init__(app, world_def, level, on_finish=on_finish)
        self.vases: list[dict] = []
        for v in mg.get("vases", []) or []:
            try:
                row = int(v[0]); col = int(v[1]); kind = str(v[2])
            except Exception:
                continue
            if not (0 <= row < BOARD_ROWS and 0 <= col < BOARD_COLS):
                continue
            payload = v[3] if len(v) > 3 else None
            self.vases.append({"row": row, "col": col, "kind": kind,
                               "payload": payload, "broken": False, "t": 0.0})
        self.status = "playing"
        self.hide_wave_text = True
        self.show_message("点击罐子打碎它：里面可能藏着僵尸或奖励！", 3.2)

    # ---------------------------------------------------------- 交互
    def handle_mouse_down(self, pos) -> bool:
        if self.status != "playing" or self.paused:
            return False
        for v in self.vases:
            if v["broken"]:
                continue
            rect = self._vase_rect(v)
            if rect.collidepoint(pos):
                self._break_vase(v)
                return True
        return super().handle_mouse_down(pos)

    def _vase_rect(self, v) -> pygame.Rect:
        x, _y = self.board.cell_center(v["row"], v["col"])
        ground = row_ground_y(v["row"])
        return pygame.Rect(int(x - 26), int(ground - 62), 52, 58)

    def _break_vase(self, v):
        v["broken"] = True
        self.shake = max(self.shake, 2.0)
        kind = v["kind"]
        if kind == "zombie":
            self._spawn_vase_zombie(str(v.get("payload") or "basic"), v["row"])
        elif kind == "sun":
            self.spawn_sun(self.board.cell_center(v["row"], v["col"])[0],
                           row_ground_y(v["row"]), None, 25, "drop")
        elif kind == "plantfood":
            self.plantfood = min(3, int(getattr(self, "plantfood", 0)) + 1)
            self.spawn_text(self.board.cell_center(v["row"], v["col"])[0],
                            row_ground_y(v["row"]) - 20,
                            "养料 +1", (140, 230, 255), 18)
        elif kind == "plant":
            pdef = (getattr(self.data, "plants", {}) or {}).get(str(v.get("payload") or ""))
            if pdef is not None and not any(p.row == v["row"] and p.col == v["col"]
                                            for p in self.plants):
                p = Plant(pdef, v["row"], v["col"], self.assets)
                self.plants.append(p)
                self.spawn_text(self.board.cell_center(v["row"], v["col"])[0],
                                row_ground_y(v["row"]) - 20,
                                f"{pdef.name_zh} +1", (150, 240, 150), 18)
        else:
            self.spawn_text(self.board.cell_center(v["row"], v["col"])[0],
                            row_ground_y(v["row"]) - 20, "空罐子", (230, 230, 210), 16)

    def _spawn_vase_zombie(self, zid, row):
        zdef = (getattr(self.data, "zombies", {}) or {}).get(zid)
        if zdef is None:
            zdef = next(iter((getattr(self.data, "zombies", {}) or {}).values()), None)
        if zdef is None:
            return
        x, _ = self.board.cell_center(row, 6)
        z = Zombie(zdef, row, float(x), self.assets,
                   armature=getattr(zdef, "armature", None))
        z.x = float(x)
        self.zombies.append(z)
        self.zombies_spawned += 1

    # ---------------------------------------------------------- 判定
    def _check_win(self):
        if self.status != "playing":
            return
        if any(not v["broken"] for v in self.vases):
            return
        if any(getattr(z, "alive", False) and getattr(z, "state", "") != "die"
               for z in self.zombies):
            return
        self._end(True)


# ------------------------------------------------------------------ 生存无尽
class SurvivalSession(LevelSession):
    """生存无尽：一波接一波，直到防线被突破；分数 = 击杀 + 波次。"""

    def __init__(self, app, world_def, on_finish=None, on_score=None):
        world_id = getattr(world_def, "id", "frontyard")
        deck = _world_deck(app.data, world_id)
        level = LevelDef(id=f"survival_{world_id}", world=world_id, index=0,
                         title="生存无尽", sun=250, deck=deck[:8], waves=[],
                         flags=1, seed_bank=6,
                         extra={"sky_sun_interval": 7.0, "first_sun": 4.0})
        super().__init__(app, world_def, level, on_finish=on_finish)
        self.on_score = on_score
        self.round = 0
        self.score = 0
        self.kills = 0
        self._start_round()

    def _start_round(self):
        self.round += 1
        waves = []
        base = min(2 + self.round, 8)
        count = min(3 + self.round * 2, 9)
        for i in range(10):
            zombies = []
            for j in range(min(base + i // 2, 10)):
                types = []
                for zid in (getattr(self.data, "zombies", {}) or {}):
                    if "gargantuar" in zid:
                        continue
                    types.append(zid)
                types.sort()
                zid = types[(i * 7 + j * 3 + self.round) % len(types)] if types else "basic"
                zombies.append(ZombieSpawn(type=zid, row=(i + j + self.round) % BOARD_ROWS))
            waves.append(Wave(delay=8.0 if i else 6.0,
                              flag=(i + 1) % 5 == 0,
                              zombies=zombies[:count]))
        self.level_def.waves = waves
        self.director = WaveDirector(self.level_def, self.rng, BOARD_ROWS)
        self.total_waves = self.director.total_waves
        self.wave_index = 0
        self._final_announced = False
        self._flag_announced = 0
        self.start_wave_banner(f"第 {self.round} 轮开始", 2.2)

    def on_zombie_killed(self, zombie):
        super().on_zombie_killed(zombie)
        self.kills += 1
        self.score += 10 + int(getattr(zombie, "hp_max", 0)) // 40

    def update(self, dt: float):
        super().update(dt)
        if self.status != "playing" or self.paused:
            return
        if not self.director.finished:
            return
        if any(getattr(z, "alive", False) and getattr(z, "state", "") != "die"
               for z in self.zombies):
            return
        self.score += 120 + self.round * 40
        if self.on_score:
            try:
                self.on_score(self.score)
            except Exception:
                pass
        self._start_round()


# ------------------------------------------------------------------ 僵尸博士
class BossSession(LevelSession):
    """僵尸博士：一只高血量 Boss + 随波小僵尸，击败 Boss 过关。"""

    def __init__(self, app, world_def, boss_def, on_finish=None):
        world_id = getattr(world_def, "id", "frontyard")
        boss = dict(boss_def or {})
        deck = list(boss.get("deck") or []) or _world_deck(app.data, world_id)
        level = LevelDef(id=f"boss_{world_id}", world=world_id, index=0,
                         title=str(boss.get("title", f"{world_id} 僵尸博士")),
                         sun=300, deck=deck[:9], waves=[], flags=1, seed_bank=9,
                         extra={"sky_sun_interval": 7.0, "first_sun": 3.0})
        super().__init__(app, world_def, level, on_finish=on_finish)
        self.boss_def = boss
        self.boss = None
        self.boss_hp_max = 1
        self._minion_timer = 8.0
        self.phase = 1
        self.phase_defs = self._normalize_phases(boss.get("phases"))
        self.boss_phase_total = len(self.phase_defs)
        self.boss_phase = BossPhase(1, self.boss_phase_total)
        self.boss_ratio = 1.0
        self._boss_base_speed = 1.0
        self._boss_base_eat = 100.0
        self._boss_ready = False
        self.show_message(f"{boss.get('name_zh', '僵尸博士')} 出现了！", 3.2)
        self._spawn_boss()
        self._apply_initial_phase()

    # ---------------------------------------------------------- 阶段配置
    def _normalize_phases(self, raw):
        """兼容两种字段命名：hp_ratio/speed_mult... 与 at/speed/summon/text。"""
        defaults = [
            {"hp_ratio": 1.0, "speed_mult": 1.0, "eat_mult": 1.0,
             "minions": [], "count": 0, "message": ""},
            {"hp_ratio": 0.66, "speed_mult": 1.15, "eat_mult": 1.20,
             "minions": [], "count": 2, "message": ""},
            {"hp_ratio": 0.33, "speed_mult": 1.30, "eat_mult": 1.40,
             "minions": [], "count": 4, "message": ""},
        ]
        items = []
        source = list(raw or [])
        for index in range(3):
            base = dict(defaults[index])
            src = source[index] if index < len(source) else None
            if isinstance(src, dict):
                base["hp_ratio"] = self._num(src.get("hp_ratio", src.get("at")),
                                             base["hp_ratio"])
                base["speed_mult"] = self._num(src.get("speed_mult", src.get("speed")),
                                               base["speed_mult"])
                base["eat_mult"] = self._num(src.get("eat_mult"), base["eat_mult"])
                minions = src.get("minions")
                if isinstance(minions, list):
                    base["minions"] = [str(x) for x in minions if str(x)]
                count = src.get("count", src.get("summon"))
                try:
                    base["count"] = max(0, int(count))
                except (TypeError, ValueError):
                    pass
                base["message"] = str(src.get("message") or src.get("text") or "")
            items.append(base)
        items[0]["hp_ratio"] = 1.0
        for index in range(1, len(items)):
            items[index]["hp_ratio"] = min(
                items[index]["hp_ratio"], items[index - 1]["hp_ratio"] - 0.01)
        return items

    @staticmethod
    def _num(value, default):
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _phase_minions(self, phase):
        minions = list(phase.get("minions") or [])
        if minions:
            return minions
        return list((self.boss_def or {}).get("minions") or [])

    def _apply_initial_phase(self):
        if self.boss is None:
            return
        self._boss_base_speed = float(getattr(self.boss, "speed", 1.0) or 1.0)
        self._boss_base_eat = float(getattr(self.boss, "eat_dps", 100.0) or 100.0)
        phase = self.phase_defs[0]
        self.boss.speed = self._boss_base_speed * self._num(phase.get("speed_mult"), 1.0)
        self.boss.eat_dps = self._boss_base_eat * self._num(phase.get("eat_mult"), 1.0)

    def _enter_phase(self, index):
        """切换到 index+1 阶段：提升移速/啃咬，召唤该阶段小僵尸波次并提示。"""
        index = max(0, min(int(index), len(self.phase_defs) - 1))
        phase = self.phase_defs[index]
        self.phase = index + 1
        self.boss_phase = BossPhase(self.phase, self.boss_phase_total)
        if self.boss is not None:
            self.boss.speed = self._boss_base_speed * self._num(
                phase.get("speed_mult"), 1.0)
            self.boss.eat_dps = self._boss_base_eat * self._num(
                phase.get("eat_mult"), 1.0)
        wave = self._phase_minions(phase)
        count = int(phase.get("count") or 0)
        for offset in range(count):
            self._spawn_minion(wave, offset)
        message = str(phase.get("message") or "")
        if message:
            self.show_message(message, 2.6)
        try:
            self.shake = max(float(getattr(self, "shake", 0.0)), 4.0)
        except (TypeError, ValueError):
            pass

    def _spawn_boss(self):
        zombies = getattr(self.data, "zombies", {}) or {}
        base = zombies.get("gargantuar") or next(iter(zombies.values()), None)
        if base is None:
            return
        hp = int(self.boss_def.get("hp", 9000))
        zdef = _clone_zdef(base, hp=hp, name=str(self.boss_def.get("name_zh", "僵尸博士")))
        row = int(self.boss_def.get("row", 2)) % BOARD_ROWS
        z = Zombie(zdef, row, float(WIN_W + 40), self.assets,
                   armature=getattr(base, "armature", None))
        z.boss = True
        z.scale = getattr(z, "scale", 0.6) * 1.35
        self.boss = z
        self.boss_hp_max = int(getattr(z, "hp_max", hp) or hp)
        self.zombies.append(z)
        self.zombies_spawned += 1

    def update(self, dt: float):
        super().update(dt)
        if self.status != "playing" or self.paused:
            return
        if self.boss is not None and getattr(self.boss, "alive", False):
            self.boss_ratio = max(0.0, float(getattr(self.boss, "hp", 0)) / max(1, self.boss_hp_max))
            self._update_boss_phase()
        self._minion_timer -= dt
        if self._minion_timer <= 0:
            self._minion_timer = max(5.0, 12.0 - self.time * 0.02)
            self._spawn_minion()

    def _update_boss_phase(self):
        """按 66%/33% 血量切换三阶段：提速、啃咬加成、召唤增援、提示。"""
        while (self.phase < len(self.phase_defs)
               and self.boss_ratio <= self._num(
                   self.phase_defs[self.phase].get("hp_ratio"), 0.0)):
            self._enter_phase(self.phase)
            self.spawn_burst(getattr(self.boss, "x", 1100),
                             getattr(self.boss, "y", 300), (255, 120, 90), 18)

    def _spawn_minion(self, minions=None, seed=None):
        minions = list(minions or (self.boss_def or {}).get("minions") or [])
        if not minions:
            zombies = getattr(self.data, "zombies", {}) or {}
            minions = [z for z in zombies if "gargantuar" not in z][:1]
        if not minions:
            return
        index = int(self.time) + int(seed or 0)
        zid = minions[index % len(minions)]
        zdef = (getattr(self.data, "zombies", {}) or {}).get(zid)
        if zdef is None:
            return
        row = self.rng.randrange(BOARD_ROWS)
        z = Zombie(zdef, row, float(WIN_W + 40 + self.rng.uniform(0, 60)),
                   self.assets, armature=getattr(zdef, "armature", None))
        self.zombies.append(z)
        self.zombies_spawned += 1

    def _check_win(self):
        if self.status != "playing":
            return
        boss_dead = self.boss is not None and (
            not getattr(self.boss, "alive", False) or getattr(self.boss, "state", "") == "die")
        if not boss_dead:
            return
        if any(getattr(z, "alive", False) and getattr(z, "state", "") != "die"
               for z in self.zombies):
            return
        self._end(True)

    def _check_lose(self):
        # Boss 与普通僵尸都按小推车规则判负
        super()._check_lose()

    # ---------------------------------------------------------- 绘制
    def draw(self, surf):
        super().draw(surf)
        try:
            self._draw_phase_track(surf)
        except Exception:
            pass

    def _draw_phase_track(self, surf):
        """在 Boss 血条下方画分段刻度（boss.py 血条本身不可改）。"""
        if getattr(self, "status", "") != "playing" or self.boss is None:
            return
        total = len(self.phase_defs or [])
        if total <= 0:
            return
        x, y, w, h = 406, 142, 470, 7
        gap = 4
        seg = max(8, (w - gap * (total - 1)) // total)
        for index in range(total):
            rect = pygame.Rect(x + index * (seg + gap), y, seg, h)
            if index < self.phase:
                color = (247, 201, 72) if index == self.phase - 1 else (196, 150, 62)
            else:
                color = (76, 64, 48)
            pygame.draw.rect(surf, color, rect, border_radius=3)
        current = pygame.Rect(x + (self.phase - 1) * (seg + gap), y - 1, seg, h + 2)
        pygame.draw.rect(surf, (255, 236, 180), current, 1, border_radius=3)
