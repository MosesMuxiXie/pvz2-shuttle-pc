// S5.7: plant food and fusion, driven by the generated tables in native/generated.
//
// The two mechanics could not be more different in shape, and the data says so: plant food is
// a duration per plant plus six plants whose sheet declares an action to play, while fusion is
// 85 explicit pairs. Both are on by default (`WorldOptions`), so the tests have to cover the
// buff, the sheet-declared action, both sides of a pair, and the promise that switching the
// options off leaves the kernel bit-for-bit where it was.
#include "catalog.hpp"
#include "content/model.hpp"
#include "engine/fusion.hpp"
#include "engine/plantfood.hpp"
#include "engine/world.hpp"
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

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

/// A lawn with no deck restriction and a chosen sun balance: the S5 mechanics are about what a
/// plant does after it exists, so the deck/sun gate must not decide the test.
LevelDefinition lawn(const Catalog& catalog, const std::string& id, int sun) {
    LevelDefinition level = catalog.levels.at("frontyard_1");
    level.id = id;
    level.rows = 5;
    level.cols = 9;
    level.sun = sun;
    level.deck.clear();
    return level;
}

struct Volley {
    std::uint64_t tick = 0;
    double damage = 0;
    int foodTicks = 0;
    std::string projectile;
};

/// Step the world and record every shot as it appears, together with the shooter's plant-food
/// state at the moment it fired. Shot ids only ever grow, so `lastId` catches a volley even
/// when another shot was reaped in the same tick.
void pump(World& world, int steps, EntityId& lastId, std::vector<Volley>& out) {
    for (int i = 0; i < steps; ++i) {
        world.step();
        for (const auto& shot : world.shots()) {
            if (shot.id <= lastId) continue;
            lastId = shot.id;
            Volley volley;
            volley.tick = world.tick();
            volley.damage = shot.damage;
            volley.projectile = shot.projectileType;
            if (const auto* plant = world.plantById(shot.owner)) volley.foodTicks = plant->plantFoodTicks;
            out.push_back(volley);
        }
    }
}

/// One entry per tick. A plant may declare the same projectile twice in the sheet (peashooter
/// does), so two shots land on one tick; cadence is a property of the tick, not of the shot.
std::vector<Volley> perTick(const std::vector<Volley>& shots) {
    std::vector<Volley> out;
    for (const auto& shot : shots) {
        if (!out.empty() && out.back().tick == shot.tick) continue;
        out.push_back(shot);
    }
    return out;
}

