#include "launcher.hpp"

#include "catalog.hpp"

#include <SDL3/SDL.h>
#include <SDL3_image/SDL_image.h>

#include <algorithm>
#include <memory>
#include <stdexcept>
#include <string>

namespace shuttle {

namespace {

constexpr int canvasWidth = 1280;
constexpr int canvasHeight = 720;

void requireSdl(bool success, const std::string& operation) {
    if (!success) {
        throw std::runtime_error(operation + ": " + SDL_GetError());
    }
}

struct VideoSession {
    VideoSession() {
        requireSdl(SDL_Init(SDL_INIT_VIDEO), "initialize SDL video");
    }

    ~VideoSession() {
        SDL_Quit();
    }
};

void drawLauncher(SDL_Renderer* renderer, SDL_Texture* texture, const SDL_FRect& destination) {
    requireSdl(SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255), "set launcher background");
    requireSdl(SDL_RenderClear(renderer), "clear launcher frame");
    requireSdl(SDL_RenderTexture(renderer, texture, nullptr, &destination), "render launcher artwork");
    requireSdl(SDL_RenderPresent(renderer), "present launcher frame");
}

}

void runLauncher(const std::filesystem::path& assetRoot, bool smokeTest) {
    const auto artwork = assetRoot / "ui" / "launcher.png";
    const auto artworkPath = utf8Path(artwork);
    if (!std::filesystem::is_regular_file(artwork)) {
        throw std::runtime_error(artworkPath + ": launcher artwork is missing");
    }

    const VideoSession video;
    const auto flags = smokeTest ? SDL_WINDOW_HIDDEN : SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY;
    const std::unique_ptr<SDL_Window, decltype(&SDL_DestroyWindow)> window(
        SDL_CreateWindow("PvZ 2 SHUTTLE", canvasWidth, canvasHeight, flags), SDL_DestroyWindow);
    requireSdl(window != nullptr, "create launcher window");

    const std::unique_ptr<SDL_Renderer, decltype(&SDL_DestroyRenderer)> renderer(
        SDL_CreateRenderer(window.get(), smokeTest ? "software" : nullptr), SDL_DestroyRenderer);
    requireSdl(renderer != nullptr, "create launcher renderer");
    requireSdl(SDL_SetRenderLogicalPresentation(renderer.get(), canvasWidth, canvasHeight,
                                                 SDL_LOGICAL_PRESENTATION_LETTERBOX),
               "set launcher viewport");

    const std::unique_ptr<SDL_Texture, decltype(&SDL_DestroyTexture)> texture(
        IMG_LoadTexture(renderer.get(), artworkPath.c_str()), SDL_DestroyTexture);
    requireSdl(texture != nullptr, "load " + artworkPath);
    float width = 0;
    float height = 0;
    requireSdl(SDL_GetTextureSize(texture.get(), &width, &height), "read launcher artwork size");
    const float scale = std::min(canvasWidth / width, canvasHeight / height);
    width *= scale;
    height *= scale;
    const SDL_FRect destination{(canvasWidth - width) / 2, (canvasHeight - height) / 2, width, height};
    drawLauncher(renderer.get(), texture.get(), destination);
    if (smokeTest) {
        return;
    }

    for (;;) {
        SDL_Event event{};
        requireSdl(SDL_WaitEvent(&event), "wait for launcher input");
        if (event.type == SDL_EVENT_QUIT || event.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED) {
            return;
        }
        if (event.type == SDL_EVENT_WINDOW_EXPOSED || event.type == SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED) {
            drawLauncher(renderer.get(), texture.get(), destination);
        }
    }
}

}
