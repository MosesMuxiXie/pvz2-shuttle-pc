// S5.9: the shot table has to be the source of speed / hit box / trajectory, not the two global
// constants the engine ran on before. These tests pin the numbers the pack actually ships and prove
// that a spawn reads them (rather than just that a table exists).
#include "catalog.hpp"
#include "engine/projectile_table.hpp"
#include "engine/tuning.hpp"
#include "engine/world.hpp"

#include <cmath>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using pvz::Catalog;
using pvz::CatalogOptions;
using pvz::LevelDefinition;
using pvz::engine::EntityId;
using pvz::engine::ProjectileSpec;
using pvz::engine::ProjectileTable;
using pvz::engine::ShotEntity;
using pvz::engine::Trajectory;
using pvz::engine::World;
using pvz::engine::WorldOptions;

void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

Catalog load(const std::filesystem::path& content, const std::filesystem::path& pack) {
    CatalogOptions options;
    options.contentPack = pack;
    return pvz::loadCatalog(content, options);
}

LevelDefinition lawn(const Catalog& catalog, const std::string& id) {
    LevelDefinition level = catalog.levels.at("frontyard_1");
    level.id = id;
    level.waves.clear(); // nothing walks in unless a test asks for it
    level.sun = 9999;
    level.deck.clear();
    return level;
}

const ShotEntity* shotById(const World& world, EntityId id) {
    for (const auto& shot : world.shots()) {
        if (shot.id == id) return &shot;
    }
    return nullptr;
}

bool hasEvent(const World& world, const std::string& type) {
    for (const auto& event : world.events()) {
        const auto kind = event.find("type");
        if (kind != event.end() && kind->is_string() && kind->get<std::string>() == type) return true;
    }
    return false;
}

void testTableLoads(const Catalog& catalog) {
    const ProjectileTable& table = ProjectileTable::shared();
    check(table.size() == 602, "the pack ships 602 projectile rows, got " + std::to_string(table.size()));
    check(table.trajectoryCount(Trajectory::straight) == 374, "374 rows are straight shots");
    check(table.trajectoryCount(Trajectory::arc) == 118, "118 rows are lobbed arcs");
    check(table.trajectoryCount(Trajectory::drop) == 59, "59 rows are falling drops");
    check(table.trajectoryCount(Trajectory::stationary) == 42, "42 rows are static");
    check(table.trajectoryCount(Trajectory::unknown) == 9, "9 rows carry no trajectory");
    check(table.withSplash() == 180,
          "180 rows declare splash damage of their own (217 rows carry a splash object, 37 of them with no damage)");
    check(table.withPierce() == 41,
          "41 rows declare a pierce ramp; only two of them also cap the number of hits");
    const ProjectileSpec* seeker = table.find("HeathSeekerDefaultProjectile");
    check(seeker != nullptr && seeker->hasPierce && seeker->pierceHits == 3,
          "HeathSeekerDefaultProjectile caps at three targets");
    const ProjectileSpec* tudo = table.find("TudoDefaultProjectile");
    check(tudo != nullptr && tudo->hasPierce && tudo->pierceHits == 5, "TudoDefaultProjectile caps at five targets");
    const ProjectileSpec* noCap = table.find("AquaWeedShark");
    check(noCap != nullptr && noCap->hasPierce && noCap->pierceHits == 0,
          "39 of the 41 pierce rows record no hit cap at all; they must not invent one");
    (void)catalog;
}

void testPeaUsesTableNumbers() {
    const ProjectileTable& table = ProjectileTable::shared();
    const ProjectileSpec* pea = table.find("PeaDefault");
    check(pea != nullptr, "PeaDefault must be in the table");
    check(pea->trajectory == Trajectory::straight, "PeaDefault is a straight shot");
    check(std::abs(pea->speedCols - 5.55) < 0.01, "PeaDefault speed must be 333 px/s = 5.55 cols/s, got " +
                                                      std::to_string(pea->speedCols));
    check(pea->speedCols > pvz::engine::tuning::kShotSpeedColsPerSec,
          "the old constant 5.2 was slower than every pea; the table must win");
    check(std::abs(pea->hitRadiusCols - 0.25) < 1e-9, "PeaDefault hit box is the CollisionRect mode 0.25");
}

void testHitBoxesPerProjectile() {
    const ProjectileTable& table = ProjectileTable::shared();
    const ProjectileSpec* slice = table.find("AcidLemonSliceProjectile");
    check(slice != nullptr, "AcidLemonSliceProjectile must be in the table");
    check(std::abs(slice->hitRadiusCols - 0.3333) < 0.001,
          "a fat projectile keeps its own 0.333 hit box, got " + std::to_string(slice->hitRadiusCols));
    const ProjectileSpec* fat = table.find("AquaWeedShark");
    check(fat != nullptr, "AquaWeedShark must be in the table");
    check(std::abs(fat->hitRadiusCols - 0.5) < 1e-9,
          "the widest common hit box is 0.5, got " + std::to_string(fat->hitRadiusCols));
    check(std::abs(slice->hitRadiusCols - fat->hitRadiusCols) > 0.1,
          "0.333 and 0.5 must be different numbers, otherwise the test proves nothing");
}

