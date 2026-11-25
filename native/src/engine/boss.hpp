#pragma once
#include "../catalog.hpp"
#include <cstddef>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

namespace pvz::engine {

/// One action a boss stage runs.
///
/// The sheets carry 34 boss action classes (`counts.actionClassesUsed` in
/// `native/generated/bosses_from_pack.json`). Only the shapes that state a column window
/// - `FireMinColumn` + `FireMaxColumn` - can be executed by this kernel today, so the
/// parser flags those and keeps every other action's fields verbatim for the unwired
/// report. Nothing here throws on an unknown class: a boss with an unwired action still
/// plays its stages.
struct BossStageAction {
    std::string type; // e.g. ZombossFireActionDefinition
    std::string alias;
    std::string rtid;
    /// True when the fields carry `FireMinColumn` and `FireMaxColumn`, i.e. the action
    /// burns a rectangle of the lawn. 58 of the shipped 105 fire-named actions qualify;
    /// the rest (`ZombossDarkFireBreath`, `ZombossDarkLobFireballs`,
    /// `ZombossEightiesFireSpeakerRay`) describe breath/imp effects with no column window
    /// and stay unwired on purpose.
    bool fire = false;
    int fireMinColumn = 0;
    int fireMaxColumn = -1; // inclusive; -1 means "to the last column"
    int fireRowRange = 1;   // rows covered, centred on the boss row
    double fireSpeed = 0;   // FireRocketSpeed, informational
    double fireHitTime = 0; // FireRocketHitTime, informational
    Json fields;            // untouched sheet fields
};

struct BossStage {
    int index = 0;
    double hitPoints = 0;
    double idleMinSeconds = 0;
    double idleMaxSeconds = 0;
    double stunSeconds = 0;
    double animRate = 1;
    std::vector<BossStageAction> actions;
    std::size_t fireActions() const;
    std::size_t unwiredActions() const { return actions.size() - fireActions(); }
};

struct BossSpawnPoint {
    int gridX = 0;
    int gridY = 0;
    int reservedColumns = 0;
    int deathRow = 0;
    int deathColumn = 0;
};

/// One boss the property sheets declare (50 shipped; 49 with at least one stage -
/// `zombossmech_egypt_rift` has an empty `stages` array and is therefore unusable).
struct BossDefinition {
    std::string id;
    std::string className;
    std::string propsName;
    std::string popAnim;
    std::string animRig;
    std::string world; // primary world as the sheet names it
    std::vector<std::string> worlds;
    int stageCount = 0;
    std::vector<BossStage> stages;
    BossSpawnPoint spawn;
    bool usable() const { return !stages.empty(); }
    double totalHitPoints() const;
    /// True when the sheet says this boss belongs to `name` - either as its primary
    /// world or through any `placements[].world`.
    bool claimsWorld(const std::string& name) const;
};

class BossTable {
  public:
    static constexpr const char* kFileName = "bosses_from_pack.json";

    /// Parse a generated table. Every failure throws `boss table: <path>: <reason>`: a
    /// half-loaded table would silently turn a boss level into an ordinary one.
    static BossTable load(const std::filesystem::path& file);
    /// The process-wide table from `generatedDir()`, parsed once.
    static const BossTable& shared();

    bool empty() const { return bosses_.empty(); }
    std::size_t size() const { return bosses_.size(); }
    std::size_t usable() const;
    std::size_t stageTotal() const;
    std::size_t fireActionTotal() const;

    const BossDefinition* find(const std::string& id) const;
    /// Deterministic pick for a world: the boss that claims it, preferring the one whose
    /// primary `world` matches, then the fewest stages, then the lexicographic id. 24 of
    /// the 26 shipped worlds have at least one candidate; `frontyard` and `muji` have none,
    /// which is why four boss-marked levels report `boss_unavailable` instead of guessing.
    const BossDefinition* forWorld(const std::string& world) const;
    std::size_t candidatesForWorld(const std::string& world) const;
    const std::vector<BossDefinition>& bosses() const { return bosses_; }

  private:
    std::vector<BossDefinition> bosses_;
};

/// What a level's `extra` marker resolved to.
struct BossSelection {
    enum class Kind {
        none,       // no marker, or the marker named something the data cannot back
        mechanic,   // `boss_zombie: "zomboss"` resolved to a staged boss
        gargantuar, // `boss_zombie: "gargantuar"` - a zombie type, not a staged mechanic
    };
    Kind kind = Kind::none;
    const BossDefinition* boss = nullptr;
    std::string zombieType; // set for `gargantuar`
    std::string marker;     // raw value of the level's boss marker, "" when absent
    std::size_t candidates = 0;
    bool spawned() const { return kind != Kind::none; }
};

/// Resolve a level's boss.
///
/// Rule, in order:
///  1. `level.extra["boss_zombie"]` (or `extra["boss"]` when that is a string) names the
///     marker. No marker -> `Kind::none` and the world says nothing about bosses.
///  2. A marker other than `zomboss` is a **zombie type** (`gargantuar` on 3 levels): the
///     level gets a normal gargantuar that only carries the boss flag.
///  3. `zomboss` -> the table's pick for `level.world` (see `BossTable::forWorld`). No
///     candidate -> `Kind::none`, and the world records `boss_unavailable`.
BossSelection selectBoss(const Catalog& catalog, const LevelDefinition& level, const BossTable& table);
std::string_view bossSelectionKindName(BossSelection::Kind kind);

} // namespace pvz::engine
