#include "audio/event_map.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace pvz {
namespace {

/// Pack values are CamelCase identifiers (`Play_ImpatiensShooter_Attack`), so a separator is
/// inserted before every upper-case letter that follows a lower-case one, then everything is
/// lower-cased and every run of non-alphanumerics becomes a single `_`.
std::string normalize(std::string_view raw) {
    std::string spaced;
    spaced.reserve(raw.size() + 8);
    for (std::size_t i = 0; i < raw.size(); ++i) {
        const auto c = static_cast<unsigned char>(raw[i]);
        if (i > 0 && std::isupper(c) &&
            (std::islower(static_cast<unsigned char>(raw[i - 1])) ||
             std::isdigit(static_cast<unsigned char>(raw[i - 1]))))
            spaced.push_back('_');
        spaced.push_back(static_cast<char>(c));
    }
    std::string out;
    out.reserve(spaced.size());
    bool pendingSeparator = false;
    for (const char c : spaced) {
        const auto uc = static_cast<unsigned char>(c);
        if (std::isalnum(uc)) {
            if (pendingSeparator && !out.empty()) out.push_back('_');
            pendingSeparator = false;
            out.push_back(static_cast<char>(std::tolower(uc)));
        } else {
            pendingSeparator = true;
        }
    }
    return out;
}

std::vector<std::string> splitTokens(const std::string& normalized) {
    std::vector<std::string> tokens;
    std::string current;
    for (const char c : normalized) {
        if (c == '_') {
            if (!current.empty()) tokens.push_back(current);
            current.clear();
        } else {
            current.push_back(c);
        }
    }
    if (!current.empty()) tokens.push_back(current);
    return tokens;
}

bool startsWith(const std::string& text, std::string_view prefix) {
    return text.size() >= prefix.size() && text.compare(0, prefix.size(), prefix) == 0;
}

struct TokenAlias {
    const char* token;
    const char* event;
};

/// A pack value that is not a canonical event name is resolved by its trailing token: the head
/// of these identifiers is the plant, the tail is what actually happens (`..._Attack`, `..._Throw`).
constexpr TokenAlias kAliases[] = {
    {"throw", "shoot"},   {"shoot", "shoot"},   {"shooter", "shoot"}, {"shot", "shoot"},
    {"fire", "shoot"},    {"attack", "shoot"},  {"launch", "shoot"},  {"spit", "shoot"},
    {"arrow", "shoot"},   {"pea", "shoot"},     {"impact", "hit"},    {"hit", "hit"},
    {"damage", "hit"},    {"bounce", "hit"},    {"sun", "sun_collect"}, {"plant", "plant"},
    {"sprout", "plant_sprout"}, {"seed", "plant"}, {"shovel", "shovel"}, {"dig", "shovel"},
    {"wave", "wave"},     {"die", "die"},       {"death", "die"},     {"dead", "die"},
    {"kill", "die"},      {"click", "click"},   {"button", "click"},  {"error", "error"},
    {"invalid", "error"}, {"denied", "error"},  {"win", "win"},       {"victory", "win"},
    {"lose", "lose"},     {"defeat", "lose"},   {"roar", "zombie_groan"},
    {"groan", "zombie_groan"}, {"moan", "zombie_groan"}, {"coin", "coin"},
    {"gem", "gem"},       {"gulp", "plant_food"}, {"open", "ui_open"}, {"close", "ui_close"},
};

/// Audio keys the shipped property sheets use. Listed explicitly so a stray `Sound` field in some
/// unrelated sheet is not mistaken for an audio event.
constexpr std::string_view kAudioKeys[] = {
    "ProjectileLaunchSound", "PlantFoodActivationSound", "ImpactSoundEvent", "ImpactSound",
    "ImpactSoundThrottleTimer", "BounceSound", "AudioEventName", "AudioGroups",
    "SoundOnRegen", "SoundOfMoveUp", "SoundOfMoveDown", "SoundOfRegret", "Music",
    "AmbientMusic", "Sound",
};

bool isAudioKey(const std::string& key) {
    return std::find(std::begin(kAudioKeys), std::end(kAudioKeys), key) != std::end(kAudioKeys);
}

using PairCounts = std::map<std::pair<std::string, std::string>, std::size_t>;

void countValue(PairCounts& counts, std::set<std::string>& keys, const std::string& key,
                const std::string& value) {
    keys.insert(key);
    ++counts[{key, value}];
}

void collectStrings(const nlohmann::json& node, const std::string& key, PairCounts& counts,
                    std::set<std::string>& keys) {
    if (node.is_string()) {
        countValue(counts, keys, key, node.get<std::string>());
    } else if (node.is_array()) {
        for (const auto& item : node) {
            if (item.is_string())
                countValue(counts, keys, key, item.get<std::string>());
            else if (item.is_object() || item.is_array())
                collectStrings(item, key, counts, keys);
        }
    } else if (node.is_object()) {
        for (const auto& item : node.items()) {
            if (item.value().is_string())
                countValue(counts, keys, key, item.value().get<std::string>());
            else if (item.value().is_array() || item.value().is_object())
                collectStrings(item.value(), key, counts, keys);
        }
    }
}

void walkPack(const nlohmann::json& node, PairCounts& counts, std::set<std::string>& keys) {
    if (node.is_object()) {
        for (const auto& item : node.items()) {
            if (isAudioKey(item.key())) collectStrings(item.value(), item.key(), counts, keys);
            walkPack(item.value(), counts, keys);
        }
    } else if (node.is_array()) {
        for (const auto& item : node) walkPack(item, counts, keys);
    }
}

std::string percent(std::size_t hit, std::size_t total) {
    if (total == 0) return "n/a";
    std::ostringstream text;
    text.setf(std::ios::fixed);
    text.precision(1);
    text << (100.0 * static_cast<double>(hit) / static_cast<double>(total)) << '%';
    return text.str();
}

} // namespace

