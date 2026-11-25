#include "progress.hpp"

#include <algorithm>
#include <atomic>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <system_error>

#include "engine/entity.hpp"
#include "engine/world.hpp"

namespace pvz {
namespace {

[[noreturn]] void fail(const std::string& origin, const std::string& what) {
  throw std::runtime_error("progress " + origin + ": " + what);
}

std::string readFile(const std::filesystem::path& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    throw std::runtime_error("cannot open " + path.string());
  }
  std::ostringstream out;
  out << in.rdbuf();
  return out.str();
}

double numberOr(const Json& json, const char* key, double fallback) {
  const auto it = json.find(key);
  if (it == json.end() || !it->is_number()) {
    return fallback;
  }
  return it->get<double>();
}

int intOr(const Json& json, const char* key, int fallback) {
  const auto it = json.find(key);
  if (it == json.end() || !it->is_number()) {
    return fallback;
  }
  return static_cast<int>(it->get<double>());
}

std::string stringOr(const Json& json, const char* key) {
  const auto it = json.find(key);
  if (it == json.end() || !it->is_string()) {
    return {};
  }
  return it->get<std::string>();
}

}  // namespace

StarKind starKindOf(const std::string& text) {
  if (text == "beat") {
    return StarKind::beat;
  }
  if (text == "mowers") {
    return StarKind::mowers;
  }
  if (text == "kill") {
    return StarKind::kill;
  }
  if (text == "sun_used") {
    return StarKind::sun_used;
  }
  if (text == "sun_produced") {
    return StarKind::sun_produced;
  }
  if (text == "plants_lost") {
    return StarKind::plants_lost;
  }
  if (text == "time") {
    return StarKind::time_limit;
  }
  return StarKind::unknown;
}

bool starKindIsMeasured(StarKind kind) {
  switch (kind) {
    case StarKind::beat:
    case StarKind::mowers:
    case StarKind::kill:
      return true;
    case StarKind::sun_used:
    case StarKind::sun_produced:
    case StarKind::plants_lost:
    case StarKind::time_limit:
    case StarKind::unknown:
      break;
  }
  return false;
}

const char* starKindName(StarKind kind) {
  switch (kind) {
    case StarKind::beat:
      return "beat";
    case StarKind::mowers:
      return "mowers";
    case StarKind::kill:
      return "kill";
    case StarKind::sun_used:
      return "sun_used";
    case StarKind::sun_produced:
      return "sun_produced";
    case StarKind::plants_lost:
      return "plants_lost";
    case StarKind::time_limit:
      return "time";
    case StarKind::unknown:
      break;
  }
  return "unknown";
}

const std::vector<StarGoal>* StarTable::find(const std::string& levelId) const {
  const auto it = levels.find(levelId);
  return it == levels.end() ? nullptr : &it->second;
}

StarTable parseStarTable(const std::string& text, const std::string& origin) {
  Json json;
  try {
    json = Json::parse(text);
  } catch (const std::exception& error) {
    fail(origin, std::string("not json: ") + error.what());
  }
  if (!json.is_object()) {
    fail(origin, "top level must be an object of level id -> goals");
  }
  StarTable table;
  for (const auto& [levelId, goals] : json.items()) {
    if (!goals.is_array()) {
      fail(origin, "level \"" + levelId + "\" must map to an array of goals");
    }
    std::vector<StarGoal> parsed;
    parsed.reserve(goals.size());
    for (const auto& raw : goals) {
      if (!raw.is_object()) {
        fail(origin, "level \"" + levelId + "\" has a non-object goal");
      }
      StarGoal goal;
      goal.typeText = stringOr(raw, "type");
      if (goal.typeText.empty()) {
        fail(origin, "level \"" + levelId + "\" has a goal without \"type\"");
      }
      goal.kind = starKindOf(goal.typeText);
      if (goal.kind == StarKind::unknown) {
        ++table.unknownKinds;
      }
      goal.value = numberOr(raw, "value", 0.0);
      goal.hasCount = raw.find("count") != raw.end() && raw["count"].is_number();
      goal.count = goal.hasCount ? intOr(raw, "count", 0) : static_cast<int>(goal.value);
      goal.max = numberOr(raw, "max", 0.0);
      goal.target = numberOr(raw, "target", 0.0);
      goal.seconds = numberOr(raw, "seconds", 0.0);
      goal.text = stringOr(raw, "text_zh");
      ++table.byKind[goal.typeText];
      parsed.push_back(std::move(goal));
    }
    table.goals += parsed.size();
    table.levels.emplace(levelId, std::move(parsed));
  }
  if (table.levels.empty()) {
    fail(origin, "no levels in star table");
  }
  return table;
}

StarTable loadStarTable(const std::filesystem::path& path) {
  return parseStarTable(readFile(path), path.string());
}

