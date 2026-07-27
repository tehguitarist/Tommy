#pragma once

#include <chowdsp_wdf/chowdsp_wdf.h>

#include <cmath>

namespace tommy::dsp
{
/**
 * Accurate Wright-omega provider for the WDF diode models. chowdsp's default omega4 uses fast
 * bit-trick log/exp approximations that impose a ~-35 dB distortion floor (oversampling-immune,
 * audible on a "transparent" pedal). This solves w + ln(w) = x to ~machine precision with a few
 * Newton steps on std::log/std::exp — drops the floor to the true aliasing level. Plugged into
 * the diode templates' OmegaProvider slot. (Note: DiodePairT's "Best" path hardcodes omega4 and
 * ignores this; its "Good" path and DiodeT honour it — so we use those.)
 */
struct AccurateOmega
{
    template <typename T>
    static T omega (T x)
    {
        // Wright omega principal branch: w > 0, w + ln(w) = x.
        T w = (x > (T) 1) ? (x - std::log (x)) : std::exp (x);
        if (w < (T) 1e-12)
            w = (T) 1e-12;
        for (int i = 0; i < 4; ++i) // Newton: w -= f*w/(w+1), f = w + ln(w) - x (quadratic conv.)
        {
            const T f = w + std::log (w) - x;
            w -= f * w / (w + (T) 1);
            if (w < (T) 1e-12)
                w = (T) 1e-12;
        }
        return w;
    }
};

/**
 * MISMATCHED antiparallel diode pair (root WDF). Like chowdsp DiodePairT's "Good" path (Werner
 * eqn 18) but the two antiparallel diodes have a small forward-voltage MISMATCH: the +swing diode
 * uses Vt·(1+mismatch), the −swing diode Vt·(1−mismatch). This models real 1N4148 component
 * tolerance (a few % Vf spread between the two devices) — a slightly asymmetric clip → mild EVEN
 * harmonics that a perfectly-matched pair can't produce.
 *
 * Why per-polarity Vt and not a lateral wave-domain bias (the previous model): the asymmetry then
 * appears ONLY where the diodes conduct (clipping). At small signal both diodes are high-Z, so each
 * polarity reflects ≈ unity → the small-signal gain is UNPERTURBED (the lateral-bias model shifted
 * the operating point at all levels, perturbing near-zero-signal gain by up to ~20% at large bias).
 * b(0)=0 with no bConst correction (each polarity's reflection is 0 at a=0), so there is no static
 * DC. Because the mismatch is SYMMETRIC about the same average Vt, the level does NOT rise (unlike a
 * per-polarity *ratio* such as 1:2 diodes, which clips one side far later and runs ~4 dB hot). The
 * residual signal-dependent DC of the asymmetric clip is removed downstream by the C6 output cap.
 * Honours the OmegaProvider (AccurateOmega), so no omega4 distortion floor.
 */
template <typename T, typename Next, typename OmegaProvider>
class AsymDiodePairT final : public chowdsp::wdft::RootWDF
{
public:
    AsymDiodePairT (Next& n, T is, T vt, T nDiodes, T mismatch) : next (n)
    {
        n.connectToParent (this);
        setParams (is, vt, nDiodes, mismatch);
    }

    /** is/vt/nDiodes as for a matched pair; `mismatch` = fractional Vt spread between the two
     *  antiparallel diodes (0 = matched/symmetric, bit-identical to chowdsp DiodePairT's Good path). */
    void setParams (T is, T vt, T nDiodes, T mismatch)
    {
        Is = is;
        vtBase = nDiodes * vt;
        mism = mismatch;
        updateVt();
        calcImpedance();
    }

    void setMismatch (T mismatch)
    {
        mism = mismatch;
        updateVt();
        calcImpedance();
    }

    /** Runtime quality switch: true = the template's OmegaProvider (accurate Wright-omega, no
     *  distortion floor); false = chowdsp's fast omega4 (bit-trick, ~45% cheaper diode solve, but a
     *  ~−30..−44 dB null error). Drives the user-facing "HQ" button. Branch is per-sample but
     *  predictable (constant within a block), so effectively free. */
    void setHighQuality (bool hq) { highQ = hq; }