double PackCrossCheck::exactRate() const {
    const std::size_t total = values - emptyValues;
    return total == 0 ? 0.0 : static_cast<double>(exactValues) / static_cast<double>(total);
}

double PackCrossCheck::aliasRate() const {
    const std::size_t total = values - emptyValues;
    return total == 0 ? 0.0
                      : static_cast<double>(exactValues + aliasValues) / static_cast<double>(total);
}

std::string PackCrossCheck::text() const {
    if (!error.empty()) return "pack cross-check: " + error;
    std::ostringstream text;
    text << "packs: " << files.size() << " file(s); keys: ";
    for (std::size_t i = 0; i < keysFound.size(); ++i)
        text << (i == 0 ? "" : ", ") << keysFound[i];
    text << "; values " << values << " (" << emptyValues << " empty); exact " << exactValues << '/'
         << (values - emptyValues) << " = " << percent(exactValues, values - emptyValues)
         << "; with aliases " << (exactValues + aliasValues) << '/' << (values - emptyValues)
         << " = " << percent(exactValues + aliasValues, values - emptyValues) << "; unmatched "
         << unmatched.size() << " distinct";
    if (!unmatched.empty()) {
        text << ": ";
        for (std::size_t i = 0; i < unmatched.size(); ++i) text << (i == 0 ? "" : ", ") << unmatched[i];
    }
    return text.str();
}

