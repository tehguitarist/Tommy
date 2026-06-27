#!/usr/bin/env python3
"""Continuous THD-vs-frequency from the existing driven log-sweep, via Farina's exponential-sweep
harmonic-separation method — NO new captures required.

Why this exists
---------------
The discrete-tone THD in analyze.py / run_compare.py only samples 7 frequencies (and run_compare
prints just 4), with nothing between 2 kHz and 5 kHz and nothing above 5 kHz. But the test signal
already contains a 10 s exponential sine sweep (ESS) 20 Hz->20 kHz at -12 dBFS ("sweep_driven"),
present in every NAM capture. Deconvolving that against the clean reference sweep separates each
harmonic order into its own peak in the resulting impulse response (a property of the ESS: the
N-th harmonic IR is time-advanced by dt_N = T*ln(N)/ln(f1/f0) relative to the linear IR). Gating
each harmonic peak and Fourier-transforming it yields that harmonic's level as a continuous
function of the *fundamental* frequency — so one existing capture gives a full THD(f) curve.

This is valid here because Tommy's distortion is a memoryless instantaneous nonlinearity (diode +
op-amp clipping), which is exactly the case Farina's method assumes. See Farina, "Simultaneous
measurement of impulse response and distortion with a swept-sine technique," AES 108 (2000).

DO NOT trust the curve until the built-in `--validate` cross-check against the 7 discrete-tone THD
measurements agrees (run it; the plan mandates this before the curve is used for anything).

Usage
-----
  python3 analysis/swept_thd.py --validate                 # self-check vs discrete tones (DRY pre-req)
  python3 analysis/swept_thd.py REAL=path/to/capture.wav   # THD(f) of one file, by band
  python3 analysis/swept_thd.py REAL=cap.wav PLUG=rendered.wav   # overlay two
  python3 analysis/swept_thd.py --matrix analysis/pedal_results4   # THD-by-band, real vs plugin,
                                                                   # across every capture in a batch
"""
import os, sys, glob, subprocess, numpy as np
import analyze as A

FS = A.FS
REND = "build/OfflineRender_artefacts/Release/OfflineRender"
OSLOG2 = 3  # 8x — take aliasing off the table for the THD comparison

# ESS parameters — MUST match gen_test_signal.log_sweep() exactly (f0,f1,T) so the deconvolution
# reference is identical to what's actually in the captures.
SWEEP_F0, SWEEP_F1, SWEEP_T = 20.0, 20000.0, 10.0
SWEEP_SEG = "sweep_driven"   # the -12 dBFS sweep (where the clipping lives); "sweep_clean" also valid

# Octave-ish reporting bands, with extra resolution through 1-8 kHz where the saturation lives.
BANDS = [(40, 80), (80, 160), (160, 320), (320, 640), (640, 1000),
         (1000, 1500), (1500, 2200), (2200, 3200), (3200, 4600), (4600, 6500),
         (6500, 9000), (9000, 13000), (13000, 16000)]


def reference_sweep():
    """The exact clean ESS excitation, taken from the original test signal's driven-sweep segment."""
    orig = A.load(A.ORIG)
    return A.seg_of(orig, SWEEP_SEG)


