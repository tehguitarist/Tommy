// OS-factor fidelity probe (v1.1): how close is the plugin at 1x / 2x / 4x to 8x (the reference
// "truth")? Most DAW users sit at 1x or 2x, so the goal is that low OS already sounds close, with
// high OS only refining — and to pin down what ONLY oversampling can fix.
//
// Measures, through the REAL full TommyDSP chain at fs=48 kHz:
//   A. Frequency response (small-signal, diodes off): top-octave magnitude vs OS factor. This is
//      governed by the C5/C11 prewarp at base rate, so it shows how much top octave 1x/2x lose
//      that prewarp can't recover (only OS fixes the last octave).
//   B. Harmonic distortion fidelity at a hot clipping setting: the in-band HARMONIC energy (the
//      wanted distortion — should be ~constant across OS) vs the INHARMONIC/aliasing energy (the
//      unwanted foldback — this is the part only oversampling removes), for Soft and Hard.
//
// Reference is 8x; deltas are vs 8x. Not a pass/fail gate — a measurement probe (finite-only).

#include "../src/dsp/TommyDSP.h"
#include "../src/utils/TaperUtils.h"

#include <juce_dsp/juce_dsp.h>

#include <array>
#include <cmath>
#include <cstdio>
#include <vector>

namespace tp = tommy::taper;
using tommy::dsp::ClipMode;
using tommy::dsp::TommyDSP;

namespace
{
constexpr double fs = 48000.0;
bool gAllFinite = true;

const double kBassR = tp::bassResistance (0.5);
const double kDriveR = tp::driveResistance (0.7);
const double kTrebR = tp::trebleResistance (0.5);

void checkFinite (const std::vector<double>& v)
{
    for (double x : v)
        gAllFinite = gAllFinite && std::isfinite (x);
}

void configure (TommyDSP& d, int factorLog2, ClipMode mode, int maxBlock = 512)
{
    d.prepare (fs, maxBlock, factorLog2);
    d.setControls (kBassR, kDriveR, kTrebR, mode);
    d.setSupplyVoltage (9.0);
    d.setAdaaEnabled (true);
}

// --- A. small-signal magnitude (dB) at `freq` through the full chain (diodes off at amp=1e-3) ---
double magDB (int factorLog2, double freq)
{
    TommyDSP d;
    configure (d, factorLog2, ClipMode::Soft); // diodes don't conduct at this level => linear path

    constexpr int blockSize = 512;
    const int total = (int) (1.0 * fs), warmup = (int) (0.5 * fs);
    const double amp = 1.0e-3;
    std::vector<double> block ((size_t) blockSize);
    double inPow = 0.0, outPow = 0.0;
    int idx = 0;
    for (int p = 0; p < total; p += blockSize)
    {
        const int n = std::min (blockSize, total - p);
        const int baseIdx = idx;
        for (int i = 0; i < n; ++i, ++idx)
            block[(size_t) i] = amp * std::sin (2.0 * M_PI * freq * (double) idx / fs);
        d.processBlock (block.data(), n);
        for (int i = 0; i < n; ++i)
            if (baseIdx + i >= warmup)
            {
                const double s = amp * std::sin (2.0 * M_PI * freq * (double) (baseIdx + i) / fs);
                inPow += s * s;
                outPow += block[(size_t) i] * block[(size_t) i];
            }
    }
    checkFinite (block);
    return 10.0 * std::log10 (outPow / inPow);
}

// --- B. harmonic vs inharmonic (aliasing) energy (dB re fundamental) at a hot clip setting ------
struct Distortion
{
    double thdDB;   // in-band harmonic energy / fundamental (the wanted distortion)
    double aliasDB; // in-band inharmonic energy / fundamental (only OS removes this)
};

Distortion distortion (int factorLog2, ClipMode mode)
{
    constexpr int N = 16384;
    TommyDSP d;
    configure (d, factorLog2, mode, N);

    constexpr double f0 = 2186.0; // non-divisor of fs so aliases land off the harmonic grid
    const double amp = 0.6;       // well into clipping at DRIVE=0.7
    const int total = 4 * N;
    std::vector<double> buf ((size_t) total);
    for (int i = 0; i < total; ++i)
        buf[(size_t) i] = amp * std::sin (2.0 * M_PI * f0 * (double) i / fs);
    for (int off = 0; off < total; off += N)
        d.processBlock (buf.data() + off, N);
    checkFinite (buf);

    const int order = 13, fftSize = 1 << order;
    juce::dsp::FFT fft (order);
    juce::dsp::WindowingFunction<float> win ((size_t) fftSize,
                                             juce::dsp::WindowingFunction<float>::blackmanHarris);
    std::vector<float> fd ((size_t) (2 * fftSize), 0.0f);
    for (int i = 0; i < fftSize; ++i)
        fd[(size_t) i] = (float) buf[(size_t) (total - fftSize + i)];
    win.multiplyWithWindowingTable (fd.data(), (size_t) fftSize);
    fft.performFrequencyOnlyForwardTransform (fd.data());

    const double binHz = fs / (double) fftSize;
    const int nyqBin = fftSize / 2, guard = 6;
    std::vector<bool> isH ((size_t) (nyqBin + 1), false);
    for (int k = 1; k * f0 < fs / 2.0; ++k)
    {
        const int hb = (int) std::lround (k * f0 / binHz);
        for (int b = hb - guard; b <= hb + guard; ++b)
            if (b >= 0 && b <= nyqBin)
                isH[(size_t) b] = true;
    }
    const int fundBin = (int) std::lround (f0 / binHz);
    double fundPow = 0.0;
    for (int b = fundBin - guard; b <= fundBin + guard; ++b)
        fundPow += (double) fd[(size_t) b] * (double) fd[(size_t) b];

    const int lo = (int) std::lround (50.0 / binHz), hi = std::min (nyqBin, (int) std::lround (18000.0 / binHz));
    double harmPow = 0.0, aliasPow = 0.0;
    for (int b = lo; b <= hi; ++b)
    {
        const double p = (double) fd[(size_t) b] * (double) fd[(size_t) b];
        if (isH[(size_t) b])
        {
            if (std::abs (b - fundBin) > guard) // exclude the fundamental itself
                harmPow += p;
        }
        else
            aliasPow += p;
    }
    return { 10.0 * std::log10 (harmPow / fundPow), 10.0 * std::log10 (aliasPow / fundPow) };
}
} // namespace

