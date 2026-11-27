/// C4: `engine::SpawnOffsets` - the plant-action `SpawnOffset` table, and the proof that its
/// `y` is a drawing height rather than a zombie landing row.
///
/// Sections
///   table      the shipped `spawn_offsets.json` parses: 487 rows / 224 plants / pxPerRow 116
///   rows       the sign and the median of the 487 `yPx` values (449 negative, 7 positive,
///              median -32), and that 183 of them sit outside +/-0.3 rows - which is why the
///              "`y` is a sub-cell nudge" reading behind the original task cannot hold
///   sentinel   the 12 rows at |yPx| >= 580 (CobCannon -600 ... Dandelion -1000) are flagged
///              and kept, not clamped away
///   launch     the launch height of a plant (highest `shot`/`special` row), and that the
///              view-space lift is monotone: the more negative `yPx`, the higher the draw
///   zombieRow  `rowAdjustmentForZombie` returns 0 for every row, so no zombie ever moves
///   errors     every malformed table throws `spawn offsets: <path>: <reason>`
///   counter    the applied-offset tally only counts non-zero offsets and resets
///
/// Usage: spawn_offset_test [<spawn_offsets.json>] [<temp dir>]
/// The first argument defaults to `generatedDir()/spawn_offsets.json`.

#include "catalog.hpp"          // pvz::pathUtf8()
#include "engine/plantfood.hpp" // generatedDir()
#include "engine/spawn_offsets.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using pvz::engine::SpawnOffset;
using pvz::engine::SpawnOffsets;

namespace {

int failures = 0;

void check(bool ok, const std::string& what) {
    std::printf("%s %s\n", ok ? "ok  " : "FAIL", what.c_str());
    if (!ok) ++failures;
}

void checkNear(double actual, double expected, double tolerance, const std::string& what) {
    const bool ok = std::abs(actual - expected) <= tolerance;
    std::printf("%s %s (got %.6f, want %.6f +/- %.6f)\n", ok ? "ok  " : "FAIL", what.c_str(),
                actual, expected, tolerance);
    if (!ok) ++failures;
}

/// A row of the table for a plant, or nullptr - used to keep the assertions readable.
const SpawnOffset* rowOf(const SpawnOffsets& table, const std::string& plant) {
    return table.launchOffset(plant);
}

double liftOf(const SpawnOffsets& table, const std::string& plant, double cellH) {
    return table.launchYPixels(plant) * (cellH / table.pxPerRow());
}

void writeFixture(const fs::path& path, const std::string& body) {
    std::ofstream out(path);
    out << body;
}

/// The message `load()` throws for `file`, or an empty string when it loads. Keeping the text
/// lets one assertion test the prefix (`spawn offsets: <path>: `) and the reason separately.
std::string messageOf(const fs::path& file) {
    try {
        (void)SpawnOffsets::load(file);
    } catch (const std::exception& error) {
        return error.what();
    }
    return {};
}

bool throwsWith(const fs::path& file, const std::string& needle) {
    return messageOf(file).find(needle) != std::string::npos;
}

} // namespace

