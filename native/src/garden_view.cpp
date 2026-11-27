#include "garden_view.hpp"

#include "almanac_view.hpp"
#include "loc.hpp"
#include "sdl_support.hpp"
#include "text.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <stdexcept>
#include <utility>

namespace pvz {
namespace {

constexpr float kWidth = 1280.0f;
constexpr float kHeight = 720.0f;

SDL_Color rgb(int r, int g, int b, int a = 255) {
    return SDL_Color{static_cast<Uint8>(r), static_cast<Uint8>(g), static_cast<Uint8>(b),
                     static_cast<Uint8>(a)};
}

struct Palette {
    SDL_Color page = rgb(15, 22, 20);
    SDL_Color panel = rgb(24, 35, 30);
    SDL_Color row = rgb(32, 46, 38);
    SDL_Color rowSelected = rgb(48, 84, 60);
    SDL_Color ink = rgb(236, 238, 228);
    SDL_Color muted = rgb(146, 162, 154);
    SDL_Color dim = rgb(92, 108, 100);
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

std::size_t utf8Step(const std::string& text, std::size_t pos) {
    if (pos >= text.size()) return text.size();
    const unsigned char lead = static_cast<unsigned char>(text[pos]);
    std::size_t length = 1;
    if ((lead & 0xE0) == 0xC0) length = 2;
    else if ((lead & 0xF0) == 0xE0) length = 3;
    else if ((lead & 0xF8) == 0xF0) length = 4;
    return std::min(text.size(), pos + length);
}

/// Shortens a single line to `maxWidth`. Cutting by codepoint because every label here is Chinese:
/// a byte-wise cut would leave half a UTF-8 sequence and the renderer would draw a box.
std::string clip(TextRenderer& text, const std::string& value, int size, float maxWidth) {
    if (text.width(value, size) <= maxWidth) return value;
    std::string out;
    std::size_t pos = 0;
    while (pos < value.size()) {
        const std::size_t next = utf8Step(value, pos);
        if (text.width(out + value.substr(pos, next - pos) + "…", size) > maxWidth) break;
        out += value.substr(pos, next - pos);
        pos = next;
    }
    return out + "…";
}

Json readJsonOrNull(const std::filesystem::path& file, std::string& note) {
    std::ifstream in(file, std::ios::binary);
    if (!in) {
        if (!note.empty()) note += "; ";
        note += pathUtf8(file) + ": not found";
        return Json();
    }
    try {
        return Json::parse(in);
    } catch (const Json::exception& error) {
        if (!note.empty()) note += "; ";
        note += pathUtf8(file) + ": invalid JSON (" + error.what() + ")";
        return Json();
    }
}

std::string textField(const Json& object, const char* key) {
    if (!object.is_object()) return {};
    const auto found = object.find(key);
    if (found == object.end() || !found->is_string()) return {};
    return found->get<std::string>();
}

/// A property sheet value as text. Numbers keep their own spelling (`18000`, `1.7413`) rather than
/// going through a formatter that would turn `2` into `2.000000` on screen.
std::string scalarText(const Json& value) {
    if (value.is_string()) return value.get<std::string>();
    if (value.is_boolean()) return value.get<bool>() ? "true" : "false";
    if (value.is_number_integer()) return std::to_string(value.get<long long>());
    if (value.is_number_unsigned()) return std::to_string(value.get<unsigned long long>());
    if (value.is_number_float()) {
        char buffer[32];
        std::snprintf(buffer, sizeof buffer, "%.4g", value.get<double>());
        return buffer;
    }
    return {};
}

GardenSale readSale(const Json& soldAs) {
    GardenSale sale;
    if (!soldAs.is_object()) return sale;
    sale.matched = true;
    sale.matchKind = textField(soldAs, "matchKind");
    sale.sku = textField(soldAs, "sku");
    sale.objectItem = textField(soldAs, "objectItem");
    sale.priceKind = textField(soldAs, "priceKind");
    const std::string coins = textField(soldAs, "priceCoins");
    const std::string gems = textField(soldAs, "priceGems");
    const std::string mints = textField(soldAs, "priceMints");
    const std::string usd = textField(soldAs, "priceUsd");
    if (sale.priceKind == "gems") sale.amount = gems;
    else if (sale.priceKind == "coins") sale.amount = coins;
    else if (sale.priceKind == "mints") sale.amount = mints;
    else if (sale.priceKind == "usd") sale.amount = usd;
    // A matched row can still be priceless: `pinata_egypt` matched a SKU whose price fields are all
    // empty. That is the original's state, not a parse failure, so it prints as "未标价".
    sale.priced = !sale.priceKind.empty() && !sale.amount.empty() && sale.amount != "0";
    return sale;
}

std::vector<GardenDropSource> readSources(const Json& rows) {
    std::vector<GardenDropSource> out;
    if (!rows.is_array()) return out;
    for (const Json& row : rows) {
        GardenDropSource source;
        source.table = textField(row, "table");
        const auto examples = row.find("examples");
        if (examples != row.end() && examples->is_array()) {
            for (const Json& example : *examples)
                if (example.is_string()) source.examples.push_back(example.get<std::string>());
        }
        out.push_back(std::move(source));
    }
    return out;
}

GardenZen readZen(const Json& zen) {
    GardenZen out;
    if (!zen.is_object()) return out;
    for (const char* name : {"props", "slotProps", "bee", "floatingText"}) {
        const auto found = zen.find(name);
        if (found != zen.end() && found->is_object()) out.tables.push_back(name);
    }
    const auto props = zen.find("props");
    if (props != zen.end() && props->is_object()) {
        for (auto entry = props->begin(); entry != props->end(); ++entry) {
            if (entry.value().is_object()) {
                // `PotCosts` is an object of per-slot gem prices; flattened so the panel can list it.
                for (auto inner = entry.value().begin(); inner != entry.value().end(); ++inner) {
                    const std::string text = scalarText(inner.value());
                    if (!text.empty())
                        out.values.push_back(ZenValue{entry.key() + "." + inner.key(), text});
                }
                continue;
            }
            const std::string text = scalarText(entry.value());
            if (!text.empty()) out.values.push_back(ZenValue{entry.key(), text});
        }
    }
    const auto pots = zen.find("pots");
    if (pots != zen.end() && pots->is_array()) {
        for (const Json& pot : *pots) {
            ZenPot row;
            row.positionKey = textField(pot, "positionKey");
            const auto position = pot.find("position");
            if (position != pot.end() && position->is_object()) {
                row.position = scalarText((*position)["mX"]) + "," + scalarText((*position)["mY"]);
            }
            const auto unlock = pot.find("unlockIndex");
            if (unlock != pot.end()) row.unlockIndex = scalarText(*unlock);
            out.pots.push_back(std::move(row));
        }
    }
    const auto rewards = zen.find("plantRewards");
    if (rewards != zen.end() && rewards->is_array())
        out.plantRewards = static_cast<int>(rewards->size());
    return out;
}

}  // namespace

GardenData loadGarden(const std::filesystem::path& contentRoot) {
    GardenData data;
    data.source = metagameTablePath(contentRoot);
    std::string note;
    const Json document = readJsonOrNull(data.source, note);
    data.note = note;
    if (!document.is_object()) {
        throw std::runtime_error(pathUtf8(data.source) +
                                 ": cannot read metagame.json (regenerate it with "
                                 "tools/contentc/metagame.py)");
    }
    const auto garden = document.find("garden");
    if (garden == document.end() || !garden->is_object())
        throw std::runtime_error(pathUtf8(data.source) + ": metagame.json has no garden block");

    const auto collectables = garden->find("collectables");
    if (collectables != garden->end() && collectables->is_array()) {
        // B6b: the drop names live in the localisation table, keyed by `rewardDialogTitleKey`.
        // `loc::load` probes `<repo>/native/generated/` from the metagame table's grandparent and
        // never throws, so a build without the table keeps `title` empty and the panel falls back to
        // the "只有键" wording it printed before.
        const loc::Strings strings = loc::load(data.source.parent_path().parent_path().string());
        for (const Json& row : *collectables) {
            GardenItem item;
            item.typeName = textField(row, "typeName");
            if (item.typeName.empty()) continue;
            item.collectableClass = textField(row, "collectableClass");
            item.image = textField(row, "image");
            item.popAnim = textField(row, "popAnim");
            item.titleKey = textField(row, "rewardDialogTitleKey");
            if (!item.titleKey.empty())
                item.title = loc::resolve(strings, item.titleKey, std::string());
            item.storeCategory = textField(row, "storeCategory");
            const auto soldAs = row.find("soldAs");
            if (soldAs != row.end()) item.sale = readSale(*soldAs);
            const auto sources = row.find("dropSources");
            if (sources != row.end()) item.sources = readSources(*sources);
            data.drops.push_back(std::move(item));
        }
    }
    // Sorted by type name so the list does not reshuffle when the table is regenerated; the arrays
    // in `metagame.json` keep the OBB's own order, which is not stable across a recompile.
    std::sort(data.drops.begin(), data.drops.end(),
              [](const GardenItem& a, const GardenItem& b) { return a.typeName < b.typeName; });

    const auto zen = garden->find("zenGarden");
    if (zen != garden->end()) data.zen = readZen(*zen);
    return data;
}

GardenPage gardenPage(const std::vector<GardenItem>& drops, int index, int pageSize) {
    GardenPage page;
    page.total = static_cast<int>(drops.size());
    if (page.total == 0 || pageSize <= 0) return page;
    page.index = std::clamp(index, 0, page.total - 1);
    page.pages = (page.total + pageSize - 1) / pageSize;
    page.page = page.index / pageSize;
    page.first = page.page * pageSize;
    page.last = std::min(page.total, page.first + pageSize);
    for (int i = page.first; i < page.last; ++i) page.visible.push_back(i);
    return page;
}

Json gardenJson(int drops, int zen, int pots) {
    return Json{{"screen", "garden"}, {"drops", drops}, {"zen", zen}, {"pots", pots}};
}

GardenResult runGarden(const GardenData& data, int index, const GardenOptions& options) {
    const auto fontFile = options.assetRoot / "ui" / "font_zh.ttc";
    if (!std::filesystem::is_regular_file(fontFile))
        throw std::runtime_error(pathUtf8(fontFile) + ": cannot open the Chinese font");

    int selected = index;
    const bool headless = options.frames > 0;
    sdl::Display display(headless, "PvZ 2 SHUTTLE - Garden");
    auto* renderer = display.renderer.get();
    TextRenderer text(renderer, fontFile);
    const Palette palette;

    constexpr float kListX = 412.0f;
    constexpr float kListW = 480.0f;
    constexpr float kRowH = 28.0f;
    constexpr float kRowStep = 30.0f;
    constexpr float kFirstRowY = 104.0f;
    constexpr float kDetailX = 912.0f;
    constexpr float kDetailW = 336.0f;

    const int zenSheets = static_cast<int>(data.zen.tables.size());
    const int pots = static_cast<int>(data.zen.pots.size());

    GardenResult result;
    bool running = true;
    int frame = 0;
    while (running) {
        const GardenPage page = gardenPage(data.drops, selected);
        selected = page.index;

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
                        selected = std::min(page.total - 1, selected + 1);
                        break;
                    case SDLK_UP:
                        selected = std::max(0, selected - 1);
                        break;
                    case SDLK_PAGEDOWN:
                        selected = std::min(page.total - 1, selected + kGardenPageSize);
                        break;
                    case SDLK_PAGEUP:
                        selected = std::max(0, selected - kGardenPageSize);
                        break;
                    default:
                        break;
                }
            } else if (event.type == SDL_EVENT_MOUSE_BUTTON_DOWN) {
                for (int i = 0; i < static_cast<int>(page.visible.size()); ++i) {
                    const SDL_FRect rect{kListX, kFirstRowY + static_cast<float>(i) * kRowStep,
                                         kListW, kRowH};
                    if (event.button.x >= rect.x && event.button.x <= rect.x + rect.w &&
                        event.button.y >= rect.y && event.button.y <= rect.y + rect.h)
                        selected = page.visible[static_cast<std::size_t>(i)];
                }
            }
        }

