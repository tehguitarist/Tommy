#pragma once

#include <cmath>

namespace tommy::taper
{
/** dB -> linear gain. */
inline double dbToGain (double dB) { return std::pow (10.0, dB / 20.0); }

/** Audio (log) taper approximation: R = Rmax * 10^(2x - 2), x in [0,1] => Rmax/100 .. Rmax.
 *  (dsp.md). Used for the rheostat controls. */
inline double audioTaperR (double x, double rMax)
{
    if (x <= 0.0)
        return rMax * 0.01;
    if (x >= 1.0)
        return rMax;
    return rMax * std::pow (10.0, 2.0 * x - 2.0);
}

// --- Control-to-WDF mappings. Directions chosen so the knob does the musical thing; curves are
//     placeholders to refine subjectively at Step 9. ---

/** BASS knob up => more low end => SMALLER gain-set resistance (more C4 path). Rmax = 50k. */
inline double bassResistance (double x) { return audioTaperR (1.0 - x, 50.0e3); }

/** DRIVE knob up => more gain => LARGER feedback resistance. Rmax = 1M (A1M pot). */
inline double driveResistance (double x) { return audioTaperR (x, 1.0e6); }

/** TREBLE knob up => more treble => LESS cut => SMALLER series resistance.
 *  TREB is a rheostat wired ~0..25k (A50k, wiper jumpered to pin 3). */
inline double trebleResistance (double x)
{
    // Pot arm Ra (pin1->wiper), audio taper of the *cut* amount; effective R = Ra || 50k.
    const double ra = audioTaperR (1.0 - x, 50.0e3);
    return (ra * 50.0e3) / (ra + 50.0e3); // ~0..25k
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
