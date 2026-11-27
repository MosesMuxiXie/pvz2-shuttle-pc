#include "daily_view.hpp"

#include "catalog.hpp"           // pathUtf8
#include "engine/plantfood.hpp"  // engine::generatedDir()
#include "loc.hpp"               // loc::load/resolve: the LawnStrings table

#include <algorithm>
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
    throw std::runtime_error("daily: " + pathUtf8(file) + ": " + detail);
}

Json parseOrFail(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    if (!in) fail(file, "cannot open metagame.json");
    // Braces, not parentheses: with parentheses this line parses as a function declaration and
    // `Json::parse` then gets a function reference (C2665, "no overloaded function could convert").
    const std::string text{std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
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

// Reward currencies the OBB uses, in the words the rest of the client already uses
// (`--shop` prints "coins"/"gems"; the 薄荷币 name is the one the mints rows use in the shop JSON).
std::string currencyLabel(const std::string& type) {
    if (type == "coins") return "金币";
    if (type == "gems") return "宝石";
    if (type == "mints") return "薄荷币";
    return type;
}

bool currencyPayable(const std::string& type) { return type == "coins"; }

std::string rewardText(const Json& entry, bool* payable, const fs::path& file) {
    *payable = true;
    const auto it = entry.find("rewards");
    if (it == entry.end() || it->is_null()) {
        *payable = false;
        return "-";
    }
    if (!it->is_array()) fail(file, "`rewards` is not an array");
    if (it->empty()) {
        *payable = false;
        return "-";
    }
    std::string out;
    bool any = false;
    for (const Json& reward : *it) {
        if (!reward.is_object()) fail(file, "a reward is not an object");
        const std::string type = textOf(reward, "type", file);
        const Json& amount = member(reward, "amount", file);
        const std::string amountText =
            amount.is_string() ? amount.get<std::string>() : amount.dump();
        if (any) out += " + ";
        out += amountText + " " + currencyLabel(type);
        any = true;
        if (!currencyPayable(type)) *payable = false;
    }
    return out;
}

}  // namespace

DailyModel DailyModel::load(const fs::path& file) {
    const Json root = parseOrFail(file);
    if (!root.is_object()) fail(file, "the root is not an object");
    const Json& quests = member(root, "quests", file);
    if (!quests.is_object()) fail(file, "`quests` is not an object");
    const Json& daily = member(quests, "daily", file);
    if (!daily.is_array()) fail(file, "`quests.daily` is not an array");
    if (daily.empty()) fail(file, "`quests.daily` is empty");

    // B6b: real titles from the LawnStrings table beside this one; `humanizeGameKey` remains the
    // fallback so a build without the table keeps its dashed placeholder titles.
    const loc::Strings strings = loc::load(file.parent_path().parent_path().string());

    DailyModel model;
    model.source = file;
    const auto tabs = quests.find("tabs");
    if (tabs != quests.end() && tabs->is_array()) model.tabs = static_cast<int>(tabs->size());
    model.rows.reserve(daily.size());

    for (const Json& entry : daily) {
        if (!entry.is_object()) fail(file, "an entry is not an object");
        DailyRow row;
        row.id = textOf(entry, "id", file);
        row.titleKey = textOf(entry, "nameKey", file);
        row.targetType = textOf(entry, "targetType", file);
        if (row.id.empty()) fail(file, "an entry has an empty id");
        row.title = loc::resolve(strings, row.titleKey, std::string());
        if (row.title.empty()) row.title = humanizeGameKey(row.titleKey);
        if (row.title.empty()) row.title = row.id;

        bool payable = false;
        row.reward = rewardText(entry, &payable, file);
        row.payable = payable;

        // The only scheduling field the sheet has. `Repeatable`/`Slot`/`Priority` exist but say
        // nothing about whether the row is live today, so they are reported, not used as a gate.
        const auto params = entry.find("params");
        bool disabled = false;
        if (params != entry.end() && params->is_object()) {
            const auto flag = params->find("Disabled");
            if (flag != params->end() && flag->is_boolean()) disabled = flag->get<bool>();
        }
        row.open = !disabled;
        if (disabled) row.reason = "包内标记 Disabled=true";
        if (row.open) ++model.open;
        model.rows.push_back(std::move(row));
    }
    return model;
}

DailyModel DailyModel::loadShipped() {
    const fs::path directory = engine::generatedDir();
    if (directory.empty()) {
        throw std::runtime_error(
            "daily: metagame.json was not found; set PVZ_GENERATED_DIR or run from the repository "
            "root");
    }
    return load(directory / "metagame.json");
}

Json dailyJson(const DailyModel& model, const PageRange& range, int perPage) {
    Json out;
    out["screen"] = "daily";
    out["total"] = static_cast<int>(model.rows.size());
    out["open"] = model.open;
    out["tabs"] = model.tabs;
    out["perPage"] = perPage;
    out["page"] = range.page;
    out["pages"] = range.pages;
    Json visible = Json::array();
    for (int i = 0; i < range.count; ++i) {
        const DailyRow& row = model.rows[static_cast<std::size_t>(range.first + i)];
        Json item;
        item["id"] = row.id;
        item["title"] = row.title;
        item["target"] = row.targetType;
        item["reward"] = row.reward;
        item["open"] = row.open;
        item["payable"] = row.payable;
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
    SDL_Color closed = rgb(30, 33, 38);
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

Json renderDailyHeadless(const DailyModel& model, const DailyOptions& options) {
    const fs::path fontFile = options.assetRoot / "ui/font_zh.ttc";
    if (!fs::is_regular_file(fontFile)) {
        throw std::runtime_error(pathUtf8(fontFile) + ": cannot open the Chinese font");
    }

    PageRange range = PageRange::of(static_cast<int>(model.rows.size()), options.page,
                                    options.perPage);
    const bool headless = options.frames > 0;
    sdl::Display display(headless, "PvZ 2 SHUTTLE - Daily challenges");
    auto* renderer = display.renderer.get();
    TextRenderer text(renderer, fontFile);
    const Palette palette;

    int selected = range.first;
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

        fill(renderer, SDL_FRect{0, 0, DailyLayout::kWidth, DailyLayout::kHeight}, palette.page);
        fill(renderer, SDL_FRect{0, 0, DailyLayout::kWidth, 64}, palette.panel);
        text.draw(40, 16, 30, palette.ink, "每日挑战");
        text.draw(196, 26, 20, palette.muted,
                  "共 " + std::to_string(model.rows.size()) + " 项 · 开放 " +
                      std::to_string(model.open) + " · 页签 " + std::to_string(model.tabs));
        text.draw(40, 88, 16, palette.muted, "名称");
        text.draw(660, 88, 16, palette.muted, "目标");
        text.draw(920, 88, 16, palette.muted, "奖励");
        text.draw(1120, 88, 16, palette.muted, "状态");

        for (int i = 0; i < range.count; ++i) {
            const int index = range.first + i;
            const DailyRow& row = model.rows[static_cast<std::size_t>(index)];
            const float y = DailyLayout::kRowTop + static_cast<float>(i) * DailyLayout::kRowHeight;
            const SDL_FRect rect{DailyLayout::kRowLeft, y, DailyLayout::kRowWidth,
                                 DailyLayout::kRowHeight - 4.0f};
            const bool isSelected = index == selected;
            SDL_Color background = row.open ? palette.row : palette.closed;
            if (isSelected) background = palette.rowSelected;
            fill(renderer, rect, background);
            if (isSelected) border(renderer, rect, palette.accent);

            text.draw(rect.x + 16, y + 8, 20, row.open ? palette.ink : palette.muted, row.title);
            text.draw(660, y + 10, 16, palette.muted, row.targetType);
            text.draw(920, y + 10, 16, row.payable ? palette.accent : palette.warn, row.reward);
            const std::string status = row.open ? "开放" : "关闭";
            text.draw(1120, y + 10, 18, row.open ? palette.accent : palette.warn, status);
        }

        text.draw(40, 676, 18, palette.muted,
                  "第 " + std::to_string(range.page + 1) + "/" + std::to_string(range.pages) +
                      " 页 · PgUp/PgDn 翻页 · ↑↓ 选择 · Esc 退出");
        // The sheet has no date, so the screen states the rule it used instead of inventing a
        // countdown: Disabled is the only gate, and the report says the same in words.
        const std::string note = "排期字段只有 Disabled：false 即开放，包里没有日期";
        text.draw(1240.0f - text.width(note, 16), 676, 16, palette.warn, note);

        if (!options.snapshot.empty()) saveSnapshot(renderer, options.snapshot);
        sdl::require(SDL_RenderPresent(renderer), "present daily");
        ++frame;
        if (headless && frame >= options.frames) break;
        if (!headless) SDL_Delay(16);
    }
    return dailyJson(model, range, options.perPage);
}
#endif

}  // namespace pvz::meta
