// T38 audio: catalog counts against the shipped assets, the event table, the WAV/OGG decoders,
// the mixer and the `--audio-audit` payload. Everything here is SDL-free on purpose, so the same
// test runs in the AuditOnly configuration.
//
// Fixtures are written under PVZ_TEST_TEMP because the repository lives on a path with non-ASCII
// characters and the tests must not assume they may write into the checkout.
#include "audio/audio_audit.hpp"
#include "audio/audio_catalog.hpp"
#include "audio/audio_decode.hpp"
#include "audio/audio_mixer.hpp"
#include "audio/audio_runtime.hpp"
#include "audio/event_map.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <filesystem>
#include <functional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#include <vector>

namespace fs = std::filesystem;

namespace {

void check(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error(what);
}

std::string describe(const fs::path& path) { return pvz::audioPathUtf8(path); }

std::string expectThrow(const std::function<void()>& body, const std::string& what) {
    try {
        body();
    } catch (const std::exception& error) {
        return error.what();
    }
    throw std::runtime_error(what + ": expected a throw, nothing was thrown");
}

float peak(const std::vector<float>& samples) {
    float loudest = 0.0F;
    for (const float sample : samples) loudest = std::max(loudest, std::fabs(sample));
    return loudest;
}

/// ① Catalog: the counts the task pins, and where every entry came from.
void testCatalog(const fs::path& assets) {
    const auto catalog = pvz::AudioCatalog::load(assets);
    check(catalog.sounds.size() == 65, "catalog should hold 65 sounds, got " +
                                           std::to_string(catalog.sounds.size()));
    check(catalog.count(pvz::SoundKind::bgm) == 26,
          "expected 26 bgm, got " + std::to_string(catalog.count(pvz::SoundKind::bgm)));
    check(catalog.count(pvz::SoundKind::sfx) == 18,
          "expected 18 sfx, got " + std::to_string(catalog.count(pvz::SoundKind::sfx)));
    check(catalog.count(pvz::SoundKind::obb) == 21,
          "expected 21 obb tracks, got " + std::to_string(catalog.count(pvz::SoundKind::obb)));
    // audio_report.json carries 10 entries; the other 8 sfx are only on disk, so the catalog has
    // to merge the manifest with a directory scan instead of trusting the report alone.
    check(catalog.reportEntries == 10,
          "audio_report.json should contribute 10 entries, got " +
              std::to_string(catalog.reportEntries));
    check(catalog.scannedEntries == 34,
          "directory scan should add 34 entries, got " + std::to_string(catalog.scannedEntries));
    check(catalog.obbEntries == 21,
          "durations.json should list 21 tracks, got " + std::to_string(catalog.obbEntries));
    check(catalog.missingFiles == 0,
          "every catalogued file should exist, " + std::to_string(catalog.missingFiles) +
              " missing");

    for (const char* name : {"frontyard_loop", "menu", "victory", "defeat"})
        check(catalog.find(name) != nullptr, std::string("bgm `") + name + "` is not catalogued");
    for (const char* name : {"plant", "plant_sprout", "sfx_click", "sfx_die", "sfx_error",
                             "sfx_plant", "sfx_shoot", "sfx_shovel", "sfx_sun", "sfx_wave",
                             "sun_collect", "zombie_groan", "zombie_groan2", "shoot_hit",
                             "ui_open", "ui_close", "coin_drop", "gem_spawn"})
        check(catalog.find(name) != nullptr, std::string("sfx `") + name + "` is not catalogued");

    // `source` has to distinguish the manifest from the scan, otherwise the 8 scan-only sfx look
    // like they came from audio_report.json.
    check(catalog.find("sfx_shoot")->source == "scan", "sfx_shoot should come from the scan");
    check(catalog.find("zombie_groan")->source == "report",
          "zombie_groan should come from audio_report.json");
    std::printf("catalog: 26 bgm, 18 sfx, 21 obb (65 sounds; 10 report, 34 scan)\n");
}

/// ② Event table: the 11 pinned classes, the engine event names, and the honest nulls.
void testEventMap(const pvz::AudioCatalog& catalog) {
    const pvz::EventMap events;
    for (const char* event : {"plant", "shoot", "hit", "sun", "wave", "die", "click", "error",
                              "shovel", "win", "lose"}) {
        const std::string sound = events.soundFor(event);
        check(!sound.empty(), std::string("event `") + event + "` has no sound");
        check(catalog.find(sound) != nullptr,
              std::string("event `") + event + "` maps to `" + sound +
                  "` which is not in the catalog");
    }

    // The five engine events that already have a real source, plus the four the captain wired.
    struct Expectation {
        const char* event;
        const char* sound;
    };
    const Expectation expectations[] = {
        {"planted", "plant"},        {"shovelled", "sfx_shovel"},
        {"sun_collected", "sun_collect"}, {"sun_spawned", "sfx_sun"},
        {"shot_fired", "sfx_shoot"}, {"shot_hit", "shoot_hit"},
        {"wave_spawn", "sfx_wave"},  {"zombie_died", "sfx_die"},
        {"level_won", "victory"},    {"level_lost", "sfx_die"},
        {"mower_triggered", "sfx_wave"}, {"input_rejected", "sfx_error"},
        {"plant_fed", "plant_sprout"}, {"boss_died", "sfx_die"},
    };
    for (const auto& expectation : expectations) {
        const pvz::GameEventSound* entry = nullptr;
        for (const auto& candidate : events.gameEvents())
            if (candidate.event == expectation.event) entry = &candidate;
        check(entry != nullptr,
              std::string("engine event `") + expectation.event + "` is missing from the table");
        check(entry->sound == expectation.sound,
              std::string("engine event `") + expectation.event + "` should play `" +
                  expectation.sound + "`, table says `" + entry->sound + "`");
    }

    std::size_t mapped = 0;
    for (const auto& entry : events.gameEvents()) {
        if (entry.sound.empty()) continue;
        ++mapped;
        check(catalog.find(entry.sound) != nullptr,
              "engine event `" + entry.event + "` plays `" + entry.sound +
                  "` which is not in the catalog");
    }
    check(mapped >= 11, "at least 11 engine events must be mapped, got " + std::to_string(mapped));

    const auto unwired = events.unwiredGameEvents();
    check(!unwired.empty(), "the unwired list must not be empty: the assets lack those samples");
    for (const char* expected : {"plant_died", "explosion", "fusion"})
        check(std::find(unwired.begin(), unwired.end(), expected) != unwired.end(),
              std::string("`") + expected + "` should be listed as unwired");
    for (const auto& event : unwired)
        for (const auto& entry : events.gameEvents())
            if (entry.event == event)
                check(entry.sound.empty(), "`" + event + "` is listed as unwired but has a sound");
    std::printf("event map: %zu engine events, %zu mapped, %zu unwired: ", events.gameEvents().size(),
                mapped, unwired.size());
    for (std::size_t i = 0; i < unwired.size(); ++i)
        std::printf("%s%s", i == 0 ? "" : ", ", unwired[i].c_str());
    std::printf("\n");

    // BGM: `<world>_loop` first, `audio/obb/` only as a fallback, and every world must resolve.
    const auto plan = pvz::planMusic(catalog, events);
    check(plan.size() == 12, "expected 12 world music selections, got " + std::to_string(plan.size()));
    for (const auto& selection : plan) {
        check(!selection.track.empty() && selection.present,
              "world `" + selection.world + "` has no playable track");
        check(!selection.fromObb, "world `" + selection.world +
                                      "` should use its own track, not the obb fallback");
        std::printf("music: %-20s -> %s (%s)\n", selection.world.c_str(), selection.track.c_str(),
                    selection.note.c_str());
    }
}

/// ③ WAV: the header parser the catalog and the mixer both stand on.
void testWav(const pvz::AudioCatalog& catalog) {
    const auto click = pvz::readWavHeader(catalog.audioDir / "sfx_click.wav");
    check(click.audioFormat == 1 && click.channels == 1 && click.sampleRate == 22050 &&
              click.bitsPerSample == 16,
          "sfx_click.wav should be PCM16 22050 Hz mono");
    check(click.frames == 1102, "sfx_click.wav should hold 1102 frames, got " +
                                    std::to_string(click.frames));
    check(std::fabs(click.seconds - 0.049977) < 0.0005, "sfx_click.wav duration is wrong");

    const auto sun = pvz::readWavHeader(catalog.audioDir / "sun_collect.wav");
    check(sun.sampleRate == 48000 && sun.channels == 1 && sun.bitsPerSample == 16,
          "sun_collect.wav should be PCM16 48000 Hz mono");
    check(sun.frames == 84191, "sun_collect.wav should hold 84191 frames, got " +
                                   std::to_string(sun.frames));

    const auto decoded = pvz::decodeWavFile(catalog.audioDir / "sfx_click.wav");
    check(decoded.frames == 1102 && decoded.samples.size() == 1102,
          "decodeWavFile should return 1102 mono samples");
    check(peak(decoded.samples) > 0.01F, "sfx_click.wav decodes to silence");

    // A non-WAV file has to be rejected with the documented prefix, not read as garbage.
    const std::string wrong = expectThrow(
        [&] { pvz::readWavHeader(catalog.audioDir / "menu.ogg"); }, "readWavHeader(menu.ogg)");
    check(wrong.find("audio catalog: ") == 0 && wrong.find("not a RIFF container") != std::string::npos,
          "unexpected readWavHeader error: " + wrong);
    std::printf("wav: sfx_click 1102 frames @22050, sun_collect 84191 frames @48000\n");
}

/// ④ OGG through the vendored stb_vorbis, and the probe that measures without keeping samples.
void testOgg(const pvz::AudioCatalog& catalog) {
    const pvz::Sound* track = catalog.find("MUSIC_PLANTSNOWLOTUS_67071061");
    check(track != nullptr, "MUSIC_PLANTSNOWLOTUS_67071061 should be catalogued from durations.json");
    const auto path = catalog.assetRoot / track->file;
    const auto decoded = pvz::decodeOggFile(path);
    check(!decoded.empty(), "the obb track decoded to nothing");
    check(decoded.sampleRate >= 8000 && decoded.channels >= 1, "decoded Ogg has no usable format");
    check(std::fabs(decoded.seconds - 6.0) < 0.2,
          "MUSIC_PLANTSNOWLOTUS should last ~6.0 s, decoded " + std::to_string(decoded.seconds) +
              " s");
    const auto probe = pvz::probeAudioFile(path);
    check(probe.decoded && probe.frames == decoded.frames,
          "probeAudioFile should agree with decodeOggFile on the frame count");
    check(std::fabs(probe.seconds - decoded.seconds) < 0.001, "probe seconds disagree with decode");
    std::printf("ogg: %s %.3f s, %llu frames, %d ch @%d Hz\n", track->file.c_str(), decoded.seconds,
                static_cast<unsigned long long>(decoded.frames), decoded.channels,
                decoded.sampleRate);

    // The biggest world track, timed: this is the number the mixer work must not move. The decode
    // path is a different translation unit from the mixer, so the guard is loose (machine load moves
    // it by 2x) and only catches a real regression such as the O(n^2) reserve that T45 fixed.
    const pvz::Sound* worldTrack = catalog.find("frontyard_loop");
    check(worldTrack != nullptr, "frontyard_loop should be catalogued from the audio directory");
    const auto started = std::chrono::steady_clock::now();
    const auto worldTrackAudio = pvz::decodeOggFile(catalog.assetRoot / worldTrack->file);
    const auto elapsed =
        std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() -
                                                              started)
            .count();
    check(!worldTrackAudio.empty(), "frontyard_loop decoded to nothing");
    check(elapsed < 5000, "frontyard_loop must decode in well under 5 s, took " +
                              std::to_string(elapsed) + " ms");
    std::printf("decode: frontyard_loop %llu frames in %lld ms\n",
                static_cast<unsigned long long>(worldTrackAudio.frames),
                static_cast<long long>(elapsed));
}

