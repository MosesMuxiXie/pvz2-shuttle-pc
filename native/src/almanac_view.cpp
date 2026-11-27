#include "almanac_view.hpp"

#include "loc.hpp"
#include "sdl_support.hpp"
#include "text.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdlib>
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
    SDL_Color page = rgb(14, 20, 26);
    SDL_Color panel = rgb(24, 34, 42);
    SDL_Color row = rgb(32, 45, 54);
    SDL_Color rowSelected = rgb(50, 84, 68);
    SDL_Color rowLocked = rgb(26, 31, 36);
    SDL_Color ink = rgb(238, 238, 226);
    SDL_Color muted = rgb(146, 160, 166);
    SDL_Color dim = rgb(92, 104, 110);
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

std::string lower(std::string value) {
    for (char& c : value) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return value;
}

// `zombies` and `Zombie` both mean the right column; anything else is a plant. Kept here so
// `entries()` and `runAlmanac()` cannot disagree about what "plant" means.
std::string normalizeKind(const std::string& raw) {
    const std::string text = lower(raw);
    return (text == "zombie" || text == "zombies") ? "zombie" : "plant";
}

const char* kindLabel(const std::string& kind) { return kind == "zombie" ? "僵尸" : "植物"; }

std::size_t utf8Step(const std::string& text, std::size_t pos) {
    if (pos >= text.size()) return text.size();
    const unsigned char lead = static_cast<unsigned char>(text[pos]);
    std::size_t length = 1;
    if ((lead & 0xE0) == 0xC0) length = 2;
    else if ((lead & 0xF0) == 0xE0) length = 3;
    else if ((lead & 0xF8) == 0xF0) length = 4;
    return std::min(text.size(), pos + length);
}

