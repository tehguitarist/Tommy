"""v1.4 W8 — the plugin is missing the pedal's LOW-FREQUENCY CONTOUR (a ~40 Hz shelf). FIXED.

STATUS: fixed and shipped 2026-07-27 — `InputBuffer.h` kC2 39n -> 16.4n, moving the PRE-CLIP input
high-pass from 8.0 to 19.1 Hz. Probe 3 (`fit`) is the sweep that chose that value; probes 1-2 are
the characterisation and now measure what is LEFT. Numbers below describe the error as found.

WHY THIS IS A SEPARATE ITEM FROM W4, AND WHY IT WAS MISSED FOR SO LONG
---------------------------------------------------------------------
W4 fixed the BASS<->DRIVE coupling around 250 Hz and is genuinely closed (from 64 Hz up the
1 kHz-normalised deviation is <= 0.25 dB). What is left is a different error with a different
shape, and every metric in the harness was blind to it for the same two reasons:

  1. **Every LF metric in this repo normalises at 1 kHz and then reports a per-band deviation.**
     That is a FIT-TO-LINE measure. A whole-curve CONTOUR error shows up in it as a small residual
     smeared across many bands (+2.11 dB at one band, +0.79 at the next, +0.25 at the next), which
     reads as "close enough" band by band while the two curves visibly differ in shape. The user
     spotted it by eye on the dashboard, from the curves themselves, which the numbers had not.
  2. **`w4_basscaps.py` scored C3/C4 on the 64/127/254 Hz bands** and concluded the shipped caps
     were optimal — but that same work recorded that "C4 is nearly irrelevant at 64-254 Hz; it only
     dominates far lower (~20 Hz)". So the sweep evaluated C4 exactly where C4 does nothing.
     **"C3/C4 refuted" is NOT a supported conclusion for the 20-50 Hz contour.**

Probes:
  1. `contour`  — how much LF RISE each side has (max dB over 20-400 Hz, minus the 20 Hz value),
     per capture and sweep level. This is a shape metric, not a fit metric, and it is the one that
     makes the error obvious: 16/16 captures, all four levels, the pedal rises more.
  2. `shelf`    — normalise BOTH curves at 20 Hz and fit the (pedal - plugin) gap. It is a clean
     first-order shelf: 0 dB at 20 Hz, plateau by ~200 Hz, flat thereafter. Reports the fitted
     plateau and corner, and the equivalent HIGH-PASS CORNER PAIR (see the note in `shelf`).
  3. `fit`      — sweep the pre-clip HP corner (C2) over real renders and score the LF error per
     sweep LEVEL. This is the probe that chose the shipped value. RENDERS: needs OfflineRender
     built, and takes a few minutes. Not in the default step set.

Usage (from the repo root):
    analysis/.venv/bin/python3 analysis/w8_lf_contour.py [--only contour,shelf]
    analysis/.venv/bin/python3 analysis/w8_lf_contour.py --only fit [--mults 1.00,0.47,0.42]

Probes 1-2 read analysis/reports/comprehensive_data.json only — no renders, no build needed. Note
that JSON must be REGENERATED (comprehensive_report.py) after any DSP change, or they will score
the old model.
"""

import argparse
import json
import math
import os
import statistics as st
import sys

import numpy as np

os.environ.setdefault("SIGNAL", "v2")  # pedal2 is a v2-layout capture set — see W2's harness note

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(REPO, "analysis/reports/comprehensive_data.json")
LEVELS = ["sweep_clean", "sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6"]
CONTOUR_HI = 400.0   # top of the "bass rise" window
SHELF_HI = 2600.0    # the gap is flat well past here; stop before the top-octave (W3) region