/// ④b MP3 through the vendored minimp3, and the measurement behind the T49 decision to vendor it:
/// the five mp3 sounds are not interchangeable with their WAV fallbacks (ui_open is 5.6 s, the
/// `sfx_click` fallback is 0.05 s), so "just use the wav" was not an option.
void testMp3(const pvz::AudioCatalog& catalog) {
    struct Expectation {
        const char* name;
        double seconds;
        int channels;
    };
    const Expectation expectations[] = {
        {"ui_open", 5.578, 2}, {"ui_close", 2.336, 2}, {"shoot_hit", 1.469, 1},
        {"coin_drop", 0.404, 1}, {"gem_spawn", 2.251, 1},
    };
    for (const auto& expected : expectations) {
        const pvz::Sound* sound = catalog.find(expected.name);
        check(sound != nullptr, std::string(expected.name) + " should be catalogued from the report");
        check(sound->format == "mp3", std::string(expected.name) + " should be catalogued as mp3");
        const auto path = catalog.assetRoot / sound->file;
        const auto decoded = pvz::decodeMp3File(path);
        check(!decoded.empty(), std::string(expected.name) + " decoded to nothing");
        check(decoded.channels == expected.channels,
              std::string(expected.name) + " channel count changed");
        check(std::fabs(decoded.seconds - expected.seconds) < 0.01,
              std::string(expected.name) + " should last " + std::to_string(expected.seconds) +
                  " s, decoded " + std::to_string(decoded.seconds) + " s");
        const auto probe = pvz::probeAudioFile(path);
        check(probe.decoded && probe.frames == decoded.frames,
              std::string(expected.name) + ": the probe must agree with the decoder");
        std::printf("mp3: %-11s %6.3f s, %7llu frames, %d ch @%d Hz\n", expected.name,
                    decoded.seconds, static_cast<unsigned long long>(decoded.frames),
                    decoded.channels, decoded.sampleRate);
    }
    // The fallbacks the event table used before, for the same comparison the review asks for.
    const pvz::Sound* click = catalog.find("sfx_click");
    const pvz::Sound* shoot = catalog.find("sfx_shoot");
    check(click != nullptr && shoot != nullptr, "the wav fallbacks should be catalogued");
    const double clickSeconds = pvz::decodeWavFile(catalog.assetRoot / click->file).seconds;
    const double shootSeconds = pvz::decodeWavFile(catalog.assetRoot / shoot->file).seconds;
    check(clickSeconds < 0.5 && shootSeconds < 0.5,
          "the fallbacks are short clicks; the mp3s are one to two orders of magnitude longer");
    std::printf("mp3: fallbacks %s %.3f s, %s %.3f s -- not interchangeable with the mp3s above\n",
                click->name.c_str(), clickSeconds, shoot->name.c_str(), shootSeconds);
}

