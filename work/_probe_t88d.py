import io, json, collections
d = json.load(io.open(r"native/generated/level_mechanics.json", encoding="utf-8"))
lv = d["levels"]
WIRED_SP = {"grid","portal","storm","ground","dino","beach","fish","gravestone","jittered"}

def kinds(v):
    out = []
    ev = v.get("events")
    if ev:
        if ev.get("tide"): out.append("events.tide")
        if ev.get("frost"): out.append("events.frost")
        if not ev.get("tide") and not ev.get("frost"): out.append("events")
    mu = v.get("mutators")
    if mu:
        has_cap = any("maxSunOverride" in row for row in mu)
        rest = [r for r in mu if "maxSunOverride" not in r]
        if rest: out.append("mutators")
    if v.get("boardGrid"): out.append("boardGrid")
    sp = v.get("spawners") or {}
    if sp.get("spider"): out.append("spawners.spider")
    for k, val in sp.items():
        if val and k not in WIRED_SP and k != "spider": out.append("spawners." + k)
    return out

base = collections.Counter(); lv_unknown = 0
after = collections.Counter(); lv_after = 0
for lid, v in lv.items():
    k = kinds(v)
    for x in k: base[x] += 1
    if k: lv_unknown += 1
    # 本轮只接 events.tide / events.frost / boardGrid / mutators.maxSun
    rest = [x for x in k if x not in ("events.tide","events.frost","boardGrid")]
    for x in rest: after[x] += 1
    if rest: lv_after += 1
print("before: levels with unknown =", lv_unknown, dict(base.most_common()))
print("after : levels with unknown =", lv_after, dict(after.most_common()))

tide_only = sum(1 for v in lv.values() if (v.get("events") or {}).get("tide"))
frost_only = sum(1 for v in lv.values() if (v.get("events") or {}).get("frost"))
both = sum(1 for v in lv.values() if (v.get("events") or {}).get("tide") and (v.get("events") or {}).get("frost"))
print("tide levels", tide_only, "frost levels", frost_only, "both", both)
caps = [(lid, [r["maxSunOverride"] for r in v["mutators"] if "maxSunOverride" in r][0]) for lid, v in lv.items() if v.get("mutators") and any("maxSunOverride" in r for r in v["mutators"])]
print("maxSun levels", len(caps), caps)
challenge_only = [lid for lid, v in lv.items() if v.get("mutators") and any("maxSunOverride" not in r for r in v["mutators"])]
print("challenge-wrapper levels", len(challenge_only))