/// Feeding a plant without a sheet action is the duration-only buff: damage and cadence both
/// improve for `durationSeconds` (peashooter: 2s from the sheet) and then go back.
void testPlantFoodFallback(const Catalog& catalog) {
    World world(catalog, lawn(catalog, "s5_plantfood_buff", 500), 11);
    check(world.plant("peashooter", 0, 0).empty(), "peashooter must be plantable on the test lawn");
    const EntityId plantId = world.plantAt(0, 0)->id;
    check(world.spawnZombie("basic", 0), "the buff test needs a target in the peashooter's row");
    // A cadence measurement needs a target that outlives the measurement: 640 ticks of volleys
    // would kill any normal zombie and the plant would then hold fire, which reads as a cadence
    // change. Only the plant is under test here.
    for (auto& zombie : world.mutableZombies()) {
        zombie.hp = 100000.0;
        zombie.maxHp = 100000.0;
    }

    EntityId lastId = 0;
    std::vector<Volley> raw;
    // 340 ticks lands one tick before the plant's fifth volley (the sheet's midpoint cadence is
    // 85), so the 2s window can cover several of them: duration is in seconds, not in shots.
    pump(world, 340, lastId, raw);
    const std::vector<Volley> volleys = perTick(raw);
    check(volleys.size() >= 3, "an unfed peashooter must fire steadily, saw " + std::to_string(volleys.size()));
    for (const auto& volley : volleys) {
        check(std::abs(volley.damage - 30.0) < 1e-9,
              "unfed peashooter damage must be content's 30, got " + std::to_string(volley.damage));
        check(volley.foodTicks == 0, "no plant-food window may be active before a feed");
    }
    for (std::size_t i = 1; i < volleys.size(); ++i) {
        const auto gap = static_cast<long long>(volleys[i].tick - volleys[i - 1].tick);
        check(gap == 85, "unfed peashooter cadence must be the CooldownTimeMin/Max midpoint (85), got " +
                             std::to_string(gap));
    }

    const std::int64_t sunBefore = world.sun();
    check(world.feed(plantId), "feeding a live plant must succeed");
    check(world.sun() == sunBefore, "plant food costs no sun");
    const auto states = world.plantFoodStates();
    check(states.size() == 1 && states.front().plant == plantId && !states.front().usesActionSlot,
          "peashooter has no plantfood action, so the state must report the buff-only shape");
    check(states.front().remainingTicks == 120, "peashooter's sheet duration is 2s == 120 ticks, got " +
                                                    std::to_string(states.front().remainingTicks));

    const auto before = raw.size();
    pump(world, 300, lastId, raw);
    const std::vector<Volley> after =
        perTick(std::vector<Volley>(raw.begin() + static_cast<std::ptrdiff_t>(before), raw.end()));
    std::vector<std::uint64_t> fedTicks;
    bool sawRestoredDamage = false;
    for (const auto& volley : after) {
        if (volley.foodTicks > 0) {
            fedTicks.push_back(volley.tick);
            check(std::abs(volley.damage - 60.0) < 1e-9,
                  "a fed peashooter hits for +100% (60), got " + std::to_string(volley.damage));
        } else if (std::abs(volley.damage - 30.0) < 1e-9) {
            sawRestoredDamage = true;
        }
    }
    check(fedTicks.size() >= 3, "a 120-tick window over an 85/2 cadence must cover at least three volleys, saw " +
                                    std::to_string(fedTicks.size()));
    for (std::size_t i = 1; i < fedTicks.size(); ++i) {
        const auto gap = static_cast<long long>(fedTicks[i] - fedTicks[i - 1]);
        check(gap == 42, "a fed peashooter cycles at +100% speed (85/2 == 42), got " + std::to_string(gap));
    }
    check(sawRestoredDamage, "the buff must expire: a volley after the window has to hit for 30 again");
    bool sawRestoredCadence = false;
    for (std::size_t i = 1; i < after.size(); ++i) {
        if (after[i].foodTicks == 0 && after[i - 1].foodTicks == 0 &&
            after[i].tick - after[i - 1].tick == 85) {
            sawRestoredCadence = true;
        }
    }
    check(sawRestoredCadence, "after the window the cadence must go back to 85 ticks");
    check(world.plantFoodStates().empty(), "an expired feed must leave no state behind");
}

/// Six plants declare a real `plantfood` action. Feeding one plays that action, which is the
/// original behaviour and the reason the table carries `effects` at all.
void testPlantFoodActionSlot(const Catalog& catalog) {
    const PlantFoodTable& table = PlantFoodTable::shared();
    check(table.actionSlotRows() >= 6, "the shipped table must keep the six plantfood actions, saw " +
                                           std::to_string(table.actionSlotRows()));
    const PlantFoodRow* row = table.find("sungun");
    check(row != nullptr && row->hasActionSlot(), "sungun must carry a plantfood action in the sheet");
    const PlantFoodEffect* effect = row->projectileEffect();
    check(effect != nullptr, "sungun's plantfood action must name a projectile");

    World world(catalog, lawn(catalog, "s5_plantfood_action", 600), 12);
    check(world.canFeed("sungun"), "sungun has a table row, so canFeed must be true");
    check(!world.canFeed("no_such_plant"), "an unknown type cannot be fed");
    check(world.plant("sungun", 0, 0).empty(), "sungun is pack-only and must still be plantable");
    const EntityId plantId = world.plantAt(0, 0)->id;
    bool hasSlot = false;
    for (const auto& slot : world.plantAt(0, 0)->slots) {
        if (slot.kind == "plantfood") hasSlot = true;
    }
    check(hasSlot, "sungun's pack action list must produce a plantfood slot");

    EntityId lastId = 0;
    std::vector<Volley> volleys;
    // Let the plant's ordinary cycle run first, so anything recorded after the feed is the
    // feed's own projectile rather than the slot it already had.
    pump(world, 5, lastId, volleys);
    volleys.clear();
    check(world.feed(plantId), "feeding sungun must succeed");
    const auto states = world.plantFoodStates();
    check(states.size() == 1 && states.front().usesActionSlot,
          "sungun's state must report that the feed plays an action");

    volleys.clear();
    pump(world, 10, lastId, volleys);
    bool played = false;
    for (const auto& volley : volleys) {
        if (volley.projectile == effect->projectile) played = true;
    }
    check(played, "feeding sungun must spawn the sheet's plantfood projectile (" + effect->projectile +
                      "), saw none");
}

