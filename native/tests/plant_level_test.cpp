// B1 (T90) plant levels: the sheet's own per-level ladder, wired to combat numbers.
//
// `native/generated/plant_levels.json` ships one row per plant and the row's `Values[]` IS the level
// ladder (`Values[i]` = the number at level i+1). Nothing here computes a percentage: the cases below
// pin absolute numbers read off the shipped table, so a regression that starts interpolating shows up
// as a wrong number rather than a plausible one.
//
// Two rules get their own cases because they are the whole contract:
//   * the sheet's cap wins - a save asking for level 99 fights at the plant's own `levelCount`;
//   * a ladder column is only applied where its LEVEL-1 value reproduces the number the pack already
//     ships (106 of the 133 levelling plants agree; 20 disagree, and `buttercup` is the case below).
//     Without that guard a default run could move, which is exactly what the smoke baseline forbids.
#include "catalog.hpp"
#include "engine/plant_levels.hpp"
#include "engine/world.hpp"
#include "progress.hpp"

#include <cmath>
#include <filesystem>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

namespace fs = std::filesystem;
using pvz::Catalog;
using pvz::CatalogOptions;
using pvz::Progress;
using pvz::engine::PlantLevelRow;
using pvz::engine::PlantLevelTable;
using pvz::engine::World;
using pvz::engine::WorldOptions;

[[noreturn]] void fail(const std::string& message) { throw std::runtime_error(message); }

void check(bool condition, const std::string& message) {
    if (!condition) fail(message);
}

void checkNear(double actual, double expected, const std::string& what) {
    if (std::fabs(actual - expected) > 1e-9) {
        fail(what + ": expected " + std::to_string(expected) + ", got " + std::to_string(actual));
    }
}

/// One plant's row, or a hard failure: every case below names a plant it expects the sheet to carry.
const PlantLevelRow& rowOf(const PlantLevelTable& table, const std::string& type) {
    const PlantLevelRow* row = table.find(type);
    if (row == nullptr) fail("the plant level table must carry " + type);
    return *row;
}

/// The ladder of one plant as `stat -> [level 1 .. levelCount]`, which is what the JSON carries.
std::vector<double> ladderOf(const PlantLevelRow& row, const std::string& stat) {
    std::vector<double> values;
    for (int level = 1; level <= row.levelCount; ++level) {
        const auto value = row.value(stat, level);
        if (!value.has_value()) fail(row.type + " must carry " + stat + " at level " + std::to_string(level));
        values.push_back(*value);
    }
    return values;
}

void checkLadder(const PlantLevelRow& row, const std::string& stat,
                 const std::vector<double>& expected) {
    const std::vector<double> actual = ladderOf(row, stat);
    if (actual.size() != expected.size()) {
        fail(row.type + "." + stat + ": expected " + std::to_string(expected.size()) + " levels, got " +
             std::to_string(actual.size()));
    }
    for (std::size_t i = 0; i < expected.size(); ++i) {
        checkNear(actual[i], expected[i],
                  row.type + "." + stat + " level " + std::to_string(i + 1));
    }
}

// ---------------------------------------------------------------- table -----
void testTableShape() {
    const PlantLevelTable& table = PlantLevelTable::shared();
    check(table.loaded(), "the plant level table must load from the generated tree");
    check(table.size() == 323, "the sheet carries 323 plant rows, got " + std::to_string(table.size()));

    const std::vector<std::string> types = table.types();
    check(types.size() == table.size(), "types() must list every row once");
    for (std::size_t i = 1; i < types.size(); ++i) {
        check(types[i - 1] < types[i], "types() must be sorted and unique");
    }

    // Three known shapes: a three-level plant, a ten-level plant, and the damage column the pack's
    // own "last entry wins" flatten picks (`@2`, not `@0`).
    const PlantLevelRow& pea = rowOf(table, "peashooter");
    check(pea.levelCount == 3, "peashooter fights at three levels");
    check(pea.damageStat == "ActionDamageNormal@2",
          "peashooter's damage column must be the greatest SubType, got " + pea.damageStat);
    check(rowOf(table, "blockoli").levelCount == 10, "blockoli carries ten levels");
    check(rowOf(table, "sunflower").levelCount == 3, "sunflower fights at three levels");
}

