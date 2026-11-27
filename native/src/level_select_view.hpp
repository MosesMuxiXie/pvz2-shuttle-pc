#pragma once

// The level list for one world: the screen between the world map and a battle.
//
// It reads `catalog.levels`, filters by `worldId`, and shows the same three things the save
// knows about a level — its position in the world, how many stars it earned, whether it has been
// cleared. Enter returns the selected level id, which is exactly what `--play-script` and the
// battle preview want, so "world map -> level list -> battle" is one id away at every step.

#include "catalog.hpp"
#include "menu_view.hpp"
#include "progress.hpp"

#include <filesystem>
#include <string>
#include <vector>

namespace pvz {

struct LevelSelectOptions {
    /// Holds `ui/font_zh.ttc`.
    std::filesystem::path assetRoot;
    /// Which world's levels to list. Unknown ids produce an empty list, not an exception: a stale
    /// save or a typo in a launcher argument should show "no levels" rather than kill the client.
    std::string worldId;
    /// Which save the rows are read from; also printed in the footer (the screen never writes it).
    std::filesystem::path progressFile;
    /// Optional frame capture; `.png` writes PNG, anything else BMP.
    std::filesystem::path snapshot;
    /// >0 renders this many frames headlessly and returns; 0 runs the interactive window.
    int frames = 0;
};

/// One row: what the screen draws and what the test can assert without reading pixels.
struct LevelSelectRow {
    std::string id;
    int index = 0;   ///< the level's own `index` field (1-based inside its world)
    int stars = 0;
    bool cleared = false;
    std::string title;
};

struct LevelSelectResult {
    std::string world;
    int levels = 0;
    int cleared = 0;
    int stars = 0;
    int keys = 0;
    /// Index into `rows`, and the id a caller would hand to `--play-script`. Empty when the
    /// player pressed Esc (no level chosen) or the world has no levels at all.
    int selected = 0;
    std::string selectedLevel;
    /// The gameplay chips of `selectedLevel` (A7): `砸罐子`, `铁轨×2`, `+1` … Empty when the level has
    /// no badges or when the generated tables are missing — in both cases the screen simply has no
    /// badge line, which is why an empty vector is not an error.
    std::vector<std::string> badges;
    /// That same list joined for drawing: `砸罐子 · 铁轨×2`.
    std::string badgeLine;
    ScreenRect selectedRect;
    std::vector<LevelSelectRow> rows;
};

/// Draws the list and returns what was under the cursor. `progress` is the save to read rows from.
LevelSelectResult runLevelSelect(const Catalog& catalog, const Progress& progress,
                                 const LevelSelectOptions& options);

/// The `--level-select` payload as one object.
///
/// It lives here rather than in `main.cpp` so the badge list cannot drift out of the JSON: the CLI
/// prints `levelSelectJson(result)` and therefore always carries `badges` for the selected level.
Json levelSelectJson(const LevelSelectResult& result);

}  // namespace pvz
