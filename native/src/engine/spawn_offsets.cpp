#include "spawn_offsets.hpp"
#include "../catalog.hpp"
#include "plantfood.hpp" // generatedDir()
#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <stdexcept>
#include <string_view>

namespace pvz::engine {
namespace {

std::string stringOr(const Json& object, const char* key) {
    const auto it = object.find(key);
    if (it == object.end() || !it->is_string()) return {};
    return it->get<std::string>();
}

double numberOr(const Json& object, const char* key, double fallback) {
    const auto it = object.find(key);
    if (it == object.end() || !it->is_number()) return fallback;
    return it->get<double>();
}

Json readTable(const std::filesystem::path& file) {
    std::ifstream in(file);
    if (!in) throw std::runtime_error("spawn offsets: " + pathUtf8(file) + ": cannot open");
    Json doc;
    try {
        in >> doc;
    } catch (const std::exception& error) {
        throw std::runtime_error("spawn offsets: " + pathUtf8(file) + ": " + error.what());
    }
    return doc;
}

/// Shots whose plant declares a vertical spawn offset, counted for `--run-level`.
std::size_t g_applied = 0;

/// Compare two plant spellings: lower case, a trailing `Default` dropped, and anything that is
/// not a letter or a digit removed. `PeashooterDefault`, `Peashooter` and the content id
/// `peashooter` all collapse to `peashooter`; `CobCannonDefault` becomes `cobcannon`.
std::string normalisePlantKey(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    for (const char raw : text) {
        const auto c = static_cast<unsigned char>(raw);
        if (std::isalnum(c) != 0) {
            out.push_back(static_cast<char>(std::tolower(c)));
        }
    }
    constexpr std::string_view suffix = "default";
    if (out.size() > suffix.size() && out.compare(out.size() - suffix.size(), suffix.size(), suffix) == 0) {
        out.resize(out.size() - suffix.size());
    }
    return out;
}

} // namespace

SpawnOffsets SpawnOffsets::load(const std::filesystem::path& file) {
    const Json doc = readTable(file);
    const std::string where = "spawn offsets: " + pathUtf8(file) + ": ";

    SpawnOffsets table;
    const auto scale = doc.find("scale");
    if (scale != doc.end() && scale->is_object()) {
        table.pxPerRow_ = numberOr(*scale, "pxPerRow", kFallbackPxPerRow);
        table.pxPerColumn_ = numberOr(*scale, "pxPerColumn", kFallbackPxPerColumn);
    }
    if (!(table.pxPerRow_ > 0.0)) throw std::runtime_error(where + "scale.pxPerRow is not positive");
    if (!(table.pxPerColumn_ > 0.0))
        throw std::runtime_error(where + "scale.pxPerColumn is not positive");

    const auto rows = doc.find("rows");
    if (rows == doc.end() || !rows->is_array()) throw std::runtime_error(where + "rows is not an array");

    std::vector<double> yValues;
    yValues.reserve(rows->size());
    for (std::size_t index = 0; index < rows->size(); ++index) {
        const Json& row = (*rows)[index];
        if (!row.is_object()) {
            throw std::runtime_error(where + "rows[" + std::to_string(index) + "] is not an object");
        }
        SpawnOffset offset;
        offset.plant = stringOr(row, "plant");
        offset.kind = stringOr(row, "kind");
        if (offset.plant.empty()) {
            throw std::runtime_error(where + "rows[" + std::to_string(index) + "].plant is missing");
        }
        if (offset.kind.empty()) {
            throw std::runtime_error(where + "rows[" + std::to_string(index) + "].kind is missing");
        }
        const auto y = row.find("yPx");
        if (y == row.end() || !y->is_number()) {
            throw std::runtime_error(where + "rows[" + std::to_string(index) + "].yPx is missing");
        }
        offset.yPx = y->get<double>();
        offset.actionIndex = static_cast<int>(numberOr(row, "actionIndex", 0));
        offset.xPx = numberOr(row, "xPx", 0);
        offset.sentinel = std::abs(offset.yPx) >= kSentinelPx;
        if (offset.yPx < 0) ++table.negativeRows_;
        if (offset.yPx > 0) ++table.positiveRows_;
        if (offset.sentinel) ++table.sentinelRows_;
        yValues.push_back(offset.yPx);
        table.rows_.push_back(std::move(offset));
    }

    // Alias map: normalised spelling -> the spelling `rows_` uses. The engine hands us the
    // content id (`peashooter`); the sheet spells it `PeashooterDefault`. Without this, every
    // lookup misses and every projectile draws at the row centre.
    for (const auto& row : table.rows_) {
        const std::string key = normalisePlantKey(row.plant);
        if (key.empty()) continue;
        const auto seen = table.alias_.find(key);
        if (seen == table.alias_.end()) {
            table.alias_.emplace(key, row.plant);
            continue;
        }
        // Two spellings collapsed together: keep the `...Default` one so the choice does not
        // depend on the order of the rows in the file. The shipped table has no such pair.
        constexpr std::string_view suffix = "default";
        const auto endsWithDefault = [suffix](const std::string& text) {
            if (text.size() <= suffix.size()) return false;
            std::string tail = text.substr(text.size() - suffix.size());
            for (char& c : tail) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
            return tail == suffix;
        };
        if (!endsWithDefault(seen->second) && endsWithDefault(row.plant)) seen->second = row.plant;
    }

    if (!yValues.empty()) {
        auto middle = yValues.begin() + static_cast<std::ptrdiff_t>(yValues.size() / 2);
        std::nth_element(yValues.begin(), middle, yValues.end());
        table.medianYPx_ = *middle;
        if (yValues.size() % 2 == 0) {
            // Even count: average the two middles so the number matches statistics.median.
            auto lower = std::max_element(yValues.begin(), middle);
            table.medianYPx_ = (*lower + table.medianYPx_) / 2.0;
        }
    }
    return table;
}

const SpawnOffsets& SpawnOffsets::shared() {
    static const SpawnOffsets table = [] {
        const std::filesystem::path directory = generatedDir();
        if (directory.empty()) throw std::runtime_error("spawn offsets: generated directory not found");
        return load(directory / kFileName);
    }();
    return table;
}

std::string SpawnOffsets::canonicalPlant(const std::string& plant) const {
    if (plant.empty()) return {};
    const auto it = alias_.find(normalisePlantKey(plant));
    return it == alias_.end() ? std::string() : it->second;
}

const SpawnOffset* SpawnOffsets::find(const std::string& plant, int actionIndex) const {
    const std::string key = canonicalPlant(plant);
    if (key.empty()) return nullptr;
    for (const auto& row : rows_) {
        if (row.actionIndex == actionIndex && row.plant == key) return &row;
    }
    return nullptr;
}

const SpawnOffset* SpawnOffsets::launchOffset(const std::string& plant) const {
    const std::string key = canonicalPlant(plant);
    if (key.empty()) return nullptr;
    const SpawnOffset* best = nullptr;
    for (const auto& row : rows_) {
        if (row.plant != key || !row.draws()) continue;
        if (best == nullptr || row.yPx < best->yPx) best = &row;
    }
    return best;
}

double SpawnOffsets::launchYPixels(const std::string& plant) const {
    const SpawnOffset* row = launchOffset(plant);
    return row == nullptr ? 0.0 : row->yPx;
}

double SpawnOffsets::launchYRows(const std::string& plant) const {
    return launchYPixels(plant) / pxPerRow_;
}

int SpawnOffsets::rowAdjustmentForZombie(int row) const {
    // See the header: no row of this table is keyed by a lawn row, so nothing to look up. The
    // parameter stays so the call site reads as the decision it is, and so a future table that
    // does carry landing rows has one place to add them instead of two.
    (void)row;
    return 0;
}

void noteSpawnOffsetApplied(double yPixels) {
    if (yPixels == 0.0) return;
    ++g_applied;
}

std::size_t spawnOffsetsApplied() { return g_applied; }

void resetSpawnOffsetsApplied() { g_applied = 0; }

} // namespace pvz::engine