// Wraps by codepoint, not by space: the descriptions are Chinese and contain no spaces at all, so
// a word wrapper would emit one over-long line and then clip it.
std::vector<std::string> wrapText(TextRenderer& text, const std::string& value, int size,
                                  float maxWidth, std::size_t maxLines) {
    std::vector<std::string> lines;
    if (value.empty() || maxLines == 0) return lines;
    std::size_t start = 0;
    while (start < value.size() && lines.size() < maxLines) {
        std::size_t end = start;
        std::size_t lastFit = start;
        while (end < value.size()) {
            const std::size_t next = utf8Step(value, end);
            if (text.width(value.substr(start, next - start), size) > maxWidth) break;
            lastFit = next;
            end = next;
        }
        if (lastFit == start) lastFit = utf8Step(value, start);  // one glyph wider than the panel
        lines.push_back(value.substr(start, lastFit - start));
        start = lastFit;
    }
    if (start < value.size() && !lines.empty()) {
        std::string& last = lines.back();
        while (!last.empty() && text.width(last + "…", size) > maxWidth) {
            std::size_t cut = last.size();
            // Step back one codepoint: `cut` may sit inside a multi-byte sequence.
            while (cut > 0 && (static_cast<unsigned char>(last[cut - 1]) & 0xC0) == 0x80) --cut;
            if (cut > 0) --cut;
            while (cut > 0 && (static_cast<unsigned char>(last[cut]) & 0xC0) == 0x80) --cut;
            last = last.substr(0, cut);
        }
        last += "…";
    }
    return lines;
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

int intField(const Json& object, const char* key, int fallback) {
    if (!object.is_object()) return fallback;
    const auto found = object.find(key);
    if (found == object.end() || !found->is_number_integer()) return fallback;
    return found->get<int>();
}

/// Display text the compiled table does not carry: `content/*.json` keeps the prose for the ids it
/// knows, and `content/almanac.json` keeps the almanac blurb keyed by plant id.
struct DisplayText {
    std::string name;
    std::string description;
    int cost = -1;
    int hp = -1;
};

struct DisplayTables {
    std::map<std::string, DisplayText> plants;
    std::map<std::string, DisplayText> zombies;
    std::string note;
};

DisplayText readDisplayEntry(const Json& object) {
    DisplayText out;
    out.name = textField(object, "name_zh");
    if (out.name.empty()) out.name = textField(object, "name_en");
    out.description = textField(object, "desc_zh");
    out.cost = intField(object, "cost", -1);
    out.hp = intField(object, "hp", -1);
    return out;
}

DisplayTables loadDisplayTables(const std::filesystem::path& contentRoot) {
    DisplayTables tables;
    const Json plants = readJsonOrNull(contentRoot / "plants.json", tables.note);
    if (plants.is_array()) {
        for (const Json& row : plants) {
            const std::string id = textField(row, "id");
            if (!id.empty()) tables.plants[id] = readDisplayEntry(row);
        }
    }
    const Json zombies = readJsonOrNull(contentRoot / "zombies.json", tables.note);
    if (zombies.is_array()) {
        for (const Json& row : zombies) {
            const std::string id = textField(row, "id");
            if (!id.empty()) tables.zombies[id] = readDisplayEntry(row);
        }
    }
    // `almanac.json` is the one file with a real blurb; it only covers the plants the client
    // itself ships, which is 27 of the 167 almanac rows.
    const Json almanac = readJsonOrNull(contentRoot / "almanac.json", tables.note);
    const auto list = almanac.is_object() ? almanac.find("plants") : almanac.end();
    if (almanac.is_object() && list != almanac.end() && list->is_object()) {
        for (auto entry = list->begin(); entry != list->end(); ++entry) {
            const Json& row = entry.value();
            const std::string desc = textField(row, "desc");
            auto found = tables.plants.find(entry.key());
            if (found == tables.plants.end()) {
                DisplayText created;
                created.description = desc;
                tables.plants[entry.key()] = created;
            } else if (!desc.empty()) {
                found->second.description = desc;
            }
        }
    }
    return tables;
}

std::string familyToken(const Json& stats) {
    if (!stats.is_array()) return {};
    for (const Json& stat : stats) {
        if (textField(stat, "statType") != "family") continue;
        std::string key = textField(stat, "valueKey");
        const std::string prefix = "STAT_FAMILY_";
        if (key.rfind(prefix, 0) == 0) key = key.substr(prefix.size());
        return lower(key);
    }
    return {};
}

std::string statValueKey(const Json& stats, const char* type) {
    if (!stats.is_array()) return {};
    for (const Json& stat : stats) {
        if (textField(stat, "statType") == type) return textField(stat, "valueKey");
    }
    return {};
}

std::vector<AlmanacStat> readStats(const Json& stats) {
    std::vector<AlmanacStat> out;
    if (!stats.is_array()) return out;
    for (const Json& stat : stats) {
        AlmanacStat row;
        row.type = textField(stat, "statType");
        row.name = textField(stat, "statName");
        row.typeKey = textField(stat, "typeKey");
        row.valueKey = textField(stat, "valueKey");
        out.push_back(std::move(row));
    }
    return out;
}

std::vector<AlmanacEntry> readEntries(const Json& rows, const std::string& kind,
                                      const std::map<std::string, DisplayText>& display,
                                      const loc::Strings& strings) {
    std::vector<AlmanacEntry> entries;
    if (!rows.is_array()) return entries;
    for (const Json& row : rows) {
        AlmanacEntry entry;
        entry.id = textField(row, "id");
        if (entry.id.empty()) continue;
        entry.kind = kind;
        entry.nameKey = textField(row, "nameKey");
        entry.descKey = textField(row, "descKey");
        entry.world = textField(row, "world");
        entry.levels = intField(row, "levels", 0);
        // `row["stats"]` on a const json goes through `at()` and throws for a row without the key,
        // so the array is looked up once and an absent one is an empty one.
        static const Json kNoStats = Json::array();
        const auto statsIt = row.find("stats");
        const Json& stats = statsIt == row.end() ? kNoStats : *statsIt;
        entry.stats = readStats(stats);
        entry.family = kind == "zombie" ? textField(row, "zombieClass") : familyToken(stats);
        entry.costKey = statValueKey(stats, "suncost");
        entry.hpKey = statValueKey(stats, "armor");
        const auto found = display.find(entry.id);
        if (found != display.end()) {
            entry.name = found->second.name;
            entry.nameFromContent = !entry.name.empty();
            entry.description = found->second.description;
            entry.cost = found->second.cost;
            entry.hp = found->second.hp;
        }
        // B6b: the content tables are hand-written and cover a subset of the roster, so the
        // localisation table is the second source, keyed by the metagame entry's own key. Order is
        // content name_zh -> LawnStrings -> the raw id; `nameFromContent` still means "a content
        // table named this", so the screen can tell the three cases apart.
        if (entry.name.empty() && !entry.nameKey.empty())
            entry.name = loc::resolve(strings, entry.nameKey, std::string());
        if (entry.description.empty() && !entry.descKey.empty())
            entry.description = loc::resolve(strings, entry.descKey, std::string());
        if (entry.name.empty()) entry.name = entry.id;
        entries.push_back(std::move(entry));
    }
    // Sorted by id here rather than trusting the file's order: the table is written with
    // `sort_keys`, the arrays are not, and a re-generated table must not reshuffle the screen.
    std::sort(entries.begin(), entries.end(),
              [](const AlmanacEntry& a, const AlmanacEntry& b) { return a.id < b.id; });
    return entries;
}

/// Almanac `HomeWorld` tokens that name a content world by another spelling. `tutorial` is the
/// frontyard intro and `skycity` ships as `sky`; every other token is compared verbatim so a
/// missing mapping can only make an entry *visible*, never invisible.
const std::pair<const char*, const char*> kWorldAliases[] = {
    {"tutorial", "frontyard"},
    {"skycity", "sky"},
};

std::string worldPrefix(const std::string& levelId) {
    std::size_t cut = 0;
    while (cut < levelId.size()) {
        const unsigned char c = static_cast<unsigned char>(levelId[cut]);
        if (std::isdigit(c) || c == '_' || c == '/') break;
        ++cut;
    }
    return lower(levelId.substr(0, cut));
}

/// The localisation table that lives beside the metagame table (B6b).
///
/// `metagameFile` is `<repo>/native/generated/metagame.json`, so its grandparent is the repository
/// root and `loc::load()` probes `<root>/native/generated/lawn_strings.json` from there. Passing the
/// metagame path instead of a content root keeps the two tables from drifting apart: whoever moves
/// one has to move the other. A missing table is not an error - `loc::resolve` then returns the
/// caller's fallback, which is the old behaviour.
loc::Strings loadStrings(const std::filesystem::path& metagameFile) {
    if (metagameFile.empty()) return loc::load(std::string());
    const std::filesystem::path root = metagameFile.parent_path().parent_path();
    return loc::load(root.string());
}

/// A key rendered as itself when the table cannot answer, which is what this screen did before the
/// table existed. `humanizeGameKey` is deliberately not used here: the almanac never had it, so
/// wiring the table must not change the shape of the output when the table is absent.
std::string resolveKey(const loc::Strings& strings, const std::string& key) {
    if (key.empty()) return std::string();
    return loc::resolve(strings, key, key);
}

}  // namespace

