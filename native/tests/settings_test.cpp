// Settings model: the three volume buses, the mute switch, and the `audio` block in the save.
//
// Everything here runs without SDL and without a sound card. The screen (`settings_view.cpp`) is
// deliberately not linked: what needs proving is the rules - clamping, key handling, the exact
// JSON shape, and that an old save without an `audio` block still loads - and the mixer level that
// "the volume really multiplies" belongs to `audio_test`'s volume case. This file adds the parts
// only the settings screen has: the row cursor, persistence, and the save round trip.
//
// Usage: settings_test <assets> <temp>

#include "audio/audio_mixer.hpp"
#include "audio/audio_runtime.hpp"
#include "audio/audio_settings.hpp"
#include "progress.hpp"

#include <cstdio>
#include <filesystem>
#include <stdexcept>
#include <string>

namespace fs = std::filesystem;

namespace {

void check(bool condition, const std::string& what) {
    if (!condition) throw std::runtime_error(what);
}

std::string text(const pvz::AudioSettings& audio) {
    return "{" + std::to_string(audio.master) + "," + std::to_string(audio.music) + "," +
           std::to_string(audio.sfx) + (audio.muted ? ",muted}" : "}");
}

/// A 0.25-level square wave: a constant clip whose peak is easy to predict after any gain.
pvz::AudioClip tone(const std::string& name, float level) {
    pvz::AudioClip clip;
    clip.name = name;
    clip.sampleRate = pvz::AudioMixer::kSampleRate;
    clip.channels = 1;
    clip.samples.assign(4096, level);
    return clip;
}

/// 1. Defaults and the exact JSON shape the screen prints.
void testDefaults() {
    const pvz::AudioSettings defaults;
    check(defaults.master == 100 && defaults.music == 100 && defaults.sfx == 100 && !defaults.muted,
          "a fresh install must start at 100/100/100 and unmuted, got " + text(defaults));
    check(defaults == pvz::AudioSettings{}, "two default values must compare equal");
    check(defaults.isDefault(), "the default value must report isDefault()");

    const auto json = pvz::audioSettingsJson(defaults);
    check(json.is_object(), "audio settings must serialise as an object");
    check(json.size() == 4, "the audio block must hold exactly four keys, got " +
                                std::to_string(json.size()));
    for (const char* key : {"master", "music", "sfx", "muted"}) {
        check(json.contains(key), std::string("the audio block is missing `") + key + "`");
    }
    // nlohmann::json keeps object keys in a std::map, so the line is alphabetical:
    // master, music, muted, sfx. The caller reads keys, never positions, and this literal pins the
    // exact bytes so a field rename cannot slip through unnoticed.
    check(pvz::settingsJsonLine(defaults) == R"({"master":100,"music":100,"muted":false,"sfx":100})",
          "the settings line must be the documented shape, got " + pvz::settingsJsonLine(defaults));
    std::printf("defaults: %s\n", pvz::settingsJsonLine(defaults).c_str());
}

/// 2. Clamp: a hand-edited save (or a future slider) can never hand the mixer a gain above 1.
void testClamp() {
    pvz::AudioSettings loud;
    loud.master = 900;
    loud.music = -40;
    loud.sfx = 55;
    const auto clean = pvz::clampAudioSettings(loud);
    check(clean.master == 100 && clean.music == 0 && clean.sfx == 55,
          "clamp must pin 900 to 100, -40 to 0 and keep 55, got " + text(clean));

    const auto fromJson = pvz::readAudioSettings(
        pvz::Json{{"master", 900}, {"music", -40}, {"sfx", 55}, {"muted", true}});
    check(fromJson.master == 100 && fromJson.music == 0 && fromJson.sfx == 55 && fromJson.muted,
          "a hand-written block must be clamped on read, got " + text(fromJson));
    std::printf("clamp: 900/-40/55 -> %s\n", text(fromJson).c_str());
}

/// 3. Keys: left/right move 5 per press inside the highlighted row, up/down wrap, M toggles mute
/// without touching the three percentages, Esc closes.
void testKeys() {
    pvz::SettingsState state;
    auto step = pvz::applySettingsKey(state, pvz::SettingsKey::right);
    check(!step.changed && step.state.audio.master == 100,
          "right on a 100% master must stay at 100 and report no change, got " +
              text(step.state.audio));

    state.audio.master = 50;
    step = pvz::applySettingsKey(state, pvz::SettingsKey::right);
    check(step.changed && step.state.audio.master == 55, "right must add 5, got " +
                                                             std::to_string(step.state.audio.master));
    step = pvz::applySettingsKey(step.state, pvz::SettingsKey::left);
    check(step.changed && step.state.audio.master == 50, "left must subtract 5, got " +
                                                             std::to_string(step.state.audio.master));

    // Down walks master -> music -> sfx -> master, and the value edited follows the cursor.
    pvz::SettingsState walk;
    walk.audio = {70, 60, 50, false};
    walk = pvz::applySettingsKey(walk, pvz::SettingsKey::down).state;
    check(walk.row == 1, "down must move to the music row, got " + std::to_string(walk.row));
    walk = pvz::applySettingsKey(walk, pvz::SettingsKey::right).state;
    check(walk.audio.music == 65 && walk.audio.master == 70,
          "the music row must be the one edited, got " + text(walk.audio));
    walk = pvz::applySettingsKey(walk, pvz::SettingsKey::down).state;
    walk = pvz::applySettingsKey(walk, pvz::SettingsKey::down).state;
    check(walk.row == 0, "down must wrap from the last row back to master, got " +
                             std::to_string(walk.row));
    walk = pvz::applySettingsKey(walk, pvz::SettingsKey::up).state;
    check(walk.row == 2, "up must wrap from master to the last row, got " + std::to_string(walk.row));

    const auto muted = pvz::applySettingsKey(walk, pvz::SettingsKey::mute);
    check(muted.changed && muted.state.audio.muted, "M must set the mute switch");
    check(muted.state.audio.music == walk.audio.music, "mute must not touch the percentages");
    const auto again = pvz::applySettingsKey(muted.state, pvz::SettingsKey::mute);
    check(!again.state.audio.muted, "M must toggle back");

    const auto back = pvz::applySettingsKey(walk, pvz::SettingsKey::back);
    check(back.closed && !back.changed, "Esc must close without claiming a value change");
    std::printf("keys: 100 +5 stays 100, 50 +5 = 55, rows wrap, mute keeps 70/60/50\n");
}

/// 4. "Immediate": the runtime keeps the numbers even with no device, and the mixer honours them
/// when there is one to render.
void testImmediate() {
    pvz::AudioMixer mixer;
    const pvz::AudioClip clip = tone("tone", 0.25F);
    check(mixer.playSfx(clip), "the mixer must accept a voice");

    mixer.setMasterVolume(1.0F);
    mixer.mix(nullptr, 0);  // no-op render, keeps the peak from the last real mix
    std::vector<float> buffer(256 * 2, 0.0F);
    mixer.mix(buffer.data(), 256);
    const float loud = mixer.lastPeak();
    check(loud > 0.0F, "a 0.25 clip at full volume must produce a peak, got " +
                           std::to_string(loud));

    mixer.setMasterVolume(0.5F);
    std::fill(buffer.begin(), buffer.end(), 0.0F);
    mixer.mix(buffer.data(), 256);
    const float half = mixer.lastPeak();
    check(std::abs(half - loud * 0.5F) < 1e-3F,
          "halving the master must halve the peak, got " + std::to_string(half) + " vs " +
              std::to_string(loud * 0.5F));

    mixer.setMasterVolume(0.0F);
    std::fill(buffer.begin(), buffer.end(), 0.0F);
    mixer.mix(buffer.data(), 256);
    check(mixer.lastPeak() == 0.0F, "a zero master must silence the mix, got " +
                                        std::to_string(mixer.lastPeak()));

    // The runtime half: percentages are remembered (and clamped) even when no backend exists.
    pvz::AudioCatalog catalog;
    pvz::AudioRuntime runtime(catalog, pvz::AudioMode::muted);
    pvz::applyAudioSettings(runtime, pvz::AudioSettings{35, 40, 45, true});
    check(runtime.volume() == 35 && runtime.musicVolume() == 40 && runtime.sfxVolume() == 45,
          "the runtime must keep the three buses, got " + std::to_string(runtime.volume()) + "/" +
              std::to_string(runtime.musicVolume()) + "/" + std::to_string(runtime.sfxVolume()));
    const auto readBack = pvz::audioSettingsOf(runtime, true);
    check(readBack == (pvz::AudioSettings{35, 40, 45, true}),
          "reading the runtime back must match what was applied, got " + text(readBack));
    std::printf("immediate: peak %0.6f -> %0.6f at 50%% -> %0.6f at 0%%, runtime keeps 35/40/45\n",
                static_cast<double>(loud), static_cast<double>(half),
                static_cast<double>(mixer.lastPeak()));
}

/// 5. Mute through the mixer: the switch alone must silence everything, percentages untouched.
void testMute() {
    pvz::AudioMixer mixer;
    const pvz::AudioClip clip = tone("tone", 0.25F);
    check(mixer.playSfx(clip, 1.0F), "the mixer must accept a voice");
    std::vector<float> buffer(256 * 2, 0.0F);
    mixer.mix(buffer.data(), 256);
    check(mixer.lastPeak() > 0.0F, "an unmuted mix must produce sound");

    mixer.setMuted(true);
    std::fill(buffer.begin(), buffer.end(), 0.0F);
    mixer.mix(buffer.data(), 256);
    check(mixer.lastPeak() == 0.0F, "a muted mix must be silent, got " +
                                        std::to_string(mixer.lastPeak()));
    check(mixer.masterVolume() == 1.0F, "mute must not overwrite the stored master volume");

    mixer.setMuted(false);
    std::fill(buffer.begin(), buffer.end(), 0.0F);
    mixer.mix(buffer.data(), 256);
    check(mixer.lastPeak() > 0.0F, "unmuting must bring the sound back");
    std::printf("mute: peak 0.25 -> 0.000000 -> 0.25, master kept at 1\n");
}

/// 6. Save round trip: write through `saveProgress`, read through `loadProgress`, compare.
void testPersistence(const fs::path& temp) {
    const fs::path file = temp / "settings_roundtrip.json";
    std::error_code ignored;
    fs::remove(file, ignored);

    pvz::Progress progress;
    progress.version = 2;
    progress.updated = 1700000000;
    progress.keys = 3;
    progress.coins = 250;
    progress.audio = pvz::AudioSettings{45, 30, 90, true};
    pvz::saveProgress(file, progress, 1700000001);

    const pvz::Progress loaded = pvz::loadProgress(file);
    check(loaded.audio == progress.audio,
          "the audio block must survive a save/load round trip, got " + text(loaded.audio));
    check(loaded.coins == 250 && loaded.keys == 3,
          "the rest of the save must survive too, got coins " + std::to_string(loaded.coins));

    // The block is only written when it differs from the defaults, so an untouched save keeps its
    // old bytes and the whole-file comparisons elsewhere stay valid.
    pvz::Progress plain;
    plain.coins = 7;
    const auto textBlock = pvz::progressToJson(plain);
    check(!textBlock.contains("audio"),
          "a save that never touched the settings must not grow an `audio` block");

    const std::string written = textBlock.dump();
    check(written.find("\"audio\"") == std::string::npos,
          "the serialised default save must not mention `audio`");
    std::printf("persistence: 45/30/90 muted round trips through saveProgress/loadProgress\n");
}

/// 7. Old saves: no `audio` block at all, or a partial one, must load with defaults.
void testOldSave() {
    const pvz::Json old = pvz::Json::parse(R"({
        "version": 1, "updated": 1600000000, "keys": 2, "coins": 40,
        "purchases": [], "seeds": [], "levels": {}
    })");
    const pvz::Progress loaded = pvz::parseProgress(old, "old-save");
    check(loaded.audio == pvz::AudioSettings{},
          "an old save must load the default audio settings, got " + text(loaded.audio));
    check(loaded.coins == 40, "the old save's coins must still load");