/// ⑤ Mixer: gain, mute and the fact that mixing actually produces samples.
void testMixer(const pvz::AudioCatalog& catalog) {
    const auto decoded = pvz::decodeWavFile(catalog.audioDir / "sfx_shoot.wav");
    pvz::AudioClip clip;
    clip.name = "sfx_shoot";
    clip.sampleRate = decoded.sampleRate;
    clip.channels = decoded.channels;
    clip.samples = decoded.samples;

    pvz::AudioMixer mixer;
    check(mixer.playSfx(clip, 1.0F), "playSfx should accept a decoded clip");
    std::vector<float> buffer(512 * 2, 0.0F);
    mixer.mix(buffer.data(), 512);
    check(mixer.mixedFrames() == 512, "the mixer should report 512 mixed frames");
    check(peak(buffer) > 0.01F, "the first 512 frames of sfx_shoot are silent");

    // Master volume 0 is silence, not "quiet": the audit uses this to prove the mute path.
    mixer.stopAll();
    mixer.setMasterVolume(0.0F);
    mixer.playSfx(clip, 1.0F);
    std::vector<float> silent(512 * 2, 0.0F);
    mixer.mix(silent.data(), 512);
    check(peak(silent) == 0.0F, "master volume 0 must produce silence");

    mixer.setMasterVolume(1.0F);
    mixer.setMuted(true);
    mixer.stopAll();
    mixer.playSfx(clip, 1.0F);
    std::fill(silent.begin(), silent.end(), 0.0F);
    mixer.mix(silent.data(), 512);
    check(peak(silent) == 0.0F, "muted output must produce silence");

    // Mono 22050 Hz has to be resampled to the 48 kHz stereo device rate, so 480 output frames
    // must consume about 220 of the 1984 source frames.
    mixer.setMuted(false);
    mixer.stopAll();
    mixer.playMusic(clip, true, 1.0F);
    check(mixer.musicPlaying(), "playMusic should start the music voice");
    std::vector<float> music(480 * 2, 0.0F);
    mixer.mix(music.data(), 480);
    check(peak(music) > 0.01F, "music should be audible after 480 frames");
    std::printf("mixer: 512 frames from sfx_shoot, volume/mute produce silence as specified\n");
}

