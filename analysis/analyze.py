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
import sys, numpy as np
from scipy.io import wavfile
from scipy import signal as sps

FS = 48000
ORIG = "analysis/tommy_test_signal_48k.wav"

# Segment layout (seconds) — must match gen_test_signal.py
T = {}
def _build_layout():
    cur = 0.0
    def seg(name, dur):
        nonlocal cur
        T[name] = (cur, cur + dur); cur += dur
    seg("sil0", 0.5); seg("cal", 1.0); seg("sil1", 0.5)
    seg("sweep_clean", 10.0); seg("sil2", 0.5)
    seg("sweep_driven", 10.0); seg("sil3", 0.5)
    lvl = {}
    for db in (-24, -18, -12, -6):
        seg(f"lvl{db}", 1.0); seg(f"lvl{db}_g", 0.3)
    for f in (82.41, 110, 220, 440, 1000, 2000, 5000):
        seg(f"f{f}", 1.0); seg(f"f{f}_g", 0.3)
_build_layout()

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
