#!/usr/bin/env python3
"""Audit analysis/reports/comprehensive_data.json against Tommy's FR/THD acceptance targets, and
GENERATE analysis/reports/executive_summary.txt (`--write`).

Imported from the Guitar-Pedal-Plugin-Template analysis harness and adapted for Tommy. Answers,
without re-rendering anything:
  1. FR: how far are we from "within 1.5 dB (3 dB at extremes), 20 Hz - 18 kHz", per SW1 clip mode,
     and how much of the miss lives in bands below 40 Hz (the sweep's least-supported region)?
  2. THD: which bands actually HAVE data (Farina ceiling / discrete-tone coverage)?
  3. THD vs LEVEL: is the error clip-onset (level-dependent) or static (wrong fault type)?
  4. Harmonics: are the individual harmonic MAGNITUDES right, not just THD (their rss)?

Run from repo root:  analysis/.venv/bin/python3 analysis/report_audit.py [--write]
"""
import argparse
import json
import sys

import numpy as np

JSON_PATH = "analysis/reports/comprehensive_data.json"
OUT_PATH = "analysis/reports/executive_summary.txt"

# The sweep starts at 20 Hz, so the bottom bins are the least-supported points of the excitation.
# Never anchor there. 18 kHz is the practical top of guitar-pedal interest.
TRUST_LO, TRUST_HI = 40.0, 18000.0
EXTREME_LO, EXTREME_HI = 60.0, 12000.0  # inside this = "within 1.5 dB"; outside = "within 3 dB"

# Tommy's circuit (circuit.md) has no twin-T/bridged-T notch filter, so none of the THD_ANCHORS
# (110/220/440 Hz — see comprehensive_report.py) sit on a notch that would inflate their ratios by
# attenuating the fundamental every harmonic ratio divides by. Add a frequency here if a future
# anchor ever does coincide with one.
CONFOUNDED_ANCHORS = ()

# Absolute floor for the harmonic audit (dBc, relative to the fundamental). A harmonic sitting at
# -50..-62 dBc is at the CAPTURE NOISE FLOOR, so the plugin-vs-pedal dB *ratio* there is comparing
# noise to noise and is meaningless — yet it enters a median-of-|delta| with the same weight as a
# real -30 dBc harmonic. Symmetric clippers (Soft/Medium) have no even harmonics in either the
# pedal or the plugin, so their H2/H4/H6 are exactly this case, and their +12..+25 dB "errors"
# used to dominate the per-mode score (Soft 1.64 -> 0.40 dB, Medium 3.24 -> 0.51 dB at -18 dBFS
# once floored; Hard barely moves, 0.95 -> 0.90, because its asymmetry puts H2 genuinely high).
# A point is dropped if EITHER side is below the floor — one noisy side is enough to ruin a ratio.
# See .claude/plans/v1.4-fidelity.md §2.4 / W5.
HARM_FLOOR_DBC = -45.0

# FR deltas in the JSON already carry a null-optimal broadband gain (`gain_db_applied`, a
# least-squares fit over the whole band). That is NOT a 1 kHz match: a genuine narrow error (Tommy's
# LF excess below ~100 Hz) drags the fitted gain down and reappears as a phantom broadband deficit
# across the midband. Normalising at 1 kHz instead removes the arbitrary level convention and shows
# the honest SHAPE. Both views are reported — see .claude/plans/v1.4-fidelity.md §1.1 / W5.
NORM_HZ = 1000.0

_sink = []


def out(msg=""):
    print(msg)
    _sink.append(msg)


def load():
    with open(JSON_PATH) as f:
        return json.load(f)


def shape(plugin, pedal):
    """Level-independent delta: median offset removed (isolates tone SHAPE from a flat level
    offset — same convention as knob_tracking.py's SHAPE metric)."""
    p = np.array(plugin, dtype=float)
    c = np.array(pedal, dtype=float)
    d = p - c
    return d - np.median(d)


