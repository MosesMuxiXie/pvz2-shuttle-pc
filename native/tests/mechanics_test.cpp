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
using pvz::engine::InitialPlant;
using pvz::engine::LevelMechanics;
using pvz::engine::LevelMechanicsTable;
using pvz::engine::MechanicTier;
using pvz::engine::PlantEntity;
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
    // T88 took this from 446 to 293: the tide (60), the frost wind (64), the board mask (49) and
    // the eight sun caps stopped being gaps, and the challenge wrappers (13) and the spider rains
    // (118) - plus the two long-standing partials, `initialGridItems.unresolved` and
    // `spawners.gravestone.unpositioned` - are what is left.
    check(table.withUnknown() == 293, "levels with an unwired mechanic, got " + std::to_string(table.withUnknown()));
    check(table.withEvents() == 123, "levels with an Events module, got " + std::to_string(table.withEvents()));
    check(table.withBoardGrid() == 49, "levels with a board mask, got " + std::to_string(table.withBoardGrid()));
    check(table.withSunCap() == 8, "levels with a sun cap, got " + std::to_string(table.withSunCap()));
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
        // 4 of 5 on paper, and five targets on three cells ((2,3) three deep). C55 made the stack
        // real: all five stand, so the sheet's four-of-five can actually be satisfied - the mission
        // used to be unwinnable because a second plant was refused on a taken cell.
        World world(catalog, catalog.levels.at("egypt_74"), 81);
        check(world.protectedPlantCount() == 5,
              "egypt_74 lists five targets, so five must stand, got " +
                  std::to_string(world.protectedPlantCount()));
        check(world.unplacedProtectedPlants() == 0,
              "no target may be dropped now that a cell can carry a stack, got " +
                  std::to_string(world.unplacedProtectedPlants()));
        check(countEvents(world, "protect_plant_unplaced") == 0, "nothing was dropped, so nothing is reported");
        check(world.protectStackAt(2, 3).size() == 3, "three targets must share cell (2,3), got " +
                                                          std::to_string(world.protectStackAt(2, 3).size()));
        check(world.deepestProtectStack() == 3, "the deepest stack here is three, got " +
                                                    std::to_string(world.deepestProtectStack()));
        check(world.requiredProtectedPlants() == 4,
              "egypt_74 requires four, got " + std::to_string(world.requiredProtectedPlants()));
        check(world.requestedProtectedPlants() == 4, "the sheet still asks for four");
        check(!world.protectClamped(), "a board that can hold every target must not be clamped");
        auto ids = protectedIds(world);
        world.damagePlant(ids[0], 1.0e6);
        check(world.status() == "playing",
              "four of five surviving still satisfies the mission, got: " + world.status());
        ids = protectedIds(world);
        world.damagePlant(ids[0], 1.0e6);
        check(world.status() == "lost",
              "dropping to three must lose a four-of-five mission, got: " + world.status());
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

