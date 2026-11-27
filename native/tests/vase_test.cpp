// A1 (T80) vasebreaker: the arcade mode the 47 `extra.vasebreaker` levels carry.
//
// The sheet gives a count per content type, a column band and (on five levels) excluded cells - and
// nothing else. All 459 entries carry `row: null, col: null`, so the cell layout is a deterministic
// inference this file pins down rather than a reading of the data. Everything else - the four
// content classes, the missing seed bank, the "clear the board" win condition - is the mode's own
// contract, and each one gets a case here.
//
// One case needs a vase the shipped sheet does not have (a sun vase: every `sunAmount` is null), so
// it writes a two-row table into the test's temp directory and hands it to the world through
// `WorldOptions::vaseTable`. That is the only seam; every other case drives real content.
#include "catalog.hpp"
#include "engine/vase.hpp"
#include "engine/world.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace {

namespace fs = std::filesystem;
using pvz::Catalog;
using pvz::engine::VaseContent;
using pvz::engine::VaseEntry;
using pvz::engine::VaseTable;
using pvz::engine::World;
using pvz::engine::WorldOptions;

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

std::string cellsOf(const World& world) {
    std::string text;
    for (const auto& vase : world.vases()) {
        text += std::to_string(vase.row);
        text += ',';
        text += std::to_string(vase.col);
        text += ';';
    }
    return text;
}

/// One entry of the sheet, or a hard failure: every case below names a level it expects to exist.
const pvz::engine::VaseSpec& specOf(const VaseTable& table, const std::string& levelId) {
    const auto* spec = table.find(levelId);
    if (spec == nullptr) fail("the vase table must carry " + levelId);
    return *spec;
}

/// A level with the vasebreaker flag, by the world's own reckoning: a case that silently fell back to
/// an ordinary level would pass every "no vase" assertion for the wrong reason.
World& requireVaseWorld(World& world, const std::string& levelId) {
    check(world.vasebreaker(), levelId + " must open as a vasebreaker board");
    check(!world.vases().empty(), levelId + " must open with vases on the lawn");
    return world;
}

// ---------------------------------------------------------------- table -----
void testTableShape() {
    const VaseTable& table = VaseTable::shared();
    check(table.size() == 47, "the vase table must carry the 47 vasebreaker levels, got " +
                                  std::to_string(table.size()));
    check(table.totalVases() == 1435, "the table must hold 1435 vases, got " +
                                          std::to_string(table.totalVases()));

    const auto& beach = specOf(table, "beach_69");
    check(beach.total == 30, "beach_69 must deal 30 vases, got " + std::to_string(beach.total));
    // The sheet lists 12 rows for this level; the twelfth is a `plantfood` collectable with
    // `count: 0`, i.e. a row that places nothing. The loader drops empty rows so the board is the
    // sum of real counts (the 47 levels add up to the sheet's own vaseTotal of 1435).
    check(beach.entries.size() == 11, "beach_69 must carry 11 non-empty sheet rows, got " +
                                          std::to_string(beach.entries.size()));
    for (const VaseEntry& entry : beach.entries) {
        check(entry.count > 0, "an entry kept from the sheet must place at least one vase");
    }
    check(beach.minColumn == 2 && beach.maxColumn == 8,
          "beach_69's band must be columns 2..8, got " + std::to_string(beach.minColumn) + ".." +
              std::to_string(beach.maxColumn));
    check(beach.excluded.size() == 5,
          "beach_69 must exclude 5 cells, got " + std::to_string(beach.excluded.size()));

    // The one level with the flag and no preset at all: the table carries the key with nothing in it
    // and the world must not turn that into "instant win".
    const auto& empty = specOf(table, "frontyard_166");
    check(empty.empty(), "frontyard_166 must have no vases at all");
    check(table.find("frontyard_1") == nullptr, "an ordinary level must not be in the vase table");
}

// ------------------------------------------------------------- the board -----
void testVasesCoverTheBoard(const Catalog& catalog) {
    const VaseTable& table = VaseTable::shared();
    for (const std::string id : {"beach_69", "egypt_57", "kongfu_83", "carnival_91"}) {
        const auto& spec = specOf(table, id);
        World world(catalog, catalog.levels.at(id), 7);
        requireVaseWorld(world, id);
        check(world.vases().size() == static_cast<std::size_t>(spec.total),
              id + " must lay every vase the sheet counts: got " +
                  std::to_string(world.vases().size()) + " of " + std::to_string(spec.total));
        check(world.vasesUnplaced() == 0, id + " must not drop a vase: the board is big enough");

        std::set<std::pair<int, int>> seen;
        for (const auto& vase : world.vases()) {
            check(vase.row >= 0 && vase.row < world.rows(),
                  id + " put a vase off the board in row " + std::to_string(vase.row));
            check(vase.col >= 0 && vase.col < world.cols(),
                  id + " put a vase off the board in column " + std::to_string(vase.col));
            check(seen.insert({vase.row, vase.col}).second,
                  id + " stacked two vases on one cell");
            for (const auto& cell : spec.excluded) {
                check(!(cell.first == vase.row && cell.second == vase.col),
                      id + " put a vase on a cell the sheet excludes");
            }
        }
        check(world.vaseTally().total == spec.total, id + " must report the vases it laid");
    }
}

