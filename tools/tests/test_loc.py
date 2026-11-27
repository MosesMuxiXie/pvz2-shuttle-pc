"""``tools/contentc/loc.py`` 的回归测试（B6 本地化表）。

两类断言：

* **产物测试**：对仓库里已生成的 ``native/generated/lawn_strings.json`` 直接断言
  19055 键 / 19052 双语 / 3 个只有英文，以及两个逐字锚点
  （``ELEMENT_7_WAVEMASSAGE`` 中文、``ACHIEVE_ALL_IN_JEST_TITLE`` = 向我开炮）。
  这是"表真的在那儿"的唯一硬证据：机械转写会给出 ``All In Jest``，两者不同。
* **夹具测试**：在临时目录里造小表，钉住 ``build()`` 的单侧计数、空值、
  行尾归一、``read_pairs()`` 的报错，以及 ``--check`` 的"缺失/过期返回 2"。

跑法::

    python -m unittest tools.tests.test_loc
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "contentc"))

import loc as L  # noqa: E402

GENERATED = ROOT / "native" / "generated" / "lawn_strings.json"
REPORT = ROOT / "docs" / "reviews" / "2026-11-26-lawn-strings.md"

_DOC: dict | None = None
_BYTES: bytes | None = None


def generated_bytes() -> bytes:
    """产物原始字节（2.9 MB，读一次复用）。"""
    global _BYTES
    if _BYTES is None:
        _BYTES = GENERATED.read_bytes()
    return _BYTES


def generated_doc() -> dict:
    global _DOC
    if _DOC is None:
        _DOC = json.loads(generated_bytes().decode("utf-8"))
    return _DOC


_INVENTORY: L.Inventory | None = None


def real_inventory() -> L.Inventory:
    """从两包原始表重算一次（两次 1.9 MB JSON，只在需要重算的用例里用）。"""
    global _INVENTORY
    if _INVENTORY is None:
        _INVENTORY = L.build(L.read_pairs(L.DEFAULT_EN), L.read_pairs(L.DEFAULT_ZH))
    return _INVENTORY


def run_main(argv: list[str]) -> tuple[int, str, str]:
    """跑 ``main()``，把两个流抓回来（测试输出里不该混进脚本的打印）。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = L.main(argv)
    return code, out.getvalue(), err.getvalue()


def sheet(values: list[str]) -> str:
    """一包最小的 LawnStrings JSON。"""
    return json.dumps(
        {
            "version": 1,
            "objects": [
                {
                    "objclass": "LawnStringsData",
                    "aliases": ["LawnStringsData"],
                    "objdata": {"LocStringValues": values},
                }
            ],
        },
        ensure_ascii=False,
    )


# --------------------------------------------------------------------------- #
# 产物
# --------------------------------------------------------------------------- #


