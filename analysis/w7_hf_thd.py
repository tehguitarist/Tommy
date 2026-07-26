"""v1.4 W7 — is the plugin genuinely THD-light at 6.3-8 kHz, or is that a measurement artefact?

The user's ear flagged the plugin as light on distortion in the 6.3-8 kHz region. §2.5 of the
v1.4 plan reported a 10-20x shortfall there (pedal 1.49%/2.16% vs plugin 0.11%/0.12% at the
6450.8/8127.5 Hz bands, `sweep_drv_-6`) but flagged it UNVALIDATED, because those two bands sit
near the Farina sweep's measurement ceiling with only **order-2** harmonics resolvable
(`meta.thd_band_orders`) and their H2 lands at 12.9/16.3 kHz, where both the pedal's own C5/C11
rolloff and the capture chain roll off hard. So the reported "THD" up there is a single harmonic
measured in the noisiest, most-attenuated part of the capture — exactly where an extraction
artefact would look like a real deficit.

Three probes, ordered so each one can kill the next:

  1. `bands`  — restate §2.5 against the CURRENT (post-W2) JSON, and show what the claim actually
     rests on: the Farina order available per band, and the absolute harmonic level in dBc that
     each THD% implies. A THD figure whose only harmonic sits at -60 dBc is a noise measurement.
  2. `tone`   — the decisive one. The v2 test signal contains **fixed 4 kHz and 8 kHz tone
     segments** (`tone_4000`/`tone_8000`, -14 dBFS, 0.8 s), so 8 kHz distortion can be measured
     DIRECTLY with a windowed DFT — no sweep, no deconvolution, no Farina order limit. Measured
     against the capture's OWN noise floor, taken from the inter-segment silence, so "the pedal
     makes 2% THD at 8 kHz" can be confirmed or refuted outright.
  3. `energy` — total in-band energy in fine bands straddling 6.3-8 kHz (no harmonic separation of
     any kind), across all 16 captures x 4 sweep depths, each side normalised on its own
     200 Hz-2 kHz content. Answers the two questions a fix depends on: is there real missing
     energy, and is it present on the CLEAN sweep (a linear FR error, fixable with a filter) or
     only under drive (clip-mediated, which per W3 no linear filter can fix)?

Usage (from the repo root):
    analysis/.venv/bin/python3 analysis/w7_hf_thd.py [--only bands,tone,energy]

Needs analysis/reports/comprehensive_data.json (regenerate with comprehensive_report.py) for
probe 1, and build/OfflineRender_artefacts/Release/OfflineRender for probes 2-3.
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

# pedal2 is the v2-signal batch; only it has the fixed 4k/8k tones and the three driven depths.
A.use_layout("v2")

SR = 48000.0
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(REPO, "analysis/reports/comprehensive_data.json")
RENDER = os.path.join(REPO, "build/OfflineRender_artefacts/Release/OfflineRender")
SIGNAL = os.path.join(REPO, "analysis/tommy_test_signal_v2_48k.wav")

LEVELS = ["sweep_clean", "sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6"]
# The bands W7 is about, plus 4.1/5.1 kHz below and 10.2 kHz above for contrast.
W7_HZ = [4063.7, 5120.0, 6450.8, 8127.5, 10240.0]


def load_json():
    with open(JSON_PATH) as f:
        return json.load(f)


def _pct_to_dbc(pct):
    """THD percent -> total harmonic level relative to the fundamental, in dBc. The point of
    printing this: at these bands the THD is ONE harmonic, so this IS that harmonic's level, and
    anything near/below the capture noise floor is not a distortion measurement."""
    return 20 * math.log10(max(pct, 1e-9) / 100.0)


def bands():
    """Probe 1: restate §2.5 from the current JSON, with the evidence its claim rests on."""
    d = load_json()
    b, orders = d["meta"]["bands"], d["meta"]["thd_band_orders"]
    print("\n" + "=" * 96)
    print("P1  §2.5 restated against the CURRENT JSON  (generated " + d["meta"]["generated"][:19] + ")")
    print("=" * 96)
    print("    THD% is the median over all 16 pedal2 captures. 'ord' = harmonic orders the Farina")
    print("    extraction can resolve at that band (1 => no THD at all; 2 => H2 only).")
    print("    dBc columns are what those percentages mean as an absolute harmonic level.")

    for lev in ("sweep_drv_-18", "sweep_drv_-12", "sweep_drv_-6"):
        print(f"\n  {lev}")
        print(f"    {'band Hz':>9}{'ord':>5}{'pedal %':>10}{'plugin %':>10}"
              f"{'ped dBc':>10}{'plug dBc':>10}{'ratio x':>9}{'H2 at':>10}")
        for hz in W7_HZ:
            j = b.index(hz)
            ped = [c["thd"][lev]["pedal_pct"][j] for c in d["captures"]]
            plg = [c["thd"][lev]["plugin_pct"][j] for c in d["captures"]]
            ped = [v for v in ped if v is not None]
            plg = [v for v in plg if v is not None]
            if not ped or not plg:
                print(f"    {hz:>9.1f}{orders[j]:>5}{'na':>10}{'na':>10}")
                continue
            mp, mg = st.median(ped), st.median(plg)
            print(f"    {hz:>9.1f}{orders[j]:>5}{mp:>10.2f}{mg:>10.2f}"
                  f"{_pct_to_dbc(mp):>10.1f}{_pct_to_dbc(mg):>10.1f}"
                  f"{mp / max(mg, 1e-9):>9.1f}{2 * hz / 1000:>9.1f}k")


def _render(parsed, orig_f32, tmp):
    out = os.path.join(tmp, "o.f32")
    subprocess.run([RENDER, orig_f32, out] + [str(a) for a in C.render_args(parsed, os_factor_log2=3)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return np.fromfile(out, dtype="<f4")


def _dft_db(x, f):
    """Windowed DFT magnitude at exactly f, in dB. Coherent, so it reads a discrete tone rather
    than the bin's noise power — the right tool for a fixed-tone harmonic."""
    t = np.arange(len(x)) / SR
    w = np.hanning(len(x))
    c = np.sum(x * w * np.exp(-2j * np.pi * f * t)) / np.sum(w) * 2
    return 20 * math.log10(max(abs(c), 1e-15))


