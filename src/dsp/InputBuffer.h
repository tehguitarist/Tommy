#pragma once

#include <chowdsp_wdf/chowdsp_wdf.h>

namespace tommy::dsp
{
/**
 * Stage 0 — Input network.
 *
 * IN --R1(2m2)-- node_A --C2(39n)-- node_B --(to IC1_A pin 3, +)
 *                  |                  |
 *               C12(47p)           R2(510k)
 *                  |                  |
 *                 GND               GND (VREF)
 *
 * Purely passive RC tree, no feedback. node_B is high impedance (op-amp
 * non-inverting input draws no current), so R2-to-GND is the network's
 * terminating one-port and node_B's voltage is the voltage across R2.
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
        source.incident (r1SeriesNodeA.reflected());
        r1SeriesNodeA.incident (source.reflected());
        return chowdsp::wdft::voltage<double> (r2);
    }

private:
    chowdsp::wdft::ResistorT<double> r1 { 2.2 }; // R1 = 2m2 = 2.2 ohm
    chowdsp::wdft::CapacitorT<double> c12 { 47.0e-12 }; // C12 = 47p
    chowdsp::wdft::CapacitorT<double> c2 { 39.0e-9 }; // C2 = 39n
    chowdsp::wdft::ResistorT<double> r2 { 510.0e3 }; // R2 = 510k

    // node_B: C2 in series leading to R2-to-GND
    chowdsp::wdft::WDFSeriesT<double, decltype (c2), decltype (r2)> c2SeriesR2 { c2, r2 };

    // node_A: C12-to-GND in parallel with (C2 series R2)
    chowdsp::wdft::WDFParallelT<double, decltype (c12), decltype (c2SeriesR2)> nodeA { c12, c2SeriesR2 };

    // source -> R1 -> nodeA
    chowdsp::wdft::WDFSeriesT<double, decltype (r1), decltype (nodeA)> r1SeriesNodeA { r1, nodeA };

    chowdsp::wdft::IdealVoltageSourceT<double, decltype (r1SeriesNodeA)> source { r1SeriesNodeA };
};
} // namespace tommy::dsp
