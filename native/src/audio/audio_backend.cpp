#if defined(PVZ_ENABLE_DESKTOP)

#include "audio/audio_backend.hpp"

#include <SDL3/SDL.h>

#include <cstring>
#include <map>
#include <string>
#include <vector>

#include "audio/audio_decode.hpp"

namespace pvz {
namespace {

/// 48 kHz float stereo is what the device is opened with; every clip is converted to it once.
constexpr int kDeviceRate = 48000;
constexpr int kDeviceChannels = 2;
/// Keep roughly 50 ms queued so a long frame cannot starve the device, while staying small enough
/// that a `stopAll` is audible immediately.
constexpr int kChunkFrames = 512;
constexpr int kTargetQueuedBytes = kDeviceRate * kDeviceChannels * 4 / 20;

AudioClip convertClip(const std::string& name, SDL_AudioSpec source, const float* data,
                      int frames) {
    AudioClip clip;
    clip.name = name;
    SDL_AudioSpec target{};
    target.format = SDL_AUDIO_F32;
    target.channels = kDeviceChannels;
    target.freq = kDeviceRate;
    SDL_AudioStream* stream = SDL_CreateAudioStream(&source, &target);
    if (stream == nullptr) return clip;
    SDL_PutAudioStreamData(stream, data, frames * source.channels * static_cast<int>(sizeof(float)));
    SDL_FlushAudioStream(stream);
    const int available = SDL_GetAudioStreamAvailable(stream);
    if (available > 0) {
        std::vector<float> out(static_cast<std::size_t>(available) / sizeof(float));
        const int read = SDL_GetAudioStreamData(stream, out.data(), available);
        if (read > 0) {
            out.resize(static_cast<std::size_t>(read) / sizeof(float));
            clip.sampleRate = kDeviceRate;
            clip.channels = kDeviceChannels;
            clip.samples = std::move(out);
        }
    }
    SDL_DestroyAudioStream(stream);
    return clip;
}

class SdlAudioBackend final : public AudioBackend {
public:
    SdlAudioBackend(const AudioCatalog& catalog, const EventMap& events)
        : catalog_(catalog), events_(events) {
        if (!SDL_InitSubSystem(SDL_INIT_AUDIO)) {
            note_ = std::string("SDL_InitSubSystem(SDL_INIT_AUDIO): ") + SDL_GetError();
            return;
        }
        audioInitialised_ = true;
        SDL_AudioSpec spec{};
        spec.format = SDL_AUDIO_F32;
        spec.channels = kDeviceChannels;
        spec.freq = kDeviceRate;
        // A null callback puts the stream in push mode: we own the mixing thread timing.
        stream_ = SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec, nullptr, nullptr);
        if (stream_ == nullptr) {
            note_ = std::string("SDL_OpenAudioDeviceStream: ") + SDL_GetError();
            return;
        }
        if (!SDL_ResumeAudioStreamDevice(stream_)) {
            note_ = std::string("SDL_ResumeAudioStreamDevice: ") + SDL_GetError();
            SDL_DestroyAudioStream(stream_);
            stream_ = nullptr;
            return;
        }
        available_ = true;
        scratch_.resize(static_cast<std::size_t>(kChunkFrames) * kDeviceChannels);
    }

    ~SdlAudioBackend() override {
        if (stream_ != nullptr) SDL_DestroyAudioStream(stream_);
        if (audioInitialised_) SDL_QuitSubSystem(SDL_INIT_AUDIO);
    }

    bool available() const override { return available_; }
    std::string note() const override { return note_; }

    bool playSfx(const std::string& sound, float gain) override {
        if (!available_) return false;
        const AudioClip* clip = load(sound);
        return clip != nullptr && mixer_.playSfx(*clip, gain);
    }

    bool playMusic(const std::string& sound, bool loop, float gain) override {
        if (!available_) return false;
        const AudioClip* clip = load(sound);
        return clip != nullptr && mixer_.playMusic(*clip, loop, gain);
    }

    void stopMusic() override { mixer_.stopMusic(); }
    void stopAll() override { mixer_.stopAll(); }

    void setMasterVolume(float volume) override { mixer_.setMasterVolume(volume); }
    void setMusicVolume(float volume) override { mixer_.setMusicVolume(volume); }
    void setSfxVolume(float volume) override { mixer_.setSfxVolume(volume); }
    void setMuted(bool muted) override { mixer_.setMuted(muted); }
    void setMusicMuted(bool muted) override { mixer_.setMusicMuted(muted); }
    void setSfxMuted(bool muted) override { mixer_.setSfxMuted(muted); }
    float masterVolume() const override { return mixer_.masterVolume(); }
    float musicVolume() const override { return mixer_.musicVolume(); }
    float sfxVolume() const override { return mixer_.sfxVolume(); }
    bool muted() const override { return mixer_.muted(); }
    bool musicMuted() const override { return mixer_.musicMuted(); }
    bool sfxMuted() const override { return mixer_.sfxMuted(); }

