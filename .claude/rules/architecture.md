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
    SW1ClippingStage (nonlinear WDF, 3 precomputed topologies)
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
| `bass` | Bass | 0.0–1.0 | 0.5 | Linear in APVTS; audio taper applied in DSP |
| `drive` | Gain | 0.0–1.0 | 0.5 | Linear in APVTS; audio taper applied in DSP |
| `treble` | Treble | 0.0–1.0 | 0.5 | Linear in APVTS; audio taper applied in DSP |
| `volume` | Volume | 0.0–1.0 | 0.5 | Linear in APVTS; audio taper applied in DSP (A10k pot) |
| `clipping_mode` | Clipping | 0/1/2 | 0 | `AudioParameterChoice`: "Soft" / "Medium" / "Hard" |
| `input_trim` | Input Trim | -12.0 to +12.0 dB | 0.0 | Linear dB; `AudioParameterFloat` |
| `output_trim` | Output Trim | -12.0 to +12.0 dB | 0.0 | Linear dB; `AudioParameterFloat` |
| `oversampling` | Oversampling | 0/1/2/3 | 2 (4x) | `AudioParameterChoice`: "1x" / "2x" / "4x" / "8x" |
| `bypass` | Bypass | true/false | false | `AudioParameterBool` — APVTS does support bool via this type |

Note: APVTS does not accept raw `bool` in `createParameterLayout()`. Use `std::make_unique<AudioParameterBool>("bypass", "Bypass", false)`.

## Bypass

- True bypass: input routed directly to output, zero DSP when bypassed
- Crossfade on bypass transition (short ramp, ~5ms) to prevent clicks
- `std::atomic<bool> bypassed` — audio thread polls this, applies ramp
- On DAW recall, bypass visual state must reflect the restored parameter value — the UI reads from APVTS on load, not from a separate flag

## Oversampling

- `juce::dsp::Oversampling` around nonlinear stage only
- Changing oversampling factor: detected via `std::atomic<int> pendingOversamplingFactor` set by UI thread; audio thread checks at the start of each `processBlock`, and if changed: calls `oversampler.reset()` then `oversampler.initProcessing(maxBlockSize)`, then updates the internal factor. This causes a brief gap (one block) which is acceptable — do not attempt sample-accurate crossfading across an oversampling change.
- Call `oversampler.initProcessing(samplesPerBlock)` in `prepareToPlay`

## prepareToPlay Responsibilities

All of the following must happen in `prepareToPlay(sampleRate, samplesPerBlock)`:
- Call `.prepare(sampleRate)` on every `CapacitorT` in every WDF stage (missing this causes silence)
- Call `oversampler.initProcessing(samplesPerBlock)`
- Reset all smoothed parameter values to current APVTS values (prevents ramp-up artefact on first block)
- Reset bypass crossfade state

Each DSP stage class (InputBuffer, Stage1, ClippingStage, TrebleNetwork, Stage2) must expose a `prepare(double sampleRate)` method that chains `.prepare(sampleRate)` down to all its capacitors. `prepareToPlay` calls each stage's `prepare()` in signal-chain order. This ensures sample-rate changes between DAW sessions are handled correctly — JUCE calls `prepareToPlay` on every SR change.

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