        const GardenPage shown = gardenPage(data.drops, selected);
        const GardenItem* current =
            data.drops.empty() ? nullptr : &data.drops[static_cast<std::size_t>(shown.index)];

        fill(renderer, SDL_FRect{0, 0, kWidth, kHeight}, palette.page);
        fill(renderer, SDL_FRect{0, 0, kWidth, 76}, palette.panel);
        text.draw(40, 14, 30, palette.ink, "花园");
        text.draw(128, 22, 20, palette.muted, "掉落物 " + std::to_string(data.drops.size()) +
                                                 " · 禅境花园 4 表 · 花盆 " +
                                                 std::to_string(pots));
        const std::string counters =
            "Zen " + std::to_string(zenSheets) + "/4";
        text.draw(kWidth - 40 - text.width(counters, 20), 24, 20, palette.accent, counters);

        // ---- left column: the Zen garden sheets ----------------------------------------------
        fill(renderer, SDL_FRect{32, 88, 360, 560}, palette.panel);
        border(renderer, SDL_FRect{32, 88, 360, 560}, palette.muted);
        text.draw(52, 102, 22, palette.ink, "禅境花园");
        text.draw(52, 132, 16, palette.dim, "四张属性表 " + std::to_string(zenSheets) + "/4");
        float y = 156;
        for (const std::string& table : data.zen.tables) {
            text.draw(52, y, 17, palette.accent, "✓ " + table);
            y += 22;
        }
        y += 6;
        int listed = 0;
        for (const ZenValue& value : data.zen.values) {
            if (listed >= 9) break;
            const std::string line = value.name + " = " + value.text;
            text.draw(52, y, 15, palette.muted, clip(text, line, 15, 320));
            y += 19;
            ++listed;
        }
        if (static_cast<int>(data.zen.values.size()) > listed)
            text.draw(52, y, 15, palette.dim,
                      "… 另有 " + std::to_string(data.zen.values.size() - listed) + " 项");
        y += 26;

