#include "catalog.hpp"
#include "content/model.hpp"
#include "engine/registry.hpp"
#include "engine/replay.hpp"
#include "engine/world.hpp"
#include "engine/plant_family.hpp"
#include "engine/zombie_family.hpp"
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <set>
#include <stdexcept>
#include <string>

namespace fs = std::filesystem;
using namespace pvz;
using namespace pvz::engine;

namespace {
void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

Catalog load(const fs::path& content, const fs::path& pack) {
    CatalogOptions options;
    if (!pack.empty()) options.contentPack = pack;
    return loadCatalog(content, options);
}

LevelDefinition synthetic(const LevelDefinition& base, int rows, int cols, const std::string& id) {
    LevelDefinition level = base;
    level.id = id;
    level.rows = rows;
    level.cols = cols;
    return level;
}

std::uint64_t runQuietly(const Catalog& catalog, const LevelDefinition& level, double seconds,
                         std::uint32_t seed = 1) {
    World world(catalog, level, seed);
    Script script;
    runScript(world, script, seconds);
    return world.hash();
}

void testDeterminism(const Catalog& catalog) {
    const auto& level = catalog.levels.at("frontyard_1");
    const auto a = runQuietly(catalog, level, 90);
    const auto b = runQuietly(catalog, level, 90);
    const auto c = runQuietly(catalog, level, 90);
    check(a == b && b == c, "same seed and script must produce identical hashes");

    // Fixed-step integration must not depend on how wall-clock time is sliced.
    World one(catalog, level, 1);
    one.advance(90.0);
    World many(catalog, level, 1);
    for (int i = 0; i < 180; ++i) many.advance(0.5);
    check(one.tick() == many.tick(), "chunked advance must reach the same tick, got " +
                                         std::to_string(one.tick()) + " vs " + std::to_string(many.tick()));
    check(one.hash() == many.hash(), "chunked advance must reach the same state hash");

    // Every shipped spawn names its row, so the seed only records provenance today; when
    // random row selection lands it must be honoured, and this check keeps that honest.
    World seeded(catalog, level, 7);
    check(seeded.snapshot().seed == 7, "the world must carry its seed");
}

void testGeometry(const Catalog& catalog) {
    const auto& base = catalog.levels.at("frontyard_1");
    check(base.rows == 5 && base.cols == 9, "frontyard_1 is a 5x9 lawn");
    World wide(catalog, synthetic(base, 6, 10, "synthetic_6x10"));
    check(wide.rows() == 6 && wide.cols() == 10, "6x10 geometry is honoured");
    const auto error = wide.plant("sunflower", 5, 9);
    check(error.empty(), "planting in the last 6x10 cell must succeed, got: " + error);
    check(!wide.plant("sunflower", 6, 0).empty(), "row 6 is out of bounds");
    check(!wide.plant("sunflower", 0, 10).empty(), "column 10 is out of bounds");
    check(!wide.plant("not_a_plant", 0, 0).empty(), "unknown plant types are rejected by name");
}

void testDirector(const Catalog& catalog) {
    std::size_t levels = 0, empty = 0, scheduled = 0;
    for (const auto& [id, level] : catalog.levels) {
        std::mt19937 rng(1);
        Director director(level, level.rows > 0 ? level.rows : 5, rng);
        std::size_t expected = 0;
        for (const auto& wave : level.waves) expected += wave.zombies.size();
        check(director.total() == expected, "director schedule must match the level's spawn count for " + id);
        check(director.waveCount() == level.waves.size(), "wave count mismatch for " + id);
        ++levels;
        scheduled += director.total();
        if (director.total() == 0) ++empty;
    }
    check(levels == 1809, "every level must produce a director");
    check(scheduled > 10000, "the corpus must schedule a realistic number of zombies");
    check(empty * 20 < levels, "at most 5% of levels may have no zombies at all");
}

void testTwentySixWorlds(const Catalog& catalog, const fs::path& tempRoot) {
    std::set<std::string> worlds;
    std::map<std::string, const LevelDefinition*> first;
    for (const auto& [id, level] : catalog.levels) {
        worlds.insert(level.world);
        const auto it = first.find(level.world);
        if (it == first.end() || level.index < it->second->index) first[level.world] = &level;
    }
    check(worlds.size() == 26, "catalog must expose 26 worlds, saw " + std::to_string(worlds.size()));
    std::size_t ran = 0;
    std::size_t spawnedSome = 0;
    // Every world run is written out: the file is the artefact a human reads when a
    // world starts misbehaving, and writing it is also the only reason argv[3] exists.
    std::ostringstream report;
    for (const auto& [world, level] : first) {
        check(level != nullptr, "missing representative level for " + world);
        World instance(catalog, *level, 1);
        Script script;
        runScript(instance, script, 120);
        const auto status = instance.status();
        check(status == "playing" || status == "won" || status == "lost",
              "unexpected status for " + level->id + ": " + status);
        // A world that is still playing after 120 s must have stepped all 120 s: a frozen
        // clock used to satisfy the status check above trivially.
        if (status == "playing") {
            check(instance.tick() == 7200,
                  "a playing world must have stepped 120 s, tick " + level->id + "=" +
                      std::to_string(instance.tick()));
        } else {
            check(instance.tick() <= 7200,
                  "a finished world cannot have stepped past 120 s: " + level->id);
        }
        check(instance.hash() != 0, "hash must be non-zero for " + level->id);
        check(instance.rows() == instance.snapshot().rows && instance.cols() == instance.snapshot().cols,
              "snapshot geometry must match the world for " + level->id);
        report << world << ' ' << level->id << ' ' << instance.rows() << 'x' << instance.cols() << ' '
               << status << " tick=" << instance.tick() << " spawned=" << instance.spawnedZombies()
               << " hash=0x" << std::hex << instance.hash() << std::dec << '\n';

        // A world with waves must actually spawn zombies within 120 s.
        if (instance.waves() > 0) {
            check(instance.spawnedZombies() > 0,
                  "waves never spawned a zombie in " + level->id);
            ++spawnedSome;
        }

        // Same seed, same level, same elapsed time => same hash (per-world determinism).
        World again(catalog, *level, 1);
        runScript(again, script, 120);
        check(again.hash() == instance.hash(), "world " + world + " is not deterministic");

        // Board size must follow the compiled table when one exists.
        const auto boardIt = catalog.boards.find(world);
        if (boardIt != catalog.boards.end()) {
            check(instance.rows() == boardIt->second.rows && instance.cols() == boardIt->second.cols,
                  "board size drift in " + world + ": engine " + std::to_string(instance.rows()) + "x" +
                      std::to_string(instance.cols()) + " vs table " + std::to_string(boardIt->second.rows) + "x" +
                      std::to_string(boardIt->second.cols));
        }
        ++ran;
    }
    check(ran == 26, "every world must run headless, ran " + std::to_string(ran));
    check(spawnedSome >= 20, "at least 20 worlds must schedule zombies, saw " + std::to_string(spawnedSome));

    check(!tempRoot.empty(), "the engine test needs a temp root for its world report");
    std::error_code ec;
    fs::create_directories(tempRoot, ec);
    const fs::path reportPath = tempRoot / "engine_worlds.txt";
    {
        std::ofstream out(reportPath, std::ios::binary | std::ios::trunc);
        check(out.good(), "cannot write the world report to " + reportPath.string());
        out << report.str();
    }
    std::ifstream in(reportPath);
    check(in.good(), "cannot read back the world report from " + reportPath.string());
    std::size_t lines = 0;
    std::string line;
    while (std::getline(in, line)) {
        if (!line.empty()) ++lines;
    }
    check(lines == 26, "the world report must hold one line per world, got " + std::to_string(lines));
}

void testPackOnlyPlant(const Catalog& catalog) {
    check(plantFamilyCount() == 339, "the plant family table must cover all 339 original types");

    // The shipped content JSON names 147 plants; everything else can only come
    // from the pack. Pick a cheap type and prove it can live on the lawn.
    const std::string id = "ailmint";
    check(catalog.plants.find(id) == catalog.plants.end(), id + " must be pack-only, not in content JSON");
    check(catalog.rules != nullptr && catalog.rules->findPlant(id) != nullptr, id + " must exist in the pack");

    LevelDefinition level = catalog.levels.at("beach_23");
    level.deck.clear(); // exercise the plant path without deck filtering
    // beach_23 is a conveyor level with initial plants, and S5.13 routes `plant()` through the
    // conveyor there. This test is about the deck-free plant path, so the mechanics layer is off.
    pvz::engine::WorldOptions options;
    options.mechanics = false;
    World world(catalog, level, 1, options);
    world.addSunToBank(2000);
    const std::string refusal = world.plant(id, 2, 3);
    check(refusal.empty(), "a pack-only plant must be plantable, got: " + refusal);
    check(world.plants().size() == 1, "the pack-only plant must be on the lawn");
    const auto& planted = world.plants().front();
    const std::string_view judged = plantFamilyFor(id);
    check(!judged.empty(), "the family table must judge " + id);
    check(planted.family == judged, "the planted family must come from the table: " + planted.family);
    check(planted.maxHp > 0, "the pack-only plant must take hitpoints from the pack");
    check(world.snapshot().plants.size() == 1, "the snapshot must expose the pack-only plant");

    // An id in neither content nor pack stays a hard error.
    check(world.plant("definitely_not_a_plant", 0, 0).rfind("unknown plant", 0) == 0,
          "an id missing from both sources must be rejected");
}

void testEffectEventsAreEmitted(const Catalog& catalog) {
    // T38 (audio) needs hooks it can trust. The engine never plays a sound, so the only contract
    // it can give the audio layer is that these three events exist, once per real occurrence.
    World world(catalog, catalog.levels.at("frontyard_1"), 11);
    check(world.plant("sunflower", 0, 0).empty(), "sunflower can be planted");
    check(world.plant("peashooter", 1, 1).empty(), "peashooter can be planted");
    check(world.spawnZombie("basic", 1), "a basic zombie can enter row 1");

    int shotsFired = 0;
    int shotHits = 0;
    int suns = 0;
    for (int i = 0; i < 60 * 30; ++i) {
        world.advance(1.0 / 60.0);
        for (const auto& event : world.events()) {
            const std::string type = event.value("type", std::string{});
            if (type == "shot_fired") ++shotsFired;
            if (type == "shot_hit") ++shotHits;
            if (type == "sun_spawned") ++suns;
        }
        if (shotsFired > 0 && shotHits > 0 && suns > 0) break;
    }
    check(shotsFired > 0, "a peashooter must emit shot_fired (audio has no other way to know)");
    check(shotHits > 0, "a hit must emit shot_hit, got " + std::to_string(shotHits));
    check(suns > 0, "a sunflower must emit sun_spawned");
}

void testRegistryTable() {
    const auto& registry = Registry::shared();
    for (const auto& family : Registry::plantFamilies()) {
        check(registry.plantBehavior(family) != nullptr, "plant family not wired: " + family);
    }
    for (const auto& family : Registry::zombieFamilies()) {
        check(registry.zombieBehavior(family) != nullptr, "zombie family not wired: " + family);
    }
    check(registry.plantBehavior("nonsense") == nullptr, "unknown plant families must stay unknown");
    check(registry.zombieBehavior("nonsense") == nullptr, "unknown zombie families must stay unknown");
    check(Registry::defaultPlant() != nullptr && Registry::defaultZombie() != nullptr,
          "defaults must always be callable");
}

void testShotsAndEating(const Catalog& catalog) {
    {
        World world(catalog, catalog.levels.at("frontyard_1"), 3);
        check(world.plant("peashooter", 2, 0).empty(), "peashooter can be planted");
        check(world.spawnZombie("basic", 2), "a basic zombie can enter row 2");
        const auto hpBefore = world.zombies().front().hp;
        world.advance(12);
        const bool hurt = world.killedZombies() > 0 || world.zombies().empty() ||
                          (!world.zombies().empty() && world.zombies().front().hp < hpBefore);
        check(hurt, "a peashooter must damage the zombie in its row");
    }

    {
        // Eating is a real state, not just a damage tick: the zombie must latch on
        // to the plant and the plant must lose hitpoints.
        World world(catalog, catalog.levels.at("frontyard_1"), 4);
        check(world.plant("wallnut", 3, 5).empty(), "wallnut can be planted at (3,5)");
        check(world.spawnZombie("basic", 3), "a basic zombie can enter row 3");
        const double nutHpBefore = world.plants().front().hp;
        double hpAfterEating = nutHpBefore;
        bool sawEating = false;
        for (int i = 0; i < 60 * 40 && !world.plants().empty(); ++i) {
            world.advance(1.0 / 60.0);
            for (const auto& z : world.zombies()) {
                if (z.state == ZombieState::eating) sawEating = true;
            }
            if (!world.plants().empty()) hpAfterEating = world.plants().front().hp;
            if (sawEating && hpAfterEating < nutHpBefore) break;
        }
        check(sawEating, "a zombie that reaches a plant must report eating=true");
        check(hpAfterEating < nutHpBefore,
              "an eating zombie must drain plant hitpoints (" + std::to_string(nutHpBefore) + " -> " +
                  std::to_string(hpAfterEating) + ")");
        check(world.plants().empty() || world.plants().front().hp < nutHpBefore, "the plant must stay the same entity");
    }

    {
        // A fly-family zombie walks over plants without eating them.
        std::string flyId;
        for (const auto& zombie : catalog.rules->zombies) {
            if (zombieFamilyFor(zombie.className) == "fly") {
                flyId = zombie.id;
                break;
            }
        }
        check(!flyId.empty(), "the pack must contain at least one fly-family zombie");
        World world(catalog, catalog.levels.at("frontyard_1"), 5);
        check(world.plant("wallnut", 1, 5).empty(), "wallnut can be planted at (1,5)");
        check(world.spawnZombie(flyId, 1), "a pack-only fly zombie must spawn from the pack: " + flyId);
        const auto& spawned = world.zombies().front();
        check(spawned.family == "fly", "pack-only zombie must take its family from the class table: " + spawned.family);
        check(!spawned.className.empty(), "pack-only zombie must carry its class name");
        check(spawned.hp > 0 && spawned.speed > 0 && spawned.eatDps > 0,
              "pack-only zombie must take hp/speed/eatDps from the pack");
        world.advance(20);
        const auto& plants = world.plants();
        check(!plants.empty(), "a fly-family zombie must not eat the plant it flies over (" + flyId + ")");
        check(plants.front().hp == plants.front().maxHp, "flying zombies must not drain hitpoints (" + flyId + ")");
    }
}

void testVaultSkipsPlantAndMowerIsNotAPlantKill(const Catalog& catalog) {
    // B1 regression. The old hop landed inside its own trigger window, so a pole
    // vaulter bounced in place forever; it also ate wall-nuts because eating is
    // resolved before the family hook ran. One hop, no chewing, and the lane mower
    // (not a plant) is the thing that removes it.
    std::string jumpId;
    for (const auto& zombie : catalog.rules->zombies) {
        if (zombieFamilyFor(zombie.className) == "jump") {
            jumpId = zombie.id;
            break;
        }
    }
    check(!jumpId.empty(), "the pack must contain at least one jump-family zombie");

    auto level = catalog.levels.at("beach_23");
    level.deck = {"wallnut"};
    level.waves.clear();
    level.rows = 5;
    level.cols = 9;
    World world(catalog, level, 11);
    world.addSunToBank(500);
    check(world.plant("wallnut", 2, 4).empty(), "wallnut can be planted at (2,4)");
    check(world.spawnZombie(jumpId, 2), "a pack-only jump zombie must spawn: " + jumpId);
    const double nutHp = world.plants().front().hp;

    for (int i = 0; i < 60 * 180 && !world.finished(); ++i) world.advance(1.0 / 60.0);

    int hops = 0;
    double hopFrom = 0.0;
    double hopTo = 0.0;
    double hopDistance = 0.0;
    int hopJumped = 0;
    std::uint64_t hopTick = 0;
    for (const auto& event : world.events()) {
        if (event.value("type", std::string{}) != "zombie_hop") continue;
        ++hops;
        const auto& payload = event.value("details", Json::object());
        hopTick = event.value("tick", std::uint64_t{0});
        hopFrom = payload.value("from", 0.0);
        hopTo = payload.value("to", 0.0);
        hopDistance = payload.value("distance", 0.0);
        hopJumped = payload.value("jump", 0);
    }

    check(!world.plants().empty(), "the vaulted plant must survive: a vaulter must not eat it");
    check(world.plants().front().hp == nutHp, "vaulting must cost the plant no hitpoints");
    check(hops == 1, "a vaulter must hop exactly once per plant (hopped " + std::to_string(hops) + ")");
    // S5.12: the hop has to carry its own evidence. `distance` is what the old event was
    // missing, so "the vaulter really moved" could only be inferred from the level settling.
    const double nutCentre = world.centerOf(4);
    check(hopDistance > 0.0,
          "a hop must record a positive distance, got " + std::to_string(hopDistance) + " at tick " +
              std::to_string(hopTick));
    check(std::abs((hopFrom - hopDistance) - hopTo) < 1e-9,
          "the hop's from/to/distance must agree: from " + std::to_string(hopFrom) + " - distance " +
              std::to_string(hopDistance) + " != to " + std::to_string(hopTo));
    check(hopTo < nutCentre,
          "the vaulter must land left of the plant centre, got " + std::to_string(hopTo) + " vs " +
              std::to_string(nutCentre));
    check(hopJumped == 1, "crossing the plant is a real jump (jump=1), got " + std::to_string(hopJumped));
    // S5.12: the trigger window must be contact-sized. A window that still reached
    // kEatRangeCols would launch the hop a whole column early, and this is the assertion
    // that notices (see the reverse probe in docs/reviews/2026-11-20-audit-fixes.md).
    check(hopFrom <= nutCentre + tuning::kVaultTriggerMaxCols + 0.01,
          "a hop must only start at contact: from " + std::to_string(hopFrom) + " is outside the " +
              std::to_string(tuning::kVaultTriggerMaxCols) + "-column window around " +
              std::to_string(nutCentre));
    check(world.finished(), "the level must settle after the vaulter reaches the house");
    check(world.mowerKills() == 1, "the lane mower must claim the kill");
    check(world.killedZombies() == 0, "a mower kill is not a plant kill");
}

void testInputScript(const Catalog& catalog) {
    Script script;
    script.seed = 5;
    script.inputs.push_back(ScriptInput{0, "plant", "sunflower", 2, 0});
    script.inputs.push_back(ScriptInput{120, "plant", "peashooter", 2, 1});
    script.inputs.push_back(ScriptInput{600, "spawn", "basic", 2});
    World world(catalog, catalog.levels.at("frontyard_1"), script.seed);
    runScript(world, script, 40);
    check(world.plants().size() >= 2, "scripted plants must be on the lawn");
    check(world.spawnedZombies() >= 1, "scripted spawns must be honoured");
}

void testSunEconomy(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("frontyard_1"), 2);
    const auto sunBefore = world.sun();
    check(world.plant("sunflower", 0, 0).empty(), "sunflower can be planted");
    check(world.sun() < sunBefore, "planting must spend sun");
    world.advance(40);
    check(!world.suns().empty(), "a sunflower must drop sun within 40 seconds");
    std::size_t collected = 0;
    for (const auto& sun : world.suns()) {
        if (sun.row >= 0) collected += sun.value;
        world.collect(sun.id);
    }
    check(collected > 0, "dropped sun must carry a positive value");
    check(world.sun() > sunBefore - 50, "collected sun must reach the bank");
}

