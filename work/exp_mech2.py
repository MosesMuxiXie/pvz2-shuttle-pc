"""Dump object structure of a few LevelDefinition packages (truncated but shaped)."""
import json
from pathlib import Path

REPO = Path(r"D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc")
PKG = Path(r"D:\OneDrive\文档\pvz_shuttle\work\obb_packages")
LEVELS = REPO / "content" / "levels"


def shape(value, depth=0, max_items=3):
    if isinstance(value, dict):
        out = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= 12:
                out["..."] = "%d more keys" % (len(value) - 12)
                break
            out[k] = shape(v, depth + 1, max_items)
        return out
    if isinstance(value, list):
        if not value:
            return []
        return [shape(value[0], depth + 1, max_items), "...x%d" % len(value)]
    return value


def pkg_of(level_id):
    doc = json.loads((LEVELS / (level_id + ".json")).read_text(encoding="utf-8"))
    return doc["extra"]["package"]


def dump(level_id, want=None):
    pkg = pkg_of(level_id)
    doc = json.loads((PKG / (pkg + "_LevelDefinition.json")).read_text(encoding="utf-8"))
    print("=" * 90)
    print("level %s -> %s_LevelDefinition.json  objects=%d" % (level_id, pkg, len(doc["objects"])))
    for o in doc["objects"]:
        cls = o.get("objclass") or ""
        if want and not any(w.lower() in cls.lower() for w in want):
            continue
        print("\n-- objclass:", cls, "| aliases:", o.get("aliases"))
        print(json.dumps(shape(o.get("objdata") or {}), ensure_ascii=False, indent=1)[:2600])


if __name__ == "__main__":
    # beach_23 has fish spawner + seedbank + waves
    dump("beach_23")
