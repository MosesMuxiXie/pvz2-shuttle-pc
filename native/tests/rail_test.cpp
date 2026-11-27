// S3/A2: the minecart track.
//
// The client data says which *rows* carry a cart (`extra.minecarts` is a list of row numbers) and
// nothing else: no starting column, no track length, no speed. So this test pins the parts that are
// real data (which levels have a track, which rows, how many carts) and the parts that are kernel
// fallbacks (`tuning.hpp`'s `kRailSpeedColumnsPerSecond` and friends), separately - a fallback that
// silently becomes data is exactly the kind of drift these tests exist to catch.
#include "catalog.hpp"
#include "content/model.hpp"
#include "engine/rail.hpp"
#include "engine/tuning.hpp"
#include "engine/world.hpp"
#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <set>
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

const LevelDefinition& levelOf(const Catalog& catalog, const std::string& id) {
    const auto it = catalog.levels.find(id);
    check(it != catalog.levels.end(), "the catalog has no level " + id);
    return it->second;
}

/// The rows `content/levels` declares for a level, in declaration order.
std::vector<int> declaredRows(const LevelDefinition& level) {
    std::vector<int> rows;
    if (!level.extra.is_object()) return rows;
    const auto carts = level.extra.find("minecarts");
    if (carts == level.extra.end() || !carts->is_array()) return rows;
    for (const Json& entry : *carts) {
        if (entry.is_number_integer()) rows.push_back(entry.get<int>());
    }
    return rows;
}

bool declaresRail(const LevelDefinition& level) {
    if (!level.extra.is_object()) return false;
    const auto rail = level.extra.find("rail");
    return rail != level.extra.end() && rail->is_boolean() && rail->get<bool>();
}

/// A copy of `base` with a deck and a sun balance, so a cart test never depends on a shipped level's
/// economy.
LevelDefinition forPlanting(const LevelDefinition& base) {
    LevelDefinition level = base;
    level.sun = 5000;
    level.deck = {"peashooter"};
    return level;
}

std::vector<const Json*> eventsOfType(const World& world, const std::string& type) {
    std::vector<const Json*> hits;
    for (const Json& event : world.events()) {
        if (event.value("type", std::string()) == type) hits.push_back(&event);
    }
    return hits;
}

// 1. The generated table loads, and today it carries no rail row at all. That is the whole reason
//    `World` falls back to `extra`: a table that silently gained rows would change which levels get
//    carts without anyone touching content.
void testRailTable(const fs::path& temp) {
    const RailTable& table = RailTable::shared();
    check(table.size() == 0, "the shipped level_mechanics.json declares no rail row, got " +
                                 std::to_string(table.size()));
    check(table.find("cowboy_1") == nullptr, "a level with no table row must find nothing");

    // The failure path has to name the table, otherwise a broken install reads as "no rail levels".
    bool threw = false;
    std::string what;
    try {
        const RailTable broken = RailTable::load(temp / "definitely-missing-level_mechanics.json");
        (void)broken;
    } catch (const std::exception& error) {
        threw = true;
        what = error.what();
    }
    check(threw, "a missing rail table must throw");
    check(what.rfind("rail table:", 0) == 0, "the error must be prefixed `rail table:`, got " + what);
}

// 2. Cart counts and rows come straight from `extra.minecarts`.
void testCartCounts(const Catalog& catalog) {
    {
        const LevelDefinition& level = levelOf(catalog, "cowboy_1");
        check(declaresRail(level), "cowboy_1 must declare a track");
        World world(catalog, level, 1);
        check(world.railLevel(), "cowboy_1 must report itself as a rail level");
        check(world.railCarts().size() == 1, "cowboy_1 carries one cart, got " +
                                                 std::to_string(world.railCarts().size()));
        check(world.railCarts()[0].row == 2, "cowboy_1's cart sits on row 2");
        check(world.railCarts()[0].col == 0, "every cart starts on the left edge");
        check(!world.railCarts()[0].derailed, "a cart starts on its rails");
    }
    {
        const LevelDefinition& level = levelOf(catalog, "cowboy_10");
        const std::vector<int> rows = declaredRows(level);
        check(rows.size() == 5, "cowboy_10 declares five rows, got " + std::to_string(rows.size()));
        World world(catalog, level, 1);
        check(world.railCarts().size() == rows.size(),
              "cowboy_10 must lay one cart per declared row");
        for (std::size_t i = 0; i < rows.size(); ++i) {
            check(world.railCarts()[i].row == rows[i],
                  "cart " + std::to_string(i) + " must sit on its declared row");
        }
    }
    // A level may declare a track and carry no cart: these two do, and they still report `rail`.
    for (const char* id : {"cowboy_41", "cowboy_42"}) {
        const LevelDefinition& level = levelOf(catalog, id);
        check(declaresRail(level), std::string(id) + " must declare a track");
        check(declaredRows(level).empty(), std::string(id) + " declares no cart");
        World world(catalog, level, 1);
        check(world.railLevel(), std::string(id) + " must still be a rail level");
        check(world.railCarts().empty(), std::string(id) + " must lay no cart");
    }
    // A level without the flag never touches the table, which is what keeps it byte-identical.
    {
        World world(catalog, levelOf(catalog, "frontyard_1"), 1);
        check(!world.railLevel(), "frontyard_1 is not a rail level");
        check(world.railCarts().empty(), "frontyard_1 carries no cart");
    }
}

