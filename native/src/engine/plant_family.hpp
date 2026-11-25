#pragma once

#include <cstddef>
#include <string_view>

namespace pvz::engine {

/// Behaviour family of a packed plant id (`native/generated/plant_families.json`).
///
/// The shipped content JSON names only 147 plants while the compiled pack carries
/// 339 original types. Types without a content entry have no `behavior` field, so
/// the engine asks this table instead: it is the projection of the rule-based
/// judgement in `tools/contentc/pfamilies.py` (rules R01..R21, evidence per row).
///
/// Returns an empty view when the id is unknown; callers fall back to `support`
/// (the "no attacking evidence" bucket) and count it as unwired.
std::string_view plantFamilyFor(std::string_view id);

/// Number of rows in the generated table (339 for the v26.10.1 sheets).
std::size_t plantFamilyCount();

}  // namespace pvz::engine
