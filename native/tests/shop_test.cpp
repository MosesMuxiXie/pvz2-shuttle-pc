// Shop catalogue + the purchase rule. Four things this test exists to prevent:
//   1. a row priced in gems/mints being handed out for free,
//   2. a refused purchase spending coins or recording ownership,
//   3. a row taking coins and delivering nothing (or only half of a bundle), and
//   4. a payload landing in the wrong field - costumes used to be pushed into `Progress::seeds`
//      because `purchase()` wrote `payloadValue` into seeds unconditionally.
//
// Every delivery section asserts three things at once: the wallet moved, the save field moved by
// exactly the receipt amount, and the receipt names the grant. The reverse probes in the report
// delete one `case` from `purchase()` and show the matching section going red.

#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "progress.hpp"
#include "shop.hpp"

namespace fs = std::filesystem;
using namespace pvz;

namespace {

void check(bool ok, const std::string& message) {
  if (!ok) {
    throw std::runtime_error("shop test failed: " + message);
  }
}

fs::path gContent;
fs::path gUnlock;
fs::path gTemp;

const ShopItem& pick(const Shop& shop, const std::string& id) {
  const ShopItem* item = shop.find(id);
  check(item != nullptr, "catalogue must contain " + id);
  return *item;
}

const Grant* findGrant(const BuyResult& result, GrantKind kind) {
  for (const Grant& grant : result.granted) {
    if (grant.kind == kind) return &grant;
  }
  return nullptr;
}

/// One-row catalogue for the shapes the shipped data does not contain (a coin-priced coin
/// bundle, a switch setting, a half-unknown bundle). The payload is spliced verbatim so each
/// section can spell the exact JSON it is testing. `currency` defaults to the row's honest
/// wallet: a 0-price row is a `free` row, because `coin` with price 0 is not buyable at all.
Shop inlineShop(const std::string& payload, const std::string& unlockKind = "none",
                int price = 100, bool oneTime = false, bool implemented = true,
                const std::string& currency = "") {
  const std::string money = currency.empty() ? (price == 0 ? "free" : "coin") : currency;
  const std::string shopText =
      R"({"items":[{"id":"row","name_zh":"row","category":"items","tab":"items",)"
      R"("item_type":"probe","currency":")" + money +
      R"(","price":)" + std::to_string(price) + R"(,"implemented":)" +
      (implemented ? "true" : "false") + R"(,"one_time":)" + (oneTime ? "true" : "false") +
      R"(,"payload":)" + payload + "}]}";
  const std::string unlockText = R"({"items":[{"id":"row","category":"items",)"
                                 R"("unlock":{"kind":")" +
                                 unlockKind + R"(","coins":null,"stars":null,"world":null}}]})";
  return Shop::parse(shopText, "inline-shop", unlockText, "inline-unlock");
}

