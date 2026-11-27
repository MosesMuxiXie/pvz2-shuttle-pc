// The shop screen (B5). What this test exists to prevent:
//   1. a tab strip that hides rows: the four currency tabs must partition all 585 rows, and the
//      "可购买" tab must be exactly the 72 rows the CLI calls `buyable`;
//   2. a refusal sentence that drifts from the rule: every one of the 585 rows is compared against
//      a real `pvz::purchase()` on a copy of the save, so the screen cannot say "not enough coins"
//      where the buyer would say "currency gem is not modelled yet";
//   3. a preview that writes the save: `renderShopHeadless()` with a save file must leave the file
//      byte-for-byte identical, and with no save file must not create one;
//   4. a screen that is not deterministic: two renders of the same state must produce the same JSON.
//
// The audit build has no SDL, so the desktop half (drawing, the two screenshots) lives in
// `shop_render_test`, which compiles this same file with PVZ_ENABLE_DESKTOP=1.

#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include "catalog.hpp"  // pathUtf8
#include "progress.hpp"
#include "shop.hpp"
#include "shop_layout.hpp"
#include "shop_view.hpp"

#ifdef PVZ_ENABLE_DESKTOP
#include <SDL3/SDL.h>
#include <SDL3_image/SDL_image.h>

#include "sdl_support.hpp"
#endif

namespace fs = std::filesystem;
using namespace pvz;