/// ⑧ Interpolation: a 24 kHz clip whose samples are {0, 1} must come out as a triangle at 48 kHz,
/// because consecutive output frames land half a source frame apart. The expected values are
/// hand-computed here, not taken from the implementation, and compared to 1e-6.
void testInterpolation() {
    const auto mono = [](int rate, std::vector<float> samples, const char* name) {
        pvz::AudioClip clip;
        clip.name = name;
        clip.sampleRate = rate;
        clip.channels = 1;
        clip.samples = std::move(samples);
        return clip;
    };

    // 24 kHz -> 48 kHz is exactly ratio 0.5, so the phase walks 0, 0.5, 1.0, 1.5, 2.0 (wrap to 0).
    // Linear interpolation gives 0, 0.5, 1.0, 0.5, 0; nearest-neighbour would give 0, 0, 1, 1, 0.
    const pvz::AudioClip ramp24 = mono(24000, {0.0F, 1.0F}, "ramp24");
    check(std::fabs(pvz::AudioMixer::sampleAt(ramp24, 0.5, 0) - 0.5F) < 1e-6F,
          "sampleAt at phase 0.5 must interpolate to 0.5, got " +
              std::to_string(pvz::AudioMixer::sampleAt(ramp24, 0.5, 0)));

    pvz::AudioMixer mixer;
    check(mixer.playMusic(ramp24, true, 1.0F), "the 24 kHz ramp should start as music");
    std::vector<float> out(5 * 2, 0.0F);
    mixer.mix(out.data(), 5);
    const float expected24[5] = {0.0F, 0.5F, 1.0F, 0.5F, 0.0F};
    for (int i = 0; i < 5; ++i) {
        const float got = out[static_cast<std::size_t>(i) * 2];
        check(std::fabs(got - expected24[i]) < 1e-6F,
              "24 kHz clip frame " + std::to_string(i) + " must be " +
                  std::to_string(expected24[i]) + " after interpolation, got " + std::to_string(got));
    }

    // 44.1 kHz is the awkward one: ratio 0.91875, so the first output frame sits at phase 0.91875
    // and must read 0.91875 of the way to the second sample, not round down to the first.
    const pvz::AudioClip ramp44 = mono(44100, {0.0F, 1.0F}, "ramp44");
    check(std::fabs(pvz::AudioMixer::sampleAt(ramp44, 0.91875, 0) - 0.91875F) < 1e-6F,
          "a 44.1 kHz clip must be sampled at the fractional phase, not the nearest sample");

    // 48 kHz passes straight through: no interpolation error may be introduced at ratio 1.
    const pvz::AudioClip native48 = mono(48000, {0.25F, -0.5F}, "native48");
    pvz::AudioMixer passthrough;
    check(passthrough.playSfx(native48, 1.0F), "the 48 kHz clip should start as an effect");
    std::vector<float> exact(2 * 2, 0.0F);
    passthrough.mix(exact.data(), 2);
    check(std::fabs(exact[0] - 0.25F) < 1e-6F && std::fabs(exact[2] + 0.5F) < 1e-6F,
          "a 48 kHz source must pass through unchanged");

    std::printf("interpolation: 24k -> {0, 0.5, 1, 0.5, 0}, 44.1k phase 0.91875 -> 0.918750, "
                "48k passthrough exact\n");
}

/// ⑨ Voice pool: sixteen effect voices, and a full pool evicts by (priority, start order).
void testVoiceStealing() {
    // One clip per voice: the mixer keeps a pointer, so a single mutable clip would make every
    // voice report the last name it was given and the assertions below would prove nothing.
    std::vector<pvz::AudioClip> pool;
    pool.reserve(64);
    const auto clipNamed = [&pool](std::string name) -> const pvz::AudioClip& {
        pvz::AudioClip clip;
        clip.name = std::move(name);
        clip.sampleRate = 48000;
        clip.channels = 1;
        clip.samples.assign(4800, 0.1F); // 0.1 s of a constant level; the sound itself is irrelevant
        pool.push_back(std::move(clip));
        return pool.back();
    };

    // Phase 1: a full pool steals the lowest priority, whatever its age.
    {
        pvz::AudioMixer mixer;
        for (int i = 0; i < 15; ++i) {
            const auto& clip = clipNamed("loud" + std::to_string(i));
            check(mixer.playSfx(clip, 1.0F, 5), "the pool must accept voice " + std::to_string(i));
        }
        check(mixer.playSfx(clipNamed("weak"), 1.0F, 1), "the weak voice must start");
        check(mixer.activeSfx() == pvz::AudioMixer::kMaxVoices,
              "the pool should be full at " + std::to_string(pvz::AudioMixer::kMaxVoices) +
                  " voices, got " + std::to_string(mixer.activeSfx()));
        check(mixer.playSfx(clipNamed("strong"), 1.0F, 9), "the strong voice must start by stealing");
        const auto names = mixer.activeSfxNames();
        check(std::find(names.begin(), names.end(), "weak") == names.end(),
              "the lowest-priority voice must be the one stolen when the pool is full");
        check(std::find(names.begin(), names.end(), "strong") != names.end(),
              "the newcomer must be playing after the steal");
        check(mixer.activeSfx() == pvz::AudioMixer::kMaxVoices,
              "stealing must not grow the pool past kMaxVoices");
    }

    // Phase 2: equal priorities steal the earliest start, so a volley keeps its newest pellets.
    {
        pvz::AudioMixer mixer;
        for (int i = 0; i < 16; ++i) {
            const auto& clip = clipNamed("shot" + std::to_string(i));
            check(mixer.playSfx(clip, 1.0F, 5), "the pool must accept shot " + std::to_string(i));
        }
        check(mixer.playSfx(clipNamed("shot_new"), 1.0F, 5),
              "the newcomer must start at equal priority");
        const auto names = mixer.activeSfxNames();
        check(std::find(names.begin(), names.end(), "shot0") == names.end(),
              "at equal priority the earliest voice must be stolen, but shot0 survived");
        check(std::find(names.begin(), names.end(), "shot_new") != names.end(),
              "the newest voice must be playing");
        check(std::find(names.begin(), names.end(), "shot15") != names.end(),
              "the second-newest voice must survive an equal-priority steal");
    }

    // Phase 3: music lives on its own slot and is never the victim.
    {
        pvz::AudioMixer mixer;
        check(mixer.playMusic(clipNamed("theme"), true, 1.0F), "the theme should start");
        for (int i = 0; i < 16; ++i) {
            const auto& clip = clipNamed("fx" + std::to_string(i));
            mixer.playSfx(clip, 1.0F, 0);
        }
        mixer.playSfx(clipNamed("fx_new"), 1.0F, 0);
        check(mixer.musicName() == "theme", "a steal must never touch the music voice");
    }
    std::printf("voices: kMaxVoices=%zu, steal order (lowest priority, then earliest start), "
                "music never stolen\n",
                pvz::AudioMixer::kMaxVoices);
}

