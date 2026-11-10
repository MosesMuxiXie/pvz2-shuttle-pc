#include "catalog.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string_view>

namespace fs = std::filesystem;

namespace {

constexpr std::string_view validLevel = R"({
  "id":"yard_1","world":"yard","index":1,"title":"Day 1","sun":150,
  "flags":0,"seed_bank":1,"deck":["sunflower"],
  "waves":[{"delay":1,"flag":false,"zombies":[{"type":"basic","row":0}]}],
  "extra":{"source":"obb","package":"pkg_0001","stage":"DayStage"}
})";

void require(bool condition, const char* message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

void write(const fs::path& path, std::string_view text) {
    std::ofstream file(path, std::ios::binary);
    file.exceptions(std::ios::failbit | std::ios::badbit);
    file << text;
}

void expectFailure(const fs::path& content, std::string_view filename, std::string_view detail) {
    try {
        (void)shuttle::loadCatalog(content);
    } catch (const std::exception& error) {
        const std::string_view message(error.what());
        if (message.find(filename) == std::string_view::npos ||
            message.find(detail) == std::string_view::npos) {
            throw std::runtime_error("Unexpected diagnostic: " + std::string(message));
        }
        return;
    }
    throw std::runtime_error("An invalid catalog was accepted");
}

void checkRealCatalog(const fs::path& content) {
    const auto catalog = shuttle::loadCatalog(content);
    require(catalog.worlds.size() == 26, "Expected 26 worlds");
    require(catalog.plants.size() == 147, "Expected 147 plants");
    require(catalog.zombies.size() == 55, "Expected 55 zombies");
    require(catalog.levels.size() == 1809, "Expected 1809 levels");
    const auto summary = catalog.summary();
    require(summary.synthesized == 163, "Expected 163 synthesized levels");
    require(summary.vasebreaker == 45, "Expected 45 vasebreaker records");
    require(summary.synthesizedVasebreaker == 42, "Expected 42 synthesized vasebreaker records");
    const auto& first = catalog.levels.at("frontyard_1");
    require(first.sun == 150 && first.deck.at(0) == "sunflower", "First level content differs");
    require(first.waves.at(0).zombies.at(0).row == 0, "First wave spawn row differs");
}

void checkFixtures(const fs::path& fixtures) {
    const auto content = fixtures / u8"\u5173\u5361";
    const auto level = content / "levels" / "yard_1.json";
    const auto duplicate = content / "levels" / "duplicate.json";
    fs::create_directories(level.parent_path());
    fs::remove(duplicate);
    write(content / "worlds.json", R"([{"id":"yard"}])");
    write(content / "plants.json", R"([{"id":"sunflower"}])");
    write(content / "zombies.json", R"([{"id":"basic"}])");
    write(level, validLevel);
    require(shuttle::loadCatalog(content).levels.size() == 1, "Fixture could not be read");

    fs::remove(content / "plants.json");
    expectFailure(content, "plants.json", "open");
    write(content / "plants.json", R"([{"id":"sunflower"}])");

    write(content / "worlds.json", R"([{"id":"other"}])");
    expectFailure(content, "yard_1.json", "world");
    write(content / "worlds.json", R"([{"id":"yard","unlock_after":"missing"}])");
    expectFailure(content, "worlds.json", "unlock_after");
    write(content / "worlds.json", R"([{"id":"yard"}])");

    write(content / "zombies.json", R"([{"id":"other"}])");
    expectFailure(content, "yard_1.json", "basic");
    write(content / "zombies.json", R"([{"id":"basic"}])");

    write(duplicate, validLevel);
    expectFailure(content, ".json", "duplicate level ID");
    fs::remove(duplicate);

    write(level, "{");
    expectFailure(content, "yard_1.json", "parse");

    std::string unknownSource(validLevel);
    unknownSource.replace(unknownSource.find("\"obb\""), 5, "\"obb-sytnh\"");
    write(level, unknownSource);
    expectFailure(content, "yard_1.json", "unknown level source 'obb-sytnh'");

    std::string multiRowLevel(validLevel);
    constexpr std::string_view singleSpawn = R"({"type":"basic","row":0})";
    multiRowLevel.replace(multiRowLevel.find(singleSpawn), singleSpawn.size(),
                          R"({"type":"basic","rows":[0,1]},"basic")");
    write(level, multiRowLevel);
    const auto multiRowCatalog = shuttle::loadCatalog(content);
    const auto& spawns = multiRowCatalog.levels.at("yard_1").waves.at(0).zombies;
    require(spawns.at(0).rows == std::vector<int>{0, 1}, "Explicit lanes were lost");
    require(spawns.at(1).type == "basic" && !spawns.at(1).row, "Short spawn format was lost");
    write(level, validLevel);
}

}

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    try {
        require(argc == 3, "Expected real content and fixture directories");
        checkRealCatalog(fs::path(argv[1]));
        checkFixtures(fs::path(argv[2]));
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
