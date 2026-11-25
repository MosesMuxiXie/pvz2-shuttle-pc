// S5.13 level mechanics: what a level says about itself beyond its wave list.
//
// The sheet (`native/generated/level_mechanics.json`) describes 1809 client levels. Four of its
// mechanisms are wired into the kernel this round and the rest are counted as unwired, so this
// file checks three different promises:
//   1. the sheet is parsed the way the pack means it      (testTableShape)
//   2. the wired mechanisms actually run                  (conveyor / initial field / gravestones /
//                                                          protect mission)
//   3. the unwired ones are visible, not silent           (testUnknownMechanicsAreCounted)
//
// The counting case is the one that keeps the project honest: a level whose tide never runs looks
// exactly like a level that never had a tide, unless the kernel says so out loud.
#include "catalog.hpp"
#include "engine/world.hpp"

#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

namespace fs = std::filesystem;
using pvz::Catalog;
using pvz::engine::GridItemEntity;
using pvz::engine::LevelMechanicsTable;
using pvz::engine::MechanicTier;
using pvz::engine::World;

[[noreturn]] void fail(const std::string& message) { throw std::runtime_error(message); }
void check(bool condition, const std::string& message) {
    if (!condition) fail(message);
}

std::size_t countEvents(const World& world, const std::string& type) {
    std::size_t total = 0;
    for (const auto& entry : world.events())
        if (entry.value("type", std::string{}) == type) ++total;
    return total;
}

/// The fields of the first event of `type`. An event carries `tick` and `type` at the top level and
/// everything else under `details`, so this returns the details rather than the record.
pvz::Json firstEvent(const World& world, const std::string& type) {
    for (const auto& entry : world.events()) {
        if (entry.value("type", std::string{}) == type) return entry.value("details", pvz::Json::object());
    }
    fail("no " + type + " event was logged");
}

/// How many spawns arrived carrying a flag marker. `wave_spawn` keeps the marker under `details`,
/// so this can tell a suppressed flag wave from an ordinary one without looking at the zombies.
std::size_t flagSpawns(const World& world) {
    std::size_t total = 0;
    for (const auto& entry : world.events()) {
        if (entry.value("type", std::string{}) != "wave_spawn") continue;
        if (entry.value("details", pvz::Json::object()).value("flag", false)) ++total;
    }
    return total;
}

/// Run until the director has handed over every wave, or the run ends first. The marker lives on the
/// spawn, not on a tick, so a test only needs the waves to arrive.
void runUntilWavesSpawned(World& world) {
    const std::uint64_t cap = world.tick() + 14400; // 240 s of ticks: far past any first flag wave
    while (world.wave() < world.waves() && world.status() == "playing" && world.tick() < cap) world.step();
}

/// A copy of a level with its waves removed: the director is exhausted at tick 0, so the lawn itself
/// is the only thing that can still end the run. Used to separate "the mission is unwinnable" from
/// "a zombie ate the objective".
pvz::LevelDefinition clearedWaves(const Catalog& catalog, const std::string& id) {
    const auto it = catalog.levels.find(id);
    if (it == catalog.levels.end()) fail("missing level: " + id);
    pvz::LevelDefinition level = it->second;
    level.waves.clear();
    return level;
}

/// A cell with neither a plant nor a grid item on it, searched from the left of the top row so the
/// answer is stable for a given level.
std::pair<int, int> freeCell(World& world) {
    for (int row = 0; row < world.rows(); ++row) {
        for (int col = 0; col < world.cols(); ++col) {
            if (world.plantAt(row, col) == nullptr && world.gridItemAt(row, col) == nullptr) return {row, col};
        }
    }
    fail("the level has no free cell to plant on");
}

