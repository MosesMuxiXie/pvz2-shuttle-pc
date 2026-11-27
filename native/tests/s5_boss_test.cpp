#include "catalog.hpp"
#include "content/model.hpp"
#include "engine/boss.hpp"
#include "engine/world.hpp"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

pvz::Catalog load(const std::filesystem::path& content, const std::filesystem::path& pack) {
    pvz::CatalogOptions options;
    options.contentPack = pack;
    return pvz::loadCatalog(content, options);
}

/// A level with its wave schedule removed. The boss arrives after the last scheduled wave, so
/// this is the cheapest way to see one; `level.extra` (the module data the boss comes from) is
/// left exactly as shipped.
pvz::LevelDefinition bossArena(const pvz::LevelDefinition& source) {
    pvz::LevelDefinition level = source;
    level.waves.clear();
    level.sun = 9999;
    level.deck.clear(); // an empty deck disables the deck gate, so a test can plant freely
    return level;
}

bool hasBossMarker(const pvz::LevelDefinition& level) {
    if (!level.extra.is_object()) return false;
    const auto marker = level.extra.find("boss_zombie");
    if (marker != level.extra.end() && marker->is_string() && !marker->get<std::string>().empty()) return true;
    const auto alternate = level.extra.find("boss");
    return alternate != level.extra.end() && alternate->is_string() && !alternate->get<std::string>().empty();
}

/// The first boss level of a world, chosen by id so the test does not depend on file order.
std::string firstBossLevel(const pvz::Catalog& catalog, const std::string& world) {
    std::string best;
    for (const auto& [id, level] : catalog.levels) {
        if (!hasBossMarker(level)) continue;
        if (!world.empty() && level.world != world) continue;
        if (best.empty() || id < best) best = id;
    }
    return best;
}

const pvz::engine::ZombieEntity* bossEntity(const pvz::engine::World& world) {
    for (const auto& zombie : world.zombies()) {
        if (zombie.alive && zombie.isBoss) return &zombie;
    }
    return nullptr;
}

/// Step until `predicate` holds, up to `limit` ticks. Returns the tick it held, or 0.
template <typename Predicate>
std::uint64_t stepUntil(pvz::engine::World& world, std::uint64_t limit, Predicate predicate) {
    for (std::uint64_t i = 0; i < limit; ++i) {
        if (predicate()) return world.tick();
        world.step();
    }
    return predicate() ? world.tick() : 0;
}

