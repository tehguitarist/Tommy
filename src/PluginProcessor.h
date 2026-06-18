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

    // float input is treated as volts at the pedal input; this scales the multi-volt internal
    // output back toward unity. Tunable at Step 9 with the VU meters / -12 dBu calibration.
    static constexpr float kOutputMakeup = 0.25f;

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
