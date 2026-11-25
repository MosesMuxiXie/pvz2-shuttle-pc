#include "audio/audio_decode.hpp"
#include "audio/audio_catalog.hpp"

#include <algorithm>
#include <cctype>
#include <cstddef>
#include <cstring>
#include <fstream>
#include <limits>
#include <stdexcept>
#include <vector>

// stb_vorbis is compiled once as C by the `pvz_stb_vorbis` target; this TU only needs the
// declarations, which the same file exposes under STB_VORBIS_HEADER_ONLY.
extern "C" {
#define STB_VORBIS_HEADER_ONLY
#include "stb_vorbis.c"
}

// minimp3 is vendored as two headers and its implementation is compiled right here, so the build
// needs no extra target and no extra build-system edit. Two details matter: the decoder is fed the
// bytes we already read (the install path contains non-ASCII characters, and minimp3's own file
// entry point takes a `const char*`), and it can count frames without keeping them, which is what
// `probeAudioFile` needs from a 5.6-second UI sound.
#ifndef NOMINMAX
#define NOMINMAX
#endif
#if defined(_MSC_VER)
#pragma warning(push, 0) // vendored C code: keep /W4 pointed at our sources, not at upstream
#endif
#define MINIMP3_IMPLEMENTATION
#define MINIMP3_FLOAT_OUTPUT
#include "minimp3_ex.h"
#if defined(_MSC_VER)
#pragma warning(pop)
#endif