// --------------------------------------------------------- S3.2 pack-driven actions
/// The pack action a plant's slot is wired to. `World::plant` copies the actions in
/// order, so slot i is action i; the test reads the sheet directly instead of trusting
/// the slot copy that the runner is supposed to honour.
const content::Action* packAction(const Catalog& catalog, const std::string& plant, std::size_t index) {
    if (!catalog.rules) return nullptr;
    const auto* type = catalog.rules->findPlant(plant);
    if (type == nullptr || index >= type->actions.size()) return nullptr;
    return &type->actions[index];
}

long long tickOffset(double seconds) { return static_cast<long long>(seconds / World::stepSeconds + 0.5); }

/// A 5x9 lawn with no deck restriction, so a test can plant any plant the pack describes.
LevelDefinition actionLawn(const Catalog& catalog, const std::string& id) {
    LevelDefinition level = synthetic(catalog.levels.at("frontyard_1"), 5, 9, id);
    level.deck.clear();
    return level;
}

void testPackActions(const Catalog& catalog) {
    // ---- sun: production follows the sun action's own cooldown -----------------------
    {
        World world(catalog, actionLawn(catalog, "pack_actions_sun"), 11);
        check(world.plant("sunflower", 0, 0).empty(), "sunflower can be planted");
        const auto plantedAt = static_cast<long long>(world.tick());
        const auto* action = packAction(catalog, "sunflower", 0);
        check(action != nullptr && action->kind == content::ActionKind::sun,
              "sunflower action 0 must be the pack's sun action");
        // The sheet leaves InitialMinCooldownTime out, so the first cycle starts at the low
        // end of CooldownTimeMin/Max (32s). The S2 runner fired on tick 1 instead.
        const double initial = action->initialMin.value_or(action->cooldownMin.value_or(0.0));
        const long long expected = plantedAt + tickOffset(initial);
        long long droppedAt = -1;
        int droppedValue = 0;
        for (int i = 0; i < 60 * 60 && droppedAt < 0; ++i) {
            world.step();
            for (const auto& sun : world.suns()) {
                if (sun.row != 0) continue; // sky sun carries row -1
                droppedAt = static_cast<long long>(world.tick());
                droppedValue = sun.value;
                break;
            }
        }
        check(droppedAt >= 0, "the sunflower's sun action never produced anything");
        check(droppedAt - expected >= -2 && droppedAt - expected <= 2,
              "the first sun must follow the pack's initial cooldown (" + std::to_string(expected) + "), got " +
                  std::to_string(droppedAt));
        check(droppedValue == 25, "the sun value must come from content (sun_value 25), got " +
                                      std::to_string(droppedValue));
    }

    // ---- projectile: repeat interval inside CooldownTimeMin/Max ----------------------
    {
        World world(catalog, actionLawn(catalog, "pack_actions_projectile"), 12);
        check(world.plant("peashooter", 2, 0).empty(), "peashooter can be planted");
        check(world.spawnZombie("basic", 2), "a basic zombie can enter row 2");
        world.zombieById(world.zombies().back().id)->x = 8.6; // far enough never to be eaten
        const auto* action = packAction(catalog, "peashooter", 0);
        check(action != nullptr && action->kind == content::ActionKind::projectile && action->cooldownMin &&
                  action->cooldownMax,
              "peashooter action 0 must carry the pack's cooldown range");
        std::vector<long long> volleys;
        double shotDamage = 0;
        EntityId seen = 0;
        for (int i = 0; i < 60 * 10 && volleys.size() < 3; ++i) {
            world.step();
            for (const auto& shot : world.shots()) {
                if (shot.id <= seen) continue;
                seen = shot.id;
                // The sheet declares the shot twice; one tick is one volley either way.
                if (!volleys.empty() && volleys.back() == static_cast<long long>(world.tick())) continue;
                volleys.push_back(static_cast<long long>(world.tick()));
                shotDamage = shot.damage;
            }
        }
        check(volleys.size() >= 2, "the peashooter must fire at least twice, saw " +
                                       std::to_string(volleys.size()));
        const long long low = tickOffset(action->cooldownMin.value());
        const long long high = tickOffset(action->cooldownMax.value());
        for (std::size_t i = 1; i < volleys.size(); ++i) {
            const long long gap = volleys[i] - volleys[i - 1];
            check(gap >= low && gap <= high, "peashooter volley gap " + std::to_string(gap) + " must sit in [" +
                                                 std::to_string(low) + ", " + std::to_string(high) + "]");
            // The kernel is deterministic, so a range has to resolve to one point: the midpoint.
            check(gap == (low + high) / 2, "peashooter volley gap " + std::to_string(gap) +
                                               " must be the CooldownTimeMin/Max midpoint " +
                                               std::to_string((low + high) / 2));
        }
        // No Damage in the sheet: content damage (30) has to beat the 20 fallback.
        check(shotDamage > 29.9 && shotDamage < 30.1,
              "a pack shot without Damage must use the content damage 30, got " + std::to_string(shotDamage));
    }

    // ---- explode: RectTriggerRange gates the blast and DieAfterExplode clears it -----
    {
        World world(catalog, actionLawn(catalog, "pack_actions_explode"), 13);
        check(world.plant("potatomine", 1, 4).empty(), "potatomine can be planted");
        const auto* action = packAction(catalog, "potatomine", 0);
        check(action != nullptr && action->kind == content::ActionKind::explode && action->triggerRect,
              "potatomine action 0 must carry a RectTriggerRange");
        check(world.spawnZombie("basic", 1), "a basic zombie can enter row 1");
        const auto bait = world.zombies().back().id;
        check(world.spawnZombie("basic", 0), "a basic zombie can enter row 0");
        const auto neighbour = world.zombies().back().id;
        world.zombieById(neighbour)->x = 4.6; // same spot, adjacent row

        // Outside the rect on both sides the mine must stay armed and buried.
        for (const double x : {6.5, 3.4}) {
            world.zombieById(bait)->x = x;
            for (int i = 0; i < 5; ++i) world.step();
            check(world.plantAt(1, 4) != nullptr, "a zombie at x=" + std::to_string(x) +
                                                      " is outside RectTriggerRange and must not set the mine off");
        }
        check(world.zombieById(bait)->alive, "the armed mine must not have hurt anything yet");

        world.zombieById(bait)->x = 4.6; // inside the rect
        world.step();
        check(world.plantAt(1, 4) == nullptr, "a mine without DieAfterExplode and no repeat interval must clear "
                                              "its own cell after detonating");
        check(!world.zombieById(bait)->alive, "a zombie inside RectTriggerRange must be caught by the blast");
        check(world.zombieById(neighbour)->alive,
              "zero SplashDamage must not reach the next row even though the blast is centred between rows");
        check(world.killedZombies() == 1, "only the zombie inside the rect died, saw " +
                                              std::to_string(world.killedZombies()));
    }

    // ---- an unrecognised Type is counted, never thrown ------------------------------
    {
        World world(catalog, actionLawn(catalog, "pack_actions_unknown"), 14);
        check(world.plant("magnifyinggrass", 0, 0).empty(), "magnifyinggrass can be planted");
        const auto* action = packAction(catalog, "magnifyinggrass", 0);
        check(action != nullptr && action->kind == content::ActionKind::unknown,
              "magnifyinggrass action 0 must be the pack's unknown action");
        for (int i = 0; i < 30; ++i) world.step(); // must not throw
        std::size_t reported = 0;
        for (const auto& entry : world.events()) {
            if (entry.value("type", std::string{}) == "action_unknown") ++reported;
        }
        check(reported == 1, "an unknown action must be reported exactly once per slot, saw " +
                                 std::to_string(reported));
    }
}

