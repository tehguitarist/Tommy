# Tommy

Tommy is an overdrive plugin (AU and VST3) modelled on the classic "transparent overdrive"
pedal circuit. Rather than capturing a handful of fixed gain settings, Tommy simulates the actual
analog circuit — drive stage, diode clipper, passive tone network, and output buffer — sample by
sample, so every control behaves the way the real pedal's electronics would at any setting in between.

> Tommy is an original implementation built from circuit analysis and is not affiliated
> with or endorsed by any pedal manufacturer.

**[⬇ Download the latest release](https://github.com/tehguitarist/Tommy/releases/latest)**

<img src="image.png" width=60% />

## Overview

Under the hood, Tommy's signal path is built as a [Wave Digital Filter](https://en.wikipedia.org/wiki/Wave_digital_filter)
(WDF) network using [`chowdsp_wdf`](https://github.com/Chowdhury-DSP/chowdsp_wdf). Every
resistor, capacitor, and diode in the original circuit has a corresponding WDF element
with the real component's value; the nonlinear clipping diodes are solved with
Newton-Raphson iteration rather than a curve-fit approximation. The result responds to
the interaction between controls the way the analog circuit does — turning up Bass
changes how Gain behaves, because on the real pedal they share the same feedback
network, and that coupling is modelled directly rather than faked with two independent
EQ curves.

## Features

- **Circuit-accurate drive stage** — Bass and Gain share a single coupled feedback
  network, modelled as one WDF tree (not two independent controls), matching the
  real pedal's interactive behavior
- **Three-position clipping switch** (Symmetrical / Open / Asymmetrical) — switches
  between three precomputed diode network topologies (two antiparallel pairs, one
  pair, or a single diode), each solved with per-component 1N4148 Shockley diode parameters
- **Interactive passive treble network** — modelled as a coupled RC filter rather than
  a generic shelving EQ
- **Per-polarity diode mismatch modelling** — reproduces the subtle even-harmonic
  content real diode tolerances add to the clipped signal, which a "perfectly matched"
  diode pair can't produce on its own
- **Selectable supply voltage** (9V / 12V / 18V) — raises op-amp rail headroom exactly
  as it would on the real pedal's power jack, without touching diode clipping thresholds
- **Oversampling with antiderivative anti-aliasing (ADAA)** — 1x/2x/4x/8x, with
  independent factors for live playback and offline rendering, applied across the
  clipping stage and the downstream linear stages so the top octave stays accurate
  at any factor
- **Calibrated I/O** — input and output trim with VU-style metering, calibrated to
  -12 dBu internal headroom
- **True bypass** with a short crossfade to avoid clicks
- **Resizable UI** from 50% to 250%, with the scale remembered per session

## Circuit accuracy

Tommy's response was validated against real-pedal reamp captures rather than tuned by ear
alone. The plugin is rendered through the exact same DSP and gain staging it ships with, then
compared to the captures across dozens of knob settings using the analysis harness in
[`analysis/`](analysis/) (1/3-octave frequency response, continuous THD-vs-frequency via
exponential-sweep harmonic separation, and a level-matched null test). Measured results:

- **Frequency response** tracks the real pedal within about **±1.5 dB across 20 Hz–20 kHz**
  once level-matched — tightest (~±0.5 dB) through the low end and midband, with the largest
  deviations in the top treble at heavy-cut settings (a deliberate taper trade-off).
- **Total harmonic distortion** tracks within **a few percent across 40 Hz–16 kHz** and across
  every gain and clipping-mode setting; the model runs slightly under the real pedal only in
  the 2–8 kHz band at very high drive.
- **Second-harmonic level** at high drive matches within **~1 dB** across all three clipping
  modes — including the even-harmonic asymmetry a symmetric diode model can't reproduce.
- **Top-octave response** (most sensitive to digital discretization error) is within **±2 dB**
  at the default oversampling factor — oversampling the linear stages after the clipper closed
  most of a several-dB gap a 1x-only fix couldn't.
- **Output level** matches the real pedal within ~±0.5 dB at and above noon volume, with unity
  gain landing at 1 o'clock as on the real pedal.
- A **level-matched null** against the captures reaches about **−14 dB** at the cleanest
  settings and **−8 to −12 dB** across the range. About half of that residual is linear
  (EQ-shape + phase): after correcting linear differences, the **purely nonlinear residual — the
  real measure of how well the clipping itself matches — is ~−20 dB across all three modes.**
  (Nulling against a NAM capture has an inherent floor — the capture is itself a model, and the
  phase of clipping harmonics decorrelates — so this measures timbre/feel agreement, not a
  sample-exact match.)

None of this is neural-net or sample-based modelling — every stage is an analytic circuit solve,
so the plugin's behavior generalizes to settings and signal levels that were never explicitly
captured.

## Where to find things

```
src/
  PluginProcessor.{h,cpp}    Plugin entry point, parameter layout, processBlock
  PluginEditor.{h,cpp}       Top-level UI layout
  dsp/                       The WDF circuit model, one file per circuit stage
    InputBuffer.h              Input network
    Stage1.h                   Drive stage (IC1_A) + SW1 diode clipping
    ClippingOversampler.h      Oversampling wrapper around Stage1
    TrebleNetwork.h            Passive treble filter
    Stage2.h                   Output buffer stage (IC1_B)
    Prewarp.h                  Bilinear-warp correction for the tone/feedback caps
    TommyDSP.h                 Wires the stages into the full signal chain
  ui/                        Custom LookAndFeel and UI components (image-based controls)
  utils/
    TaperUtils.h                Potentiometer taper curves

tests/                      Per-stage validation executables (frequency response,
                             clipping behavior, aliasing reduction, full-chain checks)
analysis/                   Offline render tool + Python scripts used to compare the
                             plugin's output against real-pedal reamp captures

.claude/rules/               Detailed circuit/DSP/architecture/UI/build references —
                             read circuit.md if you want the full component-by-component
                             schematic breakdown
```

## Installing a release build

Each [Release](https://github.com/tehguitarist/Tommy/releases) ships two ways to install per
platform — a plain zip of the plugin files (for anyone who'd rather drop them in manually) and a
guided installer. Six files total:

| Platform | Zip (manual) | Installer |
|---|---|---|
| macOS | `Tommy-macOS-vX.Y.Z.zip` — AU + VST3 | `Tommy-macOS-vX.Y.Z-Installer.pkg` — lets you choose AU, VST3, or both (both checked by default) |
| Windows | `Tommy-Windows-vX.Y.Z.zip` — VST3 | `Tommy-Windows-vX.Y.Z-Installer.exe` — VST3 only (no AU on Windows) |
| Linux | `Tommy-Linux-vX.Y.Z.zip` — VST3 | `Tommy-Linux-vX.Y.Z-Installer.deb` — VST3 only (no AU on Linux) |

### Installer (recommended)

- **macOS:** double-click the `.pkg` and follow the prompts. A "Customize" screen lets you pick AU
  and/or VST3; both are selected by default. Installs to `/Library/Audio/Plug-Ins/Components` and
  `/Library/Audio/Plug-Ins/VST3` respectively.
- **Windows:** run the `.exe` and follow the prompts. Installs the VST3 to
  `%COMMONPROGRAMFILES%\VST3\Tommy.vst3`. Includes an uninstaller.
- **Linux:** `sudo dpkg -i Tommy-Linux-vX.Y.Z-Installer.deb` installs the VST3 to
  `/usr/lib/vst3/Tommy.vst3`.

### Manual (zip)

Unzip and copy the plugin bundle(s) to your system's plugin folder yourself:

- **macOS:** `Tommy.component` → `~/Library/Audio/Plug-Ins/Components/` (or
  `/Library/Audio/Plug-Ins/Components/` for all users), `Tommy.vst3` → `~/Library/Audio/Plug-Ins/VST3/`
  (or `/Library/Audio/Plug-Ins/VST3/`).
- **Windows:** `Tommy.vst3` → `C:\Program Files\Common Files\VST3\`.
- **Linux:** `Tommy.vst3` → `~/.vst3/` (or `/usr/lib/vst3/` for all users).

> **macOS signing:** release artifacts (the AU/VST3 bundles and the `.pkg` installer itself) are
> signed with Developer ID certificates and notarized by Apple — no Gatekeeper warning on launch
> or on double-clicking the installer.

## Building

Requires CMake 3.15+, a C++17 compiler, and the JUCE, chowdsp_wdf, and xsimd submodules
(xsimd accelerates the circuit's matrix math). Builds as an Audio Unit + VST3 on macOS, and
VST3 on Windows/Linux.

```bash
git clone --recurse-submodules https://github.com/tehguitarist/Tommy
cd Tommy
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target Tommy_AU    # macOS only
cmake --build build --target Tommy_VST3  # all platforms
```

The AU is copied into `~/Library/Audio/Plug-Ins/Components/` automatically after the
build. To validate it without opening a DAW:

```bash
auval -v aufx Tom1 LeP1
```

### Running the test suite

Each circuit stage has a standalone validation executable that checks it against an
analytic transfer function or known circuit behavior. They're registered with CTest, so
the whole suite runs as one pass/fail gate (this is also what CI runs on every push/PR):

```bash
cmake --build build
ctest --test-dir build --output-on-failure
```

## License

Tommy is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPLv3).

## Credits

Built by Leigh Pierce, using:

- [JUCE](https://juce.com/) — plugin framework and UI toolkit
- [chowdsp_wdf](https://github.com/Chowdhury-DSP/chowdsp_wdf) — Wave Digital Filter
  modelling library
- [xsimd](https://github.com/xtensor-stack/xsimd) — SIMD acceleration for the circuit's
  matrix math

Thanks to the Chowdhury DSP and JUCE communities for the tools that made a
circuit-accurate approach practical to build solo.