namespace pvz {
namespace {

[[noreturn]] void fail(const std::filesystem::path& path, const std::string& what) {
    throw std::runtime_error("audio decode: " + audioPathUtf8(path) + ": " + what);
}

std::string lower(std::string text) {
    std::transform(text.begin(), text.end(), text.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return text;
}

std::string extensionOf(const std::filesystem::path& path) {
    std::string ext = lower(audioPathUtf8(path.extension()));
    if (!ext.empty() && ext.front() == '.') ext.erase(ext.begin());
    return ext;
}

std::vector<unsigned char> readBytes(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) fail(path, "cannot open for reading");
    input.seekg(0, std::ios::end);
    const auto size = input.tellg();
    if (size < 0) fail(path, "cannot determine the file size");
    input.seekg(0, std::ios::beg);
    std::vector<unsigned char> bytes(static_cast<std::size_t>(size));
    if (!bytes.empty() && !input.read(reinterpret_cast<char*>(bytes.data()), size))
        fail(path, "truncated while reading");
    return bytes;
}

float sampleAt(const unsigned char* base, int format, int bits) {
    if (format == 3 && bits == 32) {
        float value = 0.0F;
        std::memcpy(&value, base, sizeof(value));
        return std::clamp(value, -1.0F, 1.0F);
    }
    switch (bits) {
    case 8:
        return (static_cast<float>(*base) - 128.0F) / 128.0F;
    case 16: {
        std::int16_t value = 0;
        std::memcpy(&value, base, sizeof(value));
        return static_cast<float>(value) / 32768.0F;
    }
    case 24: {
        const std::int32_t raw = static_cast<std::int32_t>(base[0]) |
                                 (static_cast<std::int32_t>(base[1]) << 8) |
                                 (static_cast<std::int32_t>(base[2]) << 16);
        const std::int32_t sign = raw & 0x800000 ? raw | ~0xFFFFFF : raw;
        return static_cast<float>(sign) / 8388608.0F;
    }
    case 32: {
        std::int32_t value = 0;
        std::memcpy(&value, base, sizeof(value));
        return static_cast<float>(static_cast<double>(value) / 2147483648.0);
    }
    default:
        return 0.0F;
    }
}

/// Decodes every frame of one Ogg file. `collect == false` keeps no samples, which is what the
/// audit wants: 47 tracks would otherwise cost a few hundred megabytes at once.
template <bool Collect>
DecodedAudio decodeOgg(const std::filesystem::path& path) {
    const auto bytes = readBytes(path);
    if (bytes.size() > static_cast<std::size_t>(std::numeric_limits<int>::max()))
        fail(path, "file is too large for stb_vorbis");
    int error = 0;
    stb_vorbis* decoder = stb_vorbis_open_memory(bytes.data(), static_cast<int>(bytes.size()), &error,
                                                 nullptr);
    if (decoder == nullptr)
        fail(path, "stb_vorbis_open_memory failed (error " + std::to_string(error) + ")");
    const stb_vorbis_info info = stb_vorbis_get_info(decoder);
    DecodedAudio result;
    result.sampleRate = static_cast<int>(info.sample_rate);
    result.channels = static_cast<int>(info.channels);
    std::uint64_t frames = 0;
    for (;;) {
        int channels = 0;
        float** frame = nullptr;
        const int produced = stb_vorbis_get_frame_float(decoder, &channels, &frame);
        if (produced <= 0 || channels <= 0) break;
        frames += static_cast<std::uint64_t>(produced);
        if constexpr (Collect) {
            const int outChannels = std::min(channels, 2);
            // Grow geometrically. Reserving the exact needed size on every frame reallocates the
            // whole buffer once per packet, which turns a 15 M-float BGM decode into an O(n^2)
            // copy: measured 83 s for frontyard_loop before this guard, 1.5 s after.
            const std::size_t needed = result.samples.size() +
                                       static_cast<std::size_t>(produced) *
                                           static_cast<std::size_t>(outChannels);
            if (result.samples.capacity() < needed)
                result.samples.reserve(std::max(needed, result.samples.capacity() * 2));
            for (int i = 0; i < produced; ++i)
                for (int c = 0; c < outChannels; ++c) result.samples.push_back(frame[c][i]);
        }
    }
    stb_vorbis_close(decoder);
    result.frames = frames;
    result.seconds = result.sampleRate > 0
                         ? static_cast<double>(frames) / static_cast<double>(result.sampleRate)
                         : 0.0;
    return result;
}

} // namespace

bool audioFormatDecodable(const std::string& format) {
    return format == "wav" || format == "ogg" || format == "mp3";
}

DecodedAudio decodeWavFile(const std::filesystem::path& path) {
    const auto bytes = readBytes(path);
    const WavFormat header = readWavHeader(path);
    const auto bytesPerSample = static_cast<std::size_t>((header.bitsPerSample + 7) / 8);
    const auto bytesPerFrame = bytesPerSample * static_cast<std::size_t>(header.channels);
    if (bytesPerFrame == 0) fail(path, "header declares a zero-sized frame");
    if (header.dataOffset > bytes.size()) fail(path, "`data` offset is past the end of the file");
    const std::size_t available = bytes.size() - header.dataOffset;
    const auto usable = static_cast<std::size_t>(
        std::min<std::uint64_t>(header.dataBytes, static_cast<std::uint64_t>(available)));
    DecodedAudio audio;
    audio.sampleRate = header.sampleRate;
    audio.channels = header.channels;
    audio.frames = usable / bytesPerFrame;
    audio.seconds = static_cast<double>(audio.frames) / static_cast<double>(header.sampleRate);
    const auto outChannels = static_cast<int>(std::min(header.channels, 2));
    audio.samples.resize(static_cast<std::size_t>(audio.frames) * static_cast<std::size_t>(outChannels));
    for (std::uint64_t frame = 0; frame < audio.frames; ++frame) {
        const unsigned char* base = bytes.data() + header.dataOffset +
                                    static_cast<std::size_t>(frame) * bytesPerFrame;
        for (int c = 0; c < outChannels; ++c)
            audio.samples[static_cast<std::size_t>(frame) * static_cast<std::size_t>(outChannels) +
                          static_cast<std::size_t>(c)] =
                sampleAt(base + static_cast<std::size_t>(c) * bytesPerSample, header.audioFormat,
                         header.bitsPerSample);
    }
    return audio;
}

DecodedAudio decodeOggFile(const std::filesystem::path& path) {
    return decodeOgg<true>(path);
}

/// MP3 through the vendored minimp3. Same shape as `decodeOgg`: `Collect == false` counts frames
/// and returns no samples, so the audit never holds 267 740 stereo frames for `ui_open` in memory.
template <bool Collect> DecodedAudio decodeMp3(const std::filesystem::path& path) {
    const auto bytes = readBytes(path);
    if (bytes.empty()) fail(path, "file is empty");
    mp3dec_ex_t decoder;
    if (mp3dec_ex_open_buf(&decoder, bytes.data(), bytes.size(), MP3D_SEEK_TO_SAMPLE) != 0)
        fail(path, "minimp3 refused the stream (no MPEG frame header)");
    DecodedAudio result;
    result.sampleRate = decoder.info.hz;
    result.channels = decoder.info.channels;
    const auto channels = static_cast<std::size_t>(result.channels > 0 ? result.channels : 1);
    std::vector<float> chunk(4096 * channels, 0.0F);
    std::uint64_t frames = 0;
    for (;;) {
        const std::size_t read = mp3dec_ex_read(&decoder, chunk.data(), chunk.size());
        if (read == 0) break;
        const std::size_t whole = read / channels; // a partial frame is not a frame
        if (whole == 0) break;
        if (Collect) {
            const std::size_t needed =
                (static_cast<std::size_t>(frames) + whole) * channels;
            if (result.samples.size() < needed) {
                // Doubling, not exact sizing: an exact reserve per chunk is the O(n^2) trap the OGG
                // path had (`frontyard_loop` went from 2.6 s to 83 s because of it).
                const std::size_t grown = std::max(needed, result.samples.size() * 2);
                result.samples.reserve(grown);
            }
            result.samples.insert(result.samples.end(), chunk.begin(),
                                  chunk.begin() + static_cast<std::ptrdiff_t>(whole * channels));
        }
        frames += whole;
    }
    mp3dec_ex_close(&decoder);
    result.frames = frames;
    result.seconds = result.sampleRate > 0
                         ? static_cast<double>(frames) / static_cast<double>(result.sampleRate)
                         : 0.0;
    return result;
}

DecodedAudio decodeMp3File(const std::filesystem::path& path) {
    return decodeMp3<true>(path);
}

AudioProbe probeAudioFile(const std::filesystem::path& path) {
    AudioProbe probe;
    probe.format = extensionOf(path);
    try {
        if (probe.format == "wav") {
            const WavFormat header = readWavHeader(path);
            probe.decoded = true;
            probe.frames = header.frames;
            probe.seconds = header.seconds;
            probe.sampleRate = header.sampleRate;
            probe.channels = header.channels;
        } else if (probe.format == "ogg") {
            const DecodedAudio audio = decodeOgg<false>(path);
            probe.decoded = audio.frames > 0;
            probe.frames = audio.frames;
            probe.seconds = audio.seconds;
            probe.sampleRate = audio.sampleRate;
            probe.channels = audio.channels;
            if (!probe.decoded) probe.error = "no decodable frame";
        } else if (probe.format == "mp3") {
            const DecodedAudio audio = decodeMp3<false>(path);
            probe.decoded = audio.frames > 0;
            probe.frames = audio.frames;
            probe.seconds = audio.seconds;
            probe.sampleRate = audio.sampleRate;
            probe.channels = audio.channels;
            if (!probe.decoded) probe.error = "no decodable frame";
        } else {
            probe.error = "unsupported format `" + probe.format + "`";
        }
    } catch (const std::exception& error) {
        probe.decoded = false;
        probe.frames = 0;
        probe.seconds = 0.0;
        probe.error = error.what();
    }
    return probe;
}

} // namespace pvz
