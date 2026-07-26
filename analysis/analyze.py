#!/usr/bin/env python3
"""Compare rendered files against the original test signal.

Usage:
  python3 analysis/analyze.py REAL=path/to/real_or_nam.wav TOMMY=path/to/tommy.wav [DRY=path/to/dry.wav]

Each render is auto-aligned to the original (cross-correlation, handles plugin latency), then:
  - CLEAN sweep  -> linear frequency response (EQ), gain at octave frequencies
  - 1 kHz level steps -> output level + compression vs input level (the "3.5 dB" question)
  - freq steps   -> THD / harmonic content per frequency (clipping character)
Outputs a text report; saves PNG overlays if matplotlib is present.
"""
import os, sys, re, numpy as np
from scipy.io import wavfile
from scipy import signal as sps

FS = 48000

# --- Signal layout selection (v1 default; v2 = the comprehensive batch-6 signal) ----------------
# All tools read A.ORIG and A.T, so switching the layout retargets the whole harness. Select with
# the SIGNAL env var: SIGNAL=v2 uses tommy_test_signal_v2_48k.wav + gen_test_signal_v2's layout.
# v1 stays the default so batches 1-5 and existing runs are byte-for-byte unchanged.
ORIG = "analysis/tommy_test_signal_48k.wav"
T = {}

def _build_layout_v1():
    """v1 layout — must match gen_test_signal.py."""
    T.clear()
    cur = [0.0]
    def seg(name, dur):
        T[name] = (cur[0], cur[0] + dur); cur[0] += dur
    seg("sil0", 0.5); seg("cal", 1.0); seg("sil1", 0.5)
    seg("sweep_clean", 10.0); seg("sil2", 0.5)
    seg("sweep_driven", 10.0); seg("sil3", 0.5)
    for db in (-24, -18, -12, -6):
        seg(f"lvl{db}", 1.0); seg(f"lvl{db}_g", 0.3)
    for f in (82.41, 110, 220, 440, 1000, 2000, 5000):
        seg(f"f{f}", 1.0); seg(f"f{f}_g", 0.3)

def _build_layout_v2():
    """v2 layout — imported from gen_test_signal_v2 (its segment_times() is the source of truth),
    PLUS v1-compatible aliases so the existing tools (which ask for 'sweep_clean', 'sweep_driven',
    'lvl-12', 'f110', ...) work unchanged against v2 captures."""
    import gen_test_signal_v2 as g2
    T.clear()
    T.update(g2.segment_times())
    aliases = {"cal": "cal_1k", "sweep_driven": "sweep_drv_-12",
               "lvl-24": "lvl_-24", "lvl-18": "lvl_-18", "lvl-12": "lvl_-12", "lvl-6": "lvl_-6",
               "f82.41": "tone_82.41", "f110": "tone_110", "f220": "tone_220", "f440": "tone_440",
               "f1000": "tone_1000", "f2000": "tone_2000"}
    for old, new in aliases.items():
        if new in T:
            T[old] = T[new]

def use_layout(version):
    """Select 'v1' or 'v2'; sets ORIG + rebuilds T. Tools call A.seg_of/A.ORIG, so this is global."""
    global ORIG
    if version == "v2":
        ORIG = "analysis/tommy_test_signal_v2_48k.wav"
        _build_layout_v2()
    else:
        ORIG = "analysis/tommy_test_signal_48k.wav"
        _build_layout_v1()

use_layout(os.environ.get("SIGNAL", "v1"))

