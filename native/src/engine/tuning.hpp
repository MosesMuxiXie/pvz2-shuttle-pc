#pragma once
// Single source of tuning constants for the engine kernel. Every magic number that
// affects gameplay lives here, so calibration against the original recordings has
// exactly one site to touch. Values are in grid units (one column == 1.0) unless
// the name says otherwise.
namespace pvz::engine::tuning {

inline constexpr double kStepSeconds = 1.0 / 60.0;

// Projectiles
// 5.2 cols/s (312 px/s) is not a mode of anything in the pack: the straight-shot mode is 333 px/s
// (5.55 cols/s, 142 rows). It survives only as the fallback for a shot whose id the table does not
// know; every row that resolves gets the table's own speed.
inline constexpr double kShotSpeedColsPerSec = 5.2;
inline constexpr double kShotHitRadius = 0.25; // |shot.x - zombie.x|; == CollisionRect mode (358/596)
inline constexpr double kShotStartOffsetCols = 0.35;
inline constexpr double kSplashNeighbourFactor = 0.5;
inline constexpr double kShotSplashRadiusCols = 0.6; // fallback: tuning constant, no pack evidence
// Arc/drop shots cannot hit before they land. The sheet's InitialVelocity.z pairs with a z
// acceleration that does not integrate into a plausible flight (700 px/s with -10 px/s^2 = 140 s),
// so the landing distance falls back to a single flight time instead of a fake parabola.
inline constexpr double kLobFlightSeconds = 0.75; // fallback: tuning constant, no pack evidence

// Sky sun (matches the legacy kernel: first at tick 270, then every 24s)
inline constexpr double kFirstSkySunSeconds = 4.5;
inline constexpr double kSkySunIntervalSeconds = 24.0;
inline constexpr int kSkySunValue = 25;
inline constexpr int kSunLifetimeTicks = 600; // 10s on the lawn before it fades

// Zombies
inline constexpr double kEatStartCols = 0.35; // contact needed to start eating
inline constexpr double kEatRangeCols = 1.15; // max reach while eating
// S5.12: a vaulter may only launch the hop once it is already touching the plant, so the
// trigger window is the contact distance plus one tick of slack — not the whole eating reach.
// With the old `kEatRangeCols` bound the zombie left a whole column early and the hop lost its
// meaning as "it stepped over that plant"; `engine_test` asserts the hop's own `from` against
// this value so a widened window fails instead of silently hopping earlier.
inline constexpr double kVaultTriggerMaxCols = kEatStartCols + 0.05;
inline constexpr double kVaultLandingCols = 0.55; // landing distance left of the plant centre
inline constexpr double kZombieDeathFadeSeconds = 0.3;
inline constexpr double kGargantuarSmashExtraSeconds = 0.5;
// How far a zombie may overlap a shooter from the left and still be a forward
// target. Beyond this it has walked past the plant and must not be shot backwards.
inline constexpr double kShotBehindToleranceCols = 0.15;
// Victory needs every scheduled zombie gone; there is deliberately no extra
// hold-off constant (the old `kVictoryFlushSeconds` could never fire, because
// `allSpawned()` already implies the spawn cursor passed the last tick).

// Lawn mowers
inline constexpr double kMowerTriggerX = -0.25;
inline constexpr double kMowerSpeedColsPerSec = 8.0;

// Defeat
inline constexpr double kLoseX = -0.7;

// Wave pacing
inline constexpr double kFlagWaveSpreadSeconds = 1.0; // a flag wave arrives within this window
inline constexpr double kMinSpawnSeparationSeconds = 0.3;

// Plant food (S5.7). The sheet carries a duration per plant (`plantfood_from_pack.json`,
// 293 rows); the constants below only stand in when a row has none, and for the "+100%"
// the original applies on top of whatever the plant already does.
inline constexpr double kPlantFoodFallbackSeconds = 5.0; // fallback: tuning constant, no pack evidence
inline constexpr double kPlantFoodDamageScale = 2.0;     // fallback: tuning constant, +100% damage
inline constexpr double kPlantFoodRateScale = 2.0;       // fallback: tuning constant, +100% attack speed

// Boss (S5.8). `bosses_from_pack.json` states a column window (`FireMinColumn`/
// `FireMaxColumn`), the covered row count (`FireRowRange`) and a rocket speed/hit time, but
// no damage number: the original kills whatever the rocket lands on. One shot therefore
// clears a plant outright, and the constant below is the smallest value that does that for
// every shipped plant (the toughest non-boss plant is under 1800 hit points).
inline constexpr double kBossFireDamage = 1800.0; // fallback: tuning constant, no pack evidence

// S5.13 level mechanics.
// A grid item (gravestone, puddle) has no hit points in the sheet: it is a `GridItemType`, not a
// zombie, so nothing in `zombies_from_pack.json` describes it. The constant is low enough that one
// Cherry Bomb (1800 damage) clears the cell it lands on, which is what "墓碑可被炸" means.
inline constexpr double kGridItemHitPoints = 300.0; // fallback: tuning constant, no pack evidence
// How many cards the conveyor hand holds. The original belt shows six packets; `slots[]` in the
// sheet only weights the plants, it never says how many are visible.
inline constexpr int kConveyorHandSize = 6; // fallback: tuning constant, no pack evidence

// Rail carts (S3/A2). The pack says where a cart stands (`RailcartProperties` Column/Row) and how
// many a DangerRoom level wants (`BaseRailcartCount`), but it carries no speed, no hit points and
// no crush damage: `rails_report.json` has 204 levels with a rail object and none of them states a
// per-second number. These four are fallbacks, chosen so a cart crosses one column in two seconds
// and survives roughly half a minute of a single zombie chewing on it.
inline constexpr double kRailSpeedColumnsPerSecond = 0.5; // fallback: tuning constant, no pack evidence
inline constexpr double kRailCrushDamage = 1000.0;        // fallback: tuning constant, no pack evidence
inline constexpr double kRailCrushReachColumns = 0.55;    // fallback: one cart cell, no pack evidence
inline constexpr double kRailCartHitPoints = 3000.0;      // fallback: tuning constant, no pack evidence

// T88: frost wind. `FrostWindWaveActionProps.Winds[]` names a direction and a row (and only
// those two), so how far the wind carries a zombie is not in the sheet. Half a column: far enough
// that a wind row visibly moves the horde back, short enough that it cannot undo a whole wave.
// This is the one place a T88 number comes from tuning rather than from the sheet.
inline constexpr double kFrostWindPushColumns = 0.5; // fallback: tuning constant, no pack evidence

// Hard caps so a malformed level can never hang the kernel in CI
inline constexpr int kMaxZombies = 400;
inline constexpr int kMaxShots = 800;
inline constexpr int kMaxSuns = 200;
inline constexpr int kMaxPlants = 200;

} // namespace pvz::engine::tuning
