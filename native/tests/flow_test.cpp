// S4 loop tests: the seam between the three screens, not the combat.
//
// A real session is menu -> world map -> level -> battle -> result -> back to the map.
// Everything that can go wrong in that seam lives here: which level "continue" means,
// what a finished battle writes into the save, and whether the *next* run picks up the
// following level instead of replaying the one just finished.
//
// No SDL and no window, so this runs in the audit configuration next to the other
// headless tests. The desktop screens call the very same pick, so a disagreement
// between "continue" on screen and a scripted `--flow` cannot hide here.
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "catalog.hpp"
#include "engine/replay.hpp"
#include "flow.hpp"
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

void writeText(const fs::path& path, const std::string& text) {
  std::ofstream out(path, std::ios::binary | std::ios::trunc);
  check(static_cast<bool>(out), "cannot write " + path.string());
  out << text;
}

fs::path freshDir(const fs::path& root, const char8_t* name) {
  const auto dir = root / fs::path(name);
  std::error_code error;
  fs::remove_all(dir, error);
  fs::create_directories(dir, error);
  return dir;
}

/// A save that already holds a finished level, built in memory and written by the
/// production writer, so the reader has to accept exactly what the game writes.
Progress saveWith(const Catalog& catalog, const std::string& world, std::size_t finished, int stars) {
  Progress progress;
  const auto levels = levelsOfWorld(catalog, world);
  check(levels.size() >= finished, "the world must hold at least " + std::to_string(finished) + " levels");
  for (std::size_t i = 0; i < finished; ++i) {
    LevelRecord record;
    record.cleared = true;
    record.stars = stars;
    record.attempts = 1;
    record.bestTick = 1500;
    // A save written by a real win stores the goals it hit; `progressReport` counts them too,
    // so a hand-built record keeps the same shape as the one the game writes.
    record.goals.assign(static_cast<std::size_t>(stars), true);
    progress.levels[levels[i]] = record;
  }
  return progress;
}

void testFirstPickStartsTheStarterWorld(const Catalog& catalog) {
  const Progress empty;
  const auto pick = pickNextLevel(catalog, empty, "");
  const auto starter = starterWorld(catalog);
  check(!starter.empty(), "the content must name a starter world");
  check(pick.world == starter, "an empty save must start in " + starter + ", got " + pick.world);
  const auto levels = levelsOfWorld(catalog, starter);
  check(!levels.empty(), "the starter world must hold levels");
  check(pick.level == levels.front(), "an empty save must start at " + levels.front() + ", got " + pick.level);
  check(!pick.fromLastLevel, "an empty save has no last level to follow");
  check(!pick.allCleared, "nothing is cleared in an empty save");
}

void testPickFollowsTheSavesLastLevel(const Catalog& catalog) {
  const Progress empty;
  const auto pick = pickNextLevel(catalog, empty, "beach_23");
  check(pick.fromLastLevel, "a save that names a level must be followed");
  check(pick.world == "beach", "beach_23 must resolve to the beach world, got " + pick.world);
  const auto levels = levelsOfWorld(catalog, "beach");
  check(pick.level == levels.front(),
        "the first unfinished beach level is " + levels.front() + ", got " + pick.level);
}

void testPickIgnoresALastLevelThatIsNotALEvel(const Catalog& catalog) {
  // A hand-edited or older save must not crash the menu: an unknown id falls back to the
  // starter world instead of naming a level the game cannot open.
  const Progress empty;
  const auto pick = pickNextLevel(catalog, empty, "not_a_level");
  check(!pick.fromLastLevel, "an unknown last level must not be followed");
  check(pick.world == starterWorld(catalog), "an unknown last level must fall back to the starter world");
}

void testPickSkipsFinishedLevels(const Catalog& catalog) {
  const auto progress = saveWith(catalog, "frontyard", 2, 2);
  const auto pick = pickNextLevel(catalog, progress, "");
  const auto levels = levelsOfWorld(catalog, "frontyard");
  check(pick.level == levels[2],
        "two finished levels must leave the third (" + levels[2] + "), got " + pick.level);
  check(!pick.allCleared, "the world is not finished yet");
}

