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


def render_plugin(p, kin=""):
    orig = A.load(A.ORIG)
    orig.astype(np.float32).tofile("/tmp/knob_orig.f32")
    args = [REND, "/tmp/knob_orig.f32", "/tmp/knob_plug.f32",
            f"{p['B']:.4f}", f"{p['G']:.4f}", f"{p['T']:.4f}", f"{p['V']:.4f}",
            str(p["mode"]), str(OSLOG2), "48000"]
    if kin:
        args.append(kin)
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    orig2 = A.load(A.ORIG)
    x, _ = A.align(np.fromfile("/tmp/knob_plug.f32", dtype=np.float32).astype(np.float64), orig2)
    return x


def check_one(nam, plug, orig):
    """Return (shape_max_dev_dB, level_dev_dB, thd_max_dev_pct) for one aligned real/plug pair."""
    inp = A.seg_of(orig, "sweep_clean")
    fN, mN = A.transfer(A.seg_of(nam, "sweep_clean"), inp)
    fP, mP = A.transfer(A.seg_of(plug, "sweep_clean"), inp)
    # SHAPE: subtract each curve's own 1 kHz gain first, so only the tone-stack *shape* is compared.
    rN0, rP0 = A.gain_at(fN, mN, 1000), A.gain_at(fP, mP, 1000)
    shape_dev = max(abs((A.gain_at(fN, mN, f) - rN0) - (A.gain_at(fP, mP, f) - rP0))
                    for f in SHAPE_FREQS)
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
    print("  " + "-" * 78)
    print(f"  SHAPE (tone-stack tracking): {n_shape_ok}/{n_total} pass")
    print(f"  LEVEL (absolute level):      {n_level_ok}/{n_total} pass   "
          f"<- the known headroom issue if low")


if __name__ == "__main__":
    main()
