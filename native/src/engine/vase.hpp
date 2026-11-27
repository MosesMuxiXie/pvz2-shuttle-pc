// Vasebreaker: the arcade mode where the lawn starts covered in vases.
//
// Everything here is read from `native/generated/vasebreaker.json`, which the meta builder
// compiles out of the shipped `VaseBreakerPresetProperties` rows (the report
// `docs/reviews/2026-11-25-vasebreaker-data.md` is the survey behind it). Forty-seven levels
// carry `extra.vasebreaker` in content and the table has exactly those forty-seven keys.
//
// What the sheet does **not** say, and what this file therefore refuses to pretend it knows:
//
//   * a cell per vase. All 459 entries carry `row: null, col: null`; the sheet gives a count per
//     content type plus a column band (`MinColumnIndex`..`MaxColumnIndex`) and, on five levels, a
//     list of excluded cells. The cells are drawn from that band at runtime with the level's own
//     generator, so the layout is a deterministic inference, not sheet data.
//   * a sun amount. Every `sunAmount` is null and the only collectable the sheet names is
//     `plantfood`, so `kVaseSunValue` below is a tuning constant, not a reading.
//
// One level has the flag but no preset at all (`frontyard_166`, 0 vases). It is reported and
// played as an ordinary level instead of being declared won on tick 1 with nothing on the lawn.
#pragma once

#include <cstddef>
#include <filesystem>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace pvz::engine {

/// What sits inside a vase. The sheet's discriminators are `ZombieTypeName`, `PlantTypeName` and
/// `CollectableTypeName`; a collectable that names sun is folded into `sun` so the four classes the
/// arcade needs stay exhaustive.
enum class VaseContent { zombie, plant, collectible, sun };

/// `"zombie"` / `"plant"` / `"collectible"` / `"sun"`, as printed by `--run-level` and events.
const char* vaseContentName(VaseContent content);

/// One row of the sheet's `Vases[]`: a content type, the id it names, and how many vases hold it.
struct VaseEntry {
    VaseContent content = VaseContent::zombie;
    std::string id;
    int count = 0;
};

/// One level's vases, as the sheet declares them.
struct VaseSpec {
    std::string levelId;
    std::vector<VaseEntry> entries;
    /// Sum of `entries[].count`. This, not `vaseCount`, is what the level lays down: the sheet's
    /// own count field is null on the end-of-line odd cases and the entries always add up.
    int total = 0;
    /// The sheet's own column band. `maxColumn < 0` means "no band" (the whole board).
    int minColumn = 0;
    int maxColumn = -1;
    /// Cells the sheet excludes, already flipped to `(row, col)`: the sheet stores `{mX, mY}`, i.e.
    /// `[col, row]` (proved by the entries that would fall off a 6-row beach board any other way).
    std::vector<std::pair<int, int>> excluded;
    /// `VaseGridItemType`, `vase_firework` on three levels. Kept for the report; the kernel has no
    /// firework vase behaviour yet.
    std::string gridItemType;
    bool empty() const { return entries.empty() || total <= 0; }
};

/// The process-wide vase table. One parse per process, like every other generated table.
class VaseTable {
  public:
    static constexpr int kFormat = 1;
    static constexpr const char* kFileName = "vasebreaker.json";

    /// Throws `vase table: <path>: <reason>` when the file cannot be read or does not look like a
    /// vase table, so a broken generated file fails at construction rather than at the first tap.
    static VaseTable load(const std::filesystem::path& path);
    /// The table next to the other generated data (`engine::generatedDir()`).
    static const VaseTable& shared();

    /// Null when this level has no vase preset.
    const VaseSpec* find(std::string_view levelId) const;
    std::size_t size() const { return specs_.size(); }
    bool empty() const { return specs_.empty(); }
    const std::vector<VaseSpec>& specs() const { return specs_; }
    /// Vases over every level in the table (1435 for the shipped data).
    int totalVases() const;

  private:
    std::vector<VaseSpec> specs_;
};

/// A sun vase's payout. **Tuning constant, not sheet data**: every `sunAmount` in the generated
/// table is null and the only collectable the client ships is `plantfood`. Chosen to match one sky
/// sun, which is what an unlabelled "sun" vase would be worth in the arcade.
inline constexpr int kVaseSunValue = 25;

} // namespace pvz::engine
