#pragma once

#include <cmath>

// Generic pot-taper and gain helpers for circuit-modelled pedal plugins.
// The first three functions are universal; the rest are WORKED EXAMPLES showing how to map a
// normalised APVTS parameter (0..1) to a WDF resistance/divider. Copy the pattern, not the
// exact values — every circuit's pot wiring differs. See docs/calibration-and-gain-staging.md
// for the hard-won lessons baked into these (especially the DRIVE floor note below).

namespace pedal::taper
{
/** dB -> linear gain. */
inline double dbToGain (double dB) { return std::pow (10.0, dB / 20.0); }

/** Audio (log) taper approximation: R = Rmax * 10^(2x - 2), x in [0,1] => Rmax/100 .. Rmax.
 *  NOTE THE 1% FLOOR: at x=0 this returns Rmax/100, NOT 0. Fine for small pots, but a TRAP for
 *  large ones — see audioTaperR0 and driveResistanceExample below. Use for audio-taper rheostats. */
inline double audioTaperR (double x, double rMax)
{
    if (x <= 0.0)
        return rMax * 0.01;
    if (x >= 1.0)
        return rMax;
    return rMax * std::pow (10.0, 2.0 * x - 2.0);
}

/** Audio taper anchored to 0 at minimum: same curve shape, but x=0 -> 0 ohm exactly.
 *  USE THIS for any pot whose physical minimum is ~0 ohm AND whose Rmax is large enough that the
 *  1% floor of audioTaperR injects an audible resistance. On a 1M feedback pot the 1% floor =
 *  10k, which added ~7.7 dB of phantom minimum-gain in the reference build (the diodes/op-amp
 *  then overdrove far too early). This was a real, hard-to-spot bug — prefer this for gain pots. */
inline double audioTaperR0 (double x, double rMax)
{
    if (x <= 0.0)
        return 0.0;
    if (x >= 1.0)
        return rMax;
    return rMax * (std::pow (10.0, 2.0 * x - 2.0) - 0.01) / 0.99;
}

/** Power-law taper: R = rMax * x^p.  ** Often the BEST model for a real audio pot. **
 *  The 10^(2x-2) audio approximation above is frequently TOO AGGRESSIVE — it puts only ~10% of R
 *  at the midpoint, where a real audio pot sits nearer ~35-40%. In the reference build this made
 *  the tone controls (which set audible corner frequencies) far too shallow. Fitting the measured
 *  corner-vs-knob from pedal captures gave a clean power law with rMax ~= the SCHEMATIC pot value
 *  (the pot/cap were right — only the taper CURVE was wrong).
 *
 *  ** FIT THE SHAPE (p), NOT JUST THE MAGNITUDE. ** p > 1 is CONVEX (slow start, fast end — the
 *  usual "audio" feel). But a real control can be CONCAVE (p < 1: fast rise then ~flat) — e.g. a
 *  subtle "trim"-style tone cut that engages early and barely deepens after. In the reference build
 *  the treble cut was concave (~12k * x^0.4): convex laws were wrong in SHAPE no matter the coeff —
 *  they under-cut at low settings AND over-cut wildly at the top. Symptom of wrong shape: you can
 *  match one knob position but not two. So sample at least TWO knob points and fit p to both; don't
 *  assume convex. p~1.4 is a fine STARTING point for an audio pot, p=1 linear, p<1 concave. */
inline double powerLawTaper (double x, double rMax, double p = 1.43)
{
    if (x <= 0.0)
        return 0.0;
    return rMax * std::pow (x, p);
}

// ---------------------------------------------------------------------------------------------
// WORKED EXAMPLES — adapt to your schematic. Direction (x vs 1-x) and Rmax come from the circuit.
// ---------------------------------------------------------------------------------------------

/** EXAMPLE: a gain/drive pot in an op-amp feedback leg (more R = more gain). Anchored to 0 at
 *  min because it is a large (e.g. A1M) pot — DO NOT use the floored audioTaperR here. */
inline double driveResistanceExample (double x) { return audioTaperR0 (x, 1.0e6); }

/** EXAMPLE: a tone-CUT control (knob up = more cut). Cut-only controls map x->R directly
 *  (x=0 = no cut). Prefer the power-law taper fit to captures over the audio approximation. Fit the
 *  SHAPE p to >=2 knob points (see powerLawTaper note): the reference build's treble cut turned out
 *  CONCAVE (~12k * x^0.4), not the convex p~1.4 first assumed — a gentle high-cut that engages early
 *  then plateaus. p shown as 1.43 here only as a placeholder; measure it. */
inline double cutControlExample (double x) { return powerLawTaper (x, 12.0e3, 0.4); }

/** EXAMPLE: a passive output volume pot as a voltage divider (returns 0..1 gain).
 *  Generic shape: split Rtotal into upper/lower arms by the (tapered) wiper fraction, optionally
 *  with a fixed shaping resistor across one arm. Output = wiper / input.
 *  A passive pot can only ATTENUATE: max rotation = unity passthrough, everything below < unity. */
inline double volumeGainExample (double x)
{
    constexpr double rTotal = 25.0e3, rShape = 7.5e3; // rShape across the upper arm (optional)
    const double frac = (x <= 0.0) ? 0.0 : std::pow (10.0, 2.0 * x - 2.0); // audio law 0.01..1
    const double rLow = frac * rTotal;              // wiper -> GND
    const double rUp = (1.0 - frac) * rTotal;       // top -> wiper
    const double rUpPar = (rUp * rShape) / (rUp + rShape);
    return rLow / (rUpPar + rLow);
}
} // namespace pedal::taper
