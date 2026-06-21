#pragma once

#include "ClippingOversampler.h"
#include "InputBuffer.h"
#include "Stage1.h"
#include "Stage2.h"
#include "TrebleNetwork.h"

#include <cmath>

namespace tommy::dsp
{
/**
 * One channel of the Tommy signal chain (the inner WDF path, in "volts"):
 *   InputBuffer (Stage 0) -> [ Stage 1 + SW1 clipping -> Treble -> Stage 2 ]oversampled -> C6 DC block.
 *
 * Input trim, volume, output trim and metering live in the processor (they are plain gains and
 * level reads, not circuit nodes). The oversampled region spans Stage 1 (nonlinear) AND the
 * downstream linear Treble + Stage 2: running their HF caps (C5, C11) at the oversampled rate
 * removes the base-rate bilinear top-octave droop (~2.3 dB at 12 kHz even after prewarp) — a pure
 * linear-discretisation fix, identical in every clip mode. InputBuffer (an ~8 Hz HP, no audible-band
 * HF caps) and the C6 output DC block stay at base rate.
 */
class TommyDSP
{
public:
    void prepare (double baseSampleRate, int maxBlockSize, int factorLog2)
    {
        input.prepare (baseSampleRate);
        clipper.prepare (baseSampleRate, maxBlockSize, factorLog2);
        // Treble + Stage 2 run INSIDE the oversampled region, so prepare them at the OS rate (their
        // caps discretise there; near the higher Nyquist the bilinear warp is negligible).
        treble.prepare (clipper.getOversampledRate());
        stage2.prepare (clipper.getOversampledRate());
        // C6 (1µ) output coupling cap ≈ DC blocker — at BASE rate (after downsampling). Removes the
        // small signal-dependent DC the Asymmetric (biased) clip produces; ~6 Hz corner is inaudible
        // and transparent in all modes.
        constexpr double kC6CornerHz = 6.0;
        dcR = std::exp (-2.0 * M_PI * kC6CornerHz / baseSampleRate);
        dcX1 = dcY1 = 0.0;
    }

    void reset()
    {
        input.reset();
        clipper.reset();
        treble.reset();
        stage2.reset();
        dcX1 = dcY1 = 0.0;
    }

    void setControls (double bassR, double driveR, double trebR, Stage1::ClipMode mode)
    {
        clipper.setParams (bassR, driveR);
        clipper.setMode (mode);
        treble.setParams (trebR);
    }

    void setFactor (int factorLog2)
    {
        clipper.setFactor (factorLog2);
        // Re-prepare the in-OS-region linear stages at the new oversampled rate (preserves their
        // resistance params; trebR is re-applied each block via setControls).
        treble.prepare (clipper.getOversampledRate());
        stage2.prepare (clipper.getOversampledRate());
    }

    /** Tune Asymmetric-mode lateral bias (for calibration). */
    void setAsymBias (double bias) { clipper.setAsymBias (bias); }

    /** ADAA on both op-amp rail clips (Stage 1 inside the oversampler, Stage 2 at base rate). */
    void setAdaaEnabled (bool e)
    {
        clipper.setAdaaEnabled (e);
        stage2.setAdaaEnabled (e);
    }

    double getLatencySamples() const { return clipper.getLatencySamples(); }

    /** Processes one channel block in place (values in volts). */
    void processBlock (double* data, int numSamples)
    {
        for (int i = 0; i < numSamples; ++i)
            data[i] = input.processSample (data[i]);

        // Stage 1 + clipping, THEN treble + Stage 2, all at the oversampled rate (the postFn runs
        // per oversampled sample inside the OS region).
        clipper.processBlock (data, numSamples,
                              [this] (double s) { return stage2.processSample (treble.processSample (s)); });

        for (int i = 0; i < numSamples; ++i)
        {
            const double y = data[i]; // downsampled Stage 2 output
            const double out = y - dcX1 + dcR * dcY1; // C6 output coupling (DC block), base rate
            dcX1 = y;
            dcY1 = out;
            data[i] = out;
        }
    }

private:
    InputBuffer input;
    ClippingOversampler clipper; // owns Stage 1 + the oversampler
    TrebleNetwork treble;
    Stage2 stage2;

    // C6 output-coupling DC blocker (see prepare()).
    double dcR = 0.0, dcX1 = 0.0, dcY1 = 0.0;
};
} // namespace tommy::dsp