void testBossSpawnsInBossLevel(const pvz::Catalog& catalog) {
    // Every boss level must either put a boss on the lawn or say that it could not - a silent
    // no-op is the bug this task exists to fix. The one exception is a level that is *also* a
    // vasebreaker board: since A1/T80 those run no wave director at all (`world.cpp:352`), so a
    // boss marker there can neither fire nor be refused. That combination is counted separately
    // and pinned, so a new one cannot slip in unnoticed.
    std::size_t marked = 0, spawned = 0, unavailable = 0, vaseMode = 0;
    for (const auto& [id, source] : catalog.levels) {
        if (!hasBossMarker(source)) continue;
        ++marked;
        if (source.extra.is_object()) {
            const auto vase = source.extra.find("vasebreaker");
            if (vase != source.extra.end() && vase->is_boolean() && vase->get<bool>()) {
                ++vaseMode;
                continue;
            }
        }
        pvz::engine::World world(catalog, bossArena(source), 7);
        world.step();
        if (world.bossSpawned()) {
            ++spawned;
        } else if (world.bossUnavailable() > 0) {
            ++unavailable;
        } else {
            throw std::runtime_error("boss level " + id + " neither spawned a boss nor reported boss_unavailable");
        }
    }
    check(marked == 71, "the shipped levels carry exactly 71 boss markers, got " + std::to_string(marked));
    check(vaseMode == 1, "exactly one boss level is also a vasebreaker board (pirate_41), got " +
                             std::to_string(vaseMode));
    check(spawned + unavailable + vaseMode == marked, "every boss level must be accounted for");
    check(spawned >= 60, "at least 60 boss levels must resolve to a boss, got " + std::to_string(spawned));

    const std::string levelId = firstBossLevel(catalog, "egypt");
    check(!levelId.empty(), "the egypt world has no boss level to test against");
    const auto level = bossArena(catalog.levels.at(levelId));
    pvz::engine::World world(catalog, level, 11);
    check(world.boss() != nullptr, "an egypt boss level must resolve to a boss definition");
    check(world.bossStageCount() == 3,
          "the egypt boss ships 3 stages, got " + std::to_string(world.bossStageCount()));
    check(!world.bossSpawned(), "the boss must not stand on the lawn before the waves are done");
    world.step();
    check(world.bossSpawned(), "the boss must spawn on the first tick after the wave schedule ends");
    const auto states = world.bossStates();
    check(states.size() == 1, "exactly one boss must be live, got " + std::to_string(states.size()));
    const auto* boss = world.boss();
    check(boss != nullptr, "the world must keep the resolved boss definition");
    check(std::abs(states.front().hp - boss->stages.front().hitPoints) < 1e-6,
          "stage 0 must start at the sheet's hitPoints");
    check(states.front().stages == 3, "the live boss must know it has 3 stages");
    const auto* entity = bossEntity(world);
    check(entity != nullptr, "the boss must be an entity on the lawn, not just a counter");
    check(entity->family == "boss", "the staged boss uses its own family, got " + entity->family);
    check(entity->speed == 0.0, "a staged boss does not walk");
    // The contract asks for the boss to reach `snapshot()`, i.e. the view path, not only the
    // internal pool.
    const auto snapshot = world.snapshot();
    const auto inSnapshot = std::find_if(snapshot.zombies.begin(), snapshot.zombies.end(),
                                         [&](const pvz::engine::ZombieView& view) { return view.type == entity->type; });
    check(inSnapshot != snapshot.zombies.end(), "the boss must appear in the snapshot the view reads");
}

void testStageProgression(const pvz::Catalog& catalog) {
    const std::string levelId = firstBossLevel(catalog, "egypt");
    check(!levelId.empty(), "the egypt world has no boss level to test against");
    pvz::engine::World world(catalog, bossArena(catalog.levels.at(levelId)), 13);
    world.step();
    check(world.bossSpawned(), "the boss must spawn before the stage test can run");
    const auto* boss = world.boss();
    check(boss != nullptr && boss->stages.size() == 3, "the egypt boss must have three stages");
    const pvz::engine::EntityId id = world.bossStates().front().id;

    // Drop stage 0 by exactly enough to cross it.
    world.damageZombie(id, boss->stages[0].hitPoints + 1.0);
    auto states = world.bossStates();
    check(states.size() == 1, "the boss must survive a stage change");
    check(states.front().stageIndex == 1, "crossing stage 0 must advance to stage 1");
    check(std::abs(states.front().hp - boss->stages[1].hitPoints) < 1e-6,
          "a stage change refills to the next stage's hitPoints");
    // `idleSeconds.max` and `stunSeconds` come straight from the sheet's stage entry.
    const auto idleTicks = static_cast<int>(boss->stages[1].idleMaxSeconds / pvz::engine::World::stepSeconds + 0.5);
    const auto stunTicks = static_cast<int>(boss->stages[1].stunSeconds / pvz::engine::World::stepSeconds + 0.5);
    check(states.front().idleTicks == idleTicks,
          "the idle window must be the sheet's idleSeconds.max, got " + std::to_string(states.front().idleTicks) +
              " want " + std::to_string(idleTicks));
    check(states.front().stunTicks == stunTicks,
          "the stun window must be the sheet's stunSeconds, got " + std::to_string(states.front().stunTicks) + " want " +
              std::to_string(stunTicks));

    // One hit never skips a stage, no matter how big it is.
    world.damageZombie(id, boss->stages[1].hitPoints * 10.0);
    states = world.bossStates();
    check(states.front().stageIndex == 2, "a huge hit must still advance exactly one stage");
    check(std::abs(states.front().hp - boss->stages[2].hitPoints) < 1e-6,
          "stage 2 must start at its own hitPoints");

    // The last stage is the kill.
    world.damageZombie(id, boss->stages[2].hitPoints + 1.0);
    check(world.bossStates().empty(), "killing the last stage must leave no live boss");
    check(world.killedZombies() == 1, "the boss counts as one kill");
}

