#pragma once
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "audio/audio_catalog.hpp"
#include "audio/event_map.hpp"

// The `--audio-audit` payload. It has to work in the audit build, which has no SDL at all, so the
// only thing that changes there is `deviceAvailable`; every per-file number comes from the same
// decoder the desktop backend uses.
namespace pvz {

struct AudioFileReport {
    std::string name;
    std::string file;
    std::string format;
    bool decoded = false;
    std::uint64_t frames = 0;
    double seconds = 0.0;
    std::string error;
};

struct AudioAudit {
    AudioCatalog catalog;
    std::vector<AudioFileReport> files;
    PackCrossCheck packs;
    bool deviceAvailable = false;
    std::size_t decoded = 0;
    double seconds = 0.0;
    nlohmann::json missing = nlohmann::json::array();

    /// Exactly {sounds, bgm, sfx, decoded, seconds, missing[], deviceAvailable}.
    nlohmann::json json() const;
    int exitCode() const; ///< 0 when nothing is missing, 1 otherwise
    /// Multi-line human summary: catalog totals, per-file frames/seconds, pack hit rates.
    std::string text() const;
    /// One line for stderr when the catalog or the packs could not be read completely.
    std::string warning() const;
};

AudioAudit auditAudio(const AudioCatalog& catalog, bool deviceAvailable,
                      PackCrossCheck packs = {});

} // namespace pvz