class ShippedTableTest(unittest.TestCase):
    def test_counts_are_the_sheet_numbers(self) -> None:
        counts = generated_doc()["counts"]
        self.assertEqual(counts["keys"], 19055)
        self.assertEqual(counts["both"], 19052)
        self.assertEqual(counts["enOnly"], 3)
        self.assertEqual(counts["zhOnly"], 0)
        self.assertEqual(sum(counts[key] for key in ("both", "enOnly", "zhOnly")), counts["keys"])

    def test_row_count_matches_the_map(self) -> None:
        document = generated_doc()
        self.assertEqual(len(document["strings"]), document["counts"]["keys"])

    def test_element_wave_message_is_verbatim_on_both_sides(self) -> None:
        row = generated_doc()["strings"]["ELEMENT_7_WAVEMASSAGE"]
        self.assertEqual(row["en"], "The resentment of the dead makes you tremble!")
        self.assertEqual(row["zh"], "亡魂的怨念令你们震颤！")

    def test_achievement_title_beats_the_mechanical_transcription(self) -> None:
        # humanizeGameKey("ACHIEVE_ALL_IN_JEST_TITLE") == "All In Jest"；原表给的是中文标题。
        row = generated_doc()["strings"]["ACHIEVE_ALL_IN_JEST_TITLE"]
        self.assertEqual(row["zh"], "向我开炮")
        self.assertEqual(row["en"], "All in Jest")
        self.assertNotEqual(row["zh"], "All In Jest")

    def test_dirty_keys_survive_verbatim(self) -> None:
        # 原表有 10 个不合 [A-Z0-9_.-] 的键，一律不许清洗。
        strings = generated_doc()["strings"]
        for key in ("#OF#", "BF23_GOLD BLOOM_UNLOCK", "FF23_ULTIMATE_GEMS_ PACK",
                    "EPICQUEST_BUFFZ&BRUISEZ01_DESC"):
            self.assertIn(key, strings)
        self.assertIn("unlock", strings["BF23_GOLD BLOOM_UNLOCK"]["en"].lower())

    def test_duplicate_narrative_keys_keep_the_first_line(self) -> None:
        document = generated_doc()
        duplicates = [item for item in document["unknowns"] if item["kind"] == "duplicate-key"]
        self.assertEqual(len(duplicates), 2)
        self.assertEqual(
            {item["key"] for item in duplicates},
            {"NARRATIVE_ATLANTIS_17_INTRO_1", "NARRATIVE_ATLANTIS_17_INTRO_2"},
        )
        for item in duplicates:
            # 每个 key 在两张表里各出现两次（第一次进表，第二次留在 dropped），
            # occurrences 必须等于出现次数——多算一次会让报告与 JSON 互相打架。
            self.assertEqual(item["occurrences"]["en"], 2)
            self.assertEqual(item["occurrences"]["zh"], 2)
            self.assertEqual(len(item["dropped"]["en"]), 1)
            self.assertEqual(len(item["dropped"]["zh"]), 1)
            self.assertIn(item["key"], document["strings"])
            self.assertTrue(item["dropped"]["en"])

    def test_one_sided_keys_are_counted_and_explained(self) -> None:
        document = generated_doc()
        one_sided = [item for item in document["unknowns"] if item["kind"] == "one-sided"]
        self.assertEqual(len(one_sided), 3)
        self.assertEqual({item["side"] for item in one_sided}, {"en"})
        self.assertEqual(
            {item["key"] for item in one_sided},
            {
                "NARRATIVE_GTA_1_INTRO_18",
                "NARRATIVE_GTA_1_INTRO_19",
                "NARRATIVE_GTA_6_INTRO_7",
            },
        )
        for item in one_sided:
            row = document["strings"][item["key"]]
            self.assertEqual(row["zh"], "")
            self.assertEqual(row["en"], item["text"])

    def test_table_is_one_line_and_has_no_carriage_returns(self) -> None:
        data = generated_bytes()
        self.assertNotIn(b"\r", data)
        self.assertEqual(data.count(b"\n"), 1)
        self.assertTrue(data.endswith(b"\n"))

    def test_stamp_is_content_addressed(self) -> None:
        stamp = generated_doc()["generated"]
        self.assertTrue(stamp.startswith("sha256:"))
        digest = stamp.split(":", 1)[1]
        self.assertEqual(len(digest), 16)
        int(digest, 16)  # 必须是 16 个十六进制字符

        body = {
            "counts": generated_doc()["counts"],
            "strings": generated_doc()["strings"],
            "unknowns": generated_doc()["unknowns"],
        }
        self.assertEqual(L.stamp(body), stamp)  # 只由内容决定
        other = dict(body, counts=dict(body["counts"], keys=body["counts"]["keys"] + 1))
        self.assertNotEqual(L.stamp(other), stamp)  # 内容一变戳就变

    def test_rebuild_reproduces_the_shipped_bytes(self) -> None:
        inventory = real_inventory()
        self.assertEqual(inventory.counts["keys"], 19055)
        self.assertEqual(inventory.normalised, 682)  # 含 CR 的值
        rebuilt = L.render_json(inventory)
        self.assertEqual(rebuilt.encode("utf-8"), generated_bytes())
        self.assertEqual(
            hashlib.sha256(rebuilt.encode("utf-8")).hexdigest(),
            hashlib.sha256(generated_bytes()).hexdigest(),
        )

    def test_suffix_classes_cover_the_table(self) -> None:
        inventory = real_inventory()
        self.assertEqual(inventory.suffix_counts["TITLE"], 792)
        self.assertEqual(inventory.suffix_counts["DESC"], 1108)
        self.assertEqual(inventory.suffix_counts["HINT"], 30)
        self.assertEqual(sum(inventory.suffix_counts.values()), inventory.counts["keys"])


# --------------------------------------------------------------------------- #
# --check
# --------------------------------------------------------------------------- #


