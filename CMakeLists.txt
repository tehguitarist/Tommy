cmake_minimum_required(VERSION 3.15)

project(Tommy VERSION 1.0.1)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_OSX_DEPLOYMENT_TARGET "10.13" CACHE STRING "Minimum macOS deployment version")

enable_testing()

# -Wall/-Wextra are GCC/Clang flags; MSVC's cl.exe misparses "-Wextra" as the /W switch with a
# non-numeric argument (error D8021). Use /W4 as the MSVC equivalent.
if (MSVC)
    set(TOMMY_WARNING_FLAGS /W4)
else()
    set(TOMMY_WARNING_FLAGS -Wall -Wextra)
endif()

add_subdirectory(libs/JUCE)
add_subdirectory(libs/xsimd)
add_subdirectory(libs/chowdsp_wdf)

# Treat chowdsp_wdf's headers as SYSTEM includes so its internal warnings (e.g.
# -Wshadow-field-in-constructor, pulled in by juce_recommended_warning_flags) don't surface in our
# build, while -Wall/-Wextra still apply to OUR code. (chowdsp_wdf is a header-only INTERFACE target;
# re-declaring its interface include dir as SYSTEM is the portable, CMake 3.15-compatible way.)
get_target_property(_chowdsp_inc chowdsp_wdf INTERFACE_INCLUDE_DIRECTORIES)
set_target_properties(chowdsp_wdf PROPERTIES INTERFACE_SYSTEM_INCLUDE_DIRECTORIES "${_chowdsp_inc}")

juce_add_binary_data(TommyUIAssets
    SOURCES
        assets/ui/T_Knob.png
        assets/ui/vol_trim.png
        assets/ui/tommy_texture.png
        assets/ui/blue_led_on.png
        assets/ui/blue_led_off.png
        assets/ui/footswitch_up.png
        assets/ui/footswitch_down.png
        assets/ui/switch_up.png
        assets/ui/switch_mid.png
        assets/ui/switch_down.png
)

juce_add_plugin(Tommy
    COMPANY_NAME "Leigh Pierce"
    BUNDLE_ID com.leighpierce.Tommy
    PLUGIN_MANUFACTURER_CODE LeP1
    PLUGIN_CODE Tom1
    FORMATS AU VST3
    PRODUCT_NAME "Tommy"
    COPY_PLUGIN_AFTER_BUILD TRUE
)

target_sources(Tommy
    PRIVATE
        src/PluginProcessor.cpp
        src/PluginEditor.cpp
        src/ui/TommyLookAndFeel.cpp
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
        TommyUIAssets
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_lto_flags
        juce::juce_recommended_warning_flags
)

target_compile_options(Tommy PRIVATE ${TOMMY_WARNING_FLAGS})

