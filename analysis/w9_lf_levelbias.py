#!/usr/bin/env python3
"""v1.4 W9 — BassTilt is fitted to the CLEAN sweep and overcorrects every level you play at.

THE OBSERVATION (user, 2026-07-27, by eye on the dashboard's default `raw (null gain)` FR view):
too much bass at low gain (D0.35) and a touch too much at high gain, with 200 Hz-2 kHz reading
light where the bass reads heavy (so it looks like a TILT); `Medium D0.65` is the opposite way
round (light below 200 Hz, hot above); `Hard D0.20` is a strange exception that behaves; and the
20 Hz start point is good everywhere (i.e. W8 is holding).

WHAT THE NUMBERS SAY. Split the 1 kHz-normalised deviation into three windows -- SUB = 20-32 Hz
(W8's turf), LF = 40-160 Hz, MID = 202-806 Hz -- and the "tilt" decomposes into one real error and
one artefact:

  * **MID is already exact**: the driven-mean deviation over 202-806 Hz is -0.24..+0.04 dB across
    all 16 captures. The "200 Hz-2 kHz is light" half of the observation is the `raw` view's
    least-squares broadband gain being dragged UP by the LF excess -- the artefact CLAUDE.md
    already documents. It is not a midband deficit and must not be corrected.
  * **LF is a real, DRIVE-ordered, SIGN-FLIPPING error** that survives the shipped BassTilt:
        D0.35 driven  +0.39 .. +0.80 dB HOT      (Soft worst)
        D0.50 driven  +0.16 .. +0.19 dB
        D0.65 driven  -0.30 .. -0.90 dB LIGHT    (Medium worst)
        D0.80/1.00    -0.21 .. -0.46 dB LIGHT
        Hard D0.20    -0.02 dB                   <- the user's "strange exception", exact
    Every one of those matches the reported direction, including the D0.65 reversal.

THE MECHANISM -- and why this is a fit-weighting bug, not a new physical error. At EVERY setting
the clean sweep wants the OPPOSITE sign from the three driven sweeps, and roughly twice the
magnitude. W4 fitted BassTilt minimax across all four sweep depths, so the clean sweep -- the one
level nobody plays at -- set the table, and the driven sweeps inherit about half the shelf as
overcorrection. Removing BassTilt entirely would leave the driven sweeps NEARLY CORRECT at D0.35
and the clean sweep ~2 dB out.

There is independent reason to distrust the clean sweep here, established by W4's own probe 4:
`sweep_clean` is -30 dBFS and Stage 1's midband gain is 25-44 dB, so its 1 kHz NORMALISATION
ANCHOR is past the diode clamp in 12/16 captures. The driven sweeps are not anchor-"safe" either
(W4 lever 4) -- they are hotter still -- but on them plugin and pedal compress IN STEP, which is
what makes them the better reference. Weighting the fit toward them is the same call W8 made when
it chose the minimax-across-levels over the rms (the rms optimum was the clean sweep outvoting the
rest).

WHAT THIS PROBE DOES. Sweeps BassTilt's strength (`offline_render` argv[25], 0.0 = correction
disabled, 1.0 = shipped) over all 16 pedal2 captures x 4 sweep levels and scores the three windows.
Because the shelf gain maps near-linearly onto LF dB, it then solves per capture for the scale that
zeroes the LF error at each level, and reports the DRIVEN-ONLY optimum -- i.e. the refit table you
would ship if the clean sweep did not get a vote.

  Probe 1 `sweep`   -- LF/SUB/MID deviation vs BassTilt scale, per capture and level.
  Probe 2 `refit`   -- per-setting driven-only optimal scale -> implied BassTilt gain table, with
                       the cost to the clean sweep stated explicitly.
  Probe 3 `w8guard` -- the 20 Hz edge. A 250 Hz low shelf is essentially FLAT across 20-64 Hz, so
                       it moves SUB and LF together and barely touches the 20->200 Hz CONTOUR that
                       W8 corrected. This probe verifies that rather than assuming it, scoring
                       W8's own contour metric (rise from 20 Hz to the 20-400 Hz max) at each
                       scale. **W8's fix must not regress -- that is a hard constraint here.**

RENDERS: needs build/OfflineRender_artefacts/Release/OfflineRender. 16 captures x 5 scales = 80
renders, a few minutes.

Usage (from the repo root):
    analysis/.venv/bin/python3 analysis/w9_lf_levelbias.py [--only sweep,refit,w8guard]
    analysis/.venv/bin/python3 analysis/w9_lf_levelbias.py --scales 0,0.25,0.5,0.75,1.0

Sign convention throughout: dev = plugin - pedal, 1 kHz-normalised. POSITIVE = plugin hotter.
The BassTilt table's sign is the CORRECTION APPLIED, i.e. the negative of the deviation -- see
BassTilt.h, and do not re-derive it.
"""
import argparse
import os
import subprocess
import sys

