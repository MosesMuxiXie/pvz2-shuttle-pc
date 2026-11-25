// S5.7 reachability: plant food and fusion had no input path.
//
// The mechanics themselves are covered by `s5_runtime_test` (it calls `World::feed` and
// `World::tryFuse` directly). That is exactly the gap this file closes: a feature only the test
// can reach is not in the game. Here every action goes through a replay script, i.e. through the
// same `applyInputs` the CLI uses for `--run-level --script`.
//
// The entity ids are stable and start at 1 for a fresh world, so a script can address a plant it
// planted earlier in the same run. That is a deliberate contract, not an accident: `feed`/`fuse`
// take ids because after a shovel the cell no longer identifies anything.
#include "catalog.hpp"
#include "engine/replay.hpp"
#include "engine/world.hpp"
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>

namespace fs = std::filesystem;
using namespace pvz;
using namespace pvz::engine;

namespace {

void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

Catalog load(const fs::path& content, const fs::path& pack) {
    CatalogOptions options;
    if (!pack.empty()) options.contentPack = pack;
    return loadCatalog(content, options);
}

/// A lawn with no deck restriction and a large sun balance: the script must decide what happens,
/// not the seed bank.
LevelDefinition lawn(const Catalog& catalog, const std::string& id) {
    LevelDefinition level = catalog.levels.at("frontyard_1");
    level.id = id;
    level.rows = 5;
    level.cols = 9;
    level.sun = 5000;
    level.deck.clear();
    return level;
}

World makeWorld(const Catalog& catalog, const std::string& id, std::uint32_t seed = 7) {
    return World(catalog, lawn(catalog, id), seed);
}

bool hasEvent(const World& world, const std::string& type, const std::string& op = {}) {
    for (const auto& event : world.events()) {
        const auto kind = event.find("type");
        if (kind == event.end() || !kind->is_string() || kind->get<std::string>() != type) continue;
        if (op.empty()) return true;
        const auto details = event.find("details");
        if (details == event.end() || !details->is_object()) continue;
        const auto seen = details->find("op");
        if (seen != details->end() && seen->is_string() && seen->get<std::string>() == op) return true;
    }
    return false;
}

/// A script that plants one peashooter. `feed` is added later, once the id exists: the tests
/// read ids from the world instead of assuming `nextId_` starts at 1, so a future entity that
/// consumes ids cannot silently break them.
Script plantScript(const std::string& level, const std::string& type, int row, int col) {
    Script script;
    script.level = level;
    script.inputs.push_back(ScriptInput{0, "plant", type, row, col, 0, 0});
    return script;
}

void testFeedThroughScript(const Catalog& catalog) {
    World world = makeWorld(catalog, "s5_replay_feed");
    runScript(world, plantScript("s5_replay_feed", "peashooter", 2, 3), 0.2);
    check(world.plants().size() == 1, "the script must plant exactly one plant");
    const EntityId id = world.plants().front().id;

    Script feed;
    feed.level = "s5_replay_feed";
    feed.inputs.push_back(ScriptInput{world.tick() + 1, "feed", {}, 0, 0, id, 0});
    runScript(world, feed, 0.5);

    const auto* plant = world.plantById(id);
    check(plant != nullptr, "the planted peashooter must still stand");
    check(plant->plantFoodTicks > 0, "a feed applied through a script must leave the buff running");
    check(world.plantFoodStates().size() == 1, "the fed plant must be reported as fed");
    check(!hasEvent(world, "input_rejected", "feed"), "a legal feed must not be recorded as rejected");

    // The buff expires on its own; nothing else in the script must keep it alive.
    world.advance(5.0);
    const auto* later = world.plantById(id);
    check(later != nullptr && later->plantFoodTicks == 0, "the buff must expire without another input");
}

void testFusionThroughScript(const Catalog& catalog) {
    World world = makeWorld(catalog, "s5_replay_fuse");
    runScript(world, plantScript("s5_replay_fuse", "peashooter", 1, 2), 0.05);
    runScript(world, plantScript("s5_replay_fuse", "iceburg", 1, 3), 0.2);
    check(world.plants().size() == 2, "both ingredients must be planted before fusing");
    const EntityId a = world.plants()[0].id;
    const EntityId b = world.plants()[1].id;

    Script fuse;
    fuse.level = "s5_replay_fuse";
    fuse.inputs.push_back(ScriptInput{world.tick() + 1, "fuse", {}, 0, 0, a, b});
    runScript(world, fuse, 0.5);

    check(world.plants().size() == 1, "a fusion must consume both ingredients");
    check(world.fusions() == 1, "the fusion counter must record the pair");
    check(world.plants().front().type == "fused_snowpea",
          "peashooter + iceburg must become fused_snowpea, got " + world.plants().front().type);
    check(hasEvent(world, "fusion"), "the fusion must emit its event");
}

void testRefusalsAreVisible(const Catalog& catalog) {
    World world = makeWorld(catalog, "s5_replay_refuse");
    Script script;
    script.level = "s5_replay_refuse";
    script.inputs.push_back(ScriptInput{0, "feed", {}, 0, 0, 99, 0});
    script.inputs.push_back(ScriptInput{0, "fuse", {}, 0, 0, 98, 97});
    runScript(world, script, 0.2);

    check(hasEvent(world, "input_rejected", "feed"), "feeding a missing plant must be reported");
    check(hasEvent(world, "input_rejected", "fuse"), "fusing two missing plants must be reported");
    check(world.fusions() == 0, "a refused fusion must not count");
}

void testParsingRequiresIds() {
    bool threw = false;
    try {
        parseScript(Json{{"level", "x"}, {"inputs", Json::array({Json{{"op", "feed"}}})}});
    } catch (const std::exception& error) {
        threw = std::string(error.what()).find("feed input without id") != std::string::npos;
    }
    check(threw, "a feed without id must be refused while parsing");

    threw = false;
    try {
        parseScript(Json{{"level", "x"}, {"inputs", Json::array({Json{{"op", "fuse"}, {"id", 1}}})}});
    } catch (const std::exception& error) {
        threw = std::string(error.what()).find("fuse input without id2") != std::string::npos;
    }
    check(threw, "a fuse with one id must be refused while parsing");
}

void testScriptIsDeterministic(const Catalog& catalog) {
    // One script, both runs: plant, then feed whatever id the world handed out. The seed makes
    // the two worlds identical, so the second run must reproduce the first. The lambda returns
    // the two observable facts instead of the world itself: `World` is deliberately
    // non-copyable and non-movable (it owns reference cycles), so it cannot be handed out.
    auto run = [&catalog](const std::string& level) {
        World world = makeWorld(catalog, level, 3);
        runScript(world, plantScript(level, "peashooter", 0, 1), 0.2);
        const EntityId id = world.plants().front().id;
        Script feed;
        feed.level = level;
        feed.inputs.push_back(ScriptInput{world.tick() + 1, "feed", {}, 0, 0, id, 0});
        runScript(world, feed, 0.4);
        return std::make_pair(world.hash(), world.plantFoodStates().size());
    };
    const auto first = run("s5_replay_det");
    const auto second = run("s5_replay_det");
    check(first.first == second.first, "the same feed script must produce the same state hash");
    check(first.second == second.second, "both runs must agree on how many plants are fed");
}

} // namespace

int wmain(int argc, wchar_t** argv) {
    try {
        if (argc < 3) {
            std::cerr << "usage: replay_s5_test <content directory> [content pack]\n";
            return 2;
        }
        const fs::path content = argv[1];
        const fs::path pack = fs::path(argv[2]);
        const Catalog catalog = load(content, pack);
        if (catalog.levels.count("frontyard_1") == 0) {
            std::cerr << "replay_s5 test failed: the fixture level frontyard_1 is missing\n";
            return 1;
        }

        testFeedThroughScript(catalog);
        testFusionThroughScript(catalog);
        testRefusalsAreVisible(catalog);
        testParsingRequiresIds();
        testScriptIsDeterministic(catalog);
        std::cout << "replay_s5 tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "replay_s5 test failed: " << error.what() << "\n";
        return 1;
    }
}
