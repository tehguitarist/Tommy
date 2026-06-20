#!/usr/bin/env python3
"""For each NAM capture in analysis/pedal_results/, render the plugin at the matched settings
(via OfflineRender) and compare. Filename format: 'V1200 B1200 T0900 G1030 switch mid ...'.
Clock 0700=min .. 1200=mid .. 1700=max.  switch up/mid/down -> mode 0/1/2 (Asym/Open/Sym)."""
import os, re, glob, subprocess, numpy as np
from scipy.io import wavfile
import analyze as A   # reuse aligned transfer / level / thd helpers

import os as _os
REND = "build/OfflineRender_artefacts/Release/OfflineRender"
ORIG = "analysis/tommy_test_signal_48k.wav"
NAMDIR = _os.environ.get("NAMDIR", "analysis/pedal_results")
OSLOG2 = 3  # 8x — take aliasing off the table
KIN = _os.environ.get("KIN", "")  # override kInputRef; empty = plugin default

def clock_to_x(hhmm):
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

def parse(name):
    g = lambda k: int(re.search(rf"{k}(\d+)", name).group(1))
    sw = re.search(r"switch (\w+)", name).group(1).lower()
    mode = {"up": 0, "mid": 1, "down": 2}[sw]
    return dict(V=clock_to_x(g("V")), B=clock_to_x(g("B")), T=clock_to_x(g("T")),
                G=clock_to_x(g("G")), mode=mode, sw=sw)

def render_plugin(p):
    orig = A.load(ORIG)
    orig.astype(np.float32).tofile("/tmp/orig.f32")
    args = [REND, "/tmp/orig.f32", "/tmp/plug.f32",
            f"{p['B']:.4f}", f"{p['G']:.4f}", f"{p['T']:.4f}", f"{p['V']:.4f}",
            str(p["mode"]), str(OSLOG2), "48000"]
    if KIN:
        args.append(KIN)
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return np.fromfile("/tmp/plug.f32", dtype=np.float32).astype(np.float64)

def report(name):
    p = parse(name)
    nam = A.load(os.path.join(NAMDIR, name))
    plug = render_plugin(p)
    orig = A.load(ORIG)
    nam, _ = A.align(nam, orig)
    plug, lag = A.align(plug, orig)
    print("=" * 78)
    print(f"{name}")
    print(f"  settings -> bass {p['B']:.2f}  drive {p['G']:.2f}  treble {p['T']:.2f}  "
          f"vol {p['V']:.2f}  mode {p['mode']} ({p['sw']})   [plugin OS {1<<OSLOG2}x, lag {lag}]")
    inp = A.seg_of(orig, "sweep_clean")
    fN, mN = A.transfer(A.seg_of(nam, "sweep_clean"), inp)
    fP, mP = A.transfer(A.seg_of(plug, "sweep_clean"), inp)
    print("\n  LINEAR EQ (dB re input):   NAM(real) | plugin | plug-real")
    for fq in (60, 120, 250, 500, 1000, 2000, 4000, 8000, 12000):
        r, pl = A.gain_at(fN, mN, fq), A.gain_at(fP, mP, fq)
        print(f"    {fq:>6} Hz:  {r:>7.2f} | {pl:>7.2f} | {pl-r:>+6.2f}")
    print("\n  OUTPUT LEVEL (dBFS) @ 1 kHz vs input level:   real | plugin | plug-real")
    for db in (-24, -18, -12, -6):
        r, pl = A.rms_db(A.seg_of(nam, f"lvl{db}")), A.rms_db(A.seg_of(plug, f"lvl{db}"))
        print(f"    in {db:>4}:  {r:>7.2f} | {pl:>7.2f} | {pl-r:>+6.2f}")
    print("\n  THD (%) per freq @ -14 dBFS:   real | plugin")
    for f in (110, 440, 1000, 2000):
        r = A.thd(A.seg_of(nam, f"f{f}"), f)[0]; pl = A.thd(A.seg_of(plug, f"f{f}"), f)[0]
        print(f"    {f:>5} Hz:  {r:>6.1f} | {pl:>6.1f}")
    print()

if __name__ == "__main__":
    for f in sorted(os.path.basename(x) for x in glob.glob(os.path.join(NAMDIR, "*.wav"))):
        report(f)
