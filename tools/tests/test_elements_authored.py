"""自创元素层的编译与契约测试。

运行::

    python -m unittest tools.tests.test_elements_authored -v
    python -m unittest discover -s tools/tests -p 'test_*.py'
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.contentc import elements_authored as ea  # noqa: E402

BASELINE = REPO / "game" / "engine" / "elements.py"

ELEMENTS = ["water", "fire", "ice", "thunder", "wind"]
REACTION_COUNT = 10
PAIRS = {
    frozenset(("water", "fire")),
    frozenset(("water", "ice")),
    frozenset(("water", "thunder")),
    frozenset(("water", "wind")),
    frozenset(("fire", "ice")),
    frozenset(("fire", "thunder")),
    frozenset(("fire", "wind")),
    frozenset(("ice", "thunder")),
    frozenset(("ice", "wind")),
    frozenset(("thunder", "wind")),
}


def run(out: Path, extra: list[str] | None = None) -> int:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return ea.main(
            [
                "--baseline",
                str(BASELINE),
                "--json",
                str(out / "elements.json"),
                "--report",
                str(out / "report.md"),
                *(extra or []),
            ]
        )


class ElementsAuthoredTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.assertEqual(run(self.tmp), 0)
        self.payload = json.loads((self.tmp / "elements.json").read_text(encoding="utf-8"))
        self.report = (self.tmp / "report.md").read_text(encoding="utf-8")

    def test_top_level_contract(self) -> None:
        self.assertEqual(self.payload["format"], 1)
        self.assertEqual(self.payload["source"], "authored")
        self.assertEqual(self.payload["note"], "not an original SHUTTLE mechanic")
        self.assertEqual(self.payload["marker"], "elements-authored-v1")

    def test_elements_match_baseline(self) -> None:
        baseline = ea.load_baseline(BASELINE)
        rows = self.payload["elements"]
        self.assertEqual([row["id"] for row in rows], list(baseline.ELEMENTS))
        self.assertEqual(len(rows), 5)
        for row in rows:
            self.assertEqual(row["name_zh"], baseline.ELEMENT_NAME[row["id"]])
            self.assertEqual(tuple(row["color"]), tuple(baseline.ELEMENT_COLOR[row["id"]]))
            self.assertEqual(row["attachSeconds"], baseline.ATTACH_SECONDS[row["id"]])

    def test_elements_are_authored(self) -> None:
        for row in self.payload["elements"]:
            self.assertEqual(row["source"], "authored")
            self.assertIn("ELEMENTS", row["rationale"])
            self.assertIn("ATTACH_SECONDS", row["rationale"])

    def test_reaction_pairs_and_canonical_order(self) -> None:
        rows = self.payload["reactions"]
        self.assertEqual(len(rows), REACTION_COUNT)
        self.assertEqual({frozenset((row["a"], row["b"])) for row in rows}, PAIRS)
        order = {eid: index for index, eid in enumerate(ELEMENTS)}
        for row in rows:
            self.assertLess(order[row["a"]], order[row["b"]], row)
            self.assertNotEqual(row["a"], row["b"])

    def test_reactions_are_authored(self) -> None:
        for row in self.payload["reactions"]:
            self.assertEqual(row["source"], "authored")
            self.assertIn("_REACTIONS", row["rationale"])
            self.assertIn(row["name_zh"], row["rationale"])

    def test_no_symmetric_duplicates(self) -> None:
        seen = set()
        for row in self.payload["reactions"]:
            pair = frozenset((row["a"], row["b"]))
            self.assertNotIn(pair, seen, f"反应对重复：{row['a']}+{row['b']}")
            seen.add(pair)

    def test_melt_keeps_directional_multiplier(self) -> None:
        rows = {frozenset((row["a"], row["b"])): row for row in self.payload["reactions"]}
        melt = rows[frozenset(("fire", "ice"))]
        self.assertEqual(melt["name_zh"], "融化")
        self.assertEqual(melt["mult"], 2.0)
        self.assertEqual(melt["clear"], ["ice"])
        self.assertEqual(
            melt["directional"],
            {"attack": "ice", "attached": "fire", "mult": 1.5},
        )

    def test_evaporation_and_thunder_effects(self) -> None:
        rows = {frozenset((row["a"], row["b"])): row for row in self.payload["reactions"]}
        vapor = rows[frozenset(("water", "fire"))]
        self.assertEqual((vapor["name_zh"], vapor["mult"], vapor["clear"]), ("蒸发", 2.0, ["fire"]))
        shock = rows[frozenset(("water", "thunder"))]
        aoe = shock["effects"][0]
        self.assertEqual(aoe["type"], "aoe")
        self.assertEqual(aoe["damage"], "attack")
        self.assertEqual(aoe["cap"], 1000.0)
        self.assertEqual(shock["clear"], ["water", "thunder"])
        superconduct = rows[frozenset(("ice", "thunder"))]
        self.assertEqual(superconduct["effects"][0], {"type": "vulnerable", "mult": 0.75, "seconds": 10.0})
        overload = rows[frozenset(("fire", "thunder"))]
        self.assertEqual(overload["effects"][0]["damage"], 40.0)

    def test_unknown_element_not_emitted(self) -> None:
        payload, skipped = ea.compile_payload(
            ELEMENTS,
            {eid: eid for eid in ELEMENTS},
            {eid: (1, 2, 3) for eid in ELEMENTS},
            {eid: 5.0 for eid in ELEMENTS},
            {
                frozenset(("water", "fire")): {"name": "蒸发", "mult": 2.0, "clear": ("fire",), "effects": []},
                frozenset(("water", "light")): {"name": "光爆", "mult": 9.0, "clear": (), "effects": []},
            },
        )
        ids = {row["id"] for row in payload["elements"]}
        self.assertNotIn("light", ids)
        self.assertEqual(len(payload["reactions"]), 1)
        self.assertEqual(len(skipped), 1)
        self.assertIn("light", skipped[0])

    def test_determinism(self) -> None:
        first_json = (self.tmp / "elements.json").read_bytes()
        first_report = (self.tmp / "report.md").read_bytes()
        self.assertEqual(run(self.tmp), 0)
        self.assertEqual((self.tmp / "elements.json").read_bytes(), first_json)
        self.assertEqual((self.tmp / "report.md").read_bytes(), first_report)

    def test_check_mode(self) -> None:
        self.assertEqual(run(self.tmp, ["--check"]), 0)
        (self.tmp / "elements.json").write_text("{}\n", encoding="utf-8")
        self.assertEqual(run(self.tmp, ["--check"]), 2)

    def test_missing_baseline_exits_2(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            code = ea.main(
                [
                    "--baseline",
                    str(self.tmp / "absent.py"),
                    "--json",
                    str(self.tmp / "x.json"),
                    "--report",
                    str(self.tmp / "x.md"),
                ]
            )
        self.assertEqual(code, 2)

    def test_dry_run_writes_nothing(self) -> None:
        out = self.tmp / "dry"
        self.assertEqual(run(out, ["-n"]), 0)
        self.assertFalse((out / "elements.json").exists())
        self.assertFalse((out / "report.md").exists())

    def test_report_states_evidence_and_scope(self) -> None:
        self.assertIn("ElementReactionModuleProperties", self.report)
        self.assertIn("21", self.report)
        self.assertIn("1075", self.report)
        self.assertIn("1809", self.report)
        self.assertIn("不计入原版复刻口径", self.report)
        self.assertIn("保留基线行为", self.report)
        self.assertIn("directional", self.report)
        self.assertIn("elements.json", self.report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
