#include "registry.hpp"
#include "content/model.hpp"
#include "tuning.hpp"
#include "world.hpp"
#include <array>
#include <cmath>
#include <string>
#include <unordered_map>
#include <vector>

namespace pvz::engine {
namespace {

constexpr std::uint64_t ticksOf(double seconds) {
    return static_cast<std::uint64_t>(seconds / tuning::kStepSeconds + 0.5);
}

// ---------------------------------------------------------------- number resolution
// Families used to hold bare numbers. S3.4a makes every one of them resolve in a single
// fixed order - the plant's own pack `Actions` slot first, then the content JSON field,
// then the constant below. A constant is only the last resort and is tagged
// `// fallback: tuning constant, no pack evidence`; the constant name at a call site
// means exactly that. Where a pack slot exists but carries no number for the family the
// pack still wins the *shape* (e.g. the trigger window) and the number comes from content.
//
// All of the declarations in this block are fallbacks: tuning constants, no pack evidence.
// Art-space pixels per board column. Measured, not guessed: pkg_2073 ArtCenter is (99,115)/(99,116)
// across 374 samples, i.e. 100x116 px per cell, and the shipped kShotStartOffsetCols=0.35 equals
// SpawnOffset.x=35 / 100. The old 60.0 put SpawnOffset.x and rect triggers in a 1.667x-wrong space.
constexpr double kPixelsPerColumn = 100.0;
constexpr double kShootInterval = 1.4;     // fallback: tuning constant, no pack evidence
constexpr double kShotDamage = 20.0;       // fallback: tuning constant, no pack evidence
constexpr double kLobInterval = 2.0;       // fallback: tuning constant, no pack evidence
constexpr double kLobDamage = 40.0;        // fallback: tuning constant, no pack evidence
constexpr double kLobSplash = 0.5;         // fallback: tuning constant, no pack evidence
constexpr double kProduceInterval = 24.0;  // fallback: tuning constant, no pack evidence
constexpr double kSunValue = 25.0;         // fallback: tuning constant, no pack evidence
constexpr double kInstantDelay = 1.0;      // fallback: tuning constant, no pack evidence
constexpr double kInstantDamage = 1800.0;  // fallback: tuning constant, no pack evidence
constexpr double kInstantRadius = 1.5;     // fallback: tuning constant, no pack evidence
constexpr double kInstantSplash = 0.5;     // fallback: tuning constant, no pack evidence
constexpr double kMineArm = 14.0;          // fallback: tuning constant, no pack evidence
constexpr double kMineDamage = 1800.0;     // fallback: tuning constant, no pack evidence
constexpr double kMineRadius = 1.0;        // fallback: tuning constant, no pack evidence
constexpr double kMineHalfWidth = 0.55;    // fallback: tuning constant, no pack evidence
constexpr double kChewCooldown = 40.0;     // fallback: tuning constant, no pack evidence
constexpr double kChompDamage = 1800.0;    // fallback: tuning constant, no pack evidence
constexpr double kChompReach = 1.0;        // fallback: tuning constant, no pack evidence
constexpr double kFumeInterval = 1.5;      // fallback: tuning constant, no pack evidence
constexpr double kFumeDamage = 20.0;       // fallback: tuning constant, no pack evidence
constexpr double kFumeReach = 4.0;         // fallback: tuning constant, no pack evidence
constexpr double kBoomerangInterval = 3.0; // fallback: tuning constant, no pack evidence
constexpr double kBoomerangDamage = 20.0;  // fallback: tuning constant, no pack evidence
constexpr double kBoomerangReach = 4.0;    // fallback: tuning constant, no pack evidence
constexpr double kSpikeDamage = 20.0;      // fallback: tuning constant, no pack evidence
constexpr double kSpikeCadence = 0.5;      // fallback: tuning constant, no pack evidence
constexpr double kSpikeHalfWidth = 0.55;   // fallback: tuning constant, no pack evidence

double param(const PlantEntity& plant, const Catalog& catalog, const char* key, double fallback) {
    const auto* def = catalog.plants.find(plant.type) != catalog.plants.end() ? &catalog.plants.at(plant.type)
                                                                            : nullptr;
    if (!def) return fallback;
    if (def->raw.contains(key) && def->raw.at(key).is_number()) return def->raw.at(key).get<double>();
    return fallback;
}

PlantEntity* own(World& world, EntityId id) {
    auto* p = world.plantById(id);
    return (p && p->alive) ? p : nullptr;
}

const PlantDefinition* defOf(const Catalog& catalog, const std::string& type) {
    const auto it = catalog.plants.find(type);
    return it == catalog.plants.end() ? nullptr : &it->second;
}

/// The pack entry for a content plant id. `plant.properties` in the pack is only the sheet
/// pointer, so all numbers below come from `actions` and the content JSON.
const content::PlantType* packPlantOf(const Catalog& catalog, const std::string& type) {
    if (!catalog.rules) return nullptr;
    return catalog.rules->findPlant(type);
}

const content::Action* firstOf(const content::PlantType* type, content::ActionKind kind) {
    if (!type) return nullptr;
    for (const auto& action : type->actions) {
        if (action.kind == kind) return &action;
    }
    return nullptr;
}

/// The slot that drives a family: the plant's own action Type when it declares one, else
/// the `special` slot that routes it into this family (action_runner.cpp).
const content::Action* driverAction(const Catalog& catalog, const PlantEntity& plant, content::ActionKind natural) {
    const auto* type = packPlantOf(catalog, plant.type);
    if (!type) return nullptr;
    if (const auto* action = firstOf(type, natural)) return action;
    return firstOf(type, content::ActionKind::special);
}

/// True when the plant's own `Actions` pace the family: the slot executor calls the family
/// once per firing, so a family that adds a second timer would halve the real cadence.
/// Only `spike` acts on this - the rest are never reached per-firing with slots present.
bool slotPaced(const Catalog& catalog, const std::string& type) {
    const auto* packed = packPlantOf(catalog, type);
    return packed != nullptr && !packed->actions.empty();
}

/// pack `Damage` > content `damage` > fallback. An absent `Damage`, and a literal 0, both
/// mean "this action deals no direct damage" (chomper, iceburg): the harm is scripted, so
/// neither may override the family's number.
double damageOf(const Catalog& catalog, const PlantEntity& plant, const content::Action* action, double fallback) {
    if (action && action->damage && *action->damage > 0) return *action->damage;
    if (const auto* def = defOf(catalog, plant.type); def && def->damage > 0) return def->damage;
    return fallback;
}

/// pack `CooldownTimeMin/Max` > content field (`contentKey` or `interval`) > fallback.
/// The kernel samples a cooldown range at its midpoint so runs stay deterministic.
double cadenceOf(const Catalog& catalog, const PlantEntity& plant, const content::Action* action, const char* contentKey,
                 double fallback) {
    if (action && action->cooldownMin && *action->cooldownMin > 0) {
        const double low = *action->cooldownMin;
        const double high = action->cooldownMax && *action->cooldownMax > low ? *action->cooldownMax : low;
        return (low + high) / 2.0;
    }
    if (const auto* def = defOf(catalog, plant.type)) {
        if (contentKey && def->raw.contains(contentKey) && def->raw.at(contentKey).is_number()) {
            const double value = def->raw.at(contentKey).get<double>();
            if (value > 0) return value;
        }
        if (def->interval > 0) return def->interval;
    }
    return fallback;
}

/// `RectTriggerRange` converted to engine units (columns, rows). `rect` is authored in
/// pixels, `rect_grid` already in grid cells, so only the former is rescaled.
struct TriggerWindow {
    bool present = false;
    double x0 = 0.0;
    double x1 = 0.0;
    double y0 = 0.0;
    double y1 = 0.0;
};

TriggerWindow windowOf(const content::Action* action) {
    TriggerWindow window;
    if (!action || !action->triggerRect) return window;
    const double scale = action->trigger == "rect_grid" ? 1.0 : 1.0 / kPixelsPerColumn;
    window.present = true;
    window.x0 = action->triggerRect->x * scale;
    window.x1 = window.x0 + action->triggerRect->width * scale;
    window.y0 = action->triggerRect->y * scale;
    window.y1 = window.y0 + action->triggerRect->height * scale;
    return window;
}

/// pack `ExplodeRadius` > the trigger window's own extent > fallback.
double radiusOf(const content::Action* action, const TriggerWindow& window, double fallback) {
    if (action && action->explodeRadius && *action->explodeRadius > 0) return *action->explodeRadius;
    if (window.present) {
        const double span = std::max(std::max(std::abs(window.x0), std::abs(window.x1)),
                                     std::max(std::abs(window.y0), std::abs(window.y1)));
        return std::max(0.5, span);
    }
    return fallback;
}

/// pack `SpawnOffset.x` (pixels) > fallback, in columns.
double spawnOffsetOf(const content::Action* action, double fallback) {
    if (action && action->spawnOffset) return action->spawnOffset->x / kPixelsPerColumn;
    return fallback;
}

// ---------------------------------------------------------------- plant families
void familyWall(World& world, EntityId id) {
    if (!own(world, id)) return; // a wall does nothing but take damage
}

void familyShoot(World& world, EntityId id) {
    auto* p = own(world, id);
    if (!p) return;
    const auto& catalog = world.catalog();
    const auto* def = defOf(catalog, p->type);
    const auto* action = driverAction(catalog, *p, content::ActionKind::projectile);
    const double interval = cadenceOf(catalog, *p, action, "interval", kShootInterval);
    p->actionTimer += tuning::kStepSeconds;
    if (p->actionTimer + 1e-9 < interval) return;
    const double centre = world.centerOf(p->col);
    if (!world.firstZombieAhead(p->row, centre, static_cast<double>(world.cols()))) return;
    p->actionTimer = 0;
    // S5.9: prefer the sheet's projectile id (what the shot table is keyed by); the plant id is the
    // old fallback and simply resolves to the global constants.
    const std::string type = action && action->projectile ? action->projectile->name : (def ? def->id : p->type);
    world.spawnShot(p->row, centre + spawnOffsetOf(action, tuning::kShotStartOffsetCols),
                    damageOf(catalog, *p, action, kShotDamage), type,
                    static_cast<int>(param(*p, catalog, "pierce", 0)), def ? def->raw.value("splash", 0.0) : 0.0,
                    def ? def->raw.value("slow", 0.0) : 0.0, p->id);
}

void familyLob(World& world, EntityId id) {
    auto* p = own(world, id);
    if (!p) return;
    const auto& catalog = world.catalog();
    const auto* def = defOf(catalog, p->type);
    const auto* action = driverAction(catalog, *p, content::ActionKind::projectile);
    const double interval = cadenceOf(catalog, *p, action, "interval", kLobInterval);
    p->actionTimer += tuning::kStepSeconds;
    if (p->actionTimer + 1e-9 < interval) return;
    const double centre = world.centerOf(p->col);
    if (!world.firstZombieAhead(p->row, centre, static_cast<double>(world.cols()))) return;
    p->actionTimer = 0;
    // S5.9: prefer the sheet's projectile id (what the shot table is keyed by); the plant id is the
    // old fallback and simply resolves to the global constants.
    const std::string type = action && action->projectile ? action->projectile->name : (def ? def->id : p->type);
    world.spawnShot(p->row, centre + spawnOffsetOf(action, tuning::kShotStartOffsetCols),
                    damageOf(catalog, *p, action, kLobDamage), type, 0,
                    def ? def->raw.value("splash", kLobSplash) : kLobSplash, 0, p->id);
}

void familyProduce(World& world, EntityId id) {
    auto* p = own(world, id);
    if (!p) return;
    const auto& catalog = world.catalog();
    const auto* action = driverAction(catalog, *p, content::ActionKind::sun);
    // A `special`-only producer (jasmine) has no sun slot, so the family keeps its own timer;
    // the pack cadence only exists on a `sun` action and then it is the truth.
    const double interval = cadenceOf(catalog, *p, action, "sun_interval", kProduceInterval);
    p->actionTimer += tuning::kStepSeconds;
    if (p->actionTimer + 1e-9 < interval) return;
    p->actionTimer = 0;
    world.spawnSun(world.centerOf(p->col), p->row, static_cast<int>(param(*p, catalog, "sun_value", kSunValue)));
}

void familyInstant(World& world, EntityId id) {
    auto* p = own(world, id);
    if (!p) return;
    const auto& catalog = world.catalog();
    const auto* def = defOf(catalog, p->type);
    const auto* action = driverAction(catalog, *p, content::ActionKind::explode);
    const double delay = param(*p, catalog, "delay", kInstantDelay);
    p->actionTimer += tuning::kStepSeconds;
    if (p->actionTimer + 1e-9 < delay) return;
    const TriggerWindow window = windowOf(action);
    world.explode(p->row, world.centerOf(p->col), radiusOf(action, window, kInstantRadius),
                  damageOf(catalog, *p, action, kInstantDamage),
                  def ? def->raw.value("splash", kInstantSplash) : kInstantSplash);
    world.removePlant(id);
}

void familyMine(World& world, EntityId id) {
    auto* p = own(world, id);
    if (!p) return;
    const auto& catalog = world.catalog();
    const auto* action = driverAction(catalog, *p, content::ActionKind::explode);
    const double arm = param(*p, catalog, "delay", kMineArm);
    p->actionTimer += tuning::kStepSeconds;
    if (p->actionTimer + 1e-9 < arm) return;
    const TriggerWindow window = windowOf(action);
    const double centre = world.centerOf(p->col);
    // `RectTriggerRange` is the arming window: potatomine's -30..35px becomes [-0.5, 0.583]
    // columns, i.e. it steps off on the zombie that has actually reached its tile.
    const double x0 = window.present ? window.x0 : -kMineHalfWidth;
    const double x1 = window.present ? window.x1 : kMineHalfWidth;
    bool armed = false;
    for (const auto& z : world.zombies()) {
        if (!z.alive || z.row != p->row) continue;
        const double dx = z.x - centre;
        if (dx < x0 || dx > x1) continue;
        armed = true;
        break;
    }
    if (!armed) return;
    world.explode(p->row, centre, radiusOf(action, window, kMineRadius), damageOf(catalog, *p, action, kMineDamage), 0);
    world.removePlant(id);
}

void familyChomp(World& world, EntityId id) {
    auto* p = own(world, id);
    if (!p) return;
    const auto& catalog = world.catalog();
    const auto* action = driverAction(catalog, *p, content::ActionKind::projectile);
    // The pack's 1.75-2s on chomper is that action's own repeat, not the swallow: the chew
    // stays the content interval (17s) and only the reach comes from the pack window
    // (110px wide trigger -> 1.42 columns, up from the old bare 1.0).
    const double chew = cadenceOf(catalog, *p, nullptr, "interval", kChewCooldown);
    if (p->actionTimer > 0) {
        p->actionTimer = std::max(0.0, p->actionTimer - tuning::kStepSeconds);
        return;
    }
    const TriggerWindow window = windowOf(action);
    const double reach = window.present ? std::max(kChompReach, window.x1) : kChompReach;
    if (auto* z = world.firstZombieAhead(p->row, world.centerOf(p->col), reach)) {
        world.damageZombie(z->id, damageOf(catalog, *p, action, kChompDamage));
        p->actionTimer = chew; // chewing cooldown
    }
}

void familyFume(World& world, EntityId id) {
    auto* p = own(world, id);
    if (!p) return;
    const auto& catalog = world.catalog();
    const auto* action = driverAction(catalog, *p, content::ActionKind::projectile);
    const double interval = cadenceOf(catalog, *p, action, "interval", kFumeInterval);
    p->actionTimer += tuning::kStepSeconds;
    if (p->actionTimer + 1e-9 < interval) return;
    p->actionTimer = 0;
    // The pack's Damage (20) is the real fume number; content's 40 is the sheet author's
    // shorthand and must not win. `rect_grid` 5x1 makes the fume reach five columns.
    const double damage = damageOf(catalog, *p, action, kFumeDamage);
    const TriggerWindow window = windowOf(action);
    const double reach = window.present ? std::max(kFumeReach, window.x1) : kFumeReach;
    const double from = world.centerOf(p->col);
    std::vector<EntityId> hits;
    for (const auto& z : world.zombies()) {
        if (!z.alive || z.row != p->row) continue;
        if (z.x + 0.5 < from || z.x > from + reach) continue;
        hits.push_back(z.id);
    }
    for (const auto victim : hits) world.damageZombie(victim, damage);
}

void familyBoomerang(World& world, EntityId id) {
    auto* p = own(world, id);
    if (!p) return;
    const auto& catalog = world.catalog();
    const auto* action = driverAction(catalog, *p, content::ActionKind::projectile);
    // bloomerang's four projectile slots repeat at 1.35-1.5s; content's 2.7s is half that.
    const double interval = cadenceOf(catalog, *p, action, "interval", kBoomerangInterval);
    p->actionTimer += tuning::kStepSeconds;
    if (p->actionTimer + 1e-9 < interval) return;
    p->actionTimer = 0;
    const double centre = world.centerOf(p->col);
    const double damage = damageOf(catalog, *p, action, kBoomerangDamage);
    const TriggerWindow window = windowOf(action);
    const double reach = window.present ? std::max(kBoomerangReach, window.x1) : kBoomerangReach;
    std::vector<EntityId> hits;
    for (const auto& z : world.zombies()) {
        if (!z.alive || z.row != p->row) continue;
        if (std::abs(z.x - centre) > reach) continue;
        hits.push_back(z.id);
    }
    for (const auto victim : hits) world.damageZombie(victim, damage);
}

void familySupport(World& world, EntityId id) {
    if (!own(world, id)) return; // S3 gives the ten support plants their real auras
}

// Ground spikes hurt whatever walks over the tile and are never eaten.
void familySpike(World& world, EntityId id) {
    auto* p = own(world, id);
    if (!p) return;
    const auto& catalog = world.catalog();
    const auto* action = driverAction(catalog, *p, content::ActionKind::special);
    const double damage = damageOf(catalog, *p, action, kSpikeDamage);
    const double cadence = cadenceOf(catalog, *p, action, "interval", kSpikeCadence);
    // A plant whose `special` slot paces this family (spikeweed 10 damage @0.5s) has the
    // pack's cadence already applied by the slot executor, so the Damage lands once per
    // firing. An unscheduled spike keeps a per-tick rate of damage/cooldown instead.
    const double perCall = slotPaced(catalog, p->type) ? damage : damage * tuning::kStepSeconds / cadence;
    const TriggerWindow window = windowOf(action);
    const double halfWidth = window.present ? std::max(std::abs(window.x0), std::abs(window.x1)) : kSpikeHalfWidth;
    const double centre = world.centerOf(p->col);
    std::vector<EntityId> hits;
    for (const auto& z : world.mutableZombies()) {
        if (!z.alive || z.row != p->row) continue;
        if (std::abs(z.x - centre) <= halfWidth) hits.push_back(z.id);
    }
    for (const auto victim : hits) world.damageZombie(victim, perCall);
}

// --------------------------------------------------------------- zombie families
ZombieEntity* ownZombie(World& world, EntityId id) {
    auto* z = world.zombieById(id);
    return (z && z->alive) ? z : nullptr;
}

void zombieWalk(World&, EntityId) { /* locomotion and eating live in World */ }

void zombieJump(World&, EntityId) {
    // Vaulting moved into World::tryVault and now runs *before* the eat scan in
    // tickZombies. Doing it here was structurally too late: the loop had already
    // handed this zombie a plant to chew, so a pole vaulter ate the wall-nut instead
    // of hopping it, and when it did hop the landing point sat inside its own reach
    // window and it hopped in place forever.
}

void zombieSteal(World& world, EntityId id) {
    auto* z = ownZombie(world, id);
    if (!z) return;
    if (world.tick() < z->nextSpecialTick) return;
    for (int col = 0; col < world.cols(); ++col) {
        auto* p = world.plantAt(z->row, col);
        if (!p || !p->alive) continue;
        if (std::abs(world.centerOf(col) - z->x) > 0.9) continue;
        world.event("zombie_steal", Json{{"id", id}, {"plant", p->type}, {"row", z->row}});
        world.removePlant(p->id);
        z->nextSpecialTick = world.tick() + ticksOf(2.0);
        return;
    }
}

void zombieSummon(World& world, EntityId id) {
    auto* z = ownZombie(world, id);
    if (!z) return;
    if (world.tick() < z->nextSpecialTick) return;
    z->nextSpecialTick = world.tick() + ticksOf(8.0);
    const std::string minion = world.catalog().zombies.count("basic") ? "basic" : z->type;
    // `spawnZombie` is called from inside `World::tickZombies`' range-for over
    // `zombies_`; the kernel queues the spawn instead of growing the vector under
    // the iterator (see World::pendingSpawns_).
    const int row = z->row;
    world.spawnZombie(minion, row);
    world.event("zombie_summon", Json{{"id", id}, {"minion", minion}, {"row", row}});
}

void zombieGargantuar(World& world, EntityId id) {
    auto* z = ownZombie(world, id);
    if (!z) return;
    if (world.tick() < z->nextSpecialTick) return;
    for (int col = 0; col < world.cols(); ++col) {
        auto* p = world.plantAt(z->row, col);
        if (!p || !p->alive) continue;
        if (std::abs(world.centerOf(col) - z->x) > 1.2) continue;
        world.event("zombie_smash", Json{{"id", id}, {"plant", p->type}, {"row", z->row}});
        world.damagePlant(p->id, 100000);
        z->nextSpecialTick = world.tick() + ticksOf(3.0);
        return;
    }
}

void zombieFly(World&, EntityId) { /* passes over plants; World skips eating for this family */ }

using PlantTable = std::unordered_map<std::string, PlantBehavior>;
using ZombieTable = std::unordered_map<std::string, ZombieBehavior>;

const PlantTable& plantTable() {
    static const PlantTable table = {
        {"shoot", &familyShoot},     {"lob", &familyLob},         {"produce", &familyProduce},
        {"wall", &familyWall},       {"instant", &familyInstant}, {"mine", &familyMine},
        {"chomp", &familyChomp},     {"fume", &familyFume},       {"boomerang", &familyBoomerang},
        {"support", &familySupport}, {"spike", &familySpike},
    };
    return table;
}

const ZombieTable& zombieTable() {
    static const ZombieTable table = {
        {"walk", &zombieWalk},       {"jump", &zombieJump},   {"steal", &zombieSteal},
        {"summon", &zombieSummon},   {"gargantuar", &zombieGargantuar}, {"fly", &zombieFly},
    };
    return table;
}

} // namespace

const Registry& Registry::shared() {
    static const Registry registry;
    return registry;
}

PlantBehavior Registry::plantBehavior(const std::string& family) const {
    const auto& table = plantTable();
    const auto it = table.find(family);
    return it == table.end() ? nullptr : it->second;
}

ZombieBehavior Registry::zombieBehavior(const std::string& family) const {
    const auto& table = zombieTable();
    const auto it = table.find(family);
    return it == table.end() ? nullptr : it->second;
}

const std::vector<std::string>& Registry::plantFamilies() {
    static const std::vector<std::string> names = {"shoot", "lob",   "produce",   "wall",      "instant",
                                                   "mine",  "chomp", "fume",      "boomerang", "support",
                                                   "spike"};
    return names;
}

const std::vector<std::string>& Registry::zombieFamilies() {
    static const std::vector<std::string> names = {"walk", "jump", "steal", "summon", "gargantuar", "fly"};
    return names;
}

PlantBehavior Registry::defaultPlant() { return &familyWall; }
ZombieBehavior Registry::defaultZombie() { return &zombieWalk; }

} // namespace pvz::engine
