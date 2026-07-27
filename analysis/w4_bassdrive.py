"""v1.4 W4 — characterise the BASS <-> DRIVE coupling error (LF excess) vs pedal2.

Plan item W4 (`.claude/plans/v1.4-fidelity.md` §1.2). The LF excess below ~100 Hz is real
(+2.8 dB @20 Hz on the clean sweep, positive in 16/16 captures) but it is NOT a BASS-taper error:
it is clip-mode dependent at matched (BASS, DRIVE) and it shrinks as the clipper is driven. BASS
and DRIVE are perfectly confounded in pedal2 and no further captures exist (W6 struck), so the
only confound-free handle is the CLIP-MODE SPREAD at matched (BASS, DRIVE).

Probes, each chosen so it cannot be confused with the others:

  1. `spread()`  — the confound-free measurement. At each (BASS, DRIVE) point where all three
     switch positions were captured, report the 1 kHz-normalised LF response of plugin and pedal
     SEPARATELY per mode, then the mode spread within each. A linear filter error (taper, HP
     corner, capture-chain rolloff) has ZERO mode spread by construction, so any spread is
     clipping-mediated — and comparing the plugin's own spread against the pedal's own spread says
     whether the model over- or under-couples, with no reliance on the absolute BASS/DRIVE split.

  2. `shelf()`   — the model's LINEAR Stage-1 gain-set shelf, computed analytically from the
     shipped component values and tapers: gain(f) = 1 + Zf/Zg, with
        Zg = R3 + ( C3 || (BASS_R + C4) )        (BASS lives here)
        Zf = ( R7 + DRIVE_R ) || C1              (DRIVE lives here)
     The "+1" is what couples them: at low DRIVE, Zf is small and gain -> 1 at every frequency, so
     the shelf is SHALLOW; at high DRIVE the shelf deepens. So the linear part of the model already
     couples BASS and DRIVE, and this probe quantifies how much — the baseline any clipping-mediated
     explanation has to sit on top of. Compared against the pedal's clean-sweep shelf.

  3. `order()`   — is the pedal's mode spread a MECHANISM or capture scatter? Two controls: (i) is
     the same mode the outlier at 20 Hz and at 16 kHz, and (ii) how correlated are the two ends.
     A per-capture broadband tilt would show one consistent ordering at both ends and r ~ +1. This
     probe is what separates the real LF effect from the noise at the top of the sweep — do not
     read the pedal's HF mode spread as a mechanism, it fails this test.

  4. `anchor()` — the probe that overturns the other three. At -30 dBFS it is tempting to treat the
     clean sweep as linear and explain the mode spread by the diodes' ZERO-BIAS incremental
     resistance r_d = n·Vt/(m·Is) shunting (R7 + DRIVE_R). That reading is DEAD: Stage 1's midband
     gain is 25-44 dB here, so the 1 kHz NORMALISATION ANCHOR is itself driven past the diode clamp
     in 12/16 captures. Per-mode compression at the anchor then sets the apparent shelf depth and
     orders exactly by clip threshold — so probe 1's lever measures clip thresholds, not the LF
     network. Check the anchor before trusting ANY 1 kHz-normalised LF number.

  5. `correction()` — the corrective-shelf question, i.e. "never mind the mechanism, can a filter
     just match the shape?" Emits the required-correction table reproducibly (handover step 1),
     checks the excess is LF-localised rather than a broadband anchor offset, fits the best static
     1st-order low shelf, and then reports what that shelf does to knob_tracking's SHAPE gate and
     to the per-mode spread. Answer: no — the mode-independent part is subsonic (a ~15 Hz-corner
     rumble trim, 0.23 dB at 60 Hz) and the part that fails SHAPE is mode-dependent and of BOTH
     signs. Also documents a sign error in the plan's handover table.

Usage (from the repo root):
    analysis/.venv/bin/python3 analysis/w4_bassdrive.py [--only spread,order,anchor,shelf,correction]

Needs analysis/reports/comprehensive_data.json (regenerate with comprehensive_report.py).
No renders and no build are required — probes 2/3's model side is closed-form.
"""

import argparse
import json
import math
import os
import sys
import statistics as st

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(REPO, "analysis/reports/comprehensive_data.json")

# --- Stage 1 component values (circuit.md; mirrored in src/dsp/Stage1.h) ---
R3 = 3.3e3
C3 = 39.0e-9
C4 = 1.0e-6
R7 = 3.3e3
C1 = 100.0e-12

# --- Clipping levels, for deciding whether a band is a usable normalisation anchor ---
# Node_D clamp per SW1 mode (Stage1.h; Medium's 1.194 V is the v1.4 W1 fit, Hard clamps one
# polarity at the diode and the other at the op-amp rail, so its symmetric-equivalent is Soft's).
CLAMP_V = {"Soft": 0.987, "Medium": 1.194, "Hard": 0.987}
KINPUT_REF = 1.2  # volts per full scale (PluginProcessor.h)
CLEAN_DBFS = -30.0  # analysis/gen_test_signal_v2.py: sweep_clean is a -30 dBFS log sweep
# Peak level of each sweep segment (gen_test_signal_v2.py: DRIVEN_LEVELS_DB = -18/-12/-6).
# The driven sweeps are 12-24 dB HOTTER than the clean one, which is why the anchor gate gets
# strictly WORSE on them, not better — see correction()'s anchor-safety block.
LEVEL_DBFS = {"sweep_clean": -30.0, "sweep_drv_-18": -18.0,
              "sweep_drv_-12": -12.0, "sweep_drv_-6": -6.0}
# knob_tracking.py's SHAPE metric: bands scored, tolerance, and the sweep it reads.
SHAPE_FREQS = [60.0, 120.0, 250.0, 500.0, 1000.0, 2000.0, 4000.0, 8000.0]
SHAPE_TOL_DB = 1.5
SHAPE_SWEEP = "sweep_clean"

# LF bands the excess lives in, plus the normalisation anchor and a midband contrast.
LF_HZ = [20.0, 25.2, 31.7, 40.0, 50.4, 63.5, 80.0, 100.8]
NORM_HZ = 1015.9  # the 1 kHz band — normalising here removes the least-squares gain match
LEVELS = ["sweep_clean", "sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6"]
# Modes in threshold order (softest clip first) so the spread reads monotonically.
MODE_ORDER = ["Soft", "Medium", "Hard"]


# ---------------------------------------------------------------- tapers (TaperUtils.h)
def bass_resistance(x):
    """BASS_R = 50k * x^2.41 (convex; validated against batches 3/4/5)."""
    return 0.0 if x <= 0.0 else 50.0e3 * x**2.41


def drive_resistance(x):
    """DRIVE_R = 1e6 * x^2.75 (A1M pot).

    MUST track TaperUtils.h's driveResistance. Was x^2.2 here until 2026-07-27: that was correct
    when probes 1-5 were first run, but v1.4 W2 re-fitted the shipped taper to x^2.75 the same day
    and left this stale. Since x < 1 gives x^2.2 > x^2.75, the stale value OVERSTATED Stage 1's
    midband gain and so OVERSTATED the anchor overdrive in probe 4 (e.g. 0.388 vs 0.306 of Rmax at
    x=0.65, ~1.0 dB of gain). The anchor conclusions survive — the overdrive margins are 8-40 dB —
    but any change to the shipped taper invalidates every anchor-safety number here; re-check both
    together.
    """
    return 0.0 if x <= 0.0 else 1.0e6 * x**2.75


# ---------------------------------------------------------------- analytic Stage 1
def stage1_gain_db(f, bass_x, drive_x):
    """|1 + Zf/Zg| in dB — the shipped LINEAR Stage-1 gain (no diodes, no rail clip).

    Matches the decomposition in Stage1.h's header comment exactly.
    """
    w = 2.0 * math.pi * f
    z_c3 = 1.0 / (1j * w * C3)
    z_c4 = 1.0 / (1j * w * C4)
    z_c1 = 1.0 / (1j * w * C1)

    bass_leg = bass_resistance(bass_x) + z_c4  # BASS_R + C4, in series
    node_x = (z_c3 * bass_leg) / (z_c3 + bass_leg)  # C3 || (BASS_R + C4)
    zg = R3 + node_x

    r_fb = R7 + drive_resistance(drive_x)
    zf = (r_fb * z_c1) / (r_fb + z_c1)  # (R7 + DRIVE_R) || C1

    return 20.0 * math.log10(abs(1.0 + zf / zg))


