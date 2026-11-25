#include "level_select_view.hpp"

#include "audio/audio_runtime.hpp"
#include "sdl_support.hpp"
#include "text.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>

namespace pvz {
namespace {

constexpr float kWidth = 1280.0f;
constexpr float kHeight = 720.0f;
constexpr int kVisibleRows = 14;

SDL_Color rgb(int r, int g, int b, int a = 255) {
    return SDL_Color{static_cast<Uint8>(r), static_cast<Uint8>(g), static_cast<Uint8>(b),
                     static_cast<Uint8>(a)};
}

struct Palette {
    SDL_Color page = rgb(16, 24, 30);
    SDL_Color panel = rgb(26, 37, 45);
    SDL_Color row = rgb(34, 47, 56);
    SDL_Color rowSelected = rgb(52, 82, 66);
    SDL_Color rowCleared = rgb(30, 46, 40);
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

std::string starText(int stars) {
    if (stars <= 0) return "-";
    return std::string(static_cast<std::size_t>(stars), '*') + " " + std::to_string(stars);
}

// The list is built once, from the catalog and the save, so the picture and the JSON row set are
// the same data. Sorted by the level's own `index` (the order the world plays it in), then by id so
// two levels that share an index cannot swap places between runs.
std::vector<LevelSelectRow> buildRows(const Catalog& catalog, const Progress& progress,
                                      const std::string& world) {
    std::vector<LevelSelectRow> rows;
    for (const auto& entry : catalog.levels) {
        if (entry.second.world != world) continue;
        LevelSelectRow row;
        row.id = entry.first;
        row.index = entry.second.index;
        row.title = entry.second.title;
        if (const LevelRecord* record = progress.find(entry.first)) {
            row.stars = record->stars;
            row.cleared = record->cleared;
        }
        rows.push_back(std::move(row));
    }
    std::sort(rows.begin(), rows.end(), [](const LevelSelectRow& a, const LevelSelectRow& b) {
        if (a.index != b.index) return a.index < b.index;
        return a.id < b.id;
    });
    return rows;
}

}  // namespace

LevelSelectResult runLevelSelect(const Catalog& catalog, const Progress& progress,
                                 const LevelSelectOptions& options) {
    const auto fontFile = options.assetRoot / "ui/font_zh.ttc";
    if (!std::filesystem::is_regular_file(fontFile))
        throw std::runtime_error(pathUtf8(fontFile) + ": cannot open the Chinese font");

    LevelSelectResult result;
    result.world = options.worldId;
    result.keys = progress.keys;
    result.stars = progress.totalStars();
    result.rows = buildRows(catalog, progress, options.worldId);
    result.levels = static_cast<int>(result.rows.size());
    for (const LevelSelectRow& row : result.rows) {
        if (row.cleared) ++result.cleared;
    }

    const bool headless = options.frames > 0;
    sdl::Display display(headless, "PvZ 2 SHUTTLE - Levels");
    auto* renderer = display.renderer.get();
    TextRenderer text(renderer, fontFile);
    const Palette palette;
    // A menu screen: looping theme plus one click per cursor move. A headless run attaches in
    // `headless` mode, so a screenshot never opens an audio device.
    attachAudio(options.assetRoot, headless);
    playAudioMenuMusic();

    constexpr float kListX = 80.0f;
    constexpr float kListW = 720.0f;
    constexpr float kRowH = 32.0f;
    constexpr float kRowStep = 36.0f;
    constexpr float kFirstRowY = 120.0f;

    int selected = 0;
    bool entered = result.levels > 0;  // headless reports what Enter would pick
    bool running = true;
    int frame = 0;
    while (running) {
        const int selectionBefore = selected;
        bool clicked = false;
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT || event.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED) {
                entered = false;
                running = false;
            } else if (event.type == SDL_EVENT_KEY_DOWN) {
                const int last = result.levels - 1;
                switch (event.key.key) {
                    case SDLK_ESCAPE:
                        entered = false;
                        running = false;
                        break;
                    case SDLK_DOWN:
                        if (selected < last) ++selected;
                        break;
                    case SDLK_UP:
                        if (selected > 0) --selected;
                        break;
                    case SDLK_PAGEDOWN:
                        selected = std::min(last, selected + kVisibleRows);
                        break;
                    case SDLK_PAGEUP:
                        selected = std::max(0, selected - kVisibleRows);
                        break;
                    case SDLK_RETURN:
                    case SDLK_KP_ENTER:
                        if (result.levels > 0) {
                            entered = true;
                            running = false;
                        }
                        break;
                    default:
                        break;
                }
            } else if (event.type == SDL_EVENT_MOUSE_BUTTON_DOWN) {
                for (int i = 0; i < result.levels && i - 0 < result.levels; ++i) {
                    const SDL_FRect rect{kListX, kFirstRowY + static_cast<float>(i) * kRowStep,
                                         kListW, kRowH};
                    if (event.button.x >= rect.x && event.button.x <= rect.x + rect.w &&
                        event.button.y >= rect.y && event.button.y <= rect.y + rect.h) {
                        // The window scrolls, so a click has to be mapped back through it.
                        const int offset = std::clamp(selected - kVisibleRows / 2, 0,
                                                      std::max(0, result.levels - kVisibleRows));
                        selected = std::clamp(offset + i, 0, result.levels - 1);
                        clicked = true;
                    }
                }
            }
        }

        // One click per interaction, then top the device queue back up: a held key must not
        // machine-gun the mixer.
        if (clicked || selected != selectionBefore) playAudioClick();
        pumpAudio();