// 2g. C55: one cell, several protect targets. `lostcity_45` puts seven of its eight targets on
// (4,3) and `egypt_74` three on (2,3); `sky_31` puts one on each of five cells its own
// `initialPlants` already filled. The stack is the fix for T59's eleven unwinnable missions, so the
// order inside it has to be an observable contract, not an implementation detail: the innermost
// plant is the one planted first and the outermost one is what a zombie meets first.
void testProtectStackOnOneCell(const Catalog& catalog) {
    {
        World world(catalog, catalog.levels.at("lostcity_45"), 70);
        const auto stack = world.protectStackAt(4, 3);
        check(stack.size() == 7, "lostcity_45 must stack seven targets on (4,3), got " +
                                     std::to_string(stack.size()));
        check(world.protectedPlantCount() == 8, "all eight targets must stand, got " +
                                                    std::to_string(world.protectedPlantCount()));
        for (std::size_t i = 0; i < stack.size(); ++i) {
            check(stack[i] != nullptr && stack[i]->stackDepth == static_cast<int>(i),
                  "the stack must be ordered innermost-first at index " + std::to_string(i));
            check(stack[i]->protectedPlant, "every plant in a protect stack is a protect target");
        }
        check(world.deepestProtectStack() == 7, "seven deep is the deepest stack in the shipped data");
        check(world.plantAt(4, 3) == stack.back(), "plantAt must answer with the outermost plant");
        check(world.plantAt(0, 2) != nullptr && world.plantAt(0, 2)->stackDepth == 0,
              "the singleton target on (0,2) is the only plant there");
        // Each plant in the stack is separately damageable: kill the middle one and the other six
        // must be untouched.
        const auto* middle = stack[3];
        const auto middleId = middle->id;
        world.damagePlant(middleId, 1.0e6);
        check(world.aliveProtectedPlants() == 7, "one of eight dead must leave seven, got " +
                                                    std::to_string(world.aliveProtectedPlants()));
        std::size_t stillStanding = 0;
        for (const auto* plant : world.protectStackAt(4, 3)) {
            if (plant->alive) ++stillStanding;
        }
        check(stillStanding == 6, "six of the seven on (4,3) must still stand, got " +
                                      std::to_string(stillStanding));
        check(world.plantAt(4, 3) != nullptr && world.plantAt(4, 3)->id != middleId,
              "killing a middle plant must leave the outermost one on top");
    }
    {
        // The missions whose targets land on cells the level's own plants filled. A lilypad can hold a
        // bloomerang, a flowerpot a melonpult, so these cannot be solved by upgrading the existing
        // plant in place - the target has to be a second plant on the same square. Which cell that is
        // comes from the sheet: guessing coordinates here is how this test first went red.
        const char* levels[] = {"carnival_81", "chinesegarden_57", "frontyard_53", "lostcity_67",
                                "sky_31"};
        for (const char* levelId : levels) {
            const LevelMechanics* mechanics = LevelMechanicsTable::shared().find(levelId);
            check(mechanics != nullptr, std::string(levelId) + " must carry a mechanics row");
            if (mechanics == nullptr) continue;
            int row = -1;
            int col = -1;
            for (const auto& target : mechanics->protect.plants) {
                const bool own = std::any_of(
                    mechanics->initialPlants.begin(), mechanics->initialPlants.end(),
                    [&target](const InitialPlant& plant) {
                        return plant.gridY == target.gridY && plant.gridX == target.gridX;
                    });
                if (own) {
                    row = target.gridY;
                    col = target.gridX;
                    break;
                }
            }
            check(row >= 0, std::string(levelId) +
                                " must name a protect target on a cell its own plants already filled");
            if (row < 0) continue;
            World world(catalog, catalog.levels.at(levelId), 71);
            const auto stack = world.protectStackAt(row, col);
            check(stack.size() >= 2, std::string(levelId) + " must hold its target on top of the level's plant");
            const PlantEntity* bottom = stack.front();
            const PlantEntity* top = stack.back();
            check(!bottom->protectedPlant, std::string(levelId) + "'s own plant is not the target");
            check(top->protectedPlant, std::string(levelId) + "'s target stands above it");
            check(top->stackDepth > bottom->stackDepth, std::string(levelId) + " must order the stack");
        }
    }
}

