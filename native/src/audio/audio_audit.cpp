#include "audio/audio_audit.hpp"

#include <cmath>
#include <iomanip>
#include <sstream>

#include "audio/audio_decode.hpp"

namespace pvz {
namespace {

double roundMillis(double seconds) { return std::round(seconds * 1000.0) / 1000.0; }

const char* kindName(SoundKind kind) {
    switch (kind) {
    case SoundKind::bgm: return "bgm";
    case SoundKind::sfx: return "sfx";
    case SoundKind::obb: return "obb";
    }
    return "sfx";
}

} // namespace

nlohmann::json AudioAudit::json() const {
    nlohmann::json out;
    out["sounds"] = catalog.sounds.size();
    out["bgm"] = catalog.count(SoundKind::bgm);
    out["sfx"] = catalog.count(SoundKind::sfx);
    out["decoded"] = decoded;
    out["seconds"] = roundMillis(seconds);
    out["missing"] = missing;
    out["deviceAvailable"] = deviceAvailable;
    return out;
}

int AudioAudit::exitCode() const { return missing.empty() ? 0 : 1; }

std::string AudioAudit::warning() const {
    std::string message;
    if (catalog.missingFiles != 0)
        message += "warning: " + std::to_string(catalog.missingFiles) +
                   " catalog file(s) are not on disk; see missing[]\n";
    if (!packs.error.empty()) message += "warning: pack cross-check unavailable: " + packs.error + "\n";
    return message;
}

std::string AudioAudit::text() const {
    std::ostringstream out;
    out << catalog.text() << '\n';
    out << "decoded " << decoded << '/' << files.size() << " file(s), " << std::fixed
        << std::setprecision(3) << seconds << " s of audio\n";
    for (const auto& file : files) {
        out << "  " << std::setw(28) << std::left << file.name << ' ' << std::setw(4)
            << file.format << ' ';
        if (file.decoded)
            out << std::setw(7) << file.frames << " frames " << std::fixed
                << std::setprecision(3) << std::setw(9) << file.seconds << " s";
        else
            out << "-";
        if (!file.error.empty()) out << "  [" << file.error << ']';
        out << '\n';
    }
    out << packs.text() << '\n';
    out << "deviceAvailable: " << (deviceAvailable ? "true" : "false") << '\n';
    return out.str();
}

AudioAudit auditAudio(const AudioCatalog& catalog, bool deviceAvailable, PackCrossCheck packs) {
    AudioAudit audit;
    audit.catalog = catalog;
    audit.deviceAvailable = deviceAvailable;
    audit.packs = std::move(packs);
    for (const auto& sound : catalog.sounds) {
        AudioFileReport report;
        report.name = sound.name;
        report.file = sound.file;
        report.format = sound.format;
        if (!sound.present) {
            report.error = "missing file";
            audit.files.push_back(report);
            audit.missing.push_back({{"name", sound.name},
                                     {"file", sound.file},
                                     {"kind", kindName(sound.kind)}});
            continue;
        }
        const auto probe = probeAudioFile(catalog.assetRoot / sound.file);
        report.decoded = probe.decoded;
        report.frames = probe.frames;
        report.seconds = probe.seconds;
        report.error = probe.error;
        if (probe.decoded) {
            ++audit.decoded;
            audit.seconds += probe.seconds;
        }
        audit.files.push_back(report);
    }
    audit.missing = audit.missing.is_array() ? audit.missing : nlohmann::json::array();
    return audit;
}

} // namespace pvz
