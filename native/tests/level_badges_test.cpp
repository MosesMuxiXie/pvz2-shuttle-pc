// Level badges (A7): the table behind the level list's "玩法" line.
//
// Run it with:
//   level_badges_test <temp-dir>
// (cmake registers it with `${PVZ_TEST_TEMP}`; the working directory is the repository root, which
// is how `engine::generatedDir()` finds `native/generated`.)
//
// Two kinds of case live here. The first read the *shipped* generated tables and pin the real
// answers — vasebreaker levels say 砸罐子, a two-minecart rail level says 铁轨×2, and a plain lawn says
// nothing. The second write a two-file fixture into the temp directory, because the interesting rules
// (five chips max, `+N`, an unknown kind, a missing table) cannot be tested by editing the shipped
// data: the shipped data has no level with six kinds and no missing file.

#include "engine/plantfood.hpp"
#include "level_badges.hpp"
#include "level_select_view.hpp"
#include "worldmap_view.hpp"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error("level badge test failed: " + message);
}

bool contains(const std::vector<std::string>& values, const std::string& wanted) {
    return std::find(values.begin(), values.end(), wanted) != values.end();
}

void writeFile(const fs::path& file, const std::string& text) {
    fs::create_directories(file.parent_path());
    std::ofstream out(file, std::ios::binary);
    if (!out) throw std::runtime_error("cannot write fixture: " + file.string());
    out << text;
}

