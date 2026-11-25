#include "save.hpp"
#include <chrono>
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace pvz;
namespace fs = std::filesystem;
void check(bool ok, const std::string& message) {
    if (!ok)
        throw std::runtime_error(message);
}
std::string bytes(const fs::path& p) {
    std::ifstream in(p, std::ios::binary);
    return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}
#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
#else
int main(int argc, char** argv) {
#endif
    try {
        check(argc == 2, "expected temp root");
        const auto root = fs::path(argv[1]) / fs::path(u8"存档 测试") /
                          std::to_string(std::chrono::steady_clock::now().time_since_epoch().count());
        fs::create_directories(root);
        Json old = {
            {"version", 2},
            {"completed", {"frontyard:1"}},
            {"unlocked_worlds", {"frontyard", "egypt"}},
            {"coins", 1234},
            {"keys", 2},
            {"stars", {{"frontyard:1", {1, 0, true}}}},
            {"settings", {{"music", false}, {"future_setting", "keep"}}},
            {"unlocked_plants", {"unknown_future_plant"}},
            {"future_progress", {{"retain", true}}},
            {"garden",
             Json::array(
                 {{{"plant", "sunflower"}, {"planted", 100}, {"ready", 1100}, {"costume", "keep"}}})}};
        auto converted = migratePythonSave(old, 600);
        const auto& p = converted["progress"];
        check(converted["schema_version"] == 1 && converted["imported_from_version"] == 2 &&
                  p["version"] == 3,
              "version migration");
        check(p["coins"] == 1234 && p["keys"] == 2 && p["stars"]["frontyard:1"] == Json({1, 0, 1}),
              "progress retention");
        check(p["garden"][0]["stage"] == 2 && p["garden"][0]["last_water"] == 0 &&
                  p["garden"][0]["watered"] == 0,
              "garden v2 migration");
        check(p["garden"][0]["costume"] == "keep" && p["future_progress"] == old["future_progress"] &&
                  p["settings"] == old["settings"] && p["unlocked_plants"] == old["unlocked_plants"],
              "unknown data retained");
        check(migratePythonSave(old, 1100)["progress"]["garden"][0]["stage"] == 3,
              "garden mature at boundary");
        auto v3 = old;
        v3["version"] = 3;
        v3["garden"] = {{"slots", Json::array({{{"slot", 4},
                                                {"plant", "wallnut"},
                                                {"planted", 100},
                                                {"ready", 200},
                                                {"watered", 2},
                                                {"last_water", 150}}})}};
        auto g = migratePythonSave(v3, 160)["progress"]["garden"][0];
        check(g["slot"] == 4 && g["watered"] == 2 && g["last_water"] == 150, "v3 dictionary garden");
        v3["garden"] = {{"2", {{"plant", "sunflower"}, {"planted", 100}}}};
        g = migratePythonSave(v3, 160)["progress"]["garden"][0];
        check(g["slot"] == 2 && g["ready"] == 18100, "legacy garden slot map");
        auto bad = [&](Json data) {
            bool failed = false;
            try {
                (void)migratePythonSave(data, 600);
            } catch (const std::exception&) {
                failed = true;
            }
            check(failed, "invalid save accepted");
        };
        auto invalid = old;
        invalid["version"] = 4;
        bad(invalid);
        invalid = old;
        invalid["coins"] = -1;
        bad(invalid);
        invalid = old;
        invalid["coins"] = "1234";
        bad(invalid);
        invalid = old;
        invalid["garden"][0]["plant"] = 42;
        bad(invalid);
        invalid = old;
        invalid["stars"]["frontyard:1"] = {1, 1, 2};
        bad(invalid);
        bad(converted);
        bad(Json::array());
        const auto source = root / "python.json", destination = root / "native.json";
        const auto original = old.dump(4) + "\r\n";
        {
            std::ofstream out(source, std::ios::binary);
            out << original;
        }
        importPythonSave(source, destination, 600);
        check(bytes(source) == original && bytes(root / "native.json.legacy.json") == original,
              "source and backup byte retention");
        check(readNativeSave(destination) == converted, "atomic import read-back");
        const auto importedBytes = bytes(destination);
        bool failed = false;
        try {
            importPythonSave(source, destination, 600);
        } catch (const std::exception&) {
            failed = true;
        }
        check(failed && bytes(destination) == importedBytes, "repeat import never overwrites");
        failed = false;
        try {
            importPythonSave(source, source, 600);
        } catch (const std::exception&) {
            failed = true;
        }
        check(failed && bytes(source) == original, "in-place import rejected");
        const auto malformed = root / "broken.json";
        {
            std::ofstream(malformed) << "{broken";
        }
        failed = false;
        try {
            importPythonSave(malformed, root / "no-output.json", 600);
        } catch (const std::exception& e) {
            failed = std::string(e.what()).find("broken.json") != std::string::npos;
        }
        check(failed && !fs::exists(root / "no-output.json") &&
                  !fs::exists(root / "no-output.json.legacy.json"),
              "failed parse leaves no output");
        for (const auto& entry : fs::directory_iterator(root))
            check(pathUtf8(entry.path().filename()).find(".tmp-") == std::string::npos,
                  "temporary file leaked");
        std::cout << "PASS v2/v3 migration, Unicode paths, garden clock, unknown fields, backup and "
                     "no-overwrite import\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "FAIL " << e.what() << '\n';
        return 1;
    }
}
