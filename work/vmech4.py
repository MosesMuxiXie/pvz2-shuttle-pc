import json
import sys
from pathlib import Path

ROOT = Path(r"D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc")
sys.path.insert(0, str(ROOT / "tools" / "contentc"))
import mechanics as M  # noqa: E402

inv = M.build(M.DEFAULT_LEVELS, M.DEFAULT_OBB)
doc = json.loads(M.render_json(inv))
lvl = doc["levels"]
total = 0
for name in M.MECHANICS:
    blob = json.dumps({k: v[name] for k, v in lvl.items() if v[name] is not None}, ensure_ascii=False)
    print(f"{name:18s} {len(blob)/1e6:7.2f} MB  levels={sum(1 for v in lvl.values() if v[name] is not None)}")
    total += len(blob)
print(f"mechanics subtotal {total/1e6:.2f} MB")
sp = {}
for k, v in lvl.items():
    if v["spawners"]:
        for kind, items in v["spawners"].items():
            if items:
                sp[kind] = sp.get(kind, 0) + len(items)
print("spawner record counts:", sp)
# jittered 里 zombies 条目总数
n = 0
for v in lvl.values():
    for rec in (v["spawners"] or {}).get("jittered", []):
        n += len(rec.get("zombies") or [])
print("jittered zombie entries:", n)
