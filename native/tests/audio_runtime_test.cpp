#include "audio/audio_runtime.hpp"
#include "catalog.hpp"
#include "engine/world.hpp"

#include <algorithm>
#include <cstdio>
#include <filesystem>
#include <iostream>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

// T45: the audio pipeline was audited in T38 but nothing played. These cases pin the three
// behaviours that make playing it safe without a sound card:
//   1. one (tick, event type) pair plays exactly once, however many pellets that tick contained;
//   2. a headless screenshot run and an `--audio-off` run forward zero calls to the backend;
//   3. the real frontyard battle actually produces mapped events, named, not just counted.
// The audit configuration links the null backend (`available() == false`), which is exactly the
// no-device degradation the plan asks to prove: every assertion below runs on that path.

namespace fs = std::filesystem;
using namespace pvz;

namespace {

void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

/// `(tick, type)` pairs that the table maps to a sound, computed independently of the runtime so
/// the dedupe assertion cannot be satisfied by the same code that does the dedupe.
std::set<std::pair<std::uint64_t, std::string>> mappedPairs(const nlohmann::json& events,
                                                            const EventMap& map) {
    std::set<std::pair<std::uint64_t, std::string>> pairs;
    for (const auto& entry : events) {
        if (!entry.is_object()) continue;
        const auto type = entry.find("type");
        if (type == entry.end() || !type->is_string()) continue;
        if (map.soundForEngineEvent(type->get<std::string>()).empty()) continue;
        pairs.emplace(entry.value("tick", std::uint64_t{0}), type->get<std::string>());
    }
    return pairs;
}

AudioCatalog loadCatalogFrom(const fs::path& assets) { return AudioCatalog::load(assets); }

/// Six events across two ticks: three identical pellets in tick 10, one hit, one unmapped engine
/// event and one pellet in tick 11. Only three of them may reach the backend.
nlohmann::json pelletBurst() {
    return nlohmann::json::parse(R"([
        {"tick": 10, "type": "shot_fired", "details": {}},
        {"tick": 10, "type": "shot_fired", "details": {}},
        {"tick": 10, "type": "shot_fired", "details": {}},
        {"tick": 10, "type": "shot_hit", "details": {}},
        {"tick": 10, "type": "level_start", "details": {}},
        {"tick": 11, "type": "shot_fired", "details": {}}
    ])");
}

