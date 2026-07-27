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

@.claude/rules/circuit.md
@.claude/rules/dsp.md
@.claude/rules/architecture.md
@.claude/rules/ui.md
@.claude/rules/build.md

> The original schematic source images (`schematics/`) were removed from the repo after the
> circuit analysis in `circuit.md` was finalized and cross-checked — `circuit.md` is now the
> source of truth for all component values and topology. If a value is ever in doubt and the
> physical pedal is available, re-verify against hardware rather than re-deriving from memory.

## Build Sequence (reference — all steps below are complete)

1. Schematic analysis (`circuit.md`)
2. JUCE CMake scaffold + APVTS + AU/VST3 targets
3. chowdsp_wdf smoke test (RC lowpass, -3dB point within 1%)
4. Stage-by-stage DSP implementation (linear stages vs. transfer function, SW1 vs. sine-wave clipping)
5. SW1 switch topology — each mode verified independently
6. Oversampling + ADAA on the clipping/rail-clip stage
7. Full chain integration + level calibration (-12 dBu internal)
8. UI implementation
9. Calibration & final sweep

**Use the `schematic-checker` agent any time a circuit value or topology is in doubt; use
`dsp-validator` after any DSP stage change.**

## Current State

**Status: SHIPPABLE, v1.3.0 + unreleased v1.4 fidelity work (W5 harness, W1 Medium clip
threshold, W2 low-drive clip onset — see Roadmap).** All 9 build-sequence steps are complete. Full DSP chain
(`src/dsp/`: InputBuffer → Stage1+SW1 clipping, oversampled with ADAA on the rail clip and
`AccurateOmega` → TrebleNetwork → Stage2, wired via `TommyDSP.h`, then base-rate
`TopOctaveRestore` (corrects the low-OS top-octave droop) + `DriveTilt` (corrects a low-drive
top-octave tilt vs the real pedal) shelves) is validated; op-amp output
rails are modelled on both stages. `auval` passes; 9 test executables pass (two, `PerfBenchmark`
and `FeatureProfile`, are measurement probes rather than pass/fail accuracy — `PerfBenchmark` →
README's Performance table; `FeatureProfile` → the v1.1 roadmap's CPU-vs-accuracy data). UI
(Step 8) is a
fixed 480×480 three-column layout — full design in `ui.md`. **W4 is FIXED and shipped**
(`src/dsp/BassTilt.h`, a DRIVE+mode-keyed 250 Hz low shelf — SHAPE 12/16 → 16/16 with no capture
regressed); **the only open modelling item is W3** (likely unfixable; W7 was closed into it
2026-07-27 — characterised, its one lever refuted, no independently fixable component left).
Nothing is "blocked on captures" any more — W6 is struck, see Roadmap.

> **DSP stage classes are templated on the diode omega provider** (`Stage1T`/`ClippingOversamplerT`/
> `TommyDSPT`, all defaulting to `AccurateOmega`; `Stage1`/`ClippingOversampler`/`TommyDSP` are the
> production aliases). The template parameter exists solely so `FeatureProfile` can A/B the accurate
> solver against chowdsp's fast `omega4` — production code is byte-for-byte unchanged. `ClipMode` is
> namespace-scoped (one type across all instantiations) with a `Stage1::ClipMode` member alias.

### Calibration constants (`PluginProcessor.h` / `TaperUtils.h`)

These are load-bearing — verified against the authoritative batch-3/4/5 NAM captures
(`analysis/`); do not change without re-running `analysis/knob_tracking.py`.

- `kInputRef = 1.2f` — volts per full-scale; sets clip onset only (cancels in the linear path).
- `kOutputMakeup = 1.217f` — flat output-level correction (was 0.9; the plugin measured a
  constant ~2.6 dB quiet at every clean setting independent of input level/volume position).
