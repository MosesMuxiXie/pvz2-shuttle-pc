#pragma once

// The daily challenges screen (B4): the 11 `quests.daily` rows from
// `native/generated/metagame.json`, shown with the schedule fields that file actually carries.
//
// What the sheet says, and what it does not (checked, see the B4 report):
//   * 11 entries, all `category/slot = DailyActivities`, all `Repeatable: true`;
//   * the only scheduling field is `params.Disabled` (false on all 11 today). There is no date,
//     no start/end time, no rotation index - so "open" is `Disabled == false` and nothing more;
//   * `quests.tabs` carries the two page tabs (`DailyActivities`, `EpicQuests`); only the first
//     tab is what this screen lists, the second is the epic tree and out of scope;
//   * no quest names a level id. `targetType` is the closest thing ("BeatXAdventureLevels…"),
//     and one of the eleven (`PLAY_LEVEL_OF_THE_DAY_DQ`) is about a daily level whose id the
//     sheet never writes. The screen shows the target type and the report says why.
//
// Rewards: `rewards[]` is `{type, amount, subtype}`; the types in the sheet are `coins`, `gems`
// and `mints`. Only `coins` has somewhere to go locally (`Progress::coins`), so `payable` is
// true only when every row of the reward list is coins - the same gem/mint line the shop drew
// in B1-9 (`unmodelledCurrency = 479`) and for the same reason.

#include "achievements_view.hpp"  // PageRange, humanizeGameKey
#include "progress.hpp"

#include <filesystem>
#include <string>
#include <vector>

namespace pvz::meta {

struct DailyRow {
    std::string id;
    std::string titleKey;
    std::string title;
    /// The sheet's target class (`BeatXAdventureLevelsQuestData`, ...); never empty.
    std::string targetType;
    /// `"2000 金币"`, `"10 宝石 + 1 金币"`, or `-` when the entry carries no reward.
    std::string reward;
    /// True only when every reward currency can be paid into `Progress` today (coins).
    bool payable = false;
    bool open = true;
    /// Why the row is closed; empty when open.
    std::string reason;
};

struct DailyModel {
    std::vector<DailyRow> rows;
    int open = 0;
    /// `quests.tabs` length (2 in this data): reported so the screen cannot pretend the epic
    /// tab does not exist.
    int tabs = 0;
    std::filesystem::path source;

    /// Parses `metagame.json`. Throws `daily: <path>: <reason>` on a missing file, a non-object
    /// root, a non-array `quests.daily`, or an entry without `id`/`nameKey`/`targetType`.
    static DailyModel load(const std::filesystem::path& file);
    static DailyModel loadShipped();
};

struct DailyLayout {
    static constexpr float kWidth = 1280.0f;
    static constexpr float kHeight = 720.0f;
    static constexpr int kPerPage = 12;
    static constexpr float kRowLeft = 40.0f;
    static constexpr float kRowTop = 116.0f;
    static constexpr float kRowWidth = 1200.0f;
    static constexpr float kRowHeight = 42.0f;
};

/// `{"screen":"daily","total":11,"open":11,"tabs":2,"perPage":12,"page":0,"pages":1,
///   "visible":[{"id":..,"title":..,"target":..,"reward":..,"open":true,"payable":false}, ...]}`
Json dailyJson(const DailyModel& model, const PageRange& range, int perPage);

#ifdef PVZ_ENABLE_DESKTOP
struct DailyOptions {
    /// Holds `ui/font_zh.ttc`.
    std::filesystem::path assetRoot;
    /// Optional frame capture; `.png` writes PNG, anything else BMP.
    std::filesystem::path snapshot;
    /// >0 renders this many frames headlessly and returns; 0 runs the interactive window.
    int frames = 0;
    int page = 0;
    int perPage = DailyLayout::kPerPage;
};

/// Draws the screen and returns `dailyJson`, so the picture and the wire format cannot disagree.
Json renderDailyHeadless(const DailyModel& model, const DailyOptions& options);
#endif

}  // namespace pvz::meta
