# DSP Rules (generic, circuit-modelled pedal)

> Calibration & gain-staging lessons live in `docs/calibration-and-gain-staging.md` — read that
> too. This file covers WDF modelling, oversampling, ADAA, and the chowdsp_wdf gotchas.

## WDF Implementation

- Use **`chowdsp_wdf`** (header-only, C++17) for all circuit modelling.
- Use the **compile-time API** (`chowdsp::wdft` namespace), not the runtime `chowdsp::wdf` one —
  the compiler inlines all adaptors for near-zero call overhead. Only fall back to runtime API if a
  topology genuinely cannot be fixed at compile time (rare).
- **Use `double` for all WDF types.** `float` causes audible errors in diode Newton-Raphson at
  audio rates. Template every `ResistorT`, `CapacitorT`, `DiodePairT`, `DiodeT`, `RtypeAdaptor`,
  etc. on `double`.
- Op-amp stages: use the **ideal op-amp** model (`IdealVoltageSourceT` as the tree root driving an
  R-type adaptor, or `IdealOpAmpT` if present in your chowdsp_wdf version — check the header).
- **R-type adaptors for any feedback topology.** Derive the scattering matrix from nodal equations.
- **Never rebuild the WDF tree at runtime** for switch changes — precompute one scattering matrix
  per topology and swap via `setSMatrixData()` at the R-type adaptor.
- VREF = signal ground throughout: model **bipolar**, no power-supply node modelling (but DO model
  the op-amp output rails as a saturation — see calibration doc §6).

### Ideal op-amp decomposition (the workhorse pattern)

For an ideal op-amp the (−) input sits at the (+) input voltage and draws no current, so a
feedback stage decomposes into two independent one-ports:
```
Gain-set leg Zg (− input -> AC ground)   : Ig = Vin / Zg
Feedback leg  (− input -> output)        : Vf = (voltage Ig develops across the feedback leg)
Vout = Vin + Vf            (non-inverting)   // gain = 1 + Zf/Zg
```
This avoids a full R-type solve for simple stages. Nonlinear elements (clipping diodes) sit in the
feedback leg and only clamp `Vf` — the op-amp holds the (−) node regardless. Confirm output
polarity with a **DC-step test** in every stage; only add a `PolarityInverterT` if the readout sign
genuinely requires it (NOT reflexively for "inverting" op-amps — verify against the schematic).

### prepareToPlay requirements (missing these = silence or wrong behaviour)

- Call `.prepare(sampleRate)` on **every** `CapacitorT` / `CapacitorAlphaT` in every stage.
- Reset the oversampler.
- Each stage exposes `prepare(double sampleRate)` chaining down to its caps; the processor calls
  them in signal-chain order. JUCE calls `prepareToPlay` on every sample-rate change, so this also
  handles SR changes between sessions.

## Nonlinear elements (clipping diodes)

```cpp
// Antiparallel pair (symmetric clip):
wdft::DiodePairT<double, decltype(next), wdft::DiodeQuality::Good, AccurateOmega> dp { next, Is, Vt, nDiodes };
// Single diode (asymmetric clip):
wdft::DiodeT<double, decltype(next), wdft::DiodeQuality::Best, AccurateOmega> d { next, Is, Vt, nDiodes };
```
- Use **explicit per-component datasheet parameters**, never generic defaults. `nDiodes` is the
  **ideality factor n** (Shockley), NOT a physical count. (1N4148: Is=2.52e-9, Vt=25.85e-3, n=1.752.)
- chowdsp diodes have no series-Rs parameter; add an explicit `ResistorT` in series if Rs is
  audibly significant (usually negligible at guitar levels).

### Asymmetric clip modes — bias a symmetric pair, don't use threshold asymmetry

`DiodePairT` is **symmetric**; `DiodeT` is **one-sided** (clips one polarity, the other runs to the
rail → strongly **even-dominant**, too loud/bright — wrong for most "asym" switches). A real "asym"
position is usually **odd-dominant with moderate even** (H3 biggest, H2 below it) at **roughly the
same level as the symmetric modes**.

The trap (learned the hard way): making the asymmetry from a **per-polarity threshold** (e.g. 1 diode
one way, 2 in series the other) matches the even/odd balance ONLY by clipping the loose side ~4 dB
louder — and level is then **coupled** to the asymmetry, so you can't fix the level without losing the
harmonics. Null tests exposed it (asym ~4 dB hot, nulled worse than the symmetric modes even after
level-matching).

