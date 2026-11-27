// Achievements screen (B4). What this test exists to prevent:
//   1. the screen inventing progress the save cannot prove (the sheet has no thresholds, so only
//      `*_STARS` can be totalled - `native/generated/metagame.json` `unknowns[U4]` says the
//      rewards are server-side and were deliberately not invented);
//   2. a page range that silently drops or repeats rows (53 rows / 12 per page = 5 pages, the
//      last one is 5 rows);
//   3. a `serverOnly` badge that is not actually true for every row, which would suggest the
//      client could award them;
//   4. a headless JSON whose keys drift away from what the captain wires into `--achievements`.
//
// The desktop section (built only under PVZ_ENABLE_DESKTOP) draws the real screen and checks the
// picture: 1280x720, more than 10 KB, text ink inside the row band, a different page producing
// different pixels, and a missing font failing loudly.

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include "achievements_view.hpp"
#include "catalog.hpp"  // pathUtf8
#include "progress.hpp"

#ifdef PVZ_ENABLE_DESKTOP
#include <SDL3/SDL.h>
#include <SDL3_image/SDL_image.h>

#include "sdl_support.hpp"
#endif

namespace fs = std::filesystem;
using namespace pvz;
using namespace pvz::meta;

namespace {

void check(bool ok, const std::string& message) {
    if (!ok) throw std::runtime_error("achievements test failed: " + message);
}

fs::path gTemp;

AchievementsModel shipped() {
    AchievementsModel model = AchievementsModel::loadShipped();
    check(model.rows.size() == 53, "the sheet must carry 53 achievements, got " +
                                       std::to_string(model.rows.size()));
    return model;
}

/// A save with two worlds partly cleared: 10 egypt levels on 2 stars, 40 frontyard on 1 star.
Progress sampleSave() {
    Progress progress;
    progress.coins = 1234;
    progress.keys = 2;
    for (int i = 1; i <= 10; ++i) {
        LevelRecord record;
        record.cleared = true;
        record.stars = 2;
        record.attempts = 1;
        record.bestTick = 1200;
        progress.levels["egypt_" + std::to_string(i)] = record;
    }
    for (int i = 1; i <= 40; ++i) {
        LevelRecord record;
        record.cleared = true;
        record.stars = 1;
        record.attempts = 1;
        record.bestTick = 900;
        progress.levels["frontyard_" + std::to_string(i)] = record;
    }
    return progress;
}

int rowsWithStars(const AchievementsModel& model) {
    int count = 0;
    for (const AchievementRow& row : model.rows) {
        if (row.progress.find("星") != std::string::npos) ++count;
    }
    return count;
}

const AchievementRow& pick(const AchievementsModel& model, const std::string& id) {
    for (const AchievementRow& row : model.rows) {
        if (row.id == id) return row;
    }
    throw std::runtime_error("achievements test failed: no row " + id);
}

void testShippedModel() {
    const AchievementsModel model = shipped();
    check(model.serverOnly == 53, "all 53 rows must be serverOnly, got " +
                                      std::to_string(model.serverOnly));
    std::set<std::string> ids;
    std::set<std::string> titles;
    for (const AchievementRow& row : model.rows) {
        check(!row.id.empty(), "every row needs an id");
        check(ids.insert(row.id).second, "duplicate achievement id " + row.id);
        check(row.titleKey.rfind("ACHIEVE_", 0) == 0,
              "title key must be an ACHIEVE_ key, got " + row.titleKey);
        check(row.titleKey.size() > 9 && row.titleKey.substr(row.titleKey.size() - 6) == "_TITLE",
              "title key must end in _TITLE, got " + row.titleKey);
        check(!row.title.empty(), "row " + row.id + " has no title to draw");
        check(row.title != row.titleKey, "a title must never be the key: " + row.id);
        check(row.title.find('_') == std::string::npos,
              "no title may print a raw key fragment: " + row.title);
        check(row.serverOnly, "row " + row.id + " must carry the server badge");
        titles.insert(row.title);
    }
    check(ids.size() == 53, "53 unique ids expected");
    check(!model.source.empty(), "the model must remember where it was read from");
}

void testHumanize() {
    check(humanizeGameKey("ACHIEVE_ALL_IN_JEST_TITLE") == "All In Jest",
          "ACHIEVE_ALL_IN_JEST_TITLE -> All In Jest, got " +
              humanizeGameKey("ACHIEVE_ALL_IN_JEST_TITLE"));
    check(humanizeGameKey("ACHIEVE_EIGHTIES_BACK_FROM_THE_FUTURE_3_TITLE") ==
              "Eighties Back From The Future 3",
          "digits must survive the humaniser, got " +
              humanizeGameKey("ACHIEVE_EIGHTIES_BACK_FROM_THE_FUTURE_3_TITLE"));
    check(humanizeGameKey("all_in_jest") == "All In Jest",
          "the humaniser must not depend on the ACHIEVE_ prefix");
    check(humanizeGameKey("").empty(), "an empty key must stay empty");
}

// B6b: the row title is LawnStrings text. The humaniser is now the *third* link of the chain
// (content -> table -> humanise -> id), not the source of truth.
void testTitleComesFromTheTable() {
    const AchievementsModel model = shipped();
    const AchievementRow& row = pick(model, "ALL_IN_JEST");
    check(row.title == "向我开炮",
          "ALL_IN_JEST must print the table's 向我开炮, got " + row.title);
    check(row.title != humanizeGameKey(row.titleKey),
          "the table must win over the humaniser, both said " + row.title);
    check(row.titleKey == "ACHIEVE_ALL_IN_JEST_TITLE", "the key is still carried for the footer");

    // The shipped table names every row, so nothing should still be humanised.
    int fromTable = 0;
    for (const AchievementRow& each : model.rows) {
        if (!each.title.empty() && each.title != humanizeGameKey(each.titleKey)) ++fromTable;
    }
    check(fromTable >= 50, "the table must name the rows, only " + std::to_string(fromTable) +
                               " of 53 differ from the humanised key");
}

// No `lawn_strings.json`: the model has to look exactly like it did before B6b.
void testMissingTableFallsBackToTheHumaniser() {
    const fs::path tree = gTemp / "achievements-no-loc";
    fs::create_directories(tree / "native" / "generated");
    fs::copy_file(AchievementsModel::loadShipped().source,
                  tree / "native" / "generated" / "metagame.json",
                  fs::copy_options::overwrite_existing);
    const AchievementsModel bare =
        AchievementsModel::load(tree / "native" / "generated" / "metagame.json");
    check(bare.rows.size() == 53, "the rows must still load without a string table");
    for (const AchievementRow& row : bare.rows) {
        check(row.title == humanizeGameKey(row.titleKey),
              "with no table the title is the humanised key, got " + row.title);
    }
    check(pick(bare, "ALL_IN_JEST").title == "All In Jest",
          "and that keeps the pre-B6b rendering, got " + pick(bare, "ALL_IN_JEST").title);
}

void testPageRange() {
    const PageRange first = PageRange::of(53, 0, 12);
    check(first.page == 0 && first.first == 0 && first.count == 12 && first.pages == 5,
          "page 0 of 53 rows must be 12 rows, 5 pages");

    const PageRange last = PageRange::of(53, 4, 12);
    check(last.page == 4 && last.first == 48 && last.count == 5 && last.pages == 5,
          "the last page must be the 5 leftover rows");

    const PageRange past = PageRange::of(53, 5, 12);
    check(past.page == 4, "a page past the end must clamp to the last page, got " +
                              std::to_string(past.page));

    const PageRange negative = PageRange::of(53, -3, 12);
    check(negative.page == 0, "a negative page must clamp to 0");

    const PageRange single = PageRange::of(11, 0, 12);
    check(single.pages == 1 && single.count == 11, "11 rows must be one page of 11");

    const PageRange empty = PageRange::of(0, 0, 12);
    check(empty.pages == 1 && empty.count == 0, "an empty list is still one (empty) page");

    // Every row of the sheet must be reachable exactly once across the five pages.
    int seen = 0;
    for (int page = 0; page < 5; ++page) {
        const PageRange range = PageRange::of(53, page, 12);
        seen += range.count;
        check(range.first + range.count <= 53, "a page must not run past the list");
    }
    check(seen == 53, "the five pages must cover 53 rows exactly once, counted " +
                          std::to_string(seen));
}

void testOnlyStarRowsCarryNumbers() {
    AchievementsModel model = shipped();
    applyProgress(model, sampleSave());
    check(rowsWithStars(model) == 3,
          "only the three *_STARS rows can be derived from a save, counted " +
              std::to_string(rowsWithStars(model)));

    const AchievementRow& egypt = pick(model, "EGYPT_STARS");
    check(egypt.progress.find("20") != std::string::npos,
          "10 egypt levels on 2 stars must read 20, got " + egypt.progress);
    // A world with no progress still gets a number rather than a dash: "0 stars" is an answer the
    // save can prove, and hiding it behind "-" would look like a missing threshold.
    const AchievementRow& cowboy = pick(model, "COWBOY_STARS");
    check(cowboy.progress.find("0 星") != std::string::npos,
          "no cowboy progress must read 0 星, got " + cowboy.progress);

    // The fifty other rows must not pretend: the sheet has no threshold to compare against.
    for (const AchievementRow& row : model.rows) {
        if (row.id == "COWBOY_STARS" || row.id == "EGYPT_STARS" || row.id == "PIRATE_STARS") {
            continue;
        }
        check(row.progress == "-", "row " + row.id + " has no threshold, must show -");
    }

    check(starsInWorld(sampleSave(), "egypt") == 20, "starsInWorld(egypt) must be 20");
    check(clearedInWorld(sampleSave(), "frontyard") == 40, "40 frontyard levels are cleared");
    check(starsInWorld(sampleSave(), "nowhere") == 0, "an unknown world has 0 stars");
}

void testEmptySaveShowsZeros() {
    AchievementsModel model = shipped();
    applyProgress(model, Progress{});
    check(pick(model, "EGYPT_STARS").progress.find("0 星") != std::string::npos,
          "an empty save must read 0 stars, got " + pick(model, "EGYPT_STARS").progress);
    check(rowsWithStars(model) == 3, "still only three rows carry a star total");
}

void testJsonShape() {
    AchievementsModel model = shipped();
    applyProgress(model, sampleSave());

    const Json page0 = achievementsJson(model, PageRange::of(53, 0, 12), 12);
    std::set<std::string> keys;
    for (auto it = page0.begin(); it != page0.end(); ++it) keys.insert(it.key());
    const std::set<std::string> expected{"screen", "total", "serverOnly", "perPage", "pages",
                                         "page", "visible"};
    check(keys == expected, "the headless JSON keys drifted from the agreed set");
    check(page0["screen"] == "achievements", "screen must be `achievements`");
    check(page0["total"] == 53, "total must be 53");
    check(page0["serverOnly"] == 53, "serverOnly must be 53");
    check(page0["perPage"] == 12, "perPage must be 12");
    check(page0["pages"] == 5, "pages must be 5");
    check(page0["page"] == 0, "page must be 0");
    check(page0["visible"].size() == 12, "page 0 must carry 12 rows, got " +
                                             std::to_string(page0["visible"].size()));

    const Json item = page0["visible"][0];
    std::set<std::string> itemKeys;
    for (auto it = item.begin(); it != item.end(); ++it) itemKeys.insert(it.key());
    const std::set<std::string> expectedItem{"id", "title", "progress", "server"};
    check(itemKeys == expectedItem, "the per-row JSON keys drifted");
    check(item["server"] == true, "every row must be advertised as server-side");

    const Json last = achievementsJson(model, PageRange::of(53, 4, 12), 12);
    check(last["visible"].size() == 5, "the last page must carry 5 rows");
    check(last["page"] == 4, "the last page must report page 4");
}

#ifdef PVZ_ENABLE_DESKTOP
/// FNV-1a over a few thousand sampled pixels: enough to tell two different draws apart without
/// depending on a codec.
std::uint64_t pixelHash(SDL_Surface* surface) {
    std::uint64_t hash = 1469598103934665603ull;
    const auto* pixels = static_cast<const std::uint8_t*>(surface->pixels);
    const int pitch = surface->pitch;
    for (int y = 0; y < surface->h; y += 3) {
        const auto* row = pixels + static_cast<std::ptrdiff_t>(y) * pitch;
        for (int x = 0; x < surface->w; x += 3) {
            const auto* p = row + static_cast<std::ptrdiff_t>(x) * 4;
            for (int c = 0; c < 3; ++c) {
                hash ^= p[c];
                hash *= 1099511628211ull;
            }
        }
    }
    return hash;
}

void testRenderWritesPng(const fs::path& assets) {
    AchievementsModel model = shipped();
    applyProgress(model, sampleSave());

    AchievementsOptions options;
    options.assetRoot = assets;
    options.frames = 2;
    options.snapshot = gTemp / "achievements.png";
    options.perPage = AchievementsLayout::kPerPage;
    options.page = 0;

    const Json result = renderAchievementsHeadless(model, options);
    check(result["screen"] == "achievements", "the render must return the same JSON");
    check(result["total"] == 53, "the render must return total=53");
    check(result["serverOnly"] == 53, "the render must return serverOnly=53");
    check(fs::is_regular_file(options.snapshot), "the snapshot must be written");
    check(fs::file_size(options.snapshot) > 10 * 1024,
          "a screen with 12 rows of text must exceed 10 KB, got " +
              std::to_string(fs::file_size(options.snapshot)));

    sdl::Surface image(IMG_Load(pathUtf8(options.snapshot).c_str()), SDL_DestroySurface);
    check(bool(image), "the snapshot must decode");
    check(image->w == 1280 && image->h == 720,
          "the screen must be 1280x720, got " + std::to_string(image->w) + "x" +
              std::to_string(image->h));

    const auto* pixels = static_cast<const std::uint8_t*>(image->pixels);
    const int pitch = image->pitch;
    int ink = 0;
    for (int y = static_cast<int>(AchievementsLayout::kRowTop);
         y < static_cast<int>(AchievementsLayout::kRowTop + 12 * AchievementsLayout::kRowHeight);
         y += 2) {
        const auto* row = pixels + static_cast<std::ptrdiff_t>(y) * pitch;
        for (int x = static_cast<int>(AchievementsLayout::kRowLeft);
             x < static_cast<int>(AchievementsLayout::kRowLeft + AchievementsLayout::kRowWidth);
             x += 2) {
            const auto* p = row + static_cast<std::ptrdiff_t>(x) * 4;
            if (p[0] > 150 && p[1] > 150 && p[2] > 140) ++ink;
        }
    }
    check(ink > 500, "the row band must contain drawn text, ink pixels=" + std::to_string(ink));

    const std::uint64_t hashPage0 = pixelHash(image.get());

    AchievementsOptions second = options;
    second.snapshot = gTemp / "achievements-page4.png";
    second.page = 4;
    renderAchievementsHeadless(model, second);
    sdl::Surface page4(IMG_Load(pathUtf8(second.snapshot).c_str()), SDL_DestroySurface);
    check(bool(page4), "the page-4 snapshot must decode");
    check(page4->w == 1280 && page4->h == 720, "page 4 must be the same size");
    check(pixelHash(page4.get()) != hashPage0,
          "page 4 must not be pixel-identical to page 0 (the pager would be a no-op)");

    AchievementsOptions broken = options;
    broken.assetRoot = gTemp / "no-such-assets";
    broken.snapshot = gTemp / "never.png";
    bool threw = false;
    try {
        renderAchievementsHeadless(model, broken);
    } catch (const std::exception& error) {
        const std::string text = error.what();
        threw = text.find("font_zh.ttc") != std::string::npos;
        check(threw, "a missing font must name font_zh.ttc, got " + text);
    }
    check(threw, "a missing font must throw rather than draw an empty screen");
    check(!fs::exists(broken.snapshot), "a failed render must not leave a snapshot behind");
}
#endif

int run(int argc, char** argv) {
#ifdef PVZ_ENABLE_DESKTOP
    if (argc < 3) {
        std::cerr << "usage: achievements_test <assets dir> <temp dir>\n";
        return 2;
    }
    const fs::path assets = fs::path(argv[1]);
    gTemp = fs::path(argv[2]);
#else
    if (argc < 2) {
        std::cerr << "usage: achievements_test <temp dir>\n";
        return 2;
    }
    gTemp = fs::path(argv[1]);
#endif
    std::error_code error;
    fs::create_directories(gTemp, error);
    check(!error, "cannot create the temp directory " + pathUtf8(gTemp) + ": " + error.message());

    testShippedModel();
    testHumanize();
    testTitleComesFromTheTable();
    testMissingTableFallsBackToTheHumaniser();
    testPageRange();
    testOnlyStarRowsCarryNumbers();
    testEmptySaveShowsZeros();
    testJsonShape();
#ifdef PVZ_ENABLE_DESKTOP
    testRenderWritesPng(assets);
    std::cout << "achievements render tests passed\n";
#else
    std::cout << "achievements tests passed\n";
#endif
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        return run(argc, argv);
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
