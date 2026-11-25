#pragma once
#include "../catalog.hpp"
#include "boss.hpp"
#include "director.hpp"
#include "entity.hpp"
#include "fusion.hpp"
#include "mechanics.hpp"
#include "plantfood.hpp"
#include "tuning.hpp"
#include <map>
#include <random>
#include <set>
#include <string>
#include <vector>

namespace pvz::engine {

/// Which original mechanics this world runs.
///
/// Plant food and fusion are on by default because both have property-sheet data behind
/// them. They are switchable so a baseline run can pin the pre-S5 behaviour, and so the
/// hash of an option-off world can be compared against an old smoke recording.
struct WorldOptions {
    bool plantfood = true;
    bool fusion = true;
    /// S5.8: the boss runtime. Read at construction, because the boss table is resolved
    /// there; a level without a boss marker ignores it entirely.
    bool boss = true;
    /// S5.9: resolve shot speed / hit box / trajectory from the projectile table. Off means every
    /// shot keeps tuning::kShotSpeedColsPerSec and tuning::kShotHitRadius, which is exactly the S5.8
    /// behaviour and is what the reverse probe and the baseline comparison use.
    bool projectiles = true;
    /// S5.13: lay down the level's own mechanics - initial plants and grid items, the conveyor
    /// belt economy, the "protect the plant" mission and the gravestone drops. Off means the level
    /// plays as an ordinary level, which is the pre-S5.13 behaviour and what the reverse probe and
    /// a baseline comparison use.
    bool mechanics = true;
    /// S5.8 (next task) drives elements; declared here so the call site does not have to
    /// change again when that lands.
    bool elements = false;
};

/// What a feed does to one plant, as the view needs to read it.
struct PlantFoodState {
    EntityId plant = 0;
    std::string type;
    int remainingTicks = 0;
    /// True when the sheet declared a `plantfood` action, i.e. the feed plays something
    /// rather than only extending the buff.
    bool usesActionSlot = false;
};

/// One staged boss as the view needs it (S5.8).
struct BossState {
    EntityId id = 0;
    std::string type;
    int stageIndex = 0;
    int stages = 0;
    double hp = 0;
    double maxHp = 0;
    int idleTicks = 0;
    int stunTicks = 0;
};

/// The engine kernel: geometry, entity pool, economy, win/lose and hashing.
/// Rendering never links against internals; views consume `Snapshot` only.
class World {
  public:
    static constexpr double stepSeconds = tuning::kStepSeconds;

    World(const Catalog& catalog, const LevelDefinition& level, std::uint32_t seed = 1,
          const WorldOptions& options = {});
    World(const World&) = delete;
    World& operator=(const World&) = delete;
    const WorldOptions& options() const { return options_; }

    // ---- time -------------------------------------------------------------
    void advance(double seconds);
    void step();
    void pause(bool paused) { paused_ = paused; }
    bool paused() const { return paused_; }

    // ---- player input -----------------------------------------------------
    std::string plant(const std::string& type, int row, int col);
    bool shovel(int row, int col);
    bool collect(EntityId id);
    bool spawnZombie(const std::string& type, int row);
    /// Same as `spawnZombie`, but the zombie enters at `x` grid units instead of the right edge.
    /// A spawner row that names a column band (`spawners.storm` columns 4..6, a low tide at
    /// column 5) puts its zombies on the lawn there; the ordinary waves keep the right edge.
    bool spawnZombieAt(const std::string& type, int row, double x);

    // ---- plant food (S5.7) ------------------------------------------------
    /// True when the sheets carry a plant-food row for `type`, i.e. when a feed has
    /// authoritative data (duration and, for six plants, an action to play).
    bool canFeed(const std::string& type) const;
    /// Feed one plant. A plant whose sheet declares a `plantfood` action has that action
    /// armed for `action_runner` to play on the next tick (the original behaviour);
    /// every plant gets the +100% damage/attack-speed window from the row's duration.
    /// Returns false when the plant is gone or plant food is switched off.
    bool feed(EntityId id);
    /// The plants currently under the effect, for the view.
    std::vector<PlantFoodState> plantFoodStates() const;
    const PlantFoodTable* plantFoodTable() const { return plantFood_; }