// 1. The sheet, read the way the pack means it.
//
// The counts here are *not* the `counts` block of the JSON: that block counts levels that declare
// a module, while these count the levels whose module the kernel can act on. 690 levels declare
// `initialGridItems`, of which 466 name their items in `placements[]` and 117 more only in
// `gravestones`; the remaining 67 name the module but not what stands in it, and those are counted
// under `initialGridItems.unresolved` instead of vanishing. 350 levels declare a conveyor but only
// 348 can deal a hand - `dark_33` and `frontyard_173` provide neither `slots` nor `changes`.
void testTableShape() {
    const LevelMechanicsTable& table = LevelMechanicsTable::shared();
    check(table.size() == 1809, "the sheet must carry every client level, got " + std::to_string(table.size()));
    check(table.withConveyor() == 348, "levels with cards, got " + std::to_string(table.withConveyor()));
    check(table.withInitialPlants() == 249,
          "levels that open with plants, got " + std::to_string(table.withInitialPlants()));
    check(table.withInitialGridItems() == 583,
          "levels that open with named grid items, got " + std::to_string(table.withInitialGridItems()));
    check(table.withProtect() == 286, "protect missions, got " + std::to_string(table.withProtect()));
    check(table.withGravestones() == 353, "levels with gravestone drops, got " + std::to_string(table.withGravestones()));
    // T66 wired the eight `spawners.*` generators into the kernel, so the level counts that used
    // to include them are now the ones that actually deal arrivals: a row with no `wave` (grid 21,
    // portal 17, storm 1, ground 22, dino 64) is still counted as unwired rather than guessed, and
    // a row whose RTID names no zombie type keeps its own `nonzombie`/`creatures` entry.
    check(table.withSpawners(pvz::engine::SpawnerKind::grid) == 217,
          "levels whose grid rows name a zombie type, got " + std::to_string(table.withSpawners(pvz::engine::SpawnerKind::grid)));
    check(table.withSpawners(pvz::engine::SpawnerKind::portal) == 125,
          "levels with a portal, got " + std::to_string(table.withSpawners(pvz::engine::SpawnerKind::portal)));
    check(table.withSpawners(pvz::engine::SpawnerKind::storm) == 117,
          "levels with a storm, got " + std::to_string(table.withSpawners(pvz::engine::SpawnerKind::storm)));
    check(table.withSpawners(pvz::engine::SpawnerKind::ground) == 73,
          "levels whose ground rows name a zombie type, got " + std::to_string(table.withSpawners(pvz::engine::SpawnerKind::ground)));
    check(table.withSpawners(pvz::engine::SpawnerKind::dino) == 89,
          "levels with a dinosaur sweep, got " + std::to_string(table.withSpawners(pvz::engine::SpawnerKind::dino)));
    check(table.withSpawners(pvz::engine::SpawnerKind::beach) == 82,
          "levels with a beach tide, got " + std::to_string(table.withSpawners(pvz::engine::SpawnerKind::beach)));
    check(table.withSpawners(pvz::engine::SpawnerKind::fish) == 26,
          "levels with fish, got " + std::to_string(table.withSpawners(pvz::engine::SpawnerKind::fish)));
    // 446 levels still carry something the kernel cannot honour: the modules it never modelled
    // (tide strength, mutators, board grids) plus the spawner rows whose wave or zombie type the
    // sheet does not name. Wiring the generators took this from 868 to 446 instead of hiding them.
    check(table.withUnknown() == 446, "levels with an unwired mechanic, got " + std::to_string(table.withUnknown()));
    // `slots` and `changes[].add` are both card sources: lostcity_67 only has the latter, so a
    // reader that stops at `slots` silently loses every card in that level.
    const auto* belt = table.find("beach_12");
    check(belt != nullptr, "beach_12 must be in the sheet");
    check(belt->conveyor.slots.size() == 5, "beach_12 carries five cards, got " + std::to_string(belt->conveyor.slots.size()));
    check(belt->conveyor.alias == "ConveyorBelt", "beach_12's belt alias, got " + belt->conveyor.alias);
    const auto* late = table.find("lostcity_67");
    check(late != nullptr && !late->conveyor.slots.empty(),
          "a level that adds its cards through changes[] must still yield cards");
    check(table.find("no_such_level") == nullptr, "an unknown level must not resolve");

    // Gravestones arrive in waves, so the reader has to zip the pool counts against the positions
    // instead of flattening both.
    const auto* graves = table.find("beach_72");
    check(graves != nullptr && !graves->gravestones.empty(), "beach_72 must carry gravestone waves");
    check(graves->gravestones.front().positions.size() == 5,
          "one pool of five gravestones must land on five cells, got " +
              std::to_string(graves->gravestones.front().positions.size()));
}

