#!/usr/bin/env python3
"""Formalized pass/fail check: do all the knobs react and sound like the real pedal?

Rather than try to isolate one-knob-at-a-time monotonicity from the confounded capture sets (every
batch varies several knobs at once, and Volume never varies at all — see CLAUDE.md), this asserts
the stronger, simpler property: at EVERY captured setting, does the plugin match the real pedal?
If the plugin tracks the real pedal across the whole captured operating space, the knobs track by
construction.

It separates two independent questions, because the project's known open issue is level, not tone:
  * SHAPE  — does the tone stack track? EQ compared RELATIVE to 1 kHz (the broadband level offset
             removed), so a pure level error doesn't masquerade as a tone error. This is the real
             "do Bass/Treble/Drive/clip-switch sound right" test.
  * LEVEL  — absolute output level vs the real pedal at 1 kHz. This currently FAILS (the plugin is
             ~6-12 dB quiet, growing with drive) — that's the headroom issue tracked separately.
  * THD    — distortion amount per the discrete tones (clipping character).

Thresholds (defaults, easy to tune at the top of the file):
  SHAPE_TOL_DB = 1.5    max |plug-real| EQ deviation (relative to 1 kHz) over 60 Hz..8 kHz
  THD_TOL_ABS  = 3.0    THD agreement: within this many % absolute ...
  THD_TOL_REL  = 0.5    ... or within this fraction, whichever is looser
  LEVEL_TOL_DB = 2.0    absolute-level agreement at 1 kHz (currently expected to FAIL)

Usage:
  python3 analysis/knob_tracking.py analysis/pedal_results3 analysis/pedal_results4
  KIN=2.4 python3 analysis/knob_tracking.py analysis/pedal_results5
"""
import os, sys, glob, subprocess, numpy as np
import analyze as A

REND = "build/OfflineRender_artefacts/Release/OfflineRender"
OSLOG2 = 3

SHAPE_TOL_DB = 1.5
THD_TOL_ABS = 3.0
THD_TOL_REL = 0.5
LEVEL_TOL_DB = 2.0

SHAPE_FREQS = [60, 120, 250, 500, 1000, 2000, 4000, 8000]   # band over which tone-shape must track
THD_FREQS = [110, 440, 1000, 2000]
# Sweeps the optional SHAPE_LEVELS=1 breakdown reports on (v2 layout only; v1 has no driven set).
SHAPE_SWEEPS = ["sweep_clean", "sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6"]


def render_plugin(p, kin=""):
    orig = A.load(A.ORIG)
    orig.astype(np.float32).tofile("/tmp/knob_orig.f32")
    args = [REND, "/tmp/knob_orig.f32", "/tmp/knob_plug.f32",
            f"{p['B']:.4f}", f"{p['G']:.4f}", f"{p['T']:.4f}", f"{p['V']:.4f}",
            str(p["mode"]), str(OSLOG2), "48000"]
    if kin:
        args.append(kin)
    # CALIBRATION ONLY (v1.4 W9) — BASSTILT=<scale> re-runs the gate with BassTilt's fitted table
    # scaled (1.0 = shipped, 0.0 = disabled), so the SHAPE cost of re-weighting that fit can be
    # MEASURED rather than predicted. bassTiltScale is offline_render's argv[25], so setting it
    # means filling argv[10..25]; every other slot here is its shipped default. Unset = untouched.
    bt = os.environ.get("BASSTILT", "")
    if bt:
        if kin:
            args.pop()  # KIN is argv[10]; it is re-supplied as the first slot of the full block
        args += [kin or "1.2", "-1", "1.43", "-1", "1.43", "-1", "0", "-1", "1", "9",
                 "-1", "-1", "-1", "1", "-1", f"{float(bt):.6f}"]
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    orig2 = A.load(A.ORIG)
    x, _ = A.align(np.fromfile("/tmp/knob_plug.f32", dtype=np.float32).astype(np.float64), orig2)
    return x


def shape_dev_on(nam, plug, orig, sweep):
    """SHAPE deviation measured on one named sweep segment (1 kHz-normalised, both sides)."""
    inp = A.seg_of(orig, sweep)
    fN, mN = A.transfer(A.seg_of(nam, sweep), inp)
    fP, mP = A.transfer(A.seg_of(plug, sweep), inp)
    rN0, rP0 = A.gain_at(fN, mN, 1000), A.gain_at(fP, mP, 1000)
    return max(abs((A.gain_at(fN, mN, f) - rN0) - (A.gain_at(fP, mP, f) - rP0))
               for f in SHAPE_FREQS)