void testCatalogueCounts() {
  const Shop shop = Shop::load(gContent, gUnlock);
  check(shop.size() == 585, "the shipped catalogue has 585 rows, got " +
                                std::to_string(shop.size()));
  check(shop.byCategory().at("items") == 459, "items rows must be 459");
  check(shop.byCategory().at("seeds") == 81, "seeds rows must be 81");
  check(shop.byCategory().at("bundles") == 25, "bundles rows must be 25");
  check(shop.byCategory().at("currency") == 20, "currency rows must be 20");
  check(shop.byCurrency().at("gem") == 469, "gem rows must be 469");
  check(shop.byCurrency().at("coin") == 100, "coin rows must be 100");
  check(shop.byCurrency().at("mint") == 10, "mint rows must be 10");
  check(shop.byCurrency().at("free") == 6, "free rows must be 6");
  check(shop.byUnlock().at(UnlockKind::none) == 484, "484 rows carry no gate");
  check(shop.byUnlock().at(UnlockKind::coins) == 99, "99 rows are coin-gated");
  check(shop.byUnlock().at(UnlockKind::world) == 1, "exactly one row is world-attached");
  check(shop.byUnlock().at(UnlockKind::stars) == 0, "no shipped row is star-gated");
  check(shop.missingRows() == 0, "every shop row must have an unlock record");
  // Gem and mint prices are still refused: `Progress` can hold gems now, but no row may *spend*
  // them until a sink and a price policy exist. So this counter keeps its old meaning.
  check(shop.unmodelledCurrency() == 479, "479 rows are priced in a currency we cannot spend");
  check(shop.byUnlockCategory().at("costume") == 447, "447 rows are costumes");

  // buyable = implemented + spendable + every payload key modellable. The breakdown below is the
  // data fact this task changed: 21 seed rows alone used to be the whole list.
  check(shop.buyable() == 72, "72 rows are buyable now, got " + std::to_string(shop.buyable()));
  std::size_t seeds = 0;
  std::size_t costumes = 0;
  std::size_t keys = 0;
  std::size_t slots = 0;
  std::size_t refresh = 0;
  std::size_t gems = 0;
  std::size_t refusedBundles = 0;
  for (const ShopItem& item : shop.items()) {
    if (!item.payloadModelled) {
      if (!item.undeliverable.empty() && item.currency == "coin" && item.implemented) {
        ++refusedBundles;
      }
      continue;
    }
    if (item.currency != "coin" && item.currency != "free") continue;
    if (!item.implemented) continue;
    if (item.unlock == UnlockKind::stars || item.unlock == UnlockKind::unknown) continue;
    for (const Grant& grant : item.grants) {
      switch (grant.kind) {
        case GrantKind::seed: ++seeds; break;
        case GrantKind::costume: ++costumes; break;
        case GrantKind::key: ++keys; break;
        case GrantKind::plantfood_slots: ++slots; break;
        case GrantKind::plantfood_refresh: ++refresh; break;
        case GrantKind::gems: ++gems; break;
        case GrantKind::setting: break;
        case GrantKind::coins: break;
      }
    }
  }
  check(seeds == 21, "21 seed rows are buyable, got " + std::to_string(seeds));
  check(costumes == 45, "45 costume rows are buyable, got " + std::to_string(costumes));
  check(keys == 1, "1 world-key row is buyable, got " + std::to_string(keys));
  check(slots == 2, "2 plant-food slot rows are buyable, got " + std::to_string(slots));
  check(refresh == 1, "1 plant-food refresh row is buyable, got " + std::to_string(refresh));
  check(gems == 2, "2 gem bundle rows are buyable, got " + std::to_string(gems));
  check(seeds + costumes + keys + slots + refresh + gems == shop.buyable(),
        "the per-kind breakdown must add up to buyable()");
  check(refusedBundles == 15,
        "15 implemented coin-priced rows are refused for an undeliverable payload, got " +
            std::to_string(refusedBundles));
  std::cout << "catalogue rows=" << shop.size() << " buyable=" << shop.buyable()
            << " unmodelledCurrency=" << shop.unmodelledCurrency() << " seeds=" << seeds
            << " costumes=" << costumes << " keys=" << keys << " slots=" << slots
            << " refresh=" << refresh << " gems=" << gems << "\n";
}

void testKnownRows() {
  const Shop shop = Shop::load(gContent, gUnlock);
  const ShopItem& seed = pick(shop, "seed_iris");
  check(seed.currency == "coin", "seed_iris is priced in coins");
  check(seed.price == 500, "seed_iris costs 500 coins, got " + std::to_string(seed.price));
  // The seed rows are the coin-gated ones: `unlock.coins` repeats the price, which is how the
  // compiled table says "this is what the coins buy" rather than "this costs something".
  check(seed.unlock == UnlockKind::coins, "seed_iris is coin-gated");
  check(seed.unlockCoins == 500, "seed_iris unlock.coins must match its price, got " +
                                     std::to_string(seed.unlockCoins));
  check(seed.payloadKey == "plant_id", "seed_iris points at a plant id");
  check(seed.category == "seeds", "seed_iris lives in the seeds category");
  check(seed.grants.size() == 1 && seed.grants.front().kind == GrantKind::seed,
        "seed_iris must parse exactly one seed grant");

  const ShopItem& costume = pick(shop, "obb_Tonywrite.Costume.1");
  check(costume.currency == "gem", "the sample costume is priced in gems");
  check(costume.unlock == UnlockKind::none, "no gate, but an unmodelled currency");
  check(costume.payloadModelled, "a costume row must be modelled even when it is gem-priced");

  const ShopItem& key = pick(shop, "obb_worldkey.rainbowmarket");
  check(key.currency == "coin" && key.price == 2026,
        "the world key costs 2026 coins, got " + std::to_string(key.price));
  check(key.oneTime, "the world key is a one_time row");
  check(key.grants.size() == 1 && key.grants.front().kind == GrantKind::key &&
            key.grants.front().text == "rainbowmarket",
        "the world key row must grant rainbowmarket");
}

void testPurchaseSpendsCoins() {
  const Shop shop = Shop::load(gContent, gUnlock);
  Progress progress;
  progress.coins = 1200;

  const BuyResult ok = purchase(shop, "seed_iris", progress);
  check(ok.ok, "buying seed_iris must succeed: " + ok.reason);
  check(ok.coinsSpent == 500, "500 coins must be spent");
  check(progress.coins == 700, "coins must drop to 700, got " + std::to_string(progress.coins));
  check(owns(progress, "seed_iris"), "the purchase must be recorded");

  const BuyResult again = purchase(shop, "seed_iris", progress);
  check(!again.ok && again.reason == "already owned",
        "a second purchase must be refused as already owned, got " + again.reason);
  check(progress.coins == 700, "a refused purchase must not spend coins");
  check(again.granted.empty(), "a refused purchase must return an empty receipt");
}

