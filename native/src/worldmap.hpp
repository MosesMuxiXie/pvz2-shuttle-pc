#pragma once

// The world map: what the player sees between levels.
//
// The original game drives this from `WorldData.m_eventList` (97 gates: 53 star
// gates, 27 key gates, 17 world gates) plus per-world map pieces. The client keeps
// its own `content/worldmap.json` (26 worlds, order/difficulty/unlock_cost). Neither
// source alone is enough, and they disagree in two places that matter:
//
//   * `key_gate` `m_cost` is a NUMBER OF KEYS (1..5), while `star_gate` `m_cost` is a
//     STAR COUNT. Treating them as the same currency is what produced the earliest
//     bug reports about keys.
//   * world ids differ (`gta` vs `losantosvice`, `skycity` vs `sky`,
//     `rainbowmarket` vs `lunarrainbowmarket`). The generator resolves those and
//     stores both sides; this reader uses `worldClient` when present.
//
// This header deliberately has no SDL dependency: the map must be testable in the
// audit build, which never links the desktop target.

#include <cstddef>
#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include "progress.hpp"

namespace pvz::map {

enum class GateKind { star, key, world, unknown };

const char* gateKindName(GateKind kind);

struct Gate {
    GateKind kind = GateKind::unknown;
    std::string event;
    std::string world;        // pack world id
    std::string worldClient;  // client world id (same when the generator found no alias)
    std::string target;       // worldgate target: client id when resolvable
    std::string package;      // `extra.package` of the level that owns the event, when known
    int stars = 0;            // meaningful for star gates
    int keys = 0;             // meaningful for key gates; 1..5, NOT stars
    bool hasStars = false;
    bool hasKeys = false;
};

struct WorldInfo {
    std::string id;
    std::string nameKey;
    // Chinese/English display names come from `content/worlds.json` (a list, unlike
    // worldmap.json's object). They are optional: a world the export missed still shows its id.
    std::string nameZh;
    std::string nameEn;
    std::string desc;
    int order = 0;
    int difficulty = 0;
    int unlockCost = 0;     // stars for a world, keys when `keyRequired`
    bool keyRequired = false;
    int levels = 0;         // levels the client ships for this world
    int entryStars = 0;     // stars demanded by `<world>_stargate_start`, 0 when absent
    // True when the sheet actually carries `<world>_stargate_start`. A gate that demands
    // 0 stars is not the same fact as no gate at all, and the UI/status message must be
    // able to tell them apart.
    bool hasEntryGate = false;
    std::size_t gateCount = 0;
    // The lowest-order world is where a new save starts. The client file still prices it
    // (`frontyard` costs 1 star), which would leave a fresh save with nothing to enter, so the
    // model states the rule explicitly instead of special-casing it inside the screen. See C48.
    bool starter = false;
};

enum class WorldState { locked, available, completed };

const char* worldStateName(WorldState state);

struct WorldStatus {
    WorldState state = WorldState::locked;
    int requiredStars = 0;
    int requiredKeys = 0;
    int earnedStars = 0;
    int keys = 0;
    int clearedLevels = 0;
    // Where `requiredStars` came from: `sheet` when the world's own star gate carried a
    // count, `client` when it fell back to content/worldmap.json's unlock_cost, `none`
    // when the world is key-gated and states no star price.
    std::string starsSource;
    std::string reason;  // why it is locked, empty when it is not
};

class WorldMap {
public:
    /// `gates` is `native/generated/world_gates.json`; `worldmap` is
    /// `content/worldmap.json`; `stars` is `content/stars.json` (level → goals), used
    /// only to count how many levels each world ships.
    static WorldMap load(const std::filesystem::path& contentDir,
                         const std::filesystem::path& gatesFile);

    const std::vector<WorldInfo>& worlds() const { return worlds_; }
    const std::vector<Gate>& gates() const { return gates_; }
    const WorldInfo* find(const std::string& id) const;
    std::vector<const Gate*> gatesFor(const std::string& worldClient) const;

    /// Stars needed to open the world: the `*_stargate_start` gate's count when the
    /// sheet has one, otherwise the client's `unlock_cost`.
    int requiredStars(const std::string& id) const;
    /// Keys needed to open the world: `unlock_cost` when `key_required`, else 0.
    int requiredKeys(const std::string& id) const;

    /// `earnedStars` and `keys` come from `Progress`; `clearedLevels` counts levels of
    /// this world already recorded as cleared. A world is `completed` only when every
    /// level the client ships for it is cleared.
    WorldStatus status(const std::string& id, int earnedStars, int keys, int clearedLevels) const;

    std::size_t gateCount(GateKind kind) const;

private:
    std::vector<WorldInfo> worlds_;
    std::vector<Gate> gates_;
    std::map<std::string, std::size_t> index_;
};

/// Levels of `worldId` that the save reports cleared.
///
/// Level ids are `<world>_<n>`, so the prefix is the world. `main.cpp` (`--worldmap`) and
/// `worldmap_view.cpp` (`--worldmap-screen`) both asked this question; keeping two copies of the
/// rule is how the CLI once answered 0 while the save said 175 (t35 H1).
int clearedLevelsFor(const Progress& progress, const std::string& worldId);

}  // namespace pvz::map
