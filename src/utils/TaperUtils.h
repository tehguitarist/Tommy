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
    // seen across the capture set. NOTE the 60 Hz cut is only weakly sensitive to this coefficient
    // (the deep-LF cut is dominated by C3/C4, not the pot R), so this is a fine trim, not a big lever.
    // BASS is unaffected by the V4 treble change.
    return 50.0e3 * std::pow (x, 2.41);
}

/** DRIVE knob up => more gain => LARGER feedback resistance. Rmax = 1M (A1M pot).
 *  TAPER (corrected 2026-06-19): like treble/bass, the 10^(2x-2) audio approximation was too
 *  aggressive — it under-drove the mid of the sweep, so the plugin clipped far less than the real
 *  pedal there (THD 10.6% vs 16.6% at drive 10:30). Fitting THD-vs-drive to the gain-sweep
 *  captures gives a gentler power law 1e6 * x^2.2, which matches mid-drive THD within ~1% (clean
 *  stays clean; full drive = 1M unchanged). (Drive's exponent ~2.2 > treble/bass ~1.43 — the A1M
 *  pot's taper differs from the A50k tone pots.) NOTE: at full drive the plugin's THD caps ~3-4%
 *  below the real pedal (clipping-character ceiling, not gain — see project notes). */
inline double driveResistance (double x)
{
    if (x <= 0.0)
        return 0.0;
    return 1.0e6 * std::pow (x, 2.2);
}

/** TREBLE knob up (x->1) => MORE cut (darker). TREB feeds the R5(1k)/C5(10n) low-pass;
 *  more series R => lower corner => more HF cut. x=0: R=0 => corner ~15.9 kHz (no cut).
 *
 *  TAPER — CONVEX, matched to BASS (2026-07-05): identical formula to `bassResistance`
 *  (50k * x^2.41), replacing the earlier V4 linear-pot rheostat law (`50k*x/(x+1)`, R_eff =
 *  Ra ∥ (Ra+Rb) for the real linear pot's wiper-jumpered rheostat — see circuit.md), which was
 *  front-loaded: ~70% of the total cut landed in the first 30% of knob travel, then flattened out.
 *  The convex law inverts that feel — barely perceptible for roughly the first third of travel,
 *  cutting hard only near the top.
 *
 *  IMPORTANT PROVENANCE NOTE: independently re-deriving a taper directly from the pedal2 captures
 *  (fitting TREB_R via offline_render overrides against each capture's own B/G/mode, isolating
 *  >2kHz to sidestep BASS coupling) gave x=0.20 -> R~=8950, x=0.35 -> R~=12900 (RMS fit error
 *  <0.35 dB) — a CONCAVE curve (exponent ~0.65) landing almost exactly on the old V4 law at every
 *  knob position, not on this convex one. So the pedal2 capture set itself supports the old
 *  concave/front-loaded law, not this one. This convex law is shipped anyway on the strength of
 *  the user's own independent physical-pedal measurement (2026-07-05), which the user judges to
 *  support the slower/convex feel over what pedal2 implies — treat this as a deliberate,
 *  user-confirmed choice, NOT a hardware-accuracy fit to the in-repo capture data. If pedal2-style
 *  validation ever needs to pass again, the concave law is the one to restore (either the old
 *  `50k*x/(x+1)`, or the freshly re-derived `25611*x^0.653`, whichever fits better next time).
 */
inline double trebleResistance (double x)
{
    if (x <= 0.0)
        return 0.0;
    return 50.0e3 * std::pow (x, 2.41);
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
