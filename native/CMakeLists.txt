cmake_minimum_required(VERSION 3.24)
project(PvZ2SHUTTLE VERSION 0.1.0 LANGUAGES CXX)

# S7: static CRT so the shipped exe needs no vc_redist on the target machine. Every
# dependency here is built from source in this tree (SDL3 static, SDL3_image static,
# freetype static), so one setting covers the whole link line.
if(POLICY CMP0091)
    cmake_policy(SET CMP0091 NEW)
endif()
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

# The data pack this build was generated from. It is not derived at build time (the
# OBB is not part of the checkout), so it is a cache variable the packager can pin.
set(PVZ_DATA_VERSION "460.9" CACHE STRING "PvZ2 data (OBB) version this build targets")
include(CTest)
include(FetchContent)
option(PVZ_ENABLE_DESKTOP "Build the SDL3 desktop client" OFF)
option(PVZ_REGENERATE_CONTENT "Offer a `regenerate_content` target (needs Python 3)" OFF)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

function(pvz_warnings target)
    if(MSVC)
        target_compile_options(${target} PRIVATE /utf-8 /W4 /permissive-)
    else()
        target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic)
    endif()
endfunction()

set(JSON_BuildTests OFF CACHE BOOL "" FORCE)
FetchContent_Declare(json
    URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz
    URL_HASH SHA256=42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa
    DOWNLOAD_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../build/downloads"
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_MakeAvailable(json)

# T38 audio. `stb_vorbis.c` is C, and `project()` above only declares CXX, so the language is
# enabled here; it stays a separate static library so our /W4 flags never reach vendored code and
# the C++ half only takes the declarations (`STB_VORBIS_HEADER_ONLY`). Nothing below needs SDL:
# WAV/OGG decode, the mixer, the event table and `--audio-audit` all build in the audit config.
enable_language(C)
set(PVZ_STB_VORBIS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/third_party")
add_library(pvz_stb_vorbis STATIC third_party/stb_vorbis.c)
target_include_directories(pvz_stb_vorbis PUBLIC "${PVZ_STB_VORBIS_DIR}")
if(MSVC)
    target_compile_options(pvz_stb_vorbis PRIVATE /w)
else()
    target_compile_options(pvz_stb_vorbis PRIVATE -w)
endif()

add_library(pvz_audio_core
    src/audio/audio_catalog.cpp
    src/audio/audio_decode.cpp
    src/audio/audio_mixer.cpp
    src/audio/event_map.cpp
    src/audio/audio_audit.cpp
    src/audio/audio_runtime.cpp
    src/audio/audio_backend_null.cpp)
target_include_directories(pvz_audio_core PUBLIC src PRIVATE "${PVZ_STB_VORBIS_DIR}")
target_link_libraries(pvz_audio_core PUBLIC nlohmann_json::nlohmann_json PRIVATE pvz_stb_vorbis)
pvz_warnings(pvz_audio_core)

# art_index.cpp is the SDL-free half of the asset layer: the desktop cache and the
# `--art-audit` CLI both resolve artwork through it, so it belongs to the shared target.
add_library(pvz_catalog src/catalog.cpp src/art_index.cpp src/worldmap.cpp)
target_include_directories(pvz_catalog PUBLIC src)
target_link_libraries(pvz_catalog PUBLIC nlohmann_json::nlohmann_json pvz_content)
pvz_warnings(pvz_catalog)
add_library(pvz_content src/content/loader.cpp)
target_include_directories(pvz_content PUBLIC src)
target_link_libraries(pvz_content PUBLIC nlohmann_json::nlohmann_json)
pvz_warnings(pvz_content)
add_library(pvz_simulation src/simulation.cpp)
target_link_libraries(pvz_simulation PUBLIC pvz_catalog)
pvz_warnings(pvz_simulation)
add_library(pvz_engine
    src/engine/world.cpp
    src/engine/director.cpp
    src/engine/action_runner.cpp
    src/engine/projectile.cpp
    src/engine/projectile_table.cpp
    src/engine/armor.cpp
src/engine/mechanics.cpp
    src/engine/registry.cpp
    src/engine/zombie_family.cpp
    src/engine/plant_family.cpp
    src/engine/plantfood.cpp
    src/engine/fusion.cpp
    src/engine/boss.cpp
    src/engine/replay.cpp)
target_include_directories(pvz_engine PUBLIC src PRIVATE generated)
# S5.7: the plant-food and fusion tables are generated JSON next to the pack. Compiling the
# directory in means a shipped build needs no environment, while PVZ_GENERATED_DIR still wins
# at run time so a test can point the loader at a fixture.
target_compile_definitions(pvz_engine PRIVATE PVZ_GENERATED_DIR="${CMAKE_CURRENT_SOURCE_DIR}/generated")
target_link_libraries(pvz_engine PUBLIC pvz_catalog)
pvz_warnings(pvz_engine)
set_source_files_properties(src/engine/zombie_family.cpp PROPERTIES
    OBJECT_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/generated/zombie_family_table.inc")
set_source_files_properties(src/engine/plant_family.cpp PROPERTIES
    OBJECT_DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/generated/plant_family_table.inc")
add_library(pvz_save src/save.cpp)
target_link_libraries(pvz_save PUBLIC pvz_catalog)
pvz_warnings(pvz_save)
add_library(pvz_progress src/progress.cpp src/rewards.cpp)
target_link_libraries(pvz_progress PUBLIC pvz_catalog pvz_engine)

# Shop catalogue + the single purchase rule. `shop_unlock.json` is compiled data, so the
# dependency is a file rather than another target.
add_library(pvz_shop src/shop.cpp)
target_link_libraries(pvz_shop PUBLIC pvz_progress)
# T46: the S4 loop as a library — pick the level a save points at, play it, fold the result back.
# No SDL and no window, so `flow_test` runs in the audit configuration and `--flow` works headless;
# the desktop screens call the same pick, so "continue" cannot disagree with a scripted run.
add_library(pvz_flow src/flow.cpp)
target_link_libraries(pvz_flow PUBLIC pvz_progress)
pvz_warnings(pvz_flow)
pvz_warnings(pvz_progress)
add_executable(PvZ2SHUTTLE src/main.cpp)
target_compile_definitions(PvZ2SHUTTLE PRIVATE PVZ_VERSION="${PROJECT_VERSION}")
target_compile_definitions(PvZ2SHUTTLE PRIVATE PVZ_DATA_VERSION="${PVZ_DATA_VERSION}")
# S6.0: `--run-level --progress` folds the finished battle into the save, so the CLI needs
# the progress library. One added link target; no source of this file changed otherwise.
target_link_libraries(PvZ2SHUTTLE PRIVATE pvz_catalog pvz_simulation pvz_engine pvz_save pvz_progress pvz_shop pvz_flow pvz_audio_core)
pvz_warnings(PvZ2SHUTTLE)

if(BUILD_TESTING)
    function(pvz_failure_test name mode input expected)
        add_test(NAME ${name} COMMAND ${CMAKE_COMMAND}
            "-DPROGRAM=$<TARGET_FILE:PvZ2SHUTTLE>" "-DMODE=${mode}" "-DINPUT=${input}" "-DEXPECTED=${expected}"
            -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/expect_failure.cmake")
    endfunction()
    set(PVZ_TEST_CONTENT "${CMAKE_CURRENT_SOURCE_DIR}/../content")
    set(PVZ_TEST_TEMP "${CMAKE_CURRENT_BINARY_DIR}/Testing/fixtures")
    set(PVZ_TEST_PNG "${CMAKE_CURRENT_SOURCE_DIR}/tests/fixtures/launcher.png")
    # Artwork lives next to the repository checkout: <root>/PvZ2SHUTTLE/assets.
    set(PVZ_TEST_ASSETS "${CMAKE_CURRENT_SOURCE_DIR}/../../../PvZ2SHUTTLE/assets")
    # The runtime pack is generated from the shipped property sheets. It is
    # checked in so a build needs no Python; regenerate with tools/check_all.ps1
    # or `python tools/contentc/build_content.py`.
    set(PVZ_CONTENT_PACK "${CMAKE_CURRENT_SOURCE_DIR}/generated/content.pack")
    add_executable(catalog_test tests/catalog_test.cpp)
    target_link_libraries(catalog_test PRIVATE pvz_catalog)
    pvz_warnings(catalog_test)
    add_test(NAME catalog COMMAND catalog_test "${PVZ_TEST_CONTENT}" "${PVZ_TEST_TEMP}" "${PVZ_CONTENT_PACK}")

    add_executable(content_test tests/content_test.cpp)
    target_link_libraries(content_test PRIVATE pvz_content)
    pvz_warnings(content_test)
    add_test(NAME content COMMAND content_test "${PVZ_CONTENT_PACK}" "${PVZ_TEST_TEMP}")
    set_tests_properties(content PROPERTIES SKIP_RETURN_CODE 77)

    # S6.1: the world map is data + rules, so it is testable without SDL.
    add_executable(worldmap_test tests/worldmap_test.cpp)
    # clearedLevelsFor() reads Progress, so the model test needs the progress library too.
    target_link_libraries(worldmap_test PRIVATE pvz_catalog pvz_progress)
    pvz_warnings(worldmap_test)
    add_test(NAME worldmap COMMAND worldmap_test "${PVZ_TEST_CONTENT}")
    set_tests_properties(worldmap PROPERTIES TIMEOUT 120)
    if(PVZ_REGENERATE_CONTENT)
        find_package(Python3 COMPONENTS Interpreter QUIET)
        if(Python3_Interpreter_FOUND)
            add_custom_target(regenerate_content
                COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/../tools/contentc/build_content.py"
                        --obb "${CMAKE_CURRENT_SOURCE_DIR}/../../../work/obb_packages"
                        --out "${PVZ_CONTENT_PACK}"
                        --coverage "${CMAKE_CURRENT_SOURCE_DIR}/generated/coverage.json"
                COMMENT "Regenerating content pack from the shipped property sheets"
                VERBATIM)
        endif()
    endif()
    add_test(NAME cli_audit COMMAND PvZ2SHUTTLE --audit-content "${PVZ_TEST_CONTENT}")
    set_tests_properties(cli_audit PROPERTIES PASS_REGULAR_EXPRESSION "levels=1809")
    # T38: the audit has to work without a sound card, so this runs in both configurations and
    # only asserts the catalog half (`deviceAvailable` may be either value).
    add_test(NAME cli_audio_audit COMMAND PvZ2SHUTTLE --audio-audit "${PVZ_TEST_ASSETS}")
    set_tests_properties(cli_audio_audit PROPERTIES PASS_REGULAR_EXPRESSION "\"sounds\":65")
    pvz_failure_test(cli_missing_content --audit-content "${CMAKE_CURRENT_BINARY_DIR}/missing content" "content directory")
    pvz_failure_test(cli_unknown_command --not-a-command unused "unknown command")
    add_executable(simulation_test tests/simulation_test.cpp)
    target_link_libraries(simulation_test PRIVATE pvz_simulation)
    pvz_warnings(simulation_test)
    add_test(NAME simulation COMMAND simulation_test "${PVZ_TEST_CONTENT}")
    add_executable(save_test tests/save_test.cpp)
    target_link_libraries(save_test PRIVATE pvz_save)
    pvz_warnings(save_test)
    add_test(NAME save_import COMMAND save_test "${PVZ_TEST_TEMP}")

    add_executable(engine_test tests/engine_test.cpp)
    target_link_libraries(engine_test PRIVATE pvz_engine)
    pvz_warnings(engine_test)
    add_test(NAME engine COMMAND engine_test "${PVZ_TEST_CONTENT}" "${PVZ_CONTENT_PACK}" "${PVZ_TEST_TEMP}")
    set_tests_properties(engine PROPERTIES TIMEOUT 300)

    # Outcome/statistics regressions (victory branch, distinct unwired families,
    # despawn vs kill). Kept apart from engine_test so the branch coverage is visible.
    add_executable(world_outcome_test tests/world_outcome_test.cpp)
    target_link_libraries(world_outcome_test PRIVATE pvz_engine)
    pvz_warnings(world_outcome_test)
    add_test(NAME world_outcome COMMAND world_outcome_test "${PVZ_TEST_CONTENT}" "${PVZ_CONTENT_PACK}")
    set_tests_properties(world_outcome PROPERTIES TIMEOUT 120)

    # The 183 original ZombieClass rows are generated; this test proves the table is
    # linked and that spawnZombie prefers it over the shipped content behaviour.
    add_executable(zombie_family_test tests/zombie_family_test.cpp)
    target_link_libraries(zombie_family_test PRIVATE pvz_engine)
    pvz_warnings(zombie_family_test)
    add_test(NAME zombie_family COMMAND zombie_family_test "${PVZ_TEST_CONTENT}" "${PVZ_CONTENT_PACK}" "${PVZ_TEST_TEMP}")
    set_tests_properties(zombie_family PROPERTIES TIMEOUT 120)

    # Artwork resolution: `db/<art>` (legacy web export) then the SHUTTLE index by popAnim.
    # SDL-free, so this runs in the AuditOnly build as well.
    add_executable(art_audit_test tests/art_audit_test.cpp)
    target_link_libraries(art_audit_test PRIVATE pvz_catalog)
    pvz_warnings(art_audit_test)
    add_test(NAME art_audit COMMAND art_audit_test "${PVZ_TEST_CONTENT}" "${PVZ_CONTENT_PACK}" "${PVZ_TEST_TEMP}")
    set_tests_properties(art_audit PROPERTIES TIMEOUT 120)

    # T38 audio: same catalog, same decoders, same mixer; only the device changes. The audio
    # test runs in every configuration because the numbers it asserts (26 BGM / 18 sfx) are
    # properties of the shipped assets, not of SDL.
    add_executable(audio_test tests/audio_test.cpp)
    target_link_libraries(audio_test PRIVATE pvz_audio_core)
    pvz_warnings(audio_test)
    add_test(NAME audio COMMAND audio_test "${PVZ_TEST_ASSETS}" "${PVZ_TEST_TEMP}"
        "${CMAKE_CURRENT_SOURCE_DIR}/../../../work/obb_packages")
    set_tests_properties(audio PROPERTIES TIMEOUT 180)

    # T45 runtime wiring: a real battle's event stream driven through the same consume/pump calls
    # `BattleScene` makes. Runs without SDL (the null backend), so it also proves the no-device
    # path is silent instead of merely unbuilt.
    add_executable(audio_runtime_test tests/audio_runtime_test.cpp)
    target_link_libraries(audio_runtime_test PRIVATE pvz_audio_core pvz_engine pvz_catalog)
    pvz_warnings(audio_runtime_test)
    add_test(NAME audio_runtime COMMAND audio_runtime_test "${PVZ_TEST_ASSETS}" "${PVZ_TEST_CONTENT}"
        "${PVZ_CONTENT_PACK}")
    set_tests_properties(audio_runtime PROPERTIES TIMEOUT 180)

    # Star goals and the progress save file. The scripts directory holds the replay
    # that wins beach_23, so the evaluation path runs against a real victory.
    add_executable(progress_test tests/progress_test.cpp)
    target_link_libraries(progress_test PRIVATE pvz_progress pvz_engine)
    pvz_warnings(progress_test)
    add_test(NAME progress COMMAND progress_test "${PVZ_TEST_CONTENT}" "${PVZ_TEST_TEMP}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/scripts")
    set_tests_properties(progress PROPERTIES TIMEOUT 180)

    # T46: two turns of the S4 loop against one save. The point is the seam between the screens,
    # not the combat, so the levels run with the empty script and the test looks at the save.
    add_executable(flow_test tests/flow_test.cpp)
    target_link_libraries(flow_test PRIVATE pvz_flow)
    pvz_warnings(flow_test)
    add_test(NAME flow COMMAND flow_test "${PVZ_TEST_CONTENT}" "${PVZ_TEST_TEMP}" "${CMAKE_CURRENT_SOURCE_DIR}/tests/scripts")
    set_tests_properties(flow PROPERTIES TIMEOUT 180)

    # S5.7 runtime mechanics: plant food (buff + the six sheet-declared actions) and the 85
    # fusion recipes, plus the proof that switching them off leaves the hash untouched.
    add_executable(s5_runtime_test tests/s5_runtime_test.cpp)
    target_link_libraries(s5_runtime_test PRIVATE pvz_engine)
    pvz_warnings(s5_runtime_test)
    add_test(NAME s5_runtime COMMAND s5_runtime_test "${PVZ_TEST_CONTENT}" "${PVZ_CONTENT_PACK}" "${PVZ_TEST_TEMP}")
    set_tests_properties(s5_runtime PROPERTIES TIMEOUT 180)

    # Reachability: the same two mechanics, but driven by a replay script. `s5_runtime` calls
    # `feed`/`tryFuse` directly, so on its own it would keep passing even when no player-facing
    # path can reach them.
    add_executable(replay_s5_test tests/replay_s5_test.cpp)
    target_link_libraries(replay_s5_test PRIVATE pvz_engine)
    pvz_warnings(replay_s5_test)
    add_test(NAME replay_s5 COMMAND replay_s5_test "${PVZ_TEST_CONTENT}" "${PVZ_CONTENT_PACK}")
    set_tests_properties(replay_s5 PROPERTIES TIMEOUT 180)

    # S5.8 boss runtime: the 71 levels whose `extra` marks a boss must really put one on the
    # lawn, and `--boss off` must reproduce the pre-boss hashes.
    add_executable(s5_boss_test tests/s5_boss_test.cpp)
    target_link_libraries(s5_boss_test PRIVATE pvz_engine)
    pvz_warnings(s5_boss_test)
    add_test(NAME s5_boss COMMAND s5_boss_test "${PVZ_TEST_CONTENT}" "${PVZ_CONTENT_PACK}" "${PVZ_TEST_TEMP}")
    set_tests_properties(s5_boss PROPERTIES TIMEOUT 180)

    # S5.9 projectile wiring: the shot table has to drive speed and hit box, not the two constants.
    add_executable(projectile_table_test tests/projectile_table_test.cpp)
    target_link_libraries(projectile_table_test PRIVATE pvz_engine)
    pvz_warnings(projectile_table_test)
    add_test(NAME projectile_table COMMAND projectile_table_test "${PVZ_TEST_CONTENT}" "${PVZ_CONTENT_PACK}" "${PVZ_TEST_TEMP}")
    set_tests_properties(projectile_table PROPERTIES TIMEOUT 180)

    # S5.11 armor wiring: the sheet's layer order and ArmorFlags have to reach the engine, not
    # just the content `armor[].hp` sum this test replaces.
    add_executable(armor_test tests/armor_test.cpp)
    target_link_libraries(armor_test PRIVATE pvz_engine)
    pvz_warnings(armor_test)
    add_test(NAME armor COMMAND armor_test "${PVZ_TEST_CONTENT}" "${PVZ_CONTENT_PACK}" "${PVZ_TEST_TEMP}")
    set_tests_properties(armor PROPERTIES TIMEOUT 180)

    # T50 drag-to-plant: the drag state machine is SDL-free on purpose, so the four behaviours that
    # matter (legal drop, refused drop, one plant per drag, no card) are driven with plain numbers
    # against a real engine::World — no window, no assets, audit configuration.
    add_executable(battle_drag_test tests/battle_drag_test.cpp src/drag_plant.cpp)
    target_link_libraries(battle_drag_test PRIVATE pvz_engine)
    pvz_warnings(battle_drag_test)
    add_test(NAME battle_drag COMMAND battle_drag_test "${PVZ_TEST_CONTENT}" "${PVZ_CONTENT_PACK}" "${PVZ_TEST_TEMP}")
    set_tests_properties(battle_drag PROPERTIES TIMEOUT 180)

    # S5.13: the level mechanics sheet - conveyor economy, the opening field, gravestone drops, the
    # protect mission, and the count of mechanics the kernel still does not run.
    add_executable(mechanics_test tests/mechanics_test.cpp)
    target_link_libraries(mechanics_test PRIVATE pvz_engine)
    pvz_warnings(mechanics_test)
    add_test(NAME mechanics COMMAND mechanics_test "${PVZ_TEST_CONTENT}" "${PVZ_CONTENT_PACK}" "${PVZ_TEST_TEMP}")
    set_tests_properties(mechanics PROPERTIES TIMEOUT 180)

    # T55: reward settlement - kill periods, the lunch box (including the 13 dangling present
    # tables), the four world keys and their egypt3 gate, seed bags, and the kinds the save has
    # no field for. Drives real worlds, so the kill counter is exercised, not stubbed.
    add_executable(rewards_test tests/rewards_test.cpp)
    target_link_libraries(rewards_test PRIVATE pvz_progress)
    pvz_warnings(rewards_test)
    add_test(NAME rewards COMMAND rewards_test "${PVZ_TEST_CONTENT}" "${PVZ_TEST_TEMP}")
    set_tests_properties(rewards PROPERTIES TIMEOUT 180)
    # T77: the five reward families the save now holds (`gems`, `mowers`, `xp`, `trophies` and the
    # seed bags) must reach the receipt, and only when a save is going to take them. Two runs of
    # the same battle pin both halves: the progress run prints the counters, the plain run must
    # not grow a key at all (it stays byte-identical to the pre-T77 CLI, which the smoke baseline
    # compares).
    add_test(NAME cli_reward_receipt COMMAND PvZ2SHUTTLE --run-level "${PVZ_TEST_CONTENT}" frontyard_1
        --script "${CMAKE_CURRENT_SOURCE_DIR}/tests/scripts/frontyard_1_basic.json"
        --progress "${PVZ_TEST_TEMP}/reward_receipt.json")
    set_tests_properties(cli_reward_receipt PROPERTIES TIMEOUT 180
        PASS_REGULAR_EXPRESSION "\"gemsGained\":[0-9]+,.*\"mowersGained\":[0-9]+,.*\"plantsGained\":[0-9]+,.*\"trophiesGained\":[0-9]+,.*\"xpGained\":[0-9]+")
    add_test(NAME cli_reward_plain COMMAND PvZ2SHUTTLE --run-level "${PVZ_TEST_CONTENT}" frontyard_1
        --script "${CMAKE_CURRENT_SOURCE_DIR}/tests/scripts/frontyard_1_basic.json")
    set_tests_properties(cli_reward_plain PROPERTIES TIMEOUT 180 FAIL_REGULAR_EXPRESSION "Gained")



endif()

if(PVZ_ENABLE_DESKTOP)
    include(cmake/DesktopDependencies.cmake)
    add_library(pvz_launcher src/launcher.cpp src/battle_view.cpp src/worldmap_view.cpp
                src/menu_view.cpp src/level_select_view.cpp src/drag_plant.cpp src/assets.cpp
                src/actor_view.cpp src/dragonbones.cpp src/text.cpp)
    # pvz_engine: the battle view drives `engine::World`, not the legacy `Battle`.
    target_link_libraries(pvz_launcher PUBLIC pvz_catalog pvz_simulation pvz_engine pvz_audio_core SDL3::SDL3
                                     SDL3_image::SDL3_image)
    target_link_libraries(pvz_launcher PRIVATE freetype)
    pvz_warnings(pvz_launcher)
    target_link_libraries(PvZ2SHUTTLE PRIVATE pvz_launcher)
    target_compile_definitions(PvZ2SHUTTLE PRIVATE PVZ_ENABLE_DESKTOP=1)

# S7: the install tree is exactly what `tools/package.ps1` zips, so it has to be a tree
# that runs on a machine with no source checkout next to it. Assets come from the
# workspace root (`PvZ2SHUTTLE/assets`), generated JSON is runtime data and ships too.
install(TARGETS PvZ2SHUTTLE RUNTIME DESTINATION .)
# The artwork tree is 4.6 GB of extracted OBB art. It is not part of the repository and it
# is not shipped inside the zip: `PVZ_ASSET_ROOT` (or an `assets/` folder next to the exe) is
# how a packaged build finds it. `tools/package.ps1 -IncludeAssets` creates that folder as a
# junction and keeps it out of the archive, so nothing here copies 4.6 GB into the install tree.
# The artwork tree lives at the workspace root (`<workspace>/PvZ2SHUTTLE/assets`), three levels
# above this file: repo/pvz2-shuttle-pc/native -> repo -> workspace.
set(PVZ_ASSET_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/../../../PvZ2SHUTTLE/assets" CACHE PATH
    "Local artwork tree; only the small ui/ subset is installed, the rest is used via PVZ_ASSET_ROOT")
if(EXISTS "${PVZ_ASSET_SOURCE}")
    message(STATUS "S7: artwork at ${PVZ_ASSET_SOURCE} (only ui/ is installed; the rest needs PVZ_ASSET_ROOT)")
else()
    message(STATUS "S7: no artwork at ${PVZ_ASSET_SOURCE}; the exe needs PVZ_ASSET_ROOT at runtime")
endif()
# `ui/` is 26.6 MB (the Chinese font is 19.7 MB of it) and every headless screen needs it:
# menu_view, level_select_view, worldmap_view and battle_view all open `ui/font_zh.ttc`, and
# `launcher` opens `ui/launcher.png`. Shipping it is what makes `--menu content` run from a
# zip with no source checkout next to it. The 4.6 GB of extracted art is a different matter
# and stays outside the package.
if(EXISTS "${PVZ_ASSET_SOURCE}/ui")
    install(DIRECTORY "${PVZ_ASSET_SOURCE}/ui" DESTINATION assets)
    install(FILES "${PVZ_ASSET_SOURCE}/MANIFEST_UI.json" DESTINATION assets OPTIONAL)
endif()
# T66 repair: this `endif()` used to stand here and closed `if(PVZ_ENABLE_DESKTOP)` 66 lines early.
# Everything below it (the SDL audio backend wiring and the whole desktop test block, up to the
# `elseif(BUILD_TESTING)` below) then ran in the audit build as well, where SDL has no target, and
# CMake aborted with "Flow control statements are not properly nested". The desktop branch now
# closes right after its test block, which is where the `elseif` expects it.
install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/generated/" DESTINATION generated FILES_MATCHING PATTERN "*.json")
# content/ is the data half of the runtime (levels, plants, projectiles, every generated
# table's inputs). The exe takes it as a CLI argument, so the packaged tree keeps it in a
# `content/` folder next to the exe and the launcher's default resolves it relative to
# the install root.
install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../content/" DESTINATION content)
install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/../NOTICE.md" DESTINATION . OPTIONAL)
install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/../CHANGELOG.md" DESTINATION . OPTIONAL)
install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/../docs/PROGRESS.md" DESTINATION . RENAME PROGRESS.md OPTIONAL)
install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/../README.md" DESTINATION . OPTIONAL)
    # T38: the SDL3 device is the only part of the audio pipeline that needs SDL. It is added to
    # the shared audio target here, so the audit build keeps the stub from audio_backend_null.cpp.
    target_sources(pvz_audio_core PRIVATE src/audio/audio_backend.cpp)
    target_link_libraries(pvz_audio_core PRIVATE SDL3::SDL3)
    target_compile_definitions(pvz_audio_core PRIVATE PVZ_ENABLE_DESKTOP=1)
    if(BUILD_TESTING)
        # T45: the only audio case that needs a real card. Three seconds of frontyard battle must
        # leave mixed frames in the device queue; a machine without a device reports 77 (Skipped)
        # with the reason, so the suite never calls a device it never opened a pass.
        add_executable(audio_runtime_device_test tests/audio_runtime_device_test.cpp)
        target_link_libraries(audio_runtime_device_test PRIVATE pvz_audio_core pvz_engine pvz_catalog)
        pvz_warnings(audio_runtime_device_test)
        add_test(NAME audio_device COMMAND audio_runtime_device_test "${PVZ_TEST_ASSETS}" "${PVZ_TEST_CONTENT}"
            "${PVZ_CONTENT_PACK}")
        # Decoding the whole 65-sound catalog costs ~140 s on a loaded machine (4,475 s of audio),
# which is inside the test's own work, not a hang. 120 s was the inherited default and it
# turned a slow-but-correct run into a red gate.
set_tests_properties(audio_device PROPERTIES TIMEOUT 600 SKIP_RETURN_CODE 77)
        add_executable(launcher_test tests/launcher_test.cpp)
        target_link_libraries(launcher_test PRIVATE pvz_launcher)
        pvz_warnings(launcher_test)
        add_test(NAME launcher COMMAND launcher_test "${PVZ_TEST_PNG}" "${PVZ_TEST_TEMP}")
        pvz_failure_test(cli_missing_artwork --launcher-smoke "${CMAKE_CURRENT_BINARY_DIR}/missing assets" "launcher.png")
        add_executable(dragonbones_test tests/dragonbones_test.cpp)
        target_link_libraries(dragonbones_test PRIVATE pvz_launcher)
        pvz_warnings(dragonbones_test)
        add_test(NAME dragonbones COMMAND dragonbones_test "${PVZ_TEST_ASSETS}")
        add_executable(assets_test tests/assets_test.cpp)
        target_link_libraries(assets_test PRIVATE pvz_launcher)
        pvz_warnings(assets_test)
        add_test(NAME assets COMMAND assets_test "${PVZ_TEST_ASSETS}")
        add_executable(text_test tests/text_test.cpp)
        target_link_libraries(text_test PRIVATE pvz_launcher)
        pvz_warnings(text_test)
        add_test(NAME text_render COMMAND text_test "${PVZ_TEST_ASSETS}" "${PVZ_TEST_TEMP}")
        add_executable(battle_view_test tests/battle_view_test.cpp)
        target_link_libraries(battle_view_test PRIVATE pvz_launcher)
        pvz_warnings(battle_view_test)
        add_test(NAME battle_render COMMAND battle_view_test "${PVZ_TEST_CONTENT}" "${PVZ_TEST_ASSETS}" "${PVZ_TEST_TEMP}")
    add_executable(worldmap_render_test tests/worldmap_render_test.cpp)
    target_link_libraries(worldmap_render_test PRIVATE pvz_launcher pvz_progress)
    pvz_warnings(worldmap_render_test)
    add_test(NAME worldmap_render COMMAND worldmap_render_test "${PVZ_TEST_CONTENT}"
        "${PVZ_TEST_ASSETS}" "${PVZ_TEST_TEMP}")
    # S4: the two screens that close the meta-game chain. Their tests read a save, so they link
    # pvz_progress; both draw text, so the "ink pixels" assertions live in the render tests.
    add_executable(menu_render_test tests/menu_render_test.cpp)
    target_link_libraries(menu_render_test PRIVATE pvz_launcher pvz_progress)
    pvz_warnings(menu_render_test)
    add_test(NAME menu_render COMMAND menu_render_test "${PVZ_TEST_CONTENT}"
        "${PVZ_TEST_ASSETS}" "${PVZ_TEST_TEMP}")
    add_executable(level_select_render_test tests/level_select_render_test.cpp)
    target_link_libraries(level_select_render_test PRIVATE pvz_launcher pvz_progress)
    pvz_warnings(level_select_render_test)
    add_test(NAME level_select COMMAND level_select_render_test "${PVZ_TEST_CONTENT}"
        "${PVZ_TEST_ASSETS}" "${PVZ_TEST_TEMP}")
    endif()
elseif(BUILD_TESTING)
    pvz_failure_test(cli_desktop_disabled --launcher-smoke unused "PVZ_ENABLE_DESKTOP")
endif()
if(BUILD_TESTING)
    get_property(pvz_tests DIRECTORY PROPERTY TESTS)
    # Shop: counts, the coin spend, and the three refusals that must stay refusals.
add_executable(shop_test tests/shop_test.cpp)
target_link_libraries(shop_test PRIVATE pvz_shop)
add_test(NAME shop COMMAND shop_test "${PVZ_TEST_CONTENT}"
    "${CMAKE_CURRENT_SOURCE_DIR}/generated/shop_unlock.json" "${PVZ_TEST_TEMP}")
set_tests_properties(shop PROPERTIES TIMEOUT 120)

set_tests_properties(${pvz_tests} PROPERTIES TIMEOUT 120)
endif()

# Every test that builds an engine::World loads the generated tables, and those are found by walking
# up from the working directory: a non-ASCII source path cannot be baked in with a `-D` define
# (cl.exe reads it in the ANSI code page, so `文档` arrives as `鏂囨。`), and the build directory can
# live anywhere on disk. Declared last so it also covers the desktop tests registered above; every
# test already receives absolute paths for its own inputs.
get_property(pvz_tests DIRECTORY PROPERTY TESTS)
if(pvz_tests)
    set_tests_properties(${pvz_tests} PROPERTIES WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/..")
endif()
