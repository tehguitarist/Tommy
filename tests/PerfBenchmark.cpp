// CPU usage + latency benchmark for the v1.1 optimisation pass (see CLAUDE.md Roadmap).
// Renders a fixed-length tone through the real TommyDSP chain at every oversampling factor x
// clip mode combination, timing the render wall-clock against the audio duration it represents
// (CPU % of realtime) and reporting getLatencySamples() per factor. Not a pass/fail accuracy
// test like the other tests/ executables — it's a measurement probe, registered with ctest only
// to assert the chain stays finite/bounded (a real regression, not a perf threshold: CI runners
// vary too much in speed to gate on an absolute CPU% number).

#include "../src/dsp/TommyDSP.h"
#include "../src/utils/TaperUtils.h"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <vector>

namespace tp = tommy::taper;
using tommy::dsp::Stage1;
using tommy::dsp::TommyDSP;

namespace
{
struct Result
{
    int factor;
    const char* modeName;
    double cpuPercent;
    double latencySamples;
    double latencyMs;
    bool finite;
};

Result benchmarkOne (int factorLog2, Stage1::ClipMode mode, const char* modeName, double sampleRate)
{
    constexpr int blockSize = 512;
    constexpr double renderSeconds = 5.0;
    const int totalSamples = (int) (renderSeconds * sampleRate);

    TommyDSP dsp;
    dsp.prepare (sampleRate, blockSize, factorLog2);

    // Fixed, deliberately-engaged-clipping settings so the benchmark measures the nonlinear
    // stage's real cost, not an idle/clean best case.
    const double bassR = tp::bassResistance (0.5);
    const double driveR = tp::driveResistance (0.7);
    const double trebR = tp::trebleResistance (0.5);
    dsp.setControls (bassR, driveR, trebR, mode);
    dsp.setSupplyVoltage (9.0);
    dsp.setAdaaEnabled (true);

    std::vector<double> block (blockSize);
    constexpr double freqHz = 1000.0;
    constexpr double amplitude = 0.6; // volts; well into clipping at this drive setting

    bool finite = true;
    const auto start = std::chrono::steady_clock::now();

    int sampleIndex = 0;
    for (int processed = 0; processed < totalSamples; processed += blockSize)
    {
        const int n = std::min (blockSize, totalSamples - processed);
        for (int i = 0; i < n; ++i, ++sampleIndex)
            block[(size_t) i] = amplitude * std::sin (2.0 * M_PI * freqHz * (double) sampleIndex / sampleRate);
        dsp.processBlock (block.data(), n);
        for (int i = 0; i < n; ++i)
            finite = finite && std::isfinite (block[(size_t) i]);
    }

    const auto end = std::chrono::steady_clock::now();
    const double wallSeconds = std::chrono::duration<double> (end - start).count();
    const double audioSeconds = (double) totalSamples / sampleRate;
    const double latencySamples = dsp.getLatencySamples();

    return { 1 << factorLog2, modeName, (wallSeconds / audioSeconds) * 100.0, latencySamples,
             latencySamples / sampleRate * 1000.0, finite };
}
} // namespace

int main()
{
    constexpr double sampleRate = 48000.0;
    static const std::pair<Stage1::ClipMode, const char*> modes[] = {
        { Stage1::ClipMode::Hard, "Hard" },
        { Stage1::ClipMode::Medium, "Medium" },
        { Stage1::ClipMode::Soft, "Soft" }
    };

    std::vector<Result> results;
    for (int factorLog2 = 0; factorLog2 < 4; ++factorLog2)
        for (const auto& [mode, modeName] : modes)
            results.push_back (benchmarkOne (factorLog2, mode, modeName, sampleRate));

    std::printf ("%-6s %-8s %10s %14s %10s\n", "OS", "Mode", "CPU % RT", "Latency (smp)", "Latency (ms)");
    std::printf ("-------------------------------------------------------------\n");
    bool allFinite = true;
    for (const auto& r : results)
    {
        std::printf ("%-6s %-8s %9.2f%% %14.1f %9.3f\n", (std::to_string (r.factor) + "x").c_str(),
                     r.modeName, r.cpuPercent, r.latencySamples, r.latencyMs);
        allFinite = allFinite && r.finite;
    }

    if (! allFinite)
    {
        std::fprintf (stderr, "FAIL: non-finite output detected in at least one OS factor / clip mode\n");
        return 1;
    }

    std::printf ("\nPASS: all factors/modes produced finite, bounded output.\n");
    return 0;
}
