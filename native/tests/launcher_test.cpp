#include "catalog.hpp"
#include "launcher.hpp"
#include <SDL3/SDL.h>
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
namespace fs = std::filesystem;
void check(bool ok, const std::string& msg) {
    if (!ok)
        throw std::runtime_error(msg);
}
#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    try {
        check(argc == 3, "expected fixture PNG and temp directory");
        const auto root = fs::path(argv[2]) / fs::path(u8"启动 窗口") /
                          std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
        fs::create_directories(root / "ui");
        fs::copy_file(fs::path(argv[1]), root / "ui/launcher.png");
        const auto snapshot = root / "frame.bmp";
        pvz::runLauncher(root, true, snapshot);
        auto* pixels = SDL_LoadBMP(pvz::pathUtf8(snapshot).c_str());
        check(pixels != nullptr, "snapshot must decode");
        check(pixels->w == 1280 && pixels->h == 720, "logical frame size");
        auto pixel = [&](int x, int y, int er, int eg, int eb) {
            Uint8 r = 0, g = 0, b = 0, a = 0;
            check(SDL_ReadSurfacePixel(pixels, x, y, &r, &g, &b, &a), "read pixel");
            check(std::abs(int(r) - er) <= 2 && std::abs(int(g) - eg) <= 2 && std::abs(int(b) - eb) <= 2 &&
                      a == 255,
                  "pixel mismatch at " + std::to_string(x) + "," + std::to_string(y));
        };
        pixel(10, 10, 12, 18, 22);
        pixel(320, 200, 255, 0, 0);
        pixel(960, 200, 0, 255, 0);
        pixel(320, 520, 0, 0, 255);
        pixel(960, 520, 255, 255, 255);
        SDL_DestroySurface(pixels);
        std::ofstream(root / "ui/launcher.png") << "not an image";
        bool rejected = false;
        try {
            pvz::runLauncher(root, true);
        } catch (const std::exception& e) {
            rejected = std::string(e.what()).find("launcher.png") != std::string::npos;
        }
        check(rejected, "invalid artwork must fail with path");
        rejected = false;
        try {
            pvz::runLauncher(root / "missing", true);
        } catch (const std::exception& e) {
            rejected = std::string(e.what()).find("launcher.png") != std::string::npos;
        }
        check(rejected, "missing artwork must fail with path");
        std::cout << "PASS software render, pixels, aspect ratio, Unicode paths and artwork failures\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "FAIL " << e.what() << '\n';
        return 1;
    }
}
