#include "projectile_table.hpp"
#include "plantfood.hpp" // generatedDir(): one shared walk-up probe for every generated table
#include "../catalog.hpp" // pathUtf8
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

Json readTable(const std::filesystem::path& file) {
    std::ifstream in(file);
    if (!in) throw std::runtime_error("projectile table: " + pathUtf8(file) + ": cannot open");
    Json doc;
    try {
        in >> doc;
    } catch (const std::exception& error) {
        throw std::runtime_error("projectile table: " + pathUtf8(file) + ": " + error.what());
    }
    return doc;
}

Trajectory trajectoryOf(const std::string& name) {
    if (name == "straight") return Trajectory::straight;
    if (name == "arc") return Trajectory::arc;
    if (name == "drop") return Trajectory::drop;
    if (name == "static") return Trajectory::stationary; // `static` is a C++ keyword
    return Trajectory::unknown;
}

// 2147483647 is the pack's "sentinel, not a number" marker (7 rows carry it in baseDamage).
constexpr double kIntSentinel = 2147483647.0;

ProjectileSpec parseSpec(const Json& json) {
    ProjectileSpec spec;
    spec.id = stringOr(json, "id");
    spec.pkg = stringOr(json, "pkg");
    spec.objclass = stringOr(json, "objclass");
    spec.trajectory = trajectoryOf(stringOr(json, "trajectory"));

    if (const auto speed = json.find("speed"); speed != json.end() && speed->is_object()) {
        spec.speedCols = numberOr(*speed, "colsPerSec").value_or(0.0);
    }
    if (const auto radius = json.find("hitRadius"); radius != json.end() && radius->is_object()) {
        spec.hitRadiusCols = numberOr(*radius, "cols").value_or(0.0);
    }
    const bool sentinel = json.value("baseDamageSentinel", false);
    spec.damageSentinel = sentinel;
    if (!sentinel) {
        if (const auto damage = numberOr(json, "baseDamage");
            damage && *damage > 0.0 && *damage < kIntSentinel) {
            spec.damage = *damage;
            spec.hasDamage = true;
        }
    }
    if (const auto splash = json.find("splash"); splash != json.end() && splash->is_object()) {
        const double damage = numberOr(*splash, "damage").value_or(0.0);
        if (damage > 0.0 && damage < kIntSentinel) {
            spec.hasSplash = true;
            spec.splashDamage = damage;
            spec.splashRadiusCells = numberOr(*splash, "radius").value_or(0.0);
        }
    }
    if (const auto pierce = json.find("pierce"); pierce != json.end() && pierce->is_object()) {
        spec.hasPierce = true;
        spec.pierceHits = static_cast<int>(numberOr(*pierce, "maxTargetHits").value_or(0.0));
    }
    if (const auto velocity = json.find("velocity"); velocity != json.end() && velocity->is_object()) {
        if (const auto z = velocity->find("z"); z != velocity->end() && z->is_object()) {
            spec.vz = numberOr(*z, "max").value_or(0.0);
        }
    }
    if (const auto variants = json.find("variants"); variants != json.end() && variants->is_array()) {
        for (const auto& variant : *variants) {
            if (!variant.is_object()) continue;
            const std::string pkg = stringOr(variant, "pkg");
            if (!pkg.empty()) spec.variantPkgs.push_back(pkg);
        }
    }
    return spec;
}

} // namespace

const char* trajectoryName(Trajectory trajectory) {
    switch (trajectory) {
    case Trajectory::straight: return "straight";
    case Trajectory::arc: return "arc";
    case Trajectory::drop: return "drop";
    case Trajectory::stationary: return "static";
    case Trajectory::unknown: break;
    }
    return "unknown";
}

bool ProjectileSpec::hasVariantFor(std::string_view query) const {
    if (query.empty()) return false;
    for (const auto& variantPkg : variantPkgs) {
        if (variantPkg == query) return true;
    }
    return false;
}

ProjectileTable ProjectileTable::load(const std::filesystem::path& path) {
    const Json doc = readTable(path);
    const auto rows = doc.find("projectiles");
    if (rows == doc.end() || !rows->is_array()) {
        throw std::runtime_error("projectile table: " + pathUtf8(path) + ": no projectiles array");
    }
    ProjectileTable table;
    for (const auto& row : *rows) {
        if (!row.is_object()) {
            throw std::runtime_error("projectile table: " + pathUtf8(path) + ": entry is not an object");
        }
        ProjectileSpec spec = parseSpec(row);
        if (!spec.usable()) {
            throw std::runtime_error("projectile table: " + pathUtf8(path) + ": entry has no id");
        }
        // The shipped table is 602 rows over 601 ids (`MangosteenPlantFoodDefault` appears twice),
        // so counters must follow the unique map, not the row stream: otherwise `withSplash()`
        // can exceed `size()` and every "how many have splash" report is quietly wrong.
        std::string id = spec.id;
        const auto inserted = table.specs_.find(id);
        const bool first = inserted == table.specs_.end();
        if (first && spec.hasSplash) ++table.withSplash_;
        if (first && spec.hasPierce) ++table.withPierce_;
        table.specs_.insert_or_assign(std::move(id), std::move(spec));
    }
    table.rows_ = rows->size();
    if (table.specs_.empty()) {
        throw std::runtime_error("projectile table: " + pathUtf8(path) + ": table is empty");
    }
    return table;
}

const ProjectileTable& ProjectileTable::shared() {
    static const ProjectileTable table = [] {
        const std::filesystem::path dir = generatedDir();
        if (dir.empty()) {
            throw std::runtime_error("projectile table: the generated directory is unknown; build with "
                                     "PVZ_GENERATED_DIR or set it in the environment");
        }
        return ProjectileTable::load(dir / kFileName);
    }();
    return table;
}

const ProjectileSpec* ProjectileTable::find(std::string_view id) const {
    if (id.empty()) return nullptr;
    const auto it = specs_.find(id);
    return it == specs_.end() ? nullptr : &it->second;
}

std::size_t ProjectileTable::trajectoryCount(Trajectory trajectory) const {
    std::size_t count = 0;
    for (const auto& entry : specs_) {
        if (entry.second.trajectory == trajectory) ++count;
    }
    return count;
}

} // namespace pvz::engine
