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

add_executable(Stage2_Treble_FreqResponse tests/Stage2_Treble_FreqResponse.cpp)
target_link_libraries(Stage2_Treble_FreqResponse PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(Stage2_Treble_FreqResponse PRIVATE -Wall -Wextra)

# Step 6 aliasing test needs JUCE (juce::dsp::Oversampling + FFT), so it is a JUCE console app.
juce_add_console_app(Step6_Aliasing PRODUCT_NAME "Step6_Aliasing")
target_sources(Step6_Aliasing PRIVATE tests/Step6_Aliasing.cpp)
target_compile_definitions(Step6_Aliasing PRIVATE
    JUCE_USE_CURL=0
    JUCE_WEB_BROWSER=0
    JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(Step6_Aliasing PRIVATE
    chowdsp::chowdsp_wdf
    juce::juce_dsp
    juce::juce_recommended_config_flags)

# Step 7 full-chain integration test (TommyDSP uses ClippingOversampler -> juce_dsp).
juce_add_console_app(Step7_Integration PRODUCT_NAME "Step7_Integration")
target_sources(Step7_Integration PRIVATE tests/Step7_Integration.cpp)
target_compile_definitions(Step7_Integration PRIVATE
    JUCE_USE_CURL=0
    JUCE_WEB_BROWSER=0
    JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(Step7_Integration PRIVATE
    chowdsp::chowdsp_wdf
    juce::juce_dsp
    juce::juce_recommended_config_flags)