- Tapers (`utils/TaperUtils.h`, V4 — final, user-chosen pedal revision):
  BASS `50k·x^2.41` (convex — validated ±0.6 dB), DRIVE `1e6·x^2.75` (**re-fitted 2026-07-27,
  v1.4 W2, from `x^2.2`** — the 2.2 value predated both v1.2.1's `kIs` halving and W1 and was fitted
  at mid drive, where THD saturates and is blind to pre-clip gain; see `driveResistance`'s comment),
  TREBLE `50k·x/(x+1)` (linear-pot rheostat — V4 units use a linear pot, not the earlier
  reverse-log audio pot; trades ~+1.5–2.8 dB brightness at high cut for matching the real V4
  unit), VOLUME = A25K pot + R11 18k. BASS/TREBLE are cut controls: knob up = more cut.
- Medium clip mode has its OWN diode parameters (`Stage1.h`: `kIsMedium` = `kIs`, same diode part;
  `kNMedium` = `1.35·kN` ⇒ Vt_eff 61.1 mV vs Soft's 45.3 mV). Deriving Medium as "one pair instead
  of two" (plain `kIs`) puts it only ~31 mV from Soft, but the real pedal's Medium is markedly
  cleaner at low level *and* harder at high level. Fitted 2026-07-26 (v1.4 W1); **Soft is
  bit-identical and is what pins the shared diode parameters.** The multiplier is capped by the
  op-amp rails, not the THD fit (1.5× fitted better but manufactures even harmonics) — see
  `circuit.md`'s Mode B threshold note **and its Op-Amp Model rail note**. Medium's diode mismatch
  is rescaled by `kN/medN` (`Stage1T::mediumMismatch()`) so its *absolute* Vf spread still equals
  Soft's — `kSymMismatch` is a fraction of Vt_eff, so it would otherwise have scaled with it.
- Diode mismatch (`AsymDiodePairT`, all clip modes) models the even-harmonic content real
  diode tolerance adds: `kSymMismatch = 0.06` (Soft/Medium), `kAsymMismatch = 0.45` (Hard).
  Per-polarity Vt mismatch, not a DC bias — leaves small-signal gain unperturbed.
- Op-amp output rails: +2.5/−3.4 V at the 9 V default (no published bench measurement exists;
  estimated from datasheet swing at the pedal's light load). `supply_voltage` (9/12/18 V)
  scales both rails at +0.451/+0.549 V per supply volt (VREF divider ratio); diode thresholds
  are unaffected — it's a pure headroom change.

### Known residuals (not masked with extra makeup gain — documented limits, not bugs)

- **High drive (G0.65+) quiet residual — FIXED (2026-07-04).** Was ~2–3.5 dB quiet vs pedal2 at
  moderate signal levels, worst at quiet/moderate input and vanishing at -3 dBFS (signal pinned
  against the clip ceiling) — proving the diode/rail clip depth itself was accurate and the
  shortfall was in the PRE-CLIP gain, not clip depth. Ruled out the DRIVE taper and BASS/DRIVE
  coupling (sweeping `drive` to 50x its normal range only closed ~0.2 dB — gain hard-asymptotes
  regardless). Root cause, confirmed by schematic-checker + dsp-validator: past a certain DRIVE
  setting the R7+DRIVE branch's impedance dominates itself out of the feedback parallel
  combination, so gain is set almost entirely by the diode network's own incremental impedance —
  no WDF/topology bug (Norton injection, impedance propagation, and the Wright-omega solve all
  verified numerically correct), so the gap was a genuine parameter mismatch. **Fix: `Stage1.h`'s
  `kIs` (1N4148 saturation current) 2.52e-9 → 1.26e-9** — exactly half the datasheet-typical value,
  justified by normal unit-to-unit 1N4148 Is spread (the datasheet figure was never a per-unit
  measurement). Closes pedal2's LEVEL check from 12/16 to 16/16 pass; all 7 ctest suite tests still
  pass (a steeper ~6.5x reduction closed the gap almost exactly but failed `ClippingStage_Sine`'s
  large-signal Hard-mode check — half was the best-supported trade-off). Residual after the fix:
  ~1.1–1.6 dB at the asymptote (down from ~1.8–2.6 dB), and two ALREADY-marginal SHAPE cases
  (G0.20 "up", G0.80 "mid" — both ~1.4–1.5 dB, just under/over the 1.5 dB threshold) shifted to a
  FAIL; harmonic content (H2-H7, THD, even/odd character) unaffected. See `Stage1.h`'s `kIs`
  comment and `dsp.md`'s 1N4148 section for the full derivation. Rs (0.568Ω, omitted as negligible)
  was checked and ruled out as a cause — its ohmic drop is orders of magnitude too small.
- B0.65 SHAPE fails (2 of 16 pedal2 settings, independent of the fix above): the plugin's bass is
  ~+3 dB hot at BASS≈0.65. In the pedal2 captures B0.65 only appears with high drive, so it's
  confounded (bass taper vs BASS/DRIVE coupling) — needs a dedicated bass-sweep-at-fixed-drive
  capture to fix safely (the BASS taper is validated against batch 3/4/5, not in-repo). Deferred.
  **Update (2026-07-26, `.claude/plans/v1.4-fidelity.md` §1.2):** the per-band data narrows this —
  the LF excess is *clip-mode dependent* (Medium > Hard > Soft at matched drive) and shrinks as the
  clipper is driven, so it is a BASS↔DRIVE **coupling** error, not a BASS taper error. Still needs
  the bass-sweep-at-fixed-drive capture to fit.
- Top octave: the low-OS bilinear droop is fixed by oversampling Treble+Stage2 + `TopOctaveRestore`;
  the low-DRIVE linear tilt is fixed by `DriveTilt` (v1.2, calibrated to pedal2 — SHAPE 8/16→14/16).
  The hot tone-set pedal1 disagrees with pedal2 on the top octave; **pedal2 is the definitive tone
  reference** (user decision).
- 2–6 kHz null-test residual — harmonic phase decorrelation vs. the NAM capture, not a
  magnitude error.

### Analysis harness (`analysis/`)

`offline_render.cpp` runs the real DSP + gain staging for A/B against reamp captures; Python
tools (`run_compare.py`, `swept_thd.py`, `null_test.py`, `knob_tracking.py`,
`volume_supply_check.py`, etc.) compare against NAM captures. Capture batches: 1 = primary
pedal reference; 2 = MXR Timmy (secondary, opposite knob direction — informational only);
**3/4/5 = primary pedal, primary direction — the authoritative reference** used for all current
calibration (3 = EQ taper fit, 4 = clip-mode matrix, 5 = hot reamp for high-drive harmonics).
See `analysis/README.md` for harness usage and `analysis/CAPTURE_SPEC.md` for capture protocol.

## Roadmap

> Tracks what's done per version and what's deliberately deferred, so it survives context
> resets. Update the version line here, not just "Current State" above, when a release ships.

- **v0.7:** CI (build+test on every push/PR) and a manual-trigger release workflow that builds
  VST3 (macOS/Windows/Linux) + AU (macOS) and publishes a zip per platform.
- **v0.8:** Reference-validation pass against batch-3/4/5 captures — built the analysis harness
  above, found and fixed the `kOutputMakeup` 0.9→1.217 deficit. Added Developer ID signing +
  notarization to the macOS release job, and per-platform installers (`.pkg`/`.exe`/`.deb`) with
  an AU/VST3 choice screen on macOS. Same signing/installer pattern ported to
  `pedal-plugin-template/`.
- **v0.9:** 5 factory presets (Bluesy OD, Rhythm Crunch, Rock Lead, High Gain, Edge-of-Breakup)
  via the standard JUCE program API, stored as physical 0–10 dial positions.
- **v1.0:** Project cleanup pass — removed dead `schematics/` doc references, condensed the
  `.claude/rules/*.md`/`CLAUDE.md` investigation narration down to final values + brief
  rationale, and pruned the stale per-step build-log memories. First public release.
  - Keep condensing `.claude/rules/*.md`/`CLAUDE.md` as new work lands — strip "DONE" narration
    and investigation trails as they're superseded, but keep final values/constants verbatim.
- **v1.0.1:** Sign + notarize the macOS `.pkg` installer itself (separate "Developer ID Installer"
  cert via `productsign`, not just the AU/VST3 bundles inside it — see `release.yml`'s comments).
  Fixed the customize-screen choice outline showing a nameless parent folder above the AU/VST3
  options (`Distribution.xml`'s `<choices-outline>` had an unnecessary wrapping `<line>`).
  - The three `APPLE_INSTALLER_*` GitHub secrets are now configured (a Developer ID **Installer**
    cert, distinct from the Application cert already configured — see
    `pedal-plugin-template/.claude/rules/build.md`'s macOS signing section), so the release
    workflow's "Sign + notarize installer" step is live. No longer a blocker.
- **v1.1 — CPU/latency optimisation + low-OS fidelity pass (shipped).**
  - **DONE — measurement harness.** `tests/PerfBenchmark.cpp` (CPU % of realtime + latency per OS
    factor/clip mode → README Performance table) and `tests/FeatureProfile.cpp` (per-feature
    CPU-vs-accuracy, below). Both registered with ctest as finite-only probes (CI speed varies, so
    no absolute-CPU gate). To enable the feature A/B, the DSP stage classes were templated on the
    diode omega provider (defaulted, production-unchanged — see Current State note).
  - **DONE — feature CPU-vs-accuracy data** (from `FeatureProfile`, Apple Silicon, 48 kHz, single
    channel, clipping engaged). Classifies each performance-affecting feature:
    - **Omega solver — the ONLY real CPU/accuracy lever.** `omega4` is ~45% cheaper full-chain
      (4×: 3.0%→1.6% RT; 8×: 5.7%→3.0%) — the diode solve dominates DSP cost — but introduces a
      **−30 dB (1×) … −38…−44 dB (4×/8×) null error** vs `AccurateOmega`. Real, potentially
      audible on a transparent pedal → NOT a free swap; the sole legitimate "HQ" candidate.
    - **Rail-clip ADAA — STRAIGHT WIN, keep always on.** ~0% CPU (4×: 2.98%→2.99%) for a **+26 dB**
      aliasing reduction (4×: −47.9→−74.1 dB). No reason to ever gate it.
    - **Treble+Stage2 in the OS region — STRAIGHT WIN, keep always on.** Costs only **0.12%** at 4×
      but buys **+2.4 dB @12 kHz / +5.0 dB @16 kHz** top octave vs running them at base rate.
    - **Diode mismatch — free** (0.02% @4×); it's a faithfulness feature (even harmonics), not a
      quality/CPU tradeoff. Keep always on.
  - **DONE — HQ button.** Ships the `hq` `AudioParameterBool` (default ON = `AccurateOmega`; OFF =
    fast `omega4`, ~45% cheaper diode solve). Implemented as a RUNTIME switch
    (`AsymDiodePairT::setHighQuality` branches the omega call per sample — predictable, ~free), so no
    second DSP instantiation and no `PluginProcessor` templating; plumbed
    `PluginProcessor → TommyDSP → ClippingOversampler → Stage1 → AsymDiodePairT`. UI: a lit/dim "HQ"
    toggle (componentID `"ostoggle"`) in the bottom strip by UI SIZE, with a customer-facing hover
    tooltip. `FeatureProfile` has a regression guard asserting HQ-off is bit-identical to the omega4
    template chain (so the button can never silently become a no-op). The other three features stay
    always-on (free/near-free) — only the omega solver is gated.
  - **DONE — low-OS fidelity pass.** `tests/OSFidelity.cpp` measures FR + distortion at 1x/2x/4x vs
    8x (the common DAW case of running at low OS). Findings: the overdrive TONE (harmonic content) is
    faithful at every OS factor; what low OS costs is (a) aliasing (the OS-only fix — 1x ≈ −31..−37 dB,
    clean by 4x) and (b) top-octave FR droop (1x ≈ −4 @8k/−10 @12k/−21 @16k). Render default bumped
    4x→8x (`render_oversampling`, `PluginProcessor.cpp`) since offline CPU is free.
  - **DONE — top-octave restore** (`src/dsp/TopOctaveRestore.h`): a base-rate, OS-factor-scaled
    high-shelf that corrects the low-OS droop (pot-independent, so a fixed shape works). 1x now within
    ±1.2 dB through 12 kHz, 2x near-flat, 4x/8x bit-transparent. ~0 CPU, no latency. See dsp.md. So
    low OS now "sounds close", with high OS only refining (aliasing) — the stated goal.
  - **NOT YET DONE:** memory profiling; the optional fine-grained hot-spot profile (per-adaptor) —
    `FeatureProfile` already localised the dominant cost to the diode/omega solve, so a deeper
    per-adaptor breakdown is likely unnecessary unless a specific optimisation is pursued.
- **v1.2 — low-drive top-octave tilt fit (shipped).** `src/dsp/DriveTilt.h`: a base-rate,
  DRIVE-faded high-shelf (fc≈2.5k, full at low drive → 0 by ~G0.8) that corrects a low-drive
  top-octave roll-off (~2–3 dB across 2–8 kHz) the model had vs the real pedal. **pedal2 is the
  definitive tone reference** (user decision) — took pedal2 `knob_tracking` SHAPE 8/16 → 14/16; high
  drive is bit-unchanged (the shelf has faded out), so the validated high-drive match is preserved.
  A first attempt (a drive-SCALED-UP harmonic/EQ shelf to fix the *high*-drive deficit) was tried and
  reverted: the high-drive gap is a flat broadband LEVEL deficit (clip-output ceiling), not a tilt, so
  an HF shelf there broke SHAPE — see Known residuals. Two residuals deliberately left at the time:
  B0.65 bass (confounded, needs a targeted capture — still open) and the high-drive level ceiling
  (fixed in v1.2.1, below).
  > ⚠️ **The "SHAPE 8/16 → 14/16" figure here (and v1.2.1's "LEVEL 12/16 → 16/16" below) does not
  > reproduce** — both were measured without `SIGNAL=v2`, so `knob_tracking.py` read every segment
  > of the v2-layout `pedal2` captures at the wrong offset. The improvements were real; the counts
  > are not. Correct invocation: `SIGNAL=v2 … analysis/knob_tracking.py analysis/pedal2`. See the
  > v1.4 W2 entry.
- **v1.2.1 — high-drive quiet residual fix.** Root-caused and fixed the high-drive level ceiling
  left open above: `Stage1.h`'s 1N4148 `kIs` 2.52e-9 → 1.26e-9 (half the datasheet-typical value,
  justified by normal unit-to-unit Is spread). Closes pedal2's LEVEL check 12/16 → 16/16; harmonic
  content and the ClippingStage_Sine/full ctest suite unaffected. See Known residuals for the full
  derivation. B0.65 bass remains the one open residual.
- **v1.3.0 — trim lock + editable trim labels.** Widened `input_trim`/`output_trim` from ±12 dB to
  **±18 dB** (`PluginEditor::kTrimRange`, mirrored in each parameter's `NormalisableRange`). Added a
  `trim_lock` `AudioParameterBool` (default **true**) and a "LOCK" toggle in the oversampling strip
  (same lit/dim `"ostoggle"` styling as HQ): while on, moving either trim knob applies the
  equal-and-opposite **change** to the other (delta-linked — preserves whatever offset the pair
  already had, so enabling the lock never snaps a knob), implemented in `PluginEditor::mirrorTrim`
  with a re-entrancy guard against the two attachments' feedback loop. Also made both trim value
  labels **double-click editable** (`PluginEditor::commitTrimText`): typing a value applies it via
  the APVTS parameter (never `Slider::setValue`), so it drives the same attachment chain and
  respects the lock and host automation; non-numeric input is rejected rather than falling back to
  `String::getFloatValue()`'s silent 0.0. See `architecture.md`'s `trim_lock` row and `ui.md`'s
  Oversampling Strip / Side Panels sections for the full spec.
- **v1.4 — fidelity pass (IN PROGRESS). Plan: `.claude/plans/v1.4-fidelity.md`.**
  - **DONE — W5 harness fixes.** `report_audit.py` now floors the harmonic audit at **−45 dBc**
    (drops a point if *either* side is below it) and reports the excluded count: Soft's median
    |H-delta| falls 1.64 → 0.40 dB and Medium's 3.24 → 0.51 at −18 dBFS, because their H2/H4/H6
    "errors" were noise-floor comparisons (symmetric clippers have no even harmonics). Hard barely
    moves (0.95 → 0.90) — its asymmetry puts H2 genuinely above the floor. Added a **1 kHz-normalised
    FR view** (`fr_norm_audit`) beside the raw null-gain-matched one, which shows the ~0.9 dB
    "midband deficit" is a level-match artefact (worst 200 Hz–5 kHz band is 0.34 dB normalised).
    `dashboard_gen.py` gained matching raw/@1 kHz toggles on the FR + heatmap tabs, and flags THD
    bands with only one measurable harmonic order (6.4/8.1 kHz) with a "†" — derived from
    `meta.thd_band_orders`, not hardcoded.
  - **DONE — W1 Medium-mode clip threshold.** Root-caused and fixed; see the Medium entry under
    Calibration constants. Medium THD error **−0.17/−0.92/−1.86 → +0.16/−0.23/−0.60 dB** at
    −18/−12/−6 dBFS, and H3/H5/H7 at −6 dBFS **−1.97/−1.79/−1.61 → −0.64/−0.36/−0.29**. Soft and
    Hard renders are bit-identical (verified against the pre-change JSON: 0.00e+00 max ΔTHD).
    `knob_tracking.py` on pedal2 improved (SHAPE 12/16 → 13/16, LEVEL 8/16 → 10/16 on identical
    invocations); ctest 10/10; `auval` passes. **No test was relaxed** — Medium clamps higher than
    before (1.194 V vs Soft's 0.987) but still clears `ClippingStage_Sine`'s −6 dB compression
    bound at 47.8%; at the rejected 1.5× it would not have (51%), which is a second independent
    reason that multiplier is capped.
    **The multiplier is capped by the op-amp rails, not by the THD fit.** 1.5·kN fitted THD almost
    perfectly (+0.23/−0.00/−0.05) but pushed Stage 1 into the ASYMMETRIC rails before the diodes
    clamped, manufacturing even harmonics a symmetric mode should not have (Medium H2 error at
    −6 dBFS: +10.5 dB at 1.5×, +3.5 dB at 1.35×, −2.8 dB at v1.3.0). 1.35× is the trade; −6 dBFS
    THD lands just outside the ±0.5 dB gate as a result. A related bug found by the `dsp-validator`
    pass and fixed: `kSymMismatch` is a *fractional* Vt spread, so raising Medium's `vtBase` silently
    scaled its absolute diode mismatch too — `Stage1T::mediumMismatch()` now rescales by `kN/medN` to
    hold the absolute Vf spread equal to Soft's.
    **The "captures were made at 12 V" theory was tested and NOT supported** — see `circuit.md`'s
    rail note. Revisit `kNMedium` (1.5× was the better THD fit) only if the rails are ever measured
    and turn out wider than +2.5/−3.4 V.
    Two harness additions support this: `offline_render.cpp` modeIdx **3 = Linear** (used to refute
    the "SW1 mid is an open circuit" hypothesis) and argv[21]/[22] Medium diode overrides, plus
    `Stage1T::setMediumDiodeParams` (calibration-only; Soft is deliberately unreachable from it).
  - **DONE — W3 characterisation (no DSP change).** Added `analysis/w3_topoctave.py` (four probes:
    `confound`/`compression`/`metric`/`energy`) and an ADAA-disable override to `offline_render.cpp`
    (argv[23], measurement-only; default ON so shipped renders are bit-identical). Four results, two
    of which change what the fix must be — full numbers in the plan's W3 block:
    (a) the "onset at DRIVE ≥ 0.65" is genuinely DRIVE, but §1.3 was **confounded** — pedal2 steps
    TREBLE 0.20→0.35 and BASS 0.50→0.65 at the same point; `Medium D0.65 T0.20` breaks the tie and
    carries the full tilt, and BASS is excluded analytically (C3 shorts node_X at HF).
    (b) it is ~0.5 dB **linear** (present on the clean sweep) + ~2.0 dB **clipping-mediated** at
    10.2 kHz, so **a `DriveTilt`-style shelf cannot fix it** — being level-independent, one fitted at
    −6 dBFS would over-brighten the same setting by ~2 dB played clean. This is a second and stronger
    reason than v1.2's, and it supersedes the plan's "shelf is the fallback".
    (c) the Farina metric is **sound** here — fixed tones reproduce the plugin's swept-sine
    compression to within 0.02 dB, so §2.5's near-the-ceiling caveat doesn't discredit §1.3.
    (d) the deficit is **real energy** (total in-band, no deconvolution): Hard D1.00 is −1.87 dB at
    7–11 kHz and −2.51 at 11–16 kHz vs the pedal at −6 dBFS, low drive clean at every level. §1.3 and
    §2.5 are therefore ONE phenomenon: the model makes too little top-octave energy when driven hard.
    **Rail-clip ADAA is ELIMINATED as the cause** (off recovers only 0.04–0.09 dB, and identically at
    clean and −6 dBFS, so it can't be the level-dependent half). The leading remaining candidate is
    the **ideal op-amp model** — but see the next entry: it was tested and eliminated.
  - **DONE — W3 finite-op-amp-GBW experiment: TESTED AND ELIMINATED (no DSP change shipped).**
    Implemented finite GBW on Stage 1 (per-sample one-pole at f_p = GBW/A_cl, A_cl from the previous
    sample's solved gain so the clipping-driven loop-gain collapse was picked up), swept
    8/4/3/2/1 MHz, then **reverted** — the DSP is untouched and `ctest` is 10/10. It cannot work:
    the driven case did not move at all (−1.87 → −1.89 dB at 7–11 kHz) while the clean case got
    monotonically worse (−0.66 → −0.96 at 3 MHz). Reason: under clipping the output is clamped while
    the input keeps rising, so A_cl collapses to ≈2.5 and f_p ≈ 1.2 MHz — the filter self-disables
    exactly when clipping engages. Slew limiting is out too, on the numbers (~0.09 V/µs required at
    1.5 V / 10 kHz, far inside any JRC4559 spec). **Generalise the lesson: the pedal *expands* its
    top octave under drive (+2.19 dB at 10.2 kHz vs the model's +0.44), and no linear filter can add
    energy — so no shelf, pole or EQ of any kind can fix the clip-mediated half.** What is left is
    unverifiable without hardware: diode charge-storage/reverse-recovery (the WDF diode model is
    quasi-static) or a capture-chain contribution with no bypass anchor to rule it out.
  - **W6 STRUCK — no further pedal captures are possible** (user, 2026-07-26). Batches 1/2/3/4/5 and
    `pedal2` (batch 6) are all there will ever be, so nothing may be deferred "pending captures"
    again, and hardware re-verification is no longer available for `circuit.md`'s open questions
    (Mode B's threshold, the op-amp rail estimates). W2/W4 must be fitted from `pedal2` or
    documented as residuals; the one de-confounding lever left is clip-mode dependence at matched
    (BASS, DRIVE), which pedal2 does provide at D0.50/B0.50 and D0.65/B0.65.
  - **DONE — W4 characterisation: the proposed lever is REFUTED (no DSP change).** Added
    `analysis/w4_bassdrive.py` (probes `spread`/`order`/`anchor`/`shelf`; pure analysis, no render
    or build needed). W4's plan was to fit the BASS↔DRIVE coupling using **clip-mode spread at
    matched (BASS, DRIVE)** — the one de-confounding lever left after W6 was struck. It does not
    work, and the reason matters for every LF number in the report:
    (a) The mode spread is on the **pedal** side, not the model's — plugin 0.08–0.14 dB vs pedal
    1.57 dB (clean), up to 4.8 dB. §1.2(a)'s "the model's bass boost grows faster than the pedal's"
    has the asymmetry backwards.
    (b) Only the LF half is a mechanism: the pedal's spread is a V pinned to 0.00 at the 1 kHz
    anchor, rising at both ends (2.12 dB @20 Hz, 2.47 dB @16 kHz). The 20 Hz ordering is
    `Medium < Hard < Soft` in **5/5** groups but the 16 kHz ordering matches in only 1/5, and the
    ends are uncorrelated (r = −0.30) — **the HF spread is capture noise, not a mechanism.**
    (c) **The cause is anchor compression.** `sweep_clean` is −30 dBFS (37.9 mV in) but Stage 1's
    midband gain is 25–44 dB here, so the **1 kHz normalisation anchor is past the diode clamp in
    12/16 captures** (+15.3 dB over clamp at D1.00; only `Hard D0.20` is clear, at −12.2 dB). The
    mode compressing the anchor least gets the deepest-*looking* shelf, and the predicted order
    (Soft both-polarity 0.987 V < Hard one-polarity < Medium both at 1.194 V) is exactly the
    measured 5/5 order. Corroborated from the other side: the analytic LINEAR shelf is ~−10 dB at
    20 Hz while the rendered plugin shows ~+0.6 dB — clipping flattens nearly the whole shelf.
    (d) **W4 is not fittable AS A PHYSICAL BASS/DRIVE COUPLING PARAMETER from `pedal2`** — the
    only anchor-safe capture (`Hard D0.20`) shows an LF excess of **+0.25 dB**, essentially none,
    and regressing excess on anchor overdrive is weak/non-monotone (r = +0.31, peaking at D0.65
    where BASS also steps). ~~Recommend documenting W4 as a residual rather than fitting it.~~
    **RETRACTED same session, per the user:** the LF excess is real in 15/16 captures and, unlike
    W3, only needs a filter to CUT — ordinary shelf territory, not the "no linear filter can add
    energy" wall that killed W3. **Do not treat W4 as a closed residual.** Full handover with the
    required-correction table (median plugin−pedal at 20/40/80/100.8 Hz across DRIVE, all four
    sweep levels) and concrete next steps is in `.claude/plans/v1.4-fidelity.md`'s W4 section under
    "HANDOVER (2026-07-26, mid-session)" — start there, not from scratch.
    **Recorded dead end (still valid — this part was NOT retracted):** treating the −30 dBFS sweep
    as linear makes the diodes' zero-bias resistance the only switch-dependent term; it predicts a
    0.07–0.68 dB spread that *matches the plugin's measured* 0.08–0.6 dB and appears to imply an
    extra series element in the SW1 mid leg (which W1 inferred independently!). It is wrong — the
    premise that the diodes are off is false. **Check the anchor before trusting any
    1 kHz-normalised LF number**, including the numbers in the plan's handover table (driven-sweep
    columns are safer than the clean-sweep column — see the handover's caveat).
    **This also qualifies W5's `@1 kHz` FR view:** 1 kHz is not anchor-safe at D ≥ 0.50, and at
    D ≥ 0.65 no band on the clean sweep is (20 Hz is +5.2 dB over clamp at D1.00).
  - **W4 empirical-shelf fit: TESTED AND REFUTED (no DSP change). This closes ONE LEVER, NOT W4 —
    W4 REMAINS OPEN; see "W4 — remaining untried levers" below.** The handover's plan (fit
    the LF excess as an empirical low shelf, since unlike W3 it only needs to CUT) was carried out
    via a new `correction()` probe in `analysis/w4_bassdrive.py` (probe 5). The direction was never
    the problem; two other things are. **(1) The excess is a genuine shape error** — it decays from
    +1.2…+1.5 dB at 20 Hz to ~0 by 100–127 Hz with 127 Hz–1 kHz flat within ±0.13 dB, so it is not
    the anchor artefact probe 4 raised (a compression *mismatch* would offset every band equally).
    **(2) But its mode-independent part is subsonic:** the best static 1st-order low shelf is
    −3.1 dB at DC with a **15 Hz corner** (fit rms 0.08 dB) ⇒ −1.38 dB @20 Hz but only **−0.23 dB
    @60 Hz** and −0.10 @100 Hz. Low E is 82 Hz — it's a rumble trim, not a bass correction.
    **(3) The three LF SHAPE failures pull in OPPOSITE directions** (`Hard B0.50 D0.20` is −1.60 dB
    **dark** at 120 Hz; `Hard/Medium B0.65 D0.65` are +2.02/+3.03 **hot** at 60 Hz — the probe
    reproduces each `shapeDev` to within 0.1 dB), so one static shelf deepens the dark one while
    barely moving the hot two: measured effect on the gate is **0 failures fixed, 0 newly broken**,
    SHAPE stays 13/16. **(4) The failures that matter are mode-ordered** — 2.24 dB spread across the
    switch at identical (BASS, DRIVE), ordering Soft +0.79 < Hard +2.02 < Medium +3.03 exactly as
    probe 4's anchor-compression prediction. Soft *passes* where Medium fails by 3 dB; no
    bass-network error can do that. **So the dominant term is clip threshold/onset accuracy, not
    EQ. Do not ship a STATIC low shelf** — but that is a verdict on the static-shelf lever only, not
    on W4 as a work item (see the untried-levers list below).
    Two side findings: the plan's handover table had **every sign inverted** relative to its own
    caption (following it literally builds a shelf that BOOSTS LF, doubling the error) — flagged in
    the plan and superseded by the probe, which states one explicit convention; and a W5-class
    harness caveat, that `knob_tracking.py`'s SHAPE reads **`sweep_clean` only** with 60 Hz as its
    lowest band, so at D ≥ 0.50 its normalisation anchor is itself past the diode clamp. The same
    two settings on the **driven** sweeps collapse well inside tolerance and keep shrinking with
    level (`Medium B0.65 D0.65` @60 Hz: +3.03 clean → +1.06/−18 → +0.69/−12 → +0.50/−6;
    `Hard B0.65 D0.65`: +2.02 → +0.52 → +0.26 → +0.01), so the two "bass" failures are substantially
    an artefact of scoring SHAPE on the clean sweep. Worth fixing before treating them as tone bugs.
    - **DONE — W2 low-drive clip onset. The lever was the DRIVE TAPER, not the diodes.**
    `TaperUtils.h` `driveResistance` **`x^2.2` → `x^2.75`**, with `DriveTilt::kMaxGainDB`
    **2.5 → 1.0 dB** re-fitted jointly (it is fitted against the same low-drive captures, so the
    taper change invalidated it by construction). New probe `analysis/w2_clip_onset.py` (4 probes);
    calibration-only plumbing `DriveTilt::setMaxGainDB` → `TommyDSP::setDriveTiltGainDB` →
    `offline_render.cpp` argv[24]. **Results:** `Hard D0.20` median 100 Hz–2 kHz THD error
    **+11.61/+3.67/+1.26 → +0.40/−0.03/−0.70 dB** at −18/−12/−6; over all 16 captures × 3 depths
    **rms 1.88 → 0.52 dB, worst 11.61 → 1.14**. `knob_tracking` (SIGNAL=v2, pedal2)
    **THD 15/16 → 16/16** (G0.20 was the set's only THD failure), **LEVEL 14/16 → 15/16**,
    SHAPE 13/16 → 12/16. ctest 10/10, `auval` passes. x=1 is unchanged at 1 MΩ so full drive is
    bit-identical.
    **Why the taper:** the error is mode-INDEPENDENT in trend (at −18 dBFS, D0.35 = Soft +1.0 /
    Hard +1.4 / Medium +2.8 dB, ordering by each mode's overdrive *margin*, not its diode
    parameters), and the closed-form onset table shows the whole dataset sits **8–40 dB past clip
    onset except `Hard D0.20`/−18 at +5.4 dB** — pre-clip gain is observable at exactly one capture
    and nowhere else, which is why the old mid-drive fit missed it and why the correction costs
    nothing at D ≥ 0.35 (that region's THD rms actually *improves*, 0.71 → 0.45).
    **`kAsymMismatch` is REFUTED as the lever** — it moves H2 and almost nothing else (dTHD at
    D ≥ 0.35 is 0.57–0.62 dB rms for every value 0…0.45, dLEVEL invariant); m=0 halves the D0.20
    error but destroys the even-harmonic match that holds at every other drive. Do not re-try it.
    **Recorded side finding (not acted on):** `kAsymMismatch` being a *fractional* Vt spread
    symmetric about vtBase puts Hard's low-side clamp at 0.231 V — **below Soft's 0.365 V**, so the
    model's "hardest" mode starts clipping earliest, inverting the ordering the switch is named for.
    **Cost, stated plainly:** SHAPE 13/16 → 12/16. It fixed `Hard D0.20` and improved both standing
    D0.65 LF failures, but pushed `Soft`/`Medium D0.35` past the gate at 127 Hz — **on the clean
    sweep only**; on every driven sweep those same captures improve (mean rms 1 kHz-normalised FR
    deviation: clean 0.460 → 0.546 worse, but −18 0.309 → 0.223, −12 0.330 → 0.209, −6
    0.345 → 0.263). That is SHAPE's known weakness (it reads `sweep_clean` only, whose 1 kHz anchor
    is past the diode clamp at D ≥ 0.50 — see W4). **User decision: ship 2.75**; the conservative
    2.6 alternative regressed no gate but left the plugin at ~1.8× the pedal's distortion at
    D0.20/−18.
    **Harness fact that cost time — `knob_tracking.py` needs `SIGNAL=v2` for `pedal2`.** It defaults
    to the v1 segment layout and the v1/v2 segment *times* differ, so a bare invocation reads every
    segment at the wrong offset. This is why v1.2.1's "LEVEL 16/16" and W1's "LEVEL 8/16 → 10/16"
    disagree — **both are wrong**; the correct pre-W2 baseline is SHAPE 13/16 · LEVEL 14/16 ·
    THD 15/16. `analysis/pedal1` is also not a usable cross-check (0/8 on every gate at baseline).
  - **STILL OPEN — W3 only, and it is the "likely unfixable" one.** Every other v1.4 item is
    resolved: W1/W2/W4 fixed and shipped, W5 done, W6 struck, **W7 closed 2026-07-27** (fully
    characterised, its one candidate lever `kSymMismatch` refuted — it merges into W3 and is not
    tracked separately). W3 now carries the whole remaining residual: the pedal *expands* its top
    octave under drive and no linear filter, pole, shelf or flat parameter can add that energy back
    (finite-GBW and `kSymMismatch` both tested and eliminated). **W4 is DONE and shipped**
    (2026-07-27, `src/dsp/BassTilt.h`, SHAPE 12/16 → 16/16). Levers 1, 3, 5 and the static-shelf
    lever stay refuted; lever 2's refutation was **wrong and is retracted** — a *knob-keyed* shelf
    was the fix all along.
  - **DONE — W4 levers 4 + 5 resolved, levers 1 + 2 REFUTED (2026-07-27, no DSP change).** New
    probes `analysis/w4_bassdrive.py --only metric,decompose` (6 `metric`, 7 `decompose`); pure
    analysis, no render or build. Also fixed a stale `drive_resistance` in that file (`x^2.2` →
    `x^2.75`; W2 changed the shipped taper and left the probe behind, which **overstated** probe 4's
    anchor overdrive by ~1 dB).
    - **Lever 5 (bass network) — CLEAN, no bug.** `Stage1.h:534-540` composes
      `Zg = R3 + (C3 ‖ (BASS_R + C4))`, matching `circuit.md`'s authoritative BASS-network paragraph
      and `Stage1.h:142`. R3 3k3 / C3 39n / C4 1µ / R7 3k3 / C1 100p all correct; direction correct
      (x=0 ⇒ R=0 ⇒ max LF gain ⇒ no cut); DC limit gain→1 holds. **Side finding: `circuit.md` is
      internally inconsistent in three places** — its "node_C shunt elements" and "BASS pot detail"
      paragraphs put C3/C4 at node_C, contradicting the authoritative BASS-network paragraph the DSP
      follows. Worth correcting in `circuit.md`.
    - **Lever 4 (SHAPE metric) — DONE, and it substantially dissolves W4.** Verified end-to-end on
      the real renderer with `SIGNAL=v2 SHAPE_LEVELS=1 analysis/knob_tracking.py analysis/pedal2`
      (new opt-in breakdown; the gate itself is unchanged):

      | SHAPE scored on | pass | median | worst |
      |---|---|---|---|
      | `sweep_clean` (the shipped gate) | 12/16 | 1.12 | 2.69 |
      | `sweep_drv_-18` | **16/16** | 0.52 | 1.31 |
      | `sweep_drv_-12` | **16/16** | 0.69 | 1.45 |
      | `sweep_drv_-6` | 13/16 | 1.33 | 1.81 |
      | worst-of-all-four | 10/16 | — | — |

      **(a) NO capture fails at every level** — `sweep_drv_-18` is 16/16, so every failure in the
      set is level-specific. Clean-only inflation is **+0.47 dB median, +1.64 max** (probe 6).
      **(b) The gate's worst band migrates from bass to top octave with level** — the clean-sweep
      failures are at 64/127 Hz, the −6 dBFS ones at **8128 Hz**, i.e. **W3/W7, not W4**.
      **(c) "Driven sweeps are anchor-safe" is FALSE** (they are 12–24 dB hotter, so up to +30 dB
      over clamp); what makes them a better reference is that both sides compress in step.
      **HARNESS CAVEAT (W5-class) — probe 6's counts are NOT the gate's.** Probe 6 scores
      1/3-octave band energies from `comprehensive_data.json`; `knob_tracking` scores point gains
      from a csd transfer on a live render. They agree exactly on `sweep_clean` and `drv_-18` but
      diverge on the hot sweeps (probe 6 reads `-12` 14/16 and `-6` 8/16, vs 16/16 and 13/16), because
      the top-octave band is steep there and a 1/3-octave integral reads a larger deviation than a
      point estimate. **Use `knob_tracking` for counts, probe 6 for the per-capture level trend** —
      the W4 conclusions rest on the trend, which both agree about.
    - **⚠️ RETRACTED — levers 1 and 2 were NOT validly refuted. Both arguments below are WRONG;
      they are kept only so they are not re-made.** See "Lever 2 REOPENED" immediately after.
      - ~~Lever 1: the mode-independent part collapses 85–98% with level, so it is not a linear
        taper error — a linear filter cannot know how loud the signal is.~~ **WRONG: clipping
        MASKS a linear error at high level**, because both plugin and pedal pin to the clip
        ceiling and pre-clip gain differences stop showing. Level-collapse is exactly what a
        masked linear LF error looks like. (Probe 7's own docstring states this caveat; the
        conclusion contradicted it.) The clean sweep is the *least*-clipped and therefore the
        *most* revealing measurement, and there the mode-independent part is large and
        knob-ordered: B0.50 −1.24/−1.57 dB (dark), B0.65 +1.63/+0.98 (hot).
      - ~~Lever 2: any shelf is mode-independent by construction, so it can only address the
        smaller half of the error.~~ **WRONG: SW1 position is a knob the plugin knows.** A shelf
        keyed on (BASS, DRIVE, mode) is mode-dependent by construction.
      - Also over-weighted: the BASS/DRIVE confound blocks fitting a *physical taper*, but an
        empirical shelf keyed on **both** knobs never needs to know which one is responsible.
    - **✅ Lever 2 REOPENED and MEASURED — a knob-keyed shelf WORKS (probe 8 `knobshelf`).** Fits
      one static low shelf per exact (BASS, DRIVE, mode) setting, minimax over all four sweep
      levels — an **oracle bound** no achievable filter can beat. Scored on the LF bands
      (60/120/250 Hz, i.e. what W4 is actually about):
      **worst LF deviation median 1.00 → 0.46 dB, max 2.61 → 1.14 dB, and settings over the
      1.5 dB gate 4 → 0.** It clears every bass failure.
      **Why the all-band number looks bad and must not be quoted:** scored over all SHAPE bands the
      same shelf only moves 5/16 → 8/16, because most settings' worst band is **8128 Hz** — W3's
      top-octave deficit, which no low shelf can reach. The all-band minimax is dominated by W3 and
      **understates what an LF correction does to the bass.**
      **Form factor is simple and shippable:** a **fixed 250 Hz corner** with gain as the only
      knob-keyed term costs almost nothing vs the free-corner oracle (median residual 0.48, max
      1.19, 0 settings over gate) — the scattered per-setting corners were fit noise. Same shape as
      the already-shipped `DriveTilt`/`TopOctaveRestore`.
      **Correction gain table (fc = 250 Hz; sign is the correction TO APPLY, i.e. the negative of
      the measured plugin−pedal deviation — the plan's old handover table inverted exactly this):**

      | BASS | DRIVE | Soft | Medium | Hard |
      |---|---|---|---|---|
      | 0.50 | 0.20 | — | — | +0.5 |
      | 0.50 | 0.35 | +1.1 | +0.9 | +0.5 |
      | 0.50 | 0.50 | +0.2 | +0.2 | +0.1 |
      | 0.65 | 0.65 | −0.2 | −1.7 | −0.9 |
      | 0.65 | 0.80 | −0.1 | −0.7 | −0.6 |
      | 0.65 | 1.00 | −0.2 | −0.7 | −0.6 |

      **Irreducible residual ~0.42 dB median (max 1.04):** the ideal shelf differs per LEVEL and a
      static one can only sit in the middle of each row. Removing that needs an envelope follower;
      the plugin has no level detector (`DriveTilt` keys off the DRIVE *pot*).
      **The real risk is extrapolation, not the fit.** pedal2's 5 (BASS, DRIVE) points are
      perfectly confounded (B steps 0.50→0.65 exactly when D steps 0.50→0.65), so the table is 5
      points on a **diagonal** through a 2-D knob space; off-diagonal settings (high BASS + low
      DRIVE) are unconstrained and W6 means they can never be constrained. **Mitigation worth
      noting:** the table is near-monotone in DRIVE alone (boost below ~D0.5, cut above, zero
      crossing ~D0.55) across **six** DRIVE values spanning the full range, so keying it on DRIVE
      like `DriveTilt` is a 1-D fit with full coverage rather than a 2-D extrapolation.
    - **Lever 3 (per-mode / `kNMedium`) — REFUTED, which CLOSES W4.** Probe
      `analysis/w4_knmedium.py` (new, render-based: 5 Medium captures × 4 multipliers; its shipped
      column reproduces probe 7's JSON values to within **0.03 dB**). Setup: at 64 Hz Soft is
      essentially exact (+0.58 clean → −0.11 at −6) and Hard nearly so (+1.68 → +0.03), but
      **Medium plateaus at +0.5…+0.7** (+2.61 → +1.03 → +0.70 → +0.53) — mode-specific and
      level-persistent, i.e. a clip-threshold signature.
      **Result: the direction is right, there is NO LF-vs-THD trade — both prefer a HIGHER
      threshold** (mean |LF dev| 0.535/0.503/**0.473 shipped**/0.461 dB and mean |THD dev|
      1.19/0.99/**0.85**/0.79 % at ×1.10/1.20/1.35/1.50) — **but the sensitivity is nil.** The whole
      ×1.10…×1.50 range moves the LF metric by **0.074 dB**; shipped→×1.50 by **0.012 dB**. At the
      worst point (D0.65, 64 Hz, clean) ×1.50 buys 0.28 dB and still misses the gate by ~0.8 dB,
      while that capture already passed on every driven sweep. The cap remains the op-amp rails
      (Medium H2 **+3.48 → +10.45 dB** at ×1.5). **Keep ×1.35 — do not spend the rail artefact to
      buy 0.01 dB.**
      *Left undone deliberately:* a **per-mode AND level-faded** LF shelf is not reached by lever
      2's argument, but it has no circuit basis and would need an **envelope follower** (the plugin
      has no level detector — `DriveTilt` fades on the DRIVE *pot*, not signal level) to chase
      ≤0.5–1.0 dB. Ask before building it.
    - **Stale pre-W2 figures superseded:** probe 4's anchor count is now **5/16 anchor-safe** (was
      4/16) and `Hard D0.20`'s 20 Hz excess is **+1.13 dB** (was +0.25), so probe 4's "the only
      anchor-safe capture shows essentially no excess" no longer holds. Mechanism conclusion
      unchanged (margins are still 8–40 dB).
  - **DONE — W7 characterisation: real but ~1–2.4 dB, clip-mediated, MERGES INTO W3 (no DSP
    change).** New probe `analysis/w7_hf_thd.py` (`bands`/`tone`/`energy`/`products`), run against a
    **regenerated** `comprehensive_data.json` (the old one predated W2's taper change, so §2.5's
    plugin figures were measured on superseded DSP — regenerate before quoting that section).
    (a) **The "10–20× shortfall" headline is dead.** It reproduces (12.0×/17.3× at 6450.8/8127.5 Hz,
    `sweep_drv_-6`) but jumps discontinuously exactly where `thd_band_orders` drops 3 → 2: at
    4063.7/5120.0 Hz the plugin is **1.2×** light, at the two order-2 bands 12–17×. Those bands
    measure **H2 alone**, not THD. Don't quote the ratio again.
    (b) **The deficit is real, not measurement noise** — §2.5's stated worry is refuted directly.
    The v2 signal carries **fixed 4 kHz/8 kHz tone segments**, so harmonics read out with a plain
    windowed DFT (no Farina, no order ceiling), and every one sits **80–126 dB** above its local
    neighbour-bin level in all 16 captures.
    (c) **True size ~1–2.4 dB.** Total in-band energy at 6.3–8 kHz: **−0.62/−0.60/−0.77/−1.02 dB**
    (clean/−18/−12/−6) — milder than 8–10k (−0.73…−1.64) or 10–13k (−1.01…−1.80). Distortion
    products actually landing in the band (harmonics of the fixed 1/2/4 kHz tones — what a guitar
    puts up here, having no fundamentals there): median **−1.18/−1.00/−1.50/−2.42 dB**.
    (d) **Clip-mediated ⇒ inherits W3's wall.** By DRIVE, the deficit is ≈0 at the anchor-safe
    drives (D0.35 clean **+0.24**, D0.20 −0.67) and grows with both drive and level to −1.3 dB at
    D0.80–1.00/−6. Not present unclipped, so **no linear filter can fix it** — W7 merges into W3
    rather than being tracked separately.
    (e) ~~**New side finding, separate from W3 and possibly actionable:** Soft/Medium's
    **even**-order HF products are 7–15 dB light at high drive while Hard's are within ±3 dB — that
    is the `kSymMismatch = 0.06` term, a targeted lever.~~ **REFUTED — see the W7 closure entry
    below. `kSymMismatch` is frequency-flat and the error is a sign-reversing frequency ramp; do
    not touch it.**
    (f) **`analysis/pedal2` has an extremely clean floor** — 18–23 kHz energy is **−160 dBFS**
    during a −29 dBFS segment and the file head is 57% exact zeros, i.e. no measurable
    recording-chain noise. **This is expected of a NAM capture, not a sign of inaccuracy** — NAM
    reamps of this pedal null to ≈−45 dB against the real hardware, well inside what any conclusion
    here depends on. Consequence: noise floor is never the limit in a pedal2 measurement, and
    W3/W7's "the pedal expands its top octave under drive" should be read as a genuine property of
    the real pedal that the capture faithfully preserved, not a modelling artefact to be discounted.
  - **DONE — W7 CLOSED: `kSymMismatch` REFUTED as the even-order HF lever (2026-07-27, no DSP
    change).** This was W7's last open item — the "possibly actionable" side finding in (e) above.
    New probes `analysis/w7_hf_thd.py --only profile,sym` (5 = H2 error vs frequency at the shipped
    value; 6 = a 10 Soft/Medium captures × 5 values render sweep via `offline_render` argv[20]).
    **`kSymMismatch` stays at 0.06.**
    **(a) The even-harmonic error is a frequency RAMP that reverses sign, not an offset.** Median
    plugin−pedal H2 over the 10 Soft/Medium captures, by tone (every row 49–97 dB above its own
    local floor): 82 Hz **+7.8**, 110 +9.4, 220 **+12.3**, 440 +5.8, 1k +1.6, 2k −1.5, 4k **−10.2**
    (H2 at 8 kHz). The plugin is 6–12 dB **hot** on even harmonics across the whole audible
    midrange and light only at the very top — (e)'s "7–15 dB light" is one end of a **21 dB spread**.
    **(b) The parameter is exactly frequency-FLAT, so it slides that ramp but cannot tilt it.**
    0.06 → 0.12 adds **+6.0…+6.1 dB at all seven frequencies**. So the shipped 0.06 already
    minimises the audible midrange (mean |err| 82 Hz–1 kHz **8.09** dB, rising monotonically to
    25.60 at 0.45), and the only value that helps the top (0.12: mean |err| 2k–4k 4.73 → 3.37)
    **buys 1.4 dB at HF by spending 6 dB at LF.**
    **(c) That trade is inaudible regardless:** the 0.12 render nulls against the shipped render at
    **−47.2 dB**, i.e. the entire change is quieter than the plugin's own ≈−45 dB residual vs the
    capture. **(d) Collateral nil, as W2 said** — over 0.06…0.45 the 1 kHz H3 error moves 0.15 dB
    and THD 0.22 %. Hard needs no regression check (`kSymMismatch` is Soft/Medium-only; argv[20]
    cannot reach `kAsymMismatch`).
    **(e) Where it IS audible it is W3's wall:** the one even product at/above the −45 dBc floor is
    4 kHz H2 at 8 kHz (pedal −44.6 dBc, **6/10** captures above the floor) — exactly the top octave
    W3 showed the pedal *expands* under drive. Every other H2 row is −51…−57 dBc with 0–1/10 above
    the floor. **W7 therefore has no independently fixable component and merges into W3 in full.**
    **Harness bug fixed on the way (W5-class):** `_noise_db_at`'s default ±200 Hz window reaches the
    FUNDAMENTAL for harmonics below ~500 Hz, so H2 of the 82/110 Hz tones first reported margins of
    −29 dB ("in the floor") when they are really 59–64 dB clear. `_h2_row` narrows it to `0.4·f0`;
    any future probe reading a low-frequency harmonic must do the same.
  Findings re-derived from `analysis/reports/comprehensive_data.json` (16 pedal2 captures, 30
  1/3-octave bands, 4 sweep levels). Four real errors, one artefact, two harness fixes:
  - **Medium-mode clip threshold (W1) — FIXED, see above.** Medium was the only clip mode with a
    level-dependent THD error (−0.2/−1.0/−1.9 dB at −18/−12/−6 dBFS; H3/H5/H7 all ~−1.8 dB at −6).
    **Soft is exact at every level and drive** — which pins the shared diode parameters and makes
    Medium separable for the first time. Related: the modelled Soft↔Medium threshold gap
    (`2·kIs` vs `kIs` ⇒ only ~31 mV) was far smaller than the pedal's. The `schematic-checker` pass
    found the DSP implemented `circuit.md` exactly and correctly — so the gap is in `circuit.md`'s
    Mode B description itself, which cannot be re-verified (schematic images were removed from the
    repo). Fixed by an empirical per-mode fit; the "SW1 mid is an open circuit" reading of the
    on/off/on wording + "Open" label was tested and **refuted** (+6.1 dB THD error).
  - **Low-drive clip onset (W2) — FIXED (2026-07-27), see the W2 entry above.** Was: at D0.20/−18
    dBFS the plugin distorted ~4.4× the pedal (11.3% vs 2.55% @101 Hz), collapsing as level rises;
    the largest single error in the dataset. The diagnosis recorded here at the time — that it was a
    diode/`kIs` tension — was **wrong**; it was the DRIVE taper (pre-clip gain law). The warning not
    to chase it with global `kIs` still stands and is now moot.
  - **High-drive top-octave tilt (W3).** −2…−3 dB at 8–10 kHz, onset sharply at DRIVE ≥ 0.65,
    clip-mode independent. v1.2 reverted an HF-shelf attempt because the high-drive gap "is a flat
    LEVEL deficit, not a tilt" — **that premise died with v1.2.1's `kIs` fix** (LEVEL now 16/16);
    what remains is a genuine tilt. **Superseded by the W3 characterisation above** — it is half
    linear / half clip-mediated, and NO linear filter (shelf, pole or EQ) can fix the latter half.
  - **BASS↔DRIVE coupling (W4) — FIXED AND SHIPPED (2026-07-27): `src/dsp/BassTilt.h`.**
    A DRIVE- and clip-mode-keyed **250 Hz low shelf** (gain interpolated from a fitted per-mode
    table over six DRIVE positions; boost below ~D0.55, cut above). Wired
    `PluginProcessor → TommyDSP` at base rate after `DriveTilt`; calibration override
    `TommyDSP::setBassTiltScale` → `offline_render.cpp` argv[25] (0.0 = bit-transparent, reproduces
    pre-W4 renders).
    **Results (`SIGNAL=v2 SHAPE_LEVELS=1 knob_tracking.py analysis/pedal2`): SHAPE 12/16 → 16/16**
    — all four bass failures cleared, and **no capture regressed** (worst movement +0.02 dB, noise;
    biggest wins `G0.65 mid` 2.69 → 1.09, `G0.35 down` 1.99 → 1.19, `G1.00 mid` 1.12 → 0.45).
    LEVEL unchanged at 15/16 (the one failure, `G0.50 mid` +2.13 → +2.14, is pre-existing and
    untouched); THD 16/16; **ctest 10/10; `auval` passes.** Scored per sweep: clean 12/16 → **16/16**,
    −18 16/16 → 16/16, −12 16/16 → 16/16, −6 13/16 → 13/16 (unchanged — those are **W3's top octave
    at 8128 Hz**, which no low shelf can reach); worst-of-all-levels 10/16 → 13/16.
    **Irreducible ~0.42 dB residual** (the ideal shelf differs per signal level; a static one sits
    in the middle — closing it needs an envelope follower the plugin does not have).
    Full derivation, gain table, and the retracted arguments are below and in `dsp.md`.
  - **W4 — the BASS TAPER LAW is also refuted; the shipped taper is the GRID OPTIMUM
    (2026-07-27).** The last pre-clip lever. Swept `BASS_R = coeff · x^exp` over
    coeff ∈ {30k, 40k, 50k} × exp ∈ {1.80, 2.41, 3.00, 3.50, 4.00, 4.70} with BassTilt disabled
    (`w4_basscaps.py --taper`; coeff is R at x=1 so >50k is not realisable on a 50k pot). **The
    shipped 50k·x^2.41 is the best point on the entire grid** (worst 2.58 dB); every other
    combination is worse, and raising the exponent — which the B0.50-dark/B0.65-hot pattern
    superficially suggests — degrades it monotonically (x^4.70 → 4.51 dB).
    Closed-form agrees: correcting both ends needs R(0.65)/R(0.50) ≈ 3.4 against the shipped 1.88,
    which for a power law implies coeff ≈ **183k on a 50k pot** — physically impossible. Only an
    S-shaped taper could supply that shape, and it would be a strong unverifiable claim about the
    pot, fitted BASS/DRIVE-confounded, with the batch-3/4/5 reference gone.
    **Coverage is now complete:** C3, C4 and the BASS_R law are the network's only LF-shape levers
    and all three say the bass network is already optimal. R3/R7 are not LF-shape levers (they set
    midband gain — Zg → R3 where the caps short). **The LF residual is therefore genuinely NOT a
    component error, which is what justifies the empirical `BassTilt` shelf.**
  - **W4 — component-based alternatives to the shelf: C3/C4 REFUTED (2026-07-27).** The shipped fix
    is an empirical output shelf, so the obvious objection is "shouldn't a wrong component explain
    this instead?" — especially since C3/C4 sit PRE-clip (so their effect is naturally
    level-dependent, which would remove BassTilt's irreducible ~0.42 dB) and lever 5 only verified
    the DSP matches `circuit.md`, never that `circuit.md` is right. Tested properly via new
    `Stage1T::setBassCaps` → `offline_render.cpp` argv[26]/[27] and
    `analysis/w4_basscaps.py` (16 captures × 35 (C3,C4) points = 560 renders, **BassTilt disabled**
    so it measures the raw model). Result — **the shipped values are essentially optimal**:
    - **C4 is nearly irrelevant** at 64–254 Hz: across 0.47µ…2.2µ (a 4.7× range) the worst LF
      deviation moves ~0.05 dB. It only dominates far lower (~20 Hz).
    - **C3 has a shallow minimum at 39–47n**, i.e. at/next to the shipped 39n.
    - Best grid point (46.8n / 2.2µ) gives worst **2.43 dB vs shipped 2.58** — a 0.15 dB gain, and
      the **mean gets worse** (1.06 → 1.15). Against BassTilt's 1.14 dB worst, the best component
      point is **more than 2× worse**. The LF error is not a C3/C4 value error.
    **Correction to `TaperUtils.h` found on the way:** its claim that "the 60 Hz cut is only weakly
    sensitive to [the BASS coefficient] — the deep-LF cut is dominated by C3/C4, not the pot R" is
    **wrong at 60 Hz and had been discouraging a real lever**. Measured (64 Hz re 1 kHz, analytic):
    ~**3–4 dB per doubling of BASS_R** (B0.50/D0.35: 4.7k → −2.73 dB, 9.4k → −5.66, 18.8k → −9.40).
    C3/C4 dominate only near 20 Hz. Comment corrected in place with the numbers.
    **Also established: batches 3/4/5 no longer exist** — not in the repo and not in git history
    (they were local-only). So "the BASS taper is validated against batches 3/4/5", cited throughout
    these docs as a reason not to touch it, is **no longer verifiable**, and `pedal1` is 0/8 at
    baseline. Any taper refit would be pedal2-only, BASS/DRIVE-confounded, and unable to measure its
    own regression risk.
  - **W4 design record — REOPENED 2026-07-27 after a wrong "closed" verdict.**
    A **knob-keyed 250 Hz low shelf** (gain keyed on DRIVE/mode, `DriveTilt` form factor) clears
    every bass failure: worst LF deviation **median 1.00 → 0.46 dB, max 2.61 → 1.14, settings over
    the gate 4 → 0**. Gain table, irreducible ~0.42 dB level residual, and the off-diagonal
    extrapolation risk are all in the W4 roadmap entries above; reproduce with
    `w4_bassdrive.py --only knobshelf`. **An earlier "CLOSED as not-fixable" verdict here was
    WRONG and is retracted** — it rested on two bad arguments (that level-collapse disproves a
    linear error, when clipping masks linear errors; and that a shelf is mode-independent, when
    SW1 position is a knob). What DOES still hold: the network itself is correct (lever 5), the
    BASS *taper* should not be refitted as a physical parameter (the confound is real), a *static
    mode-blind* shelf fails, `kNMedium` moves the LF metric only 0.074 dB across ×1.10…×1.50
    (lever 3), and much of the apparent 2–3 dB is a `sweep_clean` scoring artefact (lever 4).
    **Ignore the plan's handover table, whose signs are inverted — use probe 8's gain table.**
    **Update (2026-07-27, W2):** W2's DRIVE-taper fix moved this residual the right way — the two
    standing LF SHAPE failures improve monotonically with the exponent (`Hard D0.65` +2.00 → +1.66,
    `Medium D0.65` +3.00 → +2.58 dB at 60 Hz) — which is direct support for W4's "it's clip onset,
    not EQ" reading. They still fail, and the LF now **see-saws with DRIVE**: shy at D0.35
    (−1.6…−2.0 dB @127 Hz), hot at D0.65 (+1.7…+2.6 @60 Hz). One taper exponent cannot straddle
    that. ~~The next untested lever is the **BASS taper's shape between x = 0.50 and 0.65**.~~
    **SUPERSEDED (2026-07-27, later session) — the BASS-taper lever is REFUTED and so is the faded
    shelf; see the "W4 levers 4 + 5 resolved" entry above for the numbers.** The see-saw is a
    **clean-sweep artefact**: at −6 dBFS both settings are the same sign and size (+0.18, +0.15),
    and the mode-independent (taper-shaped) part of the error collapses 85–98% with level, which no
    linear filter can do. Only **lever 3 (per-mode / `kNMedium`)** remains live, narrowed to Medium,
    which alone plateaus at +0.5…+0.7 dB instead of decaying to zero.
  - **NOT a real error:** the apparent ~0.9 dB deficit across 40 Hz–2 kHz is an artefact of
    `null_depth`'s least-squares broadband gain being dragged down by the LF excess. Normalised at
    1 kHz, 200 Hz–5 kHz sits within ±0.35 dB at all four levels. Don't "fix" it.
  - **Harness (W5) — DONE, see above:** `report_audit.py`'s harmonic median needed an absolute floor
    (−45 dBc) — the +12…+25 dB H2/H4/H6 deltas it reports for Soft/Medium are noise-floor
    comparisons at −50…−62 dBc, and they dominate its per-mode score. Also add a 1 kHz-normalised
    FR view alongside the null-gain-matched one.
  - **Capture batch 7 (W6) — STRUCK, see above.** It would have unblocked W2/W4 (`CAPTURE_SPEC.md`'s
    bypass anchor + a BASS sweep at fixed DRIVE were never captured, nor a low-DRIVE × switch × level
    block), but no further captures are possible. The confounds are permanent; fit or document.
