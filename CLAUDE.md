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

**Status: SHIPPABLE, v1.0.** All 9 build-sequence steps are complete. Full DSP chain
(`src/dsp/`: InputBuffer → Stage1+SW1 clipping, oversampled with ADAA on the rail clip and
`AccurateOmega` → TrebleNetwork → Stage2, wired via `TommyDSP.h`) is validated; op-amp output
rails are modelled on both stages. `auval` passes; 8 test executables pass (one, `PerfBenchmark`,
is a CPU/latency measurement probe rather than pass/fail accuracy — see README's Performance
table). UI (Step 8) is a
fixed 480×480 three-column layout — full design in `ui.md`. No open modelling items remain.

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

- ~2 dB quiet at full drive — clip-output scaling ceiling.
- ±2 dB @ 12 kHz, +2 dB @ 8 kHz — HF-shape/measurement confound (driven captures carry clip
  harmonics in the top octave); the bilinear-warp part of this was fixed by oversampling
  Treble+Stage2 alongside the clipper (see `dsp.md` Oversampling section).
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
  - **TODO before this can actually run:** add the three `APPLE_INSTALLER_*` GitHub secrets (a
    Developer ID **Installer** cert, distinct from the Application cert already configured — see
    `pedal-plugin-template/.claude/rules/build.md`'s macOS signing section for how to obtain one).
    The release workflow's "Sign + notarize installer" step will fail until these are set.
- **v1.1 TODO — CPU/latency/memory optimisation pass.**
  - Profile the full DSP chain (Stage 1 R-type solve, SW1 Newton-Raphson, oversampling,
    Stage 2) to find the actual hot spots before optimising blind.
  - Add CPU-usage and latency measurement to the test suite (e.g. a timed render of N seconds
    of audio at a fixed block size/sample rate, reported as % of realtime, plus
    `getLatencySamples()` reported per oversampling factor) — wire the results into `ctest`
    output and summarise them in the README (a small "Performance" table: CPU % and latency
    per OS factor/clip mode).
  - While profiling, identify which currently-on features are "a few % CPU for a small
    accuracy/quality gain" candidates (e.g. diode-pair ADAA if added, the `AccurateOmega` solve
    vs. the cheaper default `omega4`, the linear-stage-inside-oversampling treble/Stage2 pass)
    that could be gated behind an optional "HQ" mode rather than always-on.
  - **Discuss with the user before adding an HQ toggle or removing/gating any existing accuracy
    feature** — this is a UX/CPU tradeoff decision, not a pure cleanup, and changes user-facing
    behaviour (`architecture.md`'s parameter table would need a new APVTS parameter).