// ------------------------------------------------------- S3.4a family numbers from the pack
/// Calls one plant family the way the slot executor does, so the family - not `World::tick`
/// - decides whether it acts.
void callFamily(World& world, const std::string& family, EntityId plant) {
    const auto behaviour = Registry::shared().plantBehavior(family);
    check(behaviour != nullptr, "family " + family + " must be registered");
    behaviour(world, plant);
}

/// `RectTriggerRange` in engine units, mirroring registry.cpp (rect is pixels, rect_grid cells).
double windowEdge(const content::Action& action, bool right) {
    if (!action.triggerRect) return right ? 1.0 : -1.0;
    // Art space is 100 px per column (pkg_2073 ArtCenter 99x115/116 over 374 samples), and
    // registry.cpp / action_runner.cpp divide by exactly that. This used to be 60.
    const double scale = action.trigger == "rect_grid" ? 1.0 : 1.0 / 100.0;
    const double x0 = action.triggerRect->x * scale;
    return right ? x0 + action.triggerRect->width * scale : x0;
}

void testFamilyNumbers(const Catalog& catalog) {
    // ---- fume: the pack's Damage (20) beats content's shorthand (40) -----------------
    {
        World world(catalog, actionLawn(catalog, "family_numbers_fume"), 21);
        check(world.plant("fumeshroom", 0, 0).empty(), "fumeshroom can be planted");
        const auto plant = world.plantAt(0, 0)->id;
        check(world.spawnZombie("basic", 0), "a basic zombie can enter row 0");
        const auto target = world.zombies().back().id;
        world.zombieById(target)->x = world.centerOf(0) + 0.4; // inside the fume's reach
        const auto* action = packAction(catalog, "fumeshroom", 0);
        check(action != nullptr && action->kind == content::ActionKind::projectile && action->damage &&
                  *action->damage > 0,
              "fumeshroom's pack action must carry the sheet's Damage");
        const double before = world.zombieById(target)->hp;
        const double low = action->cooldownMin.value_or(0.0);
        const double high = action->cooldownMax.value_or(low);
        const long long expected = tickOffset((low + high) / 2.0);
        long long firedAt = -1;
        for (int i = 0; i < 60 * 10 && firedAt < 0; ++i) {
            callFamily(world, "fume", plant);
            if (world.zombieById(target)->hp < before) firedAt = i;
        }
        check(firedAt >= 0, "the fume family never hurt the zombie standing in front of it");
        const long long drift = firedAt - expected;
        check(drift >= -2 && drift <= 2, "the fume must fire on the CooldownTimeMin/Max midpoint (" +
                                             std::to_string(expected) + "), got " + std::to_string(firedAt));
        const double lost = before - world.zombieById(target)->hp;
        check(std::abs(lost - *action->damage) < 1e-6,
              "one fume blast must deal the pack's Damage (" + std::to_string(*action->damage) +
                  "), not content's 40, got " + std::to_string(lost));
    }

    // ---- spike: one firing lands the pack's Damage, not a per-tick dribble ------------
    {
        World world(catalog, actionLawn(catalog, "family_numbers_spike"), 22);
        check(world.plant("spikeweed", 1, 3).empty(), "spikeweed can be planted");
        const auto plant = world.plantAt(1, 3)->id;
        check(world.spawnZombie("basic", 1), "a basic zombie can enter row 1");
        const auto target = world.zombies().back().id;
        world.zombieById(target)->x = world.centerOf(3);
        const auto* action = packAction(catalog, "spikeweed", 0);
        check(action != nullptr && action->kind == content::ActionKind::special && action->damage &&
                  *action->damage > 0,
              "spikeweed's pack action must carry the sheet's Damage");
        const double before = world.zombieById(target)->hp;
        callFamily(world, "spike", plant); // the `special` slot paces it: one call is one firing
        const double lost = before - world.zombieById(target)->hp;
        check(std::abs(lost - *action->damage) < 1e-6,
              "one spike firing must deal the pack's Damage (" + std::to_string(*action->damage) +
                  "), got " + std::to_string(lost));
    }

    // ---- mine: RectTriggerRange places the arming window, not a bare 1.1 columns ------
    {
        World world(catalog, actionLawn(catalog, "family_numbers_mine"), 23);
        check(world.plant("potatomine", 2, 2).empty(), "potatomine can be planted");
        const auto plant = world.plantAt(2, 2)->id;
        const auto* action = packAction(catalog, "potatomine", 0);
        check(action != nullptr && action->kind == content::ActionKind::explode && action->triggerRect,
              "potatomine's pack action must carry a RectTriggerRange");
        const double x0 = windowEdge(*action, false);
        const double x1 = windowEdge(*action, true);
        check(x0 > -0.55 || x1 < 0.55, "the pack window must differ from the old bare +/-0.55 sweep");
        check(world.spawnZombie("basic", 2), "a basic zombie can enter row 2");
        const auto bait = world.zombies().back().id;
        world.mutablePlants().front().actionTimer = 60.0; // past the content arming delay
        const double centre = world.centerOf(2);

        world.zombieById(bait)->x = centre + x0 - 0.02; // 0.02 columns short on the left
        callFamily(world, "mine", plant);
        check(world.plantAt(2, 2) != nullptr,
              "a zombie 0.02 columns outside RectTriggerRange must not set the mine off");
        check(world.zombieById(bait)->alive, "the unarmed mine must not have hurt anything");

        world.zombieById(bait)->x = centre + x1 - 0.02; // just inside the right edge
        callFamily(world, "mine", plant);
        check(world.plantAt(2, 2) == nullptr, "a zombie inside RectTriggerRange must detonate the mine");
        check(!world.zombieById(bait)->alive, "the blast must catch the zombie that tripped it");
    }

    // ---- chomp: the reach comes from the pack window, in the measured 100 px/column space ----
    // History: the engine used to divide pack pixels by 60, which turned chomper's 100 px window
    // into 1.42 columns. The art space is 100 px per column (pkg_2073 ArtCenter), so the pack
    // value is exactly 1.0 column — the old "1.42 proves the table is wired" check cannot
    // distinguish table from constant any more, so the window is pinned against the table itself.
    {
        World world(catalog, actionLawn(catalog, "family_numbers_chomp"), 24);
        check(world.plant("chomper", 3, 1).empty(), "chomper can be planted");
        const auto plant = world.plantAt(3, 1)->id;
        const auto* action = packAction(catalog, "chomper", 0);
        check(action != nullptr && action->kind == content::ActionKind::projectile && action->triggerRect,
              "chomper's pack action must carry a trigger window");
        check(!(action->damage && *action->damage > 0), "chomper's pack Damage is 0: the swallow is scripted");
        const double reach = windowEdge(*action, true);
        // The right edge of the rect, expressed in the measured 100 px space: x + width, not width.
        const double packed = (action->triggerRect->x + action->triggerRect->width) / 100.0;
        check(std::abs(reach - packed) < 1e-9,
              "the chomp reach must be the rect's right edge in the 100 px space (" +
                  std::to_string(packed) + "), got " + std::to_string(reach));
        check(reach > 0.5, "a chomp window under half a column would be a data bug");
        check(world.spawnZombie("basic", 3), "a basic zombie can enter row 3");
        const auto inside = world.zombies().back().id;
        world.zombieById(inside)->x = world.centerOf(1) + reach - 0.05;
        callFamily(world, "chomp", plant);
        check(!world.zombieById(inside)->alive,
              "a zombie just inside the pack window must be swallowed");

        World outside(catalog, actionLawn(catalog, "family_numbers_chomp"), 25);
        check(outside.plant("chomper", 3, 1).empty(), "chomper can be planted on the control lawn");
        const auto control = outside.plantAt(3, 1)->id;
        check(outside.spawnZombie("basic", 3), "a control zombie can enter row 3");
        const auto far = outside.zombies().back().id;
        // 0.6 columns past the rect edge clears every fallback too (kChompReach = 1.0), so a
        // failure here means the family ignores the window entirely rather than rounding.
        outside.zombieById(far)->x = outside.centerOf(1) + reach + 0.60;
        callFamily(outside, "chomp", control);
        check(outside.zombieById(far)->alive,
              "a zombie outside the pack window must survive a chomp");
    }
}