def stage1_lin_gain(f, bass_x, drive_x):
    """Linear |1 + Zf/Zg| as a ratio (not dB) — used to locate the diode knee."""
    return 10.0 ** (stage1_gain_db(f, bass_x, drive_x) / 20.0)


def model_shelf_db(f, bass_x, drive_x):
    """Linear shelf depth at f, normalised at 1 kHz (negative = LF below midband)."""
    return stage1_gain_db(f, bass_x, drive_x) - stage1_gain_db(NORM_HZ, bass_x, drive_x)


# ---------------------------------------------------------------- json helpers
def load_json():
    if not os.path.exists(JSON_PATH):
        sys.exit(f"missing {JSON_PATH} — regenerate with analysis/comprehensive_report.py")
    with open(JSON_PATH) as f:
        return json.load(f)


def band_index(bands, hz):
    return min(range(len(bands)), key=lambda i: abs(bands[i] - hz))


def norm_curve(caps_fr, bands, side):
    """1 kHz-normalised dB curve for one side ('plugin_db' / 'pedal_db').

    Normalising each side against its OWN 1 kHz band removes gain_db_applied entirely, so this is
    independent of null_depth's least-squares fit — the artefact §1.1 identified.
    """
    vals = caps_fr[side]
    ref = vals[band_index(bands, NORM_HZ)]
    return [v - ref for v in vals]


def group_key(cap):
    s = cap["settings"]
    return (round(s["bass"], 3), round(s["drive"], 3))


# ---------------------------------------------------------------- probe 1: mode spread
def spread(data):
    print("=" * 96)
    print("PROBE 1 — clip-mode spread of the LF excess at MATCHED (BASS, DRIVE)")
    print("=" * 96)
    print(
        "The confound-free measurement. A linear error (BASS taper, HP corner, capture-chain\n"
        "rolloff) has zero mode spread by construction. Values are 1 kHz-normalised dB, so the\n"
        "least-squares gain match plays no part. Negative = LF below midband (the shelf).\n"
    )

    bands = data["meta"]["bands"]
    caps = data["captures"]

    groups = {}
    for cap in caps:
        groups.setdefault(group_key(cap), []).append(cap)
    matched = {k: v for k, v in groups.items() if len({c["rev"] for c in v}) == 3}

    if not matched:
        print("  no (BASS, DRIVE) point has all three switch positions — cannot run this probe")
        return

    print(f"  matched groups (all 3 switch positions): {sorted(matched)}")
    print(f"  unmatched: {sorted(k for k in groups if k not in matched)}\n")

    for key in sorted(matched):
        b, d = key
        by_mode = {c["rev"]: c for c in matched[key]}
        for level in LEVELS:
            if not all(level in c["fr"] for c in by_mode.values()):
                continue
            print(f"  --- BASS {b:.2f}  DRIVE {d:.2f}  ({level}) " + "-" * 40)
            print(f"    {'band':>8} | {'PLUGIN per mode':^26} | {'PEDAL per mode':^26} | spread")
            print(f"    {'Hz':>8} | " + "  ".join(f"{m:>6}" for m in MODE_ORDER) + " | "
                  + "  ".join(f"{m:>6}" for m in MODE_ORDER) + " |  plug   pedal")
            print("    " + "-" * 88)
            for hz in LF_HZ:
                i = band_index(bands, hz)
                plug, ped = [], []
                for m in MODE_ORDER:
                    fr = by_mode[m]["fr"][level]
                    plug.append(norm_curve(fr, bands, "plugin_db")[i])
                    ped.append(norm_curve(fr, bands, "pedal_db")[i])
                sp_plug = max(plug) - min(plug)
                sp_ped = max(ped) - min(ped)
                print(f"    {hz:8.1f} | " + "  ".join(f"{v:+6.2f}" for v in plug) + " | "
                      + "  ".join(f"{v:+6.2f}" for v in ped)
                      + f" | {sp_plug:5.2f}  {sp_ped:5.2f}")
            print()

    # Headline: median spread per side, per level, across matched groups and LF bands.
    print("  " + "=" * 90)
    print("  HEADLINE — median mode spread across LF bands (dB). Linear errors would give ~0.")
    print(f"    {'level':>14} | {'plugin':>8} | {'pedal':>8} | {'plugin-pedal':>13}")
    print("    " + "-" * 54)
    for level in LEVELS:
        sp_plug, sp_ped = [], []
        for key in sorted(matched):
            by_mode = {c["rev"]: c for c in matched[key]}
            if not all(level in c["fr"] for c in by_mode.values()):
                continue
            for hz in LF_HZ:
                i = band_index(bands, hz)
                plug = [norm_curve(by_mode[m]["fr"][level], bands, "plugin_db")[i] for m in MODE_ORDER]
                ped = [norm_curve(by_mode[m]["fr"][level], bands, "pedal_db")[i] for m in MODE_ORDER]
                sp_plug.append(max(plug) - min(plug))
                sp_ped.append(max(ped) - min(ped))
        if sp_plug:
            a, b_ = st.median(sp_plug), st.median(sp_ped)
            print(f"    {level:>14} | {a:8.2f} | {b_:8.2f} | {a - b_:+13.2f}")
    print()


# ---------------------------------------------------------------- probe 2: linear shelf
def shelf(data):
    print("=" * 96)
    print("PROBE 2 — the model's LINEAR Stage-1 shelf vs the pedal's clean-sweep shelf")
    print("=" * 96)
    print(
        "Model side is closed-form (gain = 1 + Zf/Zg from the shipped values/tapers, no diodes).\n"
        "Pedal side is the clean sweep, 1 kHz-normalised. 'model-pedal' > 0 means the model's LF\n"
        "sits ABOVE the pedal's, i.e. the model's shelf is too SHALLOW — the reported excess.\n"
        "This isolates how much of the excess exists before any diode conducts.\n"
    )

    bands = data["meta"]["bands"]
    caps = data["captures"]

    seen = {}
    for cap in caps:
        seen.setdefault(group_key(cap), []).append(cap)

    print(f"    {'BASS':>5} {'DRIVE':>6} | {'band':>8} | {'model':>7} {'plugin':>7} {'pedal':>7}"
          f" | {'mdl-ped':>8} {'plg-ped':>8}")
    print("    " + "-" * 76)
    for key in sorted(seen):
        b, d = key
        # Clean sweep is linear-ish for every mode, so average the modes present at this point.
        group = [c for c in seen[key] if "sweep_clean" in c["fr"]]
        if not group:
            continue
        for hz in LF_HZ:
            i = band_index(bands, hz)
            mdl = model_shelf_db(hz, b, d)
            plg = st.median([norm_curve(c["fr"]["sweep_clean"], bands, "plugin_db")[i] for c in group])
            ped = st.median([norm_curve(c["fr"]["sweep_clean"], bands, "pedal_db")[i] for c in group])
            print(f"    {b:5.2f} {d:6.2f} | {hz:8.1f} | {mdl:+7.2f} {plg:+7.2f} {ped:+7.2f}"
                  f" | {mdl - ped:+8.2f} {plg - ped:+8.2f}")
        print()

    print("  NOTE: 'model' is Stage 1 alone and LINEAR; 'plugin' is the full rendered chain (input")
    print("  buffer HP, C6 DC block, volume) WITH clipping. The ~10 dB gap between them is not an")
    print("  offset — it is probe 4's finding seen from the other side: the linear shelf is ~10 dB")
    print("  deep at 20 Hz, and clipping compresses the 1 kHz anchor by almost exactly that much,")
    print("  flattening the rendered shelf to ~0. So this probe's model column is the shelf the")
    print("  circuit WOULD have if nothing clipped, not the shelf either side actually exhibits.\n")


