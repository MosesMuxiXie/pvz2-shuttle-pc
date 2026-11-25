#include "shop.hpp"

#include <array>
#include <cmath>

#include <algorithm>
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace pvz {
namespace {

[[noreturn]] void fail(const std::string& origin, const std::string& what) {
  throw std::runtime_error("shop: " + origin + ": " + what);
}

std::string readFile(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    throw std::runtime_error("shop: " + path.string() + ": cannot open");
  }
  std::ostringstream buffer;
  buffer << in.rdbuf();
  return buffer.str();
}

Json parseJson(const std::string& text, const std::string& origin) {
  try {
    return Json::parse(text);
  } catch (const std::exception& error) {
    fail(origin, std::string("not valid JSON: ") + error.what());
  }
}

const Json& member(const Json& object, const char* key, const std::string& origin) {
  const auto found = object.find(key);
  if (found == object.end()) {
    fail(origin, std::string("missing \"") + key + "\"");
  }
  return *found;
}

std::string text(const Json& object, const char* key, const std::string& origin,
                 const std::string& fallback = {}) {
  const auto found = object.find(key);
  if (found == object.end() || found->is_null()) {
    return fallback;
  }
  if (!found->is_string()) {
    fail(origin, std::string("\"") + key + "\" must be a string");
  }
  return found->get<std::string>();
}

int number(const Json& object, const char* key, const std::string& origin, int fallback = 0) {
  const auto found = object.find(key);
  if (found == object.end() || found->is_null()) {
    return fallback;
  }
  if (!found->is_number()) {
    fail(origin, std::string("\"") + key + "\" must be a number");
  }
  return static_cast<int>(found->get<double>());
}

bool flag(const Json& object, const char* key, bool fallback = false) {
  const auto found = object.find(key);
  if (found == object.end() || found->is_null() || !found->is_boolean()) {
    return fallback;
  }
  return found->get<bool>();
}

/// Settings the client can actually store. Everything else that appears in `payload.setting` in
/// the shipped data - `mints`, `sprouts`, `event_energy` - is a resource counter in the original
/// economy, not a preference. Storing those in `Progress::settings` would invent an inventory and
/// hand it a name it does not have, so they are listed as undeliverable instead.
bool isSwitchSetting(const std::string& name) {
  return name == "muted" || name == "music" || name == "sfx" || name == "volume";
}

/// Turns one row's `payload` object into the grant list. All-or-nothing: every key must be
/// understood, otherwise the row is refused with the unknown keys named. `amount`, `color` and
/// `value` are modifiers of `setting` and are not payload kinds of their own.
void buildGrants(const Json& payload, ShopItem& item) {
  for (const auto& [key, value] : payload.items()) {
    if (key == "amount" || key == "color" || key == "value") {
      continue;
    }
    if (key == "plant_id" || key == "costume_id" || key == "world_key") {
      if (value.is_string() && !value.get<std::string>().empty()) {
        const GrantKind kind = key == "plant_id"    ? GrantKind::seed
                               : key == "costume_id" ? GrantKind::costume
                                                     : GrantKind::key;
        item.grants.push_back(Grant{kind, value.get<std::string>(), Json()});
      } else {
        item.undeliverable.push_back(key);
      }
      continue;
    }
    if (key == "coins" || key == "gems" || key == "plantfood_slots") {
      if (value.is_number() && value.get<double>() > 0.0) {
        const GrantKind kind = key == "coins"            ? GrantKind::coins
                               : key == "gems"           ? GrantKind::gems
                                                         : GrantKind::plantfood_slots;
        item.grants.push_back(Grant{kind, {}, value});
      } else {
        item.undeliverable.push_back(key);
      }
      continue;
    }
    if (key == "plantfood_refresh") {
      if (value.is_number() && value.get<double>() > 0.0) {
        item.grants.push_back(Grant{GrantKind::plantfood_refresh, {}, Json()});
      } else {
        item.undeliverable.push_back(key);
      }
      continue;
    }
    if (key == "setting") {
      const std::string name = value.is_string() ? value.get<std::string>() : std::string();
      const auto raw = payload.find("value");
      const bool shaped = raw == payload.end() || raw->is_boolean() || raw->is_number();
      if (!name.empty() && isSwitchSetting(name) && shaped) {
        Grant grant{GrantKind::setting, name, Json()};
        // A switch with no explicit value means "on"; `{"setting":"muted","value":false}` means
        // off, and a number keeps its own value so `volume` survives intact.
        grant.value = raw == payload.end() ? Json(true) : *raw;
        item.grants.push_back(std::move(grant));
      } else {
        item.undeliverable.push_back(key);
      }
      continue;
    }
    // seed_pack, mint, sun_shovel, sun_start_bonus, seed_slots, mower_charges, collectible and
    // anything the sheets add later: no destination, so the whole row is unsellable.
    item.undeliverable.push_back(key);
  }
  item.payloadModelled = !item.grants.empty() && item.undeliverable.empty();
}

}  // namespace

