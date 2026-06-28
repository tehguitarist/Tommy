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
> 0 dBFS input: 0 NaN/Inf, 0 runaway, all bounded. kOutputMakeup RE-CALIBRATED to 1.217 in v0.8
> (was 0.9; +2.6 dB to match the authoritative batch-3/4/5 captures — see CALIBRATION).
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
> - `kOutputMakeup = 1.217f` — **RE-CALIBRATED 2026-06-27** to the authoritative batch-3/4/5 captures
>   (user confirmed these are the reliable reference; the old 0.9 was matched to batch 1/2). The v0.8
>   validation harness (`analysis/knob_tracking.py`) found the plugin was a ROCK-CONSTANT ~2.6 dB
>   quiet at every CLEAN setting — a pure linear-gain deficit, independent of input level AND volume
>   position (volume-taper SHAPE was already right). Anchored on the cleanest point: the pure-linear
>   batch-4 no-drive file, deficit −2.62 dB dead-constant across −24/−18/−12 dBFS. Fix = +2.62 dB:
>   0.9·10^(2.62/20) = 1.217. LEVEL agreement went 0/23 → 16/23 captures; auval + 7 ctests still pass.
>   The old "do NOT lower / would be 8.7 dB quiet" and "worst case ≈ −0.6 dBFS" notes were BOTH wrong
>   (untested vs these captures). HEADROOM REALITY: now ~2.6 dB hotter than before — the upper-third
>   "boost zone" (a faithful cranked-Timmy overload, managed by the −12 dB output trim + volume knob)
>   sits correspondingly higher; this MATCHES the real pedal's level, which is the whole point.
>   KNOWN RESIDUALS (NOT masked with makeup — that's a crutch): ~2 dB quiet at full drive (clip-output
>   scaling = the documented clipping ceiling); the V0.4 ~3.5 dB deficit — **INVESTIGATED & CLOSED
>   2026-06-27** (new v2 captures `analysis/pedal1` V0.4 + `analysis/pedal2` V0.5): it is a
>   CAPTURE-GAIN discrepancy between the two sessions, NOT a taper error. Proof: the A25K + R11(18k)
>   divider is PHYSICALLY forced to rise ~+3.3 dB from V0.4→V0.5 (R11 pins the upper arm ~constant in
>   the lower range, so gain just tracks the wiper — true for ANY monotonic taper); the captures show
>   V0.4≈V0.5 (flat), which is physically impossible for this pot+R11. Making it flat would need a
>   CONCAVE taper (volume maxed by ~9 o'clock — bad feel, contradicts the spec'd A25K audio pot). The
>   ~3.4 dB gap ≈ exactly the physical volume step = the tell of a per-session recording-gain offset.
>   Volume model is physically correct and LEFT AS-IS; V0.5+ level matches spot-on (makeup 1.217
>   validated by the fresh v2 captures), unity holds at 1 o'clock, everything matches when normalised.
>   (Volume is a forward A25K + R11 divider — NOT reverse-wired like BASS/TREBLE; the bass convex
>   x^2.41 came from bass being in the Stage-1 feedback gain-leg, a different mechanism that does not
>   transfer to the volume output divider.)
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
>   thresholds (a component-tolerance effect a "perfect" model can't show). FIX (final, 2026-06-22):
>   `AsymDiodePairT` is a **MISMATCHED antiparallel pair** — +swing diode Vt·(1+m), −swing Vt·(1−m).
>   ALL diode modes use it (Soft/Medium too; at m=0 bit-identical to matched `DiodePairT`).
>   **`kSymMismatch=0.06`** (Soft/Medium), **`kAsymMismatch=0.45`** (Hard — large because Hard is
>   really a single, strongly one-sided diode approximated by a heavily-mismatched pair; symmetric
>   about Vt so it does NOT run hot). Result @440 Hz G1500 H2 real/plug: Soft −55/−51, Medium −49/−51,
>   Hard −34/−34 (exact); ODD harmonics + THD + level unchanged. **Per-polarity Vt, NOT a lateral bias
>   (earlier model):** a lateral bias shifted the operating point at ALL levels, perturbing near-zero-
>   signal gain up to ~21% (Hard); per-polarity mismatch acts ONLY where the diodes conduct, so small-
>   signal gain is UNPERTURBED (test rel err 0.0004–0.001, was 0.21) — asymmetry appears only at
>   clipping, as in reality. C6 (1µ ~6 Hz) output DC-block in `TommyDSP` handles the asymmetric clips'
>   signal-dependent DC. `offline_render` arg[20]=symMismatch, arg[15]=asymMismatch for A/B.
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
>   4. Step 9 gate DONE (subjective + objective stability sweep passed; kOutputMakeup was 0.9, now
>      RE-CALIBRATED to 1.217 in v0.8 to match batch-3/4/5 — see CALIBRATION).
>   - **Supply-voltage feature — DONE 2026-06-21.** Selectable 9/12/18 V via APVTS `supply_voltage`
>     (default 9 V) → `TommyDSP::setSupplyVoltage` scales BOTH op-amp rails (Stage1 via
>     `ClippingOversampler::setRailVoltages`, Stage2 direct); anchored at 9 V = +2.5/−3.4, slopes
>     +0.451/+0.549 V per supply volt (VREF divider ratio). Diode thresholds unchanged → pure HEADROOM
>     change: 0 effect at moderate levels, clearly present at high output/Hard mode/hot input (Hard
>     swing 9 V ±3.3 → 18 V ±7). UI: the "(+) 9V (−)" power label is now an interactive `SupplyControl`
>     ((+) raises, (−) lowers; lit when that direction is available). offline_render arg[19]=supplyV
>     for A/B. auval passes; default 9 V keeps all renders/tests byte-identical.
>   - **RT-safety — FIXED 2026-06-23.** `ClippingOversampler::setFactor()` used to `make_unique` +
>     `initProcessing()` a new `juce::dsp::Oversampling` every time the live/render OS factor changed
>     — reachable from `processBlock` on the audio thread (user moves the OS dropdown live, or
>     playback crosses the realtime/non-realtime boundary). Fixed by pre-building all three needed
>     `Oversampling` instances (2x/4x/8x) up front in `prepare()` (called once from `prepareToPlay`,
>     off the audio thread); `setFactor()` now only swaps a pointer + resets filter state — zero
>     allocation. All 8 test executables + auval still pass.
>   - **VST3 — DONE 2026-06-27.** Added to `FORMATS` in `CMakeLists.txt` (`AU VST3`); builds for
>     macOS/Windows/Linux via the new CI/release workflows (see Roadmap below). No DSP/UI changes
>     needed — JUCE's CMake layer only produces AU on macOS regardless of the FORMATS list.
>   - Open items: none for the DSP/UI build. See **Roadmap** below for what's left before 1.0.**

## Roadmap

> Tracks what's done per version and what's deliberately deferred, so it survives context
> resets. Update the version line here, not just "Current Step" above, when a release ships.

- **v0.7 (current release, 2026-06-27):** GitHub Actions CI (`.github/workflows/ci.yml` —
  build + `ctest` across macOS/Windows/Linux on every push/PR) and a manual-trigger release
  workflow (`.github/workflows/release.yml` — `workflow_dispatch` only, never runs on push) that
  builds VST3 for macOS/Windows/Linux (+ AU on macOS) and publishes one zip per platform to a
  GitHub Release. Plugin version bumped to 0.7.0. **macOS release artifacts are unsigned** —
  Gatekeeper will warn on first launch until 0.8.
- **v0.8 IN PROGRESS:** Full reference-validation pass against the authoritative batch-3/4/5 NAM
  captures. **DONE (2026-06-27):** comprehensive validation harness built + documented
  (`analysis/README.md`) — `run_compare.py FINE=1` (1/3-octave EQ 20 Hz–20 kHz), `swept_thd.py`
  (continuous THD(f) via Farina exponential-sweep harmonic separation, validated vs discrete tones,
  + `--matrix` THD×drive×mode table), `null_test.py` (sub-sample-aligned null; current best clean
  null −13.5 dB), `knob_tracking.py` (pass/fail with SHAPE/LEVEL/THD thresholds),
  `volume_supply_check.py`. Findings: THD tracks well across drive×mode; the big issue was a
  ~2.6 dB flat LEVEL deficit → **kOutputMakeup re-calibrated 0.9→1.217** (LEVEL 0/23→16/23).
  **REMAINING for v0.8:** (a) write the best null depth + THD-by-band summary into the README;
  (b) chase the two documented residuals if desired (full-drive clip-scaling ~2 dB; V0.4 volume
  taper ~4 dB — the latter needs a **batch-6 Volume-sweep reamp**, the one capture gap, since no
  batch varies Volume); (c) the EQ-shape SHAPE-fails are the known V4-linear-treble trade.
  **DONE (2026-06-28):** Apple Developer ID signing + notarization wired into `release.yml`'s
  `macos` job — imports the cert into a temporary keychain (`APPLE_CERT_P12_BASE64` +
  `APPLE_CERT_PASSWORD`), codesigns both AU and VST3 bundles (`APPLE_SIGNING_IDENTITY`, hardened
  runtime + timestamp), submits to `notarytool` (`APPLE_ID` + `APPLE_APP_SPECIFIC_PASSWORD` +
  `APPLE_TEAM_ID`, `--wait`), staples the ticket, then packages and deletes the temp keychain.
  **Verified live 2026-06-28** — `workflow_dispatch` run succeeded end-to-end, notarytool returned
  `status: Accepted`. Also added per-platform installers (`installer/macos|windows|linux/`): a
  macOS `.pkg` with an AU/VST3 choice screen (both selected by default), a Windows `.exe` (NSIS),
  and a Linux `.deb` — published alongside the raw plugin-only zips (fixed the macOS zip to
  exclude `libTommy_SharedCode.a`, a ~28 MB build byproduct that was leaking into it). Same
  signing/installer/zip-fix pattern was ported into `pedal-plugin-template/` for reuse.
- **v0.9 DONE (2026-06-28):** Plugin version bumped to 0.9.0. 5 factory presets (Bluesy OD,
  Rhythm Crunch, Rock Lead, High Gain, Edge-of-Breakup) wired via the standard JUCE program API
  (`getNumPrograms`/`setCurrentProgram`/`getProgramName` in `PluginProcessor.cpp`) — exposed in any
  host's preset menu. Knob values are stored as physical 0-10 dial positions (matching printed
  pedal markings) in `factoryPresets`, converted to the 0-1 APVTS normalised range via
  `setValueNotifyingHost` at apply time. auval +
  7 ctests still pass.
- **v1.0 TODO:** Per-platform installers shipped early (v0.8, see above) using pkgbuild/productbuild
  (macOS), NSIS (Windows), and dpkg-deb (Linux). Nothing else currently scoped for v1.0 — revisit
  once there's a concrete next feature.
