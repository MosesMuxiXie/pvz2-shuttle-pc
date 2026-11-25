#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

#include "content/loader.hpp"

namespace fs = std::filesystem;
using namespace pvz::content;

namespace {

void check(bool ok, const std::string& message) {
    if (!ok) {
        throw std::runtime_error(message);
    }
}

std::string minimalPlant(const std::string& extra = {}) {
    return R"({"id":"tester","framework":"PlantTester","propsSource":"static",
              "cost":25,"hitpoints":300,"gridType":"ground","height":"normal",
              "actions":[{"kind":"projectile","projectile":{"name":"Pea","sheet":"ProjectileTypes"},
                          "cooldownMin":1.5,"cooldownMax":1.5,"spawnOffset":{"x":35,"y":-32}},
                         {"kind":"sun","cooldownMin":20,"cooldownMax":25}]})" +
           extra;
}

std::string packWith(const std::string& plants, const std::string& zombies = "[]") {
    return "{ \"format\": 1, \"generated\": \"2026-11-20\", \"plants\": " + plants +
           ", \"zombies\": " + zombies + " }";
}

/// Expect `parseContentPack` to reject the text and mention `token`.
void reject(const std::string& text, const std::string& token, const std::string& name) {
    try {
        (void)parseContentPack(text, name);
    } catch (const LoadError& error) {
        const std::string message = error.what();
        check(message.find(token) != std::string::npos,
              "error for " + name + " should mention \"" + token + "\", got: " + message);
        return;
    }
    throw std::runtime_error("expected rejection for " + name);
}