void testDedupe(const fs::path& assets) {
    const AudioCatalog catalog = loadCatalogFrom(assets);
    AudioRuntime runtime(catalog, AudioMode::live);
    const nlohmann::json events = pelletBurst();
    const std::size_t cursor = runtime.consume(events, 0);
    check(cursor == events.size(), "consume must report the new cursor at the end of the stream");
    const auto& c = runtime.counters();
    check(c.eventsSeen == 6, "consume must see all six events, saw " + std::to_string(c.eventsSeen));
    check(c.eventsUnmapped == 1, "level_start must be counted as unmapped, saw " +
                                     std::to_string(c.eventsUnmapped));
    check(c.eventsMapped == 3, "three (tick, type) pairs are mapped, saw " +
                                   std::to_string(c.eventsMapped));
    check(c.eventsDeduped == 2, "two pellets in tick 10 must be deduped, saw " +
                                    std::to_string(c.eventsDeduped));
    check(c.sfxRequests == 3, "three requests survive the dedupe, saw " + std::to_string(c.sfxRequests));
    // A build without SDL (and a machine without a device) forwards nothing: the request is
    // counted, the backend stays silent, and the test names which of the two it saw.
    const std::size_t expectCalls = runtime.deviceAvailable() ? 3U : 0U;
    check(c.playSfxCalls == expectCalls,
          std::string("backend calls must be ") + (runtime.deviceAvailable() ? "three" : "zero (no device)") +
              ", saw " + std::to_string(c.playSfxCalls));
    const auto& played = runtime.playedLog();
    check(std::find(played.begin(), played.end(), "sfx_shoot") != played.end(),
          "shot_fired must resolve to sfx_shoot");
    check(std::find(played.begin(), played.end(), "shoot_hit") != played.end(),
          "shot_hit must resolve to shoot_hit");
    check(std::find(played.begin(), played.end(), "level_start") == played.end(),
          "an unmapped event must never invent a sound");
    // Re-consuming from the returned cursor replays nothing: the stream is append-only.
    check(runtime.consume(events, cursor) == cursor, "the cursor must stay put at the end");
    check(runtime.counters().playSfxCalls == expectCalls, "a second consume must not replay the burst");
    // In the audit build there is no device: the request is counted, the sound is not heard, and
    // the runtime says so instead of pretending.
    // The audit build has no SDL and therefore no device; the desktop build usually has one, and a
    // headless CI box may not. Both outcomes are legal: what must hold is that a request is only
    // forwarded when a device exists, which the playSfxCalls check above already pins.
    check(runtime.enabled() == runtime.deviceAvailable(),
          std::string("the runtime is enabled exactly when a device exists (device=") +
              (runtime.deviceAvailable() ? "yes" : "no") + ")");
    check(runtime.deviceAvailable() == (expectCalls == 3U),
          std::string("a forwarded call and a present device must agree (device=") +
              (runtime.deviceAvailable() ? "yes" : "no") + ", calls=" +
              std::to_string(c.playSfxCalls) + ")");
    check(runtime.status().find("live") == 0, "status must start with the mode, got " + runtime.status());
    runtime.pump();
    check(runtime.counters().pumpCalls == 1, "pump must count the call");
}

void testMutedAndHeadless(const fs::path& assets) {
    const AudioCatalog catalog = loadCatalogFrom(assets);
    const nlohmann::json events = pelletBurst();
    for (const AudioMode mode : {AudioMode::muted, AudioMode::headless}) {
        AudioRuntime runtime(catalog, mode);
        const std::string label = mode == AudioMode::muted ? "muted" : "headless";
        runtime.consume(events, 0);
        runtime.pump();
        const auto& c = runtime.counters();
        check(c.playSfxCalls == 0, label + " mode must forward zero playSfx calls, saw " +
                                       std::to_string(c.playSfxCalls));
        check(c.musicStarts == 0, label + " mode must start no music");
        check(c.sfxRequests == 3, label + " mode still counts what it would have played, saw " +
                                      std::to_string(c.sfxRequests));
        check(!runtime.enabled(), label + " mode must not be enabled");
        check(runtime.backend() == nullptr, label + " mode must not create a backend at all");
        runtime.playMusicForWorld("frontyard");
        check(runtime.musicName() == "frontyard_loop",
              label + " mode must still resolve the world track, got " + runtime.musicName());
        check(runtime.counters().musicStarts == 0,
              label + " mode must not hand the track to a device");
    }
}

