// Player progress: star goals, per-level records and the save file that holds them.
//
// The star goals come from `content/stars.json` (authored for this client, one
// list per level, 1809 entries). Nothing in the original property sheets
// describes them, so this file never claims they are original data: it reads
// what the content pack ships and evaluates it against a finished `World`.
#pragma once

#include <cstdint>
#include <filesystem>
#include <map>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace pvz {

using Json = nlohmann::json;

namespace engine {
class World;
}

/// Goal kinds understood by `evaluateStars`. Anything else is kept as
/// `unknown` so a typo in the content data shows up in the report instead of
/// silently passing or failing.
enum class StarKind {
  beat,
  mowers,
  kill,
  /// The four kinds below exist in `content/stars.json` (sun_used 31,
  /// sun_produced 61, plants_lost 36, time 5) but the engine does not count the
  /// quantities they ask for yet, so they evaluate to `false` and are reported
  /// as `unmeasured` instead of pretending to pass.
  sun_used,
  sun_produced,
  plants_lost,
  time_limit,
  unknown,
};

bool starKindIsMeasured(StarKind kind);

StarKind starKindOf(const std::string& text);
const char* starKindName(StarKind kind);

struct StarGoal {
  StarKind kind = StarKind::unknown;
  std::string typeText;      ///< exactly what the content file said
  double value = 0.0;        ///< `value` field; for mowers it is "how many must survive"
  int count = 0;             ///< `count` when present, otherwise `value`
  bool hasCount = false;
  double max = 0.0;          ///< `max` field when present (mowers uses 0 = no losses)
  double target = 0.0;       ///< `target` field when present (sun_produced)
  double seconds = 0.0;      ///< `seconds` field when present (time)
  std::string text;          ///< `text_zh`, kept verbatim for the UI
};

struct StarTable {
  std::map<std::string, std::vector<StarGoal>> levels;
  std::size_t goals = 0;
  std::size_t unknownKinds = 0;
  std::map<std::string, std::size_t> byKind;  ///< goal counts per `type` string

  const std::vector<StarGoal>* find(const std::string& levelId) const;
};

/// Reads `content/stars.json`. A missing file is an error: silently starting
/// with zero stars would make every level look unplayed.
StarTable loadStarTable(const std::filesystem::path& path);
StarTable parseStarTable(const std::string& text, const std::string& origin);

struct LevelRecord {
  bool cleared = false;
  int stars = 0;
  int attempts = 0;
  std::uint64_t bestTick = 0;              ///< fastest win in ticks; 0 = never won
  std::vector<bool> goals;                 ///< per-goal pass flags, same order as the table

  bool operator==(const LevelRecord& other) const;
};

/// The three volume buses the settings screen exposes, plus the global mute switch.
///
/// Percentages are integers 0..100 so the save file and the screen agree without rounding, and
/// `master` is the same number `--volume` sets: the mixer still multiplies master x bus x gain x
/// fade, the save just remembers what the player picked. `muted` is the `M` key, not a fourth
/// volume, because "silence everything now" must not destroy the three picks.
struct AudioSettings {
  int master = 100;
  int music = 100;
  int sfx = 100;
  bool muted = false;

  bool operator==(const AudioSettings& other) const;
  bool operator!=(const AudioSettings& other) const { return !(*this == other); }
  bool isDefault() const;
};

/// Clamps every bus into 0..100. A save written by hand (or a future slider that can overshoot)
/// is never allowed to hand the mixer a gain above 1.
AudioSettings clampAudioSettings(AudioSettings settings);

/// `{master, music, sfx, muted}` - the exact shape the settings screen prints and the save
/// stores. Kept next to `Progress` because the file, not the screen, is the source of truth.
Json audioSettingsJson(const AudioSettings& settings);

/// Reads an `audio` block. Missing or malformed members fall back to the defaults one by one, so
/// a save that only remembers `master` keeps working; this is what makes older saves readable.
AudioSettings readAudioSettings(const Json& json);

/// One reward row the save took note of without acting on it.
///
/// The shipped table carries 438 rows this client cannot pay out (see `rewards.hpp`). Writing
/// them into `Progress::rewardLog` is what keeps "the pack asked for this" answerable after the
/// fact: it is a record, not a payout, and the caller must not read it as owning anything.
struct RewardLogEntry {
  std::string kind;  ///< the row's `kind` column: `note`, `pinata`, `xp`, `trophy`, ...
  std::string id;    ///< the compiled row id, so the entry can be traced back to the sheet
  int amount = 0;    ///< the row's amount when it carries one, 0 otherwise

