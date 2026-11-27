#include "level_badges.hpp"

#include "catalog.hpp"  // Json + pathUtf8: the same aliases every other table loader uses

#include <algorithm>
#include <cctype>
#include <fstream>
#include <initializer_list>
#include <iterator>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace pvz {
namespace {

// The display order and the Chinese names. Order is the order the chips appear in, so a level with
// a vasebreaker board always puts that chip first: the same two kinds must never swap places between
// two levels of the same world.
struct KindEntry {
    const char* kind;
    const char* label;
};

constexpr KindEntry kKinds[] = {
    {"vasebreaker", "砸罐子"},
    {"rail", "铁轨"},
    {"conveyor", "传送带"},
    {"tide", "潮汐"},
    {"protecttheplant", "保卫植物"},
    {"gravestone", "墓碑"},
    {"laststand", "最后防线"},
    {"bowling", "保龄球"},
    {"beghouled", "三消"},
    {"column", "立柱"},
    {"cannon", "火炮"},
    {"camel", "骆驼"},
    {"cowboy", "西部"},
    {"seeingstars", "追星"},
    {"sproutplanting", "播种"},
    {"whackazombie", "打僵尸"},
    {"invisighoul", "隐形僵尸"},
    {"deathexplosion", "死亡爆炸"},
    {"joust", "长矛对决"},
    {"bigtrouble", "大麻烦"},
    {"bonuschallenge", "奖励关"},
};

// Unknown kinds sort after every known one, so a future table cannot push 砸罐子 off the line.
constexpr int kUnknownRank = 1000;

const KindEntry* findKind(const std::string& kind) {
    for (const KindEntry& entry : kKinds) {
        if (kind == entry.kind) return &entry;
    }
    return nullptr;
}

int rankOf(const std::string& kind) {
    const KindEntry* entry = findKind(kind);
    if (entry == nullptr) return kUnknownRank;
    return static_cast<int>(entry - kKinds);
}

/// Which mechanics the simulation actually runs today (B6b). The four below are the ones the S3
/// engine drives end to end; the rest exist in the original data and are listed so the level list is
/// not lying about the level's contents, but the screen draws them as `（未接入）`. Keeping the list
/// here - next to the dictionary - means the badge data and its "can I play it" answer cannot drift
/// into two different files.
bool wiredOf(const std::string& kind) {
    return kind == "vasebreaker" || kind == "rail" || kind == "conveyor" ||
           kind == "protecttheplant";
}

/// Reads one generated table. Returns nothing (and fills `note`) instead of throwing: the screen
/// must survive a half-generated checkout, and only the missing half loses its badges.
std::optional<Json> readTable(const std::filesystem::path& file, std::string& note) {
    std::ifstream in(file);
    if (!in) {
        if (!note.empty()) note += "; ";
        note += pathUtf8(file) + ": cannot open";
        return std::nullopt;
    }
    Json doc;
    try {
        in >> doc;
    } catch (const std::exception& error) {
        if (!note.empty()) note += "; ";
        note += pathUtf8(file) + ": " + error.what();
        return std::nullopt;
    }
    if (!doc.is_object()) {
        if (!note.empty()) note += "; ";
        note += pathUtf8(file) + ": top level is not an object";
        return std::nullopt;
    }
    return doc;
}

/// Adds `kind` to one level, keeping the first count seen: a level that lists the same kind twice is
/// one badge, not two.
void addBadge(std::map<std::string, LevelBadge>& level, const std::string& kind, int count,
              std::vector<std::string>& unknown) {
    if (kind.empty()) return;
    const auto existing = level.find(kind);
    if (existing != level.end()) {
        if (count > existing->second.count) existing->second.count = count;
        return;
    }
    LevelBadge badge;
    badge.kind = kind;
    const KindEntry* entry = findKind(kind);
    badge.label = entry != nullptr ? std::string(entry->label) : kind;
    badge.count = count > 0 ? count : 1;
    badge.rank = rankOf(kind);
    badge.wired = wiredOf(kind);
    if (entry == nullptr && std::find(unknown.begin(), unknown.end(), kind) == unknown.end())
        unknown.push_back(kind);
    level.emplace(kind, std::move(badge));
}

std::vector<LevelBadge> sortedBadges(const std::map<std::string, LevelBadge>& level) {
    std::vector<LevelBadge> out;
    out.reserve(level.size());
    for (const auto& entry : level) out.push_back(entry.second);
    std::sort(out.begin(), out.end(), [](const LevelBadge& a, const LevelBadge& b) {
        if (a.rank != b.rank) return a.rank < b.rank;
        if (a.label != b.label) return a.label < b.label;
        return a.kind < b.kind;
    });
    return out;
}

/// The minecart count of a rail level. `extra.minecarts` is the table's own number; a rail level
/// that lists none still gets the plain 铁轨 chip, because the rail itself is the mechanic.
int railCount(const Json& entry) {
    const auto extra = entry.find("extra");
    if (extra == entry.end() || !extra->is_object()) return 1;
    const auto carts = extra->find("minecarts");
    if (carts == extra->end() || !carts->is_number()) return 1;
    const int count = static_cast<int>(carts->get<double>());
    return count > 0 ? count : 1;
}

/// True when a grid item is a gravestone. The table spells them `gravestone_tutorial`,
/// `gravestoneZombieOnDestruction`, `gravestone_battlez_sun`…, so the test is on the token, not on a
/// fixed list that would rot with every world.
bool isGravestone(const std::string& item) {
    std::string lowered;
    lowered.reserve(item.size());
    for (char c : item) lowered.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
    return lowered.find("gravestone") != std::string::npos ||
           lowered.find("tombstone") != std::string::npos;
}

bool hasGravestone(const Json& entry) {
    const auto items = entry.find("initialGridItems");
    if (items == entry.end() || !items->is_object()) return false;
    const auto placements = items->find("placements");
    if (placements == items->end() || !placements->is_array()) return false;
    for (const Json& placement : *placements) {
        if (!placement.is_object()) continue;
        const auto item = placement.find("item");
        if (item != placement.end() && item->is_string() && isGravestone(item->get<std::string>()))
            return true;
    }
    return false;
}

}  // namespace

