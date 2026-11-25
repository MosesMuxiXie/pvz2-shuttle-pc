// Progress model tests: star tables from the content pack, star evaluation
// against a finished battle, and the save file round trip.
//
// Skeleton of every other native test: `check()` throws on the first failure so
// the CTest log names the exact assertion instead of a bare exit code.
#include <filesystem>
#include <memory>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

#include "catalog.hpp"
#include "engine/replay.hpp"
#include "engine/world.hpp"
#include "progress.hpp"

namespace fs = std::filesystem;
using namespace pvz;

namespace {

void check(bool condition, const std::string& message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

std::string readText(const fs::path& path) {
  std::ifstream in(path, std::ios::binary);
  check(static_cast<bool>(in), "cannot open " + path.string());
  return std::string(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
}

fs::path freshDir(const fs::path& root, const char8_t* name) {
  const auto dir = root / fs::path(name);
  std::error_code error;
  fs::remove_all(dir, error);
  fs::create_directories(dir, error);
  return dir;
}

/// beach_23 has a single zombie: five peashooters on row 2 win it in 1538 ticks.
/// `World` is neither copyable nor movable, so the helper hands out ownership.
std::unique_ptr<engine::World> wonBeach23(const Catalog& catalog, const fs::path& scripts) {
  const auto found = catalog.levels.find("beach_23");
  check(found != catalog.levels.end(), "beach_23 must exist");
  auto world = std::make_unique<engine::World>(catalog, found->second, 1);
  const auto script = engine::loadScript(scripts / "beach_23_win.json");
  engine::runScript(*world, script, 120.0);
  check(world->status() == "won", "the reference script must win beach_23, got " + world->status());
  return world;
}

void testStarTable(const fs::path& content) {
  const auto table = loadStarTable(content / "stars.json");
  check(table.levels.size() == 1809, "star table must cover 1809 levels");
  check(table.goals == 5427, "star table must hold 5427 goals, got " + std::to_string(table.goals));
  check(table.unknownKinds == 0, "no goal kind may be unknown");
  check(table.byKind.at("beat") == 1808, "beat goals must be 1808");
  check(table.byKind.at("mowers") == 1784, "mowers goals must be 1784");
  check(table.byKind.at("kill") == 1702, "kill goals must be 1702");
  check(table.byKind.at("sun_used") == 31, "sun_used goals must be 31");
  check(table.byKind.at("sun_produced") == 61, "sun_produced goals must be 61");
  check(table.byKind.at("plants_lost") == 36, "plants_lost goals must be 36");
  check(table.byKind.at("time") == 5, "time goals must be 5");

  const auto* beach = table.find("beach_23");
  check(beach != nullptr && beach->size() == 3, "beach_23 must ship three goals");
  check((*beach)[0].kind == StarKind::beat, "first beach_23 goal must be beat");
  check((*beach)[1].kind == StarKind::mowers && (*beach)[1].value == 5.0,
        "the shipped mower goal asks for five survivors");
  check((*beach)[2].kind == StarKind::kill && (*beach)[2].count == 10,
        "third beach_23 goal must be a ten kill goal");
  check(!(*beach)[2].text.empty(), "goal text must survive parsing");
}

void testStarEvaluation(const Catalog& catalog, const fs::path& content, const fs::path& scripts) {
  const auto table = loadStarTable(content / "stars.json");
  const auto* goals = table.find("beach_23");
  check(goals != nullptr, "beach_23 goals must exist");
  const auto world = wonBeach23(catalog, scripts);

  const auto outcome = evaluateStars(*goals, *world);
  check(outcome.passed.size() == 3, "every goal must be evaluated");
  check(outcome.passed[0], "beat must pass after a win");
  check(outcome.passed[1], "no mower was used, so the mower goal must pass");
  // beach_23 ships one zombie but its kill goal asks for ten: the goal is
  // unreachable by the content itself, so a clean win must award two stars, and
  // the model has to say so instead of quietly rounding up.
  check(!outcome.passed[2], "a ten kill goal cannot pass on a one zombie level");
  check(outcome.stars == 2, "a clean win on beach_23 must award two stars");

  // A goal the engine cannot measure is reported as failed, never as passed.
  std::vector<StarGoal> unmeasured;
  StarGoal sunGoal;
  sunGoal.kind = StarKind::sun_used;
  sunGoal.typeText = "sun_used";
  sunGoal.value = 50.0;
  unmeasured.push_back(sunGoal);
  check(!starKindIsMeasured(StarKind::sun_used), "sun_used must be marked unmeasured");
  check(!evaluateStars(unmeasured, *world).passed[0], "an unmeasured goal must not pass");

  // A kill goal above what happened fails: 20 kills are not in this level.
  std::vector<StarGoal> tooMany;
  StarGoal kill;
  kill.kind = StarKind::kill;
  kill.typeText = "kill";
  kill.count = 20;
  kill.hasCount = true;
  tooMany.push_back(kill);
  check(!evaluateStars(tooMany, *world).passed[0], "a 20 kill goal cannot pass on one zombie");
}

void testProgressRoundTrip(const fs::path& temp) {
  const auto dir = freshDir(temp, u8"progress 测试");
  const auto path = dir / fs::path(u8"存档") / "progress.json";
  Progress progress;
  progress.keys = 3;
  progress.coins = 1250;
  LevelRecord record;
  record.cleared = true;
  record.stars = 2;
  record.attempts = 4;
  record.bestTick = 1538;
  record.goals = {true, true, false};
  progress.levels["beach_23"] = record;
  progress.lastLevel = "beach_23";

  saveProgress(path, progress, 1700000000);
  check(fs::exists(path), "save must create the file and its directories");
  check(!fs::exists(path.string() + ".tmp0"), "the staging file must be gone after a save");

  const auto loaded = loadProgress(path);
  check(loaded.keys == 3 && loaded.coins == 1250, "scalars must survive the round trip");
  check(loaded.updated == 1700000000, "save must stamp the clock passed in");
  const auto* back = loaded.find("beach_23");
  check(back != nullptr, "the level record must survive the round trip");
  check(*back == record, "the level record must come back unchanged");
  check(loaded.totalStars() == 2 && loaded.clearedLevels() == 1, "aggregates must match");
  check(loaded.lastLevel == "beach_23", "the continue pointer must survive the round trip");

  // A save written by an older client has no seeds key. lastLevel must still parse:
  // saveProgress always writes seeds, so only a hand-written (or legacy) file catches this.
  const auto legacy = dir / "legacy.json";
  {
    std::ofstream out(legacy, std::ios::binary);
    out << R"({"version":1,"updated":1,"keys":0,"coins":0,"lastLevel":"beach_7","levels":{}})";
  }
  check(loadProgress(legacy).lastLevel == "beach_7",
        "a save without a seeds key must still carry lastLevel");

  // A missing file is a fresh start, not an error.
  const auto missing = loadProgress(dir / "nowhere.json");
  check(missing.levels.empty() && missing.keys == 0, "a missing save must load as a fresh start");

  // Corrupted JSON must surface as an error instead of being replaced.
  const auto broken = dir / "broken.json";
  std::ofstream(broken) << "{ not json";
  bool threw = false;
  std::string message;
  try {
    (void)loadProgress(broken);
  } catch (const std::exception& error) {
    threw = true;
    message = error.what();
  }
  check(threw, "a corrupted save must not load silently");
  check(message.find("progress") != std::string::npos && message.find("not json") != std::string::npos,
        "the error must say what failed: " + message);
}

void testRecordAttempt(const Catalog& catalog, const fs::path& content, const fs::path& scripts) {
  const auto table = loadStarTable(content / "stars.json");
  const auto* goals = table.find("beach_23");
  check(goals != nullptr, "beach_23 goals must exist");
  const auto world = wonBeach23(catalog, scripts);

  Progress progress;
  progress = recordAttempt(progress, "beach_23", *goals, *world);
  auto* record = progress.levels.find("beach_23") != progress.levels.end()
                     ? &progress.levels.at("beach_23")
                     : nullptr;
  check(record != nullptr, "an attempt must create the level record");
  check(record->cleared && record->stars == 2 && record->attempts == 1, "first win must be two stars");
  check(record->bestTick == world->tick(), "best tick must record the win tick");

  // Record a worse attempt: stars and best tick must not regress.
  Progress again = progress;
  LevelRecord manual;
  manual.goals = {true, false, false};
  manual.stars = 1;
  manual.attempts = 1;  // the earlier attempt that earned the single star
  again.levels["beach_23"] = manual;
  const auto folded = recordAttempt(again, "beach_23", *goals, *world);
  const auto* foldedRecord = folded.find("beach_23");
  check(foldedRecord != nullptr, "record must exist after folding");
  check(foldedRecord->stars == 2, "a later win must not lose the stars of an earlier one");
  check(foldedRecord->attempts == 2, "attempts must count every play");
  check(foldedRecord->cleared, "cleared must stay true");
}

/// Pins a content defect: some levels ask for more kills than their waves can
/// ever deliver, which would make one star permanently unreachable. The count is
/// asserted so the number cannot drift without a deliberate update here.
void testStarGoalsReachable(const Catalog& catalog, const fs::path& content) {
  const auto table = loadStarTable(content / "stars.json");
  int unreachable = 0;
  std::string first;
  for (const auto& entry : catalog.levels) {
    const auto* goals = table.find(entry.first);
    if (goals == nullptr) {
      continue;
    }
    std::size_t zombies = 0;
    for (const auto& wave : entry.second.waves) {
      zombies += wave.zombies.size();
    }
    for (const auto& goal : *goals) {
      if (goal.kind != StarKind::kill) {
        continue;
      }
      if (static_cast<std::size_t>(goal.count) > zombies) {
        ++unreachable;
        if (first.empty()) {
          first = entry.first;
        }
      }
    }
  }
  check(unreachable == 67,
        "67 kill goals ask for more zombies than the level spawns, got " + std::to_string(unreachable));
  check(first == "beach_2", "the first unreachable kill goal must be beach_2, got " + first);
}

/// S6.0: the world-map adapter. `outcomeOf` reads public getters only, `recordBattle` folds
/// the outcome into a save, and `progressReport` is the JSON the CLI prints.
///
/// beach_23 ships three goals — beat, mowers, kill 10 — and its single wave holds one zombie,
/// so the kill goal is genuinely unreachable there (content defect C35, counted by
/// `testStarGoalsReachable`). A scripted win is therefore worth exactly two stars.
void testBattleOutcomeAdapter(const Catalog& catalog, const fs::path& content,
                              const fs::path& scripts, const fs::path& temp) {
  const auto table = loadStarTable(content / "stars.json");
  const auto world = wonBeach23(catalog, scripts);

  const auto outcome = outcomeOf(*world);
  check(outcome.won, "a won world must report won=true");
  check(outcome.tick == world->tick(), "the outcome must carry the world tick");
  check(outcome.sun == world->sun(), "the outcome must carry the sun bank");
  check(outcome.sunSpent == static_cast<int>(world->sunSpent()), "sunSpent must come from the world");
  check(outcome.mowersLeft == world->mowersLeft(), "mowersLeft must come from the world");
  check(outcome.zombiesKilled == world->killedZombies(), "zombiesKilled must come from the world");
  check(outcome.plantsLost == world->plantsLost(), "plantsLost must come from the world");
  // Every charge is counted, not just the last one: five peashooters at 100 sun each.
  check(outcome.sunSpent == 500, "five peashooters must have cost 500 sun, got " +
                                     std::to_string(outcome.sunSpent));
  check(outcome.sun == 50, "beach_23 starts at 550 sun and spends 500, got " + std::to_string(outcome.sun));
  check(outcome.mowersLeft == 5, "beach_23 must still hold five mowers, got " +
                                     std::to_string(outcome.mowersLeft));
  check(outcome.plantsLost == 0, "the reference script must not lose a plant");
  check(outcome.zombiesKilled == 1, "the level spawns one zombie, got " +
                                        std::to_string(outcome.zombiesKilled));

  // The save lives under a non-ASCII directory, the shape a Chinese install would use.
  const auto dir = freshDir(temp, u8"S6 进度");
  const auto path = dir / fs::path(u8"存档") / "progress.json";
  Progress progress;
  recordBattle(progress, "beach_23", outcome, table);

  const auto* record = progress.find("beach_23");
  check(record != nullptr, "recordBattle must create the level record");
  check(record->cleared, "a win must mark the level cleared");
  check(record->stars == 2, "beat and mowers pass, kill 10 cannot over one zombie: expected 2 stars, got " +
                                std::to_string(record->stars));
  check(record->attempts == 1, "one attempt was played");
  check(record->bestTick == outcome.tick, "bestTick must record the winning tick");
  check(record->goals.size() == 3, "the record must keep one flag per goal");
  check(record->goals[0] && record->goals[1], "beat and mowers must pass");
  check(!record->goals[2], "the kill-10 goal must stay unmet: the level spawns one zombie");

  const auto report = progressReport(progress, table);
  check(report.at("totalStars") == 2, "the report must total two stars");
  check(report.at("cleared") == 1, "the report must clear one level");
  const auto& row = report.at("levels").at("beach_23");
  check(row.at("target") == 3, "beach_23 ships three goals");
  check(row.at("stars") == 2, "the level row must say two stars");

  // Write and read back through the real save path, including its parent directories.
  saveProgress(path, progress, 1700000000);
  const auto loaded = loadProgress(path);
  const auto* back = loaded.find("beach_23");
  check(back != nullptr, "the save must load back from the non-ASCII path");
  check(*back == *record, "the record must survive the round trip");
  check(progressReport(loaded, table) == report, "the report must be stable across a reload");
}

/// The same level played again. A loss is an attempt — but it must not cost stars, must not
/// un-clear the level and must not become the "best" run; only a win can move `bestTick`,
/// and then only downwards.
void testRecordBattleKeepsTheBestRun(const Catalog& catalog, const fs::path& content,
                                     const fs::path& scripts) {
  const auto table = loadStarTable(content / "stars.json");
  const auto world = wonBeach23(catalog, scripts);
  const auto win = outcomeOf(*world);

  Progress progress;
  recordBattle(progress, "beach_23", win, table);
  const auto* first = progress.find("beach_23");
  check(first != nullptr && first->stars == 2 && first->attempts == 1, "the first win must set the record");

  BattleOutcome loss;
  loss.won = false;
  loss.tick = win.tick - 500;  // deliberately "faster": a loss is still not a best run
  loss.sun = 0;
  loss.sunSpent = 100;
  loss.mowersLeft = 4;
  loss.zombiesKilled = 0;
  loss.plantsLost = 1;
  recordBattle(progress, "beach_23", loss, table);

  const auto* afterLoss = progress.find("beach_23");
  check(afterLoss != nullptr, "the record must survive a loss");
  check(afterLoss->cleared, "a loss must not un-clear the level");
  check(afterLoss->stars == 2, "a loss must not cost stars, got " + std::to_string(afterLoss->stars));
  check(afterLoss->attempts == 2, "a loss is still an attempt, got " + std::to_string(afterLoss->attempts));
  check(afterLoss->bestTick == win.tick, "a loss must never become the best tick, got " +
                                             std::to_string(afterLoss->bestTick));

  BattleOutcome faster = win;
  faster.tick = win.tick - 300;
  recordBattle(progress, "beach_23", faster, table);
  const auto* afterFast = progress.find("beach_23");
  check(afterFast != nullptr, "the record must exist after the faster win");
  check(afterFast->bestTick == faster.tick, "a faster win must lower bestTick to " +
                                                std::to_string(faster.tick));
  check(afterFast->attempts == 3, "attempts must count every play, got " +
                                      std::to_string(afterFast->attempts));
  check(afterFast->stars == 2, "a faster win must not change the stars");

  // A level the star table does not know still records the attempt instead of vanishing.
  BattleOutcome unknown;
  unknown.won = true;
  unknown.tick = 42;
  recordBattle(progress, "not_a_level", unknown, table);
  const auto* odd = progress.find("not_a_level");
  check(odd != nullptr && odd->attempts == 1, "an unknown level must still record its attempt");
  check(odd->stars == 0 && odd->goals.empty(), "an unknown level has no goals to pass");
  const auto report = progressReport(progress, table);
  check(report.at("levels").at("not_a_level").at("target") == 0, "an unknown level has target 0");
}

/// A damaged save must survive a failed load byte for byte: `loadProgress` throws instead of
/// quietly starting a new game, and it never rewrites the file it could not parse.
void testDamagedSaveIsLeftAlone(const fs::path& temp) {
  const auto dir = freshDir(temp, u8"损坏 存档");
  const auto path = dir / fs::path(u8"进度") / "progress.json";
  Progress progress;
  progress.keys = 2;
  progress.levels["beach_23"].stars = 2;
  progress.levels["beach_23"].cleared = true;
  saveProgress(path, progress, 1700000001);
  check(loadProgress(path).find("beach_23") != nullptr, "the intact save must load first");

  // JSON-looking but truncated: parses far enough to be plausible, then fails.
  {
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    check(static_cast<bool>(out), "cannot rewrite the save for the damage test");
    out << R"({"version":1,"levels":{"beach_23":{"stars":)";
  }
  const auto before = readText(path);
  bool threw = false;
  std::string message;
  try {
    (void)loadProgress(path);
  } catch (const std::exception& error) {
    threw = true;
    message = error.what();
  }
  check(threw, "a truncated save must not load silently");
  check(message.find("progress") != std::string::npos, "the error must name the save: " + message);
  check(readText(path) == before, "a failed load must leave the damaged file untouched");
}

}  // namespace


int wmain(int argc, wchar_t** argv) {
  try {
    check(argc >= 4, "usage: progress_test <content> <temp> <scripts>");
    const fs::path content(argv[1]);
    const fs::path temp(argv[2]);
    const fs::path scripts(argv[3]);
    const auto catalog = loadCatalog(content);

    testStarTable(content);
    testStarEvaluation(catalog, content, scripts);
    testProgressRoundTrip(temp);
    testRecordAttempt(catalog, content, scripts);
    testStarGoalsReachable(catalog, content);
    // S6.0: World -> BattleOutcome -> save -> report, plus the damaged-save guarantee.
    testBattleOutcomeAdapter(catalog, content, scripts, temp);
    testRecordBattleKeepsTheBestRun(catalog, content, scripts);
    testDamagedSaveIsLeftAlone(temp);

    std::cout << "progress tests passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "progress test failed: " << error.what() << "\n";
    return 1;
  }
}
