// Tests for the almanac screen.
//
// The screen is a thin, honest view over `native/generated/metagame.json`, so the test aims at the
// three places where "thin" could turn into "wrong": the counts must be the table's own counts, the
// printable name must come from `content/` rather than from a localization key being passed off as
// prose, and the grey-out must follow the save. On top of that the frame itself: 1280x720,
// byte-identical reruns, glyphs inside the selected row, and a loud failure when the font is gone.
//
// Nothing here goes through `main.cpp`: the entry point under test is `renderAlmanacHeadless()`,
// the same one the `--almanac` flag will call once the captain wires it, which is why the JSON
// assertions below are also the CLI's contract.

#include "almanac_view.hpp"
#include "progress.hpp"

#include <SDL3/SDL.h>
#include <SDL3_image/SDL_image.h>
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error("almanac render test failed: " + message);
}

std::vector<std::uint8_t> readBytes(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    if (!in) throw std::runtime_error("cannot read " + pvz::pathUtf8(file));
    return std::vector<std::uint8_t>(std::istreambuf_iterator<char>(in),
                                     std::istreambuf_iterator<char>());
}

std::size_t inkPixels(const fs::path& file, const pvz::ScreenRect& rect, int inset, int threshold,
                      int* width, int* height) {
    SDL_Surface* frame = IMG_Load(pvz::pathUtf8(file).c_str());
    if (frame == nullptr) throw std::runtime_error(std::string("load snapshot: ") + SDL_GetError());
    *width = frame->w;
    *height = frame->h;
    const int x0 = static_cast<int>(rect.x) + inset;
    const int y0 = static_cast<int>(rect.y) + inset;
    const int x1 = static_cast<int>(rect.x + rect.w) - inset;
    const int y1 = static_cast<int>(rect.y + rect.h) - inset;
    check(x1 > x0 && y1 > y0, "the selected row must be sampleable");

    Uint8 br = 0, bg = 0, bb = 0, ba = 0;
    if (!SDL_ReadSurfacePixel(frame, x0, y0, &br, &bg, &bb, &ba)) {
        SDL_DestroySurface(frame);
        throw std::runtime_error(std::string("sample background: ") + SDL_GetError());
    }
    std::size_t ink = 0;
    for (int y = y0; y < y1; ++y) {
        for (int x = x0; x < x1; ++x) {
            Uint8 r = 0, g = 0, b = 0, a = 0;
            if (!SDL_ReadSurfacePixel(frame, x, y, &r, &g, &b, &a)) continue;
            const int dr = std::abs(static_cast<int>(r) - static_cast<int>(br));
            const int dg = std::abs(static_cast<int>(g) - static_cast<int>(bg));
            const int db = std::abs(static_cast<int>(b) - static_cast<int>(bb));
            if (dr > threshold || dg > threshold || db > threshold) ++ink;
        }
    }
    SDL_DestroySurface(frame);
    return ink;
}

const pvz::AlmanacEntry* findEntry(const std::vector<pvz::AlmanacEntry>& entries,
                                   const std::string& id) {
    for (const pvz::AlmanacEntry& entry : entries)
        if (entry.id == id) return &entry;
    return nullptr;
}

