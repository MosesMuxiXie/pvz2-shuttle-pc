// S5.11: read generated/armors_from_pack.json. Every failure is a named throw rather than a
// silent empty table: an armor table that failed to load would make every zombie bare and every
// hash look plausible, which is the worst kind of green.
#include "armor.hpp"

#include "plantfood.hpp" // generatedDir(): same resolver as the other generated tables

#include <algorithm>
#include <fstream>
#include <nlohmann/json.hpp>
#include <stdexcept>

namespace pvz::engine {
namespace {

using Json = nlohmann::json;

std::string stringOr(const Json& object, const char* key, const std::string& fallback = {}) {
    const auto found = object.find(key);
    if (found == object.end() || !found->is_string()) return fallback;
    return found->get<std::string>();
}

double numberOr(const Json& object, const char* key, double fallback = 0.0) {
    const auto found = object.find(key);
    if (found == object.end() || !found->is_number()) return fallback;
    return found->get<double>();
}

bool boolOr(const Json& object, const char* key, bool fallback = false) {
    const auto found = object.find(key);
    if (found == object.end() || !found->is_boolean()) return fallback;
    return found->get<bool>();
}

std::vector<std::string> stringsOf(const Json& object, const char* key) {
    std::vector<std::string> out;
    const auto found = object.find(key);
    if (found == object.end() || !found->is_array()) return out;
    for (const Json& item : *found) {
        if (item.is_string()) out.push_back(item.get<std::string>());
    }
    return out;
}

std::vector<double> numbersOf(const Json& object, const char* key) {
    std::vector<double> out;
    const auto found = object.find(key);
    if (found == object.end() || !found->is_array()) return out;
    for (const Json& item : *found) {
        if (item.is_number()) out.push_back(item.get<double>());
    }
    return out;
}

Json readTable(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("armor table: " + path.string() + ": cannot open");
    Json document;
    try {
        input >> document;
    } catch (const std::exception& error) {
        throw std::runtime_error("armor table: " + path.string() + ": " + error.what());
    }
    if (!document.is_object()) throw std::runtime_error("armor table: " + path.string() + ": not a JSON object");
    return document;
}

ArmorSpec parseArmor(const Json& row) {
    ArmorSpec spec;
    spec.id = stringOr(row, "id");
    if (spec.id.empty()) throw std::runtime_error("armor table: armors[] entry has no id");
    spec.armorType = stringOr(row, "armorType");
    spec.objclass = stringOr(row, "objclass");
    spec.flags = stringsOf(row, "flags");
    for (const std::string& flag : spec.flags) spec.flagBits |= armorFlagBit(flag);
    spec.hitpoints = numberOr(row, "hitpoints");
    spec.hitpointsSentinel = boolOr(row, "hitpointsSentinel");
    const auto art = row.find("art");
    if (art != row.end() && art->is_object()) {
        spec.armorLayer = stringOr(*art, "armorLayer");
        spec.layers = stringsOf(*art, "layers");
        spec.layerHealth = numbersOf(*art, "layerHealth");
        spec.fireLayer = stringOr(*art, "fireLayer");
        spec.className = stringOr(*art, "className");
    }
    return spec;
}

ContentArmorBridge parseBridge(const Json& row) {
    ContentArmorBridge bridge;
    bridge.contentId = stringOr(row, "contentId");
    bridge.packZombieId = stringOr(row, "packZombieId");
    bridge.bridgeMethod = stringOr(row, "bridgeMethod");
    bridge.packArmorIds = stringsOf(row, "packArmorIds");
    bridge.contentArmature = stringsOf(row, "contentArmature");
    bridge.contentArt = stringsOf(row, "contentArt");
    bridge.contentHitpoints = numbersOf(row, "contentHitpoints");
    bridge.packHitpoints = numbersOf(row, "packHitpoints");
    bridge.match = boolOr(row, "match");
    return bridge;
}

} // namespace

unsigned armorFlagBit(std::string_view name) {
    if (name == "damageable") return kArmorDamageable;
    if (name == "invincible") return kArmorInvincible;
    if (name == "passdamage") return kArmorPassDamage;
    if (name == "droppable") return kArmorDroppable;
    if (name == "absorboverflow") return kArmorAbsorbOverflow;
    if (name == "metallic") return kArmorMetallic;
    if (name == "helm") return kArmorHelm;
    if (name == "body") return kArmorBody;
    if (name == "visibleondestroy") return kArmorVisibleOnDestroy;
    return kArmorNoFlags;
}

std::string armorFlagNames(unsigned bits) {
    static const std::pair<unsigned, const char*> names[] = {
        {kArmorDamageable, "damageable"}, {kArmorInvincible, "invincible"},
        {kArmorPassDamage, "passdamage"}, {kArmorDroppable, "droppable"},
        {kArmorAbsorbOverflow, "absorboverflow"}, {kArmorMetallic, "metallic"},
        {kArmorHelm, "helm"}, {kArmorBody, "body"},
        {kArmorVisibleOnDestroy, "visibleondestroy"},
    };
    std::string out;
    for (const auto& [bit, name] : names) {
        if ((bits & bit) == 0) continue;
        if (!out.empty()) out.push_back('+');
        out += name;
    }
    return out.empty() ? std::string{"none"} : out;
}

ArmorTable ArmorTable::load(const std::filesystem::path& path) {
    const Json document = readTable(path);
    const auto armors = document.find("armors");
    if (armors == document.end() || !armors->is_array())
        throw std::runtime_error("armor table: " + path.string() + ": no armors array");

    ArmorTable table;
    for (const Json& row : *armors) {
        if (!row.is_object()) throw std::runtime_error("armor table: " + path.string() + ": armors[] entry is not an object");
        ArmorSpec spec = parseArmor(row);
        table.specs_.emplace(spec.id, std::move(spec));
    }
    if (table.specs_.empty()) throw std::runtime_error("armor table: " + path.string() + ": the table is empty");

    const auto zombies = document.find("zombies");
    if (zombies != document.end() && zombies->is_array()) {
        for (const Json& row : *zombies) {
            if (!row.is_object()) continue;
            const std::string id = stringOr(row, "zombieId");
            if (id.empty()) continue;
            ++table.zombieRowTotal_;
            ++table.zombieRowCounts_[id];
            std::vector<std::string>& ids = table.zombieArmorIds_[id];
            for (const std::string& armorId : stringsOf(row, "armorIds")) ids.push_back(armorId);
        }
    }

    const auto comparison = document.find("contentComparison");
    if (comparison != document.end() && comparison->is_object()) {
        const auto rows = comparison->find("rows");
        if (rows != comparison->end() && rows->is_array()) {
            for (const Json& row : *rows) {
                if (!row.is_object()) continue;
                ContentArmorBridge bridge = parseBridge(row);
                if (bridge.contentId.empty()) continue;
                table.bridges_.emplace(bridge.contentId, bridge);
                table.bridgeRows_.push_back(std::move(bridge));
            }
        }
    }

    const auto counts = document.find("counts");
    if (counts != document.end() && counts->is_object()) {
        table.canonical_ = static_cast<std::size_t>(numberOr(*counts, "canonicalArmors"));
        table.embeddedOnly_ = static_cast<std::size_t>(numberOr(*counts, "embeddedOnlyArmors"));
        table.unused_ = static_cast<std::size_t>(numberOr(*counts, "unusedArmors"));
        table.withoutLayer_ = static_cast<std::size_t>(numberOr(*counts, "withoutArmorLayer"));
        table.withHitpoints_ = static_cast<std::size_t>(numberOr(*counts, "withHitpoints"));
        table.withoutHitpoints_ = static_cast<std::size_t>(numberOr(*counts, "withoutHitpoints"));
        table.danglingReferences_ = static_cast<std::size_t>(numberOr(*counts, "danglingReferences"));
        table.unusedIds_ = stringsOf(*counts, "unusedArmorIds");
        table.duplicateZombieIds_ = stringsOf(*counts, "duplicateZombieIds");
    }
    const auto dangling = document.find("dangling");
    if (dangling != document.end() && dangling->is_array()) {
        for (const Json& row : *dangling) {
            if (!row.is_object()) continue;
            const std::string id = stringOr(row, "armorId");
            if (!id.empty()) table.danglingIds_.push_back(id);
        }
    }
    if (table.unused_ == 0) table.unused_ = table.unusedIds_.size();
    return table;
}

const ArmorTable& ArmorTable::shared() {
    static const ArmorTable table = [] {
        const std::filesystem::path directory = generatedDir();
        if (directory.empty())
            throw std::runtime_error(
                "armor table: the generated directory is unknown; build with PVZ_GENERATED_DIR or set it in the environment");
        return ArmorTable::load(directory / kFileName);
    }();
    return table;
}

const ArmorSpec* ArmorTable::armorById(std::string_view id) const {
    const auto found = specs_.find(id);
    return found == specs_.end() ? nullptr : &found->second;
}

std::vector<ArmorLayer> ArmorTable::zombieArmorLayers(std::string_view zombieId) const {
    std::vector<ArmorLayer> layers;
    const auto found = zombieArmorIds_.find(zombieId);
    if (found == zombieArmorIds_.end()) return layers;
    layers.reserve(found->second.size());
    for (const std::string& armorId : found->second) {
        ArmorLayer layer;
        layer.zombieId = std::string{zombieId};
        layer.armorId = armorId;
        const ArmorSpec* spec = armorById(armorId);
        if (spec == nullptr) {
            // A dangling reference (`counts.dangling`: AngerManagement, HideLayer, InvincibleArmor).
            // There is no row to read flags or hit points from, so the layer is reported with no
            // flags and no pool: it can never block or absorb. Keeping it keeps the stack length
            // honest instead of silently shortening it.
            layers.push_back(std::move(layer));
            continue;
        }
        layer.flags = spec->flagBits;
        layer.hitpoints = spec->hitpoints;
        layer.hitpointsSentinel = spec->hitpointsSentinel;
        layer.artLayer = spec->armorLayer;
        layers.push_back(std::move(layer));
    }
    return layers;
}

std::vector<ArmorLayer> ArmorTable::contentArmorLayers(std::string_view contentId) const {
    const ContentArmorBridge* bridge = contentBridge(contentId);
    if (bridge == nullptr || bridge->packArmorIds.empty()) return {};
    std::vector<ArmorLayer> layers;
    layers.reserve(bridge->packArmorIds.size());
    for (const std::string& armorId : bridge->packArmorIds) {
        ArmorLayer layer;
        layer.zombieId = bridge->packZombieId;
        layer.armorId = armorId;
        const ArmorSpec* spec = armorById(armorId);
        if (spec != nullptr) {
            layer.flags = spec->flagBits;
            layer.hitpoints = spec->hitpoints;
            layer.hitpointsSentinel = spec->hitpointsSentinel;
            layer.artLayer = spec->armorLayer;
        }
        layers.push_back(std::move(layer));
    }
    return layers;
}

const ContentArmorBridge* ArmorTable::contentBridge(std::string_view contentId) const {
    const auto found = bridges_.find(contentId);
    return found == bridges_.end() ? nullptr : &found->second;
}

std::size_t ArmorTable::zombieRowCount(std::string_view zombieId) const {
    const auto found = zombieRowCounts_.find(zombieId);
    return found == zombieRowCounts_.end() ? 0 : found->second;
}

} // namespace pvz::engine
