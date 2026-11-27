"""`tools/contentc/mechanic_entity_resolution.py` 的回归测试（A9 取证）。

三类断言：

* **产物测试**：对仓库里已生成的 `native/generated/mechanic_entity_resolution.json`
  直接断言三个结论——spider 23 个名字全落 ZombieType 表、fish 7 个生物全落 CreatureType 表、
  unscheduled 五类 21/17/1/22/64 条全部落在 `orphan` 档。
* **交叉核对**：把产物里的 `clientId` 值真的拿去查 `pkg_2115_ZombieType.json` /
  `pkg_0013_CreatureType.json`，以及把 `sampleLevels` 拿去和 `level_mechanics.json` 对账。
  这样产物不能靠自洽骗过测试。
* **`--check` 与编码**：缺失/过期返回 2、产物无 CRLF、`generated` 戳是内容寻址的。

跑法::

    python -m unittest tools.tests.test_mechanic_entity_resolution
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

import mechanic_entity_resolution as M  # noqa: E402

JSON_PATH = ROOT / "native" / "generated" / "mechanic_entity_resolution.json"
REPORT_PATH = ROOT / "docs" / "reviews" / "2026-11-26-mechanic-entity-resolution.md"
MECHANICS_PATH = ROOT / "native" / "generated" / "level_mechanics.json"

# 派单给的数字（按记录计）。
EXPECTED_HITS = {"grid": 21, "portal": 17, "storm": 1, "ground": 22, "dino": 64}


def load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def quiet(func, argv):
    """吞掉被测函数打到 stdout/stderr 的话，只留返回码。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = func(argv)
    return code, out.getvalue(), err.getvalue()