void testRealBattle(const fs::path& assets, const fs::path& content, const fs::path& pack) {
    CatalogOptions options;
    if (!pack.empty()) options.contentPack = pack;
    const Catalog catalog = loadCatalog(content, options);
    const auto found = catalog.levels.find("frontyard_1");
    check(found != catalog.levels.end(), "frontyard_1 must exist in the shipped content");
    const LevelDefinition& level = found->second;

    const AudioCatalog audio = loadCatalogFrom(assets);
    AudioRuntime runtime(audio, AudioMode::live);
    engine::World world(catalog, level, 1);
    world.plant("sunflower", 0, 0);
    world.plant("peashooter", 0, 1);
    std::string zombieType = "basic";
    for (const auto& wave : level.waves)
        if (!wave.zombies.empty()) {
            zombieType = wave.zombies.front().type;
            break;
        }
    (void)world.spawnZombie(zombieType, 0);

    // Two seconds of battle at the engine's fixed 60 Hz tick.
    constexpr std::size_t kFrames = 120;
    std::size_t cursor = 0;
    for (std::size_t tick = 0; tick < kFrames; ++tick) {
        world.step();
        cursor = runtime.consume(world.events(), cursor);
        runtime.pump();
    }
    const auto& c = runtime.counters();
    check(c.eventsSeen > 0, "a running battle must emit events");
    check(c.sfxRequests > 0, "a running battle must request at least one sound");
    check(runtime.playedLog().size() > 0, "the played log must name what the battle asked for");
    check(std::find(runtime.playedLog().begin(), runtime.playedLog().end(), "sfx_shoot") !=
              runtime.playedLog().end(),
          "a peashooter with a zombie in its lane must ask for sfx_shoot");
    // Independent cross-check: the runtime played exactly one sound per mapped (tick, type) pair.
    const auto expected = mappedPairs(world.events(), runtime.events());
    check(c.sfxRequests == expected.size(),
          "one sound per mapped (tick, type): expected " + std::to_string(expected.size()) + ", got " +
              std::to_string(c.sfxRequests));
    // Without a device the request stops at the runtime; with one, every surviving request
    // must be handed to the backend. Either way the count is explained, never silently dropped.
    check(c.playSfxCalls == (runtime.deviceAvailable() ? c.sfxRequests : 0U),
          "every surviving request must reach the backend (" +
              std::string(runtime.deviceAvailable() ? "device present" : "no device") + "), saw " +
              std::to_string(c.playSfxCalls));
    check(c.pumpCalls == kFrames, "pump must have been called once per frame");
    check(world.events().size() == cursor, "the cursor must consume the whole event stream");
}

void testAmbientSwitch(const fs::path& assets) {
    resetAudioForTest();
    check(ambientAudio() == nullptr, "a fresh process has no runtime");
    check(!audioOff(), "a fresh process is not muted");
    const nlohmann::json events = pelletBurst();
    check(consumeAudioEvents(events, 4) == 4, "without a runtime the cursor must not move");
    pumpAudio();
    playAudioClick();

    AudioRuntime* headless = attachAudio(assets, true);
    check(headless != nullptr, "the shipped assets must attach in headless mode");
    check(headless->mode() == AudioMode::headless, "a screenshot run must attach as headless");
    check(!headless->enabled(), "headless must not be enabled");
    check(headless->backend() == nullptr, "headless must not open a device");
    check(attachAudio(assets, true) == headless, "attaching twice reuses one runtime");
    pumpAudio();
    check(headless->counters().pumpCalls == 1, "pumpAudio must forward to the ambient runtime");

    setAudioOff(true);
    AudioRuntime* muted = attachAudio(assets, false);
    check(muted != nullptr, "the shipped assets must attach with --audio-off");
    check(muted->mode() == AudioMode::muted, "with --audio-off the runtime must be muted");
    check(muted != headless, "a new mode builds a new runtime");
    playAudioClick();
    check(muted->counters().playSfxCalls == 0, "--audio-off must forward zero clicks");
    check(muted->counters().sfxRequests == 1, "--audio-off still counts the click it dropped");

    resetAudioForTest();
    check(ambientAudio() == nullptr, "resetAudioForTest must drop the runtime");
    check(!audioOff(), "resetAudioForTest must clear the switch");
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc < 4) {
        fprintf(stderr, "usage: audio_runtime_test <assets> <content> <content.pack>\n");
        return 2;
    }
    try {
        const fs::path assets = argv[1];
        const fs::path content = argv[2];
        const fs::path pack = argv[3];
        testDedupe(assets);
        testMutedAndHeadless(assets);
        testRealBattle(assets, content, pack);
        testAmbientSwitch(assets);
        printf("audio runtime tests passed\n");
        return 0;
    } catch (const std::exception& error) {
        fprintf(stderr, "audio runtime test failed: %s\n", error.what());
        return 1;
    }
}
