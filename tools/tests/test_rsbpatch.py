"""rsbpatch 的回归测试。

跑法（在仓库根目录）::

    python -m unittest discover -s tools/tests -v
    # 或者
    python tools/tests/test_rsbpatch.py -v

缺大文件（base OBB / .rsbpatch）的用例会自动 skip。想顺带校验 2 GB 成品的 MD5::

    RSBPATCH_FULL=1 python -m unittest discover -s tools/tests -v
"""
from __future__ import annotations

import hashlib
import os
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
ROOT = os.path.dirname(TOOLS)                 # 仓库根
WORKSPACE = os.path.dirname(os.path.dirname(ROOT))   # 工作区根（repo/<name>）
WORK = os.path.join(WORKSPACE, "work")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import rsbpatch as R  # noqa: E402

# 补丁链的源必须是 460.1：工作区根目录那只 main.460….obb 自 2026-11-24 起是 460.9，
# 拿它当源会让补丁头的 @24 校验直接失败（这正是「引错文件」的保护）。
BASE_OBB = os.path.join(WORK, "versions", "460.1.obb")
PATCH1 = os.path.join(WORK, "versions", "_incoming", "460.1_460.2.rsbpatch")
PATCH2 = os.path.join(WORK, "versions", "_incoming", "460.2_460.9.rsbpatch")
OUT_4602 = os.path.join(WORK, "versions", "460.2.obb")
OUT_4609 = os.path.join(WORK, "versions", "460.9.obb")

MD5_4602 = "7a219bb7fbfd54b4176aa33e48704b48"
MD5_4609 = "2963d0781e4715522cb12bc2d3bb9f8e"
MD5_INFO_4602 = "5f938695079f4a2812e0770ac261e066"
MD5_INFO_4609 = "1f0dff08e613725a19029df34537460a"
MD5_PACKAGES_4602 = "6e2b334c15b8432f9882f8c1983feafe"
MD5_PACKAGES_4609 = "40c21432b469414806c7b2db4fa10973"
MD5_KERNEL_1536 = "6b788895908bb6af35778729c302eaf7"
MD5_CODE_TABLE = "e2da1c6a7a4142c057c8f6b69f76c957"   # 官方 .so 运行期表的 dump

have_base = os.path.exists(BASE_OBB)
have_p1 = os.path.exists(PATCH1)
have_p2 = os.path.exists(PATCH2)
need_base = unittest.skipUnless(have_base, "缺 base OBB")
need_p1 = unittest.skipUnless(have_base and have_p1, "缺 base OBB 或补丁1")
need_p2 = unittest.skipUnless(have_p1 and have_p2, "缺补丁1/补丁2")


def read_patch(path):
    with open(path, "rb") as f:
        return f.read()


def base_info():
    with open(BASE_OBB, "rb") as f:
        _, size = R.read_rsb_header(f, BASE_OBB)
        f.seek(0)
        return f.read(size)


def blob_of(obb_path, name):
    """从 OBB 里取一个 subgroup 的原始字节。"""
    with open(obb_path, "rb") as f:
        _, size = R.read_rsb_header(f, obb_path)
        f.seek(0)
        info = f.read(size)
        _, recs = R.parse_info_section(info)
        by = {r["name"].upper(): r for r in recs}
        rec = by[name.upper()]
        f.seek(rec["offset"])
        return f.read(rec["size"]), rec


def md5b(b):
    return hashlib.md5(b).hexdigest()


# ------------------------------------------------------------------ 基础件

