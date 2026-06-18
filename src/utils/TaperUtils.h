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

// --- Control-to-WDF mappings. ---
// BASS and TREBLE are CUT-only controls (confirmed from real pedal, 2026-06-18):
//   Knob at 0 (CCW) = natural circuit state, no additional cut.
//   Knob at max (CW) = maximum cut. Neither knob ever boosts above its CCW reference.
// DRIVE and VOLUME behave conventionally (up = more).

/** BASS knob up => bass CUT => LARGER gain-set resistance (less C4 path to AC ground).
 *  At CCW (x=0): ~500Ω → C4 (1µF) strongly shunts node_X → maximum inherent bass character.
 *  At CW (x=1): 50kΩ → C4 path largely blocked → relative bass cut. Rmax = 50k (A50k). */
inline double bassResistance (double x) { return audioTaperR (x, 50.0e3); }

/** DRIVE knob up => more gain => LARGER feedback resistance. Rmax = 1M (A1M pot).
 *  Anchored to 0Ω at minimum: a real A1M pot reaches ~0Ω fully CCW, but the generic audioTaperR
 *  floors at 1% of max = 10kΩ here — enough feedback to add ~7.7 dB of phantom minimum-drive gain
 *  (measured: 8.96x vs 3.71x at min drive), making the pedal overdrive far too early. This shifts
 *  the audio-taper curve so x=0 -> 0Ω while preserving its shape in the usable range (x=1 -> 1M). */
inline double driveResistance (double x)
{
    if (x <= 0.0) return 0.0;
    if (x >= 1.0) return 1.0e6;
    return 1.0e6 * (std::pow (10.0, 2.0 * x - 2.0) - 0.01) / 0.99;
}

/** TREBLE knob up => treble CUT => LARGER series resistance in the TREB/R5/C5 low-pass.
 *  TREB is a rheostat wired as Ra || 50k (wiper jumpered to pin 3, circuit.md).
 *  At CCW (x=0): Ra~500Ω → effective series R ~0 → cut corner ~15.9 kHz (negligible cut).
 *  At CW (x=1): Ra=50kΩ → effective series R ~25kΩ → cut corner ~600 Hz (heavy cut). */
inline double trebleResistance (double x)
{
    const double ra = audioTaperR (x, 50.0e3);
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
