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
> **CURRENT: Step 9 — calibration & final sweep (GATE ESSENTIALLY MET, 2026-06-21). Steps 3–8 COMPLETE.
> Full DSP chain + real UI built and validated; tapers V4-FINAL, top-octave warp fixed, build warning-
> free. Step 9 gate: (a) SUBJECTIVE sweep — user confirms all controls respond correctly, no issues;
> (b) OBJECTIVE stability sweep — 144 control corners (bass/treb/vol×drive×3 modes×1x/8x) with a hot
> 0 dBFS input: 0 NaN/Inf, 0 runaway, all bounded. kOutputMakeup FINALISED at 0.9 (see CALIBRATION).
> High-drive THD ceiling RESOLVED via batch-5 hot reamp (see CLIPPING below): odd harmonics + THD
> already matched; added the missing even-harmonic asymmetry. The 9/12/18 V supply feature is DONE.
> No open modelling items remain. Build is SHIPPABLE.**
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
> - `kOutputMakeup = 0.9f` — FINALISED (Step 9 sweep, 2026-06-21). Level-matched to the NAM captures
>   (do NOT lower for headroom — it would make the plugin ~8.7 dB quieter than the real pedal at every
>   setting, breaking the A/B match). HEADROOM REALITY (measured, hot 0 dBFS in): at NOON volume the
>   output is a safe ≈ −6 dBFS for any drive; it crosses 0 dBFS at volume ≈ 0.7 and reaches ≈ +8 dBFS
>   at full drive + full volume + no tone cut. That upper-third "boost zone" is FAITHFUL (a real Timmy
>   cranked overloads an interface the same way), NOT a bug — the −12 dB output trim + the volume knob
>   manage it. (The earlier "worst case ≈ −0.6 dBFS" note was WRONG — untested at full volume/hot input.)
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
> - **CLIPPING — even-harmonic asymmetry, ALL modes (2026-06-22, batch-5 hot reamp).** Diagnosis: at
>   the matched hot input (kInputRef≈2.4 = +6 dB), the plugin's ODD harmonics + overall THD already
>   match the real pedal within ~1 dB at high drive — the "high-drive THD ceiling" was largely a
>   level-calibration artifact, NOT a clipping-model deficiency. The ONE real gap: the real Timmy
>   shows EVEN harmonics (~−47..−55 dB H2 re fund) in EVERY mode incl. symmetric Soft/Medium; a
>   perfectly-matched bipolar diode model produces NONE (−141 dB). Cause = 1N4148 forward-voltage
>   spread between the antiparallel diodes + above-mid-supply VREF bias → slightly asymmetric real
>   thresholds (a component-tolerance effect a "perfect" model can't show). FIX: Soft/Medium now also
>   use `AsymDiodePairT` (at bias=0 it's bit-identical to the old `DiodePairT` — `symReflect(0)=0`),
>   carrying a small global diode-mismatch bias **`kSymBias=0.15`**; Hard's **`kAsymBias` re-calibrated
>   0.18→0.30** to the hot-pass H2. Result @440 Hz G1500: H2 real/new Soft −55/−50, Medium −49/−51,
>   Hard −34/−36 — within ~2–5 dB across modes, ODD harmonics + THD + playing-level output UNCHANGED.
>   Side effect (bias-offset model): near-zero-signal gain perturbed (Soft ~3%, Hard ~21% at a tiny
>   level) — a LOW-LEVEL artifact only; moderate/playing-level output is identical (verified). C6
>   (1µ ~6 Hz) output DC-block in `TommyDSP` handles the asymmetric clips' signal-dependent DC.
>   `offline_render` arg[20]=symBias, arg[15]=asymBias for A/B.
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
>   3. High-drive clipping-character ceiling — **RESOLVED 2026-06-22** (batch-5 hot reamp). Odd
>      harmonics + THD already matched at the right input level; the gap was missing EVEN harmonics,
>      now added via the global diode-mismatch bias (see CLIPPING above). batch 5 = PRIMARY pedal,
>      +6 dB hot, drive 3:00/5:00 × 3 modes (analysis kInputRef ≈ 2.4 for these).
>   4. Step 9 gate DONE (subjective + objective stability sweep passed; kOutputMakeup finalised 0.9).
>   - **Supply-voltage feature — DONE 2026-06-21.** Selectable 9/12/18 V via APVTS `supply_voltage`
>     (default 9 V) → `TommyDSP::setSupplyVoltage` scales BOTH op-amp rails (Stage1 via
>     `ClippingOversampler::setRailVoltages`, Stage2 direct); anchored at 9 V = +2.5/−3.4, slopes
>     +0.451/+0.549 V per supply volt (VREF divider ratio). Diode thresholds unchanged → pure HEADROOM
>     change: 0 effect at moderate levels, clearly present at high output/Hard mode/hot input (Hard
>     swing 9 V ±3.3 → 18 V ±7). UI: the "(+) 9V (−)" power label is now an interactive `SupplyControl`
>     ((+) raises, (−) lowers; lit when that direction is available). offline_render arg[19]=supplyV
>     for A/B. auval passes; default 9 V keeps all renders/tests byte-identical.
>   - Open items: RT-safety (oversampling `setFactor` allocates on audio thread — pre-allocate if
>     tightening); VST3 still deferred (AU passes auval).**