    // ---- fusion (S5.7) ----------------------------------------------------
    /// Fuse two plants standing on the same or adjacent cells. The pair is looked up in the
    /// sheet's 85 recipes; on a hit both plants are removed and `result` is built on the
    /// first one's cell. The result's cost is charged without a balance check - fusion is a
    /// combination, not a purchase - and the `fusion` event records what happened.
    bool tryFuse(EntityId a, EntityId b);
    /// Fusion count, the other half of the S5.7 hashed state.
    std::size_t fusions() const { return fusions_; }
    const FusionTable* fusionTable() const { return fusion_; }

    // ---- boss (S5.8) ------------------------------------------------------
    /// The staged boss this level resolved to, or null when the level carries no boss
    /// marker (or names a plain zombie type instead, as 3 of the 71 boss levels do).
    /// Resolution happens in the constructor, so the view can show the health bar before
    /// the boss has walked in.
    const BossDefinition* boss() const { return bossDefinition_; }
    /// How many stages the resolved boss has; 0 for a level with no boss and for the
    /// `gargantuar`-marker levels (a plain zombie carries that flag).
    int bossStageCount() const {
        return bossDefinition_ != nullptr ? static_cast<int>(bossDefinition_->stages.size()) : 0;
    }
    bool bossSpawned() const { return bossSpawned_; }
    /// Stage actions the sheet declares but the kernel does not implement (breath, imp
    /// throws, speaker rays). Counted once per activation, never thrown.
    std::size_t bossActionUnwired() const { return bossActionUnwired_; }
    /// Boss levels whose marker resolved to nothing (4 of the 68 `zomboss` levels name a
    /// world the sheet has no boss for). Counted, and recorded as a `boss_unavailable` event.
    std::size_t bossUnavailable() const { return bossUnavailable_; }
    const BossTable* bossTable() const { return bossTable_; }
    /// Live staged bosses, for the view.
    std::vector<BossState> bossStates() const;

    // ---- level mechanics (S5.13) ------------------------------------------
    /// The row this level resolved to, or null when the level has no mechanics at all (which the
    /// sheet reports for 80 of 1809 levels) or mechanics are switched off.
    const LevelMechanics* mechanics() const { return mechanics_; }
    const LevelMechanicsTable* mechanicsTable() const { return mechanicsTable_; }
    /// True when the level's cards come off a conveyor belt instead of a seed bank: planting
    /// costs no sun and there is no recharge, but a card must be in the belt's hand.
    bool conveyorLevel() const { return mechanics_ != nullptr && mechanics_->hasConveyor(); }
    /// The cards currently on the belt, oldest first. Taken by `plant()`.
    const std::vector<std::string>& conveyorCards() const { return conveyorCards_; }
    /// Grid items standing on the lawn (gravestones, puddles). Not plants: they block a cell and
    /// are removed by `shovel()` or `explode()`.
    const std::vector<GridItemEntity>& gridItems() const { return gridItems_; }
    std::size_t gridItemsSpawned() const { return gridItems_.size(); }
    /// Plants the level placed itself (initial plants and the protect mission's targets). They are
    /// not counted as `planted` and cost no sun - see `layInitialField`.
    std::size_t initialPlantsLaid() const { return initialPlantsLaid_; }
    int protectedPlantCount() const { return protectedPlants_; }
    /// Protect targets the sheet lists on a cell that already holds one (egypt_74 lists three on
    /// one cell). They are reported, never silently dropped.
    int unplacedProtectedPlants() const { return unplacedProtectedPlants_; }
    /// How many of them the sheet requires to survive: 0 when the mission cannot be lost this way.
    int requiredProtectedPlants() const;
    /// How many targets the mission asks for but the opening board could not hold, i.e.
    /// `requiredProtectedPlants() - protectedPlantCount()` when that is positive, else 0.
    ///
    /// T59: eleven protect missions list more targets than their own board can carry
    /// (`egypt_74` lists five on three cells) and six of those place none at all
    /// (`carnival_79`, `carnival_81`, `chinesegarden_57`, `frontyard_53`, `lostcity_67`,
    /// `sky_31`). Such a mission is still winnable - it is simply zero-tolerance - but for the
    /// six with no targets the death path can never fire, so the gap has to be countable
    /// somewhere. It is reported at level start as `protect_capacity_shortfall`.
    int protectCapacityShortfall() const { return protectCapacityShortfall_; }
    /// Living protected plants right now - the number `requiredProtectedPlants()` is judged against.
    int aliveProtectedPlants() const;
    /// How many protect missions were failed (`protect_failed`). A mission that fails ends the run.
    int protectFailures() const { return protectFailures_; }
    /// Mechanic kinds this level declares but the kernel does not run, aggregated by kind. Filled
    /// at construction, because a gap must be visible before the level starts, not after it ends.
    const std::map<std::string, int>& mechanicUnknown() const { return mechanicUnknown_; }
    /// Distinct unimplemented kinds; the count `--run-level` prints next to the list.
    std::size_t mechanicUnknownKinds() const { return mechanicUnknown_.size(); }
    int mechanicUnknownInstances() const;

