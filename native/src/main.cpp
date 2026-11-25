#include "art_index.hpp"
#include "audio/audio_audit.hpp"
#include "audio/audio_backend.hpp"
#include "audio/audio_catalog.hpp"
#include "audio/audio_runtime.hpp"
#include "audio/event_map.hpp"
#include "catalog.hpp"
#include "engine/plantfood.hpp"
#include "engine/replay.hpp"
#include "flow.hpp"
#include "progress.hpp"
#include "rewards.hpp"
#include "worldmap.hpp"
#include "shop.hpp"
#include "save.hpp"
#include "simulation.hpp"
#include <chrono>
#include <cmath>
#include <optional>
#ifdef PVZ_ENABLE_DESKTOP
#include "battle_view.hpp"
#include "launcher.hpp"
#include "level_select_view.hpp"
#include "menu_view.hpp"
#include "worldmap_view.hpp"
#endif
#include <iostream>
#include <vector>
namespace fs = std::filesystem;
namespace {

// S7: where the generated tables live. The source tree keeps them in `native/generated`, the
// install tree in `generated/` next to `content/`. A packaged build must not depend on the
// caller's working directory, so probe next to the content directory first and only then fall
// back to the shared resolver (`PVZ_GENERATED_DIR`, the exe directory, a walk up from the cwd).
std::filesystem::path generatedTable(const std::filesystem::path& content, const std::string& name) {
    const std::filesystem::path root = content.parent_path();
    for (const auto& directory : {root / "generated", root / "native" / "generated"}) {
        std::error_code error;
        if (std::filesystem::is_regular_file(directory / name, error)) return directory / name;
    }
    const std::filesystem::path shared = pvz::engine::generatedDir();
    if (!shared.empty()) return shared / name;
    // Nothing found: point at the source-tree location so the error message stays recognisable.
    return root / "native" / "generated" / name;
}

} // namespace