        // Twelve pots, drawn as the grid they are: three columns of four unlock slots.
        text.draw(52, y, 17, palette.muted, "花盆 " + std::to_string(pots) + " 个");
        y += 24;
        for (int i = 0; i < static_cast<int>(data.zen.pots.size()); ++i) {
            const float px = 52.0f + static_cast<float>(i % 3) * 84.0f;
            const float py = y + static_cast<float>(i / 3) * 34.0f;
            fill(renderer, SDL_FRect{px, py, 76, 28}, palette.row);
            border(renderer, SDL_FRect{px, py, 76, 28}, palette.dim);
            text.draw(px + 6, py + 5, 14, palette.muted,
                      clip(text, data.zen.pots[static_cast<std::size_t>(i)].positionKey, 14, 64));
        }
        y += static_cast<float>((pots + 2) / 3) * 34.0f + 10;
        text.draw(52, y, 16, palette.dim,
                  "植物奖励表 " + std::to_string(data.zen.plantRewards) + " 张");

        // ---- middle column: the drop list ----------------------------------------------------
        fill(renderer, SDL_FRect{kListX, 88, kListW, 560}, palette.panel);
        border(renderer, SDL_FRect{kListX, 88, kListW, 560}, palette.muted);
        text.draw(kListX + 14, 96, 20, palette.ink, "掉落物 " + std::to_string(shown.total) + " 条");
        for (int i = 0; i < static_cast<int>(shown.visible.size()); ++i) {
            const GardenItem& item =
                data.drops[static_cast<std::size_t>(shown.visible[static_cast<std::size_t>(i)])];
            const SDL_FRect rect{kListX + 12, kFirstRowY + static_cast<float>(i) * kRowStep,
                                 kListW - 24, kRowH};
            const bool active = shown.visible[static_cast<std::size_t>(i)] == shown.index;
            fill(renderer, rect, active ? palette.rowSelected : palette.row);
            if (active) border(renderer, rect, palette.accent);
            text.draw(rect.x + 10, rect.y + 4, 17, palette.ink, clip(text, item.typeName, 17, 240));
            const std::string sources =
                item.sources.empty() ? std::string("无来源记录")
                                     : "来源 " + std::to_string(item.sources.size()) + " 条";
            text.draw(rect.x + 262, rect.y + 5, 15,
                      item.sources.empty() ? palette.dim : palette.muted, sources);
            const std::string price =
                item.sale.priced ? item.sale.amount + " " + item.sale.priceKind
                                 : (item.sale.matched ? std::string("未标价") : std::string());
            if (!price.empty())
                text.draw(rect.x + rect.w - 10 - text.width(price, 15), rect.y + 5, 15,
                          item.sale.priced ? palette.accent : palette.dim, price);
            if (active) result.selectedRect = ScreenRect{rect.x, rect.y, rect.w, rect.h};
        }
        if (shown.total == 0) text.draw(kListX + 14, kFirstRowY + 10, 18, palette.warn, "没有掉落物");
        text.draw(kListX + 14, kFirstRowY + static_cast<float>(kGardenPageSize) * kRowStep + 10, 16,
                  palette.muted,
                  "显示 " + std::to_string(shown.first + 1) + " - " + std::to_string(shown.last) +
                      " / " + std::to_string(shown.total) + " · 第 " +
                      std::to_string(shown.page + 1) + "/" + std::to_string(shown.pages) + " 页");

