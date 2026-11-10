cmake_minimum_required(VERSION 3.24)
project(PvZ2SHUTTLE LANGUAGES CXX)

include(CTest)
include(FetchContent)
option(PVZ_ENABLE_DESKTOP "Build the SDL desktop launcher" OFF)

FetchContent_Declare(nlohmann_json
    URL https://codeload.github.com/nlohmann/json/tar.gz/refs/tags/v3.12.0
    URL_HASH SHA256=4b92eb0c06d10683f7447ce9406cb97cd4b453be18d7279320f7b2f025c10187)
FetchContent_MakeAvailable(nlohmann_json)

add_library(shuttle_catalog src/catalog.cpp)
target_compile_features(shuttle_catalog PUBLIC cxx_std_20)
target_include_directories(shuttle_catalog PUBLIC src)
target_link_libraries(shuttle_catalog PUBLIC nlohmann_json::nlohmann_json)

add_executable(PvZ2SHUTTLE src/main.cpp)
target_link_libraries(PvZ2SHUTTLE PRIVATE shuttle_catalog)
if(MINGW)
    target_link_options(PvZ2SHUTTLE PRIVATE -municode)
endif()

if(BUILD_TESTING)
    add_executable(catalog_test tests/catalog_test.cpp)
    target_link_libraries(catalog_test PRIVATE shuttle_catalog)
    add_test(NAME catalog COMMAND catalog_test
        "${CMAKE_CURRENT_SOURCE_DIR}/../content"
        "${CMAKE_CURRENT_BINARY_DIR}/catalog fixtures")
endif()
