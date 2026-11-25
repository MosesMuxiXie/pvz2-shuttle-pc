#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

// Pure mixing, no SDL and no device: WAV/OGG/MP3 decode straight into an AudioClip, the mixer turns
// clips plus volume into stereo floats, and whichever backend is compiled in only has to move
// those floats to the sound card. That split is what lets the audit build (PVZ_ENABLE_DESKTOP=OFF)
// exercise the same mixing code the desktop build runs.
namespace pvz {

struct AudioClip {
    std::string name;
    int sampleRate = 0;
    int channels = 0;
    std::vector<float> samples; ///< interleaved, 1 or 2 channels, nominally [-1, 1]
    bool empty() const { return frames() == 0; }
    std::size_t frames() const {
        if (sampleRate <= 0 || channels <= 0) return 0;
        return samples.size() / static_cast<std::size_t>(channels);
    }
    double seconds() const {
        return sampleRate > 0 ? static_cast<double>(frames()) / static_cast<double>(sampleRate)
                              : 0.0;
    }
};

/// Fixed 48 kHz stereo output: the device is opened once with that format and never reopened.
///
/// Resampling is **linear interpolation on the phase**, not nearest sample. Every source rate
/// (22050, 24000, 32000, 44100, 48000) ends up as `position += rate / 48000`, and each output frame
/// reads `s[i] + (s[i+1] - s[i]) * frac`. Nearest-neighbour reading of a 44.1 kHz clip at 48 kHz
/// repeats every 147th sample and drops the rest, which is audible as a metallic edge on the
/// `frontyard_loop` strings; interpolation removes that without a filter design.
///
/// Volume is three numbers deep: `master` for the whole game, and one gain per bus (music, sfx).
/// The CLI's `--volume` drives master, `--music-volume`/`--sfx-volume` drive the buses, and
/// `--mute-bgm`/`--mute-sfx` zero a bus outright, so a player can turn the world theme down
/// without losing the sun-collect chime:
///
///     output = master * bus * voice.gain * crossfade envelope
class AudioMixer {
public:
    static constexpr int kSampleRate = 48000;
    static constexpr int kChannels = 2;
    /// Sound-effect voices. Sixteen is what a busy wave needs: a shooter volley, two groans, a
    /// sun chime, the wave horn and the shovel all at once; eight used to steal the chime.
    static constexpr std::size_t kMaxVoices = 16;

    /// Crossfade length when the music track changes. 0.75 s hides the cut on a looping world
    /// theme without leaving the menu sounding like it is still on the old song.
    static constexpr double kMusicFadeSeconds = 0.75;
    static constexpr std::size_t kMusicFadeFrames =
        static_cast<std::size_t>(static_cast<double>(kSampleRate) * kMusicFadeSeconds);

    /// Starts `clip` on a free sfx voice (1..kMaxVoices) and returns true.
    ///
    /// **Preemption rule** (only when all `kMaxVoices` are busy): evict the voice with the lowest
    /// `priority`; if several share that priority, evict the one that started earliest (smallest
    /// `started` sequence). So a long `zombie_groan` at priority 0 goes before a `level_won` at
    /// priority 5, and among equals the oldest sound dies first — a fresh pellet never cuts the
    /// pellet fired a moment ago in the same volley. Music lives on slot 0 and is never a victim.
    bool playSfx(const AudioClip& clip, float gain = 1.0F, int priority = 0);
    /// Starts `clip` as the music track. A different track already playing is crossfaded out over
    /// `kMusicFadeFrames`; the same track keeps its position instead of restarting.
    bool playMusic(const AudioClip& clip, bool loop = true, float gain = 1.0F);
    void stopMusic();
    void stopAll();

    void setMasterVolume(float volume); ///< clamped to [0, 1]
    void setMusicVolume(float volume);  ///< clamped to [0, 1]
    void setSfxVolume(float volume);    ///< clamped to [0, 1]
    void setMuted(bool muted);
    void setMusicMuted(bool muted);
    void setSfxMuted(bool muted);

    float masterVolume() const { return masterVolume_; }
    float musicVolume() const { return musicVolume_; }
    float sfxVolume() const { return sfxVolume_; }
    bool muted() const { return muted_; }
    bool musicMuted() const { return musicMuted_; }
    bool sfxMuted() const { return sfxMuted_; }

    std::size_t activeSfx() const;
    /// Names of the active sfx voices in slot order, so a test can name what survived a steal.
    std::vector<std::string> activeSfxNames() const;
    bool musicPlaying() const;
    std::string musicName() const;
    /// True while the previous track is still ramping out.
    bool musicFading() const { return fading_.active && fadeElapsed_ < kMusicFadeFrames; }
    /// 0..1 through the current crossfade; 1 means the fade is over.
    float musicFadeProgress() const;

    /// Writes `frames` stereo interleaved samples, replacing whatever was in `output`. The frame
    /// count is independent of volume and of a running crossfade: silence is written, not skipped.
    void mix(float* output, std::size_t frames);
    /// Frames rendered since construction, so a caller can assert the mixer actually produced
    /// audio without a sound card.
    std::size_t mixedFrames() const { return mixedFrames_; }
    /// Peak |sample| of the last `mix()` call, after volume and before the device sees it. A test
    /// uses it to prove `--volume 0` really multiplies the buffer to zero.
    float lastPeak() const { return lastPeak_; }

    /// One sampled frame of a clip at fractional source position, linearly interpolated. Public so
    /// the interpolation itself can be asserted against hand-computed values instead of a peak.
    /// `wrap` picks the neighbour of the last frame: frame 0 for a looping track, the last frame
    /// itself (hold) for a one-shot, so a sound's tail never blends into its own attack.
    static float sampleAt(const AudioClip& clip, double position, int channel, bool wrap = true);

private:
    struct Voice {
        const AudioClip* clip = nullptr;
        double position = 0.0; ///< in source frames, fractional
        double ratio = 1.0;    ///< source frames per output frame
        bool loop = false;
        bool music = false;
        float gain = 1.0F;
        int priority = 0;          ///< higher survives longer when the pool is full
        std::uint64_t started = 0; ///< start order; among equal priority the smallest dies first
        bool active = false;
    };

    enum Ramp { kRampNone = 0, kRampIn = 1, kRampOut = 2 };

    /// Mixes one voice into `output`. `bus` is master x the voice's bus gain; `ramp` folds the
    /// crossfade envelope in, so the outgoing track falls while the incoming one rises sample by
    /// sample and neither end of the fade can click.
    void render(Voice& voice, float bus, float* output, std::size_t frames, int ramp);

    std::array<Voice, kMaxVoices + 1> voices_{}; ///< slot 0 is the music voice
    Voice fading_{};                             ///< the outgoing music track during a crossfade
    float fadingGain_ = 0.0F;                    ///< its gain when the switch happened
    std::size_t fadeElapsed_ = kMusicFadeFrames; ///< output frames since the last track change
    float masterVolume_ = 1.0F;
    float musicVolume_ = 1.0F;
    float sfxVolume_ = 1.0F;
    bool muted_ = false;
    bool musicMuted_ = false;
    bool sfxMuted_ = false;
    float lastPeak_ = 0.0F;
    std::size_t mixedFrames_ = 0;
    std::uint64_t startCounter_ = 0; ///< bumped on every start; orders preemption ties
};

} // namespace pvz
