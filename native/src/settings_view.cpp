#include "settings_view.hpp"

#include "audio/audio_runtime.hpp"
#include "sdl_support.hpp"
#include "text.hpp"

#include <algorithm>
#include <stdexcept>
#include <string>
#include <vector>

namespace pvz {
namespace {

constexpr float kWidth = 1280.0f;
constexpr float kHeight = 720.0f;

SDL_Color rgb(int r, int g, int b, int a = 255) {
    return SDL_Color{static_cast<Uint8>(r), static_cast<Uint8>(g), static_cast<Uint8>(b),
                     static_cast<Uint8>(a)};
}

struct Palette {
    SDL_Color page = rgb(16, 24, 30);
    SDL_Color panel = rgb(26, 37, 45);
    SDL_Color row = rgb(34, 47, 56);
    SDL_Color rowSelected = rgb(52, 82, 66);
    SDL_Color ink = rgb(238, 238, 226);
    SDL_Color muted = rgb(150, 164, 168);
    SDL_Color accent = rgb(150, 216, 96);
    SDL_Color warn = rgb(226, 168, 96);
};

void fill(SDL_Renderer* renderer, const SDL_FRect& rect, SDL_Color color) {
    sdl::require(SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a), "set draw color");
    sdl::require(SDL_RenderFillRect(renderer, &rect), "fill rectangle");
}

void border(SDL_Renderer* renderer, const SDL_FRect& rect, SDL_Color color) {
    sdl::require(SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a), "set draw color");
    sdl::require(SDL_RenderRect(renderer, &rect), "draw rectangle");
}

void snapshotTo(SDL_Renderer* renderer, const std::filesystem::path& path) {
    if (path.extension() == ".png" || path.extension() == ".PNG") {
        sdl::Surface pixels(SDL_RenderReadPixels(renderer, nullptr), SDL_DestroySurface);
        sdl::require(bool(pixels), "read frame");
        sdl::require(IMG_SavePNG(pixels.get(), pathUtf8(path).c_str()),
                     pathUtf8(path) + ": save snapshot");
        return;
    }
    sdl::snapshot(renderer, path);
}

const char* rowLabel(int row) {
    switch (static_cast<SettingsRow>(row)) {
        case SettingsRow::master: return "主音量";
        case SettingsRow::music: return "音乐";
        case SettingsRow::sfx: return "音效";
    }
    return "主音量";
}

/// The value bar: a track plus a filled portion, so a screenshot shows the number twice (bar and
/// digits) and a mis-set bar is visible instead of silent.
void drawBar(SDL_Renderer* renderer, const SDL_FRect& track, int percent, const Palette& palette) {
    fill(renderer, track, palette.page);
    border(renderer, track, palette.row);
    const float ratio = static_cast<float>(std::clamp(percent, 0, 100)) / 100.0F;
    if (ratio <= 0.0F) return;
    SDL_FRect inner{track.x + 2.0F, track.y + 2.0F, (track.w - 4.0F) * ratio, track.h - 4.0F};
    fill(renderer, inner, palette.accent);
}

}  // namespace

