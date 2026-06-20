#pragma once

#include <cmath>

namespace tommy::dsp
{
/**
 * Bilinear (trapezoidal) frequency prewarping for a WDF capacitor.
 *
 * chowdsp_wdf discretises a capacitor with the trapezoidal rule: companion R = 1/(2 C fs). That is
 * the bilinear transform, which bends the frequency axis — an analog corner at f_c lands at a
 * *lower* digital frequency, the error growing toward Nyquist. At 48 kHz this costs the Tommy ~3.8 dB
 * at 12 kHz (treble C5/R5 ~16 kHz + Stage 2 C11 ~7 kHz corners), verified by a 96 kHz A/B render that
 * recovered the deficit and matched the real pedal's top octave.
 *
 * Prewarping pins ONE corner exactly: replace the capacitance C with C' = C · θ/tan(θ),
 * θ = π f_c / fs, so that after the bilinear warp the corner lands back at f_c. θ/tan(θ) < 1, so the
 * companion R = 1/(2 C' fs) grows, pushing the warped corner back up. Exact at f_c and very close
 * around it (good for our low-order, well-separated corners); still soft right at Nyquist — for that
 * last octave only full oversampling is perfect, a deliberate trade (see project notes).
 *
 * cornerHz is the analog corner the cap forms with its surrounding resistance (NOT the cap alone);
 * for the treble cap it moves with the pot, so recompute on every setParams. Clamped just below
 * Nyquist so a corner above fs/2 (e.g. the no-cut treble corner at very low fs) stays finite.
 */
inline double prewarpCapacitance (double cNominal, double cornerHz, double fs)
{
    constexpr double kMaxTheta = 1.55; // < pi/2; keeps tan() finite if a corner nears Nyquist
    double theta = M_PI * cornerHz / fs;
    if (theta > kMaxTheta)
        theta = kMaxTheta;
    if (theta < 1.0e-9)
        return cNominal; // corner far below Nyquist: no warping, no correction
    return cNominal * theta / std::tan (theta);
}
} // namespace tommy::dsp
