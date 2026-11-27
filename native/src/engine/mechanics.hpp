// S5.13 mechanics wiring: the per-level mechanics sheet, read once from
// generated/level_mechanics.json.
//
// Every level's `LevelDefinition` package says which modules run: a conveyor belt instead of a
// seed bank, plants already standing on the lawn, gravestones that block planting, a "protect
// the plant" mission. Before this the kernel ignored all of it, so 350 conveyor levels, 690
// levels with grid items and 286 protect missions played as an ordinary level - the worst kind
// of green, because the run still finished and still reported a status.
//
// This header stays SDL-free so the audit build, the engine and the view all read one table.
// T88 wired the Events module's two documented kinds (tide changes and frost winds), the
// board-grid mask (as data - its codes carry no documented meaning) and the one mutator that
// states a rule (`maxSunOverride`). What is still *named and counted* rather than silently
// dropped: `spawners.spider`, the `fish` creature entries, the mutator challenge wrappers
// (`LevelTimer`, `KillZombies1`...), and any row whose wave the sheet left empty. A level that
// quietly lost its tide is indistinguishable from a level that never had one, which is why the
// counts exist.
// The special spawners (`spawners.grid/portal/storm/ground/dino/beach/fish`) are wired since T66.
#pragma once
#include <cstddef>
#include <filesystem>
#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace pvz::engine {

/// One plant the level lays down before the first tick (`initialPlantPlacements`).
/// `gridX` is the column, `gridY` the row - the sheet stores them in that order.
struct InitialPlant {
    std::string plant;
    int gridX = 0;
    int gridY = 0;
};

/// One grid item: a gravestone, a puddle, a tombstone - something that stands on a cell but is
/// not a plant. It blocks planting and can be shovelled or blown up, and zombies walk over it.
struct GridItemPlacement {
    std::string item;
    int gridX = 0;
    int gridY = 0;
    /// 0 for the items a level starts with, the wave number for a gravestone drop.
    int wave = 0;
};

/// One row of a conveyor's weighted plant table (`ConveyorBelt.slots`).
struct ConveyorSlotRow {
    std::string plant;
    double weight = 1.0;
};

struct ConveyorSpec {
    std::string alias;
    std::vector<ConveyorSlotRow> slots;
    /// `dropDelayConditions[].delay` in seconds: when the belt is empty, the next packet
    /// arrives after this many seconds. Sorted ascending; the first entry is the base rate.
    std::vector<int> dropDelays;
    int totalWeight = 0;
    bool empty() const { return slots.empty(); }
};

struct ProtectSpec {
    bool failWhenProtectedPlantDies = false;
    /// How many of the protected plants must survive. `-1` means the sheet did not say, in which
    /// case the mission falls back to "all of them" (when the fail flag is set). `0` is a real
    /// value and means the mission places the plants as window dressing: `egypt_56` lists fifteen
    /// and requires none, so killing them cannot lose the level.
    int mustProtectCount = -1;
    std::vector<InitialPlant> plants;
    bool empty() const { return plants.empty(); }
    /// The threshold the kernel judges against, resolved the way the sheet means it.
    int requiredSurvivors() const;
};

/// A wave-triggered gravestone drop (`spawners.gravestone`).
struct GravestoneWave {
    int wave = 0;
    std::vector<GridItemPlacement> positions;
};

/// The special spawner modules a level can declare. `jittered` is the ordinary wave table (the
/// director already runs it) and `gravestone` is `GravestoneWave` above, so neither is here.
enum class SpawnerKind { grid, portal, storm, spider, ground, dino, beach, fish };

/// `SpawnerKind::grid` -> "spawners.grid", the key the report and `--run-level` print.
const char* spawnerKindName(SpawnerKind kind);
/// The kinds this kernel actually spawns for. `spider` is absent on purpose: carnival's
/// `spiderCount` rows name no enemy, and neither the 55 content zombies nor the 1127 pack
/// zombies contain a spider, so there is nothing to place on the lawn.
bool spawnerKindIsWired(SpawnerKind kind);

/// One `zombies[]` / `fishes[]` entry of a spawner row.
struct SpawnerZombie {
    std::string type;
    /// The row the sheet pinned this individual to, or -1 for "any row".
    int row = -1;
};