void testVaseLayoutFollowsTheSeed(const Catalog& catalog) {
    World first(catalog, catalog.levels.at("beach_69"), 11);
    World again(catalog, catalog.levels.at("beach_69"), 11);
    requireVaseWorld(first, "beach_69");
    check(cellsOf(first) == cellsOf(again), "the same seed must deal the same vase cells");
    check(first.hash() == again.hash(), "two worlds with one seed must hash identically");

    World other(catalog, catalog.levels.at("beach_69"), 12);
    check(cellsOf(other) != cellsOf(first), "a different seed must deal a different layout");
}

// ----------------------------------------------------------- breaking one -----
void testBreakVaseIsIdempotent(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("beach_69"), 3);
    requireVaseWorld(world, "beach_69");
    const auto first = world.vases().front();
    const std::size_t before = world.vases().size();

    const auto broken = world.breakVase(first.row, first.col);
    check(broken.ok, "the first tap on a vase must open it");
    check(!broken.kind.empty(), "an opened vase must say what it held");
    check(world.vaseTally().broke == 1, "opening one vase must count exactly one break");

    const auto again = world.breakVase(first.row, first.col);
    check(!again.ok, "a second tap on the same cell must be a no-op");
    check(world.vaseTally().broke == 1, "a second tap must not pay out twice");
    check(countEvents(world, "vase_broken") == 1, "a second tap must not log a second break");

    world.step();
    check(world.vases().size() == before - 1, "a smashed vase must leave the board on the next step");
    check(world.vaseAt(first.row, first.col) == nullptr, "a smashed cell must read as empty");
}

void testZombieVaseSpawnsInItsRow(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("beach_69"), 5);
    requireVaseWorld(world, "beach_69");
    const pvz::engine::VaseEntity* zombieVase = nullptr;
    for (const auto& vase : world.vases()) {
        if (vase.content == VaseContent::zombie) {
            zombieVase = &vase;
            break;
        }
    }
    if (zombieVase == nullptr) fail("beach_69 must hold at least one zombie vase");
    const int row = zombieVase->row;
    const int col = zombieVase->col;
    const std::string type = zombieVase->payload;

    const auto broken = world.breakVase(row, col);
    check(broken.ok && broken.kind == "zombie", "the zombie vase must open as a zombie");
    check(broken.value == type, "the vase must name the zombie it held");
    check(world.vaseTally().zombies == 1, "one zombie vase must count one zombie");

    bool landed = false;
    for (const auto& zombie : world.zombies()) {
        if (zombie.alive && zombie.row == row) landed = true;
    }
    check(landed, "the vase zombie must walk in on the vase's own row");
    check(countEvents(world, "vase_spawn_zombie") == 1, "opening a zombie vase must log one spawn");
}

void testPlantVaseCardPlantsNextToItsVase(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("egypt_57"), 9);
    requireVaseWorld(world, "egypt_57");
    // egypt_57 is the all-plant level: 30 vases, no zombie among them.
    for (const auto& vase : world.vases()) {
        check(vase.content == VaseContent::plant, "egypt_57 must hold only plant vases");
    }
    const auto first = world.vases().front();
    const auto broken = world.breakVase(first.row, first.col);
    check(broken.ok && broken.kind == "plant", "a plant vase must hand over a card");
    check(world.vaseCards().size() == 1, "one plant vase must hand over exactly one card");
    check(world.vaseTally().plants == 1, "one plant vase must count one plant");

    const std::string far = world.plantVaseCard(0, (first.row + 4) % world.rows(), (first.col + 4) % world.cols());
    check(far == "too far from its vase", "a card must not be plantable across the lawn, got: " + far);
    check(world.vaseCards().size() == 1, "a refused card must stay in hand");

    const std::string planted = world.plantVaseCard(0, first.row, first.col);
    check(planted.empty(), "the vase's own cell must accept its card, got: " + planted);
    check(world.vaseCards().empty(), "a planted card must leave the hand");
    check(world.plants().size() == 1, "planting a vase card must put one plant on the lawn");
    check(world.sunSpent() == 0, "a vase card must cost no sun");
}

