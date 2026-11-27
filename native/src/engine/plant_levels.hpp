#pragma once
// B1 (T90): `generated/plant_levels.json` - the original's per-level stat ladder.
//
// `PlantLevelStats` ships one row per plant type. Each row's `FloatStats[]` entry carries
// `Values[]`, and `Values[i]` IS the number at level i+1. That is not a growth curve: it is an
// absolute value, so a peashooter at level 2 costs 75 sun because the sheet says 75, not because
// anything was scaled. Applying a percentage here would be inventing data, which is why the
// compiler (`tools/contentc/plant_levels.py`) hands the ladder over verbatim and this file does the
// same.
//
// The sheet splits one stat into columns with a `@<SubType>` suffix when the same `Name` appears
// more than once (`ActionDamageNormal@0` and `@2` on the peashooter, i.e. one column per attack
// variant). Only the column this build can identify is used: `PlantLevelRow::damageStat`.
//
// The single rule the whole file is built around: **a column is only applied when its LEVEL-1 value
// reproduces the number the engine already has.** `tools/obb_build_content.py`'s
// `refresh_plant_stats()` flattens the same sheet with "last entry wins", so today's pack numbers
// ARE the level-1 numbers. The guard turns that into a checked assumption instead of a hope: a plant
// whose column means something else keeps its pack value rather than being quietly rebalanced, and a
// default run (every plant at level 1) cannot move at all.
//
// Data gaps this file deliberately does not paper over: no plant carries a sun-production column
// (`sunflower`'s ladder is Cost/Hitpoints/PacketCooldown/PlantTier only), so a producer's output is
// not level-dependent in this build. See docs/reviews/2026-11-26-plant-levels-wired.md.
#include <cstddef>
#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace pvz::engine {

/// One plant's ladder: `levels[i]` holds level i+1, already flattened to `stat name -> value`.
struct PlantLevelRow {
    std::string type;
    /// How many levels the sheet gives this plant. 1 means "no ladder", which is 190 of the 323
    /// rows - and every plant the sheet does not mention at all.
    int levelCount = 1;
    std::vector<std::map<std::string, double>> levels;
    /// The `ActionDamageNormal` column this row carries: the bare name when the sheet has one
    /// column, otherwise the `@SubType` column with the greatest suffix (the one the pack's
    /// "last entry wins" flatten picks). Empty when the row has no damage stat at all.
    std::string damageStat;

    /// `level` clamped into `1..levelCount`.
    int clamp(int level) const;
    /// The stats at `level` (clamped), or null when the row has no ladder.
    const std::map<std::string, double>* at(int level) const;
    /// One stat at `level` (clamped), or null when the row does not carry it.
    std::optional<double> value(const std::string& stat, int level) const;
};

/// The generated ladder table, read from `generated/plant_levels.json`.
///
/// Unlike the vase/rail tables this one is consulted by **every** plant construction, so `shared()`
/// must not throw on a tree that simply has no generated directory (a unit test with a hand-built
/// catalog). It answers an empty table there and `loaded()` says why. A file that exists but is
/// unreadable or malformed is still a named throw: a half-loaded ladder would change combat numbers
/// silently.
class PlantLevelTable {
  public:
    static constexpr const char* kFileName = "plant_levels.json";

    /// Process-wide table, parsed once from `generatedDir()`.
    static const PlantLevelTable& shared();
    /// Parse one file. Throws `plant level table: <path>: <reason>` on a broken table.
    static PlantLevelTable load(const std::filesystem::path& path);

    bool loaded() const { return loaded_; }
    std::size_t size() const { return rows_.size(); }
    /// The plant's ladder, or null when the sheet has no row for it.
    const PlantLevelRow* find(const std::string& type) const;
    /// Every plant type the table carries, sorted - the report and the tests walk this.
    std::vector<std::string> types() const;

  private:
    std::unordered_map<std::string, PlantLevelRow> rows_;
    bool loaded_ = false;
};

/// `type`'s level clamped into the table's own `1..levelCount`. 1 when the plant has no row, i.e.
/// a save asking for a plant this build does not know cannot raise it above the default.
int clampPlantLevel(const std::string& type, int level);

/// The ladder value at `level`, but only when `type` carries `stat` AND its level-1 value equals
/// `current`. Nullopt otherwise, and the caller keeps its own number - see the header comment for
/// why the identity check is the contract rather than a nicety.
std::optional<double> leveledValue(const std::string& type, const std::string& stat, int level,
                                   double current);

} // namespace pvz::engine
