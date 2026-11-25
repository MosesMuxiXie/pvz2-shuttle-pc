"""rsbpatch — PvZ2 官方 ``.rsbpatch`` 补丁应用器（纯 Python 复刻）。

把官方补丁链（460.1 -> 460.2 -> 460.9）应用到一份 1BSR OBB 上，产物逐字节等同官方
patcher 的输出（验收方式：整体 MD5 精确相等）。

容器（.rsbpatch，全部 little-endian）
------------------------------------
48 B 头::

    0   'PBSR'
    4   u32 版本, 必须 1
    8   u32 类型, 必须 2
    12  u64 **目标** OBB 字节数（不是源文件长度：patch1 = 2,095,579,136 = 460.2 的长度，
        patch2 = 2,096,463,872 = 460.9 的长度）
    20  u32 info-section 补丁流字节数
    24  u8[16] 源 OBB info-section 的 MD5
    40  u32 报文（subgroup）条数
    44  u32 flag: 1 = info-section 也是补丁流, 0 = 原样拷贝

    48  info-section VCDIFF 流（长度取 +20）
    之后逐条报文::

        0   u32 类型: 0 = 未变（原样拷贝源 subgroup）, 1 = 有 VCDIFF payload
        4   u32 payload 字节数
        8   char[128] subgroup 名（NUL 结尾）
        136 u8[16] 源 subgroup 内容的 MD5（新建 subgroup 为 d41d8...）
        152 payload

VCDIFF 方言
-----------
与 RFC3284 的差别只在“头部 + 变长整数”：

* 流头 5 B：``d6 c3 c4`` + 版本字节（0 或 0x53）+ flags（bit0/bit1 必须为 0）。
* varint 是 **MSB-first base-128**（RFC 是 little-endian base-128），最长 5 B。
* 窗口头沿用 RFC 字段顺序：Win_Indicator, [源段长, 源段内偏移], delta 编码长度,
  目标窗口长度, Delta_Indicator, data/inst/addr 三段长度。
* 码表 = RFC3284 **默认码表**（256 项，每项两条指令 ``{type,size,mode}``）。
* 三段长度为 0 时进入**内联单流模式**：opcode 之后的 size/地址/data 全部紧跟在同一
  inst 流里（官方 163 B 的 info 流就是这样）。

用法::

    python tools/rsbpatch.py apply  --src base.obb --patch a.rsbpatch --out a.obb
    python tools/rsbpatch.py chain  --src base.obb --patch a.rsbpatch --patch b.rsbpatch --out b.obb
    python tools/rsbpatch.py info   --patch a.rsbpatch
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import struct
import sys
import time

# ---------------------------------------------------------------- 常量

PATCH_MAGIC = b"PBSR"
PATCH_HEADER_SIZE = 48
DESCRIPTOR_SIZE = 152
NAME_SIZE = 128
EMPTY_MD5 = bytes.fromhex("d41d8cd98f00b204e9800998ecf8427e")
VCDIFF_MAGIC = b"\xd6\xc3\xc4"

# 1BSR 头槽位（u32 下标；字节偏移 = 4 * 下标），与 tools/obb_art.py 的 H 一致
H_VERSION = 1
H_HEADER_SIZE = 3
H_SUBGROUP_INFO_ENTRIES = 10
H_SUBGROUP_INFO_OFFSET = 11
H_SUBGROUP_INFO_ENTRY_SIZE = 12

# subgroup 记录（204 B）内的字段字节偏移
REC_NAME = 0
REC_STREAM = 128          # <12I: offset,size,_sid,flags,header_len,data_offset,
                          #       data_csize,data_dsize,_b,image_offset,image_csize,image_dsize
REC_ENTRIES = 196
REC_INFO_SIZE = 192

# 指令类型
NOOP, ADD, RUN, COPY = 0, 1, 2, 3


class PatchError(Exception):
    """补丁或容器不合法（消息里带具体位置/原因）。"""


# ---------------------------------------------------------------- varint

def read_varint(buf, pos, end):
    """读一个 MSB-first base-128 变长整数。

    官方实现（FUN_002c1800）::

        v = 0
        for i in range(5):
            b = buf[pos]; pos += 1
            v = (v << 7) | (b & 0x7f)
            if b < 0x80: return v, pos
        raise  # 第 6 个字节仍有高位 -> 非法

    返回 ``(value, new_pos)``。
    """
    v = 0
    for _ in range(5):
        if pos >= end:
            raise PatchError("varint 越界（pos=%d end=%d）" % (pos, end))
        b = buf[pos]
        pos += 1
        v = (v << 7) | (b & 0x7F)
        if b < 0x80:
            return v, pos
    raise PatchError("varint 超过 5 字节（pos=%d）" % pos)


# ---------------------------------------------------------------- 码表

def build_code_table():
    """重建官方 256 项码表（= RFC3284 默认码表，已在 .so 的运行期表上逐项核对）。"""
    table = [[(NOOP, 0, 0), (NOOP, 0, 0)] for _ in range(256)]

    table[0] = [(RUN, 0, 0), (NOOP, 0, 0)]
    for i in range(18):
        table[1 + i] = [(ADD, i, 0), (NOOP, 0, 0)]

    sizes = [0] + list(range(4, 19))          # 16 项 / 模式
    idx = 19
    for mode in range(9):
        for size in sizes:
            table[idx] = [(COPY, size, mode), (NOOP, 0, 0)]
            idx += 1

    for mode in range(6):                      # ADD 1..4 + COPY 4/5/6
        for add_size in range(1, 5):
            for copy_size in (4, 5, 6):
                table[idx] = [(ADD, add_size, 0), (COPY, copy_size, mode)]
                idx += 1

    for mode in range(6, 9):                   # ADD 1..4 + COPY 4
        for add_size in range(1, 5):
            table[idx] = [(ADD, add_size, 0), (COPY, 4, mode)]
            idx += 1

    for mode in range(9):                      # COPY 4 + ADD 1
        table[idx] = [(COPY, 4, mode), (ADD, 1, 0)]
        idx += 1

    if idx != 256:
        raise AssertionError("码表条目数 %d != 256" % idx)
    return table


CODE_TABLE = build_code_table()


def serialize_code_table():
    """码表打成 6144 B（256 x 2 x 3 x u32），用于和 .so 里 dump 出来的表比对。"""
    out = bytearray()
    for pair in CODE_TABLE:
        for (typ, size, mode) in pair:
            out += struct.pack("<3I", typ, size, mode)
    return bytes(out)


# ---------------------------------------------------------------- 解码器

def vcdiff_decode(source, patch):
    """解一条 VCDIFF 流。``source`` 是源 buffer（可为 b''）。

    注：官方驱动在某个窗口解失败、且该窗口首字节低 2 位为 0 时，会用 ``param_9=1``
    重解一次（``FUN_002c011c`` 里的重试分支）。两份官方补丁的所有流（2 条 info +
    6 条报文）都在首次尝试就成功，所以这条回退分支没有可对拍样本，此处不实现；
    真遇到了会抛出带窗口偏移的 ``PatchError``，不会被静默吞掉。
    """
    n = len(patch)
    if n < 5:
        raise PatchError("VCDIFF 流太短（%d B）" % n)
    if patch[:3] != VCDIFF_MAGIC:
        raise PatchError("VCDIFF magic 不匹配：%s" % patch[:3].hex())
    if patch[3] not in (0, 0x53):
        raise PatchError("VCDIFF 版本不支持：%d" % patch[3])
    if patch[4] & 0x03:
        raise PatchError("VCDIFF flags 不支持：0x%02x" % patch[4])

    out = bytearray()
    pos = 5
    while pos < n:
        try:
            pos = _decode_window(source, patch, pos, out)
        except _WinMode0 as exc:
            raise PatchError(
                "VCDIFF 窗口 @%d 解码失败：%s（共 %d 个窗口，已产出 %d B）"
                % (exc.pos, exc.msg, 0, len(out))) from None
    return bytes(out)


class _WinMode0(Exception):
    def __init__(self, pos, msg):
        super().__init__(msg)
        self.pos = pos
        self.msg = msg


def _decode_window(source, patch, pos, out):
    """解一个窗口，把结果追加到 ``out``；返回下一个窗口的起始偏移。"""
    start = pos
    end = len(patch)
    win_ind = patch[pos]
    pos += 1

    src_seg_len = 0
    src_seg_pos = 0
    if win_ind & 0x01:                          # VCD_SOURCE
        src_seg_len, pos = read_varint(patch, pos, end)
        src_seg_pos, pos = read_varint(patch, pos, end)
    elif win_ind & 0x02:                        # VCD_TARGET：源是同一次解码早先的输出
        src_seg_len, pos = read_varint(patch, pos, end)
        src_seg_pos, pos = read_varint(patch, pos, end)
    elif win_ind & ~0x03:
        raise PatchError("窗口指示位非法：0x%02x @%d" % (win_ind, start))

    delta_len, pos = read_varint(patch, pos, end)
    tgt_len, pos = read_varint(patch, pos, end)
    if pos >= end:
        raise PatchError("窗口头截断 @%d" % start)
    delta_ind = patch[pos]
    pos += 1
    if delta_ind:
        raise PatchError("Delta_Indicator 非 0（%d）@%d" % (delta_ind, start))

    if win_ind & 0x02:
        if src_seg_pos + src_seg_len > len(out):
            raise PatchError("VCD_TARGET 源段越界 @%d" % start)
        seg = src_seg_pos
        srcbuf = out
    else:
        if src_seg_pos + src_seg_len > len(source):
            raise PatchError(
                "源段越界：pos=%d len=%d 但源只有 %d B"
                % (src_seg_pos, src_seg_len, len(source)))
        seg = src_seg_pos
        srcbuf = source

    data_len, pos = read_varint(patch, pos, end)
    inst_len, pos = read_varint(patch, pos, end)
    addr_len, pos = read_varint(patch, pos, end)

    data_at = pos
    inst_at = data_at + data_len
    addr_at = inst_at + inst_len
    win_end = addr_at + addr_len
    if win_end > end:
        raise PatchError(
            "窗口三段越界：需要到 %d，流只到 %d（@%d）" % (win_end, end, start))

    single = data_len == 0 and addr_len == 0
    base = src_seg_len
    near = [0, 0, 0, 0]
    near_pos = 0
    same = [0] * 768

    out0 = len(out)
    i = data_at                 # data 流游标
    j = inst_at                 # inst 流游标
    k = addr_at                 # addr 流游标

    while len(out) - out0 < tgt_len:
        if j >= inst_at + inst_len:
            raise _WinMode0(start, "指令流耗尽（已产出 %d/%d）"
                            % (len(out) - out0, tgt_len))
        opcode = patch[j]
        j += 1
        for typ, size, mode in CODE_TABLE[opcode]:
            if typ == NOOP:
                continue
            if size == 0:
                size, j = read_varint(patch, j, inst_at + inst_len)
                if size == 0:
                    raise _WinMode0(start, "指令长度 0（opcode 0x%02x）" % opcode)

            if typ == ADD:
                if single:
                    if j + size > inst_at + inst_len:
                        raise _WinMode0(start, "内联 ADD 越界")
                    out += patch[j:j + size]
                    j += size
                else:
                    if i + size > inst_at:
                        raise _WinMode0(start, "data 段 ADD 越界")
                    out += patch[i:i + size]
                    i += size

            elif typ == RUN:
                if single:
                    if j >= inst_at + inst_len:
                        raise _WinMode0(start, "内联 RUN 越界")
                    byte = patch[j]
                    j += 1
                else:
                    if i >= inst_at:
                        raise _WinMode0(start, "data 段 RUN 越界")
                    byte = patch[i]
                    i += 1
                out += bytes([byte]) * size

            else:  # COPY
                here = base + (len(out) - out0)
                if mode == 0:
                    delta, _p = read_varint(patch, j if single else k,
                                            inst_at + inst_len if single else win_end)
                    if single:
                        j = _p
                    else:
                        k = _p
                    addr = delta
                elif mode == 1:
                    delta, _p = read_varint(patch, j if single else k,
                                            inst_at + inst_len if single else win_end)
                    if single:
                        j = _p
                    else:
                        k = _p
                    addr = here - delta
                elif 2 <= mode <= 5:
                    delta, _p = read_varint(patch, j if single else k,
                                            inst_at + inst_len if single else win_end)
                    if single:
                        j = _p
                    else:
                        k = _p
                    addr = near[mode - 2] + delta
                else:
                    src_pos = j if single else k
                    if src_pos >= (inst_at + inst_len if single else win_end):
                        raise _WinMode0(start, "same-cache 地址越界")
                    byte = patch[src_pos]
                    if single:
                        j = src_pos + 1
                    else:
                        k = src_pos + 1
                    addr = same[(mode - 6) * 256 + byte]

                if addr < 0:
                    raise _WinMode0(start, "COPY 地址为负（mode=%d）" % mode)
                near[near_pos] = addr
                near_pos = (near_pos + 1) & 3
                same[addr % 768] = addr
                if addr + size > here:
                    raise _WinMode0(
                        start, "COPY 越过已知输出（addr=%d size=%d here=%d）"
                        % (addr, size, here))
                _copy(srcbuf, seg, base, addr, size, out, out0)

    if len(out) - out0 != tgt_len:
        raise _WinMode0(start, "目标长度不符：%d != %d" % (len(out) - out0, tgt_len))
    if not single:
        if i != inst_at or k != win_end:
            raise _WinMode0(
                start, "data/addr 段没有恰好消费完（data %d/%d, addr %d/%d）"
                % (i - data_at, data_len, k - addr_at, addr_len))
    return win_end


def _copy(srcbuf, seg, base, addr, size, out, out0):
    """把虚拟地址空间 [addr, addr+size) 拷进 out。

    虚拟空间：``[0, base)`` 是源段，``[base, ...)`` 是**本窗口**已产出的输出；
    ``out`` 是整条流的累计输出，本窗口从 ``out0`` 起，所以落在输出段的地址
    都要再加 ``out0`` 才是 ``out`` 的下标。
    """
    if addr + size <= base:
        out += srcbuf[seg + addr:seg + addr + size]
        return
    produced = len(out) - out0               # 本窗口已产出（不含更早的窗口）
    if addr >= base and addr + size <= base + produced:
        s = out0 + (addr - base)
        out += out[s:s + size]               # 纯自引用且已物化 -> 切片即可
        return
    for p in range(addr, addr + size):
        if p < base:
            out.append(srcbuf[seg + p])
        else:
            out.append(out[out0 + (p - base)])


# ---------------------------------------------------------------- 容器层

def parse_patch_header(data):
    """解析 48 B 补丁头。"""
    if len(data) < PATCH_HEADER_SIZE:
        raise PatchError("补丁头太短（%d B）" % len(data))
    if data[:4] != PATCH_MAGIC:
        raise PatchError("补丁 magic 不匹配：%s" % data[:4])
    version, ptype, target_size, info_len = struct.unpack_from("<IIQI", data, 4)
    if version != 1:
        raise PatchError("补丁版本不支持：%d" % version)
    if ptype != 2:
        raise PatchError("补丁类型不支持：%d" % ptype)
    info_hash = data[24:40]
    count, flag = struct.unpack_from("<II", data, 40)
    return {
        "version": version,
        "type": ptype,
        "target_size": target_size,
        "info_len": info_len,
        "info_hash": info_hash,
        "count": count,
        "info_patched": flag,
        "data_offset": PATCH_HEADER_SIZE + (info_len if flag else 0),
    }


def read_rsb_header(f, path="<rsb>"):
    """读 1BSR 的 112 B 头，返回 (u32 数组, info-section 字节数)。"""
    f.seek(0)
    head = f.read(112)
    if len(head) < 112:
        raise PatchError("%s: 文件太短，读不到 1BSR 头" % path)
    if head[:4] != b"1bsr":
        raise PatchError("%s: 不是 1BSR（magic=%s）" % (path, head[:4]))
    hdr = list(struct.unpack("<28I", head))
    if hdr[H_VERSION] != 4:
        raise PatchError("%s: 1BSR 版本不支持 %d" % (path, hdr[H_VERSION]))
    return hdr, hdr[H_HEADER_SIZE]


def parse_info_section(blob):
    """解析 info-section（头部 + subgroup 表），返回 (hdr, [(name, offset, size, raw)])。"""
    if len(blob) < 112:
        raise PatchError("info-section 太短（%d B）" % len(blob))
    if blob[:4] != b"1bsr":
        raise PatchError("info-section 的 1BSR magic 不匹配：%s" % blob[:4])
    hdr = list(struct.unpack_from("<28I", blob, 0))
    entries = hdr[H_SUBGROUP_INFO_ENTRIES]
    offset = hdr[H_SUBGROUP_INFO_OFFSET]
    esize = hdr[H_SUBGROUP_INFO_ENTRY_SIZE]
    if esize < 176:
        raise PatchError("subgroup 记录尺寸太小：%d" % esize)
    if entries == 0:
        raise PatchError("subgroup 记录数为 0")
    if offset + esize * entries > len(blob):
        raise PatchError(
            "subgroup 表越过 info-section 边界（%d + %d*%d > %d）"
            % (offset, esize, entries, len(blob)))
    recs = []
    for k in range(entries):
        base = offset + k * esize
        raw = blob[base:base + esize]
        name = raw[:NAME_SIZE].split(b"\0", 1)[0].decode("utf-8", "replace")
        off, size = struct.unpack_from("<II", raw, REC_STREAM)
        recs.append({
            "index": k,
            "name": name,
            "offset": off,
            "size": size,
            "raw": raw,
            "blob": blob,
            "rec_at": base,
        })
    return hdr, recs


def _md5_file_range(f, offset, size, chunk=1 << 22):
    f.seek(offset)
    h = hashlib.md5()
    left = size
    while left:
        b = f.read(min(chunk, left))
        if not b:
            raise PatchError("读源文件时提前 EOF（offset=%d）" % offset)
        h.update(b)
        left -= len(b)
    return h.digest()


def iter_descriptors(f, patch_path, hdr):
    """按顺序遍历报文描述符。"""
    count = hdr["count"]
    f.seek(0, os.SEEK_END)
    size = f.tell()
    pos = hdr["data_offset"]
    for k in range(count):
        if pos + DESCRIPTOR_SIZE > size:
            raise PatchError(
                "补丁在报文 %d/%d 处截断（pos=%d size=%d）" % (k, count, pos, size))
        f.seek(pos)
        desc = f.read(DESCRIPTOR_SIZE)
        ptype, plen = struct.unpack_from("<II", desc, 0)
        name = desc[8:8 + NAME_SIZE].split(b"\0", 1)[0].decode("utf-8", "replace")
        before = desc[136:152]
        yield {
            "index": k,
            "type": ptype,
            "payload_len": plen,
            "name": name,
            "before_hash": before,
            "payload_at": pos + DESCRIPTOR_SIZE,
            "descriptor_at": pos,
        }
        pos += DESCRIPTOR_SIZE + plen
    if pos != size:
        raise PatchError(
            "报文走完后 pos=%d 但补丁长度=%d（差 %d）" % (pos, size, size - pos))


def verify_patch(patch_path, source_path):
    """只做校验，不解码：返回 (补丁头, 报文列表)。"""
    with open(patch_path, "rb") as f:
        hdr = parse_patch_header(f.read(PATCH_HEADER_SIZE))
        with open(source_path, "rb") as s:
            _, info_size = read_rsb_header(s, source_path)
            got = _md5_file_range(s, 0, info_size)
        if got != hdr["info_hash"]:
            raise PatchError(
                "info-section 哈希不匹配：源 %s，补丁要求 %s"
                % (got.hex(), hdr["info_hash"].hex()))
        packets = list(iter_descriptors(f, patch_path, hdr))
    return hdr, packets


# ---------------------------------------------------------------- 应用

def _replace_with_retry(tmp, dst, tries=40, delay=0.5):
    """Windows 上目标被别的进程读着时 os.replace 会 Access denied；退让重试。"""
    last = None
    for _ in range(tries):
        try:
            os.replace(tmp, dst)
            return
        except PermissionError as exc:      # 共享工作区里很常见
            last = exc
            time.sleep(delay)
    raise PatchError("无法写产物 %s（目标被占用）：%s" % (dst, last))


@contextlib.contextmanager
def _temp_product(path):
    """写中间产物；任何异常都把它删掉，留在磁盘上的只有成功的结果。"""
    f = open(path, "wb")
    try:
        yield f
    except BaseException:
        f.close()
        with contextlib.suppress(OSError):
            os.unlink(path)
        raise
    else:
        f.close()


def apply_patch(source_path, patch_path, out_path, *, log=None,
                expected_md5=None, verify=True):
    """把一条补丁应用到 ``source_path``，结果写到 ``out_path``。

    返回 dict（含 md5、字节数、变更条数等）。
    """
    say = log or (lambda *_a, **_k: None)
    with open(patch_path, "rb") as pf:
        hdr = parse_patch_header(pf.read(PATCH_HEADER_SIZE))

        with open(source_path, "rb") as sf:
            _, info_size = read_rsb_header(sf, source_path)
            if verify:
                got = _md5_file_range(sf, 0, info_size)
                if got != hdr["info_hash"]:
                    raise PatchError(
                        "info-section 哈希不匹配：源 %s，补丁要求 %s"
                        % (got.hex(), hdr["info_hash"].hex()))
            sf.seek(0)
            src_info = sf.read(info_size)

            # 1) info-section
            pf.seek(PATCH_HEADER_SIZE)
            if hdr["info_patched"]:
                stream = pf.read(hdr["info_len"])
                if len(stream) != hdr["info_len"]:
                    raise PatchError("info-section 补丁流截断")
                new_info = vcdiff_decode(src_info, stream)
            else:
                new_info = src_info
            say("info-section: %d B -> %d B" % (len(src_info), len(new_info)))

            _, new_recs = parse_info_section(new_info)
            if len(new_recs) != hdr["count"]:
                raise PatchError(
                    "info-section 记录数 %d != 补丁声明 %d"
                    % (len(new_recs), hdr["count"]))
            _, old_recs = parse_info_section(src_info)
            old_by_name = {}
            for r in old_recs:
                old_by_name[r["name"].upper()] = r
            new_by_name = {}
            for r in new_recs:
                new_by_name[r["name"].upper()] = r

            # 2) 逐报文
            packets = list(iter_descriptors(pf, patch_path, hdr))
            if len(packets) != hdr["count"]:
                raise PatchError("报文数 %d != %d" % (len(packets), hdr["count"]))

            tmp = out_path + ".part"
            changed = []
            total = 0
            with _temp_product(tmp) as of:
                of.write(new_info)
                total += len(new_info)
                for p in packets:
                    key = p["name"].upper()
                    new_rec = new_by_name.get(key)
                    if new_rec is None:
                        raise PatchError(
                            "报文 %d（%s）在目标 info-section 里不存在（报文顺序错乱）"
                            % (p["index"], p["name"]))
                    if new_rec["index"] != p["index"]:
                        raise PatchError(
                            "报文顺序错乱：报文 %d 是 %s，但目标表里它在第 %d 位"
                            % (p["index"], p["name"], new_rec["index"]))
                    old_rec = old_by_name.get(key)
                    if old_rec is None:
                        if p["before_hash"] != EMPTY_MD5:
                            raise PatchError(
                                "报文 %d（%s）在源 OBB 里不存在，但 beforeHash 不是空内容"
                                % (p["index"], p["name"]))
                        src_blob = b""
                    else:
                        if verify:
                            got = _md5_file_range(sf, old_rec["offset"], old_rec["size"])
                            if got != p["before_hash"]:
                                raise PatchError(
                                    "报文 %d（%s）源内容哈希不匹配：源 %s，补丁要求 %s"
                                    % (p["index"], p["name"], got.hex(),
                                       p["before_hash"].hex()))
                        sf.seek(old_rec["offset"])
                        src_blob = sf.read(old_rec["size"])

                    if p["type"] == 0:
                        data = src_blob
                    else:
                        pf.seek(p["payload_at"])
                        payload = pf.read(p["payload_len"])
                        if len(payload) != p["payload_len"]:
                            raise PatchError("报文 %d payload 截断" % p["index"])
                        data = vcdiff_decode(src_blob, payload)
                        changed.append({
                            "index": p["index"],
                            "name": p["name"],
                            "payload": p["payload_len"],
                            "src": len(src_blob),
                            "out": len(data),
                        })
                    if len(data) != new_rec["size"]:
                        raise PatchError(
                            "报文 %d（%s）解出 %d B，目标表要求 %d B"
                            % (p["index"], p["name"], len(data), new_rec["size"]))
                    # 装配层闭合校验：累计写出位置必须等于目标表声明的绝对 offset。
                    # 这里不重算 offset —— 解码错了必须报错，而不是被重算掩盖。
                    if total != new_rec["offset"]:
                        raise PatchError(
                            "装配偏移不闭合：报文 %d（%s）累计 %d，目标表声明 %d"
                            % (p["index"], p["name"], total, new_rec["offset"]))
                    of.write(data)
                    total += len(data)
                if hdr["target_size"] and total != hdr["target_size"]:
                    raise PatchError(
                        "产物总长 %d != 补丁头声明的目标长度 %d"
                        % (total, hdr["target_size"]))
            try:
                _replace_with_retry(tmp, out_path)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
                raise

    md5 = hashlib.md5()
    with open(out_path, "rb") as f:
        while True:
            b = f.read(1 << 22)
            if not b:
                break
            md5.update(b)
    result = {
        "out": out_path,
        "bytes": total,
        "md5": md5.hexdigest(),
        "changed": changed,
        "expected_md5": expected_md5,
    }
    if expected_md5 and result["md5"] != expected_md5:
        raise PatchError(
            "产物 MD5 不符：%s，期望 %s" % (result["md5"], expected_md5))
    return result


# ---------------------------------------------------------------- CLI

def _cmd_apply(args):
    res = apply_patch(args.src, args.patch, args.out,
                      expected_md5=args.md5, log=print)
    print(json.dumps({k: v for k, v in res.items() if k != "changed"},
                     ensure_ascii=False, indent=2))
    for c in res["changed"]:
        print("  #%-5d %-40s payload=%-9d %d -> %d"
              % (c["index"], c["name"], c["payload"], c["src"], c["out"]))
    return 0


def header_md5(path):
    """产物的 info-section（头部区）MD5 —— 下一跳补丁头的 ``@24`` 就该是它。"""
    with open(path, "rb") as f:
        _, info_size = read_rsb_header(f, path)
        return _md5_file_range(f, 0, info_size)


def _cmd_chain(args):
    cur = args.src
    tmpdir = os.path.dirname(os.path.abspath(args.out))
    patches = list(args.patch)
    # 跨跳互校：每跳产物落盘后先验「本跳产物的头部 MD5 == 下一跳声明的 @24」。
    # 这条不依赖 --md5，默认开；补丁链被人替换过时会当场炸，而不是等最后一跳。
    cross = [None] * len(patches)
    if not getattr(args, "no_cross_check", False):
        for n in range(len(patches) - 1):
            with open(patches[n + 1], "rb") as f:
                nxt = parse_patch_header(f.read(PATCH_HEADER_SIZE))
            cross[n] = nxt["info_hash"]
    for n, patch in enumerate(patches):
        last = n == len(patches) - 1
        dst = args.out if last else os.path.join(tmpdir, ".rsbchain-%d.obb" % n)
        md5 = args.md5[n] if args.md5 and n < len(args.md5) else None
        print("== %s -> %s" % (os.path.basename(patch), os.path.basename(dst)))
        res = apply_patch(cur, patch, dst, expected_md5=md5, log=print)
        print("   %d B md5=%s" % (res["bytes"], res["md5"]))
        for c in res["changed"]:
            print("   #%-5d %-40s payload=%-9d %d -> %d"
                  % (c["index"], c["name"], c["payload"], c["src"], c["out"]))
        if cross[n] is not None:
            got = header_md5(dst)
            if got != cross[n]:
                raise PatchError(
                    "跨跳互校失败：第 %d 跳产物 header md5=%s，第 %d 跳补丁要求 %s"
                    % (n + 1, got.hex(), n + 2, cross[n].hex()))
            print("   cross-check: hop %d header md5 == patch %d @24 (%s)"
                  % (n + 1, n + 2, got.hex()))
        if os.path.abspath(cur) != os.path.abspath(args.src):
            os.unlink(cur)          # 中间态用完即删（含最后一跳的输入）
        cur = dst
    return 0


def _cmd_info(args):
    with open(args.patch, "rb") as f:
        size = os.fstat(f.fileno()).st_size
        hdr = parse_patch_header(f.read(PATCH_HEADER_SIZE))
        packets = list(iter_descriptors(f, args.patch, hdr))
    print(json.dumps({
        "patch_bytes": size,
        "version": hdr["version"],
        "type": hdr["type"],
        "target_size": hdr["target_size"],
        "info_len": hdr["info_len"],
        "info_hash": hdr["info_hash"].hex(),
        "count": hdr["count"],
        "info_patched": hdr["info_patched"],
        "data_offset": hdr["data_offset"],
        "changed": [
            {"index": p["index"], "name": p["name"], "type": p["type"],
             "payload": p["payload_len"], "before": p["before_hash"].hex()}
            for p in packets if p["type"] != 0
        ],
    }, ensure_ascii=False, indent=2))
    return 0


def _cmd_table(args):
    """打印 256 条码表（两条指令各一行），可 --json。"""
    table = build_code_table()
    if args.json:
        print(json.dumps(table, separators=(",", ":")))
        return 0

    def one(ins):
        kind, size, mode = ins
        if kind == 0:
            return "NOOP"
        if kind == 1:
            return "ADD(%s)" % ("varint" if size == 0 else size)
        if kind == 2:
            return "RUN(%s)" % ("varint" if size == 0 else size)
        return "COPY(size=%s,mode=%d)" % ("varint" if size == 0 else size, mode)

    for i, (a, b) in enumerate(table):
        line = one(a)
        if b[0] != 0:
            line += " + " + one(b)
        print("%3d  %s" % (i, line))
    print("# table md5 = %s" % hashlib.md5(serialize_code_table()).hexdigest())
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rsbpatch", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("apply", help="应用一条补丁")
    a.add_argument("--src", required=True)
    a.add_argument("--patch", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--md5", help="期望的产物 MD5")
    a.set_defaults(func=_cmd_apply)

    c = sub.add_parser("chain", help="依次应用多条补丁")
    c.add_argument("--src", required=True)
    c.add_argument("--patch", action="append", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--md5", action="append", help="每一跳的期望 MD5（可多次）")
    c.add_argument("--no-cross-check", action="store_true",
                   help="不校验上一跳产物头部 MD5 与下一跳声明的 @24")
    c.set_defaults(func=_cmd_chain)

    i = sub.add_parser("info", help="打印补丁头与变更清单")
    i.add_argument("--patch", required=True)
    i.set_defaults(func=_cmd_info)

    t = sub.add_parser("table", help="打印 256 条 VCDIFF 码表")
    t.add_argument("--json", action="store_true", help="输出原始 u32 三元组")
    t.set_defaults(func=_cmd_table)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except PatchError as exc:
        print("rsbpatch: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
