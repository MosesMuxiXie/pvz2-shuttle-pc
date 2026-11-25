#include "content/loader.hpp"

#include <fstream>
#include <limits>
#include <sstream>
#include <utility>

#include <nlohmann/json.hpp>

namespace pvz::content {
namespace {

using json = nlohmann::json;

[[noreturn]] void fail(const std::string& origin, const std::string& where, const std::string& what) {
    throw LoadError("content pack " + origin + ": " + where + ": " + what);
}

const json& requireMember(const json& object, const char* key, const std::string& origin,
                          const std::string& where) {
    const auto it = object.find(key);
    if (it == object.end()) {
        fail(origin, where, std::string("missing field \"") + key + "\"");
    }
    return *it;
}

std::string requireString(const json& object, const char* key, const std::string& origin,
                          const std::string& where) {
    const json& value = requireMember(object, key, origin, where);
    if (!value.is_string()) {
        fail(origin, where, std::string("field \"") + key + "\" must be a string");
    }
    const std::string text = value.get<std::string>();
    if (text.empty()) {
        fail(origin, where, std::string("field \"") + key + "\" must not be empty");
    }
    return text;
}

std::string optionalString(const json& object, const char* key, const std::string& origin,
                           const std::string& where) {
    const auto it = object.find(key);
    if (it == object.end() || it->is_null()) {
        return {};
    }
    if (!it->is_string()) {
        fail(origin, where, std::string("field \"") + key + "\" must be a string");
    }
    return it->get<std::string>();
}

std::optional<double> optionalNumber(const json& object, const char* key, const std::string& origin,
                                     const std::string& where) {
    const auto it = object.find(key);
    if (it == object.end() || it->is_null()) {
        return std::nullopt;
    }
    if (!it->is_number()) {
        fail(origin, where, std::string("field \"") + key + "\" must be a number");
    }
    return it->get<double>();
}

std::optional<bool> optionalBool(const json& object, const char* key, const std::string& origin,
                                 const std::string& where) {
    const auto it = object.find(key);
    if (it == object.end() || it->is_null()) {
        return std::nullopt;
    }
    if (!it->is_boolean()) {
        fail(origin, where, std::string("field \"") + key + "\" must be a boolean");
    }
    return it->get<bool>();
}

std::vector<std::string> stringList(const json& object, const char* key, const std::string& origin,
                                    const std::string& where) {
    std::vector<std::string> out;
    const auto it = object.find(key);
    if (it == object.end() || it->is_null()) {
        return out;
    }
    if (!it->is_array()) {
        fail(origin, where, std::string("field \"") + key + "\" must be an array");
    }
    for (const json& item : *it) {
        if (!item.is_string()) {
            fail(origin, where, std::string("field \"") + key + "\" must hold strings");
        }
        out.push_back(item.get<std::string>());
    }
    return out;
}

Point requirePoint(const json& value, const std::string& origin, const std::string& where) {
    if (!value.is_object()) {
        fail(origin, where, "\"point\" must be an object");
    }
    Point point;
    point.x = optionalNumber(value, "x", origin, where).value_or(0.0);
    point.y = optionalNumber(value, "y", origin, where).value_or(0.0);
    return point;
}

Rect rectOf(const json& object, const char* key, const std::string& origin, const std::string& where) {
    const json& value = requireMember(object, key, origin, where);
    if (!value.is_object()) {
        fail(origin, where, std::string("field \"") + key + "\" must be an object");
    }
    Rect rect;
    rect.x = optionalNumber(value, "x", origin, where).value_or(0.0);
    rect.y = optionalNumber(value, "y", origin, where).value_or(0.0);
    rect.width = optionalNumber(value, "width", origin, where).value_or(0.0);
    rect.height = optionalNumber(value, "height", origin, where).value_or(0.0);
    return rect;
}

Rtid rtidOf(const json& value, const std::string& origin, const std::string& where) {
    if (!value.is_object()) {
        fail(origin, where, "\"RTID\" must be an object");
    }
    Rtid rtid;
    rtid.name = requireString(value, "name", origin, where);
    rtid.sheet = optionalString(value, "sheet", origin, where);
    rtid.nothing = optionalBool(value, "nothing", origin, where).value_or(false);
    return rtid;
}

ActionKind kindOf(const std::string& text, const std::string& origin, const std::string& where) {
    for (ActionKind kind : kActionKinds) {
        if (actionKindName(kind) == text) {
            return kind;
        }
    }
    // Unknown kinds are data, not corruption: the sheet grows new ones between
    // builds, and the engine reports them instead of refusing to start.
    (void)origin;
    (void)where;
    return ActionKind::unknown;
}

Action actionOf(const json& value, const std::string& origin, const std::string& where) {
    if (!value.is_object()) {
        fail(origin, where, "action must be an object");
    }
    Action action;
    action.rawType = optionalString(value, "rawType", origin, where);
    const auto kindIt = value.find("kind");
    if (kindIt == value.end() || !kindIt->is_string() || kindIt->get<std::string>().empty()) {
        fail(origin, where, "action is missing \"kind\"");
    }
    action.kind = kindOf(kindIt->get<std::string>(), origin, where);
    if (const auto it = value.find("projectile"); it != value.end() && !it->is_null()) {
        action.projectile = rtidOf(*it, origin, where);
    }
    action.trigger = optionalString(value, "trigger", origin, where);
    action.explode = optionalString(value, "explode", origin, where);
    action.launchSound = optionalString(value, "launchSound", origin, where);
    action.damage = optionalNumber(value, "damage", origin, where);
    action.splashDamage = optionalNumber(value, "splashDamage", origin, where);
    action.cooldownMin = optionalNumber(value, "cooldownMin", origin, where);
    action.cooldownMax = optionalNumber(value, "cooldownMax", origin, where);
    action.initialMin = optionalNumber(value, "initialMin", origin, where);
    action.initialMax = optionalNumber(value, "initialMax", origin, where);
    action.explodeRadius = optionalNumber(value, "explodeRadius", origin, where);
    action.chillDuration = optionalNumber(value, "chillDuration", origin, where);
    action.freezeDuration = optionalNumber(value, "freezeDuration", origin, where);
    action.stunDuration = optionalNumber(value, "stunDuration", origin, where);
    action.pushback = optionalNumber(value, "pushback", origin, where);
    action.needEating = optionalNumber(value, "needEating", origin, where);
    action.burns = optionalBool(value, "burns", origin, where);
    action.dieAfterExplode = optionalBool(value, "dieAfterExplode", origin, where);
    action.secondary = optionalBool(value, "secondary", origin, where);
    if (const auto it = value.find("spawnOffset"); it != value.end() && !it->is_null()) {
        action.spawnOffset = requirePoint(*it, origin, where);
    }
    if (value.contains("triggerRect")) {
        action.triggerRect = rectOf(value, "triggerRect", origin, where);
    }
    return action;
}

std::vector<Action> actionsOf(const json& record, const std::string& origin, const std::string& where) {
    std::vector<Action> out;
    const auto it = record.find("actions");
    if (it == record.end() || it->is_null()) {
        return out;
    }
    if (!it->is_array()) {
        fail(origin, where, "field \"actions\" must be an array");
    }
    for (const json& entry : *it) {
        out.push_back(actionOf(entry, origin, where));
    }
    return out;
}

std::vector<ActionRef> actionRefsOf(const json& record, const std::string& origin,
                                    const std::string& where) {
    std::vector<ActionRef> out;
    const auto it = record.find("actionRefs");
    if (it == record.end() || it->is_null()) {
        return out;
    }
    if (!it->is_array()) {
        fail(origin, where, "field \"actionRefs\" must be an array");
    }
    for (const json& entry : *it) {
        ActionRef ref;
        ref.name = requireString(entry, "name", origin, where);
        ref.sheet = optionalString(entry, "sheet", origin, where);
        ref.resolved = optionalBool(entry, "resolved", origin, where).value_or(false);
        out.push_back(std::move(ref));
    }
    return out;
}

PropsSource sourceOf(const json& record, const std::string& origin, const std::string& where) {
    const std::string text = optionalString(record, "propsSource", origin, where);
    if (text.empty() || text == "none") {
        return PropsSource::none;
    }
    if (text == "static") {
        return PropsSource::staticSheet;
    }
    if (text == "external") {
        return PropsSource::external;
    }
    if (text == "missing") {
        return PropsSource::missing;
    }
    fail(origin, where, "unknown propsSource \"" + text + "\"");
}

PlantType plantOf(const json& value, const std::string& origin) {
    if (!value.is_object()) {
        fail(origin, "plants[]", "plant entry must be an object");
    }
    const std::string id = requireString(value, "id", origin, "plants[]");
    const std::string where = "plant \"" + id + "\"";
    PlantType plant;
    plant.id = id;
    plant.framework = optionalString(value, "framework", origin, where);
    if (const auto it = value.find("properties"); it != value.end() && !it->is_null()) {
        plant.properties = rtidOf(*it, origin, where);
    }
    plant.propsSource = sourceOf(value, origin, where);
    plant.popAnim = optionalString(value, "popAnim", origin, where);
    plant.animRig = optionalString(value, "animRig", origin, where);
    plant.homeWorld = optionalString(value, "homeWorld", origin, where);
    plant.integerId = static_cast<int>(optionalNumber(value, "integerId", origin, where).value_or(0.0));
    plant.families = stringList(value, "families", origin, where);
    plant.sunProducer = optionalBool(value, "sunProducer", origin, where).value_or(false);
    plant.almanacBackdrop = optionalString(value, "almanacBackdrop", origin, where);
    plant.resourceGroups = stringList(value, "resourceGroups", origin, where);
    plant.cost = optionalNumber(value, "cost", origin, where);
    plant.beghouledCost = optionalNumber(value, "beghouledCost", origin, where);
    plant.hitpoints = optionalNumber(value, "hitpoints", origin, where);
    plant.packetCooldown = optionalNumber(value, "packetCooldown", origin, where);
    plant.startingCooldown = optionalNumber(value, "startingCooldown", origin, where);
    plant.plantFoodDuration = optionalNumber(value, "plantFoodDuration", origin, where);
    plant.plantFoodPlayCount = optionalNumber(value, "plantFoodPlayCount", origin, where);
    plant.gridType = optionalString(value, "gridType", origin, where);
    plant.height = optionalString(value, "height", origin, where);
    plant.actions = actionsOf(value, origin, where);
    return plant;
}

ZombieType zombieOf(const json& value, const std::string& origin) {
    if (!value.is_object()) {
        fail(origin, "zombies[]", "zombie entry must be an object");
    }
    const std::string id = requireString(value, "id", origin, "zombies[]");
    const std::string where = "zombie \"" + id + "\"";
    ZombieType zombie;
    zombie.id = id;
    zombie.className = optionalString(value, "class", origin, where);
    if (const auto it = value.find("properties"); it != value.end() && !it->is_null()) {
        zombie.properties = rtidOf(*it, origin, where);
    }
    zombie.propsSource = sourceOf(value, origin, where);
    zombie.popAnim = optionalString(value, "popAnim", origin, where);
    zombie.animRig = optionalString(value, "animRig", origin, where);
    zombie.homeWorld = optionalString(value, "homeWorld", origin, where);
    zombie.integerId =
        static_cast<int>(optionalNumber(value, "integerId", origin, where).value_or(0.0));
    zombie.isBasic = optionalBool(value, "isBasic", origin, where).value_or(false);
    zombie.resourceGroups = stringList(value, "resourceGroups", origin, where);
    zombie.hitpoints = optionalNumber(value, "hitpoints", origin, where);
    zombie.speed = optionalNumber(value, "speed", origin, where);
    zombie.speedVariance = optionalNumber(value, "speedVariance", origin, where);
    zombie.eatDps = optionalNumber(value, "eatDps", origin, where);
    zombie.weight = optionalNumber(value, "weight", origin, where);
    zombie.wavePointCost = optionalNumber(value, "wavePointCost", origin, where);
    zombie.cost = optionalNumber(value, "cost", origin, where);
    if (value.contains("hitRect")) {
        zombie.hitRect = rectOf(value, "hitRect", origin, where);
    }
    if (value.contains("attackRect")) {
        zombie.attackRect = rectOf(value, "attackRect", origin, where);
    }
    if (const auto it = value.find("art"); it != value.end() && it->is_object()) {
        if (it->contains("ArtCenter")) {
            zombie.artCenter = requirePoint((*it)["ArtCenter"], origin, where);
        }
        if (it->contains("ShadowOffset")) {
            zombie.shadowOffset = requirePoint((*it)["ShadowOffset"], origin, where);
        }
    }
    zombie.actions = actionsOf(value, origin, where);
    zombie.actionRefs = actionRefsOf(value, origin, where);
    return zombie;
}

std::string pathText(const std::filesystem::path& path) {
    const auto text = path.u8string();
    return std::string(text.begin(), text.end());
}

std::string readFile(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) {
        throw LoadError("content pack: cannot open " + pathText(path));
    }
    std::ostringstream buffer;
    buffer << stream.rdbuf();
    return buffer.str();
}

}  // namespace

