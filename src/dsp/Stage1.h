#pragma once

#include <chowdsp_wdf/chowdsp_wdf.h>

#include <cmath>

namespace tommy::dsp
{
/**
 * Stage 1 — IC1_A drive stage (NON-INVERTING op-amp) with SW1 clipping in the feedback loop.
 *
 * Verified against `updated schematic - timmy.png` (2026-06-16). Signal enters the op-amp (+)
 * input (node_B); the (-) input (node_C) sees a gain-set leg to AC ground and a feedback leg
 * to the output (node_D). For an IDEAL op-amp, V(node_C)=V(node_B)=Vin and the (-) input draws
 * no current, so the stage decomposes exactly into two one-ports:
 *
 *   Gain-set leg Zg (node_C -> VREF):   R3 + ( C3 || (BASS_R + C4) )
 *   Feedback leg  (node_C -> node_D):   ( R7 + DRIVE_R ) || C1   [|| SW1 diodes]
 *
 *   Ig  = Vin / Zg                         (current through the gain-set leg)
 *   Vf  = voltage developed across the feedback leg when that same Ig flows through it
 *   V_D = Vin + Vf
 *
 * The op-amp holds node_C = Vin regardless of the feedback contents, so Ig = Vin/Zg is
 * unaffected by the diodes; the diodes only clamp Vf (hence node_D), giving classic
 * Tube-Screamer-style op-amp soft clipping that rides on the input. This is electrically the
 * SW1 clipping stage (architecture.md lists it separately, but the diodes are inside this
 * op-amp's feedback, so they cannot be a downstream block).
 *
 * SW1 modes (circuit.md): Soft = two antiparallel 1N4148 pairs (D5+D6 ∥ D3+D4) => one
 * DiodePairT with 2*Is; Medium = one antiparallel pair (D5+D6) => DiodePairT with Is; Hard =
 * single diode (D1) => DiodeT (asymmetric). Linear (no diodes) is retained for validation.
 */
class Stage1
{
public:
    enum class ClipMode
    {
        Linear, // no diodes (Step-4 validation reference)
        Soft,   // 4 diodes: two antiparallel pairs (2*Is)
        Medium, // 2 diodes: one antiparallel pair (Is)
        Hard    // 1 diode: asymmetric single (DiodeT)
    };

    // 1N4148 datasheet/Shockley params. nDiodes folds the ideality factor (n=1.752) into Vt
    // (chowdsp computes Vt_eff = nDiodes * Vt), giving the correct ~45.3 mV effective thermal
    // voltage. See dsp.md / wdft_nonlinearities.h.
    static constexpr double kIs = 2.52e-9;   // saturation current (A)
    static constexpr double kVt = 25.85e-3;  // thermal voltage (V)
    static constexpr double kN = 1.752;      // ideality factor (passed as nDiodes)

    // --- 9V single-supply op-amp output headroom (verified from the schematic power section:
    // +9V -> D7 1N5817 (~0.35V) -> R8 100r/C7 filter -> op-amp V+ ~8.3V; VREF ~4.6V via R9/R10;
    // NO step-up/charge-pump). The JRC4559 is not rail-to-rail (datasheet: ±12V swing on ±15V,
    // ~3V/rail conservative; ~1.5V/rail typical at light load). Expressed bipolar (relative to
    // VREF), positive peaks rail first because the ~4.6V bias sits above mid-supply. These are
    // estimates — refine by ear/measurement at Step 9 via setRailVoltages(). ---
    static constexpr double kRailPosDefault = 2.2;  // +V from VREF before the upper rail
    static constexpr double kRailNegDefault = 3.1;  // |V| from VREF before the lower rail
    static constexpr double kRailKneeW = 0.35;      // knee half-width (V): linear until rail-W,
                                                    // parabolic knee, then HARD clamp at rail+W

    Stage1() = default;

    void prepare (double sampleRate)
    {
        c3.prepare (sampleRate);
        c4.prepare (sampleRate);
        c1.prepare (sampleRate);
        c1P.prepare (sampleRate);
        c1S.prepare (sampleRate);
        reset();
    }

    void reset()
    {
        c3.reset();
        c4.reset();
        c1.reset();
        c1P.reset();
        c1S.reset();
    }

    /** BASS / DRIVE as already-tapered resistances in ohms (A-taper applied by the caller). */
    void setParams (double bassResistanceOhms, double driveResistanceOhms)
    {
        // BASS lives in Zg, DRIVE in Zf (separate sub-trees) — no shared adaptor, so no
        // ScopedDeferImpedancePropagation is needed (see the note kept in git history). The
        // controls stay physically coupled through gain = 1 + Zf/Zg.
        bassR.setResistanceValue (bassResistanceOhms);
        driveR.setResistanceValue (driveResistanceOhms);

        // Feedback series resistance R7 + DRIVE for the Norton-source diode sub-trees.
        const double rfb = 3.3e3 + driveResistanceOhms;
        nortonP.setResistanceValue (rfb);
        nortonS.setResistanceValue (rfb);
    }

    void setMode (ClipMode m)
    {
        if (m == mode)
            return;
        mode = m;
        if (mode == ClipMode::Soft)
            diodePair.setDiodeParameters (2.0 * kIs, kVt, kN); // two diodes in parallel per side
        else if (mode == ClipMode::Medium)
            diodePair.setDiodeParameters (kIs, kVt, kN);
    }

    ClipMode getMode() const { return mode; }

    /** Enable/disable the 9V op-amp output rail saturation (on by default; disable for pure
     *  linear transfer-function measurement). */
    void setRailClampEnabled (bool enabled) { railClampOn = enabled; }

