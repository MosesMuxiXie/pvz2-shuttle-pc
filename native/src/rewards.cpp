#include "rewards.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <stdexcept>
#include <utility>

#include "engine/plantfood.hpp"
#include "engine/world.hpp"

namespace pvz {
namespace {

using Json = nlohmann::json;

std::string stringOr(const Json& object, const char* key) {
    const auto it = object.find(key);
    if (it == object.end() || !it->is_string()) return {};
    return it->get<std::string>();
}

double numberOr(const Json& object, const char* key, double fallback = 0.0) {
    const auto it = object.find(key);
    if (it == object.end()) return fallback;
    if (it->is_number()) return it->get<double>();
    if (it->is_string()) {
        try {
            return std::stod(it->get<std::string>());
        } catch (const std::exception&) {
            return fallback;
        }
    }
    return fallback;
}

int intOr(const Json& object, const char* key, int fallback = 0) {
    return static_cast<int>(numberOr(object, key, static_cast<double>(fallback)));
}

bool boolOr(const Json& object, const char* key, bool fallback = false) {
    const auto it = object.find(key);
    if (it == object.end()) return fallback;
    if (it->is_boolean()) return it->get<bool>();
    if (it->is_number()) return it->get<double>() != 0.0;
    return fallback;
}

/// `amountRange` is `[low, high]` in the sheet's own units; `amount` is one unit, so a
/// silver row of `10` with `[10, 30]` means "one to three coins". A null or flat range is
/// exactly one unit, which is also what rows without a range mean.
std::pair<int, int> countsOf(const Json& object) {
    const int amount = intOr(object, "amount", 0);
    const auto it = object.find("amountRange");
    if (it == object.end() || !it->is_array() || it->size() < 2 || amount <= 0) {
        return {1, 1};
    }
    const double low = (*it)[0].is_number() ? (*it)[0].get<double>() : 0.0;
    const double high = (*it)[1].is_number() ? (*it)[1].get<double>() : 0.0;
    int lowCount = static_cast<int>(std::lround(low / amount));
    int highCount = static_cast<int>(std::lround(high / amount));
    if (lowCount <= 0) lowCount = 1;
    if (highCount < lowCount) highCount = lowCount;
    return {lowCount, highCount};
}

/// Splits `loot:<UniqueId>:<LootKey>` into its three fields; other id shapes keep what they
/// have, because the id is only used for tracing.
void splitLootId(const std::string& id, LootRow& row) {
    if (id.rfind("loot:", 0) != 0) return;
    const std::size_t first = id.find(':', 5);
    if (first == std::string::npos) return;
    const std::size_t second = id.find(':', first + 1);
    if (second == std::string::npos) return;
    if (row.lootKey.empty()) row.lootKey = id.substr(second + 1);
}

/// Splits `present:<table>:<rewardType>` / `seeddrop:<pkg>:<index>:<plant>`.
std::vector<std::string> splitId(const std::string& id) {
    std::vector<std::string> parts;
    std::size_t start = 0;
    while (start <= id.size()) {
        const std::size_t colon = id.find(':', start);
        if (colon == std::string::npos) {
            parts.push_back(id.substr(start));
            break;
        }
        parts.push_back(id.substr(start, colon - start));
        start = colon + 1;
    }
    return parts;
}

RewardTable readTable(const std::filesystem::path& path) {
    std::ifstream stream(path);
    if (!stream) {
        throw std::runtime_error("rewards table: " + path.string() + ": cannot open");
    }
    Json root;
    try {
        stream >> root;
    } catch (const std::exception& error) {
        throw std::runtime_error("rewards table: " + path.string() + ": " + error.what());
    }
    if (!root.is_object()) {
        throw std::runtime_error("rewards table: " + path.string() + ": root is not a JSON object");
    }
    const auto rows = root.find("rewards");
    if (rows == root.end() || !rows->is_array()) {
        throw std::runtime_error("rewards table: " + path.string() + ": no rewards array");
    }

    RewardTable table;
    for (const Json& entry : *rows) {
        if (!entry.is_object()) continue;
        const std::string id = stringOr(entry, "id");
        if (id.empty()) continue;
        const std::string kind = stringOr(entry, "kind");

        const auto period = entry.find("period");
        if (period != entry.end() && period->is_number()) {
            LootRow row;
            row.id = id;
            row.kind = kind;
            row.lootType = stringOr(entry, "lootType");
            row.lootKey = stringOr(entry, "lootKey");
            row.world = stringOr(entry, "world");
            row.condition = stringOr(entry, "condition");
            row.period = std::max(1, intOr(entry, "period", 1));
            row.periodInSeconds = stringOr(entry, "periodUnit") == "seconds";
            row.amount = intOr(entry, "amount", 0);
            const auto [low, high] = countsOf(entry);
            row.lowCount = low;
            row.highCount = high;
            row.constant = boolOr(entry, "constant", false);
            splitLootId(id, row);
            table.loot.push_back(std::move(row));
            continue;
        }

        if (kind == "seed") {
            SeedDropRow row;
            row.id = id;
            row.pkg = stringOr(entry, "pkg");
            row.plant = stringOr(entry, "rewardType");
            row.dropChance = numberOr(entry, "dropChance", 0.0);
            row.weight = intOr(entry, "weight", 0);
            row.amount = std::max(1, intOr(entry, "amount", 1));
            if (row.plant.empty()) continue;
            table.seeds.push_back(std::move(row));
            continue;
        }

        if (id.rfind("present:", 0) == 0) {
            PresentRow row;
            row.id = id;
            const std::vector<std::string> parts = splitId(id);
            if (parts.size() >= 3) {
                row.table = parts[1];
                row.rewardType = parts[2];
            }
            row.variant = stringOr(entry, "variant");
            row.kind = kind;
            row.amount = intOr(entry, "amount", 0);
            row.weight = intOr(entry, "weight", 0);
            row.enabled = boolOr(entry, "enabled", false);
            table.present.push_back(std::move(row));
            continue;
        }

        // Everything left is a family this client cannot settle: `first:`/`replay:` level
        // rewards (the compiler aggregated them without the level they belong to), rift
        // first-clear/zomboss rows, gift-box openings and the per-world constants. Counting them
        // by kind is what stops 438 of the 575 rows from being invisible.
        if (!kind.empty()) ++table.unlanded[kind];
    }

    if (const auto dangling = root.find("danglingPresentTables");
        dangling != root.end() && dangling->is_array()) {
        for (const Json& entry : *dangling) {
            if (!entry.is_object()) continue;
            const std::string name = stringOr(entry, "table");
            if (!name.empty()) table.danglingPresentTables.push_back(name);
        }
    }
    if (const auto keys = root.find("worldKeys"); keys != root.end() && keys->is_array()) {
        for (const Json& entry : *keys) {
            if (entry.is_string()) table.worldKeys.push_back(entry.get<std::string>());
        }
    }

    if (table.loot.empty() && table.present.empty() && table.seeds.empty()) {
        throw std::runtime_error("rewards table: " + path.string() + ": the table is empty");
    }
    return table;
}

/// Deterministic weighted pick over the module's rows. Falls back to the first row when the
/// weights are all zero, so a broken weight column cannot silently stop drops.
const SeedDropRow& pickWeighted(const std::vector<const SeedDropRow*>& rows, engine::World& world) {
    int total = 0;
    for (const SeedDropRow* row : rows) total += std::max(0, row->weight);
    if (total <= 0) return *rows.front();
    int roll = static_cast<int>(world.randomBelow(static_cast<std::uint32_t>(total)));
    for (const SeedDropRow* row : rows) {
        roll -= std::max(0, row->weight);
        if (roll < 0) return *row;
    }
    return *rows.back();
}

}  // namespace

bool LootRow::appliesTo(std::string_view levelLootKey) const {
    // `any` rows carry no LevelLootKey in the sheet: the four world keys and the gem/mower
    // rows are in every level of their world, not just the `default` subset.
    if (lootKey.empty() || lootKey == "any") return true;
    return lootKey == levelLootKey;
}

RewardTable RewardTable::load(const std::filesystem::path& path) { return readTable(path); }

const RewardTable& RewardTable::shared() {
    static const RewardTable table = [] {
        const std::filesystem::path directory = engine::generatedDir();
        if (directory.empty()) {
            throw std::runtime_error(
                "rewards table: the generated directory is unknown; build with "
                "PVZ_GENERATED_DIR or set it in the environment");
        }
        return readTable(directory / kFileName);
    }();
    return table;
}

std::size_t RewardTable::coinLootRows() const {
    return static_cast<std::size_t>(
        std::count_if(loot.begin(), loot.end(), [](const LootRow& row) { return row.kind == "coin"; }));
}

std::size_t RewardTable::keyLootRows() const {
    return static_cast<std::size_t>(
        std::count_if(loot.begin(), loot.end(), [](const LootRow& row) { return row.kind == "key"; }));
}

std::vector<const PresentRow*> RewardTable::presentFor(std::string_view tableName) const {
    std::vector<const PresentRow*> rows;
    for (const PresentRow& row : present) {
        if (row.table == tableName) rows.push_back(&row);
    }
    return rows;
}

bool RewardTable::presentTableIsDangling(std::string_view tableName) const {
    return std::find(danglingPresentTables.begin(), danglingPresentTables.end(), tableName) !=
           danglingPresentTables.end();
}

std::string RewardTable::presentTableForWorld(std::string_view world) const {
    return std::string(world) + "_normal_01";
}

std::vector<const SeedDropRow*> RewardTable::seedRowsForPackage(std::string_view package) const {
    std::vector<const SeedDropRow*> rows;
    if (package.empty()) return rows;
    const std::string prefix = std::string(package) + "_LevelDefinition";
    for (const SeedDropRow& row : seeds) {
        if (row.pkg.rfind(prefix, 0) == 0) rows.push_back(&row);
    }
    return rows;
}

bool RewardGain::empty() const {
    return coins == 0 && keys == 0 && gems == 0 && mowers == 0 && xp == 0 && seeds.empty() &&
           trophies.empty() && !presentTableMissing && unmodelled.empty();
}

Json RewardGain::json() const {
    Json kinds = Json::array();
    for (const RewardUnknown& unknown : unmodelled) {
        kinds.push_back(Json{{"kind", unknown.kind}, {"count", unknown.count}});
    }
    return Json{{"coins", coins},
                {"keys", keys},
                {"gems", gems},
                {"mowers", mowers},
                {"xp", xp},
                {"seeds", seeds},
                {"trophies", trophies},
                {"presentTable", presentTable},
                {"presentSource", presentSource},
                {"presentTableMissing", presentTableMissing},
                {"presentCoins", presentCoins},
                {"unmodelled", std::move(kinds)}};
}

RewardGain settleRewards(const RewardTable& table, engine::World& world,
                         const std::string& levelWorld, const std::string& levelPackage,
                         const SettlementOptions& options) {
    RewardGain gain;
    const std::uint64_t kills = world.killedZombies();
    std::map<std::string, int> unmodelled;

    for (const LootRow& row : table.loot) {
        if (!row.appliesTo(options.lootKey)) continue;
        // The `whack` sun rows are on a seconds clock in a minigame the kernel does not run;
        // they are counted as unmodelled below rather than converted to kills.
        if (row.periodInSeconds) {
            ++unmodelled[row.kind];
            continue;
        }
        if (row.kind == "key" && row.world != "any" && row.world != levelWorld) continue;
        if (row.kind == "key" && !options.keysUnlocked) continue;

        const std::uint64_t drops = kills / static_cast<std::uint64_t>(std::max(1, row.period));
        if (drops == 0) continue;
        // Kinds the save can hold: two currencies (`coins`, `keys`) and two item counts
        // (`gems`, `mowers`). Sprouts and the whack sun still have nowhere to go, so one row
        // that fires is counted once rather than converted into coins.
        const bool landable = row.kind == "coin" || row.kind == "key" || row.kind == "gem" ||
                              row.kind == "mower";
        if (!landable) {
            ++unmodelled[row.kind];
            continue;
        }
        for (std::uint64_t drop = 0; drop < drops; ++drop) {
            int count = row.lowCount;
            if (!row.constant && row.highCount > row.lowCount) {
                const auto span = static_cast<std::uint32_t>(row.highCount - row.lowCount + 1);
                count = row.lowCount + static_cast<int>(world.randomBelow(span));
            }
            const int value = count * std::max(0, row.amount);
            if (row.kind == "coin") {
                gain.coins += value;
            } else if (row.kind == "key") {
                gain.keys += value;
            } else if (row.kind == "gem") {
                gain.gems += value;
            } else {
                gain.mowers += value;
            }
        }
    }

    // End-of-level lunch box. The pack names a table per level; the compiler only shipped the
    // per-table level counts, so the world name is the binding this client has.
    const std::string derived = levelWorld + "_" + options.presentVariant + "_01";
    gain.presentTable = derived;
    if (table.presentTableIsDangling(derived)) {
        gain.presentTableMissing = true;
        gain.presentSource = "missing";
    } else {
        std::vector<const PresentRow*> rows = table.presentFor(derived);
        std::string resolved = derived;
        if (rows.empty()) {
            // egypt_normal_01 is what 1313 levels are bound to; using it is a stated fallback,
            // not "give them 100 coins when the table is missing" (that path is above).
            const std::string fallback = "egypt_" + options.presentVariant + "_01";
            rows = table.presentFor(fallback);
            if (!rows.empty()) {
                resolved = fallback;
                gain.presentSource = "egypt_default";
            } else {
                gain.presentSource = "none";
            }
        } else {
            gain.presentSource = "world";
        }
        gain.presentTable = resolved;
        if (!rows.empty()) {
            if (world.status() != "won") {
                // A lunch box is a completion reward: a lost battle pays none of it.
                gain.presentSource += "_not_cleared";
            } else {
                for (const PresentRow* row : rows) {
                    if (!row->enabled || row->weight <= 0) continue;
                    if (row->kind != "coin") {
                        ++unmodelled[row->kind];
                        continue;
                    }
                    gain.presentCoins += row->amount;
                }
                gain.coins += gain.presentCoins;
            }
        }
    }

    // Per-kill seed bag. Only the 15 levels whose package carries the module have rows here.
    const std::vector<const SeedDropRow*> seedRows = table.seedRowsForPackage(levelPackage);
    if (!seedRows.empty() && kills > 0) {
        // One `ZombieDeathSeedDropModuleProperties` per package, and every row in it repeats the
        // same `DropChance` (checked over all 15 modules). Taking the maximum keeps that true if
        // a future compile ever publishes a per-row chance instead of a per-module one.
        double chance = 0.0;
        for (const SeedDropRow* row : seedRows) chance = std::max(chance, row->dropChance);
        constexpr std::uint32_t scale = 1000000;
        for (std::uint64_t kill = 0; kill < kills && chance > 0.0; ++kill) {
            const double roll =
                static_cast<double>(world.randomBelow(scale)) / static_cast<double>(scale);
            if (roll >= chance) continue;
            const SeedDropRow& picked = pickWeighted(seedRows, world);
            for (int copy = 0; copy < std::max(1, picked.amount); ++copy) {
                gain.seeds.push_back(picked.plant);
            }
        }
    }

    for (const auto& [kind, count] : unmodelled) {
        gain.unmodelled.push_back(RewardUnknown{kind, count});
    }
    std::sort(gain.unmodelled.begin(), gain.unmodelled.end(),
              [](const RewardUnknown& a, const RewardUnknown& b) { return a.kind < b.kind; });
    return gain;
}

RewardDelta applyRewards(Progress& progress, const RewardGain& gain) {
    const int coinsBefore = progress.coins;
    const int keysBefore = progress.keys;
    const int gemsBefore = progress.gems;
    const int mowersBefore = progress.mowers;
    const int xpBefore = progress.xp;
    const std::size_t seedsBefore = progress.seeds.size();
    const std::size_t trophiesBefore = progress.trophies.size();

    progress.coins += gain.coins;
    progress.keys += gain.keys;
    progress.gems += gain.gems;
    progress.mowers += gain.mowers;
    progress.xp += gain.xp;
    progress.seeds.insert(progress.seeds.end(), gain.seeds.begin(), gain.seeds.end());
    std::sort(progress.seeds.begin(), progress.seeds.end());
    progress.seeds.erase(std::unique(progress.seeds.begin(), progress.seeds.end()),
                         progress.seeds.end());
    progress.trophies.insert(progress.trophies.end(), gain.trophies.begin(), gain.trophies.end());
    std::sort(progress.trophies.begin(), progress.trophies.end());
    progress.trophies.erase(std::unique(progress.trophies.begin(), progress.trophies.end()),
                            progress.trophies.end());

    RewardDelta delta;
    delta.coins = progress.coins - coinsBefore;
    delta.keys = progress.keys - keysBefore;
    delta.gems = progress.gems - gemsBefore;
    delta.mowers = progress.mowers - mowersBefore;
    delta.xp = progress.xp - xpBefore;
    delta.plants = static_cast<int>(progress.seeds.size() - seedsBefore);
    delta.trophies = static_cast<int>(progress.trophies.size() - trophiesBefore);
    return delta;
}

void addRewardReceipt(Json& summary, const RewardDelta& gained, const RewardTable& table) {
    summary["gemsGained"] = gained.gems;
    summary["xpGained"] = gained.xp;
    summary["mowersGained"] = gained.mowers;
    summary["trophiesGained"] = gained.trophies;
    summary["plantsGained"] = gained.plants;
    Json unlanded = Json::array();
    for (const auto& [kind, count] : table.unlandedRows()) {
        unlanded.push_back(Json{{"kind", kind}, {"count", count}});
    }
    summary["rewardUnlanded"] = std::move(unlanded);
}

bool keysUnlocked(const Progress& progress) {
    const LevelRecord* egypt = progress.find("egypt_3");
    return egypt != nullptr && egypt->cleared;
}

}  // namespace pvz
