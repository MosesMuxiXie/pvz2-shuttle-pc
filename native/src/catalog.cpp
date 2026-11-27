#include "catalog.hpp"
#include <algorithm>
#include <cmath>
#include <fstream>
#include <limits>
#include <set>
#include <sstream>
#include <stdexcept>

#include "content/loader.hpp"

namespace pvz {
namespace fs = std::filesystem;
std::string pathUtf8(const fs::path& p) {
    const auto u8 = p.u8string();
    return {reinterpret_cast<const char*>(u8.data()), u8.size()};
}
namespace {
[[noreturn]] void fail(const fs::path& p, const std::string& detail) {
    throw std::runtime_error(pathUtf8(p) + ": " + detail);
}
Json readJson(const fs::path& p) {
    std::ifstream input(p, std::ios::binary);
    if (!input)
        fail(p, "cannot open JSON file (check that the content directory is complete and readable)");
    try {
        return Json::parse(input);
    } catch (const Json::exception& e) {
        fail(p, std::string("invalid JSON: ") + e.what());
    }
}
void object(const Json& j, const fs::path& p, const std::string& field) {
    if (!j.is_object())
        fail(p, field + " must be an object");
}
const Json& required(const Json& j, const std::string& key, const fs::path& p) {
    if (!j.contains(key))
        fail(p, "missing required field '" + key + "'");
    return j.at(key);
}
std::string text(const Json& j, const std::string& key, const fs::path& p, const std::string& fallback = "",
                 bool mandatory = false) {
    if (!mandatory && !j.contains(key))
        return fallback;
    const auto& v = required(j, key, p);
    if (!v.is_string())
        fail(p, key + " must be a string");
    return v.get<std::string>();
}
std::string id(const Json& j, const fs::path& p) {
    auto result = text(j, "id", p, "", true);
    if (result.empty() || std::any_of(result.begin(), result.end(),
                                      [](unsigned char c) { return c <= 32 || c == '/' || c == '\\'; }))
        fail(p, "id must be nonempty and cannot contain whitespace or path separators");
    return result;
}
int integer(const Json& j, const std::string& key, const fs::path& p, int fallback, int minimum = 0,
            int maximum = std::numeric_limits<int>::max(), bool mandatory = false) {
    if (!mandatory && !j.contains(key))
        return fallback;
    const auto& v = required(j, key, p);
    if (!v.is_number_integer())
        fail(p, key + " must be an integer");
    // Compare before conversion: get<int>() alone silently narrows large JSON integers.
    if (v.is_number_unsigned()) {
        const auto n = v.get<std::uint64_t>();
        if (n > static_cast<std::uint64_t>(maximum) ||
            (minimum > 0 && n < static_cast<std::uint64_t>(minimum)))
            fail(p, key + " is out of range");
    } else {
        const auto n = v.get<std::int64_t>();
        if (n < minimum || n > maximum)
            fail(p, key + " is out of range");
    }
    return v.get<int>();
}
double number(const Json& j, const std::string& key, const fs::path& p, double fallback,
              bool positive = false) {
    if (!j.contains(key))
        return fallback;
    const auto& v = j.at(key);
    if (!v.is_number())
        fail(p, key + " must be a number");
    const auto n = v.get<double>();
    if (!std::isfinite(n) || n < 0 || (positive && n == 0))
        fail(p, key + " must be finite and " + (positive ? "positive" : "nonnegative"));
    return n;
}
bool boolean(const Json& j, const std::string& key, const fs::path& p, bool fallback = false) {
    if (!j.contains(key))
        return fallback;
    if (!j.at(key).is_boolean())
        fail(p, key + " must be a boolean");
    return j.at(key).get<bool>();
}
const Json& array(const Json& j, const std::string& key, const fs::path& p) {
    const auto& v = required(j, key, p);
    if (!v.is_array())
        fail(p, key + " must be an array");
    return v;
}
void optionalFields(const Json& j, const fs::path& p) {
    if (j.contains("extra"))
        object(j.at("extra"), p, "extra");
    for (const auto& key : {"name_zh", "name_en", "art", "behavior", "desc_zh"})
        (void)text(j, key, p);
    if (j.contains("tags"))
        for (const auto& tag : array(j, "tags", p))
            if (!tag.is_string())
                fail(p, "tags must contain strings");
}
template <typename Map, typename Value> void insert(Map& map, Value&& value, const fs::path& p) {
    const auto key = value.id;
    if (!map.emplace(key, std::forward<Value>(value)).second)
        fail(p, "duplicate id '" + key + "'");
}
template <typename Fn> void registry(const fs::path& p, Fn parse) {
    const auto root = readJson(p);
    if (!root.is_array() || root.empty())
        fail(p, "registry must be a nonempty array");
    for (const auto& j : root) {
        object(j, p, "registry entry");
        parse(j);
    }
}
void reference(bool found, const fs::path& p, const std::string& field, const std::string& target) {
    if (!found)
        fail(p, field + ": unresolved reference '" + target + "'");
}
LevelDefinition parseLevel(const fs::path& p) {
    const auto j = readJson(p);
    object(j, p, "level");
    LevelDefinition l;
    l.raw = j;
    l.file = p;
    l.id = id(j, p);
    l.world = text(j, "world", p, "", true);
    l.title = text(j, "title", p);
    l.index = integer(j, "index", p, 1, 1, 1000000, true);
    l.sun = integer(j, "sun", p, 250);
    l.flags = integer(j, "flags", p, 1);
    l.seedBank = integer(j, "seed_bank", p, 6, 1, 64);
    if (j.contains("extra")) {
        object(j.at("extra"), p, "extra");
        l.extra = j.at("extra");
    }
    for (const auto& key : {"source", "package", "stage", "boss_zombie"})
        (void)text(l.extra, key, p);
    for (const auto& key : {"vasebreaker", "night", "boss"})
        (void)boolean(l.extra, key, p);
    l.rows = integer(l.extra, "board_rows", p, 5, 1, 8);
    l.cols = integer(l.extra, "board_cols", p, 9, 1, 12);
    for (const auto& card : array(j, "deck", p)) {
        if (!card.is_string() || card.get<std::string>().empty())
            fail(p, "deck must contain nonempty plant IDs");
        l.deck.push_back(card.get<std::string>());
    }
    for (const auto& w : array(j, "waves", p)) {
        object(w, p, "wave");
        WaveDefinition wave;
        wave.delay = number(w, "delay", p, 18);
        wave.flag = boolean(w, "flag", p);
        for (const auto& z : array(w, "zombies", p)) {
            ZombieSpawn spawn;
            if (z.is_string())
                spawn.type = z.get<std::string>();
            else {
                object(z, p, "zombie spawn");
                spawn.type = text(z, "type", p, "", true);
                if (z.contains("row") && !z["row"].is_null())
                    spawn.row = integer(z, "row", p, 0, 0, l.rows - 1, true);
                if (z.contains("rows") && !z["rows"].is_null()) {
                    for (const auto& row : array(z, "rows", p))
                        spawn.rows.push_back(integer(Json{{"row", row}}, "row", p, 0, 0, l.rows - 1, true));
                    if (spawn.rows.empty())
                        fail(p, "spawn rows must not be empty");
                }
            }
            if (spawn.type.empty())
                fail(p, "zombie type must not be empty");
            wave.zombies.push_back(std::move(spawn));
        }
        l.waves.push_back(std::move(wave));
    }
    return l;
}
} // namespace
Catalog loadCatalog(const fs::path& contentRoot, const CatalogOptions& options) {
    std::error_code ec;
    if (!fs::is_directory(contentRoot, ec))
        fail(contentRoot, "content directory is missing or unreadable");
    Catalog c;
    auto p = contentRoot / "plants.json";
    registry(p, [&](const Json& j) {
        optionalFields(j, p);
        PlantDefinition d;
        d.id = id(j, p);
        d.name = text(j, "name_zh", p);
        // 派生行（source="pack"）没有中文名；退回英文名，再退回 id，
        // 这样 HUD 显示 "Banana" 而不是空标签或裸 id。
        if (d.name.empty())
            d.name = text(j, "name_en", p, d.id);
        d.behavior = text(j, "behavior", p, "shoot");
        d.art = text(j, "art", p);
        d.cost = integer(j, "cost", p, 100);
        d.hp = number(j, "hp", p, 300, true);
        d.cooldown = number(j, "cooldown", p, 5);
        d.damage = number(j, "damage", p, 20);
        d.interval = number(j, "interval", p, 1.4);
        d.raw = j;
        for (const auto& key : {"sun_value", "almanac_no"})
            (void)integer(j, key, p, 0);
        for (const auto& key : {"sun_interval", "splash", "slow", "melee_range", "delay"})
            (void)number(j, key, p, 0);
        (void)boolean(j, "fused", p);
        // The checked-in schema also uses 0/1 for pierce and named plant-food skills.
        if (j.contains("pierce")) {
            if (j["pierce"].is_number_integer())
                (void)integer(j, "pierce", p, 0, 0, 1);
            else
                (void)boolean(j, "pierce", p);
        }
        if (j.contains("plantfood")) {
            if (j["plantfood"].is_string()) {
                (void)text(j, "plantfood", p); // Empty string means no skill in the legacy schema.
            } else
                (void)boolean(j, "plantfood", p);
        }
        if (j.contains("projectile") && !j["projectile"].is_null())
            (void)text(j, "projectile", p);
        if (j.contains("rows"))
            for (const auto& row : array(j, "rows", p))
                (void)integer(Json{{"row", row}}, "row", p, 0, -63, 63, true);
        insert(c.plants, std::move(d), p);
    });
    p = contentRoot / "zombies.json";
    registry(p, [&](const Json& j) {
        optionalFields(j, p);
        ZombieDefinition d;
        d.id = id(j, p);
        d.name = text(j, "name_zh", p);
        d.behavior = text(j, "behavior", p, "walk");
        d.art = text(j, "art", p);
        d.hp = number(j, "hp", p, 190, true);
        d.speed = number(j, "speed", p, 0.185);
        d.eatDps = number(j, "eat_dps", p, 100);
        d.raw = j;
        (void)integer(j, "cost", p, 100);
        if (j.contains("armature") && !j["armature"].is_null())
            (void)text(j, "armature", p);
        if (j.contains("armor"))
            for (const auto& armor : array(j, "armor", p)) {
                object(armor, p, "armor");
                (void)required(armor, "hp", p);
                d.armor.push_back(number(armor, "hp", p, 0));
                (void)boolean(armor, "metal", p);
                (void)text(armor, "art", p);
            }
        insert(c.zombies, std::move(d), p);
    });
    p = contentRoot / "worlds.json";
    registry(p, [&](const Json& j) {
        optionalFields(j, p);
        WorldDefinition d;
        d.id = id(j, p);
        d.name = text(j, "name_zh", p);
        d.map = text(j, "map", p);
        d.lawn = text(j, "lawn", p);
        d.order = integer(j, "order", p, 1, 1);
        d.levelCount = integer(j, "levels", p, 0);
        d.raw = j;
        if (j.contains("unlock_after") && !j["unlock_after"].is_null())
            d.unlockAfter = text(j, "unlock_after", p);
        insert(c.worlds, std::move(d), p);
    });
    for (const auto& [key, w] : c.worlds) {
        if (w.unlockAfter)
            reference(c.worlds.contains(*w.unlockAfter), p, "unlock_after", *w.unlockAfter);
        std::set<std::string> visited;
        const auto* current = &w;
        while (current) {
            if (!visited.insert(current->id).second)
                fail(p, "world unlock cycle at '" + current->id + "'");
            current = current->unlockAfter && c.worlds.contains(*current->unlockAfter)
                          ? &c.worlds.at(*current->unlockAfter)
                          : nullptr;
        }
    }
    const auto dir = contentRoot / "levels";
    if (!fs::is_directory(dir, ec))
        fail(dir, "levels directory is missing or unreadable");
    std::vector<fs::path> files;
    for (const auto& entry : fs::directory_iterator(dir))
        if (entry.is_regular_file() && entry.path().extension() == ".json")
            files.push_back(entry.path());
    std::sort(files.begin(), files.end());
    std::map<std::string, std::set<int>> indices;
    for (const auto& file : files) {
        auto l = parseLevel(file);
        reference(c.worlds.contains(l.world), file, "world", l.world);
        for (const auto& plant : l.deck)
            reference(c.plants.contains(plant), file, "deck", plant);
        for (const auto& wave : l.waves)
            for (const auto& zombie : wave.zombies)
                reference(c.zombies.contains(zombie.type), file, "waves.zombies", zombie.type);
        // extra.boss_zombie is an OBB codename (e.g. zomboss), not a local zombie ID.
        // Preserve it for the future Boss adapter; only wave spawn types reference this registry.
        if (c.levels.contains(l.id))
            fail(file, "duplicate level id '" + l.id + "'");
        if (!indices[l.world].insert(l.index).second)
            fail(file, "duplicate level index in world '" + l.world + "'");
        insert(c.levels, std::move(l), file);
    }
    for (const auto& [key, w] : c.worlds) {
        const auto& ix = indices[key];
        if (ix.size() != static_cast<std::size_t>(w.levelCount))
            fail(p, "world '" + key + "' declares " + std::to_string(w.levelCount) + " levels, loaded " +
                        std::to_string(ix.size()));
        if (!ix.empty() && (*ix.begin() != 1 || *ix.rbegin() != w.levelCount))
            fail(p, "world '" + key + "' level indices must span 1..levels");
    }
    // Geometry comes from the original stage modules, not from the level files: the
    // shipped 1809 levels carry no rows/cols at all, so without this file every world
    // would open as 5x9 and the 6-row beach/modern boards would be unreachable.
    if (options.boardSizes) {
        const fs::path& boardPath = *options.boardSizes;
        try {
            const Json doc = readJson(boardPath);
            if (!doc.is_object()) fail(boardPath, "board sizes must be a JSON object of world -> size");
            for (const auto& [world, entry] : doc.items()) {
                if (!entry.is_object()) fail(boardPath, "board size for '" + world + "' must be an object");
                BoardSize size;
                size.rows = integer(entry, "rows", boardPath, 5, 1, 8);
                size.cols = integer(entry, "cols", boardPath, 9, 1, 12);
                size.source = entry.value("source", std::string{});
                c.boards[world] = std::move(size);
            }
            for (auto& [id, level] : c.levels) {
                const auto it = c.boards.find(level.world);
                if (it == c.boards.end()) continue;
                // An explicit per-level override still wins over the world default.
                if (level.extra.contains("board_rows")) continue;
                level.rows = it->second.rows;
                level.cols = it->second.cols;
            }
            std::ostringstream note;
            note << "boards=" << c.boards.size() << " worlds from " << pathUtf8(boardPath);
            c.boardsNote = note.str();
        } catch (const std::exception& e) {
            // A requested geometry file that does not parse is an error, not a reason to
            // quietly run every level at 5x9: that fallback made the 26-world geometry
            // assertions unreachable (they always saw the default) and let a typo in the
            // CLI path look like a passing run.
            throw std::runtime_error(std::string("board sizes: ") + e.what());
        }
    } else {
        c.boardsNote = "boards=json-default (no geometry file requested)";
    }
    if (options.contentPack) {
        const fs::path& packPath = *options.contentPack;
        try {
            auto pack = std::make_shared<const content::ContentPack>(content::loadContentPack(packPath));
            std::ostringstream note;
            note << "rules=pack " << pathUtf8(packPath) << " plants=" << pack->plants.size()
                 << " zombies=" << pack->zombies.size();
            if (!pack->zombieDuplicates.empty())
                note << " duplicate_ids=" << pack->zombieDuplicates.size();
            c.rulesNote = note.str();
            c.rules = std::move(pack);
        } catch (const std::exception& e) {
            // Same rule as the geometry file: an explicitly requested pack is mandatory.
            // Silent fallback hid a broken --pack (every family number dropped back to a
            // tuning constant) while the process still exited 0.
            throw std::runtime_error(std::string("rules pack: ") + e.what());
        }
    } else {
        c.rulesNote = "rules=json (no pack requested)";
    }
    return c;
}
bool LevelDefinition::synthesized() const {
    return extra.value("source", std::string{}) == "obb-synth";
}
bool LevelDefinition::vasebreaker() const {
    return extra.value("vasebreaker", false);
}
CatalogSummary Catalog::summary() const {
    CatalogSummary s;
    s.worlds = worlds.size();
    s.plants = plants.size();
    s.zombies = zombies.size();
    s.levels = levels.size();
    for (const auto& [key, l] : levels) {
        const auto source = l.extra.value("source", std::string{});
        if (source == "obb")
            ++s.original;
        else if (l.synthesized())
            ++s.synthesized;
        else
            ++s.unknownSource;
        if (l.vasebreaker()) {
            ++s.vasebreaker;
            if (l.synthesized())
                ++s.synthesizedVasebreaker;
        }
    }
    return s;
}
std::string CatalogSummary::text() const {
    std::ostringstream o;
    o << "worlds=" << worlds << "\nplants=" << plants << "\nzombies=" << zombies << "\nlevels=" << levels
      << "\noriginal=" << original << "\nsynthesized=" << synthesized << "\nunknown_source=" << unknownSource
      << "\nvasebreaker=" << vasebreaker << "\nsynthesized_vasebreaker=" << synthesizedVasebreaker << '\n';
    return o.str();
}
} // namespace pvz
