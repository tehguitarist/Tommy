"""v1.4 W3 — characterise the high-drive top-octave deficit vs pedal2.

Answers the four questions the W3 work item needed settled before any DSP change, each with a
metric chosen so it cannot be confused with the others:

  1. Is the "onset at DRIVE >= 0.65" actually DRIVE, or the confounded TREBLE/BASS knob change?
     -> `confound()`. pedal2 moves T 0.20->0.35 and B 0.50->0.65 at exactly the same point as
        D 0.50->0.65, so the headline finding is confounded. One capture breaks the tie.
  2. Is the deficit a LINEAR filter error or CLIPPING-mediated?
     -> `compression()`. Splits the 1 kHz-normalised FR error into the part present on the clean
        sweep (linear) and the part that only appears as level rises (clip-mediated).
  3. Is the Farina-extracted FR trustworthy this high up, at this much distortion?
     -> `validate_metric()`. Renders steady fixed tones through the real DSP and compares the
        compression they measure against what the swept-sine pipeline reports for the same setting.
  4. Is the deficit real ENERGY, or an artefact of separating fundamental from harmonics?
     -> `band_energy()`. Total in-band energy (fundamental + every distortion product), so no
        deconvolution is involved at all.

Usage (from the repo root):
    analysis/.venv/bin/python3 analysis/w3_topoctave.py [--only confound,compression,...]

Needs analysis/reports/comprehensive_data.json (regenerate with comprehensive_report.py) for
questions 1-3, and build/OfflineRender_artefacts/Release/OfflineRender for questions 3-4.
"""

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import statistics as st

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import analyze as A  # noqa: E402
import captures as C  # noqa: E402

# pedal2 is the v2-signal batch; only it has the three driven-sweep depths this needs.
A.use_layout("v2")

SR = 48000.0
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(REPO, "analysis/reports/comprehensive_data.json")
RENDER = os.path.join(REPO, "build/OfflineRender_artefacts/Release/OfflineRender")
SIGNAL = os.path.join(REPO, "analysis/tommy_test_signal_v2_48k.wav")
PEDAL2 = os.path.join(REPO, "analysis/pedal2")

# The top-octave bands the deficit lives in, plus midband anchors for contrast.
SHOW_HZ = [4063.7, 5120.0, 6450.8, 8127.5, 10240.0, 12901.6]
LEVELS = ["sweep_clean", "sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6"]
# DRIVE >= this counts as "high drive" — the reported onset point.
HI_DRIVE = 0.65


def load_json():
    with open(JSON_PATH) as f:
        return json.load(f)


def norm_delta(cap, level, bands, i1k):
    """plugin - pedal, 1 kHz-normalised: the honest FR *shape* error (drops the arbitrary
    least-squares level match `gain_db_applied` that the raw delta carries)."""
    fr = cap["fr"][level]
    raw = [p - q for p, q in zip(fr["plugin_db"], fr["pedal_db"])]
    return [r - raw[i1k] for r in raw]


def compression_of(cap, who, level, bands, i1k):
    """1 kHz-normalised (level - clean) for one side. Isolates what CLIPPING does to the
    top octave from the linear response, because the clean sweep is subtracted out."""
    a, b = cap["fr"][level][who], cap["fr"]["sweep_clean"][who]
    return [(a[i] - a[i1k]) - (b[i] - b[i1k]) for i in range(len(bands))]


def _hdr(cols, w=10):
    return "".join(f"{c:>{w}}" for c in cols)


def confound():
    """Q1: DRIVE or TREBLE? pedal2 raises TREBLE 0.20->0.35 and BASS 0.50->0.65 at the same
    step as DRIVE 0.50->0.65, so "onset at D>=0.65" is confounded three ways.

    `Medium D0.65` is the one capture that breaks it: D0.65 but TREBLE still at 0.20. If the
    tilt were a TREBLE-taper error it should be absent there; if DRIVE, present.

    BASS is excluded analytically, not statistically: BASS_R sits in Zg behind C3 (39n), whose
    impedance is ~400 ohm at 10 kHz, so C3 shorts node_X and BASS cannot move the top octave.
    """
    d = load_json()
    bands, caps = d["meta"]["bands"], d["captures"]
    i1k, idx = bands.index(1015.9), [bands.index(f) for f in SHOW_HZ]
    print("=" * 92)
    print("Q1  Is the D>=0.65 onset really DRIVE? (TREBLE and BASS step at the same point)")
    print("=" * 92)

    for level in ("sweep_clean", "sweep_drv_-6"):
        print(f"\n  {level} — 1 kHz-normalised FR error, dB (plugin - pedal)")
        print(f"    {'capture':<30}{'D':>5}{'T':>5}  " + _hdr([f"{f/1000:.1f}k" for f in SHOW_HZ], 9))
        for c in sorted(caps, key=lambda c: (c["settings"]["treble"], c["settings"]["drive"])):
            v, s = norm_delta(c, level, bands, i1k), c["settings"]
            print(f"    {c['id'][:30]:<30}{s['drive']:>5.2f}{s['treble']:>5.2f}  "
                  + _hdr([f"{v[i]:+.2f}" for i in idx], 9))

    print("\n  The tie-breaker — all three D0.65 captures, sweep_drv_-6:")
    print(f"    {'capture':<30}{'T':>5}  " + _hdr([f"{f/1000:.1f}k" for f in SHOW_HZ], 9))
    for c in caps:
        if abs(c["settings"]["drive"] - 0.65) < 1e-9:
            v = norm_delta(c, "sweep_drv_-6", bands, i1k)
            print(f"    {c['id'][:30]:<30}{c['settings']['treble']:>5.2f}  "
                  + _hdr([f"{v[i]:+.2f}" for i in idx], 9))
    print("\n  Read: the T=0.20 capture at D0.65 carries the tilt too (in fact slightly more),")
    print("  and every T=0.20 capture at D<=0.50 is clean. The onset tracks DRIVE, not TREBLE.")


