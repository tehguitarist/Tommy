# Tommy — batch-6 capture spec (the recapture that closes the v0.8 gaps)

This is the protocol for the next real-pedal NAM/reamp session. It's designed around the lessons
the v0.8 validation harness surfaced — the test signal was never the limitation, the **capture
settings matrix** was. Follow this and every taper/level becomes cleanly fittable instead of
confounded.

Use the **v2 signal**: regenerate with `python3 analysis/gen_test_signal_v2.py` →
`analysis/tommy_test_signal_v2_48k.wav`. Play THAT through the pedal for every capture below.

## Recording protocol (read first — these are the things that bit us)

1. **Fix the interface gain for the ENTIRE session and never touch it.** Tommy's earlier batches
   had ambiguous absolute level because return gain may have differed between sessions — it cost a
   real investigation to decide the level deficit was genuine. One gain, all captures.
2. **Capture a BYPASS pass first** (pedal in true bypass, same signal). This is the absolute-level /
   unity anchor — it pins what "unity" means at this session's gain, forever. Without it, absolute
   level is unverifiable.
3. **Full length, no truncation.** Two of batch-3's files were truncated to 8 s (no sweep) and the
   harness had to learn to skip them. Each capture must be the full ~71 s.
4. **48 kHz, mono, 32-bit float.** Same as the signal.
5. **One knob at a time.** Hold the other three fixed; step only the knob under test. Confounded
   multi-knob captures (every prior batch) can't be used to fit an individual taper.
6. **EQ is read only from the clean sweep** (`sweep_clean`, -30 dBFS) — keep drive low on the EQ
   sweeps so clip harmonics don't contaminate the tone fit.

## Knob ↔ clock ↔ filename

The analyzer's parser (`analyze.parse_filename`) reads clock HHMM notation. Use it:
`V1200 B0700 T0700 G1030 switch mid tommy_test_signal_v2_48k.wav`

| Clock | 7:00 | 9:00 | 10:30 | 12:00 | 1:00 | 3:00 | 5:00 |
|-------|------|------|-------|-------|------|------|------|
| x (0..1) | 0.00 | 0.20 | 0.35 | 0.50 | 0.60 | 0.80 | 1.00 |

- **Bass / Treble are CUT controls:** 7:00 = no cut (full band), 5:00 = max cut.
- **Drive / Volume conventional:** 7:00 = min, 5:00 = max.
- **switch:** `up` = A = Asym/**Hard** (single diode) · `mid` = O = Open/**Medium** · `down` = S = Sym/**Soft**.

## The matrix (~32 captures, ~40 min)

**0. Bypass anchor** — pedal bypassed. `BYPASS tommy_test_signal_v2_48k.wav`  → 1

**1. VOLUME sweep** *(the #1 gap — no prior batch ever moved Volume)*
Fixed: Drive 7:00, Bass 7:00 (no cut), Treble 7:00 (no cut), switch mid.
Volume = **7:00, 9:00, 12:00, 1:00, 3:00, 5:00**  → 6
*The 1:00 capture directly tests the unity-at-1-o'clock behaviour (plugin currently reads −0.01 dB
through-gain there at min drive / no cut — this confirms it against the real pedal).*

**2. DRIVE sweep × 3 clip modes** *(drive taper + clip character + THD×drive×mode)*
Fixed: Bass 7:00, Treble 7:00, Volume 12:00.
Drive = **7:00, 9:00, 12:00, 3:00, 5:00**  ×  switch = **{up, mid, down}**  → 15

**3. BASS sweep** *(bass taper — convex cut law)*
Fixed: Drive 12:00, Treble 7:00, Volume 12:00, switch mid.
Bass = **7:00, 9:00, 12:00, 3:00, 5:00**  → 5

**4. TREBLE sweep** *(treble taper — resolve the V4-linear vs early-reverse-log question for real)*
Fixed: Drive 12:00, Bass 7:00, Volume 12:00, switch mid.
Treble = **7:00, 9:00, 12:00, 3:00, 5:00**  → 5

**Optional — supply voltage** (self-consistency only; no plugin-vs-real claim, just confirm headroom
ordering): one hot setting (Drive 5:00, switch up, Volume 12:00) at the 9 / 12 / 18 V jack → 3.

## After capturing

1. Drop the files in `analysis/pedal_results6/`.
2. The harness already parses the filenames and skips short files; run:
   - `FINE=1 NAMDIR=analysis/pedal_results6 python3 analysis/run_compare.py` (EQ + level)
   - `python3 analysis/knob_tracking.py analysis/pedal_results6` (pass/fail)
   - `python3 analysis/null_test.py analysis/pedal_results6` (null depth)
3. The Volume sweep lets us finally fit the volume taper (the open batch-3 V0.4 ~4 dB residual) and
   the bypass anchor lets us state absolute level with confidence.
4. Note: v2 segment names differ from v1 (`sweep_drv_-12` etc.). When batch 6 lands, point the
   analyzer at the v2 layout via `gen_test_signal_v2.segment_times()` (its single source of truth) —
   the v1 path stays as-is for batches 1–5.