bool LevelRecord::operator==(const LevelRecord& other) const {
  return cleared == other.cleared && stars == other.stars && attempts == other.attempts &&
         bestTick == other.bestTick && goals == other.goals;
}

int Progress::totalStars() const {
  int sum = 0;
  for (const auto& entry : levels) {
    sum += entry.second.stars;
  }
  return sum;
}

int Progress::clearedLevels() const {
  int sum = 0;
  for (const auto& entry : levels) {
    if (entry.second.cleared) {
      ++sum;
    }
  }
  return sum;
}

const LevelRecord* Progress::find(const std::string& levelId) const {
  const auto it = levels.find(levelId);
  return it == levels.end() ? nullptr : &it->second;
}

BattleOutcome outcomeOf(const engine::World& world) {
  BattleOutcome outcome;
  outcome.won = world.status() == "won";
  outcome.tick = world.tick();
  outcome.sun = static_cast<int>(world.sun());
  outcome.sunSpent = static_cast<int>(world.sunSpent());
  outcome.mowersLeft = world.mowersLeft();
  outcome.zombiesKilled = static_cast<int>(world.killedZombies());
  outcome.plantsLost = world.plantsLost();
  return outcome;
}

StarOutcome evaluateStars(const std::vector<StarGoal>& goals, const BattleOutcome& outcome) {
  StarOutcome result;
  result.passed.reserve(goals.size());
  for (const auto& goal : goals) {
    bool passed = false;
    switch (goal.kind) {
      case StarKind::beat:
        passed = outcome.won;
        break;
      case StarKind::mowers:
        passed = outcome.mowersLeft >= static_cast<int>(goal.value);
        break;
      case StarKind::kill:
        passed = outcome.zombiesKilled >= goal.count;
        break;
      case StarKind::sun_used:
      case StarKind::sun_produced:
      case StarKind::plants_lost:
      case StarKind::time_limit:
        // The engine keeps no sun-spend / sun-production / plant-loss /
        // wall-clock counters yet, so these goals cannot be judged. Reporting
        // them as failed (with `starKindIsMeasured == false`) is honest: the UI
        // shows them as 未统计 instead of unmet, and nothing silently passes.
        //
        // S6 note: `BattleOutcome` now carries `sunSpent` and `plantsLost`, but
        // flipping these two kinds on would change the star total of 67 levels
        // without a decision from the design owner, so they stay unmeasured here
        // and are reported as such in docs/reviews/2026-11-21-s6-progress.md.
        passed = false;
        break;
      case StarKind::unknown:
        passed = false;
        break;
    }
    result.passed.push_back(passed);
    if (passed) {
      ++result.stars;
    }
  }
  return result;
}

StarOutcome evaluateStars(const std::vector<StarGoal>& goals, const engine::World& world) {
  // One definition of the rules: the world is only a source of the recorded numbers.
  return evaluateStars(goals, outcomeOf(world));
}