EventMap::EventMap()
    : bindings_{
          // The 11 classes the task pins, then the rest of the shipped sfx.
          {"plant", "plant", "sfx_plant"},
          {"plant_sprout", "plant_sprout", "plant"},
          {"shoot", "sfx_shoot", ""},
          {"hit", "shoot_hit", "sfx_shoot"},
          {"sun", "sfx_sun", "sun_collect"},
          {"sun_collect", "sun_collect", "sfx_sun"},
          {"wave", "sfx_wave", ""},
          {"die", "sfx_die", "zombie_groan2"},
          {"click", "sfx_click", ""},
          {"error", "sfx_error", ""},
          {"shovel", "sfx_shovel", "sfx_click"},
          {"win", "victory", "menu"},
          {"lose", "defeat", "menu"},
          {"ui_open", "ui_open", "sfx_click"},
          {"ui_close", "ui_close", "sfx_click"},
          {"coin", "coin_drop", "sfx_click"},
          {"gem", "gem_spawn", "coin_drop"},
          {"zombie_groan", "zombie_groan", "zombie_groan2"},
          {"zombie_groan2", "zombie_groan2", "zombie_groan"},
          {"plant_food", "plant_sprout", "plant"},
          {"sfx_plant", "sfx_plant", "plant"},
      },
      gameEvents_{
          // Exactly the names `engine::World::events()` emits. An empty `sound` is a decision,
          // not an oversight: the 18 shipped sfx have no sample for it, and borrowing one would
          // make the report lie about what the player hears.
          {"action_unknown", "sfx_error", "", "unknown action reported as an error"},
          {"armor_absorbed", "shoot_hit", "sfx_shoot", "armour contact is a hit"},
          {"armor_blocked", "shoot_hit", "sfx_shoot", "armour contact is a hit"},
          {"armor_broken", "shoot_hit", "sfx_shoot", "armour contact is a hit"},
          {"armor_dropped", "", "", "no armour-drop sample in the shipped assets"},
          {"boss_action_unwired", "", "", "diagnostic event, not a sound"},
          {"boss_died", "sfx_die", "zombie_groan2", "bosses die like every other zombie"},
          {"boss_fire", "sfx_shoot", "", "boss projectile launch"},
          {"boss_spawn", "zombie_groan", "", "no dedicated roar; the zombie groan is the closest sample"},
          {"boss_stage", "", "", "stage banner, no sample"},
          {"boss_unavailable", "", "", "diagnostic event, not a sound"},
          {"explosion", "", "", "no explosion sample in the shipped assets"},
          {"fusion", "", "", "fusion has no sample"},
          {"input_late", "", "", "diagnostic event, not a sound"},
          {"input_rejected", "sfx_error", "", "rejected input is the error sound"},
          {"level_lost", "sfx_die", "", "no game-over sample; the death sting stands in"},
          {"level_start", "", "", "diagnostic event, not a sound"},
          {"level_won", "victory", "menu", "the victory track is the shipped win jingle"},
          {"mower_spent", "", "", "no mower sample"},
          {"mower_triggered", "sfx_wave", "", "mower sweep uses the wave whoosh"},
          {"plant_died", "", "", "no plant-death sample in the shipped assets"},
          {"plant_fed", "plant_sprout", "plant", "plant food sprouts the plant"},
          {"plant_removed", "", "", "removal is silent"},
          {"planted", "plant", "sfx_plant", "planting"},
          {"projectile_unknown", "", "", "diagnostic event, not a sound"},
          {"projectile_variant_fallback", "", "", "diagnostic event, not a sound"},
          {"shot_fired", "sfx_shoot", "", "every successful spawnShot"},
          {"shot_hit", "shoot_hit", "sfx_shoot", "projectile contact"},
          {"shovelled", "sfx_shovel", "sfx_click", "shovel"},
          {"sun_collected", "sun_collect", "sfx_sun", "sun pickup"},
          {"sun_spawned", "sfx_sun", "sun_collect", "a sun appears"},
          {"time_budget_exceeded", "sfx_error", "", "the run ran out of time: error feedback"},
          {"wave_spawn", "sfx_wave", "", "wave incoming"},
          {"wave_spawn_rejected", "", "", "diagnostic event, not a sound"},
          {"zombie_died", "sfx_die", "zombie_groan2", "zombie death"},
          {"zombie_hop", "", "", "no hop sample"},
          {"zombie_removed", "", "", "removal is silent"},
          {"zombie_smash", "", "", "no smash sample"},
          {"zombie_steal", "", "", "no steal sample"},
          {"zombie_summon", "zombie_groan", "zombie_groan2", "summoning moan"},
      } {}

std::vector<std::string> EventMap::unwiredGameEvents() const {
    std::vector<std::string> unwired;
    for (const auto& entry : gameEvents_)
        if (entry.sound.empty()) unwired.push_back(entry.event);
    std::sort(unwired.begin(), unwired.end());
    return unwired;
}

