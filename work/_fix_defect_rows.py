# -*- coding: utf-8 -*-
"""Refresh three stale defect rows in docs/COMPLETENESS.md."""
import io
import pathlib

P = pathlib.Path(__file__).resolve().parents[1] / "docs" / "COMPLETENESS.md"
t = io.open(P, encoding="utf-8").read()

REPL = {
    "| C5 | blocker | 内核 | `level.extra` 完全不解析（boss/vasebreaker/minecarts/night/special） | S7 |":
    "| C5 | 已修（原 blocker → 关闭） | 内核 | 记录已过期：`catalog.cpp` 早就在解析 `level.extra`，引擎现消费 boss / vasebreaker·rail·minecarts 标记 / `suppressFlagZombie` / 五类关卡机制（§2.19、§2.30、§2.32）。剩余的是「变体玩法本体」，另见 C27 | — |",
    "| C24 | blocker | UI | 无菜单/世界地图/选卡/图鉴/商店… | S6 |":
    "| C24 | 部分已修（原 blocker） | UI | 已有启动器、主菜单、世界地图、选关、结算、拖动连续种植；**未做**图鉴（Almanac 169）/ 花园（Garden 65）/ 设置 / 成就（Quest 69）/ 商店 UI（`--shop` 只有 CLI） | S6 余下部分 |",
    "| C25 | high | 存档 | 无星章/钥匙/奖励/解锁 | S6 |":
    "| C25 | 部分已修 | 存档 | `Progress` 已有星章（`stars`/`goals`）、金币、种子、购买记录、`lastLevel` continue 指针，原子写、损坏不覆盖；**未做**存档版本迁移策略；钥匙来源只有 `egypt_3` 通关一条，且世界门只花 1 把（C46） | S6 余下部分 |",
}

for old, new in REPL.items():
    assert old in t, old[:40]
    t = t.replace(old, new)

io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("ok", len(t))
