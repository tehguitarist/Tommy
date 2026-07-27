"""v1.4 W7 — is the plugin genuinely THD-light at 6.3-8 kHz, or is that a measurement artefact?

The user's ear flagged the plugin as light on distortion in the 6.3-8 kHz region. §2.5 of the
v1.4 plan reported a 10-20x shortfall there (pedal 1.49%/2.16% vs plugin 0.11%/0.12% at the
6450.8/8127.5 Hz bands, `sweep_drv_-6`) but flagged it UNVALIDATED, because those two bands sit
near the Farina sweep's measurement ceiling with only **order-2** harmonics resolvable
(`meta.thd_band_orders`) and their H2 lands at 12.9/16.3 kHz, where both the pedal's own C5/C11
rolloff and the capture chain roll off hard. So the reported "THD" up there is a single harmonic
measured in the noisiest, most-attenuated part of the capture — exactly where an extraction
artefact would look like a real deficit.

Six probes, ordered so each one can kill the next:

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
  4. `products` — the harmonics of the fixed 1/2/4 kHz tones that LAND in 6.3-8.2 kHz, i.e. the
     content a guitar actually puts up there. Found the side finding probes 5-6 exist to settle:
     Soft/Medium's EVEN-order products are 7-15 dB light at high drive while Hard's are fine.

  -- probes 5 and 6 close that side finding: is `kSymMismatch` the lever, and does it matter? --

  5. `profile` — the even-harmonic (H2) error vs FREQUENCY at the shipped kSymMismatch, from the
     seven fixed tones 82-4000 Hz. `kSymMismatch` is a single frequency-flat number, so it can only
     be the lever if the error has the SAME size at every frequency. Also prints each product's
     ABSOLUTE level (dBc and dBFS) beside W5's -45 dBc audibility floor, so "is this audible at
     all" is answered from the same table.
  6. `sym`     — sweep kSymMismatch over the 10 Soft/Medium captures and tabulate what each value
     does to H2 at every tone frequency, to THD/H3 (must not move), and to the null vs the pedal.
     Ends with the size of the change itself, rendered as a shipped-vs-candidate null: if that sits
     below the plugin's own ~-45 dB residual against the capture, the change is unmeasurable in an
     A/B and should not ship regardless of how the fit looks.

Usage (from the repo root):
    analysis/.venv/bin/python3 analysis/w7_hf_thd.py [--only bands,tone,energy,products,profile,sym]

Needs analysis/reports/comprehensive_data.json (regenerate with comprehensive_report.py) for
probe 1, and build/OfflineRender_artefacts/Release/OfflineRender for probes 2-6.
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


# --- probes 5-6: is kSymMismatch the lever for the even-order HF deficit? ------------------------

# H2 of each fixed tone. 8 kHz is excluded (its H2 is above Nyquist); 2 kHz/4 kHz are the two that
# put an even product INTO and ABOVE W7's band, and 82-1000 Hz are where H2 is loud enough to be
# audible at all — the contrast between those two groups is the whole question.
H2_TONES = [82.41, 110.0, 220.0, 440.0, 1000.0, 2000.0, 4000.0]
SYM_SHIPPED = 0.06
SYM_VALUES = [0.06, 0.12, 0.20, 0.30, 0.45]   # 0.45 = kAsymMismatch, i.e. Hard's value: the ceiling
AUDIBILITY_DBC = -45.0                        # W5's floor (report_audit.py), reused unchanged
IN_F32 = "/tmp/w7_sym_in.f32"
OUT_F32 = "/tmp/w7_sym_out.f32"


def _sym_args(m):
    """OfflineRender argv[10..20] with only kSymMismatch (argv[20]) overridden.

    symBias is argv[20] and render_args() supplies argv[3..9], so this list MUST be 11 long — a
    short list silently lands the value in an earlier slot (drive taper, supply volts) and the
    sweep becomes a no-op or, worse, a sweep of the wrong parameter. Same trap as w4_knmedium's.
    """
    a = ["1.2", "-1", "1.43", "-1", "1.43", "-1", "0", "-1", "1", "9", f"{m:.4f}"]
    assert len(a) == 11, f"argv[10..20] must be 11 entries, got {len(a)}"
    return a


def _render_sym(parsed, m):
    r = subprocess.run([RENDER, IN_F32, OUT_F32]
                       + C.render_args(parsed, os_factor_log2=3, extra_args=_sym_args(m)),
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:200])
    return np.fromfile(OUT_F32, dtype="<f4").astype(np.float64)


def _h2_row(cap_seg, ren_seg, f0):
    """(pedal dBc, plugin dBc, pedal margin over the local floor, plugin H2 absolute dBFS).

    The floor window is narrowed to 0.4*f0 at low frequencies. `_noise_db_at`'s default +/-200 Hz
    is fine around an 8 kHz harmonic but at H2 of the 82 Hz tone (164.8 Hz) it reaches all the way
    down to the FUNDAMENTAL, so the "floor" it returns is the fundamental's skirt and every low
    tone reports a large negative margin. That is a window bug, not a floor problem — with the
    window narrowed those rows are comfortably above their real floor.
    """
    bw = min(200.0, 0.4 * f0)
    fc, fg = _dft_db(cap_seg, f0), _dft_db(ren_seg, f0)
    hc, hg = _dft_db(cap_seg, 2 * f0), _dft_db(ren_seg, 2 * f0)
    return hc - fc, hg - fg, hc - _noise_db_at(cap_seg, 2 * f0, bw), hg


def _sm_captures():
    """Soft + Medium only — kSymMismatch is their parameter; Hard uses kAsymMismatch and is
    untouched by argv[20] by construction, so it needs no regression check here."""
    return [(p, q) for p, q in C.find_captures() if q["rev"] in ("Soft", "Medium")]


def profile():
    """Probe 5: is the even-harmonic error the same size at every frequency?

    `kSymMismatch` is one frequency-flat number: raising it lifts H2 by the same dB at 165 Hz as at
    8 kHz (verified — the sweep in probe 6 shows exactly that). So it can only be the lever for the
    HF even-product deficit if the deficit is BROADBAND. If H2 is already correct at low frequency
    and only light at HF, the error is frequency-dependent and no value of this parameter fits it.

    The absolute columns answer the second question in the same pass: W5 adopted a -45 dBc floor
    because below it the two sides are comparing noise, and probe 4 flagged these products at
    -55..-76 dBc. A product below the floor is not worth fitting even if the fit were possible.
    """
    orig = A.load(SIGNAL)
    orig.astype(np.float32).tofile(IN_F32)
    caps = _sm_captures()

    print("\n" + "=" * 100)
    print("P5  H2 error vs FREQUENCY at the shipped kSymMismatch = %.2f  (Soft/Medium only)" % SYM_SHIPPED)
    print("=" * 100)
    print("    dBc = H2 below its own fundamental. 'margin' = pedal H2 over the local neighbour-bin")
    print(f"    level. 'aud' flags a pedal H2 at or above W5's {AUDIBILITY_DBC:.0f} dBc audibility floor.")

    acc = {}
    for path, q in caps:
        cap, _ = A.align(A.load(path), orig)
        ren, _ = A.align(_render_sym(q, SYM_SHIPPED), orig)
        for f0 in H2_TONES:
            cs = A.seg_of(cap, f"tone_{f0:g}")
            rs = A.frac_align(A.seg_of(ren, f"tone_{f0:g}"), cs)
            acc.setdefault(f0, []).append((f"{q['rev']:<6} D{q['drive']:.2f}",) + _h2_row(cs, rs, f0))

    print(f"\n  {'tone':>8}{'H2 at':>9}{'ped dBc':>10}{'plug dBc':>10}{'plug-ped':>10}"
          f"{'margin':>9}{'audible?':>10}")
    for f0 in H2_TONES:
        rows = acc[f0]
        mp = st.median([r[1] for r in rows])
        mg = st.median([r[2] for r in rows])
        mm = st.median([r[3] for r in rows])
        aud = f"{sum(1 for r in rows if r[1] >= AUDIBILITY_DBC)}/{len(rows)}"
        print(f"  {f0:>8.0f}{2*f0/1000:>8.2f}k{mp:>10.1f}{mg:>10.1f}{mg-mp:>+10.1f}{mm:>9.1f}{aud:>10}")
    print(f"\n    (median over the {len(caps)} Soft/Medium captures; 'audible?' = how many of them"
          f" have the\n     PEDAL's H2 at or above {AUDIBILITY_DBC:.0f} dBc.)")

    print(f"\n  per-capture detail at the two ends")
    for f0 in (H2_TONES[0], H2_TONES[-1]):
        print(f"\n    tone {f0:g} Hz, H2 at {2*f0/1000:.2f} kHz")
        print(f"      {'capture':<14}{'ped dBc':>10}{'plug dBc':>10}{'plug-ped':>10}{'margin':>9}")
        for tag, pc, pg, mm, _ in acc[f0]:
            print(f"      {tag:<14}{pc:>10.1f}{pg:>10.1f}{pg-pc:>+10.1f}{mm:>9.1f}")


def sym():
    """Probe 6: sweep kSymMismatch, and price the change against the plugin's existing residual.

    Three questions, one render pass (10 Soft/Medium captures x len(SYM_VALUES)):
      (a) does any value close the HF even-product gap without breaking H2 where it IS audible?
      (b) does it move anything other than H2? (W2 said no; verified here on H3 and THD.)
      (c) how big is the change at all? Reported as a null between the shipped render and each
          candidate. The plugin's own null against the pedal2 captures sits near -45 dB, so a
          change quieter than that cannot be heard as a difference in the A/B it is meant to fix.
    """
    orig = A.load(SIGNAL)
    orig.astype(np.float32).tofile(IN_F32)
    caps = _sm_captures()
    print("\n" + "=" * 100)
    print(f"P6  kSymMismatch sweep — {len(caps)} Soft/Medium captures x {len(SYM_VALUES)} values"
          f" = {len(caps)*len(SYM_VALUES)} renders (shipped = {SYM_SHIPPED})")
    print("=" * 100)

    h2 = {}      # (f0, m) -> [plug-ped dB]
    other = {}   # m -> {"h3": [...], "thd": [...]}
    nulls = {}   # m -> [null vs shipped render, dB]
    ped_dbc = {}
    for path, q in caps:
        cap, _ = A.align(A.load(path), orig)
        base = None
        for m in SYM_VALUES:
            ren, _ = A.align(_render_sym(q, m), orig)
            if m == SYM_SHIPPED:
                base = ren
            for f0 in H2_TONES:
                cs = A.seg_of(cap, f"tone_{f0:g}")
                rs = A.frac_align(A.seg_of(ren, f"tone_{f0:g}"), cs)
                pc, pg, _, _ = _h2_row(cs, rs, f0)
                h2.setdefault((f0, m), []).append(pg - pc)
                ped_dbc.setdefault(f0, []).append(pc)
            cs1 = A.seg_of(cap, "tone_1000")
            rs1 = A.frac_align(A.seg_of(ren, "tone_1000"), cs1)
            o = other.setdefault(m, {"h3": [], "thd": []})
            o["h3"].append((_dft_db(rs1, 3000) - _dft_db(rs1, 1000))
                           - (_dft_db(cs1, 3000) - _dft_db(cs1, 1000)))
            o["thd"].append(A.thd(rs1, 1000)[0] - A.thd(cs1, 1000)[0])
            # size of the change itself, vs the shipped render, on the hottest driven sweep
            if base is not None and m != SYM_SHIPPED:
                b = A.seg_of(base, "sweep_drv_-6")
                t = A.frac_align(A.seg_of(ren, "sweep_drv_-6"), b)
                nulls.setdefault(m, []).append(A.null_depth(b, t)[0])

    print("\n  (a) H2 error (plugin - pedal, dB) by tone frequency and kSymMismatch")
    print(f"      {'tone':>7}{'ped dBc':>10}  " + "".join(f"{m:>10.2f}" for m in SYM_VALUES))
    print("      " + "-" * (17 + 10 * len(SYM_VALUES)))
    for f0 in H2_TONES:
        cells = "".join(f"{st.median(h2[(f0, m)]):>+10.1f}" for m in SYM_VALUES)
        print(f"      {f0:>7.0f}{st.median(ped_dbc[f0]):>10.1f}  {cells}")
    print("      " + "-" * (17 + 10 * len(SYM_VALUES)))
    lo = [f for f in H2_TONES if f <= 1000]
    hi = [f for f in H2_TONES if f > 1000]
    for lbl, grp in (("mean|err| 82-1k", lo), ("mean|err| 2k-4k", hi)):
        cells = "".join(f"{st.mean([abs(st.median(h2[(f, m)])) for f in grp]):>10.2f}"
                        for m in SYM_VALUES)
        print(f"      {lbl:>17}  {cells}")

    print("\n  (b) collateral: does it move anything other than H2? (1 kHz tone)")
    print(f"      {'metric':>17}  " + "".join(f"{m:>10.2f}" for m in SYM_VALUES))
    print(f"      {'H3 err dB':>17}  "
          + "".join(f"{st.median(other[m]['h3']):>+10.2f}" for m in SYM_VALUES))
    print(f"      {'THD err %':>17}  "
          + "".join(f"{st.median(other[m]['thd']):>+10.2f}" for m in SYM_VALUES))

    print("\n  (c) SIZE of the change: null of each candidate against the SHIPPED render")
    print("      (sweep_drv_-6, gain-matched. The plugin's own null vs the pedal2 captures is")
    print("       around -45 dB, so anything below that line is inaudible in the A/B it targets.)")
    print(f"      {'kSymMismatch':>17}  " + "".join(f"{m:>10.2f}" for m in SYM_VALUES[1:]))
    print(f"      {'null vs shipped':>17}  "
          + "".join(f"{st.median(nulls[m]):>10.1f}" for m in SYM_VALUES[1:]))


STEPS = {"bands": bands, "tone": tone, "energy": energy, "products": products,
         "profile": profile, "sym": sym}


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