MusicSelection selectMusic(const AudioCatalog& catalog, const EventMap& events,
                           std::string_view world, bool intro) {
    MusicSelection selection;
    selection.world = std::string(world);
    const std::string loop = events.music(world, false);
    const std::string opening = events.music(world, true);
    const std::string preferred = intro ? opening : loop;
    const std::string secondary = intro ? loop : opening;
    for (const auto& candidate : {preferred, secondary}) {
        if (candidate.empty()) continue;
        const Sound* sound = catalog.find(candidate);
        if (sound == nullptr) continue;
        selection.track = candidate;
        selection.present = sound->present;
        selection.note = candidate == preferred ? "world track" : "world track (alternate)";
        return selection;
    }
    // Nothing matched by name: fall back to a track recovered under audio/obb/. MUSIC_* wins over
    // STARTUPMUSIC_* because the latter is the boot jingle.
    const Sound* obb = nullptr;
    for (const auto& sound : catalog.sounds) {
        if (sound.kind != SoundKind::obb || sound.format != "ogg" || !sound.present) continue;
        if (obb == nullptr) obb = &sound;
        if (sound.name.rfind("MUSIC_", 0) == 0) {
            obb = &sound;
            break;
        }
    }
    if (obb != nullptr) {
        selection.track = obb->name;
        selection.fromObb = true;
        selection.present = true;
        selection.note = "obb/MUSIC_* fallback";
        return selection;
    }
    selection.note = "no track in the catalog";
    return selection;
}

std::vector<MusicSelection> planMusic(const AudioCatalog& catalog, const EventMap& events) {
    std::vector<MusicSelection> plan;
    for (const char* world : {"frontyard", "egypt", "pirate", "cowboy", "dark", "beach", "future",
                              "lostcity", "chinesegarden", "losantosvice", "lunarrainbowmarket",
                              "menu"})
        plan.push_back(selectMusic(catalog, events, world, false));
    return plan;
}

const EventBinding* EventMap::find(std::string_view event) const {
    const std::string norm = normalize(event);
    if (norm.empty()) return nullptr;
    for (const auto& binding : bindings_)
        if (binding.event == norm) return &binding;
    return nullptr;
}

std::string EventMap::soundFor(std::string_view event) const {
    const EventBinding* binding = find(event);
    return binding == nullptr ? std::string{} : binding->sound;
}

std::string EventMap::fallbackFor(std::string_view event) const {
    const EventBinding* binding = find(event);
    return binding == nullptr ? std::string{} : binding->fallback;
}

std::string EventMap::soundForEngineEvent(std::string_view event) const {
    const std::string name(event);
    for (const auto& entry : gameEvents_)
        if (entry.event == name) return entry.sound;
    return {};
}

std::string EventMap::music(std::string_view world, bool intro) const {
    const std::string norm = normalize(world);
    if (norm.empty()) return {};
    struct Track {
        const char* world;
        const char* loop;
        const char* intro;
    };
    static constexpr Track kTracks[] = {
        {"frontyard", "frontyard_loop", "frontyard_intro"},
        {"egypt", "egypt_loop", "egypt_intro"},
        {"pirate", "pirate_loop", "pirate_intro"},
        {"cowboy", "cowboy_loop", "cowboy_intro"},
        {"dark", "dark_loop", "dark_intro"},
        {"beach", "beach_loop", "beach_intro"},
        {"future", "future_loop", "future_intro"},
        {"lostcity", "lostcity_loop", "lostcity_intro"},
        {"chinesegarden", "chinesegarden_loop", "chinesegarden_intro"},
        {"losantosvice", "losantosvice_loop", "losantosvice_intro"},
        {"lunarrainbowmarket", "lunarrainbowmarket_loop", "lunarrainbowmarket_intro"},
        {"menu", "menu", ""},
        {"title", "menu", ""},
        {"map", "chinesegarden_map", ""},
        {"chinesegarden_map", "chinesegarden_map", ""},
        {"victory", "victory", ""},
        {"defeat", "defeat", ""},
    };
    for (const auto& track : kTracks) {
        if (norm != track.world) continue;
        if (intro && track.intro[0] != '\0') return track.intro;
        return track.loop;
    }
    return {};
}

