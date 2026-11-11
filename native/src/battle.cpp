#include "battle.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace shuttle {
namespace {

constexpr double stepSeconds = 1.0 / Battle::ticksPerSecond;
constexpr double shotSpeed = 7.0;
constexpr double mowerSpeed = 5.0;

int ticks(double seconds) {
    if (!std::isfinite(seconds) || seconds < 0 || seconds > 3600) {
        throw std::runtime_error("Unsupported battle timer");
    }
    return static_cast<int>(std::ceil(seconds * Battle::ticksPerSecond - 1e-8));
}

Battle::Card makeCard(const std::string& id, const nlohmann::json& definition) {
    using Kind = Battle::PlantKind;
    const auto behavior = definition.at("behavior").get<std::string>();
    Kind kind;
    double interval = 0;
    if (behavior == "produce") {
        kind = Kind::producer;
        interval = definition.at("sun_interval").get<double>();
    } else if (behavior == "shoot") {
        kind = Kind::shooter;
        interval = definition.at("interval").get<double>();
    } else if (behavior == "mine") {
        kind = Kind::mine;
        interval = definition.at("delay").get<double>();
    } else if (behavior == "wall") {
        kind = Kind::blocker;
    } else {
        throw std::runtime_error("Unsupported seed behavior: " + id);
    }
    return {id, definition.value("name_en", id), kind, definition.at("cost").get<int>(),
            definition.at("hp").get<double>(), definition.value("damage", 0.0),
            ticks(definition.at("cooldown").get<double>()), ticks(interval), definition.value("sun_value", 25)};
}

bool onBoard(int row, int col) {
    return row >= 0 && row < Battle::rows && col >= 0 && col < Battle::columns;
}

}

Battle::Battle(const Catalog& catalog, const LevelDefinition& level, std::uint32_t seed, EventSink sink)
    : random_(seed), sink_(std::move(sink)), seedBank_(level.seedBank), sun_(level.sun),
      nextSkySun_(ticks(level.extra.value("first_sun", 4.5))),
      skySunBase_(level.extra.value("sky_sun_interval", 8.0)),
      skySunRange_(level.extra.value("sky_sun_range", 0.0)),
      skySunIncrease_(level.extra.value("sky_sun_increase", 0.0)),
      skySunCap_(level.extra.value("sky_sun_cap", 3600.0)) {
    ticks(skySunBase_);
    ticks(skySunIncrease_);
    ticks(skySunCap_ + skySunRange_);
    if (skySunRange_ < 0 || skySunCap_ < skySunBase_) {
        throw std::runtime_error("Invalid sky sun configuration");
    }
    if (const auto timing = level.extra.find("wave_timing"); timing != level.extra.end()) {
        adaptiveTiming_ = true;
        waveTiming_ = {timing->at("jitter").get<double>(), timing->at("health_min").get<double>(),
                       timing->at("health_max").get<double>(), ticks(timing->at("minimum_gap").get<double>()),
                       ticks(timing->at("flag_warning").get<double>())};
        ticks(waveTiming_.jitter);
        if (!std::isfinite(waveTiming_.healthMin) || !std::isfinite(waveTiming_.healthMax) ||
            waveTiming_.healthMin < 0 || waveTiming_.healthMax > 1 || waveTiming_.healthMin > waveTiming_.healthMax) {
            throw std::runtime_error("Invalid wave health threshold");
        }
    }
    for (const auto& id : level.deck) {
        cards_.push_back(makeCard(id, catalog.plants.at(id)));
    }

    for (const auto& wave : level.waves) {
        auto& spawns = waves_.emplace_back(Wave{ticks(wave.delay), wave.flag, {}}).zombies;
        std::array<double, rows> nextX;
        nextX.fill(columns + 0.2);
        for (const auto& spawn : wave.zombies) {
            const auto& definition = catalog.zombies.at(spawn.type);
            const double body = definition.at("hp").get<double>();
            double armor = 0;
            if (const auto entries = definition.find("armor"); entries != definition.end()) {
                for (const auto& entry : *entries) {
                    armor += entry.at("hp").get<double>();
                }
            }
            const auto append = [&](int row) {
                spawns.push_back({row, nextX[row], body + armor, definition.at("speed").get<double>(),
                                  definition.at("eat_dps").get<double>(), armor > 0, spawn.type});
                nextX[row] += 0.65;
            };
            bool expanded = false;
            for (const auto row : spawn.rows) {
                if (row >= 0 && row < rows) {
                    append(row);
                    expanded = true;
                }
            }
            if (!expanded) {
                const int row = spawn.row.value_or(-1);
                append(row >= 0 && row < rows ? row : static_cast<int>(random_() % rows));
            }
        }
        int remainingFood = wave.additionalPlantfood;
        for (auto& zombie : spawns) {
            if (remainingFood <= 0) {
                break;
            }
            if (catalog.zombies.at(zombie.type).value("can_spawn_plantfood", true)) {
                zombie.carriesPlantfood = true;
                --remainingFood;
            }
        }
    }
    if (!waves_.empty()) {
        nextWaveAt_ = waves_.front().delay;
    }
}

