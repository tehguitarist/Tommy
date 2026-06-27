#!/usr/bin/env python3
"""For each NAM capture in $NAMDIR, render the plugin at the matched settings (via OfflineRender)
and compare linear EQ, output level, and THD against the real pedal.

Knob notations (both auto-detected by analyze.parse_filename):
  * clock HHMM  'V1200 B1330 T0900 G1030 switch mid'  (batch 4/5): 0700=min .. 1200=noon .. 1700=max
  * 0-10 scale  'G3 V4 B6 T4 SYM'                      (batch 3):   plain dial 0..10, /10
switch up/mid/down (or the Asym/Open/Sym keyword) -> mode 0/1/2.

Env vars:
  NAMDIR=analysis/pedal_results[3|4|5]   which capture batch to compare against (default batch1)
  KIN=<float>                            override kInputRef (default: plugin's built-in 1.2)
  FINE=1                                 print a 1/3-octave EQ table (~30 pts) instead of 9 fixed
"""
import os, glob, subprocess, numpy as np
import analyze as A   # reuse aligned transfer / level / thd helpers + the shared filename parser

import os as _os
REND = "build/OfflineRender_artefacts/Release/OfflineRender"
ORIG = A.ORIG   # follows SIGNAL=v1/v2 (set in analyze.use_layout); don't hardcode the v1 path
NAMDIR = _os.environ.get("NAMDIR", "analysis/pedal_results")
OSLOG2 = 3  # 8x — take aliasing off the table
KIN = _os.environ.get("KIN", "")  # override kInputRef; empty = plugin default
FINE = _os.environ.get("FINE", "") not in ("", "0")  # 1/3-octave EQ table vs the 9 coarse points

parse = A.parse_filename   # consolidated parser now lives in analyze.py (handles all batches)

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
    orig_chk = A.load(ORIG)
    if not A.is_full_length(nam, orig_chk):
        print("=" * 78); print(f"{name}\n  SKIPPED — truncated capture ({len(nam)/A.FS:.1f}s "
                                 f"< {len(orig_chk)/A.FS:.1f}s expected); no clean sweep present.\n")
        return
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
    eq_freqs = A.fractional_octave_freqs(20, 20000, 3) if FINE \
        else (60, 120, 250, 500, 1000, 2000, 4000, 8000, 12000)
    label = "1/3-oct, 20Hz-20kHz" if FINE else "9 fixed pts"
    print(f"\n  LINEAR EQ (dB re input, {label}):   NAM(real) | plugin | plug-real")
    for fq in eq_freqs:
        r, pl = A.gain_at(fN, mN, fq), A.gain_at(fP, mP, fq)
        print(f"    {fq:>7.0f} Hz:  {r:>7.2f} | {pl:>7.2f} | {pl-r:>+6.2f}")
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
