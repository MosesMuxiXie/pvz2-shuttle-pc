// Art resolver tests: the SHUTTLE index (`assets/db/shuttle/index.json`) is the only reliable
// join between a pack `popAnim` and a converted DragonBones folder, so the resolver, its failure
// modes and the audit counters get their own fixture. Nothing here reads the real artwork tree:
// fixtures live in PVZ_TEST_TEMP, because the extractor keeps writing `assets/db/shuttle/` and a
// test that watched it would flip colour with the extraction progress.
#include "art_index.hpp"
#include "catalog.hpp"
#include "content/model.hpp"

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>

namespace {

using pvz::ArtSource;

void check(bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

std::string describe(const pvz::ArtResolution& resolution) {
    const char* source = resolution.source == ArtSource::web       ? "web"
                         : resolution.source == ArtSource::shuttle ? "shuttle"
                                                                   : "none";
    return std::string{source} + ":" + resolution.dir;
}

/// Writes the four files a converted actor folder carries. The bytes do not matter: the
/// resolver only requires `skeleton.json` to exist.
void writeActor(const std::filesystem::path& dir) {
    std::filesystem::create_directories(dir);
    for (const char* name : {"skeleton.json", "atlas.json", "meta.json"})
        std::ofstream(dir / name) << "{}";
    std::ofstream(dir / "texture.png") << "png";
}

void writeFile(const std::filesystem::path& path, const std::string& text) {
    std::filesystem::create_directories(path.parent_path());
    std::ofstream(path) << text;
}

/// ① A tree without `db/shuttle/index.json` must be reported as an absent index (exit 2), not as
/// an empty success and not as an exception. The legacy web folder keeps working meanwhile.
void testMissingIndex(const pvz::Catalog& catalog, const std::filesystem::path& bareRoot) {
    const auto index = pvz::loadShuttleIndex(bareRoot);
    check(!index.present, "a tree without db/shuttle/index.json must report the index as absent");
    check(!index.loaded, "an absent index cannot report loaded");
    check(index.error.find("index.json") != std::string::npos,
          "the absent-index diagnostic must name index.json, got: " + index.error);
    check(index.items.empty() && index.failures == 0,
          "an absent index must not invent items or failures");

    const auto audit = pvz::auditArt(catalog, bareRoot);
    check(audit.exitCode() == 2, "a missing SHUTTLE index must exit 2, got " +
                                    std::to_string(audit.exitCode()));
    check(audit.indexError.find("index.json") != std::string::npos,
          "the audit must carry the index.json diagnostic, got: " + audit.indexError);
    check(audit.contentPlants.webHit >= 1,
          "the legacy web folder must still resolve without the SHUTTLE index");
}

/// An index that exists but has not listed a single base yet (the extractor's first minutes) must
/// read as "not usable", not as a loaded empty table.
void testEmptyIndex(const pvz::Catalog& catalog, const std::filesystem::path& emptyRoot) {
    const auto index = pvz::loadShuttleIndex(emptyRoot);
    check(index.present, "an index with an empty items[] is still a present file");
    check(!index.loaded, "an index without items must not report loaded");
    check(index.error.find("items") != std::string::npos,
          "the empty-index diagnostic must name items, got: " + index.error);
    check(pvz::auditArt(catalog, emptyRoot).exitCode() == 2,
          "an index without items must exit 2");
}

/// ② With an index, a pack `popAnim` must resolve to the converted folder; several bases may
/// carry one popAnim, and the first one whose folder exists wins.
void testShuttleIndexHits(const std::filesystem::path& root) {
    const auto index = pvz::loadShuttleIndex(root);
    check(index.present && index.loaded, "a well-formed index must load: " + index.error);
    check(index.items.size() == 4, "every listed base must be kept, got " +
                                       std::to_string(index.items.size()));
    check(index.usable() == 3, "only bases whose folder exists are usable, got " +
                                   std::to_string(index.usable()));
    check(index.failures == 1, "the extractor's failures must be counted, got " +
                                   std::to_string(index.failures));
    check(index.basesTotal == 4 && index.ok == 2 && index.failed == 1 && index.pending == 1 &&
              index.popAnimMatched == 3 && index.popAnimNull == 1,
          "the index `counts` must be read verbatim");
    check(index.progressDone == 3 && index.progressTotal == 4,
          "the index `progress` must be read verbatim");

    const auto candidates = index.candidates("POPANIM_PLANT_SUNFLOWER");
    check(candidates.size() == 2,
          "one popAnim may list several bases, got " + std::to_string(candidates.size()));
    check(candidates[0] != nullptr && candidates[0]->base == "GHOST" && !candidates[0]->usable(),
          "the first listed base is the one whose folder is gone");
    const auto* chosen = index.byPopAnim("POPANIM_PLANT_SUNFLOWER");
    check(chosen != nullptr && chosen->base == "FAKEBASE",
          "resolution must skip the base with no folder and take the next one");
    check(chosen->animations == 2 && chosen->images == 31 && chosen->rects == 40,
          "the entry counters must survive parsing");

    const auto shuttle = pvz::resolveArt(root, index, {}, "POPANIM_PLANT_SUNFLOWER");
    check(shuttle.source == ArtSource::shuttle,
          "a popAnim hit must resolve through the SHUTTLE index, got " + describe(shuttle));
    check(shuttle.dir == "db/shuttle/shuttle_FAKEBASE",
          "the popAnim hit must land on the index `dir`, got " + shuttle.dir);

    // `dir` is written relative to assets/ for most bases and relative to db/shuttle/ for some:
    // both layouts must land on the same folder.
    const auto pea = pvz::resolveArt(root, index, {}, "POPANIM_PLANT_PEASHOOTER");
    check(pea.source == ArtSource::shuttle && pea.dir == "db/shuttle/shuttle_FAKEPEA",
          "a dir relative to db/shuttle/ must resolve too, got " + describe(pea));

    const auto ghost = pvz::resolveArt(root, index, {}, "POPANIM_PLANT_GHOST");
    check(ghost.source == ArtSource::none,
          "a popAnim whose only base has no folder must not resolve, got " + describe(ghost));
    const auto noKey = pvz::resolveArt(root, index, {}, "");
    check(!noKey.hit(), "an empty popAnim must not resolve, got " + describe(noKey));
}

/// ③ The legacy web export wins over the SHUTTLE one for the same actor, so shipping the new
/// extraction cannot change which artwork an already-working actor draws.
void testWebWins(const std::filesystem::path& root, const pvz::ShuttleArtIndex& index) {
    const auto both =
        pvz::resolveArt(root, index, "plants/SunflowerPLANT", "POPANIM_PLANT_SUNFLOWER");
    check(both.source == ArtSource::web,
          "the legacy db/<art> folder must win over the SHUTTLE entry, got " + describe(both));
    check(both.dir == "db/plants/SunflowerPLANT",
          "the web hit must be the db/<art> path, got " + both.dir);
    const auto nothing = pvz::resolveArt(root, index, "plants/NoSuchPLANT", "POPANIM_NOTHING");
    check(!nothing.hit(), "an unknown actor must resolve to nothing, got " + describe(nothing));
}

/// ④ The audit counters must add up per cohort and split web/shuttle/missing exactly.
void testAuditCounters(const pvz::Catalog& catalog, const std::filesystem::path& root) {
    const auto audit = pvz::auditArt(catalog, root);
    check(audit.indexLoaded && audit.shuttleEntries == 4,
          "the audit must carry every listed base, got " +
              std::to_string(audit.shuttleEntries));
    check(audit.exitCode() == 1,
          "a loaded index with unresolved actors must exit 1, got " +
              std::to_string(audit.exitCode()));

    const auto& plants = audit.contentPlants;
    check(plants.total == static_cast<int>(catalog.plants.size()),
          "the content plant cohort must cover every plant, got " + std::to_string(plants.total));
    check(plants.webHit + plants.shuttleHit + plants.missing == plants.total,
          "content plant counters must add up: web " + std::to_string(plants.webHit) +
              " + shuttle " + std::to_string(plants.shuttleHit) + " + missing " +
              std::to_string(plants.missing) + " != " + std::to_string(plants.total));
    // Thirteen content plants share the `plants/SunflowerPLANT` art key (the sunflower family,
    // widened by the pack-derived rows), so a single fixture folder legitimately serves them.
    check(plants.webHit == 13, "thirteen content plants share the fixture's web art, got " +
                                   std::to_string(plants.webHit));
    check(plants.shuttleHit == 1, "exactly one content plant resolves through the index, got " +
                                      std::to_string(plants.shuttleHit));
    check(plants.missing == plants.total - 14, "everything else must be counted missing, got " +
                                                   std::to_string(plants.missing));

    const auto& zombies = audit.contentZombies;
    check(zombies.total == static_cast<int>(catalog.zombies.size()),
          "the content zombie cohort must cover every zombie, got " +
              std::to_string(zombies.total));
    check(zombies.webHit == 0 && zombies.shuttleHit == 0 && zombies.missing == zombies.total,
          "the fixture ships no zombie art, so every zombie must be missing");

    check(catalog.rules != nullptr, "the art audit needs the property-sheet pack");
    const auto& packPlants = audit.packPlants;
    check(packPlants.total == static_cast<int>(catalog.rules->plants.size()),
          "the pack plant cohort must cover every pack plant, got " +
              std::to_string(packPlants.total));
    check(packPlants.webHit == 0, "the pack carries no legacy art key, got web hits " +
                                      std::to_string(packPlants.webHit));
    check(packPlants.shuttleHit == 2,
          "both fixture popAnim keys must hit from the pack cohort, got " +
              std::to_string(packPlants.shuttleHit));
    check(audit.packZombies.total == static_cast<int>(catalog.rules->zombies.size()),
          "the pack zombie cohort must cover every pack zombie, got " +
              std::to_string(audit.packZombies.total));

    const auto report = audit.json();
    check(report["contentPlants"]["total"] == plants.total && report["shuttleIndex"] == 4 &&
              report["shuttleFailures"] == 1,
          "the report must expose the cohorts and the index counters: " + report.dump());
    check(report["contentPlants"]["missing"] == plants.missing,
          "the report's missing count must match the cohort");
    check(report["shuttleIndexCounts"]["popAnimMatched"] == 3 &&
              report["shuttleIndexCounts"]["usable"] == 3,
          "the report must quote the index counts: " + report.dump());
    check(report["shuttleIndexProgress"]["done"] == 3,
          "the report must quote the extraction progress: " + report.dump());
}

std::filesystem::path writeFixture(const std::filesystem::path& temp) {
    const auto root = temp / "art_resolver";
    std::error_code ec;
    std::filesystem::remove_all(root, ec);
    writeActor(root / "db/plants/SunflowerPLANT");
    writeActor(root / "db/shuttle/shuttle_FAKEBASE");
    writeActor(root / "db/shuttle/shuttle_FAKEPEA");
    writeActor(root / "db/shuttle/shuttle_NULLPOP");
    // GHOST is listed with a folder that exists but carries no skeleton: the extractor failed on
    // it, so the resolver must skip it and the audit must report the failure.
    std::filesystem::create_directories(root / "db/shuttle/shuttle_GHOST");
    writeFile(root / "db/shuttle/index.json", R"({
  "counts": {"bases_total": 4, "ok": 2, "failed": 1, "pending": 1,
             "popanim_matched": 3, "popanim_null": 1},
  "progress": {"done": 3, "total": 4, "aborted_at": null, "rank": 1, "last_base": "FAKEPEA"},
  "items": [
    {"base": "GHOST", "popAnim": "POPANIM_PLANT_SUNFLOWER", "dir": "db/shuttle/shuttle_GHOST",
     "images": 0, "animations": 0, "rects": 0, "page": 1, "bytes": 0, "seconds": 0.0,
     "sha256": {}},
    {"base": "FAKEBASE", "popAnim": "POPANIM_PLANT_SUNFLOWER",
     "dir": "db/shuttle/shuttle_FAKEBASE", "images": 31, "animations": 2, "rects": 40,
     "page": 1, "bytes": 10, "seconds": 1.0, "sha256": {}},
    {"base": "FAKEPEA", "popAnim": "POPANIM_PLANT_PEASHOOTER", "dir": "shuttle_FAKEPEA",
     "images": 12, "animations": 1, "rects": 9, "page": 1, "bytes": 10, "seconds": 1.0,
     "sha256": {}},
    {"base": "NULLPOP", "popAnim": null, "dir": "db/shuttle/shuttle_NULLPOP", "images": 3,
     "animations": 1, "rects": 2, "page": 1, "bytes": 10, "seconds": 1.0, "sha256": {}}
  ],
  "failures": [{"base": "BROKEN", "reason": "no texture in group"}]
})");
    // A second tree with only the legacy export, used for the absent-index case.
    const auto bare = temp / "art_resolver_no_index";
    std::filesystem::remove_all(bare, ec);
    writeActor(bare / "db/plants/SunflowerPLANT");
    // A third tree whose index has not listed a base yet.
    const auto empty = temp / "art_resolver_empty_index";
    std::filesystem::remove_all(empty, ec);
    writeFile(empty / "db/shuttle/index.json",
              R"({"counts": {"bases_total": 0, "ok": 0, "failed": 0, "pending": 1087},
                  "progress": {"done": 0, "total": 1087}, "items": [], "failures": []})");
    return root;
}

} // namespace

int wmain(int argc, wchar_t** argv) {
    if (argc < 4) {
        std::fprintf(stderr, "usage: art_audit_test <content> <pack> <temp>\n");
        return 2;
    }
    try {
        pvz::CatalogOptions options;
        options.contentPack = std::filesystem::path(argv[2]);
        const auto catalog = pvz::loadCatalog(std::filesystem::path(argv[1]), options);
        const std::filesystem::path temp(argv[3]);
        const auto root = writeFixture(temp);
        const auto bareRoot = temp / "art_resolver_no_index";
        const auto emptyRoot = temp / "art_resolver_empty_index";

        testMissingIndex(catalog, bareRoot);
        testEmptyIndex(catalog, emptyRoot);
        testShuttleIndexHits(root);
        testShuttleIndexHits(root);  // the loader must be repeatable, not stateful
        const auto index = pvz::loadShuttleIndex(root);
        testWebWins(root, index);
        testAuditCounters(catalog, root);
        std::printf("art audit tests passed\n");
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "art audit test failed: %s\n", error.what());
        return 1;
    }
}
