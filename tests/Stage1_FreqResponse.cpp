// Step 4 validation: Stage 1 (IC1_A, non-inverting drive stage), linear (no diodes).
//
// Validates the WDF model against the analytic non-inverting transfer function
//   H(jw) = 1 + Zf(jw)/Zg(jw)
// computed independently with std::complex from the same component values, plus DC polarity
// and the BASS/DRIVE interactive behaviour.

#include "../src/dsp/Stage1.h"

#include <cmath>
#include <complex>
#include <cstdio>
#include <cstdlib>

namespace
{
constexpr double R3 = 3.3e3, C3 = 39.0e-9, C4 = 1.0e-6;
constexpr double R7 = 3.3e3, C1 = 100.0e-12;

using cplx = std::complex<double>;

// Analytic non-inverting gain magnitude (dB) at a given frequency and pot resistances.
// The WDF CapacitorT is a trapezoidal (bilinear) discretisation, so a discrete cap behaves
// like an ideal cap at the *prewarped* frequency w_warp = (2/T) tan(wT/2). Using w_warp here
// makes the analytic reference match the WDF to numerical precision across the whole band,
// confirming the model is exact (not merely approximate).
double analyticGainDB (double f, double bassR, double driveR)
{
    const double fs = 96000.0;
    const double w = 2.0 * M_PI * f;
    const double wWarp = (2.0 * fs) * std::tan (w / (2.0 * fs)); // bilinear prewarp for caps
    const cplx j (0.0, 1.0);
    auto Zc = [&] (double C) { return 1.0 / (j * wWarp * C); };

    const cplx zg = R3 + (Zc (C3) * (bassR + Zc (C4))) / (Zc (C3) + (bassR + Zc (C4)));
    const cplx zf = ((R7 + driveR) * Zc (C1)) / ((R7 + driveR) + Zc (C1));
    const cplx H = 1.0 + zf / zg;
    return 20.0 * std::log10 (std::abs (H));
}

double measureGainDB (double f, double fs, double bassR, double driveR)
{
    tommy::dsp::Stage1 s;
    s.prepare (fs);
    s.setRailClampEnabled (false); // measure the pure linear transfer function (no rail saturation)
    s.setParams (bassR, driveR);

    const int n = (int) fs; // 1 second
    double mag = 0.0;
    for (int i = 0; i < n; ++i)
    {
        const double x = std::sin (2.0 * M_PI * f * (double) i / fs);
        const double y = s.processSample (x);
        if (i > n / 2) // measure after settling
            mag = std::max (mag, std::abs (y));
    }
    return 20.0 * std::log10 (mag);
}
} // namespace

int main()
{
    constexpr double fs = 96000.0;
    int failures = 0;

    std::printf ("Stage 1 (IC1_A non-inverting drive) validation\n");

    // --- 1. Frequency response vs analytic transfer function (BASS mid, DRIVE mid) ---
    {
        const double bassR = 25.0e3, driveR = 500.0e3;
        std::printf ("\n[Freq response vs analytic]  BASS=%.0f ohm  DRIVE=%.0f ohm\n", bassR, driveR);
        for (double f : { 50.0, 100.0, 500.0, 1000.0, 3000.0, 8000.0, 15000.0 })
        {
            const double meas = measureGainDB (f, fs, bassR, driveR);
            const double want = analyticGainDB (f, bassR, driveR);
            const double err = std::abs (meas - want);
            std::printf ("  %7.1f Hz : WDF %+7.3f dB | analytic %+7.3f dB | err %.4f dB %s\n",
                         f, meas, want, err, err > 0.2 ? "  <-- FAIL" : "");
            if (err > 0.2)
                ++failures;
        }
    }

    // --- 2. DC polarity: positive step -> positive output, ~unity gain at DC ---
    {
        tommy::dsp::Stage1 s;
        s.prepare (fs);
        s.setRailClampEnabled (false);
        s.setParams (25.0e3, 500.0e3);
        double y = 0.0;
        for (int i = 0; i < (int) fs; ++i) // settle 1s (caps charge)
            y = s.processSample (1.0);
        std::printf ("\n[DC polarity]  step +1.0 -> %.6f  (expect ~+1.0, non-inverting)\n", y);
        if (y < 0.9 || y > 1.1)
        {
            std::fprintf (stderr, "FAIL: DC gain/polarity wrong (non-inverting unity expected at DC)\n");
            ++failures;
        }
    }

    // --- 3. DRIVE interaction: more DRIVE resistance -> more gain at 1 kHz ---
    {
        const double f = 1000.0, bassR = 25.0e3;
        const double gLow = measureGainDB (f, fs, bassR, 10.0e3);
        const double gHigh = measureGainDB (f, fs, bassR, 1.0e6);
        std::printf ("\n[DRIVE interaction @1kHz]  DRIVE 10k -> %+.3f dB | DRIVE 1M -> %+.3f dB\n", gLow, gHigh);
        if (!(gHigh > gLow + 6.0))
        {
            std::fprintf (stderr, "FAIL: increasing DRIVE did not meaningfully increase gain\n");
            ++failures;
        }
    }

    // --- 4. BASS interaction: BASS resistance changes low-frequency gain ---
    {
        const double f = 100.0, driveR = 500.0e3;
        const double gLowBassR = measureGainDB (f, fs, 1.0e3, driveR);  // small R -> more C4 path
        const double gHighBassR = measureGainDB (f, fs, 50.0e3, driveR);
        std::printf ("\n[BASS interaction @100Hz]  BASS 1k -> %+.3f dB | BASS 50k -> %+.3f dB\n",
                     gLowBassR, gHighBassR);
        if (std::abs (gLowBassR - gHighBassR) < 1.0)
        {
            std::fprintf (stderr, "FAIL: BASS control had no meaningful effect on low-frequency gain\n");
            ++failures;
        }
    }

    std::printf ("\n%s\n", failures == 0 ? "PASS" : "FAIL");
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
