import io, json
d = json.load(io.open(r"native/generated/level_mechanics.json", encoding="utf-8"))
lv = d["levels"]
frost = []
for lid, v in lv.items():
    ev = v.get("events") or {}
    fr = ev.get("frost") or []
    if fr:
        waves = sorted({r.get("wave") for r in fr if isinstance(r.get("wave"), int)})
        frost.append((waves[0] if waves else None, lid, waves, len(fr)))
frost.sort()
print("lowest-wave frost levels:")
for w, lid, waves, n in frost[:6]: print(" ", lid, "min wave", w, "waves", waves[:6], "rows", n)
tide = []
for lid, v in lv.items():
    ev = v.get("events") or {}
    td = ev.get("tide") or []
    if td:
        waves = sorted({r.get("wave") for r in td if isinstance(r.get("wave"), int)})
        tide.append((waves[0] if waves else None, lid, waves))
tide.sort()
print("lowest-wave tide levels:")
for w, lid, waves in tide[:6]: print(" ", lid, "min wave", w, "waves", waves)
