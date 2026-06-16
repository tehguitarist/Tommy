// Step 5 validation: SW1 clipping in Stage 1's feedback (Soft / Medium / Hard).
//
// Checks: (1) small-signal linearity (diodes off => matches Linear mode), (2) large-signal
// compression (clipping modes bound the output well below the linear output), (3) symmetry
// (Soft/Medium symmetric => max ≈ -min; Hard asymmetric => max ≠ -min), (4) Soft is softer
// than Medium (lower clamp), (5) no NaN/Inf over a parameter sweep.

#include "../src/dsp/Stage1.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using tommy::dsp::Stage1;

namespace
{
struct MinMax
{
    double max, min;
};

MinMax measure (Stage1::ClipMode mode, double freq, double amp, double fs, double bassR, double driveR)
{
    Stage1 s;
    s.prepare (fs);
    s.setParams (bassR, driveR);
    s.setMode (mode);

    const int n = (int) fs;
    MinMax mm { -1e9, 1e9 };
    for (int i = 0; i < n; ++i)
    {
        const double x = amp * std::sin (2.0 * M_PI * freq * (double) i / fs);
        const double y = s.processSample (x);
        if (i > n / 2)
        {
            mm.max = std::max (mm.max, y);
            mm.min = std::min (mm.min, y);
        }
    }
    return mm;
}

bool finiteSweepOK (Stage1::ClipMode mode, double fs)
{
    Stage1 s;
    s.prepare (fs);
    s.setMode (mode);
    for (double drive : { 0.0, 1.0e3, 1.0e5, 1.0e6 })
        for (double bass : { 0.0, 1.0e3, 5.0e4 })
        {
            s.setParams (bass, drive);
            for (int i = 0; i < 4000; ++i)
            {
                const double x = 0.8 * std::sin (2.0 * M_PI * 440.0 * (double) i / fs);
                const double y = s.processSample (x);
                if (! std::isfinite (y))
                    return false;
            }
        }
    return true;
}
} // namespace

