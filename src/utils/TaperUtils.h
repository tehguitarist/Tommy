#pragma once

#include <cmath>

namespace tommy::taper
{
/** dB -> linear gain. */
inline double dbToGain (double dB) { return std::pow (10.0, dB / 20.0); }

/** Audio (log) taper approximation: R = Rmax * 10^(2x - 2), x in [0,1] => Rmax/100 .. Rmax.
 *  (dsp.md). NOTE the 1% floor at x=0 — a trap for large/HF-critical pots (see audioTaperR0). */
inline double audioTaperR (double x, double rMax)
{
    if (x <= 0.0)
        return rMax * 0.01;
    if (x >= 1.0)
        return rMax;
    return rMax * std::pow (10.0, 2.0 * x - 2.0);
}

/** Audio taper anchored to 0 at minimum: same curve shape, x=0 -> 0Ω exactly. Use for pots whose
 *  physical minimum is ~0Ω and where the 1% floor of audioTaperR is audible (DRIVE gain, TREBLE
 *  cut corner). */
inline double audioTaperR0 (double x, double rMax)
{
    if (x <= 0.0)
        return 0.0;
    if (x >= 1.0)
        return rMax;
    return rMax * (std::pow (10.0, 2.0 * x - 2.0) - 0.01) / 0.99;
}

// --- Control-to-WDF mappings. ---
// BASS and TREBLE are CUT controls: knob UP (x->1) = MORE cut (this is the intended pedal feel).
// x=0 (CCW) = no cut / full band; x=1 (CW) = maximum cut.
// (The MXR-Timmy NAM captures used for tuning happen to have the OPPOSITE knob direction, so they
// were used only to fit the cut DEPTH/curve — at the symmetric noon point direction is irrelevant —
// not the direction.) DRIVE and VOLUME behave conventionally (up = more).

/** BASS knob up => bass CUT => LARGER gain-set resistance (less C4 path to AC ground).
 *  x=0: ~0Ω => C4 strongly shunts node_X => full low end (no cut). x=1: ~50kΩ => max bass cut.
 *  TAPER: same correction as treble (2026-06-19). The audio approximation 10^(2x-2) gave too
 *  little resistance, leaving +1.5..+2.9 dB too much bass vs the captures (bass boost H(60)-H(500)).
 *  The gentler measured power law 50k * x^1.43 (schematic A50k pot) matches the captured bass to
 *  within ~0.5 dB at mid settings. NOTE: bass sits in Stage 1's gain-set leg, so this also slightly
 *  lowers LF gain at bass-noon — re-check overall level by ear (midband-anchored calibration held
 *  in analysis, but confirm). */
inline double bassResistance (double x)
{
    if (x <= 0.0)
        return 0.0;
    // BATCH 3+4 FIT (2026-06-21, PRIMARY pedal). The old 50k*x^1.43 law over-cut bass by ~2x. Back-
    // fitting BASS_R to the real 60/120 Hz cut (normalised @250 Hz, so drive/level cancels) gives the
    // CONVEX 50k*x^2.41. The real bass cut is ~flat (~1 dB @60 Hz) from x=0..0.65 then ramps to
    // ~3.3 dB by x=0.8 — a strongly convex CUT response. (Physically the bass POT is reverse-log like
    // treble, but it sits in Stage 1's gain-set leg whose nonlinear R->cut transfer INVERTS the
    // concavity into this convex cut-vs-rotation — so convex is correct here even though the pot
    // itself isn't.) Coefficient is 50k (= the A50k pot's nominal max; bumped from a 41k fit) — it
    // tightens 60 Hz at x=0.8 from +0.8 to +0.1 dB vs real and shaves the small residual bright bias
    // seen across the capture set.
    // ⚠️ CORRECTION (2026-07-27, v1.4 W4): this comment used to claim "the 60 Hz cut is only weakly
    // sensitive to this coefficient (the deep-LF cut is dominated by C3/C4, not the pot R), so this
    // is a fine trim, not a big lever." That is WRONG at 60 Hz and it discouraged a lever that
    // should have been checked. Measured from the shipped analytic Stage-1 gain (64 Hz re 1 kHz):
    //     B0.50/D0.35:  BASS_R  4.7k -> -2.73 dB |  9.4k (shipped) -> -5.66 |  18.8k -> -9.40
    //     B0.65/D0.65:  BASS_R  8.9k -> -5.86 dB | 17.7k (shipped) -> -10.32 | 35.4k -> -14.81
    // i.e. ~3-4 dB per doubling of R — a STRONG lever at 60 Hz, not a fine trim. C3/C4 dominate
    // only much lower (~20 Hz), which is where the original observation must have come from.
    // BASS is unaffected by the V4 treble change.
    return 50.0e3 * std::pow (x, 2.41);
}

/** DRIVE knob up => more gain => LARGER feedback resistance. Rmax = 1M (A1M pot).
 *  TAPER: 1e6 * x^2.75. Power law throughout; only the exponent has ever moved. History:
 *  the original 10^(2x-2) audio approximation under-drove the mid of the sweep, refitted
 *  2026-06-19 to x^2.2 against the batch-3/4/5 gain-sweep captures by matching mid-drive THD.
 *
 *  RE-FITTED 2026-07-27 (v1.4 W2), 2.2 -> 2.75, against pedal2 — the definitive tone reference.
 *  The 2.2 fit predates BOTH v1.2.1's kIs halving (which lowered the diode threshold, i.e. moved
 *  clip onset EARLIER) and v1.4 W1's Medium threshold, so it was matching mid-drive THD through a
 *  clipper that has since changed twice; and it was fitted at mid drive only, where THD saturates
 *  and is nearly blind to pre-clip gain. The low-drive corner it left behind was v1.4 W2: at
 *  D0.20/-18 dBFS the plugin distorted ~4.4x the pedal (11.3% vs 2.55% at 101 Hz), the largest
 *  single error in the pedal2 dataset and squarely in the edge-of-breakup region.
 *
 *  The error is MODE-INDEPENDENT (at -18 dBFS, D0.35: Soft +1.0 / Hard +1.4 / Medium +2.8 dB, and
 *  the ordering follows each mode's overdrive MARGIN, not its diode parameters), which is what
 *  points at the shared pre-clip gain law rather than at the diodes. See
 *  analysis/w2_clip_onset.py — probe 2 shows the whole dataset sits 8-40 dB past clip onset except
 *  D0.20/-18 at +5.4 dB, so this is the ONLY region where pre-clip gain is observable at all;
 *  everywhere else THD has saturated. Fitted by sweeping the exponent over all 16 pedal2 captures
 *  x 3 sweep depths (probe 3b):
 *      exp:              2.2(was)   2.5    2.6    2.7   2.75   2.8    3.0
 *      rms dTHD D<=0.20    7.10    4.37   3.05   1.39   0.65   1.10   6.46
 *      rms dTHD D>=0.35    0.71    0.46   0.43   0.43   0.45   0.50   0.84
 *  2.75 minimises the joint cost, and note the well-sampled D >= 0.35 region IMPROVES (0.71 ->
 *  0.45) rather than merely surviving — the evidence is four captures (Hard D0.20 plus D0.35 in
 *  all three modes), not the single D0.20 one, which is what makes this defensible under W2's
 *  "D0.20 appears once and no further captures exist" constraint.
 *
 *  Deliberately NOT a diode-parameter change: global kIs is v1.2.1's high-drive LEVEL fix and
 *  pulls the opposite way, and Hard's kAsymMismatch was shown to move H2 without moving low-drive
 *  THD (probe 3a). x=1 is unchanged at 1M, so full drive is bit-identical.
 *  Physically 2.75 puts the pot at 15% of Rmax at mid-rotation vs 2.2's 22% — squarely inside the
 *  10-20% range real A-taper pots specify, so it is not a strained value. */
inline double driveResistance (double x)
{
    if (x <= 0.0)
        return 0.0;
    return 1.0e6 * std::pow (x, 2.75);
}

/** TREBLE knob up (x->1) => MORE cut (darker). TREB rheostat feeds the R5(1k)/C5(10n) low-pass;
 *  more series R => lower corner => more HF cut. x=0: R=0 => corner ~15.9 kHz (no cut).
 *
 *  TAPER (corrected 2026-06-19): the generic audio approximation 10^(2x-2) was far too aggressive
 *  (only 10% of R at the midpoint), giving much too little cut. Extracting the treble corner vs
 *  knob from the NAM captures and fitting the actual plugin RENDER (not just a 1st-order estimate)
 *  to the real pedal gives a clean power law:
 *      TREB_R ≈ 70k * x^1.43
 *  which matches the captured 8 kHz cut to within ~0.3 dB from no-cut through the noon depth. The
 *  exponent (taper SHAPE) is the key correction; the ~70k range is close to the schematic 50k pot
 *  (the pot/cap/topology were right — only the taper curve was wrong). A real audio-ish taper
 *  (slow start) but much gentler than 10^(2x-2): ~37% of R at the midpoint, not 10%. NOTE: the same
 *  over-aggressive-audio-approx caveat may apply to BASS/DRIVE if they later need tuning.
 *  (x>0.5 is extrapolated — the captures only reached the noon cut depth.) */
inline double trebleResistance (double x)
{
    if (x <= 0.0)
        return 0.0;
    if (x >= 1.0)
        return 25.0e3;
    // V4 TREBLE (2026-06-21, user-chosen final state) — LINEAR (B) 50k pot. Later "V4" Timmy units
    // changed the treble pot from audio (A, reverse-wired) to LINEAR to remove a 7-10 o'clock dead
    // spot (web research; see timmy-pot-taper-research memory). Modelled as the genuine linear-pot
    // RHEOSTAT law (wiper jumpered to pin 3, per circuit.md): R_eff = Ra ∥ (Ra+Rb) with Ra=50k*x and
    // Ra+Rb=50k  ->  50k*x ∥ 50k = 50k*x/(x+1). Naturally R(0)=0 (no cut at CCW) and R(1)=25k (the
    // physical rheostat max; corner ~612 Hz). Note it's still mildly concave from the ∥ loading.
    //   ACCURACY TRADE (accepted by user): our batch-3 captures (which look like an EARLY reverse-log
    //   unit) want a bit MORE cut at low-mid treble (x=0.4->16k, 0.5->20k, 0.8->25k); this linear law
    //   gives 14.3k/16.7k/22.2k, i.e. ~1-2 dB BRIGHTER at low-mid treble vs those captures. That's the
    //   known cost of matching the V4 (linear) pedal rather than the early-unit captures. (The earlier
    //   capture-fit law was 29k*x^0.625 concave, kept here for reference if we revert to an early unit.)
    //   The top-octave HF-SHAPE deficit (12k) is a separate circuit-model limit, not the taper.
    return 50.0e3 * x / (x + 1.0);
}

/** VOLUME divider gain (A25K with R11 across the upper section). x = rotation 0..1.
 *  Output = wiper voltage / input. Models R11 in parallel with the upper arm.
 *  V4 (2026-06-21): R11 = 18k. Later "V4" Timmy units set the volume to 25kA + an 18k resistor from
 *  input→output (= across the pot's upper arm = our R11) to smooth the taper / fix unity-gain
 *  position (web research, timmy-pot-taper-research memory). The repo schematic shows 7k5 (an earlier
 *  revision); 18k is the V4 value the user is targeting. Affects volume-knob taper/level, not tone. */
inline double volumeGain (double x)
{
    constexpr double rTotal = 25.0e3, r11 = 18.0e3;
    const double frac = (x <= 0.0) ? 0.0 : std::pow (10.0, 2.0 * x - 2.0); // audio law, 0.01..1
    const double rLow = frac * rTotal;             // wiper -> GND
    const double rUp = (1.0 - frac) * rTotal;      // node_K -> wiper
    const double rUpPar = (rUp * r11) / (rUp + r11); // R11 || upper arm
    return rLow / (rUpPar + rLow);
}
} // namespace tommy::taper
