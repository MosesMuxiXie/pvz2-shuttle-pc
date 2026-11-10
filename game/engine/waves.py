"""波次导演：把 LevelDef.waves 展开成按时间到点的刷怪事件。

每个 Wave.delay 表示“距上一波（第一波则距关卡开始）的秒数”；
flag 波（大波）会把该波僵尸数量乘以 2~3（受 max_wave_zombies 限制）。

用法::

    director = WaveDirector(level_def)
    while ...:
        for ev in director.update(dt):
            spawn_zombie(ev.type, ev.row)

WaveDirector 不依赖 pygame，可单独测试。
"""
from __future__ import annotations

import random

from ..config import BOARD_ROWS


class SpawnEvent:
    """一条到点的刷怪事件。"""

    __slots__ = ("type", "row", "wave_index", "flag", "is_final")

    def __init__(self, type: str, row: int, wave_index: int = 0,
                 flag: bool = False, is_final: bool = False):
        self.type = str(type)
        self.row = int(row)
        self.wave_index = int(wave_index)
        self.flag = bool(flag)
        self.is_final = bool(is_final)

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<Spawn {self.type} row={self.row} wave={self.wave_index} flag={self.flag}>"


class WaveDirector:
    """根据 LevelDef 的 waves 生成刷怪事件。

    属性：
        total_waves       总波数
        current_wave      最近开始的波索引（0 基；-1 表示还没开始）
        wave_index        已开始的波数（1 基，UI 直接显示）
        progress          已开始波数 / 总波数（0~1）
        finished          所有波是否都已刷出
        spawned           已刷出的僵尸总数
        flag_waves_started 已开始的大波数
        final_wave_started 最后一波是否已开始
    """

    def __init__(self, level_def, rng: random.Random | None = None,
                 rows: int = BOARD_ROWS):
        self.level_def = level_def
        self.waves = list(getattr(level_def, "waves", []) or [])
        self.total_waves = len(self.waves)
        self.rows = max(1, int(rows))
        self.rng = rng if rng is not None else random.Random()
        self.max_wave_zombies = 16   # 单波上限，避免 flag 波爆炸
        self.flag_min, self.flag_max = 2, 3

        # 每波的绝对到点时间
        self.due_times: list[float] = []
        acc = 0.0
        for w in self.waves:
            try:
                delay = float(getattr(w, "delay", 18.0) or 0.0)
            except (TypeError, ValueError):
                delay = 18.0
            acc += max(0.0, delay)
            self.due_times.append(acc)

        self.clock = 0.0
        self.next_index = 0
        self.current_wave = -1
        self.progress = 0.0
        self.spawned = 0
        self.flag_waves_started = 0
        self.final_wave_started = False
        self.finished = self.total_waves == 0
        # 事件缓冲：同一帧内多波到点时一次返回
        self._pending: list[SpawnEvent] = []

    # ------------------------------------------------------------ 查询
    @property
    def wave_index(self) -> int:
        """已开始的波数（1 基，0 表示还没开始）。"""
        return self.next_index

    @property
    def all_spawned(self) -> bool:
        return self.finished

    def time_to_next(self) -> float | None:
        """距下一波的秒数；没有下一波返回 None。"""
        if self.next_index >= self.total_waves:
            return None
        return max(0.0, self.due_times[self.next_index] - self.clock)

    def peek_next_wave(self):
        if self.next_index >= self.total_waves:
            return None
        return self.waves[self.next_index]

    # ------------------------------------------------------------ 推进
    def update(self, dt: float) -> list[SpawnEvent]:
        """推进时间，返回本帧到点的刷怪事件列表（可能为空）。"""
        out: list[SpawnEvent] = []
        if self.finished and not self._pending:
            return out
        self.clock += max(0.0, float(dt))

        # 先把上一帧遗留的事件发完（极端情况下 dt 很大也不会丢）
        if self._pending:
            out.extend(self._pending)
            self._pending.clear()

        while self.next_index < self.total_waves:
            due = self.due_times[self.next_index]
            if self.clock + 1e-9 < due:
                break
            idx = self.next_index
            wave = self.waves[idx]
            self.next_index += 1
            self.current_wave = idx
            is_final = idx == self.total_waves - 1
            is_flag = bool(getattr(wave, "flag", False))
            if is_flag:
                self.flag_waves_started += 1
            if is_final:
                self.final_wave_started = True
            spawns = self._expand_wave(wave, idx, is_flag, is_final)
            self.spawned += len(spawns)
            out.extend(spawns)
            if self.next_index >= self.total_waves:
                self.finished = True
                break

        self.progress = (self.next_index / self.total_waves) if self.total_waves else 1.0
        return out

    # ------------------------------------------------------------ 内部
    def _expand_wave(self, wave, idx: int, is_flag: bool, is_final: bool) -> list[SpawnEvent]:
        base = list(getattr(wave, "zombies", []) or [])
        if not base:
            return []
        mult = int(self.rng.choice((self.flag_min, self.flag_max))) if is_flag else 1
        out: list[SpawnEvent] = []
        for _copy in range(mult):
            for spawn in base:
                for row in self._resolve_rows(spawn):
                    out.append(SpawnEvent(getattr(spawn, "type", "basic"), row,
                                          idx, is_flag, is_final))
                    if len(out) >= self.max_wave_zombies:
                        return out
        return out

    def _resolve_rows(self, spawn) -> list[int]:
        """解析 row / rows / 随机行，返回合法的行号列表。"""
        rows_attr = getattr(spawn, "rows", None)
        if rows_attr:
            out = [int(r) for r in rows_attr if 0 <= int(r) < self.rows]
            if out:
                return out
        row = getattr(spawn, "row", None)
        if row is not None:
            r = int(row)
            return [r if 0 <= r < self.rows else self.rng.randrange(self.rows)]
        return [self.rng.randrange(self.rows)]
