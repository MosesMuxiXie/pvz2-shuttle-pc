#include "simulation.hpp"
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
using namespace pvz;
void check(bool ok, const std::string& msg) {
    if (!ok)
        throw std::runtime_error(msg);
}
bool hasEvent(const Battle& b, const std::string& type) {
    for (const auto& e : b.events())
        if (e.at("type") == type)
            return true;
    return false;
}
#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    try {
        check(argc == 2, "expected content directory");
        auto c = loadCatalog(std::filesystem::path(argv[1]));
        auto fixture = c.levels.at("frontyard_1");
        fixture.sun = 1000;
        fixture.waves = {WaveDefinition{180, false, {{"basic", 0, {}}}}};
        Battle b(c, fixture, 42);
        check(b.plant("sunflower", 0, 0) == "ok" && b.sun() == 950, "plant debit");
        auto before = b.snapshot();
        check(b.plant("sunflower", 0, 1) == "cooldown" && b.snapshot() == before, "cooldown no debit");
        check(b.plant("wallnut", 0, 0) == "occupied" && b.sun() == 950, "occupied no debit");
        check(b.plant("wallnut", -1, 0) == "outside" && b.plant("wallnut", 0, 9) == "outside",
              "board bounds");
        check(b.plant("cherrybomb", 0, 1) == "not-in-deck", "deck enforcement");
        b.pause(true);
        before = b.snapshot();
        b.advance(10);
        check(b.snapshot() == before && b.plant("wallnut", 0, 1) == "inactive",
              "pause freezes simulation/input");
        b.pause(false);
        b.advance(6);
        check(b.tick() == 360 && b.suns().size() == 2, "sky and producer sun timers");
        const auto sunId = b.suns().front().id;
        check(b.collect(sunId) && b.sun() == 975, "collect sun");
        check(!b.collect(sunId) && b.sun() == 975, "cannot collect twice");
        check(b.shovel(0, 0) && b.plants().empty() && !b.shovel(0, 0), "shovel state");
        check(b.plant("sunflower", 0, 1) == "ok", "cooldown expiry");
        auto poor = fixture;
        poor.sun = 0;
        Battle funds(c, poor);
        check(funds.plant("sunflower", 0, 0) == "sun" && funds.sun() == 0, "insufficient sun");
        // Same inputs at the same simulation ticks, independent of display frame rate.
        fixture.waves = {WaveDefinition{1, false, {{"basic", std::nullopt, {}}}},
                         WaveDefinition{1, false, {{"conehead", 0, {}}}}};
        Battle a(c, fixture, 123), d(c, fixture, 123), e(c, fixture, 123);
        check(a.plant("peashooter", 0, 0) == "ok" && d.plant("peashooter", 0, 0) == "ok" &&
                  e.plant("peashooter", 0, 0) == "ok",
              "setup");
        for (int i = 0; i < 300; ++i)
            a.advance(1.0 / 30);
        for (int i = 0; i < 600; ++i)
            d.advance(1.0 / 60);
        for (int i = 0; i < 1200; ++i)
            e.advance(1.0 / 120);
        check(a.snapshot() == d.snapshot() && a.snapshot() == e.snapshot() && a.events() == d.events() &&
                  a.events() == e.events(),
              "30/60/120 Hz deterministic replay");
        check(a.wave() == 2 && hasEvent(a, "shot") && hasEvent(a, "hit"), "waves and projectile collision");
        check(a.zombies().back().hp == 190 && a.zombies().back().armor < 370, "armor absorbs before health");
        bool rejected = false;
        try {
            a.advance(std::numeric_limits<double>::quiet_NaN());
        } catch (const std::exception&) {
            rejected = true;
        }
        check(rejected, "reject non-finite delta");
        // A ready mine can kill armor-bearing targets, then leaves the grid.
        auto mine = fixture;
        mine.waves = {WaveDefinition{0.1, false, {{"conehead", 0, {}}}}};
        c.plants.at("potatomine").raw["delay"] = 0.1;
        Battle m(c, mine);
        check(m.plant("potatomine", 0, 8) == "ok", "mine placement");
        m.advance(20);
        check(m.status() == "won" && hasEvent(m, "explosion") && m.plants().empty(),
              "mine detonation and win");
        before = m.snapshot();
        m.advance(20);
        check(m.snapshot() == before, "terminal state freezes");
        // First empty-lawn wave uses a mower; a later wave breaches the same lane.
        auto loss = fixture;
        loss.waves = {WaveDefinition{0.1, false, {{"basic", 0, {}}}},
                      WaveDefinition{30, false, {{"basic", 0, {}}}}};
        c.zombies.at("basic").speed = 2;
        Battle lost(c, loss);
        lost.advance(60);
        check(lost.status() == "lost" && hasEvent(lost, "mower") && hasEvent(lost, "lost"),
              "mower is single use, breach loses");
        auto eating = fixture;
        eating.waves = {WaveDefinition{0.1, false, {{"basic", 0, {}}}},
                        WaveDefinition{100, false, {{"basic", 1, {}}}}};
        c.zombies.at("basic").eatDps = 10000;
        Battle eater(c, eating);
        check(eater.plant("wallnut", 0, 8) == "ok", "wall setup");
        eater.advance(2);
        check(eater.plants().empty() && hasEvent(eater, "plant-eaten"), "zombie eating");
        auto unsupported = fixture;
        unsupported.extra["boss"] = true;
        rejected = false;
        try {
            Battle invalid(c, unsupported);
        } catch (const std::exception&) {
            rejected = true;
        }
        check(rejected, "no silent boss fallback");
        // C54: the refusal is enumerable, so `--simulate` can name the rule it cannot honour.
        const auto bossRules = Battle::unsupportedRules(unsupported);
        check(bossRules.size() == 1 && bossRules.front() == "level rule 'boss'",
              "a boss level must be refused by rule name");
        check(Battle::unsupportedRules(fixture).empty(),
              "a plain frontyard level must report no unsupported rules");
        unsupported = fixture;
        unsupported.deck.push_back("cabbagepult");
        rejected = false;
        try {
            Battle invalid(c, unsupported);
        } catch (const std::exception&) {
            rejected = true;
        }
        check(rejected, "no silent plant fallback");
        // Real catalog replay (no cheats, no player inputs) must produce a deterministic defeat.
        auto real = loadCatalog(std::filesystem::path(argv[1]));
        Battle first(real, real.levels.at("frontyard_1"), 7);
        first.advance(240);
        check(first.status() == "lost" && first.tick() > 0, "real frontyard loss replay");
        // An input-only economy/defense policy must clear the real first level without
        // changing its starting sun, definitions, wave counts or mower inventory.
        Battle playable(real, real.levels.at("frontyard_1"), 7);
        for (int tick = 0; tick < 60 * 360 && playable.status() == "playing"; ++tick) {
            if (tick % 60 == 0) {
                std::vector<std::uint64_t> suns;
                for (const auto& s : playable.suns())
                    suns.push_back(s.id);
                for (auto id : suns)
                    (void)playable.collect(id);
                int flowers = 0;
                int shooters[5] = {};
                for (const auto& p : playable.plants()) {
                    if (p.type == "sunflower")
                        ++flowers;
                    if (p.type == "peashooter")
                        ++shooters[p.row];
                }
                bool placed = false;
                if (flowers < 5) {
                    for (int row = 0; row < 5 && !placed; ++row)
                        placed = playable.plant("sunflower", row, 0) == "ok";
                }
                if (!placed) {
                    int rowToProtect = -1;
                    double threat = -1;
                    for (const auto& z : playable.zombies()) {
                        const double score =
                            (z.hp + z.armor) / (std::max(0.1, z.x) + 2.0) / (1.0 + 4.0 * shooters[z.row]);
                        if (shooters[z.row] < 3 && score > threat) {
                            threat = score;
                            rowToProtect = z.row;
                        }
                    }
                    if (rowToProtect >= 0)
                        for (int col = 2; col < 5 && !placed; ++col)
                            placed = playable.plant("peashooter", rowToProtect, col) == "ok";
                }
            }
            playable.step();
        }
        check(playable.status() == "won",
              "real frontyard must be winnable by legal input replay: " + playable.status());
        std::cout << "PASS real frontyard legal-input victory at tick " << playable.tick() << '\n';
        std::cout << "PASS planting, cooldowns, sun, pause, replay, armor, mine, mower, eating, terminal "
                     "states and real level\n";
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << "FAIL " << ex.what() << '\n';
        return 1;
    }
}
