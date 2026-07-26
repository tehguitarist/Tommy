#!/usr/bin/env python3
"""v1.4 W2 — low-drive clip onset: characterise, and test the levers that could move it.

Plan item W2 (`.claude/plans/v1.4-fidelity.md` §2.2). At `Hard D0.20 B0.50 T0.20` / -18 dBFS the
plugin distorts ~4.4x as much as the pedal (11.3% vs 2.55% at 101 Hz), collapsing as level rises.
It is the largest single error in the pedal2 dataset and it lives in the edge-of-breakup region.
W4's mode-dependent LF residual folds in here too (see the plan's W4 OUTCOME block): both are
clip threshold/onset accuracy, not EQ.

Two constraints make this delicate and are enforced by every probe below:
  * `D0.20` appears exactly ONCE, Hard only, and no further captures can ever be made (W6 struck).
    So any change must be shown to leave the well-sampled D >= 0.35 behaviour intact — a one-capture
    fit that moves the rest is trading a measured error for an unmeasured one.
  * The lever must not be global `kIs`: halving it is v1.2.1's high-drive LEVEL fix (pedal2 LEVEL
    12/16 -> 16/16) and it pulls the OPPOSITE way here (lower Is = earlier onset).

OUTCOME (2026-07-27): the lever is the DRIVE TAPER, not the diodes. `TaperUtils.h`'s
`driveResistance` exponent 2.2 -> 2.75; see that function's comment for the shipped rationale and
the plan's W2 block for the full result. Reproduce the whole argument with `--only onset,levers,fit`.

Probes, in the order they were run and in the order they should be re-read:

  1. `characterise()` — from the JSON only. THD error vs DRIVE x level x clip mode, so the
     drive-dependence reads as a TREND rather than one outlier. Two results decide everything that
     follows. (i) The error is monotone in DRIVE and MODE-INDEPENDENT in trend — at -18 dBFS,
     D0.35 is Soft +1.0 / Hard +1.4 / Medium +2.8 dB and D >= 0.50 is within +-0.7 — and the
     per-mode ordering follows each mode's overdrive MARGIN (probe 2), not its diode parameters.
     Mode-independence is what rules the diodes out and points at the shared pre-clip gain.
     (ii) Hard's H2 matches within ~1.8 dB at every drive from 0.35 up, so the asymmetry is
     correctly calibrated; its +13.6 dB blow-up at D0.20/-18 is a CONSEQUENCE of the model being
     past onset where the pedal is not (H2 peaks just past onset and decays into deep clipping —
     visible in the pedal's own numbers, which RISE with level at D0.20 and FALL at D0.35+), not an
     independent asymmetry error.

  2. `onset()` — closed-form, and the probe that explains why this corner is special. Stage 1
     decomposes exactly (Stage1.h header): the op-amp holds node_C at Vin, so ig = Vin/Zg is set by
     BASS and the INPUT LEVEL ALONE — independent of DRIVE — while the unclipped feedback swing
     Vf = Vin*Zf/Zg carries all the DRIVE dependence. The diode clamp therefore sits at
     V = n*Vt_eff*ln(ig/Is) at EVERY drive setting, and onset is where Vf crosses it. Result: the
     whole dataset sits 8-40 dB past onset except `Hard D0.20`/-18 at +5.4 dB. Pre-clip gain is
     observable ONLY there; everywhere else THD has saturated and is blind to it. That is both why
     the 2.2 fit missed this and why fixing it costs nothing at D >= 0.35.
     Side finding, recorded but NOT acted on: `kAsymMismatch` is a FRACTIONAL Vt spread symmetric
     about vtBase, so Hard's low-side clamp is 0.231 V — BELOW Soft's 0.365 V. The model's "hardest"
     mode starts clipping earliest, inverting the ordering the switch is named for.

  3. `levers()` — renders; tests the two candidate levers against the captures each can move.
     (a) `kAsymMismatch` over the six Hard captures: REFUTED as the W2 lever. It moves H2 and
     almost nothing else — dTHD at D >= 0.35 is 0.57-0.62 dB rms for EVERY value from 0 to 0.45,
     and dLEVEL is invariant to it. Driving it to 0 does cut D0.20/-18 from +11.6 to +5.4 dB, but
     it destroys the even-harmonic content that matches the pedal at every other drive (rms dH2
     1.34 -> unmeasurable). No single value satisfies both.
     (b) DRIVE taper exponent over ALL 16 captures (DRIVE is shared by all three modes and by the
     LEVEL gate). This is the lever.

  4. `fit()` — the JOINT fit, and the honest one. A pre-clip GAIN law does not only move THD: at
     low drive it also moves how hard the clipper compresses, and therefore the measured frequency
     response. So this scores THD and 1 kHz-normalised FR together over all 16 captures at all four
     sweep depths, and reproduces knob_tracking's SHAPE and LEVEL gates exactly (verified: at the
     old 2.2 it returns 13/16 and 14/16, matching `knob_tracking.py analysis/pedal2` under
     SIGNAL=v2). `--fit-tilt` crosses the exponent with DriveTilt's shelf gain, because DriveTilt
     was fitted against these same low-drive captures under the OLD taper and cannot be assumed to
     still hold.

Usage (from the repo root):
    analysis/.venv/bin/python3 analysis/w2_clip_onset.py [--only characterise,onset,levers,fit]
                                                         [--jobs N] [--mismatch 0,0.25,0.45]
                                                         [--onset-exp 2.2] [--fit-exp ...]
                                                         [--fit-tilt ...]

Probe 2 models the SHIPPED taper by default; pass `--onset-exp 2.2` to reproduce the pre-W2 margins
quoted in its narration and in the plan. Probes 1's narration likewise quotes the pre-W2 diagnosis —
its TABLE always reflects whatever `comprehensive_data.json` currently holds.

Probes 1/2 need `analysis/reports/comprehensive_data.json` (regenerate with
comprehensive_report.py). Probes 3/4 additionally need
`build/OfflineRender_artefacts/Release/OfflineRender`.
"""

