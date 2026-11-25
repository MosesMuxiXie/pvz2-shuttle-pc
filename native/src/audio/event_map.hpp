#pragma once
#include <cstddef>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json.hpp>

#include "audio/audio_catalog.hpp"

// Game events (`planted`, `shot_hit`, ...) to catalog sound names, plus a cross-check of the
// names the shipped property sheets actually ask for. The cross-check exists because the packs
// speak a different vocabulary (`Play_Throw`, `Play_ImagoAttack`) than the catalog: any pack
// value that cannot be resolved is reported, never silently ignored.
namespace pvz {

/// One `engine::World::events()` name and the sample it plays. `sound` empty means the shipped
/// assets have no fitting sample: the event is then listed as unwired instead of borrowing one.
struct GameEventSound {
    std::string event;
    std::string sound;
    std::string fallback;
    std::string note;
};

struct EventBinding {
    std::string event;    ///< canonical name the game code dispatches
    std::string sound;    ///< catalog sound played for it
    std::string fallback; ///< played when `sound` is missing or undecodable, may be empty
};

/// Where a pack event value landed.
struct EventHit {
    std::string key;     ///< pack key, e.g. `ProjectileLaunchSound`
    std::string value;   ///< raw value as written in the pack
    std::string sound;   ///< resolved catalog sound, empty when unmatched
    std::string via;     ///< `event`, `exact`, `alias:<token>` or empty when unmatched
    std::size_t count = 0;
    bool exact = false;  ///< the value itself is a known event name
    bool aliased = false; ///< resolved through a token alias
};

struct PackCrossCheck {
    std::vector<std::string> files;      ///< packs actually read
    std::vector<std::string> keysFound;  ///< audio keys present in those packs
    std::vector<EventHit> hits;          ///< every distinct (key, value) pair, sorted
    std::vector<std::string> unmatched;  ///< `key=value` for every unresolved pair
    std::size_t pairs = 0;
    std::size_t values = 0;              ///< total occurrences, empty strings included
    std::size_t emptyValues = 0;
    std::size_t exactValues = 0;
    std::size_t aliasValues = 0;
    std::string error;                   ///< set when a pack could not be read

    double exactRate() const;
    double aliasRate() const;
    std::string text() const;
};

class EventMap {
public:
    EventMap();

    /// Explicit table lookup; null when the event is unknown.
    const EventBinding* find(std::string_view event) const;
    /// Resolved sound for an event, empty when unknown.
    std::string soundFor(std::string_view event) const;
    /// Fallback sound for an event, empty when the binding has none.
    std::string fallbackFor(std::string_view event) const;
    /// Sound for one `engine::World::events()` name. Empty when the table leaves it null
    /// (deliberately silent) and also when the name is unknown; callers must report both
    /// instead of substituting a sample of their own.
    std::string soundForEngineEvent(std::string_view event) const;
    /// BGM track for a world name (`frontyard`, `menu`, ...); empty when unknown.
    std::string music(std::string_view world, bool intro = false) const;
    const std::vector<EventBinding>& bindings() const { return bindings_; }

    /// Every name `engine::World::events()` emits, mapped or explicitly null.
    const std::vector<GameEventSound>& gameEvents() const { return gameEvents_; }
    /// `engine::World::events()` names whose `sound` is empty, sorted. Never silently dropped.
    std::vector<std::string> unwiredGameEvents() const;

    /// Resolution used for pack values: exact event name first, then the trailing token.
    EventHit resolve(std::string_view key, std::string_view value) const;

private:
    std::vector<EventBinding> bindings_;
    std::vector<GameEventSound> gameEvents_;
};

/// Which track a world actually plays, and why. The rule is `<world>_loop` first, then `<world>_intro`,
/// then a track recovered under `audio/obb/`; `note` names the step that fired.
struct MusicSelection {
    std::string world;
    std::string track;
    bool fromObb = false;
    bool present = false;
    std::string note;
};

MusicSelection selectMusic(const AudioCatalog& catalog, const EventMap& events,
                           std::string_view world, bool intro = false);

/// One selection per world the client can start, in the order they appear in the map.
std::vector<MusicSelection> planMusic(const AudioCatalog& catalog, const EventMap& events);

/// Reads the shipped property sheets and resolves every audio value they contain.
/// `packs` may be empty, in which case `locateAudioPacks` is consulted through the caller.
PackCrossCheck crossCheckPacks(const std::vector<std::filesystem::path>& packs, const EventMap& map);

/// `pkg_2073_PlantPropertySheet.json` and `pkg_2082_ProjectilePropertySheet.json` under `dir`.
std::vector<std::filesystem::path> locateAudioPacks(const std::filesystem::path& dir);

/// Returns the `work/obb_packages` directory that sits beside the assets tree, or an empty path.
std::filesystem::path defaultPackDirectory(const std::filesystem::path& assetRoot);

} // namespace pvz