    void calcImpedance() override
    {
        using std::log;
        R_Is = next.wdf.R * Is;
        ooVtP = (T) 1 / VtP;
        RIs_oVtP = R_Is * ooVtP;
        logRP = log (RIs_oVtP);
        ooVtN = (T) 1 / VtN;
        RIs_oVtN = R_Is * ooVtN;
        logRN = log (RIs_oVtN);
    }

    inline void incident (T x) noexcept { wdf.a = x; }

    inline T reflected() noexcept
    {
        const T a = wdf.a;
        // +swing diode (Vt·(1+mismatch)) reflects a≥0; −swing diode (Vt·(1−mismatch)) reflects a<0.
        // Each branch → a at small |a| (diode off) ⇒ no small-signal gain shift; → clamp at clipping.
        if (a >= (T) 0)
            wdf.b = a + (T) 2 * (R_Is - VtP * omega (logRP + a * ooVtP + RIs_oVtP));
        else
            wdf.b = a - (T) 2 * (R_Is - VtN * omega (logRN - a * ooVtN + RIs_oVtN));
        return wdf.b;
    }

    chowdsp::wdft::WDFMembers<T> wdf;

private:
    // HQ on → accurate Wright-omega (template provider); off → chowdsp's fast omega4.
    inline T omega (T x) const noexcept { return highQ ? OmegaProvider::omega (x) : chowdsp::Omega::omega4 (x); }

    void updateVt()
    {
        VtP = vtBase * ((T) 1 + mism);
        VtN = vtBase * ((T) 1 - mism);
    }

    T Is = 1.0e-9, vtBase = 1.0, mism = 0.0, VtP = 1.0, VtN = 1.0;
    T ooVtP = 1.0, RIs_oVtP = 0.0, logRP = 0.0;
    T ooVtN = 1.0, RIs_oVtN = 0.0, logRN = 0.0;
    T R_Is = 0.0;
    bool highQ = true; // see setHighQuality
    const Next& next;
};

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
 * DiodePairT with 2*Is; Medium = one antiparallel pair (D5+D6), but with its OWN diode params
 * (kIsMedium/kNMedium) rather than plain Is -- the measured threshold gap is far larger than a
 * halved diode area can produce, see kNMedium; Hard = single diode (D1) => DiodeT (asymmetric).
 * Linear (no diodes) is retained for validation.
 *
 * Templated on the diode Wright-omega provider (default AccurateOmega — the shipped behaviour).
 * The template parameter exists so the feature-profiling test (tests/FeatureProfile.cpp) can A/B
 * AccurateOmega against chowdsp's fast omega4 for the CPU-vs-accuracy data behind the HQ-mode
 * decision; production code uses the `Stage1` alias below and is unaffected.
 */
/** SW1 clipping mode. Namespace-scoped (not nested in Stage1T) so it is ONE type across every
 *  omega-provider instantiation — `Stage1::ClipMode` still resolves via the member alias below. */
enum class ClipMode
{
    Linear, // no diodes (Step-4 validation reference)
    Soft,   // 4 diodes: two antiparallel pairs (2*Is)
    Medium, // 2 diodes: one antiparallel pair, own threshold (kIsMedium/kNMedium)
    Hard    // "Asymmetric": mismatched diode pair (AsymDiodePairT) — strong-ish even harmonics
};

template <typename OmegaProvider = AccurateOmega>
class Stage1T
{
public:
    using ClipMode = tommy::dsp::ClipMode;

