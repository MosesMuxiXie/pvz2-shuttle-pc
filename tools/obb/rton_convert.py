# -*- coding: utf-8 -*-
"""Convert every RTON data stream extracted from the OBB into JSON."""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.environ.get("PVZ2_PYVZ2_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "..", "work", "deps", "pyvz2-main", "OBBEdit")))
from pyvz2rton import RTONDecoder

ROOT = r"D:\OneDrive\文档\pvz_shuttle\work\obb_raw"
OUT = r"D:\OneDrive\文档\pvz_shuttle\work\obb_json"
os.makedirs(OUT, exist_ok=True)


def main():
    warnings = []

    def warn(x):
        warnings.append(str(x))

    dec = RTONDecoder(b",", b"\n", b": ", False, b"  ", False, False, False, warn)
    groups = sorted(os.listdir(ROOT))
    ok = fail = 0
    t0 = time.time()
    index = []
    for name in groups:
        p = os.path.join(ROOT, name, "data.bin")
        if not os.path.exists(p):
            continue
        with open(p, "rb") as f:
            head = f.read(4)
        if head != b"RTON":
            continue
        raw = open(p, "rb").read()
        src = io.BytesIO(raw[4:])
        src.name = name
        try:
            out = dec.parse_root_object(src)
            data = json.loads(out)
            qname = name.split("_", 1)[1] if "_" in name else name
            target = os.path.join(OUT, qname + ".json")
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            ok += 1
            entry = {"group": name, "file": target, "bytes": os.path.getsize(target)}
            if isinstance(data, dict):
                entry["keys"] = list(data)[:8]
                objs = data.get("objects")
                if isinstance(objs, list):
                    entry["objects"] = len(objs)
                    classes = {}
                    for o in objs:
                        if isinstance(o, dict):
                            c = o.get("objclass") or "?"
                            classes[c] = classes.get(c, 0) + 1
                    entry["classes"] = dict(sorted(classes.items(), key=lambda kv: -kv[1])[:8])
            index.append(entry)
            print("OK", name, entry["bytes"], "%.1fs" % (time.time() - t0), flush=True)
        except Exception as e:
            fail += 1
            print("[fail]", name, type(e).__name__, e, flush=True)
    with open(os.path.join(OUT, "_index.json"), "w", encoding="utf-8") as f:
        json.dump({"ok": ok, "fail": fail, "items": index, "warnings": len(warnings)}, f, ensure_ascii=False, indent=1)
    print("DONE ok", ok, "fail", fail, "warnings", len(warnings), "%.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
