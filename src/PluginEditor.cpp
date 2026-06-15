#include "PluginEditor.h"

TommyAudioProcessorEditor::TommyAudioProcessorEditor (TommyAudioProcessor& p)
    : AudioProcessorEditor (&p), processorRef (p)
{
    setSize (520, 480);
}

TommyAudioProcessorEditor::~TommyAudioProcessorEditor() = default;

void TommyAudioProcessorEditor::paint (juce::Graphics& g)
{
    g.fillAll (juce::Colours::black);
    g.setColour (juce::Colours::white);
    g.setFont (juce::FontOptions (24.0f));
    g.drawFittedText ("Tommy", getLocalBounds(), juce::Justification::centred, 1);
}

void TommyAudioProcessorEditor::resized()
{
}