def compression():
    """Q2: linear or clipping-mediated? Splits the error in two.

    The clean sweep (-30 dBFS) is essentially unclipped, so any error there is a LINEAR filter
    error and a fixed shelf can correct it. Anything that only appears as level rises is
    clipping-mediated: a level-independent shelf cannot fix it, and one fitted at -6 dBFS would
    over-brighten the clean case by the difference.
    """
    d = load_json()
    bands, caps = d["meta"]["bands"], d["captures"]
    i1k, idx = bands.index(1015.9), [bands.index(f) for f in SHOW_HZ]
    print("\n" + "=" * 92)
    print("Q2  Linear filter error, or clipping-mediated?")
    print("=" * 92)

    for name, sel in (("HIGH drive D>=%.2f" % HI_DRIVE, lambda s: s["drive"] >= HI_DRIVE),
                      ("LOW  drive D<%.2f" % HI_DRIVE, lambda s: s["drive"] < HI_DRIVE)):
        g = [c for c in caps if sel(c["settings"])]
        print(f"\n  {name} (n={len(g)}) — median 1 kHz-normalised FR error, dB")
        print(f"    {'level':<16}" + _hdr([f"{f/1000:.1f}k" for f in SHOW_HZ]))
        for level in LEVELS:
            m = [st.median([norm_delta(c, level, bands, i1k)[i] for c in g]) for i in idx]
            print(f"    {level:<16}" + _hdr([f"{v:+.2f}" for v in m]))

        print(f"\n  {name} — COMPRESSION (level - clean), 1 kHz-normalised, dB")
        print(f"    {'level':<10}{'side':<9}" + _hdr([f"{f/1000:.1f}k" for f in SHOW_HZ]))
        for level in LEVELS[1:]:
            for who in ("pedal_db", "plugin_db"):
                m = [st.median([compression_of(c, who, level, bands, i1k)[i] for c in g]) for i in idx]
                print(f"    {level.replace('sweep_',''):<10}{who[:-3]:<9}" + _hdr([f"{v:+.2f}" for v in m]))
            ex = [st.median([compression_of(c, "plugin_db", level, bands, i1k)[i]
                             - compression_of(c, "pedal_db", level, bands, i1k)[i] for c in g])
                  for i in idx]
            print(f"    {'':<10}{'EXCESS':<9}" + _hdr([f"{v:+.2f}" for v in ex]))


