#pragma once
#include <cstddef>
#include <filesystem>
#include <string>
#include <unordered_map>
#include <vector>

namespace pvz::engine {

/// One `SpawnOffset` row from `native/generated/spawn_offsets.json`.
///
/// What this table actually is (C4 measured it; see
/// `docs/reviews/2026-11-26-spawn-offset-wired.md`): the `SpawnOffset` field of a *plant
/// action* in `pkg_2073_PlantPropertySheet.json`, flattened so the engine never parses the
/// sheet at run time. 487 rows over 224 plants, kinds `shot` 385 / `special` 77 / `sun` 18 /
/// `plantfood` 6 / `manual` 1.
///
/// It is **not** a zombie landing table: no row is keyed by a lawn row, and none of the 487
/// names a zombie. `yPx` is the vertical muzzle offset in art pixels - 116 art px make one
/// lawn row (`scale.pxPerRow`), and negative is upwards.
struct SpawnOffset {
    std::string plant;     // pack `TypeName`
    std::string kind;      // "shot" | "special" | "sun" | "plantfood" | "manual"
    int actionIndex = 0;   // index into the plant's `Actions`
    double xPx = 0;        // art pixels, +x to the right
    double yPx = 0;        // art pixels, negative is higher on screen
    /// |yPx| >= `SpawnOffsets::kSentinelPx`: a launch height further than a five-row lawn,
    /// which is a lobbed weapon (`CobCannonDefault` -600) or a screen-wide special
    /// (`DandelionDefault` -1000) rather than a muzzle. Kept, flagged, and left alone.
    bool sentinel = false;
    bool draws() const { return kind == "shot" || kind == "special"; }
};

/// The process-wide `spawn_offsets.json` table.
///
/// Same contract as `PlantFoodTable`: `shared()` parses once from `generatedDir()` and every
/// failure throws `spawn offsets: <path>: <reason>`, because a half-loaded table would
/// silently change where projectiles are drawn.
class SpawnOffsets {
  public:
    static constexpr const char* kFileName = "spawn_offsets.json";
    /// `scale.pxPerRow` from the shipped table. The fallback only matters for a fixture that
    /// leaves `scale` out; the engine must never guess a different row height silently.
    static constexpr double kFallbackPxPerRow = 116.0;
    /// `scale.pxPerColumn`, i.e. `action_runner.cpp`'s `kPixelsPerColumn`.
    static constexpr double kFallbackPxPerColumn = 100.0;
    /// A launch height of five lawn rows or more is a lob, not a muzzle. 580 = 5 * 116.
    static constexpr double kSentinelPx = 580.0;

    static SpawnOffsets load(const std::filesystem::path& file);
    static const SpawnOffsets& shared();

    bool empty() const { return rows_.empty(); }
    std::size_t size() const { return rows_.size(); }
    std::size_t negativeRows() const { return negativeRows_; }
    std::size_t positiveRows() const { return positiveRows_; }
    std::size_t sentinelRows() const { return sentinelRows_; }
    /// Median `yPx` over every row; -32 on the shipped data. Reported so a test can prove the
    /// sign convention without hardcoding a single sample.
    double medianYPx() const { return medianYPx_; }
    double pxPerRow() const { return pxPerRow_; }
    double pxPerColumn() const { return pxPerColumn_; }
    const std::vector<SpawnOffset>& rows() const { return rows_; }

    /// Exact `(plant, actionIndex)` lookup; nullptr when the sheet declares no offset there.
    const SpawnOffset* find(const std::string& plant, int actionIndex) const;

    /// The table's own spelling of the plant whose offsets govern `plant`, or "" when nothing
    /// matches.
    ///
    /// The shipped table is keyed by the property sheet's `TypeName` (`PeashooterDefault`,
    /// `CobCannonDefault`), while the engine carries the content id (`peashooter`). Comparing
    /// those strings literally silently disables every lookup - which is exactly what the first
    /// cut of this wiring did: the plant's rows were never found, every lift stayed 0, and the
    /// battle snapshot did not move by one pixel. `canonicalPlant` therefore falls back to a
    /// normalised comparison: lower case, a trailing `Default` dropped, and anything that is not
    /// a letter or a digit removed. On the shipped 224 spellings that collapse is one-to-one (224
    /// normalised names, zero collisions), so it cannot pick the wrong plant.
    std::string canonicalPlant(const std::string& plant) const;
    /// How many distinct plant spellings the table holds. Not the same as `size()`, which counts
    /// action rows.
    std::size_t plantAliases() const { return alias_.size(); }

    /// The row that governs a plant's launch height: among the plant's `shot`/`special` rows,
    /// the highest spawn point (smallest `yPx`). That is the muzzle a projectile leaves from;
    /// a plant that declares only sun/plantfood offsets returns nullptr, because those do not
    /// leave the plant's body.
    const SpawnOffset* launchOffset(const std::string& plant) const;

    /// `launchOffset`'s `yPx`, or 0 when the plant declares nothing. View space converts with
    /// `cellH / pxPerRow()`.
    double launchYPixels(const std::string& plant) const;
    /// `launchYPixels` in lawn rows; negative is higher. This is the number the report quotes
    /// when it says `DandelionDefault` is -8.62 rows.
    double launchYRows(const std::string& plant) const;

    /// How much a *zombie landing row* moves for `row`: always 0.
    ///
    /// The task that wired this asked for `row + yCols*0` and for proof that the shipped `y`
    /// really is a sub-cell nudge. It is not: 183 of the 487 rows sit outside +/-0.3 cells and
    /// the extremes are -8.62 rows (`DandelionDefault`) and -5.17 rows (`CobCannonDefault`),
    /// which are launch heights. Adding them to a row would put a zombie eight rows above the
    /// board, so the landing row keeps the sheet's row and the offset stays in the view.
    /// Kept as a function (instead of deleting the call site) so the proof is executable: row
    /// 0..7 all return 0 and the unit test asserts it.
    int rowAdjustmentForZombie(int row) const;

  private:
    std::vector<SpawnOffset> rows_;
    /// normalised spelling -> the spelling used in `rows_`; see `canonicalPlant`.
    std::unordered_map<std::string, std::string> alias_;
    std::size_t negativeRows_ = 0, positiveRows_ = 0, sentinelRows_ = 0;
    double medianYPx_ = 0;
    double pxPerRow_ = kFallbackPxPerRow;
    double pxPerColumn_ = kFallbackPxPerColumn;
};

/// How many shots this battle spawned from a plant whose `lawnchHeight` is non-zero, i.e. how
/// many projectile draws the view lifts. `--run-level` prints it as `spawnOffsetsApplied`.
///
/// Process-scoped on purpose: `world.hpp` is outside this task's write scope, so there is no
/// `World` member for it. `World`'s constructor resets it, so one `--run-level` process reports
/// exactly its own battle.
void noteSpawnOffsetApplied(double yPixels);
std::size_t spawnOffsetsApplied();
void resetSpawnOffsetsApplied();

} // namespace pvz::engine
