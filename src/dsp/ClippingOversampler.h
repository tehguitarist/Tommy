#pragma once

#include "Stage1.h"

#include <juce_dsp/juce_dsp.h>

#include <memory>

namespace tommy::dsp
{
/**
 * Owns Stage 1 (SW1 clipping inside IC1_A's feedback) + the oversampler. Stage 1's WDF caps are
 * (re)discretised at the oversampled rate so its frequency response is preserved at whatever rate
 * it runs.
 *
 * Two processBlock forms:
 *   - processBlock(data, n)            — runs Stage 1 only inside the OS region (used by the
 *                                        aliasing test to isolate the clip stage).
 *   - processBlock(data, n, postFn)    — runs Stage 1 then `postFn` per oversampled sample, so the
 *                                        caller's downstream LINEAR stages (treble + Stage 2) also
 *                                        run at the oversampled rate. This is what TommyDSP uses:
 *                                        it pulls those stages' base-rate bilinear cap warping (which
 *                                        left ~2.3 dB of top-octave droop at 12 kHz even after
 *                                        prewarp) up near the OS Nyquist, where it's negligible. The
 *                                        fix is purely a linear-discretisation correction, identical
 *                                        in every clip mode. Pass stages prepared at getOversampledRate().
 *
 * factorLog2: 0 = 1x (no oversampling), 1 = 2x, 2 = 4x, 3 = 8x.
 * Mono (single Stage1 instance); the plugin instantiates one per channel.
 */
class ClippingOversampler
{
public:
    using OS = juce::dsp::Oversampling<double>;

    void prepare (double baseSampleRate, int maxBlockSize, int factorLog2)
    {
        baseRate = baseSampleRate;
        maxBlock = maxBlockSize;
        setFactor (factorLog2);
    }

    /** Rebuilds the oversampler and re-prepares Stage 1 at the new oversampled rate. Causes a
     *  one-block gap (acceptable per architecture.md) — call from the audio thread when the
     *  pending factor changes. */
    void setFactor (int factorLog2)
    {
        osLog2 = factorLog2 < 0 ? 0 : (factorLog2 > 3 ? 3 : factorLog2);
        if (osLog2 == 0)
        {
            oversampler.reset();
        }
        else
        {
            oversampler = std::make_unique<OS> ((size_t) 1, (size_t) osLog2,
                                                OS::filterHalfBandFIREquiripple, true, false);
            oversampler->initProcessing ((size_t) maxBlock);
            oversampler->reset();
        }
        stage1.prepare (baseRate * (double) (1 << osLog2)); // caps discretised at OS rate
    }

    void reset()
    {
        stage1.reset();
        if (oversampler != nullptr)
            oversampler->reset();
    }

    void setMode (Stage1::ClipMode m) { stage1.setMode (m); }
    void setParams (double bassR, double driveR) { stage1.setParams (bassR, driveR); }
    void setAsymBias (double bias) { stage1.setAsymBias (bias); }
    void setRailClampEnabled (bool e) { stage1.setRailClampEnabled (e); }
    void setAdaaEnabled (bool e) { stage1.setAdaaEnabled (e); }

    double getLatencySamples() const { return oversampler ? (double) oversampler->getLatencyInSamples() : 0.0; }
    int getFactor() const { return 1 << osLog2; }

    /** The rate Stage 1 (and any postFn stages) actually run at = baseRate * 2^factor. Prepare the
     *  caller's downstream linear stages at THIS rate when using the postFn form of processBlock. */
    double getOversampledRate() const { return baseRate * (double) (1 << osLog2); }

    /** Processes one mono block in place at base rate — Stage 1 only (clip stage in isolation). */
    void processBlock (double* data, int numSamples)
    {
        processBlock (data, numSamples, [] (double s) { return s; });
    }

    /** As above, but runs `post` on every oversampled sample after Stage 1, so the caller's
     *  downstream linear stages run at the oversampled rate too (see class doc). */
    template <typename PostFn>
    void processBlock (double* data, int numSamples, PostFn&& post)
    {
        if (osLog2 == 0 || oversampler == nullptr)
        {
            for (int i = 0; i < numSamples; ++i)
                data[i] = post (stage1.processSample (data[i]));
            return;
        }

        double* chans[1] = { data };
        juce::dsp::AudioBlock<double> block (chans, 1, (size_t) numSamples);
        auto osBlock = oversampler->processSamplesUp (block);
        auto* d = osBlock.getChannelPointer (0);
        const int n = (int) osBlock.getNumSamples();
        for (int i = 0; i < n; ++i)
            d[i] = post (stage1.processSample (d[i]));
        oversampler->processSamplesDown (block);
    }

private:
    Stage1 stage1;
    std::unique_ptr<OS> oversampler;
    double baseRate = 48000.0;
    int maxBlock = 512;
    int osLog2 = 3;
};
} // namespace tommy::dsp
