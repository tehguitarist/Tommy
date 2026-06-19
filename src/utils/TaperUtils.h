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
    return 50.0e3 * std::pow (x, 1.43);
}

/** DRIVE knob up => more gain => LARGER feedback resistance. Rmax = 1M (A1M pot).
 *  Anchored to 0Ω at minimum: a real A1M pot reaches ~0Ω fully CCW, but the generic audioTaperR
 *  floors at 1% of max = 10kΩ here — enough feedback to add ~7.7 dB of phantom minimum-drive gain
 *  (measured: 8.96x vs 3.71x at min drive), making the pedal overdrive far too early. This shifts
 *  the audio-taper curve so x=0 -> 0Ω while preserving its shape in the usable range (x=1 -> 1M). */
inline double driveResistance (double x) { return audioTaperR0 (x, 1.0e6); }

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
    return 70.0e3 * std::pow (x, 1.43);
}

/** VOLUME divider gain (A25K with R11 7k5 across the upper section). x = rotation 0..1.
 *  Output = wiper voltage / input. Models R11 in parallel with the upper arm. */
inline double volumeGain (double x)
{
    constexpr double rTotal = 25.0e3, r11 = 7.5e3;
    const double frac = (x <= 0.0) ? 0.0 : std::pow (10.0, 2.0 * x - 2.0); // audio law, 0.01..1
    const double rLow = frac * rTotal;             // wiper -> GND
    const double rUp = (1.0 - frac) * rTotal;      // node_K -> wiper
    const double rUpPar = (rUp * r11) / (rUp + r11); // R11 || upper arm
    return rLow / (rUpPar + rLow);
}
} // namespace tommy::taper
