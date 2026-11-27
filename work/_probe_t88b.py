import io, json, collections
d = json.load(io.open(r"native/generated/level_mechanics.json", encoding="utf-8"))
lv = d["levels"]

print("=== events: key sets ===")
ev = [(lid, v["events"]) for lid, v in lv.items() if v.get("events")]
print("levels:", len(ev))
ks = collections.Counter()
for _, e in ev:
    ks[tuple(sorted(e.keys()))] += 1
for k, n in ks.most_common():
    print(n, k)
print("\nsample event bodies:")
for lid, e in ev[:4]:
    print(lid, json.dumps(e, ensure_ascii=False)[:400])

print("\n=== mutators: all 21 ===")
mu = [(lid, v["mutators"]) for lid, v in lv.items() if v.get("mutators")]
mods = collections.Counter(); mtypes = collections.Counter(); keys = collections.Counter()
for lid, m in mu:
    print("-", lid, json.dumps(m, ensure_ascii=False)[:300])
    for row in m:
        for k in row: keys[k]+=1
        for t in (row.get("tables") or []):
            mtypes[t.get("ModuleType")] += 1
            for name in (t.get("Modules") or []): mods[name]+=1
print("mutator row keys:", dict(keys))
print("module types:", dict(mtypes))
print("modules:", dict(mods.most_common(20)))
