// S5.11 armor wiring: the pack's armor sheet, read once from generated/armors_from_pack.json.
//
// Before this the engine read only `content/zombies.json`'s `armor[].hp` and summed it into a
// single `armorHp` pool. That loses the two things the original keys behaviour on: the layer
// order (`ZombieArmorProps`) and the per-layer `ArmorFlags`. This header keeps both, and stays
// SDL-free so the audit build, the engine and the view read the table the same way.
//
// Three id spaces meet here and they are not the same:
//   * `armors[]` rows are keyed by armor id (`ConeDefault`, `NunchakuDefault`),
//   * `zombies[]` rows are keyed by **pack** zombie id (`lostcity_excavator`, `af_bald`),
//   * `contentComparison.rows[]` bridges a **content** zombie id (`conehead`, `buckethead`).
// Only 10 of the 55 content zombies have a bridge row (`counts.contentBridged`), and their hp
// agrees with the sheet exactly (`counts.contentHpDifferences == 0`), so the bridge only adds
// flags and order; the other 45 keep the content-only reading (one damageable layer each).
#pragma once

#include <cstddef>
#include <filesystem>
#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace pvz::engine {

/// `ArmorFlags` bits. The sheet writes flags as strings; `armorFlagBits` maps them and
/// `armorFlagNames` renders them back for events and the report. Unknown strings are kept in
/// `ArmorSpec::flags` but map to no bit, so a data change shows up as an unmapped name instead
/// of a crash. Today the sheet uses exactly these nine (`counts.flagCounts`).
enum ArmorFlag : unsigned {
    kArmorNoFlags = 0u,
    kArmorDamageable = 1u << 0,     ///< 72 rows: takes hit points from the pool
    kArmorInvincible = 1u << 1,     ///< 16 rows: never enters the pool, so it can never break
    kArmorPassDamage = 1u << 2,     ///< 33 rows: leftover damage continues to the next layer
    kArmorDroppable = 1u << 3,      ///< 62 rows: drops a prop when it breaks
    kArmorAbsorbOverflow = 1u << 4, ///< 1 row: the hit that breaks it loses its overflow
    kArmorMetallic = 1u << 5,       ///< 20 rows: metal, the view draws a grey block
    kArmorHelm = 1u << 6,           ///< 49 rows: sits on the head
    kArmorBody = 1u << 7,           ///< 20 rows: covers the body
    kArmorVisibleOnDestroy = 1u << 8, ///< 4 rows: stays visible once broken
};

unsigned armorFlagBit(std::string_view name);
std::string armorFlagNames(unsigned bits);

/// One row of `armors[]`.
struct ArmorSpec {
    std::string id;
    std::string armorType;
    std::string objclass;
    std::vector<std::string> flags; ///< as stored, sheet order
    unsigned flagBits = kArmorNoFlags;
    double hitpoints = 0.0; ///< <- BaseHealth
    /// `BaseHealth` is an int on four rows and holds the int sentinel there
    /// (`counts.hitpointsSentinels == 4`), which means "no practical limit", not 2^31 hit points.
    bool hitpointsSentinel = false;
    std::string armorLayer;          ///< <- ArmorLayers[0]
    std::vector<std::string> layers; ///< <- ArmorLayers
    std::vector<double> layerHealth; ///< <- ArmorLayerHealth
    std::string fireLayer;
    std::string className;

    bool damageable() const { return (flagBits & kArmorDamageable) != 0; }
    bool invincible() const { return (flagBits & kArmorInvincible) != 0; }
    bool passDamage() const { return (flagBits & kArmorPassDamage) != 0; }
    bool droppable() const { return (flagBits & kArmorDroppable) != 0; }
    bool absorbOverflow() const { return (flagBits & kArmorAbsorbOverflow) != 0; }
    bool metallic() const { return (flagBits & kArmorMetallic) != 0; }
    /// `passdamage` and `absorboverflow` describe what happens to damage the layer could not
    /// take; `invincible` and the sentinel describe a layer that has no pool at all.
    bool poolsHitPoints() const { return !invincible() && !hitpointsSentinel && hitpoints > 0.0; }
};

/// One layer of one zombie after the sheet's `armorIds` order has been applied.
struct ArmorLayer {
    std::string zombieId; ///< sheet zombie id the row came from (a pack id)
    std::string armorId;  ///< `armors[]` id; empty when the id was dangling (see ArmorTable)
    unsigned flags = kArmorNoFlags;
    double hitpoints = 0.0;
    bool hitpointsSentinel = false;
    std::string artLayer; ///< `art.armorLayer`, the bone the view should draw

    bool invincible() const { return (flags & kArmorInvincible) != 0; }
    bool passDamage() const { return (flags & kArmorPassDamage) != 0; }
    bool droppable() const { return (flags & kArmorDroppable) != 0; }
    bool absorbOverflow() const { return (flags & kArmorAbsorbOverflow) != 0; }
    bool metallic() const { return (flags & kArmorMetallic) != 0; }
    bool poolsHitPoints() const { return !invincible() && !hitpointsSentinel && hitpoints > 0.0; }
    std::string flagNames() const { return armorFlagNames(flags); }
};