/// ⑩ Independent bus volumes: `--music-volume` and `--sfx-volume` scale one bus each, and the
/// other bus must not move when one of them changes. Every measurement restarts the clip, so the
/// two peaks always cover the same 10 ms of source material and the comparison is like for like.
void testBusVolumes(const pvz::AudioCatalog& catalog) {
    const auto decoded = pvz::decodeWavFile(catalog.audioDir / "sfx_shoot.wav");
    pvz::AudioClip clip;
    clip.name = "sfx_shoot";
    clip.sampleRate = decoded.sampleRate;
    clip.channels = decoded.channels;
    clip.samples = decoded.samples;
    std::vector<float> buffer(480 * 2, 0.0F);

    const auto sfxPeak = [&](float bus) {
        pvz::AudioMixer mixer;
        mixer.setSfxVolume(bus);
        mixer.playSfx(clip, 1.0F);
        mixer.mix(buffer.data(), 480);
        return mixer.lastPeak();
    };
    const auto musicPeak = [&](float bus) {
        pvz::AudioMixer mixer;
        mixer.setMusicVolume(bus);
        mixer.playMusic(clip, true, 1.0F);
        mixer.mix(buffer.data(), 480);
        return mixer.lastPeak();
    };

    const float sfxFull = sfxPeak(1.0F);
    const float sfxHalf = sfxPeak(0.5F);
    check(sfxFull > 0.01F, "the sfx bus at 100 should be audible");
    check(std::fabs(sfxHalf * 2.0F - sfxFull) < 1e-3F,
          "sfx volume 50 must halve the effect bus, got " + std::to_string(sfxHalf) + " vs " +
              std::to_string(sfxFull));

    pvz::AudioMixer sfx;
    sfx.setMusicVolume(0.5F); // the music trim must not leak into the effect bus
    sfx.playSfx(clip, 1.0F);
    sfx.mix(buffer.data(), 480);
    check(std::fabs(sfx.lastPeak() - sfxFull) < 1e-3F,
          "the music trim must not change the effect bus");

    const float musicFull = musicPeak(1.0F);
    const float musicHalf = musicPeak(0.5F);
    check(std::fabs(musicHalf * 2.0F - musicFull) < 1e-3F,
          "music volume 50 must halve the music bus, got " + std::to_string(musicHalf) + " vs " +
              std::to_string(musicFull));
    check(musicFull > 0.01F, "the music bus at 100 should be audible");

    pvz::AudioMixer music;
    music.setSfxVolume(0.25F); // the sfx trim must not leak into the music bus
    music.playMusic(clip, true, 1.0F);
    music.mix(buffer.data(), 480);
    check(std::fabs(music.lastPeak() - musicFull) < 1e-3F,
          "the sfx trim must not change the music bus");

    std::printf("bus volumes: sfx %.6f -> %.6f at 50, music %.6f -> %.6f at 50, no cross-talk\n",
                sfxFull, sfxHalf, musicFull, musicHalf);
}

/// ⑦ Volume: the master number and the two bus mutes have to act on the samples, not just on a
/// field. `--volume 0` must produce literal zeros and the same clip at 100 a real peak, which is
/// the ratio the review asks for.
void testVolume(const pvz::AudioCatalog& catalog) {
    const auto decoded = pvz::decodeWavFile(catalog.audioDir / "sfx_shoot.wav");
    pvz::AudioClip clip;
    clip.name = "sfx_shoot";
    clip.sampleRate = decoded.sampleRate;
    clip.channels = decoded.channels;
    clip.samples = decoded.samples;

    auto renderSfx = [&clip](pvz::AudioMixer& mixer) {
        std::vector<float> buffer(2048 * 2, 0.0F);
        check(mixer.playSfx(clip, 1.0F), "playSfx should accept the decoded sfx_shoot");
        mixer.mix(buffer.data(), 2048);
        return peak(buffer);
    };

    pvz::AudioMixer mixer;
    const float loud = renderSfx(mixer); // default volume: 100 %
    mixer.stopAll();
    mixer.setMasterVolume(0.0F);
    const float silent = renderSfx(mixer);

    check(loud > 0.01F, "volume 100 must produce an audible peak");
    check(silent == 0.0F, "--volume 0 must multiply the buffer down to zero");
    std::printf("volume probe: peak(100)=%.6f peak(0)=%.6f ratio=%.3f\n", loud, silent,
                loud > 0.0F ? silent / loud : 0.0F);

    // Half volume is half the peak, not "somewhat quieter".
    mixer.stopAll();
    mixer.setMasterVolume(0.5F);
    const float half = renderSfx(mixer);
    check(std::fabs(half - loud * 0.5F) < 1e-3F, "volume 50 should halve the peak");
    std::printf("volume probe: peak(50)=%.6f (half of %.6f)\n", half, loud);

    // Out-of-range values clamp instead of wrapping around; NaN is ignored.
    mixer.setMasterVolume(5.0F);
    check(mixer.masterVolume() == 1.0F, "volume above 1 must clamp to 1");
    mixer.setMasterVolume(-3.0F);
    check(mixer.masterVolume() == 0.0F, "volume below 0 must clamp to 0");
    mixer.setMasterVolume(0.25F);
    mixer.setMasterVolume(std::nanf(""));
    check(mixer.masterVolume() == 0.25F, "a NaN volume must be ignored, not stored");

    // The two buses are independent: muting music keeps the chime, and vice versa.
    mixer = pvz::AudioMixer{};
    mixer.playMusic(clip, true, 1.0F);
    mixer.setMusicMuted(true);
    std::vector<float> music(1024 * 2, 0.0F);
    mixer.mix(music.data(), 1024);
    check(peak(music) == 0.0F, "--mute-bgm must silence the music voice");
    mixer.setMusicMuted(false);
    std::fill(music.begin(), music.end(), 0.0F);
    mixer.mix(music.data(), 1024);
    check(peak(music) > 0.01F, "unmuting music must bring the track back");

    mixer.setSfxMuted(true);
    mixer.stopMusic(); // isolate the sfx bus: the music voice would otherwise keep the peak nonzero
    check(renderSfx(mixer) == 0.0F, "--mute-sfx must silence the effect voices");
    mixer.setSfxMuted(false);
    check(renderSfx(mixer) > 0.01F, "unmuting sfx must bring the effects back");
    std::printf("volume: --mute-bgm/--mute-sfx silence one bus each\n");
}

