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
threshold — see Roadmap).** All 9 build-sequence steps are complete. Full DSP chain
(`src/dsp/`: InputBuffer → Stage1+SW1 clipping, oversampled with ADAA on the rail clip and
`AccurateOmega` → TrebleNetwork → Stage2, wired via `TommyDSP.h`, then base-rate
`TopOctaveRestore` (corrects the low-OS top-octave droop) + `DriveTilt` (corrects a low-drive
top-octave tilt vs the real pedal) shelves) is validated; op-amp output
rails are modelled on both stages. `auval` passes; 9 test executables pass (two, `PerfBenchmark`
and `FeatureProfile`, are measurement probes rather than pass/fail accuracy — `PerfBenchmark` →
README's Performance table; `FeatureProfile` → the v1.1 roadmap's CPU-vs-accuracy data). UI
(Step 8) is a
fixed 480×480 three-column layout — full design in `ui.md`. Open modelling items: v1.4's W2/W3/W4
(W4 next; nothing is "blocked on captures" any more — W6 is struck, see Roadmap).

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
  BASS `50k·x^2.41` (convex — validated ±0.6 dB), DRIVE `1e6·x^2.2`,
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
  - **STILL OPEN — W2, W3 (fix; likely unfixable), W4 (fittable as an empirical shelf — plan has a
    full handover, next up).**
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
  - **Low-drive clip onset (W2).** At D0.20/−18 dBFS the plugin distorts ~4.4× the pedal (11.3% vs
    2.55% @101 Hz), collapsing as level rises. Edge-of-breakup region; largest single error in the
    dataset. Pulls opposite to v1.2.1's `kIs` halving — do NOT chase it with global `kIs`.
  - **High-drive top-octave tilt (W3).** −2…−3 dB at 8–10 kHz, onset sharply at DRIVE ≥ 0.65,
    clip-mode independent. v1.2 reverted an HF-shelf attempt because the high-drive gap "is a flat
    LEVEL deficit, not a tilt" — **that premise died with v1.2.1's `kIs` fix** (LEVEL now 16/16);
    what remains is a genuine tilt. **Superseded by the W3 characterisation above** — it is half
    linear / half clip-mediated, and NO linear filter (shelf, pole or EQ) can fix the latter half.
  - **BASS↔DRIVE coupling (W4).** LF excess below ~100 Hz (+2.8 dB @20 Hz clean) is real *as a
    measurement* and still needs fixing — **updated by the W4 characterisation above**: the mode
    dependence this was originally attributed to is anchor compression, not a bass mechanism (the
    clip-mode-spread lever is refuted, do not fit against it), but the underlying LF excess itself
    is not explained away by that and is fittable as an empirical DRIVE/level-dependent low shelf.
    See the plan's HANDOVER block for the required-correction numbers and next steps.
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
