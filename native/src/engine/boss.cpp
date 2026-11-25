#include "boss.hpp"
#include "plantfood.hpp" // generatedDir(): the same walk-up resolution the other tables use
#include <algorithm>
#include <fstream>
#include <stdexcept>
#include <utility>

namespace pvz::engine {
namespace {

std::string stringOr(const Json& object, const char* key) {
    const auto it = object.find(key);
    if (it == object.end() || !it->is_string()) return {};
    return it->get<std::string>();
}

std::optional<double> numberOr(const Json& object, const char* key) {
    const auto it = object.find(key);
    if (it == object.end() || !it->is_number()) return std::nullopt;
    return it->get<double>();
}

std::optional<int> intOr(const Json& object, const char* key) {
    const auto it = object.find(key);
    if (it == object.end() || !it->is_number()) return std::nullopt;
    return static_cast<int>(it->get<double>());
}

Json readTable(const std::filesystem::path& file) {
    std::ifstream in(file);
    if (!in) throw std::runtime_error("boss table: " + pathUtf8(file) + ": cannot open");
    Json doc;
    try {
        in >> doc;
    } catch (const std::exception& error) {
        throw std::runtime_error("boss table: " + pathUtf8(file) + ": " + error.what());
    }
    return doc;
}

BossStageAction parseAction(const Json& json) {
    BossStageAction action;
    action.type = stringOr(json, "type");
    action.alias = stringOr(json, "alias");
    action.rtid = stringOr(json, "rtid");
    const auto fields = json.find("fields");
    if (fields == json.end() || !fields->is_object()) return action;
    action.fields = *fields;
    const auto minColumn = fields->find("FireMinColumn");
    const auto maxColumn = fields->find("FireMaxColumn");
    if (minColumn == fields->end() || !minColumn->is_number() || maxColumn == fields->end() ||
        !maxColumn->is_number()) {
        return action; // breath/imp/speaker shapes: kept, counted as unwired
    }
    action.fire = true;
    action.fireMinColumn = static_cast<int>(minColumn->get<double>());
    action.fireMaxColumn = static_cast<int>(maxColumn->get<double>());
    action.fireRowRange = intOr(*fields, "FireRowRange").value_or(1);
    if (action.fireRowRange < 0) action.fireRowRange = 0;
    action.fireSpeed = numberOr(*fields, "FireRocketSpeed").value_or(0.0);
    action.fireHitTime = numberOr(*fields, "FireRocketHitTime").value_or(0.0);
    return action;
}

BossStage parseStage(const Json& json) {
    BossStage stage;
    stage.index = intOr(json, "index").value_or(0);
    stage.hitPoints = numberOr(json, "hitPoints").value_or(0.0);
    stage.stunSeconds = numberOr(json, "stunSeconds").value_or(0.0);
    stage.animRate = numberOr(json, "animRate").value_or(1.0);
    const auto idle = json.find("idleSeconds");
    if (idle != json.end() && idle->is_object()) {
        stage.idleMinSeconds = numberOr(*idle, "min").value_or(0.0);
        stage.idleMaxSeconds = numberOr(*idle, "max").value_or(stage.idleMinSeconds);
        if (stage.idleMaxSeconds < stage.idleMinSeconds) stage.idleMaxSeconds = stage.idleMinSeconds;
    }
    const auto actions = json.find("actions");
    if (actions != json.end() && actions->is_array()) {
        for (const auto& entry : *actions) {
            if (entry.is_object()) stage.actions.push_back(parseAction(entry));
        }
    }
    return stage;
}

BossSpawnPoint parseSpawn(const Json& json) {
    BossSpawnPoint spawn;
    if (!json.is_object()) return spawn;
    spawn.gridX = intOr(json, "gridX").value_or(0);
    spawn.gridY = intOr(json, "gridY").value_or(0);
    spawn.reservedColumns = intOr(json, "reservedColumns").value_or(0);
    spawn.deathRow = intOr(json, "deathRow").value_or(0);
    spawn.deathColumn = intOr(json, "deathColumn").value_or(0);
    return spawn;
}

BossDefinition parseBoss(const Json& json) {
    BossDefinition boss;
    boss.id = stringOr(json, "id");
    boss.className = stringOr(json, "className");
    boss.propsName = stringOr(json, "propsName");
    boss.popAnim = stringOr(json, "popAnim");
    boss.animRig = stringOr(json, "animRig");
    boss.world = stringOr(json, "world");
    boss.stageCount = intOr(json, "stageCount").value_or(0);
    const auto worlds = json.find("worlds");
    if (worlds != json.end() && worlds->is_array()) {
        for (const auto& entry : *worlds) {
            if (entry.is_string()) boss.worlds.push_back(entry.get<std::string>());
        }
    }
    if (boss.worlds.empty() && !boss.world.empty()) boss.worlds.push_back(boss.world);
    const auto placements = json.find("placements");
    if (placements != json.end() && placements->is_array()) {
        for (const auto& entry : *placements) {
            if (!entry.is_object()) continue;
            const std::string world = stringOr(entry, "world");
            if (world.empty()) continue;
            if (std::find(boss.worlds.begin(), boss.worlds.end(), world) == boss.worlds.end()) {
                boss.worlds.push_back(world);
            }
        }
    }
    const auto spawn = json.find("spawn");
    if (spawn != json.end()) boss.spawn = parseSpawn(*spawn);
    const auto stages = json.find("stages");
    if (stages != json.end() && stages->is_array()) {
        for (const auto& entry : *stages) {
            if (entry.is_object()) boss.stages.push_back(parseStage(entry));
        }
    }
    if (boss.stageCount <= 0) boss.stageCount = static_cast<int>(boss.stages.size());
    return boss;
}

} // namespace

std::size_t BossStage::fireActions() const {
    std::size_t count = 0;
    for (const auto& action : actions) {
        if (action.fire) ++count;
    }
    return count;
}

double BossDefinition::totalHitPoints() const {
    double total = 0;
    for (const auto& stage : stages) total += stage.hitPoints;
    return total;
}

bool BossDefinition::claimsWorld(const std::string& name) const {
    return !name.empty() && std::find(worlds.begin(), worlds.end(), name) != worlds.end();
}

BossTable BossTable::load(const std::filesystem::path& file) {
    const Json doc = readTable(file);
    const auto bosses = doc.find("bosses");
    if (bosses == doc.end() || !bosses->is_array()) {
        throw std::runtime_error("boss table: " + pathUtf8(file) + ": no 'bosses' array");
    }
    BossTable table;
    for (const auto& entry : *bosses) {
        if (!entry.is_object()) {
            throw std::runtime_error("boss table: " + pathUtf8(file) + ": an entry is not an object");
        }
        BossDefinition boss = parseBoss(entry);
        if (boss.id.empty()) {
            throw std::runtime_error("boss table: " + pathUtf8(file) + ": an entry has no id");
        }
        table.bosses_.push_back(std::move(boss));
    }
    if (table.bosses_.empty()) throw std::runtime_error("boss table: " + pathUtf8(file) + ": table is empty");
    return table;
}

const BossTable& BossTable::shared() {
    static const BossTable table = [] {
        const std::filesystem::path dir = generatedDir();
        if (dir.empty()) {
            throw std::runtime_error("boss table: the generated directory is unknown; build with "
                                     "PVZ_GENERATED_DIR or set it in the environment");
        }
        return BossTable::load(dir / kFileName);
    }();
    return table;
}

std::size_t BossTable::usable() const {
    std::size_t count = 0;
    for (const auto& boss : bosses_) {
        if (boss.usable()) ++count;
    }
    return count;
}

std::size_t BossTable::stageTotal() const {
    std::size_t total = 0;
    for (const auto& boss : bosses_) total += boss.stages.size();
    return total;
}

std::size_t BossTable::fireActionTotal() const {
    std::size_t total = 0;
    for (const auto& boss : bosses_) {
        for (const auto& stage : boss.stages) total += stage.fireActions();
    }
    return total;
}

const BossDefinition* BossTable::find(const std::string& id) const {
    if (id.empty()) return nullptr;
    for (const auto& boss : bosses_) {
        if (boss.id == id) return &boss;
    }
    return nullptr;
}

std::size_t BossTable::candidatesForWorld(const std::string& world) const {
    std::size_t count = 0;
    for (const auto& boss : bosses_) {
        if (boss.usable() && boss.claimsWorld(world)) ++count;
    }
    return count;
}

const BossDefinition* BossTable::forWorld(const std::string& world) const {
    if (world.empty()) return nullptr;
    std::vector<const BossDefinition*> candidates;
    for (const auto& boss : bosses_) {
        if (boss.usable() && boss.claimsWorld(world)) candidates.push_back(&boss);
    }
    if (candidates.empty()) return nullptr;
    // A world can be claimed by several sheets (eight variants claim `chinesegarden`); the
    // pick has to be stable across builds. Primary world first, then the shortest stage
    // list - the simplest boss that the world's data backs - then the id as the tie-break.
    std::sort(candidates.begin(), candidates.end(), [&world](const BossDefinition* left, const BossDefinition* right) {
        const bool leftPrimary = left->world == world;
        const bool rightPrimary = right->world == world;
        if (leftPrimary != rightPrimary) return leftPrimary;
        if (left->stages.size() != right->stages.size()) return left->stages.size() < right->stages.size();
        return left->id < right->id;
    });
    return candidates.front();
}

BossSelection selectBoss(const Catalog& catalog, const LevelDefinition& level, const BossTable& table) {
    BossSelection selection;
    const Json& extra = level.extra;
    if (extra.is_object()) {
        const auto marker = extra.find("boss_zombie");
        if (marker != extra.end() && marker->is_string()) selection.marker = marker->get<std::string>();
        if (selection.marker.empty()) {
            // `extra.boss` is a boolean on the 71 boss levels, but a future sheet may put the
            // name there; only a string is a marker.
            const auto alt = extra.find("boss");
            if (alt != extra.end() && alt->is_string()) selection.marker = alt->get<std::string>();
        }
    }
    if (selection.marker.empty()) return selection;
    if (selection.marker != "zomboss") {
        // A non-`zomboss` marker names a zombie type (`gargantuar` on 3 levels). Refusing an
        // unknown type here is what turns a level into `boss_unavailable` instead of a crash.
        const bool known = catalog.zombies.count(selection.marker) > 0 ||
                           (catalog.rules != nullptr && catalog.rules->findZombie(selection.marker) != nullptr);
        if (!known) return selection;
        selection.kind = BossSelection::Kind::gargantuar;
        selection.zombieType = selection.marker;
        return selection;
    }
    selection.candidates = table.candidatesForWorld(level.world);
    const BossDefinition* boss = table.forWorld(level.world);
    if (boss == nullptr) return selection;
    selection.kind = BossSelection::Kind::mechanic;
    selection.boss = boss;
    return selection;
}

std::string_view bossSelectionKindName(BossSelection::Kind kind) {
    switch (kind) {
    case BossSelection::Kind::mechanic:
        return "mechanic";
    case BossSelection::Kind::gargantuar:
        return "gargantuar";
    case BossSelection::Kind::none:
        break;
    }
    return "none";
}

} // namespace pvz::engine
