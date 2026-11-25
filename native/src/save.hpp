#pragma once
#include "catalog.hpp"
#include <cstdint>
namespace pvz {
// Reads only. The injected clock makes garden migrations reproducible.
Json migratePythonSave(const Json& legacy, std::int64_t now);
Json readNativeSave(const std::filesystem::path& path);
// Create-only atomic installation; never overwrites the source, destination or backup.
// Saves an exact copy of the source beside destination as <destination>.legacy.json.
void importPythonSave(const std::filesystem::path& source, const std::filesystem::path& destination,
                      std::int64_t now);
} // namespace pvz
