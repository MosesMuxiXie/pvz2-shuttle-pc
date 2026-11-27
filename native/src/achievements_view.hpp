#pragma once

// The achievements screen (B4): the 53 rows the OBB carries, and nothing invented about them.
//
// What `native/generated/metagame.json` actually holds (checked, see the B4 report):
//   * 53 entries with `id`, `titleKey`, `descKey`, `serverOnly: true`, `rewards: null`,
//     `rewardSource: "serverOnly"`, and `resolved.*` flags that only say whether a key was
//     found in LawnStrings - the localised text itself lives in the OBB, not in this tree;
//   * no condition, threshold or counter anywhere. `achievements.counts` is 53/53/0 and
//     `unknowns[U4]` says so in words: "成就本地只有 ACHIEVE_* 文案键，没有奖励表".
//
// Two consequences the screen refuses to paper over:
//   1. A row can only show progress the save can actually answer. Three ids name a total we
//      keep (`COWBOY_STARS`, `EGYPT_STARS`, `PIRATE_STARS`); every other row shows `-` rather
//      than a number that would be a guess.
//   2. Every row carries the `server` badge and the footer says, in one sentence, that the
//      server settles these and the client only lists the conditions.
//
// The pure half (model + JSON + paging) has no SDL so `achievements_test` runs in the
// AuditOnly configuration; `renderAchievementsHeadless()` is the desktop half that draws the
// frames and writes the PNG, and it is what the render test and (later) `--achievements` call.

#include "progress.hpp"

#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

namespace pvz::meta {

/// Turns a LawnStrings key into something readable when the text itself is not in this tree:
/// `ACHIEVE_ALL_IN_JEST_TITLE` -> `All In Jest`. Deliberately mechanical - a hand-written title
/// table would be invented data, and the report says so instead.
std::string humanizeGameKey(const std::string& key);

struct AchievementRow {
    std::string id;
    std::string titleKey;
    /// `humanizeGameKey(titleKey)`; never empty (falls back to the id).
    std::string title;
    /// A total the save can answer, or `-` when it cannot.
    std::string progress;
    bool serverOnly = true;
};

struct AchievementsModel {
    std::vector<AchievementRow> rows;
    int serverOnly = 0;
    /// The file that was read, for the JSON and for error messages.
    std::filesystem::path source;

    /// Parses `metagame.json`. Throws `achievements: <path>: <reason>` on a missing file, a
    /// non-object root, an empty `achievements.entries` array, or an entry without `id`/`titleKey`
    /// - a half-read list would silently shrink the screen.
    static AchievementsModel load(const std::filesystem::path& file);
    /// `engine::generatedDir() / "metagame.json"`; throws when the generated tree is not found.
    static AchievementsModel loadShipped();
};

/// Stars the save holds for one world (sum over `levels` whose id starts with `<worldId>_`).
int starsInWorld(const Progress& progress, const std::string& worldId);
/// Cleared levels the save holds for one world, same prefix rule.
int clearedInWorld(const Progress& progress, const std::string& worldId);

/// Fills every row's `progress` from the save. Rule (documented in the B4 report):
/// `*_STARS` -> "<n> 星（<world>）"; everything else -> "-". Nothing else in metagame.json says
/// what an achievement counts, so nothing else can be derived without inventing it.
void applyProgress(AchievementsModel& model, const Progress& progress);

/// One page of a list, with the clamp rules the screen and the JSON share.
struct PageRange {
    int page = 0;   ///< 0-based, clamped into [0, pages-1]
    int pages = 1;  ///< at least 1, so an empty list still has a page 0
    int first = 0;  ///< index of the first row on the page
    int count = 0;  ///< rows on this page

    static PageRange of(int rows, int page, int perPage);
};

/// The layout constants the renderer and the tests share, so a test can point at a row without
/// reading pixels at hard-coded coordinates that the view could drift away from.
struct AchievementsLayout {
    static constexpr float kWidth = 1280.0f;
    static constexpr float kHeight = 720.0f;
    static constexpr int kPerPage = 12;
    static constexpr float kRowLeft = 40.0f;
    static constexpr float kRowTop = 116.0f;
    static constexpr float kRowWidth = 1200.0f;
    static constexpr float kRowHeight = 42.0f;
};

/// `{"screen":"achievements","total":53,"serverOnly":53,"perPage":12,"page":0,"pages":5,
///   "visible":[{"id":..,"title":..,"progress":..,"server":true}, ...]}`
Json achievementsJson(const AchievementsModel& model, const PageRange& range, int perPage);

#ifdef PVZ_ENABLE_DESKTOP
struct AchievementsOptions {
    /// Holds `ui/font_zh.ttc`.
    std::filesystem::path assetRoot;
    /// Optional save; without it every derivable row reads 0.
    std::filesystem::path progressFile;
    /// Optional frame capture: `.png` writes PNG, anything else BMP (the same rule as `--menu`).
    std::filesystem::path snapshot;
    /// >0 renders this many frames headlessly and returns; 0 runs the interactive window.
    int frames = 0;
    /// Which page to open on; clamped by `PageRange::of`.
    int page = 0;
    int perPage = AchievementsLayout::kPerPage;
    /// The screen to open on: metagame.json is shared by both B4 screens.
    std::filesystem::path metagame;
};

/// Draws the screen and returns the same JSON `achievementsJson` produces, so the picture and
/// the wire format cannot disagree. Throws when the font is missing (`...font_zh.ttc` appears in
/// the message) - a screen that silently draws no text is worse than one that refuses to start.
Json renderAchievementsHeadless(const AchievementsModel& model, const AchievementsOptions& options);
#endif

}  // namespace pvz::meta
