#!/usr/bin/env python3
"""Self-consistency checks for the two controls that have NO real-pedal capture to validate against:
the Volume knob (every NAM batch fixed it) and the 9/12/18 V supply selector (no 12/18 V captures
exist). These are therefore SELF-consistency checks — sanity/monotonicity of the shipped DSP path,
NOT accuracy-vs-real claims. Both drive the real OfflineRender binary (the shipped gain staging),
not a Python re-implementation.

  VOLUME  — render a clean (low-drive) setting at increasing Volume positions and confirm output
            level rises monotonically across the full sweep, with a sane audio-taper spacing (no
            dead zone, no reversal). [The Volume taper still uses the generic 10^(2x-2) law that was
            already replaced by fitted laws for every other control — flagged for a future reamp.]
  SUPPLY  — render a hard-clipping hot setting at 9/12/18 V and confirm peak output rises with
            supply voltage (more rail headroom = bigger clean swing before the op-amp rails clip).
            Diode thresholds are unchanged, so this must be a pure headroom effect, never a reversal.

Usage:  python3 analysis/volume_supply_check.py
"""
import subprocess, numpy as np
import analyze as A

REND = "build/OfflineRender_artefacts/Release/OfflineRender"

# Full positional arg layout of offline_render.cpp (see its header). Defaults match PluginProcessor.
#   1 in  2 out  3 bass  4 drive  5 treb  6 vol  7 mode  8 factorLog2  9 sr  10 kInputRef
#   11 trebCoeff 12 trebExp 13 bassCoeff 14 bassExp 15 asymBias 16 unused 17 driveCoeff 18 driveExp
#   19 supplyV   20 symBias
def render(bass, drive, treb, vol, mode, supplyV=9.0, kin=1.2):
    A.load(A.ORIG).astype(np.float32).tofile("/tmp/vs_orig.f32")
    args = [REND, "/tmp/vs_orig.f32", "/tmp/vs_out.f32",
            f"{bass}", f"{drive}", f"{treb}", f"{vol}", str(mode), "3", "48000",
            f"{kin}",         # kInputRef
            "-1", "1.43", "-1", "1.43",   # treb/bass coeff/exp (shipped taper)
            "-1", "0",        # asymBias, unused
            "-1", "1.0",      # driveCoeff, driveExp (shipped taper)
            f"{supplyV}"]     # supplyV
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    orig = A.load(A.ORIG)
    x, _ = A.align(np.fromfile("/tmp/vs_out.f32", dtype=np.float32).astype(np.float64), orig)
    return x


def volume_check():
    print("VOLUME monotonicity (clean setting B0.3 G0.1 T0.0 mode Soft):")
    print("  vol     out @1kHz(-12) dBFS   step")
    levels = []
    prev = None
    ok = True
    for v in (0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0):
        x = render(0.3, 0.1, 0.0, v, 2)
        lvl = A.rms_db(A.seg_of(x, "lvl-12"))
        step = "" if prev is None else f"{lvl - prev:+.2f}"
        if prev is not None and lvl < prev - 0.05:   # allow tiny numeric noise
            step += "  <-- NON-MONOTONIC"; ok = False
        print(f"  {v:>4.2f}   {lvl:>16.2f}      {step}")
        levels.append(lvl); prev = lvl
    print(f"  => VOLUME {'OK — monotonic rise' if ok else 'FAIL — non-monotonic'} "
          f"(total range {levels[-1]-levels[0]:.1f} dB)\n")


def supply_check():
    # Must drive HARD into the op-amp rails for the supply to matter (it only changes the rail-clip
    # threshold; below the rails it's a no-op — see CLAUDE.md). Use a very hot input (kIn=6) and a
    # low volume (0.3) so the rails clip internally while the digital output stays below 0 dBFS.
    print("SUPPLY headroom ordering (hot kIn=6, B0.65 G1.0 T0.35 mode Hard, low vol so rails clip):")
    print("  supply   peak dBFS    driven-sweep RMS dBFS")
    peaks = []
    prev = None
    ok = True
    for sv in (9.0, 12.0, 18.0):
        x = render(0.65, 1.0, 0.35, 0.3, 0, supplyV=sv, kin=6.0)
        seg = A.seg_of(x, "sweep_driven")
        peak = 20 * np.log10(np.max(np.abs(seg)) + 1e-20)
        rms = A.rms_db(seg)
        flag = ""
        if prev is not None and peak < prev - 0.05:
            flag = "  <-- REVERSAL"; ok = False
        print(f"  {sv:>5.0f}V   {peak:>8.2f}    {rms:>14.2f}{flag}")
        peaks.append(peak); prev = peak
    print(f"  => SUPPLY {'OK — headroom rises with voltage' if ok else 'FAIL — reversal'} "
          f"(9V->18V peak +{peaks[-1]-peaks[0]:.1f} dB)\n")


if __name__ == "__main__":
    print("\nVolume + supply self-consistency (no real-pedal reference exists for either)\n")
    volume_check()
    supply_check()
