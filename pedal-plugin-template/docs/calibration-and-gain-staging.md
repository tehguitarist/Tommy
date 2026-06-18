# Calibration & Gain Staging — Hard-Won Lessons

This is the single most valuable document in the template. Every item here cost real debugging
time on the reference build. Read it before wiring up `processBlock` and before trying to "tune
by ear", or you will chase ghosts.

---

## 1. The core problem: DAW full-scale has no inherent voltage

A DAW hands you a normalised float, nominally [−1, 1] = "full scale." **Full scale carries no
physical unit.** Your WDF circuit, however, is built from real component values and cares about
**actual volts** — the diodes clip around 0.3–0.6 V, op-amp rails sit at a few volts. So you must
bridge two reference frames:

```
DAW float ──×K──▶ [circuit, in real volts] ──×(1/K)──▶ DAW float
```

`K` = **volts per full-scale** (`kInputRef`). Apply `K` going in, `1/K` coming out. Do this
symmetrically and `K` cancels in the *linear* path — so it changes **only where the nonlinearity
engages**, never the clean-signal level or the unity-gain point.

### Why it matters most for nonlinear circuits

Because the circuit is nonlinear, the **absolute** input level sets where clipping happens:
- `K` too small → the signal never reaches the diodes/rails → sounds sterile, "no drive".
- `K` too large → clips immediately → no clean range, overdriven at minimum gain.

Getting `K` right is the difference between a faithful drive response and a toy.

### How to calibrate K (measure, don't guess)

1. Play your hardest into your interface's Hi-Z input **at 0 / minimum gain**.
2. Note the peak in the DAW (dBFS) and, if available, the peak voltage.
3. `K = peak_volts / peak_float`, where `peak_float = 10^(dBFS/20)`.

Reference build example: a humbucker peaked at **0.7 V** reading **−13.4 dBFS** (= 0.214 float),
giving **K ≈ 0.7 / 0.214 ≈ 3.27 V/full-scale**. That implied the interface mapped ~3.27 V peak to
0 dBFS at 0 gain — a realistic Hi-Z D.I. sensitivity, so it cross-checked.