int main()
{
    std::printf ("Tommy OS-factor fidelity vs 8x reference (fs=%.0f, full chain)\n", fs);
    std::printf ("Settings: BASS=0.5 DRIVE=0.7 TREBLE=0.5\n\n");

    static const int factors[] = { 0, 1, 2, 3 }; // 1x 2x 4x 8x
    auto fname = [] (int f) { return std::to_string (1 << f) + "x"; };

    // === A. Frequency response (small signal) ===
    std::printf ("== A. Frequency response, small signal (dB; delta = vs 8x) ==\n");
    static const double freqs[] = { 100.0, 1000.0, 4000.0, 8000.0, 12000.0, 16000.0 };
    std::printf ("   %-8s", "freq");
    for (int f : factors)
        std::printf ("  %7s", fname (f).c_str());
    std::printf ("  | %s\n", "delta 1x/2x/4x vs 8x");
    for (double fr : freqs)
    {
        std::array<double, 4> m {};
        for (int i = 0; i < 4; ++i)
            m[(size_t) i] = magDB (factors[i], fr);
        std::printf ("   %6.0fHz", fr);
        for (double v : m)
            std::printf ("  %7.2f", v);
        std::printf ("  | %+5.2f %+5.2f %+5.2f\n", m[0] - m[3], m[1] - m[3], m[2] - m[3]);
    }

    // === B. Distortion fidelity (harmonic = wanted; aliasing = only-OS-fixes) ===
    auto distRow = [&] (const char* label, ClipMode mode)
    {
        std::array<Distortion, 4> dd {};
        for (int i = 0; i < 4; ++i)
            dd[(size_t) i] = distortion (factors[i], mode);
        std::printf ("   %-6s harmonic", label);
        for (auto& x : dd)
            std::printf ("  %7.2f", x.thdDB);
        std::printf ("  (delta %+.2f vs 8x)\n", dd[0].thdDB - dd[3].thdDB);
        std::printf ("   %-6s aliasing", "");
        for (auto& x : dd)
            std::printf ("  %7.2f", x.aliasDB);
        std::printf ("  (1x %+.1f dB worse than 8x)\n", dd[0].aliasDB - dd[3].aliasDB);
    };

    std::printf ("\n== B. Distortion at hot drive (dB re fundamental; harmonic=wanted, aliasing=foldback) ==\n");
    std::printf ("   %-15s", "");
    for (int f : factors)
        std::printf ("  %7s", fname (f).c_str());
    std::printf ("\n");
    distRow ("Soft", ClipMode::Soft);
    distRow ("Hard", ClipMode::Hard);

    std::printf ("\nReading it: harmonic energy ~constant across OS = the tone/THD is faithful at low OS.\n");
    std::printf ("Aliasing is what climbs at low OS — that, and the last-octave FR, are the OS-only fixes.\n");

    std::printf ("\n%s\n", gAllFinite ? "PASS: all configurations produced finite output."
                                      : "FAIL: non-finite output detected.");
    return gAllFinite ? 0 : 1;
}
