#pragma once

#include <chowdsp_wdf/chowdsp_wdf.h>

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
 * IC1_B output rails are NOT modelled yet (ideal op-amp). Add an output clamp like Stage 1's if
 * Step 7/9 shows it clipping at the -12 dBu calibration.
 */
class Stage2
{
public:
    Stage2() = default;

    void prepare (double sampleRate)
    {
        c11.prepare (sampleRate);
        reset();
    }

    void reset() { c11.reset(); }

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

        return vin + vf;
    }

private:
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
