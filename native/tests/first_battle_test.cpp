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

void selectAll(Battle& battle) {
    for (int card = 0; card < static_cast<int>(battle.cards().size()); ++card) {
        require(battle.toggleCard(card), "Card selection failed");
    }
    require(battle.start(), "Could not begin the battle");
}

void checkBattle(const shuttle::Catalog& catalog, const shuttle::LevelDefinition& level) {
    Battle lost(catalog, level);
    require(!lost.start(), "Started without a selected seed");
    require(!lost.plant(0, 0, 0), "Planted in the chooser");
    selectAll(lost);
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

    Battle won(catalog, level);
    selectAll(won);
    require(won.sun() == 50 && won.plant(0, 0, 0) && won.sun() == 0, "Starting sun or cost mismatch");
    require(!won.plant(0, 1, 0), "Cooldown did not prevent planting");
    require(!won.plant(1, 0, 0), "Planted on an occupied square");
    for (int i = 0; i < 36000 && won.phase() == Battle::Phase::playing; ++i) {
        if (i % Battle::ticksPerSecond == 0) {
            while (!won.suns().empty()) {
                const auto sun = won.suns().front();
                require(won.collectSun(sun.row, sun.col), "Sun could not be collected");
            }
            if (i < 24 * Battle::ticksPerSecond) {
                for (int col : {0, 1}) {
                    for (int row = 0; row < Battle::rows; ++row) {
                        won.plant(0, row, col);
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
                        won.plant(3, zombie.row, static_cast<int>(zombie.x - 3.3));
                    }
                }
                std::array<int, Battle::rows> order{3, 4, 0, 1, 2};
                std::ranges::stable_sort(order, [&](int a, int b) { return priority[a] > priority[b]; });
                for (const int row : order) {
                    for (const int col : {1, 2, 3, 4, 5, 0}) {
                        won.plant(1, row, col);
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
        checkBattle(catalog, level);
        checkSave(argv[2]);
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
