#pragma once

#include <cstddef>
#include <filesystem>
#include <map>
#include <string>
#include <string_view>
#include <vector>

namespace pvz::engine {

/// How a projectile travels. The names mirror the pack's `trajectory` field.
enum class Trajectory { straight, arc, drop, stationary, unknown };

/// `native/generated/projectiles_from_pack.json` spells it "static", which is a C++ keyword.
const char* trajectoryName(Trajectory trajectory);

/// One resolved row of the projectile table.
///
/// The pack gives every number a projectile could need; the engine used to run on two global
/// constants (`tuning::kShotSpeedColsPerSec` = 5.2 = 312 px/s and `tuning::kShotHitRadius` = 0.25).
/// 312 px/s is not a mode of anything: the straight-shot mode is 333 px/s (5.55 cols/s, 142 rows).
/// 0.25 *is* the CollisionRect mode (358 of 596 rows), so it stays as the fallback for rows that
/// carry no radius.
struct ProjectileSpec {
    std::string id;
    std::string pkg;
    std::string objclass;
    Trajectory trajectory = Trajectory::unknown;

    double speedCols = 0.0;      // 0 = the row declares no speed
    double hitRadiusCols = 0.0;  // 0 = the row declares no CollisionRect
    double damage = 0.0;         // 0 = no direct damage declared
    bool hasDamage = false;      // false for null / 2147483647 sentinel rows
    bool damageSentinel = false;

    bool hasSplash = false;
    double splashDamage = 0.0;
    double splashRadiusCells = 0.0;

    bool hasPierce = false;
    int pierceHits = 0;

    /// InitialVelocity z component in px/s. Non-zero marks a lobbed shot whose impact point is
    /// decided by the arc rather than by the row it was fired from.
    double vz = 0.0;

    /// Every `pkg` that ships its own copy of this id. The pack records *which keys* differ but not
    /// their values, so a pkg-specific copy cannot be reproduced: callers get the canonical numbers
    /// and report `projectile_variant_fallback` instead of pretending they resolved the variant.
    std::vector<std::string> variantPkgs;

    bool usable() const { return !id.empty(); }
    bool hasVariantFor(std::string_view query) const;
};

/// The whole table, loaded once.
class ProjectileTable {
public:
    static constexpr const char* kFileName = "projectiles_from_pack.json";

    static ProjectileTable load(const std::filesystem::path& path);
    /// Loads `generatedDir() / kFileName`. Throws `projectile table: …` when that file is missing or
    /// malformed; the directory probe is shared with the plant-food and boss tables.
    static const ProjectileTable& shared();

    bool empty() const { return specs_.empty(); }
    /// Unique ids (one per map entry).
    std::size_t size() const { return specs_.size(); }
    /// Rows in the shipped JSON, which can exceed `size()` when an id appears twice.
    std::size_t rows() const { return rows_; }
    const ProjectileSpec* find(std::string_view id) const;
    std::size_t trajectoryCount(Trajectory trajectory) const;
    std::size_t withSplash() const { return withSplash_; }
    std::size_t withPierce() const { return withPierce_; }

private:
    std::map<std::string, ProjectileSpec, std::less<>> specs_;
    std::size_t rows_ = 0;
    std::size_t withSplash_ = 0;
    std::size_t withPierce_ = 0;
};

} // namespace pvz::engine