namespace {
// One validator for every `--seconds`. A negative or non-finite budget would step the loop
// backwards, and a day of simulated time is already far past any real level, so anything above it
// is a typo rather than a long test.
double parseSecondsValue(const std::string& raw) {
    const double value = std::stod(raw);
    if (!std::isfinite(value) || value < 0.0 || value > 86400.0) {
        throw std::runtime_error("--seconds needs a finite value in [0, 86400], got " + raw);
    }
    return value;
}
}  // namespace
int run(const std::vector<fs::path>& args) {
    try {
#ifndef PVZ_VERSION
#define PVZ_VERSION "0.0.0-dev"
#endif
#ifndef PVZ_DATA_VERSION
#define PVZ_DATA_VERSION "unknown"
#endif
        if (args.size() == 2 && args[1] == "--version") {
            std::cout << "PvZ2SHUTTLE " << PVZ_VERSION << "\ndata " << PVZ_DATA_VERSION << '\n';
            return 0;
        }
        if (args.size() == 2 && args[1] == "--help") {
            std::cout << "PvZ2SHUTTLE native foundation " << PVZ_VERSION << " (data " << PVZ_DATA_VERSION << ")\nUsage:\n  --audit-content <content directory> "
                         "[rules.pack]\n  --worldmap <content directory> [--progress <file>]\n  --shop <content directory> [--unlock <json>] [--progress <file>] [--coins <n>] [--buy <item id>]\n  --worldmap-screen <content directory> [--progress <file>] [--assets <dir>] [--snapshot <out.png>] [--frames <n>]\n  "
                         "--launcher <asset directory>\n  --launcher-smoke <asset directory>\n  "
                         "--launcher-snapshot <asset directory> <output.bmp>\n  --play <content directory> "
                         "<asset directory>\n  --battle-snapshot <content directory> <asset directory> "
                         "<output.bmp>\n  --simulate <content directory> [level id]\n  --run-level <content directory> "
                         "<level id> [--pack <pack>] [--boards <json>] [--script <file>] [--seconds <n>] "
                         "[--rows <n>] [--cols <n>] [--boss <on|off>] [--progress <file>]\n  --play-script <content directory> <level id> [--pack "
                         "<pack>] [--boards <json>] [--script <file>] [--seconds <n>] [--snapshot <out.png|out.bmp>] "
                         "[--assets <dir>]\n  --art-audit <content directory> [--pack <pack>] [--assets "
                         "<dir>]\n  --audio-audit <asset directory>\n  --audio-off   mute every screen (screenshots/tests)\n  --volume <0..100>  master volume (0 is silent, default 100)\n  --music-volume <0..100>  trim the music bus (default: inherit the master)\n  --sfx-volume <0..100>  trim the effect bus (default: inherit the master)\n  --mute-bgm    silence the music bus\n  --mute-sfx    silence the effect bus\n  --import-python-save "
                         "<source.json> <new-native.json>\n  --audit-save <native.json>\n  "
                         "--menu <content directory> [--progress <file>] [--assets <dir>] "
                         "[--snapshot <out.png>] [--frames <n>] [--flow-after]\n  --level-select <content "
                         "directory> --world <id> [--progress <file>] [--assets <dir>] "
                         "[--snapshot <out.png>] [--frames <n>]\n  --flow <content directory> [--pack "
                         "<pack>] [--boards <json>] [--progress <file>] [--script <file>] [--seconds "
                         "<n>] [--assets <dir>]\n";
            return 0;
        }
        if (args.size() == 4 && args[1] == "--import-python-save") {
            const auto now = std::chrono::duration_cast<std::chrono::seconds>(
                                 std::chrono::system_clock::now().time_since_epoch())
                                 .count();
            pvz::importPythonSave(args[2], args[3], now);
            std::cout << "save_import=ok\n";
            return 0;
        }
        if (args.size() == 3 && args[1] == "--audit-save") {
            const auto save = pvz::readNativeSave(args[2]);
            std::cout << "save_schema=" << save.at("schema_version")
                      << "\ncompleted=" << save.at("progress").at("completed").size() << '\n';
            return 0;
        }
        if (args.size() >= 2 && (args[1] == "--play" || args[1] == "--battle-snapshot")) {
            const bool snapshot = args[1] == "--battle-snapshot";
            if (args.size() != (snapshot ? 5u : 4u))
                throw std::runtime_error("invalid battle preview arguments; use --help");
#ifdef PVZ_ENABLE_DESKTOP
            const auto c = pvz::loadCatalog(args[2]);
            pvz::runBattlePreview(c, args[3], snapshot, snapshot ? args[4] : fs::path{});
            std::cout << "battle_preview=ok\n";
            return 0;
#else
            throw std::runtime_error("desktop support is disabled; rebuild with -DPVZ_ENABLE_DESKTOP=ON");
#endif
        }
        if (args.size() >= 3 && args[1] == "--audio-audit") {
            // T38: SDL-free in the audit build. The backend is still asked whether a device is
            // available so the JSON answers "would this build play anything on this machine?",
            // and the stub reports false instead of pretending.
            const auto catalog = pvz::AudioCatalog::load(args[2]);
            const pvz::EventMap events;
            auto packs = pvz::crossCheckPacks(
                pvz::locateAudioPacks(pvz::defaultPackDirectory(catalog.assetRoot)), events);
            auto backend = pvz::AudioBackend::create(catalog, events);
            const auto audit = pvz::auditAudio(catalog, backend->available(), std::move(packs));
            // stdout stays a single JSON line; the per-file table, the pack hit rates and the
            // reason a device is missing are diagnostics, so they go to stderr.
            std::cerr << audit.warning();
            std::cerr << "backend: " << pvz::audioBackendBuildNote() << '\n';
            if (!audit.deviceAvailable) std::cerr << "device: " << backend->note() << '\n';
            std::cerr << audit.text();
            std::cout << audit.json().dump() << '\n';
            return audit.exitCode();
        }
        if (args.size() >= 3 && args[1] == "--art-audit") {
            // SDL-free on purpose: the audit has to run in the AuditOnly build as well, which is
            // why the resolver lives in `pvz_catalog` and not in the desktop asset cache.
            pvz::CatalogOptions options;
            fs::path assetRoot;
            for (std::size_t i = 3; i < args.size(); ++i) {
                const auto& flag = pvz::pathUtf8(args[i]);
                if (flag == "--pack" && i + 1 < args.size()) {
                    options.contentPack = args[++i];
                } else if (flag == "--assets" && i + 1 < args.size()) {
                    assetRoot = args[++i];
                } else {
                    throw std::runtime_error("unknown --art-audit option: " + flag);
                }
            }
            const auto catalog = pvz::loadCatalog(args[2], options);
            if (assetRoot.empty())
                assetRoot = pvz::locateAssetRoot(args[2]);
            const auto audit = pvz::auditArt(catalog, assetRoot);
            // The JSON stays the single machine-readable line; the index problem is a diagnostic
            // because `missing` on its own would hide why every actor is unresolved.
            if (!audit.indexError.empty())
                std::cerr << "warning: " << audit.indexError << '\n';
            std::cout << audit.json().dump() << '\n';
            return audit.exitCode();
        }
        if (args.size() >= 4 && args[1] == "--play-script") {
            // PlayScriptOptions lives in battle_view.hpp, so the whole flag has to
            // sit inside the desktop guard: parsing it in an audit build referenced
            // a type that was never compiled in and broke -DPVZ_ENABLE_DESKTOP=OFF.
#ifdef PVZ_ENABLE_DESKTOP
            const std::string levelId = pvz::pathUtf8(args[3]);
            pvz::CatalogOptions options;
            pvz::PlayScriptOptions play;
            std::optional<fs::path> scriptPath;
            for (std::size_t i = 4; i < args.size(); ++i) {
                const auto& flag = pvz::pathUtf8(args[i]);
                if (flag == "--pack" && i + 1 < args.size()) {
                    options.contentPack = args[++i];
                } else if (flag == "--boards" && i + 1 < args.size()) {
                    options.boardSizes = args[++i];
                } else if (flag == "--script" && i + 1 < args.size()) {
                    scriptPath = args[++i];
                } else if (flag == "--seconds" && i + 1 < args.size()) {
                    play.seconds = std::stod(pvz::pathUtf8(args[++i]));
                } else if (flag == "--snapshot" && i + 1 < args.size()) {
                    play.snapshot = args[++i];
                } else if (flag == "--assets" && i + 1 < args.size()) {
                    play.assetRoot = args[++i];
                } else {
                    throw std::runtime_error("unknown --play-script option: " + flag);
                }
            }
            const auto c = pvz::loadCatalog(args[2], options);
            pvz::engine::Script script;
            if (scriptPath) script = pvz::engine::loadScript(*scriptPath);
            std::cout << pvz::runPlayScript(c, levelId, script, play).dump() << '\n';
            return 0;
#else
            throw std::runtime_error("desktop support is disabled; rebuild with -DPVZ_ENABLE_DESKTOP=ON");
#endif
        }
        if (args.size() >= 4 && args[1] == "--run-level") {
            pvz::CatalogOptions options;
            std::optional<fs::path> scriptPath;
            std::optional<fs::path> progressPath;
            std::optional<int> rows;
            std::optional<int> cols;
            double seconds = 600;
            pvz::engine::WorldOptions worldOptions;
            const std::string levelId = pvz::pathUtf8(args[3]);
            for (std::size_t i = 4; i < args.size(); ++i) {
                const auto& flag = pvz::pathUtf8(args[i]);
                if (flag == "--pack" && i + 1 < args.size()) {
                    options.contentPack = args[++i];
                } else if (flag == "--boards" && i + 1 < args.size()) {
                    options.boardSizes = args[++i];
                } else if (flag == "--script" && i + 1 < args.size()) {
                    scriptPath = args[++i];
                } else if (flag == "--seconds" && i + 1 < args.size()) {
                    seconds = parseSecondsValue(pvz::pathUtf8(args[++i]));
                } else if (flag == "--rows" && i + 1 < args.size()) {
                    rows = std::stoi(pvz::pathUtf8(args[++i]));
                } else if (flag == "--cols" && i + 1 < args.size()) {
                    cols = std::stoi(pvz::pathUtf8(args[++i]));
                } else if (flag == "--boss" && i + 1 < args.size()) {
                    // S5.8: `off` is how a baseline run pins the pre-boss behaviour, which is
                    // what `engine_smoke`'s control hashes compare against.
                    const auto value = pvz::pathUtf8(args[++i]);
                    if (value == "off") {
                        worldOptions.boss = false;
                    } else if (value == "on") {
                        worldOptions.boss = true;
                    } else {
                        throw std::runtime_error("--boss takes 'on' or 'off', got: " + value);
                    }
                } else if (flag == "--progress" && i + 1 < args.size()) {
                    // S6.0: fold the finished battle into a save file. Optional on purpose:
                    // without it this command prints exactly what it printed before S6.
                    progressPath = args[++i];
                } else {
                    throw std::runtime_error("unknown --run-level option: " + flag);
                }
            }
            if (!options.boardSizes) {
                // C47: without this, `--run-level` opened every level as 5x9 and beach/modern
                // ran two rows short. The generated table is the client's own reading of the
                // original stage data, so it applies by default; `--boards` still overrides.
                const fs::path guess =
                    generatedTable(args[2], "board_sizes.json");
                if (fs::is_regular_file(guess)) options.boardSizes = guess;
            }
            const auto c = pvz::loadCatalog(args[2], options);
            const auto it = c.levels.find(levelId);
            if (it == c.levels.end()) throw std::runtime_error("unknown level: " + levelId);
            pvz::LevelDefinition level = it->second;
            if (rows) level.rows = *rows;
            if (cols) level.cols = *cols;
            pvz::engine::Script script;
            if (scriptPath) script = pvz::engine::loadScript(*scriptPath);
            pvz::engine::World world(c, level, script.seed, worldOptions);
            pvz::engine::runScript(world, script, seconds);
            // The boss keys belong to --run-level only, so they are added here instead of in
            // `summarize` (replay.cpp is the captain's file this round). Same JSON shape.
            pvz::Json summary = pvz::engine::summarize(world);
            summary["boss"] = world.boss() != nullptr ? world.boss()->id : std::string();
            summary["bossStages"] = world.bossStageCount();
            summary["bossSpawned"] = world.bossSpawned();
            summary["bossActionUnwired"] = world.bossActionUnwired();
            summary["bossUnavailable"] = world.bossUnavailable();
            // S5.13: what the level's own mechanics did, and - more importantly - which of them
            // the kernel did not run. A level that quietly lost its tide looks exactly like a level
            // that never had one, so the gap is printed rather than left to a review.
            summary["conveyor"] = world.conveyorLevel();
            summary["conveyorCards"] = world.conveyorCards();
            summary["initialPlants"] = static_cast<int>(world.initialPlantsLaid());
            summary["gridItems"] = static_cast<int>(world.gridItemsSpawned());
            summary["protectedPlants"] = world.protectedPlantCount();
            summary["protectFailures"] = world.protectFailures();
            // T59: printed only for levels that carry a protect mission, so every other level's
            // `--run-level` output keeps exactly the keys it had before this patch (the smoke
            // baseline and the byte-comparison tests rely on that, not on eyeballing).
            const pvz::engine::LevelMechanics* mechanics = world.mechanics();
            if (mechanics != nullptr && !mechanics->protect.empty()) {
                summary["protectPlaced"] = world.protectedPlantCount();
                summary["protectCapacityShortfall"] = world.protectCapacityShortfall() > 0;
            }
            // T66: 460.9's `SuppressFlagZombie`, printed only where the level actually carries the
            // switch - the other 1538 levels keep exactly the keys they had before this patch.
            if (world.suppressFlagZombie()) summary["flagSuppressed"] = world.flagSuppressed();
            // T66: arrivals per wired `spawners.<kind>` row. Printed only on levels that carry
            // such rows, so a level without them keeps its exact previous output keys.
            if (world.spawnerLevel()) {
                pvz::Json wired = pvz::Json::array();
                for (const auto& [kind, spawned] : world.spawnerSpawned()) {
                    wired.push_back(pvz::Json{{"kind", kind}, {"spawned", spawned}});
                }
                summary["mechanicWired"] = std::move(wired);
            }
            pvz::Json unknown = pvz::Json::array();
            for (const auto& [kind, count] : world.mechanicUnknown()) {
                unknown.push_back(pvz::Json{{"kind", kind}, {"count", count},
                                            {"tier", pvz::engine::mechanicTierName(
                                                         pvz::engine::mechanicTierFor(kind))}});
            }
            summary["mechanicUnknown"] = std::move(unknown);
            summary["mechanicUnknownKinds"] = static_cast<int>(world.mechanicUnknownKinds());
            summary["mechanicUnknownInstances"] = world.mechanicUnknownInstances();
            // T55: rewards are only settled when a save is going to take them. Without
            // `--progress` this command must print exactly what it printed before T55 — the smoke
            // baseline pins that, not eyeballing — and settlement advances the world's RNG, so it
            // also runs after `summarize` has already hashed the finished battle.
            pvz::Progress progress;
            std::optional<pvz::StarTable> stars;
            pvz::RewardGain gain;
            if (progressPath) {
                stars = pvz::loadStarTable(args[2] / "stars.json");
                progress = pvz::loadProgress(*progressPath);
                // The key gate is read from the save the player brought in, so clearing egypt_3
                // unlocks the key rows from the next battle rather than during this one.
                const bool keyGate = pvz::keysUnlocked(progress);
                pvz::recordBattle(progress, levelId, pvz::outcomeOf(world), *stars);
                pvz::SettlementOptions rewardOptions;
                rewardOptions.keysUnlocked = keyGate;
                const std::string package =
                    level.extra.is_object() && level.extra.contains("package") &&
                            level.extra["package"].is_string()
                        ? level.extra["package"].get<std::string>()
                        : std::string();
                gain = pvz::settleRewards(pvz::RewardTable::shared(), world, level.world, package,
                                          rewardOptions);
                // T77: the save fold reports what it actually changed, so the receipt below can
                // count real deltas (a seed already owned or a trophy already held is not a gain).
                const pvz::RewardDelta rewardGained = pvz::applyRewards(progress, gain);
                summary["coinsGained"] = gain.coins;
                summary["keysGained"] = gain.keys;
                summary["seedsGained"] = static_cast<int>(gain.seeds.size());
                summary["presentTableMissing"] = gain.presentTableMissing;
                pvz::Json unmodelledRewards = pvz::Json::array();
                for (const pvz::RewardUnknown& rewardKind : gain.unmodelled) {
                    unmodelledRewards.push_back(
                        pvz::Json{{"kind", rewardKind.kind}, {"count", rewardKind.count}});
                }
                summary["rewardUnmodelled"] = std::move(unmodelledRewards);
                pvz::addRewardReceipt(summary, rewardGained, pvz::RewardTable::shared());
            }
            std::cout << summary.dump() << '\n';
            if (progressPath) {
                // S6.0: one save write per finished battle, won or lost — a loss is an attempt
                // too, so the world map can say "played three times, two stars". Printed after
                // the summary line, so a run without --progress stays byte-identical to the
                // pre-S6 CLI (pinned by the smoke baseline, not by eyeballing).
                const auto now = std::chrono::duration_cast<std::chrono::seconds>(
                                     std::chrono::system_clock::now().time_since_epoch())
                                     .count();
                pvz::saveProgress(*progressPath, progress, now);
                std::cout << pvz::progressReport(progress, *stars).dump() << '\n';
            }
            return 0;
        }
        if (args.size() >= 3 && args[1] == "--flow") {
            // T46: one turn of the S4 loop without a window. The save decides the world and the
            // level, the engine plays it, the save takes the result — the same three steps the
            // menu, the map and the battle screen perform by hand. Two runs of this command are
            // the "menu → map → level → battle → result → map" round trip a reviewer can check
            // without a GPU, and `flow_test` drives the same functions in-process.
            pvz::CatalogOptions options;
            std::optional<fs::path> scriptPath;
            std::optional<fs::path> progressPath;
            double seconds = 600;
            for (std::size_t i = 3; i < args.size(); ++i) {
                const auto& flag = pvz::pathUtf8(args[i]);
                if (flag == "--pack" && i + 1 < args.size()) {
                    options.contentPack = args[++i];
                } else if (flag == "--boards" && i + 1 < args.size()) {
                    options.boardSizes = args[++i];
                } else if (flag == "--script" && i + 1 < args.size()) {
                    scriptPath = args[++i];
                } else if (flag == "--seconds" && i + 1 < args.size()) {
                    seconds = parseSecondsValue(pvz::pathUtf8(args[++i]));
                } else if (flag == "--progress" && i + 1 < args.size()) {
                    progressPath = args[++i];
                } else if (flag == "--assets" && i + 1 < args.size()) {
                    // Accepted and ignored: nothing here draws, but the flag list matches the
                    // screens this command stands in for, so a scripted pipeline can reuse it.
                    ++i;
                } else {
                    throw std::runtime_error("unknown --flow option: " + flag);
                }
            }
            if (!options.boardSizes) {
                const fs::path guess =
                    generatedTable(args[2], "board_sizes.json");
                if (fs::is_regular_file(guess)) options.boardSizes = guess;
            }
            const auto c = pvz::loadCatalog(args[2], options);
            const auto stars = pvz::loadStarTable(args[2] / "stars.json");
            pvz::engine::Script script;
            if (scriptPath) script = pvz::engine::loadScript(*scriptPath);
            pvz::Progress progress;
            std::string lastLevel;
            if (progressPath) {
                progress = pvz::loadProgress(*progressPath);
                lastLevel = progress.lastLevel;
            }
            const pvz::FlowResult result =
                pvz::runFlowCycle(c, progress, stars, lastLevel, script, seconds);
            if (progressPath) {
                // Written only after a full cycle: a crash mid-battle must leave the save saying
                // what it said before, or the next run would skip a level that was never played.
                const auto now = std::chrono::duration_cast<std::chrono::seconds>(
                                     std::chrono::system_clock::now().time_since_epoch())
                                     .count();
                pvz::saveProgress(*progressPath, progress, now);
            }
            std::cout << result.json().dump() << '\n';
            return 0;
        }
        if ((args.size() == 3 || args.size() == 4) && args[1] == "--simulate") {
            const auto c = pvz::loadCatalog(args[2]);
            // `args` holds paths (`std::vector<fs::path>`), so the level id needs an explicit
            // string conversion: the ternary would otherwise resolve to `fs::path`.
            const std::string levelId = args.size() == 4 ? args[3].string() : std::string("frontyard_1");
            const auto it = c.levels.find(levelId);
            if (it == c.levels.end())
                throw std::runtime_error("--simulate: no such level '" + levelId + "'");
            // C54: say which rules the legacy preview cannot honour instead of throwing an
            // opaque constructor error, and never print a simulation of a level it did not run.
            const auto unsupported = pvz::Battle::unsupportedRules(it->second);
            if (!unsupported.empty()) {
                std::cout << pvz::Json{{"level", levelId},
                                       {"simulated", false},
                                       {"unsupported", unsupported}}
                                 .dump(2)
                          << '\n';
                return 2;
            }
            pvz::Battle b(c, it->second, 1);
            b.advance(240);
            std::cout << pvz::Json{{"level", levelId},
                                   {"simulated", true},
                                   {"state", b.snapshot()},
                                   {"events", b.events()}}
                             .dump(2)
                      << '\n';
            return 0;
        }
        if (args.size() >= 2 &&
            (args[1] == "--launcher" || args[1] == "--launcher-smoke" || args[1] == "--launcher-snapshot")) {
            const bool snapshot = args[1] == "--launcher-snapshot";
            if (args.size() != (snapshot ? 4u : 3u))
                throw std::runtime_error("invalid launcher arguments; use --help");
#ifdef PVZ_ENABLE_DESKTOP
            pvz::runLauncher(args[2], args[1] != "--launcher", snapshot ? args[3] : fs::path{});
            std::cout << "launcher=ok\n";
            return 0;
#else
            throw std::runtime_error("desktop support is disabled; rebuild with -DPVZ_ENABLE_DESKTOP=ON");
#endif
        }
        if ((args.size() == 3 || args.size() == 4) && args[1] == "--audit-content") {
            pvz::CatalogOptions options;
            if (args.size() == 4) {
                options.contentPack = args[3];
            }
            const auto c = pvz::loadCatalog(args[2], options);
            std::cout << c.summary().text() << c.rulesNote << '\n';
            return 0;
        }
        if ((args.size() >= 3 && args.size() <= 5) && args[1] == "--worldmap") {
            // The world map is otherwise only reachable from the desktop screen, so this
            // command exists to prove the model is wired to a real caller (see C41).
            fs::path content = args[2];
            std::optional<fs::path> progressPath;
            if (args.size() >= 5) {
                if (args[3] != "--progress")
                    throw std::runtime_error("unknown --worldmap option: " + pvz::pathUtf8(args[3]));
                progressPath = args[4];
            } else if (args.size() == 4) {
                throw std::runtime_error("unknown --worldmap option: " + pvz::pathUtf8(args[3]));
            }
            const pvz::map::WorldMap map =
                pvz::map::WorldMap::load(content, generatedTable(content, "world_gates.json"));
            pvz::Progress progress;
            if (progressPath) progress = pvz::loadProgress(*progressPath);
            nlohmann::json out;
            out["worlds"] = map.worlds().size();
            out["gates"] = map.gates().size();
            out["stars"] = progress.totalStars();
            out["keys"] = progress.keys;
            out["clearedLevels"] = progress.clearedLevels();
            nlohmann::json rows = nlohmann::json::array();
            for (const pvz::map::WorldInfo& world : map.worlds()) {
                // The cleared count must come from the save: hard-coding 0 made the same JSON
                // claim `clearedLevels:175` at the top and `state:available` for a finished world.
                const int cleared = pvz::map::clearedLevelsFor(progress, world.id);
                const pvz::map::WorldStatus status = map.status(world.id, progress.totalStars(),
                                                               progress.keys, cleared);
                nlohmann::json row;
                row["id"] = world.id;
                row["order"] = world.order;
                row["levels"] = world.levels;
                row["gates"] = world.gateCount;
                row["requiredStars"] = status.requiredStars;
                row["starsSource"] = status.starsSource;
                row["requiredKeys"] = status.requiredKeys;
                row["state"] = pvz::map::worldStateName(status.state);
                if (!status.reason.empty()) row["reason"] = status.reason;
                rows.push_back(std::move(row));
            }
            out["rows"] = std::move(rows);
            std::cout << out.dump() << '\n';
            return 0;
        }
                if (args.size() >= 3 && args[1] == "--shop") {
            // The shop is otherwise only reachable from the desktop screen, so this command
            // exists to prove the purchase path has a real caller (same rationale as
            // --worldmap, see C41).
            fs::path content = args[2];
            fs::path unlock = generatedTable(content, "shop_unlock.json");
            std::optional<fs::path> progressPath;
            std::optional<std::string> buy;
            int coins = 0;
            for (std::size_t i = 3; i < args.size(); ++i) {
                const std::string flag = pvz::pathUtf8(args[i]);
                auto value = [&](const char* what) -> fs::path {
                    if (i + 1 >= args.size()) {
                        throw std::runtime_error(std::string(what) + " needs a value");
                    }
                    return args[++i];
                };
                if (flag == "--unlock") {
                    unlock = value("--unlock");
                } else if (flag == "--progress") {
                    progressPath = value("--progress");
                } else if (flag == "--buy") {
                    buy = pvz::pathUtf8(value("--buy"));
                } else if (flag == "--coins") {
                    coins = std::stoi(pvz::pathUtf8(value("--coins")));
                } else {
                    throw std::runtime_error("unknown --shop option: " + flag);
                }
            }
            const pvz::Shop shop = pvz::Shop::load(content, unlock);
            pvz::Progress progress;
            if (progressPath) {
                progress = pvz::loadProgress(*progressPath);
            }
            if (coins > 0) {
                progress.coins = coins;
            }
            nlohmann::json out;
            out["items"] = shop.size();
            out["buyable"] = shop.buyable();
            out["unmodelledCurrency"] = shop.unmodelledCurrency();
            out["missingRows"] = shop.missingRows();
            nlohmann::json byUnlock = nlohmann::json::object();
            for (const auto& [kind, count] : shop.byUnlock()) {
                byUnlock[pvz::unlockKindName(kind)] = count;
            }
            out["byUnlock"] = std::move(byUnlock);
            // Everything a purchase can now write into the save, echoed by name so a caller can
            // compare the JSON before and after instead of trusting `ok`.
            auto writeInventory = [&out](const pvz::Progress& p) {
                out["coins"] = p.coins;
                out["keys"] = p.keys;
                out["gems"] = p.gems;
                out["plantfoodSlots"] = p.plantfoodSlots;
                out["plantfoodRefresh"] = p.plantfoodRefresh;
                out["costumes"] = p.costumes.size();
                out["settings"] = p.settings.size();
                out["purchases"] = p.purchases.size();
                out["seeds"] = p.seeds.size();
            };
            writeInventory(progress);
            if (buy) {
                const pvz::BuyResult result = pvz::purchase(shop, *buy, progress);
                out["ok"] = result.ok;
                out["item"] = result.itemId;
                out["reason"] = result.reason;
                out["coinsSpent"] = result.coinsSpent;
                writeInventory(progress);
                out["grantedSeed"] = result.grantedSeed;
                nlohmann::json granted = nlohmann::json::array();
                for (const pvz::Grant& grant : result.granted) {
                    nlohmann::json entry = nlohmann::json::object();
                    entry["kind"] = pvz::grantKindName(grant.kind);
                    if (!grant.text.empty()) {
                        entry["id"] = grant.text;
                    }
                    if (!grant.value.is_null()) {
                        entry["value"] = grant.value;
                    }
                    granted.push_back(std::move(entry));
                }
                out["granted"] = std::move(granted);
                if (result.ok && progressPath) {
                    pvz::saveProgress(*progressPath, progress, 0);
                }
                std::cout << out.dump() << '\n';
                return result.ok ? 0 : 1;
            }
            std::cout << out.dump() << '\n';
            return 0;
        }
if (args.size() >= 3 && args[1] == "--worldmap-screen") {
            const fs::path content = args[2];
#ifdef PVZ_ENABLE_DESKTOP
            pvz::WorldMapScreenOptions options;
            for (std::size_t i = 3; i < args.size(); ++i) {
                const auto& flag = pvz::pathUtf8(args[i]);
                if (flag == "--progress" && i + 1 < args.size()) {
                    options.progressFile = args[++i];
                } else if (flag == "--assets" && i + 1 < args.size()) {
                    options.assetRoot = args[++i];
                } else if (flag == "--snapshot" && i + 1 < args.size()) {
                    options.snapshot = args[++i];
                } else if (flag == "--frames" && i + 1 < args.size()) {
                    options.frames = std::stoi(pvz::pathUtf8(args[++i]));
                } else {
                    throw std::runtime_error("unknown --worldmap-screen option: " + flag);
                }
            }
            if (options.assetRoot.empty()) {
                // Next to the content and the executable, same search the battle preview uses.
                for (const fs::path& candidate :
                     {fs::current_path() / "PvZ2SHUTTLE" / "assets", fs::current_path() / "assets"}) {
                    if (fs::is_regular_file(candidate / "ui/font_zh.ttc")) {
                        options.assetRoot = candidate;
                        break;
                    }
                }
            }
            const pvz::Catalog catalog = pvz::loadCatalog(content);
            const pvz::map::WorldMap map =
                pvz::map::WorldMap::load(content, generatedTable(content, "world_gates.json"));
            const pvz::WorldMapScreenResult result = pvz::runWorldMapScreen(catalog, map, options);
            nlohmann::json out;
            out["worlds"] = result.worlds;
            out["unlocked"] = result.unlocked;
            out["completed"] = result.completed;
            out["stars"] = result.stars;
            out["keys"] = result.keys;
            out["selected"] = result.selectedWorld;
            out["entered"] = result.enteredWorld;
            out["level"] = result.enteredLevel;
            std::cout << out.dump() << '\n';
            return 0;
#else
            throw std::runtime_error("desktop support is disabled; rebuild with -DPVZ_ENABLE_DESKTOP=ON");
#endif
        }
        if (args.size() >= 3 && (args[1] == "--menu" || args[1] == "--level-select")) {
            // S4: the two screens that close the chain "menu -> world map -> level list -> battle".
            // Both sit behind the desktop guard for the same reason `--worldmap-screen` does: the
            // view types are only compiled when SDL is, and an audit build must not reference them.
            const fs::path content = args[2];
#ifdef PVZ_ENABLE_DESKTOP
            const bool levelSelect = args[1] == "--level-select";
            fs::path assetRoot;
            fs::path progressPath;
            fs::path snapshot;
            std::string world;
            int frames = 0;
            // T46: after the menu closes, run one headless cycle in the same process. Deliberately
            // sequential — the menu owns the only event loop here, and nesting a battle loop inside
            // it would mean two clocks in one window.
            bool flowAfter = false;
            for (std::size_t i = 3; i < args.size(); ++i) {
                const auto& flag = pvz::pathUtf8(args[i]);
                const auto value = [&](const char* what) -> fs::path {
                    if (i + 1 >= args.size()) throw std::runtime_error(std::string(what) + " needs a value");
                    return args[++i];
                };
                if (flag == "--progress") {
                    progressPath = value("--progress");
                } else if (flag == "--assets") {
                    assetRoot = value("--assets");
                } else if (flag == "--snapshot") {
                    snapshot = value("--snapshot");
                } else if (flag == "--frames") {
                    frames = std::stoi(pvz::pathUtf8(value("--frames")));
                } else if (flag == "--world" && levelSelect) {
                    world = pvz::pathUtf8(value("--world"));
                } else if (flag == "--flow-after" && !levelSelect) {
                    flowAfter = true;
                } else {
                    throw std::runtime_error("unknown " + std::string(pvz::pathUtf8(args[1])) +
                                             " option: " + flag);
                }
            }
            if (levelSelect && world.empty())
                throw std::runtime_error("--level-select needs --world <id>");
            if (assetRoot.empty()) {
                // Same discovery the other screens use, so a checkout needs no --assets.
                for (const fs::path& candidate :
                     {fs::current_path() / "PvZ2SHUTTLE" / "assets", fs::current_path() / "assets"}) {
                    if (fs::is_regular_file(candidate / "ui/font_zh.ttc")) {
                        assetRoot = candidate;
                        break;
                    }
                }
            }
            pvz::Progress progress;
            if (!progressPath.empty()) progress = pvz::loadProgress(progressPath);
            const pvz::Catalog catalog = pvz::loadCatalog(content);
            pvz::Json out;
            if (levelSelect) {
                pvz::LevelSelectOptions options;
                options.assetRoot = assetRoot;
                options.worldId = world;
                options.progressFile = progressPath;
                options.snapshot = snapshot;
                options.frames = frames;
                const pvz::LevelSelectResult result =
                    pvz::runLevelSelect(catalog, progress, options);
                out["world"] = result.world;
                out["levels"] = result.levels;
                out["cleared"] = result.cleared;
                out["selected"] = result.selectedLevel;
            } else {
                pvz::MenuOptions options;
                options.assetRoot = assetRoot;
                options.progressFile = progressPath;
                options.snapshot = snapshot;
                options.frames = frames;
                const pvz::MenuResult result = pvz::runMainMenu(catalog, progress, options);
                out["choice"] = pvz::menuChoiceName(result.choice);
                if (result.choice == pvz::MenuChoice::continueGame) {
                    // "Continue" has to name the level it means; the menu knows the save, not the
                    // catalog's ordering, so the pick comes from the same function `--flow` uses.
                    out["level"] = pvz::pickNextLevel(catalog, progress, progress.lastLevel).level;
                }
                if (flowAfter && result.choice == pvz::MenuChoice::worldMap) {
                    // The menu is closed by now (runMainMenu returned), so this second loop does not
                    // overlap the first one.
                    const auto stars = pvz::loadStarTable(content / "stars.json");
                    const pvz::FlowResult played = pvz::runFlowCycle(catalog, progress, stars,
                                                          progress.lastLevel, pvz::engine::Script{}, 600.0);
                    if (!progressPath.empty()) {
                        const auto now = std::chrono::duration_cast<std::chrono::seconds>(
                                             std::chrono::system_clock::now().time_since_epoch())
                                             .count();
                        pvz::saveProgress(progressPath, progress, now);
                    }
                    out["flow"] = played.json();
                }
            }
            std::cout << out.dump() << '\n';
            return 0;
#else
            throw std::runtime_error("desktop support is disabled; rebuild with -DPVZ_ENABLE_DESKTOP=ON");
#endif
        }
        if (args.size() != 3)
            throw std::runtime_error("expected a command and a directory; use --help");
        throw std::runtime_error("unknown command: " + pvz::pathUtf8(args[1]) + "; use --help");
    } catch (const std::exception& e) {
        std::cerr << "error: " << e.what() << '\n';
        return 1;
    }
}
#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    std::vector<fs::path> args;
    args.reserve(static_cast<std::size_t>(argc));
    for (int i = 0; i < argc; ++i) args.emplace_back(argv[i]);
    // T49: `--volume`, `--mute-bgm`, `--mute-sfx` and `--audio-off` are global switches, not
    // positional arguments: they are stripped here, so no branch has to grow an extra size check,
    // and the views read the result through attachAudio(). `--audio-off` is a latch inside
    // applyAudioOptions(), so a later `--volume` cannot un-silence a screenshot run.
    const auto audioOptions = pvz::parseAudioOptions(args);
    if (!audioOptions.ok) {
        std::cerr << "error: " << audioOptions.error << '\n';
        return 1;
    }
    pvz::applyAudioOptions(audioOptions.options);
    return run(args);
}
