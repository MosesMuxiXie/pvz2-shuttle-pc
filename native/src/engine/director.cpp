#include "director.hpp"
#include "tuning.hpp"
#include <algorithm>

namespace pvz::engine {
namespace {
constexpr std::uint64_t ticksOf(double seconds) {
    return static_cast<std::uint64_t>(seconds / tuning::kStepSeconds + 0.5);
}
int pickRow(const ZombieSpawn& spawn, int rows, std::mt19937& rng) {
    if (spawn.row) {
        return *spawn.row;
    }
    if (!spawn.rows.empty()) {
        std::uniform_int_distribution<std::size_t> pick(0, spawn.rows.size() - 1);
        return spawn.rows[pick(rng)];
    }
    std::uniform_int_distribution<int> pick(0, rows > 0 ? rows - 1 : 0);
    return pick(rng);
}
bool isHeavy(const std::string& type) {
    // The heavyweight families enter a beat later so they never stack on a normal
    // zombie in the same frame. S3 replaces this with the real ZombieClass check.
    return type.find("gargantuar") != std::string::npos || type.find("zomboss") != std::string::npos ||
           type.find("mech") != std::string::npos;
}
} // namespace

Director::Director(const LevelDefinition& level, int rows, std::mt19937& rng) {
    waveCount_ = level.waves.size();
    remaining_.assign(waveCount_, 0);
    schedule_.reserve(level.waves.size() * 8);
    double clock = 0;
    for (std::size_t w = 0; w < level.waves.size(); ++w) {
        const auto& wave = level.waves[w];
        clock += wave.delay > 0 ? wave.delay : 0.0;
        const auto base = ticksOf(clock);
        const double spread = wave.flag ? tuning::kFlagWaveSpreadSeconds : 0.0;
        const std::size_t count = wave.zombies.size();
        for (std::size_t i = 0; i < count; ++i) {
            const auto& spawn = wave.zombies[i];
            double offset = 0;
            if (count > 1) {
                offset = spread > 0 ? spread * static_cast<double>(i) / static_cast<double>(count - 1)
                                    : tuning::kMinSpawnSeparationSeconds * static_cast<double>(i);
            }
            if (isHeavy(spawn.type)) {
                offset += tuning::kGargantuarSmashExtraSeconds;
            }
            Spawn entry;
            entry.tick = base + ticksOf(offset);
            entry.type = spawn.type;
            entry.row = pickRow(spawn, rows, rng);
            entry.wave = w;
            entry.flag = wave.flag;
            entry.final = (w + 1 == waveCount_);
            schedule_.push_back(entry);
            ++remaining_[w];
        }
    }
    std::stable_sort(schedule_.begin(), schedule_.end(), [](const Spawn& a, const Spawn& b) {
        if (a.tick != b.tick) return a.tick < b.tick;
        if (a.wave != b.wave) return a.wave < b.wave;
        return a.type < b.type;
    });
    if (schedule_.empty() && waveCount_ > 0) {
        // A level whose waves carry no zombies still counts as fully spawned.
        spawnedWaves_ = 0;
    }
}

std::vector<Spawn> Director::takeDue(std::uint64_t tick) {
    std::vector<Spawn> due;
    while (cursor_ < schedule_.size() && schedule_[cursor_].tick <= tick) {
        const auto& entry = schedule_[cursor_];
        due.push_back(entry);
        if (entry.wave < remaining_.size() && remaining_[entry.wave] > 0) {
            --remaining_[entry.wave];
            if (remaining_[entry.wave] == 0 && entry.wave + 1 > spawnedWaves_) {
                spawnedWaves_ = entry.wave + 1;
            }
        }
        ++cursor_;
    }
    if (schedule_.empty()) {
        spawnedWaves_ = waveCount_;
    }
    return due;
}

} // namespace pvz::engine