void testFreeRowCostsNothing() {
  const Shop shop = Shop::load(gContent, gUnlock);
  // The shipped free rows that are implemented are costumes: `obb_Tonywrite.Costume.370` must be
  // claimable for 0 coins and land in `Progress::costumes`.
  const ShopItem& free = pick(shop, "obb_Tonywrite.Costume.370");
  check(free.currency == "free" && free.price == 0, "the sample row must be free");
  Progress progress;
  const BuyResult claimed = purchase(shop, "obb_Tonywrite.Costume.370", progress);
  check(claimed.ok, "a free implemented row must be claimable: " + claimed.reason);
  check(claimed.coinsSpent == 0, "a free row must cost nothing");
  check(progress.coins == 0, "a free row must not touch the balance");
  check(progress.costumes.size() == 1 && progress.costumes.front() == "370",
        "the free costume must land in Progress::costumes");
  const Grant* grant = findGrant(claimed, GrantKind::costume);
  check(grant != nullptr && grant->text == "370", "the receipt must name the costume");

  // A free row that is *not* implemented still has to be refused with a reason.
  std::string unimplementedFree;
  for (const ShopItem& item : shop.items()) {
    if (item.currency == "free" && !item.implemented) {
      unimplementedFree = item.id;
      break;
    }
  }
  check(!unimplementedFree.empty(), "the catalogue ships unimplemented free rows");
  Progress blocked;
  const BuyResult refused = purchase(shop, unimplementedFree, blocked);
  check(!refused.ok, "an unimplemented free row must still be refused");
  check(refused.reason == "not implemented in this client",
        "the refusal must name implementation, got " + refused.reason);
  check(blocked.purchases.empty(), "a refused row must not be recorded");

  // And the zero-price path itself on an inline row. `coin` with price 0 is not a free row in
  // this catalogue's grammar - the currency column says which wallet pays - so the row is
  // spelled `free` exactly like the shipped ones.
  const Shop inline_shop =
      inlineShop(R"({"plant_id":"sunflower"})", "none", 0, false, true, "free");
  Progress free_progress;
  const BuyResult row = purchase(inline_shop, "row", free_progress);
  check(row.ok, "a free implemented row must be claimable: " + row.reason);
  check(row.grantedSeed == "sunflower", "a free claim must still deliver its payload");
}

void testGemRowIsRefused() {
  const Shop shop = Shop::load(gContent, gUnlock);
  Progress progress;
  progress.coins = 100000;
  progress.gems = 1000000;
  const BuyResult result = purchase(shop, "obb_Tonywrite.Costume.1", progress);
  check(!result.ok, "a gem-priced row must not be buyable");
  check(result.reason.find("gem") != std::string::npos,
        "the refusal must name the currency, got " + result.reason);
  check(progress.coins == 100000, "a refused purchase must not spend coins");
  check(progress.gems == 1000000, "a refused purchase must not spend gems either");
  check(!owns(progress, "obb_Tonywrite.Costume.1"), "a refused purchase must not be recorded");
}

void testSeedPayloadIsDeliveredOnce() {
  const Shop shop = Shop::load(gContent, gUnlock);
  Progress progress;
  progress.coins = 5000;
  const BuyResult first = purchase(shop, "seed_iris", progress);
  check(first.ok, "buying seed_iris must succeed: " + first.reason);
  check(first.grantedSeed == "iris",
        "the purchase must name the granted seed, got " + first.grantedSeed);
  check(progress.seeds.size() == 1 && progress.seeds.front() == "iris",
        "Progress::seeds must hold the granted seed");
  check(progress.coins == 4500, "500 coins must be spent");
  const Grant* grant = findGrant(first, GrantKind::seed);
  check(grant != nullptr && grant->text == "iris", "the receipt must name the seed");

  // seed_iris is one_time, so a second attempt is refused by ownership, not by the wallet.
  const BuyResult again = purchase(shop, "seed_iris", progress);
  check(!again.ok, "a one_time row must not be sold twice");
  check(again.reason == "already owned", "the refusal must name ownership, got " + again.reason);
  check(progress.seeds.size() == 1, "a refused repeat must not duplicate the seed");
}