// 2h. C55: the loss rule counts plants, not cells. Before the stack existed the two were the same
// number; now a mission that keeps four of five has to survive losing one plant out of a cell that
// carries three, and losing the plant *under* one must count the same as losing the one on top.
void testProtectDeathCountsEveryPlant(const Catalog& catalog) {
    {
        World world(catalog, catalog.levels.at("egypt_74"), 72);
        check(world.requiredProtectedPlants() == 4, "this mission requires four of five");
        // Kill the innermost plant of the three-deep stack: the count must drop to four and the
        // mission must keep playing, even though the cell still shows a plant.
        auto stack = world.protectStackAt(2, 3);
        check(stack.size() == 3, "the cell must carry three before the kill");
        world.damagePlant(stack.front()->id, 1.0e6);
        check(world.aliveProtectedPlants() == 4, "four of five must remain alive, got " +
                                                     std::to_string(world.aliveProtectedPlants()));
        check(world.status() == "playing",
              "losing the plant under the stack must not end a four-of-five mission, got: " + world.status());
        check(world.plantAt(2, 3) != nullptr && world.plantAt(2, 3)->alive,
              "the cell must still hold a living plant after the innermost one dies");
        world.damagePlant(world.plantAt(2, 3)->id, 1.0e6);
        check(world.aliveProtectedPlants() == 3, "three must be left, got " +
                                                     std::to_string(world.aliveProtectedPlants()));
        check(world.status() == "lost",
              "three cannot satisfy four, so the mission must be lost, got: " + world.status());
        check(world.protectFailures() == 1, "the loss must be counted once, got " +
                                                std::to_string(world.protectFailures()));
    }
    {
        // A stack that loses only its outer plants keeps the mission alive: `lostcity_45` needs all
        // eight, so killing the outermost must lose it at once - the opposite probe to the case
        // above, and the one that pins "count plants" against "count cells with a plant left".
        World world(catalog, catalog.levels.at("lostcity_45"), 73);
        check(world.requiredProtectedPlants() == 8, "lostcity_45 requires all eight");
        world.damagePlant(world.plantAt(4, 3)->id, 1.0e6);
        check(world.aliveProtectedPlants() == 7, "seven must be left");
        check(world.status() == "lost", "a mission that requires all eight must end on the first death");
    }
}

// 2i. C55's defensive half. `requiredProtectedPlants()` is `min(sheet, placed)`, so no mission can
// ask for more survivors than its board holds - that invariant is what makes the eleven T59
// missions winnable by construction. On shipped data the clamp never has to fire (the stacks reach
// the sheet's own number), which this case pins: every protect level reports no shortfall and is
// not clamped. A future pack whose cells are all blocked by grid items would flip both, and these
// two assertions are what would notice.
void testProtectRequirementNeverExceedsTheBoard(const Catalog& catalog) {
    const LevelMechanicsTable& table = LevelMechanicsTable::shared();
    int protectLevels = 0;
    int clamped = 0;
    int shortCount = 0;
    for (const auto& [id, level] : catalog.levels) {
        const LevelMechanics* mechanics = table.find(id);
        if (mechanics == nullptr || mechanics->protect.plants.empty()) continue;
        World world(catalog, level, 74);
        ++protectLevels;
        check(world.requiredProtectedPlants() <= world.protectedPlantCount(),
              id + ": the requirement must never exceed the plants that stand");
        check(world.requestedProtectedPlants() == mechanics->protect.requiredSurvivors(),
              id + ": the request must report the sheet's own number");
        if (world.protectClamped()) ++clamped;
        if (world.protectCapacityShortfall() != 0) ++shortCount;
        check(world.protectCapacityShortfall() == 0,
              id + ": every shipped protect level must hold its targets, short by " +
                  std::to_string(world.protectCapacityShortfall()));
    }
    check(protectLevels == 286, "286 levels carry protect targets, got " + std::to_string(protectLevels));
    check(clamped == 0, "no shipped level may be clamped, got " + std::to_string(clamped));
    check(shortCount == 0, "no shipped level may report a shortfall, got " + std::to_string(shortCount));
}

