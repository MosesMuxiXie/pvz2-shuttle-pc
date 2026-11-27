#pragma once

// The shop screen's data half: tabs, rows, the refusal sentence for each row, and the headless
// JSON. No SDL, no file writing - everything here is a pure function of a `Shop` catalogue and a
// `Progress` save, which is what makes it testable without a window.
//
// Two rules this file exists to keep:
//
//  * **The screen never invents a refusal.** `shopRefusalReason()` repeats `purchase()`'s checks in
//    the same order and with the same words (`native/src/shop.cpp:319-380`), so what the row says
//    and what pressing Enter returns can never drift. `shop_ui_test` proves that line by line by
//    comparing the sentence against a real `purchase()` on a copy of the save.
//  * **Tabs are a partition, not a filter.** Tab 0 is a view ("可购买", the 72 rows a player can
//    actually buy); tabs 1-4 are the four currencies the sheet ships (`coin` 100, `gem` 469,
//    `mint` 10, `free` 6) and they add up to all 585 rows with no row twice. That is why 585 is
//    reachable on screen even though `buyable` is only 72.

#include <filesystem>
#include <string>
#include <vector>

#include "shop.hpp"

namespace pvz {

/// One tab of the screen. `key` is stable (tests and the CLI print it), `label` is what is drawn.
struct ShopTab {
    std::string key;    ///< buyable | coin | gem | mint | free
    std::string label;  ///< 可购买 | 金币 | 宝石 | 薄荷币 | 免费
};

/// Five tabs, in drawing order. Tab 0 is the buyable view; the rest partition the catalogue.
const std::vector<ShopTab>& shopTabs();

/// Rows per page. Eight rows fit between the wallet strip and the key hints at 720 px.
inline constexpr int kShopPageSize = 8;

/// One line of the list. `reason` is empty exactly when `affordable` is true.
struct ShopRow {
    std::string id;
    std::string label;     ///< the row's Chinese name, falling back to the id
    std::string currency;  ///< coin | gem | mint | free, verbatim
    int price = 0;
    bool affordable = false;  ///< pressing Enter right now would succeed
    bool owned = false;       ///< `owns(progress, id)`; only `one_time` rows can block on it
    /// True when the refusal is the client's fault rather than the player's: not implemented, a
    /// currency with no wallet, or a payload this build cannot deliver. The screen groups those
    /// under "此客户端无法交付" instead of greying them out.
    bool unmodelled = false;
    std::string reason;  ///< the sentence `purchase()` would return; empty when affordable
};

/// The whole tab plus where the cursor is. `rows` is the full tab (not just the page) so a caller
/// can count, filter or print it without re-reading the catalogue.
struct ShopLayout {
    int tabIndex = 0;
    std::string tabKey;
    std::string tabLabel;
    int cursor = 0;   ///< clamped into the tab
    int pageSize = kShopPageSize;
    int page = 0;     ///< cursor's page
    int pages = 1;
    int first = 0;    ///< first row index on the page
    int count = 0;    ///< rows on the page
    int total = 0;    ///< rows in the tab
    std::vector<ShopRow> rows;
};

/// The sentence `purchase()` would return for `item`, or an empty string when it would succeed.
/// Order and wording are copied from `purchase()` on purpose; see the header comment.
std::string shopRefusalReason(const ShopItem& item, const Progress& progress);

/// Every row of one tab, in catalogue order. `tab` is clamped into `shopTabs()`.
std::vector<ShopRow> shopRowsForTab(const Shop& shop, const Progress& progress, int tab);

/// Rows of one tab, plus paging for `cursor` (clamped into the tab).
ShopLayout shopLayout(const Shop& shop, const Progress& progress, int tab, int cursor);

/// `{screen:"shop", coins, gems, buyable, rows, tab, cursor, page, pages, items:[…]}` where
/// `items` is the visible page only. This is the shape the CLI prints and the test asserts.
Json shopJson(const Shop& shop, const Progress& progress, const ShopLayout& layout);

/// Counts for the report and the screen's header: how the 72 buyable rows split by the row's own
/// `itemType` (`{"costume":45,"seed":21,…}`), and how every tab's size relates to 585.
Json shopSummaryJson(const Shop& shop, const Progress& progress);

}  // namespace pvz
