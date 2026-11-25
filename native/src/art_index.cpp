#include "art_index.hpp"
#include "content/model.hpp"
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <system_error>
#include <utility>
#ifdef _WIN32
#include <windows.h>
#endif

namespace pvz {
namespace {
/// Files a DragonBones folder needs before the view may treat it as usable artwork.
bool looksLikeArtwork(const std::filesystem::path& dir) {
    std::error_code ec;
    if (!std::filesystem::is_directory(dir, ec))
        return false;
    return std::filesystem::is_regular_file(dir / "skeleton.json", ec);
}
/// The extractor writes `dir` relative to `assets/`, older notes call it relative to
/// `db/shuttle/`. Accept both (plus a bare base name) and return the first candidate that
/// carries a skeleton, so the index layout can change without breaking the resolver.
std::string normaliseDir(const std::filesystem::path& assetRoot, const std::string& raw,
                         const std::string& base) {
    std::vector<std::string> candidates;
    if (!raw.empty()) {
        candidates.push_back(raw);
        candidates.push_back("db/" + raw);
        candidates.push_back("db/shuttle/" + raw);
    }
    if (!base.empty()) {
        candidates.push_back("db/shuttle/shuttle_" + base);
        candidates.push_back("db/shuttle/" + base);
    }
    for (const auto& candidate : candidates) {
        const auto rel = std::filesystem::path(candidate).lexically_normal();
        if (looksLikeArtwork(assetRoot / rel))
            return rel.generic_string();
    }
    return {};
}
std::string asString(const Json& object, const char* key) {
    const auto found = object.find(key);
    return found == object.end() || !found->is_string() ? std::string{} : found->get<std::string>();
}
int asInt(const Json& object, const char* key) {
    const auto found = object.find(key);
    if (found == object.end())
        return 0;
    if (found->is_number_integer())
        return found->get<int>();
    if (found->is_array())
        return static_cast<int>(found->size());
    return 0;
}
std::size_t asSize(const Json& object, const char* key) {
    const auto found = object.find(key);
    if (found == object.end())
        return 0;
    if (found->is_number_integer()) {
        const auto value = found->get<long long>();
        return value > 0 ? static_cast<std::size_t>(value) : 0;
    }
    return 0;
}
Json copiedObject(const Json& document, const char* key) {
    const auto found = document.find(key);
    return found != document.end() && found->is_object() ? *found : Json::object();
}
} // namespace

std::vector<const ShuttleArt*> ShuttleArtIndex::candidates(std::string_view popAnim) const {
    std::vector<const ShuttleArt*> matches;
    if (popAnim.empty())
        return matches;
    for (const auto& art : items)
        if (art.popAnim == popAnim)
            matches.push_back(&art);
    return matches;
}

const ShuttleArt* ShuttleArtIndex::byPopAnim(std::string_view popAnim) const {
    // Several bases can carry one popAnim (resolutions/variants): the first folder that exists
    // wins, which is why the entry list keeps the unusable ones around.
    for (const auto* art : candidates(popAnim))
        if (art->usable())
            return art;
    return nullptr;
}

const ShuttleArt* ShuttleArtIndex::byBase(std::string_view base) const {
    if (base.empty())
        return nullptr;
    const auto found = std::find_if(items.begin(), items.end(),
                                    [base](const ShuttleArt& art) { return art.base == base; });
    return found == items.end() ? nullptr : &*found;
}

std::size_t ShuttleArtIndex::usable() const {
    return static_cast<std::size_t>(
        std::count_if(items.begin(), items.end(), [](const ShuttleArt& art) { return art.usable(); }));
}

ShuttleArtIndex loadShuttleIndex(const std::filesystem::path& assetRoot) {
    ShuttleArtIndex index;
    const auto path = assetRoot / "db/shuttle/index.json";
    std::error_code ec;
    if (!std::filesystem::is_regular_file(path, ec)) {
        index.error = pathUtf8(path) + ": not found (no SHUTTLE artwork is installed)";
        return index;
    }
    index.present = true;
    std::ifstream stream(path);
    if (!stream) {
        index.error = pathUtf8(path) + ": cannot be read";
        return index;
    }
    Json document;
    try {
        stream >> document;
    } catch (const std::exception& failure) {
        index.error = pathUtf8(path) + ": invalid JSON (" + failure.what() + ")";
        return index;
    }
    if (!document.is_object()) {
        index.error = pathUtf8(path) + ": expected a JSON object";
        return index;
    }
    // `items` is the shipped key; `entries` is what the first draft of this resolver expected,
    // kept so an older index still loads.
    const Json* listed = nullptr;
    for (const char* key : {"items", "entries"}) {
        const auto found = document.find(key);
        if (found != document.end() && found->is_array()) {
            listed = &*found;
            break;
        }
    }
    if (listed == nullptr) {
        index.error = pathUtf8(path) + ": no `items` array";
        return index;
    }
    if (listed->empty()) {
        // The extractor is still on its first base: the table exists but nothing can be drawn.
        index.error = pathUtf8(path) + ": `items` is empty (extraction has not produced a base yet)";
        index.counts = copiedObject(document, "counts");
        index.progress = copiedObject(document, "progress");
        return index;
    }
    for (const auto& item : *listed) {
        if (!item.is_object())
            continue;
        ShuttleArt art;
        art.base = asString(item, "base");
        art.popAnim = asString(item, "popAnim");
        art.rawDir = asString(item, "dir");
        art.dir = normaliseDir(assetRoot, art.rawDir, art.base);
        art.images = asInt(item, "images");
        art.animations = asInt(item, "animations");
        art.rects = asInt(item, "rects");
        if (art.base.empty() && art.popAnim.empty())
            continue;
        index.items.push_back(std::move(art));
    }
    if (const auto failures = document.find("failures");
        failures != document.end() && failures->is_array())
        index.failures = failures->size();
    const auto counts = copiedObject(document, "counts");
    index.basesTotal = asSize(counts, "bases_total");
    index.ok = asSize(counts, "ok");
    index.failed = asSize(counts, "failed");
    index.pending = asSize(counts, "pending");
    index.popAnimMatched = asSize(counts, "popanim_matched");
    index.popAnimNull = asSize(counts, "popanim_null");
    const auto progress = copiedObject(document, "progress");
    index.progressDone = asSize(progress, "done");
    index.progressTotal = asSize(progress, "total");
    // `pending > 0` is normal while the extractor runs: a parseable, non-empty table is enough.
    index.loaded = true;
    return index;
}

ArtResolution resolveArt(const std::filesystem::path& assetRoot, const ShuttleArtIndex& index,
                         const std::string& art, const std::string& popAnim) {
    ArtResolution resolution;
    if (!art.empty()) {
        // ① the legacy web export, e.g. "plants/SunflowerPLANT" under `db/`.
        const auto rel = std::filesystem::path("db") / std::filesystem::path(art);
        if (looksLikeArtwork(assetRoot / rel)) {
            resolution.source = ArtSource::web;
            resolution.dir = rel.lexically_normal().generic_string();
            return resolution;
        }
    }
    // ② the SHUTTLE extraction, joined on the pack's popAnim.
    if (const auto* shuttle = index.byPopAnim(popAnim); shuttle != nullptr) {
        resolution.source = ArtSource::shuttle;
        resolution.dir = shuttle->dir;
        resolution.shuttle = shuttle;
    }
    return resolution;
}

namespace {
/// S7: a zip has to run without a source checkout, so the exe's own directory is a candidate
/// (and `PVZ_ASSET_ROOT` lets a launcher point at a shared asset tree).
std::filesystem::path executableDir() {
#ifdef _WIN32
    wchar_t buffer[32768];
    const DWORD length = GetModuleFileNameW(nullptr, buffer, static_cast<DWORD>(std::size(buffer)));
    if (length == 0 || length >= std::size(buffer))
        return {};
    return std::filesystem::path(buffer, buffer + length).parent_path();
#else
    std::error_code ec;
    const auto self = std::filesystem::read_symlink("/proc/self/exe", ec);
    return ec ? std::filesystem::path{} : self.parent_path();
#endif
}
} // namespace

std::filesystem::path locateAssetRoot(const std::filesystem::path& contentRoot) {
    std::vector<std::filesystem::path> candidates;
    // 1) an explicit override wins and is used as the asset directory itself
    if (const char* override_ = std::getenv("PVZ_ASSET_ROOT"); override_ != nullptr && *override_ != '\0')
        candidates.emplace_back(override_);
    // 2) the directory holding the executable, then its parent (exe next to `assets/`)
    const auto exeDir = executableDir();
    if (!exeDir.empty()) {
        candidates.push_back(exeDir / "assets");
        candidates.push_back(exeDir);
    }
    const auto add = [&candidates](std::filesystem::path base) {
        if (base.empty())
            return;
        candidates.push_back(base / "assets");
        candidates.push_back(base / "PvZ2SHUTTLE" / "assets");
    };
    if (!contentRoot.empty()) {
        auto dir = std::filesystem::absolute(contentRoot);
        for (int level = 0; level < 5 && !dir.empty(); ++level) {
            add(dir);
            if (!dir.has_parent_path() || dir.parent_path() == dir)
                break;
            dir = dir.parent_path();
        }
    }
    add(std::filesystem::current_path());
    std::error_code ec;
    for (const auto& candidate : candidates)
        if (std::filesystem::is_regular_file(candidate / "lawn" / "frontyard.png", ec))
            return candidate;
    return {};
}

namespace {
void countOne(ArtCohort& cohort, const ArtResolution& resolution) {
    ++cohort.total;
    if (resolution.source == ArtSource::web)
        ++cohort.webHit;
    else if (resolution.source == ArtSource::shuttle)
        ++cohort.shuttleHit;
    else
        ++cohort.missing;
}
Json cohortJson(const ArtCohort& cohort) {
    return Json{{"total", cohort.total},
                {"webHit", cohort.webHit},
                {"shuttleHit", cohort.shuttleHit},
                {"missing", cohort.missing}};
}
} // namespace

Json ArtAudit::json() const {
    Json report{{"contentPlants", cohortJson(contentPlants)},
                {"contentZombies", cohortJson(contentZombies)},
                {"packPlants", cohortJson(packPlants)},
                {"packZombies", cohortJson(packZombies)},
                {"shuttleIndex", shuttleEntries},
                {"shuttleFailures", shuttleFailures},
                {"shuttleIndexLoaded", indexLoaded},
                {"shuttleIndexCounts", counts},
                {"shuttleIndexProgress", progress},
                {"assetRoot", pathUtf8(assetRoot)}};
    if (!indexError.empty())
        report["shuttleIndexError"] = indexError;
    return report;
}

int ArtAudit::exitCode() const {
    // A missing or unusable index outranks per-actor misses: without it the whole SHUTTLE layer
    // is absent, which is a different problem from "this actor has no artwork".
    if (!indexLoaded)
        return 2;
    const int missing = contentPlants.missing + contentZombies.missing + packPlants.missing +
                        packZombies.missing;
    return missing > 0 ? 1 : 0;
}

ArtAudit auditArt(const Catalog& catalog, const std::filesystem::path& assetRoot) {
    ArtAudit audit;
    audit.assetRoot = assetRoot;
    const auto index = loadShuttleIndex(assetRoot);
    audit.indexPresent = index.present;
    audit.indexLoaded = index.loaded;
    audit.indexError = index.error;
    audit.shuttleEntries = index.items.size();
    audit.shuttleFailures = index.failures;
    audit.counts = Json{{"basesTotal", index.basesTotal},
                        {"ok", index.ok},
                        {"failed", index.failed},
                        {"pending", index.pending},
                        {"popAnimMatched", index.popAnimMatched},
                        {"popAnimNull", index.popAnimNull},
                        {"usable", index.usable()}};
    audit.progress = Json{{"done", index.progressDone}, {"total", index.progressTotal}};
    const auto popAnimOfPlant = [&catalog](const std::string& id) {
        if (!catalog.rules)
            return std::string{};
        const auto* type = catalog.rules->findPlant(id);
        return type == nullptr ? std::string{} : type->popAnim;
    };
    const auto popAnimOfZombie = [&catalog](const std::string& id) {
        if (!catalog.rules)
            return std::string{};
        const auto* type = catalog.rules->findZombie(id);
        return type == nullptr ? std::string{} : type->popAnim;
    };
    for (const auto& [id, plant] : catalog.plants)
        countOne(audit.contentPlants, resolveArt(assetRoot, index, plant.art, popAnimOfPlant(id)));
    for (const auto& [id, zombie] : catalog.zombies)
        countOne(audit.contentZombies,
                 resolveArt(assetRoot, index, zombie.art, popAnimOfZombie(id)));
    if (catalog.rules) {
        // The pack carries no legacy art key: these cohorts can only be reached through the
        // SHUTTLE index, which is exactly the coverage question this audit answers.
        for (const auto& plant : catalog.rules->plants)
            countOne(audit.packPlants, resolveArt(assetRoot, index, {}, plant.popAnim));
        for (const auto& zombie : catalog.rules->zombies)
            countOne(audit.packZombies, resolveArt(assetRoot, index, {}, zombie.popAnim));
    }
    return audit;
}
} // namespace pvz
