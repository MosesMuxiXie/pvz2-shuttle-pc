// Shop catalogue and the purchase rule this client implements.
//
// Two files feed this model and neither is invented here:
//   * `content/shop.json`                 - 585 rows the client wrote (names, SKUs, price, currency)
//   * `native/generated/shop_unlock.json` - compiled from the OBB property sheets: what each row
//                                           is attached to (none / coins / world / mixed / stars)
//
// The original sheets carry no price-gate columns at all (the geometer scan looked for ten
// plausible key names across all 585 rows and found none), so `unlock.kind` is the only gate
// this model honours. Coins are the only currency `Progress` can spend, so gem/mint-priced rows
// are reported as unmodelled instead of being handed out for free.
//
// Payload delivery is all-or-nothing: a row is only sold when *every* payload key it carries is
// modelled (see `Grant`). The shipped catalogue has six such kinds - `plant_id`, `costume_id`,
// `world_key`, `coins`, `gems`, `plantfood_slots`, `plantfood_refresh` - plus `setting` when the
// name is a client switch. `seed_pack`, `mint`, `sun_shovel`, `seed_slots`, `mower_charges`,
// `sun_start_bonus` and resource-counter settings have nowhere to land, so those rows stay
// refused rather than taking coins for nothing.
//
// One trap worth naming: the single row whose `unlock.kind` is `world` is a gem-priced pinata
// bundle for Egypt, not a world key - it is still refused. Keys are granted only by the row
// whose payload is `world_key` (one row, `obb_worldkey.rainbowmarket`), and only because that
// row says so explicitly.
#pragma once

#include <cstdint>
#include <filesystem>
#include <map>
#include <set>
#include <string>
#include <vector>

#include "progress.hpp"

namespace pvz {

enum class UnlockKind { none, coins, world, mixed, stars, unknown };

UnlockKind unlockKindOf(const std::string& text);
const char* unlockKindName(UnlockKind kind);

/// One thing a purchase actually hands over. The receipt (`BuyResult::granted`) is a list of
/// these, so a caller can check the save against the receipt without re-reading the catalogue.
enum class GrantKind {
  seed,              ///< `Progress::seeds` (plant_id)
  costume,           ///< `Progress::costumes` (costume_id)
  key,               ///< `Progress::keys`, +1 per grant; `text` names the world
  coins,             ///< `Progress::coins`, +amount
  gems,              ///< `Progress::gems`, +amount
  plantfood_slots,   ///< `Progress::plantfoodSlots`, +amount
  plantfood_refresh, ///< `Progress::plantfoodRefresh`, set true
  setting,           ///< `Progress::settings[text] = amount` (bool stored as 0/1)
};

const char* grantKindName(GrantKind kind);

struct Grant {
  GrantKind kind = GrantKind::seed;
  /// The id for seed/costume, the world name for a key, the setting name for a setting.
  /// Empty for the numeric kinds.
  std::string text;
  /// What to add or store: a number for coins/gems/plantfood_slots, a bool or number for a
  /// setting, null for seed/costume/key/plantfood_refresh (those are presence, not quantity).
  Json value;
  /// The numeric part of `value`, 0 when it is not a number.
  double number() const { return value.is_number() ? value.get<double>() : 0.0; }
};

struct ShopItem {
  std::string id;
  std::string nameZh;
  std::string category;  ///< shop.json side: items | seeds | bundles | currency
  std::string tab;
  std::string itemType;  ///< plant | costume | pinata | gameupgrade | ...
  std::string currency;  ///< coin | gem | mint | free (exactly what the row says)
  int price = 0;
  bool implemented = false;
  bool oneTime = false;
  UnlockKind unlock = UnlockKind::none;
  int unlockCoins = 0;
  int unlockStars = 0;
  std::string unlockWorld;
  std::string unlockCategory;  ///< the compiled table's own category (costume/seed/event/...)
  std::string payloadKey;      ///< first payload key, e.g. "plant_id"
  /// The payload value when the row grants a string id (`plant_id`). Empty otherwise.
  std::string payloadValue;
  /// Everything a purchase will deliver, in catalogue order. Empty when nothing can be.
  std::vector<Grant> grants;
  /// Payload keys that this client cannot deliver, named so the refusal can quote them.
  /// Non-empty means the row is refused even when `grants` is non-empty: a bundle that pays out
  /// half of what it advertises is worse than a refusal that says which half is missing.
  std::vector<std::string> undeliverable;
  /// True only when every payload key is modelled and at least one grant exists. Everything
  /// else would take coins and hand back nothing, so it is refused instead of sold.
  bool payloadModelled = false;
};

/// Reads `content/shop.json` plus the compiled unlock table. A missing unlock file is an
/// error: without it every row would look buyable.
class Shop {
 public:
  static Shop load(const std::filesystem::path& contentDir,
                   const std::filesystem::path& unlockFile);
  static Shop parse(const std::string& shopText, const std::string& shopOrigin,
                    const std::string& unlockText, const std::string& unlockOrigin);

  const std::vector<ShopItem>& items() const { return items_; }
  const ShopItem* find(const std::string& id) const;
  std::size_t size() const { return items_.size(); }
  /// Counts keyed by `shop.json`'s own category (`items`, `seeds`, `bundles`, `currency`).
  const std::map<std::string, std::size_t>& byCategory() const { return byCategory_; }
  /// Counts keyed by the compiled table's category (`costume`, `seed`, `event`, ...).
  const std::map<std::string, std::size_t>& byUnlockCategory() const { return byUnlockCategory_; }
  const std::map<UnlockKind, std::size_t>& byUnlock() const { return byUnlock_; }
  const std::map<std::string, std::size_t>& byCurrency() const { return byCurrency_; }
  /// Rows a player can actually buy today: implemented, spendable currency, no star gate.
  std::size_t buyable() const { return buyable_; }
  /// Rows priced in a currency this client cannot spend yet (gem / mint).
  std::size_t unmodelledCurrency() const { return unmodelledCurrency_; }
  /// Rows present in shop.json with no record in the compiled table.
  std::size_t missingRows() const { return missingRows_; }

 private:
  std::vector<ShopItem> items_;
  std::map<std::string, std::size_t> index_;
  std::map<std::string, std::size_t> byCategory_;
  std::map<std::string, std::size_t> byUnlockCategory_;
  std::map<UnlockKind, std::size_t> byUnlock_;
  std::map<std::string, std::size_t> byCurrency_;
  std::size_t buyable_ = 0;
  std::size_t unmodelledCurrency_ = 0;
  std::size_t missingRows_ = 0;
};

struct BuyResult {
  bool ok = false;
  std::string itemId;
  std::string reason;
  std::string grantedSeed;  ///< first granted seed, kept for callers of the seed-only API
  int coinsSpent = 0;
  /// The receipt: exactly what was written into `Progress`, in the order it was written.
  /// Empty on a refusal, and empty when the row genuinely grants nothing.
  std::vector<Grant> granted;
};

/// Spends coins from `progress` and records the purchase. Every refusal returns a reason
/// string: a silent `false` is not a valid outcome. Keys are granted only by rows whose payload
/// says `world_key`, and one_time rows cannot be bought twice.
BuyResult purchase(const Shop& shop, const std::string& itemId, Progress& progress);

/// True when `progress` already owns `itemId`.
bool owns(const Progress& progress, const std::string& itemId);

}  // namespace pvz
