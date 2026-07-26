#!/usr/bin/env python3
"""Comprehensive plugin-vs-capture analysis — FR, THD, H2-H7 harmonics -> JSON dashboard data.

Imported and adapted for Tommy from the Guitar-Pedal-Plugin-Template analysis harness (see that
project's analysis/README.md). Reads every capture in analysis/pedal2/ (the v2-signal, definitive
tone-reference batch — see captures.py), renders the plugin at matching settings via OfflineRender,
and writes a JSON report at analysis/reports/comprehensive_data.json.

This targets the v2 test signal exclusively (forces analyze.use_layout("v2")): pedal2 is the only
capture batch with three driven-sweep depths + the full 8-tone discrete THD anchor set this report's
per-band analysis expects (see CAPTURE_SPEC.md). pedal1 (v1 signal, single driven sweep, 7 tones,
0-10 notation) isn't compatible with this report's schema — use the existing run_compare.py /
knob_tracking.py / swept_thd.py tools for that batch instead.

Run from repo root:
    python3 analysis/comprehensive_report.py [--os 8] [--keep-renders DIR] [--jobs N]

Captures are analysed in parallel across a process pool (each capture's render + analysis is
independent). Defaults to all cores minus a reservation for the OS and other running processes —
override with --jobs, or pass --jobs 1 to run serially.

Real-pedal capture analysis (load, align, transfer/FR curve, Farina harmonic curve, discrete-tone
THD) depends only on the capture .wav + the reference test signal — never on the plugin — so it's
cached to disk per capture file (analysis/.cache/pedal_features) and skipped entirely on later runs
as you iterate on the plugin. Pass --no-cache to bypass.

Output: analysis/reports/comprehensive_data.json
"""
import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import pickle
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
from scipy.io import wavfile

import analyze as A
import gen_test_signal_v2 as G

import captures as C

A.use_layout("v2")  # only pedal2 (batch-6, v2 signal) has the driven-sweep/tone set this needs

DEFAULT_BIN = C.RENDER_BIN
OUTPUT_JSON = "analysis/reports/comprehensive_data.json"
CACHE_DIR = "analysis/.cache/pedal_features"
CACHE_VERSION = 1  # bump to invalidate every cache entry after a change to the analysis below
DRIVEN_SWEEPS = tuple(f"sweep_drv_{db}" for db in G.DRIVEN_LEVELS_DB)
ALL_SWEEP_LEVELS = ("sweep_clean",) + DRIVEN_SWEEPS
FARINA_CEILING_HZ = A.thd_max_measurable_hz(max_order=2)
# Guitar-relevant low-string fundamentals (matches harmonics.py's default f0 range) rather than the
# template's generic (100, 200, 400) anchors.
THD_ANCHORS = (110, 220, 440)
HARMONIC_ORDERS = tuple(range(2, 8))
TONE_FREQS = G.TONE_FREQS


def max_measurable_order(band_hz, max_order=max(HARMONIC_ORDERS)):
    """Highest harmonic order still in-band at this fundamental (see analyze.harmonic_thd_curve's
    order-limiting docstring) — report_audit.py's THD-coverage section reports this per band."""
    order = 0
    for n in range(1, max_order + 1):
        if n * band_hz <= A.SWEEP_F1 * A.ORDER_LIMIT_MARGIN:
            order = n
    return order


def build_band_source_map(bands):
    """Return list of (band_hz, source_str) — 'farina', 'discrete', or 'na'."""
    result = []
    for b in bands:
        if b <= FARINA_CEILING_HZ + 1e-6:
            result.append((b, "farina"))
            continue
        nearest_tone = min(TONE_FREQS, key=lambda t: abs(t - b))
        if abs(nearest_tone - b) / b < 0.06 and nearest_tone > FARINA_CEILING_HZ:
            result.append((b, "discrete"))
        else:
            result.append((b, "na"))
    return result


def render_plugin(binpath, args, in_f32_path, out_f32_path):
    """OfflineRender has no --os flag or WAV I/O: it's `in.f32 out.f32 bassX driveX trebX volX
    modeIdx factorLog2 [sr]` over raw float32 (see offline_render.cpp)."""
    cmd = [binpath, in_f32_path, out_f32_path] + args
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"  ! render failed: {r.stderr.strip() or r.stdout.strip()}\n")
        return False
    return True