double Battle::sample(double minimum, double maximum) {
    if (minimum == maximum) {
        return minimum;
    }
    constexpr double rngRange = static_cast<double>(std::mt19937::max()) + 1.0;
    return minimum + (maximum - minimum) * (static_cast<double>(random_()) / rngRange);
}

bool Battle::toggleCard(int card) {
    if (phase_ != Phase::choosing || card < 0 || static_cast<std::size_t>(card) >= cards_.size()) {
        return false;
    }
    auto& entry = cards_[card];
    if (!entry.selected && std::ranges::count(cards_, true, &Card::selected) >= seedBank_) {
        return false;
    }
    entry.selected = !entry.selected;
    emit("seed_toggled", [&] { return nlohmann::json{{"card", card}, {"plant", entry.id}, {"selected", entry.selected}}; });
    return true;
}

bool Battle::start() {
    if (phase_ != Phase::choosing || !std::ranges::any_of(cards_, &Card::selected)) {
        return false;
    }
    phase_ = Phase::playing;
    emit("battle_started", [&] { return nlohmann::json{{"sun", sun_}, {"waves", waves_.size()}}; });
    return true;
}

bool Battle::plant(int card, int row, int col) {
    if (phase_ != Phase::playing || !onBoard(row, col) || card < 0 ||
        static_cast<std::size_t>(card) >= cards_.size()) {
        return false;
    }
    auto& entry = cards_[card];
    if (!entry.selected || tick_ < entry.availableAt || sun_ < entry.cost ||
        std::ranges::any_of(plants_, [=](const Plant& p) { return p.row == row && p.col == col; })) {
        return false;
    }
    const int firstAction = entry.kind == PlantKind::shooter ? tick_ : tick_ + entry.interval;
    plants_.push_back({card, row, col, entry.hp, firstAction});
    entry.availableAt = tick_ + entry.recharge;
    sun_ -= entry.cost;
    emit("plant_placed", [&] {
        return nlohmann::json{{"plant", entry.id}, {"row", row}, {"col", col}, {"cost", entry.cost}, {"sun", sun_}};
    });
    return true;
}

bool Battle::shovel(int row, int col) {
    if (phase_ != Phase::playing ||
        std::erase_if(plants_, [=](const Plant& p) { return p.row == row && p.col == col; }) == 0) {
        return false;
    }
    emit("plant_removed", [&] { return nlohmann::json{{"row", row}, {"col", col}, {"source", "shovel"}}; });
    return true;
}

bool Battle::collectSun(int row, int col) {
    if (phase_ != Phase::playing) {
        return false;
    }
    const auto match = std::ranges::find_if(suns_, [=](const Sun& sun) { return sun.row == row && sun.col == col; });
    if (match == suns_.end()) {
        return false;
    }
    sun_ += match->value;
    emit("sun_collected", [&] { return nlohmann::json{{"row", row}, {"col", col}, {"amount", match->value}, {"sun", sun_}}; });
    suns_.erase(match);
    return true;
}

bool Battle::collectPlantfood(int row, int col) {
    if (phase_ != Phase::playing) {
        return false;
    }
    const auto match = std::ranges::find_if(plantfoodDrops_, [=](const Plantfood& drop) {
        return drop.row == row && drop.col == col;
    });
    if (match == plantfoodDrops_.end()) {
        return false;
    }
    plantfoodDrops_.erase(match);
    ++plantfood_;
    emit("plantfood_collected", [&] { return nlohmann::json{{"row", row}, {"col", col}, {"inventory", plantfood_}}; });
    return true;
}

void Battle::addSun(int row, int col, int value, const char* source) {
    suns_.push_back({row, col, value, tick_ + 10 * ticksPerSecond});
    emit("sun_dropped", [&] { return nlohmann::json{{"row", row}, {"col", col}, {"amount", value}, {"source", source}}; });
}

void Battle::finish(Phase phase) {
    phase_ = phase;
    emit("battle_finished", [&] {
        return nlohmann::json{{"result", phase == Phase::won ? "won" : "lost"}, {"waves_started", wavesStarted_}};
    });
}

