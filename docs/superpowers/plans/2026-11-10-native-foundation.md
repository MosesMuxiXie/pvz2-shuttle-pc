# Native Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal** Build the first native milestone with an executable that loads and audits the complete local catalog, plus an SDL3 window that can render the existing launcher artwork.

**Architecture** `native/` builds independently of the Python baseline. The catalog library owns validated JSON definitions and exposes data and audit counts to both the CLI and the desktop shell. The shell loads launcher art on the user machine. Subsequent milestones add the playable simulation, saves, APK parity, confirmed online services and final installers under the approved design.

**Tech Stack** C++20, CMake, CTest, SDL3, SDL3_image, nlohmann/json.

**Spec** [Native client design and APK parity audit](../specs/2026-11-10-native-client-design.md)

## Global Constraints

- Windows 10/11 x64 and macOS 11+ Intel/Apple Silicon are the final targets. Python remains the reference and can still run as before.
- Build and run without Python or APK libraries. The build can fetch pinned, hash-verified dependencies. Game assets remain local and optional for catalog auditing.
- Read the repository's existing `content` schema. Preserve stable IDs and `extra.source`, `extra.package`, `extra.stage`, and `extra.vasebreaker`. Expose synthesized levels distinctly.
- This is the foundation milestone. It does not change the current release entry point. The launcher's interaction and appearance require APK observations before parity is claimed.

## Review Focus

- Paths can contain spaces and non-ASCII characters. Test Windows CLI argument encoding and filesystem operations using such a path.
- A missing content root or broken JSON must make the tool fail with an actionable path and nonzero exit status.
- Invalid references must fail audit even if the total level count matches. Test missing world and zombie IDs and duplicate level IDs in a small fixture.
- Original and synthesized records can overlap with special-mode records. Assert both raw counts and overlap.
- A missing artwork file must leave the headless CLI usable and produce an explicit error when opening the launcher.

### Task 1. Native catalog and headless executable

**Files** Create `native/CMakeLists.txt`, `native/src/catalog.hpp`, `native/src/catalog.cpp`, `native/src/main.cpp`, and `native/tests/catalog_test.cpp`.

**Interfaces** `Catalog loadCatalog(const std::filesystem::path& contentRoot)` reads root registries and levels, validates IDs and references, and reports path-qualified input errors. `Catalog` exposes plants, zombies, worlds, levels and summary counts. `LevelDefinition` preserves ID, world, index, starting sun, deck, waves and source metadata. `PvZ2SHUTTLE --audit-content <directory>` prints counts on stdout and uses exit 0 only for a readable, internally consistent catalog.

- [x] Write a CTest executable for real content and malformed temporary fixtures. For the checked-in v26.10.1 catalog, expect 26 worlds, 147 plants, 55 zombies, 1,809 levels, 163 synthesized levels, 45 vasebreaker records and 42 overlapping records. Check `frontyard_1` starts with 150 sun and a deck whose first card is `sunflower`. Check a non-ASCII fixture path and actionable errors for malformed JSON, missing registries, duplicate IDs and unresolved references.
- [x] Configure the CMake test target before adding the implementation and run a build to observe missing catalog symbols or the missing implementation file.
- [x] Implement the catalog using strict field parsing. Validate world, plant and zombie references and duplicate IDs. Include filenames in parse and validation errors. Pass paths as `std::filesystem::path` and preserve Windows Unicode arguments. Print deterministic summary output.
- [x] Configure with `cmake -S native -B build/native -DPVZ_ENABLE_DESKTOP=OFF`, build with `cmake --build build/native --config Release`, and run `ctest --test-dir build/native -C Release --output-on-failure`. Run the CLI against `content`, expecting the counts above. Run against a missing directory, expecting nonzero status.
- [x] Commit the independently verified catalog and CLI.

### Task 2. SDL launcher window

**Files** Modify `native/CMakeLists.txt` and `native/src/main.cpp`. Create `native/src/launcher.hpp`, `native/src/launcher.cpp` and `native/README.md`.

**Interfaces** `void runLauncher(const std::filesystem::path& assetRoot, bool smokeTest)` opens a resizable SDL window with a 1280×720 logical coordinate system and displays `ui/launcher.png` fit to the reference viewport. `PvZ2SHUTTLE --launcher <asset directory>` displays it until the window is closed. `--launcher-smoke <asset directory>` decodes and renders once, then exits. Audit mode can be built alone with `PVZ_ENABLE_DESKTOP=OFF`.

- [x] Add tests for a missing asset directory and for one software-rendered frame using an independently created small fixture PNG. For the full launcher smoke test, point to `PvZ2SHUTTLE/assets` locally.
- [x] Run the tests before connecting the launcher entry point and confirm the missing integration fails.
- [x] Add pinned SDL3/SDL3_image sources, configure PNG decoding, and implement the launcher. Preserve logical aspect ratio, accept the window close event, and report the actual path for missing or undecodable art. Describe the local asset root and the audit-only and desktop configure commands.
- [x] Configure a clean desktop build, build Release, and run CTest. Run `--launcher-smoke` with the actual local assets and with a missing asset path. Confirm correct exit codes and diagnostic. Preserve the audit-only build tests.
- [x] Commit the independently verified SDL launcher.

- [ ] Verify the native build and launcher on a macOS runner. This remains pending on both target architectures.

Windows Release verification passed 2 audit-only tests and 4 desktop tests. The desktop smoke test also rendered the actual local launcher PNG through the Windows video driver.

## Subsequent milestones

The next plan delivers fixed-step combat, a playable `frontyard_1` and Python save import. Follow with the data and mechanics expansion, full screen/asset parity, network integration and native installers specified in the design. Each stage has separately recorded behavior comparisons and platform validation.
