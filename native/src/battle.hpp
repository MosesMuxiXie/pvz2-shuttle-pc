#pragma once

#include "catalog.hpp"

#include <array>
#include <cstdint>
#include <functional>
#include <random>
#include <string_view>

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
    struct Zombie {
        int row;
        double x, hp, speed, eat;
        bool armored;
        std::string type;
        int id{};
        std::size_t wave{};
        bool carriesPlantfood{};
    };
    struct Shot { int row; double x; double damage; };
    struct Sun { int row; int col; int value; int expiresAt; };
    struct Plantfood { int row; int col; };
    struct Mower { enum State { ready, rolling, spent } state = ready; double x{}; };

    using EventSink = std::function<void(const nlohmann::json&)>;
    explicit Battle(const Catalog& catalog, const LevelDefinition& level, std::uint32_t seed = 1,
                    EventSink sink = {});
    bool toggleCard(int card);
    bool start();
    bool plant(int card, int row, int col);
    bool shovel(int row, int col);
    bool collectSun(int row, int col);
    bool collectPlantfood(int row, int col);
    void step();

    [[nodiscard]] Phase phase() const { return phase_; }
    [[nodiscard]] int sun() const { return sun_; }
    [[nodiscard]] int tick() const { return tick_; }
    [[nodiscard]] std::size_t wavesStarted() const { return wavesStarted_; }
    [[nodiscard]] std::size_t waveCount() const { return waves_.size(); }
    [[nodiscard]] bool flagWarning() const { return flagWarning_; }
    [[nodiscard]] int plantfood() const { return plantfood_; }
    [[nodiscard]] const auto& cards() const { return cards_; }
    [[nodiscard]] const auto& plants() const { return plants_; }
    [[nodiscard]] const auto& zombies() const { return zombies_; }
    [[nodiscard]] const auto& shots() const { return shots_; }
    [[nodiscard]] const auto& suns() const { return suns_; }
    [[nodiscard]] const auto& plantfoodDrops() const { return plantfoodDrops_; }
    [[nodiscard]] const auto& mowers() const { return mowers_; }

private:
    struct Wave { int delay; bool flag; std::vector<Zombie> zombies; };
    struct WaveTiming { double jitter{}, healthMin{}, healthMax{}; int minimumGap{}, warning{}; };

    template <typename Describe>
    void emit(std::string_view name, Describe describe) const {
        if (sink_) {
            auto event = describe();
            event["event"] = std::string(name);
            event["tick"] = tick_;
            sink_(event);
        }
    }

    double sample(double minimum, double maximum);
    void addSun(int row, int col, int value, const char* source);
    void updateWaves();
    void finish(Phase phase);
    void damageZombie(Zombie& zombie, double amount, const char* source);
    void updatePlants();
    void updateShots();
    void updateZombies();
    void updateMowers();

    std::mt19937 random_;
    EventSink sink_;
    WaveTiming waveTiming_;
    std::vector<Wave> waves_;
    std::vector<Card> cards_;
    std::vector<Plant> plants_;
    std::vector<Zombie> zombies_;
    std::vector<Shot> shots_;
    std::vector<Sun> suns_;
    std::vector<Plantfood> plantfoodDrops_;
    std::array<Mower, rows> mowers_{};
    Phase phase_ = Phase::choosing;
    int seedBank_;
    int sun_;
    int tick_{};
    int nextSkySun_, scheduledSkySuns_{};
    double skySunBase_, skySunRange_, skySunIncrease_, skySunCap_;
    int nextWaveAt_{}, lastWaveAt_{}, nextZombieId_{}, plantfood_{};
    double waveHealthThreshold_{};
    bool flagWarning_{};
    bool adaptiveTiming_{};
    std::size_t wavesStarted_{};
};

}
