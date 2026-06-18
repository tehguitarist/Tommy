// Stage 2 rail probe: measures the peak voltage at node_J (IC1_B op-amp output) across the
// realistic operating space, so we can decide (a) whether Stage 2 actually reaches its ~+2.2/-3.1V
// rails in normal use and (b) what clip threshold/knee to model. TommyDSP::processBlock returns
// node_J directly (VOL + output makeup are applied later in the processor), so the chain output in
// volts IS the Stage 2 op-amp output. Not a pass/fail test — a measurement table.
//
// Reference levels: guitar input float == volts. -12 dBu ~= 0.275 V peak. Light pick ~0.05-0.1 V,
// hot humbucker hard strum ~0.5-0.8 V. JRC4559 on 9V/VREF~4.6V => est. rails +2.2 / -3.1 V.

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

// Peak and asymmetry (max positive / max |negative|) of node_J for a sine at (freq, amp) and the
// given control settings. Captures the asymmetry because Hard mode + Stage 2 gain pushes the two
// polarities differently against the rails.
struct Probe
{
    double peak, posPeak, negPeak;
};

Probe runProbe (double bassX, double driveX, double trebX, int clipIdx, double amp, double freq)
{
    TommyDSP dsp;
    dsp.prepare (fs, N, 3 /*8x*/);
    dsp.setControls (tp::bassResistance (bassX), tp::driveResistance (driveX),
                     tp::trebleResistance (trebX), static_cast<Stage1::ClipMode> (1 + clipIdx));

    std::vector<double> buf ((size_t) N);
    Probe p { 0.0, 0.0, 0.0 };
    for (int blk = 0; blk < 8; ++blk) // warm up RC state, measure last block
    {
        for (int i = 0; i < N; ++i)
            buf[(size_t) i] = amp * std::sin (2.0 * M_PI * freq * (double) (blk * N + i) / fs);
        dsp.processBlock (buf.data(), N);
        if (blk == 7)
            for (int i = 0; i < N; ++i)
            {
                const double v = buf[(size_t) i];
                p.peak = std::max (p.peak, std::abs (v));
                p.posPeak = std::max (p.posPeak, v);
                p.negPeak = std::max (p.negPeak, -v);
            }
    }
    return p;
}
} // namespace

int main()
{
    const char* modes[3] = { "Soft", "Med ", "Hard" };
    const double amps[] = { 0.05, 0.1, 0.2, 0.275, 0.5, 0.8 };
    const double drives[] = { 0.3, 0.6, 0.9, 1.0 };

    std::printf ("Stage 2 (node_J) peak voltage probe — est. rails +2.2 / -3.1 V\n");
    std::printf ("bass=0.5, treble=0.5, 8x OS.  Columns: peak (pos / neg)\n\n");

    for (double freq : { 1000.0, 120.0 }) // 1 kHz, and 120 Hz where the bass boost drives hardest
    {
        std::printf ("=== %.0f Hz ===\n", freq);
        std::printf ("  in(V) |");
        for (int m = 0; m < 3; ++m)
            for (double d : drives)
                std::printf ("  %s d%.1f       |", modes[m], d);
        std::printf ("\n");

        for (double amp : amps)
        {
            std::printf ("  %.3f |", amp);
            for (int m = 0; m < 3; ++m)
                for (double d : drives)
                {
                    const Probe p = runProbe (0.5, d, 0.5, m, amp, freq);
                    std::printf (" %4.2f(%.2f/%.2f)|", p.peak, p.posPeak, p.negPeak);
                }
            std::printf ("\n");
        }
        std::printf ("\n");
    }

    // Worst case: bass maxed (max LF gain), hottest input, full drive, low freq.
    std::printf ("=== worst case (bass=1.0, treble=0.5, in=0.8V, drive=1.0, 120 Hz) ===\n");
    for (int m = 0; m < 3; ++m)
    {
        const Probe p = runProbe (1.0, 1.0, 0.5, m, 0.8, 120.0);
        std::printf ("  %s : peak %.2f V  (pos %.2f / neg %.2f)\n", modes[m], p.peak, p.posPeak, p.negPeak);
    }

    return 0;
}
