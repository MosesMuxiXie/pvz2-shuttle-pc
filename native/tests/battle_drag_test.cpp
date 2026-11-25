// T50 drag-to-plant. `battle_view` owns the SDL plumbing (motion events, preview border, the
// button-up that ends the drag), but everything that can be wrong lives in `ui::DragController`:
// which cell the pointer is on, whether a drop is legal, and how many plants one drag may place.
// Keeping that unit free of SDL is what lets this file drive it with plain numbers against a real
// `engine::World` — no window, no assets, so it runs in the audit configuration.
//
// The four behaviours the contract asks for, one case each:
//   1. a legal drag plants and charges sun            (testLegalDragPlants)
//   2. an illegal drop charges nothing                (testOccupied/OffBoard/NoSun)
//   3. one drag plants at most one plant              (testOneDragPlantsOnePlant)
//   4. dragging with no card armed does nothing       (testNoCardDragsNothing)
#include "drag_plant.hpp"
#include "engine/world.hpp"

#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

namespace fs = std::filesystem;
using pvz::Catalog;
using pvz::Json;
using pvz::engine::World;
using pvz::ui::DragCell;
using pvz::ui::DragController;
using pvz::ui::DragGeometry;
using pvz::ui::DragVerdict;

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

/// The cell centre in the numbers `battle_view` draws with, so the test walks the same geometry
/// the player's pointer does.
DragCell centreOf(const DragGeometry& geometry, int row, int col) {
    return geometry.cellAt(geometry.boardX + (static_cast<float>(col) + 0.5f) * geometry.cellW,
                           geometry.boardY + (static_cast<float>(row) + 0.5f) * geometry.cellH);
}

/// The most expensive plant in the content: its cost is far above the starting sun, which is what
/// makes the "not enough sun" branch reachable without touching the economy.
std::string priciest(const Catalog& catalog) {
    std::string id;
    double best = -1;
    for (const auto& entry : catalog.plants)
        if (entry.second.cost > best) {
            best = entry.second.cost;
            id = entry.first;
        }
    return id;
}

// 1. A legal drag plants on release and costs exactly the card's price. Moving the pointer over the
// board must not plant anything: that is the difference between dragging and continuous planting.
void testLegalDragPlants(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("frontyard_1"), 41);
    const std::string card = "sunflower";
    const double cost = catalog.plants.at(card).cost;
    const double sunBefore = world.sun();
    check(sunBefore >= cost, "frontyard_1 must start with enough sun for a sunflower, sun=" +
                                 std::to_string(sunBefore));

    DragController drag;
    const DragGeometry geometry;
    drag.begin(0);
    check(drag.active(), "a press on a card must arm the drag");

    const DragCell cell = centreOf(geometry, 1, 2);
    check(cell.row == 1 && cell.col == 2,
          "the pointer must map to its cell, got " + std::to_string(cell.row) + "/" +
              std::to_string(cell.col));
    drag.moved(cell, pvz::ui::dragRulesFor(world, catalog, card, cell));
    check(drag.state().verdict == DragVerdict::legal,
          "a free, affordable cell must preview as legal, got " +
              std::string(pvz::ui::dragVerdictName(drag.state().verdict)));
    check(world.plants().empty(), "dragging over the lawn must not plant on its own");

    const int planted = drag.release(cell, pvz::ui::dragRulesFor(world, catalog, card, cell));
    check(planted == 0, "a legal release must report deck card 0, got " + std::to_string(planted));
    check(!drag.active(), "the release must end the drag");

    const std::string reason = world.plant(card, cell.row, cell.col);
    check(reason.empty(), "the world must accept the released cell: " + reason);
    check(world.plantAt(cell.row, cell.col) != nullptr, "the plant must end up in that cell");
    check(world.sun() == sunBefore - cost,
          "the drop must charge the card's price, sun=" + std::to_string(world.sun()));
    check(countEvents(world, "planted") == 1, "exactly one `planted` event");
}

// 2a. An occupied cell refuses the drop: no sun spent, no second `planted` event.
void testOccupiedCellRefuses(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("frontyard_1"), 42);
    check(world.plant("sunflower", 1, 2).empty(), "the fixture must fill the cell first");
    const double sunBefore = world.sun();
    const std::size_t plantedBefore = countEvents(world, "planted");

    DragController drag;
    drag.begin(0);
    const DragCell cell{1, 2};
    const pvz::ui::DragRules rules = pvz::ui::dragRulesFor(world, catalog, "sunflower", cell);
    check(rules.occupied, "the rules must see the plant already in the cell");
    drag.moved(cell, rules);
    check(drag.state().verdict == DragVerdict::occupied,
          "an occupied cell must preview as red, got " +
              std::string(pvz::ui::dragVerdictName(drag.state().verdict)));
    check(drag.release(cell, rules) == -1, "an occupied cell must not plant");
    check(!drag.active(), "a refused release still ends the drag");
    check(world.sun() == sunBefore, "a refused drop must not spend sun");
    check(countEvents(world, "planted") == plantedBefore, "a refused drop must not plant");
    check(!pvz::ui::dragVerdictText(DragVerdict::occupied).empty(),
          "the HUD must have something to say about a refused drop");
}