void testVariantSelection() {
    const ProjectileTable& table = ProjectileTable::shared();
    const ProjectileSpec* cannon = table.find("CannonballDefault");
    check(cannon != nullptr, "CannonballDefault must be in the table");
    check(cannon->variantPkgs.size() == 2, "CannonballDefault ships two pkg-specific copies, got " +
                                               std::to_string(cannon->variantPkgs.size()));
    check(cannon->hasVariantFor("pkg_0839_LevelDefinition"), "the level pkg copy must be seen");
    check(!cannon->hasVariantFor("pkg_2082_ProjectilePropertySheet"),
          "the canonical pkg is not a variant; asking for it must not claim a fallback");
    check(!cannon->hasVariantFor(""), "an empty pkg never selects a variant");
}

void testUnknownIdFallsBackToConstants(const Catalog& catalog) {
    World world(catalog, lawn(catalog, "s59_unknown"));
    const EntityId id = world.spawnShot(0, 1.5, 30.0, "NoSuchProjectile", 0, 0.0, 0.0, 0);
    const ShotEntity* shot = shotById(world, id);
    check(shot != nullptr, "the shot must exist");
    check(std::abs(shot->speed - pvz::engine::tuning::kShotSpeedColsPerSec) < 1e-9,
          "an unknown projectile keeps the fallback speed, got " + std::to_string(shot->speed));
    check(std::abs(shot->hitRadius - pvz::engine::tuning::kShotHitRadius) < 1e-9,
          "an unknown projectile keeps the fallback hit box");
    check(hasEvent(world, "projectile_unknown"), "an unknown projectile id must be reported, not swallowed");

    WorldOptions off;
    off.projectiles = false;
    World legacy(catalog, lawn(catalog, "s59_unknown_off"), 1, off);
    const EntityId keeping = legacy.spawnShot(0, 1.5, 30.0, "PeaDefault", 0, 0.0, 0.0, 0);
    const ShotEntity* plain = shotById(legacy, keeping);
    check(plain != nullptr, "the legacy shot must exist");
    check(std::abs(plain->speed - pvz::engine::tuning::kShotSpeedColsPerSec) < 1e-9,
          "with the table off every shot keeps 5.2, got " + std::to_string(plain->speed));
    check(!hasEvent(legacy, "projectile_unknown"), "the table being off is not an unknown id");
}

void testTableIdReachesTheShot(const Catalog& catalog) {
    World world(catalog, lawn(catalog, "s59_pea"));
    const EntityId id = world.spawnShot(0, 1.5, 30.0, "PeaDefault", 0, 0.0, 0.0, 0);
    const ShotEntity* shot = shotById(world, id);
    check(shot != nullptr, "the pea must exist");
    check(std::abs(shot->speed - 5.55) < 0.01, "the shot must fly at the table's 5.55, got " +
                                                   std::to_string(shot->speed));

    World fat(catalog, lawn(catalog, "s59_fat"));
    const EntityId slice = fat.spawnShot(0, 1.5, 10.0, "AcidLemonSliceProjectile", 0, 0.0, 0.0, 0);
    const ShotEntity* wide = shotById(fat, slice);
    check(wide != nullptr, "the slice must exist");
    check(std::abs(wide->hitRadius - 0.3333) < 0.001, "the fat shot carries the table's hit box, got " +
                                                          std::to_string(wide->hitRadius));

    World lob(catalog, lawn(catalog, "s59_lob"));
    const EntityId cabbage = lob.spawnShot(0, 1.0, 40.0, "CabbageDefault", 0, 0.0, 0.0, 0);
    const ShotEntity* arc = shotById(lob, cabbage);
    check(arc != nullptr, "the cabbage must exist");
    check(arc->lobbed, "CabbageDefault is an arc and must be marked lobbed");
    check(arc->landX > 1.0, "a lobbed shot lands ahead of the plant, landX=" + std::to_string(arc->landX));
}