    /// T66: 460.9's per-level `SuppressFlagZombie`. True means the level's flag waves arrive as
    /// ordinary waves, so `flagSuppressed()` counts them and `--run-level` prints the count.
    bool suppressFlagZombie() const { return suppressFlagZombie_; }
    /// How many distinct flag waves this run turned into ordinary waves. Zero on every level that
    /// does not carry the switch, which is 1538 of 1809 — those keep the old output keys.
    int flagSuppressed() const { return static_cast<int>(suppressedFlagWaves_.size()); }

    /// T66: arrivals each wired spawner kind produced this run, keyed `spawners.<kind>`. Empty on
    /// a level without special spawners, which is why `--run-level` only prints the array when it
    /// is non-empty (the other 1500 levels keep their exact output keys).
    const std::map<std::string, int>& spawnerSpawned() const { return spawnerSpawned_; }
    bool spawnerLevel() const { return mechanics_ != nullptr && mechanics_->hasSpawners(); }

    // ---- queries ----------------------------------------------------------
    const std::string& status() const { return status_; }
    std::uint64_t tick() const { return tick_; }
    std::int64_t sun() const { return sun_; }
    /// Every sun this run spent: one charge per plant built, whether the player planted it
    /// (`plant()`) or a fusion recipe produced it (`tryFuse()`). Both paths go through
    /// `constructPlant`, which is where the charge lands, so the sum cannot double count or
    /// miss a path. Printed as `sunSpent` for the `sun_used` star goal; never part of `hash()`.
    std::int64_t sunSpent() const { return sunSpent_; }
    /// Lawn mowers still waiting to fire, i.e. mowers with `state == 0`. A mower that ran and
    /// left the lawn is `state == 2`; the one on its way is `state == 1`.
    int mowersLeft() const;
    /// Plants killed by damage this run (eaten, smashed, burned, spiked). Harvesting via
    /// `shovel()` and consuming both halves of a fusion are *not* losses and are not counted.
    int plantsLost() const { return plantsLost_; }
    std::size_t wave() const { return director_.spawnedWaves(); }
    std::size_t waves() const { return director_.waveCount(); }
    std::uint64_t cooldown(const std::string& type) const;
    const LevelDefinition& level() const { return level_; }
    int rows() const { return rows_; }
    int cols() const { return cols_; }
    std::uint32_t seed() const { return seed_; }
    std::size_t spawnedZombies() const { return spawned_; }
    /// Zombies killed by damage (shots, explosions, mowers, behaviours).
    std::size_t killedZombies() const { return killed_; }
    /// Zombies removed without being killed (despawn/cleanup). Kept apart from
    /// `killedZombies()` so statistics cannot silently mix the two.
    std::size_t removedZombies() const { return removed_; }
    /// Of `killedZombies()`, the ones run over by a lawn mower.
    std::size_t mowerKills() const { return mowerKills_; }
    /// Zombies that reached the house (the run reported `lost`).
    std::size_t leakedZombies() const { return leaked_; }
    /// Wave entries the director could not place (e.g. row clipped by `--rows`).
    std::size_t rejectedSpawns() const { return rejectedSpawns_; }
    /// Number of distinct behaviour families that had no registered implementation.
    /// Distinct names, not per-tick misses: a miss inside `tickPlants`/`tickZombies`
    /// happens every frame, so counting hits would inflate the number 60x a second.
    std::size_t unwiredPlants() const { return unwiredPlants_; }
    std::size_t unwiredZombies() const { return unwiredZombies_; }
    const std::set<std::string>& unwiredPlantNames() const { return unwiredPlantNames_; }
    const std::set<std::string>& unwiredZombieNames() const { return unwiredZombieNames_; }

