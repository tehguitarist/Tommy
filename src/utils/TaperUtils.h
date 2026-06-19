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
// BASS and TREBLE are CUT controls with the knob direction CORRECTED 2026-06-19 from NAM captures
// of the (MXR) Timmy: knob fully CW (x=1, "5 o'clock") = NO cut = full band; turning CCW (toward
// x=0, "7 o'clock") progressively cuts. (The earlier "x=0 = no cut" was backwards — the swept
// captures show treble swinging -10.7 dB@noon -> +9.9 dB@max at 8 kHz, i.e. CW = brighter.)
// So both controls take (1 - x): the cut increases as the knob is turned down.
// DRIVE and VOLUME behave conventionally (up = more).

/** BASS knob up (CW) => MORE low end => SMALLER gain-set resistance (more C4 path to AC ground).
 *  At CW (x=1): ~0Ω → C4 (1µF) strongly shunts node_X → full low-frequency gain (no cut).
 *  At CCW (x=0): 50kΩ → C4 path largely blocked → maximum bass cut. Rmax = 50k (A50k). */
inline double bassResistance (double x) { return audioTaperR0 (1.0 - x, 50.0e3); }

/** DRIVE knob up => more gain => LARGER feedback resistance. Rmax = 1M (A1M pot).
 *  Anchored to 0Ω at minimum: a real A1M pot reaches ~0Ω fully CCW, but the generic audioTaperR
 *  floors at 1% of max = 10kΩ here — enough feedback to add ~7.7 dB of phantom minimum-drive gain
 *  (measured: 8.96x vs 3.71x at min drive), making the pedal overdrive far too early. This shifts
 *  the audio-taper curve so x=0 -> 0Ω while preserving its shape in the usable range (x=1 -> 1M). */
inline double driveResistance (double x) { return audioTaperR0 (x, 1.0e6); }

/** TREBLE knob up (CW) => LESS cut (brighter). TREB is a rheostat (wiper jumpered to pin 3)
 *  feeding the R5/C5 low-pass.
 *  At CW (x=1): R=0Ω → cut corner ~15.9 kHz (no cut, full HF).
 *  At CCW (x=0): R=max → cut corner ~hundreds of Hz (heavy cut).
 *  Takes (1 - x) so cut deepens as the knob turns down; audioTaperR0 anchors the no-cut (CW)
 *  end to 0Ω. RANGE empirically fit to the MXR-Timmy NAM captures (2026-06-19): the schematic's
 *  50k gave far too shallow a cut (noon was +3 dB@8kHz vs the captured -10.7 dB). A ~250k range
 *  puts the noon corner at ~730 Hz, matching the captures (max stays bright; mids slightly
 *  under-cut due to the audio-taper shape). MXR values differ from the original schematic — refine
 *  with a clean single-control treble sweep when a pedal is available. */
inline double trebleResistance (double x)
{
    constexpr double rRange = 250.0e3; // empirical (MXR); schematic A50k was too little cut
    const double ra = audioTaperR0 (1.0 - x, rRange);
    return (ra * rRange) / (ra + rRange); // 0 .. ~rRange/2
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
