// Proves the generated `ZombieClass` -> behaviour-family table is linked in and that
// `World::spawnZombie` prefers it over the shipped content `behavior` field.
//
// argv: [1] content directory, [2] content pack, [3] scratch directory.

#include "catalog.hpp"
#include "engine/entity.hpp"
#include "engine/world.hpp"
#include "engine/zombie_family.hpp"

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>

namespace fs = std::filesystem;
using pvz::Catalog;
using pvz::CatalogOptions;
using pvz::LevelDefinition;
using pvz::content::ContentPack;
using pvz::engine::World;
using pvz::engine::zombieFamilyCount;
using pvz::engine::zombieFamilyFor;

namespace {

void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error("zombie_family test failed: " + message);
}

const pvz::ZombieDefinition* findZombie(const Catalog& catalog, const std::string& id) {
    const auto it = catalog.zombies.find(id);
    return it == catalog.zombies.end() ? nullptr : &it->second;
}

const LevelDefinition* pickLevel(const Catalog& catalog) {
    const auto it = catalog.levels.find("frontyard_1");
    if (it != catalog.levels.end()) return &it->second;
    if (catalog.levels.empty()) return nullptr;
    return &catalog.levels.begin()->second;
}

void testTable() {
    check(zombieFamilyCount() == 183, "expected 183 mapped ZombieClass rows");
    const struct {
        const char* className;
        const char* family;
    } spots[] = {
        {"ZombieBasic", "walk"},
        {"ZombieZombossMech_Egypt", "gargantuar"},
        {"ZombieModernPoleVaulting", "jump"},
        {"ZombieModernPogo", "jump"},
        {"ZombieLostCityRelicHunter", "steal"},
        {"ZombieCarnieMagician", "summon"},
        {"ZombieModernBalloon", "fly"},
        {"ZombieCakeTank", "gargantuar"},
        {"ZombieZCorpImp", "walk"},
    };
    for (const auto& spot : spots) {
        const std::string got(zombieFamilyFor(spot.className));
        check(got == spot.family,
              std::string("class ") + spot.className + " mapped to " + got + ", want " + spot.family);
    }
    check(zombieFamilyFor("").empty(), "empty class must map to nothing");
    check(zombieFamilyFor("ZombieNotInThisBuild").empty(), "unknown class must map to nothing");
}

void testSpawnPrefersClassTable(const fs::path& contentRoot, const fs::path& pack, const fs::path& scratch) {
    CatalogOptions options;
    options.contentPack = pack;
    Catalog catalog = pvz::loadCatalog(contentRoot, options);
    check(catalog.rules != nullptr, "content pack must load");
    const LevelDefinition* level = pickLevel(catalog);
    check(level != nullptr, "catalog must contain at least one level");

    // A pack type name that content does not ship, with a deliberately wrong
    // `behavior` so the assertion can only pass when the class table wins.
    pvz::ZombieDefinition injected;
    injected.id = "iceage_dodo";
    injected.name = "injected dodo";
    injected.behavior = "walk";
    catalog.zombies[injected.id] = injected;

    World world(catalog, *level, 7);
    check(world.spawnZombie("iceage_dodo", 0), "spawnZombie must accept the injected type");
    const auto snapshot = world.snapshot();
    check(snapshot.zombies.size() == 1, "one zombie expected after spawn");
    const auto& zombie = snapshot.zombies.front();
    check(zombie.className == "ZombieIceAgeDodo",
          "className must come from the pack, got '" + zombie.className + "'");
    const std::string expected(zombieFamilyFor(zombie.className));
    check(!expected.empty(), "the dodo class must be in the generated table");
    check(zombie.family == expected,
          "family must follow the class table (" + expected + "), got " + zombie.family);

    // Content behaviour still decides when the pack has no row for the type.
    World plain(catalog, *level, 7);
    check(plain.spawnZombie("conehead", 0), "conehead must spawn");
    const auto plainSnapshot = plain.snapshot();
    check(plainSnapshot.zombies.size() == 1, "one conehead expected");
    check(plainSnapshot.zombies.front().className.empty(),
          "a client-only id must not claim a pack class");
    check(plainSnapshot.zombies.front().family == "walk",
          "client-only zombie keeps its content family");

    std::error_code ec;
    fs::create_directories(scratch, ec);
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc < 4) {
            std::cerr << "usage: zombie_family_test <content> <pack> <scratch>\n";
            return 2;
        }
        // `argv` is in the active ANSI code page on Windows, not UTF-8: build the
        // paths directly (fs::u8path would reject the CJK temp directory).
        const fs::path contentRoot = fs::path(argv[1]);
        const fs::path pack = fs::path(argv[2]);
        const fs::path scratch = fs::path(argv[3]);
        testTable();
        testSpawnPrefersClassTable(contentRoot, pack, scratch);
        std::cout << "zombie family table: 183 classes -> 6 families, spawn uses it\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