    /// Column geometry: one column == 1.0 grid unit, column 0 starts at x == 0.0.
    double columnOf(int col) const { return static_cast<double>(col); }
    double centerOf(int col) const { return static_cast<double>(col) + 0.5; }

    const std::vector<PlantEntity>& plants() const { return plants_; }
    const std::vector<ZombieEntity>& zombies() const { return zombies_; }
    const std::vector<ShotEntity>& shots() const { return shots_; }
    const std::vector<SunEntity>& suns() const { return suns_; }
    const std::vector<MowerEntity>& mowers() const { return mowers_; }
    /// Engine-internal write access (projectile integration, behaviours). Views must
    /// stay on `snapshot()`.
    std::vector<ZombieEntity>& mutableZombies() { return zombies_; }
    std::vector<ShotEntity>& mutableShots() { return shots_; }
    std::vector<PlantEntity>& mutablePlants() { return plants_; }
    const Json& events() const { return events_; }
    const Catalog& catalog() const { return catalog_; }
    Snapshot snapshot() const;
    std::uint64_t hash() const;
    bool finished() const { return status_ != "playing"; }

    // ---- services used by behaviors / action runner / director ------------
    bool inBounds(int row, int col) const;
    PlantEntity* plantAt(int row, int col);
    /// S5.13: the grid item standing on a cell, or null. Kept beside `plantAt` because both answer
    /// "may something be planted here".
    GridItemEntity* gridItemAt(int row, int col);
    PlantEntity* plantById(EntityId id);
    ZombieEntity* zombieById(EntityId id);
    /// Nearest live zombie in `row` within `range` columns ahead of `from`.
    /// A zombie that already overlaps the shooter by more than `kShotBehindToleranceCols`
    /// is behind it and is not a target.
    ZombieEntity* firstZombieAhead(int row, double from, double range);
    void damagePlant(EntityId id, double amount);
    // `countsAsKill` keeps lawn-mower kills out of `killed()`, which is the plants'
    // score: with an unconditional increment a 26-world smoke showed
    // `killed == mowerKills` everywhere, i.e. nothing died to a plant.
    void damageZombie(EntityId id, double amount, bool ignoreArmor = false, bool countsAsKill = true);
    void removePlant(EntityId id);
    void removeZombie(EntityId id);
    void explode(int row, double x, double radius, double damage, double splash);
    EntityId spawnShot(int row, double x, double damage, const std::string& projectileType,
                       int pierce = 0, double splash = 0, double slow = 0, EntityId owner = 0);
    EntityId spawnSun(double x, int row, int value);
    void addSunToBank(int value) { sun_ += value; }
    /// Presentation-only event (audio/visual hooks). Same stream as vent, exposed so the
    /// projectile step can report a hit without making vent public. Never hashed.
    void emitEffect(const std::string& type, Json details = Json::object()) { event(type, std::move(details)); }

    void event(const std::string& type, Json details = Json::object());
    void noteUnwiredPlant(const std::string& name);
    void noteUnwiredZombie(const std::string& name);
    std::uint32_t randomBelow(std::uint32_t bound);
    double randomRange(double low, double high);

    /// Plant type lookup that prefers the rules pack over the JSON registry.
    const PlantDefinition* findPlant(const std::string& type) const;
    const ZombieDefinition* findZombie(const std::string& type) const;

  private:
    /// A spawn requested from inside the zombie loop, replayed after the loop ends.
    struct PendingSpawn {
        std::string type;
        int row = 0;
        double x = 0.0;
    };

    /// Sheet-driven numbers for one plant type, resolved once so `plant()`, the fusion
    /// builder and the sun gate cannot disagree about what a plant costs.
    struct PlantStats {
        double cost = 100.0;
        double hp = 300.0;
        double recharge = 5.0;
    };
    PlantStats plantStatsOf(const std::string& type) const;
    /// Build a plant from the sheets - family, hitpoints, action slots - and charge its
    /// cost. `plant()` validates first; fusion calls this directly, because a fused plant is
    /// a combination rather than a purchase and must not be gated by deck, cooldown or balance.
    /// `chargeSun == false` is the S5.13 initial-field path: the level's own plants and a card
    /// taken off a conveyor belt cost nothing and must not appear in `sunSpent`.
    PlantEntity constructPlant(const std::string& type, int row, int col, bool chargeSun = true);