// 2a. A conveyor level has no seed bank: the cards come off the belt, cost nothing, and the deck
// list is not the authority - the hand is.
void testConveyorNeedsNoSun(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("beach_12"), 71);
    check(world.conveyorLevel(), "beach_12 is a conveyor level");
    check(world.conveyorCards().size() == 6,
          "the belt deals six cards, got " + std::to_string(world.conveyorCards().size()));
    const std::int64_t sunBefore = world.sun();
    const std::int64_t spentBefore = world.sunSpent();
    const auto cell = freeCell(world);
    const std::string card = world.conveyorCards().front();
    const std::string refusal = world.plant(card, cell.first, cell.second);
    check(refusal.empty(), "a card from the belt must plant, refused with: " + refusal);
    check(world.plantAt(cell.first, cell.second) != nullptr, "the card must actually be on the lawn");
    check(world.sun() == sunBefore, "a belt card must not cost sun, sun=" + std::to_string(world.sun()));
    check(world.sunSpent() == spentBefore, "a belt card must not reach sunSpent");
    check(world.conveyorCards().size() == 6,
          "the belt must refill to a full hand, got " + std::to_string(world.conveyorCards().size()));
    check(countEvents(world, "conveyor_dealt") >= 2, "the deal must be visible in the event log");

    // Planting something the belt never dealt is refused rather than being silently free: the
    // deck list is not what authorises a plant here, the hand is.
    const auto other = freeCell(world);
    const std::string refused = world.plant("sunflower", other.first, other.second);
    check(refused == "not on the conveyor", "a plant that is not in hand must be refused, got: " + refused);
    check(world.sun() == sunBefore && world.sunSpent() == spentBefore, "a refused belt plant must cost nothing");
}

// 2b. The opening field is laid before the first tick, costs nothing, and is an ordinary plant
// afterwards - it can be eaten like any other.
void testInitialPlantsAreLaid(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("beach_1"), 72);
    check(world.initialPlantsLaid() == 3,
          "beach_1 opens with three lilypads, got " + std::to_string(world.initialPlantsLaid()));
    check(world.sun() == 150, "the opening field is free, sun=" + std::to_string(world.sun()));
    check(world.sunSpent() == 0, "the opening field must not reach sunSpent");
    // sheet coordinates: gridX is the column, gridY the row.
    const auto* pad = world.plantAt(0, 5);
    check(pad != nullptr && pad->type == "lilypad", "the lilypad at column 5 row 0 must be there");
    check(world.plantAt(3, 5) != nullptr && world.plantAt(4, 5) != nullptr, "the other two pads must be there");

    // It is a plant, not scenery: a zombie eats it.
    world.spawnZombie("basic", 0);
    check(!world.zombies().empty(), "the zombie must spawn for the eating case");
    auto& zombie = world.mutableZombies().back();
    zombie.x = 5.55; // in reach of the pad's column
    const double hpBefore = world.plantAt(0, 5)->hp;
    for (int step = 0; step < 90; ++step) world.step();
    const auto* eaten = world.plantAt(0, 5);
    check(eaten == nullptr || eaten->hp < hpBefore, "an opening plant must be edible like any other");
}

