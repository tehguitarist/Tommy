// Step 4 validation: Stage 0 (input network) frequency response.
//
// Expected behaviour:
//  - High-pass corner from C2 (39n) + R2 (510k): f = 1/(2*pi*510k*39n) ~= 8 Hz
//  - HF shunt from R1 (2m2) + C12 (47p) is far above the audio band (~GHz),
//    so the network should be flat (0 dB) through the audio range.

#include "../src/dsp/InputBuffer.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

namespace
{
double measureMagnitudeDB (double freq, double fs)
{
    tommy::dsp::InputBuffer buf;
    buf.prepare (fs);
    buf.reset();

    const int numSamples = (int) fs;
    double magnitude = 0.0;
    for (int n = 0; n < numSamples; ++n)
    {
        const auto x = std::sin (2.0 * M_PI * freq * (double) n / fs);
        const auto y = buf.processSample (x);

        if (n > numSamples / 10)
            magnitude = std::max (magnitude, std::abs (y));
    }

    return 20.0 * std::log10 (magnitude);
}
} // namespace

int main()
{
    constexpr double fs = 96000.0;
    constexpr double fc = 1.0 / (2.0 * M_PI * 510.0e3 * 39.0e-9); // ~8 Hz

    std::printf ("Stage 0 (Input Network) frequency response\n");
    std::printf ("  High-pass corner (R2+C2) target: %.3f Hz\n", fc);

    int failures = 0;

    // At the high-pass corner, expect -3dB.
    {
        const auto mag = measureMagnitudeDB (fc, fs);
        std::printf ("  Magnitude at fc (%.2f Hz): %.4f dB (expected -3.01 dB)\n", fc, mag);
        if (std::abs (mag - (-3.0102)) > 0.1)
        {
            std::fprintf (stderr, "FAIL: high-pass corner magnitude out of tolerance\n");
            ++failures;
        }
    }

    // In the audio band, should be flat (0 dB).
    for (double freq : { 100.0, 1000.0, 5000.0, 10000.0, 15000.0 })
    {
        const auto mag = measureMagnitudeDB (freq, fs);
        std::printf ("  Magnitude at %.1f Hz: %.4f dB (expected ~0 dB)\n", freq, mag);
        if (std::abs (mag) > 0.1)
        {
            std::fprintf (stderr, "FAIL: audio-band magnitude at %.1f Hz out of tolerance\n", freq);
            ++failures;
        }
    }

    // Well below the corner, should be heavily attenuated.
    {
        const auto mag = measureMagnitudeDB (1.0, fs);
        std::printf ("  Magnitude at 1 Hz: %.4f dB (expected << 0 dB)\n", mag);
        if (mag > -10.0)
        {
            std::fprintf (stderr, "FAIL: sub-corner magnitude not sufficiently attenuated\n");
            ++failures;
        }
    }

    // Polarity check: a positive DC step should produce a positive node_B voltage
    // (Stage 0 is passive and non-inverting).
    {
        tommy::dsp::InputBuffer buf;
        buf.prepare (fs);
        buf.reset();

        double y = 0.0;
        for (int n = 0; n < 100; ++n)
            y = buf.processSample (1.0);

        std::printf ("  DC step response after 100 samples: %.6f (expected > 0)\n", y);
        if (y <= 0.0)
        {
            std::fprintf (stderr, "FAIL: polarity inversion detected at node_B\n");
            ++failures;
        }
    }

    if (failures > 0)
    {
        std::fprintf (stderr, "FAIL: %d check(s) failed\n", failures);
        return EXIT_FAILURE;
    }

    std::printf ("PASS\n");
    return EXIT_SUCCESS;
}
