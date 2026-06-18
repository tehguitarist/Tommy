# Tommy Overdrive Plugin — Project Memory

> Tommy is a circuit-level emulation of the Cochrane/MXR Timmy overdrive pedal,
> built as an AU/VST3 plugin using JUCE 8+ and chowdsp_wdf WDF modelling.
> Author/Company: Leigh Pierce

## Quick Reference

```
Build:   cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build
Test:    cmake --build build --target Tommy_AU  (then load in DAW)
Lint:    clang-tidy src/**/*.cpp
Format:  clang-format -i src/**/*.{cpp,h}
```

## Schematics

All three are in `schematics/` at the repo root. Load them when verifying any circuit detail.

| File | Role |
|------|------|
| `updated_schematic_-_timmy.png` | Primary source of truth for component values and topology |
| `timmy_switch_refernce.jpg` | Authoritative for SW1 diode network and switch topology |
| `older_schematic_-_Timmy.webp` | Cross-reference only — earlier version, some values differ |

@.claude/rules/circuit.md
@.claude/rules/dsp.md
@.claude/rules/architecture.md
@.claude/rules/ui.md
@.claude/rules/build.md

## Build Sequence (do not skip ahead)

1. Schematic analysis — DONE (see `circuit.md`)
2. JUCE CMake scaffold + APVTS + AU/VST3 targets loading in DAW
3. chowdsp_wdf smoke test — implement a trivial RC lowpass, feed a swept sine, confirm the -3dB point matches `f = 1/(2π×R×C)` to within 1%. Use a short offline render or unit test; do not proceed on a visual guess.
4. Stage-by-stage DSP implementation, validated at each step:
   - Linear stages: verify frequency response against expected transfer function
   - Nonlinear stage (SW1): verify clipping behaviour with a sine wave input
   - **Invoke `dsp-validator` agent after each stage before proceeding**
5. Switch topology switching — verify each SW1 mode independently
6. Oversampling + ADAA on nonlinear stage — verify aliasing reduction
7. Full chain integration + level calibration (-12 dBu)
8. UI implementation
9. Final sweep: all controls full range, no instability, clicks, or NaN output

**Never proceed past a step before validating the current step.**
**Use the `schematic-checker` agent any time a circuit value or topology is in doubt.**

## Current Step

> Update this line at the **start** of each session to reflect where work is resuming,
> and again when a step completes. Do not rely on conversation history to infer progress.
> **CURRENT: Step 8 — UI implementation (see ui.md). Steps 3–7 COMPLETE & validated (details in git history + project memory). Full DSP chain done: `src/dsp/` InputBuffer (Stage0) → Stage1+SW1 clipping (oversampled, ADAA on rail clip, AccurateOmega) → TrebleNetwork → Stage2, wired via `TommyDSP.h`; `utils/TaperUtils.h` A-tapers; `PluginProcessor` has APVTS, smoothed gains, 5ms bypass crossfade, oversampling switching, trims, metering atomics (getInputLevel/getOutputLevel/isBypassed for the editor). auval PASSES; 7 test exes all pass (SmokeTest_RC, Stage0/Stage1/Stage2_Treble freq, ClippingStage_Sine, Step6_Aliasing, Step7_Integration). Editor is still the blank Step-2 scaffold — build the real UI now.
> UI DESIGN CONFIRMED 2026-06-17: 480×480px fixed window (setSize(480,480)). Three-column layout: left panel (74px, Input label + 70px halo trim knob SVG + VU bar fills rest), centre pedal face (flex-1, mottled dark navy/black with blue sparkle dots, white knobs), right panel (74px, Output label + halo trim + VU bar). Pedal face contains: 9V label, Row1 Bass+SW1+Gain, LED, Row2 Volume+Treble, italic Tommy logo, dome bypass button. Oversampling segmented strip (10px gap) below. Full colour palette in ui.md. SW1 labels right of switch body (Soft/Med/Hard top-to-bottom).
> CALIBRATION: input float = volts; `kOutputMakeup`=0.25 (PluginProcessor.h) → ~unity out; refine at Step 9.
> KEY CARRY-FORWARDS to Step 9: (a) DONE 2026-06-17 — IC1_B (Stage 2) output rails NOW modelled (same parabolic-knee+ADAA clamp as Stage 1, `tests/Stage2_RailProbe` confirmed node_J hit impossible ~6.2V in Hard mode = 2× Stage 1 −rail; fixes Hard-louder-than-Soft/Med). ALSO fixed: ADAA was never actually enabled in the plugin (only in Step6 test) — now `setAdaaEnabled(true)` in prepareToPlay routes to both rail clips. Rail values nudged +2.2/−3.1 → +2.5/−3.4 (datasheet ~2V headroom@RL≥2k, light load ~1.2V; NO published Timmy measurement exists, web-searched); (b) RT-safety: oversampling `setFactor` allocates on the audio thread — pre-allocate 4 oversamplers if tightening; (c) refine kOutputMakeup + taper curves/directions + rail voltages by ear. Step 2: AU passes auval. VST3 deferred.**
