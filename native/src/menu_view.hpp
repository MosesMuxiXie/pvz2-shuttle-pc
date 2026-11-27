#pragma once

// The main menu: the screen the client opens with, and the only place that decides whether the
// player continues a save, walks to the world map, or leaves.
//
// It sits beside `runWorldMapScreen()` and `runBattlePreview()` on purpose: one screen, one
// `run*Screen()` function, one CLI flag, one render test. That is what makes the chain
// "menu -> world map -> level list -> battle" checkable from the command line instead of only by
// watching a window.
//
// Headless mode (`frames > 0`) renders exactly that many frames with SDL's software renderer and
// returns without polling for input, which is how the render test runs it.

#include "catalog.hpp"
#include "progress.hpp"

#include <filesystem>
#include <string>

struct SDL_Renderer;  // only the snapshot helper below needs it

namespace pvz {

/// What the player picked. `continueGame` is only reachable when the save has something to
/// continue; otherwise the menu starts on 世界地图 so a fresh install cannot "continue" into a
/// game that does not exist.
///
/// The second half (`almanac` … `settings`) are the meta screens added with A/B/C: the menu is the
/// only place that knows they exist, so each one needs a value here and a branch in `main.cpp`.
/// They never touch the battle clock — `runMainMenu` returns, the caller opens the screen, and the
/// menu is shown again when it closes.
enum class MenuChoice {
    continueGame,
    worldMap,
    almanac,
    garden,
    achievements,
    daily,
    settings,
    shop,
    quit,
};

/// The spelling used by `--menu`'s JSON line. `continue` doubles as a C++ keyword, so the enum
/// value is `continueGame` while the wire name stays `continue`.
const char* menuChoiceName(MenuChoice choice);

/// A rectangle in screen pixels. The render tests sample `MenuResult::selectedRect` because a
/// screen whose text silently failed to draw is otherwise indistinguishable from a working one:
/// both produce a 1280x720 PNG with the right background colours.
struct ScreenRect {
    double x = 0.0;
    double y = 0.0;
    double w = 0.0;
    double h = 0.0;
};

struct MenuOptions {
    /// Holds `ui/font_zh.ttc`.
    std::filesystem::path assetRoot;
    /// Which save the header is describing. The screen never writes it; `--menu` prints it in the
    /// footer so two saves can be told apart while the same content directory is in use.
    std::filesystem::path progressFile;
    /// Optional frame capture; `.png` writes PNG, anything else BMP (same rule as `--play-script`).
    std::filesystem::path snapshot;
    /// >0 renders this many frames headlessly and returns; 0 runs the interactive window.
    int frames = 0;
};

struct MenuResult {
    MenuChoice choice = MenuChoice::quit;
    /// How many items the menu drew (8) and which one the cursor sat on.
    int items = 0;
    int selected = 0;
    /// Whether 继续游戏 was selectable. False on a save with no attempts at all.
    bool continued = false;
    int stars = 0;
    int keys = 0;
    int cleared = 0;
    /// Where the selected item's rectangle was drawn, for the render test.
    ScreenRect selectedRect;
};

/// Draws the menu and returns the player's choice. `progress` is the save to display; the caller
/// loads it (the CLI does, the launcher will) so this function has no filesystem policy of its own.
MenuResult runMainMenu(const Catalog& catalog, const Progress& progress,
                       const MenuOptions& options);

/// Writes the current render target to `path`: `.png`/`.PNG` through SDL_image, anything else as
/// BMP. Shared with the level list because both screens capture frames the same way; the copy in
/// worldmap_view.cpp is file-static, so the chain's newer screens share this one.
void saveScreenSnapshot(SDL_Renderer* renderer, const std::filesystem::path& path);

}  // namespace pvz
