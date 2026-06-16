cmake_minimum_required(VERSION 3.15)

project(Tommy VERSION 0.1.0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_OSX_DEPLOYMENT_TARGET "10.13" CACHE STRING "Minimum macOS deployment version")

add_subdirectory(libs/JUCE)
add_subdirectory(libs/xsimd)
add_subdirectory(libs/chowdsp_wdf)

juce_add_plugin(Tommy
    COMPANY_NAME "Leigh Pierce"
    BUNDLE_ID com.leighpierce.Tommy
    PLUGIN_MANUFACTURER_CODE LeP1
    PLUGIN_CODE Tom1
    FORMATS AU
    PRODUCT_NAME "Tommy"
)

target_sources(Tommy
    PRIVATE
        src/PluginProcessor.cpp
        src/PluginEditor.cpp
)

target_compile_definitions(Tommy
    PUBLIC
        JUCE_WEB_BROWSER=0
        JUCE_USE_CURL=0
        JUCE_VST3_CAN_REPLACE_VST2=0
)

target_link_libraries(Tommy
    PRIVATE
        juce::juce_audio_utils
        juce::juce_dsp
        chowdsp::chowdsp_wdf
        xsimd
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_lto_flags
        juce::juce_recommended_warning_flags
)

target_compile_options(Tommy PRIVATE -Wall -Wextra)

add_executable(SmokeTest_RC tests/SmokeTest_RC.cpp)
target_link_libraries(SmokeTest_RC PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(SmokeTest_RC PRIVATE -Wall -Wextra)

add_executable(Stage0_FreqResponse tests/Stage0_FreqResponse.cpp)
target_link_libraries(Stage0_FreqResponse PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(Stage0_FreqResponse PRIVATE -Wall -Wextra)

add_executable(Stage1_FreqResponse tests/Stage1_FreqResponse.cpp)
target_link_libraries(Stage1_FreqResponse PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(Stage1_FreqResponse PRIVATE -Wall -Wextra)

add_executable(ClippingStage_Sine tests/ClippingStage_Sine.cpp)
target_link_libraries(ClippingStage_Sine PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(ClippingStage_Sine PRIVATE -Wall -Wextra)
