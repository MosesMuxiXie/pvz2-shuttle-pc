// Daily challenges screen (B4). What this test exists to prevent:
//   1. inventing a schedule: the sheet's only gate is `params.Disabled` (no date, no rotation),
//      so "open" must be that flag and the screen must say so instead of drawing a countdown;
//   2. a reward line that quietly promises gems/mints the client cannot pay (the shop drew the
//      same line: `unmodelledCurrency = 479`);
//   3. a pager that hides rows of an 11-row list;
//   4. a headless JSON whose keys drift away from what `--daily` will print.
//
// The desktop section draws the screen and checks the picture, like the achievements test.

#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include "catalog.hpp"  // pathUtf8
#include "daily_view.hpp"

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
    if (!ok) throw std::runtime_error("daily test failed: " + message);
}

fs::path gTemp;

DailyModel shipped() {
    DailyModel model = DailyModel::loadShipped();
    check(model.rows.size() == 11,
          "the sheet must carry 11 daily quests, got " + std::to_string(model.rows.size()));
    return model;
}

const DailyRow& pick(const DailyModel& model, const std::string& id) {
    for (const DailyRow& row : model.rows) {
        if (row.id == id) return row;
    }
    throw std::runtime_error("daily test failed: no row " + id);
}

void testShippedModel() {
    const DailyModel model = shipped();
    check(model.open == 11, "the shipped sheet marks all 11 open, got " +
                                std::to_string(model.open));
    check(model.tabs == 2, "quests.tabs must be 2 (daily + epic), got " +
                               std::to_string(model.tabs));
    std::set<std::string> ids;
    for (const DailyRow& row : model.rows) {
        check(!row.id.empty(), "every row needs an id");
        check(ids.insert(row.id).second, "duplicate daily id " + row.id);
        check(!row.title.empty(), "row " + row.id + " has no title to draw");
        check(row.title != row.titleKey, "a title must never be the key: " + row.id);
        check(row.title.find('_') == std::string::npos,
              "no title may print a raw key fragment: " + row.title);
        check(!row.targetType.empty(), "row " + row.id + " has no target type");
        check(row.open, "the shipped rows are open (Disabled=false), found a closed one");
        check(row.reason.empty(), "an open row must not carry a reason");
        check(!row.reward.empty(), "even a rewardless row must render something");
    }
    check(ids.size() == 11, "11 unique ids expected");
    check(!model.source.empty(), "the model must remember where it was read from");
}

// B6b: `title` is LawnStrings text, the humaniser only runs when the table has no row.
void testTitleComesFromTheTable() {
    const DailyModel model = shipped();
    int fromTable = 0;
    int humanised = 0;
    for (const DailyRow& row : model.rows) {
        if (row.title == humanizeGameKey(row.titleKey)) ++humanised;
        else ++fromTable;
    }
    check(fromTable == 11, "the table must name all 11 rows, " + std::to_string(fromTable) +
                               " use the table and " + std::to_string(humanised) +
                               " fell back to the humaniser");
    const DailyRow& seeds = pick(model, "COLLECT_SEED_PACKETS_40_DQ");
    check(seeds.titleKey == "COLLECT_SEED_PACKETS_TITLE",
          "the row keeps its key, got " + seeds.titleKey);
    check(seeds.title == "收集种子包！",
          "the row must print the table's 收集种子包！, got " + seeds.title);
}

// No `lawn_strings.json`: the model has to look exactly like it did before B6b.
void testMissingTableFallsBackToTheHumaniser() {
    const fs::path tree = gTemp / "daily-no-loc";
    fs::create_directories(tree / "native" / "generated");
    fs::copy_file(DailyModel::loadShipped().source, tree / "native" / "generated" / "metagame.json",
                  fs::copy_options::overwrite_existing);
    const DailyModel bare = DailyModel::load(tree / "native" / "generated" / "metagame.json");
    check(bare.rows.size() == 11, "the rows must still load without a string table");
    for (const DailyRow& row : bare.rows) {
        check(row.title == humanizeGameKey(row.titleKey),
              "with no table the title is the humanised key, got " + row.title);
    }
}