void testPickReplaysTheFirstLevelWhenEverythingIsCleared(const Catalog& catalog) {
  const auto levels = levelsOfWorld(catalog, "frontyard");
  const auto progress = saveWith(catalog, "frontyard", levels.size(), 3);
  const auto pick = pickNextLevel(catalog, progress, "");
  check(pick.allCleared, "a fully cleared world must report it");
  check(pick.level == levels.front(),
        "a fully cleared world replays its first level (" + levels.front() + "), got " + pick.level);
}

/// The cursor the loop depends on: `Progress::lastLevel` has to survive the save round trip,
/// because "continue" on the next launch reads it back from the file and nowhere else.
void testSaveCarriesTheLastLevel(const fs::path& dir) {
  const auto path = dir / "last-level.json";
  std::error_code ignored;
  fs::remove(path, ignored);
  check(loadProgress(path).lastLevel.empty(), "a fresh save has no last level");

  Progress progress;
  progress.lastLevel = "kongfu_7";
  saveProgress(path, progress, 1700000000);
  check(loadProgress(path).lastLevel == "kongfu_7",
        "the save must carry lastLevel, got '" + loadProgress(path).lastLevel + "'");

  // A save written before the field existed has no `lastLevel` key at all and must still load.
  writeText(path, R"({"version": 1, "keys": 2, "levels": {}})");
  const auto old = loadProgress(path);
  check(old.lastLevel.empty(), "an older save without lastLevel must load as empty");
  check(old.keys == 2, "the rest of an older save must still be read");
}

/// The battle half: a won level must land in the save it was given, with its stars, and
/// with lastLevel pointing at it so the next run continues from there.
void testWonBattleLandsInTheSave(const Catalog& catalog, const fs::path& content, const fs::path& scripts,
                                 const fs::path& dir) {
  const auto table = loadStarTable(content / "stars.json");
  const auto found = catalog.levels.find("beach_23");
  check(found != catalog.levels.end(), "beach_23 must exist");
  const auto script = engine::loadScript(scripts / "beach_23_win.json");

  Progress progress;
  FlowPick pick;
  pick.world = "beach";
  pick.level = "beach_23";
  pick.lastLevel = "beach_23";
  const auto result = playPickedLevel(catalog, progress, table, pick, script, 120.0);

  check(result.status == "won", "the reference script must win beach_23, got " + result.status);
  check(result.cleared, "a won level must be recorded as cleared");
  check(result.levelStars >= 1, "a won level must carry at least one star, got " +
                                    std::to_string(result.levelStars));
  check(result.lastLevel == "beach_23", "the result must name the level it just played");
  const auto record = progress.find("beach_23");
  check(record != nullptr && record->cleared, "the save must hold the finished level");
  check(record != nullptr && record->stars == result.levelStars, "the save must hold the stars");

  const auto path = dir / "beach.json";
  saveProgress(path, progress, 1700000000);
  const auto reloaded = loadProgress(path);
  const auto again = reloaded.find("beach_23");
  check(again != nullptr && again->cleared, "the written save must reload with the level cleared");
  check(again != nullptr && again->stars == result.levelStars, "the written save must reload with the stars");

  // The JSON the result prints is what a caller parses; it must carry the same numbers.
  const auto json = result.json();
  check(json.at("level") == "beach_23", "the printed result must name the level");
  check(json.at("status") == "won", "the printed result must carry the status");
  check(json.at("stars").get<int>() == result.levelStars, "the printed result must carry the stars");
}

