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
> - **Tapers (`utils/TaperUtils.h`) — RE-FIT 2026-06-21 (batch 3, PRIMARY pedal).** BASS `41k·x^2.41`,
>   DRIVE `1e6·x^2.2`, TREBLE `29k·x^0.625`, VOLUME A25K+R11 7.5k (unchanged). BASS/TREBLE are CUT
>   controls: **knob up = MORE cut**. **The 2026-06-20 TREBLE `12k·x^0.4` "gentle concave" law was
>   WRONG** — it left the plugin +6..+12 dB too BRIGHT @4 kHz. That fit confused the small INCREMENTAL
>   cut of the matched pair (T5→T8 only adds ~2.5 dB @8k) with a gentle taper; but a 1st-order LP's
>   8 kHz attenuation SATURATES once the corner drops below ~800 Hz, so the same small increment occurs
>   at HIGH R. The ABSOLUTE level (real 8k=−16 dB @x=0.5) needs TREB_R ~20k, not ~9k. Back-fitting
>   TREB_R to real 4k & 8k cut (norm @250 Hz, drive cancels) over the consistent-drive G3 captures:
>   x=0.4→16k, 0.5→20k, 0.8→25k → `29k·x^0.625`. BASS similarly over-cut ~2×: real wants x=0.6→12k,
>   0.8→24k → `41k·x^2.41`. **Result: musical-band (60 Hz–8 kHz) error now ~1 dB mean / 2.4 dB max
>   (was 6–12 dB).** Direction confirmed PRIMARY via the B8 matched pair (knob 0.5→0.8 = more cut).
>   LIMITATION: matching 4k/8k forces a low corner that over-darkens 12 kHz by ~5–8 dB and leaves
>   1–4 kHz +1–2.4 dB bright at high cut — an HF-SHAPE (circuit-model) limit, NOT a taper limit (the
>   real top octave rolls off gentler than the plugin's treble-LP + C11 + bilinear stack). ±0.3 dB is
>   NOT reachable from this confounded data; this is the best circuit-informed estimate.
> - **Top-octave prewarp (`dsp/Prewarp.h`, 2026-06-20):** base-rate linear caps warp near Nyquist
>   (bilinear), leaving 12k ~3.8 dB too dark; prewarp C5 (dynamic, tracks TREB) + C11 (fixed) → clean
>   12k −3.8→−2.0 dB. Stage-1 caps NOT prewarped (already oversampled). Residual = chosen prewarp-vs-OS
>   trade. Test suite 7/7 green.
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
>   1. **EQ tapers — best-estimate DONE 2026-06-21** (`29k·x^0.625` treble, `41k·x^2.41` bass; musical
>      band now ~1 dB mean error). ±0.3 dB NOT reached and not reachable from current data — the
>      residual is HF-SHAPE (12k over-dark, 1–4k bright at high cut), a circuit-model limit, not the
>      taper. To go further would need EITHER (a) clean low-drive single-knob sweeps on the PRIMARY
>      pedal (one knob 7→5 o'clock, others noon, drive low enough to not clip the −30 dBFS sweep —
>      current batches clip-confound above ~x=0.35 and only span x≈0.4–0.8 with 2 bass / 3 treble
>      points), OR (b) a higher-order/shape correction to the treble+C11 HF rolloff to match the real
>      pedal's gentler top octave (would also help the 12k deficit). Tone stack is committed as-is.
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
