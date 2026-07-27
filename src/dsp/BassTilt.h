#pragma once

#include "Stage1.h" // tommy::dsp::ClipMode

#include <cmath>

namespace tommy::dsp
{
/**
 * BASS<->DRIVE coupling correction (v1.4 W4) — a DRIVE- and clip-mode-keyed LOW shelf.
 *
 * Measured against the authoritative pedal2 NAM captures (1 kHz-normalised, the metric
 * knob_tracking's SHAPE uses): below ~250 Hz the model's low end tracks the real pedal with a
 * SIGN-FLIPPING error — the plugin is ~1 dB DARK at low DRIVE and up to ~2.6 dB HOT at DRIVE 0.65+,
 * and the size is clip-mode dependent (Medium worst, Soft nearly exact). Present in 15/16 captures.
 *
 * This is the ONLY correction that works, and W4 spent several refuted levers establishing that:
 *   * The bass NETWORK is correct — R3/C3/C4/BASS-pot values and topology were verified against
 *     circuit.md (Zg = R3 + (C3 || (BASS_R + C4))). Not an implementation bug.
 *   * The BASS TAPER must not be re-fitted as a physical parameter: BASS and DRIVE are perfectly
 *     confounded in pedal2 (B steps 0.50->0.65 exactly when D steps 0.50->0.65), so there is no
 *     signal to attribute between them, and the taper is validated against batches 3/4/5.
 *   * A STATIC, mode-blind low shelf fails: its mode-independent part is subsonic (~15 Hz corner)
 *     and the part that matters is mode-ordered and of BOTH signs.
 *   * Medium's clip threshold (kNMedium) is NOT the lever — the whole x1.10..x1.50 range moves the
 *     LF metric by 0.074 dB, against a rail-driven H2 cost of +3.48 -> +10.45 dB.
 *   * NO COMPONENT VALUE explains it, which is the strongest justification for correcting it here
 *     rather than in the circuit model. The bass network has exactly three LF-shape levers and all
 *     three were swept against the real clipper with this shelf disabled (analysis/w4_basscaps.py,
 *     560 + 288 renders): C3 has a shallow optimum AT the shipped 39n; C4 is nearly irrelevant at
 *     64-254 Hz (0.05 dB across 0.47u..2.2u, it only dominates near 20 Hz); and the BASS taper law
 *     coeff*x^exp has its grid optimum at exactly the shipped 50k*x^2.41, degrading monotonically
 *     as the exponent rises. Best component point 2.43 dB worst-LF vs this shelf's 1.14 dB — more
 *     than 2x worse. (R3/R7 are not LF-shape levers; they set midband gain, Zg -> R3 where the
 *     caps short.) Correcting both ends via the taper would need R(0.65)/R(0.50) ~ 3.4 vs the
 *     shipped 1.88, i.e. coeff ~183k on a 50k pot — physically impossible.
 * What DOES work is keying the shelf on the knobs, because the plugin knows DRIVE and SW1 position.
 * See analysis/w4_bassdrive.py --only knobshelf and CLAUDE.md's W4 entry.
 *
 * FITTED as an oracle bound: one static low shelf per (DRIVE, mode), chosen minimax across all four
 * sweep depths (clean/-18/-12/-6 dBFS) and the LF SHAPE bands (60/120/250 Hz). Result — worst LF
 * deviation median 1.00 -> 0.46 dB, max 2.61 -> 1.14 dB, and settings over the 1.5 dB SHAPE gate
 * 4 -> 0. A FIXED 250 Hz corner gives up almost nothing vs letting the corner float per setting
 * (median residual 0.48 vs 0.46 dB), so the corner is fixed and only the gain is keyed.
 *
 * KEYED ON DRIVE, NOT BASS (user decision, 2026-07-27). The fitted table is near-monotone in DRIVE
 * alone — boost below ~D0.5, cut above, crossing zero near D0.55 — and pedal2 samples SIX DRIVE
 * values across the full range but only TWO BASS values, locked to DRIVE. Keying on DRIVE is
 * therefore a 1-D fit with complete coverage; keying on (BASS, DRIVE) would be a 2-D surface fitted
 * from 5 points on a diagonal, unconstrained off it, and W6 means no future capture can ever
 * constrain it. Accepted cost: if the effect is physically BASS-driven rather than DRIVE-driven,
 * high-BASS/low-DRIVE settings get the correction with the wrong sign. No capture can settle that.
 *
 * Base rate, one biquad, ~0 CPU, no added latency. Unlike DriveTilt this shelf is NEVER exactly
 * transparent across the DRIVE range (it crosses zero rather than fading out), so it is bypassed
 * only where the interpolated gain rounds to zero.
 */
class BassTilt
{
public:
    void prepare (double sampleRate)
    {
        fs = sampleRate;
        update();
        reset();
    }

    void reset() { x1 = x2 = y1 = y2 = 0.0; }

    /** DRIVE pot position (0..1). */
    void setDrive (double driveX)
    {
        lastDriveX = driveX;
        update();
    }

