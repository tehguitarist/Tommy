// Throwaway probe (2026-06-18): quantify the Stage-1 DRIVE taper floor bug and its effect on the
// linear chain gain + unity-volume position. Linear stages only (Stage1 at min drive is ~clean,
// so no oversampler/clipping needed). Pure chowdsp_wdf — compile standalone.

#include "../src/dsp/Stage1.h"
#include "../src/dsp/Stage2.h"
#include "../src/dsp/TrebleNetwork.h"

#include <cmath>
#include <cstdio>
#include <vector>

using namespace tommy::dsp;

namespace
{
constexpr double fs = 48000.0;
constexpr int N = 8192;

// Audio taper helpers (mirror TaperUtils so the probe is self-contained).
double audioTaperR (double x, double rMax)
{
    if (x <= 0.0) return rMax * 0.01;
    if (x >= 1.0) return rMax;
    return rMax * std::pow (10.0, 2.0 * x - 2.0);
}
double bassR (double x)  { return audioTaperR (x, 50.0e3); }
double trebR (double x)
{
    const double ra = audioTaperR (x, 50.0e3);
    return (ra * 50.0e3) / (ra + 50.0e3);
}
double driveOld (double x) { return audioTaperR (x, 1.0e6); }                 // current (1% floor)
double driveNew (double x)                                                    // anchored to 0 at min
{
    if (x <= 0.0) return 0.0;
    if (x >= 1.0) return 1.0e6;
    return 1.0e6 * (std::pow (10.0, 2.0 * x - 2.0) - 0.01) / 0.99;
}

double volumeGain (double x)
{
    constexpr double rTotal = 25.0e3, r11 = 7.5e3;
    const double frac = (x <= 0.0) ? 0.0 : std::pow (10.0, 2.0 * x - 2.0);
    const double rLow = frac * rTotal;
    const double rUp = (1.0 - frac) * rTotal;
    const double rUpPar = (rUp * r11) / (rUp + r11);
    return rLow / (rUpPar + rLow);
}

// RMS chain gain (linear, volts in -> volts out) at 1 kHz, min bass/treble, mode Open (Medium).
double chainGain (double driveOhms, double amp)
{
    Stage1 s1;
    TrebleNetwork tr;
    Stage2 s2;
    s1.prepare (fs); tr.prepare (fs); s2.prepare (fs);
    s1.setParams (bassR (0.0), driveOhms);
    s1.setMode (Stage1::ClipMode::Medium);
    tr.setParams (trebR (0.0));

    double sumIn = 0.0, sumOut = 0.0;
    for (int blk = 0; blk < 4; ++blk)
        for (int i = 0; i < N; ++i)
        {
            const double t = (double) (blk * N + i) / fs;
            const double in = amp * std::sin (2.0 * M_PI * 1000.0 * t);
            const double out = s2.processSample (tr.processSample (s1.processSample (in)));
            if (blk == 3) { sumIn += in * in; sumOut += out * out; }
        }
    return std::sqrt (sumOut / sumIn);
}

// Volume rotation where output = input (unity), given chain gain G and output makeup.
double unityVolPos (double G, double makeup)
{
    for (double x = 0.0; x <= 1.0; x += 0.001)
        if (G * makeup * volumeGain (x) >= 1.0)
            return x;
    return 1.0; // never reaches unity within range
}
const char* clockOf (double x) // rough o'clock for a 7→5 (270°) knob
{
    static char buf[8];
    const double deg = x * 270.0; // 0 = 7 o'clock
    const int oclock = (int) std::lround (7 + deg / 30.0);
    std::snprintf (buf, sizeof buf, "%d", ((oclock - 1) % 12) + 1);
    return buf;
}
} // namespace

int main()
{
    std::printf ("DRIVE floor probe — min bass/treble, Open mode, 1 kHz\n\n");

    const double gOldMin = chainGain (driveOld (0.0), 0.01);
    const double gNewMin = chainGain (driveNew (0.0), 0.01);
    std::printf ("min-drive chain gain (lin): OLD(floor 10k)=%.3fx (%.1f dB) | NEW(0R)=%.3fx (%.1f dB)\n",
                 gOldMin, 20 * std::log10 (gOldMin), gNewMin, 20 * std::log10 (gNewMin));
    std::printf ("  => fix reduces min-drive gain by %.1f dB\n\n", 20 * std::log10 (gNewMin / gOldMin));

    std::printf ("unity-volume position (rotation / ~o'clock):\n");
    for (double mk : { 0.5, 0.7, 1.0, 1.2 })
    {
        const double xo = unityVolPos (gOldMin, mk);
        const double xn = unityVolPos (gNewMin, mk);
        std::printf ("  makeup %.2f:  OLD x=%.2f (~%s o'c) | NEW x=%.2f (~%s o'c)\n",
                     mk, xo, clockOf (xo), xn, clockOf (xn));
    }

    // High-drive headroom: peak chain gain at full drive (still linear probe, small input).
    const double gMaxOld = chainGain (driveOld (1.0), 0.001);
    const double gMaxNew = chainGain (driveNew (1.0), 0.001);
    std::printf ("\nfull-drive linear gain: OLD=%.0fx | NEW=%.0fx (unchanged at top, as expected)\n",
                 gMaxOld, gMaxNew);
    return 0;
}
