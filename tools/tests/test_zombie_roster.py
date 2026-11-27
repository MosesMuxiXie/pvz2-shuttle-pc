"""Tests for tools/contentc/zombie_roster.py (A9b: zombie/creature roster)."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.contentc import zombie_roster as zr

ROOT = zr.ROOT
AUTHORED = 55
ADDED = 56
TOTAL = 111
REFERENCED = 57
CONFLICTS = 1
SPIDER_IDS = 23
FISH_IDS = 18
CREATURE_IDS = 7


class RosterCache:
    """One build for every test: scanning 118 level definitions is the slow part."""

    roster: zr.Roster | None = None
    content_rows: list[dict] | None = None

    @classmethod
    def get(cls) -> zr.Roster:
        if cls.roster is None:
            cls.roster = zr.build()
        return cls.roster

    @classmethod
    def content(cls) -> list[dict]:
        if cls.content_rows is None:
            cls.content_rows = json.loads(zr.DEFAULT_ZOMBIES.read_text(encoding="utf-8"))
        return cls.content_rows


def artifact() -> dict:
    return json.loads(zr.DEFAULT_JSON.read_text(encoding="utf-8"))


class CountsTest(unittest.TestCase):
    def test_counts_close(self):
        counts = RosterCache.get().counts
        self.assertEqual(counts["authored"], AUTHORED)
        self.assertEqual(counts["added"], ADDED)
        self.assertEqual(counts["total"], TOTAL)
        self.assertEqual(counts["referenced"], REFERENCED)
        self.assertEqual(counts["conflicts"], CONFLICTS)
        self.assertEqual(counts["unresolved"], 0)
        self.assertEqual(counts["authored"] + counts["added"], counts["total"])

    def test_kind_and_objclass_splits(self):
        counts = RosterCache.get().counts
        self.assertEqual(counts["byKind"]["spider"], SPIDER_IDS)
        self.assertEqual(counts["byKind"]["fish"], FISH_IDS)
        self.assertEqual(counts["byKind"]["fish_creature"], CREATURE_IDS)
        self.assertEqual(counts["byKind"]["minigame"], 9)  # `beach` is a conflict, not a row
        self.assertEqual(counts["byObjclass"], {"CreatureType": CREATURE_IDS, "ZombieType": 49})
        self.assertEqual(counts["withHp"], 49)
        self.assertEqual(counts["withoutHp"], CREATURE_IDS)
        self.assertEqual(sum(counts["byFamily"].values()), 49)

    def test_reference_totals(self):
        references = artifact()["references"]
        self.assertEqual(references["spider"]["ids"], SPIDER_IDS)
        # 118 levels carry a spider entry, but egypt_25 / frontyard_162 / lostcity_65 are
        # `SpiderCount: 0` eye-alert markers with no SpiderZombieName -- they reference nothing.
        self.assertEqual(references["spider"]["levels"], 115)
        self.assertEqual(references["fish"]["levels"], 26)
        self.assertGreaterEqual(references["minigame"]["levels"], 1)


class SpiderTest(unittest.TestCase):
    def test_spider_names_come_from_the_pack_objects(self):
        rows = {row["id"]: row for row in RosterCache.get().rows}
        row = rows["chinesegarden_imp"]
        self.assertEqual(row["objclass"], "ZombieType")
        self.assertEqual(row["zombieClass"], "ZombieFutureImp")
        self.assertEqual(row["family"], "walk")
        self.assertEqual(row["hp"], 190)
        self.assertEqual(row["hpSource"], "ZombieWaterImpDefault")
        self.assertEqual(row["referencedCounts"]["spider"], 42)

    def test_all_spider_ids_resolve(self):
        rows = RosterCache.get().rows
        spider = {row["id"] for row in rows if row["referencedCounts"]["spider"]}
        self.assertEqual(len(spider), SPIDER_IDS)
        for expected in ("future_imp", "heian_ninja", "beach_imp", "roman_imp", "hero_impfinity"):
            self.assertIn(expected, spider)

    def test_package_suffix_is_stripped(self):
        """level_mechanics stores `pkg_0325_LevelDefinition.json`; the scan needs `pkg_0325`."""
        counted = RosterCache.get().counts["byKind"]["spider"]
        self.assertEqual(counted, SPIDER_IDS, "spider names silently dropped: package suffix not stripped")


class FishTest(unittest.TestCase):
    def test_atlantis_zombies_use_the_property_sheet_for_hp(self):
        rows = {row["id"]: row for row in RosterCache.get().rows}
        self.assertEqual(rows["poseidon_assistant"]["zombieClass"], "ZombieAtlantisPoseidon")
        self.assertEqual(rows["poseidon_assistant"]["family"], "summon")
        self.assertEqual(rows["poseidon_assistant"]["hp"], 550)
        self.assertEqual(rows["cthulhu_jelly_fish"]["family"], "gargantuar")
        self.assertEqual(rows["cthulhu_jelly_fish"]["hp"], 2700)
        self.assertEqual(rows["atlantis_diver"]["family"], "walk")
        self.assertEqual(rows["atlantis_diver"]["hp"], 320)

    def test_creatures_are_creature_types_without_hp(self):
        rows = {row["id"]: row for row in RosterCache.get().rows}
        self.assertEqual(rows["hermitcrab"]["objclass"], "CreatureType")
        self.assertEqual(rows["hermitcrab"]["creatureClass"], "FishHermitCrab")
        self.assertIsNone(rows["hermitcrab"]["hp"])
        self.assertIsNone(rows["hermitcrab"]["family"])
        self.assertEqual(rows["krill"]["creatureClass"], "FishBase")
        creatures = [row for row in rows.values() if row["objclass"] == "CreatureType"]
        self.assertEqual(len(creatures), CREATURE_IDS)


class ConflictTest(unittest.TestCase):
    def test_beach_keeps_the_authored_row(self):
        roster = RosterCache.get()
        self.assertEqual([row["id"] for row in roster.conflicts], ["beach"])
        self.assertNotIn("beach", [row["id"] for row in roster.rows])
        beach = next(row for row in roster.authored_rows if row["id"] == "beach")
        self.assertNotIn("source", beach)

    def test_content_file_never_repeats_an_authored_id(self):
        rows = RosterCache.content()
        ids = [row["id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))


class GuardTest(unittest.TestCase):
    def test_every_referenced_id_is_in_the_roster_or_unresolved(self):
        roster = RosterCache.get()
        present = {row["id"] for row in RosterCache.content()}
        resolved = {row["id"] for row in roster.rows} | {row["id"] for row in roster.conflicts}
        missing = resolved - present
        self.assertEqual(missing, set())
        for entry in roster.unresolved:
            self.assertTrue(entry["reason"].strip(), f"{entry['id']} has no reason")
        self.assertEqual(
            {row["id"] for row in roster.rows} | {row["id"] for row in roster.conflicts} | {e["id"] for e in roster.unresolved},
            {row["id"] for row in roster.rows} | {row["id"] for row in roster.conflicts},
        )


class ArtifactShapeTest(unittest.TestCase):
    def test_top_level(self):
        doc = artifact()
        self.assertEqual(doc["marker"], zr.MARKER)
        self.assertEqual(doc["format"], zr.FORMAT)
        self.assertIsNone(doc["generated"], "the stamp must not embed a wall clock")
        self.assertEqual(len(doc["inputs"]), 7)
        for label, info in doc["inputs"].items():
            self.assertRegex(info["sha256"], r"^[0-9a-f]{64}$", label)
            self.assertGreater(info["bytes"], 0, label)
        self.assertFalse(doc["unresolved"])

    def test_rows_are_sorted_and_complete(self):
        rows = artifact()["added"]
        self.assertEqual([row["id"] for row in rows], sorted(row["id"] for row in rows))
        for row in rows:
            self.assertEqual(tuple(sorted(row)), tuple(sorted(zr.ROW_KEYS)))
            self.assertEqual(row["source"], "pack")
            for entry in row["referencedBy"]:
                self.assertIn(entry["kind"], zr.KINDS)
                self.assertTrue(entry["level"])
            if row["family"]:
                self.assertIn(row["family"], zr.FAMILIES)


class ContentFileTest(unittest.TestCase):
    def test_authored_rows_come_first_and_carry_no_source(self):
        rows = RosterCache.content()
        self.assertEqual(len(rows), TOTAL)
        for row in rows[:AUTHORED]:
            self.assertNotIn("source", row, f"authored row {row['id']} was rewritten")
        for row in rows[AUTHORED:]:
            self.assertEqual(row.get("source"), "pack")

    def test_pack_rows_written_for_the_engine_have_no_nulls(self):
        rows = RosterCache.content()[AUTHORED:]
        nulls = [(row["id"], key) for row in rows for key, value in row.items() if value is None]
        self.assertEqual(nulls, [], "catalog.cpp fails on explicit nulls (hp/name_zh/art)")
        creatures = [row for row in rows if row["objclass"] == "CreatureType"]
        self.assertEqual(len(creatures), CREATURE_IDS)
        for row in creatures:
            self.assertNotIn("hp", row, "creatures have no Hitpoints; the key must be omitted")

    def test_file_matches_the_hand_maintained_format(self):
        raw = zr.DEFAULT_ZOMBIES.read_text(encoding="utf-8")
        self.assertFalse(raw.endswith("\n"), "content files carry no trailing newline")
        self.assertEqual(json.dumps(json.loads(raw), ensure_ascii=False, indent=1), raw)


class RenderTest(unittest.TestCase):
    def test_renders_are_stable(self):
        roster = RosterCache.get()
        self.assertEqual(zr.render_artifact(roster), zr.render_artifact(roster))
        self.assertEqual(
            zr.render_content(zr.merge_content(roster.authored_rows, roster)),
            zr.render_content(zr.merge_content(roster.authored_rows, roster)),
        )
        self.assertTrue(zr.render_artifact(roster).endswith("\n"))

    def test_render_matches_the_committed_files(self):
        roster = RosterCache.get()
        self.assertEqual(
            zr.DEFAULT_JSON.read_text(encoding="utf-8"), zr.render_artifact(roster)
        )
        self.assertEqual(
            zr.DEFAULT_ZOMBIES.read_text(encoding="utf-8"),
            zr.render_content(zr.merge_content(roster.authored_rows, roster)),
        )


class IdempotencyTest(unittest.TestCase):
    def test_check_accepts_the_committed_files(self):
        ok, message, _ = zr.check()
        self.assertTrue(ok, message)

    def test_second_write_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = Path(tmp) / "zombies.json"
            art = Path(tmp) / "zombie_roster.json"
            shutil.copyfile(zr.DEFAULT_ZOMBIES, content)
            first = zr.write_outputs(content_path=content, artifact_path=art)
            content_bytes = content.read_bytes()
            artifact_bytes = art.read_bytes()
            second = zr.write_outputs(content_path=content, artifact_path=art)
            self.assertEqual(first.counts, second.counts)
            self.assertEqual(content.read_bytes(), content_bytes)
            self.assertEqual(art.read_bytes(), artifact_bytes)


class UnresolvedTest(unittest.TestCase):
    def test_unknown_rtid_is_reported_not_invented(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            minigames = json.loads(zr.DEFAULT_MINIGAMES.read_text(encoding="utf-8"))
            minigames["levels"]["beach_20"] = {
                "params": {"whackazombie": {"SpawnWhackAZombiesProps": [
                    {"Zombies": [{"Type": "RTID(not_a_zombie@ZombieTypes)"}]}
                ]}}
            }
            path = tmp / "minigames.json"
            path.write_text(json.dumps(minigames), encoding="utf-8")
            roster = zr.build(minigames_path=path)
            ids = [entry["id"] for entry in roster.unresolved]
            self.assertIn("not_a_zombie", ids)
            entry = next(item for item in roster.unresolved if item["id"] == "not_a_zombie")
            self.assertIn("找不到", entry["reason"])
            self.assertNotIn("not_a_zombie", [row["id"] for row in roster.rows])

    def test_missing_input_is_an_input_error(self):
        with self.assertRaises(zr.InputError):
            zr.build(obb=ROOT / "work" / "definitely-not-here")


class CliTest(unittest.TestCase):
    def test_summary_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = Path(tmp) / "zombies.json"
            art = Path(tmp) / "zombie_roster.json"
            shutil.copyfile(zr.DEFAULT_ZOMBIES, content)
            before = content.read_bytes()
            code = zr.main(["--zombies", str(content), "--json", str(art), "-n"])
            self.assertEqual(code, 0)
            self.assertFalse(art.exists(), "-n must not write the artifact")
            self.assertEqual(content.read_bytes(), before)

    def test_dry_run_reports_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            art = Path(tmp) / "zombie_roster.json"
            code = zr.main(["--json", str(art), "--dry-run"])
            self.assertEqual(code, 0)
            self.assertFalse(art.exists(), "--dry-run must not write")

    def test_check_reports_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = Path(tmp) / "zombies.json"
            art = Path(tmp) / "zombie_roster.json"
            shutil.copyfile(zr.DEFAULT_ZOMBIES, content)
            zr.write_outputs(content_path=content, artifact_path=art)
            rows = json.loads(content.read_text(encoding="utf-8"))
            rows[AUTHORED]["hp"] = 9999
            content.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
            code = zr.main(["--zombies", str(content), "--json", str(art), "--check"])
            self.assertEqual(code, 1)

    def test_missing_obb_exits_2(self):
        code = zr.main(["--obb", str(ROOT / "work" / "nope"), "-n"])
        self.assertEqual(code, 2)


class NameHygieneTest(unittest.TestCase):
    def test_ids_are_catalog_safe(self):
        for row in RosterCache.content():
            self.assertRegex(row["id"], r"^[A-Za-z0-9_.-]+$")
            self.assertFalse(re.search(r"\s", row["id"]))

    def test_pop_anim_is_carried_through(self):
        rows = {row["id"]: row for row in RosterCache.get().rows}
        self.assertEqual(rows["chinesegarden_imp"]["popAnim"], "POPANIM_ZOMBIE_ZOMBIE_CHINESE_IMP")
        self.assertTrue(rows["hermitcrab"]["popAnim"].startswith("POPANIM_PLANT_FISHS_FISH_"))


if __name__ == "__main__":
    unittest.main()

# A fresh clone has no pack tree (it lives outside the repository, ~1.4 GB) and no
# extracted art index; the shipped products are still asserted by the tests that do
# not need them. Mark the whole module skipped instead of erroring, the same way
# test_fusions / test_plant_playable do.
if not (zr.DEFAULT_OBB / "pkg_2115_ZombieType.json").is_file():
    import unittest as _unittest

    _WHY = "缺少原版表目录 {{}}（设 PVZ2_OBB_DIR）".format(zr.DEFAULT_OBB)
    for _name, _obj in list(globals().items()):
        if isinstance(_obj, type) and issubclass(_obj, _unittest.TestCase):
            setattr(_obj, "__unittest_skip__", True)
            setattr(_obj, "__unittest_skip_why__", _WHY)