# ---------------------------------------------------------------- probe 3: mechanism vs scatter
def order(data):
    print("=" * 96)
    print("PROBE 3 — is the pedal's mode spread a MECHANISM, or per-capture scatter?")
    print("=" * 96)
    print(
        "Control (i): a per-capture broadband tilt puts the SAME mode at the extreme at both ends of\n"
        "the sweep. Control (ii): it also makes the two ends strongly correlated (r -> +1).\n"
        "The pedal's mode spread is a V pinned to 0.00 at the 1 kHz anchor and rising at BOTH ends,\n"
        "which looks like a tilt — these two controls are what tell the halves apart.\n"
    )

    bands = data["meta"]["bands"]
    i20, i16k = band_index(bands, 20.0), band_index(bands, 16255.0)

    groups = {}
    for cap in data["captures"]:
        groups.setdefault(group_key(cap), []).append(cap)
    matched = {k: v for k, v in groups.items() if len({c["rev"] for c in v}) == 3}

    print(f"    {'BASS':>5} {'DRIVE':>6} | {'20 Hz (Soft/Med/Hard)':^24} | {'16 kHz':^24} | ordering")
    print("    " + "-" * 86)
    n_same = n_tot = 0
    xs, ys = [], []
    for key in sorted(matched):
        by_mode = {c["rev"]: c for c in matched[key]}
        if not all("sweep_clean" in c["fr"] for c in by_mode.values()):
            continue
        lo = [norm_curve(by_mode[m]["fr"]["sweep_clean"], bands, "pedal_db")[i20] for m in MODE_ORDER]
        hi = [norm_curve(by_mode[m]["fr"]["sweep_clean"], bands, "pedal_db")[i16k] for m in MODE_ORDER]
        o_lo = sorted(range(3), key=lambda j: lo[j])
        o_hi = sorted(range(3), key=lambda j: hi[j])
        same = o_lo == o_hi
        n_same += same
        n_tot += 1
        mlo, mhi = sum(lo) / 3.0, sum(hi) / 3.0
        for j in range(3):
            xs.append(lo[j] - mlo)
            ys.append(hi[j] - mhi)
        print(f"    {key[0]:5.2f} {key[1]:6.2f} | " + "  ".join(f"{v:+6.2f}" for v in lo)
              + " | " + "  ".join(f"{v:+6.2f}" for v in hi)
              + f" | {'SAME' if same else 'differs':>7}  lo={'<'.join(MODE_ORDER[j] for j in o_lo)}")

    if n_tot:
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        sx = sum((a - mx) ** 2 for a in xs) ** 0.5
        sy = sum((b - my) ** 2 for b in ys) ** 0.5
        r = cov / (sx * sy) if sx > 0 and sy > 0 else float("nan")
        print()
        print(f"    orderings matching across the two ends: {n_same}/{n_tot}")
        print(f"    correlation of the two ends (deviation from group mean): r = {r:+.3f}  (n={n})")
        print()
        print("    READ: the 20 Hz ordering is systematic across every group while the 16 kHz one is")
        print("    not, and the two ends are uncorrelated. So the LF spread is a real mechanism and")
        print("    the HF spread is capture noise — they are NOT one broadband tilt.")
    print()


