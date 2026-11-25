#include "catalog.hpp"
#include <chrono>
#include <fstream>
#include <functional>
#include <iostream>
#include <stdexcept>

#include "content/model.hpp"
using namespace pvz;
namespace fs = std::filesystem;
void check(bool ok, const std::string& message) {
    if (!ok)
        throw std::runtime_error(message);
}
void write(const fs::path& p, const Json& j) {
    std::ofstream(p) << j.dump(2);
}
struct Fixture {
    fs::path root;
    Json plants = Json::array({{{"id", "sunflower"}, {"behavior", "produce"}}});
    Json zombies = Json::array({{{"id", "basic"}}});
    Json worlds = Json::array({{{"id", "yard"}, {"levels", 1}}});
    Json level = {
        {"id", "yard_1"},
        {"world", "yard"},
        {"index", 1},
        {"sun", 150},
        {"deck", {"sunflower"}},
        {"waves",
         Json::array({{{"delay", 1}, {"zombies", Json::array({{{"type", "basic"}, {"row", 0}}, "basic"})}}})},
        {"extra",
         {{"source", "obb-synth"},
          {"package", "pkg_test"},
          {"stage", "DayStage"},
          {"vasebreaker", true},
          {"future_rule", {1, 2, 3}}}}};
    void save() const {
        fs::create_directories(root / "levels");
        write(root / "plants.json", plants);
        write(root / "zombies.json", zombies);
        write(root / "worlds.json", worlds);
        write(root / "levels/yard_1.json", level);
    }
};
#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    try {
        check(argc == 4, "expected content, fixture and rules-pack roots");
        const auto catalog = loadCatalog(fs::path(argv[1]));
        const auto s = catalog.summary();
        check(s.worlds == 26 && s.plants == 147 && s.zombies == 55 && s.levels == 1809,
              "real catalog counts");
        check(s.original == 1646 && s.synthesized == 163 && s.unknownSource == 0, "source counts");
        // T53 made the three level flags builder output, so the counts moved:
        // vasebreaker 45 -> 47 (pirate_41 + plantagenet_18), synthesized 42 -> 44.
        check(s.vasebreaker == 47 && s.synthesizedVasebreaker == 44, "overlapping mode counts");
        check(!catalog.rules, "no rules pack unless one is asked for");
        check(catalog.rulesNote == "rules=json (no pack requested)", "default rules note");

        // The rules pack carries the original parameters; the JSON registries keep
        // driving decks and worlds until the id mapping exists.
        CatalogOptions withPack;
        withPack.contentPack = fs::path(argv[3]);
        const auto rules = loadCatalog(fs::path(argv[1]), withPack);
        check(rules.rules != nullptr, "rules pack loaded: " + rules.rulesNote);
        check(rules.rules->plants.size() == 339 && rules.rules->zombies.size() == 1127, "pack counts");
        check(rules.rulesNote.rfind("rules=pack", 0) == 0, "rules note names the pack");
        check(rules.levels.size() == 1809 && rules.plants.size() == 147, "JSON registries stay");

        // A pack that was asked for but cannot be read is a hard error. Falling back
        // to JSON here used to let a typo in --pack run a whole session on tuning
        // constants while reporting success.
        CatalogOptions brokenPack;
        brokenPack.contentPack = fs::path(argv[2]) / "missing-rules.pack";
        bool packThrew = false;
        try {
            static_cast<void>(loadCatalog(fs::path(argv[1]), brokenPack));
        } catch (const std::exception& e) {
            packThrew = true;
            const std::string what = e.what();
            check(what.find("rules pack:") != std::string::npos, "pack error names the stage: " + what);
            check(what.find("missing-rules.pack") != std::string::npos, "pack error names the file: " + what);
        }
        check(packThrew, "broken pack is fatal, not a silent fallback");

        CatalogOptions brokenBoards;
        brokenBoards.boardSizes = fs::path(argv[2]) / "missing-boards.json";
        bool boardsThrew = false;
        try {
            static_cast<void>(loadCatalog(fs::path(argv[1]), brokenBoards));
        } catch (const std::exception& e) {
            boardsThrew = true;
            const std::string what = e.what();
            check(what.find("board sizes:") != std::string::npos, "board error names the stage: " + what);
        }
        check(boardsThrew, "broken board sizes are fatal, not 5x9 everywhere");
        const auto& first = catalog.levels.at("frontyard_1");
        check(first.sun == 150 && first.deck.at(0) == "sunflower", "first level sun/deck");
        check(first.extra.at("package") == "pkg_1996" && first.extra.at("stage") == "DayStage",
              "source metadata");
        check(first.waves.size() == 7 && first.waves.at(0).zombies.at(0).row == 0, "wave data");
        const auto base = fs::path(argv[2]) / fs::path(u8"中文 空格") /
                          std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
        int cases = 0;
        auto fixture = [&]() {
            Fixture f;
            f.root = base / std::to_string(++cases);
            return f;
        };
        auto valid = fixture();
        valid.save();
        const auto loaded = loadCatalog(valid.root);
        check(loaded.levels.at("yard_1").extra == valid.level["extra"], "preserve unknown metadata");
        check(loaded.levels.at("yard_1").waves.at(0).zombies.size() == 2, "string/object spawns");
        auto fails = [&](const std::string& name, const std::function<void(Fixture&)>& mutate,
                         const std::string& token, const std::string& filename) {
            auto f = fixture();
            mutate(f);
            f.save();
            try {
                (void)loadCatalog(f.root);
            } catch (const std::exception& e) {
                const std::string message = e.what();
                check(message.find(token) != std::string::npos && message.find(filename) != std::string::npos,
                      name + ": unhelpful diagnostic: " + message);
                std::cout << "PASS " << name << '\n';
                return;
            }
            throw std::runtime_error(name + ": invalid catalog accepted");
        };
        fails(
            "missing world reference", [](auto& f) { f.level["world"] = "absent"; }, "absent", "yard_1.json");
        fails(
            "missing plant reference", [](auto& f) { f.level["deck"] = {"absent"}; }, "absent",
            "yard_1.json");
        fails(
            "missing zombie reference", [](auto& f) { f.level["waves"][0]["zombies"][0]["type"] = "absent"; },
            "absent", "yard_1.json");
        fails(
            "duplicate plants", [](auto& f) { f.plants.push_back(f.plants[0]); }, "duplicate", "plants.json");
        fails(
            "duplicate zombies", [](auto& f) { f.zombies.push_back(f.zombies[0]); }, "duplicate",
            "zombies.json");
        fails(
            "duplicate worlds", [](auto& f) { f.worlds.push_back(f.worlds[0]); }, "duplicate", "worlds.json");
        fails("strict integer", [](auto& f) { f.level["sun"] = "150"; }, "sun", "yard_1.json");
        fails("fractional integer", [](auto& f) { f.level["index"] = 1.5; }, "index", "yard_1.json");
        fails("overflow integer", [](auto& f) { f.level["sun"] = 1000000000000LL; }, "sun", "yard_1.json");
        fails("negative sun", [](auto& f) { f.level["sun"] = -1; }, "sun", "yard_1.json");
        fails("negative delay", [](auto& f) { f.level["waves"][0]["delay"] = -1; }, "delay", "yard_1.json");
        fails(
            "invalid row", [](auto& f) { f.level["waves"][0]["zombies"][0]["row"] = 5; }, "row",
            "yard_1.json");
        fails("invalid flag", [](auto& f) { f.level["waves"][0]["flag"] = "false"; }, "flag", "yard_1.json");
        fails("invalid metadata", [](auto& f) { f.level["extra"] = Json::array(); }, "extra", "yard_1.json");
        fails("invalid source", [](auto& f) { f.level["extra"]["source"] = 42; }, "source", "yard_1.json");
        fails(
            "invalid mode", [](auto& f) { f.level["extra"]["vasebreaker"] = "false"; }, "vasebreaker",
            "yard_1.json");
        fails("missing waves", [](auto& f) { f.level.erase("waves"); }, "waves", "yard_1.json");
        fails("wrong registry shape", [](auto& f) { f.plants = Json::object(); }, "array", "plants.json");
        fails("missing world levels", [](auto& f) { f.worlds[0]["levels"] = 2; }, "levels", "worlds.json");
        fails(
            "unknown world unlock", [](auto& f) { f.worlds[0]["unlock_after"] = "absent"; }, "absent",
            "worlds.json");
        fails(
            "world unlock cycle", [](auto& f) { f.worlds[0]["unlock_after"] = "yard"; }, "cycle",
            "worlds.json");
        fails("invalid plant stats", [](auto& f) { f.plants[0]["hp"] = 0; }, "hp", "plants.json");
        fails(
            "invalid armor", [](auto& f) { f.zombies[0]["armor"] = Json::array({{{"hp", -1}}}); }, "hp",
            "zombies.json");
        auto ioFail = [&](const std::function<void(const Fixture&)>& mutate, const std::string& token) {
            auto f = fixture();
            f.save();
            mutate(f);
            try {
                (void)loadCatalog(f.root);
            } catch (const std::exception& e) {
                check(std::string(e.what()).find(token) != std::string::npos &&
                          std::string(e.what()).find(pathUtf8(f.root)) != std::string::npos,
                      e.what());
                return;
            }
            throw std::runtime_error("expected error: " + token);
        };
        ioFail([](const auto& f) { fs::remove(f.root / "plants.json"); }, "plants.json");
        ioFail([](const auto& f) { std::ofstream(f.root / "plants.json") << "[{broken"; }, "plants.json");
        ioFail([](const auto& f) { write(f.root / "levels/duplicate.json", f.level); }, "duplicate");
        ioFail(
            [](const auto& f) {
                auto l = f.level;
                l["id"] = "yard_other";
                write(f.root / "levels/other.json", l);
            },
            "index");
        ioFail([](const auto& f) { fs::remove(f.root / "levels/yard_1.json"); }, "levels");
        std::cout << "PASS real catalog, Unicode fixture and " << cases << " fixture cases\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "FAIL " << e.what() << '\n';
        return 1;
    }
}