void testCoinsPayloadIsCredited() {
  // No shipped row can reach this branch: both `payload.coins` rows are gem-priced and gem
  // prices are refused. The inline row therefore carries the whole contract for the kind.
  const Shop shop = inlineShop(R"({"coins":250})", "none", 100);
  Progress progress;
  progress.coins = 1000;
  const BuyResult result = purchase(shop, "row", progress);
  check(result.ok, "a coin bundle must be buyable: " + result.reason);
  check(result.coinsSpent == 100, "the price must be charged, got " +
                                      std::to_string(result.coinsSpent));
  check(progress.coins == 1150,
        "1000 - 100 + 250 must leave 1150, got " + std::to_string(progress.coins));
  const Grant* grant = findGrant(result, GrantKind::coins);
  check(grant != nullptr && grant->number() == 250.0, "the receipt must carry the 250 coins");
  check(grant->number() == 250.0, "the receipt amount must match the credit");

  // The shipped coin bundles exist but are gem-priced: they must still be refused, and the
  // refusal must be about the currency, not about the payload.
  const Shop shipped = Shop::load(gContent, gUnlock);
  Progress wallet;
  wallet.coins = 100000;
  const BuyResult gemPriced = purchase(shipped, "obb_com.popcap.pvz2.coins.3000.consume", wallet);
  check(!gemPriced.ok, "a gem-priced coin bundle must not be sold for coins");
  check(gemPriced.reason.find("gem") != std::string::npos,
        "the refusal must name the currency first, got " + gemPriced.reason);
  check(wallet.coins == 100000, "the refused bundle must not move the wallet");
}

void testGemsPayloadIsCredited() {
  const Shop shop = Shop::load(gContent, gUnlock);
  Progress progress;
  progress.coins = 4000;
  const BuyResult result = purchase(shop, "obb_com.popcap.pvz2.gems.1.consume", progress);
  check(result.ok, "the coin-priced gem bundle must be buyable: " + result.reason);
  check(progress.coins == 1000,
        "3000 coins must be spent, got " + std::to_string(progress.coins));
  check(progress.gems == 1, "1 gem must be credited, got " + std::to_string(progress.gems));
  const Grant* grant = findGrant(result, GrantKind::gems);
  check(grant != nullptr && grant->number() == 1.0, "the receipt must carry the gem count");
  check(owns(progress, "obb_com.popcap.pvz2.gems.1.consume"),
        "a purchased row must be recorded");
}

void testWorldKeyIsGrantedOnce() {
  const Shop shop = Shop::load(gContent, gUnlock);
  Progress progress;
  progress.coins = 5000;
  const BuyResult first = purchase(shop, "obb_worldkey.rainbowmarket", progress);
  check(first.ok, "the world key must be buyable: " + first.reason);
  check(progress.keys == 1, "exactly one key must be granted, got " +
                                std::to_string(progress.keys));
  check(progress.coins == 5000 - 2026, "2026 coins must be spent");
  const Grant* grant = findGrant(first, GrantKind::key);
  check(grant != nullptr && grant->text == "rainbowmarket",
        "the receipt must name the world the key opens");

  const BuyResult again = purchase(shop, "obb_worldkey.rainbowmarket", progress);
  check(!again.ok && again.reason == "already owned",
        "the one_time key must not be sold twice, got " + again.reason);
  check(progress.keys == 1, "a refused repeat must not grant a second key");
  check(progress.coins == 5000 - 2026, "a refused repeat must not charge again");
}

void testPlantfoodUpgrades() {
  const Shop shop = Shop::load(gContent, gUnlock);
  Progress progress;
  progress.coins = 50000;
  const BuyResult first = purchase(shop, "obb_com.popcap.pvz2.gameupgrade.pfslot.nonconsume.t1",
                                   progress);
  check(first.ok, "the first slot upgrade must be buyable: " + first.reason);
  check(progress.plantfoodSlots == 1, "one slot must be added");
  const BuyResult second = purchase(shop, "obb_com.popcap.pvz2.gameupgrade.pfslot2.nonconsume.t1",
                                    progress);
  check(second.ok, "the second slot upgrade must be buyable: " + second.reason);
  check(progress.plantfoodSlots == 2,
        "two different rows must stack to 2 slots, got " +
            std::to_string(progress.plantfoodSlots));
  check(progress.coins == 50000 - 2 * 15000, "both upgrades must be charged");
  const Grant* slotGrant = findGrant(second, GrantKind::plantfood_slots);
  check(slotGrant != nullptr && slotGrant->number() == 1.0,
        "the receipt must carry the slot count");

  const BuyResult refresh =
      purchase(shop, "obb_com.popcap.pvz2.gameupgrade.pfrefresh.nonconsume.t1", progress);
  check(refresh.ok, "the refresh upgrade must be buyable: " + refresh.reason);
  check(progress.plantfoodRefresh, "the refresh upgrade must set the flag");
  check(findGrant(refresh, GrantKind::plantfood_refresh) != nullptr,
        "the receipt must name the refresh grant");
  check(progress.plantfoodSlots == 2, "the refresh must not touch the slot count");
}

