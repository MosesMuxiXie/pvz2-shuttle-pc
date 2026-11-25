#pragma once
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

// Sample decoding, kept apart from both the catalog (which only reads manifests) and the SDL
// backend (which owns the device). WAV is parsed by hand, OGG goes through the vendored
// `stb_vorbis.c`, MP3 through the vendored `minimp3.h`/`minimp3_ex.h`; a probe decodes without
// keeping samples, so `--audio-audit` can measure 47 Ogg files and 5 MP3s without holding their
// PCM in memory at once.
namespace pvz {

struct DecodedAudio {
    int sampleRate = 0;
    int channels = 0;
    std::uint64_t frames = 0;
    double seconds = 0.0;
    std::vector<float> samples; ///< interleaved, nominally [-1, 1]
    bool empty() const { return frames == 0 || samples.empty(); }
};

/// What `--audio-audit` records per file. `decoded == false` carries the reason in `error`.
struct AudioProbe {
    bool decoded = false;
    std::uint64_t frames = 0;
    double seconds = 0.0;
    int sampleRate = 0;
    int channels = 0;
    std::string format;
    std::string error;
};

/// Full decode. Throws `audio decode: <path>: <what>` on a missing or malformed file.
DecodedAudio decodeWavFile(const std::filesystem::path& path);
DecodedAudio decodeOggFile(const std::filesystem::path& path);
/// MP3 through the vendored minimp3 (public domain, `native/third_party/minimp3*.h`).
DecodedAudio decodeMp3File(const std::filesystem::path& path);

/// Frames and seconds without keeping the samples. Never throws: failures come back as
/// `decoded == false` plus `error`, because the audit has to report every file it cannot read.
AudioProbe probeAudioFile(const std::filesystem::path& path);

/// WAV, OGG and MP3: the three formats this build actually carries a decoder for. `audio_report`
/// marks one entry with the vendor's original `.m4a` source; that name is data, not a decoder.
bool audioFormatDecodable(const std::string& format);

} // namespace pvz
