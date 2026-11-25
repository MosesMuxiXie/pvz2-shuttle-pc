#include "save.hpp"
#include <algorithm>
#include <chrono>
#include <fstream>
#include <limits>
#include <set>
#include <stdexcept>
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#else
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <unistd.h>
#endif
namespace pvz {
namespace fs = std::filesystem;
namespace {
void check(bool ok, const std::string& message) {
    if (!ok)
        throw std::runtime_error("save: " + message);
}
std::int64_t integer(const Json& j, const std::string& key, std::int64_t fallback = 0) {
    if (!j.contains(key))
        return fallback;
    const auto& v = j.at(key);
    check(v.is_number_integer(), key + " must be an integer");
    if (v.is_number_unsigned())
        check(v.get<std::uint64_t>() <= static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max()),
              key + " overflows");
    const auto n = v.get<std::int64_t>();
    check(n >= 0, key + " must be nonnegative");
    return n;
}
void ids(Json& j, const std::string& key) {
    if (!j.contains(key) || j[key].is_null())
        j[key] = Json::array();
    check(j[key].is_array(), key + " must be an array");
    for (const auto& value : j[key])
        check(value.is_string() && !value.get<std::string>().empty(), key + " must contain nonempty IDs");
}
std::string read(const fs::path& path) {
    std::ifstream in(path, std::ios::binary | std::ios::ate);
    check(bool(in), pathUtf8(path) + ": cannot open");
    const auto size = in.tellg();
    check(size > 0 && size <= 16 * 1024 * 1024, pathUtf8(path) + ": save must be between 1 byte and 16 MiB");
    std::string bytes(static_cast<std::size_t>(size), '\0');
    in.seekg(0);
    check(bool(in.read(bytes.data(), static_cast<std::streamsize>(bytes.size()))),
          pathUtf8(path) + ": cannot read");
    return bytes;
}
Json parse(const std::string& bytes, const fs::path& path) {
    try {
        return Json::parse(bytes);
    } catch (const Json::exception& e) {
        throw std::runtime_error(pathUtf8(path) + ": " + e.what());
    }
}
void validateNative(const Json& j) {
    check(j.is_object() && j.value("format", std::string{}) == "pvz2-shuttle-native", "not a native save");
    check(integer(j, "schema_version") == 1, "unsupported native schema version");
    check(j.contains("progress") && j["progress"].is_object(), "missing progress object");
    check(integer(j["progress"], "version") == 3, "unsupported progress version");
    // Validate through the same version-3 reader without mutating the saved document.
    (void)migratePythonSave(j["progress"], integer(j, "imported_at"));
}
void installNew(const fs::path& destination, const std::string& bytes) {
    check(!fs::exists(destination), pathUtf8(destination) + ": already exists; refusing to overwrite");
    fs::path temp;
#ifdef _WIN32
    HANDLE handle = INVALID_HANDLE_VALUE;
    for (int attempt = 0; attempt < 100 && handle == INVALID_HANDLE_VALUE; ++attempt) {
        temp = destination;
        temp += L".tmp-" + std::to_wstring(GetCurrentProcessId()) + L"-" +
                std::to_wstring(std::chrono::steady_clock::now().time_since_epoch().count()) + L"-" +
                std::to_wstring(attempt);
        handle =
            CreateFileW(temp.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
        if (handle == INVALID_HANDLE_VALUE && GetLastError() != ERROR_FILE_EXISTS)
            throw std::runtime_error(
                pathUtf8(temp) + ": cannot create temporary save, Win32=" + std::to_string(GetLastError()));
    }
    check(handle != INVALID_HANDLE_VALUE, "cannot allocate temporary save");
    DWORD written = 0;
    const bool ok = WriteFile(handle, bytes.data(), static_cast<DWORD>(bytes.size()), &written, nullptr) &&
                    written == bytes.size() && FlushFileBuffers(handle);
    CloseHandle(handle);
    if (!ok) {
        DeleteFileW(temp.c_str());
        throw std::runtime_error(pathUtf8(temp) + ": failed writing/flushing temporary save");
    }
    if (!MoveFileExW(temp.c_str(), destination.c_str(), MOVEFILE_WRITE_THROUGH)) {
        const auto error = GetLastError();
        DeleteFileW(temp.c_str());
        throw std::runtime_error(pathUtf8(destination) +
                                 ": cannot atomically create save, Win32=" + std::to_string(error));
    }
#else
    int fd = -1;
    for (int attempt = 0; attempt < 100 && fd < 0; ++attempt) {
        temp = destination;
        temp += ".tmp-" + std::to_string(getpid()) + "-" +
                std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + "-" +
                std::to_string(attempt);
        fd = ::open(temp.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0600);
        if (fd < 0 && errno != EEXIST)
            throw std::runtime_error(pathUtf8(temp) + ": " + std::strerror(errno));
    }
    check(fd >= 0, "cannot allocate temporary save");
    std::size_t offset = 0;
    bool ok = true;
    while (offset < bytes.size()) {
        const auto n = ::write(fd, bytes.data() + offset, bytes.size() - offset);
        if (n < 0 && errno == EINTR)
            continue;
        if (n <= 0) {
            ok = false;
            break;
        }
        offset += static_cast<std::size_t>(n);
    }
    if (::fsync(fd) != 0)
        ok = false;
    if (::close(fd) != 0)
        ok = false;
    if (!ok) {
        ::unlink(temp.c_str());
        throw std::runtime_error(pathUtf8(temp) + ": failed writing/flushing temporary save");
    }
    // link is atomic and, unlike rename(), cannot replace an existing destination.
    if (::link(temp.c_str(), destination.c_str()) != 0) {
        const auto error = errno;
        ::unlink(temp.c_str());
        throw std::runtime_error(pathUtf8(destination) + ": " + std::strerror(error));
    }
    ::unlink(temp.c_str());
    const auto parent = destination.parent_path().empty() ? fs::path(".") : destination.parent_path();
    const int directory = ::open(parent.c_str(), O_RDONLY);
    if (directory >= 0) {
        ::fsync(directory);
        ::close(directory);
    }
#endif
}
} // namespace
Json migratePythonSave(const Json& legacy, std::int64_t now) {
    check(now >= 0, "clock must be nonnegative");
    check(legacy.is_object(), "Python save must be an object");
    check(!legacy.contains("format"), "input is already a native or unknown save format");
    const auto version = integer(legacy, "version", 2);
    check(version == 2 || version == 3, "only Python save versions 2 and 3 are supported");
    Json progress = legacy;
    progress["version"] = 3;
    for (const auto& key : {"completed", "unlocked_worlds", "unlocked_plants"})
        ids(progress, key);
    for (const auto& key : {"coins", "plantfood", "keys", "keys_earned_from_stars"})
        progress[key] = integer(progress, key);
    for (const auto& key : {"settings", "stars", "best_survival"}) {
        if (!progress.contains(key) || progress[key].is_null())
            progress[key] = Json::object();
        check(progress[key].is_object(), std::string(key) + " must be an object");
    }
    for (auto& [key, stars] : progress["stars"].items()) {
        check(stars.is_array() && stars.size() <= 3, "invalid star array for " + key);
        for (auto& star : stars) {
            check(star.is_boolean() || (star.is_number_integer() && (star == 0 || star == 1)),
                  "star flags must be 0/1 or boolean");
            star = (star == true || star == 1) ? 1 : 0;
        }
    }
    for (const auto& [key, value] : progress["best_survival"].items())
        (void)integer(Json{{key, value}}, key);
    Json raw = progress.value("garden", Json::array());
    if (raw.is_null())
        raw = Json::array();
    if (raw.is_object()) {
        if (raw.contains("slots")) {
            raw = raw["slots"].get<Json>();
            check(raw.is_array(), "garden.slots must be an array");
        } else {
            Json entries = Json::array();
            for (const auto& [key, value] : raw.items()) {
                check(value.is_object(), "garden slot must be an object");
                Json item = value;
                if (!item.contains("slot")) {
                    check(!key.empty() && key.find_first_not_of("0123456789") == std::string::npos,
                          "invalid garden slot key");
                    item["slot"] = std::stoll(key);
                }
                entries.push_back(std::move(item));
            }
            raw = std::move(entries);
        }
    }
    check(raw.is_array(), "garden must be an array or slot dictionary");
    std::map<std::int64_t, Json> garden;
    for (std::size_t i = 0; i < raw.size(); ++i) {
        auto entry = raw[i];
        check(entry.is_object(), "garden entry must be an object");
        check(entry.contains("plant") && entry["plant"].is_string() &&
                  !entry["plant"].get<std::string>().empty(),
              "garden plant must be a nonempty ID");
        const auto slot = integer(entry, "slot", static_cast<std::int64_t>(i));
        const auto planted = integer(entry, "planted", now);
        auto ready = integer(entry, "ready");
        if (ready == 0) {
            const auto grow = std::max<std::int64_t>(1, integer(entry, "grow_seconds", 18000));
            check(planted <= std::numeric_limits<std::int64_t>::max() - grow, "garden time overflow");
            ready = planted + grow;
        }
        if (ready <= planted) {
            check(planted < std::numeric_limits<std::int64_t>::max(), "garden time overflow");
            ready = planted + 1;
        }
        int stage = 3;
        if (now < ready) {
            const double fraction =
                double(std::max<std::int64_t>(0, now - planted)) / double(ready - planted);
            stage = std::clamp(int(fraction * 4), 0, 2);
        }
        entry["slot"] = slot;
        entry["planted"] = planted;
        entry["ready"] = ready;
        entry["stage"] = stage;
        entry["last_water"] = integer(entry, "last_water");
        entry["watered"] = integer(entry, "watered");
        garden[slot] = std::move(entry);
    }
    progress["garden"] = Json::array();
    for (auto& [slot, entry] : garden)
        progress["garden"].push_back(std::move(entry));
    return {{"format", "pvz2-shuttle-native"},
            {"schema_version", 1},
            {"imported_from_version", version},
            {"imported_at", now},
            {"progress", std::move(progress)}};
}
Json readNativeSave(const fs::path& path) {
    const auto j = parse(read(path), path);
    try {
        validateNative(j);
    } catch (const std::exception& e) {
        throw std::runtime_error(pathUtf8(path) + ": " + e.what());
    }
    return j;
}
void importPythonSave(const fs::path& source, const fs::path& destination, std::int64_t now) {
    try {
        check(fs::absolute(source).lexically_normal() != fs::absolute(destination).lexically_normal(),
              "source and destination must differ");
        auto backup = destination;
        backup += ".legacy.json";
        check(!fs::exists(destination) && !fs::exists(backup),
              pathUtf8(destination) + ": destination or legacy backup already exists; refusing to overwrite");
        const auto original = read(source);
        const auto migrated = migratePythonSave(parse(original, source), now);
        validateNative(migrated);
        const auto output = migrated.dump(2) + "\n";
        check(output.size() <= 16 * 1024 * 1024, "serialized save exceeds 16 MiB");
        check(parse(output, destination) == migrated, "serialization verification failed");
        installNew(backup, original); // If the next operation fails, preserve this recovery copy.
        installNew(destination, output);
        check(readNativeSave(destination) == migrated, "read-back verification failed");
    } catch (const std::exception& e) {
        throw std::runtime_error(pathUtf8(source) + " -> " + pathUtf8(destination) + ": " + e.what());
    }
}
} // namespace pvz
