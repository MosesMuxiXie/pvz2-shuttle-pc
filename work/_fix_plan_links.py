# -*- coding: utf-8 -*-
"""Point the top-level plan at docs/PROGRESS.md and refresh its measured numbers."""
import io
import pathlib

P = pathlib.Path(__file__).resolve().parents[1] / "docs" / "superpowers" / "plans" / "2026-11-20-full-native-replica.md"
t = io.open(P, encoding="utf-8").read()

old_head = "### 1.1 阶段状态（2026-11-24 14:20 实测）"
new_head = (
    "### 1.1 阶段状态（2026-11-25 实测）\n\n"
    "> 活的剩余清单在 [`docs/PROGRESS.md`](../../PROGRESS.md)：按 P0/P1/P2 分了 20 条，带量化与门禁红线。\n"
    "> 本节只保留阶段级结论。当前读数：audit **27** / Python **469** / desktop **36**，静树严格模式 EXIT=0。"
)
assert old_head in t
t = t.replace(old_head, new_head)

old_q = "### 1.2 下一步队列（2026-11-24 21:15 重排）"
new_q = "### 1.2 下一步队列（2026-11-25 重排；细节见 `docs/PROGRESS.md` §2）"
assert old_q in t
t = t.replace(old_q, new_q)

old0 = "0. **460.9 收尾**（数据已对齐，剩消费端）：`suppressFlagZombie` 271 关进 content + 引擎抑制旗子波（t64/t65 进行中）；"
new0 = "0. **460.9 收尾**（数据已对齐）：`suppressFlagZombie` 271 关已进 content + 引擎抑制旗子波（t64/t65 完成）；"
assert old0 in t
t = t.replace(old0, new0)

old1 = "1. **S7 打包**（用户已定「打包留到最后」，但代码侧已无阻塞）：按 `2026-11-24-packaging.md` 做"
new1 = ("1. **玩法补齐优先**：关卡机制剩 342 关 → 砸罐子 47 → 小游戏 45（`PROGRESS.md` P0 #1–#3），这是「像不像原版」的最大缺口。\n"
        "2. **S7 打包**（用户已定「打包留到最后」，但代码侧已无阻塞）：按 `2026-11-24-packaging.md` 做")
assert old1 in t
t = t.replace(old1, new1)

io.open(P, "w", encoding="utf-8", newline="\n").write(t)
print("ok", len(t))
