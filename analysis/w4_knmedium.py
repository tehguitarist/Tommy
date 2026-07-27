#!/usr/bin/env python3
"""v1.4 W4 lever 3 — is Medium's residual LF excess fixable via kNMedium?

W4 probe 7 (`w4_bassdrive.py --only decompose`) left exactly one lever standing. At 64 Hz, Soft is
essentially exact (+0.58 clean -> -0.11 at -6 dBFS) and Hard nearly so (+1.68 -> +0.03), but MEDIUM
plateaus at +0.5..+0.7 instead of decaying to zero. That is mode-specific and level-persistent, i.e.
a clip-threshold signature rather than an EQ error, and W1 explicitly noted `kNMedium = 1.35x` was a
RAIL-capped compromise (1.5x fitted THD better). So: sweep kNMedium and measure the LF metric.

This probe RENDERS (unlike w4_bassdrive.py, which is closed-form + JSON only), so it needs
`build/OfflineRender_artefacts/Release/OfflineRender`. 5 Medium pedal2 captures x 4 multipliers.

Usage (from the repo root):
    analysis/.venv/bin/python3 analysis/w4_knmedium.py

OUTCOME (2026-07-27): **lever 3 REFUTED — the direction is right but the sensitivity is nil.**
  * Both metrics prefer HIGHER kNMedium, so there is NO LF-vs-THD trade to arbitrate:
        mean |LF dev|:  x1.10 0.535 -> x1.20 0.503 -> x1.35 0.473 (shipped) -> x1.50 0.461 dB
        mean |THD dev|: x1.10 1.19  -> x1.20 0.99  -> x1.35 0.85  (shipped) -> x1.50 0.79  %
  * But the whole 1.10..1.50 range moves the aggregate LF metric by **0.074 dB**, and shipped->1.50
    by **0.012 dB**. At the worst single point (D0.65, 64 Hz, clean) 1.50 buys 0.28 dB and still
    misses the 1.5 dB gate by ~0.8 dB; on the driven sweeps that capture already passed.
  * The binding constraint is unchanged and is NOT this metric: at 1.5x Stage 1 reaches the
    ASYMMETRIC op-amp rails before the diodes clamp, so Medium's H2 error goes +3.48 -> +10.45 dB
    (Stage1.h's kNMedium comment). Medium is a symmetric clipper; that is an audible timbre error.
  * Conclusion: **Medium's LF residual is essentially insensitive to kNMedium.** Do not spend the
    rail artefact to buy 0.01 dB. Keep 1.35x.

Sign convention: LF dev = plugin - pedal, 1 kHz-normalised. Positive = plugin hotter than pedal.
"""
import os
import subprocess
import sys

import numpy as np

os.environ.setdefault("SIGNAL", "v2")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A  # noqa: E402
import captures as C  # noqa: E402

KN = 1.752          # Stage1.h kN (1N4148 ideality)
SHIPPED = 1.35      # Stage1.h kNMedium = 1.35 * kN (W1 fit, rail-capped)
MULTS = [1.10, 1.20, SHIPPED, 1.50]
LF_HZ = [63.5, 127.0]
NORM_HZ = 1015.9
LEVELS = ["sweep_clean", "sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6"]
THD_TONES = [110, 440, 1000]
IN_F32 = "/tmp/w4_knmed_in.f32"
OUT_F32 = "/tmp/w4_knmed_out.f32"


def xargs(med_n):
    """OfflineRender argv[10..22] with only kNMedium overridden.

    medN is argv[22], so this list MUST be 13 long. A 12-long list silently lands the value in
    argv[21] (medIs) and leaves medN defaulted, making the whole sweep a no-op with four identical
    columns — that exact bug cost a full render pass on 2026-07-27. The assert is the guard.
    """
    a = ["1.2", "-1", "1.43", "-1", "1.43", "-1", "0", "-1", "1", "9", "-1", "-1", f"{med_n:.6f}"]
    assert len(a) == 13, f"argv[10..22] must be 13 entries, got {len(a)}"
    return a


def features(sig, orig):
    """({level: [1 kHz-normalised dB at each LF_HZ]}, [THD% per tone])."""
    fr = {}
    for lv in LEVELS:
        f, m = A.transfer(A.seg_of(sig, lv), A.seg_of(orig, lv))
        ref = A.gain_at(f, m, NORM_HZ)
        fr[lv] = [A.gain_at(f, m, hz) - ref for hz in LF_HZ]
    return fr, [A.thd(A.seg_of(sig, f"tone_{t}"), t)[0] for t in THD_TONES]


