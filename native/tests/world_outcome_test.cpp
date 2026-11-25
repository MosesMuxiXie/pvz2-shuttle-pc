// Regression tests for World outcome/statistics accounting.
//
// These cover three defects that the first data-driven kernel shipped with:
//   1. the victory branch was never exercised by any test or smoke scenario;
//   2. `noteUnwiredPlant/Zombie` were called every tick, so the counters counted
//      frames instead of families;
//   3. `removeZombie` (a despawn) incremented the kill counter.
#include "catalog.hpp"
#include "engine/world.hpp"

#include <cstdio>
#include <stdexcept>
#include <string>

namespace {

void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

pvz::LevelDefinition singleZombieLevel() {
    pvz::LevelDefinition level;
    level.id = "outcome_probe";
    level.world = "frontyard";
    level.title = "outcome probe";
    level.sun = 500;
    level.rows = 5;
    level.cols = 9;
    level.flags = 1;
    pvz::WaveDefinition wave;
    wave.delay = 2.0;
    wave.flag = false;
    pvz::ZombieSpawn spawn;
    spawn.type = "basic";
    spawn.row = 2;
    wave.zombies.push_back(spawn);
    level.waves.push_back(wave);
    return level;
}

void testVictoryBranch(const pvz::Catalog& catalog) {
    auto level = singleZombieLevel();
    pvz::engine::World world(catalog, level, 3u);
    world.advance(2.2);
    check(world.zombies().size() == 1, "the probe wave must have spawned exactly one zombie");
    const auto& zombie = world.zombies().front();
    world.explode(zombie.row, zombie.x, 2.0, 1e9, 0.0);
    for (int i = 0; i < 120 && !world.finished(); ++i) world.advance(pvz::engine::tuning::kStepSeconds);
    check(world.status() == "won", "killing the last scheduled zombie must win, got " + world.status());
    check(world.killedZombies() == 1, "the killed counter must count the exploded zombie");
    check(world.removedZombies() == 0, "a kill must not be reported as a removal");
}

void testUnwiredCountsFamiliesNotFrames(const pvz::Catalog& catalog) {
    auto level = singleZombieLevel();
    pvz::engine::World world(catalog, level, 1u);
    for (int i = 0; i < 50; ++i) {
        world.noteUnwiredPlant("bogus_family");
        world.noteUnwiredZombie("bogus_family");
    }
    check(world.unwiredPlants() == 1, "one unwired family must be counted once, got " +
                                          std::to_string(world.unwiredPlants()));
    check(world.unwiredZombies() == 1, "one unwired zombie family must be counted once, got " +
                                           std::to_string(world.unwiredZombies()));
    world.noteUnwiredPlant("other_family");
    check(world.unwiredPlants() == 2, "a second family must still be counted");
    check(world.unwiredPlantNames().size() == 2, "both names must be remembered");
}

void testRemovalIsNotAKill(const pvz::Catalog& catalog) {
    auto level = singleZombieLevel();
    pvz::engine::World world(catalog, level, 1u);
    check(world.spawnZombie("basic", 1), "spawnZombie must accept a known type");
    const auto id = world.zombies().front().id;
    world.removeZombie(id);
    check(world.killedZombies() == 0, "removeZombie must not increment the kill counter");
    check(world.removedZombies() == 1, "removeZombie must increment the removed counter");
    check(world.spawnedZombies() == 1, "the spawn counter must stay untouched");
}

void testUnknownZombieTypeIsRejected(const pvz::Catalog& catalog) {
    auto level = singleZombieLevel();
    pvz::engine::World world(catalog, level, 1u);
    check(!world.spawnZombie("no_such_zombie", 0), "an unknown zombie type must be refused");
    check(world.spawnedZombies() == 0, "a refused spawn must not move the counter");
}

} // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: world_outcome_test <content> <pack>\n");
        return 2;
    }
    try {
        pvz::CatalogOptions options;
        options.contentPack = std::filesystem::path(argv[2]);
        const auto catalog = pvz::loadCatalog(std::filesystem::path(argv[1]), options);
        testVictoryBranch(catalog);
        testUnwiredCountsFamiliesNotFrames(catalog);
        testRemovalIsNotAKill(catalog);
        testUnknownZombieTypeIsRejected(catalog);
        std::printf("world outcome tests passed\n");
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "world outcome test failed: %s\n", error.what());
        return 1;
    }
}