void Battle::updateWaves() {
    if (wavesStarted_ >= waves_.size()) {
        return;
    }
    bool early = false;
    if (!flagWarning_ && adaptiveTiming_ && wavesStarted_ > 0 && tick_ - lastWaveAt_ >= waveTiming_.minimumGap) {
        double remainingHealth = 0;
        for (const auto& zombie : zombies_) {
            if (zombie.wave == wavesStarted_) {
                remainingHealth += std::trunc(zombie.hp);
            }
        }
        early = remainingHealth <= waveHealthThreshold_ && tick_ < nextWaveAt_;
    }
    if (!early && tick_ < nextWaveAt_) {
        return;
    }
    const auto& wave = waves_[wavesStarted_];
    const char* trigger = flagWarning_ ? "warning_elapsed" : early ? "health" : "timer";
    if (wave.flag && !flagWarning_ && waveTiming_.warning > 0) {
        flagWarning_ = true;
        nextWaveAt_ = tick_ + waveTiming_.warning;
        emit("flag_warning", [&] {
            return nlohmann::json{{"wave", wavesStarted_ + 1}, {"spawn_tick", nextWaveAt_}, {"trigger", trigger}};
        });
        return;
    }
    flagWarning_ = false;
    ++wavesStarted_;
    lastWaveAt_ = tick_;
    emit("wave_started", [&] {
        return nlohmann::json{{"wave", wavesStarted_}, {"flag", wave.flag}, {"trigger", trigger}};
    });
    double initialHealth = 0;
    for (auto zombie : wave.zombies) {
        zombie.id = ++nextZombieId_;
        zombie.wave = wavesStarted_;
        initialHealth += zombie.hp;
        emit("zombie_spawned", [&] {
            return nlohmann::json{{"zombie", zombie.type}, {"id", zombie.id}, {"row", zombie.row},
                                  {"wave", zombie.wave}, {"hp", zombie.hp}, {"plantfood", zombie.carriesPlantfood}};
        });
        zombies_.push_back(std::move(zombie));
    }
    if (wavesStarted_ < waves_.size()) {
        const auto& next = waves_[wavesStarted_];
        nextWaveAt_ = tick_ + next.delay + (next.flag ? 0 : ticks(sample(0, waveTiming_.jitter)));
        waveHealthThreshold_ = std::trunc(initialHealth * sample(waveTiming_.healthMin, waveTiming_.healthMax));
        emit("wave_scheduled", [&] {
            return nlohmann::json{{"wave", wavesStarted_ + 1}, {"timer_tick", nextWaveAt_},
                                  {"health_threshold", waveHealthThreshold_}};
        });
    }
}

void Battle::step() {
    if (phase_ != Phase::playing) {
        return;
    }
    ++tick_;
    if (tick_ >= nextSkySun_) {
        const int row = static_cast<int>(random_() % rows);
        const int col = static_cast<int>(random_() % columns);
        addSun(row, col, 25, "sky");
        const double base = std::min(skySunCap_, skySunBase_ + ++scheduledSkySuns_ * skySunIncrease_);
        nextSkySun_ = tick_ + std::max(1, ticks(base + sample(0, skySunRange_)));
    }
    for (const auto& sun : suns_) {
        if (sun.expiresAt <= tick_) {
            emit("sun_expired", [&] { return nlohmann::json{{"row", sun.row}, {"col", sun.col}, {"amount", sun.value}}; });
        }
    }
    std::erase_if(suns_, [this](const Sun& sun) { return sun.expiresAt <= tick_; });
    updatePlants();
    updateShots();
    updateZombies();
    if (phase_ == Phase::lost) {
        return;
    }
    updateMowers();
    for (const auto& plant : plants_) {
        if (plant.hp <= 0) {
            emit("plant_removed", [&] {
                return nlohmann::json{{"row", plant.row}, {"col", plant.col}, {"plant", cards_[plant.card].id},
                                      {"source", cards_[plant.card].kind == PlantKind::mine ? "detonated" : "damage"}};
            });
        }
    }
    std::erase_if(plants_, [](const Plant& p) { return p.hp <= 0; });
    for (const auto& zombie : zombies_) {
        if (zombie.hp > 0) {
            continue;
        }
        emit("zombie_defeated", [&] { return nlohmann::json{{"id", zombie.id}, {"wave", zombie.wave}}; });
        if (zombie.carriesPlantfood) {
            const auto col = std::clamp(static_cast<int>(zombie.x), 0, columns - 1);
            plantfoodDrops_.push_back({zombie.row, col});
            emit("plantfood_dropped", [&] {
                return nlohmann::json{{"id", zombie.id}, {"wave", zombie.wave}, {"row", zombie.row}, {"col", col}};
            });
        }
    }
    std::erase_if(zombies_, [](const Zombie& z) { return z.hp <= 0; });
    if (phase_ == Phase::playing) {
        updateWaves();
        if (wavesStarted_ == waves_.size() && zombies_.empty()) {
            finish(Phase::won);
        }
    }
}

