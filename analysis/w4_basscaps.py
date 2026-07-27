#!/usr/bin/env python3
"""v1.4 W4 — is the LF residual a COMPONENT error (C3/C4) rather than an output-shelf problem?

BassTilt.h fixes the LF error empirically, at the OUTPUT, with a static shelf. That works
(SHAPE 12/16 -> 16/16) but has two smells: it is not circuit-derived, and being post-clip and
static it cannot track the error's level-dependence, leaving an irreducible ~0.42 dB residual.

A component error would be strictly better on both counts. C3 (39n) and C4 (1u) DOMINATE the
deep-LF cut — TaperUtils.h's bassResistance note says so explicitly ("the deep-LF cut is dominated
by C3/C4, not the pot R") — and they sit PRE-clip, so a wrong value produces an error that is
naturally knob- AND level-dependent, exactly the signature measured. Critically, W4's lever 5 only
verified the DSP MATCHES circuit.md; it never asked whether circuit.md is RIGHT, and circuit.md is
the only surviving source (the schematic images were removed) and is internally inconsistent about
this very network in three places.

Method: render all 16 pedal2 captures with BassTilt DISABLED (argv[25]=0, bit-transparent) over a
grid of C3/C4 values, and score the LF error the same way BassTilt was fitted — worst |deviation|
over the LF SHAPE bands and all four sweep depths, 1 kHz-normalised. If some (C3, C4) beats the
shipped 39n/1u by enough, the shelf is a workaround for a wrong component and should be replaced.

Usage (from the repo root):
    analysis/.venv/bin/python3 analysis/w4_basscaps.py [--jobs N] [--quick]

Sign convention: deviation = plugin - pedal, 1 kHz-normalised. Positive = plugin hotter.
"""
import argparse
import concurrent.futures
import os
import subprocess
import sys

import numpy as np

os.environ.setdefault("SIGNAL", "v2")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A  # noqa: E402
import captures as C  # noqa: E402

C3_SHIPPED = 39.0e-9
C4_SHIPPED = 1.0e-6
LF_HZ = [63.5, 127.0, 254.0]
NORM_HZ = 1015.9
LEVELS = ["sweep_clean", "sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6"]

# Multipliers on the shipped values. Deliberately spans standard-series neighbours: 39n's E12
# neighbours are 33n/47n (x0.85 / x1.20) and 1u's are 680n/1u5 (x0.68 / x1.5), so a mis-read or
# mis-specified part lands inside this grid rather than outside it.
C3_MULTS = [0.50, 0.68, 0.85, 1.00, 1.20, 1.50, 2.00]
C4_MULTS = [0.47, 0.68, 1.00, 1.50, 2.20]

_ORIG = None
_IN_F32 = "/tmp/w4_caps_in.f32"


def _init():
    global _ORIG
    _ORIG = A.load(A.ORIG)


def xargs(c3, c4, bass_coeff=-1.0, bass_exp=1.43):
    """argv[10..27]; BassTilt forced OFF so this measures the RAW model, not model+shelf.

    argv[13]/[14] are the BASS taper overrides (BASS_R = coeff * bassX^exp), which let the same
    harness test the OTHER pre-clip component lever without a rebuild — see --taper.
    """
    a = ["1.2", "-1", "1.43", f"{bass_coeff:.6g}", f"{bass_exp:.6g}", "-1", "0", "-1", "1", "9",
         "-1", "-1", "-1", "1", "-1", "0", f"{c3:.6e}", f"{c4:.6e}"]
    assert len(a) == 18, f"argv[10..27] must be 18 entries, got {len(a)}"
    return a


def lf_dev(sig, ped):
    """Worst |plugin-pedal| over LF bands x levels, 1 kHz-normalised."""
    worst = 0.0
    for lv in LEVELS:
        f, m = A.transfer(A.seg_of(sig, lv), A.seg_of(_ORIG, lv))
        ref = A.gain_at(f, m, NORM_HZ)
        for hz in LF_HZ:
            worst = max(worst, abs((A.gain_at(f, m, hz) - ref) - ped[lv][hz]))
    return worst


def pedal_curve(path):
    a, _ = A.align(A.load(path), _ORIG)
    out = {}
    for lv in LEVELS:
        f, m = A.transfer(A.seg_of(a, lv), A.seg_of(_ORIG, lv))
        ref = A.gain_at(f, m, NORM_HZ)
        out[lv] = {hz: A.gain_at(f, m, hz) - ref for hz in LF_HZ}
    return out


def _pedal_job(path):
    return path, pedal_curve(path)


def _render_job(job):
    key, extra, parsed, ped = job
    out = f"/tmp/w4_caps_{os.getpid()}.f32"
    r = subprocess.run([C.RENDER_BIN, _IN_F32, out] + C.render_args(parsed, extra_args=extra),
                       capture_output=True, text=True)
    if r.returncode != 0:
        return (key, None)
    x, _ = A.align(np.fromfile(out, dtype=np.float32).astype(np.float64), _ORIG)
    return (key, lf_dev(x, ped))


# BASS taper grid (BASS_R = coeff * bassX^exp). The coefficient IS R at x=1, so it is capped by the
# physical pot: a 50k pot cannot present more than 50k, and values above that are not a taper the
# hardware could have. Shipped is 50k * x^2.41.
TAPER_COEFFS = [30.0e3, 40.0e3, 50.0e3]
TAPER_EXPS = [1.80, 2.41, 3.00, 3.50, 4.00, 4.70]


