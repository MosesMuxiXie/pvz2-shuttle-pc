#include "audio/audio_catalog.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <nlohmann/json.hpp>
#include <stdexcept>
#include <system_error>

namespace pvz {
namespace {

using Json = nlohmann::json;

[[noreturn]] void fail(const std::filesystem::path& path, const std::string& what) {
    throw std::runtime_error("audio catalog: " + audioPathUtf8(path) + ": " + what);
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

std::string stemOf(const std::filesystem::path& path) { return audioPathUtf8(path.stem()); }

std::string readTextFile(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) fail(path, "cannot open for reading");
    std::string text((std::istreambuf_iterator<char>(input)), std::istreambuf_iterator<char>());
    if (text.empty()) fail(path, "file is empty");
    return text;
}

Json parseJsonFile(const std::filesystem::path& path) {
    const std::string text = readTextFile(path);
    try {
        return Json::parse(text);
    } catch (const Json::exception& error) {
        fail(path, std::string{"invalid JSON: "} + error.what());
    }
}

/// A manifest entry must name a file inside `audio/`. Anything that walks out of the directory
/// (or names an absolute path) is a broken manifest, not a sound.
void requireBareFileName(const std::filesystem::path& manifest, const std::string& file) {
    if (file.empty()) fail(manifest, "manifest entry with an empty `file`");
    if (file.find('/') != std::string::npos || file.find('\\') != std::string::npos)
        fail(manifest, "manifest entry `file` must be a bare file name, got: " + file);
    if (file == "." || file == ".." || file.rfind("..", 0) == 0)
        fail(manifest, "manifest entry `file` escapes the audio directory: " + file);
}

std::uint32_t readU32(std::istream& input, const std::filesystem::path& path) {
    unsigned char bytes[4] = {};
    if (!input.read(reinterpret_cast<char*>(bytes), 4)) fail(path, "truncated header");
    return static_cast<std::uint32_t>(bytes[0]) | (static_cast<std::uint32_t>(bytes[1]) << 8U) |
           (static_cast<std::uint32_t>(bytes[2]) << 16U) | (static_cast<std::uint32_t>(bytes[3]) << 24U);
}

std::uint16_t readU16(std::istream& input, const std::filesystem::path& path) {
    unsigned char bytes[2] = {};
    if (!input.read(reinterpret_cast<char*>(bytes), 2)) fail(path, "truncated header");
    return static_cast<std::uint16_t>(bytes[0]) | static_cast<std::uint16_t>(bytes[1] << 8U);
}

/// The shipped layout is what decides the group: top-level `.ogg` are the world/menu tracks,
/// top-level `.wav`/`.mp3` are the 18 sfx, and everything under `audio/obb/` is OBB music.
void classify(Sound& sound) {
    if (sound.source == "obb") {
        sound.kind = SoundKind::obb;
        return;
    }
    sound.kind = sound.format == "ogg" ? SoundKind::bgm : SoundKind::sfx;
}

struct Builder {
    std::filesystem::path root;
    std::filesystem::path audioDir;
    std::vector<Sound> sounds;
    std::map<std::string, std::size_t> byName;
    std::map<std::string, std::size_t> byFile;

    void add(Sound sound, const std::filesystem::path& manifest) {
        const auto nameIt = byName.find(sound.name);
        if (nameIt != byName.end())
            fail(manifest, "duplicate sound name `" + sound.name + "` (also " +
                               sounds[nameIt->second].file + ")");
        if (!sound.file.empty() && byFile.count(sound.file))
            fail(manifest, "duplicate sound file `" + sound.file + "`");
        byName.emplace(sound.name, sounds.size());
        if (!sound.file.empty()) byFile.emplace(sound.file, sounds.size());
        sounds.push_back(std::move(sound));
    }
};

} // namespace

std::string audioPathUtf8(const std::filesystem::path& path) {
    const auto text = path.u8string();
    return std::string(reinterpret_cast<const char*>(text.data()), text.size());
}

WavFormat readWavHeader(const std::filesystem::path& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) fail(path, "cannot open for reading");
    char riff[4] = {};
    if (!input.read(riff, 4) || std::string(riff, 4) != "RIFF") fail(path, "not a RIFF container");
    (void)readU32(input, path); // RIFF size: untrusted in several shipped files.
    char wave[4] = {};
    if (!input.read(wave, 4) || std::string(wave, 4) != "WAVE") fail(path, "not a WAVE container");

