#!/usr/bin/env python3
"""Null test: how completely does the plugin cancel against the real-pedal capture?

For each NAM capture in a batch, render the plugin at the matched settings, sub-sample-align the
two, level-match (optimal least-squares gain), subtract, and report the residual relative to the
real signal in dB. A deeper (more-negative) null = the plugin's output is a closer match to the
real pedal's. The headline number for the README is the BEST achievable null across all settings
(measured on the clean, linear sweep, where a faithful model should null deepest); the WORST is
reported too, for honesty.

Why a new tool (vs analyze.align): analyze.align only does integer-sample cross-correlation lag.
One sample of misalignment at 20 kHz is ~150 deg of phase error — enough to wreck a null. This
adds fractional-delay alignment (parabolic xcorr-peak refinement + FFT phase-ramp shift) so the
residual reflects real spectral/temporal mismatch, not leftover sub-sample skew.

NOTE: the null is computed AFTER an optimal broadband gain-match (standard null-test convention),
so it measures timbre/shape/phase agreement, NOT absolute level. The absolute level error is
reported by run_compare.py separately. The gain that was applied is printed here as 'lvl' so both
are visible.

Usage:
  python3 analysis/null_test.py analysis/pedal_results3      # null every capture in a batch
  KIN=2.4 python3 analysis/null_test.py analysis/pedal_results5
"""
import os, sys, glob, subprocess, numpy as np
from scipy import signal as sps
import analyze as A

FS = A.FS
REND = "build/OfflineRender_artefacts/Release/OfflineRender"
OSLOG2 = 3  # 8x


def frac_align(test, ref):
    """Shift `test` by a fractional number of samples to best line up with `ref` (same length).
    Coarse integer lag from xcorr, refined to sub-sample by parabolic interpolation of the peak,
    then applied as an FFT phase ramp."""
    n = min(len(test), len(ref))
    a = test[:n] - np.mean(test[:n])
    b = ref[:n] - np.mean(ref[:n])
    corr = sps.correlate(a, b, mode="full", method="fft")   # FFT-based; np.correlate is O(n^2)
    k = int(np.argmax(np.abs(corr)))
    # parabolic refinement around the integer peak
    if 0 < k < len(corr) - 1:
        y0, y1, y2 = np.abs(corr[k - 1]), np.abs(corr[k]), np.abs(corr[k + 1])
        denom = (y0 - 2 * y1 + y2)
        delta = 0.5 * (y0 - y2) / denom if denom != 0 else 0.0
    else:
        delta = 0.0
    lag = (k - (n - 1)) + delta   # fractional samples `test` leads `ref`
    # apply -lag fractional shift to test via phase ramp
    X = np.fft.rfft(test)
    freqs = np.fft.rfftfreq(len(test))
    X *= np.exp(-1j * 2 * np.pi * freqs * (-lag))
    return np.fft.irfft(X, len(test))


def null_depth(ref, test):
    """Optimal-gain-match `test` to `ref`, subtract, return (null_dB, applied_gain_dB)."""
    g = float(np.dot(ref, test) / (np.dot(test, test) + 1e-30))   # least-squares level match
    resid = ref - g * test
    null_db = 20 * np.log10((np.sqrt(np.mean(resid ** 2)) + 1e-20) /
                            (np.sqrt(np.mean(ref ** 2)) + 1e-20))
    return null_db, 20 * np.log10(abs(g) + 1e-20)


def render_plugin(p, kin=""):
    orig = A.load(A.ORIG)
    orig.astype(np.float32).tofile("/tmp/null_orig.f32")
    args = [REND, "/tmp/null_orig.f32", "/tmp/null_plug.f32",
            f"{p['B']:.4f}", f"{p['G']:.4f}", f"{p['T']:.4f}", f"{p['V']:.4f}",
            str(p["mode"]), str(OSLOG2), "48000"]
    if kin:
        args.append(kin)
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    x, _ = A.align(np.fromfile("/tmp/null_plug.f32", dtype=np.float32).astype(np.float64), orig)
    return x


def null_for_segment(nam, plug, seg):
    """Frac-align + null on one named segment. Returns (null_dB, lvl_dB)."""
    r = A.seg_of(nam, seg)
    t = A.seg_of(plug, seg)
    t = frac_align(t, r)
    return null_depth(r, t)


def main():
    namdir = next((a for a in sys.argv[1:] if not a.startswith("-")), "analysis/pedal_results3")
    kin = os.environ.get("KIN", "")
    orig = A.load(A.ORIG)
    files = sorted(os.path.basename(x) for x in glob.glob(os.path.join(namdir, "*.wav")))
    print(f"\nNull test — {namdir}  (kIn={kin or 'default'})")
    print("  (null = level-matched residual vs real, dB; lower is better. lvl = gain applied)")
    print("  setting                              clean-sweep      driven-sweep")
    print("                                       null   lvl       null   lvl")
    print("  " + "-" * 64)
    results = []
    for fn in files:
        p = A.parse_filename(fn)
        nam_raw = A.load(os.path.join(namdir, fn))
        if not A.is_full_length(nam_raw, orig):   # check BEFORE align (align pads to full length)
            print(f"  {fn[:34]:34s}  (truncated capture skipped)")
            continue
        nam, _ = A.align(nam_raw, orig)
        plug = render_plugin(p, kin)
        cn, cl = null_for_segment(nam, plug, "sweep_clean")
        dn, dl = null_for_segment(nam, plug, "sweep_driven")
        tag = f"G{p['G']:.2f} {p['sw']:>4} B{p['B']:.2f} T{p['T']:.2f}"
        print(f"  {tag:34s}  {cn:>6.1f} {cl:>+5.1f}     {dn:>6.1f} {dl:>+5.1f}")
        results.append((cn, dn, fn))
    if results:
        best = min(results, key=lambda r: r[0])
        worst = max(results, key=lambda r: r[0])
        print("  " + "-" * 64)
        print(f"  BEST  clean-sweep null: {best[0]:.1f} dB   ({best[2][:40]})")
        print(f"  WORST clean-sweep null: {worst[0]:.1f} dB   ({worst[2][:40]})")


if __name__ == "__main__":
    main()
