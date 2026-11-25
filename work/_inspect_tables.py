# -*- coding: utf-8 -*-
import hashlib
import json
import pathlib

for rel in ("native/generated/bosses_from_pack.json",
            "native/generated/projectiles_from_pack.json"):
    p = pathlib.Path(rel)
    raw = p.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    print(rel, "bytes", len(raw), "sha256", hashlib.sha256(raw).hexdigest()[:16],
          "keys", list(data.keys()))
    for key in ("counts", "sources", "source", "generated", "generatedAt", "obbDir"):
        if key in data:
            print("   ", key, "=", json.dumps(data[key], ensure_ascii=False)[:200])
