"""Read-only inventory of every objclass in the original OBB tables.

Purpose: answer "which game systems does the original have that our client has
no counterpart for" with data instead of memory. We count objclass names across
all pkg_*.json and bucket them by feature keyword.

Usage:
    python work/probe_objclass_inventory.py            # summary + buckets
    python work/probe_objclass_inventory.py --list 60  # also list top classes
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from contentc import s5scan  # noqa: E402

OBB = s5scan.DEFAULT_OBB

# keyword -> what we already do with it (None = we have nothing)
BUCKETS = {
    "almanac": "图鉴（未做）",
    "quest": "任务（未做）",
    "daily": "每日（未做）",
    "arena": "竞技场（未做）",
    "league": "联赛（未做）",
    "pinata": "彩罐（未做）",
    "garden": "花园（未做）",
    "boost": "强化（未做）",
    "powerup": "道具（未做）",
    "achievement": "成就（未做）",
    "tutorial": "教程（未做）",
    "hint": "提示（未做）",
    "store": "商店（已做，仅 585 件）",
    "shop": "商店（已做，仅 585 件）",
    "costume": "装扮（数据有，未做界面）",
    "reward": "奖励（数据待查）",
    "coin": "货币",
    "gem": "货币",
    "mint": "货币",
    "plantfood": "养料（已做）",
    "armor": "护甲（已做）",
    "projectile": "弹道（已做）",
    "fusion": "融合（已做）",
    "boss": "Boss（已做）",
    "level": "关卡（已做）",
    "world": "世界（已做）",
    "zombie": "僵尸（已做）",
    "plant": "植物（已做）",
    "wave": "波次（已做）",
    "rail": "铁轨（数据有，运行时无）",
    "vase": "砸罐子（数据有，运行时无）",
    "mower": "割草机（已做）",
    "save": "存档（已做）",
    "player": "玩家档（未做）",
    "profile": "玩家档（未做）",
    "music": "音频（已做）",
    "sound": "音频（已做）",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", type=int, default=0)
    args = ap.parse_args()

    files = s5scan.package_paths(OBB)
    classes = Counter()
    per_file = defaultdict(set)
    for path in files:
        pkg = s5scan.load_package(path)
        if not pkg:
            continue
        objs = pkg.get("objects") or []
        if isinstance(objs, dict):
            objs = list(objs.values())
        for obj in objs:
            cls = obj.get("objclass") or ""
            if not cls:
                continue
            classes[cls] += 1
            per_file[cls].add(path.name)

    print("packages scanned:", len(files))
    print("distinct objclasses:", len(classes))
    print("total objects:", sum(classes.values()))

    print("\n== buckets the original has ==")
    rows = []
    for key, note in BUCKETS.items():
        hits = [(c, n) for c, n in classes.items() if key in c.lower()]
        if not hits:
            continue
        total = sum(n for _, n in hits)
        top = sorted(hits, key=lambda kv: -kv[1])[:3]
        rows.append((total, key, note, len(hits), top))
    for total, key, note, nhit, top in sorted(rows, reverse=True):
        print("%-12s objects=%-6d classes=%-3d  %-28s e.g. %s"
              % (key, total, nhit, note, ", ".join("%s(%d)" % (c, n) for c, n in top)))

    if args.list:
        print("\n== top %d classes ===" % args.list)
        for cls, n in classes.most_common(args.list):
            print("%-6d %-52s files=%d" % (n, cls, len(per_file[cls])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
