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
**Corrected 2026-06-16:** IC1_A is **non-inverting** (verified against `updated schematic -
timmy.png` — see the circuit.md audit banner). Earlier guidance here claiming IC1_A is
inverting and needs a `PolarityInverterT` was wrong. **Neither op-amp stage inverts**, so
neither IC1_A nor IC1_B needs a `PolarityInverterT` for op-amp polarity. (Stage 0 also needed
no inverter — confirmed by its DC-step polarity test.) Use `PolarityInverterT` only if a
specific WDF sub-tree's sign convention requires it for a correct voltage readout, not because
of op-amp inversion. Confirm output polarity with a DC-step test in every stage's validation.

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
wdft::DiodePairT<double, decltype(next), wdft::DiodeQuality::Best> dp { next, Is, Vt, nDiodes };
// nDiodes = ideality factor n (NOT a physical diode count). For 1N4148: nDiodes=1.752
// Use DiodeQuality::Best — higher accuracy Wright Omega approximation, correct for audio

// Single diode (Mode C — use for D1):
wdft::DiodeT<double, decltype(next), wdft::DiodeQuality::Best> d { next, Is, Vt, nDiodes };
// Same parameter convention as DiodePairT
```

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
constexpr double Is_1N4148 = 2.52e-9;   // saturation current (A)
constexpr double Vt_1N4148 = 25.85e-3;  // thermal voltage (V)
constexpr double n_1N4148  = 1.752;     // ideality factor — passed as nDiodes parameter
// nDiodes in chowdsp_wdf is the ideality factor n in the Shockley equation, not a physical diode count.
// For 1N4148: pass nDiodes=1.752 (the measured ideality factor), not nDiodes=1.

// Note: chowdsp_wdf DiodePairT/DiodeT has no separate series resistance (Rs) parameter.
// Rs=0.568Ω for 1N4148 must be modelled as an explicit ResistorT in series with the diode element
// if series resistance is deemed audibly significant. At guitar signal levels it is negligible
// and may be omitted — flag if in doubt.
```

## Oversampling

- Apply oversampling to the SW1 clipping stage **only** — not full chain
- Use `juce::dsp::Oversampling`
- Minimum 4x, prefer **8x** for the clipping stage
- User-selectable: 1x / 2x / 4x / 8x — expose in UI
- Oversampling factor change must be glitch-free (handle transition cleanly)
- Do NOT oversample linear stages

## ADAA

- Apply ADAA to the diode waveshaper stage within the WDF tree
- ADAA is in addition to oversampling, not instead of it
- ADAA must be transparent — must not colour the sound
- Reference: DAFx2020 paper "Antiderivative antialiasing in nonlinear wave digital filters" — 2x ADAA + oversampling outperforms higher oversampling alone

## Potentiometer Tapers

- All four pots are **audio taper (A)** — use approximated exponential curve
- Never use linear mapping for an A-designation pot
- Apply taper conversion before passing value to WDF node
- Recommended: `R = R_max * pow(10.0, 2.0 * x - 2.0)` or equivalent two-segment approx

## Component Values

- Use schematic values exactly — see `circuit.md`
- 1N4148 Shockley params: Is=2.52e-9, n=1.752, Vt=25.85e-3, Rs=0.568
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

