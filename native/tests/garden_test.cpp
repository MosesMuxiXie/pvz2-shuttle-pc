// Tests for the garden screen.
//
// The garden block is where the OBB is thinnest: 65 collectables, 2 of them attached to a store row,
// 6 with any drop-source reference at all. The test therefore spends its assertions on exactly
// that thinness — a screen that quietly invented prices or level numbers would pass a "does it
// draw" test and still be wrong, so the counts here are the table's own counts and the missing
// pieces are asserted to be *missing*.
//
// Like the almanac test, nothing goes through `main.cpp`: `renderGardenHeadless()` is the entry
// point the `--garden` flag will call once the captain wires it.

#include "almanac_view.hpp"  // metagameTablePath(), the same table both screens read
#include "garden_view.hpp"

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
    if (!condition) throw std::runtime_error("garden render test failed: " + message);
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

const pvz::GardenItem* findByType(const std::vector<pvz::GardenItem>& drops,
                                 const std::string& typeName) {
    for (const pvz::GardenItem& item : drops)
        if (item.typeName == typeName) return &item;
    return nullptr;
}

const pvz::ZenValue* findValue(const std::vector<pvz::ZenValue>& values, const std::string& name) {
    for (const pvz::ZenValue& value : values)
        if (value.name == name) return &value;
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
        const auto root = fs::path(argv[3]) / fs::path("花园 渲染") /
                          std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
        fs::create_directories(root);

        // ---- 1. the block the screen reads ---------------------------------------------------
        const pvz::GardenData data = pvz::loadGarden(content);
        check(data.drops.size() == 65, "the garden has 65 collectables, screen loaded " +
                                           std::to_string(data.drops.size()));
        check(data.zen.tables.size() == 4, "four Zen property sheets, screen found " +
                                               std::to_string(data.zen.tables.size()));
        check(data.zen.pots.size() == 12, "the Zen garden has 12 pots, screen found " +
                                              std::to_string(data.zen.pots.size()));
        check(data.zen.plantRewards == 3, "three Zen plant-reward tables, screen found " +
                                              std::to_string(data.zen.plantRewards));

        const std::vector<std::string> expectedSheets{"props", "slotProps", "bee", "floatingText"};
        check(data.zen.tables == expectedSheets, "the four sheets are props/slotProps/bee/floatingText");
        check(std::is_sorted(data.drops.begin(), data.drops.end(),
                             [](const pvz::GardenItem& a, const pvz::GardenItem& b) {
                                 return a.typeName < b.typeName;
                             }),
              "the drop list must be sorted by type name so a regenerated table cannot reshuffle it");

        // ---- 2. the Zen numbers are the sheet's, spelled as the sheet spells them -------------
        const pvz::ZenValue* grow = findValue(data.zen.values, "PlantGrowDurationInSeconds");
        check(grow != nullptr && grow->text == "18000",
              "the grow duration is 18000 seconds, screen shows " +
                  (grow == nullptr ? std::string("nothing") : grow->text));
        const pvz::ZenValue* coin = findValue(data.zen.values, "NormalPlantCoinRewardAmount");
        check(coin != nullptr && coin->text == "50",
              "a normal plant pays 50 coins, screen shows " +
                  (coin == nullptr ? std::string("nothing") : coin->text));
        const pvz::ZenValue* spawn = findValue(data.zen.values, "TreasurePlantSpawnRate");
        check(spawn != nullptr && spawn->text == "3", "the treasure spawn rate is 3");
        bool potCost = false;
        for (const pvz::ZenValue& value : data.zen.values)
            if (value.name.rfind("PotCosts.", 0) == 0 && value.text == "20") potCost = true;
        check(potCost, "a pot costs 20 gems in the sheet, and the panel must be able to list it");

        // ---- 3. prices: two matched, one priced, sixty-three impossible ----------------------
        int matched = 0;
        int priced = 0;
        for (const pvz::GardenItem& item : data.drops) {
            if (item.sale.matched) ++matched;
            if (item.sale.priced) ++priced;
        }
        check(matched == 2, "two collectables match a store row, got " + std::to_string(matched));
        check(priced == 1, "one of the two has a price, got " + std::to_string(priced) + " priced");

        const pvz::GardenItem* sprout = findByType(data.drops, "sprout");
        check(sprout != nullptr && sprout->sale.matched && sprout->sale.priced,
              "sprout matches its own SKU by item name and carries a price");
        check(sprout->sale.matchKind == "item", "sprout matches by item, got " +
                                                    sprout->sale.matchKind);
        check(sprout->sale.priceKind == "gems", "sprout is priced in gems, got " +
                                                    sprout->sale.priceKind);
        check(std::stoi(sprout->sale.amount) > 0,
              "sprout's price is a positive number, got " + sprout->sale.amount);

        const pvz::GardenItem* pinata = findByType(data.drops, "pinata_egypt");
        check(pinata != nullptr && pinata->sale.matched,
              "pinata_egypt matches a store row by SKU tokens");
        check(pinata->sale.matchKind == "sku", "pinata_egypt matches by sku, got " +
                                                   pinata->sale.matchKind);
        check(!pinata->sale.priced,
              "pinata_egypt's store row has no price fields, so the screen must not invent one");

        const pvz::GardenItem* bare = findByType(data.drops, "pinata");
        check(bare != nullptr, "the bare pinata collectable must be in the table");
        check(!bare->sale.matched, "the category name pinata is not a product");
        check(bare->storeCategory == "pinata",
              "pinata is recorded as a store category instead, got " + bare->storeCategory);

        // ---- 4. drop sources: six rows, referencing tables rather than levels -----------------
        int withSources = 0;
        for (const pvz::GardenItem& item : data.drops)
            if (!item.sources.empty()) ++withSources;
        check(withSources == 6, "six collectables carry a drop-source reference, got " +
                                    std::to_string(withSources));

        const pvz::GardenItem* beach = findByType(data.drops, "pinata_beach");
        check(beach != nullptr && !beach->sources.empty(), "pinata_beach has a drop source");
        check(beach->sources.front().table == "QuestRewardTablesProps",
              "its source is the quest reward table, got " + beach->sources.front().table);
        check(!beach->sources.front().examples.empty(), "the source names its bucket");
        check(beach->sources.front().examples.front().find("difficulty=") == 0,
              "the bucket is a difficulty, not a level id: " +
                  beach->sources.front().examples.front());

        // ---- 5. the JSON the flag prints ------------------------------------------------------
        const fs::path gardenPng = root / "garden.png";
        const pvz::Json json = pvz::renderGardenHeadless(content, 2, gardenPng, assets);
        check(json.size() == 4, "the JSON carries exactly the four wire keys");
        check(json.at("screen").get<std::string>() == "garden", "screen must be garden");
        check(json.at("drops").get<int>() == 65, "drops must be 65");
        check(json.at("zen").get<int>() == 4, "zen must be 4");
        check(json.at("pots").get<int>() == 12, "pots must be 12");
        check(fs::file_size(gardenPng) > 10 * 1024,
              "the frame must be a real picture, got " + std::to_string(fs::file_size(gardenPng)) +
                  " bytes");

        // ---- 6. paging, and a real frame -----------------------------------------------------
        const pvz::GardenPage first = pvz::gardenPage(data.drops, 0);
        check(first.total == 65 && first.pages == 6 && first.visible.size() == 12,
              "12 rows per page puts 65 drops on 6 pages, got " + std::to_string(first.pages));
        const pvz::GardenPage last = pvz::gardenPage(data.drops, 64);
        check(last.page == 5 && last.first == 60 && last.last == 65 && last.visible.size() == 5,
              "the last page holds the remaining 5 rows, got " +
                  std::to_string(last.visible.size()));

        pvz::GardenOptions options;
        options.contentRoot = content;
        options.assetRoot = assets;
        options.frames = 2;
        options.snapshot = root / "garden-frame.png";
        const pvz::GardenResult result = pvz::runGarden(data, 0, options);
        check(result.drops == 65 && result.zen == 4 && result.zenPots == 12,
              "the drawn screen reports the block's own counts");
        check(result.selectedTypeName == data.drops.front().typeName,
              "the cursor starts on the first row, got " + result.selectedTypeName);

        int width = 0;
        int height = 0;
        const std::size_t ink = inkPixels(root / "garden-frame.png", result.selectedRect, 6, 40,
                                          &width, &height);
        check(width == 1280 && height == 720,
              "snapshot is " + std::to_string(width) + "x" + std::to_string(height));
        check(ink >= 120, "the selected row must carry glyphs, only " + std::to_string(ink) +
                              " ink pixels inside its rectangle");

        pvz::GardenOptions again = options;
        again.snapshot = root / "garden-frame-again.png";
        const pvz::GardenResult secondRun = pvz::runGarden(data, 0, again);
        check(secondRun.selectedTypeName == result.selectedTypeName,
              "two runs must agree about the cursor");
        check(readBytes(root / "garden-frame.png") == readBytes(root / "garden-frame-again.png"),
              "two runs must produce byte-identical frames");

        // ---- 7. a missing font is an error, not a blank window -------------------------------
        bool rejected = false;
        try {
            pvz::GardenOptions broken = options;
            broken.assetRoot = assets / "missing";
            (void)pvz::runGarden(data, 0, broken);
        } catch (const std::exception& error) {
            rejected = std::string(error.what()).find("font_zh.ttc") != std::string::npos;
        }
        check(rejected, "a missing font must fail with the font path in the message");

        // ---- 8. a missing table is an error, not an empty garden -----------------------------
        bool tableRejected = false;
        try {
            (void)pvz::loadGarden(root / "no-content-here");
        } catch (const std::exception& error) {
            tableRejected = std::string(error.what()).find("metagame.json") != std::string::npos;
        }
        check(tableRejected, "a missing metagame.json must name the file it wanted");

        // ---- 9. B6b: the reward-dialog title is text, not a key -------------------------------
        // Before B6b the detail panel printed `标题键 BEACH_DANGER_ROOM_NAME` and the sentence
        // "原版无文案（只有键）" for every collectable, because nothing ever filled `item.title`.
        int titled = 0;
        int keyed = 0;
        for (const pvz::GardenItem& item : data.drops) {
            if (item.titleKey.empty()) {
                ++keyed;
                check(item.title.empty(),
                      "a collectable with no title key must not invent a title: " + item.typeName);
                continue;
            }
            if (!item.title.empty()) ++titled;
            check(item.title != item.titleKey,
                  "a resolved title must never be the key: " + item.typeName);
        }
        check(keyed == 11, "eleven collectables carry no title key, got " + std::to_string(keyed));
        check(titled >= 40, "LawnStrings must title the rest, resolved " + std::to_string(titled) +
                                " of 54");

        const pvz::GardenItem* beachRoom = findByType(data.drops, "dangerroom_beach");
        check(beachRoom != nullptr, "dangerroom_beach must be in the table");
        check(beachRoom->title == "提基文明传承者",
              "the panel must print the table's title, printed " + beachRoom->title);
        check(beachRoom->titleKey == "BEACH_DANGER_ROOM_NAME",
              "the key is still carried for the `标题键` line, got " + beachRoom->titleKey);
        const pvz::GardenItem* bacon = findByType(data.drops, "collectable_bacon");
        check(bacon != nullptr && bacon->titleKey.empty() && bacon->title.empty(),
              "collectable_bacon has no key and therefore no title");

        // ---- 10. no LawnStrings: the screen still draws, with keys only -----------------------
        const fs::path noLoc = root / "no-loc";
        fs::create_directories(noLoc / "native" / "generated");
        fs::create_directories(noLoc / "content");
        fs::copy_file(pvz::metagameTablePath(content),
                      noLoc / "native" / "generated" / "metagame.json",
                      fs::copy_options::overwrite_existing);
        const pvz::GardenData bareData = pvz::loadGarden(noLoc / "content");
        check(bareData.drops.size() == 65, "the garden block loads without a string table");
        const pvz::GardenItem* bareRoom = findByType(bareData.drops, "dangerroom_beach");
        check(bareRoom != nullptr && bareRoom->title.empty(),
              "with no table the title stays empty and the panel falls back to the key line");
        check(bareRoom != nullptr && !bareRoom->titleKey.empty(),
              "and the key is still there to print");

        pvz::GardenOptions bareOptions = options;
        bareOptions.contentRoot = noLoc / "content";
        bareOptions.snapshot = root / "garden-noloc.png";
        const pvz::GardenResult bareResult = pvz::runGarden(bareData, 0, bareOptions);
        check(bareResult.drops == 65, "the fallback screen still reports 65 drops");
        check(fs::file_size(root / "garden-noloc.png") > 10 * 1024,
              "a missing LawnStrings must still produce a frame, got " +
                  std::to_string(fs::file_size(root / "garden-noloc.png")) + " bytes");

        std::cout << "garden render tests passed (drops=65, zen=4, pots=12, priced=" << priced
                  << ", sources=" << withSources << ", titled=" << titled << ", ink=" << ink
                  << ")\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
