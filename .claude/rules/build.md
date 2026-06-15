# Build Rules

## CMake

- CMake build system only — no Projucer
- C++17 minimum standard
- JUCE 8+ via CMake submodule or FetchContent
- `chowdsp_wdf` as CMake submodule (header-only)
- Targets: AU (primary), VST3 (secondary)
- Author: Leigh Pierce | Company: Leigh Pierce

## Project Structure

```
tommy-pedal/
├── CMakeLists.txt
├── CLAUDE.md
├── .claude/
│   ├── agents/
│   │   ├── dsp-validator.md
│   │   └── schematic-checker.md
│   └── rules/
│       ├── circuit.md
│       ├── dsp.md
│       ├── architecture.md
│       ├── ui.md
│       └── build.md
├── src/
│   ├── PluginProcessor.h / .cpp
│   ├── PluginEditor.h / .cpp
│   ├── dsp/
│   │   ├── InputBuffer.h
│   │   ├── Stage1.h
│   │   ├── ClippingStage.h      ← SW1 nonlinear WDF
│   │   ├── TrebleNetwork.h
│   │   ├── Stage2.h
│   │   └── TommyDSP.h          ← top-level DSP wrapper
│   ├── ui/
│   │   ├── TommyLookAndFeel.h / .cpp
│   │   ├── KnobComponent.h / .cpp
│   │   ├── SwitchComponent.h / .cpp
│   │   ├── VUMeter.h / .cpp
│   │   └── LEDIndicator.h / .cpp
│   └── utils/
│       └── TaperUtils.h        ← pot taper conversion functions
├── libs/
│   ├── JUCE/                   ← git submodule
│   └── chowdsp_wdf/            ← git submodule
└── tests/
    ├── SmokeTest_RC.cpp        ← chowdsp_wdf smoke test (step 3)
    ├── Stage1_FreqResponse.cpp
    └── ClippingStage_Sine.cpp
```

## Build Commands

```bash
# Configure
cmake -B build -DCMAKE_BUILD_TYPE=Release

# Build AU
cmake --build build --target Tommy_AU

# Build VST3
cmake --build build --target Tommy_VST3

# Build all
cmake --build build
```

## Plugin Metadata

```cmake
juce_add_plugin(Tommy
    COMPANY_NAME "Leigh Pierce"
    PLUGIN_MANUFACTURER_CODE LeP1
    PLUGIN_CODE Tom1
    FORMATS AU VST3
    PRODUCT_NAME "Tommy"
)
```

## Submodule Setup

```bash
git submodule add https://github.com/juce-framework/JUCE libs/JUCE
git submodule add https://github.com/Chowdhury-DSP/chowdsp_wdf libs/chowdsp_wdf
# Optional but recommended: XSIMD for automatic SIMD acceleration of R-type adaptor matrix multiply
git submodule add https://github.com/xtensor-stack/xsimd libs/xsimd
```

If XSIMD is included, add to CMakeLists.txt before chowdsp_wdf:
```cmake
add_subdirectory(libs/xsimd)
target_link_libraries(Tommy PRIVATE xsimd)
# In DSP code, #include <xsimd/xsimd.hpp> BEFORE #include <chowdsp_wdf/chowdsp_wdf.h>
```
XSIMD accelerates R-type adaptor matrix multiplications automatically — relevant since Stage 1, SW1, and Stage 2 all use R-type adaptors.

**Note on chowdsp_utils:** BYOD also uses `chowdsp_utils` for additional DSP helpers. This project uses only `chowdsp_wdf` directly. If during implementation a helper from `chowdsp_utils` is needed (e.g. for ADAA or filter utilities), add it as a submodule then — do not add it preemptively.

## .gitignore

Add at project root:
```
build/
*.DS_Store
*.user
.idea/
.vscode/
```

## .gitmodules

After running `git submodule add` commands, `.gitmodules` is created automatically. Commit it along with the empty submodule directories. To clone the project fresh with submodules:
```bash
git clone --recurse-submodules <repo-url>
# or after a plain clone:
git submodule update --init --recursive
```

## Compiler / Standard

- `-std=c++17` (chowdsp_wdf requires C++14 minimum; our project uses C++17)
- CMake 3.15 minimum required (chowdsp_wdf requires 3.1+; JUCE 8 requires 3.15+)
- First line of CMakeLists.txt: `cmake_minimum_required(VERSION 3.15)`
- Target macOS 10.13+ (AU requirement)
- Enable `-Wall -Wextra` warnings; treat warnings as errors in CI

## Code Style

Add a `.clang-format` at project root (BYOD-style, based on LLVM):
```yaml
BasedOnStyle: LLVM
IndentWidth: 4
ColumnLimit: 120
BreakBeforeBraces: Attach
AllowShortFunctionsOnASingleLine: Inline
SortIncludes: false
```

Add a `.clang-tidy` at project root with at minimum:
```yaml
Checks: "clang-diagnostic-*,clang-analyzer-*,modernize-*,readability-*,-readability-magic-numbers"
WarningsAsErrors: ""
```

## Validation Gates (do not proceed without)

- Step 2 gate: AU and VST3 both scan and load in a DAW (Logic or Reaper)
- Step 3 gate: RC lowpass smoke test produces correct -3dB point
- Step 4 gates: each stage verified before next (freq response or sine clipping as appropriate)
- Step 5 gate: each switch position verified independently
- Step 9 gate: full control sweep, no instability or clicks
