#pragma once

#include <cmath>

namespace tommy::dsp
{
/**
 * Low-drive top-octave tilt correction — a DRIVE-faded high-shelf.
 *
 * Measured (clean −30 dBFS sweep, level-normalised to 1 kHz vs the authoritative pedal2 NAM
 * captures — the same metric knob_tracking's SHAPE uses): the model's linear top octave rolls off
 * ~2–3 dB more than the real pedal across ~2–8 kHz, and the deficit is LARGEST at low drive,
 * shrinking as drive rises (≈−2.95 dB @8k at G0.2 → ≈−0.3 dB by G1.0). At high drive the clip
 * harmonics fill the top in, so the tilt only shows when fairly clean.
 *
 * So the correction is a high-shelf whose gain is FULL at low drive and FADES TO ZERO by high
 * drive — the opposite ramp to a clip-harmonic boost. The fade is essential: a fixed (always-on)
 * top lift would over-brighten high drive (where the tilt is already gone) and break the validated
 * high-drive tone match. Keyed to the DRIVE pot position; base rate; one biquad, ~0 CPU.
 *
 * pedal2 is the definitive reference for this (user decision): it took pedal2 knob_tracking SHAPE
 * from 8/16 → 14/16 (the 2 residual fails are an unrelated B0.65 bass-taper deviation, not the top
 * octave). The hot tone-set pedal1 disagrees on the top octave, but pedal2 is authoritative.
 *
 * Below kDriveLo it's at full gain; above kDriveHi it's exactly transparent (so high-drive settings
 * are bit-unchanged). It corrects the SHAPE band (≤8 kHz); above that the shelf plateaus, adding a
 * little air at 12–16 kHz on clean tones — small and within the V4-treble character.
 */
class DriveTilt
{
public:
    void prepare (double sampleRate)
    {
        fs = sampleRate;
        setDrive (lastDriveX);
        reset();
    }

    void reset() { x1 = x2 = y1 = y2 = 0.0; }

    /** DRIVE pot position (0..1). Full shelf gain at/below kDriveLo, fading to 0 at/above kDriveHi. */
    void setDrive (double driveX)
    {
        lastDriveX = driveX;
        double t = (driveX - kDriveLo) / (kDriveHi - kDriveLo);
        t = t < 0.0 ? 0.0 : (t > 1.0 ? 1.0 : t);
        t = t * t * (3.0 - 2.0 * t);           // smoothstep
        updateCoeffs (kMaxGainDB * (1.0 - t)); // full when clean, 0 when driven
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
            b0 = 1.0;
            b1 = b2 = a1 = a2 = 0.0; // exactly transparent at high drive
            return;
        }
        const double A = std::pow (10.0, gainDB / 40.0);
        const double w0 = 2.0 * M_PI * kFc / fs;
        const double cw = std::cos (w0), sw = std::sin (w0);
        const double alpha = sw / 2.0 * std::sqrt ((A + 1.0 / A) * (1.0 / kS - 1.0) + 2.0);
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

    // Calibrated against pedal2 low/mid-drive SHAPE (see class doc); tune here.
    static constexpr double kFc = 2500.0;     // shelf corner (Hz) — ramps the lift through 3–8 kHz
    static constexpr double kS = 0.7;         // gentle slope
    static constexpr double kMaxGainDB = 2.5; // lift at/below kDriveLo (cleanest)
    static constexpr double kDriveLo = 0.35;  // at/below this: full lift
    static constexpr double kDriveHi = 0.80;  // at/above this: none (high drive unchanged)

    double fs = 48000.0;
    double lastDriveX = 0.0;
    double b0 = 1.0, b1 = 0.0, b2 = 0.0, a1 = 0.0, a2 = 0.0;
    double x1 = 0.0, x2 = 0.0, y1 = 0.0, y2 = 0.0;
};
} // namespace tommy::dsp
