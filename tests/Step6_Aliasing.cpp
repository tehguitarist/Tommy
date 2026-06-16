// Step 6 validation: oversampling + ADAA reduce aliasing on the nonlinear clipping stage.
//
// Drives a clipping sine whose harmonics extend past Nyquist, then measures the aliased
// (non-harmonic) energy via FFT. Compares 1x/4x/8x oversampling and ADAA off/on, separately
// for Soft (soft diode clip) and Hard (hard rail clip) modes. Expectation: oversampling cuts
// aliasing sharply; ADAA helps most on the hard rail clip (Hard mode); Soft aliases less to
// begin with (soft clip => fast-decaying harmonics).

#include "../src/dsp/ClippingOversampler.h"

#include <cmath>
#include <cstdio>
#include <vector>

using tommy::dsp::ClippingOversampler;
using tommy::dsp::Stage1;

namespace
{
constexpr double fs = 48000.0;
constexpr double f0 = 2186.0; // non-divisor of fs so aliases land off the harmonic grid
constexpr int N = 16384;      // process one block; FFT the steady tail
constexpr double bassR = 25.0e3;

// Returns aliasing level in dB relative to the fundamental (lower = cleaner).
double measureAliasingDB (Stage1::ClipMode mode, int factorLog2, bool adaa, double amp, double driveR)
{
    ClippingOversampler os;
    os.prepare (fs, N, factorLog2);
    os.setMode (mode);
    os.setParams (bassR, driveR);
    os.setAdaaEnabled (adaa);

    // Phase-continuous sine over warmup + analysis so the FFT window is true steady state
    // (the gain-set leg's 1µF cap settles slowly; a single block's tail is still transient).
    const int total = 4 * N;
    std::vector<double> buf ((size_t) total);
    for (int i = 0; i < total; ++i)
        buf[(size_t) i] = amp * std::sin (2.0 * M_PI * f0 * (double) i / fs);
    for (int off = 0; off < total; off += N)
        os.processBlock (buf.data() + off, N); // oversampler state persists across blocks

    const int order = 13;
    const int fftSize = 1 << order; // 8192
    juce::dsp::FFT fft (order);
    // Blackman-Harris: ~-92 dB sidelobes, so leakage from the strong fundamental/harmonics does
    // not masquerade as aliasing (a Hann window's -31 dB sidelobes floor the measurement ~-35 dB).
    juce::dsp::WindowingFunction<float> win ((size_t) fftSize,
                                             juce::dsp::WindowingFunction<float>::blackmanHarris);
    std::vector<float> fftData ((size_t) (2 * fftSize), 0.0f);
    for (int i = 0; i < fftSize; ++i)
        fftData[(size_t) i] = (float) buf[(size_t) (total - fftSize + i)]; // steady tail
    win.multiplyWithWindowingTable (fftData.data(), (size_t) fftSize);
    fft.performFrequencyOnlyForwardTransform (fftData.data());

    const double binHz = fs / (double) fftSize;
    const int nyqBin = fftSize / 2;

    // Mark harmonic bins (k*f0 below Nyquist), ±3 bins for window leakage.
    std::vector<bool> isHarmonic ((size_t) (nyqBin + 1), false);
    const int guard = 6; // Blackman-Harris main lobe is ~4 bins wide; exclude a little extra
    for (int k = 1; k * f0 < fs / 2.0; ++k)
    {
        const int hb = (int) std::lround (k * f0 / binHz);
        for (int b = hb - guard; b <= hb + guard; ++b)
            if (b >= 0 && b <= nyqBin)
                isHarmonic[(size_t) b] = true;
    }

    const int fundBin = (int) std::lround (f0 / binHz);
    double fundPow = 0.0;
    for (int b = fundBin - guard; b <= fundBin + guard; ++b)
        fundPow += (double) fftData[(size_t) b] * (double) fftData[(size_t) b];

    // Aliasing = energy in non-harmonic bins, measured over the AUDIBLE band only. Harmonics
    // that fold into the 22-24 kHz region land in the decimation filter's transition band and
    // can't be removed by more oversampling (a filter-sharpness limit), but they're inaudible —
    // including them makes the metric falsely pessimistic. Audible aliasing is what matters.
    double aliasPow = 0.0;
    const int lowCut = (int) std::lround (50.0 / binHz);
    const int highCut = std::min (nyqBin, (int) std::lround (18000.0 / binHz));
    for (int b = lowCut; b <= highCut; ++b)
        if (! isHarmonic[(size_t) b])
            aliasPow += (double) fftData[(size_t) b] * (double) fftData[(size_t) b];

    return 10.0 * std::log10 (aliasPow / fundPow);
}
} // namespace

