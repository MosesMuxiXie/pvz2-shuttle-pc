#include "audio/audio_runtime.hpp"

#include <algorithm>
#include <charconv>
#include <cstdint>
#include <filesystem>
#include <string_view>
#include <system_error>

namespace pvz {
namespace {

std::uint64_t tickOf(const nlohmann::json& entry) {
    const auto found = entry.find("tick");
    if (found == entry.end()) return 0;
    if (found->is_number_unsigned()) return found->get<std::uint64_t>();
    if (found->is_number_integer()) {
        const auto value = found->get<std::int64_t>();
        return value > 0 ? static_cast<std::uint64_t>(value) : 0;
    }
    return 0;
}

void pushUnique(std::vector<std::string>& list, const std::string& value) {
    if (list.size() >= 64) return;
    if (std::find(list.begin(), list.end(), value) == list.end()) list.push_back(value);
}

} // namespace

AudioRuntime::AudioRuntime(const AudioCatalog& catalog, AudioMode mode)
    : mode_(mode), catalog_(catalog), events_() {
    if (mode_ == AudioMode::live) backend_ = AudioBackend::create(catalog_, events_);
}

AudioRuntime::~AudioRuntime() = default;

std::unique_ptr<AudioRuntime> AudioRuntime::open(const std::filesystem::path& assetRoot, AudioMode mode,
                                                 std::string* error) {
    AudioCatalog catalog;
    try {
        catalog = AudioCatalog::load(assetRoot);
    } catch (const std::exception& failure) {
        if (error != nullptr) *error = failure.what();
        return nullptr;
    }
    auto runtime = std::make_unique<AudioRuntime>(catalog, mode);
    runtime->assetRoot_ = assetRoot;
    if (error != nullptr) error->clear();
    return runtime;
}

bool AudioRuntime::enabled() const {
    return mode_ == AudioMode::live && backend_ != nullptr && backend_->available();
}

bool AudioRuntime::deviceAvailable() const { return backend_ != nullptr && backend_->available(); }

std::string AudioRuntime::status() const {
    std::string text;
    switch (mode_) {
        case AudioMode::headless: text = "headless (snapshot)"; break;
        case AudioMode::muted: text = "muted (--audio-off)"; break;
        case AudioMode::live: text = "live (" + audioBackendBuildNote() + ")"; break;
    }
    if (mode_ == AudioMode::live && backend_ != nullptr && !backend_->available())
        text += " - silent: " + backend_->note();
    return text;
}

std::string AudioRuntime::note() const {
    if (backend_ == nullptr) return mode_ == AudioMode::headless ? "headless run: no device opened"
                                                                : "muted run: no device opened";
    return backend_->note();
}

void AudioRuntime::remember(const std::string& sound) { pushUnique(playedLog_, sound); }

void AudioRuntime::start(const std::string& sound, float gain, int priority) {
    remember(sound);
    lastSfxPriority_ = priority;
    if (!enabled()) return;
    ++counters_.playSfxCalls;
    (void)backend_->playSfx(sound, gain, priority);
}

void AudioRuntime::playMusicForWorld(const std::string& world, bool intro) {
    if (catalog_.sounds.empty()) return;
    const MusicSelection selection = selectMusic(catalog_, events_, world, intro);
    if (selection.track.empty()) return;
    musicName_ = selection.track;
    statusNote_ = selection.note;
    if (!enabled()) return;
    ++counters_.musicStarts;
    (void)backend_->playMusic(selection.track, true, 0.55F);
}

void AudioRuntime::playMenuMusic() {
    if (catalog_.sounds.empty()) return;
    musicName_ = "menu";
    if (!enabled()) return;
    ++counters_.musicStarts;
    (void)backend_->playMusic("menu", true, 0.5F);
}

void AudioRuntime::playClick() {
    ++counters_.sfxRequests;
    // Level 3: a cursor move is the one sound the player asked for directly, so a full mix must
    // never eat it.
    start("sfx_click", 0.7F, 3);
}

void AudioRuntime::stopMusic() {
    if (backend_ != nullptr) backend_->stopMusic();
    musicName_.clear();
}

void AudioRuntime::stopAll() {
    if (backend_ != nullptr) backend_->stopAll();
    musicName_.clear();
}

void AudioRuntime::setMasterVolume(float volume) {
    if (backend_ != nullptr) backend_->setMasterVolume(volume);
}

void AudioRuntime::setMuted(bool muted) {
    if (backend_ != nullptr) backend_->setMuted(muted);
}

float AudioRuntime::masterVolume() const { return backend_ != nullptr ? backend_->masterVolume() : 1.0F; }

bool AudioRuntime::muted() const { return backend_ != nullptr ? backend_->muted() : mode_ != AudioMode::live; }

void AudioRuntime::setVolume(int percent) {
    volume_ = std::clamp(percent, 0, 100);
    if (backend_ != nullptr)
        backend_->setMasterVolume(static_cast<float>(volume_) / 100.0F);
}

void AudioRuntime::setMusicVolume(int percent) {
    musicVolume_ = std::clamp(percent, 0, 100);
    if (backend_ != nullptr) backend_->setMusicVolume(static_cast<float>(musicVolume_) / 100.0F);
}

void AudioRuntime::setSfxVolume(int percent) {
    sfxVolume_ = std::clamp(percent, 0, 100);
    if (backend_ != nullptr) backend_->setSfxVolume(static_cast<float>(sfxVolume_) / 100.0F);
}

void AudioRuntime::setMusicMuted(bool muted) {
    musicMuted_ = muted;
    if (backend_ != nullptr) backend_->setMusicMuted(muted);
}

void AudioRuntime::setSfxMuted(bool muted) {
    sfxMuted_ = muted;
    if (backend_ != nullptr) backend_->setSfxMuted(muted);
}

float AudioRuntime::lastPeak() const { return backend_ != nullptr ? backend_->lastPeak() : 0.0F; }

bool AudioRuntime::musicFading() const { return backend_ != nullptr && backend_->musicFading(); }

float AudioRuntime::musicFadeProgress() const {
    return backend_ != nullptr ? backend_->musicFadeProgress() : 1.0F;
}

std::size_t AudioRuntime::consume(const nlohmann::json& events, std::size_t cursor) {
    if (!events.is_array() || cursor >= events.size()) return events.is_array() ? events.size() : cursor;
    for (std::size_t index = cursor; index < events.size(); ++index) {
        const nlohmann::json& entry = events[index];
        if (!entry.is_object()) continue;
        const auto type = entry.find("type");
        if (type == entry.end() || !type->is_string()) continue;
        const std::uint64_t tick = tickOf(entry);
        // Ticks arrive in order, so a single open tick is enough to remember "already played".
        if (!tickOpen_ || tick != lastTick_) {
            lastTick_ = tick;
            tickOpen_ = true;
            tickTypes_.clear();
        }
        ++counters_.eventsSeen;
        const std::string name = type->get<std::string>();
        const std::string sound = events_.soundForEngineEvent(name);
        if (sound.empty()) {
            ++counters_.eventsUnmapped;
            pushUnique(silentEvents_, name);
            continue;
        }
        // A peashooter fires eight pellets in one tick; the mixer has eight voices for the whole
        // screen, so the horn, the sun and the chomp all need theirs. First of a type wins.
        if (tickTypes_.count(name) != 0) {
            ++counters_.eventsDeduped;
            continue;
        }
        tickTypes_.insert(name);
        ++counters_.eventsMapped;
        ++counters_.sfxRequests;
        start(sound, 1.0F, events_.priorityForEngineEvent(name));
    }
    return events.size();
}

void AudioRuntime::pump() {
    ++counters_.pumpCalls;
    if (enabled()) backend_->pump();
}

// ---------------------------------------------------------------------------------------------
// Process-wide runtime used by the views.
// ---------------------------------------------------------------------------------------------
namespace {
bool gAudioOff = false;
std::unique_ptr<AudioRuntime> gRuntime;
/// Remembered so a runtime attached later (the views attach once each) hears the same mix, and so
/// `--volume 30 --menu` and `--menu --volume 30` cannot disagree.
AudioOptions gOptions;

void pushOptions(AudioRuntime* runtime) {
    if (runtime == nullptr) return;
    runtime->setVolume(gOptions.volume);
    // A negative trim means the switch was not given: the bus stays at 100 and inherits the master.
    runtime->setMusicVolume(gOptions.musicVolume >= 0 ? gOptions.musicVolume : 100);
    runtime->setSfxVolume(gOptions.sfxVolume >= 0 ? gOptions.sfxVolume : 100);
    runtime->setMusicMuted(gOptions.muteMusic);
    runtime->setSfxMuted(gOptions.muteSfx);
}
} // namespace

void setAudioOff(bool off) {
    gAudioOff = off;
    gOptions.off = off;
}
bool audioOff() { return gAudioOff; }

AudioRuntime* attachAudio(const std::filesystem::path& assetRoot, bool headless) {
    const AudioMode mode = headless ? AudioMode::headless : (gAudioOff ? AudioMode::muted : AudioMode::live);
    if (gRuntime != nullptr && gRuntime->mode() == mode && gRuntime->assetRoot() == assetRoot) {
        pushOptions(gRuntime.get());
        return gRuntime.get();
    }
    gRuntime = AudioRuntime::open(assetRoot, mode, nullptr);
    pushOptions(gRuntime.get());
    return gRuntime.get();
}

void detachAudio() { gRuntime.reset(); }

AudioRuntime* ambientAudio() { return gRuntime.get(); }

void pumpAudio() {
    if (gRuntime != nullptr) gRuntime->pump();
}

void playAudioMusicForWorld(const std::string& world) {
    if (gRuntime != nullptr) gRuntime->playMusicForWorld(world);
}

void playAudioMenuMusic() {
    if (gRuntime != nullptr) gRuntime->playMenuMusic();
}

void playAudioClick() {
    if (gRuntime != nullptr) gRuntime->playClick();
}

std::size_t consumeAudioEvents(const nlohmann::json& events, std::size_t cursor) {
    return gRuntime != nullptr ? gRuntime->consume(events, cursor) : cursor;
}

void resetAudioForTest() {
    gRuntime.reset();
    gAudioOff = false;
    gOptions = AudioOptions{};
}

// ---------------------------------------------------------------------------------------------
// Volume switches (`--volume`, `--mute-bgm`, `--mute-sfx`).
// ---------------------------------------------------------------------------------------------
namespace {

/// One strict 0..100 parse shared by `--volume`, `--music-volume` and `--sfx-volume`, so all three
/// switches reject `40x`-style input with the same wording shape and name themselves in the error.
bool parsePercentValue(const std::string& flag, const std::string& raw, int& value,
                       std::string& error) {
    if (raw.empty()) {
        error = flag + " expects a number from 0 to 100, got an empty value";
        return false;
    }
    int parsedValue = 0;
    const char* first = raw.data();
    const char* last = raw.data() + raw.size();
    const auto result = std::from_chars(first, last, parsedValue);
    if (result.ec != std::errc{} || result.ptr != last) {
        error = flag + " expects a number from 0 to 100, got \"" + raw + "\"";
        return false;
    }
    if (parsedValue < 0 || parsedValue > 100) {
        error = flag + " must be between 0 and 100, got " + raw;
        return false;
    }
    value = parsedValue;
    return true;
}

bool parseVolumeValue(const std::string& raw, int& value, std::string& error) {
    return parsePercentValue("--volume", raw, value, error);
}

/// The UTF-8 bytes a `std::string` argv holds, turned into a path without going through the ANSI
/// code page (the asset directory in this repo sits under a non-ASCII parent).
std::filesystem::path pathFromUtf8(std::string_view text) {
    std::u8string utf8;
    utf8.reserve(text.size());
    for (const char ch : text) utf8.push_back(static_cast<char8_t>(ch));
    return std::filesystem::path(utf8);
}

} // namespace

AudioOptionParse parseAudioOptions(std::vector<std::filesystem::path>& args) {
    AudioOptionParse result;
    std::vector<std::filesystem::path> kept;
    kept.reserve(args.size());

    for (std::size_t index = 0; index < args.size(); ++index) {
        // Every switch is ASCII, so comparing its UTF-8 form is safe even for a non-ASCII directory
        // argument: the path itself is stored and pushed back untouched, never round-tripped.
        const std::string flag = audioPathUtf8(args[index]);
        if (index == 0) { // the program name stays put
            kept.push_back(args[index]);
            continue;
        }
        if (flag == "--volume" || flag.rfind("--volume=", 0) == 0) {
            std::string raw;
            if (flag == "--volume") {
                if (index + 1 >= args.size()) {
                    result.ok = false;
                    result.error = "--volume expects a number from 0 to 100, got nothing";
                    break;
                }
                raw = audioPathUtf8(args[++index]);
            } else {
                raw = flag.substr(std::string("--volume=").size());
            }
            if (!parseVolumeValue(raw, result.options.volume, result.error)) {
                result.ok = false;
                break;
            }
            continue;
        }
        if (flag == "--music-volume" || flag.rfind("--music-volume=", 0) == 0) {
            std::string raw;
            if (flag == "--music-volume") {
                if (index + 1 >= args.size()) {
                    result.ok = false;
                    result.error = "--music-volume expects a number from 0 to 100, got nothing";
                    break;
                }
                raw = audioPathUtf8(args[++index]);
            } else {
                raw = flag.substr(std::string("--music-volume=").size());
            }
            if (!parsePercentValue("--music-volume", raw, result.options.musicVolume, result.error)) {
                result.ok = false;
                break;
            }
            continue;
        }
        if (flag == "--sfx-volume" || flag.rfind("--sfx-volume=", 0) == 0) {
            std::string raw;
            if (flag == "--sfx-volume") {
                if (index + 1 >= args.size()) {
                    result.ok = false;
                    result.error = "--sfx-volume expects a number from 0 to 100, got nothing";
                    break;
                }
                raw = audioPathUtf8(args[++index]);
            } else {
                raw = flag.substr(std::string("--sfx-volume=").size());
            }
            if (!parsePercentValue("--sfx-volume", raw, result.options.sfxVolume, result.error)) {
                result.ok = false;
                break;
            }
            continue;
        }
        if (flag == "--mute-bgm") {
            result.options.muteMusic = true;
            continue;
        }
        if (flag == "--mute-sfx") {
            result.options.muteSfx = true;
            continue;
        }
        if (flag == "--audio-off") {
            result.options.off = true;
            continue;
        }
        kept.push_back(args[index]);
    }
    if (!result.ok) return result; // a bad value leaves `args` untouched for the caller's message
    args = std::move(kept);
    return result;
}

AudioOptionParse parseAudioOptions(std::vector<std::string>& args) {
    std::vector<std::filesystem::path> paths;
    paths.reserve(args.size());
    for (const auto& arg : args) paths.push_back(pathFromUtf8(arg));
    AudioOptionParse result = parseAudioOptions(paths);
    if (!result.ok) return result;
    args.clear();
    args.reserve(paths.size());
    for (const auto& path : paths) args.push_back(audioPathUtf8(path));
    return result;
}

void applyAudioOptions(const AudioOptions& options) {
    gOptions = options;
    gOptions.volume = std::clamp(gOptions.volume, 0, 100);
    if (gOptions.musicVolume >= 0) gOptions.musicVolume = std::clamp(gOptions.musicVolume, 0, 100);
    if (gOptions.sfxVolume >= 0) gOptions.sfxVolume = std::clamp(gOptions.sfxVolume, 0, 100);
    // A silent sink stays silent: --audio-off is a latch, so a later --volume must not undo it.
    gOptions.off = gOptions.off || gAudioOff;
    if (gOptions.off) gAudioOff = true;
    pushOptions(gRuntime.get());
}

std::string audioOptionUsage() {
    return "--volume <0..100>  master volume (0 is silent, default 100); --music-volume / "
           "--sfx-volume <0..100> trim one bus (default: inherit the master); --mute-bgm / "
           "--mute-sfx silence one bus";
}

} // namespace pvz
