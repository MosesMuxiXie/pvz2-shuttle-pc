#pragma once
// Art resolver: maps a content `art` key or a pack `popAnim` onto a DragonBones folder on disk.
// Deliberately free of SDL so `--art-audit` and its test run in the AuditOnly build too.
// A folder that cannot be found is an ordinary outcome (empty result), never an exception.
#include "catalog.hpp"
#include <cstddef>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

namespace pvz {

/// One extracted SHUTTLE actor, as written by the OBB extractor's `index.json` `items[]`.
struct ShuttleArt {
    std::string base;
    std::string popAnim;  // "POPANIM_PLANT_SUNFLOWER"; empty when the extractor matched nothing
    std::string rawDir;   // `dir` exactly as the index wrote it
    std::string dir;      // usable path relative to the asset root; empty if the folder is gone
    int images = 0;
    int animations = 0;
    int rects = 0;

    bool usable() const { return !dir.empty(); }
};

/// `assets/db/shuttle/index.json`. `present == false` means the extractor has not written the
/// table yet (or the asset root is a test fixture): the resolver then reports no SHUTTLE art
/// instead of failing. `loaded` only needs a parseable file with a non-empty `items[]`, because
/// the extractor keeps appending while it runs (`progress.done` only ever grows).
struct ShuttleArtIndex {
    bool present = false;
    bool loaded = false;
    std::string error;
    std::vector<ShuttleArt> items;  // every listed base, usable or not
    /// Extractor counters, copied verbatim so the audit can quote them.
    std::size_t basesTotal = 0, ok = 0, failed = 0, pending = 0, popAnimMatched = 0,
                popAnimNull = 0;
    std::size_t failures = 0;
    std::size_t progressDone = 0, progressTotal = 0;
    Json counts = Json::object();    // the index's `counts`, verbatim
    Json progress = Json::object();  // the index's `progress`, verbatim

    /// Every listed base whose `popAnim` matches, in file order. One popAnim can map to several
    /// bases (same actor at different resolutions or as a variant), so callers get the list.
    std::vector<const ShuttleArt*> candidates(std::string_view popAnim) const;
    /// The first candidate whose folder actually exists, i.e. the one the view should draw.
    const ShuttleArt* byPopAnim(std::string_view popAnim) const;
    const ShuttleArt* byBase(std::string_view base) const;
    /// How many listed bases resolve to a folder on disk.
    std::size_t usable() const;
};

/// Reads `<assetRoot>/db/shuttle/index.json`. Never throws.
ShuttleArtIndex loadShuttleIndex(const std::filesystem::path& assetRoot);

enum class ArtSource { none, web, shuttle };

struct ArtResolution {
    ArtSource source = ArtSource::none;
    std::string dir;  // relative to the asset root; empty when nothing matched
    const ShuttleArt* shuttle = nullptr;

    bool hit() const { return source != ArtSource::none; }
};

/// Tries the legacy web export (`db/<art>`) first, then the SHUTTLE index by `popAnim`.
/// A hit needs the folder's `skeleton.json`: an empty directory is not artwork.
ArtResolution resolveArt(const std::filesystem::path& assetRoot, const ShuttleArtIndex& index,
                         const std::string& art, const std::string& popAnim);

/// The asset root that belongs to a content directory: an upward probe of the layouts this
/// repository and an installed build use. Empty when nothing carries the lawn.
std::filesystem::path locateAssetRoot(const std::filesystem::path& contentRoot);

/// Counters for one cohort (content plants, pack zombies, ...).
struct ArtCohort {
    int total = 0;
    int webHit = 0;
    int shuttleHit = 0;
    int missing = 0;
};

struct ArtAudit {
    ArtCohort contentPlants;
    ArtCohort contentZombies;
    ArtCohort packPlants;
    ArtCohort packZombies;
    std::size_t shuttleEntries = 0;  // listed bases, usable or not
    std::size_t shuttleFailures = 0;
    bool indexPresent = false;
    bool indexLoaded = false;
    std::string indexError;
    std::filesystem::path assetRoot;
    Json counts = Json::object();    // the index's `counts`, copied verbatim
    Json progress = Json::object();  // the index's `progress`, copied verbatim

    /// `{contentPlants:{...},...,shuttleIndex:N,shuttleFailures:N,...}` - the `--art-audit` line.
    Json json() const;
    /// 0 every actor resolved, 1 some missing (still runnable), 2 the SHUTTLE index is
    /// missing or unusable.
    int exitCode() const;
};

/// Walks the catalog: the shipped content always, the property-sheet pack when it is loaded.
ArtAudit auditArt(const Catalog& catalog, const std::filesystem::path& assetRoot);

} // namespace pvz