def fr_norm_audit(d):
    """The two level-match conventions side by side, per band, per sweep level.

    Column 'raw' is `plugin_db - pedal_db` straight from the JSON (null-optimal broadband gain
    already applied). Column '@1k' re-references each capture's delta to its own value at the
    1 kHz band. Where the two disagree, the raw column is reporting the level-match convention,
    not a tone error."""
    bands = np.array(d["meta"]["bands"], dtype=float)
    j1k = int(np.argmin(np.abs(bands - NORM_HZ)))
    levels = ["sweep_clean"] + list(d["meta"]["driven_sweeps"])
    out()
    out("=" * 78)
    out(f"1b. FR LEVEL-MATCH CONVENTION — raw (null-gain-matched) vs normalised at "
        f"{bands[j1k]:.0f} Hz")
    out(f"    median over all {len(d['captures'])} captures, dB (plugin - pedal)")
    out("=" * 78)
    hdr = "".join(f"{lv.replace('sweep_', ''):>16}" for lv in levels)
    out(f"{'band':>9}" + hdr)
    out(f"{'':>9}" + "".join(f"{'raw    @1k':>16}" for _ in levels))
    raws, norms = {}, {}
    for lv in levels:
        r = np.array([np.array(c["fr"][lv]["plugin_db"], dtype=float)
                      - np.array(c["fr"][lv]["pedal_db"], dtype=float)
                      for c in d["captures"] if lv in c["fr"]])
        raws[lv] = np.median(r, axis=0)
        norms[lv] = np.median(r - r[:, [j1k]], axis=0)
    for j, b in enumerate(bands):
        row = f"{b:>9.0f}"
        for lv in levels:
            row += f"{raws[lv][j]:>+9.2f}{norms[lv][j]:>+7.2f}"
        out(row)
    out()
    mid = (bands >= 200.0) & (bands <= 5000.0)
    worst = max(float(np.max(np.abs(norms[lv][mid]))) for lv in levels)
    out(f"  Normalised, the worst 200 Hz-5 kHz band across all levels is {worst:.2f} dB — the")
    out("  midband is CLEAN. Any broad deficit in the 'raw' column across that span is the")
    out("  least-squares gain being dragged by the LF excess, not a midband tone error.")
    out("  Read the raw column for absolute level, the @1k column for tone shape.")


def fr_audit(d):
    bands = np.array(d["meta"]["bands"], dtype=float)
    trust_all = (bands >= TRUST_LO) & (bands <= TRUST_HI)
    n_trust = int(np.sum(trust_all))
    out("=" * 78)
    out("1. FR vs TARGET  (shape metric, median offset removed)")
    out("   target: |delta| <= 1.5 dB in 60 Hz-12 kHz, <= 3.0 dB outside, over 20 Hz-18 kHz")
    out("=" * 78)
    out(f"{'capture':<28}{'rmsFULL':>8}{'rmsTRUST':>9}{'n>1.5':>7}{'n>3':>6}{'worst band':>22}")
    per_rev = {}
    for c in d["captures"]:
        fr = c["fr"]["sweep_clean"]
        dlt = shape(fr["plugin_db"], fr["pedal_db"])
        rms_full = float(np.sqrt(np.mean(dlt**2)))
        rms_trust = float(np.sqrt(np.mean(dlt[trust_all] ** 2)))
        # tolerance per band
        tol = np.where((bands >= EXTREME_LO) & (bands <= EXTREME_HI), 1.5, 3.0)
        fail15 = int(np.sum((np.abs(dlt) > tol) & trust_all))
        fail3 = int(np.sum((np.abs(dlt) > 3.0) & trust_all))
        i = int(np.argmax(np.abs(np.where(trust_all, dlt, 0))))
        out(
            f"{c['id']:<28}{rms_full:>8.2f}{rms_trust:>9.2f}{fail15:>7}{fail3:>6}"
            f"{f'{bands[i]:.0f}Hz {dlt[i]:+.1f}dB':>22}"
        )
        per_rev.setdefault(c["rev"], []).append((rms_full, rms_trust, fail15))
    out()
    out(f"{'mode':<8}{'med rmsFULL':>12}{'med rmsTRUST':>13}{'med n>tol':>11}  (of {n_trust} trusted bands)")
    for rev, rows in per_rev.items():
        a = np.array(rows, dtype=float)
        out(f"{rev:<8}{np.median(a[:,0]):>12.2f}{np.median(a[:,1]):>13.2f}{np.median(a[:,2]):>11.0f}")

    # where does the error live?
    out()
    out(f"FR shape error by band, median |delta| across all {len(d['captures'])} captures:")
    out(f"{'band':>9}{'med|d|':>9}{'max|d|':>9}   {'trusted?':<9}")
    allshape = np.array([shape(c["fr"]["sweep_clean"]["plugin_db"], c["fr"]["sweep_clean"]["pedal_db"]) for c in d["captures"]])
    for j, b in enumerate(bands):
        med = float(np.median(np.abs(allshape[:, j])))
        mx = float(np.max(np.abs(allshape[:, j])))
        if med > 1.5 or mx > 6.0:
            flag = "" if TRUST_LO <= b <= TRUST_HI else "  <- untrusted (below 40 Hz)"
            out(f"{b:>9.0f}{med:>9.2f}{mx:>9.2f}{flag}")


