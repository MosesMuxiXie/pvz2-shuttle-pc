#include "achievements_view.hpp"

#include "catalog.hpp"          // pathUtf8
#include "engine/plantfood.hpp"  // engine::generatedDir(): the shared generated-tree resolver
#include "loc.hpp"               // loc::load/resolve: the LawnStrings table

#include <algorithm>
#include <cctype>
#include <cmath>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <string>

#ifdef PVZ_ENABLE_DESKTOP
#include "sdl_support.hpp"
#include "text.hpp"
#endif

namespace pvz::meta {
namespace {

namespace fs = std::filesystem;

[[noreturn]] void fail(const fs::path& file, const std::string& detail) {
    throw std::runtime_error("achievements: " + pathUtf8(file) + ": " + detail);
}

std::string readText(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    if (!in) fail(file, "cannot open metagame.json");
    return std::string(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
}

Json parseOrFail(const fs::path& file) {
    const std::string text = readText(file);
    try {
        return Json::parse(text);
    } catch (const std::exception& error) {
        fail(file, std::string("invalid JSON (") + error.what() + ")");
    }
}

const Json& member(const Json& object, const char* key, const fs::path& file) {
    const auto it = object.find(key);
    if (it == object.end()) fail(file, std::string("no `") + key + "`");
    return *it;
}

std::string textOf(const Json& object, const char* key, const fs::path& file) {
    const Json& value = member(object, key, file);
    if (!value.is_string()) fail(file, std::string("`") + key + "` is not a string");
    return value.get<std::string>();
}

// `ACHIEVE_ALL_IN_JEST_TITLE` -> `All In Jest`. The key is the only title the tree carries, so
// this is a mechanical readability transform, not a translation: the report says the same.
std::string titleize(const std::string& words) {
    std::string out;
    out.reserve(words.size());
    bool startOfWord = true;
    for (char raw : words) {
        const unsigned char c = static_cast<unsigned char>(raw);
        if (c == '_' || c == ' ' || c == '-') {
            if (!out.empty() && out.back() != ' ') out.push_back(' ');
            startOfWord = true;
            continue;
        }
        if (startOfWord) {
            out.push_back(static_cast<char>(std::toupper(c)));
            startOfWord = false;
        } else {
            out.push_back(static_cast<char>(std::tolower(c)));
        }
    }
    while (!out.empty() && out.back() == ' ') out.pop_back();
    return out;
}

}  // namespace

std::string humanizeGameKey(const std::string& key) {
    std::string base = key;
    // LawnsStrings convention: ACHIEVE_<ID>_TITLE / ACHIEVE_<ID>_DESC, and for quests
    // <ID>_TITLE. Strip the known affixes only; anything else is left for titleize() to walk.
    constexpr const char* kAchievementPrefix = "ACHIEVE_";
    constexpr const char* kTitleSuffix = "_TITLE";
    if (base.rfind(kAchievementPrefix, 0) == 0) base.erase(0, std::string(kAchievementPrefix).size());
    if (base.size() > std::string(kTitleSuffix).size() &&
        base.compare(base.size() - std::string(kTitleSuffix).size(), std::string(kTitleSuffix).size(),
                     kTitleSuffix) == 0) {
        base.erase(base.size() - std::string(kTitleSuffix).size());
    }
    std::string out = titleize(base);
    return out.empty() ? key : out;
}

AchievementsModel AchievementsModel::load(const fs::path& file) {
    const Json root = parseOrFail(file);
    if (!root.is_object()) fail(file, "the root is not an object");
    const Json& achievements = member(root, "achievements", file);
    if (!achievements.is_object()) fail(file, "`achievements` is not an object");
    const Json& entries = member(achievements, "entries", file);
    if (!entries.is_array()) fail(file, "`achievements.entries` is not an array");
    if (entries.empty()) fail(file, "`achievements.entries` is empty");

    // B6b: the real strings now come from the localisation table that sits beside this one
    // (`<repo>/native/generated/lawn_strings.json`). `humanizeGameKey` stays as the fallback, so a
    // build without that table renders exactly the dashed title it rendered before.
    const loc::Strings strings = loc::load(file.parent_path().parent_path().string());

    AchievementsModel model;
    model.source = file;
    model.rows.reserve(entries.size());
    for (const Json& entry : entries) {
        if (!entry.is_object()) fail(file, "an entry is not an object");
        AchievementRow row;
        row.id = textOf(entry, "id", file);
        row.titleKey = textOf(entry, "titleKey", file);
        if (row.id.empty()) fail(file, "an entry has an empty id");
        if (row.titleKey.empty()) fail(file, "an entry has an empty titleKey");
        const auto serverOnly = entry.find("serverOnly");
        row.serverOnly = serverOnly == entry.end() ? true : serverOnly->get<bool>();
        row.title = loc::resolve(strings, row.titleKey, std::string());
        if (row.title.empty()) row.title = humanizeGameKey(row.titleKey);
        if (row.title.empty()) row.title = row.id;
        row.progress = "-";
        if (row.serverOnly) ++model.serverOnly;
        model.rows.push_back(std::move(row));
    }
    return model;
}

AchievementsModel AchievementsModel::loadShipped() {
    const fs::path directory = engine::generatedDir();
    if (directory.empty()) {
        throw std::runtime_error(
            "achievements: metagame.json was not found; set PVZ_GENERATED_DIR or run from the "
            "repository root");
    }
    return load(directory / "metagame.json");
}

int starsInWorld(const Progress& progress, const std::string& worldId) {
    const std::string prefix = worldId + "_";
    int stars = 0;
    for (const auto& [id, record] : progress.levels) {
        if (id.rfind(prefix, 0) == 0) stars += record.stars;
    }
    return stars;
}

int clearedInWorld(const Progress& progress, const std::string& worldId) {
    const std::string prefix = worldId + "_";
    int cleared = 0;
    for (const auto& [id, record] : progress.levels) {
        if (record.cleared && id.rfind(prefix, 0) == 0) ++cleared;
    }
    return cleared;
}

void applyProgress(AchievementsModel& model, const Progress& progress) {
    for (AchievementRow& row : model.rows) {
        constexpr const char* kStarsSuffix = "_STARS";
        const std::size_t suffix = std::string(kStarsSuffix).size();
        if (row.id.size() <= suffix ||
            row.id.compare(row.id.size() - suffix, suffix, kStarsSuffix) != 0) {
            row.progress = "-";  // nothing in metagame.json says what this row counts
            continue;
        }
        std::string world = row.id.substr(0, row.id.size() - suffix);
        std::transform(world.begin(), world.end(), world.begin(),
                       [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        const int stars = starsInWorld(progress, world);
        row.progress = std::to_string(stars) + " 星（" + world + "）";
    }
}

PageRange PageRange::of(int rows, int page, int perPage) {
    PageRange range;
    const int size = perPage > 0 ? perPage : 1;
    const int count = rows > 0 ? rows : 0;
    range.pages = std::max(1, (count + size - 1) / size);
    range.page = std::clamp(page, 0, range.pages - 1);
    range.first = range.page * size;
    range.count = std::clamp(count - range.first, 0, size);
    return range;
}

Json achievementsJson(const AchievementsModel& model, const PageRange& range, int perPage) {
    Json out;
    out["screen"] = "achievements";
    out["total"] = static_cast<int>(model.rows.size());
    out["serverOnly"] = model.serverOnly;
    out["perPage"] = perPage;
    out["page"] = range.page;
    out["pages"] = range.pages;
    Json visible = Json::array();
    for (int i = 0; i < range.count; ++i) {
        const AchievementRow& row = model.rows[static_cast<std::size_t>(range.first + i)];
        Json item;
        item["id"] = row.id;
        item["title"] = row.title;
        item["progress"] = row.progress;
        item["server"] = row.serverOnly;
        visible.push_back(std::move(item));
    }
    out["visible"] = std::move(visible);
    return out;
}

#ifdef PVZ_ENABLE_DESKTOP
namespace {

SDL_Color rgb(int r, int g, int b, int a = 255) {
    return SDL_Color{static_cast<Uint8>(r), static_cast<Uint8>(g), static_cast<Uint8>(b),
                     static_cast<Uint8>(a)};
}

struct Palette {
    SDL_Color page = rgb(18, 26, 32);
    SDL_Color panel = rgb(28, 39, 47);
    SDL_Color row = rgb(34, 47, 56);
    SDL_Color rowSelected = rgb(52, 82, 66);
    SDL_Color ink = rgb(238, 238, 226);
    SDL_Color muted = rgb(150, 164, 168);
    SDL_Color accent = rgb(150, 216, 96);
    SDL_Color warn = rgb(226, 168, 96);
};

void fill(SDL_Renderer* renderer, const SDL_FRect& rect, SDL_Color color) {
    sdl::require(SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a),
                 "set draw color");
    sdl::require(SDL_RenderFillRect(renderer, &rect), "fill rectangle");
}

void border(SDL_Renderer* renderer, const SDL_FRect& rect, SDL_Color color) {
    sdl::require(SDL_SetRenderDrawColor(renderer, color.r, color.g, color.b, color.a),
                 "set draw color");
    sdl::require(SDL_RenderRect(renderer, &rect), "draw rectangle");
}

void saveSnapshot(SDL_Renderer* renderer, const fs::path& path) {
    sdl::Surface pixels(SDL_RenderReadPixels(renderer, nullptr), SDL_DestroySurface);
    sdl::require(bool(pixels), "read frame");
    if (path.extension() == ".png" || path.extension() == ".PNG") {
        sdl::require(IMG_SavePNG(pixels.get(), pathUtf8(path).c_str()),
                     pathUtf8(path) + ": save snapshot");
    } else {
        sdl::require(SDL_SaveBMP(pixels.get(), pathUtf8(path).c_str()),
                     pathUtf8(path) + ": save snapshot");
    }
}

}  // namespace

Json renderAchievementsHeadless(const AchievementsModel& model, const AchievementsOptions& options) {
    const fs::path fontFile = options.assetRoot / "ui/font_zh.ttc";
    if (!fs::is_regular_file(fontFile)) {
        throw std::runtime_error(pathUtf8(fontFile) + ": cannot open the Chinese font");
    }

    PageRange range = PageRange::of(static_cast<int>(model.rows.size()), options.page,
                                    options.perPage);
    const bool headless = options.frames > 0;
    sdl::Display display(headless, "PvZ 2 SHUTTLE - Achievements");
    auto* renderer = display.renderer.get();
    TextRenderer text(renderer, fontFile);
    const Palette palette;

    int selected = range.first;  // absolute row index; the page decides which rows are drawn
    bool running = true;
    int frame = 0;
    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_EVENT_QUIT || event.type == SDL_EVENT_WINDOW_CLOSE_REQUESTED) {
                running = false;
            } else if (event.type == SDL_EVENT_KEY_DOWN) {
                switch (event.key.key) {
                    case SDLK_ESCAPE:
                        running = false;
                        break;
                    case SDLK_PAGEDOWN:
                        if (range.page + 1 < range.pages) {
                            range = PageRange::of(static_cast<int>(model.rows.size()),
                                                  range.page + 1, options.perPage);
                            selected = range.first;
                        }
                        break;
                    case SDLK_PAGEUP:
                        if (range.page > 0) {
                            range = PageRange::of(static_cast<int>(model.rows.size()),
                                                  range.page - 1, options.perPage);
                            selected = range.first;
                        }
                        break;
                    case SDLK_DOWN:
                        if (selected + 1 < range.first + range.count) ++selected;
                        break;
                    case SDLK_UP:
                        if (selected > range.first) --selected;
                        break;
                    default:
                        break;
                }
            }
        }

