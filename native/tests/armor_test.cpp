// S5.11 armor wiring: the sheet's layer order and ArmorFlags have to reach the engine's damage
// path, not just sit in JSON. Before this the engine read `content/zombies.json`'s `armor[].hp`
// and summed it into one pool, so a bucket and a cloth were the same thing and `invincible`
// meant nothing. These cases pin the reading (counts, order, flags, the content bridge) and the
// two behaviours that differ from the old sum: a layer pool that breaks with events, and an
// invincible layer that blocks.
#include "engine/armor.hpp"
#include "engine/world.hpp"

#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <algorithm>
#include <vector>

namespace {

namespace fs = std::filesystem;
using pvz::Json;
using pvz::engine::ArmorLayer;
using pvz::engine::ArmorTable;
using pvz::engine::World;

[[noreturn]] void fail(const std::string& message) { throw std::runtime_error(message); }
void check(bool condition, const std::string& message) {
    if (!condition) fail(message);
}

std::string layerIds(const std::vector<ArmorLayer>& layers) {
    std::string out;
    for (const ArmorLayer& layer : layers) {
        if (!out.empty()) out += ", ";
        out += layer.armorId.empty() ? std::string{"<dangling>"} : layer.armorId;
    }
    return out;
}

bool hasFlag(const ArmorLayer& layer, const char* name) {
    return (layer.flags & pvz::engine::armorFlagBit(name)) != 0;
}

/// Counts straight out of the sheet: if any of these move, the armor data changed and the
/// wiring in world.cpp was not what changed, so the test should make someone look.
void testCounts(const ArmorTable& table) {
    check(table.size() == 102, "the sheet must carry 102 armors, got " + std::to_string(table.size()));
    check(table.canonical() == 97, "canonicalArmors must be 97, got " + std::to_string(table.canonical()));
    check(table.embeddedOnly() == 5,
          "embeddedOnlyArmors must be 5, got " + std::to_string(table.embeddedOnly()));
    check(table.unused() == 14, "unusedArmors must be 14, got " + std::to_string(table.unused()));
    check(table.unusedIds().size() == 14,
          "the unused id list must hold 14 names, got " + std::to_string(table.unusedIds().size()));
    check(table.withoutLayer() == 13,
          "13 armors must carry no ArmorLayers, got " + std::to_string(table.withoutLayer()));
    check(table.withHitpoints() == 101,
          "101 armors must carry hit points, got " + std::to_string(table.withHitpoints()));

    // Dangling references: the sheet names three armor ids that no row defines anywhere.
    check(table.danglingIds().size() == 3,
          "three armor ids must be dangling, got " + std::to_string(table.danglingIds().size()));
    for (const char* expected : {"AngerManagement", "HideLayer", "InvincibleArmor"}) {
        bool found = false;
        for (const std::string& id : table.danglingIds()) found = found || id == expected;
        check(found, std::string{"the dangling list must name "} + expected);
    }

    // Two zombie ids carry two rows each. Merging them would hide the sheet's own bookkeeping.
    check(table.zombieRowCount("heavy_shield") == 2, "heavy_shield must keep its two rows");
    check(table.zombieRowCount("kongfu_gargantuar") == 2, "kongfu_gargantuar must keep its two rows");
    check(table.zombieRowCount("lostcity_excavator") == 1, "lostcity_excavator has one row");
    check(table.zombieRowCount("no_such_zombie") == 0, "an unknown zombie id has no rows");
}

/// Three real stacks: the order is the sheet's, and the flags are per layer, not per zombie.
void testLayerOrderAndFlags(const ArmorTable& table) {
    // kongfu_armor3: two cloths over a helmet, all 1650 hp, only the last one is a droppable helm.
    const auto kongfu = table.zombieArmorLayers("kongfu_armor3");
    check(kongfu.size() == 3, "kongfu_armor3 must have three layers, got " + layerIds(kongfu));
    check(kongfu[0].armorId == "KongfuHelmetClothDefault" && kongfu[1].armorId == "KongfuHelmetCloth2Default" &&
              kongfu[2].armorId == "KongfuHelmetDefault",
          "kongfu_armor3 layers must keep the sheet order, got " + layerIds(kongfu));
    for (const ArmorLayer& layer : kongfu) check(layer.hitpoints == 1650.0, "each kongfu layer is 1650 hp");
    check(hasFlag(kongfu[0], "passdamage") && !hasFlag(kongfu[0], "helm"),
          "the first kongfu cloth passes damage and is not a helm");
    check(hasFlag(kongfu[1], "passdamage") && !hasFlag(kongfu[1], "droppable"),
          "the second kongfu cloth passes damage and does not drop");
    check(hasFlag(kongfu[2], "helm") && hasFlag(kongfu[2], "droppable") && !hasFlag(kongfu[2], "passdamage"),
          "the kongfu helmet drops, is a helm, and does not pass damage");
    check(!kongfu[0].artLayer.empty(), "a layer with ArmorLayers must carry the bone name for the view");

    // Cone and bucket are the two the view used to hardcode; the sheet must be what says so.
    const auto cone = table.zombieArmorLayers("tutorial_armor1");
    check(cone.size() == 1 && cone[0].armorId == "ConeDefault", "tutorial_armor1 wears ConeDefault");
    check(cone[0].hitpoints == 370.0 && hasFlag(cone[0], "droppable") && !hasFlag(cone[0], "metallic"),
          "a cone is 370 hp, droppable and not metal");
    const auto bucket = table.zombieArmorLayers("tutorial_armor2");
    check(bucket.size() == 1 && bucket[0].armorId == "BucketDefault", "tutorial_armor2 wears BucketDefault");
    check(bucket[0].hitpoints == 1100.0 && hasFlag(bucket[0], "metallic"),
          "a bucket is 1100 hp and metal, which is what the view's grey block keys on");
}

/// Invincible layers never enter the pool, so they can never break. Two shapes exist:
/// `kongfu_qigong_wave` blocks (no passdamage), `mausoleum_drunk` lets the hit through.
void testInvincibleLayers(const ArmorTable& table) {
    const auto nunchaku = table.zombieArmorLayers("kongfu_qigong_wave");
    check(nunchaku.size() == 1 && nunchaku[0].armorId == "NunchakuDefault",
          "kongfu_qigong_wave wears NunchakuDefault, got " + layerIds(nunchaku));
    check(hasFlag(nunchaku[0], "invincible") && !hasFlag(nunchaku[0], "passdamage"),
          "the nunchaku is invincible and does not pass damage: it blocks");
    check(!nunchaku[0].poolsHitPoints(), "an invincible layer must stay out of the hit-point pool");

    const auto jars = table.zombieArmorLayers("mausoleum_drunk");
    check(jars.size() == 5, "mausoleum_drunk must keep five jars, got " + layerIds(jars));
    check(jars.front().armorId == "DrunkardWineJar" && jars.back().armorId == "DrunkardWineJar4",
          "the jars must keep the sheet order, got " + layerIds(jars));
    for (const ArmorLayer& jar : jars) {
        check(hasFlag(jar, "invincible") && hasFlag(jar, "passdamage"),
              "every jar is invincible and passes damage: it never blocks");
        check(!jar.poolsHitPoints(), "an invincible jar must stay out of the hit-point pool");
    }
}

/// Content zombies reach the sheet only through `contentComparison`; 10 of the 55 have a row and
/// the unbridged ones must come back empty so world.cpp keeps the content-only reading.
void testContentBridge(const ArmorTable& table) {
    const auto buckethead = table.contentArmorLayers("buckethead");
    check(buckethead.size() == 1 && buckethead[0].armorId == "BucketDefault",
          "buckethead must bridge to BucketDefault, got " + layerIds(buckethead));
    check(buckethead[0].hitpoints == 1100.0, "the bridge must carry the sheet's 1100 hp");
    check(hasFlag(buckethead[0], "metallic") && hasFlag(buckethead[0], "droppable"),
          "the bridge must carry the sheet's flags, which the content armor array does not have");
    const auto conehead = table.contentArmorLayers("conehead");
    check(conehead.size() == 1 && conehead[0].armorId == "ConeDefault",
          "conehead must bridge to ConeDefault, got " + layerIds(conehead));
    const auto bridge = table.contentBridge("buckethead");
    check(bridge != nullptr && bridge->packZombieId == "tutorial_armor2",
          "buckethead bridges to tutorial_armor2");
    // 16 bridge rows for the 16 armored content zombies. (`counts.contentBridged` says 10: the
    // sheet counts only the rows that resolve a real pack zombie id, the other 6 bridge armour
    // sets without one — the rows are what world.cpp reads, so that is what is asserted here.)
    check(table.bridged() == 16, "the sheet must carry 16 bridge rows, got " + std::to_string(table.bridged()));
    check(table.contentArmorLayers("basic").empty(),
          "an unarmored content zombie must return no layers so the caller plants its own armor[]");
    check(table.contentArmorLayers("no_such_zombie").empty(), "an unknown content id has no layers");
}

/// The engine side: the stack reaches `ZombieEntity`, a bridge changes the flags, and a break
/// reports what happened instead of silently zeroing one number.
void testEngineLayers(const pvz::Catalog& catalog) {
    World world(catalog, catalog.levels.at("frontyard_1"), 71);
    check(world.spawnZombie("buckethead", 0), "buckethead must spawn from content");
    const auto* zombie = world.zombies().empty() ? nullptr : &world.zombies().front();
    check(zombie != nullptr && zombie->armorLayers.size() == 1,
          "buckethead must carry one armor layer in the engine");
    check(zombie->armorHp == 1100.0 && zombie->armorMaxHp == 1100.0,
          "buckethead's pool must be the sheet's 1100 hp, got " + std::to_string(zombie->armorHp));
    check(zombie->armorLayers.front().armorId == "BucketDefault",
          "the engine layer must name the sheet row, not a synthetic id");
    check((zombie->armorLayers.front().flags & pvz::engine::kArmorMetallic) != 0,
          "the engine layer must carry the sheet's metallic flag, not just an hp number");

    // A hit that the bucket survives leaves hp alone and breaks nothing.
    const auto id = zombie->id;
    const double hpBefore = zombie->hp;
    world.damageZombie(id, 100.0);
    check(world.zombieById(id)->armorHp == 1000.0, "100 damage must leave the bucket at 1000");
    check(world.zombieById(id)->hp == hpBefore, "damage inside the pool must not reach the body");
    for (const Json& entry : world.events()) {
        check(entry.value("type", std::string{}) != "armor_broken", "the bucket must not break at 1000 hp");
    }

    // Exactly the remaining pool: it breaks, reports the drop, and still does not touch the body.
    world.damageZombie(id, 1000.0);
    check(world.zombieById(id)->armorHp == 0.0, "the bucket must be empty after 1100 damage");
    check(world.zombieById(id)->hp == hpBefore, "breaking the armor must not spill into the body");
    bool broken = false;
    bool dropped = false;
    for (const Json& entry : world.events()) {
        const std::string type = entry.value("type", std::string{});
        if (type == "armor_broken") broken = true;
        if (type == "armor_dropped") dropped = true;
    }
    check(broken, "breaking a layer must emit armor_broken");
    check(dropped, "a droppable layer must emit armor_dropped (the sheet says droppable on BucketDefault)");

    // A pack-only zombie with no bridge row still gets its sheet stack by pack id.
    World packWorld(catalog, catalog.levels.at("frontyard_1"), 72);
    check(packWorld.spawnZombie("kongfu_armor3", 1), "kongfu_armor3 must spawn from the pack");
    const auto& packZombie = packWorld.zombies().front();
    check(packZombie.armorLayers.size() == 3, "kongfu_armor3 must carry three layers in the engine");
    check(packZombie.armorHp == 4950.0,
          "three 1650 hp cloths sum to 4950, got " + std::to_string(packZombie.armorHp));
    check((packZombie.armorLayers[0].flags & pvz::engine::kArmorPassDamage) != 0,
          "the first cloth must keep its passdamage flag in the engine");
}

/// The case the old flat pool could not express: an invincible layer that blocks. Nothing may
/// die and nothing behind it may lose a hit point.
void testInvincibleBlocks(const pvz::Catalog& catalog) {
    World world(catalog, catalog.levels.at("frontyard_1"), 73);
    check(world.spawnZombie("kongfu_qigong_wave", 2), "kongfu_qigong_wave must spawn from the pack");
    const auto* zombie = world.zombies().empty() ? nullptr : &world.zombies().front();
    check(zombie != nullptr && zombie->armorLayers.size() == 1, "the nunchaku zombie carries one layer");
    check(zombie->armorLayers.front().hp == 0.0 && zombie->armorLayers.front().maxHp == 0.0,
          "an invincible layer must hold no hit points at all");
    const auto id = zombie->id;
    const double hpBefore = zombie->hp;
    world.damageZombie(id, 100000.0);
    check(world.zombieById(id)->alive, "an invincible blocking layer must keep the zombie alive");
    check(world.zombieById(id)->hp == hpBefore, "a blocked hit must not touch the body");
    bool blocked = false;
    for (const Json& entry : world.events())
        if (entry.value("type", std::string{}) == "armor_blocked") blocked = true;
    check(blocked, "a blocked hit must emit armor_blocked");

    // `ignoreArmor` is the one way past it (boss scripts and mower use that path).
    world.damageZombie(id, 50.0, true);
    check(world.zombieById(id)->hp < hpBefore, "ignoreArmor must still reach the body");
}

/// Regression for 2026-11-21: 20 content zombie ids also exist as rows in the sheet's
/// `zombies[]`, and 6 of those rows carry armor (`cowboy` → `CowboyHatDefault`). The first
/// wiring pass looked the bridge up first and then fell back to the sheet row by id, so
/// content zombies silently picked up pack armor they never had in `content/zombies.json`
/// (it showed up as a `world cowboy` hash change in the smoke gate). Content ids must read
/// content + bridge only; pack rows belong to pack-only zombies.
void testContentZombieKeepsContentArmor(const pvz::Catalog& catalog) {
    World world(catalog, catalog.levels.at("frontyard_1"), 91);
    check(world.spawnZombie("cowboy", 1), "cowboy must spawn from content");
    const auto* cowboy = world.zombies().empty() ? nullptr : &world.zombies().front();
    check(cowboy != nullptr, "cowboy must be in the list");
    check(cowboy->armorLayers.empty(),
          "cowboy has armor: [] in content; the sheet row must not leak in, got " +
              std::to_string(cowboy->armorLayers.size()));
    check(cowboy->armorHp == 0.0 && cowboy->armorMaxHp == 0.0,
          "cowboy must start with no armor pool, got " + std::to_string(cowboy->armorHp));

    // The other direction: a content zombie that really has armor keeps the content reading,
    // and the bridge only adds the flags the content array cannot express.
    check(world.spawnZombie("conehead", 2), "conehead must spawn from content");
    const auto& list = world.zombies();
    const auto conehead = std::find_if(list.begin(), list.end(), [](const auto& entry) {
        return entry.type == "conehead";
    });
    check(conehead != list.end() && conehead->armorLayers.size() == 1,
          "conehead keeps its single content armor piece");
    check(conehead->armorLayers.front().armorId == "ConeDefault",
          "conehead's armor must be the bridged ConeDefault");
    check(conehead->armorMaxHp == 370.0, "conehead's pool is the sheet's 370 hp");
}

void run(const fs::path& content, const fs::path& pack) {
    pvz::CatalogOptions options;
    options.contentPack = pack;
    const pvz::Catalog catalog = pvz::loadCatalog(content, options);
    check(catalog.rules != nullptr, "the rules pack must load for the armor tests");
    const ArmorTable& table = ArmorTable::shared();
    testCounts(table);
    testLayerOrderAndFlags(table);
    testInvincibleLayers(table);
    testContentBridge(table);
    testEngineLayers(catalog);
    testInvincibleBlocks(catalog);
    testContentZombieKeepsContentArmor(catalog);
}

} // namespace

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    if (argc < 4) {
        std::cerr << "usage: armor_test <content> <pack> <temp>\n";
        return 2;
    }
    try {
        run(fs::path{argv[1]}, fs::path{argv[2]});
    } catch (const std::exception& error) {
        std::cerr << "armor test failed: " << error.what() << '\n';
        return 1;
    }
    std::cout << "armor tests passed\n";
    return 0;
}
