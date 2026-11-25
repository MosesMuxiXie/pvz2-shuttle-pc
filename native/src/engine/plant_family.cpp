#include "engine/plant_family.hpp"

#include <array>
#include <utility>

namespace pvz::engine {
namespace {

struct Row {
    std::string_view id;
    std::string_view family;
};

// Generated from `native/generated/plant_families.json`; keep the file in sync
// with `python tools/contentc/plant_family_inc.py --check` (check_all fails on
// drift).
constexpr std::array<Row, 339> kRows{{
#include "plant_family_table.inc"
}};

}  // namespace

std::string_view plantFamilyFor(std::string_view id) {
    if (id.empty()) return {};
    // Sorted by id: a binary search keeps `World::plant` cheap even when a
    // script plants a few dozen types per level.
    std::size_t lo = 0, hi = kRows.size();
    while (lo < hi) {
        const std::size_t mid = lo + (hi - lo) / 2;
        if (kRows[mid].id < id) {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    if (lo < kRows.size() && kRows[lo].id == id) return kRows[lo].family;
    return {};
}

std::size_t plantFamilyCount() { return kRows.size(); }

}  // namespace pvz::engine