        fill(renderer, SDL_FRect{0, 0, AchievementsLayout::kWidth, AchievementsLayout::kHeight},
             palette.page);
        fill(renderer, SDL_FRect{0, 0, AchievementsLayout::kWidth, 64}, palette.panel);
        text.draw(40, 16, 30, palette.ink, "成就");
        text.draw(132, 26, 20, palette.muted,
                  "共 " + std::to_string(model.rows.size()) + " 项 · 全部由服务器结算 · 本地只列条件");
        text.draw(40, 88, 16, palette.muted, "名称");
        text.draw(780, 88, 16, palette.muted, "进度（本地存档）");
        text.draw(1120, 88, 16, palette.muted, "来源");

        for (int i = 0; i < range.count; ++i) {
            const int index = range.first + i;
            const AchievementRow& row = model.rows[static_cast<std::size_t>(index)];
            const float y = AchievementsLayout::kRowTop + static_cast<float>(i) * AchievementsLayout::kRowHeight;
            const SDL_FRect rect{AchievementsLayout::kRowLeft, y, AchievementsLayout::kRowWidth,
                                 AchievementsLayout::kRowHeight - 4.0f};
            const bool isSelected = index == selected;
            fill(renderer, rect, isSelected ? palette.rowSelected : palette.row);
            if (isSelected) border(renderer, rect, palette.accent);

            text.draw(rect.x + 16, y + 8, 20, palette.ink, row.title);
            const bool derived = row.progress != "-";
            text.draw(780, y + 10, 18, derived ? palette.accent : palette.muted, row.progress);
            if (row.serverOnly) {
                const std::string badge = "server";
                const float w = text.width(badge, 16) + 20.0f;
                const SDL_FRect badgeRect{1216.0f - w, y + 7, w, 26.0f};
                fill(renderer, badgeRect, palette.panel);
                border(renderer, badgeRect, palette.warn);
                text.drawCentered(badgeRect.x + badgeRect.w * 0.5f, y + 11, 16, palette.warn, badge);
            }
        }

        text.draw(40, 676, 18, palette.muted,
                  "第 " + std::to_string(range.page + 1) + "/" + std::to_string(range.pages) +
                      " 页 · PgUp/PgDn 翻页 · ↑↓ 选择 · Esc 退出");
        // The one sentence the screen exists to say. Right-aligned because it is a statement
        // about the whole list, not about the selected row.
        const std::string note = "这些成就由服务器结算，本地只展示条件";
        text.draw(1240.0f - text.width(note, 18), 676, 18, palette.accent, note);

        if (!options.snapshot.empty()) saveSnapshot(renderer, options.snapshot);
        sdl::require(SDL_RenderPresent(renderer), "present achievements");
        ++frame;
        if (headless && frame >= options.frames) break;
        if (!headless) SDL_Delay(16);
    }
    return achievementsJson(model, range, options.perPage);
}
#endif

}  // namespace pvz::meta
