#include "menu_view.hpp"

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
    SDL_Color item = rgb(34, 47, 56);
    SDL_Color itemSelected = rgb(52, 82, 66);
    SDL_Color itemDisabled = rgb(28, 32, 37);
    SDL_Color ink = rgb(238, 238, 226);
    SDL_Color muted = rgb(150, 164, 168);
    SDL_Color accent = rgb(150, 216, 96);
    SDL_Color warn = rgb(226, 168, 96);
};

// One menu entry. `enabled` is decided once, from the save, so the picture and the JSON cannot
// disagree about whether "continue" was clickable.
struct Item {
    const char* label;
    MenuChoice choice;
    bool enabled;
};

void fill(SDL_Renderer* renderer, const SDL_FRect& rect, SDL_Color color) {
    sdl::require(SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a), "set draw color");
    sdl::require(SDL_RenderFillRect(renderer, &rect), "fill rectangle");
}

void border(SDL_Renderer* renderer, const SDL_FRect& rect, SDL_Color color) {
    sdl::require(SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a), "set draw color");
    sdl::require(SDL_RenderRect(renderer, &rect), "draw rectangle");
}

// Moves the cursor over the enabled items only. A disabled entry is skipped rather than landed on:
// the alternative is a cursor that stops on something Enter cannot do.
int step(const std::vector<Item>& items, int from, int direction) {
    int index = from;
    for (int guard = 0; guard < static_cast<int>(items.size()); ++guard) {
        index = (index + direction + static_cast<int>(items.size())) %
                static_cast<int>(items.size());
        if (items[static_cast<std::size_t>(index)].enabled) return index;
    }
    return from;
}

}  // namespace

const char* menuChoiceName(MenuChoice choice) {
    switch (choice) {
        case MenuChoice::continueGame: return "continue";
        case MenuChoice::worldMap: return "worldmap";
        case MenuChoice::almanac: return "almanac";
        case MenuChoice::garden: return "garden";
        case MenuChoice::achievements: return "achievements";
        case MenuChoice::daily: return "daily";
        case MenuChoice::settings: return "settings";
    case MenuChoice::shop: return "shop";
        case MenuChoice::quit: return "quit";
    }
    return "quit";
}

void saveScreenSnapshot(SDL_Renderer* renderer, const std::filesystem::path& path) {
    if (path.extension() == ".png" || path.extension() == ".PNG") {
        sdl::Surface pixels(SDL_RenderReadPixels(renderer, nullptr), SDL_DestroySurface);
        sdl::require(bool(pixels), "read frame");
        sdl::require(IMG_SavePNG(pixels.get(), pathUtf8(path).c_str()),
                     pathUtf8(path) + ": save snapshot");
        return;
    }
    sdl::snapshot(renderer, path);
}