void testCostumeIsRecordedOnce() {
  const Shop shop = Shop::load(gContent, gUnlock);
  Progress progress;
  progress.coins = 600;
  const BuyResult result = purchase(shop, "obb_com.pvz2.costume.272", progress);
  check(result.ok, "a coin-priced costume must be buyable: " + result.reason);
  check(progress.coins == 100, "500 coins must be spent, got " + std::to_string(progress.coins));
  check(progress.costumes.size() == 1 && progress.costumes.front() == "272",
        "the costume id must land in Progress::costumes");
  const Grant* grant = findGrant(result, GrantKind::costume);
  check(grant != nullptr && grant->text == "272", "the receipt must name the costume");
  check(progress.seeds.empty(),
        "a costume must never be written into Progress::seeds (the old bug)");

  const BuyResult again = purchase(shop, "obb_com.pvz2.costume.272", progress);
  check(!again.ok && again.reason == "already owned",
        "a one_time costume must not be sold twice, got " + again.reason);
  check(progress.costumes.size() == 1, "a refused repeat must not duplicate the costume");
}

void testCostumeListStaysSortedAndUnique() {
  // Two rows pointing at the same costume id: the list is a set, so the id appears once.
  // Built with the JSON writer rather than a raw literal - hand-writing nested quotes here is how
  // the first draft grew a stray `)` and made `Shop::parse` fail on its own fixture.
  Json items = Json::array();
  for (const char* id : {"a", "b"}) {
    Json row;
    row["id"] = id;
    row["name_zh"] = "x";
    row["category"] = "items";
    row["tab"] = "items";
    row["item_type"] = "costume";
    row["currency"] = "coin";
    row["price"] = 10;
    row["implemented"] = true;
    row["one_time"] = false;
    row["payload"]["costume_id"] = "900";
    items.push_back(row);
  }
  Json shop_json;
  shop_json["items"] = items;
  Json unlock_row;
  unlock_row["id"] = "a";
  unlock_row["category"] = "items";
  unlock_row["unlock"] = {{"kind", "none"}, {"coins", nullptr}, {"stars", nullptr}, {"world", nullptr}};
  Json unlock_second = unlock_row;
  unlock_second["id"] = "b";
  Json unlock_json;
  unlock_json["items"] = Json::array({unlock_row, unlock_second});
  const Shop shop = Shop::parse(shop_json.dump(), "inline-shop", unlock_json.dump(),
                                "inline-unlock");
  Progress progress;
  progress.coins = 100;
  check(purchase(shop, "a", progress).ok, "the first costume must be granted");
  check(purchase(shop, "b", progress).ok, "the second row must also be granted");
  check(progress.costumes.size() == 1, "the costume list must stay unique, got " +
                                           std::to_string(progress.costumes.size()));
  check(progress.coins == 80, "both rows must still be charged");
}

void testSettingSwitchIsStored() {
  const Shop muted = inlineShop(R"({"setting":"muted"})", "none", 0);
  Progress progress;
  const BuyResult result = purchase(muted, "row", progress);
  check(result.ok, "a switch setting must be buyable: " + result.reason);
  check(progress.settings.count("muted") == 1, "the switch must be stored by name");
  check(progress.settings.at("muted") == true, "a switch without a value means on");
  const Grant* grant = findGrant(result, GrantKind::setting);
  check(grant != nullptr && grant->text == "muted" && grant->value == true,
        "the receipt must carry the setting name and value");

  const Shop volume = inlineShop(R"({"setting":"volume","value":0.5})", "none", 0);
  Progress level;
  const BuyResult stored = purchase(volume, "row", level);
  check(stored.ok, "a numeric setting must be buyable: " + stored.reason);
  check(level.settings.at("volume") == 0.5, "the numeric value must survive as a number");

  const Shop off = inlineShop(R"({"setting":"sfx","value":false})", "none", 0);
  Progress quiet;
  check(purchase(off, "row", quiet).ok, "an explicit false must be buyable");
  check(quiet.settings.at("sfx") == false, "an explicit false must be stored, not dropped");
}

void testSettingResourceCounterIsRefused() {
  const Shop shop = Shop::load(gContent, gUnlock);
  const ShopItem& mints = pick(shop, "obb_com.popcap.pvz2.mints.1.consume");
  check(mints.payloadKey == "setting", "the mints row is a setting row");
  check(!mints.payloadModelled, "a resource-counter setting must not be modelled");
  check(!mints.undeliverable.empty() && mints.undeliverable.front() == "setting",
        "the row must name `setting` as the undeliverable key");

  Progress progress;
  progress.coins = 100000;
  const BuyResult result = purchase(shop, "obb_com.popcap.pvz2.mints.1.consume", progress);
  check(!result.ok, "a mints row must not be sold");
  check(result.reason == "payload setting is not modelled yet",
        "the refusal must name the payload, got " + result.reason);
  check(progress.coins == 100000, "a refused setting must not spend coins");
  check(progress.settings.empty(), "a refused setting must not reach the save");
}