/// A real pair from the 85: peashooter + iceburg -> fused_snowpea. Both plants must disappear,
/// the result must stand on the first plant's cell, and the count must move.
void testFusionPairApplies(const Catalog& catalog) {
    const FusionTable& table = FusionTable::shared();
    check(table.size() == 85, "the shipped fusion table has 85 pairs, got " + std::to_string(table.size()));
    const FusionRecipe* recipe = table.find("peashooter", "iceburg");
    check(recipe != nullptr, "peashooter + iceburg must be one of the sheet's pairs");
    check(recipe->result == "fused_snowpea", "that pair's result must be fused_snowpea, got " + recipe->result);
    check(table.find("iceburg", "peashooter") == recipe, "the pair must match in either order");

    World world(catalog, lawn(catalog, "s5_fusion_pair", 600), 13);
    check(world.plant("peashooter", 1, 1).empty(), "peashooter must be plantable");
    const EntityId a = world.plantAt(1, 1)->id;
    check(world.plant("iceburg", 1, 2).empty(), "iceburg must be plantable next door");
    const EntityId b = world.plantAt(1, 2)->id;

    const std::int64_t sunBefore = world.sun();
    check(world.tryFuse(a, b), "an adjacent pair from the sheet must fuse");
    check(world.plantAt(1, 1) != nullptr && world.plantAt(1, 1)->type == recipe->result,
          "the result must be built on the first plant's cell");
    check(world.plantAt(1, 2) == nullptr, "the second plant must be consumed");
    check(world.fusions() == 1, "the fusion counter must move once");
    check(world.sun() < sunBefore, "a fused plant still costs its sheet sun, got " +
                                       std::to_string(world.sun() - sunBefore));

    bool sawEvent = false;
    for (const auto& entry : world.events()) {
        if (entry.value("type", std::string{}) != "fusion") continue;
        sawEvent = true;
        const auto& details = entry.at("details");
        check(details.value("result", std::string{}) == recipe->result, "the fusion event must name the result");
        check(details.value("a", 0ULL) == a && details.value("b", 0ULL) == b, "the fusion event must name both plants");
    }
    check(sawEvent, "a fusion must be visible in the event log");
    check(!world.tryFuse(a, b), "a consumed pair cannot fuse again");
}

