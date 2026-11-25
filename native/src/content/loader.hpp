#pragma once

#include <filesystem>
#include <stdexcept>
#include <string>

#include "content/model.hpp"

namespace pvz::content {

/// Raised for a pack that cannot be trusted. The message always names the
/// record and field, so a data regression is diagnosable from the log alone.
struct LoadError : std::runtime_error {
    using std::runtime_error::runtime_error;
};

/// Read and validate `native/generated/content.pack`.
ContentPack loadContentPack(const std::filesystem::path& path);

/// Validate a pack already in memory. `origin` only labels error messages.
ContentPack parseContentPack(const std::string& text, const std::string& origin);

/// Version this loader understands.
inline constexpr int kPackFormat = 1;

}  // namespace pvz::content
