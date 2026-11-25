import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(r"D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc")
sys.path.insert(0, str(ROOT / "tools" / "contentc"))
import mechanics  # noqa: E402

inv = mechanics.build(mechanics.DEFAULT_LEVELS, mechanics.DEFAULT_OBB)
doc = json.loads(mechanics.render_json(inv))
print("json bytes:", len(mechanics.render_json(inv).encode()))
print("top keys:", sorted(doc))
print("counts:", json.dumps(doc["counts"], ensure_ascii=False, indent=1))
print("unknowns:", len(doc["unknowns"]))
for row in doc["unknowns"]:
    print("  -", row["kind"], row["count"], "|", row["detail"][:110])
print()
print("sentinels top:")
for row in doc["sentinels"][:8]:
    print("  ", row)
print("coerced top:")
for row in doc["coerced"][:8]:
    print("  ", row)
print()
lvl = doc["levels"]
print("levels:", len(lvl))
for key in ("beach_23", "egypt_1"):
    if key in lvl:
        print("---", key, "---")
        print(json.dumps(lvl[key], ensure_ascii=False, indent=1)[:2600])