    /** Override the bipolar output rail limits (Volts from VREF). posLimit > 0, negLimitMag > 0. */
    void setRailVoltages (double posLimit, double negLimitMag)
    {
        railPos = posLimit;
        railNegMag = negLimitMag;
    }

    /** Processes one sample. vin = node_B voltage (Stage 0 output). Returns node_D (= node_F). */
    double processSample (double vin)
    {
        // Gain-set leg: hold node_C at Vin, read the current it pulls to ground.
        vSource.setVoltage (vin);
        vSource.incident (zg.reflected());
        zg.incident (vSource.reflected());
        const double ig = chowdsp::wdft::current<double> (zg);

        double vf = 0.0;
        switch (mode)
        {
            case ClipMode::Linear:
                iSource.setCurrent (ig);
                iSource.incident (zf.reflected());
                zf.incident (iSource.reflected());
                vf = chowdsp::wdft::voltage<double> (zf);
                break;

            case ClipMode::Soft:
            case ClipMode::Medium:
                nortonP.setCurrent (ig);
                diodePair.incident (zfP.reflected());
                zfP.incident (diodePair.reflected());
                vf = chowdsp::wdft::voltage<double> (c1P);
                break;

            case ClipMode::Hard:
                nortonS.setCurrent (ig);
                diodeS.incident (zfS.reflected());
                zfS.incident (diodeS.reflected());
                vf = chowdsp::wdft::voltage<double> (c1S);
                break;
        }

        return railClip (vin + vf);
    }

private:
    // Asymmetric op-amp output-rail saturation (9V supply). Models the JRC4559 output stage
    // saturating against its rails: DEAD LINEAR until railKneeW volts before the rail, a short
    // parabolic knee, then a HARD clamp at the rail — matching a real op-amp output transistor
    // saturating (not a gentle tanh). Faithful for Hard mode's asymmetric character (soft diode
    // clip one way, hard rail clip the other). Transparent for normal/diode-clipped levels which
    // sit well inside the rails (Soft/Medium never reach it). This is an OUTPUT-STAGE
    // approximation — it does not re-close the feedback loop (the ideal op-amp already solved the
    // diode feedback); a full nonlinear-op-amp WDF model is the rigorous alternative if needed.
    // The hard edge's aliasing is handled by Step-6 oversampling + ADAA.
    double railClip (double x) const
    {
        if (! railClampOn)
            return x;
        const double L = (x >= 0.0) ? railPos : railNegMag;
        const double ax = std::abs (x);
        const double W = kRailKneeW;
        double y;
        if (ax <= L - W)
            y = ax; // linear region — exact, no coloration
        else if (ax >= L + W)
            y = L; // hard clamp at the rail
        else
        {
            const double d = ax - (L - W); // parabolic soft knee, C1-continuous at both ends
            y = ax - d * d / (4.0 * W);
        }
        return (x >= 0.0) ? y : -y;
    }

    using Res = chowdsp::wdft::ResistorT<double>;
    using Cap = chowdsp::wdft::CapacitorT<double>;
    template <typename A, typename B>
    using Series = chowdsp::wdft::WDFSeriesT<double, A, B>;
    template <typename A, typename B>
    using Parallel = chowdsp::wdft::WDFParallelT<double, A, B>;

    ClipMode mode = ClipMode::Linear;
    bool railClampOn = true;
    double railPos = kRailPosDefault;
    double railNegMag = kRailNegDefault;

    // --- Gain-set leg Zg : R3 + ( C3 || (BASS_R + C4) ) ---  (shared by all modes)
    Res r3 { 3.3e3 };
    Cap c3 { 39.0e-9 };
    Res bassR { 25.0e3 };
    Cap c4 { 1.0e-6 };
    Series<decltype (bassR), decltype (c4)> bassLeg { bassR, c4 };
    Parallel<decltype (c3), decltype (bassLeg)> nodeX { c3, bassLeg };
    Series<decltype (r3), decltype (nodeX)> zg { r3, nodeX };
    chowdsp::wdft::IdealVoltageSourceT<double, decltype (zg)> vSource { zg };

    // --- Linear feedback leg Zf : ( R7 + DRIVE_R ) || C1 ---  (mode = Linear)
    Res r7 { 3.3e3 };
    Res driveR { 500.0e3 };
    Cap c1 { 100.0e-12 };
    Series<decltype (r7), decltype (driveR)> r7Drive { r7, driveR };
    Parallel<decltype (r7Drive), decltype (c1)> zf { r7Drive, c1 };
    chowdsp::wdft::IdealCurrentSourceT<double, decltype (zf)> iSource { zf };

    // --- Antiparallel-pair feedback (modes Soft/Medium): Norton(R7+DRIVE) || C1, diode pair root ---
    chowdsp::wdft::ResistiveCurrentSourceT<double> nortonP { 503.3e3 };
    Cap c1P { 100.0e-12 };
    Parallel<decltype (nortonP), decltype (c1P)> zfP { nortonP, c1P };
    chowdsp::wdft::DiodePairT<double, decltype (zfP), chowdsp::wdft::DiodeQuality::Best> diodePair { zfP, kIs, kVt, kN };

    // --- Single-diode feedback (mode Hard): Norton(R7+DRIVE) || C1, single diode root ---
    chowdsp::wdft::ResistiveCurrentSourceT<double> nortonS { 503.3e3 };
    Cap c1S { 100.0e-12 };
    Parallel<decltype (nortonS), decltype (c1S)> zfS { nortonS, c1S };
    chowdsp::wdft::DiodeT<double, decltype (zfS), chowdsp::wdft::DiodeQuality::Best> diodeS { zfS, kIs, kVt, kN };
};
} // namespace tommy::dsp
