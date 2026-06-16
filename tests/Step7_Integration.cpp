// Step 7 validation: full DSP chain (TommyDSP) integration — control effects, clipping,
// stability across all clip modes and oversampling factors. Uses the taper mappings the
// processor uses. Values are in "volts" (the processor treats input float as volts).

#include "../src/dsp/TommyDSP.h"
#include "../src/utils/TaperUtils.h"

#include <cmath>
#include <cstdio>
#include <vector>

using tommy::dsp::TommyDSP;
using tommy::dsp::Stage1;
namespace tp = tommy::taper;

namespace
{
constexpr double fs = 48000.0;
constexpr int N = 4096;

// Returns peak |output| of a 1 kHz sine through the chain at the given control settings.
double runPeak (double bassX, double driveX, double trebX, int clipIdx, int factorLog2,
                double amp, bool& finite)
{
    TommyDSP dsp;
    dsp.prepare (fs, N, factorLog2);
    dsp.setControls (tp::bassResistance (bassX), tp::driveResistance (driveX),
                     tp::trebleResistance (trebX),
                     static_cast<Stage1::ClipMode> (1 + clipIdx));

    std::vector<double> buf ((size_t) N);
    double peak = 0.0;
    finite = true;
    for (int blk = 0; blk < 6; ++blk) // warm up + measure (continuous phase)
    {
        for (int i = 0; i < N; ++i)
            buf[(size_t) i] = amp * std::sin (2.0 * M_PI * 1000.0 * (double) (blk * N + i) / fs);
        dsp.processBlock (buf.data(), N);
        if (blk == 5)
            for (int i = 0; i < N; ++i)
            {
                if (! std::isfinite (buf[(size_t) i]))
                    finite = false;
                peak = std::max (peak, std::abs (buf[(size_t) i]));
            }
    }
    return peak;
}
} // namespace

int main()
{
    int failures = 0;
    std::printf ("Step 7: full chain (TommyDSP) integration\n\n");

    bool fin = true;

    // 1. Clean-ish: low drive, small input -> amplified but not hard clipped, finite.
    {
        const double pk = runPeak (0.5, 0.1, 0.5, 0 /*Soft*/, 3 /*8x*/, 0.05, fin);
        std::printf ("[clean] low drive, 0.05V in -> peak %.3f V  (finite=%d)\n", pk, fin);
        if (! fin || pk < 0.05 || pk > 3.5)
            ++failures;
    }

    // 2. Driven: high drive + hot input -> clipping bounds the output well below linear blow-up.
    {
        const double pk = runPeak (0.5, 0.95, 0.5, 0 /*Soft*/, 3, 0.5, fin);
        std::printf ("[driven] high drive, 0.5V in -> peak %.3f V  (finite=%d, bounded by rails)\n", pk, fin);
        if (! fin || pk > 7.0) // Stage2 (x2) of rail-clamped Stage1 (<=3.1V) => <=~6.2V
            ++failures;
    }

    // 3. DRIVE has an effect: more drive -> more output (at fixed small input, before heavy clip).
    {
        const double lo = runPeak (0.5, 0.2, 0.5, 0, 3, 0.02, fin);
        const double hi = runPeak (0.5, 0.9, 0.5, 0, 3, 0.02, fin);
        std::printf ("[drive effect] 0.02V in: drive 0.2 -> %.4f V | drive 0.9 -> %.4f V\n", lo, hi);
        if (! (hi > lo * 1.5))
            ++failures;
    }

    // 4. TREBLE has an effect at HF: compare peak of a 6 kHz tone at min vs max treble.
    {
        auto run6k = [&] (double trebX)
        {
            TommyDSP dsp;
            dsp.prepare (fs, N, 3);
            dsp.setControls (tp::bassResistance (0.5), tp::driveResistance (0.3),
                             tp::trebleResistance (trebX), Stage1::ClipMode::Soft);
            std::vector<double> buf ((size_t) N);
            double peak = 0.0;
            for (int blk = 0; blk < 6; ++blk)
            {
                for (int i = 0; i < N; ++i)
                    buf[(size_t) i] = 0.05 * std::sin (2.0 * M_PI * 6000.0 * (double) (blk * N + i) / fs);
                dsp.processBlock (buf.data(), N);
                if (blk == 5)
                    for (int i = 0; i < N; ++i)
                        peak = std::max (peak, std::abs (buf[(size_t) i]));
            }
            return peak;
        };
        const double dark = run6k (0.0); // max cut
        const double bright = run6k (1.0); // min cut
        std::printf ("[treble effect] 6kHz: treble=0 -> %.4f V | treble=1 -> %.4f V\n", dark, bright);
        if (! (bright > dark * 1.3))
            ++failures;
    }

    // 5. Stability: every clip mode x every oversampling factor stays finite under hot drive.
    {
        std::printf ("[stability] all modes x all OS factors:\n");
        const char* names[3] = { "Soft", "Medium", "Hard" };
        for (int clip = 0; clip < 3; ++clip)
            for (int f = 0; f <= 3; ++f)
            {
                const double pk = runPeak (0.7, 0.9, 0.4, clip, f, 0.6, fin);
                if (! fin)
                {
                    std::printf ("    %-6s %dx: NON-FINITE\n", names[clip], 1 << f);
                    ++failures;
                }
            }
        std::printf ("    all finite: %s\n", failures == 0 ? "yes" : "NO");
    }

    std::printf ("\n%s\n", failures == 0 ? "PASS" : "FAIL");
    return failures == 0 ? 0 : 1;
}
