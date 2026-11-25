#pragma once
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <memory>
#include <set>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "audio/audio_backend.hpp"
#include "audio/audio_catalog.hpp"
#include "audio/event_map.hpp"

// The seam between the engine and the sound card. `--audio-audit` proved the pipeline decodes
// and that the event table resolves; this file is what actually plays during a frame.
//
// Three rules keep it out of the way of the pictures:
//   * `headless` (a screenshot run) never opens a device, so a PNG stays byte-identical;
//   * one (tick, event type) pair plays at most once, so a peashooter's 400 pellets cannot fill
//     the eight mixer voices and starve the wave horn;
//   * every counter below counts a call that happened, so a test can prove silence instead of
//     trusting a comment about silence.
namespace pvz {

/// How a view wants to be heard. `headless` draws one frame and must not touch the sound card.
enum class AudioMode { live, muted, headless };

struct AudioCounters {
    std::size_t pumpCalls = 0;
    std::size_t musicStarts = 0;
    std::size_t sfxRequests = 0;   ///< requests that survived the per-tick dedupe
    std::size_t playSfxCalls = 0;  ///< forwarded to the backend: 0 when muted or headless
    std::size_t eventsSeen = 0;
    std::size_t eventsMapped = 0;
    std::size_t eventsUnmapped = 0; ///< events the table deliberately leaves silent
    std::size_t eventsDeduped = 0;  ///< suppressed because (tick, type) already played
};

/// Owns the decoded clips behind one backend and turns `engine::World::events()` into sfx.
/// The catalog and the event table are cheap value types, so the runtime copies what it needs and
/// the caller cannot pull the rug out from under a running frame.
class AudioRuntime {
  public:
    AudioRuntime(const AudioCatalog& catalog, AudioMode mode);
    ~AudioRuntime();
    AudioRuntime(const AudioRuntime&) = delete;
    AudioRuntime& operator=(const AudioRuntime&) = delete;

    /// Loads the catalog and builds a backend. A missing `audio/audio_report.json` is not fatal:
    /// the runtime comes back silent (`enabled() == false`) and `error` explains why, because a
    /// broken asset install must not stop the game from drawing its lawn.
    static std::unique_ptr<AudioRuntime> open(const std::filesystem::path& assetRoot, AudioMode mode,
                                              std::string* error = nullptr);

    AudioMode mode() const { return mode_; }
    /// True only when this run may make noise: `live` with a usable device.
    bool enabled() const;
    bool deviceAvailable() const;
    /// `live (SDL3 push-mode device)` / `muted (--audio-off)` / `headless (snapshot)`,
    /// plus the backend's own reason when the device refused to open.
    std::string status() const;
    /// Why the run is silent at the device level (empty when it plays).
    std::string note() const;
    const std::filesystem::path& assetRoot() const { return assetRoot_; }

    const AudioCatalog& catalog() const { return catalog_; }
    const EventMap& events() const { return events_; }

    /// `<world>_loop` first, `obb/MUSIC_*` as the documented fallback (see `selectMusic`).
    void playMusicForWorld(const std::string& world, bool intro = false);
    /// The main menu track (`menu`), looped.
    void playMenuMusic();
    /// One UI click; the caller decides when a click really happened.
    void playClick();
    void stopMusic();
    void stopAll();
    void setMasterVolume(float volume);
    void setMuted(bool muted);
    float masterVolume() const;
    bool muted() const;

    /// `--volume <0..100>`: one master number, clamped here as well as in the mixer.
    void setVolume(int percent);
    int volume() const { return volume_; }
    /// `--music-volume` / `--sfx-volume`: per-bus trim, 0..100, defaulting to 100 (which means the
    /// bus inherits the master untouched). `--mute-bgm` / `--mute-sfx` still zero the bus outright.
    void setMusicVolume(int percent);
    void setSfxVolume(int percent);
    int musicVolume() const { return musicVolume_; }
    int sfxVolume() const { return sfxVolume_; }
    /// `--mute-bgm` / `--mute-sfx`: the two buses can be silenced one at a time.
    void setMusicMuted(bool muted);
    void setSfxMuted(bool muted);
    bool musicMuted() const { return musicMuted_; }
    bool sfxMuted() const { return sfxMuted_; }

    /// Peak of the last mixed chunk and the state of the music crossfade, so a test or the device
    /// harness can prove that volume acts on the samples and that a track switch really ramps.
    float lastPeak() const;
    bool musicFading() const;
    float musicFadeProgress() const;

    /// Plays the new events in `events[cursor..]` and returns the next cursor. Events already
    /// consumed are never replayed, and a (tick, type) pair that already played is only counted.
    std::size_t consume(const nlohmann::json& events, std::size_t cursor);
    /// Keeps the device queue topped up. Safe every frame and cheap without a device.
    void pump();