import numpy as np

os.environ.setdefault("SIGNAL", "v2")  # pedal2 is a v2-layout capture set (W2 harness note)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A  # noqa: E402
import captures as C  # noqa: E402

LEVELS = ["sweep_clean", "sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6"]
# The levels the shipped table is FITTED against (--objective overrides). -18/-12 dBFS is ~151/301 mV
# at kInputRef, i.e. soft picking to a typical single coil -- the centre of normal playing, and the
# user's stated target (2026-07-27). -6 dBFS is hard-strummed humbucker: it is scored and reported
# but does not set the fit, and in practice it improves alongside rather than being traded away.
OBJECTIVE = ["sweep_drv_-18", "sweep_drv_-12"]
DRIVEN = LEVELS[1:]
NORM_HZ = 1015.9          # midband anchor, independently calibrated to +-0.35 dB
SUB_HZ = [20.0, 25.2, 31.7]                                  # W8's turf
LF_HZ = [40.0, 50.4, 63.5, 80.0, 100.8, 127.0, 160.0]        # where BassTilt acts
MID_HZ = [201.6, 254.0, 320.0, 403.2, 508.0, 640.0, 806.3]   # must stay untouched
CONTOUR_HZ = [20.0, 25.2, 31.7, 40.0, 50.4, 63.5, 80.0, 100.8, 127.0,
              160.0, 201.6, 254.0, 320.0, 403.2]             # W8's 20-400 Hz contour window
SCALES = [0.0, 0.25, 0.5, 0.75, 1.0]
SHIPPED = 1.0
IN_F32 = "/tmp/w9_lf_in.f32"
OUT_F32 = "/tmp/w9_lf_out.f32"


def xargs(bass_tilt_scale):
    """OfflineRender argv[10..25] with only the BassTilt strength overridden.

    bassTiltScale is argv[25], so this list MUST be 16 long -- a short list silently lands the
    value in an earlier slot and makes the whole sweep a no-op with identical columns (the exact
    bug w4_knmedium.py records costing a full render pass). The assert is the guard.
    """
    a = ["1.2", "-1", "1.43", "-1", "1.43", "-1", "0", "-1", "1", "9",
         "-1", "-1", "-1", "1", "-1", f"{bass_tilt_scale:.6f}"]
    assert len(a) == 16, f"argv[10..25] must be 16 entries, got {len(a)}"
    return a


def features(sig, orig):
    """{level: {'sub','lf','mid','contour'}} -- 1 kHz-normalised dB, per window."""
    out = {}
    for lv in LEVELS:
        f, m = A.transfer(A.seg_of(sig, lv), A.seg_of(orig, lv))
        ref = A.gain_at(f, m, NORM_HZ)
        g = lambda hz: A.gain_at(f, m, hz) - ref  # noqa: E731
        curve = [g(hz) for hz in CONTOUR_HZ]
        out[lv] = {
            "sub": float(np.mean([g(hz) for hz in SUB_HZ])),
            "lf": float(np.mean([g(hz) for hz in LF_HZ])),
            "mid": float(np.mean([g(hz) for hz in MID_HZ])),
            # W8's SHAPE metric: how much the curve RISES from 20 Hz to its 20-400 Hz peak.
            "contour": float(max(curve) - curve[0]),
        }
    return out


def label(q):
    return f"{q['rev']:<6} D{q['drive']:.2f} B{q['bass']:.2f}"


def render_all(caps, orig, scales):
    """{(capture_id, scale): features}, plus {capture_id: pedal features}."""
    ped, plug = {}, {}
    for p, q in caps:
        ped[q["id"]] = features(A.align(A.load(p), orig)[0], orig)
    for i, (_, q) in enumerate(caps):
        for s in scales:
            r = subprocess.run([C.RENDER_BIN, IN_F32, OUT_F32]
                               + C.render_args(q, extra_args=xargs(s)),
                               capture_output=True, text=True)
            if r.returncode != 0:
                print(f"  ! render failed {label(q)} scale={s}: {r.stderr.strip()[:200]}")
                continue
            x, _ = A.align(np.fromfile(OUT_F32, dtype=np.float32).astype(np.float64), orig)
            plug[(q["id"], s)] = features(x, orig)
        print(f"  rendered {i + 1}/{len(caps)}  {label(q)}", flush=True)
    return ped, plug