import argparse
import concurrent.futures
import json
import math
import os
import statistics as st
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "analysis"))
os.chdir(REPO)

import numpy as np  # noqa: E402

import analyze as A  # noqa: E402

A.use_layout("v2")  # pedal2 is a v2-signal batch
import captures as C  # noqa: E402

JSON_PATH = os.path.join(REPO, "analysis/reports/comprehensive_data.json")

# --- Stage 1 component values (circuit.md; mirrored in src/dsp/Stage1.h) ---
R3, C3, C4, R7, C1 = 3.3e3, 39.0e-9, 1.0e-6, 3.3e3, 100.0e-12
KIS = 1.26e-9        # shared diode saturation current (Stage1.h kIs)
KVT, KN = 25.85e-3, 1.752
VT_EFF = KN * KVT                 # 45.3 mV — Soft/Hard effective thermal voltage
VT_EFF_MEDIUM = 1.35 * KN * KVT   # 61.1 mV — W1 fit
ASYM_MISMATCH = 0.45              # Stage1.h kAsymMismatch (Hard)
SYM_MISMATCH = 0.06               # Stage1.h kSymMismatch (Soft/Medium)
KINPUT_REF = 1.2                  # volts per full scale (PluginProcessor.h)

DRIVEN = ["sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6"]
LEVEL_DBFS = {"sweep_drv_-18": -18.0, "sweep_drv_-12": -12.0, "sweep_drv_-6": -6.0}
PROBE_HZ = [101.0, 403.0, 1015.9]   # THD probe bands (inside the 100 Hz-2 kHz report window)
ANCHORS = [110.0, 220.0, 440.0]     # harmonic anchors, matching comprehensive_report.py
THD_WINDOW = (100.0, 2000.0)        # the canonical report metric's band window


# ---------------------------------------------------------------- tapers (TaperUtils.h)
def bass_resistance(x):
    """BASS_R = 50k * x^2.41."""
    return 0.0 if x <= 0.0 else 50.0e3 * x**2.41


DRIVE_EXP_SHIPPED = 2.75   # TaperUtils.h driveResistance — W2 re-fit; was 2.2 before 2026-07-27
DRIVE_EXP_PRE_W2 = 2.2     # pass exp=DRIVE_EXP_PRE_W2 to reproduce the pre-fix onset table