    const AudioCounters& counters() const { return counters_; }
    /// The last 64 sound names handed to the backend, oldest first: a test can name what played.
    const std::vector<std::string>& playedLog() const { return playedLog_; }
    const std::vector<std::string>& silentEvents() const { return silentEvents_; }
    const std::string& musicName() const { return musicName_; }
    /// Non-null only in `live` mode; the desktop test reads `mixedFrames()` from it.
    AudioBackend* backend() const { return backend_.get(); }

  private:
    void start(const std::string& sound, float gain);
    void remember(const std::string& sound);

    AudioMode mode_;
    std::filesystem::path assetRoot_;
    AudioCatalog catalog_;
    EventMap events_;
    std::unique_ptr<AudioBackend> backend_;
    AudioCounters counters_{};
    std::vector<std::string> playedLog_;
    std::vector<std::string> silentEvents_;
    std::string musicName_;
    std::string statusNote_;
    std::uint64_t lastTick_ = 0;
    bool tickOpen_ = false;
    std::set<std::string> tickTypes_;
    int volume_ = 100;
    int musicVolume_ = 100;
    int sfxVolume_ = 100;
    bool musicMuted_ = false;
    bool sfxMuted_ = false;
};

// ---------------------------------------------------------------------------------------------
// Volume switches. `main.cpp` collects these before any view runs, which is why the parser lives
// here instead of in each branch: `--volume` has to work for `--play`, `--menu`, `--worldmap` and
// every other command without every branch repeating three lines of argument parsing.
// ---------------------------------------------------------------------------------------------

/// One master volume, two optional bus trims and per-bus mutes. The three numbers relate as
/// `output = master x bus x voice.gain x fade`; a bus trim of -1 (the default, i.e. the switch was
/// not given) means "inherit the master", which the mixer expresses by leaving that bus at 1.0.
/// Two trims rather than two masters: the game keeps one player-facing volume, and the trims exist
/// so a screenshot/diagnostic run or a future options slider can push music under the chimes
/// without inventing a second master that the two would then multiply.
struct AudioOptions {
    int volume = 100;       ///< 0..100, `--volume`
    int musicVolume = -1;   ///< 0..100, `--music-volume`; -1 = inherit the master
    int sfxVolume = -1;     ///< 0..100, `--sfx-volume`; -1 = inherit the master
    bool muteMusic = false;
    bool muteSfx = false;
    bool off = false; ///< `--audio-off`, the older global kill switch
};

struct AudioOptionParse {
    AudioOptions options;
    bool ok = true;
    std::string error; ///< `--volume expects ...`; empty when the switches were understood
};

/// Removes `--volume N`, `--music-volume N`, `--sfx-volume N`, `--mute-bgm`, `--mute-sfx` and
/// `--audio-off` from `args` (index 1 onward) and reports what they asked for. Unknown switches are
/// left alone for the command to reject.
AudioOptionParse parseAudioOptions(std::vector<std::string>& args);
/// The same parse for the process argv this program actually carries (`std::filesystem::path`, so a
/// non-ASCII asset directory survives). main() only has to call this and then applyAudioOptions().
AudioOptionParse parseAudioOptions(std::vector<std::filesystem::path>& args);
/// Remembers the values for runtimes attached later and pushes them into the live one.
void applyAudioOptions(const AudioOptions& options);
/// The `--help` line for the three switches.
std::string audioOptionUsage();

// ---------------------------------------------------------------------------------------------
// The views own their own option structs, and those headers are not this task's to change. These
// helpers let `battle_view.cpp`, `menu_view.cpp`, `worldmap_view.cpp`, `level_select_view.cpp`
// and `launcher.cpp` reach one process-wide runtime with three lines each.
// ---------------------------------------------------------------------------------------------

/// Set once from the CLI (`--audio-off`) before any view runs; also forces `muted` on attach.
void setAudioOff(bool off);
bool audioOff();

/// Builds (or reuses) the process-wide runtime for `assetRoot`. `headless` wins over the
/// `--audio-off` switch: a screenshot run is silent either way, but reports why.
/// Never throws: a broken asset tree leaves the game silent and the reason is recorded.
AudioRuntime* attachAudio(const std::filesystem::path& assetRoot, bool headless);
void detachAudio();
AudioRuntime* ambientAudio();

/// Per-frame helpers the views call. All are no-ops before `attachAudio` or after a failure.
void pumpAudio();
void playAudioMusicForWorld(const std::string& world);
void playAudioMenuMusic();
void playAudioClick();
std::size_t consumeAudioEvents(const nlohmann::json& events, std::size_t cursor);

/// Drops the process-wide runtime so a test starts from `--audio-off` with no leftover state.
void resetAudioForTest();

} // namespace pvz