/// S5.11: the armor sheet, not a flat hp sum, decides what a hit does. Two shapes are pinned
/// here because they are the ones the old `armorHp` pool could not express at all:
///   * an invincible layer that blocks — full damage must leave the zombie alive and untouched;
///   * a layer that holds — the hit must not spill into the layer behind it.
void testArmorLayers(const Catalog& catalog) {
    // ---- invincible blocking layer -----------------------------------------------------
    {
        World world(catalog, actionLawn(catalog, "armor_invincible"), 81);
        check(world.spawnZombie("kongfu_qigong_wave", 2), "kongfu_qigong_wave must spawn from the pack");
        const auto id = world.zombies().front().id;
        const double hpBefore = world.zombies().front().hp;
        const auto layers = world.zombies().front().armorLayers;
        check(layers.size() == 1 && layers.front().invincible() && !layers.front().passDamage(),
              "the nunchaku layer must be invincible and blocking");
        world.damageZombie(id, 100000.0);
        check(world.zombieById(id)->alive,
              "an invincible blocking layer must keep the zombie alive against any single hit");
        check(world.zombieById(id)->hp == hpBefore,
              "a blocked hit must not reach the body: hp " + std::to_string(world.zombieById(id)->hp) +
                  " vs " + std::to_string(hpBefore));
        check(world.zombieById(id)->armorLayers.front().hp == 0.0,
              "an invincible layer must never gain hit points from being hit");
    }
    // ---- a layer that holds does not leak into the next one ----------------------------
    {
        World world(catalog, actionLawn(catalog, "armor_stack"), 82);
        check(world.spawnZombie("kongfu_armor3", 1), "kongfu_armor3 must spawn from the pack");
        const auto id = world.zombies().front().id;
        check(world.zombies().front().armorLayers.size() == 3, "kongfu_armor3 must carry three layers");
        world.damageZombie(id, 100.0);
        const auto& zombie = *world.zombieById(id);
        check(zombie.armorLayers[0].hp == 1550.0,
              "the first cloth must absorb the 100, got " + std::to_string(zombie.armorLayers[0].hp));
        check(zombie.armorLayers[1].hp == 1650.0 && zombie.armorLayers[2].hp == 1650.0,
              "a layer that holds must leave the layers behind it untouched");
        check(zombie.armorHp == 4850.0, "the pool must follow the layers, got " + std::to_string(zombie.armorHp));
    }
}