    // 1N4148 datasheet/Shockley params. nDiodes folds the ideality factor (n=1.752) into Vt
    // (chowdsp computes Vt_eff = nDiodes * Vt), giving the correct ~45.3 mV effective thermal
    // voltage. See dsp.md / wdft_nonlinearities.h.
    // kIs CALIBRATED (2026-07-04, half the 2.52e-9 datasheet-typical value): the datasheet Is is a
    // "typical" spec, not a per-unit measurement, and real 1N4148 Is commonly spreads several-fold
    // between individual diodes/batches. At the asymptotic gain limit (DRIVE -> max, where R7+DRIVE
    // drops out of the feedback parallel combination and gain is set almost entirely by the diode
    // network's own incremental impedance in series with R3), the plugin was measurably ~1.8-2.6 dB
    // quiet vs the pedal2 reference across all three clip modes — see CLAUDE.md's former "High
    // drive (G0.65+)" residual entry. Confirmed via dsp-validator that this is NOT a WDF/topology
    // bug (Norton injection, impedance propagation, and the Wright-omega diode solve were all
    // verified numerically correct) and NOT the DRIVE taper (sweeping the drive parameter to 50x
    // its normal range only closes ~0.2 dB of the gap - the plugin's gain hard-asymptotes below the
    // real pedal's regardless). Halving Is raises the diode's effective forward-voltage-per-current
    // (V = n*Vt*ln(I/Is), smaller Is => more V at the same current), which is exactly the diode-
    // dominated regime this residual lives in. Closes pedal2's LEVEL check from 12/16 to 16/16 pass
    // with no THD/SHAPE/harmonic-content regression beyond two already-marginal SHAPE cases (see
    // CLAUDE.md). A steeper reduction (~6.5x, Is=3.84e-10) closed the gap almost exactly but failed
    // ClippingStage_Sine's large-signal Hard-mode compression check - this more conservative half
    // value was chosen as the best-supported trade-off. Re-verify against batch 3/4/5 if those
    // captures become available; re-derive from a physical-diode Is measurement if in doubt.
    static constexpr double kIs = 1.26e-9;   // saturation current (A) -- see calibration note above
    static constexpr double kVt = 25.85e-3;  // thermal voltage (V)
    static constexpr double kN = 1.752;      // ideality factor (passed as nDiodes)

    // --- Medium ("Open", SW1 mid) branch diode params — INDEPENDENT of Soft's. ---
    // Soft is 2*kIs / kN and measures EXACT against pedal2 at every level and drive, which pins the
    // shared diode parameters; Medium is then separately fittable. Deriving Medium as simply "one
    // pair instead of two" (i.e. kIs, kN) does not reproduce the real pedal: a 2x ratio in Is is
    // worth only n*Vt*ln(2) ~= 31 mV of threshold, whereas the pedal's Medium is markedly CLEANER
    // than its Soft at low level (D0.35/-18 dBFS, 101 Hz: pedal 12.4% vs Soft 18.1%; model had both
    // at ~19%) and yet MORE distorted at high level (-6 dBFS: pedal 19.4% vs Soft 15.3%). That is a
    // higher-threshold, HARDER-kneed clip, not a softer one — the shipped model was progressively
    // too clean as level rose (-0.2/-1.0/-1.9 dB THD error at -18/-12/-6).
    // Ruled out first: SW1 mid is NOT a genuinely open circuit (no diodes). circuit.md calls SW1
    // "three ganged on/off/on" switches, which would put the middle position all-off, and the UI
    // label is "Open" — but rendering Medium as ClipMode::Linear (rail clip only) gives 33-41% THD
    // against the pedal's ~20% (+6.1 dB median error, worst +10.3). "Open" is sonic branding.
    // circuit.md's Mode B ("one antiparallel pair") is right in KIND; what it cannot tell us is the
    // per-mode component detail, because the schematic images were removed from the repo and no
    // physical re-verification is currently possible. So these are an empirical FIT, exactly as
    // .claude/plans/v1.4-fidelity.md W1 authorises ("give the Soft/Medium branch a per-mode degree
    // of freedom ... rather than deriving Medium from kIs and Soft from 2*kIs"). Re-derive from a
    // measurement of the real switch/diodes if that ever becomes possible.
    // FIT RESULT (2026-07-26, W1). Is is UNCHANGED at kIs — the same diode part as Soft, which is
    // what a shared-diode reading requires and what the fit independently preferred (a competing
    // n=3.066 solution needed Is at 4x kIs and was both worse, cost 0.190 vs 0.137, and in direct
    // conflict with v1.2.1's Is calibration). The whole correction is the effective thermal-voltage
    // multiplier: chowdsp's nDiodes scales Vt (Vt_eff = nDiodes * kVt), so kNMedium = 1.35 * kN
    // raises Medium's Vt_eff from 45.3 mV to 61.1 mV -- a HIGHER, HARDER clip threshold.
    // A multiplier between 1 and 2 sits between one and two 1N4148s in series (nDiodes = k * kN
    // models k diodes in series per direction), which is consistent with -- but NOT proof of -- an
    // extra series element in the SW1 mid leg that circuit.md does not record. It is an empirical
    // fit, not a derivation.
    // Fitted on all 5 pedal2 Medium captures x 3 sweep levels x 3 probe frequencies, minimising the
    // RMS of the per-level median THD error so that BOTH the offset and the level SLOPE are
    // corrected (a mean-only fit would leave the knee wrong):
    //     shipped (kIs, kN):        -0.17 / -0.92 / -1.86 dB at -18/-12/-6 dBFS
    //     fitted  (kIs, 1.35*kN):   +0.16 / -0.23 / -0.60 dB
    // (median over the 100 Hz-2 kHz Farina bands, the canonical report metric; the 3-probe fit
    // metric reads -0.51 at -6. Either way -6 dBFS lands just outside the +-0.5 dB gate -- a
    // deliberate trade, see the rail note below.)
    // The THD-optimal multiplier was 1.5x (cost 0.136) but it is NOT what ships -- see the rail
    // note below. Soft is untouched and remains bit-identical (see setMediumDiodeParams).
    // Held at 1.35x, NOT the THD-optimal 1.5x, because of the op-amp rails. Raising Medium's
    // threshold delays its clip, and past ~1.35x the Stage-1 output starts reaching the ASYMMETRIC
    // rails (+2.5/-3.4 V) before the diodes clamp — which manufactures even harmonics the real
    // pedal does not have. Medium is a SYMMETRIC clipper, so that is an audible timbre error.
    // Measured H2 error vs pedal at -6 dBFS (median over the 5 Medium captures):
    //     k=1.00 (v1.3.0): -2.83 dB | k=1.25: -3.44 | k=1.35: +3.48 | k=1.50: +10.45
    // and the matching THD error (-18/-12/-6 dBFS, rms):
    //     k=1.00: -0.18/-0.91/-1.79 (1.164) | k=1.25: +0.09/-0.37/-0.87 (0.550)
    //     k=1.35: +0.16/-0.21/-0.51 (0.331) | k=1.50: +0.23/-0.00/-0.05 (0.136)
    // 1.35x meets the +-0.5 dB THD gate (at its boundary at -6) while keeping the rail artefact
    // small. Confirmed rail-driven, not diode-driven: raising the supply to 12 V (which scales the
    // rails but NOT the diode thresholds) drops Medium's H2 from ~-38 to -48..-53 dBc, right onto
    // the pedal. See the rail note in circuit.md's Op-Amp Model section.
    static constexpr double kIsMedium = kIs;         // same diode part as Soft — deliberately kIs
    static constexpr double kNMedium = 1.35 * kN;    // 2.365 => Vt_eff 61.1 mV (was 45.3 mV)

