#!/usr/bin/env python3
"""Generate a test signal for A/B comparing the Tommy plugin against the real pedal.

Layout (48 kHz, mono, 32-bit float). Segments separated by silence so they auto-detect,
but analysis aligns by cross-correlation against this original (handles plugin latency).

  1. 0.5 s silence                         (noise-floor reference)
  2. 1.0 s  1 kHz @ -18 dBFS               (calibration tone)
  3. 0.5 s silence
  4. 10 s  log sweep 20 Hz->20 kHz @ -30 dBFS   (CLEAN: linear EQ / frequency response)
  5. 0.5 s silence
  6. 10 s  log sweep 20 Hz->20 kHz @ -12 dBFS   (DRIVEN: response under clipping)
  7. 0.5 s silence
  8. 1 kHz tones @ -24,-18,-12,-6 dBFS, 1 s each   (gain/compression vs input level)
  9. tones @ -14 dBFS: 82,110,220,440,1000,2000,5000 Hz, 1 s each  (harmonics vs freq)
 10. 0.5 s silence
"""
import numpy as np
from scipy.io import wavfile

FS = 48000
def dbfs(db): return 10.0 ** (db / 20.0)
def silence(sec): return np.zeros(int(sec * FS), dtype=np.float64)

def fade(x, ms=5.0):
    n = int(ms * 1e-3 * FS)
    if n * 2 < len(x):
        r = np.linspace(0, 1, n)
        x[:n] *= r; x[-n:] *= r[::-1]
    return x

def tone(freq, sec, db):
    t = np.arange(int(sec * FS)) / FS
    return fade(dbfs(db) * np.sin(2 * np.pi * freq * t))

def log_sweep(f0, f1, sec, db):
    t = np.arange(int(sec * FS)) / FS
    T = sec
    k = np.log(f1 / f0)
    phase = 2 * np.pi * f0 * T / k * (np.exp(t / T * k) - 1.0)
    return fade(dbfs(db) * np.sin(phase), 10.0)

parts = []
def add(x): parts.append(np.asarray(x, dtype=np.float64))

add(silence(0.5))
add(tone(1000, 1.0, -18))
add(silence(0.5))
add(log_sweep(20, 20000, 10.0, -30))   # clean EQ
add(silence(0.5))
add(log_sweep(20, 20000, 10.0, -12))   # driven
add(silence(0.5))
for db in (-24, -18, -12, -6):          # 1 kHz level steps
    add(tone(1000, 1.0, db)); add(silence(0.3))
for f in (82.41, 110, 220, 440, 1000, 2000, 5000):  # freq steps @ -14 dBFS
    add(tone(f, 1.0, -14)); add(silence(0.3))
add(silence(0.5))

sig = np.concatenate(parts).astype(np.float32)
wavfile.write("analysis/tommy_test_signal_48k.wav", FS, sig)
print(f"wrote analysis/tommy_test_signal_48k.wav  ({len(sig)/FS:.1f} s, {len(sig)} samples, {FS} Hz)")
print(f"peak = {np.max(np.abs(sig)):.3f}  ({20*np.log10(np.max(np.abs(sig))):.1f} dBFS)")