std::string_view actionKindName(ActionKind kind) {
    switch (kind) {
        case ActionKind::projectile:
            return "projectile";
        case ActionKind::sun:
            return "sun";
        case ActionKind::explode:
            return "explode";
        case ActionKind::special:
            return "special";
        case ActionKind::plantfood:
            return "plantfood";
        case ActionKind::manual:
            return "manual";
        case ActionKind::unknown:
            break;
    }
    return "unknown";
}

std::string_view propsSourceName(PropsSource source) {
    switch (source) {
        case PropsSource::none:
            return "none";
        case PropsSource::staticSheet:
            return "static";
        case PropsSource::external:
            return "external";
        case PropsSource::missing:
            return "missing";
    }
    return "missing";
}

void ContentPack::index() {
    plantIndex_.clear();
    zombieIndex_.clear();
    plantDuplicates.clear();
    zombieDuplicates.clear();
    plantIndex_.reserve(plants.size());
    zombieIndex_.reserve(zombies.size());
    for (std::size_t i = 0; i < plants.size(); ++i) {
        const auto inserted = plantIndex_.emplace(plants[i].id, i);
        if (!inserted.second) {
            plantDuplicates.push_back(plants[i].id);
        }
    }
    for (std::size_t i = 0; i < zombies.size(); ++i) {
        const auto inserted = zombieIndex_.emplace(zombies[i].id, i);
        if (!inserted.second) {
            zombieDuplicates.push_back(zombies[i].id);
        }
    }
    indexed_ = true;
}

