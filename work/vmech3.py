import json
import sys
from pathlib import Path

ROOT = Path(r"D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc")
sys.path.insert(0, str(ROOT / "tools" / "contentc"))
import mechanics as M  # noqa: E402

inv = M.build(M.DEFAULT_LEVELS, M.DEFAULT_OBB)
doc = json.loads(M.render_json(inv))
lvl = doc["levels"]
empty = [k for k, v in lvl.items() if all(v[m] is None for m in M.MECHANICS)]
print(f"levels with all mechanics null: {len(empty)} / {len(lvl)}")
print("samples:", empty[:14])
print()
doc2 = M.load_package(M.DEFAULT_OBB / "pkg_0568_LevelDefinition.json")
print("pkg_0568 objclasses:", [o.get("objclass") for o in M.dicts(doc2.get("objects"))])
print()
# declared-only 与"有模块但无 props"的差集
for name, keys in (("conveyor", ("ConveyorSeedBankProperties",)),):
    pass
print("withConveyorSeedBank:", sum(1 for v in lvl.values() if v["conveyor"] and v["conveyor"].get("slots")))
print("conveyor-only-changes:", sum(1 for v in lvl.values() if v["conveyor"] and not v["conveyor"].get("slots") and v["conveyor"].get("changes")))
print("gridItem placements:", sum(1 for v in lvl.values() if v["initialGridItems"] and v["initialGridItems"].get("placements")))
print()
print("size of json:", len(M.render_json(inv).encode()))