def _noise_db_at(x, f, bw=200.0):
    """Local NEIGHBOUR-BIN level near f: RMS of the spectrum in a +/-bw window around f, excluding
    f itself, using the same normalisation as `_dft_db` so 'is this peak discrete?' is
    apples-to-apples.

    Deliberately NOT called a noise floor. `analysis/pedal2` is not a raw analog recording: during
    a -29 dBFS segment its 18-23 kHz energy measures **-160 dBFS** (130 dB down, below a 24-bit
    LSB) and its file head is 57% exact zeros. It is a deterministic render, so this number is a
    numerical/leakage floor, not a recording noise floor, and the huge margins it produces mean
    only that the harmonic is a genuine discrete component of the reference signal."""
    n = len(x)
    X = np.abs(np.fft.rfft(x * np.hanning(n))) / np.sum(np.hanning(n)) * 2
    fr = np.fft.rfftfreq(n, 1 / SR)
    m = (np.abs(fr - f) <= bw) & (np.abs(fr - f) > 3 * SR / n)
    if not m.any():
        return -200.0
    return 20 * math.log10(max(float(np.sqrt(np.mean(X[m] ** 2))), 1e-15))


def tone():
    """Probe 2: measure 4 kHz and 8 kHz distortion DIRECTLY off the fixed-tone segments.

    No sweep, no deconvolution, no Farina order ceiling — this is the check §2.5 could not do and
    the reason W7 was marked 'needs validation'. Each harmonic is printed beside the capture's own
    noise floor at that frequency, so a harmonic that is really noise is visible as such.
    """
    orig = A.load(SIGNAL)
    tmp = tempfile.mkdtemp()
    orig_f32 = os.path.join(tmp, "orig.f32")
    orig.astype("<f4").tofile(orig_f32)

    print("\n" + "=" * 96)
    print("P2  DIRECT fixed-tone distortion at 4 kHz and 8 kHz (v2 tone_4000/tone_8000, -14 dBFS)")
    print("=" * 96)
    print("    dBc = harmonic level below that capture's own fundamental. 'floor' = the LOCAL")
    print("    NEIGHBOUR-BIN level at the harmonic's frequency (see _noise_db_at: the reference is")
    print("    a deterministic render, so this is a leakage floor, not recording noise). A harmonic")
    print("    within ~6 dB of it is not a real component. H3+ at 8 kHz is above Nyquist.")

    rows = []
    for path, parsed in C.find_captures():
        cap = A.load(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        ren_al, _ = A.align(_render(parsed, orig_f32, tmp), orig)
        tag = f"{parsed['rev']:<6} D{parsed['drive']:.2f}"
        for f0, seg, harms in ((4000.0, "tone_4000", (2, 3)), (8000.0, "tone_8000", (2,))):
            cs = A.seg_of(cap_al, seg)
            rs = A.frac_align(A.seg_of(ren_al, seg), cs)
            for k in harms:
                fk = f0 * k
                pc = _dft_db(cs, fk) - _dft_db(cs, f0)
                pg = _dft_db(rs, fk) - _dft_db(rs, f0)
                pf = _noise_db_at(cs, fk) - _dft_db(cs, f0)
                gf = _noise_db_at(rs, fk) - _dft_db(rs, f0)
                rows.append((f0, k, tag, parsed["drive"], pc, pg, pf, gf))

    for f0, k in ((4000.0, 2), (4000.0, 3), (8000.0, 2)):
        sub = [r for r in rows if r[0] == f0 and r[1] == k]
        if not sub:
            continue
        print(f"\n  {f0/1000:.0f} kHz tone, H{k} at {f0*k/1000:.0f} kHz")
        print(f"    {'capture':<14}{'ped dBc':>10}{'ped floor':>11}{'ped SNR':>9}"
              f"{'plug dBc':>10}{'plug floor':>11}{'plug-ped':>10}")
        for _, _, tag, _, pc, pg, pf, gf in sorted(sub, key=lambda r: (r[3], r[2])):
            snr = pc - pf
            flag = "  <- floor" if snr < 6.0 else ""
            print(f"    {tag:<14}{pc:>10.1f}{pf:>11.1f}{snr:>9.1f}"
                  f"{pg:>10.1f}{gf:>11.1f}{pg - pc:>10.1f}{flag}")
        usable = [r for r in sub if r[4] - r[6] >= 6.0]
        print(f"    -- {len(usable)}/{len(sub)} captures have the pedal's H{k} at least 6 dB clear"
              f" of its noise floor")
        if usable:
            print(f"    -- median plugin-pedal over those: "
                  f"{st.median([r[5] - r[4] for r in usable]):+.2f} dB")


def _band_energy_db(x, lo, hi):
    """Total energy in [lo,hi) — fundamental AND every distortion product. No deconvolution."""
    X = np.fft.rfft(x * np.hanning(len(x)))
    f = np.fft.rfftfreq(len(x), 1 / SR)
    m = (f >= lo) & (f < hi)
    return 10 * math.log10(max(float(np.sum(np.abs(X[m]) ** 2)), 1e-30))


def energy():
    """Probe 3: is there real missing ENERGY at 6.3-8 kHz, and is it linear or clip-mediated?

    Total in-band energy only, so no harmonic/fundamental split and no Farina. Each side is
    normalised on its OWN 200 Hz-2 kHz content, so the broadband level match cannot leak in. The
    clean-sweep column is the one that decides fixability: a deficit present on the clean sweep is
    a linear FR error (a filter can fix it); one that only appears under drive is clip-mediated,
    and per W3's outcome no linear filter can add it back.
    """
    orig = A.load(SIGNAL)
    tmp = tempfile.mkdtemp()
    orig_f32 = os.path.join(tmp, "orig.f32")
    orig.astype("<f4").tofile(orig_f32)
    fine = [(4000, 5000), (5000, 6300), (6300, 8000), (8000, 10000), (10000, 13000)]

    print("\n" + "=" * 96)
    print("P3  Total in-band energy, fine bands around 6.3-8 kHz (no Farina, no harmonic split)")
    print("=" * 96)
    print("    plug-ped, dB, each side re its own 200 Hz-2 kHz energy. Negative = plugin light.")

    acc = {}   # (band, level) -> [deltas]
    per_drive = {}  # (band, level, drive) -> [deltas]
    for path, parsed in C.find_captures():
        cap = A.load(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        ren_al, _ = A.align(_render(parsed, orig_f32, tmp), orig)
        for lev in LEVELS:
            cs = A.seg_of(cap_al, lev)
            rs = A.frac_align(A.seg_of(ren_al, lev), cs)
            rc, rr = _band_energy_db(cs, 200, 2000), _band_energy_db(rs, 200, 2000)
            for lo, hi in fine:
                dl = (_band_energy_db(rs, lo, hi) - rr) - (_band_energy_db(cs, lo, hi) - rc)
                acc.setdefault((lo, hi, lev), []).append(dl)
                per_drive.setdefault((lo, hi, lev, parsed["drive"]), []).append(dl)

    print(f"\n  median over all 16 captures")
    print(f"    {'band':<12}" + "".join(f"{lev.replace('sweep_',''):>15}" for lev in LEVELS))
    for lo, hi in fine:
        lbl = f"{lo/1000:g}-{hi/1000:g}k"
        cells = "".join(f"{st.median(acc[(lo, hi, lev)]):>+15.2f}" for lev in LEVELS)
        print(f"    {lbl:<12}{cells}")

    drives = sorted({k[3] for k in per_drive})
    for lo, hi in ((6300, 8000),):
        print(f"\n  {lo/1000:g}-{hi/1000:g}k broken out by DRIVE (median per drive)")
        print(f"    {'DRIVE':<12}" + "".join(f"{lev.replace('sweep_',''):>15}" for lev in LEVELS))
        for dv in drives:
            cells = "".join(f"{st.median(per_drive[(lo, hi, lev, dv)]):>+15.2f}"
                            if (lo, hi, lev, dv) in per_drive else f"{'-':>15}" for lev in LEVELS)
            print(f"    {dv:<12.2f}{cells}")


def products():
    """Probe 4: the question the user's EAR actually asked.

    Probe 3's in-band energy at 6.3-8 kHz is dominated by the sweep's own FUNDAMENTAL passing
    through that band, so a small total-energy delta can hide a large deficit in the distortion
    products — and on guitar, 6.3-8 kHz content is almost entirely harmonics of much lower notes,
    not fundamentals. This measures exactly those: harmonics of the fixed 1/2/4 kHz tones that
    LAND in 6.3-8.2 kHz, each as a level below its own fundamental, pedal vs plugin.

    Unlike probe 1 this is a direct windowed DFT on a steady tone (no Farina, no order ceiling),
    and unlike probe 3 it excludes the fundamental entirely.
    """
    orig = A.load(SIGNAL)
    tmp = tempfile.mkdtemp()
    orig_f32 = os.path.join(tmp, "orig.f32")
    orig.astype("<f4").tofile(orig_f32)

    # (segment, f0, harmonic orders whose product lands in 6.3-8.2 kHz)
    src = [("tone_1000", 1000.0, (7, 8)), ("tone_2000", 2000.0, (4,)), ("tone_4000", 4000.0, (2,))]

    print("\n" + "=" * 96)
    print("P4  Distortion products LANDING in 6.3-8.2 kHz, from the fixed 1/2/4 kHz tones")
    print("=" * 96)
    print("    dBc = product level below its own fundamental. This is the content a guitar signal")
    print("    actually puts in this band. Negative plug-ped = plugin makes less of it.")

    rows = {}
    for path, parsed in C.find_captures():
        cap = A.load(path)
        if not A.is_full_length(cap, orig):
            continue
        cap_al, _ = A.align(cap, orig)
        ren_al, _ = A.align(_render(parsed, orig_f32, tmp), orig)
        tag = f"{parsed['rev']:<6} D{parsed['drive']:.2f}"
        for seg, f0, orders in src:
            cs = A.seg_of(cap_al, seg)
            rs = A.frac_align(A.seg_of(ren_al, seg), cs)
            fc, fg = _dft_db(cs, f0), _dft_db(rs, f0)
            for k in orders:
                fk = f0 * k
                rows.setdefault((f0, k), []).append(
                    (tag, parsed["drive"], _dft_db(cs, fk) - fc, _dft_db(rs, fk) - fg,
                     _noise_db_at(cs, fk) - fc))

    for (f0, k), sub in sorted(rows.items()):
        print(f"\n  {f0/1000:g} kHz tone, H{k} at {f0*k/1000:.1f} kHz")
        print(f"    {'capture':<14}{'ped dBc':>10}{'plug dBc':>10}{'plug-ped':>10}{'ped margin':>12}")
        for tag, _, pc, pg, pf in sorted(sub, key=lambda r: (r[1], r[0])):
            flag = "  <- in floor" if pc - pf < 6.0 else ""
            print(f"    {tag:<14}{pc:>10.1f}{pg:>10.1f}{pg - pc:>+10.1f}{pc - pf:>12.1f}{flag}")
        ok = [r for r in sub if r[2] - r[4] >= 6.0]
        if ok:
            print(f"    -- median plug-ped over the {len(ok)}/{len(sub)} above-floor captures: "
                  f"{st.median([r[3] - r[2] for r in ok]):+.2f} dB")


STEPS = {"bands": bands, "tone": tone, "energy": energy, "products": products}


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
