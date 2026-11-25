"""Pins the world diff and the world-gate export to the shipped data.

The numbers here come from `pkg_2107_WorldData.json`; if a future extract changes
them the test fails instead of the diff silently drifting.

Run:
    python -m unittest tools.tests.test_worlds -v
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import contentc.worlds as worlds  # noqa: E402

OBB = worlds.DEFAULT_OBB
CONTENT = worlds.DEFAULT_CONTENT
GATES = worlds.DEFAULT_GATES


@unittest.skipUnless((OBB / "pkg_2107_WorldData.json").exists(), "shipped sheets not available")
class WorldDiffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.obb = worlds.load_obb_worlds(OBB)
        cls.content = worlds.load_content_worlds(CONTENT)
        cls.result = worlds.diff(cls.obb, cls.content)

    def test_world_counts(self) -> None:
        self.assertEqual(len(self.obb), 46)
        self.assertEqual(len(self.content), 26)

    def test_match_sets(self) -> None:
        self.assertEqual(len(self.result["matched"]), 22)
        self.assertEqual(
            sorted(world.id for world in self.result["unmatched_content"]),
            ["frontyard", "future", "iceage", "renai"],
        )

    def test_event_totals(self) -> None:
        totals = self.result["event_totals"]
        self.assertEqual(totals["level"], 1248)
        self.assertEqual(totals["star_gate"], 53)
        self.assertEqual(totals["key_gate"], 27)
        self.assertEqual(totals["worldgate"], 17)
        self.assertEqual(totals["plant"], 231)

    def test_named_worlds(self) -> None:
        by_name = {world.name: world for world in self.obb}
        self.assertEqual(by_name["tower"].events["level"], 100)
        self.assertEqual(by_name["epicquest"].events["level"], 154)
        self.assertEqual(by_name["kongfu"].events["level"], 25)
        # `kungfu` is a separate variant entry that the client has no world for.
        self.assertEqual(by_name["kungfu"].world_id, 80)
        self.assertEqual(by_name["kungfu"].pieces, 74)

    def test_render_mentions_gaps(self) -> None:
        text = worlds.render(self.result, "2026-11-20")
        self.assertIn("已匹配：22", text)
        self.assertIn("| future |", text)
        self.assertIn("| tower |", text)
        self.assertIn("star_gate", text)


@unittest.skipUnless((OBB / "pkg_2107_WorldData.json").exists(), "shipped sheets not available")
class WorldGateTest(unittest.TestCase):
    """The gate export S6 reads; counts must match `world_diff.md`."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = worlds.build_gates(OBB)
        cls.gates = cls.payload["gates"]

    def test_counts_match_world_diff(self) -> None:
        counts = self.payload["counts"]
        self.assertEqual(counts["star_gate"], 53)
        self.assertEqual(counts["key_gate"], 27)
        self.assertEqual(counts["worldgate"], 17)
        self.assertEqual(counts["total"], 97)
        self.assertEqual(counts["unknownKinds"], {})
        self.assertEqual(counts["star_gate"] + counts["key_gate"] + counts["worldgate"], counts["total"])
        by_kind: dict[str, int] = {}
        for gate in self.gates:
            by_kind[gate["kind"]] = by_kind.get(gate["kind"], 0) + 1
        self.assertEqual(by_kind, {"star_gate": 53, "key_gate": 27, "worldgate": 17})

    def test_schema_and_provenance(self) -> None:
        self.assertEqual(self.payload["format"], 1)
        self.assertEqual(self.payload["source"], "work/obb_packages/pkg_2107_WorldData.json")
        self.assertRegex(self.payload["generated"], r"^sha256:[0-9a-f]{16}$")
        self.assertEqual(self.payload["generated"], worlds.gate_stamp(OBB))
        self.assertEqual(len(self.gates), 97)
        for gate in self.gates:
            self.assertEqual(
                set(gate),
                {"world", "worldClient", "kind", "event", "target", "targetClient", "stars", "keys", "raw"},
            )
            self.assertIsInstance(gate["world"], str)
            self.assertIsInstance(gate["worldClient"], str)
            self.assertIn(gate["kind"], worlds.GATE_KINDS)
            self.assertIsInstance(gate["event"], str)
            self.assertIsInstance(gate["raw"], dict)
            self.assertEqual(gate["raw"]["m_eventType"], gate["kind"])
        self.assertEqual(len({gate["event"] for gate in self.gates}), 97)

    def test_keys_and_stars_never_mix(self) -> None:
        for gate in self.gates:
            self.assertFalse(
                gate["keys"] is not None and gate["stars"] is not None,
                f"{gate['event']} 同时有 keys 和 stars",
            )
            if gate["kind"] == "key_gate":
                self.assertIsNone(gate["stars"])
                self.assertIn(gate["keys"], {1, 3, 4, 5})
                self.assertEqual(gate["keys"], gate["raw"]["m_cost"])
            if gate["kind"] == "star_gate":
                self.assertIsNone(gate["keys"])
                self.assertEqual(gate["stars"], gate["raw"].get("m_cost"))
            if gate["kind"] == "worldgate":
                self.assertIsNone(gate["keys"])
                self.assertIsNone(gate["stars"])

    def test_zero_is_not_null(self) -> None:
        free = [g for g in self.gates if g["kind"] == "star_gate" and g["stars"] == 0]
        unpriced = [g for g in self.gates if g["kind"] == "star_gate" and g["stars"] is None]
        self.assertEqual(len(free), 21)  # m_cost = 0 means "free", not "unknown"
        self.assertEqual(len(unpriced), 18)  # m_cost absent -> null
        self.assertTrue(free and unpriced)
        for gate in free + unpriced:
            self.assertIsNone(gate["keys"])

    def test_client_ids_follow_aliases(self) -> None:
        by_world = {}
        for gate in self.gates:
            by_world.setdefault(gate["world"], []).append(gate)
        for alias, client in (("gta", "losantosvice"), ("skycity", "sky"), ("rainbowmarket", "lunarrainbowmarket")):
            self.assertIn(alias, by_world, f"没有 {alias} 的门，别名用例落空")
            for gate in by_world[alias]:
                self.assertEqual(gate["world"], alias)  # 原字段不变
                self.assertEqual(gate["worldClient"], client)
        self.assertEqual(self.payload["counts"]["aliasHits"], {"gta": 6, "kungfu": 1, "rainbowmarket": 1, "skycity": 2})
        for gate in self.gates:
            self.assertEqual(gate["targetClient"], worlds._client_name(gate["target"]))
            if gate["target"] is None:
                self.assertIsNone(gate["targetClient"])

    def test_targets_and_stars_are_not_guessed(self) -> None:
        stars = [gate["stars"] for gate in self.gates if gate["kind"] == "star_gate"]
        self.assertLessEqual(set(stars), {0, 1, 8, 10, 20, None})
        self.assertEqual(stars.count(None), 18)  # 18 star gates carry no m_cost
        for gate in self.gates:
            if gate["kind"] == "key_gate":
                self.assertIsNone(gate["stars"])  # m_cost there means keys, not stars
                self.assertIsNone(gate["target"])  # m_unlockedFrom is empty on all 27
            if gate["kind"] == "worldgate":
                self.assertIsNone(gate["stars"])
                head = str(gate["raw"]["m_dataString"]).split("-", 1)[0]
                self.assertEqual(gate["target"], head)
        self.assertEqual(sum(1 for gate in self.gates if gate["target"] is None), 58)
        for gate in self.gates:
            if gate["kind"] == "star_gate" and gate["raw"].get("m_unlockedFrom"):
                self.assertEqual(gate["target"], gate["raw"]["m_unlockedFrom"])

    def test_export_is_deterministic_and_matches_committed_file(self) -> None:
        first = worlds.render_gates_json(worlds.build_gates(OBB))
        second = worlds.render_gates_json(worlds.build_gates(OBB))
        self.assertEqual(
            hashlib.sha256(first.encode("utf-8")).hexdigest(),
            hashlib.sha256(second.encode("utf-8")).hexdigest(),
        )
        self.assertTrue(GATES.exists(), f"missing committed artifact: {GATES}")
        self.assertEqual(first.encode("utf-8"), GATES.read_bytes())

    def test_unknown_gate_kinds_survive(self) -> None:
        sheet = {
            "version": 1,
            "objects": [
                {
                    "objclass": "WorldData",
                    "objdata": {
                        "m_worldName": "testworld",
                        "m_worldId": 1,
                        "m_eventList": [
                            {"m_eventType": "star_gate", "m_name": "test_star", "m_cost": 8},
                            {"m_eventType": "mystery_gate", "m_name": "test_mystery"},
                            {"m_eventType": "level", "m_name": "test_level_1"},
                        ],
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            obb = Path(tmp)
            (obb / "pkg_2107_WorldData.json").write_text(
                json.dumps(sheet, ensure_ascii=False), encoding="utf-8"
            )
            payload = worlds.build_gates(obb)
        counts = payload["counts"]
        self.assertEqual(counts["star_gate"], 1)
        self.assertEqual(counts["total"], 2)  # the level event is not a gate
        self.assertEqual(counts["unknownKinds"], {"mystery_gate": 1})
        unknown = [gate for gate in payload["gates"] if gate["kind"] == "mystery_gate"]
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0]["event"], "test_mystery")
        self.assertIsNone(unknown[0]["stars"])
        self.assertIsNone(unknown[0]["target"])
        self.assertEqual(unknown[0]["world"], "testworld")
        self.assertEqual(payload["source"], f"{obb.as_posix()}/pkg_2107_WorldData.json")

    def test_committed_report_lists_zero_gate_worlds(self) -> None:
        self.assertTrue(worlds.DEFAULT_GATES_REPORT.exists(), "缺少 docs/reviews/2026-11-21-world-gates.md")
        text = worlds.DEFAULT_GATES_REPORT.read_text(encoding="utf-8")
        self.assertEqual(text, worlds.render_gates_markdown(self.payload, OBB))
        self.assertIn("`egypt`", text)
        self.assertIn("`gta`", text)
        self.assertIn("`losantosvice`", text)
        zero_line = next(line for line in text.splitlines() if line.startswith("WorldData 共"))
        self.assertIn("零门", text)
        self.assertTrue(zero_line)
        self.assertIn("keys", text) and self.assertIn("stars", text)

    def test_cli_writes_markdown_and_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "world_diff.md"
            gates = Path(tmp) / "world_gates.json"
            report = Path(tmp) / "gates.md"
            argv = [
                "worlds.py",
                "--out",
                str(md),
                "--emit-json",
                str(gates),
                "--emit-report",
                str(report),
            ]
            out = io.StringIO()
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
                code = worlds.main()
            self.assertEqual(code, 0)
            self.assertTrue(md.is_file())
            self.assertTrue(gates.is_file())
            self.assertTrue(report.is_file())
            self.assertIn("gates star=53 key=27 world=17 total=97", out.getvalue())
            payload = json.loads(gates.read_text(encoding="utf-8"))
            self.assertEqual(payload["counts"]["total"], 97)
            self.assertEqual(report.read_text(encoding="utf-8"), worlds.render_gates_markdown(payload, OBB))


if __name__ == "__main__":
    unittest.main()
