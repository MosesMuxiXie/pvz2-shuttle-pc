# -*- coding: utf-8 -*-
import json
import pathlib

for rel in ("native/generated/rewards_from_pack.json",
            "native/generated/spawn_offsets.json",
            "native/generated/world_gates.json",
            "native/generated/engine_smoke.json"):
    data = json.loads(pathlib.Path(rel).read_text(encoding="utf-8"))
    print("{0:<42} generated={1!r} generatedAt={2!r}".format(
        rel, data.get("generated"), data.get("generatedAt")))
