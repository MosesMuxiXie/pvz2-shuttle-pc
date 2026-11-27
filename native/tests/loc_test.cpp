// Runtime localisation table: the compiled `lawn_strings.json` and the resolve order.
//
// The sections below are the ones that matter to a screen:
//
//   1. the shipped table really loads (19,055 rows) and answers a Chinese title;
//   2. Chinese wins over English, an English-only row still answers, and a row that is blank on
//      both sides is a miss rather than an empty line;
//   3. a key the table does not know returns the caller's fallback — that is what keeps
//      `humanizeGameKey` usable as the last resort;
//   4. an empty table and a root with no table are both safe (no throw, no noise);
//   5. a fixture proves the order on data this test controls, and that a broken file is reported
//      through `error` instead of taking the screen down.
//
// Section 2 also pins the case that motivated the whole table: the mechanical transcription of
// `ACHIEVE_ALL_IN_JEST_TITLE` is "All In Jest", while the shipped Chinese text is 向我开炮 — a test
// that passed with the transcription would not prove the file was read at all.

#include "loc.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

namespace fs = std::filesystem;
using pvz::loc::Strings;

namespace {

int failures = 0;

void check(bool condition, const std::string& what) {
    if (condition) return;
    ++failures;
    std::cerr << "  FAIL " << what << '\n';
}

void checkEqual(const std::string& actual, const std::string& expected, const std::string& what) {
    if (actual == expected) return;
    ++failures;
    std::cerr << "  FAIL " << what << '\n' << "       expected: " << expected << '\n'
              << "       actual:   " << actual << '\n';
}

void writeFile(const fs::path& file, const std::string& text) {
    fs::create_directories(file.parent_path());
    std::ofstream output(file, std::ios::binary);
    if (!output) throw std::runtime_error("cannot write " + file.string());
    output << text;
}

void section(const char* name) { std::cout << "- " << name << '\n'; }

} // namespace

int main(int argc, char** argv) {
    try {
        if (argc < 3) throw std::runtime_error("expected the content root and a temp directory");
        const fs::path content = fs::path(argv[1]);
        const fs::path temp = fs::path(argv[2]);

        section("shipped table");
        const Strings shipped = pvz::loc::load(content.string());
        check(shipped.error.empty() || !shipped.empty(), "load() failed: " + shipped.error);
        check(!shipped.empty(), "the shipped table did not load from " + content.string());
        check(shipped.size() == 19055, "row count is " + std::to_string(shipped.size()) +
                                           ", expected 19055");
        checkEqual(pvz::loc::resolve(shipped, "ACHIEVE_ALL_IN_JEST_TITLE", "?"), "向我开炮",
                   "the achievement title is not the shipped Chinese text");
        checkEqual(pvz::loc::resolve(shipped, "ELEMENT_7_WAVEMASSAGE", "?"),
                   "亡魂的怨念令你们震颤！", "the 460.9 element wave message is not verbatim");
        // The mechanical transcription of the same key: proving the two differ is what proves the
        // table was really read, not merely that resolve() returned something.
        const std::string transcribed = "All In Jest";
        check(pvz::loc::resolve(shipped, "ACHIEVE_ALL_IN_JEST_TITLE", transcribed) != transcribed,
              "resolve() returned the mechanical transcription, so the table was not read");

        section("resolve order");
        const auto* twin = shipped.find("ACHIEVE_ALL_IN_JEST_TITLE");
        check(twin != nullptr && !twin->en.empty() && !twin->zh.empty(),
              "the achievement row should carry both languages");
        const auto* englishOnly = shipped.find("NARRATIVE_GTA_1_INTRO_18");
        check(englishOnly != nullptr, "the English-only narrative row is missing");
        if (englishOnly != nullptr) {
            check(englishOnly->zh.empty(), "the English-only row grew a Chinese side");
            check(!pvz::loc::resolve(shipped, "NARRATIVE_GTA_1_INTRO_18", "").empty(),
                  "an English-only row did not fall through to English");
        }
        checkEqual(pvz::loc::resolve(shipped, "NO_SUCH_KEY_TITLE", "fallback text"), "fallback text",
                   "an unknown key did not return the fallback");
        checkEqual(pvz::loc::resolve(shipped, "no_such_key_title", "fallback text"), "fallback text",
                   "lookup is not case sensitive");

        section("empty and absent tables");
        const Strings nothing;
        check(nothing.empty() && nothing.size() == 0, "a default-constructed table is not empty");
        checkEqual(pvz::loc::resolve(nothing, "ANY_KEY", "kept"), "kept",
                   "an empty table did not return the fallback");
        const Strings absent = pvz::loc::load((temp / "no-such-content-root").string());
        check(absent.empty(), "a missing root produced rows");
        check(!absent.error.empty(), "a missing root did not explain itself in `error`");

        section("fixture: order, blanks, broken file");
        const fs::path fixture = temp / "loc-fixture";
        writeFile(fixture / "lawn_strings.json",
                  R"({"generated":"sha256:0000000000000000",)"
                  R"("counts":{"keys":4,"enOnly":1,"zhOnly":0,"both":3},)"
                  R"("strings":{)"
                  R"("BOTH":{"en":"English text","zh":"中文文本"},)"
                  R"("EN_ONLY":{"en":"English only","zh":""},)"
                  R"("BLANK_BOTH":{"en":"   ","zh":""},)"
                  R"("ZERO_WIDTH":{"en":"","zh":"  "}},)"
                  R"("unknowns":[]})");
        const Strings custom = pvz::loc::load(fixture.string());
        check(!custom.empty(), "the fixture did not load: " + custom.error);
        checkEqual(pvz::loc::resolve(custom, "BOTH", "?"), "中文文本", "Chinese did not win");
        checkEqual(pvz::loc::resolve(custom, "EN_ONLY", "?"), "English only",
                   "a blank Chinese side did not fall through to English");
        checkEqual(pvz::loc::resolve(custom, "BLANK_BOTH", "?"), "?",
                   "a whitespace-only row was returned as text");
        checkEqual(pvz::loc::resolve(custom, "ZERO_WIDTH", "?"), "?",
                   "a whitespace-only Chinese side was returned as text");

        writeFile(temp / "loc-broken" / "lawn_strings.json", "{not json");
        const Strings broken = pvz::loc::load((temp / "loc-broken").string());
        check(broken.empty(), "malformed JSON produced rows");
        check(!broken.error.empty(), "malformed JSON did not report an error");

        writeFile(temp / "loc-shape" / "lawn_strings.json", R"({"generated":"x","strings":[]})");
        const Strings wrongShape = pvz::loc::load((temp / "loc-shape").string());
        check(wrongShape.empty(), "a non-object `strings` produced rows");

        if (failures != 0) {
            std::cerr << "FAIL loc " << failures << " check(s)\n";
            return 1;
        }
        std::cout << "PASS loc rows=" << shipped.size() << " source=" << shipped.source << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "FAIL " << error.what() << '\n';
        return 1;
    }
}
