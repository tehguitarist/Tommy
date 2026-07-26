#!/usr/bin/env python3
"""Tommy-specific capture I/O and OfflineRender argument mapping for comprehensive_report.py.

Targets `analysis/pedal2` — the v2-signal batch-6 recapture (see CAPTURE_SPEC.md). That's the only
capture set with all three driven-sweep depths (-18/-12/-6 dBFS) and the full 8-tone discrete THD
anchor set comprehensive_report.py's per-band FR/THD/harmonic analysis needs; `pedal1` predates the
v2 spec (single driven sweep, 7 tones, 0-10 notation) and CLAUDE.md already treats pedal2 as the
definitive tone reference.

offline_render.cpp has no --os flag or WAV I/O — it takes raw float32 in/out paths and positional
knob args (bassX driveX trebX volX modeIdx factorLog2 [sr]). render_plugin() in
comprehensive_report.py does the WAV<->raw-float32 conversion; render_args() here only builds the
positional knob/mode/OS-factor arguments.
"""
import glob
import os

import analyze as A

RENDER_BIN = "build/OfflineRender_artefacts/Release/OfflineRender"
CAPTURE_DIR = "analysis/pedal2"
OS_FACTOR_LOG2 = 3  # 8x — matches run_compare.py/knob_tracking.py/null_test.py's validation default

_MODE_TO_REV = {"up": "Hard", "mid": "Medium", "down": "Soft"}  # circuit.md SW1 mode names


def parse_capture(filename):
    """Parse a pedal2 clock-notation filename via the shared analyze.parse_filename() parser.
    `rev` is the clip mode (Tommy has no hardware revisions, unlike the template's multi-pedal
    default) — grouping per-revision summaries by clip mode is the meaningful split here."""
    p = A.parse_filename(os.path.basename(filename))
    return {
        "rev": _MODE_TO_REV[p["sw"]],
        "bass": p["B"],
        "drive": p["G"],
        "treble": p["T"],
        "volume": p["V"],
        "mode": p["mode"],
    }


def find_captures(directory=CAPTURE_DIR):
    """Return sorted [(path, parsed_dict), ...] for every .wav under directory."""
    if not os.path.isdir(directory):
        return []
    return [(p, parse_capture(p)) for p in sorted(glob.glob(os.path.join(directory, "*.wav")))]


def load_capture(path, expect_fs=48000):
    """Tommy's captures are already correctly-labelled 48 kHz mono WAVs (see CAPTURE_SPEC.md's
    recording protocol) — no rate-mislabel correction needed, unlike the templated NAM skeleton."""
    return A.load(path)


def render_args(parsed, os_factor_log2=None, extra_args=None):
    """Positional args for OfflineRender AFTER the in/out raw-float32 paths."""
    log2 = OS_FACTOR_LOG2 if os_factor_log2 is None else os_factor_log2
    args = [
        f"{parsed['bass']:.4f}",
        f"{parsed['drive']:.4f}",
        f"{parsed['treble']:.4f}",
        f"{parsed['volume']:.4f}",
        str(parsed["mode"]),
        str(log2),
        "48000",
    ]
    if extra_args:
        args += list(extra_args)
    return args
