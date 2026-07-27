# DSP Rules

## WDF Implementation

- Use `chowdsp_wdf` (header-only, C++17) for ALL circuit modelling
- Use the **compile-time API** (`chowdsp::wdft` namespace) throughout — not the runtime `chowdsp::wdf` namespace. The compile-time API allows the compiler to inline all adaptor interfaces, yielding zero-call-instruction assembly and significantly better performance. Only use runtime API if a topology genuinely cannot be determined at compile time (it can for this circuit).
- **Use `double` precision for all WDF types** — `float` causes audible errors in Newton-Raphson iteration for diode models at audio frequencies. All `ResistorT`, `CapacitorT`, `DiodePairT`, `DiodeT`, `RtypeAdaptor` etc. must be templated on `double`.
- All passive networks modelled as WDF port trees
- Nonlinear elements use chowdsp_wdf nonlinear models with **explicit per-component datasheet parameters** — never generic defaults
- Op-amp stages use ideal op-amp WDF model (both IC1_A and IC1_B are JRC4559; neither clips rails under normal use)
- R-type adaptors required for any feedback topology — derive scattering matrix from nodal equations
- **Never reconstruct the WDF tree at runtime for switch changes** — use precomputed per-topology scattering matrices switched via `setSMatrixData()` at the R-type adaptor level
- VREF treated as signal ground throughout — model bipolar, no power supply modelling
- Linear stages: pure WDF tree computation, no Newton-Raphson
- Nonlinear stages (SW1 diodes): Newton-Raphson via chowdsp_wdf nonlinear solver

### prepareToPlay requirements
Every `CapacitorT` (and `CapacitorAlphaT`) must have `.prepare(sampleRate)` called in `prepareToPlay`. Forgetting this leaves the capacitor at its initial state with an undefined sample rate and produces silence or wrong behaviour. Call prepare on every capacitor in every WDF stage. Also reset the oversampler in `prepareToPlay`.

### PolarityInverterT
Neither op-amp stage inverts (IC1_A and IC1_B are both non-inverting, per `circuit.md`), so
neither needs a `PolarityInverterT` for op-amp polarity, and neither does Stage 0. Use
`PolarityInverterT` only if a specific WDF sub-tree's sign convention requires it for a correct
voltage readout — confirm output polarity with a DC-step test in every stage's validation.

## chowdsp_wdf API Reference (key types)

All in `chowdsp::wdft` namespace. Include header: `#include <chowdsp_wdf/chowdsp_wdf.h>`

### Passive elements
```cpp
wdft::ResistorT<double> r { 1.0e3 };           // resistor, value in ohms
wdft::CapacitorT<double> c { 1.0e-6 };          // capacitor, value in farads; call c.prepare(sampleRate)
wdft::ResistorCapacitorSeriesT<double> rc { R, C };   // convenience: R+C in series
wdft::ResistorCapacitorParallelT<double> rc { R, C }; // convenience: R+C in parallel
```

### Adaptors
```cpp
wdft::WDFSeriesT<double, decltype(a), decltype(b)> s { a, b };   // series adaptor
wdft::WDFParallelT<double, decltype(a), decltype(b)> p { a, b }; // parallel adaptor
wdft::PolarityInverterT<double, decltype(s)> inv { s };           // polarity inversion (needed for inverting op-amp)
```

### R-type adaptor (for feedback topologies)
```cpp
// ImpedanceCalculator is a struct with static method:
//   static void calcImpedance(RtypeAdaptor& r) { ... r.setSMatrixData({{ ... }}); }
// upPortIndex is the index of the port that connects upward (toward root/source)
wdft::RtypeAdaptor<double, upPortIndex, ImpedanceCalculator, Port0Type, Port1Type, Port2Type> rtype { port0, port1, port2 };

// To switch SW1 topologies at runtime (no tree reconstruction):
rtype.setSMatrixData({{ s00, s01, ... }, { s10, s11, ... }, ... }); // precomputed matrix for new topology
```