// 2c. Grid items occupy a cell: nothing may be planted on them until they are gone, and both the
// shovel and an explosion know how to remove them.
void testGridItemsBlockAndBreak(const Catalog& catalog) {
    {
        World world(catalog, catalog.levels.at("beach_20"), 73);
        check(world.gridItemsSpawned() == 5,
              "beach_20 opens with five puddles, got " + std::to_string(world.gridItemsSpawned()));
        check(world.plantAt(0, 5) == nullptr, "the puddle is not a plant");
        check(world.gridItemAt(0, 5) != nullptr, "the puddle at column 5 row 0 must be there");
        const std::string refusal = world.plant("sunflower", 0, 5);
        check(refusal == "cell occupied", "a grid item must block planting, got: " + refusal);
        check(world.shovel(0, 5), "the shovel must clear a grid item");
        check(world.gridItemAt(0, 5) == nullptr, "the cleared cell must be empty");
        check(countEvents(world, "grid_item_removed") == 1, "clearing a grid item must be logged");
        const std::string ok = world.plant("sunflower", 0, 5);
        check(ok.empty(), "the cleared cell must accept a plant, refused with: " + ok);
    }
    {
        // The explosion path uses the same rule, so a Cherry Bomb clears a blocked cell too.
        World world(catalog, catalog.levels.at("beach_20"), 74);
        world.explode(0, 5.5, 0.6, 1800.0, 0.0);
        check(world.gridItemAt(0, 5) == nullptr, "an explosion must destroy a grid item");
        check(countEvents(world, "grid_item_destroyed") == 1, "destroying a grid item must be logged");
        check(world.plant("sunflower", 0, 5).empty(), "the cleared cell must accept a plant");
    }
}

// Living protected plants, left to right, top to bottom - the order the sheet lists them in.
std::vector<pvz::engine::EntityId> protectedIds(const World& world) {
    std::vector<pvz::engine::EntityId> ids;
    for (const auto& plant : world.plants())
        if (plant.alive && plant.protectedPlant) ids.push_back(plant.id);
    return ids;
}

// 2d. The protect mission: the sheet's plants are the objective, and losing one loses the level
// immediately instead of waiting for the lawn to empty.
void testProtectMission(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("beach_14"), 75);
    check(world.protectedPlantCount() == 5,
          "beach_14 protects five plants, got " + std::to_string(world.protectedPlantCount()));
    check(world.requiredProtectedPlants() == 5,
          "beach_14 requires all five, got " + std::to_string(world.requiredProtectedPlants()));
    check(world.aliveProtectedPlants() == 5, "all five must be standing at the start");
    check(world.status() == "playing", "the level starts playing");
    const auto* target = world.plantAt(0, 0);
    check(target != nullptr && target->protectedPlant, "the bowling bulb at column 0 row 0 is protected");
    check(world.shovel(0, 0) == false, "the objective cannot be shoveled away");
    check(world.plantAt(0, 0) != nullptr, "the shovel must leave the objective in place");
    check(countEvents(world, "shovel_blocked") == 1, "a refused shovel must be logged");

    world.damagePlant(target->id, 1.0e6);
    check(world.protectFailures() == 1, "losing the objective must be counted");
    check(countEvents(world, "protect_failed") == 1, "losing the objective must be logged");
    check(world.status() == "lost", "losing the objective must lose the level, got: " + world.status());
    check(world.tick() == 0, "the loss must be immediate, not on the next tick, tick=" + std::to_string(world.tick()));
}

