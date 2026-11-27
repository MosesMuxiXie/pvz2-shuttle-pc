#include "worldmap_view.hpp"

#include "audio/audio_runtime.hpp"
#include "engine/plantfood.hpp"  // engine::generatedDir(): where metagame.json lives
#include "progress.hpp"
#include "sdl_support.hpp"
#include "text.hpp"

#include <algorithm>
#include <fstream>
#include <string>
#include <vector>

namespace pvz {
namespace {

using map::WorldInfo;
using map::WorldState;
using map::WorldStatus;

constexpr float kWidth = 1280.0f;
constexpr float kHeight = 720.0f;

SDL_Color rgb(int r, int g, int b, int a = 255) {
    return SDL_Color{static_cast<Uint8>(r), static_cast<Uint8>(g), static_cast<Uint8>(b),
                     static_cast<Uint8>(a)};
}

struct Palette {
    SDL_Color page = rgb(18, 26, 32);
    SDL_Color panel = rgb(28, 39, 47);
    SDL_Color row = rgb(34, 47, 56);
    SDL_Color rowSelected = rgb(52, 82, 66);
    SDL_Color locked = rgb(30, 33, 38);
    SDL_Color ink = rgb(238, 238, 226);
    SDL_Color muted = rgb(150, 164, 168);
    SDL_Color accent = rgb(150, 216, 96);
    SDL_Color warn = rgb(226, 168, 96);
};

// A world row is one line of the left list: name, level count and the requirement. Selection is
// drawn by the caller; this only fills the row rectangle.
struct Row {
    float x = 0, y = 0, w = 0, h = 0;
    std::size_t index = 0;
};

std::string requirementText(const WorldStatus& status) {
    if (status.state != WorldState::locked) return {};
    if (status.requiredKeys > 0) return std::to_string(status.requiredKeys) + " 把钥匙";
    if (status.requiredStars > 0) return std::to_string(status.requiredStars) + " 颗星";
    return "未开放";
}

// Wraps UTF-8 text to `maxWidth` by measuring each candidate prefix, because the font is loaded at
// runtime and byte offsets say nothing about rendered width.
std::vector<std::string> wrap(TextRenderer& text, const std::string& utf8, int pixelSize,
                              float maxWidth) {
    std::vector<std::string> lines;
    const auto codepoints = decodeUtf8(utf8);
    std::string line;
    std::string candidate;
    for (std::uint32_t codepoint : codepoints) {
        if (codepoint == '\n') {
            lines.push_back(line);
            line.clear();
            continue;
        }
        std::string piece;
        if (codepoint < 0x80) {
            piece.push_back(static_cast<char>(codepoint));
        } else if (codepoint < 0x800) {
            piece.push_back(static_cast<char>(0xC0 | (codepoint >> 6)));
            piece.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
        } else if (codepoint < 0x10000) {
            piece.push_back(static_cast<char>(0xE0 | (codepoint >> 12)));
            piece.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
            piece.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
        } else {
            piece.push_back(static_cast<char>(0xF0 | (codepoint >> 18)));
            piece.push_back(static_cast<char>(0x80 | ((codepoint >> 12) & 0x3F)));
            piece.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
            piece.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
        }
        candidate = line + piece;
        if (!line.empty() && text.width(candidate, pixelSize) > maxWidth) {
            lines.push_back(line);
            line = piece;
        } else {
            line = candidate;
        }
    }
    if (!line.empty()) lines.push_back(line);
    return lines;
}

void fill(SDL_Renderer* renderer, const SDL_FRect& rect, SDL_Color color) {
    sdl::require(SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a), "set draw color");
    sdl::require(SDL_RenderFillRect(renderer, &rect), "fill rectangle");
}

void border(SDL_Renderer* renderer, const SDL_FRect& rect, SDL_Color color) {
    sdl::require(SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a), "set draw color");
    sdl::require(SDL_RenderRect(renderer, &rect), "draw rectangle");
}

std::vector<std::string> levelsOf(const Catalog& catalog, const std::string& world) {
    std::vector<std::string> ids;
    for (const auto& entry : catalog.levels) {
        if (entry.second.world != world) continue;
        ids.push_back(entry.first);
    }
    std::sort(ids.begin(), ids.end());
    return ids;
}