    WavFormat format;
    bool haveFormat = false;
    bool haveData = false;
    while (input && !(haveFormat && haveData)) {
        char id[4] = {};
        if (!input.read(id, 4)) break;
        const std::uint32_t size = readU32(input, path);
        const std::string chunk(id, 4);
        if (chunk == "fmt ") {
            if (size < 16) fail(path, "`fmt ` chunk is shorter than 16 bytes");
            format.audioFormat = static_cast<int>(readU16(input, path));
            format.channels = static_cast<int>(readU16(input, path));
            format.sampleRate = static_cast<int>(readU32(input, path));
            (void)readU32(input, path); // byte rate
            (void)readU16(input, path); // block align
            format.bitsPerSample = static_cast<int>(readU16(input, path));
            if (size > 16) input.seekg(static_cast<std::streamoff>(size - 16), std::ios::cur);
            haveFormat = true;
        } else if (chunk == "data") {
            format.dataOffset = static_cast<std::uint32_t>(input.tellg());
            format.dataBytes = size;
            haveData = true;
            input.seekg(static_cast<std::streamoff>(size), std::ios::cur);
        } else {
            input.seekg(static_cast<std::streamoff>(size), std::ios::cur);
        }
        if (size % 2 != 0) input.seekg(1, std::ios::cur); // RIFF chunks are word aligned.
    }
    if (!haveFormat) fail(path, "no `fmt ` chunk");
    if (!haveData) fail(path, "no `data` chunk");
    if (format.channels <= 0) fail(path, "`fmt ` declares no channels");
    if (format.sampleRate <= 0) fail(path, "`fmt ` declares no sample rate");
    if (format.bitsPerSample <= 0) fail(path, "`fmt ` declares no sample width");
    if (format.audioFormat != 1 && format.audioFormat != 3)
        fail(path, "unsupported WAV encoding " + std::to_string(format.audioFormat) +
                       " (only PCM and IEEE float are decoded)");
    const auto bytesPerFrame = static_cast<std::uint64_t>(format.channels) *
                               static_cast<std::uint64_t>(format.bitsPerSample + 7) / 8U;
    if (bytesPerFrame == 0) fail(path, "`fmt ` declares a zero-sized frame");
    format.frames = format.dataBytes / bytesPerFrame;
    format.seconds = static_cast<double>(format.frames) / static_cast<double>(format.sampleRate);
    return format;
}

const Sound* AudioCatalog::find(std::string_view name) const {
    for (const auto& sound : sounds)
        if (sound.name == name) return &sound;
    return nullptr;
}

std::size_t AudioCatalog::count(SoundKind kind) const {
    return static_cast<std::size_t>(std::count_if(
        sounds.begin(), sounds.end(), [kind](const Sound& sound) { return sound.kind == kind; }));
}

std::string AudioCatalog::text() const {
    std::string text = "audio: " + std::to_string(count(SoundKind::bgm)) + " bgm, " +
                       std::to_string(count(SoundKind::sfx)) + " sfx, " +
                       std::to_string(count(SoundKind::obb)) + " obb (" +
                       std::to_string(sounds.size()) + " sounds; " + std::to_string(reportEntries) +
                       " report, " + std::to_string(scannedEntries) + " scan, " +
                       std::to_string(obbEntries) + " obb)";
    if (missingFiles != 0) text += "; " + std::to_string(missingFiles) + " missing file(s)";
    return text;
}