const PlantType* ContentPack::findPlant(std::string_view id) const {
    if (!indexed_) {
        return nullptr;
    }
    const auto it = plantIndex_.find(std::string(id));
    return it == plantIndex_.end() ? nullptr : &plants[it->second];
}

const ZombieType* ContentPack::findZombie(std::string_view id) const {
    if (!indexed_) {
        return nullptr;
    }
    const auto it = zombieIndex_.find(std::string(id));
    return it == zombieIndex_.end() ? nullptr : &zombies[it->second];
}

ContentPack parseContentPack(const std::string& text, const std::string& origin) {
    json root;
    try {
        root = json::parse(text);
    } catch (const json::parse_error& error) {
        throw LoadError("content pack " + origin + ": invalid JSON: " + error.what());
    }
    if (!root.is_object()) {
        fail(origin, "root", "must be a JSON object");
    }
    ContentPack pack;
    pack.format = static_cast<int>(optionalNumber(root, "format", origin, "root").value_or(0.0));
    if (pack.format != kPackFormat) {
        fail(origin, "root", "unsupported format " + std::to_string(pack.format) + " (want " +
                                 std::to_string(kPackFormat) + ")");
    }
    pack.generated = optionalString(root, "generated", origin, "root");

    const json& plants = requireMember(root, "plants", origin, "root");
    if (!plants.is_array()) {
        fail(origin, "root", "field \"plants\" must be an array");
    }
    pack.plants.reserve(plants.size());
    for (const json& entry : plants) {
        pack.plants.push_back(plantOf(entry, origin));
    }

    const json& zombies = requireMember(root, "zombies", origin, "root");
    if (!zombies.is_array()) {
        fail(origin, "root", "field \"zombies\" must be an array");
    }
    pack.zombies.reserve(zombies.size());
    for (const json& entry : zombies) {
        pack.zombies.push_back(zombieOf(entry, origin));
    }

    pack.index();
    return pack;
}

ContentPack loadContentPack(const std::filesystem::path& path) {
    return parseContentPack(readFile(path), pathText(path));
}

}  // namespace pvz::content
