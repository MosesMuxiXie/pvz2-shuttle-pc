#pragma once
#include "entity.hpp"
#include <string>
#include <vector>

namespace pvz::engine {

class World;
using PlantBehavior = void (*)(World&, EntityId);
using ZombieBehavior = void (*)(World&, EntityId);

/// String -> behaviour function tables. This is the single place where a plant
/// family or zombie class gains behaviour, and it doubles as the data source for
/// the coverage matrix: a family that is absent here falls back to the default
/// and is counted as `unwired`.
class Registry {
  public:
    static const Registry& shared();

    /// Returns nullptr when the family is unknown to the engine.
    PlantBehavior plantBehavior(const std::string& family) const;
    ZombieBehavior zombieBehavior(const std::string& family) const;

    static const std::vector<std::string>& plantFamilies();
    static const std::vector<std::string>& zombieFamilies();

    /// Family used when nothing matched; never nullptr.
    static PlantBehavior defaultPlant();
    static ZombieBehavior defaultZombie();
};

} // namespace pvz::engine
