cmake_minimum_required(VERSION 3.24)
file(STRINGS "${CMAKE_CURRENT_SOURCE_DIR}/../VERSION" SHUTTLE_VERSION LIMIT_COUNT 1)
project(PvZ2SHUTTLE VERSION "${SHUTTLE_VERSION}" LANGUAGES CXX)

include(CTest)
include(FetchContent)
option(PVZ_ENABLE_DESKTOP "Build the SDL desktop launcher" OFF)

FetchContent_Declare(nlohmann_json
    URL https://codeload.github.com/nlohmann/json/tar.gz/refs/tags/v3.12.0
    URL_HASH SHA256=4b92eb0c06d10683f7447ce9406cb97cd4b453be18d7279320f7b2f025c10187)
FetchContent_MakeAvailable(nlohmann_json)

add_library(shuttle_catalog STATIC src/catalog.cpp src/battle.cpp src/replay.cpp src/save.cpp)
target_compile_features(shuttle_catalog PUBLIC cxx_std_20)
target_include_directories(shuttle_catalog PUBLIC src)
target_link_libraries(shuttle_catalog PUBLIC nlohmann_json::nlohmann_json)

add_executable(PvZ2SHUTTLE src/main.cpp)
target_link_libraries(PvZ2SHUTTLE PRIVATE shuttle_catalog)
if(MINGW)
    target_link_options(PvZ2SHUTTLE PRIVATE -municode)
endif()

if(PVZ_ENABLE_DESKTOP)
    enable_language(C)
    set(BUILD_SHARED_LIBS OFF)
    set(SDL_SHARED OFF)
    set(SDL_STATIC ON)
    set(SDL_TEST_LIBRARY OFF)
    set(SDLIMAGE_AVIF OFF)
    set(SDLIMAGE_TIF OFF)
    set(SDLIMAGE_WEBP OFF)
    set(SDLIMAGE_JPG_SAVE OFF)
    set(SDLIMAGE_PNG_SAVE OFF)
    FetchContent_Declare(SDL3
        URL https://codeload.github.com/libsdl-org/SDL/tar.gz/refs/tags/release-3.2.28
        URL_HASH SHA256=5c908f07a93087037d3319bc5d820ba8df14ac98bdbdf24af9084ef460ce01b1)
    FetchContent_Declare(SDL3_image
        URL https://codeload.github.com/libsdl-org/SDL_image/tar.gz/refs/tags/release-3.2.4
        URL_HASH SHA256=6a2f263e69d5cf0f218615e061f0d6cc1ae708e847ffe5372af98d5dd96bd037)
    FetchContent_MakeAvailable(SDL3 SDL3_image)
    target_sources(PvZ2SHUTTLE PRIVATE src/launcher.cpp src/battle_screen.cpp)
    target_compile_definitions(PvZ2SHUTTLE PRIVATE PVZ_ENABLE_DESKTOP)
    target_link_libraries(PvZ2SHUTTLE PRIVATE SDL3::SDL3 SDL3_image::SDL3_image)
endif()