/// One spawner row. A row combines the four things the sheet gives every spawner: *when*
/// (`wave`), *where* (`columnStart`/`columnEnd`, `row`), *who* (`zombies`) and *how many at a
/// time* (`groupSize`/`betweenGroups`, `count`). The kernel runs the arrival only: the zombie
/// appears on the lawn and walks; the storm clouds, portals and dino are reported as events.
struct SpawnerRow {
    SpawnerKind kind = SpawnerKind::grid;
    std::string alias;
    /// 1-based wave that triggers the row. 0 means the sheet left `wave` empty; such a row is
    /// never scheduled and is reported as `spawners.<kind>.unscheduled` instead of being run at
    /// a wave the data does not name.
    int wave = 0;
    int columnStart = -1;
    int columnEnd = -1;
    /// `dinoRow` for a dino sweep; otherwise a single pinned row for the whole row.
    int row = -1;
    int groupSize = 0;
    /// Seconds between groups (`timeBetweenGroups`).
    double betweenGroups = 0.0;
    /// `grid.zombieSpawnWaitTime`: seconds after the wave before the zombies climb out.
    double waitSeconds = 0.0;
    /// `spiderCount` / `beach.zombieCount`; 0 when the kind counts its own `zombies` entries.
    int count = 0;
    std::vector<SpawnerZombie> zombies;

    bool scheduled() const { return wave > 0; }
};

struct SpawnerSpec {
    SpawnerKind kind = SpawnerKind::grid;
    std::vector<SpawnerRow> rows;
    bool empty() const { return rows.empty(); }
};

/// One tide change of the level's Events module (`TidalChangeWaveActionProps`): at `wave` the
/// waterline moves to `column`. The sheet's `ChangeType` is carried verbatim because only
/// `absolute` names a destination the kernel can honour; a relative type would have to know the
/// waterline it starts from, which no shipped row names.
struct TideChange {
    int wave = 0;
    int column = 0;
    std::string changeType;
};

/// One frost wind (`FrostWindWaveActionProps.Winds[]`): at `wave` the wind blows over `rows`.
/// The sheet's `Row` is `-1` for "every row", which is stored as a literal -1 entry here.
struct FrostWind {
    int wave = 0;
    std::vector<int> rows;
    std::string direction;
};

/// `BoardGridMapProps.Values`: the level's 5x9 cell-code matrix.
///
/// The sheet documents no meaning for the codes (`tools/contentc/level_extra_rules.py` R02 says
/// so in as many words: "0/1 的含义原版没有字段说明"), and every one of the 49 shipped levels has
/// exactly one map at 5x9 - the board never changes shape. So the kernel carries the matrix as
/// data (`cells`, `marked` = the cells whose code is 1) and exposes it for later rules; it does
/// **not** turn a code into "planting is refused here", because that would be an invented rule
/// that the sheet cannot contradict.
struct BoardGridSpec {
    std::string alias;
    int width = 0;
    int height = 0;
    std::vector<std::vector<int>> cells;
    bool empty() const { return cells.empty(); }
    /// How many cells carry the code 1.
    int marked() const;
};

/// The Events module split into the two kinds the sheet gives semantics for.
struct EventsSpec {
    std::vector<TideChange> tide;
    std::vector<FrostWind> frost;
    bool empty() const { return tide.empty() && frost.empty(); }
};

/// `LevelMutator*` objects. Only one shape says what it does to the game: `maxSunOverride` caps
/// the sun bank. The `LevelMutatorModuleProperties` rows are mission wrappers (`LevelTimer`,
/// `KillZombies1`, `PlantsLost2`...) - challenge objectives, not global modifiers - so they stay
/// counted as unknown instead of being read as a multiplier the sheet never gave.
struct MutatorSpec {
    /// `LevelMutatorMaxSunProps.maxSunOverride`: the bank may not hold more than this. 0 = no cap.
    int maxSun = 0;
    /// Rows that are challenge wrappers rather than a modifier (counted, not applied).
    int challengeRows = 0;
    bool empty() const { return maxSun == 0 && challengeRows == 0; }
};

/// A mechanic the level declares that the kernel does not implement, with how many instances
/// the level asked for (one Events module == 1, four beach spawner entries == 4). Kept as a
/// count rather than a bool so `--run-level` can show "this level has 9 unimplemented tide
/// events", not just "something is missing".
struct UnknownMechanic {
    std::string kind;
    int count = 0;
};

