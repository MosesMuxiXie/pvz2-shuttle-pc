"""Tests for the unicorn based rsbpatch decoding oracle.

Run with::

    python -m unittest tools.tests.test_emulate_rsb -v

The tests drive ``libczProject_official.so`` (the shipping ARM64 library that
parses ``*.rsbpatch`` files) inside unicorn and compare the decoder output with
the MD5 recorded in the patch container itself.  When the local artifacts are
missing the whole module is skipped, because the library, the patch and the
460.1 OBB are working-directory dumps rather than repository content.
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools import emulate_rsb as rsb  # noqa: E402

PATCH = rsb.WORK / "versions" / "_incoming" / "460.1_460.2.rsbpatch"
NEXT_PATCH = rsb.WORK / "versions" / "_incoming" / "460.2_460.9.rsbpatch"
SO = rsb.DEFAULT_SO
OBB = rsb.DEFAULT_SOURCE

SOURCE_HEAD = 0x48C000
HEAD_MD5 = "37ac0818b9aba97146cff6b156f6ec8e"
ORACLE_MD5 = "5f938695079f4a2812e0770ac261e066"
ORACLE_BYTES = 4767744  # 0x48C000

# Window trace of the 163 byte info stream (start, consumed, produced).
WINDOW_TRACE = [
    (5, 19, 0x100000),
    (24, 27, 0x100000),
    (51, 27, 0x100000),
    (78, 48, 0x100000),
    (126, 37, 0x8C000),
]

_EMU: "rsb.Emulator | None" = None
_DECODED: "dict | None" = None


def setUpModule() -> None:  # noqa: N802 - unittest naming
    for path in (SO, PATCH, OBB):
        if not path.exists():
            raise unittest.SkipTest(f"missing local artifact: {path}")


def emu() -> "rsb.Emulator":
    global _EMU
    if _EMU is None:
        _EMU = rsb.Emulator(SO)
        _EMU.load()
    return _EMU


def decoded() -> dict:
    """Decode the info stream once and share it between the assertions."""
    global _DECODED
    if _DECODED is None:
        patch = rsb.read_container(PATCH)
        head = rsb.read_source_head(OBB, SOURCE_HEAD)
        status, blob, records = emu().trace_stream(patch.info, head)
        _DECODED = {
            "patch": patch,
            "head": head,
            "status": status,
            "blob": blob,
            "records": records,
        }
    return _DECODED


def parse_window(raw: bytes, start: int = 0) -> dict:
    """Parse one window record header (layout established by emulation)."""
    cursor = start

    def varint() -> int:
        nonlocal cursor
        value = 0
        while True:
            byte = raw[cursor]
            cursor += 1
            value = (value << 7) | (byte & 0x7F)
            if not byte & 0x80:
                return value

    kind = raw[cursor]
    cursor += 1
    window = {"kind": kind, "src_seg_len": varint(), "src_seg_pos": varint()}
    delta_len = varint()
    window["delta_len"] = delta_len
    payload_start = cursor
    window["target_len"] = varint()
    window["indicator"] = raw[cursor]
    cursor += 1
    window["data_len"] = varint()
    window["inst_len"] = varint()
    window["addr_len"] = varint()
    window["payload_bounds"] = (payload_start, payload_start + delta_len)
    window["inst"] = raw[cursor:cursor + window["inst_len"]]
    return window


class ContainerTest(unittest.TestCase):
    def test_header_fields(self) -> None:
        patch = rsb.read_container(PATCH)
        self.assertEqual(patch.raw[:4], b"PBSR")
        self.assertEqual(int.from_bytes(patch.raw[4:8], "little"), 1)
        self.assertEqual(int.from_bytes(patch.raw[8:12], "little"), 2)
        self.assertEqual(patch.info_length, 163)
        self.assertEqual(patch.build, 0x10D6)
        self.assertEqual(patch.source_md5.hex(), HEAD_MD5)
        self.assertEqual(patch.source_size, 0x7CE80000)

    def test_second_patch_uses_the_first_one_as_source(self) -> None:
        patch = rsb.read_container(NEXT_PATCH)
        self.assertEqual(patch.info_length, 427125)
        self.assertEqual(patch.build, 0x10D9)
        # 460.2_460.9 promises the head this very tool reproduces from 460.1.
        self.assertEqual(patch.source_md5.hex(), ORACLE_MD5)

    def test_stream_offsets(self) -> None:
        patch = rsb.read_container(PATCH)
        self.assertEqual(rsb.find_streams(patch.raw), [0x30, 0x1978B])

    def test_source_size_field_equals_the_obb_length(self) -> None:
        patch = rsb.read_container(PATCH)
        # The u64 at 0x0C is the exact length of the source file on disk, which
        # is what makes "decode a prefix and compare the MD5" meaningful.
        self.assertEqual(patch.source_size, OBB.stat().st_size)

    def test_source_head_matches_the_container_digest(self) -> None:
        head = rsb.read_source_head(OBB, SOURCE_HEAD)
        self.assertEqual(len(head), SOURCE_HEAD)
        self.assertEqual(hashlib.md5(head).hexdigest(), HEAD_MD5)


class DecodeTest(unittest.TestCase):
    def test_info_stream_reproduces_the_recorded_md5(self) -> None:
        result = decoded()
        self.assertEqual(result["status"], 1)
        self.assertEqual(len(result["blob"]), ORACLE_BYTES)
        self.assertEqual(hashlib.md5(result["blob"]).hexdigest(), ORACLE_MD5)

    def test_decoded_head_is_an_rsb_container(self) -> None:
        blob = decoded()["blob"]
        self.assertEqual(blob[:4], b"1bsr")
        self.assertEqual(int.from_bytes(blob[4:8], "little"), 4)

    def test_window_trace_matches_the_stream_length(self) -> None:
        result = decoded()
        records = result["records"]
        self.assertEqual([(r.start, r.consumed, r.produced) for r in records],
                         WINDOW_TRACE)
        consumed = sum(r.consumed for r in records)
        produced = sum(r.produced for r in records)
        self.assertEqual(consumed + 5, result["patch"].info_length)
        self.assertEqual(produced, len(result["blob"]))

    def test_first_window_record_layout(self) -> None:
        result = decoded()
        window = parse_window(result["patch"].info, result["records"][0].start)
        self.assertEqual(window["kind"], 0x01)  # COPY from the source segment
        self.assertEqual(window["src_seg_len"], SOURCE_HEAD)
        self.assertEqual(window["src_seg_pos"], 0)
        self.assertEqual(window["delta_len"], 12)
        self.assertEqual(window["target_len"], 0x100000)
        self.assertEqual(window["indicator"], 0)
        self.assertEqual(window["data_len"], 0)
        self.assertEqual(window["inst_len"], 5)
        self.assertEqual(window["addr_len"], 0)
        self.assertEqual(window["inst"].hex(), "73c0800000")

    def test_header_only_stream_is_a_valid_no_op(self) -> None:
        status, blob = rsb.decode_stream(emu(), b"\xd6\xc3\xc4\x53\x00", b"\x00" * 64)
        self.assertEqual(status, 1)
        self.assertEqual(blob, b"")

    def test_bad_magic_is_rejected(self) -> None:
        status, blob = rsb.decode_stream(emu(), b"\xd6\xc3\xc5\x53\x00", b"\x00" * 64)
        self.assertEqual(status & 1, 0)
        self.assertEqual(blob, b"")

    def test_decode_is_deterministic(self) -> None:
        patch = decoded()["patch"]
        head = rsb.read_source_head(OBB, SOURCE_HEAD)
        status, blob = rsb.decode_stream(emu(), patch.info, head)
        self.assertEqual(status, 1)
        self.assertEqual(hashlib.md5(blob).hexdigest(), ORACLE_MD5)


class OpcodeTableTest(unittest.TestCase):
    def test_runtime_tables_are_filled(self) -> None:
        # The tables live in .bss and are filled by a global constructor; the
        # first decode triggers it, so make sure the emulator has run.
        decoded()
        emulator = emu()
        table_a = emulator._mem(rsb.TABLE_A, 256 * 6)
        table_b = emulator._mem(rsb.TABLE_B, 256 * 3)
        rows_a = [table_a[i * 6:(i + 1) * 6] for i in range(256)]
        rows_b = [table_b[i * 3:(i + 1) * 3] for i in range(256)]
        self.assertEqual(sum(1 for row in rows_a if any(row)), 93)
        self.assertEqual(sum(1 for row in rows_b if any(row)), 62)
        self.assertEqual(len(set(rows_a)), 38)
        self.assertEqual(len(set(rows_b)), 20)
        self.assertEqual(rows_a[0x04].hex(), "010000000000")
        self.assertEqual(rows_a[0x08].hex(), "010000000100")
        self.assertEqual(rows_b[0x04].hex(), "010000")
        self.assertEqual(rows_b[0x0D].hex(), "000100")


if __name__ == "__main__":
    unittest.main(verbosity=2)
