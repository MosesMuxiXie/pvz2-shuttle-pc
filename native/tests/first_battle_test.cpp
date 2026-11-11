#include "battle.hpp"
#include "save.hpp"

#include <algorithm>
#include <barrier>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <thread>

namespace fs = std::filesystem;
using shuttle::Battle;
using nlohmann::json;

void require(bool value, const char* message) {
    if (!value) {
        throw std::runtime_error(message);
    }
}

void selectAll(Battle& battle, json& actions) {
    for (int card = 0; card < static_cast<int>(battle.cards().size()); ++card) {
        require(battle.toggleCard(card), "Card selection failed");
        actions.push_back({{"tick", 0}, {"action", "select"}, {"card", card}});
    }
    require(battle.start(), "Could not begin the battle");
    actions.push_back({{"tick", 0}, {"action", "start"}});
}

void writeReplay(const fs::path& root, const char* name, const Battle& battle,
                 const json& actions, const std::vector<json>& events) {
    fs::create_directories(root);
    const auto file = root / name;
    auto scriptPath = file;
    scriptPath += ".json";
    std::ofstream script(scriptPath, std::ios::binary);
    script.exceptions(std::ios::failbit | std::ios::badbit);
    script << json{{"seed", 1}, {"ticks", battle.tick()}, {"actions", actions}}.dump(2) << '\n';
    script.close();
    auto tracePath = file;
    tracePath += ".jsonl";
    std::ofstream trace(tracePath, std::ios::binary);
    trace.exceptions(std::ios::failbit | std::ios::badbit);
    trace << json{{"event", "replay_header"}, {"schema", 1}, {"seed", 1}, {"level", "frontyard_1"},
                   {"tick_rate", Battle::ticksPerSecond}}.dump() << '\n';
    for (const auto& event : events) {
        trace << event.dump() << '\n';
    }
    trace.close();
}

void checkBattle(const shuttle::Catalog& catalog, const shuttle::LevelDefinition& level, const fs::path& output) {
    json lostActions = json::array();
    std::vector<json> lostEvents;
    Battle lost(catalog, level, 1, [&](const json& event) { lostEvents.push_back(event); });
    require(!lost.start(), "Started without a selected seed");
    require(!lost.plant(0, 0, 0), "Planted in the chooser");
    selectAll(lost, lostActions);
    for (int tick = 0; tick < 2 * Battle::ticksPerSecond - 1; ++tick) {
        lost.step();
    }
    require(lost.suns().empty(), "Initial sun appeared early");
    lost.step();
    require(lost.suns().size() == 1, "Initial sun did not appear after two seconds");
    while (lost.tick() < 12 * Battle::ticksPerSecond - 1) {
        lost.step();
    }
    require(lost.wavesStarted() == 0, "First wave started early");
    lost.step();
    require(lost.wavesStarted() == 1 && lost.zombies().size() == 2, "First wave mismatch");
    for (int i = 0; i < 36000 && lost.phase() == Battle::Phase::playing; ++i) {
        lost.step();
    }
    require(lost.phase() == Battle::Phase::lost, "An undefended lawn should lose");
    require(lostEvents.back().at("event") == "battle_finished", "Events followed the losing settlement");
    writeReplay(output, "lost", lost, lostActions, lostEvents);

    json wonActions = json::array();
    std::vector<json> wonEvents;
    Battle won(catalog, level, 1, [&](const json& event) { wonEvents.push_back(event); });
    selectAll(won, wonActions);
    const auto planted = [&](int card, int row, int col) {
        const bool accepted = won.plant(card, row, col);
        if (accepted) {
            wonActions.push_back({{"tick", won.tick()}, {"action", "plant"}, {"card", card}, {"row", row}, {"col", col}});
        }
        return accepted;
    };
    require(won.sun() == 50 && planted(0, 0, 0) && won.sun() == 0, "Starting sun or cost mismatch");
    require(!won.plant(0, 1, 0), "Cooldown did not prevent planting");
    require(!won.plant(1, 0, 0), "Planted on an occupied square");
    for (int i = 0; i < 36000 && won.phase() == Battle::Phase::playing; ++i) {
        if (i % Battle::ticksPerSecond == 0) {
            while (!won.suns().empty()) {
                const auto sun = won.suns().front();
                require(won.collectSun(sun.row, sun.col), "Sun could not be collected");
                wonActions.push_back({{"tick", won.tick()}, {"action", "collect_sun"}, {"row", sun.row}, {"col", sun.col}});
            }
            while (!won.plantfoodDrops().empty()) {
                const auto drop = won.plantfoodDrops().front();
                require(won.collectPlantfood(drop.row, drop.col), "Could not collect the additional plant food");
                wonActions.push_back({{"tick", won.tick()}, {"action", "collect_plantfood"}, {"row", drop.row}, {"col", drop.col}});
            }
            if (i < 24 * Battle::ticksPerSecond) {
                for (int col : {0, 1}) {
                    for (int row = 0; row < Battle::rows; ++row) {
                        planted(0, row, col);
                    }
                }
            } else {
                std::array<double, Battle::rows> priority{};
                for (const auto& plant : won.plants()) {
                    if (plant.card == 1) {
                        priority[plant.row] -= 5.0;
                    }
                }
                for (const auto& zombie : won.zombies()) {
                    priority[zombie.row] += zombie.hp / 190.0 * (10 - std::min(zombie.x, 9.0)) / 3.0;
                    if (zombie.x > 3.5 && zombie.x < 8.5) {
                        planted(3, zombie.row, static_cast<int>(zombie.x - 3.3));
                    }
                }
                std::array<int, Battle::rows> order{3, 4, 0, 1, 2};
                std::ranges::stable_sort(order, [&](int a, int b) { return priority[a] > priority[b]; });
                for (const int row : order) {
                    for (const int col : {1, 2, 3, 4, 5, 0}) {
                        planted(1, row, col);
                    }
                }
            }
        }
        won.step();
    }
    if (won.phase() != Battle::Phase::won) {
        std::cerr << "Win replay stopped on wave " << won.wavesStarted() << " at tick " << won.tick() << '\n';
    }
    require(won.phase() == Battle::Phase::won, "Scripted first battle did not win");
    require(won.wavesStarted() == level.waves.size(), "Win occurred before final wave");
    require(won.plantfood() == 1, "The fifth wave did not provide one collectible plant food");
    writeReplay(output, "won", won, wonActions, wonEvents);
}

