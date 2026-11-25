#pragma once
#include <string>

namespace pvz {
// `struct`, not `class`: catalog.hpp declares `struct Catalog`, and MSVC mangles the two
// differently. A `class` forward declaration here turned `dragRulesFor` into a second, unresolved
// symbol the moment a translation unit included catalog.hpp first (the desktop link caught it as
// LNK2019 while the audit test linked only against itself).
struct Catalog;
namespace engine {
class World;
} // namespace engine

/// Drag-to-plant: the state machine behind "hold the left button on a seed card, drag onto the
/// lawn, release to plant". It is deliberately free of SDL so `battle_drag_test` can drive it
/// with plain numbers against a real `engine::World`; `battle_view` feeds it pointer positions
/// from `SDL_EVENT_MOUSE_MOTION` / `SDL_EVENT_MOUSE_BUTTON_UP` and draws the preview border.
namespace ui {

/// Where the pointer is on the board, in cells. `row`/`col` stay `-1` when the pointer is off the
/// lawn (over the seed bank, above the board, past the right edge), so `inside()` is the one test
/// the callers need.
struct DragCell {
    int row = -1;
    int col = -1;
    bool inside() const { return row >= 0 && col >= 0; }
};

/// The three colours the preview can take, plus "no preview" and "nothing to say".
enum class DragVerdict {
    none,     ///< no drag in progress
    legal,    ///< release here plants
    occupied, ///< a plant already lives in this cell (red)
    noSun,    ///< the player cannot afford the card (grey)
    cooling,  ///< the card is still recharging (red)
    offBoard, ///< the pointer is not over the lawn (no preview)
};
const char* dragVerdictName(DragVerdict verdict);
/// What the HUD says after a refused release. Empty for `none`/`legal`.
std::string dragVerdictText(DragVerdict verdict);

/// The gates `engine::World::plant` applies, asked before the release so the preview can be drawn
/// without planting anything. `engine::World::plant` remains the authority: a `legal` preview that
/// the world still refuses reports the world's own reason.
struct DragRules {
    bool occupied = false;
    bool ready = true;
    bool affordable = true;
};
DragRules dragRulesFor(engine::World& world, const Catalog& catalog, const std::string& cardId,
                       const DragCell& cell);

DragVerdict dragVerdictOf(const DragCell& cell, const DragRules& rules);

/// The board rectangle in logical (1280x720) coordinates, the same numbers `battle_view` draws
/// with. `cellAt` never returns an out-of-range cell: the caller gets `inside() == false` instead.
struct DragGeometry {
    float boardX = 190, boardY = 120, cellW = 100, cellH = 100;
    int cols = 9, rows = 6;
    DragCell cellAt(float x, float y) const;
    /// True when the pointer is anywhere over the lawn rectangle, even in the far margin where
    /// `cellAt` clamps away: a release there is a failed drop, not a cancelled one.
    bool onBoard(float x, float y) const;
};

struct DragState {
    bool active = false;
    int card = -1;
    DragCell cell;
    DragVerdict verdict = DragVerdict::none;
    /// One drag plants at most one plant (no continuous planting: the pack has no "drag a row"
    /// flag on any of its 147 plants, see the review note). Everything after the first plant in
    /// the same drag is ignored until the next `begin`.
    bool planted = false;
};

class DragController {
  public:
    /// Left button went down on deck card `card`. Any previous drag is dropped.
    void begin(int card);
    /// Pointer moved while the button is held: update the preview.
    void moved(const DragCell& cell, const DragRules& rules);
    /// Left button released. Returns the deck card to plant, or -1 when nothing should be
    /// planted (refused cell, no drag, or the one plant this drag already placed).
    int release(const DragCell& cell, const DragRules& rules);
    void cancel();
    bool active() const { return state_.active; }
    const DragState& state() const { return state_; }

  private:
    DragState state_;
};

} // namespace ui
} // namespace pvz
