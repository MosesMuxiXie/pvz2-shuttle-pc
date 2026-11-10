#pragma once

#include <filesystem>

namespace shuttle {

void importPythonSave(const std::filesystem::path& source, const std::filesystem::path& destination);
void recordFirstBattleWin(const std::filesystem::path& path);

}