class TestCodeTable(unittest.TestCase):
    def test_matches_official_runtime_table(self):
        blob = R.serialize_code_table()
        self.assertEqual(len(blob), 256 * 24)
        self.assertEqual(md5b(blob), MD5_CODE_TABLE,
                         "码表与官方 .so 里 FUN_002c0460 生成的表不一致")

    def test_known_entries(self):
        t = R.CODE_TABLE
        self.assertEqual(t[0], [(R.RUN, 0, 0), (R.NOOP, 0, 0)])
        self.assertEqual(t[1], [(R.ADD, 0, 0), (R.NOOP, 0, 0)])
        self.assertEqual(t[18], [(R.ADD, 17, 0), (R.NOOP, 0, 0)])
        self.assertEqual(t[19], [(R.COPY, 0, 0), (R.NOOP, 0, 0)])
        self.assertEqual(t[0x73], [(R.COPY, 0, 6), (R.NOOP, 0, 0)])   # info 流用的就是它
        self.assertEqual(t[162], [(R.COPY, 18, 8), (R.NOOP, 0, 0)])
        self.assertEqual(t[163], [(R.ADD, 1, 0), (R.COPY, 4, 0)])
        self.assertEqual(t[247], [(R.COPY, 4, 0), (R.ADD, 1, 0)])
        self.assertEqual(t[255], [(R.COPY, 4, 8), (R.ADD, 1, 0)])

    def test_one_entry_per_opcode(self):
        for k, pair in enumerate(R.CODE_TABLE):
            self.assertEqual(len(pair), 2, "opcode %d" % k)
            self.assertNotEqual(pair[0][0], R.NOOP, "opcode %d 第一条为空" % k)


class TestVarint(unittest.TestCase):
    def rt(self, data, expect, consumed=None):
        val, pos = R.read_varint(data, 0, len(data))
        self.assertEqual(val, expect)
        if consumed is not None:
            self.assertEqual(pos, consumed)
        return pos

    def test_values(self):
        self.rt(b"\x00", 0, 1)
        self.rt(b"\x7f", 0x7F, 1)
        self.rt(b"\x81\x00", 0x80, 2)
        self.rt(b"\x82\xa3\x80\x00", 0x48C000, 4)      # info 流里的源段长
        self.rt(b"\xc0\x80\x00", 0x100000, 3)          # 目标窗口长度
        self.rt(b"\xff\xff\xff\xff\x7f", (1 << 35) - 1, 5)

    def test_msb_first_not_lsb(self):
        # RFC3284 的小端变长整数会把 81 00 读成 1；这里是 (1<<7)|0 = 128
        self.rt(b"\x81\x00", 0x80)

    def test_overlong_or_truncated(self):
        with self.assertRaises(R.PatchError):
            R.read_varint(b"\xff\xff\xff\xff\xff\x00", 0, 6)
        with self.assertRaises(R.PatchError):
            R.read_varint(b"\x81", 0, 1)