void testFireActionHitsColumns(const pvz::Catalog& catalog) {
    // Find a boss whose first stage really declares a `Fire` window.
    std::string levelId;
    const pvz::engine::BossDefinition* chosen = nullptr;
    for (const auto& [id, source] : catalog.levels) {
        if (!hasBossMarker(source)) continue;
        pvz::engine::World probe(catalog, bossArena(source), 1);
        const auto* boss = probe.boss();
        if (boss == nullptr || boss->stages.empty()) continue;
        if (boss->stages.front().fireActions() == 0) continue;
        if (levelId.empty() || id < levelId) {
            levelId = id;
            chosen = boss;
        }
    }
    check(!levelId.empty() && chosen != nullptr, "no boss level declares a Fire action in its first stage");

    const auto level = bossArena(catalog.levels.at(levelId));
    pvz::engine::World world(catalog, level, 17);
    world.step();
    check(world.bossSpawned(), "the boss must spawn before the fire test can run");
    const auto* entity = bossEntity(world);
    check(entity != nullptr, "the boss must be on the lawn");
    const int bossRow = entity->row;
    const auto& stage = chosen->stages.front();
    const auto& action = [&]() -> const pvz::engine::BossStageAction& {
        for (const auto& entry : stage.actions) {
            if (entry.fire) return entry;
        }
        throw std::runtime_error("the chosen stage lost its fire action");
    }();
    const int low = std::min(action.fireMinColumn, action.fireMaxColumn);
    const int high = std::max(action.fireMinColumn, action.fireMaxColumn);
    const int inside = std::clamp(low, 0, world.cols() - 1);
    const int outside = std::clamp(high + 2, 0, world.cols() - 1);

    // The boss row is where the volley lands; `fireRowRange` widens that downward.
    check(world.plant("peashooter", bossRow, inside).empty(), "the target plant must be plantable");
    const pvz::engine::EntityId target = world.plantAt(bossRow, inside) != nullptr ? world.plantAt(bossRow, inside)->id : 0;
    check(target != 0, "the target plant must exist");
    if (outside != inside) {
        // A different species on purpose: planting the same card twice at tick 0 is refused by
        // the recharge gate, which is not what this test measures.
        check(world.plant("sunflower", bossRow, outside).empty(), "the control plant must be plantable");
    }

    const std::uint64_t firedAt = stepUntil(world, 900, [&]() {
        return world.plantById(target) == nullptr || !world.plantById(target)->alive;
    });
    check(firedAt != 0, "the boss never fired its declared column window");
    check(world.plantById(target) == nullptr || !world.plantById(target)->alive,
          "a plant inside FireMinColumn..FireMaxColumn must be destroyed by the volley");
    if (outside != inside) {
        const auto* control = world.plantAt(bossRow, outside);
        check(control != nullptr && control->alive, "a plant outside the column window must survive");
    }
}

void testUnavailableBossIsCounted(const pvz::Catalog& catalog) {
    // The sheet has no boss for `frontyard`/`muji`, yet 4 shipped levels mark one there; they
    // must be counted and reported, not silently turned into ordinary levels.
    std::string levelId;
    for (const auto& [id, source] : catalog.levels) {
        if (!hasBossMarker(source)) continue;
        pvz::engine::World probe(catalog, bossArena(source), 1);
        if (probe.boss() == nullptr && probe.bossUnavailable() > 0) {
            levelId = id;
            break;
        }
    }
    check(!levelId.empty(), "at least one boss level must be unresolvable (frontyard/muji) for this test");

    pvz::engine::World world(catalog, bossArena(catalog.levels.at(levelId)), 19);
    check(world.boss() == nullptr, "an unresolvable boss marker must not invent a boss");
    check(world.bossUnavailable() == 1, "an unresolvable boss marker must be counted exactly once");
    world.step();
    check(!world.bossSpawned(), "an unresolvable boss marker must not spawn anything");
    const auto& events = world.events();
    const auto reported = std::find_if(events.begin(), events.end(), [](const pvz::Json& entry) {
        return entry.value("type", std::string{}) == "boss_unavailable";
    });
    check(reported != events.end(), "the refusal must be visible as a boss_unavailable event");
    check(reported->value("details", pvz::Json::object()).value("level", std::string{}) == levelId,
          "the boss_unavailable event must name its level");
}

