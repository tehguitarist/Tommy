# Architecture Rules

## Threading

- All DSP runs on the **audio thread**
- All UI runs on the **message thread**
- Cross-thread communication: `std::atomic` only — no locks, mutexes, or blocking calls on the audio thread
- Meter levels: `std::atomic<float>` written by audio thread, read by UI timer
- Bypass state: `std::atomic<bool>`
- Parameter changes: JUCE `AudioProcessorValueTreeState` with smoothed parameter values (no zipper noise)

## Plugin Structure

```
TommyAudioProcessor          ← AudioProcessor subclass
  AudioProcessorValueTreeState apvts
  InputTrimStage
  DriveStage (WDF, oversample wrapper)
    InputBuffer (linear WDF)
    Stage1 (linear WDF, IC1_A ideal op-amp)
    ClippingOversampler (nonlinear WDF, 3 precomputed topologies)
    TrebleNetwork (linear WDF passive)
    Stage2 (linear WDF, IC1_B ideal op-amp)
  VolumePot (linear)
  OutputTrimStage
  std::atomic<float> inputLevelL, inputLevelR
  std::atomic<float> outputLevelL, outputLevelR
  std::atomic<bool> bypassed
```

## Parameters (APVTS IDs)

| ID | Label | Range | Default | Notes |
|----|-------|-------|---------|-------|
| `bass` | Bass | 0.0–1.0 | 0.0 (knob at minimum) | Linear in APVTS; audio taper applied in DSP |
| `drive` | Gain | 0.0–1.0 | 0.0 (knob at minimum) | Linear in APVTS; audio taper applied in DSP |
| `treble` | Treble | 0.0–1.0 | 0.0 (knob at minimum) | Linear in APVTS; audio taper applied in DSP |
| `volume` | Volume | 0.0–1.0 | 0.5 + 30/288 ≈ 0.6042 (knob at 1 o'clock) | Linear in APVTS; audio taper applied in DSP (A25K pot + R11 18k, see `circuit.md`). The 0.5→noon mapping comes from the LookAndFeel's default 288° rotary sweep; see `ui.md` Controls — Knobs. |
| `clipping_mode` | Clipping | 0/1/2 | 1 (Open) | `AudioParameterChoice`: "Asymmetric" (top lever, single diode, = Hard) / "Open" (middle, one diode pair, = Medium) / "Symmetric" (bottom, all four diodes, = Soft). UI shows these as A/O/S — see `ui.md` SW1 section. |
| `input_trim` | Input Trim | -12.0 to +12.0 dB | 0.0 | Linear dB; `AudioParameterFloat` |
| `output_trim` | Output Trim | -12.0 to +12.0 dB | 0.0 | Linear dB; `AudioParameterFloat` |
| `oversampling` | Oversampling (live) | 0/1/2/3 | 1 (2x) | `AudioParameterChoice`: "1x" / "2x" / "4x" / "8x" — used during real-time playback |
| `render_oversampling` | Oversampling (render) | 0/1/2/3 | 3 (8x) | Same choices; independent factor used for offline rendering/export (CPU is free offline → cleanest render) |
| `bypass` | Bypass | true/false | false | `AudioParameterBool` — APVTS does support bool via this type |
| `supply_voltage` | Supply | 0/1/2 | 0 (9V) | `AudioParameterChoice`: "9V" / "12V" / "18V" — scales op-amp rail headroom only, diode thresholds unchanged |
| `hq` | HQ | true/false | true | `AudioParameterBool` — diode solve quality: on = `AccurateOmega` (shipped), off = fast `omega4` (~45% cheaper diode solve, ~−30..−44 dB distortion floor). Runtime switch in `AsymDiodePairT::setHighQuality` (no template re-instantiation). See `dsp.md` Omega accuracy + `CLAUDE.md` v1.1. |

Note: APVTS does not accept raw `bool` in `createParameterLayout()`. Use `std::make_unique<AudioParameterBool>("bypass", "Bypass", false)`.

## Bypass

- True bypass: input routed directly to output, zero DSP when bypassed
- Crossfade on bypass transition (short ramp, ~5ms) to prevent clicks
- `std::atomic<bool> bypassed` — audio thread polls this, applies ramp
- On DAW recall, bypass visual state must reflect the restored parameter value — the UI reads from APVTS on load, not from a separate flag

## Oversampling

- `juce::dsp::Oversampling` spans Stage 1 → Treble → Stage 2 (not the nonlinear stage alone — see
  `dsp.md`'s Oversampling section for why the linear downstream stages are included too).
- Two independent factors: `oversampling` (live) and `render_oversampling` (render/offline), both
  plain APVTS choice parameters — no separate `pendingOversamplingFactor` atomic. `processBlock`
  picks the live or render parameter via `isNonRealtime()`, compares it against the cached
  `currentFactorLog2`, and if changed calls `setFactor()` on each channel's DSP chain (which
  re-inits the oversampler and updates `setLatencySamples()`). This causes a brief gap (one block)
  on a factor change — acceptable; do not attempt sample-accurate crossfading across it.
- Call `.prepare()`/init on every oversampler in `prepareToPlay`.

## prepareToPlay Responsibilities

All of the following must happen in `prepareToPlay(sampleRate, samplesPerBlock)`:
- Call `.prepare(sampleRate)` on every `CapacitorT` in every WDF stage (missing this causes silence)
- Call `oversampler.initProcessing(samplesPerBlock)`
- Reset all smoothed parameter values to current APVTS values (prevents ramp-up artefact on first block)
- Reset bypass crossfade state

Each DSP stage class (InputBuffer, Stage1, ClippingOversampler, TrebleNetwork, Stage2) must expose a `prepare(double sampleRate)` method that chains `.prepare(sampleRate)` down to all its capacitors. `prepareToPlay` calls each stage's `prepare()` in signal-chain order. This ensures sample-rate changes between DAW sessions are handled correctly — JUCE calls `prepareToPlay` on every SR change.

## processBlock Structure

```
1. Check pendingOversamplingFactor — reinit if changed
2. Read all APVTS parameter values (smoothed)
3. Apply audio taper conversion to pot values
4. Update WDF node values (use ScopedDeferImpedancePropagation for BASS+DRIVE)
5. If bypassed: copy input to output directly, update input meter, skip DSP
6. Else:
   a. Apply input trim gain
   b. Update input meter levels (std::atomic write)
   c. Upsample nonlinear stage block
   d. Process full WDF chain sample by sample
   e. Downsample nonlinear stage block
   f. Apply output trim gain
   g. Update output meter levels (std::atomic write)
```

## State Save/Restore

- Full state via `AudioProcessorValueTreeState::state` (standard JUCE XML serialise)
- Oversampling and all pedal controls saved/restored
- Bypass state saved/restored via APVTS `bypass` parameter
