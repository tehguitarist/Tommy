#!/usr/bin/env python3
"""Tommy v2 comprehensive capture signal — closes the gaps the v0.8 validation work exposed.

Writes a NEW file (`tommy_test_signal_v2_48k.wav`) and does NOT touch the original
`gen_test_signal.py` / `tommy_test_signal_48k.wav`: batches 1-5 were captured with v1 and their
analysis (analyze.py's hard-coded T{} layout) stays valid. v2 is for the next capture session
(batch 6+) — see analysis/CAPTURE_SPEC.md for the settings matrix to record against it.

What v2 adds over v1 (the gaps the harness found):
  - Three DRIVEN sweeps (-18/-12/-6 dBFS), all 10 s like the clean sweep, so the Farina
    harmonic-separation (swept_thd.py) has consistent, well-spaced harmonic impulse responses at
    three drive depths instead of one. (v1 had a single 10 s driven sweep at -12 only.)
  - Intermodulation tests: SMPTE (60 Hz + 7 kHz, 4:1) AND a GUITAR-BAND twin-tone (220 Hz + 660 Hz,
    a musical 5th) — the latter is where audible chord intermod actually lives. (CCIF 19 k+20 k was
    deliberately NOT included: both tones sit near Nyquist where the pedal has rolled everything off
    and the plugin's antialiasing vs the analog pedal makes the A/B unreliable — low value for a
    guitar pedal.)
  - Finer level steps (-30..-3 dBFS, 3 dB) for the compression curve, hotter top than v1's -6.
  - Plucked decay notes (220 Hz, 1 kHz) for touch/dynamic response — cheap insurance in case the
    9/12/18 V rail interplay shows any envelope dependence (Tommy is mostly memoryless, so these
    are a secondary check, not a primary metric).

Single source of truth: the analyzer imports `segment_times()` / `SWEEP_F0` / `SWEEP_F1` from here
so segment timings + sweep parameters never drift between generator and analysis.

Layout (48 kHz, mono, 32-bit float). Segments bracketed by silence; analysis keys off the
documented timings (robust to plugin/NAM latency by analysing each segment's steady middle).
"""
import numpy as np

FS = 48000

# Sweep parameters — shared with the analyzer's Farina inverse filter (import these, don't re-type).
SWEEP_F0 = 20.0
SWEEP_F1 = 20000.0
SWEEP_CLEAN_SEC = 10.0
SWEEP_DRIVEN_SEC = 10.0                 # v2: 10 s (was 8 s) — consistent Farina length, cleaner sep
DRIVEN_LEVELS_DB = (-18, -12, -6)       # v2: three drive depths (was one, -12)

# Discrete tones (Hz) @ -14 dBFS — densified through 1-8 kHz; these are validation ANCHORS for the
# continuous swept-THD curve (swept_thd.py --validate), so a modest set is enough.
TONE_FREQS = (82.41, 110, 220, 440, 1000, 2000, 4000, 8000)

LEVEL_STEPS_DB = tuple(range(-30, -2, 3))   # -30,-27,...,-3 — compression curve

GAP = 0.3          # silence between segments (s)
TONE_SEC = 0.8     # discrete tone / level-step duration (s)


def dbfs(db):
    return 10.0 ** (db / 20.0)


def silence(sec):
    return np.zeros(int(sec * FS), dtype=np.float64)


def fade(x, ms=5.0):
    n = int(ms * 1e-3 * FS)
    if n * 2 < len(x):
        r = np.linspace(0, 1, n)
        x[:n] *= r
        x[-n:] *= r[::-1]
    return x


def tone(freq, sec, db):
    t = np.arange(int(sec * FS)) / FS
    return fade(dbfs(db) * np.sin(2 * np.pi * freq * t))


def log_sweep(sec, db, f0=SWEEP_F0, f1=SWEEP_F1):
    """True exponential sine sweep (Farina ESS): instantaneous freq f(t)=f0*exp(t/T*k), k=ln(f1/f0)."""
    t = np.arange(int(sec * FS)) / FS
    T = sec
    k = np.log(f1 / f0)
    phase = 2 * np.pi * f0 * T / k * (np.exp(t / T * k) - 1.0)
    return fade(dbfs(db) * np.sin(phase), 10.0)