UnlockKind unlockKindOf(const std::string& text) {
  if (text == "none") return UnlockKind::none;
  if (text == "coins") return UnlockKind::coins;
  if (text == "world") return UnlockKind::world;
  if (text == "mixed") return UnlockKind::mixed;
  if (text == "stars") return UnlockKind::stars;
  return UnlockKind::unknown;
}

const char* unlockKindName(UnlockKind kind) {
  switch (kind) {
    case UnlockKind::none: return "none";
    case UnlockKind::coins: return "coins";
    case UnlockKind::world: return "world";
    case UnlockKind::mixed: return "mixed";
    case UnlockKind::stars: return "stars";
    case UnlockKind::unknown: return "unknown";
  }
  return "unknown";
}

const char* grantKindName(GrantKind kind) {
  switch (kind) {
    case GrantKind::seed: return "seed";
    case GrantKind::costume: return "costume";
    case GrantKind::key: return "world_key";
    case GrantKind::coins: return "coins";
    case GrantKind::gems: return "gems";
    case GrantKind::plantfood_slots: return "plantfood_slots";
    case GrantKind::plantfood_refresh: return "plantfood_refresh";
    case GrantKind::setting: return "setting";
  }
  return "unknown";
}

Shop Shop::load(const std::filesystem::path& contentDir,
                const std::filesystem::path& unlockFile) {
  const std::filesystem::path shopPath = contentDir / "shop.json";
  return parse(readFile(shopPath), shopPath.string(), readFile(unlockFile),
               unlockFile.string());
}