void testShippedPack(const fs::path& path) {
    const ContentPack pack = loadContentPack(path);
    check(pack.format == kPackFormat, "pack format");
    check(pack.plants.size() == 339, "339 plant types");
    check(pack.zombies.size() == 1127, "1127 zombie types");

    std::size_t missingProps = 0;
    std::size_t actions = 0;
    std::size_t unknownKinds = 0;
    for (const PlantType& plant : pack.plants) {
        check(!plant.id.empty(), "plant id present");
        actions += plant.actions.size();
        for (const Action& action : plant.actions) {
            if (action.kind == ActionKind::unknown) {
                ++unknownKinds;
            }
        }
    }
    check(actions == 668, "plant action entries");
    // Two sheet entries carry no `Type` at all; they are data, so they survive
    // as `unknown` with the raw value preserved for later study.
    check(unknownKinds == 2, "two untyped plant actions");

    for (const ZombieType& zombie : pack.zombies) {
        if (zombie.propsSource == PropsSource::missing) {
            ++missingProps;
        }
    }
    check(missingProps == 3, "three zombie types with dangling properties");

    const PlantType* sunflower = pack.findPlant("sunflower");
    check(sunflower != nullptr, "sunflower present");
    check(sunflower->framework == "PlantLittleSunflower", "sunflower framework");
    check(sunflower->cost.value_or(0) == 50, "sunflower cost 50");
    check(sunflower->hitpoints.value_or(0) == 300, "sunflower hitpoints 300");
    check(sunflower->packetCooldown.value_or(0) == 5, "sunflower packet cooldown 5");
    check(sunflower->sunProducer, "sunflower produces sun");
    check(sunflower->actions.size() == 2, "sunflower two actions");
    check(sunflower->actions[0].kind == ActionKind::sun, "sunflower first action is sun");
    check(sunflower->actions[0].cooldownMin.value_or(0) == 32, "sun cooldown min 32");
    check(sunflower->actions[0].cooldownMax.value_or(0) == 36, "sun cooldown max 36");
    check(sunflower->actions[0].spawnOffset.has_value(), "sun spawn offset");
    check(sunflower->actions[0].spawnOffset->y == -52, "sun spawn offset y -52");

    const PlantType* peashooter = pack.findPlant("peashooter");
    check(peashooter != nullptr, "peashooter present");
    check(peashooter->cost.value_or(0) == 100, "peashooter cost 100");
    check(peashooter->actions.size() == 2, "peashooter two actions (normal + plantfood)");
    const Action& shot = peashooter->actions[0];
    check(shot.kind == ActionKind::projectile, "peashooter shoots projectiles");
    check(shot.projectile.has_value() && shot.projectile->name == "PeaDefault",
          "peashooter projectile is PeaDefault");
    check(shot.projectile->sheet == "ProjectileTypes", "projectile sheet");
    check(shot.cooldownMin.value_or(0) == 1.35, "peashooter cooldown min 1.35");
    check(shot.cooldownMax.value_or(0) == 1.5, "peashooter cooldown max 1.5");
    check(shot.damage == std::nullopt, "peashooter damage comes from the projectile");

    const PlantType* wallnut = pack.findPlant("wallnut");
    check(wallnut != nullptr && wallnut->hitpoints.value_or(0) == 4000, "wallnut hitpoints 4000");
    check(wallnut->actions.empty(), "wallnut has no actions");

    const PlantType* potatomine = pack.findPlant("potatomine");
    check(potatomine != nullptr, "potatomine present");
    check(potatomine->height == "low", "potatomine height low");
    check(potatomine->actions.size() == 1, "potatomine one action");
    const Action& mine = potatomine->actions[0];
    check(mine.kind == ActionKind::explode, "potatomine explodes");
    check(mine.trigger == "rect", "potatomine rect trigger");
    check(mine.triggerRect.has_value(), "potatomine trigger rect present");
    check(mine.triggerRect->width == 65 && mine.triggerRect->height == 60,
          "potatomine trigger rect size");
    check(mine.triggerRect->x == -30 && mine.triggerRect->y == -50, "potatomine trigger rect origin");

    const ZombieType* kongfu = pack.findZombie("kongfu_monk_bucket");
    check(kongfu != nullptr, "kongfu_monk_bucket present");
    check(kongfu->className == "ZombieBasic", "kongfu bucket walks the basic class");
    check(kongfu->hitpoints.value_or(0) == 190, "kongfu bucket hitpoints 190");
    check(kongfu->speed.value_or(0) == 0.185, "kongfu bucket speed 0.185");
    check(kongfu->weight.value_or(0) == 4000, "kongfu bucket weight 4000");
    check(kongfu->wavePointCost.value_or(0) == 400, "kongfu bucket wave point cost 400");
    check(kongfu->cost.value_or(0) == 150, "kongfu bucket sun cost 150");
    check(kongfu->hitRect.has_value(), "zombie hit rect present");

    // Two ids repeat in the sheet; the class (not the id) separates them, so the
    // pack keeps both records and reports the collision.
    check(pack.plantDuplicates.empty(), "no duplicate plant ids");
    check(pack.zombieDuplicates.size() == 2, "two duplicate zombie ids");
    check(pack.zombieDuplicates[0] == "heavy_shield" && pack.zombieDuplicates[1] == "kongfu_gargantuar",
          "duplicate zombie ids are heavy_shield and kongfu_gargantuar");
    const ZombieType* heavy = pack.findZombie("heavy_shield");
    check(heavy != nullptr && heavy->className == "ZombieStatue",
          "the first heavy_shield record is the statue");
    check(heavy->integerId == 538, "heavy_shield integer id 538");

    // Behaviour-script references are recorded, and the ones the sheet carries
    // resolve; missing ones stay visible instead of being dropped.
    std::size_t refs = 0;
    std::size_t unresolved = 0;
    for (const ZombieType& zombie : pack.zombies) {
        for (const ActionRef& ref : zombie.actionRefs) {
            ++refs;
            if (!ref.resolved) {
                ++unresolved;
            }
        }
    }
    check(refs > 0, "zombie behaviour references recorded");
    check(unresolved == 0, "every reachable zombie behaviour reference resolves");
}

void testMinimalPack() {
    const ContentPack pack = parseContentPack(packWith("[" + minimalPlant() + "]"), "minimal");
    check(pack.plants.size() == 1, "minimal plant count");
    const PlantType& plant = pack.plants[0];
    check(plant.id == "tester", "minimal plant id");
    check(plant.cost.value_or(0) == 25, "minimal plant cost");
    check(plant.actions.size() == 2, "minimal plant actions");
    check(plant.actions[0].projectile.has_value(), "minimal projectile");
    check(plant.actions[0].spawnOffset->x == 35, "minimal spawn offset x");
    check(plant.actions[1].kind == ActionKind::sun, "minimal second action is sun");
    check(pack.findPlant("tester") == &plant, "index finds the plant");
    check(pack.findPlant("absent") == nullptr, "index rejects unknown ids");
    check(pack.findZombie("tester") == nullptr, "plant is not a zombie");
}

