#pragma once
#include <cstddef>
#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace pvz::engine {

/// One `Actions` row a plant food feed plays, flattened to what the kernel needs.
///
/// The property sheets write these as regular actions on the plant's plant-food object;
/// `tools/contentc` flattens them to `native/generated/plantfood_from_pack.json` so the
/// engine never parses the raw sheet at run time.
struct PlantFoodEffect {
    std::string kind;       // "projectile" for all six shipped rows
    std::string projectile; // ProjectileTypes RTID name, empty when the sheet has none
    std::optional<double> cooldownMin;
    std::optional<double> cooldownMax;
    std::optional<double> initialMin;
    std::optional<double> spawnOffsetX; // pixels, exactly as the sheet writes them
    std::optional<double> spawnOffsetY;
    std::string launchSound;
    bool hasProjectile() const { return !projectile.empty(); }
};

/// One plant's plant-food declaration.
///
/// Two shapes exist in the shipped data and they behave differently:
///  * `effects` is non-empty (six plants: sungun, dartichoke, draftodil1, homingthistle,
///    magnetfruit, rheumnobile) - feeding plays that action once, which is the original
///    behaviour;
///  * `effects` is empty (everyone else) - there is no action to play, so feeding is the
///    duration-only buff described by `durationSeconds`.
struct PlantFoodRow {
    std::string id;       // client id or pack id, whichever the sheet used
    std::string packType; // pack `TypeName`, empty when the row has no pack id
    std::string idKind;   // "client" | "pack"
    std::string framework;
    std::optional<double> durationSeconds;
    std::optional<int> playCount;
    std::vector<PlantFoodEffect> effects;
    std::vector<std::string> gaps; // what the sheets do not declare for this plant
    bool hasActionSlot() const { return !effects.empty(); }
    /// The first effect that names a projectile, or nullptr.
    const PlantFoodEffect* projectileEffect() const;
    bool matches(const std::string& type) const;
};

class PlantFoodTable {
  public:
    static constexpr const char* kFileName = "plantfood_from_pack.json";

    /// Parse a generated table. Every failure throws `plantfood table: <path>: <reason>` -
    /// a half-loaded buff table would silently change what feeding does.
    static PlantFoodTable load(const std::filesystem::path& file);
    /// The process-wide table from `generatedDir()`, parsed once.
    static const PlantFoodTable& shared();

    bool empty() const { return rows_.empty(); }
    std::size_t size() const { return rows_.size(); }
    /// How many rows actually carry an action to play (the six above).
    std::size_t actionSlotRows() const;

    const PlantFoodRow* find(const std::string& type) const;
    bool has(const std::string& type) const { return find(type) != nullptr; }
    const std::vector<PlantFoodRow>& rows() const { return rows_; }

  private:
    std::vector<PlantFoodRow> rows_;
};

/// Where the generated tables live.
///
/// `PVZ_GENERATED_DIR` is a compile definition CMake sets to `native/generated`; the
/// environment variable of the same name overrides it, which is what lets a test point the
/// loader at a fixture. Empty when neither is available.
std::filesystem::path generatedDir();

} // namespace pvz::engine