def drive_resistance(x, coeff=1.0e6, exp=DRIVE_EXP_SHIPPED):
    """DRIVE_R = 1e6 * x^2.75 (A1M pot); coeff/exp exposed so probes 3/4 can sweep the taper.
    Keep the default in step with TaperUtils.h — probe 2 is a model of the SHIPPED circuit."""
    return 0.0 if x <= 0.0 else coeff * x**exp


def zg(f, bass_x):
    """Gain-set leg R3 + ( C3 || (BASS_R + C4) ) — the impedance that sets ig = Vin/Zg."""
    w = 2.0 * math.pi * f
    z_c3, z_c4 = 1.0 / (1j * w * C3), 1.0 / (1j * w * C4)
    leg = bass_resistance(bass_x) + z_c4
    return R3 + (z_c3 * leg) / (z_c3 + leg)


def zf(f, drive_x, **kw):
    """Feedback leg ( R7 + DRIVE_R ) || C1 — carries all the DRIVE dependence."""
    w = 2.0 * math.pi * f
    z_c1 = 1.0 / (1j * w * C1)
    r = R7 + drive_resistance(drive_x, **kw)
    return (r * z_c1) / (r + z_c1)


def clamp_volts(ig, vt_eff):
    """Diode clamp: the node_D swing at which diode current equals the source current ig,
    V = n*Vt*ln(ig/Is). Note ig is set by Vin and BASS only — NOT by DRIVE."""
    return vt_eff * math.log(max(ig, 1e-15) / KIS)


def clamps_for(mode, ig):
    """(low, high) clamp magnitudes for a clip mode, in volts at node_D.

    Soft/Medium/Hard all use AsymDiodePairT, whose `mismatch` is a FRACTIONAL Vt spread: the
    +swing diode sees Vt*(1+m) and the -swing diode Vt*(1-m). So the LOW clamp — the one that
    sets clip onset — is (1-m) times the matched value. Hard's m = 0.45 makes its low side clamp
    at 55% of a nominal 1N4148 drop, which is the whole of W2 (see levers()).
    """
    ln_ig = math.log(max(ig, 1e-15))
    if mode == "Soft":                      # setMode: 2*kIs, kN, kSymMismatch
        base, m = VT_EFF * (ln_ig - math.log(2.0 * KIS)), SYM_MISMATCH
    elif mode == "Medium":                  # setMode: kIs, kNMedium, mediumMismatch()
        base, m = VT_EFF_MEDIUM * (ln_ig - math.log(KIS)), SYM_MISMATCH / 1.35
    else:                                   # Hard: kIs, kN, kAsymMismatch
        base, m = VT_EFF * (ln_ig - math.log(KIS)), ASYM_MISMATCH
    return base * (1.0 - m), base * (1.0 + m)


def load_json():
    with open(JSON_PATH) as fh:
        return json.load(fh)


def band_idx(bands, lo, hi):
    return [i for i, f in enumerate(bands) if lo <= f <= hi]


def thd_err_db(cap, level, bands, idx):
    """Median 20*log10(plugin%/pedal%) over the report's 100 Hz-2 kHz window."""
    t = cap["thd"][level]
    d = [20.0 * math.log10(t["plugin_pct"][i] / t["pedal_pct"][i])
         for i in idx if t["plugin_pct"][i] and t["pedal_pct"][i]]
    return st.median(d) if d else float("nan")


