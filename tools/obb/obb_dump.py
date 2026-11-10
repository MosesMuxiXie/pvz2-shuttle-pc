# -*- coding: utf-8 -*-
"""Dump every RSG subgroup of a PvZ2 1BSR (RSB v4) OBB by index.

Name tables inside this SHUTTLE build are encoded, so we do not rely on
file names: each subgroup is written as <group>.section (data stream) and
<group>.image (image stream), both decompressed (zstd or zlib).
"""
import os
import struct
import sys
import time
import zlib

try:
    import zstandard as zstd
except Exception:
    zstd = None

OBB = sys.argv[1] if len(sys.argv) > 1 else r"D:\OneDrive\文档\pvz_shuttle\main.460.com.ea.game.pvz2_shu.obb"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"D:\OneDrive\文档\pvz_shuttle\work\obb_raw"
LIMIT = int(sys.argv[3]) if len(sys.argv) > 3 else 0

os.makedirs(OUT, exist_ok=True)


def uncompress(buf, want=0):
    if not buf:
        return b""
    if buf[:4] == b"\x28\xb5\x2f\xfd":
        if zstd is None:
            raise RuntimeError("zstd needed")
        d = zstd.ZstdDecompressor()
        try:
            return d.decompress(buf, max_output_size=want or (256 << 20))
        except Exception:
            with d.stream_reader(buf) as r:
                return r.read()
    return zlib.decompress(buf)


def main():
    f = open(OBB, "rb")
    raw = f.read(128)
    magic, version, unk0, header_size, file_list_size, file_list_offset = struct.unpack("<4sIIIII", raw[:24])
    assert magic == b"1bsr", magic
    # fixed offsets per 1BSR v4 layout (see README/notes)
    f.seek(0)
    head = f.read(112)
    vals = struct.unpack("<28I", head)
    subgroup_info_entries, subgroup_info_offset, subgroup_info_entry_size = vals[10], vals[11], vals[12]
    group_info_entries, group_info_offset, group_info_entry_size = vals[13], vals[14], vals[15]
    print("version", version, "header", header_size, "subgroups", subgroup_info_entries)
    print("group info", group_info_entries, group_info_offset, group_info_entry_size)

    f.seek(subgroup_info_offset)
    info = f.read(subgroup_info_entries * 204)
    groups = []
    for i in range(subgroup_info_entries):
        base = i * 204
        name = info[base:base + 128].rstrip(b"\x00").decode("utf-8", "replace")
        off, size = struct.unpack_from("<II", info, base + 128)
        groups.append((name, off, size))

    total = len(groups) if not LIMIT else min(LIMIT, len(groups))
    t0 = time.time()
    stats = {"groups": 0, "data": 0, "image": 0, "nulldata": 0, "err": 0}
    for idx in range(total):
        name, off, size = groups[idx]
        try:
            f.seek(off)
            hdr = f.read(96)
            if hdr[:4] != b"pgsr":
                continue
            (version2,) = struct.unpack_from("<I", hdr, 4)
            flags, hlen = struct.unpack_from("<II", hdr, 16)
            doff, csize, dsize = struct.unpack_from("<III", hdr, 24)
            imoff, icmp, idec = struct.unpack_from("<III", hdr, 40)
            info_size, info_off = struct.unpack_from("<II", hdr, 72)

            safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)[:120]
            gdir = os.path.join(OUT, "%04d_%s" % (idx, safe))
            os.makedirs(gdir, exist_ok=True)

            data = None
            if csize:
                f.seek(off + doff)
                buf = f.read(csize)
                data = uncompress(buf, dsize)
                open(os.path.join(gdir, "data.bin"), "wb").write(data)
                stats["data"] += 1
            elif flags & 2 and dsize == 0:
                stats["nulldata"] += 1

            if idec and icmp:
                f.seek(off + imoff)
                buf = f.read(icmp)
                img = uncompress(buf, idec)
                open(os.path.join(gdir, "image.bin"), "wb").write(img)
                stats["image"] += 1

            meta = {
                "index": idx, "name": name, "offset": off, "size": size,
                "version": version2, "flags": flags, "header_len": hlen,
                "data_offset": doff, "compressed_data_size": csize, "decompressed_data_size": dsize,
                "image_offset": imoff, "compressed_image_size": icmp, "decompressed_image_size": idec,
                "info_size": info_size, "info_offset": info_off,
            }
            open(os.path.join(gdir, "meta.txt"), "w", encoding="utf-8").write(repr(meta) + "\n")
            stats["groups"] += 1
        except Exception as e:
            stats["err"] += 1
            print("[error]", idx, name, type(e).__name__, e)
        if idx % 200 == 0:
            print(idx, name, "%.1fs" % (time.time() - t0), stats, flush=True)

    print("DONE", stats, "%.1fs" % (time.time() - t0))


if __name__ == "__main__":
    main()
