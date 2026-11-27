#include "vase.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <stdexcept>

#include <nlohmann/json.hpp>

#include "engine/plantfood.hpp"

namespace pvz::engine {
namespace {

using Json = nlohmann::json;

std::string stringOr(const Json& object, const char* key) {
    const auto it = object.find(key);
    if (it == object.end() || !it->is_string()) return {};
    return it->get<std::string>();
}

int intOr(const Json& object, const char* key, int fallback = 0) {
    const auto it = object.find(key);
    if (it == object.end() || !it->is_number()) return fallback;
    return static_cast<int>(it->get<double>());
}

std::string lowerAscii(std::string text) {
    for (char& ch : text) ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
    return text;
}

/// `CollectableTypeName` is the sheet's own discriminator. `sun`, `coins` and `plantfood` are the
/// three the arcade ships; a sun collectable becomes a sun vase so the kernel keeps four classes.
VaseContent contentOfCollectable(const std::string& type) {
    const std::string lower = lowerAscii(type);
    if (lower == "sun" || lower == "sunsmall" || lower == "sunlarge") return VaseContent::sun;
    return VaseContent::collectible;
}

std::runtime_error broken(const std::filesystem::path& path, const std::string& why) {
    return std::runtime_error("vase table: " + path.string() + ": " + why);
}

} // namespace

const char* vaseContentName(VaseContent content) {
    switch (content) {
    case VaseContent::zombie:
        return "zombie";
    case VaseContent::plant:
        return "plant";
    case VaseContent::collectible:
        return "collectible";
    case VaseContent::sun:
        return "sun";
    }
    return "zombie";
}

VaseTable VaseTable::load(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw broken(path, "cannot open the vase file");
    Json doc = Json::parse(in, nullptr, false);
    if (doc.is_discarded() || !doc.is_object()) throw broken(path, "the root must be a JSON object");
    const auto levels = doc.find("levels");
    if (levels == doc.end() || !levels->is_object()) throw broken(path, "the file has no `levels` object");

    VaseTable table;
    table.specs_.reserve(levels->size());
    for (auto level = levels->begin(); level != levels->end(); ++level) {
        if (!level.value().is_object()) continue;
        VaseSpec spec;
        spec.levelId = level.key();
        const auto vases = level.value().find("vases");
        if (vases != level.value().end() && vases->is_array()) {
            for (const Json& entry : *vases) {
                if (!entry.is_object()) continue;
                const int count = intOr(entry, "count", 0);
                if (count <= 0) continue;
                const std::string kind = stringOr(entry, "type");
                VaseEntry row;
                if (kind == "zombie") {
                    row.content = VaseContent::zombie;
                    row.id = stringOr(entry, "zombieId");
                } else if (kind == "plant") {
                    row.content = VaseContent::plant;
                    row.id = stringOr(entry, "plantId");
                } else if (kind == "collectable" || kind == "collectible") {
                    const std::string named = stringOr(entry, "collectableType");
                    row.content = contentOfCollectable(named);
                    row.id = named;
                } else if (kind == "sun") {
                    // No shipped row uses this discriminator (every sunAmount is null), but a
                    // table that names one directly must not be dropped on the floor.
                    row.content = VaseContent::sun;
                    row.id = "sun";
                } else {
                    continue; // an unknown discriminator fills nothing; it is not a silent count
                }
                row.count = count;
                spec.total += count;
                spec.entries.push_back(row);
            }
        }
        const auto range = level.value().find("columnRange");
        if (range != level.value().end() && range->is_object()) {
            spec.minColumn = intOr(*range, "min", 0);
            spec.maxColumn = intOr(*range, "max", -1);
        }
        const auto excluded = level.value().find("excludedCells");
        if (excluded != level.value().end() && excluded->is_array()) {
            for (const Json& cell : *excluded) {
                if (!cell.is_array() || cell.size() < 2) continue;
                if (!cell[0].is_number() || !cell[1].is_number()) continue;
                // The sheet stores `{mX, mY}` and the generator writes `[x, y]`, so the pair is
                // (col, row). Stored as (row, col) because that is how the board is indexed.
                spec.excluded.emplace_back(static_cast<int>(cell[1].get<double>()),
                                           static_cast<int>(cell[0].get<double>()));
            }
        }
        spec.gridItemType = stringOr(level.value(), "vaseGridItemType");
        table.specs_.push_back(std::move(spec));
    }
    if (table.specs_.empty()) throw broken(path, "the table has no levels");
    std::sort(table.specs_.begin(), table.specs_.end(),
              [](const VaseSpec& left, const VaseSpec& right) { return left.levelId < right.levelId; });
    return table;
}

const VaseTable& VaseTable::shared() {
    static const VaseTable table = [] {
        const std::filesystem::path directory = engine::generatedDir();
        if (directory.empty()) {
            throw std::runtime_error(
                "vase table: the generated directory is unknown; build with PVZ_GENERATED_DIR "
                "or set it in the environment");
        }
        return load(directory / kFileName);
    }();
    return table;
}

const VaseSpec* VaseTable::find(std::string_view levelId) const {
    const auto it = std::lower_bound(specs_.begin(), specs_.end(), levelId,
                                     [](const VaseSpec& spec, std::string_view id) {
                                         return spec.levelId < id;
                                     });
    if (it == specs_.end() || it->levelId != levelId) return nullptr;
    return &*it;
}

int VaseTable::totalVases() const {
    int total = 0;
    for (const VaseSpec& spec : specs_) total += spec.total;
    return total;
}

} // namespace pvz::engine
