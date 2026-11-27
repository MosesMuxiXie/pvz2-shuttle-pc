import json, pathlib
base = json.loads(pathlib.Path("native/generated/engine_smoke.json").read_text(encoding="utf-8"))
new = json.loads(pathlib.Path("work/_smoke_vase.json").read_text(encoding="utf-8"))
b = {s["name"]: s for s in base["scenarios"]}
n = {s["name"]: s for s in new["scenarios"]}
diffs = [k for k in b if b[k].get("hash") != n.get(k, {}).get("hash")]
print("baseline", len(b), "new", len(n), "diffs", len(diffs))
for k in diffs:
    print(" name:", k)
    print("   hash ", b[k].get("hash"), "->", n[k].get("hash"))
    print("   tick ", b[k].get("tick"), "->", n[k].get("tick"))
    print("   status", b[k].get("status"), "->", n[k].get("status"))
print("extra", [k for k in n if k not in b])
print("vase levels in smoke:", [k for k in n if "vase" in k.lower() or k in ("beach_69","egypt_57","kongfu_83","carnival_91")])
