"""Contract tests for `tools/contentc/mapping.py`.

The mapping is the bridge between the shipped PlantType/ZombieType sheets and the
client's own `content/plants.json` / `content/zombies.json` ids. These tests pin the
things a reviewer must be able to trust:

* every pack objdata row becomes exactly one CSV row (339 plants, 1127 zombies);
* every client id is either attributed to a pack row or listed as client-only;
* the known art-reuse PopAnim hits never become matches;
* two runs produce byte-identical CSV and report output.

    python tools/tests/test_mapping.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tools.contentc import mapping  # noqa: E402

OBB = Path(
    os.environ.get("PVZ2_OBB_DIR") or (REPO.parent.parent / "work" / "obb_packages")
)
CONTENT = REPO / "content"
MANUAL = REPO / "tools" / "contentc" / "manual_mapping.csv"

# Zombies whose `extra.source_codename` names a real original TypeName. They are
# accepted through the manual table, not through an automatic level.
CODENAME_MANUAL_ZOMBIES = {
    "basic": "tutorial",
    "conehead": "tutorial_armor1",
    "buckethead": "tutorial_armor2",
    "flag": "tutorial_flag",
    "gargantuar": "tutorial_gargantuar",
    "football": "football_mech",
    "newspaper": "modern_newspaper",
    "pole_vaulter": "iceage_dodo",
}

# Codenames the shipped sheets do not contain at all: no attribution is possible.
CODENAME_MISSING_ZOMBIES = {"royal_zombie": "royal", "royal_flag": "royal_flag"}

COLUMNS = [
    "side",
    "client_id",
    "pack_type",
    "pack_class",
    "pop_anim",
    "integer_id",
    "match_kind",
    "note",
]

MATCH_KINDS = {"none", "exact", "popanim", "almanac", "manual"}

# Client ids the shipped sheets cannot hold: the plants were added after this build
# (or exist only as `unused_NN` slots). They must be reported as client-only, never
# paired by a PopAnim/name coincidence.
CLIENT_ONLY_PLANTS = {
    "twinsunflower",
    "gatling",
    "umbrellaleaf",
    "iris",
    "rosemary",
    "snowlotus",
    "wildflower",
    "olivewood",
    "astrofruit",
    "chrysanthea",
    "doominator",
    "helioscabbage",
}

# PopAnim collisions that are art reuse, not the same plant.
ART_REUSE_PLANTS = {
    "rosemary": "spearmint",
    "snowlotus": "enforcemint",
    "wildflower": "evilshroom_toughness",
    "olivewood": "olivepit",
    "cheesestrawberry": "explodeonut",
    "oolongpeach": "tombtangler",
    "succulentgrape": "teleportatomine",
}


def run_mapping(out_dir: Path) -> tuple[Path, Path, int]:
    csv_path = out_dir / "id_mapping.csv"
    report_path = out_dir / "mapping_report.md"
    code = mapping.main(
        [
            "--obb",
            str(OBB),
            "--content",
            str(CONTENT),
            "--manual",
            str(MANUAL),
            "--csv",
            str(csv_path),
            "--report",
            str(report_path),
        ]
    )
    return csv_path, report_path, code


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def client_ids(name: str) -> list[str]:
    """名册里的**客户端行** id。

    `source: "pack"` 的派生行是原版表自己的条目（名册只是把它抄进来），
    `mapping.py` 不算它们，这里也必须排除，否则「客户端独有」会凭空多 251 条。
    """
    with (CONTENT / name).open(encoding="utf-8-sig") as handle:
        return [row["id"] for row in json.load(handle) if row.get("source") != "pack"]


class MappingOutputTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        csv_path, report_path, code = run_mapping(cls.tmp)
        assert code == 0, f"mapping.main returned {code}"
        cls.csv_path = csv_path
        cls.report_path = report_path
        cls.rows = read_rows(csv_path)
        cls.report = report_path.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # ---- shape ---------------------------------------------------------

    def test_header_is_exact(self):
        with self.csv_path.open(encoding="utf-8", newline="") as handle:
            self.assertEqual(next(csv.reader(handle)), COLUMNS)

    def test_pack_side_row_counts(self):
        plants = [r for r in self.rows if r["side"] == "plant" and r["pack_type"]]
        zombies = [r for r in self.rows if r["side"] == "zombie" and r["pack_type"]]
        self.assertEqual(len(plants), 339)
        self.assertEqual(len(zombies), 1127)

    def test_total_row_count_is_pack_plus_client_only(self):
        client_only = [r for r in self.rows if not r["pack_type"]]
        self.assertEqual(len(self.rows), 339 + 1127 + len(client_only))

    def test_match_kinds_are_from_the_declared_set(self):
        kinds = {r["match_kind"] for r in self.rows}
        self.assertLessEqual(kinds, MATCH_KINDS)

    # ---- client coverage ----------------------------------------------

    def test_every_client_plant_is_attributed_or_client_only(self):
        attributed = {r["client_id"] for r in self.rows if r["pack_type"] and r["client_id"]}
        client_only = {r["client_id"] for r in self.rows if not r["pack_type"] and r["client_id"]}
        ids = client_ids("plants.json")
        self.assertEqual(len(ids), 147)
        for cid in ids:
            self.assertTrue(cid in attributed or cid in client_only, cid)
        self.assertFalse(attributed & client_only)

    def test_every_client_zombie_is_attributed_or_client_only(self):
        attributed = {r["client_id"] for r in self.rows if r["pack_type"] and r["client_id"]}
        client_only = {r["client_id"] for r in self.rows if not r["pack_type"] and r["client_id"]}
        ids = client_ids("zombies.json")
        self.assertEqual(len(ids), 55)
        for cid in ids:
            self.assertTrue(cid in attributed or cid in client_only, cid)
        self.assertFalse(attributed & client_only)

    def test_known_client_only_plants(self):
        client_only = {r["client_id"] for r in self.rows if not r["pack_type"]}
        self.assertLessEqual(CLIENT_ONLY_PLANTS, client_only)
        # 103 of the 147 client plants do not exist in this build of the sheets.
        self.assertEqual(sum(1 for r in self.rows if not r["pack_type"] and r["side"] == "plant"), 103)

    # ---- the guards the known facts demand ----------------------------

    def test_art_reuse_popanim_is_not_a_match(self):
        by_client = {r["client_id"]: r for r in self.rows if r["pack_type"] and r["client_id"]}
        for client_id, pack_type in ART_REUSE_PLANTS.items():
            self.assertNotIn(client_id, by_client, f"{client_id} must not be matched by PopAnim")
            row = next(r for r in self.rows if r["client_id"] == client_id and not r["pack_type"])
            self.assertEqual(row["match_kind"], "none")
            self.assertIn("美术复用", row["note"])
            self.assertIn(pack_type, row["note"])

    def test_no_plant_is_paired_through_almanac_numbers(self):
        # Client almanac_no is its own 1..147 ordering; the pack IntegerID space is
        # unrelated. Any collision is a candidate, never an automatic match.
        almanac = [r for r in self.rows if r["match_kind"] == "almanac"]
        self.assertEqual(almanac, [])

    def test_duplicate_pack_type_names_are_kept_apart(self):
        for name in ("heavy_shield", "kongfu_gargantuar"):
            rows = [r for r in self.rows if r["side"] == "zombie" and r["pack_type"] == name]
            self.assertEqual(len(rows), 2, name)
            self.assertEqual({r["match_kind"] for r in rows}, {"none"}, name)
        # The duplicate heavy_shield entries share IntegerID 538.
        heavy = [r for r in self.rows if r["pack_type"] == "heavy_shield"]
        self.assertEqual({r["integer_id"] for r in heavy}, {"538"})

    def test_known_exact_matches_carry_pack_metadata(self):
        row = next(r for r in self.rows if r["side"] == "plant" and r["client_id"] == "sunflower")
        self.assertEqual(row["match_kind"], "exact")
        self.assertEqual(row["pack_type"], "sunflower")
        self.assertEqual(row["pack_class"], "PlantLittleSunflower")
        self.assertEqual(row["integer_id"], "1")
        zombie = next(r for r in self.rows if r["side"] == "zombie" and r["client_id"] == "kongfu")
        self.assertEqual(zombie["match_kind"], "exact")
        self.assertEqual(zombie["pack_class"], "ZombieBasic")

    # ---- the report ----------------------------------------------------

    def test_report_covers_both_directions_and_candidates(self):
        self.assertIn("## 逐级命中统计", self.report)
        self.assertIn("## 客户端独有", self.report)
        self.assertIn("## 原版独有", self.report)
        self.assertIn("## 一对多清单", self.report)
        self.assertIn("## 需要人工确认的候选", self.report)
        self.assertIn("source_codename", self.report)
        self.assertIn("美术复用", self.report)
        self.assertIn("unused_43", self.report)

    def test_report_separates_accepted_codenames_from_invalid_ones(self):
        self.assertIn("A0. 已按 `source_codename` 经人工表采信", self.report)
        self.assertIn("A2. `source_codename` 指向原版不存在的条目", self.report)
        self.assertIn("代号无效，不是没有线索", self.report)
        self.assertIn("27 个 client 独有", self.report)
        self.assertIn("8 个按 `extra.source_codename` 经人工表采信", self.report)

    def test_client_only_zombies_split_into_codename_and_unknown(self):
        client_only = [r for r in self.rows if not r["pack_type"] and r["side"] == "zombie"]
        # 55 client zombies - 20 exact - 8 codename manual matches = 27 client-only.
        self.assertEqual(len(client_only), 27)
        self.assertFalse([r for r in client_only if "精确命中原版" in r["note"]])
        unresolved = [r for r in client_only if "指向的原版条目不存在" in r["note"]]
        self.assertEqual({r["client_id"] for r in unresolved}, set(CODENAME_MISSING_ZOMBIES))
        self.assertEqual(len(client_only) - len(unresolved), 25)

    def test_codename_zombies_are_accepted_through_the_manual_table(self):
        matched = {
            r["client_id"]: r
            for r in self.rows
            if r["side"] == "zombie" and r["client_id"] and r["pack_type"]
        }
        for client_id, pack_type in CODENAME_MANUAL_ZOMBIES.items():
            self.assertIn(client_id, matched, client_id)
            row = matched[client_id]
            self.assertEqual(row["match_kind"], "manual", client_id)
            self.assertEqual(row["pack_type"], pack_type, client_id)
            self.assertIn("source_codename", row["note"], client_id)
            self.assertIn(pack_type, row["note"], client_id)
        for client_id in CODENAME_MISSING_ZOMBIES:
            self.assertNotIn(client_id, matched, client_id)
            row = next(r for r in self.rows if r["side"] == "zombie" and r["client_id"] == client_id)
            self.assertEqual(row["match_kind"], "none", client_id)

    # ---- determinism ---------------------------------------------------

    def test_two_runs_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as other:
            csv_path, report_path, code = run_mapping(Path(other))
            self.assertEqual(code, 0)
            self.assertEqual(csv_path.read_bytes(), self.csv_path.read_bytes())
            self.assertEqual(report_path.read_bytes(), self.report_path.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)

# 干净 clone 里没有 work/obb_packages（原版表目录不进仓库）：缺目录时整套跳过，
# 而不是每个用例报 FileNotFoundError。想真跑就设 PVZ2_OBB_DIR 指到解包目录。
if not OBB.is_dir():
    import unittest as _unittest

    for _name, _obj in list(globals().items()):
        if isinstance(_obj, type) and issubclass(_obj, _unittest.TestCase):
            setattr(_obj, "__unittest_skip__", True)
            setattr(_obj, "__unittest_skip_why__", f"缺少原版表目录 {OBB}（设 PVZ2_OBB_DIR）")