void testPeaFlightMatchesTable(const Catalog& catalog) {
    World world(catalog, lawn(catalog, "s59_flight"), 7);
    const std::string placed = world.plant("peashooter", 0, 0);
    check(placed.empty(), "planting the peashooter failed: " + placed);
    const EntityId zombie = [&] {
        world.spawnZombie("basic", 0);
        check(!world.zombies().empty(), "the bait zombie must exist");
        return world.zombies().front().id;
    }();
    world.mutableZombies().front().x = 8.0; // far enough that the pea cannot reach it in one step
    world.mutableZombies().front().hp = 100000;
    world.mutableZombies().front().maxHp = 100000;
    (void)zombie;

    EntityId seen = 0;
    double startX = 0;
    for (int step = 0; step < 300 && seen == 0; ++step) {
        world.step();
        for (const auto& shot : world.shots()) {
            if (shot.projectileType != "PeaDefault") continue;
            seen = shot.id;
            startX = shot.x;
        }
    }
    check(seen != 0, "the peashooter never fired a PeaDefault shot");
    const ShotEntity* shot = shotById(world, seen);
    check(shot != nullptr, "the pea must still be alive one step after spawning");

    const int ticks = 20;
    for (int i = 0; i < ticks; ++i) world.step();
    const ShotEntity* moved = shotById(world, seen);
    check(moved != nullptr, "the pea died before the flight measurement finished");
    const double expected = 5.55 * ticks * pvz::engine::tuning::kStepSeconds;
    check(std::abs((moved->x - startX) - expected) < 0.02,
          "a pea must cover 5.55 cols/s: expected " + std::to_string(expected) + ", got " +
              std::to_string(moved->x - startX));

    // Damage is measured on a single hand-spawned pea: the peashooter's sheet carries two identical
    // projectile actions, so a plant-fired volley puts two peas in the air and they both land in the
    // same window. That is the plant's business (see the S3.2 tests); this one is the shot's.
    World dmg(catalog, lawn(catalog, "s59_damage"), 7);
    dmg.spawnZombie("basic", 0);
    check(!dmg.zombies().empty(), "the damage dummy must exist");
    const EntityId dummy = dmg.zombies().front().id;
    dmg.mutableZombies().front().x = 3.0;
    dmg.mutableZombies().front().hp = 1000;
    dmg.mutableZombies().front().maxHp = 1000;
    dmg.spawnShot(0, 2.0, 30.0, "PeaDefault", 0, 0.0, 0.0, 0);
    for (int i = 0; i < 120 && dmg.zombieById(dummy)->hp >= 1000.0; ++i) dmg.step();
    const double dealt = 1000.0 - dmg.zombieById(dummy)->hp;
    check(std::abs(dealt - 30.0) < 0.001, "one pea deals the 30 damage it was spawned with, got " + std::to_string(dealt));
}

void testLobLandingZone(const Catalog& catalog) {
    World world(catalog, lawn(catalog, "s59_lobzone"), 9);
    const EntityId shotId = world.spawnShot(1, 1.0, 40.0, "CabbageDefault", 0, 0.0, 0.0, 0);
    const ShotEntity* shot = shotById(world, shotId);
    check(shot != nullptr, "the cabbage must exist");
    const double landX = shot->landX;

    world.spawnZombie("basic", 1);
    world.spawnZombie("basic", 1);
    check(world.zombies().size() == 2, "two bait zombies must exist");
    EntityId early = world.zombies()[0].id;
    EntityId late = world.zombies()[1].id;
    world.mutableZombies()[0].x = 2.0;          // between plant and landing
    world.mutableZombies()[0].hp = 1000;
    world.mutableZombies()[1].x = landX;        // exactly where it comes down
    world.mutableZombies()[1].hp = 1000;

    for (int i = 0; i < 200; ++i) {
        if (shotById(world, shotId) == nullptr) break;
        world.step();
    }
    check(world.zombieById(early)->hp >= 1000.0 - 1e-9,
          "a lobbed shot must not hit a zombie it flies over, hp=" + std::to_string(world.zombieById(early)->hp));
    check(world.zombieById(late)->hp < 1000.0,
          "a lobbed shot must hit the landing zone, hp=" + std::to_string(world.zombieById(late)->hp));
}

void run(const Catalog& catalog) {
    testTableLoads(catalog);
    testPeaUsesTableNumbers();
    testHitBoxesPerProjectile();
    testVariantSelection();
    testUnknownIdFallsBackToConstants(catalog);
    testTableIdReachesTheShot(catalog);
    testPeaFlightMatchesTable(catalog);
    testLobLandingZone(catalog);
}

} // namespace

#ifdef _WIN32
int wmain(int argc, wchar_t** argv)
#else
int main(int argc, char** argv)
#endif
{
    if (argc < 4) {
        std::fprintf(stderr, "usage: projectile_table_test <content> <pack> <temp>\n");
        return 2;
    }
    try {
        const Catalog catalog = load(argv[1], argv[2]);
        check(catalog.rules != nullptr, "the projectile test needs the rules pack");
        run(catalog);
    } catch (const std::exception& error) {
        std::fprintf(stderr, "projectile table test failed: %s\n", error.what());
        return 1;
    }
    std::cout << "PASS projectile table\n";
    return 0;
}