def check_one(nam, plug, orig):
    """Return (shape_max_dev_dB, level_dev_dB, thd_max_dev_pct) for one aligned real/plug pair."""
    # SHAPE: subtract each curve's own 1 kHz gain first, so only the tone-stack *shape* is compared.
    #
    # NOTE (v1.4 W4 lever 4, 2026-07-27) — this is scored on `sweep_clean` ALONE, and that choice is
    # load-bearing, not incidental. `sweep_clean` is -30 dBFS but Stage 1's midband gain is 25-44 dB
    # at these settings, so its own 1 kHz normalisation anchor is past the diode clamp at D >= 0.50.
    # Measured consequence (analysis/w4_bassdrive.py --only metric): scored here SHAPE is 12/16;
    # scored on sweep_drv_-18 it is 16/16, on -12 14/16, on -6 8/16 — and *0/16 captures fail at
    # every level*, i.e. every failure in the set is level-specific. Clean-only inflation is
    # +0.47 dB median / +1.64 dB max. The worst band also migrates with level: the clean-sweep
    # failures are LF (64/127 Hz) while the -6 dBFS ones are at 8128 Hz (that is W3's top-octave
    # deficit, not a bass error). The gate is deliberately LEFT on sweep_clean for continuity with
    # every recorded count in CLAUDE.md; the per-level breakdown below exists so a clean-sweep
    # artefact is never again diagnosed as a tone bug. See CLAUDE.md's W4 entry.
    shape_dev = shape_dev_on(nam, plug, orig, "sweep_clean")
    # LEVEL: absolute output at 1 kHz, -12 dBFS input step.
    level_dev = A.rms_db(A.seg_of(plug, "lvl-12")) - A.rms_db(A.seg_of(nam, "lvl-12"))
    # THD: worst per-tone deviation.
    thd_dev = 0.0
    for f in THD_FREQS:
        r = A.thd(A.seg_of(nam, f"f{f}"), f)[0]
        pl = A.thd(A.seg_of(plug, f"f{f}"), f)[0]
        if abs(pl - r) > THD_TOL_ABS and abs(pl - r) > THD_TOL_REL * max(r, 1.0):
            thd_dev = max(thd_dev, abs(pl - r))
    return shape_dev, level_dev, thd_dev


def main():
    namdirs = [a for a in sys.argv[1:] if not a.startswith("-")] or ["analysis/pedal_results3"]
    kin = os.environ.get("KIN", "")
    orig = A.load(A.ORIG)
    print(f"\nKnob-tracking pass/fail  (kIn={kin or 'default'})")
    print(f"  thresholds: shape +/-{SHAPE_TOL_DB} dB | level +/-{LEVEL_TOL_DB} dB | "
          f"thd +/-{THD_TOL_ABS}% or {THD_TOL_REL:.0%}")
    print(f"  {'setting':40s} shapeDev levelDev thdDev   SHAPE LEVEL THD")
    print("  " + "-" * 78)
    n_shape_ok = n_level_ok = n_total = 0
    per_level = {}   # sweep -> [shapeDev, ...]; only populated when SHAPE_LEVELS is set
    extra = [s for s in SHAPE_SWEEPS if s in A.T] if os.environ.get("SHAPE_LEVELS") else []
    for namdir in namdirs:
        for fn in sorted(os.path.basename(x) for x in glob.glob(os.path.join(namdir, "*.wav"))):
            nam_raw = A.load(os.path.join(namdir, fn))
            if not A.is_full_length(nam_raw, orig):
                continue
            p = A.parse_filename(fn)
            nam, _ = A.align(nam_raw, orig)
            plug = render_plugin(p, kin)
            sdev, ldev, tdev = check_one(nam, plug, orig)
            s_ok = sdev <= SHAPE_TOL_DB
            l_ok = abs(ldev) <= LEVEL_TOL_DB
            t_ok = tdev == 0.0
            n_total += 1; n_shape_ok += s_ok; n_level_ok += l_ok
            tag = f"G{p['G']:.2f} {p['sw']:>4} B{p['B']:.2f} T{p['T']:.2f} V{p['V']:.2f}"
            print(f"  {tag:40s} {sdev:>6.2f}  {ldev:>+6.2f}  {tdev:>5.1f}   "
                  f"{'PASS' if s_ok else 'FAIL':>5} {'PASS' if l_ok else 'FAIL':>5} "
                  f"{'PASS' if t_ok else 'FAIL':>4}")
            for sw in extra:
                per_level.setdefault(sw, []).append(shape_dev_on(nam, plug, orig, sw))
    print("  " + "-" * 78)
    print(f"  SHAPE (tone-stack tracking): {n_shape_ok}/{n_total} pass")
    print(f"  LEVEL (absolute level):      {n_level_ok}/{n_total} pass   "
          f"<- the known headroom issue if low")
    if per_level:
        # W4 lever 4: the gate above scores sweep_clean only, whose 1 kHz anchor is past the diode
        # clamp at D >= 0.50. This shows what SHAPE would say on each sweep, so a level-specific
        # artefact can't be mistaken for a tone error. See check_one's note.
        print()
        print("  SHAPE by which sweep it is scored on (gate uses sweep_clean):")
        for sw in extra:
            devs = per_level[sw]
            ok = sum(1 for d in devs if d <= SHAPE_TOL_DB)
            mark = "  <- the shipped gate" if sw == "sweep_clean" else ""
            print(f"    {sw:>15}: {ok}/{len(devs)} pass   "
                  f"median {sorted(devs)[len(devs) // 2]:.2f} dB   worst {max(devs):.2f} dB{mark}")
        n_all = sum(1 for i in range(n_total)
                    if max(per_level[sw][i] for sw in extra) <= SHAPE_TOL_DB)
        print(f"    {'worst-of-all':>15}: {n_all}/{n_total} pass   "
              f"(a capture must track at EVERY level)")


if __name__ == "__main__":
    main()