The fix that **decouples level from asymmetry**: take a SYMMETRIC pair (same threshold as the
medium/symmetric mode) and shift it by a small **lateral bias** in the wave domain —
`b(a) = symPair(a + bias) − symPair(bias)` (subtract `symPair(bias)` so `b(0)=0`, no static DC). The
shift makes the clip mildly asymmetric (even harmonics) while both sides still clip at the same
threshold (level unchanged). Tune `bias` to the captured even/odd. In the reference build this put the
asym level back on top of the symmetric modes and its null depth matched them across the whole drive
range. Two caveats: (1) an asymmetric clip produces **signal-dependent DC** — model the output
coupling cap (a ~6 Hz DC-block highpass) or it leaks DC; (2) a fixed bias perturbs the **small-signal
gain** (more bias = more: ~3 % at a small bias, ~20 % at a large one, measured at near-zero signal) —
a LOW-LEVEL artifact only (moderate/playing-level output is unchanged), and it over-asymmetrises at
very low drive; fine if the nulls/levels hold, else use a signal-scaled bias. Still honours the
OmegaProvider, so no omega4 floor.

### Even harmonics in the "symmetric" modes — model component tolerance, not the ideal circuit

A real pedal's *symmetric* clipper (antiparallel diode pairs) still shows measurable **even
harmonics** — in the reference build ~−47..−55 dB H2 re fundamental at high drive, in EVERY mode. An
ideal, perfectly-matched bipolar diode model produces NONE (even harmonics at the numerical floor,
−140 dB). The cause is **component tolerance**: real diodes have a forward-voltage spread between the
two antiparallel devices, and an above-mid-supply VREF bias offsets the operating point, so the real
clip thresholds are slightly asymmetric. A "perfect" analog emulation is therefore *less* faithful
than one that models the tolerance. Fix: give the symmetric pair the SAME bias-offset mechanism with a
SMALL global bias (much smaller than the dedicated "asym" mode), calibrated to the captured H2 — at
bias=0 it's bit-identical to the plain symmetric pair (`symReflect(0)=0`), so a small bias only adds
the missing even content; odd harmonics, THD, and playing-level output stay put. To DIAGNOSE: at high
drive, match the input level (a hot-reamp capture is ideal) then compare per-harmonic FFT — if the odd
harmonics already match, a "THD ceiling" is usually a *level-calibration* artifact, and the only real
gap is the missing even harmonics. Don't chase it with global EQ; it's a clipping-asymmetry effect.

### Omega accuracy gotcha (do NOT use the default omega)

chowdsp's default `Omega::omega` (omega4) uses bit-trick log/exp approximations that impose a
~−35 dB distortion floor — audible on a "transparent" pedal. Supply a custom **AccurateOmega**
provider (std::log/exp + a few Newton steps solving `w + ln(w) = x`).
**Trap:** `DiodePairT`'s `DiodeQuality::Best` path HARDCODES omega4 and ignores the provider — use
**`DiodeQuality::Good`** for the pair (eqn-18; accurate once given a true omega). `DiodeT` and the
pair's `Good` path both honour the provider. Verify with an audible-band aliasing test.

## Oversampling

- Oversample for the **nonlinear stage** (the aliasing source), but let the region SPAN any
  downstream linear stages that have audible-band HF caps (tone/recovery) — see Top-octave below.
  Only leave OUT linear stages with no audible HF caps (e.g. an input ~8 Hz HP). Pattern: give the
  oversampler a per-OS-sample `postFn` overload that runs those downstream stages, and prepare them
  at the oversampled rate.
- `juce::dsp::Oversampling`; minimum 4×, prefer 8× for clipping. Expose 1×/2×/4×/8× in the UI.
- Re-discretise every oversampled stage's caps at the oversampled rate so its response is preserved.
- Glitch-free factor switching: detect a pending change via `std::atomic<int>`, and at block start
  `reset()` + `initProcessing(maxBlock)` then update the factor (one-block gap is acceptable; do
  NOT try to crossfade an OS change).
- Consider a **separate render-time OS factor**: in `processBlock`, pick the higher factor when
  `isNonRealtime()` is true (offline bounce) — see architecture.md.

## Top-octave accuracy: bilinear cap warping near Nyquist

Linear stages run at base rate, and chowdsp's trapezoidal capacitor (companion `R = 1/(2 C fs)`) is
the bilinear transform — it bends the frequency axis, so an analog corner at `f_c` lands at a
*lower* digital frequency, the error growing toward Nyquist. Symptom: the modelled top octave is
**too dark** vs the real pedal even with tone controls flat (the reference build was ~−3.8 dB at
12 kHz / 48 kHz from a ~16 kHz treble corner + a ~7 kHz feedback corner). Diagnose by rendering the
**same signal at 2× base rate** (resample in, render, resample out) — if the deficit closes and
matches the real unit, it's warping, not a modelling error.