void testRewardLines() {
    const DailyModel model = shipped();
    const DailyRow& seeds = pick(model, "COLLECT_SEED_PACKETS_40_DQ");
    check(seeds.reward.find("2000") != std::string::npos &&
              seeds.reward.find("金币") != std::string::npos,
          "2000 coins must read as 2000 金币, got " + seeds.reward);
    check(seeds.payable, "coins are the one currency this client can pay");

    const DailyRow& gems = pick(model, "COMPLETE_ALL_DAILY_QUESTS_DQ");
    check(gems.reward.find("10") != std::string::npos &&
              gems.reward.find("宝石") != std::string::npos,
          "10 gems must read as 10 宝石, got " + gems.reward);
    check(!gems.payable, "gems have no sink or source here, the row must not promise payment");

    const DailyRow& mints = pick(model, "WIN_SINGLE_JOUST_MATCH_DQ");
    check(mints.reward.find("薄荷币") != std::string::npos,
          "mints must be named 薄荷币, got " + mints.reward);
    check(!mints.payable, "mints are server-side, the row must not promise payment");

    int payable = 0;
    for (const DailyRow& row : model.rows) {
        if (row.payable) ++payable;
    }
    check(payable == 5, "5 of the 11 rows pay coins only, counted " + std::to_string(payable));
}

void testDisabledClosesTheRow() {
    // The rule, proved on a scratch sheet: the shipped data has no closed row, so a synthetic one
    // is the only way to show the flag is actually read instead of hardcoded open.
    const fs::path file = gTemp / "daily-disabled.json";
    std::ofstream out(file, std::ios::binary);
    out << R"({"quests":{"tabs":[{},{}],"daily":[)"
        << R"({"id":"A_DQ","nameKey":"ALPHA_TITLE","targetType":"BeatXAdventureLevelsQuestData",)"
        << R"("params":{"Disabled":false,"Repeatable":true},)"
        << R"("rewards":[{"amount":100,"type":"coins"}]},)"
        << R"({"id":"B_DQ","nameKey":"BETA_TITLE","targetType":"AdsViewedQuestData",)"
        << R"("params":{"Disabled":true,"Repeatable":true},)"
        << R"("rewards":[{"amount":2,"type":"gems"}]}]}})";
    out.close();

    const DailyModel scratch = DailyModel::load(file);
    check(scratch.rows.size() == 2, "the scratch sheet has two rows");
    check(scratch.open == 1, "one row is Disabled=true, so exactly one is open, got " +
                                 std::to_string(scratch.open));
    const DailyRow& closed = pick(scratch, "B_DQ");
    check(!closed.open, "Disabled=true must close the row");
    check(!closed.reason.empty(), "a closed row must carry a reason");
    check(closed.reason.find("Disabled") != std::string::npos,
          "the reason must name the field it used, got " + closed.reason);
    check(pick(scratch, "A_DQ").open, "Disabled=false must stay open");
    check(scratch.tabs == 2, "the tabs count must be read from the sheet");
}

void testPageRange() {
    const PageRange single = PageRange::of(11, 0, 12);
    check(single.pages == 1 && single.count == 11, "11 rows fit one page of 12");

    const PageRange four = PageRange::of(11, 2, 4);
    check(four.pages == 3 && four.page == 2 && four.first == 8 && four.count == 3,
          "perPage 4 over 11 rows: page 2 must be the 3 leftovers");

    const PageRange past = PageRange::of(11, 9, 4);
    check(past.page == 2, "a page past the end must clamp to the last page");

    int seen = 0;
    for (int page = 0; page < 3; ++page) seen += PageRange::of(11, page, 4).count;
    check(seen == 11, "the three pages must cover 11 rows exactly once");
}

void testJsonShape() {
    const DailyModel model = shipped();
    const Json json = dailyJson(model, PageRange::of(11, 0, 12), 12);
    std::set<std::string> keys;
    for (auto it = json.begin(); it != json.end(); ++it) keys.insert(it.key());
    const std::set<std::string> expected{"screen", "total", "open", "tabs",
                                         "perPage", "page", "pages", "visible"};
    check(keys == expected, "the headless JSON keys drifted from the agreed set");
    check(json["screen"] == "daily", "screen must be `daily`");
    check(json["total"] == 11, "total must be 11");
    check(json["open"] == 11, "open must be 11 for the shipped sheet");
    check(json["tabs"] == 2, "tabs must be 2");
    check(json["visible"].size() == 11, "the single page must carry all 11 rows");

    const Json item = json["visible"][0];
    std::set<std::string> itemKeys;
    for (auto it = item.begin(); it != item.end(); ++it) itemKeys.insert(it.key());
    const std::set<std::string> expectedItem{"id", "title", "target", "reward", "open", "payable"};
    check(itemKeys == expectedItem, "the per-row JSON keys drifted");
    check(item["open"] == true, "the rows are open");
    check(item["target"].is_string(), "the target type must be a string");
}

