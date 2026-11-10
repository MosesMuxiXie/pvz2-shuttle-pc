#pragma once

#include "catalog.hpp"

#include <array>
#include <cstdint>
#include <random>

namespace shuttle {

class Battle {
public:
    static constexpr int rows = 5;
    static constexpr int columns = 9;
    static constexpr int ticksPerSecond = 60;

    enum class Phase { choosing, playing, won, lost };
    enum class PlantKind { producer, shooter, blocker, mine };

    struct Card {
        std::string id;
        std::string name;
        PlantKind kind;
        int cost;
        double hp;
        double damage;
        int recharge;
        int interval;
        int sunValue;
        int availableAt{};
        bool selected{};
    };
    struct Plant { int card; int row; int col; double hp; int actionAt; };
    struct Zombie { int row; double x; double hp; double speed; double eat; bool armored; };
    struct Shot { int row; double x; double damage; };
    struct Sun { int row; int col; int value; int expiresAt; };
    struct Mower { enum State { ready, rolling, spent } state = ready; double x{}; };

    explicit Battle(const Catalog& catalog, const LevelDefinition& level, std::uint32_t seed = 1);
    bool toggleCard(int card);
    bool start();
    bool plant(int card, int row, int col);
    bool shovel(int row, int col);
    bool collectSun(int row, int col);
    void step();

    [[nodiscard]] Phase phase() const { return phase_; }
    [[nodiscard]] int sun() const { return sun_; }
    [[nodiscard]] int tick() const { return tick_; }
    [[nodiscard]] std::size_t wavesStarted() const { return wavesStarted_; }
    [[nodiscard]] std::size_t waveCount() const { return waves_.size(); }
    [[nodiscard]] const auto& cards() const { return cards_; }
    [[nodiscard]] const auto& plants() const { return plants_; }
    [[nodiscard]] const auto& zombies() const { return zombies_; }
    [[nodiscard]] const auto& shots() const { return shots_; }
    [[nodiscard]] const auto& suns() const { return suns_; }
    [[nodiscard]] const auto& mowers() const { return mowers_; }

private:
    struct Wave { int tick; std::vector<Zombie> zombies; };
    void addSun(int row, int col, int value);
    void updatePlants();
    void updateShots();
    void updateZombies();
    void updateMowers();

    std::mt19937 random_;
    std::vector<Wave> waves_;
    std::vector<Card> cards_;
    std::vector<Plant> plants_;
    std::vector<Zombie> zombies_;
    std::vector<Shot> shots_;
    std::vector<Sun> suns_;
    std::array<Mower, rows> mowers_{};
    Phase phase_ = Phase::choosing;
    int seedBank_;
    int sun_;
    int tick_{};
    int nextSkySun_;
    int skySunInterval_;
    std::size_t wavesStarted_{};
};

}