def dev(plug, ped, cid, s, lv, win):
    if (cid, s) not in plug:
        return float("nan")
    return plug[(cid, s)][lv][win] - ped[cid][lv][win]


# --------------------------------------------------------------------------------------------
def probe_sweep(caps, ped, plug, scales):
    print("\n" + "=" * 100)
    print("PROBE 1 `sweep` -- deviation (plugin - pedal, 1 kHz-normalised) vs BassTilt scale")
    print("=" * 100)
    for win, name in (("lf", "LF 40-160 Hz"), ("mid", "MID 202-806 Hz"), ("sub", "SUB 20-32 Hz")):
        print(f"\n--- {name} ---")
        print(f"  {'capture':<22}{'level':>9} | " + "".join(f"{f's={s:g}':>9}" for s in scales))
        print("  " + "-" * (31 + 9 * len(scales)))
        for _, q in caps:
            for lv in LEVELS:
                row = [dev(plug, ped, q["id"], s, lv, win) for s in scales]
                print(f"  {label(q):<22}{lv.replace('sweep_', ''):>9} | "
                      + "".join(f"{v:+9.2f}" for v in row))
            print()
        if win == "mid":
            allv = [abs(dev(plug, ped, q["id"], s, lv, "mid"))
                    for _, q in caps for lv in LEVELS for s in scales]
            print(f"  MID is insensitive to this shelf and already small: max |dev| over the whole")
            print(f"  sweep = {np.nanmax(allv):.2f} dB. The apparent 200 Hz-2 kHz deficit in the")
            print(f"  dashboard's `raw` view is the null-gain offset, not a midband error.\n")


def probe_refit(caps, ped, plug, scales, objective):
    print("\n" + "=" * 100)
    print(f"PROBE 2 `refit` -- per-setting optimum scored on {', '.join(objective)}")
    print("=" * 100)
    print("\n  LF deviation is near-linear in BassTilt scale, so for each capture we least-squares")
    print("  fit dev(s) = a + b*s per level and solve for the scale that zeroes it.\n")
    print(f"  {'capture':<22}{'shipped LF':>11}{'  |':>3}{'best s':>8}{'refit LF':>10}"
          f"{'clean was':>11}{'clean then':>11}")
    print("  " + "-" * 78)

    tbl, s_arr = [], np.array(scales, dtype=float)
    for _, q in caps:
        cid = q["id"]
        d_driven = np.array([np.mean([dev(plug, ped, cid, s, lv, "lf") for lv in objective])
                             for s in scales])
        d_clean = np.array([dev(plug, ped, cid, s, "sweep_clean", "lf") for s in scales])
        if np.any(np.isnan(d_driven)) or np.any(np.isnan(d_clean)):
            print(f"  {label(q):<22}  incomplete renders -- skipped")
            continue
        b, a = np.polyfit(s_arr, d_driven, 1)
        s_opt = float(-a / b) if abs(b) > 1e-9 else float("nan")
        bc, ac = np.polyfit(s_arr, d_clean, 1)
        shipped_lf = float(a + b * SHIPPED)
        clean_now = float(ac + bc * SHIPPED)
        clean_then = float(ac + bc * s_opt)
        tbl.append((q, s_opt, shipped_lf, clean_now, clean_then))
        print(f"  {label(q):<22}{shipped_lf:+11.2f}{'  |':>3}{s_opt:8.2f}{0.0:+10.2f}"
              f"{clean_now:+11.2f}{clean_then:+11.2f}")

    print("\n  --- implied BassTilt gain table (dB at 250 Hz) if the clean sweep loses its vote ---")
    print("  Shipped values are BassTilt.h's kGainSoft/Medium/Hard; refit = shipped * best s.")
    print(f"\n  {'capture':<22}{'shipped':>9}{'refit':>9}{'delta':>9}")
    print("  " + "-" * 49)
    # Must mirror BassTilt.h's kGainSoft/kGainMedium/kGainHard. These are the POST-W9 values, so a
    # re-run of this probe reports the residual ON TOP of the shipped table, and "best s" is now
    # expected to sit near 1.0 rather than near 0.2.
    ship = {"Soft": {0.20: +0.30, 0.35: +0.30, 0.50: +0.04, 0.65: +0.06, 0.80: +0.07, 1.00: +0.14},
            "Medium": {0.20: +0.26, 0.35: +0.26, 0.50: -0.02, 0.65: -0.79, 0.80: -0.25, 1.00: -0.24},
            "Hard": {0.20: +0.71, 0.35: +0.14, 0.50: -0.06, 0.65: -0.26, 0.80: -0.23, 1.00: -0.24}}
    for q, s_opt, _, _, _ in tbl:
        g0 = ship[q["rev"]][round(q["drive"], 2)]
        print(f"  {label(q):<22}{g0:+9.2f}{g0 * s_opt:+9.2f}{g0 * (s_opt - 1.0):+9.2f}")

    print("\n  --- aggregate: mean |LF dev| by scoring set ---")
    for s in scales:
        ob = [abs(dev(plug, ped, q["id"], s, lv, "lf")) for _, q in caps for lv in objective]
        dv = [abs(dev(plug, ped, q["id"], s, lv, "lf")) for _, q in caps for lv in DRIVEN]
        cl = [abs(dev(plug, ped, q["id"], s, "sweep_clean", "lf")) for _, q in caps]
        tag = "  <- shipped" if s == SHIPPED else ("  <- BassTilt OFF" if s == 0.0 else "")
        print(f"    scale {s:4.2f}: objective {np.nanmean(ob):.3f}   all-driven {np.nanmean(dv):.3f}"
              f"   clean {np.nanmean(cl):.3f}   all-4 {np.nanmean(dv + cl):.3f}{tag}")


