"""For each mechanic objclass: first example objdata + key coverage across all level packages."""
import json
from collections import Counter, defaultdict
from pathlib import Path

PKG = Path(r"D:\OneDrive\文档\pvz_shuttle\work\obb_packages")

CLASSES = [
    "ConveyorSeedBankProperties", "ModifyConveyorWaveActionProps",
    "InitialPlantProperties", "InitialGridItemProperties", "GravestoneProperties",
    "ProtectThePlantChallengeProperties",
    "TidalChangeWaveActionProps", "FrostWindWaveActionProps",
    "SpawnZombiesFromGridItemSpawnerProps", "SpawnZombiesFromGroundSpawnerProps",
    "SpiderRainZombieSpawnerProps", "StormZombieSpawnerProps",
    "SpawnZombiesFishWaveActionProps", "SpawnModernPortalsWaveActionProps",
    "DinoWaveActionProps", "BeachStageEventZombieSpawnerProps",
    "SpawnGravestonesWaveActionProps", "BoardGridMapProps",
]
MUTATOR_PREFIX = "LevelMutator"

examples = {}
key_counts = defaultdict(Counter)
obj_counts = Counter()
alias_counts = Counter()

for path in sorted(PKG.glob("pkg_*_LevelDefinition.json")):
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    for obj in doc.get("objects") or []:
        cls = obj.get("objclass") or ""
        base = cls if cls in CLASSES else (cls if cls.startswith(MUTATOR_PREFIX) else None)
        if not base:
            continue
        obj_counts[base] += 1
        od = obj.get("objdata")
        if isinstance(od, dict):
            for k in od:
                key_counts[base][k] += 1
        if isinstance(obj.get("aliases"), list):
            for a in obj["aliases"]:
                alias_counts[base] += 1
        if base not in examples:
            examples[base] = (path.name, obj.get("aliases"), od)

print("%-40s %6s %8s" % ("objclass", "objects", "withAlias"))
for cls in sorted(obj_counts):
    print("%-40s %6d %8d" % (cls, obj_counts[cls], alias_counts[cls]))

print("\n=== keys + first example ===")
for cls in sorted(examples):
    name, aliases, od = examples[cls]
    print("\n-- %s  (%s) aliases=%s" % (cls, name, aliases))
    print("   keys:", dict(key_counts[cls].most_common()))
    print("   example:", json.dumps(od, ensure_ascii=False)[:1200])
