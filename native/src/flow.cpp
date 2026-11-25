#include "flow.hpp"

#include <algorithm>
#include <stdexcept>

#include "rewards.hpp"

namespace pvz {

std::vector<std::string> levelsOfWorld(const Catalog& catalog, const std::string& world) {
    std::vector<const LevelDefinition*> found;
    for (const auto& entry : catalog.levels) {
        if (entry.second.world == world) found.push_back(&entry.second);
    }
    std::sort(found.begin(), found.end(), [](const LevelDefinition* a, const LevelDefinition* b) {
        if (a->index != b->index) return a->index < b->index;
        return a->id < b->id;
    });
    std::vector<std::string> ids;
    ids.reserve(found.size());
    for (const auto* level : found) ids.push_back(level->id);
    return ids;
}

std::string starterWorld(const Catalog& catalog) {
    // The world map has an explicit order (`scene/worlds` -> `order`), so the starter world is
    // the first one in it, not whichever level id sorts first. `frontyard` is order 1 and is the
    // only world a fresh save may open; the fallback below keeps a catalog without worlds usable.
    const WorldDefinition* first = nullptr;
    for (const auto& entry : catalog.worlds) {
        const WorldDefinition& world = entry.second;
        if (levelsOfWorld(catalog, world.id).empty()) continue;
        if (first == nullptr || world.order < first->order ||
            (world.order == first->order && world.id < first->id)) {
            first = &world;
        }
    }
    if (first != nullptr) return first->id;
    if (!catalog.levels.empty()) return catalog.levels.begin()->second.world;
    throw std::runtime_error("the catalog has no levels");
}

FlowPick pickNextLevel(const Catalog& catalog, const Progress& progress,
                       const std::string& lastLevel) {
    FlowPick pick;
    pick.lastLevel = lastLevel;

    // The save's own world first: "continue" should resume where the player was, not where a new
    // player would start.
    if (!lastLevel.empty()) {
        const auto remembered = catalog.levels.find(lastLevel);
        if (remembered != catalog.levels.end()) {
            pick.world = remembered->second.world;
            pick.fromLastLevel = true;
        }
    }
    if (pick.world.empty()) pick.world = starterWorld(catalog);

    const std::vector<std::string> levels = levelsOfWorld(catalog, pick.world);
    if (levels.empty()) {
        throw std::runtime_error("world has no levels: " + pick.world);
    }
    for (const std::string& id : levels) {
        const LevelRecord* record = progress.find(id);
        if (record == nullptr || !record->cleared) {
            pick.level = id;
            return pick;
        }
    }
    // Everything in this world is cleared: replay the first level rather than refusing to continue.
    pick.level = levels.front();
    pick.allCleared = true;
    return pick;
}

Json FlowResult::json() const {
    return Json{{"world", world},
                {"level", level},
                {"status", status},
                {"tick", tick},
                {"stars", stars},
                {"levelStars", levelStars},
                {"cleared", cleared},
                {"lastLevel", lastLevel},
                {"coinsGained", coinsGained},
                {"keysGained", keysGained},
                {"seedsGained", seedsGained},
                {"presentTableMissing", presentTableMissing},
                {"rewardUnmodelled", rewardUnmodelled}};
}

FlowResult playPickedLevel(const Catalog& catalog, Progress& progress, const StarTable& stars,
                           const FlowPick& pick, const engine::Script& script, double seconds,
                           const engine::WorldOptions& worldOptions) {
    const auto found = catalog.levels.find(pick.level);
    if (found == catalog.levels.end()) throw std::runtime_error("unknown level: " + pick.level);

    engine::World world(catalog, found->second, script.seed, worldOptions);
    engine::runScript(world, script, seconds);

    const BattleOutcome outcome = outcomeOf(world);
    const std::vector<StarGoal>* goals = stars.find(pick.level);
    static const std::vector<StarGoal> kNoGoals;
    const StarOutcome earned = evaluateStars(goals != nullptr ? *goals : kNoGoals, outcome);

    // Same call `--run-level --progress` makes, so the two commands cannot disagree about what a
    // finished battle does to a save (stars never regress, attempts always rise).
    recordBattle(progress, pick.level, outcome, stars);

    // T55: the battle also pays coins, keys and seed bags. Settled from the live world (its kill
    // counter and RNG), then folded into the same save the stars just went into. The gate for the
    // four world keys is read before the fold, so clearing egypt_3 unlocks them from the next
    // battle rather than retroactively for the one that cleared it.
    const bool keyGate = keysUnlocked(progress);
    SettlementOptions rewards;
    rewards.keysUnlocked = keyGate;
    const std::string package =
        found->second.extra.is_object() && found->second.extra.contains("package") &&
                found->second.extra["package"].is_string()
            ? found->second.extra["package"].get<std::string>()
            : std::string();
    const RewardGain gain =
        settleRewards(RewardTable::shared(), world, pick.world, package, rewards);
    applyRewards(progress, gain);

    FlowResult result;
    result.world = pick.world;
    result.level = pick.level;
    result.status = world.status();
    result.tick = world.tick();
    result.stars = earned.stars;
    result.lastLevel = pick.level;
    result.coinsGained = gain.coins;
    result.keysGained = gain.keys;
    result.seedsGained = static_cast<int>(gain.seeds.size());
    result.presentTableMissing = gain.presentTableMissing;
    for (const RewardUnknown& unknown : gain.unmodelled) {
        result.rewardUnmodelled.push_back(Json{{"kind", unknown.kind}, {"count", unknown.count}});
    }
    if (const LevelRecord* record = progress.find(pick.level); record != nullptr) {
        result.levelStars = record->stars;
        result.cleared = record->cleared;
    }
    return result;
}

FlowResult runFlowCycle(const Catalog& catalog, Progress& progress, const StarTable& stars,
                        const std::string& saveLastLevel, const engine::Script& script,
                        double seconds, const engine::WorldOptions& worldOptions) {
    const FlowPick pick = pickNextLevel(catalog, progress, saveLastLevel);
    return playPickedLevel(catalog, progress, stars, pick, script, seconds, worldOptions);
}

}  // namespace pvz