Forget dBu. Work in **volts ↔ dBFS** only. (For reference, 0 dBu = 0.775 Vrms, so "−12 dBu = 1 V"
is wrong by ~12 dB — a common conflation. Don't anchor to dBu.)

### Implementation

```cpp
// header: pick from your measurement
static constexpr float kInputRef = 3.27f; // volts per full-scale

// processBlock — scale into the circuit, but keep the meter + bypass dry path in DAW domain:
work[i] = (double) wet * kInputRef;        // wet = in[i] * inputTrimGain
// ... run WDF chain (now in real volts) ...
// fold 1/kInputRef into the output gain so it cancels in the linear path:
outputGain = kOutputMakeup * volumeGain * dbToGain(outTrim) / kInputRef;
```

Keep the **input meter** and the **bypass dry copy** in DAW domain (do NOT scale them by `K`),
so metering and true-bypass passthrough stay honest.

---

## 2. Output makeup: should be ~1.0, used as a headroom pad

With `K` anchored at both ends, the **physically-honest** makeup multiplier is **1.0**: the output
float then represents the real circuit output voltage at the same scale as the input. The circuit's
own gain sets where unity lands on the volume sweep — you are NOT forcing it.

So why deviate from 1.0 at all? **Headroom.** A drive circuit genuinely amplifies (an op-amp
recovery stage is often +6 dB), so the loudest internal voltage (the rail, e.g. ~3.4 V) maps to
`3.4 / K` at the output. If that exceeds 1.0 it ticks over 0 dBFS:

| makeup | worst-case peak (rail 3.4 V, K 3.27) |
|--------|--------------------------------------|
| 1.0    | +0.34 dBFS  (clips)                  |
| 0.9    | −0.6 dBFS   (honest to ~1 dB, safe) |
| 0.8    | −1.6 dBFS   (comfortable)           |

**Use ~0.9**: closest to real behaviour while guaranteeing the output never exceeds 0 dBFS. It is a
deliberate ~1 dB safety pad, **not** a calibration crutch. Tune within 0.8–1.0 to taste.

> The makeup is the ONLY legitimately non-circuit scalar in the whole chain. If you find yourself
> needing it far from 1.0 to get unity, your `kInputRef` or a taper is wrong — fix that, not this.

---

## 3. The DRIVE taper floor bug (read this — it's subtle)

A generic audio-taper helper that floors at 1% of max (`R = Rmax * 10^(2x-2)`, clamped at x=0 to
`Rmax/100`) is fine for small pots but **injects phantom resistance on large ones**. On a 1 MΩ
feedback (drive) pot, 1% = **10 kΩ** of feedback resistance present even at minimum — but a real
pot reaches ~0 Ω fully CCW.

Measured impact on the reference build: minimum-drive gain was **8.96× (19 dB)** instead of the
correct **3.71× (11.4 dB)** — **7.7 dB of phantom gain**, which made the pedal overdrive far too
early (only got clean if you trimmed −12 dB at the input).

**Fix:** anchor large gain pots to 0 Ω at minimum (`audioTaperR0` in `TaperUtils.h`):
```cpp
R(x) = Rmax * (10^(2x-2) - 0.01) / 0.99;   // x=0 -> 0, x=1 -> Rmax, shape preserved
```
The full-drive end is unchanged; only the bottom of the sweep is corrected.

**General rule:** whenever a pot's physical minimum is ~0 Ω, verify your taper actually returns ~0
there. Print `taper(0.0)` and sanity-check it against the schematic.

---

## 4. Output load: almost never worth modelling

A passive output volume pot feeding a high-impedance destination (guitar amp / Hi-Z interface
input, ~1 MΩ) loses essentially nothing:
- Worst-case pot source impedance ~6 kΩ into 1 MΩ → divider loss **−0.05 dB** (−0.1 dB even into
  470 kΩ). Inaudible at any volume position.
- Output coupling cap (e.g. 1 µF) into 1 MΩ → high-pass corner ~0.16 Hz. Inaudible.
- Source impedance into cable capacitance → treble corner ~50 kHz. Inaudible.

So model the volume pot as an **unloaded** divider and move on. Output loading only matters feeding
something <50 kΩ, which guitar gear never presents. **Input** load needs calibrating (§1);
**output** load does not.

---

## 5. Internal clipping vs output clipping

- **Internally there is no digital-clipping risk.** The WDF chain runs in the **volts domain**
  (double precision; float in the oversampler) — single-digit numbers with ~38 orders of magnitude
  of headroom. The signal is bounded to a few volts by the **modelled op-amp rails** — that
  bounding *is* the intended analog clipping, not a numeric artifact. Nothing inside can overflow.
- **The only place a sample can exceed 0 dBFS is the final write back to the DAW.** And because
  that path is floating-point, a >1.0 sample is **not destroyed in-plugin** — it leaves intact and
  only audibly clips at a downstream fixed-point boundary (interface DAC, fixed-bit bounce, or a
  hard ceiling). Keeping makeup ≤ 0.9 (§2) ensures even that never happens.

Conclusion: spend zero effort on internal headroom; spend a little on the output ceiling.

---

## 6. Op-amp output rails (not rail-to-rail)

On a typical 9 V pedal supply (≈8.3 V at V+, VREF ≈ 4.6 V), a non-rail-to-rail op-amp swings only
to within ~1–2 V of its rails. Model this as an **asymmetric output saturation** (positive rails
first when bias sits above mid-supply), e.g. **+2.5 / −3.4 V** from VREF in the reference build.

Model shape that matched a real op-amp output stage: **dead-linear until ~0.35 V before the rail, a
short parabolic knee, then a HARD clamp** — a real output transistor saturates hard, NOT a gentle
`tanh`. Expose `setRailVoltages()` / `setRailClampEnabled()`. Absolute values are estimates (±0.5 V)
unless you have a scope/SPICE — refine by ear. **Beware compounding gain:** a +6 dB recovery stage
can try to drive a downstream node to 2× the previous rail (physically impossible on 9 V) — clamp
each op-amp's output, and measure the worst-case node before assuming.

---

## 7. VU meter idle-noise gate

At the unity volume setting, output ≈ input, so the meter shows the **source's idle noise floor**
(guitar hum + interface noise), which the pedal's gain makes visible on the lowest segment. Clamp
sub-threshold levels to zero in the meter timer so it reads clean silence:

```cpp
static constexpr float kNoiseFl = 2e-3f; // ~-54 dBFS: clears idle hum, far below any real playing
if (level < kNoiseFl) level = 0.0f;
```

~−54 dBFS clears typical idle noise yet sits well below even soft playing, so nothing audible is
masked. If you change the output makeup, the idle floor moves with it — re-check this threshold.

---

## 8. Quick pre-flight checklist for a new build

- [ ] `kInputRef` measured from YOUR interface + pickups, not copied blindly.
- [ ] Every pot taper sanity-checked at x=0 and x=1 against the schematic (esp. 0 Ω minimums).
- [ ] Makeup ≈ 0.9; verify the loudest setting (full drive + full volume) peaks < 0 dBFS.
- [ ] Op-amp rails clamped on every op-amp output; worst-case node measured.
- [ ] Cut controls map x→cut (knob up = more cut), not inverted.
- [ ] VU idle gate re-checked after the final makeup value.
- [ ] `kInputRef` and makeup decoupled: changing input load must NOT move the unity point.
