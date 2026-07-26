# Tommy analysis & validation harness

Offline A/B tools that compare the plugin's DSP against NAM captures of the real pedal. Everything
runs the **real** DSP via the `OfflineRender` executable (built from `offline_render.cpp`, which
mirrors `PluginProcessor`'s exact gain staging) plus a Python analysis layer — no separate model.

## Setup

```bash
# Build the offline renderer + tests (from repo root)
cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build --target OfflineRender

# Python deps (numpy, scipy; matplotlib optional for plots)
python3 -m venv analysis/.venv && analysis/.venv/bin/pip install numpy scipy matplotlib
```

Run every script **from the repo root** (paths are repo-root-relative).

## Test signal

`gen_test_signal.py` writes `tommy_test_signal_48k.wav` (48 kHz, ~37.8 s). The real-pedal captures
in `pedal_results{,2,3,4,5}/` were recorded by playing THIS signal through the pedal, so the segment
layout in `analyze.py` (`T{}`) must stay in lock-step with it. Segments: noise-floor silence, a
1 kHz cal tone, a 20 Hz→20 kHz log sweep at -30 dBFS (clean EQ) and again at -12 dBFS (driven),
1 kHz level steps (-24/-18/-12/-6 dBFS), and discrete tones (82–5000 Hz @ -14 dBFS).

> ⚠️ **Changing the test signal invalidates the existing captures.** Only ever *append* new
> segments at the end (and re-capture the pedal) — inserting in the middle shifts every later
> segment's offset and breaks alignment for batches 1–5.

## Capture batches

| Dir | What | Notes |
|-----|------|-------|
| `pedal_results`  | batch 1 — primary pedal | direct knob direction |
| `pedal_results2` | batch 2 — MXR Timmy | secondary ref, opposite knob direction |
| `pedal_results3` | batch 3 — primary, EQ fit | 0-10 knob notation; 2 of 6 files are truncated 8 s (auto-skipped) |
| `pedal_results4` | batch 4 — drive × switch matrix | clock HHMM notation; Volume fixed at noon |
| `pedal_results5` | batch 5 — HOT (+6 dB) reamp | use `KIN≈2.4`; Volume fixed at noon |

**No batch varies Volume** — there is no real-pedal reference for the Volume taper (see
`volume_supply_check.py`).

## Tools

| Script | Purpose |
|--------|---------|
| `analyze.py` | Core library: load/align, `transfer`, `thd`, `rms_db`, the shared `parse_filename` (auto-detects clock vs 0-10 notation + switch/sym keyword), `is_full_length` (truncated-capture guard), `fractional_octave_freqs`. Also a CLI: `analyze.py REAL=a.wav TOMMY=b.wav`. |
| `run_compare.py` | Per-capture EQ / output-level / THD vs real. `NAMDIR=…` picks the batch, `KIN=…` overrides input ref, **`FINE=1`** prints a 1/3-octave EQ table (~30 pts, 20 Hz–20 kHz) instead of 9 fixed points. |
| `swept_thd.py` | Continuous **THD(f)** via Farina exponential-sweep harmonic separation (no new captures). `--validate` cross-checks the curve against the discrete tones (run first); `--matrix <dir>` prints THD-by-band, real vs plugin, across a whole batch (extra columns through 1–4 kHz where the saturation lives). |
| `null_test.py` | Sub-sample-aligned (fractional-delay) **null test**. Level-matches then subtracts; reports residual dB (best/worst). `null_test.py <batchdir>`. |
| `knob_tracking.py` | Formalized **pass/fail**: at every captured setting, does the plugin match the real pedal? Separates SHAPE (tone-stack, level-normalized) from LEVEL (absolute) from THD, with explicit thresholds. `knob_tracking.py <dir> [<dir>…]`. **Set `SIGNAL=v2` when pointing it at `pedal2`** — it defaults to the v1 segment layout, and the v1/v2 segment *times* differ, so without it every segment is read from the wrong offset and the pass counts are meaningless. Two figures in this repo's history were recorded without it; the correct `SIGNAL=v2 … analysis/pedal2` baseline before v1.4 W2 was SHAPE 13/16, LEVEL 14/16, THD 15/16. Also note SHAPE reads **`sweep_clean` only** (−30 dBFS), whose 1 kHz normalisation anchor is past the diode clamp at D ≥ 0.50 — see W4/W2 in `.claude/plans/v1.4-fidelity.md` before treating a SHAPE failure as a tone bug. |
| `w2_clip_onset.py` / `w3_topoctave.py` / `w4_bassdrive.py` | The v1.4 fidelity-pass work-item probes; each reproduces one plan item's argument end to end and is the reproduction command quoted in `.claude/plans/v1.4-fidelity.md`. `w2` (low-drive clip onset) is the one that also *fits*: probe `onset` is a closed-form clip-onset margin table, `levers` renders candidate parameters across the captures each can move, and `fit` scores THD and 1 kHz-normalised FR jointly while reproducing knob_tracking's SHAPE/LEVEL gates exactly. `w3`/`w4` are characterisation-only — both ended in refutations, so read their plan OUTCOME blocks before re-opening either. |
| `volume_supply_check.py` | Self-consistency for the two controls with no real reference: Volume monotonicity + Supply (9/12/18 V) headroom ordering. |
| `harmonics.py` | Per-tone harmonic profile (H2…H7, even-vs-odd) vs a capture — clip-character detail. |
| `treble_fit.py` / `treble_xcheck.py` / `sweep_kinput.py` | Taper/level fitting helpers used when refitting a control against the captures. |
| `comprehensive_report.py` | Imported from the Guitar-Pedal-Plugin-Template analysis harness and adapted for Tommy. Renders every `pedal2` capture (the only batch with all three driven-sweep depths + full 8-tone THD anchor set — `pedal1` predates that spec) at matching settings, then writes per-1/3-octave-band FR, THD (Farina swept + discrete-tone crossover), and H2-H7 harmonic data to `analysis/reports/comprehensive_data.json`, grouped by SW1 clip mode. `captures.py` is the Tommy-specific capture-I/O/render-args glue this reads; `analyze.py`'s `harmonic_thd_curve`/`frac_align`/`null_depth`/`thd_max_measurable_hz` were added to support it. Parallelised across a process pool with a disk cache for the (plugin-independent) capture-side analysis — see the script's docstring. |
| `dashboard_gen.py` | Also imported from the template — in the interactive tabbed/Chart.js format of `reports/example_dashboard.html` (NoAmp's reference dashboard), not a static-SVG layout. Reads `comprehensive_data.json`, embeds it directly into a self-contained `analysis/reports/dashboard.html` (FR comparison + error, FR error heatmap, THD comparison, harmonic breakdown, per-clip-mode summary + quick-take issues), so it opens pre-loaded; the file-input control still works if you want to load a different JSON snapshot without regenerating. Needs network access once (loads Chart.js from a CDN, same as the reference). Clip-mode badges/dropdown are driven by whatever `rev` values are actually in the data (Hard/Medium/Soft for Tommy), not hardcoded. |
| `report_audit.py` | Also imported from the template. Audits `comprehensive_data.json` against FR/THD acceptance targets and writes `analysis/reports/executive_summary.txt` (`--write`): FR-vs-target grading per clip mode, THD data coverage (Farina ceiling vs discrete-tone bands), THD-vs-drive-level (clip-onset vs static fault), and per-harmonic (H2-H7) magnitude deltas. Tommy's circuit has no twin-T/bridged-T notch, so `CONFOUNDED_ANCHORS` is empty (unlike the template's default). |

## Typical workflow

```bash
# Fine frequency response vs the EQ batch
FINE=1 NAMDIR=analysis/pedal_results3 analysis/.venv/bin/python3 analysis/run_compare.py

# Validate then run the continuous-THD matrix across the drive/switch sweep
analysis/.venv/bin/python3 analysis/swept_thd.py --validate
analysis/.venv/bin/python3 analysis/swept_thd.py --matrix analysis/pedal_results4

# Null depth (headline number for the README)
analysis/.venv/bin/python3 analysis/null_test.py analysis/pedal_results3

# Overall pass/fail across the operating space
analysis/.venv/bin/python3 analysis/knob_tracking.py analysis/pedal_results3 analysis/pedal_results4

# Hot batch uses a higher input reference
KIN=2.4 analysis/.venv/bin/python3 analysis/knob_tracking.py analysis/pedal_results5

# Comprehensive per-band FR/THD/harmonic report across all of pedal2 -> reports/comprehensive_data.json
analysis/.venv/bin/python3 analysis/comprehensive_report.py --os 8

# HTML dashboard + text executive summary from that JSON (no re-rendering)
analysis/.venv/bin/python3 analysis/dashboard_gen.py           # -> reports/dashboard.html
analysis/.venv/bin/python3 analysis/report_audit.py --write    # -> reports/executive_summary.txt
```

## Validation summary (v0.8, 2026-06-28)

Headline numbers from the validation pass that drove the v0.8 calibration changes (`kOutputMakeup`
0.9→1.217, the diode-mismatch even-harmonic fix). Captured against batches 3/4/5 (the authoritative
NAM reference — see Capture batches above); the raw WAVs are local-only (`.gitignore`'d, not in the
repo) so these figures are carried over from that session rather than re-derived live.

**Null depth** (`null_test.py` + `null_optimize.py`/`null_floor.py`, sub-sample fractional-delay
aligned, level-matched; re-measured against `analysis/pedal2` — the v2-signal batch-6 recapture,
`SIGNAL=v2`). Gain-at-noon (G=0.5), one capture per clip mode (Soft/Medium/Hard), averaged:
- **As-shipped (nominal capture settings, B0.50/T0.20):** clean-sweep null averages **−10.4 dB**
  (Soft −10.6, Medium −10.0, Hard −10.7); driven-sweep averages **−11.2 dB**. Better than this
  batch's worst case (−7.9 dB at high drive) but short of the old −13.5 dB headline from the
  earlier batch-3 capture.
- **Best achievable (small Bass/Treble/Drive retune, coordinate-descent search):** clean-sweep
  null averages **−12.4 dB** (Soft −12.3, Medium −12.2, Hard −12.8 at B≈0.30–0.34/T≈0.14–0.17/
  G≈0.30–0.34); driven-sweep averages **−13.1 dB** — deeper than the old headline. The knobs that
  null deepest sit slightly below the capture's nominal Bass/Treble/Drive in every mode, consistent
  with our pot-taper mapping being close but not pixel-perfect to the real unit (Treble moves the
  most, ~0.03–0.06 lower than nominal) — not a sign of a bigger modelling error.
- **Diagnosis (`null_floor.py`, coherence-based linear-vs-nonlinear split):** at the nominal
  settings, removing the optimal LTI (EQ+phase) filter instead of just a gain pushes the null to
  **−18.7 to −22.8 dB** (avg ≈ −20.8 dB) in every mode — ~10 dB deeper than the raw null. So the
  raw-null residual is overwhelmingly **linear** (EQ shape / group-delay / sub-sample skew vs a
  separately-recorded NAM capture), not a nonlinear clipping-model mismatch; the nonlinear floor
  itself is comfortably below what the raw null currently shows.

**THD by band / harmonic profile** (`swept_thd.py --matrix`, `harmonics.py`):
- Odd-harmonic content and overall THD track the real pedal within ~1 dB across the drive × clipping
  mode sweep once the input level is correctly matched (batch 5, +6 dB hot reamp) — the earlier
  "high-drive THD ceiling" was mostly a level-calibration artifact, not a clipping-model gap.
- H2 (even harmonic, 440 Hz, drive ≈ 5 o'clock), real vs plugin:
  - Soft: −55 dB vs −51 dB
  - Medium: −49 dB vs −51 dB
  - Hard: −34 dB vs −34 dB (exact)
  Closed by `AsymDiodePairT` — a deliberately mismatched antiparallel diode pair
  (`kSymMismatch=0.06` Soft/Medium, `kAsymMismatch=0.45` Hard) standing in for real 1N4148
  manufacturing tolerance, which a "perfect" symmetric model can't produce.
- Known residual (not chased further): ~2 dB quiet at full drive — a clip-output-scaling effect
  isolated to the top of the Gain range, confounded with harmonic content in the existing captures,
  so not resolvable without a cleaner low-drive sweep.

**Level (`run_compare.py` / `knob_tracking.py`)**:
- Pre-fix: plugin was a rock-constant **~2.6 dB quiet** at every clean (sub-clipping) setting,
  independent of input level and volume position — a pure linear-gain deficit, not a taper-shape
  error. Anchored on the cleanest available point (pure-linear batch-4 no-drive file): deficit
  −2.62 dB dead-constant across −24/−18/−12 dBFS.
- Fix: `kOutputMakeup` 0.9 → 1.217 (+2.62 dB). LEVEL pass rate across the `knob_tracking.py`
  threshold check went **0/23 → 16/23** captures.
- Remaining SHAPE fails are the accepted V4-linear-treble trade (see CLAUDE.md's taper notes), not a
  level issue.
