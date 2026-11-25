#pragma once
#include "catalog.hpp"
#include "engine/replay.hpp"
#include "engine/world.hpp"
#include <cstdint>
#include <filesystem>

namespace pvz {
// Interactive battle preview over the real kernel (`engine::World`): seed bank, planting,
// shovelling, sun collection and the HUD all drive the same world the simulation uses.
void runBattlePreview(const Catalog& catalog, const std::filesystem::path& assetRoot, bool smokeTest = false,
                      const std::filesystem::path& snapshot = {});

/// What a `--play-script` run actually achieved. `planted`/`collected`/`shoveled` count the
/// inputs the world accepted; `rejected` counts inputs the world refused (deck, sun, cooldown,
/// occupancy), so a script cannot look successful by having its clicks silently dropped.
struct PlayStats {
    std::size_t planted = 0, collected = 0, shoveled = 0, rejected = 0;
};

struct PlayScriptOptions {
    /// Empty means "probe next to the level content and the executable".
    std::filesystem::path assetRoot;
    /// Empty means no frame is captured (the kernel still runs the whole script).
    std::filesystem::path snapshot;
    double seconds = 30.0;
};

/// `engine::summarize()` plus the interaction counters above.
Json playScriptSummary(const engine::World& world, const PlayStats& stats);

/// Replays `script` on `levelId` and returns one line of statistics. The snapshot, when
/// requested, is the same view `--play` renders, drawn from the world read-only.
Json runPlayScript(const Catalog& catalog, const std::string& levelId, const engine::Script& script,
                   const PlayScriptOptions& options);
} // namespace pvz