class ShippedDocumentTest(unittest.TestCase):
    """已生成产物的形状与三个结论。"""

    @classmethod
    def setUpClass(cls):
        cls.doc = load(JSON_PATH)

    def test_top_level_shape(self):
        for key in ("generated", "spider", "fish", "unscheduled", "search", "tables", "notes"):
            self.assertIn(key, self.doc)
        stamp = self.doc["generated"]
        self.assertTrue(stamp.startswith("sha256:"), stamp)
        self.assertEqual(len(stamp), len("sha256:") + 16, stamp)
        self.assertTrue(all(c in "0123456789abcdef" for c in stamp[7:]), stamp)

    def test_stamp_is_content_addressed(self):
        body = {k: v for k, v in self.doc.items() if k != "generated"}
        digest = hashlib.sha256(
            json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
        self.assertEqual(self.doc["generated"], "sha256:" + digest)

    def test_spider_exists_with_evidence(self):
        spider = self.doc["spider"]
        self.assertIs(spider["exists"], True)
        self.assertGreaterEqual(len(spider["evidence"]), 3)
        for item in spider["evidence"]:
            self.assertTrue(item.get("claim"))
            self.assertTrue(item.get("detail"))
            self.assertIsInstance(item.get("count"), int)
        self.assertEqual(spider["summary"]["objects"], 322)
        self.assertEqual(spider["summary"]["packs"], 119)
        self.assertEqual(spider["summary"]["distinctNames"], 23)
        self.assertEqual(spider["summary"]["unresolvedNames"], 0)

    def test_spider_client_ids_all_exist_in_zombie_type_table(self):
        """把产物的 clientId 真的拿去查 pkg_2115，而不是信它自己写的 resolved=0。"""
        table = ROOT.parent.parent / "work" / "obb_packages" / "pkg_2115_ZombieType.json"
        if not table.is_file():
            self.skipTest("pkg_2115_ZombieType.json is not available")
        aliases: set[str] = set()
        for _cls, names, objdata in M.iter_objects(load(table)):
            aliases.update(name for name in names if name)
            if isinstance(objdata.get("TypeName"), str):
                aliases.add(objdata["TypeName"])
        values = self.doc["spider"]["clientId"]["values"]
        self.assertEqual(len(values), 23)
        missing = sorted(name for name in values if name not in aliases)
        self.assertEqual(missing, [], "spider clientIds missing from ZombieType: %s" % missing)
        self.assertEqual(self.doc["spider"]["clientId"]["unresolved"], [])

    def test_fish_client_ids_all_exist_in_creature_type_table(self):
        names = set(self.doc["tables"]["creatureType"]["names"])
        fish = self.doc["fish"]
        self.assertIs(fish["exists"], True)
        values = fish["clientId"]["values"]
        self.assertEqual(sorted(values), sorted(
            ["hermitcrab", "inkfish", "jellyfish", "krill", "pufferfish", "starfish", "swordfish"]))
        self.assertEqual(sorted(name for name in values if name not in names), [])
        self.assertEqual(fish["clientId"]["unresolved"], [])

    def test_fish_creature_table_carries_art_bindings(self):
        table = self.doc["fish"]["clientId"]["creatureTable"]
        for name in self.doc["fish"]["clientId"]["values"]:
            entry = table[name]
            self.assertTrue(entry["popAnim"].startswith("POPANIM_"), (name, entry["popAnim"]))
            self.assertIn("PropertySheets", entry["properties"], (name, entry["properties"]))
            self.assertTrue(entry["creatureClass"])
            self.assertTrue(entry["animRigClass"])

    def test_unscheduled_hits_match_the_assignment(self):
        unsched = self.doc["unscheduled"]
        self.assertEqual(sorted(unsched), sorted(EXPECTED_HITS))
        actual = {kind: entry["hits"] for kind, entry in unsched.items()}
        self.assertEqual(actual, EXPECTED_HITS)
        self.assertEqual(sum(actual.values()), 125)

    def test_every_unscheduled_record_is_an_orphan(self):
        for kind, entry in self.doc["unscheduled"].items():
            with self.subTest(kind=kind):
                self.assertEqual(entry["buckets"],
                                 {"in-waves": 0, "digitless": 0, "orphan": entry["hits"]})
                self.assertLessEqual(entry["hits"], entry["records"])
                self.assertGreater(entry["distinctAliases"], 0)
                self.assertTrue(entry["aliases"])
                self.assertTrue(all(alias for alias in entry["aliases"]))

    def test_unscheduled_wave_fields_are_not_wave_indices(self):
        """原表里带 wave 字样的字段必须是提示文案/时长/空串，不能是波号。"""
        allowed = {"WaveStartMessage", "DinoWaveDuration", "Waves"}
        for kind, entry in self.doc["unscheduled"].items():
            with self.subTest(kind=kind):
                for name in entry["waveFieldNames"]:
                    self.assertIn(name, allowed, (kind, name))
                    self.assertNotEqual(name.lower(), "wave")
                    self.assertNotIn("number", name.lower())
        self.assertEqual(self.doc["unscheduled"]["portal"]["waveFieldNames"], [])

    def test_sample_levels_carry_the_raw_module(self):
        for kind, entry in self.doc["unscheduled"].items():
            with self.subTest(kind=kind):
                samples = entry["sampleLevels"]
                self.assertGreaterEqual(len(samples), 1)
                self.assertLessEqual(len(samples), M.SAMPLES_PER_KIND)
                for sample in samples:
                    self.assertTrue(sample["package"].endswith(".json"), sample["package"])
                    self.assertTrue(sample["alias"])
                    self.assertEqual(sample["bucket"], "orphan")
                    self.assertIsInstance(sample["raw"], dict)
                    self.assertTrue(sample["raw"], "raw objdata is empty: %s" % sample["level"])

    def test_sample_levels_reconcile_with_level_mechanics(self):
        mechanics = load(MECHANICS_PATH)
        levels = mechanics["levels"]
        for kind, entry in self.doc["unscheduled"].items():
            objclass = entry["objclass"]
            self.assertEqual(M.UNSCHEDULED_KINDS[kind], objclass)
            for sample in entry["sampleLevels"]:
                level = sample["level"]
                self.assertIn(level, levels)
                rows = (levels[level].get("spawners") or {}).get(kind) or []
                match = [row for row in rows if row.get("alias") == sample["alias"]]
                self.assertTrue(match, "%s/%s alias %s missing from mechanics"
                                % (kind, level, sample["alias"]))
                self.assertIn(match[0].get("wave"), (None, ""),
                              "%s/%s alias %s is scheduled after all"
                              % (kind, level, sample["alias"]))


class CheckTest(unittest.TestCase):
    """`--check` 的三条路径与产物编码。"""

    def test_check_passes_on_shipped_artifacts(self):
        code, out, _err = quiet(M.main, ["--check"])
        self.assertEqual(code, 0, out)
        self.assertIn("[ok]", out)

    def test_check_detects_a_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _out, err = quiet(M.main, [
                "--check", "--json", str(Path(tmp) / "missing.json"),
                "--report", str(REPORT_PATH)])
            self.assertEqual(code, 2)
            self.assertIn("missing", err)

    def test_check_detects_a_stale_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "stale.json"
            stale.write_text('{"generated":"sha256:0000000000000000"}\n', encoding="utf-8")
            code, _out, err = quiet(M.main, [
                "--check", "--json", str(stale), "--report", str(REPORT_PATH)])
            self.assertEqual(code, 2)
            self.assertIn("stale", err)

    def test_artifacts_have_no_crlf(self):
        for path in (JSON_PATH, REPORT_PATH):
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                self.assertNotIn(b"\r", raw)
                self.assertTrue(raw.endswith(b"\n"))
        raw = JSON_PATH.read_bytes()
        self.assertEqual(raw.count(b"\n"), 1, "JSON should be a single compact line")


class GuardTest(unittest.TestCase):
    """两条容易回退的口径。"""

    def test_notes_explain_the_client_table_gap(self):
        doc = load(JSON_PATH)
        joined = " ".join(doc["notes"])
        self.assertIn("content/zombies.json", joined)
        self.assertIn("55", joined)
        self.assertEqual(doc["tables"]["clientZombies"]["ids"], 55)

    def test_search_matrix_covers_both_paths(self):
        doc = load(JSON_PATH)
        for group, terms in M.SEARCH_TERMS.items():
            self.assertEqual([row["term"] for row in doc["search"][group]], list(terms))
        for row in doc["search"]["spider"]:
            self.assertIsInstance(row["objclassObjects"], int)
            self.assertIsInstance(row["fieldObjects"], int)
        # 既然没有 spider 实体，类名命中只能来自 Action/Designer 这类动作类。
        spider_classes = set()
        for row in doc["search"]["spider"]:
            spider_classes.update(row["objclasses"])
        self.assertTrue(spider_classes)
        for name in spider_classes:
            self.assertFalse(name.endswith("ZombieType"), name)


if __name__ == "__main__":
    unittest.main()

# A fresh clone has no pack tree (it lives outside the repository), so the shipped
# document cannot be re-rendered here. Skip instead of erroring, like the other
# content compilers' tests.
if not (M.DEFAULT_OBB / "pkg_2115_ZombieType.json").is_file():
    import unittest as _unittest

    _WHY = "缺少原版表目录 {}（设 PVZ2_OBB_DIR）".format(M.DEFAULT_OBB)
    for _name, _obj in list(globals().items()):
        if isinstance(_obj, type) and issubclass(_obj, _unittest.TestCase):
            setattr(_obj, "__unittest_skip__", True)
            setattr(_obj, "__unittest_skip_why__", _WHY)
