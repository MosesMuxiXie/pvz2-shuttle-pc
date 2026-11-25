# -*- coding: utf-8 -*-
"""Guard against CRLF creeping back into generated artifacts and review docs.

C60: `Path.write_text()` translates "\\n" to "\\r\\n" on Windows, so several compilers
wrote CRLF while their `--check` compares bytes — the result was a gate that went red on a
clean checkout (`core.autocrlf=true` rewrites the working tree) and green after a
regeneration. Writers must use `write_bytes(...encode("utf-8"))`.

This test is the cheap end-to-end guard: whatever a compiler writes, it must be LF.
"""
import pathlib
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]


def crlf_files(*patterns):
    hits = []
    for pattern in patterns:
        for path in sorted(REPO.glob(pattern)):
            if path.is_file() and b"\r\n" in path.read_bytes():
                hits.append(str(path.relative_to(REPO)).replace("\\", "/"))
    return hits


class NewlineTests(unittest.TestCase):
    def test_generated_json_is_lf(self):
        hits = crlf_files("native/generated/*.json")
        self.assertEqual(
            hits, [],
            "generated JSON must be written with write_bytes(): write_text() emits CRLF on "
            "Windows and breaks the byte-for-byte --check steps: " + ", ".join(hits),
        )

    def test_generated_markdown_is_lf(self):
        hits = crlf_files("native/generated/*.md")
        self.assertEqual(
            hits, [],
            "generated markdown must be written with write_bytes(): " + ", ".join(hits),
        )

    def test_review_docs_are_lf(self):
        hits = crlf_files("docs/reviews/*.md")
        self.assertEqual(
            hits, [],
            "review docs are compared byte-for-byte by some --check steps; keep them LF: "
            + ", ".join(hits),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
