// Render test for the level list.
//
// The screen exists to close the gap between the world map and a battle, so the test checks the
// two things that gap needs: the rows really are *this world's* levels (a dropped filter would
// list all 1809 and the count assertion catches it), and the save's stars/cleared flags reach the
// rows. On top of that: a real 1280x720 frame, byte-identical reruns, glyphs inside the selected
// row, and a loud failure when the font is missing.

#include "level_select_view.hpp"
#include "progress.hpp"

#include <SDL3/SDL.h>
#include <SDL3_image/SDL_image.h>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error("level select render test failed: " + message);
}

std::vector<std::uint8_t> readBytes(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    if (!in) throw std::runtime_error("cannot read " + pvz::pathUtf8(file));
    return std::vector<std::uint8_t>(std::istreambuf_iterator<char>(in),
                                     std::istreambuf_iterator<char>());
}

std::size_t inkPixels(const fs::path& file, const pvz::ScreenRect& rect, int inset, int threshold,
                      int* width, int* height) {
    SDL_Surface* frame = IMG_Load(pvz::pathUtf8(file).c_str());
    if (frame == nullptr) throw std::runtime_error(std::string("load snapshot: ") + SDL_GetError());
    *width = frame->w;
    *height = frame->h;
    const int x0 = static_cast<int>(rect.x) + inset;
    const int y0 = static_cast<int>(rect.y) + inset;
    const int x1 = static_cast<int>(rect.x + rect.w) - inset;
    const int y1 = static_cast<int>(rect.y + rect.h) - inset;
    check(x1 > x0 && y1 > y0, "the selected row must be sampleable");

    Uint8 br = 0, bg = 0, bb = 0, ba = 0;
    if (!SDL_ReadSurfacePixel(frame, x0, y0, &br, &bg, &bb, &ba)) {
        SDL_DestroySurface(frame);
        throw std::runtime_error(std::string("sample background: ") + SDL_GetError());
    }
    std::size_t ink = 0;
    for (int y = y0; y < y1; ++y) {
        for (int x = x0; x < x1; ++x) {
            Uint8 r = 0, g = 0, b = 0, a = 0;
            if (!SDL_ReadSurfacePixel(frame, x, y, &r, &g, &b, &a)) continue;
            const int dr = std::abs(static_cast<int>(r) - static_cast<int>(br));
            const int dg = std::abs(static_cast<int>(g) - static_cast<int>(bg));
            const int db = std::abs(static_cast<int>(b) - static_cast<int>(bb));
            if (dr > threshold || dg > threshold || db > threshold) ++ink;
        }
    }
    SDL_DestroySurface(frame);
    return ink;
}

