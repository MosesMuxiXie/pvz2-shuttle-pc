"""Dump chosen package files by pkg number, showing the mechanic object classes of interest."""
import json
import sys
from pathlib import Path

REPO = Path(r"D:\OneDrive\文档\pvz_shuttle\repo\pvz2-shuttle-pc")
PKG = Path(r"D:\OneDrive\文档\pvz_shuttle\work\obb_packages")
LEVELS = REPO / "content" / "levels"

WANT = [
    "ConveyorSeedBank", "ModifyConveyor", "InitialPlant", "InitialGridItem", "Gravestone",
    "ProtectThePlant", "TidalChange", "FrostWind", "DinoWave", "SpawnModernPortals",
    "SpiderRain", "SpawnZombiesFish", "StormZombieSpawner", "BeachStageEvent",
    "SpawnGravestones", "FromGridItem", "FromGround", "BoardGridMap", "LevelMutator",
    "WaveManagerProps", "WaveManagerModule",
]


def level_for(pkg_stem):
    for path in LEVELS.glob("*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if (doc.get("extra") or {}).get("package") == pkg_stem:
            return path.stem
    return "?"


def show(pkg_num):
    stem = "pkg_%04d" % int(pkg_num)
    doc = json.loads((PKG / (stem + "_LevelDefinition.json")).read_text(encoding="utf-8"))
    print("=" * 95)
    print("%s -> client level %s  (%d objects)" % (stem, level_for(stem), len(doc["objects"])))
    for o in doc["objects"]:
        cls = o.get("objclass") or ""
        if not any(w.lower() in cls.lower() for w in WANT):
            continue
        print("\n-- %s   aliases=%s" % (cls, o.get("aliases")))
        text = json.dumps(o.get("objdata") or {}, ensure_ascii=False, indent=1)
        print(text if len(text) < 1800 else text[:1800] + "\n   ...(truncated)")


if __name__ == "__main__":
    for arg in sys.argv[1:] or ["0327", "0621", "0360", "0541"]:
        show(arg)