# ================================================================ probe 1
def characterise(data):
    print("=" * 94)
    print("PROBE 1 — where the onset error lives (from comprehensive_data.json)")
    print("=" * 94)
    bands = data["meta"]["bands"]
    idx = band_idx(bands, *THD_WINDOW)

    print("\n(a) THD error, median over 100 Hz-2 kHz, dB (plugin re pedal). "
          "Positive = plugin too distorted.\n")
    print(f"  {'capture':30s} {'-18':>7} {'-12':>7} {'-6':>7} | {'pedal% @-18':>12}")
    rows = sorted(data["captures"], key=lambda c: (c["settings"]["drive"], c["rev"]))
    for c in rows:
        errs = [thd_err_db(c, l, bands, idx) for l in DRIVEN]
        ped = st.median([c["thd"]["sweep_drv_-18"]["pedal_pct"][i] for i in idx
                         if c["thd"]["sweep_drv_-18"]["pedal_pct"][i]])
        print(f"  {c['id'][:30]:30s} {errs[0]:+7.2f} {errs[1]:+7.2f} {errs[2]:+7.2f} | {ped:12.2f}")

    print("\n  Read (figures quoted below are the PRE-W2 diagnosis; a post-fix JSON shows the "
          "corrected table above):")
    print("  the error was monotone in DRIVE and mode-INDEPENDENT in trend "
          "(D0.35: Soft +1.0 / Hard +1.4 / Medium +2.8;")
    print("  D>=0.50: all within +-0.7). Only D0.20 breaks out, at +11.6 dB — and D0.20 is the "
          "one setting where the")
    print("  pedal itself is still essentially clean (3.5% vs 16.4% at D0.35), i.e. the pedal has "
          "not reached onset and the")
    print("  plugin has. This is an ONSET shift, not a knee-shape error at a shared operating "
          "point.")

    print("\n(b) Hard mode H2 (median over 110/220/440 Hz), dBc — the discriminator.\n")
    print(f"  {'capture':22s} {'level':>6} {'pedal':>8} {'plugin':>8} {'delta':>8}")
    for c in sorted([x for x in data["captures"] if x["rev"] == "Hard"],
                    key=lambda c: c["settings"]["drive"]):
        for l in DRIVEN:
            h = c["harmonics"][l]["H2"]
            p, q = st.median(h["plugin_db"]), st.median(h["pedal_db"])
            print(f"  D{c['settings']['drive']:.2f}{'':17s} {LEVEL_DBFS[l]:+6.0f} "
                  f"{q:8.1f} {p:8.1f} {p - q:+8.1f}")
        print()
    print("  Read (pre-W2 figures): H2 matched within ~1.8 dB at EVERY drive from 0.35 up, at "
          "every level — the asymmetry is well calibrated")
    print("  where it was fitted. At D0.20/-18 it is +13.6 dB. Note also the DIRECTION of the "
          "pedal's own level trend: at")
    print("  D0.20 its H2 RISES with level (-32.8 -> -22.0 -> -23.8) while at D0.35+ it FALLS. "
          "That is one curve — H2 peaks")
    print("  just past onset and decays into deep clipping — and it says the pedal's D0.20/-18 "
          "point is BELOW onset while")
    print("  the plugin's is above it.")