    void tickSkySun();
    void tickPlants();
    void tickZombies();
    void tickShots();
    void tickSuns();
    void tickMowers();
    void tickWaves();
    void reap();
    void resolveOutcome();

    // ---- T66 special spawners ---------------------------------------------
    /// Queue every spawner row the sheet keyed to `wave`. Called right after the director has
    /// handed that wave to the lawn, so a row's zombies arrive with their wave (plus the row's
    /// own `zombieSpawnWaitTime`/`timeBetweenGroups` stagger).
    void scheduleSpawnersForWave(int wave);
    /// Queue one row's arrivals: per-kind timing and placement rules live here.
    void scheduleSpawnerRow(const SpawnerRow& row);
    /// Fire everything whose delay has elapsed. Runs once per step, after `tickWaves`.
    void tickSpawners();
    /// Put one spawner arrival in the queue at `delaySeconds` from now.
    void queueSpawnerZombie(SpawnerKind kind, const std::string& type, int row, double x, double delaySeconds);
    /// The row a spawner row lands on: the pinned one when the sheet gave it, otherwise a draw
    /// from the spawner's own generator (never the wave RNG - a storm must not reshuffle the
    /// wave schedule of the level it happens in).
    int spawnerRowFor(const SpawnerRow& row);
    /// The column a spawner row lands on, in grid units (`centerOf` of the band's far column).
    double spawnerColumnFor(const SpawnerRow& row) const;
    // Vaulting lives next to eating, not in the family hook: this loop resolves eating
    // first, so a pole vaulter that was handed a plant to chew would never vault it.
    bool tryVault(ZombieEntity& zombie);

    // ---- boss (S5.8) ------------------------------------------------------
    /// Spawn the resolved boss once the whole wave schedule has been handed to the spawner.
    void trySpawnBoss();
    /// Enter the current stage: set the idle/stun timers and play that stage's fire
    /// windows. Called on spawn and again on every stage change.
    void activateBossStage(ZombieEntity& zombie);
    /// One tick of a staged boss: count down idle/stun, then fire whatever window is due.
    void tickBoss(ZombieEntity& zombie);
    /// Damage routed from `damageZombie`: only the current stage's hitPoints matter, and a
    /// single hit never skips a stage (overflow is dropped rather than carried).
    void damageBoss(ZombieEntity& zombie, double amount, bool countsAsKill);

    // ---- level mechanics (S5.13) ------------------------------------------
    /// Lay down everything the level starts with: the sheet's initial plants, then the protect
    /// mission's targets (which are planted even when `initialPlants` did not name them), then the
    /// initial grid items. Runs once from the constructor, so the lawn looks right on tick 1.
    void layInitialField();
    /// Put one grid item on the lawn unless the cell is taken. Returns 0 when it was skipped.
    EntityId addGridItem(const std::string& type, int row, int col);
    /// Damage a grid item the way a hit damages a zombie: a gravestone breaks, a puddle dries up.
    void damageGridItem(GridItemEntity& item, double amount);
    /// Gravestone drops declared for the wave that just spawned (`spawners.gravestone`).
    void spawnGravestonesForWave(std::size_t wave);
    /// Deal the conveyor's hand up to `kConveyorHandSize`, weighted by the sheet's slot weights.
    void refillConveyor();
    /// Plant one card that came off the belt. No sun, no recharge - the belt is the economy - but
    /// the card has to be in the hand.
    std::string plantFromConveyor(const std::string& type, int row, int col);