// 2e. `mustProtectCount` is the threshold, not the plant list: eighteen missions require fewer
// plants than they list, and one (`egypt_56`) requires none at all. Treating the list length as
// the threshold made every one of them stricter than the pack says.
void testProtectThresholds(const Catalog& catalog) {
    {
        // 4 of 5: the first death is survivable, the second is not.
        World world(catalog, catalog.levels.at("beach_88"), 80);
        check(world.protectedPlantCount() == 5, "beach_88 lists five protected plants");
        check(world.requiredProtectedPlants() == 4,
              "beach_88 requires four of the five, got " + std::to_string(world.requiredProtectedPlants()));
        auto ids = protectedIds(world);
        check(ids.size() == 5, "five protected plants must be standing");
        world.damagePlant(ids[0], 1.0e6);
        check(world.status() == "playing",
              "losing one of five must not lose a mission that requires four, got: " + world.status());
        check(world.protectFailures() == 0, "a survivable death must not be counted as a protect failure");
        check(world.aliveProtectedPlants() == 4, "four must be left");
        ids = protectedIds(world);
        world.damagePlant(ids[0], 1.0e6);
        check(world.aliveProtectedPlants() == 3, "three must be left");
        check(world.status() == "lost",
              "dropping below four must lose the mission, got: " + world.status());
        check(world.protectFailures() == 1, "the failure must be counted once");
    }
    {
        // 4 of 5 on paper, but `egypt_74` lists five targets on three cells ((3,2) three times),
        // so only three can stand. The sheet still asks for four: the mission is unwinnable by
        // data, which is reported (`protect_plant_unplaced`) instead of being quietly relaxed.
        World world(catalog, catalog.levels.at("egypt_74"), 81);
        check(world.protectedPlantCount() == 3,
              "egypt_74 stacks three targets on one cell, so three stand, got " +
                  std::to_string(world.protectedPlantCount()));
        check(world.unplacedProtectedPlants() == 2,
              "two of the five targets have no cell, got " + std::to_string(world.unplacedProtectedPlants()));
        check(countEvents(world, "protect_plant_unplaced") == 2, "each dropped target must be reported");
        check(world.requiredProtectedPlants() == 4,
              "egypt_74 requires four, got " + std::to_string(world.requiredProtectedPlants()));
        auto ids = protectedIds(world);
        world.damagePlant(ids[0], 1.0e6);
        check(world.status() == "lost",
              "three targets cannot satisfy a four-of-five mission, got: " + world.status());
    }
    {
        // 0 of 15: the plants are the level's scenery. Killing all of them must change nothing,
        // because inventing a stricter rule here would be exactly the bug this case guards.
        World world(catalog, catalog.levels.at("egypt_56"), 82);
        check(world.protectedPlantCount() == 15,
              "egypt_56 lists fifteen protected plants, got " + std::to_string(world.protectedPlantCount()));
        check(world.requiredProtectedPlants() == 0,
              "egypt_56 requires none of them, got " + std::to_string(world.requiredProtectedPlants()));
        for (const auto id : protectedIds(world)) world.damagePlant(id, 1.0e6);
        check(world.aliveProtectedPlants() == 0, "all fifteen must be gone");
        check(world.status() == "playing",
              "a mission that requires none cannot be lost this way, got: " + world.status());
        check(world.protectFailures() == 0, "no protect failure may be counted");
        check(countEvents(world, "protect_failed") == 0, "no protect failure may be logged");
    }
}