EventHit EventMap::resolve(std::string_view key, std::string_view value) const {
    EventHit hit;
    hit.key = std::string(key);
    hit.value = std::string(value);
    const std::string norm = normalize(value);
    if (norm.empty()) return hit;

    // 1. The value already is a canonical event name.
    if (const EventBinding* binding = find(norm)) {
        hit.sound = binding->sound;
        hit.via = "event";
        hit.exact = true;
        return hit;
    }
    // 2. Strip the wrapper prefixes the packs like to add, then retry the exact name.
    static constexpr std::string_view kPrefixes[] = {"play_", "sound_", "sfx_", "audio_",
                                                     "music_", "event_", "ui_"};
    for (const std::string_view prefix : kPrefixes) {
        if (!startsWith(norm, prefix)) continue;
        if (const EventBinding* binding = find(norm.substr(prefix.size()))) {
            hit.sound = binding->sound;
            hit.via = "exact";
            hit.exact = true;
            return hit;
        }
    }
    // 3. Fall back to the trailing token: `plant_citron_attack` is an attack, not a plant.
    const std::vector<std::string> tokens = splitTokens(norm);
    for (auto token = tokens.rbegin(); token != tokens.rend(); ++token) {
        for (const auto& alias : kAliases) {
            if (*token != alias.token) continue;
            if (const EventBinding* binding = find(alias.event)) {
                hit.sound = binding->sound;
                hit.via = std::string("alias:") + alias.token;
                hit.aliased = true;
                return hit;
            }
        }
    }
    return hit;
}

PackCrossCheck crossCheckPacks(const std::vector<std::filesystem::path>& packs,
                               const EventMap& map) {
    PackCrossCheck result;
    PairCounts counts;
    std::set<std::string> keys;
    for (const auto& pack : packs) {
        std::ifstream input(pack, std::ios::binary);
        if (!input) {
            result.error = "cannot open " + pack.string();
            return result;
        }
        nlohmann::json document;
        try {
            input >> document;
        } catch (const std::exception& error) {
            result.error = pack.string() + ": " + error.what();
            return result;
        }
        result.files.push_back(pack.filename().string());
        walkPack(document, counts, keys);
    }
    result.keysFound.assign(keys.begin(), keys.end());
    result.pairs = counts.size();
    for (const auto& [key_value, count] : counts) {
        const EventHit hit = map.resolve(key_value.first, key_value.second);
        result.values += count;
        if (hit.value.empty()) {
            result.emptyValues += count;
        } else if (hit.exact) {
            result.exactValues += count;
        } else if (hit.aliased) {
            result.aliasValues += count;
        }
        result.hits.push_back([&] {
            EventHit stored = hit;
            stored.count = count;
            return stored;
        }());
        if (hit.sound.empty()) {
            result.unmatched.push_back(hit.key + "=" +
                                       (hit.value.empty() ? std::string("<empty>") : hit.value));
        }
    }
    return result;
}

std::vector<std::filesystem::path> locateAudioPacks(const std::filesystem::path& dir) {
    std::vector<std::filesystem::path> found;
    if (dir.empty()) return found;
    std::error_code ec;
    if (!std::filesystem::is_directory(dir, ec)) return found;
    for (const char* name : {"pkg_2073_PlantPropertySheet.json",
                             "pkg_2082_ProjectilePropertySheet.json"}) {
        const auto candidate = dir / name;
        if (std::filesystem::is_regular_file(candidate, ec)) found.push_back(candidate);
    }
    return found;
}

std::filesystem::path defaultPackDirectory(const std::filesystem::path& assetRoot) {
    // `<repo>/native/tests`-relative callers pass the assets root directly, so the packs sit two
    // levels above it (`assets` -> `PvZ2SHUTTLE` -> workspace) under `work/obb_packages`.
    std::error_code ec;
    const auto workspace = assetRoot.parent_path().parent_path();
    const auto candidate = workspace / "work" / "obb_packages";
    if (std::filesystem::is_directory(candidate, ec)) return candidate;
    return {};
}

} // namespace pvz