json read(const fs::path& path) {
    std::ifstream stream(path, std::ios::binary);
    return json::parse(stream);
}

void checkSave(const fs::path& root) {
    const auto dir = root / u8"\u5b58\u6863";
    fs::create_directories(dir);
    const auto input = dir / "python.json";
    const auto output = dir / "native.json";
    const auto invalid = dir / "invalid.json";
    const auto unused = dir / "unused.json";
    fs::remove(output);
    fs::remove(unused);
    const json expected = {{"version", 2}, {"completed", {"egypt:0"}}, {"coins", 999},
                           {"garden", {{"slots", json::array()}}}, {"extra", "preserved"}};
    std::ofstream(input) << expected.dump();
    std::ofstream(invalid) << R"({"version":99})";
    shuttle::importPythonSave(input, output);
    require(read(input) == expected && read(output) == expected, "Import changed legacy fields");
    shuttle::recordFirstBattleWin(output);
    shuttle::recordFirstBattleWin(output);
    auto won = expected;
    won["completed"].push_back("frontyard:0");
    require(read(output) == won && read(input) == expected, "Win was not idempotent");
    bool rejected = false;
    try { shuttle::importPythonSave(input, output); } catch (const std::exception&) { rejected = true; }
    require(rejected && read(output) == won, "Import must reject an existing save");
    rejected = false;
    try { shuttle::importPythonSave(invalid, unused); } catch (const std::exception&) { rejected = true; }
    require(rejected && !fs::exists(unused), "Import must reject an unsupported save");
    shuttle::recordFirstBattleWin(unused);
    require(read(unused).at("completed") == json::array({"frontyard:0"}), "Fresh win was not saved");

    const auto concurrent = dir / "concurrent.json";
    for (int attempt = 0; attempt < 32; ++attempt) {
        fs::remove(concurrent);
        std::barrier start(2);
        bool imported = false;
        std::jthread importer([&] {
            start.arrive_and_wait();
            try {
                shuttle::importPythonSave(input, concurrent);
                imported = true;
            } catch (const std::exception&) {
                // A win that publishes first takes ownership of the empty slot.
            }
        });
        start.arrive_and_wait();
        shuttle::recordFirstBattleWin(concurrent);
        importer.join();
        const auto result = read(concurrent);
        require(std::ranges::find(result.at("completed"), "frontyard:0") != result.at("completed").end(),
                "Concurrent save lost the win");
        require(!imported || result == won, "A successful concurrent import lost its fields");
    }
}

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    try {
        require(argc == 3, "Expected content and test output directories");
        const fs::path content(argv[1]);
        const auto catalog = shuttle::loadCatalog(content);
        const auto level = shuttle::loadLevelDefinition(content / "native" / "frontyard_1.json", catalog);
        require(level.waves.size() == 6, "Expected six defined source waves");
        checkBattle(catalog, level, fs::path(argv[2]) / "replays");
        checkSave(argv[2]);
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