LevelBadges load(const std::filesystem::path& generatedDir) {
    LevelBadges badges;
    badges.source = generatedDir;
    if (generatedDir.empty()) {
        badges.note = "generated directory not found (set PVZ_GENERATED_DIR or run from the repository root)";
        return badges;
    }

    // levelId -> kind -> badge, merged from both tables before sorting, so a kind that both tables
    // mention (conveyor is the one that does) keeps a single chip.
    std::map<std::string, std::map<std::string, LevelBadge>> merged;
    std::vector<std::string> unknown;

    if (const auto minigames = readTable(generatedDir / "minigames.json", badges.note)) {
        const auto levels = minigames->find("levels");
        if (levels != minigames->end() && levels->is_object()) {
            for (const auto& entry : levels->items()) {
                if (!entry.value().is_object()) continue;
                ++badges.minigameLevels;
                auto& level = merged[entry.key()];
                const auto kinds = entry.value().find("kinds");
                if (kinds == entry.value().end() || !kinds->is_array()) continue;
                for (const Json& kind : *kinds) {
                    if (!kind.is_string()) continue;
                    const std::string name = kind.get<std::string>();
                    const int count = name == "rail" ? railCount(entry.value()) : 1;
                    addBadge(level, name, count, unknown);
                }
            }
        }
    }

    if (const auto mechanics = readTable(generatedDir / "level_mechanics.json", badges.note)) {
        const auto levels = mechanics->find("levels");
        if (levels != mechanics->end() && levels->is_object()) {
            for (const auto& entry : levels->items()) {
                if (!entry.value().is_object()) continue;
                auto& level = merged[entry.key()];
                bool contributed = false;
                const auto conveyor = entry.value().find("conveyor");
                if (conveyor != entry.value().end() && !conveyor->is_null()) {
                    addBadge(level, "conveyor", 1, unknown);
                    contributed = true;
                }
                if (hasGravestone(entry.value())) {
                    addBadge(level, "gravestone", 1, unknown);
                    contributed = true;
                }
                if (contributed) ++badges.mechanicLevels;
            }
        }
    }

    for (auto& entry : merged) {
        std::vector<LevelBadge> sorted = sortedBadges(entry.second);
        if (!sorted.empty()) badges.levels.emplace(entry.first, std::move(sorted));
    }
    std::sort(unknown.begin(), unknown.end());
    badges.unknownKinds = std::move(unknown);
    badges.loaded = !badges.levels.empty();
    if (!badges.loaded && badges.note.empty()) badges.note = "no level in either table carries a badge";
    return badges;
}

LevelBadges loadBadges(const std::filesystem::path& generatedDir) { return load(generatedDir); }

const std::vector<LevelBadge>& badgesOf(const LevelBadges& badges, const std::string& levelId) {
    static const std::vector<LevelBadge> kEmpty;
    const auto found = badges.levels.find(levelId);
    return found == badges.levels.end() ? kEmpty : found->second;
}

std::vector<std::string> badgesFor(const LevelBadges& badges, const std::string& levelId) {
    const std::vector<LevelBadge>& all = badgesOf(badges, levelId);
    std::vector<std::string> chips;
    if (all.empty()) return chips;
    const std::size_t shown = all.size() <= kMaxBadges ? all.size() : kMaxBadges - 1;
    for (std::size_t i = 0; i < shown; ++i) {
        const LevelBadge& badge = all[i];
        chips.push_back(badge.count > 1 ? badge.label + "×" + std::to_string(badge.count) : badge.label);
    }
    if (shown < all.size()) chips.push_back("+" + std::to_string(all.size() - shown));
    return chips;
}

std::string badgeLine(const std::vector<std::string>& badges) {
    std::string out;
    for (const std::string& chip : badges) {
        if (!out.empty()) out += " · ";
        out += chip;
    }
    return out;
}

std::string badgeSummary(const LevelBadges& badges, const std::string& levelId) {
    return badgeLine(badgesFor(badges, levelId));
}

std::string badgeLabel(const std::string& kind) {
    const KindEntry* entry = findKind(kind);
    return entry != nullptr ? std::string(entry->label) : std::string();
}

bool badgeWired(const std::string& kind) { return wiredOf(kind); }

std::string badgeKindOfLabel(const std::string& label) {
    for (const KindEntry& entry : kKinds) {
        if (label == entry.label) return std::string(entry.kind);
    }
    return std::string();
}

std::vector<std::string> badgeDictionary() {
    std::vector<std::string> rows;
    rows.reserve(std::size(kKinds));
    for (const KindEntry& entry : kKinds) {
        rows.push_back(std::string(entry.kind) + "=" + entry.label);
    }
    return rows;
}

}  // namespace pvz