# ================================================================ probe 2
def onset(data, exp=DRIVE_EXP_SHIPPED):
    print("\n" + "=" * 94)
    print(f"PROBE 2 — analytic clip onset: unclipped swing vs diode clamp  (DRIVE exp {exp:g}"
          f"{' = SHIPPED' if exp == DRIVE_EXP_SHIPPED else ''})")
    print("=" * 94)
    print("""
Stage 1 decomposes exactly (Stage1.h header): the ideal op-amp holds node_C at Vin, so
    ig = Vin / Zg                      <- set by BASS and INPUT LEVEL only, NOT by DRIVE
    Vf = Vin * |Zf/Zg|                 <- unclipped feedback swing, carries all the DRIVE dependence
    V_clamp = n*Vt_eff*ln(ig/Is)       <- where diode current meets ig; grows only logarithmically
Onset is Vf > V_clamp(low side). Overdrive below is 20*log10(Vf / V_clamp_low).
""")
    f = 200.0  # inside the flat part of the reported THD window
    print(f"  probe frequency {f:.0f} Hz\n")
    print(f"  {'capture':30s} {'lvl':>4} {'ig uA':>7} {'clamp- V':>9} {'clamp+ V':>9} "
          f"{'Vf V':>7} {'overdrive dB':>13}")
    for c in sorted(data["captures"], key=lambda c: (c["settings"]["drive"], c["rev"])):
        s = c["settings"]
        g = abs(zf(f, s["drive"], exp=exp) / zg(f, s["bass"]))
        for l in DRIVEN:
            vin = KINPUT_REF * 10.0 ** (LEVEL_DBFS[l] / 20.0)
            ig = vin / abs(zg(f, s["bass"]))
            lo, hi = clamps_for(c["rev"], ig)
            vf = vin * g
            print(f"  {c['id'][:30]:30s} {LEVEL_DBFS[l]:+4.0f} {ig * 1e6:7.2f} {lo:9.3f} "
                  f"{hi:9.3f} {vf:7.3f} {20 * math.log10(vf / lo):+13.2f}")
        print()
    print("  Read (the numbers quoted here are for the PRE-W2 taper — rerun with "
          "--onset-exp 2.2 to see them):")
    print("  at exp 2.2 the whole dataset sat 8-40 dB past onset EXCEPT Hard D0.20/-18 at +5.4 dB. "
          "Pre-clip gain")
    print("  is observable at exactly one capture and nowhere else — everywhere else THD has "
          "saturated and is")
    print("  blind to it. That is both why the old mid-drive fit missed this and why correcting it "
          "costs nothing")
    print("  at D >= 0.35. At the shipped exp 2.75 that capture's margin becomes -1.1 dB, i.e. just "
          "BELOW onset —")
    print("  which is where the pedal itself is (2.55% THD, essentially clean), and it is why the "
          "fix lands.")
    print("  Side finding, NOT acted on: Hard's LOW clamp is 0.55x a nominal 1N4148 drop, because")
    print("  kAsymMismatch = 0.45 is a FRACTIONAL Vt spread symmetric about vtBase "
          "(VtN = Vt_eff*(1-m) = 24.9 mV")
    print("  vs 45.3). At 0.231 V that is BELOW Soft's 0.365 V — the model's 'hardest' mode starts "
          "clipping")
    print("  earliest, inverting the ordering the switch is named for. Left alone: probe 3a shows "
          "moving it")
    print("  trades the pedal-matching even-harmonic content for no THD benefit.")


# ================================================================ probe 3
_ORIG = None
_ORIG_F32 = None


def _init_worker():
    global _ORIG, _ORIG_F32
    _ORIG = A.load(A.ORIG)
    fh = tempfile.NamedTemporaryFile(suffix=".f32", delete=False)
    _ORIG_F32 = fh.name
    fh.close()
    _ORIG.astype(np.float32).tofile(_ORIG_F32)


FR_BANDS = [20.0 * 2.0 ** (i / 3.0) for i in range(30)]      # 1/3-octave, 20 Hz-16 kHz
FR_SCORED = [f for f in FR_BANDS if 60.0 <= f <= 8000.0]     # knob_tracking's SHAPE window
ALL_SWEEPS = ["sweep_clean"] + DRIVEN


def _features(sig, orig):
    """Farina THD + harmonic curves for the three driven sweeps, the 1 kHz-normalised FR at
    1/3-octave bands for all four sweep depths, and the knob_tracking LEVEL segment (a -12 dBFS
    1 kHz step, RMS)."""
    inp = A.seg_of(orig, "sweep_clean")
    out = {l: A.harmonic_thd_curve(A.seg_of(sig, l), inp, max_order=7) for l in DRIVEN}
    fr = {}
    for l in ALL_SWEEPS:
        f, mag = A.transfer(A.seg_of(sig, l), inp)
        curve = [A.gain_at(f, mag, b) for b in FR_BANDS]
        ref = A.gain_at(f, mag, 1015.9)
        fr[l] = [c - ref for c in curve]     # normalised at 1 kHz -> pure shape
    out["fr"] = fr
    out["lvl"] = A.rms_db(A.seg_of(sig, "lvl-12"))
    return out


def _at(fr, y, f):
    return float(np.interp(f, fr, y))


def _h_dbc(Hn, fr, order, f):
    return 20.0 * math.log10(max(_at(fr, Hn[order], f), 1e-12) / max(_at(fr, Hn[1], f), 1e-12))


def _summarise(feat):
    """(median THD% per level, median H2 dBc per level, level dB, 1 kHz-normalised FR per level)."""
    thd = {l: st.median([_at(feat[l][0], feat[l][1], f) for f in PROBE_HZ]) for l in DRIVEN}
    h2 = {l: st.median([_h_dbc(feat[l][2], feat[l][0], 2, f) for f in ANCHORS]) for l in DRIVEN}
    return thd, h2, feat["lvl"], feat["fr"]


