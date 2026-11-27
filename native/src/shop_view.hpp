#pragma once

// The shop screen (B5): 585 catalogue rows, of which 72 are buyable today, drawn as a list with a
// detail panel that says *why* a row cannot be bought instead of greying it out.
//
// Layout lives in `shop_layout.{hpp,cpp}` and has no SDL; this file only draws and handles keys, so
// the four decisions that can be wrong (tabs, paging, the refusal sentence, the JSON shape) are
// testable in the audit build with no window and no font.
//
// What the screen does and does not do:
//  * It buys through `pvz::purchase()` - the same function `--shop --buy` uses - and prints its
//    receipt. A successful purchase is written back to `--progress` only when that file was given;
//    with no save file the screen is a read-only preview and never touches the disk.
//  * It cannot pay in gems or mints: those rows carry `unmodelledCurrency`, and the panel says so
//    with the same sentence the CLI prints.
//  * Server-side rows (`mints`, `event_energy`) stay refused; nothing here invents a currency.

#include <filesystem>

#include "catalog.hpp"
#include "progress.hpp"
#include "shop_layout.hpp"

namespace pvz {

/// Everything the screen needs. `assetRoot` is optional: when it is empty the font is looked up next
/// to the content tree (the same rule `almanac_view` uses), which keeps the CLI free of an extra
/// flag.
struct ShopScreenOptions {
    std::filesystem::path contentRoot;   ///< holds `shop.json`
    std::filesystem::path progressFile;  ///< empty = read-only preview, never written
    std::filesystem::path assetRoot;     ///< empty = resolved from `contentRoot`
    std::filesystem::path snapshot;      ///< written when non-empty
    int frames = 0;                      ///< > 0 = headless, draw this many frames and stop
    int tab = 0;
    int cursor = 0;
};

/// The one call the CLI dispatcher needs: draw the screen for `frames` frames (0 = nothing is drawn,
/// only the JSON is computed), write `snapshot` when asked, and return the screen state as JSON.
/// Never writes the save file: this is a preview, not a purchase.
Json renderShopHeadless(const std::filesystem::path& contentRoot,
                        const std::filesystem::path& progressFile, int frames,
                        const std::filesystem::path& snapshot, int tab = 0, int cursor = 0);

/// The interactive screen: ↑↓ move, ←→/Tab/q/e switch tab, Enter buys (through `purchase()`), Esc
/// exits. Purchases are written back only when `progressFile` is non-empty. The returned JSON is the
/// final screen state plus `lastResult` (the receipt of the last Enter, or null).
Json runShop(const ShopScreenOptions& options);

}  // namespace pvz
