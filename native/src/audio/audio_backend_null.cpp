#if !defined(PVZ_ENABLE_DESKTOP)

#include "audio/audio_backend.hpp"

namespace pvz {
namespace {

/// Compiled into the audit/CI build, which has no SDL at all. Every call is a no-op and
/// `available()` stays false, which is what `--audio-audit` reports as `deviceAvailable: false`.
class NullAudioBackend final : public AudioBackend {
public:
    bool available() const override { return false; }
    std::string note() const override { return "audio backend stub: built without SDL (PVZ_ENABLE_DESKTOP=OFF)"; }

    bool playSfx(const std::string&, float, int) override { return false; }
    bool playMusic(const std::string&, bool, float) override { return false; }
    void stopMusic() override {}
    void stopAll() override {}

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

    void pump() override {}
    std::size_t mixedFrames() const override { return mixer_.mixedFrames(); }
    std::size_t loadedClips() const override { return 0; }
    float lastPeak() const override { return mixer_.lastPeak(); }
    bool musicFading() const override { return mixer_.musicFading(); }
    float musicFadeProgress() const override { return mixer_.musicFadeProgress(); }

private:
    AudioMixer mixer_;
};

} // namespace

bool audioBackendCompiledIn() { return false; }

std::string audioBackendBuildNote() { return "stub (PVZ_ENABLE_DESKTOP=OFF)"; }

std::unique_ptr<AudioBackend> AudioBackend::create(const AudioCatalog&, const EventMap&) {
    return std::make_unique<NullAudioBackend>();
}

} // namespace pvz

#endif // !PVZ_ENABLE_DESKTOP