class TestSyntheticWindows(unittest.TestCase):
    """手搓一条最小 VCDIFF 流，验证 ADD / RUN / COPY 三条路径。"""

    @staticmethod
    def varint(v):
        out = [v & 0x7F]
        v >>= 7
        while v:
            out.append((v & 0x7F) | 0x80)
            v >>= 7
        return bytes(reversed(out))

    def window(self, source_len, target_len, inst, data=b"", addr=b"", pos=0):
        """一个窗口的字节（不含 5 B 流头），多窗口流直接拼接即可。"""
        win = bytearray()
        win += b"\x01"                                  # VCD_SOURCE
        win += self.varint(source_len) + self.varint(pos)
        body = self.varint(target_len) + b"\x00"
        body += self.varint(len(data)) + self.varint(len(inst)) + self.varint(len(addr))
        body += data + inst + addr
        win += self.varint(len(body)) + body
        return bytes(win)

    def build(self, source_len, target_len, inst, data=b"", addr=b"", pos=0):
        win = self.window(source_len, target_len, inst, data, addr, pos)
        return R.VCDIFF_MAGIC + b"\x53\x00" + win

    def test_add_run_copy_modes(self):
        source = bytes(range(64)) * 4                  # 256 B
        # ADD 4 (opcode 5) + ADD 4 + ADD 4 -> 12 B, 然后 COPY mode0 size 4
        data = b"ABCDEFGHIJKL"
        inst = bytes([5, 5, 5])                        # 3 x ADD 4
        addr = self.varint(0)                          # COPY mode 0 绝对地址 0
        inst += bytes([20])                            # COPY mode 0 size 4
        target = b"ABCDEFGHIJKL" + source[:4]
        stream = self.build(len(source), len(target), inst, data=data, addr=addr)
        self.assertEqual(R.vcdiff_decode(source, stream), target)

    def test_single_stream_inline_mode(self):
        # data 段与 addr 段都为 0 -> 内联单流：opcode/size/addr 全在 inst 里
        source = b"0123456789" * 8
        inst = bytes([0, 5, ord("z")])                 # RUN size=5 字节 'z'
        inst += bytes([0x13]) + self.varint(20)        # COPY mode 0, size 变长
        inst += self.varint(4)                         # 地址 = 4
        stream = self.build(len(source), 5 + 20, inst)
        self.assertEqual(R.vcdiff_decode(source, stream), b"zzzzz" + source[4:24])

    def test_run_and_add_inline(self):
        inst = bytes([0, 3, ord("x")]) + bytes([4]) + b"abc"
        stream = self.build(0, 3 + 3, inst)
        self.assertEqual(R.vcdiff_decode(b"", stream), b"xxxabc")

    def test_self_reference_copy_in_a_later_window(self):
        """H1 回归：第二窗口的自引用 COPY 只能读**本窗口**已产出的字节。

        审计用同形状的流抓到过「长度对、内容错、不报错」：``_copy`` 的切片分支
        少加窗口起点 ``out0``，于是第二个窗口会把**第一个窗口**的同偏移字节抄回来
        （得 ``AAAA+ABCDAAAA``，正确是 ``AAAA+ABCDABCD``）。
        """
        win1 = self.window(0, 4, bytes([5]), data=b"AAAA")      # ADD 4 -> AAAA
        inst2 = bytes([5]) + b"ABCD"                            # ADD 4 -> ABCD
        inst2 += bytes([20]) + self.varint(0)                   # COPY 4 @ 0（本窗口起点）
        win2 = self.window(0, 8, inst2)
        stream = R.VCDIFF_MAGIC + b"\x53\x00" + win1 + win2
        self.assertEqual(R.vcdiff_decode(b"", stream), b"AAAAABCDABCD")

    def test_self_reference_copy_may_start_mid_window(self):
        """同一分支的另一面：地址指向本窗口的中段（不是起点）也要对。"""
        win1 = self.window(0, 2, bytes([3]), data=b"xy")        # ADD 2 -> xy
        inst2 = bytes([5]) + b"WXYZ"                            # ADD 4 -> WXYZ
        inst2 += bytes([19]) + self.varint(2) + self.varint(2)  # COPY size 2 @ 2
        win2 = self.window(0, 6, inst2)
        stream = R.VCDIFF_MAGIC + b"\x53\x00" + win1 + win2
        self.assertEqual(R.vcdiff_decode(b"", stream), b"xyWXYZYZ")

    def test_bad_magic(self):
        with self.assertRaises(R.PatchError) as cm:
            R.vcdiff_decode(b"", b"\xd6\xc3\xc5\x53\x00")
        self.assertIn("magic", str(cm.exception))

    def test_bad_version_and_flags(self):
        with self.assertRaises(R.PatchError):
            R.vcdiff_decode(b"", R.VCDIFF_MAGIC + b"\x01\x00")
        with self.assertRaises(R.PatchError):
            R.vcdiff_decode(b"", R.VCDIFF_MAGIC + b"\x53\x01")

    def test_add_without_data_section(self):
        # addr 段非空 -> 不是内联模式，于是 ADD 必须去 data 段取字节，而 data 段是空的
        stream = self.build(0, 4, bytes([5]), addr=b"\x00")
        with self.assertRaises(R.PatchError):
            R.vcdiff_decode(b"", stream)


# ------------------------------------------------------------------ 真实补丁

