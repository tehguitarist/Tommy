// Step 4 validation: Stage 0 (input network) frequency response.
//
// Expected behaviour:
//  - High-pass corner from C2 + R2 (510k). C2 is FITTED, not the documented 39n — see
//    InputBuffer::kC2 (v1.4 W8), so the corner is derived from the constant rather than hardcoded.
//    Audio-band points are checked against the analytic first-order HP response, not against a flat
//    0 dB: with the pole at ~19 Hz the network is legitimately -0.15 dB at 100 Hz, and asserting
//    flatness there would test the old corner by the back door.
//  - R1 (2m2 = 2.2 MΩ) is an input PULLDOWN to GND, transparent with a low-Z source.
//  - HF shunt from the series source impedance (rSrc) + C12 (47p) is far above the audio band
//    (~GHz), so the network should be flat (0 dB) through the audio range.

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
    constexpr double fc = 1.0 / (2.0 * M_PI * 510.0e3 * tommy::dsp::InputBuffer::kC2);

    std::printf ("Stage 0 (Input Network) frequency response\n");
    std::printf ("  High-pass corner (R2+C2) target: %.3f Hz  (C2 = %.1fn, fitted; documented %.0fn)\n",
                 fc, tommy::dsp::InputBuffer::kC2 * 1e9, tommy::dsp::InputBuffer::kC2Documented * 1e9);

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

    // In the audio band, should follow the analytic first-order high-pass (flat well above fc).
    for (double freq : { 100.0, 1000.0, 5000.0, 10000.0, 15000.0 })
    {
        const auto mag = measureMagnitudeDB (freq, fs);
        const auto want = 20.0 * std::log10 (freq / std::sqrt (freq * freq + fc * fc));
        std::printf ("  Magnitude at %.1f Hz: %.4f dB (expected %.4f dB)\n", freq, mag, want);
        if (std::abs (mag - want) > 0.1)
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
