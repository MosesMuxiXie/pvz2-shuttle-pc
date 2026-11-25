#include "launcher.hpp"
#include "audio/audio_runtime.hpp"
#include "sdl_support.hpp"
#include <algorithm>
namespace pvz {
void runLauncher(const std::filesystem::path& assetRoot, bool smokeTest,
                 const std::filesystem::path& snapshot) {
    const auto file = assetRoot / "ui/launcher.png";
    if (!std::filesystem::is_regular_file(file))
        throw std::runtime_error(pathUtf8(file) + ": cannot open launcher artwork");
    sdl::Display display(smokeTest, "PvZ 2 SHUTTLE - Native preview");
    auto* renderer = display.renderer.get();
    auto art = sdl::texture(renderer, file);
    float width = 0, height = 0;
    sdl::require(SDL_GetTextureSize(art.get(), &width, &height), "read artwork dimensions");
    const float scale = std::min(1280.0f / width, 720.0f / height);
    const SDL_FRect destination{(1280 - width * scale) / 2, (720 - height * scale) / 2, width * scale,
                                height * scale};
    // The launcher is the first screen with a sound: the menu theme starts with it. `smokeTest`
    // means "render one frame for a screenshot", which attaches in `headless` mode and therefore
    // never opens a device.
    attachAudio(assetRoot, smokeTest);
    playAudioMenuMusic();
    bool running = true;
    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event))
            if (event.type == SDL_EVENT_QUIT || event.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED ||
                (event.type == SDL_EVENT_KEY_DOWN && event.key.key == SDLK_ESCAPE))
                running = false;
        sdl::require(SDL_SetRenderDrawColor(renderer, 12, 18, 22, 255), "set clear color");
        sdl::require(SDL_RenderClear(renderer), "clear launcher");
        sdl::require(SDL_RenderTexture(renderer, art.get(), nullptr, &destination), "render launcher");
        if (!snapshot.empty())
            sdl::snapshot(renderer, snapshot);
        sdl::require(SDL_RenderPresent(renderer), "present launcher");
        pumpAudio();
        if (smokeTest)
            break;
        SDL_Delay(16);
    }
}
} // namespace pvz
