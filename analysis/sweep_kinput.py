#!/usr/bin/env python3
"""Sweep kInputRef and compare the plugin's level/THD-vs-input curves to the NAM captures,
to find the input reference that matches the real pedal's clipping onset."""
import subprocess, numpy as np
import analyze as A

REND = "build/OfflineRender_artefacts/Release/OfflineRender"
orig = A.load("analysis/tommy_test_signal_48k.wav")
orig.astype(np.float32).tofile("/tmp/orig.f32")

def render(b, d, t, v, mode, kin):
    subprocess.run([REND, "/tmp/orig.f32", "/tmp/p.f32", f"{b}", f"{d}", f"{t}", f"{v}",
                    str(mode), "3", "48000", f"{kin}"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    x, _ = A.align(np.fromfile("/tmp/p.f32", dtype=np.float32).astype(np.float64), orig)
    return x

def levels(x): return [A.rms_db(A.seg_of(x, f"lvl{db}")) for db in (-24, -18, -12, -6)]
def thds(x):   return [A.thd(A.seg_of(x, f"f{f}"), f)[0] for f in (110, 440, 1000)]

cases = {
 "test1 drive0  (B0 D0 T0 V.5 mid)": dict(b=0, d=0, t=0, v=0.5, mode=1,
    nam="analysis/pedal_results/V1200 B0700 T0700 G0700 switch mid tommy_test_signal_48k.wav"),
 "test2 drive.35 (B.5 D.35 T.2 V.5 mid)": dict(b=0.5, d=0.35, t=0.2, v=0.5, mode=1,
    nam="analysis/pedal_results/V1200 B1200 T0900 G1030 switch mid tommy_test_signal_48k.wav"),
}
for label, c in cases.items():
    nam, _ = A.align(A.load(c["nam"]), orig)
    print("=" * 72); print(label)
    print("            level @ in=-24,-18,-12,-6 dBFS        THD% @110,440,1k")
    print("  REAL    ", " ".join(f"{v:6.2f}" for v in levels(nam)),
          "   ", " ".join(f"{v:5.1f}" for v in thds(nam)))
    for kin in (0.7, 1.0, 1.5, 2.0, 3.27):
        x = render(c["b"], c["d"], c["t"], c["v"], c["mode"], kin)
        print(f"  kIn {kin:4.2f}", " ".join(f"{v:6.2f}" for v in levels(x)),
              "   ", " ".join(f"{v:5.1f}" for v in thds(x)))
