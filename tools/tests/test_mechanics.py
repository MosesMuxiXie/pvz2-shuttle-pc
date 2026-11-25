"""``tools/contentc/mechanics.py`` 的回归测试（T51）。

两部分：

* **夹具测试**：在临时目录里造 ``content/levels`` + ``work/obb_packages``，
  逐条钉住机制抽取、身份映射、哨兵、波次归属、unknowns 的行为。
* **产物测试**：对仓库里已生成的 ``native/generated/level_mechanics.json``
  断言聚合数字（1809 关 / 349 关带传送带卡槽 / 286 关保护植物等），
  这是"数据真的在那儿"的唯一硬证据。

跑法::

    python -m unittest discover -s tools/tests -p 'test_*.py'
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "contentc"))

import mechanics as M  # noqa: E402

GENERATED = ROOT / "native" / "generated" / "level_mechanics.json"

_DOC_CACHE: dict | None = None


def generated_doc() -> dict:
    """读一次产物，供聚合断言复用（17 MB，别每条测试都读）。"""
    global _DOC_CACHE
    if _DOC_CACHE is None:
        with GENERATED.open(encoding="utf-8") as handle:
            _DOC_CACHE = json.load(handle)
    return _DOC_CACHE


# --------------------------------------------------------------------------- #
# 夹具
# --------------------------------------------------------------------------- #


class Fixture:
    """一个最小的 ``content/levels`` + ``work/obb_packages`` 组合。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.levels = root / "content" / "levels"
        self.obb = root / "work" / "obb_packages"
        self.levels.mkdir(parents=True, exist_ok=True)
        self.obb.mkdir(parents=True, exist_ok=True)

    def level(self, level_id: str, package: str | None) -> None:
        extra: dict = {} if package is None else {"package": package}
        doc = {"id": level_id, "world": "test", "extra": extra}
        (self.levels / f"{level_id}.json").write_text(
            json.dumps(doc, ensure_ascii=False), encoding="utf-8"
        )

    def package(self, stem: str, objects: list[dict], suffix: str = "") -> Path:
        doc = {"#comment": "fixture", "version": 1, "objects": objects}
        path = self.obb / f"{stem}{suffix}_LevelDefinition.json"
        path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return path

    def build(self, **kwargs) -> M.Inventory:
        return M.build(self.levels, self.obb, **kwargs)


def obj(objclass: str, objdata: dict, alias: str | None = None) -> dict:
    entry: dict = {"objclass": objclass, "objdata": objdata}
    if alias is not None:
        entry["aliases"] = [alias]
    return entry


def level_def(modules: list[str]) -> dict:
    return obj("LevelDefinition", {"Modules": [f"RTID({m}@LevelModules)" for m in modules]})


def wave_manager(waves: list[list[str]]) -> dict:
    return obj(
        "WaveManagerProperties",
        {"Waves": [[f"RTID({name}@CurrentLevel)" for name in wave] for wave in waves]},
        alias="NewWaves",
    )


class FixtureCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.fx = Fixture(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()


# --------------------------------------------------------------------------- #
# 身份映射
# --------------------------------------------------------------------------- #


class IdentityTest(FixtureCase):
    def test_package_stem_is_the_identity_anchor(self) -> None:
        """``extra.package = "pkg_0001"`` 直接对 ``pkg_0001_LevelDefinition.json``。"""
        self.fx.level("beach_1", "pkg_0001")
        self.fx.package("pkg_0001", [level_def([]), obj("InitialPlantProperties",
                          {"InitialPlantPlacements": [{"GridX": 2, "GridY": 3, "TypeName": "peashooter"}]})])
        inv = self.fx.build()
        self.assertEqual(inv.counts["packagesResolved"], 1)
        self.assertEqual(inv.counts["withInitials"], 1)
        self.assertEqual(inv.records["beach_1"]["source"]["package"], "pkg_0001_LevelDefinition.json")
        # source 里记的是包内的对象路径，形如 objects[1]（对象数组下标）
        self.assertEqual(inv.records["beach_1"]["source"]["objects"]["initialPlants"], ["objects[1]"])

    def test_missing_package_leaves_every_mechanic_null(self) -> None:
        """包文件不存在时：机制全 null，但关卡仍然出现在 ``levels`` 里。"""
        self.fx.level("beach_2", "pkg_0999")
        inv = self.fx.build()
        self.assertIn("beach_2", inv.records)
        for name in M.MECHANICS:
            self.assertIsNone(inv.records["beach_2"][name])
        self.assertEqual(inv.counts["packagesMissing"], 1)
        kinds = {row["kind"] for row in inv.unknowns}
        self.assertIn("package-missing", kinds)

    def test_shared_package_gives_both_levels_identical_data(self) -> None:
        """一个包被两关共用：两关都拿到同一份数据，并记 ``package-shared``。"""
        self.fx.level("a_1", "pkg_0002")
        self.fx.level("a_2", "pkg_0002")
        self.fx.package("pkg_0002", [
            level_def([]),
            obj("ProtectThePlantChallengeProperties",
                {"MustProtectCount": 3, "Plants": [{"GridX": 1, "GridY": 1, "PlantType": "sunflower"}]},
                alias="ProtectThePlant"),
        ])
        inv = self.fx.build()
        self.assertEqual(inv.counts["packagesShared"], 1)
        self.assertEqual(inv.records["a_1"]["protectThePlant"], inv.records["a_2"]["protectThePlant"])
        self.assertEqual(inv.records["a_1"]["protectThePlant"]["mustProtectCount"], 3)
        kinds = {row["kind"]: row for row in inv.unknowns}
        self.assertIn("package-shared", kinds)
        self.assertEqual(kinds["package-shared"]["count"], 1)

    def test_ambiguous_index_takes_first_and_records_unknown(self) -> None:
        """同一个 stem 匹配到多个文件时取字典序第一个，并进 ``unknowns``（注入索引来构造）。"""
        self.fx.level("c_1", "pkg_0003")
        first = self.fx.package("pkg_0003", [level_def([])])
        second = self.fx.package("pkg_0003", [level_def(["ProtectThePlant"]), obj(
            "ProtectThePlantChallengeProperties", {"MustProtectCount": 9}, alias="ProtectThePlant")],
            suffix="_dup")
        inv = self.fx.build(package_index={"pkg_0003": [first, second]})
        self.assertEqual(inv.counts["packagesAmbiguous"], 1)
        # 取第一个（没有 protect 的那个）
        self.assertIsNone(inv.records["c_1"]["protectThePlant"])
        kinds = {row["kind"] for row in inv.unknowns}
        self.assertIn("package-ambiguous", kinds)


# --------------------------------------------------------------------------- #
# 哨兵 / 数值字符串
# --------------------------------------------------------------------------- #


class SentinelTest(FixtureCase):
    def test_sentinels_are_kept_and_counted(self) -> None:
        """``-1`` 与 ``2147483647`` 原样保留，并分别计数。"""
        self.fx.level("s_1", "pkg_0010")
        self.fx.package("pkg_0010", [
            level_def([]),
            obj("InitialGridItemProperties",
                {"InitialGridItemPlacements": [
                    {"GridX": -1, "GridY": 2, "TypeName": "mold"},
                    {"GridX": 3, "GridY": 2147483647, "TypeName": "mold"},
                ]}, alias="MoldLocations"),
        ])
        inv = self.fx.build()
        placements = inv.records["s_1"]["initialGridItems"]["placements"]
        self.assertEqual(placements[0]["gridX"], -1)
        self.assertEqual(placements[1]["gridY"], 2147483647)
        self.assertEqual(inv.counts["sentinels"], 2)
        values = {row["value"] for row in inv.sentinels}
        self.assertEqual(values, {-1, 2147483647})

    def test_numeric_strings_are_coerced_and_counted(self) -> None:
        """原版把浮点写成字符串；编译成数字并计数。"""
        self.fx.level("n_1", "pkg_0011")
        self.fx.package("pkg_0011", [
            level_def([]),
            obj("SpiderRainZombieSpawnerProps",
                {"TimeBetweenGroups": "1.5", "GroupSize": "4", "SpiderCount": 9},
                alias="Wave3OfficerRainEvent0"),
        ])
        inv = self.fx.build()
        record = inv.records["n_1"]["spawners"]["spider"][0]
        self.assertEqual(record["timeBetweenGroups"], 1.5)
        self.assertEqual(record["groupSize"], 4)
        self.assertEqual(record["spiderCount"], 9)
        self.assertEqual(inv.counts["coercedHits"], 2)
        keys = {(row["objclass"], row["key"]) for row in inv.coerced}
        self.assertIn(("SpiderRainZombieSpawnerProps", "TimeBetweenGroups"), keys)


# --------------------------------------------------------------------------- #
# 波次归属
# --------------------------------------------------------------------------- #


class WaveTest(FixtureCase):
    def setUp(self) -> None:
        super().setUp()
        self.fx.level("w_1", "pkg_0020")
        self.fx.package("pkg_0020", [
            level_def([]),
            wave_manager([["Wave1"], ["Wave2", "Wave2StormEvent0"]]),
            obj("FrostWindWaveActionProps", {"Winds": [{"Direction": "left", "Row": 2}]},
                alias="Wave2FrostWindEvent0"),
            obj("StormZombieSpawnerProps", {"ColumnStart": 1, "ColumnEnd": 5},
                alias="Wave7StormEvent0"),
            obj("DinoWaveActionProps", {"DinoType": "raptor", "DinoRow": 1}, alias="sweep1"),
        ])
        self.inv = self.fx.build()

    def test_alias_found_in_waves_list(self) -> None:
        """alias 在 ``Waves[i]`` 里出现 -> 波号 = i+1。"""
        frost = self.inv.records["w_1"]["events"]["frost"][0]
        self.assertEqual(frost["wave"], 2)

    def test_alias_falls_back_to_wave_regex(self) -> None:
        """alias 不在 ``Waves`` 里但含 ``Wave<N>`` -> 用正则取 N。"""
        storm = self.inv.records["w_1"]["spawners"]["storm"][0]
        self.assertEqual(storm["wave"], 7)

    def test_unresolvable_alias_is_null_and_unknown(self) -> None:
        """既不在 Waves 里、也没有 ``Wave<N>`` -> ``wave: null`` 且进 unknowns。"""
        dino = self.inv.records["w_1"]["spawners"]["dino"][0]
        self.assertIsNone(dino["wave"])
        unresolved = [row for row in self.inv.unknowns if row["kind"] == "wave-unresolved"]
        self.assertEqual(len(unresolved), 1)
        self.assertIn("sweep1", unresolved[0]["samples"])


# --------------------------------------------------------------------------- #
# 各机制形状
# --------------------------------------------------------------------------- #


class MechanicShapeTest(FixtureCase):
    def test_conveyor_slots_and_changes(self) -> None:
        self.fx.level("cv_1", "pkg_0030")
        self.fx.package("pkg_0030", [
            level_def(["ConveyorBelt"]),
            wave_manager([["Wave1"], ["Wave2"]]),
            obj("ConveyorSeedBankProperties", {
                "InitialPlantList": [
                    {"PlantType": "peashooter", "Weight": 80, "MaxCount": 3, "level": 1},
                    {"Type": "sunflower", "Weight": 20, "MinCount": 1},
                ],
                "ManualPacketSpawning": "true",
            }, alias="ConveyorBelt"),
            obj("ModifyConveyorWaveActionProps", {
                "Add": [{"Type": "wallnut", "Weight": 30}],
                "Remove": [{"Type": "sunflower"}],
            }, alias="Wave2ModConveyor0"),
        ])
        inv = self.fx.build()
        conveyor = inv.records["cv_1"]["conveyor"]
        self.assertEqual(conveyor["slots"][0]["plant"], "peashooter")
        self.assertEqual(conveyor["slots"][1]["plant"], "sunflower")  # Add/Remove 用 Type
        self.assertIs(conveyor["manualPacketSpawning"], True)
        self.assertEqual(conveyor["changes"][0]["wave"], 2)
        self.assertEqual(conveyor["changes"][0]["remove"][0]["plant"], "sunflower")
        self.assertEqual(inv.counts["withConveyorSeedBank"], 1)
        self.assertEqual(inv.counts["withConveyorChanges"], 1)
        # 小写 level 脏键被读到
        self.assertEqual(conveyor["slots"][0]["level"], 1)

    def test_gravestones_and_empty_objdata(self) -> None:
        self.fx.level("gv_1", "pkg_0031")
        self.fx.package("pkg_0031", [
            level_def(["Gravestones"]),
            obj("GravestoneProperties", {
                "ForceSpawnData": [{"GridX": 4, "GridY": 0, "TypeName": "gravestone"}],
                "GravestoneCount": 5,
                "SpawnColumnStart": 1,
                "SpawnColumnEnd": 7,
            }, alias="Gravestones"),
        ])
        inv = self.fx.build()
        gravestones = inv.records["gv_1"]["initialGridItems"]["gravestones"]
        body = gravestones["objects"][0]
        self.assertEqual(body["gravestoneCount"], 5)
        self.assertEqual(body["forceSpawn"][0]["gridX"], 4)
        self.assertEqual(inv.counts["withGravestones"], 1)

    def test_protect_the_plant_payload(self) -> None:
        self.fx.level("pt_1", "pkg_0032")
        self.fx.package("pkg_0032", [
            level_def(["ProtectThePlant"]),
            obj("ProtectThePlantChallengeProperties", {
                "MustProtectCount": 2,
                "Plants": [{"GridX": 3, "GridY": 2, "PlantType": "sunflower", "Level": -1}],
            }, alias="ProtectThePlant"),
        ])
        inv = self.fx.build()
        payload = inv.records["pt_1"]["protectThePlant"]
        self.assertEqual(payload["mustProtectCount"], 2)
        self.assertEqual(payload["plants"][0]["plant"], "sunflower")
        self.assertIs(payload["failWhenProtectedPlantDies"], True)

    def test_merge_multiple_protect_modules(self) -> None:
        """同包多个 protect 模块必须合并（pkg_0965/lostcity_46 的 2 株 → 9 株）。"""
        self.fx.level("pt_2", "pkg_0965")
        self.fx.package("pkg_0965", [
            level_def(["ProtectThePlant1", "ProtectThePlant"]),
            obj("ProtectThePlantChallengeProperties", {
                "MustProtectCount": 2,
                "Plants": [
                    {"GridX": 2, "GridY": 2, "PlantType": "sunflower", "Level": 2},
                    {"GridX": 3, "GridY": 2, "PlantType": "sunflower", "Level": 2},
                ],
            }, alias="ProtectThePlant1"),
            obj("ProtectThePlantChallengeProperties", {
                "MustProtectCount": 2,
                "Plants": [
                    {"GridX": 1, "GridY": 1, "PlantType": "wallnut"},
                    {"GridX": 4, "GridY": 1, "PlantType": "wallnut"},
                    {"GridX": 5, "GridY": 1, "PlantType": "wallnut"},
                ],
            }, alias="ProtectThePlant"),
        ])
        inv = self.fx.build()
        record = inv.records["pt_2"]
        payload = record["protectThePlant"]
        # plants 按对象顺序拼接，5 条不丢；每条带 module 标明来源。
        self.assertEqual(
            [plant["plant"] for plant in payload["plants"]],
            ["sunflower", "sunflower", "wallnut", "wallnut", "wallnut"],
        )
        self.assertEqual(
            [plant["module"] for plant in payload["plants"]],
            ["ProtectThePlant1", "ProtectThePlant1", "ProtectThePlant", "ProtectThePlant", "ProtectThePlant"],
        )
        # must 是各模块相加（并发要求），不是取第一个也不取最大。
        self.assertEqual(payload["mustProtectCount"], 4)
        self.assertEqual(payload["aliases"], ["ProtectThePlant1", "ProtectThePlant"])
        self.assertEqual(payload["alias"], "ProtectThePlant1")  # 向后兼容：仍指第一个模块
        self.assertEqual(
            [(m["alias"], m["plants"], m["mustProtectCount"]) for m in payload["modules"]],
            [("ProtectThePlant1", 2, 2), ("ProtectThePlant", 3, 2)],
        )
        # 每个模块的 objects[i] 都要进 provenance，否则没法回溯是哪个模块贡献的株。
        self.assertEqual(record["source"]["objects"]["protectThePlant"], ["objects[1]", "objects[2]"])
        self.assertEqual([m["object"] for m in payload["modules"]], ["objects[1]", "objects[2]"])
        audit = inv.counts["protect"]
        self.assertEqual(audit["modules"], 2)
        self.assertEqual(
            [row["level"] for row in audit["multiModuleLevels"]], ["pt_2"]
        )
        self.assertEqual(audit["multiModuleLevels"][0]["plants"], 5)
        self.assertEqual(audit["multiModuleLevels"][0]["cells"], 5)
        self.assertEqual(audit["multiModuleLevels"][0]["mustProtectCount"], 4)

    def test_protect_default_field_is_marked_as_client_default(self) -> None:
        """failWhenProtectedPlantDies 是编译端约定，payload 必须标注来源。"""
        self.fx.level("pt_3", "pkg_0033")
        original = {
            "MustProtectCount": 1,
            "Plants": [{"GridX": 0, "GridY": 0, "PlantType": "peashooter"}],
        }
        self.fx.package("pkg_0033", [
            level_def(["ProtectThePlant"]),
            obj("ProtectThePlantChallengeProperties", original, alias="ProtectThePlant"),
        ])
        inv = self.fx.build()
        payload = inv.records["pt_3"]["protectThePlant"]
        self.assertIs(payload["failWhenProtectedPlantDies"], True)
        self.assertEqual(payload["failWhenProtectedPlantDiesSource"], "client-default")
        # 原表没有这个键 —— 标注的意义就在于区分「原版字段」和「我们的约定」。
        self.assertNotIn("FailWhenProtectedPlantDies", original)
        self.assertNotIn("failWhenProtectedPlantDies", original)
        # 单模块时 modules 仍是一条，must 不因相乘/相加而变。
        self.assertEqual(len(payload["modules"]), 1)
        self.assertEqual(payload["modules"][0]["alias"], "ProtectThePlant")
        self.assertEqual(payload["mustProtectCount"], 1)

    def test_jittered_is_aggregated_into_a_pool(self) -> None:
        """夹具级钉住聚合语义：同一 id 出现 N 次就是 N 只，行号去重保留。"""
        self.fx.level("jt_1", "pkg_0040")
        self.fx.package("pkg_0040", [
            level_def(["WaveManagerProperties"]),
            wave_manager([["Wave1"], ["Wave2"]]),
            obj("SpawnZombiesJitteredWaveActionProps", {
                "Zombies": [
                    {"Type": "RTID(basic@ZombieTypes)", "Row": "1"},
                    {"Type": "RTID(basic@ZombieTypes)", "Row": "3"},
                    {"Type": "RTID(cone@ZombieTypes)"},
                ],
                "AdditionalPlantfood": 2,
            }, alias="Wave1"),
            obj("SpawnZombiesJitteredWaveActionProps", {
                "Zombies": [{"Type": "RTID(basic@ZombieTypes)", "Row": "1"}],
                "DynamicPlantfood": 1,
            }, alias="DynamicZombies"),  # 正则兜底不到 → wave null
        ])
        inv = self.fx.build()
        summary = inv.records["jt_1"]["spawners"]["jittered"]
        self.assertEqual(summary["objects"], 2)
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["waves"], {"1": 1})
        self.assertEqual(summary["waveUnresolved"], 1)
        self.assertEqual(summary["pool"]["RTID(basic@ZombieTypes)"], {"count": 3, "rows": [1, 3]})
        self.assertEqual(summary["pool"]["RTID(cone@ZombieTypes)"], {"count": 1})
        self.assertEqual(summary["additionalPlantfood"], 2)
        self.assertEqual(summary["dynamicPlantfood"], 1)
        # 源对象路径仍然逐条记录，聚合不丢 provenance。
        self.assertEqual(inv.records["jt_1"]["source"]["objects"]["spawners"],
                         ["objects[2]", "objects[3]"])

    def test_board_grid_matrix(self) -> None:
        self.fx.level("bg_1", "pkg_0033")
        self.fx.package("pkg_0033", [
            level_def([]),
            obj("BoardGridMapProps", {"Values": [[1, 0, 1], [0, 1, 0]]}, alias="MoldLocationsCustom"),
        ])
        inv = self.fx.build()
        grid = inv.records["bg_1"]["boardGrid"]
        self.assertEqual(grid["rows"], [[1, 0, 1], [0, 1, 0]])
        self.assertEqual((grid["height"], grid["width"]), (2, 3))

    def test_declared_module_without_props_is_counted(self) -> None:
        """``Modules`` 里有 ConveyorBelt 但没有 props 对象 -> ``declaredOnly``。"""
        self.fx.level("dm_1", "pkg_0034")
        self.fx.package("pkg_0034", [level_def(["ConveyorBelt"])])
        inv = self.fx.build()
        self.assertIsNone(inv.records["dm_1"]["conveyor"])
        self.assertEqual(inv.counts["declaredOnly"].get("conveyor"), 1)


