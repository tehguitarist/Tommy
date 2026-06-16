// Step 7 prep: validate the Treble network and Stage 2 (IC1_B) linear stages against their
// analytic transfer functions (bilinear-prewarped caps), plus DC gain and polarity.

#include "../src/dsp/Stage2.h"
#include "../src/dsp/TrebleNetwork.h"

#include <cmath>
#include <complex>
#include <cstdio>
#include <cstdlib>

namespace
{
constexpr double fs = 96000.0;
using cplx = std::complex<double>;

double wWarp (double f) { return (2.0 * fs) * std::tan (2.0 * M_PI * f / (2.0 * fs)); }

// --- Treble: output = V across C5 = Zc5 / (TREB + R5 + Zc5) ---
constexpr double R5 = 1.0e3, C5 = 10.0e-9;
double trebAnalyticDB (double f, double trebR)
{
    const cplx j (0.0, 1.0);
    const cplx zc = 1.0 / (j * wWarp (f) * C5);
    return 20.0 * std::log10 (std::abs (zc / (trebR + R5 + zc)));
}
double trebMeasureDB (double f, double trebR)
{
    tommy::dsp::TrebleNetwork t;
    t.prepare (fs);
    t.setParams (trebR);
    double mag = 0.0;
    const int n = (int) fs;
    for (int i = 0; i < n; ++i)
    {
        const double y = t.processSample (std::sin (2.0 * M_PI * f * (double) i / fs));
        if (i > n / 2)
            mag = std::max (mag, std::abs (y));
    }
    return 20.0 * std::log10 (mag);
}

// --- Stage 2: gain = 1 + (R6 || Zc11)/R4 ---
constexpr double R4 = 10.0e3, R6 = 10.0e3, C11 = 2.2e-9;
double s2AnalyticDB (double f)
{
    const cplx j (0.0, 1.0);
    const cplx zc = 1.0 / (j * wWarp (f) * C11);
    const cplx zf = (R6 * zc) / (R6 + zc);
    return 20.0 * std::log10 (std::abs (1.0 + zf / R4));
}
double s2MeasureDB (double f)
{
    tommy::dsp::Stage2 s;
    s.prepare (fs);
    double mag = 0.0;
    const int n = (int) fs;
    for (int i = 0; i < n; ++i)
    {
        const double y = s.processSample (std::sin (2.0 * M_PI * f * (double) i / fs));
        if (i > n / 2)
            mag = std::max (mag, std::abs (y));
    }
    return 20.0 * std::log10 (mag);
}
} // namespace

int main()
{
    int failures = 0;

    std::printf ("Treble network validation (TREB=12.5k)\n");
    for (double f : { 100.0, 500.0, 1000.0, 5000.0, 10000.0, 15000.0 })
    {
        const double meas = trebMeasureDB (f, 12.5e3);
        const double want = trebAnalyticDB (f, 12.5e3);
        const double err = std::abs (meas - want);
        std::printf ("  %7.1f Hz : WDF %+7.3f | analytic %+7.3f | err %.4f %s\n",
                     f, meas, want, err, err > 0.1 ? " <-- FAIL" : "");
        if (err > 0.1)
            ++failures;
    }

    std::printf ("\nStage 2 (IC1_B) validation\n");
    for (double f : { 100.0, 1000.0, 5000.0, 7200.0, 10000.0, 15000.0 })
    {
        const double meas = s2MeasureDB (f);
        const double want = s2AnalyticDB (f);
        const double err = std::abs (meas - want);
        std::printf ("  %7.1f Hz : WDF %+7.3f | analytic %+7.3f | err %.4f %s\n",
                     f, meas, want, err, err > 0.1 ? " <-- FAIL" : "");
        if (err > 0.1)
            ++failures;
    }

    // DC gains + polarity (step response).
    {
        tommy::dsp::TrebleNetwork t;
        t.prepare (fs);
        t.setParams (12.5e3);
        double yt = 0.0;
        for (int i = 0; i < (int) fs; ++i)
            yt = t.processSample (1.0);
        std::printf ("\n[Treble DC]  step +1 -> %.5f (expect ~+1, unity passthrough)\n", yt);
        if (yt < 0.99 || yt > 1.01)
            ++failures;

        tommy::dsp::Stage2 s;
        s.prepare (fs);
        double ys = 0.0;
        for (int i = 0; i < (int) fs; ++i)
            ys = s.processSample (1.0);
        std::printf ("[Stage2 DC]  step +1 -> %.5f (expect ~+2.0, non-inverting +6 dB)\n", ys);
        if (ys < 1.98 || ys > 2.02)
            ++failures;
    }

    std::printf ("\n%s\n", failures == 0 ? "PASS" : "FAIL");
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
