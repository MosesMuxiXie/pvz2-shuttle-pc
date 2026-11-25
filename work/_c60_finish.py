# -*- coding: utf-8 -*-
"""C60 finish: worlds.py writer + pause.md normalisation."""
import io
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]

w = ROOT / "tools" / "contentc" / "worlds.py"
text = io.open(w, encoding="utf-8").read()
old = 'args.out.write_text(text, encoding="utf-8")'
new = 'args.out.write_bytes(text.encode("utf-8"))  # bytes: Windows must not turn LF into CRLF'
if new not in text:
    assert old in text, "worlds.py writer not found"
    io.open(w, "w", encoding="utf-8", newline="\n").write(text.replace(old, new))
    print("patched tools/contentc/worlds.py")
else:
    print("skip worlds.py (already)")

p = ROOT / "docs" / "reviews" / "2026-11-21-pause.md"
raw = p.read_bytes()
if b"\r\n" in raw:
    p.write_bytes(raw.replace(b"\r\n", b"\n"))
    print("normalised docs/reviews/2026-11-21-pause.md ->", len(raw), "->", len(p.read_bytes()), "bytes")
else:
    print("pause.md already LF")
