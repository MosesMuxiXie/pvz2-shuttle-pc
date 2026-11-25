#include "simulation.hpp"
#include <algorithm>
#include <cmath>
#include <set>
#include <stdexcept>
namespace pvz {
namespace {
std::uint64_t ticks(double seconds) {
    if (!std::isfinite(seconds) || seconds < 0 || seconds > 86400)
        throw std::runtime_error("battle timer must be within 0..86400 seconds");
    return static_cast<std::uint64_t>(std::ceil(seconds * 60.0 - 1e-9));
}
void supported(bool ok, const std::string& detail) {
    if (!ok)
        throw std::runtime_error("native battle preview does not support " + detail);
}
} // namespace
std::vector<std::string> Battle::unsupportedRules(const LevelDefinition& level) {
    // C54: the legacy preview is kept only for `--simulate` and its own tests (four plants,
    // three zombie types, one world). It must never pretend to run a level rule it does not
    // implement, so the boundary is enumerable instead of an opaque constructor throw: the
    // CLI prints exactly which rules it cannot honour and exits without simulating.
    std::vector<std::string> rules;
    if (level.world != "frontyard")
        rules.push_back("world '" + level.world + "'");
    if (level.synthesized())
        rules.push_back("synthesized levels");
    for (const auto& flag : {"boss", "vasebreaker", "night", "minecarts"})
        if (level.extra.contains(flag) && level.extra[flag] != false)
            rules.push_back("level rule '" + std::string(flag) + "'");
    if (!(level.rows > 0 && level.rows <= 8 && level.cols > 0 && level.cols <= 12))
        rules.push_back("board dimensions");
    return rules;
}
Battle::Battle(const Catalog& catalog, const LevelDefinition& level, std::uint32_t seed)
    : catalog_(catalog), level_(level), rng_(seed ? seed : 1), sun_(level.sun) {
    const auto unsupported = unsupportedRules(level);
    supported(unsupported.empty(), unsupported.empty() ? "" : unsupported.front());
    const std::set<std::string> plants{"sunflower", "peashooter", "wallnut", "potatomine"};
    const std::set<std::string> zombies{"basic", "conehead", "buckethead"};
    for (const auto& id : level.deck)
        supported(plants.contains(id) && catalog.plants.contains(id), "plant '" + id + "'");
    double due = 0;
    for (const auto& wave : level.waves) {
        due += wave.delay;
        waveTicks_.push_back(ticks(due));
        for (const auto& spawn : wave.zombies) {
            supported(zombies.contains(spawn.type) && catalog.zombies.contains(spawn.type),
                      "zombie '" + spawn.type + "'");
            if (spawn.row)
                supported(*spawn.row >= 0 && *spawn.row < level.rows, "spawn row");
            for (int row : spawn.rows)
                supported(row >= 0 && row < level.rows, "spawn rows");
        }
    }
    for (int row = 0; row < level.rows; ++row)
        mowers_.push_back({row, -0.5, 0});
    event("start", {{"level", level.id}, {"seed", rng_}});
}
std::uint32_t Battle::random() {
    rng_ ^= rng_ << 13;
    rng_ ^= rng_ >> 17;
    rng_ ^= rng_ << 5;
    return rng_;
}
void Battle::event(const std::string& type, Json details) {
    details["type"] = type;
    details["tick"] = tick_;
    events_.push_back(std::move(details));
}
std::uint64_t Battle::cooldown(const std::string& type) const {
    const auto it = cooldowns_.find(type);
    return it == cooldowns_.end() || it->second <= tick_ ? 0 : it->second - tick_;
}
std::string Battle::plant(const std::string& type, int row, int col) {
    if (paused_ || status_ != "playing")
        return "inactive";
    if (row < 0 || row >= level_.rows || col < 0 || col >= level_.cols)
        return "outside";
    if (std::find(level_.deck.begin(), level_.deck.end(), type) == level_.deck.end())
        return "not-in-deck";
    for (const auto& p : plants_)
        if (p.row == row && p.col == col)
            return "occupied";
    if (cooldown(type) > 0)
        return "cooldown";
    const auto& def = catalog_.plants.at(type);
    if (sun_ < def.cost)
        return "sun";
    sun_ -= def.cost;
    cooldowns_[type] = tick_ + ticks(def.cooldown);
    const auto id = nextId_++;
    plants_.push_back({id, type, row, col, def.hp, tick_, tick_ + ticks(type == "sunflower" ? 6.0 : 0.35)});
    event("plant", {{"id", id}, {"plant", type}, {"row", row}, {"col", col}});
    return "ok";
}
bool Battle::shovel(int row, int col) {
    if (paused_ || status_ != "playing")
        return false;
    const auto it = std::find_if(plants_.begin(), plants_.end(),
                                 [&](const auto& p) { return p.row == row && p.col == col; });
    if (it == plants_.end())
        return false;
    event("shovel", {{"id", it->id}});
    plants_.erase(it);
    return true;
}
bool Battle::collect(std::uint64_t id) {
    if (paused_ || status_ != "playing")
        return false;
    const auto it = std::find_if(suns_.begin(), suns_.end(), [&](const auto& s) { return s.id == id; });
    if (it == suns_.end())
        return false;
    sun_ += it->value;
    event("collect", {{"id", id}, {"sun", sun_}});
    suns_.erase(it);
    return true;
}
void Battle::addSun(double x, double row, int value) {
    const auto id = nextId_++;
    suns_.push_back({id, x, row, value, tick_ + 600});
    event("sun", {{"id", id}, {"value", value}});
}
void Battle::damage(BattleZombie& z, double amount, bool ignoreArmor) {
    if (z.hp <= 0)
        return;
    if (!ignoreArmor) {
        const auto absorbed = std::min(z.armor, amount);
        z.armor -= absorbed;
        amount -= absorbed;
    }
    z.hp = std::max(0.0, z.hp - amount);
    event("hit", {{"id", z.id}, {"hp", z.hp}, {"armor", z.armor}});
    if (z.hp == 0)
        event("kill", {{"id", z.id}});
}
void Battle::advance(double seconds) {
    if (!std::isfinite(seconds) || seconds < 0 || seconds > 600)
        throw std::invalid_argument("frame delta must be finite and within 0..600 seconds");
    if (paused_ || status_ != "playing")
        return;
    accumulator_ += seconds;
    while (accumulator_ + 1e-10 >= stepSeconds && status_ == "playing") {
        accumulator_ -= stepSeconds;
        step();
    }
    if (std::abs(accumulator_) < 1e-10 || status_ != "playing")
        accumulator_ = 0;
}
void Battle::step() {
    if (paused_ || status_ != "playing")
        return;
    ++tick_;
    while (nextWave_ < waveTicks_.size() && tick_ >= waveTicks_[nextWave_]) {
        const auto& wave = level_.waves[nextWave_++];
        event("wave", {{"index", nextWave_}, {"flag", wave.flag}});
        // Use exactly the catalog spawns. The Python baseline's random flag multiplier
        // is an unverified approximation, not an APK rule that may be claimed as parity.
        for (const auto& spawn : wave.zombies) {
            auto rows = spawn.rows;
            if (rows.empty())
                rows.push_back(spawn.row ? *spawn.row
                                         : static_cast<int>(random() % static_cast<unsigned>(level_.rows)));
            for (const int row : rows) {
                const auto& def = catalog_.zombies.at(spawn.type);
                double armor = 0;
                for (double hp : def.armor)
                    armor += hp;
                const auto id = nextId_++;
                zombies_.push_back({id, spawn.type, row, level_.cols + 0.5, def.hp, armor});
                event("spawn", {{"id", id}, {"zombie", spawn.type}, {"row", row}});
            }
        }
    }
    if (tick_ >= nextSkySun_) {
        const double x = 0.5 + static_cast<double>(random() % static_cast<unsigned>(level_.cols));
        const double row = 0.3 + static_cast<double>(random() % static_cast<unsigned>(level_.rows));
        addSun(x, row, 25);
        nextSkySun_ = tick_ + 480;
    }
    for (auto& p : plants_) {
        if (p.hp <= 0)
            continue;
        const auto& def = catalog_.plants.at(p.type);
        const double x = p.col + 0.5;
        if (p.type == "sunflower" && tick_ >= p.nextAction) {
            addSun(x, p.row + 0.3, def.raw.value("sun_value", 25));
            p.nextAction = tick_ + std::max<std::uint64_t>(1, ticks(def.raw.value("sun_interval", 24.0)));
        } else if (p.type == "peashooter" && tick_ >= p.nextAction) {
            const bool target = std::any_of(zombies_.begin(), zombies_.end(), [&](const auto& z) {
                return z.hp > 0 && z.row == p.row && z.x >= x - 0.1;
            });
            if (target) {
                const auto id = nextId_++;
                shots_.push_back({id, p.row, x + 0.3, def.damage});
                p.nextAction = tick_ + std::max<std::uint64_t>(1, ticks(def.interval));
                event("shot", {{"id", id}, {"plant", p.id}});
            }
        } else if (p.type == "potatomine" && tick_ >= p.born + ticks(def.raw.value("delay", 14.0))) {
            const bool trigger = std::any_of(zombies_.begin(), zombies_.end(), [&](const auto& z) {
                return z.hp > 0 && z.row == p.row && std::abs(z.x - x) <= 0.55;
            });
            if (trigger) {
                event("explosion", {{"plant", p.id}});
                p.hp = 0;
                for (auto& z : zombies_)
                    if (z.hp > 0 && z.row == p.row && std::abs(z.x - x) <= 1.0)
                        damage(z, def.damage, true);
            }
        }
    }
    for (auto& shot : shots_) {
        const double end = shot.x + 5.2 * stepSeconds;
        BattleZombie* target = nullptr;
        for (auto& z : zombies_)
            if (z.hp > 0 && z.row == shot.row && z.x + 0.25 >= shot.x && z.x - 0.25 <= end &&
                (!target || z.x < target->x))
                target = &z;
        if (target) {
            damage(*target, shot.damage);
            shot.damage = 0;
        }
        shot.x = end;
    }
    for (auto& z : zombies_) {
        if (z.hp <= 0)
            continue;
        BattlePlant* target = nullptr;
        for (auto& p : plants_)
            if (p.hp > 0 && p.row == z.row && p.type != "potatomine" && z.x >= p.col + 0.35 &&
                z.x <= p.col + 1.15 && (!target || p.col > target->col))
                target = &p;
        const auto& def = catalog_.zombies.at(z.type);
        if (target) {
            target->hp -= def.eatDps * stepSeconds;
            if (target->hp <= 0)
                event("plant-eaten", {{"id", target->id}});
        } else
            z.x -= def.speed * stepSeconds;
    }
    for (auto& mower : mowers_) {
        if (mower.state == 0 && std::any_of(zombies_.begin(), zombies_.end(), [&](const auto& z) {
                return z.hp > 0 && z.row == mower.row && z.x <= -0.25;
            })) {
            mower.state = 1;
            event("mower", {{"row", mower.row}});
        }
        if (mower.state == 1) {
            const double end = mower.x + 5.2 * stepSeconds;
            for (auto& z : zombies_)
                if (z.hp > 0 && z.row == mower.row && z.x >= mower.x - 0.4 && z.x <= end + 0.4)
                    damage(z, z.hp, true);
            mower.x = end;
            if (mower.x > level_.cols + 1)
                mower.state = 2;
        }
    }
    const bool breach =
        std::any_of(zombies_.begin(), zombies_.end(), [](const auto& z) { return z.hp > 0 && z.x < -0.7; });
    std::erase_if(plants_, [](const auto& p) { return p.hp <= 0; });
    std::erase_if(zombies_, [](const auto& z) { return z.hp <= 0; });
    std::erase_if(shots_, [&](const auto& p) { return p.damage <= 0 || p.x > level_.cols + 1; });
    std::erase_if(suns_, [&](const auto& s) { return s.expires <= tick_; });
    if (breach) {
        status_ = "lost";
        event("lost");
    } else if (nextWave_ == level_.waves.size() && zombies_.empty()) {
        status_ = "won";
        event("won");
    }
}
Json Battle::snapshot() const {
    Json j = {{"level", level_.id},
              {"tick", tick_},
              {"status", status_},
              {"paused", paused_},
              {"sun", sun_},
              {"wave", nextWave_},
              {"rng", rng_},
              {"next_id", nextId_},
              {"next_sky_sun", nextSkySun_},
              {"cooldowns", cooldowns_}};
    for (const auto& key : {"plants", "zombies", "shots", "suns", "mowers"})
        j[key] = Json::array();
    for (const auto& p : plants_)
        j["plants"].push_back({{"id", p.id},
                               {"type", p.type},
                               {"row", p.row},
                               {"col", p.col},
                               {"hp", p.hp},
                               {"born", p.born},
                               {"next_action", p.nextAction}});
    for (const auto& z : zombies_)
        j["zombies"].push_back(
            {{"id", z.id}, {"type", z.type}, {"row", z.row}, {"x", z.x}, {"hp", z.hp}, {"armor", z.armor}});
    for (const auto& s : shots_)
        j["shots"].push_back({{"id", s.id}, {"row", s.row}, {"x", s.x}, {"damage", s.damage}});
    for (const auto& s : suns_)
        j["suns"].push_back(
            {{"id", s.id}, {"row", s.row}, {"x", s.x}, {"value", s.value}, {"expires", s.expires}});
    for (const auto& m : mowers_)
        j["mowers"].push_back({{"row", m.row}, {"x", m.x}, {"state", m.state}});
    return j;
}
} // namespace pvz