SettingsResult runSettingsScreen(const SettingsOptions& options) {
    const auto fontFile = options.assetRoot / "ui/font_zh.ttc";
    if (!std::filesystem::is_regular_file(fontFile))
        throw std::runtime_error(pathUtf8(fontFile) + ": cannot open the Chinese font");

    SettingsResult result;
    result.rows = kSettingsRowCount;
    result.state = options.state;

    const bool headless = options.frames > 0;
    sdl::Display display(headless, "PvZ 2 SHUTTLE - Settings");
    auto* renderer = display.renderer.get();
    TextRenderer text(renderer, fontFile);
    const Palette palette;

    // Same rule as every other screen: a headless run stays away from the sound card, and the
    // settings still take effect on the runtime so the values leave this function as state, not as
    // pixels only.
    attachAudio(options.assetRoot, headless);
    applyAudioSettingsProcess(result.state.audio);

    constexpr float kRowX = 260.0f;
    constexpr float kRowW = 760.0f;
    constexpr float kRowH = 96.0f;
    constexpr float kRowY = 200.0f;
    constexpr float kRowStep = 116.0f;
    constexpr float kBarX = 640.0f;
    constexpr float kBarW = 320.0f;
    constexpr float kBarH = 26.0f;

    bool running = true;
    int frame = 0;
    while (running) {
        bool clicked = false;
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT || event.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED) {
                running = false;
            } else if (event.type == SDL_EVENT_KEY_DOWN) {
                SettingsKey key = SettingsKey::none;
                switch (event.key.key) {
                    case SDLK_UP: key = SettingsKey::up; break;
                    case SDLK_DOWN: key = SettingsKey::down; break;
                    case SDLK_LEFT: key = SettingsKey::left; break;
                    case SDLK_RIGHT: key = SettingsKey::right; break;
                    case SDLK_M: key = SettingsKey::mute; break;
                    case SDLK_ESCAPE: key = SettingsKey::back; break;
                    default: break;
                }
                if (key != SettingsKey::none) {
                    const SettingsStepResult step = applySettingsKey(result.state, key);
                    result.state = step.state;
                    if (step.closed) {
                        result.closed = true;
                        running = false;
                    }
                    if (step.changed) {
                        // Audible before the next frame: the player hears the bus they are moving.
                        applyAudioSettingsProcess(result.state.audio);
                        clicked = true;
                    }
                    if (step.moved) clicked = true;
                }
            }
        }

        if (clicked) playAudioClick();
        pumpAudio();

        fill(renderer, SDL_FRect{0, 0, kWidth, kHeight}, palette.page);
        fill(renderer, SDL_FRect{0, 0, kWidth, 76}, palette.panel);
        text.draw(40, 16, 32, palette.ink, "植物大战僵尸 2 · SHUTTLE 复刻");
        text.draw(40, 50, 16, palette.muted, "设置 · ←→ 调整 · ↑↓ 换行 · M 静音 · Esc 返回");

        for (int row = 0; row < kSettingsRowCount; ++row) {
            const SDL_FRect rect{kRowX, kRowY + static_cast<float>(row) * kRowStep, kRowW, kRowH};
            const bool selected = row == result.state.rowIndex();
            fill(renderer, rect, selected ? palette.rowSelected : palette.row);
            if (selected) border(renderer, rect, palette.accent);

            const SettingsState probe = [&] {
                SettingsState copy = result.state;
                copy.row = row;
                return copy;
            }();
            // The label and its hint are stacked inside a 96 px row: the label owns the
            // top half, the hint the bottom. Drawing the hint at +66 put it inside the
            // label's line box (the drawer advances by line height, not font size), so
            // the two ran together in the screenshot.
            text.draw(rect.x + 28, rect.y + 14, 30, palette.ink, rowLabel(row));

            const SDL_FRect track{kBarX, rect.y + 28, kBarW, kBarH};
            drawBar(renderer, track, probe.value(), palette);
            text.draw(track.x + track.w + 24, rect.y + 24, 26, palette.ink,
                      std::to_string(probe.value()) + "%");
            text.draw(rect.x + 28, rect.y + 74, 15, palette.muted,
                      "←→ 每次 5%（当前行）");
        }

        if (result.state.audio.muted) {
            text.draw(kRowX, kRowY + 3.0F * kRowStep + 8, 26, palette.warn, "已静音（M 取消）");
        } else {
            text.draw(kRowX, kRowY + 3.0F * kRowStep + 8, 26, palette.muted, "未静音");
        }

        const std::string line = "存档：主 " + std::to_string(result.state.audio.master) + " · 音乐 " +
                                 std::to_string(result.state.audio.music) + " · 音效 " +
                                 std::to_string(result.state.audio.sfx) +
                                 (result.state.audio.muted ? " · 静音" : "");
        text.draw(40, 648, 18, palette.muted, line);
        if (!options.snapshot.empty()) {
            text.draw(40, 676, 16, palette.muted, "截图：" + pathUtf8(options.snapshot));
        }

        if (!options.snapshot.empty()) snapshotTo(renderer, options.snapshot);
        sdl::require(SDL_RenderPresent(renderer), "present settings screen");
        ++frame;
        if (headless && frame >= options.frames) break;
        if (!headless) SDL_Delay(16);
    }

    result.frames = frame;
    return result;
}

nlohmann::json renderSettingsHeadless(const std::filesystem::path& assetRoot, int frames,
                                      const std::filesystem::path& snapshot,
                                      const AudioSettings& start) {
    SettingsOptions options;
    options.assetRoot = assetRoot;
    options.state.audio = clampAudioSettings(start);
    options.snapshot = snapshot;
    options.frames = std::max(1, frames);
    const SettingsResult result = runSettingsScreen(options);
    // The runtime already has the values; write them into the save is the caller's job (it owns
    // the `--progress` file). Returning the JSON keeps this function free of file policy.
    return result.json();
}

}  // namespace pvz
