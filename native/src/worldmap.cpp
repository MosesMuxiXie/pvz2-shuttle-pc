#include "worldmap.hpp"

#include "loc.hpp"  // B6b: world names the content list does not carry

#include <algorithm>
#include <cctype>
#include <fstream>
#include <limits>
#include <stdexcept>

#include <nlohmann/json.hpp>

namespace pvz::map {
namespace {

using Json = nlohmann::json;

[[noreturn]] void fail(const std::filesystem::path& path, const std::string& what) {
    throw std::runtime_error("world map: " + path.string() + ": " + what);
}

Json readJson(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) fail(path, "cannot open");
    try {
        return Json::parse(stream);
    } catch (const std::exception& error) {
        fail(path, error.what());
    }
}

const Json* member(const Json& object, const char* key) {
    if (!object.is_object()) return nullptr;
    const auto found = object.find(key);
    if (found == object.end() || found->is_null()) return nullptr;
    return &*found;
}

std::string text(const Json& object, const char* key) {
    const Json* value = member(object, key);
    if (!value || !value->is_string()) return {};
    return value->get<std::string>();
}

std::string upper(const std::string& value) {
    std::string out = value;
    for (char& c : out) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    return out;
}

int number(const Json& object, const char* key) {
    const Json* value = member(object, key);
    if (!value || !value->is_number_integer()) return 0;
    return value->get<int>();
}

std::optional<int> optionalNumber(const Json& object, const char* key) {
    const Json* value = member(object, key);
    if (!value || !value->is_number_integer()) return std::nullopt;
    return value->get<int>();
}

GateKind kindOf(const std::string& name) {
    if (name == "star_gate") return GateKind::star;
    if (name == "key_gate") return GateKind::key;
    if (name == "worldgate") return GateKind::world;
    return GateKind::unknown;
}

}  // namespace

const char* gateKindName(GateKind kind) {
    switch (kind) {
        case GateKind::star: return "star_gate";
        case GateKind::key: return "key_gate";
        case GateKind::world: return "worldgate";
        case GateKind::unknown: break;
    }
    return "unknown";
}

const char* worldStateName(WorldState state) {
    switch (state) {
        case WorldState::locked: return "locked";
        case WorldState::available: return "available";
        case WorldState::completed: return "completed";
    }
    return "locked";
}

WorldMap WorldMap::load(const std::filesystem::path& contentDir,
                        const std::filesystem::path& gatesFile) {
    WorldMap map;
    const auto worldmapPath = contentDir / "worldmap.json";
    const auto starsPath = contentDir / "stars.json";

    const Json gatesRoot = readJson(gatesFile);
    const Json* gateList = member(gatesRoot, "gates");
    if (!gateList || !gateList->is_array()) fail(gatesFile, "gates must be an array");

    for (const Json& entry : *gateList) {
        Gate gate;
        const std::string kindText = text(entry, "kind");
        gate.kind = kindOf(kindText);
        gate.event = text(entry, "event");
        gate.world = text(entry, "world");
        gate.worldClient = text(entry, "worldClient");
        if (gate.worldClient.empty()) gate.worldClient = gate.world;
        gate.target = text(entry, "targetClient");
        if (gate.target.empty()) gate.target = text(entry, "target");
        const Json* raw = member(entry, "raw");
        if (raw) gate.package = text(*raw, "m_dataString");
        if (const auto stars = optionalNumber(entry, "stars")) {
            gate.stars = *stars;
            gate.hasStars = true;
        }
        if (const auto keys = optionalNumber(entry, "keys")) {
            gate.keys = *keys;
            gate.hasKeys = true;
        }
        map.gates_.push_back(std::move(gate));
    }

    const Json worldRoot = readJson(worldmapPath);
    const Json* worldList = member(worldRoot, "worlds");
    if (!worldList || !worldList->is_object()) fail(worldmapPath, "worlds must be an object");

    const Json starRoot = readJson(starsPath);
    if (!starRoot.is_object()) fail(starsPath, "must be an object mapping level ids to goals");

    std::map<std::string, int> levelCounts;
    for (auto it = starRoot.begin(); it != starRoot.end(); ++it) {
        const std::string& levelId = it.key();
        const auto cut = levelId.rfind('_');
        if (cut == std::string::npos) continue;
        levelCounts[levelId.substr(0, cut)] += 1;
    }

    for (auto it = worldList->begin(); it != worldList->end(); ++it) {
        const Json& entry = it.value();
        WorldInfo info;
        info.id = text(entry, "id");
        if (info.id.empty()) info.id = it.key();
        info.nameKey = text(entry, "name_key");
        info.desc = text(entry, "desc");
        info.order = number(entry, "order");
        info.difficulty = number(entry, "difficulty");
        info.unlockCost = number(entry, "unlock_cost");
        const Json* keyRequired = member(entry, "key_required");
        info.keyRequired = keyRequired && keyRequired->is_boolean() && keyRequired->get<bool>();
        if (const auto counted = levelCounts.find(info.id); counted != levelCounts.end()) {
            info.levels = counted->second;
        }
        map.worlds_.push_back(std::move(info));
    }

    std::sort(map.worlds_.begin(), map.worlds_.end(), [](const WorldInfo& a, const WorldInfo& b) {
        if (a.order != b.order) return a.order < b.order;
        return a.id < b.id;
    });

    // Display names. `content/worlds.json` is a LIST while `worldmap.json` is an object, and
    // the two are keyed differently, so this is a lookup by id rather than a merge.
    const auto namesPath = contentDir / "worlds.json";
    if (std::filesystem::is_regular_file(namesPath)) {
        const Json namesRoot = readJson(namesPath);
        const Json* list = nullptr;
        if (namesRoot.is_array()) {
            list = &namesRoot;
        } else {
            list = member(namesRoot, "worlds");
        }
        if (list && list->is_array()) {
            std::map<std::string, std::pair<std::string, std::string>> names;
            for (const Json& entry : *list) {
                const std::string id = text(entry, "id");
                if (id.empty()) continue;
                names[id] = {text(entry, "name_zh"), text(entry, "name_en")};
            }
            for (WorldInfo& world : map.worlds_) {
                const auto found = names.find(world.id);
                if (found == names.end()) continue;
                world.nameZh = found->second.first;
                world.nameEn = found->second.second;
            }
        }
    }

    // B6b: `content/worlds.json` names the 26 worlds this build ships, and it stays the first
    // source - the table below only fills what it left blank, so a hand-written name_zh can never be
    // overwritten by guessing. The original strings live under `ALM_<WORLD>` (the almanac world
    // heading) and, for a few worlds, under the bare upper-case id; `name_key` is tried last because
    // the content file invents `world.<id>.name` and the table has no such row. Still nothing and
    // `worldmap_view` prints the id, exactly as before.
    const loc::Strings strings = loc::load(contentDir.string());
    for (WorldInfo& world : map.worlds_) {
        if (!world.nameZh.empty()) continue;
        const std::string id = upper(world.id);
        std::string resolved = loc::resolve(strings, "ALM_" + id, std::string());
        if (resolved.empty()) resolved = loc::resolve(strings, id, std::string());
        if (resolved.empty() && !world.nameKey.empty())
            resolved = loc::resolve(strings, world.nameKey, std::string());
        world.nameZh = resolved;
    }

    for (std::size_t i = 0; i < map.worlds_.size(); ++i) {
        WorldInfo& world = map.worlds_[i];
        // The gate is named after the PACK world id (`rainbowmarket_stargate_start`), not
        // the client id (`lunarrainbowmarket`), so both spellings have to be accepted.
        const std::string startGate = world.id + "_stargate_start";
        for (const Gate& gate : map.gates_) {
            if (gate.worldClient != world.id && gate.world != world.id) continue;
            ++world.gateCount;
            const bool namedForWorld = gate.event == startGate ||
                                       gate.event == gate.world + "_stargate_start";
            if (gate.kind == GateKind::star && namedForWorld && gate.hasStars) {
                world.entryStars = gate.stars;
                world.hasEntryGate = true;
            }
        }
        world.starter = map.worlds_.empty() ? false : (i == 0);
        map.index_[world.id] = i;
    }

    return map;
}

