import io, json, collections
p = r"native/generated/level_mechanics.json"
d = json.load(io.open(p, encoding="utf-8"))
lv = d["levels"]
print("levels", len(lv), "counts", json.dumps(d["counts"], ensure_ascii=False)[:600])

WIRED = {"initialPlants","initialGridItems","conveyor","protectThePlant","spawners.gravestone","spawners.jittered",
         "spawners.grid","spawners.portal","spawners.storm","spawners.ground","spawners.dino","spawners.beach","spawners.fish"}

def unknowns(v):
    out=[]
    if v.get("events"): out.append("events")
    if v.get("mutators"): out.append("mutators")
    if v.get("boardGrid"): out.append("boardGrid")
    sp = v.get("spawners") or {}
    for k, val in sp.items():
        if not val: continue
        if k in ("gravestone","jittered"): continue
        if k == "spider": out.append("spawners.spider"); continue
        if k in ("grid","portal","storm","ground","dino","beach","fish"): continue
        out.append("spawners." + k)
    return out

cnt = collections.Counter()
levels_unknown = 0
for lid, v in lv.items():
    u = unknowns(v)
    if u: levels_unknown += 1
    for x in u: cnt[x] += 1
print("levels with any unknown:", levels_unknown)
print("by kind:", dict(cnt.most_common()))

# boardGrid shapes
bg = [(lid, v["boardGrid"]) for lid, v in lv.items() if v.get("boardGrid")]
print("\nboardGrid levels:", len(bg))
print("keys:", sorted({k for _, b in bg for k in b.keys()}))
for lid, b in bg[:3]:
    print(lid, json.dumps(b, ensure_ascii=False)[:600])
rows_hist = collections.Counter()
for lid, b in bg:
    rows = b.get("rows")
    rows_hist[(b.get("width"), b.get("height"), len(rows) if isinstance(rows,list) else None)] += 1
print("width/height/len(rows) histogram:", dict(rows_hist))
al = collections.Counter(b.get("alias") for _, b in bg)
print("aliases:", dict(al))

mu = [(lid, v["mutators"]) for lid, v in lv.items() if v.get("mutators")]
print("\nmutator levels:", len(mu))
print("sample:", json.dumps(mu[0][1], ensure_ascii=False)[:1200])
