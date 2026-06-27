#!/usr/bin/env python3
"""How deep COULD the null go, and what's the nature of the residual?

The standard null (null_test.py) removes only a single broadband gain + a delay, so its residual
still contains every LINEAR mismatch (EQ-shape, phase/group-delay, top-octave warp) PLUS the
nonlinear part. This separates them:

  raw null         single optimal gain removed                  (what null_test reports)
  linear-removed   the OPTIMAL LTI filter removed, via the       (the deepest a null could reach
                   magnitude-squared coherence gamma^2(f):        if linear differences were
                   residual power fraction = 1 - gamma^2          perfectly matched)

`linear-removed` is the floor set by the genuinely NONLINEAR disagreement (clipping-harmonic phase)
plus the NAM capture's own fidelity. Coherence comes from Welch averaging (limited DOF), so it does
NOT overfit the way a per-bin Y/X division would. Interpretation:
  - linear-removed MUCH deeper than raw  -> residual is mostly LINEAR -> a better taper / less
    discretization warp could deepen the real (plugin-as-shipped) null toward it.
  - linear-removed ~= raw                -> residual is mostly nonlinear / capture floor -> already
    near the limit; tweaking the plugin won't help.

This is a DIAGNOSTIC (it applies a correction not in the plugin) — the shipped plugin's honest null
stays the null_test number. Usage:
  SIGNAL=v2 python3 analysis/null_floor.py "analysis/pedalX/<file>.wav"
"""
import os, sys, subprocess, numpy as np
from scipy import signal as sps
import analyze as A
import null_test as N

REND = "build/OfflineRender_artefacts/Release/OfflineRender"
OSLOG2 = 3


def render(p):
    orig = A.load(A.ORIG)
    orig.astype(np.float32).tofile("/tmp/nfloor_orig.f32")
    subprocess.run([REND, "/tmp/nfloor_orig.f32", "/tmp/nfloor_p.f32",
                    f"{p['B']}", f"{p['G']}", f"{p['T']}", f"{p['V']}", str(p["mode"]),
                    str(OSLOG2), "48000"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    x, _ = A.align(np.fromfile("/tmp/nfloor_p.f32", dtype=np.float32).astype(float), orig)
    return x


def linear_removed_null(test, ref):
    """Residual after the optimal LTI filter, via magnitude-squared coherence (Welch-averaged)."""
    n = min(len(test), len(ref))
    f, cxy = sps.coherence(test[:n], ref[:n], A.FS, nperseg=8192)
    f, pyy = sps.welch(ref[:n], A.FS, nperseg=8192)
    resid_frac = np.sum(pyy * (1.0 - cxy)) / (np.sum(pyy) + 1e-30)
    return 10.0 * np.log10(resid_frac + 1e-20)


def main():
    path = sys.argv[1]
    p = A.parse_filename(os.path.basename(path))
    orig = A.load(A.ORIG)
    nam, _ = A.align(A.load(path), orig)
    plug = render(p)
    print(f"\nNull floor — {os.path.basename(path)[:46]}")
    print(f"  B{p['B']:.2f} T{p['T']:.2f} G{p['G']:.2f} V{p['V']:.2f} mode{p['mode']}")
    print("  segment        raw null    linear-removed (nonlinear floor)")
    for s in ("sweep_clean", "sweep_driven"):
        r = A.seg_of(nam, s)
        t = N.frac_align(A.seg_of(plug, s), r)
        raw, _ = N.null_depth(r, t)
        lin = linear_removed_null(t, r)
        print(f"  {s:13s}  {raw:7.2f} dB   {lin:7.2f} dB")


if __name__ == "__main__":
    main()
