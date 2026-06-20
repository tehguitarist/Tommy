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
> **CURRENT: Step 9 — calibration & final sweep (IN PROGRESS). Steps 3–8 COMPLETE. Full DSP chain
> + real UI built and validated; now A/B-ing against NAM captures of the real pedal and tuning
> calibration/tapers to match. Currently PAUSED awaiting more audio samples from the user (see NEXT).**
>
> **DSP chain (done):** `src/dsp/` InputBuffer (Stage0) → Stage1+SW1 clipping (oversampled, ADAA on
> rail clip, AccurateOmega) → TrebleNetwork → Stage2, wired via `TommyDSP.h`. IC1_A & IC1_B output
> rails modelled (parabolic-knee + ADAA clamp). auval PASSES; 7 stage tests + Stage2_RailProbe pass.
>
> **UI (Step 8, done):** 480×480 fixed window, three-column layout (Input panel / mottled pedal face /
> Output panel) + oversampling strip with LIVE/RENDER OS ComboBoxes + UI-size selector. Custom
> `TommyLookAndFeel`, halo trim knobs, VU meters, dome bypass. Full design in ui.md.
>
> **CALIBRATION (Step 9, current values in `PluginProcessor.h`):**
> - `kInputRef = 1.2f` (volts per full-scale; re-calibrated from NAM A/B — was 3.27 which over-drove
>   clipping ~9 dB and caused the "harsh/fizzy" tone). Cancels in the linear path; only sets clip onset.
> - `kOutputMakeup = 0.9f` (honest 1.0 minus ~1 dB headroom pad; worst case full-drive/full-vol ≈ −0.6 dBFS).
> - **Tapers (`utils/TaperUtils.h`) — the generic `10^(2x-2)` audio approx was too aggressive.** Refit
>   to measured power laws: BASS `50k·x^1.43`, TREBLE `70k·x^1.43`, DRIVE `1e6·x^2.2`. BASS/TREBLE are
>   CUT controls: **knob up = MORE cut** (confirmed by user). VOLUME = A25K + R11 7.5k divider, unchanged.
> - **Asymmetric (Hard) clip mode:** reworked from one-sided `DiodeT` to `AsymDiodePairT` (per-polarity
>   Vt, 1:2 ratio) in `Stage1.h` — a mild 2-sided asymmetry matching the captured even/odd balance.
>
> **Analysis harness (`analysis/`):** `offline_render.cpp` (OfflineRender exe — runs the real DSP +
> processBlock gain staging; many override args for fitting) + Python tools (run_compare, sweep_kinput,
> treble_fit/xcheck, harmonics, analyze). NAM captures in `pedal_results{,2,3}` (batch 3 unreliable —
> non-monotonic treble, excluded). NOTE: batch 1 = PRIMARY pedal; batch 2 = MXR Timmy (SECONDARY ref,
> opposite knob direction — used for cut DEPTH/curve only, not direction).
>
> **NEXT STEPS (Step 9 remaining — awaiting user audio samples):**
>   1. Re-validate THD-vs-drive across ALL three clip modes (Asym/Open/Sym) over the full drive range —
>      confirm gain reacts identically across clip styles. (User requested; needs a mode×gain matrix:
>      up/mid/down at ~9:00/12:00/3:00 drive, bass/treble/vol fixed at noon, on the PRIMARY pedal.)
>   2. Investigate the high-drive clipping-character ceiling (plugin THD caps ~3-4% below real at full
>      drive — suspected ideal-op-amp + ideal-diode limit, not gain). Needs a HOT-input pass (~6 dB
>      hotter reamp at highest drive) to diagnose.
>   3. Re-fit BASS/TREBLE tapers against the PRIMARY pedal if clean sweeps are provided (currently fit
>      to MXR secondary). Confirm WITH USER which pedal is the primary reference.
>   4. Then: subjective full-control sweep (Step 9 gate) — no instability/clicks/NaN; finalise kOutputMakeup.
>   - Open items: RT-safety (oversampling `setFactor` allocates on audio thread — pre-allocate if
>     tightening); VST3 still deferred (AU passes auval).**