# --------------------------------------------------------------------------- #
# 渲染 / CLI
# --------------------------------------------------------------------------- #


class RenderTest(FixtureCase):
    def test_render_is_deterministic_and_timestamp_free(self) -> None:
        self.fx.level("r_1", "pkg_0040")
        self.fx.package("pkg_0040", [level_def([])])
        inv = self.fx.build()
        first = M.render_json(inv)
        second = M.render_json(self.fx.build())
        self.assertEqual(first, second)
        self.assertTrue(first.endswith("\n"))
        self.assertIn('"generated":"2026-11-24"', first)
        doc = json.loads(first)
        self.assertEqual(sorted(doc), ["coerced", "counts", "format", "generated", "levels",
                                       "sentinels", "unknowns"])

    def test_check_reports_missing_outputs(self) -> None:
        self.fx.level("r_2", "pkg_0041")
        self.fx.package("pkg_0041", [level_def([])])
        code = M.main([
            "--levels", str(self.fx.levels),
            "--obb", str(self.fx.obb),
            "--json", str(self.fx.root / "out.json"),
            "--report", str(self.fx.root / "out.md"),
            "--check",
        ])
        self.assertEqual(code, 2)

    def test_write_then_check_is_clean(self) -> None:
        self.fx.level("r_3", "pkg_0042")
        self.fx.package("pkg_0042", [level_def([])])
        json_path = self.fx.root / "out.json"
        report_path = self.fx.root / "out.md"
        argv = [
            "--levels", str(self.fx.levels),
            "--obb", str(self.fx.obb),
            "--json", str(json_path),
            "--report", str(report_path),
        ]
        self.assertEqual(M.main(argv + ["-n"]), 0)
        self.assertFalse(json_path.exists())  # -n 不写盘
        self.assertEqual(M.main(argv), 0)
        self.assertTrue(json_path.exists() and report_path.exists())
        self.assertEqual(M.main(argv + ["--check"]), 0)