@need_p1
class TestPatchHeader(unittest.TestCase):
    def test_patch1_header(self):
        hdr = R.parse_patch_header(read_patch(PATCH1))
        self.assertEqual(hdr["version"], 1)
        self.assertEqual(hdr["type"], 2)
        # @12 是**目标**长度：patch1 的产物 460.2 = 2,095,579,136 B
        self.assertEqual(hdr["target_size"], 2_095_579_136)
        self.assertEqual(hdr["info_len"], 163)
        self.assertEqual(hdr["info_hash"].hex(),
                         "37ac0818b9aba97146cff6b156f6ec8e")
        self.assertEqual(hdr["count"], 4310)
        self.assertEqual(hdr["info_patched"], 1)
        self.assertEqual(hdr["data_offset"], 48 + 163)

    @need_p2
    def test_patch2_header(self):
        hdr = R.parse_patch_header(read_patch(PATCH2))
        self.assertEqual(hdr["target_size"], 2_096_463_872)   # = 460.9 的长度
        self.assertEqual(hdr["info_len"], 427_125)
        self.assertEqual(hdr["count"], 4313)
        self.assertEqual(hdr["info_hash"].hex(), MD5_INFO_4602)
        self.assertEqual(hdr["data_offset"], 48 + 427_125)

    def test_rejects_bad_magic_version_type(self):
        good = read_patch(PATCH1)[:48]
        for off, val in ((0, b"XBSR"), (4, struct.pack("<I", 2)),
                         (8, struct.pack("<I", 3))):
            bad = bytearray(good)
            bad[off:off + len(val)] = val
            with self.assertRaises(R.PatchError):
                R.parse_patch_header(bytes(bad))

    def test_descriptor_walk_consumes_file_exactly(self):
        p = read_patch(PATCH1)
        hdr = R.parse_patch_header(p)
        with open(PATCH1, "rb") as f:
            packets = list(R.iter_descriptors(f, PATCH1, hdr))
        self.assertEqual(len(packets), 4310)
        last = packets[-1]
        self.assertEqual(last["payload_at"] + last["payload_len"], len(p),
                         "报文走完必须正好等于补丁长度")

    @need_p2
    def test_changed_packets(self):
        with open(PATCH1, "rb") as f:
            hdr = R.parse_patch_header(read_patch(PATCH1))
            p1 = [p for p in R.iter_descriptors(f, PATCH1, hdr) if p["type"]]
        self.assertEqual([(p["index"], p["name"], p["payload_len"]) for p in p1],
                         [(684, "PACKAGES", 2_030_916)])

        with open(PATCH2, "rb") as f:
            hdr2 = R.parse_patch_header(read_patch(PATCH2))
            p2 = [p for p in R.iter_descriptors(f, PATCH2, hdr2) if p["type"]]
        self.assertEqual(
            [(p["index"], p["name"], p["payload_len"], p["before_hash"].hex())
             for p in p2],
            [
                (378, "EffectElementReactionGroup_1536", 647_192, R.EMPTY_MD5.hex()),
                (379, "EffectElementReactionGroup_768", 217_112, R.EMPTY_MD5.hex()),
                (380, "EffectElementReactionGroup_Common", 16_408, R.EMPTY_MD5.hex()),
                (687, "PACKAGES", 1_341_981, MD5_PACKAGES_4602),
                (4168, "__MANIFESTGROUP__", 6_461_634,
                 "76c9b07360a1e9aa1cb72a1ad8d27d23"),
            ])