/// ⑧ Crossfade: a track change ramps both ends, so no sample ever steps. Constant-level clips make
/// the envelope arithmetic checkable by hand, and the frame count stays exactly what was asked for
/// — a fade must not add or skip a single mixed frame.
void testCrossfade() {
    auto constantClip = [](const char* name, float level) {
        pvz::AudioClip clip;
        clip.name = name;
        clip.sampleRate = pvz::AudioMixer::kSampleRate;
        clip.channels = 1;
        clip.samples.assign(static_cast<std::size_t>(pvz::AudioMixer::kSampleRate) * 2, level);
        return clip;
    };
    const pvz::AudioClip first = constantClip("frontyard_loop", 0.5F);
    const pvz::AudioClip second = constantClip("egypt_loop", 0.25F);

    pvz::AudioMixer mixer;
    check(mixer.playMusic(first, true, 1.0F), "playMusic should accept the first track");
    std::vector<float> setup(64 * 2, 0.0F);
    mixer.mix(setup.data(), 64);
    check(!mixer.musicFading(), "a first start must not fade: nothing is fading out");
    check(std::fabs(mixer.lastPeak() - 0.5F) < 1e-4F, "the first track should play at full level");

    // Switch tracks: the old one fades out while the new one ramps in.
    check(mixer.playMusic(second, true, 1.0F), "playMusic should accept the second track");
    check(mixer.musicFading(), "a track change must start a crossfade");
    check(mixer.musicFadeProgress() == 0.0F, "the crossfade must start at 0");
    check(mixer.musicName() == "egypt_loop", "musicName should report the incoming track");

    const std::size_t fadeFrames = pvz::AudioMixer::kMusicFadeFrames;
    check(fadeFrames >= 24000 && fadeFrames <= 48000,
          "the crossfade constant must stay between 0.5 s and 1.0 s");

    std::vector<float> chunk(256 * 2, 0.0F);
    float previous = 0.5F; // the sample the previous buffer ended on
    float biggestStep = 0.0F;
    std::size_t consumed = 64;
    while (consumed < fadeFrames + 512) {
        std::fill(chunk.begin(), chunk.end(), 0.0F);
        mixer.mix(chunk.data(), 256);
        for (std::size_t frame = 0; frame < 256; ++frame) {
            const float left = chunk[frame * 2];
            // Expected envelope: 0.5*(1-t) + 0.25*t with t the position through the fade.
            const float t = std::min(1.0F, static_cast<float>(consumed + frame) /
                                               static_cast<float>(fadeFrames));
            const float expected = 0.5F * (1.0F - t) + 0.25F * t;
            check(std::fabs(left - expected) < 1e-3F, "the crossfade envelope is not linear");
            biggestStep = std::max(biggestStep, std::fabs(left - previous));
            previous = left;
        }
        consumed += 256;
    }
    check(biggestStep < 1e-3F, "the crossfade must not step between neighbouring samples");
    check(!mixer.musicFading(), "the crossfade should be finished by its own length");
    check(std::fabs(previous - 0.25F) < 1e-3F, "the incoming track should end at its own level");
    check(mixer.mixedFrames() == consumed, "the fade must not change the number of mixed frames");
    std::printf("crossfade: %.3f s (%zu frames), max sample step %.7f, end level %.6f, "
                "mixed frames %zu == requested %zu\n",
                pvz::AudioMixer::kMusicFadeSeconds, fadeFrames, static_cast<double>(biggestStep),
                static_cast<double>(previous), mixer.mixedFrames(), consumed);
}