### Nonlinear elements
```cpp
// Antiparallel diode pair (Modes A and B — use for D5+D6, D3+D4):
wdft::DiodePairT<double, decltype(next), wdft::DiodeQuality::Good, AccurateOmega> dp { next, Is, Vt, nDiodes };
// nDiodes = ideality factor n (NOT a physical diode count). For 1N4148: nDiodes=1.752

// Single diode (Mode C — use for D1):
wdft::DiodeT<double, decltype(next), wdft::DiodeQuality::Best, AccurateOmega> d { next, Is, Vt, nDiodes };
// Same parameter convention as DiodePairT
```

**Omega accuracy — do NOT revert to the default omega4:** chowdsp's default `Omega::omega`
(= `omega4`) uses bit-trick `log_approx`/`exp_approx` that impose a ~-35 dB oversampling-immune
distortion floor — audible on a transparent pedal. We supply a custom `AccurateOmega` provider
(std::log/exp + Newton solve of `w + ln(w) = x`) in `Stage1.h`. **Gotcha:** `DiodePairT`'s
`DiodeQuality::Best` path hardcodes `omega4` and ignores the OmegaProvider — for the pair use
`DiodeQuality::Good` (eqn-18; accurate once given a true omega). `DiodeT` and the pair's `Good`
path both honour the provider. Accurate omega is heavier than omega4 — a candidate for gating
behind an "HQ" mode in the v1.1 optimisation pass (see `CLAUDE.md` Roadmap).

### Ideal op-amp
```cpp
// Ideal voltage-controlled voltage source — use for both IC1_A and IC1_B
// The op-amp is the root of its WDF tree (it drives the tree, not the input source)
// Connect the R-type adaptor as the op-amp's port
wdft::IdealVoltageSourceT<double, decltype(Rtype)> Vop { Rtype };

// Each sample, read the voltage at the inverting input port of the R-type adaptor,
// set the op-amp voltage to enforce virtual ground at that node (V+ - V- = 0 for ideal):
double Vin_minus = wdft::voltage<double>(invertingPort);
Vop.setVoltage(-Vin_minus * gain); // gain = -Rf/Rin for inverting; (1 + Rf/Rg) for non-inverting

// In practice for WDF ideal op-amp: the op-amp voltage source is set to drive
// the output node, and the tree solves simultaneously. See chowdsp_wdf examples
// for the exact IdealOpAmpT helper if available, or implement as above.
```

If `chowdsp::wdft::IdealOpAmpT` exists in the version of chowdsp_wdf being used, prefer it over a manual implementation. Check the installed header for availability before implementing manually.

## ADAA Implementation

ADAA (Antiderivative Anti-Aliasing) for diode nonlinearities is not a built-in one-liner in chowdsp_wdf — it requires implementing the antiderivative of the diode's implicit nonlinear function.

**Approach for WDF diode clipper:**

The standard 1st-order ADAA replaces `f(x)` with `F1(x[n], x[n-1])` where `F1` is the first antiderivative integral:

```cpp
// For a diode pair, the nonlinearity f(x) is the implicit current function.
// 1st-order ADAA:
//   if |x[n] - x[n-1]| > threshold (e.g. 1e-8):
//     output = (F1(x[n]) - F1(x[n-1])) / (x[n] - x[n-1])
//   else:
//     output = f((x[n] + x[n-1]) / 2)  // fallback for near-equal inputs

// For a 1N4148 single diode, the antiderivative of Is*(exp(v/Vt) - 1) is:
//   F1(v) = Is * Vt * exp(v/Vt) - Is*v

// For an antiparallel pair (symmetric), f(v) = 2*Is*sinh(v/Vt):
//   F1(v) = 2*Is*Vt*cosh(v/Vt)
```

Apply ADAA at the wave variable level within the WDF nonlinear element's incident wave processing, not at the plugin input/output level. Wrap the diode WDF element to intercept the incident wave, apply ADAA, then pass the result to the underlying Newton-Raphson solver.

Reference: Esqueda et al., "Antiderivative Antialiasing in Nonlinear Wave Digital Filters," DAFx 2020. Implement 1st-order ADAA minimum; 2nd-order if CPU budget allows.

