# Build Rules (generic pedal plugin)

## Toolchain

- **CMake only** (no Projucer). `cmake_minimum_required(VERSION 3.15)` on line 1.
- C++17. Target macOS 10.13+ for AU.
- JUCE 8+ and `chowdsp_wdf` (header-only) as submodules under `libs/`.
- Optional but recommended: **xsimd** (accelerates R-type adaptor matrix multiplies). Add it
  before chowdsp_wdf and `#include <xsimd/xsimd.hpp>` before `<chowdsp_wdf/chowdsp_wdf.h>`.
- `-Wall -Wextra`; treat warnings as errors in CI.

## Submodule setup

```bash
git submodule add https://github.com/juce-framework/JUCE libs/JUCE
git submodule add https://github.com/Chowdhury-DSP/chowdsp_wdf libs/chowdsp_wdf
git submodule add https://github.com/xtensor-stack/xsimd libs/xsimd   # optional
git submodule update --init --recursive
```

## Build commands

```bash
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target <Pedal>_AU      # AU (primary)
cmake --build build                          # everything (incl. test exes)
```
`COPY_PLUGIN_AFTER_BUILD TRUE` installs the AU to `~/Library/Audio/Plug-Ins/Components/` on build.
Logic caches AU components — **bump the project VERSION** to force a rescan after changes, or
remove/re-add the plugin.

## Project layout

```
<pedal>/
├── CMakeLists.txt
├── CLAUDE.md
├── .claude/rules/{build,architecture,dsp,ui,circuit}.md
├── docs/{calibration-and-gain-staging,ui-peripheral-spec}.md
├── schematics/                 # the source-of-truth images
├── src/
│   ├── PluginProcessor.{h,cpp}
│   ├── PluginEditor.{h,cpp}
│   ├── dsp/                     # one header per stage + a top-level wrapper
│   ├── ui/                      # PedalLookAndFeel, VUMeter, ThreePositionSwitch, LEDIndicator
│   └── utils/TaperUtils.h
├── libs/ {JUCE, chowdsp_wdf, xsimd}
└── tests/                       # per-stage validation exes
```

## Testing pattern (validate every stage before moving on)

- Linear stages: pure chowdsp_wdf console exes (no JUCE) — verify frequency response vs the
  expected transfer function (e.g. RC −3 dB point within 1%).
- Nonlinear stage: sine-in clipping checks; aliasing measurement (needs JUCE for
  `juce::dsp::Oversampling` + FFT — use `juce_add_console_app`).
- Full chain: integration test across all modes × OS factors; assert finite, bounded output.
- Throwaway measurement probes (gain, rail levels) are fine standalone:
  `c++ -std=c++17 -O2 -I libs/chowdsp_wdf/include tests/Probe.cpp -o build/Probe` (works for
  headers that only pull chowdsp_wdf, not JUCE).

## Code style

`.clang-format` (LLVM base, IndentWidth 4, ColumnLimit 120, BreakBeforeBraces Attach,
AllowShortFunctionsOnASingleLine Inline, SortIncludes false) and a `.clang-tidy`
(`clang-diagnostic-*,clang-analyzer-*,modernize-*,readability-*,-readability-magic-numbers`) are
included in the template root.

## Validation gates (do not skip ahead)

- Both plugin formats scan/load in a DAW.
- Each linear stage's frequency response verified before the next stage.
- Each switch position verified independently.
- Nonlinear aliasing acceptable at the shipped OS default.
- Final: full control sweep — no instability, clicks, or NaN/Inf.
