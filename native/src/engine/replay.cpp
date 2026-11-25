#include "replay.hpp"
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace pvz::engine {
namespace {
std::string text(const Json& object, const char* key, const std::string& fallback = {}) {
    const auto it = object.find(key);
    if (it == object.end() || !it->is_string()) return fallback;
    return it->get<std::string>();
}
int number(const Json& object, const char* key, int fallback = 0) {
    const auto it = object.find(key);
    if (it == object.end() || !it->is_number()) return fallback;
    return static_cast<int>(it->get<double>());
}
} // namespace

Script parseScript(const Json& json) {
    if (!json.is_object()) throw std::runtime_error("replay script must be a JSON object");
    Script script;
    script.level = text(json, "level");
    const auto seedIt = json.find("seed");
    if (seedIt != json.end() && seedIt->is_number()) script.seed = seedIt->get<std::uint32_t>();
    const auto inputs = json.find("inputs");
    if (inputs == json.end()) return script;
    if (!inputs->is_array()) throw std::runtime_error("replay script: inputs must be an array");
    for (const auto& entry : *inputs) {
        if (!entry.is_object()) throw std::runtime_error("replay script: input must be an object");
        ScriptInput input;
        const double rawTick = number(entry, "tick", 0);
        // A negative (or absurd) tick used to wrap into ~1.8e19, after which every input was
        // silently dropped and the run looked like a clean no-op. Refuse it by name instead.
        if (!(rawTick >= 0.0) || rawTick > 1.0e9) {
            throw std::runtime_error("replay script: input tick " + std::to_string(rawTick) +
                                     " is outside [0, 1e9]");
        }
        input.tick = static_cast<std::uint64_t>(rawTick);
        input.op = text(entry, "op");
        input.type = text(entry, "type");
        input.row = number(entry, "row", 0);
        input.col = number(entry, "col", 0);
        input.id = static_cast<EntityId>(number(entry, "id", 0));
        input.id2 = static_cast<EntityId>(number(entry, "id2", 0));
        if (input.op.empty()) throw std::runtime_error("replay script: input without op");
        if (input.op == "plant" && input.type.empty()) {
            throw std::runtime_error("replay script: plant input without type");
        }
        if ((input.op == "feed" || input.op == "fuse") && input.id == 0) {
            // Feeding or fusing is addressed by entity id, not by cell: after a shovel the
            // ids are the only stable handle, and a 0 here would silently target nothing.
            throw std::runtime_error("replay script: " + input.op + " input without id");
        }
        if (input.op == "fuse" && input.id2 == 0) {
            throw std::runtime_error("replay script: fuse input without id2");
        }
        if (input.op == "collect" && number(entry, "id", 0) < 0) {
            // Ids are `EntityId` (unsigned); a negative literal would wrap to a huge
            // value and look like "collect nothing". 0 is the documented "all suns".
            throw std::runtime_error("replay script: collect id must be >= 0");
        }
        // Inputs are consumed in file order, so an out-of-order list would silently
        // drop the earlier request; refusing it keeps a replay readable as a timeline.
        if (!script.inputs.empty() && input.tick < script.inputs.back().tick) {
            throw std::runtime_error("replay script: input goes back in time (tick " +
                                     std::to_string(input.tick) + " after " +
                                     std::to_string(script.inputs.back().tick) + ")");
        }
        script.inputs.push_back(std::move(input));
    }
    return script;
}

Script loadScript(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error("cannot open replay script: " + pathUtf8(path));
    std::ostringstream buffer;
    buffer << stream.rdbuf();
    return parseScript(Json::parse(buffer.str()));
}

void applyInputs(World& world, const Script& script, std::size_t& cursor) {
    while (cursor < script.inputs.size() && script.inputs[cursor].tick <= world.tick()) {
        const auto& input = script.inputs[cursor++];
        // An input meant for an earlier tick still gets applied (dropping a click is
        // worse), but it is recorded so a replay whose timing drifted is visible.
        if (input.tick + 1 < world.tick()) {
            world.event("input_late", Json{{"op", input.op}, {"tick", input.tick}, {"at", world.tick()}});
        }
        if (input.op == "plant") {
            const auto error = world.plant(input.type, input.row, input.col);
            if (!error.empty()) {
                world.event("input_rejected", Json{{"op", "plant"}, {"type", input.type}, {"row", input.row},
                                                   {"col", input.col}, {"reason", error}});
            }
        } else if (input.op == "shovel") {
            world.shovel(input.row, input.col);
        } else if (input.op == "collect") {
            if (input.id == 0) {
                for (const auto& sun : world.suns()) world.collect(sun.id);
            } else {
                world.collect(input.id);
            }
        } else if (input.op == "spawn") {
            world.spawnZombie(input.type, input.row);
        } else if (input.op == "feed") {
            // S5.7: plant food exists in the world but a replay had no way to trigger it,
            // which made the feature unreachable from every non-SDL path.
            if (!world.feed(input.id)) {
                world.event("input_rejected", Json{{"op", "feed"}, {"id", input.id}, {"reason", "feed refused"}});
            }
        } else if (input.op == "fuse") {
            if (!world.tryFuse(input.id, input.id2)) {
                world.event("input_rejected", Json{{"op", "fuse"}, {"id", input.id}, {"id2", input.id2},
                                                   {"reason", "fusion refused"}});
            }
        } else {
            world.event("input_rejected", Json{{"op", input.op}, {"reason", "unknown op"}});
        }
    }
}

void runScript(World& world, const Script& script, double seconds) {
    std::size_t cursor = 0;
    const auto limit = static_cast<std::uint64_t>(seconds / World::stepSeconds + 0.5);
    while (!world.finished() && world.tick() < limit) {
        applyInputs(world, script, cursor);
        world.step();
    }
    applyInputs(world, script, cursor);
}

Json summarize(const World& world) {
    char buffer[32];
    std::snprintf(buffer, sizeof(buffer), "0x%016llx", static_cast<unsigned long long>(world.hash()));
    return Json{{"level", world.level().id},
                {"status", world.status()},
                {"tick", world.tick()},
                {"hash", std::string(buffer)},
                {"spawned", world.spawnedZombies()},
                {"killed", world.killedZombies()},
                {"removed", world.removedZombies()},
                {"mowerKills", world.mowerKills()},
                {"leaked", world.leakedZombies()},
                {"rejectedSpawns", world.rejectedSpawns()},
                {"waves", world.wave()},
                {"rows", world.rows()},
                {"cols", world.cols()},
                {"sun", world.sun()},
                {"fusions", world.fusions()},
                {"unwiredPlants", world.unwiredPlants()},
                {"unwiredZombies", world.unwiredZombies()}};
}

} // namespace pvz::engine