# --- probe 3 (`fit`) only: the pre-clip high-pass sweep -------------------------------------
C2_SHIPPED = 39.0e-9   # documented nominal (circuit.md); swept as the realisation of the corner
R2_OHMS = 510.0e3      # bias resistor it works against — sets the input pole with C2
NORM_HZ = 1015.9       # midband anchor: independently calibrated to +-0.35 dB, so it is the datum
# The plugin's own SMALL-SIGNAL composite high-pass corner: InputBuffer's kC2/R2 pole (19.1 Hz once
# W8 shipped; 8.0 Hz before it) cascaded with the ~6 Hz C6 output DC block. Used by `shelf` to turn a
# measured plateau into an implied pedal corner. Update it if kC2 changes.
PLUGIN_HP_HZ = 20.8    # pre-W8 this was 12.5
LF_HZ = [20.0, 25.2, 31.7, 40.0, 50.4, 63.5]  # where W8 lives: the contour below ~64 Hz
# Multipliers on C2. The top of the range is the shipped part; the bottom overshoots the ~14.6n
# the algebra predicts, so the grid brackets the optimum instead of ending at it.
C2_MULTS = [1.00, 0.80, 0.65, 0.55, 0.47, 0.40, 0.34, 0.28]

_ORIG = None
_IN_F32 = "/tmp/w8_hp_in.f32"
A = None
C = None


def _corner(c2):
    """Input-network pole in Hz for a given C2, against R2 = 510k."""
    return 1.0 / (2.0 * math.pi * R2_OHMS * c2)


def _fit_init():
    """Process-pool initialiser: import the harness and load the dry reference once per worker."""
    global _ORIG, A, C
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import analyze as _A
    import captures as _C
    A, C = _A, _C
    _ORIG = A.load(A.ORIG)


def _lf_curve(sig):
    """plugin-or-pedal gain at the LF bands, 1 kHz-normalised, per sweep level."""
    out = {}
    for lv in LEVELS:
        f, m = A.transfer(A.seg_of(sig, lv), A.seg_of(_ORIG, lv))
        ref = A.gain_at(f, m, NORM_HZ)
        out[lv] = np.array([A.gain_at(f, m, hz) - ref for hz in LF_HZ])
    return out


def _ped_job(path):
    a, _ = A.align(A.load(path), _ORIG)
    return path, _lf_curve(a)


def _fit_job(job):
    import subprocess
    c2, parsed, ped = job
    out = f"/tmp/w8_hp_{os.getpid()}.f32"
    extra = ["1.2", "-1", "1.43", "-1", "1.43", "-1", "0", "-1", "1", "9",
             "-1", "-1", "-1", "1", "-1", "-1", "-1", "-1", f"{c2:.6e}"]
    assert len(extra) == 19, "argv[10..28]"
    r = subprocess.run([C.RENDER_BIN, _IN_F32, out] + C.render_args(parsed, extra_args=extra),
                       capture_output=True, text=True)
    if r.returncode != 0:
        return (c2, None)
    x, _ = A.align(np.fromfile(out, dtype=np.float32).astype(np.float64), _ORIG)
    plug = _lf_curve(x)
    return (c2, [{"level": lv, "bands": plug[lv] - ped[lv]} for lv in LEVELS])


def load():
    with open(JSON_PATH) as f:
        return json.load(f)


def _tag(c):
    s = c["settings"]
    return f"{c['rev']:<6} B{s['bass']:.2f} D{s['drive']:.2f}"


