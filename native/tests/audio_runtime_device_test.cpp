#include "audio/audio_runtime.hpp"
#include "catalog.hpp"
#include "engine/world.hpp"

#include <chrono>
#include <cstdio>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <thread>

// T45, desktop configuration only: the one case that needs a real sound card. It runs three
// seconds of a real frontyard battle through the same per-frame calls `BattleScene` makes
// (`consume` + `pump`), then asks the mixer how many frames it actually produced.
//
// A machine without an audio device is not a failure and not a pass: the case prints the reason
// and exits 77, which CMake maps to CTest's `Skipped` so the suite never claims green for a
// device it never touched.

namespace fs = std::filesystem;
using namespace pvz;

namespace {
void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}
}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc < 4) {
        fprintf(stderr, "usage: audio_runtime_device_test <assets> <content> <content.pack>\n");
        return 2;
    }
    try {
        const fs::path assets = argv[1];
        const fs::path content = argv[2];
        const fs::path pack = argv[3];
        CatalogOptions options;
        if (!pack.empty()) options.contentPack = pack;
        const auto started = std::chrono::steady_clock::now();
        const auto ms = [&started] {
            return static_cast<long long>(std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - started).count());
        };
        const Catalog catalog = loadCatalog(content, options);
        const auto found = catalog.levels.find("frontyard_1");
        if (found == catalog.levels.end()) throw std::runtime_error("frontyard_1 is missing");
        printf("phase: catalog %lld ms\n", ms());
        const AudioCatalog audio = AudioCatalog::load(assets);
        printf("phase: audio catalog %lld ms\n", ms());
        AudioRuntime runtime(audio, AudioMode::live);
        printf("phase: backend %lld ms\n", ms());
        if (!runtime.deviceAvailable()) {
            printf("SKIP audio_runtime_device_test: no audio device (%s)\n", runtime.note().c_str());
            return 77;
        }
        check(runtime.enabled(), "a device that opened must enable the runtime");
        runtime.playMusicForWorld(found->second.world);
        printf("phase: music %lld ms\n", ms());
        check(runtime.musicName() == "frontyard_loop",
              "frontyard must start frontyard_loop, got " + runtime.musicName());

        engine::World world(catalog, found->second, 1);
        world.plant("sunflower", 0, 0);
        world.plant("peashooter", 0, 1);
        std::string zombieType = "basic";
        for (const auto& wave : found->second.waves)
            if (!wave.zombies.empty()) {
                zombieType = wave.zombies.front().type;
                break;
            }
        (void)world.spawnZombie(zombieType, 0);

        // Three seconds of wall clock, one pump per 20 ms: the same shape as the battle loop.
        std::size_t cursor = 0;
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
        while (std::chrono::steady_clock::now() < deadline) {
            cursor = runtime.consume(world.events(), cursor);
            runtime.pump();
            std::this_thread::sleep_for(std::chrono::milliseconds(20));
            world.step();
        }
        runtime.pump();
        printf("phase: battle %lld ms\n", ms());
        const std::size_t mixed = runtime.backend() != nullptr ? runtime.backend()->mixedFrames() : 0;
        const auto& counters = runtime.counters();
        printf("device: %s\n", runtime.status().c_str());
        printf("music: %s (starts %zu)\n", runtime.musicName().c_str(), counters.musicStarts);
        printf("events: seen %zu mapped %zu unmapped %zu deduped %zu\n", counters.eventsSeen,
               counters.eventsMapped, counters.eventsUnmapped, counters.eventsDeduped);
        printf("pump: %zu calls, %zu mixed frames, %zu sfx calls\n", counters.pumpCalls, mixed,
               counters.playSfxCalls);
        check(counters.pumpCalls > 0, "the loop must pump");
        check(mixed > 0, "three seconds of battle must leave mixed frames on the device queue");
        check(runtime.backend()->loadedClips() > 0, "the music clip must have been decoded");

        // T49: `mix()` writes the very buffer SDL_PutAudioStreamData hands to the device, so a peak
        // read here is the peak the device received. Compare volume 100 with volume 0, and say how
        // many frames each window mixed, so a stale lastPeak() cannot be mistaken for silence.
        const auto peakAtVolume = [&runtime](int volume, std::size_t& mixedFrames) {
            runtime.setVolume(volume);
            const auto until = std::chrono::steady_clock::now() + std::chrono::milliseconds(240);
            float peak = 0.0F;
            while (std::chrono::steady_clock::now() < until) {
                runtime.pump();
                peak = runtime.lastPeak();
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
            mixedFrames = runtime.backend() != nullptr ? runtime.backend()->mixedFrames() : 0;
            return peak;
        };
        std::size_t loudFrames = 0;
        const float loud = peakAtVolume(100, loudFrames);
        std::size_t silentFrames = 0;
        const float silent = peakAtVolume(0, silentFrames);
        runtime.setVolume(100);
        printf("peak: volume 100 = %.6f (%zu frames), volume 0 = %.6f (%zu frames)\n", loud,
               loudFrames - mixed, silent, silentFrames - mixed);
        check(loud > 0.0F, "volume 100 must leave a non-zero peak in the device buffer");
        check(silentFrames > loudFrames, "the volume 0 window must have mixed new frames");
        check(silent == 0.0F, "volume 0 must push silence to the device");
        printf("audio runtime device test passed\n");
        return 0;
    } catch (const std::exception& error) {
        fprintf(stderr, "audio runtime device test failed: %s\n", error.what());
        return 1;
    }
}