/// One layer as the engine tracks it: the sheet's flags plus this zombie's remaining hit points.
/// `maxHp == 0` means the layer has no pool at all (invincible or sentinel hit points), so it can
/// never break; `hp` then stays 0 and only the flags decide what a hit does.
struct ArmorLayerState {
    std::string armorId;
    unsigned flags = kArmorNoFlags;
    std::string artLayer;
    double hp = 0.0;
    double maxHp = 0.0;

    bool invincible() const { return (flags & kArmorInvincible) != 0; }
    bool passDamage() const { return (flags & kArmorPassDamage) != 0; }
    bool droppable() const { return (flags & kArmorDroppable) != 0; }
    bool absorbOverflow() const { return (flags & kArmorAbsorbOverflow) != 0; }
    bool metallic() const { return (flags & kArmorMetallic) != 0; }
    bool poolsHitPoints() const { return maxHp > 0.0; }
    std::string flagNames() const { return armorFlagNames(flags); }
};

/// One row of `contentComparison.rows[]`: a content zombie id and the pack armor set that
/// answers for it. `bridgeMethod` is `exact` for 8 and a heuristic for 2.
struct ContentArmorBridge {
    std::string contentId;
    std::string packZombieId;
    std::string bridgeMethod;
    std::vector<std::string> packArmorIds;
    std::vector<std::string> contentArmature;
    std::vector<std::string> contentArt;
    std::vector<double> contentHitpoints;
    std::vector<double> packHitpoints;
    bool match = false;
};

/// The armor sheet. `load` throws `armor table: <path>: <reason>`; `shared()` caches the file
/// found through `generatedDir()` (the same resolver the plant-food, fusion, boss and projectile
/// tables use), so `World` can resolve it once in its constructor.
class ArmorTable {
  public:
    static constexpr const char* kFileName = "armors_from_pack.json";

    static ArmorTable load(const std::filesystem::path& path);
    static const ArmorTable& shared();

    const ArmorSpec* armorById(std::string_view id) const;
    /// Layers of a **pack** zombie id, in the sheet's stored order. The order is never sorted:
    /// the sheet's own note says reading it as outermost-first is an inference, and the row order
    /// is the only thing both readings agree on.
    std::vector<ArmorLayer> zombieArmorLayers(std::string_view zombieId) const;
    /// Layers of a **content** zombie id through `contentComparison`. Empty when the zombie has
    /// no bridge row; the caller then keeps the content-only reading.
    std::vector<ArmorLayer> contentArmorLayers(std::string_view contentId) const;
    const ContentArmorBridge* contentBridge(std::string_view contentId) const;
    /// How many `zombies[]` rows carry this id. `heavy_shield` and `kongfu_gargantuar` have two
    /// (`counts.duplicateZombieIds`), which is the sheet's bookkeeping and must not be merged away.
    std::size_t zombieRowCount(std::string_view zombieId) const;

    bool empty() const { return specs_.empty(); }
    std::size_t size() const { return specs_.size(); }
    std::size_t canonical() const { return canonical_; }
    std::size_t embeddedOnly() const { return embeddedOnly_; }
    std::size_t unused() const { return unused_; }
    std::size_t withoutLayer() const { return withoutLayer_; }
    std::size_t withoutHitpoints() const { return withoutHitpoints_; }
    std::size_t withHitpoints() const { return withHitpoints_; }
    std::size_t zombieRows() const { return zombieRowTotal_; }
    std::size_t zombieTypes() const { return zombieArmorIds_.size(); }
    std::size_t danglingReferences() const { return danglingReferences_; }
    std::size_t bridged() const { return bridgeRows_.size(); }
    const std::vector<std::string>& unusedIds() const { return unusedIds_; }
    const std::vector<std::string>& duplicateZombieIds() const { return duplicateZombieIds_; }
    const std::vector<std::string>& danglingIds() const { return danglingIds_; }
    const std::vector<ContentArmorBridge>& bridges() const { return bridgeRows_; }

  private:
    std::map<std::string, ArmorSpec, std::less<>> specs_;
    /// Merged across rows of the same id, in insert order; dangling ids are kept so
    /// `zombieArmorLayers` can report them instead of silently shortening the stack.
    std::map<std::string, std::vector<std::string>, std::less<>> zombieArmorIds_;
    std::map<std::string, std::size_t, std::less<>> zombieRowCounts_;
    std::map<std::string, ContentArmorBridge, std::less<>> bridges_;
    /// Kept in file order as well, so a report can walk them the way the sheet writes them.
    std::vector<ContentArmorBridge> bridgeRows_;
    std::vector<std::string> unusedIds_;
    std::vector<std::string> duplicateZombieIds_;
    std::vector<std::string> danglingIds_;
    std::size_t canonical_ = 0;
    std::size_t embeddedOnly_ = 0;
    std::size_t unused_ = 0;
    std::size_t withoutLayer_ = 0;
    std::size_t withoutHitpoints_ = 0;
    std::size_t withHitpoints_ = 0;
    std::size_t zombieRowTotal_ = 0;
    std::size_t danglingReferences_ = 0;
};

} // namespace pvz::engine
