// The settings screen, rendered without a window: the PNG is the artifact and the JSON is the
// contract a caller reads back.
//
// This test is the desktop-only half of T85. `settings_test` covers the rules (keys, clamping, the
// save block) with no SDL at all; here the screen itself has to run: create a headless display, draw
// three rows, write a 1280x720 image, and hand back the same four numbers it painted. When the
// device is missing the audio side degrades to silence - the image and the JSON must still come out.
//
// Usage: settings_render_test <assets> <temp>

#include "catalog.hpp"
#include "settings_view.hpp"

#include <SDL3/SDL.h>
#include <SDL3_image/SDL_image.h>

#include <cstdio>
#include <filesystem>
#include <stdexcept>
#include <string>

namespace fs = std::filesystem;

namespace {

void check(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error(what);
}

/// Load the written image and report its size, so the test proves a real 1280x720 frame exists
/// instead of trusting that the file is non-empty.
void checkImage(const fs::path& file, int wantWidth, int wantHeight) {
    check(fs::is_regular_file(file), "the snapshot was not written: " + pvz::pathUtf8(file));
    // `path.string()` narrows through the ANSI code page, so a build tree under a Chinese
    // directory turns into mojibake and IMG_Load reports "no such file". Every other render
    // test already goes through pathUtf8.
    SDL_Surface* raw = IMG_Load(pvz::pathUtf8(file).c_str());
    check(raw != nullptr, "the snapshot is not a readable image: " + std::string(SDL_GetError()));
    const int width = raw->w;
    const int height = raw->h;
    SDL_DestroySurface(raw);
    check(width == wantWidth && height == wantHeight,
          "the settings screen must be " + std::to_string(wantWidth) + "x" +
              std::to_string(wantHeight) + ", got " + std::to_string(width) + "x" +
              std::to_string(height));
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: settings_render_test <assets> <temp>\n");
        return 2;
    }
    const fs::path assets = argv[1];
    const fs::path temp = argv[2];
    try {
        std::error_code ignored;
        fs::create_directories(temp, ignored);

        // The default frame: three rows at 100%, drawn from a headless display.
        const fs::path first = temp / "settings_default.png";
        fs::remove(first, ignored);
        const auto defaults = pvz::renderSettingsHeadless(assets, 2, first);
        check(defaults.is_object() && defaults.size() == 4,
              "the screen must report exactly four audio values, got " + defaults.dump());
        check(defaults["master"] == 100 && defaults["music"] == 100 && defaults["sfx"] == 100 &&
                  defaults["muted"] == false,
              "a headless run must start at the defaults, got " + defaults.dump());
        checkImage(first, 1280, 720);
        std::printf("settings_default: 1280x720 %s\n", defaults.dump().c_str());

        // A non-default state paints different numbers; the JSON has to follow the state it drew.
        const fs::path second = temp / "settings_custom.png";
        fs::remove(second, ignored);
        const auto custom =
            pvz::renderSettingsHeadless(assets, 1, second, pvz::AudioSettings{55, 20, 95, true});
        check(custom["master"] == 55 && custom["music"] == 20 && custom["sfx"] == 95 &&
                  custom["muted"] == true,
              "the screen must report the state it painted, got " + custom.dump());
        checkImage(second, 1280, 720);
        std::printf("settings_custom: 1280x720 %s\n", custom.dump().c_str());

        // Asking for no frames still has to produce one frame rather than an empty file.
        const fs::path third = temp / "settings_one_frame.png";
        fs::remove(third, ignored);
        const auto minimal = pvz::renderSettingsHeadless(assets, 0, third);
        check(minimal.size() == 4, "a zero-frame request must still report the values");
        checkImage(third, 1280, 720);
        std::printf("settings_one_frame: 1280x720 %s\n", minimal.dump().c_str());

        std::printf("settings render tests passed\n");
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "settings render test failed: %s\n", error.what());
        return 1;
    }
}
