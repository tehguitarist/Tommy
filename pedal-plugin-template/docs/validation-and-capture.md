# Reference Validation & Capture — Hard-Won Lessons

How to measure how close the plugin is to the real pedal, and how to capture the pedal so the
measurement is actually trustworthy. Companion to `calibration-and-gain-staging.md` (that doc sets
levels; this one verifies them and the rest of the model against the real thing).

> **The single biggest lesson: the test signal is almost never the limitation — the capture
> SETTINGS MATRIX is.** A perfect signal captured at the wrong/confounded settings can't be fit.
> Spend your recapture budget on the matrix (§3), not on the signal.

The reusable harness lives in `analysis/`:
- `gen_test_signal.py` — the comprehensive A/B signal (full-range sweep + 3 driven sweeps for THD +
  level steps + discrete tones + IMD + decay notes). Single source of truth for segment timings.
- `analyze.py` — reusable primitives: load/align, `transfer` (FR), `thd` (discrete) +
  `harmonic_thd_curve` (continuous Farina swept THD), `frac_align`/`null_depth` (sub-sample null),
  `parse_filename` (clock + 0-10 notations), `is_full_length` (truncation guard).

---

## 1. The four analyses (what each answers)

1. **Frequency response** — 1/3-octave (≈30 pts, 20 Hz–20 kHz) from the **clean** sweep via
   `transfer()`. Read EQ ONLY from the clean (low-level) sweep so clip harmonics don't pollute the
   tone fit. This is your taper/tone-stack accuracy check.
2. **THD by frequency band** — `harmonic_thd_curve()` deconvolves a **driven** sweep (Farina
   exponential-sweep harmonic separation) into a **continuous** THD(f) curve from a single capture —
   no need for hundreds of discrete tones. Pay attention to the 1–8 kHz band (where most saturation
   character lives). **VALIDATE the swept curve against the discrete-tone `thd()` at the same
   frequencies before trusting it** — if they disagree, the deconvolution/gating is wrong, fix it
   first. (On the reference build, tightening the harmonic gate to 35% of the inter-order gap took
   the swept curve from ~25% high to within ~1% of the discrete tones.)
3. **Null test** — `frac_align()` then `null_depth()`: sub-sample align, optimal-gain level-match,
   subtract, report residual dB. **It measures timbre/shape/phase, NOT absolute level** (the gain
   match removes level). Report the BEST null (cleanest linear setting — the README headline) and
   the WORST (honesty). Integer-only alignment is not enough: 1 sample at 20 kHz ≈ 150° phase error.
4. **Knob-tracking pass/fail** — at every captured setting, does the plugin match the real pedal?
   Separate three things with explicit thresholds, because they fail for different reasons:
   - **SHAPE** — EQ compared RELATIVE to 1 kHz (level offset removed) → tone-stack accuracy.
   - **LEVEL** — absolute output at 1 kHz → the gain-staging/makeup calibration.
   - **THD** — distortion amount → clipping character.

---

## 2. Wiring it to your pedal

The orchestrators (compare-vs-batch, null-vs-batch, knob-tracking) render the plugin via an
**`OfflineRender`** console exe that runs your REAL DSP chain plus the exact `processBlock` gain
staging (kInputRef in, kOutputMakeup·volume/kInputRef out), and takes knob positions + mode as
CLI args. Build it as a `juce_add_console_app` target (see `build.md`). Then each orchestrator:
parse filename → render plugin at those settings → `align` both to the reference → compare per §1.
Use OS 8x for the comparison to take aliasing off the table. `analyze.py` is pedal-agnostic; only
the OfflineRender arg layout is per-pedal.

---

## 3. Capture protocol (the part that actually matters)

1. **Fix the interface gain for the WHOLE session and never touch it.** Ambiguous return gain
   between sessions makes absolute level unverifiable — it cost real investigation on the reference
   build to decide a level deficit was genuine rather than a recording artifact.
2. **Capture a BYPASS pass first** (pedal in true bypass, same signal). This is the absolute-level /
   unity anchor — without it you cannot state absolute level with confidence.
3. **One knob at a time.** Hold the other controls fixed; step only the knob under test (~5–6
   positions). Confounded multi-knob captures can't be used to fit an individual taper.
4. **Sweep EVERY control — including Volume.** A control you never sweep has zero ground truth; on
   the reference build Volume was never captured and its taper stayed an unvalidated guess.
5. **Full length, no truncation.** A short file's missing segments read as zeros → garbage numbers.
   `is_full_length()` skips them, but you still lose the capture.
6. **Read EQ only from the clean sweep** — keep drive low on the FR captures.
7. **Consistent filename notation** the parser understands, e.g.
   `V1200 B0700 T0700 G1030 switch mid <signal>.wav` (clock HHMM: 0700=min, 1200=noon, 1700=max;
   `switch up/mid/down`). The 0-10 dial notation (`G3 V4 B6 T4 SYM`) is also auto-detected.
8. **Cross-check fits against ≥2 batches**, and note **primary vs secondary** references — knob
   direction and component values differ between an original and a licensed reissue.

A good default matrix: bypass ×1; Volume sweep (incl. the pedal's unity position) at min drive/no
cut; Drive sweep × each clip mode; Bass sweep; Treble sweep. ~30 captures, ~40 min.

---

## 4. Decomposing a level deficit (do this before changing any constant)

If the plugin is quieter/louder than the real pedal, find out WHY before touching `kOutputMakeup`:

- Measure plug−real at a **clean, low input level** (no clipping) across several input levels.
  - **Constant across input level** → a pure linear-gain error → makeup (or a globally-off volume
    taper). Anchor the fix on the **cleanest pure-linear, no-drive** capture.
  - **Grows with drive** → the clipped-output scaling (the clipping ceiling). **Do NOT mask this
    with makeup** — makeup is a flat scalar; using it to paper over a drive-dependent gap throws off
    every clean setting. (See the "go hotter" trap in `calibration-and-gain-staging.md`.)
  - **Differs by volume position** → the volume taper, not makeup.
- **Cross-check:** after fixing makeup, unity (output = input at min drive / no cut) should land at
  the volume position the REAL pedal does (often ~1 o'clock). If the makeup that level-matches your
  captures ALSO lands unity at the right spot, that's two independent facts agreeing — strong
  evidence it's right. (On the reference build this is exactly how the makeup value was confirmed.)

This decomposition is why `calibration-and-gain-staging.md` §2 says **calibrate makeup to the
captures** rather than pinning it to a "headroom-safe" number — see that section.