const std::vector<AlmanacEntry>& AlmanacData::entries(const std::string& kind) const {
    return kind == "zombie" ? zombies : plants;
}

std::filesystem::path metagameTablePath(const std::filesystem::path& contentRoot) {
    const std::filesystem::path root = contentRoot.parent_path();
    for (const auto& directory : {root / "generated", root / "native" / "generated"}) {
        std::error_code error;
        if (std::filesystem::is_regular_file(directory / "metagame.json", error))
            return directory / "metagame.json";
    }
    if (const char* configured = std::getenv("PVZ_GENERATED_DIR")) {
        if (configured[0] != '\0') {
            std::error_code error;
            const std::filesystem::path candidate =
                std::filesystem::path(configured) / "metagame.json";
            if (std::filesystem::is_regular_file(candidate, error)) return candidate;
        }
    }
    return root / "native" / "generated" / "metagame.json";
}

AlmanacData loadAlmanac(const std::filesystem::path& contentRoot) {
    AlmanacData data;
    data.source = metagameTablePath(contentRoot);
    std::string note;
    const Json document = readJsonOrNull(data.source, note);
    if (!document.is_object()) {
        throw std::runtime_error(pathUtf8(data.source) +
                                 ": cannot read metagame.json (regenerate it with "
                                 "tools/contentc/metagame.py)");
    }
    const DisplayTables display = loadDisplayTables(contentRoot);
    const loc::Strings strings = loadStrings(data.source);
    note = note.empty() ? display.note : (display.note.empty() ? note : note + "; " + display.note);
    data.note = note;

    const auto almanac = document.find("almanac");
    if (almanac == document.end() || !almanac->is_object())
        throw std::runtime_error(pathUtf8(data.source) + ": metagame.json has no almanac block");
    const auto plants = almanac->find("plants");
    const auto zombies = almanac->find("zombies");
    if (plants != almanac->end()) data.plants = readEntries(*plants, "plant", display.plants, strings);
    if (zombies != almanac->end())
        data.zombies = readEntries(*zombies, "zombie", display.zombies, strings);
    return data;
}

