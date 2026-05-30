# Sayam vitals producer — links against the Homebrew-installed SmartSpectra SDK.
#
# Build:
#   cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
#   cmake --build build
# Run:
#   ./build/sayam_vitals --api_key=YOUR_KEY
cmake_minimum_required(VERSION 3.22.1)
project(SayamVitals CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# SmartSpectra SDK is vendored under vitals/vendor/smartspectra (extracted from
# the official macOS-arm64 release tarball). Its runtime deps (opencv,
# vulkan-loader, molten-vk) come from Homebrew at /opt/homebrew.
list(PREPEND CMAKE_PREFIX_PATH
    "${CMAKE_CURRENT_SOURCE_DIR}/vendor/smartspectra"
    "/opt/homebrew")

find_package(SmartSpectra CONFIG REQUIRED)

add_executable(sayam_vitals main.cc)
target_link_libraries(sayam_vitals PRIVATE SmartSpectra::SDK)