void testBundleWithUnknownHalfIsRefused() {
  // A bundle that pays out coins but not its seed pack is worse than a refusal: the row is
  // refused as a whole and both halves are untouched.
  const Shop bundle = inlineShop(R"({"seed_pack":1,"coins":1000})", "none", 100);
  Progress progress;
  progress.coins = 5000;
  const BuyResult result = purchase(bundle, "row", progress);
  check(!result.ok, "a half-modelled bundle must not be sold");
  check(result.reason == "payload seed_pack is not modelled yet",
        "the refusal must name the undeliverable half, got " + result.reason);
  check(progress.coins == 5000, "the refused bundle must not move the wallet");
  check(progress.seeds.empty(), "the refused bundle must not grant a seed");

  // The shipped row of exactly this shape is gem-priced, so it is refused on currency first.
  const Shop shop = Shop::load(gContent, gUnlock);
  const ShopItem& starreed = pick(shop, "obb_com.pvz2.bundle.starreed");
  check(starreed.undeliverable.size() == 1 && starreed.undeliverable.front() == "seed_pack",
        "starreed must be refused for its seed pack");
  Progress wallet;
  wallet.coins = 1000000;
  const BuyResult refused = purchase(shop, "obb_com.pvz2.bundle.starreed", wallet);
  check(!refused.ok, "the gem-priced bundle must be refused");
  check(refused.reason.find("gem") != std::string::npos,
        "the currency refusal must come first, got " + refused.reason);
}

void testUnknownPayloadKindsAreRefused() {
  const std::vector<std::string> payloads = {
      R"({"sun_shovel":1})", R"({"seed_slots":1})", R"({"mower_charges":1})",
      R"({"collectible":"x"})", R"({"sun_start_bonus":25})", R"({"mint":10})"};
  for (const std::string& payload : payloads) {
    const Shop shop = inlineShop(payload);
    Progress progress;
    progress.coins = 1000;
    const BuyResult result = purchase(shop, "row", progress);
    check(!result.ok, "payload " + payload + " must not be sold");
    check(result.reason.find("is not modelled yet") != std::string::npos,
          "the refusal must name the payload, got " + result.reason);
    check(progress.coins == 1000, "a refused payload must not spend coins");
    check(progress.purchases.empty(), "a refused payload must not be recorded");
  }
}

void testWalletGateRunsBeforePayload() {
  // A row that is modelled but unaffordable must report the wallet, not the payload: the order
  // of the two checks is what makes the reason actionable.
  const Shop shop = inlineShop(R"({"coins":50})", "none", 500);
  Progress progress;
  progress.coins = 10;
  const BuyResult result = purchase(shop, "row", progress);
  check(!result.ok, "an unaffordable row must be refused");
  check(result.reason.find("not enough coins") != std::string::npos,
        "the refusal must be about the wallet, got " + result.reason);
  check(result.reason.find("payload") == std::string::npos,
        "an unaffordable modelled row must not be reported as an unmodelled payload");
  check(progress.coins == 10, "the refusal must not touch the wallet");
  check(result.granted.empty(), "an unaffordable row must return an empty receipt");
  check(progress.purchases.empty(), "an unaffordable row must not be recorded");
}

void testReceiptMatchesSaveDelta() {
  // One purchase per kind, each checked as delta == receipt. This is the invariant that makes
  // "the receipt says we granted something" mean "the save actually moved".
  const Shop shop = Shop::load(gContent, gUnlock);
  Progress progress;
  progress.coins = 100000;
  const std::vector<std::pair<std::string, GrantKind>> rows = {
      {"seed_iris", GrantKind::seed},
      {"obb_com.pvz2.costume.272", GrantKind::costume},
      {"obb_worldkey.rainbowmarket", GrantKind::key},
      {"obb_com.popcap.pvz2.gems.1.consume", GrantKind::gems},
      {"obb_com.popcap.pvz2.gameupgrade.pfslot.nonconsume.t1", GrantKind::plantfood_slots},
      {"obb_com.popcap.pvz2.gameupgrade.pfrefresh.nonconsume.t1", GrantKind::plantfood_refresh},
  };
  const int coinsStart = progress.coins;
  const int gemsStart = progress.gems;
  const std::size_t seedsStart = progress.seeds.size();
  const std::size_t costumesStart = progress.costumes.size();
  const std::size_t slotsStart = static_cast<std::size_t>(progress.plantfoodSlots);
  int keysStart = progress.keys;
  int spent = 0;
  for (const auto& [id, kind] : rows) {
    const BuyResult result = purchase(shop, id, progress);
    check(result.ok, "receipt probe: " + id + " must be buyable: " + result.reason);
    check(result.granted.size() == 1, "receipt probe: " + id + " must return one grant");
    check(result.granted.front().kind == kind, "receipt probe: " + id + " kind mismatch");
    spent += result.coinsSpent;
  }
  check(progress.coins == coinsStart - spent, "the wallet must equal start minus spent");
  check(progress.gems == gemsStart + 1, "gems must move by the receipt amount (1)");
  check(progress.seeds.size() == seedsStart + 1, "seeds must move by 1");
  check(progress.costumes.size() == costumesStart + 1, "costumes must move by 1");
  check(progress.keys == keysStart + 1, "keys must move by 1");
  check(progress.plantfoodSlots == static_cast<int>(slotsStart) + 1, "slots must move by 1");
  check(progress.plantfoodRefresh, "the refresh grant must be visible in the save");
}