int main()
{
    constexpr double fs = 96000.0;
    constexpr double bassR = 25.0e3;
    int failures = 0;

    std::printf ("Stage 1 SW1 clipping validation\n");

    // --- 1. Small-signal linearity: feedback voltage must be << Vt_eff (~45 mV) so the
    // diodes stay essentially off; then clipping modes should match Linear. (1N4148 has no
    // hard knee — it soft-conducts well below 0.6 V — so the signal must be genuinely tiny.) ---
    {
        const double amp = 1.0e-4, drive = 1.0e4, f = 1000.0;
        const double lin = measure (Stage1::ClipMode::Linear, f, amp, fs, bassR, drive).max;
        std::printf ("\n[Small-signal linearity]  input=%.0e V, DRIVE=%.0f\n", amp, drive);
        for (auto m : { Stage1::ClipMode::Soft, Stage1::ClipMode::Medium, Stage1::ClipMode::Hard })
        {
            const double pk = measure (m, f, amp, fs, bassR, drive).max;
            const double relErr = std::abs (pk - lin) / std::abs (lin);
            const char* name = m == Stage1::ClipMode::Soft ? "Soft" : m == Stage1::ClipMode::Medium ? "Medium" : "Hard";
            std::printf ("  %-6s peak %.6f vs Linear %.6f  (rel err %.4f) %s\n",
                         name, pk, lin, relErr, relErr > 0.02 ? " <-- FAIL" : "");
            if (relErr > 0.02)
                ++failures;
        }
    }

    // --- 2. Large-signal compression: clipping modes must bound the output ---
    {
        const double amp = 0.5, drive = 1.0e6, f = 1000.0;
        const double lin = measure (Stage1::ClipMode::Linear, f, amp, fs, bassR, drive).max;
        std::printf ("\n[Large-signal compression]  input=%.1f V, DRIVE=%.0f\n", amp, drive);
        std::printf ("  Linear peak (uncompressed): %.3f V\n", lin);
        for (auto m : { Stage1::ClipMode::Soft, Stage1::ClipMode::Medium, Stage1::ClipMode::Hard })
        {
            const auto mm = measure (m, f, amp, fs, bassR, drive);
            const char* name = m == Stage1::ClipMode::Soft ? "Soft" : m == Stage1::ClipMode::Medium ? "Medium" : "Hard";
            std::printf ("  %-6s max %+.3f  min %+.3f\n", name, mm.max, mm.min);
            if (! (mm.max < lin * 0.5)) // must be substantially compressed
            {
                std::fprintf (stderr, "FAIL: %s did not compress the large signal\n", name);
                ++failures;
            }
        }
    }

    // --- 3. Symmetry: Soft/Medium symmetric, Hard asymmetric ---
    {
        const double amp = 0.5, drive = 1.0e6, f = 1000.0;
        std::printf ("\n[Symmetry]  (symmetric => max ≈ -min)\n");
        for (auto m : { Stage1::ClipMode::Soft, Stage1::ClipMode::Medium, Stage1::ClipMode::Hard })
        {
            const auto mm = measure (m, f, amp, fs, bassR, drive);
            const double asym = std::abs (mm.max + mm.min); // 0 if perfectly symmetric (odd output)
            const char* name = m == Stage1::ClipMode::Soft ? "Soft" : m == Stage1::ClipMode::Medium ? "Medium" : "Hard";
            std::printf ("  %-6s |max+min| = %.4f\n", name, asym);
            const bool symmetric = (m != Stage1::ClipMode::Hard);
            if (symmetric && asym > 0.02)
            {
                std::fprintf (stderr, "FAIL: %s should be symmetric but isn't\n", name);
                ++failures;
            }
            if (! symmetric && asym < 0.05)
            {
                std::fprintf (stderr, "FAIL: Hard should be asymmetric but looks symmetric\n");
                ++failures;
            }
        }
    }

    // --- 4. Soft is softer (lower clamp) than Medium ---
    {
        const double amp = 0.5, drive = 1.0e6, f = 1000.0;
        const double soft = measure (Stage1::ClipMode::Soft, f, amp, fs, bassR, drive).max;
        const double med = measure (Stage1::ClipMode::Medium, f, amp, fs, bassR, drive).max;
        std::printf ("\n[Soft vs Medium]  Soft peak %.4f  Medium peak %.4f\n", soft, med);
        if (! (soft < med))
        {
            std::fprintf (stderr, "FAIL: Soft (more diodes) should clamp lower than Medium\n");
            ++failures;
        }
    }

    // --- 5. NaN/Inf safety over a parameter sweep ---
    {
        std::printf ("\n[Stability sweep]\n");
        for (auto m : { Stage1::ClipMode::Soft, Stage1::ClipMode::Medium, Stage1::ClipMode::Hard })
        {
            const bool ok = finiteSweepOK (m, fs);
            const char* name = m == Stage1::ClipMode::Soft ? "Soft" : m == Stage1::ClipMode::Medium ? "Medium" : "Hard";
            std::printf ("  %-6s finite: %s\n", name, ok ? "yes" : "NO");
            if (! ok)
                ++failures;
        }
    }

    // --- 6. 9V op-amp rails: bound the output; transparent at normal levels ---
    {
        std::printf ("\n[9V rails]\n");

        // (a) Hard-mode unclipped polarity must hard-clamp AT the negative rail (-3.1 V),
        //     not the ~-77 V the ideal op-amp produced. A real op-amp clips hard at the rail.
        const auto hard = measure (Stage1::ClipMode::Hard, 1000.0, 0.5, fs, bassR, 1.0e6);
        std::printf ("  Hard min (hard-clamped at rail): %+.3f V (expect -3.10)\n", hard.min);
        if (std::abs (hard.min - (-3.1)) > 0.05)
        {
            std::fprintf (stderr, "FAIL: Hard unclipped polarity not hard-clamped at the rail\n");
            ++failures;
        }

        // (b) Linear mode driven far past the rails must hard-clamp exactly at +2.2 / -3.1 V
        //     (confirms a true hard limit, not a soft roll-off that keeps creeping up).
        const auto lin = measure (Stage1::ClipMode::Linear, 1000.0, 0.5, fs, bassR, 1.0e6);
        std::printf ("  Linear max %+.3f (expect +2.20)  min %+.3f (expect -3.10)\n", lin.max, lin.min);
        if (std::abs (lin.max - 2.2) > 0.05 || std::abs (lin.min - (-3.1)) > 0.05)
        {
            std::fprintf (stderr, "FAIL: Linear output not hard-clamped exactly at the rails\n");
            ++failures;
        }

        // (c) Transparency: a signal that stays well inside the rails must be unchanged whether
        //     the rail clamp is on or off (the diode-clipped ±0.9 V is far from the ±2-3 V rail).
        Stage1 on, off;
        on.prepare (fs);
        off.prepare (fs);
        on.setParams (bassR, 1.0e6);
        off.setParams (bassR, 1.0e6);
        on.setMode (Stage1::ClipMode::Soft);
        off.setMode (Stage1::ClipMode::Soft);
        off.setRailClampEnabled (false);
        double maxDiff = 0.0;
        for (int i = 0; i < (int) fs; ++i)
        {
            const double x = 0.3 * std::sin (2.0 * M_PI * 1000.0 * (double) i / fs);
            maxDiff = std::max (maxDiff, std::abs (on.processSample (x) - off.processSample (x)));
        }
        std::printf ("  Soft transparency (clamp on vs off), max diff: %.2e V\n", maxDiff);
        if (maxDiff > 1.0e-6)
        {
            std::fprintf (stderr, "FAIL: rail clamp not transparent below the knee\n");
            ++failures;
        }
    }

    std::printf ("\n%s\n", failures == 0 ? "PASS" : "FAIL");
    return failures == 0 ? EXIT_SUCCESS : EXIT_FAILURE;
}