// ----------------------------------------------------------------- ladder ---
void testAbsoluteLadderIsNotACurve() {
    const PlantLevelTable& table = PlantLevelTable::shared();

    // A three-level shooter: cost falls, hitpoints rise late, the damage column is the `@2` one.
    const PlantLevelRow& pea = rowOf(table, "peashooter");
    checkLadder(pea, "Hitpoints", {300, 300, 500});
    checkLadder(pea, "Cost", {100, 75, 75});
    checkLadder(pea, "PacketCooldown", {5, 5, 5});
    checkLadder(pea, "ActionDamageNormal@2", {30, 35, 45});

    // A producer: its ladder carries no sun column at all. That is the data, not an omission here.
    const PlantLevelRow& sun = rowOf(table, "sunflower");
    checkLadder(sun, "Hitpoints", {300, 350, 500});
    checkLadder(sun, "Cost", {50, 40, 30});
    check(!sun.value("SunValue", 1).has_value(), "sunflower must carry no sun-production column");

    // A ten-level plant, and the reason `levelCount` comes from the ladder: the sheet's own
    // `levelCap` for blockoli is 10, but 99 rows disagree with their own array length.
    checkLadder(rowOf(table, "blockoli"), "Hitpoints",
                {6000, 7000, 8000, 9000, 10000, 11000, 12000, 13000, 14500, 16000});
}

void testClampToTheSheetsOwnCap() {
    using pvz::engine::clampPlantLevel;
    check(clampPlantLevel("peashooter", 99) == 3, "level 99 must clamp to peashooter's three levels");
    check(clampPlantLevel("peashooter", 0) == 1, "level 0 must clamp up to 1");
    check(clampPlantLevel("peashooter", 2) == 2, "a level inside the ladder must be kept");
    check(clampPlantLevel("not_a_plant", 7) == 1, "an unknown plant must stay at level 1");

    const PlantLevelRow& pea = rowOf(PlantLevelTable::shared(), "peashooter");
    check(pea.at(99) == pea.at(3), "at() must clamp to the last level");
    check(pea.at(-4) == pea.at(1), "at() must clamp up to the first level");
}

void testIdentityGuardKeepsForeignColumnsOut() {
    using pvz::engine::leveledValue;
    // The pack says peashooter hp 300 and the ladder's level 1 says 300: level 3 may move it.
    checkNear(*leveledValue("peashooter", "Hitpoints", 3, 300.0), 500.0,
              "peashooter hp at level 3");
    // A number the ladder does not explain is never replaced: the guard rejects it.
    check(!leveledValue("peashooter", "Hitpoints", 3, 999.0).has_value(),
          "a column whose level-1 value disagrees with the pack must not be applied");
    // Level 1 is rejected by definition, which is what keeps a default run byte-identical.
    check(!leveledValue("peashooter", "Hitpoints", 1, 300.0).has_value(),
          "level 1 must never come out of the ladder");
    // `buttercup` is one of the 20 plants whose ladder disagrees with the pack (hp 900 vs 300).
    check(!leveledValue("buttercup", "Hitpoints", 2, 300.0).has_value(),
          "buttercup's hitpoint column must stay out: 900 != 300");
    // A stat the sheet does not carry stays out.
    check(!leveledValue("peashooter", "SunValue", 3, 25.0).has_value(),
          "a stat the sheet has no column for must not be applied");
}

// ---------------------------------------------------------------- progress --
void testProgressRoundTrip() {
    Progress progress;
    progress.plantLevels["peashooter"] = 3;
    progress.plantLevels["sunflower"] = 2;
    const pvz::Json written = pvz::progressToJson(progress);
    check(written.contains("plantLevels"), "a save with levels must write the key");
    check(written["plantLevels"].size() == 2, "two plants, two entries");
    check(written["plantLevels"]["peashooter"] == 3, "the level must survive serialisation");

    const Progress reread = pvz::parseProgress(written, "round-trip");
    check(reread.plantLevels == progress.plantLevels, "load(save(x)) must return the same levels");

    // A save that never raised a plant must not grow the key: that is what keeps every pre-T90 save
    // byte-identical through a round trip.
    const Progress plain;
    const pvz::Json untouched = pvz::progressToJson(plain);
    check(!untouched.contains("plantLevels"), "a default save must not carry a plantLevels key");
    check(pvz::parseProgress(untouched, "default").plantLevels.empty(),
          "a save without the key must load as 'every plant at level 1'");

    // Junk is skipped rather than failing the save, the same policy the landing fields follow.
    const pvz::Json junk = pvz::Json{{"plantLevels", pvz::Json{{"peashooter", "3"}, {"sunflower", 0}}}};
    check(pvz::parseProgress(junk, "junk").plantLevels.empty(),
          "a non-numeric or sub-1 entry must be skipped");
}

