"""Emulate the rsbpatch decoder inside libczProject.so with unicorn.

The official library ships the only known implementation of the `rsbpatch`
dialect (a VCDIFF variant with custom opcode tables).  This module maps the
ARM64 shared object into unicorn, resolves its imports to Python hooks and
calls the decoder entry points directly, so the semantics can be observed
instead of guessed:

    python tools/emulate_rsb.py info --patch work/versions/_incoming/460.1_460.2.rsbpatch \
        --source main.460.com.ea.game.pvz2_shu.obb

The tool only reads the `.so` and the patch; it never writes to them.

Entry points (found through `.eh_frame_hdr`, because the Ghidra dump lists
interior addresses):

    WINDOW_ENTRY = 0x1C0FC8   single window / record decode
    STREAM_ENTRY = 0x1C011C   whole delta stream ("VCDIFF" magic check + loop)
    INFO_ENTRY   = 0x2C2B14   RSB container ("1bsr") info parser
    APPLY_ENTRY  = 0x2C3F9C   top level patcher

Layout of a `.rsbpatch` container (measured on both patches):

    0x00  "PBSR"
    0x04  u32  format version (1)
    0x08  u32  section count (2)
    0x0C  u64  source size
    0x14  u32  info stream length
    0x18  16B  md5 of the source head region
    0x28  u32  build number of the target (0x10D6 / 0x10D9)
    0x2C  u32  1
    0x30  ..   the info delta stream (starts with D6 C3 C4)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_PROT_ALL
    from unicorn.arm64_const import (
        UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2, UC_ARM64_REG_X3,
        UC_ARM64_REG_X4, UC_ARM64_REG_X5, UC_ARM64_REG_X6, UC_ARM64_REG_X7,
        UC_ARM64_REG_X29, UC_ARM64_REG_X30, UC_ARM64_REG_SP, UC_ARM64_REG_PC,
        UC_ARM64_REG_LR,
    )
except ImportError:  # pragma: no cover - unicorn is an optional dependency
    raise SystemExit("unicorn is required: python -m pip install unicorn")

from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection

REPO = Path(__file__).resolve().parents[1]
WORK = REPO.parent.parent / "work"
DEFAULT_SO = WORK / "versions" / "_incoming" / "libczProject_official.so"
# The patches chain 460.1 -> 460.2 -> 460.9, so the *source* OBB must be 460.1. Since
# 2026-11-24 the workspace root `main.460….obb` is the upgraded 460.9 file (its MD5 is
# 2963d078…), which no longer matches the patch headers; pointing here at the archived
# 460.1 keeps the oracle honest instead of silently re-deriving against the wrong input.
DEFAULT_SOURCE = WORK / "versions" / "460.1.obb"

# Entry points, see module docstring.
WINDOW_ENTRY = 0x1C0FC8
STREAM_ENTRY = 0x1C011C
INFO_ENTRY = 0x1C2B40
APPLY_ENTRY = 0x1C469C

# Segment / scratch addresses inside the emulated address space.
STACK_BASE = 0x70000000
STACK_SIZE = 0x200000
HEAP_BASE = 0x30000000
HEAP_SIZE = 0x10000000
TRAMP_BASE = 0x20000000
TRAMP_STRIDE = 0x10
TRAMP_SIZE = 0x20000
RETURN_SENTINEL = 0x1FFFF000
SCRATCH_BASE = 0x80000000
TABLE_A = 0x5143E8
TABLE_B = 0x5143F4

PAGE = 0x1000

# x86 host -> the four patch streams.  Sizes taken from the container header.
PATCH_MAGIC = b"PBSR"


def align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) // alignment * alignment


@dataclass
class PatchContainer:
    raw: bytes
    source_size: int
    info_length: int
    source_md5: bytes
    build: int
    info: bytes

    @property
    def info_offset(self) -> int:
        return 0x30

    @property
    def info_hex(self) -> str:
        return self.info.hex()


@dataclass
class HookCall:
    name: str
    args: tuple[int, ...]
    result: int


@dataclass
class Emulator:
    """Minimal ELF64/AArch64 loader plus the hooks the decoder needs."""

    so_path: Path
    so_bytes: bytes = b""
    uc: Uc | None = None
    base: int = 0
    heap_next: int = HEAP_BASE
    tramp_next: int = TRAMP_BASE
    hooks: dict[int, str] = field(default_factory=dict)
    calls: list[HookCall] = field(default_factory=list)
    trace: bool = False
    _blocked: set[str] = field(default_factory=set)
    scratch_next: int = SCRATCH_BASE

    # ---------------------------------------------------------------- loading
    def load(self) -> None:
        self.so_bytes = self.so_path.read_bytes()
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        uc = self.uc

        spans: list[tuple[int, int]] = []
        uc.mem_map(TRAMP_BASE, TRAMP_SIZE, UC_PROT_ALL)
        with open(self.so_path, "rb") as fh:
            elf = ELFFile(fh)
            segments = [seg for seg in elf.iter_segments() if seg["p_type"] == "PT_LOAD"]
            for seg in segments:
                start = seg["p_vaddr"] & ~(PAGE - 1)
                end = align_up(seg["p_vaddr"] + seg["p_memsz"], PAGE)
                spans.append((start, end))
            for start, end in spans:
                uc.mem_map(start, end - start, UC_PROT_ALL)
            for seg in segments:
                data = seg.data()
                if data:
                    uc.mem_write(seg["p_vaddr"], data)
            self._apply_relocations(elf)
        uc.mem_map(STACK_BASE, STACK_SIZE, UC_PROT_ALL)
        uc.mem_map(HEAP_BASE, HEAP_SIZE, UC_PROT_ALL)
        self.heap_next = HEAP_BASE
        self.tramp_next = TRAMP_BASE

        # Return sentinel page + a fake thread pointer block (canary at +0x28).
        uc.mem_map(RETURN_SENTINEL & ~(PAGE - 1), PAGE, UC_PROT_ALL)
        tls = align_up(HEAP_BASE + HEAP_SIZE, PAGE) - PAGE
        # keep TLS inside the heap mapping: reserve the last page of the heap
        self.tls = tls
        uc.mem_write(tls + 0x28, b"\x5a" * 8)
        self.heap_limit = tls
        try:
            from unicorn.arm64_const import UC_ARM64_REG_TPIDR_EL0
            uc.reg_write(UC_ARM64_REG_TPIDR_EL0, tls)
        except Exception:  # pragma: no cover - depends on unicorn build
            pass

        uc.hook_add(UC_HOOK_CODE, self._on_code, begin=TRAMP_BASE, end=TRAMP_BASE + TRAMP_SIZE,
                    user_data=None)
        uc.hook_add(UC_HOOK_CODE, self._on_return, begin=RETURN_SENTINEL - PAGE,
                    end=RETURN_SENTINEL + PAGE, user_data=None)

    def _apply_relocations(self, elf: ELFFile) -> None:
        assert self.uc is not None
        for section in elf.iter_sections():
            if not isinstance(section, RelocationSection):
                continue
            symtab = elf.get_section(section["sh_link"])
            target = elf.get_section(section["sh_info"]) if section["sh_info"] else None
            for rel in section.iter_relocations():
                rtype = rel["r_info_type"]
                offset = rel["r_offset"]
                if rtype == 1027:  # R_AARCH64_RELATIVE
                    value = rel["r_addend"] + self.base
                    self.uc.mem_write(offset, struct.pack("<Q", value))
                elif rtype in (1025, 1026):  # GLOB_DAT / JUMP_SLOT
                    sym = symtab.get_symbol(rel["r_info_sym"])
                    name = sym.name
                    addr = self._make_trampoline(name)
                    self.uc.mem_write(offset, struct.pack("<Q", addr))
                elif rtype in (1024, 1029):  # ABS64 / ABS32
                    sym = symtab.get_symbol(rel["r_info_sym"])
                    if sym.name:
                        addr = self._make_trampoline(sym.name)
                        self.uc.mem_write(offset, struct.pack("<Q", addr))
                elif rtype in (1030, 1031):  # TLS DTPMOD / DTPREL
                    continue
                else:
                    continue

    def _make_trampoline(self, name: str) -> int:
        assert self.uc is not None
        addr = self.tramp_next
        self.tramp_next += TRAMP_STRIDE
        self.hooks[addr] = name
        # `ret` so that a direct branch into the trampoline also returns.
        self.uc.mem_write(addr, struct.pack("<I", 0xD65F03C0))
        return addr

    # ------------------------------------------------------------------ hooks
    def _on_code(self, uc: Uc, address: int, size: int, _user) -> None:
        name = self.hooks.get(address)
        if name is None:
            return
        args = tuple(uc.reg_read(reg) for reg in (
            UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
            UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5,
        ))
        result = self._dispatch(name, args)
        self.calls.append(HookCall(name, args, result))
        if self.trace:
            print(f"    hook {name}{args} -> {result}", file=sys.stderr)
        uc.reg_write(UC_ARM64_REG_X0, result & 0xFFFFFFFFFFFFFFFF)
        lr = uc.reg_read(UC_ARM64_REG_LR)
        uc.reg_write(UC_ARM64_REG_PC, lr)

    def _on_return(self, uc: Uc, address: int, size: int, _user) -> None:
        uc.emu_stop()

    # ------------------------------------------------------------- primitives
    def _mem(self, addr: int, size: int) -> bytes:
        assert self.uc is not None
        return bytes(self.uc.mem_read(addr, size)) if size else b""

    def _write(self, addr: int, data: bytes) -> None:
        assert self.uc is not None
        if data:
            self.uc.mem_write(addr, bytes(data))

    def _read_u64(self, addr: int) -> int:
        return struct.unpack("<Q", self._mem(addr, 8))[0]

    def _write_u64(self, addr: int, value: int) -> None:
        self._write(addr, struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF))

    def alloc(self, size: int) -> int:
        size = align_up(max(size, 1), 16)
        addr = self.heap_next
        if addr + size > self.heap_limit:
            raise MemoryError(f"heap exhausted allocating {size} bytes")
        self.heap_next += size
        return addr

    def read_cstring(self, addr: int, limit: int = 4096) -> str:
        data = b""
        while len(data) < limit:
            chunk = self._mem(addr + len(data), 64)
            if b"\x00" in chunk:
                data += chunk[: chunk.index(b"\x00")]
                break
            data += chunk
        return data.decode("utf-8", "replace")

    # ---------------------------------------------------------------- imports
    def _dispatch(self, name: str, args: tuple[int, ...]) -> int:
        if name in ("memcpy", "memmove", "__memcpy_chk", "bcopy"):
            src, dst, n = args[1], args[0], args[2]
            self._write(dst, self._mem(src, n))
            return dst
        if name in ("memset", "__memset_chk"):
            dst, value, n = args[0], args[1] & 0xFF, args[2]
            self._write(dst, bytes([value]) * n)
            return dst
        if name == "memcmp":
            a, b, n = args[0], args[1], args[2]
            return 0 if self._mem(a, n) == self._mem(b, n) else 1
        if name == "strlen":
            return len(self.read_cstring(args[0]))
        if name in ("_Znwm", "_Znam"):
            return self.alloc(args[0])
        if name in ("_ZdlPv", "_ZdaPv", "free"):
            return 0
        if name == "calloc":
            n, size = args[0], args[1]
            addr = self.alloc(n * size)
            self._write(addr, bytes(n * size))
            return addr
        if name == "malloc":
            return self.alloc(args[0])
        if name == "realloc":
            old, size = args[0], args[1]
            new = self.alloc(size)
            if old:
                self._write(new, self._mem(old, size))
            return new
        if name in ("__stack_chk_fail", "abort", "__cxa_pure_virtual"):
            raise RuntimeError(f"target aborted via {name}")
        if name == "__cxa_guard_acquire":
            return 1
        if name == "__cxa_guard_release":
            return 0
        if name in ("__cxa_atexit", "__cxa_finalize"):
            return 0
        if name.startswith("_ZNSt6__ndk1") or name.startswith("_ZNKSt6__ndk1"):
            return self._string_op(name, args)
        return 0

    # libc++ string layout is only used by the error path; record logical
    # strings and answer with the destination pointer.
    def _string_op(self, name: str, args: tuple[int, ...]) -> int:
        if "basic_string" in name and args:
            return args[0]
        return 0

    # ------------------------------------------------------------------- call
    def call(self, entry: int, args: list[int], timeout: int = 60_000_000) -> int:
        assert self.uc is not None
        uc = self.uc
        sp = STACK_BASE + STACK_SIZE - 0x1000
        uc.mem_write(sp, bytes(0x1000))
        uc.reg_write(UC_ARM64_REG_SP, sp)
        uc.reg_write(UC_ARM64_REG_LR, RETURN_SENTINEL)
        uc.reg_write(UC_ARM64_REG_X29, 0)
        regs = (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
                UC_ARM64_REG_X3, UC_ARM64_REG_X4, UC_ARM64_REG_X5,
                UC_ARM64_REG_X6, UC_ARM64_REG_X7)
        for reg, value in zip(regs, args + [0] * (len(regs) - len(args))):
            uc.reg_write(reg, value)
        uc.emu_start(entry, RETURN_SENTINEL, timeout=timeout, count=200_000_000)
        return uc.reg_read(UC_ARM64_REG_X0)

    # --------------------------------------------------------------- tracing
    def trace_stream(self, delta: bytes, source: bytes,
                     trace: bool = False) -> tuple[int, bytes, list[WindowRecord]]:
        """Decode a delta stream and record every window the driver decodes.

        The driver calls the window decoder at ``0x1C02BC`` (and ``0x1C0308``
        for the "allow header" retry).  Hooking right before/after those calls
        exposes the cursor and the per-window output vector without having to
        re-implement the window record layout.
        """
        assert self.uc is not None
        uc = self.uc
        emu = self
        records: list[WindowRecord] = []
        state: dict[str, int] = {}

        def before(uc_: Uc, address: int, size: int, _user) -> None:
            # Argument order at the call site: x4 = &cursor, x5 = end,
            # x6 = &out_vector (see the disassembly of FUN_002c011c).
            state["cursor"] = uc_.reg_read(UC_ARM64_REG_X4)
            state["out"] = uc_.reg_read(UC_ARM64_REG_X6)
            state["start"] = emu._read_u64(state["cursor"]) - state["delta_base"]

        def after(uc_: Uc, address: int, size: int, _user) -> None:
            status = uc_.reg_read(UC_ARM64_REG_X0)
            if not status & 1:
                return
            cursor = state.get("cursor", 0)
            out = state.get("out", 0)
            if not cursor or not out:
                return
            end = emu._read_u64(cursor) - state["delta_base"]
            begin_ptr = emu._read_u64(out)
            end_ptr = emu._read_u64(out + 8)
            data = emu._mem(begin_ptr, end_ptr - begin_ptr) if end_ptr > begin_ptr else b""
            records.append(WindowRecord(len(records), state["start"], end - state["start"],
                                        len(data), data))

        src_addr = emu.map_bytes(source)
        delta_addr = emu.map_bytes(delta)
        state["delta_base"] = delta_addr
        packages = _new_vector(emu)
        err = emu.alloc(32)
        emu._write(err, bytes(32))
        emu.trace = trace
        handles = [
            uc.hook_add(UC_HOOK_CODE, before, begin=0x1C02BC, end=0x1C02BC, user_data=None),
            uc.hook_add(UC_HOOK_CODE, after, begin=0x1C02C0, end=0x1C02C0, user_data=None),
            uc.hook_add(UC_HOOK_CODE, before, begin=0x1C0308, end=0x1C0308, user_data=None),
            uc.hook_add(UC_HOOK_CODE, after, begin=0x1C030C, end=0x1C030C, user_data=None),
        ]
        try:
            status = emu.call(STREAM_ENTRY, [src_addr, len(source), delta_addr, len(delta),
                                             packages, 0, err])
        finally:
            for handle in handles:
                uc.hook_del(handle)
        blob = emu.read_byte_vector(packages) if status & 1 else b""
        return status, blob, records

    # ---------------------------------------------------------- convenience
    def map_bytes(self, data: bytes, addr: int | None = None) -> int:
        """Map ``data`` into a fresh scratch window and return its address."""
        assert self.uc is not None
        size = align_up(max(len(data), 1), PAGE)
        if addr is None:
            addr = self.scratch_next
            self.scratch_next = addr + size
        self.uc.mem_map(addr, size, UC_PROT_ALL)
        self.uc.mem_write(addr, bytes(data))
        return addr

    def read_byte_vector(self, vec_addr: int) -> bytes:
        """Read a libc++ ``std::vector<uint8_t>`` laid out as {begin, end, cap}."""
        begin = self._read_u64(vec_addr)
        end = self._read_u64(vec_addr + 8)
        cap = self._read_u64(vec_addr + 16)
        if not begin and not end:
            return b""
        if end < begin or end - begin > 0x40000000 or cap < end:
            raise RuntimeError(
                f"implausible vector at 0x{vec_addr:x}: begin=0x{begin:x} "
                f"end=0x{end:x} cap=0x{cap:x}")
        return self._mem(begin, end - begin)


@dataclass
class WindowRecord:
    index: int
    start: int          # offset of the first byte of this record inside the delta
    consumed: int       # bytes the decoder advanced the cursor by
    produced: int       # bytes written to the output vector
    data: bytes = b""

    @property
    def md5(self) -> str:
        return hashlib.md5(self.data).hexdigest()

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "start": self.start,
            "consumed": self.consumed,
            "produced": self.produced,
            "md5": self.md5,
            "head": self.data[:32].hex(),
        }


def read_container(path: Path) -> PatchContainer:
    raw = path.read_bytes()
    if raw[:4] != PATCH_MAGIC:
        raise SystemExit(f"{path} does not start with PBSR")
    source_size, info_length = struct.unpack_from("<QI", raw, 12)
    source_md5 = raw[24:40]
    build = struct.unpack_from("<I", raw, 40)[0]
    return PatchContainer(
        raw=raw,
        source_size=source_size,
        info_length=info_length,
        source_md5=source_md5,
        build=build,
        info=raw[0x30: 0x30 + info_length],
    )


def read_source_head(path: Path, length: int) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(length)


def _map_pair(emu: Emulator, source: bytes, delta: bytes) -> tuple[int, int]:
    src_addr = emu.map_bytes(source)
    delta_addr = emu.map_bytes(delta)
    return src_addr, delta_addr


def _new_vector(emu: Emulator) -> int:
    addr = emu.alloc(24)
    emu._write(addr, bytes(24))
    return addr


def decode_stream(emu: Emulator, delta: bytes, source: bytes,
                  trace: bool = False) -> tuple[int, bytes]:
    """Run STREAM_ENTRY over ``delta``; returns (status, decoded bytes)."""
    emu.trace = trace
    src_addr, delta_addr = _map_pair(emu, source, delta)
    packages = _new_vector(emu)
    err = emu.alloc(32)
    emu._write(err, bytes(32))
    status = emu.call(STREAM_ENTRY, [src_addr, len(source), delta_addr, len(delta),
                                     packages, 0, err])
    blob = emu.read_byte_vector(packages) if status & 1 else b""
    return status, blob


def decode_record(emu: Emulator, delta: bytes, source: bytes, offset: int = 0,
                  allow_header: int = 0, packages: bool = False) -> WindowRecord:
    """Decode exactly one window record starting at ``offset`` inside ``delta``."""
    src_addr, delta_addr = _map_pair(emu, source, delta)
    packages_vec = _new_vector(emu)
    out_vec = _new_vector(emu)
    err = emu.alloc(32)
    emu._write(err, bytes(32))
    cursor = emu.alloc(8)
    emu._write_u64(cursor, delta_addr + offset)
    status = emu.call(WINDOW_ENTRY, [
        src_addr, len(source), packages_vec, 0, cursor, delta_addr + len(delta),
        out_vec, err, allow_header, 1 if packages else 0,
    ])
    end = emu._read_u64(cursor) - delta_addr
    data = emu.read_byte_vector(out_vec) if status & 1 else b""
    return WindowRecord(0, offset, end - offset, len(data), data)


def decode_windows(emu: Emulator, delta: bytes, source: bytes) -> list[WindowRecord]:
    """Walk a whole delta stream window by window (the container inner loop)."""
    src_addr, delta_addr = _map_pair(emu, source, delta)
    packages = _new_vector(emu)
    err = emu.alloc(32)
    emu._write(err, bytes(32))
    cursor = emu.alloc(8)
    emu._write_u64(cursor, delta_addr + 5)  # skip magic (4) + hdr_ind (1)
    records: list[WindowRecord] = []
    while emu._read_u64(cursor) < delta_addr + len(delta):
        before = emu._read_u64(cursor) - delta_addr
        out_vec = _new_vector(emu)
        status = emu.call(WINDOW_ENTRY, [
            src_addr, len(source), packages, 0, cursor, delta_addr + len(delta),
            out_vec, err, 0, 1,
        ])
        if not status & 1 and delta[before] & 3 == 0:
            # The stream driver retries once with "allow header" for records
            # whose type bits are zero (see FUN_002c011c).
            emu._write_u64(cursor, delta_addr + before)
            out_vec = _new_vector(emu)
            status = emu.call(WINDOW_ENTRY, [
                src_addr, len(source), packages, 0, cursor, delta_addr + len(delta),
                out_vec, err, 1, 1,
            ])
        after = emu._read_u64(cursor) - delta_addr
        if not status & 1:
            break
        data = emu.read_byte_vector(out_vec)
        records.append(WindowRecord(len(records), before, after - before, len(data), data))
        if after <= before:
            break
    return records


def find_streams(raw: bytes) -> list[int]:
    """Offsets of every ``D6 C3 C4`` stream header inside a patch container."""
    out: list[int] = []
    start = 0
    magic = b"\xd6\xc3\xc4"
    while True:
        idx = raw.find(magic, start)
        if idx < 0:
            return out
        out.append(idx)
        start = idx + 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--so", default=str(DEFAULT_SO))
    sub = parser.add_subparsers(dest="mode", required=True)

    info = sub.add_parser("info", help="decode the info delta stream and hash it")
    info.add_argument("--patch", required=True)
    info.add_argument("--source", default=str(DEFAULT_SOURCE))
    info.add_argument("--source-head", type=lambda v: int(v, 0), default=0x48C000)
    info.add_argument("--windows", action="store_true", help="list every window record")
    info.add_argument("--out")

    con = sub.add_parser("container", help="print the PBSR container header")
    con.add_argument("--patch", required=True)

    wse = sub.add_parser("windows", help="walk the windows of a raw delta")
    wse.add_argument("--patch", required=True)
    wse.add_argument("--source", default=str(DEFAULT_SOURCE))
    wse.add_argument("--source-head", type=lambda v: int(v, 0), default=0x48C000)

    rec = sub.add_parser("record", help="decode a single hand written record")
    rec.add_argument("--delta-hex", required=True)
    rec.add_argument("--source-hex", default="")
    rec.add_argument("--allow-header", type=int, default=0)
    rec.add_argument("--packages", action="store_true")

    stm = sub.add_parser("stream", help="decode a raw delta stream given as hex")
    stm.add_argument("--delta-hex", required=True)
    stm.add_argument("--source-hex", default="")

    vec = sub.add_parser("vectors", help="write the reproducible vector set")
    vec.add_argument("--patch", required=True)
    vec.add_argument("--source", default=str(DEFAULT_SOURCE))
    vec.add_argument("--source-head", type=lambda v: int(v, 0), default=0x48C000)
    vec.add_argument("--outdir", required=True)

    args = parser.parse_args(argv)

    if args.mode == "container":
        patch = read_container(Path(args.patch))
        print(f"magic={PATCH_MAGIC.decode()} source_size=0x{patch.source_size:x} "
              f"info_length={patch.info_length} build=0x{patch.build:x} "
              f"source_md5={patch.source_md5.hex()}")
        print(f"streams at {[hex(i) for i in find_streams(patch.raw)]}")
        return 0

    emu = Emulator(Path(args.so))
    emu.load()

    if args.mode == "info":
        patch = read_container(Path(args.patch))
        head = read_source_head(Path(args.source), args.source_head)
        if args.windows:
            status, blob, records = emu.trace_stream(patch.info, head)
        else:
            status, blob = decode_stream(emu, patch.info, head)
            records = []
        for record in records:
            print(f"  #{record.index} start={record.start:>4} "
                  f"consumed={record.consumed:>4} produced={record.produced:>7} "
                  f"md5={record.md5}")
        print(f"status={status} bytes={len(blob)} md5={hashlib.md5(blob).hexdigest()}")
        print(f"source_head_md5={hashlib.md5(head).hexdigest()} "
              f"container_md5={patch.source_md5.hex()}")
        if args.out:
            Path(args.out).write_bytes(blob)
        return 0 if status & 1 else 1

    if args.mode == "windows":
        patch = read_container(Path(args.patch))
        head = read_source_head(Path(args.source), args.source_head)
        for offset in find_streams(patch.raw):
            stream = patch.raw[offset:]
            if len(stream) > 0x100000:
                stream = stream[:0x100000]
            records = decode_windows(emu, stream, head)
            total = sum(r.produced for r in records)
            print(f"stream @0x{offset:x}: windows={len(records)} produced={total}")
            for record in records[:12]:
                print(f"   #{record.index} start={record.start} consumed={record.consumed} "
                      f"produced={record.produced} head={record.data[:16].hex()}")
        return 0

    if args.mode == "stream":
        delta = bytes.fromhex(args.delta_hex)
        source = bytes.fromhex(args.source_hex)
        status, blob = decode_stream(emu, delta, source or b"\x00" * 8)
        print(f"status={status} bytes={len(blob)} md5={hashlib.md5(blob).hexdigest()}")
        if blob:
            print(f"data={blob[:64].hex()}")
        return 0 if status & 1 else 1

    if args.mode == "vectors":
        patch = read_container(Path(args.patch))
        head = read_source_head(Path(args.source), args.source_head)
        outdir = Path(args.outdir)
        outdir.mkdir(parents=True, exist_ok=True)
        status, blob, records = emu.trace_stream(patch.info, head)
        # 1. the container description
        (outdir / "container.json").write_text(
            json.dumps({
                "patch": Path(args.patch).name,
                "patch_bytes": len(patch.raw),
                "source_size_field": patch.source_size,
                "source_file_bytes": Path(args.source).stat().st_size,
                "source_md5": patch.source_md5.hex(),
                "build": hex(patch.build),
                "info_length": patch.info_length,
                "info_offset": patch.info_offset,
                "streams": [hex(i) for i in find_streams(patch.raw)],
            }, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        # 2. the info delta itself (small, keeps the vector reproducible)
        (outdir / "info_stream.hex").write_text(patch.info.hex() + "\n", encoding="utf-8")
        # 3. the decoded head region (only the first 4 KiB; the md5 covers all)
        (outdir / "info_decoded_head.bin").write_bytes(blob[:4096])
        (outdir / "info_decoded.json").write_text(
            json.dumps({
                "status": status,
                "bytes": len(blob),
                "md5": hashlib.md5(blob).hexdigest(),
                "first32": blob[:32].hex(),
                "windows": [r.as_dict() for r in records],
            }, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        # 4. runtime opcode tables
        tables = {
            "table_a": {"address": hex(TABLE_A), "stride": 6,
                        "rows": [emu._mem(TABLE_A + i * 6, 6).hex() for i in range(256)]},
            "table_b": {"address": hex(TABLE_B), "stride": 3,
                        "rows": [emu._mem(TABLE_B + i * 3, 3).hex() for i in range(256)]},
        }
        (outdir / "opcode_tables.json").write_text(
            json.dumps(tables, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        # 5. a no-op stream: header only, no windows
        noop = b"\xd6\xc3\xc4\x53\x00"
        noop_status, noop_blob = decode_stream(emu, noop, head[:64])
        (outdir / "noop_stream.hex").write_text(noop.hex() + "\n", encoding="utf-8")
        (outdir / "noop_stream.json").write_text(
            json.dumps({"delta": noop.hex(), "status": noop_status,
                        "bytes": len(noop_blob)}, indent=1, sort_keys=True) + "\n",
            encoding="utf-8")
        print(f"vectors written to {outdir}")
        print(f"info status={status} bytes={len(blob)} md5={hashlib.md5(blob).hexdigest()}")
        print(f"noop status={noop_status} bytes={len(noop_blob)}")
        return 0

    delta = bytes.fromhex(args.delta_hex)
    source = bytes.fromhex(args.source_hex)
    record = decode_record(emu, delta, source, allow_header=args.allow_header,
                           packages=args.packages)
    print(f"status={'ok' if record.produced or record.consumed else 'fail'} "
          f"consumed={record.consumed} produced={record.produced} md5={record.md5}")
    print(f"data={record.data[:64].hex()}")
    for call in emu.calls[:20]:
        print(f"  {call.name}{call.args} -> {call.result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