int main()
{
    int failures = 0;
    const double amp = 0.5, drive = 1.0e6;

    std::printf ("Step 6: oversampling + ADAA aliasing reduction (lower dB = cleaner)\n");
    std::printf ("Driving f0=%.0f Hz, amp=%.1f, DRIVE=%.0f at fs=%.0f\n\n", f0, amp, drive, fs);

    auto row = [&] (const char* name, Stage1::ClipMode m)
    {
        const double a1 = measureAliasingDB (m, 0, false, amp, drive); // 1x, no ADAA
        const double a4 = measureAliasingDB (m, 2, false, amp, drive); // 4x
        const double a8 = measureAliasingDB (m, 3, false, amp, drive); // 8x
        const double a4a = measureAliasingDB (m, 2, true, amp, drive); // 4x + ADAA
        const double a8a = measureAliasingDB (m, 3, true, amp, drive); // 8x + ADAA
        std::printf ("  %-6s  1x %7.2f | 4x %7.2f | 8x %7.2f | 4x+ADAA %7.2f | 8x+ADAA %7.2f  dB\n",
                     name, a1, a4, a8, a4a, a8a);
        return std::array<double, 5> { a1, a4, a8, a4a, a8a };
    };

    // Diagnostic: clean (non-clipping) reference reveals the measurement noise floor.
    const double clean1x = measureAliasingDB (Stage1::ClipMode::Hard, 0, false, 1.0e-4, drive);
    const double clean8x = measureAliasingDB (Stage1::ClipMode::Hard, 3, false, 1.0e-4, drive);
    std::printf ("  (clean ref, no clipping)  1x %7.2f | 8x %7.2f  dB  <- measurement floor\n\n",
                 clean1x, clean8x);

    const auto hard = row ("Hard", Stage1::ClipMode::Hard);
    const auto soft = row ("Soft", Stage1::ClipMode::Soft);

    std::printf ("\nChecks:\n");

    // 1. Oversampling sharply reduces aliasing (Hard mode, 8x vs 1x).
    const bool osWorks = (hard[2] < hard[0] - 15.0);
    std::printf ("  [%s] 8x cuts Hard aliasing >=15 dB vs 1x (%.1f -> %.1f)\n",
                 osWorks ? "PASS" : "FAIL", hard[0], hard[2]);
    if (! osWorks)
        ++failures;

    // 2. ADAA further reduces aliasing on the hard rail clip (Hard, 4x+ADAA vs 4x).
    const bool adaaWorks = (hard[3] < hard[1] - 1.0);
    std::printf ("  [%s] ADAA further cuts Hard aliasing at 4x (%.1f -> %.1f)\n",
                 adaaWorks ? "PASS" : "FAIL", hard[1], hard[3]);
    if (! adaaWorks)
        ++failures;

    // 3. Soft mode aliases less than Hard at 1x (soft clip => fewer high harmonics).
    const bool softCleaner = (soft[0] < hard[0]);
    std::printf ("  [%s] Soft aliases less than Hard at 1x (%.1f < %.1f)\n",
                 softCleaner ? "PASS" : "FAIL", soft[0], hard[0]);
    if (! softCleaner)
        ++failures;

    // 4. Best config (8x + ADAA) gives a low aliasing floor for Hard mode.
    const bool floorOK = (hard[4] < -60.0);
    std::printf ("  [%s] Hard 8x+ADAA aliasing floor < -60 dB (%.1f)\n",
                 floorOK ? "PASS" : "FAIL", hard[4]);
    if (! floorOK)
        ++failures;

    std::printf ("\n%s\n", failures == 0 ? "PASS" : "FAIL");
    return failures == 0 ? 0 : 1;
}
