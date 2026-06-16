#pragma once

#include "ClippingOversampler.h"
#include "InputBuffer.h"
#include "Stage1.h"
#include "Stage2.h"
#include "TrebleNetwork.h"

namespace tommy::dsp
{
/**
 * One channel of the Tommy signal chain (the inner WDF path, in "volts"):
 *   InputBuffer (Stage 0) -> Stage 1 + SW1 clipping (oversampled) -> Treble -> Stage 2.
 *
 * Input trim, volume, output trim and metering live in the processor (they are plain gains and
 * level reads, not circuit nodes). Only the nonlinear Stage 1 is oversampled; the linear stages
 * run at base rate, processed sample-by-sample over the block.
 */
class TommyDSP
{
public:
    void prepare (double baseSampleRate, int maxBlockSize, int factorLog2)
    {
        input.prepare (baseSampleRate);
        clipper.prepare (baseSampleRate, maxBlockSize, factorLog2);
        treble.prepare (baseSampleRate);
        stage2.prepare (baseSampleRate);
    }

    void reset()
    {
        input.reset();
        clipper.reset();
        treble.reset();
        stage2.reset();
    }

    void setControls (double bassR, double driveR, double trebR, Stage1::ClipMode mode)
    {
        clipper.setParams (bassR, driveR);
        clipper.setMode (mode);
        treble.setParams (trebR);
    }

    void setFactor (int factorLog2) { clipper.setFactor (factorLog2); }
    void setAdaaEnabled (bool e) { clipper.setAdaaEnabled (e); }
    double getLatencySamples() const { return clipper.getLatencySamples(); }

    /** Processes one channel block in place (values in volts). */
    void processBlock (double* data, int numSamples)
    {
        for (int i = 0; i < numSamples; ++i)
            data[i] = input.processSample (data[i]);

        clipper.processBlock (data, numSamples); // Stage 1 + clipping, oversampled

        for (int i = 0; i < numSamples; ++i)
            data[i] = stage2.processSample (treble.processSample (data[i]));
    }

private:
    InputBuffer input;
    ClippingOversampler clipper; // owns Stage 1 + the oversampler
    TrebleNetwork treble;
    Stage2 stage2;
};
} // namespace tommy::dsp