void testBossOffKeepsBaseline(const pvz::Catalog& catalog) {
    // Recorded from the pre-S5.8 binary (C:\pvzbuild\s5a) with exactly this construction and
    // 120 simulated seconds. `beach_19` differs from the `--boards` recording because the test
    // loads the catalog without a board-size override; the hash below is the like-for-like one.
    //
    // Re-pinned in S5.13: `beach_19` opens with three initial plants and `egypt_14` /
    // `mausoleum_40` carry their own field mechanics, so boss-off no longer reproduces the S5.8
    // numbers. What the test still guarantees is that turning the boss off removes every boss
    // contribution and leaves the field mechanics alone.
    //
    // Re-pinned again in T66: `mausoleum_40` also carries five dinosaur sweeps and five storms
    // (`spawners.dino` / `spawners.storm`), which now put zombies on the lawn over the 120 s
    // window. Its pin moved with that wiring; `beach_19` and `egypt_14` carry no special
    // spawners and kept theirs, which is exactly the check that the wiring is level-scoped.
    struct Baseline {
        const char* level;
        const char* hash;
    };
    const Baseline baselines[] = {{"beach_19", "0xd19e8983839045d1"},
                                  {"egypt_14", "0x59d4f87dd42ec2f4"},
                                  {"mausoleum_40", "0x50b67347cf5adc08"}};
    pvz::engine::WorldOptions off;
    off.boss = false;
    for (const auto& baseline : baselines) {
        const auto it = catalog.levels.find(baseline.level);
        check(it != catalog.levels.end(), std::string("missing baseline level ") + baseline.level);
        pvz::engine::World world(catalog, it->second, 1, off);
        world.advance(120.0);
        char buffer[32];
        std::snprintf(buffer, sizeof(buffer), "0x%016llx", static_cast<unsigned long long>(world.hash()));
        check(std::string(buffer) == baseline.hash,
              std::string("--boss off must reproduce the pre-boss hash for ") + baseline.level + ", got " + buffer +
                  " want " + baseline.hash);    }
    // A level without a boss marker hashes identically either way, which is what makes the
    // option safe to default on.
    const auto plain = catalog.levels.at("frontyard_1");
    pvz::engine::World withBoss(catalog, plain, 1);
    pvz::engine::World withoutBoss(catalog, plain, 1, off);
    withBoss.advance(30.0);
    withoutBoss.advance(30.0);
    check(withBoss.hash() == withoutBoss.hash(), "a level without a boss marker must hash the same with the option off");
}

} // namespace

#ifdef _WIN32
int wmain(int argc, wchar_t** argv)
#else
int main(int argc, char** argv)
#endif
{
    if (argc < 4) {
        std::fprintf(stderr, "usage: s5_boss_test <content> <pack> <temp>\n");
        return 2;
    }
    try {
        const pvz::Catalog catalog = load(argv[1], argv[2]);
        check(catalog.levels.size() == 1809, "the catalog must carry 1809 levels");
        check(catalog.rules != nullptr, "the content pack must load");
        testBossSpawnsInBossLevel(catalog);
        testStageProgression(catalog);
        testFireActionHitsColumns(catalog);
        testUnavailableBossIsCounted(catalog);
        testBossOffKeepsBaseline(catalog);
        std::printf("PASS s5 boss runtime\n");
    } catch (const std::exception& error) {
        std::printf("s5 boss test failed: %s\n", error.what());
        return 1;
    }
    return 0;
}
