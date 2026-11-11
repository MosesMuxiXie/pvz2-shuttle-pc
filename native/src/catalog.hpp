#pragma once

#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace shuttle {

struct ZombieSpawn {
    std::string type;
    std::optional<int> row;
    std::vector<int> rows;
};

struct WaveDefinition {
    double delay{};
    bool flag{};
    std::vector<ZombieSpawn> zombies;
    int additionalPlantfood{};
};

struct LevelDefinition {
    std::string id;
    std::string world;
    int index{};
    std::string title;
    int sun{};
    int flags{};
    int seedBank{};
    std::vector<std::string> deck;
    std::vector<WaveDefinition> waves;
    std::string source;
    std::string package;
    std::string stage;
    bool vasebreaker{};
    nlohmann::json extra;
};

struct CatalogSummary {
    std::size_t synthesized{};
    std::size_t vasebreaker{};
    std::size_t synthesizedVasebreaker{};
};

struct Catalog {
    using Registry = std::map<std::string, nlohmann::json>;

    Registry plants;
    Registry zombies;
    Registry worlds;
    std::map<std::string, LevelDefinition> levels;

    [[nodiscard]] CatalogSummary summary() const;
};

[[nodiscard]] Catalog loadCatalog(const std::filesystem::path& contentRoot);
[[nodiscard]] LevelDefinition loadLevelDefinition(const std::filesystem::path& path, const Catalog& catalog);
[[nodiscard]] std::string utf8Path(const std::filesystem::path& path);

}