const pvz::AlmanacEntry* findWorld(const std::vector<pvz::AlmanacEntry>& entries,
                                   const std::string& world) {
    for (const pvz::AlmanacEntry& entry : entries)
        if (entry.world == world) return &entry;
    return nullptr;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 4) {
            throw std::runtime_error("expected content directory, assets directory and temp root");
        }
        const fs::path content = argv[1];
        const fs::path assets = argv[2];
        const auto root = fs::path(argv[3]) / fs::path("图鉴 渲染") /
                          std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
        fs::create_directories(root);

        // ---- 1. the table the screen reads ---------------------------------------------------
        const fs::path tablePath = pvz::metagameTablePath(content);
        check(fs::is_regular_file(tablePath),
              "metagame.json must resolve next to the content tree, looked at " +
                  pvz::pathUtf8(tablePath));
        const pvz::AlmanacData table = pvz::loadAlmanac(content);
        check(table.plants.size() == 167,
              "the almanac has 167 plant rows, screen loaded " + std::to_string(table.plants.size()));
        check(table.zombies.size() == 428,
              "the almanac has 428 zombie rows, screen loaded " +
                  std::to_string(table.zombies.size()));

        int plantNameKeys = 0;
        for (const pvz::AlmanacEntry& entry : table.plants)
            if (!entry.nameKey.empty()) ++plantNameKeys;
        check(plantNameKeys == 167,
              "every plant row carries a name key (167), got " + std::to_string(plantNameKeys));

        check(std::is_sorted(table.plants.begin(), table.plants.end(),
                             [](const pvz::AlmanacEntry& a, const pvz::AlmanacEntry& b) {
                                 return a.id < b.id;
                             }),
              "the plant list must be sorted by id so a regenerated table cannot reshuffle it");
        check(std::is_sorted(table.zombies.begin(), table.zombies.end(),
                             [](const pvz::AlmanacEntry& a, const pvz::AlmanacEntry& b) {
                                 return a.id < b.id;
                             }),
              "the zombie list must be sorted by id");

        // ---- 2. one page is twelve rows ------------------------------------------------------
        const pvz::AlmanacPage first = pvz::almanacPage(table.plants, 0);
        check(first.total == 167 && first.pages == 14 && first.page == 0,
              "12 rows per page puts 167 entries on 14 pages, got " + std::to_string(first.pages));
        check(first.visible.size() == 12 && first.first == 0 && first.last == 12,
              "the first page holds rows 1-12");
        const pvz::AlmanacPage second = pvz::almanacPage(table.plants, 12);
        check(second.page == 1 && second.first == 12 && second.visible.front() == 12,
              "entry 13 opens page 2 at row 13");
        const pvz::AlmanacPage last = pvz::almanacPage(table.plants, 166);
        check(last.page == 13 && last.first == 156 && last.last == 167 && last.visible.size() == 11,
              "the last page holds the remaining 11 rows, got " +
                  std::to_string(last.visible.size()));
        const pvz::AlmanacPage clamped = pvz::almanacPage(table.plants, 99999);
        check(clamped.index == 166 && clamped.page == 13,
              "an out-of-range index clamps to the last entry, got " +
                  std::to_string(clamped.index));

        // ---- 3. text comes from content, never from a key ------------------------------------
        // `content/` is a moving target — other tasks keep extending it — so the assertions here are
        // invariants rather than a fixed intersection count: a row content covers renders its prose,
        // a row it does not cover renders its id, and no row ever prints a localization key.
        int named = 0;
        int fromTable = 0;
        int fallback = 0;
        int described = 0;
        for (const pvz::AlmanacEntry& entry : table.plants) {
            if (entry.nameFromContent) {
                ++named;
                check(entry.name != entry.id,
                      "a plant content covers must print its own name: " + entry.id);
            } else if (entry.name == entry.id) {
                // Third link of the chain: no content row *and* no LawnStrings row (minishroom).
                ++fallback;
            } else {
                ++fromTable;
            }
            check(!entry.name.empty(), "every plant row prints something: " + entry.id);
            check(entry.name != entry.nameKey,
                  "a printable name must never be the localization key: " + entry.id);
            if (!entry.description.empty()) ++described;
        }
        check(named >= 20, "content/plants.json must cover a useful part of the table, covered " +
                               std::to_string(named) + " of 167");
        // B6b: the rows content does not carry are named by LawnStrings instead of by their id.
        check(fromTable >= 15, "LawnStrings must name the plants content does not, resolved " +
                                   std::to_string(fromTable) + " of 167");
        check(fallback >= 1,
              "at least one plant has neither a content row nor a table row and prints its id");
        check(described >= 20, "the almanac prose covers the rows content ships, got " +
                                   std::to_string(described) + " described plants");
        int zombiesNamed = 0;
        for (const pvz::AlmanacEntry& entry : table.zombies)
            if (entry.nameFromContent) ++zombiesNamed;
        check(zombiesNamed >= 10, "content/zombies.json must cover a useful part of the table, "
                                  "covered " + std::to_string(zombiesNamed) + " of 428");

        // minishroom is the one row whose LawnStrings entry is missing, and the screen still has to
        // be able to show it: the key is there, so the row prints its id and the panel prints the key.
        const pvz::AlmanacEntry* keyOnly = findEntry(table.plants, "minishroom");
        check(keyOnly != nullptr, "minishroom must be in the table");
        check(!keyOnly->nameKey.empty(), "minishroom still carries a name key");
        check(keyOnly->name != keyOnly->nameKey,
              "minishroom must not print its key as a name, printed " + keyOnly->name);

        // ---- 4. the grey-out follows the save ------------------------------------------------
        const pvz::AlmanacData open = pvz::almanacWithProgress(table, nullptr);
        for (const pvz::AlmanacEntry& entry : open.plants)
            check(entry.seen, "without a save every entry is visible: " + entry.id);

        pvz::Progress save;
        pvz::LevelRecord beach;
        beach.cleared = true;
        beach.stars = 2;
        beach.attempts = 1;
        beach.bestTick = 900;
        save.levels["beach_1"] = beach;
        const std::vector<std::string> cleared = pvz::almanacClearedWorlds(save);
        check(cleared.size() == 1 && cleared.front() == "beach",
              "the save cleared one beach level, the screen derived " +
                  std::to_string(cleared.size()) + " worlds");
        const pvz::AlmanacData gated = pvz::almanacWithProgress(table, &save);
        const pvz::AlmanacEntry* beachZombie = findWorld(gated.zombies, "beach");
        check(beachZombie != nullptr && beachZombie->seen,
              "a beach zombie is revealed once a beach level is cleared");
        const pvz::AlmanacEntry* skyZombie = findWorld(gated.zombies, "skycity");
        check(skyZombie != nullptr && !skyZombie->seen,
              "a skycity zombie stays grey while only beach is cleared");
        const pvz::AlmanacEntry* noWorld = findEntry(gated.plants, "akee");
        check(noWorld != nullptr && noWorld->world.empty(),
              "akee must be one of the 51 plants with no HomeWorld token");
        check(noWorld->seen, "an entry with no world token is never greyed out");

        // ---- 5. the JSON the flag prints ------------------------------------------------------
        const fs::path plantPng = root / "almanac-plant.png";
        const pvz::Json plantJson =
            pvz::renderAlmanacHeadless(content, "plant", 0, 2, plantPng, {}, assets);
        check(plantJson.size() == 4, "the JSON carries exactly the four wire keys");
        check(plantJson.at("screen").get<std::string>() == "almanac", "screen must be almanac");
        check(plantJson.at("kind").get<std::string>() == "plant", "kind must be plant");
        check(plantJson.at("index").get<int>() == 0, "the first entry is index 0");
        check(plantJson.at("total").get<int>() == 167, "the plant total is 167");
        check(fs::file_size(plantPng) > 10 * 1024,
              "the frame must be a real picture, got " + std::to_string(fs::file_size(plantPng)) +
                  " bytes");

        const pvz::Json zombieJson =
            pvz::renderAlmanacHeadless(content, "zombie", 12, 2, root / "almanac-zombie.png", {},
                                       assets);
        check(zombieJson.at("kind").get<std::string>() == "zombie", "kind must be zombie");
        check(zombieJson.at("index").get<int>() == 12, "index 12 must survive the round trip");
        check(zombieJson.at("total").get<int>() == 428, "the zombie total is 428");

        const pvz::Json clampedJson =
            pvz::renderAlmanacHeadless(content, "plant", 99999, 1, root / "almanac-clamped.png", {},
                                       assets);
        check(clampedJson.at("index").get<int>() == 166,
              "an index past the end clamps before it reaches the JSON");

        // ---- 6. a real frame, and two runs that agree ----------------------------------------
        pvz::AlmanacOptions options;
        options.contentRoot = content;
        options.assetRoot = assets;
        options.frames = 2;
        options.snapshot = root / "almanac-frame.png";
        const pvz::AlmanacResult result = pvz::runAlmanac(table, "plant", 0, options);
        check(result.total == 167 && result.pages == 14, "the drawn screen reports the table size");
        check(result.selectedId == table.plants.front().id,
              "the cursor starts on the first row, got " + result.selectedId);

        int width = 0;
        int height = 0;
        const std::size_t ink = inkPixels(root / "almanac-frame.png", result.selectedRect, 6, 40,
                                          &width, &height);
        check(width == 1280 && height == 720,
              "snapshot is " + std::to_string(width) + "x" + std::to_string(height));
        check(ink >= 120, "the selected row must carry glyphs, only " + std::to_string(ink) +
                              " ink pixels inside its rectangle");

        pvz::AlmanacOptions again = options;
        again.snapshot = root / "almanac-frame-again.png";
        const pvz::AlmanacResult secondRun = pvz::runAlmanac(table, "plant", 0, again);
        check(secondRun.selectedId == result.selectedId && secondRun.index == result.index,
              "two runs must agree about the cursor");
        check(readBytes(root / "almanac-frame.png") == readBytes(root / "almanac-frame-again.png"),
              "two runs must produce byte-identical frames");

        // ---- 7. a missing font is an error, not a blank window -------------------------------
        bool rejected = false;
        try {
            pvz::AlmanacOptions broken = options;
            broken.assetRoot = assets / "missing";
            (void)pvz::runAlmanac(table, "plant", 0, broken);
        } catch (const std::exception& error) {
            rejected = std::string(error.what()).find("font_zh.ttc") != std::string::npos;
        }
        check(rejected, "a missing font must fail with the font path in the message");

        // ---- 8. a missing table is an error, not an empty almanac ----------------------------
        bool tableRejected = false;
        try {
            (void)pvz::loadAlmanac(root / "no-content-here");
        } catch (const std::exception& error) {
            tableRejected =
                std::string(error.what()).find("metagame.json") != std::string::npos;
        }
        check(tableRejected, "a missing metagame.json must name the file it wanted");

        // ---- 9. B6b: the panel spells the table out instead of the key -------------------------
        // These are the rows the screen used to render as `BLAZELEAF` / `ZOMBIE_ATLANTIS` /
        // `STAT_FAMILY_ROSEMARY`: outside `content/`, named only by LawnStrings.
        const pvz::AlmanacEntry* blazeleaf = findEntry(table.plants, "blazeleaf");
        check(blazeleaf != nullptr, "blazeleaf must be in the plant table");
        check(!blazeleaf->nameFromContent, "blazeleaf is one of the 20 plants content does not cover");
        check(blazeleaf->name == "炽叶",
              "the almanac must print the LawnStrings name, printed " + blazeleaf->name);
        check(blazeleaf->name != blazeleaf->nameKey, "and never the key " + blazeleaf->nameKey);
        check(blazeleaf->description.rfind("{FLAVOR}", 0) == 0,
              "blazeleaf must carry its table description, got " +
                  blazeleaf->description.substr(0, 24));

        const pvz::AlmanacEntry* atlantis = findEntry(table.zombies, "atlantis");
        check(atlantis != nullptr, "atlantis must be in the zombie table");
        check(atlantis->name == "海洋普通僵尸",
              "the zombie detail panel must print its table name, printed " + atlantis->name);

        const pvz::AlmanacEntry* familyRow = findEntry(table.plants, "akee");
        check(familyRow != nullptr, "akee must be in the plant table");
        bool familyResolved = false;
        for (const pvz::AlmanacStat& stat : familyRow->stats) {
            if (stat.type != "family") continue;
            // The screen draws `stat.type + " · " + resolveKey(valueKey)`; the model hands over the
            // key and the view resolves it, so the key itself is what this row has to still carry.
            check(!stat.valueKey.empty(), "the family row keeps its value key for the view");
            familyResolved = !stat.valueKey.empty();
        }
        check(familyResolved, "akee must carry a family stat row");

        // ---- 10. no LawnStrings at all: the screen still draws, from content and ids only ------
        // A checkout whose content tools have not run has no `lawn_strings.json`; the screen must
        // fall back to the id (exactly what it did before B6b) rather than refusing to open.
        const fs::path noLoc = root / "no-loc";
        fs::create_directories(noLoc / "native" / "generated");
        fs::create_directories(noLoc / "content");
        fs::copy_file(tablePath, noLoc / "native" / "generated" / "metagame.json",
                      fs::copy_options::overwrite_existing);
        const pvz::AlmanacData bare = pvz::loadAlmanac(noLoc / "content");
        check(bare.plants.size() == 167, "the table still loads without a string table");
        const pvz::AlmanacEntry* bareLeaf = findEntry(bare.plants, "blazeleaf");
        check(bareLeaf != nullptr, "blazeleaf must survive the fallback");
        check(bareLeaf->name == bareLeaf->id,
              "with no table and no content row the screen prints the id, printed " +
                  bareLeaf->name);
        check(bareLeaf->description.empty(),
              "with no table and no content row the panel has no prose to print");

        pvz::AlmanacOptions bareOptions = options;
        bareOptions.contentRoot = noLoc / "content";
        bareOptions.snapshot = root / "almanac-noloc.png";
        const pvz::AlmanacResult bareResult = pvz::runAlmanac(bare, "plant", 0, bareOptions);
        check(bareResult.total == 167, "the fallback screen still reports 167 rows");
        check(fs::file_size(root / "almanac-noloc.png") > 10 * 1024,
              "a missing LawnStrings must still produce a frame, got " +
                  std::to_string(fs::file_size(root / "almanac-noloc.png")) + " bytes");

        std::cout << "almanac render tests passed (plants=167, zombies=428, named=" << named
                  << ", fromTable=" << fromTable << ", described=" << described
                  << ", ink=" << ink << ")\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
