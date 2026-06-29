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

**Status: SHIPPABLE, v1.2.** All 9 build-sequence steps are complete. Full DSP chain
(`src/dsp/`: InputBuffer → Stage1+SW1 clipping, oversampled with ADAA on the rail clip and
`AccurateOmega` → TrebleNetwork → Stage2, wired via `TommyDSP.h`, then base-rate
`TopOctaveRestore` (corrects the low-OS top-octave droop) + `DriveTilt` (corrects a low-drive
top-octave tilt vs the real pedal) shelves) is validated; op-amp output
rails are modelled on both stages. `auval` passes; 9 test executables pass (two, `PerfBenchmark`
and `FeatureProfile`, are measurement probes rather than pass/fail accuracy — `PerfBenchmark` →
README's Performance table; `FeatureProfile` → the v1.1 roadmap's CPU-vs-accuracy data). UI
(Step 8) is a
fixed 480×480 three-column layout — full design in `ui.md`. No open modelling items remain.

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
- Diode mismatch (`AsymDiodePairT`, all clip modes) models the even-harmonic content real
  diode tolerance adds: `kSymMismatch = 0.06` (Soft/Medium), `kAsymMismatch = 0.45` (Hard).
  Per-polarity Vt mismatch, not a DC bias — leaves small-signal gain unperturbed.
- Op-amp output rails: +2.5/−3.4 V at the 9 V default (no published bench measurement exists;
  estimated from datasheet swing at the pedal's light load). `supply_voltage` (9/12/18 V)
  scales both rails at +0.451/+0.549 V per supply volt (VREF divider ratio); diode thresholds
  are unaffected — it's a pure headroom change.

### Known residuals (not masked with extra makeup gain — documented limits, not bugs)

- High drive (G0.65+): ~3.5–4 dB quiet vs pedal2 — the clip-output scaling ceiling (the plugin
  compresses more at high drive). A distortion-DEPTH residual, not EQ: an HF/harmonic shelf does NOT
  fix it (tried in v1.2 dev — it broke the level-normalised SHAPE match; a flat broadband deficit,
  not a tilt). Fixing it would need drive-scaled makeup (masks the ceiling — avoided) or a clip-depth
  change. Left as-is.
- B0.65 SHAPE fails (2 of 16 pedal2 settings): the plugin's bass is ~+3 dB hot at BASS≈0.65. In the
  pedal2 captures B0.65 only appears with high drive, so it's confounded (bass taper vs BASS/DRIVE
  coupling) — needs a dedicated bass-sweep-at-fixed-drive capture to fix safely (the BASS taper is
  validated against batch 3/4/5, not in-repo). Deferred.
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
  an HF shelf there broke SHAPE — see Known residuals. Two residuals deliberately left: B0.65 bass
  (confounded, needs a targeted capture) and the high-drive level ceiling.
