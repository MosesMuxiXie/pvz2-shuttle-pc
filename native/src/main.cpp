#include "catalog.hpp"

#include <iostream>

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    if (argc != 3 || std::filesystem::path(argv[1]) != "--audit-content") {
        std::cerr << "Usage: PvZ2SHUTTLE --audit-content <content directory>\n";
        return 2;
    }
    try {
        const auto catalog = shuttle::loadCatalog(std::filesystem::path(argv[2]));
        const auto summary = catalog.summary();
        std::cout << "worlds=" << catalog.worlds.size()
                  << " plants=" << catalog.plants.size()
                  << " zombies=" << catalog.zombies.size()
                  << " levels=" << catalog.levels.size()
                  << " synthesized=" << summary.synthesized
                  << " vasebreaker=" << summary.vasebreaker
                  << " synthesized_vasebreaker=" << summary.synthesizedVasebreaker << '\n';
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
