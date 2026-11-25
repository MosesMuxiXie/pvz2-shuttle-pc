#pragma once
#include "armor.hpp"            // ArmorLayerState: per-zombie armor layers in sheet order
#include "projectile_table.hpp" // Trajectory carried by every shot
#include <cstdint>
#include <string>
#include <vector>

namespace pvz::engine {

using EntityId = std::uint64_t;

/// One runtime slot per `content::Action` of the plant type. `kind` mirrors
/// `content::ActionKind` but is kept as a plain string so the engine does not
/// depend on the rules-pack loader for its entity model.
struct ActionSlot {
    std::string kind;           // projectile | sun | explode | special | plantfood | manual | unknown
    std::string rawType;        // original Type text, kept for coverage reporting
    std::string projectileType; // Rtid name, when the action spawns a shot
    std::string specialName;    // Rtid name, when the action dispatches to the registry
    std::string trigger;        // none | instant | column | row | rect
    double damage = 0;
    double splash = 0;
    double slow = 0;
    double radius = 0;          // explode radius in columns
    double triggerWidth = 0, triggerHeight = 0;
    int cooldownTicks = 0;
    int remainingTicks = 0;
    int initialTicks = 0;
    int pierce = 0;
    /// The runner re-seeds `remainingTicks` once, on the plant's first tick, because
    /// `InitialMinCooldownTime` is only half the rule: when the sheet leaves it out the
    /// first cycle starts at `CooldownTimeMin` (see `action_runner.cpp`).
    bool seeded = false;
    /// An action Type the engine has no behaviour for is reported once, not every frame.
    bool unknownReported = false;
};

struct PlantEntity {
    EntityId id = 0;
    std::string type;
    std::string family; // shoot | lob | produce | wall | instant | mine | chomp | fume | boomerang | support
    int row = 0, col = 0;
    double hp = 0, maxHp = 0;
    std::uint64_t born = 0;
    bool alive = true;
    double actionTimer = 0; // JSON-driven families only (plants without a rules-pack action list)
    std::vector<ActionSlot> slots;
    /// S5.7 plant food: ticks left in the buff window (0 == not fed) and whether the sheet's
    /// `plantfood` action still has to play once. Kept on the plant, not in `ActionSlot`,
    /// because the buff applies to every action the plant has, not just the plant-food one.
    int plantFoodTicks = 0;
    bool plantFoodArmed = false;
    /// S5.13 `protectThePlant`: the level fails the moment this plant dies. Set on the plants a
    /// protect mission places, never on anything the player bought.
    bool protectedPlant = false;
};

/// S5.13 grid items: what a level puts on a cell that is not a plant - a gravestone, a puddle, a
/// tombstone. They block planting and are removed by a shovel or an explosion; zombies walk over
/// them, which is why they are not `PlantEntity` (they would be eaten, counted as plants lost and
/// hashed as plants, changing every baseline for a level that only meant to block one cell).
struct GridItemEntity {
    EntityId id = 0;
    std::string type;
    int row = 0, col = 0;
    double hp = 0, maxHp = 0;
    bool alive = true;
};

enum class ZombieState { walking, eating, dying };

struct ZombieEntity {
    EntityId id = 0;
    std::string type;
    std::string className;
    std::string family; // walk | jump | steal | summon | gargantuar | fly
    int row = 0;
    double x = 0; // column coordinate of the zombie's front edge
    double hp = 0, maxHp = 0;
    double armorHp = 0, armorMaxHp = 0;
    /// S5.11: the armor stack in the sheet's stored order (see ArmorTable::zombieArmorLayers —
    /// the order is never sorted). `armorHp`/`armorMaxHp` stay as the sum of the layers that
    /// actually carry hit points, which is what every view and the hash already read; the flags
    /// live here so `damageZombie` can decide per layer instead of draining one flat pool.
    std::vector<ArmorLayerState> armorLayers;
    double speed = 0;  // columns per second
    double eatDps = 0;
    ZombieState state = ZombieState::walking;
    bool alive = true;
    std::uint64_t spawnTick = 0;
    std::uint64_t deathTick = 0;
    std::uint64_t nextSpecialTick = 0; // family-specific cooldown (summon / smash / steal)
    EntityId target = 0; // plant being eaten
    double slowUntilTick = 0;
    /// S5.8 boss runtime. `bossStages > 0` marks a staged mechanic boss: it does not walk,
    /// eat or trigger mowers, and its hit points advance through the sheet's stage list.
    /// `isBoss` alone marks the `gargantuar`-marker levels, where the boss is an ordinary
    /// zombie that only carries the flag (3 of the 71 boss levels).
    bool isBoss = false;
    int stageIndex = 0;
    int bossStages = 0;
    double bossHp = 0, bossMaxHp = 0;
    int bossIdleTicks = 0;
    int bossStunTicks = 0;
};

struct ShotEntity {
    EntityId id = 0;
    int row = 0;
    double x = 0, damage = 0, speed = 0;
    int pierce = 0;
    double splash = 0, slow = 0;
    EntityId owner = 0;
    std::string projectileType;
    bool alive = true;

    // S5.9: the numbers below come from native/generated/projectiles_from_pack.json, resolved by
    // World::spawnShot. The defaults are the old global constants, so a shot spawned without a
    // table hit behaves exactly as it did before this wiring.
    Trajectory trajectory = Trajectory::straight;
    double hitRadius = 0.25;   // tuning::kShotHitRadius = CollisionRect mode (358/596 rows)
    double splashRadius = 0.6; // columns a neighbour-row splash reaches
    double splashDamage = 0;   // <= 0 falls back to damage * tuning::kSplashNeighbourFactor
    double landX = 0;          // arc/drop: the column the shot returns to the ground at
    bool lobbed = false;       // arc/drop: only the landing zone can be hit
};

struct SunEntity {
    EntityId id = 0;
    double x = 0, y = 0;
    int row = 0;
    int value = 25;
    std::uint64_t expires = 0;
};

struct MowerEntity {
    int row = 0;
    double x = -0.5;
    int state = 0; // 0 ready, 1 moving, 2 spent
};

/// Value copy handed to views and to the hash. Kept close to the legacy
/// `Battle*` structures so S4 can migrate the view without reshaping data.
struct PlantView {
    EntityId id;
    std::string type, family;
    int row, col;
    double hp, maxHp;
    std::uint64_t born;
    int busyTicks; // ticks until the first ready action, 0 when idle
};
struct ZombieView {
    EntityId id;
    std::string type, className, family;
    int row;
    double x, hp, maxHp, armor;
    bool eating;
};
struct ShotView {
    EntityId id;
    int row;
    double x, damage;
    std::string projectileType;
};
struct SunView {
    EntityId id;
    double x, y;
    int row, value;
    std::uint64_t expires;
};
struct MowerView {
    int row;
    double x;
    int state;
};

struct Snapshot {
    std::string level;
    std::string status;
    std::uint64_t tick = 0;
    bool paused = false;
    std::int64_t sun = 0;
    std::size_t wave = 0;
    std::size_t waves = 0;
    int rows = 0, cols = 0;
    std::uint32_t seed = 1;
    std::uint64_t hash = 0;
    std::vector<PlantView> plants;
    std::vector<ZombieView> zombies;
    std::vector<ShotView> shots;
    std::vector<SunView> suns;
    std::vector<MowerView> mowers;
};

} // namespace pvz::engine