def twin_tone(f_lo, f_hi, sec, db_peak, ratio_lo=1.0, ratio_hi=1.0):
    """Two summed tones, scaled so the peak sits at db_peak (amplitudes in ratio_lo:ratio_hi)."""
    t = np.arange(int(sec * FS)) / FS
    a_lo = ratio_lo / (ratio_lo + ratio_hi)
    a_hi = ratio_hi / (ratio_lo + ratio_hi)
    x = a_lo * np.sin(2 * np.pi * f_lo * t) + a_hi * np.sin(2 * np.pi * f_hi * t)
    x *= dbfs(db_peak) / (np.max(np.abs(x)) + 1e-20)
    return fade(x)


def plucked(freq, sec, db_peak, decay_tau=0.35):
    """A plucked note: fast attack, exponential decay — sweeps DOWN through the drive range as it
    decays, so analysis can track harmonic content vs instantaneous level (touch-sensitivity)."""
    t = np.arange(int(sec * FS)) / FS
    env = np.exp(-t / decay_tau)
    atk = int(0.003 * FS)
    env[:atk] *= np.linspace(0, 1, atk)
    return dbfs(db_peak) * env * np.sin(2 * np.pi * freq * t)


def build_segments():
    """Ordered list of (name, audio_array). Pure data — no I/O."""
    segs = []
    segs.append(("cal_1k", tone(1000, 1.0, -18)))                      # level-calibration anchor
    segs.append(("sweep_clean", log_sweep(SWEEP_CLEAN_SEC, -30)))      # CLEAN EQ (read EQ ONLY here)
    for db in DRIVEN_LEVELS_DB:
        segs.append((f"sweep_drv_{db}", log_sweep(SWEEP_DRIVEN_SEC, db)))   # driven THD-vs-freq
    for db in LEVEL_STEPS_DB:
        segs.append((f"lvl_{db}", tone(1000, TONE_SEC, db)))          # compression vs input level
    for f in TONE_FREQS:
        segs.append((f"tone_{f:g}", tone(f, TONE_SEC, -14)))          # discrete THD anchors
    segs.append(("imd_smpte", twin_tone(60, 7000, 2.0, -12, ratio_lo=4.0, ratio_hi=1.0)))  # SMPTE IMD
    segs.append(("imd_guitar", twin_tone(220, 660, 2.0, -12)))        # guitar-band twin-tone (5th)
    segs.append(("decay_220", plucked(220, 1.5, -6)))                 # touch / dynamic response
    segs.append(("decay_1k", plucked(1000, 1.5, -6)))
    return segs


def assemble(lead=0.5, gap=GAP, tail=0.5):
    """Concatenate segments with lead/gap/tail silence; return (signal, timing_map).
    timing_map[name] = (t0, t1) bounds the AUDIO of that segment in seconds."""
    parts = [silence(lead)]
    pos = lead
    times = {}
    for name, audio in build_segments():
        t0 = pos
        parts.append(audio)
        pos += len(audio) / FS
        times[name] = (t0, pos)
        parts.append(silence(gap))
        pos += gap
    parts.append(silence(tail - gap if tail > gap else 0.0))
    sig = np.concatenate(parts).astype(np.float32)
    return sig, times


def segment_times():
    """Timing map only — the analyzer's single source of truth for v2 segment bounds."""
    return assemble()[1]


if __name__ == "__main__":
    from scipy.io import wavfile

    sig, times = assemble()
    out = "analysis/tommy_test_signal_v2_48k.wav"
    wavfile.write(out, FS, sig)
    peak = float(np.max(np.abs(sig)))
    print(f"wrote {out}  ({len(sig)/FS:.1f} s, {len(sig)} samples, {FS} Hz)")
    print(f"peak = {peak:.3f}  ({20*np.log10(peak+1e-20):.1f} dBFS)")
    print("\nsegment timing map (s):")
    for name, (t0, t1) in times.items():
        print(f"  {name:16} {t0:7.3f} .. {t1:7.3f}  ({t1-t0:.2f}s)")
