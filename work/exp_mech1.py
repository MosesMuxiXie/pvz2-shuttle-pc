"""Explore: client level JSON <-> package file identity, and LevelDefinition shape."""
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(r"D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc")
PKG = Path(r"D:\OneDrive\文档\pvz_shuttle\work\obb_packages")
LEVELS = REPO / "content" / "levels"

files = sorted(LEVELS.glob("*.json"))
print("client level files:", len(files))

pkg_of = {}
per_pkg = defaultdict(list)
missing = []
for path in files:
    doc = json.loads(path.read_text(encoding="utf-8"))
    extra = doc.get("extra") or {}
    pkg = extra.get("package")
    if not pkg:
        missing.append(path.name)
        continue
    pkg_of[path.stem] = pkg
    per_pkg[pkg].append(path.stem)

print("levels with extra.package:", len(pkg_of), "missing:", len(missing), missing[:5])
dup = {k: v for k, v in per_pkg.items() if len(v) > 1}
print("packages used by >1 level:", len(dup), list(dup.items())[:5])

names = {p.name for p in PKG.glob("*.json")}
print("package files on disk:", len(names))
notfound = [p for p in per_pkg if p + "_LevelDefinition.json" not in names]
print("packages whose LevelDefinition file is missing:", len(notfound), notfound[:5])

# LevelDefinition shape for one level
sample = "beach_23"
pkg = pkg_of[sample]
doc = json.loads((PKG / (pkg + "_LevelDefinition.json")).read_text(encoding="utf-8"))
print("\n=== pkg file:", pkg + "_LevelDefinition.json", "top keys:", list(doc)[:8])
objs = doc.get("objects") or []
print("objects:", len(objs), "objclass:", [o.get("objclass") for o in objs][:6])
for o in objs:
    cls = o.get("objclass") or ""
    if "LevelDefinition" in cls:
        od = o.get("objdata") or {}
        print("objclass:", cls)
        print("objdata keys:", sorted(od.keys()))
        break

# which objdata key carries the mechanic props?
counter = Counter()
for path in list(files)[:200]:
    p = pkg_of.get(path.stem)
    if not p:
        continue
    f = PKG / (p + "_LevelDefinition.json")
    if not f.exists():
        continue
    d = json.loads(f.read_text(encoding="utf-8"))
    for o in d.get("objects") or []:
        if "LevelDefinition" in (o.get("objclass") or ""):
            od = o.get("objdata") or {}
            for k, v in od.items():
                if isinstance(v, dict):
                    counter[k] += 1
            break
print("\nnested objdata keys (first 200 levels):", counter.most_common(30))
