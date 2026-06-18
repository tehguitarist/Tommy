# Pedal Plugin Template

A starting point for building a new circuit-level guitar-pedal plugin (AU/VST3, JUCE 8+,
`chowdsp_wdf`), capturing the generic engineering and UI from the Tommy overdrive build so you
don't reinvent the wheel each time.

## What's here

```
CLAUDE.md                          project-memory template + the 9-step build sequence
.claude/rules/
  circuit.md                       fill-in-from-schematic template (with reading gotchas)
  dsp.md                           WDF / chowdsp / oversampling / ADAA rules + gotchas
  architecture.md                  threading, plugin structure, processBlock, bypass, OS, state
  ui.md                            UI contract (points at the spec + provided components)
  build.md                         CMake, submodules, layout, testing, validation gates
docs/
  calibration-and-gain-staging.md  ★ the hard-won DSP/level lessons — read first
  ui-peripheral-spec.md            full visual spec for the reusable UI elements
src/
  ui/PedalLookAndFeel.{h,cpp}      palette, knobs, octagonal footswitch, ComboBox, VU drawing
  ui/VUMeter.h                     22-segment bar meter
  ui/ThreePositionSwitch.h         generic vertical toggle (setLabels / onChange)
  ui/LEDIndicator.h                bypass LED
  utils/TaperUtils.h               taper helpers (incl. audioTaperR0 for large gain pots)
```

The `src/ui/*` and `utils/*` files are **drop-in** — they're the proven Tommy code with the
pedal-specific names removed (`PedalLookAndFeel`, `ThreePositionSwitch`). The colour palette is a
dark-navy theme; recolour via the constants in `PedalLookAndFeel.h`.

## How to use it

1. Copy this folder to a new repo (or `cp -R` it and `git init`).
2. Add JUCE / chowdsp_wdf (+ optional xsimd) as submodules under `libs/` (see `.claude/rules/build.md`).
3. Drop the schematic images into `schematics/` and fill in `.claude/rules/circuit.md`.
4. Write `CMakeLists.txt` (use the Tommy one as a model — see build.md for the structure), then
   `PluginProcessor`/`PluginEditor` following `architecture.md`.
5. Follow the 9-step build sequence in `CLAUDE.md`, validating each stage.
6. **Calibrate** per `docs/calibration-and-gain-staging.md` — measure `kInputRef` for your own
   rig; set the output makeup to ~0.9.

## The three things that bit us last time (so they don't bite you)

1. **Input level calibration** — the circuit is nonlinear, so the absolute input voltage decides
   where it clips. Anchor `kInputRef` (volts per full-scale) to a real measurement.
2. **The audio-taper floor** — a 1%-floored taper on a large (1 M) gain pot injects ~10 kΩ that
   adds ~8 dB of phantom minimum gain. Use `audioTaperR0` for pots whose minimum is ~0 Ω.
3. **Output makeup ≈ 0.9** — with the input anchored the circuit sets unity itself; 0.9 is the
   honest value minus a ~1 dB clip-safety pad.
