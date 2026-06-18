#pragma once

#include <chowdsp_wdf/chowdsp_wdf.h>

#include <cmath>

namespace tommy::dsp
{
/**
 * Stage 2 — IC1_B output recovery stage (NON-INVERTING op-amp).  [linear]
 *
 * Verified against `updated schematic - timmy.png` (2026-06-16). Same ideal-op-amp
 * two-one-port decomposition as Stage 1, but purely linear (no diodes):
 *
 *   + input = node_H (treble output).  (-) input = node_I.  output = node_J.
 *   Gain-set leg Zg (node_I -> VREF):   R4 (10k)            [pure resistor]
 *   Feedback leg Zf (node_I -> node_J): R6 (10k) || C11 (2n2)
 *
 *   Ig  = Vin / R4 ;  Vf = Ig * Zf ;  node_J = Vin + Vf  =>  gain = 1 + Zf/R4
 *
 * DC: C11 open => Zf = R6 => gain = 1 + 10k/10k = +2 (+6 dB). HF: C11 shorts R6 => Zf -> 0 =>
 * gain -> +1 (unity). Corner f = 1/(2*pi*R6*C11) ~= 7.2 kHz (a gentle high-cut/smoothing).
 *
 * IC1_B output rails ARE modelled (2026-06-17). Same JRC4559 on the same 9V/VREF~4.6V supply as
 * IC1_A, so identical estimated bipolar rails (+2.2 / -3.1 V from VREF). Measurement (Stage2_RailProbe)
 * showed node_J reaching ~6.2 V on the negative polarity in Hard mode — exactly 2x Stage 1's -3.1 V
 * rail doubled by this stage's +2 gain — which a real op-amp on 9V cannot produce. Modelled with the
 * SAME parabolic-knee + 1st-order ADAA clamp as Stage 1 (see Stage1::railClip). Stage 2 runs at base
 * rate, but the dominant case (Hard mode's negative swing) is ALREADY a band-limited flat clipped top
 * from Stage 1's oversampled rail clip, so clamping it here adds essentially no new harmonics; ADAA
 * covers the rest. Soft/Medium barely reach the rails (~2.5 V peak), so the clamp is near-transparent
 * there. Absolute rail volts are datasheet estimates (+-0.5 V) — tune via setRailVoltages() at Step 9.
 */
class Stage2
{
public:
    // Same op-amp / supply as Stage 1 — see Stage1.h for the derivation. Kept as independent
    // constants so Stage 2's rails can be tuned separately if ever needed.
    static constexpr double kRailPosDefault = 2.5;  // +V from VREF before the upper rail (see Stage1.h)
    static constexpr double kRailNegDefault = 3.4;  // |V| from VREF before the lower rail
    static constexpr double kRailKneeW = 0.35;      // knee half-width (V)

    Stage2() = default;

    void prepare (double sampleRate)
    {
        c11.prepare (sampleRate);
        reset();
    }

    void reset()
    {
        c11.reset();
        railPrevX = 0.0;
    }

    /** Enable 1st-order ADAA on the op-amp rail saturation (in addition to base-rate processing). */
    void setAdaaEnabled (bool enabled) { adaaOn = enabled; }

    /** Enable/disable the 9V op-amp output rail saturation (on by default; disable for pure linear
     *  transfer-function measurement). */
    void setRailClampEnabled (bool enabled) { railClampOn = enabled; }

    /** Override the bipolar output rail limits (Volts from VREF). posLimit > 0, negLimitMag > 0. */
    void setRailVoltages (double posLimit, double negLimitMag)
    {
        railPos = posLimit;
        railNegMag = negLimitMag;
    }

    /** Processes one sample. vin = node_H (treble output). Returns node_J (op-amp output). */
    double processSample (double vin)
    {
        // Gain-set leg (R4 to ground): Ig = current pulled from node_I held at Vin.
        vSource.setVoltage (vin);
        vSource.incident (r4.reflected());
        r4.incident (vSource.reflected());
        const double ig = chowdsp::wdft::current<double> (r4);

        // Feedback leg (R6 || C11): voltage developed by that current.
        iSource.setCurrent (ig);
        iSource.incident (zf.reflected());
        zf.incident (iSource.reflected());
        const double vf = chowdsp::wdft::voltage<double> (zf);

        return applyRail (vin + vf);
    }

private:
    // --- 9V op-amp output-rail saturation, identical model to Stage 1 (see Stage1.h for the full
    // rationale: linear until kneeW before the rail, short parabolic knee, then a hard clamp).
    // 1st-order ADAA bandlimits the hard corner; falls back to the midpoint value on tiny steps. ---
    double applyRail (double x)
    {
        if (! railClampOn)
        {
            railPrevX = x;
            return x;
        }
        double y;
        if (adaaOn)
        {
            const double dx = x - railPrevX;
            y = (std::abs (dx) > 1.0e-7) ? (railAntideriv (x) - railAntideriv (railPrevX)) / dx
                                         : railClip (0.5 * (x + railPrevX));
        }
        else
        {
            y = railClip (x);
        }
        railPrevX = x;
        return y;
    }

    double railAntideriv (double x) const
    {
        const double L = (x >= 0.0) ? railPos : railNegMag;
        const double ax = std::abs (x);
        const double W = kRailKneeW;
        if (ax <= L - W)
            return 0.5 * ax * ax;
        if (ax < L + W)
        {
            const double d = ax - (L - W);
            return 0.5 * ax * ax - d * d * d / (12.0 * W);
        }
        const double B = 0.5 * (L + W) * (L + W) - (2.0 / 3.0) * W * W;
        return B + L * (ax - (L + W));
    }

    double railClip (double x) const
    {
        const double L = (x >= 0.0) ? railPos : railNegMag;
        const double ax = std::abs (x);
        const double W = kRailKneeW;
        double y;
        if (ax <= L - W)
            y = ax;
        else if (ax >= L + W)
            y = L;
        else
        {
            const double d = ax - (L - W);
            y = ax - d * d / (4.0 * W);
        }
        return (x >= 0.0) ? y : -y;
    }

    bool railClampOn = true;
    bool adaaOn = false;
    double railPos = kRailPosDefault;
    double railNegMag = kRailNegDefault;
    double railPrevX = 0.0;

    // Gain-set leg: R4 (10k) to VREF. Pure resistor one-port driven by Vin.
    chowdsp::wdft::ResistorT<double> r4 { 10.0e3 };
    chowdsp::wdft::IdealVoltageSourceT<double, decltype (r4)> vSource { r4 };

    // Feedback leg: R6 (10k) || C11 (2n2), driven by the gain-set current.
    chowdsp::wdft::ResistorT<double> r6 { 10.0e3 };
    chowdsp::wdft::CapacitorT<double> c11 { 2.2e-9 };
    chowdsp::wdft::WDFParallelT<double, decltype (r6), decltype (c11)> zf { r6, c11 };
    chowdsp::wdft::IdealCurrentSourceT<double, decltype (zf)> iSource { zf };
};
} // namespace tommy::dsp
