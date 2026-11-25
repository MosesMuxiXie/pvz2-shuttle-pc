# -*- coding: utf-8 -*-
"""C60 part 2: make artifact writers emit LF on Windows.

`Path.write_text()` translates "\\n" to "\\r\\n" on Windows, so artifacts written that way
got CRLF, and any `--check` that compares bytes then flip-flops depending on checkout
normalisation. rewards.py / spawn_offsets.py already use write_bytes; align the rest.
"""
import io
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

PATCHES = [
    ("tools/contentc/bosses.py", 'path.write_text(render(data), encoding="utf-8")',
     'path.write_bytes(render(data).encode("utf-8"))'),
    ("tools/contentc/bosses.py", 'path.write_text(render_report(data, rows, client_path), encoding="utf-8")',
     'path.write_bytes(render_report(data, rows, client_path).encode("utf-8"))'),
    ("tools/contentc/projectiles.py", 'path.write_text(render(table), encoding="utf-8")',
     'path.write_bytes(render(table).encode("utf-8"))'),
    ("tools/contentc/projectiles.py", 'path.write_text(render_report(table, obb_dir), encoding="utf-8")',
     'path.write_bytes(render_report(table, obb_dir).encode("utf-8"))'),
    ("tools/engine_smoke.py", 'args.out.write_text(text, encoding="utf-8")',
     'args.out.write_bytes(text.encode("utf-8"))'),
    ("tools/parity_report.py", 'args.out.write_text(text, encoding="utf-8")',
     'args.out.write_bytes(text.encode("utf-8"))'),
]

for rel, old, new in PATCHES:
    p = ROOT / rel
    t = io.open(p, encoding="utf-8").read()
    if new in t:
        print("skip (already)", rel, old[:32])
        continue
    assert old in t, (rel, old)
    io.open(p, "w", encoding="utf-8", newline="\n").write(t.replace(old, new))
    print("patched", rel, "|", old[:40])