// 2b. Off the lawn: no cell, no plant, no charge.
void testOffBoardRefuses(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("frontyard_1"), 43);
    const double sunBefore = world.sun();
    const DragGeometry geometry;
    DragController drag;
    drag.begin(0);
    const DragCell cell = geometry.cellAt(10.0f, 10.0f); // over the seed bank, not the lawn
    check(!cell.inside(), "a pointer above the board must not map to a cell");
    check(!geometry.onBoard(10.0f, 10.0f), "the seed bank is not the lawn");
    const pvz::ui::DragRules rules = pvz::ui::dragRulesFor(world, catalog, "sunflower", cell);
    drag.moved(cell, rules);
    check(drag.state().verdict == DragVerdict::offBoard,
          "off the lawn the preview must vanish, got " +
              std::string(pvz::ui::dragVerdictName(drag.state().verdict)));
    check(drag.release(cell, rules) == -1, "a drop outside the lawn must not plant");
    check(world.plants().empty(), "nothing may be planted outside the lawn");
    check(world.sun() == sunBefore, "a drop outside the lawn must not spend sun");
    check(!pvz::ui::dragVerdictText(DragVerdict::offBoard).empty(),
          "the HUD must explain a drop outside the lawn");
}

// 2c. Not enough sun: the preview is grey and the release is refused.
void testNoSunRefuses(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("frontyard_1"), 44);
    const std::string card = priciest(catalog);
    check(catalog.plants.at(card).cost > world.sun(),
          "the fixture needs a card the player cannot afford, cost=" +
              std::to_string(catalog.plants.at(card).cost) + " sun=" + std::to_string(world.sun()));
    const double sunBefore = world.sun();
    DragController drag;
    drag.begin(0);
    const DragCell cell = centreOf(DragGeometry{}, 3, 4);
    const pvz::ui::DragRules rules = pvz::ui::dragRulesFor(world, catalog, card, cell);
    check(!rules.affordable, "the rules must report the card as unaffordable");
    drag.moved(cell, rules);
    check(drag.state().verdict == DragVerdict::noSun,
          "an unaffordable card must preview as grey, got " +
              std::string(pvz::ui::dragVerdictName(drag.state().verdict)));
    check(drag.release(cell, rules) == -1, "an unaffordable drop must not plant");
    check(world.plants().empty(), "an unaffordable drop must not plant anything");
    check(world.sun() == sunBefore, "an unaffordable drop must not spend sun");
}

// 3. One drag, one plant. The pointer sweeps across three free cells and only the release plants;
// once that has happened the drag is over, so a repeated button-up (or a caller that plants on every
// release it is handed) cannot fill the row.
void testOneDragPlantsOnePlant(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("frontyard_1"), 45);
    const std::string card = "sunflower";
    const double cost = catalog.plants.at(card).cost;
    const double sunBefore = world.sun();
    const DragGeometry geometry;
    DragController drag;
    drag.begin(0);

    const DragCell path[] = {centreOf(geometry, 2, 3), centreOf(geometry, 3, 4),
                             centreOf(geometry, 4, 5)};
    for (const DragCell& cell : path)
        drag.moved(cell, pvz::ui::dragRulesFor(world, catalog, card, cell));
    check(world.plants().empty(), "sweeping the pointer across cells must not plant a thing");

    const DragCell last = path[2];
    check(drag.release(last, pvz::ui::dragRulesFor(world, catalog, card, last)) == 0,
          "the first legal release must plant");
    check(world.plant(card, last.row, last.col).empty(), "the released cell must accept the plant");

    // Same press, second release: the drag is over, so this is the guard against continuous
    // planting (a controller that stays armed would hand the card back here).
    for (const DragCell& cell : path) {
        const int again = drag.release(cell, pvz::ui::dragRulesFor(world, catalog, card, cell));
        check(again == -1,
              "a second release in the same drag must not plant again (cell " +
                  std::to_string(cell.row) + "/" + std::to_string(cell.col) + ")");
    }
    check(world.plants().size() == 1,
          "one drag must leave exactly one plant, got " + std::to_string(world.plants().size()));
    check(world.sun() == sunBefore - cost,
          "one drag must charge one card, sun=" + std::to_string(world.sun()));
}

// 4. No card armed (the player released the card before pressing, or pressed the lawn directly):
// motion and release are inert.
void testNoCardDragsNothing(const Catalog& catalog) {
    World world(catalog, catalog.levels.at("frontyard_1"), 46);
    const double sunBefore = world.sun();
    DragController drag;
    check(!drag.active(), "a fresh controller must be idle");
    const DragCell cell = centreOf(DragGeometry{}, 2, 2);
    drag.moved(cell, pvz::ui::dragRulesFor(world, catalog, "sunflower", cell));
    check(drag.state().verdict == DragVerdict::none,
          "without a card there is no preview, got " +
              std::string(pvz::ui::dragVerdictName(drag.state().verdict)));
    check(drag.release(cell, pvz::ui::dragRulesFor(world, catalog, "sunflower", cell)) == -1,
          "a release without a card must not plant");
    check(world.plants().empty(), "a release without a card must not plant anything");
    check(world.sun() == sunBefore, "a release without a card must not spend sun");

    // A card index outside the deck cannot arm a drag either.
    drag.begin(-1);
    check(!drag.active(), "an out-of-range card must not arm the drag");
}

void run(const fs::path& content, const fs::path& pack) {
    pvz::CatalogOptions options;
    options.contentPack = pack;
    const Catalog catalog = pvz::loadCatalog(content, options);
    check(!catalog.levels.empty(), "the content must carry levels for the drag tests");
    testLegalDragPlants(catalog);
    testOccupiedCellRefuses(catalog);
    testOffBoardRefuses(catalog);
    testNoSunRefuses(catalog);
    testOneDragPlantsOnePlant(catalog);
    testNoCardDragsNothing(catalog);
}

} // namespace

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    if (argc < 4) {
        std::cerr << "usage: battle_drag_test <content> <pack> <temp>\n";
        return 2;
    }
    try {
        run(fs::path{argv[1]}, fs::path{argv[2]});
    } catch (const std::exception& error) {
        std::cerr << "battle drag test failed: " << error.what() << '\n';
        return 1;
    }
    std::cout << "battle drag tests passed\n";
    return 0;
}
