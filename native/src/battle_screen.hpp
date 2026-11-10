#pragma once

#include <filesystem>

namespace shuttle {

void runFirstBattle(const std::filesystem::path& content, const std::filesystem::path& save, bool smoke);
std::filesystem::path defaultSavePath();
std::filesystem::path bundledContentPath();

}