def _render_raw(x, args, tmp):
    """Push a raw float32 buffer through the real DSP chain + PluginProcessor gain staging."""
    fin, fout = os.path.join(tmp, "i.f32"), os.path.join(tmp, "o.f32")
    x.astype("<f4").tofile(fin)
    subprocess.run([RENDER, fin, fout] + [str(a) for a in args],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return np.fromfile(fout, dtype="<f4")


def _fund_db(y, f):
    """Magnitude of the fundamental over the steady-state second half (windowed DFT bin at f)."""
    seg = y[len(y) // 2:]
    t = np.arange(len(seg)) / SR
    w = np.hanning(len(seg))
    c = np.sum(seg * w * np.exp(-2j * np.pi * f * t)) / np.sum(w) * 2
    return 20 * math.log10(max(abs(c), 1e-12))


def validate_metric():
    """Q3: can the Farina-extracted FR be trusted at 8-13 kHz with this much distortion?

    Renders steady fixed tones through the same DSP and measures the same compression directly.
    If the two disagree, the swept-sine numbers are an extraction artefact and nothing should be
    fitted to them. Plugin-side only — that is the point: it validates the instrument.
    """
    d = load_json()
    bands, i1k = d["meta"]["bands"], d["meta"]["bands"].index(1015.9)
    byid = {c["id"]: c for c in d["captures"]}
    tmp = tempfile.mkdtemp()
    freqs = [1000.0] + [f for f in SHOW_HZ]
    print("\n" + "=" * 92)
    print("Q3  Is the Farina-extracted FR trustworthy up here? (tone probe vs swept sine)")
    print("=" * 92)

    # (json id, bass, drive, treble, volume, modeIdx) — modeIdx 0=Hard 1=Medium 2=Soft
    for cid, bass, drive, treb, vol, mode in (
            ("Soft D1.00 B0.65 T0.35 V0.50", 0.65, 1.00, 0.35, 0.50, 2),
            ("Hard D1.00 B0.65 T0.35 V0.50", 0.65, 1.00, 0.35, 0.50, 0),
            ("Soft D0.50 B0.50 T0.20 V0.50", 0.50, 0.50, 0.20, 0.50, 2)):
        g = {}
        for tag, dbfs in (("clean", -30.0), ("drv", -6.0)):
            amp = 10 ** (dbfs / 20)
            for f in freqs:
                t = np.arange(int(SR)) / SR
                y = _render_raw(amp * np.sin(2 * np.pi * f * t),
                                [bass, drive, treb, vol, mode, 3, SR], tmp)
                g[(tag, f)] = _fund_db(y, f)
        base = g[("drv", 1000.0)] - g[("clean", 1000.0)]
        cap = byid.get(cid)
        print(f"\n  {cid}")
        print(f"    {'freq':>9}{'tone probe':>13}{'swept sine':>13}{'diff':>9}")
        for f in SHOW_HZ:
            tone = (g[("drv", f)] - g[("clean", f)]) - base
            sw = diff = ""
            if cap and f in bands:
                j = bands.index(f)
                p6, pc = cap["fr"]["sweep_drv_-6"]["plugin_db"], cap["fr"]["sweep_clean"]["plugin_db"]
                v = (p6[j] - p6[i1k]) - (pc[j] - pc[i1k])
                sw, diff = f"{v:+.2f}", f"{tone - v:+.2f}"
            print(f"    {f:>9.1f}{tone:>+13.2f}{sw:>13}{diff:>9}")


def _band_energy_db(x, lo, hi):
    """Total energy in [lo,hi) — fundamental AND every distortion product. No deconvolution."""
    X = np.fft.rfft(x * np.hanning(len(x)))
    f = np.fft.rfftfreq(len(x), 1 / SR)
    m = (f >= lo) & (f < hi)
    return 10 * math.log10(max(float(np.sum(np.abs(X[m]) ** 2)), 1e-30))


def band_energy():
    """Q4: is the deficit real energy? Compares TOTAL in-band energy, pedal vs plugin, each
    normalised on its own 200 Hz-2 kHz content so the broadband level match cannot leak in.

    This is the check that decides whether anything needs fixing at all: if the deficit survives
    here it is real missing energy, not an artefact of splitting fundamental from harmonics.
    """
    orig = A.load(SIGNAL)
    tmp = tempfile.mkdtemp()
    orig_f32 = os.path.join(tmp, "orig.f32")
    orig.astype("<f4").tofile(orig_f32)
    out = os.path.join(tmp, "o.f32")
    bands = [(200, 2000), (2000, 4000), (4000, 7000), (7000, 11000), (11000, 16000)]
    print("\n" + "=" * 92)
    print("Q4  Is it real energy? (total in-band energy, no Farina extraction)")
    print("=" * 92)

    for fn in ("V1200 B1330 T1030 G1700 switch down tommy_test_signal_48k.wav",   # Soft   D1.00
               "V1200 B1330 T1030 G1700 switch up tommy_test_signal_48k.wav",     # Hard   D1.00
               "V1200 B1200 T0900 G1200 switch down tommy_test_signal_48k.wav"):  # Soft   D0.50
        path = os.path.join(PEDAL2, fn)
        parsed = C.parse_capture(path)
        cap_al, _ = A.align(A.load(path), orig)
        subprocess.run([RENDER, orig_f32, out]
                       + [str(a) for a in C.render_args(parsed, os_factor_log2=3)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ren_al, _ = A.align(np.fromfile(out, dtype="<f4"), orig)
        print(f"\n  {fn[:56]}\n  drive={parsed.get('drive')} mode={parsed.get('mode')}")
        for sw in ("sweep_clean", "sweep_drv_-6"):
            cs = A.seg_of(cap_al, sw)
            rs = A.frac_align(A.seg_of(ren_al, sw), cs)
            rc, rr = _band_energy_db(cs, 200, 2000), _band_energy_db(rs, 200, 2000)
            print(f"    {sw}   (dB re each side's own 200 Hz-2 kHz energy)")
            print(f"      {'band':<12}{'pedal':>9}{'plugin':>9}{'plug-ped':>10}")
            for lo, hi in bands:
                pc = _band_energy_db(cs, lo, hi) - rc
                pr = _band_energy_db(rs, lo, hi) - rr
                lbl = f"{lo//1000 if lo >= 1000 else lo}-{hi//1000}k"
                print(f"      {lbl:<12}{pc:>+9.2f}{pr:>+9.2f}{pr-pc:>+10.2f}")


STEPS = {"confound": confound, "compression": compression,
         "metric": validate_metric, "energy": band_energy}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=None,
                    help="comma-separated subset of: " + ",".join(STEPS))
    a = ap.parse_args()
    names = [s.strip() for s in a.only.split(",")] if a.only else list(STEPS)
    for n in names:
        if n not in STEPS:
            sys.exit(f"unknown step {n!r}; choose from {','.join(STEPS)}")
        STEPS[n]()


if __name__ == "__main__":
    main()