// ------------------------------------------------------------------ world ---
void testWorldAppliesTheLadder(const Catalog& catalog) {
    const auto level = catalog.levels.find("frontyard_1");
    check(level != catalog.levels.end(), "the content must carry frontyard_1");

    WorldOptions raised;
    raised.plantLevels["peashooter"] = 3;
    raised.plantLevels["not_a_plant"] = 9; // unknown: capped to 1, so it must not be reported
    World world(catalog, level->second, 11, raised);
    check(world.plantLevel("peashooter") == 3, "the world must hold the requested level");
    check(world.plantLevel("not_a_plant") == 1, "an unknown plant must read as level 1");
    check(world.plantLevelsApplied().size() == 1,
          "only plants above level 1 may be reported, got " +
              std::to_string(world.plantLevelsApplied().size()));
    check(world.plantLevelsApplied().at("peashooter") == 3, "the report must name the level");

    check(world.plant("peashooter", 2, 0).empty(), "frontyard_1 must accept a peashooter");
    const auto* planted = world.plantAt(2, 0);
    check(planted != nullptr, "the peashooter must stand on (2,0)");
    checkNear(planted->maxHp, 500.0, "a level-3 peashooter has 500 hp");

    // The same board with no request: the pack numbers, untouched.
    World plain(catalog, level->second, 11);
    check(plain.plantLevelsApplied().empty(), "a default world must report nothing applied");
    check(plain.plant("peashooter", 2, 0).empty(), "the default world must accept the same plant");
    const auto* baseline = plain.plantAt(2, 0);
    check(baseline != nullptr, "the default peashooter must stand on (2,0)");
    checkNear(baseline->maxHp, 300.0, "a level-1 peashooter keeps the pack's 300 hp");
}

void testLevelDamageFollowsTheSameGuard(const Catalog& catalog) {
    const auto level = catalog.levels.find("frontyard_1");
    check(level != catalog.levels.end(), "the content must carry frontyard_1");

    WorldOptions raised;
    raised.plantLevels["peashooter"] = 3;
    World world(catalog, level->second, 12, raised);
    checkNear(world.levelDamage("peashooter", 30.0), 45.0, "level 3 peashooter hits for 45");
    checkNear(world.levelDamage("peashooter", 20.0), 20.0,
              "a number the ladder's level 1 does not explain must be left alone");
    checkNear(world.levelDamage("sunflower", 0.0), 0.0, "a zero stays zero");

    World plain(catalog, level->second, 12);
    checkNear(plain.levelDamage("peashooter", 30.0), 30.0, "a default world keeps the pack damage");
}

void run(const fs::path& content, const fs::path& pack) {
    CatalogOptions options;
    options.contentPack = pack;
    const Catalog catalog = pvz::loadCatalog(content, options);
    check(!catalog.levels.empty(), "the content must carry levels for the plant level tests");

    testTableShape();
    testAbsoluteLadderIsNotACurve();
    testClampToTheSheetsOwnCap();
    testIdentityGuardKeepsForeignColumnsOut();
    testProgressRoundTrip();
    testWorldAppliesTheLadder(catalog);
    testLevelDamageFollowsTheSameGuard(catalog);
}

} // namespace

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    if (argc < 3) {
        std::cerr << "usage: plant_level_test <content> <pack>\n";
        return 2;
    }
    try {
        run(fs::path{argv[1]}, fs::path{argv[2]});
    } catch (const std::exception& error) {
        std::cerr << "plant level test failed: " << error.what() << '\n';
        return 1;
    }
    std::cout << "plant level tests passed\n";
    return 0;
}
