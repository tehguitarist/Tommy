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

    // Input reference: volts-per-full-scale. Anchors the DAW float to real guitar volts so the
    // nonlinear stages (diodes ~0.3-0.6V, op-amp rails +-2.5/3.4V from VREF) clip at the
    // physically correct point relative to the player's dynamics. Calibrated 2026-06-18 from a
    // measured humbucker peak: 0.7 V at -13.4 dBFS (=0.214 float) => 0.7/0.214 ~= 3.27 V/FS
    // (implies the interface Hi-Z input maps ~3.27 V peak to 0 dBFS at 0 gain). The signal is
    // scaled UP by this entering the WDF chain and DOWN by 1/kInputRef leaving it, so K_in
    // cancels in the linear path — it changes ONLY where clipping engages, not clean-signal level.
    static constexpr float kInputRef = 3.27f;

    // Output makeup (dimensionless, applied after 1/kInputRef). The physically-honest value is 1.0
    // (output voltage measured at the same volts-per-full-scale reference as the input); set to 0.9
    // as the closest-to-real value that still guarantees no output clipping. Ceiling check: Stage 2's
    // worst-case rail is 3.4 V, so the loudest possible output (full drive + full volume) peaks at
    // 3.4 * 0.9 / kInputRef ≈ -0.6 dBFS — just under 0 dBFS. This is a deliberate ~1 dB headroom pad,
    // NOT a calibration crutch: with the input load anchored (kInputRef) the circuit sets unity on
    // its own (~1 o'clock at min drive). 1.0 would be exact but can tick ~+0.3 dBFS at the extreme
    // corner. Re-calibrated 2026-06-18 alongside the DRIVE taper fix (which dropped min-drive gain
    // 7.7 dB, 8.96x→3.71x — without it this makeup would sit much lower). Tune by ear within 0.8-1.0.
    static constexpr float kOutputMakeup = 0.9f;

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

    std::atomic<float> inputLevelL { 0.0f }, inputLevelR { 0.0f };
    std::atomic<float> outputLevelL { 0.0f }, outputLevelR { 0.0f };
    std::atomic<bool> bypassed { false };

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (TommyAudioProcessor)
};