// 3. A cart holds one plant, refuses a second, and carries the first along as it moves.
void testPlantOnCart(const Catalog& catalog) {
    const LevelDefinition level = forPlanting(levelOf(catalog, "cowboy_1"));
    World world(catalog, level, 1);
    check(world.railCarts().size() == 1, "the planting fixture needs one cart");
    const int row = world.railCarts()[0].row;
    const int col = world.railCarts()[0].col;

    const std::string reason = world.plantOnCart("peashooter", row, col);
    check(reason.empty(), "planting on a cart must succeed, got " + reason);
    check(world.railCarts()[0].plant != 0, "the cart must link the plant it carries");
    const EntityId riding = world.railCarts()[0].plant;

    // The plain path must refuse the cell: the cart is already standing on it.
    check(world.plant("peashooter", row, col) == "cell occupied",
          "plant() must refuse the cell a cart stands on");
    check(world.plantOnCart("peashooter", row, col) == "cart occupied",
          "a cart takes exactly one plant");
    check(world.plantOnCart("peashooter", (row + 1) % world.rows(), col) == "no cart",
          "planting off the cart must say `no cart`");

    // Every column the cart enters carries the plant with it.
    world.advance(3.0);
    check(world.railCarts()[0].col > col, "the cart must have moved, still at column " +
                                             std::to_string(world.railCarts()[0].col));
    const PlantEntity* plant = world.plantById(riding);
    check(plant != nullptr, "the riding plant must still exist");
    check(plant->col == world.railCarts()[0].col, "the plant must stay on the cart");
    check(plant->row == row, "the plant must stay on the cart's row");
}

// 4. `rail_move` fires once per column entered, not once per tick.
void testRailMoveEventsOncePerColumn(const Catalog& catalog) {
    World world(catalog, levelOf(catalog, "cowboy_1"), 1);
    check(world.railCarts().size() == 1, "the event fixture needs one cart");
    const EntityId cart = world.railCarts()[0].id;
    for (int step = 0; step < 16; ++step) world.advance(0.25);
    const int column = world.railCarts()[0].col;
    check(column >= 1, "half a column per second over four seconds must move the cart, got " +
                           std::to_string(column));

    std::vector<int> entered;
    for (const Json* event : eventsOfType(world, "rail_move")) {
        const Json& details = event->at("details");
        if (details.value("cart", EntityId{0}) != cart) continue;
        check(details.value("row", -1) == world.railCarts()[0].row, "rail_move must name the cart's row");
        entered.push_back(details.value("col", -1));
    }
    check(static_cast<int>(entered.size()) == column,
          "one rail_move per column entered, got " + std::to_string(entered.size()) + " for column " +
              std::to_string(column));
    check(world.railMovedColumns() == entered.size(), "the counter must match the event stream");
    for (std::size_t i = 0; i < entered.size(); ++i) {
        check(entered[i] == static_cast<int>(i) + 1, "columns must be entered in order, 1,2,3...");
    }
    const std::set<int> unique(entered.begin(), entered.end());
    check(unique.size() == entered.size(), "a column must never be reported twice");
}

