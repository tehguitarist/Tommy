#!/usr/bin/env python3
"""Extract the TREBLE low-pass corner vs knob position from the pedal_results3 NAM captures,
then back out the TREB rheostat resistance (given R5=1k, C5=10n) and see what taper law fits.
The treble net is a 1st-order LP: |H_treb(f)| = 1/sqrt(1+(f/fc)^2), fc = 1/(2pi*(TREB_R+R5)*C5)."""
import re, glob, os, numpy as np
import analyze as A

R5, C5 = 1.0e3, 10.0e-9
orig = A.load("analyze_orig" if False else "analysis/tommy_test_signal_48k.wav")

def knobs(name):
    g = lambda k: int(re.search(rf"{k}(\d)", name).group(1)) / 10.0
    return dict(G=g("G"), V=g("V"), B=g("B"), T=g("T"))

files = sorted(glob.glob("analysis/pedal_results3/*.wav"))
inp = A.seg_of(orig, "sweep_clean")

# Build transfer functions
data = {}
for f in files:
    x, _ = A.align(A.load(f), orig)
    fr, mag = A.transfer(A.seg_of(x, "sweep_clean"), inp)
    data[f] = (knobs(os.path.basename(f)), fr, mag)

def gain_at(fr, mag, hz): return mag[np.argmin(np.abs(fr - hz))]

# Use the brightest capture (highest treble% = least cut on this MXR-direction pedal) as the
# treble reference, and isolate each setting's extra rolloff by ratio (cancels common circuit).
ref = max(data, key=lambda f: data[f][0]["T"])
_, frR, magR = data[ref]
print(f"reference (brightest treble) = T{int(data[ref][0]['T']*10)}: {os.path.basename(ref)}\n")

print("file (knobs)            T%   fc(-3dB rel bright)   impliedTREB_R   linear?  audio?")
fitpts = []
for f in sorted(data, key=lambda f: data[f][0]["T"]):
    k, fr, mag = data[f]
    rel = mag - magR  # dB, relative to brightest -> treble LP rolloff of this setting
    # find -3 dB crossing of rel (scanning up from 1 kHz)
    band = (fr >= 800) & (fr <= 16000)
    fb, rb = fr[band], rel[band]
    idx = np.where(rb <= -3.0)[0]
    fc = fb[idx[0]] if len(idx) else float("inf")
    # back out TREB_R from fc (absolute corner of a 1st-order LP)
    if np.isfinite(fc):
        treb_r = 1.0 / (2 * np.pi * fc * C5) - R5
    else:
        treb_r = 0.0
    T = k["T"]
    # what would linear (R=Tx*Rmax) and audio (10^(2T-2)) predict, for Rmax guesses
    print(f"  T{int(T*10)} G{int(k['G']*10)} B{int(k['B']*10)}   {T:.1f}   "
          f"fc={fc:7.0f} Hz        {treb_r/1e3:6.1f} k")
    if np.isfinite(fc) and treb_r > 100:
        fitpts.append((T, treb_r))

print("\nTREB_R vs knob (from data) — fit taper law:")
if len(fitpts) >= 2:
    Ts = np.array([p[0] for p in fitpts]); Rs = np.array([p[1] for p in fitpts])
    # NOTE: this MXR pedal cuts as knob goes DOWN, so cut (R) is largest at LOW T.
    # Plugin wants cut largest at HIGH x, so plug_x = 1 - T_mxr for the same cut.
    print("   T(mxr)  TREB_R(k)   plug_x=1-T   ")
    for T, R in zip(Ts, Rs):
        print(f"    {T:.1f}    {R/1e3:7.1f}       {1-T:.1f}")
    # linear fit R = a*(1-T) + b  (cut vs plugin rotation)
    px = 1 - Ts
    Acoef = np.polyfit(px, Rs, 1)
    print(f"\n   linear fit  TREB_R ≈ {Acoef[0]/1e3:.0f}k * x + {Acoef[1]/1e3:.1f}k   (x = plugin rotation)")
    # implied full-rotation (x=1) resistance:
    print(f"   => implied max TREB_R at x=1: {(Acoef[0]+Acoef[1])/1e3:.0f}k")