/// ⑨ The `--volume` / `--mute-bgm` / `--mute-sfx` switches: stripped from the argument list, and a
/// bad number is an error the CLI can print before exiting 1.
void testAudioOptions(const fs::path& assets) {
    {
        std::vector<std::string> args{"PvZ2SHUTTLE", "--play", "content", "--volume", "35"};
        const auto parsed = pvz::parseAudioOptions(args);
        check(parsed.ok, "--volume 35 should parse: " + parsed.error);
        check(parsed.options.volume == 35, "--volume 35 should yield 35");
        check(args.size() == 3 && args[1] == "--play" && args[2] == "content",
              "--volume should be removed from the argument list with its value");
    }
    {
        std::vector<std::string> args{"PvZ2SHUTTLE", "--volume=0", "--mute-bgm", "--mute-sfx",
                                      "--audio-off", "--menu", "content"};
        const auto parsed = pvz::parseAudioOptions(args);
        check(parsed.ok, "--volume=0 should parse: " + parsed.error);
        check(parsed.options.volume == 0, "--volume=0 should yield 0");
        check(parsed.options.muteMusic && parsed.options.muteSfx, "both bus mutes should be seen");
        check(parsed.options.off, "--audio-off should still be recognised");
        check(args.size() == 3 && args[1] == "--menu", "every audio switch should be stripped");
    }
    // The bus trims: absent means -1 (inherit the master), and both spellings must land.
    {
        std::vector<std::string> args{"PvZ2SHUTTLE", "--menu", "content"};
        const auto parsed = pvz::parseAudioOptions(args);
        check(parsed.ok, "a command without trims should parse: " + parsed.error);
        check(parsed.options.musicVolume == -1 && parsed.options.sfxVolume == -1,
              "an absent --music-volume/--sfx-volume must inherit the master, not default to 0");
    }
    {
        std::vector<std::string> args{"PvZ2SHUTTLE", "--volume", "50", "--music-volume", "20",
                                      "--sfx-volume=80", "--play", "content"};
        const auto parsed = pvz::parseAudioOptions(args);
        check(parsed.ok, "the bus trims should parse: " + parsed.error);
        check(parsed.options.volume == 50, "the master should stay 50 next to a music trim");
        check(parsed.options.musicVolume == 20, "--music-volume 20 should yield 20");
        check(parsed.options.sfxVolume == 80, "--sfx-volume=80 should yield 80");
        check(args.size() == 3 && args[1] == "--play",
              "both trims should be stripped from the argument list");
    }
    {
        std::vector<std::string> args{"PvZ2SHUTTLE", "--menu", "content", "--music-volume", "200"};
        const auto parsed = pvz::parseAudioOptions(args);
        check(!parsed.ok, "--music-volume 200 must be rejected");
        check(parsed.error == "--music-volume must be between 0 and 100, got 200",
              "--music-volume 200 should name its own flag (got: " + parsed.error + ")");
        check(args.size() == 5, "a rejected --music-volume must leave the arguments untouched");
    }
    {
        std::vector<std::string> args{"PvZ2SHUTTLE", "--menu", "content", "--sfx-volume=x"};
        const auto parsed = pvz::parseAudioOptions(args);
        check(!parsed.ok && parsed.error == "--sfx-volume expects a number from 0 to 100, got \"x\"",
              "a bad --sfx-volume should name its own flag (got: " + parsed.error + ")");
    }

    // Bad values: a readable message and ok == false, which the CLI turns into exit 1.
    const std::pair<std::string, std::string> badValues[] = {
        {"101", "--volume must be between 0 and 100, got 101"},
        {"-5", "--volume must be between 0 and 100, got -5"},
        {"abc", "--volume expects a number from 0 to 100, got \"abc\""},
        {"40x", "--volume expects a number from 0 to 100, got \"40x\""},
    };
    for (const auto& [value, expected] : badValues) {
        std::vector<std::string> args{"PvZ2SHUTTLE", "--volume", value, "--menu", "content"};
        const auto parsed = pvz::parseAudioOptions(args);
        check(!parsed.ok, "--volume " + value + " must be rejected");
        check(parsed.error == expected, "--volume " + value + " should say: " + expected +
                                            " (got: " + parsed.error + ")");
        check(args.size() == 5, "a rejected --volume must leave the arguments untouched");
    }
    {
        std::vector<std::string> args{"PvZ2SHUTTLE", "--menu", "content", "--volume"};
        const auto parsed = pvz::parseAudioOptions(args);
        check(!parsed.ok && parsed.error == "--volume expects a number from 0 to 100, got nothing",
              "a --volume without a value should say it got nothing");
    }
    {
        // The argv this program really carries: file system paths, one of them non-ASCII (this
        // repo's asset directory sits under a directory whose name is Chinese). The overload must
        // strip the switches and hand every path back byte for byte.
        const fs::path nonAscii = fs::path(L"\u65e5\u5fd7") / L"assets";
        std::vector<fs::path> args{fs::path("PvZ2SHUTTLE"), fs::path("--menu"), fs::path("content"),
                                   nonAscii, fs::path("--volume"), fs::path("70"),
                                   fs::path("--mute-bgm")};
        const auto parsed = pvz::parseAudioOptions(args);
        check(parsed.ok, "--volume 70 should parse from a path argv: " + parsed.error);
        check(parsed.options.volume == 70 && parsed.options.muteMusic,
              "the path overload should see --volume 70 and --mute-bgm");
        check(args.size() == 4 && args[3] == nonAscii,
              "the path overload must keep the non-ASCII path intact");
        std::printf("options: path argv keeps %s\n", pvz::audioPathUtf8(args[3]).c_str());
    }
    // Applying the switches reaches the runtime the views attach later, including the silent ones.
    pvz::resetAudioForTest();
    pvz::AudioOptions options;
    options.volume = 30;
    options.muteSfx = true;
    options.musicVolume = 40;
    pvz::applyAudioOptions(options);
    const pvz::AudioRuntime* runtime = pvz::attachAudio(assets, /*headless=*/true);
    check(runtime != nullptr, "attachAudio should hand back a runtime");
    check(runtime->volume() == 30, "the attached runtime should use --volume 30");
    check(runtime->musicVolume() == 40, "the attached runtime should use --music-volume 40");
    check(runtime->sfxVolume() == 100,
          "an absent --sfx-volume must inherit the master default, not the music trim");
    check(runtime->sfxMuted(), "the attached runtime should keep --mute-sfx");
    pvz::resetAudioForTest();
    const pvz::AudioRuntime* fresh = pvz::attachAudio(assets, /*headless=*/true);
    check(fresh != nullptr && fresh->volume() == 100, "resetAudioForTest should restore volume 100");
    check(fresh->musicVolume() == 100 && fresh->sfxVolume() == 100,
          "resetAudioForTest should restore both bus trims to 100");
    pvz::resetAudioForTest();
    std::printf("options: --volume/--mute-bgm/--mute-sfx/--music-volume/--sfx-volume parse, reject "
                "bad values, reach the runtime\n");
}

