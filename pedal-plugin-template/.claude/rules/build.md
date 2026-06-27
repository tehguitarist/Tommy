# Build Rules (generic pedal plugin)

## Toolchain

- **CMake only** (no Projucer). `cmake_minimum_required(VERSION 3.15)` on line 1.
- C++17. Target macOS 10.13+ for AU.
- JUCE 8+ and `chowdsp_wdf` (header-only) as submodules under `libs/`.
- Optional but recommended: **xsimd** (accelerates R-type adaptor matrix multiplies). Add it
  before chowdsp_wdf and `#include <xsimd/xsimd.hpp>` before `<chowdsp_wdf/chowdsp_wdf.h>`.
- `-Wall -Wextra` on GCC/Clang. **MSVC's `cl.exe` misparses `-Wextra`** (error D8021: `/W` with a
  non-numeric arg), so gate the flags — `/W4` on MSVC, `-Wall -Wextra` otherwise — via a
  `PEDAL_WARNING_FLAGS` variable (see `CMakeLists.txt.template`). A hardcoded `-Wextra` breaks the
  Windows CI build.
- **Mark third-party headers (chowdsp_wdf, etc.) as SYSTEM includes.** `juce_recommended_warning_flags`
  enables `-Wshadow-field-in-constructor`, which fires harmlessly on chowdsp_wdf's header-only
  constructors (param/field name reuse — not a bug). Don't silence it globally (you'd blind yourself
  to real shadowing). Instead, after `add_subdirectory(libs/chowdsp_wdf)`, re-declare its includes as
  SYSTEM so its noise vanishes while your code stays fully warned (CMake 3.15-compatible):
  ```cmake
  get_target_property(_chowdsp_inc chowdsp_wdf INTERFACE_INCLUDE_DIRECTORIES)
  set_target_properties(chowdsp_wdf PROPERTIES INTERFACE_SYSTEM_INCLUDE_DIRECTORIES "${_chowdsp_inc}")
  ```

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
├── docs/{calibration-and-gain-staging,ui-peripheral-spec,validation-and-capture}.md
├── analysis/                   # gen_test_signal.py + analyze.py (A/B harness) + offline_render.cpp
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

## CI / release (GitHub Actions)

`.github/workflows/ci.yml` and `release.yml` are included as templates (replace `<Pedal>`/`<Cod1>`/
`<Mfr1>`). They're inert inside the template folder — GitHub only reads `.github` at a repo root, so
they activate once you copy the template out.

- **ci.yml** — builds + runs `ctest` on macOS/Windows/Linux on every push/PR. Register each pass/fail
  test exe with `add_test()` (see `CMakeLists.txt.template`) so the whole suite runs as one gate.
- **release.yml** — `workflow_dispatch` ONLY (no push trigger, so a release is never cut by accident):
  builds VST3 (+ AU on macOS) on all three OSes, zips one archive per platform, publishes a draft
  GitHub Release. macOS artifacts are unsigned until you wire up codesign/notarytool.
- **auval on CI gotcha:** a freshly-copied `.component` isn't registered with the
  `AudioComponentRegistrar` on a clean runner, so `auval` fails with "didn't find the component" /
  `-50`. Bounce the registrar (`killall -9 AudioComponentRegistrar`) and retry — the ci.yml step
  already does this. If headless `auval` stays flaky, switch to **pluginval** (validates the built
  bundle directly, no OS registration, cross-platform so it covers the VST3 too).

## Validation gates (do not skip ahead)

- Both plugin formats build + scan/load in a DAW; CI is green on all three platforms.
- Each linear stage's frequency response verified before the next stage.
- Each switch position verified independently.
- Nonlinear aliasing acceptable at the shipped OS default.
- Reference validation vs real-pedal captures (FR / THD-by-band / null) — see
  `docs/validation-and-capture.md`.
- Final: full control sweep — no instability, clicks, or NaN/Inf.