Progress parseProgress(const Json& json, const std::string& origin) {
  if (!json.is_object()) {
    fail(origin, "top level must be an object");
  }
  Progress progress;
  progress.version = intOr(json, "version", 1);
  progress.updated = static_cast<std::int64_t>(numberOr(json, "updated", 0.0));
  progress.keys = intOr(json, "keys", 0);
  progress.coins = intOr(json, "coins", 0);
  progress.gems = intOr(json, "gems", 0);
  progress.mowers = intOr(json, "mowers", 0);
  progress.xp = intOr(json, "xp", 0);
  progress.plantfoodSlots = intOr(json, "plantfoodSlots", 0);
  progress.plantfoodRefresh = json.value("plantfoodRefresh", false);
  if (const auto costumes = json.find("costumes");
      costumes != json.end() && costumes->is_array()) {
    for (const Json& entry : *costumes) {
      if (!entry.is_string()) continue;
      const std::string id = entry.get<std::string>();
      if (id.empty()) continue;
      progress.costumes.push_back(id);
    }
    std::sort(progress.costumes.begin(), progress.costumes.end());
    progress.costumes.erase(std::unique(progress.costumes.begin(), progress.costumes.end()),
                            progress.costumes.end());
  }
  if (const auto settings = json.find("settings");
      settings != json.end() && settings->is_object()) {
    for (const auto& [name, value] : settings->items()) {
      if (name.empty()) continue;
      // Only scalar switches survive: a nested object in the settings block is not something
      // this client wrote, and copying it through would launder unknown data into the save.
      if (value.is_boolean() || value.is_number() || value.is_string()) {
        progress.settings.emplace(name, value);
      }
    }
  }
  if (const auto purchases = json.find("purchases");
      purchases != json.end() && purchases->is_array()) {
    for (const Json& entry : *purchases) {
      if (entry.is_string()) {
        progress.purchases.push_back(entry.get<std::string>());
      }
    }
    std::sort(progress.purchases.begin(), progress.purchases.end());
  }

  // lastLevel is a top-level field, not part of `seeds`. It used to sit inside the seeds
  // branch, so a save without a `seeds` key silently lost the continue pointer — and
  // saveProgress always writes `seeds`, which is why a round-trip test could not see it.
  if (const auto last = json.find("lastLevel"); last != json.end() && last->is_string()) {
    progress.lastLevel = last->get<std::string>();
  }

  if (const auto seeds = json.find("seeds"); seeds != json.end() && seeds->is_array()) {
    for (const Json& entry : *seeds) {
      if (!entry.is_string()) continue;
      const std::string id = entry.get<std::string>();
      if (id.empty()) continue;
      progress.seeds.push_back(id);
    }
    std::sort(progress.seeds.begin(), progress.seeds.end());
    progress.seeds.erase(std::unique(progress.seeds.begin(), progress.seeds.end()),
                         progress.seeds.end());
  }
  if (const auto trophies = json.find("trophies");
      trophies != json.end() && trophies->is_array()) {
    for (const Json& entry : *trophies) {
      if (!entry.is_string()) continue;
      const std::string id = entry.get<std::string>();
      if (id.empty()) continue;
      progress.trophies.push_back(id);
    }
    std::sort(progress.trophies.begin(), progress.trophies.end());
    progress.trophies.erase(std::unique(progress.trophies.begin(), progress.trophies.end()),
                            progress.trophies.end());
  }
  const auto levels = json.find("levels");
  if (levels != json.end()) {
    if (!levels->is_object()) {
      fail(origin, "\"levels\" must be an object");
    }
    for (const auto& [levelId, raw] : levels->items()) {
      if (!raw.is_object()) {
        fail(origin, "level \"" + levelId + "\" must be an object");
      }
      LevelRecord record;
      record.cleared = raw.value("cleared", false);
      record.stars = intOr(raw, "stars", 0);
      record.attempts = intOr(raw, "attempts", 0);
      record.bestTick = static_cast<std::uint64_t>(numberOr(raw, "bestTick", 0.0));
      const auto goals = raw.find("goals");
      if (goals != raw.end() && goals->is_array()) {
        for (const auto& flag : *goals) {
          record.goals.push_back(flag.is_boolean() && flag.get<bool>());
        }
      }
      progress.levels.emplace(levelId, std::move(record));
    }
  }
  return progress;
}

Progress loadProgress(const std::filesystem::path& path) {
  std::error_code error;
  if (!std::filesystem::exists(path, error) || error) {
    return Progress{};
  }
  const auto text = readFile(path);
  if (text.find_first_not_of(" \t\r\n") == std::string::npos) {
    return Progress{};
  }
  Json json;
  try {
    json = Json::parse(text);
  } catch (const std::exception& failure) {
    fail(path.string(), std::string("not json: ") + failure.what());
  }
  return parseProgress(json, path.string());
}

Json progressToJson(const Progress& progress) {
  Json json = Json::object();
  json["version"] = progress.version;
  json["updated"] = progress.updated;
  json["keys"] = progress.keys;
  json["coins"] = progress.coins;
  // The five fields below are written only when they differ from the default. A player who has
  // never bought a shop row keeps a byte-identical save, which is what lets the existing
  // round-trip and snapshot tests keep comparing whole files.
  if (progress.gems != 0) {
    json["gems"] = progress.gems;
  }
  if (progress.mowers != 0) {
    json["mowers"] = progress.mowers;
  }
  if (progress.xp != 0) {
    json["xp"] = progress.xp;
  }
  if (progress.plantfoodSlots != 0) {
    json["plantfoodSlots"] = progress.plantfoodSlots;
  }
  if (progress.plantfoodRefresh) {
    json["plantfoodRefresh"] = true;
  }
  if (!progress.costumes.empty()) {
    Json costumes = Json::array();
    for (const std::string& id : progress.costumes) {
      costumes.push_back(id);
    }
    json["costumes"] = std::move(costumes);
  }
  if (!progress.settings.empty()) {
    Json settings = Json::object();
    for (const auto& [name, value] : progress.settings) {
      settings[name] = value;
    }
    json["settings"] = std::move(settings);
  }
  Json purchases = Json::array();
  for (const std::string& id : progress.purchases) {
    purchases.push_back(id);
  }
  json["purchases"] = std::move(purchases);

  Json seeds = Json::array();
  for (const std::string& id : progress.seeds) {
    seeds.push_back(id);
  }
  json["seeds"] = std::move(seeds);
  if (!progress.trophies.empty()) {
    Json trophies = Json::array();
    for (const std::string& id : progress.trophies) {
      trophies.push_back(id);
    }
    json["trophies"] = std::move(trophies);
  }
  if (!progress.lastLevel.empty()) {
    json["lastLevel"] = progress.lastLevel;
  }
  Json levels = Json::object();
  for (const auto& [levelId, record] : progress.levels) {
    Json entry = Json::object();
    entry["cleared"] = record.cleared;
    entry["stars"] = record.stars;
    entry["attempts"] = record.attempts;
    entry["bestTick"] = record.bestTick;
    Json goals = Json::array();
    for (const bool hit : record.goals) {
      goals.push_back(hit);
    }
    entry["goals"] = std::move(goals);
    levels[levelId] = std::move(entry);
  }
  json["levels"] = std::move(levels);
  return json;
}