def _render_job(job):
    """(label, parsed, extra_args) -> (label, drive, summarised plugin features)."""
    label, parsed, extra = job
    out = tempfile.NamedTemporaryFile(suffix=".f32", delete=False).name
    try:
        cmd = [C.RENDER_BIN, _ORIG_F32, out] + C.render_args(parsed, extra_args=extra)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip())
        sig, _ = A.align(np.fromfile(out, dtype=np.float32).astype(np.float64), _ORIG)
    finally:
        if os.path.exists(out):
            os.unlink(out)
    return label, parsed["drive"], _summarise(_features(sig, _ORIG))


def _pedal_job(path):
    cap, _ = A.align(A.load(path), _ORIG)
    return path, _summarise(_features(cap, _ORIG))


def xargs(kin=KINPUT_REF, asym=-1.0, drive_coeff=-1.0, drive_exp=1.0, tilt=-1.0):
    """OfflineRender argv[10..24] with named overrides; everything else left at its default."""
    a = [f"{kin}", "-1", "1.43", "-1", "1.43", f"{asym}", "0",
         f"{drive_coeff}", f"{drive_exp}"]
    if tilt >= 0.0:  # argv[19..23] must be filled in to reach argv[24]
        a += ["9", "-1", "-1", "-1", "1", f"{tilt}"]
    return a


def run_variants(variants, caps, jobs):
    """Render `caps` under each named variant. Returns (pedal_by_key, {label: {key: summary}}),
    keyed by (mode, drive) so mixed-mode capture sets stay separable."""
    def key(q):
        return (q["rev"], q["drive"])

    work = []
    for label, extra in variants:
        for p, parsed in caps:
            work.append((label, parsed, extra))

    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs,
                                                initializer=_init_worker) as ex:
        ped_raw = dict(ex.map(_pedal_job, [p for p, _ in caps]))
        rendered = list(ex.map(_render_job, work))

    ped = {key(q): ped_raw[p] for p, q in caps}
    keys = {q["drive"]: key(q) for _, q in caps}  # only valid for single-mode sets
    by_label = {}
    for (label, drive, summ), (_, parsed) in zip(rendered, [(w[0], w[1]) for w in work]):
        by_label.setdefault(label, {})[key(parsed)] = summ
    del keys
    return ped, by_label


def _fr_cost(ped, table, sweep):
    """RMS over captures of the per-capture rms |plugin-pedal| 1 kHz-normalised FR deviation
    across knob_tracking's 60 Hz-8 kHz SHAPE window."""
    per = []
    for k in table:
        idx = [i for i, f in enumerate(FR_BANDS) if f in FR_SCORED]
        d = [table[k][3][sweep][i] - ped[k][3][sweep][i] for i in idx]
        per.append(math.sqrt(sum(x * x for x in d) / len(d)))
    return rms(per)


def _shape_fails(ped, table):
    """knob_tracking's SHAPE gate, reproduced: max |dev| over 60 Hz-8 kHz on sweep_clean > 1.5 dB."""
    n = 0
    for k in table:
        idx = [i for i, f in enumerate(FR_BANDS) if f in FR_SCORED]
        n += max(abs(table[k][3]["sweep_clean"][i] - ped[k][3]["sweep_clean"][i])
                 for i in idx) > 1.5
    return n


