#!/usr/bin/env python3
"""Local search for the deepest achievable null at ONE capture, by minor tweaks to the knob params.

null_test.py renders at the capture's NOMINAL settings; this asks "how much deeper can we null if
the real pot positions / our taper mapping were slightly off?" — a coordinate descent over Bass,
Treble, Drive offsets (Volume is pure level, removed by the gain-match, so it can't change the null).
A small tweak that deepens the null a lot = a taper-mapping error worth fixing; little improvement =
we're already at the irreducible nonlinear/phase floor.

Usage:
  SIGNAL=v2 python3 analysis/null_optimize.py "analysis/pedal2/<file>.wav" [seg]
    seg = sweep_clean (default, EQ-dominated) or sweep_driven (adds clipping)
"""
import os, sys, subprocess, numpy as np
import analyze as A
import null_test as N   # frac_align + null_depth live here in this repo

REND = "build/OfflineRender_artefacts/Release/OfflineRender"
OSLOG2 = 3
SEG = sys.argv[2] if len(sys.argv) > 2 else "sweep_clean"

_cache = {}
_orig = A.load(A.ORIG)
_orig.astype(np.float32).tofile("/tmp/nopt_orig.f32")


def null_at(B, T, G, V, mode, nam_seg):
    key = (round(B, 4), round(T, 4), round(G, 4))
    if key in _cache:
        return _cache[key]
    subprocess.run([REND, "/tmp/nopt_orig.f32", "/tmp/nopt_p.f32",
                    f"{B}", f"{G}", f"{T}", f"{V}", str(mode), str(OSLOG2), "48000"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    plug, _ = A.align(np.fromfile("/tmp/nopt_p.f32", dtype=np.float32).astype(float), _orig)
    t = N.frac_align(A.seg_of(plug, SEG), nam_seg)
    nd, _ = N.null_depth(nam_seg, t)
    _cache[key] = nd
    return nd


def main():
    path = sys.argv[1]
    p = A.parse_filename(os.path.basename(path))
    nam, _ = A.align(A.load(path), _orig)
    nam_seg = A.seg_of(nam, SEG)
    cur = {"B": p["B"], "T": p["T"], "G": p["G"]}
    V, mode = p["V"], p["mode"]
    base = null_at(cur["B"], cur["T"], cur["G"], V, mode, nam_seg)
    print(f"\nNull optimize — {os.path.basename(path)[:44]}  (seg={SEG})")
    print(f"  nominal  B{cur['B']:.2f} T{cur['T']:.2f} G{cur['G']:.2f}  ->  null {base:.2f} dB")
    offsets = [-0.10, -0.06, -0.03, 0.0, 0.03, 0.06, 0.10]
    best = base
    for it in range(2):                       # two coordinate-descent passes
        for prm in ("T", "B", "G"):           # treble (biggest EQ lever here), bass, drive
            trials = []
            for off in offsets:
                v = min(1.0, max(0.0, cur[prm] + off))
                nd = null_at(cur["B"] if prm != "B" else v,
                             cur["T"] if prm != "T" else v,
                             cur["G"] if prm != "G" else v, V, mode, nam_seg)
                trials.append((nd, v))
            nd, v = min(trials, key=lambda z: z[0])
            if nd < best - 0.02:
                cur[prm] = v; best = nd
                print(f"  pass{it+1} {prm}: -> {v:.3f}   null {nd:.2f} dB")
    print(f"\n  BEST  B{cur['B']:.3f} T{cur['T']:.3f} G{cur['G']:.3f}  ->  null {best:.2f} dB"
          f"   (improved {base - best:.2f} dB from nominal)")
    # report both segments at the optimum
    for s in ("sweep_clean", "sweep_driven"):
        ns = A.seg_of(nam, s)
        subprocess.run([REND, "/tmp/nopt_orig.f32", "/tmp/nopt_p.f32",
                        f"{cur['B']}", f"{cur['G']}", f"{cur['T']}", f"{V}", str(mode),
                        str(OSLOG2), "48000"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        plug, _ = A.align(np.fromfile("/tmp/nopt_p.f32", dtype=np.float32).astype(float), _orig)
        nd, lvl = N.null_depth(ns, N.frac_align(A.seg_of(plug, s), ns))
        print(f"    at optimum: {s:13s} null {nd:.2f} dB (lvl {lvl:+.2f})")


if __name__ == "__main__":
    main()