    const Catalog& catalog_;
    LevelDefinition level_;
    std::uint32_t seed_;
    std::mt19937 rng_;
    std::uint64_t tick_ = 0;
    EntityId nextId_ = 1;
    std::int64_t sun_ = 0;
    bool paused_ = false;
    double accumulator_ = 0;
    double skySunTimer_ = 0;
    bool firstSkySunSpawned_ = false;
    int rows_ = 5, cols_ = 9;
    std::string status_ = "playing";
    std::size_t spawned_ = 0, killed_ = 0, removed_ = 0, mowerKills_ = 0, leaked_ = 0, rejectedSpawns_ = 0;
    /// S6 counters. Deliberately outside `hash()`: they describe what the run cost, not what
    /// the simulation became, so adding them must not move a single recorded smoke hash.
    std::int64_t sunSpent_ = 0;
    int plantsLost_ = 0;
    /// Spawns requested from inside the zombie loop must not grow `zombies_` while it
    /// is being iterated (that invalidates the references the loop still uses).
    std::vector<PendingSpawn> pendingSpawns_;
    bool inZombieLoop_ = false;
    std::size_t unwiredPlants_ = 0, unwiredZombies_ = 0;
    std::set<std::string> unwiredPlantNames_, unwiredZombieNames_;
    std::map<std::string, std::uint64_t> cooldowns_;
    WorldOptions options_;
    /// Null while the mechanic is switched off. The tables themselves are process-wide, so a
    /// thousand test worlds still parse the generated JSON exactly once.
    const PlantFoodTable* plantFood_ = nullptr;
    const FusionTable* fusion_ = nullptr;
    std::size_t fusions_ = 0;
    /// Resolved once in the constructor so a level that names no boss costs nothing, and a
    /// level whose marker resolves to nothing reports exactly once.
    const BossTable* bossTable_ = nullptr;
    BossSelection bossPick_;
    const BossDefinition* bossDefinition_ = nullptr;
    bool bossSpawned_ = false;
    std::size_t bossActionUnwired_ = 0, bossUnavailable_ = 0;
    /// S5.9: null when options_.projectiles is off, so spawnShot falls back to the old constants.
    const ProjectileTable* projectiles_ = nullptr;
    /// Ids already named in a `projectile_unknown` / `projectile_variant_fallback` event: one plant
    /// fires dozens of shots a minute, and a per-shot event buries the ones that matter.
    std::set<std::string> notedProjectiles_;
    /// S5.13 mechanics. The table is process-wide, the row is this level's.
    const LevelMechanicsTable* mechanicsTable_ = nullptr;
    const LevelMechanics* mechanics_ = nullptr;
    std::vector<GridItemEntity> gridItems_;
    std::vector<std::string> conveyorCards_;
    /// The belt draws from its own generator: dealing a hand must not consume the wave RNG, or
    /// every conveyor level would also shift its own zombie schedule.
    std::mt19937 conveyorRng_;
    std::map<std::string, int> mechanicUnknown_;
    std::size_t initialPlantsLaid_ = 0;
    int protectedPlants_ = 0;
    int protectFailures_ = 0;
    int unplacedProtectedPlants_ = 0;
    /// T59: targets the mission asked for minus the ones the opening board could hold. Zero for
    /// every mission whose board is big enough, which is 275 of the 286 protect levels.
    int protectCapacityShortfall_ = 0;
    /// T66: `extra.suppressFlagZombie` read once at construction (missing key = false).
    bool suppressFlagZombie_ = false;
    /// Waves whose flag marker was dropped because of the switch above. A wave appears once however
    /// many zombies it carries, so the count matches "flag waves", not "flag spawns".
    std::vector<std::size_t> suppressedFlagWaves_;
    /// Gravestone drops are looked up by wave; this remembers the highest wave already served so a
    /// paused/replayed tick cannot deal the same stones twice.
    int gravestonesServedWave_ = -1;

    /// T66: one queued spawner arrival. Kept in `dueTick` order so the step loop only ever looks
    /// at the head; `kind` is the `spawners.<kind>` name the run reports.
    struct QueuedSpawner {
        std::uint64_t dueTick = 0;
        std::string kind;
        std::string type;
        int row = 0;
        double x = 0.0;
    };
    std::vector<QueuedSpawner> spawnerQueue_;
    /// Arrivals each wired kind actually produced, keyed like `mechanicUnknown`.
    std::map<std::string, int> spawnerSpawned_;
    /// Rows and columns of spawner arrivals must not consume the wave RNG.
    std::mt19937 spawnerRng_;
    /// Highest wave whose spawner rows have been queued.
    int spawnerServedWave_ = 0;
    /// Waves a portal already redirected: one portal opens once, however many zombies walk
    /// through it in that wave's spread window.
    std::set<std::size_t> portalWavesServed_;
    std::vector<PlantEntity> plants_;
    std::vector<ZombieEntity> zombies_;
    std::vector<ShotEntity> shots_;
    std::vector<SunEntity> suns_;
    std::vector<MowerEntity> mowers_;
    Director director_;
    Json events_ = Json::array();
};

} // namespace pvz::engine
