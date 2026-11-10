#include "catalog.hpp"
#ifdef PVZ_ENABLE_DESKTOP
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
    std::cerr << "Usage: PvZ2SHUTTLE --audit-content <content directory>\n";
#ifdef PVZ_ENABLE_DESKTOP
    std::cerr << "       PvZ2SHUTTLE --launcher <asset directory>\n"
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
    if (argc != 3) {
        return usage();
    }
    try {
        const std::filesystem::path command(argv[1]);
        const std::filesystem::path path(argv[2]);
        if (command == "--audit-content") {
            auditContent(path);
            return 0;
        }
#ifdef PVZ_ENABLE_DESKTOP
        if (command == "--launcher" || command == "--launcher-smoke") {
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
