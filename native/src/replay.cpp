#include "replay.hpp"

#include "battle.hpp"

#include <fstream>
#include <limits>
#include <stdexcept>

namespace shuttle {
namespace {

using nlohmann::json;

std::uint32_t number(const json& value, const char* field, std::uint32_t maximum) {
    if (value.is_number_integer()) {
        const auto numeric = value.get<double>();
        if (numeric >= 0 && numeric <= maximum) {
            return static_cast<std::uint32_t>(numeric);
        }
    }
    throw std::runtime_error(std::string(field) + " must be an integer in range");
}

bool runAction(Battle& battle, const json& input) {
    const auto action = input.at("action").get<std::string>();
    if (action == "start") {
        return battle.start();
    }
    if (action == "select") {
        return battle.toggleCard(static_cast<int>(number(input.at("card"), "card", 255)));
    }
    const auto row = static_cast<int>(number(input.at("row"), "row", Battle::rows - 1));
    const auto col = static_cast<int>(number(input.at("col"), "col", Battle::columns - 1));
    if (action == "plant") {
        return battle.plant(static_cast<int>(number(input.at("card"), "card", 255)), row, col);
    }
    if (action == "shovel") {
        return battle.shovel(row, col);
    }
    if (action == "collect_sun") {
        return battle.collectSun(row, col);
    }
    if (action == "collect_plantfood") {
        return battle.collectPlantfood(row, col);
    }
    throw std::runtime_error("unknown replay action: " + action);
}

}

void replayFirst(const std::filesystem::path& content, const std::filesystem::path& scenario, std::ostream& output) {
    const auto catalog = loadCatalog(content);
    const auto level = loadLevelDefinition(content / "native" / "frontyard_1.json", catalog);
    try {
        std::ifstream input(scenario, std::ios::binary);
        if (!input) {
            throw std::runtime_error("cannot open scenario");
        }
        const auto script = json::parse(input);
        const auto seed = number(script.at("seed"), "seed", std::numeric_limits<std::uint32_t>::max());
        const auto limit = number(script.at("ticks"), "ticks", 36000);
        const auto& actions = script.at("actions");
        if (!actions.is_array()) {
            throw std::runtime_error("actions must be an array");
        }
        std::uint32_t previousTick = 0;
        for (const auto& action : actions) {
            const auto at = number(action.at("tick"), "tick", limit);
            if (at < previousTick) {
                throw std::runtime_error("actions must be sorted by tick");
            }
            previousTick = at;
        }
        const auto emit = [&](const json& event) {
            if (!(output << event.dump() << '\n')) {
                throw std::runtime_error("cannot write replay output");
            }
        };
        emit(json{{"event", "replay_header"}, {"schema", 1}, {"seed", seed}, {"level", level.id},
                  {"tick_rate", Battle::ticksPerSecond}});
        Battle battle(catalog, level, seed, emit);
        auto next = actions.begin();
        for (std::uint32_t tick = 0; tick <= limit; ++tick) {
            while (next != actions.end() && next->at("tick") == tick) {
                if (!runAction(battle, *next)) {
                    throw std::runtime_error("action rejected at tick " + std::to_string(tick) + ": " +
                                             next->at("action").get<std::string>());
                }
                ++next;
            }
            if (tick == limit || battle.phase() == Battle::Phase::won || battle.phase() == Battle::Phase::lost) {
                break;
            }
            if (battle.phase() != Battle::Phase::playing) {
                throw std::runtime_error("battle must start at tick zero");
            }
            battle.step();
        }
        if (next != actions.end()) {
            throw std::runtime_error("replay contains actions after battle ended");
        }
    } catch (const std::exception& error) {
        throw std::runtime_error(utf8Path(scenario) + ": " + error.what());
    }
}

}