std::vector<std::string> almanacClearedWorlds(const Progress& progress) {
    std::vector<std::string> worlds;
    for (const auto& entry : progress.levels) {
        if (!entry.second.cleared) continue;
        const std::string prefix = worldPrefix(entry.first);
        if (prefix.empty()) continue;
        if (std::find(worlds.begin(), worlds.end(), prefix) == worlds.end()) worlds.push_back(prefix);
    }
    std::sort(worlds.begin(), worlds.end());
    return worlds;
}

AlmanacData almanacWithProgress(AlmanacData data, const Progress* progress) {
    // No save at all, or a save that has not beaten anything: everything is visible. A wall of
    // grey on a fresh install would say "you know nothing" when the point is "there is a shelf".
    if (progress == nullptr || progress->clearedLevels() == 0) return data;
    const std::vector<std::string> cleared = almanacClearedWorlds(*progress);
    const auto revealed = [&cleared](const std::string& world) {
        if (world.empty()) return true;  // no world token: nothing can gate it
        const std::string token = lower(world);
        if (std::find(cleared.begin(), cleared.end(), token) != cleared.end()) return true;
        for (const auto& alias : kWorldAliases) {
            if (token == alias.first &&
                std::find(cleared.begin(), cleared.end(), alias.second) != cleared.end())
                return true;
        }
        return false;
    };
    for (auto* list : {&data.plants, &data.zombies}) {
        for (AlmanacEntry& entry : *list) entry.seen = revealed(entry.world);
    }
    return data;
}

AlmanacPage almanacPage(const std::vector<AlmanacEntry>& entries, int index, int pageSize) {
    AlmanacPage page;
    page.total = static_cast<int>(entries.size());
    if (page.total == 0 || pageSize <= 0) return page;
    page.index = std::clamp(index, 0, page.total - 1);
    page.pages = (page.total + pageSize - 1) / pageSize;
    page.page = page.index / pageSize;
    page.first = page.page * pageSize;
    page.last = std::min(page.total, page.first + pageSize);
    for (int i = page.first; i < page.last; ++i) page.visible.push_back(i);
    return page;
}

Json almanacJson(const std::string& kind, int index, int total) {
    return Json{{"screen", "almanac"}, {"kind", kind}, {"index", index}, {"total", total}};
}

std::filesystem::path defaultAssetRoot(const std::filesystem::path& contentRoot) {
    if (const char* configured = std::getenv("PVZ_ASSET_ROOT")) {
        if (configured[0] != '\0') return std::filesystem::path(configured);
    }
    const std::filesystem::path root = contentRoot.parent_path();
    std::error_code error;
    if (std::filesystem::is_regular_file(root / "assets" / "ui" / "font_zh.ttc", error))
        return root / "assets";
    const std::filesystem::path workspace = root.parent_path();
    if (std::filesystem::is_regular_file(workspace / "PvZ2SHUTTLE" / "assets" / "ui" / "font_zh.ttc",
                                         error))
        return workspace / "PvZ2SHUTTLE" / "assets";
    return root / "assets";
}