// A fixture directory with the two tables the loader reads. Kept as raw JSON text so the test shows
// exactly which keys it depends on.
fs::path makeFixture(const fs::path& root, const std::string& minigames, const std::string& mechanics) {
    const fs::path dir = root / "badge-fixture";
    fs::remove_all(dir);
    fs::create_directories(dir);
    writeFile(dir / "minigames.json", minigames);
    writeFile(dir / "level_mechanics.json", mechanics);
    return dir;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc < 2) throw std::runtime_error("usage: level_badges_test <temp-dir>");
        const fs::path temp = fs::path(argv[1]);
        fs::create_directories(temp);

        // 1. The dictionary itself: every token the screen can print, in display order.
        {
            const std::vector<std::string> rows = pvz::badgeDictionary();
            check(rows.size() == 21, "the dictionary must hold 21 kinds, got " + std::to_string(rows.size()));
            check(rows.front() == "vasebreaker=砸罐子", "vasebreaker must come first, got " + rows.front());
            check(contains(rows, "rail=铁轨"), "rail must be 铁轨");
            check(contains(rows, "conveyor=传送带"), "conveyor must be 传送带");
            check(contains(rows, "gravestone=墓碑"), "gravestone must be 墓碑");
            check(pvz::badgeLabel("vasebreaker") == "砸罐子", "badgeLabel must resolve a known kind");
            check(pvz::badgeLabel("no-such-kind").empty(), "badgeLabel must not invent a label");
        }

        // 2. The shipped tables: they load, and every level the content tools classified is present.
        const pvz::LevelBadges shipped = pvz::load(pvz::engine::generatedDir());
        check(shipped.loaded, "the shipped tables must load (note: " + shipped.note + ")");
        check(shipped.minigameLevels == 813,
              "minigames.json must contribute 813 levels, got " + std::to_string(shipped.minigameLevels));
        check(shipped.mechanicLevels > 0,
              "level_mechanics.json must contribute conveyor/gravestone levels, got " +
                  std::to_string(shipped.mechanicLevels));
        check(shipped.size() > 800, "the merged table is suspiciously small: " + std::to_string(shipped.size()));

        // 3. The four badges the task names, on the levels that really carry them.
        {
            const std::vector<std::string> vase = pvz::badgesFor(shipped, "beach_69");
            check(contains(vase, "砸罐子"), "beach_69 is a vasebreaker level");
            const std::vector<std::string> rail = pvz::badgesFor(shipped, "beach_10");
            check(contains(rail, "铁轨×2"), "beach_10 carries two minecarts, got " +
                                                pvz::badgeLine(rail));
            const std::vector<std::string> conveyor = pvz::badgesFor(shipped, "beach_12");
            check(contains(conveyor, "传送带"), "beach_12 is a conveyor level");
            const std::vector<std::string> grave = pvz::badgesFor(shipped, "frontyard_61");
            check(contains(grave, "墓碑"), "frontyard_61 starts with gravestones, got " +
                                               pvz::badgeLine(grave));
            // A belt the minigame table did not classify still reads as a belt: frontyard_10 has no
            // `kinds` entry at all and only the mechanics table knows about its conveyor.
            const std::vector<std::string> belt = pvz::badgesFor(shipped, "frontyard_10");
            check(belt.size() == 1 && belt.front() == "传送带",
                  "a conveyor known only to level_mechanics.json must still show, got " + pvz::badgeLine(belt));
            check(!contains(pvz::badgesFor(shipped, "beach_12"), "传送带 · 传送带"), "a kind must not repeat");
        }

        // 4. A plain level has no badges, and that is not an error.
        {
            const std::vector<std::string> plain = pvz::badgesFor(shipped, "frontyard_1");
            check(plain.empty(), "frontyard_1 has no mechanic, got " + pvz::badgeLine(plain));
            check(pvz::badgeSummary(shipped, "frontyard_1").empty(), "an empty level must summarise to nothing");
            check(pvz::badgesOf(shipped, "no-such-level").empty(), "an unknown level must have no badges");
        }

        // 5. Fixed order: the chips follow the dictionary, never the order the JSON arrays happen to
        // have. `kongfu_83` lists vasebreaker, rail, laststand, protecttheplant.
        {
            const std::vector<std::string> chips = pvz::badgesFor(shipped, "kongfu_83");
            check(chips.size() == 4, "kongfu_83 has four kinds, got " + std::to_string(chips.size()));
            check(chips[0] == "砸罐子" && chips[1] == "铁轨" && chips[2] == "保卫植物" &&
                      chips[3] == "最后防线",
                  "chips must follow the dictionary order, got " + pvz::badgeLine(chips));
        }

        // 6. Five chips max, then `+N`: the shipped data never needs this, so a fixture provides it.
        {
            const fs::path dir = makeFixture(temp,
                                             R"({"levels":{"six":{"kinds":["bowling","tide","vasebreaker","rail","conveyor","protecttheplant"]},)"
                                             R"("one":{"kinds":["rail"]}}})",
                                             R"({"levels":{}})");
            const pvz::LevelBadges fixture = pvz::load(dir);
            check(fixture.loaded, "the fixture must load (note: " + fixture.note + ")");
            const std::vector<std::string> six = pvz::badgesFor(fixture, "six");
            check(six.size() == pvz::kMaxBadges, "six kinds must collapse to five chips, got " +
                                                     std::to_string(six.size()));
            check(six.back() == "+2", "the last chip must be +2, got " + six.back());
            check(six[0] == "砸罐子" && six[1] == "铁轨" && six[2] == "传送带" && six[3] == "潮汐",
                  "truncation must keep the highest-ranked chips, got " + pvz::badgeLine(six));
            check(pvz::badgeLine(six) == "砸罐子 · 铁轨 · 传送带 · 潮汐 · +2",
                  "the line is joined with ' · ', got " + pvz::badgeLine(six));
            check(pvz::badgeSummary(fixture, "six") == pvz::badgeLine(six),
                  "badgeSummary must be badgesFor + badgeLine");
        }

        // 7. An unknown kind still shows (as its raw token) and is reported once, not silently dropped.
        {
            const fs::path dir = makeFixture(temp,
                                             R"({"levels":{"mystery":{"kinds":["mysterymode","vasebreaker"]}}})",
                                             R"({"levels":{}})");
            const pvz::LevelBadges fixture = pvz::load(dir);
            const std::vector<std::string> chips = pvz::badgesFor(fixture, "mystery");
            check(contains(chips, "mysterymode"), "an unknown kind must keep its token, got " +
                                                     pvz::badgeLine(chips));
            check(chips.front() == "砸罐子", "a known kind must still sort first, got " + pvz::badgeLine(chips));
            check(contains(fixture.unknownKinds, "mysterymode"), "the unknown kind must be reported");
            check(fixture.unknownKinds.size() == 1, "one unknown kind must be reported once");
        }

        // 8. A missing or broken table is a note, never a throw: the level list must still open.
        {
            const pvz::LevelBadges empty = pvz::load(temp / "no-such-directory");
            check(!empty.loaded, "a missing directory must not claim loaded");
            check(!empty.note.empty(), "a missing directory must explain itself");
            check(pvz::badgesFor(empty, "beach_10").empty(), "nothing loaded means no chips");
            check(pvz::badgeSummary(empty, "beach_10").empty(), "nothing loaded means no summary");

            const pvz::LevelBadges none = pvz::load({});
            check(!none.loaded, "an empty generated dir must not claim loaded");
            check(none.note.find("PVZ_GENERATED_DIR") != std::string::npos,
                  "the note must name the variable that fixes it, got " + none.note);

            const fs::path broken = makeFixture(temp, "{not json", "{}");
            const pvz::LevelBadges bad = pvz::load(broken);
            check(!bad.loaded, "unparsable JSON must not claim loaded");
            check(bad.note.find("minigames.json") != std::string::npos,
                  "the note must name the file that failed, got " + bad.note);
        }

        // 9. The level list hands its chips to the CLI as `badges`, and nothing else changes shape.
        {
            pvz::LevelSelectResult result;
            result.world = "beach";
            result.levels = 32;
            result.cleared = 4;
            result.selected = 9;
            result.selectedLevel = "beach_10";
            result.badges = {"铁轨×2", "潮汐", "三消"};
            result.badgeLine = "铁轨×2 · 潮汐 · 三消";

            const pvz::Json json = pvz::levelSelectJson(result);
            check(json["world"] == "beach", "the level list must still report its world");
            check(json["levels"] == 32 && json["cleared"] == 4, "the level counts must survive");
            check(json["selected"] == "beach_10", "the level list must still report the selection");
            check(json["badges"].is_array() && json["badges"].size() == 3,
                  "badges must be an array of the chips for the selected level");
            // B6b: each chip reports whether the simulation runs that mechanic, so the screen can
            // colour it and a caller can tell 铁轨 (playable) from 三消 (data only).
            const pvz::Json& first = json["badges"][0];
            check(first["label"] == "铁轨×2",
                  "the chips must keep their order, got " + json["badges"].dump());
            check(first["kind"] == "rail", "`铁轨×2` maps back to `rail`, got " +
                                               first["kind"].dump());
            check(first["wired"] == true, "rail is wired in the simulation");
            check(json["badges"][1]["kind"] == "tide" && json["badges"][1]["wired"] == false,
                  "tide is a badge the simulation does not run yet");
            check(json["badges"][2]["wired"] == false, "三消 is data only for now");
            check(!first.contains("marker"), "a real chip is not the truncation marker");
        }

        // 9b. `+N` is a marker, not a mechanic: it has no kind and nothing to wire.
        {
            pvz::LevelSelectResult result;
            result.badges = {"砸罐子", "+2"};
            const pvz::Json json = pvz::levelSelectJson(result);
            check(json["badges"][1]["label"] == "+2", "the marker keeps its text");
            check(json["badges"][1]["marker"] == true, "the marker must be flagged");
            check(json["badges"][1]["wired"] == false, "the marker is not a wired mechanic");
            check(!json["badges"][1].contains("kind"), "the marker has no kind");
            check(json["badges"][0]["wired"] == true, "砸罐子 is wired");
        }

        // 9c. The chip -> kind mapping the screen colours by.
        {
            check(pvz::badgeKindOfLabel("铁轨") == "rail", "铁轨 -> rail");
            check(pvz::badgeKindOfLabel("砸罐子") == "vasebreaker", "砸罐子 -> vasebreaker");
            check(pvz::badgeKindOfLabel("传送带") == "conveyor", "传送带 -> conveyor");
            check(pvz::badgeKindOfLabel("保卫植物") == "protecttheplant", "保卫植物 -> protecttheplant");
            check(pvz::badgeKindOfLabel("墓碑") == "gravestone", "墓碑 -> gravestone");
            check(pvz::badgeKindOfLabel("没有这个").empty(), "an unknown label maps to no kind");
            check(pvz::badgeWired("rail") && pvz::badgeWired("vasebreaker"), "rail/vase are wired");
            check(!pvz::badgeWired("beghouled"), "beghouled is not wired");
            check(!pvz::badgeWired(""), "an empty kind is not wired");
            // Everything the table actually ships has to fall into one of the two buckets.
            for (const pvz::LevelBadge& badge : pvz::badgesOf(shipped, "kongfu_83")) {
                check(pvz::badgeKindOfLabel(badge.label) == badge.kind,
                      "label and kind must agree for " + badge.kind);
                check(pvz::badgeWired(badge.kind) == badge.wired,
                      "`wired` must follow the kind for " + badge.kind);
            }
        }

        // 10. The world map's almanac/garden line reads the same table, and its JSON carries it.
        {
            const pvz::MetagameCounts counts = pvz::loadMetagameCounts(pvz::engine::generatedDir());
            check(counts.loaded, "metagame.json must load from the generated dir, note: " + counts.note);
            check(counts.plants == 167, "almanac.counts.plants, got " + std::to_string(counts.plants));
            check(counts.zombies == 428, "almanac.counts.zombies, got " + std::to_string(counts.zombies));
            check(counts.drops == 65, "garden.counts.collectables, got " + std::to_string(counts.drops));

            const pvz::MetagameCounts missing = pvz::loadMetagameCounts(temp / "no-such-directory");
            check(!missing.loaded, "a missing metagame.json must not claim loaded");
            check(!missing.note.empty(), "a missing metagame.json must explain itself");

            pvz::WorldMapScreenResult result;
            result.worlds = 26;
            result.unlocked = 1;
            result.completed = 2;
            result.stars = 7;
            result.keys = 3;
            result.selected = 0;
            result.selectedWorld = "frontyard";
            result.enteredWorld = "frontyard";
            result.enteredLevel = "frontyard_1";
            result.clearedWorlds = 2;
            result.metagame = counts;

            const pvz::Json json = pvz::worldMapScreenJson(result);
            check(json["worlds"] == 26 && json["stars"] == 7 && json["level"] == "frontyard_1",
                  "the pre-existing world map keys must survive");
            check(json["clearedWorlds"] == 2, "clearedWorlds must mirror the completed count");
            check(json["almanac"]["plants"] == 167, "almanac.plants must reach the CLI");
            check(json["almanac"]["zombies"] == 428, "almanac.zombies must reach the CLI");
            check(json["garden"]["drops"] == 65, "garden.drops must reach the CLI");
        }

        std::cout << "level_badges_test: OK (dictionary " << pvz::badgeDictionary().size() << " kinds, "
                  << shipped.size() << " levels with badges, " << shipped.minigameLevels
                  << " from minigames.json, " << shipped.mechanicLevels
                  << " from level_mechanics.json, unknown " << shipped.unknownKinds.size() << ")\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
