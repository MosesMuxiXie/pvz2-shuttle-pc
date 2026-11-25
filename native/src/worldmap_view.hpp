#pragma once

// The world map screen: what the player picks a world from.
//
// This is the first screen that is *not* a battle. It renders `map::WorldMap` (the model in
// worldmap.cpp) with the same Chinese font the HUD uses, so a wrong model shows up as a wrong
// screen rather than as a passing unit test.
//
// Headless mode (`frames > 0`) renders exactly that many frames with SDL's software renderer and
// returns; the render test drives it that way, which is why the screen is testable in CI at all.

#include "catalog.hpp"
#include "worldmap.hpp"

#include <cstdint>
#include <filesystem>
#include <string>

namespace pvz {

struct WorldMapScreenOptions {
    /// Holds `ui/font_zh.ttc`.
    std::filesystem::path assetRoot;
    /// Optional save: stars/keys and per-level stars decide which worlds are open.
    std::filesystem::path progressFile;
    /// Optional frame capture; `.png` writes PNG, anything else BMP (same rule as `--play-script`).
    std::filesystem::path snapshot;
    /// >0 renders this many frames headlessly and returns; 0 runs the interactive window.
    int frames = 0;
};

/// What the screen decided. `entered` is the world id the player confirmed, empty when they quit.
struct WorldMapScreenResult {
    int worlds = 0;
    int unlocked = 0;
    int completed = 0;
    int stars = 0;
    int keys = 0;
    int selected = 0;
    std::string selectedWorld;
    std::string enteredWorld;
    std::string enteredLevel;
};

WorldMapScreenResult runWorldMapScreen(const Catalog& catalog, const map::WorldMap& map,
                                       const WorldMapScreenOptions& options);

}  // namespace pvz
