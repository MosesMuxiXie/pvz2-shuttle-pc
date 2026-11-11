#include "battle.hpp"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>

namespace {

using nlohmann::json;
using shuttle::Battle;

void require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

void begin(Battle& battle, int seed) {
    require(battle.toggleCard(seed) && battle.start(), "Could not start fixture battle");
}

void adaptiveWaves(shuttle::Catalog catalog, shuttle::LevelDefinition level, bool keepOldWave) {
    auto& pea = catalog.plants.at("peashooter");
    pea["cost"] = 0;
    pea["damage"] = 10000;
    pea["interval"] = 0.1;
    level.deck = {"peashooter"};
    level.waves = {
        {12, false, {{"basic", 1, {}}}, 0},
        {25, false, {{"basic", 1, {}}}, 1},
        {45, true, {{"basic", 1, {}}}, 0}
    };
    if (keepOldWave) {
        level.waves[0].zombies.push_back({"basic", 0, {}});
    }
    std::vector<json> events;
    Battle battle(catalog, level, 1, [&](const json& event) { events.push_back(event); });
    begin(battle, 0);
    require(battle.plant(0, 1, 8), "Fixture shooter could not be planted");
    bool collected = false;
    for (int i = 0; i < 30 * Battle::ticksPerSecond && battle.phase() == Battle::Phase::playing; ++i) {
        battle.step();
        if (!battle.plantfoodDrops().empty()) {
            require(!collected, "Plant food dropped more than once");
            const auto drop = battle.plantfoodDrops().front();
            require(battle.collectPlantfood(drop.row, drop.col), "Plant food could not be collected");
            require(!battle.collectPlantfood(drop.row, drop.col), "Plant food could be collected twice");
            collected = true;
        }
    }
    require(collected && battle.plantfood() == 1, "Additional plant food was lost");
    std::vector<int> waves;
    int warning = -1;
    int drops = 0;
    for (const auto& event : events) {
        const auto name = event.at("event");
        if (name == "wave_started") { waves.push_back(event.at("tick").get<int>()); }
        if (name == "flag_warning") {
            warning = event.at("tick");
            require(event.at("trigger") == "health", "Flag warning should be health-triggered");
        }
        if (name == "plantfood_dropped") {
            require(event.at("wave") == 2, "Plant food was assigned to the wrong wave");
            ++drops;
        }
    }
    require(waves == std::vector<int>{720, 960, 1500}, "Adaptive wave or warning timings differ");
    require(warning == 1200 && drops == 1, "Warning delay or plant food count differs");
    if (keepOldWave) {
        require(std::ranges::any_of(battle.zombies(), [](const auto& zombie) { return zombie.wave == 1; }),
                "Fixture did not preserve an earlier-wave zombie");
    } else {
        require(battle.phase() == Battle::Phase::won && events.back().at("event") == "battle_finished",
                "Terminal event does not finish the winning trace");
    }
}

void solarTiming(shuttle::Catalog catalog, shuttle::LevelDefinition level) {
    catalog.zombies.at("basic")["speed"] = 0;
    level.waves = {{0, false, {{"basic", 0, {}}}, 0}};
    std::vector<int> skyTicks;
    Battle battle(catalog, level, 2, [&](const json& event) {
        if (event.at("event") == "sun_dropped" && event.at("source") == "sky") {
            skyTicks.push_back(event.at("tick").get<int>());
        }
    });
    begin(battle, 0);
    for (int tick = 0; tick < 90000 && skyTicks.size() < 70; ++tick) {
        battle.step();
    }
    require(skyTicks.size() == 70 && skyTicks.front() == 120, "Missing timed sky drops");
    for (std::size_t attempt = 1; attempt < skyTicks.size(); ++attempt) {
        const double base = std::min(12.0, 6.0 + 0.1 * attempt);
        const int lower = static_cast<int>(std::ceil(base * 60 - 1e-8));
        const int upper = static_cast<int>(std::ceil((base + 3) * 60 - 1e-8));
        const int gap = skyTicks[attempt] - skyTicks[attempt - 1];
        require(gap >= lower && gap <= upper, "Sky sun countdown violates the original formula");
    }
}

void timerWaves(shuttle::Catalog catalog, shuttle::LevelDefinition level) {
    catalog.zombies.at("basic")["speed"] = 0;
    level.waves = {{12, false, {{"basic", 0, {}}}, 0},
                   {25, false, {{"basic", 0, {}}}, 0},
                   {45, true, {{"basic", 0, {}}}, 0}};
    std::vector<int> starts;
    int warning = -1;
    Battle battle(catalog, level, 5, [&](const json& event) {
        if (event.at("event") == "wave_started") {
            starts.push_back(event.at("tick"));
            require(event.at("trigger") != "health", "An undamaged wave triggered an early wave");
        }
        if (event.at("event") == "flag_warning") {
            warning = event.at("tick");
            require(event.at("trigger") == "timer", "Undamaged flag warning should use its timer");
        }
    });
    begin(battle, 0);
    for (int i = 0; i < 6000 && starts.size() < 3; ++i) { battle.step(); }
    require(starts.size() == 3 && starts[0] == 720, "Timer fixture did not spawn three waves");
    const int normalGap = starts[1] - starts[0];
    require(normalGap >= 1500 && normalGap <= 1860, "Normal wave timer must be 25 to 31 seconds");
    require(warning - starts[1] == 2700 && starts[2] - warning == 300,
            "Flag timer must be 45 seconds followed by a 5-second warning");
}

void thresholdEquality(shuttle::Catalog catalog, shuttle::LevelDefinition level) {
    auto& pea = catalog.plants.at("peashooter");
    pea["cost"] = 0;
    pea["damage"] = 38;
    pea["interval"] = 3600;
    level.deck = {"peashooter"};
    level.waves = {{12, false, {{"basic", 1, {}}}, 0}, {25, false, {{"basic", 1, {}}}, 0}};
    level.extra["wave_timing"]["health_min"] = 0.8;
    level.extra["wave_timing"]["health_max"] = 0.8;
    Battle battle(catalog, level);
    begin(battle, 0);
    require(battle.plant(0, 1, 8), "Could not place equality fixture shooter");
    while (battle.tick() < 960) { battle.step(); }
    require(battle.zombies().front().hp == 152, "Fixture did not reach the exact health threshold");
    require(battle.wavesStarted() == 2, "Threshold equality must allow early spawning");
}

void eligibleCarriers(shuttle::Catalog catalog, shuttle::LevelDefinition level) {
    catalog.zombies.at("basic")["can_spawn_plantfood"] = false;
    catalog.zombies.at("conehead")["can_spawn_plantfood"] = true;
    level.waves = {{0, false, {{"basic", 0, {}}, {"conehead", 1, {}}}, 9}};
    Battle battle(catalog, level);
    begin(battle, 0);
    battle.step();
    require(battle.zombies().size() == 2 && !battle.zombies()[0].carriesPlantfood &&
            battle.zombies()[1].carriesPlantfood, "Plant food must use eligible carriers and cap its count");
}

}

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    try {
        require(argc == 2, "Expected content directory");
        const std::filesystem::path content(argv[1]);
        const auto catalog = shuttle::loadCatalog(content);
        const auto level = shuttle::loadLevelDefinition(content / "native" / "frontyard_1.json", catalog);
        adaptiveWaves(catalog, level, false);
        adaptiveWaves(catalog, level, true);
        solarTiming(catalog, level);
        timerWaves(catalog, level);
        thresholdEquality(catalog, level);
        eligibleCarriers(catalog, level);
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
