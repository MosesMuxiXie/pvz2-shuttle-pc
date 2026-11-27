import io, json
d = json.load(io.open(r"native/generated/level_mechanics.json", encoding="utf-8"))
lv=d["levels"]
frost=[(lid,v["events"]["frost"]) for lid,v in lv.items() if v.get("events") and v["events"].get("frost")]
print("levels with frost rows:", len(frost))
for lid,f in frost[:6]: print(lid, json.dumps(f, ensure_ascii=False)[:300])
strengths=sorted({v["events"]["strength"] for v in lv.values() if v.get("events")})
print("strength values:", strengths)