def thd_coverage(d):
    bands = d["meta"]["bands"]
    src = d["meta"]["thd_band_sources"]
    out()
    out("=" * 78)
    out("2. THD COVERAGE — can we even measure 'THD 20 Hz-18 kHz'?")
    out("=" * 78)
    n_far = sum(1 for s in src if s == "farina")
    n_dis = sum(1 for s in src if s == "discrete")
    na = [b for b, s in zip(bands, src) if s == "na"]
    far_hi = max((b for b, s in zip(bands, src) if s == "farina"), default=0.0)
    f1 = d["meta"].get("sweep_f1_hz")
    orders = d["meta"].get("thd_band_orders")
    out(f"  farina  : {n_far:2d} bands (20 Hz - {far_hi:.0f} Hz)")
    if n_dis:
        out(f"  discrete: {n_dis:2d} bands ({', '.join(f'{b:.0f}' for b,s in zip(bands,src) if s=='discrete')} Hz)")
    out(f"  NO DATA : {len(na):2d} bands -> {', '.join(f'{b:.0f}' for b in na) if na else '(none)'}")
    out()
    if f1:
        out(f"  Farina sees order N only while N*f <= SWEEP_F1 ({f1:.0f} Hz) — past that the")
        out(f"  deconvolution divides by a band with no energy and order N spikes at exactly")
        out(f"  SWEEP_F1/N (see analyze.harmonic_thd_curve). So THD needs H2 => the honest ceiling")
        out(f"  is {f1*0.95/2:.0f} Hz.")
        out()
        out("  ABOVE THAT IT IS NOT A TOOLING GAP:")
        out(f"    {f1*0.95/2:.0f}-12000 Hz : needs a NEW test signal sweeping to 24 kHz => re-capture the pedal")
        out("    >12000 Hz      : THD does not exist at 48 kHz (H2 lands past Nyquist)")
    if orders:
        out()
        out("  Measurable order count per band (falls with frequency — an absolute THD built from")
        out("  1 order is NOT comparable to one built from 6; a plugin-vs-pedal DELTA still is):")
        row = [f"{b:.0f}:{n}" for b, n in zip(bands, orders) if b >= 2000.0]
        for k in range(0, len(row), 8):
            out("    " + "  ".join(row[k:k + 8]))


def thd_vs_level(d):
    bands = np.array(d["meta"]["bands"], dtype=float)
    sweeps = d["meta"]["driven_sweeps"]
    out()
    out("=" * 78)
    out("3. THD vs LEVEL @ 101 Hz — is the error clip-ONSET (level-dep) or static (level-flat)?")
    out("=" * 78)
    j = int(np.argmin(np.abs(bands - 101.0)))
    out(f"{'capture':<28}" + "".join(f"{s.replace('sweep_drv_',''):>20}" for s in sweeps))
    out(f"{'':<28}" + "".join(f"{'pedal / plugin':>20}" for s in sweeps))
    for c in d["captures"]:
        row = f"{c['id']:<28}"
        for s in sweeps:
            t = c["thd"][s]
            pc, pl = t["pedal_pct"][j], t["plugin_pct"][j]
            row += f"{f'{pc:5.1f} / {pl:5.1f}':>20}" if pc is not None else f"{'-':>20}"
        out(row)
    out()
    out("  Read: pedal THD should RISE with level (clip onset). A plugin column that barely")
    out("  moves is a static/level-independent nonlinearity in the wrong place.")