  bool operator==(const RewardLogEntry& other) const;
  bool operator!=(const RewardLogEntry& other) const { return !(*this == other); }
};

/// Sorts by (kind, id, amount) and drops duplicates. Landing the same table twice must not grow
/// the log, so this is the canonical form both the parser and the landing pass produce.
void sortUniqueRewardLog(std::vector<RewardLogEntry>& log);

struct Progress {
  int version = 1;
  std::int64_t updated = 0;
  int keys = 0;
  int coins = 0;
  /// Gems. The shop ships two coin-priced rows that grant gems
  /// (`payload.gems`), so this counter needs somewhere to live. No shipped row is *payable*
  /// in gems yet: `purchase()` still refuses gem-priced rows, which is why the counter has an
  /// income and no sink today. Say so instead of pretending the currency is playable.
  int gems = 0;
  /// Lawn mowers held as spares. The only rows that pay this are in-level `LawnMower` loot
  /// pickups (`loot:LawnMower1..4:any`, `pickup: lawn_mower`), and the row carries no value
  /// field: one drop is one mower. A count is the honest shape - the save cannot say *which*
  /// lane to repair, so this is an extra-mower inventory, not a repair flag.
  int mowers = 0;
  /// Plant XP, cumulative. Every shipped row that pays it names a rift slot
  /// (`rift-boss:a0:d0:2:plantXP`, attempt x difficulty), which this client cannot address yet,
  /// so nothing writes the field today. It exists so the save shape is fixed before the rift
  /// mode lands, and `applyRewards` already folds it.
  int xp = 0;
  /// Extra plant-food slots bought in the shop (`payload.plantfood_slots`, +1 each, two rows).
  int plantfoodSlots = 0;
  /// The plant-food refresh upgrade (`payload.plantfood_refresh`). One shipped row, a one-off
  /// unlock, so a bool is the honest shape rather than a counter.
  bool plantfoodRefresh = false;
  /// Costume ids the player owns, sorted and unique. `purchase()` writes here for
  /// `payload.costume_id`; nothing renders them yet, so this is ownership only.
  std::vector<std::string> costumes;
  /// Client settings bought or unlocked in the shop (`payload.setting`). Value is kept as the
  /// JSON the row carried (bool or number) so a switch and a level both round-trip; a row whose
  /// `setting` names a resource counter (mints/event_energy/sprouts) is refused instead of
  /// being stored here - those are inventories, not preferences.
  std::map<std::string, Json> settings;
  /// The settings screen's own state. A separate field, not an entry in `settings`: those are shop
  /// switches keyed by row id, and overloading them would let a shop row rename a volume.
  AudioSettings audio;
  /// Shop rows already bought, sorted. Currency is spent by `purchase()` in shop.cpp; this
  /// list is what makes "already owned" answerable across sessions.
  std::vector<std::string> purchases;
  /// Seeds the player owns, sorted. `purchase()` appends here for rows whose payload is a
  /// `plant_id`; costumes, keys, gems, plant-food upgrades and settings land in the fields
  /// above, so a purchase never has to be modelled as a seed to be delivered.
  std::vector<std::string> seeds;
  /// World trophies owned, sorted and unique. The pack's 18 trophy rows are `worldtrophy_*` /
  /// `worldkey_*` / `dangerroom_*` first-clear rewards, and a row does not name the level that
  /// grants it (the compiler aggregated them: `levels: 1|2|4`), so nothing can fill this yet.
  /// The field and its fold exist so the save shape is fixed.
  std::vector<std::string> trophies;
  /// Plants unlocked by a `first:unlock_plant:<plant>` reward row, sorted and unique. The pack
  /// ships 293 such rows and a row does not name the level that grants it (the compiler
  /// aggregated them: `levels: 1`), so this list records ownership, not "the level that gave it".
  /// Separate from `seeds`: a seed is a plantable packet you can buy, an unlock is a plant the
  /// roster may now offer at all.
  std::vector<std::string> unlockedPlants;
  /// Rows the shipped table carries that this client records but cannot act on, sorted and unique
  /// by (kind, id, amount). See `RewardLogEntry` and `rewards.hpp`.
  std::vector<RewardLogEntry> rewardLog;
  /// The last level the player finished, win or lose. The menu needs one fact to answer
  /// "continue": without it, "继续游戏" could only guess from `levels` and would restart the
  /// earliest unfinished world instead of the one being played.
  std::string lastLevel;
  /// B1 (T90): the battle level each plant fights at, `plant type -> level`. Absent means 1, which is
  /// what every save written before this field existed says by saying nothing - so a default save
  /// stays byte-identical through a round trip. `std::map` gives the sorted, one-entry-per-plant
  /// shape for free; the sheet's own cap is applied by `engine::clampPlantLevel` at the point a
  /// battle reads it, not here, because a save must not need the generated tree to load.
  std::map<std::string, int> plantLevels;
  std::map<std::string, LevelRecord> levels;