void testGrantsSurviveSaveRoundTrip() {
  const Shop shop = Shop::load(gContent, gUnlock);
  Progress progress;
  progress.coins = 100000;
  check(purchase(shop, "obb_worldkey.rainbowmarket", progress).ok, "key purchase");
  check(purchase(shop, "obb_com.pvz2.costume.272", progress).ok, "costume purchase");
  check(purchase(shop, "obb_com.popcap.pvz2.gems.1.consume", progress).ok, "gem purchase");
  check(purchase(shop, "obb_com.popcap.pvz2.gameupgrade.pfslot.nonconsume.t1", progress).ok,
        "slot purchase");
  check(purchase(shop, "obb_com.popcap.pvz2.gameupgrade.pfrefresh.nonconsume.t1", progress).ok,
        "refresh purchase");
  const Shop switchShop = inlineShop(R"({"setting":"muted"})", "none", 0);
  check(purchase(switchShop, "row", progress).ok, "switch purchase");

  const fs::path save = gTemp / "shop-roundtrip" / "save.json";
  fs::create_directories(save.parent_path());
  saveProgress(save, progress, 0);
  const Progress reloaded = loadProgress(save);
  check(reloaded.keys == 1, "keys must survive the round trip");
  check(reloaded.gems == 1, "gems must survive the round trip");
  check(reloaded.costumes.size() == 1 && reloaded.costumes.front() == "272",
        "costumes must survive the round trip");
  check(reloaded.plantfoodSlots == 1, "plant food slots must survive the round trip");
  check(reloaded.plantfoodRefresh, "the refresh flag must survive the round trip");
  check(reloaded.settings.count("muted") == 1 && reloaded.settings.at("muted") == true,
        "switch settings must survive the round trip");
  check(reloaded.coins == progress.coins, "the wallet must survive the round trip");
  check(reloaded.purchases.size() == 6, "every purchase must be recorded, got " +
                                            std::to_string(reloaded.purchases.size()));

  // A save that never bought a shop row must not grow the new keys: the five fields are only
  // written when they differ from their default.
  Progress pristine;
  pristine.coins = 10;
  const fs::path plain = gTemp / "shop-roundtrip" / "pristine.json";
  saveProgress(plain, pristine, 0);
  const std::string text = [&] {
    std::ifstream in(plain, std::ios::binary);
    return std::string((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
  }();
  for (const char* key : {"\"gems\"", "\"costumes\"", "\"settings\"", "\"plantfoodSlots\"",
                          "\"plantfoodRefresh\""}) {
    check(text.find(key) == std::string::npos,
          std::string("a pristine save must not carry ") + key);
  }
}

void testRepeatableRowIsNotAlreadyOwned() {
  // `one_time=false` rows used to report "already owned" after the first purchase because the
  // flag was parsed and never read. A repeatable seed row pins the rule.
  const Shop shop = inlineShop(R"({"plant_id":"peashooter"})", "none", 100, false);
  Progress progress;
  progress.coins = 250;
  check(purchase(shop, "row", progress).ok, "the first purchase must succeed");
  const BuyResult second = purchase(shop, "row", progress);
  check(second.ok, "a repeatable row must be buyable twice: " + second.reason);
  check(progress.coins == 50,
        "both purchases must be charged, got " + std::to_string(progress.coins));
  check(progress.purchases.size() == 1, "the ownership list must stay a set");
  check(progress.seeds.size() == 1, "the seed must not be duplicated");
}

void testNotEnoughCoins() {
  const Shop shop = Shop::load(gContent, gUnlock);
  Progress progress;
  progress.coins = 10;
  const BuyResult result = purchase(shop, "seed_iris", progress);
  check(!result.ok, "10 coins cannot buy a 500-coin seed");
  check(result.reason.find("not enough coins") != std::string::npos,
        "the refusal must say how much is missing, got " + result.reason);
  check(result.granted.empty(), "an unaffordable row must return an empty receipt");
}

void testWorldRowNeverMintsAKey() {
  // The one `unlock.kind == world` row is a gem-priced pinata bundle for Egypt, *not* the world
  // key: a key is granted only by a `payload.world_key` row, and this row has none.
  const Shop shop = Shop::load(gContent, gUnlock);
  std::string worldRow;
  for (const ShopItem& item : shop.items()) {
    if (item.unlock == UnlockKind::world) {
      worldRow = item.id;
      break;
    }
  }
  check(!worldRow.empty(), "the catalogue must ship one world-attached row");
  const ShopItem& item = pick(shop, worldRow);
  check(item.unlockWorld == "egypt", "the world row targets egypt, got " + item.unlockWorld);
  check(item.currency != "coin",
        "the world row is not coin-priced; if this ever changes the rule below needs review");
  bool carriesKey = false;
  for (const Grant& grant : item.grants) {
    if (grant.kind == GrantKind::key) carriesKey = true;
  }
  check(!carriesKey, "the world-attached pinata row must not carry a key grant");

  Progress progress;
  progress.coins = 1000000;
  const BuyResult result = purchase(shop, worldRow, progress);
  check(!result.ok, "an unmodelled-currency world row must be refused");
  check(progress.keys == 0, "a refused purchase must never grant a key");
  check(progress.purchases.empty(), "a refused purchase must not be recorded");
}

void testRoundTripThroughSave() {
  const Shop shop = Shop::load(gContent, gUnlock);
  Progress progress;
  progress.coins = 900;
  check(purchase(shop, "seed_iris", progress).ok, "the setup purchase must succeed");

  const fs::path save = gTemp / "shop-progress" / "save.json";
  fs::create_directories(save.parent_path());
  saveProgress(save, progress, 0);
  const Progress reloaded = loadProgress(save);
  check(reloaded.coins == 400, "coins must survive the round trip");
  check(owns(reloaded, "seed_iris"), "purchases must survive the round trip");
  check(reloaded.seeds.size() == 1 && reloaded.seeds.front() == "iris",
        "granted seeds must survive the round trip");
}

void testUntabulatedRowIsRefused() {
  Json row;
  row["id"] = "mystery";
  row["name_zh"] = "mystery";
  row["category"] = "items";
  row["tab"] = "items";
  row["item_type"] = "unknown";
  row["currency"] = "coin";
  row["price"] = 10;
  row["implemented"] = true;
  row["payload"]["plant_id"] = "sunflower";
  Json shop_json;
  shop_json["items"] = Json::array({row});
  Json unlock_json;
  unlock_json["items"] = Json::array();
  const Shop shop =
      Shop::parse(shop_json.dump(), "inline-shop", unlock_json.dump(), "inline-unlock");
  check(shop.size() == 1, "the inline catalogue has one row");
  check(shop.missingRows() == 1, "a row with no unlock record must be counted, not assumed free");
  Progress progress;
  progress.coins = 100;
  const BuyResult result = purchase(shop, "mystery", progress);
  check(!result.ok, "a row with no unlock record must not be buyable");
  check(result.reason.find("unlock kind is unknown") != std::string::npos,
        "the refusal must name the missing gate, got " + result.reason);
}

void testRejections() {
  bool threw = false;
  try {
    Shop::parse("not json", "bad-shop", R"({"items":[]})", "inline");
  } catch (const std::exception& error) {
    threw = std::string(error.what()).find("bad-shop: not valid JSON") != std::string::npos;
  }
  check(threw, "malformed shop JSON must name the file");

  threw = false;
  try {
    Shop::parse(R"({"items":[]})", "inline-shop", "{}", "bad-unlock");
  } catch (const std::exception& error) {
    threw = std::string(error.what()).find("missing \"items\"") != std::string::npos;
  }
  check(threw, "an unlock table without items must be rejected");
}

void run() {
  testCatalogueCounts();
  testKnownRows();
  testPurchaseSpendsCoins();
  testFreeRowCostsNothing();
  testGemRowIsRefused();
  testSeedPayloadIsDeliveredOnce();
  testCoinsPayloadIsCredited();
  testGemsPayloadIsCredited();
  testWorldKeyIsGrantedOnce();
  testPlantfoodUpgrades();
  testCostumeIsRecordedOnce();
  testCostumeListStaysSortedAndUnique();
  testSettingSwitchIsStored();
  testSettingResourceCounterIsRefused();
  testBundleWithUnknownHalfIsRefused();
  testUnknownPayloadKindsAreRefused();
  testWalletGateRunsBeforePayload();
  testReceiptMatchesSaveDelta();
  testGrantsSurviveSaveRoundTrip();
  testRepeatableRowIsNotAlreadyOwned();
  testNotEnoughCoins();
  testWorldRowNeverMintsAKey();
  testRoundTripThroughSave();
  testUntabulatedRowIsRefused();
  testRejections();
  std::cout << "shop tests passed (" << 25 << " sections)\n";
}

}  // namespace

int main(int argc, char** argv) {
  try {
    if (argc < 4) {
      std::cerr << "usage: shop_test <content> <unlock.json> <temp>\n";
      return 2;
    }
    gContent = fs::path(argv[1]);
    gUnlock = fs::path(argv[2]);
    gTemp = fs::path(argv[3]);
    fs::create_directories(gTemp);
    run();
    return 0;
  } catch (const std::exception& error) {
    std::cerr << error.what() << "\n";
    return 1;
  }
}
