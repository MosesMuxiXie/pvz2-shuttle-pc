"""Guard the numbers quoted in the docs against the artifacts they come from.

The roster口径 changed three times in one round (147 → 293 playable → 304 playable /
409 rows / 35 blocked).  A reader cannot tell which prose figure is current, so the
docs must either quote the artifact's value or not quote a number at all.  These
checks fail with the文件名 and the line number of the stale sentence instead of
leaving the drift for the next person to notice.

Everything is read from disk: no hand arithmetic, no constants copied out of the
task brief.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
COMPLETENESS = DOCS / "COMPLETENESS.md"
PROGRESS = DOCS / "PROGRESS.md"
BASELINE = DOCS / "PARITY_BASELINE.md"
PLAYABLE = ROOT / "native" / "generated" / "plant_playable.json"
BLOCKED = ROOT / "native" / "generated" / "plant_blocked.json"
ROSTER = ROOT / "content" / "plants.json"
LEVEL_PLAYABILITY = ROOT / "native" / "generated" / "level_playability.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def lines(path: Path) -> list[str]:
    return read_text(path).splitlines()


def find(pattern: str, path: Path) -> list[tuple[int, str]]:
    """Every (1-based line number, line) matching the regex."""
    rx = re.compile(pattern)
    return [(number, line) for number, line in enumerate(lines(path), 1) if rx.search(line)]


class ArtifactFacts(unittest.TestCase):
    """The artifact is the authority; the doc checks below only compare against it."""

    def test_playable_and_blocked_come_from_the_same_roster(self) -> None:
        payload = read_json(PLAYABLE)
        counts = payload["counts"]
        self.assertEqual(counts["total"], 339)
        self.assertEqual(
            counts["playable"],
            counts["playableAuthored"] + counts["playableNew"],
            "可玩 = 同名可玩 + 新增可玩，产物自己必须闭合",
        )
        self.assertEqual(counts["playable"] + counts["blocked"], counts["total"])

    def test_blocked_artifact_matches_the_playable_tally(self) -> None:
        playable = read_json(PLAYABLE)["counts"]
        blocked = read_json(BLOCKED)
        counts = blocked["counts"]
        self.assertEqual(len(blocked["rows"]), playable["blocked"])
        self.assertEqual(counts["total"], playable["blocked"])
        self.assertEqual(counts["missingCost"], playable["missingCost"])
        self.assertEqual(counts["missingArt"], playable["missingArt"])
        self.assertEqual(counts["both"], playable["blockedBoth"])
        self.assertEqual(counts["missingCost"] + counts["missingArt"] - counts["both"], counts["total"])

    def test_roster_rows_are_authored_plus_pack(self) -> None:
        rows = read_json_array(ROSTER)
        authored = [row for row in rows if row.get("source") != "pack"]
        pack = [row for row in rows if row.get("source") == "pack"]
        self.assertEqual((len(authored), len(pack), len(rows)), (147, 262, 409))
        self.assertEqual(len({row["id"] for row in rows}), len(rows), "名册 id 必须唯一")


def read_json_array(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise AssertionError(f"{path} 顶层不是数组")
    return data


class CompletenessDoc(unittest.TestCase):
    def test_completeness_quotes_the_current_playable_and_blocked_counts(self) -> None:
        counts = read_json(PLAYABLE)["counts"]
        text = read_text(COMPLETENESS)
        for phrase, value in (
            ("可玩", counts["playable"]),
            ("阻断", counts["blocked"]),
        ):
            self.assertIn(
                f"**{value} {phrase}**",
                text,
                f"docs/COMPLETENESS.md 没有引用 {value} {phrase}；产物已变，文档停在旧值",
            )

    def test_completeness_lists_plant_blocked_as_an_artifact(self) -> None:
        size = BLOCKED.stat().st_size
        hits = find(r"plant_blocked\.json", COMPLETENESS)
        self.assertTrue(hits, "docs/COMPLETENESS.md 的产物表缺 plant_blocked.json 一行")
        self.assertTrue(
            any(f"{size:,} B" in line for _, line in hits),
            f"docs/COMPLETENESS.md 里的 plant_blocked.json 尺寸不是当前的 {size:,} B",
        )

    def test_completeness_does_not_repeat_the_retired_decisions(self) -> None:
        text = read_text(COMPLETENESS)
        for stale in ("维持 147", "293 可玩", "46 阻断"):
            self.assertNotIn(
                stale,
                text,
                f"docs/COMPLETENESS.md 仍写着已作废的口径「{stale}」；应改指 409 / 304 / 35",
            )


class ProgressDoc(unittest.TestCase):
    def test_progress_states_the_roster_split(self) -> None:
        rows = read_json_array(ROSTER)
        authored = sum(1 for row in rows if row.get("source") != "pack")
        pack = len(rows) - authored
        text = read_text(PROGRESS)
        self.assertIn(
            f"手工 {authored} + pack 派生 {pack}",
            text,
            "docs/PROGRESS.md 没有写出「手工 N + pack 派生 M」这一当前口径",
        )
        self.assertIn(f"{len(rows)}", text)

    def test_progress_quotes_the_level_playability_counts(self) -> None:
        counts = read_json(LEVEL_PLAYABILITY)["counts"]
        text = read_text(PROGRESS)
        for label, value in (
            ("可玩", counts["playable"]),
            ("仅数据", counts["blockedDataOnly"]),
            ("小游戏", counts["blockedMinigame"]),
            ("引擎可跑", counts["playableInEngine"]),
        ):
            self.assertIn(
                f"{label} {value}",
                text,
                f"docs/PROGRESS.md 的「{label}」不是 level_playability.json 的当前值 {value}",
            )


class BaselineDoc(unittest.TestCase):
    def test_baseline_section_quotes_the_artifacts(self) -> None:
        playable = read_json(PLAYABLE)["counts"]
        blocked = read_json(BLOCKED)["counts"]
        text = read_text(BASELINE)
        self.assertIn("名册 409 与可玩 304（2026-11-26）", text)
        self.assertIn(f"可玩 **{playable['playable']}**", text)
        self.assertIn(f"阻断 **{playable['blocked']}**", text)
        self.assertIn(f"**{blocked['total']} 条**", text)

    def test_baseline_ledger_matches_the_tree(self) -> None:
        """The ledger is a floor for python and an equality for the ctest counts."""
        text = read_text(BASELINE)
        block = re.search(r"<!--\s*test-counts\s*-->(.*?)<!--\s*/test-counts\s*-->", text, re.S)
        self.assertIsNotNone(block, "PARITY_BASELINE.md 缺 test-counts 机器可读块")
        for key in ("audit", "python", "desktop"):
            self.assertRegex(
                block.group(1),
                rf"\|\s*{key}\s*\|\s*\d+\s*\|",
                f"test-counts 块缺 {key} 一行",
            )


if __name__ == "__main__":
    unittest.main()
