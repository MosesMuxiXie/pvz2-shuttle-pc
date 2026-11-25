// Render test for the main menu.
//
// Four separate things, because "a PNG appeared" proves none of them on its own:
//   * the save decides what the cursor starts on (a fresh save cannot continue, a played one can),
//   * the frame is a real 1280x720 picture,
//   * two runs of the same state are byte-identical,
//   * the selected item actually has glyphs inside its rectangle — a menu drawn without text is
//     the one failure a colour histogram cannot see,
//   * a missing font fails loudly with its path in the message.

#include "menu_view.hpp"
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
    if (!condition) throw std::runtime_error("menu render test failed: " + message);
}

std::vector<std::uint8_t> readBytes(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    if (!in) throw std::runtime_error("cannot read " + pvz::pathUtf8(file));
    return std::vector<std::uint8_t>(std::istreambuf_iterator<char>(in),
                                     std::istreambuf_iterator<char>());
}

// Counts pixels inside `rect` (inset by `inset` on every side) whose colour differs from the
// rectangle's own background by more than `threshold` on any channel. Glyphs are the only thing
// that produces such pixels in the middle of a menu item, so a zero count means "the text did not
// draw" — exactly the failure a font size of 0 produces.
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
    check(x1 > x0 && y1 > y0, "the selected rectangle must be sampleable");

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

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 4) {
            throw std::runtime_error("expected content directory, assets directory and temp root");
        }
        const fs::path content = argv[1];
        const fs::path assets = argv[2];
        // An ASCII fixture directory on purpose: a narrow source literal such as "主菜单" is read
        // through the machine's ANSI code page, and on a non-Chinese code page the STL throws
        // "no mapping for the Unicode character" before a single frame is drawn.
        const auto root = fs::path(argv[3]) / fs::path("menu-render") /
                          std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
        fs::create_directories(root);

        const pvz::Catalog catalog = pvz::loadCatalog(content);

        // ---- a fresh save: nothing to continue, so the cursor starts on the world map --------
        pvz::MenuOptions options;
        options.assetRoot = assets;
        options.frames = 2;
        options.snapshot = root / "menu-fresh.png";
        const pvz::Progress fresh;
        const pvz::MenuResult freshResult = pvz::runMainMenu(catalog, fresh, options);
        check(freshResult.items == 3, "the menu must draw three items, got " +
                                          std::to_string(freshResult.items));
        check(!freshResult.continued, "an empty save cannot continue a game");
        check(freshResult.selected == 1,
              "the cursor must skip the disabled item and land on the world map, got " +
                  std::to_string(freshResult.selected));
        check(freshResult.choice == pvz::MenuChoice::worldMap,
              std::string("a fresh save leaves the menu on the world map, got ") +
                  pvz::menuChoiceName(freshResult.choice));
        check(freshResult.cleared == 0, "a fresh save has cleared nothing");

        // Only the label band is measured. The first version sampled the whole card and a font size
        // of 0 still reported ~580 "ink" pixels from the card's rounded edge, so a menu with no text
        // at all passed. The band holds nothing but the label, which makes the count mean its name.
        const pvz::ScreenRect& card = freshResult.selectedRect;
        const pvz::ScreenRect band{card.x + 20.0f, card.y + 18.0f, 240.0f, 46.0f};
        int width = 0, height = 0;
        const std::size_t ink = inkPixels(root / "menu-fresh.png", band, 4, 40, &width, &height);
        check(width == 1280 && height == 720,
              "snapshot is " + std::to_string(width) + "x" + std::to_string(height));
        // Measured: 583 with the label, 274 with the font size forced to 0 (the band's rounded
        // edge). 420 sits between them with room on both sides.
        check(ink >= 420, "the selected item must carry glyphs, only " + std::to_string(ink) +
                              " ink pixels inside its rectangle");

        // ---- a played save: 继续游戏 becomes selectable and wins the cursor ------------------
        pvz::Progress played;
        played.keys = 2;
        pvz::LevelRecord record;
        record.cleared = true;
        record.stars = 3;
        record.attempts = 2;
        record.bestTick = 1800;
        played.levels["frontyard_1"] = record;
        const fs::path saveFile = root / "save.json";
        pvz::saveProgress(saveFile, played, 0);
        const pvz::Progress reloaded = pvz::loadProgress(saveFile);
        check(reloaded.totalStars() == 3, "the fixture save must reload with three stars");

        auto playedOptions = options;
        playedOptions.progressFile = saveFile;
        playedOptions.snapshot = root / "menu-played.png";
        const pvz::MenuResult playedResult = pvz::runMainMenu(catalog, reloaded, playedOptions);
        check(playedResult.continued, "a save with attempts must offer 继续游戏");
        check(playedResult.selected == 0, "with something to continue the cursor starts there");
        check(playedResult.choice == pvz::MenuChoice::continueGame,
              std::string("a played save leaves the menu on continue, got ") +
                  pvz::menuChoiceName(playedResult.choice));
        check(playedResult.stars == 3 && playedResult.keys == 2 && playedResult.cleared == 1,
              "the header must show the save's stars, keys and cleared levels, got " +
                  std::to_string(playedResult.stars) + "/" + std::to_string(playedResult.keys) +
                  "/" + std::to_string(playedResult.cleared));

        // ---- determinism: the same save and the same frame count must give the same bytes ----
        auto again = playedOptions;
        again.snapshot = root / "menu-played-again.png";
        const pvz::MenuResult second = pvz::runMainMenu(catalog, reloaded, again);
        check(second.choice == playedResult.choice && second.selected == playedResult.selected,
              "two runs of the same save must agree");
        check(readBytes(root / "menu-played.png") == readBytes(root / "menu-played-again.png"),
              "two runs must produce byte-identical frames");

        // ---- a missing font is an error, not a blank window ---------------------------------
        bool rejected = false;
        try {
            auto broken = options;
            broken.assetRoot = assets / "missing";
            (void)pvz::runMainMenu(catalog, fresh, broken);
        } catch (const std::exception& error) {
            rejected = std::string(error.what()).find("font_zh.ttc") != std::string::npos;
        }
        check(rejected, "a missing font must fail with the font path in the message");

        std::cout << "menu render tests passed (ink=" << ink << ")\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