    void pump() override {
        if (!available_ || stream_ == nullptr) return;
        while (SDL_GetAudioStreamQueued(stream_) < kTargetQueuedBytes) {
            mixer_.mix(scratch_.data(), static_cast<std::size_t>(kChunkFrames));
            if (!SDL_PutAudioStreamData(stream_, scratch_.data(),
                                        static_cast<int>(scratch_.size() * sizeof(float))))
                return;
        }
    }

    std::size_t mixedFrames() const override { return mixer_.mixedFrames(); }
    std::size_t loadedClips() const override { return clips_.size(); }
    float lastPeak() const override { return mixer_.lastPeak(); }
    bool musicFading() const override { return mixer_.musicFading(); }
    float musicFadeProgress() const override { return mixer_.musicFadeProgress(); }

private:
    /// Decodes on first use and keeps the clip: `sfx_click` is 2 KB but `frontyard_loop` is
    /// 6.5 MB, so loading all 65 up front would cost more than it saves.
    const AudioClip* load(const std::string& sound) {
        const auto cached = clips_.find(sound);
        if (cached != clips_.end()) return cached->second.empty() ? nullptr : &cached->second;
        const Sound* entry = catalog_.find(sound);
        if (entry == nullptr || !entry->present) {
            clips_.emplace(sound, AudioClip{});
            return nullptr;
        }
        const auto path = catalog_.assetRoot / entry->file;
        AudioClip clip;
        try {
            if (entry->format == "wav") {
                clip = loadWav(sound, path);
            } else if (entry->format == "ogg" || entry->format == "mp3") {
                // Both decoders return float samples at the file's own rate; the shared converter
                // resamples them to the device format (48 kHz stereo).
                const DecodedAudio decoded = entry->format == "ogg" ? decodeOggFile(path)
                                                                   : decodeMp3File(path);
                if (!decoded.empty()) {
                    SDL_AudioSpec source{};
                    source.format = SDL_AUDIO_F32;
                    source.channels = decoded.channels;
                    source.freq = decoded.sampleRate;
                    clip = convertClip(sound, source, decoded.samples.data(),
                                       static_cast<int>(decoded.frames));
                }
            }
        } catch (const std::exception&) {
            clip = AudioClip{};
        }
        const auto inserted = clips_.emplace(sound, std::move(clip));
        if (inserted.first->second.empty()) {
            std::string resolved = sound;
            if (const std::string fallback = events_.fallbackFor(sound); !fallback.empty())
                resolved = fallback;
            if (resolved != sound) return load(resolved);
            return nullptr;
        }
        return &inserted.first->second;
    }

    AudioClip loadWav(const std::string& name, const std::filesystem::path& path) {
        const std::string utf8 = audioPathUtf8(path);
        SDL_AudioSpec spec{};
        Uint8* data = nullptr;
        Uint32 length = 0;
        if (!SDL_LoadWAV(utf8.c_str(), &spec, &data, &length)) return AudioClip{};
        const int frames = static_cast<int>(length / (spec.channels * SDL_AUDIO_BYTESIZE(spec.format)));
        AudioClip clip;
        // SDL hands back the file's native format (PCM16 mono for every shipped wav); the shared
        // converter turns it into the device format, and 22050 Hz files are resampled there.
        if (spec.format == SDL_AUDIO_F32 && frames > 0) {
            clip = convertClip(name, spec, reinterpret_cast<const float*>(data), frames);
        } else if (frames > 0) {
            SDL_AudioSpec asFloat = spec;
            asFloat.format = SDL_AUDIO_F32;
            SDL_AudioStream* toFloat = SDL_CreateAudioStream(&spec, &asFloat);
            if (toFloat != nullptr) {
                SDL_PutAudioStreamData(toFloat, data, static_cast<int>(length));
                SDL_FlushAudioStream(toFloat);
                const int available = SDL_GetAudioStreamAvailable(toFloat);
                std::vector<float> converted(static_cast<std::size_t>(available) / sizeof(float));
                const int read = SDL_GetAudioStreamData(toFloat, converted.data(), available);
                SDL_DestroyAudioStream(toFloat);
                if (read > 0) {
                    converted.resize(static_cast<std::size_t>(read) / sizeof(float));
                    clip = convertClip(name, asFloat, converted.data(),
                                       static_cast<int>(converted.size()) / asFloat.channels);
                }
            }
        }
        SDL_free(data);
        return clip;
    }

    const AudioCatalog& catalog_;
    const EventMap& events_;
    AudioMixer mixer_;
    std::map<std::string, AudioClip> clips_;
    SDL_AudioStream* stream_ = nullptr;
    std::vector<float> scratch_;
    std::string note_;
    bool available_ = false;
    bool audioInitialised_ = false;
};

} // namespace

bool audioBackendCompiledIn() { return true; }

std::string audioBackendBuildNote() { return "SDL3 push-mode device (48 kHz float stereo)"; }

std::unique_ptr<AudioBackend> AudioBackend::create(const AudioCatalog& catalog,
                                                   const EventMap& events) {
    return std::make_unique<SdlAudioBackend>(catalog, events);
}

} // namespace pvz

#endif // PVZ_ENABLE_DESKTOP
