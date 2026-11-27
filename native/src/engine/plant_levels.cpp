// B1 (T90): read the generated plant ladder. Same shape as the other generated tables - a named
// throw rather than a silent half-load - with one deliberate difference: a tree that has no
// generated directory answers an EMPTY table instead of throwing, because every plant construction
// consults this file and a hand-built catalog in a unit test must not depend on the shipped tree.
#include "plant_levels.hpp"

#include "plantfood.hpp" // generatedDir(): the same resolver the other generated tables use

#include <algorithm>
#include <fstream>
#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>
#include <utility>

namespace pvz::engine {
namespace {

using Json = nlohmann::json;

[[noreturn]] void fail(const std::filesystem::path& path, const std::string& reason) {
    throw std::runtime_error("plant level table: " + path.string() + ": " + reason);
}

/// The `ActionDamageNormal` column this row carries.
///
/// The sheet spells a repeated `Name` as `Name@<SubType>`, and the peashooter carries both
/// `ActionDamageNormal@0` and `@2`. `obb_build_content.py`'s flatten keeps the LAST entry, so the
/// column that reproduces today's pack number is the greatest suffix. A row with a single column
/// keeps the bare name.
std::string damageColumn(const std::map<std::string, double>& stats) {
    constexpr const char* kBare = "ActionDamageNormal";
    if (stats.count(kBare) != 0) return kBare;
    std::string best;
    long bestSuffix = -1;
    const std::string prefix = std::string(kBare) + "@";
    for (const auto& [name, unused] : stats) {
        (void)unused;
        if (name.rfind(prefix, 0) != 0) continue;
        const std::string tail = name.substr(prefix.size());
        if (tail.empty()) continue;
        long suffix = 0;
        bool numeric = true;
        for (const char digit : tail) {
            if (digit < '0' || digit > '9') {
                numeric = false;
                break;
            }
            suffix = suffix * 10 + (digit - '0');
        }
        if (!numeric) continue;
        if (suffix > bestSuffix) {
            bestSuffix = suffix;
            best = name;
        }
    }
    return best;
}

} // namespace

int PlantLevelRow::clamp(int level) const { return std::clamp(level, 1, std::max(levelCount, 1)); }

const std::map<std::string, double>* PlantLevelRow::at(int level) const {
    if (levels.empty()) return nullptr;
    const int index = clamp(level) - 1;
    return &levels[static_cast<std::size_t>(index)];
}

std::optional<double> PlantLevelRow::value(const std::string& stat, int level) const {
    const std::map<std::string, double>* stats = at(level);
    if (stats == nullptr) return std::nullopt;
    const auto found = stats->find(stat);
    if (found == stats->end()) return std::nullopt;
    return found->second;
}

PlantLevelTable PlantLevelTable::load(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) fail(path, "cannot open");
    Json json;
    try {
        input >> json;
    } catch (const std::exception& error) {
        fail(path, error.what());
    }
    if (!json.is_object()) fail(path, "the root is not an object");
    const auto plants = json.find("plants");
    if (plants == json.end() || !plants->is_object()) fail(path, "no `plants` object");

    PlantLevelTable table;
    for (auto row = plants->begin(); row != plants->end(); ++row) {
        const Json& entry = row.value();
        if (!entry.is_object()) fail(path, "plants." + row.key() + " is not an object");
        PlantLevelRow parsed;
        parsed.type = row.key();
        if (const auto count = entry.find("levelCount");
            count != entry.end() && count->is_number_integer()) {
            parsed.levelCount = std::max(1, count->get<int>());
        }
        const auto levels = entry.find("levels");
        if (levels == entry.end() || !levels->is_array()) {
            fail(path, "plants." + row.key() + " has no `levels` array");
        }
        for (const Json& step : *levels) {
            if (!step.is_object()) fail(path, "plants." + row.key() + ": a level is not an object");
            std::map<std::string, double> stats;
            const auto values = step.find("stats");
            if (values != step.end() && values->is_object()) {
                for (auto stat = values->begin(); stat != values->end(); ++stat) {
                    if (!stat.value().is_number()) continue;
                    stats.emplace(stat.key(), stat.value().get<double>());
                }
            }
            parsed.levels.push_back(std::move(stats));
        }
        if (parsed.levels.empty()) fail(path, "plants." + row.key() + " carries no levels");
        // The sheet also says `levelCount`, but the ladder is what a fight reads: a row whose
        // `levelCount` disagrees with its own `Values` (99 of 323 do, per the compiler's report)
        // must not be read past its last column.
        parsed.levelCount = static_cast<int>(parsed.levels.size());
        parsed.damageStat = damageColumn(parsed.levels.front());
        if (parsed.damageStat.empty()) {
            for (const auto& stats : parsed.levels) {
                parsed.damageStat = damageColumn(stats);
                if (!parsed.damageStat.empty()) break;
            }
        }
        table.rows_.emplace(parsed.type, std::move(parsed));
    }
    if (table.rows_.empty()) fail(path, "no plant rows");
    table.loaded_ = true;
    return table;
}

const PlantLevelTable& PlantLevelTable::shared() {
    static const PlantLevelTable table = [] {
        const std::filesystem::path directory = generatedDir();
        if (directory.empty()) return PlantLevelTable{};
        const std::filesystem::path file = directory / kFileName;
        std::error_code ignored;
        if (!std::filesystem::is_regular_file(file, ignored)) return PlantLevelTable{};
        return load(file);
    }();
    return table;
}

const PlantLevelRow* PlantLevelTable::find(const std::string& type) const {
    const auto found = rows_.find(type);
    return found == rows_.end() ? nullptr : &found->second;
}

std::vector<std::string> PlantLevelTable::types() const {
    std::vector<std::string> names;
    names.reserve(rows_.size());
    for (const auto& [type, unused] : rows_) {
        (void)unused;
        names.push_back(type);
    }
    std::sort(names.begin(), names.end());
    return names;
}

int clampPlantLevel(const std::string& type, int level) {
    const PlantLevelRow* row = PlantLevelTable::shared().find(type);
    if (row == nullptr) return 1;
    return row->clamp(level);
}

std::optional<double> leveledValue(const std::string& type, const std::string& stat, int level,
                                   double current) {
    if (level <= 1) return std::nullopt;
    const PlantLevelRow* row = PlantLevelTable::shared().find(type);
    if (row == nullptr) return std::nullopt;
    const std::optional<double> base = row->value(stat, 1);
    if (!base.has_value() || *base != current) return std::nullopt; // the identity guard
    return row->value(stat, level);
}

} // namespace pvz::engine