# ---------------------------------------------------------------- probe 4: the anchor
def anchor(data):
    print("=" * 96)
    print("PROBE 4 — is the 1 kHz normalisation anchor itself inside the clipping region?")
    print("=" * 96)
    print(
        "This probe exists because the obvious reading of probe 1 is wrong. At -30 dBFS it is\n"
        "tempting to treat the clean sweep as linear and explain the mode spread by the diodes'\n"
        "ZERO-BIAS resistance shunting the feedback leg. That explanation is dead: Stage 1's midband\n"
        "gain is 25-44 dB at these settings, so the 1 kHz ANCHOR is driven well past the diode clamp\n"
        "in almost every capture. Per-mode compression AT THE ANCHOR therefore sets the apparent\n"
        "shelf depth, and it orders exactly by clip threshold.\n"
    )

    bands = data["meta"]["bands"]
    i20, i1k = band_index(bands, 20.0), band_index(bands, NORM_HZ)
    v_in = KINPUT_REF * 10.0 ** (CLEAN_DBFS / 20.0)

    rows = []
    for cap in data["captures"]:
        s = cap["settings"]
        b, d, m = s["bass"], s["drive"], cap["rev"]
        fr = cap["fr"]["sweep_clean"]
        excess = ((fr["plugin_db"][i20] - fr["plugin_db"][i1k])
                  - (fr["pedal_db"][i20] - fr["pedal_db"][i1k]))
        depth_1k = 20.0 * math.log10(stage1_lin_gain(NORM_HZ, b, d) * v_in / CLAMP_V[m])
        depth_20 = 20.0 * math.log10(stage1_lin_gain(20.0, b, d) * v_in / CLAMP_V[m])
        rows.append((d, b, m, depth_1k, depth_20, excess))
    rows.sort()

    print(f"    clean sweep is {CLEAN_DBFS:.0f} dBFS => {v_in * 1000:.1f} mV peak in "
          f"(kInputRef={KINPUT_REF})")
    print("    'over clamp' is dB of modelled LINEAR node_D swing relative to that mode's clamp;")
    print("    positive means the band is compressed, so it cannot serve as a clean anchor.\n")
    print(f"    {'DRIVE':>5} {'BASS':>5} {'mode':>7} | {'1 kHz over clamp':>17}"
          f" {'20 Hz over clamp':>17} | {'LF excess':>10}")
    print("    " + "-" * 74)
    for d, b, m, dp, d20, ex in rows:
        flag = "" if dp < 0 else "  <- anchor compressed"
        print(f"    {d:5.2f} {b:5.2f} {m:>7} | {dp:+17.2f} {d20:+17.2f} | {ex:+10.2f}{flag}")

    safe = [r for r in rows if r[3] < 0.0]
    print()
    print(f"    captures with an UNCOMPRESSED 1 kHz anchor: {len(safe)}/{len(rows)}")
    for d, b, m, dp, d20, ex in safe:
        print(f"      D{d:.2f} B{b:.2f} {m}: anchor {dp:+.2f} dB, LF excess {ex:+.2f} dB")

    xs = [r[3] for r in rows]
    ys = [r[5] for r in rows]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((a - mx) * (b_ - my) for a, b_ in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    sy = sum((b_ - my) ** 2 for b_ in ys) ** 0.5
    r = cov / (sxx ** 0.5 * sy) if sxx > 0 and sy > 0 else float("nan")
    slope = cov / sxx if sxx > 0 else float("nan")
    print()
    print(f"    LF excess vs anchor overdrive: r = {r:+.3f}, slope = {slope:+.3f} dB/dB,")
    print(f"    intercept at zero overdrive = {my - slope * mx:+.3f} dB")
    print()

    # Ordering is a structural claim independent of magnitude.
    print("    ORDERING (shallowest apparent shelf -> deepest), clean sweep, pedal side:")
    groups = {}
    for cap in data["captures"]:
        groups.setdefault(group_key(cap), []).append(cap)
    measured = []
    for key in sorted(groups):
        by_mode = {c["rev"]: c for c in groups[key]}
        if len(by_mode) < 3 or not all("sweep_clean" in c["fr"] for c in by_mode.values()):
            continue
        depths = {m: norm_curve(by_mode[m]["fr"]["sweep_clean"], bands, "pedal_db")[i20]
                  for m in MODE_ORDER}
        measured.append(tuple(sorted(MODE_ORDER, key=lambda m: -depths[m])))
    for o in sorted(set(measured)):
        print(f"      pedal measures  : {' < '.join(reversed(o))}   "
              f"({measured.count(o)}/{len(measured)} groups)")
    print("      predicted by ANCHOR COMPRESSION : Soft < Hard < Medium")
    print("        Soft   — clamps both polarities at 0.987 V  => most anchor compression")
    print("        Hard   — single diode, clamps ONE polarity  => less")
    print("        Medium — clamps both, but at 1.194 V (W1)   => least")
    print()
    print("    READ: whichever mode compresses the anchor LEAST has the highest 1 kHz reference and")
    print("    so the DEEPEST-looking shelf. That predicted order is exactly what the pedal shows in")
    print("    5/5 groups. Note clamp voltage alone does not separate Soft from Hard (both 0.987 V)")
    print("    — it is Hard clipping only one polarity that puts it between them.")
    print()
    print("    CONSEQUENCE: the mode-spread lever measures CLIP THRESHOLDS, not the LF network, so it")
    print("    cannot de-confound BASS from DRIVE after all. And the one capture with a genuinely")
    print("    uncompressed anchor (Hard D0.20, -12.2 dB) shows an LF excess of only +0.25 dB.")
    print()


# ---------------------------------------------------------------- probe 5: the corrective shelf
def excess_db(cap, level, idx, i1k):
    """plugin - pedal at band `idx`, each side 1 kHz-normalised against its OWN 1 kHz band.

    POSITIVE means the plugin sits ABOVE the pedal there, so a corrector must CUT by this much.
    This is the ONE sign convention in this probe; the handover table in
    `.claude/plans/v1.4-fidelity.md` had it inverted relative to its own caption (see the
    SIGN note printed below), so both columns are labelled explicitly wherever it is reported.
    """
    fr = cap["fr"][level]
    return ((fr["plugin_db"][idx] - fr["plugin_db"][i1k])
            - (fr["pedal_db"][idx] - fr["pedal_db"][i1k]))


def shelf_response_db(f, gain_db, fp_hz):
    """1st-order low shelf: `gain_db` at DC, unity well above `fp_hz`. |H| in dB at f."""
    g = 10.0 ** (gain_db / 20.0)
    fz = g * fp_hz
    return 10.0 * math.log10((f * f + fz * fz) / (f * f + fp_hz * fp_hz))


def fit_low_shelf(freqs, target_db):
    """Least-squares (gain_db, fp_hz) of a 1st-order low shelf against `target_db`."""
    best = None
    for g10 in range(1, 121):
        gain = g10 / 10.0
        for fp2 in range(20, 3000, 2):
            fp = fp2 / 2.0
            err = sum((shelf_response_db(f, gain, fp) - t) ** 2
                      for f, t in zip(freqs, target_db))
            if best is None or err < best[0]:
                best = (err, gain, fp)
    err, gain, fp = best
    return gain, fp, math.sqrt(err / len(freqs))


def correction(data):
    print("=" * 96)
    print("PROBE 5 — the corrective low shelf: fit target, best static fit, and what it cannot fix")
    print("=" * 96)
    print(
        "Handover step 1 (`.claude/plans/v1.4-fidelity.md` W4): make the required-correction table\n"
        "reproducible instead of hand-run, then answer step 2 (DRIVE-gated vs level-gated) with a\n"
        "real fit. It answers step 2 in the NEGATIVE — see the VERDICT at the end.\n"
    )
    print("  SIGN CONVENTION (the handover table got this wrong — do not copy its numbers):")
    print("    'excess' = plugin - pedal, 1 kHz-normalised. POSITIVE = plugin is HOT there.")
    print("    A corrector must therefore CUT by +excess, i.e. its gain is -excess.")
    print("    The plan's table was already negated (it listed shelf targets) while its caption")
    print("    said 'plugin - pedal' AND 'negate to get the filter's target' — following it")
    print("    literally double-negates and yields a shelf that BOOSTS LF, doubling the error.\n")

    bands = data["meta"]["bands"]
    caps = data["captures"]
    i1k = band_index(bands, NORM_HZ)
    drives = sorted({c["settings"]["drive"] for c in caps})
    driven = [lv for lv in LEVELS if lv != "sweep_clean"]

    # ---- (1) the required-correction table, per level, median across captures at each DRIVE
    print("  " + "=" * 90)
    print("  (1) REQUIRED CORRECTION — median 'excess' (plugin-pedal) across captures at each DRIVE.")
    print("      Positive = plugin hot = corrector must cut. Clean sweep is anchor-contaminated")
    print("      (see probe 4 and block (3)); the driven sweeps are the ones to fit against.")
    for level in LEVELS:
        print(f"\n    --- {level} ({LEVEL_DBFS[level]:.0f} dBFS) " + "-" * 46)
        print(f"      {'Hz':>7} | " + "  ".join(f"D{d:.2f}" for d in drives))
        for hz in LF_HZ:
            idx = band_index(bands, hz)
            row = []
            for d in drives:
                vals = [excess_db(c, level, idx, i1k) for c in caps
                        if c["settings"]["drive"] == d and level in c["fr"]]
                row.append(st.median(vals) if vals else float("nan"))
            print(f"      {hz:7.1f} | " + "  ".join(f"{v:+5.2f}" for v in row))

    # ---- (2) is the excess LF-localised, or a broadband offset?
    print("\n  " + "=" * 90)
    print("  (2) IS IT A REAL SHAPE ERROR? An anchor-compression MISMATCH between plugin and pedal")
    print("      offsets EVERY band equally; a real LF shelf error decays to 0 in the midband.")
    print(f"\n      {'Hz':>8} | " + "  ".join(f"{lv.replace('sweep_', ''):>9}" for lv in LEVELS))
    print("      " + "-" * 52)
    for k, hz in enumerate(bands):
        if hz > 5200.0:
            continue  # above the SHAPE band the W3/W7 top-octave deficit takes over
        row = [st.median([excess_db(c, lv, k, i1k) for c in caps if lv in c["fr"]])
               for lv in LEVELS]
        tag = "  <- LF" if hz <= 110.0 else ("  <- anchor" if k == i1k else "")
        print(f"      {hz:8.1f} | " + "  ".join(f"{v:+9.2f}" for v in row) + tag)
    print("\n      READ: it decays monotonically to ~0 by 100-127 Hz and 127 Hz-1 kHz is flat within")
    print("      ~0.1 dB. So it is NOT a broadband anchor offset — it is a genuine LF shape error,")
    print("      and it IS in principle shelf-correctable. Blocks (3)-(5) are about whether that")
    print("      helps anything audible.")

    # ---- (3) anchor safety per level — the handover expected this backwards
    print("\n  " + "=" * 90)
    print("  (3) ANCHOR SAFETY per level. The handover guessed 'on the driven sweeps most SHOULD")
    print("      pass since the clamp is what the signal is meant to reach'. That is BACKWARDS:")
    print("      the driven sweeps are 12-24 dB HOTTER, so the 1 kHz anchor is further past the")
    print("      clamp, not nearer it. Verified here rather than assumed.")
    print(f"\n      {'level':>14} {'dBFS':>6} | {'anchor-safe captures':>21} | {'median overdrive':>17}")
    print("      " + "-" * 64)
    for level in LEVELS:
        v_in = KINPUT_REF * 10.0 ** (LEVEL_DBFS[level] / 20.0)
        od = []
        for c in caps:
            if level not in c["fr"]:
                continue
            s = c["settings"]
            od.append(20.0 * math.log10(
                stage1_lin_gain(NORM_HZ, s["bass"], s["drive"]) * v_in / CLAMP_V[c["rev"]]))
        safe = sum(1 for x in od if x < 0.0)
        print(f"      {level:>14} {LEVEL_DBFS[level]:6.0f} | {safe:>10}/{len(od):<10} |"
              f" {st.median(od):+17.2f} dB")
    print("\n      READ: 0/16 captures have an uncompressed 1 kHz anchor on ANY driven sweep. The")
    print("      driven sweeps are still the better fit target — not because the anchor is clean,")
    print("      but because block (2) shows the contamination is a flat offset that normalising")
    print("      removes, while the LF shape survives. Do NOT describe them as anchor-safe.")

    # ---- (4) best static shelf
    fit_freqs = [hz for hz in LF_HZ] + [127.0, 160.0]
    target = [st.median([excess_db(c, lv, band_index(bands, hz), i1k)
                         for c in caps for lv in driven if lv in c["fr"]])
              for hz in fit_freqs]
    gain, fp, rms = fit_low_shelf(fit_freqs, target)
    print("\n  " + "=" * 90)
    print("  (4) BEST STATIC 1st-ORDER LOW SHELF fitted to the driven-sweep median.")
    print(f"\n      cut of {gain:.2f} dB at DC, corner fp = {fp:.1f} Hz   (fit rms {rms:.3f} dB)")
    print(f"\n      {'Hz':>7} | {'target':>7} {'shelf':>7} {'resid':>7}")
    print("      " + "-" * 34)
    for hz, t in zip(fit_freqs, target):
        s = shelf_response_db(hz, gain, fp)
        print(f"      {hz:7.1f} | {t:+7.2f} {s:+7.2f} {t - s:+7.2f}")
    print(f"\n      The fit is excellent (rms {rms:.2f} dB) but look at WHERE it acts: the corner is")
    print(f"      {fp:.0f} Hz, so the cut is {shelf_response_db(20.0, gain, fp):.2f} dB at 20 Hz but only"
          f" {shelf_response_db(63.5, gain, fp):.2f} dB at 63 Hz")
    print(f"      and {shelf_response_db(100.8, gain, fp):.2f} dB at 100 Hz. Low E on a guitar is 82 Hz."
          " This is a RUMBLE TRIM,")
    print("      not a bass-tone correction.")

    # ---- (5) what it does to the metric that actually gates this
    print("\n  " + "=" * 90)
    print("  (5) EFFECT ON knob_tracking's SHAPE — the gate this work is judged by.")
    print(f"      SHAPE reads '{SHAPE_SWEEP}' ONLY, scores {[int(f) for f in SHAPE_FREQS]} Hz,")
    print(f"      tolerance +/-{SHAPE_TOL_DB} dB. Its lowest band is 60 Hz, and per probe 4 its")
    print("      normalisation anchor is itself compressed at D>=0.50. Deviations below are the")
    print("      LF ones only (the metric takes the max |dev| over all its bands, so its printed")
    print("      shapeDev can also come from the top octave).")
    print(f"\n      {'capture':>22} | {'60 Hz':>7} {'120 Hz':>7} | {'after shelf':>11} | verdict")
    print("      " + "-" * 74)
    n_fix = n_break = 0
    for c in sorted(caps, key=lambda c: (c["settings"]["drive"], c["rev"])):
        if SHAPE_SWEEP not in c["fr"]:
            continue
        s = c["settings"]
        e60 = excess_db(c, SHAPE_SWEEP, band_index(bands, 60.0), i1k)
        e120 = excess_db(c, SHAPE_SWEEP, band_index(bands, 120.0), i1k)
        worst = max((e60, 60.0), (e120, 120.0), key=lambda t: abs(t[0]))
        after = worst[0] - shelf_response_db(worst[1], gain, fp)
        was_fail = abs(worst[0]) > SHAPE_TOL_DB
        now_fail = abs(after) > SHAPE_TOL_DB
        verdict = "-"
        if was_fail and not now_fail:
            verdict, n_fix = "FIXED", n_fix + 1
        elif was_fail and now_fail:
            verdict = "still FAILS"
        elif abs(after) > abs(worst[0]) + 0.05:
            verdict = "worsened"
            if not was_fail and now_fail:
                verdict, n_break = "BROKEN", n_break + 1
        tag = f"{c['rev']:>6} B{s['bass']:.2f} D{s['drive']:.2f}"
        print(f"      {tag:>22} | {e60:+7.2f} {e120:+7.2f} | {after:+11.2f} | {verdict}")
    print(f"\n      SHAPE failures the static shelf fixes: {n_fix}; newly broken: {n_break}")

    # The harness caveat: the same failing settings measured on the DRIVEN sweeps.
    i60 = band_index(bands, 60.0)
    failing = [c for c in caps if SHAPE_SWEEP in c["fr"]
               and abs(excess_db(c, SHAPE_SWEEP, i60, i1k)) > SHAPE_TOL_DB]
    if failing:
        print("\n      HARNESS CAVEAT — the captures that fail at 60 Hz on the clean sweep, measured")
        print("      at the SAME setting on the driven sweeps. SHAPE never looks at these.")
        print(f"\n      {'capture':>22} | " + "  ".join(f"{lv.replace('sweep_', ''):>9}"
                                                       for lv in LEVELS))
        print("      " + "-" * 66)
        for c in failing:
            s = c["settings"]
            row = [excess_db(c, lv, i60, i1k) if lv in c["fr"] else float("nan") for lv in LEVELS]
            tag = f"{c['rev']:>6} B{s['bass']:.2f} D{s['drive']:.2f}"
            print(f"      {tag:>22} | " + "  ".join(f"{v:+9.2f}" for v in row))
        print(f"\n      Every one collapses inside the +/-{SHAPE_TOL_DB} dB tolerance as soon as the")
        print("      sweep is driven, and keeps shrinking with level. A real bass-network error would")
        print("      NOT be level-dependent like this — which is the third independent sign that this")
        print("      is clip-threshold behaviour, and that scoring SHAPE on 'sweep_clean' alone")
        print("      overstates it.")

    # ---- (6) the mode split the shelf cannot represent
    print("\n  " + "=" * 90)
    print("  (6) WHY NO STATIC SHELF CAN FIX THE FAILURES: at IDENTICAL (BASS, DRIVE) the required")
    print("      60 Hz cut is mode-dependent, and it orders by CLIP THRESHOLD (probe 4's anchor")
    print("      ordering Soft < Hard < Medium), not by anything in the bass network.")
    groups = {}
    for c in caps:
        groups.setdefault(group_key(c), []).append(c)
    print(f"\n      {'BASS':>5} {'DRIVE':>6} | " + "  ".join(f"{m:>7}" for m in MODE_ORDER)
          + " | spread")
    print("      " + "-" * 48)
    for key in sorted(groups):
        by_mode = {c["rev"]: c for c in groups[key]}
        if len(by_mode) < 3 or not all(SHAPE_SWEEP in c["fr"] for c in by_mode.values()):
            continue
        vals = [excess_db(by_mode[m], SHAPE_SWEEP, band_index(bands, 60.0), i1k) for m in MODE_ORDER]
        print(f"      {key[0]:5.2f} {key[1]:6.2f} | " + "  ".join(f"{v:+7.2f}" for v in vals)
              + f" | {max(vals) - min(vals):6.2f}")
    print("\n      A static shelf applies the SAME cut to every mode, so it cannot straddle a")
    print("      spread of this size. That is the same wall probe 1's lever hit, reached from the")
    print("      correction side instead of the mechanism side.")

    print("\n  " + "=" * 90)
    print("  VERDICT — W4 is NOT fixable as an empirical low shelf, for a NEW reason:")
    print("    * The mode-independent part IS cleanly fittable, but it is subsonic: a"
          f" {gain:.1f} dB/{fp:.0f} Hz")
    print(f"      shelf, i.e. {shelf_response_db(20.0, gain, fp):+.2f} dB at 20 Hz and only"
          f" {shelf_response_db(63.5, gain, fp):+.2f} dB at 60 Hz. Inaudible on guitar.")
    print("    * The LF SHAPE failures pull in OPPOSITE directions (one capture is ~1.6 dB DARK at")
    print("      120 Hz, two are ~2-3 dB HOT at 60 Hz), so one static shelf cannot correct both —")
    print("      it deepens the dark one while barely touching the hot ones.")
    print("    * The hot ones are mode-ordered at matched (BASS, DRIVE) per block (6), which makes")
    print("      them clip-threshold accuracy (W1/W2 territory), not a bass-network error.")
    print("    * The user's framing 'unlike W3 this only needs a filter to CUT' is right in")
    print("      principle; what defeats it is not the direction but that the needed cut is")
    print("      mode-dependent and, where mode-independent, subsonic.")
    print()


# ---------------------------------------------------------------- probe 6: the SHAPE metric itself
def shape_dev(cap, level, bands, i1k):
    """knob_tracking.py's shapeDev, recomputed on an arbitrary sweep.

    Returns (worst_abs_dev, worst_band_hz, signed_plugin_minus_pedal_at_that_band). knob_tracking
    scores max|(pedal_norm) - (plugin_norm)| over SHAPE_FREQS with each side normalised at its own
    1 kHz gain; this reproduces that on the 1/3-octave banded data to within ~0.1 dB (verified
    against the three known failures in probe 5).
    """
    fr = cap["fr"][level]
    worst = (-1.0, 0.0, 0.0)
    for hz in SHAPE_FREQS:
        i = band_index(bands, hz)
        signed = ((fr["plugin_db"][i] - fr["plugin_db"][i1k])
                  - (fr["pedal_db"][i] - fr["pedal_db"][i1k]))
        if abs(signed) > worst[0]:
            worst = (abs(signed), bands[i], signed)
    return worst


def metric(data):
    print("=" * 96)
    print("PROBE 6 — is the SHAPE gate's clean-sweep-only scoring what makes W4 look large?")
    print("=" * 96)
    print(
        "W4 lever 4. knob_tracking.py scores SHAPE on `sweep_clean` ALONE (check_one ->\n"
        "A.seg_of(orig, 'sweep_clean')), normalising each side at 1 kHz. Probe 4 showed that anchor\n"
        "is past the diode clamp at D >= 0.50 — exactly where the surviving LF failures live. This\n"
        "probe recomputes the SAME metric on all four sweeps, so a level-INDEPENDENT tone-stack\n"
        "error (which is what SHAPE claims to measure) can be separated from a level-DEPENDENT\n"
        "clipping artefact. Levers 1-3 would otherwise be fitted against a compromised target.\n"
    )

    print("    CAVEAT — this probe's PASS COUNTS are not the gate's. It scores 1/3-octave band")
    print("    energies from comprehensive_data.json; knob_tracking scores point gains from a csd")
    print("    transfer on a live render. They agree exactly on sweep_clean (12/16) and drv_-18")
    print("    (16/16) but diverge on the hot sweeps, where the top-octave band is steep and a")
    print("    1/3-octave integral reads a larger deviation than a point estimate:")
    print("        drv_-12: this probe 14/16 vs knob_tracking 16/16")
    print("        drv_-6 : this probe  8/16 vs knob_tracking 13/16")
    print("    Verified 2026-07-27 with `SIGNAL=v2 SHAPE_LEVELS=1 knob_tracking.py analysis/pedal2`.")
    print("    Use knob_tracking for COUNTS; use this probe for the per-capture level TREND, which")
    print("    is what the W4 conclusions rest on and which both agree about.\n")

    bands = data["meta"]["bands"]
    i1k = band_index(bands, NORM_HZ)
    v_full = KINPUT_REF

    rows = []
    for cap in data["captures"]:
        s = cap["settings"]
        b, d, m = s["bass"], s["drive"], cap["rev"]
        per = {}
        for lv in LEVELS:
            if lv not in cap["fr"]:
                continue
            dev, hz, signed = shape_dev(cap, lv, bands, i1k)
            v_in = v_full * 10.0 ** (LEVEL_DBFS[lv] / 20.0)
            over = 20.0 * math.log10(stage1_lin_gain(NORM_HZ, b, d) * v_in / CLAMP_V[m])
            per[lv] = (dev, hz, signed, over)
        rows.append((d, b, m, per))
    rows.sort()

    # --- per-capture table -----------------------------------------------------------------
    print(f"    shapeDev per sweep (gate is {SHAPE_TOL_DB} dB). '*' = fails that sweep.")
    print("    'worst band' is where the clean sweep peaks; it can differ per sweep.\n")
    hdr = "".join(f"{lv.replace('sweep_', ''):>12}" for lv in LEVELS)
    print(f"    {'DRIVE':>5} {'BASS':>5} {'mode':>7} |{hdr} | {'clean worst band':>16}")
    print("    " + "-" * 88)
    for d, b, m, per in rows:
        cells = ""
        for lv in LEVELS:
            if lv not in per:
                cells += f"{'-':>12}"
                continue
            dev = per[lv][0]
            cells += f"{dev:>10.2f}{'*' if dev > SHAPE_TOL_DB else ' '} "
        band = f"{per['sweep_clean'][1]:.0f} Hz" if "sweep_clean" in per else "-"
        print(f"    {d:5.2f} {b:5.2f} {m:>7} |{cells}| {band:>16}")

    print()
    print("    PASS COUNT BY WHICH SWEEP SHAPE IS SCORED ON:")
    for lv in LEVELS:
        ok = sum(1 for _, _, _, per in rows if lv in per and per[lv][0] <= SHAPE_TOL_DB)
        n = sum(1 for _, _, _, per in rows if lv in per)
        devs = sorted(per[lv][0] for _, _, _, per in rows if lv in per)
        med = st.median(devs)
        print(f"      {lv:>15}: {ok}/{n} pass   median shapeDev {med:.2f} dB   "
              f"worst {devs[-1]:.2f} dB")

    # --- level-independent floor ----------------------------------------------------------
    print()
    print("    LEVEL-INDEPENDENT FLOOR — a genuine tone-stack error cannot vanish when the signal")
    print("    gets louder, so min-across-sweeps bounds the part of shapeDev that is really tone:")
    print(f"      {'DRIVE':>5} {'BASS':>5} {'mode':>7} | {'clean':>8} {'min':>8} "
          f"{'at':>14} | {'clean-only inflation':>20}")
    print("    " + "-" * 82)
    infl = []
    for d, b, m, per in rows:
        if "sweep_clean" not in per:
            continue
        clean = per["sweep_clean"][0]
        best_lv = min(per, key=lambda lv: per[lv][0])
        mn = per[best_lv][0]
        infl.append(clean - mn)
        print(f"      {d:5.2f} {b:5.2f} {m:>7} | {clean:8.2f} {mn:8.2f} "
              f"{best_lv.replace('sweep_', ''):>14} | {clean - mn:+20.2f}")
    print()
    print(f"    median clean-only inflation: {st.median(infl):+.2f} dB   "
          f"max {max(infl):+.2f} dB")
    n_fail_any = sum(1 for _, _, _, per in rows
                     if min(per[lv][0] for lv in per) > SHAPE_TOL_DB)
    print(f"    captures failing SHAPE at EVERY level (i.e. level-independent): {n_fail_any}/{len(rows)}")

    # --- level trend of the three known failures ------------------------------------------
    print()
    print("    LEVEL TREND of the captures that fail on the clean sweep:")
    for d, b, m, per in rows:
        if "sweep_clean" not in per or per["sweep_clean"][0] <= SHAPE_TOL_DB:
            continue
        print(f"      D{d:.2f} B{b:.2f} {m:>7}: ", end="")
        parts = []
        for lv in LEVELS:
            if lv in per:
                dev, hz, signed, over = per[lv]
                parts.append(f"{lv.replace('sweep_', '')} {signed:+.2f}@{hz:.0f}Hz"
                             f" (anchor {over:+.0f})")
        print("  ".join(parts))

    print()
    print("    READ THE ANCHOR COLUMN: it gets WORSE on the driven sweeps (they are 12-24 dB hotter")
    print("    than the clean one), so 'driven sweeps are anchor-safe' is FALSE. What makes them the")
    print("    better reference is that both sides are then compressed roughly in step, so the")
    print("    DIFFERENTIAL is closer to a true shape error — not that the anchor is clean.")
    print()


# ------------------------------------------------- probe 7: mode-independent vs mode-dependent
def decompose(data):
    print("=" * 96)
    print("PROBE 7 — split the LF deviation into a TAPER-shaped part and a CLIP-shaped part")
    print("=" * 96)
    print(
        "This is the test that decides W4 lever 1 (BASS taper shape between x=0.50 and 0.65).\n"
        "The BASS network (R3/C3/C4/pot) is LINEAR and sits upstream of SW1, so a taper-shape error\n"
        "must be MODE-INDEPENDENT: identical for Soft/Medium/Hard at matched (BASS, DRIVE). A clip\n"
        "threshold/onset error must be MODE-DEPENDENT. At each matched group this probe therefore\n"
        "splits the signed LF deviation into:\n"
        "    mode-independent = mean over the three modes   -> candidate taper / EQ error\n"
        "    mode-dependent   = max - min over the modes    -> clip threshold error\n"
        "Second discriminator: a linear taper error is also LEVEL-independent in its\n"
        "mode-independent part, because a linear filter does not know how loud the signal is.\n"
        "(Clipping can MASK it at high level by saturating both sides, so level-dependence alone\n"
        "does not refute a taper error — but level-INdependence would strongly support one.)\n"
        "Sign convention throughout: POSITIVE = plugin hotter than pedal, 1 kHz-normalised.\n"
    )

    bands = data["meta"]["bands"]
    i1k = band_index(bands, NORM_HZ)
    lf_bands = [60.0, 120.0]

    groups = {}
    for cap in data["captures"]:
        groups.setdefault(group_key(cap), []).append(cap)

    for hz in lf_bands:
        i = band_index(bands, hz)
        print(f"    --- {bands[i]:.0f} Hz band " + "-" * 62)
        print(f"      {'BASS':>5} {'DRIVE':>5} {'level':>9} | {'Soft':>7} {'Medium':>7} "
              f"{'Hard':>7} | {'mode-indep':>11} {'mode-dep':>9}")
        print("      " + "-" * 76)
        for key in sorted(groups, key=lambda k: (k[1], k[0])):
            by_mode = {c["rev"]: c for c in groups[key]}
            if len(by_mode) < 3:
                continue
            b, d = key
            for lv in LEVELS:
                if not all(lv in c["fr"] for c in by_mode.values()):
                    continue
                vals = {}
                for m in MODE_ORDER:
                    fr = by_mode[m]["fr"][lv]
                    vals[m] = ((fr["plugin_db"][i] - fr["plugin_db"][i1k])
                               - (fr["pedal_db"][i] - fr["pedal_db"][i1k]))
                mi = st.mean(vals.values())
                md = max(vals.values()) - min(vals.values())
                print(f"      {b:5.2f} {d:5.2f} {lv.replace('sweep_', ''):>9} | "
                      f"{vals['Soft']:+7.2f} {vals['Medium']:+7.2f} {vals['Hard']:+7.2f} | "
                      f"{mi:+11.2f} {md:9.2f}")
            print()

    # --- summary: how big is each part, and is the taper-shaped part level-stable? ----------
    print("    SUMMARY — is there a coherent taper-shaped error?")
    print(f"      {'band':>7} {'BASS':>5} {'DRIVE':>5} | mode-indep by level "
          f"(clean / -18 / -12 / -6) | {'level spread':>12}")
    print("      " + "-" * 84)
    taper_evidence = []
    for hz in lf_bands:
        i = band_index(bands, hz)
        for key in sorted(groups, key=lambda k: (k[1], k[0])):
            by_mode = {c["rev"]: c for c in groups[key]}
            if len(by_mode) < 3:
                continue
            b, d = key
            per_lv = {}
            for lv in LEVELS:
                if not all(lv in c["fr"] for c in by_mode.values()):
                    continue
                vals = []
                for m in MODE_ORDER:
                    fr = by_mode[m]["fr"][lv]
                    vals.append((fr["plugin_db"][i] - fr["plugin_db"][i1k])
                                - (fr["pedal_db"][i] - fr["pedal_db"][i1k]))
                per_lv[lv] = st.mean(vals)
            if len(per_lv) < 2:
                continue
            spread_lv = max(per_lv.values()) - min(per_lv.values())
            cells = "  ".join(f"{per_lv.get(lv, float('nan')):+6.2f}" for lv in LEVELS)
            print(f"      {bands[i]:7.0f} {b:5.2f} {d:5.2f} | {cells} | {spread_lv:12.2f}")
            taper_evidence.append((bands[i], b, d, per_lv, spread_lv))
    print()
    print("      A taper error would show a LEVEL-STABLE mode-independent column (small level")
    print("      spread) with a sign that flips between BASS=0.50 and BASS=0.65 (needing a steeper")
    print("      taper through that range). Read the level-spread column: if it is comparable to or")
    print("      larger than the mode-independent values themselves, the deviation is dominated by")
    print("      level-dependent behaviour and a static taper refit cannot be fitted to it.")
    print()
    med_spread = st.median(t[4] for t in taper_evidence)
    med_abs_mi = st.median(abs(v) for t in taper_evidence for v in t[3].values())
    print(f"      median level spread of the mode-independent part: {med_spread:.2f} dB")
    print(f"      median |mode-independent| value:                  {med_abs_mi:.2f} dB")
    print()


# ------------------------------------------------- probe 8: the knob-keyed shelf's CEILING
def _best_static_shelf(dev_by_level):
    """Minimax (gain_db, fp_hz) for ONE static shelf against a setting's deviation at every level.

    dev_by_level: {level: {hz: signed plugin-pedal dB}}. Returns (gain, fp, worst_residual,
    worst_uncorrected). Grid search covers BOTH signs — some settings need a cut, some a boost.
    """
    best = None
    for g10 in range(-60, 61):
        gain = g10 / 10.0
        for fp in (40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500):
            worst = 0.0
            for lv, per_hz in dev_by_level.items():
                for hz, d in per_hz.items():
                    worst = max(worst, abs(d - shelf_response_db(hz, gain, fp)))
            if best is None or worst < best[2]:
                best = (gain, fp, worst)
    raw = max(abs(d) for per_hz in dev_by_level.values() for d in per_hz.values())
    return best[0], best[1], best[2], raw


def knobshelf(data):
    print("=" * 96)
    print("PROBE 8 — CEILING on a knob-keyed corrective shelf (the user's proposal, measured)")
    print("=" * 96)
    print(
        "Probes 1-7 argued about MECHANISM. This one ignores mechanism and asks the only question\n"
        "that decides whether to ship a correction: how much of the error can a shelf REMOVE?\n"
        "\n"
        "Two earlier arguments are retracted here and must not be reused:\n"
        "  * 'a shelf is mode-independent by construction' (probe 5 / lever 2) — FALSE. SW1 position\n"
        "    is a knob the plugin knows, so a shelf keyed on (BASS, DRIVE, mode) is mode-dependent.\n"
        "  * 'the error collapses with level, so it is not a linear taper error' (lever 1) — FALSE.\n"
        "    Clipping MASKS a linear error at high level, because both sides pin to the clip\n"
        "    ceiling. Level-collapse is exactly what a masked linear LF error looks like.\n"
        "\n"
        "This probe fits ONE static 1st-order low shelf per capture, i.e. per exact (BASS, DRIVE,\n"
        "mode) setting, chosen minimax over all four sweep levels and all SHAPE bands. That is an\n"
        "ORACLE BOUND, not a shippable filter: a real knob-keyed shelf must INTERPOLATE, and pedal2\n"
        "samples only 5 distinct (BASS, DRIVE) points. No achievable shelf can beat this table.\n"
        "The residual column is therefore the honest answer to 'why not just shelve it?'.\n"
    )

    bands = data["meta"]["bands"]
    i1k = band_index(bands, NORM_HZ)

    rows = []
    for cap in data["captures"]:
        s = cap["settings"]
        b, d, m = s["bass"], s["drive"], cap["rev"]
        dev = {}
        for lv in LEVELS:
            if lv not in cap["fr"]:
                continue
            fr = cap["fr"][lv]
            dev[lv] = {}
            for hz in SHAPE_FREQS:
                i = band_index(bands, hz)
                dev[lv][bands[i]] = ((fr["plugin_db"][i] - fr["plugin_db"][i1k])
                                     - (fr["pedal_db"][i] - fr["pedal_db"][i1k]))
        gain, fp, resid, raw = _best_static_shelf(dev)
        rows.append((d, b, m, gain, fp, resid, raw, dev))
    rows.sort()

    print(f"    {'DRIVE':>5} {'BASS':>5} {'mode':>7} | {'shelf gain':>10} {'corner':>7} | "
          f"{'worst NOW':>9} {'worst AFTER':>11} | {'gained':>7}")
    print("    " + "-" * 82)
    for d, b, m, gain, fp, resid, raw, _ in rows:
        flag = ""
        if raw > SHAPE_TOL_DB and resid <= SHAPE_TOL_DB:
            flag = "  FIXES"
        elif raw > SHAPE_TOL_DB:
            flag = "  still fails"
        print(f"    {d:5.2f} {b:5.2f} {m:>7} | {gain:+10.1f} {fp:7.0f} | "
              f"{raw:9.2f} {resid:11.2f} | {raw - resid:+7.2f}{flag}")

    now_ok = sum(1 for r in rows if r[6] <= SHAPE_TOL_DB)
    aft_ok = sum(1 for r in rows if r[5] <= SHAPE_TOL_DB)
    print()
    print(f"    worst-of-all-levels SHAPE:  now {now_ok}/{len(rows)} pass  ->  "
          f"with an ORACLE per-setting shelf {aft_ok}/{len(rows)} pass")
    print(f"    median worst-case deviation: {st.median(r[6] for r in rows):.2f} dB  ->  "
          f"{st.median(r[5] for r in rows):.2f} dB")
    print()
    print("    ^ READ THIS CAREFULLY. Most '+0.00 gained' rows are NOT rows where the bass is")
    print("      already right — they are rows whose WORST band is 8128 Hz, i.e. W3's top-octave")
    print("      deficit, which no low shelf can reach. The all-band minimax above is therefore")
    print("      dominated by W3 and UNDERSTATES what an LF correction does to the bass.")

    # --- the same question restricted to the bands a low shelf can actually act on -----------
    lf_only = [f for f in SHAPE_FREQS if f <= 250]
    print()
    print(f"    LF-ONLY view — same oracle shelf, scored on {lf_only} Hz (what W4 is about):")
    print(f"      {'DRIVE':>5} {'BASS':>5} {'mode':>7} | {'gain':>6} {'corner':>7} | "
          f"{'worst NOW':>9} {'worst AFTER':>11}")
    print("      " + "-" * 66)
    now_lf, aft_lf = [], []
    for d, b, m, _, _, _, _, dev in rows:
        sub = {lv: {hz: v for hz, v in per.items() if hz <= 250.0} for lv, per in dev.items()}
        gain, fp, resid, raw = _best_static_shelf(sub)
        now_lf.append(raw)
        aft_lf.append(resid)
        print(f"      {d:5.2f} {b:5.2f} {m:>7} | {gain:+6.1f} {fp:7.0f} | "
              f"{raw:9.2f} {resid:11.2f}")
    print()
    print(f"      worst LF deviation: median {st.median(now_lf):.2f} -> "
          f"{st.median(aft_lf):.2f} dB, max {max(now_lf):.2f} -> {max(aft_lf):.2f} dB")
    print(f"      settings over {SHAPE_TOL_DB} dB in the bass: "
          f"{sum(1 for v in now_lf if v > SHAPE_TOL_DB)} -> "
          f"{sum(1 for v in aft_lf if v > SHAPE_TOL_DB)}")
    print("      THIS is the honest measure of the proposal: a knob-keyed shelf DOES fix most of")
    print("      the bass error. It just cannot move the SHAPE gate much, because at driven levels")
    print("      that gate is scoring W3's top octave, not W4's bass.")

    # --- feasibility: the per-setting corners above scatter 40..500 Hz, which means the fit is
    # underdetermined. A SHIPPABLE filter needs ONE fixed shape with only the gain keyed to knobs
    # (that is how DriveTilt/TopOctaveRestore are built). Does that survive?
    print()
    print("    FEASIBILITY — one FIXED corner, gain the only knob-keyed term (DriveTilt's shape):")
    print(f"      {'corner':>7} | {'median resid':>12} {'max resid':>10} | {'over 1.5 dB':>11}")
    print("      " + "-" * 48)
    best_fixed = None
    for fp in (40, 63, 80, 100, 125, 160, 200, 250, 315, 400):
        resids = []
        for d, b, m, _, _, _, _, dev in rows:
            sub = {lv: {hz: v for hz, v in per.items() if hz <= 250.0}
                   for lv, per in dev.items()}
            best = None
            for g10 in range(-60, 61):
                gain = g10 / 10.0
                worst = max(abs(v - shelf_response_db(hz, gain, fp))
                            for per in sub.values() for hz, v in per.items())
                if best is None or worst < best:
                    best = worst
            resids.append(best)
        over = sum(1 for v in resids if v > SHAPE_TOL_DB)
        med, mx = st.median(resids), max(resids)
        if best_fixed is None or med < best_fixed[1]:
            best_fixed = (fp, med, mx, over)
        print(f"      {fp:7.0f} | {med:12.2f} {mx:10.2f} | {over:11d}")
    fp, med, mx, over = best_fixed
    print()
    print(f"      BEST FIXED CORNER: {fp:.0f} Hz — median residual {med:.2f} dB, max {mx:.2f} dB, "
          f"{over} setting(s) still over {SHAPE_TOL_DB} dB.")
    print("      Compare the free-corner oracle above: the fixed-shape version gives up very"
          " little,")
    print("      so the scattered corners were fit noise, not a real per-setting shape difference.")
    print("      => A single low-shelf SHAPE with a knob-keyed GAIN is the right form factor.")
    print()
    # The design deliverable: the CORRECTION gain per setting at the chosen fixed corner.
    print()
    print(f"      GAIN TABLE at fc = {fp:.0f} Hz. SIGN IS THE CORRECTION THE SHELF APPLIES")
    print("      (negative = cut the plugin's bass). This is the NEGATIVE of the measured")
    print("      plugin-pedal deviation — the plan's old handover table inverted exactly this and")
    print("      would have doubled the error. Do not re-derive the sign; use this column.")
    print(f"      {'BASS':>5} {'DRIVE':>5} | {'Soft':>7} {'Medium':>7} {'Hard':>7}")
    print("      " + "-" * 40)
    by_bd = {}
    for d, b, m, _, _, _, _, dev in rows:
        sub = {lv: {hz: v for hz, v in per.items() if hz <= 250.0} for lv, per in dev.items()}
        best = None
        for g10 in range(-60, 61):
            gain = g10 / 10.0
            worst = max(abs(v - shelf_response_db(hz, gain, fp))
                        for per in sub.values() for hz, v in per.items())
            if best is None or worst < best[1]:
                best = (gain, worst)
        by_bd.setdefault((b, d), {})[m] = -best[0]  # negate: measured deviation -> correction
    for (b, d) in sorted(by_bd, key=lambda k: (k[0], k[1])):
        g = by_bd[(b, d)]
        cells = "".join(f"{g[m]:+7.1f}" if m in g else f"{'-':>7}" for m in MODE_ORDER)
        print(f"      {b:5.2f} {d:5.2f} |{cells}")
    print()
    print("      Note the sign flip along the captured diagonal: BOOST at (B0.50, low DRIVE),")
    print("      CUT at (B0.65, high DRIVE). That is the see-saw, and a knob-keyed shelf handles")
    print("      it precisely BECAUSE it is keyed on the knobs — no de-confounding required.")
    print()
    print("      REMAINING RISK, and it is the real one: pedal2 samples only 5 distinct (BASS,")
    print("      DRIVE) points and they are perfectly CONFOUNDED (B steps 0.50->0.65 exactly when")
    print("      D steps 0.50->0.65). The gain table above is therefore 5 points on a diagonal")
    print("      through a 2-D knob space. Interpolating along that diagonal is defensible;")
    print("      extrapolating OFF it (high BASS + low DRIVE, or low BASS + high DRIVE) is")
    print("      unconstrained by any capture, and W6 means no capture can ever constrain it.")
    print()

    # --- why a static per-setting shelf cannot go further: the level spread it must straddle ---
    print()
    print("    WHY THE RESIDUAL DOES NOT GO TO ZERO — the ideal shelf is different at each level.")
    print("    Per setting, the 64 Hz deviation the ONE shelf has to straddle:")
    print(f"      {'DRIVE':>5} {'BASS':>5} {'mode':>7} | "
          + "".join(f"{lv.replace('sweep_', ''):>9}" for lv in LEVELS)
          + f" | {'half-range':>10}")
    print("    " + "-" * 78)
    halves = []
    for d, b, m, _, _, _, _, dev in rows:
        vals = [dev[lv].get(63.5) for lv in LEVELS if lv in dev]
        vals = [v for v in vals if v is not None]
        if not vals:
            continue
        half = (max(vals) - min(vals)) / 2.0
        halves.append(half)
        print(f"      {d:5.2f} {b:5.2f} {m:>7} | "
              + "".join(f"{v:+9.2f}" for v in vals) + f" | {half:10.2f}")
    print()
    print(f"    median half-range across levels: {st.median(halves):.2f} dB, max {max(halves):.2f} dB")
    print("    A static shelf can at best sit in the middle of each row, so the half-range IS its")
    print("    irreducible error. Removing it needs the shelf to follow SIGNAL LEVEL, i.e. an")
    print("    envelope follower — the plugin has no level detector (DriveTilt keys off the DRIVE")
    print("    POT, not the signal), so that is a dynamics feature, not a filter re-tune.")
    print()


PROBES = {"spread": spread, "order": order, "anchor": anchor, "shelf": shelf,
          "correction": correction, "metric": metric, "decompose": decompose,
          "knobshelf": knobshelf}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma-separated subset of: " + ",".join(PROBES))
    args = ap.parse_args()

    wanted = [p.strip() for p in args.only.split(",") if p.strip()] or list(PROBES)
    for p in wanted:
        if p not in PROBES:
            sys.exit(f"unknown probe '{p}' (have: {', '.join(PROBES)})")

    data = load_json()
    print(f"\nsource: {JSON_PATH}")
    print(f"generated: {data['meta']['generated']}  os_factor={data['meta']['os_factor']}"
          f"  n={data['meta']['num_captures']}\n")
    for p in wanted:
        PROBES[p](data)


if __name__ == "__main__":
    main()
