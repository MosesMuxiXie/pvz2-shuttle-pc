#pragma once

// The compiled localisation table (`generated/lawn_strings.json`).
//
// Every screen that showed a localisation key used to fall back to the mechanical transcription in
// `achievements_view.cpp` (`ACHIEVE_ALL_IN_JEST_TITLE` → "All In Jest"). The OBB ships the real
// strings in two property sheets — `pkg_0231_LawnStringsData.json` (English) and
// `pkg_0232_LawnStringsData.json` (Chinese) — and `tools/contentc/loc.py` joins them into one JSON
// table keyed by the LawnStrings id, verbatim (no case folding: a handful of shipped ids carry a
// space, `&`, `#` or `$`).
//
// This file is the runtime half: read the table, answer a key. It deliberately has no SDL and no
// engine dependency — `load()` takes a content root, so a screen passes its content directory and a
// test passes a fixture without either of them linking the engine.

#include <cstddef>
#include <string>
#include <unordered_map>

namespace pvz::loc {

/// One row of the table: the two languages the OBB ships. Either side may be empty (3 keys exist
/// only in English; ~77 rows have a blank text on one side).
struct Entry {
    std::string zh;
    std::string en;
};

/// The compiled table. `source` is the file that was actually read (`""` when nothing was found),
/// `error` says why the table is empty when it is — nothing here throws, because a missing table
/// must not stop a screen from starting.
struct Strings {
    std::string source;
    std::string error;
    std::unordered_map<std::string, Entry> rows;

    std::size_t size() const { return rows.size(); }
    bool empty() const { return rows.empty(); }

    /// The row for `key`, or nullptr. Exact match; the id is the sheet's spelling.
    const Entry* find(const std::string& key) const;
};

/// Read `<contentRoot>/…/lawn_strings.json`.
///
/// Probe order when `contentRoot` is not empty: `<root>/lawn_strings.json`, `<root>/generated/`,
/// `<root>/native/generated/`, `<root>/../native/generated/`, `<root>/../../native/generated/`.
/// When `contentRoot` is empty the fallback is `PVZ_GENERATED_DIR` and then a walk up from the
/// current directory, which is how every other generated table in this tree is found.
///
/// Never throws: an unknown root, an unreadable file and malformed JSON all come back as an empty
/// `Strings` with `error` set.
Strings load(const std::string& contentRoot);

/// Chinese first, then English, then `fallback`.
///
/// The build's target language is Chinese, so `zh` wins and `en` only fills in when the Chinese side
/// is missing or blank. A blank side counts as absent, never as a result — the caller's own
/// transcription (`humanizeGameKey`) stays the last resort, so a key the table does not know still
/// renders as something readable instead of nothing. No logging: a missing translation is a data
/// fact, not a runtime error.
std::string resolve(const Strings& strings, const std::string& key, const std::string& fallback);

} // namespace pvz::loc
