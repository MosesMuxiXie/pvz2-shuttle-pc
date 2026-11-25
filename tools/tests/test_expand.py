#!/usr/bin/env python3
"""expand.py 的验收测试。

运行：
    python -m unittest tools.tests.test_expand -v
    python -m unittest discover -s tools/tests -p 'test_*.py'

断言四件事：
  - pack 的 339 株一棵不漏、一棵不重；
  - 只输出 content 里没有的 295 株，44 株同名被跳过且原样保留结论；
  - cost / cooldown 的缺省值可以由 content 同族均值当场复算；
  - art 猜中的数量与 assets/db 真实存在的 actor 键一致，猜不到就是 null。
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

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.contentc import expand  # noqa: E402

PACK = REPO / "native" / "generated" / "content.pack"
CONTENT = REPO / "content" / "plants.json"
FAMILIES = REPO / "native" / "generated" / "plant_families.json"
ASSETS = REPO.parent.parent / "PvZ2SHUTTLE" / "assets"

EXPECTED_PACK = 339
EXPECTED_EMITTED = 295
EXPECTED_SKIPPED = 44


def run_main(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = expand.main(argv)
    return code, out.getvalue(), err.getvalue()


@unittest.skipUnless(
    PACK.is_file() and CONTENT.is_file() and (ASSETS / "db" / "MANIFEST.json").is_file(),
    "缺少 content.pack、plants.json 或美术库，跳过",
)
class ExpandTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.roster = expand.build(PACK, CONTENT, FAMILIES, ASSETS)
        cls.pack = expand.load_pack(PACK)
        cls.content = expand.load_content(CONTENT)

    def test_pack_is_fully_covered_without_duplicates(self) -> None:
        pack_ids = [str(row["id"]) for row in self.pack]
        self.assertEqual(len(pack_ids), EXPECTED_PACK)
        self.assertEqual(len(set(pack_ids)), EXPECTED_PACK, "pack 自身有重复 id")
        emitted = [row.entry["id"] for row in self.roster.rows]
        skipped = [row["id"] for row in self.roster.skipped]
        self.assertEqual(len(emitted), len(set(emitted)))
        self.assertEqual(len(skipped), len(set(skipped)))
        self.assertEqual(set(emitted) & set(skipped), set())
        self.assertEqual(set(emitted) | set(skipped), set(pack_ids))

    def test_only_pack_only_plants_are_emitted(self) -> None:
        self.assertEqual(len(self.roster.rows), EXPECTED_EMITTED)
        self.assertEqual(len(self.roster.skipped), EXPECTED_SKIPPED)
        emitted_ids = {row.entry["id"] for row in self.roster.rows}
        self.assertEqual(set(self.roster.skipped[0]), {"id", "reason", "framework", "art"})
        self.assertEqual(emitted_ids & set(self.content), set(), "已存在的 id 不应出现在输出里")
        for row in self.roster.skipped:
            self.assertIn(row["id"], self.content)

    def test_cost_and_cooldown_defaults_are_recomputable(self) -> None:
        stats = expand.cost_stats(self.content)
        families = expand.load_families(FAMILIES)
        for row in self.roster.rows:
            entry = row.entry
            pid = entry["id"]
            family = str(entry["family"])
            if entry["fieldSources"]["cost"] == "family-avg":
                self.assertIn(pid, self.roster.cost_default)
                self.assertEqual(
                    entry["cost"],
                    round(stats.cost_by_family.get(family, stats.cost_global)),
                )
            else:
                self.assertEqual(entry["fieldSources"]["cost"], "pack")
                self.assertIsInstance(entry["packFacts"]["cost"], (int, float))
                self.assertEqual(entry["cost"], int(entry["packFacts"]["cost"]))
            if entry["fieldSources"]["cooldown"] == "family-avg":
                self.assertIn(pid, self.roster.cooldown_default)
                self.assertAlmostEqual(
                    float(entry["cooldown"]),
                    round(stats.cooldown_by_family.get(family, stats.cooldown_global), 2),
                    places=6,
                )
            if pid in families:
                self.assertEqual(family, families[pid]["family"])
                self.assertEqual(entry["fieldSources"]["family"], "plant_families.json")
        self.assertEqual(len(self.roster.cost_default), 2)
        self.assertEqual(len(self.roster.cooldown_default), 3)

    def test_art_hits_match_real_db_keys(self) -> None:
        db = ASSETS / "db"
        for row in self.roster.rows:
            art = row.entry["art"]
            if art is None:
                self.assertEqual(row.entry["fieldSources"]["art"], "null")
                continue
            self.assertTrue(
                (db / art / "skeleton.json").is_file(),
                f"{row.entry['id']} 猜到的 {art} 在美术库里没有 skeleton.json",
            )
            self.assertNotEqual(row.entry["fieldSources"]["art"], "null")
        emitted_hits = sum(1 for row in self.roster.rows if row.entry["art"])
        self.assertEqual(emitted_hits, self.roster.art_hit_pack_only)
        # 全 339 株的命中数要能独立复算：对 pack 每一行重新猜一次
        actors = expand.load_plant_actors(ASSETS)
        total_hits = sum(
            1
            for row in self.pack
            if expand.guess_art(row.get("popAnim"), row.get("animRig"), actors)[0]
        )
        self.assertEqual(total_hits, self.roster.art_hit)
        self.assertGreaterEqual(self.roster.art_hit, self.roster.art_hit_pack_only)

    def test_rows_tags_and_source_markers(self) -> None:
        water = [row for row in self.roster.rows if row.entry["id"] in self.roster.water]
        self.assertEqual(len(water), 1)
        for row in self.roster.rows:
            entry = row.entry
            self.assertEqual(entry["source"], "pack")
            self.assertEqual(entry["behavior"], entry["family"])
            self.assertIn(entry["family"], expand.FAMILY_TAGS)
            if entry["id"] in self.roster.water:
                self.assertEqual(entry["rows"], [])
                self.assertIn("water", entry["tags"])
            else:
                self.assertEqual(entry["rows"], [0])
                self.assertNotIn("water", entry["tags"])
            self.assertIn("plant", entry["tags"])
            self.assertIsInstance(entry["plantfood"], bool)
            self.assertEqual(
                entry["plantfood"],
                bool((entry["packFacts"]["plantFoodDuration"] or 0) > 0),
            )
            self.assertEqual(set(entry["fieldSources"]), set(expand.REQUIRED_FIELDS))
            for field in expand.REQUIRED_FIELDS:
                self.assertIn(field, entry, f"{entry['id']} 缺字段 {field}")

    def test_json_payload_is_self_consistent(self) -> None:
        payload = json.loads(expand.render_json(self.roster))
        self.assertEqual(payload["format"], expand.FORMAT)
        self.assertEqual(payload["generated"], expand.MARKER)
        self.assertEqual(len(payload["plants"]), EXPECTED_EMITTED)
        self.assertEqual(len(payload["skipped_existing"]), EXPECTED_SKIPPED)
        self.assertEqual(payload["counts"]["pack"], EXPECTED_PACK)
        self.assertEqual(payload["counts"]["emitted"], EXPECTED_EMITTED)
        self.assertEqual(payload["counts"]["skipped_existing"], EXPECTED_SKIPPED)
        self.assertEqual(payload["counts"]["artHit"], self.roster.art_hit)
        self.assertEqual(payload["counts"]["artHitPackOnly"], self.roster.art_hit_pack_only)
        self.assertEqual(payload["sources"]["familySource"], self.roster.family_source)

    def test_report_sections_and_family_totals(self) -> None:
        text = expand.render_report(self.roster)
        for heading in (
            "## 摘要",
            "## 分族统计",
            "## art 命中率",
            "## cost / cooldown 缺省",
            f"## 最该先补的 {expand.TOP_READY} 条",
            "## 已知简化",
        ):
            self.assertIn(heading, text)
        self.assertEqual(sum(count for _, count in self.roster.family_counts), EXPECTED_EMITTED)
        ready = expand.ready_to_fill(self.roster)
        self.assertLessEqual(len(ready), expand.TOP_READY)
        for row in ready:
            self.assertTrue(row.entry["art"])
            self.assertTrue(row.has_actions)
        section = text.split(f"## 最该先补的 {expand.TOP_READY} 条", 1)[1].split("## ", 1)[0]
        table_rows = [
            line
            for line in section.splitlines()
            if line.startswith("| ") and not line.startswith("| #")
        ]
        self.assertEqual(len(table_rows), len(ready))

    def test_regeneration_is_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "a.json"
            second = Path(tmp) / "b.json"
            report_a = Path(tmp) / "a.md"
            report_b = Path(tmp) / "b.md"
            base = ["--pack", str(PACK), "--content", str(CONTENT), "--families", str(FAMILIES), "--assets", str(ASSETS)]
            self.assertEqual(run_main(base + ["--json", str(first), "--report", str(report_a)])[0], 0)
            self.assertEqual(run_main(base + ["--json", str(second), "--report", str(report_b)])[0], 0)
            self.assertEqual(
                hashlib.sha256(first.read_bytes()).hexdigest(),
                hashlib.sha256(second.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                hashlib.sha256(report_a.read_bytes()).hexdigest(),
                hashlib.sha256(report_b.read_bytes()).hexdigest(),
            )
            self.assertEqual(first.read_text(encoding="utf-8"), expand.render_json(self.roster))

    def test_check_mode_accepts_fresh_and_rejects_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / "roster.json"
            report = Path(tmp) / "report.md"
            base = ["--pack", str(PACK), "--content", str(CONTENT), "--families", str(FAMILIES), "--assets", str(ASSETS)]
            code, _, err = run_main(base + ["--json", str(payload), "--report", str(report), "--check"])
            self.assertEqual(code, 1)
            self.assertIn("缺失", err)

            self.assertEqual(run_main(base + ["--json", str(payload), "--report", str(report)])[0], 0)
            self.assertEqual(
                run_main(base + ["--json", str(payload), "--report", str(report), "--check"])[0], 0
            )

            report.write_text(report.read_text(encoding="utf-8") + "\n<!-- stale -->\n", encoding="utf-8")
            code, _, err = run_main(base + ["--json", str(payload), "--report", str(report), "--check"])
            self.assertEqual(code, 1)
            self.assertIn("过期", err)

    def test_missing_inputs_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = run_main(["--pack", str(Path(tmp) / "nope.pack"), "--content", str(CONTENT)])
            self.assertEqual(code, 2)
            self.assertIn("缺少 pack", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
