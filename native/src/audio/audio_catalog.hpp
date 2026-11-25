#pragma once
#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

// SDL-free half of the audio layer. `AudioCatalog` only reads the two manifests that the OBB
// extractor leaves in `assets/audio/`, plus a directory scan for files the manifest forgot
// (8 of the 13 shipped `.wav` sfx are not listed in `audio_report.json`). Decoding lives in
// `audio_decode.hpp` so the audit build never has to link SDL, and playback lives in
// `audio_mixer.hpp` / `audio_backend.cpp`.
namespace pvz {

/// Where a `Sound` came from.
/// - `report`: listed in `audio/audio_report.json` (the extractor's manifest).
/// - `scan`:   present in `audio/` but missing from that manifest (found by the directory scan).
/// - `obb`:    an extracted OBB track, timed by `audio/obb/durations.json`.
enum class SoundSource { report, scan, obb };

/// The three groups the audit reports separately.
/// - `bgm`: a top-level `.ogg` (26 world intro/loop tracks plus menu/victory/defeat).
/// - `sfx`: a top-level `.wav` or `.mp3` (13 + 5 = 18).
/// - `obb`: an OBB music track under `audio/obb/` (21, timed by `durations.json`).
enum class SoundKind { bgm, sfx, obb };

struct Sound {
    std::string name;    ///< stem the event map and the CLI use: "plant", "beach_loop".
    std::string file;    ///< path relative to the asset root, POSIX separators: "audio/plant.wav".
    std::string format;  ///< lower-case extension: "wav", "mp3", "ogg".
    double seconds = 0.0;  ///< declared length (report `duration` / obb table); 0 when unknown.
    std::uintmax_t bytes = 0;
    std::string source;  ///< "report" | "scan" | "obb" (see `SoundSource`).
    SoundKind kind = SoundKind::sfx;
    bool present = true;  ///< false when the manifest names a file that is not on disk.
};

/// The PCM facts a `.wav` header carries. `readWavHeader` never decodes samples: the audit only
/// needs frames and seconds, and the desktop backend hands the samples to `SDL_LoadWAV`.
struct WavFormat {
    int audioFormat = 0;  ///< 1 = integer PCM, 3 = IEEE float.
    int channels = 0;
    int sampleRate = 0;
    int bitsPerSample = 0;
    std::uint32_t dataOffset = 0;
    std::uint32_t dataBytes = 0;
    std::uint64_t frames = 0;
    double seconds = 0.0;
};

struct AudioCatalog {
    std::filesystem::path assetRoot;  ///< `<root>/PvZ2SHUTTLE/assets`
    std::filesystem::path audioDir;   ///< `<assetRoot>/audio`
    std::vector<Sound> sounds;        ///< report entries, then scanned files, then obb tracks.
    std::size_t reportEntries = 0;
    std::size_t scannedEntries = 0;
    std::size_t obbEntries = 0;
    std::size_t missingFiles = 0;

    const Sound* find(std::string_view name) const;
    std::size_t count(SoundKind kind) const;
    /// `audio: 26 bgm, 18 sfx, 21 obb (65 sounds; 10 report, 34 scan, 21 obb)`
    std::string text() const;

    /// Reads `<assetRoot>/audio/audio_report.json` and `<assetRoot>/audio/obb/durations.json`,
    /// then scans `audio/` for files the manifest omits. Structural problems throw
    /// `audio catalog: <path>: <what>`; a manifest entry whose file is absent is kept with
    /// `present = false` so `--audio-audit` can report it instead of dying.
    static AudioCatalog load(const std::filesystem::path& assetRoot);
};

/// UTF-8 view of a path, independent of `pvz::pathUtf8` so `pvz_audio_core` does not have to
/// link the whole catalog library.
std::string audioPathUtf8(const std::filesystem::path& path);

/// Parses a RIFF/WAVE header and the `fmt `/`data` chunks. Throws
/// `audio catalog: <path>: <what>` for a missing, truncated or non-PCM file.
WavFormat readWavHeader(const std::filesystem::path& path);

} // namespace pvz