// 2f. T59: a mission may ask for more targets than its own board can hold. That is not a rule
// change - `egypt_74` stays winnable while all three of its targets stand - it is a capacity
// report. The six missions that place no target at all need it most: with nothing on the lawn the
// death path in `damagePlant` can never fire, so without this event the mission would pass no
// matter what the player did, and nothing in the output would say so.
void testProtectCapacityShortfall(const Catalog& catalog) {
    {
        World world(catalog, catalog.levels.at("egypt_74"), 90);
        check(countEvents(world, "protect_capacity_shortfall") == 1,
              "egypt_74 must report that its board cannot hold every target");
        check(world.protectCapacityShortfall() == 1,
              "egypt_74 is one target short, got " + std::to_string(world.protectCapacityShortfall()));
        const auto& payload = firstEvent(world, "protect_capacity_shortfall");
        check(payload.value("placed", -1) == 3,
              "three targets must stand, got " + std::to_string(payload.value("placed", -1)));
        check(payload.value("must", -1) == 4, "the mission must ask for four, got " +
                                                  std::to_string(payload.value("must", -1)));
        check(payload.value("delta", -1) == 1, "the gap must be one, got " +
                                                   std::to_string(payload.value("delta", -1)));
        check(world.status() == "playing", "a short mission must still start playing");

        // The report must not become a loss: with the waves gone, three standing targets win.
        World survivor(catalog, clearedWaves(catalog, "egypt_74"), 90);
        for (int i = 0; i < 30; ++i) survivor.step();
        check(survivor.status() == "won",
              "egypt_74 must stay winnable while its three targets stand, got: " + survivor.status());
    }
    {
        // carnival_79 lists protect targets that land on no cell at all: the mission protects
        // nothing, and before T59 that fact appeared nowhere.
        World world(catalog, catalog.levels.at("carnival_79"), 91);
        check(world.protectedPlantCount() == 0,
              "carnival_79 places no protect target, got " + std::to_string(world.protectedPlantCount()));
        check(world.requiredProtectedPlants() > 0,
              "carnival_79 still asks for survivors, got " + std::to_string(world.requiredProtectedPlants()));
        check(countEvents(world, "protect_capacity_shortfall") == 1,
              "carnival_79 must report that it can protect nothing");
        check(world.protectCapacityShortfall() == world.requiredProtectedPlants(),
              "with nothing placed the gap must be the whole mission, got " +
                  std::to_string(world.protectCapacityShortfall()));
        check(world.status() == "playing", "an empty protect mission must not fail the level by itself");
    }
    {
        // beach_88 lists five and needs four: enough cells, so no report.
        World world(catalog, catalog.levels.at("beach_88"), 92);
        check(countEvents(world, "protect_capacity_shortfall") == 0,
              "beach_88 has enough cells and must not report a shortfall");
        check(world.protectCapacityShortfall() == 0,
              "beach_88 must report no gap, got " + std::to_string(world.protectCapacityShortfall()));
    }
    {
        // beach_14 lists exactly as many targets as it requires (five of five). The board fits them
        // all, so the gap is zero - and a gap of zero must not be reported as a shortfall either,
        // which is what keeps `<` from drifting into `<=` unnoticed.
        World world(catalog, catalog.levels.at("beach_14"), 93);
        check(world.protectedPlantCount() == world.requiredProtectedPlants(),
              "beach_14 places exactly as many targets as it requires");
        check(countEvents(world, "protect_capacity_shortfall") == 0,
              "an exact fit is not a shortfall");
        check(world.protectCapacityShortfall() == 0,
              "an exact fit must report a zero gap, got " + std::to_string(world.protectCapacityShortfall()));
    }
}

// 9. 460.9's per-level `SuppressFlagZombie` (T66).
//
// `frontyard_75` carries the switch in `content` (271 levels do, 215 of them true; the value comes
// from `native/generated/patch_460_9.json` by way of t64), and its single wave is a flag wave 18 s
// in — so one level proves both halves of the contract: as shipped the flag must be dropped, and
// with the same level's switch flipped in memory (never on disk) the flag must come back.
//
// This kernel has no separate flag-zombie entity: a flag wave differs only by the marker the
// director carries, and the spread window (`tuning::kFlagWaveSpreadSeconds`) is baked into the
// schedule when it is built. So "the flag wave arrives as an ordinary wave" is exactly "the marker
// is dropped and the wave is counted", which is what these assertions check.
void testSuppressFlagZombie(const Catalog& catalog) {
    const auto it = catalog.levels.find("frontyard_75");
    if (it == catalog.levels.end()) fail("missing level: frontyard_75");
    const pvz::LevelDefinition source = it->second;
    check(source.extra.value("suppressFlagZombie", false),
          "content must carry extra.suppressFlagZombie = true for frontyard_75 (t64)");
    std::size_t flagWaves = 0;
    for (const pvz::WaveDefinition& wave : source.waves)
        if (wave.flag) ++flagWaves;
    check(flagWaves > 0, "frontyard_75 must carry a flag wave for the switch to have anything to do");
    {
        World world(catalog, source, 66);
        check(world.suppressFlagZombie(), "extra.suppressFlagZombie = true must be read at construction");
        runUntilWavesSpawned(world);
        check(world.wave() == world.waves(), "every wave must still be handed over");
        check(world.flagSuppressed() == static_cast<int>(flagWaves),
              "each flag wave must be counted exactly once, got " + std::to_string(world.flagSuppressed()));
        check(flagSpawns(world) == 0, "a suppressed flag wave must not carry the marker");
        check(countEvents(world, "flag_wave_suppressed") == flagWaves,
              "the suppression must be visible in the event log");
        check(countEvents(world, "wave_spawn") > 0, "the zombies themselves must still arrive");
    }
    {
        pvz::LevelDefinition level = source;
        level.extra["suppressFlagZombie"] = false;
        World world(catalog, level, 66);
        check(!world.suppressFlagZombie(), "extra.suppressFlagZombie = false must keep the flag waves");
        runUntilWavesSpawned(world);
        check(world.flagSuppressed() == 0, "a level that does not suppress must count nothing");
        check(flagSpawns(world) > 0, "without the switch the flag wave keeps its marker");
    }
}

