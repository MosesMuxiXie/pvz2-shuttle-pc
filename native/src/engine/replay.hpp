#pragma once
#include "../catalog.hpp"
#include "world.hpp"
#include <filesystem>
#include <string>
#include <vector>

namespace pvz::engine {

/// One player action scheduled at a tick, as written in a replay script.
struct ScriptInput {
    std::uint64_t tick = 0;
    std::string op; // plant | shovel | collect | spawn | feed | fuse
    std::string type;
    int row = 0, col = 0;
    EntityId id = 0;
    /// Second plant for `fuse`; the first one is `id`.
    EntityId id2 = 0;
};

struct Script {
    std::string level;
    std::uint32_t seed = 1;
    std::vector<ScriptInput> inputs;
};

Script parseScript(const Json& json);
Script loadScript(const std::filesystem::path& path);

/// Applies every input whose tick is `<= world.tick()` before each step.
void applyInputs(World& world, const Script& script, std::size_t& cursor);

/// Steps the world until it finishes or `seconds` of simulated time elapse.
void runScript(World& world, const Script& script, double seconds);

/// `{"level":..,"status":..,"tick":..,"hash":"0x..."}` plus counters.
Json summarize(const World& world);

} // namespace pvz::engine
