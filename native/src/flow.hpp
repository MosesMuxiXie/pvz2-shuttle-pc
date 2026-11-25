// One cycle of the S4 loop, engine-side and headless: pick a level from the save, play it, fold the
// result back into the save.
//
// Why this lives outside `main.cpp`: the loop is the part worth testing, and a test that has to
// build a command line to exercise it can only assert on stdout text. Everything here is plain
// values in and plain values out, so `flow_test` can run two cycles against one save and look at
// the data between them.
#pragma once

#include "catalog.hpp"
#include "engine/replay.hpp"
#include "engine/world.hpp"
#include "progress.hpp"

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace pvz {

/// Which level the loop would play next, and why.
struct FlowPick {
    std::string world;      ///< the world the level belongs to
    std::string level;      ///< level id to play
    std::string lastLevel;  ///< the save's `lastLevel`, empty when it has none
    bool fromLastLevel = false;  ///< world came from `lastLevel`, not from the starter world
    bool allCleared = false;     ///< every level in that world is cleared, so it replays the first
};

/// Ordered level ids of one world: by the level's own `index`, then by id.
std::vector<std::string> levelsOfWorld(const Catalog& catalog, const std::string& world);

/// The world a fresh save starts in: the world of the lowest-indexed level in the catalog.
std::string starterWorld(const Catalog& catalog);

/// Picks the next level: the world of `lastLevel` when the save names one, otherwise the starter
/// world; then the first uncleared level of that world, otherwise its first level.
FlowPick pickNextLevel(const Catalog& catalog, const Progress& progress, const std::string& lastLevel);

struct FlowResult {
    std::string world;
    std::string level;
    std::string status;   ///< "won" / "lost" / "playing" — `engine::World::status()` verbatim
    std::uint64_t tick = 0;
    int stars = 0;        ///< stars this attempt earned
    int levelStars = 0;   ///< stars the save now holds for the level (never regresses)
    bool cleared = false; ///< the level is cleared in the save after this attempt
    std::string lastLevel;

    // T55: what the battle paid, folded into the save before it was written. Same five facts
    // `--run-level --progress` prints, so the two commands cannot disagree about a reward.
    int coinsGained = 0;
    int keysGained = 0;
    int seedsGained = 0;
    bool presentTableMissing = false;
    Json rewardUnmodelled = Json::array();  ///< `[{kind, count}]`, sorted by kind

    Json json() const;
};

/// Plays exactly one attempt of `pick.level` with `script` for at most `seconds` of simulated time,
/// folds it into `progress` with the same bookkeeping `--run-level --progress` uses, and reports
/// what happened. `progress` is updated in place; saving it is the caller's job, so a caller can
/// decide when the write happens.
FlowResult playPickedLevel(const Catalog& catalog, Progress& progress, const StarTable& stars,
                           const FlowPick& pick, const engine::Script& script, double seconds,
                           const engine::WorldOptions& worldOptions = {});

/// `pickNextLevel` + `playPickedLevel`: one loop iteration from a save to the same save.
FlowResult runFlowCycle(const Catalog& catalog, Progress& progress, const StarTable& stars,
                        const std::string& saveLastLevel, const engine::Script& script,
                        double seconds, const engine::WorldOptions& worldOptions = {});

}  // namespace pvz