def main():
    if not os.path.exists(C.RENDER_BIN):
        sys.exit(f"missing {C.RENDER_BIN} — build OfflineRender first")
    orig = A.load(A.ORIG)
    orig.astype(np.float32).tofile(IN_F32)

    caps = [(p, q) for p, q in C.find_captures() if q["rev"] == "Medium"]
    if not caps:
        sys.exit("no Medium captures found in analysis/pedal2")
    print(f"\n{len(caps)} Medium captures x {len(MULTS)} kNMedium values "
          f"=> {len(caps) * len(MULTS)} renders (shipped = x{SHIPPED})\n")

    ped = {q["drive"]: features(A.align(A.load(p), orig)[0], orig) for p, q in caps}

    plug = {}
    for _, q in caps:
        for mult in MULTS:
            r = subprocess.run([C.RENDER_BIN, IN_F32, OUT_F32]
                               + C.render_args(q, extra_args=xargs(KN * mult)),
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(f"  ! render failed D{q['drive']} x{mult}: {r.stderr.strip()[:200]}")
                continue
            x, _ = A.align(np.fromfile(OUT_F32, dtype=np.float32).astype(np.float64), orig)
            plug[(q["drive"], mult)] = features(x, orig)

    for i, hz in enumerate(LF_HZ):
        print(f"=== {hz:.0f} Hz — LF dev (plugin - pedal, 1 kHz-normalised) ===")
        print(f"  {'D':>5} {'level':>9} | " + "".join(f"{f'x{m:.2f}':>9}" for m in MULTS))
        print("  " + "-" * 66)
        for _, q in caps:
            for lv in LEVELS:
                row = [plug[(q["drive"], m)][0][lv][i] - ped[q["drive"]][0][lv][i]
                       if (q["drive"], m) in plug else float("nan") for m in MULTS]
                print(f"  {q['drive']:5.2f} {lv.replace('sweep_', ''):>9} | "
                      + "".join(f"{v:+9.2f}" for v in row))
            print()

    print("=== THD dev (plugin - pedal, % absolute) at tone_110 / 440 / 1000 ===")
    print(f"  {'D':>5} | " + "".join(f"{f'x{m:.2f}':>24}" for m in MULTS))
    print("  " + "-" * 102)
    for _, q in caps:
        cells = []
        for m in MULTS:
            if (q["drive"], m) not in plug:
                cells.append("n/a")
                continue
            d = [a - b for a, b in zip(plug[(q["drive"], m)][1], ped[q["drive"]][1])]
            cells.append(" / ".join(f"{v:+.1f}" for v in d))
        print(f"  {q['drive']:5.2f} | " + "".join(f"{c:>24}" for c in cells))

    print("\n=== aggregate ===")
    agg = {}
    for m in MULTS:
        lf = [abs(plug[(q["drive"], m)][0][lv][i] - ped[q["drive"]][0][lv][i])
              for _, q in caps for lv in LEVELS for i in range(len(LF_HZ))
              if (q["drive"], m) in plug]
        th = [abs(a - b) for _, q in caps if (q["drive"], m) in plug
              for a, b in zip(plug[(q["drive"], m)][1], ped[q["drive"]][1])]
        agg[m] = (float(np.mean(lf)), float(np.mean(th)))
        tag = "  <- shipped" if m == SHIPPED else ""
        print(f"  x{m:.2f}: mean |LF dev| = {agg[m][0]:.3f} dB   "
              f"mean |THD dev| = {agg[m][1]:.2f} %{tag}")

    span = max(v[0] for v in agg.values()) - min(v[0] for v in agg.values())
    delta = agg[SHIPPED][0] - agg[MULTS[-1]][0]
    print()
    print(f"  LF metric spanned by the WHOLE {MULTS[0]}..{MULTS[-1]} range: {span:.3f} dB")
    print(f"  LF metric bought by shipped -> x{MULTS[-1]}:                  {delta:.3f} dB")
    print("  Both LF and THD prefer HIGHER kNMedium, so there is no trade between them here —")
    print("  but the movement is negligible, and the real cap is the op-amp rails (Medium H2")
    print("  +3.48 -> +10.45 dB at 1.5x, Stage1.h). Lever 3 refuted; keep 1.35x.")
    print()


if __name__ == "__main__":
    main()
