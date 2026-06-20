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
    // BATCH-3 RE-FIT (2026-06-21, PRIMARY pedal). The 50k*x^1.43 law over-cut bass by ~2x: at the
    // measured points it wanted ~half the resistance (x=0.6 -> ~12k not 23.8k; x=0.8 -> ~24k not
    // 36.3k), i.e. the plugin cut ~1-1.8 dB too much LF. Back-fitting BASS_R to the real 60/120 Hz
    // cut (normalised @250 Hz, so drive/level cancels) over the clean-drive G3 captures gives
    // 41k*x^2.41 (matches 60 & 120 Hz to ~±0.5 dB at x=0.6 and ~±1 dB at x=0.8). Only two distinct
    // bass settings (0.6, 0.8) were available and the x=0.8 captures scatter ~22-30k, so the
    // exponent is loosely constrained — this is a best-estimate, not a tight fit. See NEXT STEPS.
    return 41.0e3 * std::pow (x, 2.41);
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
    // BATCH-3 RE-FIT (2026-06-21, PRIMARY pedal) — SUPERSEDES the 12k*x^0.4 "gentle concave" law,
    // which was WRONG (it left the plugin +6..+12 dB too BRIGHT at 4 kHz vs the real pedal). The
    // 2026-06-20 fit confused the small INCREMENTAL cut from the matched pair (T5->T8 only adds
    // ~2.5 dB @8k) with a gentle taper -- but a 1st-order LP's 8 kHz attenuation SATURATES once the
    // corner drops below ~800 Hz, so that same small increment occurs at HIGH R too. The ABSOLUTE
    // level disambiguates: real 8k = -16 dB at x=0.5 needs TREB_R ~20k, not ~9k.
    //   Back-fitting TREB_R to the real 4k & 8k cut (normalised @250 Hz) over the consistent-drive
    //   G3 captures gives monotonic points: x=0.4->16k, x=0.5->20k, x=0.8->25k. (The x=0.2 point is
    //   excluded -- it's at a different drive, G4, and is the "non-monotonic treble" outlier flagged
    //   earlier.) Log-log fit -> 29k*x^0.625. This matches 60 Hz..8 kHz to ~±1-2 dB.
    //   LIMITATION: matching 4k/8k forces a low corner (~530-750 Hz), which then over-darkens 12 kHz
    //   by ~5-8 dB -- the real pedal's top octave rolls off GENTLER than the plugin's (treble LP +
    //   Stage 2 C11 + bilinear warp) single-pole-ish stack. That is an HF-SHAPE (circuit-model)
    //   limit, NOT a taper limit; no single R fixes it. Top octave is the least audible band and was
    //   accepted as "close, not perfect". The 29k at x=1 slightly exceeds the ideal A50k rheostat
    //   max (~25k) -- it's an EFFECTIVE value absorbing the total measured HF rolloff. See NEXT STEPS.
    return 29.0e3 * std::pow (x, 0.625);
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
