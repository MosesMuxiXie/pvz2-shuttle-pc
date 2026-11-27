import json, pathlib
d = json.loads(pathlib.Path("native/generated/engine_smoke.json").read_text(encoding="utf-8"))
print(list(d.keys()))
for s in d["scenarios"][:3]:
    print(s)