def harmonic_thd_curve(capture_sweep, ref_sweep, max_order=7):
    """Return (freqs, thd_pct, {order: |H_order|(f)}) via ESS harmonic separation.

    freqs is the fundamental-frequency axis; thd_pct[i] = 100*sqrt(sum_{N>=2}|H_N|^2)/|H_1| at
    freqs[i]. Both spectra are expressed on the same fundamental-frequency axis (Farina: the N-th
    harmonic IR's transfer function is a function of the excitation/fundamental frequency)."""
    n = min(len(capture_sweep), len(ref_sweep))
    y = capture_sweep[:n].astype(np.float64)
    x = ref_sweep[:n].astype(np.float64)

    # Regularized frequency-domain deconvolution: h = IFFT( Y * conj(X) / (|X|^2 + eps) ).
    # eps is a small fraction of the mean band energy — tames the out-of-band nulls of the sweep
    # spectrum without smearing the in-band response.
    nfft = 1 << int(np.ceil(np.log2(2 * n)))
    X = np.fft.rfft(x, nfft)
    Y = np.fft.rfft(y, nfft)
    eps = 1e-6 * np.mean(np.abs(X) ** 2)
    H = Y * np.conj(X) / (np.abs(X) ** 2 + eps)
    ir = np.fft.irfft(H, nfft)  # linear IR at n=0; harmonic N IRs wrap to (nfft - dt_N*FS)

    R = np.log(SWEEP_F1 / SWEEP_F0)
    # Gate each order's IR with a window centered at its time advance dt_N (samples wrap from the
    # end too). The half-width must NOT reach an adjacent order: consecutive orders are spaced by
    # (T/R)*ln((N+1)/N) seconds, which shrinks as N grows, so we size the window to 35% of the gap
    # to the nearest neighbour. (An earlier 0.45*dt window overlapped N=2/N=3 and inflated THD.)
    def gated_spectrum(order):
        dt = SWEEP_T * np.log(order) / R              # seconds the N-th harmonic IR is advanced
        center = int(round((-dt) * FS)) % nfft        # circular index of this order's peak
        if order == 1:
            half = int(0.04 * FS)
        else:
            gap = (SWEEP_T / R) * np.log((order + 1) / order)   # secs to the next-higher order
            half = int(0.35 * gap * FS)
        half = max(half, int(0.01 * FS))
        idx = (np.arange(center - half, center + half) % nfft)
        seg = ir[idx] * np.hanning(len(idx))
        spec = np.fft.rfft(seg, nfft)
        fr = np.fft.rfftfreq(nfft, 1 / FS)
        return fr, np.abs(spec)

    fr, H1 = gated_spectrum(1)
    # Each harmonic-N spectrum is naturally indexed by the HARMONIC output frequency; remap to the
    # fundamental axis by f_fund = f_harmonic / N (resample onto the order-1 frequency grid).
    Hn = {1: H1}
    for N in range(2, max_order + 1):
        frN, mag = gated_spectrum(N)
        Hn[N] = np.interp(fr, frN / N, mag, left=0.0, right=0.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        harm = np.sqrt(sum(Hn[N] ** 2 for N in range(2, max_order + 1)))
        thd = 100.0 * harm / (H1 + 1e-20)
    return fr, thd, Hn


def thd_by_band(freqs, thd):
    """Median THD% within each reporting band (median is robust to the sweep's edge ripple)."""
    out = []
    for lo, hi in BANDS:
        m = (freqs >= lo) & (freqs < hi)
        out.append((lo, hi, float(np.median(thd[m])) if np.any(m) else float("nan")))
    return out


def measure_file(path):
    """Load a capture, align it, and return its THD-by-band list."""
    orig = A.load(A.ORIG)
    x, _ = A.align(A.load(path), orig)
    if not A.is_full_length(x, orig):
        return None
    fr, thd, _ = harmonic_thd_curve(A.seg_of(x, SWEEP_SEG), reference_sweep())
    return fr, thd


def validate():
    """Cross-check the swept-sine THD against the 7 discrete-tone THD measurements on the SAME
    capture. They should agree within a few % absolute; large disagreement = deconvolution/mapping
    bug, fix before trusting the curve. Uses a mid-drive batch-4 capture that has real distortion."""
    import glob, os, subprocess
    REND = "build/OfflineRender_artefacts/Release/OfflineRender"
    # Pick a driven batch-4 file (mid switch, decent gain) so there's measurable THD to compare.
    cands = glob.glob("analysis/pedal_results4/*G1500*switch mid*.wav") or \
            glob.glob("analysis/pedal_results4/*switch mid*.wav")
    if not cands:
        print("validate: no batch-4 capture found"); return
    nam_path = sorted(cands)[0]
    p = A.parse_filename(os.path.basename(nam_path))
    print(f"validate against: {os.path.basename(nam_path)}")
    print(f"  settings B{p['B']:.2f} T{p['T']:.2f} G{p['G']:.2f} V{p['V']:.2f} mode{p['mode']}\n")

    orig = A.load(A.ORIG)
    nam, _ = A.align(A.load(nam_path), orig)

    # Swept-sine THD curve, sampled at the discrete tone frequencies:
    fr, thd, _ = harmonic_thd_curve(A.seg_of(nam, SWEEP_SEG), reference_sweep())
    print("  freq    discrete-tone THD%   swept-sine THD%   (should roughly agree)")
    ok = True
    for f0 in (110, 220, 440, 1000, 2000):
        disc = A.thd(A.seg_of(nam, f"f{f0}"), f0)[0]
        # median over a narrow band around f0 to avoid single-bin ripple
        m = (fr >= f0 * 0.92) & (fr <= f0 * 1.08)
        swp = float(np.median(thd[m]))
        flag = "" if abs(disc - swp) < max(2.0, 0.3 * disc) else "  <-- MISMATCH"
        if flag:
            ok = False
        print(f"  {f0:>5} Hz   {disc:>14.1f}   {swp:>14.1f}{flag}")
    print(f"\n  => {'OK — swept curve tracks the discrete tones' if ok else 'MISMATCH — do not trust the curve yet'}")


# Coarser bands for the cross-batch matrix (keeps each row scannable); the mid band 1-4 kHz is
# where most of Tommy's saturation character lives, so it gets its own columns.
MATRIX_BANDS = [(80, 320, "low"), (320, 1000, "lo-mid"), (1000, 2000, "1-2k"),
                (2000, 4000, "2-4k"), (4000, 8000, "4-8k"), (8000, 14000, "high")]


def render_plugin(p, kin=""):
    """Render the plugin at matched settings p (from A.parse_filename) and return the aligned out."""
    orig = A.load(A.ORIG)
    orig.astype(np.float32).tofile("/tmp/swept_orig.f32")
    args = [REND, "/tmp/swept_orig.f32", "/tmp/swept_plug.f32",
            f"{p['B']:.4f}", f"{p['G']:.4f}", f"{p['T']:.4f}", f"{p['V']:.4f}",
            str(p["mode"]), str(OSLOG2), "48000"]
    if kin:
        args.append(kin)
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    x, _ = A.align(np.fromfile("/tmp/swept_plug.f32", dtype=np.float32).astype(np.float64), orig)
    return x


def band_median(freqs, thd, lo, hi):
    m = (freqs >= lo) & (freqs < hi)
    return float(np.median(thd[m])) if np.any(m) else float("nan")


def matrix(namdir, kin=""):
    """THD-by-band, real vs plugin, for every (full-length) capture in a batch — one block per file,
    sorted so the drive/mode sweep reads top-to-bottom. Answers 'does THD track across drive x mode',
    with extra columns through 1-4 kHz where Tommy's saturation lives."""
    orig = A.load(A.ORIG)
    ref = reference_sweep()
    files = sorted(os.path.basename(x) for x in glob.glob(os.path.join(namdir, "*.wav")))
    hdr = "  drive mode  src    " + "  ".join(f"{name:>6}" for *_ , name in MATRIX_BANDS)
    print(f"\nTHD% by band — {namdir}  (kIn={kin or 'default'})")
    print(hdr); print("  " + "-" * (len(hdr) - 2))
    for fn in files:
        p = A.parse_filename(fn)
        nam, _ = A.align(A.load(os.path.join(namdir, fn)), orig)
        if not A.is_full_length(nam, orig):
            print(f"  G{p['G']:.2f} {p['sw']:>4}  (truncated capture skipped: {fn[:34]})")
            continue
        frN, thdN = harmonic_thd_curve(A.seg_of(nam, SWEEP_SEG), ref)[:2]
        plug = render_plugin(p, kin)
        frP, thdP = harmonic_thd_curve(A.seg_of(plug, SWEEP_SEG), ref)[:2]
        rrow = "  ".join(f"{band_median(frN, thdN, lo, hi):>6.1f}" for lo, hi, _ in MATRIX_BANDS)
        prow = "  ".join(f"{band_median(frP, thdP, lo, hi):>6.1f}" for lo, hi, _ in MATRIX_BANDS)
        print(f"  G{p['G']:.2f} {p['sw']:>4}  real   {rrow}")
        print(f"  {'':5} {'':>4}  plug   {prow}")
    print()


def main():
    if "--validate" in sys.argv:
        validate(); return
    if "--matrix" in sys.argv:
        i = sys.argv.index("--matrix")
        namdir = sys.argv[i + 1] if len(sys.argv) > i + 1 else "analysis/pedal_results4"
        kin = os.environ.get("KIN", "")
        matrix(namdir, kin); return
    args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
    if not args:
        print(__doc__); return
    curves = {}
    for label, path in args.items():
        r = measure_file(path)
        if r is None:
            print(f"[{label}] SKIPPED (truncated): {path}"); continue
        curves[label] = r
    if not curves:
        return
    labels = list(curves)
    print("\n  THD% by band:   band(Hz)        " + "   ".join(f"{l:>8}" for l in labels))
    bands_per = {l: thd_by_band(*curves[l]) for l in labels}
    for i, (lo, hi, _) in enumerate(bands_per[labels[0]]):
        row = "   ".join(f"{bands_per[l][i][2]:>8.1f}" for l in labels)
        print(f"   {lo:>6}-{hi:<6}                {row}")


if __name__ == "__main__":
    main()