# --------------------------------------------------------------------------- #
# 产物聚合断言（真实数据）
# --------------------------------------------------------------------------- #


class GeneratedDataTest(unittest.TestCase):
    def setUp(self) -> None:
        if not GENERATED.exists():
            self.skipTest(f"产物不存在：{GENERATED}")
        self.doc = generated_doc()
        self.counts = self.doc["counts"]

    def test_level_count_matches_client(self) -> None:
        self.assertEqual(self.counts["levels"], 1809)
        self.assertEqual(self.counts["clientLevels"], 1809)
        self.assertEqual(len(self.doc["levels"]), 1809)

    def test_conveyor_levels(self) -> None:
        """任务要求的 349 关：有 ``ConveyorSeedBankProperties`` 卡槽表的关卡数。"""
        self.assertEqual(self.counts["withConveyorSeedBank"], 349)
        self.assertEqual(self.counts["withConveyorChanges"], 132)
        with_slots = sum(
            1 for record in self.doc["levels"].values()
            if record["conveyor"] and record["conveyor"].get("slots")
        )
        self.assertEqual(with_slots, 345)

    def test_protect_levels(self) -> None:
        """任务要求的 286 关保护植物。"""
        self.assertEqual(self.counts["withProtect"], 286)
        for level_id, record in self.doc["levels"].items():
            payload = record["protectThePlant"]
            if payload is None:
                continue
            self.assertIsInstance(payload["mustProtectCount"], int)
            self.assertIsInstance(payload["plants"], list)
            self.assertTrue(level_id)  # 客户端 id，形如 beach_23

    def test_identity_mapping_is_bijective_on_real_data(self) -> None:
        self.assertEqual(self.counts["packagesResolved"], 1809)
        self.assertEqual(self.counts["packagesMissing"], 0)
        self.assertEqual(self.counts["packagesShared"], 0)
        self.assertEqual(self.counts["packagesAmbiguous"], 0)

    def test_counts_are_self_consistent(self) -> None:
        null_counts = {name: 0 for name in M.MECHANICS}
        for record in self.doc["levels"].values():
            for name in M.MECHANICS:
                if record[name] is None:
                    null_counts[name] += 1
        self.assertEqual(null_counts["conveyor"], 1809 - self.counts["withConveyor"])
        self.assertEqual(null_counts["protectThePlant"], 1809 - self.counts["withProtect"])
        self.assertEqual(null_counts["boardGrid"], 1809 - self.counts["withBoardGrid"])
        self.assertEqual(self.counts["unknownMechanics"], len(self.doc["unknowns"]))

    def test_every_level_has_source_package(self) -> None:
        for level_id, record in self.doc["levels"].items():
            package = record["source"]["package"]
            self.assertIsNotNone(package, level_id)
            self.assertTrue(package.startswith("pkg_"), level_id)
            self.assertTrue(package.endswith("_LevelDefinition.json"), level_id)

    def test_spawners_have_wave_attribution(self) -> None:
        """所有带波次的记录（spawners + 传输带改动 + 事件）都落在 resolved/unresolved 里。"""
        total = 0
        unresolved = 0
        for record in self.doc["levels"].values():
            for kind, items in (record["spawners"] or {}).items():
                if kind == "jittered":
                    # 聚合摘要：waves 是 {波号: 对象数}，配 waveUnresolved 必须凑回 objects。
                    self.assertIsInstance(items, dict, "jittered 应该是聚合摘要而不是列表")
                    resolved = sum(items["waves"].values())
                    self.assertEqual(resolved + items["waveUnresolved"], items["objects"])
                    total += items["objects"]
                    unresolved += items["waveUnresolved"]
                    continue
                self.assertIsInstance(items, list, f"{kind} 应保持逐条列表")
                for item in items:
                    total += 1
                    if item["wave"] is None:
                        unresolved += 1
            conveyor = record["conveyor"] or {}
            for item in conveyor.get("changes") or []:
                total += 1
                if item["wave"] is None:
                    unresolved += 1
            events = record["events"] or {}
            for item in (events.get("tide") or []) + (events.get("frost") or []):
                total += 1
                if item["wave"] is None:
                    unresolved += 1
        self.assertEqual(total, self.counts["waveResolved"] + self.counts["waveUnresolved"])
        self.assertEqual(unresolved, self.counts["waveUnresolved"])
        self.assertLess(unresolved / total, 0.05)  # 实测 <2%

    def test_jittered_pool_is_aggregated_not_dumped(self) -> None:
        """jittered 只留聚合（objects/total/pool），不再逐条落 12 万条僵尸条目。"""
        seen = 0
        entries = 0
        for level_id, record in self.doc["levels"].items():
            summary = (record["spawners"] or {}).get("jittered")
            if summary is None:
                continue
            seen += 1
            # 必带五个键；additionalPlantfood / dynamicPlantfood 只在非零时出现。
            self.assertLessEqual(
                {"objects", "total", "waves", "waveUnresolved", "pool"}, set(summary),
                f"{level_id} 的 jittered 摘要缺字段",
            )
            self.assertLessEqual(
                set(summary),
                {"objects", "total", "waves", "waveUnresolved", "pool",
                 "additionalPlantfood", "dynamicPlantfood"},
                f"{level_id} 的 jittered 摘要混进了不该有的字段",
            )
            self.assertNotIn("zombies", summary, "jittered 不应再带逐条 zombies")
            self.assertEqual(summary["total"], sum(item["count"] for item in summary["pool"].values()))
            entries += summary["total"]
            for zombie_id, item in summary["pool"].items():
                self.assertTrue(zombie_id.startswith("RTID("), zombie_id)
                self.assertGreater(item["count"], 0)
                if "rows" in item:
                    # 行号原版既可能是 int 也可能是数字字符串，排序键与聚合端保持一致。
                    self.assertEqual(item["rows"],
                                     sorted(set(item["rows"]), key=M._sort_key))
        self.assertEqual(seen, self.counts["spawnerByKind"]["jittered"])
        self.assertGreater(entries, 100000)  # 实测 121018 条压成聚合后仍在总数上对得上

    def test_sentinels_are_present_and_counted(self) -> None:
        self.assertGreater(self.counts["sentinels"], 0)
        self.assertEqual(sum(row["count"] for row in self.doc["sentinels"]),
                         self.counts["sentinels"])
        values = {row["value"] for row in self.doc["sentinels"]}
        self.assertTrue(values <= {-1, 2147483647})


if __name__ == "__main__":
    unittest.main()
