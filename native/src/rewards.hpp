// Level rewards: what a finished battle pays into the save.
//
// Everything here is read from `native/generated/rewards_from_pack.json`, which
// `tools/contentc/rewards.py` compiles from the shipped property sheets. Nothing is
// invented: every number below comes from a row, and the rows the client cannot pay
// out (gems, lawn mowers, sprouts, sun in the whack minigame) are reported as
// `unmodelled` instead of being turned into coins.
//
// Three bindings the generated data does **not** carry, and what this file does about them:
//
//   * level -> loot key (`default` / `danger` / `whack` / none). The compiler only ships
//     per-key counts, so the caller passes the key and defaults to `default` (1762 of 1809
//     levels). A level compiled as `NoLoot` therefore still pays silver here; the report
//     states the number and the gap is visible in `settleRewards`' options.
//   * level -> present table. Also counts only. The table name is derived from the level's
//     world (`<world>_normal_01`); a name listed in `danglingPresentTables[].table` is a
//     reference the pack made to a table it never shipped, so it pays nothing and sets
//     `presentTableMissing`. Worlds with no table name at all fall back to
//     `egypt_normal_01`, the table 1313 levels are bound to, and say so in `presentSource`.
//   * `EnabledAfter=egypt3` for the four world keys. There is no world-progress gate table in
//     this client, so the caller decides: `SettlementOptions::keysUnlocked` is that decision.
#pragma once

#include <cstddef>
#include <filesystem>
#include <map>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

#include "progress.hpp"

namespace pvz {

namespace engine {
class World;
}

/// One `LootTable/DefaultLootTable.Entries[]` row that fires on a kill period.
struct LootRow {
    std::string id;         ///< `loot:<UniqueId>:<LootKey>` (UniqueId alone is not unique)
    std::string kind;       ///< `coin`, `key`, `gem`, `mower`, `sprout`, `sun`
    std::string lootType;   ///< `SilverCoin`, `GoldCoin`, `EgyptKey`, ...
    std::string lootKey;    ///< `default`, `danger`, `whack`, or `any` (no LevelLootKey)
    std::string world;      ///< `any`, or the one world whose key this is
    std::string condition;  ///< `tutorial4` / `egypt3` / empty, kept as text
    int period = 1;         ///< kills between drops (seconds when `periodInSeconds`)
    bool periodInSeconds = false;
    int amount = 0;         ///< value of one dropped unit (silver 10, gold 100, key 1)
    int lowCount = 1;       ///< units per period, `amountRange` low / `amount`
    int highCount = 1;      ///< units per period, `amountRange` high / `amount`
    bool constant = false;  ///< the sheet marks this row constant (no roll)

    /// `any` rows ignore the level's loot key; the rest must match it exactly.
    bool appliesTo(std::string_view levelLootKey) const;
};

/// One `PresentTable/.../Entries[]` row: what the end-of-level lunch box holds.
struct PresentRow {
    std::string id;          ///< `present:<table>:<rewardType>`
    std::string table;       ///< `cowboy_normal_01`
    std::string variant;     ///< `normal` / `shiny`
    std::string rewardType;  ///< `coinpack_medium`
    std::string kind;        ///< `coin`, `powerup`, `junk`, `sprout`
    int amount = 0;
    int weight = 0;
    bool enabled = false;    ///< `weight == 0` rows ship disabled: they pay nothing
};

/// One `ZombieDeathSeedDropModuleProperties.SeedDropList[]` row.
struct SeedDropRow {
    std::string id;            ///< `seeddrop:<pkg>:<index>:<plant>`
    std::string pkg;           ///< `pkg_0243_LevelDefinition.json`
    std::string plant;         ///< `threepeater1`
    double dropChance = 0.0;   ///< 0.01 .. 1
    int weight = 0;            ///< weight inside the module's weighted list
    int amount = 1;
};

/// `rewards_from_pack.json`, parsed. Fails loudly: a missing or malformed table is an error,
/// because a silent zero would make every battle pay nothing and look normal.
class RewardTable {
public:
    static constexpr const char* kFileName = "rewards_from_pack.json";

    static RewardTable load(const std::filesystem::path& path);
    static const RewardTable& shared();

    std::size_t lootRows() const { return loot.size(); }
    std::size_t presentRows() const { return present.size(); }
    std::size_t seedRows() const { return seeds.size(); }
    std::size_t danglingTables() const { return danglingPresentTables.size(); }
    /// Rows the table carries whose family this client cannot settle (level first-clear and
    /// replay rewards, rift rewards, gift boxes, constants), by `kind`, sorted. `readTable`
    /// used to drop them silently; the census is what lets the receipt say so.
    const std::map<std::string, int>& unlandedRows() const { return unlanded; }
    std::size_t coinLootRows() const;
    std::size_t keyLootRows() const;

