#include "battle_screen.hpp"

#include "battle.hpp"
#include "save.hpp"
#include "video.hpp"

#include <algorithm>
#include <chrono>
#include <iostream>
#include <memory>

namespace shuttle {
namespace {

using Phase = Battle::Phase;
constexpr float boardX = 73, boardY = 85, cellW = 58, cellH = 44;
constexpr SDL_FRect startButton{218, 225, 204, 32};
constexpr SDL_FRect shovelButton{525, 315, 85, 25};
constexpr SDL_FRect replayButton{249, 202, 142, 28};
constexpr SDL_Color paper{247, 239, 198, 255};
constexpr SDL_Color ink{27, 44, 33, 255};

void color(SDL_Renderer* renderer, SDL_Color value) {
    SDL_SetRenderDrawColor(renderer, value.r, value.g, value.b, value.a);
}

void fill(SDL_Renderer* renderer, SDL_FRect rectangle, SDL_Color value) {
    color(renderer, value);
    SDL_RenderFillRect(renderer, &rectangle);
}

void label(SDL_Renderer* renderer, float x, float y, const std::string& text, SDL_Color value = paper) {
    color(renderer, value);
    SDL_RenderDebugText(renderer, x, y, text.c_str());
}

SDL_FRect cardRect(int index, Phase phase) {
    return {17.0f + index * 154.0f, phase == Phase::choosing ? 146.0f : 13.0f, 143, 40};
}

SDL_FRect square(int row, int col) {
    return {boardX + col * cellW, boardY + row * cellH, cellW, cellH};
}

SDL_FRect sunMarker(int row, int col) {
    const auto tile = square(row, col);
    return {tile.x + 32, tile.y + 3, 22, 16};
}

void drawCards(SDL_Renderer* renderer, const Battle& battle, int held) {
    for (int i = 0; i < static_cast<int>(battle.cards().size()); ++i) {
        const auto& card = battle.cards()[i];
        const auto rect = cardRect(i, battle.phase());
        fill(renderer, rect, i == held ? SDL_Color{243, 193, 69, 255} :
            card.selected ? SDL_Color{190, 213, 147, 255} : SDL_Color{143, 156, 135, 255});
        label(renderer, rect.x + 7, rect.y + 8, std::to_string(i + 1) + " " + card.name, ink);
        auto details = std::to_string(card.cost) + " sun";
        if (battle.phase() == Phase::choosing) {
            details += card.selected ? " / selected" : " / select";
        } else if (card.availableAt > battle.tick()) {
            details += " / " + std::to_string((card.availableAt - battle.tick() + 59) / 60) + "s";
        }
        label(renderer, rect.x + 7, rect.y + 23, details, ink);
    }
}

void drawBoard(SDL_Renderer* renderer, const Battle& battle) {
    for (int row = 0; row < Battle::rows; ++row) {
        for (int col = 0; col < Battle::columns; ++col) {
            fill(renderer, square(row, col), (row + col) % 2 == 0 ? SDL_Color{77, 130, 53, 255} :
                 SDL_Color{86, 144, 61, 255});
        }
        const auto& mower = battle.mowers()[row];
        if (mower.state != Battle::Mower::spent) {
            fill(renderer, {boardX + static_cast<float>(mower.x) * cellW - 24, square(row, 0).y + 22, 22, 13},
                 {201, 67, 53, 255});
        }
    }
    constexpr SDL_Color plants[] = {{236, 194, 44, 255}, {119, 214, 75, 255},
                                    {169, 100, 52, 255}, {226, 144, 68, 255}};
    constexpr const char* names[] = {"SUN", "PEA", "NUT", "MINE"};
    for (const auto& plant : battle.plants()) {
        const auto tile = square(plant.row, plant.col);
        const auto kind = static_cast<int>(battle.cards()[plant.card].kind);
        fill(renderer, {tile.x + 9, tile.y + 10, 40, 25}, plants[kind]);
        label(renderer, tile.x + 13, tile.y + 18, names[kind], ink);
    }
    for (const auto& z : battle.zombies()) {
        const auto x = boardX + static_cast<float>(z.x) * cellW;
        const auto y = square(z.row, 0).y;
        fill(renderer, {x - 10, y + 11, 22, 29}, {103, 113, 150, 255});
        fill(renderer, {x - 8, y + 6, 18, 14}, z.armored ? SDL_Color{213, 131, 53, 255} :
             SDL_Color{165, 182, 127, 255});
    }
    for (const auto& shot : battle.shots()) {
        fill(renderer, {boardX + static_cast<float>(shot.x) * cellW, square(shot.row, 0).y + 20, 6, 5},
             {207, 242, 102, 255});
    }
    for (const auto& sun : battle.suns()) {
        const auto marker = sunMarker(sun.row, sun.col);
        fill(renderer, marker, {255, 221, 83, 255});
        label(renderer, marker.x + 3, marker.y + 4, std::to_string(sun.value), ink);
    }
}

void render(SDL_Renderer* renderer, const Battle& battle, int held, bool shovel, bool paused, bool saveFailed) {
    color(renderer, {32, 56, 44, 255});
    requireSdl(SDL_RenderClear(renderer), "clear battle frame");
    drawCards(renderer, battle, held);
    const auto phase = battle.phase();
    if (phase == Phase::choosing) {
        label(renderer, 205, 98, "FRONT YARD / DAY 1");
        label(renderer, 174, 116, "Choose seeds by clicking their cards.");
        fill(renderer, startButton, {185, 206, 125, 255});
        label(renderer, 250, 237, "START BATTLE / ENTER", ink);
    } else {
        label(renderer, 18, 65, "SUN " + std::to_string(battle.sun()) + "    WAVE " +
              std::to_string(battle.wavesStarted()) + "/" + std::to_string(battle.waveCount()));
        drawBoard(renderer, battle);
        fill(renderer, shovelButton, shovel ? SDL_Color{243, 193, 69, 255} : SDL_Color{190, 213, 147, 255});
        label(renderer, 532, 324, "SHOVEL X", ink);
        label(renderer, 18, 324, "1-4: seeds    Click: collect / plant    Space: pause");
        if (phase == Phase::won || phase == Phase::lost || paused) {
            fill(renderer, {171, 125, 298, 118}, {25, 46, 39, 255});
            label(renderer, 277, 150, paused ? "PAUSED" : phase == Phase::won ? "YOU WIN" : "YOU LOST");
            if (paused) {
                label(renderer, 226, 175, "Press Space to resume");
            } else {
                label(renderer, 194, 175, saveFailed ? "Save failed. Press S to retry." :
                      "Waves cleared: " + std::to_string(battle.wavesStarted()));
                fill(renderer, replayButton, {185, 206, 125, 255});
                label(renderer, 268, 212, "PLAY AGAIN / R", ink);
            }
        }
    }
    requireSdl(SDL_RenderPresent(renderer), "present battle frame");
}

}

std::filesystem::path defaultSavePath() {
    const std::unique_ptr<char, decltype(&SDL_free)> folder(SDL_GetPrefPath("PvZ2SHUTTLE", "Native"), SDL_free);
    requireSdl(folder != nullptr, "find native save directory");
    return std::filesystem::u8path(folder.get()) / "save.json";
}

std::filesystem::path bundledContentPath() {
    const auto* folder = SDL_GetBasePath();
    requireSdl(folder != nullptr, "find application resources");
    return std::filesystem::u8path(folder) / "content";
}

void runFirstBattle(const std::filesystem::path& content, const std::filesystem::path& save, bool smoke) {
    const auto catalog = loadCatalog(content);
    const auto level = loadLevelDefinition(content / "native" / "frontyard_1.json", catalog);
    Battle battle(catalog, level);
    const VideoSession video;
    const auto flags = smoke ? SDL_WINDOW_HIDDEN : SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY;
    const std::unique_ptr<SDL_Window, decltype(&SDL_DestroyWindow)> window(
        SDL_CreateWindow("PvZ 2 SHUTTLE - Front Yard", 1280, 720, flags), SDL_DestroyWindow);
    requireSdl(window != nullptr, "create battle window");
    const std::unique_ptr<SDL_Renderer, decltype(&SDL_DestroyRenderer)> renderer(
        SDL_CreateRenderer(window.get(), smoke ? "software" : nullptr), SDL_DestroyRenderer);
    requireSdl(renderer != nullptr, "create battle renderer");
    requireSdl(SDL_SetRenderLogicalPresentation(renderer.get(), 640, 360, SDL_LOGICAL_PRESENTATION_LETTERBOX),
               "set battle viewport");
    if (smoke) {
        render(renderer.get(), battle, -1, false, false, false);
        battle.toggleCard(0);
        battle.start();
        battle.plant(0, 0, 0);
        battle.step();
        render(renderer.get(), battle, 0, false, false, false);
        return;
    }

    const auto savePath = save.empty() ? defaultSavePath() : save;
    int held = -1;
    bool shovel = false, paused = false, saveFailed = false;
    const auto saveWin = [&] {
        try {
            recordFirstBattleWin(savePath);
            saveFailed = false;
        } catch (const std::exception& error) {
            saveFailed = true;
            std::cerr << error.what() << '\n';
        }
    };
    const auto replay = [&] {
        battle = Battle(catalog, level);
        held = -1;
        shovel = paused = saveFailed = false;
    };
    const auto select = [&](int card) {
        if (battle.phase() == Phase::choosing) {
            battle.toggleCard(card);
        } else if (battle.phase() == Phase::playing && !paused && battle.cards()[card].selected) {
            held = card;
            shovel = false;
        }
    };

    using Clock = std::chrono::steady_clock;
    auto last = Clock::now();
    double pending = 0;
    constexpr double step = 1.0 / Battle::ticksPerSecond;
    for (;;) {
        SDL_Event event{};
        while (SDL_PollEvent(&event)) {
            const auto phase = battle.phase();
            const bool finished = phase == Phase::won || phase == Phase::lost;
            if (event.type == SDL_EVENT_QUIT || event.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED) {
                return;
            }
            if (event.type == SDL_EVENT_KEY_DOWN && !event.key.repeat) {
                const auto key = event.key.key;
                if (key == SDLK_ESCAPE) { return; }
                if (key >= SDLK_1 && key < SDLK_1 + battle.cards().size()) { select(key - SDLK_1); }
                if (key == SDLK_RETURN && phase == Phase::choosing) { battle.start(); }
                if (key == SDLK_SPACE && phase == Phase::playing) { paused = !paused; }
                if (key == SDLK_X && phase == Phase::playing && !paused) { shovel = !shovel; held = -1; }
                if (key == SDLK_R && finished) { replay(); }
                if (key == SDLK_S && phase == Phase::won && saveFailed) { saveWin(); }
            }
            if (event.type != SDL_EVENT_MOUSE_BUTTON_DOWN || event.button.button != SDL_BUTTON_LEFT ||
                !SDL_ConvertEventToRenderCoordinates(renderer.get(), &event)) {
                continue;
            }
            const SDL_FPoint click{event.button.x, event.button.y};
            for (int i = 0; i < static_cast<int>(battle.cards().size()); ++i) {
                const auto card = cardRect(i, phase);
                if (SDL_PointInRectFloat(&click, &card)) { select(i); }
            }
            if (phase == Phase::choosing && SDL_PointInRectFloat(&click, &startButton)) { battle.start(); }
            if (finished && SDL_PointInRectFloat(&click, &replayButton)) { replay(); }
            if (phase != Phase::playing || paused) { continue; }
            if (SDL_PointInRectFloat(&click, &shovelButton)) { shovel = !shovel; held = -1; }
            const SDL_FRect lawn{boardX, boardY, Battle::columns * cellW, Battle::rows * cellH};
            if (!SDL_PointInRectFloat(&click, &lawn)) { continue; }
            const int row = static_cast<int>((click.y - boardY) / cellH);
            const int col = static_cast<int>((click.x - boardX) / cellW);
            const auto marker = sunMarker(row, col);
            if (SDL_PointInRectFloat(&click, &marker) && battle.collectSun(row, col)) { continue; }
            if (shovel) { if (battle.shovel(row, col)) { shovel = false; } }
            else if (held >= 0 && battle.plant(held, row, col)) { held = -1; }
        }

        const auto now = Clock::now();
        if (battle.phase() == Phase::playing && !paused) {
            pending += std::min(0.25, std::chrono::duration<double>(now - last).count());
            while (pending >= step && battle.phase() == Phase::playing) {
                battle.step();
                pending -= step;
                if (battle.phase() == Phase::won) { saveWin(); }
            }
        } else {
            pending = 0;
        }
        last = now;
        render(renderer.get(), battle, held, shovel, paused, saveFailed);
        SDL_Delay(8);
    }
}

}