/// Everything one level says about the mechanics the kernel runs.
struct LevelMechanics {
    std::string id;
    std::vector<InitialPlant> initialPlants;
    std::vector<GridItemPlacement> initialGridItems;
    std::vector<GravestoneWave> gravestones;
    ConveyorSpec conveyor;
    ProtectSpec protect;
    /// T66: the special spawner rows this level declares, one spec per kind present, sorted by
    /// kind. Only wired kinds appear; an unwired kind (spider) stays in `unknownMechanics`.
    std::vector<SpawnerSpec> spawners;
    /// T88: the Events module (tide + frost wind), the board mask and the sun cap. Kinds inside
    /// these modules that the sheet gives no semantics for stay in `unknownMechanics`.
    EventsSpec events;
    BoardGridSpec boardGrid;
    MutatorSpec mutators;
    /// Kinds present in the sheet that this kernel does not run. Sorted by kind.
    std::vector<UnknownMechanic> unknownMechanics;

    bool hasConveyor() const { return !conveyor.slots.empty(); }
    bool hasProtect() const { return !protect.plants.empty(); }
    bool hasGravestones() const { return !gravestones.empty(); }
    bool hasSpawners() const;
    const SpawnerSpec* spawner(SpawnerKind kind) const;
    bool hasEvents() const { return !events.empty(); }
    bool hasBoardGrid() const { return !boardGrid.empty(); }
    bool hasSunCap() const { return mutators.maxSun > 0; }
    /// True when the level declares nothing this kernel would have to skip.
    bool fullyCovered() const { return unknownMechanics.empty(); }
};

/// How the kernel treats one mechanic kind.
/// `covered` means the module actually runs (initial plants, grid items, conveyor, protect,
/// gravestone drops, and the ordinary jittered waves that already drive every level);
/// `unknown` means the module is counted and named instead of being silently dropped.
enum class MechanicTier { covered, unknown };
MechanicTier mechanicTierFor(const std::string& kind);
const char* mechanicTierName(MechanicTier tier);

class LevelMechanicsTable {
  public:
    static constexpr const char* kFileName = "level_mechanics.json";

    /// Parse one level_mechanics.json. Every failure throws `mechanics table: <path>: <why>`
    /// rather than returning an empty table: an empty table would make every level look like a
    /// plain level, which is exactly the bug this file exists to remove.
    static LevelMechanicsTable load(const std::filesystem::path& path);
    /// The process-wide table from `generatedDir()`, parsed once.
    static const LevelMechanicsTable& shared();

    bool empty() const { return levels_.empty(); }
    std::size_t size() const { return levels_.size(); }
    /// Null when the level has no row; an all-null row still returns a (fully empty) record,
    /// because "this level declares no mechanics" is information the caller must be able to read.
    const LevelMechanics* find(std::string_view id) const;

    std::size_t withConveyor() const { return withConveyor_; }
    std::size_t withInitialPlants() const { return withInitialPlants_; }
    std::size_t withInitialGridItems() const { return withInitialGridItems_; }
    std::size_t withProtect() const { return withProtect_; }
    std::size_t withGravestones() const { return withGravestones_; }
    std::size_t withUnknown() const { return withUnknown_; }
    /// T88: levels with tide/frost rows, with a board mask, and with a sun cap.
    std::size_t withEvents() const { return withEvents_; }
    std::size_t withBoardGrid() const { return withBoardGrid_; }
    std::size_t withSunCap() const { return withSunCap_; }
    /// Levels that declare at least one row of this spawner kind (`spawners.grid` etc.), counted
    /// over the whole sheet. Zero for `spider`, which never leaves `unknownMechanics`.
    std::size_t withSpawners(SpawnerKind kind) const;

  private:
    std::map<std::string, LevelMechanics, std::less<>> levels_;
    std::map<SpawnerKind, std::size_t> spawnerLevels_;
    std::size_t withConveyor_ = 0;
    std::size_t withInitialPlants_ = 0;
    std::size_t withInitialGridItems_ = 0;
    std::size_t withProtect_ = 0;
    std::size_t withGravestones_ = 0;
    std::size_t withUnknown_ = 0;
    std::size_t withEvents_ = 0;
    std::size_t withBoardGrid_ = 0;
    std::size_t withSunCap_ = 0;
};

} // namespace pvz::engine
