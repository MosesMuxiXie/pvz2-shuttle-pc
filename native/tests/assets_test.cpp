#include "assets.hpp"
#include "sdl_support.hpp"
#include <filesystem>
#include <iostream>
#include <stdexcept>
namespace fs = std::filesystem;
int main(int argc, char** argv) {
    try {
        if (argc != 2)
            throw std::runtime_error("expected the assets directory");
        const fs::path assets = argv[1];
        pvz::sdl::Display display(true, "asset cache test");
        auto* renderer = display.renderer.get();
        pvz::AssetCache cache(renderer, assets);
        auto* sun = cache.texture("ui/sun.png");
        float width = 0, height = 0;
        pvz::sdl::require(SDL_GetTextureSize(sun, &width, &height), "read sun size");
        if (width < 16 || height < 16)
            throw std::runtime_error("sun artwork is too small");
        const auto plant = cache.model("db/plants/SunflowerPLANT");
        if (plant.model == nullptr || plant.texture == nullptr)
            throw std::runtime_error("sunflower model did not load");
        if (plant.model->armature.name != "Sunflower")
            throw std::runtime_error("unexpected sunflower armature");
        const auto again = cache.model("db/plants/SunflowerPLANT");
        if (again.model != plant.model)
            throw std::runtime_error("model cache returned a second copy");
        if (cache.textureCount() < 2 || cache.modelCount() != 1)
            throw std::runtime_error("cache counters are wrong");
        bool missing = false;
        try {
            (void)cache.texture("ui/does-not-exist.png");
        } catch (const std::exception& error) {
            missing = std::string(error.what()).find("cannot open artwork") != std::string::npos;
        }
        if (!missing)
            throw std::runtime_error("missing artwork was not diagnosed");
        std::cout << "PASS assets textures=" << cache.textureCount() << " models=" << cache.modelCount()
                  << " sun=" << width << 'x' << height << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
