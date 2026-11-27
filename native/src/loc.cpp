#include "loc.hpp"

// Reads `generated/lawn_strings.json` (written by `tools/contentc/loc.py`).
//
// Two rules shape this file:
//
//   * a missing or unreadable table is an empty table, not a crash — every caller is a screen that
//     must still paint, and the one thing worse than an untranslated label is a screen that will not
//     open because a data file is absent;
//   * no logging. A key the table does not know is a data fact; printing it would drown the warnings
//     that matter.

#include <nlohmann/json.hpp>

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <system_error>
#include <utility>
#include <vector>

namespace fs = std::filesystem;

namespace pvz::loc {
namespace {

using Json = nlohmann::json;

constexpr const char* kFileName = "lawn_strings.json";

/// Environment lookup without the deprecation MSVC attaches to `std::getenv` (C4996); the checked
/// variant also frees the copy it hands back.
std::string readVariable(const char* name) {
#if defined(_MSC_VER)
    char* value = nullptr;
    std::size_t length = 0;
    if (_dupenv_s(&value, &length, name) != 0 || value == nullptr) return {};
    std::string text(value);
    std::free(value);
    return text;
#else
    const char* value = std::getenv(name);
    return value == nullptr ? std::string() : std::string(value);
#endif
}

/// The roots worth trying, most specific first. `contentRoot` wins; the process environment and the
/// current directory only get a vote when the caller passed nothing.
std::vector<fs::path> candidates(const std::string& contentRoot) {
    std::vector<fs::path> out;

    if (!contentRoot.empty()) {
        const fs::path root(contentRoot);
        out.push_back(root / kFileName);
        out.push_back(root / "generated" / kFileName);
        out.push_back(root / "native" / "generated" / kFileName);
        out.push_back(root / ".." / "native" / "generated" / kFileName);
        out.push_back(root / ".." / ".." / "native" / "generated" / kFileName);
        // A caller that hands over the generated directory itself hits the first candidate.
        return out;
    }

    const std::string configured = readVariable("PVZ_GENERATED_DIR");
    if (!configured.empty()) {
        out.emplace_back(fs::path(configured) / kFileName);
    }

    // Walk up from the working directory, the same way `engine::generatedDir()` finds the other
    // generated tables (the source path cannot be baked in: it contains non-ASCII characters that
    // cl.exe would read in the ANSI code page).
    std::error_code failed;
    fs::path directory = fs::current_path(failed);
    for (int depth = 0; depth < 8 && !failed && !directory.empty(); ++depth) {
        out.push_back(directory / "native" / "generated" / kFileName);
        out.push_back(directory / "generated" / kFileName);
        const fs::path parent = directory.parent_path();
        if (parent == directory) break;
        directory = parent;
    }
    return out;
}

std::string textFrom(const Json& object, const char* key) {
    const auto found = object.find(key);
    if (found == object.end() || !found->is_string()) return {};
    return found->get<std::string>();
}

/// Parse one file into `into`. Returns false with `error` set when the payload is not a table.
bool parseInto(const fs::path& file, Strings& into) {
    std::ifstream input(file, std::ios::binary);
    if (!input) {
        into.error = "cannot open " + file.string();
        return false;
    }
    Json document;
    try {
        input >> document;
    } catch (const std::exception& problem) {
        into.error = std::string("not valid JSON in ") + file.string() + ": " + problem.what();
        return false;
    }
    if (!document.is_object()) {
        into.error = file.string() + ": the root is not an object";
        return false;
    }
    const auto strings = document.find("strings");
    if (strings == document.end() || !strings->is_object()) {
        into.error = file.string() + ": `strings` is missing or not an object";
        return false;
    }

    into.rows.reserve(strings->size());
    for (auto entry = strings->begin(); entry != strings->end(); ++entry) {
        if (!entry.value().is_object()) continue;
        Entry row;
        row.zh = textFrom(entry.value(), "zh");
        row.en = textFrom(entry.value(), "en");
        into.rows.emplace_hint(into.rows.end(), entry.key(), std::move(row));
    }
    into.source = file.string();
    return true;
}

bool blank(const std::string& text) {
    for (const char character : text) {
        if (character != ' ' && character != '\t' && character != '\n' && character != '\r') {
            return false;
        }
    }
    return true;
}

} // namespace

const Entry* Strings::find(const std::string& key) const {
    const auto found = rows.find(key);
    return found == rows.end() ? nullptr : &found->second;
}

Strings load(const std::string& contentRoot) {
    Strings strings;
    const std::vector<fs::path> probes = candidates(contentRoot);
    std::string firstFailure;
    for (const fs::path& probe : probes) {
        std::error_code failed;
        if (!fs::is_regular_file(probe, failed) || failed) continue;
        Strings parsed;
        if (parseInto(probe, parsed)) return parsed;
        if (firstFailure.empty()) firstFailure = parsed.error;
    }
    // Nothing readable under the given root: an empty table, and the reason kept for the caller that
    // wants to print it once at start-up. `resolve()` never looks at `error`.
    strings.error = firstFailure.empty()
                        ? std::string("no ") + kFileName + " under " +
                              (contentRoot.empty() ? std::string("the working directory")
                                                   : contentRoot)
                        : firstFailure;
    return strings;
}

std::string resolve(const Strings& strings, const std::string& key, const std::string& fallback) {
    const Entry* row = strings.find(key);
    if (row == nullptr) return fallback;
    if (!row->zh.empty() && !blank(row->zh)) return row->zh;
    if (!row->en.empty() && !blank(row->en)) return row->en;
    return fallback;
}

} // namespace pvz::loc
