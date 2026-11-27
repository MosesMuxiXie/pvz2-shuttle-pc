#include "action_runner.hpp"
#include "../content/model.hpp"
#include "registry.hpp"
#include "tuning.hpp"
#include "world.hpp"
#include <algorithm>
#include <cmath>

namespace pvz::engine {
namespace {
constexpr int kFallbackCooldownTicks = 60;

/// The sheets place things in pixels; one lawn cell is 60 px wide and 60 px tall.
// Art-space pixels per board column. Measured, not guessed: pkg_2073 ArtCenter is (99,115)/(99,116)
// across 374 samples, i.e. 100x116 px per cell, and the shipped kShotStartOffsetCols=0.35 equals
// SpawnOffset.x=35 / 100. The old 60.0 put SpawnOffset.x and rect triggers in a 1.667x-wrong space.
constexpr double kPixelsPerColumn = 100.0;

int ticksOf(double seconds) { return static_cast<int>(seconds / tuning::kStepSeconds + 0.5); }

/// The sheet action a slot was built from.
///
/// `World::plant` copies `PlantType::actions` in order, so slot `index` is action `index`;
/// it only keeps the fields `ActionSlot` can hold. Everything else the declaration carries
/// - `SpawnOffset`, the `RectTriggerRange` origin, `DieAfterExplode`, the high end of
/// `CooldownTimeMin/Max` - is read from the pack here instead of being guessed, and the
/// engine never invents a value the sheet leaves out.
const content::Action* packActionOf(const World& world, const PlantEntity& plant, std::size_t index) {
    if (!world.catalog().rules) return nullptr;
    const auto* type = world.catalog().rules->findPlant(plant.type);
    if (type == nullptr || index >= type->actions.size()) return nullptr;
    return &type->actions[index];
}

/// `RectTriggerRange` in engine units: columns to the right of the plant's centre, rows
/// below its row.
struct TriggerArea {
    bool active = false;
    double x0 = 0, x1 = 0;
    double y0 = 0, y1 = 0;
};

TriggerArea triggerAreaOf(const content::Action* action) {
    TriggerArea area;
    if (action == nullptr || !action->triggerRect) return area;
    // The two rect triggers do not share a unit: `rect` is in pixels (potatomine 65x60,
    // akees 800x50) while `rect_grid` is already in cells (akees 5x1). Dividing both by 60
    // would shrink every grid trigger fifteen-fold.
    const double scale = action->trigger == "rect_grid" ? 1.0 : (1.0 / kPixelsPerColumn);
    area.active = true;
    area.x0 = action->triggerRect->x * scale;
    area.x1 = area.x0 + action->triggerRect->width * scale;
    area.y0 = action->triggerRect->y * scale;
    area.y1 = area.y0 + action->triggerRect->height * scale;
    return area;
}

bool covers(const TriggerArea& area, double dx, double dy) {
    return dx >= area.x0 && dx <= area.x1 && dy >= area.y0 && dy <= area.y1;
}

/// Does `TriggerType` see a zombie this tick?
bool triggerSeesTarget(World& world, const PlantEntity& plant, const ActionSlot& slot,
                       const content::Action* action) {
    const double centre = world.centerOf(plant.col);
    const auto area = triggerAreaOf(action);
    if (area.active) {
        for (const auto& zombie : world.zombies()) {
            if (!zombie.alive) continue;
            if (covers(area, zombie.x - centre, static_cast<double>(zombie.row - plant.row))) return true;
        }
        return false;
    }
    if (slot.trigger == "column") {
        // `column` fires on whatever stands in the plant's own cell.
        for (const auto& zombie : world.zombies()) {
            if (!zombie.alive || zombie.row != plant.row) continue;
            if (std::abs(zombie.x - centre) <= 0.5) return true;
        }
        return false;
    }
    // `none`, `row` and `instant` keep the S2 rule - something worth shooting in this row -
    // and so do the sheet's bespoke triggers (`board`, `allfront`, `manual`), which need
    // targeting logic S3 does not have yet. None of them may make a plant fire blind.
    return world.firstZombieAhead(plant.row, centre, static_cast<double>(world.cols())) != nullptr;
}

/// `SpawnOffset.x` in columns. Absent SpawnOffset keeps S2's 0.35 column offset for shots
/// and puts sun at the plant's centre. `SpawnOffset.y` is not applied: `World::spawnSun`
/// takes a row, not a height, and a vertical nudge belongs to the view layer.
double spawnOffsetColumns(const content::Action* action, double fallback) {
    if (action == nullptr || !action->spawnOffset) return fallback;
    return action->spawnOffset->x / kPixelsPerColumn;
}

/// `CooldownTimeMin/Max`: a range the original picks from per cycle; the kernel is
/// deterministic, so it repeats at the midpoint (peashooter 1.35-1.5s -> 85 ticks). A sheet
/// interval of zero stays zero - that is how a one-shot explosion declares itself.
int repeatTicks(const content::Action* action, const ActionSlot& slot) {
    if (action != nullptr && action->cooldownMin) {
        const int low = ticksOf(*action->cooldownMin);
        const int high = action->cooldownMax ? ticksOf(*action->cooldownMax) : low;
        return (low + high) / 2;
    }
    if (slot.cooldownTicks > 0) return slot.cooldownTicks;
    return kFallbackCooldownTicks;
}

/// Ticks before the first cycle. `InitialMinCooldownTime` when the sheet has it; otherwise
/// the low end of the repeat range, which is what the original does and why S2's tick-1
/// sun was 32 seconds early for sunflower.
int firstTicks(const content::Action* action, const ActionSlot& slot) {
    if (action != nullptr && action->initialMin) {
        const int low = ticksOf(*action->initialMin);
        const int high = action->initialMax ? ticksOf(*action->initialMax) : low;
        return std::max(0, (low + high) / 2);
    }
    if (action != nullptr && action->cooldownMin) return std::max(0, ticksOf(*action->cooldownMin));
    return std::max(0, slot.initialTicks);
}

/// Pack `Damage`, else the content value, else S2's 20. A fed plant hits for +100%, which is
/// the half of plant food that has no action to play.
double packDamage(World& world, const PlantEntity& plant, const ActionSlot& slot) {
    double damage = 20;
    if (slot.damage > 0) {
        damage = slot.damage;
    } else if (const auto* def = world.findPlant(plant.type); def != nullptr && def->damage > 0) {
        damage = def->damage;
    }
    // B1 (T90): the sheet's per-level damage, applied to the number the pack just gave us. The
    // identity guard inside `levelDamage` rejects everything at level 1, so this line cannot move a
    // default run; it is also idempotent, which is why it is safe to reach it from both the shot and
    // the explode path below.
    damage = world.levelDamage(plant.type, damage);
    if (plant.plantFoodTicks > 0) damage *= tuning::kPlantFoodDamageScale;
    return damage;
}

/// Sun value comes from content (`sun_value`), never from the engine.
int sunValue(const World& world, const PlantEntity& plant) {
    const auto* def = world.findPlant(plant.type);
    if (def != nullptr) {
        const auto it = def->raw.find("sun_value");
        if (it != def->raw.end() && it->is_number()) return static_cast<int>(it->get<double>());
    }
    return tuning::kSkySunValue;
}

/// `ExplodeRadius`, else the radius that spans the rect that armed the blast, else one cell.
double explodeRadiusOf(const ActionSlot& slot, const content::Action* action, const TriggerArea& area) {
    if (action != nullptr && action->explodeRadius && *action->explodeRadius > 0) return *action->explodeRadius;
    if (slot.radius > 0) return slot.radius;
    if (area.active) {
        // potatomine has no ExplodeRadius: the trigger footprint is the blast, and only the
        // horizontal reach is expressible because `World::explode` handles neighbours through
        // `SplashDamage`, not through a vertical radius.
        return std::max(0.5, std::max(std::abs(area.x0), std::abs(area.x1)));
    }
    return 1.0;
}

/// `DieAfterExplode`. When the sheet leaves it out, an explosion that cannot repeat is a
/// one-shot (a mine arms, fires and is gone) while a repeating one is a sustained emanation
/// and the plant stays.
bool selfDestructs(const content::Action* action, int repeat) {
    if (action != nullptr && action->dieAfterExplode) return *action->dieAfterExplode;
    return repeat <= 0;
}

/// The registry families exist for plants whose sheet declares no actions. A `special`
/// marker next to a declared action of the same class would otherwise run the behaviour a
/// second time - a sunflower would drop two suns per cycle, a peashooter two peas.
bool familyCoveredBySheet(const PlantEntity& plant, const std::string& family) {
    for (const auto& slot : plant.slots) {
        if (family == "produce" && slot.kind == "sun") return true;
        if (slot.kind == "projectile" && (family == "shoot" || family == "lob" || family == "fume" ||
                                          family == "boomerang" || family == "spike")) {
            return true;
        }
        if (slot.kind == "explode" && (family == "instant" || family == "mine")) return true;
    }
    return false;
}

bool idlesOnCooldown(const std::string& kind) {
    // Recognised by the parser but not driven by a sheet cycle: `plantfood` waits for a feed,
    // `manual` needs targeting the engine does not have, `unknown` is an action Type with no
    // behaviour at all. All three still hold a cooldown so they are not re-checked every frame.
    return kind == "plantfood" || kind == "manual" || kind == "unknown";
}
} // namespace

void runActionSlots(World& world, PlantEntity& plant) {
    if (plant.slots.empty() || !plant.alive) return;
    const double centre = world.centerOf(plant.col);
    for (std::size_t index = 0; index < plant.slots.size(); ++index) {
        auto& slot = plant.slots[index];
        const content::Action* action = packActionOf(world, plant, index);
        if (!slot.seeded) {
            // The sheet, not `World::plant`, decides where a cycle starts; the seed lands on
            // the plant's first tick so a first sun arrives exactly `InitialMinCooldownTime`
            // after planting.
            slot.seeded = true;
            slot.initialTicks = firstTicks(action, slot);
            slot.cooldownTicks = repeatTicks(action, slot);
            slot.remainingTicks = slot.initialTicks;
        }
        if (slot.remainingTicks > 0) {
            --slot.remainingTicks;
            if (slot.remainingTicks > 0) continue;
        }
        bool fired = false;
        if (slot.kind == "projectile") {
            if (triggerSeesTarget(world, plant, slot, action)) {
                const double offset =
                    action && action->spawnOffset ? spawnOffsetColumns(action, 0.0) : tuning::kShotStartOffsetCols;
                world.spawnShot(plant.row, centre + offset, packDamage(world, plant, slot), slot.projectileType,
                                slot.pierce, slot.splash, slot.slow, plant.id);
                fired = true;
            }
        } else if (slot.kind == "sun") {
            world.spawnSun(centre + spawnOffsetColumns(action, 0.0), plant.row, sunValue(world, plant));
            fired = true;
        } else if (slot.kind == "explode") {
            const auto area = triggerAreaOf(action);
            if (!area.active || triggerSeesTarget(world, plant, slot, action)) {
                world.explode(plant.row, centre, explodeRadiusOf(slot, action, area), packDamage(world, plant, slot),
                              slot.splash);
                fired = true;
                if (selfDestructs(action, slot.cooldownTicks)) {
                    world.removePlant(plant.id);
                    return;
                }
            }
        } else if (slot.kind == "special") {
            if (!familyCoveredBySheet(plant, plant.family)) {
                if (const auto* behavior = Registry::shared().plantBehavior(plant.family)) {
                    (*behavior)(world, plant.id);
                    if (!plant.alive) return; // the behaviour removed the plant
                    fired = true;
                }
            }
        } else if (slot.kind == "plantfood") {
            // Feeding is the only thing that plays a plant-food action: it is not a cycle the
            // plant runs on its own. `World::feed` arms the slot *and* drops its countdown, so
            // reaching this branch with the flag set means a feed is waiting to be played.
            if (plant.plantFoodArmed) {
                plant.plantFoodArmed = false;
                const std::string projectile = !slot.projectileType.empty()
                                                   ? slot.projectileType
                                                   : (action && action->projectile ? action->projectile->name
                                                                                   : std::string{});
                if (!projectile.empty()) {
                    const double offset = action && action->spawnOffset ? spawnOffsetColumns(action, 0.0)
                                                                       : tuning::kShotStartOffsetCols;
                    world.spawnShot(plant.row, centre + offset, packDamage(world, plant, slot), projectile,
                                    slot.pierce, slot.splash, slot.slow, plant.id);
                    fired = true;
                }
            }
        } else {
            // `plantfood` and `manual` are recognised by the parser and wait for S4; anything
            // else is an action Type the engine has no behaviour for. Either way it is data,
            // never a contract: report the unknown ones once per slot and never throw.
            if (slot.kind == "unknown" && !slot.unknownReported) {
                slot.unknownReported = true;
                world.event("action_unknown",
                            Json{{"plant", plant.type}, {"type", slot.rawType}, {"kind", slot.kind}});
            }
        }
        // A wait of N ticks fires on the tick its own countdown reaches zero, so re-arming
        // with `cooldownTicks` puts the next cycle exactly that far away. Zero-length intervals
        // (a one-shot) still wait one tick, which is what keeps a bare `explode` from firing
        // twice in the same frame. A fed plant cycles at +100% speed.
        const int period = plant.plantFoodTicks > 0
                               ? std::max(1, static_cast<int>(static_cast<double>(slot.cooldownTicks) /
                                                             tuning::kPlantFoodRateScale))
                               : slot.cooldownTicks;
        slot.remainingTicks = (fired || idlesOnCooldown(slot.kind)) ? std::max(1, period) : 1;
    }
}

} // namespace pvz::engine