AlmanacResult runAlmanac(const AlmanacData& data, const std::string& kind, int index,
                         const AlmanacOptions& options) {
    const auto fontFile = options.assetRoot / "ui" / "font_zh.ttc";
    if (!std::filesystem::is_regular_file(fontFile))
        throw std::runtime_error(pathUtf8(fontFile) + ": cannot open the Chinese font");

    std::string currentKind = normalizeKind(kind);
    int selected = index;

    const bool headless = options.frames > 0;
    sdl::Display display(headless, "PvZ 2 SHUTTLE - Almanac");
    auto* renderer = display.renderer.get();
    TextRenderer text(renderer, fontFile);
    const Palette palette;
    // The table itself so the detail panel can resolve the fact labels it only knows as keys
    // (`STAT_TOUGHNESS_ARMOR0` -> 普通). Loaded once per run, never per frame.
    const loc::Strings strings = loadStrings(data.source);

    constexpr float kListX = 248.0f;
    constexpr float kListW = 520.0f;
    constexpr float kRowH = 28.0f;
    constexpr float kRowStep = 30.0f;
    constexpr float kFirstRowY = 96.0f;
    constexpr float kDetailX = 792.0f;
    constexpr float kDetailW = 456.0f;

    AlmanacResult result;
    bool running = true;
    int frame = 0;
    while (running) {
        const AlmanacPage page = almanacPage(data.entries(currentKind), selected);
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
                        selected = std::min(page.total - 1, selected + kAlmanacPageSize);
                        break;
                    case SDLK_PAGEUP:
                        selected = std::max(0, selected - kAlmanacPageSize);
                        break;
                    case SDLK_LEFT:
                    case SDLK_RIGHT:
                    case SDLK_TAB:
                        currentKind = currentKind == "plant" ? "zombie" : "plant";
                        selected = 0;
                        break;
                    default:
                        break;
                }
            } else if (event.type == SDL_EVENT_MOUSE_BUTTON_DOWN) {
                // A click on a category row switches columns; a click inside the list selects the
                // row it landed on. Both are mapped back through the same window the drawing uses.
                for (int category = 0; category < 2; ++category) {
                    const SDL_FRect rect{32.0f, 96.0f + static_cast<float>(category) * 40.0f, 200.0f,
                                         34.0f};
                    if (event.button.x >= rect.x && event.button.x <= rect.x + rect.w &&
                        event.button.y >= rect.y && event.button.y <= rect.y + rect.h) {
                        const std::string wanted = category == 0 ? "plant" : "zombie";
                        if (wanted != currentKind) {
                            currentKind = wanted;
                            selected = 0;
                        }
                    }
                }
                for (int i = 0; i < static_cast<int>(page.visible.size()); ++i) {
                    const SDL_FRect rect{kListX, kFirstRowY + static_cast<float>(i) * kRowStep, kListW,
                                         kRowH};
                    if (event.button.x >= rect.x && event.button.x <= rect.x + rect.w &&
                        event.button.y >= rect.y && event.button.y <= rect.y + rect.h)
                        selected = page.visible[static_cast<std::size_t>(i)];
                }
            }
        }

        const AlmanacPage shown = almanacPage(data.entries(currentKind), selected);
        const auto& list = data.entries(currentKind);
        const AlmanacEntry* current =
            list.empty() ? nullptr : &list[static_cast<std::size_t>(shown.index)];

        fill(renderer, SDL_FRect{0, 0, kWidth, kHeight}, palette.page);
        fill(renderer, SDL_FRect{0, 0, kWidth, 76}, palette.panel);
        text.draw(40, 14, 30, palette.ink, "图鉴");
        text.draw(128, 22, 20, palette.muted, std::string("分类 ") + kindLabel(currentKind) + " · " +
                                                       std::to_string(shown.total) + " 条");
        int unlocked = 0;
        for (const AlmanacEntry& entry : list)
            if (entry.seen) ++unlocked;
        const std::string counters = "已解锁 " + std::to_string(unlocked) + " / " +
                                     std::to_string(shown.total);
        text.draw(kWidth - 40 - text.width(counters, 20), 24, 20, palette.accent, counters);

        // ---- left column: the two categories ------------------------------------------------
        for (int category = 0; category < 2; ++category) {
            const std::string name = category == 0 ? "plant" : "zombie";
            const SDL_FRect rect{32.0f, 96.0f + static_cast<float>(category) * 40.0f, 200.0f, 34.0f};
            const bool active = name == currentKind;
            fill(renderer, rect, active ? palette.rowSelected : palette.panel);
            if (active) border(renderer, rect, palette.accent);
            const int count = static_cast<int>(data.entries(name).size());
            text.draw(rect.x + 14, rect.y + 6, 20, active ? palette.ink : palette.muted,
                      std::string(kindLabel(name)) + " " + std::to_string(count));
            if (active) result.selectedRect = ScreenRect{rect.x, rect.y, rect.w, rect.h};
        }

        // ---- middle column: one page of twelve rows ------------------------------------------
        if (shown.total == 0) {
            text.draw(kListX, kFirstRowY + 20, 22, palette.warn, "没有图鉴条目");
        } else {
            for (int i = 0; i < static_cast<int>(shown.visible.size()); ++i) {
                const AlmanacEntry& entry = list[static_cast<std::size_t>(shown.visible[
                    static_cast<std::size_t>(i)])];
                const SDL_FRect rect{kListX, kFirstRowY + static_cast<float>(i) * kRowStep, kListW,
                                     kRowH};
                SDL_Color background = entry.seen ? palette.row : palette.rowLocked;
                if (shown.visible[static_cast<std::size_t>(i)] == shown.index)
                    background = palette.rowSelected;
                fill(renderer, rect, background);
                if (shown.visible[static_cast<std::size_t>(i)] == shown.index)
                    border(renderer, rect, palette.accent);
                const std::string order = "#" + std::to_string(shown.visible[
                                                     static_cast<std::size_t>(i)] + 1);
                text.draw(rect.x + 10, rect.y + 4, 16, palette.dim, order);
                text.draw(rect.x + 66, rect.y + 3, 18, entry.seen ? palette.ink : palette.dim,
                          entry.name);
                if (!entry.world.empty())
                    text.draw(rect.x + kListW - 10 - text.width(entry.world, 15), rect.y + 5, 15,
                              entry.seen ? palette.muted : palette.dim, entry.world);
                if (shown.visible[static_cast<std::size_t>(i)] == shown.index)
                    result.selectedRect = ScreenRect{rect.x, rect.y, rect.w, rect.h};
            }
            text.draw(kListX, kFirstRowY + static_cast<float>(kAlmanacPageSize) * kRowStep + 8, 16,
                      palette.muted,
                      "显示 " + std::to_string(shown.first + 1) + " - " +
                          std::to_string(shown.last) + " / " + std::to_string(shown.total) +
                          " · 第 " + std::to_string(shown.page + 1) + "/" +
                          std::to_string(shown.pages) + " 页");
        }

        // ---- right column: the detail panel --------------------------------------------------
        fill(renderer, SDL_FRect{kDetailX, 88, kDetailW, 560}, palette.panel);
        border(renderer, SDL_FRect{kDetailX, 88, kDetailW, 560}, palette.muted);
        if (current != nullptr) {
            float y = 104;
            text.draw(kDetailX + 20, y, 26, current->seen ? palette.ink : palette.dim, current->name);
            y += 38;
            text.draw(kDetailX + 20, y, 16, palette.dim, current->id + " · " + current->kind);
            y += 26;
            text.draw(kDetailX + 20, y, 18, current->seen ? palette.accent : palette.dim,
                      current->id == current->name ? "名称：无中文文案（内容表未收录）"
                                                   : "名称：" + current->name);
            y += 26;
            const std::string worldText =
                current->world.empty() ? "世界：表内未标注" : "世界：" + current->world;
            text.draw(kDetailX + 20, y, 18, palette.muted, worldText);
            y += 26;
            const std::string familyText =
                current->family.empty() ? std::string("族/类型：无")
                                        : "族/类型：" + current->family;
            text.draw(kDetailX + 20, y, 18, palette.muted, familyText);
            y += 26;

            // `resolveKey` answers the key itself when the table has no row, so an unresolved fact
            // keeps the old "只有分级键" wording instead of printing a bare token. With the table
            // present the same slot shows the localised grade (普通 / 沙包 …).
            const std::string costValue = resolveKey(strings, current->costKey);
            const std::string costText =
                current->cost >= 0
                    ? "阳光 " + std::to_string(current->cost)
                    : (current->costKey.empty()
                           ? std::string("阳光：表内无")
                           : (costValue == current->costKey ? "阳光：只有分级键 " + current->costKey
                                                            : "阳光：" + costValue));
            text.draw(kDetailX + 20, y, 18, palette.muted, costText);
            y += 24;
            const std::string hpValue = resolveKey(strings, current->hpKey);
            const std::string hpText =
                current->hp >= 0
                    ? "生命 " + std::to_string(current->hp)
                    : (current->hpKey.empty()
                           ? std::string("生命：表内无")
                           : (hpValue == current->hpKey ? "生命：只有分级键 " + current->hpKey
                                                        : "生命：" + hpValue));
            text.draw(kDetailX + 20, y, 18, palette.muted, hpText);
            y += 24;
            // The table ships a count of referencing level packages, not a first level id.
            text.draw(kDetailX + 20, y, 18, palette.muted,
                      "出场关卡 " + std::to_string(current->levels) + " 关（表内只给计数）");
            y += 30;

            if (current->description.empty()) {
                text.draw(kDetailX + 20, y, 17, palette.warn, "描述：metagame 表只有本地化键");
                y += 22;
                text.draw(kDetailX + 20, y, 16, palette.dim, current->descKey);
                y += 26;
            } else {
                text.draw(kDetailX + 20, y, 17, palette.dim, "描述");
                y += 22;
                for (const std::string& line :
                     wrapText(text, current->description, 17, kDetailW - 40, 4)) {
                    text.draw(kDetailX + 20, y, 17, palette.ink, line);
                    y += 22;
                }
                y += 4;
            }

            // The stat sheet, only the rows the panel has room for. The label is the fact name as the
            // table spells it ("Armor", "Special", …) and the value is a localisation key; with the
            // table available it becomes 普通 / 沙包 …, without it the key is shown as before.
            int shownStats = 0;
            for (const AlmanacStat& stat : current->stats) {
                if (shownStats >= 6) break;
                const std::string line = stat.type + " · " + resolveKey(strings, stat.valueKey);
                text.draw(kDetailX + 20, y, 15, palette.dim, line);
                y += 18;
                ++shownStats;
            }
            if (static_cast<int>(current->stats.size()) > shownStats)
                text.draw(kDetailX + 20, y, 15, palette.dim,
                          "… 另有 " + std::to_string(current->stats.size() - shownStats) + " 条");

            text.draw(kDetailX + 20, 596, 16,
                      current->seen ? palette.accent : palette.warn,
                      current->seen ? "已解锁：画面对比度正常" : "未解锁：按存档置灰");
        } else {
            text.draw(kDetailX + 20, 108, 20, palette.warn, "没有可显示的条目");
        }

        text.draw(40, 664, 18, palette.muted,
                  "↑↓ 选择 · PgUp/PgDn 翻页（每页 12 行） · ←→ 切换分类 · Esc 退出");
        if (!data.source.empty())
            text.draw(40, 690, 15, palette.dim, "数据：" + pathUtf8(data.source));
        if (!data.note.empty()) text.draw(40, 706, 14, palette.dim, "备注：" + data.note);

        result.kind = currentKind;
        result.page = shown.page;
        result.pages = shown.pages;
        result.total = shown.total;
        result.index = shown.index;
        result.selectedId = current == nullptr ? std::string() : current->id;
        result.json = almanacJson(currentKind, shown.index, shown.total);

        if (!options.snapshot.empty()) saveScreenSnapshot(renderer, options.snapshot);
        sdl::require(SDL_RenderPresent(renderer), "present almanac");
        ++frame;
        if (headless && frame >= options.frames) break;
        if (!headless) SDL_Delay(16);
    }
    return result;
}

Json renderAlmanacHeadless(const std::filesystem::path& contentRoot, const std::string& kind,
                           int index, int frames, const std::filesystem::path& snapshot,
                           const std::filesystem::path& progressFile,
                           const std::filesystem::path& assetRoot) {
    AlmanacData data = loadAlmanac(contentRoot);
    Progress save;
    if (!progressFile.empty()) save = loadProgress(progressFile);
    data = almanacWithProgress(std::move(data), progressFile.empty() ? nullptr : &save);

    AlmanacOptions options;
    options.contentRoot = contentRoot;
    options.assetRoot = assetRoot.empty() ? defaultAssetRoot(contentRoot) : assetRoot;
    options.progressFile = progressFile;
    options.snapshot = snapshot;
    options.frames = frames;
    const AlmanacResult result = runAlmanac(data, kind, index, options);
    return result.json;
}

}  // namespace pvz
