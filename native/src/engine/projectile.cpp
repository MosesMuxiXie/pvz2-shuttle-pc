#include "projectile.hpp"
#include "tuning.hpp"
#include "world.hpp"
#include <cmath>

namespace pvz::engine {
namespace {

double splashDamageOf(const ShotEntity& shot) {
    // The sheet declares an absolute splash damage for most lobbed/fat shots; when it does not, the
    // legacy rule (a fraction of the direct hit) stays in charge.
    if (shot.splashDamage > 0.0) return shot.splashDamage;
    return shot.damage * tuning::kSplashNeighbourFactor;
}

} // namespace

void stepShots(World& world) {
    const double dt = tuning::kStepSeconds;
    const double maxX = static_cast<double>(world.cols()) + 1.5;
    for (auto& shot : world.mutableShots()) {
        if (!shot.alive) continue;
        if (shot.trajectory != Trajectory::stationary) shot.x += shot.speed * dt;
        if (shot.x > maxX) {
            shot.alive = false;
            continue;
        }
        // A lobbed shot is in the air until it comes down: it passes over every zombie between the
        // plant and its landing column and only the landing zone can be hit.
        if (shot.lobbed) {
            if (shot.x + shot.hitRadius < shot.landX) continue;
            if (shot.x - shot.hitRadius > shot.landX) {
                shot.alive = false; // it landed on empty ground
                continue;
            }
        }
        for (auto& zombie : world.mutableZombies()) {
            if (!shot.alive) break;
            if (!zombie.alive || zombie.row != shot.row) continue;
            if (std::abs(zombie.x - shot.x) > shot.hitRadius) continue;
            world.damageZombie(zombie.id, shot.damage);
            // Presentation-only hook (T38 audio): name the hit so a sound can follow it.
            world.emitEffect("shot_hit",
                                 Json{{"shot", shot.id}, {"zombie", zombie.id},
                                      {"row", shot.row}, {"x", shot.x},
                                      {"damage", shot.damage}});
            if (shot.splash > 0) {
                const int rows = world.rows();
                const int splashRow = shot.row;
                const double centre = shot.x;
                const double reach = shot.splashRadius;
                const double damage = splashDamageOf(shot);
                for (int row = 0; row < rows; ++row) {
                    if (std::abs(row - splashRow) != 1) continue;
                    for (auto& other : world.mutableZombies()) {
                        if (!other.alive || other.row != row) continue;
                        if (std::abs(other.x - centre) > reach) continue;
                        world.damageZombie(other.id, damage);
                    }
                }
            }
            if (shot.slow > 0) {
                // `shot.slow` is in *seconds* (chill/freeze durations come from the
                // property sheet); `slowUntilTick` is a tick. Adding the seconds as if
                // they were ticks made a 3s chill last 50ms.
                zombie.slowUntilTick = static_cast<double>(world.tick()) + shot.slow / tuning::kStepSeconds;
            }
            if (shot.pierce > 0) {
                --shot.pierce;
            } else {
                shot.alive = false;
            }
        }
    }
}

} // namespace pvz::engine
