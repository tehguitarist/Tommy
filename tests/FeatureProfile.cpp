// Feature CPU-vs-accuracy profiler (v1.1 optimisation pass — informs the "HQ mode" decision).
//
// For each performance-affecting DSP feature, this measures BOTH its CPU cost and its accuracy
// contribution, so each can be classified:
//   - "free win"  : negligible accuracy change when made cheaper  -> always use the cheap path
//   - "HQ knob"   : real accuracy gain for real CPU               -> candidate for an HQ toggle
//
// Features profiled:
//   1. Diode Wright-omega solver:  AccurateOmega  vs  chowdsp omega4 (fast bit-trick).
//   2. Rail-clip ADAA:             on vs off (aliasing reduction on the hard op-amp rail clip).
//   3. Treble+Stage2 oversampling: run those linear stages INSIDE the OS region (shipped) vs at
//                                  base rate (cheaper) — top-octave accuracy vs CPU.
//   4. Diode mismatch:             CPU of the per-polarity Vt asymmetry (faithfulness feature).
//
// Not a pass/fail accuracy gate — it is a measurement probe (registered with ctest only to assert
// finite output; CI runner speed varies too much to gate on absolute CPU %). Run it directly to
// read the table. CPU figures are single-channel, Release build, fs=48 kHz.

#include "../src/dsp/ClippingOversampler.h"
#include "../src/dsp/Stage1.h"
#include "../src/dsp/Stage2.h"
#include "../src/dsp/TommyDSP.h"
#include "../src/dsp/TrebleNetwork.h"
#include "../src/utils/TaperUtils.h"

#include <juce_dsp/juce_dsp.h>

#include <chrono>
#include <cmath>
#include <cstdio>
#include <vector>

namespace tp = tommy::taper;
using tommy::dsp::AccurateOmega;
using tommy::dsp::ClipMode;
using tommy::dsp::ClippingOversamplerT;
using tommy::dsp::Stage1T;
using tommy::dsp::Stage2;
using tommy::dsp::TommyDSPT;
using tommy::dsp::TrebleNetwork;

using FastOmega = chowdsp::Omega::Omega; // omega4 (default chowdsp provider)

