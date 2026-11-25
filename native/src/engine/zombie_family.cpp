#include "engine/zombie_family.hpp"

#include <array>
#include <utility>

namespace pvz::engine {
namespace {

struct Row {
    std::string_view className;
    std::string_view family;
};

// Generated from the original sheets; keep the file in sync with
// `python tools/contentc/zclasses.py` (check_all fails when it drifts).
constexpr std::array<Row, 183> kRows{{
#include "zombie_family_table.inc"
}};

}  // namespace

std::string_view zombieFamilyFor(std::string_view className) {
    if (className.empty()) return {};
    // The table is sorted by class name, so a binary search keeps a 1127-type
    // spawn path cheap even when the director creates dozens of zombies a second.
    std::size_t lo = 0, hi = kRows.size();
    while (lo < hi) {
        const std::size_t mid = lo + (hi - lo) / 2;
        if (kRows[mid].className < className) {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    if (lo < kRows.size() && kRows[lo].className == className) return kRows[lo].family;
    return {};
}

std::size_t zombieFamilyCount() { return kRows.size(); }

}  // namespace pvz::engine