        fill(renderer, SDL_FRect{0, 0, kWidth, kHeight}, palette.page);
        fill(renderer, SDL_FRect{0, 0, kWidth, 76}, palette.panel);
        text.draw(40, 16, 30, palette.ink, "选择关卡");
        text.draw(200, 24, 20, palette.muted,
                  options.worldId + " · 共 " + std::to_string(result.levels) + " 关 · 已通关 " +
                      std::to_string(result.cleared));
        const std::string stats = "★ " + std::to_string(result.stars) + "　钥匙 " +
                                  std::to_string(result.keys);
        text.draw(kWidth - 40 - text.width(stats, 22), 26, 22, palette.accent, stats);

        if (result.levels == 0) {
            text.draw(kListX, kFirstRowY + 20, 24, palette.warn,
                      "该世界没有关卡：" + options.worldId);
        } else {
            // 14 rows fill 120..624; the same window keeps the cursor visible without a scrollbar
            // the screen could not test.
            const int offset = std::clamp(selected - kVisibleRows / 2, 0,
                                          std::max(0, result.levels - kVisibleRows));
            const int last = std::min(result.levels, offset + kVisibleRows);
            for (int i = offset; i < last; ++i) {
                const LevelSelectRow& row = result.rows[static_cast<std::size_t>(i)];
                const SDL_FRect rect{kListX, kFirstRowY + static_cast<float>(i - offset) * kRowStep,
                                     kListW, kRowH};
                SDL_Color background = row.cleared ? palette.rowCleared : palette.row;
                if (i == selected) background = palette.rowSelected;
                fill(renderer, rect, background);
                if (i == selected) border(renderer, rect, palette.accent);

                const std::string order = "#" + std::to_string(row.index);
                text.draw(rect.x + 12, rect.y + 6, 20, palette.muted, order);
                text.draw(rect.x + 90, rect.y + 6, 20, palette.ink, row.id);
                const std::string stars = starText(row.stars);
                text.draw(rect.x + 420, rect.y + 8, 18, palette.accent, stars);
                const std::string state = row.cleared ? "已通关" : "未通关";
                text.draw(rect.x + kListW - 12 - text.width(state, 18), rect.y + 8, 18,
                          row.cleared ? palette.accent : palette.muted, state);

                if (i == selected) {
                    result.selectedRect =
                        ScreenRect{rect.x, rect.y, rect.w, rect.h};
                }
            }
            text.draw(kListX, kFirstRowY + static_cast<float>(kVisibleRows) * kRowStep + 14, 16,
                      palette.muted,
                      "显示 " + std::to_string(offset + 1) + " - " + std::to_string(last) + " / " +
                          std::to_string(result.levels));
        }

        // Detail panel: what Enter would start, spelled out, so the CLI's `selected` id is visible
        // on screen too.
        fill(renderer, SDL_FRect{840, 120, 400, 500}, palette.panel);
        border(renderer, SDL_FRect{840, 120, 400, 500}, palette.muted);
        if (result.levels > 0) {
            const LevelSelectRow& row = result.rows[static_cast<std::size_t>(selected)];
            float y = 140;
            text.draw(864, y, 28, palette.ink, row.id);
            y += 44;
            text.draw(864, y, 18, palette.muted, "世界 " + options.worldId + " · 序号 " +
                                                     std::to_string(row.index));
            y += 30;
            if (!row.title.empty()) {
                // The title is the only free-form string on this screen ("Your House - Chapter 1 -
                // Day 1" already overruns the 352-pixel panel body), so it is the only one that
                // needs wrapping; everything else is a number or an id.
                const std::string title = row.title;
                std::size_t start = 0;
                for (int line = 0; line < 2 && start < title.size(); ++line) {
                    std::size_t end = title.size();
                    while (end > start + 1 && text.width(title.substr(start, end - start), 18) > 352) {
                        const std::size_t space = title.rfind(' ', end - 1);
                        end = (space == std::string::npos || space <= start) ? end - 1 : space;
                    }
                    text.draw(864, y, 18, palette.muted, title.substr(start, end - start));
                    y += 26;
                    start = end;
                    while (start < title.size() && title[start] == ' ') ++start;
                }
            }
            text.draw(864, y, 20, palette.accent, "星数 " + std::to_string(row.stars));
            y += 32;
            text.draw(864, y, 20, row.cleared ? palette.accent : palette.muted,
                      row.cleared ? "已通关" : "未通关");
            y += 40;
            text.draw(864, y, 18, palette.ink, "回车开始这一关");
        } else {
            text.draw(864, 140, 20, palette.warn, "没有可选的关卡");
        }

        text.draw(40, 664, 18, palette.muted, "↑↓ 选择 · PgUp/PgDn 翻页 · 回车开始 · Esc 返回");
        if (!options.progressFile.empty()) {
            text.draw(40, 692, 16, palette.muted, "存档：" + pathUtf8(options.progressFile));
        }

        result.selected = selected;
        if (result.levels > 0 && entered) {
            result.selectedLevel = result.rows[static_cast<std::size_t>(selected)].id;
        } else {
            result.selectedLevel.clear();
        }

        if (!options.snapshot.empty()) saveScreenSnapshot(renderer, options.snapshot);
        sdl::require(SDL_RenderPresent(renderer), "present level list");
        ++frame;
        if (headless && frame >= options.frames) break;
        if (!headless) SDL_Delay(16);
    }

    return result;
}

}  // namespace pvz
