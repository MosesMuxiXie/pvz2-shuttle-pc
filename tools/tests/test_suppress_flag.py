"""Tests for the ``extra.suppressFlagZombie`` content flag (T65).

The flag comes from the original ``WaveManagerProperties`` object
(``SuppressFlagZombie``) and is cross-checked against the independently compiled
``native/generated/patch_460_9.json`` table, so "two sources agree" is an
assertion rather than a hope.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools import obb_build_content_v2 as builder  # noqa: E402
from tools.contentc import rails  # noqa: E402

LEVELS = REPO / "content" / "levels"
PATCH = REPO / "native" / "generated" / "patch_460_9.json"
KEY = "suppressFlagZombie"

TOTAL = 271
TRUE_COUNT = 215
FALSE_COUNT = 56
LEVEL_COUNT = 1809


def _requires_obb() -> None:
    root = builder.obb_dir()
    if not root.is_dir() or not any(root.glob("pkg_*_LevelDefinition.json")):
        raise unittest.SkipTest(f"original tables missing: {root}")


class DerivedFactsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _requires_obb()
        cls.facts = builder.load_rail_facts()

    def test_counts_and_distribution(self) -> None:
        values = [row.get(KEY) for row in self.facts.values()]
        present = [value for value in values if value is not None]
        self.assertEqual(len(self.facts), LEVEL_COUNT)
        self.assertEqual(len(present), TOTAL)
        self.assertEqual(sum(1 for value in present if value), TRUE_COUNT)
        self.assertEqual(sum(1 for value in present if not value), FALSE_COUNT)

    def test_the_flag_only_comes_from_wave_manager_properties(self) -> None:
        # One object per package, always on WaveManagerProperties: prove it on a
        # package the patch table also lists.
        doc = json.loads((builder.obb_dir() / "pkg_0416_LevelDefinition.json")
                         .read_text(encoding="utf-8-sig"))
        holders = [obj.get("objclass") for obj in doc.get("objects") or []
                   if builder.SUPPRESS_FIELD in (obj.get("objdata") or {})]
        self.assertEqual(holders, ["WaveManagerProperties"])
        self.assertIs(self.facts["pkg_0416"][KEY], True)

    def test_matches_the_compiled_patch_table(self) -> None:
        derived = {package: row[KEY] for package, row in self.facts.items()
                   if row.get(KEY) is not None}
        reference = builder.load_patch_suppress()
        self.assertEqual(len(reference), TOTAL)
        self.assertEqual(derived, reference)
        self.assertEqual(builder.crosscheck_suppress(self.facts), [])

    def test_missing_field_stays_absent_in_derive(self) -> None:
        self.assertEqual(builder.derive_flags({}), {})
        self.assertNotIn(KEY, builder.derive_flags({"modules": [], "rail": False,
                                                    KEY: None}))
        self.assertEqual(builder.derive_flags({KEY: False})[KEY], False)
        self.assertEqual(builder.derive_flags({KEY: True})[KEY], True)


class ContentLevelsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.with_key: dict[str, dict] = {}
        cls.without: list[str] = []
        for path in sorted(LEVELS.glob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            extra = doc.get("extra") or {}
            if KEY in extra:
                cls.with_key[doc["id"]] = doc
            else:
                cls.without.append(doc["id"])

    def test_every_affected_level_carries_the_key(self) -> None:
        self.assertEqual(len(self.with_key), TOTAL)
        self.assertEqual(len(self.without), LEVEL_COUNT - TOTAL)
        true_count = sum(1 for doc in self.with_key.values()
                         if doc["extra"][KEY] is True)
        false_count = sum(1 for doc in self.with_key.values()
                          if doc["extra"][KEY] is False)
        self.assertEqual((true_count, false_count), (TRUE_COUNT, FALSE_COUNT))

    def test_packages_and_ids_agree_with_the_patch_table(self) -> None:
        reference = {row["package"]: row["levelId"]
                     for row in json.loads(PATCH.read_text(encoding="utf-8"))["levelFlags"]}
        seen: dict[str, str] = {}
        for level_id, doc in self.with_key.items():
            package = doc["extra"]["package"]
            self.assertEqual(reference.get(package), level_id, package)
            seen[package] = level_id
        self.assertEqual(len(seen), TOTAL)
        self.assertEqual(seen, reference)

    def test_files_keep_the_builder_formatting(self) -> None:
        for level_id, doc in self.with_key.items():
            text = (LEVELS / f"{level_id}.json").read_text(encoding="utf-8")
            self.assertEqual(json.dumps(doc, ensure_ascii=False, indent=1), text,
                             level_id)

    def test_unaffected_levels_have_no_key(self) -> None:
        for level_id in self.without[:200]:
            doc = json.loads((LEVELS / f"{level_id}.json").read_text(encoding="utf-8"))
            self.assertNotIn(KEY, doc.get("extra") or {}, level_id)


class ReportTest(unittest.TestCase):
    def test_report_is_clean(self) -> None:
        _requires_obb()
        counts, mismatches = builder.content_flag_report()
        self.assertEqual(mismatches, [])
        self.assertEqual(counts["levels"], LEVEL_COUNT)
        self.assertEqual(counts["suppressFlag"], TOTAL)
        self.assertEqual(counts["suppressFlagTrue"], TRUE_COUNT)
        self.assertEqual(counts["suppressFlagFalse"], FALSE_COUNT)
        self.assertEqual(counts["derivedSuppressFlag"], TOTAL)
        self.assertEqual(counts["derivedSuppressFlagTrue"], TRUE_COUNT)

    def test_report_notices_a_stripped_key(self) -> None:
        _requires_obb()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "carnival_22.json"
            shutil.copy2(LEVELS / "carnival_22.json", target)
            doc = json.loads(target.read_text(encoding="utf-8"))
            doc["extra"].pop(KEY)
            target.write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                              encoding="utf-8", newline="\n")
            counts, mismatches = builder.content_flag_report(levels_dir=Path(tmp))
            self.assertEqual(counts["suppressFlag"], 0)
            self.assertTrue(any("carnival_22" in line and KEY in line
                                for line in mismatches), mismatches)

    def test_crosscheck_flags_a_wrong_value(self) -> None:
        _requires_obb()
        facts = dict(builder.load_rail_facts())
        package = next(pkg for pkg, row in facts.items() if row.get(KEY) is True)
        facts[package] = dict(facts[package], **{KEY: False})
        diffs = builder.crosscheck_suppress(facts)
        self.assertTrue(any(package in line for line in diffs), diffs)


class BuilderEmitTest(unittest.TestCase):
    """The derivation must reach the JSON the builder writes, not just the report."""

    def test_build_levels_emits_the_flag(self) -> None:
        _requires_obb()
        facts = builder.load_rail_facts()
        builder.setup_tables()
        zh, en = builder.base.collect_strings()
        grouped, _unknown, _special, _stats = builder.build_levels(zh, en,
                                                                   rail_table=facts)
        levels = [level for world in grouped.values() for level in world]
        self.assertEqual(len(levels), LEVEL_COUNT)
        values = [level["extra"][KEY] for level in levels
                  if KEY in (level.get("extra") or {})]
        self.assertEqual(len(values), TOTAL)
        self.assertEqual(sum(1 for value in values if value), TRUE_COUNT)
        self.assertEqual(sum(1 for value in values if not value), FALSE_COUNT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
