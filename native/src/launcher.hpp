#pragma once

#include <filesystem>

namespace shuttle {

void runLauncher(const std::filesystem::path& assetRoot, bool smokeTest);

}
