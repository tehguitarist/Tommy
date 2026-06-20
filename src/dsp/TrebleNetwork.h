#pragma once

#include "Prewarp.h"

#include <chowdsp_wdf/chowdsp_wdf.h>

namespace tommy::dsp
{
/**
 * Treble network — passive treble-cut between Stage 1 and Stage 2.  [linear]
 *
 * Verified against `updated schematic - timmy.png` (2026-06-16). TREB is a RHEOSTAT (wiper
 * jumpered to pin 3, NO ground leg). Signal path:
 *
 *   node_F --TREB(var R, ~0..25k)-- node_G --R5(1k)-- node_H --(to IC1_B pin 5, +)
 *                                                       |
 *                                                     C5(10n)
 *                                                       |
 *                                                      GND
 *
 * IC1_B's (+) input is high impedance, so all current flows node_F -> TREB -> R5 -> C5 -> GND.
 * The output (node_H) is the voltage across C5 — a 1st-order low-pass whose corner is set by
 * (TREB + R5) and C5: ~15.9 kHz at TREB=0, ~612 Hz at TREB~25k (more TREB R = more treble cut).
 * Unity (passthrough) at low frequency.
 */
class TrebleNetwork
{
public:
    TrebleNetwork() = default;

    void prepare (double sampleRate)
    {
        fs = sampleRate;
        c5.prepare (sampleRate);
        updateC5Prewarp();
        reset();
    }

    void reset() { c5.reset(); }

    /** TREB as an already-mapped series resistance in ohms (~0..25k). */
    void setParams (double trebResistanceOhms)
    {
        trebRValue = trebResistanceOhms;
        trebR.setResistanceValue (trebResistanceOhms);
        updateC5Prewarp();
    }

    /** Processes one sample. vin = node_F (Stage 1 output). Returns node_H (to IC1_B +). */
    double processSample (double vin)
    {
        source.setVoltage (vin);
        source.incident (trebR5C5.reflected());
        trebR5C5.incident (source.reflected());
        return chowdsp::wdft::voltage<double> (c5);
    }

private:
    // Prewarp C5 so its low-pass corner — set by (TREB + R5) and C5, and moving with the pot —
    // lands at the true analog frequency despite bilinear warping near Nyquist. Recomputed whenever
    // TREB changes (and at prepare). Uses the NOMINAL C5/R5 to find the analog corner.
    void updateC5Prewarp()
    {
        constexpr double kC5Nom = 10.0e-9, kR5 = 1.0e3;
        const double cornerHz = 1.0 / (2.0 * M_PI * (trebRValue + kR5) * kC5Nom);
        c5.setCapacitanceValue (prewarpCapacitance (kC5Nom, cornerHz, fs));
    }

    double fs = 48000.0;
    double trebRValue = 12.5e3;

    chowdsp::wdft::ResistorT<double> trebR { 12.5e3 }; // TREB rheostat (0..~25k); default mid
    chowdsp::wdft::ResistorT<double> r5 { 1.0e3 };     // R5 = 1k
    chowdsp::wdft::CapacitorT<double> c5 { 10.0e-9 };  // C5 = 10n (prewarped at runtime)

    chowdsp::wdft::WDFSeriesT<double, decltype (r5), decltype (c5)> r5c5 { r5, c5 };
    chowdsp::wdft::WDFSeriesT<double, decltype (trebR), decltype (r5c5)> trebR5C5 { trebR, r5c5 };
    chowdsp::wdft::IdealVoltageSourceT<double, decltype (trebR5C5)> source { trebR5C5 };
};
} // namespace tommy::dsp
