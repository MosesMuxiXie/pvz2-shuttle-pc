#include "audio/audio_mixer.hpp"

#include <algorithm>
#include <cmath>

namespace pvz {

namespace {
double ratioFor(const AudioClip& clip) {
    const double ratio = static_cast<double>(clip.sampleRate) / static_cast<double>(AudioMixer::kSampleRate);
    return ratio > 0.0 ? ratio : 1.0;
}
} // namespace

float AudioMixer::sampleAt(const AudioClip& clip, double position, int channel, bool wrap) {
    const std::size_t total = clip.frames();
    if (total == 0) return 0.0F;
    const std::size_t stride = static_cast<std::size_t>(clip.channels);
    const int last = clip.channels - 1;
    const std::size_t lane = static_cast<std::size_t>(std::clamp(channel, 0, last));

    if (position < 0.0) position = 0.0;
    if (position >= static_cast<double>(total))
        position = wrap ? std::fmod(position, static_cast<double>(total))
                        : static_cast<double>(total - 1);

    const auto index = static_cast<std::size_t>(position);
    const float frac = static_cast<float>(position - static_cast<double>(index));
    // The neighbour is the next frame, wrapping to frame 0 for a loop. A one-shot holds the last
    // frame instead, because blending its tail into its attack would be a click, not a smoother.
    const std::size_t next = index + 1 < total ? index + 1 : (wrap ? 0 : index);
    const float a = clip.samples[index * stride + lane];
    const float b = clip.samples[next * stride + lane];
    return a + (b - a) * frac;
}

void AudioMixer::setMasterVolume(float volume) {
    if (std::isnan(volume)) return;
    masterVolume_ = std::clamp(volume, 0.0F, 1.0F);
}

void AudioMixer::setMusicVolume(float volume) {
    if (std::isnan(volume)) return;
    musicVolume_ = std::clamp(volume, 0.0F, 1.0F);
}

void AudioMixer::setSfxVolume(float volume) {
    if (std::isnan(volume)) return;
    sfxVolume_ = std::clamp(volume, 0.0F, 1.0F);
}

void AudioMixer::setMuted(bool muted) { muted_ = muted; }

void AudioMixer::setMusicMuted(bool muted) { musicMuted_ = muted; }

void AudioMixer::setSfxMuted(bool muted) { sfxMuted_ = muted; }

bool AudioMixer::playSfx(const AudioClip& clip, float gain, int priority) {
    if (clip.empty()) return false;
    // Voices 1..kMaxVoices are the sfx pool; slot 0 is music and never a victim.
    std::size_t slot = 0;
    for (std::size_t i = 1; i <= kMaxVoices; ++i) {
        if (!voices_[i].active) {
            slot = i;
            break;
        }
    }
    if (slot == 0) {
        // Pool full: evict the lowest priority, and among equal priorities the earliest start. That
        // keeps a wave horn over a pellet and a fresh pellet over the one fired 3 ms earlier.
        slot = 1;
        for (std::size_t i = 2; i <= kMaxVoices; ++i) {
            const Voice& candidate = voices_[i];
            const Voice& victim = voices_[slot];
            if (candidate.priority < victim.priority ||
                (candidate.priority == victim.priority && candidate.started < victim.started)) {
                slot = i;
            }
        }
    }
    Voice& voice = voices_[slot];
    voice.clip = &clip;
    voice.position = 0.0;
    voice.ratio = ratioFor(clip);
    voice.loop = false;
    voice.music = false;
    voice.gain = std::clamp(gain, 0.0F, 4.0F);
    voice.priority = priority;
    voice.started = ++startCounter_;
    voice.active = true;
    return true;
}

bool AudioMixer::playMusic(const AudioClip& clip, bool loop, float gain) {
    if (clip.empty()) return false;
    Voice& music = voices_[0];
    const float target = std::clamp(gain, 0.0F, 4.0F);
    // Re-entering the same theme keeps its position: a level restart must not stutter the loop.
    if (music.active && music.clip == &clip) {
        music.gain = target;
        return true;
    }
    if (music.active && music.clip != nullptr) {
        // Hand the old track to the fade-out slot instead of dropping it on the floor. The
        // incoming track only ramps in when something is actually ramping out; a first start from
        // silence keeps full gain, because a fade from nothing would only delay the music.
        fading_ = music;
        fadingGain_ = music.gain;
        fadeElapsed_ = 0;
    } else {
        fading_ = Voice{};
        fadingGain_ = 0.0F;
        fadeElapsed_ = kMusicFadeFrames;
    }

    music.clip = &clip;
    music.position = 0.0;
    music.ratio = ratioFor(clip);
    music.loop = loop;
    music.music = true;
    music.gain = target;
    music.priority = 0;
    music.started = ++startCounter_;
    music.active = true;
    return true;
}

void AudioMixer::stopMusic() {
    voices_[0] = Voice{};
    fading_ = Voice{};
    fadingGain_ = 0.0F;
    fadeElapsed_ = kMusicFadeFrames;
}

void AudioMixer::stopAll() {
    for (auto& voice : voices_) voice = Voice{};
    fading_ = Voice{};
    fadingGain_ = 0.0F;
    fadeElapsed_ = kMusicFadeFrames;
}

std::size_t AudioMixer::activeSfx() const {
    std::size_t count = 0;
    for (std::size_t i = 1; i <= kMaxVoices; ++i)
        if (voices_[i].active) ++count;
    return count;
}

std::vector<std::string> AudioMixer::activeSfxNames() const {
    std::vector<std::string> names;
    for (std::size_t i = 1; i <= kMaxVoices; ++i) {
        if (voices_[i].active && voices_[i].clip != nullptr) names.push_back(voices_[i].clip->name);
    }
    return names;
}

bool AudioMixer::musicPlaying() const { return voices_[0].active; }

std::string AudioMixer::musicName() const {
    return voices_[0].active && voices_[0].clip != nullptr ? voices_[0].clip->name : std::string{};
}

float AudioMixer::musicFadeProgress() const {
    static_assert(kMusicFadeFrames > 0, "the fade length is a compile-time constant in frames");
    const float t = static_cast<float>(fadeElapsed_) / static_cast<float>(kMusicFadeFrames);
    return std::clamp(t, 0.0F, 1.0F);
}

void AudioMixer::render(Voice& voice, float bus, float* output, std::size_t frames, int ramp) {
    if (!voice.active) return;
    const AudioClip* clip = voice.clip;
    if (clip == nullptr || clip->empty()) {
        voice = Voice{};
        return;
    }
    const std::size_t total = clip->frames();
    const auto sourceFrames = static_cast<double>(total);
    const bool stereo = clip->channels >= 2;
    const float scale = bus * voice.gain;
    const auto fadeSpan = static_cast<double>(kMusicFadeFrames);
    double position = voice.position;
    for (std::size_t frame = 0; frame < frames; ++frame) {
        // Envelope: `kRampIn` rises 0 -> 1 over the fade, `kRampOut` falls 1 -> 0. Both are linear
        // in the sample index, so no step ever appears between two neighbouring samples.
        float envelope = 1.0F;
        if (ramp != kRampNone && fadeSpan > 0.0) {
            const double t = std::min(1.0, (static_cast<double>(fadeElapsed_) +
                                            static_cast<double>(frame)) /
                                               fadeSpan);
            envelope = static_cast<float>(ramp == kRampIn ? t : 1.0 - t);
        }
        const float frameGain = scale * envelope;
        if (position >= sourceFrames) {
            if (!voice.loop) {
                voice = Voice{};
                return;
            }
            position = std::fmod(position, sourceFrames);
        }
        // Linear interpolation on the fractional phase. For a looping track the neighbour of the
        // last frame is frame 0 (the wrap the loop needs); a one-shot holds its last frame, and the
        // guard above ends it before that matters anyway.
        const float left = sampleAt(*clip, position, 0, voice.loop) * frameGain;
        const float right = sampleAt(*clip, position, stereo ? 1 : 0, voice.loop) * frameGain;
        output[frame * 2] += left;
        output[frame * 2 + 1] += right;
        position += voice.ratio;
    }
    if (voice.active) voice.position = position;
}

void AudioMixer::mix(float* output, std::size_t frames) {
    if (output == nullptr || frames == 0) return;
    std::fill(output, output + frames * static_cast<std::size_t>(kChannels), 0.0F);

    const float master = muted_ ? 0.0F : masterVolume_;
    const float musicBus = master * (musicMuted_ ? 0.0F : musicVolume_);
    const float sfxBus = master * (sfxMuted_ ? 0.0F : sfxVolume_);

    render(voices_[0], musicBus, output, frames, fading_.active ? kRampIn : kRampNone);
    if (fading_.active) {
        Voice out = fading_;
        out.gain = fadingGain_;
        render(out, musicBus, output, frames, kRampOut);
        if (!out.active) {
            fading_ = Voice{};
            fadingGain_ = 0.0F;
        }
    }
    for (std::size_t i = 1; i <= kMaxVoices; ++i) render(voices_[i], sfxBus, output, frames, kRampNone);

    if (fadeElapsed_ < kMusicFadeFrames) {
        fadeElapsed_ = std::min(fadeElapsed_ + frames, kMusicFadeFrames);
        if (fadeElapsed_ >= kMusicFadeFrames) {
            fading_ = Voice{};
            fadingGain_ = 0.0F;
        }
    }

    // Sixteen voices can add up; clamp instead of letting the device wrap around, and remember the
    // peak so a volume setting can be proven rather than assumed.
    float peak = 0.0F;
    const std::size_t samples = frames * static_cast<std::size_t>(kChannels);
    for (std::size_t i = 0; i < samples; ++i) {
        output[i] = std::clamp(output[i], -1.0F, 1.0F);
        peak = std::max(peak, std::fabs(output[i]));
    }
    lastPeak_ = peak;
    mixedFrames_ += frames;
}

} // namespace pvz