Two fixes, a real trade-off:
- **Prewarp the HF caps** (`utils/Prewarp.h`): replace `C` with `C·θ/tan(θ)`, `θ = π·f_c/fs`, pinning
  the corner where the real circuit has it. Zero CPU, no architecture change, no added coloration —
  it just relocates corners. Exact at the pinned corner, excellent through ~12–14 kHz, slightly soft
  right at Nyquist. Recompute per-block for a cap whose corner moves with a pot. Best for low-order,
  well-separated corners. **Only prewarp BASE-RATE linear caps** — a cap inside the oversampled
  nonlinear stage is already discretised at the high rate (the oversampler fixes its warp; prewarping
  it too would over-correct).
- **Oversample the downstream linear HF stages** (extend the nonlinear oversampling region to cover
  tone + recovery): flat to 20 kHz regardless of topology, mode-INDEPENDENT (it's a pure
  discretisation fix, so it behaves identically in every clip mode — the right answer when you need
  the top octave correct in ALL modes), and the OS factor then actually improves the top octave.
  Costs ~N× the (cheap, linear) tone/recovery CPU. Implementation: a templated `processBlock(data, n,
  postFn)` on the oversampler runs `postFn` (the downstream linear stages) per OS-sample; prepare
  those stages at `getOversampledRate()` and re-prepare on factor change. In the reference build this
  recovered ~+8 dB at 12 kHz (heavy-cut setting) and pulled 12 kHz from ~8 dB-dark to within ±2 dB of
  the real unit; at the default 4× it already ≈ the true-analog response, < 4 kHz unchanged.
  **Keep prewarp as well** — it's what fixes the top octave at the 1× (no-oversampling) setting.
  Recommended over prewarp-alone whenever the deficit is audible; prewarp-alone is the zero-CPU
  fallback. (The two are complementary, not exclusive.)

Independent of supply-voltage / rail features (those scale amplitude headroom; prewarp corrects
frequency) — the two never interact.

## ADAA (antiderivative anti-aliasing)

- ADAA is **in addition to** oversampling, not instead of it.
- Apply it where the **hardest** nonlinearity is. In the reference build the dominant aliaser was
  the **op-amp rail clip** (a hard clamp), not the soft diodes (whose fast-decaying harmonics
  oversampling already crushes). So 1st-order ADAA wrapped `railClip` (exact piecewise
  antiderivative), and diodes relied on oversampling + AccurateOmega. The chowdsp diode models also
  expose no closed-form antiderivative, so diode ADAA needs a bespoke omega-antiderivative — only
  worth it if listening reveals residual diode aliasing at low OS factors.
- 1st-order ADAA: `y = (F1(x) - F1(xPrev)) / (x - xPrev)`, with a midpoint fallback when
  `|x - xPrev|` is tiny. Update the state every sample so toggling is glitch-free.
- Reference: Esqueda et al., "Antiderivative Antialiasing in Nonlinear Wave Digital Filters",
  DAFx 2020.

## Pot tapers

- Honour the schematic's taper (audio/log vs linear). Build kits often substitute linear for cost —
  do NOT follow the kit, follow the schematic.
- See `utils/TaperUtils.h` and calibration doc §3 for the **audio-taper floor trap** on large pots.
- **The `10^(2x-2)` audio approximation is too aggressive** (only ~10% R at midpoint vs ~35-40% for
  a real audio pot) — it makes tone controls far too shallow. Prefer fitting a **power-law taper**
  (`R = Rmax * x^p`) to captures, with Rmax ≈ the schematic pot value. See calibration doc §3b. Tone
  pots inside a feedback gain-set leg are coupled to gain — re-check levels after retapering them.
- **Fit the taper SHAPE (p), and don't assume convex.** p≈1.4 (convex) is only a starting guess. A
  subtle "trim"-style tone cut can be **concave** (p<1: fast rise to a moderate R, then ~flat) — the
  reference build's treble was `~12k·x^0.4`. Tell-tale of a wrong shape (not just wrong coeff): you
  can match ONE knob position but the error flips sign at another (e.g. too bright at 9 o'clock yet
  too dark at 3 o'clock). So constrain p with **at least two** knob points across the full range.
- **Isolate a coupled control with a MATCHED-PAIR capture.** When a control only appears in captures
  alongside clipping/other controls (so the linear EQ is confounded), capture two settings that
  differ in **only that one knob**, everything else identical. The clipping/other effects are then
  identical in both and **cancel in the difference**, giving a clean differential measurement of
  that control's contribution — even from driven captures. (This rescued a treble fit that raw
  per-capture transfers couldn't, because the clean sweep wasn't actually clean at drive.)

## Signal calibration

- Anchor `kInputRef` (volts per full-scale) from a real measurement — calibration doc §1.
- Internal nominal reference: pick one (e.g. −12 dBu) and stay consistent.
- Provide input + output trims, visually distinct from the pedal controls.

## Coupled controls

- Controls sharing a network (e.g. bass + drive in one feedback web) must be modelled as a **single
  coupled WDF network**, not independent processors. Use
  `wdft::ScopedDeferImpedancePropagation` when updating several parameters at once.