def load(path):
    sr, x = wavfile.read(path)
    if x.dtype.kind in "iu":
        x = x.astype(np.float64) / np.iinfo(x.dtype).max
    else:
        x = x.astype(np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    assert sr == FS, f"{path}: expected {FS} Hz, got {sr}"
    return x

def is_full_length(x, orig, frac=0.95):
    """True if capture `x` spans at least `frac` of the test signal. Guards against the truncated
    8-second captures (e.g. batch-3's two all-caps 'SYM' files) — without this the segments past a
    short file's end read as zeros and the transfer/THD numbers come out as garbage (-200 dB nulls,
    +200 dB 'deltas') rather than an honest skip. The full signal is 37.8 s; truncated ones are 8 s."""
    return len(x) >= frac * len(orig)

def align(render, orig):
    """Return render shifted so it lines up with orig (via xcorr on the clean sweep region)."""
    a, b = T["sweep_clean"]
    ref = orig[int(a * FS):int(b * FS)]
    seg = render[int(a * FS):int(min(len(render), (b + 0.5) * FS))]
    n = min(len(ref), len(seg))
    corr = sps.correlate(seg[:n] - seg[:n].mean(), ref[:n] - ref[:n].mean(), mode="full")
    lag = np.argmax(np.abs(corr)) - (n - 1)
    if lag > 0:
        render = render[lag:]
    elif lag < 0:
        render = np.concatenate([np.zeros(-lag), render])
    if len(render) < len(orig):
        render = np.concatenate([render, np.zeros(len(orig) - len(render))])
    return render[:len(orig)], lag

def seg_of(x, name):
    a, b = T[name]
    return x[int(a * FS):int(b * FS)]

def rms_db(x):
    r = np.sqrt(np.mean(x ** 2))
    return 20 * np.log10(r + 1e-12)

def transfer(out, inp):
    f, Pxy = sps.csd(inp, out, FS, nperseg=8192)
    f, Pxx = sps.welch(inp, FS, nperseg=8192)
    H = np.abs(Pxy) / (Pxx + 1e-20)
    return f, 20 * np.log10(H + 1e-12)

def gain_at(f, mag, target):
    i = np.argmin(np.abs(f - target))
    return mag[i]

def thd(x, f0):
    w = np.hanning(len(x)); X = np.abs(np.fft.rfft(x * w)); fr = np.fft.rfftfreq(len(x), 1 / FS)
    def amp(fc):
        i = np.argmin(np.abs(fr - fc)); lo, hi = max(0, i - 3), i + 4
        return np.max(X[lo:hi])
    fund = amp(f0)
    harm = np.sqrt(sum(amp(f0 * k) ** 2 for k in range(2, 9)))
    return 100 * harm / (fund + 1e-20), fund

# --- Continuous (Farina) THD + sub-sample null test (added for comprehensive_report.py) --------
# SWEEP_F0/F1 match both gen_test_signal.py and gen_test_signal_v2.py's log_sweep(20, 20000, ...)
# endpoints, so these hold under either SIGNAL=v1/v2 layout. frac_align/null_depth are otherwise
# duplicated locally in null_test.py (this project's existing convention of small standalone
# scripts each carrying their own copy) — these are the shared versions comprehensive_report.py
# imports from analyze.py, per the analysis-template's library/orchestrator split.
SWEEP_F0 = 20.0
SWEEP_F1 = 20000.0
ORDER_LIMIT_MARGIN = 0.95  # keep order N only while N*f <= SWEEP_F1*this (edge spike sits AT f1/N)

def harmonic_thd_curve(capture_sweep, ref_sweep, max_order=7, order_limit=True):
    """Continuous THD(f) via Farina exponential-sweep harmonic separation. Deconvolve the captured
    driven sweep against the clean reference sweep; the N-th harmonic IR is time-advanced by
    dt_N = T*ln(N)/ln(f1/f0), so gate each, FFT, and map to the fundamental axis. Returns
    (freqs, thd_pct, {order: |H|}).

    Order limiting (default on): the reference sweep has no energy above SWEEP_F1 (20 kHz), so
    order N is only measurable while N*f <= SWEEP_F1 — past that the regularised division blows up
    and produces a spurious edge spike at f = SWEEP_F1/N. Masking order N above
    SWEEP_F1*ORDER_LIMIT_MARGIN/N avoids this; nothing below ~2714 Hz changes (every order still
    in-band there)."""
    n = min(len(capture_sweep), len(ref_sweep))
    y = capture_sweep[:n].astype(np.float64); x = ref_sweep[:n].astype(np.float64)
    nfft = 1 << int(np.ceil(np.log2(2 * n)))
    X = np.fft.rfft(x, nfft); Y = np.fft.rfft(y, nfft)
    eps = 1e-6 * np.mean(np.abs(X) ** 2)
    ir = np.fft.irfft(Y * np.conj(X) / (np.abs(X) ** 2 + eps), nfft)
    T_sweep = n / FS
    R = np.log(SWEEP_F1 / SWEEP_F0)

    def gated_spectrum(order):
        dt = T_sweep * np.log(order) / R
        center = int(round((-dt) * FS)) % nfft
        if order == 1:
            half = int(0.04 * FS)
        else:
            gap = (T_sweep / R) * np.log((order + 1) / order)   # secs to the next-higher order
            half = int(0.35 * gap * FS)                          # 35% of the gap -> no overlap
        half = max(half, int(0.01 * FS))
        idx = (np.arange(center - half, center + half) % nfft)
        spec = np.fft.rfft(ir[idx] * np.hanning(len(idx)), nfft)
        return np.fft.rfftfreq(nfft, 1 / FS), np.abs(spec)

    fr, H1 = gated_spectrum(1)
    Hn = {1: H1}
    for N in range(2, max_order + 1):
        frN, mag = gated_spectrum(N)
        Hn[N] = np.interp(fr, frN / N, mag, left=0.0, right=0.0)   # remap harmonic->fundamental axis
        if order_limit:
            Hn[N] = np.where(N * fr <= SWEEP_F1 * ORDER_LIMIT_MARGIN, Hn[N], 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        harm = np.sqrt(sum(Hn[N] ** 2 for N in range(2, max_order + 1)))
        thd_pct = 100.0 * harm / (H1 + 1e-20)
    return fr, thd_pct, Hn

def thd_max_measurable_hz(max_order=2):
    """Highest fundamental at which THD is measurable from this sweep, using orders up to
    `max_order`. THD needs at least H2, so the ceiling is SWEEP_F1*margin/2 ~= 9.5 kHz — and no
    test signal can beat FS/4 = 12 kHz at 48 kHz, because H2 lands past Nyquist above that."""
    return min(SWEEP_F1 * ORDER_LIMIT_MARGIN / max_order, FS / (2.0 * max_order))

def frac_align(test, ref):
    """Shift `test` by a FRACTIONAL number of samples to best line up with `ref` (FFT phase ramp;
    parabolic refinement of the xcorr peak). Integer alignment isn't enough for a deep null —
    1 sample at 20 kHz is ~150 deg of phase error."""
    n = min(len(test), len(ref))
    a = test[:n] - test[:n].mean(); b = ref[:n] - ref[:n].mean()
    corr = sps.correlate(a, b, mode="full", method="fft")
    k = int(np.argmax(np.abs(corr)))
    if 0 < k < len(corr) - 1:
        y0, y1, y2 = np.abs(corr[k - 1]), np.abs(corr[k]), np.abs(corr[k + 1])
        denom = (y0 - 2 * y1 + y2); delta = 0.5 * (y0 - y2) / denom if denom else 0.0
    else:
        delta = 0.0
    lag = (k - (n - 1)) + delta
    X = np.fft.rfft(test); freqs = np.fft.rfftfreq(len(test))
    return np.fft.irfft(X * np.exp(-1j * 2 * np.pi * freqs * (-lag)), len(test))

def null_depth(ref, test):
    """Optimal-gain-match `test` to `ref`, subtract, return (null_dB, applied_gain_dB). The gain
    match measures TIMBRE/shape/phase agreement, NOT absolute level (report level separately)."""
    g = float(np.dot(ref, test) / (np.dot(test, test) + 1e-30))
    resid = ref - g * test
    null_db = 20 * np.log10((np.sqrt(np.mean(resid ** 2)) + 1e-20) / (np.sqrt(np.mean(ref ** 2)) + 1e-20))
    return null_db, 20 * np.log10(abs(g) + 1e-20)

# --- Shared NAM-capture filename parsing (consolidated 2026-06-27) ---------------------------
# The capture batches use TWO different knob notations, and this parser auto-detects both so every
# downstream tool (run_compare, harmonics, swept_thd, null_test, knob_tracking) reads filenames the
# same way. Previously run_compare.py (clock_to_x) and harmonics.py (cx) had two slightly-divergent
# copies of this logic — cx() missed the 3-digit-typo fixups, a latent inconsistency bug.
#
#   * CLOCK notation (batch 4 & 5): "V1200 B1330 T0900 G1030 switch mid" — values are clock face
#     positions HHMM, 0700 (7 o'clock = min) .. 1200 (noon) .. 1700 (5 o'clock = max). 3-4 digits.
#   * 0-10 SCALE (batch 3):          "G3 V4 B6 T4 SYM"  — values are a plain 0..10 knob dial, /10.
#
# Detection: a token value >= 100 is clock notation; < 100 is the 0..10 scale. (The 0..10 max is 10;
# the clock min is 700, or the 3-digit typo "120"->1200 — so 100 separates them cleanly.)

def clock_to_x(hhmm):
    """Clock-face HHMM (0700=min .. 1200=noon .. 1700=max) -> normalized knob position 0..1."""
    s = str(int(hhmm))
    if len(s) == 5:        # 'G10300' typo -> 1030
        s = s[:4]
    # 3-digit values are H:MM only for single-digit hours 7/8/9 ("700","900"). A 3-digit value
    # starting with '1' (e.g. "120") is a missing-trailing-zero typo for noon-ish -> "1200".
    if len(s) == 3 and s[0] == "1":
        s = s + "0"
    v = int(s)
    h, m = v // 100, v % 100
    return max(0.0, min(1.0, (h + m / 60.0 - 7.0) / 10.0))

def knob_to_x(raw):
    """One knob token's integer value -> 0..1, auto-detecting clock vs 0-10 notation (see above)."""
    v = int(raw)
    return clock_to_x(v) if v >= 100 else max(0.0, min(1.0, v / 10.0))

def switch_to_mode(name):
    """Switch position -> clip-mode index 0/1/2 = Asym(up)/Open(mid)/Sym(down). Handles both the
    'switch up|mid|down' tokens (batch 4/5) and the bare 'SYM'/'Sym Clip'/'Asym'/'Open' words
    (batch 3, which only ever captured the Sym position)."""
    m = re.search(r"switch (\w+)", name, re.IGNORECASE)
    if m:
        return {"up": 0, "mid": 1, "down": 2}[m.group(1).lower()]
    low = name.lower()
    if "asym" in low:
        return 0
    if "open" in low:
        return 1
    return 2  # 'sym'/'Sym Clip' or unlabelled -> Sym (the batch-3 default)

def parse_filename(name):
    """NAM capture filename -> dict(B, T, V, G as 0..1 positions, mode 0/1/2, sw label).
    Works for every batch (clock or 0-10 notation, switch token or sym keyword)."""
    def g(k):
        mm = re.search(rf"{k}0*(\d+)", name)  # tolerate a leading zero typo e.g. 'B01200'
        return int(mm.group(1)) if mm else 0
    mode = switch_to_mode(name)
    return dict(B=knob_to_x(g("B")), T=knob_to_x(g("T")), V=knob_to_x(g("V")),
                G=knob_to_x(g("G")), mode=mode, sw=["up", "mid", "down"][mode])

# --- Fractional-octave frequency grid for fine EQ reporting -----------------------------------
def fractional_octave_freqs(f_lo=20.0, f_hi=20000.0, frac=3):
    """Geometric grid at 1/`frac`-octave spacing over [f_lo, f_hi] (default 1/3-octave, ~30 pts)."""
    import math
    n = int(math.floor(frac * math.log2(f_hi / f_lo)))
    return [f_lo * 2.0 ** (i / frac) for i in range(n + 1)]

def main():
    args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
    orig = load(ORIG)
    renders = {}
    for label, path in args.items():
        x, lag = align(load(path), orig)
        renders[label] = x
        print(f"[{label}] aligned (lag {lag} smp = {lag/FS*1000:.1f} ms)  <- {path}")
    print()

    print("=== LINEAR EQ (clean sweep) — gain re input, dB ===")
    inp = seg_of(orig, "sweep_clean")
    freqs = [60, 120, 250, 500, 1000, 2000, 4000, 8000, 12000]
    hdr = "freq Hz  | " + " | ".join(f"{l:>8}" for l in renders)
    print(hdr); print("-" * len(hdr))
    tf = {l: transfer(seg_of(x, "sweep_clean"), inp) for l, x in renders.items()}
    for fq in freqs:
        row = f"{fq:>7}  | " + " | ".join(f"{gain_at(*tf[l], fq):>8.2f}" for l in renders)
        print(row)
    if len(renders) == 2:
        a, b = list(renders)
        print(f"\n  delta ({a} - {b}) at each freq:")
        for fq in freqs:
            d = gain_at(*tf[a], fq) - gain_at(*tf[b], fq)
            print(f"    {fq:>6} Hz: {d:+.2f} dB")

    print("\n=== OUTPUT LEVEL vs INPUT LEVEL (1 kHz steps) — output dBFS ===")
    hdr = "in dBFS | " + " | ".join(f"{l:>8}" for l in renders)
    print(hdr); print("-" * len(hdr))
    for db in (-24, -18, -12, -6):
        row = f"{db:>7} | " + " | ".join(f"{rms_db(seg_of(x, f'lvl{db}')):>8.2f}" for x in renders.values())
        print(row)

    print("\n=== THD per frequency (driven tones @ -14 dBFS), % ===")
    hdr = "freq Hz | " + " | ".join(f"{l:>8}" for l in renders)
    print(hdr); print("-" * len(hdr))
    for f in (82.41, 110, 220, 440, 1000, 2000, 5000):
        if f"f{f}" not in T:   # e.g. v2 layout dropped 5000 — skip cleanly instead of KeyError
            continue
        row = f"{f:>7.0f} | " + " | ".join(f"{thd(seg_of(x, f'f{f}'), f)[0]:>8.1f}" for x in renders.values())
        print(row)

    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        plt.figure(figsize=(10, 5))
        for l in renders:
            f, m = tf[l]; plt.semilogx(f[(f > 20) & (f < 20000)], m[(f > 20) & (f < 20000)], label=l)
        plt.grid(True, which="both", alpha=0.3); plt.legend(); plt.xlabel("Hz"); plt.ylabel("dB")
        plt.title("Linear EQ — Tommy vs real"); plt.xlim(20, 20000)
        plt.savefig("analysis/eq_compare.png", dpi=110, bbox_inches="tight")
        print("\nsaved analysis/eq_compare.png")
    except ImportError:
        print("\n(matplotlib not installed — text report only)")

if __name__ == "__main__":
    main()