    /** SW1 position — the correction is markedly mode-dependent (Medium worst, Soft nearly zero). */
    void setClipMode (ClipMode m)
    {
        mode = m;
        update();
    }

    /** CALIBRATION ONLY — scale the whole fitted table (1.0 = shipped, 0.0 = disabled).
     *  Exists so analysis/offline_render.cpp can sweep the correction's strength without a rebuild,
     *  the same way DriveTilt::setMaxGainDB does. Production never calls it. */
    void setGainScale (double s)
    {
        gainScale = s;
        update();
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
    // Fitted correction gain (dB) at kFc, per clip mode, at the six captured DRIVE positions.
    // SIGN IS THE CORRECTION APPLIED: negative = cut the plugin's bass. It is the NEGATIVE of the
    // measured plugin-pedal deviation — the v1.4 plan's old handover table inverted exactly this
    // and would have doubled the error, so do not re-derive the sign, use these numbers.
    // Soft/Medium have no D0.20 capture; the D0.35 value is held below that (see kDriveGrid).
    //   NOTE Medium's -1.7 at D0.65 is the least-certain entry: it is the single largest deviation
    //   in the set and sits at the capture most affected by anchor compression (its 1 kHz
    //   normalisation reference is past the diode clamp). It is kept because the driven sweeps
    //   agree on its sign and it is the mode's own worst point, but it is the first value to
    //   revisit if Medium's low end ever sounds over-thinned at mid drive.
    static constexpr int kN = 6;
    static constexpr double kDriveGrid[kN] = { 0.20, 0.35, 0.50, 0.65, 0.80, 1.00 };
    static constexpr double kGainSoft[kN] = { +1.1, +1.1, +0.2, -0.2, -0.1, -0.2 };
    static constexpr double kGainMedium[kN] = { +0.9, +0.9, +0.2, -1.7, -0.7, -0.7 };
    static constexpr double kGainHard[kN] = { +0.5, +0.5, +0.1, -0.9, -0.6, -0.6 };

    static constexpr double kFc = 250.0; // shelf corner (Hz) — fitted; see class doc
    static constexpr double kS = 0.7;    // gentle slope, matching DriveTilt

    /** Piecewise-linear interpolation of the fitted table at the current DRIVE. */
    double gainForDrive() const
    {
        const double* g = kGainHard;
        if (mode == ClipMode::Soft)
            g = kGainSoft;
        else if (mode == ClipMode::Medium)
            g = kGainMedium;
        // Linear is a validation-only mode with no fitted data — leave it uncorrected.
        else if (mode == ClipMode::Linear)
            return 0.0;

        const double x = lastDriveX;
        if (x <= kDriveGrid[0])
            return g[0];
        for (int i = 1; i < kN; ++i)
        {
            if (x <= kDriveGrid[i])
            {
                const double t = (x - kDriveGrid[i - 1]) / (kDriveGrid[i] - kDriveGrid[i - 1]);
                return g[i - 1] + t * (g[i] - g[i - 1]);
            }
        }
        return g[kN - 1];
    }

    void update() { updateCoeffs (gainForDrive() * gainScale); }

    void updateCoeffs (double gainDB)
    {
        if (std::abs (gainDB) <= 1.0e-6)
        {
            b0 = 1.0;
            b1 = b2 = a1 = a2 = 0.0; // exactly transparent at the zero crossing
            return;
        }
        // RBJ low shelf (the mirror of DriveTilt's high shelf).
        const double A = std::pow (10.0, gainDB / 40.0);
        const double w0 = 2.0 * M_PI * kFc / fs;
        const double cw = std::cos (w0), sw = std::sin (w0);
        const double alpha = sw / 2.0 * std::sqrt ((A + 1.0 / A) * (1.0 / kS - 1.0) + 2.0);
        const double tsa = 2.0 * std::sqrt (A) * alpha;

        const double b0n = A * ((A + 1.0) - (A - 1.0) * cw + tsa);
        const double b1n = 2.0 * A * ((A - 1.0) - (A + 1.0) * cw);
        const double b2n = A * ((A + 1.0) - (A - 1.0) * cw - tsa);
        const double a0n = (A + 1.0) + (A - 1.0) * cw + tsa;
        const double a1n = -2.0 * ((A - 1.0) + (A + 1.0) * cw);
        const double a2n = (A + 1.0) + (A - 1.0) * cw - tsa;

        b0 = b0n / a0n;
        b1 = b1n / a0n;
        b2 = b2n / a0n;
        a1 = a1n / a0n;
        a2 = a2n / a0n;
    }

    double fs = 48000.0;
    double lastDriveX = 0.0;
    double gainScale = 1.0; // see setGainScale — calibration override, 1.0 in production
    ClipMode mode = ClipMode::Soft;
    double b0 = 1.0, b1 = 0.0, b2 = 0.0, a1 = 0.0, a2 = 0.0;
    double x1 = 0.0, x2 = 0.0, y1 = 0.0, y2 = 0.0;
};
} // namespace tommy::dsp