void saveSnapshot(SDL_Renderer* renderer, const std::filesystem::path& path) {
    if (path.extension() == ".png" || path.extension() == ".PNG") {
        sdl::Surface pixels(SDL_RenderReadPixels(renderer, nullptr), SDL_DestroySurface);
        sdl::require(bool(pixels), "read frame");
        sdl::require(IMG_SavePNG(pixels.get(), pathUtf8(path).c_str()),
                     pathUtf8(path) + ": save snapshot");
        return;
    }
    sdl::snapshot(renderer, path);
}

}  // namespace

MetagameCounts loadMetagameCounts(const std::filesystem::path& generatedDir) {
    MetagameCounts counts;
    if (generatedDir.empty()) {
        counts.note = "generated directory not found (set PVZ_GENERATED_DIR or run from the repository root)";
        return counts;
    }
    const auto file = generatedDir / "metagame.json";
    std::ifstream in(file);
    if (!in) {
        counts.note = pathUtf8(file) + ": cannot open";
        return counts;
    }
    Json doc;
    try {
        in >> doc;
    } catch (const std::exception& error) {
        counts.note = pathUtf8(file) + ": " + error.what();
        return counts;
    }
    if (!doc.is_object()) {
        counts.note = pathUtf8(file) + ": top level is not an object";
        return counts;
    }
    // Each number is read through `find`, so a table that lost one block still contributes the
    // other: the line then says what is known instead of disappearing as a whole.
    const auto numberAt = [](const Json& root, const char* block, const char* key) -> int {
        const auto outer = root.find(block);
        if (outer == root.end() || !outer->is_object()) return 0;
        const auto inner = outer->find("counts");
        if (inner == outer->end() || !inner->is_object()) return 0;
        const auto value = inner->find(key);
        if (value == inner->end() || !value->is_number()) return 0;
        return static_cast<int>(value->get<double>());
    };
    counts.plants = numberAt(doc, "almanac", "plants");
    counts.zombies = numberAt(doc, "almanac", "zombies");
    counts.drops = numberAt(doc, "garden", "collectables");
    counts.loaded = counts.plants > 0 || counts.zombies > 0 || counts.drops > 0;
    if (!counts.loaded) counts.note = pathUtf8(file) + ": no almanac or garden counts";
    return counts;
}