def probe_w8guard(caps, ped, plug, scales):
    print("\n" + "=" * 100)
    print("PROBE 3 `w8guard` -- does changing BassTilt disturb W8's 20 Hz contour fix?")
    print("=" * 100)
    print("\n  W8's metric: LF RISE = (max deviation over 20-400 Hz) - (deviation at 20 Hz), per")
    print("  side. Here we report the plugin-pedal MISMATCH in that rise -- 0 = same contour.")
    print("  A 250 Hz low shelf is ~flat across 20-64 Hz, so it should move SUB and LF together")
    print("  and leave this nearly untouched. Verify, do not assume.\n")
    print(f"  {'level':>9} | " + "".join(f"{f's={s:g}':>9}" for s in scales))
    print("  " + "-" * (12 + 9 * len(scales)))
    for lv in LEVELS:
        row = []
        for s in scales:
            v = [abs(dev(plug, ped, q["id"], s, lv, "contour")) for _, q in caps]
            row.append(np.nanmean(v))
        print(f"  {lv.replace('sweep_', ''):>9} | " + "".join(f"{v:9.3f}" for v in row))
    print("\n  mean |contour mismatch| over all captures and levels:")
    for s in scales:
        v = [abs(dev(plug, ped, q["id"], s, lv, "contour")) for _, q in caps for lv in LEVELS]
        tag = "  <- shipped" if s == SHIPPED else ("  <- BassTilt OFF" if s == 0.0 else "")
        print(f"    scale {s:4.2f}: {np.nanmean(v):.3f} dB{tag}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="sweep,refit,w8guard")
    ap.add_argument("--scales", default=",".join(f"{s:g}" for s in SCALES))
    ap.add_argument("--objective", default=",".join(OBJECTIVE),
                    help="sweep levels the refit targets (default: the shipped -18/-12)")
    args = ap.parse_args()
    want = {s.strip() for s in args.only.split(",") if s.strip()}
    scales = [float(s) for s in args.scales.split(",")]
    objective = [s.strip() for s in args.objective.split(",") if s.strip()]

    if not os.path.exists(C.RENDER_BIN):
        sys.exit(f"missing {C.RENDER_BIN} -- build OfflineRender first")
    orig = A.load(A.ORIG)
    orig.astype(np.float32).tofile(IN_F32)

    caps = C.find_captures()
    if not caps:
        sys.exit("no captures found in analysis/pedal2")
    for p, q in caps:
        q.setdefault("id", label(q))
    print(f"\n{len(caps)} captures x {len(scales)} BassTilt scales "
          f"= {len(caps) * len(scales)} renders (shipped scale = {SHIPPED})\n")
    ped, plug = render_all(caps, orig, scales)

    if "sweep" in want:
        probe_sweep(caps, ped, plug, scales)
    if "refit" in want:
        probe_refit(caps, ped, plug, scales, objective)
    if "w8guard" in want:
        probe_w8guard(caps, ped, plug, scales)
    print()


if __name__ == "__main__":
    main()
