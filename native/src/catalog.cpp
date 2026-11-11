#include "catalog.hpp"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <string_view>
#include <utility>

namespace shuttle {

namespace {

namespace fs = std::filesystem;
using nlohmann::json;

json readJson(const fs::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("cannot open file");
    }
    return json::parse(input);
}

template <typename Decode>
auto readDefinition(const fs::path& path, Decode decode) {
    try {
        return decode(readJson(path));
    } catch (const std::exception& error) {
        throw std::runtime_error(utf8Path(path) + ": " + error.what());
    }
}

const json& nonEmptyArray(const json& value, std::string_view label) {
    if (!value.is_array() || value.empty()) {
        throw std::runtime_error(std::string(label) + " must be a non-empty array");
    }
    return value;
}

std::string readId(const json& value, std::string_view label) {
    auto id = value.get<std::string>();
    if (id.empty()) {
        throw std::runtime_error(std::string(label) + " must not be empty");
    }
    return id;
}

int readInt(const json& value, std::string_view label, int minimum = 0) {
    if (value.is_number_integer()) {
        const auto numeric = value.get<double>();
        if (numeric >= minimum && numeric <= std::numeric_limits<int>::max()) {
            return static_cast<int>(numeric);
        }
    }
    throw std::runtime_error(std::string(label) + " must be an integer in range");
}

Catalog::Registry readRegistry(const fs::path& path) {
    return readDefinition(path, [](json data) {
        nonEmptyArray(data, "registry");
        Catalog::Registry registry;
        for (auto& item : data) {
            auto id = readId(item.at("id"), "registry ID");
            if (!registry.emplace(id, std::move(item)).second) {
                throw std::runtime_error("duplicate registry ID '" + id + "'");
            }
        }
        return registry;
    });
}

void requireReference(const Catalog::Registry& registry, const std::string& id,
                      std::string_view kind) {
    if (!registry.contains(id)) {
        throw std::runtime_error("unknown " + std::string(kind) + " '" + id + "'");
    }
}

void validateWorldUnlocks(const Catalog::Registry& worlds, const fs::path& path) {
    for (const auto& [id, definition] : worlds) {
        const auto after = definition.find("unlock_after");
        if (after == definition.end() || after->is_null()) {
            continue;
        }
        if (!after->is_string() || !worlds.contains(after->get_ref<const std::string&>())) {
            throw std::runtime_error(utf8Path(path) + ": invalid unlock_after for world '" +
                                     id + "': " + after->dump());
        }
    }
}

LevelDefinition decodeLevel(json data, const Catalog& catalog) {
    LevelDefinition level;
    level.id = readId(data.at("id"), "level ID");
    level.world = readId(data.at("world"), "world ID");
    requireReference(catalog.worlds, level.world, "world");
    level.index = readInt(data.at("index"), "index", 1);
    level.title = data.at("title").get<std::string>();
    level.sun = readInt(data.at("sun"), "sun");
    level.flags = readInt(data.at("flags"), "flags");
    level.seedBank = readInt(data.at("seed_bank"), "seed_bank", 1);
    for (const auto& entry : nonEmptyArray(data.at("deck"), "deck")) {
        auto id = readId(entry, "plant ID");
        requireReference(catalog.plants, id, "plant");
        level.deck.push_back(std::move(id));
    }
    for (const auto& entry : nonEmptyArray(data.at("waves"), "waves")) {
        WaveDefinition wave;
        wave.delay = entry.at("delay").get<double>();
        if (!std::isfinite(wave.delay) || wave.delay < 0) {
            throw std::runtime_error("wave delay must be finite and nonnegative");
        }
        wave.flag = entry.at("flag").get<bool>();
        if (const auto amount = entry.find("additional_plantfood"); amount != entry.end()) {
            wave.additionalPlantfood = readInt(*amount, "additional_plantfood");
        }
        const auto& zombies = entry.at("zombies");
        if (!zombies.is_array()) {
            throw std::runtime_error("wave zombies must be an array");
        }
        for (const auto& zombie : zombies) {
            ZombieSpawn spawn;
            spawn.type = readId(zombie.is_string() ? zombie : zombie.at("type"), "zombie ID");
            requireReference(catalog.zombies, spawn.type, "zombie");
            if (zombie.contains("row") && !zombie.at("row").is_null()) {
                spawn.row = readInt(zombie.at("row"), "zombie row");
            }
            if (zombie.contains("rows") && !zombie.at("rows").is_null()) {
                const auto& rows = zombie.at("rows");
                if (!rows.is_array()) {
                    throw std::runtime_error("zombie rows must be an array");
                }
                for (const auto& row : rows) {
                    spawn.rows.push_back(readInt(row, "zombie row"));
                }
            }
            wave.zombies.push_back(std::move(spawn));
        }
        level.waves.push_back(std::move(wave));
    }
    level.extra = std::move(data.at("extra"));
    level.source = readId(level.extra.at("source"), "level source");
    if (level.source != "obb" && level.source != "obb-synth") {
        throw std::runtime_error("unknown level source '" + level.source + "'");
    }
    level.package = readId(level.extra.at("package"), "level package");
    level.stage = level.extra.at("stage").get<std::string>();
    level.vasebreaker = level.extra.value("vasebreaker", false);
    return level;
}

}

std::string utf8Path(const fs::path& path) {
    const auto value = path.u8string();
    return {value.begin(), value.end()};
}

LevelDefinition loadLevelDefinition(const fs::path& path, const Catalog& catalog) {
    return readDefinition(path, [&catalog](json data) { return decodeLevel(std::move(data), catalog); });
}

Catalog loadCatalog(const fs::path& contentRoot) {
    Catalog catalog;
    catalog.plants = readRegistry(contentRoot / "plants.json");
    catalog.zombies = readRegistry(contentRoot / "zombies.json");
    const auto worldsPath = contentRoot / "worlds.json";
    catalog.worlds = readRegistry(worldsPath);
    validateWorldUnlocks(catalog.worlds, worldsPath);
    const auto levelRoot = contentRoot / "levels";
    if (!fs::is_directory(levelRoot)) {
        throw std::runtime_error(utf8Path(levelRoot) + ": cannot open level directory");
    }

    std::vector<fs::path> paths;
    for (const auto& entry : fs::directory_iterator(levelRoot)) {
        if (entry.is_regular_file() && entry.path().extension() == ".json") {
            paths.push_back(entry.path());
        }
    }
    if (paths.empty()) {
        throw std::runtime_error(utf8Path(levelRoot) + ": no level JSON files");
    }
    std::sort(paths.begin(), paths.end());
    for (const auto& path : paths) {
        auto level = loadLevelDefinition(path, catalog);
        const auto id = level.id;
        if (!catalog.levels.emplace(id, std::move(level)).second) {
            throw std::runtime_error(utf8Path(path) + ": duplicate level ID '" + id + "'");
        }
    }
    return catalog;
}

CatalogSummary Catalog::summary() const {
    CatalogSummary result;
    for (const auto& [id, level] : levels) {
        const auto synthesized = level.source == "obb-synth";
        result.synthesized += synthesized;
        result.vasebreaker += level.vasebreaker;
        result.synthesizedVasebreaker += synthesized && level.vasebreaker;
    }
    return result;
}

}
