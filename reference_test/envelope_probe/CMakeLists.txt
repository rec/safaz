cmake_minimum_required(VERSION 3.15)
project(safaz_envelope_probe LANGUAGES C CXX)

# A separate client of the frozen checkout; no sfizz source files are patched.
set(SFIZZ_SOURCE "" CACHE PATH "Unmodified pinned sfizz checkout")
set(SFIZZ_JACK OFF CACHE BOOL "" FORCE)
set(SFIZZ_SHARED OFF CACHE BOOL "" FORCE)
set(SFIZZ_TESTS OFF CACHE BOOL "" FORCE)
set(SFIZZ_RENDER OFF CACHE BOOL "" FORCE)
set(ENABLE_LTO OFF CACHE BOOL "" FORCE)
add_subdirectory("${SFIZZ_SOURCE}" sfizz)

add_executable(envelope_probe main.cpp)
target_compile_features(envelope_probe PRIVATE cxx_std_17)
target_link_libraries(envelope_probe PRIVATE sfizz::internal)