    /// Every shipped row for one table name, in file order (normal and shiny live together).
    std::vector<const PresentRow*> presentFor(std::string_view table) const;
    bool presentTableIsDangling(std::string_view table) const;
    /// The table a level's lunch box would come from, decided by its world.
    std::string presentTableForWorld(std::string_view world) const;
    /// Seed rows whose package is exactly this level package (`pkg_0662` matches
    /// `pkg_0662_LevelDefinition.json`).
    std::vector<const SeedDropRow*> seedRowsForPackage(std::string_view package) const;

    std::vector<LootRow> loot;
    std::vector<PresentRow> present;
    std::vector<SeedDropRow> seeds;
    std::vector<std::string> danglingPresentTables;
    std::vector<std::string> worldKeys;
    std::map<std::string, int> unlanded;  ///< kind -> rows of an unmodelled family
};

/// One `kind` the client cannot pay out, with how many rows asked for it.
struct RewardUnknown {
    std::string kind;
    int count = 0;
};

struct SettlementOptions {
    /// `default`, `danger`, `whack`, or empty for "this level pays no loot".
    std::string lootKey = "default";
    /// `normal` or `shiny`. Every shiny-only entry ships with weight 0, so today this only
    /// changes which table name is looked up, not the amount.
    std::string presentVariant = "normal";
    /// `EnabledAfter=egypt3` for the four world keys. The caller owns this fact.
    bool keysUnlocked = false;
};

/// What one finished battle paid. Plain value: the caller folds it into a save.
struct RewardGain {
    int coins = 0;
    int keys = 0;
    /// In-level gem pickups (`loot:Gem1/Gem2`, `pickup: gem_diamond`, 2 gems every 30/40 kills).
    int gems = 0;
    /// In-level lawn-mower pickups (`loot:LawnMower1..4`, one mower per drop).
    int mowers = 0;
    /// Plant XP. No shipped row reaches this from a battle (every xp row is a rift slot), so
    /// `settleRewards` never sets it; `applyRewards` folds it so the save path is complete.
    int xp = 0;
    std::vector<std::string> seeds;   ///< in drop order, duplicates possible (apply() dedupes)
    /// World trophies. Same shape as `xp`: no battle row can name one yet (the 18 rows are
    /// first-clear rewards the compiler aggregated without their level), so this stays empty
    /// from `settleRewards` and is only folded by `applyRewards`.
    std::vector<std::string> trophies;
    bool presentTableMissing = false;
    std::string presentTable;         ///< the table name that was looked up
    std::string presentSource;        ///< `world`, `egypt_default`, `missing`, or `none`
    int presentCoins = 0;
    std::vector<RewardUnknown> unmodelled;  ///< sorted by kind

    bool empty() const;
    Json json() const;
};

/// What a gain actually changed in the save. Every field is `after - before`, so a duplicate
/// seed or an already-owned trophy does not count: this is the honest "what the player got",
/// and it is what the CLI reports as `*Gained` under `--progress`.
struct RewardDelta {
    int coins = 0;
    int keys = 0;
    int gems = 0;
    int mowers = 0;
    int xp = 0;
    int plants = 0;     ///< seed ids newly added to `Progress::seeds`
    int trophies = 0;   ///< trophy ids newly added to `Progress::trophies`
};

/// Settles one finished battle against `world`'s counters.
///
/// Deterministic: the only randomness is `world.randomBelow`, so the same seed, level and
/// kill count produce the same gain. Call it after the battle is over — it advances the
/// world's RNG, which is why the CLI prints its summary line first (a run without
/// `--progress` never reaches this function and stays byte-identical).
RewardGain settleRewards(const RewardTable& table, engine::World& world,
                         const std::string& levelWorld, const std::string& levelPackage,
                         const SettlementOptions& options = {});

/// Folds a gain into a save: coins and keys add up, seeds stay sorted and unique. Returns what
/// the save actually gained, so a caller reports deltas instead of re-deriving them.
RewardDelta applyRewards(Progress& progress, const RewardGain& gain);

/// Adds the reward receipt keys to a `--run-level` summary: `gemsGained`, `xpGained`,
/// `mowersGained`, `trophiesGained`, `plantsGained`, plus `rewardUnlanded` (the rows the shipped
/// table carries that this client still cannot settle, `[{kind, count}]`, sorted by kind).
/// Kept here rather than inline in `main.cpp` so a test can pin the shape; the CLI calls it only
/// when a save is going to take the gain, which is what keeps a run without `--progress`
/// byte-identical.
void addRewardReceipt(Json& summary, const RewardDelta& gained, const RewardTable& table);

/// Whether the save has cleared `egypt_3`, the gate the key rows name in `EnabledAfter`.
bool keysUnlocked(const Progress& progress);

}  // namespace pvz