        // ---- right column: the selected collectable -------------------------------------------
        fill(renderer, SDL_FRect{kDetailX, 88, kDetailW, 560}, palette.panel);
        border(renderer, SDL_FRect{kDetailX, 88, kDetailW, 560}, palette.muted);
        if (current != nullptr) {
            float dy = 104;
            text.draw(kDetailX + 18, dy, 22, palette.ink, clip(text, current->typeName, 22, 300));
            dy += 32;
            text.draw(kDetailX + 18, dy, 16, palette.dim,
                      clip(text, current->collectableClass, 16, 300));
            dy += 26;
            text.draw(kDetailX + 18, dy, 17, palette.muted,
                      "标题键 " + clip(text, current->titleKey, 17, 240));
            dy += 24;
            text.draw(kDetailX + 18, dy, 17, palette.muted,
                      current->title.empty() ? "标题：原版无文案（只有键）" : "标题：" + current->title);
            dy += 24;
            if (!current->image.empty()) {
                text.draw(kDetailX + 18, dy, 15, palette.dim, "图 " + current->image);
                dy += 20;
            }
            if (!current->popAnim.empty()) {
                text.draw(kDetailX + 18, dy, 15, palette.dim,
                          "动画 " + clip(text, current->popAnim, 15, 290));
                dy += 20;
            }
            if (!current->storeCategory.empty()) {
                text.draw(kDetailX + 18, dy, 15, palette.dim,
                          "商店品类 " + current->storeCategory + "（品类名不是商品）");
                dy += 20;
            }
            dy += 8;
            if (current->sale.matched) {
                text.draw(kDetailX + 18, dy, 17, palette.muted,
                          "商店匹配 " + current->sale.matchKind);
                dy += 22;
                text.draw(kDetailX + 18, dy, 15, palette.dim,
                          clip(text, current->sale.sku, 15, 290));
                dy += 20;
                const std::string line = current->sale.priced
                                             ? "价格 " + current->sale.amount + " " +
                                                   current->sale.priceKind
                                             : std::string("价格：原版未标价");
                text.draw(kDetailX + 18, dy, 17,
                          current->sale.priced ? palette.accent : palette.warn, line);
                dy += 24;
            } else {
                text.draw(kDetailX + 18, dy, 17, palette.dim, "商店：65 条里只有 2 条有商品或价格");
                dy += 24;
            }
            dy += 6;
            text.draw(kDetailX + 18, dy, 17, palette.muted, "掉落来源");
            dy += 24;
            if (current->sources.empty()) {
                text.draw(kDetailX + 18, dy, 16, palette.dim, "原版没有登记来源");
                dy += 22;
                text.draw(kDetailX + 18, dy, 15, palette.dim,
                          "65 条里只有 6 条带来源引用");
            } else {
                for (const GardenDropSource& source : current->sources) {
                    text.draw(kDetailX + 18, dy, 16, palette.ink, clip(text, source.table, 16, 290));
                    dy += 20;
                    for (const std::string& example : source.examples) {
                        text.draw(kDetailX + 34, dy, 15, palette.dim,
                                  clip(text, example, 15, 270));
                        dy += 18;
                    }
                }
                text.draw(kDetailX + 18, dy, 15, palette.dim,
                          "来源是奖励表引用，不是关卡 id");
            }
        } else {
            text.draw(kDetailX + 18, 108, 20, palette.warn, "没有可显示的掉落物");
        }

