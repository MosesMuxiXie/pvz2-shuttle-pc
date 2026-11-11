#include "catalog.hpp"
#include "replay.hpp"
#include "save.hpp"
#ifdef PVZ_ENABLE_DESKTOP
#include "battle_screen.hpp"
#include "launcher.hpp"
#endif

#include <iostream>

namespace {

void auditContent(const std::filesystem::path& path) {
    const auto catalog = shuttle::loadCatalog(path);
    const auto summary = catalog.summary();
    std::cout << "worlds=" << catalog.worlds.size()
              << " plants=" << catalog.plants.size()
              << " zombies=" << catalog.zombies.size()
              << " levels=" << catalog.levels.size()
              << " synthesized=" << summary.synthesized
              << " vasebreaker=" << summary.vasebreaker
              << " synthesized_vasebreaker=" << summary.synthesizedVasebreaker << '\n';
}

int usage() {
    std::cerr << "Usage: PvZ2SHUTTLE --audit-content <content directory>\n"
              << "       PvZ2SHUTTLE --replay-first <content directory> <scenario.json>\n"
              << "       PvZ2SHUTTLE --import-save <Python save.json> <native save.json>\n";
#ifdef PVZ_ENABLE_DESKTOP
    std::cerr << "       PvZ2SHUTTLE --play-first <content directory> [native save.json]\n"
              << "       PvZ2SHUTTLE --import-save <Python save.json>\n"
              << "       PvZ2SHUTTLE --launcher <asset directory>\n"
              << "       PvZ2SHUTTLE --launcher-smoke <asset directory>\n";
#endif
    return 2;
}

}

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    try {
#if defined(__APPLE__) && defined(PVZ_ENABLE_DESKTOP)
        if (argc == 1) {
            shuttle::runFirstBattle(shuttle::bundledContentPath(), {}, false);
            return 0;
        }
#endif
        if (argc < 3 || argc > 4) {
            return usage();
        }
        const std::filesystem::path command(argv[1]);
        const std::filesystem::path path(argv[2]);
        if (command == "--audit-content" && argc == 3) {
            auditContent(path);
            return 0;
        }
        if (command == "--replay-first" && argc == 4) {
            shuttle::replayFirst(path, std::filesystem::path(argv[3]), std::cout);
            return 0;
        }
        if (command == "--import-save" && argc == 4) {
            shuttle::importPythonSave(path, std::filesystem::path(argv[3]));
            return 0;
        }
#ifdef PVZ_ENABLE_DESKTOP
        if (command == "--import-save" && argc == 3) {
            shuttle::importPythonSave(path, shuttle::defaultSavePath());
            return 0;
        }
        if (command == "--play-first" || (command == "--play-first-smoke" && argc == 3)) {
            const auto save = argc == 4 ? std::filesystem::path(argv[3]) : std::filesystem::path{};
            shuttle::runFirstBattle(path, save, command == "--play-first-smoke");
            return 0;
        }
        if ((command == "--launcher" || command == "--launcher-smoke") && argc == 3) {
            shuttle::runLauncher(path, command == "--launcher-smoke");
            return 0;
        }
#endif
        return usage();
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