### Voltage readout
```cpp
double output = wdft::voltage<double>(element); // read voltage across any element
```

### Deferred impedance propagation (use for coupled controls like BASS+DRIVE)
```cpp
// When updating multiple parameters simultaneously, defer impedance propagation
// to avoid redundant recalculations:
{
    wdft::ScopedDeferImpedancePropagation deferrer { port0, port1 };
    r_bass.setResistanceValue(newBassR);
    r_drive.setResistanceValue(newDriveR);
} // impedance propagation fires once here, not twice
```

### 1N4148 diode parameters (use these exact values — do not use defaults)
```cpp
constexpr double Is_1N4148 = 1.26e-9;   // saturation current (A) — see calibration note below
constexpr double Vt_1N4148 = 25.85e-3;  // thermal voltage (V)
constexpr double n_1N4148  = 1.752;     // ideality factor — passed as nDiodes parameter
// nDiodes in chowdsp_wdf is the ideality factor n in the Shockley equation, not a physical diode count.
// For 1N4148: pass nDiodes=1.752 (the measured ideality factor), not nDiodes=1.

// Note: chowdsp_wdf DiodePairT/DiodeT has no separate series resistance (Rs) parameter.
// Rs=0.568Ω for 1N4148 must be modelled as an explicit ResistorT in series with the diode element
// if series resistance is deemed audibly significant. At guitar signal levels it is negligible
// and may be omitted — flag if in doubt. (Ruled out as the cause of the Is recalibration below —
// at guitar-level diode currents Rs's ohmic drop is orders of magnitude too small to account for
// the multi-kΩ incremental-impedance gap that motivated it.)

// The Medium clip mode does NOT use these two values directly — it has its own kIsMedium (= kIs,
// same diode part) and kNMedium (= 1.5*kN, i.e. Vt_eff 67.9 mV instead of 45.3 mV). Deriving
// Medium as "one pair instead of two" makes it only ~31 mV different from Soft, whereas the real
// pedal's Medium is much cleaner at low level AND harder at high level. Fitted 2026-07-26 (v1.4
// W1) against pedal2; Soft is bit-identical and is what pins the shared parameters below. Ruled
// out first: SW1 mid is NOT an open circuit (rendering it as Linear is +6.1 dB THD error). See
// Stage1.h's kNMedium comment and circuit.md's Mode B threshold note.

// Is CALIBRATED 2026-07-04 (half the 2.52e-9 datasheet-typical value, see Stage1.h's kIs comment
// for the full derivation): the datasheet figure is a typical spec, not a per-unit measurement, and
// real 1N4148 Is commonly spreads several-fold between individual parts/batches. This closed a
// ~1.8-2.6 dB asymptotic (DRIVE->max) gain shortfall vs the pedal2 reference, confirmed via
// dsp-validator to be a genuine parameter gap rather than a WDF/topology bug or a DRIVE-taper
// issue. Re-derive from a physical measurement of the actual installed diodes if that ever becomes
// available — this value is an empirical fit, not a datasheet lookup.
```

## Oversampling

- Apply oversampling to the SW1 clipping stage as the PRIMARY reason (nonlinear → aliasing)
- Use `juce::dsp::Oversampling`
- Minimum 4x, prefer **8x** for the clipping stage
- User-selectable: 1x / 2x / 4x / 8x — expose in UI
- Oversampling factor change must be glitch-free (handle transition cleanly)
- **The oversampled region spans Stage 1 → Treble → Stage 2**, not just the nonlinear clipper.
  Reason: the downstream linear stages have audible-band HF caps (Treble C5, Stage 2 C11) whose
  base-rate bilinear discretisation droops the top octave (~2.3 dB @12k even after prewarp).
  Implemented via `ClippingOversampler::processBlock(data, n, postFn)`: the postFn (treble +
  Stage 2) runs per oversampled sample; prepare those stages at `getOversampledRate()`. Do NOT
  oversample stages with no audible-band HF caps (e.g. the InputBuffer ≈8 Hz HP) — no benefit,
  just cost. Keep the prewarp (`Prewarp.h`) too — it still helps at the 1x setting.