// 5. A cart crushes what stands in its cell - once, through the ordinary damage channel.
void testCartCrushesZombie(const Catalog& catalog) {
    World world(catalog, levelOf(catalog, "cowboy_1"), 1);
    const int row = world.railCarts()[0].row;
    check(world.spawnZombieAt("basic", row, 3.0), "a basic zombie must spawn three columns out");
    const EntityId zombie = world.zombies().back().id;
    const double before = world.zombies().back().hp;

    std::size_t hits = 0;
    for (int step = 0; step < 24 && hits == 0; ++step) {
        world.advance(0.5);
        hits = eventsOfType(world, "rail_hit").size();
    }
    check(hits > 0, "the cart must run into the zombie and report rail_hit");
    std::size_t forThisZombie = 0;
    for (const Json* event : eventsOfType(world, "rail_hit")) {
        const Json& details = event->at("details");
        if (details.value("zombie", EntityId{0}) != zombie) continue;
        ++forThisZombie;
        check(details.value("damage", 0.0) == tuning::kRailCrushDamage,
              "rail_hit must carry the tuning damage");
    }
    check(forThisZombie == 1, "one crushing pass must report the zombie once, got " +
                                  std::to_string(forThisZombie));
    check(world.railHits() >= 1, "the hit counter must move with the event");
    const ZombieEntity* after = world.zombieById(zombie);
    check(after == nullptr || !after->alive || after->hp < before,
          "the crushed zombie must lose hit points through damageZombie()");
}

// 6. The switch: off means no cart, no event, and `railLevel()` stays false.
void testRailOffSwitch(const Catalog& catalog) {
    WorldOptions options;
    options.rail = false;
    World world(catalog, levelOf(catalog, "cowboy_1"), 1, options);
    check(!world.railLevel(), "with rail off a rail level must not report a track");
    check(world.railCarts().empty(), "with rail off no cart may be laid");
    world.advance(4.0);
    check(eventsOfType(world, "rail_move").empty(), "with rail off no rail_move may fire");
    check(eventsOfType(world, "rail_carts").empty(), "with rail off no rail_carts may fire");
}

// 7. Every level that declares a track can be built and played, and the 12 levels the rails report
//    calls decorative/unknown are not among them.
void testEveryRailLevelInitializes(const Catalog& catalog) {
    std::vector<std::string> railLevels;
    for (const auto& [id, level] : catalog.levels) {
        if (declaresRail(level)) railLevels.push_back(id);
    }
    check(railLevels.size() == 192,
          "content marks 192 rail levels, got " + std::to_string(railLevels.size()));
    // The twelve that carry rail *objects* in the pack but no client flag: six decorative
    // (carts=0, a Rails path only) and six unknown. They must stay out of the playable set.
    for (const char* id : {"egypt_46", "frontyard_98", "frontyard_143", "lunarrainbowmarket_93",
                           "muji_27", "pirate_67", "fairy_31", "future_66", "future_69",
                           "future_70", "iceage_65", "plantagenet_47"}) {
        const auto it = std::find(railLevels.begin(), railLevels.end(), std::string(id));
        check(it == railLevels.end(), std::string(id) + " must not be a playable rail level");
    }
    std::size_t withCarts = 0;
    for (const std::string& id : railLevels) {
        const LevelDefinition& level = levelOf(catalog, id);
        World world(catalog, level, 1);
        check(world.railLevel(), id + " must report a track");
        const std::size_t expected = declaredRows(level).size();
        check(world.railCarts().size() == expected, id + " must lay one cart per declared row");
        if (expected > 0) ++withCarts;
        world.advance(5.0);
    }
    check(withCarts == 190, "190 of the 192 declare at least one row, got " + std::to_string(withCarts));
}

void run(const fs::path& content, const fs::path& pack, const fs::path& temp) {
    const Catalog catalog = load(content, pack);
    testRailTable(temp);
    testCartCounts(catalog);
    testPlantOnCart(catalog);
    testRailMoveEventsOncePerColumn(catalog);
    testCartCrushesZombie(catalog);
    testRailOffSwitch(catalog);
    testEveryRailLevelInitializes(catalog);
}
}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc < 4) {
        std::wcerr << L"usage: rail_test <content> <pack> <temp>\n";
        return 2;
    }
    try {
        run(fs::path(argv[1]), fs::path(argv[2]), fs::path(argv[3]));
    } catch (const std::exception& error) {
        std::cerr << "rail test failed: " << error.what() << '\n';
        return 1;
    }
    std::cout << "rail tests passed\n";
    return 0;
}