/// ⑥ The audit payload: exactly the eight keys the CLI promises.
void testAudit(const pvz::AudioCatalog& catalog, const pvz::EventMap& events,
               const fs::path& packDir) {
    pvz::PackCrossCheck packs;
    if (!packDir.empty())
        packs = pvz::crossCheckPacks(pvz::locateAudioPacks(packDir), events);
    const auto audit = pvz::auditAudio(catalog, /*deviceAvailable=*/false, packs);
    const auto json = audit.json();
    check(json.size() == 7, "the audit JSON must hold exactly the 7 documented keys, got " +
                                std::to_string(json.size()));
    for (const char* key : {"sounds", "bgm", "sfx", "decoded", "seconds", "missing",
                            "deviceAvailable"})
        check(json.contains(key), std::string("audit JSON is missing `") + key + "`");
    check(json["sounds"] == 65 && json["bgm"] == 26 && json["sfx"] == 18,
          "audit counts must match the catalog");
    check(json["deviceAvailable"] == false, "the audit must report the device it was given");
    check(audit.exitCode() == 0, "an intact asset tree must exit 0");
    check(audit.missing.empty(), "the shipped assets have no missing files");
    // 65 sounds minus the five mp3 files there is no decoder for.
    // 65 files, all decodable since T49 vendored minimp3 for the five mp3s.
    check(audit.decoded == 65, "expected 65 decoded files, got " + std::to_string(audit.decoded));
    check(audit.seconds > 300.0, "the decoded audio should add up to more than 300 s");
    std::printf("audit: %s\n", json.dump().c_str());

    if (!packDir.empty()) {
        check(packs.files.size() == 2, "both property sheets should be read, got " +
                                           std::to_string(packs.files.size()));
        check(packs.values > 500, "expected hundreds of audio values, got " +
                                      std::to_string(packs.values));
        check(packs.emptyValues > 0, "ProjectileLaunchSound has 86 empty values; none were counted");
        check(packs.aliasValues > 0, "no pack value resolved through a token alias");
        check(!packs.unmatched.empty(), "the unmatched list must not be empty");
        bool throwHit = false;
        for (const auto& hit : packs.hits) {
            if (hit.key != "ProjectileLaunchSound" || hit.value != "Play_Throw") continue;
            throwHit = true;
            check(hit.sound == "sfx_shoot", "Play_Throw should resolve to sfx_shoot, got `" +
                                                hit.sound + "`");
            check(hit.count == 90, "Play_Throw occurs 90 times, counted " +
                                       std::to_string(hit.count));
        }
        check(throwHit, "ProjectileLaunchSound=Play_Throw was not seen at all");
        // The empty string is a real pack value: it must be named, not dropped.
        check(std::find(packs.unmatched.begin(), packs.unmatched.end(),
                        "ProjectileLaunchSound=<empty>") != packs.unmatched.end(),
              "the 86 empty ProjectileLaunchSound values must appear as `<empty>`");
        std::printf("%s\n", packs.text().c_str());
    } else {
        std::printf("audit: pack cross-check skipped (no pack directory argument)\n");
    }
}

/// ⑦ Errors carry the documented `audio catalog: <path>: <what>` prefix.
void testErrors(const fs::path& assets, const fs::path& temp) {
    const fs::path bare = temp / "audio-missing";
    std::error_code ec;
    fs::remove_all(bare, ec);
    fs::create_directories(bare / "audio", ec);
    const std::string missingReport = expectThrow([&] { pvz::AudioCatalog::load(bare); },
                                                  "load() without audio_report.json");
    check(missingReport.find("audio catalog: ") == 0,
          "the error must start with `audio catalog: `, got: " + missingReport);
    check(missingReport.find("audio_report.json") != std::string::npos,
          "the error must name the missing file, got: " + missingReport);

    const fs::path emptyRoot = temp / "audio-empty-root";
    fs::remove_all(emptyRoot, ec);
    fs::create_directories(emptyRoot, ec);
    const std::string noDir = expectThrow([&] { pvz::AudioCatalog::load(emptyRoot); },
                                          "load() without an audio directory");
    check(noDir.find("audio catalog: ") == 0 && noDir.find("no such audio directory") != std::string::npos,
          "unexpected missing-directory error: " + noDir);

    // A manifest that points at a file which is not there keeps loading, but counts it as missing
    // so `--audio-audit` can exit 1 instead of pretending the bank is complete.
    const fs::path ghost = temp / "audio-ghost";
    fs::remove_all(ghost, ec);
    fs::create_directories(ghost / "audio", ec);
    const fs::path ghostReport = ghost / "audio" / "audio_report.json";
    {
        // fs::path + ofstream, not fopen(utf8): the gate runs under a non-ASCII parent directory
        // and narrow fopen() fails there, which made this fixture unable to run anywhere but %TEMP%.
        std::ofstream file(ghostReport, std::ios::binary);
        check(file.good(), "cannot write the ghost manifest: " + describe(ghostReport));
        file << R"([{"name":"ghost","file":"ghost.wav","uuid":"x","bytes":0,"fmt":"wav"}])";
        file.close();
    }
    // The OBB timing table is required too, so the fixture carries an empty one.
    {
        fs::create_directories(ghost / "audio" / "obb", ec);
        const fs::path ghostDurations = ghost / "audio" / "obb" / "durations.json";
        std::ofstream file(ghostDurations, std::ios::binary);
        check(file.good(), "cannot write the ghost durations table: " + describe(ghostDurations));
        file << "{}";
        file.close();
    }
    const auto ghostCatalog = pvz::AudioCatalog::load(ghost);
    check(ghostCatalog.missingFiles == 1,
          "the ghost entry should be counted as one missing file, got " +
              std::to_string(ghostCatalog.missingFiles));
    const auto ghostAudit = pvz::auditAudio(ghostCatalog, false);
    check(ghostAudit.exitCode() == 1, "an audit with a missing file must exit 1");
    check(ghostAudit.json()["missing"].size() == 1, "missing[] should name the ghost entry");
    std::printf("errors: %s\n", missingReport.c_str());
    std::printf("errors: missing files make --audio-audit exit 1\n");

    // The shipped tree is the control: it must not be affected by the fixtures above.
    check(pvz::AudioCatalog::load(assets).missingFiles == 0,
          "loading the fixtures must not disturb the shipped catalog");
}

} // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: audio_test <assets> <temp> [<obb_packages>]\n");
        return 2;
    }
    const fs::path assets = argv[1];
    const fs::path temp = argv[2];
    const fs::path packDir = argc >= 4 ? fs::path(argv[3]) : fs::path{};
    try {
        const auto catalog = pvz::AudioCatalog::load(assets);
        const pvz::EventMap events;
        testCatalog(assets);
        testEventMap(catalog);
        testWav(catalog);
        testOgg(catalog);
        testMp3(catalog);
        testMixer(catalog);
        testInterpolation();
        testVoiceStealing();
        testBusVolumes(catalog);
        testVolume(catalog);
        testCrossfade();
        testAudioOptions(assets);
        testAudit(catalog, events, packDir);
        testErrors(assets, temp);
        std::printf("audio tests passed\n");
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "audio test failed: %s\n", error.what());
        return 1;
    }
}