Shop Shop::parse(const std::string& shopText, const std::string& shopOrigin,
                 const std::string& unlockText, const std::string& unlockOrigin) {
  const Json shop = parseJson(shopText, shopOrigin);
  const Json unlocks = parseJson(unlockText, unlockOrigin);

  // id -> unlock record. A row that the compiled table never produced stays absent, and the
  // shop row is then counted as `missingRows` instead of being treated as free.
  std::map<std::string, Json> unlockById;
  const Json& unlockItems = member(unlocks, "items", unlockOrigin);
  if (!unlockItems.is_array()) {
    fail(unlockOrigin, "\"items\" must be an array");
  }
  for (const Json& entry : unlockItems) {
    if (!entry.is_object()) {
      fail(unlockOrigin, "every \"items\" entry must be an object");
    }
    unlockById.emplace(text(entry, "id", unlockOrigin), entry);
  }

  const Json& items = member(shop, "items", shopOrigin);
  if (!items.is_array()) {
    fail(shopOrigin, "\"items\" must be an array");
  }

  Shop out;
  // A kind nobody uses must still read as zero, not as an absent key: `.at()` on a missing
  // kind is how the first version of this test crashed instead of reporting "0 star-gated".
  for (const UnlockKind kind : {UnlockKind::none, UnlockKind::coins, UnlockKind::world,
                                UnlockKind::mixed, UnlockKind::stars, UnlockKind::unknown}) {
    out.byUnlock_[kind] = 0;
  }
  out.items_.reserve(items.size());
  std::size_t missing = 0;
  for (const Json& entry : items) {
    if (!entry.is_object()) {
      fail(shopOrigin, "every \"items\" entry must be an object");
    }
    ShopItem item;
    item.id = text(entry, "id", shopOrigin);
    if (item.id.empty()) {
      fail(shopOrigin, "an item has an empty id");
    }
    item.nameZh = text(entry, "name_zh", shopOrigin);
    item.category = text(entry, "category", shopOrigin);
    item.tab = text(entry, "tab", shopOrigin);
    item.itemType = text(entry, "item_type", shopOrigin);
    item.currency = text(entry, "currency", shopOrigin);
    item.price = number(entry, "price", shopOrigin);
    item.implemented = flag(entry, "implemented");
    item.oneTime = flag(entry, "one_time");
    if (const auto payload = entry.find("payload");
        payload != entry.end() && payload->is_object() && !payload->empty()) {
      // nlohmann keeps object keys sorted, so egin() is not the semantic first field:
      // a setting row's payload is {amount, setting, color} and egin() would hand back
      // "amount". Pick the payload identity by an explicit priority list instead.
      static const std::array<const char*, 10> kPayloadKeys = {
          "plant_id", "costume_id", "seed_pack", "setting", "world_key",
          "coins", "gems", "mint", "plantfood_slots", "plantfood_refresh"};
      const Json* chosen = nullptr;
      for (const char* key : kPayloadKeys) {
        if (const auto found = payload->find(key); found != payload->end()) {
          chosen = &*found;
          item.payloadKey = key;
          break;
        }
      }
      if (chosen == nullptr) {
        item.payloadKey = payload->begin().key();
        chosen = &payload->begin().value();
      }
      if (chosen->is_string()) {
        item.payloadValue = chosen->get<std::string>();
      }
      // The priority list above is only for reporting `payloadKey`; delivery is decided by the
      // full key set, so a bundle must pay out everything it advertises or not be sold at all.
      buildGrants(*payload, item);
    } else {
      item.payloadModelled = false;
    }

    if (const auto found = unlockById.find(item.id); found != unlockById.end()) {
      const Json& unlock = found->second;
      if (const auto node = unlock.find("unlock"); node != unlock.end() && node->is_object()) {
        item.unlock = unlockKindOf(text(*node, "kind", unlockOrigin));
        item.unlockCoins = number(*node, "coins", unlockOrigin);
        item.unlockStars = number(*node, "stars", unlockOrigin);
        item.unlockWorld = text(*node, "world", unlockOrigin);
        item.unlockCategory = text(found->second, "category", unlockOrigin);
      } else {
        fail(unlockOrigin, "row \"" + item.id + "\" has no \"unlock\" object");
      }
    } else {
      ++missing;
      item.unlock = UnlockKind::unknown;
    }

    // `free` rows cost nothing; `coin` rows must quote a positive price. Everything else is a
    // currency Progress cannot spend, and saying so is the honest answer.
    const bool spendable = item.currency == "free" || (item.currency == "coin" && item.price > 0);
    const bool freebie = item.currency == "free";
    if (!spendable) {
      ++out.unmodelledCurrency_;
    }
    if (spendable && item.implemented && item.payloadModelled &&
        item.unlock != UnlockKind::stars && item.unlock != UnlockKind::unknown) {
      ++out.buyable_;
    }
    if (freebie && item.price != 0) {
      fail(shopOrigin, "free row \"" + item.id + "\" quotes a non-zero price");
    }

    ++out.byCategory_[item.category];
    ++out.byUnlockCategory_[item.unlockCategory.empty() ? "missing" : item.unlockCategory];
    ++out.byUnlock_[item.unlock];
    ++out.byCurrency_[item.currency];
    out.index_.emplace(item.id, out.items_.size());
    out.items_.push_back(std::move(item));
  }
  out.missingRows_ = missing;
  return out;
}

const ShopItem* Shop::find(const std::string& id) const {
  const auto found = index_.find(id);
  return found == index_.end() ? nullptr : &items_[found->second];
}

bool owns(const Progress& progress, const std::string& itemId) {
  return std::find(progress.purchases.begin(), progress.purchases.end(), itemId) !=
         progress.purchases.end();
}

