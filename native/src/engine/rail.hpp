#pragma once
// A2 (S3): the minecart track. The original keeps the plan in two property sheets -
// `RailcartProperties` (one row per cart, with Column/Row) and `DangerRoomRailcartDesigner`
// (`BaseRailcartCount`, plus a `Layouts` shape this build deliberately does not model).
//
// `content/levels/<id>.json` already carries the derived, client-visible half of that:
// `extra.rail: true` on the 192 levels `rails_report.json` calls functional, and
// `extra.minecarts` as the LIST OF ROWS a cart stands on (190 of the 192 - `cowboy_41` and
// `cowboy_42` declare rail with no cart at all). The rail COLUMN is not in the client data: every
// cart starts at column 0 and drives right, which is why the movement is a kernel fallback rather
// than a pack value. See docs/reviews/2026-11-26-rail-gameplay.md.
#include <cstddef>
#include <filesystem>
#include <map>
#include <string>
#include <vector>

namespace pvz::engine {

/// One level's cart plan: the rows the level puts a cart on, in declaration order.
struct RailRow {
    std::string level;
    std::vector<int> rows;
};

/// The generated half of the plan, read from `native/generated/level_mechanics.json`.
///
/// **Today this table is empty of rail data.** No `levels.<id>` row carries `rail`, `railcarts` or
/// `minecarts` (the mechanics compiler never emitted them), so `find()` answers null for all 1809
/// levels and `World` builds the carts from `LevelDefinition::extra` instead. The loader exists
/// anyway: a rail level must fail with a named error rather than silently start with an empty
/// track, and the day the mechanics compiler starts emitting the rows this file needs no change.
class RailTable {
  public:
    static constexpr const char* kFileName = "level_mechanics.json";

    /// Process-wide table, parsed once. Throws `rail table: <path>: <reason>` when the generated
    /// directory cannot be resolved or the JSON is unusable.
    static const RailTable& shared();
    static RailTable load(const std::filesystem::path& path);

    /// The level's generated row, or null when the table has nothing for it (all 1809 today).
    const RailRow* find(const std::string& level) const;
    /// How many levels the generated table describes. Zero with the shipped table.
    std::size_t size() const { return rows_.size(); }

  private:
    std::map<std::string, RailRow> rows_;
};

} // namespace pvz::engine
