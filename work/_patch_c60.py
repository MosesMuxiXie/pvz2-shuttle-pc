# -*- coding: utf-8 -*-
"""C60: make original_gaps.py --check newline-insensitive (Windows checkout may give CRLF)."""
import io
import pathlib

P = pathlib.Path(__file__).resolve().parents[1] / "tools" / "contentc" / "original_gaps.py"
t = io.open(P, encoding="utf-8").read()

OLD = '            if path.read_bytes() != text.encode("utf-8"):\n'
NEW = (
    '            # C60: compare newline-insensitively. A Windows checkout may hand us CRLF\n'
    '            # while the renderer emits LF, which made --check fail on an otherwise clean tree.\n'
    '            if path.read_bytes().replace(b"\\r\\n", b"\\n") != text.encode("utf-8"):\n'
)

assert OLD in t, "anchor missing"
if NEW in t:
    print("already patched")
else:
    io.open(P, "w", encoding="utf-8", newline="\n").write(t.replace(OLD, NEW))
    print("patched", P)
