#pragma once

// The garden screen: the drop table and the Zen garden sheets out of `native/generated/metagame.json`.
//
// It is the almanac screen's sibling and follows the same shape on purpose: `loadGarden()` reads,
// `gardenPage()` pages, `runGarden()` draws, and `renderGardenHeadless()` is the single call the CLI
// dispatcher needs. Nothing here knows about `--garden`; the captain wires the flag.
//
// What the table does and does not carry, because both show up on screen:
//
//  * The 65 collectables are `CollectableType` rows: `typeName`, its class, an image, a pop anim, a
//    reward-dialog title key, and — for 2 of the 65 — a store price. The other 63 have no price in
//    the OBB at all; the panel says "原版无标价" instead of inventing one.
//  * `dropSources` is not "which levels drop this". The original stores reward-table references
//    (`QuestRewardTablesProps`, difficulty buckets like `difficulty=5`) and store SKUs, never level
//    ids, so the screen shows the reference count and names the table it came from. The report
//    records that gap as an unknown rather than calling it a level count.
//  * The Zen garden is four property sheets (`props`, `slotProps`, `bee`, `floatingText`) plus 12
//    pots and 3 plant-reward tables. "Zen 4/4" is the four sheets; the pots are counted separately.

#include "catalog.hpp"
#include "menu_view.hpp"

#include <filesystem>
#include <string>
#include <vector>

namespace pvz {

/// Rows per page in the drop list. Twelve keeps the list clear of the Zen summary above it.
inline constexpr int kGardenPageSize = 12;

/// One reward-table reference (`table`) with the rows that named this collectable (`examples`, e.g.
/// `difficulty=5`). Kept verbatim: the strings are the original's own bucket labels.
struct GardenDropSource {
    std::string table;
    std::vector<std::string> examples;
};

/// The store row a collectable matched, when it matched one. `matchKind` is `item` (the collectable
/// names the SKU's object directly) or `sku` (every token of the collectable appears in the SKU);
/// `priced` is false for a matched row whose price fields are all empty, which is 1 of the 2.
struct GardenSale {
    bool matched = false;
    bool priced = false;
    std::string matchKind;
    std::string sku;
    std::string objectItem;
    std::string priceKind;
    std::string amount;
};

struct GardenItem {
    std::string typeName;
    std::string collectableClass;
    std::string image;
    std::string popAnim;
    std::string titleKey;
    /// `content/` has no prose for collectables, so this stays empty and the panel shows the key.
    std::string title;
    /// The `ObjectType` category this collectable's name coincides with (`pinata`), when it does.
    std::string storeCategory;
    GardenSale sale;
    std::vector<GardenDropSource> sources;
};

/// One scalar from `zenGarden.props`, already printable.
struct ZenValue {
    std::string name;
    std::string text;
};

struct ZenPot {
    std::string positionKey;
    std::string position;
    std::string unlockIndex;
};

struct GardenZen {
    /// The four property sheets found, by name: `props`, `slotProps`, `bee`, `floatingText`.
    std::vector<std::string> tables;
    std::vector<ZenValue> values;
    std::vector<ZenPot> pots;
    /// Plant-reward tables (`ZenGardenMarigoldFinalRewards` and friends).
    int plantRewards = 0;
};

struct GardenData {
    std::vector<GardenItem> drops;
    GardenZen zen;
    std::filesystem::path source;
    /// What could not be read. Empty when everything was; never an exception for a missing input.
    std::string note;
};

/// Reads `metagame.json` (loudly when it is missing) and the `garden` block out of it.
GardenData loadGarden(const std::filesystem::path& contentRoot);

/// One page of the drop list; `index` clamped into `[0, total-1]`, an empty table yields `total == 0`.
struct GardenPage {
    int total = 0;
    int index = 0;
    int page = 0;
    int pages = 0;
    int first = 0;
    int last = 0;
    std::vector<int> visible;
};

GardenPage gardenPage(const std::vector<GardenItem>& drops, int index,
                      int pageSize = kGardenPageSize);

struct GardenOptions {
    std::filesystem::path contentRoot;
    /// Holds `ui/font_zh.ttc`.
    std::filesystem::path assetRoot;
    /// Optional frame capture; `.png` writes PNG, anything else BMP.
    std::filesystem::path snapshot;
    /// >0 renders this many frames headlessly and returns; 0 runs the interactive window.
    int frames = 0;
};

struct GardenResult {
    int drops = 0;
    /// The four Zen property sheets, i.e. the first half of "Zen 4/4".
    int zen = 0;
    int zenTables = 0;
    int zenPots = 0;
    /// The collectable the cursor sat on. Empty when the table had no rows.
    std::string selectedTypeName;
    /// Where the selected row was drawn, for the render test.
    ScreenRect selectedRect;
    /// Exactly the four keys the CLI prints: `screen`, `drops`, `zen`, `pots`.
    Json json;
};

/// `{"screen":"garden","drops":drops,"zen":zen,"pots":pots}` — one place so CLI and tests agree.
Json gardenJson(int drops, int zen, int pots);

/// Draws the screen; `index` is the initial cursor, clamped.
GardenResult runGarden(const GardenData& data, int index, const GardenOptions& options);

/// The one call `main.cpp` needs: load, draw `frames` frames into `snapshot`, return the CLI JSON.
Json renderGardenHeadless(const std::filesystem::path& contentRoot, int frames,
                          const std::filesystem::path& snapshot,
                          const std::filesystem::path& assetRoot = {});

}  // namespace pvz