// 2j. The eleven T59 missions, one by one, must initialise without throwing and must end up with
// their targets standing. This is deliberately a loop over the named levels: a regression that
// makes one of them throw takes the whole suite down with a message that names the level.
void testProtectLevelsInitialize(const Catalog& catalog) {
    struct Case {
        const char* level;
        int must;
        int placed;
    } cases[] = {
        {"carnival_23", 6, 6},  {"carnival_79", 1, 1},  {"carnival_81", 3, 3},
        {"chinesegarden_57", 3, 3}, {"egypt_74", 4, 5}, {"frontyard_51", 6, 6},
        {"frontyard_53", 2, 2}, {"lostcity_45", 8, 8}, {"lostcity_67", 1, 1},
        {"sky_31", 5, 5},       {"sky_46", 10, 10},
    };
    for (const Case& one : cases) {
        World world(catalog, catalog.levels.at(one.level), 75);
        check(world.requestedProtectedPlants() == one.must,
              std::string(one.level) + " must ask for " + std::to_string(one.must) + ", got " +
                  std::to_string(world.requestedProtectedPlants()));
        check(world.protectedPlantCount() == one.placed,
              std::string(one.level) + " must place " + std::to_string(one.placed) + ", got " +
                  std::to_string(world.protectedPlantCount()));
        check(world.requiredProtectedPlants() == one.must,
              std::string(one.level) + " must require " + std::to_string(one.must) + ", got " +
                  std::to_string(world.requiredProtectedPlants()));
        check(!world.protectClamped(), std::string(one.level) + " must not be clamped");
        check(world.unplacedProtectedPlants() == 0,
              std::string(one.level) + " must not drop a target, dropped " +
                  std::to_string(world.unplacedProtectedPlants()));
    }
}


