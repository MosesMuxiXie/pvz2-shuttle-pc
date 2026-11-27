#include "shop_layout.hpp"

#include <algorithm>
#include <map>

namespace pvz {
namespace {

/// True when the refusal blames the client, not the wallet. Kept here next to the sentences so a
/// new refusal reason has to decide which side it is on.
bool blamesClient(const ShopItem& item) {
    if (!item.implemented) return true;
    if (item.unlock == UnlockKind::unknown) return true;
    if (item.currency != "coin" && item.currency != "free") return true;
    return !item.payloadModelled;
}

}  // namespace

const std::vector<ShopTab>& shopTabs() {
    static const std::vector<ShopTab> tabs{
        {"buyable", "可购买"},
        {"coin", "金币"},
        {"gem", "宝石"},
        {"mint", "薄荷币"},
        {"free", "免费"},
    };
    return tabs;
}

std::string shopRefusalReason(const ShopItem& item, const Progress& progress) {
    // Same order, same words as `purchase()` (native/src/shop.cpp:319-380). A difference here is a
    // screen that lies about what Enter will do, so the test compares the two directly.
    if (item.oneTime && owns(progress, item.id)) return "already owned";
    if (!item.implemented) return "not implemented in this client";
    if (item.unlock == UnlockKind::stars) {
        return "star-gated: needs " + std::to_string(item.unlockStars) + " stars";
    }
    if (item.unlock == UnlockKind::unknown) return "unlock kind is unknown for this row";
    int cost = 0;
    if (item.currency == "free") {
        cost = 0;
    } else if (item.currency == "coin") {
        if (item.price <= 0) return "item has no coin price";
        cost = item.price;
    } else {
        return "currency " + item.currency + " is not modelled yet";
    }
    if (!item.payloadModelled) {
        if (item.undeliverable.empty()) return "row grants nothing this client models";
        std::string named;
        for (const std::string& key : item.undeliverable) {
            if (!named.empty()) named += ", ";
            named += key;
        }
        return "payload " + named + " is not modelled yet";
    }
    if (progress.coins < cost) {
        return "not enough coins (need " + std::to_string(cost) + ", have " +
               std::to_string(progress.coins) + ")";
    }
    return {};
}

std::vector<ShopRow> shopRowsForTab(const Shop& shop, const Progress& progress, int tab) {
    const auto& tabs = shopTabs();
    const int index = std::clamp(tab, 0, static_cast<int>(tabs.size()) - 1);
    const std::string& key = tabs[static_cast<std::size_t>(index)].key;

    std::vector<ShopRow> rows;
    rows.reserve(shop.items().size());
    for (const ShopItem& item : shop.items()) {
        if (key == "buyable") {
            // The one view that is a filter, and it must agree with `Shop::buyable_` exactly
            // (native/src/shop.cpp:285-293): spendable means a free row or a positive coin price.
            const bool spendable =
                item.currency == "free" || (item.currency == "coin" && item.price > 0);
            if (!spendable || !item.implemented || item.unlock == UnlockKind::stars ||
                item.unlock == UnlockKind::unknown || !item.payloadModelled) {
                continue;
            }
        } else if (item.currency != key) {
            continue;
        }
        ShopRow row;
        row.id = item.id;
        row.label = item.nameZh.empty() ? item.id : item.nameZh;
        row.currency = item.currency;
        row.price = item.price;
        row.owned = owns(progress, item.id);
        row.reason = shopRefusalReason(item, progress);
        row.affordable = row.reason.empty();
        row.unmodelled = !row.affordable && blamesClient(item);
        rows.push_back(std::move(row));
    }
    return rows;
}

ShopLayout shopLayout(const Shop& shop, const Progress& progress, int tab, int cursor) {
    const auto& tabs = shopTabs();
    ShopLayout layout;
    layout.tabIndex = std::clamp(tab, 0, static_cast<int>(tabs.size()) - 1);
    layout.tabKey = tabs[static_cast<std::size_t>(layout.tabIndex)].key;
    layout.tabLabel = tabs[static_cast<std::size_t>(layout.tabIndex)].label;
    layout.rows = shopRowsForTab(shop, progress, layout.tabIndex);
    layout.total = static_cast<int>(layout.rows.size());
    layout.pageSize = kShopPageSize;
    layout.pages = layout.total == 0 ? 1 : (layout.total + layout.pageSize - 1) / layout.pageSize;
    layout.cursor = layout.total == 0 ? 0 : std::clamp(cursor, 0, layout.total - 1);
    layout.page = layout.cursor / layout.pageSize;
    layout.first = layout.page * layout.pageSize;
    layout.count = std::min(layout.pageSize, layout.total - layout.first);
    return layout;
}

Json shopJson(const Shop& shop, const Progress& progress, const ShopLayout& layout) {
    Json items = Json::array();
    for (int i = layout.first; i < layout.first + layout.count; ++i) {
        const ShopRow& row = layout.rows[static_cast<std::size_t>(i)];
        Json entry{{"id", row.id},
                   {"label", row.label},
                   {"price", row.price},
                   {"currency", row.currency},
                   {"affordable", row.affordable},
                   {"owned", row.owned},
                   {"unmodelled", row.unmodelled},
                   {"reason", row.reason}};
        entry["selected"] = (i == layout.cursor);
        items.push_back(std::move(entry));
    }
    return Json{{"screen", "shop"},
                {"coins", progress.coins},
                {"gems", progress.gems},
                {"buyable", static_cast<int>(shop.buyable())},
                {"rows", static_cast<int>(shop.size())},
                {"tab", layout.tabKey},
                {"tabLabel", layout.tabLabel},
                {"tabIndex", layout.tabIndex},
                {"cursor", layout.cursor},
                {"page", layout.page},
                {"pages", layout.pages},
                {"totalInTab", layout.total},
                {"items", std::move(items)}};
}

Json shopSummaryJson(const Shop& shop, const Progress& progress) {
    // `buyable` splits by the row's own `itemType`, which is what the report's table shows.
    std::map<std::string, int> byType;
    for (const ShopRow& row : shopRowsForTab(shop, progress, 0)) {
        const ShopItem* item = shop.find(row.id);
        byType[item != nullptr && !item->itemType.empty() ? item->itemType : "unknown"] += 1;
    }
    Json types = Json::object();
    for (const auto& [type, count] : byType) types[type] = count;

    Json tabs = Json::object();
    int partition = 0;
    for (std::size_t i = 0; i < shopTabs().size(); ++i) {
        const int size = static_cast<int>(shopRowsForTab(shop, progress, static_cast<int>(i)).size());
        tabs[shopTabs()[i].key] = size;
        if (i > 0) partition += size;  // tab 0 is a view over the same rows, so it is not counted
    }
    // Every row of the catalogue, once, bucketed by the sentence it would return. The map makes the
    // histogram stable so the report can quote it and a test can pin it.
    std::map<std::string, int> reasons;
    for (const ShopItem& item : shop.items()) {
        const std::string reason = shopRefusalReason(item, progress);
        reasons[reason.empty() ? "(buyable)" : reason] += 1;
    }
    Json reasonCounts = Json::object();
    for (const auto& [reason, count] : reasons) reasonCounts[reason] = count;

    return Json{{"rows", static_cast<int>(shop.size())},
                {"buyable", static_cast<int>(shop.buyable())},
                {"unmodelledCurrency", static_cast<int>(shop.unmodelledCurrency())},
                {"buyableByType", std::move(types)},
                {"tabSizes", std::move(tabs)},
                {"currencyPartition", partition},
                {"reasons", std::move(reasonCounts)}};
}

}  // namespace pvz