/// Three ways a pair must be refused: wrong plants, non-adjacent cells, and the option off.
void testFusionRejectsNonPair(const Catalog& catalog) {
    World world(catalog, lawn(catalog, "s5_fusion_refuse", 600), 14);
    check(world.plant("peashooter", 3, 1).empty(), "first peashooter");
    const EntityId a = world.plantAt(3, 1)->id;
    // A different plant, not a second peashooter: one type cannot be planted twice in a row
    // (the sheet recharge is 5s), and the point is "not a pair", not "rejected by the gate".
    check(world.plant("sunflower", 3, 2).empty(), "sunflower next to the peashooter");
    const EntityId b = world.plantAt(3, 2)->id;
    check(!world.tryFuse(a, b), "peashooter + sunflower is not a pair");
    check(world.plantAt(3, 1) != nullptr && world.plantAt(3, 2) != nullptr, "a refused fusion must not eat plants");
    check(world.fusions() == 0, "a refused fusion must not count");

    check(world.plant("iceburg", 4, 6).empty(), "iceburg far away");
    const EntityId far = world.plantAt(4, 6)->id;
    check(!world.tryFuse(a, far), "a pair must stand on the same or adjacent cells");
    check(!world.tryFuse(a, a), "a plant cannot fuse with itself");
    check(!world.tryFuse(a, 9999), "an unknown entity cannot fuse");

    WorldOptions off;
    off.plantfood = false;
    off.fusion = false;
    World disabled(catalog, lawn(catalog, "s5_fusion_off", 600), 14, off);
    check(disabled.plant("peashooter", 0, 0).empty(), "peashooter under options off");
    const EntityId da = disabled.plantAt(0, 0)->id;
    check(disabled.plant("iceburg", 0, 1).empty(), "iceburg under options off");
    const EntityId db = disabled.plantAt(0, 1)->id;
    check(!disabled.tryFuse(da, db), "fusion must be inert while the option is off");
    check(!disabled.feed(da), "plant food must be inert while the option is off");
    check(!disabled.canFeed("peashooter"), "canFeed must report the switch, not the table");
}

/// Switching both mechanics off has to leave the kernel exactly where it was, otherwise every
/// recorded baseline (engine_smoke, snapshots) moves for a feature that is not in play.
void testOptionsOffKeepsHash(const Catalog& catalog) {
    std::vector<std::string> ids;
    for (const auto& entry : catalog.levels) {
        ids.push_back(entry.first);
        if (ids.size() == 3) break;
    }
    check(ids.size() == 3, "the catalog must offer at least three levels to sample");

    WorldOptions off;
    off.plantfood = false;
    off.fusion = false;
    for (const auto& id : ids) {
        const auto& level = catalog.levels.at(id);
        World disabled(catalog, level, 21, off);
        World defaults(catalog, level, 21);
        for (int i = 0; i < 240; ++i) {
            disabled.step();
            defaults.step();
        }
        check(disabled.hash() == defaults.hash(),
              "options off must not change the hash on " + id + ": " + std::to_string(disabled.hash()) + " vs " +
                  std::to_string(defaults.hash()));
    }

    // ... while actually using a mechanic must change it, or the state is not really hashed.
    World world(catalog, lawn(catalog, "s5_hash_food", 500), 22);
    check(world.plant("sunflower", 0, 0).empty(), "sunflower must be plantable");
    const EntityId plantId = world.plantAt(0, 0)->id;
    const std::uint64_t quiet = world.hash();
    check(world.feed(plantId), "feeding must work with the option on");
    check(world.hash() != quiet, "a live plant-food window must be part of the hash");

    World fused(catalog, lawn(catalog, "s5_hash_fusion", 600), 23);
    check(fused.plant("peashooter", 2, 2).empty(), "peashooter for the fusion hash");
    const EntityId fa = fused.plantAt(2, 2)->id;
    check(fused.plant("iceburg", 2, 3).empty(), "iceburg for the fusion hash");
    const EntityId fb = fused.plantAt(2, 3)->id;
    const std::uint64_t beforeFusion = fused.hash();
    check(fused.tryFuse(fa, fb), "the pair must fuse");
    check(fused.hash() != beforeFusion, "a fusion must be part of the hash");
}

} // namespace

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    if (argc < 4) {
        std::cerr << "usage: s5_runtime_test <content> <pack> <temp>\n";
        return 2;
    }
    try {
        const fs::path content = argv[1];
        const fs::path pack = argv[2];
        const auto catalog = load(content, pack);
        check(catalog.levels.size() == 1809, "catalog must load 1809 levels");
        check(catalog.rules != nullptr, "the rules pack is required: both tables key off pack ids");
        testPlantFoodFallback(catalog);
        testPlantFoodActionSlot(catalog);
        testFusionPairApplies(catalog);
        testFusionRejectsNonPair(catalog);
        testOptionsOffKeepsHash(catalog);
        std::cout << "s5 runtime tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "s5 runtime test failed: " << error.what() << '\n';
        return 1;
    }
}