def _variant_table(label, ped, table, show_h2=True):
    print(f"\n--- {label} ---")
    hdr = f"  {'capture':>16} {'lvl':>4} {'THD ped/plg':>14} {'dTHD dB':>8}"
    if show_h2:
        hdr += f" {'H2 ped/plg':>16} {'dH2 dB':>8}"
    print(hdr + f" {'dLEVEL':>7}")
    for k in sorted(table, key=lambda k: (k[1], k[0])):
        pt, ph, pl_ = ped[k][:3]
        rt, rh, rl = table[k][:3]
        for n, l in enumerate(DRIVEN):
            # LEVEL is a single -12 dBFS 1 kHz step per capture, so print it once per capture.
            lvl_col = f"{rl - pl_:+7.2f}" if n == 0 else " " * 7
            row = (f"  {k[0] + ' D' + format(k[1], '.2f'):>16} {LEVEL_DBFS[l]:+4.0f} "
                   f"{pt[l]:6.2f}/{rt[l]:6.2f} {20 * math.log10(rt[l] / pt[l]):+8.2f}")
            if show_h2:
                row += f" {ph[l]:7.1f}/{rh[l]:7.1f} {rh[l] - ph[l]:+8.1f}"
            print(row + f" {lvl_col}")
    lo = [k for k in table if k[1] <= 0.20]
    hi = [k for k in table if k[1] >= 0.35]

    def agg(ks, idx):
        return rms([(20 * math.log10(table[k][0][l] / ped[k][0][l]) if idx == 0
                     else table[k][1][l] - ped[k][1][l]) for k in ks for l in DRIVEN])
    print(f"    rms dTHD  D<=0.20 {agg(lo, 0):5.2f} dB | D>=0.35 {agg(hi, 0):5.2f} dB")
    if show_h2:
        print(f"    rms dH2   D<=0.20 {agg(lo, 1):5.2f} dB | D>=0.35 {agg(hi, 1):5.2f} dB")
    print(f"    max |dLEVEL| {max(abs(table[k][2] - ped[k][2]) for k in table):.2f} dB "
          f"(knob_tracking gate is 2.0)")


def levers(mismatches, drive_exps, jobs):
    print("\n" + "=" * 94)
    print("PROBE 3 — candidate levers, rendered across the captures each lever can move")
    print("=" * 94)
    if not os.path.exists(C.RENDER_BIN):
        print(f"  ! {C.RENDER_BIN} not found — build OfflineRender first. Skipping.")
        return

    all_caps = C.find_captures()
    hard = sorted([(p, q) for p, q in all_caps if q["rev"] == "Hard"],
                  key=lambda t: t[1]["drive"])

    print("""
(a) kAsymMismatch — the Hard-branch asymmetry. It is a FRACTIONAL Vt spread symmetric about
    vtBase, so raising it LOWERS the clip threshold on one polarity: at m = 0.45 Hard's low side
    clamps at 0.231 V, BELOW Soft's 0.365 V, which inverts the mode ordering the switch is named
    for. Hard captures only (it touches no other mode).""")
    ped, by_label = run_variants([(f"kAsymMismatch {m:g}"
                                  + ("   (SHIPPED)" if abs(m - ASYM_MISMATCH) < 1e-9 else ""),
                                  xargs(asym=m)) for m in mismatches], hard, jobs)
    for label, _ in [(f"kAsymMismatch {m:g}"
                      + ("   (SHIPPED)" if abs(m - ASYM_MISMATCH) < 1e-9 else ""), None)
                     for m in mismatches]:
        _variant_table(label, ped, by_label[label])

    print("""
(b) DRIVE taper exponent — the SHARED pre-clip gain law (DRIVE_R = 1e6 * x^exp, TaperUtils.h).
    This is the lever the mode-independence of the error points at: at -18 dBFS every mode is too
    distorted at low drive (D0.35: Soft +1.0 / Hard +1.4 / Medium +2.8 dB) and the ordering follows
    each mode's overdrive margin from probe 2, not its diode parameters. Run over ALL 16 captures,
    because DRIVE is shared by all three modes and by the LEVEL gate.""")
    caps = sorted(all_caps, key=lambda t: (t[1]["drive"], t[1]["rev"]))
    ped2, by_label2 = run_variants([(f"driveExp {e:g}"
                                     + ("   (SHIPPED)" if abs(e - 2.2) < 1e-9 else ""),
                                     xargs(drive_coeff=1.0e6, drive_exp=e)) for e in drive_exps],
                                   caps, jobs)
    for e in drive_exps:
        label = f"driveExp {e:g}" + ("   (SHIPPED)" if abs(e - 2.2) < 1e-9 else "")
        _variant_table(label, ped2, by_label2[label], show_h2=False)


