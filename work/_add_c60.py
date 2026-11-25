# -*- coding: utf-8 -*-
"""Register C60 (CRLF vs LF in byte-compared artifacts) and add it to PROGRESS.md."""
import io
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
C = ROOT / "docs" / "COMPLETENESS.md"
P = ROOT / "docs" / "PROGRESS.md"

c = io.open(C, encoding="utf-8").read()
row = (
    "| C60 | medium | 工具链确定性 | `original_gaps.py --check` 逐字节比对产物，而 Windows 上 `core.autocrlf=true` "
    "会把提交的 LF 在检出时变成 CRLF → 干净树上也会报 `docs/reviews/2026-11-24-original-gaps.md 内容过期` "
    "（本次门禁就红在这一步；`git diff` 却是空的，因为 git 在 diff 时又归一化了）。已修：比对前 `read_bytes().replace(b\"\\r\\n\", b\"\\n\")`；"
    "用 CRLF 副本做探针 `--check` 现在 exit 0。同类风险仍在 7 个 CRLF 产物上（`bosses_from_pack.json`、`boss_report.md`、`engine_smoke.json`、"
    "`projectiles_from_pack.json`、`projectile_report.md`、`world_diff.md`、`docs/reviews/2026-11-21-pause.md`），它们各自的 `--check` 目前不用逐字节比对。 |\n"
)
anchor = "\n## 4."
idx = c.find("\n## 4.")
assert idx != -1
if "| C60 |" not in c:
    c = c[:idx] + "\n" + row.rstrip("\n") + c[idx:]
    io.open(C, "w", encoding="utf-8", newline="\n").write(c)
    print("C60 added")

p = io.open(P, encoding="utf-8").read()
old = "| 18 | **确定性戳（C58）** | 2 张表 `generatedAt` + 1 张 `generated` | 每次重生成 churn | 小 |"
new = (old + "\n"
       "| 21 | **产物换行归一（C60）** | 7 个 CRLF 产物 | `original_gaps` 已改宽容比对；其余 7 个产物仍可能因检出 CRLF 而闪红 | 小 |")
if "C60" not in p:
    assert old in p, "PROGRESS anchor missing"
    p = p.replace(old, new)
    io.open(P, "w", encoding="utf-8", newline="\n").write(p)
    print("PROGRESS updated")
