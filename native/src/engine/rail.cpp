// A2 (S3): read the generated rail rows. Same shape and the same "named error, never an empty
// table" rule as mechanics.cpp - an empty rail plan would make 192 minecart levels play as
// ordinary levels, which is the bug this file exists to make visible.
#include "rail.hpp"

#include "plantfood.hpp" // generatedDir(): the same resolver the other generated tables use

#include <fstream>
#include <nlohmann/json.hpp>
#include <stdexcept>

namespace pvz::engine {
namespace {

using Json = nlohmann::json;

/// One `levels.<id>.rail` / `railcarts` / `minecarts` entry as a row number.
///
/// Written tolerantly because the sheet has never shipped one: `rail` may be a bool (the client
/// flag), an object (`{rows: [...]}`) or the row list itself, and a cart may be an integer or an
/// object with `Row` / `row`. Only an integer row inside 0..7 is accepted; anything else is a parse
/// gone wrong and must not silently become row 0.
bool rowNumber(const Json& value, int& out) {
    if (value.is_number_integer()) {
        const int row = value.get<int>();
        if (row < 0 || row > 7) return false;
        out = row;
        return true;
    }
    if (value.is_object()) {
        for (const char* key : {"Row", "row"}) {
            const auto found = value.find(key);
            if (found == value.end()) continue;
            if (!found->is_number_integer()) return false;
            const int row = found->get<int>();
            if (row < 0 || row > 7) return false;
            out = row;
            return true;
        }
    }
    return false;
}

std::vector<int> rowsOf(const Json& rail) {
    std::vector<int> rows;
    if (rail.is_array()) {
        for (const Json& entry : rail) {
            int row = -1;
            if (rowNumber(entry, row)) rows.push_back(row);
        }
        return rows;
    }
    if (!rail.is_object()) return rows;
    for (const char* key : {"railcarts", "minecarts", "rows", "Rows"}) {
        const auto found = rail.find(key);
        if (found == rail.end() || !found->is_array()) continue;
        for (const Json& entry : *found) {
            int row = -1;
            if (rowNumber(entry, row)) rows.push_back(row);
        }
        if (!rows.empty()) return rows;
    }
    return rows;
}

} // namespace

RailTable RailTable::load(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("rail table: " + path.string() + ": cannot open");
    Json document;
    try {
        input >> document;
    } catch (const std::exception& error) {
        throw std::runtime_error("rail table: " + path.string() + ": " + error.what());
    }
    if (!document.is_object()) {
        throw std::runtime_error("rail table: " + path.string() + ": root is not a JSON object");
    }
    const auto levels = document.find("levels");
    if (levels == document.end() || !levels->is_object()) {
        throw std::runtime_error("rail table: " + path.string() + ": no levels object");
    }
    RailTable table;
    for (auto it = levels->begin(); it != levels->end(); ++it) {
        if (!it.value().is_object()) continue;
        const auto rail = it.value().find("rail");
        // `false` is the client flag for "this level has a rail object, but no cart". It is not a
        // row: a row needs at least one cart, otherwise the level belongs to the decorative set
        // and the kernel puts nothing on the lawn.
        if (rail == it.value().end() || rail->is_boolean()) continue;
        std::vector<int> rows = rowsOf(*rail);
        if (rows.empty()) {
            // A bare list under `rail` (the shape a future compiler would most plausibly emit).
            const auto carts = it.value().find("railcarts");
            if (carts != it.value().end()) rows = rowsOf(*carts);
        }
        if (rows.empty()) continue;
        table.rows_.emplace(it.key(), RailRow{it.key(), std::move(rows)});
    }
    return table;
}

const RailTable& RailTable::shared() {
    static const RailTable table = [] {
        const std::filesystem::path dir = generatedDir();
        if (dir.empty()) {
            throw std::runtime_error("rail table: the generated directory is unknown; set "
                                     "PVZ_GENERATED_DIR or run from the repository root");
        }
        return load(dir / kFileName);
    }();
    return table;
}

const RailRow* RailTable::find(const std::string& level) const {
    const auto found = rows_.find(level);
    return found == rows_.end() ? nullptr : &found->second;
}

} // namespace pvz::engine
