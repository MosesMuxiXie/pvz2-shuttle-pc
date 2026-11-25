#include "world.hpp"
#include "../content/model.hpp"
#include "action_runner.hpp"
#include "projectile.hpp"
#include "registry.hpp"
#include "plant_family.hpp"
#include "zombie_family.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <sstream>
#include <stdexcept>

namespace pvz::engine {
namespace {
constexpr std::uint64_t ticksOf(double seconds) {
    return static_cast<std::uint64_t>(seconds / tuning::kStepSeconds + 0.5);
}
int clampInt(int value, int low, int high) { return value < low ? low : (value > high ? high : value); }
long long quantize(double value) { return static_cast<long long>(std::llround(value * 1000.0)); }
double numberOr(const Json& object, const char* key, double fallback) {
    const auto it = object.find(key);
    if (it == object.end()) return fallback;
    if (it->is_number()) return it->get<double>();
    if (it->is_boolean()) return it->get<bool>() ? 1.0 : 0.0;
    return fallback;
}
std::string familyOf(const PlantDefinition& def) {
    if (!def.behavior.empty()) return def.behavior;
    return def.damage > 0 ? "shoot" : "wall";
}
int pierceOf(const Json& raw) {
    const auto it = raw.find("pierce");
    if (it == raw.end()) return 0;
    if (it->is_boolean()) return it->get<bool>() ? 1 : 0;
    if (it->is_number()) return static_cast<int>(it->get<double>());
    return 0;
}
/// S5.11: the armor sheet, resolved once per process. `world.hpp` is not in this task's write
/// scope, so there is no `WorldOptions::armor` switch and no member pointer; the table is reached
/// through this accessor and loaded from the constructor so a broken file still fails at load
/// rather than on the first zombie of the level.
const ArmorTable& armorTable() {
    static const ArmorTable& table = ArmorTable::shared();
    return table;
}
} // namespace

World::World(const Catalog& catalog, const LevelDefinition& level, std::uint32_t seed,
             const WorldOptions& options)
    : catalog_(catalog), level_(level), seed_(seed), rng_(seed), options_(options) {
    // S5.7: plant food and fusion are on by default. Resolving the tables here means a
    // missing/broken generated file fails at construction with a named error instead of
    // quietly feeding nothing at tick 900.
    if (options_.plantfood) plantFood_ = &PlantFoodTable::shared();
    if (options_.fusion) fusion_ = &FusionTable::shared();
    rows_ = clampInt(level.rows > 0 ? level.rows : 5, 1, 8);
    cols_ = clampInt(level.cols > 0 ? level.cols : 9, 1, 12);
    sun_ = level.sun;
    mowers_.reserve(static_cast<std::size_t>(rows_));
    for (int row = 0; row < rows_; ++row) {
        MowerEntity mower;
        mower.row = row;
        mower.x = -0.5;
        mower.state = 0;
        mowers_.push_back(mower);
    }
    director_ = Director(level_, rows_, rng_);
    // T66: 460.9 taught `WaveManagerProperties` a per-level `SuppressFlagZombie` switch, and the
    // patch sheet has a real value for 271 levels (215 true / 56 false). This is the game's own
    // field, not something invented here: when it is true the level's flag waves must arrive as
    // ordinary waves. Read from `content` (the engine never opens patch_460_9.json), and a missing
    // key means false, which is what 1538 levels say by saying nothing.
    if (level_.extra.is_object()) {
        const auto it = level_.extra.find("suppressFlagZombie");
        if (it != level_.extra.end() && it->is_boolean()) suppressFlagZombie_ = it->get<bool>();
    }
    // S5.8: resolve the boss before the first tick. A level whose marker names a world the
    // sheet has no boss for must say so once, at load, rather than looking like an ordinary
    // level for 20 minutes.
    if (options_.boss) {
        bossTable_ = &BossTable::shared();
        bossPick_ = selectBoss(catalog_, level_, *bossTable_);
        if (bossPick_.spawned()) {
            bossDefinition_ = bossPick_.kind == BossSelection::Kind::mechanic ? bossPick_.boss : nullptr;
        } else if (!bossPick_.marker.empty()) {
            ++bossUnavailable_;
            event("boss_unavailable", Json{{"marker", bossPick_.marker}, {"world", level_.world},
                                           {"level", level_.id}, {"candidates", bossPick_.candidates}});
        }
    }
    // S5.9: the shot table is the source of speed / hit box / trajectory. Loading it here means a
    // broken generated file fails at construction instead of mid-level, and `--run-level` can flip
    // it off to reproduce the pre-S5.9 numbers.
    if (options_.projectiles) projectiles_ = &ProjectileTable::shared();
    // S5.11: armor layers are read from the sheet for every spawn, so pull the table in now — a
    // missing or malformed armors_from_pack.json must fail here, with the other tables, instead
    // of at the first zombie of the level.
    (void)armorTable();
    // S5.13: the per-level mechanics sheet. Loaded here so a broken file fails at construction,
    // and so the lawn, the belt and the mission are already decided before tick 1. A level the
    // sheet has no row for (80 of 1809 declare nothing) simply has `mechanics_ == nullptr`.
    if (options_.mechanics) {
        mechanicsTable_ = &LevelMechanicsTable::shared();
        mechanics_ = mechanicsTable_->find(level_.id);
        conveyorRng_.seed(seed_ ^ 0x9e3779b9u);
        // T66: spawner rows draw their own rows/columns; keeping that off `rng_` means adding a
        // storm to a level cannot change which rows its ordinary waves picked.
        spawnerRng_.seed(seed_ ^ 0x85ebca6bu);
        layInitialField();
        // Anything this level declares that the kernel does not run is named once, with how many
        // instances were skipped. A silent drop is how 350 conveyor levels played as seed-bank
        // levels for a whole stage: the run still finished, so nothing ever looked broken.
        if (mechanics_ != nullptr) {
            for (const UnknownMechanic& unknown : mechanics_->unknownMechanics) {
                mechanicUnknown_[unknown.kind] += unknown.count;
                event("mechanic_unknown", Json{{"level", level_.id}, {"mechanic", unknown.kind},
                                               {"count", unknown.count},
                                               {"tier", mechanicTierName(mechanicTierFor(unknown.kind))}});
            }
        }
    }
    event("level_start", Json{{"world", level_.world}, {"rows", rows_}, {"cols", cols_},
                              {"waves", director_.waveCount()}, {"seed", seed_}});
}

// ------------------------------------------------------------------ time -----
void World::advance(double seconds) {
    // A NaN/Inf `dt` used to poison `accumulator_` permanently: every later call then
    // advanced zero ticks while the game looked frozen. Reject it at the door instead
    // (the legacy kernel threw here too).
    if (!std::isfinite(seconds) || seconds < 0 || seconds > 86400) {
        throw std::invalid_argument("World::advance needs a finite dt in [0, 86400]");
    }
    if (seconds <= 0) return;
    accumulator_ += seconds;
    int guard = 0;
    while (accumulator_ + 1e-12 >= stepSeconds && guard < 200000) {
        accumulator_ -= stepSeconds;
        step();
        ++guard;
    }
    // A single call may not consume more than ~55 minutes of wall time; drop the rest
    // explicitly (with an event) instead of leaving it to burn on the next call.
    if (guard >= 200000) {
        event("time_budget_exceeded", Json{{"droppedSeconds", accumulator_}});
        accumulator_ = 0;
    }
    if (accumulator_ < 1e-12) accumulator_ = 0;
}

void World::step() {
    if (finished()) return;
    ++tick_;
    tickWaves();
    tickSpawners();
    tickSkySun();
    tickPlants();
    tickZombies();
    stepShots(*this);
    tickSuns();
    tickMowers();
    reap();
    resolveOutcome();
}

void World::tickWaves() {
    for (const auto& spawn : director_.takeDue(tick_)) {
        // T66: this kernel has no separate flag-zombie entity - a flag wave differs only by the
        // marker the director carries on each spawn (the spread window is baked in when the
        // schedule is built). So honouring 460.9's `SuppressFlagZombie` means the wave arrives as
        // an ordinary wave: the marker is dropped, the spawn itself is untouched, and the wave is
        // counted once so `--run-level` can show that the switch did something.
        const bool flagDropped = spawn.flag && suppressFlagZombie_;
        if (flagDropped &&
            std::find(suppressedFlagWaves_.begin(), suppressedFlagWaves_.end(), spawn.wave) ==
                suppressedFlagWaves_.end()) {
            suppressedFlagWaves_.push_back(spawn.wave);
            event("flag_wave_suppressed", Json{{"wave", spawn.wave}, {"level", level_.id}});
        }
        // S5.13/T66: a portal row for this wave reroutes the wave's own spawns through the portal
        // cell instead of the right edge. The sheet names only the portal's cell (`portalRow`,
        // `portalColumn`), not a destination, so "the zombies arrive at the portal" is the whole
        // mechanic this kernel can honour without inventing a second endpoint.
        int row = spawn.row;
        double x = static_cast<double>(cols_) + 0.6;
        if (mechanics_ != nullptr) {
            if (const SpawnerSpec* portals = mechanics_->spawner(SpawnerKind::portal); portals != nullptr) {
                for (const SpawnerRow& portal : portals->rows) {
                    if (!portal.scheduled() || portal.wave != static_cast<int>(spawn.wave)) continue;
                    if (portal.row < 0 || portal.columnEnd < 0) continue;
                    row = portal.row;
                    x = spawnerColumnFor(portal);
                    if (portalWavesServed_.insert(spawn.wave).second) {
                        ++spawnerSpawned_[spawnerKindName(SpawnerKind::portal)];
                        event("portal_opened", Json{{"wave", spawn.wave}, {"row", row},
                                                    {"column", portal.columnEnd}, {"level", level_.id}});
                    }
                    break;
                }
            }
        }
        if (!spawnZombieAt(spawn.type, row, x)) {
            ++rejectedSpawns_;
            event("wave_spawn_rejected", Json{{"type", spawn.type}, {"row", row}, {"wave", spawn.wave}});
            continue;
        }
        event("wave_spawn", Json{{"type", spawn.type}, {"row", row}, {"wave", spawn.wave},
                                 {"flag", spawn.flag && !flagDropped}, {"final", spawn.final}});
    }
    // S5.13: a gravestone drop belongs to a wave, so it is dealt here - after the wave's zombies
    // have been handed to the spawner, before the boss check. The stones land on cells that are
    // free, which is why they must not be laid during the constructor for a later wave.
    spawnGravestonesForWave(director_.spawnedWaves());
    // T66: the special spawner rows of the wave that just landed.
    scheduleSpawnersForWave(static_cast<int>(director_.spawnedWaves()));
    // The boss arrives after the last scheduled wave has been handed to the spawner. Doing it
    // here (not in the constructor) keeps a boss level's first 20 seconds identical to a
    // normal level, which is what the shipped recordings show.
    trySpawnBoss();
}

void World::tickSkySun() {
    skySunTimer_ += stepSeconds;
    const double threshold = firstSkySunSpawned_ ? tuning::kSkySunIntervalSeconds : tuning::kFirstSkySunSeconds;
    if (skySunTimer_ + 1e-9 < threshold) return;
    // Subtract instead of zeroing: zeroing silently loses the overshoot and makes
    // the sun cadence drift slower than `kSkySunIntervalSeconds`.
    skySunTimer_ -= threshold;
    firstSkySunSpawned_ = true;
    const int col = cols_ > 0 ? static_cast<int>(randomBelow(static_cast<std::uint32_t>(cols_))) : 0;
    spawnSun(centerOf(col), -1, tuning::kSkySunValue);
}

void World::tickPlants() {
    for (auto& plant : plants_) {
        if (!plant.alive) continue;
        // Counted down for every plant, not only the ones with action slots: the buff window
        // has to expire on the same schedule whether the plant runs slots or a family hook.
        if (plant.plantFoodTicks > 0) --plant.plantFoodTicks;
        if (!plant.slots.empty()) {
            runActionSlots(*this, plant);
            continue;
        }
        const auto* behavior = Registry::shared().plantBehavior(plant.family);
        if (!behavior) {
            noteUnwiredPlant(plant.family);
            behavior = Registry::defaultPlant();
        }
        (*behavior)(*this, plant.id);
    }
}

void World::tickZombies() {
    const double dt = stepSeconds;
    inZombieLoop_ = true;
    for (auto& zombie : zombies_) {
        if (!zombie.alive) continue;
        if (zombie.state == ZombieState::dying) continue;
        // A staged boss owns its own timeline: it does not walk, eat, vault or reach the
        // mower line, so it is handled here and skipped by everything below. The plain
        // `gargantuar`-marker levels keep `bossStages == 0` and run the normal path.
        if (zombie.isBoss && zombie.bossStages > 0) {
            tickBoss(zombie);
            continue;
        }
        PlantEntity* target = nullptr;
        // A jumper vaults the plant it is walking into instead of eating it. This runs
        // before the eat scan below; the family hook runs after it, which is why the old
        // placement let a pole vaulter chew through wall-nuts and never hop.
        if (zombie.family == "jump") tryVault(zombie);
        // Only flyers ignore plants entirely. A jumper vaults the first plant and then
        // eats normally, so it must not be excluded here.
        if (zombie.family != "fly") {
            // S5.12: a jumper must be able to walk up to the plant, otherwise the contact-sized
            // vault window (kEatStartCols + 0.05) is never reachable: the eat scan below reaches
            // a whole column further (`kEatRangeCols`), so the vaulter would start chewing at
            // 1.15 columns and never get close enough to hop. Jumpers therefore only take a
            // target at contact distance; every other family keeps the long reach.
            const double reach = zombie.family == "jump" ? tuning::kEatStartCols : tuning::kEatRangeCols;
            for (auto& plant : plants_) {
                if (!plant.alive || plant.row != zombie.row) continue;
                if (plant.family == "spike") continue; // walk-over plants never block a zombie
                const double centre = centerOf(plant.col);
                if (centre <= zombie.x + tuning::kEatStartCols && centre >= zombie.x - reach) {
                    target = &plant;
                    break;
                }
            }
        }
        if (target) {
            zombie.state = ZombieState::eating;
            zombie.target = target->id;
            damagePlant(target->id, zombie.eatDps * dt);
        } else {
            zombie.state = ZombieState::walking;
            zombie.target = 0;
            double speed = zombie.speed;
            if (zombie.slowUntilTick > static_cast<double>(tick_)) speed *= 0.5;
            zombie.x -= speed * dt;
        }
        const auto* behavior = Registry::shared().zombieBehavior(zombie.family);
        if (!behavior) {
            noteUnwiredZombie(zombie.family);
            behavior = Registry::defaultZombie();
        }
        (*behavior)(*this, zombie.id);
        if (!zombie.alive) continue;
        auto& mower = mowers_[static_cast<std::size_t>(clampInt(zombie.row, 0, rows_ - 1))];
        // Mower trigger and defeat are two different lines: the mower leaves at
        // `kMowerTriggerX`, the house is breached at `kLoseX`. Gating defeat on
        // `state == 2` let a second zombie in the same lane walk past a mower that was
        // still driving, and the world kept reporting `playing`.
        if (zombie.x < tuning::kLoseX) {
            if (mower.state != 0) {
                ++leaked_;
                status_ = "lost";
                event("level_lost", Json{{"row", zombie.row}, {"x", zombie.x}, {"mower", mower.state}});
                inZombieLoop_ = false;
                return;
            }
        }
        if (zombie.x < tuning::kMowerTriggerX && mower.state == 0) {
            mower.state = 1;
            event("mower_triggered", Json{{"row", zombie.row}});
        }
    }
    inZombieLoop_ = false;
    // Spawns requested from inside the loop are applied here, after iteration, so the
    // vector never reallocates under the references the loop just used.
    if (!pendingSpawns_.empty()) {
        auto queued = std::move(pendingSpawns_);
        pendingSpawns_.clear();
        for (const auto& spawn : queued) spawnZombieAt(spawn.type, spawn.row, spawn.x);
    }
}

bool World::tryVault(ZombieEntity& zombie) {
    if (static_cast<double>(tick_) < zombie.nextSpecialTick) return false;
    for (int col = 0; col < cols_; ++col) {
        auto* plant = plantAt(zombie.row, col);
        if (!plant || !plant->alive) continue;
        if (plant->family == "spike") continue; // ground cover never blocks a walk
        const double centre = centerOf(col);
        // S5.12: contact-sized window. The hop used to start anywhere inside the eating reach
        // (`kEatRangeCols`, 1.15 columns), which meant a vaulter launched a whole column before
        // it ever touched the plant and the event could not say what it had stepped over.
        const double ahead = zombie.x - centre;
        if (ahead < -0.05 || ahead > tuning::kVaultTriggerMaxCols) continue;
        // Land beyond the far (left) edge of the plant so the same plant can never be
        // the vault target again; the cooldown is a second line of defence only.
        const double landing = centre - tuning::kVaultLandingCols;
        const double from = zombie.x;
        zombie.x = landing;
        zombie.state = ZombieState::walking;
        zombie.target = 0;
        zombie.nextSpecialTick = tick_ + static_cast<std::uint64_t>(ticksOf(2.0));
        // `jump` separates "stepped over the plant" from "was already past its centre and only
        // got nudged back to the far side"; `distance` is the horizontal travel the hop claims.
        const int jumped = (from > centre && landing < centre) ? 1 : 0;
        event("zombie_hop", Json{{"id", zombie.id}, {"row", zombie.row}, {"col", col},
                                 {"x", landing}, {"from", from}, {"to", landing},
                                 {"distance", from - landing}, {"jump", jumped}});
        return true;
    }
    return false;
}

void World::tickSuns() {
    // Suns are decayed in `reap`; the tick hook exists so audio/animation can be
    // attached in S5 without touching the kernel.
}

void World::tickMowers() {
    const double dt = stepSeconds;
    for (auto& mower : mowers_) {
        if (mower.state != 1) continue;
        mower.x += tuning::kMowerSpeedColsPerSec * dt;
        for (auto& zombie : zombies_) {
            if (!zombie.alive || zombie.row != mower.row) continue;
            // A boss entry survives the mower. `damageZombie` routes a staged boss into
            // `damageBoss`, which spends one stage per hit, so a mower rolling past for a few
            // ticks would delete the whole boss encounter (measured: modern_93 lost its boss
            // to `mowerKills` before this guard).
            if (zombie.isBoss) continue;
            if (std::abs(zombie.x - mower.x) > 0.6) continue;
            const bool aliveBefore = zombie.alive;
            damageZombie(zombie.id, 100000, false, false);
            if (aliveBefore && !zombie.alive) ++mowerKills_;
        }
        if (mower.x > static_cast<double>(cols_) + 1.0) {
            mower.state = 2;
            event("mower_spent", Json{{"row", mower.row}});
        }
    }
}

void World::reap() {
    plants_.erase(std::remove_if(plants_.begin(), plants_.end(),
                                 [](const PlantEntity& plant) { return !plant.alive; }),
                  plants_.end());
    // Grid items leave immediately: a broken gravestone does not need a death animation, and a
    // corpse that still occupied the cell would keep the cell unplantable.
    gridItems_.erase(std::remove_if(gridItems_.begin(), gridItems_.end(),
                                    [](const GridItemEntity& item) { return !item.alive; }),
                     gridItems_.end());
    // Corpses linger for `kZombieDeathFadeSeconds` so the view can play a death
    // animation; every gameplay loop skips `!alive`, so this is cosmetic only.
    const std::uint64_t fadeTicks = ticksOf(tuning::kZombieDeathFadeSeconds);
    zombies_.erase(std::remove_if(zombies_.begin(), zombies_.end(),
                                  [this, fadeTicks](const ZombieEntity& zombie) {
                                      if (zombie.alive) return false;
                                      return tick_ >= zombie.deathTick + fadeTicks;
                                  }),
                   zombies_.end());
    shots_.erase(std::remove_if(shots_.begin(), shots_.end(),
                                [](const ShotEntity& shot) { return !shot.alive; }),
                 shots_.end());
    const auto now = tick_;
    suns_.erase(std::remove_if(suns_.begin(), suns_.end(),
                               [now](const SunEntity& sun) { return now > sun.expires; }),
                suns_.end());
}

void World::resolveOutcome() {
    if (finished()) return;
    // `allSpawned()` already implies the director's cursor passed the last tick;
    // the old extra `tick_ + flush < lastTick` guard could never be true and only
    // looked like a rule. What still has to drain is the deferred spawn queue and
    // the zombie list itself.
    if (!director_.allSpawned() || !pendingSpawns_.empty()) return;
    if (!zombies_.empty()) return;
    status_ = "won";
    event("level_won", Json{{"tick", tick_}, {"spawned", spawned_}, {"killed", killed_}});
}

// ------------------------------------------------------------ plant builds ---
World::PlantStats World::plantStatsOf(const std::string& type) const {
    PlantStats stats;
    const auto it = catalog_.plants.find(type);
    if (it != catalog_.plants.end()) {
        stats.cost = static_cast<double>(it->second.cost);
        stats.hp = it->second.hp > 0 ? it->second.hp : 300.0;
        stats.recharge = it->second.cooldown > 0 ? it->second.cooldown : 5.0;
        return stats;
    }
    // The pack knows 339 original types while content names 147: a pack-only type still has
    // a cost, a hitpoint total and a recharge, so resolve them from the sheet.
    const content::PlantType* packed = catalog_.rules ? catalog_.rules->findPlant(type) : nullptr;
    if (packed == nullptr) return stats;
    stats.cost = packed->cost.value_or(100.0);
    stats.hp = packed->hitpoints.value_or(300.0);
    stats.recharge = packed->packetCooldown.value_or(5.0);
    if (stats.hp <= 0) stats.hp = 300.0;
    if (stats.recharge <= 0) stats.recharge = 5.0;
    return stats;
}

PlantEntity World::constructPlant(const std::string& type, int row, int col, bool chargeSun) {
    const PlantStats stats = plantStatsOf(type);
    const auto it = catalog_.plants.find(type);
    PlantEntity plant;
    plant.id = nextId_++;
    plant.type = type;
    if (it != catalog_.plants.end()) {
        plant.family = familyOf(it->second);
    } else {
        const std::string_view judged = plantFamilyFor(type);
        plant.family = judged.empty() ? "support" : std::string(judged);
        if (judged.empty()) noteUnwiredPlant(type);
    }
    plant.row = row;
    plant.col = col;
    plant.hp = stats.hp;
    plant.maxHp = stats.hp;
    plant.born = tick_;
    if (catalog_.rules) {
        if (const auto* rules = catalog_.rules->findPlant(type)) {
            for (const auto& action : rules->actions) {
                ActionSlot slot;
                slot.kind = std::string(content::actionKindName(action.kind));
                slot.rawType = action.rawType;
                if (action.projectile) slot.projectileType = action.projectile->name;
                slot.trigger = action.trigger;
                slot.damage = action.damage.value_or(0);
                slot.splash = action.splashDamage.value_or(0);
                slot.slow = action.chillDuration.value_or(0) + action.freezeDuration.value_or(0);
                slot.radius = action.explodeRadius.value_or(0);
                if (action.triggerRect) {
                    slot.triggerWidth = action.triggerRect->width;
                    slot.triggerHeight = action.triggerRect->height;
                }
                slot.cooldownTicks = static_cast<int>(ticksOf(action.cooldownMin.value_or(1.0)));
                slot.initialTicks = static_cast<int>(ticksOf(action.initialMin.value_or(0.0)));
                slot.remainingTicks = slot.initialTicks;
                slot.pierce = it != catalog_.plants.end() ? pierceOf(it->second.raw) : 0;
                plant.slots.push_back(slot);
            }
        }
    }
    // Sun costs are integers in the pack (`Cost`); the double path only exists so the three
    // sources can share one variable. Round instead of truncating so a fractional cost never
    // quietly costs less than the sheet says. Fusion calls this without a balance check,
    // which is why the subtraction lives here rather than in `plant()`.
    const auto charged = static_cast<std::int64_t>(std::llround(stats.cost));
    if (chargeSun) {
        sun_ -= charged;
        // S6: the spend total lives next to the charge itself, so every path that costs sun
        // (planting and fusion) is counted exactly once. A conveyor card and a plant the level
        // laid down itself never reach here with `chargeSun == true`.
        sunSpent_ += charged;
    }
    return plant;
}

// ------------------------------------------------------- level mechanics (S5.13) ---
void World::layInitialField() {
    if (mechanics_ == nullptr) return;
    const auto place = [this](const InitialPlant& placement, bool isProtected) {
        if (!inBounds(placement.gridY, placement.gridX)) return;
        if (plantAt(placement.gridY, placement.gridX) != nullptr ||
            gridItemAt(placement.gridY, placement.gridX) != nullptr) {
            // A target the sheet places on a taken cell (`egypt_74` stacks three on one cell) cannot
            // be laid twice: say so instead of pretending the board holds it.
            if (isProtected) {
                ++unplacedProtectedPlants_;
                event("protect_plant_unplaced", Json{{"level", level_.id},
                                                     {"plant", placement.plant},
                                                     {"row", placement.gridY},
                                                     {"col", placement.gridX}});
            }
            return;
        }
        PlantEntity plant = constructPlant(placement.plant, placement.gridY, placement.gridX, false);
        plant.protectedPlant = isProtected;
        plants_.push_back(plant);
        ++initialPlantsLaid_;
        if (isProtected) ++protectedPlants_;
        event(isProtected ? "protect_plant_placed" : "initial_plant",
              Json{{"type", plant.type}, {"row", plant.row}, {"col", plant.col}, {"id", plant.id}});
    };
    for (const InitialPlant& placement : mechanics_->initialPlants) place(placement, false);
    // The protect mission's targets are part of the opening board even when `initialPlants` did
    // not name them (`beach_14` names them in both, `dark_*` levels often only here).
    for (const InitialPlant& placement : mechanics_->protect.plants) place(placement, true);
    // T59: the sheet can ask for more survivors than its own board can carry. `egypt_74` lists
    // five targets on three cells, and six missions (`carnival_79`, `carnival_81`,
    // `chinesegarden_57`, `frontyard_53`, `lostcity_67`, `sky_31`) list targets that land on no
    // cell at all because the level's board or its `initialGridItems` filled them first. Those
    // six are the reason this check exists: with `protectedPlants_ == 0` the death path in
    // `damagePlant` can never run, so the mission silently passes no matter what the player does.
    // Reporting the gap does not change the rules - `egypt_74` stays winnable when all three
    // targets survive - it only makes the missing capacity visible and countable.
    const int mustProtect = mechanics_->protect.requiredSurvivors();
    if (mustProtect > 0 && protectedPlants_ < mustProtect) {
        protectCapacityShortfall_ = mustProtect - protectedPlants_;
        event("protect_capacity_shortfall", Json{{"level", level_.id},
                                                 {"placed", protectedPlants_},
                                                 {"must", mustProtect},
                                                 {"delta", protectCapacityShortfall_}});
    }
    for (const GridItemPlacement& placement : mechanics_->initialGridItems) {
        addGridItem(placement.item, placement.gridY, placement.gridX);
    }
    if (mechanics_->hasConveyor()) refillConveyor();
}

EntityId World::addGridItem(const std::string& type, int row, int col) {
    if (!inBounds(row, col)) return 0;
    if (plantAt(row, col) != nullptr || gridItemAt(row, col) != nullptr) return 0;
    GridItemEntity item;
    item.id = nextId_++;
    item.type = type;
    item.row = row;
    item.col = col;
    // The sheet names the species but no hit points (a gravestone is a `GridItemType`, not a
    // zombie), so one tuning constant covers every item. It is deliberately low enough that one
    // Cherry Bomb clears a cell, which is what "可被炸" means in practice.
    item.hp = tuning::kGridItemHitPoints;
    item.maxHp = item.hp;
    gridItems_.push_back(item);
    event("grid_item_spawned", Json{{"id", item.id}, {"type", type}, {"row", row}, {"col", col}});
    return item.id;
}

void World::damageGridItem(GridItemEntity& item, double amount) {
    if (!item.alive) return;
    item.hp -= amount;
    if (item.hp > 0) return;
    item.hp = 0;
    item.alive = false;
    event("grid_item_destroyed", Json{{"id", item.id}, {"type", item.type}, {"row", item.row}, {"col", item.col}});
}

void World::spawnGravestonesForWave(std::size_t wave) {
    if (mechanics_ == nullptr || mechanics_->gravestones.empty()) return;
    const int asInt = static_cast<int>(wave);
    if (asInt <= gravestonesServedWave_) return;
    gravestonesServedWave_ = asInt;
    for (const GravestoneWave& drop : mechanics_->gravestones) {
        if (drop.wave != asInt) continue;
        for (const GridItemPlacement& placement : drop.positions) {
            addGridItem(placement.item, placement.gridY, placement.gridX);
        }
    }
}

void World::refillConveyor() {
    if (mechanics_ == nullptr || mechanics_->conveyor.slots.empty()) return;
    const ConveyorSpec& spec = mechanics_->conveyor;
    const auto handSize = static_cast<std::size_t>(tuning::kConveyorHandSize);
    while (conveyorCards_.size() < handSize) {
        int total = 0;
        for (const ConveyorSlotRow& slot : spec.slots) total += static_cast<int>(slot.weight * 100.0 + 0.5);
        if (total <= 0) return;
        std::uniform_int_distribution<int> dist(0, total - 1);
        int pick = dist(conveyorRng_);
        for (const ConveyorSlotRow& slot : spec.slots) {
            const int weight = static_cast<int>(slot.weight * 100.0 + 0.5);
            if (pick < weight) {
                conveyorCards_.push_back(slot.plant);
                break;
            }
            pick -= weight;
        }
    }
    event("conveyor_dealt", Json{{"cards", conveyorCards_}, {"hand", conveyorCards_.size()}});
}

std::string World::plantFromConveyor(const std::string& type, int row, int col) {
    if (!inBounds(row, col)) return "cell out of bounds";
    if (plantAt(row, col) != nullptr || gridItemAt(row, col) != nullptr) return "cell occupied";
    const auto card = std::find(conveyorCards_.begin(), conveyorCards_.end(), type);
    if (card == conveyorCards_.end()) return "not on the conveyor";
    conveyorCards_.erase(card);
    PlantEntity plant = constructPlant(type, row, col, false);
    plants_.push_back(plant);
    // The belt is the economy: no sun, no recharge, and the hand refills itself afterwards.
    event("planted", Json{{"type", type}, {"row", row}, {"col", col}, {"id", plant.id},
                          {"conveyor", true}});
    refillConveyor();
    return {};
}

// ----------------------------------------------------- T66 special spawners ---
void World::scheduleSpawnersForWave(int wave) {
    if (mechanics_ == nullptr || wave <= 0 || wave <= spawnerServedWave_) return;
    spawnerServedWave_ = wave;
    for (const SpawnerSpec& spec : mechanics_->spawners) {
        // A portal is not a generator: it reroutes the wave's own spawns (see `tickWaves`), so
        // there is nothing for it to queue here.
        if (spec.kind == SpawnerKind::portal) continue;
        if (!spawnerKindIsWired(spec.kind)) continue;
        for (const SpawnerRow& row : spec.rows) {
            if (!row.scheduled() || row.wave != wave) continue;
            scheduleSpawnerRow(row);
        }
    }
}

void World::scheduleSpawnerRow(const SpawnerRow& row) {
    // `spawners.dino`: the sheet names no zombie and no damage, only the row a dinosaur walks
    // down and how long it takes. Letting it eat the lawn would be invented damage, so the sweep
    // is an event and still counts as the arrival it is.
    if (row.kind == SpawnerKind::dino) {
        const int target = spawnerRowFor(row);
        ++spawnerSpawned_[spawnerKindName(row.kind)];
        event("dino_sweep", Json{{"wave", row.wave}, {"row", target},
                                 {"seconds", row.betweenGroups}, {"level", level_.id}});
        return;
    }
    std::vector<SpawnerZombie> pool = row.zombies;
    int count = static_cast<int>(pool.size());
    if (pool.empty() && row.kind == SpawnerKind::beach) {
        // `spawners.beach` names no type at all: the tide brings in whatever that wave was already
        // sending, so the level's own wave pool is the only source the sheets give. The row's
        // `zombieCount`/`groupSize` say how many of them come in this way.
        const auto index = static_cast<std::size_t>(row.wave - 1);
        if (index < level_.waves.size()) {
            for (const ZombieSpawn& entry : level_.waves[index].zombies) {
                pool.push_back(SpawnerZombie{entry.type, entry.row.value_or(-1)});
            }
        }
        if (pool.empty()) {
            // No pool to take from: this row cannot be honoured without inventing zombies.
            mechanicUnknown_["spawners.beach.notypes"] += 1;
            event("spawner_row_skipped", Json{{"kind", spawnerKindName(row.kind)}, {"wave", row.wave},
                                              {"level", level_.id}, {"reason", "no zombie pool"}});
            return;
        }
        count = row.count > 0 ? row.count : row.groupSize;
        if (count <= 0) count = 1;
    } else if (pool.empty()) {
        return;
    }
    for (int index = 0; index < count; ++index) {
        const SpawnerZombie& zombie = pool[static_cast<std::size_t>(index) % pool.size()];
        // A spawner row may pin each zombie's row (ground/fish/storm do); when it does not, the
        // arrival is drawn from the spawner generator so a level's first run is not the only run.
        const int target = zombie.row >= 0 ? zombie.row : spawnerRowFor(row);
        double delay = 0.0;
        if (row.kind == SpawnerKind::grid) delay = row.waitSeconds * static_cast<double>(index);
        else if (row.kind == SpawnerKind::storm || row.kind == SpawnerKind::spider) {
            delay = row.betweenGroups * static_cast<double>(index);
        }
        queueSpawnerZombie(row.kind, zombie.type, target, spawnerColumnFor(row), delay);
    }
}

void World::tickSpawners() {
    if (spawnerQueue_.empty()) return;
    std::vector<QueuedSpawner> keep;
    keep.reserve(spawnerQueue_.size());
    for (const QueuedSpawner& queued : spawnerQueue_) {
        if (queued.dueTick > tick_) {
            keep.push_back(queued);
            continue;
        }
        if (!spawnZombieAt(queued.type, queued.row, queued.x)) {
            ++rejectedSpawns_;
            event("spawner_spawn_rejected", Json{{"kind", queued.kind}, {"type", queued.type},
                                                 {"row", queued.row}});
            continue;
        }
        ++spawnerSpawned_[queued.kind];
        event("spawner_spawn", Json{{"kind", queued.kind}, {"type", queued.type},
                                    {"row", queued.row}, {"x", queued.x}});
    }
    spawnerQueue_ = std::move(keep);
}

void World::queueSpawnerZombie(SpawnerKind kind, const std::string& type, int row, double x,
                               double delaySeconds) {
    QueuedSpawner queued;
    queued.dueTick = tick_ + ticksOf(delaySeconds > 0.0 ? delaySeconds : 0.0);
    queued.kind = spawnerKindName(kind);
    queued.type = type;
    queued.row = row;
    queued.x = x;
    spawnerQueue_.push_back(queued);
}

int World::spawnerRowFor(const SpawnerRow& row) {
    if (rows_ <= 0) return 0;
    if (row.row >= 0) return std::min(row.row, rows_ - 1);
    // Never the wave RNG: a storm must not reshuffle the wave schedule of the level it hits.
    const auto draw = static_cast<unsigned>(spawnerRng_() % static_cast<unsigned>(rows_));
    return static_cast<int>(draw);
}

double World::spawnerColumnFor(const SpawnerRow& row) const {
    int col = row.columnEnd >= 0 ? row.columnEnd : row.columnStart;
    if (col < 0) return static_cast<double>(cols_) + 0.6;
    if (col >= cols_) col = cols_ - 1;
    return centerOf(col);
}

int World::mechanicUnknownInstances() const {
    int total = 0;
    for (const auto& [kind, count] : mechanicUnknown_) total += count;
    return total;
}

// ------------------------------------------------------------ player input ---
std::string World::plant(const std::string& type, int row, int col) {
    if (finished()) return "level finished";
    const auto it = catalog_.plants.find(type);
    // 147 plants carry a content entry; the pack knows 339 original types. A
    // pack-only type is real data, so plant it with the pack's cost/hitpoints
    // and the family table's judgement instead of refusing it.
    const content::PlantType* packed = catalog_.rules ? catalog_.rules->findPlant(type) : nullptr;
    if (it == catalog_.plants.end() && packed == nullptr) return "unknown plant: " + type;
    if (plants_.size() >= static_cast<std::size_t>(tuning::kMaxPlants)) return "too many plants";
    // S5.13: a conveyor level has no seed bank. The cards come off the belt, cost no sun and
    // ignore both the deck list and the recharge table, but only a card that is actually in the
    // hand can be played - so a script that planted with sun still works (nothing is charged),
    // while planting something the belt never dealt is refused instead of being silently free.
    if (conveyorLevel()) return plantFromConveyor(type, row, col);
    // The level deck is the authority on what may be planted; the legacy kernel
    // returned "not-in-deck" here and dropping that check let scripts and UI plant
    // anything at all, which also makes a replay's legality unverifiable.
    if (!level_.deck.empty() && std::find(level_.deck.begin(), level_.deck.end(), type) == level_.deck.end()) {
        return "not-in-deck";
    }
    if (!inBounds(row, col)) return "cell out of bounds";
    if (plantAt(row, col)) return "cell occupied";
    // A grid item (gravestone, puddle) blocks the cell just like a plant does.
    if (gridItemAt(row, col) != nullptr) return "cell occupied";
    if (cooldown(type) > tick_) return "cooling down";

    const PlantStats stats = plantStatsOf(type);
    if (static_cast<double>(sun_) < stats.cost) return "not enough sun";

    PlantEntity plant = constructPlant(type, row, col);
    cooldowns_[type] = tick_ + ticksOf(stats.recharge);
    plants_.push_back(plant);
    event("planted", Json{{"type", type}, {"row", row}, {"col", col}, {"id", plant.id}});
    return {};
}

bool World::shovel(int row, int col) {
    auto* plant = plantAt(row, col);
    if (plant) {
        // A protect mission's target is the objective, not a plant the player may harvest: digging
        // it up would fail the level through a path that never looks like a failure.
        if (plant->protectedPlant) {
            event("shovel_blocked", Json{{"id", plant->id}, {"type", plant->type}, {"reason", "protected"}});
            return false;
        }
        const auto id = plant->id;
        plant->alive = false;
        event("shovelled", Json{{"row", row}, {"col", col}, {"id", id}});
        return true;
    }
    // S5.13: a gravestone or puddle can be dug out as well. Before this the shovel only knew
    // plants, so a blocked cell stayed blocked for the whole level.
    for (auto& item : gridItems_) {
        if (!item.alive || item.row != row || item.col != col) continue;
        item.alive = false;
        item.hp = 0;
        event("grid_item_removed", Json{{"id", item.id}, {"type", item.type}, {"row", row}, {"col", col}});
        return true;
    }
    return false;
}

bool World::collect(EntityId id) {
    for (auto it = suns_.begin(); it != suns_.end(); ++it) {
        if (it->id != id) continue;
        sun_ += it->value;
        event("sun_collected", Json{{"id", id}, {"value", it->value}});
        suns_.erase(it);
        return true;
    }
    return false;
}

// ------------------------------------------------------- plant food / fusion ---
bool World::canFeed(const std::string& type) const {
    return options_.plantfood && plantFood_ != nullptr && plantFood_->has(type);
}

bool World::feed(EntityId id) {
    PlantEntity* plant = plantById(id);
    if (plant == nullptr || !plant->alive) return false;
    if (!options_.plantfood || plantFood_ == nullptr) return false;
    const PlantFoodRow* row = plantFood_->find(plant->type);
    // 293 of the 339 pack types carry a duration; anything else uses the tuning constant so a
    // feed always has a length instead of quietly doing nothing.
    const double seconds = row != nullptr && row->durationSeconds && *row->durationSeconds > 0
                               ? *row->durationSeconds
                               : tuning::kPlantFoodFallbackSeconds;
    plant->plantFoodTicks = std::max(1, static_cast<int>(ticksOf(seconds)));
    bool usesAction = false;
    for (auto& slot : plant->slots) {
        if (slot.kind != "plantfood") continue;
        // `action_runner` stays the only place that turns a declaration into entities: the
        // feed arms the slot and the next tick plays it, so the sheet's SpawnOffset,
        // projectile and cooldown keep one code path instead of a second one here.
        slot.remainingTicks = 0;
        plant->plantFoodArmed = true;
        usesAction = true;
        break;
    }
    event("plant_fed",
          Json{{"id", id}, {"type", plant->type}, {"ticks", plant->plantFoodTicks}, {"action", usesAction}});
    return true;
}

std::vector<PlantFoodState> World::plantFoodStates() const {
    std::vector<PlantFoodState> states;
    for (const auto& plant : plants_) {
        if (!plant.alive || plant.plantFoodTicks <= 0) continue;
        PlantFoodState state;
        state.plant = plant.id;
        state.type = plant.type;
        state.remainingTicks = plant.plantFoodTicks;
        for (const auto& slot : plant.slots) {
            if (slot.kind != "plantfood") continue;
            state.usesActionSlot = true;
            break;
        }
        states.push_back(state);
    }
    return states;
}

bool World::tryFuse(EntityId a, EntityId b) {
    if (!options_.fusion || fusion_ == nullptr || a == b) return false;
    PlantEntity* first = plantById(a);
    PlantEntity* second = plantById(b);
    // `plantById` keeps dead entries (removal only clears `alive`) so a stale id from a previous
    // fusion would look alive enough to pair again; both plants must still stand.
    if (first == nullptr || second == nullptr || !first->alive || !second->alive) return false;
    // Fusion is a neighbour reaction. The same cell cannot happen (a cell holds one plant),
    // so "same or adjacent" means Chebyshev distance 1, diagonals included.
    if (std::abs(first->row - second->row) > 1 || std::abs(first->col - second->col) > 1) return false;
    const FusionRecipe* recipe = fusion_->find(first->type, second->type);
    if (recipe == nullptr) return false;
    // Results are client ids (`fused_snowpea`) even when the ingredients are pack ids, and a
    // recipe may name a type only the pack knows; both must be buildable.
    const bool plantable = catalog_.plants.count(recipe->result) > 0 ||
                           (catalog_.rules && catalog_.rules->findPlant(recipe->result) != nullptr);
    if (!plantable) return false;
    // Copy what is needed before `plants_` may reallocate under the two pointers.
    const EntityId firstId = first->id;
    const EntityId secondId = second->id;
    const int row = first->row;
    const int col = first->col;
    const double cost = plantStatsOf(recipe->result).cost;
    first->alive = false;
    second->alive = false;
    PlantEntity fused = constructPlant(recipe->result, row, col);
    plants_.push_back(fused);
    ++fusions_;
    event("fusion", Json{{"a", firstId},
                         {"b", secondId},
                         {"into", fused.id},
                         {"result", recipe->result},
                         {"row", row},
                         {"col", col},
                         {"cost", cost},
                         {"sound", recipe->sound}});
    return true;
}

// ----------------------------------------------------------------- boss (S5.8) -----
void World::trySpawnBoss() {
    if (bossSpawned_ || bossTable_ == nullptr || !bossPick_.spawned()) return;
    // The sheet records *where* the boss stands, not when it arrives; the arrival beat is the
    // end of the wave schedule, which is also the first tick the player has cleared the lawn.
    if (!director_.allSpawned() || !pendingSpawns_.empty()) return;
    const BossDefinition* boss = bossPick_.kind == BossSelection::Kind::mechanic ? bossPick_.boss : nullptr;
    if (boss != nullptr && !boss->stages.empty()) {
        if (zombies_.size() >= static_cast<std::size_t>(tuning::kMaxZombies)) return;
        ZombieEntity zombie;
        zombie.id = nextId_++;
        zombie.type = boss->id;
        zombie.className = boss->className;
        // `boss` is a behaviour the registry deliberately does not have: `tickBoss` drives this
        // entity instead of the walker families below it.
        zombie.family = "boss";
        zombie.row = clampInt(boss->spawn.gridY, 0, rows_ - 1);
        // The sheet gives a grid cell; the kernel stands entities on column centres.
        zombie.x = static_cast<double>(clampInt(boss->spawn.gridX, 0, cols_ - 1)) + 0.5;
        zombie.hp = boss->stages.front().hitPoints;
        zombie.maxHp = zombie.hp;
        // A staged boss neither walks nor eats: its timeline comes from the sheet.
        zombie.speed = 0.0;
        zombie.eatDps = 0.0;
        zombie.state = ZombieState::walking;
        zombie.alive = true;
        zombie.spawnTick = tick_;
        zombie.isBoss = true;
        zombie.stageIndex = 0;
        zombie.bossStages = static_cast<int>(boss->stages.size());
        zombie.bossHp = zombie.hp;
        zombie.bossMaxHp = zombie.hp;
        zombies_.push_back(zombie);
        bossSpawned_ = true;
        ++spawned_;
        event("boss_spawn", Json{{"id", zombies_.back().id},
                                 {"type", zombies_.back().type},
                                 {"row", zombies_.back().row},
                                 {"x", zombies_.back().x},
                                 {"stages", zombies_.back().bossStages},
                                 {"hp", zombies_.back().hp}});
        activateBossStage(zombies_.back());
        return;
    }
    // The 3 `gargantuar`-marker levels name a plain zombie type: it goes through the normal
    // spawner (content first, pack fallback) and only carries the flag. It has no spawn cell,
    // so it walks in on the middle row like any other wave.
    const std::size_t before = zombies_.size();
    if (!spawnZombie(bossPick_.zombieType, rows_ / 2)) return;
    if (zombies_.size() == before) {
        // Deferred through `pendingSpawns_` (a family spawned it mid-loop); the flag would be
        // lost, so say so rather than silently shipping an unmarked boss.
        event("boss_unavailable", Json{{"marker", bossPick_.marker}, {"world", level_.world},
                                       {"level", level_.id}, {"reason", "deferred-spawn"}});
        ++bossUnavailable_;
        return;
    }
    ZombieEntity& zombie = zombies_.back();
    zombie.isBoss = true;
    zombie.bossStages = 0; // no stage list: this one is an ordinary zombie with a flag
    zombie.bossHp = zombie.maxHp = zombie.hp;
    zombie.bossMaxHp = zombie.hp;
    bossSpawned_ = true;
    event("boss_spawn", Json{{"id", zombie.id},
                             {"type", zombie.type},
                             {"row", zombie.row},
                             {"x", zombie.x},
                             {"stages", 0},
                             {"hp", zombie.hp}});
}

void World::activateBossStage(ZombieEntity& zombie) {
    const BossDefinition* boss = bossDefinition_;
    if (boss == nullptr || zombie.stageIndex < 0 ||
        static_cast<std::size_t>(zombie.stageIndex) >= boss->stages.size()) {
        zombie.bossIdleTicks = 0;
        zombie.bossStunTicks = 0;
        return;
    }
    const BossStage& stage = boss->stages[static_cast<std::size_t>(zombie.stageIndex)];
    // `hp`/`bossHp` hold the *current* stage's hit points, so a stage change is a refill rather
    // than a running total: the sheet lists per-stage HP, not cumulative.
    zombie.bossHp = stage.hitPoints;
    zombie.hp = stage.hitPoints;
    zombie.bossMaxHp = stage.hitPoints;
    zombie.bossIdleTicks = static_cast<int>(ticksOf(stage.idleMaxSeconds));
    zombie.bossStunTicks = static_cast<int>(ticksOf(stage.stunSeconds));
    zombie.nextSpecialTick = tick_ + static_cast<std::uint64_t>(std::max(0, zombie.bossIdleTicks));
    // Count what the sheet declares but the kernel cannot play, once per activation: breath,
    // imp throws and speaker rays have no column window, so they are data we keep, not data we
    // pretend to run.
    std::vector<std::string> unwired;
    for (const auto& action : stage.actions) {
        if (action.fire || action.type.empty()) continue;
        if (std::find(unwired.begin(), unwired.end(), action.type) == unwired.end()) unwired.push_back(action.type);
    }
    if (!unwired.empty()) {
        bossActionUnwired_ += unwired.size();
        event("boss_action_unwired", Json{{"stage", zombie.stageIndex}, {"types", unwired}});
    }
    event("boss_stage", Json{{"id", zombie.id},
                             {"stage", zombie.stageIndex},
                             {"stages", zombie.bossStages},
                             {"hp", zombie.bossHp},
                             {"idleTicks", zombie.bossIdleTicks},
                             {"stunTicks", zombie.bossStunTicks},
                             {"fireActions", stage.fireActions()}});
}

void World::tickBoss(ZombieEntity& zombie) {
    const BossDefinition* boss = bossDefinition_;
    if (boss == nullptr || zombie.stageIndex < 0 ||
        static_cast<std::size_t>(zombie.stageIndex) >= boss->stages.size()) {
        return;
    }
    // Stun first: a stunned boss cannot start a volley, and the sheet's `stunSeconds` is the
    // recovery window after a stage drops, not a second timeline.
    if (zombie.bossStunTicks > 0) {
        --zombie.bossStunTicks;
        return;
    }
    if (zombie.bossIdleTicks > 0) {
        --zombie.bossIdleTicks;
        if (zombie.bossIdleTicks > 0) return;
    }
    const BossStage& stage = boss->stages[static_cast<std::size_t>(zombie.stageIndex)];
    const std::size_t fires = stage.fireActions();
    if (fires == 0) return;
    // One volley per idle window: fire every window the stage declares, then re-arm the idle
    // timer. `idleSeconds.min` is deliberately unused - the sheet's band is a range, and a
    // deterministic kernel has to pick one end (the upper one, so stages do not stack).
    std::size_t hits = 0;
    for (const auto& action : stage.actions) {
        if (!action.fire) continue;
        const int low = clampInt(std::min(action.fireMinColumn, action.fireMaxColumn), 0, cols_ - 1);
        const int high = clampInt(std::max(action.fireMinColumn, action.fireMaxColumn), 0, cols_ - 1);
        const int span = std::max(1, action.fireRowRange);
        const int rowHigh = clampInt(zombie.row + span - 1, 0, rows_ - 1);
        for (auto& plant : plants_) {
            if (!plant.alive) continue;
            if (plant.row < zombie.row || plant.row > rowHigh) continue;
            if (plant.col < low || plant.col > high) continue;
            damagePlant(plant.id, tuning::kBossFireDamage);
            ++hits;
        }
        event("boss_fire", Json{{"id", zombie.id},
                                {"stage", zombie.stageIndex},
                                {"action", action.type},
                                {"minColumn", low},
                                {"maxColumn", high},
                                {"rows", span},
                                {"row", zombie.row},
                                {"speed", action.fireSpeed},
                                {"hitTime", action.fireHitTime},
                                {"hits", hits}});
    }
    zombie.bossIdleTicks = static_cast<int>(ticksOf(stage.idleMaxSeconds));
    zombie.nextSpecialTick = tick_ + static_cast<std::uint64_t>(std::max(0, zombie.bossIdleTicks));
}

void World::damageBoss(ZombieEntity& zombie, double amount, bool countsAsKill) {
    if (amount <= 0) return;
    zombie.bossHp -= amount;
    zombie.hp = std::max(0.0, zombie.bossHp);
    if (zombie.bossHp > 0) return;
    const BossDefinition* boss = bossDefinition_;
    const int stages = boss != nullptr ? static_cast<int>(boss->stages.size()) : zombie.bossStages;
    if (boss != nullptr && zombie.stageIndex + 1 < stages) {
        ++zombie.stageIndex;
        // A single hit never skips a stage: the overflow is dropped rather than carried, because
        // each stage has its own idle/retreat beat and swallowing one would hide a volley.
        activateBossStage(zombie);
        return;
    }
    zombie.bossHp = 0;
    zombie.hp = 0;
    zombie.alive = false;
    zombie.state = ZombieState::dying;
    zombie.deathTick = tick_;
    if (countsAsKill) ++killed_;
    event("boss_died", Json{{"id", zombie.id}, {"type", zombie.type}, {"stage", zombie.stageIndex},
                            {"stages", zombie.bossStages}});
}

std::vector<BossState> World::bossStates() const {
    std::vector<BossState> out;
    for (const auto& zombie : zombies_) {
        if (!zombie.alive || !zombie.isBoss) continue;
        BossState state;
        state.id = zombie.id;
        state.type = zombie.type;
        state.stageIndex = zombie.stageIndex;
        state.stages = zombie.bossStages;
        state.hp = zombie.bossHp;
        state.maxHp = zombie.bossMaxHp;
        state.idleTicks = zombie.bossIdleTicks;
        state.stunTicks = zombie.bossStunTicks;
        out.push_back(std::move(state));
    }
    return out;
}

bool World::spawnZombie(const std::string& type, int row) {
    return spawnZombieAt(type, row, static_cast<double>(cols_) + 0.6);
}

bool World::spawnZombieAt(const std::string& type, int row, double x) {
    if (row < 0 || row >= rows_) return false;
    if (zombies_.size() >= static_cast<std::size_t>(tuning::kMaxZombies)) return false;
    const auto it = catalog_.zombies.find(type);
    // The compiled pack carries 1127 zombie types while the shipped content
    // JSON only names 55; a type that exists only in the pack is still real
    // data, so spawn it from the pack instead of refusing it.
    const content::ZombieType* packed = catalog_.rules ? catalog_.rules->findZombie(type) : nullptr;
    if (it == catalog_.zombies.end() && packed == nullptr) return false;
    if (inZombieLoop_) {
        // Called from a zombie behaviour while `tickZombies` iterates `zombies_`:
        // defer the insert to `flushPendingSpawns` at the end of that loop.
        pendingSpawns_.push_back(PendingSpawn{type, row, x});
        return true;
    }
    ZombieEntity zombie;
    zombie.id = nextId_++;
    zombie.type = type;
    // Family resolution order: original `ZombieClass` (generated table) > shipped
    // content `behavior` > `walk`. The pack-only branch below has no content
    // behaviour at all, so its family always comes from the class table.
    std::string family = (it != catalog_.zombies.end() && !it->second.behavior.empty()) ? it->second.behavior
                                                                                       : std::string("walk");
    if (packed != nullptr) {
        zombie.className = packed->className;
        const std::string_view mapped = zombieFamilyFor(zombie.className);
        if (!mapped.empty()) family = std::string(mapped);
    }
    zombie.family = std::move(family);
    zombie.row = row;
    zombie.x = x;
    if (it != catalog_.zombies.end()) {
        const auto& def = it->second;
        zombie.hp = def.hp > 0 ? def.hp : 190;
        zombie.speed = def.speed > 0 ? def.speed : 0.185;
        zombie.eatDps = def.eatDps > 0 ? def.eatDps : 100;
        // Armor is not summed here any more: S5.11 builds the layer stack below, which reads the
        // same `def.armor` numbers when the sheet has no bridge for this zombie.
    } else {
        zombie.hp = packed->hitpoints.value_or(190);
        if (zombie.hp <= 0) zombie.hp = 190;
        zombie.speed = packed->speed.value_or(0.185);
        if (zombie.speed <= 0) zombie.speed = 0.185;
        zombie.eatDps = packed->eatDps.value_or(100);
        if (zombie.eatDps <= 0) zombie.eatDps = 100;
    }
    zombie.maxHp = zombie.hp;
    zombie.spawnTick = tick_;
    zombie.nextSpecialTick = tick_ + ticksOf(2.0);
    // ---- S5.11 armor layers --------------------------------------------------------------
    // Sheet first: a content zombie reaches it through `contentComparison` (10 of the 55), a
    // pack-only zombie through its own id. Everything else keeps the pre-S5.11 reading — one
    // damageable layer per `content/zombies.json` armor entry, no flags — which is why the 45
    // unbridged content zombies keep their exact numbers.
    {
        const ArmorTable& table = armorTable();
        // Two id spaces, two lookups, and they must not be mixed: 20 content zombie ids also have
        // a `zombies[]` row in the sheet (cowboy, mummy, gang_gargantuar, ...) and 6 of those rows
        // carry armor the content definition does not give the zombie (cowboy -> CowboyHatDefault).
        // A content zombie is therefore described by the content definition plus the bridge row
        // only; the sheet's own zombie id is read for pack-only zombies, where it is the only
        // source. Mixing the two moved `world cowboy` and `world muji` in the smoke baseline.
        const bool fromContent = it != catalog_.zombies.end();
        std::vector<ArmorLayer> spec =
            fromContent ? table.contentArmorLayers(zombie.type) : table.zombieArmorLayers(zombie.type);
        for (const ArmorLayer& layer : spec) {
            ArmorLayerState state;
            state.armorId = layer.armorId;
            state.flags = layer.flags;
            state.artLayer = layer.artLayer;
            // `poolsHitPoints()` is false for invincible and sentinel rows: they keep a zero pool
            // so the damage walk can never break them, and only their flags decide the outcome.
            state.maxHp = layer.poolsHitPoints() ? layer.hitpoints : 0.0;
            state.hp = state.maxHp;
            zombie.armorLayers.push_back(std::move(state));
        }
        if (zombie.armorLayers.empty() && fromContent) {
            for (double hitpoints : it->second.armor) {
                ArmorLayerState state;
                state.armorId = "content";
                state.flags = kArmorDamageable;
                state.maxHp = hitpoints;
                state.hp = hitpoints;
                zombie.armorLayers.push_back(std::move(state));
            }
        }
        for (const ArmorLayerState& layer : zombie.armorLayers) zombie.armorHp += layer.hp;
        zombie.armorMaxHp = zombie.armorHp;
    }
    zombies_.push_back(zombie);
    ++spawned_;
    return true;
}

// ---------------------------------------------------------------- services ---
bool World::inBounds(int row, int col) const {
    return row >= 0 && row < rows_ && col >= 0 && col < cols_;
}

PlantEntity* World::plantAt(int row, int col) {
    for (auto& plant : plants_) {
        if (plant.alive && plant.row == row && plant.col == col) return &plant;
    }
    return nullptr;
}

PlantEntity* World::plantById(EntityId id) {
    for (auto& plant : plants_) {
        if (plant.id == id) return &plant;
    }
    return nullptr;
}

GridItemEntity* World::gridItemAt(int row, int col) {
    for (auto& item : gridItems_) {
        if (item.alive && item.row == row && item.col == col) return &item;
    }
    return nullptr;
}

ZombieEntity* World::zombieById(EntityId id) {
    for (auto& zombie : zombies_) {
        if (zombie.id == id) return &zombie;
    }
    return nullptr;
}

ZombieEntity* World::firstZombieAhead(int row, double from, double range) {
    ZombieEntity* best = nullptr;
    for (auto& zombie : zombies_) {
        if (!zombie.alive || zombie.row != row) continue;
        if (zombie.x < from - tuning::kShotBehindToleranceCols) continue; // already walked past
        if (zombie.x - from > range) continue;
        if (!best || zombie.x < best->x) best = &zombie;
    }
    return best;
}

void World::damagePlant(EntityId id, double amount) {
    auto* plant = plantById(id);
    if (!plant || !plant->alive) return;
    plant->hp -= amount;
    if (plant->hp > 0) return;
    plant->hp = 0;
    plant->alive = false;
    // S6: this is the single exit for a plant that died of damage - eaten, smashed by a
    // gargantuar, burned by a boss, spiked - so counting here cannot miss a path. `shovel()`
    // and the two fusion halves clear `alive` themselves and stay out of the count.
    ++plantsLost_;
    event("plant_died", Json{{"id", id}, {"type", plant->type}, {"row", plant->row}, {"col", plant->col}});
    // S5.13 protect mission: the sheet says how many of the protected plants must survive, not
    // "lose on the first death". Eighteen missions require fewer than they list (`beach_88` 4 of
    // 5, `carnival_90` 1 of 2), so dying plants are only a loss once the count drops below the
    // threshold - and `egypt_56` lists fifteen with a threshold of zero, which is a mission that
    // cannot be lost this way at all.
    if (plant->protectedPlant && mechanics_ != nullptr && status_ != "lost") {
        const int required = mechanics_->protect.requiredSurvivors();
        const int alive = aliveProtectedPlants();
        if (required > 0 && alive < required) {
            ++protectFailures_;
            status_ = "lost";
            event("protect_failed", Json{{"level", level_.id}, {"id", id}, {"type", plant->type},
                                         {"row", plant->row}, {"col", plant->col},
                                         {"mustProtect", mechanics_->protect.mustProtectCount},
                                         {"required", required}, {"alive", alive}});
            event("level_lost", Json{{"reason", "protected_plant_died"}, {"row", plant->row},
                                     {"x", centerOf(plant->col)}});
        }
    }
}

int World::requiredProtectedPlants() const {
    return mechanics_ != nullptr ? mechanics_->protect.requiredSurvivors() : 0;
}

int World::aliveProtectedPlants() const {
    int alive = 0;
    for (const auto& plant : plants_)
        if (plant.alive && plant.protectedPlant) ++alive;
    return alive;
}

int World::mowersLeft() const {
    int ready = 0;
    for (const auto& mower : mowers_) {
        if (mower.state == 0) ++ready;
    }
    return ready;
}

void World::damageZombie(EntityId id, double amount, bool ignoreArmor, bool countsAsKill) {
    auto* zombie = zombieById(id);
    if (!zombie || !zombie->alive) return;
    if (zombie->isBoss && zombie->bossStages > 0) {
        damageBoss(*zombie, amount, countsAsKill);
        return;
    }
    double rest = amount;
    // ---- S5.11: the layer walk -----------------------------------------------------------
    // Order is the sheet's `armorIds` order, never sorted. Per layer:
    //   invincible + passdamage -> immune, and the hit carries on to the next layer
    //   invincible              -> immune *and* blocking: nothing behind it takes damage
    //   pooled                  -> takes min(hp, rest); a break emits `armor_broken`, plus
    //                              `armor_dropped` when the sheet says droppable
    //   break + absorboverflow  -> the hit that breaks it loses whatever was left
    //   break + passdamage      -> the leftover continues to the next layer
    //   break, neither flag     -> the leftover skips the rest of the stack and reaches hp,
    //                              which is exactly what the old single pool did
    if (!ignoreArmor) {
        for (ArmorLayerState& layer : zombie->armorLayers) {
            if (!layer.poolsHitPoints()) {
                if (layer.invincible() && !layer.passDamage()) {
                    event("armor_blocked",
                          Json{{"id", id}, {"type", zombie->type}, {"armor", layer.armorId},
                               {"flags", layer.flagNames()}});
                    return; // 打不穿也传不过去：后面的层和本体都不掉血
                }
                continue; // invincible+passdamage, or a dangling id with no row behind it
            }
            if (layer.hp <= 0.0) continue; // broken earlier in the level
            const double absorbed = std::min(layer.hp, rest);
            layer.hp -= absorbed;
            rest -= absorbed;
            zombie->armorHp -= absorbed;
            if (layer.hp > 0.0) return; // the layer held; everything behind it is untouched
            event("armor_broken",
                  Json{{"id", id}, {"type", zombie->type}, {"armor", layer.armorId},
                       {"flags", layer.flagNames()}});
            if (layer.droppable())
                event("armor_dropped", Json{{"id", id}, {"armor", layer.armorId}, {"layer", layer.artLayer}});
            if (rest <= 0.0) return;
            if (layer.absorbOverflow()) {
                event("armor_absorbed", Json{{"id", id}, {"armor", layer.armorId}, {"lost", rest}});
                return;
            }
            if (!layer.passDamage()) break; // 溢出直达本体（S5.11 之前的单池行为）
        }
    }
    zombie->hp -= rest;
    if (zombie->hp > 0) return;
    zombie->hp = 0;
    zombie->alive = false;
    zombie->state = ZombieState::dying;
    zombie->deathTick = tick_;
    if (countsAsKill) ++killed_;
    event("zombie_died", Json{{"id", id}, {"type", zombie->type}, {"row", zombie->row}, {"x", zombie->x}});
}

void World::removePlant(EntityId id) {
    auto* plant = plantById(id);
    if (!plant || !plant->alive) return;
    plant->alive = false;
    event("plant_removed", Json{{"id", id}, {"type", plant->type}});
}

void World::removeZombie(EntityId id) {
    auto* zombie = zombieById(id);
    if (!zombie || !zombie->alive) return;
    zombie->alive = false;
    zombie->hp = 0;
    zombie->state = ZombieState::dying;
    zombie->deathTick = tick_;
    // A despawn is not a kill: `killed_` stays reserved for damage kills so the
    // clear-rate shown in reports cannot be inflated by cleanup.
    ++removed_;
    event("zombie_removed", Json{{"id", id}, {"type", zombie->type}});
}

void World::explode(int row, double x, double radius, double damage, double splash) {
    for (auto& zombie : zombies_) {
        if (!zombie.alive) continue;
        if (std::abs(zombie.row - row) > 1) continue;
        if (std::abs(zombie.x - x) > radius) continue;
        const double factor = zombie.row == row ? 1.0 : (splash > 0 ? splash : 0.0);
        if (factor <= 0) continue;
        damageZombie(zombie.id, damage * factor);
    }
    // S5.13: an explosion also clears grid items in its cell radius - that is the whole point of
    // "墓碑可被炸". Rows are handled like zombies: full damage on the blast row, `splash` on the
    // neighbours, and no damage when the caller passed no splash factor.
    for (auto& item : gridItems_) {
        if (!item.alive) continue;
        if (std::abs(item.row - row) > 1) continue;
        if (std::abs(centerOf(item.col) - x) > radius) continue;
        const double factor = item.row == row ? 1.0 : (splash > 0 ? splash : 0.0);
        if (factor <= 0) continue;
        damageGridItem(item, damage * factor);
    }
    event("explosion", Json{{"row", row}, {"x", x}, {"radius", radius}, {"damage", damage}});
}

EntityId World::spawnShot(int row, double x, double damage, const std::string& projectileType, int pierce,
                          double splash, double slow, EntityId owner) {
    if (shots_.size() >= static_cast<std::size_t>(tuning::kMaxShots)) return 0;
    ShotEntity shot;
    shot.id = nextId_++;
    shot.row = row;
    shot.x = x;
    shot.damage = damage;
    shot.speed = tuning::kShotSpeedColsPerSec;
    shot.pierce = pierce;
    shot.splash = splash;
    shot.slow = slow;
    shot.owner = owner;
    shot.projectileType = projectileType;
    shot.speed = tuning::kShotSpeedColsPerSec;
    shot.hitRadius = tuning::kShotHitRadius;
    shot.splashRadius = tuning::kShotSplashRadiusCols;
    shot.landX = x;

    // S5.9: a shot id that the table knows overrides the two global constants. An unknown id keeps
    // them and says so once per spawn: silently firing a pea at the old speed hid the miss, and
    // throwing would turn a data gap into a crash.
    const ProjectileSpec* spec = projectiles_ ? projectiles_->find(projectileType) : nullptr;
    if (spec) {
        if (spec->speedCols > 0.0) shot.speed = spec->speedCols;
        if (spec->hitRadiusCols > 0.0) shot.hitRadius = spec->hitRadiusCols;
        shot.trajectory = spec->trajectory;
        shot.lobbed = spec->trajectory == Trajectory::arc || spec->trajectory == Trajectory::drop;
        if (shot.lobbed) shot.landX = x + std::max(0.0, shot.speed) * tuning::kLobFlightSeconds;
        if (spec->hasSplash) {
            if (shot.splash <= 0.0) shot.splash = 1.0; // "this shot splashes at all"
            shot.splashDamage = spec->splashDamage;
            if (spec->splashRadiusCells > 0.0) shot.splashRadius = spec->splashRadiusCells;
        }
        if (spec->hasPierce && spec->pierceHits > 0 && shot.pierce <= 0) shot.pierce = spec->pierceHits;
        if (shot.damage <= 0.0 && spec->hasDamage) shot.damage = spec->damage;
        // A pkg-specific copy exists but the sheet records only *which* keys differ, never their
        // values, so the canonical numbers are used and the substitution is named once per id.
        if (!spec->variantPkgs.empty() && notedProjectiles_.insert(spec->id).second) {
            event("projectile_variant_fallback",
                  Json{{"projectile", spec->id}, {"pkg", spec->pkg}, {"variants", spec->variantPkgs}});
        }
    } else if (projectiles_ && !projectileType.empty() && notedProjectiles_.insert(projectileType).second) {
        event("projectile_unknown", Json{{"projectile", projectileType}, {"row", row}, {"x", x}});
    }
    shots_.push_back(shot);
    // Presentation-only hook (T38 audio): the engine never plays sounds, but it must say when a
    // shot and a sun came into being, otherwise the audio layer can only guess from health deltas.
    // Events are not part of hash(), so adding them cannot move a single existing hash.
    event("shot_fired", Json{{"id", shot.id}, {"row", row}, {"x", x},
                             {"projectile", projectileType}, {"damage", shot.damage}});
    return shot.id;
}

EntityId World::spawnSun(double x, int row, int value) {
    if (suns_.size() >= static_cast<std::size_t>(tuning::kMaxSuns)) return 0;
    SunEntity sun;
    sun.id = nextId_++;
    sun.x = x;
    sun.y = row < 0 ? 0.0 : static_cast<double>(row) + 0.5;
    sun.row = row;
    sun.value = value;
    sun.expires = tick_ + static_cast<std::uint64_t>(tuning::kSunLifetimeTicks);
    suns_.push_back(sun);
    event("sun_spawned", Json{{"id", sun.id}, {"row", row}, {"x", x}, {"value", value}});
    return sun.id;
}

void World::event(const std::string& type, Json details) {
    events_.push_back(Json{{"tick", tick_}, {"type", type}, {"details", std::move(details)}});
}

void World::noteUnwiredPlant(const std::string& name) {
    // `tickPlants` calls this every frame for a family without an implementation.
    // Count the family once, otherwise 60 ticks == 60 "unwired plants" in reports.
    if (unwiredPlantNames_.insert(name).second) ++unwiredPlants_;
}

void World::noteUnwiredZombie(const std::string& name) {
    if (unwiredZombieNames_.insert(name).second) ++unwiredZombies_;
}

std::uint32_t World::randomBelow(std::uint32_t bound) {
    if (bound == 0) return 0;
    std::uniform_int_distribution<std::uint32_t> dist(0, bound - 1);
    return dist(rng_);
}

double World::randomRange(double low, double high) {
    if (high <= low) return low;
    std::uniform_real_distribution<double> dist(low, high);
    return dist(rng_);
}

const PlantDefinition* World::findPlant(const std::string& type) const {
    const auto it = catalog_.plants.find(type);
    return it == catalog_.plants.end() ? nullptr : &it->second;
}

const ZombieDefinition* World::findZombie(const std::string& type) const {
    const auto it = catalog_.zombies.find(type);
    return it == catalog_.zombies.end() ? nullptr : &it->second;
}

std::uint64_t World::cooldown(const std::string& type) const {
    const auto it = cooldowns_.find(type);
    return it == cooldowns_.end() ? 0 : it->second;
}

// ----------------------------------------------------------- snapshot/hash ---
std::uint64_t World::hash() const {
    std::uint64_t value = 1469598103934665603ULL;
    const auto mix = [&value](const std::string& text) {
        for (unsigned char byte : text) {
            value ^= byte;
            value *= 1099511628211ULL;
        }
    };
    std::ostringstream out;
    out << tick_ << '|' << status_ << '|' << sun_ << '|' << director_.spawnedWaves() << '|' << zombies_.size()
        << '|' << plants_.size() << '|' << shots_.size() << '|' << suns_.size() << '|' << nextId_ << '|'
        << spawned_ << '|' << killed_ << '|' << removed_ << '|' << quantize(skySunTimer_) << '|'
        << (firstSkySunSpawned_ ? 1 : 0) << '|';
    // Pending player cooldowns change what can happen next, so a hash that skipped
    // them would report "identical" for two worlds that diverge on the next click.
    for (const auto& [type, readyTick] : cooldowns_) out << 'C' << type << ',' << readyTick << ';';
    for (const auto& plant : plants_) {
        out << 'P' << plant.id << ',' << plant.row << ',' << plant.col << ',' << quantize(plant.hp) << ','
            << plant.type << ',' << quantize(plant.actionTimer) << ';';
        for (const auto& slot : plant.slots) out << 'p' << slot.kind << ',' << slot.remainingTicks << ';';
        // S5.7 state, but only while it is in play: appending `plantFoodTicks=0` to every plant
        // would move every recorded baseline hash for a difference that cannot exist.
        if (plant.plantFoodTicks > 0 || plant.plantFoodArmed) {
            out << 'f' << plant.plantFoodTicks << ',' << (plant.plantFoodArmed ? 1 : 0) << ';';
        }
    }
    // S5.13: grid items and the belt's hand decide what can be planted next, so both are state.
    // Appended only when they exist, which keeps every non-mechanics level byte-identical.
    for (const auto& item : gridItems_) {
        out << 'I' << item.id << ',' << item.row << ',' << item.col << ',' << item.type << ','
            << quantize(item.hp) << ';';
    }
    if (!conveyorCards_.empty()) {
        out << 'Y';
        for (const auto& card : conveyorCards_) out << card << ',';
        out << ';' << conveyorRng_;
    }
    // Fusion changes what stands on the lawn, so the count belongs in the hash; it is only
    // mixed in once something fused, which keeps pre-S5 baselines byte-identical.
    if (fusions_ > 0) out << 'G' << fusions_ << ';';
    for (const auto& zombie : zombies_) {
        out << 'Z' << zombie.id << ',' << zombie.row << ',' << quantize(zombie.x) << ',' << quantize(zombie.hp) << ','
            << quantize(zombie.armorHp) << ',' << static_cast<int>(zombie.state) << ','
            << quantize(zombie.slowUntilTick) << ',' << zombie.nextSpecialTick << ',' << zombie.target << ','
            << quantize(zombie.speed) << ',' << zombie.family << ',' << zombie.deathTick << ';';
        // Boss state is appended only for a staged boss, so a world without one hashes
        // exactly as it did before S5.8.
        if (zombie.isBoss && zombie.bossStages > 0) {
            out << 'B' << zombie.stageIndex << ',' << zombie.bossStages << ',' << quantize(zombie.bossHp) << ','
                << zombie.bossIdleTicks << ',' << zombie.bossStunTicks << ';';
        }
        // S5.11: per-layer hit points are state only once a zombie carries more than one layer
        // (kongfu_armor3's three cloths, mausoleum_drunk's five jars). A single layer is fully
        // described by `armorHp`, so single-layer zombies keep the pre-S5.11 hash byte for byte.
        if (zombie.armorLayers.size() > 1) {
            out << 'A';
            for (const ArmorLayerState& layer : zombie.armorLayers) out << quantize(layer.hp) << ',';
            out << ';';
        }
    }
    for (const auto& shot : shots_) {
        out << 'S' << shot.id << ',' << shot.row << ',' << quantize(shot.x) << ',' << quantize(shot.damage) << ','
            << quantize(shot.speed) << ',' << shot.pierce << ',' << quantize(shot.splash) << ','
            << quantize(shot.slow) << ',' << shot.owner << ';';
    }
    for (const auto& sun : suns_) {
        out << 'U' << sun.id << ',' << quantize(sun.x) << ',' << sun.row << ',' << sun.value << ',' << sun.expires
            << ';';
    }
    for (const auto& mower : mowers_) {
        out << 'M' << mower.row << ',' << quantize(mower.x) << ',' << mower.state << ';';
    }
    // The generator's state is the only record of future random draws; without it
    // two worlds that will pick different rows can hash the same.
    out << 'R' << rng_;
    mix(out.str());
    return value;
}

Snapshot World::snapshot() const {
    Snapshot snap;
    snap.level = level_.id;
    snap.status = status_;
    snap.tick = tick_;
    snap.paused = paused_;
    snap.sun = sun_;
    snap.wave = director_.spawnedWaves();
    snap.waves = director_.waveCount();
    snap.rows = rows_;
    snap.cols = cols_;
    snap.seed = seed_;
    snap.hash = hash();
    snap.plants.reserve(plants_.size());
    for (const auto& plant : plants_) {
        PlantView view{plant.id, plant.type, plant.family, plant.row, plant.col, plant.hp, plant.maxHp,
                       plant.born, 0};
        for (const auto& slot : plant.slots) view.busyTicks = std::max(view.busyTicks, slot.remainingTicks);
        snap.plants.push_back(view);
    }
    snap.zombies.reserve(zombies_.size());
    for (const auto& zombie : zombies_) {
        snap.zombies.push_back(ZombieView{zombie.id, zombie.type, zombie.className, zombie.family, zombie.row,
                                          zombie.x, zombie.hp, zombie.maxHp, zombie.armorHp,
                                          zombie.state == ZombieState::eating});
    }
    snap.shots.reserve(shots_.size());
    for (const auto& shot : shots_) {
        snap.shots.push_back(ShotView{shot.id, shot.row, shot.x, shot.damage, shot.projectileType});
    }
    snap.suns.reserve(suns_.size());
    for (const auto& sun : suns_) {
        snap.suns.push_back(SunView{sun.id, sun.x, sun.y, sun.row, sun.value, sun.expires});
    }
    snap.mowers.reserve(mowers_.size());
    for (const auto& mower : mowers_) snap.mowers.push_back(MowerView{mower.row, mower.x, mower.state});
    return snap;
}

} // namespace pvz::engine