MenuResult runMainMenu(const Catalog& catalog, const Progress& progress,
                       const MenuOptions& options) {
    (void)catalog;  // the menu is about the save, not the content: nothing here reads a level
    const auto fontFile = options.assetRoot / "ui/font_zh.ttc";
    if (!std::filesystem::is_regular_file(fontFile))
        throw std::runtime_error(pathUtf8(fontFile) + ": cannot open the Chinese font");

    // "Continue" means there is an attempt to resume. Stars alone are not enough: a save that only
    // holds keys (a shop purchase) has nothing to continue either.
    const bool hasAttempt = !progress.levels.empty();

    MenuResult result;
    result.continued = hasAttempt;
    result.stars = progress.totalStars();
    result.keys = progress.keys;
    result.cleared = progress.clearedLevels();

    // Nine entries, fixed order: the two that walk into the game first, then the browsable tables,
    // then the shop and the settings, then the way out. `items` is a vector rather than an array
    // because the count is a UI decision that changed twice (three -> eight -> nine); every loop
    // below already keys off `items.size()`.
    const std::vector<Item> items{
        {"继续游戏", MenuChoice::continueGame, hasAttempt},
        {"世界地图", MenuChoice::worldMap, true},
        {"图鉴", MenuChoice::almanac, true},
        {"花园", MenuChoice::garden, true},
        {"成就", MenuChoice::achievements, true},
        {"每日挑战", MenuChoice::daily, true},
        {"设置", MenuChoice::settings, true},
        {"商店", MenuChoice::shop, true},
        {"退出", MenuChoice::quit, true},
    };
    result.items = static_cast<int>(items.size());

    const bool headless = options.frames > 0;
    sdl::Display display(headless, "PvZ 2 SHUTTLE - Main menu");
    auto* renderer = display.renderer.get();
    TextRenderer text(renderer, fontFile);
    const Palette palette;
    // The menu is what the game sounds like before anything happens: one looping theme and a click
    // per cursor move. `headless` keeps a screenshot run away from the sound card entirely.
    attachAudio(options.assetRoot, headless);
    playAudioMenuMusic();

    int selected = 0;
    for (std::size_t i = 0; i < items.size(); ++i) {
        if (items[i].enabled) {
            selected = static_cast<int>(i);
            break;
        }
    }
    MenuChoice choice = items[static_cast<std::size_t>(selected)].choice;

    constexpr float kItemX = 400.0f;
    constexpr float kItemW = 480.0f;
    // Nine rows: 132 + 8*58 + 48 = 644, clear of the footer at 648. The three-row layout used
    // 88 px boxes at 112 px steps; the boxes shrank twice as the meta screens and the shop landed.
    constexpr float kItemH = 48.0f;
    constexpr float kItemY = 132.0f;
    constexpr float kItemStep = 58.0f;

    bool running = true;
    int frame = 0;
    while (running) {
        const int selectionBefore = selected;
        bool clicked = false;
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT || event.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED) {
                choice = MenuChoice::quit;
                running = false;
            } else if (event.type == SDL_EVENT_KEY_DOWN) {
                switch (event.key.key) {
                    case SDLK_ESCAPE:
                        choice = MenuChoice::quit;
                        running = false;
                        break;
                    case SDLK_DOWN:
                        selected = step(items, selected, +1);
                        break;
                    case SDLK_UP:
                        selected = step(items, selected, -1);
                        break;
                    case SDLK_RETURN:
                    case SDLK_KP_ENTER:
                        if (items[static_cast<std::size_t>(selected)].enabled) {
                            choice = items[static_cast<std::size_t>(selected)].choice;
                            running = false;
                        }
                        break;
                    default:
                        break;
                }
            } else if (event.type == SDL_EVENT_MOUSE_BUTTON_DOWN) {
                for (std::size_t i = 0; i < items.size(); ++i) {
                    const SDL_FRect rect{kItemX, kItemY + static_cast<float>(i) * kItemStep, kItemW,
                                         kItemH};
                    if (event.button.x >= rect.x && event.button.x <= rect.x + rect.w &&
                        event.button.y >= rect.y && event.button.y <= rect.y + rect.h &&
                        items[i].enabled) {
                        selected = static_cast<int>(i);
                        clicked = true;
                    }
                }
            }
        }

        // A held key must not machine-gun the mixer: one click per interaction, then top up.
        if (clicked || selected != selectionBefore) playAudioClick();
        pumpAudio();

        // The cursor's choice is the state, so a headless run reports what Enter would have done.
        choice = items[static_cast<std::size_t>(selected)].choice;

        fill(renderer, SDL_FRect{0, 0, kWidth, kHeight}, palette.page);
        fill(renderer, SDL_FRect{0, 0, kWidth, 76}, palette.panel);
        text.draw(40, 16, 32, palette.ink, "植物大战僵尸 2 · SHUTTLE 复刻");
        text.draw(40, 50, 16, palette.muted, "S4 主菜单 · 回车确认 · Esc 退出");

        const std::string stats = "★ " + std::to_string(result.stars) + "　钥匙 " +
                                  std::to_string(result.keys) + "　已通关 " +
                                  std::to_string(result.cleared) + " 关";
        text.draw(kWidth - 40 - text.width(stats, 22), 26, 22, palette.accent, stats);

        for (std::size_t i = 0; i < items.size(); ++i) {
            const SDL_FRect rect{kItemX, kItemY + static_cast<float>(i) * kItemStep, kItemW, kItemH};
            const bool isSelected = static_cast<int>(i) == selected;
            SDL_Color background = items[i].enabled ? palette.item : palette.itemDisabled;
            if (isSelected) background = items[i].enabled ? palette.itemSelected : palette.item;
            fill(renderer, rect, background);
            if (isSelected) border(renderer, rect, palette.accent);

            const SDL_Color inkColor = items[i].enabled ? palette.ink : palette.muted;
            text.draw(rect.x + 28, rect.y + 16, 26, inkColor, items[i].label);
            if (!items[i].enabled) {
                // Says *why* it cannot be picked: a greyed-out "continue" with no reason reads as
                // a bug rather than as "you have not played yet".
                text.draw(rect.x + 28 + text.width(items[i].label, 26) + 16, rect.y + 20, 16,
                          palette.warn, "没有可继续的存档");
            }
        }

        text.draw(40, 648, 18, palette.muted, "↑↓ 选择 · 回车确认 · Esc 退出");
        if (!options.progressFile.empty()) {
            text.draw(40, 680, 16, palette.muted, "存档：" + pathUtf8(options.progressFile));
        }

        result.selected = selected;
        result.selectedRect = ScreenRect{kItemX, kItemY + static_cast<float>(selected) * kItemStep,
                                         kItemW, kItemH};
        result.choice = choice;

        if (!options.snapshot.empty()) saveScreenSnapshot(renderer, options.snapshot);
        sdl::require(SDL_RenderPresent(renderer), "present main menu");
        ++frame;
        if (headless && frame >= options.frames) break;
        if (!headless) SDL_Delay(16);
    }

    result.choice = choice;
    return result;
}

}  // namespace pvz
