#pragma once

// Runtime view of the shipped property sheets, as produced by
// `tools/contentc/build_content.py`.
//
// The pack is a projection of `work/obb_packages/*.json`: it carries what the
// engine consumes and nothing else. The sheets stay authoritative, so a field
// that is absent here can still be read from them — never infer a default and
// never "fix" a value that looks wrong.

#include <array>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

namespace pvz::content {

enum class ActionKind { projectile, sun, explode, special, plantfood, manual, unknown };

constexpr std::array<ActionKind, 7> kActionKinds = {
    ActionKind::projectile, ActionKind::sun,  ActionKind::explode, ActionKind::special,
    ActionKind::plantfood,  ActionKind::manual, ActionKind::unknown};

std::string_view actionKindName(ActionKind kind);

/// Where a type's `Properties` reference ended up.
enum class PropsSource {
    /// No reference (or `RTID(0)`): the object has no property sheet.
    none,
    /// Resolved in one of the shipped sheets.
    staticSheet,
    /// The level supplies it, e.g. `CurrentLevel` spawn scripts.
    external,
    /// The shipped data dangles; the original game tolerates it.
    missing,
};

std::string_view propsSourceName(PropsSource source);

struct Rtid {
    std::string name;
    std::string sheet;  // empty for the aggregate sheet
    bool nothing = false;
};

struct Point {
    double x = 0.0;
    double y = 0.0;
};

struct Rect {
    double x = 0.0;
    double y = 0.0;
    double width = 0.0;
    double height = 0.0;
};

/// One entry of a plant's or zombie's `Actions` array.
///
/// Absent numbers stay `nullopt` instead of collapsing to 0: the sheets use
/// "missing" to mean "behave per class", and 0 as a real value (instant
/// cooldown). Every field name below mirrors the sheet key it came from.
struct Action {
    ActionKind kind = ActionKind::unknown;
    std::string rawType;  // the sheet's `Type`, kept verbatim
    std::optional<Rtid> projectile;
    std::string trigger;   // `TriggerType`, `none` dropped
    std::string explode;   // `ExplodeType`, `none` dropped
    std::string launchSound;
    std::optional<double> damage;
    std::optional<double> splashDamage;
    std::optional<double> cooldownMin;
    std::optional<double> cooldownMax;
    std::optional<double> initialMin;
    std::optional<double> initialMax;
    std::optional<double> explodeRadius;
    std::optional<double> chillDuration;
    std::optional<double> freezeDuration;
    std::optional<double> stunDuration;
    std::optional<double> pushback;
    std::optional<double> needEating;
    std::optional<bool> burns;
    std::optional<bool> dieAfterExplode;
    std::optional<bool> secondary;
    std::optional<Point> spawnOffset;
    std::optional<Rect> triggerRect;
};

/// A zombie behaviour-script reference (`Actions: ["RTID(X@ZombieActions)"]`).
struct ActionRef {
    std::string name;
    std::string sheet;
    bool resolved = false;
};

struct PlantType {
    std::string id;
    std::string framework;
    Rtid properties;
    PropsSource propsSource = PropsSource::none;
    std::string popAnim;
    std::string animRig;
    std::string homeWorld;
    int integerId = 0;
    std::vector<std::string> families;
    bool sunProducer = false;
    std::string almanacBackdrop;
    std::vector<std::string> resourceGroups;

    std::optional<double> cost;
    std::optional<double> beghouledCost;
    std::optional<double> hitpoints;
    std::optional<double> packetCooldown;
    std::optional<double> startingCooldown;
    std::optional<double> plantFoodDuration;
    std::optional<double> plantFoodPlayCount;
    std::string gridType;
    std::string height;

    std::vector<Action> actions;
};

struct ZombieType {
    std::string id;
    std::string className;
    Rtid properties;
    PropsSource propsSource = PropsSource::none;
    std::string popAnim;
    std::string animRig;
    std::string homeWorld;
    int integerId = 0;
    bool isBasic = false;
    std::vector<std::string> resourceGroups;

    std::optional<double> hitpoints;
    std::optional<double> speed;
    std::optional<double> speedVariance;
    std::optional<double> eatDps;
    std::optional<double> weight;
    std::optional<double> wavePointCost;
    std::optional<double> cost;
    std::optional<Rect> hitRect;
    std::optional<Rect> attackRect;
    std::optional<Point> artCenter;
    std::optional<Point> shadowOffset;

    std::vector<Action> actions;
    std::vector<ActionRef> actionRefs;
};

struct ContentPack {
    int format = 0;
    std::string generated;
    std::vector<PlantType> plants;
    std::vector<ZombieType> zombies;

    /// Ids that appear more than once in the shipped tables. The game keys
    /// some lookups on class as well as name (two `heavy_shield` entries share
    /// one IntegerID), so duplicates are reported instead of collapsed.
    std::vector<std::string> plantDuplicates;
    std::vector<std::string> zombieDuplicates;

    /// Filled by `index()`. Pointers stay valid while the pack is alive.
    /// The first record wins when an id repeats.
    const PlantType* findPlant(std::string_view id) const;
    const ZombieType* findZombie(std::string_view id) const;

    void index();

   private:
    std::unordered_map<std::string, std::size_t> plantIndex_;
    std::unordered_map<std::string, std::size_t> zombieIndex_;
    bool indexed_ = false;
};

}  // namespace pvz::content
