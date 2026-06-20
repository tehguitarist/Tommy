#pragma once

#include <chowdsp_wdf/chowdsp_wdf.h>

namespace tommy::dsp
{
/**
 * Stage 0 — Input network.
 *
 *      IN --Rsrc-- node_A --C2(39n)-- node_B --(to IC1_A pin 3, +)
 *                   |   |               |
 *                R1(2m2)|            R2(510k)
 *                   |  C12(47p)         |
 *                  GND  |              GND (VREF)
 *                      GND
 *
 * R1 = 2m2 = 2.2 MΩ is an input PULLDOWN to ground (bias/pop suppression), NOT a series
 * resistor. (A 2.2 MΩ *series* element would attenuate ~14.5 dB and, with C12, roll off all
 * treble above ~1.5 kHz — clearly not the real pedal. Earlier code mislabelled a 2.2 Ω series
 * resistor as "R1 = 2m2", reconciled 2026-06-21.) With a low-Z DAW source the pulldown, the C12
 * RF shunt, and the source/wiring impedance are all audibly transparent; only C2+R2 act, giving
 * an ~8 Hz high-pass. `rSrc` is a small explicit series source/wiring impedance that keeps the
 * 47 pF RF shunt well-posed (its RF corner sits in the GHz range, far above audio).
 *
 * Purely passive RC tree, no feedback. node_B is high impedance (op-amp non-inverting input
 * draws no current); node_B's voltage is the voltage across R2.
 */
class InputBuffer
{
public:
    InputBuffer() = default;

    void prepare (double sampleRate)
    {
        c12.prepare (sampleRate);
        c2.prepare (sampleRate);
    }

    void reset()
    {
        c12.reset();
        c2.reset();
    }

    /** Processes one sample, returns the voltage at node_B (IC1_A pin 3 input). */
    double processSample (double x)
    {
        source.setVoltage (x);
        source.incident (rSrcSeriesNodeA.reflected());
        rSrcSeriesNodeA.incident (source.reflected());
        return chowdsp::wdft::voltage<double> (r2);
    }

private:
    chowdsp::wdft::ResistorT<double> rSrc { 2.2 };      // series source/wiring impedance (~a wire in
                                                        // audio; makes the C12 RF shunt well-posed)
    chowdsp::wdft::ResistorT<double> r1 { 2.2e6 };      // R1 = 2m2 = 2.2 MΩ input PULLDOWN to GND
    chowdsp::wdft::CapacitorT<double> c12 { 47.0e-12 }; // C12 = 47p RF shunt to GND
    chowdsp::wdft::CapacitorT<double> c2 { 39.0e-9 };   // C2 = 39n coupling
    chowdsp::wdft::ResistorT<double> r2 { 510.0e3 };    // R2 = 510k bias to VREF (GND in bipolar)

    // node_B: C2 in series leading to R2-to-GND
    chowdsp::wdft::WDFSeriesT<double, decltype (c2), decltype (r2)> c2SeriesR2 { c2, r2 };

    // node_A shunts to GND: R1 (pulldown) ∥ C12 (RF), in parallel with the node_B branch (C2+R2)
    chowdsp::wdft::WDFParallelT<double, decltype (r1), decltype (c12)> r1ParC12 { r1, c12 };
    chowdsp::wdft::WDFParallelT<double, decltype (r1ParC12), decltype (c2SeriesR2)> nodeA { r1ParC12, c2SeriesR2 };

    // source -> rSrc -> nodeA
    chowdsp::wdft::WDFSeriesT<double, decltype (rSrc), decltype (nodeA)> rSrcSeriesNodeA { rSrc, nodeA };

    chowdsp::wdft::IdealVoltageSourceT<double, decltype (rSrcSeriesNodeA)> source { rSrcSeriesNodeA };
};
} // namespace tommy::dsp
