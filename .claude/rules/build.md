# Build Rules

## CMake

- CMake build system only — no Projucer
- C++17 minimum standard
- JUCE 8+ via CMake submodule or FetchContent
- `chowdsp_wdf` as CMake submodule (header-only)
- `xsimd` as CMake submodule (header-only; SIMD-accelerates the R-type adaptor matrix math)
- Targets: AU only for now (`FORMATS AU` in `CMakeLists.txt`'s `juce_add_plugin` call). VST3 is
  planned but not yet wired up — adding it back is just adding `VST3` to `FORMATS`, no DSP/UI
  changes needed.
- Author: Leigh Pierce | Company: Leigh Pierce

## Project Structure

```
Tommy/
├── CMakeLists.txt
├── CLAUDE.md
├── README.md
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
│   │   ├── ClippingOversampler.h  ← SW1 nonlinear WDF + oversampling wrapper
│   │   ├── TrebleNetwork.h
│   │   ├── Stage2.h
│   │   ├── Prewarp.h              ← bilinear-warp correction for tone/feedback caps
│   │   └── TommyDSP.h             ← top-level DSP wrapper
│   ├── ui/
│   │   ├── TommyLookAndFeel.h / .cpp  ← all procedural drawing lives here
│   │   ├── SW1Switch.h                ← 3-position clipping switch component
│   │   ├── SupplyControl.h            ← interactive 9/12/18V power-label control
│   │   ├── VUMeter.h
│   │   └── LEDIndicator.h
│   └── utils/
│       └── TaperUtils.h        ← pot taper conversion functions
├── libs/
│   ├── JUCE/                   ← git submodule
│   ├── chowdsp_wdf/            ← git submodule
│   └── xsimd/                  ← git submodule
├── analysis/                   ← offline render tool + Python A/B comparison scripts
├── schematics/                 ← source schematics the circuit model is built from
└── tests/
    ├── SmokeTest_RC.cpp            ← chowdsp_wdf smoke test (step 3)
    ├── Stage0_FreqResponse.cpp
    ├── Stage1_FreqResponse.cpp
    ├── ClippingStage_Sine.cpp
    ├── Stage2_Treble_FreqResponse.cpp
    ├── Stage2_RailProbe.cpp
    ├── Step6_Aliasing.cpp
    ├── Step7_Integration.cpp
    └── VolumeCal_Probe.cpp
```

## Build Commands

```bash
# Configure
cmake -B build -DCMAKE_BUILD_TYPE=Release

# Build AU
cmake --build build --target Tommy_AU

# Build all targets (plugin + every test executable)
cmake --build build

# Validate the AU without opening a DAW
auval -v aufx Tom1 LeP1
```

VST3 has no build target yet — see the CMake note above.

## Plugin Metadata

```cmake
juce_add_plugin(Tommy
    COMPANY_NAME "Leigh Pierce"
    BUNDLE_ID com.leighpierce.Tommy
    PLUGIN_MANUFACTURER_CODE LeP1
    PLUGIN_CODE Tom1
    FORMATS AU
    PRODUCT_NAME "Tommy"
    COPY_PLUGIN_AFTER_BUILD TRUE
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

- Step 2 gate: AU scans and loads in a DAW (Logic or Reaper) and passes `auval`. VST3 deferred —
  re-add `VST3` to `FORMATS` and re-run this gate before shipping a VST3 build.
- Step 3 gate: RC lowpass smoke test produces correct -3dB point
- Step 4 gates: each stage verified before next (freq response or sine clipping as appropriate)
- Step 5 gate: each switch position verified independently
- Step 9 gate: full control sweep, no instability or clicks