def harmonic_audit(d):
    anchors = d["meta"]["thd_anchors"]
    orders = d["meta"]["harmonic_orders"]
    out()
    out("=" * 78)
    out("4. HARMONIC MAGNITUDES (not just THD) — delta = plugin - pedal, dB, sweep_drv_-18")
    out("=" * 78)
    keep = [i for i, a in enumerate(anchors) if a not in CONFOUNDED_ANCHORS]
    if len(keep) < len(anchors):
        out("  anchors marked (*) are NOTCH-CONFOUNDED: they attenuate the FUNDAMENTAL that every")
        out("  ratio divides by, so they are shown but EXCLUDED from the medians below.")
    else:
        out("  none of these anchors sit on a known notch in Tommy's circuit, so every column")
        out("  below is included in the medians.")
    out()
    out(f"  Points where EITHER pedal or plugin sits below {HARM_FLOOR_DBC:.0f} dBc are at the capture")
    out("  noise floor and are EXCLUDED from the medians (shown as '.' in the delta columns).")
    out()
    hdr = "".join(f"{str(a) + ('*' if a in CONFOUNDED_ANCHORS else ''):>8}" for a in anchors)
    out(f"{'capture':<24}{'order':>6}" + hdr + f"{'  med|d|':>9}")
    rev_acc = {}
    n_excl = n_tot = 0
    for c in d["captures"]:
        h = c["harmonics"]["sweep_drv_-18"]
        for o in orders:
            key = f"H{o}"
            pl = np.array(h[key]["plugin_db"], dtype=float)
            pc = np.array(h[key]["pedal_db"], dtype=float)
            dlt = pl - pc
            above = (pl >= HARM_FLOOR_DBC) & (pc >= HARM_FLOOR_DBC)
            use = [i for i in keep if above[i]]   # confounded anchors AND floor noise excluded
            n_tot += len(keep)
            n_excl += len(keep) - len(use)
            med = float(np.median(np.abs(dlt[use]))) if use else float("nan")
            if use:
                rev_acc.setdefault(c["rev"], []).append(med)
            if o <= 3:  # keep the printout readable: H2/H3 carry the character
                cells = "".join(f"{x:>+8.1f}" if above[i] else f"{'.':>8}" for i, x in enumerate(dlt))
                medtxt = f"{med:>9.1f}" if use else f"{'-':>9}"
                out(f"{c['id']:<24}{key:>6}" + cells + medtxt)
    out()
    out(f"  excluded {n_excl} of {n_tot} (capture x order x anchor) points as below-floor "
        f"({100.0 * n_excl / n_tot:.0f}%).")
    out()
    out(f"{'mode':<8}{'median |H-delta| over H2..H7, clean anchors, above floor':<58}")
    for rev, vals in rev_acc.items():
        out(f"{rev:<8}{np.median(vals):>8.1f} dB")
    out()
    out("  A correct THD with wrong per-harmonic magnitudes = right total energy, wrong timbre —")
    out("  THD is the rss of these, so it can be right while every term in it is wrong. This is")
    out("  the 'harmonic volume, not just placement' check.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", nargs="?", const=OUT_PATH, default=None,
                    help=f"also write the summary to a file (default {OUT_PATH})")
    a = ap.parse_args()

    try:
        d = load()
    except FileNotFoundError:
        sys.exit(f"{JSON_PATH} not found — run: analysis/.venv/bin/python3 analysis/comprehensive_report.py")

    out("TOMMY — COMPREHENSIVE EXECUTIVE SUMMARY")
    out("=" * 78)
    out(f"source: {JSON_PATH}  generated {d['meta']['generated']}  OS={d['meta']['os_factor']}x")
    out(f"captures: {d['meta']['num_captures']}  bands: {d['meta']['num_bands']}")
    out("generator: analysis/report_audit.py --write   (do NOT hand-edit; do NOT regenerate inline)")
    out()
    fr_audit(d)
    fr_norm_audit(d)
    thd_coverage(d)
    thd_vs_level(d)
    harmonic_audit(d)

    if a.write:
        with open(a.write, "w") as f:
            f.write("\n".join(_sink) + "\n")
        print(f"\nwrote {a.write}")


if __name__ == "__main__":
    main()
