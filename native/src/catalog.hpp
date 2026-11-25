#pragma once
#include <filesystem>
#include <map>
#include <memory>
#include <nlohmann/json.hpp>
#include <optional>
#include <string>
#include <vector>

// `Catalog::rules` is a `shared_ptr<const content::ContentPack>` that every caller
// immediately dereferences (`rules->findPlant(...)`, `rules->plants`). A forward
// declaration made that legal here and left the *definition* to whoever happened to
// include `content/model.hpp`, which produced two red windows on 2026-11-20: the
// new `art_audit_test.cpp` (22:04) and `battle_view.cpp` (22:09) both failed with
// C2027/C2039 "use of undefined type ContentPack" while `catalog.hpp` looked fine.
// The definition is included unconditionally so audit and desktop builds see one
// identical contract; `content/model.hpp` includes nothing from `pvz`, so there is
// no cycle.
#include "content/model.hpp"

namespace pvz {
using Json = nlohmann::json;
struct PlantDefinition {
    std::string id, name, behavior, art;
    int cost = 100;
    double hp = 300, cooldown = 5, damage = 20, interval = 1.4;
    Json raw;
};
struct ZombieDefinition {
    std::string id, name, behavior, art;
    double hp = 190, speed = 0.185, eatDps = 100;
    std::vector<double> armor;
    Json raw;
};
struct WorldDefinition {
    std::string id, name, map, lawn;
    std::optional<std::string> unlockAfter;
    int order = 1, levelCount = 0;
    Json raw;
};
struct ZombieSpawn {
    std::string type;
    std::optional<int> row;
    std::vector<int> rows;
};
struct WaveDefinition {
    double delay = 18;
    bool flag = false;
    std::vector<ZombieSpawn> zombies;
};
struct LevelDefinition {
    std::string id, world, title;
    int index = 1, sun = 250, seedBank = 6, flags = 1, rows = 5, cols = 9;
    std::vector<std::string> deck;
    std::vector<WaveDefinition> waves;
    Json extra = Json::object(), raw;
    std::filesystem::path file;
    bool synthesized() const;
    bool vasebreaker() const;
};
/// Board geometry derived from the original stage modules (`tools/contentc/geometry.py`
/// writes `native/generated/board_sizes.json`). The shipped level files carry no
/// rows/cols at all, so without this every level would open as 5x9.
struct BoardSize {
    int rows = 5, cols = 9;
    std::string source;
};
struct CatalogSummary {
    std::size_t worlds = 0, plants = 0, zombies = 0, levels = 0;
    std::size_t original = 0, synthesized = 0, unknownSource = 0;
    std::size_t vasebreaker = 0, synthesizedVasebreaker = 0;
    std::string text() const;
};
struct CatalogOptions {
    /// Rules pack generated from the shipped property sheets. When it loads, its
    /// 339/1127 records are the authoritative plant and zombie parameters; the
    /// JSON registries stay in place for level decks, worlds and translations
    /// until the id mapping exists. A pack that fails to load never stops the
    /// catalog: the JSON numbers are used and `rulesNote` says why.
    std::optional<std::filesystem::path> contentPack;
    /// Optional `board_sizes.json`. When absent, or for a world it does not list,
    /// levels keep their own rows/cols (5x9 by default).
    std::optional<std::filesystem::path> boardSizes;
};
struct Catalog {
    std::map<std::string, PlantDefinition> plants;
    std::map<std::string, ZombieDefinition> zombies;
    std::map<std::string, WorldDefinition> worlds;
    std::map<std::string, LevelDefinition> levels;
    /// Set when a rules pack was requested and loaded.
    std::shared_ptr<const content::ContentPack> rules;
    /// One line describing what happened to the requested pack.
    std::string rulesNote;
    /// World -> board size, when `board_sizes.json` was loaded.
    std::map<std::string, BoardSize> boards;
    /// One line describing what happened to the requested geometry file.
    std::string boardsNote;
    CatalogSummary summary() const;
};
std::string pathUtf8(const std::filesystem::path& path);
Catalog loadCatalog(const std::filesystem::path& contentRoot, const CatalogOptions& options = {});
} // namespace pvz
