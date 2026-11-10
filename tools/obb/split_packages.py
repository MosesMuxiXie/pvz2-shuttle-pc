# -*- coding: utf-8 -*-
"""Split 0684_PACKAGES (concatenated 4 KiB-aligned RTON blocks) into JSON."""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.environ.get("PVZ2_PYVZ2_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "..", "work", "deps", "pyvz2-main", "OBBEdit")))
from pyvz2rton import RTONDecoder

SRC = r"D:\OneDrive\文档\pvz_shuttle\work\obb_raw\0684_PACKAGES\data.bin"
OUT = r"D:\OneDrive\文档\pvz_shuttle\work\obb_packages"
os.makedirs(OUT, exist_ok=True)


def main():
    raw = open(SRC, "rb").read()
    n = len(raw)
    starts = []
    i = raw.find(b"RTON")
    while i != -1:
        if i % 4096 == 0:
            starts.append(i)
        i = raw.find(b"RTON", i + 1)
    starts.append(n)
    print("blocks", len(starts) - 1)

    warnings = []

    def warn(x):
        warnings.append(str(x))

    dec = RTONDecoder(b",", b"\n", b": ", False, b"  ", False, False, False, warn)
    index = []
    ok = fail = 0
    t0 = time.time()
    for k in range(len(starts) - 1):
        a, b = starts[k], starts[k + 1]
        chunk = raw[a:]
        # trim trailing zero padding
        end = len(chunk)
        while end > 0 and chunk[end - 1:end] == b"\x00":
            end -= 1
        # find next 4096 boundary if this block is padded
        blk = chunk[:b - a]
        # remove padding tail (4K aligned)
        src = io.BytesIO(blk[4:])
        src.name = "pkg_%04d" % k
        try:
            out = dec.parse_root_object(src)
            data = json.loads(out)
            objclass = None
            uid = None
            name = None
            if isinstance(data, dict):
                objs = data.get("objects")
                if isinstance(objs, list) and objs and isinstance(objs[0], dict):
                    objclass = objs[0].get("objclass")
                    uid = objs[0].get("uid")
                    objdata = objs[0].get("objdata") or {}
                    if isinstance(objdata, dict):
                        nm = objdata.get("Name")
                        if isinstance(nm, dict):
                            name = nm.get("en") or nm.get("zh")
                        elif isinstance(nm, str):
                            name = nm
            target = os.path.join(OUT, "pkg_%04d_%s.json" % (k, objclass or "unknown"))
            with open(target, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
            index.append({"k": k, "objclass": objclass, "uid": uid, "name": name,
                          "bytes": os.path.getsize(target), "warn": len(warnings)})
            ok += 1
        except Exception as e:
            fail += 1
            index.append({"k": k, "error": type(e).__name__ + ": " + str(e)})
        if k % 200 == 0:
            print(k, "%.1fs" % (time.time() - t0), "ok", ok, "fail", fail, flush=True)

    with open(os.path.join(OUT, "_index.json"), "w", encoding="utf-8") as f:
        json.dump({"ok": ok, "fail": fail, "blocks": len(starts) - 1, "items": index,
                   "warnings": len(warnings)}, f, ensure_ascii=False, indent=1)
    print("DONE ok", ok, "fail", fail, "%.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
