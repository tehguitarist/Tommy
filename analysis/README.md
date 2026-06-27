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
| `knob_tracking.py` | Formalized **pass/fail**: at every captured setting, does the plugin match the real pedal? Separates SHAPE (tone-stack, level-normalized) from LEVEL (absolute) from THD, with explicit thresholds. `knob_tracking.py <dir> [<dir>…]`. |
| `volume_supply_check.py` | Self-consistency for the two controls with no real reference: Volume monotonicity + Supply (9/12/18 V) headroom ordering. |
| `harmonics.py` | Per-tone harmonic profile (H2…H7, even-vs-odd) vs a capture — clip-character detail. |
| `treble_fit.py` / `treble_xcheck.py` / `sweep_kinput.py` | Taper/level fitting helpers used when refitting a control against the captures. |

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
```
