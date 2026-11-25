#pragma once
#include "../catalog.hpp"
#include <cstdint>
#include <random>
#include <string>
#include <vector>

namespace pvz::engine {

/// One zombie scheduled to enter the lawn at `tick`.
struct Spawn {
    std::uint64_t tick = 0;
    std::string type;
    int row = 0;
    std::size_t wave = 0;
    bool flag = false;
    bool final = false;
};

/// Turns `LevelDefinition::waves` into a deterministic, tick-addressed schedule.
/// The schedule is built once in the constructor so that the kernel never
/// re-randomises row choice while stepping.
class Director {
  public:
    Director() = default;
    Director(const LevelDefinition& level, int rows, std::mt19937& rng);

    /// Pops every spawn whose tick is `<= now`, in schedule order.
    std::vector<Spawn> takeDue(std::uint64_t tick);
    bool allSpawned() const { return cursor_ >= schedule_.size(); }
    std::size_t waveCount() const { return waveCount_; }
    std::size_t spawnedWaves() const { return spawnedWaves_; }
    std::size_t total() const { return schedule_.size(); }
    std::uint64_t lastTick() const { return schedule_.empty() ? 0 : schedule_.back().tick; }
    const std::vector<Spawn>& schedule() const { return schedule_; }

  private:
    std::vector<Spawn> schedule_;
    std::vector<std::size_t> remaining_; // per-wave outstanding spawns
    std::size_t cursor_ = 0;
    std::size_t waveCount_ = 0;
    std::size_t spawnedWaves_ = 0;
};

} // namespace pvz::engine
