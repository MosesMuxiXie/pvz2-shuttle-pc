import json
import sys
from pathlib import Path

ROOT = Path(r"D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc")
sys.path.insert(0, str(ROOT / "tools" / "contentc"))
import mechanics as M  # noqa: E402

# 直接复查 InitialPlantProperties 的 Level 哨兵，绕开编译器
obb = M.DEFAULT_OBB
total_placements = 0
level_minus1 = 0
level_present = 0
per_file = []
for path in sorted(obb.glob("pkg_*_LevelDefinition.json")):
    doc = M.load_package(path)
    if not doc:
        continue
    for obj in M.dicts(doc.get("objects")):
        if obj.get("objclass") != "InitialPlantProperties":
            continue
        data = obj.get("objdata") if isinstance(obj.get("objdata"), dict) else {}
        for raw in M.dicts(data.get("InitialPlantPlacements")):
            total_placements += 1
            if "Level" in raw:
                level_present += 1
                if raw["Level"] == -1:
                    level_minus1 += 1
                    per_file.append((path.name, raw.get("TypeName"), raw.get("GridX"), raw.get("GridY")))
print(f"InitialPlantPlacements total={total_placements} hasLevel={level_present} level==-1 => {level_minus1}")
for row in per_file[:6]:
    print("  ", row)

inv = M.build(M.DEFAULT_LEVELS, M.DEFAULT_OBB)
doc = json.loads(M.render_json(inv))
print()
print("coerced top:")
for row in doc["coercedFields"][:10]:
    print("  ", row)
lvl = doc["levels"]
for key in ("beach_23", "egypt_1"):
    if key in lvl:
        print("---", key, "---")
        text = json.dumps(lvl[key], ensure_ascii=False, indent=1)
        print(text[:3000])
