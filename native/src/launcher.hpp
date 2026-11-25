#pragma once
#include <filesystem>
namespace pvz {
// Smoke mode renders the identical frame with SDL's software renderer, without a display.
void runLauncher(const std::filesystem::path& assetRoot, bool smokeTest,
                 const std::filesystem::path& snapshot = {});
} // namespace pvz
