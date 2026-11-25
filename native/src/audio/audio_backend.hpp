#pragma once
#include <cstddef>
#include <memory>
#include <string>

#include "audio/audio_catalog.hpp"
#include "audio/event_map.hpp"
#include "audio/audio_mixer.hpp"

// The only part that touches a sound card. Two implementations exist:
//   * `audio_backend.cpp`      SDL3 device + SDL_AudioStream, compiled with PVZ_ENABLE_DESKTOP
//   * `audio_backend_null.cpp` a no-op that reports `available() == false`, compiled otherwise
// Both load clips through the same decoders, so `--audio-audit` measures what the game plays.
namespace pvz {

class AudioBackend {
public:
    virtual ~AudioBackend() = default;

    virtual bool available() const = 0;
    /// Why the backend is silent (`no SDL`, `SDL_OpenAudioDeviceStream: ...`), empty when it plays.
    virtual std::string note() const = 0;

    virtual bool playSfx(const std::string& sound, float gain = 1.0F) = 0;
    virtual bool playMusic(const std::string& sound, bool loop = true, float gain = 1.0F) = 0;
    virtual void stopMusic() = 0;
    virtual void stopAll() = 0;

    virtual void setMasterVolume(float volume) = 0;
    virtual void setMusicVolume(float volume) = 0;
    virtual void setSfxVolume(float volume) = 0;
    virtual void setMuted(bool muted) = 0;
    virtual void setMusicMuted(bool muted) = 0;
    virtual void setSfxMuted(bool muted) = 0;
    virtual float masterVolume() const = 0;
    virtual float musicVolume() const = 0;
    virtual float sfxVolume() const = 0;
    virtual bool muted() const = 0;
    virtual bool musicMuted() const = 0;
    virtual bool sfxMuted() const = 0;

    /// Tops the device queue back up. Cheap and safe to call every frame; a no-op without a device.
    virtual void pump() = 0;
    virtual std::size_t mixedFrames() const = 0;
    virtual std::size_t loadedClips() const = 0;
    /// Peak |sample| of the last mixed chunk, which is what the volume setting acts on.
    virtual float lastPeak() const = 0;
    virtual bool musicFading() const = 0;
    virtual float musicFadeProgress() const = 0;

    /// Never null. The result may be unavailable, which is the documented no-device degradation.
    static std::unique_ptr<AudioBackend> create(const AudioCatalog& catalog, const EventMap& events);
};

/// False when the binary was built with PVZ_ENABLE_DESKTOP=OFF.
bool audioBackendCompiledIn();
/// `SDL3 push-mode device` or `stub (PVZ_ENABLE_DESKTOP=OFF)`; recorded in the audit report.
std::string audioBackendBuildNote();

} // namespace pvz