// (one plant per cell) instead of the report. The report itself stays: it now fires only on a board
// whose cells are blocked by grid items, which no shipped level has, so what this case pins down is
// that the eleven are *quiet* and every one of them can actually be won.
void testProtectCapacityShortfall(const Catalog& catalog) {
    const char* eleven[] = {"carnival_23", "carnival_79", "carnival_81", "chinesegarden_57",
                            "egypt_74",    "frontyard_51", "frontyard_53", "lostcity_45",
                            "lostcity_67", "sky_31",       "sky_46"};
    for (const char* id : eleven) {
        World world(catalog, catalog.levels.at(id), 90);
        check(world.protectedPlantCount() > 0, std::string(id) + " must have its targets standing");
        check(world.protectCapacityShortfall() == 0,
              std::string(id) + " must not be short after C55, got " +
                  std::to_string(world.protectCapacityShortfall()));
        check(countEvents(world, "protect_capacity_shortfall") == 0,
              std::string(id) + " must not report a shortfall any more");
        check(countEvents(world, "protect_requirement_clamped") == 0,
              std::string(id) + " must not be clamped: its cells can hold every target");
        check(world.requiredProtectedPlants() <= world.protectedPlantCount(),
              std::string(id) + " must never ask for more survivors than stand");
        check(world.status() == "playing", std::string(id) + " must start playing");
    }
    {
        // The one that used to protect nothing: `carnival_79` lists its single target on a cell the
        // level's own pvine1 stood on. It now stacks on top of it instead of being dropped.
        World world(catalog, catalog.levels.at("carnival_79"), 91);
        check(world.protectedPlantCount() == 1,
              "carnival_79 must protect its one target, got " + std::to_string(world.protectedPlantCount()));
        check(world.protectStackAt(0, 0).size() == 2, "the target stands on top of the level's own plant");
        check(world.plantAt(0, 0) != nullptr && world.plantAt(0, 0)->stackDepth == 1,
              "the protect target is the outermost plant on (0,0)");
        check(world.requiredProtectedPlants() == 1, "one of one must survive");
        world.damagePlant(protectedIds(world).at(0), 1.0e6);
        check(world.status() == "lost", "losing the only target must lose the mission, got: " + world.status());
    }
    {
        // beach_88 lists five and needs four: enough cells, so no report - the guard against a
        // zero gap being mistaken for a shortfall.
        World world(catalog, catalog.levels.at("beach_88"), 92);
        check(countEvents(world, "protect_capacity_shortfall") == 0,
              "beach_88 has enough cells and must not report a shortfall");
        check(world.protectCapacityShortfall() == 0,
              "beach_88 must report no gap, got " + std::to_string(world.protectCapacityShortfall()));
    }
    {
        // beach_14 lists exactly as many targets as it requires (five of five) and fits them all.
        World world(catalog, catalog.levels.at("beach_14"), 93);
        check(world.protectedPlantCount() == world.requiredProtectedPlants(),
              "beach_14 places exactly as many targets as it requires");
        check(countEvents(world, "protect_capacity_shortfall") == 0, "an exact fit is not a shortfall");
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
        // T88: beach_10's tide is wired now, so it must report a clean sheet and actually move
        // the waterline when its waves land (TidalChange rows at waves 2..9, column = the wave).
        World world(catalog, catalog.levels.at("beach_10"), 76);
        const auto& unknown = world.mechanicUnknown();
        check(unknown.empty(), "beach_10's tide is wired, kinds left: " + std::to_string(unknown.size()));
        check(world.mechanicUnknownKinds() == unknown.size(), "the kind count must match the map");
        check(world.mechanicUnknownInstances() == 0, "no instances left on a wired tide level");
        check(pvz::engine::mechanicTierFor("events.tide") == MechanicTier::covered, "the tide is wired");
        check(pvz::engine::mechanicTierFor("spawners.spider") == MechanicTier::unknown,
              "a spider rain is still unwired: no spider exists in content or the pack");
        for (int step = 0; step < 60; ++step) world.step();
        check(world.status() == "playing", "a wired mechanic must not stop the level");
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
        check(pvz::engine::mechanicTierFor("boardGrid") == MechanicTier::covered,
              "the board mask is carried as data since T88");
        check(pvz::engine::mechanicTierFor("mutators.maxSun") == MechanicTier::covered,
              "the sun cap is wired since T88");
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

// T88-1: the tide is a wave-triggered row, not a timer. beach_2 states two absolute changes:
// column 6 on wave 1, column 3 on wave 2.
void testTideFollowsTheWaves(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("beach_2"), 88);
    check(world.tideChanges() == 0, "the waterline must not move before a wave lands");
    check(world.tideColumn() == 0, "no tide yet, column=" + std::to_string(world.tideColumn()));
    const std::uint64_t cap = world.tick() + 20000;
    while (world.wave() < 2 && world.status() == "playing" && world.tick() < cap) world.step();
    std::vector<int> columns;
    for (const auto& entry : world.events()) {
        if (entry.value("type", std::string{}) != "tide_changed") continue;
        columns.push_back(entry.value("details", pvz::Json::object()).value("column", -1));
    }
    check(!columns.empty(), "beach_2's tide must arrive with its waves");
    check(world.tideChanges() == static_cast<int>(columns.size()),
          "tideChanges must match the log: " + std::to_string(world.tideChanges()) + " vs " +
              std::to_string(columns.size()));
    check(world.tideColumn() == columns.back(), "the state must be the last change applied");
    check(columns.front() == 6,
          "wave 1 sets the waterline to column 6, got " + std::to_string(columns.front()));
}

/// A zombie on `row` at the far right, as a probe for wind and for row placement.
double rowX(const World& world, int row) {
    for (const auto& zombie : world.zombies()) {
        if (zombie.alive && zombie.row == row) return zombie.x;
    }
    return -1.0;
}

// T88-2: a frost wind pushes the zombies standing on its rows. iceage_25's wave 1 names rows
// 0/2/3/4 and never row 1, so row 1 is the control.
void testFrostWindPushesItsRows(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("iceage_25"), 89);
    world.spawnZombieAt("basic", 0, 4.0);
    world.spawnZombieAt("basic", 1, 4.0);
    double row0Before = rowX(world, 0);
    double row1Before = rowX(world, 1);
    check(row0Before > 0.0 && row1Before > 0.0, "both probes must be on the lawn");
    const std::uint64_t cap = world.tick() + 20000;
    while (world.wave() < 1 && world.status() == "playing" && world.tick() < cap) {
        row0Before = rowX(world, 0);
        row1Before = rowX(world, 1);
        world.step();
    }
    check(world.frostWinds() >= 1, "iceage_25's wave 1 must blow a wind");
    check(world.frostWinds() == static_cast<int>(countEvents(world, "frost_wind")),
          "frostWinds must match the log");
    const pvz::Json wind = firstEvent(world, "frost_wind");
    check(wind.value("direction", std::string{}) == "right", "the wind blows right");
    check(wind.value("pushed", 0) >= 1, "the wind must push at least the row 0 probe");
    const double row0After = rowX(world, 0);
    const double row1After = rowX(world, 1);
    check(row0After > row0Before,
          "the wind must carry row 0's zombie right: " + std::to_string(row0Before) + " -> " +
              std::to_string(row0After));
    check(row1After <= row1Before,
          "row 1 is not in the wind and must only walk left: " + std::to_string(row1Before) + " -> " +
              std::to_string(row1After));
}