void Battle::updatePlants() {
    for (auto& plant : plants_) {
        if (tick_ < plant.actionAt) {
            continue;
        }
        const auto& card = cards_[plant.card];
        const double x = plant.col + 0.5;
        if (card.kind == PlantKind::producer) {
            addSun(plant.row, plant.col, card.sunValue, "plant");
            plant.actionAt = tick_ + card.interval;
        } else if (card.kind == PlantKind::shooter) {
            const auto target = std::ranges::find_if(zombies_, [&](const Zombie& z) {
                return z.hp > 0 && z.row == plant.row && z.x >= x - 0.2;
            });
            if (target != zombies_.end()) {
                shots_.push_back({plant.row, x, card.damage});
                plant.actionAt = tick_ + card.interval;
            }
        } else if (card.kind == PlantKind::mine) {
            const auto contact = [&](const Zombie& z) {
                return z.hp > 0 && z.row == plant.row && std::abs(z.x - x) <= 0.55;
            };
            if (std::ranges::any_of(zombies_, contact)) {
                for (auto& z : zombies_) {
                    if (contact(z)) {
                        damageZombie(z, card.damage, "mine");
                    }
                }
                plant.hp = 0;
            }
        }
    }
}

void Battle::damageZombie(Zombie& zombie, double amount, const char* source) {
    zombie.hp -= amount;
    emit("zombie_damaged", [&] {
        return nlohmann::json{{"id", zombie.id}, {"wave", zombie.wave}, {"source", source},
                              {"damage", amount}, {"hp", std::max(0.0, zombie.hp)}};
    });
}

void Battle::updateShots() {
    for (auto& shot : shots_) {
        const double next = shot.x + shotSpeed * stepSeconds;
        Zombie* closest = nullptr;
        for (auto& z : zombies_) {
            if (z.hp > 0 && z.row == shot.row && z.x >= shot.x - 0.22 && z.x <= next + 0.22 &&
                (!closest || z.x < closest->x)) {
                closest = &z;
            }
        }
        if (closest) {
            damageZombie(*closest, shot.damage, "pea");
            shot.damage = 0;
        }
        shot.x = next;
    }
    std::erase_if(shots_, [](const Shot& shot) { return shot.damage <= 0 || shot.x > columns + 3; });
}

void Battle::updateZombies() {
    for (auto& z : zombies_) {
        if (z.hp <= 0) {
            continue;
        }
        const double next = z.x - z.speed * stepSeconds;
        const auto blocker = std::ranges::find_if(plants_, [&](const Plant& p) {
            const double center = p.col + 0.5;
            return p.hp > 0 && p.row == z.row && z.x >= center - 0.2 && next <= center + 0.44;
        });
        if (blocker != plants_.end()) {
            const auto damage = z.eat * stepSeconds;
            blocker->hp -= damage;
            emit("plant_damaged", [&] {
                return nlohmann::json{{"id", z.id}, {"row", blocker->row}, {"col", blocker->col},
                                      {"damage", damage}, {"hp", std::max(0.0, blocker->hp)}};
            });
            continue;
        }
        z.x = next;
        if (z.x > 0) {
            continue;
        }
        auto& mower = mowers_[z.row];
        if (mower.state == Mower::spent) {
            finish(Phase::lost);
            return;
        }
        if (mower.state == Mower::ready) {
            emit("mower_started", [&] { return nlohmann::json{{"row", z.row}}; });
        }
        mower.state = Mower::rolling;
    }
}

void Battle::updateMowers() {
    for (int row = 0; row < rows; ++row) {
        auto& mower = mowers_[row];
        if (mower.state != Mower::rolling) {
            continue;
        }
        mower.x += mowerSpeed * stepSeconds;
        for (auto& z : zombies_) {
            if (z.hp > 0 && z.row == row && z.x <= mower.x + 0.3) {
                damageZombie(z, z.hp, "mower");
            }
        }
        if (mower.x >= columns + 3) {
            mower.state = Mower::spent;
        }
    }
}

}
