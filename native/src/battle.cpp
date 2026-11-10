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

Battle::Battle(const Catalog& catalog, const LevelDefinition& level, std::uint32_t seed)
    : random_(seed), seedBank_(level.seedBank), sun_(level.sun),
      nextSkySun_(ticks(level.extra.value("first_sun", 4.5))),
      skySunInterval_(std::max(1, ticks(level.extra.value("sky_sun_interval", 8.0)))) {
    for (const auto& id : level.deck) {
        cards_.push_back(makeCard(id, catalog.plants.at(id)));
    }

    int due = 0;
    for (const auto& wave : level.waves) {
        due += ticks(wave.delay);
        auto& spawns = waves_.emplace_back(Wave{due, {}}).zombies;
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
                                  definition.at("eat_dps").get<double>(), armor > 0});
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
    }
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
    return true;
}

bool Battle::start() {
    if (phase_ != Phase::choosing || !std::ranges::any_of(cards_, &Card::selected)) {
        return false;
    }
    phase_ = Phase::playing;
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
    return true;
}

bool Battle::shovel(int row, int col) {
    return phase_ == Phase::playing &&
        std::erase_if(plants_, [=](const Plant& p) { return p.row == row && p.col == col; }) > 0;
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
    suns_.erase(match);
    return true;
}

void Battle::addSun(int row, int col, int value) {
    suns_.push_back({row, col, value, tick_ + 10 * ticksPerSecond});
}

void Battle::step() {
    if (phase_ != Phase::playing) {
        return;
    }
    ++tick_;
    if (tick_ >= nextSkySun_) {
        const int row = static_cast<int>(random_() % rows);
        const int col = static_cast<int>(random_() % columns);
        addSun(row, col, 25);
        nextSkySun_ += skySunInterval_;
    }
    std::erase_if(suns_, [this](const Sun& sun) { return sun.expiresAt <= tick_; });
    while (wavesStarted_ < waves_.size() && waves_[wavesStarted_].tick <= tick_) {
        const auto& spawns = waves_[wavesStarted_++].zombies;
        zombies_.insert(zombies_.end(), spawns.begin(), spawns.end());
    }
    updatePlants();
    updateShots();
    updateZombies();
    updateMowers();
    std::erase_if(plants_, [](const Plant& p) { return p.hp <= 0; });
    std::erase_if(zombies_, [](const Zombie& z) { return z.hp <= 0; });
    if (phase_ == Phase::playing && wavesStarted_ == waves_.size() && zombies_.empty()) {
        phase_ = Phase::won;
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
            addSun(plant.row, plant.col, card.sunValue);
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
                        z.hp -= card.damage;
                    }
                }
                plant.hp = 0;
            }
        }
    }
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
            closest->hp -= shot.damage;
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
            blocker->hp -= z.eat * stepSeconds;
            continue;
        }
        z.x = next;
        if (z.x > 0) {
            continue;
        }
        auto& mower = mowers_[z.row];
        if (mower.state == Mower::spent) {
            phase_ = Phase::lost;
            return;
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
            if (z.row == row && z.x <= mower.x + 0.3) {
                z.hp = 0;
            }
        }
        if (mower.x >= columns + 3) {
            mower.state = Mower::spent;
        }
    }
}

}
