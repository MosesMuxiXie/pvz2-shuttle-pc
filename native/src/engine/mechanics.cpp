// S5.13: read generated/level_mechanics.json. Every failure is a named throw rather than a
// silent empty table: an empty table would make all 1809 levels look like plain levels, which is
// exactly the bug ("the level finished anyway") this file exists to remove.
#include "mechanics.hpp"

#include "plantfood.hpp" // generatedDir(): same resolver as the other generated tables

#include <algorithm>
#include <fstream>
#include <iterator> // std::size over the spawner kind tables below
#include <nlohmann/json.hpp>
#include <stdexcept>

namespace pvz::engine {
namespace {

using Json = nlohmann::json;

std::string stringOr(const Json& object, const char* key, const std::string& fallback = {}) {
    const auto found = object.find(key);
    if (found == object.end() || !found->is_string()) return fallback;
    return found->get<std::string>();
}

int intOr(const Json& object, const char* key, int fallback = 0) {
    const auto found = object.find(key);
    if (found == object.end() || !found->is_number_integer()) return fallback;
    return found->get<int>();
}

double numberOr(const Json& object, const char* key, double fallback = 0.0) {
    const auto found = object.find(key);
    if (found == object.end() || !found->is_number()) return fallback;
    return found->get<double>();
}

bool boolOr(const Json& object, const char* key, bool fallback = false) {
    const auto found = object.find(key);
    if (found == object.end() || !found->is_boolean()) return fallback;
    return found->get<bool>();
}

/// `RTID(gravestone_tutorial@GridItemTypes)` -> `gravestone_tutorial`. Plant and item names in
/// this sheet are already plain (`lilypad`, `whack_puddle`); only the gravestone pool and a few
/// spawner pools carry the serialised form, and the engine keys on the bare name.
std::string bareName(const std::string& raw) {
    std::string text = raw;
    const std::string prefix = "RTID(";
    if (text.rfind(prefix, 0) == 0) text = text.substr(prefix.size());
    const auto at = text.find('@');
    if (at != std::string::npos) text = text.substr(0, at);
    const auto close = text.find(')');
    if (close != std::string::npos) text = text.substr(0, close);
    return text;
}

void readPlacements(const Json& parent, const char* key, std::vector<InitialPlant>& out) {
    const auto found = parent.find(key);
    if (found == parent.end() || !found->is_object()) return;
    const auto placements = found->find("placements");
    if (placements == found->end() || !placements->is_array()) return;
    for (const auto& entry : *placements) {
        if (!entry.is_object()) continue;
        InitialPlant placement;
        placement.plant = bareName(stringOr(entry, "plant"));
        placement.gridX = intOr(entry, "gridX");
        placement.gridY = intOr(entry, "gridY");
        if (placement.plant.empty()) continue;
        out.push_back(placement);
    }
}

void readGridItems(const Json& parent, std::vector<GridItemPlacement>& out, int& unresolved) {
    const auto found = parent.find("initialGridItems");
    if (found == parent.end() || !found->is_object()) return;
    // Two shapes, and both are used: `placements[]` holds items the sheet names directly
    // (`whack_puddle`), while `gravestones.objects[].forceSpawn[]` holds the ones a level starts
    // with through the gravestone module (`beach_72`'s 20 tombstones, `beach_24`'s puddles).
    // Reading only the first shape left 224 levels with a declared module and an empty lawn.
    if (const auto placements = found->find("placements"); placements != found->end() && placements->is_array()) {
        for (const auto& entry : *placements) {
            if (!entry.is_object()) continue;
            GridItemPlacement placement;
            placement.item = bareName(stringOr(entry, "item"));
            placement.gridX = intOr(entry, "gridX");
            placement.gridY = intOr(entry, "gridY");
            if (placement.item.empty()) continue;
            out.push_back(placement);
        }
    }
    if (const auto gravestones = found->find("gravestones");
        gravestones != found->end() && gravestones->is_object()) {
        // Two shapes again: `gravestones.objects[].forceSpawn[]` on most levels, and
        // `gravestones.forceSpawn[]` with no `objects` wrapper on 46 of them. Reading only the
        // first shape loses a whole level's worth of tombstones each time, which is exactly the
        // kind of silent gap this task exists to remove.
        std::vector<const Json*> blocks;
        if (const auto objects = gravestones->find("objects");
            objects != gravestones->end() && objects->is_array()) {
            for (const auto& block : *objects)
                if (block.is_object()) blocks.push_back(&block);
        } else {
            blocks.push_back(&*gravestones);
        }
        for (const Json* block : blocks) {
            const auto spawn = block->find("forceSpawn");
            if (spawn == block->end() || !spawn->is_array()) continue;
            for (const auto& entry : *spawn) {
                if (!entry.is_object()) continue;
                GridItemPlacement placement;
                placement.item = bareName(stringOr(entry, "type"));
                placement.gridX = intOr(entry, "gridX");
                placement.gridY = intOr(entry, "gridY");
                if (placement.item.empty()) {
                    // The sheet could not resolve what the cell holds (the module names it only in
                    // the source package). The cell is still blocked in the original, so this is a
                    // gap rather than nothing - counted, never silently dropped.
                    ++unresolved;
                    continue;
                }
                out.push_back(placement);
            }
        }
    }
}

void readConveyor(const Json& parent, ConveyorSpec& out) {
    const auto found = parent.find("conveyor");
    if (found == parent.end() || !found->is_object()) return;
    out.alias = stringOr(*found, "alias");
    if (const auto slots = found->find("slots"); slots != found->end() && slots->is_array()) {
        for (const auto& entry : *slots) {
            if (!entry.is_object()) continue;
            ConveyorSlotRow row;
            row.plant = bareName(stringOr(entry, "plant"));
            row.weight = numberOr(entry, "weight", 1.0);
            if (row.plant.empty()) continue;
            if (row.weight <= 0.0) row.weight = 1.0;
            out.totalWeight += static_cast<int>(row.weight * 100.0 + 0.5);
            out.slots.push_back(row);
        }
    }
    // Three conveyor levels carry no `slots` at all and instead add packets through
    // `changes[].add[]` (`lostcity_67`). Without this the belt would be an empty table and the
    // level would look like a seed-bank level again. Two more levels name the class and provide
    // neither path (`dark_33`, `frontyard_173`), so they read as a belt with no cards and are
    // counted under `withConveyor` only - which is why that count (350) is larger than the number
    // of levels that can actually deal a hand (348).
    if (const auto changes = found->find("changes"); changes != found->end() && changes->is_array()) {
        for (const auto& change : *changes) {
            if (!change.is_object()) continue;
            const auto added = change.find("add");
            if (added == change.end() || !added->is_array()) continue;
            for (const auto& entry : *added) {
                if (!entry.is_object()) continue;
                ConveyorSlotRow row;
                row.plant = bareName(stringOr(entry, "plant"));
                row.weight = numberOr(entry, "weight", 1.0);
                if (row.plant.empty()) continue;
                if (row.weight <= 0.0) row.weight = 1.0;
                out.totalWeight += static_cast<int>(row.weight * 100.0 + 0.5);
                out.slots.push_back(row);
            }
        }
    }
    if (const auto delays = found->find("dropDelayConditions"); delays != found->end() && delays->is_array()) {
        for (const auto& entry : *delays) {
            if (!entry.is_object()) continue;
            const int delay = intOr(entry, "delay");
            if (delay > 0) out.dropDelays.push_back(delay);
        }
        std::sort(out.dropDelays.begin(), out.dropDelays.end());
        out.dropDelays.erase(std::unique(out.dropDelays.begin(), out.dropDelays.end()), out.dropDelays.end());
    }
    // An empty slot table means "declared but not a conveyor level" (5 of the 350 declare only a
    // wave modifier); the caller must not build a hand for those.
}

void readProtect(const Json& parent, ProtectSpec& out) {
    const auto found = parent.find("protectThePlant");
    if (found == parent.end() || !found->is_object()) return;
    out.failWhenProtectedPlantDies = boolOr(*found, "failWhenProtectedPlantDies");
    // `-1` keeps "the sheet did not say" apart from a real zero: `egypt_56` says zero explicitly
    // and listing fifteen plants it does not require must not turn into "all fifteen are required".
    const auto count = found->find("mustProtectCount");
    out.mustProtectCount = (count != found->end() && !count->is_null()) ? intOr(*found, "mustProtectCount") : -1;
    if (const auto plants = found->find("plants"); plants != found->end() && plants->is_array()) {
        for (const auto& entry : *plants) {
            if (!entry.is_object()) continue;
            InitialPlant plant;
            plant.plant = bareName(stringOr(entry, "plant"));
            plant.gridX = intOr(entry, "gridX");
            plant.gridY = intOr(entry, "gridY");
            if (plant.plant.empty()) continue;
            out.plants.push_back(plant);
        }
    }
}

/// The eight special spawner modules, in the order the report prints them.
constexpr SpawnerKind kSpawnerKinds[] = {SpawnerKind::grid,    SpawnerKind::portal, SpawnerKind::storm,
                                         SpawnerKind::spider,  SpawnerKind::ground, SpawnerKind::dino,
                                         SpawnerKind::beach,   SpawnerKind::fish};
constexpr const char* kSpawnerKeys[] = {"grid", "portal", "storm", "spider", "ground", "dino", "beach", "fish"};
static_assert(std::size(kSpawnerKinds) == std::size(kSpawnerKeys), "spawner kind/key tables must match");

/// `RTID(carnie@ZombieTypes)` -> `ZombieTypes`; a bare name (no RTID wrapper) counts as a zombie.
std::string rtidCategory(const std::string& raw) {
    const std::string prefix = "RTID(";
    if (raw.rfind(prefix, 0) != 0) return "ZombieTypes";
    const auto at = raw.find('@');
    if (at == std::string::npos) return "ZombieTypes";
    std::string category = raw.substr(at + 1);
    const auto close = category.find(')');
    if (close != std::string::npos) category = category.substr(0, close);
    return category;
}

/// Read one `zombies[]` array of a spawner row. Entries whose RTID category is not
/// `ZombieTypes` (the sheet also names `@.` and `@CurrentLevel` objects there) are not zombies
/// and are returned through `nonZombie` so the level can report them instead of spawning a
/// zombie the data never asked for.
void readSpawnerZombies(const Json& entry, std::vector<SpawnerZombie>& out, int& nonZombie) {
    const auto found = entry.find("zombies");
    if (found == entry.end() || !found->is_array()) return;
    for (const auto& row : *found) {
        if (!row.is_object()) continue;
        const std::string raw = stringOr(row, "type");
        if (raw.empty()) continue;
        if (rtidCategory(raw) != "ZombieTypes") {
            ++nonZombie;
            continue;
        }
        SpawnerZombie zombie;
        zombie.type = bareName(raw);
        zombie.row = intOr(row, "row", -1);
        out.push_back(std::move(zombie));
    }
}

/// T66: the special spawner modules. Every kind keeps its own column/row meaning, but they all
/// end in the same three questions - which wave, which cells, which zombies - so one reader with
/// a per-kind switch is enough. Rows the kernel cannot place are counted, never dropped:
/// `spawners.<kind>.unscheduled` for a row the sheet never gave a wave, `spawners.fish.creatures`
/// for the hermit-crab entries, and `spawners.spider` (in `readUnknowns`) for the one kind with
/// no enemy to spawn at all.
void readSpawners(const Json& level, std::vector<SpawnerSpec>& out, std::vector<UnknownMechanic>& unknown) {
    const auto spawners = level.find("spawners");
    if (spawners == level.end() || !spawners->is_object()) return;
    const auto pushUnknown = [&unknown](std::string kind, int count) {
        if (count <= 0) return;
        for (auto& entry : unknown) {
            if (entry.kind != kind) continue;
            entry.count += count;
            return;
        }
        unknown.push_back(UnknownMechanic{std::move(kind), count});
    };
    for (std::size_t index = 0; index < std::size(kSpawnerKeys); ++index) {
        const SpawnerKind kind = kSpawnerKinds[index];
        const auto found = spawners->find(kSpawnerKeys[index]);
        if (found == spawners->end() || !found->is_array()) continue;
        SpawnerSpec spec;
        spec.kind = kind;
        int scheduled = 0;
        int unscheduled = 0;
        int nonZombie = 0;
        for (const auto& entry : *found) {
            if (!entry.is_object()) continue;
            SpawnerRow row;
            row.kind = kind;
            row.alias = stringOr(entry, "alias");
            row.wave = intOr(entry, "wave");
            row.columnStart = intOr(entry, "columnStart", -1);
            row.columnEnd = intOr(entry, "columnEnd", -1);
            row.row = intOr(entry, "dinoRow", -1);
            if (kind == SpawnerKind::portal) {
                // A portal names a cell, not a band: `portalRow`/`portalColumn` are the only
                // placement facts it carries, so they feed the row/column the kernel reads.
                row.row = intOr(entry, "portalRow", -1);
                row.columnEnd = intOr(entry, "portalColumn", -1);
                row.columnStart = row.columnEnd;
            }
            row.groupSize = intOr(entry, "groupSize");
            row.betweenGroups = numberOr(entry, "timeBetweenGroups");
            row.waitSeconds = numberOr(entry, "zombieSpawnWaitTime");
            row.count = intOr(entry, "spiderCount", intOr(entry, "zombieCount"));
            readSpawnerZombies(entry, row.zombies, nonZombie);
            if (kind == SpawnerKind::fish) {
                // `fishes[]` are CreatureTypes (hermit crabs), not zombies: the kernel has no
                // creature entity, so they stay counted rather than turned into zombies.
                if (const auto fishes = entry.find("fishes"); fishes != entry.end() && fishes->is_array()) {
                    pushUnknown("spawners.fish.creatures", static_cast<int>(fishes->size()));
                }
            }
            // A portal names no zombies: it redirects the wave's own spawns. A dino names no
            // zombies either: it sweeps a row. Both are still rows the kernel runs, so they are
            // kept even with an empty `zombies` list.
            const bool needsZombies = kind == SpawnerKind::grid || kind == SpawnerKind::storm ||
                                      kind == SpawnerKind::ground || kind == SpawnerKind::beach ||
                                      kind == SpawnerKind::fish;
            if (needsZombies && row.zombies.empty() && kind != SpawnerKind::beach) continue;
            if (row.scheduled()) ++scheduled;
            else ++unscheduled;
            spec.rows.push_back(std::move(row));
        }
        if (unscheduled > 0) pushUnknown(std::string("spawners.") + kSpawnerKeys[index] + ".unscheduled", unscheduled);
        if (nonZombie > 0) pushUnknown(std::string("spawners.") + kSpawnerKeys[index] + ".nonzombie", nonZombie);
        if (scheduled > 0) out.push_back(std::move(spec));
    }
}

void readGravestones(const Json& parent, std::vector<GravestoneWave>& out, int& unpositioned) {
    const auto spawners = parent.find("spawners");
    if (spawners == parent.end() || !spawners->is_object()) return;
    const auto found = spawners->find("gravestone");
    if (found == spawners->end() || !found->is_array()) return;
    for (const auto& entry : *found) {
        if (!entry.is_object()) continue;
        GravestoneWave wave;
        wave.wave = intOr(entry, "wave");
        std::string type;
        int wanted = 0;
        if (const auto pool = entry.find("gravestonePool"); pool != entry.end() && pool->is_array()) {
            for (const auto& row : *pool) {
                if (!row.is_object()) continue;
                if (type.empty()) type = bareName(stringOr(row, "type"));
                wanted += intOr(row, "count");
            }
        }
        if (type.empty()) type = "gravestone";
        if (const auto positions = entry.find("spawnPositionsPool");
            positions != entry.end() && positions->is_array()) {
            for (const auto& row : *positions) {
                if (!row.is_object()) continue;
                if (wanted > 0 && static_cast<int>(wave.positions.size()) >= wanted) break;
                GridItemPlacement placement;
                placement.item = type;
                placement.gridX = intOr(row, "mX");
                placement.gridY = intOr(row, "mY");
                placement.wave = wave.wave;
                wave.positions.push_back(placement);
            }
        }
        if (!wave.positions.empty()) out.push_back(wave);
        else {
            // Twenty-seven waves name a gravestone pool but no cells: the original reads the cells
            // from the board instead. The wave is kept, so the level is still a gravestone level,
            // and the unplaceable count is reported as a gap rather than dropped on the floor.
            ++unpositioned;
            out.push_back(wave);
        }
    }
}

/// T88: the Events module. Two kinds carry a meaning the kernel can honour - a tide change names
/// a destination column at a wave (`ChangeType: absolute` in every shipped row) and a frost wind
/// names a wave plus the rows it blows over (`Row: -1` = every row). Anything the sheet left
/// without a wave is counted instead of being run at a guessed wave.
void readEvents(const Json& level, EventsSpec& out, std::vector<UnknownMechanic>& unknown) {
    const auto push = [&unknown](std::string kind, int count) {
        if (count <= 0) return;
        for (auto& entry : unknown) {
            if (entry.kind != kind) continue;
            entry.count += count;
            return;
        }
        unknown.push_back(UnknownMechanic{std::move(kind), count});
    };
    const auto found = level.find("events");
    if (found == level.end() || !found->is_object()) return;

    if (const auto tide = found->find("tide"); tide != found->end() && tide->is_array()) {
        for (const Json& row : *tide) {
            if (!row.is_object()) continue;
            const int wave = intOr(row, "wave", 0);
            const int amount = intOr(row, "changeAmount", 0);
            const std::string type = stringOr(row, "changeType");
            if (wave <= 0) {
                push("events.tide.unscheduled", 1);
                continue;
            }
            // Only an absolute change names a column. A relative one would have to know the
            // waterline it starts from, which no shipped row states, so it is counted.
            if (type != "absolute") {
                push("events.tide.relative", 1);
                continue;
            }
            out.tide.push_back(TideChange{wave, amount, type});
        }
        std::sort(out.tide.begin(), out.tide.end(),
                  [](const TideChange& a, const TideChange& b) {
                      if (a.wave != b.wave) return a.wave < b.wave;
                      return a.column < b.column;
                  });
    }

    if (const auto frost = found->find("frost"); frost != found->end() && frost->is_array()) {
        for (const Json& row : *frost) {
            if (!row.is_object()) continue;
            const int wave = intOr(row, "wave", 0);
            FrostWind wind;
            wind.wave = wave;
            if (const auto winds = row.find("winds"); winds != row.end() && winds->is_array()) {
                for (const Json& entry : *winds) {
                    if (!entry.is_object()) continue;
                    const int windRow = intOr(entry, "row", -1);
                    if (windRow < -1) continue;
                    const std::string direction = stringOr(entry, "direction");
                    if (wind.direction.empty()) wind.direction = direction;
                    if (std::find(wind.rows.begin(), wind.rows.end(), windRow) == wind.rows.end()) {
                        wind.rows.push_back(windRow);
                    }
                }
            }
            if (wave <= 0) {
                push("events.frost.unscheduled", 1);
                continue;
            }
            if (wind.rows.empty()) {
                push("events.frost.empty", 1);
                continue;
            }
            std::sort(wind.rows.begin(), wind.rows.end());
            out.frost.push_back(std::move(wind));
        }
        std::sort(out.frost.begin(), out.frost.end(),
                  [](const FrostWind& a, const FrostWind& b) { return a.wave < b.wave; });
    }
}

/// T88: `BoardGridMapProps.Values`, carried as data. A mask whose shape is not the sheet's 5x9
/// would be a different board than the level's own rows/cols, so it is counted rather than
/// applied.
void readBoardGrid(const Json& level, BoardGridSpec& out, std::vector<UnknownMechanic>& unknown) {
    const auto found = level.find("boardGrid");
    if (found == level.end() || !found->is_object()) return;
    BoardGridSpec spec;
    spec.alias = stringOr(*found, "alias");
    spec.width = intOr(*found, "width", 0);
    spec.height = intOr(*found, "height", 0);
    const auto rows = found->find("rows");
    if (rows == found->end() || !rows->is_array()) {
        unknown.push_back({"boardGrid.malformed", 1});
        return;
    }
    for (const Json& row : *rows) {
        if (!row.is_array()) {
            unknown.push_back({"boardGrid.malformed", 1});
            return;
        }
        std::vector<int> cells;
        cells.reserve(row.size());
        for (const Json& cell : row) {
            cells.push_back(cell.is_number_integer() ? cell.get<int>() : 0);
        }
        spec.cells.push_back(std::move(cells));
    }
    const int height = static_cast<int>(spec.cells.size());
    const int width = spec.cells.empty() ? 0 : static_cast<int>(spec.cells.front().size());
    if (height <= 0 || width <= 0 || (spec.height > 0 && spec.height != height) ||
        (spec.width > 0 && spec.width != width)) {
        unknown.push_back({"boardGrid.malformed", 1});
        return;
    }
    spec.height = height;
    spec.width = width;
    out = std::move(spec);
}

/// T88: the mutators. `LevelMutatorMaxSunProps.maxSunOverride` states a rule - the sun bank may
/// not hold more than N - and is applied. `LevelMutatorModuleProperties` / `...TableProps` rows
/// are mission wrappers (`LevelTimer`, `KillZombies1`, `PlantsLost2`...) with no modifier in
/// them, so they are counted as unknown instead of being read as a multiplier the sheet never
/// gave. There is no speed/health/damage/sun-production multiplier anywhere in the 21 levels.
void readMutators(const Json& level, MutatorSpec& out, std::vector<UnknownMechanic>& unknown) {
    const auto found = level.find("mutators");
    if (found == level.end() || !found->is_array()) return;
    int wrappers = 0;
    for (const Json& row : *found) {
        if (!row.is_object()) continue;
        if (const auto cap = row.find("maxSunOverride"); cap != row.end() && cap->is_number_integer()) {
            const int value = cap->get<int>();
            if (value > 0) out.maxSun = std::max(out.maxSun, value);
            continue;
        }
        ++wrappers;
    }
    out.challengeRows = wrappers;
    if (wrappers > 0) {
        for (auto& entry : unknown) {
            if (entry.kind != "mutators") continue;
            entry.count += wrappers;
            return;
        }
        unknown.push_back({"mutators", wrappers});
    }
}

/// Present-but-unimplemented modules. `spawners.jittered` is the ordinary wave source and is
/// covered, `spawners.gravestone` has its own reader, and the seven spawner kinds T66 wires are
/// read by `readSpawners` - only the kinds that are left (`spawners.spider`, and anything the
/// sheet grows later) are counted here. Counting instances rather than a bool keeps the report
/// honest about how much of the level is missing: a level with two spider-rain rows is reported
/// as two, not "one gap".
void readUnknowns(const Json& level, std::vector<UnknownMechanic>& out) {
    const auto push = [&out](std::string kind, int count) {
        if (count <= 0) return;
        for (auto& entry : out) {
            if (entry.kind != kind) continue;
            entry.count += count;
            return;
        }
        out.push_back(UnknownMechanic{std::move(kind), count});
    };
    // T88: `events`, `mutators` and `boardGrid` are no longer counted here - `readEvents`,
    // `readMutators` and `readBoardGrid` run them, and each counts only the part of its module
    // that the sheet left without semantics (an untimed row, a challenge wrapper, a malformed
    // mask). What is left in this function is the spawner kinds the kernel cannot place.
    if (const auto spawners = level.find("spawners"); spawners != level.end() && spawners->is_object()) {
        for (auto it = spawners->begin(); it != spawners->end(); ++it) {
            const std::string kind = it.key();
            if (kind == "jittered" || kind == "gravestone") continue;
            // T66: a kind that `readSpawners` runs is no longer a gap. `spider` is the exception
            // on purpose - the sheet names a spider count, but neither the 55 content zombies nor
            // the 1127 pack zombies has a spider, so there is no enemy the kernel could place.
            bool wired = false;
            for (std::size_t slot = 0; slot < std::size(kSpawnerKeys); ++slot) {
                if (kind != kSpawnerKeys[slot]) continue;
                wired = spawnerKindIsWired(kSpawnerKinds[slot]);
                break;
            }
            if (wired) continue;
            if (it->is_array()) {
                push("spawners." + kind, static_cast<int>(it->size()));
            } else if (it->is_object()) {
                push("spawners." + kind, 1);
            }
        }
    }
    std::sort(out.begin(), out.end(),
              [](const UnknownMechanic& a, const UnknownMechanic& b) { return a.kind < b.kind; });
}

LevelMechanics parseLevel(const std::string& id, const Json& level) {
    LevelMechanics mechanics;
    mechanics.id = id;
    if (!level.is_object()) return mechanics;
    readPlacements(level, "initialPlants", mechanics.initialPlants);
    int unresolvedGridItems = 0;
    int unpositionedGravestones = 0;
    readGridItems(level, mechanics.initialGridItems, unresolvedGridItems);
    if (unresolvedGridItems > 0) {
        mechanics.unknownMechanics.push_back({"initialGridItems.unresolved", unresolvedGridItems});
    }
    readConveyor(level, mechanics.conveyor);
    readProtect(level, mechanics.protect);
    readGravestones(level, mechanics.gravestones, unpositionedGravestones);
    readSpawners(level, mechanics.spawners, mechanics.unknownMechanics);
    readEvents(level, mechanics.events, mechanics.unknownMechanics);
    readBoardGrid(level, mechanics.boardGrid, mechanics.unknownMechanics);
    readMutators(level, mechanics.mutators, mechanics.unknownMechanics);
    if (unpositionedGravestones > 0) {
        mechanics.unknownMechanics.push_back({"spawners.gravestone.unpositioned", unpositionedGravestones});
    }
    readUnknowns(level, mechanics.unknownMechanics);
    std::sort(mechanics.unknownMechanics.begin(), mechanics.unknownMechanics.end(),
              [](const UnknownMechanic& a, const UnknownMechanic& b) { return a.kind < b.kind; });
    return mechanics;
}

} // namespace

// Resolved outside the anonymous namespace: the helpers above are file-local, this is part of the
// type the rest of the engine sees.
int BoardGridSpec::marked() const {
    int count = 0;
    for (const std::vector<int>& row : cells) {
        for (const int code : row) {
            if (code != 0) ++count;
        }
    }
    return count;
}

int ProtectSpec::requiredSurvivors() const {    if (plants.empty()) return 0;
    // A mission that does not fail on a protected death keeps the plants as set dressing
    // (`failWhenProtectedPlantDies` is the sheet's own switch, and all 286 missions set it).
    if (!failWhenProtectedPlantDies) return 0;
    // `mustProtectCount` is authoritative whenever the sheet gave one - including the explicit
    // zero on `egypt_56`, where fifteen plants are listed and none has to survive.
    if (mustProtectCount >= 0) return mustProtectCount;
    return static_cast<int>(plants.size());
}

MechanicTier mechanicTierFor(const std::string& kind) {
    // Covered: the modules this kernel actually runs. `spawners.jittered` is here because the
    // director already turns that table into the ordinary wave schedule - the rows, counts and
    // per-wave split all reach the lawn, so counting it as a gap would double-report it. The
    // seven spawner kinds T66 wired are here for the same reason: their rows now become zombies
    // (or a portal/dino event) on the wave the sheet names.
    static const char* kCovered[] = {"initialPlants",
                                     "initialGridItems",
                                     "conveyor",
                                     "protectThePlant",
                                     "spawners.gravestone",
                                     "spawners.jittered",
                                     "spawners.grid",
                                     "spawners.portal",
                                     "spawners.storm",
                                     "spawners.ground",
                                     "spawners.dino",
                                     "spawners.beach",
                                     "spawners.fish",
                                     // T88: the Events module's two documented kinds, the board
                                     // mask (carried as data) and the one mutator that states a
                                     // rule. Everything else in those modules stays unknown.
                                     "events.tide",
                                     "events.frost",
                                     "boardGrid",
                                     "mutators.maxSun"};
    for (const char* name : kCovered) {
        if (kind == name) return MechanicTier::covered;
    }
    return MechanicTier::unknown;
}

const char* spawnerKindName(SpawnerKind kind) {
    switch (kind) {
    case SpawnerKind::grid: return "spawners.grid";
    case SpawnerKind::portal: return "spawners.portal";
    case SpawnerKind::storm: return "spawners.storm";
    case SpawnerKind::spider: return "spawners.spider";
    case SpawnerKind::ground: return "spawners.ground";
    case SpawnerKind::dino: return "spawners.dino";
    case SpawnerKind::beach: return "spawners.beach";
    case SpawnerKind::fish: return "spawners.fish";
    }
    return "spawners.grid";
}

bool spawnerKindIsWired(SpawnerKind kind) {
    // `spider` has no enemy to place: `spiderCount` is a count of spiders, and no spider exists
    // in either zombie table. Leaving it unknown keeps `--run-level` honest instead of spawning
    // 6 generic zombies the sheet never named.
    return kind != SpawnerKind::spider;
}

bool LevelMechanics::hasSpawners() const {
    for (const SpawnerSpec& spec : spawners) {
        if (!spec.empty()) return true;
    }
    return false;
}

const SpawnerSpec* LevelMechanics::spawner(SpawnerKind kind) const {
    for (const SpawnerSpec& spec : spawners) {
        if (spec.kind == kind) return &spec;
    }
    return nullptr;
}

std::size_t LevelMechanicsTable::withSpawners(SpawnerKind kind) const {
    const auto found = spawnerLevels_.find(kind);
    return found == spawnerLevels_.end() ? 0 : found->second;
}

const char* mechanicTierName(MechanicTier tier) {
    switch (tier) {
    case MechanicTier::covered: return "covered";
    case MechanicTier::unknown: return "unknown";
    }
    return "unknown";
}

LevelMechanicsTable LevelMechanicsTable::load(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("mechanics table: " + path.string() + ": cannot open");
    Json document;
    try {
        input >> document;
    } catch (const std::exception& error) {
        throw std::runtime_error("mechanics table: " + path.string() + ": " + error.what());
    }
    if (!document.is_object()) {
        throw std::runtime_error("mechanics table: " + path.string() + ": root is not a JSON object");
    }
    const auto levels = document.find("levels");
    if (levels == document.end() || !levels->is_object()) {
        throw std::runtime_error("mechanics table: " + path.string() + ": no levels object");
    }
    LevelMechanicsTable table;
    for (auto it = levels->begin(); it != levels->end(); ++it) {
        LevelMechanics mechanics = parseLevel(it.key(), it.value());
        if (mechanics.hasConveyor()) ++table.withConveyor_;
        if (!mechanics.initialPlants.empty()) ++table.withInitialPlants_;
        if (!mechanics.initialGridItems.empty()) ++table.withInitialGridItems_;
        if (mechanics.hasProtect()) ++table.withProtect_;
        if (mechanics.hasGravestones()) ++table.withGravestones_;
        if (mechanics.hasEvents()) ++table.withEvents_;
        if (mechanics.hasBoardGrid()) ++table.withBoardGrid_;
        if (mechanics.hasSunCap()) ++table.withSunCap_;
        for (const SpawnerSpec& spec : mechanics.spawners) {
            if (!spec.empty()) ++table.spawnerLevels_[spec.kind];
        }
        if (!mechanics.unknownMechanics.empty()) ++table.withUnknown_;
        table.levels_.emplace(it.key(), std::move(mechanics));
    }
    if (table.levels_.empty()) {
        throw std::runtime_error("mechanics table: " + path.string() + ": the table is empty");
    }
    return table;
}

const LevelMechanicsTable& LevelMechanicsTable::shared() {
    static const LevelMechanicsTable table = [] {
        const std::filesystem::path dir = generatedDir();
        if (dir.empty()) {
            throw std::runtime_error("mechanics table: the generated directory is unknown; set "
                                     "PVZ_GENERATED_DIR or run from the repository root");
        }
        return load(dir / kFileName);
    }();
    return table;
}

const LevelMechanics* LevelMechanicsTable::find(std::string_view id) const {
    const auto it = levels_.find(id);
    return it == levels_.end() ? nullptr : &it->second;
}

} // namespace pvz::engine