const WorldInfo* WorldMap::find(const std::string& id) const {
    const auto found = index_.find(id);
    if (found == index_.end()) return nullptr;
    return &worlds_[found->second];
}

std::vector<const Gate*> WorldMap::gatesFor(const std::string& worldClient) const {
    std::vector<const Gate*> out;
    for (const Gate& gate : gates_) {
        if (gate.worldClient == worldClient || gate.world == worldClient) out.push_back(&gate);
    }
    return out;
}

int WorldMap::requiredStars(const std::string& id) const {
    const WorldInfo* world = find(id);
    if (!world) return 0;
    // The sheet's own `<world>_stargate_start` wins; `content/worldmap.json` is a
    // client-side reading, and where the two disagree the sheet is the authority.
    if (world->hasEntryGate) return world->entryStars;
    if (!world->keyRequired) return world->unlockCost;
    return 0;
}

int WorldMap::requiredKeys(const std::string& id) const {
    const WorldInfo* world = find(id);
    if (!world || !world->keyRequired) return 0;
    return world->unlockCost;
}

WorldStatus WorldMap::status(const std::string& id, int earnedStars, int keys,
                             int clearedLevels) const {
    WorldStatus status;
    status.earnedStars = earnedStars;
    status.keys = keys;
    status.clearedLevels = clearedLevels;
    const WorldInfo* world = find(id);
    if (!world) {
        status.state = WorldState::locked;
        status.reason = "unknown world";
        return status;
    }
    status.requiredStars = requiredStars(id);
    status.requiredKeys = requiredKeys(id);
    if (world->hasEntryGate) {
        status.starsSource = "sheet";
    } else if (!world->keyRequired && world->unlockCost > 0) {
        status.starsSource = "client";
    } else {
        status.starsSource = "none";
    }
    if (world->starter) {
        // C48: the client prices even the first world, so a new save would have no way in.
        status.state = clearedLevels >= world->levels && world->levels > 0 ? WorldState::completed
                                                                          : WorldState::available;
        if (status.state == WorldState::completed) status.reason.clear();
        return status;
    }
    if (earnedStars < status.requiredStars) {
        status.state = WorldState::locked;
        status.reason = "needs " + std::to_string(status.requiredStars) + " stars, has " +
                        std::to_string(earnedStars);
        return status;
    }
    if (keys < status.requiredKeys) {
        status.state = WorldState::locked;
        status.reason = "needs " + std::to_string(status.requiredKeys) + " keys, has " +
                        std::to_string(keys);
        return status;
    }
    if (world->levels > 0 && clearedLevels >= world->levels) {
        status.state = WorldState::completed;
    } else {
        status.state = WorldState::available;
    }
    return status;
}

std::size_t WorldMap::gateCount(GateKind kind) const {
    return static_cast<std::size_t>(
        std::count_if(gates_.begin(), gates_.end(), [kind](const Gate& gate) { return gate.kind == kind; }));
}

int clearedLevelsFor(const Progress& progress, const std::string& worldId) {
  int cleared = 0;
  const std::string prefix = worldId + "_";
  for (const auto& [levelId, record] : progress.levels) {
    if (record.cleared && levelId.rfind(prefix, 0) == 0) ++cleared;
  }
  return cleared;
}

}  // namespace pvz::map
