#include "save.hpp"

#include "catalog.hpp"

#include <algorithm>
#include <fstream>
#include <random>
#include <stdexcept>

namespace shuttle {
namespace {

namespace fs = std::filesystem;
using nlohmann::json;

json readSave(const fs::path& path) {
    try {
        std::ifstream input(path, std::ios::binary);
        if (!input) {
            throw std::runtime_error("cannot open save");
        }
        auto data = json::parse(input);
        if (!data.is_object()) {
            throw std::runtime_error("save must be a JSON object");
        }
        if (const auto version = data.find("version"); version != data.end() &&
            (!version->is_number_integer() || (*version != 2 && *version != 3))) {
            throw std::runtime_error("unsupported save version");
        }
        if (const auto completed = data.find("completed"); completed != data.end() && !completed->is_null() &&
            (!completed->is_array() || !std::ranges::all_of(*completed, &json::is_string))) {
            throw std::runtime_error("completed levels must be an array of strings");
        }
        return data;
    } catch (const std::exception& error) {
        throw std::runtime_error(utf8Path(path) + ": " + error.what());
    }
}

class StagedSave {
public:
    explicit StagedSave(const fs::path& parent) {
        fs::create_directories(parent);
        std::random_device random;
        for (int attempt = 0; attempt < 8; ++attempt) {
            auto candidate = parent / (".shuttle-save-" + std::to_string(random()));
            if (fs::create_directory(candidate)) {
                directory_ = std::move(candidate);
                return;
            }
        }
        throw std::runtime_error("cannot create a temporary save directory");
    }

    StagedSave(const StagedSave&) = delete;
    StagedSave& operator=(const StagedSave&) = delete;

    ~StagedSave() {
        std::error_code error;
        fs::remove(path(), error);
        fs::remove(directory_, error);
    }

    fs::path path() const { return directory_ / "save.json"; }

private:
    fs::path directory_;
};

bool writeSave(const fs::path& destination, const json& data, bool replace) {
    try {
        const auto parent = destination.has_parent_path() ? destination.parent_path() : fs::path(".");
        const StagedSave staged(parent);
        std::ofstream output;
        output.exceptions(std::ios::failbit | std::ios::badbit);
        output.open(staged.path(), std::ios::binary);
        output << data.dump(2) << '\n';
        output.close();
        if (replace) {
            fs::rename(staged.path(), destination);
        } else {
            std::error_code error;
            fs::create_hard_link(staged.path(), destination, error);
            if (error == std::errc::file_exists) {
                return false;
            }
            if (error) {
                throw std::system_error(error, "cannot publish save");
            }
        }
        return true;
    } catch (const std::exception& error) {
        throw std::runtime_error(utf8Path(destination) + ": " + error.what());
    }
}

}

void importPythonSave(const std::filesystem::path& source, const std::filesystem::path& destination) {
    if (!writeSave(destination, readSave(source), false)) {
        throw std::runtime_error(utf8Path(destination) + ": destination save already exists");
    }
}

void recordFirstBattleWin(const std::filesystem::path& path) {
    constexpr auto firstLevel = "frontyard:0";
    if (!fs::exists(path)) {
        const json fresh = {{"version", 3}, {"completed", json::array({firstLevel})}};
        if (writeSave(path, fresh, false)) {
            return;
        }
    }
    auto data = readSave(path);
    auto& completed = data["completed"];
    if (completed.is_null()) {
        completed = json::array();
    }
    if (std::ranges::find(completed, firstLevel) == completed.end()) {
        completed.push_back(firstLevel);
        writeSave(path, data, true);
    }
}

}