namespace
{
constexpr double fs = 48000.0;
bool gAllFinite = true;

// Realistic, clipping-engaged control settings (same as PerfBenchmark) so we measure the real
// nonlinear cost, not an idle best case.
const double kBassR = tp::bassResistance (0.5);
const double kDriveR = tp::driveResistance (0.7);
const double kTrebR = tp::trebleResistance (0.5);

double sineSample (int i, double freq, double amp)
{
    return amp * std::sin (2.0 * M_PI * freq * (double) i / fs);
}

double now()
{
    using namespace std::chrono;
    return duration<double> (steady_clock::now().time_since_epoch()).count();
}

void checkFinite (const std::vector<double>& v)
{
    for (double x : v)
        gAllFinite = gAllFinite && std::isfinite (x);
}

// ---- 1 & 4: full-chain CPU for a given omega provider + ADAA/mismatch settings --------------
template <typename Omega>
double fullChainCpuPercent (int factorLog2, ClipMode mode, bool adaa, double symMis, double asymMis)
{
    constexpr int blockSize = 512;
    constexpr double renderSeconds = 4.0;
    const int totalSamples = (int) (renderSeconds * fs);

    TommyDSPT<Omega> dsp;
    dsp.prepare (fs, blockSize, factorLog2);
    dsp.setControls (kBassR, kDriveR, kTrebR, mode);
    dsp.setSupplyVoltage (9.0);
    dsp.setAdaaEnabled (adaa);
    dsp.setSymMismatch (symMis);
    dsp.setAsymMismatch (asymMis);

    std::vector<double> block ((size_t) blockSize);
    const double t0 = now();
    int idx = 0;
    std::vector<double> tail;
    for (int p = 0; p < totalSamples; p += blockSize)
    {
        const int n = std::min (blockSize, totalSamples - p);
        for (int i = 0; i < n; ++i, ++idx)
            block[(size_t) i] = sineSample (idx, 1000.0, 0.6);
        dsp.processBlock (block.data(), n);
    }
    const double wall = now() - t0;
    block.resize ((size_t) blockSize);
    checkFinite (block);
    return wall / ((double) totalSamples / fs) * 100.0;
}

// Null error of fast omega vs accurate omega through the full chain (dB). This IS the distortion
// the fast solver introduces relative to the accurate reference.
double omegaNullErrorDB (int factorLog2, ClipMode mode)
{
    constexpr int blockSize = 512;
    const int total = (int) (2.0 * fs);

    TommyDSPT<AccurateOmega> acc;
    TommyDSPT<FastOmega> fast;
    acc.prepare (fs, blockSize, factorLog2);
    fast.prepare (fs, blockSize, factorLog2);
    acc.setControls (kBassR, kDriveR, kTrebR, mode);
    fast.setControls (kBassR, kDriveR, kTrebR, mode);
    acc.setSupplyVoltage (9.0);
    fast.setSupplyVoltage (9.0);
    acc.setAdaaEnabled (true);
    fast.setAdaaEnabled (true);

    std::vector<double> a ((size_t) blockSize), b ((size_t) blockSize);
    double sigPow = 0.0, errPow = 0.0;
    const int warmup = (int) (0.5 * fs);
    int idx = 0;
    for (int p = 0; p < total; p += blockSize)
    {
        const int n = std::min (blockSize, total - p);
        for (int i = 0; i < n; ++i, ++idx)
            a[(size_t) i] = b[(size_t) i] = sineSample (idx, 1000.0, 0.6);
        acc.processBlock (a.data(), n);
        fast.processBlock (b.data(), n);
        if (p >= warmup)
            for (int i = 0; i < n; ++i)
            {
                const double ref = a[(size_t) i], err = b[(size_t) i] - a[(size_t) i];
                sigPow += ref * ref;
                errPow += err * err;
            }
    }
    checkFinite (a);
    checkFinite (b);
    return 10.0 * std::log10 (errPow / sigPow);
}

// ---- 2: aliasing measurement (reused Step6 method) for ADAA on/off --------------------------
double aliasingDB (ClipMode mode, int factorLog2, bool adaa, double amp, double driveR)
{
    constexpr int N = 16384;
    ClippingOversamplerT<AccurateOmega> os;
    os.prepare (fs, N, factorLog2);
    os.setMode (mode);
    os.setParams (kBassR, driveR);
    os.setAdaaEnabled (adaa);

    constexpr double f0 = 2186.0;
    const int total = 4 * N;
    std::vector<double> buf ((size_t) total);
    for (int i = 0; i < total; ++i)
        buf[(size_t) i] = amp * std::sin (2.0 * M_PI * f0 * (double) i / fs);
    for (int off = 0; off < total; off += N)
        os.processBlock (buf.data() + off, N);
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
    double aliasPow = 0.0;
    const int lo = (int) std::lround (50.0 / binHz), hi = std::min (nyqBin, (int) std::lround (18000.0 / binHz));
    for (int b = lo; b <= hi; ++b)
        if (! isH[(size_t) b])
            aliasPow += (double) fd[(size_t) b] * (double) fd[(size_t) b];
    return 10.0 * std::log10 (aliasPow / fundPow);
}

// ---- 3: Treble+Stage2 inside the OS region (shipped) vs at base rate -------------------------
// Returns linear magnitude (dB) at `freq` for a small-signal (Linear clip mode) sweep, so the
// chain is purely linear and we isolate the top-octave discretisation behaviour.
struct PostChainResult
{
    double magDB;
    double cpuPercent;
};

PostChainResult postChainMag (int factorLog2, double freq, bool oversamplePost)
{
    constexpr int blockSize = 512;
    ClippingOversamplerT<AccurateOmega> os;
    TrebleNetwork treble;
    Stage2 stage2;
    os.prepare (fs, blockSize, factorLog2);
    os.setMode (ClipMode::Linear); // linear => isolate the linear top-octave response
    os.setParams (kBassR, kDriveR);
    treble.setParams (kTrebR);

    const double postRate = oversamplePost ? os.getOversampledRate() : fs;
    treble.prepare (postRate);
    stage2.prepare (postRate);

    const int total = (int) (1.0 * fs);
    const int warmup = (int) (0.5 * fs);
    std::vector<double> block ((size_t) blockSize);
    double inPow = 0.0, outPow = 0.0;
    int idx = 0;
    const double amp = 1.0e-3; // small => no clipping

    const double t0 = now();
    for (int p = 0; p < total; p += blockSize)
    {
        const int n = std::min (blockSize, total - p);
        for (int i = 0; i < n; ++i, ++idx)
            block[(size_t) i] = sineSample (idx, freq, amp);
        const int baseIdx = idx - n;

        if (oversamplePost)
            os.processBlock (block.data(), n,
                             [&] (double s) { return stage2.processSample (treble.processSample (s)); });
        else
        {
            os.processBlock (block.data(), n);
            for (int i = 0; i < n; ++i)
                block[(size_t) i] = stage2.processSample (treble.processSample (block[(size_t) i]));
        }

        for (int i = 0; i < n; ++i)
            if (baseIdx + i >= warmup)
            {
                inPow += sineSample (baseIdx + i, freq, amp) * sineSample (baseIdx + i, freq, amp);
                outPow += block[(size_t) i] * block[(size_t) i];
            }
    }
    const double wall = now() - t0;
    checkFinite (block);
    return { 10.0 * std::log10 (outPow / inPow), wall / ((double) total / fs) * 100.0 };
}
} // namespace

