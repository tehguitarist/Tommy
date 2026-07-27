"""v1.4 W8 — the plugin is missing the pedal's LOW-FREQUENCY CONTOUR (a ~40 Hz shelf).

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

Usage (from the repo root):
    analysis/.venv/bin/python3 analysis/w8_lf_contour.py [--only contour,shelf]

Reads analysis/reports/comprehensive_data.json only — no renders, no build needed.
"""

import argparse
import json
import math
import os
import statistics as st
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(REPO, "analysis/reports/comprehensive_data.json")
LEVELS = ["sweep_clean", "sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6"]
CONTOUR_HI = 400.0   # top of the "bass rise" window
SHELF_HI = 2600.0    # the gap is flat well past here; stop before the top-octave (W3) region


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
        f1 = 12.5
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

    print("\n    CAVEAT that must travel with any fix: the 'pedal' side includes the NAM reamp")
    print("    chain, which has its own subsonic roll-off. CAPTURE_SPEC's bypass anchor would have")
    print("    separated pedal from chain, and W6 struck all further captures — so this cannot be")
    print("    attributed to the pedal itself on the evidence available.")


STEPS = {"contour": contour, "shelf": shelf}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=None, help="comma-separated subset of: " + ",".join(STEPS))
    a = ap.parse_args()
    for n in ([s.strip() for s in a.only.split(",")] if a.only else list(STEPS)):
        if n not in STEPS:
            sys.exit(f"unknown step {n!r}; choose from {','.join(STEPS)}")
        STEPS[n]()


if __name__ == "__main__":
    main()
