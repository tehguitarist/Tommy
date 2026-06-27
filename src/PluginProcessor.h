#pragma once

#include "dsp/TommyDSP.h"

#include <juce_audio_processors/juce_audio_processors.h>

#include <array>

class TommyAudioProcessor : public juce::AudioProcessor
{
public:
    TommyAudioProcessor();
    ~TommyAudioProcessor() override;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;

    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;

    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override;

    const juce::String getName() const override;

    bool acceptsMidi() const override;
    bool producesMidi() const override;
    double getTailLengthSeconds() const override;

    int getNumPrograms() override;
    int getCurrentProgram() override;
    void setCurrentProgram (int index) override;
    const juce::String getProgramName (int index) override;
    void changeProgramName (int index, const juce::String& newName) override;

    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    juce::AudioProcessorValueTreeState apvts;

    // Public meter/state reads for the editor (message thread reads these atomics).
    float getInputLevel (int ch) const { return (ch == 0 ? inputLevelL : inputLevelR).load(); }
    float getOutputLevel (int ch) const { return (ch == 0 ? outputLevelL : outputLevelR).load(); }
    bool isBypassed() const { return bypassed.load(); }

private:
    static juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout();

    // Factory presets (Step 9.5 / v0.9). Knob values stored as physical 0-10 dial positions
    // (matching the printed pedal markings), converted to the 0-1 APVTS range at apply time.
    struct FactoryPreset
    {
        const char* name;
        float bass, drive, treble, volume; // 0-10 dial position
        int clipMode; // 0=Asymmetric, 1=Open, 2=Symmetric
    };
    static const std::array<FactoryPreset, 5> factoryPresets;

    int currentProgramIndex { 0 };

    // Input reference: volts-per-full-scale. Anchors the DAW float to real guitar volts so the
    // nonlinear stages (diodes ~0.3-0.6V, op-amp rails) clip at the physically correct point.
    // Scaled UP entering the WDF chain and DOWN by 1/kInputRef leaving it, so it cancels in the
    // linear path — it changes ONLY where clipping engages, not the clean-signal level/unity.
    //
    // RE-CALIBRATED 2026-06-19 from NAM captures of the real pedal (analysis/): the earlier 3.27
    // (from a 0.7V@-13.4dBFS guitar reading) drove the clipper ~9 dB too hot — the real pedal is
    // CLEAN at min drive up to -6 dBFS (0.1% THD) where 3.27 was already clipping (3.3% THD) and
    // ~4.6 dB compressed. Sweeping against the NAM level/THD curves (analysis/sweep_kinput.py)
    // fits ~1.0-1.5; 1.2 matches Open/Symmetric output to within ~1 dB across the drive range and
    // also collapses the apparent mid-EQ error (which was over-compression, not tone). NOTE: this
    // matches the NAM capture level — verify by ear with the guitar; nudge 1.0-1.5 to taste.
    static constexpr float kInputRef = 1.2f;

    // Output makeup (dimensionless, applied after 1/kInputRef).
    //
    // RE-CALIBRATED 2026-06-27 to the authoritative batch-3/4/5 NAM captures (user confirmed these
    // are the reliable reference, batch 5 = +6 dB hot). The comprehensive validation harness
    // (analysis/knob_tracking.py, run_compare.py) showed the plugin was a ROCK-CONSTANT ~2.6 dB
    // quieter than the real pedal at every clean (sub-clipping) setting — a pure linear-gain
    // deficit, independent of input level AND of volume position (the volume-taper SHAPE was
    // already correct; see analysis decomposition). The cleanest anchor is the pure-linear batch-4
    // no-drive file (V0.5), whose deficit was -2.62 dB dead-constant across -24/-18/-12 dBFS inputs.
    // Fix = boost makeup by +2.62 dB: 0.9 * 10^(2.62/20) = 1.217. This took LEVEL agreement from
    // 0/23 to 16/23 captures. (The earlier 0.9 + its "worst case ≈ -0.6 dBFS" claim were BOTH wrong
    // — untested against these captures; the real pedal is ~2.6 dB louder, and at full drive+volume
    // the faithful output is well above 0 dBFS, managed by the -12 dB output trim + volume knob.)
    //
    // KNOWN RESIDUALS (deliberately NOT masked with makeup — that would be a calibration crutch):
    //  - high-drive: ~2 dB quiet at full drive (clip-output scaling, the documented clipping ceiling)
    //  - V0.4: batch-3 still ~4 dB quiet, hinting the volume taper is too steep below noon — but
    //    that's confounded (one V0.4 point, varying B/G) and needs the batch-6 Volume reamp to fit.
    static constexpr float kOutputMakeup = 1.217f;

    std::array<tommy::dsp::TommyDSP, 2> dsp;
    juce::AudioBuffer<double> scratch; // double work buffer (WDF is double)

    double currentSampleRate { 48000.0 };
    int maxBlock { 512 };
    int currentFactorLog2 { 2 }; // matches "oversampling" default (4x)

    juce::SmoothedValue<float> inputGain, outputGain, bypassMix;

    // Cached APVTS parameter pointers (avoids string lookups on the audio thread).
    std::atomic<float>* pBass { nullptr };
    std::atomic<float>* pDrive { nullptr };
    std::atomic<float>* pTreble { nullptr };
    std::atomic<float>* pVolume { nullptr };
    std::atomic<float>* pClip { nullptr };
    std::atomic<float>* pInTrim { nullptr };
    std::atomic<float>* pOutTrim { nullptr };
    std::atomic<float>* pOversampling  { nullptr };
    std::atomic<float>* pRenderOs      { nullptr };
    std::atomic<float>* pBypass        { nullptr };
    std::atomic<float>* pSupply        { nullptr };

    std::atomic<float> inputLevelL { 0.0f }, inputLevelR { 0.0f };
    std::atomic<float> outputLevelL { 0.0f }, outputLevelR { 0.0f };
    std::atomic<bool> bypassed { false };

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (TommyAudioProcessor)
};