BuyResult purchase(const Shop& shop, const std::string& itemId, Progress& progress) {
  BuyResult result;
  result.itemId = itemId;
  const ShopItem* item = shop.find(itemId);
  if (item == nullptr) {
    result.reason = "unknown item " + itemId;
    return result;
  }
  // `one_time` rows are the only ones ownership can block. Repeatable rows are not "already
  // owned" by definition (the field was parsed but unread before this fix).
  if (item->oneTime && owns(progress, itemId)) {
    result.reason = "already owned";
    return result;
  }
  if (!item->implemented) {
    result.reason = "not implemented in this client";
    return result;
  }
  if (item->unlock == UnlockKind::stars) {
    result.reason = "star-gated: needs " + std::to_string(item->unlockStars) + " stars";
    return result;
  }
  if (item->unlock == UnlockKind::unknown) {
    result.reason = "unlock kind is unknown for this row";
    return result;
  }
  int cost = 0;
  if (item->currency == "free") {
    cost = 0;
  } else if (item->currency == "coin") {
    if (item->price <= 0) {
      result.reason = "item has no coin price";
      return result;
    }
    cost = item->price;
  } else {
    // Progress tracks coins only. Saying so beats handing out gem rows for free.
    result.reason = "currency " + item->currency + " is not modelled yet";
    return result;
  }
  // Currency comes first: a row we cannot even pay for must say so. Only once the price is
  // payable does "we would take your coins and deliver nothing" become the honest refusal.
  if (!item->payloadModelled) {
    if (item->undeliverable.empty()) {
      result.reason = "row grants nothing this client models";
    } else {
      std::string named;
      for (const std::string& key : item->undeliverable) {
        if (!named.empty()) named += ", ";
        named += key;
      }
      // Naming every unknown key matters for bundles: `{seed_pack, coins}` is refused for the
      // seed pack, and the player should see which half is missing instead of a vague "no".
      result.reason = "payload " + named + " is not modelled yet";
    }
    return result;
  }
  if (progress.coins < cost) {
    result.reason = "not enough coins (need " + std::to_string(cost) + ", have " +
                    std::to_string(progress.coins) + ")";
    return result;
  }

  progress.coins -= cost;
  result.coinsSpent = cost;
  if (!owns(progress, itemId)) {
    progress.purchases.push_back(itemId);
    std::sort(progress.purchases.begin(), progress.purchases.end());
  }
  // Deliver exactly the grants the catalogue parsed, and record each one in the receipt. Every
  // branch writes to a different Progress field, which is what the tests check pairwise
  // (receipt value == save delta) instead of trusting a single success flag.
  for (const Grant& grant : item->grants) {
    switch (grant.kind) {
      case GrantKind::seed:
        if (std::find(progress.seeds.begin(), progress.seeds.end(), grant.text) ==
            progress.seeds.end()) {
          progress.seeds.push_back(grant.text);
          std::sort(progress.seeds.begin(), progress.seeds.end());
        }
        if (result.grantedSeed.empty()) {
          result.grantedSeed = grant.text;
        }
        break;
      case GrantKind::costume:
        if (std::find(progress.costumes.begin(), progress.costumes.end(), grant.text) ==
            progress.costumes.end()) {
          progress.costumes.push_back(grant.text);
          std::sort(progress.costumes.begin(), progress.costumes.end());
        }
        break;
      case GrantKind::key:
        ++progress.keys;
        break;
      case GrantKind::coins:
        progress.coins += static_cast<int>(std::llround(grant.number()));
        break;
      case GrantKind::gems:
        progress.gems += static_cast<int>(std::llround(grant.number()));
        break;
      case GrantKind::plantfood_slots:
        progress.plantfoodSlots += static_cast<int>(std::llround(grant.number()));
        break;
      case GrantKind::plantfood_refresh:
        progress.plantfoodRefresh = true;
        break;
      case GrantKind::setting:
        progress.settings[grant.text] = grant.value;
        break;
    }
    result.granted.push_back(grant);
  }
  result.ok = true;
  return result;
}

}  // namespace pvz
