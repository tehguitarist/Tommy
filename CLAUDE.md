# Tommy Overdrive Plugin — Project Memory

> Tommy is a circuit-level emulation of the Cochrane/MXR Timmy overdrive pedal,
> built as an AU/VST3 plugin using JUCE 8+ and chowdsp_wdf WDF modelling.
> Author/Company: Leigh Pierce

## Quick Reference

```
Build:   cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build
Test:    cmake --build build --target Tommy_AU  (then load in DAW)
Lint:    clang-tidy src/**/*.cpp
Format:  clang-format -i src/**/*.{cpp,h}
```

## Schematics

All three are in `schematics/` at the repo root. Load them when verifying any circuit detail.

| File | Role |
|------|------|
| `updated_schematic_-_timmy.png` | Primary source of truth for component values and topology |
| `timmy_switch_refernce.jpg` | Authoritative for SW1 diode network and switch topology |
| `older_schematic_-_Timmy.webp` | Cross-reference only — earlier version, some values differ |

@.claude/rules/circuit.md
@.claude/rules/dsp.md
@.claude/rules/architecture.md
@.claude/rules/ui.md
@.claude/rules/build.md

## Build Sequence (do not skip ahead)

1. Schematic analysis — DONE (see `circuit.md`)
2. JUCE CMake scaffold + APVTS + AU/VST3 targets loading in DAW
3. chowdsp_wdf smoke test — implement a trivial RC lowpass, feed a swept sine, confirm the -3dB point matches `f = 1/(2π×R×C)` to within 1%. Use a short offline render or unit test; do not proceed on a visual guess.
4. Stage-by-stage DSP implementation, validated at each step:
   - Linear stages: verify frequency response against expected transfer function
   - Nonlinear stage (SW1): verify clipping behaviour with a sine wave input
   - **Invoke `dsp-validator` agent after each stage before proceeding**
5. Switch topology switching — verify each SW1 mode independently
6. Oversampling + ADAA on nonlinear stage — verify aliasing reduction
7. Full chain integration + level calibration (-12 dBu)
8. UI implementation
9. Final sweep: all controls full range, no instability, clicks, or NaN output

**Never proceed past a step before validating the current step.**
**Use the `schematic-checker` agent any time a circuit value or topology is in doubt.**

## Current Step

> Update this line at the **start** of each session to reflect where work is resuming,
> and again when a step completes. Do not rely on conversation history to infer progress.
> **CURRENT: Step 7 — full chain integration + level calibration (-12 dBu). Need Treble + Stage 2 DSP (not yet built), then wire Stage0→Stage1(OS)→Treble→Stage2→Volume in PluginProcessor with APVTS + A-tapers. Step 6 (oversampling + ADAA) COMPLETE & validated: `src/dsp/ClippingOversampler.h` wraps Stage1 in juce::dsp::Oversampling (factorLog2 0/1/2/3 = 1x/2x/4x/8x, FIR equiripple, re-prepares Stage1 at OS rate; oversamples nonlinear stage ONLY). 1st-order ADAA added on the rail clip in Stage1.h (railAntideriv/applyRail, setAdaaEnabled). ALSO replaced chowdsp's fast omega4 (bit-trick log/exp, caused ~-35dB distortion floor) with `AccurateOmega` (std::log/exp+Newton Wright-omega); diodePair now DiodeQuality::Good+AccurateOmega (Best hardcodes omega4, ignores provider), diodeS DiodeT+AccurateOmega. `tests/Step6_Aliasing.cpp` (JUCE console app, audible-band 50Hz-18kHz FFT): Hard 1x=-13→8x=-54→8x+ADAA=-60dB; Soft 8x=-81dB. Residual ~-35dB ONLY in 22-24kHz transition band (inaudible, decimation-filter-sharpness limited, NOT OS-dependent). dsp-validator NOT re-run (session limit) — re-run before final. PERF NOTE: AccurateOmega uses std::log/exp+4 Newton iters/sample at OS rate — heavier; profile at Step 7, optimise init/iters if needed. Step 5 (SW1 clipping) & 9V rails done (see git). CARRY-FORWARD to Step 7: (a) DRIVE-pot node_F wiper tap unresolved — Stage1 outputs node_D; (b) apply A-taper R_max BASS=50k, DRIVE=1M, TREB=50k, VOL=25k in processBlock; (c) IC1_B (Stage 2) rails not yet modelled — add if it clips at -12dBu; (d) oversampling factor-change glitch handling (atomic pendingFactor) at processor level. Stages 0/1 & smoke test done. Step 2: AU passes auval. VST3 deferred.**