// The number of catalog levels that belong to `world` — computed here, independently of the
// screen, so a screen that forgot its filter cannot agree with the test by accident.
std::size_t levelsIn(const pvz::Catalog& catalog, const std::string& world) {
    std::size_t count = 0;
    for (const auto& entry : catalog.levels)
        if (entry.second.world == world) ++count;
    return count;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 4) {
            throw std::runtime_error("expected content directory, assets directory and temp root");
        }
        const fs::path content = argv[1];
        const fs::path assets = argv[2];
        const auto root = fs::path(argv[3]) / fs::path("关卡列表 渲染") /
                          std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
        fs::create_directories(root);

        const pvz::Catalog catalog = pvz::loadCatalog(content);
        check(levelsIn(catalog, "frontyard") > 1, "the fixture needs more than one frontyard level");

        // ---- a save that cleared two frontyard levels ----------------------------------------
        pvz::Progress played;
        played.keys = 1;
        pvz::LevelRecord first;
        first.cleared = true;
        first.stars = 3;
        first.attempts = 1;
        first.bestTick = 1500;
        pvz::LevelRecord second;
        second.cleared = true;
        second.stars = 1;
        second.attempts = 3;
        second.bestTick = 2400;
        played.levels["frontyard_1"] = first;
        played.levels["frontyard_2"] = second;
        const fs::path saveFile = root / "save.json";
        pvz::saveProgress(saveFile, played, 0);
        const pvz::Progress reloaded = pvz::loadProgress(saveFile);

        pvz::LevelSelectOptions options;
        options.assetRoot = assets;
        options.worldId = "frontyard";
        options.progressFile = saveFile;
        options.frames = 2;
        options.snapshot = root / "levels.png";
        const pvz::LevelSelectResult result = pvz::runLevelSelect(catalog, reloaded, options);

        check(result.world == "frontyard", "the screen must report the world it listed");
        check(static_cast<std::size_t>(result.levels) == levelsIn(catalog, "frontyard"),
              "the list must hold exactly this world's levels: got " +
                  std::to_string(result.levels) + ", content has " +
                  std::to_string(levelsIn(catalog, "frontyard")) + " (of " +
                  std::to_string(catalog.levels.size()) + " total)");
        check(result.rows.size() == static_cast<std::size_t>(result.levels),
              "every listed level needs a row");
        for (const pvz::LevelSelectRow& row : result.rows) {
            check(catalog.levels.count(row.id) == 1, "row id is not a catalog level: " + row.id);
            check(catalog.levels.at(row.id).world == "frontyard",
                  "row " + row.id + " belongs to " + catalog.levels.at(row.id).world +
                      ", not frontyard");
        }
        check(result.cleared == 2, "two frontyard levels are cleared in this save, got " +
                                       std::to_string(result.cleared));
        check(result.selected == 0 && result.selectedLevel == result.rows.front().id,
              "the cursor must start on the first row, got " + result.selectedLevel);
        check(result.rows.front().id == "frontyard_1",
              "the first frontyard level must sort first, got " + result.rows.front().id);
        check(result.rows.front().stars == 3 && result.rows.front().cleared,
              "row 1 must carry the save's three stars");
        check(result.rows[1].stars == 1 && result.rows[1].cleared,
              "row 2 must carry the save's single star");
        check(!result.rows[2].cleared && result.rows[2].stars == 0,
              "row 3 is untouched and must say so");

        int width = 0, height = 0;
        const std::size_t ink = inkPixels(root / "levels.png", result.selectedRect, 6, 40, &width,
                                          &height);
        check(width == 1280 && height == 720,
              "snapshot is " + std::to_string(width) + "x" + std::to_string(height));
        check(ink >= 120, "the selected row must carry glyphs, only " + std::to_string(ink) +
                              " ink pixels inside its rectangle");

        // ---- determinism ---------------------------------------------------------------------
        auto again = options;
        again.snapshot = root / "levels-again.png";
        const pvz::LevelSelectResult second_run = pvz::runLevelSelect(catalog, reloaded, again);
        check(second_run.selectedLevel == result.selectedLevel && second_run.levels == result.levels,
              "two runs of the same save must agree");
        check(readBytes(root / "levels.png") == readBytes(root / "levels-again.png"),
              "two runs must produce byte-identical frames");

        // ---- an unknown world lists nothing and still draws ----------------------------------
        auto unknown = options;
        unknown.worldId = "no_such_world";
        unknown.snapshot = root / "levels-empty.png";
        const pvz::LevelSelectResult empty = pvz::runLevelSelect(catalog, reloaded, unknown);
        check(empty.levels == 0 && empty.rows.empty() && empty.selectedLevel.empty(),
              "an unknown world must list nothing, got " + std::to_string(empty.levels) + " rows");
        check(fs::file_size(root / "levels-empty.png") > 0,
              "an empty world must still produce a frame");

        // ---- a missing font is an error, not a blank window ---------------------------------
        bool rejected = false;
        try {
            auto broken = options;
            broken.assetRoot = assets / "missing";
            (void)pvz::runLevelSelect(catalog, reloaded, broken);
        } catch (const std::exception& error) {
            rejected = std::string(error.what()).find("font_zh.ttc") != std::string::npos;
        }
        check(rejected, "a missing font must fail with the font path in the message");

        std::cout << "level select render tests passed (levels=" << result.levels
                  << ", cleared=" << result.cleared << ", ink=" << ink << ")\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