AudioCatalog AudioCatalog::load(const std::filesystem::path& assetRoot) {
    Builder builder;
    builder.root = assetRoot;
    builder.audioDir = assetRoot / "audio";
    std::error_code ec;
    if (!std::filesystem::is_directory(builder.audioDir, ec))
        fail(builder.audioDir, "no such audio directory");

    AudioCatalog catalog;
    // 1. The extractor's manifest. 10 of the 23 top-level sfx/bgm files are listed there.
    const auto reportPath = builder.audioDir / "audio_report.json";
    if (!std::filesystem::is_regular_file(reportPath, ec))
        fail(reportPath, "missing `audio_report.json`");
    const auto report = parseJsonFile(reportPath);
    if (!report.is_array()) fail(reportPath, "expected a JSON array of sound entries");
    for (const auto& entry : report) {
        if (!entry.is_object()) fail(reportPath, "expected a JSON object per sound entry");
        if (!entry.contains("name") || !entry["name"].is_string())
            fail(reportPath, "entry without a string `name`");
        if (!entry.contains("file") || !entry["file"].is_string())
            fail(reportPath, "entry `" + entry["name"].get<std::string>() + "` without a string `file`");
        Sound sound;
        sound.name = entry["name"].get<std::string>();
        const std::string file = entry["file"].get<std::string>();
        requireBareFileName(reportPath, file);
        sound.file = "audio/" + file;
        const auto onDisk = builder.audioDir / file;
        sound.present = std::filesystem::is_regular_file(onDisk, ec);
        sound.bytes = sound.present ? std::filesystem::file_size(onDisk, ec) : 0;
        sound.format = entry.contains("fmt") && entry["fmt"].is_string()
                           ? lower(entry["fmt"].get<std::string>())
                           : extensionOf(onDisk);
        sound.seconds = entry.contains("duration") && entry["duration"].is_number()
                            ? entry["duration"].get<double>()
                            : 0.0;
        sound.source = "report";
        classify(sound);
        builder.add(std::move(sound), reportPath);
    }
    catalog.reportEntries = builder.sounds.size();

    // 2. Files the manifest forgot: all 26 top-level world tracks and 8 of the 13 wav sfx.
    std::vector<std::filesystem::directory_entry> scanned;
    for (const auto& entry : std::filesystem::directory_iterator(builder.audioDir, ec)) {
        if (!entry.is_regular_file(ec)) continue;
        const std::string ext = extensionOf(entry.path());
        if (ext != "wav" && ext != "mp3" && ext != "ogg") continue;
        scanned.push_back(entry);
    }
    std::sort(scanned.begin(), scanned.end(), [](const auto& left, const auto& right) {
        return left.path().filename() < right.path().filename();
    });
    for (const auto& entry : scanned) {
        Sound sound;
        sound.name = stemOf(entry.path());
        sound.file = "audio/" + audioPathUtf8(entry.path().filename());
        if (builder.byFile.count(sound.file)) continue;
        sound.format = extensionOf(entry.path());
        sound.bytes = entry.file_size(ec);
        sound.present = true;
        sound.source = "scan";
        // A `.wav` carries its own length; `.ogg` and `.mp3` are measured by the audit decoder.
        if (sound.format == "wav") {
            try {
                sound.seconds = readWavHeader(entry.path()).seconds;
            } catch (const std::exception&) {
                sound.seconds = 0.0; // broken wav: the audit probe reports the parse error.
            }
        }
        classify(sound);
        builder.add(std::move(sound), entry.path());
    }
    catalog.scannedEntries = builder.sounds.size() - catalog.reportEntries;

    // 3. The extracted OBB music set, timed by `durations.json`.
    const auto obbDir = builder.audioDir / "obb";
    const auto durationsPath = obbDir / "durations.json";
    if (!std::filesystem::is_regular_file(durationsPath, ec))
        fail(durationsPath, "missing `durations.json`");
    const auto durations = parseJsonFile(durationsPath);
    if (!durations.is_object()) fail(durationsPath, "expected a JSON object of file -> seconds");
    std::vector<std::pair<std::string, double>> tracks;
    for (const auto& item : durations.items()) {
        if (!item.value().is_number())
            fail(durationsPath, "duration of `" + item.key() + "` is not a number");
        tracks.emplace_back(item.key(), item.value().get<double>());
    }
    std::sort(tracks.begin(), tracks.end());
    for (const auto& [file, seconds] : tracks) {
        requireBareFileName(durationsPath, file);
        Sound sound;
        sound.name = stemOf(std::filesystem::path(file));
        sound.file = "audio/obb/" + file;
        sound.format = extensionOf(std::filesystem::path(file));
        sound.seconds = seconds;
        sound.present = std::filesystem::is_regular_file(obbDir / file, ec);
        sound.bytes = sound.present ? std::filesystem::file_size(obbDir / file, ec) : 0;
        sound.source = "obb";
        classify(sound);
        builder.add(std::move(sound), durationsPath);
    }
    // A track that `durations.json` does not time still belongs to the catalog.
    std::vector<std::filesystem::directory_entry> untimed;
    for (const auto& entry : std::filesystem::directory_iterator(obbDir, ec)) {
        if (!entry.is_regular_file(ec)) continue;
        if (extensionOf(entry.path()) != "ogg") continue;
        untimed.push_back(entry);
    }
    std::sort(untimed.begin(), untimed.end(), [](const auto& left, const auto& right) {
        return left.path().filename() < right.path().filename();
    });
    for (const auto& entry : untimed) {
        Sound sound;
        sound.name = stemOf(entry.path());
        sound.file = "audio/obb/" + audioPathUtf8(entry.path().filename());
        if (builder.byFile.count(sound.file)) continue;
        sound.format = "ogg";
        sound.bytes = entry.file_size(ec);
        sound.present = true;
        sound.source = "obb";
        classify(sound);
        builder.add(std::move(sound), entry.path());
    }
    catalog.obbEntries = builder.sounds.size() - catalog.reportEntries - catalog.scannedEntries;

    catalog.assetRoot = assetRoot;
    catalog.audioDir = builder.audioDir;
    catalog.sounds = std::move(builder.sounds);
    catalog.missingFiles = static_cast<std::size_t>(std::count_if(
        catalog.sounds.begin(), catalog.sounds.end(), [](const Sound& s) { return !s.present; }));
    return catalog;
}

} // namespace pvz
