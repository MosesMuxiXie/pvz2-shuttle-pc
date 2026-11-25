// Render test for the world map screen.
//
// The screen is the first non-battle UI, so the test checks three separate things instead of only
// "a PNG appeared": the model reached the screen (26 worlds, a named world selected), the frame is
// a real 1280x720 picture rather than a blank rectangle, and a missing font fails loudly instead of
// rendering an empty window.

#include "worldmap_view.hpp"

#include <SDL3/SDL.h>
#include <SDL3_image/SDL_image.h>
#include <chrono>
#include <filesystem>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>

namespace fs = std::filesystem;

namespace {

void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error("worldmap render test failed: " + message);
}

std::size_t sampledColors(const fs::path& file, int* width, int* height) {
    auto* frame = IMG_Load(pvz::pathUtf8(file).c_str());
    if (frame == nullptr) throw std::runtime_error(std::string("load snapshot: ") + SDL_GetError());
    *width = frame->w;
    *height = frame->h;
    std::set<Uint32> colors;
    for (int y = 0; y < frame->h; y += 4) {
        for (int x = 0; x < frame->w; x += 4) {
            Uint8 r = 0, g = 0, b = 0, a = 0;
            if (SDL_ReadSurfacePixel(frame, x, y, &r, &g, &b, &a)) {
                colors.insert((static_cast<Uint32>(r) << 16) | (static_cast<Uint32>(g) << 8) | b);
            }
        }
    }
    SDL_DestroySurface(frame);
    return colors.size();
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 4) {
            throw std::runtime_error("expected content directory, assets directory and temp root");
        }
        const fs::path content = argv[1];
        const fs::path assets = argv[2];
        const auto root = fs::path(argv[3]) / fs::path("世界地图 渲染") /
                          std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
        fs::create_directories(root);

        pvz::CatalogOptions catalogOptions;
        catalogOptions.boardSizes = content.parent_path() / "native" / "generated" / "board_sizes.json";
        const pvz::Catalog catalog = pvz::loadCatalog(content, catalogOptions);
        const pvz::map::WorldMap map =
            pvz::map::WorldMap::load(content, content.parent_path() / "native" / "generated" /
                                                  "world_gates.json");
        check(map.worlds().size() == 26, "the shipped map must hold 26 worlds");

        pvz::WorldMapScreenOptions options;
        options.assetRoot = assets;
        options.frames = 2;
        options.snapshot = root / "worldmap.png";
        const pvz::WorldMapScreenResult result = pvz::runWorldMapScreen(catalog, map, options);

        check(result.worlds == 26, "the screen must report 26 worlds");
        check(result.selectedWorld == "frontyard", "the first world must start selected, got " +
                                                       result.selectedWorld);
        check(result.unlocked >= 1, "a fresh save must still open the first world");
        check(result.completed == 0, "a fresh save cannot have completed a world");

        int width = 0, height = 0;
        const std::size_t colors = sampledColors(root / "worldmap.png", &width, &height);
        check(width == 1280 && height == 720,
              "snapshot is " + std::to_string(width) + "x" + std::to_string(height));
        check(colors >= 300, "snapshot looks blank: only " + std::to_string(colors) + " sampled colours");

        // Second run must draw the same picture: the screen reads no clock and no RNG.
        const fs::path again = root / "worldmap-again.png";
        auto repeat = options;
        repeat.snapshot = again;
        const pvz::WorldMapScreenResult second = pvz::runWorldMapScreen(catalog, map, repeat);
        check(second.unlocked == result.unlocked && second.selectedWorld == result.selectedWorld,
              "two runs of the same save must agree");
        check(fs::file_size(again) == fs::file_size(root / "worldmap.png"),
              "two runs must produce the same sized frame");

        // A missing font is an error, not a blank window.
        bool rejected = false;
        try {
            auto broken = options;
            broken.assetRoot = assets / "missing";
            (void)pvz::runWorldMapScreen(catalog, map, broken);
        } catch (const std::exception& error) {
            rejected = std::string(error.what()).find("font_zh.ttc") != std::string::npos;
        }
        check(rejected, "a missing font must fail with the font path in the message");

        std::cout << "worldmap render tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