void testSnapshotContract(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("frontyard_1"), 9);
    world.plant("sunflower", 0, 0);
    const auto snap = world.snapshot();
    check(snap.level == "frontyard_1", "snapshot level id");
    check(snap.rows == 5 && snap.cols == 9, "snapshot geometry");
    check(snap.plants.size() == 1, "snapshot plant count");
    check(snap.hash == world.hash(), "snapshot hash must match the world");
    check(snap.mowers.size() == 5, "one mower per row");
}
} // namespace

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    if (argc < 4) {
        std::cerr << "usage: engine_test <content> <pack> <temp>\n";
        return 2;
    }
    try {
        const fs::path content = argv[1];
        const fs::path pack = argv[2];
        const fs::path temp = argv[3];
        const auto catalog = load(content, pack);
        check(catalog.levels.size() == 1809, "catalog must load 1809 levels");
        check(catalog.rules != nullptr, "rules pack must load for the engine tests");
        testEffectEventsAreEmitted(catalog);
    testRegistryTable();
        testDeterminism(catalog);
        testGeometry(catalog);
        testDirector(catalog);
        testShotsAndEating(catalog);
        testVaultSkipsPlantAndMowerIsNotAPlantKill(catalog);
        testPackOnlyPlant(catalog);
        testSunEconomy(catalog);
        testInputScript(catalog);
        testSnapshotContract(catalog);
        testArmorLayers(catalog);
        testPackActions(catalog);
        testFamilyNumbers(catalog);
        testTwentySixWorlds(catalog, temp);
        std::cout << "engine tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "engine test failed: " << error.what() << '\n';
        return 1;
    }
}
