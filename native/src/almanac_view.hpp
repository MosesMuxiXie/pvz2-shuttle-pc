#pragma once

// The almanac screen: the two-column browser over `native/generated/metagame.json`.
//
// It sits beside `runLevelSelect()` and `runGarden()` on purpose: one screen, one `run*()`
// function, one CLI flag (wired by the captain, not here), one test. Everything below is a pure
// function of the compiled table plus an optional save, so the whole screen is checkable without
// a window: `loadAlmanac()` reads, `almanacPage()` pages, `renderAlmanacHeadless()` draws two
// frames and returns the same JSON the CLI prints.
//
// Two facts about the source table shape this file, and both are in the report:
//
//  * `metagame.json` ships *localization keys* and a `resolved` map of booleans, never the prose
//    itself. A name is therefore only printable when `content/plants.json` (or `content/zombies.json`)
//    carries that id; otherwise the row shows the id and the detail panel says so. Nothing here
//    pretends a key is a translation.
//  * `levels` is "how many level packages reference this id", not "the first level it appears in".
//    The table has no first-appearance id, so the detail panel prints the count and labels it.
//
// Grayscale ("seen") is derived, not shipped: an entry is revealed once the save has cleared a
// level in the entry's world. A missing or empty save reveals everything, which is what the task
// asks for ("没有 progress 时全部可见"), and an entry whose world token has no content world behind
// it stays visible instead of being greyed out forever.

#include "catalog.hpp"
#include "menu_view.hpp"
#include "progress.hpp"

#include <filesystem>
#include <string>
#include <vector>

namespace pvz {

/// Rows per page in the middle column. Twelve fits between the 96-pixel header and the footer with
/// 30-pixel rows, and it is the number the task fixed.
inline constexpr int kAlmanacPageSize = 12;

/// One `AlmanacDataEntries` row: `statType` is the sheet's own lowercase kind (`suncost`, `armor`,
/// `family`), `valueKey` the localization key it resolves through.
struct AlmanacStat {
    std::string type;
    std::string name;
    std::string typeKey;
    std::string valueKey;
};

struct AlmanacEntry {
    std::string id;
    /// `plant` or `zombie`; also the left column's key.
    std::string kind;
    std::string nameKey;
    std::string descKey;
    /// Printable name: `content/plants.json`'s `name_zh` when the id is there, else the id.
    std::string name;
    /// Whether `content/` supplied `name`. When false the row shows its id, and that is the only
    /// honest thing to show: `metagame.json` carries `nameKey`, never the translated string.
    bool nameFromContent = false;
    /// Printable description: the content prose when it exists, else empty. Never a bare key.
    std::string description;
    /// Plant family token trimmed from `STAT_FAMILY_*`; for a zombie this is its `ZombieClass`.
    std::string family;
    /// Internal `HomeWorld` token. Empty when the sheet never set one (51 of the 167 plants).
    std::string world;
    /// Numeric cost/hp when `content/` ships them, else -1.
    int cost = -1;
    int hp = -1;
    /// The tier key the almanac sheet carries when there is no number (`STAT_TOUGHNESS_ARMOR0`).
    std::string costKey;
    std::string hpKey;
    /// Level packages that reference this id. See the header comment: a count, not a first level.
    int levels = 0;
    /// Whether the save has revealed it. See `almanacWithProgress()`.
    bool seen = true;
    std::vector<AlmanacStat> stats;
};

struct AlmanacData {
    std::vector<AlmanacEntry> plants;
    std::vector<AlmanacEntry> zombies;
    /// The `metagame.json` that was read, so a screenshot can be traced to a table.
    std::filesystem::path source;
    /// What could not be read (empty when everything was). Never an exception for a missing
    /// optional input: a content tree without `plants.json` still shows the almanac.
    std::string note;

    /// `kind == "zombie"` selects `zombies`, anything else `plants`.
    const std::vector<AlmanacEntry>& entries(const std::string& kind) const;
};

/// `metagame.json` next to `contentRoot`, or the source-tree location when it is not installed.
/// Mirrors `generatedTable()` in main.cpp without sharing it: this file is linked into tests that
/// never build the CLI.
std::filesystem::path metagameTablePath(const std::filesystem::path& contentRoot);

/// Reads `metagame.json` (loudly fails when it is missing) and the display text `content/` may have.
AlmanacData loadAlmanac(const std::filesystem::path& contentRoot);

/// Copies `data` with `seen` recomputed from the save. A null/empty progress reveals everything.
AlmanacData almanacWithProgress(AlmanacData data, const Progress* progress);

/// Worlds the save has cleared at least one level in, derived from level ids (`beach_1` -> `beach`).
/// `ALIASES` folds the two almanac tokens that name a content world differently (`tutorial` is the
/// frontyard intro, `skycity` is `sky`); every other token is compared verbatim.
std::vector<std::string> almanacClearedWorlds(const Progress& progress);

/// One page of the middle column. `index` is clamped into `[0, total-1]`; an empty table yields
/// `total == 0` and `first == last == 0`.
struct AlmanacPage {
    int total = 0;
    int index = 0;
    int page = 0;
    int pages = 0;
    int first = 0;
    int last = 0;
    std::vector<int> visible;
};

AlmanacPage almanacPage(const std::vector<AlmanacEntry>& entries, int index,
                        int pageSize = kAlmanacPageSize);

struct AlmanacOptions {
    std::filesystem::path contentRoot;
    /// Holds `ui/font_zh.ttc`.
    std::filesystem::path assetRoot;
    /// Which save reveals entries. Empty reads the built-in default: nothing is revealed.
    std::filesystem::path progressFile;
    /// Optional frame capture; `.png` writes PNG, anything else BMP.
    std::filesystem::path snapshot;
    /// >0 renders this many frames headlessly and returns; 0 runs the interactive window.
    int frames = 0;
};

struct AlmanacResult {
    std::string kind;
    int index = 0;
    int total = 0;
    int page = 0;
    int pages = 0;
    /// The id the cursor sat on. Empty when the table had no rows for `kind`.
    std::string selectedId;
    /// Where the selected row was drawn, for the render test.
    ScreenRect selectedRect;
    /// Exactly the four keys the CLI prints: `screen`, `kind`, `index`, `total`.
    Json json;
};

/// `{"screen":"almanac","kind":kind,"index":index,"total":total}` — the wire shape, built in one
/// place so the CLI and the tests cannot drift apart.
Json almanacJson(const std::string& kind, int index, int total);

/// Draws the screen. `index` is the initial cursor, clamped; `kind` is `plant` or `zombie`.
AlmanacResult runAlmanac(const AlmanacData& data, const std::string& kind, int index,
                         const AlmanacOptions& options);

/// The one call `main.cpp` needs: load, apply `progressFile`, draw `frames` frames into
/// `snapshot`, return the CLI JSON. `assetRoot` defaults to the artwork tree next to the content
/// directory (`PVZ_ASSET_ROOT` wins when set), which is how a packaged build finds the font.
Json renderAlmanacHeadless(const std::filesystem::path& contentRoot, const std::string& kind,
                           int index, int frames, const std::filesystem::path& snapshot,
                           const std::filesystem::path& progressFile = {},
                           const std::filesystem::path& assetRoot = {});

/// Font/artwork root used when a caller does not pass one: `PVZ_ASSET_ROOT`, then `assets/` next to
/// the content directory, then `<workspace>/PvZ2SHUTTLE/assets`.
std::filesystem::path defaultAssetRoot(const std::filesystem::path& contentRoot);

}  // namespace pvz