namespace {

void check(bool ok, const std::string& message) {
    if (!ok) throw std::runtime_error("shop ui test failed: " + message);
}

fs::path gContent;
fs::path gUnlock;
fs::path gTemp;

std::string readBytes(const fs::path& file) {
    std::ifstream in(file, std::ios::binary);
    check(bool(in), "cannot read " + pathUtf8(file));
    return std::string(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
}

const Shop& shop() {
    static const Shop loaded = Shop::load(gContent, gUnlock);
    return loaded;
}

/// A save that can afford any single row in the catalogue, so refusals are never about money unless
/// the section says so.
Progress richSave() {
    Progress progress;
    progress.coins = 10'000'000;
    return progress;
}

const ShopRow& rowOf(const ShopLayout& layout, const std::string& id) {
    for (const ShopRow& row : layout.rows) {
        if (row.id == id) return row;
    }
    throw std::runtime_error("shop ui test failed: no row " + id + " in tab " + layout.tabKey);
}

int countTabs() { return static_cast<int>(shopTabs().size()); }

// ---------------------------------------------------------------------------------------------
// 1. Tabs partition the catalogue
// ---------------------------------------------------------------------------------------------

void testTabPartition() {
    check(countTabs() == 5, "five tabs expected (buyable + four currencies)");
    const Progress save = richSave();
    const int buyableRows = static_cast<int>(shopRowsForTab(shop(), save, 0).size());
    check(buyableRows == static_cast<int>(shop().buyable()),
          "the 可购买 tab must be the CLI's buyable set: tab=" + std::to_string(buyableRows) +
              " cli=" + std::to_string(shop().buyable()));

    int partition = 0;
    for (int tab = 1; tab < countTabs(); ++tab) {
        partition += static_cast<int>(shopRowsForTab(shop(), save, tab).size());
    }
    check(partition == static_cast<int>(shop().size()),
          "the four currency tabs must add up to every row: " + std::to_string(partition) + " vs " +
              std::to_string(shop().size()));

    const Json summary = shopSummaryJson(shop(), save);
    check(summary["rows"] == 585, "the catalogue has 585 rows");
    check(summary["buyable"] == 72, "the buyable set is 72 rows");
    check(summary["currencyPartition"] == 585, "summary must report the same partition");
    check(summary["tabSizes"]["gem"] == 469, "469 rows are priced in gems");
    check(summary["tabSizes"]["coin"] == 100, "100 rows are priced in coins");
    check(summary["tabSizes"]["mint"] == 10, "10 rows are priced in mints");
    check(summary["tabSizes"]["free"] == 6, "6 rows are free");
    std::cout << "  tabs: " << summary["tabSizes"].dump() << "  buyable by type: "
              << summary["buyableByType"].dump() << '\n';
    std::cout << "  reasons: " << summary["reasons"].dump() << '\n';
    // The histogram is a partition of the catalogue too: every row lands in exactly one bucket.
    int reasoned = 0;
    for (const auto& entry : summary["reasons"].items()) reasoned += entry.value().get<int>();
    check(reasoned == static_cast<int>(shop().size()),
          "every row must have exactly one refusal sentence, counted " + std::to_string(reasoned));
    check(summary["reasons"]["(buyable)"] == static_cast<int>(shop().buyable()),
          "the buyable bucket must equal Shop::buyable()");
}

// ---------------------------------------------------------------------------------------------
// 2. The buyable tab == the CLI's buyable set, and each row is really affordable
// ---------------------------------------------------------------------------------------------

void testBuyableTabIsAffordable() {
    const Progress save = richSave();
    const ShopLayout layout = shopLayout(shop(), save, 0, 0);
    check(layout.tabKey == "buyable", "tab 0 is the buyable view");
    check(layout.total == 72, "72 rows in the buyable tab, got " + std::to_string(layout.total));
    for (const ShopRow& row : layout.rows) {
        check(row.affordable, "row " + row.id + " is listed as buyable but refuses: " + row.reason);
        check(row.reason.empty(), "an affordable row must not carry a reason");
        check(!row.owned, "nothing is owned in a fresh save: " + row.id);
        check(row.currency == "coin" || row.currency == "free",
              "buyable rows are coin or free, " + row.id + " is " + row.currency);
        // Independently of the layout's filter, the purchase rule must accept it.
        Progress copy = save;
        const BuyResult result = purchase(shop(), row.id, copy);
        check(result.ok, "purchase() must accept " + row.id + ", said: " + result.reason);
    }

    // The JSON the CLI prints must describe the visible page, not the whole tab.
    const Json json = shopJson(shop(), save, layout);
    check(json["screen"] == "shop", "screen must be `shop`");
    check(json["coins"] == save.coins, "coins must be reported");
    check(json["gems"] == save.gems, "gems must be reported");
    check(json["buyable"] == 72, "buyable must be 72");
    check(json["rows"] == 585, "rows must be 585");
    check(json["tab"] == "buyable", "tab key must be stable");
    check(json["items"].size() == static_cast<std::size_t>(kShopPageSize),
          "the page must carry exactly 8 rows");
    std::set<std::string> keys;
    for (auto it = json["items"][0].begin(); it != json["items"][0].end(); ++it) keys.insert(it.key());
    const std::set<std::string> expected{"id", "label", "price", "currency", "affordable",
                                         "owned", "unmodelled", "reason", "selected"};
    check(keys == expected, "the per-row JSON keys drifted");
    check(json["items"][0]["selected"] == true, "the cursor's row must be marked selected");
}

// ---------------------------------------------------------------------------------------------
// 3. Paging and cursor clamping
// ---------------------------------------------------------------------------------------------

void testPaging() {
    const Progress save = richSave();
    const ShopLayout first = shopLayout(shop(), save, 0, 0);
    check(first.pageSize == 8, "the page size is 8 rows");
    check(first.pages == 9, "72 rows over 8 per page is 9 pages, got " +
                                std::to_string(first.pages));
    check(first.page == 0 && first.first == 0 && first.count == 8, "page 0 is the first 8 rows");

    const ShopLayout last = shopLayout(shop(), save, 0, 71);
    check(last.page == 8 && last.first == 64 && last.count == 8,
          "the last page starts at row 64 and holds 8 rows");

    const ShopLayout past = shopLayout(shop(), save, 0, 999);
    check(past.cursor == 71, "a cursor past the end clamps to the last row, got " +
                                 std::to_string(past.cursor));
    const ShopLayout negative = shopLayout(shop(), save, 0, -5);
    check(negative.cursor == 0, "a negative cursor clamps to 0");

    const ShopLayout gems = shopLayout(shop(), save, 2, 0);
    check(gems.tabKey == "gem", "tab 2 is the gem tab");
    check(gems.total == 469, "469 gem rows");
    check(gems.pages == 59, "469 rows over 8 is 59 pages, got " + std::to_string(gems.pages));
    const ShopLayout gemLast = shopLayout(shop(), save, 2, 468);
    check(gemLast.count == 5, "the last gem page holds the leftover 5 rows");

    // Out-of-range tabs clamp instead of reading past the table.
    const ShopLayout clamped = shopLayout(shop(), save, 99, 0);
    check(clamped.tabIndex == countTabs() - 1, "a tab past the end clamps to the last tab");
}

// ---------------------------------------------------------------------------------------------
// 4. Buying lowers coins and flips `owned` (only one-time rows are blocked by ownership)
// ---------------------------------------------------------------------------------------------

void testPurchaseFlipsOwned() {
    const Progress rich = richSave();
    const ShopLayout layout = shopLayout(shop(), rich, 0, 0);
    const ShopRow* oneTime = nullptr;
    for (const ShopRow& row : layout.rows) {
        const ShopItem* item = shop().find(row.id);
        if (item != nullptr && item->oneTime) {
            oneTime = &row;
            break;
        }
    }
    check(oneTime != nullptr, "the buyable set must contain at least one one-time row");

    Progress save = rich;
    const BuyResult result = purchase(shop(), oneTime->id, save);
    check(result.ok, "the one-time row must be buyable: " + result.reason);
    check(save.coins == rich.coins - result.coinsSpent,
          "coins must drop by exactly the receipt: " + std::to_string(save.coins));
    check(owns(save, oneTime->id), "the purchase must be recorded in the save");

    const ShopLayout after = shopLayout(shop(), save, 0, 0);
    const ShopRow fresh = [&] {
        for (const ShopRow& row : after.rows) {
            if (row.id == oneTime->id) return row;
        }
        throw std::runtime_error("shop ui test failed: the bought row left the tab");
    }();
    // A one-time row that is owned is no longer in the "can buy" view only if the tab filters it;
    // this tab keeps it visible and tells the truth about why Enter would fail.
    check(fresh.owned, "the row must report itself owned");
    check(!fresh.affordable, "an owned one-time row cannot be bought again");
    check(fresh.reason == "already owned", "the reason must be `already owned`, got " + fresh.reason);
}

// ---------------------------------------------------------------------------------------------
// 5. Not enough coins quotes both numbers
// ---------------------------------------------------------------------------------------------

void testNotEnoughCoins() {
    Progress broke;
    broke.coins = 0;
    const ShopLayout layout = shopLayout(shop(), broke, 0, 0);
    const ShopRow& row = layout.rows.front();
    const int price = row.price;
    check(price > 0, "the first buyable row must cost coins");
    check(!row.affordable, "a save with 0 coins cannot buy a priced row");
    check(row.reason == "not enough coins (need " + std::to_string(price) + ", have 0)",
          "the refusal must quote the price and the balance, got " + row.reason);
    check(!row.unmodelled, "a short wallet is the player's problem, not the client's");
}

// ---------------------------------------------------------------------------------------------
// 6. Every refusal sentence matches what `purchase()` would say, for all 585 rows
// ---------------------------------------------------------------------------------------------

void testRefusalSentencesMatchPurchase() {
    // Two saves: one rich (so money never explains the refusal) and one poor (so money does).
    for (const Progress& save : {richSave(), [] {
             Progress p;
             p.coins = 0;
             return p;
         }()}) {
        int compared = 0;
        for (int tab = 1; tab < countTabs(); ++tab) {
            for (const ShopRow& row : shopRowsForTab(shop(), save, tab)) {
                Progress copy = save;
                const BuyResult result = purchase(shop(), row.id, copy);
                const std::string why = shopRefusalReason(*shop().find(row.id), save);
                check(why == result.reason,
                      "row " + row.id + ": screen says `" + why + "`, purchase says `" +
                          result.reason + "`");
                check(row.affordable == result.ok,
                      "row " + row.id + ": affordable flag disagrees with purchase()");
                check(row.unmodelled == (!result.reason.empty() &&
                                         result.reason.find("not enough coins") == std::string::npos &&
                                         result.reason != "already owned"),
                      "row " + row.id + ": unmodelled must mean `not the wallet's fault`");
                ++compared;
            }
        }
        check(compared == 585, "every row must be compared, compared " + std::to_string(compared));
    }

    // Spot-check the four families the report names, so the test fails loudly if the wording moves.
    const Progress rich = richSave();
    const auto findWith = [&](const std::string& currency) -> const ShopItem& {
        for (const ShopItem& item : shop().items()) {
            if (item.currency == currency) return item;
        }
        throw std::runtime_error("shop ui test failed: no row priced in " + currency);
    };
    check(shopRefusalReason(findWith("gem"), rich) == "currency gem is not modelled yet",
          "gem rows must say the currency is not modelled");
    check(shopRefusalReason(findWith("mint"), rich) == "currency mint is not modelled yet",
          "mint rows must say the currency is not modelled");

    const ShopItem* payload = nullptr;
    for (const ShopItem& item : shop().items()) {
        if (item.currency == "coin" && !item.payloadModelled && !item.undeliverable.empty()) {
            payload = &item;
            break;
        }
    }
    check(payload != nullptr, "a coin-priced row with an undeliverable payload must exist");
    check(shopRefusalReason(*payload, rich).rfind("payload ", 0) == 0,
          "an undeliverable payload must be named: " + shopRefusalReason(*payload, rich));
    check(shopRefusalReason(*payload, rich).find("is not modelled yet") != std::string::npos,
          "the payload refusal must say it is not modelled");

    // The shipped catalogue has no star-gated, unimplemented or unknown-unlock row (the unlock table
    // reports `stars: 0`), so those three sentences are pinned on synthetic rows: the words are part
    // of the contract even when today's data cannot reach them.
    ShopItem star;
    star.id = "synthetic.star";
    star.currency = "coin";
    star.price = 500;
    star.implemented = true;
    star.payloadModelled = true;
    star.unlock = UnlockKind::stars;
    star.unlockStars = 40;
    check(shopRefusalReason(star, rich) == "star-gated: needs 40 stars",
          "the star gate must quote its number, got " + shopRefusalReason(star, rich));

    ShopItem unimplemented = star;
    unimplemented.unlock = UnlockKind::coins;
    unimplemented.implemented = false;
    check(shopRefusalReason(unimplemented, rich) == "not implemented in this client",
          "an unimplemented row must say so");

    ShopItem unknown = star;
    unknown.unlock = UnlockKind::unknown;
    check(shopRefusalReason(unknown, rich) == "unlock kind is unknown for this row",
          "an unknown unlock must say so");

    ShopItem noPrice = star;
    noPrice.unlock = UnlockKind::coins;
    noPrice.price = 0;
    check(shopRefusalReason(noPrice, rich) == "item has no coin price",
          "a coin row without a price must say so");

    ShopItem granted = star;
    granted.unlock = UnlockKind::coins;
    granted.currency = "coin";
    granted.price = 100;
    granted.oneTime = true;
    Progress owned = rich;
    owned.purchases.push_back(granted.id);
    check(shopRefusalReason(granted, owned) == "already owned",
          "an owned one-time row must say so");
    check(shopRefusalReason(granted, rich).empty(), "an unowned, affordable row has no reason");
}

// ---------------------------------------------------------------------------------------------
// 7. A preview never writes the save
// ---------------------------------------------------------------------------------------------

void testPreviewDoesNotWriteSave() {
    const fs::path save = gTemp / "shop-preview.json";
    Progress progress;
    progress.coins = 12345;
    progress.gems = 7;
    saveProgress(save, progress, 1);
    const std::string before = readBytes(save);

    const Json json = renderShopHeadless(gContent, save, 0, "", 0, 0);
    check(json["coins"] == 12345, "the preview must report the save's coins");
    check(readBytes(save) == before, "renderShopHeadless must not touch the save file");
    check(fs::file_size(save) == before.size(), "the save file size must not change");

    // With no save path at all, nothing may appear on disk.
    const fs::path untouched = gTemp / "shop-never-created.json";
    std::error_code error;
    fs::remove(untouched, error);
    const Json preview = renderShopHeadless(gContent, "", 0, "", 0, 0);
    check(preview["coins"] == 0, "no save file means an empty wallet");
    check(!fs::exists(untouched), "the preview must not create a save file");
}

// ---------------------------------------------------------------------------------------------
// 8. Two renders of the same state are identical
// ---------------------------------------------------------------------------------------------

void testRendersAreDeterministic() {
    const fs::path save = gTemp / "shop-deterministic.json";
    Progress progress;
    progress.coins = 5000;
    progress.gems = 3;
    saveProgress(save, progress, 2);

    const std::string first = renderShopHeadless(gContent, save, 0, "", 0, 3).dump();
    const std::string second = renderShopHeadless(gContent, save, 0, "", 0, 3).dump();
    check(first == second, "two identical renders must produce identical JSON");
    check(first.find("\"cursor\":3") != std::string::npos, "the cursor must be reported");
}

#ifdef PVZ_ENABLE_DESKTOP
// ---------------------------------------------------------------------------------------------
// 9. The desktop half: two screenshots, 1280x720, different pages differ
// ---------------------------------------------------------------------------------------------

void testScreenshots() {
    const fs::path save = gTemp / "shop-shot.json";
    Progress progress;
    progress.coins = 5000;
    progress.gems = 4;
    saveProgress(save, progress, 3);

    // Frame 1: the buyable tab with the cursor on the first row.
    const fs::path shotA = gTemp / "shop-buyable.png";
    renderShopHeadless(gContent, save, 2, shotA, 0, 0);
    check(fs::is_regular_file(shotA), "the first screenshot must be written");
    check(fs::file_size(shotA) > 10 * 1024, "the screenshot must exceed 10 KB");
    const std::string a = readBytes(shotA);

    // Frame 2: the gem tab, where every row is refused for a named reason.
    const fs::path shotB = gTemp / "shop-gem.png";
    renderShopHeadless(gContent, save, 2, shotB, 2, 0);
    const std::string b = readBytes(shotB);
    check(a != b, "the gem tab must draw differently from the buyable tab");

    sdl::Surface image(IMG_Load(pathUtf8(shotA).c_str()), SDL_DestroySurface);
    check(bool(image), "the screenshot must decode");
    check(image->w == 1280 && image->h == 720, "the screen must be 1280x720");

    // A missing font must fail loudly instead of drawing an empty screen.
    const fs::path missing = gTemp / "no-assets";
    bool threw = false;
    try {
        ShopScreenOptions options;
        options.contentRoot = gContent;
        options.progressFile = save;
        options.assetRoot = missing;
        options.frames = 1;
        runShop(options);
    } catch (const std::exception& error) {
        threw = std::string(error.what()).find("font_zh.ttc") != std::string::npos;
        check(threw, std::string("a missing font must name font_zh.ttc, got ") + error.what());
    }
    check(threw, "a missing font must throw");
}
#endif

int run(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "usage: shop_ui_test <content dir> <shop_unlock.json> <temp dir>\n";
        return 2;
    }
    gContent = fs::path(argv[1]);
    gUnlock = fs::path(argv[2]);
    gTemp = fs::path(argv[3]);
    std::error_code error;
    fs::create_directories(gTemp, error);
    check(!error, "cannot create the temp directory " + pathUtf8(gTemp));

    testTabPartition();
    testBuyableTabIsAffordable();
    testPaging();
    testPurchaseFlipsOwned();
    testNotEnoughCoins();
    testRefusalSentencesMatchPurchase();
    testPreviewDoesNotWriteSave();
    testRendersAreDeterministic();
#ifdef PVZ_ENABLE_DESKTOP
    testScreenshots();
    std::cout << "shop ui render tests passed\n";
#else
    std::cout << "shop ui tests passed\n";
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