        text.draw(40, 664, 18, palette.muted,
                  "↑↓ 选择 · PgUp/PgDn 翻页（每页 12 行） · Esc 退出");
        if (!data.source.empty())
            text.draw(40, 690, 15, palette.dim, "数据：" + pathUtf8(data.source));
        if (!data.note.empty()) text.draw(40, 706, 14, palette.dim, "备注：" + data.note);

        result.drops = shown.total;
        result.zen = zenSheets;
        result.zenTables = zenSheets;
        result.zenPots = pots;
        result.selectedTypeName = current == nullptr ? std::string() : current->typeName;
        result.json = gardenJson(shown.total, zenSheets, pots);

        if (!options.snapshot.empty()) saveScreenSnapshot(renderer, options.snapshot);
        sdl::require(SDL_RenderPresent(renderer), "present garden");
        ++frame;
        if (headless && frame >= options.frames) break;
        if (!headless) SDL_Delay(16);
    }
    return result;
}

Json renderGardenHeadless(const std::filesystem::path& contentRoot, int frames,
                          const std::filesystem::path& snapshot,
                          const std::filesystem::path& assetRoot) {
    const GardenData data = loadGarden(contentRoot);
    GardenOptions options;
    options.contentRoot = contentRoot;
    options.assetRoot = assetRoot.empty() ? defaultAssetRoot(contentRoot) : assetRoot;
    options.snapshot = snapshot;
    options.frames = frames;
    const GardenResult result = runGarden(data, 0, options);
    return result.json;
}

}  // namespace pvz
