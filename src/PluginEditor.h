#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include "PluginProcessor.h"

class TommyAudioProcessorEditor : public juce::AudioProcessorEditor
{
public:
    explicit TommyAudioProcessorEditor (TommyAudioProcessor&);
    ~TommyAudioProcessorEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

private:
    [[maybe_unused]] TommyAudioProcessor& processorRef;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (TommyAudioProcessorEditor)
};