int main()
{
    std::printf ("Tommy feature CPU-vs-accuracy profile (fs=%.0f, single channel, Release)\n", fs);
    std::printf ("Settings: BASS=0.5 DRIVE=0.7 TREBLE=0.5, 1 kHz / 0.6 V (clipping engaged)\n\n");

    // === 1. Omega solver: AccurateOmega vs omega4 =====================================
    std::printf ("== 1. Diode Wright-omega solver (full chain) ==\n");
    std::printf ("   CPU %% of realtime, and null error of fast omega4 vs accurate (lower dB = closer)\n");
    std::printf ("   %-5s %-7s %10s %10s %12s\n", "OS", "Mode", "accurate", "omega4", "null err dB");
    for (int f : { 0, 2, 3 }) // 1x, 4x (shipped default), 8x
        for (auto mode : { ClipMode::Soft, ClipMode::Hard })
        {
            const char* mn = (mode == ClipMode::Soft) ? "Soft" : "Hard";
            const double cAcc = fullChainCpuPercent<AccurateOmega> (f, mode, true, 0.06, 0.45);
            const double cFast = fullChainCpuPercent<FastOmega> (f, mode, true, 0.06, 0.45);
            const double nerr = omegaNullErrorDB (f, mode);
            std::printf ("   %-5s %-7s %9.2f%% %9.2f%% %12.1f\n", (std::to_string (1 << f) + "x").c_str(),
                         mn, cAcc, cFast, nerr);
        }

    // === 2. Rail-clip ADAA: aliasing reduction vs CPU =================================
    std::printf ("\n== 2. Rail-clip ADAA (Linear mode: rail is the active nonlinearity) ==\n");
    std::printf ("   Aliasing dB (lower=cleaner) and full-chain CPU, ADAA off vs on\n");
    std::printf ("   %-5s %12s %12s %10s %10s\n", "OS", "alias off", "alias on", "CPU off", "CPU on");
    for (int f : { 1, 2, 3 }) // 2x, 4x, 8x
    {
        const double aOff = aliasingDB (ClipMode::Linear, f, false, 0.5, 1.0e6);
        const double aOn = aliasingDB (ClipMode::Linear, f, true, 0.5, 1.0e6);
        const double cOff = fullChainCpuPercent<AccurateOmega> (f, ClipMode::Hard, false, 0.06, 0.45);
        const double cOn = fullChainCpuPercent<AccurateOmega> (f, ClipMode::Hard, true, 0.06, 0.45);
        std::printf ("   %-5s %12.1f %12.1f %9.2f%% %9.2f%%\n", (std::to_string (1 << f) + "x").c_str(),
                     aOff, aOn, cOff, cOn);
    }

    // === 3. Treble+Stage2 oversampled vs base rate ===================================
    std::printf ("\n== 3. Treble+Stage2 inside OS region (shipped) vs at base rate ==\n");
    std::printf ("   Linear magnitude (dB) at top-octave freqs; OS-rate is the reference truth.\n");
    std::printf ("   %-6s %10s %10s %10s | %s\n", "freq", "OS-rate", "base", "droop", "(@4x shipped default)");
    for (double freq : { 1000.0, 8000.0, 12000.0, 16000.0 })
    {
        const auto osR = postChainMag (2, freq, true);
        const auto base = postChainMag (2, freq, false);
        std::printf ("   %5.0fHz %9.2f %9.2f %9.2f\n", freq, osR.magDB, base.magDB, base.magDB - osR.magDB);
    }
    {
        // CPU cost of the post chain alone, OS-rate vs base, at 4x.
        const auto osR = postChainMag (2, 1000.0, true);
        const auto base = postChainMag (2, 1000.0, false);
        std::printf ("   clip+post CPU @4x: OS-rate %.2f%%  base %.2f%%  (delta %.2f%%)\n",
                     osR.cpuPercent, base.cpuPercent, osR.cpuPercent - base.cpuPercent);
    }

    // === 4. Diode mismatch CPU (faithfulness feature) ================================
    std::printf ("\n== 4. Diode mismatch (even-harmonic faithfulness) CPU @4x, Soft ==\n");
    {
        const double cOff = fullChainCpuPercent<AccurateOmega> (2, ClipMode::Soft, true, 0.0, 0.0);
        const double cOn = fullChainCpuPercent<AccurateOmega> (2, ClipMode::Soft, true, 0.06, 0.45);
        std::printf ("   mismatch=0: %.2f%%   shipped mismatch: %.2f%%   (delta %.2f%%)\n",
                     cOff, cOn, cOn - cOff);
    }

    std::printf ("\n%s\n", gAllFinite ? "PASS: all configurations produced finite output."
                                      : "FAIL: non-finite output detected.");
    return gAllFinite ? 0 : 1;
}