def run_taper(caps, ped, jobs):
    """Sweep the BASS taper (the OTHER pre-clip lever) with BassTilt off."""
    print("\nBASS TAPER sweep — BASS_R = coeff * bassX^exp, BassTilt DISABLED, C3/C4 shipped.")
    print("The coefficient is R at x=1, so >50k is not physically realisable on a 50k pot.\n")
    grid = [(k, e) for k in TAPER_COEFFS for e in TAPER_EXPS]
    work = [((k, e), xargs(-1.0, -1.0, k, e), q, ped[p]) for (k, e) in grid for p, q in caps]
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs, initializer=_init) as ex:
        results = list(ex.map(_render_job, work, chunksize=1))
    agg = {}
    for key, dev in results:
        if dev is not None:
            agg.setdefault(key, []).append(dev)

    print("worst |LF deviation| over all captures x levels x LF bands (dB)")
    print(f"  {'coeff':>8} | " + "".join(f"{f'x^{e:.2f}':>11}" for e in TAPER_EXPS))
    print("  " + "-" * (10 + 11 * len(TAPER_EXPS)))
    best = None
    for k in TAPER_COEFFS:
        cells = ""
        for e in TAPER_EXPS:
            vals = agg.get((k, e))
            if not vals:
                cells += f"{'-':>11}"
                continue
            mx = max(vals)
            mark = "*" if (abs(k - 50.0e3) < 1 and abs(e - 2.41) < 1e-9) else " "
            cells += f"{mx:>10.2f}{mark}"
            if best is None or mx < best[0]:
                best = (mx, k, e, float(np.mean(vals)))
        print(f"  {k / 1e3:7.0f}k | {cells}")
    print("  (* = shipped 50k * x^2.41)")
    if best:
        mx, k, e, mean = best
        print(f"\n  best physical taper: {k / 1e3:.0f}k * x^{e:.2f} -> worst {mx:.2f} dB, "
              f"mean {mean:.2f} dB")
        print(f"  shipped BassTilt shelf achieves worst 1.14 dB (probe 8) for comparison.")
    print()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--quick", action="store_true",
                    help="C3 only, at the shipped C4 (fast screen)")
    ap.add_argument("--taper", action="store_true",
                    help="sweep the BASS taper instead of C3/C4 (the other pre-clip lever)")
    args = ap.parse_args()

    if not os.path.exists(C.RENDER_BIN):
        sys.exit(f"missing {C.RENDER_BIN} — build OfflineRender first")
    _init()
    _ORIG.astype(np.float32).tofile(_IN_F32)

    caps = C.find_captures()
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs, initializer=_init) as ex:
        ped = dict(ex.map(_pedal_job, [p for p, _ in caps]))

    if args.taper:
        run_taper(caps, ped, args.jobs)
        return

    grid = [(C3_SHIPPED * a, C4_SHIPPED * b)
            for a in C3_MULTS for b in ([1.00] if args.quick else C4_MULTS)]
    print(f"\n{len(caps)} captures x {len(grid)} (C3,C4) points = {len(caps) * len(grid)} renders")
    print(f"shipped: C3 = {C3_SHIPPED * 1e9:.0f}n, C4 = {C4_SHIPPED * 1e6:.2f}u  "
          f"(BassTilt DISABLED for all renders)\n")

    with concurrent.futures.ProcessPoolExecutor(max_workers=args.jobs,
                                                initializer=_init) as ex:
        work = [((c3, c4), xargs(c3, c4), q, ped[p]) for (c3, c4) in grid for p, q in caps]
        results = list(ex.map(_render_job, work, chunksize=1))

    agg = {}
    for key, dev in results:
        if dev is None:
            continue
        agg.setdefault(key, []).append(dev)

    print("worst |LF deviation| over all captures x levels x LF bands (dB)")
    print(f"  {'C3':>8} | " + "".join(f"{f'C4 x{b:.2f}':>11}" for b in
                                      ([1.00] if args.quick else C4_MULTS)))
    print("  " + "-" * (10 + 11 * len(([1.00] if args.quick else C4_MULTS))))
    best = None
    for a in C3_MULTS:
        c3 = C3_SHIPPED * a
        cells = ""
        for b in ([1.00] if args.quick else C4_MULTS):
            c4 = C4_SHIPPED * b
            vals = agg.get((c3, c4))
            if not vals:
                cells += f"{'-':>11}"
                continue
            mx = max(vals)
            mark = "*" if (a == 1.0 and b == 1.0) else " "
            cells += f"{mx:>10.2f}{mark}"
            if best is None or mx < best[0]:
                best = (mx, a, b, float(np.mean(vals)))
        print(f"  {c3 * 1e9:7.1f}n | {cells}")
    print("  (* = shipped values)")

    ship = max(agg[(C3_SHIPPED, C4_SHIPPED)])
    ship_mean = float(np.mean(agg[(C3_SHIPPED, C4_SHIPPED)]))
    print()
    print(f"  shipped 39n/1.00u : worst {ship:.2f} dB, mean {ship_mean:.2f} dB")
    if best:
        mx, a, b, mean = best
        print(f"  best on this grid : C3 x{a:.2f} ({C3_SHIPPED * a * 1e9:.1f}n), "
              f"C4 x{b:.2f} ({C4_SHIPPED * b * 1e6:.2f}u) -> worst {mx:.2f} dB, mean {mean:.2f} dB")
        print(f"  improvement       : worst {ship - mx:+.2f} dB, mean {ship_mean - mean:+.2f} dB")
        print()
        print("  DECIDE: a component fix is only preferable if it gets close to what the shipped")
        print("  BassTilt shelf achieves (worst LF deviation 1.14 dB with the shelf, from probe 8).")
        print("  If the best grid point is far above that, the LF error is NOT a C3/C4 value error")
        print("  and the shelf stays. If it is comparable or better, replace the shelf with the")
        print("  component value and re-run the full gate.")
    print()


if __name__ == "__main__":
    main()