#ifdef PVZ_ENABLE_DESKTOP
std::uint64_t pixelHash(SDL_Surface* surface) {
    std::uint64_t hash = 1469598103934665603ull;
    const auto* pixels = static_cast<const std::uint8_t*>(surface->pixels);
    for (int y = 0; y < surface->h; y += 3) {
        const auto* row = pixels + static_cast<std::ptrdiff_t>(y) * surface->pitch;
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
    const DailyModel model = shipped();
    DailyOptions options;
    options.assetRoot = assets;
    options.frames = 2;
    options.snapshot = gTemp / "daily.png";
    options.perPage = DailyLayout::kPerPage;

    const Json result = renderDailyHeadless(model, options);
    check(result["screen"] == "daily", "the render must return the same JSON");
    check(result["total"] == 11, "the render must return total=11");
    check(result["open"] == 11, "the render must return open=11");
    check(fs::is_regular_file(options.snapshot), "the snapshot must be written");
    check(fs::file_size(options.snapshot) > 10 * 1024,
          "a screen with 11 rows of text must exceed 10 KB, got " +
              std::to_string(fs::file_size(options.snapshot)));

    sdl::Surface image(IMG_Load(pathUtf8(options.snapshot).c_str()), SDL_DestroySurface);
    check(bool(image), "the snapshot must decode");
    check(image->w == 1280 && image->h == 720,
          "the screen must be 1280x720, got " + std::to_string(image->w) + "x" +
              std::to_string(image->h));

    const auto* pixels = static_cast<const std::uint8_t*>(image->pixels);
    int ink = 0;
    for (int y = static_cast<int>(DailyLayout::kRowTop);
         y < static_cast<int>(DailyLayout::kRowTop + 11 * DailyLayout::kRowHeight); y += 2) {
        const auto* row = pixels + static_cast<std::ptrdiff_t>(y) * image->pitch;
        for (int x = static_cast<int>(DailyLayout::kRowLeft);
             x < static_cast<int>(DailyLayout::kRowLeft + DailyLayout::kRowWidth); x += 2) {
            const auto* p = row + static_cast<std::ptrdiff_t>(x) * 4;
            if (p[0] > 150 && p[1] > 150 && p[2] > 140) ++ink;
        }
    }
    check(ink > 500, "the row band must contain drawn text, ink pixels=" + std::to_string(ink));

    const std::uint64_t hashAll = pixelHash(image.get());

    DailyOptions paged = options;
    paged.snapshot = gTemp / "daily-paged.png";
    paged.perPage = 4;
    renderDailyHeadless(model, paged);
    sdl::Surface paged4(IMG_Load(pathUtf8(paged.snapshot).c_str()), SDL_DestroySurface);
    check(bool(paged4), "the paged snapshot must decode");
    check(pixelHash(paged4.get()) != hashAll,
          "a 4-row page must not be pixel-identical to the 11-row page");

    DailyOptions broken = options;
    broken.assetRoot = gTemp / "no-such-assets";
    broken.snapshot = gTemp / "never-daily.png";
    bool threw = false;
    try {
        renderDailyHeadless(model, broken);
    } catch (const std::exception& error) {
        threw = std::string(error.what()).find("font_zh.ttc") != std::string::npos;
        check(threw, std::string("a missing font must name font_zh.ttc, got ") + error.what());
    }
    check(threw, "a missing font must throw rather than draw an empty screen");
    check(!fs::exists(broken.snapshot), "a failed render must not leave a snapshot behind");
}
#endif

int run(int argc, char** argv) {
#ifdef PVZ_ENABLE_DESKTOP
    if (argc < 3) {
        std::cerr << "usage: daily_test <assets dir> <temp dir>\n";
        return 2;
    }
    const fs::path assets = fs::path(argv[1]);
    gTemp = fs::path(argv[2]);
#else
    if (argc < 2) {
        std::cerr << "usage: daily_test <temp dir>\n";
        return 2;
    }
    gTemp = fs::path(argv[1]);
#endif
    std::error_code error;
    fs::create_directories(gTemp, error);
    check(!error, "cannot create the temp directory " + pathUtf8(gTemp) + ": " + error.message());

    testShippedModel();
    testTitleComesFromTheTable();
    testMissingTableFallsBackToTheHumaniser();
    testRewardLines();
    testDisabledClosesTheRow();
    testPageRange();
    testJsonShape();
#ifdef PVZ_ENABLE_DESKTOP
    testRenderWritesPng(assets);
    std::cout << "daily render tests passed\n";
#else
    std::cout << "daily tests passed\n";
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
