"""Probe 5: wave attribution, sentinels, nested item shapes, string-number anomalies."""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

PKG = Path(r"D:\OneDrive\文档\pvz_shuttle\work\obb_packages")
RTID_RE = re.compile(r"RTID\(([^@]+)@([^)]+)\)")

WAVE_ACTIONS = [
    "TidalChangeWaveActionProps", "FrostWindWaveActionProps", "DinoWaveActionProps",
    "SpawnModernPortalsWaveActionProps", "SpiderRainZombieSpawnerProps",
    "StormZombieSpawnerProps", "SpawnZombiesFishWaveActionProps",
    "BeachStageEventZombieSpawnerProps", "SpawnGravestonesWaveActionProps",
    "SpawnZombiesFromGridItemSpawnerProps", "SpawnZombiesFromGroundSpawnerProps",
    "ModifyConveyorWaveActionProps",
]
NUMERIC_STRING = re.compile(r"^-?\d+(\.\d+)?$")

files = sorted(PKG.glob("pkg_*_LevelDefinition.json"))
print("level packages:", len(files))

waves_shape = Counter()
alias_hit = Counter()
alias_miss = Counter()
miss_examples = defaultdict(list)
wave_refs = Counter()
sentinels = Counter()
str_num = Counter()
nested_keys = defaultdict(Counter)
mutator_classes = Counter()
gravestone_force = Counter()

for path in files:
    doc = json.loads(path.read_text(encoding="utf-8-sig"))
    objs = doc.get("objects") or []
    by_alias = {}
    waves = None
    for obj in objs:
        for a in obj.get("aliases") or []:
            by_alias[a] = obj
        if obj.get("objclass") == "WaveManagerProperties":
            waves = (obj.get("objdata") or {}).get("Waves")
        if (obj.get("objclass") or "").startswith("LevelMutator"):
            mutator_classes[obj["objclass"]] += 1
        if obj.get("objclass") == "GravestoneProperties":
            fsd = (obj.get("objdata") or {}).get("ForceSpawnData")
            if isinstance(fsd, list):
                for item in fsd:
                    if isinstance(item, dict):
                        for k in item:
                            gravestone_force[k] += 1

    # wave reference map: alias -> set of wave numbers
    ref = defaultdict(set)
    if waves is None:
        waves_shape["none"] += 1
    elif isinstance(waves, list):
        waves_shape["list"] += 1
        for i, entry in enumerate(waves):
            if isinstance(entry, list):
                waves_shape["entry=list"] += 1
                for item in entry:
                    m = RTID_RE.search(str(item))
                    if m:
                        ref[m.group(1)].add(i + 1)
            else:
                waves_shape["entry=" + type(entry).__name__] += 1
    else:
        waves_shape["type=" + type(waves).__name__] += 1

    for obj in objs:
        cls = obj.get("objclass") or ""
        if cls not in WAVE_ACTIONS:
            continue
        if not waves:
            continue
        aliases = obj.get("aliases") or []
        hit = [a for a in aliases if a in ref]
        if hit:
            alias_hit[cls] += 1
        else:
            alias_miss[cls] += 1
            if len(miss_examples[cls]) < 3:
                miss_examples[cls].append((path.name, aliases))

    # sentinels + numeric strings + nested item keys
    for obj in objs:
        od = obj.get("objdata")
        if not isinstance(od, dict):
            continue
        cls = obj.get("objclass") or ""
        for key, value in od.items():
            stack = [(key, value)]
            while stack:
                k, v = stack.pop()
                if isinstance(v, int) and v in (2147483647, -1):
                    sentinels[(cls, k, v)] += 1
                elif isinstance(v, str) and NUMERIC_STRING.match(v):
                    str_num[(cls, k)] += 1
                elif isinstance(v, dict):
                    stack.extend((k + "." + kk, vv) for kk, vv in v.items())
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            for kk, vv in item.items():
                                nested_keys[(cls, k)][kk] += 1
                            stack.extend((k + "[]." + kk, vv) for kk, vv in item.items())
                        elif isinstance(item, int) and item in (2147483647, -1):
                            sentinels[(cls, k + "[]", item)] += 1

print("\nWaves shape:", dict(waves_shape))
print("\nwave-action alias resolved via Waves:")
for cls in sorted(set(alias_hit) | set(alias_miss)):
    print("  %-40s hit=%-4d miss=%-4d  ex=%s" % (cls, alias_hit[cls], alias_miss[cls], miss_examples[cls][:1]))
print("\nsentinels:", dict(sentinels))
print("\nnumeric strings (cls,key)->count:", dict(list(str_num.items())[:20]), "total kinds:", len(str_num))
print("\nnested item keys:")
for (cls, key), counter in sorted(nested_keys.items()):
    print("  %-40s %-28s %s" % (cls, key, dict(counter.most_common(14))))
print("\ngravestone ForceSpawnData item keys:", dict(gravestone_force))
print("mutator classes in level files:", dict(mutator_classes))