    // --- 9V single-supply op-amp output headroom (verified from the schematic power section:
    // +9V -> D7 1N5817 (~0.35V) -> R8 100r/C7 filter -> op-amp V+ ~8.3V; VREF ~4.6V via R9/R10;
    // NO step-up/charge-pump). The JRC4559 is not rail-to-rail (datasheet: ±12V swing on ±15V,
    // ~3V/rail conservative; ~1.5V/rail typical at light load). Expressed bipolar (relative to
    // VREF), positive peaks rail first because the ~4.6V bias sits above mid-supply. These are
    // estimates — refine by ear/measurement at Step 9 via setRailVoltages(). ---
    // Nudged 2026-06-17 from +2.2/-3.1 to +2.5/-3.4: datasheet gives ~2V headroom-from-rail at
    // RL>=2k (NJM4559: +-13V typ swing on +-15V); the Timmy loads IC1 far lighter (>=25k) so real
    // headroom is ~1.2V, putting the rails closer to the supply. No published Timmy measurement
    // exists (only qualitative confirmation) — still an estimate, refine by ear at Step 9.
    static constexpr double kRailPosDefault = 2.5;  // +V from VREF before the upper rail
    static constexpr double kRailNegDefault = 3.4;  // |V| from VREF before the lower rail
    static constexpr double kRailKneeW = 0.35;      // knee half-width (V): linear until rail-W,
                                                    // parabolic knee, then HARD clamp at rail+W

