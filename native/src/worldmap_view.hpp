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

/// How many entries the meta screens hold, read from `metagame.json` (A7).
///
/// The world map is where a player looks for "what else is there", so it is the honest place to say
/// how big the almanac and the garden are. A checkout without the generated table simply has no such
/// line: `loaded` stays false and the screen draws nothing.
struct MetagameCounts {
    int plants = 0;   ///< `almanac.counts.plants`
    int zombies = 0;  ///< `almanac.counts.zombies`
    int drops = 0;    ///< `garden.counts.collectables`
    bool loaded = false;
    std::string note;  ///< why nothing loaded; empty on success
};

/// Reads `metagame.json` from `generatedDir`. Never throws.
MetagameCounts loadMetagameCounts(const std::filesystem::path& generatedDir);

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
    /// Worlds every level of which is cleared (the same number as `completed`, named for the JSON:
    /// `clearedWorlds`).
    int clearedWorlds = 0;
    MetagameCounts metagame;
};

WorldMapScreenResult runWorldMapScreen(const Catalog& catalog, const map::WorldMap& map,
                                       const WorldMapScreenOptions& options);

/// The `--worldmap-screen` payload as one object: the world counts plus the almanac/garden entry
/// line, so the CLI cannot print one without the other.
Json worldMapScreenJson(const WorldMapScreenResult& result);

}  // namespace pvz