def contour():
    """Probe 1: LF RISE per side. A shape metric — deliberately NOT normalised at 1 kHz.

    rise = max(dB over 20..400 Hz) - dB(20 Hz). It asks "how much bass contour does this curve
    have", which is what the eye reads off the dashboard, rather than "how close are the two
    curves after I slide one onto the other", which is what every other LF metric here asks.
    """
    d = load()
    b = d["meta"]["bands"]
    idx = [i for i, x in enumerate(b) if x <= CONTOUR_HI]
    i20 = b.index(20.0)

    print("\n" + "=" * 92)
    print(f"P1  LF CONTOUR — rise over 20-{CONTOUR_HI:.0f} Hz relative to each curve's own 20 Hz value")
    print("=" * 92)
    print("    'missing' = pedal rise - plugin rise. Positive => the plugin is FLATTER than the")
    print("    pedal down low, i.e. it passes too much sub-bass relative to its own midband.")

    for lev in LEVELS:
        pr, er = [], []
        print(f"\n  {lev}")
        print(f"    {'capture':<22}{'plug rise':>10}{'ped rise':>10}{'missing':>9}"
              f"{'plug pk':>9}{'ped pk':>8}")
        for c in d["captures"]:
            fr = c["fr"][lev]
            pg = [fr["plugin_db"][i] for i in idx]
            pd = [fr["pedal_db"][i] for i in idx]
            rp, rd = max(pg) - pg[i20], max(pd) - pd[i20]
            pr.append(rp)
            er.append(rd)
            print(f"    {_tag(c):<22}{rp:>10.2f}{rd:>10.2f}{rd - rp:>+9.2f}"
                  f"{b[idx[pg.index(max(pg))]]:>9.0f}{b[idx[pd.index(max(pd))]]:>8.0f}")
        print(f"    {'MEDIAN':<22}{st.median(pr):>10.2f}{st.median(er):>10.2f}"
              f"{st.median(er) - st.median(pr):>+9.2f}")

    print("\n    NOTE the level trend: the gap shrinks as the sweep gets hotter. That is clipping")
    print("    MASKING a linear error (both sides pin to the clip ceiling), not evidence against")
    print("    one — the same lesson W4 had to retract twice. The clean sweep is the least-masked")
    print("    and therefore the most revealing measurement of the underlying linear size.")


def shelf():
    """Probe 2: fit the gap as a first-order low shelf, and as an equivalent high-pass pair.

    Both curves are normalised at 20 Hz, then gap(f) = pedal(f) - plugin(f). Measured, that gap is
    0 at 20 Hz, rises, and plateaus flat from ~200 Hz to at least 2.5 kHz — a first-order shelf.

    The high-pass reading is the physically meaningful one. If the plugin high-passes at f1 and the
    pedal at f2 > f1, then normalising both at 20 Hz produces exactly this shape, with

        plateau_dB = 10*log10( (1 + (f2/20)^2) / (1 + (f1/20)^2) )

    so a measured plateau pins f2 once f1 is known. The plugin's f1 is set by C2(39n)+R2(510k)
    ~ 8.0 Hz in InputBuffer.h, cascaded with the C6 output DC block — an effective ~12-13 Hz.
    """
    d = load()
    b = d["meta"]["bands"]
    i20 = b.index(20.0)
    idx = [i for i, x in enumerate(b) if x <= SHELF_HI]
    f = np.array([b[i] for i in idx])

    print("\n" + "=" * 92)
    print("P2  Fit the gap (both curves normalised at 20 Hz) as a first-order shelf / HP pair")
    print("=" * 92)

    for lev in LEVELS:
        gaps = []
        for c in d["captures"]:
            fr = c["fr"][lev]
            pg = np.array([fr["plugin_db"][i] for i in idx]) - fr["plugin_db"][i20]
            pd = np.array([fr["pedal_db"][i] for i in idx]) - fr["pedal_db"][i20]
            gaps.append(pd - pg)
        g = np.median(np.array(gaps), axis=0)

        # first-order shelf: A * (f^2/(f^2+fc^2)) normalised to 0 at 20 Hz
        best = None
        for fc in np.arange(5.0, 200.0, 0.5):
            shape = f ** 2 / (f ** 2 + fc ** 2)
            shape = shape - (400.0 / (400.0 + fc ** 2))
            A = float(np.dot(shape, g) / (np.dot(shape, shape) + 1e-30))
            e = float(np.sqrt(np.mean((A * shape - g) ** 2)))
            if best is None or e < best[0]:
                best = (e, fc, A)
        e, fc, A = best

        plateau = float(np.median(g[f >= 200.0]))
        # equivalent HP corner pair, taking the plugin's own effective corner as f1
        f1 = PLUGIN_HP_HZ
        ratio = 10 ** (plateau / 10.0) * (1 + (f1 / 20.0) ** 2)
        f2 = 20.0 * math.sqrt(max(ratio - 1.0, 1e-9))

        print(f"\n  {lev}")
        print(f"    measured plateau (>=200 Hz)      {plateau:+.2f} dB")
        print(f"    fitted shelf                     {A:+.2f} dB, corner {fc:.1f} Hz"
              f"   (rms {e:.3f} dB)")
        print(f"    equivalent HP pair               plugin {f1:.1f} Hz  ->  pedal {f2:.1f} Hz")
        print(f"    {'Hz':>7}" + "".join(f"{x:>8.0f}" for x in
                                         [20, 32, 40, 64, 101, 202, 508, 1016, 2032]))
        show = [int(np.argmin(np.abs(f - x))) for x in [20, 32, 40, 64, 101, 202, 508, 1016, 2032]]
        print(f"    {'gap':>7}" + "".join(f"{g[i]:>+8.2f}" for i in show))

    print("\n    READING THIS POST-W8: the implied pedal corner is now an UPPER BOUND on what is")
    print("    left, not a fresh measurement of the pedal. Pre-W8 (plugin f1 = 12.5 Hz) the same")
    print("    fit read the pedal at 23.0 Hz on the clean sweep; with f1 moved to 20.8 the residual")
    print("    plateau implies a HIGHER f2 than that, which the pedal obviously did not do. The")
    print("    reason is that a PRE-clip corner change is partly compressed by Stage 1's clipper")
    print("    even on the -30 dBFS clean sweep (its 1 kHz anchor is past the diode clamp in 11/16")
    print("    captures — W4 probe 4), so the linear algebra OVER-states how far the effective")
    print("    corner actually moved. Judge the fix on `fit`'s per-level deviations, not on f2.")
    print("\n    CAVEAT that must travel with any fix: the 'pedal' side includes the NAM reamp")
    print("    chain, which has its own subsonic roll-off. CAPTURE_SPEC's bypass anchor would have")
    print("    separated pedal from chain, and W6 struck all further captures — so this cannot be")
    print("    attributed to the pedal itself on the evidence available.")


