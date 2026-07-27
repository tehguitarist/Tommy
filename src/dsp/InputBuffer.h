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
 * the chain's input high-pass — see `kC2` below, which is FITTED (19.1 Hz), not the documented
 * 39 n / 8.0 Hz. `rSrc` is a small explicit series source/wiring impedance that keeps the
 * 47 pF RF shunt well-posed (its RF corner sits in the GHz range, far above audio).
 *
 * Purely passive RC tree, no feedback. node_B is high impedance (op-amp non-inverting input
 * draws no current); node_B's voltage is the voltage across R2.
 */
class InputBuffer
{
public:
    /** C2, the input coupling cap — the ONE deliberately non-schematic component value in the model.
     *
     *  `circuit.md` documents **39 n**, which with R2 (510k) puts the input pole at 8.0 Hz; cascaded
     *  with the C6 output DC block that gives the chain an effective ~12.5 Hz corner. Measured
     *  against the pedal2 captures the real thing rolls off ~10 Hz HIGHER: normalise both FR curves
     *  at 20 Hz and the gap is a clean first-order shelf (0 dB at 20 Hz → a +2.2…+2.8 dB plateau by
     *  ~200 Hz, flat to 2.5 kHz), in **16/16 captures at all four sweep levels**. Since the midband
     *  is independently calibrated to ±0.35 dB, the correct reading is that the model passed ~2.5 dB
     *  too much below ~40 Hz. (v1.4 W8; found by eye on the dashboard — every LF metric in the
     *  harness normalises at 1 kHz and reports per-band deviations, a FIT-TO-LINE measure that
     *  smears a whole-curve CONTOUR error into "close enough" residuals. `w8_lf_contour.py --only
     *  contour` is the shape metric that does see it.)
     *
     *  **This value is a FIT, not a claim about the part.** Reaching the measured corner needs a ~3×
     *  departure from the documented 39 n, far outside any capacitor tolerance, so the extra
     *  roll-off is either an element `circuit.md` does not record or the NAM reamp chain's own
     *  subsonic roll-off. `CAPTURE_SPEC`'s bypass anchor would have separated the two; W6 struck all
     *  further captures, so it cannot be attributed on the evidence available. Shipping it is a
     *  judgement call about matching the reference, of the same class as "pedal2 is the definitive
     *  tone reference" — NOT a derivation. If the pedal is ever on a bench again, measure the input
     *  network and put `kC2Documented` back.
     *
     *  **Why here and not in a shelf:** the error's level-collapse (+2.24 dB clean → +0.77 dB at
     *  −6 dBFS) is clipping masking a linear error. Pre-clip placement reproduces that for free — at
     *  the fitted value every sweep level improves (median |deviation| over 20–64 Hz, 1 kHz-
     *  normalised: clean 1.10 → 0.58, −18 0.62 → 0.29, −12 0.57 → 0.41, −6 0.55 → 0.54). A static
     *  post-clip shelf could only sit in the middle of that range, which is exactly the ~0.42 dB
     *  irreducible residual `BassTilt` already carries — and `BassTilt`'s 250 Hz corner cannot reach
     *  40 Hz regardless. Fitted on the minimax across levels, not the rms: the rms optimum sits at
     *  23.5 Hz, but that is the clean sweep (the one level nobody plays at) outvoting the others.
     *  Sweep with `analysis/w8_lf_contour.py --only fit`; A/B back via `setC2Value`.
     */
    static constexpr double kC2 = 16.4e-9;           // fitted — input pole 19.1 Hz
    static constexpr double kC2Documented = 39.0e-9; // circuit.md's nominal — input pole 8.0 Hz

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

    /** CALIBRATION ONLY — override C2, i.e. move the input high-pass corner (v1.4 W8 sweep).
     *  Call AFTER prepare(): chowdsp's setCapacitanceValue re-propagates impedance using the
     *  already-stored sample rate. `<= 0` leaves the shipped value alone. */
    void setC2Value (double farads)
    {
        if (farads > 0.0)
            c2.setCapacitanceValue (farads);
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
    chowdsp::wdft::CapacitorT<double> c2 { kC2 };       // C2 coupling — FITTED, see kC2 above
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
