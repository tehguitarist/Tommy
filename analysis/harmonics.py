#!/usr/bin/env python3
"""Compare clipping harmonic profile + saturation between the plugin and a NAM capture.
For a steady tone f0, extract amplitudes at k*f0 (k=1..8) -> characterises clip type
(even harmonics = asymmetric, odd = symmetric) and depth (THD). Renders the plugin at the
capture's settings via OfflineRender. Knob direction: batch-1 = direct (knob-up=cut)."""
import sys, subprocess, os, numpy as np
import analyze as A

REND = "build/OfflineRender_artefacts/Release/OfflineRender"
orig = A.load("analysis/tommy_test_signal_48k.wav"); orig.astype(np.float32).tofile("/tmp/o.f32")
FS = 48000

parse = A.parse_filename   # consolidated parser now lives in analyze.py (handles all batches)

def render(k, kin="1.2"):
    subprocess.run([REND, "/tmp/o.f32", "/tmp/p.f32", f"{k['B']}", f"{k['G']}", f"{k['T']}",
                    f"{k['V']}", str(k['mode']), "3", "48000", kin], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    x, _ = A.align(np.fromfile("/tmp/p.f32", dtype=np.float32).astype(float), orig)
    return x

def harmonics(x, seg, f0):
    s = A.seg_of(x, seg)
    s = s[int(0.1*FS):]  # skip fade-in
    w = np.hanning(len(s)); X = np.abs(np.fft.rfft(s * w)); fr = np.fft.rfftfreq(len(s), 1/FS)
    def amp(fc):
        i = np.argmin(np.abs(fr - fc)); return np.max(X[max(0,i-3):i+4])
    h = np.array([amp(f0*k) for k in range(1, 9)])
    return h

def report(nam_path, f0=220, seg="f220"):
    k = parse(os.path.basename(nam_path))
    nam, _ = A.align(A.load(nam_path), orig)
    hr = harmonics(nam, seg, f0); hp = harmonics(render(k), seg, f0)
    hr_db = 20*np.log10(hr/hr[0] + 1e-9); hp_db = 20*np.log10(hp/hp[0] + 1e-9)
    print(f"\n{os.path.basename(nam_path)[:48]}")
    print(f"  mode {k['mode']}  B{k['B']:.1f} T{k['T']:.1f} G{k['G']:.1f} V{k['V']:.1f}   tone {f0} Hz")
    print(f"  harmonic dB re fundamental:   H2     H3     H4     H5     H6     H7")
    print(f"    REAL    " + " ".join(f"{v:6.1f}" for v in hr_db[1:7]))
    print(f"    PLUGIN  " + " ".join(f"{v:6.1f}" for v in hp_db[1:7]))
    thd = lambda h: 100*np.sqrt(np.sum(h[1:]**2))/h[0]
    evn = lambda h: 20*np.log10(np.sqrt(h[1]**2+h[3]**2)/np.sqrt(h[2]**2+h[4]**2)+1e-9)  # even/odd
    print(f"  THD:  real {thd(hr):.1f}%  plugin {thd(hp):.1f}%   |  even-vs-odd (dB, +=more even): "
          f"real {evn(hr):+.1f}  plugin {evn(hp):+.1f}")

if __name__ == "__main__":
    base = "analysis/pedal_results"
    for f in ("V1200 B1200 T0900 G1030 switch up tommy_test_signal_48k.wav",
              "V1200 B1200 T0900 G1030 switch mid tommy_test_signal_48k.wav",
              "V1200 B1200 T0900 G10300 switch down tommy_test_signal_48k.wav"):
        p = os.path.join(base, f)
        if os.path.exists(p): report(p)
