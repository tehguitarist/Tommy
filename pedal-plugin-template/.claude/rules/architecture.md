# Architecture Rules (generic pedal plugin)

## Threading

- DSP on the **audio thread**; UI on the **message thread**.
- Cross-thread only via `std::atomic` — no locks/mutexes/allocations on the audio thread.
- Meter levels: `std::atomic<float>` written by audio thread, read by a UI `Timer`.
- Bypass: `std::atomic<bool>` (but the UI should read the APVTS `bypass` parameter directly for
  immediate visual response — see UI note below).
- Parameter changes via `AudioProcessorValueTreeState` (APVTS) with **smoothed** values.

## Plugin structure (template)

```
PedalAudioProcessor : AudioProcessor
  AudioProcessorValueTreeState apvts
  std::array<PedalDSP, 2> dsp          // one inner WDF chain per channel
  juce::AudioBuffer<double> scratch    // double work buffer (WDF is double)
  SmoothedValue<float> inputGain, outputGain, bypassMix
  std::atomic<float>* cached param pointers (avoid string lookups on audio thread)
  std::atomic<float> inputLevelL/R, outputLevelL/R
  std::atomic<bool>  bypassed
  static constexpr float kInputRef     // volts per full-scale (calibration doc §1)
  static constexpr float kOutputMakeup // ~0.9 (calibration doc §2)
```

`PedalDSP` is the per-channel inner chain (input network → gain/clip stage (oversampled) → tone →
recovery stage). Volume/trim/metering live in the processor (plain gains + level reads), not in the
WDF tree.

## Parameters (APVTS)

Typical set — adapt to the pedal. Use `0..1` `AudioParameterFloat` for pot controls and apply the
taper in DSP (keeps host automation linear and the taper in one place):

| ID | Type | Notes |
|----|------|-------|
| pot controls (`gain`, `tone`, `volume`, …) | `AudioParameterFloat` 0..1 | taper applied in DSP |
| mode switch | `AudioParameterChoice` | precomputed topologies |
| `input_trim` / `output_trim` | `AudioParameterFloat` dB | distinct from pedal controls |
| `oversampling` | `AudioParameterChoice` 1×/2×/4×/8× | realtime factor |
| `render_oversampling` | `AudioParameterChoice` | offline-bounce factor (see below) |
| `bypass` | `AudioParameterBool` | APVTS supports bool via this type |

## processBlock structure

```
1. Pick OS factor: isNonRealtime() ? render_oversampling : oversampling. Reinit if changed.
2. Read smoothed params; apply tapers to pot values.
3. Update WDF node values (defer impedance propagation for coupled controls).
4. Per channel:
   a. input trim -> wet (DAW domain); take dry copy for bypass; update INPUT meter (DAW domain)
   b. work = wet * kInputRef          // -> real volts (calibration doc §1)
   c. run WDF chain (input -> oversampled clip -> tone -> recovery)
   d. optional silence gate (zero the block if all |samples| are sub-threshold)
   e. work * outputGain, outputGain = kOutputMakeup * volumeGain * dbToGain(outTrim) / kInputRef
   f. crossfade against dry copy for bypass; update OUTPUT meter (DAW domain)
```
Keep meters + bypass dry path in DAW domain; only the WDF chain sees `kInputRef` volts.

## Oversampling: realtime vs render

Expose two choice params. In `processBlock`, `isNonRealtime()` returns true during offline bounce
(Logic and most DAWs), so the render factor applies automatically with no extra UI action:
```cpp
const int wantFactor = isNonRealtime()
    ? (pRenderOs != nullptr ? (int)pRenderOs->load() : 3)   // default 8x offline
    : (int)pOversampling->load();
```

## Bypass

- True bypass: dry input routed to output, DSP skipped when bypassed.
- ~5 ms crossfade (`SmoothedValue bypassMix`) on transitions to avoid clicks.
- On DAW recall, the UI must reflect the restored `bypass` parameter — read APVTS, not a stale flag.

## prepareToPlay responsibilities

- `.prepare(sampleRate)` on every capacitor in every stage (missing this = silence).
- `oversampler.initProcessing(samplesPerBlock)`.
- Reset smoothed values to current APVTS values (no first-block ramp artefact).
- Reset bypass crossfade state.
- `setLatencySamples()` from the oversampler's reported latency.

## State save/restore

- Full state via `apvts.state` (standard XML serialise). All controls + OS + bypass round-trip.
- Optionally persist UI scale: per-session in `apvts.state` property, cross-session default in
  `ApplicationProperties` (see ui.md).
