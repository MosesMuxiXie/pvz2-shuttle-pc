#include "sdl_support.hpp"
#include "text.hpp"
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <vector>
namespace fs = std::filesystem;
int main(int argc, char** argv) {
    try {
        if (argc != 3)
            throw std::runtime_error("expected the assets directory and a temporary directory");
        const fs::path assets = argv[1];
        const fs::path temp = fs::path(argv[2]) / "文字 测试";
        fs::create_directories(temp);
        const auto font = assets / "ui/font_zh.ttc";
        pvz::sdl::Display display(true, "text test");
        auto* renderer = display.renderer.get();
        pvz::TextRenderer text(renderer, font);
        const auto decoded = pvz::decodeUtf8("阳光A");
        if (decoded.size() != 3 || decoded[0] != 0x9633 || decoded[1] != 0x5149 || decoded[2] != 'A')
            throw std::runtime_error("UTF-8 decoding is wrong");
        const float cjk = text.width("阳光", 32);
        const float latin = text.width("A", 32);
        if (cjk < 20.0f || latin < 8.0f)
            throw std::runtime_error("glyph advances are too small");
        if (text.lineHeight(32) < 32.0f)
            throw std::runtime_error("line height is too small");
        pvz::sdl::require(SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255), "clear");
        pvz::sdl::require(SDL_RenderClear(renderer), "clear");
        text.draw(20, 20, 48, SDL_Color{255, 255, 255, 255}, "阳光 25");
        const auto snapshot = temp / "text.bmp";
        pvz::sdl::snapshot(renderer, snapshot);
        auto* frame = SDL_LoadBMP(pvz::pathUtf8(snapshot).c_str());
        if (frame == nullptr)
            throw std::runtime_error(SDL_GetError());
        int lit = 0;
        for (int y = 0; y < frame->h; ++y)
            for (int x = 0; x < frame->w; ++x) {
                Uint8 r = 0, g = 0, b = 0, a = 0;
                if (SDL_ReadSurfacePixel(frame, x, y, &r, &g, &b, &a) && r > 128)
                    ++lit;
            }
        SDL_DestroySurface(frame);
        if (lit < 200)
            throw std::runtime_error("rendered text produced only " + std::to_string(lit) + " lit pixels");
        bool rejected = false;
        try {
            pvz::TextRenderer missing(renderer, assets / "ui/missing.ttc");
            (void)missing;
        } catch (const std::exception& error) {
            rejected = std::string(error.what()).find("missing font file") != std::string::npos;
        }
        if (!rejected)
            throw std::runtime_error("missing font was not diagnosed");
        std::cout << "PASS text face=" << text.faceIndex() << " cjkAdvance=" << cjk << " litPixels=" << lit
                  << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
