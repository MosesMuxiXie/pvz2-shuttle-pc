#include "drag_plant.hpp"

#include "catalog.hpp"
#include "engine/world.hpp"

#include <cmath>
#include <utility>

namespace pvz::ui {

const char* dragVerdictName(DragVerdict verdict) {
    switch (verdict) {
    case DragVerdict::legal:
        return "legal";
    case DragVerdict::occupied:
        return "occupied";
    case DragVerdict::noSun:
        return "noSun";
    case DragVerdict::cooling:
        return "cooling";
    case DragVerdict::offBoard:
        return "offBoard";
    case DragVerdict::none:
        break;
    }
    return "none";
}

std::string dragVerdictText(DragVerdict verdict) {
    switch (verdict) {
    case DragVerdict::occupied:
        return "这一格已经有植物了。";
    case DragVerdict::noSun:
        return "阳光不够，先别种。";
    case DragVerdict::cooling:
        return "这张卡还在冷却。";
    case DragVerdict::offBoard:
        return "拖到草坪上再松手才能种。";
    case DragVerdict::legal:
        return "松手种植。";
    case DragVerdict::none:
        break;
    }
    return {};
}

DragRules dragRulesFor(engine::World& world, const Catalog& catalog, const std::string& cardId,
                       const DragCell& cell) {
    DragRules rules;
    // A card the catalog does not know cannot be planted at all; report it as unaffordable so the
    // preview turns grey instead of promising a plant the world will refuse.
    const auto definition = catalog.plants.find(cardId);
    if (definition == catalog.plants.end()) {
        rules.affordable = false;
        return rules;
    }
    if (cell.inside()) rules.occupied = world.plantAt(cell.row, cell.col) != nullptr;
    rules.ready = world.cooldown(cardId) <= world.tick();
    rules.affordable = world.sun() >= definition->second.cost;
    return rules;
}

DragVerdict dragVerdictOf(const DragCell& cell, const DragRules& rules) {
    // Order matters for the visible feedback: "off the lawn" explains a grey/dark miss, "occupied"
    // explains a refused drop even when the player is also short on sun.
    if (!cell.inside()) return DragVerdict::offBoard;
    if (rules.occupied) return DragVerdict::occupied;
    if (!rules.ready) return DragVerdict::cooling;
    if (!rules.affordable) return DragVerdict::noSun;
    return DragVerdict::legal;
}

DragCell DragGeometry::cellAt(float x, float y) const {
    const float local = (x - boardX) / cellW;
    const float line = (y - boardY) / cellH;
    const int col = static_cast<int>(std::floor(local));
    const int row = static_cast<int>(std::floor(line));
    if (col < 0 || col >= cols || row < 0 || row >= rows) return {};
    return DragCell{row, col};
}

bool DragGeometry::onBoard(float x, float y) const {
    return x >= boardX && y >= boardY && x < boardX + cellW * static_cast<float>(cols) &&
           y < boardY + cellH * static_cast<float>(rows);
}

void DragController::begin(int card) {
    state_ = DragState{};
    if (card < 0) return; // nothing to drag: keep the machine idle
    state_.active = true;
    state_.card = card;
}

void DragController::moved(const DragCell& cell, const DragRules& rules) {
    if (!state_.active) return;
    state_.cell = cell;
    state_.verdict = dragVerdictOf(cell, rules);
}

int DragController::release(const DragCell& cell, const DragRules& rules) {
    if (!state_.active) return -1;
    state_.cell = cell;
    state_.verdict = dragVerdictOf(cell, rules);
    state_.active = false;
    // One drag, one plant. The flag stays set until the next `begin`, so a duplicated button-up
    // (SDL delivers them on focus changes) cannot plant twice.
    if (state_.planted) return -1;
    if (state_.verdict != DragVerdict::legal) return -1;
    state_.planted = true;
    return state_.card;
}

void DragController::cancel() { state_ = DragState{}; }

} // namespace pvz::ui
