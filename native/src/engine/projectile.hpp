#pragma once
namespace pvz::engine {
class World;
/// Integrates every live shot by one fixed step and applies hits.
void stepShots(World& world);
} // namespace pvz::engine