void testSunVasePaysSun(const Catalog& catalog, const fs::path& temp) {
    const fs::path path = temp / "vase-sun.json";
    {
        std::ofstream out(path, std::ios::binary | std::ios::trunc);
        if (!out) fail("cannot write the vase fixture");
        out << R"({"levels":{"egypt_57":{"columnRange":{"min":0,"max":2},)"
               R"("excludedCells":[],"vaseCount":2,"vases":[)"
               R"({"type":"sun","count":2,"sunAmount":null,"row":null,"col":null}]}}})";
    }
    const VaseTable table = VaseTable::load(path);
    const auto& spec = specOf(table, "egypt_57");
    check(spec.total == 2, "the fixture must deal two sun vases");
    check(spec.entries.front().content == VaseContent::sun,
          "a sun entry must read as a sun vase");

    WorldOptions options;
    options.vaseTable = &table;
    World world(catalog, catalog.levels.at("egypt_57"), 4, options);
    requireVaseWorld(world, "egypt_57");
    const std::int64_t before = world.sun();
    const auto first = world.vases().front();
    const auto broken = world.breakVase(first.row, first.col);
    check(broken.ok && broken.kind == "sun", "the fixture vase must open as a sun vase");
    check(broken.sun == pvz::engine::kVaseSunValue,
          "a sun vase must pay the tuning constant, got " + std::to_string(broken.sun));
    check(world.sun() == before + pvz::engine::kVaseSunValue, "a sun vase must credit the sun");
    check(world.vaseTally().sun == 1, "one sun vase must count one payout");
    check(countEvents(world, "vase_pickup") == 1, "a sun vase must log one pickup");
}

// ------------------------------------------------------------- the rules -----
void testVaseLevelHasNoSeedBank(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("beach_69"), 6);
    requireVaseWorld(world, "beach_69");
    const std::string reason = world.plant("sunflower", 0, 0);
    check(reason == "no seed bank", "a vasebreaker board must refuse the seed bank, got: " + reason);
    check(world.plants().empty(), "no plant may appear from a seed bank that does not exist");
    // ... and no sky sun either: the mode's only sun comes out of vases.
    const std::int64_t sun = world.sun();
    for (int i = 0; i < 900; ++i) world.step();
    check(world.suns().empty(), "a vasebreaker board must not drop sky sun");
    check(world.sun() == sun, "nothing but a vase may change the sun on a vasebreaker board");
}

void testClearingEveryVaseWins(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("egypt_57"), 8);
    requireVaseWorld(world, "egypt_57");
    std::vector<std::pair<int, int>> cells;
    cells.reserve(world.vases().size());
    for (const auto& vase : world.vases()) cells.emplace_back(vase.row, vase.col);
    for (const auto& [row, col] : cells) {
        const auto broken = world.breakVase(row, col);
        check(broken.ok, "every vase on the board must be breakable");
    }
    check(world.status() == "playing", "the run may only end on a tick, not on the last tap");
    const std::uint64_t cap = world.tick() + 600;
    while (world.status() == "playing" && world.tick() < cap) world.step();
    check(world.status() == "won", "clearing every vase with no zombies left must win, got: " +
                                       world.status());
    check(countEvents(world, "level_won") == 1, "the win must be logged once");
}

void testOrdinaryLevelIsUntouched(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("frontyard_1"), 5);
    check(!world.vasebreaker(), "frontyard_1 must not be a vasebreaker level");
    check(world.vases().empty(), "an ordinary level must have no vases");
    check(world.vaseTally().total == 0, "an ordinary level must report no vases");
    check(world.snapshot().vases.empty(), "an ordinary snapshot must carry no vases");
    check(world.plant("sunflower", 2, 0).empty(), "an ordinary level must keep its seed bank");
}

void testSwitchingTheModeOffKeepsTheSeedBank(const Catalog& catalog) {
    WorldOptions options;
    options.vasebreaker = false;
    World world(catalog, catalog.levels.at("beach_69"), 6, options);
    check(!world.vasebreaker(), "the option must switch the mode off");
    check(world.vases().empty(), "the option must leave the lawn without vases");
    check(countEvents(world, "vase_field_laid") == 0, "the option must not lay a vase field");
    check(world.plant("sunflower", 0, 0).empty(),
          "with the mode off a vasebreaker level must play as an ordinary level");
}

void run(const fs::path& content, const fs::path& pack, const fs::path& temp) {
    pvz::CatalogOptions options;
    options.contentPack = pack;
    const Catalog catalog = pvz::loadCatalog(content, options);
    check(!catalog.levels.empty(), "the content must carry levels for the vase tests");
    std::error_code ignored;
    fs::create_directories(temp, ignored);
    testTableShape();
    testVasesCoverTheBoard(catalog);
    testVaseLayoutFollowsTheSeed(catalog);
    testBreakVaseIsIdempotent(catalog);
    testZombieVaseSpawnsInItsRow(catalog);
    testPlantVaseCardPlantsNextToItsVase(catalog);
    testSunVasePaysSun(catalog, temp);
    testVaseLevelHasNoSeedBank(catalog);
    testClearingEveryVaseWins(catalog);
    testOrdinaryLevelIsUntouched(catalog);
    testSwitchingTheModeOffKeepsTheSeedBank(catalog);
}

} // namespace

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    if (argc < 4) {
        std::cerr << "usage: vase_test <content> <pack> <temp>\n";
        return 2;
    }
    try {
        run(fs::path{argv[1]}, fs::path{argv[2]}, fs::path{argv[3]});
    } catch (const std::exception& error) {
        std::cerr << "vase test failed: " << error.what() << '\n';
        return 1;
    }
    std::cout << "vase tests passed\n";
    return 0;
}
