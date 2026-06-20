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
    // BATCH 3+4 RE-FIT (2026-06-20, PRIMARY pedal). The real Timmy treble is a GENTLE high-cut
    // across its whole rotation, NOT the dramatic darkening a convex audio taper produces. Earlier
    // convex power laws were wrong in SHAPE: 70k*x^1.43 over-cut by ~5 dB @8k by x=0.35; 50k*x^1.8
    // under-cut at x=0.20 (+4 dB) yet still over-cut at the top. Two reliable measurements pin it:
    //   - batch 4 (clock matrix): real TREB_R ≈ flat ~7k across x=0.20..0.35 (drive-independent
    //     Soft-mode 8k shelf: real +0.5 dB @0.20, -1.1 dB @0.35).
    //   - batch 3 MATCHED PAIR (G3 V4 B8, only treble differs T5->T8): real adds only ~2 dB more
    //     cut @8k from x=0.5->0.8, vs ~7 dB for the old taper -> taper far too steep up top.
    // A CONCAVE law 12k*x^0.4 (fast rise to ~6k by x=0.2, then ~flat to 12k at full) matches both:
    // batch-4 8k within ~0.85 dB at 0.20 & 0.35, batch-3 pair incremental within ~0.4 dB. Max cut
    // ~12k (corner ~1.2 kHz) is musical, not the old 50k/612 Hz over-cut. (A treble-INDEPENDENT
    // baseline ~-3.8 dB @12k deficit remains — Stage 2 C11 + bilinear cap warp near Nyquist.)
    return 12.0e3 * std::pow (x, 0.4);
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