    // Partial block: only `master` remembered. The other two keep their defaults, one member at a
    // time, instead of the whole block failing.
    const pvz::Json partial = pvz::Json::parse(R"({"audio": {"master": 20}})");
    const pvz::Progress half = pvz::parseProgress(partial, "partial-save");
    check(half.audio.master == 20 && half.audio.music == 100 && half.audio.sfx == 100 &&
              !half.audio.muted,
          "a partial audio block must fill the missing members with defaults, got " +
              text(half.audio));

    // Wrong type: an array where an object belongs. Ignored, not fatal - losing every star over a
    // malformed preference would be the worse failure.
    const pvz::Json broken = pvz::Json::parse(R"({"audio": [1, 2, 3], "coins": 9})");
    const pvz::Progress survived = pvz::parseProgress(broken, "broken-save");
    check(survived.audio == pvz::AudioSettings{} && survived.coins == 9,
          "a malformed audio block must fall back to defaults without losing the save");
    std::printf("old saves: no block -> 100/100/100, partial -> 20/100/100, array -> defaults\n");
}

/// 8. The JSON line is one line and parses back to the same four values (the CLI contract).
void testJsonLine() {
    const pvz::AudioSettings audio{5, 50, 95, true};
    const std::string line = pvz::settingsJsonLine(audio);
    check(line.find('\n') == std::string::npos, "the settings line must not contain a newline");
    const auto parsed = pvz::Json::parse(line);
    check(parsed.size() == 4 && parsed["master"] == 5 && parsed["music"] == 50 &&
              parsed["sfx"] == 95 && parsed["muted"] == true,
          "the printed line must parse back to the same four values, got " + line);
    std::printf("json line: %s\n", line.c_str());
}

}  // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc < 3) {
        std::fprintf(stderr, "usage: settings_test <assets> <temp>\n");
        return 2;
    }
    const fs::path assets = argv[1];
    const fs::path temp = argv[2];
    try {
        std::error_code ignored;
        fs::create_directories(temp, ignored);
        (void)assets;  // the model needs no artwork; kept in the signature so the suite is uniform

        testDefaults();
        testClamp();
        testKeys();
        testImmediate();
        testMute();
        testPersistence(temp);
        testOldSave();
        testJsonLine();

        std::printf("settings tests passed\n");
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "settings test failed: %s\n", error.what());
        return 1;
    }
}
