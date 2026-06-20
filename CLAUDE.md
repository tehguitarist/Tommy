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
>   to measured laws: BASS `50k·x^1.43`, DRIVE `1e6·x^2.2`, TREBLE **`12k·x^0.4` (CONCAVE — batch 3+4,
>   2026-06-20)**: the real Timmy treble is a gentle cut, not a convex audio taper; down-mode 8k delta
>   now ±1 dB across the matrix (was −5.8). BASS/TREBLE are CUT controls: **knob up = MORE cut**.
>   VOLUME = A25K + R11 7.5k divider, unchanged.
> - **Top-octave prewarp (`dsp/Prewarp.h`, 2026-06-20):** base-rate linear caps warp near Nyquist
>   (bilinear), leaving 12k ~3.8 dB too dark; prewarp C5 (dynamic, tracks TREB) + C11 (fixed) → clean
>   12k −3.8→−2.0 dB. Stage-1 caps NOT prewarped (already oversampled). Residual = chosen prewarp-vs-OS
>   trade. Test suite 7/7 green (fixed 3 stale assertions). FLAG: InputBuffer R1=2.2Ω vs circuit.md 2m2.
> - **Asymmetric (Hard) clip mode:** reworked from one-sided `DiodeT` to `AsymDiodePairT` (per-polarity
>   Vt, 1:2 ratio) in `Stage1.h` — a mild 2-sided asymmetry matching the captured even/odd balance.
>
> **Analysis harness (`analysis/`):** `offline_render.cpp` (OfflineRender exe — runs the real DSP +
> processBlock gain staging; many override args for fitting) + Python tools (run_compare, sweep_kinput,
> treble_fit/xcheck, harmonics, analyze). NAM captures in `pedal_results{,2,3}` (batch 3 unreliable —
> non-monotonic treble, excluded). NOTE: batch 1 = PRIMARY pedal; batch 2 = MXR Timmy (SECONDARY ref,
> opposite knob direction — used for cut DEPTH/curve only, not direction).
>
> **NEXT STEPS (Step 9 remaining):**
>   1. **Re-check GAIN & BASS tapers** now treble is fixed (treble is post-clip so shouldn't disturb
>      them, but BASS is in the Stage-1 gain-set leg → coupled to gain; verify vs batch 4).
>   2. **Null-test investigation (user, after tapers):** plugin-vs-pedal null cancels well <2 kHz but
>      WORSE 2–6 kHz, and **Asym clip nulls worse than Sym/Open** (sounds similar by ear; user suspects
>      asym slightly too loud — matches batch-4 data: asym LEVEL ran +1.5–4 dB hot at low drive though
>      even/odd balance matched ±1 dB). Dig into overdrive harmonics/phase in 2–6 kHz + the asym level.
>   3. Clean LOW-DRIVE treble+bass sweeps on the PRIMARY pedal to finalise those tapers past noon
>      (x>0.5 currently extrapolated; batch 3/4 only reach ~0.35–0.8 and are clipping-confounded).
>   4. High-drive clipping-character ceiling (plugin THD ~1–3% under real at 3–5:00 — ideal-op-amp +
>      ideal-diode limit, may live in the 2–6 kHz null gap). Needs a HOT-input pass (~6 dB hotter) to diagnose.
>   5. Then: subjective full-control sweep (Step 9 gate) — no instability/clicks/NaN; finalise kOutputMakeup.
>   - FUTURE FEATURE (user): selectable 9/12/18 V supply = rail-voltage scaler (`setRailVoltages`),
>     orthogonal to tapers/prewarp.
>   - Open items: RT-safety (oversampling `setFactor` allocates on audio thread — pre-allocate if
>     tightening); VST3 still deferred (AU passes auval).**
