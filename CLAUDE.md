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
> - **Tapers (`utils/TaperUtils.h`) — V4 FINAL STATE (2026-06-21, user-chosen; web-verified taper
>   types, see `timmy-pot-taper-research`).** BASS `50k·x^2.41`, DRIVE `1e6·x^2.2`, TREBLE
>   `50k·x/(x+1)` (LINEAR-pot rheostat law), VOLUME A25K + **R11 18k**. BASS/TREBLE are CUT controls:
>   **knob up = MORE cut**.
>   • **TREBLE — V4 = LINEAR pot.** Real Timmy tone pots are A (audio) pots wired in REVERSE to mimic
>     C-taper; the documented "forward `10^(2x-2)`" was wrong. But the *later "V4"* unit (which the user
>     is targeting as final) changed TREBLE to a LINEAR (B) pot. Modelled as the genuine linear-pot
>     rheostat `50k·x/(x+1)` (R(0)=0, R(1)=25k physical max). ACCURACY TRADE (user-accepted): our
>     batch-3 captures look like an EARLY reverse-log unit (want concave `29k·x^0.625`, kept in a code
>     comment for reference), so V4 linear runs ~+1.5..+2.8 dB bright @4 kHz at high cut and over-dark
>     at very low treble. (The 06-20 `12k·x^0.4` concave law was WRONG — left it +6..+12 dB too bright;
>     the trap: a 1st-order LP's 8 kHz attenuation SATURATES once the corner < ~800 Hz, so the matched
>     pair's small T5→T8 increment ≠ a gentle taper; the ABSOLUTE level disambiguates.)
>   • **BASS — convex, VALIDATED.** `50k·x^2.41` (coefficient bumped 41k→50k as a fine LF trim:
>     tightens 60 Hz @x=0.8 from +0.8 to +0.1 dB vs real; the 60 Hz cut is only weakly sensitive to
>     this coeff — dominated by C3/C4, not the pot R). Matches real 60 Hz cut within ~±0.4 dB at
>     x=0.5/0.6/0.8 (batch 4 mined for the extra x=0.5 point). Convex is correct: bass sits in the
>     Stage 1 gain leg whose R→cut transfer inverts the pot's concavity. Direction confirmed PRIMARY.
>   • **VOLUME — R11 18k** (V4 spec: 25kA + 18k input→output; repo schematic shows 7k5 = earlier rev).
>   • Residual HF-SHAPE limit (12k over-dark, 1–4k bright at high cut) is a circuit-model issue, NOT a
>     taper one; ±0.3 dB not reachable from this confounded data. Tone stack is FINAL for V4.
> - **Top-octave fix — OVERSAMPLED LINEAR STAGES (2026-06-21).** The base-rate Treble (C5) + Stage 2
>   (C11) caps warp near Nyquist (bilinear), leaving the top octave too dark EVEN AFTER prewarp
>   (probe: −2.33 dB @12k, worse above). FIXED by extending the oversampled region to include Treble
>   + Stage 2: `ClippingOversampler::processBlock` now takes a per-OS-sample `postFn`, and `TommyDSP`
>   runs treble+stage2 inside it (prepared at `getOversampledRate()`). Pure linear-discretisation fix,
>   IDENTICAL in every clip mode. Result: 12k now within ±2 dB of the real pedal (was ~5–8 dB dark);
>   at the default 4x it's already ≈ the true-analog response; below 4 kHz unchanged. The OS factor now
>   meaningfully improves the top octave (it didn't before). Prewarp (`dsp/Prewarp.h`, C5 dynamic + C11
>   fixed) is KEPT — it still helps at 1x (no oversampling). InputBuffer (≈8 Hz HP, no audible HF caps)
>   and the C6 DC block stay at base rate. Residual ±2 dB @12k + ~+2 dB @8k = the HF-SHAPE/measurement
>   confound (driven captures carry clip harmonics in the top), NOT the bilinear warp. Tests 8/8 green.
> - **InputBuffer R1 flag — FIXED 2026-06-21.** R1 (`2m2` = 2.2 MΩ) is now correctly modelled as an
>   input PULLDOWN to GND (was a mislabelled 2.2 Ω series resistor; a 2.2 MΩ *series* element would
>   lose ~14.5 dB + roll off treble). Added a small explicit series source impedance (`rSrc`) so the
>   47 pF RF shunt stays well-posed. Transparent with a low-Z source; Stage0 test still flat in-band.
> - **Asymmetric (Hard) clip mode (2026-06-20):** `AsymDiodePairT` is a SYMMETRIC pair (Medium
>   threshold) shifted by a lateral wave-domain **bias** (`kAsymBias=0.18`) — mild even harmonics
>   WITHOUT the level boost the old per-polarity 1:2 threshold gave (it ran ~3.9 dB hot, coupled to
>   the harmonic match). Now level ≈ Sym and Asym NULLS as well as Sym/Open across drive. Added **C6
>   (1µ ~6 Hz) output DC-block in `TommyDSP`** for the asym clip's signal-dependent DC.
>
> **Analysis harness (`analysis/`):** `offline_render.cpp` (OfflineRender exe — runs the real DSP +
> processBlock gain staging; many override args for fitting) + Python tools (run_compare, sweep_kinput,
> treble_fit/xcheck, harmonics, analyze). NAM captures in `pedal_results{,2,3,4}`. batch 1 = PRIMARY
> pedal; batch 2 = MXR Timmy (SECONDARY ref, opposite knob direction); **batch 3 = PRIMARY pedal,
> PRIMARY direction (knob up = more cut)** — its 6 files: only 4 are full-length/usable (the two 8 s
> files are truncated, no clean sweep), and it's monotonic ONLY when drive is held constant (the lone
> G4 file is the "non-monotonic" outlier — exclude when fitting EQ). The batch-3 EQ re-fit (2026-06-21)
> normalises each transfer @250 Hz so overall drive/level cancels, fits TREB_R/BASS_R per-knob via the
> `offline_render` overrides (trebCoeff/Exp argv11/12, bassCoeff/Exp argv13/14; set Exp=0 for constant
> R), then fits a power law. batch 4 = PRIMARY clock-matrix (switch up/mid/down × gain).
>
> **NEXT STEPS (Step 9 remaining):**
>   1. **EQ tapers — V4 FINAL, DONE 2026-06-21.** Taper TYPES resolved via web research (see
>      `timmy-pot-taper-research`): values & cut-direction CONFIRMED right; tone pots are A-pots wired
>      in REVERSE to mimic C-taper (reverse-log), AND treble is VERSION-DEPENDENT (early = A-reverse;
>      "V4" = LINEAR). **User chose V4 as final** → TREBLE `50k·x/(x+1)` (linear rheostat), VOLUME R11
>      18k. BASS `50k·x^2.41` convex VALIDATED ±0.6 dB (batch 3+4). Accepted trade: V4 linear treble
>      runs +1.5..+2.8 dB bright @4 kHz at high cut vs our (early-unit-looking) captures. Remaining
>      ±0.3 dB gap is HF-SHAPE (12k over-dark, 1–4k bright at high cut) — a circuit-model limit, NOT a
>      taper one. **The 12k bilinear-warp part of that gap is now FIXED** by oversampling Treble +
>      Stage 2 (see the Top-octave fix above — 12k now within ±2 dB of real). The small residual (~±2 dB
>      @12k, ~+2 dB @8k) is the HF-SHAPE/measurement confound (driven captures carry clip harmonics up
>      top), not reachable without a clean low-drive sweep. Tone stack + top-octave handling FINAL.
>   2. **Asym level/null — DONE** (bias-offset model + C6). Remaining null gap: 2–6 kHz residual is
>      harmonic PHASE decorrelation in ALL modes (level-matched: <2k nulls −5/−6 dB, 2–6k ≈ 0) —
>      partly inherent to nulling vs a NAM capture (magnitude/feel, not exact phase). Magnitude matches.
>   3. High-drive clipping-character ceiling (plugin THD ~1–3% under real at 3–5:00 — ideal-op-amp +
>      ideal-diode limit, may live in the 2–6 kHz null gap). Needs a HOT-input pass (~6 dB hotter) to diagnose.
>   4. Then: subjective full-control sweep (Step 9 gate) — no instability/clicks/NaN; finalise kOutputMakeup.
>   - FUTURE FEATURE (user): selectable 9/12/18 V supply = rail-voltage scaler (`setRailVoltages`),
>     orthogonal to tapers/prewarp.
>   - Open items: RT-safety (oversampling `setFactor` allocates on audio thread — pre-allocate if
>     tightening); VST3 still deferred (AU passes auval).**