void testUnknownKindIsKept() {
    const std::string plant =
        R"({"id":"oddity","propsSource":"static","actions":[{"kind":"unknown","rawType":"gravity"}]})";
    const ContentPack pack = parseContentPack(packWith("[" + plant + "]"), "unknown-kind");
    check(pack.plants.size() == 1, "unknown-kind plant loaded");
    const Action& action = pack.plants[0].actions.at(0);
    check(action.kind == ActionKind::unknown, "unknown kind preserved");
    check(action.rawType == "gravity", "raw type preserved");
}

void testRejections(const fs::path& scratch) {
    fs::create_directories(scratch);
    reject("{ \"format\": 2, \"plants\": [], \"zombies\": [] }", "unsupported format", "bad-format");
    reject("{ \"plants\": [], \"zombies\": [] }", "unsupported format", "missing-format");
    reject(packWith("[{\"framework\":\"x\"}]"), "missing field \"id\"", "no-id");
    reject(packWith("[{\"id\":\"\"}]"), "must not be empty", "empty-id");
    // The shipped tables repeat two zombie ids (their zombie class tells them
    // apart), so a repeated id is recorded, not refused.
    const ContentPack doubled =
        parseContentPack(packWith("[" + minimalPlant() + "," + minimalPlant() + "]"), "doubled");
    check(doubled.plants.size() == 2, "duplicate plant records are kept");
    check(doubled.plantDuplicates.size() == 1 && doubled.plantDuplicates[0] == "tester",
          "duplicate plant id is recorded");
    reject(packWith("[{\"id\":\"x\",\"cost\":\"free\"}]"), "must be a number", "cost-string");
    reject(packWith("[{\"id\":\"x\",\"actions\":\"none\"}]"), "must be an array", "actions-string");
    reject(packWith("[{\"id\":\"x\",\"actions\":[{\"rawType\":\"none\"}]}]"), "missing \"kind\"",
           "action-without-kind");
    reject(packWith("[{\"id\":\"x\",\"propsSource\":\"imaginary\"}]"), "propsSource",
           "bad-props-source");
    const ContentPack doubledZombies =
        parseContentPack(packWith("[]", "[{\"id\":\"x\"},{\"id\":\"x\"}]"), "doubled-zombies");
    check(doubledZombies.zombies.size() == 2, "duplicate zombie records are kept");
    check(doubledZombies.zombieDuplicates.size() == 1 && doubledZombies.zombieDuplicates[0] == "x",
          "duplicate zombie id is recorded");
    reject("not json", "invalid JSON", "not-json");

    const fs::path missing = scratch / u8"没有这个文件.pack";
    try {
        (void)loadContentPack(missing);
        throw std::runtime_error("expected a missing-file error");
    } catch (const LoadError& error) {
        const std::string message = error.what();
        check(message.find("cannot open") != std::string::npos, "missing file message: " + message);
        check(message.find(".pack") != std::string::npos,
              "missing file message keeps the path: " + message);
    }
}

void testPackOnDisk(const fs::path& scratch) {
    fs::create_directories(scratch);
    const fs::path path = scratch / "tiny.pack";
    std::ofstream(path, std::ios::binary) << packWith("[" + minimalPlant() + "]");
    const ContentPack pack = loadContentPack(path);
    check(pack.findPlant("tester") != nullptr, "loaded from disk");
    check(pack.generated == "2026-11-20", "generated stamp read");
}

}  // namespace

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    try {
        check(argc == 3, "expected <content.pack> <fixture directory>");
        const fs::path pack = argv[1];
        const fs::path scratch = argv[2] / fs::path(u8"content 测试") / "run";
        testShippedPack(pack);
        testMinimalPack();
        testUnknownKindIsKept();
        testRejections(scratch);
        testPackOnDisk(scratch);
        std::cout << "content tests passed\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "content test failed: " << error.what() << "\n";
        return 1;
    }
}