void saveProgress(const std::filesystem::path& path, Progress progress, std::int64_t now) {
  progress.updated = now;
  const auto parent = path.parent_path();
  if (!parent.empty()) {
    std::error_code error;
    std::filesystem::create_directories(parent, error);
  }
  // A distinct staging name per call keeps two saves from truncating each
  // other's temporary file.
  static std::atomic<unsigned> counter{0};
  auto staging = std::filesystem::path(path);
  staging += ".tmp" + std::to_string(static_cast<unsigned long>(counter.fetch_add(1)));
  {
    std::ofstream out(staging, std::ios::binary | std::ios::trunc);
    if (!out) {
      throw std::runtime_error("cannot write " + staging.string());
    }
    out << progressToJson(progress).dump(1, ' ') << "\n";
    if (!out) {
      throw std::runtime_error("cannot finish writing " + staging.string());
    }
  }
  std::error_code error;
  std::filesystem::rename(staging, path, error);
  if (error) {
    std::error_code ignored;
    std::filesystem::remove(staging, ignored);
    throw std::runtime_error("cannot replace " + path.string() + ": " + error.message());
  }
}

namespace {

/// The one place a finished attempt is folded into a save. Both `recordAttempt` (which
/// takes a live world) and `recordBattle` (which takes a recorded outcome) go through here,
/// so "stars never regress" and "attempts always increase" cannot drift apart.
void foldAttempt(Progress& progress, const std::string& levelId, const StarOutcome& outcome,
                 const BattleOutcome& attempt) {
  // Win or lose, this is now the level the player was on; "continue" starts here.
  progress.lastLevel = levelId;
  LevelRecord& record = progress.levels[levelId];
  if (record.goals.size() < outcome.passed.size()) {
    record.goals.resize(outcome.passed.size(), false);
  }
  for (std::size_t index = 0; index < outcome.passed.size(); ++index) {
    // A star never goes away: a later sloppy win must not erase an earlier
    // clean one.
    record.goals[index] = record.goals[index] || outcome.passed[index];
  }
  int stars = 0;
  for (const bool hit : record.goals) {
    if (hit) {
      ++stars;
    }
  }
  record.stars = stars;
  record.attempts += 1;
  if (attempt.won) {
    record.cleared = true;
    if (record.bestTick == 0 || attempt.tick < record.bestTick) {
      record.bestTick = attempt.tick;
    }
  }
}

}  // namespace

Progress recordAttempt(Progress progress, const std::string& levelId,
                       const std::vector<StarGoal>& goals, const engine::World& world) {
  const auto attempt = outcomeOf(world);
  foldAttempt(progress, levelId, evaluateStars(goals, attempt), attempt);
  return progress;
}

void recordBattle(Progress& progress, const std::string& levelId, const BattleOutcome& outcome,
                  const StarTable& table) {
  // A level the star table does not know still records its attempt: dropping it would make a
  // played level look unplayed. Its goal list is simply empty, so it can earn no stars.
  static const std::vector<StarGoal> noGoals;
  const auto* goals = table.find(levelId);
  foldAttempt(progress, levelId, evaluateStars(goals != nullptr ? *goals : noGoals, outcome),
              outcome);
}

Json progressReport(const Progress& progress, const StarTable& table) {
  Json levels = Json::object();
  for (const auto& [levelId, record] : progress.levels) {
    Json entry = Json::object();
    entry["cleared"] = record.cleared;
    entry["stars"] = record.stars;
    entry["attempts"] = record.attempts;
    entry["bestTick"] = record.bestTick;
    const auto* goals = table.find(levelId);
    entry["target"] = goals != nullptr ? static_cast<int>(goals->size()) : 0;
    Json flags = Json::array();
    for (const bool hit : record.goals) {
      flags.push_back(hit);
    }
    entry["goals"] = std::move(flags);
    levels[levelId] = std::move(entry);
  }
  Json report = Json::object();
  report["totalStars"] = progress.totalStars();
  report["cleared"] = progress.clearedLevels();
  report["levels"] = std::move(levels);
  return report;
}

}  // namespace pvz