@need_p1
class TestInfoSection(unittest.TestCase):
    def test_source_info_hash_matches_patch(self):
        info = base_info()
        self.assertEqual(len(info), 4_767_744)
        self.assertEqual(md5b(info), "37ac0818b9aba97146cff6b156f6ec8e")

    def test_decode_info_patch1(self):
        hdr = R.parse_patch_header(read_patch(PATCH1))
        out = R.vcdiff_decode(base_info(), read_patch(PATCH1)[48:48 + hdr["info_len"]])
        self.assertEqual(len(out), 4_767_744)
        self.assertEqual(md5b(out), MD5_INFO_4602)
        self.assertEqual(out[:4], b"1bsr")
        hdr_new, recs = R.parse_info_section(out)
        self.assertEqual(len(recs), 4310)
        self.assertEqual(hdr_new[R.H_SUBGROUP_INFO_ENTRIES], 4310)

    @need_p2
    def test_decode_info_patch2(self):
        hdr1 = R.parse_patch_header(read_patch(PATCH1))
        info2 = R.vcdiff_decode(base_info(),
                                read_patch(PATCH1)[48:48 + hdr1["info_len"]])
        p2 = read_patch(PATCH2)
        hdr2 = R.parse_patch_header(p2)
        out = R.vcdiff_decode(info2, p2[48:48 + hdr2["info_len"]])
        self.assertEqual(len(out), 4_771_840)
        self.assertEqual(md5b(out), MD5_INFO_4609)
        _, recs = R.parse_info_section(out)
        self.assertEqual(len(recs), 4313)
        names = [r["name"] for r in recs]
        self.assertEqual(names[378], "EffectElementReactionGroup_1536")
        self.assertEqual(names[4168], "__MANIFESTGROUP__")

    def test_record_offsets_are_contiguous(self):
        """新表里的 offset 必须等于 HEADER_SIZE + 前面所有 size 之和。"""
        hdr = R.parse_patch_header(read_patch(PATCH1))
        out = R.vcdiff_decode(base_info(), read_patch(PATCH1)[48:48 + hdr["info_len"]])
        hdr_new, recs = R.parse_info_section(out)
        cur = hdr_new[R.H_HEADER_SIZE]
        for r in recs:
            self.assertEqual(r["offset"], cur, "记录 %d(%s) 偏移不连续"
                             % (r["index"], r["name"]))
            cur += r["size"]


@need_p1
class TestSinglePacketDecode(unittest.TestCase):
    """用真实报文对拍：源 subgroup 字节 + payload -> 新 subgroup 字节。"""

    def test_packages_patch1(self):
        src, rec = blob_of(BASE_OBB, "PACKAGES")
        self.assertEqual(len(src), 2_342_912)
        self.assertEqual(md5b(src), "4a80ca19a4eb49c943d4a3c6de080c22")

        hdr = R.parse_patch_header(read_patch(PATCH1))
        with open(PATCH1, "rb") as f:
            packets = list(R.iter_descriptors(f, PATCH1, hdr))
        pkt = [p for p in packets if p["name"] == "PACKAGES"][0]
        with open(PATCH1, "rb") as f:
            f.seek(pkt["payload_at"])
            payload = f.read(pkt["payload_len"])
        out = R.vcdiff_decode(src, payload)
        self.assertEqual(len(out), 2_342_912)
        self.assertEqual(md5b(out), MD5_PACKAGES_4602)

    @need_p2
    def test_packages_patch2_chained(self):
        src, _ = blob_of(BASE_OBB, "PACKAGES")
        p1 = read_patch(PATCH1)
        h1 = R.parse_patch_header(p1)
        with open(PATCH1, "rb") as f:
            pk1 = [p for p in R.iter_descriptors(f, PATCH1, h1)
                   if p["name"] == "PACKAGES"][0]
        with open(PATCH1, "rb") as f:
            f.seek(pk1["payload_at"])
            mid = R.vcdiff_decode(src, f.read(pk1["payload_len"]))
        self.assertEqual(md5b(mid), MD5_PACKAGES_4602)

        p2 = read_patch(PATCH2)
        h2 = R.parse_patch_header(p2)
        with open(PATCH2, "rb") as f:
            pk2 = [p for p in R.iter_descriptors(f, PATCH2, h2)
                   if p["name"] == "PACKAGES"][0]
        with open(PATCH2, "rb") as f:
            f.seek(pk2["payload_at"])
            out = R.vcdiff_decode(mid, f.read(pk2["payload_len"]))
        self.assertEqual(len(out), 2_342_912)
        self.assertEqual(md5b(out), MD5_PACKAGES_4609)

    @need_p2
    def test_new_subgroup_from_empty_source(self):
        """beforeHash 为 d41d8... 的报文：源是空 buffer。"""
        p2 = read_patch(PATCH2)
        h2 = R.parse_patch_header(p2)
        with open(PATCH2, "rb") as f:
            pk = [p for p in R.iter_descriptors(f, PATCH2, h2)
                  if p["name"] == "EffectElementReactionGroup_1536"][0]
        self.assertEqual(pk["before_hash"], R.EMPTY_MD5)
        with open(PATCH2, "rb") as f:
            f.seek(pk["payload_at"])
            out = R.vcdiff_decode(b"", f.read(pk["payload_len"]))
        self.assertEqual(len(out), 647_168)
        self.assertEqual(md5b(out), MD5_KERNEL_1536)