- **Top-octave restore (`TopOctaveRestore.h`) — base-rate correction for the LOW-OS droop.** Even
  with prewarp, at low oversampling the Treble/Stage 2 bilinear discretisation droops the top
  octave (measured vs an 8x reference: 1x ≈ −4 dB @8k / −10 dB @12k / −21 dB @16k; 2x ≈ −0.9 /
  −2.2 / −4.1; 4x/8x negligible — see `tests/OSFidelity.cpp`). The droop is essentially
  POT-INDEPENDENT and scales with the OS factor, so a single fixed-shape RBJ high-shelf (fc≈9.5k,
  steepest non-resonant slope) with gain set PER OS FACTOR (`{+12, +3, 0, 0}` dB for 1x/2x/4x/8x)
  restores most of it: 1x → within ±1.2 dB through 12 kHz (16 kHz stays ~−9 dB; you can't invert a
  near-Nyquist zero without instability — accepted, least audible). At 4x/8x the gain is 0 so it is
  bit-transparent (the default experience is unchanged). Applied at BASE rate after the C6 DC block
  in `TommyDSP::processBlock`; one biquad, ~0 CPU, no added latency. Also restores the clipped
  harmonics' top octave (1x harmonic fidelity vs 8x went −2.6 dB → −0.4 dB), and barely touches
  aliasing. Always-on (it self-disables where there's no droop) — NOT gated behind any toggle.
- **Drive-faded top-octave tilt (`DriveTilt.h`) — corrects a LOW-DRIVE linear-FR tilt vs the real
  pedal.** Separate from the bilinear droop above: measured at 8x against the authoritative pedal2
  NAM captures (level-normalised to 1 kHz — the `knob_tracking.py` SHAPE metric), the model's linear
  top octave rolls off more than the real pedal across 2–8 kHz, *worst when clean* and
  shrinking as drive rises (clip harmonics fill the top at high drive). So it's a base-rate high-shelf
  (fc≈2.5k) whose gain is FULL at low drive and **fades to 0 by ~G0.8** (keyed to the DRIVE pot via
  `setDrivePosition`). The fade is essential — a fixed top lift would over-brighten high drive (where
  the tilt is already gone) and break the validated high-drive match. One biquad, ~0 CPU, high drive
  bit-unchanged. **pedal2 is the definitive tone reference for this** (user decision); the hot
  tone-set pedal1 disagrees on the top octave, but pedal2 is authoritative.
- **BASS↔DRIVE LF coupling correction (`BassTilt.h`) — a DRIVE- and CLIP-MODE-keyed LOW shelf
  (v1.4 W4).** Distinct from both shelves above: it acts below ~250 Hz, and its gain **changes
  sign** with DRIVE rather than fading out. Measured 1 kHz-normalised against pedal2, the model's
  low end is ~1 dB **dark** at low DRIVE and up to **2.6 dB hot** at DRIVE ≥ 0.65, mode-ordered
  (Medium worst, Soft nearly exact), in 15/16 captures. Fixed corner **250 Hz**, gain interpolated
  from a fitted per-mode table over six DRIVE positions (see the table in `BassTilt.h`).
  Fitted as an oracle bound — one static shelf per (DRIVE, mode), minimax over all four sweep
  depths and the LF SHAPE bands: **worst LF deviation median 1.00 → 0.46 dB, max 2.61 → 1.14, and
  settings over the 1.5 dB SHAPE gate 4 → 0.** Letting the corner float per setting buys only
  0.02 dB, so the corner is fixed and only the gain is keyed.
  **Keyed on DRIVE, not BASS (user decision).** pedal2 samples six DRIVE values across the full
  range but only two BASS values, locked to DRIVE — so DRIVE-keying is a 1-D fit with complete
  coverage, where (BASS, DRIVE) would be a 2-D surface from five points on a diagonal that no
  future capture can ever constrain (W6). Accepted cost: if the effect is physically BASS-driven,
  high-BASS/low-DRIVE gets the wrong sign.
  **Irreducible ~0.42 dB residual:** the ideal shelf differs per signal LEVEL and a static one can
  only sit in the middle; closing that needs an envelope follower, which the plugin does not have
  (these shelves key off POT positions, never the signal). `setGainScale(0)` makes it
  bit-transparent — used by `offline_render.cpp` argv[25] for A/B.
  **Do not re-derive the table's sign** — it is the correction to APPLY, i.e. the negative of the
  measured plugin−pedal deviation; the v1.4 plan's old handover table inverted exactly this.
  **Two W4 arguments were retracted to get here** and must not be re-made: "the error collapses
  with level so it is not linear" (clipping MASKS linear errors at high level) and "a shelf is
  mode-independent by construction" (SW1 position is a knob). See `CLAUDE.md`'s W4 entry.

  **`kMaxGainDB` RE-FITTED 2.5 → 1.0 dB (2026-07-27, v1.4 W2)** — this shelf and the DRIVE taper are
  fitted against the SAME low-drive captures, so W2's taper re-fit (`x^2.2` → `x^2.75`) invalidated
  the 2.5 dB by construction. It turned out 2.5 dB was partly compensating **clipping compression**
  rather than the linear tilt this shelf is for: the old taper over-drove low DRIVE, the clipper
  squashed the top octave, and the shelf was sized to lift that back. With the pre-clip gain
  corrected the compression is gone and the same lift over-brightens. Re-fitting takes driven-sweep
  FR *below* the pre-W2 baseline at every depth. **If the DRIVE taper is ever touched again, re-fit
  this shelf in the same pass** — `analysis/w2_clip_onset.py --only fit --fit-tilt …` crosses the
  two; do not assume either still holds after the other moves.

## ADAA

- ADAA is in addition to oversampling, not instead of it
- ADAA must be transparent — must not colour the sound
- Reference: DAFx2020 paper "Antiderivative antialiasing in nonlinear wave digital filters" — 2x ADAA + oversampling outperforms higher oversampling alone

**ADAA is applied to the op-amp rail clip, not the diodes (deliberate — do not re-litigate
without new measurement data):** the hard op-amp rail clip is the dominant aliasing source; the
soft diodes already produce fast-decaying harmonics that oversampling alone crushes (Soft 8x =
-81 dB; ADAA there measured as a 0.03 dB no-op). The chowdsp diode models also expose no
closed-form antiderivative, so diode ADAA would need a bespoke omega-antiderivative
implementation for ~no audible gain. 1st-order ADAA wraps `railClip` (exact piecewise
antiderivative `railAntideriv` in `Stage1.h`); diodes rely on oversampling + the `AccurateOmega`
fix. Hard mode: 8x -54 dB → 8x+ADAA -60 dB. If diode-pair ADAA is revisited, it's a v1.1 "HQ
mode" candidate (see `CLAUDE.md` Roadmap) — discuss with the user first.

## Potentiometer Tapers

- Taper type is per-control and version-dependent — see `circuit.md`'s Pot Tapers section and
  `CLAUDE.md`'s Calibration constants for the shipped formulas. Do not assume audio (log) taper
  for all four controls (TREBLE is a linear taper on the targeted pedal revision).
- Apply taper conversion before passing value to WDF node

## Component Values

- Use schematic values exactly — see `circuit.md`
- 1N4148 Shockley params: Is=1.26e-9 (empirically calibrated, half datasheet-typical — see the
  "1N4148 diode parameters" section above), n=1.752, Vt=25.85e-3, Rs=0.568 (omitted, negligible)
- Do not substitute or approximate any passive value
- Flag any unresolvable value before proceeding

## Interactive Controls

- BASS and DRIVE share Stage 1 feedback network — model as coupled WDF network
- Use `ScopedDeferImpedancePropagation` when updating BASS and DRIVE simultaneously to avoid double impedance propagation
- TREB interacts with R5/C5 — model as coupled passive WDF network
- Never decouple interactive controls into independent processing

## Signal Calibration

- Internal nominal: **-12 dBu**
- Provide input trim and output trim (UI-labelled, visually distinct from pedal controls)
- Input trim: post-trim → VU meter → DSP chain
- Output trim: DSP chain → VU meter → output trim