/// Two turns of the loop over one save file: an unfinished level is retried, and once it is
/// finished the next turn opens the following level. Every counter moves forward only.
void testTwoTurnsMoveForward(const Catalog& catalog, const fs::path& content, const fs::path& dir) {
  const auto table = loadStarTable(content / "stars.json");
  const auto path = dir / "loop.json";
  std::error_code ignored;
  fs::remove(path, ignored);

  engine::Script script;  // empty: the battle runs, nothing is planted

  Progress first = loadProgress(path);  // no file yet -> a fresh save
  const auto turn1 = runFlowCycle(catalog, first, table, first.lastLevel, script, 30.0);
  check(turn1.world == starterWorld(catalog), "turn 1 must start in the starter world, got " + turn1.world);
  check(!turn1.cleared, "an empty script cannot finish a level, got cleared for " + turn1.level);
  check(first.lastLevel == turn1.level,
        "the save must remember the level that was just played, got '" + first.lastLevel + "'");
  saveProgress(path, first, 1700000000);

  // Turn 2 sees the same unfinished level: a lost or abandoned battle is retried, never skipped.
  Progress second = loadProgress(path);
  const auto turn2 = runFlowCycle(catalog, second, table, second.lastLevel, script, 30.0);
  check(turn2.level == turn1.level, "an unfinished level must be retried, got " + turn2.level +
                                        " after " + turn1.level);
  check(second.levels.at(turn2.level).attempts >= 1, "the retry must be counted as an attempt");
  const auto before = progressReport(second, table);

  // Turn 3 is the real question: finish the level the way a won battle would, and the loop
  // must open the next one instead of replaying it.
  const auto levels = levelsOfWorld(catalog, turn1.world);
  check(levels.size() >= 3, "the starter world needs a few levels for this test");
  auto won = second;
  LevelRecord record = won.levels.at(turn1.level);
  record.cleared = true;
  record.stars = 2;
  record.goals = {true, true, false};  // a real win stores the goals it hit, not just the count
  won.levels[turn1.level] = record;
  saveProgress(path, won, 1700000001);

  Progress third = loadProgress(path);
  const auto recorded = third.find(turn1.level);
  check(recorded != nullptr && recorded->cleared, "the finished level must reload as cleared");
  check(recorded != nullptr && recorded->stars == 2, "the finished level must keep its stars");
  const auto turn3 = runFlowCycle(catalog, third, table, third.lastLevel, script, 30.0);
  check(turn3.level == levels[1], "a finished level must open the next one (" + levels[1] + "), got " +
                                      turn3.level);

  // `stars` in the printed result is what this battle earned (the result screen's number); the
  // save's totals are what the map shows and those may only move forward.
  const auto after = progressReport(third, table);
  check(after.at("totalStars").get<int>() >= before.at("totalStars").get<int>(),
        "the star total may not go backwards: had " +
            std::to_string(before.at("totalStars").get<int>()) + ", now " +
            std::to_string(after.at("totalStars").get<int>()));
  check(after.at("cleared").get<int>() >= before.at("cleared").get<int>(),
        "the cleared count may not go backwards");

  Progress fourth = loadProgress(path);
  (void)runFlowCycle(catalog, fourth, table, fourth.lastLevel, script, 30.0);
  const auto later = progressReport(fourth, table);
  check(later.at("totalStars").get<int>() >= after.at("totalStars").get<int>(),
        "a further turn may not lower the star total");
  check(later.at("cleared").get<int>() >= after.at("cleared").get<int>(),
        "a further turn may not lower the cleared count");
}

/// A damaged save is the one thing the loop must refuse: an unreadable save that gets
/// overwritten would erase a player's progress.
void testDamagedSaveIsNotOverwritten(const fs::path& dir) {
  const auto path = dir / "damaged.json";
  writeText(path, R"({"version": 1, "levels": {"frontyard_1": )");
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
  check(readText(path) == before, "a refused save must be left byte for byte alone");
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
  try {
    check(argc >= 4, "usage: flow_test <content> <temp> <scripts>");
    const fs::path content(argv[1]);
    const fs::path temp(argv[2]);
    const fs::path scripts(argv[3]);
    const auto catalog = loadCatalog(content);
    const auto dir = freshDir(temp, u8"flow");

    testFirstPickStartsTheStarterWorld(catalog);
    testPickFollowsTheSavesLastLevel(catalog);
    testPickIgnoresALastLevelThatIsNotALEvel(catalog);
    testPickSkipsFinishedLevels(catalog);
    testPickReplaysTheFirstLevelWhenEverythingIsCleared(catalog);
    testSaveCarriesTheLastLevel(dir);
    testWonBattleLandsInTheSave(catalog, content, scripts, dir);
    testTwoTurnsMoveForward(catalog, content, dir);
    testDamagedSaveIsNotOverwritten(dir);

    std::cout << "flow tests passed\n";
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "flow test failed: " << error.what() << "\n";
    return 1;
  }
}
