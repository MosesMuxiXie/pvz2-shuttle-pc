#pragma once

// Per-level gameplay badges: what is unusual about a level, in the fewest words that still tell the
// truth.
//
// The level list used to say only "world, index, stars, cleared". That is everything the save knows
// and nothing about the level itself: a vasebreaker board and a plain lawn looked identical in the
// list. The two generated tables already answer the question —
//
//   * `minigames.json` says which gameplay kinds the level turns on (vasebreaker, rail, conveyor,
//     tide, protecttheplant, …), and how many minecarts a rail level carries;
//   * `level_mechanics.json` says which grid items the level starts with (gravestones are the one
//     that reads as a badge rather than as scenery) and whether a conveyor belt is present even
//     when the minigame table did not classify the level as a conveyor level.
//
// This file merges the two into `levelId -> [badge]` and formats the one line the screen draws. It
// deliberately has no SDL and no engine dependency: the screen passes `engine::generatedDir()`, the
// test passes a fixture directory or the same generated directory, and both get the same answer.

#include <cstddef>
#include <filesystem>
#include <map>
#include <string>
#include <vector>

namespace pvz {

/// One chip on the badge line.
struct LevelBadge {
    std::string kind;   ///< engine token, e.g. "vasebreaker" (kept so a test can assert on it)
    std::string label;  ///< 中文 chip text: 砸罐子 / 铁轨 / 墓碑
    int count = 1;      ///< how many times it applies; >1 renders `×N` (rail: the minecart count)
    int rank = 0;       ///< fixed display order, smaller first
    /// Whether the simulation actually runs this mechanic today (B6b). The badge still describes what
    /// the *original* level contains either way; a `false` only tells the screen to draw the chip in
    /// the muted colour with a `（未接入）` suffix, so a player is never promised a mode the build
    /// cannot play yet. Keep the order independent of this flag: the chips sort by `rank` alone.
    bool wired = false;
};

/// Every level's badges, loaded once per screen.
struct LevelBadges {
    /// The directory the two tables were read from; empty when nothing was found.
    std::filesystem::path source;
    /// Why the load produced nothing (or what it had to skip); empty on a clean load.
    std::string note;
    bool loaded = false;
    /// levelId -> badges, already sorted and de-duplicated by kind.
    std::map<std::string, std::vector<LevelBadge>> levels;
    /// Kinds the dictionary does not know. They still display (raw token as the label), but the
    /// screen and the report can say so instead of inventing a translation.
    std::vector<std::string> unknownKinds;
    int minigameLevels = 0;  ///< rows the minigame table contributed
    int mechanicLevels = 0;  ///< rows the mechanics table contributed (conveyor / gravestone only)

    std::size_t size() const { return levels.size(); }
};

/// How many chips the line may hold; the rest collapse into `+N`.
inline constexpr std::size_t kMaxBadges = 5;

/// Reads `minigames.json` and `level_mechanics.json` from `generatedDir`.
///
/// Never throws and never aborts the screen: a missing or unreadable table leaves `loaded == false`
/// with a `note` explaining why, because a level list without badges is still a working level list.
LevelBadges load(const std::filesystem::path& generatedDir);

/// Same table, named for call sites: `loadBadges(engine::generatedDir())`.
LevelBadges loadBadges(const std::filesystem::path& generatedDir);

/// The badges of one level (empty when the level has none, or when nothing loaded).
const std::vector<LevelBadge>& badgesOf(const LevelBadges& badges, const std::string& levelId);

/// The chips to draw/emit, in fixed order, truncated to `kMaxBadges` — the last entry becomes
/// `+N` when the level has more badges than fit.
std::vector<std::string> badgesFor(const LevelBadges& badges, const std::string& levelId);

/// `a · b · c`; empty string when there is nothing to join.
std::string badgeLine(const std::vector<std::string>& badges);

/// `badgesFor` + `badgeLine`: the exact string the detail panel draws.
std::string badgeSummary(const LevelBadges& badges, const std::string& levelId);

/// kind -> 中文 label; empty when the dictionary does not know the kind.
std::string badgeLabel(const std::string& kind);

/// Whether the simulation runs `kind` today. Unknown kinds are not wired (nothing can run them).
bool badgeWired(const std::string& kind);

/// 中文 label -> kind; empty when the label is not in the dictionary. Used to answer "is this chip
/// wired?" from a chip string alone, which is all `LevelSelectResult` carries into the JSON writer.
std::string badgeKindOfLabel(const std::string& label);

/// The dictionary in display order, as `kind=label` rows. The report and the test read this.
std::vector<std::string> badgeDictionary();

}  // namespace pvz
