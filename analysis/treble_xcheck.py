#!/usr/bin/env python3
"""Cross-check the fitted treble taper (70k*x^1.43, baked into the plugin) against batch-1 and
batch-3 captures — which were NOT used for the fit. Renders the plugin at the MXR-mirrored
settings (plug_x = 1 - mxr for bass & treble) and compares the treble cut, normalising each
transfer to its own 250 Hz value to remove inter-file/inter-batch level differences."""
import sys, subprocess, glob, os, re, numpy as np
import analyze as A

REND = "build/OfflineRender_artefacts/Release/OfflineRender"
orig = A.load("analysis/tommy_test_signal_48k.wav"); orig.astype(np.float32).tofile("/tmp/o.f32")
inp = A.seg_of(orig, "sweep_clean")
NORM = 250.0  # Hz: below all treble corners, used to normalise out level differences

def parse_clock(n):  # batch-1/2 style "V1200 B0700 T0900 G1030"
    g = lambda k: int(re.search(rf"{k}(\d+)", n).group(1))
    def cx(v):
        if v > 9999:  # '10300' typo -> 1030
            v //= 10
        h, m = v // 100, v % 100   # HHMM (handles leading-zero values like 0700)
        return max(0, min(1, (h + m / 60.0 - 7) / 10.0))
    return dict(B=cx(g("B")), T=cx(g("T")), V=cx(g("V")), G=cx(g("G")))

def parse_pct(n):    # batch-3 style "G3 V4 B6 T4"
    g = lambda k: int(re.search(rf"{k}(\d)", n).group(1)) / 10.0
    return dict(B=g("B"), T=g("T"), V=g("V"), G=g("G"))

def norm_resp(x):
    fr, m = A.transfer(A.seg_of(x, "sweep_clean"), inp)
    ref = m[np.argmin(np.abs(fr - NORM))]
    return fr, m - ref

def at(fr, m, hz): return m[np.argmin(np.abs(fr - hz))]

def render_at(bx, tx, v, gn):
    subprocess.run([REND, "/tmp/o.f32", "/tmp/p.f32", f"{bx}", f"{gn}", f"{tx}",
                    f"{v}", "2", "3", "48000", "1.2"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    x, _ = A.align(np.fromfile("/tmp/p.f32", dtype=np.float32).astype(float), orig)
    return x

def check(folder, parser, label, mirror):
    # mirror=True for MXR (knob-down=cut); render plugin at 1-T to get the same cut amount.
    print(f"\n=== {label} (norm @{NORM:.0f}Hz; 8kHz treble cut: real | plug | delta) ===")
    print("  T    plug_x  G     8kHz real | plug | delta")
    for f in sorted(glob.glob(f"{folder}/*.wav")):
        k = parser(os.path.basename(f))
        nam, _ = A.align(A.load(f), orig); fr_n, m_n = norm_resp(nam)
        bx, tx = (1 - k['B'], 1 - k['T']) if mirror else (k['B'], k['T'])
        fr_p, m_p = norm_resp(render_at(bx, tx, k['V'], k['G']))
        r8, p8 = at(fr_n, m_n, 8000), at(fr_p, m_p, 8000)
        print(f"   {k['T']:.2f}  {tx:.2f}   {k['G']:.1f}    {r8:6.1f} | {p8:6.1f} | {p8-r8:+5.1f}")

check("analysis/pedal_results",  parse_clock, "BATCH 1 (direct, knob-up=cut)", mirror=False)
check("analysis/pedal_results2", parse_clock, "BATCH 2 (MXR, mirrored) — the fit set", mirror=True)
check("analysis/pedal_results3", parse_pct,   "BATCH 3 (MXR, mirrored)", mirror=True)
