#pragma once

#include <filesystem>
#include <iosfwd>

namespace shuttle {

void replayFirst(const std::filesystem::path& content, const std::filesystem::path& scenario, std::ostream& output);

}