WorldMapScreenResult runWorldMapScreen(const Catalog& catalog, const map::WorldMap& map,
                                       const WorldMapScreenOptions& options) {
    const auto fontFile = options.assetRoot / "ui/font_zh.ttc";
    if (!std::filesystem::is_regular_file(fontFile))
        throw std::runtime_error(pathUtf8(fontFile) + ": cannot open the Chinese font");

    Progress progress;
    if (!options.progressFile.empty()) progress = loadProgress(options.progressFile);

    const bool headless = options.frames > 0;
    sdl::Display display(headless, "PvZ 2 SHUTTLE - World map");
    auto* renderer = display.renderer.get();
    TextRenderer text(renderer, fontFile);
    const Palette palette;
    // The map is a menu screen: one looping menu track and a click per cursor move. A headless
    // screenshot attaches in `headless` mode and therefore never opens a device.
    attachAudio(options.assetRoot, headless);
    playAudioMenuMusic();

    WorldMapScreenResult result;
    result.worlds = static_cast<int>(map.worlds().size());
    result.stars = progress.totalStars();
    result.keys = progress.keys;
    // A7: how much there is to look at beyond the levels. Read once; a checkout without the table
    // keeps the line off the screen instead of failing.
    result.metagame = loadMetagameCounts(engine::generatedDir());

    // One status per world, computed once: the screen must show exactly what the model says, and
    // recomputing it per frame would let the two drift.
    std::vector<WorldStatus> statuses;
    statuses.reserve(map.worlds().size());
    for (const WorldInfo& world : map.worlds()) {
        const int cleared = map::clearedLevelsFor(progress, world.id);
        statuses.push_back(map.status(world.id, progress.totalStars(), progress.keys, cleared));
    }
    for (const WorldStatus& status : statuses) {
        if (status.state == WorldState::available) ++result.unlocked;
        if (status.state == WorldState::completed) ++result.completed;
    }
    // `completed` already means "every level of this world is cleared"; the JSON calls that number
    // `clearedWorlds`, so it gets its own field instead of relying on the reader knowing that.
    result.clearedWorlds = result.completed;

    // Two columns of thirteen keeps all 26 worlds on one screen without scrolling; the original
    // map scrolls, but a scrollbar would hide worlds behind an interaction the screen cannot test.
    std::vector<Row> rows;
    const std::size_t perColumn = (map.worlds().size() + 1) / 2;
    for (std::size_t i = 0; i < map.worlds().size(); ++i) {
        const std::size_t column = i / perColumn;
        const std::size_t line = i % perColumn;
        rows.push_back(Row{40.0f + static_cast<float>(column) * 400.0f, 96.0f + static_cast<float>(line) * 44.0f,
                           380.0f, 38.0f, i});
    }

    std::size_t selected = 0;
    std::string enteredWorld;
    std::string enteredLevel;
    bool running = true;
    int frame = 0;
    while (running) {
        const std::size_t selectionBefore = selected;
        bool clicked = false;
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT || event.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED) {
                running = false;
            } else if (event.type == SDL_EVENT_KEY_DOWN) {
                switch (event.key.key) {
                    case SDLK_ESCAPE:
                        running = false;
                        break;
                    case SDLK_DOWN:
                        if (selected + 1 < rows.size()) ++selected;
                        break;
                    case SDLK_UP:
                        if (selected > 0) --selected;
                        break;
                    case SDLK_RIGHT:
                        if (selected + perColumn < rows.size()) selected += perColumn;
                        break;
                    case SDLK_LEFT:
                        if (selected >= perColumn) selected -= perColumn;
                        break;
                    case SDLK_RETURN:
                    case SDLK_KP_ENTER: {
                        const WorldInfo& world = map.worlds()[selected];
                        if (statuses[selected].state != WorldState::locked) {
                            enteredWorld = world.id;
                            const auto levels = levelsOf(catalog, world.id);
                            if (!levels.empty()) enteredLevel = levels.front();
                            running = false;
                        }
                        break;
                    }
                    default:
                        break;
                }
            } else if (event.type == SDL_EVENT_MOUSE_BUTTON_DOWN) {
                for (const Row& row : rows) {
                    if (event.button.x >= row.x && event.button.x <= row.x + row.w &&
                        event.button.y >= row.y && event.button.y <= row.y + row.h) {
                        selected = row.index;
                        clicked = true;
                    }
                }
            }
        }

        // One click per real interaction, not per frame: a held key must not machine-gun the
        // eight mixer voices that the wave horn needs.
        if (clicked || selected != selectionBefore) playAudioClick();
        pumpAudio();

        fill(renderer, SDL_FRect{0, 0, kWidth, kHeight}, palette.page);
        fill(renderer, SDL_FRect{0, 0, kWidth, 64}, palette.panel);
        text.draw(40, 18, 30, palette.ink, "世界地图");
        text.draw(200, 26, 22, palette.muted,
                  "共 " + std::to_string(result.worlds) + " 个世界 · 可进入 " +
                      std::to_string(result.unlocked) + " · 已通关 " +
                      std::to_string(result.completed));
        text.draw(1000, 26, 22, palette.accent,
                  "★ " + std::to_string(result.stars) + "   钥匙 " + std::to_string(result.keys));

        for (const Row& row : rows) {
            const WorldInfo& world = map.worlds()[row.index];
            const WorldStatus& status = statuses[row.index];
            const bool isSelected = row.index == selected;
            SDL_Color background = palette.row;
            if (status.state == WorldState::locked) background = palette.locked;
            if (isSelected) background = palette.rowSelected;
            fill(renderer, SDL_FRect{row.x, row.y, row.w, row.h}, background);
            if (isSelected) border(renderer, SDL_FRect{row.x, row.y, row.w, row.h}, palette.accent);

            SDL_Color nameColor = palette.ink;
            if (status.state == WorldState::locked) nameColor = palette.muted;
            const std::string name = world.nameZh.empty() ? world.id : world.nameZh;
            text.draw(row.x + 12, row.y + 8, 22, nameColor, name);
            text.draw(row.x + 12 + text.width(name, 22) + 10, row.y + 11, 16, palette.muted,
                      std::to_string(world.levels) + " 关");
            const std::string requirement = requirementText(status);
            if (!requirement.empty()) {
                text.draw(row.x + row.w - 12 - text.width(requirement, 18), row.y + 9, 18, palette.warn,
                          requirement);
            } else if (status.state == WorldState::completed) {
                // A7: a check mark on the world itself, so a finished world reads at a glance and
                // not only in the right-hand panel.
                const std::string done = "✓ 已通关";
                text.draw(row.x + row.w - 12 - text.width(done, 18), row.y + 9, 18, palette.accent,
                          done);
            }
        }

        // Detail panel: the same numbers, spelled out. This is where a wrong `starsSource` becomes
        // visible: the panel says whether the requirement came from the sheet or from the client.
        const WorldInfo& world = map.worlds()[selected];
        const WorldStatus& status = statuses[selected];
        fill(renderer, SDL_FRect{840, 96, 400, 560}, palette.panel);
        border(renderer, SDL_FRect{840, 96, 400, 560}, palette.muted);
        float y = 112;
        text.draw(860, y, 28, palette.ink, world.nameZh.empty() ? world.id : world.nameZh);
        y += 40;
        text.draw(860, y, 16, palette.muted,
                  world.id + " · " + std::string(map::worldStateName(status.state)));
        y += 32;
        for (const std::string& line : wrap(text, world.desc, 18, 352.0f)) {
            text.draw(860, y, 18, palette.ink, line);
            y += 28;
        }
        y += 16;
        // The starter's price is a client number that the model deliberately ignores (C48), so
        // the panel says which rule is in force instead of showing a ticket nobody pays.
        std::string ticket;
        if (world.starter) {
            ticket = "初始世界（客户端标价 " + std::to_string(world.unlockCost) + " 颗星，不生效）";
        } else if (status.requiredKeys > 0) {
            ticket = std::to_string(status.requiredKeys) + " 把钥匙";
        } else {
            ticket = std::to_string(status.requiredStars) + " 颗星（来源 " + status.starsSource + "）";
        }
        for (const std::string& line : wrap(text, "门票：" + ticket, 18, 352.0f)) {
            text.draw(860, y, 18, palette.muted, line);
            y += 26;
        }
        y += 8;
        text.draw(860, y, 18, palette.muted,
                  "关卡 " + std::to_string(world.levels) + " · 世界门 " +
                      std::to_string(world.gateCount));
        y += 30;
        if (status.state == WorldState::locked) {
            for (const std::string& line : wrap(text, status.reason, 18, 352.0f)) {
                text.draw(860, y, 18, palette.warn, line);
                y += 26;
            }
        } else {
            const auto levels = levelsOf(catalog, world.id);
            const std::string entry = levels.empty() ? "关卡数据缺失" : "回车进入 " + levels.front();
            text.draw(860, y, 18, palette.accent, entry);
        }
        // The hint lives outside the panel: inside, it was wider than the panel and got clipped.
        text.draw(40, 676, 18, palette.muted,
                  "↑↓ 选择 · ←→ 翻列 · 回车进入 · Esc 退出");
        // A7: the way in to the two catalogue screens, stated as sizes so it also says how much is
        // behind the door. Right-aligned because the hint on the left already owns the row.
        if (result.metagame.loaded) {
            const std::string entry = "图鉴 " + std::to_string(result.metagame.plants) + "+" +
                                      std::to_string(result.metagame.zombies) + " · 花园 " +
                                      std::to_string(result.metagame.drops);
            text.draw(kWidth - 40 - text.width(entry, 18), 676, 18, palette.accent, entry);
        }

        if (!options.snapshot.empty()) saveSnapshot(renderer, options.snapshot);
        sdl::require(SDL_RenderPresent(renderer), "present world map");
        ++frame;
        if (headless && frame >= options.frames) break;
        if (!headless) SDL_Delay(16);
    }

    result.selected = static_cast<int>(selected);
    result.selectedWorld = map.worlds()[selected].id;
    result.enteredWorld = enteredWorld;
    result.enteredLevel = enteredLevel;
    return result;
}

Json worldMapScreenJson(const WorldMapScreenResult& result) {
    Json out;
    out["worlds"] = result.worlds;
    out["unlocked"] = result.unlocked;
    out["completed"] = result.completed;
    out["stars"] = result.stars;
    out["keys"] = result.keys;
    out["selected"] = result.selectedWorld;
    out["entered"] = result.enteredWorld;
    out["level"] = result.enteredLevel;
    out["clearedWorlds"] = result.clearedWorlds;
    out["almanac"] = Json{{"plants", result.metagame.plants}, {"zombies", result.metagame.zombies}};
    out["garden"] = Json{{"drops", result.metagame.drops}};
    return out;
}

}  // namespace pvz