    // Diode-mismatch asymmetry — fractional Vt spread between the two antiparallel diodes (see
    // AsymDiodePairT). Models real 1N4148 component tolerance: a real Timmy shows EVEN harmonics in
    // EVERY mode (incl. symmetric Soft/Medium) at ~−47..−55 dB H2 re fund at high drive; a matched
    // model produces NONE. Unlike the earlier lateral-bias model, the mismatch perturbs NO
    // small-signal gain (asymmetry only where the diodes conduct) and adds no static DC. Calibrated
    // to the batch-5 hot-reamp H2 (2026-06-22); odd harmonics + THD + level unchanged (mismatch=0 is
    // bit-identical to a matched pair). "Hard" needs a larger value (real H2 ≈ −34, a strongly
    // one-sided single-diode circuit approximated here by the mismatched pair).
    static constexpr double kAsymMismatch = 0.45; // Hard "Asymmetric": real Hard H2 ≈ −34. Large
                                                  // because Hard is really a SINGLE diode (strongly
                                                  // one-sided) approximated by a heavily-mismatched
                                                  // pair; symmetric about Vt so it does NOT run hot.
    static constexpr double kSymMismatch  = 0.06; // Soft/Medium diode Vf tolerance (real H2 ≈ −50)

    Stage1T() = default;

    void prepare (double sampleRate)
    {
        c3.prepare (sampleRate);
        c4.prepare (sampleRate);
        c1.prepare (sampleRate);
        c1P.prepare (sampleRate);
        c1A.prepare (sampleRate);
        reset();
    }

    void reset()
    {
        c3.reset();
        c4.reset();
        c1.reset();
        c1P.reset();
        c1A.reset();
        railPrevX = 0.0;
    }

    /** Enable 1st-order ADAA on the op-amp rail saturation (the hard-edged nonlinearity that
     *  aliases most). In addition to oversampling, not instead — see dsp.md. */
    void setAdaaEnabled (bool enabled) { adaaOn = enabled; }

    /** CALIBRATION ONLY — override the BASS-network caps C3 / C4 (<=0 keeps the shipped value).
     *  Exists for v1.4 W4: those two caps DOMINATE the deep-LF cut (the BASS pot only trims it,
     *  see TaperUtils.h's bassResistance note), they sit PRE-clip so their effect is naturally
     *  level-dependent, and circuit.md — which is the only surviving source for them, the
     *  schematic images having been removed — is internally inconsistent about this exact network
     *  in three places. So "the DSP matches circuit.md" (verified) does NOT establish the values
     *  are right, and this hook lets the harness ask whether a different C3/C4 explains the LF
     *  residual better than the empirical BassTilt shelf does. Production never calls it. */
    void setBassCaps (double c3F, double c4F)
    {
        if (c3F > 0.0)
            c3.setCapacitanceValue (c3F);
        if (c4F > 0.0)
            c4.setCapacitanceValue (c4F);
    }

    /** HQ on → accurate Wright-omega diode solve; off → fast omega4 (cheaper, slight distortion
     *  floor). Drives the user-facing HQ button; applies to both diode sub-trees. */
    void setHighQuality (bool hq)
    {
        diodePair.setHighQuality (hq);
        diodeA.setHighQuality (hq);
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
        nortonA.setResistanceValue (rfb);
    }

    /** Tune the Asymmetric-mode lateral bias (wave-domain offset; more bias = more even harmonics,
     *  level ~unchanged). For calibration sweeps. */
    void setAsymMismatch (double m) { diodeA.setMismatch (m); }

    /** Tune the Soft/Medium diode-mismatch (small even-harmonic asymmetry from Vf tolerance). For
     *  calibration; re-applied on the next setMode (mode reconfigures the pair's Is + mismatch). */
    void setSymMismatch (double m)
    {
        symMismatch = m;
        if (mode == ClipMode::Soft)
            diodePair.setParams (2.0 * kIs, kVt, kN, symMismatch);
        else if (mode == ClipMode::Medium)
            diodePair.setParams (medIs, kVt, medN, mediumMismatch());
    }

    /** Medium's fractional Vt mismatch, rescaled so the ABSOLUTE Vf spread matches what
     *  kSymMismatch means on Soft. `mismatch` in AsymDiodePairT is a FRACTION of vtBase, and
     *  Medium's vtBase is kNMedium/kN = 1.5x Soft's — so passing symMismatch through unscaled
     *  would silently make Medium's absolute diode mismatch 1.5x Soft's, and it did: Medium's H2
     *  jumped from -50.7 to -37.5 dBc at -6 dBFS against a pedal that measures -48.8 (i.e. no
     *  even-harmonic content to speak of, as a SYMMETRIC clipper should have). That is a real
     *  timbre error, caught by the dsp-validator pass on this change.
     *  There is no physical basis for the scaling: kSymMismatch models 1N4148 unit-to-unit Vf
     *  TOLERANCE, which is a device property in millivolts, whereas kNMedium's 1.5x is a lumped
     *  threshold fit (not 1.5 literal series diodes). So hold the absolute spread constant. */
    double mediumMismatch() const { return symMismatch * kN / medN; }

