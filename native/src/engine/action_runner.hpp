#pragma once
#include "entity.hpp"

namespace pvz::engine {
class World;

/// Executes one fixed step of a plant's rules-pack action list. Plants whose type
/// is absent from the rules pack carry no slots and are driven by
/// `Registry` families instead.
void runActionSlots(World& world, PlantEntity& plant);

} // namespace pvz::engine