def fit(pairs, jobs):
    """Probe 4 — the JOINT fit. Sweeping the DRIVE exponent on THD alone is not enough: the taper
    is a pre-clip GAIN law, so at low drive it also moves how much the clipper compresses, and
    therefore the measured frequency response. This scores both against all 16 pedal2 captures so
    the trade is explicit rather than discovered afterwards."""
    print("\n" + "=" * 94)
    print("PROBE 4 — joint THD + FR fit of the DRIVE taper exponent (all 16 captures)")
    print("=" * 94)
    if not os.path.exists(C.RENDER_BIN):
        print(f"  ! {C.RENDER_BIN} not found — build OfflineRender first. Skipping.")
        return
    caps = sorted(C.find_captures(), key=lambda t: (t[1]["drive"], t[1]["rev"]))
    variants = [(f"{e:g}/{t:g}", xargs(drive_coeff=1.0e6, drive_exp=e, tilt=t)) for e, t in pairs]
    ped, by_label = run_variants(variants, caps, jobs)

    print("\n  THD  = rms over 16 captures x 3 driven depths of the median 100 Hz-2 kHz THD error")
    print("  FR   = rms over captures of each capture's rms 1 kHz-normalised FR deviation, "
          "60 Hz-8 kHz")
    print("  SHAPE/LEVEL fails reproduce knob_tracking's gates (1.5 dB on sweep_clean / 2.0 dB)\n")
    print(f"  {'exp/tilt':>9} | {'THD all':>8} {'THD D<=.20':>11} {'THD D>=.35':>11} | "
          f"{'FR clean':>9} {'FR -18':>7} {'FR -12':>7} {'FR -6':>7} | {'SHAPE':>6} {'LEVEL':>6}")
    for label, _ in variants:
        t = by_label[label]
        lo = [k for k in t if k[1] <= 0.20]
        hi = [k for k in t if k[1] >= 0.35]

        def thd(ks):
            return rms([20 * math.log10(t[k][0][l] / ped[k][0][l]) for k in ks for l in DRIVEN])
        lvl_fail = sum(abs(t[k][2] - ped[k][2]) > 2.0 for k in t)
        print(f"  {label:>9} | {thd(list(t)):8.2f} {thd(lo):11.2f} {thd(hi):11.2f} | "
              f"{_fr_cost(ped, t, 'sweep_clean'):9.3f} "
              + " ".join(f"{_fr_cost(ped, t, l):7.3f}" for l in DRIVEN)
              + f" | {16 - _shape_fails(ped, t):4d}/16 {16 - lvl_fail:4d}/16")


def rms(v):
    return math.sqrt(sum(x * x for x in v) / len(v)) if v else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="characterise,onset,levers,fit",
                    help="comma-separated probe names")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--onset-exp", type=float, default=DRIVE_EXP_SHIPPED,
                    help=f"DRIVE exponent for probe 2 (default {DRIVE_EXP_SHIPPED} = shipped; "
                         f"pass {DRIVE_EXP_PRE_W2} to reproduce the pre-W2 table)")
    ap.add_argument("--mismatch", default="0,0.25,0.45",
                    help="kAsymMismatch values for probe 3(a)")
    ap.add_argument("--drive-exp", default="2.2,2.6,3.0",
                    help="DRIVE taper exponents for probe 3(b)")
    ap.add_argument("--fit-exp", default="2.2,2.4,2.5,2.6,2.7,2.75,2.8,3.0",
                    help="DRIVE taper exponents for probe 4's joint fit")
    ap.add_argument("--fit-tilt", default="2.5",
                    help="DriveTilt kMaxGainDB values to cross with --fit-exp (2.5 = shipped)")
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    if {"characterise", "onset"} & only:
        data = load_json()
    if "characterise" in only:
        characterise(data)
    if "onset" in only:
        onset(data, args.onset_exp)
    if "levers" in only:
        levers([float(s) for s in args.mismatch.split(",")],
               [float(s) for s in args.drive_exp.split(",")], args.jobs)
    if "fit" in only:
        fit([(e, t) for e in (float(s) for s in args.fit_exp.split(","))
             for t in (float(s) for s in args.fit_tilt.split(","))], args.jobs)


if __name__ == "__main__":
    main()