# ------------------------------------------------------------------ 错误路径

@need_p1
class TestErrorPaths(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="rsbpatch-test-")

    def tmp(self, name):
        return os.path.join(self.tmpdir, name)

    def test_info_href_mismatch(self):
        """改了补丁头里的 info-section 哈希 -> 明确报错。"""
        p = bytearray(read_patch(PATCH1))
        p[24] ^= 0xFF
        bad = self.tmp("bad-info-hash.rsbpatch")
        with open(bad, "wb") as f:
            f.write(p)
        out = self.tmp("nope.obb")
        with self.assertRaises(R.PatchError) as cm:
            R.apply_patch(BASE_OBB, bad, out)
        msg = str(cm.exception)
        self.assertIn("info-section 哈希不匹配", msg)
        self.assertIn("37ac0818", msg)          # 报出补丁要求的值
        self.assertFalse(os.path.exists(out))

    def test_packet_order_mismatch(self):
        """把前两条报文的名字互换 -> 报文顺序失配必须报错。"""
        p = bytearray(read_patch(PATCH1))
        hdr = R.parse_patch_header(bytes(p))
        pos = hdr["data_offset"]

        def name_at(off):
            return bytes(p[off + 8:off + 8 + R.NAME_SIZE])

        n0, l0 = name_at(pos), struct.unpack_from("<I", p, pos + 4)[0]
        pos1 = pos + R.DESCRIPTOR_SIZE + l0
        n1 = name_at(pos1)
        # 两个名字都 <= 128 B，直接换（长度不同就补零）
        def put(off, nm):
            p[off + 8:off + 8 + R.NAME_SIZE] = nm.ljust(R.NAME_SIZE, b"\0")
        put(pos, n1)
        put(pos1, n0)
        bad = self.tmp("bad-order.rsbpatch")
        with open(bad, "wb") as f:
            f.write(p)
        out = self.tmp("nope2.obb")
        with self.assertRaises(R.PatchError) as cm:
            R.apply_patch(BASE_OBB, bad, out)
        self.assertIn("报文顺序错乱", str(cm.exception))
        self.assertFalse(os.path.exists(out))

    def test_before_hash_mismatch(self):
        """改掉某条报文（未变的那条）的 beforeHash -> 源内容哈希不匹配。"""
        p = bytearray(read_patch(PATCH1))
        hdr = R.parse_patch_header(bytes(p))
        with open(PATCH1, "rb") as f:
            packets = list(R.iter_descriptors(f, PATCH1, hdr))
        target = packets[5]
        p[target["descriptor_at"] + 136] ^= 0xFF
        bad = self.tmp("bad-before.rsbpatch")
        with open(bad, "wb") as f:
            f.write(p)
        out = self.tmp("nope3.obb")
        with self.assertRaises(R.PatchError) as cm:
            R.apply_patch(BASE_OBB, bad, out)
        self.assertIn("源内容哈希不匹配", str(cm.exception))

    def test_truncated_patch(self):
        p = read_patch(PATCH1)[:-1]
        bad = self.tmp("trunc.rsbpatch")
        with open(bad, "wb") as f:
            f.write(p)
        with self.assertRaises(R.PatchError) as cm:
            R.apply_patch(BASE_OBB, bad, self.tmp("nope4.obb"))
        self.assertIn("截断", str(cm.exception))

    def test_source_not_1bsr(self):
        bad = self.tmp("notrsb.bin")
        with open(bad, "wb") as f:
            f.write(b"nope" * 64)
        with self.assertRaises(R.PatchError) as cm:
            R.apply_patch(bad, PATCH1, self.tmp("nope5.obb"))
        self.assertIn("1BSR", str(cm.exception))

    @classmethod
    def tearDownClass(cls):
        for n in os.listdir(cls.tmpdir):
            os.unlink(os.path.join(cls.tmpdir, n))
        os.rmdir(cls.tmpdir)