if(APPLE AND PVZ_ENABLE_DESKTOP)
    set_target_properties(PvZ2SHUTTLE PROPERTIES
        MACOSX_BUNDLE TRUE
        MACOSX_BUNDLE_GUI_IDENTIFIER "io.github.mosesmuxixie.pvz2-shuttle-pc"
        MACOSX_BUNDLE_BUNDLE_NAME "PvZ 2 SHUTTLE"
        MACOSX_BUNDLE_BUNDLE_VERSION "${PROJECT_VERSION}"
        MACOSX_BUNDLE_SHORT_VERSION_STRING "${PROJECT_VERSION}")
    install(TARGETS PvZ2SHUTTLE BUNDLE DESTINATION .)
    install(DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/../content" DESTINATION PvZ2SHUTTLE.app/Contents/Resources)
    install(FILES "${CMAKE_CURRENT_SOURCE_DIR}/../LICENSE" "${CMAKE_CURRENT_SOURCE_DIR}/../NOTICE.md"
        DESTINATION PvZ2SHUTTLE.app/Contents/Resources)
    set(bundle_licenses PvZ2SHUTTLE.app/Contents/Resources/licenses)
    install(FILES "${sdl3_SOURCE_DIR}/LICENSE.txt" DESTINATION "${bundle_licenses}" RENAME SDL3.txt)
    install(FILES "${sdl3_image_SOURCE_DIR}/LICENSE.txt" DESTINATION "${bundle_licenses}" RENAME SDL3_image.txt)
    install(FILES "${nlohmann_json_SOURCE_DIR}/LICENSE.MIT" DESTINATION "${bundle_licenses}" RENAME nlohmann_json.txt)
    set(CPACK_GENERATOR DragNDrop)
    set(CPACK_PACKAGE_FILE_NAME "PvZ2SHUTTLE-${PROJECT_VERSION}-macOS-dev")
    set(CPACK_DMG_VOLUME_NAME "PvZ 2 SHUTTLE")
    include(CPack)
endif()

if(BUILD_TESTING)
    add_executable(parity_test tests/parity_test.cpp)
    target_link_libraries(parity_test PRIVATE shuttle_catalog)
    if(MINGW)
        target_link_options(parity_test PRIVATE -municode)
    endif()
    add_test(NAME battle_parity COMMAND parity_test "${CMAKE_CURRENT_SOURCE_DIR}/../content")
    find_package(Threads REQUIRED)
    add_executable(first_battle_test tests/first_battle_test.cpp)
    target_link_libraries(first_battle_test PRIVATE shuttle_catalog Threads::Threads)
    if(MINGW)
        target_link_options(first_battle_test PRIVATE -municode)
    endif()
    add_test(NAME first_battle COMMAND first_battle_test
        "${CMAKE_CURRENT_SOURCE_DIR}/../content" "${CMAKE_CURRENT_BINARY_DIR}/battle fixtures")
    set_tests_properties(first_battle PROPERTIES FIXTURES_SETUP battle_replays)
    add_test(NAME recorded_battle_replay COMMAND "${CMAKE_COMMAND}"
        "-DPROGRAM=$<TARGET_FILE:PvZ2SHUTTLE>"
        "-DCONTENT=${CMAKE_CURRENT_SOURCE_DIR}/../content"
        "-DREPLAYS=${CMAKE_CURRENT_BINARY_DIR}/battle fixtures/replays"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/recorded_replay.cmake")
    set_tests_properties(recorded_battle_replay PROPERTIES FIXTURES_REQUIRED battle_replays)
    add_test(NAME first_battle_replay COMMAND "${CMAKE_COMMAND}"
        "-DPROGRAM=$<TARGET_FILE:PvZ2SHUTTLE>"
        "-DCONTENT=${CMAKE_CURRENT_SOURCE_DIR}/../content"
        "-DSCENARIO=${CMAKE_CURRENT_SOURCE_DIR}/tests/first_replay.json"
        -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/first_replay.cmake")

    add_executable(catalog_test tests/catalog_test.cpp)
    target_link_libraries(catalog_test PRIVATE shuttle_catalog)
    if(MINGW)
        target_link_options(catalog_test PRIVATE -municode)
    endif()
    set(catalog_fixtures "${CMAKE_CURRENT_BINARY_DIR}/catalog fixtures 🌻")
    add_test(NAME catalog COMMAND catalog_test
        "${CMAKE_CURRENT_SOURCE_DIR}/../content"
        "${catalog_fixtures}")
    set_tests_properties(catalog PROPERTIES FIXTURES_SETUP catalog_fixture)
    add_test(NAME catalog_cli_unicode COMMAND PvZ2SHUTTLE --audit-content "${catalog_fixtures}/关卡")
    set_tests_properties(catalog_cli_unicode PROPERTIES FIXTURES_REQUIRED catalog_fixture)

    if(PVZ_ENABLE_DESKTOP)
        add_test(NAME first_battle_frame COMMAND PvZ2SHUTTLE --play-first-smoke "${CMAKE_CURRENT_SOURCE_DIR}/../content")
        set_tests_properties(first_battle_frame PROPERTIES ENVIRONMENT "SDL_VIDEODRIVER=dummy")
        set(launcher_assets "${CMAKE_CURRENT_BINARY_DIR}/launcher fixture")
        file(MAKE_DIRECTORY "${launcher_assets}/ui")
        configure_file(tests/launcher.png "${launcher_assets}/ui/launcher.png" COPYONLY)
        add_test(NAME launcher_frame COMMAND PvZ2SHUTTLE --launcher-smoke "${launcher_assets}")
        set_tests_properties(launcher_frame PROPERTIES ENVIRONMENT "SDL_VIDEODRIVER=dummy")
        add_test(NAME launcher_missing_art
            COMMAND "${CMAKE_COMMAND}"
                "-DPROGRAM=$<TARGET_FILE:PvZ2SHUTTLE>"
                "-DASSET_ROOT=${CMAKE_CURRENT_BINARY_DIR}/missing assets"
                -P "${CMAKE_CURRENT_SOURCE_DIR}/tests/launcher_missing.cmake")
    endif()
endif()