// T88-3: `LevelMutatorMaxSunProps.maxSunOverride` caps the bank. carnival_82 states 200 and its
// content opens at 550, so the opening bank is clamped too - and says so.
void testSunCapStopsTheBank(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("carnival_82"), 90);
    check(world.sunCap() == 200, "carnival_82's cap, got " + std::to_string(world.sunCap()));
    check(world.sun() == 200,
          "an opening bank above its own cap must be clamped, got " + std::to_string(world.sun()));
    check(countEvents(world, "sun_capped") == 1, "the clamp must be logged, not silent");
    check(world.plant("sunflower", 2, 0).empty(), "the first sunflower must plant");
    // A second card of the same kind has to wait out its recharge, so step past it rather than
    // asserting twice in one tick.
    for (int tick = 0; tick < 700; ++tick) world.step();
    // (2,1) is an initial cabbagepult in this level, so the second cell is (2,2); picking an
    // occupied cell would fail on `cell occupied` and never exercise the recharge at all.
    check(world.plant("sunflower", 2, 2).empty(), "the second sunflower must plant after its recharge");
    std::int64_t peak = world.sun();
    std::size_t collected = 0;
    for (int step = 0; step < 6000; ++step) {
        world.step();
        for (const auto& sun : world.suns()) {
            if (world.collect(sun.id)) {
                ++collected;
                peak = std::max(peak, world.sun());
            }
        }
        peak = std::max(peak, world.sun());
    }
    check(collected > 0, "the sunflowers must produce something to collect");
    check(peak <= 200, "the bank must never pass the cap, peaked at " + std::to_string(peak));
    check(world.sun() == 200, "the run must end at the cap, got " + std::to_string(world.sun()));
}