# ------------------------------------------------------------------ 成品

class TestProducts(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(OUT_4602), "缺 460.2.obb 成品")
    def test_4602_header_and_packages(self):
        info_md5 = hashlib.md5()
        with open(OUT_4602, "rb") as f:
            _, size = R.read_rsb_header(f, OUT_4602)
            f.seek(0)
            info_md5.update(f.read(size))
        self.assertEqual(info_md5.hexdigest(), MD5_INFO_4602)
        blob, rec = blob_of(OUT_4602, "PACKAGES")
        self.assertEqual(md5b(blob), MD5_PACKAGES_4602)

    @unittest.skipUnless(os.path.exists(OUT_4609), "缺 460.9.obb 成品")
    def test_4609_header_and_packages(self):
        info_md5 = hashlib.md5()
        with open(OUT_4609, "rb") as f:
            _, size = R.read_rsb_header(f, OUT_4609)
            f.seek(0)
            info_md5.update(f.read(size))
        self.assertEqual(info_md5.hexdigest(), MD5_INFO_4609)
        blob, _ = blob_of(OUT_4609, "PACKAGES")
        self.assertEqual(md5b(blob), MD5_PACKAGES_4609)

    @unittest.skipUnless(os.path.exists(OUT_4602) and os.path.exists(PATCH2),
                         "缺 460.2.obb 成品或补丁2")
    def test_next_patch_accepts_the_previous_product_header(self):
        """M1 跨跳互校：第 n 跳产物的头部 MD5 必须等于第 n+1 跳声明的 ``@24``。

        ``_cmd_chain`` 每跳落盘后就用这条等式，不通过立刻 raise（可用
        ``--no-cross-check`` 关）；这里把等式本身钉成用例，免得补丁链被替换后
        只能靠整链跑完才发现。
        """
        with open(PATCH2, "rb") as f:
            want = R.parse_patch_header(f.read(R.PATCH_HEADER_SIZE))["info_hash"]
        self.assertEqual(want.hex(), MD5_INFO_4602)
        self.assertEqual(R.header_md5(OUT_4602), want)
        # 反面：拿第一跳的声明去比第二跳的产物，必须不相等（防止等式恒真）。
        with open(PATCH1, "rb") as f:
            first = R.parse_patch_header(f.read(R.PATCH_HEADER_SIZE))["info_hash"]
        self.assertNotEqual(R.header_md5(OUT_4602), first)

    @unittest.skipUnless(os.environ.get("RSBPATCH_FULL"), "设 RSBPATCH_FULL=1 才跑整包 MD5")
    def test_full_md5(self):
        for path, want in ((OUT_4602, MD5_4602), (OUT_4609, MD5_4609)):
            if not os.path.exists(path):
                continue
            h = hashlib.md5()
            with open(path, "rb") as f:
                while True:
                    b = f.read(1 << 22)
                    if not b:
                        break
                    h.update(b)
            self.assertEqual(h.hexdigest(), want, path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