int main(int argc, char** argv) {
    // Unbuffered: a crash must not swallow the section it died in.
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    const fs::path table_path =
        argc > 1 ? fs::path(argv[1]) : pvz::engine::generatedDir() / SpawnOffsets::kFileName;
    const fs::path temp = argc > 2 ? fs::path(argv[2]) : fs::temp_directory_path();
    // The fixture section writes its own tables. A temp directory that does not exist would make
    // every fixture unwritable, and the assertions below would then die on an uncaught throw
    // (fail-fast 0xC0000409) instead of reporting the real reason.
    std::error_code mkdirError;
    fs::create_directories(temp, mkdirError);
    if (!fs::is_directory(temp)) {
        std::printf("FAIL temp directory %s is unavailable: %s\n", pvz::pathUtf8(temp).c_str(),
                    mkdirError.message().c_str());
        return 1;
    }
    std::printf("spawn offsets table: %s\n", pvz::pathUtf8(table_path).c_str());

    // ---- table ---------------------------------------------------------------------------
    std::printf("-- table\n");
    SpawnOffsets table;
    try {
        table = SpawnOffsets::load(table_path);
    } catch (const std::exception& error) {
        std::printf("FAIL load: %s\n", error.what());
        return 1;
    }
    check(table.size() == 487, "487 rows");
    checkNear(table.pxPerRow(), 116.0, 0.0001, "pxPerRow 116");
    checkNear(table.pxPerColumn(), 100.0, 0.0001, "pxPerColumn 100");
    std::size_t plants = 0;
    {
        std::vector<std::string> seen;
        for (const auto& row : table.rows()) {
            bool known = false;
            for (const auto& name : seen) known = known || name == row.plant;
            if (!known) {
                seen.push_back(row.plant);
                ++plants;
            }
        }
    }
    check(plants == 224, "224 distinct plants (got " + std::to_string(plants) + ")");
    const SpawnOffset* agave = table.find("AgaveDefault", 0);
    check(agave != nullptr && agave->yPx == -110.0, "find(AgaveDefault, 0).yPx == -110");
    check(table.find("AgaveDefault", 9) == nullptr, "action 9 of AgaveDefault is absent");

    // ---- rows: sign and median -----------------------------------------------------------
    std::printf("-- rows\n");
    check(table.negativeRows() == 449, "449 negative rows");
    check(table.positiveRows() == 7, "7 positive rows");
    checkNear(table.medianYPx(), -32.0, 1.0, "median yPx -32");
    std::size_t outside = 0;
    for (const auto& row : table.rows())
        if (std::abs(row.yPx / table.pxPerRow()) > 0.3) ++outside;
    check(outside == 183, "183 rows outside +/-0.3 cells (got " + std::to_string(outside) + ")");
    check(outside > table.size() / 3, "the sub-cell premise fails for over a third of the table");

    // ---- sentinel ------------------------------------------------------------------------
    std::printf("-- sentinel\n");
    check(table.sentinelRows() == 12, "12 sentinel rows at |yPx| >= 580");
    const SpawnOffset* cannon = rowOf(table, "CobCannonDefault");
    check(cannon != nullptr && cannon->sentinel && cannon->yPx == -600.0,
          "CobCannonDefault -600 is flagged");
    const SpawnOffset* dandelion = rowOf(table, "DandelionDefault");
    check(dandelion != nullptr && dandelion->sentinel && dandelion->yPx == -1000.0,
          "DandelionDefault -1000 is flagged");
    checkNear(table.launchYRows("DandelionDefault"), -1000.0 / 116.0, 0.001,
              "DandelionDefault is -8.62 rows");

    // ---- launch: monotone drawing offset --------------------------------------------------
    std::printf("-- launch\n");
    const double cellH = 100.0; // battle_view's lawn cell
    checkNear(liftOf(table, "AgaveDefault", cellH), -115.0 * (100.0 / 116.0), 0.001,
              "AgaveDefault lifts -115 px");
    check(table.launchYPixels("DandelionDefault") < table.launchYPixels("AgaveDefault"),
          "DandelionDefault is drawn above AgaveDefault");
    check(table.launchYPixels("PowerVineDefault") > table.launchYPixels("AgaveDefault"),
          "PowerVineDefault (+14/+ -10 -> -10) is drawn below AgaveDefault");
    check(table.launchYPixels("NoSuchPlantDefault") == 0.0, "unknown plant lifts nothing");
    check(liftOf(table, "NoSuchPlantDefault", cellH) == 0.0, "unknown plant lifts 0 view px");
    {
        // y more negative => lift more negative => drawn higher. Asserted over every row rather
        // than on three samples, so a sign flip anywhere in the table fails here.
        std::vector<const SpawnOffset*> ordered;
        for (const auto& row : table.rows()) ordered.push_back(&row);
        for (std::size_t i = 1; i < ordered.size(); ++i) {
            for (std::size_t j = i; j > 0 && ordered[j - 1]->yPx > ordered[j]->yPx; --j)
                std::swap(ordered[j - 1], ordered[j]);
        }
        bool monotone = true;
        double previous = -1e30;
        for (const auto* row : ordered) {
            const double lift = row->yPx * (cellH / table.pxPerRow());
            if (lift < previous - 1e-9) monotone = false;
            previous = lift;
        }
        check(monotone, "view lift is monotone in yPx across all 487 rows");
    }
    {
        // The board clamp the view applies must not invert the order either: clamp() is
        // monotone, so the clamped draw height of a higher launch stays at or above.
        const double top = 12.0, bottom = 12.0 + 5 * cellH;
        std::vector<double> lifts;
        for (const auto& row : table.rows()) lifts.push_back(row.yPx);
        std::sort(lifts.begin(), lifts.end());
        double previous = -1e30;
        bool clampedMonotone = true;
        for (const double yPx : lifts) {
            const double y = std::clamp(12.0 + yPx * (cellH / table.pxPerRow()), top, bottom);
            if (y < previous - 1e-9) clampedMonotone = false;
            previous = y;
        }
        check(clampedMonotone, "clamping to the board keeps the order");
    }

    // ---- zombie rows do not move ---------------------------------------------------------
    std::printf("-- zombieRow\n");
    {
        bool allZero = true;
        for (int row = -2; row <= 10; ++row)
            if (table.rowAdjustmentForZombie(row) != 0) allZero = false;
        check(allZero, "rowAdjustmentForZombie is 0 for rows -2..10");
        check(table.rowAdjustmentForZombie(0) == 0, "even the -8.62-row Dandelion offset moves nothing");
    }

    // ---- errors --------------------------------------------------------------------------
    std::printf("-- errors\n");
    {
        const fs::path garbage = temp / "spawn_offsets_garbage.json";
        writeFixture(garbage, "{ not json");
        {
            const std::string message = messageOf(garbage);
            check(message.rfind("spawn offsets: ", 0) == 0 &&
                      message.find("spawn_offsets_garbage.json") != std::string::npos,
                  "broken JSON is reported as `spawn offsets: <path>: ...`");
        }

        const fs::path missing = temp / "spawn_offsets_missing.json";
        writeFixture(missing, R"({"rows": []})");
        check(SpawnOffsets::load(missing).empty(), "an empty rows array loads as an empty table");

        const fs::path noRows = temp / "spawn_offsets_no_rows.json";
        writeFixture(noRows, R"({"scale": {"pxPerRow": 116}})");
        check(throwsWith(noRows, "rows is not an array"), "a table without rows is refused");

        const fs::path noY = temp / "spawn_offsets_no_y.json";
        writeFixture(noY, R"({"rows": [{"plant": "X", "kind": "shot"}]})");
        check(throwsWith(noY, "yPx is missing"), "a row without yPx is refused");

        const fs::path noPlant = temp / "spawn_offsets_no_plant.json";
        writeFixture(noPlant, R"({"rows": [{"kind": "shot", "yPx": -1}]})");
        check(throwsWith(noPlant, "plant is missing"), "a row without a plant is refused");

        const fs::path fallback = temp / "spawn_offsets_fallback.json";
        writeFixture(fallback, R"({"rows": [{"plant": "X", "kind": "shot", "yPx": -116}]})");
        const SpawnOffsets small = SpawnOffsets::load(fallback);
        checkNear(small.pxPerRow(), SpawnOffsets::kFallbackPxPerRow, 0.0001,
                  "a table without scale falls back to 116 px per row");
        checkNear(small.launchYRows("X"), -1.0, 0.001, "and -116 px is exactly -1 row");
    }
    {
        const fs::path absent = temp / "spawn_offsets_absent_xyz.json";
        if (fs::exists(absent)) fs::remove(absent);
        check(throwsWith(absent, "cannot open"), "an absent file is reported with the path");
    }

    // ---- content id -> sheet spelling -------------------------------------------------------
    // The trap this covers: the table is keyed by the property sheet's TypeName
    // (`PeashooterDefault`) while the engine carries the content id (`peashooter`). A literal
    // comparison finds nothing, every lift stays 0, and the wiring looks installed but does
    // nothing - which is what the first cut did (battle snapshot byte-identical).
    std::printf("-- alias\n");
    check(table.plantAliases() == 224, "the table holds 224 distinct plant spellings");
    check(table.canonicalPlant("peashooter") == "PeashooterDefault",
          "a content id resolves to the sheet spelling");
    check(table.canonicalPlant("PEASHOOTER") == "PeashooterDefault", "the match ignores case");
    check(table.canonicalPlant("Peashooter") == "PeashooterDefault",
          "and a spelling without the Default suffix");
    checkNear(table.launchYPixels("peashooter"), table.launchYPixels("PeashooterDefault"), 0.0001,
              "so the content id and the sheet spelling give the same launch height");
    check(table.launchYPixels("peashooter") < 0.0,
          "and that height is above the row centre (peashooter -32 px)");
    check(table.canonicalPlant("cobcannon") == "CobCannonDefault", "CobCannon resolves too");
    checkNear(table.launchYRows("cobcannon"), -600.0 / table.pxPerRow(), 0.001,
              "and its lobbed shot still reports -5.17 rows");
    check(table.canonicalPlant("powervine") == "PowerVineDefault", "a two-word sheet name resolves");
    check(table.canonicalPlant("definitely_not_a_plant").empty(),
          "an unknown plant resolves to nothing");
    checkNear(table.launchYPixels("definitely_not_a_plant"), 0.0, 0.0001,
              "and draws at the row centre");
    checkNear(table.launchYPixels("sunflower"), 0.0, 0.0001,
              "a plant that only declares sun offsets has no muzzle height");

    // ---- counter -------------------------------------------------------------------------
    std::printf("-- counter\n");
    pvz::engine::resetSpawnOffsetsApplied();
    check(pvz::engine::spawnOffsetsApplied() == 0, "counter starts at 0");
    pvz::engine::noteSpawnOffsetApplied(0.0);
    check(pvz::engine::spawnOffsetsApplied() == 0, "a zero offset is not counted");
    pvz::engine::noteSpawnOffsetApplied(-115.0);
    pvz::engine::noteSpawnOffsetApplied(14.0);
    check(pvz::engine::spawnOffsetsApplied() == 2, "two non-zero offsets counted");
    pvz::engine::resetSpawnOffsetsApplied();
    check(pvz::engine::spawnOffsetsApplied() == 0, "reset clears the tally");

    if (failures == 0) {
        std::printf("PASS spawn_offset rows=%zu sentinel=%zu\n", table.size(), table.sentinelRows());
        return 0;
    }
    std::printf("FAIL spawn_offset %d check(s)\n", failures);
    return 1;
}
