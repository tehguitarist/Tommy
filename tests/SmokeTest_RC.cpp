// Step 3 smoke test: chowdsp_wdf compile-time API RC lowpass.
// Verifies the -3dB point matches f = 1/(2*pi*R*C) to within 1%.

#include <chowdsp_wdf/chowdsp_wdf.h>

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace chowdsp::wdft;

namespace
{
double measureMagnitudeDB (double freq, double fs, ResistorT<double>& r1, CapacitorT<double>& c1)
{
    auto s1 = makeSeries<double> (r1, c1);
    auto p1 = makeInverter<double> (s1);
    IdealVoltageSourceT<double, decltype (p1)> vs { p1 };

    c1.reset();

    double magnitude = 0.0;
    const int numSamples = (int) fs;
    for (int n = 0; n < numSamples; ++n)
    {
        const auto x = std::sin (2.0 * M_PI * freq * (double) n / fs);
        vs.setVoltage (x);

        vs.incident (p1.reflected());
        p1.incident (vs.reflected());

        const auto y = voltage<double> (c1);

        if (n > numSamples / 10)
            magnitude = std::max (magnitude, std::abs (y));
    }

    return 20.0 * std::log10 (magnitude);
}
} // namespace

int main()
{
    constexpr double fs = 96000.0;
    constexpr double fc = 1000.0;
    constexpr double capValue = 1.0e-6;
    constexpr double resValue = 1.0 / (2.0 * M_PI * fc * capValue);

    ResistorT<double> r1 (resValue);
    CapacitorT<double> c1 (capValue, fs);

    const auto magAtFc = measureMagnitudeDB (fc, fs, r1, c1);
    const auto errorDB = std::abs (magAtFc - (-3.0102));

    std::printf ("RC Lowpass smoke test\n");
    std::printf ("  R = %.4f ohm, C = %.3e F, fc(target) = %.2f Hz\n", resValue, capValue, fc);
    std::printf ("  Magnitude at fc: %.4f dB (expected -3.0102 dB)\n", magAtFc);
    std::printf ("  Error: %.4f dB\n", errorDB);

    // -3dB point should be accurate to within ~1% in frequency, which corresponds
    // to a magnitude tolerance well under 0.1 dB at the -3dB knee.
    if (errorDB > 0.1)
    {
        std::fprintf (stderr, "FAIL: -3dB point error exceeds tolerance\n");
        return EXIT_FAILURE;
    }

    std::printf ("PASS\n");
    return EXIT_SUCCESS;
}