def _pedal_cache_key(path):
    """Identity of a capture file + the reference signal it's aligned against + the analysis
    version. A capture is a real recording — it never changes once made — so keying on
    (path, mtime, size) is enough to detect an edit/re-record without hashing file contents."""
    st = os.stat(path)
    ost = os.stat(A.ORIG)
    payload = {
        "version": CACHE_VERSION,
        "path": os.path.abspath(path),
        "mtime": st.st_mtime,
        "size": st.st_size,
        "orig_mtime": ost.st_mtime,
        "orig_size": ost.st_size,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def compute_pedal_features(cap_al, orig):
    """All CAPTURE-side (real-pedal) analysis — transfer/FR curve, Farina harmonic curve,
    discrete-tone THD — for every sweep/tone this report ever reads. None of this depends on the
    plugin render, so it's exactly what's safe to cache to disk keyed by the capture file."""
    inp = A.seg_of(orig, "sweep_clean")

    fr_transfer = {sw: A.transfer(A.seg_of(cap_al, sw), inp) for sw in ALL_SWEEP_LEVELS}
    farina = {sw: A.harmonic_thd_curve(A.seg_of(cap_al, sw), inp, max_order=7) for sw in DRIVEN_SWEEPS}

    tone_thd = {}
    for t in TONE_FREQS:
        seg_name = f"tone_{t:g}"
        try:
            tone_thd[seg_name] = A.thd(A.seg_of(cap_al, seg_name), t)
        except Exception:
            tone_thd[seg_name] = (None, None)

    return {"fr_transfer": fr_transfer, "farina": farina, "tone_thd": tone_thd}


def get_pedal_features(path, orig, cache_dir, use_cache=True):
    """Return (cap_al, pedal_features), loading from disk cache when the capture + reference
    signal identity matches a prior run. Returns None if the capture is truncated."""
    cpath = os.path.join(cache_dir, _pedal_cache_key(path) + ".pkl") if use_cache else None

    if use_cache and os.path.exists(cpath):
        try:
            with open(cpath, "rb") as fh:
                return pickle.load(fh)
        except Exception:
            pass  # corrupt/partial cache entry -> fall through and recompute

    cap = C.load_capture(path)
    if not A.is_full_length(cap, orig):
        return None
    cap_al, _ = A.align(cap, orig)
    result = (cap_al, compute_pedal_features(cap_al, orig))

    if use_cache:
        os.makedirs(cache_dir, exist_ok=True)
        tmp = f"{cpath}.tmp{os.getpid()}"
        with open(tmp, "wb") as fh:
            pickle.dump(result, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, cpath)

    return result


def fr_at_bands(cap_al, ren_al, orig, sweep_name, bands, pedal_features):
    """Return (plugin_db, pedal_db, gain_db_applied) at each band."""
    inp = A.seg_of(orig, "sweep_clean")
    cap_seg = A.seg_of(cap_al, sweep_name)
    ren_seg = A.seg_of(ren_al, sweep_name)
    ren_seg_aligned = A.frac_align(ren_seg, cap_seg)
    _, gain_db = A.null_depth(cap_seg, ren_seg_aligned)

    f_cap, H_cap = pedal_features["fr_transfer"][sweep_name]
    f, H_ren = A.transfer(ren_seg, inp)
    plugin_db = [float(np.interp(b, f, H_ren)) + gain_db for b in bands]
    pedal_db = [float(np.interp(b, f_cap, H_cap)) for b in bands]
    return plugin_db, pedal_db, float(gain_db)


def thd_at_bands(cap_al, ren_al, orig, sweep_name, band_source_map, pedal_features):
    """Return (plugin_pct, pedal_pct, source) arrays at each band."""
    ref = A.seg_of(orig, "sweep_clean")
    ren_sweep = A.seg_of(ren_al, sweep_name)

    farina_cache = {}
    tone_cache = {}

    plugin_pct = []
    pedal_pct = []
    sources = []

    for band_hz, source in band_source_map:
        if source == "farina":
            if "ren" not in farina_cache:
                fr_c, thd_c, _ = pedal_features["farina"][sweep_name]
                fr_r, thd_r, _ = A.harmonic_thd_curve(ren_sweep, ref, max_order=7)
                farina_cache["cap_fr"] = fr_c
                farina_cache["cap_thd"] = thd_c
                farina_cache["ren_fr"] = fr_r
                farina_cache["ren_thd"] = thd_r
                farina_cache["ren"] = True
            p_cap = float(np.interp(band_hz, farina_cache["cap_fr"], farina_cache["cap_thd"]))
            p_ren = float(np.interp(band_hz, farina_cache["ren_fr"], farina_cache["ren_thd"]))
            plugin_pct.append(p_ren)
            pedal_pct.append(p_cap)
            sources.append("farina")
        elif source == "discrete":
            nearest_tone = min(TONE_FREQS, key=lambda t: abs(t - band_hz))
            tone_seg = f"tone_{nearest_tone:g}"
            if tone_seg not in tone_cache:
                try:
                    thd_cap, _ = pedal_features["tone_thd"][tone_seg]
                    thd_ren, _ = A.thd(A.seg_of(ren_al, tone_seg), nearest_tone)
                    tone_cache[tone_seg] = (float(thd_cap), float(thd_ren))
                except Exception:
                    tone_cache[tone_seg] = (None, None)
            p_cap, p_ren = tone_cache[tone_seg]
            plugin_pct.append(p_ren)
            pedal_pct.append(p_cap)
            sources.append("discrete")
        else:
            plugin_pct.append(None)
            pedal_pct.append(None)
            sources.append("na")

    return plugin_pct, pedal_pct, sources


def harmonics_at_anchors(cap_al, ren_al, orig, sweep_name, pedal_features):
    """Return {order: {plugin_db, pedal_db}} at each anchor freq."""
    ref = A.seg_of(orig, "sweep_clean")
    ren_sweep = A.seg_of(ren_al, sweep_name)

    fr_c, thd_c, Hn_c = pedal_features["farina"][sweep_name]
    fr_r, thd_r, Hn_r = A.harmonic_thd_curve(ren_sweep, ref, max_order=7)

    har = {}
    for order in range(2, 8):
        plugin_db = []
        pedal_db = []
        for ahz in THD_ANCHORS:
            idx_c = int(np.argmin(np.abs(fr_c - ahz)))
            idx_r = int(np.argmin(np.abs(fr_r - ahz)))
            H1_c = Hn_c[1][idx_c] if 1 in Hn_c else 1e-20
            H1_r = Hn_r[1][idx_r] if 1 in Hn_r else 1e-20
            val_c = float(20.0 * np.log10(Hn_c[order][idx_c] / (H1_c + 1e-20) + 1e-20))
            val_r = float(20.0 * np.log10(Hn_r[order][idx_r] / (H1_r + 1e-20) + 1e-20))
            pedal_db.append(val_c)
            plugin_db.append(val_r)
        har[f"H{order}"] = {"plugin_db": plugin_db, "pedal_db": pedal_db}
    return har


def short_id(parsed):
    """Compact capture label, e.g. 'Hard D0.60 B0.20 T0.20 V0.50'."""
    return (f"{parsed.get('rev', '?')} D{parsed.get('drive', 0):.2f} "
            f"B{parsed.get('bass', 0):.2f} T{parsed.get('treble', 0):.2f} "
            f"V{parsed.get('volume', 0):.2f}")


def analyse_one(path, parsed, orig, orig_f32_path, binpath, os_log2, keep_dir, bands,
                 band_source_map, cache_dir, use_cache):
    cached = get_pedal_features(path, orig, cache_dir, use_cache)
    if cached is None:
        sys.stderr.write(f"  SKIP (truncated): {os.path.basename(path)}\n")
        return None
    cap_al, pedal_features = cached

    args = C.render_args(parsed, os_factor_log2=os_log2)
    out_tmp = tempfile.NamedTemporaryFile(suffix=".f32", delete=False)
    out_path = out_tmp.name
    out_tmp.close()

    try:
        if not render_plugin(binpath, args, orig_f32_path, out_path):
            return None
        ren = np.fromfile(out_path, dtype=np.float32).astype(np.float64)
        ren_al, _ = A.align(ren, orig)

        if keep_dir:
            os.makedirs(keep_dir, exist_ok=True)
            wav_path = os.path.join(keep_dir,
                                    os.path.splitext(os.path.basename(path))[0] + "_plugin.wav")
            wavfile.write(wav_path, 48000, ren.astype(np.float32))

        settings = {k: float(v) for k, v in parsed.items() if k not in ("rev", "mode") and v is not None}

        result = {
            "id": short_id(parsed),
            "rev": parsed.get("rev", "?"),
            "file": os.path.basename(path),
            "settings": settings,
            "fr": {},
            "thd": {},
            "harmonics": {},
        }

        for sw in ALL_SWEEP_LEVELS:
            plugin_db, pedal_db, gain_db = fr_at_bands(cap_al, ren_al, orig, sw, bands, pedal_features)
            result["fr"][sw] = {"plugin_db": plugin_db, "pedal_db": pedal_db, "gain_db_applied": gain_db}

        for sw in DRIVEN_SWEEPS:
            plugin_pct, pedal_pct, sources = thd_at_bands(
                cap_al, ren_al, orig, sw, band_source_map, pedal_features)
            result["thd"][sw] = {
                "plugin_pct": plugin_pct, "pedal_pct": pedal_pct, "source": sources,
            }

        for sw in DRIVEN_SWEEPS:
            result["harmonics"][sw] = harmonics_at_anchors(cap_al, ren_al, orig, sw, pedal_features)

        return result

    finally:
        if os.path.exists(out_path):
            os.unlink(out_path)


def compute_summary(results, bands):
    """Per-clip-mode aggregate scores (Tommy has no hardware revisions, so `rev` here is the SW1
    clip mode — Hard/Medium/Soft — derived from the data)."""
    by_rev = defaultdict(list)
    for r in results:
        if r:
            by_rev[r["rev"]].append(r)

    out = {}
    for rev, rev_caps in by_rev.items():
        fr_rms_vals = []
        best_rms = float("inf")
        worst_rms = float("-inf")
        best_id = worst_id = ""
        for r in rev_caps:
            fr = r["fr"]["sweep_clean"]
            diff = [fr["plugin_db"][i] - fr["pedal_db"][i] for i in range(len(bands))]
            rms = float(np.sqrt(np.mean(np.array(diff) ** 2)))
            fr_rms_vals.append(rms)
            if rms < best_rms:
                best_rms = rms
                best_id = r["id"]
            if rms > worst_rms:
                worst_rms = rms
                worst_id = r["id"]
        out[rev] = {
            "n_captures": len(rev_caps),
            "fr_rms_mean": float(np.mean(fr_rms_vals)),
            "fr_rms_median": float(np.median(fr_rms_vals)),
            "fr_rms_min": best_rms,
            "fr_rms_max": worst_rms,
            "best_capture": best_id,
            "worst_capture": worst_id,
        }
    return {"by_revision": out}


def default_jobs():
    """All cores minus a reservation for the OS + other running processes."""
    n = os.cpu_count() or 4
    reserved = max(1, round(n * 0.2))
    return max(1, n - reserved)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bin", default=DEFAULT_BIN)
    ap.add_argument("--os", type=int, default=8, choices=(1, 2, 4, 8),
                     help="oversampling factor passed to OfflineRender (default: %(default)s)")
    ap.add_argument("--capture-dir", default=C.CAPTURE_DIR,
                     help="capture batch directory (default: %(default)s)")
    ap.add_argument("--keep-renders", default=None)
    ap.add_argument("--jobs", type=int, default=None,
                     help=f"parallel worker processes (default: {default_jobs()} "
                          f"of {os.cpu_count()} cores, reserving some for the OS)")
    ap.add_argument("--cache-dir", default=CACHE_DIR,
                     help="disk cache dir for capture-side (pedal) analysis (default: %(default)s)")
    ap.add_argument("--no-cache", action="store_true",
                     help="recompute capture-side analysis fresh; don't read or write the cache")
    a = ap.parse_args()
    jobs = a.jobs if a.jobs and a.jobs > 0 else default_jobs()
    use_cache = not a.no_cache
    os_log2 = int(round(math.log2(a.os)))

    if not os.path.exists(a.bin):
        sys.exit(f"OfflineRender not found at {a.bin} — build it with "
                 f"`cmake --build build --target OfflineRender`, or check --bin")
    if not os.path.exists(A.ORIG):
        sys.exit(f"Reference not found at {A.ORIG} — run `python3 analysis/gen_test_signal_v2.py` first")

    bands = [round(b, 1) for b in A.fractional_octave_freqs(20.0, 20000.0, 3)]
    band_source_map = build_band_source_map(bands)

    orig = A.load(A.ORIG)
    caps = C.find_captures(a.capture_dir)

    sys.stderr.write(f"Comprehensive report: {len(caps)} captures | OS={a.os}x | {len(bands)} bands\n")
    sys.stderr.write(f"  THD coverage: {sum(1 for _, s in band_source_map if s != 'na')}/{len(bands)} bands\n")
    sys.stderr.write(f"  jobs: {jobs} (of {os.cpu_count()} cores) | cache: "
                     f"{'off' if not use_cache else a.cache_dir}\n\n")

    orig_f32 = tempfile.NamedTemporaryFile(suffix=".f32", delete=False)
    orig_f32_path = orig_f32.name
    orig_f32.close()
    orig.astype(np.float32).tofile(orig_f32_path)

    try:
        results = [None] * len(caps)
        if jobs <= 1:
            for i, (path, parsed) in enumerate(caps):
                sys.stderr.write(f"[{i + 1}/{len(caps)}] {short_id(parsed)} ... ")
                sys.stderr.flush()
                res = analyse_one(path, parsed, orig, orig_f32_path, a.bin, os_log2, a.keep_renders,
                                   bands, band_source_map, a.cache_dir, use_cache)
                sys.stderr.write("done\n" if res else "FAILED\n")
                results[i] = res
        else:
            with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as ex:
                futures = {
                    ex.submit(analyse_one, path, parsed, orig, orig_f32_path, a.bin, os_log2,
                              a.keep_renders, bands, band_source_map, a.cache_dir, use_cache): i
                    for i, (path, parsed) in enumerate(caps)
                }
                completed = 0
                for fut in concurrent.futures.as_completed(futures):
                    i = futures[fut]
                    _, parsed = caps[i]
                    completed += 1
                    try:
                        res = fut.result()
                    except Exception as e:
                        sys.stderr.write(f"[{completed}/{len(caps)}] {short_id(parsed)} ... FAILED ({e})\n")
                        res = None
                    else:
                        sys.stderr.write(f"[{completed}/{len(caps)}] {short_id(parsed)} ... "
                                          f"{'done' if res else 'FAILED'}\n")
                    results[i] = res
    finally:
        os.unlink(orig_f32_path)

    ok = [r for r in results if r]
    sys.stderr.write(f"\n{len(ok)}/{len(results)} captures analysed.\n")

    summary = compute_summary(ok, bands)

    out = {
        "meta": {
            "generated": datetime.now(timezone.utc).isoformat(),
            "os_factor": a.os,
            "num_captures": len(ok),
            "num_bands": len(bands),
            "bands": bands,
            "thd_anchors": list(THD_ANCHORS),
            "harmonic_orders": list(HARMONIC_ORDERS),
            "driven_sweeps": list(DRIVEN_SWEEPS),
            "all_sweep_levels": list(ALL_SWEEP_LEVELS),
            "thd_band_sources": [s for _, s in band_source_map],
            "sweep_f1_hz": A.SWEEP_F1,
            "thd_band_orders": [max_measurable_order(b) for b in bands],
        },
        "captures": ok,
        "summary": summary,
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w") as fh:
        json.dump(out, fh, indent=2)
    sys.stderr.write(f"wrote {OUTPUT_JSON}  ({os.path.getsize(OUTPUT_JSON)} bytes)\n")


if __name__ == "__main__":
    main()
