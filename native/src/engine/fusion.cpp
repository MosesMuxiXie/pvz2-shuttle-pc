#include "fusion.hpp"
#include "plantfood.hpp"
#include "../catalog.hpp"
#include <fstream>
#include <stdexcept>
#include <utility>

namespace pvz::engine {
namespace {

std::string stringOf(const Json& object, const char* key) {
    const auto it = object.find(key);
    if (it == object.end() || !it->is_string()) return {};
    return it->get<std::string>();
}

bool boolOf(const Json& object, const char* key) {
    const auto it = object.find(key);
    if (it == object.end() || !it->is_boolean()) return false;
    return it->get<bool>();
}

} // namespace

FusionTable FusionTable::load(const std::filesystem::path& file) {
    std::ifstream in(file);
    if (!in) throw std::runtime_error("fusion table: " + pathUtf8(file) + ": cannot open");
    Json doc;
    try {
        in >> doc;
    } catch (const std::exception& error) {
        throw std::runtime_error("fusion table: " + pathUtf8(file) + ": " + error.what());
    }
    const auto pairs = doc.find("pairs");
    if (pairs == doc.end() || !pairs->is_array()) {
        throw std::runtime_error("fusion table: " + pathUtf8(file) + ": no `pairs` array");
    }
    FusionTable table;
    table.recipes_.reserve(pairs->size());
    for (const auto& entry : *pairs) {
        if (!entry.is_object()) {
            throw std::runtime_error("fusion table: " + pathUtf8(file) + ": a `pairs` entry is not an object");
        }
        FusionRecipe recipe;
        recipe.source = stringOf(entry, "source");
        recipe.fusion = stringOf(entry, "fusion");
        recipe.result = stringOf(entry, "result");
        recipe.sound = stringOf(entry, "sound");
        recipe.sourceKind = stringOf(entry, "sourceKind");
        recipe.onlyResult = boolOf(entry, "onlyResult");
        // A recipe with a missing ingredient or outcome cannot be applied, and guessing one
        // would fuse two plants into something the sheets never named.
        if (recipe.source.empty() || recipe.fusion.empty() || recipe.result.empty()) {
            throw std::runtime_error("fusion table: " + pathUtf8(file) + ": a row is missing source/fusion/result");
        }
        table.recipes_.push_back(std::move(recipe));
    }
    if (table.recipes_.empty()) {
        throw std::runtime_error("fusion table: " + pathUtf8(file) + ": `pairs` is empty");
    }
    return table;
}

const FusionTable& FusionTable::shared() {
    static const FusionTable table = [] {
        const auto dir = generatedDir();
        if (dir.empty()) {
            throw std::runtime_error(
                "fusion table: the generated directory is unknown; build with PVZ_GENERATED_DIR or set it in the "
                "environment");
        }
        return FusionTable::load(dir / kFileName);
    }();
    return table;
}

const FusionRecipe* FusionTable::find(const std::string& a, const std::string& b) const {
    if (a.empty() || b.empty()) return nullptr;
    for (const auto& recipe : recipes_) {
        if (recipe.matches(a, b)) return &recipe;
    }
    return nullptr;
}

} // namespace pvz::engine
