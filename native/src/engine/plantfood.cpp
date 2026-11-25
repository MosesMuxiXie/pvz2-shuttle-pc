#include "plantfood.hpp"
#include "../catalog.hpp"
#include <cstdlib>
#include <fstream>
#include <stdexcept>
#include <utility>
#include <vector>

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

/// Read a generated JSON table, turning every failure into `what: <path>: <reason>`.
Json readTable(const std::filesystem::path& file, const char* what) {
    std::ifstream in(file);
    if (!in) throw std::runtime_error(std::string(what) + ": " + pathUtf8(file) + ": cannot open");
    Json doc;
    try {
        in >> doc;
    } catch (const std::exception& error) {
        throw std::runtime_error(std::string(what) + ": " + pathUtf8(file) + ": " + error.what());
    }
    return doc;
}

std::vector<std::string> stringsOr(const Json& object, const char* key) {
    std::vector<std::string> out;
    const auto it = object.find(key);
    if (it == object.end() || !it->is_array()) return out;
    for (const auto& entry : *it) {
        if (entry.is_string()) out.push_back(entry.get<std::string>());
    }
    return out;
}

PlantFoodEffect parseEffect(const Json& json) {
    PlantFoodEffect effect;
    effect.kind = stringOr(json, "kind");
    effect.projectile = stringOr(json, "projectile");
    effect.cooldownMin = numberOr(json, "cooldownMin");
    effect.cooldownMax = numberOr(json, "cooldownMax");
    effect.initialMin = numberOr(json, "initialMin");
    effect.launchSound = stringOr(json, "launchSound");
    const auto offset = json.find("spawnOffset");
    if (offset != json.end() && offset->is_object()) {
        effect.spawnOffsetX = numberOr(*offset, "x");
        effect.spawnOffsetY = numberOr(*offset, "y");
    }
    return effect;
}

} // namespace

const PlantFoodEffect* PlantFoodRow::projectileEffect() const {
    for (const auto& effect : effects) {
        if (effect.hasProjectile()) return &effect;
    }
    return nullptr;
}

bool PlantFoodRow::matches(const std::string& type) const {
    // A row is keyed by whichever identity the sheet had: 39 rows carry a client id, the
    // rest a pack `TypeName`. Both are planting identities, so `feed`/`canFeed` accept both.
    return type == id || (!packType.empty() && type == packType);
}

PlantFoodTable PlantFoodTable::load(const std::filesystem::path& file) {
    const Json doc = readTable(file, "plantfood table");
    const auto plants = doc.find("plants");
    if (plants == doc.end() || !plants->is_array()) {
        throw std::runtime_error("plantfood table: " + pathUtf8(file) + ": no `plants` array");
    }
    PlantFoodTable table;
    table.rows_.reserve(plants->size());
    for (const auto& entry : *plants) {
        if (!entry.is_object()) {
            throw std::runtime_error("plantfood table: " + pathUtf8(file) + ": a `plants` entry is not an object");
        }
        PlantFoodRow row;
        row.id = stringOr(entry, "id");
        row.packType = stringOr(entry, "packType");
        row.idKind = stringOr(entry, "idKind");
        row.framework = stringOr(entry, "framework");
        row.durationSeconds = numberOr(entry, "durationSeconds");
        row.playCount = intOr(entry, "playCount");
        row.gaps = stringsOr(entry, "gaps");
        if (row.id.empty() && row.packType.empty()) {
            throw std::runtime_error("plantfood table: " + pathUtf8(file) + ": a row names no plant id");
        }
        const auto effects = entry.find("effects");
        if (effects != entry.end() && effects->is_array()) {
            for (const auto& effect : *effects) {
                if (effect.is_object()) row.effects.push_back(parseEffect(effect));
            }
        }
        table.rows_.push_back(std::move(row));
    }
    if (table.rows_.empty()) {
        throw std::runtime_error("plantfood table: " + pathUtf8(file) + ": `plants` is empty");
    }
    return table;
}

const PlantFoodTable& PlantFoodTable::shared() {
    static const PlantFoodTable table = [] {
        const auto dir = generatedDir();
        if (dir.empty()) {
            throw std::runtime_error(
                "plantfood table: plantfood_from_pack.json was not found; set PVZ_GENERATED_DIR or run from the "
                "repository root (working directory: " + pathUtf8(std::filesystem::current_path()) + ")");
        }
        return PlantFoodTable::load(dir / kFileName);
    }();
    return table;
}

std::size_t PlantFoodTable::actionSlotRows() const {
    std::size_t count = 0;
    for (const auto& row : rows_) {
        if (row.hasActionSlot()) ++count;
    }
    return count;
}

const PlantFoodRow* PlantFoodTable::find(const std::string& type) const {
    if (type.empty()) return nullptr;
    for (const auto& row : rows_) {
        if (row.matches(type)) return &row;
    }
    return nullptr;
}

namespace {

/// The environment wins so a test can point at a fixture without rebuilding. It is read as wide
/// text on MSVC on purpose: a narrow `getenv` would hand back ANSI bytes for a Chinese path and
/// every table lookup would fail with `cannot open`.
std::filesystem::path fromEnvironment() {
#ifdef _MSC_VER
    if (const wchar_t* wide = _wgetenv(L"PVZ_GENERATED_DIR"); wide != nullptr && *wide != L'\0') {
        return std::filesystem::path(wide);
    }
#else
    if (const char* narrow = std::getenv("PVZ_GENERATED_DIR"); narrow != nullptr && *narrow != '\0') {
        return std::filesystem::path(narrow);
    }
#endif
    return {};
}

bool hasTableFile(const std::filesystem::path& dir) {
    if (dir.empty()) return false;
    std::error_code error;
    const bool found = std::filesystem::is_regular_file(dir / PlantFoodTable::kFileName, error);
    return found && !error;
}

/// Every place a generated directory may sit, most specific first: the environment, the
/// compile-time default, then the source tree found by walking up from the working directory.
/// The walk is what makes an out-of-tree build work at all: cl.exe reads `-D` text in the ANSI
/// code page, so a non-ASCII source path arrives mangled and the compile-time default is
/// unusable (that is the `鏂囨。` in the audit gate's error messages).
std::vector<std::filesystem::path> generatedCandidates() {
    std::vector<std::filesystem::path> out;
    out.push_back(fromEnvironment());
#ifdef PVZ_GENERATED_DIR
    out.push_back(std::filesystem::path(PVZ_GENERATED_DIR));
#endif
    std::error_code error;
    auto dir = std::filesystem::current_path(error);
    for (int level = 0; level < 8 && !error && !dir.empty(); ++level) {
        out.push_back(dir / "native" / "generated");
        out.push_back(dir / "generated");
        const auto parent = dir.parent_path();
        if (parent == dir) break;
        dir = parent;
    }
    return out;
}

} // namespace

std::filesystem::path generatedDir() {
    for (const auto& candidate : generatedCandidates()) {
        if (hasTableFile(candidate)) return candidate;
    }
    return {};
}

} // namespace pvz::engine
