#include <cmath>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>

#include "worldmap.hpp"

namespace fs = std::filesystem;
using pvz::LevelRecord;
using pvz::Progress;
using pvz::map::Gate;
using pvz::map::GateKind;
using pvz::map::clearedLevelsFor;
using pvz::map::WorldInfo;
using pvz::map::WorldMap;
using pvz::map::WorldState;
using pvz::map::WorldStatus;

namespace {

void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

WorldMap loadMap(const fs::path& content) {
    return WorldMap::load(content, content.parent_path() / "native" / "generated" / "world_gates.json");
}

void testShape(const WorldMap& map) {
    check(map.worlds().size() == 26, "26 worlds, got " + std::to_string(map.worlds().size()));
    check(map.gates().size() == 97, "97 gates, got " + std::to_string(map.gates().size()));
    check(map.gateCount(GateKind::star) == 53,
          "53 star gates, got " + std::to_string(map.gateCount(GateKind::star)));
    check(map.gateCount(GateKind::key) == 27,
          "27 key gates, got " + std::to_string(map.gateCount(GateKind::key)));
    check(map.gateCount(GateKind::world) == 17,
          "17 world gates, got " + std::to_string(map.gateCount(GateKind::world)));
    // Order comes from content/worldmap.json and must survive the sort.
    check(map.worlds().front().id == "frontyard",
          "first world is frontyard, got " + map.worlds().front().id);
    // Levels are counted from stars.json keys, so a missing world must stay 0 rather
    // than borrow another world's levels through a prefix match.
    const auto* frontyard = map.find("frontyard");
    check(frontyard != nullptr && frontyard->levels == 175,
          "frontyard ships 175 levels, got " +
              std::to_string(frontyard ? frontyard->levels : -1));
    check(map.find("no_such_world") == nullptr, "an unknown world must resolve to null");
    // Display names come from a different file (`content/worlds.json`), so a load that reads
    // only worldmap.json would silently render ids on screen.
    check(frontyard != nullptr && frontyard->nameZh == "前院",
          "frontyard's Chinese name must come from content/worlds.json");
    int named = 0;
    for (const auto& world : map.worlds()) {
        if (!world.nameZh.empty()) ++named;
    }
    check(named == 26, "all 26 worlds carry a Chinese name, got " + std::to_string(named));
}

void testKeyCostIsNotStars(const WorldMap& map) {
    // The single most abused field: `key_gate` m_cost counts KEYS (1..5), not stars.
    int keyGatesWithCost = 0;
    for (const Gate& gate : map.gates()) {
        if (gate.kind != GateKind::key) continue;
        if (gate.hasKeys) {
            ++keyGatesWithCost;
            check(gate.keys >= 1 && gate.keys <= 5,
                  "a key gate costs 1..5 keys, got " + std::to_string(gate.keys) + " for " +
                      gate.event);
            check(!gate.hasStars, "a key gate must not carry a star count: " + gate.event);
        }
    }
    check(keyGatesWithCost == 27,
          "all 27 key gates carry a key count, got " + std::to_string(keyGatesWithCost));
}

void testStarSources(const WorldMap& map) {
    // cowboy's own start gate states 0 stars, so the sheet wins over unlock_cost.
    const WorldStatus cowboy = map.status("cowboy", 0, 1, 0);
    check(cowboy.requiredStars == 0, "cowboy's start gate says 0 stars");
    check(cowboy.requiredKeys == 1, "cowboy is key-gated and costs 1 key");
    check(cowboy.starsSource == "sheet", "cowboy's star count comes from the sheet");

    // lunarrainbowmarket's gate lives under the alias `rainbowmarket` and states 10 stars.
    const WorldStatus lunar = map.status("lunarrainbowmarket", 9, 5, 0);
    check(lunar.requiredStars == 10,
          "lunarrainbowmarket needs 10 stars, got " + std::to_string(lunar.requiredStars));
    check(lunar.state == WorldState::locked,
          "9 stars must not open a 10-star world, got " +
              std::string(pvz::map::worldStateName(lunar.state)));

    // egypt has no `<world>_stargate_start` at all and is key-gated, so it states no star
    // price. The model must say "none" rather than invent a 0-star or 1-star entry: a
    // key-gated world opened with stars would let a star farmer walk into a world the
    // original game keeps behind keys.
    const WorldStatus egypt = map.status("egypt", 0, 0, 0);
    check(egypt.requiredStars == 0, "egypt states no star price");
    check(egypt.starsSource == "none",
          "egypt's star count is absent, got " + egypt.starsSource);
    check(egypt.requiredKeys == 1, "egypt is key-gated and costs 1 key");
    check(egypt.state == WorldState::locked && egypt.reason.find("keys") != std::string::npos,
          "egypt must be locked for a missing key, got " + egypt.reason);

    // frontyard is the one world that is neither key-gated nor given a start gate, so its
    // requirement really is a client-side number and must be labelled as such.
    const WorldStatus frontyard = map.status("frontyard", 0, 0, 0);
    check(frontyard.requiredStars == 1, "frontyard falls back to unlock_cost 1");
    check(frontyard.starsSource == "client",
          "frontyard's star count is a client fallback, got " + frontyard.starsSource);
}

void testStatusFlow(const WorldMap& map) {
    // C48: the client prices even the first world, so a new save would have nothing to enter.
    // The model states the starter rule instead of letting the screen invent it.
    const WorldStatus starter = map.status("frontyard", 0, 0, 0);
    const auto* starterInfo = map.find("frontyard");
    check(starterInfo != nullptr && starterInfo->starter, "the lowest-order world is the starter");
    check(starter.state == WorldState::available,
          "the starter is open on a fresh save, got " + std::string(worldStateName(starter.state)));
    check(starter.reason.empty(), "an open world carries no lock reason");
    // A key is what actually opens egypt: stars alone must not.
    const WorldStatus egyptStarsOnly = map.status("egypt", 99, 0, 0);
    check(egyptStarsOnly.state == WorldState::locked,
          "stars must not open a key-gated world");
    const WorldStatus egyptWithKey = map.status("egypt", 0, 1, 0);
    check(egyptWithKey.state == WorldState::available, "one key opens egypt, got " +
                                                           std::string(worldStateName(egyptWithKey.state)));
    const auto* frontyard = map.find("frontyard");
    check(frontyard != nullptr, "frontyard must exist");
    const WorldStatus done = map.status("frontyard", 40, 0, frontyard->levels);
    check(done.state == WorldState::completed,
          "clearing every level completes the world, got " +
              std::string(pvz::map::worldStateName(done.state)));

    // A world the client ships no levels for can never be `completed`; claiming it were
    // would hide a missing world behind a green check.
    const WorldStatus unknown = map.status("no_such_world", 999, 99, 999);
    check(unknown.state == WorldState::locked, "an unknown world stays locked");
    check(unknown.reason == "unknown world", "an unknown world says so, got " + unknown.reason);
}

void testClearedLevelsAddUp(const WorldMap& map) {
    // One rule, two callers: `--worldmap` and `--worldmap-screen` must agree on "cleared".
    // Clearing every level the map knows about must sum to the save's own total, otherwise one
    // of the two screens is lying about a finished game.
    Progress progress;
    int expected = 0;
    for (const WorldInfo& world : map.worlds()) {
        const std::string prefix = world.id + "_";
        for (int index = 0; index < world.levels; ++index) {
            LevelRecord record;
            record.cleared = true;
            record.stars = 3;  // lunarrainbowmarket's sheet gate wants 10 stars
            progress.levels[prefix + std::to_string(index)] = record;
            ++expected;
        }
    }
    int summed = 0;
    for (const WorldInfo& world : map.worlds()) {
        summed += clearedLevelsFor(progress, world.id);
    }
    check(summed == expected,
          "per-world cleared counts must add up to " + std::to_string(expected) + ", got " +
              std::to_string(summed));

    int completed = 0;
    for (const WorldInfo& world : map.worlds()) {
        // C46: 25 of 26 worlds are key-gated, so "cleared everything" only completes a world
        // when the keys are there too. Hand out plenty and the completion rule is what is tested.
        const WorldStatus status =
            map.status(world.id, progress.totalStars(), 99, clearedLevelsFor(progress, world.id));
        if (status.state == WorldState::completed) ++completed;
    }
    std::string notCompleted;
    for (const WorldInfo& world : map.worlds()) {
        const WorldStatus status =
            map.status(world.id, progress.totalStars(), 99, clearedLevelsFor(progress, world.id));
        if (status.state != WorldState::completed && notCompleted.empty()) {
            notCompleted = world.id + " (" + status.reason + ", levels " +
                           std::to_string(world.levels) + ", cleared " +
                           std::to_string(clearedLevelsFor(progress, world.id)) + ")";
        }
    }
    check(notCompleted.empty(),
          "a save that cleared every level must complete every world, first miss: " +
              notCompleted);

    // A level id that belongs to no world must not be attributed to one.
    Progress stray;
    LevelRecord record;
    record.cleared = true;
    stray.levels["not_a_world_1"] = record;
    check(clearedLevelsFor(stray, "frontyard") == 0,
          "an unknown level id must not be counted for frontyard");
}

void testAliases(const WorldMap& map) {
    // The generator resolved `skycity` → `sky`, `gta` → `losantosvice`,
    // `rainbowmarket` → `lunarrainbowmarket`. Reading the pack-side id must still find
    // the client world, otherwise the map silently loses gates.
    const auto sky = map.gatesFor("sky");
    check(!sky.empty(), "sky must resolve the skycity gates");
    bool sawAlias = false;
    for (const Gate* gate : sky) {
        if (gate->world == "skycity" && gate->worldClient == "sky") sawAlias = true;
    }
    check(sawAlias, "a gate from world skycity must land on the client world sky");
    const auto lunar = map.gatesFor("lunarrainbowmarket");
    bool sawRainbow = false;
    for (const Gate* gate : lunar) {
        if (gate->world == "rainbowmarket") sawRainbow = true;
    }
    check(sawRainbow, "a gate from world rainbowmarket must land on lunarrainbowmarket");
}

}  // namespace

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    if (argc < 2) {
        std::cerr << "usage: worldmap_test <content>\n";
        return 2;
    }
    try {
        const fs::path content{argv[1]};
        const WorldMap map = loadMap(content);
        testShape(map);
        testKeyCostIsNotStars(map);
        testStarSources(map);
        testStatusFlow(map);
        testAliases(map);
        testClearedLevelsAddUp(map);
    } catch (const std::exception& error) {
        std::cerr << "worldmap test failed: " << error.what() << '\n';
        return 1;
    }
    std::cout << "worldmap tests passed\n";
    return 0;
}