add_executable(SmokeTest_RC tests/SmokeTest_RC.cpp)
target_link_libraries(SmokeTest_RC PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(SmokeTest_RC PRIVATE ${TOMMY_WARNING_FLAGS})
add_test(NAME SmokeTest_RC COMMAND SmokeTest_RC)

add_executable(Stage0_FreqResponse tests/Stage0_FreqResponse.cpp)
target_link_libraries(Stage0_FreqResponse PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(Stage0_FreqResponse PRIVATE ${TOMMY_WARNING_FLAGS})
add_test(NAME Stage0_FreqResponse COMMAND Stage0_FreqResponse)

add_executable(Stage1_FreqResponse tests/Stage1_FreqResponse.cpp)
target_link_libraries(Stage1_FreqResponse PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(Stage1_FreqResponse PRIVATE ${TOMMY_WARNING_FLAGS})
add_test(NAME Stage1_FreqResponse COMMAND Stage1_FreqResponse)

add_executable(ClippingStage_Sine tests/ClippingStage_Sine.cpp)
target_link_libraries(ClippingStage_Sine PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(ClippingStage_Sine PRIVATE ${TOMMY_WARNING_FLAGS})
add_test(NAME ClippingStage_Sine COMMAND ClippingStage_Sine)

add_executable(Stage2_Treble_FreqResponse tests/Stage2_Treble_FreqResponse.cpp)
target_link_libraries(Stage2_Treble_FreqResponse PRIVATE chowdsp::chowdsp_wdf)
target_compile_options(Stage2_Treble_FreqResponse PRIVATE ${TOMMY_WARNING_FLAGS})
add_test(NAME Stage2_Treble_FreqResponse COMMAND Stage2_Treble_FreqResponse)

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
add_test(NAME Step6_Aliasing COMMAND Step6_Aliasing)

# Stage 2 rail probe (measurement, not pass/fail): peak node_J across the operating space.
juce_add_console_app(Stage2_RailProbe PRODUCT_NAME "Stage2_RailProbe")
target_sources(Stage2_RailProbe PRIVATE tests/Stage2_RailProbe.cpp)
target_compile_definitions(Stage2_RailProbe PRIVATE
    JUCE_USE_CURL=0
    JUCE_WEB_BROWSER=0
    JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(Stage2_RailProbe PRIVATE
    chowdsp::chowdsp_wdf
    juce::juce_dsp
    juce::juce_recommended_config_flags)

# Offline renderer for A/B analysis vs NAM captures (uses TommyDSP -> juce_dsp).
juce_add_console_app(OfflineRender PRODUCT_NAME "OfflineRender")
target_sources(OfflineRender PRIVATE analysis/offline_render.cpp)
target_compile_definitions(OfflineRender PRIVATE
    JUCE_USE_CURL=0
    JUCE_WEB_BROWSER=0
    JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(OfflineRender PRIVATE
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
add_test(NAME Step7_Integration COMMAND Step7_Integration)

# v1.1 CPU/latency benchmark (TommyDSP uses ClippingOversampler -> juce_dsp). Measurement probe,
# not an accuracy test — see PerfBenchmark.cpp's header comment.
juce_add_console_app(PerfBenchmark PRODUCT_NAME "PerfBenchmark")
target_sources(PerfBenchmark PRIVATE tests/PerfBenchmark.cpp)
target_compile_definitions(PerfBenchmark PRIVATE
    JUCE_USE_CURL=0
    JUCE_WEB_BROWSER=0
    JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(PerfBenchmark PRIVATE
    chowdsp::chowdsp_wdf
    juce::juce_dsp
    juce::juce_recommended_config_flags)
add_test(NAME PerfBenchmark COMMAND PerfBenchmark)

# v1.1 feature CPU-vs-accuracy profiler (omega solver / ADAA / OS-region / mismatch). Measurement
# probe (asserts finite output only) — informs the HQ-mode decision. See FeatureProfile.cpp header.
juce_add_console_app(FeatureProfile PRODUCT_NAME "FeatureProfile")
target_sources(FeatureProfile PRIVATE tests/FeatureProfile.cpp)
target_compile_definitions(FeatureProfile PRIVATE
    JUCE_USE_CURL=0
    JUCE_WEB_BROWSER=0
    JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(FeatureProfile PRIVATE
    chowdsp::chowdsp_wdf
    juce::juce_dsp
    juce::juce_recommended_config_flags)
add_test(NAME FeatureProfile COMMAND FeatureProfile)

# v1.1 OS-factor fidelity probe (how close 1x/2x/4x are to 8x for FR + distortion). Measurement
# probe (finite-only) — see OSFidelity.cpp header.
juce_add_console_app(OSFidelity PRODUCT_NAME "OSFidelity")
target_sources(OSFidelity PRIVATE tests/OSFidelity.cpp)
target_compile_definitions(OSFidelity PRIVATE
    JUCE_USE_CURL=0
    JUCE_WEB_BROWSER=0
    JUCE_STANDALONE_APPLICATION=1)
target_link_libraries(OSFidelity PRIVATE
    chowdsp::chowdsp_wdf
    juce::juce_dsp
    juce::juce_recommended_config_flags)
add_test(NAME OSFidelity COMMAND OSFidelity)