// T88-4: the board mask is carried as data. The sheet gives its 0/1 codes no meaning, so the
// kernel loads them, counts them, and refuses to invent a second layout.
void testBoardGridMaskIsCarried(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("beach_94"), 91);
    const pvz::engine::LevelMechanics* spec = LevelMechanicsTable::shared().find("beach_94");
    check(spec != nullptr && spec->hasBoardGrid(), "beach_94 must carry a board mask");
    int marked = 0;
    for (const auto& row : spec->boardGrid.cells) {
        for (const int cell : row) {
            if (cell != 0) ++marked;
        }
    }
    check(world.boardGridIndex() == 0, "layout 0 must be loaded");
    check(world.boardGridMarkedCells() == marked,
          "the mask must be carried whole: " + std::to_string(world.boardGridMarkedCells()) + " vs " +
              std::to_string(marked));
    check(marked > 0, "beach_94's mask must mark something");
    check(world.boardGridMarked(0, 0) == (spec->boardGrid.cells[0][0] != 0),
          "a cell's code must come straight from the sheet");
    check(!world.applyBoardGrid(1), "a level with one layout must refuse layout 1");
    check(countEvents(world, "board_grid_rejected") == 1, "the refusal must be logged");
    check(world.boardGridIndex() == 0, "a refused layout must not change the board");
    // And the codes are not a rule. beach_94 carries a belt (so does most of the mold family), so
    // the planting probe uses carnival_7: same "mold" mask, an ordinary seed bank, so a marked cell
    // can actually be used and a refusal would mean the mask had been turned into a rule.
    World bank(catalog, catalog.levels.at("carnival_7"), 96);
    check(bank.boardGridIndex() == 0 && bank.boardGridMarkedCells() > 0,
          "carnival_7 must carry a mask too");
    std::pair<int, int> target{-1, -1};
    for (int row = 0; row < bank.rows() && target.first < 0; ++row) {
        for (int col = 0; col < bank.cols(); ++col) {
            if (!bank.boardGridMarked(row, col)) continue;
            if (bank.plantAt(row, col) != nullptr || bank.gridItemAt(row, col) != nullptr) continue;
            target = {row, col};
            break;
        }
    }
    check(target.first >= 0, "the mask must leave at least one free marked cell");
    const std::string refusal =
        bank.plant(catalog.levels.at("carnival_7").deck.front(), target.first, target.second);
    check(refusal.empty(),
          "a marked cell must still take a plant - the codes have no meaning in the sheet, refused: " +
              refusal);
    check(bank.plantAt(target.first, target.second) != nullptr, "the plant must be on the lawn");
}

// T88-5: what is left unwired is exactly what the report says is left.
void testWiringLeavesOnlyTheDocumentedGaps(const Catalog& catalog) {
    World tide(catalog, catalog.levels.at("beach_2"), 92);
    check(tide.mechanicUnknown().count("events.tide") == 0, "the tide is wired");
    check(tide.mechanicUnknown().empty(),
          "beach_2 must be clean, kinds left: " + std::to_string(tide.mechanicUnknown().size()));
    World wrapper(catalog, catalog.levels.at("beach_21"), 93);
    check(wrapper.mechanicUnknown().count("mutators") == 1,
          "a challenge wrapper is not a modifier and must stay counted");
    World spider(catalog, catalog.levels.at("carnival_1"), 94);
    check(spider.mechanicUnknown().count("spawners.spider") > 0,
          "a spider rain has no zombie to place and must stay counted");
    World mask(catalog, catalog.levels.at("beach_94"), 95);
    check(mask.mechanicUnknown().count("boardGrid") == 0, "a carried mask is not a gap");
}

void run(const fs::path& content, const fs::path& pack) {
    pvz::CatalogOptions options;
    options.contentPack = pack;
    const Catalog catalog = pvz::loadCatalog(content, options);
    check(!catalog.levels.empty(), "the content must carry levels for the mechanics tests");
    testTableShape();
    // T88: the Events module, the board mask and the sun cap. These run early because they are
    // self-contained (one level each) and because the protect-stack block below exercises the
    // overlay rules that the same `plantAt` feeds.
    testTideFollowsTheWaves(catalog);
    testFrostWindPushesItsRows(catalog);
    testSunCapStopsTheBank(catalog);
    testBoardGridMaskIsCarried(catalog);
    testWiringLeavesOnlyTheDocumentedGaps(catalog);
    testConveyorNeedsNoSun(catalog);
    testInitialPlantsAreLaid(catalog);
    testGridItemsBlockAndBreak(catalog);
    testProtectMission(catalog);
    testProtectThresholds(catalog);
    testProtectCapacityShortfall(catalog);
    testProtectStackOnOneCell(catalog);
    testProtectDeathCountsEveryPlant(catalog);
    testProtectRequirementNeverExceedsTheBoard(catalog);
    testProtectLevelsInitialize(catalog);
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
