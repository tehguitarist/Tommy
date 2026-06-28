#pragma once

#include <cmath>

namespace tommy::dsp
{
/**
 * Top-octave restore — a deterministic high-shelf that compensates the bilinear top-octave droop
 * the linear tone stages (Treble C5 + Stage 2 C11) accrue when the chain runs at LOW oversampling.
 *
 * Why it exists: the trapezoidal (bilinear) capacitor model places a zero at Nyquist, so an RC
 * low-pass discretised at fs droops toward fs/2 — a loss that grows with frequency and shrinks as
 * the internal rate rises. Prewarp (`Prewarp.h`) pins the corner frequencies but cannot lift that
 * near-Nyquist droop. Measured at 48 kHz (full chain, vs an 8x reference) it is essentially
 * POT-INDEPENDENT and scales cleanly with the oversampling factor:
 *      1x:  -4 dB @8k, -10 dB @12k, -21 dB @16k
 *      2x:  -0.9,      -2.2,        -4.1
 *      4x:  -0.2,      -0.4,        -0.8   (negligible)
 *      8x:   reference (≈0)
 * (see tests/OSFidelity.cpp). Because it is pot-independent, a single fixed-shape shelf whose gain
 * is set per OS factor restores most of it — at 4x/8x the gain is ~0, so the shelf is transparent
 * there and only acts where it's needed (1x/2x). Zero perceptible CPU (one biquad at base rate).
 *
 * It deliberately does NOT try to fully invert the 16 kHz loss at 1x: that would need ~+21 dB at
 * the very top (inverting a near-Nyquist zero — unstable/noisy). The shelf recovers the audible
 * 6–12 kHz "brilliance" region and partially the top, turning "noticeably dark" at 1x into "slightly
 * soft". A first-order RBJ high-shelf (gentle slope) matched to the droop shape.
 */
class TopOctaveRestore
{
public:
    void prepare (double sampleRate, int factorLog2)
    {
        fs = sampleRate;
        setFactor (factorLog2);
        reset();
    }

    void reset() { x1 = x2 = y1 = y2 = 0.0; }

    /** Recompute the shelf gain for the active oversampling factor (0=1x … 3=8x). The droop only
     *  needs correcting at 1x/2x; 4x/8x get ~0 dB (transparent). Gains tuned against OSFidelity. */
    void setFactor (int factorLog2)
    {
        // Shelf gain (dB) per OS factor — matched to the measured droop's audible region. 4x/8x ≈ 0.
        constexpr double kGainDB[4] = { 12.0, 3.0, 0.0, 0.0 };
        const int idx = factorLog2 < 0 ? 0 : (factorLog2 > 3 ? 3 : factorLog2);
        updateCoeffs (kGainDB[idx]);
    }

    inline double processSample (double x) noexcept
    {
        const double y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
        x2 = x1;
        x1 = x;
        y2 = y1;
        y1 = y;
        return y;
    }

private:
    void updateCoeffs (double gainDB)
    {
        if (gainDB <= 1.0e-6)
        {
            // Exactly transparent (no rounding-induced colouration at 4x/8x).
            b0 = 1.0;
            b1 = b2 = a1 = a2 = 0.0;
            return;
        }
        // RBJ high-shelf. fc ≈ 4 kHz so the boost rises through the 6–12 kHz droop region; a gentle
        // slope (S below) so it doesn't peak/ring near Nyquist.
        constexpr double fc = 9500.0;
        constexpr double S = 1.0; // shelf slope (1.0 = steepest non-resonant RBJ shelf)
        const double A = std::pow (10.0, gainDB / 40.0);
        const double w0 = 2.0 * M_PI * fc / fs;
        const double cw = std::cos (w0), sw = std::sin (w0);
        const double alpha = sw / 2.0 * std::sqrt ((A + 1.0 / A) * (1.0 / S - 1.0) + 2.0);
        const double tsa = 2.0 * std::sqrt (A) * alpha;

        const double b0n = A * ((A + 1.0) + (A - 1.0) * cw + tsa);
        const double b1n = -2.0 * A * ((A - 1.0) + (A + 1.0) * cw);
        const double b2n = A * ((A + 1.0) + (A - 1.0) * cw - tsa);
        const double a0n = (A + 1.0) - (A - 1.0) * cw + tsa;
        const double a1n = 2.0 * ((A - 1.0) - (A + 1.0) * cw);
        const double a2n = (A + 1.0) - (A - 1.0) * cw - tsa;

        b0 = b0n / a0n;
        b1 = b1n / a0n;
        b2 = b2n / a0n;
        a1 = a1n / a0n;
        a2 = a2n / a0n;
    }

    double fs = 48000.0;
    double b0 = 1.0, b1 = 0.0, b2 = 0.0, a1 = 0.0, a2 = 0.0;
    double x1 = 0.0, x2 = 0.0, y1 = 0.0, y2 = 0.0;
};
} // namespace tommy::dsp
