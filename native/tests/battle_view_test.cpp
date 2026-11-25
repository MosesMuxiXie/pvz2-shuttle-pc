#include "battle_view.hpp"
#include <SDL3/SDL.h>
#include <SDL3_image/SDL_image.h>
#include <chrono>
#include <filesystem>
#include <iostream>
#include <set>
#include <stdexcept>
namespace fs = std::filesystem;
int main(int argc, char** argv) {
    try {
        if (argc != 4)
            throw std::runtime_error("expected content directory, assets directory and temp root");
        const auto catalog = pvz::loadCatalog(fs::path(argv[1]));
        const fs::path assets = argv[2];
        const auto root = fs::path(argv[3]) / fs::path(u8"战斗 渲染") /
                          std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
        fs::create_directories(root);
        pvz::runBattlePreview(catalog, assets, true, root / "battle.bmp");
        auto* frame = SDL_LoadBMP(pvz::pathUtf8(root / "battle.bmp").c_str());
        if (frame == nullptr)
            throw std::runtime_error(SDL_GetError());
        const bool size = frame->w == 1280 && frame->h == 720;
        std::set<Uint32> colors;
        for (int y = 0; y < frame->h; y += 4)
            for (int x = 0; x < frame->w; x += 4) {
                Uint8 r = 0, g = 0, b = 0, a = 0;
                if (SDL_ReadSurfacePixel(frame, x, y, &r, &g, &b, &a))
                    colors.insert((static_cast<Uint32>(r) << 16) | (static_cast<Uint32>(g) << 8) | b);
            }
        SDL_DestroySurface(frame);
        if (!size)
            throw std::runtime_error("battle snapshot is not 1280x720");
        if (colors.size() < 400)
            throw std::runtime_error("battle snapshot looks blank: only " + std::to_string(colors.size()) +
                                     " sampled colours");
        bool rejected = false;
        try {
            pvz::runBattlePreview(catalog, assets / "missing", true);
        } catch (const std::exception& error) {
            rejected = std::string(error.what()).find("frontyard.png") != std::string::npos;
        }
        if (!rejected)
            throw std::runtime_error("missing lawn was not reported");

        // ---- S4.0: `--play-script` drives the same kernel end to end and captures a frame. ----
        const auto repo = fs::path(argv[1]).parent_path();
        pvz::CatalogOptions options;
        const auto packPath = repo / "native" / "generated" / "content.pack";
        if (fs::is_regular_file(packPath))
            options.contentPack = packPath;
        else
            std::cerr << "warning: " << pvz::pathUtf8(packPath) << " missing; the script run uses JSON "
                      << "parameters only\n";
        const auto scriptCatalog = pvz::loadCatalog(fs::path(argv[1]), options);
        const auto script = pvz::engine::loadScript(repo / "native" / "tests" / "scripts" / "play_frontyard.json");
        pvz::PlayScriptOptions play;
        play.assetRoot = assets;
        play.snapshot = root / "play.png";
        play.seconds = 15;
        const auto stats = pvz::runPlayScript(scriptCatalog, "frontyard_1", script, play);
        const auto number = [&stats](const char* key) {
            const auto it = stats.find(key);
            return it == stats.end() || !it->is_number() ? -1LL : it->get<long long>();
        };
        const std::string status = stats.value("status", std::string{});
        if (number("planted") < 3)
            throw std::runtime_error("play-script planted " + std::to_string(number("planted")) +
                                     ", expected at least 3");
        if (number("collected") < 1)
            throw std::runtime_error("play-script collected " + std::to_string(number("collected")) +
                                     " suns, expected at least 1");
        if (status != "playing" && status != "won" && status != "lost")
            throw std::runtime_error("play-script reported an unknown status: " + status);
        if (number("tick") < 600)
            throw std::runtime_error("play-script stopped at tick " + std::to_string(number("tick")) +
                                     ", expected at least 600");
        if (number("snapshotBytes") <= 0)
            throw std::runtime_error("play-script wrote no snapshot");
        // The script asks for a second sunflower 2 ticks after the first (card still cooling
        // down) and a wallnut with 0 sun: both must be reported as refused, not dropped.
        if (number("rejectedInputs") < 2)
            throw std::runtime_error("play-script silently dropped refusals: rejectedInputs=" +
                                     std::to_string(number("rejectedInputs")));
        auto* playFrame = IMG_Load(pvz::pathUtf8(root / "play.png").c_str());
        if (playFrame == nullptr)
            throw std::runtime_error(std::string("play-script snapshot: ") + SDL_GetError());
        const bool playSize = playFrame->w == 1280 && playFrame->h == 720;
        SDL_DestroySurface(playFrame);
        if (!playSize)
            throw std::runtime_error("play-script snapshot is not 1280x720");
        std::cout << "PASS battle render 1280x720 after 1800 ticks, sampledColours=" << colors.size()
                  << ", missing lawn diagnosed\n";
        std::cout << "PASS play-script frontyard_1 tick=" << number("tick") << " planted=" << number("planted")
                  << " collected=" << number("collected") << " status=" << status
                  << " hash=" << stats.value("hash", std::string{})
                  << " snapshotBytes=" << number("snapshotBytes") << "\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
