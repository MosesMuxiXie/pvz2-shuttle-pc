import struct
import unittest

from tools.obb import level_index


class LevelIndexTest(unittest.TestCase):
    def test_name_trie_reuses_prefix_at_odd_word_boundary(self):
        table = struct.pack(
            "<12I", 0x84, 0x86, 0x389, 2, 0, 4096, 20, 0x8A, 2, 0, 0, 24
        )
        entries = level_index.decode_directory(table, 8192)
        self.assertEqual(
            [(entry.path, entry.offset, entry.size) for entry in entries],
            [("ABD", 0, 24), ("ABC", 4096, 20)],
        )

    def test_module_references_keep_scope_and_missing_nested_reference(self):
        objects = [
            {"objclass": "LevelDefinition", "objdata": {"Modules": [
                "RTID(Belt@CurrentLevel)", "RTID(OldVases@.)", "RTID(Sun@LevelModules)"
            ]}},
            {"aliases": ["Belt"], "objclass": "ConveyorSeedBankProperties",
             "objdata": {"Wave": "RTID(Missing@CurrentLevel)"}},
            {"aliases": ["OldVases"], "objclass": "VaseBreakerPresetProperties"},
        ]
        modules, local = level_index.level_references(
            objects, 0, {"Sun": [{"index": 18, "class": "SunDropperProperties"}]}
        )
        self.assertEqual([module["status"] for module in modules], ["resolved"] * 3)
        self.assertEqual(modules[2]["targets"][0]["index"], 18)
        self.assertEqual([(ref["pointer"], ref["reference"]) for ref in local
                          if ref["status"] == "missing"],
                         [("/objects/1/objdata/Wave", "RTID(Missing@CurrentLevel)")])

    def test_world_link_requires_exact_level_path(self):
        docs = [("pkg_0010", "PACKAGES/WORLDMAPDATA.RTON", {"objects": [
            {"objclass": "WorldData", "objdata": {"m_worldName": "example", "m_eventList": [
                {"m_eventType": "level", "m_name": "example_1", "m_dataString": "event/one/day1"},
                {"m_eventType": "level", "m_name": "example_2", "m_dataString": "day1"},
            ]}}
        ]})]
        links, unmatched = level_index.world_entries(docs, {"event/one/day1": "pkg_0001"})
        self.assertEqual([entry["event"] for entry in links.get("pkg_0001", [])], ["example_1"])
        self.assertEqual([entry["event"] for entry in unmatched], ["example_2"])

    def test_duplicate_alias_is_ambiguous_and_other_scope_is_not_local(self):
        objects = [
            {"objclass": "LevelDefinition", "objdata": {"Modules": [
                "RTID(Same@CurrentLevel)", "RTID(Same@ZombieTypes)"]}},
            {"aliases": ["Same"], "objclass": "SeedBankProperties"},
            {"aliases": ["Same"], "objclass": "ConveyorSeedBankProperties"},
        ]
        modules, _ = level_index.level_references(objects, 0, {})
        self.assertEqual([ref["status"] for ref in modules], ["ambiguous", "unindexed_scope"])
        self.assertEqual([t["index"] for t in modules[0]["targets"]], [1, 2])
        self.assertEqual(modules[1]["targets"], [])

    def test_directory_rejects_entry_outside_decompressed_stream(self):
        table = struct.pack("<5I", 0x84, 2, 0, 4096, 20)
        with self.assertRaises(ValueError):
            level_index.decode_directory(table, 4096)

    def test_index_uses_path_and_existing_package_link_despite_comment(self):
        docs = [("pkg_0000", "PACKAGES/LEVELS/EVENT/ONE/DAY1.RTON", {
            "#comment": "Completely different level", "objects": [
                {"objclass": "LevelDefinition", "objdata": {
                    "Modules": ["RTID(Belt@CurrentLevel)"]}},
                {"aliases": ["Belt"], "objclass": "ConveyorSeedBankProperties"},
            ]})]
        legacy = [{"file": "frontyard_7.json", "id": "frontyard_7", "world": "frontyard",
                   "extra": {"package": "pkg_0000", "source": "obb-synth"}}]
        result = level_index.build_index(docs, legacy)
        self.assertEqual(result["levels"][0]["level_key"], "event/one/day1")
        self.assertEqual(result["legacy_links"][0]["path"], docs[0][1])
        self.assertEqual(result["legacy_links"][0]["source"], "obb-synth")
        self.assertEqual(result["levels"][0]["mechanics"]["conveyor"][0]["index"], 1)


if __name__ == "__main__":
    unittest.main()