// 3. An unwired mechanic is counted, named and graded - and does not stop the level.
void testUnknownMechanicsAreCounted(const Catalog& catalog) {
    {
        // beach_10 declares a tide, which this round does not run.
        World world(catalog, catalog.levels.at("beach_10"), 76);
        const auto& unknown = world.mechanicUnknown();
        check(!unknown.empty(), "beach_10 must report its unwired mechanics");
        check(unknown.count("events") == 1, "beach_10's tide must be counted under events");
        check(world.mechanicUnknownKinds() == unknown.size(), "the kind count must match the map");
        check(world.mechanicUnknownInstances() == 1, "one instance for one module");
        check(pvz::engine::mechanicTierFor("events") == MechanicTier::unknown, "events is not wired yet");
        check(countEvents(world, "mechanic_unknown") == 1, "the gap must be in the event log");
        for (int step = 0; step < 60; ++step) world.step();
        check(world.status() == "playing", "an unwired mechanic must not stop the level");
    }
    {
        // jittered spawners are the ordinary wave path, so they are `covered`, not `unknown`: a
        // level that only has one must report a clean sheet.
        World world(catalog, catalog.levels.at("beach_1"), 77);
        check(world.mechanicUnknown().count("spawners.jittered") == 0,
              "the jittered spawner is the wave path and must not be counted as unwired");
        check(pvz::engine::mechanicTierFor("spawners.jittered") == MechanicTier::covered,
              "the jittered spawner must be graded covered");
        // The wired ones are covered too, even though the kernel did read them.
        check(pvz::engine::mechanicTierFor("conveyor") == MechanicTier::covered, "the belt is wired");
        check(pvz::engine::mechanicTierFor("protectThePlant") == MechanicTier::covered, "protect is wired");
        check(pvz::engine::mechanicTierFor("boardGrid") == MechanicTier::unknown, "the mold grid is not wired");
    }
    {
        // A level with nothing beyond its waves has an empty sheet entry.
        World world(catalog, catalog.levels.at("frontyard_1"), 78);
        check(world.mechanicUnknown().empty(), "frontyard_1 must report no unwired mechanics");
        check(world.mechanicUnknownInstances() == 0, "no instances on a plain level");
        check(world.initialPlantsLaid() == 0 && world.gridItemsSpawned() == 0, "a plain level opens empty");
        check(!world.conveyorLevel(), "frontyard_1 has a seed bank");
    }
    {
        // 67 levels name `initialGridItems` without saying what stands in them: the sheet leaves
        // `type` null because the module only names the item inside its own package. The cells are
        // blocked in the original, so this is reported as a gap rather than dropped - a level that
        // quietly opens empty is exactly what this task exists to prevent.
        World world(catalog, catalog.levels.at("dark_63"), 83);
        const auto& unknown = world.mechanicUnknown();
        check(unknown.count("initialGridItems.unresolved") == 1,
              "dark_63's unnamed grid items must be reported, kinds=" + std::to_string(unknown.size()));
        check(world.gridItemsSpawned() == 0, "an item with no name cannot be placed");
        check(pvz::engine::mechanicTierFor("initialGridItems.unresolved") == MechanicTier::unknown,
              "an unresolved grid item is a gap, not a covered mechanic");
        check(countEvents(world, "mechanic_unknown") >= 1, "the gap must be in the event log");
        for (int step = 0; step < 60; ++step) world.step();
        check(world.status() == "playing", "an unnamed item must not stop the level");
    }
}

