#pragma once
#include "catalog.hpp"
#include <cstdint>
#include <string>
#include <vector>
namespace pvz {
struct BattlePlant {
    std::uint64_t id;
    std::string type;
    int row, col;
    double hp;
    std::uint64_t born, nextAction;
};
struct BattleZombie {
    std::uint64_t id;
    std::string type;
    int row;
    double x, hp, armor;
};
struct BattleShot {
    std::uint64_t id;
    int row;
    double x, damage;
};
struct BattleSun {
    std::uint64_t id;
    double x, row;
    int value;
    std::uint64_t expires;
};
struct BattleMower {
    int row;
    double x = -0.5;
    int state = 0;
}; // ready, moving, spent
class Battle {
  public:
    static constexpr double stepSeconds = 1.0 / 60.0;
    /// Level rules this preview cannot honour (empty = fully supported). C54: enumerated so
    /// the CLI can refuse a level with a reason instead of an opaque constructor failure.
    static std::vector<std::string> unsupportedRules(const LevelDefinition& level);
    Battle(const Catalog& catalog, const LevelDefinition& level, std::uint32_t seed = 1);
    void advance(double seconds);
    void step();
    std::string plant(const std::string& type, int row, int col);
    bool shovel(int row, int col);
    bool collect(std::uint64_t id);
    void pause(bool paused) { paused_ = paused; }
    bool paused() const { return paused_; }
    const std::string& status() const { return status_; }
    std::uint64_t tick() const { return tick_; }
    std::int64_t sun() const { return sun_; }
    std::size_t wave() const { return nextWave_; }
    std::uint64_t cooldown(const std::string& type) const;
    const LevelDefinition& level() const { return level_; }
    const std::vector<BattlePlant>& plants() const { return plants_; }
    const std::vector<BattleZombie>& zombies() const { return zombies_; }
    const std::vector<BattleShot>& shots() const { return shots_; }
    const std::vector<BattleSun>& suns() const { return suns_; }
    const std::vector<BattleMower>& mowers() const { return mowers_; }
    const Json& events() const { return events_; }
    Json snapshot() const;

  private:
    const Catalog& catalog_;
    LevelDefinition level_;
    std::uint32_t rng_;
    std::uint64_t tick_ = 0, nextId_ = 1, nextSkySun_ = 270;
    std::size_t nextWave_ = 0;
    std::int64_t sun_ = 0;
    bool paused_ = false;
    double accumulator_ = 0;
    std::string status_ = "playing";
    std::vector<std::uint64_t> waveTicks_;
    std::map<std::string, std::uint64_t> cooldowns_;
    std::vector<BattlePlant> plants_;
    std::vector<BattleZombie> zombies_;
    std::vector<BattleShot> shots_;
    std::vector<BattleSun> suns_;
    std::vector<BattleMower> mowers_;
    Json events_ = Json::array();
    std::uint32_t random();
    void event(const std::string& type, Json details = Json::object());
    void addSun(double x, double row, int value);
    void damage(BattleZombie& zombie, double amount, bool ignoreArmor = false);
};
} // namespace pvz
