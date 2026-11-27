// Reward settlement tests: what a finished battle pays, and what it refuses to pay.
//
// The cases are the ones a reviewer can check against `docs/reviews/2026-11-24-rewards.md` and
// `docs/reviews/2026-11-25-reward-kinds.md`: the silver/gold kill periods and their rounding
// edges, the end-of-level lunch box (including the 13 present tables the pack references but
// never shipped), the four world keys with their `EnabledAfter=egypt3` gate, the weighted seed
// bags, and — since T77 — the five families the save can now hold (gems, lawn mowers, plant XP,
// trophies, seed bags) plus the ones it still cannot (sprouts, whack sun, and the 438 first-clear
// / rift / gift-box rows the table carries but no battle can name).
//
// No SDL: this runs in the audit configuration. The worlds are real `engine::World`s, driven by
// spawning and killing zombies through the public damage path, so a change to the kill counter
// shows up here instead of only moving a hash.
#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include "catalog.hpp"
#include "engine/world.hpp"
#include "progress.hpp"
#include "rewards.hpp"

namespace fs = std::filesystem;
using namespace pvz;

namespace {

void check(bool condition, const std::string& message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

/// A level that finishes the moment it starts: no waves, so the director is exhausted and the
/// lawn is empty. That is `won`, the only state that pays a lunch box.
LevelDefinition wonLevel(const Catalog& catalog, const std::string& id) {
  const auto it = catalog.levels.find(id);
  check(it != catalog.levels.end(), "missing level: " + id);
  LevelDefinition level = it->second;
  level.waves.clear();
  return level;
}

/// Kills exactly `count` basic zombies through the public damage path, so the world's own kill
/// counter and its RNG advance the way a real battle would.
void killZombies(engine::World& world, int count) {
  for (int i = 0; i < count; ++i) {
    if (!world.spawnZombie("basic", 0)) {
      throw std::runtime_error("the world refused a bait zombie at kill " + std::to_string(i));
    }
    const engine::EntityId id = world.zombies().back().id;
    world.damageZombie(id, 1.0e9);
  }
  check(static_cast<int>(world.killedZombies()) == count,
        "the kill counter must match the zombies killed");
}

int unmodelledOf(const RewardGain& gain, const std::string& kind) {
  for (const RewardUnknown& unknown : gain.unmodelled) {
    if (unknown.kind == kind) return unknown.count;
  }
  return 0;
}

/// One loot row in exactly the shape the shipped table has, so the period maths can be pinned
/// without the other 24 rows adding noise.
LootRow coinRow(const std::string& id, int period, int amount, int low, int high,
                const std::string& lootKey = "default") {
  LootRow row;
  row.id = id;
  row.kind = "coin";
  row.lootType = amount >= 100 ? "GoldCoin" : "SilverCoin";
  row.lootKey = lootKey;
  row.world = "any";
  row.period = period;
  row.amount = amount;
  row.lowCount = low;
  row.highCount = high;
  return row;
}

RewardTable tableWith(std::vector<LootRow> rows) {
  RewardTable table;
  table.loot = std::move(rows);
  return table;
}

void testTableCounts() {
  const RewardTable& table = RewardTable::shared();
  check(table.lootRows() == 25,
        "the pack ships 25 kill-period loot rows, got " + std::to_string(table.lootRows()));
  check(table.coinLootRows() == 8,
        "8 of them are coins, got " + std::to_string(table.coinLootRows()));
  check(table.keyLootRows() == 8,
        "8 of them are world keys, got " + std::to_string(table.keyLootRows()));
  check(table.presentRows() == 36,
        "the pack ships 36 present entries, got " + std::to_string(table.presentRows()));
  check(table.seedRows() == 76,
        "the pack ships 76 seed-drop rows, got " + std::to_string(table.seedRows()));
  check(table.danglingTables() == 13,
        "13 present tables are referenced but never shipped, got " +
            std::to_string(table.danglingTables()));
  check(table.worldKeys.size() == 10,
        "10 world key names, got " + std::to_string(table.worldKeys.size()));
  check(table.presentTableIsDangling("beach_normal_01"),
        "beach_normal_01 is one of the 13 dangling tables");
  check(!table.presentTableIsDangling("egypt_normal_01"),
        "egypt_normal_01 is shipped, so it cannot be dangling");
  check(table.seedRowsForPackage("pkg_0662").size() == 2,
        "pkg_0662 carries a two-candidate seed bag");
  check(table.seedRowsForPackage("pkg_0000").empty(),
        "an unknown package carries no seed bag");
  // The four key rows are the only place a world key can come from, and the sheet names the gate
  // in `condition`. Nothing in the shipped table may claim to produce mint or stars.
  int keyRows = 0;
  for (const LootRow& row : table.loot) {
    if (row.kind == "key") {
      check(row.condition == "egypt3", "every key row is gated on egypt3, got " + row.condition);
      ++keyRows;
    }
    check(row.kind != "mint" && row.kind != "star",
          "mint and star are server-only and must not appear as loot rows: " + row.id);
  }
  check(keyRows == 8, "all 8 key rows carry the gate");
}

void testSilverPeriod(const Catalog& catalog) {
  const RewardTable& shipped = RewardTable::shared();
  bool sawSilver = false;
  for (const LootRow& row : shipped.loot) {
    if (row.kind != "coin" || row.lootType != "SilverCoin") continue;
    sawSilver = true;
    check(row.period == 2, "silver drops every 2 kills, got " + std::to_string(row.period));
    check(row.amount == 10, "one silver coin is worth 10, got " + std::to_string(row.amount));
    check(row.lowCount == 1 && row.highCount == 3,
          "silver pays 1..3 coins per period, got " + std::to_string(row.lowCount) + ".." +
              std::to_string(row.highCount));
  }
  check(sawSilver, "the pack must ship at least one silver row");

  // The same numbers through the shipped table: 1 kill is one short, 2 kills pays 10..30.
  {
    engine::World world(catalog, wonLevel(catalog, "frontyard_1"), 21);
    killZombies(world, 1);
    SettlementOptions options;
    options.lootKey = "whack";  // no coin row belongs to the whack key, so only silver can move
    const RewardGain gain = settleRewards(shipped, world, "frontyard", "pkg_0001", options);
    check(gain.coins == 0, "one kill must not drop a silver coin, got " +
                               std::to_string(gain.coins));
  }
  {
    engine::World world(catalog, wonLevel(catalog, "frontyard_1"), 21);
    killZombies(world, 2);
    const RewardGain gain = settleRewards(shipped, world, "frontyard", "pkg_0001");
    check(gain.coins >= 10 && gain.coins <= 30,
          "two kills must drop 1..3 silver coins, got " + std::to_string(gain.coins));
  }
}

void testGoldPeriods(const Catalog& catalog) {
  const RewardTable table = tableWith(
      {coinRow("probe:gold1", 40, 100, 1, 1), coinRow("probe:gold3", 60, 100, 1, 3)});
  struct Case {
    int kills;
    int low;
    int high;
    const char* what;
  };
  const Case cases[] = {{39, 0, 0, "39 kills: neither row has fired"},
                        {40, 100, 100, "40 kills: one flat gold coin"},
                        {60, 200, 400, "60 kills: plus one 1..3 gold roll"},
                        {120, 400, 800, "120 kills: both rows fired twice"}};
  for (const Case& item : cases) {
    engine::World world(catalog, wonLevel(catalog, "frontyard_1"), 7);
    killZombies(world, item.kills);
    const RewardGain gain = settleRewards(table, world, "frontyard", "pkg_0001");
    check(gain.coins >= item.low && gain.coins <= item.high,
          std::string(item.what) + ", got " + std::to_string(gain.coins));
  }
}

void testSameSeedSameGain(const Catalog& catalog) {
  const RewardTable& table = RewardTable::shared();
  auto once = [&](std::uint32_t seed) {
    engine::World world(catalog, wonLevel(catalog, "egypt_1"), seed);
    killZombies(world, 47);
    SettlementOptions options;
    options.keysUnlocked = true;
    return settleRewards(table, world, "egypt", "pkg_0001", options).json();
  };
  const auto first = once(11);
  const auto second = once(11);
  check(first == second, "the same seed and kill count must settle to the same rewards");
  const auto other = once(12);
  check(first != other, "a different seed must be allowed to pay differently");
}

void testKeyWorldAndGate(const Catalog& catalog) {
  const RewardTable& table = RewardTable::shared();

  // 30 kills is exactly one key period: gated off, no key may appear.
  {
    engine::World world(catalog, wonLevel(catalog, "egypt_1"), 3);
    killZombies(world, 30);
    const RewardGain gain = settleRewards(table, world, "egypt", "pkg_0001", SettlementOptions{});
    check(gain.keys == 0, "a locked save must not earn a key, got " + std::to_string(gain.keys));
  }
  // Ungated, both egypt rows fire.
  {
    engine::World world(catalog, wonLevel(catalog, "egypt_1"), 3);
    killZombies(world, 30);
    SettlementOptions unlocked;
    unlocked.keysUnlocked = true;
    const RewardGain gain = settleRewards(table, world, "egypt", "pkg_0001", unlocked);
    check(gain.keys == 2, "the egypt level must pay both egypt key rows, got " +
                              std::to_string(gain.keys));
  }
  // The gate is not the only filter: a cowboy level pays cowboy keys, never egypt keys.
  {
    engine::World world(catalog, wonLevel(catalog, "cowboy_1"), 3);
    killZombies(world, 30);
    SettlementOptions unlocked;
    unlocked.keysUnlocked = true;
    const RewardGain gain = settleRewards(table, world, "cowboy", "pkg_0001", unlocked);
    check(gain.keys == 2, "the cowboy level must pay both cowboy key rows, got " +
                              std::to_string(gain.keys));
  }
  // A world with no key rows pays none, however many zombies die.
  {
    engine::World world(catalog, wonLevel(catalog, "frontyard_1"), 3);
    killZombies(world, 300);
    SettlementOptions unlocked;
    unlocked.keysUnlocked = true;
    const RewardGain gain = settleRewards(table, world, "frontyard", "pkg_0001", unlocked);
    check(gain.keys == 0, "frontyard has no key rows, got " + std::to_string(gain.keys));
  }
}

void testPresentLunchBox(const Catalog& catalog) {
  const RewardTable& table = RewardTable::shared();

  // Shipped table: cowboy_normal_01 pays one 100-coin pack.
  {
    engine::World world(catalog, wonLevel(catalog, "cowboy_1"), 5);
    world.step();
    check(world.status() == "won", "the fixture level must end won, got " + world.status());
    const RewardGain gain = settleRewards(table, world, "cowboy", "pkg_0001");
    check(gain.presentSource == "world", "cowboy has its own table, got " + gain.presentSource);
    check(!gain.presentTableMissing, "a shipped table is not missing");
    check(gain.presentCoins == 100,
          "the cowboy lunch box is 100 coins, got " + std::to_string(gain.presentCoins));
    check(gain.coins == gain.presentCoins, "no kills means the lunch box is the only income");
  }
  // beach_normal_01 is one of the 13 dangling tables: pay nothing, say so.
  {
    engine::World world(catalog, wonLevel(catalog, "beach_1"), 5);
    world.step();
    const RewardGain gain = settleRewards(table, world, "beach", "pkg_0001");
    check(gain.presentTableMissing, "beach_normal_01 is dangling and must be reported missing");
    check(gain.presentSource == "missing",
          "the source must say missing, got " + gain.presentSource);
    check(gain.presentCoins == 0 && gain.coins == 0,
          "a dangling table must pay nothing, got " + std::to_string(gain.coins));
  }
  // A world with no table name at all falls back to egypt_normal_01, and says so.
  {
    engine::World world(catalog, wonLevel(catalog, "modern_1"), 5);
    world.step();
    const RewardGain gain = settleRewards(table, world, "modern", "pkg_0001");
    check(!gain.presentTableMissing, "modern is not listed as dangling");
    check(gain.presentSource == "egypt_default",
          "modern must use the stated egypt fallback, got " + gain.presentSource);
    check(gain.presentTable == "egypt_normal_01",
          "the fallback table is egypt_normal_01, got " + gain.presentTable);
    check(gain.presentCoins == 100,
          "the fallback table pays 100, got " + std::to_string(gain.presentCoins));
  }
  // A battle that has not ended pays no lunch box.
  {
    engine::World world(catalog, catalog.levels.at("cowboy_1"), 5);
    const RewardGain gain = settleRewards(table, world, "cowboy", "pkg_0001");
    check(gain.presentCoins == 0,
          "an unfinished battle pays no lunch box, got " + std::to_string(gain.presentCoins));
    check(gain.presentSource.find("not_cleared") != std::string::npos,
          "the source must say the level was not cleared, got " + gain.presentSource);
  }
  // A shiny table ships the same 100 coins and seven disabled extras: nothing extra is paid.
  {
    engine::World world(catalog, wonLevel(catalog, "cowboy_1"), 5);
    world.step();
    SettlementOptions shiny;
    shiny.presentVariant = "shiny";
    const RewardGain gain = settleRewards(table, world, "cowboy", "pkg_0001", shiny);
    check(gain.presentCoins == 100,
          "the shiny lunch box is still 100 coins, got " + std::to_string(gain.presentCoins));
    check(unmodelledOf(gain, "powerup") == 0,
          "disabled shiny extras must not be counted as unmodelled drops");
  }
}

void testSeedBag(const Catalog& catalog) {
  const RewardTable& table = RewardTable::shared();
  // pkg_0662 is frontyard_101's package: 20% over two candidates.
  {
    engine::World world(catalog, wonLevel(catalog, "frontyard_101"), 9);
    killZombies(world, 200);
    const RewardGain gain = settleRewards(table, world, "frontyard", "pkg_0662");
    check(!gain.seeds.empty(), "200 kills at 20% must drop at least one seed");
    for (const std::string& seed : gain.seeds) {
      check(seed == "impatiensshooter" || seed == "buduhboom",
            "seed " + seed + " is not one of pkg_0662's two candidates");
    }
  }
  // pkg_1690 is carnival_52's package and drops on every kill (chance 1).
  {
    engine::World world(catalog, wonLevel(catalog, "carnival_52"), 9);
    killZombies(world, 5);
    const RewardGain gain = settleRewards(table, world, "carnival", "pkg_1690");
    check(gain.seeds.size() == 5, "a 100% bag must drop once per kill, got " +
                                      std::to_string(gain.seeds.size()));
  }
  // A level without the module drops nothing, however many zombies die.
  {
    engine::World world(catalog, wonLevel(catalog, "frontyard_1"), 9);
    killZombies(world, 200);
    const RewardGain gain = settleRewards(table, world, "frontyard", "pkg_0001");
    check(gain.seeds.empty(), "a level without the seed module must not drop seeds");
  }
}

void testUnmodelledKinds(const Catalog& catalog) {
  const RewardTable& table = RewardTable::shared();
  engine::World world(catalog, wonLevel(catalog, "frontyard_1"), 4);
  killZombies(world, 60);
  const RewardGain gain = settleRewards(table, world, "frontyard", "pkg_0001");
  // 60 kills reaches the gem (30), lawn mower (20) and sprout (5) periods. Gems and mowers now
  // land in the save, so only the families with nowhere to go may still be counted.
  check(unmodelledOf(gain, "gem") == 0,
        "gems have a save field since T77 and must not be reported unmodelled");
  check(unmodelledOf(gain, "mower") == 0,
        "lawn mowers have a save field since T77 and must not be reported unmodelled");
  check(unmodelledOf(gain, "sprout") > 0, "sprouts have no save field and must be reported");
  check(unmodelledOf(gain, "sun") == 0,
        "the whack sun rows belong to the whack minigame, not to a normal level");
  // The reported kinds stay sorted, so a CLI reader can diff two runs.
  std::string last;
  for (const RewardUnknown& unknown : gain.unmodelled) {
    check(last < unknown.kind, "unmodelled kinds must be sorted, saw " + unknown.kind);
    last = unknown.kind;
  }
  // Loot keys are not decorative: the coin rows are `default`-keyed, so a level with no key pays
  // none. The gem and mower rows are `any` (the sheet leaves their LevelLootKey empty), which is
  // what puts them in every level of the world rather than only the default subset.
  SettlementOptions none;
  none.lootKey.clear();
  const RewardGain noLoot = settleRewards(table, world, "frontyard", "pkg_0001", none);
  check(noLoot.coins == 0 && noLoot.keys == 0,
        "an empty loot key must stop the coin rows, got " + std::to_string(noLoot.coins) + "/" +
            std::to_string(noLoot.keys));
  check(noLoot.gems == 6 && noLoot.mowers == 10,
        "the `any` gem and mower rows pay in a level with no loot key, got " +
            std::to_string(noLoot.gems) + "/" + std::to_string(noLoot.mowers));
}

void testApplyRewardsFoldsTheSave() {
  Progress progress;
  progress.coins = 5;
  progress.keys = 1;
  progress.seeds = {"wallnut"};

  RewardGain gain;
  gain.coins = 100;
  gain.keys = 2;
  gain.seeds = {"impatiensshooter", "wallnut", "aloe"};

  applyRewards(progress, gain);
  check(progress.coins == 105, "coins add up, got " + std::to_string(progress.coins));
  check(progress.keys == 3, "keys add up, got " + std::to_string(progress.keys));
  check(progress.seeds == std::vector<std::string>({"aloe", "impatiensshooter", "wallnut"}),
        "seeds stay sorted and unique");

  // The empty gain changes nothing, which is what a level with no drops must do.
  const Progress before = progress;
  applyRewards(progress, RewardGain{});
  check(progress.coins == before.coins && progress.keys == before.keys &&
            progress.seeds == before.seeds,
        "an empty gain must not touch the save");
}

/// T77 gem / mower: the two loot families a battle can now pay into the save.
void testGemMowerLand(const Catalog& catalog) {
  const RewardTable& table = RewardTable::shared();
  engine::World world(catalog, wonLevel(catalog, "frontyard_1"), 4);
  killZombies(world, 60);
  const RewardGain gain = settleRewards(table, world, "frontyard", "pkg_0001");
  // Gem1 (period 30) fires twice and Gem2 (period 40) once, two gems each: 6.
  check(gain.gems == 6, "60 kills must pay 6 gems, got " + std::to_string(gain.gems));
  // Four mower rows at periods 20/20/30/30 pay 3 + 3 + 2 + 2 = 10.
  check(gain.mowers == 10, "60 kills must pay 10 mowers, got " + std::to_string(gain.mowers));

  Progress progress;
  const RewardDelta delta = applyRewards(progress, gain);
  check(progress.gems == 6, "the save holds the gems, got " + std::to_string(progress.gems));
  check(delta.gems == 6, "the delta reports the gems, got " + std::to_string(delta.gems));
  check(progress.mowers == 10, "the save holds the mowers, got " + std::to_string(progress.mowers));
  check(delta.mowers == 10, "the delta reports the mowers, got " + std::to_string(delta.mowers));

  Json summary = Json::object();
  addRewardReceipt(summary, delta, table);
  check(summary["gemsGained"] == 6 && summary["mowersGained"] == 10,
        "the receipt repeats what the save took, got " + summary.dump());
}

/// A save that already holds the gem count keeps adding; the delta is what changed.
void testGemMowerDeltaIsHonest() {
  Progress progress;
  progress.gems = 4;
  progress.mowers = 2;
  RewardGain gain;
  gain.gems = 6;
  gain.mowers = 10;
  const RewardDelta delta = applyRewards(progress, gain);
  check(progress.gems == 10 && delta.gems == 6,
        "gems start at 4 and the delta is 6, got " + std::to_string(progress.gems) + "/" +
            std::to_string(delta.gems));
  check(progress.mowers == 12 && delta.mowers == 10,
        "mowers start at 2 and the delta is 10, got " + std::to_string(progress.mowers) + "/" +
            std::to_string(delta.mowers));
}

/// `plant` is an unlock, not a seed packet: the 293 rows are first-clear `unlock_plant:` rewards
/// with no level and no amount, so they must stay out of `Progress::seeds`. What lands there is
/// the 76 `seed` rows, and a seed already owned is not a gain.
void testPlantUnlockIsNotASeedBag() {
  const RewardTable& table = RewardTable::shared();
  const auto it = table.unlandedRows().find("plant");
  check(it != table.unlandedRows().end() && it->second == 293,
        "the pack ships 293 unlock_plant rows and none of them can be settled");

  Progress progress;
  RewardGain gain;
  gain.seeds = {"wallnut"};
  const RewardDelta first = applyRewards(progress, gain);
  check(first.plants == 1 && progress.seeds == std::vector<std::string>({"wallnut"}),
        "a new seed is one plant gained");
  const RewardDelta again = applyRewards(progress, gain);
  check(again.plants == 0,
        "a seed already in the save is not a second plant, got " + std::to_string(again.plants));
  check(progress.seeds.size() == 1, "seeds stay unique, got " +
                                        std::to_string(progress.seeds.size()));
}

/// Plant XP and trophies have storage and a fold even though no shipped battle row can name
/// them yet: the save shape is what P1-9 and the rift work need, and the delta stays honest.
void testXpAndTrophyFold() {
  Progress progress;
  RewardGain gain;
  gain.xp = 25;
  gain.trophies = {"worldtrophy_dark", "worldtrophy_beach"};
  const RewardDelta delta = applyRewards(progress, gain);
  check(progress.xp == 25 && delta.xp == 25, "xp accumulates, got " + std::to_string(progress.xp));
  check(progress.trophies ==
            std::vector<std::string>({"worldtrophy_beach", "worldtrophy_dark"}),
        "trophies stay sorted and unique");
  check(delta.trophies == 2, "two new trophies are two gains, got " +
                                 std::to_string(delta.trophies));

  const RewardDelta repeat = applyRewards(progress, gain);
  check(repeat.xp == 25, "xp is a counter, so it accumulates again");
  check(repeat.trophies == 0, "an owned trophy is not granted twice, got " +
                                  std::to_string(repeat.trophies));
  check(progress.trophies.size() == 2, "the set still holds two");
}

/// The receipt shape the CLI prints under `--progress`: the five gained counters plus the census
/// of rows no battle can settle. Nothing else — `coinsGained` and friends stay main.cpp's keys.
void testReceiptShape() {
  const RewardTable& table = RewardTable::shared();
  RewardDelta gained;
  gained.coins = 999;
  gained.keys = 999;
  gained.gems = 4;
  gained.xp = 7;
  gained.mowers = 1;
  gained.trophies = 2;
  gained.plants = 3;
  Json summary = Json::object();
  addRewardReceipt(summary, gained, table);

  check(summary["gemsGained"] == 4 && summary["xpGained"] == 7 &&
            summary["mowersGained"] == 1 && summary["trophiesGained"] == 2 &&
            summary["plantsGained"] == 3,
        "the five counters must carry the delta, got " + summary.dump());
  check(!summary.contains("coinsGained") && !summary.contains("keysGained") &&
            !summary.contains("seedsGained"),
        "the old summary keys belong to main.cpp, got " + summary.dump());
  check(summary.contains("rewardUnlanded") && summary["rewardUnlanded"].is_array(),
        "the receipt names the rows that cannot be settled");

  std::string last;
  for (const Json& row : summary["rewardUnlanded"]) {
    const std::string kind = row["kind"].get<std::string>();
    check(last < kind, "the census is sorted by kind, saw " + kind);
    check(row["count"].get<int>() > 0, "a census row always has a count, saw " + kind);
    last = kind;
  }
}

/// The 438 rows the table carries that no battle can name, by family, and the closure that makes
/// the number checkable: 25 loot + 76 seed + 36 present + 438 unlanded = the 575 shipped rows.
void testUnlandedCensus() {
  const RewardTable& table = RewardTable::shared();
  const auto& unlanded = table.unlandedRows();
  int total = 0;
  for (const auto& [kind, count] : unlanded) total += count;
  check(total == 438, "438 of the 575 shipped rows cannot be settled, got " +
                          std::to_string(total));
  check(unlanded.at("plant") == 293, "plant 293, got " + std::to_string(unlanded.at("plant")));
  check(unlanded.at("cosmetic") == 22, "cosmetic 22");
  check(unlanded.at("trophy") == 18, "trophy 18");
  check(unlanded.at("xp") == 14, "xp 14");
  check(unlanded.at("note") == 11, "note 11");
  check(unlanded.at("collectable") == 9, "collectable 9");
  check(unlanded.at("gem") == 6, "the 6 rift/gift-box gem rows are still unlanded");
  const int landed = static_cast<int>(table.lootRows()) + static_cast<int>(table.seedRows()) +
                     static_cast<int>(table.presentRows());
  check(landed == 137, "25 loot + 76 seed + 36 present = 137, got " + std::to_string(landed));
  check(landed + total == 575, "the four families must add up to the shipped 575 rows");
}

/// The three new save fields survive a write/read round trip, and a save that never earned one
/// keeps the older byte shape (no `mowers` / `xp` / `trophies` keys at all).
void testNewSaveFieldsRoundTrip() {
  Progress progress;
  progress.mowers = 3;
  progress.xp = 42;
  progress.trophies = {"worldtrophy_beach"};
  const Json json = progressToJson(progress);
  check(json["mowers"] == 3 && json["xp"] == 42, "the counters are written, got " + json.dump());
  check(json["trophies"] == Json::array({"worldtrophy_beach"}), "the trophy set is written");
  const Progress back = parseProgress(json, "rewards_test");
  check(back.mowers == 3 && back.xp == 42 &&
            back.trophies == std::vector<std::string>({"worldtrophy_beach"}),
        "the three fields survive the round trip");

  const Json fresh = progressToJson(Progress{});
  check(!fresh.contains("mowers") && !fresh.contains("xp") && !fresh.contains("trophies"),
        "a save that never earned one keeps the older shape, got " + fresh.dump());

  Json duplicated = json;
  duplicated["trophies"] = Json::array({"b", "a", "a"});
  const Progress loaded = parseProgress(duplicated, "rewards_test");
  check(loaded.trophies == std::vector<std::string>({"a", "b"}),
        "trophies are a set: a duplicated id collapses on load");
}

/// The seed bag is the one family where a battle really does pay it: settle → fold → receipt, in
/// one case. A repeated candidate is one plant, not two, and the receipt says so.
void testSeedBagReachesTheReceipt(const Catalog& catalog) {
  const RewardTable& table = RewardTable::shared();
  engine::World world(catalog, wonLevel(catalog, "carnival_52"), 9);
  killZombies(world, 5);
  const RewardGain gain = settleRewards(table, world, "carnival", "pkg_1690");
  check(gain.seeds.size() == 5, "pkg_1690 drops once per kill, got " +
                                    std::to_string(gain.seeds.size()));
  std::vector<std::string> unique = gain.seeds;
  std::sort(unique.begin(), unique.end());
  unique.erase(std::unique(unique.begin(), unique.end()), unique.end());

  Progress progress;
  const RewardDelta delta = applyRewards(progress, gain);
  check(progress.seeds == unique, "the save holds exactly the distinct seeds");
  check(delta.plants == static_cast<int>(unique.size()),
        "the delta counts distinct seeds, got " + std::to_string(delta.plants));
  Json summary = Json::object();
  addRewardReceipt(summary, delta, table);
  check(summary["plantsGained"] == static_cast<int>(unique.size()),
        "the receipt repeats the distinct seeds, got " + summary.dump());
}

void testKeysUnlockedGate() {
  Progress progress;
  check(!keysUnlocked(progress), "a fresh save has not cleared egypt_3");
  LevelRecord record;
  record.cleared = true;
  progress.levels["egypt_3"] = record;
  check(keysUnlocked(progress), "clearing egypt_3 opens the key rows");
  record.cleared = false;
  progress.levels["egypt_3"] = record;
  check(!keysUnlocked(progress), "an attempted but uncleared egypt_3 keeps the gate shut");
}

/// 438 rows the battle path cannot reach; 293 of them name a plant. Landing writes those plants into
/// `unlockedPlants` (ownership), not into `seeds` (a plantable packet), and a second pass changes
/// nothing: the roster is a set.
///
/// 293 rows are not 293 plants: 244 are `first:unlock_plant:<plant>` and 49 are
/// `replay:unlock_plant:<plant>` naming a plant the first-clear row already granted. So `landed`
/// counts rows (293) while the roster grows by the 244 distinct ids and the 49 repeats report as
/// `already_owned`.
void testPlantUnlocksLand() {
  const RewardTable& table = RewardTable::shared();
  Progress progress;
  const RewardLanding first = landRewards(progress, table);

  check(first.planted == 244, "244 distinct plants must land, got " +
                                  std::to_string(first.planted));
  check(first.alreadyOwned == 56,
        "49 replay plant rows + 7 repeated costume rows are already owned, got " +
            std::to_string(first.alreadyOwned));
  check(progress.unlockedPlants.size() == 244,
        "the save must own 244 plants, got " + std::to_string(progress.unlockedPlants.size()));
  check(std::is_sorted(progress.unlockedPlants.begin(), progress.unlockedPlants.end()),
        "unlockedPlants stays sorted");
  const auto has = [&progress](const std::string& id) {
    return std::binary_search(progress.unlockedPlants.begin(), progress.unlockedPlants.end(), id);
  };
  check(has("ailmint") && has("akee1") && has("aloe"),
        "three sampled rows from the table must be owned after landing");
  check(first.unlockedPlants.size() == 244, "the report lists the plants this pass added");
  check(progress.seeds.empty(), "an unlock is not a seed: the seed bag stays untouched");

  const RewardLanding again = landRewards(progress, table);
  check(again.planted == 0 && again.unlockedPlants.empty(),
        "a second pass unlocks nothing, got " + std::to_string(again.planted));
  check(again.alreadyOwned == 315, "every plant and costume row is already owned on pass two, got " +
                                       std::to_string(again.alreadyOwned));
  check(progress.unlockedPlants.size() == 244, "the roster does not grow on a second pass");

  std::cout << "plants: 293 rows -> " << progress.unlockedPlants.size()
            << " owned (landed " << first.landed << ", already owned " << first.alreadyOwned
            << "), second pass planted " << again.planted << " alreadyOwned " << again.alreadyOwned
            << "\n";
}

/// The 30 coin rows are three families, and paying the wrong two would mint money:
///   * 4 `constant:` rows are `GamePropertySheet` prices (`CoinsPerKey = 1000` = a key costs 1000);
///   * 26 `rift-boss:` / `rift-clear:` rows are payouts of a mode this client does not have;
///   * the 10 `present:...:coinpack_medium` rows are the lunch box, already paid by `settleRewards`.
/// The default pays none of the first two, and each opt-in pays exactly its family.
void testCoinFamiliesDoNotMintCoins() {
  const RewardTable& table = RewardTable::shared();
  const int constants = 5010;  // 1000 + 10 + 2000 + 2000
  const int rift = 23600;      // 3 x 5200 from rift-boss + 8000 from rift-clear

  Progress progress;
  const RewardLanding plain = landRewards(progress, table);
  check(progress.coins == 0 && plain.coins == 0,
        "the default pass must not pay a price or a rift payout, got " +
            std::to_string(progress.coins));
  check(plain.prices.at("CoinsPerKey") == 1000 && plain.prices.at("KeysPerCostume") == 10 &&
            plain.prices.at("LawnMowerPurchasePriceInCoins") == 2000 &&
            plain.prices.at("SeedSlotRentalCost") == 2000 &&
            plain.prices.at("StarsPerCostume") == 20,
        "the five economy constants are reported as prices, got " + plain.json().dump());
  check(plain.byReason.at("price_constant") == 5,
        "4 coin prices + the star price, got " +
            std::to_string(plain.byReason.at("price_constant")));
  check(plain.byKind.at("star") == 1,
        "StarsPerCostume = 20 is a star price and can never be paid into coins, got " +
            plain.json().dump());
  check(plain.byReason.at("rift_payout") == 54,
        "26 rift coin + 5 gem + 9 pinata + 14 xp rows, got " +
            std::to_string(plain.byReason.at("rift_payout")));

  LandingOptions payConstants;
  payConstants.landEconomyConstants = true;
  Progress constantSave;
  const RewardLanding paid = landRewards(constantSave, table, payConstants);
  check(constantSave.coins == constants,
        "the opt-in pays exactly the four coin constants (" + std::to_string(constants) +
            "), got " + std::to_string(constantSave.coins));
  check(paid.coins == constants && paid.byReason.at("price_paid") == 4,
        "the report names the four paid constants, got " + paid.json().dump());

  LandingOptions payRift;
  payRift.landRiftPayouts = true;
  Progress riftSave;
  const RewardLanding riftPaid = landRewards(riftSave, table, payRift);
  check(riftSave.coins == rift,
        "the rift opt-in pays the 26 rift coin rows (" + std::to_string(rift) + "), got " +
            std::to_string(riftSave.coins));
  check(riftPaid.coins == rift && riftPaid.byReason.at("rift_paid") == 26,
        "the report names the 26 paid rift rows, got " + riftPaid.json().dump());
  check(riftPaid.byReason.at("rift_payout") == 28,
        "the gem, pinata and xp rift rows stay recorded, got " + riftPaid.json().dump());

  std::cout << "coins: default 0, constants opt-in " << constantSave.coins << ", rift opt-in "
            << riftSave.coins << ", prices " << plain.prices.size() << "\n";
}

/// 22 `unlock_costume:<id>` rows land in `costumes`, the field the shop already writes for
/// `payload.costume_id`, so ownership has one home. Like the plant rows they repeat: 15 distinct
/// costumes, 7 duplicates.
void testCostumesLand() {
  const RewardTable& table = RewardTable::shared();
  Progress progress;
  const RewardLanding landing = landRewards(progress, table);
  check(landing.costumed == 15, "15 distinct costumes must land, got " +
                                    std::to_string(landing.costumed));
  check(progress.costumes.size() == 15, "the save owns 15 costumes, got " +
                                            std::to_string(progress.costumes.size()));
  check(landing.byReason.at("already_owned") == 56,
        "7 costume rows + 49 plant rows repeat an id, got " +
            std::to_string(landing.byReason.at("already_owned")));
  check(std::binary_search(progress.costumes.begin(), progress.costumes.end(),
                           std::string("539-idle")),
        "539-idle is one of the sampled rows and must be owned");
  check(std::is_sorted(progress.costumes.begin(), progress.costumes.end()) &&
            std::adjacent_find(progress.costumes.begin(), progress.costumes.end()) ==
                progress.costumes.end(),
        "costumes stay sorted and unique");
}

/// Rows with no settlement path are recorded, not paid: `rewardLog` grows by one entry per row, the
/// currency counters do not move, and landing twice does not duplicate the log.
void testNoteOnlyRowsAreLogged() {
  const RewardTable& table = RewardTable::shared();
  Progress progress;
  progress.coins = 7;
  progress.keys = 3;
  const RewardLanding landing = landRewards(progress, table);
  check(progress.coins == 7 && progress.keys == 3,
        "a record is not a payout: coins and keys stay put");
  check(landing.logged == 123, "every unlanded row is logged once, got " +
                                   std::to_string(landing.logged));
  check(progress.rewardLog.size() == 123, "the log holds 123 entries, got " +
                                              std::to_string(progress.rewardLog.size()));

  const bool hasNote = std::any_of(progress.rewardLog.begin(), progress.rewardLog.end(),
                                   [](const RewardLogEntry& entry) {
                                     return entry.kind == "note" && entry.id == "first:note:note_beach";
                                   });
  check(hasNote, "the note_beach row must be in the log");
  check(std::is_sorted(progress.rewardLog.begin(), progress.rewardLog.end(),
                       [](const RewardLogEntry& a, const RewardLogEntry& b) {
                         if (a.kind != b.kind) return a.kind < b.kind;
                         if (a.id != b.id) return a.id < b.id;
                         return a.amount < b.amount;
                       }),
        "the log is sorted by (kind, id, amount)");

  const std::size_t before = progress.rewardLog.size();
  landRewards(progress, table);
  check(progress.rewardLog.size() == before,
        "a second pass must not duplicate the log, got " +
            std::to_string(progress.rewardLog.size()));
}

/// A save written before the landing fields existed loads with empty vectors, lands normally, and
/// then writes both keys. A duplicated id or log entry collapses on load.
void testOldSaveLandsAndRoundTrips(const fs::path& temp) {
  const fs::path path = temp / "rewards_landing_roundtrip.json";
  Json old = Json::object();
  old["coins"] = 11;
  old["seeds"] = Json::array({"wallnut"});
  const Progress before = parseProgress(old, "rewards_test");
  check(before.unlockedPlants.empty() && before.rewardLog.empty(),
        "an old save has no landing fields");

  Progress landed = before;
  landRewards(landed, RewardTable::shared());
  saveProgress(path, landed, 1'700'000'000);
  const Progress back = loadProgress(path);
  check(back.unlockedPlants == landed.unlockedPlants && back.unlockedPlants.size() == 244,
        "unlockedPlants survives save/load");
  check(back.rewardLog.size() == landed.rewardLog.size() && back.rewardLog == landed.rewardLog,
        "rewardLog survives save/load");
  check(back.coins == 11 && back.seeds == std::vector<std::string>({"wallnut"}),
        "landing leaves the counters and seeds it did not touch alone");

  const Json json = progressToJson(landed);
  check(json.contains("unlockedPlants") && json.contains("rewardLog"),
        "both keys are written once they hold something");
  check(!progressToJson(Progress{}).contains("unlockedPlants"),
        "a save that never landed anything keeps the older byte shape");

  Json duplicated = json;
  duplicated["unlockedPlants"] = Json::array({"aloe", "ailmint", "aloe"});
  duplicated["rewardLog"] = Json::array(
      {Json{{"kind", "note"}, {"id", "b"}, {"amount", 0}},
       Json{{"kind", "note"}, {"id", "b"}, {"amount", 0}},
       Json{{"kind", "note"}, {"id", "a"}, {"amount", 2}}});
  const Progress loaded = parseProgress(duplicated, "rewards_test");
  check(loaded.unlockedPlants == std::vector<std::string>({"ailmint", "aloe"}),
        "unlockedPlants is a set: duplicates collapse and the order is sorted");
  check(loaded.rewardLog.size() == 2 && loaded.rewardLog.front().id == "a",
        "rewardLog is a set ordered by (kind, id, amount)");
}

/// The report line `--rewards-report` prints: the six contract keys, a `byKind` census that adds up,
/// and a closure a reviewer can recompute (landed + unlanded = the 438 counted rows).
void testReportShape() {
  Progress progress;
  const RewardLanding landing = landRewards(progress, RewardTable::shared());
  const Json report = landing.json();
  for (const char* key : {"landed", "unlanded", "byKind", "unlockedPlants", "costumes", "coins"}) {
    check(report.contains(key), std::string("the report must carry `") + key + "`, got " +
                                    report.dump());
  }
  check(report.size() == 6, "the contract names exactly six keys, got " + report.dump());
  check(report["landed"] == 315, "293 plants + 22 costumes, got " + report.dump());
  check(report["unlanded"] == 123, "438 - 315, got " + report.dump());
  check(report["unlockedPlants"] == 244 && report["costumes"] == 15,
        "the report counts the ids it landed, got " + report.dump());
  check(report["coins"] == 0, "the default pass pays no coins, got " + report.dump());
  int byKindTotal = 0;
  for (const auto& [kind, count] : landing.byKind) byKindTotal += count;
  check(byKindTotal == landing.unlanded,
        "byKind is the same census as unlanded, got " + std::to_string(byKindTotal));
  check(landing.landed + landing.unlanded ==
            static_cast<int>(RewardTable::shared().unlandedDetail().size()),
        "landed + unlanded must equal the 438 rows the table counts");
  check(report.dump().find('\n') == std::string::npos, "the report is a single line");
  const Json detail = landing.detail();
  check(detail.contains("reasons") && detail.contains("prices") &&
            detail["reasons"]["unmodelled"] == 64 && detail["reasons"]["price_constant"] == 5 &&
            detail["reasons"]["rift_payout"] == 54,
        "the detail census explains the 123 rows, got " + detail.dump());
  check(detail.size() == 8, "the detail block carries its own eight keys, got " + detail.dump());
  std::cout << "report: " << report.dump() << "\n";
  std::cout << "detail: " << detail.dump() << "\n";
}

/// `unlockedPlantsGained` is a `--run-level` key only when the pass unlocked something: a save that
/// already owns the roster must not grow a key.
void testLandingReceiptIsConditional() {
  Progress fresh;
  const RewardLanding first = landRewards(fresh, RewardTable::shared());
  Json summary = Json::object();
  addLandingReceipt(summary, first);
  check(summary["unlockedPlantsGained"] == 244,
        "the first settle reports the plants it unlocked, got " + summary.dump());

  const RewardLanding second = landRewards(fresh, RewardTable::shared());
  Json repeat = Json::object();
  addLandingReceipt(repeat, second);
  check(!repeat.contains("unlockedPlantsGained"),
        "a second settle adds no key, got " + repeat.dump());
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
  try {
    check(argc >= 3, "usage: rewards_test <content> <temp>");
    const fs::path content(argv[1]);
    const auto catalog = loadCatalog(content);

    testTableCounts();
    testSilverPeriod(catalog);
    testGoldPeriods(catalog);
    testSameSeedSameGain(catalog);
    testKeyWorldAndGate(catalog);
    testPresentLunchBox(catalog);
    testSeedBag(catalog);
    testUnmodelledKinds(catalog);
    testApplyRewardsFoldsTheSave();
    testGemMowerLand(catalog);
    testGemMowerDeltaIsHonest();
    testPlantUnlockIsNotASeedBag();
    testXpAndTrophyFold();
    testReceiptShape();
    testUnlandedCensus();
    testNewSaveFieldsRoundTrip();
    testSeedBagReachesTheReceipt(catalog);
    testKeysUnlockedGate();
    testPlantUnlocksLand();
    testCoinFamiliesDoNotMintCoins();
    testCostumesLand();
    testNoteOnlyRowsAreLogged();
    testOldSaveLandsAndRoundTrips(fs::path(argv[2]));
    testReportShape();
    testLandingReceiptIsConditional();

    std::cout << "rewards tests passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "rewards test failed: " << error.what() << "\n";
    return 1;
  }
}