class CheckTest(unittest.TestCase):
    def test_check_passes_on_the_shipped_files(self) -> None:
        code, out, err = run_main(["--check"])
        self.assertEqual(code, 0, err)
        self.assertIn("[ok]", out or err)

    def test_check_notices_a_stale_table(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            table = temp / "lawn_strings.json"
            report = temp / "report.md"
            table.write_bytes(generated_bytes())
            report.write_bytes(REPORT.read_bytes())

            # 先确认这对临时副本是"最新"的，否则下面那半截断言没有意义。
            code, _, err = run_main(["--check", "--json", str(table), "--report", str(report)])
            self.assertEqual(code, 0, err)

            document = json.loads(table.read_text(encoding="utf-8"))
            document["strings"]["ELEMENT_7_WAVEMASSAGE"]["zh"] = "改了"
            table.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            code, _, err = run_main(["--check", "--json", str(table), "--report", str(report)])
            self.assertEqual(code, 2)
            self.assertIn("stale", err)

    def test_check_notices_a_missing_table(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            code, _, err = run_main(
                ["--check", "--json", str(temp / "nope.json"), "--report", str(temp / "nope.md")]
            )
            self.assertEqual(code, 2)
            self.assertIn("missing", err)

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            code, out, _ = run_main(["-n", "--json", str(temp / "x.json"),
                                     "--report", str(temp / "x.md")])
            self.assertEqual(code, 0)
            self.assertIn("dry run", out)
            self.assertFalse((temp / "x.json").exists())
            self.assertFalse((temp / "x.md").exists())


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #


class FixtureTest(unittest.TestCase):
    def test_build_counts_both_sides_and_blanks(self) -> None:
        en = [("BOTH_TITLE", "English"), ("EN_ONLY_DESC", "Only English"),
              ("BLANK_TITLE", "   "), ("CRLF_DESC", "one\r\ntwo")]
        zh = [("BOTH_TITLE", "中文"), ("ZH_ONLY_TITLE", "只有中文"),
              ("BLANK_TITLE", ""), ("CRLF_DESC", "一\r\n二")]
        inventory = L.build(en, zh)

        self.assertEqual(inventory.counts["keys"], 5)
        self.assertEqual(inventory.counts["both"], 3)  # BOTH / BLANK / CRLF
        self.assertEqual(inventory.counts["enOnly"], 1)
        self.assertEqual(inventory.counts["zhOnly"], 1)
        self.assertEqual(inventory.en_only, ["EN_ONLY_DESC"])
        self.assertEqual(inventory.zh_only, ["ZH_ONLY_TITLE"])
        self.assertEqual(inventory.empty_en, ["BLANK_TITLE"])
        self.assertEqual(inventory.empty_zh, ["BLANK_TITLE"])
        self.assertEqual(inventory.normalised, 2)  # en 与 zh 各一条含 CRLF
        self.assertEqual(inventory.strings["CRLF_DESC"], {"en": "one\ntwo", "zh": "一\n二"})
        self.assertEqual(inventory.strings["ZH_ONLY_TITLE"]["en"], "")

    def test_build_keeps_the_first_duplicate_and_reports_it(self) -> None:
        inventory = L.build([("DUP_TITLE", "first"), ("DUP_TITLE", "second")], [])
        self.assertEqual(inventory.strings["DUP_TITLE"]["en"], "first")
        self.assertEqual(inventory.duplicates["DUP_TITLE"]["en"], ["first", "second"])
        kinds = [item["kind"] for item in inventory.unknowns]
        self.assertIn("duplicate-key", kinds)
        duplicate = [item for item in inventory.unknowns if item["kind"] == "duplicate-key"][0]
        self.assertEqual(duplicate["occurrences"], {"en": 2})
        self.assertEqual(duplicate["kept"], {"en": "first"})
        self.assertEqual(duplicate["dropped"], {"en": ["second"]})

    def test_build_flags_keys_outside_the_expected_shape(self) -> None:
        inventory = L.build([("BAD KEY", "x"), ("GOOD_TITLE", "y")], [])
        self.assertEqual(inventory.dirty_keys, ["BAD KEY"])
        shape = [item for item in inventory.unknowns if item["kind"] == "key-shape"]
        self.assertEqual(len(shape), 1)
        self.assertEqual(shape[0]["keys"], ["BAD KEY"])

    def test_classify_uses_the_suffix_table(self) -> None:
        self.assertEqual(L.classify("ACHIEVE_ALL_IN_JEST_TITLE"), "TITLE")
        self.assertEqual(L.classify("ACCOUNT_LINK_DESCRIPTION"), "DESCRIPTION")
        self.assertEqual(L.classify("PLANTFOOD_DESC"), "DESC")
        self.assertEqual(L.classify("SOMETHING_HINT"), "HINT")
        self.assertEqual(L.classify("WHATEVER"), "<other>")
        # 后缀只认结尾：ALOE_DESCRIPTION_PLANTFOOD 以 _PLANTFOOD 收尾，所以是 <other>。
        self.assertEqual(L.classify("ALOE_DESCRIPTION_PLANTFOOD"), "<other>")

    def test_read_pairs_reads_a_sheet_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "sheet.json"
            path.write_text(sheet(["A_TITLE", "a", "B_DESC", "b"]), encoding="utf-8")
            self.assertEqual(L.read_pairs(path), [("A_TITLE", "a"), ("B_DESC", "b")])

    def test_read_pairs_rejects_malformed_sheets(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            odd = temp / "odd.json"
            odd.write_text(sheet(["A_TITLE", "a", "B_DESC"]), encoding="utf-8")
            with self.assertRaises(SystemExit) as caught:
                L.read_pairs(odd)
            self.assertIn("even", str(caught.exception))

            broken = temp / "broken.json"
            broken.write_text("{not json", encoding="utf-8")
            with self.assertRaises(SystemExit):
                L.read_pairs(broken)

            shaped = temp / "shaped.json"
            shaped.write_text('{"objects":[{"objdata":{}}]}', encoding="utf-8")
            with self.assertRaises(SystemExit) as caught:
                L.read_pairs(shaped)
            self.assertIn("LocStringValues", str(caught.exception))

            missing = temp / "missing.json"
            with self.assertRaises(SystemExit) as caught:
                L.read_pairs(missing)
            self.assertIn("missing", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