  int totalStars() const;
  int clearedLevels() const;
  const LevelRecord* find(const std::string& levelId) const;
};

struct StarOutcome {
  std::vector<bool> passed;
  int stars = 0;
};

/// What one finished attempt achieved, read from `engine::World`'s public getters only.
///
/// A plain value on purpose: the CLI and the tests can hand it around after the world is
/// gone, and `recordBattle` needs no engine link to fold it into a save.
struct BattleOutcome {
  bool won = false;
  std::uint64_t tick = 0;   ///< ticks the attempt ran, win or lose
  int sun = 0;              ///< sun left in the bank at the end
  int sunSpent = 0;         ///< everything spent on planting and fusing
  int mowersLeft = 0;       ///< mowers that never fired
  int zombiesKilled = 0;    ///< damage kills; lawn-mower kills excluded by the engine
  int plantsLost = 0;       ///< plants that died of damage; shovelled/fused ones excluded
};

/// Snapshots a finished (or abandoned) world. Uses `status/tick/sun/sunSpent/mowersLeft/
/// killedZombies/plantsLost` and nothing else, so it cannot disagree with `evaluateStars`.
BattleOutcome outcomeOf(const engine::World& world);

/// Evaluates one finished attempt. `world` may be in any state; a goal only
/// passes when the attempt actually satisfied it.
///
/// | kind | passes when |
/// |---|---|
/// | `beat` | `world.status() == "won"` |
/// | `mowers` | mowers still ready (`state == 0`) is at least `value` |
/// | `kill` | `world.killedZombies() >= count` |
StarOutcome evaluateStars(const std::vector<StarGoal>& goals, const engine::World& world);

/// Same evaluation over a recorded outcome. `evaluateStars(goals, world)` is exactly
/// `evaluateStars(goals, outcomeOf(world))`; the engine-free overload is what `recordBattle`
/// uses so a save can be updated without a live world.
StarOutcome evaluateStars(const std::vector<StarGoal>& goals, const BattleOutcome& outcome);

/// Missing file or empty object yields a default `Progress`; malformed JSON is
/// an error so a corrupted save is never silently replaced.
Progress loadProgress(const std::filesystem::path& path);
Progress parseProgress(const Json& json, const std::string& origin);

/// Writes through a temporary file in the same directory, then renames, so an
/// interrupted save cannot leave a half-written file. Creates parent directories.
void saveProgress(const std::filesystem::path& path, Progress progress, std::int64_t now);

/// Folds one attempt into `progress`: stars never regress, attempts always
/// increase, and `bestTick` keeps the fastest win.
Progress recordAttempt(Progress progress, const std::string& levelId,
                       const std::vector<StarGoal>& goals, const engine::World& world);

/// Folds one finished attempt into a save. Identical bookkeeping to `recordAttempt`, but it
/// takes the recorded `BattleOutcome`: attempts always increase (a loss counts as an
/// attempt), stars and `cleared` never regress, and `bestTick` keeps the fastest win.
void recordBattle(Progress& progress, const std::string& levelId, const BattleOutcome& outcome,
                  const StarTable& table);

/// Machine-readable progress for the CLI and the world map:
/// `{totalStars, cleared, levels: {id: {cleared, stars, attempts, bestTick, target, goals[]}}}`.
/// `target` is how many goals the star table ships for that level, so a caller can tell
/// "2 of 3" from "2 of 2".
Json progressReport(const Progress& progress, const StarTable& table);

Json progressToJson(const Progress& progress);

}  // namespace pvz