    /** CALIBRATION ONLY — override the Medium branch's diode Is / ideality factor. Soft is
     *  deliberately NOT reachable from here: it measures exact against pedal2 at every level and
     *  drive, which is what pins the shared diode parameters and makes Medium separately fittable.
     *  Re-applied on the next setMode. Used by analysis/offline_render.cpp's fit sweep. */
    void setMediumDiodeParams (double is, double n)
    {
        medIs = is > 0.0 ? is : kIsMedium;
        medN = n > 0.0 ? n : kNMedium;
        if (mode == ClipMode::Medium)
            diodePair.setParams (medIs, kVt, medN, mediumMismatch());
    }

    void setMode (ClipMode m)
    {
        if (m == mode)
            return;
        mode = m;
        if (mode == ClipMode::Soft)
            diodePair.setParams (2.0 * kIs, kVt, kN, symMismatch); // two diodes in parallel per side
        else if (mode == ClipMode::Medium)
            diodePair.setParams (medIs, kVt, medN, mediumMismatch());
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
                nortonA.setCurrent (ig);
                diodeA.incident (zfA.reflected());
                zfA.incident (diodeA.reflected());
                vf = chowdsp::wdft::voltage<double> (c1A);
                break;
        }

        return applyRail (vin + vf);
    }

private:
    // 1st-order ADAA wrapper around the rail saturation: replaces g(x) with the average of g
    // over [x[n-1], x[n]] = (G(x[n]) - G(x[n-1])) / (x[n] - x[n-1]), G = antiderivative of the
    // clip. Bandlimits the hard rail corner, cutting aliasing on top of oversampling. Falls back
    // to the midpoint value when the step is tiny (avoids 0/0). State updates every call so
    // toggling ADAA is glitch-free.
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

    // Antiderivative of railClip(x), with G(0)=0 (piecewise: x^2/2 linear, cubic knee, then
    // linear once hard-clamped). Even about each (asymmetric) rail magnitude.
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
    double symMismatch = kSymMismatch; // current Soft/Medium diode mismatch (default kSymMismatch)
    double medIs = kIsMedium;          // Medium-branch diode Is (Soft always uses 2*kIs)
    double medN = kNMedium;            // Medium-branch ideality factor (Soft always uses kN)
    bool railClampOn = true;
    bool adaaOn = false;
    double railPos = kRailPosDefault;
    double railNegMag = kRailNegDefault;
    double railPrevX = 0.0;

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
    // AsymDiodePairT (not chowdsp DiodePairT) so Soft/Medium carry the small diode-Vf mismatch
    // (kSymMismatch). At mismatch=0 it is bit-identical to DiodePairT's Good/eqn-18 path (each
    // polarity's reflection is 0 at a=0), so the symmetric behaviour is preserved; a small mismatch
    // adds the measured even harmonics with NO small-signal gain shift. AccurateOmega removes the
    // omega4 distortion floor.
    AsymDiodePairT<double, decltype (zfP), OmegaProvider> diodePair { zfP, kIs, kVt, kN, kSymMismatch };

    // --- Asymmetric-pair feedback (mode Hard/"Asymmetric"): Norton(R7+DRIVE) || C1, asym pair root.
    // Mild 2-sided asymmetric clip (n_pos vs n_neg diodes) — matches the captures' odd-dominant +
    // moderate-even profile, unlike the old single diode (one-sided, strong even). ---
    chowdsp::wdft::ResistiveCurrentSourceT<double> nortonA { 503.3e3 };
    Cap c1A { 100.0e-12 };
    Parallel<decltype (nortonA), decltype (c1A)> zfA { nortonA, c1A };
    AsymDiodePairT<double, decltype (zfA), OmegaProvider> diodeA { zfA, kIs, kVt, kN, kAsymMismatch };
};

/** Production Stage 1: accurate Wright-omega (no omega4 distortion floor). All non-test code uses
 *  this alias, so `Stage1::ClipMode` / `Stage1::kRailPosDefault` etc. resolve exactly as before. */
using Stage1 = Stage1T<AccurateOmega>;
} // namespace tommy::dsp