// The mechanism switch has to be able to reproduce the pre-S5.13 world: that is what keeps the
// smoke baseline meaningful while the wiring is still growing.
void testMechanicsOffKeepsTheOldWorld(const Catalog& catalog) {
    pvz::engine::WorldOptions options;
    options.mechanics = false;
    World plain(catalog, catalog.levels.at("beach_1"), 79);
    World off(catalog, catalog.levels.at("beach_1"), 79, options);
    check(!off.conveyorLevel(), "mechanics off must not open a belt");
    check(off.initialPlantsLaid() == 0, "mechanics off must not lay the opening field");
    check(off.mechanicUnknown().empty(), "mechanics off must not report unknown mechanics");
    check(off.hash() != plain.hash(), "mechanics off must differ from the wired world");
    for (int step = 0; step < 60; ++step) {
        plain.step();
        off.step();
    }
    check(off.hash() != plain.hash(), "the two worlds must stay different after a second of play");
}


// 4. T66: a special spawner row puts zombies on the lawn, and a level without one says nothing.
void testSpawnersLandOnTheLawn(const Catalog& catalog) {
    const LevelMechanicsTable& table = LevelMechanicsTable::shared();
    const pvz::engine::LevelMechanics* sheet = table.find("carnival_86");
    check(sheet != nullptr, "carnival_86 must carry its level mechanics");
    const pvz::engine::SpawnerSpec* grid = sheet->spawner(pvz::engine::SpawnerKind::grid);
    check(grid != nullptr && !grid->rows.empty(), "carnival_86 must carry a grid generator");
    World world(catalog, catalog.levels.at("carnival_86"), 7);
    check(world.spawnerLevel(), "a level with spawner rows must report itself as a spawner level");
    // Wave 1 lands at 18 s. The grid row keyed to that wave must arrive with it, not "some time
    // later": the queue is drained right after `tickWaves`.
    const std::uint64_t tickCap = 4000;
    while (world.wave() < 1 && world.status() == "playing" && world.tick() < tickCap) world.step();
    check(world.wave() >= 1, "wave 1 must land inside the guard window");
    check(world.spawnerSpawned().count("spawners.grid") == 1,
          "carnival_86's grid row must report the kind it used");
    check(world.spawnerSpawned().at("spawners.grid") > 0,
          "the grid row must put at least one zombie on the lawn, got " +
              std::to_string(world.spawnerSpawned().at("spawners.grid")));
    check(countEvents(world, "spawner_spawn") > 0, "a wired spawner must raise spawner_spawn");
    // `frontyard_1` declares no spawner module: `--run-level` must not print `mechanicWired` for
    // it, which is why the array is gated on `spawnerLevel()`.
    World plain(catalog, catalog.levels.at("frontyard_1"), 7);
    check(!plain.spawnerLevel(), "frontyard_1 must not report itself as a spawner level");
    check(plain.spawnerSpawned().empty(), "a level without special spawners must report no arrivals");
}

void run(const fs::path& content, const fs::path& pack) {
    pvz::CatalogOptions options;
    options.contentPack = pack;
    const Catalog catalog = pvz::loadCatalog(content, options);
    check(!catalog.levels.empty(), "the content must carry levels for the mechanics tests");
    testTableShape();
    testConveyorNeedsNoSun(catalog);
    testInitialPlantsAreLaid(catalog);
    testGridItemsBlockAndBreak(catalog);
    testProtectMission(catalog);
    testProtectThresholds(catalog);
    testProtectCapacityShortfall(catalog);
    testSuppressFlagZombie(catalog);
    testSpawnersLandOnTheLawn(catalog);
    testUnknownMechanicsAreCounted(catalog);
    testMechanicsOffKeepsTheOldWorld(catalog);
}

} // namespace

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    if (argc < 4) {
        std::cerr << "usage: mechanics_test <content> <pack> <temp>\n";
        return 2;
    }
    try {
        run(fs::path{argv[1]}, fs::path{argv[2]});
    } catch (const std::exception& error) {
        std::cerr << "mechanics test failed: " << error.what() << '\n';
        return 1;
    }
    std::cout << "mechanics tests passed\n";
    return 0;
}