def fit(jobs, mults):
    """Probe 3: sweep the PRE-CLIP high-pass corner (C2) and score the LF error on real renders.

    Why C2 and not a post-clip shelf: the error's level-collapse (+2.24 dB clean -> +0.77 at
    -6 dBFS) is clipping MASKING a linear error. A filter placed before the clipper reproduces that
    collapse for free; a static post-clip shelf cannot, and would have to sit in the middle of the
    range (BassTilt already carries a ~0.42 dB irreducible residual for exactly this reason, and its
    250 Hz corner cannot reach 40 Hz anyway).

    Score = plugin - pedal at the LF bands, 1 kHz-normalised, over all 16 captures x 4 sweep levels.
    The full shipped chain is active (BassTilt ON) because that is what would ship; W4's gate is
    re-checked separately with knob_tracking.

    C2 is swept as the realisation of the corner, NOT as a claim about the part: 39n is documented
    and the shipped nominal. The corner printed beside each row is 1/(2*pi*R2*C2) with R2 = 510k.
    """
    import concurrent.futures

    _fit_init()
    _ORIG.astype(np.float32).tofile(_IN_F32)
    caps = C.find_captures()

    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs, initializer=_fit_init) as ex:
        ped = dict(ex.map(_ped_job, [p for p, _ in caps]))

    grid = [C2_SHIPPED * m for m in mults]
    print(f"\n{len(caps)} captures x {len(grid)} C2 values = {len(caps) * len(grid)} renders")
    print(f"shipped C2 = {C2_SHIPPED * 1e9:.0f}n  (input pole {_corner(C2_SHIPPED):.1f} Hz; "
          f"cascaded with the C6 DC block the effective corner is ~12.5 Hz)\n")

    work = [(c2, q, ped[p]) for c2 in grid for p, q in caps]
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs, initializer=_fit_init) as ex:
        results = list(ex.map(_fit_job, work, chunksize=1))

    agg = {}
    for c2, dev in results:
        if dev is not None:
            agg.setdefault(c2, []).extend(dev)

    print("plugin - pedal, 1 kHz-normalised (dB). Positive = the plugin passes too much down low.")
    print(f"  {'C2':>7} {'pole':>7} | " + "".join(f"{f'{h:.0f}Hz':>8}" for h in LF_HZ)
          + f"{'rms':>9}{'worst':>8}")
    print("  " + "-" * (18 + 8 * len(LF_HZ) + 17))
    best = None
    for c2 in grid:
        vals = agg.get(c2)
        if not vals:
            continue
        arr = np.array([v["bands"] for v in vals])      # (capture*level, band)
        med = np.median(arr, axis=0)
        rms = float(np.sqrt(np.mean(arr ** 2)))
        worst = float(np.max(np.abs(arr)))
        mark = "*" if abs(c2 - C2_SHIPPED) < 1e-15 else " "
        print(f"  {c2 * 1e9:6.1f}n{mark}{_corner(c2):>7.1f} | "
              + "".join(f"{x:>+8.2f}" for x in med) + f"{rms:>9.3f}{worst:>8.2f}")
        if best is None or rms < best[0]:
            best = (rms, c2, worst)
    print("  (* = shipped 39n)")

    if best:
        rms, c2, worst = best
        ship = np.array([v["bands"] for v in agg[C2_SHIPPED]])
        print(f"\n  shipped 39n      : rms {float(np.sqrt(np.mean(ship ** 2))):.3f} dB, "
              f"worst {float(np.max(np.abs(ship))):.2f} dB")
        print(f"  best on the grid : C2 {c2 * 1e9:.1f}n (pole {_corner(c2):.1f} Hz) -> "
              f"rms {rms:.3f} dB, worst {worst:.2f} dB")

    # Per-level breakdown at the shipped value vs the best: does a PRE-clip fix track the
    # level-collapse for free? If it does, every level improves, not just the clean sweep.
    print("\n  per-level median |deviation| over the LF bands — the test of pre-clip placement.")
    print("  A pre-clip filter is supposed to track the level-collapse for free, so the honest")
    print("  check is whether EVERY level improves. Ship on the minimax, not on the rms: the rms")
    print("  is dominated by the clean sweep, which is the one level nobody plays at.")
    print(f"    {'C2':>8}{'pole':>7} | " + "".join(f"{lv.replace('sweep_', ''):>10}" for lv in LEVELS)
          + f"{'minimax':>10}")
    mm = None
    for c2 in grid:
        vals = agg.get(c2)
        if not vals:
            continue
        per = [float(np.median(np.abs(np.array([v["bands"] for v in vals if v["level"] == lv]))))
               for lv in LEVELS]
        cells = "".join(f"{x:>10.2f}" for x in per)
        print(f"    {c2 * 1e9:6.1f}n{_corner(c2):>7.1f} | {cells}{max(per):>10.2f}")
        if mm is None or max(per) < mm[0]:
            mm = (max(per), c2)
    if mm:
        print(f"\n  minimax-optimal  : C2 {mm[1] * 1e9:.1f}n (pole {_corner(mm[1]):.1f} Hz) -> "
              f"worst level {mm[0]:.2f} dB")


STEPS = {"contour": contour, "shelf": shelf, "fit": None}  # `fit` is dispatched separately (renders)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="contour,shelf",
                    help="comma-separated subset of: " + ",".join(STEPS)
                         + "  (`fit` RENDERS — needs OfflineRender built; not in the default set)")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--mults", default=None,
                    help="comma-separated C2 multipliers for `fit` (default: the bracketing grid)")
    a = ap.parse_args()
    for n in [s.strip() for s in a.only.split(",")]:
        if n not in STEPS:
            sys.exit(f"unknown step {n!r}; choose from {','.join(STEPS)}")
        if n == "fit":
            mults = [float(x) for x in a.mults.split(",")] if a.mults else C2_MULTS
            fit(a.jobs, sorted(mults, reverse=True))
        else:
            STEPS[n]()


if __name__ == "__main__":
    main()
